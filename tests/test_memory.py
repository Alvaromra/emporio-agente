from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from emporio.agent import Agent
from emporio.llm import AssistantTurn, Message, ToolCall
from emporio.memory import ConversationStore
from emporio.memory.export import to_markdown

NOW = datetime(2026, 10, 31, 10, 30, tzinfo=ZoneInfo("America/Campo_Grande"))
TEST_PEPPER = "pepper-de-teste"


@pytest.fixture
def store(tmp_path):
    return ConversationStore(tmp_path / "app.db")


def test_ida_e_volta_de_mensagens(store):
    call = ToolCall("detalhar_produto", {"produto": "GD20"}, id="c1")
    messages = [
        Message("user", "quanto custa o GD20?"),
        Message("assistant", "", tool_calls=[call]),
        Message.tool_result(call, {"preco": "R$ 2.199,00"}),
        Message("assistant", "Sai por R$ 1.999,00.", internal=True),
        Message("assistant", "Custa R$ 2.199,00."),
    ]
    store.ensure_session("s1", "cli", NOW)
    store.append("s1", messages[:2], NOW)
    store.append("s1", messages[2:], NOW)  # gravação incremental continua a sequência
    loaded = store.load("s1")
    assert [(m.role, m.content, m.internal) for m in loaded] == [
        (m.role, m.content, m.internal) for m in messages
    ]
    assert loaded[1].tool_calls == [call]
    assert loaded[2].tool_name == "detalhar_produto" and loaded[2].tool_call_id == "c1"


def test_protocolos_sequenciais_por_dia(store):
    a = store.register("s1", "reclamacao", "Defeito no braço", 3, NOW)
    b = store.register("s2", "atraso_pedido", "Pedido parado", 8, NOW)
    c = store.register("s3", "outro", "Dúvida", None, NOW + timedelta(days=1))
    assert (a.protocol, b.protocol, c.protocol) == (
        "EM20261031-0001",
        "EM20261031-0002",
        "EM20261101-0001",
    )
    assert [h["protocol"] for h in store.list_handoffs()] == [a.protocol, b.protocol, c.protocol]


def test_exclusao_a_pedido_do_cliente(store):
    store.ensure_session("s1", "web", NOW)
    store.append("s1", [Message("user", "oi")], NOW)
    store.register("s1", "outro", "x", None, NOW)
    assert store.delete_session("s1")
    assert store.load("s1") == [] and store.list_handoffs() == []
    assert not store.delete_session("s1")


def test_retencao(store):
    store.ensure_session("antiga", "web", NOW - timedelta(days=120))
    store.ensure_session("recente", "web", NOW - timedelta(days=10))
    assert store.purge(90, NOW) == 1
    assert [s.session_id for s in store.list_sessions()] == ["recente"]


def test_exportacao_em_markdown_esconde_mensagens_internas():
    call = ToolCall("status_da_loja", {})
    texto = to_markdown(
        [
            Message("user", "vocês estão abertos?"),
            Message("assistant", "", tool_calls=[call]),
            Message.tool_result(call, {"situacao": "Aberta"}),
            Message("assistant", "resposta reprovada", internal=True),
            Message("assistant", "Estamos abertos até as 13h!"),
        ],
        "Horário",
    )
    assert "**Cliente:** vocês estão abertos?" in texto
    assert "`status_da_loja({})`" in texto
    assert "**Tom:** Estamos abertos até as 13h!" in texto
    assert "reprovada" not in texto and "situacao" not in texto


# ------------------------------------------------------------------ integração com o agente


@dataclass
class ScriptedModel:
    script: list
    name: str = "roteiro"
    model: str = "teste"
    received: list = field(default_factory=list)

    def complete(self, system, messages, tools):
        self.received.append(list(messages))
        return self.script.pop(0)


def say(text):
    return AssistantTurn(text, [], Message("assistant", text))


def call(name, **arguments):
    calls = [ToolCall(name, arguments, id="x")]
    return AssistantTurn("", calls, Message("assistant", "", tool_calls=calls))


@pytest.fixture
def agent_with_store(store, store_db, settings_env):
    settings_env(EMPORIO_NOW="2026-10-31T10:30")

    def _make(*script):
        model = ScriptedModel(list(script))
        return Agent(model, db_path=store_db, pepper=TEST_PEPPER, store=store), model

    return _make


def test_conversa_salva_sem_dados_pessoais(agent_with_store, store):
    agent, _ = agent_with_store(
        call("consultar_pedido", numero_pedido=1, email_ou_telefone="[EMAIL_1]"),
        say("Pedro, seu pedido foi entregue."),
    )
    session = agent.new_session("web")
    agent.reply(session, "pedido 1, email pedro.oliveira@jmail.com")
    saved = store.load(session.id)
    assert len(saved) == 4  # cliente, chamada, resultado, resposta
    assert all("jmail" not in m.content for m in saved)
    assert saved[1].tool_calls[0].arguments["email_ou_telefone"] == "[EMAIL_1]"


def test_retomar_conversa_depois_de_reiniciar(agent_with_store, store, store_db):
    agent, _ = agent_with_store(say("Oi! Como posso ajudar?"))
    session = agent.new_session("cli")
    agent.reply(session, "oi")

    # "Reinício": um agente novo, com o mesmo banco.
    model = ScriptedModel([say("Claro, me diz o modelo.")])
    restarted = Agent(model, db_path=store_db, pepper=TEST_PEPPER, store=store)
    resumed = restarted.resume(session.id)
    restarted.reply(resumed, "quero saber um preço")
    assert [m.content for m in model.received[0]] == [
        "oi",
        "Oi! Como posso ajudar?",
        "quero saber um preço",
    ]
    assert len(store.load(session.id)) == 4
    assert restarted.resume("nao-existe") is None


def test_encaminhamento_vai_para_o_banco(agent_with_store, store):
    agent, _ = agent_with_store(
        call("encaminhar_para_atendente", motivo="atraso_pedido", resumo="Pedido 8 atrasado"),
        say("Registrei o protocolo EM20261031-0001."),
    )
    agent.reply(agent.new_session("web"), "meu pedido está atrasado, quero falar com alguém")
    [handoff] = store.list_handoffs()
    assert handoff["protocol"] == "EM20261031-0001" and handoff["reason"] == "atraso_pedido"
