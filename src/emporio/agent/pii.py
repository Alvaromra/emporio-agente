"""Dados pessoais fora do modelo: marcadores no lugar de e-mails e telefones.

Antes de a mensagem do cliente ir ao LLM, e-mails e telefones viram marcadores
([EMAIL_1], [TELEFONE_1]). O modelo raciocina e chama ferramentas com os
marcadores; o agente os troca pelos valores reais só na hora de executar a
ferramenta, que compara por HMAC. Assim o provedor de LLM nunca recebe o contato.

CPF e número de cartão não são necessários para nada no atendimento: são removidos
de forma irreversível, e o modelo é instruído a avisar o cliente.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
CPF = re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)")
CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
PHONE = re.compile(
    r"(?<![\w.,/])"
    r"(?:\+?55[\s.-]?)?"
    r"(?:\(?0?\d{2}\)?[\s.-]?)?"
    r"9?\d{4}[\s.-]?\d{4}"
    r"(?![\w.,/])"
)
MARKER = re.compile(r"\[(?:EMAIL|TELEFONE)_\d+\]")
CPF_REMOVED = "[CPF REMOVIDO]"
CARD_REMOVED = "[CARTÃO REMOVIDO]"


def _luhn_ok(number: str) -> bool:
    digits = [int(d) for d in re.sub(r"\D", "", number)][::-1]
    total = sum(d if i % 2 == 0 else (d * 2 - 9 if d > 4 else d * 2) for i, d in enumerate(digits))
    return total % 10 == 0


@dataclass
class PiiVault:
    """Cofre por conversa: marcador <-> valor real. Vive só em memória."""

    values: dict[str, str] = field(default_factory=dict)  # marcador -> valor
    markers: dict[str, str] = field(default_factory=dict)  # valor -> marcador

    def _marker(self, kind: str, value: str) -> str:
        key = value.strip()
        if key not in self.markers:
            count = sum(1 for m in self.values if m.startswith(f"[{kind}_")) + 1
            marker = f"[{kind}_{count}]"
            self.markers[key] = marker
            self.values[marker] = key
        return self.markers[key]

    def redact(self, text: str) -> str:
        text = EMAIL.sub(lambda m: self._marker("EMAIL", m.group()), text)
        text = CPF.sub(CPF_REMOVED, text)
        text = CARD.sub(lambda m: CARD_REMOVED if _luhn_ok(m.group()) else m.group(), text)
        return PHONE.sub(lambda m: self._marker("TELEFONE", m.group()), text)

    def restore(self, value):
        """Troca marcadores pelos valores reais (em textos, listas e dicionários)."""
        if isinstance(value, str):
            return MARKER.sub(lambda m: self.values.get(m.group(), m.group()), value)
        if isinstance(value, dict):
            return {k: self.restore(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.restore(v) for v in value]
        return value
