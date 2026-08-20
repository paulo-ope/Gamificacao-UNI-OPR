from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import func, select

from app.modules.support.models import SupportOpaAttendance, SupportOpaAttendanceRaw, SupportOpaImportRun
from app.modules.support.opa_ingestion import OpaImportInterrupted, import_opa_attendances, resume_opa_import_run
from app.modules.support.router import opa_metrics
from app.services.opa_client import OpaPage


class FakeOpaClient:
    def __init__(self, records, users=None, reasons=None, departments=None, tags=None, clients=None, fail_on_skip=None, transient_failures=None):
        self.records = records
        self.users = users or []
        self.reasons = reasons or []
        self.departments = departments or []
        self.tags = tags or []
        self.clients = clients or []
        self.fail_on_skip = set(fail_on_skip or [])
        self.transient_failures = dict(transient_failures or {})
        self.attendance_calls = []

    def iter_attendances(self, **kwargs):
        yield from self.records

    def list_attendances(self, **kwargs):
        limit = kwargs.get("limit", 100)
        skip = kwargs.get("skip", 0)
        self.attendance_calls.append(skip)
        if skip in self.transient_failures and self.transient_failures[skip] > 0:
            self.transient_failures[skip] -= 1
            raise RuntimeError(f"erro transitório no skip {skip}")
        if skip in self.fail_on_skip:
            raise RuntimeError(f"falha no skip {skip}")
        return OpaPage(records=self.records[skip:skip + limit], total=len(self.records), limit=limit, skip=skip)

    def list_users(self):
        return self.users

    def list_reasons(self):
        return self.reasons

    def list_departments(self):
        return self.departments

    def list_tags(self):
        return self.tags

    def list_clients(self):
        return self.clients


def _record(**overrides):
    base = {
        "id": "OPA-1",
        "protocolo": "P-1",
        "cliente": {"id": "C-1", "nome": "Cliente Um"},
        "atendente": {"id": "A-1", "nome": "Atendente Um"},
        "motivo": {"id": "M-1", "nome": "Suporte"},
        "status": "finalizado",
        "data_abertura": "2026-08-15T10:00:00+00:00",
        "data_encerramento": "2026-08-15T10:10:00+00:00",
        "tma_seconds": 600,
        "tmr_seconds": 90,
    }
    base.update(overrides)
    return base


def test_import_opa_attendances_is_idempotent(db_session):
    client = FakeOpaClient([_record()])

    first = import_opa_attendances(
        db_session,
        client,
        date_from=date(2026, 8, 15),
        date_to=date(2026, 8, 15),
        imported_by=None,
    )
    second = import_opa_attendances(
        db_session,
        client,
        date_from=date(2026, 8, 15),
        date_to=date(2026, 8, 15),
        imported_by=None,
    )

    assert first["created_count"] == 1
    assert first["pages_processed"] == 1
    assert second["created_count"] == 0
    assert second["unchanged_count"] == 1
    assert db_session.scalar(select(func.count(SupportOpaAttendance.id))) == 1
    assert db_session.scalar(select(func.count(SupportOpaAttendanceRaw.id))) == 1


def test_import_opa_attendances_processes_all_pages_without_fixed_1000_limit(db_session):
    records = [_record(id=f"OPA-{index}") for index in range(1, 206)]
    client = FakeOpaClient(records)

    result = import_opa_attendances(
        db_session,
        client,
        date_from=date(2026, 8, 15),
        date_to=date(2026, 8, 15),
        imported_by=None,
    )

    assert result["created_count"] == 205
    assert result["fetched_count"] == 205
    assert result["pages_processed"] == 3
    assert db_session.scalar(select(func.count(SupportOpaAttendance.id))) == 205
    run = db_session.get(SupportOpaImportRun, result["run_id"])
    assert run is not None
    assert run.next_skip == 205
    assert run.checkpoint_json["finished_reason"] == "total_reached"


def test_import_opa_attendances_marks_interrupted_after_checkpoint(db_session, monkeypatch):
    monkeypatch.setattr("app.modules.support.opa_ingestion.time.sleep", lambda _: None)
    records = [_record(id=f"OPA-{index}") for index in range(1, 351)]
    client = FakeOpaClient(records, fail_on_skip={300})

    with pytest.raises(OpaImportInterrupted) as exc_info:
        import_opa_attendances(
            db_session,
            client,
            date_from=date(2026, 8, 15),
            date_to=date(2026, 8, 15),
            imported_by=None,
        )

    run = db_session.get(SupportOpaImportRun, exc_info.value.run_id)
    assert run is not None
    assert run.status == "interrupted"
    assert run.pages_processed == 3
    assert run.next_skip == 300
    assert run.fetched_count == 300
    assert run.created_count == 300
    assert run.checkpoint_json["next_skip"] == 300
    assert client.attendance_calls == [0, 100, 200, 300, 300, 300]


