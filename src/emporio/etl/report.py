"""Relatório de qualidade em Markdown e alertas operacionais.

O relatório é determinístico (mesma entrada e mesma data de referência geram o
mesmo arquivo), para que as diferenças no git reflitam mudanças reais nos dados.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from emporio.etl.checks import Issue
from emporio.etl.transform import CleanData

OPEN_ORDER_STATUSES = ("pending", "confirmed", "shipped")
STALE_AFTER_DAYS = 30


@dataclass(frozen=True)
class Alert:
    order_id: int
    status: str
    order_date: str
    estimated_delivery: str | None
    situation: str


def operational_alerts(orders: list[dict], reference: date) -> list[Alert]:
    """Pedidos em aberto com previsão vencida ou parados há mais de 30 dias."""
    alerts: list[Alert] = []
    for order in sorted(orders, key=lambda o: o["order_id"]):
        if order["status"] not in OPEN_ORDER_STATUSES:
            continue
        estimated = order["estimated_delivery"]
        age = (reference - date.fromisoformat(order["order_date"])).days
        if estimated and date.fromisoformat(estimated) < reference:
            late = (reference - date.fromisoformat(estimated)).days
            situation = f"previsão de entrega vencida há {late} dias"
        elif age > STALE_AFTER_DAYS:
            situation = f"em aberto há {age} dias"
        else:
            continue
        alerts.append(
            Alert(order["order_id"], order["status"], order["order_date"], estimated, situation)
        )
    return alerts


def _id_key(value: str):
    return [int(part) if part.isdigit() else part for part in value.split(",")]


def render_report(
    data: CleanData, alerts: list[Alert], reference: date, sources: dict[str, str]
) -> str:
    sellable = [p for p in data.products if p["status"] == "active" and p["stock_quantity"] > 0]
    active_promos = [p for p in data.promotions if p["is_active"]]
    unreliable = [p for p in data.products if not p["description_reliable"]]

    grouped: dict[str, list[Issue]] = defaultdict(list)
    for item in data.issues:
        grouped[item.check.code].append(item)
    ordered_codes = sorted(grouped, key=lambda c: (grouped[c][0].check.severity.rank, c))

    lines = [
        "# Relatório de qualidade dos dados",
        "",
        "> Gerado automaticamente por `python -m emporio.etl`. Não edite à mão.",
        f"> Data de referência: {reference.isoformat()}",
        "",
        "## Resumo",
        "",
        "| Tabela | Registros carregados |",
        "|---|---|",
    ]
    for table in ("categories", "products", "promotions", "customers", "orders", "order_items"):
        lines.append(f"| `{table}` | {len(getattr(data, table))} |")
    lines += [
        "",
        f"- Produtos vendáveis (ativos e com estoque): **{len(sellable)}** "
        f"de {len(data.products)}.",
        f"- Promoções ativas: **{len(active_promos)}** de {len(data.promotions)}.",
        f"- Produtos com descrição não confiável: **{len(unreliable)}**.",
        f"- Achados de qualidade: **{len(data.issues)}** em {len(grouped)} tipos.",
        "",
        "## Achados e tratamento",
        "",
        "| Severidade | Achado | Ocorrências | Registros | Tratamento |",
        "|---|---|---|---|---|",
    ]
    for code in ordered_codes:
        items = grouped[code]
        check = items[0].check
        ids = sorted({i.entity_id for i in items}, key=_id_key)
        lines.append(
            f"| {check.severity.value} | {check.title} | {len(items)} | "
            f"{items[0].entity} {', '.join(ids)} | {check.treatment} |"
        )

    lines += ["", "## Detalhes", ""]
    for code in ordered_codes:
        items = sorted(grouped[code], key=lambda i: _id_key(i.entity_id))
        lines += [f"### {items[0].check.title}", "", f"Código: `{code}`", ""]
        lines += [f"- {i.entity} {i.entity_id}: {i.detail}" for i in items]
        lines.append("")

    lines += [
        "## Alertas operacionais",
        "",
        f"Pedidos em aberto com previsão vencida ou sem atualização há mais de "
        f"{STALE_AFTER_DAYS} dias, na data de referência. Dependem da data e, por isso, "
        "são recalculados a cada consulta do agente, não gravados no banco.",
        "",
    ]
    if alerts:
        lines += [
            "| Pedido | Status | Data do pedido | Previsão | Situação |",
            "|---|---|---|---|---|",
        ]
        lines += [
            f"| {a.order_id} | {a.status} | {a.order_date} | {a.estimated_delivery or '-'} | "
            f"{a.situation} |"
            for a in alerts
        ]
    else:
        lines.append("Nenhum alerta.")

    lines += ["", "## Integridade da origem", "", "| Arquivo | SHA-256 |", "|---|---|"]
    lines += [f"| `{name}` | `{digest}` |" for name, digest in sorted(sources.items())]
    lines.append("")
    return "\n".join(lines)
