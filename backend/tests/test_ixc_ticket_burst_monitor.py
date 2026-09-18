"""Item 9 do plano de evolução analítica do Atendimento IXC: escalonamento automático quando
bursts (BURST_V1, ver `ixc_ticket_baseline.py`) são detectados - integra no MESMO motor de
alertas/incidentes do UNI Intelligence (dedupe, lifecycle) já usado por SLA/pressão operacional/
incidente coletivo de rede."""

from __future__ import annotations

from datetime import datetime, timezone

from app.modules.intelligence.alerts import sync_alerts_for_monitor
from app.modules.intelligence.models import IntelligenceAlert
from app.modules.intelligence.monitors.ixc_ticket_burst import run_ixc_ticket_burst_monitor
from app.modules.support.models import SupportIxcHourlyBaseline, SupportIxcTicket

REGIONAL = "UNI - JI PARANA"


def _ticket(db, *, source_id, created_at, regional=REGIONAL):
    db.add(SupportIxcTicket(source_id=source_id, regional=regional, created_at=created_at))


def _baseline_row(db, *, scope_type, scope_id, weekday, hour, avg_count=1.0, stddev_count=0.0):
    db.add(
        SupportIxcHourlyBaseline(
            scope_type=scope_type, scope_id=scope_id, weekday=weekday, hour=hour,
            avg_count=avg_count, stddev_count=stddev_count, sample_weeks=4,
        )
    )


def test_ixc_ticket_burst_monitor_escalates_active_window_for_a_regional(db_session):
    reference_time = datetime(2026, 9, 15, 14, 30, tzinfo=timezone.utc)  # terça, 14h

    # Baseline baixo (avg=1, stddev=0) pros slots cobertos pelas janelas de 2h (13h/14h) e 6h
    # (9h-14h) - qualquer volume real bem acima disso deve estourar o limite superior.
    for hour in range(9, 15):
        _baseline_row(db_session, scope_type="regional", scope_id=REGIONAL, weekday=1, hour=hour)
    for i in range(20):
        _ticket(db_session, source_id=f"BURST{i}", created_at=datetime(2026, 9, 15, 14, 0, tzinfo=timezone.utc))
    db_session.commit()

    result = run_ixc_ticket_burst_monitor(db_session, reference_time=reference_time)

    regional_detections = {d.evidence["window"]: d for d in result.detections if d.regional == REGIONAL}
    assert set(regional_detections) == {"2h", "6h"}
    for detection in regional_detections.values():
        assert detection.alert_type == "IXC_TICKET_BURST"
        assert detection.kind == "ALERT"
        assert detection.evidence["observed"] == 20
        assert detection.severity in ("MEDIUM", "HIGH", "CRITICAL")
        assert detection.dedupe_key == f"ixc_ticket_burst:regional:{REGIONAL}:{detection.evidence['window']}"


def test_ixc_ticket_burst_monitor_skips_scope_without_computed_baseline(db_session):
    """Regional sem nenhum `SupportIxcHourlyBaseline` (job diário ainda não rodou pra ela) não
    pode virar alerta - `basis="none"` do BURST_V1 já cobre isso, o monitor só não deve
    escalonar nada em cima de um limiar inventado."""
    reference_time = datetime(2026, 9, 15, 14, 30, tzinfo=timezone.utc)
    for i in range(20):
        _ticket(db_session, source_id=f"NOBASE{i}", created_at=datetime(2026, 9, 15, 14, 0, tzinfo=timezone.utc), regional="UNI - OUTRA")
    db_session.commit()

    result = run_ixc_ticket_burst_monitor(db_session, reference_time=reference_time)

    assert not any(d.regional == "UNI - OUTRA" for d in result.detections)


def test_ixc_ticket_burst_monitor_detection_reaches_the_shared_alert_lifecycle(db_session):
    """Fim a fim: a detecção de burst precisa criar um `IntelligenceAlert` de verdade pelo MESMO
    motor de dedupe/lifecycle que SLA/pressão operacional/incidente coletivo já usam - é o que
    faz o burst aparecer escalonado no cockpit sem canal de notificação próprio."""
    reference_time = datetime(2026, 9, 15, 14, 30, tzinfo=timezone.utc)
    for hour in range(13, 15):
        _baseline_row(db_session, scope_type="regional", scope_id=REGIONAL, weekday=1, hour=hour)
    for i in range(20):
        _ticket(db_session, source_id=f"BURST{i}", created_at=datetime(2026, 9, 15, 14, 0, tzinfo=timezone.utc))
    db_session.commit()

    result = run_ixc_ticket_burst_monitor(db_session, reference_time=reference_time)
    stats = sync_alerts_for_monitor(db_session, monitor_key="ixc_ticket_burst", detections=result.detections, resolve_after_misses=2)
    db_session.commit()

    assert stats.created >= 1
    alert = db_session.query(IntelligenceAlert).filter_by(monitor_key="ixc_ticket_burst", regional=REGIONAL).first()
    assert alert is not None
    assert alert.status == "NEW"
    assert alert.alert_type == "IXC_TICKET_BURST"
