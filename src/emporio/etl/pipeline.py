"""Orquestração do ETL: extrair, transformar, carregar e relatar."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from emporio import clock
from emporio.config import PROJECT_ROOT, get_settings
from emporio.etl.checks import Issue, issue
from emporio.etl.extract import extract
from emporio.etl.load import write_database
from emporio.etl.report import Alert, operational_alerts, render_report
from emporio.etl.transform import transform
from emporio.rag.manual import load_manual

DEFAULT_REPORT_PATH = PROJECT_ROOT / "docs" / "relatorio_qualidade_dados.md"


@dataclass(frozen=True)
class PipelineResult:
    db_path: Path
    report_path: Path | None
    counts: dict[str, int]
    issues: list[Issue]
    alerts: list[Alert]


def run_pipeline(
    raw_dir: Path | None = None,
    db_path: Path | None = None,
    report_path: Path | None = DEFAULT_REPORT_PATH,
    reference_date: date | None = None,
    pepper: str | None = None,
) -> PipelineResult:
    settings = get_settings()
    raw_dir = raw_dir or settings.raw_dir
    db_path = db_path or settings.db_path
    reference = reference_date or clock.today()

    raw = extract(raw_dir)
    data = transform(raw.tables, pepper or settings.pii_pepper)
    chunks, errata = load_manual(raw.manual_path)
    data.policy_chunks = [
        {
            "section": c.section,
            "title": c.title,
            "parent": c.parent,
            "heading": c.heading,
            "text": c.text,
        }
        for c in chunks
    ]
    data.issues += [issue("policy.errata_applied", "policy_chunks", s, d) for s, d in errata]
    alerts = operational_alerts(data.orders, reference)

    tables = (
        "categories",
        "products",
        "promotions",
        "customers",
        "orders",
        "order_items",
        "policy_chunks",
    )
    counts = {table: len(getattr(data, table)) for table in tables}
    write_database(
        data,
        db_path,
        metadata={
            "reference_date": reference.isoformat(),
            "sources_sha256": raw.sources,
            "counts": counts,
            "issues": len(data.issues),
        },
    )

    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = render_report(data, alerts, reference, raw.sources)
        report_path.write_text(report, encoding="utf-8", newline="\n")

    return PipelineResult(db_path, report_path, counts, data.issues, alerts)
