from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import func, select

from app.modules.support.models import SupportOpaAttendance, SupportOpaAttendanceRaw, SupportOpaImportRun
from app.modules.support.opa_ingestion import (
    OpaImportInterrupted,
    _opa_import_busy_message,
    active_opa_import_run,
    import_opa_attendances,
    opa_import_lock_busy,
    resume_opa_import_run,
)
from app.modules.support.router import opa_metrics, opa_sync_status
from app.services.opa_client import OpaPage


class FakeOpaClient:
    def __init__(
        self,
        records,
        users=None,
        reasons=None,
        departments=None,
        tags=None,
        clients=None,
        fail_on_skip=None,
        transient_failures=None,
        messages=None,
    ):
        self.records = records
        self.users = users or []
        self.reasons = reasons or []
        self.departments = departments or []
        self.tags = tags or []
        self.clients = clients or []
        self.fail_on_skip = set(fail_on_skip or [])
        self.transient_failures = dict(transient_failures or {})
        self.messages = messages or {}
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

    def list_messages(self, source_id):
        return self.messages.get(source_id, [])


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


def test_import_computes_human_tmr_first_response_and_bot_human_handoff(db_session):
    record = _record(
        id="OPA-HANDOFF",
        atendente={"id": "A-1", "nome": "Atendente Um"},
        data_abertura="2026-08-20T10:00:00+00:00",
        data_encerramento="2026-08-20T10:30:00+00:00",
    )
    messages = [
        {"id_atend": "BOT-1", "data": "2026-08-20T10:00:05+00:00"},
        {"id_user": "U-1", "data": "2026-08-20T10:00:10+00:00"},
        {"id_atend": "BOT-1", "data": "2026-08-20T10:00:15+00:00"},
        {"id_user": "U-1", "data": "2026-08-20T10:05:00+00:00"},
        {"id_atend": "A-1", "data": "2026-08-20T10:10:00+00:00"},
        {"id_user": "U-1", "data": "2026-08-20T10:15:00+00:00"},
        {"id_atend": "A-1", "data": "2026-08-20T10:20:00+00:00"},
    ]
    client = FakeOpaClient(
        [record],
        users=[
            {"_id": "A-1", "nome": "Atendente Um", "tipo": "user"},
            {"_id": "BOT-1", "nome": "Bot", "tipo": "bot"},
        ],
        messages={"OPA-HANDOFF": messages},
    )

    import_opa_attendances(
        db_session,
        client,
        date_from=date(2026, 8, 20),
        date_to=date(2026, 8, 20),
        imported_by=None,
    )

    attendance = db_session.scalar(select(SupportOpaAttendance).where(SupportOpaAttendance.source_id == "OPA-HANDOFF"))
    assert attendance is not None
    # gaps humanos: 10:00:10->10:10:00 (590s, ignora a 2a msg de cliente antes da
    # resposta) e 10:15:00->10:20:00 (300s) -> media 445s. Mensagens do BOT-1 nao
    # entram no calculo (nem fecham, nem resetam o intervalo pendente).
    assert attendance.tmr_seconds == 445
    assert attendance.first_response_at is not None
    assert attendance.first_response_at.replace(tzinfo=None) == datetime(2026, 8, 20, 10, 10, 0)
    assert attendance.handled_by_bot is True
    assert attendance.reached_human is True
    assert attendance.bot_to_human_handoff is True
    # TMR geral conta a resposta rápida do bot também: gaps 5s (10:00:10->10:00:15,
    # bot), 300s (10:05:00->10:10:00, humano) e 300s (10:15:00->10:20:00, humano)
    # -> media 605/3 = 201,67 ~= 202. Deve ficar menor que o TMR humano (445),
    # exatamente porque o bot respondeu rápido antes do humano.
    assert attendance.tmr_all_responses_seconds == 202
    assert attendance.tmr_all_responses_seconds < attendance.tmr_seconds


