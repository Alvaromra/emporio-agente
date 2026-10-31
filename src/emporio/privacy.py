"""Proteção de dados pessoais (LGPD).

O banco operacional do agente não guarda e-mail nem telefone de clientes em texto
claro. Ele guarda apenas uma impressão digital (HMAC-SHA256 com um segredo, o
"pepper"), suficiente para conferir a identidade de quem pergunta por um pedido,
mas inútil para quem tentar extrair contatos do banco. Do cadastro, só o primeiro
nome (para a saudação, manual 7.2) e a cidade (regras de frete) ficam legíveis.

Isso aplica os princípios de minimização e pseudonimização da LGPD
(arts. 6º, III, e 13, § 4º).
"""

from __future__ import annotations

import hashlib
import hmac
import re
from typing import Literal

ContactKind = Literal["email", "phone"]

# DDD de Campo Grande/MS. Usado quando o cliente informa o telefone sem DDD.
DEFAULT_DDD = "67"


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_phone(value: str, default_ddd: str = DEFAULT_DDD) -> str:
    """Reduz um telefone brasileiro a DDD + número, só dígitos.

    Aceita "(67) 99812-3456", "+55 67 99812-3456", "067998123456" e "99812-3456"
    (este último assume o DDD da loja).
    """
    digits = re.sub(r"\D", "", value)
    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]
    digits = digits.lstrip("0")
    if len(digits) in (8, 9):
        digits = default_ddd + digits
    return digits


def fingerprint(kind: ContactKind, value: str, pepper: str) -> str:
    """Impressão digital determinística de um contato, após normalização."""
    normalized = normalize_email(value) if kind == "email" else normalize_phone(value)
    message = f"{kind}:{normalized}".encode()
    return hmac.new(pepper.encode(), message, hashlib.sha256).hexdigest()


def first_name(full_name: str) -> str:
    parts = full_name.split()
    return parts[0] if parts else ""
