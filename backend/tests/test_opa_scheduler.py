from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import select

from app.models import AppSetting
from app.services import opa_scheduler


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
        "opa_api_base_url": "https://opa.local",
        "opa_api_token": "token",
        "opa_sync_interval_minutes": 20,
        "opa_sync_lookback_days": 1,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _setting_value(db_session, key: str) -> str | None:
    setting = db_session.scalar(select(AppSetting).where(AppSetting.key == key))
    return setting.value if setting else None


def test_opa_sync_once_does_nothing_without_config(monkeypatch):
    monkeypatch.setattr(opa_scheduler, "get_settings", lambda: _settings(opa_api_base_url="", opa_api_token=""))

    assert opa_scheduler.run_opa_sync_once() is None


def test_opa_sync_once_imports_lookback_days_and_records_success(monkeypatch, db_session):
    imported_days = []

    def fake_import(db, client, *, date_from, date_to, imported_by):
        imported_days.append((date_from, date_to, imported_by, client))
        return {
            "run_id": len(imported_days),
            "status": "completed",
            "date_from": date_from,
            "date_to": date_to,
            "fetched_count": 1,
            "created_count": 1,
            "updated_count": 0,
            "unchanged_count": 0,
            "rejected_count": 0,
            "errors": [],
        }

    monkeypatch.setattr(opa_scheduler, "SessionLocal", SessionLocalStub(db_session))
    monkeypatch.setattr(opa_scheduler, "get_settings", lambda: _settings(opa_sync_lookback_days=1))
    monkeypatch.setattr(opa_scheduler, "get_opa_client", lambda: "client")
    monkeypatch.setattr(opa_scheduler, "import_opa_attendances", fake_import)

    result = opa_scheduler.run_opa_sync_once(interval_minutes=20)

    assert result is not None
    assert len(result["imports"]) == 2
    assert len(imported_days) == 2
    assert {item[2] for item in imported_days} == {None}
    assert {item[3] for item in imported_days} == {"client"}
    assert _setting_value(db_session, opa_scheduler.SUPPORT_OPA_SYNC_LAST_SUCCESS_AT_KEY)
    assert _setting_value(db_session, opa_scheduler.SUPPORT_OPA_SYNC_LAST_ATTEMPT_AT_KEY)
    assert _setting_value(db_session, opa_scheduler.SUPPORT_OPA_SYNC_CONSECUTIVE_FAILURES_KEY) == "0"


def test_opa_sync_once_records_failure_without_raising(monkeypatch, db_session):
    db_session.add(AppSetting(key=opa_scheduler.SUPPORT_OPA_SYNC_CONSECUTIVE_FAILURES_KEY, value="2"))
    db_session.flush()

    def fail_import(*args, **kwargs):
        raise RuntimeError("OPA indisponível")

    monkeypatch.setattr(opa_scheduler, "SessionLocal", SessionLocalStub(db_session))
    monkeypatch.setattr(opa_scheduler, "get_settings", lambda: _settings(opa_sync_lookback_days=1))
    monkeypatch.setattr(opa_scheduler, "get_opa_client", lambda: "client")
    monkeypatch.setattr(opa_scheduler, "import_opa_attendances", fail_import)

    result = opa_scheduler.run_opa_sync_once(interval_minutes=20)

    assert result is None
    assert _setting_value(db_session, opa_scheduler.SUPPORT_OPA_SYNC_LAST_ERROR_KEY) == "OPA indisponível"
    assert _setting_value(db_session, opa_scheduler.SUPPORT_OPA_SYNC_LAST_ERROR_AT_KEY)
    assert _setting_value(db_session, opa_scheduler.SUPPORT_OPA_SYNC_CONSECUTIVE_FAILURES_KEY) == "3"

