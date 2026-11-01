"""Avaliação ponta a ponta e conversas de exemplo, com o modelo configurado no .env.

python -m emporio.evals              # roda evals/agente.json e grava docs/avaliacao.md
python -m emporio.evals --exemplos   # gera docs/conversas/*.md
python -m emporio.evals --pausa 6    # espaça as chamadas (cotas do tier gratuito)
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime

from emporio.config import PROJECT_ROOT
from emporio.evals.examples import generate
from emporio.evals.runner import EvalSummary, load_scenarios, render_report, run_scenario
from emporio.llm import LLMError, get_provider

REPORT_PATH = PROJECT_ROOT / "docs" / "avaliacao.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m emporio.evals")
    parser.add_argument("--exemplos", action="store_true", help="gera as conversas de exemplo")
    parser.add_argument("--pausa", type=float, default=4.0, help="segundos entre cenários")
    parser.add_argument("--so", metavar="TRECHO", help="roda só cenários cujo nome contém o trecho")
    args = parser.parse_args(argv)

    try:
        provider = get_provider()
    except LLMError as error:
        print(f"Erro: {error}")
        return 1
    print(f"Modelo: {provider.model} via {provider.name}\n")

    if args.exemplos:
        for path in generate(provider, pause_s=args.pausa / 2):
            print(f"  gerado {path.relative_to(PROJECT_ROOT)}")
        return 0

    scenarios = load_scenarios()
    if args.so:
        scenarios = [s for s in scenarios if args.so.lower() in s["nome"].lower()]
    summary = EvalSummary(provider.name, provider.model)
    for i, scenario in enumerate(scenarios):
        if i:
            time.sleep(args.pausa)
        outcome = run_scenario(provider, scenario)
        summary.outcomes.append(outcome)
        mark = "ok   " if outcome.passed else "FALHA"
        detail = f"  ({'; '.join(outcome.failures)})" if outcome.failures else ""
        print(f"  {mark} {outcome.name} [{outcome.elapsed_s}s]{detail}")

    print(f"\n{summary.passed}/{len(summary.outcomes)} cenários aprovados")
    if not args.so:
        REPORT_PATH.write_text(
            render_report(summary, datetime.now().strftime("%d/%m/%Y %H:%M")), encoding="utf-8"
        )
        print(f"Relatório: {REPORT_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
