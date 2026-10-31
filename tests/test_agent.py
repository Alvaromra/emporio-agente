"""Testes do agente com um modelo roteirizado: cada resposta do "modelo" é definida no teste."""

from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

import pytest

from emporio.agent import Agent, Session, guardrails
from emporio.agent.loop import MAX_STEPS, window
from emporio.agent.pii import PiiVault
from emporio.agent.prompt import build_system_prompt
from emporio.llm import AssistantTurn, Message, ToolCall

TEST_PEPPER = "pepper-de-teste"  # o mesmo do conftest (fixture store_db)
CAMPO_GRANDE = ZoneInfo("America/Campo_Grande")


def say(text: str) -> AssistantTurn:
    return AssistantTurn(text, [], Message("assistant", text))


def call(name: str, **arguments) -> AssistantTurn:
    calls = [ToolCall(name, arguments, id=f"id-{name}")]
    return AssistantTurn("", calls, Message("assistant", "", tool_calls=calls))


@dataclass
class ScriptedModel:
    script: list
    name: str = "roteiro"
    model: str = "teste"
    received: list = field(default_factory=list)

    def complete(self, system, messages, tools):
        self.received.append({"system": system, "messages": list(messages), "tools": tools})
        step = self.script.pop(0)
        return step(self.received[-1]) if callable(step) else step


@pytest.fixture
def agent_for(store_db, settings_env):
    settings_env(EMPORIO_NOW="2026-10-31T10:30")

    def _make(*script):
        model = ScriptedModel(list(script))
        return Agent(model, db_path=store_db, pepper=TEST_PEPPER), model

    return _make


def test_executa_ferramenta_e_devolve_resposta(agent_for):
    agent, model = agent_for(
        call("detalhar_produto", produto="Takamine GD20"),
        say("O Takamine GD20 custa **R$ 2.199,00**, ou R$ 2.089,05 no PIX."),
    )
    reply = agent.reply(Session(), "quanto custa o Takamine GD20?")
    assert reply.text.startswith("O Takamine GD20 custa")
    assert [t.name for t in reply.tools] == ["detalhar_produto"] and reply.tools[0].ok
    tool_message = model.received[1]["messages"][-1]
    assert tool_message.role == "tool" and "R$ 2.199,00" in tool_message.content


def test_email_nao_chega_ao_modelo_mas_chega_a_ferramenta(agent_for):
    agent, model = agent_for(
        call("consultar_pedido", numero_pedido=1, email_ou_telefone="[EMAIL_1]"),
        say("Pedro, seu pedido 1 foi entregue. Confirmei pelo [EMAIL_1]."),
    )
    reply = agent.reply(Session(), "pedido 1, meu email é pedro.oliveira@jmail.com")
    sent = model.received[0]["messages"][-1].content
    assert "jmail" not in sent and "[EMAIL_1]" in sent
    assert reply.tools[0].ok  # a ferramenta recebeu o e-mail real e verificou
    assert reply.tools[0].arguments["email_ou_telefone"] == "[EMAIL_1]"  # o trace não guarda o dado
    assert "pedro.oliveira@jmail.com" in reply.text  # o cliente vê o próprio e-mail


def test_valor_inventado_e_corrigido(agent_for):
    agent, model = agent_for(
        say("Esse violão sai por R$ 1.999,00."),  # sem consultar nada
        call("detalhar_produto", produto="Takamine GD20"),
        say("O Takamine GD20 custa R$ 2.199,00."),
    )
    reply = agent.reply(Session(), "quanto custa o Takamine GD20?")
    assert reply.text == "O Takamine GD20 custa R$ 2.199,00."
    assert any("corrigir" in e for e in reply.events)
    correction = model.received[1]["messages"][-1]
    assert correction.internal and "R$ 1.999,00" in correction.content


def test_valor_inventado_duas_vezes_vira_resposta_segura(agent_for):
    agent, _ = agent_for(say("Sai por R$ 1.999,00."), say("Na verdade, R$ 1.899,00."))
    reply = agent.reply(Session(), "quanto custa o Takamine GD20?")
    assert reply.text == guardrails.FALLBACK_UNGROUNDED


def test_valor_dito_pelo_cliente_pode_ser_repetido(agent_for):
    agent, _ = agent_for(say("Entendi, você quer gastar até R$ 1.000. É violão ou guitarra?"))
    assert "R$ 1.000" in agent.reply(Session(), "quero algo até R$ 1000").text


