from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from emporio.rules.calendar import add_business_days, easter, holiday_name, is_business_day
from emporio.rules.store import store_status

CG = ZoneInfo("America/Campo_Grande")


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=CG)


def test_pascoa_e_sexta_feira_santa():
    assert easter(2026) == date(2026, 4, 5)
    assert holiday_name(date(2026, 4, 3)) == "Sexta-feira Santa"


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 11, 20), "Dia Nacional de Zumbi e da Consciência Negra"),
        (date(2026, 10, 11), "Criação do Estado de Mato Grosso do Sul"),
        (date(2026, 8, 26), "Aniversário de Campo Grande"),
        (date(2026, 11, 3), None),
    ],
)
def test_feriados(day, expected):
    assert holiday_name(day) == expected


def test_dias_uteis_pulam_fim_de_semana_e_feriado():
    # Sexta 30/10 + 1 dia útil: pula sábado, domingo e Finados (segunda, 02/11).
    assert add_business_days(date(2026, 10, 30), 1) == date(2026, 11, 3)
    assert not is_business_day(date(2026, 10, 31))  # sábado


def test_sabado_de_manha_aberta():
    status = store_status(at("2026-10-31T10:30"))
    assert status.is_open
    assert status.closes_at.hour == 13
    assert status.summary() == "Aberta agora, até as 13:00."


def test_sabado_as_13h_ja_fechou_e_reabre_depois_de_finados():
    status = store_status(at("2026-10-31T13:00"))
    assert not status.is_open
    # Domingo fechado, segunda é Finados: reabre na terça.
    assert status.next_opening == at("2026-11-03T09:00")
    assert status.summary() == "Fechada agora (fora do horário). Reabre terça, 03/11 às 09:00."


def test_domingo():
    status = store_status(at("2026-11-01T11:00"))
    assert status.closed_reason == "domingo"


def test_feriado_em_dia_de_semana():
    status = store_status(at("2026-11-20T10:00"))
    assert not status.is_open
    assert status.closed_reason.startswith("feriado")
    assert status.next_opening == at("2026-11-21T09:00")  # sábado


@pytest.mark.parametrize(
    ("moment", "is_open"),
    [("2026-11-04T08:59", False), ("2026-11-04T09:00", True), ("2026-11-04T17:59", True),
     ("2026-11-04T18:00", False)],
)  # fmt: skip
def test_limites_do_expediente(moment, is_open):
    assert store_status(at(moment)).is_open is is_open


def test_antes_de_abrir_reabre_hoje():
    assert store_status(at("2026-11-04T07:00")).summary().endswith("Reabre hoje às 09:00.")


def test_horario_de_brasilia_e_convertido():
    # 18:30 em Brasília = 17:30 em Campo Grande: ainda aberta.
    momento = datetime.fromisoformat("2026-11-04T18:30-03:00")
    assert store_status(momento).is_open


def test_exige_fuso_horario():
    with pytest.raises(ValueError):
        store_status(datetime(2026, 11, 4, 10, 0))