def test_resume_opa_import_run_starts_at_checkpoint_and_preserves_counters(db_session, monkeypatch):
    monkeypatch.setattr("app.modules.support.opa_ingestion.time.sleep", lambda _: None)
    records = [_record(id=f"OPA-{index}") for index in range(1, 351)]
    failing_client = FakeOpaClient(records, fail_on_skip={300})

    with pytest.raises(OpaImportInterrupted) as exc_info:
        import_opa_attendances(
            db_session,
            failing_client,
            date_from=date(2026, 8, 15),
            date_to=date(2026, 8, 15),
            imported_by=None,
        )

    resume_client = FakeOpaClient(records)
    result = resume_opa_import_run(
        db_session,
        resume_client,
        run_id=exc_info.value.run_id,
        imported_by=None,
    )

    assert resume_client.attendance_calls == [300]
    assert result["status"] == "completed"
    assert result["pages_processed"] == 4
    assert result["fetched_count"] == 350
    assert result["created_count"] == 350
    assert result["updated_count"] == 0
    assert result["unchanged_count"] == 0
    assert result["rejected_count"] == 0
    assert db_session.scalar(select(func.count(SupportOpaAttendance.id))) == 350


def test_import_opa_attendances_recovers_transient_page_error_with_retry(db_session, monkeypatch):
    monkeypatch.setattr("app.modules.support.opa_ingestion.time.sleep", lambda _: None)
    records = [_record(id=f"OPA-{index}") for index in range(1, 151)]
    client = FakeOpaClient(records, transient_failures={100: 1})

    result = import_opa_attendances(
        db_session,
        client,
        date_from=date(2026, 8, 15),
        date_to=date(2026, 8, 15),
        imported_by=None,
    )

    assert client.attendance_calls == [0, 100, 100]
    assert result["status"] == "completed"
    assert result["pages_processed"] == 2
    assert result["created_count"] == 150


def test_resume_opa_import_run_rejects_completed_run(db_session):
    client = FakeOpaClient([_record()])
    result = import_opa_attendances(
        db_session,
        client,
        date_from=date(2026, 8, 15),
        date_to=date(2026, 8, 15),
        imported_by=None,
    )

    with pytest.raises(ValueError, match="concluída"):
        resume_opa_import_run(
            db_session,
            FakeOpaClient([_record()]),
            run_id=result["run_id"],
            imported_by=None,
        )


def test_resume_opa_import_run_rejects_running_run(db_session):
    run = SupportOpaImportRun(
        provider="opa",
        entity="attendance",
        mode="resume",
        date_from=date(2026, 8, 15),
        date_to=date(2026, 8, 15),
        status="running",
        page_limit=100,
        pages_processed=3,
        next_skip=300,
        checkpoint_json={"next_skip": 300},
    )
    db_session.add(run)
    db_session.flush()

    with pytest.raises(RuntimeError, match="já está em execução"):
        resume_opa_import_run(
            db_session,
            FakeOpaClient([]),
            run_id=run.id,
            imported_by=None,
        )


def test_import_opa_attendances_accepts_real_opa_field_names(db_session):
    client = FakeOpaClient(
        [
            {
                "_id": "real-1",
                "id_cliente": "cliente-1",
                "id_atendente": "atendente-1",
                "setor": "suporte",
                "status": "F",
                "protocolo": "UNI202611",
                "date": "2026-08-16T20:43:34.885Z",
                "fim": "2026-08-16T20:48:41.135Z",
                "evaluations": [{"likert": {"rating": 5}}],
            }
        ]
    )

    result = import_opa_attendances(
        db_session,
        client,
        date_from=date(2026, 8, 16),
        date_to=date(2026, 8, 16),
        imported_by=None,
    )

    attendance = db_session.scalar(select(SupportOpaAttendance).where(SupportOpaAttendance.source_id == "real-1"))
    assert result["created_count"] == 1
    assert result["rejected_count"] == 0
    assert attendance is not None
    assert attendance.protocol == "UNI202611"
    assert attendance.rating == 5
    assert attendance.opened_at.date() == date(2026, 8, 16)
    assert attendance.tma_seconds == 306


