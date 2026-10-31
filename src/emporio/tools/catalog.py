"""Ferramentas de catálogo: busca, detalhes de produto e promoções vigentes.

Todos os preços saem já formatados ("R$ 2.199,00"). O modelo só repete valores
prontos e nunca precisa fazer contas.
"""

from __future__ import annotations

import json
import sqlite3

from emporio.money import format_brl
from emporio.rules.payments import payment_options
from emporio.tools.base import ToolContext, ToolError, tool
from emporio.tools.search import (
    accessory_mentioned,
    category_tokens,
    resolve_category,
    score,
    tokens,
)

DEFAULT_LIMIT = 5
MAX_LIMIT = 15
LOW_STOCK = 2
ALTERNATIVES = 3

SPEC_LABELS = {
    "top": "tampo", "back_sides": "fundo e laterais", "neck": "braço", "strings": "cordas",
    "scale": "escala", "electronics": "captação", "color": "cor", "body": "corpo",
    "hardware": "ferragens", "pieces": "peças", "shells": "cascos", "keys": "teclas",
    "type": "tipo", "polyphony": "polifonia",
}  # fmt: skip
SPEC_VALUES = {
    "steel": "aço", "no": "não", "yes": "sim", "included": "inclusas",
    "synthesizer": "sintetizador",
}  # fmt: skip
ACCESSORY_NOTICE = (
    "A Empório da Música trabalha exclusivamente com instrumentos musicais e não vende "
    "acessórios como cordas, palhetas, cabos, cases, pedais ou amplificadores."
)


def availability(row: sqlite3.Row) -> str:
    if row["status"] == "discontinued":
        return "fora de linha (não faz mais parte do catálogo)"
    if row["status"] == "coming_soon":
        return "em breve (ainda não disponível para venda)"
    if row["stock_quantity"] == 0:
        return "esgotado no momento"
    if row["stock_quantity"] <= LOW_STOCK:
        return "disponível, últimas unidades"
    return "disponível"


def price_info(row: sqlite3.Row) -> dict:
    if row["discount_percent"] is None:
        return {"preco": format_brl(row["price_cents"])}
    # Manual 6.2: preço promocional sempre junto do original e do percentual.
    return {
        "preco": format_brl(row["final_price_cents"]),
        "preco_original": format_brl(row["price_cents"]),
        "desconto": f"{row['discount_percent']}%",
        "promocao": row["promotion_label"],
    }


def summarize(row: sqlite3.Row) -> dict:
    return {
        "id": row["product_id"],
        "nome": row["name"],
        "categoria": row["category_name"],
        **price_info(row),
        "disponibilidade": availability(row),
    }


def _specs(row: sqlite3.Row) -> dict:
    specs = json.loads(row["specs_json"])
    return {
        SPEC_LABELS.get(key, key): SPEC_VALUES.get(value.lower(), value)
        for key, value in specs.items()
    }


def _catalog(conn: sqlite3.Connection, where: str = "1 = 1", params: tuple = ()) -> list:
    return conn.execute(f"SELECT * FROM v_catalog WHERE {where}", params).fetchall()


def _category(conn: sqlite3.Connection, slug: str) -> sqlite3.Row:
    return conn.execute("SELECT * FROM categories WHERE slug = ?", (slug,)).fetchone()


