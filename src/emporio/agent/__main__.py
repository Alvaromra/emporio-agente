"""Conversa com o agente pelo terminal.

    python -m emporio.agent                 # modo interativo
    python -m emporio.agent --trace         # mostra as ferramentas chamadas
    python -m emporio.agent "oi, vocês estão abertos?"   # uma pergunta só
    python -m emporio.agent --sessao ID     # retoma uma conversa salva
    python -m emporio.agent --efemero       # não salva a conversa

Comandos no modo interativo: /trace (liga/desliga), /nova (nova conversa), /sair.
"""

from __future__ import annotations

import argparse
import contextlib
import json

# Habilita setas e histórico no input(). Não existe no Windows, onde é dispensável.
with contextlib.suppress(ImportError):
    import readline  # noqa: F401

from emporio.agent import Agent, AgentReply
from emporio.agent.prompt import AGENT_NAME
from emporio.config import get_settings
from emporio.llm import LLMError, get_provider
from emporio.memory import ConversationStore


def show(reply: AgentReply, trace: bool) -> None:
    if trace:
        for t in reply.tools:
            status = "ok" if t.ok else "erro"
            args = json.dumps(t.arguments, ensure_ascii=False)
            print(f"   · {t.name}({args}) [{status}, {t.elapsed_ms} ms]")
        for event in reply.events:
            print(f"   ! {event}")
        print(f"   ({reply.elapsed_s}s, tokens {reply.usage})")
    print(f"{AGENT_NAME}: {reply.text}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m emporio.agent")
    parser.add_argument("mensagem", nargs="?")
    parser.add_argument("--trace", action="store_true")
    parser.add_argument("--sessao", metavar="ID", help="retoma uma conversa salva")
    parser.add_argument("--efemero", action="store_true", help="não salva a conversa")
    args = parser.parse_args(argv)

    store = None if args.efemero else ConversationStore(get_settings().app_db_path)
    try:
        agent = Agent(get_provider(), store=store)
    except LLMError as error:
        print(f"Erro: {error}")
        return 1
    trace = args.trace
    if args.sessao:
        session = agent.resume(args.sessao)
        if session is None:
            print(f"Conversa {args.sessao} não encontrada.")
            return 1
    else:
        session = agent.new_session("cli")

    if args.mensagem:
        show(agent.reply(session, args.mensagem), trace)
        return 0

    print(f"Empório da Música | {agent.provider.name}: {agent.provider.model}")
    if store:
        print(f"Conversa: {session.id} (salva em {store.path.name})")
    print("Comandos: /trace, /nova, /sair\n")
    while True:
        try:
            text = input("Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not text:
            continue
        if text == "/sair":
            return 0
        if text == "/trace":
            trace = not trace
            print(f"(trace {'ligado' if trace else 'desligado'})\n")
            continue
        if text == "/nova":
            session = agent.new_session("cli")
            print(f"(nova conversa: {session.id})\n")
            continue
        try:
            show(agent.reply(session, text), trace)
        except LLMError as error:
            print(f"(erro do modelo: {error})\n")


if __name__ == "__main__":
    raise SystemExit(main())
