import sqlite3

import pytest

from emporio.tools import ToolError, VerificationGuard, execute


def consultar(ctx, pedido, contato=None):
    args = {"numero_pedido": pedido}
    if contato:
        args["email_ou_telefone"] = contato
    return execute("consultar_pedido", args, ctx)


def test_consulta_com_email_correto(make_ctx):
    result = consultar(make_ctx(), 1, "Pedro.Oliveira@JMAIL.com")
    assert result["verificado"]
    assert result["cliente"] == "Pedro"  # só o primeiro nome
    assert result["status"] == "entregue"
    assert result["total"] == "R$ 11.499,00"


def test_consulta_com_telefone_sem_ddd(make_ctx):
    assert consultar(make_ctx(), 8, "99654-7821")["cliente"] == "Ana"


def test_falha_nao_revela_se_o_pedido_existe(make_ctx):
    contato_errado = consultar(make_ctx(), 1, "outra.pessoa@jmail.com")
    pedido_inexistente = consultar(make_ctx(), 999, "pedro.oliveira@jmail.com")
    assert contato_errado == pedido_inexistente
    assert "Não foi possível confirmar" in contato_errado["erro"]


def test_sem_contato_pede_o_dado(make_ctx):
    assert "peça o e-mail ou o telefone" in consultar(make_ctx(), 1)["erro"]


def test_bloqueio_apos_tres_falhas(make_ctx):
    guard = VerificationGuard()
    ctx = make_ctx(guard=guard)
    for _ in range(3):
        consultar(ctx, 1, "errado@x.com")
    result = consultar(ctx, 1, "pedro.oliveira@jmail.com")  # mesmo com o dado certo
    assert "Limite de tentativas" in result["erro"]
    # Outra conversa não é afetada.
    assert consultar(make_ctx(session_id="outra", guard=guard), 1, "pedro.oliveira@jmail.com")[
        "verificado"
    ]


def test_pedido_verificado_dispensa_repetir_contato(make_ctx):
    ctx = make_ctx(guard=VerificationGuard())
    consultar(ctx, 1, "pedro.oliveira@jmail.com")
    assert consultar(ctx, 1)["verificado"]


def test_email_compartilhado_exige_telefone(make_ctx):
    # O e-mail do cliente 11 (dono do pedido 10) também está no cadastro 43.
    assert "telefone" in consultar(make_ctx(), 10, "bruno.martins@jmail.com")["erro"]
    assert consultar(make_ctx(), 10, "(67) 98543-2109")["verificado"]


def test_pedido_atrasado_traz_alerta_e_orientacao(make_ctx):
    result = consultar(make_ctx(), 8, "99654-7821")
    assert result["alerta"] == "Previsão de entrega vencida há 245 dias."
    assert result["rastreamento"]["codigo"] == "BRJL5544332BR"
    assert any("encaminhar para a equipe" in o for o in result["orientacoes_ao_agente"])


def test_pedido_com_produto_nao_lancado(make_ctx):
    # Pedido 14 (cliente 13, Diego) contém um produto "em breve".
    result = consultar(make_ctx(), 14, "diego.castro@coldmail.com")
    assert any("não prometa prazo" in o for o in result["orientacoes_ao_agente"])


def test_pedido_cancelado_mostra_motivo(make_ctx):
    result = consultar(make_ctx(), 17, "matheus.correia@hayoo.com.br")
    assert result["status"] == "cancelado"
    assert "cancelado pelo cliente" in result["nota_do_pedido"]


def test_arrependimento_fora_do_prazo(make_ctx):
    result = execute(
        "avaliar_troca_devolucao",
        {"numero_pedido": 1, "motivo": "arrependimento", "email_ou_telefone": "98432-1098"},
        make_ctx(),
    )
    assert result["elegivel"] is False
    assert "4.1" in result["secoes_do_manual"]


def test_arrependimento_dentro_do_prazo(make_ctx):
    result = execute(
        "avaliar_troca_devolucao",
        {"numero_pedido": 1, "motivo": "arrependimento", "email_ou_telefone": "98432-1098"},
        make_ctx(now="2025-10-28T10:00"),
    )
    assert result["elegivel"] is True
    assert (result["prazo_final"], result["dias_restantes"]) == ("01/11/2025", 4)


def test_motivo_invalido(make_ctx):
    result = execute(
        "avaliar_troca_devolucao",
        {"numero_pedido": 1, "motivo": "nao gostei", "email_ou_telefone": "98432-1098"},
        make_ctx(),
    )
    assert "deve ser um de" in result["erro"]


def test_ferramentas_usam_conexao_somente_leitura(make_ctx):
    with pytest.raises(sqlite3.OperationalError), make_ctx().connect() as conn:
        conn.execute("DELETE FROM orders")


def test_banco_ausente_gera_erro_claro(make_ctx, tmp_path):
    ctx = make_ctx()
    ctx.db_path = tmp_path / "nao_existe.db"
    with pytest.raises(ToolError, match="emporio.etl"):
        ctx.connect()
