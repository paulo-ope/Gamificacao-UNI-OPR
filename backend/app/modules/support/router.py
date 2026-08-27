from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import Float, case, cast, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import get_current_user, permissions_for_user, require_permission
from app.db.session import get_db
from app.models import User
from app.services.audit_log import record_audit_log
from app.services.calculation import get_setting, upsert_setting
from app.services.notifications import create_notification
from app.services.opa_client import OpaApiError, get_opa_client
from app.services.opa_scheduler import (
    SUPPORT_OPA_BACKFILL_ENABLED_KEY,
    SUPPORT_OPA_BACKFILL_LOOKBACK_MONTHS_KEY,
    SUPPORT_OPA_BACKFILL_RUN_HOUR_KEY,
    SUPPORT_OPA_SYNC_CONSECUTIVE_FAILURES_KEY,
    SUPPORT_OPA_SYNC_ENABLED_KEY,
    SUPPORT_OPA_SYNC_INTERVAL_MINUTES_KEY,
    SUPPORT_OPA_SYNC_LAST_ATTEMPT_AT_KEY,
    SUPPORT_OPA_SYNC_LAST_ERROR_AT_KEY,
    SUPPORT_OPA_SYNC_LAST_ERROR_KEY,
    SUPPORT_OPA_SYNC_LAST_SUCCESS_AT_KEY,
    SUPPORT_OPA_SYNC_LOOKBACK_DAYS_KEY,
    SUPPORT_OPA_SYNC_NEXT_ALLOWED_AT_KEY,
    recompute_support_opa_next_allowed_at,
)

from . import opa_attendant_overrides, opa_attendant_service, opa_overview_service, opa_timeline_service
from .models import SupportOpaAttendance, SupportOpaDimension, SupportOpaImportRun, SupportOpaSavedFilter
from .opa_filters import (
    SUPPORT_TIMEZONE,
    OpaAttendanceFilters,
    apply_opa_attendance_filters,
    opa_period_bounds,
    validate_opa_period,
)
from .opa_ingestion import (
    OpaImportInterrupted,
    _create_pending_import_run,
    _opa_import_busy_message,
    _run_result,
    active_opa_import_run,
    import_months_status,
    opa_import_lock_busy,
    resume_opa_import_run,
    run_opa_import_background_job,
)
from .schemas import (
    SupportImportResult,
    SupportOpaImportMonthOut,
    SupportOpaAttendanceDetail,
    SupportOpaAttendancePage,
    SupportOpaAttendanceTimeline,
    SupportOpaAttendantOverride as SupportOpaAttendantOverrideSchema,
    SupportOpaAttendantOverrideCreate,
    SupportOpaAttendantOverrideUpdate,
    SupportOpaAttendantSummary,
    SupportOpaBreakdowns,
    SupportOpaFilters,
    SupportOpaMetrics,
    SupportOpaOverview,
    SupportOpaSavedFilter as SupportOpaSavedFilterSchema,
    SupportOpaSavedFilterCreate,
    SupportOpaSyncSettings,
    SupportOpaSyncSettingsUpdate,
    SupportOpaSyncStatus,
    SupportOpaTimeseries,
    SupportPeriodRequest,
)

logger = logging.getLogger("support")
router = APIRouter(
    prefix="/support",
    tags=["support"],
    dependencies=[Depends(require_permission("support:read"))],
)


def _validate_period(date_from: date, date_to: date) -> None:
    validate_opa_period(date_from, date_to)


def _bool_setting(value: str | None, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"true", "1", "sim", "yes"}


def _int_setting(value: str | None, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value or "")
    except (TypeError, ValueError):
        return default
    return min(max(parsed, minimum), maximum)


def _parse_app_setting_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _support_period_bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    return opa_period_bounds(date_from, date_to)


def _raw_get(payload: dict | None, *paths: str):
    if not isinstance(payload, dict):
        return None
    for path in paths:
        current = payload
        found = True
        for part in path.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                found = False
                break
        if found and current not in (None, ""):
            return current
    return None


def _raw_text(value) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return None


