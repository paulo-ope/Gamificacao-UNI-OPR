"""Schemas de resposta do módulo intelligence. Nasce 100% no FilterContractV1 (nomes canônicos,
plural/snake_case para filtros de igualdade, envelope `meta` com applied_filters/ignored_filters/
warnings/source_last_sync em toda listagem) - decisão explícita aprovada antes desta
implementação: nenhum vocabulário novo paralelo ao REST legado."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class IntelligenceIgnoredFilterOut(BaseModel):
    field: str
    reason: str
    detail: str | None = None


class IntelligenceResponseMetaOut(BaseModel):
    applied_filters: dict
    ignored_filters: list[IntelligenceIgnoredFilterOut]
    warnings: list[dict]
    generated_at: datetime
    source_last_sync: datetime | None = None


class MonitorOut(BaseModel):
    key: str
    name: str
    description: str
    scope_strategy: str
    enabled: bool
    interval_minutes: int
    resolve_after_misses: int
    last_run_at: datetime | None = None
    last_run_status: str | None = None
    last_success_at: datetime | None = None
    consecutive_failures: int = 0


class MonitorListOut(BaseModel):
    items: list[MonitorOut]
    meta: IntelligenceResponseMetaOut


class MonitorRunOut(BaseModel):
    id: int
    monitor_key: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    result_count: int
    alerts_created: int
    alerts_updated: int
    alerts_resolved: int
    error: str | None
    stats: dict

    model_config = {"from_attributes": True}


class MonitorRunPageOut(BaseModel):
    items: list[MonitorRunOut]
    total: int
    page: int
    page_size: int
    meta: IntelligenceResponseMetaOut


class AlertEventOut(BaseModel):
    id: int
    event_type: str
    payload: dict
    created_at: datetime
    created_by: int | None

    model_config = {"from_attributes": True}


class AlertOut(BaseModel):
    id: int
    kind: str
    alert_type: str
    monitor_key: str
    dedupe_key: str
    regional: str | None
    city: str | None
    scope: dict
    severity: str
    title: str
    summary: str
    recommended_action: str | None
    evidence: dict
    confidence: float | None
    coverage: dict
    warnings: list[dict]
    source_last_sync: datetime | None
    status: str
    first_detected_at: datetime
    last_seen_at: datetime
    resolved_at: datetime | None
    acknowledged_by: int | None
    acknowledged_at: datetime | None
    misses_count: int
    source_type: str
    source_key: str | None
    created_at: datetime
    updated_at: datetime


class AlertDetailOut(AlertOut):
    events: list[AlertEventOut]


class AlertPageOut(BaseModel):
    items: list[AlertOut]
    total: int
    page: int
    page_size: int
    meta: IntelligenceResponseMetaOut


class AlertDismissRequest(BaseModel):
    reason: str | None = None


# --- Cockpit (F2) --------------------------------------------------------------------------------


class CockpitProfileOut(BaseModel):
    key: str
    name: str
    purpose: str
    widgets: list[str]
    refresh_seconds: int
    display_config: dict


class CockpitOverallStatusOut(BaseModel):
    status: str
    reason: str


class CockpitProductionOut(BaseModel):
    opened_today: int
    closed_today: int
    balance_today: int
    avg_opened_7d: float
    avg_closed_7d: float


class CockpitBacklogOut(BaseModel):
    total: int
    gt_3d: int
    gt_7d: int
    gt_15d: int


class CockpitCriticalRegionalOut(BaseModel):
    regional: str
    sla_rate: float


class CockpitSlaOut(BaseModel):
    current: float | None
    target: float
    critical_regionals: list[CockpitCriticalRegionalOut]


class CockpitAlertSummaryOut(BaseModel):
    id: int
    kind: str
    alert_type: str
    severity: str
    status: str
    title: str
    summary: str
    recommended_action: str | None
    regional: str | None
    confidence: float | None
    coverage: dict
    warnings: list[dict]
    first_detected_at: datetime
    last_seen_at: datetime
    age_seconds: int
    source_type: str


class CockpitContentOut(BaseModel):
    id: int
    content_type: str
    profile_key: str | None
    regional: str | None
    severity: str
    title: str
    body: str
    evidence: dict
    confidence: float | None
    source_type: str
    source_key: str | None
    author_user_id: int | None
    valid_from: datetime
    valid_until: datetime | None
    created_at: datetime


class CockpitMonitorHealthOut(BaseModel):
    monitor_key: str
    name: str
    enabled: bool
    last_run_at: datetime | None
    last_run_status: str | None
    last_success_at: datetime | None
    consecutive_failures: int


class CockpitDataFreshnessOut(BaseModel):
    last_successful_import_at: datetime | None
    status: str | None
    date_from: date | None
    date_to: date | None


class CockpitPayloadOut(BaseModel):
    profile: CockpitProfileOut
    generated_at: datetime
    overall_status: CockpitOverallStatusOut
    display_mode: str
    production: CockpitProductionOut
    backlog: CockpitBacklogOut
    sla: CockpitSlaOut
    alerts: list[CockpitAlertSummaryOut]
    incidents: list[CockpitAlertSummaryOut]
    content: list[CockpitContentOut]
    monitor_health: list[CockpitMonitorHealthOut]
    data_freshness: CockpitDataFreshnessOut
    meta: IntelligenceResponseMetaOut


class PublishCockpitContentRequest(BaseModel):
    content_type: str
    profile_key: str | None = None
    scope: dict = {}
    severity: str = "INFO"
    title: str
    body: str
    evidence: dict = {}
    confidence: float | None = None
    valid_until: datetime | None = None