@tool(
    "buscar_produtos",
    """Busca instrumentos no catálogo da loja, com preço, promoção vigente e
    disponibilidade em tempo real. Use para perguntas sobre quais produtos existem,
    opções dentro de uma faixa de preço, marcas ou tipos de instrumento.
    Ex.: "violões até R$ 1000" -> categoria="violão", preco_max=1000.""",
    {
        "termo": {
            "type": "string",
            "description": "Palavras-chave: marca, modelo ou característica (ex.: 'Yamaha', "
            "'eletroacústico', 'nylon').",
        },
        "categoria": {
            "type": "string",
            "description": "Tipo de instrumento em linguagem natural (ex.: 'violão', "
            "'guitarra', 'ukulele', 'teclado').",
        },
        "preco_min": {"type": "number", "description": "Preço mínimo em reais."},
        "preco_max": {"type": "number", "description": "Preço máximo em reais."},
        "incluir_indisponiveis": {
            "type": "boolean",
            "description": "Se true, inclui esgotados e fora de linha. Padrão: false.",
        },
        "limite": {"type": "integer", "description": "Máximo de resultados (padrão 5)."},
    },
)
def buscar_produtos(
    ctx: ToolContext,
    termo: str = "",
    categoria: str = "",
    preco_min: float | None = None,
    preco_max: float | None = None,
    incluir_indisponiveis: bool = False,
    limite: int = DEFAULT_LIMIT,
) -> dict:
    limite = max(1, min(limite, MAX_LIMIT))
    accessory = accessory_mentioned(f"{termo} {categoria}")
    slug = resolve_category(categoria) if categoria else resolve_category(termo)

    with ctx.connect() as conn:
        clauses, params = [], []
        if slug:
            clauses.append("category_slug = ?")
            params.append(slug)
        if preco_min is not None:
            clauses.append("final_price_cents >= ?")
            params.append(round(preco_min * 100))
        if preco_max is not None:
            clauses.append("final_price_cents <= ?")
            params.append(round(preco_max * 100))
        rows = _catalog(conn, " AND ".join(clauses) or "1 = 1", tuple(params))
        category = _category(conn, slug) if slug else None

    query_tokens = tokens(termo)
    if slug:
        # A categoria já virou filtro; não deve pesar no ranking ("violão yamaha" -> "yamaha").
        query_tokens = [t for t in query_tokens if t not in category_tokens(slug)]
    if query_tokens:
        scored = [(score(query_tokens, r["name"], r["search_text"]), r) for r in rows]
        best = max((s for s, _ in scored), default=0)
        rows = [r for s, r in sorted(scored, key=lambda x: (-x[0], x[1]["final_price_cents"]))
                if s > 0 and s >= best / 2]  # fmt: skip
    else:
        rows = sorted(rows, key=lambda r: r["final_price_cents"])

    available = [r for r in rows if r["is_sellable"]]
    hidden = len(rows) - len(available)
    selected = rows if incluir_indisponiveis else available

    result: dict = {
        "filtros_aplicados": {
            "categoria": category["name"] if category else None,
            "termo": termo or None,
            "preco_min": format_brl(round(preco_min * 100)) if preco_min is not None else None,
            "preco_max": format_brl(round(preco_max * 100)) if preco_max is not None else None,
        },
        "total_encontrado": len(selected),
        "produtos": [summarize(r) for r in selected[:limite]],
    }
    if len(selected) > limite:
        result["orientacao"] = (
            f"Mostrando {limite} de {len(selected)}. Diga ao cliente quantas opções existem e "
            "pergunte se quer refinar (faixa de preço, marca, tipo de corda)."
        )
    if hidden and not incluir_indisponiveis:
        result["indisponiveis_ocultos"] = hidden
    if category and not selected:
        with ctx.connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM products WHERE category_id = ?", (category["category_id"],)
            ).fetchone()[0]
        if count == 0:
            result["aviso"] = (
                f"A categoria '{category['name']}' existe, mas não há nenhum produto cadastrado "
                "no momento. Não invente produtos; ofereça avisar a equipe ou outra categoria."
            )
    if accessory:
        result["aviso_escopo"] = (
            f"O pedido menciona '{accessory}'. {ACCESSORY_NOTICE} Se o cliente procura o "
            "acessório, explique isso com gentileza."
        )
    return result


