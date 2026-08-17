"""Lote C: dedupe, lifecycle e auto-resolve de alertas (app/modules/intelligence/alerts.py).

Cobre os testes obrigatorios 4-7 do processo aprovado para a fundacao F0+F1 do UNI Intelligence:
4. mesmo incidente em dois ciclos -> 1 alerta, segundo ciclo atualiza, nao cria outro.
5. evento desaparece por menos de N ciclos -> permanece ativo.
6. evento desaparece por N ciclos -> RESOLVED.
7. evento volta depois de resolvido -> nova ocorrencia, nunca reabre o alerta antigo em silencio.
"""
from __future__ import annotations

from sqlalchemy import select

from app.modules.intelligence.alerts import sync_alerts_for_monitor
from app.modules.intelligence.models import IntelligenceAlert, IntelligenceAlertEvent
from app.modules.intelligence.types import MonitorDetection

DEDUPE_KEY = "collective_outage:UNI - JI PARANA:-10.947:-61.952"


def _detection(*, dedupe_key: str = DEDUPE_KEY, severity: str = "HIGH", confidence: float = 0.8) -> MonitorDetection:
    return MonitorDetection(
        dedupe_key=dedupe_key,
        kind="INCIDENT",
        alert_type="COLLECTIVE_OUTAGE",
        severity=severity,
        title="Possível incidente coletivo",
        summary="5 logins offline concentrados",
        regional="UNI - JI PARANA",
        confidence=confidence,
    )


def _all_alerts(db_session) -> list[IntelligenceAlert]:
    return list(db_session.scalars(select(IntelligenceAlert).order_by(IntelligenceAlert.id)))


def _events_for(db_session, alert_id: int) -> list[IntelligenceAlertEvent]:
    return list(db_session.scalars(select(IntelligenceAlertEvent).where(IntelligenceAlertEvent.alert_id == alert_id).order_by(IntelligenceAlertEvent.id)))


def test_same_incident_two_cycles_updates_not_duplicates(db_session):
    stats1 = sync_alerts_for_monitor(db_session, monitor_key="collective_outage", detections=[_detection()], resolve_after_misses=3)
    db_session.commit()
    assert stats1.created == 1
    assert stats1.updated == 0

    alerts = _all_alerts(db_session)
    assert len(alerts) == 1
    assert alerts[0].status == "NEW"

    stats2 = sync_alerts_for_monitor(db_session, monitor_key="collective_outage", detections=[_detection(confidence=0.93)], resolve_after_misses=3)
    db_session.commit()
    assert stats2.created == 0
    assert stats2.updated == 1

    alerts = _all_alerts(db_session)
    assert len(alerts) == 1, "segundo ciclo do MESMO incidente nao pode criar um segundo alerta"
    assert alerts[0].status == "CONFIRMED", "redeteccao persistente promove NEW -> CONFIRMED"
    assert alerts[0].confidence == 0.93

    events = _events_for(db_session, alerts[0].id)
    event_types = [event.event_type for event in events]
    assert event_types[0] == "DETECTED"
    assert "UPDATED" in event_types
    assert "STATUS_CHANGED" in event_types


def test_alert_stays_active_below_miss_threshold(db_session):
    sync_alerts_for_monitor(db_session, monitor_key="collective_outage", detections=[_detection()], resolve_after_misses=3)
    db_session.commit()

    # ciclo sem deteccao (o evento sumiu) - so 1 miss, limite configurado e 3
    sync_alerts_for_monitor(db_session, monitor_key="collective_outage", detections=[], resolve_after_misses=3)
    db_session.commit()

    alert = _all_alerts(db_session)[0]
    assert alert.status != "RESOLVED"
    assert alert.misses_count == 1


def test_alert_auto_resolves_after_miss_threshold(db_session):
    sync_alerts_for_monitor(db_session, monitor_key="collective_outage", detections=[_detection()], resolve_after_misses=2)
    db_session.commit()

    sync_alerts_for_monitor(db_session, monitor_key="collective_outage", detections=[], resolve_after_misses=2)
    db_session.commit()
    alert = _all_alerts(db_session)[0]
    assert alert.status != "RESOLVED", "1a falta consecutiva ainda nao atinge o limite de 2"
    assert alert.misses_count == 1

    sync_alerts_for_monitor(db_session, monitor_key="collective_outage", detections=[], resolve_after_misses=2)
    db_session.commit()
    db_session.refresh(alert)
    assert alert.status == "RESOLVED"
    assert alert.resolved_at is not None

    resolved_events = [e for e in _events_for(db_session, alert.id) if e.event_type == "RESOLVED"]
    assert len(resolved_events) == 1
    assert resolved_events[0].payload_json["reason"] == "auto_resolve"


def test_resolved_alert_recurrence_creates_new_occurrence(db_session):
    sync_alerts_for_monitor(db_session, monitor_key="collective_outage", detections=[_detection()], resolve_after_misses=1)
    db_session.commit()
    sync_alerts_for_monitor(db_session, monitor_key="collective_outage", detections=[], resolve_after_misses=1)
    db_session.commit()

    resolved_alert = _all_alerts(db_session)[0]
    assert resolved_alert.status == "RESOLVED"
    resolved_id = resolved_alert.id

    # a mesma dedupe_key volta a ser detectada depois de resolvida
    sync_alerts_for_monitor(db_session, monitor_key="collective_outage", detections=[_detection()], resolve_after_misses=1)
    db_session.commit()

    all_alerts = _all_alerts(db_session)
    assert len(all_alerts) == 2, "reincidencia deve criar uma linha nova, nunca reaproveitar a antiga"
    assert all_alerts[0].id == resolved_id
    assert all_alerts[0].status == "RESOLVED", "o alerta antigo permanece intocado"
    assert all_alerts[1].status == "NEW", "a ocorrencia nova comeca do zero (NEW), nao herda estado"
    assert all_alerts[1].dedupe_key == all_alerts[0].dedupe_key
    assert all_alerts[1].id != resolved_id
