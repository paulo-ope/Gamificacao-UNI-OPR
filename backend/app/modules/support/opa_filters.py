from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import or_

from .models import SupportOpaAttendance

# Todo filtro de período do SGP interpreta "o dia" no fuso operacional da UNI, não
# em UTC — ver docs/plano-analise-opa-suite-atendimentos.md, seção "fuso horário".
SUPPORT_TIMEZONE_NAME = "America/Porto_Velho"
SUPPORT_TIMEZONE = ZoneInfo(SUPPORT_TIMEZONE_NAME)


def _selected_values(value: str | None) -> list[str]:
    """Aceita valores únicos e listas serializadas pela URL (ex.: A-1,A-2)."""
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def validate_opa_period(date_from: date, date_to: date) -> None:
    if date_from > date_to:
        raise HTTPException(status_code=422, detail="A data inicial não pode ser maior que a data final.")
    if (date_to - date_from).days > 31:
        raise HTTPException(status_code=422, detail="Por segurança, consulte no máximo 32 dias por requisição.")


def opa_period_bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    """Converte um intervalo de datas locais (America/Porto_Velho) nos limites
    UTC equivalentes, usados para filtrar `opened_at` (armazenado em UTC)."""
    start_local = datetime.combine(date_from, time.min, tzinfo=SUPPORT_TIMEZONE)
    end_local = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=SUPPORT_TIMEZONE)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


# Colunas de data válidas para `date_basis` — controla se o período filtra por
# abertura (padrão, comportamento histórico) ou por encerramento do
# atendimento. Um atendimento aberto num dia e encerrado no seguinte só
# aparece no filtro do 2º dia quando `date_basis="closed_at"` — e nesse modo,
# atendimentos ainda em aberto (closed_at NULL) nunca aparecem, por definição.
DATE_BASIS_COLUMNS = {
    "opened_at": SupportOpaAttendance.opened_at,
    "closed_at": SupportOpaAttendance.closed_at,
}
DEFAULT_DATE_BASIS = "opened_at"

# Separador usado em `SupportOpaAttendance.tag_ids_text` — o valor é sempre
# gravado cercado por vírgulas (ex.: ",a,b,"), pra que um LIKE "%,a,%" nunca
# case com um id que só CONTENHA outro como prefixo/sufixo.
TAG_SEPARATOR = ","

# Recortes de participação bot/humano. As colunas por trás são nullable e
# `NULL` significa "não classificado" (histórico anterior à Fase 2, ou mensagens
# indisponíveis) — por isso todo filtro aqui usa `IS TRUE`/`IS FALSE`, que
# EXCLUI os não classificados dos dois lados, em vez de tratar NULL como False.
# Ver `opa_ingestion._classify_bot_human`.
BOT_HUMAN_FILTERS = {
    "with_bot": lambda: SupportOpaAttendance.handled_by_bot.is_(True),
    "without_bot": lambda: SupportOpaAttendance.handled_by_bot.is_(False),
    "reached_human": lambda: SupportOpaAttendance.reached_human.is_(True),
    "bot_only": lambda: SupportOpaAttendance.reached_human.is_(False),
    "handoff": lambda: SupportOpaAttendance.bot_to_human_handoff.is_(True),
    "unclassified": lambda: SupportOpaAttendance.handled_by_bot.is_(None),
}


@dataclass(frozen=True)
class OpaAttendanceFilters:
    date_from: date | None = None
    date_to: date | None = None
    date_basis: str = DEFAULT_DATE_BASIS
    status: str | None = None
    channel: str | None = None
    attendant_id: str | None = None
    department_id: str | None = None
    reason_id: str | None = None
    search: str | None = None
    attendant: str | None = None
    department: str | None = None
    reason: str | None = None
    protocol: str | None = None
    customer: str | None = None
    tag_id: str | None = None
    customer_id: str | None = None
    rating_min: float | None = None
    rating_max: float | None = None
    bot_human: str | None = None

    def previous_period(self) -> "OpaAttendanceFilters":
        """Mesmo recorte de filtros, deslocado pro período imediatamente
        anterior de mesma duração. Usa `dataclasses.replace` de propósito: a
        versão antiga copiava campo a campo, e todo filtro novo que alguém
        esquecesse de adicionar aqui vazaria silenciosamente do comparativo
        (o "período anterior" ficaria calculado sobre um universo diferente do
        atual, sem erro nenhum aparecendo)."""
        if not self.date_from or not self.date_to:
            return self
        validate_opa_period(self.date_from, self.date_to)
        days = (self.date_to - self.date_from).days + 1
        previous_to = self.date_from - timedelta(days=1)
        previous_from = previous_to - timedelta(days=days - 1)
        return replace(self, date_from=previous_from, date_to=previous_to)


