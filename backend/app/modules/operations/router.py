from __future__ import annotations

import logging
from datetime import date, datetime, time, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.security import get_current_user, permissions_for_user, require_permission
from app.db.session import SessionLocal, get_db
from app.models import User
from app.services.audit_log import record_audit_log, snapshot
from app.services.calculation import get_setting, upsert_setting
from app.services.ixc_scheduler import (
    IXC_SYNC_BACKLOG_SWEEP_INTERVAL_MINUTES_KEY,
    IXC_SYNC_DEFAULT_LOOKBACK_DAYS,
    IXC_SYNC_ENABLED_KEY,
    IXC_SYNC_INTERVAL_MINUTES_KEY,
    IXC_SYNC_LOOKBACK_DAYS_KEY,
    IXC_SYNC_SECTOR_IDS_KEY,
    recompute_next_allowed_at,
)
from app.services.ixc_client import IxcApiError, IxcQueryLimitError, get_ixc_client

from . import backfill, queries, services
from .ixc_ingestion import import_current_month_period
from .models import OperationIxcCollaborator, OperationOrder, OperationResponsibleAssignment, OperationResponsibleDirectorySetting, OperationSavedFilter, OperationSubjectTypeMapping, OperationTeamModel, OperationTeamTargetRule
from .period import OPERATIONS_TIMEZONE_NAME, operations_period_bounds, validate_operations_period
from .scope import IXC_SECTORS, MAX_FILTER_VALUES_PER_FIELD, ixc_sector_scope_label, normalize_ixc_sector_ids
from .schemas import (
    OperationBreakdownItem,
    OperationSlaRiskItem,
    OperationBackfillJobOut,
    OperationCalendar,
    OperationCalendarDayDetail,
    OperationCalendarMonthlyDetail,
    OperationCollaboratorSla,
    OperationConfigurationImportResult,
    OperationConfigurationJson,
    OperationControlTower,
    OperationDataFreshness,
    OperationFilters,
    OperationImportRequest,
    OperationImportResult,
    OperationIxcSyncSettings,
    OperationIxcSyncSettingsUpdate,
    OperationIxcCollaboratorSyncResult,
    OperationOpeningsAnalytics,
    OperationOpenBacklogJobOut,
    OperationOrderPage,
    OperationOverview,
    OperationWorkScheduleOverview,
    OperationPeriod,
    OperationSavedFilterCreate,
    OperationSavedFilterOut,
    OperationSavedFilterUpdate,
    OperationSlaHierarchy,
    OperationSlaItem,
    OperationSubjectVolumeAlerts,
    OperationTrendSeries,
    OperationWarrantyAnalytics,
    OperationResponsibleAssignmentUpdate,
    OperationResponsibleDirectoryUpdate,
    OperationTeamConfiguration,
    OperationTeamModelCreate,
    OperationTeamModelOut,
    OperationTeamModelUpdate,
    OperationSubjectTypeBulkUpdate,
    OperationSubjectTypeMappingOut,
)


logger = logging.getLogger("operations")
router = APIRouter(
    prefix="/operations",
    tags=["operations"],
    dependencies=[Depends(require_permission("operations:read"))],
)


def _validated_period(date_from: date, date_to: date) -> tuple[date, date]:
    validate_operations_period(date_from, date_to)
    return date_from, date_to


def _validated_ixc_sector_ids(sector_ids: list[str] | None) -> list[str]:
    try:
        return normalize_ixc_sector_ids(sector_ids)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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


def _sync_settings_response(db: Session) -> dict:
    sector_ids = _validated_ixc_sector_ids(
        (get_setting(db, IXC_SYNC_SECTOR_IDS_KEY, "") or "").split(",")
    )
    return {
        "enabled": _bool_setting(get_setting(db, IXC_SYNC_ENABLED_KEY, ""), False),
        "interval_minutes": _int_setting(
            get_setting(db, IXC_SYNC_INTERVAL_MINUTES_KEY, ""),
            20,
            minimum=5,
            maximum=1440,
        ),
        "backlog_sweep_interval_minutes": _int_setting(
            get_setting(db, IXC_SYNC_BACKLOG_SWEEP_INTERVAL_MINUTES_KEY, ""),
            60,
            minimum=15,
            maximum=1440,
        ),
        "lookback_days": _int_setting(
            get_setting(db, IXC_SYNC_LOOKBACK_DAYS_KEY, ""),
            IXC_SYNC_DEFAULT_LOOKBACK_DAYS,
            minimum=1,
            maximum=30,
        ),
        "sector_ids": sector_ids,
        "sector_scope_label": ixc_sector_scope_label(sector_ids),
        "available_sectors": [{"id": sector_id, "name": name} for sector_id, name in IXC_SECTORS],
    }


def _validate_team_thresholds(values: dict) -> None:
    median = int(values["median_from_quantity"])
    good = int(values["good_from_quantity"])
    daily_target = int(values["daily_target"])
    if not 1 < median < good < daily_target:
        raise HTTPException(
            status_code=422,
            detail="As faixas precisam respeitar a ordem: abaixo, mediano, bom e excelente/meta.",
        )


def _validate_target_rule(values: dict) -> None:
    median = int(values["median_from_quantity"])
    good = int(values["good_from_quantity"])
    target = int(values["target_quantity"])
    if not 1 < median < good < target:
        raise HTTPException(status_code=422, detail="As faixas da meta precisam estar em ordem crescente.")
    if values["period_type"] != "monthly" and values.get("enabled") and (
        values.get("start_time") is None or values.get("end_time") is None
    ):
        raise HTTPException(status_code=422, detail="Informe início e término da jornada ativa.")


def _default_target_rules(values: dict) -> list[dict]:
    base = {
        "median_from_quantity": int(values["median_from_quantity"]),
        "good_from_quantity": int(values["good_from_quantity"]),
        "target_quantity": int(values["daily_target"]),
    }
    return [
        {"period_type": "weekday", "enabled": True, **base, "start_time": time(8), "end_time": time(18)},
        {"period_type": "saturday", "enabled": True, **base, "start_time": time(8), "end_time": time(18)},
        {"period_type": "sunday", "enabled": False, **base, "start_time": None, "end_time": None},
        {
            "period_type": "monthly",
            "enabled": True,
            "median_from_quantity": base["median_from_quantity"] * 22,
            "good_from_quantity": base["good_from_quantity"] * 22,
            "target_quantity": base["target_quantity"] * 22,
            "start_time": None,
            "end_time": None,
        },
    ]


