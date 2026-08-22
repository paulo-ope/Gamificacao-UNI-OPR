from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date, timedelta
from statistics import mean, median, pstdev
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.services import shift_schedule

from . import queries
from .models import OperationResponsibleAssignment, OperationTeamModel
from .period import OPERATIONS_TIMEZONE


PerformanceBand = Literal["neutral", "below", "median", "good", "excellent"]
CONTROL_TOWER_LEVELS = ("subject", "regional", "city", "sector", "responsible")


def _normalized_identity(value: str | None) -> str:
    return " ".join((value or "").strip().casefold().split())


def _outside_schedule(local_datetime, rule) -> tuple[bool, str | None]:
    if rule is None:
        return False, None
    if not rule.enabled:
        return True, None
    if rule.start_time is None or rule.end_time is None:
        return False, None
    current = local_datetime.time().replace(tzinfo=None)
    start = rule.start_time
    end = rule.end_time
    if start == end:
        return False, None
    if start < end:
        if current < start:
            return True, "before_start"
        if current > end:
            return True, "after_end"
        return False, None
    if current >= start or current <= end:
        return False, None
    return True, "after_end"


def work_schedule_overview(
    db: Session,
    date_from: date,
    date_to: date,
    user: User,
    *,
    model_ids: list[int] | None = None,
    **filters,
) -> dict:
    orders = queries.work_schedule_orders(db, date_from, date_to, user, **filters)
    names = {_normalized_identity(order.responsible) for order in orders if order.responsible}
    assignments = list(
        db.scalars(
            select(OperationResponsibleAssignment).where(OperationResponsibleAssignment.responsible_name.is_not(None))
        )
    )
    models = {item.id: item for item in db.scalars(select(OperationTeamModel)).unique()}
    by_identity: dict[str, OperationResponsibleAssignment] = {}
    for assignment in assignments:
        identity = _normalized_identity(assignment.responsible_name)
        if identity in names:
            by_identity.setdefault(identity, assignment)

    selected = set(model_ids or [])
    counters: dict[int, dict[str, int | str]] = {}
    totals = {"completed": 0, "classified": 0, "outside_schedule": 0, "before_start": 0, "after_end": 0, "unclassified": 0}
    for order in orders:
        assignment = by_identity.get(_normalized_identity(order.responsible))
        model = models.get(assignment.team_model_id) if assignment and assignment.team_model_id else None
        if selected and (model is None or model.id not in selected):
            continue
        totals["completed"] += 1
        if model is None or order.closed_at is None:
            totals["unclassified"] += 1
            continue
        local_closed = order.closed_at.astimezone(OPERATIONS_TIMEZONE)
        period_type = "sunday" if local_closed.weekday() == 6 else "saturday" if local_closed.weekday() == 5 else "weekday"
        rule = next((item for item in model.target_rules if item.period_type == period_type), None)
        outside, reason = _outside_schedule(local_closed, rule)
        totals["classified"] += 1
        model_counter = counters.setdefault(model.id, {
            "model_id": model.id,
            "model_name": model.name,
            "completed": 0,
            "outside_schedule": 0,
            "before_start": 0,
            "after_end": 0,
            "unclassified": 0,
        })
        model_counter["completed"] = int(model_counter["completed"]) + 1
        if outside:
            totals["outside_schedule"] += 1
            model_counter["outside_schedule"] = int(model_counter["outside_schedule"]) + 1
            if reason:
                totals[reason] += 1
                model_counter[reason] = int(model_counter[reason]) + 1
    classified = totals["classified"]
    return {
        **totals,
        "outside_rate": round(totals["outside_schedule"] / classified * 100, 1) if classified else None,
        "selected_model_ids": sorted(selected),
        "available_models": [
            {"id": model.id, "name": model.name}
            for model in sorted(models.values(), key=lambda item: item.name.casefold())
            if model.active
        ],
        "by_model": sorted(counters.values(), key=lambda item: (-int(item["outside_schedule"]), str(item["model_name"]))),
    }


