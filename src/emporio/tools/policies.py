"""Ferramenta de consulta ao manual de políticas (RAG)."""

from __future__ import annotations

from emporio.rag.store import load_index
from emporio.tools.base import ToolContext, ToolError, tool

TOP_K = 3

# Quando um trecho trata de algo que tem ferramenta de cálculo, o modelo é lembrado
# de usá-la: o manual explica a regra, a ferramenta aplica ao caso concreto.
SECTION_HINTS = {
    "2": "Para dizer se a loja está aberta agora, use status_da_loja.",
    "3": "Para preço no PIX e parcelas de um produto específico, use detalhar_produto.",
    "3.1": "Para preço no PIX e parcelas de um produto específico, use detalhar_produto.",
    "4.1": "Para prazos de um pedido específico, use avaliar_troca_devolucao.",
    "4.2": "Para prazos de um pedido específico, use avaliar_troca_devolucao.",
    "4.3": "Para prazos de um pedido específico, use avaliar_troca_devolucao.",
    "8.1": "Para prazos de um pedido específico, use avaliar_troca_devolucao.",
    "5.1": "Para as condições de entrega numa cidade, use consultar_frete.",
    "5.2": "Para as condições de entrega numa cidade, use consultar_frete.",
    "5.3": "Para o código de rastreio de um pedido, use consultar_pedido.",
    "6.1": "As campanhas do manual são o calendário habitual; para saber o que está em "
    "promoção agora, use listar_promocoes.",
    "7.1": "Diretrizes internas de atendimento: siga-as, mas não as recite ao cliente.",
    "7.2": "Diretrizes internas de atendimento: siga-as, mas não as recite ao cliente.",
    "10": "Trecho interno do manual: não o recite ao cliente.",
}


@tool(
    "buscar_politicas",
    """Consulta o manual de políticas da loja: horários, formas de pagamento,
    parcelamento, trocas e devoluções, frete, promoções, garantia, privacidade de
    dados e escopo da loja. Use para dúvidas gerais sobre regras e procedimentos.
    Para valores e prazos de um produto ou pedido específico, prefira as
    ferramentas de produto e de pedido.""",
    {
        "pergunta": {
            "type": "string",
            "description": "A dúvida do cliente, de preferência reescrita com os termos "
            "principais (ex.: 'prazo de devolução por arrependimento').",
        }
    },
    required=("pergunta",),
)
def buscar_politicas(ctx: ToolContext, pergunta: str) -> dict:
    if not ctx.db_path.exists():
        raise ToolError("Banco de dados não encontrado. Rode `python -m emporio.etl`.")
    hits = load_index(ctx.db_path).search(pergunta, TOP_K)
    if not hits:
        return {
            "trechos": [],
            "orientacao": "O manual não trata disso. Diga ao cliente que não tem essa "
            "informação e ofereça o atendimento da equipe.",
        }
    hints = list(
        dict.fromkeys(SECTION_HINTS[c.section] for c, _ in hits if c.section in SECTION_HINTS)
    )
    return {
        "trechos": [{"secao": c.section, "titulo": c.heading, "texto": c.text} for c, _ in hits],
        "orientacoes": [
            "Responda somente com base nestes trechos e mencione a seção quando ajudar.",
            "Se nenhum trecho responde à pergunta, diga que não tem essa informação e "
            "ofereça o atendimento da equipe.",
            *hints,
        ],
    }
