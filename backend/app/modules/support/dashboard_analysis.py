"""Análise geral dos Indicadores do Suporte (pedido do usuário, 2026-10-27): dia de maior aumento de atendimentos
no OPA e os motivos que mais pesaram nele, contra o habitual do próprio período. Usa os MESMOS filtros do dashboard
(departamento e colaborador), então é uma decomposição do mesmo universo dos cartões. A parte de "quanto falta para
a meta" sai dos próprios cartões, na tela."""
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
# Indicadores de tempo da projeção de fechamento: chave -> (média, quantidade) em `overview_metrics`.
PROJECTION_METRICS = {
    "tmr": ("average_tmr_effective_seconds", "tmr_effective_coverage"),
    "tma": ("average_tma_effective_seconds", "tma_effective_coverage"),
}


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


def month_projection(db: Session, filters: OpaAttendanceFilters, date_to: date, targets: dict[str, float]) -> dict[str, Any]:
    """Quanto o RESTO do mês de `date_to` precisa fechar para a média do mês terminar na meta (TMR e TMA).

    Média do mês é ponderada pelo volume: com `n` atendimentos já medidos a média `m` e a meta `T`, o resto do mês
    (volume estimado pelo ritmo diário do mês até agora) precisa fechar em
    `x = (T * (n + n_resto) - m * n) / n_resto`. `x <= 0` quer dizer que não dá mais para fechar o mês na meta."""
    month_start = date_to.replace(day=1)
    next_month = (month_start + timedelta(days=32)).replace(day=1)
    month_end = next_month - timedelta(days=1)
    elapsed = (date_to - month_start).days + 1
    remaining = (month_end - date_to).days
    metrics = opa_overview_service.overview_metrics(db, replace(filters, date_from=month_start, date_to=date_to))

    items = []
    for key, (value_key, coverage_key) in PROJECTION_METRICS.items():
        target = targets.get(key)
        value = metrics.get(value_key)
        count = int((metrics.get(coverage_key) or {}).get("count") or 0)
        item: dict[str, Any] = {"key": key, "month_value": value, "target": target, "count": count, "required_value": None, "status": "no_data"}
        if value is not None and target is not None and count > 0:
            if remaining == 0:
                item["status"] = "closed"
            else:
                expected = count / elapsed * remaining
                required = (target * (count + expected) - value * count) / expected
                item["required_value"] = round(required, 1) if required > 0 else None
                item["status"] = "reachable" if required > 0 else "unreachable"
        items.append(item)
    return {
        "month_from": month_start,
        "month_to": month_end,
        "elapsed_days": elapsed,
        "remaining_days": remaining,
        "remaining_from": date_to + timedelta(days=1) if remaining else None,
        "items": items,
    }
