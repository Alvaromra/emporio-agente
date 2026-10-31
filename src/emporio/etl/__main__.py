"""CLI do ETL: `python -m emporio.etl` (ou `emporio-etl`)."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from emporio.config import get_settings
from emporio.etl.extract import ContractError
from emporio.etl.pipeline import DEFAULT_REPORT_PATH, run_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="emporio-etl",
        description="Gera o banco SQLite do agente a partir dos CSVs da loja.",
    )
    parser.add_argument("--raw-dir", type=Path, help="pasta com os CSVs (padrão: data/raw)")
    parser.add_argument("--db", type=Path, help="banco de saída (padrão: data/processed/store.db)")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--no-report", action="store_true", help="não gera o relatório")
    parser.add_argument(
        "--reference-date",
        type=date.fromisoformat,
        help="data de referência AAAA-MM-DD para os alertas (padrão: hoje em Campo Grande)",
    )
    args = parser.parse_args(argv)

    if get_settings().pii_pepper_is_default:
        print("Aviso: EMPORIO_PII_PEPPER não definido; usando o valor de desenvolvimento.")

    try:
        result = run_pipeline(
            raw_dir=args.raw_dir,
            db_path=args.db,
            report_path=None if args.no_report else args.report,
            reference_date=args.reference_date,
        )
    except ContractError as error:
        print(f"Erro de contrato nos dados de origem: {error}", file=sys.stderr)
        return 1

    print(f"Banco gerado em {result.db_path}")
    for table, count in result.counts.items():
        print(f"  {table:<12} {count:>4} registros")
    by_severity = Counter(i.check.severity.value for i in result.issues)
    summary = ", ".join(f"{n} {sev}" for sev, n in sorted(by_severity.items()))
    print(f"Achados de qualidade: {len(result.issues)} ({summary})")
    print(f"Alertas operacionais: {len(result.alerts)}")
    if result.report_path:
        print(f"Relatório: {result.report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
