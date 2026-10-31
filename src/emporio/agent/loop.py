"""O agente: recebe a mensagem, conversa com o modelo e executa as ferramentas.

Fluxo de uma mensagem:
1. Dados pessoais da mensagem viram marcadores (pii.py).
2. O modelo recebe o histórico, a persona e as ferramentas.
3. Se pedir ferramentas, o agente troca os marcadores pelos valores reais, executa,
   devolve os resultados e chama o modelo de novo. No máximo MAX_STEPS rodadas.
4. A resposta final passa pelos guardrails: todo valor em R$ precisa ter vindo de
   uma ferramenta (ou do próprio cliente). Se não veio, o modelo recebe uma chance
   de corrigir; se insistir, a resposta é trocada por uma mensagem segura.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from emporio import clock
from emporio.agent import guardrails
from emporio.agent.pii import PiiVault
from emporio.agent.prompt import build_system_prompt
from emporio.config import get_settings
from emporio.llm import LLMProvider, Message
from emporio.tools import TOOLS, Tool, ToolContext, VerificationGuard, execute
from emporio.tools.base import InMemoryHandoffs

MAX_STEPS = 6
MAX_CORRECTIONS = 1
HISTORY_USER_TURNS = 12


@dataclass
class Session:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    history: list[Message] = field(default_factory=list)
    vault: PiiVault = field(default_factory=PiiVault)


@dataclass(frozen=True)
class ToolTrace:
    name: str
    arguments: dict  # com marcadores, nunca com dados pessoais
    ok: bool
    elapsed_ms: int


@dataclass
class AgentReply:
    text: str
    tools: list[ToolTrace] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=lambda: {"entrada": 0, "saida": 0})
    elapsed_s: float = 0.0


def window(history: list[Message], user_turns: int = HISTORY_USER_TURNS) -> list[Message]:
    """Últimas N trocas. O corte acontece sempre numa mensagem do cliente, para nunca
    separar um pedido de ferramenta da sua resposta."""
    starts = [i for i, m in enumerate(history) if m.role == "user" and not m.internal]
    if len(starts) <= user_turns:
        return history
    return history[starts[-user_turns] :]


class Agent:
    def __init__(
        self,
        provider: LLMProvider,
        tools: list[Tool] | None = None,
        db_path=None,
        pepper: str | None = None,
        handoffs=None,
    ):
        settings = get_settings()
        self.provider = provider
        self.tools = tools if tools is not None else list(TOOLS.values())
        self.db_path = db_path or settings.db_path
        self.pepper = pepper or settings.pii_pepper
        self.guard = VerificationGuard()  # compartilhado entre conversas, indexado por sessão
        self.handoffs = handoffs or InMemoryHandoffs()

    def _context(self, session: Session) -> ToolContext:
        return ToolContext(
            db_path=self.db_path,
            now=clock.now(),
            pepper=self.pepper,
            session_id=session.id,
            guard=self.guard,
            handoffs=self.handoffs,
        )

    def reply(self, session: Session, user_text: str) -> AgentReply:
        started = time.perf_counter()
        result = AgentReply(text="")
        session.history.append(Message("user", session.vault.redact(user_text)))
        system = build_system_prompt(clock.now())
        corrections = 0

        for _ in range(MAX_STEPS):
            turn = self.provider.complete(system, window(session.history), self.tools)
            for key, value in turn.usage.items():
                result.usage[key] = result.usage.get(key, 0) + value
            session.history.append(turn.message)

            if turn.tool_calls:
                ctx = self._context(session)
                for call in turn.tool_calls:
                    t0 = time.perf_counter()
                    output = execute(call.name, session.vault.restore(call.arguments), ctx)
                    result.tools.append(
                        ToolTrace(
                            call.name,
                            call.arguments,
                            "erro" not in output,
                            int((time.perf_counter() - t0) * 1000),
                        )
                    )
                    session.history.append(Message.tool_result(call, output))
                continue

            text = guardrails.sanitize(turn.text)
            ungrounded = guardrails.ungrounded_amounts(text, session.history)
            if ungrounded and corrections < MAX_CORRECTIONS:
                corrections += 1
                turn.message.internal = True  # a resposta reprovada não aparece ao cliente
                result.events.append("valor sem fonte: modelo instruído a corrigir")
                session.history.append(
                    Message("user", guardrails.correction_request(ungrounded), internal=True)
                )
                continue
            if ungrounded:
                result.events.append("valor sem fonte após correção: resposta substituída")
                text = guardrails.FALLBACK_UNGROUNDED
            if not text:
                result.events.append("resposta vazia")
                text = guardrails.FALLBACK_EMPTY
            if text != turn.text:
                turn.message.content = text
                turn.message.raw = None  # o histórico passa a refletir o texto entregue
            result.text = session.vault.restore(text)
            break
        else:
            result.events.append(f"limite de {MAX_STEPS} rodadas atingido")
            result.text = guardrails.FALLBACK_LOOP
            session.history.append(Message("assistant", result.text))

        result.elapsed_s = round(time.perf_counter() - started, 2)
        return result
