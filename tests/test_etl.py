"""Testes do ETL contra os dados reais da loja.

Os números esperados vêm da análise manual dos CSVs; se a loja atualizar os
dados, estes testes apontam exatamente o que mudou.
"""

import shutil
import sqlite3
from datetime import date

import pytest

from emporio.config import PROJECT_ROOT
from emporio.etl import run_pipeline
from emporio.etl.extract import ContractError
from emporio.money import apply_discount
from emporio.privacy import fingerprint

RAW_DIR = PROJECT_ROOT / "data" / "raw"
PEPPER = "pepper-de-teste"
REFERENCE = date(2026, 10, 31)


@pytest.fixture(scope="module")
def etl(tmp_path_factory):
    out = tmp_path_factory.mktemp("etl")
    result = run_pipeline(
        raw_dir=RAW_DIR,
        db_path=out / "store.db",
        report_path=out / "relatorio.md",
        reference_date=REFERENCE,
        pepper=PEPPER,
    )
    conn = sqlite3.connect(result.db_path)
    yield result, conn
    conn.close()


def ids(conn, sql, *params):
    return {row[0] for row in conn.execute(sql, params)}


def issue_ids(conn, code):
    return ids(conn, "SELECT entity_id FROM data_quality_issues WHERE check_code = ?", code)


def test_contagens(etl):
    result, _ = etl
    assert result.counts == {
        "categories": 9,
        "products": 65,
        "promotions": 25,
        "customers": 50,
        "orders": 20,
        "order_items": 22,
        "policy_chunks": 25,
    }


def test_integridade_referencial(etl):
    _, conn = etl
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_dinheiro_em_centavos(etl):
    _, conn = etl
    assert conn.execute("SELECT price_cents FROM products WHERE product_id = 81").fetchone() == (
        59990,
    )


def test_status_prevalece_sobre_estoque(etl):
    _, conn = etl
    nao_vendaveis = ids(conn, "SELECT product_id FROM v_catalog WHERE NOT is_sellable")
    assert nao_vendaveis == {96, 113, 130, 136}


def test_apenas_promocoes_ativas_valem(etl):
    _, conn = etl
    com_desconto = ids(conn, "SELECT product_id FROM v_catalog WHERE discount_percent IS NOT NULL")
    assert com_desconto == {90, 94, 121, 127}
    preco = conn.execute(
        "SELECT price_cents, final_price_cents FROM v_catalog WHERE product_id = 121"
    ).fetchone()
    assert preco == (54900, 43920)  # R$ 549,00 com 20% -> R$ 439,20


def test_takamine_gd20_sem_promocao_vencida(etl):
    # Exemplo do próprio enunciado: há uma promoção de 12% para ele, mas inativa.
    _, conn = etl
    row = conn.execute(
        "SELECT discount_percent, final_price_cents FROM v_catalog WHERE product_id = 95"
    ).fetchone()
    assert row == (None, 219900)


def test_violoes_ate_mil_reais(etl):
    _, conn = etl
    encontrados = ids(
        conn,
        "SELECT product_id FROM v_catalog WHERE category_slug = 'violoes' AND is_sellable "
        "AND final_price_cents <= 100000",
    )
    assert len(encontrados) == 12
    assert not encontrados & {96, 113}  # sem estoque / fora de linha


def test_descricoes_contraditorias_sao_suprimidas(etl):
    _, conn = etl
    suprimidas = ids(conn, "SELECT product_id FROM v_catalog WHERE description IS NULL")
    assert suprimidas == {135, 136, 137, 139, 140, 142, 144}
    assert issue_ids(conn, "product.description_spec_conflict") == {
        "135",
        "137",
        "139",
        "140",
        "142",
    }


def test_correcao_explicita_de_nome(etl):
    _, conn = etl
    nome = conn.execute("SELECT name FROM products WHERE product_id = 84").fetchone()[0]
    assert nome == "Giannini GN-15 Nylon Cedro Natural"


