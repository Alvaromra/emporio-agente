"""Histórico de conversas e protocolos de encaminhamento em SQLite.

Fica num banco separado (`data/runtime/app.db`) do banco da loja, porque o ETL
recria o `store.db` do zero e a conversa dos clientes não pode ser apagada junto.

O que é guardado, e o que não é (LGPD, minimização):
- As mensagens são guardadas como o modelo as viu: e-mails e telefones já trocados
  por marcadores ([EMAIL_1]) e CPF/cartão removidos. O cofre que liga marcador e
  valor real vive só em memória e não é persistido.
- O registro de ferramentas guarda os argumentos com marcadores, nunca o contato.
- Conteúdo bruto do provedor (metadados internos do Gemini) não é guardado.
- Há prazo de retenção e exclusão por conversa (manual 9: o cliente pode pedir a
  exclusão dos seus dados).
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from emporio.llm import Message, ToolCall
from emporio.tools.base import Handoff

SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id  TEXT PRIMARY KEY,
    channel     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    session_id    TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    seq           INTEGER NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
    content       TEXT NOT NULL,
    tool_calls    TEXT,
    tool_name     TEXT,
    tool_call_id  TEXT,
    internal      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    PRIMARY KEY (session_id, seq)
);

CREATE TABLE IF NOT EXISTS handoffs (
    protocol    TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    reason      TEXT NOT NULL,
    summary     TEXT NOT NULL,
    order_id    INTEGER,
    status      TEXT NOT NULL DEFAULT 'aberto',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_handoffs_created ON handoffs (created_at);
"""


@dataclass(frozen=True)
class SessionInfo:
    session_id: str
    channel: str
    created_at: str
    updated_at: str
    messages: int


def _calls_to_json(calls: list[ToolCall]) -> str | None:
    if not calls:
        return None
    return json.dumps(
        [{"name": c.name, "arguments": c.arguments, "id": c.id} for c in calls], ensure_ascii=False
    )


def _calls_from_json(raw: str | None) -> list[ToolCall]:
    if not raw:
        return []
    return [ToolCall(c["name"], c["arguments"], c.get("id")) for c in json.loads(raw)]


class ConversationStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @contextmanager
    def _connect(self):
        # Uma conexão por operação: simples e seguro com várias threads (interface web).
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    # ------------------------------------------------------------------ sessões

    def ensure_session(self, session_id: str, channel: str, now: datetime) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO sessions VALUES (?, ?, ?, ?)",
                (session_id, channel, now.isoformat(), now.isoformat()),
            )

    def exists(self, session_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM sessions WHERE session_id = ?", (session_id,))
            return row.fetchone() is not None

    def list_sessions(self, limit: int = 20) -> list[SessionInfo]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT s.*, (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.session_id "
                "AND m.role = 'user' AND m.internal = 0) AS n "
                "FROM sessions s ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            SessionInfo(r["session_id"], r["channel"], r["created_at"], r["updated_at"], r["n"])
            for r in rows
        ]

    def delete_session(self, session_id: str) -> bool:
        """Exclusão a pedido do cliente: conversa e encaminhamentos da sessão."""
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            return cursor.rowcount > 0

    def purge(self, older_than_days: int, now: datetime) -> int:
        """Apaga conversas sem atividade há mais de N dias. Devolve quantas apagou."""
        cutoff = (now - timedelta(days=older_than_days)).isoformat()
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM sessions WHERE updated_at < ?", (cutoff,))
            return cursor.rowcount

    # ------------------------------------------------------------------ mensagens

    def append(self, session_id: str, messages: list[Message], now: datetime) -> None:
        if not messages:
            return
        with self._connect() as conn:
            start = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM messages WHERE session_id = ?", (session_id,)
            ).fetchone()[0]
            conn.executemany(
                "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        session_id,
                        start + offset,
                        m.role,
                        m.content,
                        _calls_to_json(m.tool_calls),
                        m.tool_name,
                        m.tool_call_id,
                        int(m.internal),
                        now.isoformat(),
                    )
                    for offset, m in enumerate(messages, start=1)
                ],
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (now.isoformat(), session_id),
            )

    def load(self, session_id: str) -> list[Message]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY seq", (session_id,)
            ).fetchall()
        return [
            Message(
                role=r["role"],
                content=r["content"],
                tool_calls=_calls_from_json(r["tool_calls"]),
                tool_name=r["tool_name"],
                tool_call_id=r["tool_call_id"],
                internal=bool(r["internal"]),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------ encaminhamentos

    def register(
        self, session_id: str, reason: str, summary: str, order_id: int | None, now: datetime
    ) -> Handoff:
        """Mesmo contrato de InMemoryHandoffs: a ferramenta não sabe onde o protocolo fica."""
        self.ensure_session(session_id, "desconhecido", now)
        with self._connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM handoffs WHERE substr(created_at, 1, 10) = ?",
                (now.date().isoformat(),),
            ).fetchone()[0]
            handoff = Handoff(
                protocol=f"EM{now:%Y%m%d}-{count + 1:04d}",
                session_id=session_id,
                reason=reason,
                summary=summary,
                order_id=order_id,
                created_at=now,
            )
            conn.execute(
                "INSERT INTO handoffs (protocol, session_id, reason, summary, order_id, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (handoff.protocol, session_id, reason, summary, order_id, now.isoformat()),
            )
        return handoff

    def list_handoffs(self, status: str | None = "aberto") -> list[dict]:
        with self._connect() as conn:
            query = "SELECT * FROM handoffs"
            params: tuple = ()
            if status:
                query += " WHERE status = ?"
                params = (status,)
            rows = conn.execute(query + " ORDER BY created_at", params).fetchall()
        return [dict(r) for r in rows]
