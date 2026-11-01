"""Sobe a interface web: `python -m emporio.web` e abra http://localhost:8000.

python -m emporio.web --host 0.0.0.0   # acessível por outros aparelhos da rede local
"""

from __future__ import annotations

import argparse

import uvicorn

from emporio.web.app import create_app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m emporio.web")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    print(f"Empório da Música: abra http://localhost:{args.port} (API em /docs)")
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