def _raw_datetime(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(raw, fmt)
                break
            except ValueError:
                parsed = None
        if parsed is None:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _raw_entity(value) -> tuple[str | None, str | None]:
    if isinstance(value, dict):
        identifier = _raw_text(_raw_get(value, "_id", "id", "value"))
        label = _raw_text(_raw_get(value, "nome", "name", "motivo", "descricao", "description", "label"))
        return identifier, label
    return _raw_text(value), None


def _raw_reasons(payload: dict | None, fallback_id: str | None = None, fallback_name: str | None = None) -> list[dict]:
    reasons = []
    value = _raw_get(payload, "motivos", "reasons")
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                reason_value = _raw_get(item, "idMotivo", "motivo", "reason")
                reason_id, reason_name = _raw_entity(reason_value)
                reasons.append(
                    {
                        "id": reason_id or _raw_text(_raw_get(item, "id", "_id")),
                        "name": reason_name or _raw_text(_raw_get(item, "nome", "motivo", "descricao", "name")),
                    }
                )
            else:
                reasons.append({"id": _raw_text(item), "name": None})
    elif isinstance(value, dict):
        reason_id, reason_name = _raw_entity(value)
        reasons.append({"id": reason_id, "name": reason_name})
    if not reasons and (fallback_id or fallback_name):
        reasons.append({"id": fallback_id, "name": fallback_name})
    return [reason for reason in reasons if reason.get("id") or reason.get("name")]


def _raw_tags(payload: dict | None) -> list[dict]:
    tags = []
    value = _raw_get(payload, "tags", "etiquetas")
    if not isinstance(value, list):
        return tags
    for item in value:
        if isinstance(item, dict):
            tag_value = _raw_get(item, "id_tag", "tag", "idTag", "etiqueta")
            tag_id, tag_name = _raw_entity(tag_value)
            tags.append(
                {
                    "id": tag_id or _raw_text(_raw_get(item, "id", "_id")),
                    "name": tag_name or _raw_text(_raw_get(item, "nome", "name", "descricao")),
                }
            )
        else:
            tags.append({"id": _raw_text(item), "name": None})
    return [tag for tag in tags if tag.get("id") or tag.get("name")]


def _raw_rating(payload: dict | None) -> float | None:
    value = _raw_get(payload, "rating", "avaliacao", "evaluation", "evaluations.0.likert.rating")
    if value is None and isinstance(payload, dict):
        evaluations = payload.get("evaluations")
        if isinstance(evaluations, list):
            for evaluation in evaluations:
                value = _raw_get(evaluation, "likert.rating", "rating", "nota")
                if value is not None:
                    break
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _duration_seconds(opened_at: datetime | None, closed_at: datetime | None) -> int | None:
    if not opened_at or not closed_at:
        return None
    return max(0, int((closed_at - opened_at).total_seconds()))


def _sync_settings_response(db: Session) -> dict:
    return {
        "enabled": _bool_setting(get_setting(db, SUPPORT_OPA_SYNC_ENABLED_KEY, ""), False),
        "interval_minutes": _int_setting(
            get_setting(db, SUPPORT_OPA_SYNC_INTERVAL_MINUTES_KEY, ""),
            20,
            minimum=5,
            maximum=1440,
        ),
        "lookback_days": _int_setting(
            get_setting(db, SUPPORT_OPA_SYNC_LOOKBACK_DAYS_KEY, ""),
            1,
            minimum=1,
            maximum=30,
        ),
        "backfill_enabled": _bool_setting(get_setting(db, SUPPORT_OPA_BACKFILL_ENABLED_KEY, ""), True),
        "backfill_run_hour": _int_setting(
            get_setting(db, SUPPORT_OPA_BACKFILL_RUN_HOUR_KEY, ""),
            3,
            minimum=0,
            maximum=23,
        ),
        "backfill_lookback_months": _int_setting(
            get_setting(db, SUPPORT_OPA_BACKFILL_LOOKBACK_MONTHS_KEY, ""),
            3,
            minimum=1,
            maximum=24,
        ),
    }


def _sync_status_response(db: Session) -> dict:
    settings = get_settings()
    sync_settings = _sync_settings_response(db)
    try:
        failures = int(get_setting(db, SUPPORT_OPA_SYNC_CONSECUTIVE_FAILURES_KEY, "0") or "0")
    except ValueError:
        failures = 0

    active_run = active_opa_import_run(db)
    lock_busy = opa_import_lock_busy(db)
    sync_in_progress = bool(active_run is not None or lock_busy)
    next_allowed_at = _parse_app_setting_datetime(get_setting(db, SUPPORT_OPA_SYNC_NEXT_ALLOWED_AT_KEY, ""))
    next_window_delayed = bool(
        sync_in_progress and next_allowed_at is not None and next_allowed_at <= datetime.now(timezone.utc)
    )

    return {
        "configured": bool(settings.opa_api_base_url and settings.opa_api_token),
        **sync_settings,
        "last_success_at": _parse_app_setting_datetime(get_setting(db, SUPPORT_OPA_SYNC_LAST_SUCCESS_AT_KEY, "")),
        "last_attempt_at": _parse_app_setting_datetime(get_setting(db, SUPPORT_OPA_SYNC_LAST_ATTEMPT_AT_KEY, "")),
        "next_allowed_at": next_allowed_at,
        "last_error": get_setting(db, SUPPORT_OPA_SYNC_LAST_ERROR_KEY, "") or None,
        "last_error_at": _parse_app_setting_datetime(get_setting(db, SUPPORT_OPA_SYNC_LAST_ERROR_AT_KEY, "")),
        "consecutive_failures": failures,
        "sync_in_progress": sync_in_progress,
        "lock_busy": lock_busy,
        "active_run_id": active_run.id if active_run is not None else None,
        "active_run_mode": active_run.mode if active_run is not None else None,
        "active_run_started_at": active_run.started_at if active_run is not None else None,
        "next_window_delayed": next_window_delayed,
    }


def _attendance_list_item(row: SupportOpaAttendance) -> dict:
    return {
        "id": row.id,
        "source_id": row.source_id,
        "protocol": row.protocol,
        "customer_id": row.customer_id,
        "customer_name": row.customer_name,
        "attendant_id": row.attendant_id,
        "attendant_name": row.attendant_name,
        "department_id": row.department_id,
        "department_name": row.department_name,
        "reason_id": row.reason_id,
        "reason_name": row.reason_name,
        "channel": row.channel,
        "channel_id": row.channel_id,
        "channel_customer": row.channel_customer,
        "status": row.status,
        "opened_at": row.opened_at,
        "closed_at": row.closed_at,
        "rating": row.rating,
        "tma_seconds": row.tma_seconds,
        "tmr_seconds": row.tmr_seconds,
        "tmr_all_responses_seconds": row.tmr_all_responses_seconds,
    }


def _attendance_local_detail(row: SupportOpaAttendance) -> dict:
    raw = row.raw_payload or {}
    return {
        "source_id": row.source_id,
        "protocol": row.protocol,
        "customer_id": row.customer_id,
        "customer_name": row.customer_name,
        "attendant_id": row.attendant_id,
        "attendant_name": row.attendant_name,
        "department_id": row.department_id,
        "department_name": row.department_name,
        "channel": row.channel,
        "channel_id": row.channel_id,
        "channel_customer": row.channel_customer,
        "status": row.status,
        "opened_at": row.opened_at,
        "closed_at": row.closed_at,
        "first_response_at": row.first_response_at,
        "duration_seconds": row.tma_seconds or _duration_seconds(row.opened_at, row.closed_at),
        "tma_seconds": row.tma_seconds,
        "tmr_seconds": row.tmr_seconds,
        "tmr_all_responses_seconds": row.tmr_all_responses_seconds,
        "rating": row.rating,
        "reasons": _raw_reasons(raw, row.reason_id, row.reason_name),
        "tags": _raw_tags(raw),
        "description": _raw_text(_raw_get(raw, "descricao", "description")),
        "observations": _raw_text(_raw_get(raw, "observacoes", "observacao", "observations", "notes")),
    }


def _attendance_enriched_detail(payload: dict) -> dict:
    customer_id, customer_name = _raw_entity(_raw_get(payload, "id_cliente", "cliente", "customer"))
    attendant_id, attendant_name = _raw_entity(_raw_get(payload, "id_atendente", "atendente", "attendant"))
    department_id, department_name = _raw_entity(_raw_get(payload, "setor", "departamento", "department"))
    opened_at = _raw_datetime(_raw_get(payload, "date", "data", "opened_at", "abertura"))
    closed_at = _raw_datetime(_raw_get(payload, "fim", "closed_at", "encerramento"))
    return {
        "source_id": _raw_text(_raw_get(payload, "_id", "id")),
        "protocol": _raw_text(_raw_get(payload, "protocolo", "protocol")),
        "customer_id": customer_id,
        "customer_name": customer_name,
        "attendant_id": attendant_id,
        "attendant_name": attendant_name,
        "department_id": department_id,
        "department_name": department_name,
        "channel": _raw_text(_raw_get(payload, "canal", "channel")),
        "channel_id": _raw_text(_raw_get(payload, "canal_id", "channel_id")),
        "channel_customer": _raw_text(_raw_get(payload, "canal_cliente", "channel_customer", "telefone", "phone")),
        "status": _raw_text(_raw_get(payload, "status.nome", "status.descricao", "status")),
        "opened_at": opened_at,
        "closed_at": closed_at,
        "duration_seconds": _duration_seconds(opened_at, closed_at),
        "tma_seconds": _duration_seconds(opened_at, closed_at),
        "rating": _raw_rating(payload),
        "reasons": _raw_reasons(payload),
        "tags": _raw_tags(payload),
        "description": _raw_text(_raw_get(payload, "descricao", "description")),
        "observations": _raw_text(_raw_get(payload, "observacoes", "observacao", "observations", "notes")),
    }


class OpaExtraFilters:
    """Filtros adicionais da tela /suporte, agrupados num `Depends` único.

    São declarados aqui em vez de repetidos em cada rota de propósito: já são
    cinco endpoints lendo o mesmo recorte (atendimentos, visão geral,
    breakdowns, resumo do atendente, série diária), e um parâmetro esquecido em
    um deles produziria justamente o pior tipo de bug de dashboard — a tela
    mostrando números de universos diferentes lado a lado, sem erro nenhum.
    """

    def __init__(
        self,
        # `Annotated` em vez de `= Query(...)` de propósito: assim o default em
        # Python continua sendo `None` de verdade, e `OpaExtraFilters()` pode ser
        # instanciado direto (a suíte chama as rotas como função, sem passar pelo
        # FastAPI) sem receber objetos `Query` no lugar dos valores.
        tag_id: Annotated[str | None, Query(description="IDs de etiqueta separados por vírgula (OU entre elas).")] = None,
        customer_id: Annotated[str | None, Query(description="IDs de cliente separados por vírgula.")] = None,
        rating_min: Annotated[float | None, Query(ge=0, le=5)] = None,
        rating_max: Annotated[float | None, Query(ge=0, le=5)] = None,
        bot_human: Annotated[
            str | None,
            Query(pattern="^(with_bot|without_bot|reached_human|bot_only|handoff|unclassified)$"),
        ] = None,
    ) -> None:
        self.tag_id = tag_id
        self.customer_id = customer_id
        self.rating_min = rating_min
        self.rating_max = rating_max
        self.bot_human = bot_human

    def as_kwargs(self) -> dict[str, object]:
        return {
            "tag_id": self.tag_id,
            "customer_id": self.customer_id,
            "rating_min": self.rating_min,
            "rating_max": self.rating_max,
            "bot_human": self.bot_human,
        }


def _apply_attendance_filters(
    statement,
    *,
    date_from: date | None,
    date_to: date | None,
    date_basis: str = "opened_at",
    status: str | None,
    channel: str | None,
    attendant_id: str | None,
    attendant: str | None,
    department_id: str | None,
    department: str | None,
    reason_id: str | None,
    reason: str | None,
    protocol: str | None,
    customer: str | None,
    search: str | None,
    tag_id: str | None = None,
    customer_id: str | None = None,
    rating_min: float | None = None,
    rating_max: float | None = None,
    bot_human: str | None = None,
):
    return apply_opa_attendance_filters(
        statement,
        OpaAttendanceFilters(
            date_from=date_from,
            date_to=date_to,
            date_basis=date_basis,
            status=status,
            channel=channel,
            attendant_id=attendant_id,
            attendant=attendant,
            department_id=department_id,
            department=department,
            reason_id=reason_id,
            reason=reason,
            protocol=protocol,
            customer=customer,
            search=search,
            tag_id=tag_id,
            customer_id=customer_id,
            rating_min=rating_min,
            rating_max=rating_max,
            bot_human=bot_human,
        ),
    )


def _breakdown_dimension(dimension: str):
    dimensions = {
        "attendant": (SupportOpaAttendance.attendant_id, SupportOpaAttendance.attendant_name),
        "department": (SupportOpaAttendance.department_id, SupportOpaAttendance.department_name),
        "reason": (SupportOpaAttendance.reason_id, SupportOpaAttendance.reason_name),
        "channel": (SupportOpaAttendance.channel, SupportOpaAttendance.channel),
        "status": (SupportOpaAttendance.status, SupportOpaAttendance.status),
        "customer": (SupportOpaAttendance.customer_id, SupportOpaAttendance.customer_name),
    }
    try:
        return dimensions[dimension]
    except KeyError as exc:
        raise HTTPException(status_code=422, detail="Dimensão de breakdown inválida para atendimentos OPA.") from exc


def _opa_breakdown_rows(
    db: Session,
    *,
    dimension: str,
    filters: OpaAttendanceFilters,
    sort_by: str,
    sort_dir: str,
    limit: int,
) -> tuple[int, list[dict]]:
    id_column, label_column = _breakdown_dimension(dimension)
    total_statement = apply_opa_attendance_filters(select(func.count(SupportOpaAttendance.id)), filters)
    universe_total = int(db.scalar(total_statement) or 0)
    if not universe_total:
        return 0, []

    def aggregate_rows(period_filters: OpaAttendanceFilters, *, ordered: bool) -> list:
        group_id = id_column.label("id")
        group_label = func.coalesce(func.max(label_column), id_column, "Não identificado").label("label")
        total = func.count(SupportOpaAttendance.id).label("total")
        closed = func.coalesce(
            func.sum(case((SupportOpaAttendance.closed_at.isnot(None), 1), else_=0)), 0
        ).label("closed")
        open_total = (total - closed).label("open")
        closure_rate = (
            cast(closed, Float) * 100.0 / func.nullif(cast(total, Float), 0.0)
        ).label("closure_rate")
        average_duration = func.avg(
            case((SupportOpaAttendance.closed_at.isnot(None), SupportOpaAttendance.tma_seconds))
        ).label("avg_duration_seconds")
        average_rating = func.avg(SupportOpaAttendance.rating).label("avg_rating")
        rating_count = func.count(SupportOpaAttendance.rating).label("rating_count")

        statement = select(
            group_id,
            group_label,
            total,
            closed,
            open_total,
            closure_rate,
            average_duration,
            average_rating,
            rating_count,
        ).group_by(id_column)
        if ordered:
            sortable_fields = {
                "label": group_label,
                "total": total,
                "closed": closed,
                "open": open_total,
                "closure_rate": closure_rate,
                "avg_duration_seconds": average_duration,
                "avg_rating": average_rating,
                "rating_count": rating_count,
                "share_percentage": total,
            }
            if sort_by not in sortable_fields:
                raise HTTPException(status_code=422, detail="Campo de ordenação inválido para breakdowns OPA.")
            order_column = sortable_fields[sort_by]
            order_expr = order_column.asc() if sort_dir == "asc" else order_column.desc()
            statement = statement.order_by(order_expr, group_label.asc()).limit(limit)
        return db.execute(apply_opa_attendance_filters(statement, period_filters)).all()

    rows = aggregate_rows(filters, ordered=True)
    previous_by_id = {}
    if filters.date_from and filters.date_to:
        previous_by_id = {row.id: row for row in aggregate_rows(filters.previous_period(), ordered=False)}

    def percentage_change(current: float | int | None, previous: float | int | None) -> float | None:
        if previous in (None, 0):
            return 0.0 if current in (None, 0) else None
        return ((float(current or 0) - float(previous)) / float(previous)) * 100

    return universe_total, [
        _opa_breakdown_item(row, previous_by_id.get(row.id), universe_total, percentage_change)
        for row in rows
    ]


def _opa_breakdown_item(row, previous_row, universe_total: int, percentage_change) -> dict:
    total = int(row.total or 0)
    closure_rate = float(row.closure_rate or 0)
    average_duration = float(row.avg_duration_seconds) if row.avg_duration_seconds is not None else None
    average_rating = float(row.avg_rating) if row.avg_rating is not None else None
    previous_total = int(previous_row.total or 0) if previous_row is not None else 0
    previous_closure_rate = float(previous_row.closure_rate or 0) if previous_row is not None else 0.0
    previous_average_duration = (
        float(previous_row.avg_duration_seconds)
        if previous_row is not None and previous_row.avg_duration_seconds is not None
        else None
    )
    previous_average_rating = (
        float(previous_row.avg_rating) if previous_row is not None and previous_row.avg_rating is not None else None
    )
    return {
        "id": row.id,
        "label": row.label,
        "total": total,
        "closed": int(row.closed or 0),
        "open": int(row.open or 0),
        "closure_rate": closure_rate,
        "avg_duration_seconds": average_duration,
        "avg_rating": average_rating,
        "rating_count": int(row.rating_count or 0),
        "share_percentage": (total / universe_total) * 100,
        "previous_total": previous_total,
        "total_change": total - previous_total,
        "total_change_percentage": percentage_change(total, previous_total),
        "previous_closure_rate": previous_closure_rate,
        "closure_rate_change_pp": closure_rate - previous_closure_rate,
        "previous_avg_duration_seconds": previous_average_duration,
        "avg_duration_change_percentage": percentage_change(average_duration, previous_average_duration),
        "previous_avg_rating": previous_average_rating,
        "avg_rating_change": (
            average_rating - previous_average_rating
            if average_rating is not None and previous_average_rating is not None
            else None
        ),
    }


@router.get("/opa-sync-settings", response_model=SupportOpaSyncSettings)
def opa_sync_settings(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("support:sync_opa")),
):
    return _sync_settings_response(db)


