from __future__ import annotations

import calendar
import math
from collections import defaultdict
from datetime import date, datetime, time, timezone

from sqlalchemy import Date, Integer, String, and_, case, cast, func, or_, select
from sqlalchemy.orm import Session

from app.models import User
from app.services.regional import effective_managed_regionals

from .models import OperationImportRun, OperationIxcCollaborator, OperationOrder, OperationResponsibleAssignment, OperationResponsibleDirectorySetting, OperationSubjectTypeMapping, OperationTeamModel
from .period import OPERATIONS_TIMEZONE, OPERATIONS_TIMEZONE_NAME, local_period_utc_bounds, operations_period_bounds
from .scope import ALL_SECTOR_NAMES


FILTER_COLUMNS = {
    "companies": OperationOrder.company_id,
    "regionals": OperationOrder.regional,
    "states": OperationOrder.state,
    "cities": OperationOrder.city,
    "contract_types": OperationOrder.contract_type,
    "person_types": OperationOrder.person_type,
    "os_types": OperationOrder.os_type,
    "subjects": OperationOrder.os_subject,
    "diagnoses": OperationOrder.diagnosis,
    "departments": OperationOrder.department,
    "sectors": OperationOrder.sector,
    "priorities": OperationOrder.priority,
    "creators": OperationOrder.creator,
    "responsibles": OperationOrder.responsible,
    # Filtro por id do tecnico no IXC (Collaborator.ixc_employee_id no lado da gamificacao) - alem
    # do filtro por nome acima, permite que a gamificacao passe o mesmo colaborador com garantia de
    # ser a mesma pessoa, sem depender de o nome bater exatamente (ver operations_sync.py).
    "responsible_ixc_ids": OperationOrder.responsible_ixc_id,
    "statuses": OperationOrder.status,
    "sla_statuses": OperationOrder.sla_status,
    "projects": OperationOrder.project,
    "pops": OperationOrder.pop,
}

CONTROL_TOWER_COLUMNS = {
    "subject": OperationOrder.os_subject,
    "regional": OperationOrder.regional,
    "city": OperationOrder.city,
    "sector": OperationOrder.sector,
    "responsible": OperationOrder.responsible,
}

CONTROL_TOWER_PATH_FIELDS = {
    "subject": OperationOrder.os_subject,
    "regional": OperationOrder.regional,
    "city": OperationOrder.city,
    "sector": OperationOrder.sector,
}

UNIDENTIFIED_LABEL = "Não identificado"

SEARCH_COLUMNS = (
    OperationOrder.order_code,
    OperationOrder.protocol,
    OperationOrder.contract_id,
    OperationOrder.customer_login,
    OperationOrder.customer_name,
    OperationOrder.company_id,
    OperationOrder.regional,
    OperationOrder.state,
    OperationOrder.city,
    OperationOrder.contract_type,
    OperationOrder.person_type,
    OperationOrder.os_type,
    OperationOrder.os_subject,
    OperationOrder.diagnosis,
    OperationOrder.department,
    OperationOrder.sector,
    OperationOrder.priority,
    OperationOrder.creator,
    OperationOrder.responsible,
    OperationOrder.project,
    OperationOrder.pop,
)


def _query_conditions(
    date_from: date,
    date_to: date,
    user: User,
    filters: dict,
    *,
    exclude_filter: str | None = None,
) -> tuple[list, datetime, datetime]:
    start, end = local_period_utc_bounds(date_from, date_to)
    conditions = [
        or_(
            OperationOrder.opened_at.between(start, end),
            OperationOrder.closed_at.between(start, end),
        )
    ]
    conditions.extend(_dimension_conditions(user, filters, exclude_filter=exclude_filter))
    return conditions, start, end


def _opening_filters(filters: dict) -> dict:
    """Openings are operational demand, independent from the executing team."""
    return {**filters, "responsibles": [], "team_models": []}


def _dimension_conditions(
    user: User,
    filters: dict,
    *,
    exclude_filter: str | None = None,
) -> list:
    conditions: list = []
    # O escopo regional pertence ao usuário, não ao filtro enviado pela tela.
    # Assim, uma visão global ou uma chamada direta à API nunca amplia o acesso.
    # A lista é normalizada e sem duplicatas em effective_managed_regionals.
    allowed_regionals = effective_managed_regionals(user.managed_regional, user.managed_regionals)
    if allowed_regionals:
        conditions.append(OperationOrder.regional.in_(allowed_regionals))
    elif user.role == "regional_manager_viewer":
        # Gestores regionais sem configuração explícita não podem receber um
        # escopo implícito de "todas as regionais".
        conditions.append(OperationOrder.id == -1)
    selected_team_models = filters.get("team_models")
    if selected_team_models and exclude_filter != "team_models":
        assigned_to_model = (
            select(OperationResponsibleAssignment.id)
            .join(
                OperationTeamModel,
                OperationTeamModel.id == OperationResponsibleAssignment.team_model_id,
            )
            .where(
                func.lower(OperationResponsibleAssignment.responsible_name) == func.lower(OperationOrder.responsible),
                OperationTeamModel.name.in_(selected_team_models),
            )
            .exists()
        )
        conditions.append(assigned_to_model)
    for api_field, column in FILTER_COLUMNS.items():
        if api_field == exclude_filter:
            continue
        selected = filters.get(api_field)
        if selected:
            conditions.append(column.in_(selected))
    search = str(filters.get("search") or "").strip()
    if search:
        pattern = f"%{search}%"
        conditions.append(or_(*(cast(column, String).ilike(pattern) for column in SEARCH_COLUMNS)))
    closed_time_from = filters.get("closed_time_from")
    closed_time_to = filters.get("closed_time_to")
    if closed_time_from or closed_time_to:
        start_time = time.fromisoformat(str(closed_time_from)) if closed_time_from else None
        end_time = time.fromisoformat(str(closed_time_to)) if closed_time_to else None
        utc_minutes = cast(func.extract("hour", OperationOrder.closed_at), Integer) * 60 + cast(
            func.extract("minute", OperationOrder.closed_at), Integer
        )
        # America/Porto_Velho permanece em UTC-4. A aritmética por minuto é
        # portável entre PostgreSQL e SQLite, usado nos testes.
        local_minutes = (utc_minutes - 240 + 1440) % 1440
        start_minutes = start_time.hour * 60 + start_time.minute if start_time else None
        end_minutes = end_time.hour * 60 + end_time.minute if end_time else None
        if start_minutes is not None and end_minutes is not None:
            if start_minutes <= end_minutes:
                conditions.append(local_minutes.between(start_minutes, end_minutes))
            else:
                conditions.append(or_(local_minutes >= start_minutes, local_minutes <= end_minutes))
        elif start_minutes is not None:
            conditions.append(local_minutes >= start_minutes)
        elif end_minutes is not None:
            conditions.append(local_minutes <= end_minutes)
    return conditions


