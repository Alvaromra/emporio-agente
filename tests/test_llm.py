"""Testes da camada de provedores, sem rede: os clientes dos SDKs são substituídos."""

from types import SimpleNamespace

import pytest
from google.genai import errors, types
from ollama import ChatResponse
from ollama import Message as OllamaMessage

from emporio.llm import LLMError, Message, ToolCall, gemini, get_provider, ollama_backend
from emporio.tools import TOOLS

TOOLS_LIST = [TOOLS["detalhar_produto"], TOOLS["status_da_loja"]]
CALL = ToolCall("detalhar_produto", {"produto": "Takamine GD20"}, id="c1")
HISTORY = [
    Message("user", "quanto custa o Takamine GD20?"),
    Message("assistant", "", tool_calls=[CALL]),
    Message.tool_result(CALL, {"preco": "R$ 2.199,00"}),
]


# ------------------------------------------------------------------ Gemini


def test_gemini_declaracoes_de_ferramentas():
    [tool] = gemini.tool_declarations(TOOLS_LIST)
    by_name = {d.name: d for d in tool.function_declarations}
    assert by_name["detalhar_produto"].parameters_json_schema["required"] == ["produto"]
    assert by_name["status_da_loja"].parameters_json_schema is None  # sem parâmetros


def test_gemini_historico_convertido():
    contents = gemini.to_contents(HISTORY)
    assert [c.role for c in contents] == ["user", "model", "user"]
    call = contents[1].parts[0].function_call
    assert (call.name, call.args, call.id) == (
        "detalhar_produto",
        {"produto": "Takamine GD20"},
        "c1",
    )
    response = contents[2].parts[0].function_response
    assert response.response == {"preco": "R$ 2.199,00"} and response.id == "c1"


def test_gemini_varias_respostas_de_ferramenta_viram_uma_mensagem():
    other = ToolCall("status_da_loja", {}, id="c2")
    history = [*HISTORY, Message.tool_result(other, {"situacao": "Aberta"})]
    contents = gemini.to_contents(history)
    assert len(contents) == 3 and len(contents[2].parts) == 2


def gemini_response(*parts):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=list(parts)))],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=120, candidates_token_count=8
        ),
    )


def test_gemini_resposta_ignora_raciocinio_interno():
    response = gemini_response(
        types.Part(text="o cliente quer preço, vou consultar", thought=True),
        types.Part(
            function_call=types.FunctionCall(
                name="detalhar_produto", args={"produto": "GD20"}, id="x"
            )
        ),
    )
    turn = gemini.parse_response(response)
    assert turn.text == ""
    assert turn.tool_calls == [ToolCall("detalhar_produto", {"produto": "GD20"}, "x")]
    assert turn.usage == {"entrada": 120, "saida": 8}
    # A mensagem original é preservada para reenviar (thought signatures).
    assert isinstance(turn.message.raw, types.Content)


def test_gemini_resposta_sem_candidatos():
    turn = gemini.parse_response(types.GenerateContentResponse(candidates=[]))
    assert turn.text == "" and turn.tool_calls == []


class FakeModels:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_gemini_complete_envia_sistema_ferramentas_e_desliga_execucao_automatica():
    models = FakeModels(gemini_response(types.Part(text="Custa R$ 2.199,00.")))
    provider = gemini.GeminiProvider(client=SimpleNamespace(models=models))
    turn = provider.complete("Você é atendente.", HISTORY, TOOLS_LIST)
    assert turn.text == "Custa R$ 2.199,00."
    config = models.calls[0]["config"]
    assert config.system_instruction == "Você é atendente."
    assert config.automatic_function_calling.disable is True
    assert models.calls[0]["model"] == "gemma-4-26b-a4b-it"


@pytest.mark.parametrize(
    ("code", "hint"), [(429, "Limite de uso"), (401, "inválida"), (404, "Modelo")]
)
def test_gemini_erros_amigaveis(code, hint):
    error = errors.ClientError(code, {"error": {"code": code, "message": "x", "status": "X"}})
    provider = gemini.GeminiProvider(
        client=SimpleNamespace(models=FakeModels(error)), sleep=lambda seconds: None
    )
    with pytest.raises(LLMError, match=hint):
        provider.complete("s", [Message("user", "oi")], [])


def quota_error(delay: str) -> errors.ClientError:
    body = {
        "error": {
            "code": 429,
            "message": f"Quota exceeded. Please retry in {delay}.",
            "status": "RESOURCE_EXHAUSTED",
            "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay}],
        }
    }
    return errors.ClientError(429, body)


class FlakyModels:
    """Falha com 429 nas primeiras chamadas e depois responde."""

    def __init__(self, failures):
        self.failures = list(failures)

    def generate_content(self, **kwargs):
        if self.failures:
            raise self.failures.pop(0)
        return gemini_response(types.Part(text="ok"))


