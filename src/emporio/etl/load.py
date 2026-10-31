"""Esquema do banco operacional e carga atômica."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from emporio.etl.transform import CleanData

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE categories (
    category_id   INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    slug          TEXT NOT NULL UNIQUE,
    description   TEXT
);

CREATE TABLE products (
    product_id            INTEGER PRIMARY KEY,
    name                  TEXT NOT NULL,
    category_id           INTEGER NOT NULL REFERENCES categories(category_id),
    price_cents           INTEGER NOT NULL CHECK (price_cents > 0),
    stock_quantity        INTEGER NOT NULL CHECK (stock_quantity >= 0),
    status                TEXT NOT NULL CHECK (status IN ('active', 'discontinued', 'coming_soon')),
    description           TEXT,
    description_reliable  INTEGER NOT NULL CHECK (description_reliable IN (0, 1)),
    specs_json            TEXT NOT NULL,
    created_at            TEXT NOT NULL,
    search_text           TEXT NOT NULL
);

CREATE TABLE promotions (
    promotion_id      INTEGER PRIMARY KEY,
    product_id        INTEGER NOT NULL REFERENCES products(product_id),
    discount_percent  INTEGER NOT NULL CHECK (discount_percent BETWEEN 1 AND 99),
    label             TEXT NOT NULL,
    is_active         INTEGER NOT NULL CHECK (is_active IN (0, 1))
);

-- Dados pessoais minimizados: sem nome completo, e-mail ou telefone em texto claro.
CREATE TABLE customers (
    customer_id  INTEGER PRIMARY KEY,
    first_name   TEXT NOT NULL,
    city         TEXT,
    email_fp     TEXT NOT NULL,
    phone_fp     TEXT NOT NULL
);

CREATE TABLE orders (
    order_id            INTEGER PRIMARY KEY,
    customer_id         INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date          TEXT NOT NULL,
    status              TEXT NOT NULL CHECK (
                            status IN ('pending', 'confirmed', 'shipped', 'delivered', 'cancelled')
                        ),
    total_cents         INTEGER NOT NULL CHECK (total_cents >= 0),
    payment_type        TEXT NOT NULL CHECK (payment_type IN ('pix', 'debit', 'credit', 'boleto')),
    installments        INTEGER NOT NULL CHECK (installments BETWEEN 1 AND 12),
    tracking_code       TEXT,
    estimated_delivery  TEXT,
    notes               TEXT
);

CREATE TABLE order_items (
    order_id    INTEGER NOT NULL REFERENCES orders(order_id),
    product_id  INTEGER NOT NULL REFERENCES products(product_id),
    quantity    INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, product_id)
);

-- Manual de políticas dividido por seção, para o RAG.
CREATE TABLE policy_chunks (
    section  TEXT PRIMARY KEY,
    title    TEXT NOT NULL,
    parent   TEXT,
    heading  TEXT NOT NULL,
    text     TEXT NOT NULL
);

CREATE TABLE data_quality_issues (
    issue_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    check_code  TEXT NOT NULL,
    severity    TEXT NOT NULL,
    entity      TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    detail      TEXT NOT NULL
);
CREATE INDEX idx_issues_entity ON data_quality_issues (entity, entity_id);

CREATE TABLE etl_metadata (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);

-- Visão do catálogo consumida pelas ferramentas do agente. Concentra as regras
-- de vitrine: o que pode ser vendido, qual promoção vale e qual descrição é segura.
CREATE VIEW v_catalog AS
WITH best_promotion AS (
    SELECT product_id, discount_percent, label,
           ROW_NUMBER() OVER (
               PARTITION BY product_id ORDER BY discount_percent DESC, promotion_id
           ) AS rank
    FROM promotions
    WHERE is_active = 1
),
base AS (
    SELECT p.*,
           c.name AS category_name,
           c.slug AS category_slug,
           (p.status = 'active' AND p.stock_quantity > 0) AS is_sellable,
           bp.discount_percent AS raw_discount,
           bp.label AS raw_promotion_label
    FROM products p
    JOIN categories c USING (category_id)
    LEFT JOIN best_promotion bp ON bp.product_id = p.product_id AND bp.rank = 1
)
SELECT product_id, name, category_id, category_name, category_slug,
       price_cents, stock_quantity, status, is_sellable,
       CASE WHEN description_reliable = 1 THEN description END AS description,
       specs_json, search_text,
       CASE WHEN is_sellable THEN raw_discount END AS discount_percent,
       CASE WHEN is_sellable THEN raw_promotion_label END AS promotion_label,
       CASE WHEN is_sellable AND raw_discount IS NOT NULL
            THEN CAST(ROUND(price_cents * (100 - raw_discount) / 100.0) AS INTEGER)
            ELSE price_cents
       END AS final_price_cents
FROM base;
"""

TABLE_ORDER = (
    "categories",
    "products",
    "promotions",
    "customers",
    "orders",
    "order_items",
    "policy_chunks",
)


def _insert(conn: sqlite3.Connection, table: str, rows: list[dict]) -> None:
    if not rows:
        return
    columns = list(rows[0])
    placeholders = ", ".join(f":{c}" for c in columns)
    conn.executemany(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})", rows)


def write_database(data: CleanData, db_path: Path, metadata: dict[str, object]) -> None:
    """Gera o banco num arquivo temporário e só então substitui o anterior.

    Se algo falhar no meio, o banco em uso pelo agente continua íntegro.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = db_path.with_suffix(db_path.suffix + ".tmp")
    tmp_path.unlink(missing_ok=True)

    conn = sqlite3.connect(tmp_path)
    try:
        conn.executescript(SCHEMA)
        with conn:
            for table in TABLE_ORDER:
                _insert(conn, table, getattr(data, table))
            conn.executemany(
                "INSERT INTO data_quality_issues (check_code, severity, entity, entity_id, detail)"
                " VALUES (?, ?, ?, ?, ?)",
                [
                    (i.check.code, i.check.severity.value, i.entity, i.entity_id, i.detail)
                    for i in data.issues
                ],
            )
            conn.executemany(
                "INSERT INTO etl_metadata (key, value) VALUES (?, ?)",
                [(k, json.dumps(v, ensure_ascii=False)) for k, v in metadata.items()],
            )
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"Violação de chave estrangeira após a carga: {violations[:5]}")
    finally:
        conn.close()
    os.replace(tmp_path, db_path)