def test_categorias_vazias(etl):
    _, conn = etl
    assert issue_ids(conn, "category.empty") == {"6", "7", "8"}


def test_pedidos_com_total_divergente(etl):
    _, conn = etl
    assert issue_ids(conn, "order.total_mismatch") == {"3", "20"}
    assert issue_ids(conn, "order.item_not_released") == {"3", "14"}


def test_pedidos_fora_das_regras_de_pagamento(etl):
    _, conn = etl
    assert issue_ids(conn, "order.installment_below_minimum") == {"9", "16", "18"}
    assert issue_ids(conn, "order.pix_discount_missing") == {"1", "5", "10", "13", "17"}


def test_preco_promocional_do_banco_bate_com_a_regra_em_python(etl):
    _, conn = etl
    rows = conn.execute(
        "SELECT price_cents, discount_percent, final_price_cents FROM v_catalog "
        "WHERE discount_percent IS NOT NULL"
    ).fetchall()
    assert rows
    for price, discount, final in rows:
        assert final == apply_discount(price, discount)


def test_forma_de_pagamento_decomposta(etl):
    _, conn = etl
    rows = conn.execute(
        "SELECT order_id, payment_type, installments FROM orders WHERE order_id IN (1, 2)"
    ).fetchall()
    assert rows == [(1, "pix", 1), (2, "credit", 6)]


def test_clientes_pseudonimizados(etl):
    _, conn = etl
    colunas = {row[1] for row in conn.execute("PRAGMA table_info(customers)")}
    assert colunas == {"customer_id", "first_name", "city", "email_fp", "phone_fp"}

    email_fp, phone_fp = conn.execute(
        "SELECT email_fp, phone_fp FROM customers WHERE customer_id = 1"
    ).fetchone()
    assert email_fp == fingerprint("email", " Lucas.Mendes@JMAIL.com", PEPPER)
    assert phone_fp == fingerprint("phone", "99812-3456", PEPPER)


def test_email_compartilhado_detectado(etl):
    _, conn = etl
    assert issue_ids(conn, "customer.shared_email") == {"11,43"}
    detalhe = conn.execute(
        "SELECT detail FROM data_quality_issues WHERE check_code = 'customer.shared_email'"
    ).fetchone()[0]
    assert "@" not in detalhe  # o relatório nunca expõe o contato


def test_alertas_operacionais(etl):
    result, _ = etl
    alertas = {a.order_id: a.situation for a in result.alerts}
    assert set(alertas) == {8, 9, 10, 11, 12, 13, 14, 15, 16}
    assert alertas[8] == "previsão de entrega vencida há 245 dias"


def test_relatorio_gerado(etl):
    result, _ = etl
    texto = result.report_path.read_text(encoding="utf-8")
    assert "## Achados e tratamento" in texto
    assert "## Alertas operacionais" in texto
    # Nenhum contato de cliente vaza para o relatório (o e-mail da loja pode aparecer).
    clientes = (RAW_DIR / "customers.csv").read_text(encoding="utf-8")
    emails = {linha.split(",")[3] for linha in clientes.splitlines()[1:]}
    assert not any(email in texto for email in emails)


def test_coluna_ausente_interrompe_com_erro_claro(tmp_path):
    raw = tmp_path / "raw"
    shutil.copytree(RAW_DIR, raw)
    products = raw / "products.csv"
    linhas = products.read_text(encoding="utf-8").splitlines()
    linhas[0] = linhas[0].replace("price_brl", "preco")
    products.write_text("\n".join(linhas), encoding="utf-8")

    with pytest.raises(ContractError, match="price_brl"):
        run_pipeline(raw_dir=raw, db_path=tmp_path / "x.db", report_path=None, pepper=PEPPER)
    assert not (tmp_path / "x.db").exists()  # nada é gravado se a origem estiver quebrada
