"""Scheduler do UNI Intelligence - 6o loop asyncio do backend, no MESMO padrao ja usado pelos 5
existentes (IXC, OPA, backlog snapshot, login status snapshot, ONU signal snapshot - ver
app/services/opa_scheduler.py e app/main.py::lifespan). Sem Celery, sem Redis, sem broker novo,
sem WebSocket - decisao aprovada explicitamente antes desta implementacao.

Diferenca deliberada em relacao aos 5 loops existentes: em vez de UMA task por fonte de dado,
este e um UNICO loop que, a cada "tick", verifica cada monitor do registry (registry.py) e
executa os que estao no horario - assim, adicionar um monitor novo e so acrescentar uma entrada
no registry, sem criar mais uma task asyncio no lifespan.

Configuracao (enabled/interval/resolve_after_misses) fica em app_settings, lida a cada ciclo -
mesmo padrao de app/services/opa_scheduler.py: o .env/registry so fornecem o valor inicial, a
tela de Administracao muda em runtime sem reiniciar o backend."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.calculation import get_setting, upsert_setting

from .alerts import sync_alerts_for_monitor
from .models import IntelligenceMonitorRun
from .registry import MonitorDefinition, list_monitors

logger = logging.getLogger("intelligence_scheduler")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

# Sono fatiado (mesmo valor dos loops de IXC/OPA) - uma mudanca de intervalo/enabled feita pela
# tela de configuracao vale em segundos, sem precisar reiniciar o backend.
INTELLIGENCE_POLL_SECONDS = 15.0


def _setting_key(monitor_key: str, suffix: str) -> str:
    return f"intelligence_monitor_{monitor_key}_{suffix}"


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def get_monitor_enabled(db: Session, monitor: MonitorDefinition) -> bool:
    raw = get_setting(db, _setting_key(monitor.key, "enabled"), "")
    if not raw:
        return monitor.enabled_by_default
    return raw.strip().lower() in {"true", "1", "sim", "yes"}


def get_monitor_interval_minutes(db: Session, monitor: MonitorDefinition) -> int:
    raw = get_setting(db, _setting_key(monitor.key, "interval_minutes"), "")
    try:
        minutes = int(raw)
    except (TypeError, ValueError):
        return monitor.default_interval_minutes
    return min(max(minutes, 1), 1440)


def get_monitor_resolve_after_misses(db: Session, monitor: MonitorDefinition) -> int:
    raw = get_setting(db, _setting_key(monitor.key, "resolve_after_misses"), "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return monitor.resolve_after_misses
    return max(value, 1)


def get_monitor_next_allowed_at(db: Session, monitor_key: str) -> datetime | None:
    raw = get_setting(db, _setting_key(monitor_key, "next_allowed_at"), "")
    return _parse_timestamp(raw)


def _set_next_allowed_at(db: Session, monitor_key: str, when: datetime) -> None:
    upsert_setting(db, _setting_key(monitor_key, "next_allowed_at"), when.isoformat())


RECENT_RUNS_LOOKBACK = 20


def recent_runs(db: Session, monitor_key: str, limit: int = RECENT_RUNS_LOOKBACK) -> list[IntelligenceMonitorRun]:
    """Runs mais recentes de um monitor, mais nova primeiro - usado tanto pelo meta-monitor de
    saúde quanto pelo router (GET /monitors) para avaliar saúde sem duplicar a consulta."""
    return list(
        db.scalars(
            select(IntelligenceMonitorRun)
            .where(IntelligenceMonitorRun.monitor_key == monitor_key)
            .order_by(IntelligenceMonitorRun.started_at.desc())
            .limit(limit)
        )
    )


def count_consecutive_failures(runs: list[IntelligenceMonitorRun]) -> int:
    """Quantas das runs mais recentes (em ordem decrescente) falharam em sequência, parando na
    primeira que não falhou. `runs` deve já vir ordenado por started_at desc (ver recent_runs)."""
    count = 0
    for run in runs:
        if run.status in ("FAILED", "INTERRUPTED"):
            count += 1
        else:
            break
    return count


def last_success_run(db: Session, monitor_key: str) -> IntelligenceMonitorRun | None:
    return db.scalar(
        select(IntelligenceMonitorRun)
        .where(
            IntelligenceMonitorRun.monitor_key == monitor_key,
            IntelligenceMonitorRun.status.in_(("COMPLETED", "COMPLETED_WITH_WARNINGS")),
        )
        .order_by(IntelligenceMonitorRun.started_at.desc())
        .limit(1)
    )


def mark_interrupted_runs_on_startup(db: Session) -> int:
    """Ao subir o processo, qualquer run que ainda esta RUNNING so pode ser porque o processo
    anterior caiu no meio da execucao (nunca chegou ao ponto que finaliza a run). Marca como
    INTERRUPTED em vez de deixar uma run "fantasma" rodando para sempre - e exatamente o que
    permite distinguir "nao houve alerta" de "o monitor nao rodou" mesmo depois de um restart."""
    now = datetime.now(timezone.utc)
    stale_runs = list(db.scalars(select(IntelligenceMonitorRun).where(IntelligenceMonitorRun.status == "RUNNING")))
    for run in stale_runs:
        run.status = "INTERRUPTED"
        run.finished_at = now
        run.error = "Processo reiniciado com a run ainda RUNNING - marcada como interrompida na inicializacao."
        if run.started_at:
            started_at = run.started_at if run.started_at.tzinfo else run.started_at.replace(tzinfo=timezone.utc)
            run.duration_ms = max(round((now - started_at).total_seconds() * 1000), 0)
    db.commit()
    return len(stale_runs)


def _finish_run(
    run_id: int,
    *,
    status: str,
    started_mono: float,
    result_count: int | None = None,
    stats: dict | None = None,
    alerts_created: int | None = None,
    alerts_updated: int | None = None,
    alerts_resolved: int | None = None,
    error: str | None = None,
) -> None:
    with SessionLocal() as db:
        run = db.get(IntelligenceMonitorRun, run_id)
        if run is None:
            return
        run.status = status
        run.finished_at = datetime.now(timezone.utc)
        run.duration_ms = round((time.monotonic() - started_mono) * 1000)
        if result_count is not None:
            run.result_count = result_count
        if stats is not None:
            run.stats_json = stats
        if alerts_created is not None:
            run.alerts_created = alerts_created
        if alerts_updated is not None:
            run.alerts_updated = alerts_updated
        if alerts_resolved is not None:
            run.alerts_resolved = alerts_resolved
        if error is not None:
            run.error = error
        db.commit()


def execute_monitor_once(monitor: MonitorDefinition) -> None:
    """Executa um monitor uma vez: cria a run (RUNNING) antes de qualquer avaliacao de resultado,
    chama o runner do monitor, sincroniza os alertas (alerts.sync_alerts_for_monitor) e finaliza a
    run com o resultado - sempre, sucesso ou falha (o try/except cumpre o papel do "finally" do
    processo aprovado). Uma falha aqui NUNCA derruba o loop do scheduler (ver run_intelligence_scheduler_loop)."""

    with SessionLocal() as create_db:
        run = IntelligenceMonitorRun(monitor_key=monitor.key, status="RUNNING")
        create_db.add(run)
        create_db.commit()
        run_id = run.id

    started_mono = time.monotonic()
    try:
        with SessionLocal() as db:
            resolve_after_misses = get_monitor_resolve_after_misses(db, monitor)
            result = monitor.runner(db)
            sync_stats = sync_alerts_for_monitor(
                db,
                monitor_key=monitor.key,
                detections=result.detections,
                resolve_after_misses=resolve_after_misses,
            )
            db.commit()
        status = "COMPLETED"
        _finish_run(
            run_id,
            status=status,
            started_mono=started_mono,
            result_count=len(result.detections),
            stats=result.stats,
            alerts_created=sync_stats.created,
            alerts_updated=sync_stats.updated,
            alerts_resolved=sync_stats.resolved,
        )
    except Exception as exc:
        logger.exception("Monitor %s falhou", monitor.key)
        _finish_run(run_id, status="FAILED", started_mono=started_mono, error=str(exc)[:500])


async def run_intelligence_scheduler_loop() -> None:
    with SessionLocal() as db:
        interrupted = mark_interrupted_runs_on_startup(db)
        if interrupted:
            logger.warning("UNI Intelligence: %s run(s) marcada(s) como INTERRUPTED na inicializacao", interrupted)

    while True:
        due_monitors: list[MonitorDefinition] = []
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            for monitor in list_monitors():
                if not get_monitor_enabled(db, monitor):
                    continue
                next_allowed_at = get_monitor_next_allowed_at(db, monitor.key)
                if next_allowed_at is not None and next_allowed_at > now:
                    continue
                interval = get_monitor_interval_minutes(db, monitor)
                _set_next_allowed_at(db, monitor.key, now + timedelta(minutes=interval))
                due_monitors.append(monitor)
            db.commit()

        for monitor in due_monitors:
            await asyncio.to_thread(execute_monitor_once, monitor)

        await asyncio.sleep(INTELLIGENCE_POLL_SECONDS)
