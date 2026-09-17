"""Backfill noturno de TMR HISTÓRICO (usuário pediu 2026-09-16: "implementa o
backfill de TMR histórico rodando de madrugada" - 45 mil de 55 mil atendimentos
ainda sem `tmr_all_responses_seconds`, cobertura cai a 0% antes de 2026-08-20).
Diferente do backfill de meses (`test_opa_backfill.py`): este reprocessa
atendimentos JÁ GRAVADOS, nunca busca página de atendimentos de novo - só
`client.list_messages` por atendimento pendente."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.modules.support.models import SupportOpaAttendance
from app.modules.support.opa_ingestion import (
    pending_tmr_backfill_count,
    run_tmr_history_backfill,
)
from app.services import opa_scheduler
from app.services.calculation import get_setting, upsert_setting
from tests.test_opa_ingestion import FakeOpaClient
from tests.test_opa_scheduler import SessionLocalStub


def _settings(**overrides):
    values = {"opa_api_base_url": "https://opa.local", "opa_api_token": "token"}
    values.update(overrides)
    return SimpleNamespace(**values)


def _closed_attendance(source_id: str, **overrides) -> SupportOpaAttendance:
    base = dict(
        source_id=source_id,
        opened_at=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
        closed_at=datetime(2026, 7, 1, 10, 30, tzinfo=timezone.utc),
        raw_payload={},
    )
    base.update(overrides)
    return SupportOpaAttendance(**base)


def test_pending_tmr_backfill_count_only_counts_closed_without_all_responses(db_session):
    db_session.add_all(
        [
            _closed_attendance("A-1"),
            _closed_attendance("A-2", tmr_all_responses_seconds=120),
            _closed_attendance("A-3", closed_at=None),
        ]
    )
    db_session.flush()

    assert pending_tmr_backfill_count(db_session) == 1


def test_run_tmr_history_backfill_fills_metrics_from_messages(db_session):
    db_session.add(_closed_attendance("A-1"))
    db_session.flush()

    messages = {
        "A-1": [
            {"id_user": "cliente-1", "data": "2026-07-01T10:00:00+00:00"},
            {"id_atend": "agente-1", "data": "2026-07-01T10:05:00+00:00"},
        ]
    }
    client = FakeOpaClient([], messages=messages)

    result = run_tmr_history_backfill(db_session, client, limit=10)

    assert result == {"processed": 1, "updated": 1, "failed": 0}
    db_session.expire_all()
    attendance = db_session.query(SupportOpaAttendance).filter_by(source_id="A-1").one()
    assert attendance.tmr_all_responses_seconds == 300
    assert attendance.tmr_backfill_attempted_at is not None


def test_run_tmr_history_backfill_marks_attempt_even_without_messages(db_session):
    db_session.add(_closed_attendance("A-1"))
    db_session.flush()

    client = FakeOpaClient([], messages={})

    result = run_tmr_history_backfill(db_session, client, limit=10)

    assert result == {"processed": 1, "updated": 0, "failed": 0}
    db_session.expire_all()
    attendance = db_session.query(SupportOpaAttendance).filter_by(source_id="A-1").one()
    assert attendance.tmr_all_responses_seconds is None
    assert attendance.tmr_backfill_attempted_at is not None


def test_run_tmr_history_backfill_respects_limit_and_prioritizes_never_attempted(db_session):
    db_session.add_all([_closed_attendance(f"A-{i}") for i in range(3)])
    db_session.flush()

    client = FakeOpaClient([], messages={})
    result = run_tmr_history_backfill(db_session, client, limit=2)

    assert result["processed"] == 2
    db_session.expire_all()
    attempted = [
        row.source_id
        for row in db_session.query(SupportOpaAttendance).filter(SupportOpaAttendance.tmr_backfill_attempted_at.isnot(None))
    ]
    assert len(attempted) == 2


def test_run_opa_tmr_backfill_once_is_disabled_by_default(db_session, monkeypatch):
    monkeypatch.setattr(opa_scheduler, "SessionLocal", SessionLocalStub(db_session))
    monkeypatch.setattr(opa_scheduler, "get_settings", lambda: _settings())
    monkeypatch.setattr(opa_scheduler, "get_opa_client", lambda: FakeOpaClient([]))

    assert opa_scheduler.run_opa_tmr_backfill_once() is None


def test_run_opa_tmr_backfill_once_respects_night_window(db_session, monkeypatch):
    monkeypatch.setattr(opa_scheduler, "SessionLocal", SessionLocalStub(db_session))
    monkeypatch.setattr(opa_scheduler, "get_settings", lambda: _settings())
    monkeypatch.setattr(opa_scheduler, "get_opa_client", lambda: FakeOpaClient([]))
    upsert_setting(db_session, opa_scheduler.SUPPORT_OPA_TMR_BACKFILL_ENABLED_KEY, "true")
    # Janela de 1h que ainda não chegou (começa daqui a 2h, termina daqui a 3h) -
    # nunca deve disparar agora. run_hour != run_until_hour, senão a janela é
    # tratada como "sempre aberta" (ver _tmr_backfill_window_open).
    now_local = datetime.now(opa_scheduler.SUPPORT_TIMEZONE)
    future_start = (now_local.hour + 2) % 24
    future_end = (now_local.hour + 3) % 24
    upsert_setting(db_session, opa_scheduler.SUPPORT_OPA_TMR_BACKFILL_RUN_HOUR_KEY, str(future_start))
    upsert_setting(db_session, opa_scheduler.SUPPORT_OPA_TMR_BACKFILL_RUN_UNTIL_HOUR_KEY, str(future_end))
    db_session.commit()

    assert opa_scheduler.run_opa_tmr_backfill_once() is None


def test_run_opa_tmr_backfill_once_processes_batch_and_tracks_daily_budget(db_session, monkeypatch):
    db_session.add_all([_closed_attendance(f"A-{i}") for i in range(3)])
    db_session.flush()

    fake_client = FakeOpaClient([], messages={})
    monkeypatch.setattr(opa_scheduler, "SessionLocal", SessionLocalStub(db_session))
    monkeypatch.setattr(opa_scheduler, "get_settings", lambda: _settings())
    monkeypatch.setattr(opa_scheduler, "get_opa_client", lambda: fake_client)
    upsert_setting(db_session, opa_scheduler.SUPPORT_OPA_TMR_BACKFILL_ENABLED_KEY, "true")
    # Janela cobrindo qualquer hora (run_hour == run_until_hour -> sempre aberta).
    upsert_setting(db_session, opa_scheduler.SUPPORT_OPA_TMR_BACKFILL_RUN_HOUR_KEY, "0")
    upsert_setting(db_session, opa_scheduler.SUPPORT_OPA_TMR_BACKFILL_RUN_UNTIL_HOUR_KEY, "0")
    upsert_setting(db_session, opa_scheduler.SUPPORT_OPA_TMR_BACKFILL_DAILY_LIMIT_KEY, "100")
    db_session.commit()

    result = opa_scheduler.run_opa_tmr_backfill_once(batch_size=2)

    assert result["processed"] == 2
    today_iso = datetime.now(opa_scheduler.SUPPORT_TIMEZONE).date().isoformat()
    assert get_setting(db_session, opa_scheduler.SUPPORT_OPA_TMR_BACKFILL_LAST_RUN_DATE_KEY, "") == today_iso
    assert get_setting(db_session, opa_scheduler.SUPPORT_OPA_TMR_BACKFILL_PROCESSED_TODAY_KEY, "") == "2"


def test_run_opa_tmr_backfill_once_stops_when_daily_budget_exhausted(db_session, monkeypatch):
    db_session.add(_closed_attendance("A-1"))
    db_session.flush()

    fake_client = FakeOpaClient([], messages={})
    monkeypatch.setattr(opa_scheduler, "SessionLocal", SessionLocalStub(db_session))
    monkeypatch.setattr(opa_scheduler, "get_settings", lambda: _settings())
    monkeypatch.setattr(opa_scheduler, "get_opa_client", lambda: fake_client)
    upsert_setting(db_session, opa_scheduler.SUPPORT_OPA_TMR_BACKFILL_ENABLED_KEY, "true")
    upsert_setting(db_session, opa_scheduler.SUPPORT_OPA_TMR_BACKFILL_RUN_HOUR_KEY, "0")
    upsert_setting(db_session, opa_scheduler.SUPPORT_OPA_TMR_BACKFILL_RUN_UNTIL_HOUR_KEY, "0")
    upsert_setting(db_session, opa_scheduler.SUPPORT_OPA_TMR_BACKFILL_DAILY_LIMIT_KEY, "100")
    today_iso = datetime.now(opa_scheduler.SUPPORT_TIMEZONE).date().isoformat()
    upsert_setting(db_session, opa_scheduler.SUPPORT_OPA_TMR_BACKFILL_LAST_RUN_DATE_KEY, today_iso)
    upsert_setting(db_session, opa_scheduler.SUPPORT_OPA_TMR_BACKFILL_PROCESSED_TODAY_KEY, "100")
    db_session.commit()

    assert opa_scheduler.run_opa_tmr_backfill_once() is None
