"""Tipos neutros de conversa, independentes de provedor."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from emporio.tools import Tool


class LLMError(RuntimeError):
    """Falha ao falar com o modelo, com mensagem pronta para o usuário do sistema."""


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict
    id: str | None = None


@dataclass
class Message:
    role: Literal["user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_name: str | None = None  # role="tool": qual ferramenta respondeu
    tool_call_id: str | None = None  # role="tool": a qual chamada responde
    raw: Any = None  # mensagem nativa do provedor (preserva metadados como thought signatures)

    @classmethod
    def tool_result(cls, call: ToolCall, result: dict) -> Message:
        return cls(
            role="tool",
            content=json.dumps(result, ensure_ascii=False),
            tool_name=call.name,
            tool_call_id=call.id,
        )


@dataclass
class AssistantTurn:
    """Resposta do modelo: texto final e/ou pedidos de ferramenta."""

    text: str
    tool_calls: list[ToolCall]
    message: Message  # para anexar ao histórico
    usage: dict[str, int] = field(default_factory=dict)


class LLMProvider(Protocol):
    name: str
    model: str

    def complete(self, system: str, messages: list[Message], tools: list[Tool]) -> AssistantTurn:
        """Uma chamada ao modelo. Não executa ferramentas: isso é papel do agente."""
        ...


def parse_json_object(value: Any) -> dict:
    """Argumentos de ferramenta podem chegar como dict ou como texto JSON."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}
