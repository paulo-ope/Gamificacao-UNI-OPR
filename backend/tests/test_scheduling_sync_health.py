from __future__ import annotations

from types import SimpleNamespace

from app.models import AppSetting
from app.modules.scheduling import router as scheduling_router
from app.modules.scheduling import scheduler as scheduling_scheduler


def _settings(**overrides):
    values = {
        "ixc_api_base_url": "https://ixc.local",
        "ixc_api_token": "token",
        "scheduling_sync_enabled": True,
        "scheduling_sync_interval_minutes": 20,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_sync_health_reports_not_configured_without_ixc_credentials(db_session, admin_user, monkeypatch):
    monkeypatch.setattr(scheduling_router, "get_settings", lambda: _settings(ixc_api_base_url="", ixc_api_token=""))

    health = scheduling_router.sync_health(db=db_session, user=admin_user)

    assert health.configured is False


def test_sync_health_reflects_appsetting_values(db_session, admin_user, monkeypatch):
    monkeypatch.setattr(scheduling_router, "get_settings", lambda: _settings())
    db_session.add(AppSetting(key=scheduling_scheduler.SCHEDULING_SYNC_LAST_SUCCESS_AT_KEY, value="2026-08-31T10:00:00+00:00"))
    db_session.add(AppSetting(key=scheduling_scheduler.SCHEDULING_SYNC_LAST_ERROR_KEY, value="IXC indisponível"))
    db_session.add(AppSetting(key=scheduling_scheduler.SCHEDULING_SYNC_CONSECUTIVE_FAILURES_KEY, value="2"))
    db_session.flush()

    health = scheduling_router.sync_health(db=db_session, user=admin_user)

    assert health.configured is True
    assert health.enabled is True
    assert health.interval_minutes == 20
    assert health.last_success_at is not None
    assert health.last_error == "IXC indisponível"
    assert health.consecutive_failures == 2


def test_sync_health_defaults_to_zero_failures_when_never_synced(db_session, admin_user, monkeypatch):
    monkeypatch.setattr(scheduling_router, "get_settings", lambda: _settings())

    health = scheduling_router.sync_health(db=db_session, user=admin_user)

    assert health.consecutive_failures == 0
    assert health.last_success_at is None
    assert health.last_error is None
