"""Análise geral dos Indicadores do Suporte (pedido do usuário, 2026-10-27): dia de maior aumento de atendimentos
no OPA e os motivos que mais pesaram nele, contra o habitual do próprio período. Usa os MESMOS filtros do dashboard
(departamento e colaborador), então é uma decomposição do mesmo universo dos cartões. A parte de "quanto falta para
a meta" sai dos próprios cartões, na tela."""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import opa_overview_service
from .models import SupportOpaAttendance
from .opa_filters import OpaAttendanceFilters, apply_opa_attendance_filters

MIN_DAYS = 3
# O pico só conta como "aumento" se passar do habitual em pelo menos esta proporção.
MIN_INCREASE_RATIO = 1.2
TOP_REASONS = 5
NO_REASON_LABEL = "Sem motivo registrado"


def _reason_counts(db: Session, filters: OpaAttendanceFilters) -> dict[str, int]:
    label = func.coalesce(func.nullif(func.trim(SupportOpaAttendance.reason_name), ""), NO_REASON_LABEL)
    statement = apply_opa_attendance_filters(select(label, func.count(SupportOpaAttendance.id)), filters).group_by(label)
    return {reason: int(count) for reason, count in db.execute(statement).all()}


def peak_day(db: Session, filters: OpaAttendanceFilters) -> dict[str, Any] | None:
    """Dia de maior volume do período, se for um aumento real sobre a média dos demais dias; senão `None`."""
    series = [(point["day"], int(point.get("total") or 0)) for point in opa_overview_service.daily_timeseries(db, filters)]
    if len(series) < MIN_DAYS:
        return None
    day, total = max(series, key=lambda item: item[1])
    others = [value for other_day, value in series if other_day != day]
    average = sum(others) / len(others)
    if total <= 0 or average <= 0 or total < average * MIN_INCREASE_RATIO:
        return None

    day_filters = replace(filters, date_from=day, date_to=day)
    peak_reasons = _reason_counts(db, day_filters)
    period_reasons = _reason_counts(db, filters)
    reasons = []
    for reason, count in sorted(peak_reasons.items(), key=lambda item: -item[1])[:TOP_REASONS]:
        usual = (period_reasons.get(reason, 0) - count) / len(others)
        reasons.append({"reason": reason, "count": count, "usual_per_day": round(usual, 1)})
    return {
        "day": day,
        "total": total,
        "average": round(average, 1),
        "percent_above": round((total / average - 1) * 100, 1),
        "reasons": reasons,
    }
