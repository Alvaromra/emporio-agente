from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from emporio.agent import Agent
from emporio.llm import AssistantTurn, LLMError, Message, ToolCall
from emporio.memory import ConversationStore
from emporio.web.app import MAX_MESSAGE_CHARS, create_app

TEST_PEPPER = "pepper-de-teste"


@dataclass
class EchoModel:
    """Consulta o pedido na primeira rodada e responde na segunda."""

    name: str = "roteiro"
    model: str = "teste"
    fail: bool = False

    def complete(self, system, messages, tools):
        if self.fail:
            raise LLMError("Limite de uso da Gemini API atingido.")
        last = messages[-1]
        if last.role == "user" and "pedido" in last.content:
            calls = [
                ToolCall("consultar_pedido", {"numero_pedido": 1, "email_ou_telefone": "[EMAIL_1]"})
            ]
            return AssistantTurn("", calls, Message("assistant", "", tool_calls=calls))
        text = (
            "Pedro, seu pedido foi entregue." if last.role == "tool" else "Oi! Como posso ajudar?"
        )
        return AssistantTurn(text, [], Message("assistant", text))


@pytest.fixture
def client_for(store_db, tmp_path, settings_env):
    settings_env(EMPORIO_NOW="2026-10-31T10:30")

    def _make(model=None):
        store = ConversationStore(tmp_path / "app.db")
        agent = Agent(model or EchoModel(), db_path=store_db, pepper=TEST_PEPPER, store=store)
        return TestClient(create_app(agent, store)), store

    return _make


def test_pagina_e_status_da_loja(client_for):
    client, _ = client_for()
    assert "Empório da Música" in client.get("/").text
    loja = client.get("/api/loja").json()
    assert loja["aberta"] is True and loja["situacao"] == "Aberta agora, até as 13:00."
    assert client.get("/api/saude").json()["ok"] is True


def test_conversa_completa(client_for):
    client, store = client_for()
    session_id = client.post("/api/conversas").json()["id"]
    r = client.post(
        f"/api/conversas/{session_id}/mensagens",
        json={"texto": "meu pedido 1, email pedro.oliveira@jmail.com"},
    ).json()
    assert r["resposta"] == "Pedro, seu pedido foi entregue."
    assert r["ferramentas"][0]["nome"] == "consultar_pedido" and r["ferramentas"][0]["ok"]
    assert r["ferramentas"][0]["argumentos"]["email_ou_telefone"] == "[EMAIL_1]"

    historico = client.get(f"/api/conversas/{session_id}").json()["mensagens"]
    assert [m["autor"] for m in historico] == ["cliente", "tom"]
    assert "jmail" not in historico[0]["texto"]  # o histórico guardado é o mascarado
    assert all("jmail" not in m.content for m in store.load(session_id))


def test_conversa_retomada_depois_de_reiniciar(client_for, store_db, tmp_path):
    client, store = client_for()
    session_id = client.post("/api/conversas").json()["id"]
    client.post(f"/api/conversas/{session_id}/mensagens", json={"texto": "oi"})
    agent = Agent(EchoModel(), db_path=store_db, pepper=TEST_PEPPER, store=store)
    restarted = TestClient(create_app(agent, store))
    assert len(restarted.get(f"/api/conversas/{session_id}").json()["mensagens"]) == 2


def test_apagar_conversa(client_for):
    client, store = client_for()
    session_id = client.post("/api/conversas").json()["id"]
    client.post(f"/api/conversas/{session_id}/mensagens", json={"texto": "oi"})
    assert client.delete(f"/api/conversas/{session_id}").status_code == 204
    assert store.load(session_id) == []
    assert client.get(f"/api/conversas/{session_id}").status_code == 404


@pytest.mark.parametrize("texto", ["", "x" * (MAX_MESSAGE_CHARS + 1)])
def test_mensagem_vazia_ou_longa_demais(client_for, texto):
    client, _ = client_for()
    session_id = client.post("/api/conversas").json()["id"]
    response = client.post(f"/api/conversas/{session_id}/mensagens", json={"texto": texto})
    assert response.status_code == 422


def test_conversa_inexistente(client_for):
    client, _ = client_for()
    response = client.post("/api/conversas/nao-existe/mensagens", json={"texto": "oi"})
    assert response.status_code == 404


def test_falha_do_modelo_vira_503_com_mensagem(client_for):
    client, _ = client_for(EchoModel(fail=True))
    session_id = client.post("/api/conversas").json()["id"]
    response = client.post(f"/api/conversas/{session_id}/mensagens", json={"texto": "oi"})
    assert response.status_code == 503
    assert "Limite de uso" in response.json()["detail"]


def test_sobe_mesmo_sem_chave_e_explica(settings_env, tmp_path):
    settings_env(EMPORIO_LLM_PROVIDER="gemini", GEMINI_API_KEY="", GOOGLE_API_KEY="")
    client = TestClient(create_app(store=ConversationStore(tmp_path / "app.db")))
    saude = client.get("/api/saude").json()
    assert saude["ok"] is False and "GEMINI_API_KEY" in saude["erro"]
    assert client.post("/api/conversas").status_code == 503
