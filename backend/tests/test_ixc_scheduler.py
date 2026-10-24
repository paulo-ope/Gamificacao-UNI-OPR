import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.services import ixc_scheduler


class StopLoop(Exception):
    pass


def test_sync_wait_seconds_requires_full_interval_when_never_attempted():
    assert ixc_scheduler._sync_wait_seconds(None, 20) == 20 * 60


def test_sync_wait_seconds_blocks_until_configured_interval_passes():
    now = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
    next_allowed = now + timedelta(minutes=12)

    wait_seconds = ixc_scheduler._sync_wait_seconds(next_allowed, 20, now=now)

    assert wait_seconds == 12 * 60


def test_sync_wait_seconds_allows_run_after_configured_interval():
    now = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
    next_allowed = now - timedelta(minutes=5)

    wait_seconds = ixc_scheduler._sync_wait_seconds(next_allowed, 20, now=now)

    assert wait_seconds == 0


def test_ixc_loop_sleeps_before_first_automatic_sync_when_interval_remains(monkeypatch):
    calls: list[tuple[str, float | None]] = []

    async def fake_sleep(seconds):
        calls.append(("sleep", seconds))
        raise StopLoop()

    def fail_sync():
        calls.append(("sync", None))
        raise AssertionError("sync should not run before the configured interval")

    monkeypatch.setattr(ixc_scheduler, "_current_sync_enabled", lambda default: True)
    monkeypatch.setattr(ixc_scheduler, "_seconds_until_next_sync", lambda default_interval_minutes: 1200.0)
    monkeypatch.setattr(ixc_scheduler, "run_ixc_sync_once", fail_sync)
    monkeypatch.setattr(ixc_scheduler.asyncio, "sleep", fake_sleep)

    with pytest.raises(StopLoop):
        asyncio.run(ixc_scheduler.run_ixc_sync_loop(20, initial_enabled=True))

    assert calls == [("sleep", 15.0)]


def test_ixc_loop_runs_sync_when_configured_interval_has_passed(monkeypatch):
    calls: list[tuple[str, float | None]] = []

    async def fake_sleep(seconds):
        calls.append(("sleep", seconds))
        raise StopLoop()

    async def fake_to_thread(func, *args, **kwargs):
        calls.append(("to_thread", None))
        return func(*args, **kwargs)

    def fake_sync(interval_minutes=None):
        calls.append(("sync", None))
        return {"summary": {}}

    monkeypatch.setattr(ixc_scheduler, "_current_sync_enabled", lambda default: True)
    wait_times = iter([0.0, 1200.0])

    monkeypatch.setattr(ixc_scheduler, "_seconds_until_next_sync", lambda default_interval_minutes: next(wait_times))
    monkeypatch.setattr(ixc_scheduler, "_current_interval_minutes", lambda default: 20)
    monkeypatch.setattr(ixc_scheduler, "run_ixc_sync_once", fake_sync)
    monkeypatch.setattr(ixc_scheduler.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(ixc_scheduler.asyncio, "to_thread", fake_to_thread)

    with pytest.raises(StopLoop):
        asyncio.run(ixc_scheduler.run_ixc_sync_loop(20, initial_enabled=True))

    assert calls == [("to_thread", None), ("sync", None), ("sleep", 15.0)]


class _FakeDb:
    def __init__(self):
        self.rollbacks = 0

    def rollback(self):
        self.rollbacks += 1


def test_recent_reconciliation_runs_real_and_only_for_missing_orders(monkeypatch):
    seen = {}

    def fake_reconcile(db, **kwargs):
        seen.update(kwargs)
        return {"created_count": 3, "error_count": 0, "invalid_collaborator": 0, "blocked_paid_period": 0}

    monkeypatch.setattr(ixc_scheduler, "reconcile_recent_missing_service_orders_from_operations", fake_reconcile)

    result = ixc_scheduler._run_recent_reconciliation(_FakeDb())

    assert result["created_count"] == 3
    assert seen["dry_run"] is False
    assert seen["only_missing"] is True
    assert seen["days"] == ixc_scheduler.RECONCILIATION_RECENT_DAYS


def test_recent_reconciliation_failure_does_not_break_the_cycle(monkeypatch):
    def failing_reconcile(db, **kwargs):
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(ixc_scheduler, "reconcile_recent_missing_service_orders_from_operations", failing_reconcile)
    db = _FakeDb()

    result = ixc_scheduler._run_recent_reconciliation(db)

    assert result["created_count"] == 0
    assert result["error_count"] == 1
    assert db.rollbacks == 1
