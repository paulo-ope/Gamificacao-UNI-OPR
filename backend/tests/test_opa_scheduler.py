from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import select

from app.models import AppSetting
from app.modules.support import router as support_router
from app.modules.support.models import SupportOpaImportRun
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


def test_opa_sync_once_recomputes_next_allowed_at_from_finish_time_on_success(monkeypatch, db_session):
    def fake_import(db, client, *, date_from, date_to, imported_by):
        return {
            "run_id": 1,
            "status": "completed",
            "date_from": date_from,
            "date_to": date_to,
            "fetched_count": 0,
            "created_count": 0,
            "updated_count": 0,
            "unchanged_count": 0,
            "rejected_count": 0,
            "errors": [],
        }

    monkeypatch.setattr(opa_scheduler, "SessionLocal", SessionLocalStub(db_session))
    monkeypatch.setattr(opa_scheduler, "get_settings", lambda: _settings(opa_sync_lookback_days=0))
    monkeypatch.setattr(opa_scheduler, "get_opa_client", lambda: "client")
    monkeypatch.setattr(opa_scheduler, "import_opa_attendances", fake_import)

    before = datetime.now(timezone.utc)
    opa_scheduler.run_opa_sync_once(interval_minutes=20)
    after = datetime.now(timezone.utc)

    next_allowed_at = opa_scheduler._parse_sync_timestamp(
        _setting_value(db_session, opa_scheduler.SUPPORT_OPA_SYNC_NEXT_ALLOWED_AT_KEY)
    )
    # Recalculado a partir do FIM da execução (agora), não do início registrado por
    # `_record_sync_attempt_started` — por isso cai numa janela estreita ao redor de
    # "agora + intervalo", mesmo que a execução tenha demorado.
    assert before + timedelta(minutes=20) <= next_allowed_at <= after + timedelta(minutes=20)


def test_opa_sync_once_recomputes_next_allowed_at_from_finish_time_on_failure(monkeypatch, db_session):
    def fail_import(*args, **kwargs):
        raise RuntimeError("OPA indisponível")

    monkeypatch.setattr(opa_scheduler, "SessionLocal", SessionLocalStub(db_session))
    monkeypatch.setattr(opa_scheduler, "get_settings", lambda: _settings(opa_sync_lookback_days=0))
    monkeypatch.setattr(opa_scheduler, "get_opa_client", lambda: "client")
    monkeypatch.setattr(opa_scheduler, "import_opa_attendances", fail_import)

    before = datetime.now(timezone.utc)
    opa_scheduler.run_opa_sync_once(interval_minutes=20)
    after = datetime.now(timezone.utc)

    next_allowed_at = opa_scheduler._parse_sync_timestamp(
        _setting_value(db_session, opa_scheduler.SUPPORT_OPA_SYNC_NEXT_ALLOWED_AT_KEY)
    )
    assert before + timedelta(minutes=20) <= next_allowed_at <= after + timedelta(minutes=20)


def test_opa_sync_status_reports_scheduled_run_in_progress(db_session, admin_user):
    db_session.add(
        SupportOpaImportRun(
            provider="opa",
            entity="attendance",
            mode="scheduled",
            date_from=datetime(2026, 8, 25).date(),
            date_to=datetime(2026, 8, 25).date(),
            status="running",
            started_at=datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc),
        )
    )
    db_session.flush()

    status = support_router.opa_sync_status(db=db_session, user=admin_user)

    assert status["sync_in_progress"] is True
    assert status["active_run_mode"] == "scheduled"
    # SQLite (usado nos testes) não preserva tzinfo em DateTime — compara os campos.
    assert status["active_run_started_at"].replace(tzinfo=timezone.utc) == datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc)
    # SQLite nos testes não tem lock consultivo do Postgres — sinal fica indefinido.
    assert status["lock_busy"] is None


def test_opa_sync_status_reports_no_import_in_progress_by_default(db_session, admin_user):
    status = support_router.opa_sync_status(db=db_session, user=admin_user)

    assert status["sync_in_progress"] is False
    assert status["active_run_id"] is None
    assert status["active_run_mode"] is None
    assert status["next_window_delayed"] is False

