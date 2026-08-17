"""Motor de lifecycle e dedupe dos alertas/incidentes do UNI Intelligence.

Regra central (pedido explícito do usuário): o MESMO evento não pode nascer de novo a cada
execução. Cada monitor calcula uma `dedupe_key` estável (ver types.MonitorDetection); se já
existe um alerta ATIVO com essa chave, este módulo ATUALIZA (last_seen_at, evidence, severity,
confidence, coverage, warnings) em vez de criar, e registra um evento UPDATED (mais
SEVERITY_CHANGED se a severidade mudou). Se não existir, cria um alerta NEW e um evento DETECTED.

Lifecycle mínimo desta fase (NEW -> CONFIRMED -> RESOLVED/DISMISSED, ver docstring de
IntelligenceAlert.status): um alerta NEW que é redetectado no ciclo seguinte vira CONFIRMED - a
mesma ocorrência persistindo já é evidência de que não foi um pico isolado. Os demais valores do
enum (INVESTIGATING, IN_PROGRESS, RECOVERING, EXPIRED) ficam reservados para quando IA e ação
humana entrarem no motor (F2+).

Auto-resolve é deliberadamente conservador: um alerta ativo do monitor que NÃO foi redetectado
neste ciclo tem seu misses_count incrementado; só vira RESOLVED ao atingir `resolve_after_misses`
ciclos consecutivos sem detecção (configurável por monitor - ver registry.py/scheduler.py, nunca
hardcoded num único lugar). Um alerta já RESOLVED/DISMISSED cuja dedupe_key volta a ser detectada
gera uma OCORRÊNCIA NOVA (outra linha), nunca reaproveita silenciosamente o alerta antigo - por
isso a dedupe é restrita aos alertas ativos (ver models.py: dedupe_key não é unique na coluna)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import IntelligenceAlert, IntelligenceAlertEvent
from .types import MonitorDetection

# Estados em que um alerta ainda está "vivo" para efeito de dedupe/auto-resolve. RESOLVED,
# DISMISSED e EXPIRED são terminais - uma dedupe_key nesses estados não bloqueia nem é atualizada
# por uma nova detecção (ver módulo docstring: reincidência cria linha nova).
ACTIVE_STATUSES = ("NEW", "INVESTIGATING", "CONFIRMED", "IN_PROGRESS", "RECOVERING")
TERMINAL_STATUSES = ("RESOLVED", "DISMISSED", "EXPIRED")


@dataclass
class AlertSyncStats:
    created: int = 0
    updated: int = 0
    resolved: int = 0


def _record_event(db: Session, alert: IntelligenceAlert, event_type: str, payload: dict, *, created_by: int | None = None) -> None:
    db.add(IntelligenceAlertEvent(alert_id=alert.id, event_type=event_type, payload_json=payload, created_by=created_by))


def _active_alerts_for_monitor(db: Session, monitor_key: str) -> list[IntelligenceAlert]:
    return list(
        db.scalars(
            select(IntelligenceAlert).where(
                IntelligenceAlert.monitor_key == monitor_key,
                IntelligenceAlert.status.in_(ACTIVE_STATUSES),
            )
        )
    )


def _create_alert(
    db: Session,
    *,
    monitor_key: str,
    detection: MonitorDetection,
    source_type: str,
    source_key: str | None,
    now: datetime,
) -> IntelligenceAlert:
    alert = IntelligenceAlert(
        kind=detection.kind,
        alert_type=detection.alert_type,
        monitor_key=monitor_key,
        dedupe_key=detection.dedupe_key,
        regional=detection.regional,
        city=detection.city,
        scope_json=detection.scope,
        severity=detection.severity,
        title=detection.title,
        summary=detection.summary,
        recommended_action=detection.recommended_action,
        evidence_json=detection.evidence,
        confidence=detection.confidence,
        coverage_json=detection.coverage,
        warnings_json=detection.warnings,
        source_last_sync=detection.source_last_sync,
        status="NEW",
        first_detected_at=now,
        last_seen_at=now,
        misses_count=0,
        source_type=source_type,
        source_key=source_key,
    )
    db.add(alert)
    db.flush()
    _record_event(
        db,
        alert,
        "DETECTED",
        {"severity": detection.severity, "confidence": detection.confidence, "title": detection.title},
    )
    return alert


def _update_alert(db: Session, existing: IntelligenceAlert, detection: MonitorDetection, now: datetime) -> None:
    severity_changed = existing.severity != detection.severity
    previous_severity = existing.severity
    previous_status = existing.status

    existing.title = detection.title
    existing.summary = detection.summary
    existing.recommended_action = detection.recommended_action
    existing.evidence_json = detection.evidence
    existing.severity = detection.severity
    existing.confidence = detection.confidence
    existing.coverage_json = detection.coverage
    existing.warnings_json = detection.warnings
    existing.source_last_sync = detection.source_last_sync
    existing.scope_json = detection.scope
    existing.regional = detection.regional
    existing.city = detection.city
    existing.last_seen_at = now
    existing.misses_count = 0

    # Redetecção persistente é evidência de que não foi um pico isolado - promove NEW -> CONFIRMED
    # na segunda detecção em diante. Único avanço de estado automático que os monitores exigem
    # nesta fase (ver docstring do módulo).
    if existing.status == "NEW":
        existing.status = "CONFIRMED"

    _record_event(db, existing, "UPDATED", {"severity": detection.severity, "confidence": detection.confidence})
    if severity_changed:
        _record_event(db, existing, "SEVERITY_CHANGED", {"from": previous_severity, "to": detection.severity})
    if existing.status != previous_status:
        _record_event(db, existing, "STATUS_CHANGED", {"from": previous_status, "to": existing.status})


def sync_alerts_for_monitor(
    db: Session,
    *,
    monitor_key: str,
    detections: list[MonitorDetection],
    resolve_after_misses: int,
    source_type: str = "MONITOR",
    source_key: str | None = None,
) -> AlertSyncStats:
    """Aplica as detecções de UM ciclo de execução de um monitor: cria/atualiza alertas por
    dedupe_key e resolve automaticamente os que pararam de ser detectados por
    `resolve_after_misses` ciclos seguidos.

    Precisa ser chamada com TODAS as detecções daquele ciclo de uma vez (não incrementalmente) -
    senão o cálculo de "quem sumiu deste ciclo" fica incorreto."""

    stats = AlertSyncStats()
    active_alerts = _active_alerts_for_monitor(db, monitor_key)
    existing_by_key = {alert.dedupe_key: alert for alert in active_alerts}
    detected_keys = {detection.dedupe_key for detection in detections}
    now = datetime.now(timezone.utc)

    for detection in detections:
        existing = existing_by_key.get(detection.dedupe_key)
        if existing is None:
            _create_alert(db, monitor_key=monitor_key, detection=detection, source_type=source_type, source_key=source_key, now=now)
            stats.created += 1
        else:
            _update_alert(db, existing, detection, now)
            stats.updated += 1

    for alert in active_alerts:
        if alert.dedupe_key in detected_keys:
            continue
        alert.misses_count += 1
        if alert.misses_count >= max(resolve_after_misses, 1):
            previous_status = alert.status
            alert.status = "RESOLVED"
            alert.resolved_at = now
            _record_event(db, alert, "RESOLVED", {"reason": "auto_resolve", "misses_count": alert.misses_count})
            _record_event(db, alert, "STATUS_CHANGED", {"from": previous_status, "to": "RESOLVED"})
            stats.resolved += 1

    db.flush()
    return stats


def acknowledge_alert(db: Session, alert: IntelligenceAlert, *, user_id: int) -> IntelligenceAlert:
    alert.acknowledged_by = user_id
    alert.acknowledged_at = datetime.now(timezone.utc)
    _record_event(db, alert, "ACKNOWLEDGED", {"user_id": user_id}, created_by=user_id)
    db.flush()
    return alert


def dismiss_alert(db: Session, alert: IntelligenceAlert, *, user_id: int, reason: str | None = None) -> IntelligenceAlert:
    previous_status = alert.status
    now = datetime.now(timezone.utc)
    alert.status = "DISMISSED"
    alert.resolved_at = now
    _record_event(db, alert, "DISMISSED", {"user_id": user_id, "reason": reason}, created_by=user_id)
    _record_event(db, alert, "STATUS_CHANGED", {"from": previous_status, "to": "DISMISSED"}, created_by=user_id)
    db.flush()
    return alert
