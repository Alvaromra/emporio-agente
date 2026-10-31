"""Calendário da loja: feriados e dias úteis em Campo Grande/MS.

O manual diz apenas "Domingo e Feriados: Fechado", sem listar os feriados.
A lista abaixo é uma suposição documentada (docs/suposicoes.md, M5).
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

# Feriados nacionais fixos (Lei 662/1949, Lei 6.802/1980 e Lei 14.759/2023).
NATIONAL_FIXED = {
    (1, 1): "Confraternização Universal",
    (4, 21): "Tiradentes",
    (5, 1): "Dia do Trabalho",
    (9, 7): "Independência do Brasil",
    (10, 12): "Nossa Senhora Aparecida",
    (11, 2): "Finados",
    (11, 15): "Proclamação da República",
    (11, 20): "Dia Nacional de Zumbi e da Consciência Negra",
    (12, 25): "Natal",
}
STATE_FIXED = {(10, 11): "Criação do Estado de Mato Grosso do Sul"}
# Municipais de Campo Grande: a confirmar com a loja.
MUNICIPAL_FIXED = {
    (6, 13): "Santo Antônio, padroeiro de Campo Grande",
    (8, 26): "Aniversário de Campo Grande",
}


def easter(year: int) -> date:
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher, calendário gregoriano)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month, day = divmod(h + l_ - 7 * m + 114, 31)
    return date(year, month, day + 1)


@lru_cache(maxsize=32)
def holidays(year: int) -> dict[date, str]:
    result = {
        date(year, month, day): name
        for table in (NATIONAL_FIXED, STATE_FIXED, MUNICIPAL_FIXED)
        for (month, day), name in table.items()
    }
    result[easter(year) - timedelta(days=2)] = "Sexta-feira Santa"
    return result


def holiday_name(day: date) -> str | None:
    return holidays(day.year).get(day)


def is_business_day(day: date) -> bool:
    """Segunda a sexta, exceto feriados (o sábado não conta como dia útil)."""
    return day.weekday() < 5 and holiday_name(day) is None


def add_business_days(start: date, days: int) -> date:
    """Data após `days` dias úteis, sem contar o próprio dia de início."""
    current, remaining = start, days
    while remaining > 0:
        current += timedelta(days=1)
        if is_business_day(current):
            remaining -= 1
    return current
