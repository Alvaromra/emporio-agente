"""Situação de pedidos: rótulos em português e detecção de atraso."""

from __future__ import annotations

from datetime import date

OPEN_STATUSES = ("pending", "confirmed", "shipped")
STALE_AFTER_DAYS = 30

STATUS_LABELS = {
    "pending": "aguardando processamento",
    "confirmed": "confirmado, em preparação para envio",
    "shipped": "enviado",
    "delivered": "entregue",
    "cancelled": "cancelado",
}
PAYMENT_LABELS = {
    "pix": "PIX",
    "debit": "cartão de débito",
    "boleto": "boleto bancário",
    "credit": "cartão de crédito",
}


def payment_label(payment_type: str, installments: int) -> str:
    label = PAYMENT_LABELS[payment_type]
    if payment_type == "credit":
        label += " à vista" if installments == 1 else f" em {installments}x"
    return label


def delay_message(order: dict, today: date) -> str | None:
    """Mensagem de atraso para pedidos em aberto, ou None se estiver em dia."""
    if order["status"] not in OPEN_STATUSES:
        return None
    estimated = order.get("estimated_delivery")
    if estimated and date.fromisoformat(estimated) < today:
        days = (today - date.fromisoformat(estimated)).days
        return f"previsão de entrega vencida há {days} dias"
    age = (today - date.fromisoformat(order["order_date"])).days
    if age > STALE_AFTER_DAYS:
        return f"em aberto há {age} dias"
    return None
