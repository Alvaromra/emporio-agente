"""Leitura dos CSVs com validação do contrato de colunas."""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path

Row = dict[str, str]

EXPECTED_COLUMNS: dict[str, tuple[str, ...]] = {
    "categories": ("category_id", "name", "description"),
    "products": (
        "product_id", "price_brl", "name", "category_id", "description",
        "stock_quantity", "status", "specs", "created_at",
    ),
    "promotions": ("promotion_id", "product_id", "discount_percent", "description", "is_active"),
    "customers": ("customer_id", "name", "phone", "email", "city"),
    "orders": (
        "order_id", "customer_id", "order_date", "status", "total_brl", "payment_method",
        "tracking_code", "estimated_delivery", "notes",
    ),
    "order_items": ("order_id", "quantity", "product_id"),
}  # fmt: skip


class ContractError(ValueError):
    """Os arquivos de origem violam o formato esperado."""


@dataclass(frozen=True)
class RawData:
    tables: dict[str, list[Row]]
    sources: dict[str, str]  # nome do arquivo -> SHA-256
    manual_path: Path


def find_table_file(raw_dir: Path, table: str) -> Path:
    """Aceita tanto `products.csv` quanto o nome original `..._products.csv`."""
    candidates = sorted(
        path
        for path in raw_dir.glob("*.csv")
        if path.name == f"{table}.csv" or path.name.endswith(f"_{table}.csv")
    )
    if len(candidates) != 1:
        found = ", ".join(p.name for p in candidates) or "nenhum"
        raise ContractError(f"Esperava 1 arquivo para '{table}' em {raw_dir}, achei: {found}")
    return candidates[0]


def read_table(path: Path, expected: tuple[str, ...]) -> list[Row]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = tuple(reader.fieldnames or ())
        missing = [col for col in expected if col not in columns]
        if missing:
            raise ContractError(f"{path.name}: colunas ausentes {missing}")
        return [{col: (row.get(col) or "").strip() for col in expected} for row in reader]


def find_manual(raw_dir: Path) -> Path:
    candidates = sorted(raw_dir.glob("*.pdf"))
    if len(candidates) != 1:
        found = ", ".join(p.name for p in candidates) or "nenhum"
        raise ContractError(f"Esperava 1 PDF de políticas em {raw_dir}, achei: {found}")
    return candidates[0]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(raw_dir: Path) -> RawData:
    tables: dict[str, list[Row]] = {}
    sources: dict[str, str] = {}
    for table, expected in EXPECTED_COLUMNS.items():
        path = find_table_file(raw_dir, table)
        tables[table] = read_table(path, expected)
        sources[path.name] = sha256(path)
    manual = find_manual(raw_dir)
    sources[manual.name] = sha256(manual)
    return RawData(tables=tables, sources=sources, manual_path=manual)