def _target_rule(team_model: dict | None, period_type: str) -> dict | None:
    if team_model is None:
        return None
    rules = team_model.get("target_rules") or []
    return next((rule for rule in rules if rule.get("period_type") == period_type), None)


def _classify_quantity(quantity: int, rule: dict | None) -> PerformanceBand:
    if quantity <= 0:
        return "neutral"
    if rule is None or not rule.get("enabled", True):
        return "neutral"
    if quantity < int(rule["median_from_quantity"]):
        return "below"
    if quantity < int(rule["good_from_quantity"]):
        return "median"
    if quantity < int(rule["target_quantity"]):
        return "good"
    return "excellent"


def classify_daily_performance(
    quantity: int,
    team_model: dict | None,
    day: date | None = None,
    *,
    is_scheduled_workday: bool = True,
) -> PerformanceBand:
    # Achado real de 2026-08-21: sem essa checagem, a folga da escala alternada (12x36 etc.) de um
    # colaborador virava "abaixo da meta" no calendário sempre que ele produzia algo abaixo do
    # limiar nesse dia - mesmo já não sendo avaliado pelo motor de casos automáticos
    # (`management.cases.is_scheduled_workday`, que pula esse dia). Um dia de folga é sempre
    # neutro aqui, igual já é o comportamento pra produção zero.
    if not is_scheduled_workday:
        return "neutral"
    if team_model is None:
        return "neutral"
    period_type = "sunday" if day and day.weekday() == 6 else "saturday" if day and day.weekday() == 5 else "weekday"
    rule = _target_rule(team_model, period_type)
    if rule is None:
        rule = {
            "enabled": True,
            "median_from_quantity": team_model["median_from_quantity"],
            "good_from_quantity": team_model["good_from_quantity"],
            "target_quantity": team_model["daily_target"],
        }
    return _classify_quantity(quantity, rule)


def monthly_calendar(
    db: Session,
    competence: date,
    user: User,
    *,
    group_by: Literal["regional", "collaborator"] = "regional",
    # Escala alternada (12x36 etc.) por responsável normalizado (`_normalized_identity`), vinda de
    # `ManagementOperationalMember` - `operations` não pode importar `management` nas camadas de
    # query/serviço (é o contrário que vale, ver `management/services.py`), então quem já tem
    # acesso aos dois módulos (o router) busca e injeta aqui. `None`/ausente = ninguém tem escala
    # configurada, mesmo comportamento de antes desse parâmetro existir.
    shift_info_by_identity: dict[str, dict] | None = None,
    **filters,
) -> dict:
    calendar = deepcopy(queries.monthly_calendar(db, competence, user, group_by=group_by, **filters))
    for regional in calendar["regionals"]:
        for collaborator in regional["collaborators"]:
            shift_info = (shift_info_by_identity or {}).get(_normalized_identity(collaborator["responsible"]))
            collaborator["daily_performance"] = {
                day["date"].isoformat(): classify_daily_performance(
                    int(collaborator["daily_counts"].get(day["date"].isoformat(), 0)),
                    collaborator["team_model"],
                    day["date"],
                    is_scheduled_workday=(
                        shift_schedule.is_scheduled_workday(
                            shift_info["shift_pattern"],
                            shift_info["shift_cycle_days_on"],
                            shift_info["shift_cycle_days_off"],
                            shift_info["shift_anchor_date"],
                            day["date"],
                        )
                        if shift_info
                        else True
                    ),
                )
                for day in calendar["days"]
            }
            collaborator["monthly_performance"] = _classify_quantity(
                int(collaborator["total"]),
                _target_rule(collaborator["team_model"], "monthly"),
            )
    return calendar


def calendar_order_page(
    db: Session,
    day: date,
    regional: str,
    responsible: str,
    user: User,
    *,
    group_by: Literal["regional", "collaborator"] = "regional",
    page: int,
    page_size: int,
    **filters,
) -> dict:
    return queries.calendar_order_page(
        db,
        day,
        regional,
        responsible,
        user,
        group_by=group_by,
        page=page,
        page_size=page_size,
        **filters,
    )


