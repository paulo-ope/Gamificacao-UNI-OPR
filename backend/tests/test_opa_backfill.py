"""Backfill automático de meses completos do OPA Suite (roda de madrugada) - achado
real de 2026-08-27: sync manual de um mês inteiro rodava dentro da requisição HTTP
(risco de timeout) e não existia nenhum jeito de saber se um mês já foi totalmente
importado. Testa: import de período virou job em background (POST devolve na hora,
progresso via GET /opa/sync-runs/{id}), rastreio de mês completo
(SupportOpaImportMonth) e o job de backfill que roda 1x por dia a partir da hora
configurada, importando só os meses recentes ainda não completos."""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.modules.support.models import SupportOpaImportMonth, SupportOpaImportRun
from app.modules.support.opa_ingestion import (
    _create_pending_import_run,
    _maybe_mark_month_complete,
    _month_bounds,
    import_months_status,
    run_opa_import_background_job,
)
from app.services import opa_scheduler
from app.services.calculation import upsert_setting
from tests.test_opa_ingestion import FakeOpaClient, _record
from tests.test_opa_scheduler import SessionLocalStub


def _settings(**overrides):
    values = {"opa_api_base_url": "https://opa.local", "opa_api_token": "token"}
    values.update(overrides)
    return SimpleNamespace(**values)


def test_month_bounds():
    assert _month_bounds(2026, 2) == (date(2026, 2, 1), date(2026, 2, 28))
    assert _month_bounds(2026, 7) == (date(2026, 7, 1), date(2026, 7, 31))


def test_maybe_mark_month_complete_only_for_full_month_success(db_session):
    run = SupportOpaImportRun(
        provider="opa", entity="attendance", mode="manual",
        date_from=date(2026, 7, 1), date_to=date(2026, 7, 31), status="completed",
    )
    db_session.add(run)
    db_session.flush()

    # Run parcial (não cobre o mês inteiro) - não deve marcar nada.
    partial = SupportOpaImportRun(
        provider="opa", entity="attendance", mode="manual",
        date_from=date(2026, 7, 5), date_to=date(2026, 7, 10), status="completed",
    )
    db_session.add(partial)
    db_session.flush()
    _maybe_mark_month_complete(db_session, run_id=partial.id, date_from=partial.date_from, date_to=partial.date_to, status=partial.status)
    assert db_session.query(SupportOpaImportMonth).count() == 0

    # Run de mês inteiro mas falhou - não deve marcar.
    _maybe_mark_month_complete(db_session, run_id=run.id, date_from=run.date_from, date_to=run.date_to, status="failed")
    assert db_session.query(SupportOpaImportMonth).count() == 0

    # Run de mês inteiro com sucesso - marca "complete".
    _maybe_mark_month_complete(db_session, run_id=run.id, date_from=run.date_from, date_to=run.date_to, status="completed")
    month = db_session.query(SupportOpaImportMonth).filter_by(year_month="2026-07").one()
    assert month.status == "complete"
    assert month.last_run_id == run.id


def test_import_months_status_defaults_to_missing(db_session):
    db_session.add(SupportOpaImportMonth(year_month="2026-06", status="complete", attendance_count=42))
    db_session.flush()

    result = import_months_status(db_session, ["2026-05", "2026-06"])
    assert result["2026-05"]["status"] == "missing"
    assert result["2026-06"]["status"] == "complete"
    assert result["2026-06"]["attendance_count"] == 42


def test_run_opa_import_background_job_completes_pending_run(db_session, monkeypatch):
    records = [_record(id=f"OPA-{i}", data_abertura="2026-07-10T10:00:00+00:00", data_encerramento="2026-07-10T10:10:00+00:00") for i in range(3)]
    fake_client = FakeOpaClient(records)
    monkeypatch.setattr("app.modules.support.opa_ingestion.get_opa_client", lambda: fake_client)

    run_id = _create_pending_import_run(mode="manual", date_from=date(2026, 7, 10), date_to=date(2026, 7, 10), imported_by=None)
    created = db_session.get(SupportOpaImportRun, run_id)
    assert created.status == "pending"
    db_session.expire_all()

    run_opa_import_background_job(run_id)

    db_session.expire_all()
    finished = db_session.get(SupportOpaImportRun, run_id)
    assert finished.status in ("completed", "completed_with_warnings")
    assert finished.created_count == 3


