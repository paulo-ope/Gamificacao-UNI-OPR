"""Lote D: os quatro monitores contra as funcoes reais de operations (nenhum mock de
login_incident_analysis/control_tower/sla_breakdown/coordinate_quality_audit).

Cobre os testes obrigatorios 8, 9, 11 e 12 do processo aprovado:
8. monitor atrasado -> MONITOR_UNHEALTHY.
9. monitor volta -> alerta de saude resolvido.
11. timezone America/Porto_Velho corretamente interpretado.
12. validar dados reais: pelo menos uma execucao de cada monitor contra as funcoes reais.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.modules.intelligence.alerts import sync_alerts_for_monitor
from app.modules.intelligence.models import IntelligenceAlert, IntelligenceMonitorRun
from app.modules.intelligence.monitors import sla_deterioration as sla_deterioration_module
from app.modules.intelligence.monitors.collective_outage import run_collective_outage_monitor
from app.modules.intelligence.monitors.monitor_health import run_monitor_health_monitor
from app.modules.intelligence.monitors.operational_pressure import run_operational_pressure_monitor
from app.modules.intelligence.monitors.sla_deterioration import run_sla_deterioration_monitor
from app.modules.operations.models import OperationLoginCurrentStatus, OperationOrder
from app.modules.operations.period import OPERATIONS_TIMEZONE


def _make_login(db_session, login_id: int, *, lat: float, lng: float, regional: str = "UNI - JI PARANA", minutes_ago: int = 10) -> None:
    db_session.add(
        OperationLoginCurrentStatus(
            login_id=login_id,
            login=f"login{login_id}",
            online="N",
            regional=regional,
            latitude=lat,
            longitude=lng,
            status_changed_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
            captured_at=datetime.now(timezone.utc),
        )
    )


def _make_order(db_session, source_order_id: str, *, regional: str, sla_status: str, closed_at: datetime) -> None:
    db_session.add(
        OperationOrder(
            source="ixc",
            source_order_id=source_order_id,
            order_code=source_order_id,
            regional=regional,
            os_type="Manutencao",
            os_subject="Reparo",
            sla_status=sla_status,
            is_closed=True,
            opened_at=closed_at - timedelta(hours=2),
            closed_at=closed_at,
            elapsed_hours=2.0,
        )
    )


def _utc_noon(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=12)


# --- teste 11: timezone -----------------------------------------------------------------------


def test_operations_timezone_is_porto_velho():
    assert OPERATIONS_TIMEZONE.key == "America/Porto_Velho"


def test_sla_deterioration_windows_use_calendar_days_correctly():
    reference = date(2026, 8, 16)
    (recent_from, recent_to), (baseline_from, baseline_to) = sla_deterioration_module._windows(reference)

    assert recent_to == reference
    assert recent_from == reference - timedelta(days=sla_deterioration_module.RECENT_WINDOW_DAYS - 1)
    assert baseline_to == recent_from - timedelta(days=1)
    assert baseline_from == baseline_to - timedelta(days=sla_deterioration_module.BASELINE_WINDOW_DAYS - 1)
    # janelas nao podem se sobrepor
    assert baseline_to < recent_from


# --- teste 12: cada monitor contra a funcao real ----------------------------------------------


def test_collective_outage_monitor_against_real_login_incident_analysis(db_session):
    for i in range(5):
        _make_login(db_session, 5000 + i, lat=-10.9472 + i * 0.0004, lng=-61.9528 + i * 0.0004)
    db_session.commit()

    result = run_collective_outage_monitor(db_session)

    assert result.stats["clusters_evaluated"] >= 1
    matches = [d for d in result.detections if d.alert_type == "COLLECTIVE_OUTAGE"]
    assert matches, "5 logins offline concentrados devem formar um cluster real"
    detection = matches[0]
    assert detection.kind == "INCIDENT"
    assert detection.regional == "UNI - JI PARANA"
    assert 0 < detection.confidence <= 0.97
    assert detection.evidence["cluster_size"] >= 3


def test_sla_deterioration_monitor_against_real_sla_breakdown(db_session):
    regional = "UNI - JI PARANA"
    reference = datetime.now(OPERATIONS_TIMEZONE).date()
    (recent_from, recent_to), (baseline_from, baseline_to) = sla_deterioration_module._windows(reference)

    counter = 0
    for _ in range(18):  # baseline: 90% (18 on_time / 2 out_of_time)
        counter += 1
        _make_order(db_session, f"BASE-{counter}", regional=regional, sla_status="on_time", closed_at=_utc_noon(baseline_from))
    for _ in range(2):
        counter += 1
        _make_order(db_session, f"BASE-{counter}", regional=regional, sla_status="out_of_time", closed_at=_utc_noon(baseline_from))
    for _ in range(2):  # recente: 20% (2 on_time / 8 out_of_time)
        counter += 1
        _make_order(db_session, f"RECENT-{counter}", regional=regional, sla_status="on_time", closed_at=_utc_noon(recent_to))
    for _ in range(8):
        counter += 1
        _make_order(db_session, f"RECENT-{counter}", regional=regional, sla_status="out_of_time", closed_at=_utc_noon(recent_to))
    db_session.commit()

    result = run_sla_deterioration_monitor(db_session)

    matches = [d for d in result.detections if d.regional == regional]
    assert matches, "queda de 90% para 20% de SLA deve ser detectada como deterioracao"
    detection = matches[0]
    assert detection.evidence["sla_baseline_pct"] > detection.evidence["sla_recent_pct"]
    assert detection.evidence["drop_percentage_points"] >= sla_deterioration_module.DETERIORATION_THRESHOLD_PP
    assert detection.severity in ("MEDIUM", "HIGH", "CRITICAL")


def test_sla_deterioration_monitor_skips_regional_with_insufficient_baseline(db_session):
    regional = "UNI - ARIQUEMES"
    reference = datetime.now(OPERATIONS_TIMEZONE).date()
    (_, recent_to), _ = sla_deterioration_module._windows(reference)
    # so 2 O.S. no total - abaixo do minimo de amostra do baseline (MIN_BASELINE_MEASURABLE)
    _make_order(db_session, "SPARSE-1", regional=regional, sla_status="out_of_time", closed_at=_utc_noon(recent_to))
    _make_order(db_session, "SPARSE-2", regional=regional, sla_status="on_time", closed_at=_utc_noon(recent_to))
    db_session.commit()

    result = run_sla_deterioration_monitor(db_session)

    assert not any(d.regional == regional for d in result.detections)
    assert result.stats["regionals_insufficient_data"] >= 1


def test_operational_pressure_monitor_against_real_control_tower(db_session):
    regional = "UNI - JI PARANA"
    today = datetime.now(OPERATIONS_TIMEZONE).date()
    for offset in range(7):
        _make_order(db_session, f"PRESSURE-{offset}", regional=regional, sla_status="on_time", closed_at=_utc_noon(today - timedelta(days=offset)))
    db_session.commit()

    result = run_operational_pressure_monitor(db_session)

    assert isinstance(result.stats["regionals_evaluated"], int)
    assert result.stats["regionals_evaluated"] >= 1
    # nao afirmamos que gera alerta (8 semanas de baseline exigem muito mais dado historico) -
    # o que este teste prova e que roda de ponta a ponta contra control_tower real sem excecao.
    for detection in result.detections:
        assert detection.alert_type == "OPERATIONAL_PRESSURE"
        assert detection.severity in ("MEDIUM", "HIGH", "CRITICAL")


def test_monitor_health_against_real_run_history_when_healthy(db_session):
    db_session.add(IntelligenceMonitorRun(monitor_key="sla_deterioration", status="COMPLETED", started_at=datetime.now(timezone.utc)))
    db_session.commit()

    result = run_monitor_health_monitor(db_session)

    assert result.stats["monitors_checked"] >= 1
    assert not any(d.evidence.get("monitor_key") == "sla_deterioration" for d in result.detections)


# --- testes 8 e 9: monitor atrasado vira alerta, depois se resolve -----------------------------


def test_monitor_health_detects_stale_monitor(db_session):
    """Teste obrigatorio 8 - um monitor cuja ultima run foi ha muito mais tempo que o dobro do
    intervalo configurado deve gerar MONITOR_UNHEALTHY."""
    stale_run = IntelligenceMonitorRun(
        monitor_key="sla_deterioration",
        status="COMPLETED",
        started_at=datetime.now(timezone.utc) - timedelta(hours=10),
        finished_at=datetime.now(timezone.utc) - timedelta(hours=10) + timedelta(seconds=5),
    )
    db_session.add(stale_run)
    db_session.commit()

    result = run_monitor_health_monitor(db_session)

    unhealthy = [d for d in result.detections if d.evidence.get("monitor_key") == "sla_deterioration"]
    assert unhealthy, "monitor com ultima execucao ha 10h (intervalo default 30min) deveria estar atrasado"
    detection = unhealthy[0]
    assert detection.alert_type == "MONITOR_UNHEALTHY"
    assert detection.dedupe_key == "monitor_health:sla_deterioration"


def test_monitor_health_resolves_when_monitor_recovers(db_session):
    """Teste obrigatorio 9 - depois que o alerta de saude foi criado, se o monitor voltar a
    rodar recentemente, o proximo ciclo do meta-monitor nao redeteta e o alerta e resolvido."""
    stale_run = IntelligenceMonitorRun(
        monitor_key="sla_deterioration",
        status="COMPLETED",
        started_at=datetime.now(timezone.utc) - timedelta(hours=10),
    )
    db_session.add(stale_run)
    db_session.commit()

    first_result = run_monitor_health_monitor(db_session)
    sync_alerts_for_monitor(db_session, monitor_key="monitor_health", detections=first_result.detections, resolve_after_misses=1)
    db_session.commit()

    alert = db_session.scalar(
        select(IntelligenceAlert).where(IntelligenceAlert.dedupe_key == "monitor_health:sla_deterioration")
    )
    assert alert is not None
    assert alert.status != "RESOLVED"

    # o monitor "volta": uma run recente e bem-sucedida
    db_session.add(IntelligenceMonitorRun(monitor_key="sla_deterioration", status="COMPLETED", started_at=datetime.now(timezone.utc)))
    db_session.commit()

    second_result = run_monitor_health_monitor(db_session)
    assert not any(d.evidence.get("monitor_key") == "sla_deterioration" for d in second_result.detections)

    sync_alerts_for_monitor(db_session, monitor_key="monitor_health", detections=second_result.detections, resolve_after_misses=1)
    db_session.commit()
    db_session.refresh(alert)

    assert alert.status == "RESOLVED"
    assert alert.resolved_at is not None