def _duration_minutes(start, end) -> float | None:
    if start is None or end is None or end < start:
        return None
    return round((end - start).total_seconds() / 60, 2)


def _average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _calendar_day_metrics(orders, reference_regional: str | None) -> dict:
    execution_minutes = [
        duration
        for order in orders
        if (duration := _duration_minutes(order.execution_started_at, order.finished_at or order.closed_at)) is not None
    ]
    pre_displacement_minutes = [
        duration
        for order in orders
        if (duration := _duration_minutes(order.opened_at, order.displacement_started_at)) is not None
    ]
    displacement_minutes = [
        duration
        for order in orders
        if (duration := _duration_minutes(order.displacement_started_at, order.execution_started_at)) is not None
    ]
    total_minutes = [
        duration
        for order in orders
        if (duration := _duration_minutes(order.opened_at, order.finished_at or order.closed_at)) is not None
    ]
    measurable_sla = [order for order in orders if order.sla_status in {"on_time", "out_of_time"}]
    type_counts: dict[str, int] = {}
    for order in orders:
        label = order.os_type or "Não identificado"
        type_counts[label] = type_counts.get(label, 0) + 1

    attended_regionals = sorted({order.regional or "Não identificada" for order in orders})
    cross_regional_orders = sum(
        1
        for order in orders
        if reference_regional and (order.regional or "Não identificada") != reference_regional
    )
    operational_window_orders = [
        order
        for order in orders
        if order.displacement_started_at is not None
        and (order.finished_at or order.closed_at) is not None
    ]

    return {
        "total_orders": len(orders),
        "active_days": len({order.closed_at.astimezone(OPERATIONS_TIMEZONE).date() for order in orders if order.closed_at is not None}),
        "timed_orders": len(execution_minutes),
        "missing_execution_times": len(orders) - len(execution_minutes),
        "average_execution_minutes": _average(execution_minutes),
        "median_execution_minutes": round(float(median(execution_minutes)), 2) if execution_minutes else None,
        "minimum_execution_minutes": min(execution_minutes) if execution_minutes else None,
        "maximum_execution_minutes": max(execution_minutes) if execution_minutes else None,
        "average_pre_displacement_minutes": _average(pre_displacement_minutes),
        "average_total_minutes": _average(total_minutes),
        "sla_rate": round(
            sum(1 for order in measurable_sla if order.sla_status == "on_time") / len(measurable_sla) * 100,
            2,
        ) if measurable_sla else None,
        "first_displacement_at": min(
            (order.displacement_started_at for order in operational_window_orders),
            default=None,
        ),
        "last_finished_at": max(
            ((order.finished_at or order.closed_at) for order in operational_window_orders),
            default=None,
        ),
        "operational_window_orders": len(operational_window_orders),
        "missing_operational_window_times": len(orders) - len(operational_window_orders),
        "total_execution_minutes": round(sum(execution_minutes), 2) if execution_minutes else None,
        "average_displacement_minutes": _average(displacement_minutes),
        "total_displacement_minutes": round(sum(displacement_minutes), 2) if displacement_minutes else None,
        "displacement_orders": len(displacement_minutes),
        "attended_regionals": attended_regionals,
        "cross_regional_orders": cross_regional_orders,
        "type_counts": dict(sorted(type_counts.items(), key=lambda item: (-item[1], item[0]))),
    }


def calendar_day_detail(
    db: Session,
    day: date,
    regional: str,
    responsible: str,
    user: User,
    *,
    group_by: Literal["regional", "collaborator"] = "regional",
    reference_regional: str | None = None,
    page: int,
    page_size: int,
    **filters,
) -> dict:
    orders = queries.calendar_day_metric_orders(
        db,
        day,
        regional,
        responsible,
        user,
        group_by=group_by,
        **filters,
    )
    return {
        "metrics": _calendar_day_metrics(orders, reference_regional),
        "orders": queries.calendar_order_page(
            db,
            day,
            regional,
            responsible,
            user,
            group_by=group_by,
            page=page,
            page_size=page_size,
            **filters,
        ),
    }


