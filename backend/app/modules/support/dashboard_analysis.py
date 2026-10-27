"""Análise geral dos Indicadores do Suporte (pedido do usuário, 2026-10-27): dia de maior aumento de atendimentos
no OPA com os motivos, as semanas do mês e a projeção de fechamento do mês. Usa os MESMOS filtros do dashboard
(departamento e colaborador) nos números do OPA, então é uma decomposição do mesmo universo dos cartões."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
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
CSAT_MAX = 5.0
PERCENT_MAX = 100.0


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


def _rated_count(db: Session, filters: OpaAttendanceFilters) -> int:
    return int(db.scalar(apply_opa_attendance_filters(select(func.count(SupportOpaAttendance.rating)), filters)) or 0)


def _count(coverage: Any) -> int:
    return int((coverage or {}).get("count") or 0)


def _sum_item(key: str, month_value: float | None, period_value: float | None, period_days: int, remaining: int) -> dict[str, Any]:
    """Indicador de volume: o mês fecha em (o que já foi) + (ritmo diário do período) x (dias que faltam)."""
    item: dict[str, Any] = {
        "key": key, "kind": "sum", "month_value": month_value, "pace_value": None, "target": None, "direction": None,
        "count": int(month_value or 0), "required_value": None, "pace_meets_target": None, "status": "no_data",
    }
    if month_value is None:
        return item
    projected = month_value + (period_value or 0) / period_days * remaining
    item.update(pace_value=round(projected, 1), status="closed" if remaining == 0 else "no_target")
    return item


def _mean_item(
    key: str, *, month_value: float | None, month_weight: float, period_value: float | None, period_weight: float,
    period_days: int, elapsed: int, remaining: int, target: float | None, direction: str, upper: float | None = None,
) -> dict[str, Any]:
    """Indicador de média ponderada pelo volume. Com `n` já medidos a média `m`, a média do resto do mês `p` (a do
    período selecionado, o "ritmo atual") e `r` o volume que ainda deve entrar, o mês fecha em
    `(m*n + p*r) / (n + r)`; para fechar na meta `T` o resto precisa fechar em `x = (T*(n + r) - m*n) / r`."""
    item: dict[str, Any] = {
        "key": key, "kind": "mean", "month_value": month_value, "pace_value": None, "target": target, "direction": direction,
        "count": int(month_weight), "required_value": None, "pace_meets_target": None, "status": "no_data",
    }
    if month_value is None or month_weight <= 0:
        return item
    if remaining == 0:
        item.update(pace_value=month_value, status="closed", pace_meets_target=_meets(month_value, target, direction))
        return item
    expected = (period_weight / period_days if period_weight > 0 else month_weight / elapsed) * remaining
    pace = month_value if period_value is None else period_value
    projected = (month_value * month_weight + pace * expected) / (month_weight + expected)
    item.update(pace_value=round(projected, 4), pace_meets_target=_meets(projected, target, direction), status="no_target")
    if target is not None and expected > 0:
        required = (target * (month_weight + expected) - month_value * month_weight) / expected
        feasible = required > 0 if direction == "max" else (required <= upper if upper is not None else True)
        item["status"] = "reachable" if feasible else "unreachable"
        item["required_value"] = round(required, 4) if feasible else None
    return item


def _meets(value: float, target: float | None, direction: str) -> bool | None:
    if target is None:
        return None
    return value <= target if direction == "max" else value >= target


def month_projection(
    db: Session, filters: OpaAttendanceFilters, *, date_to: date, period_days: int, targets: dict[str, float],
    current_opa: dict[str, Any], current_ixc: dict[str, Any], month_ixc: dict[str, Any],
) -> dict[str, Any]:
    """Projeção de fechamento do mês de `date_to`: o que o ritmo do período selecionado entrega no fim do mês e o
    quanto o resto do mês precisa fechar para a média do mês terminar na meta (quando o indicador tem meta)."""
    month_start = date_to.replace(day=1)
    month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    elapsed = (date_to - month_start).days + 1
    remaining = (month_end - date_to).days
    month_opa = opa_overview_service.overview_metrics(db, replace(filters, date_from=month_start, date_to=date_to))
    month_rated = _rated_count(db, replace(filters, date_from=month_start, date_to=date_to))
    period_rated = _rated_count(db, filters)

    def mean(key, month_value, month_weight, period_value, period_weight, direction, upper=None):
        return _mean_item(
            key, month_value=month_value, month_weight=month_weight, period_value=period_value, period_weight=period_weight,
            period_days=period_days, elapsed=elapsed, remaining=remaining, target=targets.get(key), direction=direction, upper=upper,
        )

    items = [
        _sum_item("opa_total", month_opa["total_attendances"], current_opa["total_attendances"], period_days, remaining),
        mean("tmr", month_opa["average_tmr_effective_seconds"], _count(month_opa["tmr_effective_coverage"]),
             current_opa["average_tmr_effective_seconds"], _count(current_opa["tmr_effective_coverage"]), "max"),
        mean("tma", month_opa["average_tma_effective_seconds"], _count(month_opa["tma_effective_coverage"]),
             current_opa["average_tma_effective_seconds"], _count(current_opa["tma_effective_coverage"]), "max"),
        mean("csat", month_opa["average_rating"], month_rated, current_opa["average_rating"], period_rated, "min", CSAT_MAX),
        _sum_item("performed", month_ixc["performed"], current_ixc["performed"], period_days, remaining),
        _sum_item("field", month_ixc["field"], current_ixc["field"], period_days, remaining),
        mean("resolutivity", month_ixc["resolutivity"], month_ixc["performed"] or 0, current_ixc["resolutivity"],
             current_ixc["performed"] or 0, "min", PERCENT_MAX),
    ]
    return {
        "month_from": month_start,
        "month_to": month_end,
        "elapsed_days": elapsed,
        "remaining_days": remaining,
        "remaining_from": date_to + timedelta(days=1) if remaining else None,
        "items": items,
    }


def weeks_opa(db: Session, filters: OpaAttendanceFilters, buckets: list[dict[str, Any]], date_to: date) -> list[dict[str, Any]]:
    """Indicadores do OPA de cada semana do mês até `date_to` (semana que começa depois dele vem sem números)."""
    weeks = []
    for bucket in buckets:
        if bucket["key"] in ("month", "previous_last_week"):
            continue
        future = bucket["from"] > date_to
        week = {
            "key": bucket["key"], "label": bucket["label"], "date_from": bucket["from"], "date_to": bucket["to"],
            "future": future, "partial": not future and bucket["to"] > date_to,
            "total": None, "tmr_seconds": None, "tma_seconds": None, "rating": None,
        }
        if not future:
            metrics = opa_overview_service.overview_metrics(db, replace(filters, date_from=bucket["from"], date_to=min(bucket["to"], date_to)))
            week.update(
                total=metrics["total_attendances"], tmr_seconds=metrics["average_tmr_effective_seconds"],
                tma_seconds=metrics["average_tma_effective_seconds"], rating=metrics["average_rating"],
            )
        weeks.append(week)
    return weeks
