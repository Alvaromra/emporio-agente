"""Teste rápido do provedor, sem o agente completo.

    python -m emporio.llm --ping                         # o modelo responde?
    python -m emporio.llm "quanto custa o Takamine GD20?"  # qual ferramenta ele escolhe?

O segundo modo mostra a decisão de roteamento do modelo (ferramenta e argumentos) e
executa a ferramenta uma vez, para conferir a integração ponta a ponta.
"""

from __future__ import annotations

import argparse
import json
import time

from emporio.llm import LLMError, Message, get_provider
from emporio.tools import TOOLS, ToolContext, execute

SMOKE_SYSTEM = (
    "Você é o assistente virtual da Empório da Música, loja de instrumentos musicais em "
    "Campo Grande/MS. Use as ferramentas disponíveis para responder sobre produtos, "
    "pedidos e políticas. Responda em português do Brasil."
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m emporio.llm")
    parser.add_argument("pergunta", nargs="?")
    parser.add_argument("--ping", action="store_true")
    args = parser.parse_args(argv)

    try:
        provider = get_provider()
        print(f"Provedor: {provider.name} | modelo: {provider.model}")
        start = time.perf_counter()
        if args.ping or not args.pergunta:
            turn = provider.complete(
                "Responda apenas com a palavra: ok", [Message("user", "ping")], []
            )
            print(f"Resposta: {turn.text!r} ({time.perf_counter() - start:.1f}s)")
            return 0

        tools = list(TOOLS.values())
        history = [Message("user", args.pergunta)]
        turn = provider.complete(SMOKE_SYSTEM, history, tools)
        print(f"1ª chamada: {time.perf_counter() - start:.1f}s, tokens {turn.usage}")
        if not turn.tool_calls:
            print(f"O modelo respondeu sem ferramenta:\n{turn.text}")
            return 0
        history.append(turn.message)
        ctx = ToolContext.from_settings(session_id="smoke")
        for call in turn.tool_calls:
            print(
                f"Ferramenta escolhida: {call.name}"
                f"({json.dumps(call.arguments, ensure_ascii=False)})"
            )
            history.append(Message.tool_result(call, execute(call.name, call.arguments, ctx)))
        final = provider.complete(SMOKE_SYSTEM, history, tools)
        print(f"Resposta final ({time.perf_counter() - start:.1f}s no total):\n{final.text}")
        if final.tool_calls:
            print(
                f"(o modelo ainda pediu: {[c.name for c in final.tool_calls]}; "
                "o loop completo vem na etapa 07)"
            )
    except LLMError as error:
        print(f"Erro: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