def calendar_week_detail(
    db: Session,
    date_from: date,
    date_to: date,
    regional: str,
    responsible: str,
    user: User,
    *,
    group_by: Literal["regional", "collaborator"] = "regional",
    reference_regional: str | None = None,
    page: int,
    page_size: int,
    **filters,
) -> dict:
    orders = queries.calendar_period_metric_orders(
        db,
        date_from,
        date_to,
        regional,
        responsible,
        user,
        group_by=group_by,
        **filters,
    )
    return {
        "metrics": _calendar_day_metrics(orders, reference_regional),
        "orders": queries.calendar_period_order_page(
            db,
            date_from,
            date_to,
            regional,
            responsible,
            user,
            group_by=group_by,
            page=page,
            page_size=page_size,
            **filters,
        ),
    }


def calendar_month_detail(
    db: Session,
    competence: date,
    regional: str,
    responsible: str,
    user: User,
    *,
    group_by: Literal["regional", "collaborator"] = "regional",
    reference_regional: str | None = None,
    page: int,
    page_size: int,
    **filters,
) -> dict:
    orders = queries.calendar_month_metric_orders(
        db,
        competence,
        regional,
        responsible,
        user,
        group_by=group_by,
        **filters,
    )
    execution_minutes = [
        duration
        for order in orders
        if (duration := _duration_minutes(order.execution_started_at, order.finished_at or order.closed_at)) is not None
    ]
    displacement_minutes = [
        duration
        for order in orders
        if (duration := _duration_minutes(order.displacement_started_at, order.execution_started_at)) is not None
    ]
    total_minutes = [
        duration
        for order in orders
        if (duration := _duration_minutes(order.opened_at, order.finished_at or order.closed_at)) is not None
    ]
    measurable_sla = [order for order in orders if order.sla_status in {"on_time", "out_of_time"}]
    regional_counts = Counter(order.regional or "Não identificada" for order in orders)
    attended_regionals = sorted(regional_counts)
    total_orders = len(orders)
    metrics = {
        "total_orders": total_orders,
        "active_days": len({order.closed_at.astimezone(OPERATIONS_TIMEZONE).date() for order in orders if order.closed_at is not None}),
        "timed_orders": len(execution_minutes),
        "missing_execution_times": total_orders - len(execution_minutes),
        "average_execution_minutes": _average(execution_minutes),
        "median_execution_minutes": round(float(median(execution_minutes)), 2) if execution_minutes else None,
        "average_total_minutes": _average(total_minutes),
        "total_execution_minutes": round(sum(execution_minutes), 2) if execution_minutes else None,
        "average_displacement_minutes": _average(displacement_minutes),
        "total_displacement_minutes": round(sum(displacement_minutes), 2) if displacement_minutes else None,
        "displacement_orders": len(displacement_minutes),
        "sla_rate": round(
            sum(1 for order in measurable_sla if order.sla_status == "on_time") / len(measurable_sla) * 100,
            2,
        ) if measurable_sla else None,
        "attended_regionals": attended_regionals,
        "cross_regional_orders": sum(
            quantity for branch, quantity in regional_counts.items() if reference_regional and branch != reference_regional
        ),
    }
    return {
        "metrics": metrics,
        "by_regional": [
            {"label": branch, "quantity": quantity, "percentage": round(quantity / total_orders * 100, 2)}
            for branch, quantity in sorted(regional_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "orders": queries.calendar_month_order_page(
            db,
            competence,
            regional,
            responsible,
            user,
            group_by=group_by,
            page=page,
            page_size=page_size,
            **filters,
        ),
    }


def _trend_group_start(day: date, granularity: str) -> date:
    if granularity == "week":
        return day - timedelta(days=day.weekday())
    if granularity == "month":
        return day.replace(day=1)
    return day


def overview_trends(
    db: Session,
    date_from: date,
    date_to: date,
    user: User,
    *,
    granularity: Literal["day", "week", "month"],
    **filters,
) -> dict:
    daily = queries.overview_trend_daily(db, date_from, date_to, user, **filters)
    grouped: dict[date, dict] = {}
    current = date_from
    while current <= date_to:
        group_key = _trend_group_start(current, granularity)
        item = grouped.setdefault(
            group_key,
            {
                "period_start": current,
                "period_end": current,
                "opened_operation": 0,
                "opened_associated": 0,
                "completed": 0,
                "completed_on_time": 0,
                "completed_out_of_time": 0,
            },
        )
        item["period_start"] = min(item["period_start"], current)
        item["period_end"] = max(item["period_end"], current)
        source = daily.get(current, {})
        for field in (
            "opened_operation",
            "opened_associated",
            "completed",
            "completed_on_time",
            "completed_out_of_time",
        ):
            item[field] += int(source.get(field, 0))
        current += timedelta(days=1)

    points = []
    cumulative_on_time = 0
    cumulative_measurable = 0
    for item in grouped.values():
        measurable = item["completed_on_time"] + item["completed_out_of_time"]
        cumulative_on_time += item["completed_on_time"]
        cumulative_measurable += measurable
        item["completed_unmeasurable"] = max(0, item["completed"] - measurable)
        item["sla_rate"] = round(item["completed_on_time"] / measurable * 100, 1) if measurable else None
        item["sla_cumulative_rate"] = (
            round(cumulative_on_time / cumulative_measurable * 100, 1)
            if cumulative_measurable
            else None
        )
        points.append(item)
    return {
        "granularity": granularity,
        "responsible_filter_active": bool(filters.get("responsibles")),
        "openings_ignore_responsibles": True,
        "points": points,
    }


def subject_volume_alerts(
    db: Session,
    reference_date: date,
    user: User,
    *,
    baseline_days: int = 56,
    recent_days: int = 7,
    **filters,
) -> dict:
    history_from = reference_date - timedelta(days=baseline_days + recent_days - 1)
    events = queries.subject_backlog_history(db, history_from, reference_date, user, **filters)
    opened_by_day: dict[date, dict[str, int]] = {}
    closed_by_day: dict[date, dict[str, int]] = {}
    for day, subject, quantity in events["opened"]:
        opened_by_day.setdefault(day, {})[subject] = quantity
    for day, subject, quantity in events["closed"]:
        closed_by_day.setdefault(day, {})[subject] = quantity

    all_subjects = set(events["initial"])
    all_subjects.update(subject for _, subject, _ in events["opened"])
    all_subjects.update(subject for _, subject, _ in events["closed"])
    current_counts = {subject: int(events["initial"].get(subject, 0)) for subject in all_subjects}
    history: dict[str, list[int]] = {subject: [] for subject in all_subjects}
    current = history_from
    while current <= reference_date:
        for subject in all_subjects:
            current_counts[subject] = max(
                0,
                int(current_counts.get(subject, 0))
                + int(opened_by_day.get(current, {}).get(subject, 0))
                - int(closed_by_day.get(current, {}).get(subject, 0)),
            )
            history[subject].append(int(current_counts.get(subject, 0)))
        current += timedelta(days=1)

    severity_order = {"critical": 3, "attention": 2, "normal": 1, "insufficient": 0}
    items = []
    for subject, values in history.items():
        baseline = values[:baseline_days]
        recent = values[baseline_days:]
        if not recent:
            continue
        expected = mean(baseline) if baseline else 0.0
        current_quantity = int(recent[-1])
        deviation = current_quantity - expected
        standard_deviation = pstdev(baseline) if len(baseline) >= 2 else 0.0
        z_score = deviation / standard_deviation if standard_deviation > 0 else None
        if len(baseline) < 14:
            status = "insufficient"
        elif deviation <= 0:
            status = "normal"
        elif z_score is not None:
            status = "critical" if z_score >= 2.5 else "attention" if z_score >= 1.5 else "normal"
        else:
            critical_floor = max(3.0, expected * 1.5)
            attention_floor = max(2.0, expected * 1.25)
            status = "critical" if current_quantity >= critical_floor else "attention" if current_quantity >= attention_floor else "normal"
        if current_quantity <= 0 and expected <= 0:
            continue
        items.append(
            {
                "subject": subject,
                "current_backlog": current_quantity,
                "recent_average": round(mean(recent), 1),
                "expected_backlog": round(expected, 1),
                "deviation_percentage": round(deviation / expected * 100, 1) if expected > 0 else None,
                "z_score": round(z_score, 2) if z_score is not None else None,
                "status": status,
                "sample_days": len(baseline),
            }
        )
    items.sort(
        key=lambda item: (
            -severity_order[item["status"]],
            -(item["z_score"] or 0),
            -item["current_backlog"],
            item["subject"],
        )
    )
    return {
        "reference_date": reference_date,
        "baseline_days": baseline_days,
        "recent_days": recent_days,
        "responsibles_ignored": True,
        "items": items[:20],
    }


def _control_daily(rows: list[tuple[date, str, int]]) -> dict[str, dict[date, int]]:
    result: dict[str, dict[date, int]] = {}
    for day, label, quantity in rows:
        result.setdefault(label, {})[day] = int(quantity)
    return result


def _weekday_expectation(day: date, daily: dict[date, int], baseline_weeks: int) -> tuple[float, float]:
    samples = [int(daily.get(day - timedelta(days=7 * offset), 0)) for offset in range(1, baseline_weeks + 1)]
    expected = mean(samples) if samples else 0.0
    deviation = pstdev(samples) if len(samples) >= 2 else 0.0
    upper_limit = max(expected + (2 * deviation), expected * 1.35, expected + 2)
    return expected, upper_limit


def _control_metrics(
    daily_opened: dict[date, int],
    daily_completed: dict[date, int],
    reference_date: date,
    *,
    recent_days: int,
    baseline_weeks: int,
    available_weeks: int,
    backlog: int,
    overdue_backlog: int,
    average_backlog_age_hours: float | None,
) -> dict:
    recent_dates = [reference_date - timedelta(days=offset) for offset in reversed(range(recent_days))]
    opened_recent = sum(int(daily_opened.get(day, 0)) for day in recent_dates)
    completed_recent = sum(int(daily_completed.get(day, 0)) for day in recent_dates)
    expectations = [_weekday_expectation(day, daily_opened, baseline_weeks) for day in recent_dates]
    expected_opened = sum(item[0] for item in expectations)
    outside = [int(daily_opened.get(day, 0)) > expectation[1] for day, expectation in zip(recent_dates, expectations)]
    persistent_days = 0
    for is_outside in reversed(outside):
        if not is_outside:
            break
        persistent_days += 1

    net_flow = opened_recent - completed_recent
    pressure_ratio = opened_recent / completed_recent if completed_recent > 0 else None
    deviation_percentage = ((opened_recent - expected_opened) / expected_opened * 100) if expected_opened > 0 else None
    overdue_rate = overdue_backlog / backlog if backlog > 0 else 0.0
    has_meaningful_volume = opened_recent >= 3
    positive_deviation = deviation_percentage or 0.0

    if available_weeks < 4:
        status = "insufficient"
    elif (
        (persistent_days >= 3 and positive_deviation >= 25)
        or (has_meaningful_volume and positive_deviation >= 50 and (pressure_ratio or 0) >= 1.2 and net_flow > 0)
        or (opened_recent >= 5 and positive_deviation >= 25 and (pressure_ratio or 0) >= 1.5 and net_flow > 0)
        or (positive_deviation >= 25 and backlog >= 5 and overdue_rate >= 0.5 and net_flow > 0)
    ):
        status = "critical"
    elif (
        persistent_days >= 1
        or (has_meaningful_volume and positive_deviation >= 25)
        or (positive_deviation > 0 and (pressure_ratio or 0) >= 1.1 and net_flow > 0)
        or (positive_deviation > 0 and backlog >= 5 and overdue_rate >= 0.3 and net_flow > 0)
    ):
        status = "attention"
    else:
        status = "normal"

    # Explica o status em linguagem direta - a classificação acima combina 8 condições em OR e sem
    # isso o usuário via só o resultado ("crítico") sem entender qual sinal específico disparou.
    reasons: list[str] = []
    if status in ("critical", "attention"):
        if persistent_days >= 1:
            reasons.append(f"{persistent_days} dia(s) consecutivo(s) com aberturas acima do limite esperado.")
        if positive_deviation > 0:
            reasons.append(f"Aberturas {round(positive_deviation)}% acima do esperado para o período.")
        if (pressure_ratio or 0) >= 1.1 and net_flow > 0:
            reasons.append(f"Entrando {round(pressure_ratio, 1)}x mais O.S. do que a equipe está finalizando.")
        if backlog >= 5 and overdue_rate >= 0.3 and net_flow > 0:
            reasons.append(f"{round(overdue_rate * 100)}% do backlog já está vencido, com o estoque crescendo.")
        if not reasons:
            reasons.append("Padrão de entrada fora do esperado para o período.")
        if opened_recent < 10:
            # Com poucas O.S. no total, um desvio grande em % (ex.: 5 O.S. quando 2 eram esperadas)
            # já dispara o alerta neste nível agregado, mas some quando espalhado por regional/cidade/
            # setor/responsável - cada recorte menor fica sem volume suficiente para acionar o mesmo
            # limite (o alerta exige pelo menos 3 O.S. recentes para considerar o desvio significativo).
            # Sem essa nota, parece contraditório "crítico aqui, normal em todo filho".
            reasons.append(
                f"Volume baixo em números absolutos ({opened_recent} O.S. no total) - por isso o alerta "
                "aparece neste recorte agregado, mas pode não repetir em cada regional/cidade/setor "
                "aberto individualmente, já que cada um recebe uma fração ainda menor dessas O.S."
            )

    return {
        "status": status,
        "opened_recent": opened_recent,
        "expected_opened": round(expected_opened, 1),
        "deviation_percentage": round(deviation_percentage, 1) if deviation_percentage is not None else None,
        "completed_recent": completed_recent,
        "net_flow": net_flow,
        "pressure_ratio": round(pressure_ratio, 2) if pressure_ratio is not None else None,
        "backlog": backlog,
        "overdue_backlog": overdue_backlog,
        "average_backlog_age_hours": round(average_backlog_age_hours, 1) if average_backlog_age_hours is not None else None,
        "persistent_days": persistent_days,
        "reasons": reasons,
    }


def control_tower(
    db: Session,
    reference_date: date,
    user: User,
    *,
    level: Literal["subject", "regional", "city", "sector", "responsible"] = "subject",
    path: dict[str, str | None] | None = None,
    recent_days: int = 7,
    baseline_weeks: int = 8,
    timeline_days: int = 28,
    **filters,
) -> dict:
    path = {key: value for key, value in (path or {}).items() if value}
    history_from = reference_date - timedelta(days=timeline_days + baseline_weeks * 7 - 1)
    aggregates = queries.control_tower_aggregates(
        db,
        history_from,
        reference_date,
        level,
        user,
        path=path,
        **filters,
    )
    opened = _control_daily(aggregates["opened"])
    completed = _control_daily(aggregates["completed"])
    backlog_data = aggregates["backlog"]
    labels = set(opened) | set(completed) | set(backlog_data)

    recent_start = reference_date - timedelta(days=recent_days - 1)
    earliest_event = min(
        (day for rows in (*opened.values(), *completed.values()) for day in rows),
        default=recent_start,
    )
    available_weeks = min(baseline_weeks, max(0, (recent_start - earliest_event).days // 7))
    items = []
    for label in labels:
        stock = backlog_data.get(label, {})
        metrics = _control_metrics(
            opened.get(label, {}),
            completed.get(label, {}),
            reference_date,
            recent_days=recent_days,
            baseline_weeks=baseline_weeks,
            available_weeks=available_weeks,
            backlog=int(stock.get("quantity", 0)),
            overdue_backlog=int(stock.get("overdue", 0)),
            average_backlog_age_hours=stock.get("average_age_hours"),
        )
        items.append(
            {
                "label": label,
                "level": level,
                "path": {**path, level: label},
                **metrics,
                "has_children": level != CONTROL_TOWER_LEVELS[-1],
            }
        )

    severity = {"critical": 3, "attention": 2, "normal": 1, "insufficient": 0}
    items.sort(
        key=lambda item: (
            -severity[item["status"]],
            -(item["deviation_percentage"] or 0),
            -item["backlog"],
            item["label"].casefold(),
        )
    )

    total_opened: dict[date, int] = {}
    total_completed: dict[date, int] = {}
    for daily in opened.values():
        for day, quantity in daily.items():
            total_opened[day] = total_opened.get(day, 0) + quantity
    for daily in completed.values():
        for day, quantity in daily.items():
            total_completed[day] = total_completed.get(day, 0) + quantity

    total_backlog = sum(int(item.get("quantity", 0)) for item in backlog_data.values())
    total_overdue = sum(int(item.get("overdue", 0)) for item in backlog_data.values())
    weighted_age_total = sum(
        float(item.get("average_age_hours") or 0) * int(item.get("quantity", 0))
        for item in backlog_data.values()
    )
    average_age = weighted_age_total / total_backlog if total_backlog else None
    summary = _control_metrics(
        total_opened,
        total_completed,
        reference_date,
        recent_days=recent_days,
        baseline_weeks=baseline_weeks,
        available_weeks=available_weeks,
        backlog=total_backlog,
        overdue_backlog=total_overdue,
        average_backlog_age_hours=average_age,
    )
    summary["critical_nodes"] = sum(1 for item in items if item["status"] == "critical")
    summary["attention_nodes"] = sum(1 for item in items if item["status"] == "attention")
    if summary["status"] == "normal" and (summary["critical_nodes"] or summary["attention_nodes"]):
        summary["status"] = "attention"
        summary["reasons"] = [
            f"{summary['critical_nodes']} assunto(s) crítico(s) e {summary['attention_nodes']} em atenção, "
            "mesmo com o total geral dentro do esperado."
        ]

    timeline_dates = [reference_date - timedelta(days=offset) for offset in reversed(range(timeline_days))]
    running_backlog = total_backlog
    backlog_by_day: dict[date, int] = {}
    for day in reversed(timeline_dates):
        backlog_by_day[day] = running_backlog
        running_backlog = max(
            0,
            running_backlog - int(total_opened.get(day, 0)) + int(total_completed.get(day, 0)),
        )
    timeline = []
    for day in timeline_dates:
        expected, upper_limit = _weekday_expectation(day, total_opened, baseline_weeks)
        actual = int(total_opened.get(day, 0))
        timeline.append(
            {
                "date": day,
                "opened": actual,
                "completed": int(total_completed.get(day, 0)),
                "expected_opened": round(expected, 1),
                "upper_limit": round(upper_limit, 1),
                "outside_expected": actual > upper_limit,
                "backlog": backlog_by_day[day],
            }
        )

    current_index = CONTROL_TOWER_LEVELS.index(level)
    next_level = CONTROL_TOWER_LEVELS[current_index + 1] if current_index + 1 < len(CONTROL_TOWER_LEVELS) else None
    return {
        "reference_date": reference_date,
        "level": level,
        "next_level": next_level,
        "path": path,
        "recent_days": recent_days,
        "baseline_weeks": baseline_weeks,
        "timeline_days": timeline_days,
        "responsibles_ignored": True,
        "calculation_note": "Compara cada dia com o mesmo dia da semana nas 8 semanas anteriores e combina desvio, persistência, entradas versus finalizações e backlog vencido.",
        "summary": summary,
        "timeline": timeline,
        "items": items[:30] if level == "subject" else items[:50],
    }