def test_limite_de_rodadas(agent_for):
    agent, _ = agent_for(*[call("status_da_loja") for _ in range(MAX_STEPS)])
    reply = agent.reply(Session(), "oi")
    assert reply.text == guardrails.FALLBACK_LOOP
    assert len(reply.tools) == MAX_STEPS


def test_erro_de_ferramenta_volta_para_o_modelo(agent_for):
    agent, model = agent_for(
        call("consultar_pedido", numero_pedido=1),
        say("Para consultar, me passa o e-mail ou telefone da compra?"),
    )
    reply = agent.reply(Session(), "cadê meu pedido 1?")
    assert not reply.tools[0].ok
    assert "erro" in model.received[1]["messages"][-1].content


def test_marcacao_vazada_e_removida(agent_for):
    agent, _ = agent_for(say("Claro!<tool_response|> Posso ajudar em mais algo?"))
    assert agent.reply(Session(), "oi").text == "Claro! Posso ajudar em mais algo?"


def test_encaminhamento_gera_protocolo(agent_for):
    agent, _ = agent_for(
        call("encaminhar_para_atendente", motivo="reclamacao", resumo="Instrumento com defeito"),
        say("Pronto, registrei. Seu protocolo é EM20261031-0001."),
    )
    reply = agent.reply(Session(), "quero reclamar")
    assert reply.tools[0].ok
    assert agent.handoffs.items[0].protocol == "EM20261031-0001"


def test_historico_continua_entre_mensagens(agent_for):
    agent, model = agent_for(say("Oi! Como posso ajudar?"), say("Claro."))
    session = Session()
    agent.reply(session, "oi")
    agent.reply(session, "tudo bem?")
    roles = [m.role for m in model.received[1]["messages"]]
    assert roles == ["user", "assistant", "user"]


def test_prompt_traz_hora_e_situacao_da_loja():
    sabado_tarde = build_system_prompt(_at("2026-10-31T14:00"))
    assert "sábado, 31/10/2026, 14:00" in sabado_tarde
    assert "equipe volta terça, 03/11 às 09:00" in sabado_tarde
    assert "fora do expediente" not in build_system_prompt(_at("2026-11-04T10:00"))


def _at(text):
    from datetime import datetime

    return datetime.fromisoformat(text).replace(tzinfo=CAMPO_GRANDE)


def test_janela_de_historico_nao_separa_ferramenta_da_resposta():
    history = []
    for i in range(15):
        history += [
            Message("user", f"pergunta {i}"),
            Message("assistant", "", tool_calls=[ToolCall("status_da_loja", {})]),
            Message("tool", "{}", tool_name="status_da_loja"),
            Message("assistant", "resposta"),
        ]
    trimmed = window(history, user_turns=3)
    assert trimmed[0].content == "pergunta 12" and len(trimmed) == 12


# ------------------------------------------------------------------ dados pessoais


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("meu email é Ana.Souza@jmail.com", "meu email é [EMAIL_1]"),
        ("tel (67) 99654-7821", "tel [TELEFONE_1]"),
        ("+55 67 99654-7821", "[TELEFONE_1]"),
        ("cpf 123.456.789-09", "cpf [CPF REMOVIDO]"),
        ("cartão 4111 1111 1111 1111", "cartão [CARTÃO REMOVIDO]"),
    ],
)
def test_dados_pessoais_viram_marcadores(text, expected):
    assert PiiVault().redact(text) == expected


@pytest.mark.parametrize(
    "text",
    ["preço R$ 2.199,00", "CEP 79202-333", "pedido 12345", "rastreio BRJL5544332BR", "31/10/2026"],
)
def test_dados_que_nao_sao_pessoais_ficam(text):
    assert PiiVault().redact(text) == text


def test_mesmo_contato_mesmo_marcador_e_restauracao():
    vault = PiiVault()
    assert vault.redact("a@b.com") == vault.redact("a@b.com") == "[EMAIL_1]"
    assert vault.restore({"x": ["[EMAIL_1]"]}) == {"x": ["a@b.com"]}


def test_valores_em_reais_sao_lidos_em_centavos():
    assert guardrails.amounts("R$ 2.199,00, R$2199 e R$ 35,5") == {219900, 3550}
