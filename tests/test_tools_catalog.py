from emporio.tools import TOOLS, execute


def run(make_ctx, name, **args):
    return execute(name, args, make_ctx())


def ids(result):
    return [p["id"] for p in result["produtos"]]


def test_violoes_ate_mil_reais(make_ctx):
    result = run(make_ctx, "buscar_produtos", categoria="violões", preco_max=1000)
    assert result["total_encontrado"] == 12
    assert result["filtros_aplicados"]["categoria"] == "Violões"
    assert 96 not in ids(result) and 113 not in ids(result)  # esgotado / fora de linha
    assert result["indisponiveis_ocultos"] == 2
    assert "orientacao" in result  # 12 resultados, limite padrão de 5


def test_preco_vindo_como_texto_e_aceito(make_ctx):
    result = run(make_ctx, "buscar_produtos", categoria="violão", preco_max="1000")
    assert result["total_encontrado"] == 12


def test_busca_por_modelo_com_erro_de_digitacao(make_ctx):
    assert ids(run(make_ctx, "buscar_produtos", termo="takamini gd 20"))[0] == 95


def test_busca_por_marca_dentro_da_categoria(make_ctx):
    result = run(make_ctx, "buscar_produtos", termo="violão yamaha")
    nomes = [p["nome"] for p in result["produtos"]]
    assert nomes and all("Yamaha" in n for n in nomes)


def test_categoria_sem_produtos_nao_inventa(make_ctx):
    result = run(make_ctx, "buscar_produtos", categoria="saxofone")
    assert result["produtos"] == []
    assert "não há nenhum produto cadastrado" in result["aviso"]


def test_acessorio_fora_do_escopo(make_ctx):
    result = run(make_ctx, "buscar_produtos", termo="palhetas")
    assert result["produtos"] == []
    assert "exclusivamente com instrumentos" in result["aviso_escopo"]


def test_violao_de_7_cordas_nao_e_acessorio(make_ctx):
    assert "aviso_escopo" not in run(make_ctx, "buscar_produtos", termo="violão 7 cordas")


def test_detalhe_takamine_gd20_sem_promocao_vencida(make_ctx):
    result = run(make_ctx, "detalhar_produto", produto="Takamine GD20")
    assert result["id"] == 95
    assert result["preco"] == "R$ 2.199,00"
    assert "desconto" not in result
    assert "PIX à vista: R$ 2.089,05 (5% de desconto)" in result["pagamento"]


def test_detalhe_com_promocao_mostra_original_e_percentual(make_ctx):
    result = run(make_ctx, "detalhar_produto", produto="Ohana CK-20")
    assert (result["preco"], result["preco_original"], result["desconto"]) == (
        "R$ 439,20",
        "R$ 549,00",
        "20%",
    )
    assert any("não se aplica a preços promocionais" in linha for linha in result["pagamento"])


def test_produto_esgotado_traz_alternativas(make_ctx):
    result = run(make_ctx, "detalhar_produto", produto="Giannini GF-3D")
    assert result["disponibilidade"] == "esgotado no momento"
    assert "pagamento" not in result
    assert len(result["alternativas"]) == 3
    assert all(a["disponibilidade"].startswith("disponível") for a in result["alternativas"])


def test_produto_fora_de_linha_por_id(make_ctx):
    result = run(make_ctx, "detalhar_produto", produto="136")
    assert result["disponibilidade"].startswith("fora de linha")


def test_descricao_contraditoria_nao_chega_ao_agente(make_ctx):
    result = run(make_ctx, "detalhar_produto", produto="Music Man Bass 1X")
    assert result["descricao"] is None
    assert "Fender" not in str(result)
    assert "orientacao_descricao" in result


def test_especificacoes_traduzidas(make_ctx):
    specs = run(make_ctx, "detalhar_produto", produto="Yamaha F310")["especificacoes"]
    assert specs["cordas"] == "aço" and specs["captação"] == "não"


def test_nome_ambiguo_pede_confirmacao(make_ctx):
    result = run(make_ctx, "detalhar_produto", produto="Martin")
    assert result["ambiguo"]
    assert {c["id"] for c in result["candidatos"]} == {93, 108}


def test_modelo_especifico_desfaz_ambiguidade(make_ctx):
    assert run(make_ctx, "detalhar_produto", produto="Martin D-28E")["id"] == 108


def test_produto_inexistente(make_ctx):
    assert "erro" in run(make_ctx, "detalhar_produto", produto="Stradivarius")


def test_promocoes_vigentes(make_ctx):
    result = run(make_ctx, "listar_promocoes")
    assert {p["id"] for p in result["promocoes_ativas"]} == {90, 94, 121, 127}
    assert all("preco_original" in p for p in result["promocoes_ativas"])


def test_todas_as_ferramentas_tem_schema_valido():
    for spec in TOOLS.values():
        params = spec.parameters
        assert params["type"] == "object"
        assert set(params["required"]) <= set(params["properties"])
        assert spec.description and len(spec.description) < 1024


def test_ferramenta_desconhecida_e_parametro_faltando(make_ctx):
    assert "erro" in execute("apagar_tudo", {}, make_ctx())
    assert "obrigatórios" in execute("detalhar_produto", {}, make_ctx())["erro"]
