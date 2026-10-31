"""Avaliação da recuperação: a seção certa aparece entre os primeiros resultados?

Métricas: hit@1 (a primeira seção é uma das esperadas), hit@k (alguma das k é
esperada) e MRR (média do inverso da posição da primeira seção correta).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from emporio.config import PROJECT_ROOT
from emporio.rag.store import PolicyIndex

DEFAULT_EVAL_PATH = PROJECT_ROOT / "evals" / "politicas.jsonl"


@dataclass(frozen=True)
class EvalItem:
    question: str
    expected: set[str]


@dataclass
class EvalReport:
    k: int
    total: int = 0
    hit_at_1: int = 0
    hit_at_k: int = 0
    reciprocal_rank: float = 0.0
    misses: list[tuple[str, set[str], list[str]]] = field(default_factory=list)

    @property
    def mrr(self) -> float:
        return self.reciprocal_rank / self.total if self.total else 0.0

    def summary(self) -> str:
        return (
            f"hit@1 = {self.hit_at_1}/{self.total} ({self.hit_at_1 / self.total:.0%})  "
            f"hit@{self.k} = {self.hit_at_k}/{self.total} ({self.hit_at_k / self.total:.0%})  "
            f"MRR = {self.mrr:.2f}"
        )


def load_items(path: Path = DEFAULT_EVAL_PATH) -> list[EvalItem]:
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            data = json.loads(line)
            items.append(EvalItem(data["pergunta"], set(data["secoes"])))
    return items


def evaluate(index: PolicyIndex, items: list[EvalItem], k: int = 3) -> EvalReport:
    report = EvalReport(k=k)
    for item in items:
        found = [chunk.section for chunk, _ in index.search(item.question, k)]
        rank = next((i + 1 for i, s in enumerate(found) if s in item.expected), None)
        report.total += 1
        report.hit_at_1 += rank == 1
        report.hit_at_k += rank is not None
        report.reciprocal_rank += 1 / rank if rank else 0.0
        if rank != 1:
            report.misses.append((item.question, item.expected, found))
    return report
