import pytest

from emporio.money import apply_discount, format_brl
from emporio.rules.payments import (
    combined_payment_allowed,
    installment_plan,
    is_installment_allowed,
    max_installments,
    payment_options,
    pix_price,
)


@pytest.mark.parametrize(
    ("cents", "text"),
    [(59990, "R$ 599,90"), (1234567, "R$ 12.345,67"), (5, "R$ 0,05"), (-4800, "-R$ 48,00")],
)
def test_format_brl(cents, text):
    assert format_brl(cents) == text


def test_desconto_arredonda_ao_centavo():
    assert apply_discount(219900, 5) == 208905  # R$ 2.199,00 no PIX -> R$ 2.089,05
    assert apply_discount(239900, 18) == 196718


@pytest.mark.parametrize(
    ("price", "expected"),
    [
        (5_000, 1),  # R$ 50: 2x daria R$ 25, abaixo do mínimo de R$ 50
        (10_000, 2),  # R$ 100: 2x de R$ 50
        (15_990, 3),  # R$ 159,90: 3x de R$ 53,30
        (30_000, 3),  # R$ 300: 3x cabe, 4x (R$ 75) não; as faixas não são monotônicas
        (34_990, 4),  # R$ 349,90: 4x de R$ 87,47
        (69_000, 6),  # R$ 690: 7x (R$ 98,57) não cabe, 6x (R$ 115) cabe
        (70_000, 7),  # R$ 700: 7x de R$ 100
        (100_000, 10),
        (119_900, 11),  # R$ 1.199: 12x daria R$ 99,92
        (120_000, 12),
    ],
)
def test_maximo_de_parcelas(price, expected):
    assert max_installments(price) == expected


def test_parcelas_somam_o_total_e_o_resto_vai_na_primeira():
    first, others = installment_plan(100_001, 3)
    assert (first, others) == (33_335, 33_333)
    assert first + 2 * others == 100_001


def test_parcelamento_invalido_fora_de_1_a_12():
    with pytest.raises(ValueError):
        is_installment_allowed(100_000, 13)


def test_pix_nao_acumula_com_promocao():
    assert pix_price(219_900, is_promotional=False) == 208_905
    assert pix_price(43_920, is_promotional=True) is None


def test_pagamento_combinado_somente_acima_de_dois_mil():
    assert not combined_payment_allowed(200_000)
    assert combined_payment_allowed(200_001)


def test_opcoes_de_pagamento_takamine_gd20():
    options = payment_options(219_900, is_promotional=False)
    assert options.pix_cents == 208_905
    assert options.max_installments == 12
    assert options.combined_payment_allowed
    assert "PIX à vista: R$ 2.089,05 (5% de desconto)" in options.as_text()


def test_opcoes_de_pagamento_sem_parcelamento():
    texto = payment_options(4_990, is_promotional=False).as_text()
    assert any("à vista (valor abaixo do mínimo para parcelar)" in linha for linha in texto)
