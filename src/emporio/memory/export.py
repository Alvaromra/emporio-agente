"""Exporta uma conversa em Markdown (usado nos exemplos de interação do repositório)."""

from __future__ import annotations

import json

from emporio.agent.prompt import AGENT_NAME
from emporio.llm import Message


def to_markdown(messages: list[Message], title: str, show_tools: bool = True) -> str:
    lines = [f"# {title}", ""]
    for m in messages:
        if m.internal:
            continue
        if m.role == "user":
            lines += [f"**Cliente:** {m.content}", ""]
        elif m.role == "assistant":
            if show_tools:
                for call in m.tool_calls:
                    args = json.dumps(call.arguments, ensure_ascii=False)
                    lines += [f"> 🔧 `{call.name}({args})`", ""]
            if m.content:
                lines += [f"**{AGENT_NAME}:** {m.content}", ""]
    return "\n".join(lines).rstrip() + "\n"
