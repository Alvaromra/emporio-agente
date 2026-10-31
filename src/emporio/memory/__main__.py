"""Administração das conversas guardadas.

python -m emporio.memory                          # últimas conversas
python -m emporio.memory --mostrar ID             # uma conversa em Markdown
python -m emporio.memory --exportar ID arquivo.md # salva a conversa em arquivo
python -m emporio.memory --encaminhamentos        # protocolos em aberto
python -m emporio.memory --apagar ID              # exclusão a pedido do cliente
python -m emporio.memory --purgar                 # aplica o prazo de retenção
"""

from __future__ import annotations

import argparse
from pathlib import Path

from emporio import clock
from emporio.config import get_settings
from emporio.memory.export import to_markdown
from emporio.memory.store import ConversationStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m emporio.memory")
    parser.add_argument("--mostrar", metavar="ID")
    parser.add_argument("--exportar", nargs=2, metavar=("ID", "ARQUIVO"))
    parser.add_argument("--titulo", default="Conversa com o agente")
    parser.add_argument("--encaminhamentos", action="store_true")
    parser.add_argument("--apagar", metavar="ID")
    parser.add_argument("--purgar", action="store_true")
    args = parser.parse_args(argv)

    settings = get_settings()
    store = ConversationStore(settings.app_db_path)

    if args.mostrar:
        print(to_markdown(store.load(args.mostrar), args.titulo))
    elif args.exportar:
        session_id, target = args.exportar
        Path(target).write_text(to_markdown(store.load(session_id), args.titulo), encoding="utf-8")
        print(f"Conversa exportada para {target}")
    elif args.encaminhamentos:
        for h in store.list_handoffs():
            pedido = f" | pedido {h['order_id']}" if h["order_id"] else ""
            print(f"{h['protocol']} | {h['reason']}{pedido} | {h['summary']}")
    elif args.apagar:
        print("Conversa apagada." if store.delete_session(args.apagar) else "Não encontrada.")
    elif args.purgar:
        removed = store.purge(settings.retention_days, clock.now())
        print(f"{removed} conversa(s) com mais de {settings.retention_days} dias apagada(s).")
    else:
        for s in store.list_sessions():
            print(f"{s.session_id} | {s.channel} | {s.updated_at[:16]} | {s.messages} mensagens")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