def test_backfill_once_skips_already_complete_months(db_session, monkeypatch):
    fake_client = FakeOpaClient([])
    monkeypatch.setattr(opa_scheduler, "SessionLocal", SessionLocalStub(db_session))
    monkeypatch.setattr(opa_scheduler, "get_opa_client", lambda: fake_client)
    monkeypatch.setattr(opa_scheduler, "get_settings", lambda: _settings())

    today = datetime.now(opa_scheduler.SUPPORT_TIMEZONE).date()
    current_year_month = today.strftime("%Y-%m")
    db_session.add(SupportOpaImportMonth(year_month=current_year_month, status="complete", attendance_count=10))
    db_session.commit()

    result = opa_scheduler.run_opa_backfill_once(lookback_months=1)
    assert result == {"imported_months": []}
    # Nenhuma chamada à API - o único mês do lookback já estava completo.
    assert fake_client.attendance_calls == []


def test_backfill_once_imports_missing_month_and_marks_complete(db_session, monkeypatch):
    today = datetime.now(opa_scheduler.SUPPORT_TIMEZONE).date()
    records = [
        _record(
            id="OPA-BF-1",
            data_abertura=f"{today.strftime('%Y-%m')}-05T10:00:00+00:00",
            data_encerramento=f"{today.strftime('%Y-%m')}-05T10:10:00+00:00",
        )
    ]
    fake_client = FakeOpaClient(records)
    monkeypatch.setattr(opa_scheduler, "SessionLocal", SessionLocalStub(db_session))
    monkeypatch.setattr(opa_scheduler, "get_opa_client", lambda: fake_client)
    monkeypatch.setattr(opa_scheduler, "get_settings", lambda: _settings())

    result = opa_scheduler.run_opa_backfill_once(lookback_months=1)
    assert len(result["imported_months"]) == 1
    assert fake_client.attendance_calls  # a API foi chamada pro mês faltando

    db_session.expire_all()
    months = db_session.query(SupportOpaImportMonth).all()
    assert len(months) == 1
    assert months[0].status == "complete"


def test_import_opa_period_endpoint_runs_in_background_and_status_is_pollable(client, db_session, monkeypatch):
    """POST /opa-imports não deve bloquear a requisição - devolve o run_id na hora, e
    GET /opa/sync-runs/{id} reflete o progresso. No TestClient o BackgroundTasks já
    roda antes da resposta terminar de ser processada, então o GET seguinte já vê o
    resultado final - é exatamente esse comportamento (job assíncrono, mas rápido o
    bastante pra concluir dentro do ciclo de teste) que a UI vai fazer polling até ver."""
    records = [_record(id="OPA-EP-1", data_abertura="2026-07-10T10:00:00+00:00", data_encerramento="2026-07-10T10:10:00+00:00")]
    fake_client = FakeOpaClient(records)
    monkeypatch.setattr("app.modules.support.opa_ingestion.get_opa_client", lambda: fake_client)

    response = client.post("/api/support/opa-imports", json={"date_from": "2026-07-10", "date_to": "2026-07-10"})
    assert response.status_code == 200
    run_id = response.json()["run_id"]

    status_response = client.get(f"/api/support/opa/sync-runs/{run_id}")
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["run_id"] == run_id
    assert body["status"] in ("completed", "completed_with_warnings")
    assert body["created_count"] == 1


def test_import_opa_period_endpoint_rejects_when_busy(client, db_session, monkeypatch):
    monkeypatch.setattr("app.modules.support.router.opa_import_lock_busy", lambda db: True)
    response = client.post("/api/support/opa-imports", json={"date_from": "2026-07-10", "date_to": "2026-07-10"})
    assert response.status_code == 409


def test_backfill_due_respects_run_hour_and_daily_gate(db_session, monkeypatch):
    monkeypatch.setattr(opa_scheduler, "SessionLocal", SessionLocalStub(db_session))
    upsert_setting(db_session, opa_scheduler.SUPPORT_OPA_BACKFILL_ENABLED_KEY, "true")
    # Hora configurada 1h no futuro (mod 24) - ainda não chegou, não deve disparar.
    future_hour = (datetime.now(opa_scheduler.SUPPORT_TIMEZONE).hour + 1) % 24
    upsert_setting(db_session, opa_scheduler.SUPPORT_OPA_BACKFILL_RUN_HOUR_KEY, str(future_hour))
    db_session.commit()
    assert opa_scheduler._backfill_due(default_enabled=True, default_run_hour=3) is False

    # Hora já passou (0h) e nunca rodou hoje - deve disparar.
    upsert_setting(db_session, opa_scheduler.SUPPORT_OPA_BACKFILL_RUN_HOUR_KEY, "0")
    db_session.commit()
    assert opa_scheduler._backfill_due(default_enabled=True, default_run_hour=3) is True

    # Já rodou hoje - não deve disparar de novo.
    today = datetime.now(opa_scheduler.SUPPORT_TIMEZONE).date()
    upsert_setting(db_session, opa_scheduler.SUPPORT_OPA_BACKFILL_LAST_RUN_DATE_KEY, today.isoformat())
    db_session.commit()
    assert opa_scheduler._backfill_due(default_enabled=True, default_run_hour=3) is False