def find_product(conn: sqlite3.Connection, produto: str) -> tuple[sqlite3.Row | None, list]:
    """Encontra um produto por id ou nome. Devolve (produto, candidatos se ambíguo)."""
    if produto.strip().isdigit():
        row = conn.execute(
            "SELECT * FROM v_catalog WHERE product_id = ?", (int(produto),)
        ).fetchone()
        return row, []
    query_tokens = tokens(produto)
    if not query_tokens:
        return None, []
    scored = sorted(
        ((score(query_tokens, r["name"], r["search_text"]), r) for r in _catalog(conn)),
        key=lambda x: -x[0],
    )
    if not scored or scored[0][0] == 0:
        return None, []
    best = scored[0][0]
    ties = [r for s, r in scored if s == best]
    if len(ties) > 1:
        return None, ties
    return ties[0], []


def _alternatives(conn: sqlite3.Connection, row: sqlite3.Row) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM v_catalog WHERE category_id = ? AND is_sellable AND product_id != ? "
        "ORDER BY ABS(final_price_cents - ?) LIMIT ?",
        (row["category_id"], row["product_id"], row["price_cents"], ALTERNATIVES),
    ).fetchall()
    return [summarize(r) for r in rows]


@tool(
    "detalhar_produto",
    """Detalhes completos de UM produto: preço, promoção vigente, condições de
    pagamento (PIX, parcelamento), especificações e disponibilidade. Se o produto
    estiver indisponível, já traz alternativas semelhantes. Use quando o cliente
    citar um modelo específico (ex.: "quanto custa o Takamine GD20?").""",
    {
        "produto": {
            "type": "string",
            "description": "Nome ou modelo do produto (ex.: 'Takamine GD20'), ou o id "
            "numérico retornado por buscar_produtos.",
        }
    },
    required=("produto",),
)
def detalhar_produto(ctx: ToolContext, produto: str) -> dict:
    with ctx.connect() as conn:
        row, candidates = find_product(conn, produto)
        if candidates:
            return {
                "ambiguo": True,
                "candidatos": [summarize(r) for r in candidates[:5]],
                "orientacao": "Mais de um produto corresponde. Pergunte ao cliente qual deles.",
            }
        if row is None:
            raise ToolError(
                f"Nenhum produto encontrado para '{produto}'. Tente buscar_produtos com "
                "termos mais gerais."
            )
        alternatives = [] if row["is_sellable"] else _alternatives(conn, row)

    result = {
        **summarize(row),
        "especificacoes": _specs(row),
        "descricao": row["description"],
    }
    if row["description"] is None:
        result["orientacao_descricao"] = (
            "Descrição em revisão pela equipe. Use apenas nome e especificações."
        )
    if row["is_sellable"]:
        options = payment_options(row["final_price_cents"], row["discount_percent"] is not None)
        result["pagamento"] = options.as_text()
    else:
        result["alternativas"] = alternatives
        result["orientacao"] = (
            "Produto indisponível. Informe com transparência e sugira as alternativas "
            "(manual 7.3). Nunca confirme disponibilidade de item indisponível."
        )
    return result


@tool(
    "listar_promocoes",
    """Lista as promoções vigentes agora, com preço original, percentual e preço
    promocional. Use quando o cliente perguntar por ofertas, descontos ou por uma
    campanha específica (ex.: Black Friday). Promoções que não aparecem aqui não
    estão ativas.""",
    {},
)
def listar_promocoes(ctx: ToolContext) -> dict:
    with ctx.connect() as conn:
        rows = _catalog(conn, "discount_percent IS NOT NULL ORDER BY discount_percent DESC")
    return {
        "promocoes_ativas": [summarize(r) for r in rows],
        "regras": [
            "Promoções não são cumulativas.",
            "O desconto de 5% no PIX não se aplica a preços promocionais.",
            "Sujeitas à disponibilidade de estoque, sem reserva de preço.",
        ],
        "orientacao": (
            "Se o cliente citar uma promoção que não está nesta lista, ela não está vigente: "
            "informe com transparência e apresente o preço atual (manual 7.3)."
        ),
    }
