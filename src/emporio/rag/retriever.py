"""Recuperação de trechos do manual com BM25 e expansão de sinônimos.

Por que BM25 e não embeddings, nesta etapa: são 25 trechos de um manual com
vocabulário estreito e previsível. A busca lexical é determinística, roda sem rede
e sem modelo, e o conjunto de avaliação (evals/politicas.jsonl) mostra se ela basta.
A ponte entre o jeito de o cliente falar ("me arrependi", "chegou quebrado") e o
vocabulário do manual ("arrependimento", "defeito", "avaria") é feita por um
dicionário de sinônimos pequeno e auditável.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from emporio.text import fold, stem

STOPWORDS = {
    "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das", "e",
    "em", "no", "na", "nos", "nas", "com", "para", "pra", "por", "pelo", "pela", "que",
    "qual", "quais", "como", "quando", "onde", "se", "eu", "meu", "minha", "voce", "voces",
    "vcs", "ser", "sao", "esta", "estao", "tem", "ter", "posso", "pode", "podem", "ao",
    "aos", "ou", "mais", "muito", "isso", "esse", "essa", "este", "ja", "nao", "sim", "me",
    "mim", "loja", "emporio", "musica", "oi", "ola", "bom", "dia", "tarde", "noite",
}  # fmt: skip

# termo do cliente -> termos do manual. Pesam metade de um termo original.
SYNONYMS = {
    "devolver": ("devolucao", "arrependimento", "reembolso"),
    "devolucao": ("arrependimento", "reembolso"),
    "arrependi": ("arrependimento", "devolucao"),
    "desistir": ("arrependimento", "devolucao"),
    "desisti": ("arrependimento", "devolucao"),
    "gostei": ("arrependimento", "devolucao", "preferencia"),
    "dinheiro": ("reembolso",),
    "estorno": ("reembolso",),
    "trocar": ("troca",),
    "quebrado": ("defeito", "avaria", "dano"),
    "quebrou": ("defeito", "dano"),
    "estragado": ("defeito",),
    "estragou": ("defeito",),
    "funciona": ("defeito",),
    "problema": ("defeito",),
    "amassado": ("avaria", "dano"),
    "pagar": ("pagamento", "forma"),
    "pago": ("pagamento",),
    "aceita": ("pagamento", "forma"),
    "aceitam": ("pagamento", "forma"),
    "cartao": ("credito", "debito"),
    "parcelar": ("parcelamento", "parcela"),
    "parcelado": ("parcelamento", "parcela"),
    "vezes": ("parcelamento", "parcela"),
    "juros": ("parcelamento",),
    "metade": ("combinacao",),
    "junto": ("combinacao",),
    "entrega": ("frete", "envio", "prazo"),
    "entregam": ("entrega", "frete"),
    "envia": ("frete", "envio"),
    "mandam": ("frete", "envio"),
    "chega": ("prazo", "entrega"),
    "demora": ("prazo",),
    "correio": ("pac", "sedex"),
    "rastrear": ("rastreamento", "codigo"),
    "rastreio": ("rastreamento", "codigo"),
    "horario": ("funcionamento",),
    "aberto": ("horario", "funcionamento"),
    "aberta": ("horario", "funcionamento"),
    "abre": ("horario", "funcionamento"),
    "abrem": ("horario", "funcionamento"),
    "fecha": ("horario", "funcionamento"),
    "fecham": ("horario", "funcionamento"),
    "funcionam": ("funcionamento", "horario"),
    "fica": ("endereco",),
    "telefone": ("whatsapp", "contato"),
    "ligar": ("telefone", "whatsapp"),
    "email": ("contato",),
    "falar": ("contato", "atendimento"),
    "dados": ("privacidade", "pessoais"),
    "privacidade": ("dados", "lgpd"),
    "apagar": ("exclusao", "dados"),
    "excluir": ("exclusao", "dados"),
    "compartilham": ("compartilhados", "terceiros"),
    "vendem": ("comercializamos",),
    "vende": ("comercializamos",),
    "promocao": ("desconto",),
    "desconto": ("promocao",),
    "oferta": ("promocao", "desconto"),
    "liquidacao": ("promocao", "queima"),
    "acumula": ("cumulativa", "cumulatividade"),
    "acumular": ("cumulativa", "cumulatividade"),
    "reclamar": ("reclamacao",),
    "reclamacao": ("responsavel",),
    "garantia": ("fabricante", "legal"),
    "cobre": ("garantia",),
    "gasta": ("desgaste",),
    "gastas": ("desgaste",),
    "gastou": ("desgaste",),
    "regulagem": ("ajuste", "setup"),
    "bocal": ("boquilha",),
}

K1 = 1.5
B = 0.75
SYNONYM_WEIGHT = 0.5


def _words(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", fold(text)) if t not in STOPWORDS]


def analyze(text: str) -> list[str]:
    return [stem(t) for t in _words(text)]


def expand(query: str) -> dict[str, float]:
    """Termos da consulta com peso: originais 1.0, sinônimos 0.5."""
    weights: dict[str, float] = {}
    for word in _words(query):
        weights[stem(word)] = 1.0
        for synonym in SYNONYMS.get(word, SYNONYMS.get(stem(word), ())):
            for term in analyze(synonym):
                weights.setdefault(term, SYNONYM_WEIGHT)
    return weights


@dataclass(frozen=True)
class Document:
    key: str
    tokens: list[str]


@dataclass(frozen=True)
class Hit:
    key: str
    score: float


class BM25Index:
    def __init__(self, documents: dict[str, str]):
        self.docs = [Document(key, analyze(text)) for key, text in documents.items()]
        self.avg_len = sum(len(d.tokens) for d in self.docs) / max(len(self.docs), 1)
        self.freqs = [Counter(d.tokens) for d in self.docs]
        df = Counter(term for f in self.freqs for term in f)
        n = len(self.docs)
        self.idf = {
            term: math.log(1 + (n - count + 0.5) / (count + 0.5)) for term, count in df.items()
        }

    def search(self, query: str, k: int = 3) -> list[Hit]:
        weights = expand(query)
        hits = []
        for doc, freqs in zip(self.docs, self.freqs, strict=True):
            norm = K1 * (1 - B + B * len(doc.tokens) / self.avg_len)
            total = 0.0
            for term, weight in weights.items():
                tf = freqs.get(term)
                if tf:
                    total += weight * self.idf[term] * tf * (K1 + 1) / (tf + norm)
            if total > 0:
                hits.append(Hit(doc.key, total))
        hits.sort(key=lambda h: (-h.score, h.key))
        return hits[:k]
