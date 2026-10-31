"""Busca textual no catálogo: tolerante a acentos, plurais e pequenos erros de digitação.

Com 65 produtos, uma busca determinística e explicável funciona melhor do que
embeddings: "Takamine GD20" precisa achar exatamente o GD20, e "violões até R$ 1.000"
é um filtro, não uma similaridade. Só biblioteca padrão (difflib).
"""

from __future__ import annotations

import re
from difflib import get_close_matches

from emporio.text import fold

STOPWORDS = {
    "a", "o", "as", "os", "um", "uma", "de", "do", "da", "dos", "das", "e", "em", "no",
    "na", "com", "para", "pra", "por", "que", "qual", "quais", "quanto", "custa", "preco",
    "valor", "tem", "voces", "vcs", "loja", "modelo", "modelos", "opcao", "opcoes",
}  # fmt: skip

# slug da categoria -> termos que a identificam (já sem acento). Termos compostos
# são verificados antes, para "contrabaixo acústico" não cair em "baixos".
CATEGORY_TERMS = {
    "cordas-orquestrais": ("contrabaixo acustico", "violino", "viola", "violoncelo", "cello"),
    "violoes": ("violao", "violoes"),
    "guitarras": ("guitarra",),
    "baixos": ("contrabaixo", "baixo"),
    "baterias-e-percussao": ("bateria", "percussao", "cajon", "pandeiro"),
    "teclados-e-pianos": ("teclado", "piano", "sintetizador", "synth", "controlador midi"),
    "instrumentos-de-sopro-madeiras": (
        "flauta", "clarinete", "saxofone", "sax", "oboe", "fagote",
    ),
    "instrumentos-de-sopro-metais": ("trompete", "trombone", "tuba", "trompa", "bombardino"),
    "ukuleles": ("ukulele", "uke"),
}  # fmt: skip

# Acessórios que a loja não vende (manual 1 e 7.1).
ACCESSORY_TERMS = (
    "palheta", "cabo", "case", "bag", "capa", "pedal", "pedaleira", "amplificador",
    "cubo", "correia", "baqueta", "estante", "suporte", "encordoamento", "jogo de cordas",
    "cordas para", "corda para", "cordas avulsas",
)  # fmt: skip


def stem(token: str) -> str:
    """Radical simples para plurais em português: violões -> violao, cordas -> corda."""
    if token.endswith(("oes", "aes")) and len(token) > 4:
        return token[:-3] + "ao"
    if token.endswith("s") and len(token) > 3 and not token[-2].isdigit():
        return token[:-1]
    return token


def tokens(text: str) -> list[str]:
    return [stem(t) for t in re.findall(r"[a-z0-9]+", fold(text)) if t not in STOPWORDS]


def _has_term(folded: str, term: str) -> bool:
    return re.search(rf"\b{re.escape(term)}s?\b", folded) is not None


def resolve_category(text: str) -> str | None:
    folded = fold(text)
    for slug, terms in CATEGORY_TERMS.items():
        if any(_has_term(folded, term) for term in terms):
            return slug
    return None


def category_tokens(slug: str) -> set[str]:
    words = " ".join(CATEGORY_TERMS.get(slug, ())) + " " + slug.replace("-", " ")
    return set(tokens(words))


def accessory_mentioned(text: str) -> str | None:
    folded = fold(text)
    return next((term for term in ACCESSORY_TERMS if _has_term(folded, term)), None)


def _partial_match(token: str, compact_name: str, product_tokens: set[str]) -> bool:
    if len(token) >= 2 and token in compact_name:
        return True
    return len(token) >= 4 and bool(get_close_matches(token, product_tokens, n=1, cutoff=0.8))


def score(query_tokens: list[str], name: str, search_text: str) -> int:
    """Pontuação: +2 token exato, +1 trecho do nome ou palavra parecida, +2 sequência colada.

    "gd 20" e "gd20" encontram o "GD20"; "takamini" encontra "Takamine".
    """
    product_tokens = set(tokens(search_text))
    compact_name = re.sub(r"[^a-z0-9]", "", fold(name))
    total = 0
    for token in query_tokens:
        if token in product_tokens:
            total += 2
        elif _partial_match(token, compact_name, product_tokens):
            total += 1
    for first, second in zip(query_tokens, query_tokens[1:], strict=False):
        if first + second in compact_name:
            total += 2
    return total
