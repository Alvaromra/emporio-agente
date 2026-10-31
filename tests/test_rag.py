from emporio.config import PROJECT_ROOT
from emporio.rag.evaluate import evaluate, load_items
from emporio.rag.manual import load_manual
from emporio.rag.retriever import expand
from emporio.rag.store import load_index
from emporio.tools import execute

MANUAL = PROJECT_ROOT / "data" / "raw" / "politicas_da_loja.pdf"
EXPECTED_SECTIONS = [
    "1", "1.1", "1.2", "2", "3", "3.1", "4", "4.1", "4.2", "4.3", "4.4", "5.1", "5.2",
    "5.3", "6.1", "6.2", "7", "7.1", "7.2", "7.3", "8.1", "8.2", "8.3", "9", "10",
]  # fmt: skip


def test_manual_dividido_por_secao():
    chunks, _ = load_manual(MANUAL)
    assert [c.section for c in chunks] == EXPECTED_SECTIONS


def test_itens_numerados_nao_viram_secoes():
    # "1. Saudação", "2. Entendimento"... ficam dentro da 7.2.
    chunks = {c.section: c for c in load_manual(MANUAL)[0]}
    assert "1. Saudação" in chunks["7.2"].text
    assert chunks["1"].title == "Sobre a Empório da Música"


def test_contexto_da_secao_mae():
    chunks = {c.section: c for c in load_manual(MANUAL)[0]}
    assert chunks["4.2"].heading == "4. Política de Trocas e Devoluções > 4.2 Trocas por Defeito"
    assert chunks["9"].heading == "9. Privacidade e Proteção de Dados"


def test_secao_quebrada_entre_paginas_fica_inteira():
    chunks = {c.section: c for c in load_manual(MANUAL)[0]}
    assert "SEDEX (Correios) 2 a 5 dias úteis" in chunks["5.2"].text
    assert all("Página" not in c.text for c in chunks.values())


def test_errata_aplicada():
    chunks, applied = load_manual(MANUAL)
    texto = " ".join(c.text for c in chunks)
    assert "3321-4500" not in texto and "empóriodamusica" not in texto
    assert {section for section, _ in applied} == {"1.2", "7"}


def test_sinonimos_ligam_a_fala_do_cliente_ao_manual():
    termos = expand("me arrependi da compra")
    assert termos["arrependimento"] == 0.5
    assert "me" not in termos


def test_avaliacao_da_recuperacao(store_db):
    report = evaluate(load_index(store_db), load_items(), k=3)
    assert report.hit_at_k == report.total  # a seção certa sempre está entre as 3 primeiras
    assert report.hit_at_1 / report.total >= 0.9


def test_ferramenta_buscar_politicas(make_ctx):
    result = execute("buscar_politicas", {"pergunta": "me arrependi, posso devolver?"}, make_ctx())
    assert result["trechos"][0]["secao"] == "4.1"
    assert any("avaliar_troca_devolucao" in o for o in result["orientacoes"])


def test_diretrizes_internas_nao_devem_ser_recitadas(make_ctx):
    result = execute("buscar_politicas", {"pergunta": "tom de voz do atendimento"}, make_ctx())
    assert result["trechos"][0]["secao"] == "7.1"
    assert any("não as recite" in o for o in result["orientacoes"])


def test_pergunta_fora_do_manual(make_ctx):
    result = execute("buscar_politicas", {"pergunta": "qual a capital da França?"}, make_ctx())
    assert result["trechos"] == []
