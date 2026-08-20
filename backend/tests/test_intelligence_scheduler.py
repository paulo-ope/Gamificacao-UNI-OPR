"""Lote B: scheduler asyncio e intelligence_monitor_runs (app/modules/intelligence/scheduler.py).

Cobre os testes obrigatorios 1-3 e 8 (parcial - saude via mark_interrupted) do processo aprovado:
1. scheduler executa monitor real.
2. run nasce RUNNING e termina COMPLETED.
3. falha controlada: run FAILED; scheduler continua (nao propaga excecao, proxima execucao funciona).
+ deteccao de run RUNNING orfa apos reinicio (mark_interrupted_runs_on_startup).

Mesmo padrao de app/tests/test_opa_scheduler.py: monkeypatch de SessionLocal por um stub que
sempre devolve a MESMA sessao de teste (in-memory sqlite), ja que execute_monitor_once abre
"varias sessoes" (create/execute/finish) que precisam enxergar o mesmo banco."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.modules.intelligence import scheduler
from app.modules.intelligence.models import IntelligenceMonitorRun
from app.modules.intelligence.registry import MonitorDefinition, get_monitor
from app.modules.intelligence.types import MonitorRunResult


class SessionLocalStub:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.fixture(autouse=True)
def _patch_session_local(monkeypatch, db_session):
    monkeypatch.setattr(scheduler, "SessionLocal", SessionLocalStub(db_session))


def _runs_for(db_session, monitor_key: str) -> list[IntelligenceMonitorRun]:
    return list(db_session.scalars(select(IntelligenceMonitorRun).where(IntelligenceMonitorRun.monitor_key == monitor_key)))


def test_scheduler_executes_real_monitor(db_session):
    """Teste obrigatorio 1 - roda um monitor REAL do registry (monitor_health, que não exige
    dado operacional semeado) através do caminho real do scheduler, não um double."""
    monitor = get_monitor("monitor_health")
    assert monitor is not None

    scheduler.execute_monitor_once(monitor)

    runs = _runs_for(db_session, "monitor_health")
    assert len(runs) == 1
    assert runs[0].status == "COMPLETED"
    assert runs[0].finished_at is not None
    assert runs[0].duration_ms is not None
    assert runs[0].result_count == 0  # sem monitor atrasado/falhando pra detectar


def test_run_starts_running_and_ends_completed(db_session):
    """Teste obrigatorio 2 - a run precisa estar RUNNING enquanto o monitor executa (não só
    "COMPLETED no final"), por isso o runner de teste lê o próprio status durante a execução."""
    observed = {}

    def probe_runner(db):
        run = db.scalar(select(IntelligenceMonitorRun).where(IntelligenceMonitorRun.monitor_key == "probe"))
        observed["mid_execution_status"] = run.status
        return MonitorRunResult(detections=[], stats={"probed": True})

    monitor = MonitorDefinition(
        key="probe", name="Probe", description="monitor de teste", default_interval_minutes=5,
        enabled_by_default=True, scope_strategy="global", resolve_after_misses=2, runner=probe_runner,
    )

    scheduler.execute_monitor_once(monitor)

    assert observed["mid_execution_status"] == "RUNNING"
    run = _runs_for(db_session, "probe")[0]
    assert run.status == "COMPLETED"
    assert run.stats_json == {"probed": True}


def test_monitor_failure_is_recorded_and_scheduler_continues(db_session):
    """Teste obrigatorio 3 - falha de um monitor vira run FAILED com o erro registrado, e NAO
    propaga excecao (o scheduler segue rodando outros monitores normalmente)."""

    def failing_runner(db):
        raise RuntimeError("falha proposital do monitor de teste")

    def working_runner(db):
        return MonitorRunResult(detections=[], stats={})

    failing_monitor = MonitorDefinition(
        key="failing", name="Failing", description="", default_interval_minutes=5,
        enabled_by_default=True, scope_strategy="global", resolve_after_misses=2, runner=failing_runner,
    )
    working_monitor = MonitorDefinition(
        key="working", name="Working", description="", default_interval_minutes=5,
        enabled_by_default=True, scope_strategy="global", resolve_after_misses=2, runner=working_runner,
    )

    scheduler.execute_monitor_once(failing_monitor)  # não deve levantar exceção para o chamador

    failing_run = _runs_for(db_session, "failing")[0]
    assert failing_run.status == "FAILED"
    assert failing_run.error is not None
    assert "falha proposital" in failing_run.error
    assert failing_run.finished_at is not None

    # o "scheduler continua": a próxima execução (de outro monitor) funciona normalmente
    scheduler.execute_monitor_once(working_monitor)
    working_run = _runs_for(db_session, "working")[0]
    assert working_run.status == "COMPLETED"


def test_mark_interrupted_runs_on_startup(db_session):
    """Uma run RUNNING encontrada na inicialização só pode ser de um processo anterior que caiu
    no meio - vira INTERRUPTED, nunca fica "rodando" para sempre."""
    stale = IntelligenceMonitorRun(
        monitor_key="collective_outage",
        status="RUNNING",
        started_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(stale)
    db_session.commit()

    count = scheduler.mark_interrupted_runs_on_startup(db_session)
    db_session.commit()

    assert count == 1
    db_session.refresh(stale)
    assert stale.status == "INTERRUPTED"
    assert stale.finished_at is not None
    assert stale.error is not None
    assert stale.duration_ms is not None and stale.duration_ms > 0


def test_mark_interrupted_ignores_completed_runs(db_session):
    finished = IntelligenceMonitorRun(
        monitor_key="collective_outage",
        status="COMPLETED",
        started_at=datetime.now(timezone.utc) - timedelta(hours=1),
        finished_at=datetime.now(timezone.utc) - timedelta(minutes=55),
    )
    db_session.add(finished)
    db_session.commit()

    count = scheduler.mark_interrupted_runs_on_startup(db_session)

    assert count == 0
    db_session.refresh(finished)
    assert finished.status == "COMPLETED"
