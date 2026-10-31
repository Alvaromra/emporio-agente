from emporio.tools import execute


def test_loja_aberta_no_sabado_de_manha(make_ctx):
    result = execute("status_da_loja", {}, make_ctx())
    assert result["situacao"] == "Aberta agora, até as 13:00."
    assert result["telefone_whatsapp"] == "(67) 3341-4444"


def test_loja_fechada_em_feriado(make_ctx):
    result = execute("status_da_loja", {}, make_ctx(now="2026-11-02T10:00"))
    assert result["feriado_hoje"] == "Finados"
    assert "Reabre amanhã às 09:00" in result["situacao"]


def test_frete_local(make_ctx):
    result = execute(
        "consultar_frete", {"cidade": "Campo Grande", "valor_pedido": 599.9}, make_ctx()
    )
    assert result["entrega_local"]
    assert result["condicoes"][0].startswith("Frete grátis")


def test_frete_para_outra_cidade(make_ctx):
    result = execute("consultar_frete", {"cidade": "Dourados"}, make_ctx())
    assert not result["entrega_local"]
    assert any("CEP" in linha for linha in result["condicoes"])
