"""API HTTP e interface web (FastAPI).

A interface é um único arquivo HTML, sem etapa de build: o servidor Python é tudo o
que precisa rodar. A mesma API que a página usa serve para integrar outro canal
(ex.: WhatsApp) e está documentada em /docs.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from emporio import clock
from emporio.agent import Agent, Session
from emporio.config import get_settings
from emporio.llm import LLMError, get_provider
from emporio.memory import ConversationStore
from emporio.rules.store import store_status, weekly_hours_text

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
MAX_MESSAGE_CHARS = 1000
MAX_ACTIVE_SESSIONS = 500


class NewMessage(BaseModel):
    texto: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


@dataclass
class SessionPool:
    """Conversas ativas em memória (com o cofre de dados pessoais), com uma trava por
    conversa para que duas mensagens simultâneas não se embaralhem."""

    capacity: int = MAX_ACTIVE_SESSIONS
    sessions: OrderedDict = field(default_factory=OrderedDict)
    locks: dict = field(default_factory=dict)
    mutex: threading.Lock = field(default_factory=threading.Lock)

    def put(self, session: Session) -> None:
        with self.mutex:
            self.sessions[session.id] = session
            self.sessions.move_to_end(session.id)
            self.locks.setdefault(session.id, threading.Lock())
            while len(self.sessions) > self.capacity:
                old_id, _ = self.sessions.popitem(last=False)
                self.locks.pop(old_id, None)

    def get(self, session_id: str) -> Session | None:
        with self.mutex:
            session = self.sessions.get(session_id)
            if session:
                self.sessions.move_to_end(session_id)
            return session

    def lock(self, session_id: str) -> threading.Lock:
        with self.mutex:
            return self.locks.setdefault(session_id, threading.Lock())

    def drop(self, session_id: str) -> None:
        with self.mutex:
            self.sessions.pop(session_id, None)
            self.locks.pop(session_id, None)


def create_app(agent: Agent | None = None, store: ConversationStore | None = None) -> FastAPI:
    settings = get_settings()
    store = store or ConversationStore(settings.app_db_path)
    startup_error: str | None = None
    if agent is None:
        try:
            agent = Agent(get_provider(), store=store)
        except LLMError as error:  # sobe mesmo assim, para mostrar o problema na página
            startup_error = str(error)
            logger.error("Agente indisponível: %s", error)
    pool = SessionPool()

    app = FastAPI(
        title="Empório da Música: agente de atendimento",
        description="API do assistente virtual Tom.",
        version="0.1.0",
    )

    def require_agent() -> Agent:
        if agent is None:
            raise HTTPException(503, detail=startup_error or "Agente indisponível.")
        return agent

    def find_session(session_id: str) -> Session:
        session = pool.get(session_id)
        if session is None and agent is not None:
            session = agent.resume(session_id)
            if session is not None:
                pool.put(session)
        if session is None:
            raise HTTPException(404, detail="Conversa não encontrada.")
        return session

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/saude")
    def health() -> dict:
        return {
            "ok": agent is not None,
            "provedor": agent.provider.name if agent else None,
            "modelo": agent.provider.model if agent else None,
            "erro": startup_error,
        }

    @app.get("/api/loja")
    def store_info() -> dict:
        status = store_status(clock.now())
        return {
            "aberta": status.is_open,
            "situacao": status.summary(),
            "horario": weekly_hours_text(),
        }

    @app.post("/api/conversas", status_code=201)
    def new_conversation() -> dict:
        session = require_agent().new_session("web")
        pool.put(session)
        return {"id": session.id}

    @app.get("/api/conversas/{session_id}")
    def conversation(session_id: str) -> dict:
        session = find_session(session_id)
        visible = [
            {"autor": "cliente" if m.role == "user" else "tom", "texto": m.content}
            for m in session.history
            if not m.internal and m.role in ("user", "assistant") and m.content
        ]
        return {"id": session.id, "mensagens": visible}

    @app.post("/api/conversas/{session_id}/mensagens")
    def send_message(session_id: str, body: NewMessage) -> dict:
        current = require_agent()
        session = find_session(session_id)
        with pool.lock(session_id):
            try:
                reply = current.reply(session, body.texto.strip())
            except LLMError as error:
                raise HTTPException(503, detail=str(error)) from error
        return {
            "resposta": reply.text,
            "ferramentas": [
                {"nome": t.name, "argumentos": t.arguments, "ok": t.ok, "ms": t.elapsed_ms}
                for t in reply.tools
            ],
            "eventos": reply.events,
            "tempo_s": reply.elapsed_s,
            "tokens": reply.usage,
        }

    @app.delete("/api/conversas/{session_id}", status_code=204)
    def delete_conversation(session_id: str) -> Response:
        """Exclusão a pedido do cliente (manual, seção 9)."""
        pool.drop(session_id)
        if not store.delete_session(session_id):
            raise HTTPException(404, detail="Conversa não encontrada.")
        return Response(status_code=204)

    return app
