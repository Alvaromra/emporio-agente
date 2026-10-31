"""Ferramentas de pedidos, sempre com verificação de identidade.

Regras de segurança (LGPD):
- Um pedido só é exibido para quem informa o número do pedido e o e-mail ou o
  telefone do cliente dono daquele pedido.
- A mensagem de falha é a mesma para "pedido inexistente" e "contato não confere",
  para não revelar quais números de pedido existem.
- Se o e-mail do cliente é compartilhado com outro cadastro, só o telefone é aceito.
- Após 3 falhas na sessão, consultas a pedidos ficam bloqueadas.
- A resposta traz apenas o primeiro nome do cliente.
"""

from __future__ import annotations

import hmac
import sqlite3
from datetime import date

from emporio.money import format_brl
from emporio.privacy import fingerprint
from emporio.rules.orders import STATUS_LABELS, delay_message, payment_label
from emporio.rules.returns import Reason, assess_return
from emporio.tools.base import ToolContext, ToolError, tool

GENERIC_FAILURE = (
    "Não foi possível confirmar os dados. Confira o número do pedido e o e-mail ou telefone "
    "usado na compra."
)
BLOCKED = (
    "Limite de tentativas de verificação atingido nesta conversa. Por segurança, a consulta "
    "de pedidos deve ser feita com um atendente."
)

# Achados do ETL que mudam a forma de responder sobre um pedido.
ISSUE_GUIDANCE = {
    "order.total_mismatch": "Informe o total registrado; não recalcule a partir dos itens.",
    "order.item_not_released": "O pedido contém produto ainda não lançado ou fora de linha: "
    "não prometa prazo e ofereça encaminhar para a equipe.",
    "order.local_with_carrier_tracking": "Informe o código de rastreio sem afirmar qual "
    "transportadora fez a entrega.",
    "order.installment_below_minimum": "Não comente as condições de pagamento deste pedido "
    "além do que está registrado.",
    "order.pix_discount_missing": "Não comente se houve desconto no pagamento deste pedido.",
}

CONTACT_PARAM = {
    "type": "string",
    "description": "E-mail ou telefone usado na compra, exatamente como o cliente informou. "
    "Pode ser omitido se este pedido já foi verificado nesta conversa.",
}
ORDER_PARAM = {"type": "integer", "description": "Número do pedido."}


def _fmt_date(value: str | None) -> str | None:
    return date.fromisoformat(value).strftime("%d/%m/%Y") if value else None


def _shared_email(conn: sqlite3.Connection, customer_id: int) -> bool:
    rows = conn.execute(
        "SELECT entity_id FROM data_quality_issues WHERE check_code = 'customer.shared_email'"
    ).fetchall()
    return any(str(customer_id) in row[0].split(",") for row in rows)


def _verify(ctx: ToolContext, conn: sqlite3.Connection, order_id: int, contact: str | None):
    """Devolve a linha do pedido (com dados do cliente) se a identidade for confirmada."""
    session = ctx.session_id
    if ctx.guard.is_blocked(session):
        raise ToolError(BLOCKED)

    order = conn.execute(
        "SELECT o.*, c.first_name, c.city, c.email_fp, c.phone_fp "
        "FROM orders o JOIN customers c USING (customer_id) WHERE o.order_id = ?",
        (order_id,),
    ).fetchone()

    if order is not None and ctx.guard.is_verified(session, order_id):
        return order
    if not contact:
        raise ToolError("Para consultar o pedido, peça o e-mail ou o telefone usado na compra.")

    is_email = "@" in contact
    if order is not None and is_email and _shared_email(conn, order["customer_id"]):
        raise ToolError(
            "Para este pedido, a confirmação precisa ser feita pelo telefone cadastrado. "
            "Peça o telefone ao cliente (sem explicar o motivo interno)."
        )

    ok = False
    if order is not None:
        kind = "email" if is_email else "phone"
        expected = order["email_fp"] if is_email else order["phone_fp"]
        ok = hmac.compare_digest(fingerprint(kind, contact, ctx.pepper), expected)
    if not ok:
        remaining = ctx.guard.register_failure(session)
        message = GENERIC_FAILURE
        if remaining <= 0:
            message += " " + BLOCKED
        raise ToolError(message)

    ctx.guard.register_success(session, order_id)
    return order


def _issue_codes(conn: sqlite3.Connection, order_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT check_code FROM data_quality_issues "
        "WHERE entity = 'orders' AND entity_id = ? ORDER BY check_code",
        (str(order_id),),
    ).fetchall()
    return [row[0] for row in rows]


