"""Schemas de resposta do módulo intelligence. Nasce 100% no FilterContractV1 (nomes canônicos,
plural/snake_case para filtros de igualdade, envelope `meta` com applied_filters/ignored_filters/
warnings/source_last_sync em toda listagem) - decisão explícita aprovada antes desta
implementação: nenhum vocabulário novo paralelo ao REST legado."""
from __future__ import annotations

from datetime import datetime

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
