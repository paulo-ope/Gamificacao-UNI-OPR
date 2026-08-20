"""Lote E: endpoints REST (app/modules/intelligence/router.py).

Cobre o teste obrigatorio 10 (coverage/warnings persistidos e retornados pela API) e smoke tests
dos demais endpoints, usando o fixture `client` compartilhado (admin_user via ROLE_PERMISSIONS,
já cobre intelligence:read/intelligence:manage - ver core/security.py)."""
from __future__ import annotations

from datetime import datetime, timezone

from app.modules.intelligence.models import IntelligenceAlert


def _seed_alert(db_session, **overrides) -> IntelligenceAlert:
    now = datetime.now(timezone.utc)
    defaults = dict(
        kind="INCIDENT",
        alert_type="COLLECTIVE_OUTAGE",
        monitor_key="collective_outage",
        dedupe_key="collective_outage:test:-10.9:-61.9",
        regional="UNI - JI PARANA",
        severity="HIGH",
        title="Possível incidente coletivo",
        summary="5 logins offline concentrados",
        evidence_json={"cluster_size": 5},
        confidence=0.82,
        coverage_json={"coordinate_coverage_pct": 71.4, "regional_population": 812},
        warnings_json=[{"code": "PARTIAL_DIMENSION_COVERAGE", "dimension": "coordinates"}],
        status="NEW",
        first_detected_at=now,
        last_seen_at=now,
    )
    defaults.update(overrides)
    alert = IntelligenceAlert(**defaults)
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)
    return alert


def test_list_monitors_endpoint_returns_registry_with_meta(client):
    response = client.get("/api/intelligence/monitors")
    assert response.status_code == 200
    body = response.json()

    keys = {item["key"] for item in body["items"]}
    assert {"collective_outage", "sla_deterioration", "operational_pressure", "monitor_health"} <= keys
    assert "generated_at" in body["meta"]
    assert body["meta"]["applied_filters"] == {}


def test_alert_detail_returns_confidence_coverage_and_warnings(client, db_session):
    """Teste obrigatorio 10 - confidence/coverage/warnings persistidos no monitor precisam
    chegar intactos na resposta da API, não apenas ficar no banco."""
    alert = _seed_alert(db_session)

    response = client.get(f"/api/intelligence/alerts/{alert.id}")
    assert response.status_code == 200
    body = response.json()

    assert body["confidence"] == 0.82
    assert body["coverage"]["coordinate_coverage_pct"] == 71.4
    assert body["coverage"]["regional_population"] == 812
    assert body["warnings"][0]["code"] == "PARTIAL_DIMENSION_COVERAGE"
    assert body["events"] == []


def test_alerts_list_filters_by_severity_and_reports_applied_filters(client, db_session):
    _seed_alert(db_session, dedupe_key="a1", severity="HIGH")
    _seed_alert(db_session, dedupe_key="a2", severity="LOW")

    response = client.get("/api/intelligence/alerts", params={"severities": ["HIGH"]})
    assert response.status_code == 200
    body = response.json()

    assert body["total"] == 1
    assert body["items"][0]["severity"] == "HIGH"
    assert body["meta"]["applied_filters"]["severities"] == ["HIGH"]


def test_monitor_runs_endpoint_reports_unknown_monitor_key_as_ignored_filter(client):
    response = client.get("/api/intelligence/monitor-runs", params={"monitor_keys": ["nao_existe"]})
    assert response.status_code == 200
    body = response.json()

    assert body["total"] == 0
    ignored = body["meta"]["ignored_filters"]
    assert any(item["field"] == "monitor_keys" and item["reason"] == "NOT_SUPPORTED_BY_ENDPOINT" for item in ignored)


def test_dismiss_alert_endpoint_records_event(client, db_session):
    alert = _seed_alert(db_session)

    response = client.post(f"/api/intelligence/alerts/{alert.id}/dismiss", json={"reason": "falso positivo"})
    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "DISMISSED"
    event_types = [event["event_type"] for event in body["events"]]
    assert "DISMISSED" in event_types
    assert "STATUS_CHANGED" in event_types


def test_get_alert_not_found_returns_404(client):
    response = client.get("/api/intelligence/alerts/999999")
    assert response.status_code == 404
