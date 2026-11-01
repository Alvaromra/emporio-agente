"""Executa cenários contra o agente com o modelo real e verifica o resultado.

Cada cenário declara o que precisa acontecer, de forma objetiva:
- ferramentas: todas precisam ter sido chamadas;
- ferramentas_algum: ao menos uma delas;
- ferramentas_proibidas / sem_ferramentas: o que não pode ser chamado;
- contem / contem_algum / nao_contem: trechos esperados ou proibidos na última resposta.

Os cenários rodam com o relógio congelado (padrão: sábado, 31/10/2026, 10h30) para que
prazos e horário da loja sejam reproduzíveis.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from emporio.agent import Agent
from emporio.config import PROJECT_ROOT, get_settings
from emporio.llm import LLMError, LLMProvider

DEFAULT_NOW = "2026-10-31T10:30"
SCENARIOS_PATH = PROJECT_ROOT / "evals" / "agente.json"


@contextmanager
def frozen_time(moment: str) -> Iterator[None]:
    """Congela o "agora" do agente (EMPORIO_NOW) durante o bloco."""
    previous = os.environ.get("EMPORIO_NOW")
    os.environ["EMPORIO_NOW"] = moment
    get_settings.cache_clear()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("EMPORIO_NOW", None)
        else:
            os.environ["EMPORIO_NOW"] = previous
        get_settings.cache_clear()


@dataclass
class Outcome:
    name: str
    passed: bool
    failures: list[str]
    tools: list[str]
    answers: list[str]
    events: list[str]
    elapsed_s: float
    tokens: int = 0


@dataclass
class EvalSummary:
    provider: str
    model: str
    outcomes: list[Outcome] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(o.passed for o in self.outcomes)


def check(scenario: dict, tools: list[str], answer: str) -> list[str]:
    """Falhas de um cenário (lista vazia = passou). Comparação de texto sem caixa."""
    failures = []
    lower = answer.lower()
    for name in scenario.get("ferramentas", []):
        if name not in tools:
            failures.append(f"não chamou {name}")
    expected_any = scenario.get("ferramentas_algum")
    if expected_any and not set(expected_any) & set(tools):
        failures.append(f"não chamou nenhuma de {expected_any}")
    for name in scenario.get("ferramentas_proibidas", []):
        if name in tools:
            failures.append(f"chamou {name}, que não deveria")
    if scenario.get("sem_ferramentas") and tools:
        failures.append(f"chamou ferramentas sem necessidade: {tools}")
    for text in scenario.get("contem", []):
        if text.lower() not in lower:
            failures.append(f"faltou '{text}'")
    any_of = scenario.get("contem_algum")
    if any_of and not any(t.lower() in lower for t in any_of):
        failures.append(f"faltou algum de {any_of}")
    for text in scenario.get("nao_contem", []):
        if text.lower() in lower:
            failures.append(f"continha '{text}'")
    return failures


def run_scenario(provider: LLMProvider, scenario: dict) -> Outcome:
    with frozen_time(scenario.get("agora", DEFAULT_NOW)):
        agent = Agent(provider)
        session = agent.new_session("avaliacao")
        tools: list[str] = []
        answers: list[str] = []
        events: list[str] = []
        tokens = 0
        started = time.perf_counter()
        try:
            for message in scenario["mensagens"]:
                reply = agent.reply(session, message)
                tools += [t.name for t in reply.tools]
                answers.append(reply.text)
                events += reply.events
                tokens += sum(reply.usage.values())
        except LLMError as error:
            elapsed = time.perf_counter() - started
            return Outcome(scenario["nome"], False, [f"erro do modelo: {error}"], tools,
                           answers, events, round(elapsed, 1), tokens)  # fmt: skip
        elapsed = time.perf_counter() - started
    failures = check(scenario, tools, answers[-1] if answers else "")
    return Outcome(scenario["nome"], not failures, failures, tools, answers, events,
                   round(elapsed, 1), tokens)  # fmt: skip


def load_scenarios(path: Path = SCENARIOS_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def render_report(summary: EvalSummary, run_date: str) -> str:
    total = len(summary.outcomes)
    rate = summary.passed / total if total else 0
    avg = sum(o.elapsed_s for o in summary.outcomes) / total if total else 0
    lines = [
        "# Avaliação ponta a ponta do agente",
        "",
        "> Gerado por `python -m emporio.evals`. Cenários em `evals/agente.json`.",
        "",
        f"- Modelo: `{summary.model}` via {summary.provider}",
        f"- Execução: {run_date}, com o relógio do agente congelado em {DEFAULT_NOW} "
        "(salvo cenários que definem outro horário)",
        f"- Resultado: **{summary.passed} de {total} cenários aprovados ({rate:.0%})**",
        f"- Tempo médio por cenário: {avg:.1f} s",
        "",
        "| Cenário | Resultado | Ferramentas chamadas | Observação |",
        "|---|---|---|---|",
    ]
    for o in summary.outcomes:
        status = "aprovado" if o.passed else "reprovado"
        tools = ", ".join(f"`{t}`" for t in o.tools) or "nenhuma"
        note = "; ".join(o.failures + o.events) or "-"
        lines.append(f"| {o.name} | {status} | {tools} | {note} |")
    lines += ["", "## Respostas", ""]
    for o in summary.outcomes:
        lines += [f"### {o.name}", ""]
        lines += [f"> {a}".replace("\n", "\n> ") + "\n" for a in o.answers]
    return "\n".join(lines).rstrip() + "\n"