def test_import_classifies_bot_only_attendance_without_handoff(db_session):
    record = _record(
        id="OPA-BOT-ONLY",
        data_abertura="2026-08-20T10:00:00+00:00",
        data_encerramento=None,
        tmr_seconds=None,
    )
    messages = [
        {"id_user": "U-1", "data": "2026-08-20T10:00:00+00:00"},
        {"id_atend": "BOT-1", "data": "2026-08-20T10:00:02+00:00"},
    ]
    client = FakeOpaClient(
        [record],
        users=[{"_id": "BOT-1", "nome": "Bot", "tipo": "bot"}],
        messages={"OPA-BOT-ONLY": messages},
    )

    import_opa_attendances(
        db_session, client, date_from=date(2026, 8, 20), date_to=date(2026, 8, 20), imported_by=None
    )

    attendance = db_session.scalar(select(SupportOpaAttendance).where(SupportOpaAttendance.source_id == "OPA-BOT-ONLY"))
    assert attendance.handled_by_bot is True
    assert attendance.reached_human is False
    assert attendance.bot_to_human_handoff is False
    # TMR humano fica None: nenhuma mensagem do BOT-1 conta como resposta humana.
    assert attendance.tmr_seconds is None
    # TMR geral, ao contrário, conta a resposta do bot: cliente 10:00:00 ->
    # bot 10:00:02 = 2s. Atendimento só-bot pode ter TMR geral preenchido com
    # TMR humano nulo.
    assert attendance.tmr_all_responses_seconds == 2


def test_import_leaves_bot_human_classification_null_without_message_data(db_session):
    client = FakeOpaClient([_record(id="OPA-SEM-MSG")])  # sem `messages`: list_messages devolve []

    import_opa_attendances(
        db_session, client, date_from=date(2026, 8, 15), date_to=date(2026, 8, 15), imported_by=None
    )

    attendance = db_session.scalar(select(SupportOpaAttendance).where(SupportOpaAttendance.source_id == "OPA-SEM-MSG"))
    assert attendance.handled_by_bot is None
    assert attendance.reached_human is None
    assert attendance.bot_to_human_handoff is None
    assert attendance.tmr_all_responses_seconds is None


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


def _running_run(**overrides) -> SupportOpaImportRun:
    base = {
        "provider": "opa",
        "entity": "attendance",
        "mode": "scheduled",
        "date_from": date(2026, 8, 25),
        "date_to": date(2026, 8, 25),
        "status": "running",
        "started_at": datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return SupportOpaImportRun(**base)


def test_active_opa_import_run_returns_none_when_nothing_running(db_session):
    assert active_opa_import_run(db_session) is None


def test_active_opa_import_run_ignores_finished_runs(db_session):
    db_session.add(_running_run(status="completed"))
    db_session.flush()

    assert active_opa_import_run(db_session) is None


def test_active_opa_import_run_returns_most_recent_running_row(db_session):
    db_session.add(_running_run(started_at=datetime(2026, 8, 25, 8, 0, tzinfo=timezone.utc)))
    newest = _running_run(mode="manual", started_at=datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc))
    db_session.add(newest)
    db_session.flush()

    active = active_opa_import_run(db_session)
    assert active is not None
    assert active.mode == "manual"


def test_opa_import_lock_busy_is_none_outside_postgres(db_session):
    # db_session de teste roda em SQLite — a checagem de lock não se aplica lá,
    # igual ao comportamento pré-existente do `_support_opa_import_lock`.
    assert opa_import_lock_busy(db_session) is None


def test_opa_import_busy_message_mentions_automatica_when_scheduled_run_is_active(db_session):
    db_session.add(_running_run(mode="scheduled"))
    db_session.flush()

    message = _opa_import_busy_message(db_session)
    assert "automática" in message
    assert "manual" in message


def test_opa_import_busy_message_is_generic_when_active_run_is_manual(db_session):
    db_session.add(_running_run(mode="manual"))
    db_session.flush()

    message = _opa_import_busy_message(db_session)
    assert "automática" not in message


def test_opa_import_busy_message_is_generic_without_any_active_run(db_session):
    message = _opa_import_busy_message(db_session)
    assert "automática" not in message
    assert "em andamento" in message


def test_opa_import_busy_message_uses_fallback_when_no_active_run_is_visible(db_session):
    # Lock ocupado mas nenhuma run "running" visível (ex.: corrida rara entre o lock
    # ser adquirido e a run ser commitada) — mensagem amigável específica, não a
    # genérica de "outra importação manual".
    message = _opa_import_busy_message(db_session)
    assert "ainda não pôde ser identificada" in message