def apply_opa_attendance_filters(statement, filters: OpaAttendanceFilters):
    date_column = DATE_BASIS_COLUMNS.get(filters.date_basis, DATE_BASIS_COLUMNS[DEFAULT_DATE_BASIS])
    clauses = []
    if filters.date_from and filters.date_to:
        validate_opa_period(filters.date_from, filters.date_to)
        start_at, end_at = opa_period_bounds(filters.date_from, filters.date_to)
        clauses.extend([date_column >= start_at, date_column < end_at])
    elif filters.date_from:
        start_at = datetime.combine(filters.date_from, time.min, tzinfo=SUPPORT_TIMEZONE).astimezone(timezone.utc)
        clauses.append(date_column >= start_at)
    elif filters.date_to:
        end_at = datetime.combine(
            filters.date_to + timedelta(days=1), time.min, tzinfo=SUPPORT_TIMEZONE
        ).astimezone(timezone.utc)
        clauses.append(date_column < end_at)

    if values := _selected_values(filters.status):
        clauses.append(SupportOpaAttendance.status.in_(values))
    if values := _selected_values(filters.channel):
        clauses.append(SupportOpaAttendance.channel.in_(values))
    if values := _selected_values(filters.attendant_id):
        clauses.append(SupportOpaAttendance.attendant_id.in_(values))
    if filters.attendant:
        clauses.append(SupportOpaAttendance.attendant_name == filters.attendant)
    if values := _selected_values(filters.department_id):
        clauses.append(SupportOpaAttendance.department_id.in_(values))
    if filters.department:
        clauses.append(SupportOpaAttendance.department_name == filters.department)
    if values := _selected_values(filters.reason_id):
        clauses.append(SupportOpaAttendance.reason_id.in_(values))
    if filters.reason:
        clauses.append(SupportOpaAttendance.reason_name == filters.reason)
    if values := _selected_values(filters.customer_id):
        clauses.append(SupportOpaAttendance.customer_id.in_(values))
    if values := _selected_values(filters.tag_id):
        # Etiqueta é multivalorada por atendimento (um atendimento pode ter N
        # etiquetas), então a semântica é OU: "tem pelo menos uma das
        # selecionadas" — igual ao que o painel do OPA faz.
        clauses.append(
            or_(
                *[
                    SupportOpaAttendance.tag_ids_text.like(f"%{TAG_SEPARATOR}{value}{TAG_SEPARATOR}%")
                    for value in values
                ]
            )
        )
    if filters.rating_min is not None:
        clauses.append(SupportOpaAttendance.rating >= filters.rating_min)
    if filters.rating_max is not None:
        clauses.append(SupportOpaAttendance.rating <= filters.rating_max)
    if filters.bot_human:
        build_clause = BOT_HUMAN_FILTERS.get(filters.bot_human)
        if build_clause is None:
            raise HTTPException(status_code=422, detail="Filtro de participação bot/humano inválido.")
        clauses.append(build_clause())
    if filters.protocol:
        clauses.append(SupportOpaAttendance.protocol.ilike(f"%{filters.protocol.strip()}%"))
    if filters.customer:
        term = f"%{filters.customer.strip()}%"
        clauses.append(
            or_(
                SupportOpaAttendance.customer_name.ilike(term),
                SupportOpaAttendance.customer_id.ilike(term),
                SupportOpaAttendance.channel_customer.ilike(term),
            )
        )
    if filters.search:
        term = f"%{filters.search.strip()}%"
        clauses.append(
            or_(
                SupportOpaAttendance.protocol.ilike(term),
                SupportOpaAttendance.source_id.ilike(term),
                SupportOpaAttendance.customer_name.ilike(term),
                SupportOpaAttendance.customer_id.ilike(term),
                SupportOpaAttendance.channel_customer.ilike(term),
                SupportOpaAttendance.attendant_name.ilike(term),
                SupportOpaAttendance.department_name.ilike(term),
                SupportOpaAttendance.reason_name.ilike(term),
            )
        )
    if clauses:
        return statement.where(*clauses)
    return statement
