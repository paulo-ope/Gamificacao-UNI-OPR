"""Regras de negócio do painel individual por colaborador do SGP Suporte.

Fase 3A: só o resumo agregado do atendente. Nada de histórico/timeline, IA,
metas ou chamada à API do OPA Suite aqui — isso é Fase 3B/3C em diante. A maior
parte do cálculo é reaproveitada de `opa_overview_service`, que já é genérico o
suficiente para operar sobre qualquer `OpaAttendanceFilters` (inclusive com
`attendant_id` fixo), evitando duplicar lógica de agregação.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import opa_attendant_overrides, opa_overview_service
from .models import SupportOpaAttendance, SupportOpaDimension
from .opa_filters import OpaAttendanceFilters, apply_opa_attendance_filters


def resolve_attendant_identity(db: Session, attendant_id: str) -> dict[str, Any] | None:
    """Confirma que o atendente existe (em algum atendimento já importado, ou na
    dimensão de usuários sincronizada) antes de montar um resumo — evita
    devolver 200 com tudo zerado para um id que nunca existiu no OPA Suite.
    Retorna também `attendant_type` (`"bot"`/`"user"`/... ou `None` se
    desconhecido), útil pra deixar claro no painel quando o "colaborador" é na
    verdade um atendimento automatizado."""
    attendance_name = db.scalar(
        select(func.max(SupportOpaAttendance.attendant_name)).where(
            SupportOpaAttendance.attendant_id == attendant_id
        )
    )
    dimension = db.scalar(
        select(SupportOpaDimension).where(
            SupportOpaDimension.dimension_type == "user",
            SupportOpaDimension.source_id == attendant_id,
        )
    )
    overrides = opa_attendant_overrides.load_active_overrides(db)
    if attendance_name is None and dimension is None and attendant_id not in overrides:
        return None

    opa_tipo = None
    dimension_name = None
    if dimension is not None:
        dimension_name = dimension.name
        if isinstance(dimension.payload_json, dict):
            opa_tipo = dimension.payload_json.get("tipo")

    attendant_type = opa_attendant_overrides.resolve_attendant_type(attendant_id, opa_tipo, overrides)

    return {
        "attendant_id": attendant_id,
        "attendant_name": attendance_name or dimension_name,
        "attendant_type": attendant_type,
    }


def attendant_summary(db: Session, attendant_id: str, filters: OpaAttendanceFilters) -> dict[str, Any] | None:
    """Resumo individual do atendente nos filtros informados. Retorna `None`
    quando o atendente nunca existiu na base — cabe ao router decidir o 404."""
    identity = resolve_attendant_identity(db, attendant_id)
    if identity is None:
        return None

    scoped_filters = OpaAttendanceFilters(
        date_from=filters.date_from,
        date_to=filters.date_to,
        date_basis=filters.date_basis,
        status=filters.status,
        channel=filters.channel,
        attendant_id=attendant_id,
        department_id=filters.department_id,
        reason_id=filters.reason_id,
        customer=filters.customer,
        search=filters.search,
    )

    metrics = opa_overview_service.overview_metrics(db, scoped_filters)
    rating_count = (
        db.scalar(apply_opa_attendance_filters(select(func.count(SupportOpaAttendance.rating)), scoped_filters))
        or 0
    )

    return {
        **identity,
        "total_attendances": metrics["total_attendances"],
        "closed_attendances": metrics["closed_attendances"],
        "open_attendances": metrics["open_attendances"],
        "closure_rate": metrics["closure_rate"],
        "average_tma_seconds": metrics["average_duration_seconds"],
        "average_tmr_seconds": metrics["average_tmr_seconds"],
        "average_tmr_all_responses_seconds": metrics["average_tmr_all_responses_seconds"],
        "tmr_all_responses_coverage": metrics["tmr_all_responses_coverage"],
        "average_first_response_seconds": opa_overview_service.average_first_response_seconds(db, scoped_filters),
        "average_rating": metrics["average_rating"],
        "rating_count": int(rating_count),
        "customers": opa_overview_service.customer_metrics(db, scoped_filters),
        "by_status": opa_overview_service.status_breakdown(db, scoped_filters),
        "by_reason": opa_overview_service.top_reasons(db, scoped_filters, limit=50),
        "by_channel": opa_overview_service.channel_counts(db, scoped_filters),
        "bot_human": opa_overview_service.bot_human_metrics(db, scoped_filters),
    }
