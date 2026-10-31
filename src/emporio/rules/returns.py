"""Trocas, devoluções e garantia (manual, seções 4 e 8).

Funções puras: recebem o pedido e a data de hoje, e devolvem uma avaliação com
prazos já calculados. O LLM apenas comunica o resultado; ele nunca conta dias.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum


class Reason(StrEnum):
    ARREPENDIMENTO = "arrependimento"
    DEFEITO = "defeito"
    PREFERENCIA = "preferencia"


WITHDRAWAL_DAYS = 7  # 4.1, dias corridos após o recebimento
DEFECT_EXCHANGE_DAYS = 30  # 4.2, dias corridos após a compra
PREFERENCE_DAYS = 7  # 4.3 (marco inicial: recebimento, ver suposição M7)
LEGAL_WARRANTY_DAYS = 90  # 8.1, a partir do recebimento
REFUND_BUSINESS_DAYS = 10

NOT_ELIGIBLE_ITEMS = (
    "instrumentos com personalização ou ajuste sob encomenda (setup, regulagem especial)",
    "produtos de liquidação com aviso explícito de 'venda final'",
    "boquilhas de instrumentos de sopro, por higiene",
)
WARRANTY_EXCLUSIONS = (
    "desgaste natural (trastes, cordas, feltros, palhetas de sopro)",
    "mau uso, queda ou exposição a condições climáticas extremas",
    "modificações ou reparos feitos por terceiros não autorizados",
    "danos estéticos que não afetam o funcionamento",
)


@dataclass(frozen=True)
class ReturnAssessment:
    reason: Reason
    eligible: bool
    summary: str
    deadline: date | None = None
    days_left: int | None = None
    conditions: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    policy_sections: list[str] = field(default_factory=list)


def received_on(order: dict) -> date | None:
    """Data de recebimento. Sem data real de entrega nos dados, usa-se a previsão (M6)."""
    if order["status"] != "delivered" or not order.get("estimated_delivery"):
        return None
    return date.fromisoformat(order["estimated_delivery"])


def _not_applicable(reason: Reason, order: dict) -> ReturnAssessment | None:
    status = order["status"]
    if status == "delivered":
        return None
    messages = {
        "cancelled": "O pedido foi cancelado, então não há produto para trocar ou devolver.",
        "shipped": "O pedido ainda está em transporte. A troca ou devolução vale a partir "
        "do recebimento.",
        "pending": "O pedido ainda não foi processado. Nesse caso, o caminho é solicitar o "
        "cancelamento com a equipe.",
        "confirmed": "O pedido ainda não foi enviado. Nesse caso, o caminho é solicitar o "
        "cancelamento com a equipe.",
    }
    return ReturnAssessment(
        reason, False, messages[status], next_steps=["Encaminhar para a equipe de atendimento."]
    )


def assess_return(order: dict, reason: Reason, today: date) -> ReturnAssessment:
    """Avalia um pedido para arrependimento, troca por defeito ou troca por preferência.

    `order` precisa de: status, order_date e estimated_delivery (AAAA-MM-DD).
    """
    reason = Reason(reason)
    blocked = _not_applicable(reason, order)
    if blocked:
        return blocked

    received = received_on(order)
    purchased = date.fromisoformat(order["order_date"])
    item_rules = [f"Não são elegíveis: {'; '.join(NOT_ELIGIBLE_ITEMS)}."]

    if reason is Reason.ARREPENDIMENTO:
        deadline = received + timedelta(days=WITHDRAWAL_DAYS)
        ok = today <= deadline
        return ReturnAssessment(
            reason,
            ok,
            (
                f"Dentro do prazo de arrependimento de {WITHDRAWAL_DAYS} dias corridos após "
                "o recebimento."
                if ok
                else f"O prazo de arrependimento ({WITHDRAWAL_DAYS} dias corridos após o "
                "recebimento) já terminou."
            ),
            deadline,
            (deadline - today).days if ok else None,
            conditions=[
                "Embalagem original, sem sinais de uso, com todos os acessórios e manuais.",
                *item_rules,
            ]
            if ok
            else [],
            next_steps=[
                f"Reembolso na mesma forma de pagamento em até {REFUND_BUSINESS_DAYS} dias úteis.",
                "O frete de devolução é por conta da loja.",
            ]
            if ok
            else [
                "Se houver defeito de fabricação, avaliar troca por defeito ou garantia.",
            ],
            policy_sections=["4.1", "4.4"],
        )

    if reason is Reason.PREFERENCIA:
        deadline = received + timedelta(days=PREFERENCE_DAYS)
        ok = today <= deadline
        return ReturnAssessment(
            reason,
            ok,
            (
                "Dentro do prazo de troca por preferência (cor, modelo ou tamanho)."
                if ok
                else f"O prazo de troca por preferência ({PREFERENCE_DAYS} dias) já terminou."
            ),
            deadline,
            (deadline - today).days if ok else None,
            conditions=[
                "Produto em perfeito estado e na embalagem original.",
                "Sujeito à disponibilidade do produto desejado.",
                "Diferenças de valor são cobradas ou reembolsadas.",
                *item_rules,
            ]
            if ok
            else [],
            policy_sections=["4.3", "4.4"],
        )

    # Defeito: troca na loja até 30 dias da compra; depois, garantia.
    exchange_deadline = purchased + timedelta(days=DEFECT_EXCHANGE_DAYS)
    legal_deadline = received + timedelta(days=LEGAL_WARRANTY_DAYS)
    exclusions = f"A garantia não cobre: {'; '.join(WARRANTY_EXCLUSIONS)}."
    if today <= exchange_deadline:
        return ReturnAssessment(
            reason,
            True,
            "Dentro do prazo de troca por defeito de fabricação "
            f"({DEFECT_EXCHANGE_DAYS} dias corridos após a compra).",
            exchange_deadline,
            (exchange_deadline - today).days,
            conditions=[exclusions],
            next_steps=["A equipe avalia o produto e faz a troca."],
            policy_sections=["4.2", "8.3"],
        )
    within_legal = today <= legal_deadline
    return ReturnAssessment(
        reason,
        False,
        "O prazo de troca direta na loja (30 dias após a compra) já terminou. "
        + (
            "O produto ainda está na garantia legal de 90 dias."
            if within_legal
            else "A garantia legal de 90 dias também terminou; resta a garantia do "
            "fabricante, que varia de 6 meses a 2 anos conforme o certificado do produto."
        ),
        legal_deadline if within_legal else None,
        (legal_deadline - today).days if within_legal else None,
        conditions=[exclusions],
        next_steps=[
            "Acionar a garantia diretamente com o fabricante. A Empório da Música pode "
            "intermediar o processo, se o cliente pedir.",
        ],
        policy_sections=["4.2", "8.1", "8.2", "8.3"],
    )
