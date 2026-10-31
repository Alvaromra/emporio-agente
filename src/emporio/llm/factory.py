"""Escolha do provedor a partir da configuração."""

from __future__ import annotations

from emporio.config import Settings, get_settings
from emporio.llm.base import LLMError, LLMProvider


def get_provider(settings: Settings | None = None) -> LLMProvider:
    settings = settings or get_settings()
    if settings.llm_provider == "gemini":
        from emporio.llm.gemini import DEFAULT_MODEL, GeminiProvider

        return GeminiProvider(
            model=settings.llm_model or DEFAULT_MODEL,
            api_key=settings.gemini_api_key,
            temperature=settings.llm_temperature,
        )
    if settings.llm_provider == "ollama":
        from emporio.llm.ollama_backend import DEFAULT_MODEL, OllamaProvider

        return OllamaProvider(
            model=settings.llm_model or DEFAULT_MODEL,
            host=settings.ollama_host,
            temperature=settings.llm_temperature,
            think=settings.ollama_think,
        )
    raise LLMError(
        f"Provedor desconhecido: '{settings.llm_provider}'. Use 'gemini' ou 'ollama' em "
        "EMPORIO_LLM_PROVIDER."
    )