@router.put("/opa-sync-settings", response_model=SupportOpaSyncSettings)
def update_opa_sync_settings(
    payload: SupportOpaSyncSettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("support:sync_opa")),
):
    before = _sync_settings_response(db)
    if payload.enabled is not None:
        upsert_setting(
            db,
            SUPPORT_OPA_SYNC_ENABLED_KEY,
            "true" if payload.enabled else "false",
            description="Liga ou desliga a sincronização automática do OPA Suite no módulo Suporte.",
        )
    if payload.interval_minutes is not None:
        upsert_setting(
            db,
            SUPPORT_OPA_SYNC_INTERVAL_MINUTES_KEY,
            str(payload.interval_minutes),
            description="Intervalo em minutos da sincronização automática do OPA Suite no módulo Suporte.",
        )
        recompute_support_opa_next_allowed_at(db, payload.interval_minutes)
    if payload.lookback_days is not None:
        upsert_setting(
            db,
            SUPPORT_OPA_SYNC_LOOKBACK_DAYS_KEY,
            str(payload.lookback_days),
            description="Quantos dias antes de hoje o ciclo automático do OPA Suite reimporta para o módulo Suporte.",
        )
    if payload.backfill_enabled is not None:
        upsert_setting(
            db,
            SUPPORT_OPA_BACKFILL_ENABLED_KEY,
            "true" if payload.backfill_enabled else "false",
            description="Liga ou desliga o backfill automático de meses completos do OPA Suite (roda de madrugada).",
        )
    if payload.backfill_run_hour is not None:
        upsert_setting(
            db,
            SUPPORT_OPA_BACKFILL_RUN_HOUR_KEY,
            str(payload.backfill_run_hour),
            description="Hora do dia (0-23, fuso America/Porto_Velho) em que o backfill automático de meses roda.",
        )
    if payload.backfill_lookback_months is not None:
        upsert_setting(
            db,
            SUPPORT_OPA_BACKFILL_LOOKBACK_MONTHS_KEY,
            str(payload.backfill_lookback_months),
            description="Quantos meses (incluindo o atual) o backfill automático de madrugada verifica/completa.",
        )
    after = _sync_settings_response(db)
    record_audit_log(db, user, "update", "support_opa_sync_settings", "opa", before, after)
    db.commit()
    return after