def _replace_target_rules(db: Session, item: OperationTeamModel, rules: list[dict]) -> None:
    normalized = rules or _default_target_rules({
        "median_from_quantity": item.median_from_quantity,
        "good_from_quantity": item.good_from_quantity,
        "daily_target": item.daily_target,
    })
    period_types = [rule["period_type"] for rule in normalized]
    if len(set(period_types)) != len(period_types):
        raise HTTPException(status_code=422, detail="Cada tipo de período pode aparecer somente uma vez.")
    for rule in normalized:
        _validate_target_rule(rule)
    if item.id is not None:
        db.execute(delete(OperationTeamTargetRule).where(OperationTeamTargetRule.team_model_id == item.id))
        db.flush()
        db.expire(item, ["target_rules"])
    else:
        item.target_rules.clear()
    item.target_rules.extend(OperationTeamTargetRule(**rule) for rule in normalized)
    weekday = next((rule for rule in normalized if rule["period_type"] == "weekday"), None)
    if weekday:
        item.median_from_quantity = int(weekday["median_from_quantity"])
        item.good_from_quantity = int(weekday["good_from_quantity"])
        item.daily_target = int(weekday["target_quantity"])


def _normalize_team_model_name(value: str) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise HTTPException(status_code=422, detail="Informe o nome do modelo de equipe.")
    return normalized


def _normalize_responsible_name(value: str) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise HTTPException(status_code=422, detail="Informe o nome do colaborador.")
    return normalized


