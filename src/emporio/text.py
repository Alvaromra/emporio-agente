"""Utilitários de normalização de texto para busca e comparação."""

from __future__ import annotations

import re
import unicodedata


def fold(text: str) -> str:
    """Minúsculas, sem acentos e com espaços colapsados.

    >>> fold("  Violão   Elétrico ")
    'violao eletrico'
    """
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", without_accents).strip().lower()


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", fold(text)).strip("-")


def stem(token: str) -> str:
    """Radical simples para plurais em português: violões -> violao, cordas -> corda."""
    if token.endswith(("oes", "aes")) and len(token) > 4:
        return token[:-3] + "ao"
    if token.endswith("s") and len(token) > 3 and not token[-2].isdigit():
        return token[:-1]
    return token