@tool(
    "consultar_pedido",
    """Consulta o status de um pedido do cliente: situação, itens, total, forma de
    pagamento, rastreamento e previsão de entrega. Exige o número do pedido e o
    e-mail ou telefone da compra. Se o cliente não informou, peça antes de chamar.""",
    {"numero_pedido": ORDER_PARAM, "email_ou_telefone": CONTACT_PARAM},
    required=("numero_pedido",),
)
def consultar_pedido(
    ctx: ToolContext, numero_pedido: int, email_ou_telefone: str | None = None
) -> dict:
    today = ctx.now.date()
    with ctx.connect() as conn:
        order = _verify(ctx, conn, numero_pedido, email_ou_telefone)
        items = conn.execute(
            "SELECT p.name, i.quantity FROM order_items i JOIN products p USING (product_id) "
            "WHERE i.order_id = ? ORDER BY p.name",
            (numero_pedido,),
        ).fetchall()
        codes = _issue_codes(conn, numero_pedido)

    result: dict = {
        "verificado": True,
        "pedido": order["order_id"],
        "cliente": order["first_name"],
        "status": STATUS_LABELS[order["status"]],
        "data_do_pedido": _fmt_date(order["order_date"]),
        "itens": [{"produto": r["name"], "quantidade": r["quantity"]} for r in items],
        "total": format_brl(order["total_cents"]),
        "pagamento": payment_label(order["payment_type"], order["installments"]),
    }
    show_tracking = (
        order["status"] in ("shipped", "delivered")
        and order["tracking_code"]
        and "order.tracking_invalid" not in codes
    )
    if show_tracking:
        result["rastreamento"] = {
            "codigo": order["tracking_code"],
            "onde_consultar": "site dos Correios ou da Jadlog",
        }
    if order["estimated_delivery"] and order["status"] != "cancelled":
        result["previsao_de_entrega"] = _fmt_date(order["estimated_delivery"])
    if order["notes"]:
        result["nota_do_pedido"] = order["notes"]

    guidance = [ISSUE_GUIDANCE[c] for c in codes if c in ISSUE_GUIDANCE]
    delay = delay_message(dict(order), today)
    if delay:
        result["alerta"] = f"{delay[0].upper()}{delay[1:]}."
        guidance.append(
            "Reconheça o atraso com empatia, não invente motivo nem novo prazo, e ofereça "
            "encaminhar para a equipe (retorno em até 24 horas úteis)."
        )
    if guidance:
        result["orientacoes_ao_agente"] = guidance
    return result


@tool(
    "avaliar_troca_devolucao",
    """Verifica se um pedido pode ser devolvido ou trocado e calcula os prazos, de
    acordo com a política da loja. Use quando o cliente quiser devolver, trocar ou
    acionar garantia de um pedido. Motivos: 'arrependimento' (desistiu da compra),
    'defeito' (problema de fabricação) ou 'preferencia' (trocar cor, modelo ou
    tamanho). Exige número do pedido e e-mail ou telefone da compra.""",
    {
        "numero_pedido": ORDER_PARAM,
        "motivo": {
            "type": "string",
            "enum": [r.value for r in Reason],
            "description": "Motivo da troca ou devolução.",
        },
        "email_ou_telefone": CONTACT_PARAM,
    },
    required=("numero_pedido", "motivo"),
)
def avaliar_troca_devolucao(
    ctx: ToolContext, numero_pedido: int, motivo: str, email_ou_telefone: str | None = None
) -> dict:
    with ctx.connect() as conn:
        order = _verify(ctx, conn, numero_pedido, email_ou_telefone)
    assessment = assess_return(dict(order), Reason(motivo), today=ctx.now.date())
    result = {
        "pedido": numero_pedido,
        "cliente": order["first_name"],
        "motivo": assessment.reason.value,
        "elegivel": assessment.eligible,
        "resumo": assessment.summary,
        "prazo_final": _fmt_date(assessment.deadline.isoformat()) if assessment.deadline else None,
        "dias_restantes": assessment.days_left,
        "condicoes": assessment.conditions,
        "proximos_passos": assessment.next_steps,
        "secoes_do_manual": assessment.policy_sections,
    }
    if assessment.reason is Reason.ARREPENDIMENTO:
        result["orientacao"] = (
            "Prazo contado a partir da previsão de entrega registrada, pois o sistema não "
            "guarda a data real de recebimento. Se o cliente recebeu depois, a equipe confirma."
        )
    return result
