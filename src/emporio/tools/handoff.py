"""Encaminhamento para a equipe humana (manual 7.3)."""

from __future__ import annotations

from emporio.rules.store import store_status
from emporio.tools.base import ToolContext, tool

REASONS = ("reclamacao", "atraso_pedido", "atendimento_humano", "outro")


@tool(
    "encaminhar_para_atendente",
    """Registra um encaminhamento para a equipe humana e devolve um número de
    protocolo. Use para reclamações, pedidos atrasados, quando o cliente pedir para
    falar com uma pessoa, ou quando nenhuma ferramenta resolve o caso. Antes de
    chamar, confirme com o cliente que ele quer o encaminhamento.""",
    {
        "motivo": {"type": "string", "enum": list(REASONS), "description": "Motivo."},
        "resumo": {
            "type": "string",
            "description": "Resumo objetivo do caso para a equipe, em uma ou duas frases, "
            "sem e-mail, telefone ou outros dados pessoais.",
        },
        "numero_pedido": {"type": "integer", "description": "Pedido relacionado, se houver."},
    },
    required=("motivo", "resumo"),
)
def encaminhar_para_atendente(
    ctx: ToolContext, motivo: str, resumo: str, numero_pedido: int | None = None
) -> dict:
    handoff = ctx.handoffs.register(ctx.session_id, motivo, resumo, numero_pedido, ctx.now)
    status = store_status(ctx.now)
    result = {
        "protocolo": handoff.protocol,
        "prazo_de_retorno": "até 24 horas úteis",
        "equipe": status.summary(),
        "orientacao": "Informe o protocolo e o prazo ao cliente. Se a loja estiver fechada, "
        "diga quando a equipe volta.",
    }
    return result
