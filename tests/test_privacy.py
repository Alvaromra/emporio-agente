import pytest

from emporio.privacy import fingerprint, first_name, normalize_phone
from emporio.text import fold, slugify


@pytest.mark.parametrize(
    "raw",
    ["(67) 99812-3456", "+55 67 99812-3456", "067 99812 3456", "99812-3456", "67998123456"],
)
def test_telefone_normalizado_para_ddd_mais_numero(raw):
    assert normalize_phone(raw) == "67998123456"


def test_fingerprint_ignora_caixa_e_espacos_no_email():
    a = fingerprint("email", "lucas.mendes@jmail.com", "segredo")
    b = fingerprint("email", "  Lucas.Mendes@JMAIL.com ", "segredo")
    assert a == b


def test_fingerprint_depende_do_segredo_e_do_tipo():
    assert fingerprint("email", "x@y.com", "a") != fingerprint("email", "x@y.com", "b")
    assert fingerprint("email", "123", "a") != fingerprint("phone", "123", "a")


def test_utilitarios_de_texto():
    assert first_name("  Ana Carolina Ferreira ") == "Ana"
    assert fold("Violão  ELÉTRICO") == "violao eletrico"
    assert slugify("Instrumentos de Sopro (Madeiras)") == "instrumentos-de-sopro-madeiras"
