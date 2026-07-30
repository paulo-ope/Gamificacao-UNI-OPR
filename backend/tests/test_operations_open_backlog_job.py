import pytest

from app.modules.operations import backfill
from app.services.ixc_client import IxcApiError


def _fake_result(**overrides):
    result = {
        "fetched_count": 1,
        "created_count": 1,
        "updated_count": 0,
        "unchanged_count": 0,
        "rejected_count": 0,
        "errors": [],
    }
    result.update(overrides)
    return result


def test_create_open_backlog_job_dedupes_sectors_and_sets_total(db_session, admin_user):
    job = backfill.create_open_backlog_job(
        db_session, sector_ids=["7", "8", "7"], requested_by=admin_user.id,
    )

    assert job.status == "pending"
    assert job.sector_ids == ["7", "8"]
    assert job.total_sectors == 2
    assert job.processed_sectors == 0


def test_create_open_backlog_job_requires_at_least_one_sector(db_session, admin_user):
    with pytest.raises(ValueError):
        backfill.create_open_backlog_job(db_session, sector_ids=[], requested_by=admin_user.id)


def test_run_open_backlog_job_processes_every_sector_and_completes(db_session, admin_user, monkeypatch):
    job = backfill.create_open_backlog_job(
        db_session, sector_ids=["7", "8", "9"], requested_by=admin_user.id,
    )
    calls: list[str] = []

    def fake_import(db, client, *, date_from, date_to, imported_by, sector_ids, open_backlog=False):
        calls.append(sector_ids[0])
        return _fake_result()

    monkeypatch.setattr(backfill, "import_current_month_period", fake_import)
    monkeypatch.setattr(backfill, "get_ixc_client", lambda: object())

    result = backfill.run_open_backlog_job(db_session, job_id=job.id)

    assert result.status == "completed"
    assert result.processed_sectors == 3
    assert result.created_count == 3
    assert calls == ["7", "8", "9"], "cada setor deve ser processado exatamente uma vez, em ordem"


def test_run_open_backlog_job_retries_transient_ixc_api_error(db_session, admin_user, monkeypatch):
    job = backfill.create_open_backlog_job(db_session, sector_ids=["7"], requested_by=admin_user.id)
    attempts = {"n": 0}

    def flaky_import(db, client, *, date_from, date_to, imported_by, sector_ids, open_backlog=False):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise IxcApiError("timeout passageiro")
        return _fake_result()

    monkeypatch.setattr(backfill, "import_current_month_period", flaky_import)
    monkeypatch.setattr(backfill, "get_ixc_client", lambda: object())
    monkeypatch.setattr(backfill.time, "sleep", lambda seconds: None)

    result = backfill.run_open_backlog_job(db_session, job_id=job.id)

    assert result.status == "completed"
    assert attempts["n"] == 3


def test_run_open_backlog_job_marks_failed_with_friendly_reason_on_unexpected_error(
    db_session, admin_user, monkeypatch,
):
    job = backfill.create_open_backlog_job(db_session, sector_ids=["7"], requested_by=admin_user.id)

    def failing_import(db, client, *, date_from, date_to, imported_by, sector_ids, open_backlog=False):
        raise ValueError("falha inesperada de normalização")

    monkeypatch.setattr(backfill, "import_current_month_period", failing_import)
    monkeypatch.setattr(backfill, "get_ixc_client", lambda: object())

    with pytest.raises(ValueError):
        backfill.run_open_backlog_job(db_session, job_id=job.id)

    db_session.refresh(job)
    assert job.status == "failed"
    assert job.errors[-1]["sector_id"] == "7"
    assert "falha inesperada" in job.errors[-1]["reason"]


def test_run_open_backlog_job_resumes_without_reprocessing_completed_sectors(
    db_session, admin_user, monkeypatch,
):
    job = backfill.create_open_backlog_job(
        db_session, sector_ids=["7", "8"], requested_by=admin_user.id,
    )
    calls: list[str] = []

    def failing_on_sector_8(db, client, *, date_from, date_to, imported_by, sector_ids, open_backlog=False):
        calls.append(sector_ids[0])
        if sector_ids[0] == "8":
            raise ValueError("boom")
        return _fake_result()

    monkeypatch.setattr(backfill, "import_current_month_period", failing_on_sector_8)
    monkeypatch.setattr(backfill, "get_ixc_client", lambda: object())

    with pytest.raises(ValueError):
        backfill.run_open_backlog_job(db_session, job_id=job.id)

    db_session.refresh(job)
    assert job.status == "failed"
    assert job.processed_sectors == 1, "setor 7 deve ter sido contabilizado antes da falha no 8"

    def now_working(db, client, *, date_from, date_to, imported_by, sector_ids, open_backlog=False):
        calls.append(sector_ids[0])
        return _fake_result()

    monkeypatch.setattr(backfill, "import_current_month_period", now_working)
    result = backfill.run_open_backlog_job(db_session, job_id=job.id)

    assert result.status == "completed"
    assert result.processed_sectors == 2
    assert calls == ["7", "8", "8"], "setor 7 não deve ser reprocessado ao retomar o job"
