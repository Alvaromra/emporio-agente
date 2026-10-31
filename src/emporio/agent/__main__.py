"""Conversa com o agente pelo terminal.

    python -m emporio.agent                 # modo interativo
    python -m emporio.agent --trace         # mostra as ferramentas chamadas
    python -m emporio.agent "oi, vocês estão abertos?"   # uma pergunta só

Comandos no modo interativo: /trace (liga/desliga), /nova (nova conversa), /sair.
"""

from __future__ import annotations

import argparse
import json

from emporio.agent import Agent, AgentReply, Session
from emporio.agent.prompt import AGENT_NAME
from emporio.llm import LLMError, get_provider


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
    args = parser.parse_args(argv)

    try:
        agent = Agent(get_provider())
    except LLMError as error:
        print(f"Erro: {error}")
        return 1
    session, trace = Session(), args.trace

    if args.mensagem:
        show(agent.reply(session, args.mensagem), trace)
        return 0

    print(f"Empório da Música | {agent.provider.name}: {agent.provider.model}")
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
            session = Session()
            print("(nova conversa)\n")
            continue
        try:
            show(agent.reply(session, text), trace)
        except LLMError as error:
            print(f"(erro do modelo: {error})\n")


if __name__ == "__main__":
    raise SystemExit(main())
