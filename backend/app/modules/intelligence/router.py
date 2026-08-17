"""Endpoints do UNI Intelligence - só o necessário para inspecionar/testar o motor nesta fase
(F0+F1). Sem Cockpit API, sem dashboard_profiles, sem frontend de TV - isso é escopo de F2+ (ver
docs/plano-plataforma-inteligencia-operacional.md).

Nasce 100% no FilterContractV1: filtros de igualdade em plural/snake_case, envelope `meta` com
applied_filters/ignored_filters/warnings/source_last_sync em toda listagem - sem herdar o
vocabulário do REST legado de `operations`."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_permission
from app.db.session import get_db
from app.models import User
from app.modules.ai_governance.response_meta import build_meta

from .alerts import dismiss_alert
from .models import IntelligenceAlert, IntelligenceAlertEvent, IntelligenceMonitorRun
from .registry import list_monitors
from .scheduler import (
    count_consecutive_failures,
    get_monitor_enabled,
    get_monitor_interval_minutes,
    get_monitor_resolve_after_misses,
    last_success_run,
    recent_runs,
)
from .schemas import (
    AlertDetailOut,
    AlertDismissRequest,
    AlertEventOut,
    AlertOut,
    AlertPageOut,
    IntelligenceResponseMetaOut,
    MonitorListOut,
    MonitorOut,
    MonitorRunOut,
    MonitorRunPageOut,
)

router = APIRouter(
    prefix="/intelligence",
    tags=["intelligence"],
    dependencies=[Depends(require_permission("intelligence:read"))],
)

MAX_PAGE_SIZE = 200


def _meta(applied_filters: dict, ignored_filters: list[dict] | None = None, warnings: list[dict] | None = None) -> IntelligenceResponseMetaOut:
    built = build_meta(applied_filters=applied_filters, ignored_filters=ignored_filters, warnings=warnings)
    return IntelligenceResponseMetaOut(**built)


def _alert_to_out(alert: IntelligenceAlert) -> AlertOut:
    return AlertOut(
        id=alert.id,
        kind=alert.kind,
        alert_type=alert.alert_type,
        monitor_key=alert.monitor_key,
        dedupe_key=alert.dedupe_key,
        regional=alert.regional,
        city=alert.city,
        scope=alert.scope_json,
        severity=alert.severity,
        title=alert.title,
        summary=alert.summary,
        recommended_action=alert.recommended_action,
        evidence=alert.evidence_json,
        confidence=alert.confidence,
        coverage=alert.coverage_json,
        warnings=alert.warnings_json,
        source_last_sync=alert.source_last_sync,
        status=alert.status,
        first_detected_at=alert.first_detected_at,
        last_seen_at=alert.last_seen_at,
        resolved_at=alert.resolved_at,
        acknowledged_by=alert.acknowledged_by,
        acknowledged_at=alert.acknowledged_at,
        misses_count=alert.misses_count,
        source_type=alert.source_type,
        source_key=alert.source_key,
        created_at=alert.created_at,
        updated_at=alert.updated_at,
    )


def _event_to_out(event: IntelligenceAlertEvent) -> AlertEventOut:
    return AlertEventOut(
        id=event.id,
        event_type=event.event_type,
        payload=event.payload_json,
        created_at=event.created_at,
        created_by=event.created_by,
    )


def _run_to_out(run: IntelligenceMonitorRun) -> MonitorRunOut:
    return MonitorRunOut(
        id=run.id,
        monitor_key=run.monitor_key,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        duration_ms=run.duration_ms,
        result_count=run.result_count,
        alerts_created=run.alerts_created,
        alerts_updated=run.alerts_updated,
        alerts_resolved=run.alerts_resolved,
        error=run.error,
        stats=run.stats_json,
    )


@router.get("/monitors", response_model=MonitorListOut)
def list_monitors_endpoint(db: Session = Depends(get_db)) -> MonitorListOut:
    """Estado efetivo de cada monitor: configuração atual (app_settings, com fallback pro
    default do registry) + última execução + última execução com sucesso + falhas consecutivas -
    o mesmo material que o meta-monitor de saúde usa, exposto para inspeção manual."""
    items: list[MonitorOut] = []
    for monitor in list_monitors():
        runs = recent_runs(db, monitor.key, limit=20)
        last_run = runs[0] if runs else None
        success_run = last_success_run(db, monitor.key)
        items.append(
            MonitorOut(
                key=monitor.key,
                name=monitor.name,
                description=monitor.description,
                scope_strategy=monitor.scope_strategy,
                enabled=get_monitor_enabled(db, monitor),
                interval_minutes=get_monitor_interval_minutes(db, monitor),
                resolve_after_misses=get_monitor_resolve_after_misses(db, monitor),
                last_run_at=last_run.started_at if last_run else None,
                last_run_status=last_run.status if last_run else None,
                last_success_at=success_run.started_at if success_run else None,
                consecutive_failures=count_consecutive_failures(runs),
            )
        )
    return MonitorListOut(items=items, meta=_meta(applied_filters={}))


@router.get("/monitor-runs", response_model=MonitorRunPageOut)
def list_monitor_runs_endpoint(
    monitor_keys: list[str] | None = Query(default=None),
    statuses: list[str] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
) -> MonitorRunPageOut:
    conditions = []
    ignored_filters: list[dict] = []
    known_keys = {monitor.key for monitor in list_monitors()}

    if monitor_keys:
        valid_keys = [key for key in monitor_keys if key in known_keys]
        invalid_keys = [key for key in monitor_keys if key not in known_keys]
        if invalid_keys:
            ignored_filters.append(
                {"field": "monitor_keys", "reason": "NOT_SUPPORTED_BY_ENDPOINT", "detail": f"chaves desconhecidas: {invalid_keys}"}
            )
        if valid_keys:
            conditions.append(IntelligenceMonitorRun.monitor_key.in_(valid_keys))

    if statuses:
        conditions.append(IntelligenceMonitorRun.status.in_(statuses))

    total = db.scalar(select(func.count(IntelligenceMonitorRun.id)).where(*conditions)) or 0
    rows = list(
        db.scalars(
            select(IntelligenceMonitorRun)
            .where(*conditions)
            .order_by(IntelligenceMonitorRun.started_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )

    applied_filters = {}
    if monitor_keys and any(key in known_keys for key in monitor_keys):
        applied_filters["monitor_keys"] = [key for key in monitor_keys if key in known_keys]
    if statuses:
        applied_filters["statuses"] = statuses

    return MonitorRunPageOut(
        items=[_run_to_out(run) for run in rows],
        total=total,
        page=page,
        page_size=page_size,
        meta=_meta(applied_filters=applied_filters, ignored_filters=ignored_filters),
    )


@router.get("/alerts", response_model=AlertPageOut)
def list_alerts_endpoint(
    statuses: list[str] | None = Query(default=None),
    severities: list[str] | None = Query(default=None),
    monitor_keys: list[str] | None = Query(default=None),
    regionals: list[str] | None = Query(default=None),
    kinds: list[str] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
) -> AlertPageOut:
    conditions = []
    applied_filters: dict = {}

    if statuses:
        conditions.append(IntelligenceAlert.status.in_(statuses))
        applied_filters["statuses"] = statuses
    if severities:
        conditions.append(IntelligenceAlert.severity.in_(severities))
        applied_filters["severities"] = severities
    if monitor_keys:
        conditions.append(IntelligenceAlert.monitor_key.in_(monitor_keys))
        applied_filters["monitor_keys"] = monitor_keys
    if regionals:
        conditions.append(IntelligenceAlert.regional.in_(regionals))
        applied_filters["regionals"] = regionals
    if kinds:
        conditions.append(IntelligenceAlert.kind.in_(kinds))
        applied_filters["kinds"] = kinds

    total = db.scalar(select(func.count(IntelligenceAlert.id)).where(*conditions)) or 0
    rows = list(
        db.scalars(
            select(IntelligenceAlert)
            .where(*conditions)
            .order_by(IntelligenceAlert.last_seen_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )

    return AlertPageOut(
        items=[_alert_to_out(alert) for alert in rows],
        total=total,
        page=page,
        page_size=page_size,
        meta=_meta(applied_filters=applied_filters),
    )


@router.get("/alerts/{alert_id}", response_model=AlertDetailOut)
def get_alert_endpoint(alert_id: int, db: Session = Depends(get_db)) -> AlertDetailOut:
    alert = db.get(IntelligenceAlert, alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alerta não encontrado.")
    base = _alert_to_out(alert)
    return AlertDetailOut(**base.model_dump(), events=[_event_to_out(event) for event in alert.events])


@router.post(
    "/alerts/{alert_id}/dismiss",
    response_model=AlertDetailOut,
    dependencies=[Depends(require_permission("intelligence:manage"))],
)
def dismiss_alert_endpoint(
    alert_id: int,
    body: AlertDismissRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AlertDetailOut:
    alert = db.get(IntelligenceAlert, alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alerta não encontrado.")
    dismiss_alert(db, alert, user_id=user.id, reason=body.reason)
    db.commit()
    db.refresh(alert)
    base = _alert_to_out(alert)
    return AlertDetailOut(**base.model_dump(), events=[_event_to_out(event) for event in alert.events])
