"""Gemma 4 local via Ollama.

Útil para rodar sem internet e sem cotas, ou para manter os dados dos clientes fora
de serviços externos (ver LGPD no README).
"""

from __future__ import annotations

import json
import re

import httpx
import ollama

from emporio.llm.base import AssistantTurn, LLMError, Message, ToolCall, parse_json_object
from emporio.tools import Tool

DEFAULT_MODEL = "gemma4:e4b"
DEFAULT_HOST = "http://localhost:11434"

# Formato nativo de chamada do Gemma 4. Às vezes ele vaza no texto quando o runtime
# não o converte em tool_calls; nesse caso, o agente ainda consegue aproveitá-lo.
NATIVE_CALL = re.compile(r"<\|tool_call>\s*call:(\w+)\{(.*?)\}\s*<tool_call\|>", re.DOTALL)
NATIVE_QUOTE = '<|"|>'


def tool_specs(tools: list[Tool]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
        }
        for t in tools
    ]


def to_messages(system: str, messages: list[Message]) -> list[dict]:
    result = [{"role": "system", "content": system}]
    for m in messages:
        if m.role == "tool":
            result.append({"role": "tool", "content": m.content, "tool_name": m.tool_name})
        elif m.role == "assistant":
            entry: dict = {"role": "assistant", "content": m.content}
            if m.tool_calls:
                entry["tool_calls"] = [
                    {"function": {"name": c.name, "arguments": c.arguments}} for c in m.tool_calls
                ]
            result.append(entry)
        else:
            result.append({"role": "user", "content": m.content})
    return result


def _split_top_level(text: str, separator: str) -> list[str]:
    parts, current, in_string = [], [], False
    for char in text:
        if char == '"':
            in_string = not in_string
        if char == separator and not in_string:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return parts


def _native_value(raw: str):
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1]
    if raw in ("true", "false"):
        return raw == "true"
    try:
        return int(raw)
    except ValueError:
        try:
            return float(raw)
        except ValueError:
            return raw


def parse_native_calls(text: str) -> tuple[list[ToolCall], str]:
    """Extrai chamadas no formato nativo do Gemma 4 e devolve (chamadas, texto restante).

    Ex.: <|tool_call>call:detalhar_produto{produto:<|"|>Takamine GD20<|"|>}<tool_call|>
    Suporta argumentos planos (texto, número, booleano), que é o caso das ferramentas.
    """
    calls = []
    for match in NATIVE_CALL.finditer(text):
        body = match.group(2).replace(NATIVE_QUOTE, '"')
        arguments = {}
        for pair in _split_top_level(body, ","):
            pieces = _split_top_level(pair, ":")
            if len(pieces) >= 2:
                arguments[pieces[0].strip()] = _native_value(":".join(pieces[1:]))
        calls.append(ToolCall(match.group(1), arguments))
    remaining = NATIVE_CALL.sub("", text)
    remaining = re.sub(r"<\|tool_response>|<tool_response\|>", "", remaining).strip()
    return calls, remaining


def parse_response(response) -> AssistantTurn:
    message = response.message
    text = (message.content or "").strip()
    calls = [
        ToolCall(c.function.name, parse_json_object(c.function.arguments))
        for c in (message.tool_calls or [])
    ]
    if not calls and "call:" in text:
        calls, text = parse_native_calls(text)
    usage = {
        "entrada": getattr(response, "prompt_eval_count", 0) or 0,
        "saida": getattr(response, "eval_count", 0) or 0,
    }
    neutral = Message(role="assistant", content=text, tool_calls=calls)
    return AssistantTurn(text=text, tool_calls=calls, message=neutral, usage=usage)


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        host: str = DEFAULT_HOST,
        temperature: float = 0.3,
        timeout_s: float = 120,
        think: bool | None = None,
        client: ollama.Client | None = None,
    ):
        self.model = model
        self.host = host
        self.temperature = temperature
        self.think = think
        self.client = client or ollama.Client(host=host, timeout=timeout_s)

    def complete(self, system: str, messages: list[Message], tools: list[Tool]) -> AssistantTurn:
        kwargs: dict = {
            "model": self.model,
            "messages": to_messages(system, messages),
            "tools": tool_specs(tools) or None,
            "options": {"temperature": self.temperature},
        }
        if self.think is not None:
            kwargs["think"] = self.think
        try:
            response = self.client.chat(**kwargs)
        except ollama.ResponseError as error:
            if error.status_code == 404:
                raise LLMError(
                    f"Modelo '{self.model}' não encontrado no Ollama. "
                    f"Rode: ollama pull {self.model}"
                ) from error
            raise LLMError(f"Erro do Ollama: {error.error}") from error
        except (httpx.ConnectError, ConnectionError) as error:
            raise LLMError(
                f"Ollama não está acessível em {self.host}. Ele está rodando? "
                "Confira OLLAMA_HOST no .env."
            ) from error
        except httpx.TimeoutException as error:
            raise LLMError("O Ollama demorou demais para responder.") from error
        return parse_response(response)


def describe(messages: list[dict]) -> str:
    return json.dumps(messages, ensure_ascii=False)
