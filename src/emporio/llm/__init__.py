"""Provedores de LLM atrás de uma interface única.

O agente (etapa 07) conversa só com `LLMProvider`. Trocar Gemini API por Ollama
é uma variável de ambiente, sem mudar uma linha do agente.
"""

from emporio.llm.base import AssistantTurn, LLMError, LLMProvider, Message, ToolCall
from emporio.llm.factory import get_provider

__all__ = ["AssistantTurn", "LLMError", "LLMProvider", "Message", "ToolCall", "get_provider"]