def test_gemini_espera_o_tempo_pedido_pela_api_e_repete():
    waits = []
    models = FlakyModels([quota_error("24s"), quota_error("5.8s")])
    provider = gemini.GeminiProvider(client=SimpleNamespace(models=models), sleep=waits.append)
    assert provider.complete("s", [Message("user", "oi")], []).text == "ok"
    assert waits == [25.0, pytest.approx(6.8)]


def test_gemini_cota_diaria_nao_segura_o_cliente():
    waits = []
    models = FlakyModels([quota_error("3600s")])
    provider = gemini.GeminiProvider(client=SimpleNamespace(models=models), sleep=waits.append)
    with pytest.raises(LLMError, match="Limite de uso"):
        provider.complete("s", [Message("user", "oi")], [])
    assert waits == []


def test_gemini_desiste_depois_de_algumas_tentativas():
    waits = []
    models = FlakyModels([quota_error("1s")] * 10)
    provider = gemini.GeminiProvider(client=SimpleNamespace(models=models), sleep=waits.append)
    with pytest.raises(LLMError):
        provider.complete("s", [Message("user", "oi")], [])
    assert len(waits) == gemini.RATE_LIMIT_RETRIES


def test_gemini_sem_chave():
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        gemini.GeminiProvider(api_key=None)


# ------------------------------------------------------------------ Ollama


def test_ollama_mensagens_convertidas():
    messages = ollama_backend.to_messages("sistema", HISTORY)
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "tool"]
    assert messages[2]["tool_calls"][0]["function"]["arguments"] == {"produto": "Takamine GD20"}
    assert messages[3]["tool_name"] == "detalhar_produto"


def test_ollama_resposta_com_tool_calls():
    response = ChatResponse(
        model="gemma4",
        message=OllamaMessage(
            role="assistant",
            content="",
            tool_calls=[
                OllamaMessage.ToolCall(
                    function=OllamaMessage.ToolCall.Function(
                        name="buscar_produtos", arguments={"preco_max": 1000}
                    )
                )
            ],
        ),
    )
    turn = ollama_backend.parse_response(response)
    assert turn.tool_calls == [ToolCall("buscar_produtos", {"preco_max": 1000})]


def test_ollama_formato_nativo_do_gemma_vazado_no_texto():
    text = (
        'Vou verificar. <|tool_call>call:buscar_produtos{categoria:<|"|>violão<|"|>,'
        "preco_max:1000,incluir_indisponiveis:false}<tool_call|>"
    )
    calls, remaining = ollama_backend.parse_native_calls(text)
    assert calls == [
        ToolCall(
            "buscar_produtos",
            {"categoria": "violão", "preco_max": 1000, "incluir_indisponiveis": False},
        )
    ]
    assert remaining == "Vou verificar."


def test_ollama_texto_com_virgula_e_dois_pontos_dentro_de_aspas():
    text = (
        '<|tool_call>call:buscar_politicas{pergunta:<|"|>troca: prazo, condições<|"|>}<tool_call|>'
    )
    [call], _ = ollama_backend.parse_native_calls(text)
    assert call.arguments == {"pergunta": "troca: prazo, condições"}


class FakeOllama:
    def __init__(self, result):
        self.result = result
        self.kwargs = None

    def chat(self, **kwargs):
        self.kwargs = kwargs
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_ollama_complete_e_parametro_think():
    fake = FakeOllama(
        ChatResponse(model="m", message=OllamaMessage(role="assistant", content="ok"))
    )
    provider = ollama_backend.OllamaProvider(think=False, client=fake)
    assert provider.complete("s", [Message("user", "oi")], TOOLS_LIST).text == "ok"
    assert fake.kwargs["think"] is False
    assert fake.kwargs["tools"][0]["function"]["name"] == "detalhar_produto"


def test_ollama_modelo_nao_baixado():
    import ollama

    fake = FakeOllama(ollama.ResponseError("model not found", status_code=404))
    with pytest.raises(LLMError, match="ollama pull"):
        ollama_backend.OllamaProvider(client=fake).complete("s", [Message("user", "oi")], [])


# ------------------------------------------------------------------ Fábrica


def test_fabrica_escolhe_provedor(settings_env):
    settings_env(EMPORIO_LLM_PROVIDER="ollama", EMPORIO_LLM_MODEL="gemma4:e2b")
    provider = get_provider()
    assert (provider.name, provider.model) == ("ollama", "gemma4:e2b")


def test_fabrica_gemini_com_chave(settings_env):
    settings_env(
        EMPORIO_LLM_PROVIDER="gemini", GEMINI_API_KEY="chave-de-teste", EMPORIO_LLM_MODEL=""
    )
    provider = get_provider()
    assert (provider.name, provider.model) == ("gemini", "gemma-4-26b-a4b-it")


def test_fabrica_provedor_desconhecido(settings_env):
    settings_env(EMPORIO_LLM_PROVIDER="openai")
    with pytest.raises(LLMError, match="desconhecido"):
        get_provider()
