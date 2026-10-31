"""Frete e entregas (manual, seção 5).

O valor do frete para outras cidades depende de CEP, peso e dimensões, que não estão
nos dados. O agente informa as modalidades e prazos, mas não inventa valores.
"""

from __future__ import annotations

from dataclasses import dataclass

from emporio.money import format_brl
from emporio.text import fold

FREE_SHIPPING_ABOVE_CENTS = 50_000  # R$ 500,00 (estritamente acima)
LOCAL_FLAT_FEE_CENTS = 3_500  # R$ 35,00
# A lista oficial da região metropolitana não foi fornecida (docs/suposicoes.md, M4).
LOCAL_CITIES = {"campo grande"}
CARRIERS = (
    ("PAC (Correios)", "5 a 12 dias úteis"),
    ("SEDEX (Correios)", "2 a 5 dias úteis"),
    ("Jadlog (.package)", "3 a 8 dias úteis"),
)
# Instrumentos de grande porte com frete especial (cotação individual).
LARGE_ITEM_KEYWORDS = ("bateria acustica", "piano digital", "contrabaixo acustico")


@dataclass(frozen=True)
class ShippingQuote:
    is_local: bool
    fee_cents: int | None  # None: calculado no fechamento do pedido
    lines: list[str]


def is_local(city: str) -> bool:
    return fold(city) in LOCAL_CITIES


def requires_special_freight(product_text: str) -> bool:
    folded = fold(product_text)
    return any(keyword in folded for keyword in LARGE_ITEM_KEYWORDS)


def shipping_quote(
    city: str, order_total_cents: int, product_texts: list[str] = ()
) -> ShippingQuote:
    special = [t for t in product_texts if requires_special_freight(t)]
    if is_local(city):
        free = order_total_cents > FREE_SHIPPING_ABOVE_CENTS
        fee = 0 if free else LOCAL_FLAT_FEE_CENTS
        lines = [
            "Frete grátis (pedido acima de R$ 500,00)."
            if free
            else f"Taxa fixa de {format_brl(fee)} (frete grátis só acima de R$ 500,00).",
            "Prazo de 1 a 3 dias úteis, por motoboy próprio. A loja liga antes de entregar.",
        ]
        return ShippingQuote(True, fee, lines)

    lines = [
        f"{name}: {deadline}, com rastreamento e seguro incluído" for name, deadline in CARRIERS
    ]
    lines.append("O valor é calculado pelo CEP de destino, peso e dimensões do produto.")
    if special:
        lines.append(
            "Instrumentos de grande porte podem exigir frete especial com cotação individual."
        )
    lines.append("Em caso de avaria, recuse o recebimento e avise a loja imediatamente.")
    return ShippingQuote(False, None, lines)