@router.get("/opa/attendant-overrides", response_model=list[SupportOpaAttendantOverrideSchema])
def list_opa_attendant_overrides(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("support:sync_opa")),
):
    return opa_attendant_overrides.list_overrides(db)


@router.post("/opa/attendant-overrides", response_model=SupportOpaAttendantOverrideSchema, status_code=201)
def create_opa_attendant_override(
    payload: SupportOpaAttendantOverrideCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("support:sync_opa")),
):
    try:
        override = opa_attendant_overrides.create_override(
            db,
            attendant_id=payload.attendant_id,
            attendant_name=payload.attendant_name,
            classification=payload.classification,
            active=payload.active,
            created_by=user.id,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail="Já existe um cadastro para este attendant_id.") from exc
    record_audit_log(db, user, "create", "support_opa_attendant_override", str(override.id), None, {
        "attendant_id": override.attendant_id,
        "classification": override.classification,
        "active": override.active,
    })
    db.commit()
    return override


@router.patch("/opa/attendant-overrides/{override_id}", response_model=SupportOpaAttendantOverrideSchema)
def update_opa_attendant_override(
    override_id: int,
    payload: SupportOpaAttendantOverrideUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("support:sync_opa")),
):
    try:
        override = opa_attendant_overrides.update_override(db, override_id, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    record_audit_log(db, user, "update", "support_opa_attendant_override", str(override_id), None, {
        "attendant_id": override.attendant_id,
        "classification": override.classification,
        "active": override.active,
    })
    db.commit()
    return override


@router.delete("/opa/attendant-overrides/{override_id}")
def delete_opa_attendant_override(
    override_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("support:sync_opa")),
):
    deleted = opa_attendant_overrides.delete_override(db, override_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Cadastro de atendente não encontrado.")
    record_audit_log(db, user, "delete", "support_opa_attendant_override", str(override_id), None, None)
    db.commit()
    return {"deleted": True}


@router.get("/opa-sync-status", response_model=SupportOpaSyncStatus)
def opa_sync_status(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("support:sync_opa")),
):
    return _sync_status_response(db)