def test_import_opa_attendances_enriches_real_opa_ids_from_dimensions(db_session):
    client = FakeOpaClient(
        [
            {
                "_id": "real-2",
                "id_cliente": "C-1",
                "id_atendente": "U-1",
                "setor": "D-1",
                "motivos": [{"idMotivo": "R-1"}],
                "status": "F",
                "date": "2026-08-16T20:00:00.000Z",
                "fim": "2026-08-16T20:05:00.000Z",
            }
        ],
        users=[{"_id": "U-1", "nome": "Ana Suporte"}],
        reasons=[{"_id": "R-1", "motivo": "2 via de boleto"}],
        departments=[{"_id": "D-1", "nome": "Central de Suporte"}],
        clients=[{"_id": "C-1", "nome": "Cliente Resolvido"}],
    )

    result = import_opa_attendances(
        db_session,
        client,
        date_from=date(2026, 8, 16),
        date_to=date(2026, 8, 16),
        imported_by=None,
    )

    attendance = db_session.scalar(select(SupportOpaAttendance).where(SupportOpaAttendance.source_id == "real-2"))
    assert result["created_count"] == 1
    assert result["rejected_count"] == 0
    assert attendance is not None
    assert attendance.attendant_name == "Ana Suporte"
    assert attendance.department_name == "Central de Suporte"
    assert attendance.reason_name == "2 via de boleto"
    assert attendance.customer_name == "Cliente Resolvido"
    assert attendance.tma_seconds == 300


def test_import_opa_attendances_backfills_existing_customer_names_from_dimensions(db_session):
    db_session.add(
        SupportOpaAttendance(
            source_id="existing-1",
            protocol="UNI-1",
            customer_id="C-2",
            customer_name=None,
            opened_at=datetime(2026, 8, 15, 9, 0, tzinfo=timezone.utc),
            raw_payload={"id": "existing-1"},
        )
    )
    db_session.flush()

    client = FakeOpaClient(
        [_record(id="new-1", cliente={"id": "C-3"})],
        clients=[
            {"_id": "C-2", "fantasia": "Cliente Antigo"},
            {"_id": "C-3", "nome": "Cliente Novo"},
        ],
    )

    import_opa_attendances(
        db_session,
        client,
        date_from=date(2026, 8, 15),
        date_to=date(2026, 8, 15),
        imported_by=None,
    )

    existing = db_session.scalar(select(SupportOpaAttendance).where(SupportOpaAttendance.source_id == "existing-1"))
    created = db_session.scalar(select(SupportOpaAttendance).where(SupportOpaAttendance.source_id == "new-1"))
    assert existing is not None
    assert created is not None
    assert existing.customer_name == "Cliente Antigo"
    assert created.customer_name == "Cliente Novo"


def test_import_opa_attendances_rejects_records_outside_requested_period(db_session):
    client = FakeOpaClient(
        [
            {
                "_id": "outside-1",
                "date": "2026-01-28T20:43:34.885Z",
                "fim": "2026-01-28T20:48:41.135Z",
            }
        ]
    )

    result = import_opa_attendances(
        db_session,
        client,
        date_from=date(2026, 8, 16),
        date_to=date(2026, 8, 16),
        imported_by=None,
    )

    assert result["created_count"] == 0
    assert result["rejected_count"] == 1
    assert "fora do período" in result["errors"][0]["reason"]


def test_import_opa_attendances_updates_existing_record(db_session):
    initial = FakeOpaClient([_record()])
    changed = FakeOpaClient([_record(atendente={"id": "A-1", "nome": "Atendente Corrigido"})])

    import_opa_attendances(
        db_session,
        initial,
        date_from=date(2026, 8, 15),
        date_to=date(2026, 8, 15),
        imported_by=None,
    )
    result = import_opa_attendances(
        db_session,
        changed,
        date_from=date(2026, 8, 15),
        date_to=date(2026, 8, 15),
        imported_by=None,
    )

    attendance = db_session.scalar(select(SupportOpaAttendance))
    assert result["updated_count"] == 1
    assert attendance.attendant_name == "Atendente Corrigido"


def test_opa_metrics_summarizes_imported_attendances(db_session, admin_user):
    client = FakeOpaClient([
        _record(id="OPA-1", atendente={"id": "A-1", "nome": "Ana"}, motivo={"id": "M-1", "nome": "Suporte"}, tma_seconds=600),
        _record(id="OPA-2", atendente={"id": "A-2", "nome": "Bruno"}, motivo={"id": "M-1", "nome": "Suporte"}, tma_seconds=300),
    ])
    import_opa_attendances(
        db_session,
        client,
        date_from=date(2026, 8, 15),
        date_to=date(2026, 8, 15),
        imported_by=None,
    )

    result = opa_metrics(date_from=date(2026, 8, 15), date_to=date(2026, 8, 15), db=db_session, user=admin_user)

    assert result["total_attendances"] == 2
    assert result["closed_attendances"] == 2
    assert result["average_tma_seconds"] == 450
    assert result["by_reason"][0]["label"] == "Suporte"
    assert result["by_reason"][0]["total"] == 2
