from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import or_

from .models import SupportOpaAttendance


def _selected_values(value: str | None) -> list[str]:
    """Aceita valores únicos e listas serializadas pela URL (ex.: A-1,A-2)."""
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def validate_opa_period(date_from: date, date_to: date) -> None:
    if date_from > date_to:
        raise HTTPException(status_code=422, detail="A data inicial não pode ser maior que a data final.")
    if (date_to - date_from).days > 31:
        raise HTTPException(status_code=422, detail="Por segurança, consulte no máximo 32 dias por requisição.")


def opa_period_bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(date_from, time.min, tzinfo=timezone.utc),
        datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc),
    )


@dataclass(frozen=True)
class OpaAttendanceFilters:
    date_from: date | None = None
    date_to: date | None = None
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

    def previous_period(self) -> "OpaAttendanceFilters":
        if not self.date_from or not self.date_to:
            return self
        validate_opa_period(self.date_from, self.date_to)
        days = (self.date_to - self.date_from).days + 1
        previous_to = self.date_from - timedelta(days=1)
        previous_from = previous_to - timedelta(days=days - 1)
        return OpaAttendanceFilters(
            date_from=previous_from,
            date_to=previous_to,
            status=self.status,
            channel=self.channel,
            attendant_id=self.attendant_id,
            department_id=self.department_id,
            reason_id=self.reason_id,
            search=self.search,
            attendant=self.attendant,
            department=self.department,
            reason=self.reason,
            protocol=self.protocol,
            customer=self.customer,
        )


def apply_opa_attendance_filters(statement, filters: OpaAttendanceFilters):
    clauses = []
    if filters.date_from and filters.date_to:
        validate_opa_period(filters.date_from, filters.date_to)
        start_at, end_at = opa_period_bounds(filters.date_from, filters.date_to)
        clauses.extend([SupportOpaAttendance.opened_at >= start_at, SupportOpaAttendance.opened_at < end_at])
    elif filters.date_from:
        start_at = datetime.combine(filters.date_from, time.min, tzinfo=timezone.utc)
        clauses.append(SupportOpaAttendance.opened_at >= start_at)
    elif filters.date_to:
        end_at = datetime.combine(filters.date_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
        clauses.append(SupportOpaAttendance.opened_at < end_at)

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