@router.post("/opa-imports", response_model=SupportImportResult)
def import_opa_period(
    payload: SupportPeriodRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("support:sync_opa")),
):
    """Dispara a importação em BACKGROUND (não bloqueia a requisição) - devolve o
    run_id na hora com status "pending", e o frontend acompanha o progresso via
    GET /opa/sync-runs/{run_id} (polling, mesmo padrão do sync do IXC em
    scheduling/router.py). Achado real: import de mês inteiro busca mensagem por
    mensagem pra calcular TMR e pode levar minutos - antes disso rodava inline na
    requisição HTTP e arriscava timeout."""
    _validate_period(payload.date_from, payload.date_to)
    if opa_import_lock_busy(db):
        raise HTTPException(status_code=409, detail=_opa_import_busy_message(db))
    run_id = _create_pending_import_run(
        mode="manual", date_from=payload.date_from, date_to=payload.date_to, imported_by=user.id
    )
    background_tasks.add_task(run_opa_import_background_job, run_id)
    run = db.get(SupportOpaImportRun, run_id)
    return _run_result(run)


@router.get("/opa/sync-runs/{run_id}", response_model=SupportImportResult)
def get_opa_sync_run(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("support:sync_opa")),
):
    """Status/progresso de uma run (pending/running/completed/failed/interrupted) -
    usado pelo frontend pra fazer polling depois de POST /opa-imports."""
    run = db.get(SupportOpaImportRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run de importação OPA não encontrada.")
    return _run_result(run)


@router.get("/opa/import-months", response_model=list[SupportOpaImportMonthOut])
def get_opa_import_months(
    months: int = Query(default=6, ge=1, le=24),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("support:sync_opa")),
):
    """Status (missing/complete) dos últimos `months` meses calendário, do mais
    antigo pro mais recente - alimenta o painel de meses da tela e o backfill
    automático de madrugada usa a mesma fonte (`import_months_status`)."""
    today = datetime.now(SUPPORT_TIMEZONE).date()
    year_months: list[str] = []
    year, month = today.year, today.month
    for _ in range(months):
        year_months.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    year_months.reverse()
    status_by_month = import_months_status(db, year_months)
    return [status_by_month[year_month] for year_month in year_months]


