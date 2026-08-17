"""Meta-monitor de saúde: resolve, de forma definitiva, a diferença entre "não houve alerta" e
"o monitor não rodou" (problema operacional já vivido antes desta plataforma). Olha para o
histórico real de `intelligence_monitor_runs` de cada OUTRO monitor - nunca para os próprios
alertas de negócio - e declara `MONITOR_UNHEALTHY` quando um monitor está atrasado além da
tolerância ou falhando repetidamente.

Import de `..scheduler` e `..registry` é adiado para dentro da função (não no topo do módulo)
porque `registry.py` importa este arquivo para registrar o runner - um import de `scheduler` no
topo aqui, que por sua vez importa `registry`, fecharia um ciclo de import a nível de módulo."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..types import MonitorDetection, MonitorRunResult

MONITOR_HEALTH_KEY = "monitor_health"
# Ciclos de atraso tolerados antes de considerar o monitor atrasado (não 1 - jitter do próprio
# scheduler, de até INTELLIGENCE_POLL_SECONDS, não pode virar falso positivo).
TOLERANCE_INTERVALS = 2
# Runs falhas consecutivas (mais recentes) até subir a severidade.
CONSECUTIVE_FAILURES_FOR_CRITICAL = 3


def run_monitor_health_monitor(db: Session) -> MonitorRunResult:
    from ..registry import list_monitors
    from ..scheduler import count_consecutive_failures, get_monitor_enabled, get_monitor_interval_minutes, recent_runs

    now = datetime.now(timezone.utc)
    detections: list[MonitorDetection] = []
    monitors_checked = 0
    monitors_unhealthy = 0

    for monitor in list_monitors():
        if monitor.key == MONITOR_HEALTH_KEY:
            continue  # não se autoavalia - evita um alerta sobre si mesmo sem sentido prático
        if not get_monitor_enabled(db, monitor):
            continue  # desligado deliberadamente não é "não saudável"

        monitors_checked += 1
        interval_minutes = get_monitor_interval_minutes(db, monitor)
        tolerance = timedelta(minutes=interval_minutes * TOLERANCE_INTERVALS)
        runs = recent_runs(db, monitor.key)
        last_run = runs[0] if runs else None
        consecutive_failures = count_consecutive_failures(runs)

        is_stale = False
        expected_next_at = None
        if last_run is None:
            # Nunca rodou - só é preocupante se o próprio meta-monitor já tem histórico (senão é
            # só o sistema recém-instalado, ainda dentro do primeiro ciclo).
            continue
        started_at = last_run.started_at if last_run.started_at.tzinfo else last_run.started_at.replace(tzinfo=timezone.utc)
        expected_next_at = started_at + timedelta(minutes=interval_minutes)
        is_stale = now > expected_next_at + tolerance

        if not is_stale and consecutive_failures == 0:
            continue

        monitors_unhealthy += 1
        severity = "MEDIUM"
        reasons = []
        if is_stale:
            reasons.append(f"última execução em {started_at.isoformat()}, esperada por volta de {expected_next_at.isoformat()}")
            severity = "HIGH"
        if consecutive_failures > 0:
            reasons.append(f"{consecutive_failures} execução(ões) consecutiva(s) sem sucesso")
            if consecutive_failures >= CONSECUTIVE_FAILURES_FOR_CRITICAL:
                severity = "CRITICAL"
            elif severity != "HIGH":
                severity = "MEDIUM"

        detections.append(
            MonitorDetection(
                dedupe_key=f"monitor_health:{monitor.key}",
                kind="ALERT",
                alert_type="MONITOR_UNHEALTHY",
                severity=severity,
                title=f"Monitor '{monitor.name}' não está saudável",
                summary=f"{monitor.name} ({monitor.key}): " + "; ".join(reasons) + ".",
                scope={"monitor_key": monitor.key},
                recommended_action="verificar logs do backend e o histórico de execuções deste monitor",
                evidence={
                    "monitor_key": monitor.key,
                    "last_run_status": last_run.status,
                    "last_run_started_at": started_at.isoformat(),
                    "expected_next_at": expected_next_at.isoformat() if expected_next_at else None,
                    "interval_minutes": interval_minutes,
                    "consecutive_failures": consecutive_failures,
                    "last_run_error": last_run.error,
                },
                confidence=0.9,
                coverage={},
                warnings=[],
                source_last_sync=None,
            )
        )

    return MonitorRunResult(
        detections=detections,
        stats={"monitors_checked": monitors_checked, "monitors_unhealthy": monitors_unhealthy},
    )
