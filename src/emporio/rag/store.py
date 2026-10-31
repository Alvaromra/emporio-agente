"""Índice do manual carregado a partir do banco gerado pelo ETL."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from emporio.rag.retriever import BM25Index


@dataclass(frozen=True)
class StoredChunk:
    section: str
    heading: str
    text: str


@dataclass(frozen=True)
class PolicyIndex:
    chunks: dict[str, StoredChunk]
    bm25: BM25Index

    def search(self, query: str, k: int = 3) -> list[tuple[StoredChunk, float]]:
        return [(self.chunks[hit.key], hit.score) for hit in self.bm25.search(query, k)]


def document_text(heading: str, title: str, text: str) -> str:
    # O título entra duas vezes (no caminho e sozinho) para pesar mais no BM25.
    return f"{heading} {title} {text}"


@lru_cache(maxsize=4)
def _load(db_path: str, mtime: float) -> PolicyIndex:
    conn = sqlite3.connect(f"{Path(db_path).resolve().as_uri()}?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT section, title, heading, text FROM policy_chunks").fetchall()
    finally:
        conn.close()
    chunks = {s: StoredChunk(s, heading, text) for s, _, heading, text in rows}
    documents = {s: document_text(heading, title, text) for s, title, heading, text in rows}
    return PolicyIndex(chunks, BM25Index(documents))


def load_index(db_path: Path) -> PolicyIndex:
    """Carrega (e guarda em cache) o índice; recarrega se o ETL gerar um banco novo."""
    return _load(str(db_path), db_path.stat().st_mtime)