@router.post("/opa/sync-runs/{run_id}/resume", response_model=SupportImportResult)
def resume_opa_sync_run(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("support:sync_opa")),
):
    try:
        result = resume_opa_import_run(
            db,
            get_opa_client(),
            run_id=run_id,
            imported_by=user.id,
        )
        create_notification(
            db,
            user_id=user.id,
            title="Retomada OPA concluída",
            message=(
                f"Run #{result['run_id']}: {result['fetched_count']} recebido(s) em "
                f"{result.get('pages_processed', 0)} página(s), "
                f"{result['created_count']} novo(s), {result['updated_count']} atualizado(s), "
                f"{result['unchanged_count']} sem alteração, {result['rejected_count']} rejeitado(s)."
            ),
            link_url="/suporte",
            entity_type="support_opa_import",
            entity_id=result["run_id"],
        )
        db.commit()
        return result
    except OpaApiError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=f"Falha ao consultar a API do OPA Suite: {exc}") from exc
    except OpaImportInterrupted as exc:
        db.commit()
        raise HTTPException(status_code=502, detail=f"Retomada OPA interrompida no run #{exc.run_id}: {exc}") from exc
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        logger.exception("Falha inesperada na retomada da importação OPA Suite")
        raise HTTPException(status_code=500, detail="Falha inesperada ao retomar importação do OPA Suite.") from exc