def _as_utc(value: datetime) -> datetime:
    # SQLite usado nos testes remove o tzinfo ao desserializar DateTime. Os dados
    # do módulo são persistidos em UTC, portanto o fallback explícito é seguro.
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _inside(value: datetime | None, start: datetime, end: datetime) -> bool:
    return bool(value and start <= _as_utc(value) <= end)


def _period_orders(db: Session, date_from: date, date_to: date, user: User) -> list[OperationOrder]:
    conditions, _, _ = _query_conditions(date_from, date_to, user, {})
    stmt = select(OperationOrder).where(*conditions)
    return list(db.scalars(stmt.order_by(OperationOrder.opened_at.desc(), OperationOrder.id.desc())))


def _matches(
    order: OperationOrder,
    *,
    companies: list[str] | None = None,
    regionals: list[str] | None = None,
    states: list[str] | None = None,
    cities: list[str] | None = None,
    contract_types: list[str] | None = None,
    person_types: list[str] | None = None,
    os_types: list[str] | None = None,
    subjects: list[str] | None = None,
    diagnoses: list[str] | None = None,
    departments: list[str] | None = None,
    sectors: list[str] | None = None,
    priorities: list[str] | None = None,
    creators: list[str] | None = None,
    responsibles: list[str] | None = None,
    statuses: list[str] | None = None,
    sla_statuses: list[str] | None = None,
    projects: list[str] | None = None,
    pops: list[str] | None = None,
    closed_time_from: str | None = None,
    closed_time_to: str | None = None,
    search: str | None = None,
) -> bool:
    pairs = (
        (companies, order.company_id),
        (regionals, order.regional),
        (states, order.state),
        (cities, order.city),
        (contract_types, order.contract_type),
        (person_types, order.person_type),
        (os_types, order.os_type),
        (subjects, order.os_subject),
        (diagnoses, order.diagnosis),
        (departments, order.department),
        (sectors, order.sector),
        (priorities, order.priority),
        (creators, order.creator),
        (responsibles, order.responsible),
        (statuses, order.status),
        (sla_statuses, order.sla_status),
        (projects, order.project),
        (pops, order.pop),
    )
    if any(expected and actual not in expected for expected, actual in pairs):
        return False
    if closed_time_from or closed_time_to:
        if order.closed_at is None:
            return False
        local_time = _as_utc(order.closed_at).astimezone(OPERATIONS_TIMEZONE).time()
        start_time = time.fromisoformat(closed_time_from) if closed_time_from else None
        end_time = time.fromisoformat(closed_time_to) if closed_time_to else None
        if start_time and end_time:
            inside = start_time <= local_time <= end_time if start_time <= end_time else local_time >= start_time or local_time <= end_time
            if not inside:
                return False
        elif start_time and local_time < start_time:
            return False
        elif end_time and local_time > end_time:
            return False
    if search:
        needle = search.casefold().strip()
        haystack = " ".join(
            str(value or "")
            for value in (
                order.order_code,
                order.protocol,
                order.contract_id,
                order.customer_login,
                order.customer_name,
                order.company_id,
                order.regional,
                order.state,
                order.city,
                order.contract_type,
                order.person_type,
                order.os_type,
                order.os_subject,
                order.diagnosis,
                order.department,
                order.sector,
                order.priority,
                order.creator,
                order.responsible,
                order.project,
                order.pop,
            )
        ).casefold()
        if needle not in haystack:
            return False
    return True


def filtered_orders(db: Session, date_from: date, date_to: date, user: User, **filters) -> list[OperationOrder]:
    conditions, _, _ = _query_conditions(date_from, date_to, user, filters)
    return list(
        db.scalars(
            select(OperationOrder)
            .where(*conditions)
            .order_by(OperationOrder.opened_at.desc(), OperationOrder.id.desc())
        )
    )


def filter_options(
    db: Session,
    date_from: date,
    date_to: date,
    user: User,
    *,
    responsible_mode: str = "all",
    scope: str = "period",
    **filters,
) -> dict:
    result: dict[str, list[str]] = {}
    result["team_models"] = list(
        db.scalars(
            select(OperationTeamModel.name)
            .where(OperationTeamModel.active.is_(True))
            .order_by(OperationTeamModel.name)
        )
    )
    for api_field, column in FILTER_COLUMNS.items():
        if api_field == "sectors":
            result[api_field] = list(ALL_SECTOR_NAMES)
            continue
        if scope == "in_progress":
            conditions = _dimension_conditions(user, filters, exclude_filter=api_field)
            conditions.append(OperationOrder.is_closed.is_(False))
        else:
            conditions, start, end = _query_conditions(
                date_from,
                date_to,
                user,
                filters,
                exclude_filter=api_field,
            )
            if api_field == "responsibles" and responsible_mode == "completed":
                conditions.append(OperationOrder.closed_at.between(start, end))
        # responsible_ixc_ids e uma coluna Integer - "!= ''" nao se aplica (e ate quebra no
        # Postgres, que nao compara integer com string vazia).
        extra_conditions = [column.is_not(None)] if api_field == "responsible_ixc_ids" else [column.is_not(None), column != ""]
        values = db.scalars(select(column).where(*conditions, *extra_conditions).distinct())
        if api_field == "responsible_ixc_ids":
            result[api_field] = sorted({int(value) for value in values})
        else:
            result[api_field] = sorted({str(value) for value in values}, key=str.casefold)
    directory = db.get(OperationResponsibleDirectorySetting, 1)
    source = directory.source if directory else "orders"
    if source in {"ixc", "both"}:
        ixc_names = set(
            db.scalars(
                select(OperationIxcCollaborator.name).where(OperationIxcCollaborator.active.is_(True))
            )
        )
        selected_models = filters.get("team_models") or []
        if selected_models:
            allowed_identities = {
                " ".join(name.casefold().split())
                for name in db.scalars(
                    select(OperationResponsibleAssignment.responsible_name)
                    .join(OperationTeamModel, OperationTeamModel.id == OperationResponsibleAssignment.team_model_id)
                    .where(OperationTeamModel.name.in_(selected_models))
                )
            }
            ixc_names = {
                name
                for name in ixc_names
                if " ".join(name.casefold().split()) in allowed_identities
            }
        result["responsibles"] = sorted(
            ixc_names if source == "ixc" else set(result["responsibles"]) | ixc_names,
            key=str.casefold,
        )
    return result


