from datetime import date, timedelta

from emporio import clock


def test_now_usa_fuso_de_campo_grande(settings_env):
    settings_env(EMPORIO_NOW="2026-10-31T10:30")
    agora = clock.now()
    assert agora.utcoffset() == timedelta(hours=-4)
    assert clock.today() == date(2026, 10, 31)


def test_override_com_fuso_explicito_e_convertido(settings_env):
    # 23:30 em Brasília (UTC-3) ainda é 22:30 em Campo Grande.
    settings_env(EMPORIO_NOW="2026-10-31T23:30-03:00")
    assert clock.now().hour == 22
