from datetime import date

from emporio.rules.returns import Reason, assess_return

DELIVERED = {"status": "delivered", "order_date": "2025-10-15", "estimated_delivery": "2025-10-25"}


def test_arrependimento_dentro_do_prazo():
    result = assess_return(DELIVERED, Reason.ARREPENDIMENTO, today=date(2025, 10, 28))
    assert result.eligible
    assert result.deadline == date(2025, 11, 1)
    assert result.days_left == 4
    assert any("frete de devolução" in step for step in result.next_steps)


def test_arrependimento_no_ultimo_dia_ainda_vale():
    assert assess_return(DELIVERED, "arrependimento", today=date(2025, 11, 1)).eligible


def test_arrependimento_fora_do_prazo():
    result = assess_return(DELIVERED, Reason.ARREPENDIMENTO, today=date(2026, 10, 31))
    assert not result.eligible
    assert result.days_left is None


def test_defeito_dentro_de_30_dias_da_compra():
    result = assess_return(DELIVERED, Reason.DEFEITO, today=date(2025, 11, 14))
    assert result.eligible
    assert result.deadline == date(2025, 11, 14)


def test_defeito_depois_de_30_dias_cai_na_garantia_legal():
    result = assess_return(DELIVERED, Reason.DEFEITO, today=date(2025, 12, 1))
    assert not result.eligible
    assert "garantia legal" in result.summary
    assert result.deadline == date(2026, 1, 23)  # 90 dias após o recebimento


def test_defeito_depois_da_garantia_legal_vai_para_o_fabricante():
    result = assess_return(DELIVERED, Reason.DEFEITO, today=date(2026, 10, 31))
    assert "fabricante" in result.summary
    assert result.deadline is None


def test_troca_por_preferencia():
    result = assess_return(DELIVERED, Reason.PREFERENCIA, today=date(2025, 10, 30))
    assert result.eligible
    assert any("disponibilidade" in c for c in result.conditions)


def test_pedido_em_transporte_ainda_nao_pode_ser_devolvido():
    order = {"status": "shipped", "order_date": "2026-02-15", "estimated_delivery": "2026-02-28"}
    result = assess_return(order, Reason.ARREPENDIMENTO, today=date(2026, 2, 20))
    assert not result.eligible
    assert "transporte" in result.summary


def test_pedido_cancelado():
    order = {"status": "cancelled", "order_date": "2026-01-28", "estimated_delivery": None}
    assert not assess_return(order, Reason.DEFEITO, today=date(2026, 2, 1)).eligible