def overview(db: Session, date_from: date, date_to: date, user: User, **filters) -> dict:
    conditions, start, end = _query_conditions(date_from, date_to, user, filters)
    opening_conditions, _, _ = _query_conditions(
        date_from,
        date_to,
        user,
        _opening_filters(filters),
    )
    opened = OperationOrder.opened_at.between(start, end)
    completed = OperationOrder.closed_at.between(start, end)
    row = db.execute(
        select(
            func.sum(case((opened, 1), else_=0)),
            func.sum(case((completed, 1), else_=0)),
            func.sum(case((and_(completed, OperationOrder.sla_status == "on_time"), 1), else_=0)),
            func.sum(case((and_(completed, OperationOrder.sla_status == "out_of_time"), 1), else_=0)),
            func.avg(case((completed, OperationOrder.elapsed_hours), else_=None)),
        ).where(*conditions)
    ).one()
    # Backlog is a current stock: it deliberately ignores the selected dates.
    backlog_conditions = [
        *_dimension_conditions(user, filters),
        OperationOrder.is_closed.is_(False),
    ]
    backlog_row = db.execute(
        select(
            func.count(OperationOrder.id),
            func.sum(case((OperationOrder.sla_status == "out_of_time", 1), else_=0)),
        ).where(*backlog_conditions)
    ).one()
    opened_associated_count = int(row[0] or 0)
    opened_count = int(
        db.scalar(
            select(func.count(OperationOrder.id)).where(
                *opening_conditions,
                OperationOrder.opened_at.between(start, end),
            )
        )
        or 0
    )
    completed_count = int(row[1] or 0)
    in_progress_count = int(backlog_row[0] or 0)
    opened_out = int(backlog_row[1] or 0)
    completed_on_time = int(row[2] or 0)
    completed_out = int(row[3] or 0)
    measurable_count = completed_on_time + completed_out
    timeline_rows = db.execute(
        select(
            OperationOrder.opened_at,
            OperationOrder.displacement_started_at,
            OperationOrder.finished_at,
            OperationOrder.closed_at,
        ).where(*conditions, completed)
    ).all()
    wait_minutes = [
        (displacement_started_at - opened_at).total_seconds() / 60
        for opened_at, displacement_started_at, _, _ in timeline_rows
        if opened_at is not None and displacement_started_at is not None and displacement_started_at >= opened_at
    ]
    cycle_minutes = [
        ((finished_at or closed_at) - opened_at).total_seconds() / 60
        for opened_at, _, finished_at, closed_at in timeline_rows
        if opened_at is not None and (finished_at or closed_at) is not None and (finished_at or closed_at) >= opened_at
    ]
    days = max(1, (date_to - date_from).days + 1)
    return {
        "opened": opened_count,
        "opened_associated": opened_associated_count,
        "responsible_filter_active": bool(filters.get("responsibles") or filters.get("team_models")),
        "completed": completed_count,
        "in_progress": in_progress_count,
        "opened_out_of_time": opened_out,
        "completed_on_time": completed_on_time,
        "completed_out_of_time": completed_out,
        "sla_rate": round((completed_on_time / measurable_count) * 100, 1) if measurable_count else None,
        "average_daily_opened": round(opened_count / days, 1),
        "average_daily_completed": round(completed_count / days, 1),
        "average_closing_hours": round(float(row[4]), 2) if row[4] is not None else None,
        "average_wait_to_displacement_minutes": round(sum(wait_minutes) / len(wait_minutes), 2) if wait_minutes else None,
        "average_cycle_minutes": round(sum(cycle_minutes) / len(cycle_minutes), 2) if cycle_minutes else None,
    }


def work_schedule_orders(db: Session, date_from: date, date_to: date, user: User, **filters):
    conditions, start, end = _query_conditions(date_from, date_to, user, filters)
    return list(
        db.scalars(
            select(OperationOrder).where(
                *conditions,
                OperationOrder.closed_at.between(start, end),
                OperationOrder.is_closed.is_(True),
            )
        )
    )


def sla_breakdown(db: Session, date_from: date, date_to: date, user: User, group_by: str, **filters) -> list[dict]:
    allowed_groups = {
        "os_type": OperationOrder.os_type,
        "subject": OperationOrder.os_subject,
        "diagnosis": OperationOrder.diagnosis,
        "department": OperationOrder.department,
        "sector": OperationOrder.sector,
    }
    field = allowed_groups.get(group_by, OperationOrder.os_type)
    conditions, start, end = _query_conditions(date_from, date_to, user, filters)
    label = func.coalesce(field, "Não identificado")
    elapsed = OperationOrder.elapsed_hours
    rows = db.execute(
        select(
            label,
            func.count(OperationOrder.id),
            func.sum(case((OperationOrder.sla_status == "on_time", 1), else_=0)),
            func.sum(case((OperationOrder.sla_status == "out_of_time", 1), else_=0)),
            func.sum(case((and_(elapsed.is_not(None), elapsed <= 12), 1), else_=0)),
            func.sum(case((and_(elapsed > 12, elapsed <= 24), 1), else_=0)),
            func.sum(case((and_(elapsed > 24, elapsed <= 48), 1), else_=0)),
            func.sum(case((and_(elapsed > 48, elapsed <= 72), 1), else_=0)),
            func.sum(case((elapsed > 72, 1), else_=0)),
            func.avg(elapsed),
        )
        .where(*conditions, OperationOrder.closed_at.between(start, end))
        .group_by(label)
    ).all()
    result: list[dict] = []
    for row in rows:
        completed_count = int(row[1] or 0)
        on_time = int(row[2] or 0)
        out_of_time = int(row[3] or 0)
        measurable_count = on_time + out_of_time
        result.append(
            {
                "label": str(row[0]),
                "completed": completed_count,
                "on_time": on_time,
                "out_of_time": out_of_time,
                "sla_rate": round((on_time / measurable_count) * 100, 1) if measurable_count else None,
                "up_to_12h": int(row[4] or 0),
                "from_12h_to_24h": int(row[5] or 0),
                "from_24h_to_48h": int(row[6] or 0),
                "from_48h_to_72h": int(row[7] or 0),
                "after_72h": int(row[8] or 0),
                "average_closing_hours": round(float(row[9]), 2) if row[9] is not None else None,
            }
        )
    return sorted(result, key=lambda item: (-item["completed"], item["label"]))


def _sla_percentage(value: int, total: int) -> float | None:
    return round((value / total) * 100, 1) if total else None


def _normalized_dimension(column, fallback: str = "Não identificado"):
    return func.coalesce(func.nullif(func.trim(column), ""), fallback)


