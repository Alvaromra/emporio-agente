"""Valores monetários em centavos inteiros e formatação em reais."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def format_brl(cents: int) -> str:
    """59990 -> 'R$ 599,90'; 1234567 -> 'R$ 12.345,67'."""
    sign = "-" if cents < 0 else ""
    reais, centavos = divmod(abs(cents), 100)
    return f"{sign}R$ {reais:,}".replace(",", ".") + f",{centavos:02d}"


def apply_discount(cents: int, percent: int | Decimal) -> int:
    """Aplica um desconto percentual, arredondando ao centavo (meio para cima)."""
    factor = (Decimal(100) - Decimal(percent)) / Decimal(100)
    return int((Decimal(cents) * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
