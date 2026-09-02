from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import select

from app.models import AppSetting
from app.modules.scheduling import scheduler as scheduling_scheduler


class SessionLocalStub:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, tb):
        return False


def _settings(**overrides):
    values = {
        "ixc_api_base_url": "https://ixc.local",
        "ixc_api_token": "token",
        "scheduling_sync_interval_minutes": 20,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _setting_value(db_session, key: str) -> str | None:
    setting = db_session.scalar(select(AppSetting).where(AppSetting.key == key))
    return setting.value if setting else None


def test_scheduling_sync_does_nothing_without_ixc_config(monkeypatch):
    monkeypatch.setattr(
        scheduling_scheduler, "get_settings", lambda: _settings(ixc_api_base_url="", ixc_api_token="")
    )

    assert scheduling_scheduler.run_scheduling_sync_once() is None


def test_scheduling_sync_records_controlled_error_when_watermark_missing(monkeypatch, db_session):
    def fail_run_sync(db, client, *, date_from=None, date_to=None):
        raise RuntimeError("Sem marca d'água - rode um backfill com intervalo de datas primeiro.")

    monkeypatch.setattr(scheduling_scheduler, "SessionLocal", SessionLocalStub(db_session))
    monkeypatch.setattr(scheduling_scheduler, "get_settings", lambda: _settings())
    monkeypatch.setattr(scheduling_scheduler, "get_ixc_client", lambda: "client")
    monkeypatch.setattr(scheduling_scheduler, "run_sync", fail_run_sync)

    result = scheduling_scheduler.run_scheduling_sync_once(interval_minutes=20)

    assert result is None
    last_error = _setting_value(db_session, scheduling_scheduler.SCHEDULING_SYNC_LAST_ERROR_KEY)
    assert last_error is not None
    assert "marca d'água" in last_error
    assert _setting_value(db_session, scheduling_scheduler.SCHEDULING_SYNC_CONSECUTIVE_FAILURES_KEY) == "1"


def test_scheduling_sync_calls_run_sync_incremental_when_watermark_exists(monkeypatch, db_session):
    calls = []

    def fake_run_sync(db, client, *, date_from=None, date_to=None):
        calls.append({"client": client, "date_from": date_from, "date_to": date_to})
        return {"events_created": 3}

    monkeypatch.setattr(scheduling_scheduler, "SessionLocal", SessionLocalStub(db_session))
    monkeypatch.setattr(scheduling_scheduler, "get_settings", lambda: _settings())
    monkeypatch.setattr(scheduling_scheduler, "get_ixc_client", lambda: "client")
    monkeypatch.setattr(scheduling_scheduler, "run_sync", fake_run_sync)

    result = scheduling_scheduler.run_scheduling_sync_once(interval_minutes=20)

    assert result == {"events_created": 3}
    assert len(calls) == 1
    # Sem date_from/date_to - o scheduler automático nunca faz backfill grande, só incremental.
    assert calls[0]["date_from"] is None
    assert calls[0]["date_to"] is None
    assert _setting_value(db_session, scheduling_scheduler.SCHEDULING_SYNC_LAST_SUCCESS_AT_KEY)
    assert _setting_value(db_session, scheduling_scheduler.SCHEDULING_SYNC_CONSECUTIVE_FAILURES_KEY) == "0"


def test_scheduling_sync_failure_increments_counter_without_raising(monkeypatch, db_session):
    db_session.add(AppSetting(key=scheduling_scheduler.SCHEDULING_SYNC_CONSECUTIVE_FAILURES_KEY, value="2"))
    db_session.flush()

    def fail_run_sync(db, client, *, date_from=None, date_to=None):
        raise RuntimeError("IXC indisponível")

    monkeypatch.setattr(scheduling_scheduler, "SessionLocal", SessionLocalStub(db_session))
    monkeypatch.setattr(scheduling_scheduler, "get_settings", lambda: _settings())
    monkeypatch.setattr(scheduling_scheduler, "get_ixc_client", lambda: "client")
    monkeypatch.setattr(scheduling_scheduler, "run_sync", fail_run_sync)

    result = scheduling_scheduler.run_scheduling_sync_once(interval_minutes=20)

    assert result is None
    assert _setting_value(db_session, scheduling_scheduler.SCHEDULING_SYNC_LAST_ERROR_KEY) == "IXC indisponível"
    assert _setting_value(db_session, scheduling_scheduler.SCHEDULING_SYNC_CONSECUTIVE_FAILURES_KEY) == "3"


def test_scheduling_sync_loop_never_raises_when_a_round_fails(monkeypatch):
    """O loop nunca propaga uma falha de rodada - só dorme e tenta de novo no próximo ciclo."""
    import asyncio

    class StopLoop(Exception):
        pass

    calls: list[str] = []

    async def fake_sleep(seconds):
        calls.append("sleep")
        raise StopLoop()

    async def fake_to_thread(func, *args, **kwargs):
        calls.append("to_thread")
        return func(*args, **kwargs)

    def fake_run_once(interval_minutes=None):
        calls.append("run_once")
        return None  # run_scheduling_sync_once nunca propaga - falha já foi registrada e engolida

    monkeypatch.setattr(scheduling_scheduler, "_current_sync_enabled", lambda default: True)
    wait_times = iter([0.0, 1200.0])
    monkeypatch.setattr(scheduling_scheduler, "_seconds_until_next_sync", lambda default_interval_minutes: next(wait_times))
    monkeypatch.setattr(scheduling_scheduler, "_current_interval_minutes", lambda default: 20)
    monkeypatch.setattr(scheduling_scheduler, "run_scheduling_sync_once", fake_run_once)
    monkeypatch.setattr(scheduling_scheduler.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(scheduling_scheduler.asyncio, "to_thread", fake_to_thread)

    try:
        asyncio.run(scheduling_scheduler.run_scheduling_sync_loop(20, initial_enabled=True))
        raised = False
    except StopLoop:
        raised = False
    except Exception:
        raised = True

    assert not raised
    assert calls == ["to_thread", "run_once", "sleep"]
