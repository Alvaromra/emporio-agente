"""Ferramentas institucionais: loja aberta agora, contato e frete."""

from __future__ import annotations

from emporio.money import format_brl
from emporio.rules.calendar import holiday_name
from emporio.rules.shipping import shipping_quote
from emporio.rules.store import SPECIAL_DATES_NOTE, STORE_INFO, store_status, weekly_hours_text
from emporio.tools.base import ToolContext, tool


@tool(
    "status_da_loja",
    """Informa se a loja está aberta agora (no horário de Campo Grande/MS), quando
    reabre, o horário de funcionamento, endereço e contatos. Use para perguntas
    sobre horário, endereço, telefone, e-mail ou "vocês estão abertos?".""",
    {},
)
def status_da_loja(ctx: ToolContext) -> dict:
    status = store_status(ctx.now)
    result = {
        "agora_em_campo_grande": status.now.strftime("%d/%m/%Y %H:%M"),
        "situacao": status.summary(),
        "horario_de_funcionamento": weekly_hours_text(),
        "datas_especiais": SPECIAL_DATES_NOTE,
        "endereco": STORE_INFO["endereco"],
        "telefone_whatsapp": STORE_INFO["telefone_whatsapp"],
        "email": STORE_INFO["email"],
    }
    holiday = holiday_name(status.now.date())
    if holiday:
        result["feriado_hoje"] = holiday
    return result


@tool(
    "consultar_frete",
    """Informa as condições de entrega para uma cidade: frete grátis ou taxa fixa em
    Campo Grande, ou modalidades e prazos (PAC, SEDEX, Jadlog) para outras cidades.
    Não calcula o valor exato do frete para fora de Campo Grande, que depende do CEP.""",
    {
        "cidade": {"type": "string", "description": "Cidade de entrega."},
        "valor_pedido": {
            "type": "number",
            "description": "Valor do pedido em reais, se conhecido (define o frete grátis).",
        },
        "produto": {
            "type": "string",
            "description": "Nome do produto, se conhecido (instrumentos grandes têm frete "
            "especial).",
        },
    },
    required=("cidade",),
)
def consultar_frete(
    ctx: ToolContext, cidade: str, valor_pedido: float | None = None, produto: str = ""
) -> dict:
    total = round(valor_pedido * 100) if valor_pedido is not None else 0
    quote = shipping_quote(cidade, total, [produto] if produto else [])
    result = {
        "cidade": cidade,
        "entrega_local": quote.is_local,
        "condicoes": quote.lines,
    }
    if quote.is_local and valor_pedido is None:
        result["orientacao"] = (
            "Valor do pedido não informado: explique que o frete é grátis acima de "
            f"R$ 500,00 e custa {format_brl(3500)} abaixo disso."
        )
    return result
