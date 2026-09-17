from __future__ import annotations

from types import SimpleNamespace

from app.modules.support import ixc_ticket_scheduler
from app.services.calculation import get_setting


class _SessionLocalStub:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return self

    def __enter__(self):
        return self._session

    def __exit__(self, exc_type, exc, tb):
        return False


def _bind_session(monkeypatch, session):
    monkeypatch.setattr(ixc_ticket_scheduler, "SessionLocal", _SessionLocalStub(session))


def _configured_settings():
    return SimpleNamespace(ixc_api_base_url="https://ixc.example.test", ixc_api_token="token")


def test_run_once_returns_none_when_ixc_not_configured(db_session, monkeypatch):
    _bind_session(monkeypatch, db_session)
    monkeypatch.setattr(ixc_ticket_scheduler, "get_settings", lambda: SimpleNamespace(ixc_api_base_url="", ixc_api_token=""))

    result = ixc_ticket_scheduler.run_ixc_ticket_sync_once()

    assert result is None


def test_run_once_imports_tickets_and_records_success(db_session, monkeypatch):
    _bind_session(monkeypatch, db_session)
    monkeypatch.setattr(ixc_ticket_scheduler, "get_settings", _configured_settings)
    monkeypatch.setattr(ixc_ticket_scheduler, "get_ixc_client", lambda: object())

    calls = []

    def fake_import_tickets(db, client, **kwargs):
        calls.append(("tickets", kwargs))
        return {"fetched": 3, "created": 3, "updated": 0, "unchanged": 0, "rejected": 0}

    monkeypatch.setattr(ixc_ticket_scheduler, "import_tickets_for_period", fake_import_tickets)
    monkeypatch.setattr(
        ixc_ticket_scheduler,
        "import_customer_contracts",
        lambda db, client: {"fetched": 0, "created": 0, "updated": 0, "unchanged": 0, "rejected": 0},
    )

    result = ixc_ticket_scheduler.run_ixc_ticket_sync_once()

    assert result["tickets"]["created"] == 3
    assert calls[0][0] == "tickets"
    assert get_setting(db_session, ixc_ticket_scheduler.SUPPORT_IXC_TICKET_SYNC_LAST_SUCCESS_AT_KEY, "") != ""


def test_run_once_syncs_contracts_on_first_run(db_session, monkeypatch):
    _bind_session(monkeypatch, db_session)
    monkeypatch.setattr(ixc_ticket_scheduler, "get_settings", _configured_settings)
    monkeypatch.setattr(ixc_ticket_scheduler, "get_ixc_client", lambda: object())
    monkeypatch.setattr(
        ixc_ticket_scheduler,
        "import_tickets_for_period",
        lambda db, client, **kwargs: {"fetched": 0, "created": 0, "updated": 0, "unchanged": 0, "rejected": 0},
    )

    contract_calls = []
    monkeypatch.setattr(
        ixc_ticket_scheduler,
        "import_customer_contracts",
        lambda db, client: contract_calls.append(1) or {"fetched": 0, "created": 0, "updated": 0, "unchanged": 0, "rejected": 0},
    )

    result = ixc_ticket_scheduler.run_ixc_ticket_sync_once()

    assert len(contract_calls) == 1
    assert result["contracts"] is not None


def test_run_once_skips_contract_sync_when_recently_run(db_session, monkeypatch):
    from datetime import datetime, timezone

    from app.services.calculation import upsert_setting

    _bind_session(monkeypatch, db_session)
    monkeypatch.setattr(ixc_ticket_scheduler, "get_settings", _configured_settings)
    monkeypatch.setattr(ixc_ticket_scheduler, "get_ixc_client", lambda: object())
    monkeypatch.setattr(
        ixc_ticket_scheduler,
        "import_tickets_for_period",
        lambda db, client, **kwargs: {"fetched": 0, "created": 0, "updated": 0, "unchanged": 0, "rejected": 0},
    )
    upsert_setting(db_session, ixc_ticket_scheduler.SUPPORT_IXC_CONTRACT_SYNC_LAST_AT_KEY, datetime.now(timezone.utc).isoformat())
    db_session.commit()

    contract_calls = []
    monkeypatch.setattr(
        ixc_ticket_scheduler,
        "import_customer_contracts",
        lambda db, client: contract_calls.append(1),
    )

    result = ixc_ticket_scheduler.run_ixc_ticket_sync_once()

    assert contract_calls == []
    assert result["contracts"] is None


def test_run_once_treats_lock_busy_as_warning_not_error(db_session, monkeypatch):
    """Achado real em produção (2026-09-11): 'outra importação já em andamento' é condição
    esperada (ciclo anterior ainda rodando), não falha de integração - não deve marcar
    SUPPORT_IXC_TICKET_SYNC_LAST_ERROR_KEY (mesmo tratamento de scheduling/scheduler.py)."""
    _bind_session(monkeypatch, db_session)
    monkeypatch.setattr(ixc_ticket_scheduler, "get_settings", _configured_settings)
    monkeypatch.setattr(ixc_ticket_scheduler, "get_ixc_client", lambda: object())

    def busy_import(db, client, **kwargs):
        raise RuntimeError("Outra importação de atendimento IXC já está em andamento.")

    monkeypatch.setattr(ixc_ticket_scheduler, "import_tickets_for_period", busy_import)

    result = ixc_ticket_scheduler.run_ixc_ticket_sync_once()

    assert result is None
    assert get_setting(db_session, ixc_ticket_scheduler.SUPPORT_IXC_TICKET_SYNC_LAST_ERROR_KEY, "") == ""


def test_run_once_records_error_without_raising(db_session, monkeypatch):
    _bind_session(monkeypatch, db_session)
    monkeypatch.setattr(ixc_ticket_scheduler, "get_settings", _configured_settings)
    monkeypatch.setattr(ixc_ticket_scheduler, "get_ixc_client", lambda: object())

    def failing_import(db, client, **kwargs):
        # ConnectionError, não RuntimeError: RuntimeError agora é reservado para "outra
        # importação já em andamento" (tratado como aviso, não erro - ver
        # test_run_once_treats_lock_busy_as_warning_not_error).
        raise ConnectionError("falha simulada de rede")

    monkeypatch.setattr(ixc_ticket_scheduler, "import_tickets_for_period", failing_import)

    result = ixc_ticket_scheduler.run_ixc_ticket_sync_once()

    assert result is None
    assert "falha simulada" in get_setting(db_session, ixc_ticket_scheduler.SUPPORT_IXC_TICKET_SYNC_LAST_ERROR_KEY, "")
