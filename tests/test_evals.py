"""Testes da infraestrutura de avaliação (com modelo roteirizado, sem rede)."""

import json

import pytest

from emporio.evals import examples
from emporio.evals.runner import EvalSummary, check, load_scenarios, render_report, run_scenario
from emporio.llm import AssistantTurn, Message, ToolCall


def test_cenarios_bem_formados():
    keys = {
        "nome", "mensagens", "agora", "ferramentas", "ferramentas_algum", "ferramentas_proibidas",
        "sem_ferramentas", "contem", "contem_algum", "nao_contem",
    }  # fmt: skip
    scenarios = load_scenarios()
    assert len(scenarios) >= 10
    for s in scenarios:
        assert set(s) <= keys, s["nome"]
        assert s["mensagens"]


@pytest.mark.parametrize(
    ("scenario", "tools", "answer", "expected"),
    [
        ({"ferramentas": ["detalhar_produto"], "contem": ["2.199,00"]},
         ["detalhar_produto"], "Custa R$ 2.199,00", []),
        ({"ferramentas": ["detalhar_produto"]}, [], "x", ["não chamou detalhar_produto"]),
        ({"nao_contem": ["12%"]}, [], "tem 12% de desconto", ["continha '12%'"]),
        ({"contem_algum": ["expirou", "terminou"]}, [], "O prazo TERMINOU.", []),
        ({"sem_ferramentas": True}, ["buscar_produtos"], "x",
         ["chamou ferramentas sem necessidade: ['buscar_produtos']"]),
        ({"ferramentas_algum": ["a", "b"]}, ["c"], "x", ["não chamou nenhuma de ['a', 'b']"]),
    ],
)  # fmt: skip
def test_verificacoes(scenario, tools, answer, expected):
    assert check(scenario, tools, answer) == expected


class ScriptedModel:
    name, model = "roteiro", "teste"

    def complete(self, system, messages, tools):
        if messages[-1].role == "user":
            calls = [ToolCall("detalhar_produto", {"produto": "Takamine GD20"}, "a")]
            return AssistantTurn("", calls, Message("assistant", "", tool_calls=calls))
        return AssistantTurn("Custa R$ 2.199,00.", [], Message("assistant", "Custa R$ 2.199,00."))


@pytest.fixture
def real_data(store_db, settings_env):
    settings_env(EMPORIO_DB_PATH=str(store_db), EMPORIO_PII_PEPPER="pepper-de-teste")


def test_cenario_executado_de_ponta_a_ponta(real_data):
    scenario = {
        "nome": "GD20",
        "mensagens": ["Quanto custa o Takamine GD20?"],
        "ferramentas": ["detalhar_produto"],
        "contem": ["2.199,00"],
        "nao_contem": ["12%"],
    }
    outcome = run_scenario(ScriptedModel(), scenario)
    assert outcome.passed, outcome.failures
    report = render_report(EvalSummary("roteiro", "teste", [outcome]), "31/10/2026 10:30")
    assert "**1 de 1 cenários aprovados (100%)**" in report


def test_exemplos_gerados_a_partir_da_conversa(real_data, tmp_path, monkeypatch):
    spec = [{"arquivo": "x.md", "titulo": "Exemplo", "contexto": "Contexto.", "mensagens": ["oi"]}]
    source = tmp_path / "exemplos.json"
    source.write_text(json.dumps(spec), encoding="utf-8")
    monkeypatch.setattr(examples, "EXAMPLES_PATH", source)
    [path] = examples.generate(ScriptedModel(), output_dir=tmp_path / "conversas")
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Exemplo")
    assert "**Cliente:** oi" in text and "**Tom:** Custa R$ 2.199,00." in text
    assert "`detalhar_produto(" in text and "Horário simulado: 2026-10-31 às 10:30" in text
