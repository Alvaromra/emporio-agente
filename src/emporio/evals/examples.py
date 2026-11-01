"""Gera as conversas de exemplo do repositório a partir de conversas reais com o modelo.

Cada conversa roda com o agente de verdade, é salva num banco temporário e exportada em
Markdown pelo mesmo código de `python -m emporio.memory --exportar`. Nada é escrito à
mão: o que aparece nos exemplos é o que o modelo respondeu.
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from emporio.agent import Agent
from emporio.config import PROJECT_ROOT
from emporio.evals.runner import DEFAULT_NOW, frozen_time
from emporio.llm import LLMProvider
from emporio.memory import ConversationStore
from emporio.memory.export import to_markdown

EXAMPLES_PATH = PROJECT_ROOT / "evals" / "exemplos.json"
OUTPUT_DIR = PROJECT_ROOT / "docs" / "conversas"

NOTE = (
    "> E-mails e telefones aparecem como marcadores (`[EMAIL_1]`, `[TELEFONE_1]`) porque o\n"
    "> histórico nunca guarda o dado pessoal: o cliente viu o próprio contato na tela, mas\n"
    "> o modelo e o banco só conhecem o marcador. As linhas com 🔧 mostram as ferramentas\n"
    "> que o agente consultou antes de responder.\n"
)


def generate(
    provider: LLMProvider,
    pause_s: float = 0,
    output_dir: Path = OUTPUT_DIR,
    on_written=None,
) -> list[Path]:
    examples = json.loads(EXAMPLES_PATH.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    with tempfile.TemporaryDirectory() as tmp:
        store = ConversationStore(Path(tmp) / "exemplos.db")
        for example in examples:
            moment = example.get("agora", DEFAULT_NOW)
            with frozen_time(moment):
                agent = Agent(provider, store=store)
                session = agent.new_session("exemplo")
                for message in example["mensagens"]:
                    agent.reply(session, message)
                    time.sleep(pause_s)
            body = to_markdown(store.load(session.id), example["titulo"])
            header, _, conversation = body.partition("\n\n")
            day, hour = moment.split("T")
            context = (
                f"{example['contexto']}\n\n*Horário simulado: {day} às {hour}, em Campo Grande.*\n"
            )
            target = output_dir / example["arquivo"]
            target.write_text(f"{header}\n\n{context}\n{NOTE}\n{conversation}", encoding="utf-8")
            written.append(target)
            if on_written:
                on_written(target)  # avisa a cada arquivo: um erro depois não apaga o progresso
    return written