def sla_hierarchy(
    db: Session,
    date_from: date,
    date_to: date,
    user: User,
    level: str,
    *,
    parent_os_type: str | None = None,
    parent_subject: str | None = None,
    **filters,
) -> dict:
    fields = {
        "os_type": OperationOrder.os_type,
        "subject": OperationOrder.os_subject,
        "diagnosis": OperationOrder.diagnosis,
    }
    field = fields[level]
    conditions, start, end = _query_conditions(date_from, date_to, user, filters)
    if parent_os_type is not None:
        conditions.append(_normalized_dimension(OperationOrder.os_type) == parent_os_type)
    if parent_subject is not None:
        conditions.append(_normalized_dimension(OperationOrder.os_subject) == parent_subject)

    elapsed = OperationOrder.elapsed_hours
    valid_elapsed = and_(elapsed.is_not(None), elapsed >= 0)
    label = _normalized_dimension(field)
    rows = db.execute(
        select(
            label,
            func.count(OperationOrder.id),
            func.sum(case((OperationOrder.sla_status == "on_time", 1), else_=0)),
            func.sum(case((OperationOrder.sla_status == "out_of_time", 1), else_=0)),
            func.sum(case((valid_elapsed, 1), else_=0)),
            func.sum(case((and_(valid_elapsed, elapsed <= 12), 1), else_=0)),
            func.sum(case((and_(valid_elapsed, elapsed > 12, elapsed <= 24), 1), else_=0)),
            func.sum(case((and_(valid_elapsed, elapsed > 24, elapsed <= 48), 1), else_=0)),
            func.sum(case((and_(valid_elapsed, elapsed > 48, elapsed <= 72), 1), else_=0)),
            func.sum(case((and_(valid_elapsed, elapsed > 72), 1), else_=0)),
            func.avg(case((valid_elapsed, elapsed), else_=None)),
        )
        .where(*conditions, OperationOrder.closed_at.between(start, end))
        .group_by(label)
    ).all()

    totals = {
        "completed": 0,
        "on_time": 0,
        "out_of_time": 0,
        "timed_orders": 0,
        "up_to_12h": 0,
        "from_12h_to_24h": 0,
        "from_24h_to_48h": 0,
        "from_48h_to_72h": 0,
        "after_72h": 0,
        "elapsed_sum": 0.0,
    }

    def metric(row, metric_label: str) -> dict:
        completed = int(row[1] or 0)
        on_time = int(row[2] or 0)
        out_of_time = int(row[3] or 0)
        timed_orders = int(row[4] or 0)
        buckets = [int(row[index] or 0) for index in range(5, 10)]
        average = float(row[10]) if row[10] is not None else None
        return {
            "label": metric_label,
            "completed": completed,
            "on_time": on_time,
            "out_of_time": out_of_time,
            "sla_rate": _sla_percentage(on_time, on_time + out_of_time),
            "timed_orders": timed_orders,
            "up_to_12h_rate": _sla_percentage(buckets[0], timed_orders),
            "from_12h_to_24h_rate": _sla_percentage(buckets[1], timed_orders),
            "from_24h_to_48h_rate": _sla_percentage(buckets[2], timed_orders),
            "from_48h_to_72h_rate": _sla_percentage(buckets[3], timed_orders),
            "after_72h_rate": _sla_percentage(buckets[4], timed_orders),
            "average_closing_hours": round(average, 2) if average is not None else None,
        }

    items = []
    for row in rows:
        item = metric(row, str(row[0]))
        items.append(item)
        totals["completed"] += item["completed"]
        totals["on_time"] += item["on_time"]
        totals["out_of_time"] += item["out_of_time"]
        totals["timed_orders"] += item["timed_orders"]
        for target, index in (
            ("up_to_12h", 5),
            ("from_12h_to_24h", 6),
            ("from_24h_to_48h", 7),
            ("from_48h_to_72h", 8),
            ("after_72h", 9),
        ):
            totals[target] += int(row[index] or 0)
        if row[10] is not None:
            totals["elapsed_sum"] += float(row[10]) * item["timed_orders"]

    total_timed = int(totals["timed_orders"])
    total_on_time = int(totals["on_time"])
    total_out_of_time = int(totals["out_of_time"])
    total = {
        "label": "Total ponderado",
        "completed": int(totals["completed"]),
        "on_time": total_on_time,
        "out_of_time": total_out_of_time,
        "sla_rate": _sla_percentage(total_on_time, total_on_time + total_out_of_time),
        "timed_orders": total_timed,
        "up_to_12h_rate": _sla_percentage(int(totals["up_to_12h"]), total_timed),
        "from_12h_to_24h_rate": _sla_percentage(int(totals["from_12h_to_24h"]), total_timed),
        "from_24h_to_48h_rate": _sla_percentage(int(totals["from_24h_to_48h"]), total_timed),
        "from_48h_to_72h_rate": _sla_percentage(int(totals["from_48h_to_72h"]), total_timed),
        "after_72h_rate": _sla_percentage(int(totals["after_72h"]), total_timed),
        "average_closing_hours": round(float(totals["elapsed_sum"]) / total_timed, 2) if total_timed else None,
    }
    return {
        "level": level,
        "parent_os_type": parent_os_type,
        "parent_subject": parent_subject,
        "items": sorted(items, key=lambda item: (-item["completed"], item["label"])),
        "total": total,
    }


def _local_date(db: Session, column):
    """Data no fuso operacional, compatível com PostgreSQL e SQLite."""
    if db.get_bind().dialect.name == "postgresql":
        return cast(func.timezone(OPERATIONS_TIMEZONE_NAME, column), Date)
    # America/Porto_Velho é UTC-4 e não adota horário de verão.
    return func.date(column, "-4 hours")


def _local_closed_date(db: Session):
    return _local_date(db, OperationOrder.closed_at)


