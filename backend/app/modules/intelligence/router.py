"""Endpoints do UNI Intelligence.

F0+F1: inspeção do motor (monitores, runs, alertas). F2: Cockpit API (payload único da TV) e
publicação genérica de conteúdo (`intelligence_cockpit_content`) - ver
docs/plano-plataforma-inteligencia-operacional.md.

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

from .alert_rules import (
    AlertRuleValidationError,
    build_alert_rule_catalog,
    alert_rule_to_out,
    create_alert_rule,
    get_alert_rule,
    list_alert_rules,
    update_alert_rule,
)
from .alerts import dismiss_alert
from .cockpit import (
    CockpitContentValidationError,
    ProfileValidationError,
    build_cockpit_payload,
    build_filter_catalog,
    create_profile,
    dismiss_cockpit_content,
    get_profile,
    list_cockpit_content,
    list_profiles,
    profile_to_admin_out,
    publish_cockpit_content,
    update_cockpit_content,
    update_profile,
)
from .models import IntelligenceAlert, IntelligenceAlertEvent, IntelligenceCockpitContent, IntelligenceMonitorRun
from .registry import get_monitor, list_monitors
from .scheduler import (
    count_consecutive_failures,
    get_monitor_enabled,
    get_monitor_interval_minutes,
    get_monitor_resolve_after_misses,
    last_success_run,
    recent_runs,
    update_monitor_settings,
)
from .schemas import (
    AdminAlertRuleCreateRequest,
    AdminAlertRuleOut,
    AdminAlertRuleUpdateRequest,
    AdminContentOut,
    AdminContentUpdateRequest,
    AdminMonitorUpdateRequest,
    AdminProfileCreateRequest,
    AdminProfileOut,
    AdminProfileUpdateRequest,
    AlertDetailOut,
    AlertDismissRequest,
    AlertEventOut,
    AlertOut,
    AlertPageOut,
    AlertRuleCatalogOut,
    CockpitContentOut,
    CockpitPayloadOut,
    FilterCatalogOut,
    IntelligenceResponseMetaOut,
    MonitorListOut,
    MonitorOut,
    MonitorRunOut,
    MonitorRunPageOut,
    PublishCockpitContentRequest,
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


# --- Cockpit (F2) --------------------------------------------------------------------------------


def _content_out(content) -> CockpitContentOut:
    return CockpitContentOut(
        id=content.id,
        content_type=content.content_type,
        profile_key=content.profile_key,
        regional=content.regional,
        severity=content.severity,
        title=content.title,
        body=content.body,
        evidence=content.evidence_json,
        confidence=content.confidence,
        source_type=content.source_type,
        source_key=content.source_key,
        author_user_id=content.author_user_id,
        valid_from=content.valid_from,
        valid_until=content.valid_until,
        created_at=content.created_at,
    )


@router.get("/cockpit/{profile_key}", response_model=CockpitPayloadOut)
def get_cockpit_payload(profile_key: str, db: Session = Depends(get_db)) -> CockpitPayloadOut:
    """Payload único da TV - tudo que o frontend precisa para renderizar o cockpit num só
    request. Monta no backend reaproveitando funções já existentes de operations/ai (ver
    cockpit.py); o frontend nunca chama dezenas de endpoints separados."""
    profile = get_profile(db, profile_key)
    if profile is None or not profile.active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Profile '{profile_key}' não encontrado.")
    payload = build_cockpit_payload(db, profile)
    return CockpitPayloadOut(**payload)


@router.post(
    "/cockpit-content",
    response_model=CockpitContentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("intelligence:publish"))],
)
def publish_cockpit_content_endpoint(
    body: PublishCockpitContentRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CockpitContentOut:
    """Porta de publicação REST - usa a MESMA função (`cockpit.publish_cockpit_content`) que a
    tool MCP `opr_publish_cockpit_content`, para nunca duplicar regra de validação. Origem
    sempre determinada pelo backend a partir de quem chamou (nunca aceita publisher arbitrário
    vindo do payload) - aqui é sempre `source_type="USER"` com `author_user_id` do usuário logado."""
    try:
        content = publish_cockpit_content(
            db,
            content_type=body.content_type,
            profile_key=body.profile_key,
            scope=body.scope,
            severity=body.severity,
            title=body.title,
            body=body.body,
            evidence=body.evidence,
            confidence=body.confidence,
            valid_until=body.valid_until,
            source_type="USER",
            source_key=None,
            author_user_id=user.id,
        )
    except CockpitContentValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _content_out(content)


# --- Administração (F5) --------------------------------------------------------------------------
# Toda rota abaixo exige intelligence:manage (além de intelligence:read, já exigido pelo router
# inteiro) - é a gestão de profiles/publicações/monitores, não a leitura pública da TV.

admin_router = APIRouter(dependencies=[Depends(require_permission("intelligence:manage"))])


def _admin_content_out(content: IntelligenceCockpitContent) -> AdminContentOut:
    base = _content_out(content)
    return AdminContentOut(**base.model_dump(), status=content.status)


# --- profiles --------------------------------------------------------------------------------


@admin_router.get("/admin/profiles", response_model=list[AdminProfileOut])
def list_profiles_endpoint(db: Session = Depends(get_db)) -> list[AdminProfileOut]:
    return [AdminProfileOut(**profile_to_admin_out(p)) for p in list_profiles(db)]


@admin_router.get("/admin/profiles/{profile_key}", response_model=AdminProfileOut)
def get_profile_admin_endpoint(profile_key: str, db: Session = Depends(get_db)) -> AdminProfileOut:
    profile = get_profile(db, profile_key)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Profile '{profile_key}' não encontrado.")
    return AdminProfileOut(**profile_to_admin_out(profile))


@admin_router.post("/admin/profiles", response_model=AdminProfileOut, status_code=status.HTTP_201_CREATED)
def create_profile_endpoint(body: AdminProfileCreateRequest, db: Session = Depends(get_db)) -> AdminProfileOut:
    try:
        profile = create_profile(
            db,
            key=body.key,
            name=body.name,
            purpose=body.purpose,
            scope=body.scope,
            widgets=[w.model_dump() for w in body.widgets],
            display_config=body.display_config,
            refresh_seconds=body.refresh_seconds,
            active=body.active,
        )
    except ProfileValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return AdminProfileOut(**profile_to_admin_out(profile))


@admin_router.put("/admin/profiles/{profile_key}", response_model=AdminProfileOut)
def update_profile_endpoint(profile_key: str, body: AdminProfileUpdateRequest, db: Session = Depends(get_db)) -> AdminProfileOut:
    profile = get_profile(db, profile_key)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Profile '{profile_key}' não encontrado.")
    try:
        profile = update_profile(
            db,
            profile,
            name=body.name,
            purpose=body.purpose,
            scope=body.scope,
            widgets=[w.model_dump() for w in body.widgets] if body.widgets is not None else None,
            display_config=body.display_config,
            refresh_seconds=body.refresh_seconds,
            active=body.active,
        )
    except ProfileValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return AdminProfileOut(**profile_to_admin_out(profile))


@admin_router.get("/admin/filter-catalog", response_model=FilterCatalogOut)
def get_filter_catalog_endpoint(db: Session = Depends(get_db)) -> FilterCatalogOut:
    return FilterCatalogOut(**build_filter_catalog(db))


# --- publicações -------------------------------------------------------------------------------


@admin_router.get("/admin/content", response_model=list[AdminContentOut])
def list_content_admin_endpoint(
    profile_key: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    content_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[AdminContentOut]:
    rows = list_cockpit_content(db, profile_key=profile_key, status=status_filter, content_type=content_type)
    return [_admin_content_out(row) for row in rows]


@admin_router.put("/admin/content/{content_id}", response_model=AdminContentOut)
def update_content_admin_endpoint(content_id: int, body: AdminContentUpdateRequest, db: Session = Depends(get_db)) -> AdminContentOut:
    content = db.get(IntelligenceCockpitContent, content_id)
    if content is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conteúdo não encontrado.")
    try:
        content = update_cockpit_content(db, content, title=body.title, body=body.body, severity=body.severity, valid_until=body.valid_until)
    except CockpitContentValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _admin_content_out(content)


@admin_router.post("/admin/content/{content_id}/dismiss", response_model=AdminContentOut)
def dismiss_content_admin_endpoint(content_id: int, db: Session = Depends(get_db)) -> AdminContentOut:
    content = db.get(IntelligenceCockpitContent, content_id)
    if content is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conteúdo não encontrado.")
    content = dismiss_cockpit_content(db, content)
    return _admin_content_out(content)


# --- monitores -----------------------------------------------------------------------------------


@admin_router.put("/admin/monitors/{monitor_key}", response_model=MonitorOut)
def update_monitor_admin_endpoint(monitor_key: str, body: AdminMonitorUpdateRequest, db: Session = Depends(get_db)) -> MonitorOut:
    monitor = get_monitor(monitor_key)
    if monitor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Monitor '{monitor_key}' não encontrado.")
    update_monitor_settings(db, monitor, enabled=body.enabled, interval_minutes=body.interval_minutes, resolve_after_misses=body.resolve_after_misses)
    runs = recent_runs(db, monitor.key, limit=20)
    last_run = runs[0] if runs else None
    success_run = last_success_run(db, monitor.key)
    return MonitorOut(
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


# --- regras de alertas (parametrizáveis) ---------------------------------------------------------


@admin_router.get("/admin/alert-rules", response_model=list[AdminAlertRuleOut])
def list_alert_rules_endpoint(db: Session = Depends(get_db)) -> list[AdminAlertRuleOut]:
    return [AdminAlertRuleOut(**alert_rule_to_out(rule)) for rule in list_alert_rules(db)]


@admin_router.get("/admin/alert-rules/catalog", response_model=AlertRuleCatalogOut)
def get_alert_rule_catalog_endpoint() -> AlertRuleCatalogOut:
    return AlertRuleCatalogOut(**build_alert_rule_catalog())


@admin_router.post("/admin/alert-rules", response_model=AdminAlertRuleOut, status_code=status.HTTP_201_CREATED)
def create_alert_rule_endpoint(body: AdminAlertRuleCreateRequest, db: Session = Depends(get_db)) -> AdminAlertRuleOut:
    try:
        rule = create_alert_rule(
            db,
            key=body.key,
            name=body.name,
            rule_type=body.rule_type,
            scope=body.scope,
            params=body.params,
            severity=body.severity,
            active=body.active,
            cooldown_minutes=body.cooldown_minutes,
            confirm_cycles=body.confirm_cycles,
            resolve_cycles=body.resolve_cycles,
        )
    except AlertRuleValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return AdminAlertRuleOut(**alert_rule_to_out(rule))


@admin_router.put("/admin/alert-rules/{rule_key}", response_model=AdminAlertRuleOut)
def update_alert_rule_endpoint(rule_key: str, body: AdminAlertRuleUpdateRequest, db: Session = Depends(get_db)) -> AdminAlertRuleOut:
    rule = get_alert_rule(db, rule_key)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Regra '{rule_key}' não encontrada.")
    try:
        rule = update_alert_rule(
            db,
            rule,
            name=body.name,
            active=body.active,
            scope=body.scope,
            params=body.params,
            severity=body.severity,
            cooldown_minutes=body.cooldown_minutes,
            confirm_cycles=body.confirm_cycles,
            resolve_cycles=body.resolve_cycles,
        )
    except AlertRuleValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return AdminAlertRuleOut(**alert_rule_to_out(rule))


router.include_router(admin_router)
