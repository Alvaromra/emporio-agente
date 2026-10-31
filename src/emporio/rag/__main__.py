"""Busca no manual e avaliação da recuperação.

python -m emporio.rag "posso devolver um produto?"   # mostra os trechos
python -m emporio.rag --eval                           # roda evals/politicas.jsonl
"""

from __future__ import annotations

import argparse

from emporio.config import get_settings
from emporio.rag.evaluate import evaluate, load_items
from emporio.rag.store import load_index


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m emporio.rag")
    parser.add_argument("pergunta", nargs="?")
    parser.add_argument("--eval", action="store_true", help="avalia a recuperação")
    parser.add_argument("-k", type=int, default=3)
    args = parser.parse_args(argv)

    index = load_index(get_settings().db_path)
    if args.eval:
        report = evaluate(index, load_items(), k=args.k)
        print(report.summary())
        for question, expected, found in report.misses:
            print(f"  fora do topo: {question!r} esperado {sorted(expected)}, veio {found}")
        return 0
    if not args.pergunta:
        parser.error("informe uma pergunta ou --eval")
    for chunk, score in index.search(args.pergunta, args.k):
        print(f"[{score:.2f}] {chunk.heading}\n{chunk.text}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
