"""Leitura do manual de políticas (PDF) e divisão em trechos por seção.

O manual tem seções numeradas (1, 1.1, 4.2...). Cada seção vira um trecho: assim
uma regra nunca é cortada ao meio, como acontece com fatias de tamanho fixo, e a
resposta pode citar a seção exata. O título da seção-mãe acompanha o trecho para
dar contexto ("4. Política de Trocas e Devoluções > 4.2 Trocas por Defeito").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

PAGE_NOISE = (
    re.compile(r"^Empório da Música Manual de Políticas e Procedimentos$"),
    re.compile(r"^Página \d+$"),
    re.compile(r"^Empório da Música — Sua música começa aqui\.$"),
    re.compile(r"^Última atualização:"),
)
HEADING = re.compile(r"^(\d{1,2})(?:\.(\d{1,2}))?\.?\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ].{2,90})$")
NUMBERED_ITEM = re.compile(r"^\d{1,2}\.\s")

# Correções explícitas de erros do manual (docs/suposicoes.md, M9 e M10).
ERRATA = (
    (
        "contato@empóriodamusica.com.br",
        "contato@emporiodamusica.com.br",
        "e-mail com acento no domínio (M10)",
    ),
    (
        "(67) 3321-4500",
        "(67) 3341-4444",
        "número de WhatsApp divergente dos dados cadastrais (M9)",
    ),
)


@dataclass(frozen=True)
class PolicyChunk:
    section: str  # "4.2"
    title: str  # "Trocas por Defeito"
    parent: str | None  # "4. Política de Trocas e Devoluções"
    text: str

    @property
    def heading(self) -> str:
        own = f"{self.section} {self.title}" if self.parent else f"{self.section}. {self.title}"
        return f"{self.parent} > {own}" if self.parent else own


def extract_lines(pdf_path: Path) -> list[str]:
    """Texto do PDF linha a linha, sem cabeçalhos e rodapés de página."""
    lines: list[str] = []
    for page in PdfReader(pdf_path).pages:
        for raw in page.extract_text(extraction_mode="layout").splitlines():
            line = re.sub(r"\s+", " ", raw).strip()
            if any(pattern.match(line) for pattern in PAGE_NOISE):
                continue
            lines.append(line)
    return lines


def _section_key(major: int, minor: int | None) -> tuple[int, int]:
    return (major, minor or 0)


def _render(lines: list[str]) -> str:
    """Junta linhas quebradas em parágrafos, mantendo itens de lista separados."""
    blocks: list[str] = []
    current = ""
    for line in lines + [""]:
        starts_item = line.startswith("•") or NUMBERED_ITEM.match(line)
        if not line or starts_item:
            if current:
                blocks.append(current)
            current = ("- " + line.lstrip("• ").strip()) if line.startswith("•") else line
            continue
        current = f"{current} {line}" if current else line
    return "\n".join(blocks)


def split_sections(lines: list[str]) -> list[PolicyChunk]:
    """Divide o texto nas seções numeradas.

    Linhas como "1. Saudação: ..." dentro da seção 7.2 parecem títulos, mas são itens
    de lista: só é título o que avança a numeração (de 7.2 para 7.3 ou para 8).
    """
    chunks: list[PolicyChunk] = []
    current: tuple[str, str, str | None] | None = None
    body: list[str] = []
    last_key = (0, 0)
    major_titles: dict[int, str] = {}

    def flush() -> None:
        if current and (text := _render(body)):
            chunks.append(PolicyChunk(current[0], current[1], current[2], text))

    for line in lines:
        match = HEADING.match(line)
        if match:
            major, minor = int(match.group(1)), match.group(2)
            minor = int(minor) if minor else None
            key = _section_key(major, minor)
            is_next = key > last_key and (major == last_key[0] or major == last_key[0] + 1)
            if is_next:
                flush()
                title = match.group(3).strip()
                if minor is None:
                    major_titles[major] = f"{major}. {title}"
                    current = (str(major), title, None)
                else:
                    current = (f"{major}.{minor}", title, major_titles.get(major))
                body, last_key = [], key
                continue
        if current:  # texto antes da seção 1 (capa) é descartado
            body.append(line)
    flush()
    return chunks


def apply_errata(chunks: list[PolicyChunk]) -> tuple[list[PolicyChunk], list[tuple[str, str]]]:
    """Aplica as correções e devolve (trechos corrigidos, [(seção, descrição)])."""
    fixed: list[PolicyChunk] = []
    applied: list[tuple[str, str]] = []
    for chunk in chunks:
        text = chunk.text
        for wrong, right, reason in ERRATA:
            if wrong in text:
                text = text.replace(wrong, right)
                applied.append((chunk.section, f"{wrong!r} -> {right!r}: {reason}"))
        fixed.append(PolicyChunk(chunk.section, chunk.title, chunk.parent, text))
    return fixed, applied


def load_manual(pdf_path: Path) -> tuple[list[PolicyChunk], list[tuple[str, str]]]:
    return apply_errata(split_sections(extract_lines(pdf_path)))
