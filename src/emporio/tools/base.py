"""Infraestrutura das ferramentas: registro, contexto, validação e execução.

As ferramentas são funções Python comuns, descritas por um JSON Schema neutro. A
etapa 06 converte esse schema para o formato de cada provedor (Gemini API, Ollama),
então nada aqui depende de um LLM específico.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from emporio import clock
from emporio.config import get_settings

logger = logging.getLogger(__name__)

MAX_VERIFICATION_FAILURES = 3


class ToolError(Exception):
    """Erro previsto, com mensagem segura para devolver ao modelo."""


@dataclass
class VerificationGuard:
    """Limita tentativas de verificação de identidade por sessão.

    Sem esse limite, alguém poderia testar números de pedido e e-mails em sequência
    até acertar. Depois de 3 falhas, a sessão só consulta pedidos via atendente.
    Também lembra quais pedidos já foram verificados, para o cliente não precisar
    repetir o contato a cada pergunta sobre o mesmo pedido.
    """

    max_failures: int = MAX_VERIFICATION_FAILURES
    failures: dict[str, int] = field(default_factory=dict)
    verified: set[tuple[str, int]] = field(default_factory=set)

    def is_blocked(self, session_id: str) -> bool:
        return self.failures.get(session_id, 0) >= self.max_failures

    def register_failure(self, session_id: str) -> int:
        self.failures[session_id] = self.failures.get(session_id, 0) + 1
        return self.max_failures - self.failures[session_id]

    def register_success(self, session_id: str, order_id: int) -> None:
        self.verified.add((session_id, order_id))

    def is_verified(self, session_id: str, order_id: int) -> bool:
        return (session_id, order_id) in self.verified


@dataclass(frozen=True)
class Handoff:
    protocol: str
    session_id: str
    reason: str
    summary: str
    order_id: int | None
    created_at: datetime


class InMemoryHandoffs:
    """Registro de encaminhamentos em memória. A etapa 08 troca por SQLite."""

    def __init__(self) -> None:
        self.items: list[Handoff] = []

    def register(
        self, session_id: str, reason: str, summary: str, order_id: int | None, now: datetime
    ) -> Handoff:
        sequence = sum(1 for h in self.items if h.created_at.date() == now.date()) + 1
        handoff = Handoff(
            protocol=f"EM{now:%Y%m%d}-{sequence:04d}",
            session_id=session_id,
            reason=reason,
            summary=summary,
            order_id=order_id,
            created_at=now,
        )
        self.items.append(handoff)
        return handoff


@dataclass
class ToolContext:
    db_path: Path
    now: datetime
    pepper: str
    session_id: str = "local"
    guard: VerificationGuard = field(default_factory=VerificationGuard)
    handoffs: InMemoryHandoffs = field(default_factory=InMemoryHandoffs)

    @classmethod
    def from_settings(
        cls,
        session_id: str = "local",
        guard: VerificationGuard | None = None,
        handoffs: InMemoryHandoffs | None = None,
    ) -> ToolContext:
        settings = get_settings()
        return cls(
            db_path=settings.db_path,
            now=clock.now(),
            pepper=settings.pii_pepper,
            session_id=session_id,
            guard=guard or VerificationGuard(),
            handoffs=handoffs or InMemoryHandoffs(),
        )

    def connect(self) -> sqlite3.Connection:
        """Conexão somente leitura: nenhuma ferramenta consegue alterar os dados."""
        if not self.db_path.exists():
            raise ToolError("Banco de dados não encontrado. Rode `python -m emporio.etl`.")
        conn = sqlite3.connect(f"{self.db_path.resolve().as_uri()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn


Handler = Callable[..., dict]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict  # JSON Schema (type=object)
    handler: Handler


TOOLS: dict[str, Tool] = {}


def tool(name: str, description: str, properties: dict, required: tuple[str, ...] = ()):
    """Registra uma função como ferramenta disponível para o agente."""

    def register(handler: Handler) -> Handler:
        if name in TOOLS:
            raise ValueError(f"Ferramenta duplicada: {name}")
        schema = {"type": "object", "properties": properties, "required": list(required)}
        TOOLS[name] = Tool(name, " ".join(description.split()), schema, handler)
        return handler

    return register


def _coerce(name: str, value, spec: dict):
    """Modelos às vezes mandam "1000" em vez de 1000; normaliza sem ser permissivo demais."""
    expected = spec.get("type")
    try:
        if expected == "string":
            value = str(value).strip()
        elif expected == "integer":
            value = int(float(str(value).replace(",", ".")))
        elif expected == "number":
            value = float(str(value).replace(",", "."))
        elif expected == "boolean" and not isinstance(value, bool):
            value = str(value).strip().lower() in {"true", "1", "sim", "yes"}
    except ValueError:
        raise ToolError(f"Parâmetro '{name}' deveria ser do tipo {expected}.") from None
    if "enum" in spec and value not in spec["enum"]:
        raise ToolError(f"Parâmetro '{name}' deve ser um de {spec['enum']}.")
    return value


def execute(name: str, arguments: dict | None, ctx: ToolContext) -> dict:
    """Executa uma ferramenta e sempre devolve um dicionário serializável.

    Erros viram {"erro": "..."} em vez de exceções, para que o agente possa repassar
    a falha ao modelo e ele reaja (pedir outro dado, tentar outra ferramenta).
    """
    spec = TOOLS.get(name)
    if spec is None:
        return {"erro": f"Ferramenta desconhecida: {name}."}
    properties = spec.parameters["properties"]
    try:
        args = {
            key: _coerce(key, value, properties[key])
            for key, value in (arguments or {}).items()
            if key in properties and value not in (None, "")
        }
        missing = [key for key in spec.parameters["required"] if key not in args]
        if missing:
            raise ToolError(f"Parâmetros obrigatórios ausentes: {', '.join(missing)}.")
        return spec.handler(ctx, **args)
    except ToolError as error:
        return {"erro": str(error)}
    except Exception:
        logger.exception("Falha inesperada na ferramenta %s", name)
        return {"erro": "Falha interna ao consultar o sistema. Ofereça o atendimento humano."}