def _responsible_identity(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _team_model_or_404(db: Session, model_id: int) -> OperationTeamModel:
    item = db.get(OperationTeamModel, model_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Modelo de equipe não encontrado.")
    return item


def _filter_params(
    team_models: list[str] = Query(default_factory=list),
    companies: list[str] = Query(default_factory=list),
    regionals: list[str] = Query(default_factory=list),
    states: list[str] = Query(default_factory=list),
    cities: list[str] = Query(default_factory=list),
    contract_types: list[str] = Query(default_factory=list),
    person_types: list[str] = Query(default_factory=list),
    os_types: list[str] = Query(default_factory=list),
    subjects: list[str] = Query(default_factory=list),
    diagnoses: list[str] = Query(default_factory=list),
    departments: list[str] = Query(default_factory=list),
    sectors: list[str] = Query(default_factory=list),
    priorities: list[str] = Query(default_factory=list),
    creators: list[str] = Query(default_factory=list),
    responsibles: list[str] = Query(default_factory=list),
    responsible_ixc_ids: list[int] = Query(default_factory=list),
    statuses: list[str] = Query(default_factory=list),
    sla_statuses: list[str] = Query(default_factory=list),
    projects: list[str] = Query(default_factory=list),
    pops: list[str] = Query(default_factory=list),
    opened_weekdays: list[str] = Query(default_factory=list),
    closed_weekdays: list[str] = Query(default_factory=list),
    custom_window_basis: list[str] = Query(default_factory=list),
    custom_window_start_weekday: str | None = Query(default=None, max_length=20),
    custom_window_start_time: str | None = Query(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$"),
    custom_window_end_weekday: str | None = Query(default=None, max_length=20),
    custom_window_end_time: str | None = Query(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$"),
    closed_time_from: str | None = Query(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$"),
    closed_time_to: str | None = Query(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$"),
    search: str | None = Query(default=None, max_length=160),
) -> dict:
    values = {
        "team_models": team_models,
        "companies": companies,
        "regionals": regionals,
        "states": states,
        "cities": cities,
        "contract_types": contract_types,
        "person_types": person_types,
        "os_types": os_types,
        "subjects": subjects,
        "diagnoses": diagnoses,
        "departments": departments,
        "sectors": sectors,
        "priorities": priorities,
        "creators": creators,
        "responsibles": responsibles,
        "statuses": statuses,
        "sla_statuses": sla_statuses,
        "projects": projects,
        "pops": pops,
        "opened_weekdays": opened_weekdays,
        "closed_weekdays": closed_weekdays,
        "custom_window_basis": custom_window_basis,
        "custom_window_start_weekday": custom_window_start_weekday,
        "custom_window_start_time": custom_window_start_time,
        "custom_window_end_weekday": custom_window_end_weekday,
        "custom_window_end_time": custom_window_end_time,
        "closed_time_from": closed_time_from,
        "closed_time_to": closed_time_to,
        "search": search,
    }
    for field, selected in values.items():
        if field in {
            "search",
            "closed_time_from",
            "closed_time_to",
            "custom_window_start_weekday",
            "custom_window_start_time",
            "custom_window_end_weekday",
            "custom_window_end_time",
        }:
            continue
        if field != "responsibles" and len(selected) > MAX_FILTER_VALUES_PER_FIELD:
            raise HTTPException(status_code=422, detail=f"O filtro '{field}' excede o limite de valores permitidos.")
        values[field] = list(dict.fromkeys(value.strip() for value in selected if value.strip()))
    if len(responsible_ixc_ids) > MAX_FILTER_VALUES_PER_FIELD:
        raise HTTPException(status_code=422, detail="O filtro 'responsible_ixc_ids' excede o limite de valores permitidos.")
    values["responsible_ixc_ids"] = list(dict.fromkeys(responsible_ixc_ids))
    return values


@router.get("/period", response_model=OperationPeriod)
def available_period():
    allowed_from, allowed_to = operations_period_bounds()
    return {
        "date_from": allowed_to.replace(day=1),
        "date_to": allowed_to,
        "allowed_from": allowed_from,
        "allowed_to": allowed_to,
        "timezone": OPERATIONS_TIMEZONE_NAME,
    }


@router.get("/ixc-sync-settings", response_model=OperationIxcSyncSettings)
def ixc_sync_settings(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("operations:sync_ixc")),
):
    return _sync_settings_response(db)


@router.put("/ixc-sync-settings", response_model=OperationIxcSyncSettings)
def update_ixc_sync_settings(
    payload: OperationIxcSyncSettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("operations:sync_ixc")),
):
    before = _sync_settings_response(db)
    if payload.enabled is not None:
        upsert_setting(
            db,
            IXC_SYNC_ENABLED_KEY,
            "true" if payload.enabled else "false",
            description="Liga ou desliga a sincronizacao automatica do IXC.",
        )
    if payload.interval_minutes is not None:
        upsert_setting(
            db,
            IXC_SYNC_INTERVAL_MINUTES_KEY,
            str(payload.interval_minutes),
            description="Intervalo em minutos da sincronizacao automatica do IXC.",
        )
        # Sem isso, o novo intervalo só valeria na tentativa seguinte ao horário já calculado com o
        # intervalo anterior (até 1h de atraso num caso real) - ver ixc_scheduler.recompute_next_allowed_at.
        recompute_next_allowed_at(db, payload.interval_minutes)
    if payload.backlog_sweep_interval_minutes is not None:
        upsert_setting(
            db,
            IXC_SYNC_BACKLOG_SWEEP_INTERVAL_MINUTES_KEY,
            str(payload.backlog_sweep_interval_minutes),
            description="Intervalo em minutos da varredura de backlog aberto do IXC.",
        )
    if payload.lookback_days is not None:
        upsert_setting(
            db,
            IXC_SYNC_LOOKBACK_DAYS_KEY,
            str(payload.lookback_days),
            description="Quantos dias antes de hoje o ciclo automatico do IXC reimporta a cada rodada.",
        )
    if payload.sector_ids is not None:
        sector_ids = _validated_ixc_sector_ids(payload.sector_ids)
        upsert_setting(
            db,
            IXC_SYNC_SECTOR_IDS_KEY,
            ",".join(sector_ids),
            description="Setores IXC usados pela sincronizacao automatica da Operacao Analitica.",
        )
    after = _sync_settings_response(db)
    record_audit_log(db, user, "update", "operations_ixc_sync_settings", "ixc", before, after)
    db.commit()
    return after


@router.post("/imports", response_model=OperationImportResult)
def import_period(
    payload: OperationImportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("operations:sync_ixc")),
):
    validate_operations_period(payload.date_from, payload.date_to)
    if payload.date_from != payload.date_to:
        raise HTTPException(
            status_code=422,
            detail="Por segurança, a atualização do IXC é processada um dia por vez. A interface divide o período automaticamente.",
        )
    try:
        result = import_current_month_period(
            db,
            get_ixc_client(),
            date_from=payload.date_from,
            date_to=payload.date_to,
            imported_by=user.id,
            sector_ids=_validated_ixc_sector_ids(payload.sector_ids),
        )
        db.commit()
        return result
    except IxcQueryLimitError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IxcApiError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=f"Falha ao consultar a API do IXC: {exc}") from exc
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        logger.exception("Falha inesperada na importação analítica do IXC")
        raise HTTPException(status_code=500, detail="Falha inesperada ao importar o período selecionado do IXC.") from exc



def _run_backfill_job(job_id: int) -> None:
    with SessionLocal() as db:
        job = db.get(backfill.OperationBackfillJob, job_id)
        if job is None:
            return
        backfill.run_backfill(
            db,
            date_from=job.date_from,
            date_to=job.date_to,
            sector_ids=list(job.sector_ids),
            resume_job_id=job.id,
            delay_seconds=0.25,
        )


@router.post("/imports/backfill", response_model=OperationBackfillJobOut)
def start_backfill_import(
    payload: OperationImportRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("operations:sync_ixc")),
):
    validate_operations_period(payload.date_from, payload.date_to)
    job = backfill.create_backfill_job(
        db,
        date_from=payload.date_from,
        date_to=payload.date_to,
        sector_ids=_validated_ixc_sector_ids(payload.sector_ids),
        requested_by=user.id,
    )
    background_tasks.add_task(_run_backfill_job, job.id)
    db.refresh(job)
    return job


@router.get("/imports/backfill/{job_id}", response_model=OperationBackfillJobOut)
def backfill_import_status(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("operations:sync_ixc")),
):
    job = db.get(backfill.OperationBackfillJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Importacao historica nao encontrada.")
    return job

def _run_open_backlog_job(job_id: int) -> None:
    with SessionLocal() as db:
        job = db.get(backfill.OperationOpenBacklogJob, job_id)
        if job is None:
            return
        try:
            backfill.run_open_backlog_job(db, job_id=job.id, delay_seconds=0.25)
        except Exception:
            # run_open_backlog_job já marca o job como "failed" e grava o motivo em job.errors antes
            # de repropagar - aqui só evita que uma BackgroundTask sem handler derrube o worker por
            # uma exceção não tratada. O detalhe fica no log do backend, nunca exposto ao usuário.
            logger.exception("Falha na varredura de backlog aberto do IXC (job=%s)", job_id)


@router.post("/imports/open-backlog", response_model=OperationOpenBacklogJobOut)
def start_open_backlog_import(
    background_tasks: BackgroundTasks,
    sector_ids: list[str] = Query(default_factory=list),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("operations:sync_ixc")),
):
    try:
        job = backfill.create_open_backlog_job(
            db,
            sector_ids=_validated_ixc_sector_ids(sector_ids),
            requested_by=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    background_tasks.add_task(_run_open_backlog_job, job.id)
    db.refresh(job)
    return job


@router.get("/imports/open-backlog/{job_id}", response_model=OperationOpenBacklogJobOut)
def open_backlog_import_status(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("operations:sync_ixc")),
):
    job = db.get(backfill.OperationOpenBacklogJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Varredura de backlog aberto não encontrada.")
    return job


@router.get("/filters", response_model=OperationFilters)
def filters(
    date_from: date | None = None,
    date_to: date | None = None,
    scope: Literal["period", "in_progress"] = "period",
    responsible_mode: Literal["all", "completed"] = "all",
    selected_filters: dict = Depends(_filter_params),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if scope == "period":
        if date_from is None or date_to is None:
            raise HTTPException(status_code=422, detail="Informe a data inicial e a data final para consultar este período.")
        _validated_period(date_from, date_to)
    else:
        allowed_from, allowed_to = operations_period_bounds()
        date_from = date_from or allowed_from
        date_to = date_to or allowed_to
    return queries.filter_options(
        db,
        date_from,
        date_to,
        user,
        responsible_mode=responsible_mode,
        scope=scope,
        **selected_filters,
    )


@router.get("/overview", response_model=OperationOverview)
def overview(
    date_from: date,
    date_to: date,
    selected_filters: dict = Depends(_filter_params),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validated_period(date_from, date_to)
    return queries.overview(
        db,
        date_from,
        date_to,
        user,
        **selected_filters,
    )


@router.get("/overview/work-schedule", response_model=OperationWorkScheduleOverview)
def overview_work_schedule(
    date_from: date,
    date_to: date,
    model_ids: list[int] = Query(default_factory=list),
    selected_filters: dict = Depends(_filter_params),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validated_period(date_from, date_to)
    if len(model_ids) > MAX_FILTER_VALUES_PER_FIELD:
        raise HTTPException(status_code=422, detail="Selecione menos modelos de equipe.")
    return services.work_schedule_overview(
        db,
        date_from,
        date_to,
        user,
        model_ids=model_ids,
        **selected_filters,
    )


@router.get("/overview/trends", response_model=OperationTrendSeries)
def overview_trends(
    date_from: date,
    date_to: date,
    granularity: Literal["day", "week", "month"] = "day",
    selected_filters: dict = Depends(_filter_params),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validated_period(date_from, date_to)
    return services.overview_trends(
        db,
        date_from,
        date_to,
        user,
        granularity=granularity,
        **selected_filters,
    )


@router.get("/overview/volume-alerts", response_model=OperationSubjectVolumeAlerts)
def overview_volume_alerts(
    date_from: date,
    date_to: date,
    selected_filters: dict = Depends(_filter_params),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validated_period(date_from, date_to)
    return services.subject_volume_alerts(db, date_to, user, **selected_filters)


@router.get("/overview/control-tower", response_model=OperationControlTower)
def overview_control_tower(
    date_from: date,
    date_to: date,
    level: Literal["subject", "regional", "city", "sector", "responsible"] = "subject",
    parent_subject: str | None = Query(default=None, max_length=220),
    parent_regional: str | None = Query(default=None, max_length=160),
    parent_city: str | None = Query(default=None, max_length=160),
    parent_sector: str | None = Query(default=None, max_length=160),
    selected_filters: dict = Depends(_filter_params),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validated_period(date_from, date_to)
    required_parents = {
        "regional": (parent_subject,),
        "city": (parent_subject, parent_regional),
        "sector": (parent_subject, parent_regional, parent_city),
        "responsible": (parent_subject, parent_regional, parent_city, parent_sector),
    }
    if level in required_parents and not all(required_parents[level]):
        raise HTTPException(status_code=422, detail="Informe todo o caminho pai para expandir este nível operacional.")
    return services.control_tower(
        db,
        date_to,
        user,
        level=level,
        path={
            "subject": parent_subject,
            "regional": parent_regional,
            "city": parent_city,
            "sector": parent_sector,
        },
        **selected_filters,
    )


@router.get(
    "/openings/analytics",
    response_model=OperationOpeningsAnalytics,
    dependencies=[Depends(require_permission("operations:view_openings"))],
)
def openings_analytics(
    date_from: date,
    date_to: date,
    granularity: Literal["day", "week", "month"] = "day",
    selected_filters: dict = Depends(_filter_params),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validated_period(date_from, date_to)
    return queries.openings_analytics(db, date_from, date_to, user, granularity=granularity, **selected_filters)


@router.get("/data-freshness", response_model=OperationDataFreshness)
def operations_data_freshness(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    del user
    return queries.data_freshness(db)


@router.get("/sla", response_model=list[OperationSlaItem], dependencies=[Depends(require_permission("operations:view_sla"))])
def sla(
    date_from: date,
    date_to: date,
    group_by: Literal["os_type", "subject", "diagnosis", "department", "sector"] = "os_type",
    selected_filters: dict = Depends(_filter_params),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validated_period(date_from, date_to)
    return queries.sla_breakdown(
        db,
        date_from,
        date_to,
        user,
        group_by,
        **selected_filters,
    )


@router.get("/sla/hierarchy", response_model=OperationSlaHierarchy, dependencies=[Depends(require_permission("operations:view_sla"))])
def sla_hierarchy(
    date_from: date,
    date_to: date,
    level: Literal["os_type", "subject", "diagnosis"] = "os_type",
    parent_os_type: str | None = Query(default=None, max_length=160),
    parent_subject: str | None = Query(default=None, max_length=220),
    selected_filters: dict = Depends(_filter_params),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validated_period(date_from, date_to)
    if parent_subject and not parent_os_type:
        raise HTTPException(status_code=422, detail="Informe o tipo geral ao filtrar um assunto específico.")
    return queries.sla_hierarchy(
        db,
        date_from,
        date_to,
        user,
        level,
        parent_os_type=parent_os_type,
        parent_subject=parent_subject,
        **selected_filters,
    )


@router.get("/sla/collaborators", response_model=OperationCollaboratorSla, dependencies=[Depends(require_permission("operations:view_sla"))])
def sla_collaborators(
    date_from: date,
    date_to: date,
    selected_filters: dict = Depends(_filter_params),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validated_period(date_from, date_to)
    return queries.collaborator_sla(db, date_from, date_to, user, **selected_filters)


@router.get(
    "/warranty",
    response_model=OperationWarrantyAnalytics,
    dependencies=[Depends(require_permission("operations:view_warranty"))],
)
def warranty(
    date_from: date,
    date_to: date,
    period_basis: Literal["opened", "closed"] = "opened",
    denominator: Literal["closed_origins", "active_origins", "maintenance_total", "activation_closed"] = "active_origins",
    selected_filters: dict = Depends(_filter_params),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validated_period(date_from, date_to)
    return queries.warranty_analytics(
        db,
        date_from,
        date_to,
        user,
        period_basis=period_basis,
        denominator=denominator,
        **selected_filters,
    )


@router.get("/calendar", response_model=OperationCalendar, dependencies=[Depends(require_permission("operations:view_calendar"))])
def calendar_view(
    date_from: date,
    date_to: date,
    group_by: Literal["regional", "collaborator"] = Query(default="regional"),
    selected_filters: dict = Depends(_filter_params),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validated_period(date_from, date_to)
    return services.monthly_calendar(db, date_to, user, group_by=group_by, **selected_filters)


@router.get("/calendar/orders", response_model=OperationOrderPage, dependencies=[Depends(require_permission("operations:view_calendar")), Depends(require_permission("operations:view_order_details"))])
def calendar_orders(
    day: date,
    regional: str = Query(min_length=1, max_length=160),
    responsible: str = Query(min_length=1, max_length=180),
    group_by: Literal["regional", "collaborator"] = Query(default="regional"),
    selected_filters: dict = Depends(_filter_params),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=10, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validated_period(day, day)
    return services.calendar_order_page(
        db,
        day,
        regional,
        responsible,
        user,
        group_by=group_by,
        page=page,
        page_size=page_size,
        **selected_filters,
    )


@router.get("/calendar/day-detail", response_model=OperationCalendarDayDetail, dependencies=[Depends(require_permission("operations:view_calendar")), Depends(require_permission("operations:view_order_details"))])
def calendar_day_detail(
    day: date,
    regional: str = Query(min_length=1, max_length=160),
    responsible: str = Query(min_length=1, max_length=180),
    group_by: Literal["regional", "collaborator"] = Query(default="regional"),
    reference_regional: str | None = Query(default=None, max_length=160),
    selected_filters: dict = Depends(_filter_params),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=10, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validated_period(day, day)
    return services.calendar_day_detail(
        db,
        day,
        regional,
        responsible,
        user,
        group_by=group_by,
        reference_regional=reference_regional,
        page=page,
        page_size=page_size,
        **selected_filters,
    )


@router.get("/calendar/week-detail", response_model=OperationCalendarDayDetail, dependencies=[Depends(require_permission("operations:view_calendar")), Depends(require_permission("operations:view_order_details"))])
def calendar_week_detail(
    date_from: date,
    date_to: date,
    regional: str = Query(min_length=1, max_length=160),
    responsible: str = Query(min_length=1, max_length=180),
    group_by: Literal["regional", "collaborator"] = Query(default="regional"),
    reference_regional: str | None = Query(default=None, max_length=160),
    selected_filters: dict = Depends(_filter_params),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=10, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validated_period(date_from, date_to)
    return services.calendar_week_detail(
        db,
        date_from,
        date_to,
        regional,
        responsible,
        user,
        group_by=group_by,
        reference_regional=reference_regional,
        page=page,
        page_size=page_size,
        **selected_filters,
    )


@router.get("/calendar/month-detail", response_model=OperationCalendarMonthlyDetail, dependencies=[Depends(require_permission("operations:view_calendar")), Depends(require_permission("operations:view_order_details"))])
def calendar_month_detail(
    date_from: date,
    date_to: date,
    regional: str = Query(min_length=1, max_length=160),
    responsible: str = Query(min_length=1, max_length=180),
    group_by: Literal["regional", "collaborator"] = Query(default="regional"),
    reference_regional: str | None = Query(default=None, max_length=160),
    selected_filters: dict = Depends(_filter_params),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=10, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validated_period(date_from, date_to)
    return services.calendar_month_detail(
        db,
        date_to,
        regional,
        responsible,
        user,
        group_by=group_by,
        reference_regional=reference_regional,
        page=page,
        page_size=page_size,
        **selected_filters,
    )


@router.get("/in-progress", response_model=list[OperationBreakdownItem], dependencies=[Depends(require_permission("operations:view_backlog"))])
def in_progress(
    group_by: Literal["regional", "city", "os_type", "subject", "status"] = "regional",
    selected_filters: dict = Depends(_filter_params),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return queries.in_progress_breakdown(
        db,
        user,
        group_by,
        **selected_filters,
    )


@router.get("/in-progress/sla-risk", response_model=list[OperationSlaRiskItem], dependencies=[Depends(require_permission("operations:view_backlog"))])
def in_progress_sla_risk(
    selected_filters: dict = Depends(_filter_params),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return queries.in_progress_sla_risk(db, user, **selected_filters)


@router.get("/in-progress/orders", response_model=OperationOrderPage, dependencies=[Depends(require_permission("operations:view_backlog")), Depends(require_permission("operations:view_order_details"))])
def in_progress_orders(
    selected_filters: dict = Depends(_filter_params),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=10, le=200),
    sort_by: str | None = Query(default=None, max_length=40),
    sort_dir: Literal["asc", "desc"] = Query(default="asc"),
    sla_risk: Literal["breached", "critical", "attention", "on_track", "no_target"] | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return queries.in_progress_order_page(
        db,
        user,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        sla_risk=sla_risk,
        **selected_filters,
    )


@router.get("/orders", response_model=OperationOrderPage, dependencies=[Depends(require_permission("operations:view_order_details"))])
def orders(
    date_from: date,
    date_to: date,
    selected_filters: dict = Depends(_filter_params),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=10, le=200),
    sort_by: str | None = Query(default=None, max_length=40),
    sort_dir: Literal["asc", "desc"] = Query(default="desc"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validated_period(date_from, date_to)
    return queries.order_page(
        db,
        date_from,
        date_to,
        user,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        **selected_filters,
    )


@router.get(
    "/openings/orders",
    response_model=OperationOrderPage,
    dependencies=[
        Depends(require_permission("operations:view_openings")),
        Depends(require_permission("operations:view_order_details")),
    ],
)
def opening_orders(
    date_from: date,
    date_to: date,
    selected_filters: dict = Depends(_filter_params),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=10, le=200),
    sort_by: str | None = Query(default=None, max_length=40),
    sort_dir: Literal["asc", "desc"] = Query(default="desc"),
    aging_bucket: Literal["0_1", "2_3", "4_7", "8_plus"] | None = Query(default=None),
    weekday: int | None = Query(default=None, ge=1, le=7),
    hour: int | None = Query(default=None, ge=0, le=23),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validated_period(date_from, date_to)
    return queries.opening_order_page(
        db,
        date_from,
        date_to,
        user,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        aging_bucket=aging_bucket,
        weekday=weekday,
        hour=hour,
        **selected_filters,
    )


def _saved_filter_or_404(db: Session, saved_filter_id: int, user_id: int) -> OperationSavedFilter:
    item = db.scalar(
        select(OperationSavedFilter).where(
            OperationSavedFilter.id == saved_filter_id,
            OperationSavedFilter.user_id == user_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Filtro salvo não encontrado.")
    return item


def _ensure_unique_filter_name(db: Session, user_id: int, name: str, exclude_id: int | None = None) -> None:
    stmt = select(OperationSavedFilter.id).where(
        OperationSavedFilter.user_id == user_id,
        func.lower(OperationSavedFilter.name) == name.casefold(),
    )
    if exclude_id is not None:
        stmt = stmt.where(OperationSavedFilter.id != exclude_id)
    if db.scalar(stmt) is not None:
        raise HTTPException(status_code=409, detail="Você já possui um filtro salvo com esse nome.")


def _saved_filter_permissions(user: User) -> set[str]:
    return permissions_for_user(user)


def _ensure_global_saved_filter_permission(user: User, action: Literal["read", "create", "update", "delete"]) -> None:
    if f"operations:views:{action}_global" not in _saved_filter_permissions(user):
        raise HTTPException(status_code=403, detail="Seu perfil não permite gerenciar visões globais.")


def _saved_filter_or_404_scoped(db: Session, saved_filter_id: int, user: User) -> OperationSavedFilter:
    item = db.scalar(select(OperationSavedFilter).where(OperationSavedFilter.id == saved_filter_id))
    if item is None or (item.visibility == "personal" and item.user_id != user.id):
        raise HTTPException(status_code=404, detail="Filtro salvo não encontrado.")
    return item


def _can_manage_saved_filter(user: User, item: OperationSavedFilter, action: Literal["update", "delete"]) -> bool:
    if item.visibility == "personal":
        return item.user_id == user.id and "operations:manage_filters" in _saved_filter_permissions(user)
    return f"operations:views:{action}_global" in _saved_filter_permissions(user)


def _ensure_unique_filter_name_scoped(
    db: Session,
    user_id: int,
    name: str,
    visibility: Literal["personal", "global"],
    exclude_id: int | None = None,
) -> None:
    stmt = select(OperationSavedFilter.id).where(func.lower(OperationSavedFilter.name) == name.casefold())
    if visibility == "personal":
        stmt = stmt.where(OperationSavedFilter.user_id == user_id, OperationSavedFilter.visibility == "personal")
    else:
        stmt = stmt.where(OperationSavedFilter.visibility == "global")
    if exclude_id is not None:
        stmt = stmt.where(OperationSavedFilter.id != exclude_id)
    if db.scalar(stmt) is not None:
        detail = "Já existe uma visão global com esse nome." if visibility == "global" else "Você já possui uma visão pessoal com esse nome."
        raise HTTPException(status_code=409, detail=detail)


@router.get("/saved-filters", response_model=list[OperationSavedFilterOut])
def list_saved_filters(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    condition = OperationSavedFilter.user_id == user.id
    if "operations:views:read_global" in _saved_filter_permissions(user):
        condition = condition | (OperationSavedFilter.visibility == "global")
    return list(
        db.scalars(
            select(OperationSavedFilter)
            .where(condition)
            .order_by(OperationSavedFilter.visibility.asc(), OperationSavedFilter.updated_at.desc(), OperationSavedFilter.name.asc())
        )
    )


@router.get("/team-configuration", response_model=OperationTeamConfiguration, dependencies=[Depends(require_permission("operations:manage_team_models"))])
def get_team_configuration(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return queries.team_configuration(db, user)


@router.put("/responsible-directory", response_model=OperationTeamConfiguration)
def update_responsible_directory(
    payload: OperationResponsibleDirectoryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("operations:manage_team_models")),
):
    setting = db.get(OperationResponsibleDirectorySetting, 1)
    if setting is None:
        setting = OperationResponsibleDirectorySetting(id=1)
        db.add(setting)
    setting.source = payload.source
    setting.updated_by = user.id
    setting.updated_at = datetime.now(timezone.utc)
    db.commit()
    return queries.team_configuration(db, user)


@router.post("/responsible-directory/sync", response_model=OperationIxcCollaboratorSyncResult)
def sync_ixc_collaborator_directory(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("operations:sync_ixc")),
):
    if "operations:manage_team_models" not in permissions_for_user(user):
        raise HTTPException(status_code=403, detail="Seu perfil não permite administrar o cadastro de colaboradores.")
    try:
        # Cadastro é uma sincronização manual e paginada; não impomos corte de
        # colaboradores para que a lista do IXC permaneça completa.
        records = list(get_ixc_client().list_all("funcionarios", rp=200, sortname="funcionarios.id"))
        now = datetime.now(timezone.utc)
        existing = {
            item.source_employee_id: item
            for item in db.scalars(select(OperationIxcCollaborator))
        }
        seen: set[str] = set()
        imported = 0
        for record in records:
            source_id = str(record.get("id") or "").strip()
            name = " ".join(str(record.get("funcionario") or record.get("nome") or "").strip().split())
            if not source_id or not name:
                continue
            active_raw = str(record.get("ativo") or record.get("status") or "S").strip().casefold()
            active = active_raw not in {"n", "nao", "não", "0", "inativo", "false"}
            item = existing.get(source_id)
            if item is None:
                item = OperationIxcCollaborator(source_employee_id=source_id, name=name)
                db.add(item)
            item.name, item.active, item.last_synced_at = name, active, now
            seen.add(source_id)
            imported += 1
        for source_id, item in existing.items():
            if source_id not in seen:
                item.active = False
                item.last_synced_at = now
        db.commit()
        return {"imported": imported, "active": sum(1 for record in records if str(record.get("ativo") or record.get("status") or "S").strip().casefold() not in {"n", "nao", "não", "0", "inativo", "false"}), "synced_at": now}
    except IxcQueryLimitError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IxcApiError as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao sincronizar colaboradores do IXC: {exc}") from exc


@router.get("/configuration-json", response_model=OperationConfigurationJson)
def export_configuration_json(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("operations:manage_team_models")),
):
    """Portable, ID-free configuration snapshot for the operational module."""
    permissions = permissions_for_user(user)
    models = list(db.scalars(select(OperationTeamModel).order_by(OperationTeamModel.name.asc())))
    assignments = list(db.scalars(select(OperationResponsibleAssignment).order_by(OperationResponsibleAssignment.updated_at.desc())))
    model_names = {item.id: item.name for item in models}
    unique_assignments: dict[str, OperationResponsibleAssignment] = {}
    for assignment in assignments:
        unique_assignments.setdefault(_responsible_identity(assignment.responsible_name), assignment)

    result: dict = {
        "schema_version": 1,
        "team_models": [
            {
                "name": item.name,
                "daily_target": item.daily_target,
                "median_from_quantity": item.median_from_quantity,
                "good_from_quantity": item.good_from_quantity,
                "below_target_color": item.below_target_color,
                "median_color": item.median_color,
                "good_color": item.good_color,
                "excellent_color": item.excellent_color,
                "active": item.active,
                "target_rules": [
                    {
                        "period_type": rule.period_type,
                        "enabled": rule.enabled,
                        "median_from_quantity": rule.median_from_quantity,
                        "good_from_quantity": rule.good_from_quantity,
                        "target_quantity": rule.target_quantity,
                        "start_time": rule.start_time,
                        "end_time": rule.end_time,
                    }
                    for rule in item.target_rules
                ],
            }
            for item in models
        ],
        "team_members": [
            {
                "responsible_name": item.responsible_name,
                "regional": item.regional,
                "team_model_name": model_names.get(item.team_model_id),
            }
            for item in unique_assignments.values()
        ],
        "subject_mappings": [],
        "saved_filters": [],
    }
    if "operations:manage_subjects" in permissions:
        result["subject_mappings"] = [
            {"subject": item.subject, "os_type": item.os_type, "active": item.active}
            for item in db.scalars(select(OperationSubjectTypeMapping).order_by(OperationSubjectTypeMapping.subject.asc()))
        ]
    if "operations:manage_filters" in permissions:
        views = list_saved_filters(db=db, user=user)
        result["saved_filters"] = [
            {"name": item.name, "filters": item.filters, "visibility": item.visibility}
            for item in views
        ]
    return result


@router.post("/configuration-json", response_model=OperationConfigurationImportResult)
def import_configuration_json(
    payload: OperationConfigurationJson,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("operations:manage_team_models")),
):
    """Merges a portable configuration snapshot without relying on database IDs."""
    permissions = permissions_for_user(user)
    if payload.subject_mappings and "operations:manage_subjects" not in permissions:
        raise HTTPException(status_code=403, detail="Seu perfil não permite importar classificações de assuntos.")
    if payload.saved_filters and "operations:manage_filters" not in permissions:
        raise HTTPException(status_code=403, detail="Seu perfil não permite importar visões salvas.")
    if any(item.visibility == "global" for item in payload.saved_filters):
        _ensure_global_saved_filter_permission(user, "create")

    try:
        existing_models = {
            item.name.casefold(): item
            for item in db.scalars(select(OperationTeamModel))
        }
        models_by_name: dict[str, OperationTeamModel] = {}
        imported_models = 0
        for incoming in payload.team_models:
            values = incoming.model_dump()
            target_rules = values.pop("target_rules", [])
            name = _normalize_team_model_name(values.pop("name"))
            values["name"] = name
            _validate_team_thresholds(values)
            item = existing_models.get(name.casefold())
            if item is None:
                item = OperationTeamModel(**values, created_by=user.id)
                _replace_target_rules(db, item, target_rules)
                db.add(item)
                db.flush()
            else:
                for field, value in values.items():
                    setattr(item, field, value)
                _replace_target_rules(db, item, target_rules)
                item.updated_at = datetime.now(timezone.utc)
            models_by_name[name.casefold()] = item
            imported_models += 1

        # Include existing models so an assignment-only file remains valid.
        for item in db.scalars(select(OperationTeamModel)):
            models_by_name.setdefault(item.name.casefold(), item)

        current_assignments = list(db.scalars(select(OperationResponsibleAssignment).order_by(OperationResponsibleAssignment.updated_at.desc())))
        assignments_by_person: dict[str, list[OperationResponsibleAssignment]] = {}
        for item in current_assignments:
            assignments_by_person.setdefault(_responsible_identity(item.responsible_name), []).append(item)
        imported_members = 0
        for incoming in payload.team_members:
            responsible_name = _normalize_responsible_name(incoming.responsible_name)
            identity = _responsible_identity(responsible_name)
            model = None
            if incoming.team_model_name:
                model = models_by_name.get(_normalize_team_model_name(incoming.team_model_name).casefold())
                if model is None:
                    raise HTTPException(status_code=422, detail=f"Modelo de equipe '{incoming.team_model_name}' não encontrado no arquivo ou no sistema.")
            duplicates = assignments_by_person.get(identity, [])
            item = duplicates[0] if duplicates else OperationResponsibleAssignment(
                responsible_name=responsible_name,
                regional=(incoming.regional or "Não identificada").strip() or "Não identificada",
            )
            if not duplicates:
                db.add(item)
                db.flush()
            item.responsible_name = responsible_name
            if incoming.regional:
                item.regional = incoming.regional.strip() or item.regional
            item.team_model_id = model.id if model else None
            item.updated_by = user.id
            item.updated_at = datetime.now(timezone.utc)
            for duplicate in duplicates[1:]:
                db.delete(duplicate)
            assignments_by_person[identity] = [item]
            imported_members += 1

        imported_subjects = 0
        if payload.subject_mappings:
            existing_subjects = {
                item.subject.casefold(): item
                for item in db.scalars(select(OperationSubjectTypeMapping))
            }
            for incoming in payload.subject_mappings:
                subject = " ".join(incoming.subject.strip().split())
                os_type = " ".join(incoming.os_type.strip().split())
                item = existing_subjects.get(subject.casefold())
                if item is None:
                    item = OperationSubjectTypeMapping(subject=subject, os_type=os_type, active=incoming.active, updated_by=user.id)
                    db.add(item)
                else:
                    item.subject, item.os_type, item.active, item.updated_by = subject, os_type, incoming.active, user.id
                db.execute(update(OperationOrder).where(OperationOrder.os_subject == subject).values(os_type=os_type))
                imported_subjects += 1

        imported_filters = 0
        for incoming in payload.saved_filters:
            name = incoming.name.strip()
            visibility = incoming.visibility
            existing = db.scalar(
                select(OperationSavedFilter).where(
                    OperationSavedFilter.user_id == user.id,
                    OperationSavedFilter.visibility == visibility,
                    func.lower(OperationSavedFilter.name) == name.casefold(),
                )
            )
            if existing is None:
                existing = OperationSavedFilter(user_id=user.id, name=name, visibility=visibility)
                db.add(existing)
            existing.filters = incoming.filters.model_dump(mode="json")
            existing.updated_at = datetime.now(timezone.utc)
            imported_filters += 1

        record_audit_log(db, user, "import", "operations_configuration_json", None, None, {
            "team_models": imported_models,
            "team_members": imported_members,
            "subject_mappings": imported_subjects,
            "saved_filters": imported_filters,
        })
        db.commit()
        return {
            "team_models": imported_models,
            "team_members": imported_members,
            "subject_mappings": imported_subjects,
            "saved_filters": imported_filters,
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Falha ao importar configuração JSON da Operação")
        raise HTTPException(status_code=422, detail="Arquivo de configuração inválido ou incompatível.") from exc


@router.post("/team-models", response_model=OperationTeamModelOut, status_code=201)
def create_team_model(
    payload: OperationTeamModelCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("operations:manage_team_models")),
):
    values = payload.model_dump()
    target_rules = values.pop("target_rules", [])
    values["name"] = _normalize_team_model_name(values["name"])
    _validate_team_thresholds(values)
    duplicate = db.scalar(select(OperationTeamModel.id).where(func.lower(OperationTeamModel.name) == values["name"].casefold()))
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="Já existe um modelo de equipe com esse nome.")
    item = OperationTeamModel(**values, created_by=user.id)
    _replace_target_rules(db, item, target_rules)
    db.add(item)
    db.flush()
    record_audit_log(db, user, "create", "operations_team_models", item.id, None, snapshot(item))
    db.commit()
    db.refresh(item)
    return item


@router.patch("/team-models/{model_id}", response_model=OperationTeamModelOut)
def update_team_model(
    model_id: int,
    payload: OperationTeamModelUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("operations:manage_team_models")),
):
    item = _team_model_or_404(db, model_id)
    before = snapshot(item)
    changes = payload.model_dump(exclude_unset=True)
    target_rules = changes.pop("target_rules", None)
    if "name" in changes:
        changes["name"] = _normalize_team_model_name(changes["name"])
        duplicate = db.scalar(
            select(OperationTeamModel.id).where(
                func.lower(OperationTeamModel.name) == changes["name"].casefold(),
                OperationTeamModel.id != item.id,
            )
        )
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="Já existe um modelo de equipe com esse nome.")
    proposed = {column: getattr(item, column) for column in ("median_from_quantity", "good_from_quantity", "daily_target")}
    proposed.update(changes)
    _validate_team_thresholds(proposed)
    for field, value in changes.items():
        setattr(item, field, value)
    if target_rules is not None:
        _replace_target_rules(db, item, target_rules)
    item.updated_at = datetime.now(timezone.utc)
    record_audit_log(db, user, "update", "operations_team_models", item.id, before, snapshot(item))
    db.commit()
    db.refresh(item)
    return item


@router.get("/subject-type-mappings", response_model=list[OperationSubjectTypeMappingOut], dependencies=[Depends(require_permission("operations:manage_subjects"))])
def list_subject_type_mappings(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return queries.subject_type_mappings(db, user)


@router.put("/subject-type-mappings", response_model=list[OperationSubjectTypeMappingOut])
def update_subject_type_mappings(
    payload: OperationSubjectTypeBulkUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("operations:manage_subjects")),
):
    os_type = " ".join(payload.os_type.strip().split())
    subjects = sorted({" ".join(subject.strip().split()) for subject in payload.subjects if subject.strip()})
    if not os_type or not subjects:
        raise HTTPException(status_code=422, detail="Informe o tipo geral e ao menos um assunto.")
    existing = {
        item.subject: item
        for item in db.scalars(select(OperationSubjectTypeMapping).where(OperationSubjectTypeMapping.subject.in_(subjects)))
    }
    for subject in subjects:
        item = existing.get(subject)
        before = snapshot(item) if item else None
        if item is None:
            item = OperationSubjectTypeMapping(subject=subject, os_type=os_type, updated_by=user.id)
            db.add(item)
            db.flush()
        else:
            item.os_type = os_type
            item.active = True
            item.updated_by = user.id
            item.updated_at = datetime.now(timezone.utc)
        record_audit_log(db, user, "update", "operations_subject_type_mappings", item.id, before, snapshot(item))
    db.execute(
        update(OperationOrder)
        .where(OperationOrder.os_subject.in_(subjects))
        .values(os_type=os_type, last_imported_at=datetime.now(timezone.utc))
    )
    db.commit()
    return queries.subject_type_mappings(db, user)


@router.delete("/team-models/{model_id}", status_code=204)
def delete_team_model(
    model_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("operations:manage_team_models")),
):
    item = _team_model_or_404(db, model_id)
    linked_members = int(
        db.scalar(
            select(func.count(OperationResponsibleAssignment.id)).where(
                OperationResponsibleAssignment.team_model_id == item.id
            )
        )
        or 0
    )
    if linked_members:
        raise HTTPException(
            status_code=409,
            detail=f"Este modelo está vinculado a {linked_members} colaborador(es). Remova ou transfira os vínculos antes de excluir.",
        )
    before = snapshot(item)
    record_audit_log(db, user, "delete", "operations_team_models", item.id, before, None)
    db.delete(item)
    db.commit()


@router.put("/team-members", status_code=204)
def assign_team_member(
    payload: OperationResponsibleAssignmentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("operations:manage_team_models")),
):
    responsible_name = _normalize_responsible_name(payload.responsible_name)
    regional = payload.regional.strip()
    if payload.team_model_id is not None:
        model = _team_model_or_404(db, payload.team_model_id)
        if not model.active:
            raise HTTPException(status_code=422, detail="Selecione um modelo de equipe ativo.")
    matches = list(
        db.scalars(
            select(OperationResponsibleAssignment)
            .where(func.lower(OperationResponsibleAssignment.responsible_name) == responsible_name.casefold())
            .order_by(OperationResponsibleAssignment.updated_at.desc(), OperationResponsibleAssignment.id.asc())
        )
    )
    item = matches[0] if matches else None
    before = snapshot(item) if item else None
    if item is None:
        item = OperationResponsibleAssignment(responsible_name=responsible_name, regional=regional)
        db.add(item)
        db.flush()
    item.team_model_id = payload.team_model_id
    item.responsible_name = responsible_name
    # The model belongs to the collaborator, not to a branch. Regional remains
    # only as the last known origin for backwards-compatible records.
    item.regional = regional or item.regional
    item.updated_by = user.id
    item.updated_at = datetime.now(timezone.utc)
    for duplicate in matches[1:]:
        db.delete(duplicate)
    record_audit_log(db, user, "update", "operations_responsible_assignments", item.id, before, snapshot(item))
    db.commit()


@router.post("/saved-filters", response_model=OperationSavedFilterOut, status_code=201, dependencies=[Depends(require_permission("operations:manage_filters"))])
def create_saved_filter(
    payload: OperationSavedFilterCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    name = payload.name.strip()
    if payload.visibility == "global":
        _ensure_global_saved_filter_permission(user, "create")
    _ensure_unique_filter_name_scoped(db, user.id, name, payload.visibility)
    item = OperationSavedFilter(
        user_id=user.id,
        name=name,
        filters=payload.filters.model_dump(mode="json"),
        visibility=payload.visibility,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/saved-filters/{saved_filter_id}", response_model=OperationSavedFilterOut)
def update_saved_filter(
    saved_filter_id: int,
    payload: OperationSavedFilterUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = _saved_filter_or_404_scoped(db, saved_filter_id, user)
    if not _can_manage_saved_filter(user, item, "update"):
        raise HTTPException(status_code=403, detail="Seu perfil não permite atualizar esta visão.")
    next_visibility = payload.visibility or item.visibility
    if next_visibility == "global" and item.visibility != "global":
        _ensure_global_saved_filter_permission(user, "create")
    if item.visibility == "global":
        _ensure_global_saved_filter_permission(user, "update")
    if payload.name is not None:
        name = payload.name.strip()
        _ensure_unique_filter_name_scoped(db, user.id, name, next_visibility, exclude_id=item.id)
        item.name = name
    if payload.filters is not None:
        item.filters = payload.filters.model_dump(mode="json")
    if payload.visibility is not None:
        item.visibility = payload.visibility
    item.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/saved-filters/{saved_filter_id}", status_code=204)
def delete_saved_filter(
    saved_filter_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = _saved_filter_or_404_scoped(db, saved_filter_id, user)
    if not _can_manage_saved_filter(user, item, "delete"):
        raise HTTPException(status_code=403, detail="Seu perfil não permite excluir esta visão.")
    db.delete(item)
    db.commit()
