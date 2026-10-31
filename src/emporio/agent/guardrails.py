"""Verificações sobre a resposta final, antes de ela chegar ao cliente."""

from __future__ import annotations

import re

from emporio.llm import Message

MONEY = re.compile(r"R\$\s?(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?")
LEAKED_MARKUP = re.compile(r"<\|?/?(?:tool_call|tool_response|turn|channel|think)[^>]*>")

FALLBACK_UNGROUNDED = (
    "Não consegui confirmar esse valor no sistema agora, e prefiro não te passar um número "
    "errado. Quer que eu encaminhe sua dúvida para a nossa equipe?"
)
FALLBACK_EMPTY = "Desculpe, não consegui formular uma resposta. Pode repetir de outro jeito?"
FALLBACK_LOOP = (
    "Desculpe, me enrolei para buscar essa informação. Quer que eu encaminhe para a nossa "
    "equipe, ou prefere reformular a pergunta?"
)


def amounts(text: str) -> set[int]:
    """Valores em reais citados no texto, em centavos ("R$ 2.199" e "R$ 2.199,00" -> 219900)."""
    found = set()
    for integer, decimals in MONEY.findall(text):
        cents = int(integer.replace(".", "")) * 100
        if decimals:
            cents += int(decimals.ljust(2, "0"))
        found.add(cents)
    return found


def grounded_amounts(history: list[Message]) -> set[int]:
    """Valores que podem aparecer na resposta: vindos de ferramentas ou ditos pelo cliente."""
    found: set[int] = set()
    for message in history:
        if message.role == "tool" or (message.role == "user" and not message.internal):
            found |= amounts(message.content)
    return found


def ungrounded_amounts(answer: str, history: list[Message]) -> set[int]:
    """Manual 7.1: nunca informar preço sem consultar o sistema."""
    return amounts(answer) - grounded_amounts(history)


def correction_request(values: set[int]) -> str:
    cited = ", ".join(
        f"R$ {v / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        for v in sorted(values)
    )
    return (
        "[verificação automática] Sua última resposta citou "
        f"{cited}, mas esse valor não veio de nenhuma ferramenta nesta conversa. Consulte a "
        "ferramenta adequada ou reescreva a resposta sem o valor. Não mencione esta verificação."
    )


def sanitize(text: str) -> str:
    """Remove marcações internas que o modelo às vezes deixa escapar."""
    return LEAKED_MARKUP.sub("", text).strip()