@router.get("/opa/attendances", response_model=SupportOpaAttendancePage)
def opa_attendances(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_by: str = Query(default="opened_at"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    search: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    date_basis: str = Query(default="opened_at", pattern="^(opened_at|closed_at)$"),
    status: str | None = None,
    channel: str | None = None,
    attendant_id: str | None = None,
    attendant: str | None = None,
    department_id: str | None = None,
    department: str | None = None,
    reason_id: str | None = None,
    reason: str | None = None,
    protocol: str | None = None,
    customer: str | None = None,
    extra: OpaExtraFilters = Depends(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sortable_fields = {
        "opened_at": SupportOpaAttendance.opened_at,
        "closed_at": SupportOpaAttendance.closed_at,
        "protocol": SupportOpaAttendance.protocol,
        "customer_name": SupportOpaAttendance.customer_name,
        "attendant_name": SupportOpaAttendance.attendant_name,
        "department_name": SupportOpaAttendance.department_name,
        "reason_name": SupportOpaAttendance.reason_name,
        "channel": SupportOpaAttendance.channel,
        "status": SupportOpaAttendance.status,
        "rating": SupportOpaAttendance.rating,
        "tma_seconds": SupportOpaAttendance.tma_seconds,
    }
    if sort_by not in sortable_fields:
        raise HTTPException(status_code=422, detail="Campo de ordenação inválido para atendimentos OPA.")

    base = _apply_attendance_filters(
        select(SupportOpaAttendance),
        date_from=date_from,
        date_to=date_to,
        date_basis=date_basis,
        status=status,
        channel=channel,
        attendant_id=attendant_id,
        attendant=attendant,
        department_id=department_id,
        department=department,
        reason_id=reason_id,
        reason=reason,
        protocol=protocol,
        customer=customer,
        search=search,
        **extra.as_kwargs(),
    )
    count_statement = _apply_attendance_filters(
        select(func.count(SupportOpaAttendance.id)),
        date_from=date_from,
        date_to=date_to,
        date_basis=date_basis,
        status=status,
        channel=channel,
        attendant_id=attendant_id,
        attendant=attendant,
        department_id=department_id,
        department=department,
        reason_id=reason_id,
        reason=reason,
        protocol=protocol,
        customer=customer,
        search=search,
        **extra.as_kwargs(),
    )

    total = int(db.scalar(count_statement) or 0)
    total_pages = (total + page_size - 1) // page_size if total else 0
    order_column = sortable_fields[sort_by]
    order_expr = order_column.asc() if sort_dir == "asc" else order_column.desc()
    rows = db.scalars(
        base.order_by(order_expr, SupportOpaAttendance.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [_attendance_list_item(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


@router.get("/opa/overview", response_model=SupportOpaOverview)
def opa_overview(
    date_from: date,
    date_to: date,
    date_basis: str = Query(default="opened_at", pattern="^(opened_at|closed_at)$"),
    status: str | None = None,
    channel: str | None = None,
    attendant_id: str | None = None,
    department_id: str | None = None,
    reason_id: str | None = None,
    customer: str | None = None,
    search: str | None = None,
    extra: OpaExtraFilters = Depends(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    filters = OpaAttendanceFilters(
        date_from=date_from,
        date_to=date_to,
        date_basis=date_basis,
        status=status,
        channel=channel,
        attendant_id=attendant_id,
        department_id=department_id,
        reason_id=reason_id,
        customer=customer,
        search=search,
        **extra.as_kwargs(),
    )
    previous_filters = filters.previous_period()
    return {
        "current_period": {"date_from": date_from, "date_to": date_to},
        "previous_period": {"date_from": previous_filters.date_from, "date_to": previous_filters.date_to},
        **opa_overview_service.expanded_overview(db, filters),
    }


@router.get("/opa/timeseries", response_model=SupportOpaTimeseries)
def opa_timeseries(
    date_from: date,
    date_to: date,
    date_basis: str = Query(default="opened_at", pattern="^(opened_at|closed_at)$"),
    status: str | None = None,
    channel: str | None = None,
    attendant_id: str | None = None,
    department_id: str | None = None,
    reason_id: str | None = None,
    customer: str | None = None,
    search: str | None = None,
    extra: OpaExtraFilters = Depends(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Série diária do MESMO recorte da Visão Geral — o gráfico de tendência é
    uma decomposição dos cards, não um cálculo paralelo."""
    filters = OpaAttendanceFilters(
        date_from=date_from,
        date_to=date_to,
        date_basis=date_basis,
        status=status,
        channel=channel,
        attendant_id=attendant_id,
        department_id=department_id,
        reason_id=reason_id,
        customer=customer,
        search=search,
        **extra.as_kwargs(),
    )
    return {
        "date_basis": date_basis,
        "points": opa_overview_service.daily_timeseries(db, filters),
    }


@router.get("/opa/breakdowns", response_model=SupportOpaBreakdowns)
def opa_breakdowns(
    dimension: str = Query(pattern="^(attendant|department|reason|channel|status|customer)$"),
    sort_by: str = Query(default="total"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=20, ge=1, le=200),
    search: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    date_basis: str = Query(default="opened_at", pattern="^(opened_at|closed_at)$"),
    status: str | None = None,
    channel: str | None = None,
    attendant_id: str | None = None,
    attendant: str | None = None,
    department_id: str | None = None,
    department: str | None = None,
    reason_id: str | None = None,
    reason: str | None = None,
    protocol: str | None = None,
    customer: str | None = None,
    extra: OpaExtraFilters = Depends(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    filters = OpaAttendanceFilters(
        date_from=date_from,
        date_to=date_to,
        date_basis=date_basis,
        status=status,
        channel=channel,
        attendant_id=attendant_id,
        attendant=attendant,
        department_id=department_id,
        department=department,
        reason_id=reason_id,
        reason=reason,
        protocol=protocol,
        customer=customer,
        search=search,
        **extra.as_kwargs(),
    )
    total, items = _opa_breakdown_rows(
        db,
        dimension=dimension,
        filters=filters,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
    )
    return {"dimension": dimension, "total": total, "items": items}


@router.get("/opa/attendants/{attendant_id}/summary", response_model=SupportOpaAttendantSummary)
def opa_attendant_summary(
    attendant_id: str,
    date_from: date | None = None,
    date_to: date | None = None,
    date_basis: str = Query(default="opened_at", pattern="^(opened_at|closed_at)$"),
    status: str | None = None,
    channel: str | None = None,
    department_id: str | None = None,
    reason_id: str | None = None,
    customer: str | None = None,
    search: str | None = None,
    extra: OpaExtraFilters = Depends(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    filters = OpaAttendanceFilters(
        date_from=date_from,
        date_to=date_to,
        date_basis=date_basis,
        status=status,
        channel=channel,
        department_id=department_id,
        reason_id=reason_id,
        customer=customer,
        search=search,
        **extra.as_kwargs(),
    )
    summary = opa_attendant_service.attendant_summary(db, attendant_id, filters)
    if summary is None:
        raise HTTPException(status_code=404, detail="Atendente OPA não encontrado.")
    return summary


@router.get("/opa/attendances/{attendance_id}", response_model=SupportOpaAttendanceDetail)
def opa_attendance_detail(
    attendance_id: int,
    include_external: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = db.get(SupportOpaAttendance, attendance_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Atendimento OPA não encontrado.")

    external_detail = None
    external_error = None
    if include_external:
        try:
            external_payload = get_opa_client().get_attendance_detail(row.source_id)
            external_detail = _attendance_enriched_detail(external_payload)
            customer_name = external_detail.get("customer_name")
            customer_id = external_detail.get("customer_id")
            if customer_name and (row.customer_name != customer_name or (customer_id and row.customer_id != customer_id)):
                row.customer_name = customer_name
                if customer_id:
                    row.customer_id = customer_id
                db.commit()
        except Exception as exc:
            logger.warning("Falha ao enriquecer atendimento OPA %s: %s", row.source_id, exc)
            external_error = str(exc)

    return {
        "id": row.id,
        "source_id": row.source_id,
        "local": _attendance_local_detail(row),
        "enriched": external_detail,
        "external_detail_available": external_detail is not None,
        "external_detail_error": external_error,
    }


@router.get("/opa/attendances/{attendance_id}/timeline", response_model=SupportOpaAttendanceTimeline)
def opa_attendance_timeline(
    attendance_id: int,
    include_messages: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = db.get(SupportOpaAttendance, attendance_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Atendimento OPA não encontrado.")
    return opa_timeline_service.build_timeline(db, row, include_messages=include_messages)


@router.get("/opa/filters", response_model=SupportOpaFilters)
def opa_filters(
    date_from: date | None = None,
    date_to: date | None = None,
    date_basis: str = Query(default="opened_at", pattern="^(opened_at|closed_at)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    def options(value_field, label_field=None):
        label_field = label_field or value_field
        statement = select(value_field, label_field).where(value_field.isnot(None), value_field != "")
        if date_from or date_to:
            statement = _apply_attendance_filters(
                statement,
                date_from=date_from,
                date_to=date_to,
                date_basis=date_basis,
                status=None,
                channel=None,
                attendant_id=None,
                attendant=None,
                department_id=None,
                department=None,
                reason_id=None,
                reason=None,
                protocol=None,
                customer=None,
                search=None,
            )
        rows = db.execute(statement.group_by(value_field, label_field).order_by(label_field.asc()).limit(200)).all()
        return [{"value": str(row[0]), "label": str(row[1])} for row in rows if row[0]]

    # Etiquetas não têm coluna de nome no atendimento (só o id vem no payload),
    # então o rótulo sai da dimensão já sincronizada do OPA — sem isso a tela
    # mostraria hashes ao usuário. Só aparecem etiquetas ativas do cadastro.
    tag_rows = db.execute(
        select(SupportOpaDimension.source_id, SupportOpaDimension.name)
        .where(SupportOpaDimension.dimension_type == "tag", SupportOpaDimension.name.isnot(None))
        .order_by(SupportOpaDimension.name.asc())
        .limit(500)
    ).all()

    return {
        "attendants": options(SupportOpaAttendance.attendant_id, SupportOpaAttendance.attendant_name),
        "departments": options(SupportOpaAttendance.department_id, SupportOpaAttendance.department_name),
        "channels": options(SupportOpaAttendance.channel),
        "statuses": options(SupportOpaAttendance.status),
        "reasons": options(SupportOpaAttendance.reason_id, SupportOpaAttendance.reason_name),
        "tags": [{"value": str(row[0]), "label": str(row[1])} for row in tag_rows if row[0]],
    }


def _can_sync_opa(user: User) -> bool:
    """Mesma fonte de verdade do `require_permission("support:sync_opa")` usado
    nas rotas de sincronização — aqui a checagem precisa ser inline porque a
    rota é acessível a leitores, e só a AÇÃO de publicar/remover um filtro
    global é restrita."""
    return "support:sync_opa" in permissions_for_user(user)


def _saved_filter_payload(row: SupportOpaSavedFilter) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "scope": row.scope,
        "filters": row.filters_json or {},
        "owner_id": row.owner_id,
        "updated_at": row.updated_at,
    }


def _visible_saved_filters(db: Session, user: User) -> list[SupportOpaSavedFilter]:
    return list(
        db.scalars(
            select(SupportOpaSavedFilter)
            .where(
                or_(
                    SupportOpaSavedFilter.scope == "global",
                    SupportOpaSavedFilter.owner_id == user.id,
                )
            )
            .order_by(SupportOpaSavedFilter.scope.asc(), SupportOpaSavedFilter.name.asc())
        ).all()
    )


@router.get("/opa/saved-filters", response_model=list[SupportOpaSavedFilterSchema])
def opa_saved_filters(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Filtros salvos visíveis pro usuário: os globais da operação e os pessoais
    dele. Nunca devolve o pessoal de outra pessoa."""
    return [_saved_filter_payload(row) for row in _visible_saved_filters(db, user)]


@router.post("/opa/saved-filters", response_model=SupportOpaSavedFilterSchema, status_code=201)
def create_opa_saved_filter(
    payload: SupportOpaSavedFilterCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Salvar um recorte como "global" publica ele pra operação inteira, então
    # exige a mesma permissão de gestão do módulo — qualquer leitor pode criar
    # os próprios recortes pessoais.
    if payload.scope == "global" and not _can_sync_opa(user):
        raise HTTPException(status_code=403, detail="Somente quem administra o SGP pode publicar um filtro global.")

    row = SupportOpaSavedFilter(
        name=payload.name.strip(),
        scope=payload.scope,
        filters_json=payload.filters or {},
        # Filtro global não pertence a ninguém: se o autor for desativado, o
        # recorte oficial da operação não pode desaparecer junto (`ondelete=CASCADE`).
        owner_id=None if payload.scope == "global" else user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _saved_filter_payload(row)


@router.delete("/opa/saved-filters/{saved_filter_id}")
def delete_opa_saved_filter(
    saved_filter_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = db.get(SupportOpaSavedFilter, saved_filter_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Filtro salvo não encontrado.")
    if row.scope == "global":
        if not _can_sync_opa(user):
            raise HTTPException(status_code=403, detail="Somente quem administra o SGP pode remover um filtro global.")
    elif row.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Filtro salvo não encontrado.")
    db.delete(row)
    db.commit()
    return {"status": "deleted"}


@router.get("/opa-metrics", response_model=SupportOpaMetrics)
def opa_metrics(
    date_from: date,
    date_to: date,
    date_basis: str = Query(default="opened_at", pattern="^(opened_at|closed_at)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validate_period(date_from, date_to)
    start_at, end_at = opa_period_bounds(date_from, date_to)
    date_column = SupportOpaAttendance.closed_at if date_basis == "closed_at" else SupportOpaAttendance.opened_at
    base_filters = [
        date_column >= start_at,
        date_column < end_at,
    ]
    total, closed, avg_tma, avg_tmr, avg_tmr_all, tmr_all_count, avg_rating = db.execute(
        select(
            func.count(SupportOpaAttendance.id),
            func.count(SupportOpaAttendance.closed_at),
            func.avg(SupportOpaAttendance.tma_seconds),
            func.avg(SupportOpaAttendance.tmr_seconds),
            func.avg(SupportOpaAttendance.tmr_all_responses_seconds),
            # COUNT ignora NULL igual AVG - denominador real da media de TMR
            # geral, que tem cobertura parcial do historico (norma de
            # qualidade de dados, secao 1 - denominador explicito).
            func.count(SupportOpaAttendance.tmr_all_responses_seconds),
            func.avg(SupportOpaAttendance.rating),
        ).where(*base_filters)
    ).one()

    def grouped(field):
        label_expr = func.coalesce(field, "Não identificado")
        rows = db.execute(
            select(
                label_expr.label("label"),
                func.count(SupportOpaAttendance.id).label("total"),
                func.avg(SupportOpaAttendance.tma_seconds).label("average_tma_seconds"),
                func.avg(SupportOpaAttendance.tmr_seconds).label("average_tmr_seconds"),
                func.avg(SupportOpaAttendance.tmr_all_responses_seconds).label("average_tmr_all_responses_seconds"),
                func.count(SupportOpaAttendance.tmr_all_responses_seconds).label("tmr_all_count"),
                func.avg(SupportOpaAttendance.rating).label("average_rating"),
            )
            .where(*base_filters)
            .group_by(label_expr)
            .order_by(func.count(SupportOpaAttendance.id).desc())
            .limit(20)
        ).all()
        return [
            {
                "label": row.label,
                "total": int(row.total or 0),
                "average_tma_seconds": float(row.average_tma_seconds) if row.average_tma_seconds is not None else None,
                "average_tmr_seconds": float(row.average_tmr_seconds) if row.average_tmr_seconds is not None else None,
                "average_tmr_all_responses_seconds": (
                    float(row.average_tmr_all_responses_seconds)
                    if row.average_tmr_all_responses_seconds is not None
                    else None
                ),
                "tmr_all_responses_coverage": opa_overview_service.coverage(int(row.tmr_all_count or 0), int(row.total or 0)),
                "average_rating": float(row.average_rating) if row.average_rating is not None else None,
            }
            for row in rows
        ]

    total = int(total or 0)
    return {
        "date_from": date_from,
        "date_to": date_to,
        "total_attendances": total,
        "closed_attendances": int(closed or 0),
        "average_tma_seconds": float(avg_tma) if avg_tma is not None else None,
        "average_tmr_seconds": float(avg_tmr) if avg_tmr is not None else None,
        "average_tmr_all_responses_seconds": float(avg_tmr_all) if avg_tmr_all is not None else None,
        "tmr_all_responses_coverage": opa_overview_service.coverage(int(tmr_all_count or 0), total),
        "average_rating": float(avg_rating) if avg_rating is not None else None,
        "by_attendant": grouped(SupportOpaAttendance.attendant_name),
        "by_reason": grouped(SupportOpaAttendance.reason_name),
    }
