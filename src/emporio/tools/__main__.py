"""Chamada manual de ferramentas, útil para depurar sem LLM.

python -m emporio.tools                       # lista as ferramentas
python -m emporio.tools buscar_produtos '{"categoria": "violão", "preco_max": 1000}'
"""

from __future__ import annotations

import json
import sys

from emporio.tools import TOOLS, ToolContext, execute


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        for spec in TOOLS.values():
            params = ", ".join(spec.parameters["properties"]) or "-"
            print(f"{spec.name}({params})\n    {spec.description}\n")
        return 0
    name, raw = argv[0], (argv[1] if len(argv) > 1 else "{}")
    result = execute(name, json.loads(raw), ToolContext.from_settings())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if "erro" in result else 0


if __name__ == "__main__":
    raise SystemExit(main())
