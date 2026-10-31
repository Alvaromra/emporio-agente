"""Formas de pagamento e parcelamento (manual, seções 3, 3.1 e 6.2).

Interpretação adotada para o conflito entre a tabela da seção 3 ("parcela mínima de
R$ 100") e a seção 3.1 (faixas por número de parcelas): vale a 3.1, por ser mais
específica. A tabela descreve o caso extremo de 12x. Ver docs/suposicoes.md (M1).
"""

from __future__ import annotations

from dataclasses import dataclass

from emporio.money import apply_discount, format_brl

MAX_INSTALLMENTS = 12
PIX_DISCOUNT_PERCENT = 5
COMBINED_PAYMENT_ABOVE_CENTS = 200_000  # R$ 2.000,00 (estritamente acima)
BOLETO_CLEARING_BUSINESS_DAYS = 3

# (de, até, parcela mínima em centavos). A seção 3.1 diz que até 3x não há mínimo
# "exceto abaixo de R$ 50,00": interpretado como parcela mínima de R$ 50 em 2x e 3x.
# Em 1x (crédito à vista) não há mínimo.
INSTALLMENT_TIERS = (
    (1, 1, 0),
    (2, 3, 5_000),
    (4, 6, 8_000),
    (7, 12, 10_000),
)


def minimum_installment_cents(installments: int) -> int:
    for low, high, minimum in INSTALLMENT_TIERS:
        if low <= installments <= high:
            return minimum
    raise ValueError(f"Parcelamento inválido: {installments}x (permitido de 1x a 12x)")


def installment_plan(total_cents: int, installments: int) -> tuple[int, int]:
    """(primeira parcela, demais parcelas). O resto da divisão vai na primeira."""
    base, remainder = divmod(total_cents, installments)
    return base + remainder, base


def is_installment_allowed(total_cents: int, installments: int) -> bool:
    """Toda parcela (inclusive a menor) precisa respeitar o mínimo da faixa."""
    minimum = minimum_installment_cents(installments)
    _, smallest = installment_plan(total_cents, installments)
    return smallest >= minimum


def max_installments(total_cents: int) -> int:
    """Maior número de parcelas sem juros permitido para o valor.

    As faixas não são monotônicas (R$ 300 cabe em 3x, mas não em 4x), então
    cada quantidade é testada individualmente.
    """
    return max(n for n in range(1, MAX_INSTALLMENTS + 1) if is_installment_allowed(total_cents, n))


def pix_price(table_price_cents: int, is_promotional: bool) -> int | None:
    """Preço no PIX, ou None se o desconto não se aplica (preço já promocional, manual 6.2)."""
    if is_promotional:
        return None
    return apply_discount(table_price_cents, PIX_DISCOUNT_PERCENT)


def combined_payment_allowed(total_cents: int) -> bool:
    """Combinar formas de pagamento (ex.: PIX + cartão) só acima de R$ 2.000,00."""
    return total_cents > COMBINED_PAYMENT_ABOVE_CENTS


@dataclass(frozen=True)
class PaymentOptions:
    price_cents: int
    is_promotional: bool
    pix_cents: int | None
    max_installments: int
    installment_cents: int  # valor das parcelas no parcelamento máximo
    combined_payment_allowed: bool

    def as_text(self) -> list[str]:
        lines = []
        if self.pix_cents is not None:
            lines.append(f"PIX à vista: {format_brl(self.pix_cents)} (5% de desconto)")
        else:
            lines.append(
                f"PIX à vista: {format_brl(self.price_cents)} "
                "(o desconto de 5% não se aplica a preços promocionais)"
            )
        lines.append(f"Débito à vista: {format_brl(self.price_cents)}")
        lines.append(
            f"Boleto à vista: {format_brl(self.price_cents)} "
            f"(compensação em até {BOLETO_CLEARING_BUSINESS_DAYS} dias úteis)"
        )
        if self.max_installments > 1:
            lines.append(
                f"Cartão de crédito: até {self.max_installments}x sem juros de "
                f"aproximadamente {format_brl(self.installment_cents)}"
            )
        else:
            lines.append("Cartão de crédito: à vista (valor abaixo do mínimo para parcelar)")
        if self.combined_payment_allowed:
            lines.append("É possível combinar formas de pagamento (ex.: PIX + cartão).")
        return lines


def payment_options(price_cents: int, is_promotional: bool) -> PaymentOptions:
    n = max_installments(price_cents)
    _, installment = installment_plan(price_cents, n)
    return PaymentOptions(
        price_cents=price_cents,
        is_promotional=is_promotional,
        pix_cents=pix_price(price_cents, is_promotional),
        max_installments=n,
        installment_cents=installment,
        combined_payment_allowed=combined_payment_allowed(price_cents),
    )
