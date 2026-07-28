from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException


OPERATIONS_TIMEZONE_NAME = "America/Porto_Velho"
OPERATIONS_TIMEZONE = ZoneInfo(OPERATIONS_TIMEZONE_NAME)


def operations_period_bounds(now: datetime | None = None) -> tuple[date, date]:
    local_now = (now or datetime.now(timezone.utc)).astimezone(OPERATIONS_TIMEZONE)
    first = date(local_now.year, 1, 1)
    return first, local_now.date()


def validate_operations_period(date_from: date, date_to: date, now: datetime | None = None) -> tuple[date, date]:
    allowed_from, allowed_to = operations_period_bounds(now)
    if date_from > date_to:
        raise HTTPException(status_code=422, detail="A data inicial deve ser menor ou igual à data final.")
    if date_from < allowed_from or date_to > allowed_to:
        raise HTTPException(
            status_code=422,
            detail=f"Nesta fase, somente datas do ano operacional disponivel ({allowed_from:%d/%m/%Y} a {allowed_to:%d/%m/%Y}) sao permitidas.",
        )
    return allowed_from, allowed_to


# Compatibilidade para consumidores internos existentes.

current_month_bounds = operations_period_bounds
validate_current_month_period = validate_operations_period


def local_day_query_bounds(date_from: date, date_to: date) -> tuple[str, str]:
    start = datetime.combine(date_from, time.min)
    end = datetime.combine(date_to, time.max.replace(microsecond=0))
    return start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")


def local_period_utc_bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    start_local = datetime.combine(date_from, time.min, tzinfo=OPERATIONS_TIMEZONE)
    end_local = datetime.combine(date_to, time.max, tzinfo=OPERATIONS_TIMEZONE)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def parse_ixc_local_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw or raw in {"0000-00-00", "0000-00-00 00:00:00"}:
        return None
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(raw, pattern)
            return parsed.replace(tzinfo=OPERATIONS_TIMEZONE).astimezone(timezone.utc)
        except ValueError:
            continue
    return None