def _date_value(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def overview_trend_daily(
    db: Session,
    date_from: date,
    date_to: date,
    user: User,
    **filters,
) -> dict[date, dict[str, int]]:
    """Agrega os eventos por dia sem enviar linhas de O.S. ao frontend."""
    start, end = local_period_utc_bounds(date_from, date_to)
    full_conditions = _dimension_conditions(user, filters)
    opening_conditions = _dimension_conditions(user, _opening_filters(filters))
    opened_day = _local_date(db, OperationOrder.opened_at)
    closed_day = _local_date(db, OperationOrder.closed_at)

    opened_operation = db.execute(
        select(opened_day, func.count(OperationOrder.id))
        .where(*opening_conditions, OperationOrder.opened_at.between(start, end))
        .group_by(opened_day)
    ).all()
    opened_associated = db.execute(
        select(opened_day, func.count(OperationOrder.id))
        .where(*full_conditions, OperationOrder.opened_at.between(start, end))
        .group_by(opened_day)
    ).all()
    completed = db.execute(
        select(
            closed_day,
            func.count(OperationOrder.id),
            func.sum(case((OperationOrder.sla_status == "on_time", 1), else_=0)),
            func.sum(case((OperationOrder.sla_status == "out_of_time", 1), else_=0)),
        )
        .where(*full_conditions, OperationOrder.closed_at.between(start, end))
        .group_by(closed_day)
    ).all()

    result: dict[date, dict[str, int]] = defaultdict(
        lambda: {
            "opened_operation": 0,
            "opened_associated": 0,
            "completed": 0,
            "completed_on_time": 0,
            "completed_out_of_time": 0,
        }
    )
    for day, quantity in opened_operation:
        result[_date_value(day)]["opened_operation"] = int(quantity or 0)
    for day, quantity in opened_associated:
        result[_date_value(day)]["opened_associated"] = int(quantity or 0)
    for day, quantity, on_time, out_of_time in completed:
        item = result[_date_value(day)]
        item["completed"] = int(quantity or 0)
        item["completed_on_time"] = int(on_time or 0)
        item["completed_out_of_time"] = int(out_of_time or 0)
    return dict(result)


def subject_backlog_history(
    db: Session,
    history_from: date,
    history_to: date,
    user: User,
    **filters,
) -> dict:
    """Retorna eventos agregados para reconstruir o backlog diário por assunto."""
    start, end = local_period_utc_bounds(history_from, history_to)
    conditions = _dimension_conditions(user, filters, exclude_filter="responsibles")
    label = _normalized_dimension(OperationOrder.os_subject)
    opened_day = _local_date(db, OperationOrder.opened_at)
    closed_day = _local_date(db, OperationOrder.closed_at)

    initial_rows = db.execute(
        select(label, func.count(OperationOrder.id))
        .where(
            *conditions,
            OperationOrder.opened_at < start,
            or_(OperationOrder.closed_at.is_(None), OperationOrder.closed_at >= start),
        )
        .group_by(label)
    ).all()
    opened_rows = db.execute(
        select(opened_day, label, func.count(OperationOrder.id))
        .where(*conditions, OperationOrder.opened_at.between(start, end))
        .group_by(opened_day, label)
    ).all()
    closed_rows = db.execute(
        select(closed_day, label, func.count(OperationOrder.id))
        .where(*conditions, OperationOrder.closed_at.between(start, end))
        .group_by(closed_day, label)
    ).all()
    return {
        "initial": {str(subject): int(quantity or 0) for subject, quantity in initial_rows},
        "opened": [(_date_value(day), str(subject), int(quantity or 0)) for day, subject, quantity in opened_rows],
        "closed": [(_date_value(day), str(subject), int(quantity or 0)) for day, subject, quantity in closed_rows],
    }


def _control_tower_path_conditions(path: dict[str, str | None]) -> list:
    conditions = []
    for field, column in CONTROL_TOWER_PATH_FIELDS.items():
        value = path.get(field)
        if not value:
            continue
        if value == UNIDENTIFIED_LABEL:
            conditions.append(or_(column.is_(None), column == ""))
        else:
            conditions.append(column == value)
    return conditions


def _age_hours_at(db: Session, reference_at: datetime):
    if db.get_bind().dialect.name == "postgresql":
        return func.extract("epoch", reference_at - OperationOrder.opened_at) / 3600.0
    return (func.julianday(reference_at) - func.julianday(OperationOrder.opened_at)) * 24.0


def control_tower_aggregates(
    db: Session,
    history_from: date,
    reference_date: date,
    level: str,
    user: User,
    *,
    path: dict[str, str | None],
    **filters,
) -> dict:
    """Agrega fluxos e estoque por nó sem materializar O.S. em memória."""
    field = CONTROL_TOWER_COLUMNS[level]
    label = func.coalesce(func.nullif(field, ""), UNIDENTIFIED_LABEL)
    start, end = local_period_utc_bounds(history_from, reference_date)
    conditions = [
        *_dimension_conditions(user, filters, exclude_filter="responsibles"),
        *_control_tower_path_conditions(path),
    ]
    opened_day = _local_date(db, OperationOrder.opened_at)
    closed_day = _local_date(db, OperationOrder.closed_at)

    opened = db.execute(
        select(opened_day, label, func.count(OperationOrder.id))
        .where(*conditions, OperationOrder.opened_at.between(start, end))
        .group_by(opened_day, label)
    ).all()
    completed = db.execute(
        select(closed_day, label, func.count(OperationOrder.id))
        .where(*conditions, OperationOrder.closed_at.between(start, end))
        .group_by(closed_day, label)
    ).all()

    open_at_reference = and_(
        OperationOrder.opened_at <= end,
        or_(OperationOrder.closed_at.is_(None), OperationOrder.closed_at > end),
    )
    age_hours = _age_hours_at(db, end)
    backlog = db.execute(
        select(
            label,
            func.count(OperationOrder.id),
            func.sum(
                case(
                    (
                        or_(
                            OperationOrder.sla_status == "out_of_time",
                            and_(OperationOrder.deadline_at.is_not(None), OperationOrder.deadline_at < end),
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
            func.avg(age_hours),
        )
        .where(*conditions, open_at_reference)
        .group_by(label)
    ).all()

    return {
        "opened": [(_date_value(day), str(group), int(quantity or 0)) for day, group, quantity in opened],
        "completed": [(_date_value(day), str(group), int(quantity or 0)) for day, group, quantity in completed],
        "backlog": {
            str(group): {
                "quantity": int(quantity or 0),
                "overdue": int(overdue or 0),
                "average_age_hours": round(float(average_age or 0), 2) if average_age is not None else None,
            }
            for group, quantity, overdue, average_age in backlog
        },
    }


def data_freshness(db: Session) -> dict:
    run = db.scalar(
        select(OperationImportRun)
        .where(
            OperationImportRun.status.in_(("completed", "completed_with_warnings")),
            OperationImportRun.finished_at.is_not(None),
        )
        .order_by(OperationImportRun.finished_at.desc(), OperationImportRun.id.desc())
        .limit(1)
    )
    if run is None:
        return {
            "last_successful_import_at": None,
            "status": None,
            "date_from": None,
            "date_to": None,
        }
    return {
        "last_successful_import_at": run.finished_at,
        "status": run.status,
        "date_from": run.date_from,
        "date_to": run.date_to,
    }


def _execution_hours(db: Session):
    valid = and_(
        OperationOrder.execution_started_at.is_not(None),
        OperationOrder.finished_at.is_not(None),
        OperationOrder.finished_at >= OperationOrder.execution_started_at,
    )
    if db.get_bind().dialect.name == "postgresql":
        duration = func.extract("epoch", OperationOrder.finished_at - OperationOrder.execution_started_at) / 3600.0
    else:
        duration = (func.julianday(OperationOrder.finished_at) - func.julianday(OperationOrder.execution_started_at)) * 24.0
    return case((valid, duration), else_=None)


def collaborator_sla(db: Session, date_from: date, date_to: date, user: User, **filters) -> dict:
    conditions, start, end = _query_conditions(date_from, date_to, user, filters)
    responsible = func.coalesce(OperationOrder.responsible, "Não identificado")
    regional = func.coalesce(OperationOrder.regional, "Não identificada")
    closed_day = _local_closed_date(db)
    execution_hours = _execution_hours(db)
    rows = db.execute(
        select(
            responsible,
            regional,
            func.count(OperationOrder.id),
            func.sum(case((OperationOrder.sla_status == "on_time", 1), else_=0)),
            func.sum(case((OperationOrder.sla_status == "out_of_time", 1), else_=0)),
            func.count(func.distinct(closed_day)),
            func.count(execution_hours),
            func.avg(execution_hours),
            func.min(execution_hours),
            func.max(execution_hours),
        )
        .where(*conditions, OperationOrder.closed_at.between(start, end))
        .group_by(responsible, regional)
    ).all()
    type_label = func.coalesce(OperationOrder.os_type, "Não identificado")
    type_rows = db.execute(
        select(responsible, regional, type_label, func.count(OperationOrder.id))
        .where(*conditions, OperationOrder.closed_at.between(start, end))
        .group_by(responsible, regional, type_label)
    ).all()
    type_totals: dict[str, int] = defaultdict(int)
    counts_by_person: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
    for person, branch, label, quantity in type_rows:
        label_text = str(label)
        quantity_value = int(quantity or 0)
        type_totals[label_text] += quantity_value
        counts_by_person[(str(person), str(branch))][label_text] = quantity_value
    type_columns = [label for label, _ in sorted(type_totals.items(), key=lambda item: (-item[1], item[0]))[:6]]
    other_column = "Demais tipos"
    while other_column in type_columns:
        other_column = f"{other_column} (agrupados)"
    items = []
    for row in rows:
        completed = int(row[2] or 0)
        on_time = int(row[3] or 0)
        out_of_time = int(row[4] or 0)
        active_days = int(row[5] or 0)
        measurable = on_time + out_of_time
        person_key = (str(row[0]), str(row[1]))
        person_counts = counts_by_person[person_key]
        visible_counts = {label: person_counts.get(label, 0) for label in type_columns}
        other_count = sum(value for label, value in person_counts.items() if label not in type_columns)
        if other_count:
            visible_counts[other_column] = other_count
        items.append(
            {
                "responsible": person_key[0],
                "regional": person_key[1],
                "completed": completed,
                "on_time": on_time,
                "out_of_time": out_of_time,
                "sla_rate": round((on_time / measurable) * 100, 1) if measurable else None,
                "active_days": active_days,
                "daily_average": round(completed / active_days, 1) if active_days else 0,
                "measurable_execution_orders": int(row[6] or 0),
                "average_execution_minutes": round(float(row[7]) * 60, 1) if row[7] is not None else None,
                "minimum_execution_minutes": round(float(row[8]) * 60, 1) if row[8] is not None else None,
                "maximum_execution_minutes": round(float(row[9]) * 60, 1) if row[9] is not None else None,
                "type_counts": visible_counts,
            }
        )
    return {
        "type_columns": [*type_columns, *([other_column] if any(other_column in item["type_counts"] for item in items) else [])],
        "items": sorted(items, key=lambda item: (-item["completed"], item["responsible"])),
    }


def monthly_calendar(
    db: Session,
    competence: date,
    user: User,
    *,
    group_by: str = "regional",
    **filters,
) -> dict:
    allowed_from, allowed_to = operations_period_bounds()
    month_start = date(competence.year, competence.month, 1)
    month_end = date(competence.year, competence.month, calendar.monthrange(competence.year, competence.month)[1])
    query_start = max(month_start, allowed_from)
    query_end = min(month_end, allowed_to)
    conditions, start, end = _query_conditions(query_start, query_end, user, filters)
    responsible = func.coalesce(OperationOrder.responsible, "Não identificado")
    regional = func.coalesce(OperationOrder.regional, "Não identificada")
    closed_day = _local_closed_date(db)
    rows = db.execute(
        select(regional, responsible, closed_day, func.count(OperationOrder.id))
        .where(*conditions, OperationOrder.closed_at.between(start, end))
        .group_by(regional, responsible, closed_day)
    ).all()
    grouped: dict[str, dict] = {}
    for branch, person, closed_date, quantity in rows:
        branch_text = str(branch)
        person_text = str(person)
        day_key = closed_date.isoformat() if isinstance(closed_date, date) else str(closed_date)
        branch_item = grouped.setdefault(branch_text, {"regional": branch_text, "total": 0, "daily_counts": defaultdict(int), "people": {}})
        person_item = branch_item["people"].setdefault(person_text, {"responsible": person_text, "total": 0, "daily_counts": {}})
        value = int(quantity or 0)
        person_item["daily_counts"][day_key] = value
        person_item["total"] += value
        branch_item["daily_counts"][day_key] += value
        branch_item["total"] += value
    assignments = db.execute(
        select(OperationResponsibleAssignment, OperationTeamModel)
        .outerjoin(OperationTeamModel, OperationTeamModel.id == OperationResponsibleAssignment.team_model_id)
        .order_by(OperationResponsibleAssignment.updated_at.desc(), OperationResponsibleAssignment.id.asc())
    ).all()
    team_by_identity: dict[str, OperationTeamModel] = {}
    for assignment, model in assignments:
        if model is not None and model.active:
            team_by_identity.setdefault(" ".join(assignment.responsible_name.casefold().split()), model)
    regionals = []
    for branch_item in grouped.values():
        collaborators = sorted(branch_item["people"].values(), key=lambda item: (-item["total"], item["responsible"]))
        for collaborator in collaborators:
            model = team_by_identity.get(" ".join(collaborator["responsible"].casefold().split()))
            collaborator["team_model"] = (
                {
                    "id": model.id,
                    "name": model.name,
                    "daily_target": model.daily_target,
                    "median_from_quantity": model.median_from_quantity,
                    "good_from_quantity": model.good_from_quantity,
                    "below_target_color": model.below_target_color,
                    "median_color": model.median_color,
                    "good_color": model.good_color,
                    "excellent_color": model.excellent_color,
                    "target_rules": [
                        {
                            "id": rule.id,
                            "period_type": rule.period_type,
                            "enabled": rule.enabled,
                            "median_from_quantity": rule.median_from_quantity,
                            "good_from_quantity": rule.good_from_quantity,
                            "target_quantity": rule.target_quantity,
                            "start_time": rule.start_time,
                            "end_time": rule.end_time,
                        }
                        for rule in model.target_rules
                    ],
                }
                if model is not None
                else None
            )
            collaborator["reference_regional"] = branch_item["regional"]
            collaborator["attended_regionals"] = [branch_item["regional"]]
        regionals.append(
            {
                "regional": branch_item["regional"],
                "total": branch_item["total"],
                "daily_counts": dict(branch_item["daily_counts"]),
                "collaborators": collaborators,
            }
        )
    if group_by == "collaborator":
        consolidated_people: dict[str, dict] = {}
        consolidated_daily_counts: defaultdict[str, int] = defaultdict(int)
        for regional_item in regionals:
            for collaborator in regional_item["collaborators"]:
                person = consolidated_people.setdefault(
                    collaborator["responsible"],
                    {
                        "responsible": collaborator["responsible"],
                        "total": 0,
                        "daily_counts": defaultdict(int),
                        "team_model": None,
                        "reference_regional": None,
                        "attended_regionals": set(),
                    },
                )
                person["total"] += collaborator["total"]
                for day_key, quantity in collaborator["daily_counts"].items():
                    person["daily_counts"][day_key] += quantity
                    consolidated_daily_counts[day_key] += quantity
                person["attended_regionals"].update(collaborator["attended_regionals"])
                if person["team_model"] is None and collaborator["team_model"] is not None:
                    person["team_model"] = collaborator["team_model"]
                    person["reference_regional"] = collaborator["reference_regional"]
        collaborators = []
        for person in consolidated_people.values():
            person["daily_counts"] = dict(person["daily_counts"])
            person["attended_regionals"] = sorted(person["attended_regionals"])
            collaborators.append(person)
        collaborators.sort(key=lambda item: (-item["total"], item["responsible"]))
        regionals = [{
            "regional": "Todos os colaboradores",
            "total": sum(item["total"] for item in collaborators),
            "daily_counts": dict(consolidated_daily_counts),
            "collaborators": collaborators,
        }]
    days = []
    week_number = 1
    for day_number in range(1, month_end.day + 1):
        current = date(competence.year, competence.month, day_number)
        if day_number > 1 and current.weekday() == 0:
            week_number += 1
        days.append(
            {
                "date": current,
                "day": day_number,
                "weekday": current.weekday(),
                "week": week_number,
                "available": query_start <= current <= query_end,
            }
        )
    return {
        "competence": f"{competence.year:04d}-{competence.month:02d}",
        "date_from": query_start,
        "date_to": query_end,
        "group_by": group_by,
        "days": days,
        "regionals": sorted(
            regionals,
            key=lambda item: ("IDENTIFIC" in item["regional"].upper(), item["regional"]),
        ),
    }


def _calendar_order_conditions(
    db: Session,
    day: date,
    regional: str,
    responsible: str,
    user: User,
    *,
    group_by: str = "regional",
    **filters,
) -> list:
    conditions, start, end = _query_conditions(day, day, user, filters)
    conditions.extend([
        OperationOrder.closed_at.between(start, end),
    ])
    if responsible != "__ALL__":
        conditions.append(func.coalesce(OperationOrder.responsible, "Não identificado") == responsible)
    if group_by == "regional":
        conditions.append(func.coalesce(OperationOrder.regional, "Não identificada") == regional)
    return conditions


def _calendar_period_order_conditions(
    db: Session,
    date_from: date,
    date_to: date,
    regional: str,
    responsible: str,
    user: User,
    *,
    group_by: str = "regional",
    **filters,
) -> list:
    conditions, start, end = _query_conditions(date_from, date_to, user, filters)
    conditions.extend([
        OperationOrder.closed_at.between(start, end),
    ])
    if responsible != "__ALL__":
        conditions.append(func.coalesce(OperationOrder.responsible, "Não identificado") == responsible)
    if group_by == "regional":
        conditions.append(func.coalesce(OperationOrder.regional, "Não identificada") == regional)
    return conditions


def calendar_period_order_page(
    db: Session,
    date_from: date,
    date_to: date,
    regional: str,
    responsible: str,
    user: User,
    *,
    group_by: str = "regional",
    page: int,
    page_size: int,
    **filters,
) -> dict:
    conditions = _calendar_period_order_conditions(
        db,
        date_from,
        date_to,
        regional,
        responsible,
        user,
        group_by=group_by,
        **filters,
    )
    total = int(db.scalar(select(func.count(OperationOrder.id)).where(*conditions)) or 0)
    items = list(
        db.scalars(
            select(OperationOrder)
            .where(*conditions)
            .order_by(OperationOrder.closed_at.desc(), OperationOrder.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total else 0,
    }


def calendar_period_metric_orders(
    db: Session,
    date_from: date,
    date_to: date,
    regional: str,
    responsible: str,
    user: User,
    *,
    group_by: str = "regional",
    **filters,
) -> list[OperationOrder]:
    conditions = _calendar_period_order_conditions(
        db,
        date_from,
        date_to,
        regional,
        responsible,
        user,
        group_by=group_by,
        **filters,
    )
    return list(
        db.scalars(
            select(OperationOrder)
            .where(*conditions)
            .order_by(OperationOrder.closed_at.asc(), OperationOrder.id.asc())
        )
    )


def calendar_order_page(
    db: Session,
    day: date,
    regional: str,
    responsible: str,
    user: User,
    *,
    group_by: str = "regional",
    page: int,
    page_size: int,
    **filters,
) -> dict:
    conditions = _calendar_order_conditions(db, day, regional, responsible, user, group_by=group_by, **filters)
    total = int(db.scalar(select(func.count(OperationOrder.id)).where(*conditions)) or 0)
    items = list(
        db.scalars(
            select(OperationOrder)
            .where(*conditions)
            .order_by(OperationOrder.closed_at.desc(), OperationOrder.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total else 0,
    }


def calendar_day_metric_orders(
    db: Session,
    day: date,
    regional: str,
    responsible: str,
    user: User,
    *,
    group_by: str = "regional",
    **filters,
) -> list[OperationOrder]:
    conditions = _calendar_order_conditions(db, day, regional, responsible, user, group_by=group_by, **filters)
    return list(
        db.scalars(
            select(OperationOrder)
            .where(*conditions)
            .order_by(OperationOrder.closed_at.asc(), OperationOrder.id.asc())
        )
    )


def _calendar_month_order_conditions(
    db: Session,
    competence: date,
    regional: str,
    responsible: str,
    user: User,
    *,
    group_by: str = "regional",
    **filters,
) -> list:
    allowed_from, allowed_to = operations_period_bounds()
    month_start = date(competence.year, competence.month, 1)
    month_end = date(competence.year, competence.month, calendar.monthrange(competence.year, competence.month)[1])
    query_start = max(month_start, allowed_from)
    query_end = min(month_end, allowed_to)
    conditions, start, end = _query_conditions(query_start, query_end, user, filters)
    conditions.extend([
        OperationOrder.closed_at.between(start, end),
        func.coalesce(OperationOrder.responsible, "Não identificado") == responsible,
    ])
    if group_by == "regional":
        conditions.append(func.coalesce(OperationOrder.regional, "Não identificada") == regional)
    return conditions


def calendar_month_order_page(
    db: Session,
    competence: date,
    regional: str,
    responsible: str,
    user: User,
    *,
    group_by: str = "regional",
    page: int,
    page_size: int,
    **filters,
) -> dict:
    conditions = _calendar_month_order_conditions(db, competence, regional, responsible, user, group_by=group_by, **filters)
    total = int(db.scalar(select(func.count(OperationOrder.id)).where(*conditions)) or 0)
    items = list(
        db.scalars(
            select(OperationOrder)
            .where(*conditions)
            .order_by(OperationOrder.closed_at.desc(), OperationOrder.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total else 0,
    }


def calendar_month_metric_orders(
    db: Session,
    competence: date,
    regional: str,
    responsible: str,
    user: User,
    *,
    group_by: str = "regional",
    **filters,
) -> list[OperationOrder]:
    conditions = _calendar_month_order_conditions(db, competence, regional, responsible, user, group_by=group_by, **filters)
    return list(
        db.scalars(
            select(OperationOrder)
            .where(*conditions)
            .order_by(OperationOrder.closed_at.asc(), OperationOrder.id.asc())
        )
    )


def team_configuration(db: Session, user: User) -> dict:
    visible_conditions = _dimension_conditions(user, {})
    pairs = list(db.execute(
        select(OperationOrder.responsible, OperationOrder.regional)
        .where(
            *visible_conditions,
            OperationOrder.responsible.is_not(None),
            OperationOrder.responsible != "",
            OperationOrder.regional.is_not(None),
            OperationOrder.regional != "",
        )
        .distinct()
        .order_by(OperationOrder.regional.asc(), OperationOrder.responsible.asc())
    ).all())
    known_people = {" ".join(str(responsible).casefold().split()) for responsible, _ in pairs}
    for name in db.scalars(select(OperationIxcCollaborator.name).where(OperationIxcCollaborator.active.is_(True))):
        identity = " ".join(str(name).casefold().split())
        if identity not in known_people:
            pairs.append((name, "Cadastro IXC"))
            known_people.add(identity)
    assignments: dict[str, OperationResponsibleAssignment] = {}
    for item in db.scalars(select(OperationResponsibleAssignment).order_by(OperationResponsibleAssignment.updated_at.desc())):
        assignments.setdefault(" ".join(item.responsible_name.casefold().split()), item)
    members_by_person: dict[str, dict] = {}
    for responsible, regional in pairs:
        responsible_text, regional_text = str(responsible), str(regional)
        identity = " ".join(responsible_text.casefold().split())
        assignment = assignments.get(identity)
        member = members_by_person.setdefault(
            identity,
            {
                "responsible_name": responsible_text,
                "regional": regional_text,
                "regionals": [],
                "team_model_id": assignment.team_model_id if assignment else None,
            },
        )
        member["regionals"].append(regional_text)
    members = sorted(
        ({**item, "regionals": sorted(set(item["regionals"]))} for item in members_by_person.values()),
        key=lambda item: item["responsible_name"].casefold(),
    )
    directory = db.get(OperationResponsibleDirectorySetting, 1)
    synced_at = db.scalar(select(func.max(OperationIxcCollaborator.last_synced_at)))
    return {
        "models": list(db.scalars(select(OperationTeamModel).order_by(OperationTeamModel.active.desc(), OperationTeamModel.name.asc()))),
        "members": members,
        "responsible_source": directory.source if directory else "orders",
        "ixc_collaborators_synced_at": synced_at,
    }


def subject_type_mappings(db: Session, user: User) -> list[dict]:
    visible_conditions = _dimension_conditions(user, {})
    rows = db.execute(
        select(
            OperationOrder.os_subject,
            func.count(OperationOrder.id),
            OperationSubjectTypeMapping.id,
            OperationSubjectTypeMapping.os_type,
            OperationSubjectTypeMapping.active,
        )
        .outerjoin(OperationSubjectTypeMapping, OperationSubjectTypeMapping.subject == OperationOrder.os_subject)
        .where(*visible_conditions, OperationOrder.os_subject.is_not(None), OperationOrder.os_subject != "")
        .group_by(
            OperationOrder.os_subject,
            OperationSubjectTypeMapping.id,
            OperationSubjectTypeMapping.os_type,
            OperationSubjectTypeMapping.active,
        )
        .order_by(OperationSubjectTypeMapping.os_type.asc().nullsfirst(), OperationOrder.os_subject.asc())
    ).all()
    return [
        {
            "id": mapping_id,
            "subject": str(subject),
            "os_type": str(os_type or "Pendente de classificação"),
            "order_count": int(quantity or 0),
            "active": bool(active) if mapping_id is not None else False,
        }
        for subject, quantity, mapping_id, os_type, active in rows
    ]


def in_progress_breakdown(db: Session, user: User, group_by: str, **filters) -> list[dict]:
    allowed_groups = {
        "regional": OperationOrder.regional,
        "os_type": OperationOrder.os_type,
        "subject": OperationOrder.os_subject,
        "status": OperationOrder.status,
    }
    field = allowed_groups.get(group_by, OperationOrder.regional)
    conditions = _dimension_conditions(user, filters)
    label = func.coalesce(field, "Não identificado")
    rows = db.execute(
        select(label, func.count(OperationOrder.id))
        .where(*conditions, OperationOrder.is_closed.is_(False))
        .group_by(label)
    ).all()
    total = sum(int(row[1]) for row in rows)
    return [
        {"label": str(row[0]), "quantity": int(row[1]), "percentage": round((int(row[1]) / total) * 100, 2) if total else 0}
        for row in sorted(rows, key=lambda item: (-int(item[1]), str(item[0])))
    ]


def in_progress_order_page(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    **filters,
) -> dict:
    conditions = [*_dimension_conditions(user, filters), OperationOrder.is_closed.is_(False)]
    total = int(db.scalar(select(func.count(OperationOrder.id)).where(*conditions)) or 0)
    orders = list(
        db.scalars(
            select(OperationOrder)
            .where(*conditions)
            .order_by(OperationOrder.opened_at.asc(), OperationOrder.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return {
        "items": orders,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total else 0,
    }


def order_page(
    db: Session,
    date_from: date,
    date_to: date,
    user: User,
    *,
    page: int,
    page_size: int,
    **filters,
) -> dict:
    conditions, _, _ = _query_conditions(date_from, date_to, user, filters)
    total = int(db.scalar(select(func.count(OperationOrder.id)).where(*conditions)) or 0)
    start = (page - 1) * page_size
    orders = list(
        db.scalars(
            select(OperationOrder)
            .where(*conditions)
            .order_by(OperationOrder.opened_at.desc(), OperationOrder.id.desc())
            .offset(start)
            .limit(page_size)
        )
    )
    return {
        "items": orders,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total else 0,
    }


def opening_order_page(
    db: Session,
    date_from: date,
    date_to: date,
    user: User,
    *,
    page: int,
    page_size: int,
    **filters,
) -> dict:
    start, end = local_period_utc_bounds(date_from, date_to)
    conditions = [
        *_dimension_conditions(user, _opening_filters(filters)),
        OperationOrder.opened_at.between(start, end),
    ]
    total = int(db.scalar(select(func.count(OperationOrder.id)).where(*conditions)) or 0)
    orders = list(
        db.scalars(
            select(OperationOrder)
            .where(*conditions)
            .order_by(OperationOrder.opened_at.desc(), OperationOrder.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return {
        "items": orders,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total else 0,
    }
