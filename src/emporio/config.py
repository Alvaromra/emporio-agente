"""Configuração central, lida de variáveis de ambiente (e de um .env opcional).

Caminhos relativos são resolvidos a partir da raiz do projeto, para que os
comandos funcionem independentemente do diretório de onde são executados.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Valor usado apenas em desenvolvimento. Em produção, defina EMPORIO_PII_PEPPER.
DEV_PII_PEPPER = "emporio-dev-pepper-nao-usar-em-producao"

load_dotenv(PROJECT_ROOT / ".env")


def _path(env_var: str, default: str) -> Path:
    raw = Path(os.getenv(env_var, default))
    return raw if raw.is_absolute() else PROJECT_ROOT / raw


def _optional_bool(value: str | None) -> bool | None:
    if value is None or not value.strip():
        return None
    return value.strip().lower() in {"1", "true", "sim", "yes"}


@dataclass(frozen=True)
class Settings:
    raw_dir: Path
    db_path: Path
    app_db_path: Path
    retention_days: int
    timezone: str
    now_override: str | None
    pii_pepper: str
    llm_provider: str
    llm_model: str | None
    llm_temperature: float
    gemini_api_key: str | None
    ollama_host: str
    ollama_think: bool | None

    @property
    def pii_pepper_is_default(self) -> bool:
        return self.pii_pepper == DEV_PII_PEPPER


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        raw_dir=_path("EMPORIO_RAW_DIR", "data/raw"),
        db_path=_path("EMPORIO_DB_PATH", "data/processed/store.db"),
        app_db_path=_path("EMPORIO_APP_DB_PATH", "data/runtime/app.db"),
        retention_days=int(os.getenv("EMPORIO_RETENTION_DAYS") or 90),
        timezone=os.getenv("EMPORIO_TIMEZONE", "America/Campo_Grande"),
        now_override=os.getenv("EMPORIO_NOW") or None,
        pii_pepper=os.getenv("EMPORIO_PII_PEPPER") or DEV_PII_PEPPER,
        llm_provider=(os.getenv("EMPORIO_LLM_PROVIDER") or "gemini").strip().lower(),
        llm_model=os.getenv("EMPORIO_LLM_MODEL") or None,
        llm_temperature=float(os.getenv("EMPORIO_LLM_TEMPERATURE") or 0.3),
        gemini_api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or None,
        ollama_host=os.getenv("OLLAMA_HOST") or "http://localhost:11434",
        ollama_think=_optional_bool(os.getenv("EMPORIO_OLLAMA_THINK")),
    )
