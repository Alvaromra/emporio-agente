"""Dados institucionais e horário de funcionamento (manual, seções 1.2 e 2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from emporio.clock import store_tz
from emporio.rules.calendar import holiday_name

# Onde o manual se contradiz, a escolha está em docs/suposicoes.md (M9 e M10).
STORE_INFO = {
    "nome": "Empório da Música",
    "razao_social": "Empório da Música Instrumentos Musicais Ltda.",
    "cnpj": "12.345.678/0001-90",
    "endereco": "Rua 14 de Maio, 3200, Centro, Campo Grande - MS, CEP 79202-333",
    "telefone_whatsapp": "(67) 3341-4444",
    "email": "contato@emporiodamusica.com.br",
    "fundacao": 2008,
}

# weekday() -> (abertura, fechamento). Domingo (6) fechado.
OPENING_HOURS: dict[int, tuple[time, time]] = {
    **{weekday: (time(9), time(18)) for weekday in range(5)},
    5: (time(9), time(13)),
}
WEEKDAY_NAMES = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
SPECIAL_DATES_NOTE = (
    "Em datas especiais (Black Friday, Aniversário da Loja, Natal) o horário pode ser "
    "estendido; alterações são avisadas nas redes sociais e no WhatsApp."
)


@dataclass(frozen=True)
class StoreStatus:
    is_open: bool
    now: datetime
    closes_at: datetime | None  # quando está aberta
    next_opening: datetime | None  # quando está fechada
    closed_reason: str | None  # "domingo", nome do feriado, "fora do horário"

    def summary(self) -> str:
        if self.is_open:
            return f"Aberta agora, até as {self.closes_at:%H:%M}."
        reason = f" ({self.closed_reason})" if self.closed_reason else ""
        when = describe_moment(self.next_opening, relative_to=self.now)
        return f"Fechada agora{reason}. Reabre {when}."


def hours_for(day) -> tuple[time, time] | None:
    """Horário de um dia específico, ou None se a loja não abre."""
    if holiday_name(day):
        return None
    return OPENING_HOURS.get(day.weekday())


def describe_moment(moment: datetime, relative_to: datetime) -> str:
    days = (moment.date() - relative_to.date()).days
    if days == 0:
        label = "hoje"
    elif days == 1:
        label = "amanhã"
    else:
        label = f"{WEEKDAY_NAMES[moment.weekday()]}, {moment:%d/%m}"
    return f"{label} às {moment:%H:%M}"


def store_status(at: datetime) -> StoreStatus:
    """Situação da loja num instante (aceita qualquer fuso; converte para Campo Grande)."""
    if at.tzinfo is None:
        raise ValueError("Informe um datetime com fuso horário.")
    tz = store_tz()
    now = at.astimezone(tz)
    today = hours_for(now.date())
    if today and today[0] <= now.time() < today[1]:
        closes = datetime.combine(now.date(), today[1], tz)
        return StoreStatus(True, now, closes, None, None)

    holiday = holiday_name(now.date())
    if holiday:
        reason = f"feriado: {holiday}"
    elif now.weekday() == 6:
        reason = "domingo"
    else:
        reason = "fora do horário"

    for offset in range(0, 15):
        day = now.date() + timedelta(days=offset)
        hours = hours_for(day)
        if not hours:
            continue
        opening = datetime.combine(day, hours[0], tz)
        if opening > now:
            return StoreStatus(False, now, None, opening, reason)
    return StoreStatus(False, now, None, None, reason)


def weekly_hours_text() -> str:
    return (
        "Segunda a sexta, das 9h às 18h; sábado, das 9h às 13h; "
        "fechado aos domingos e feriados. O atendimento pelo WhatsApp segue o mesmo horário."
    )