def test_active_opa_import_run_is_visible_while_pages_are_still_being_fetched(db_session):
    """Reproduz o cenário relatado: durante uma importação real, outra consulta
    (`active_opa_import_run`, a mesma usada por `/opa-sync-status`) precisa enxergar a
    run como `running` — não só depois que tudo termina e a transação principal
    commita. Antes da correção, a run só existia dentro da transação em aberto de
    `import_opa_attendances` (via `db.flush()`, nunca commitada até o fim)."""
    seen = {}

    class ProbingClient(FakeOpaClient):
        def list_attendances(self, **kwargs):
            if not seen:
                active = active_opa_import_run(db_session)
                seen["found"] = active is not None
                seen["status"] = active.status if active else None
                seen["mode"] = active.mode if active else None
                seen["id"] = active.id if active else None
            return super().list_attendances(**kwargs)

    client = ProbingClient([_record(id="OPA-VISIVEL-1")])
    result = import_opa_attendances(
        db_session, client, date_from=date(2026, 8, 25), date_to=date(2026, 8, 25), imported_by=None
    )

    assert seen["found"] is True
    assert seen["status"] == "running"
    assert seen["mode"] == "scheduled"
    assert seen["id"] == result["run_id"]


def test_import_commits_the_running_run_before_fetching_the_first_page(db_session, monkeypatch):
    """Garante que a linha "running" é commitada ANTES do processamento longo (não só
    no fim) — a diferença exata entre o bug relatado e a correção. Sem isso, o commit
    só aconteceria depois de todas as páginas processadas, quando o chamador
    (`router.py`/`opa_scheduler.py`) commita a sessão inteira."""
    events: list[str] = []
    original_commit = db_session.commit

    def spy_commit():
        events.append("commit")
        return original_commit()

    monkeypatch.setattr(db_session, "commit", spy_commit)

    class ProbingClient(FakeOpaClient):
        def list_attendances(self, **kwargs):
            events.append("list_attendances")
            return super().list_attendances(**kwargs)

    client = ProbingClient([_record(id="OPA-ORDEM-1")])
    import_opa_attendances(
        db_session, client, date_from=date(2026, 8, 25), date_to=date(2026, 8, 25), imported_by=None
    )

    assert "commit" in events
    assert "list_attendances" in events
    assert events.index("commit") < events.index("list_attendances")


def test_active_opa_import_run_is_none_again_after_successful_completion(db_session):
    client = FakeOpaClient([_record(id="OPA-FIM-OK")])
    import_opa_attendances(
        db_session, client, date_from=date(2026, 8, 25), date_to=date(2026, 8, 25), imported_by=None
    )

    assert active_opa_import_run(db_session) is None


def test_active_opa_import_run_is_none_after_interrupted_run_even_if_caller_rolls_back(db_session, monkeypatch):
    """`_persist_run_terminal_status` grava o status final numa sessão à parte e já
    commitada — precisa sobreviver mesmo se o chamador reverter a sessão principal
    depois (o que o router faz pra qualquer exceção que não seja
    `OpaImportInterrupted`), senão a run fica presa em "running" pra sempre."""
    monkeypatch.setattr("app.modules.support.opa_ingestion.time.sleep", lambda _: None)
    records = [_record(id=f"OPA-{index}") for index in range(1, 351)]
    client = FakeOpaClient(records, fail_on_skip={300})

    with pytest.raises(OpaImportInterrupted):
        import_opa_attendances(
            db_session, client, date_from=date(2026, 8, 15), date_to=date(2026, 8, 15), imported_by=None
        )

    # Simula o `db.rollback()` que o router faria pra uma exceção não-Interrupted —
    # aqui só pra provar que o status final já está commitado numa sessão à parte,
    # independente do que a sessão principal faça depois.
    db_session.rollback()

    active = active_opa_import_run(db_session)
    assert active is None
    run = db_session.query(SupportOpaImportRun).filter_by(status="interrupted").one()
    assert run.pages_processed == 3


def test_opa_sync_status_endpoint_shows_active_run_during_execution(db_session, admin_user):
    seen = {}

    class ProbingClient(FakeOpaClient):
        def list_attendances(self, **kwargs):
            if not seen:
                seen.update(opa_sync_status(db=db_session, user=admin_user))
            return super().list_attendances(**kwargs)

    client = ProbingClient([_record(id="OPA-STATUS-1")])
    import_opa_attendances(
        db_session, client, date_from=date(2026, 8, 25), date_to=date(2026, 8, 25), imported_by=None
    )

    assert seen["sync_in_progress"] is True
    assert seen["active_run_mode"] == "scheduled"
    assert seen["active_run_id"] is not None
