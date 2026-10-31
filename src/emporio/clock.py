"""Relógio da loja.

Toda regra que depende de data (loja aberta agora, pedido atrasado, prazo de
devolução) consulta este módulo, nunca datetime.now() diretamente. Assim o
fuso de Campo Grande é respeitado e os testes podem congelar o tempo com
EMPORIO_NOW.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from emporio.config import get_settings


def store_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def now() -> datetime:
    """Data e hora atuais no fuso da loja (ou o valor congelado em EMPORIO_NOW)."""
    tz = store_tz()
    override = get_settings().now_override
    if override:
        frozen = datetime.fromisoformat(override)
        return frozen.replace(tzinfo=tz) if frozen.tzinfo is None else frozen.astimezone(tz)
    return datetime.now(tz)


def today() -> date:
    return now().date()
