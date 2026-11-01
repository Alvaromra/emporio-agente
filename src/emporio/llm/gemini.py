"""Gemma 4 via Gemini API (Google AI Studio)."""

from __future__ import annotations

import json
import logging
import re
import time

import httpx
from google import genai
from google.genai import errors, types

from emporio.llm.base import AssistantTurn, LLMError, Message, ToolCall, parse_json_object
from emporio.tools import Tool

DEFAULT_MODEL = "gemma-4-26b-a4b-it"

logger = logging.getLogger(__name__)

# Cota do tier gratuito: a API diz quanto esperar ("Please retry in 24s"). Esperas curtas
# (limite por minuto) são respeitadas e a chamada é repetida; esperas longas (limite
# diário) viram erro imediato, porque não faz sentido segurar o cliente por horas.
RATE_LIMIT_RETRIES = 3
MAX_RATE_LIMIT_WAIT_S = 65

ERROR_HINTS = {
    400: "Requisição recusada pela Gemini API. Verifique se o modelo suporta ferramentas.",
    401: "Chave da Gemini API inválida. Confira GEMINI_API_KEY no .env.",
    403: "Chave da Gemini API sem permissão. Confira GEMINI_API_KEY no .env.",
    404: "Modelo não encontrado na Gemini API. Confira EMPORIO_LLM_MODEL.",
    429: "Limite de uso da Gemini API atingido (o tier gratuito tem cotas baixas). "
    "Aguarde um minuto ou use o Ollama local.",
}


def tool_declarations(tools: list[Tool]) -> list[types.Tool]:
    declarations = [
        types.FunctionDeclaration(
            name=t.name,
            description=t.description,
            # Ferramentas sem parâmetros não enviam schema (objeto vazio é rejeitado por
            # alguns modelos).
            parameters_json_schema=t.parameters if t.parameters["properties"] else None,
        )
        for t in tools
    ]
    return [types.Tool(function_declarations=declarations)] if declarations else []


def to_contents(messages: list[Message]) -> list[types.Content]:
    """Converte o histórico neutro para o formato da Gemini API.

    Respostas de ferramentas consecutivas viram uma única mensagem com várias partes,
    como a API espera depois de um turno com várias chamadas.
    """
    contents: list[types.Content] = []
    pending_responses: list[types.Part] = []

    def flush() -> None:
        if pending_responses:
            contents.append(types.Content(role="user", parts=list(pending_responses)))
            pending_responses.clear()

    for message in messages:
        if message.role == "tool":
            pending_responses.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        name=message.tool_name,
                        id=message.tool_call_id,
                        response=parse_json_object(message.content)
                        or {"resultado": message.content},
                    )
                )
            )
            continue
        flush()
        if message.role == "user":
            contents.append(types.Content(role="user", parts=[types.Part(text=message.content)]))
        elif isinstance(message.raw, types.Content):
            contents.append(message.raw)  # preserva thought signatures do próprio modelo
        else:
            parts = [types.Part(text=message.content)] if message.content else []
            parts += [
                types.Part(function_call=types.FunctionCall(name=c.name, args=c.arguments, id=c.id))
                for c in message.tool_calls
            ]
            contents.append(types.Content(role="model", parts=parts))
    flush()
    return contents


def parse_response(response: types.GenerateContentResponse) -> AssistantTurn:
    candidate = response.candidates[0] if response.candidates else None
    content = candidate.content if candidate and candidate.content else None
    texts: list[str] = []
    calls: list[ToolCall] = []
    for part in (content.parts or []) if content else []:
        if part.function_call:
            fc = part.function_call
            calls.append(ToolCall(fc.name, parse_json_object(fc.args), fc.id))
        elif part.text and not part.thought:  # raciocínio interno nunca vai ao cliente
            texts.append(part.text)
    text = "".join(texts).strip()
    usage = {}
    if response.usage_metadata:
        usage = {
            "entrada": response.usage_metadata.prompt_token_count or 0,
            "saida": response.usage_metadata.candidates_token_count or 0,
        }
    raw = content or types.Content(role="model", parts=[types.Part(text=text)])
    message = Message(role="assistant", content=text, tool_calls=calls, raw=raw)
    return AssistantTurn(text=text, tool_calls=calls, message=message, usage=usage)


def retry_delay_seconds(error: errors.APIError) -> float | None:
    """Tempo de espera sugerido pela API num erro 429, em segundos."""
    details = (error.details or {}).get("error", {}).get("details", []) if error.details else []
    for item in details:
        if str(item.get("@type", "")).endswith("RetryInfo") and item.get("retryDelay"):
            match = re.match(r"([\d.]+)s", str(item["retryDelay"]))
            if match:
                return float(match.group(1))
    match = re.search(r"retry in ([\d.]+)s", error.message or "")
    return float(match.group(1)) if match else None


def friendly_error(error: errors.APIError) -> LLMError:
    hint = ERROR_HINTS.get(error.code, "Falha na Gemini API.")
    return LLMError(f"{hint} (HTTP {error.code}: {error.message})")


class GeminiProvider:
    name = "gemini"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        temperature: float = 0.3,
        timeout_s: float = 60,
        client: genai.Client | None = None,
        sleep=time.sleep,
    ):
        if client is None and not api_key:
            raise LLMError(
                "GEMINI_API_KEY não definida. Crie uma chave gratuita em "
                "https://aistudio.google.com/apikey e adicione ao .env."
            )
        self.model = model
        self.temperature = temperature
        self.sleep = sleep
        self.client = client or genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=int(timeout_s * 1000),
                # O SDK repete falhas temporárias do servidor. O 429 (cota) é tratado em
                # complete(), respeitando o tempo de espera que a própria API informa.
                retry_options=types.HttpRetryOptions(
                    attempts=4,
                    initial_delay=2,
                    max_delay=30,
                    http_status_codes=[408, 500, 502, 503, 504],
                ),
            ),
        )

    def _rate_limit_wait(self, error: errors.APIError, attempt: int) -> float | None:
        """Segundos a esperar antes de repetir, ou None se o erro não deve ser repetido."""
        if error.code != 429 or attempt >= RATE_LIMIT_RETRIES:
            return None
        delay = retry_delay_seconds(error)
        delay = delay if delay is not None else 15.0 * (attempt + 1)
        return delay + 1 if delay <= MAX_RATE_LIMIT_WAIT_S else None

    def complete(self, system: str, messages: list[Message], tools: list[Tool]) -> AssistantTurn:
        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=tool_declarations(tools),
            # O agente controla o loop de ferramentas; o SDK não executa nada sozinho.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            temperature=self.temperature,
        )
        contents = to_contents(messages)
        for attempt in range(RATE_LIMIT_RETRIES + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model, contents=contents, config=config
                )
                break
            except errors.APIError as error:
                wait = self._rate_limit_wait(error, attempt)
                if wait is None:
                    raise friendly_error(error) from error
                logger.warning("Cota da Gemini API: aguardando %.0f s", wait)
                self.sleep(wait)
            except httpx.TimeoutException as error:
                raise LLMError("A Gemini API demorou demais para responder.") from error
            except httpx.HTTPError as error:
                raise LLMError(
                    "Não foi possível conectar à Gemini API. Verifique a conexão com a internet."
                ) from error
        return parse_response(response)


def describe_contents(contents: list[types.Content]) -> str:
    """Resumo legível do que é enviado à API (útil em depuração)."""
    return json.dumps([c.model_dump(exclude_none=True) for c in contents], ensure_ascii=False)
