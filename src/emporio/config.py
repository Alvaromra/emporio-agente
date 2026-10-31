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

load_dotenv(PROJECT_ROOT / ".env")


def _path(env_var: str, default: str) -> Path:
    raw = Path(os.getenv(env_var, default))
    return raw if raw.is_absolute() else PROJECT_ROOT / raw


@dataclass(frozen=True)
class Settings:
    raw_dir: Path
    db_path: Path
    timezone: str
    now_override: str | None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        raw_dir=_path("EMPORIO_RAW_DIR", "data/raw"),
        db_path=_path("EMPORIO_DB_PATH", "data/processed/store.db"),
        timezone=os.getenv("EMPORIO_TIMEZONE", "America/Campo_Grande"),
        now_override=os.getenv("EMPORIO_NOW") or None,
    )
