"""TV do Agendamento: recorte fixo nos departamentos de agendamento do OPA e ranking com a equipe toda."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.modules.support import opa_tv_service
from app.modules.support.models import SupportOpaAttendance

NOW = datetime(2026, 10, 8, 18, 0, tzinfo=timezone.utc)  # 14:00 em America/Porto_Velho
OPENED = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


def _attendance(source_id: str, department_id: str, department_name: str, attendant_id: str, name: str) -> SupportOpaAttendance:
    return SupportOpaAttendance(
        source_id=source_id,
        protocol=f"UNI{source_id}",
        customer_id="C-1",
        customer_name="Cliente",
        attendant_id=attendant_id,
        attendant_name=name,
        department_id=department_id,
        department_name=department_name,
        channel="whatsapp",
        status="F",
        opened_at=OPENED,
        closed_at=OPENED + timedelta(minutes=10),
        rating=4.0,
        tmr_all_responses_seconds=60,
        raw_payload={},
    )


def _seed(db_session):
    db_session.add_all(
        [
            _attendance("1", "D-AG", "Agendamentos", "A-1", "Ana"),
            _attendance("2", "D-AG", "Agendamentos", "A-1", "Ana"),
            _attendance("3", "D-JPA", "(JPA) Agendamento", "A-2", "Bia"),
            _attendance("4", "D-SUP", "Suporte Técnico", "A-3", "Caio"),
        ]
    )
    db_session.flush()


def test_scheduling_departments_are_resolved_by_name(db_session):
    _seed(db_session)

    assert sorted(opa_tv_service.scheduling_department_ids(db_session)) == ["D-AG", "D-JPA"]


def test_scheduling_snapshot_ignores_other_departments_and_lists_every_attendant(db_session):
    _seed(db_session)

    snapshot = opa_tv_service.build_snapshot(db_session, now=NOW, scope="scheduling")

    assert snapshot["kpis"]["total_today"] == 3  # o atendimento do Suporte Técnico fica de fora
    assert [(item["name"], item["total"]) for item in snapshot["attendants"]] == [("Ana", 2), ("Bia", 1)]
    assert sorted(snapshot["department_filter"]["department_names"]) == ["(JPA) Agendamento", "Agendamentos"]


def test_scheduling_snapshot_without_any_scheduling_department_is_empty_not_everything(db_session):
    db_session.add(_attendance("4", "D-SUP", "Suporte Técnico", "A-3", "Caio"))
    db_session.flush()

    snapshot = opa_tv_service.build_snapshot(db_session, now=NOW, scope="scheduling")

    assert snapshot["kpis"]["total_today"] == 0
    assert snapshot["attendants"] == []
    assert snapshot["department_filter"]["department_names"] == []


def test_scheduling_queue_lists_waiting_customers_without_attendant_oldest_first(db_session):
    waiting = _attendance("Q1", "D-AG", "Agendamentos", "", "x")
    waiting.status, waiting.closed_at, waiting.attendant_id = "AG", None, None
    waiting.customer_name, waiting.opened_at = "ALINE DA SILVA", NOW - timedelta(minutes=12)
    newer = _attendance("Q2", "D-JPA", "(JPA) Agendamento", "", "x")
    newer.status, newer.closed_at, newer.attendant_id = "AG", None, None
    newer.customer_name, newer.opened_at = "Rodrigo", NOW - timedelta(minutes=3)
    # Não entram: já tem atendente, aguardando há mais de 24 h (dado parado do OPA) e outro departamento.
    taken = _attendance("Q3", "D-AG", "Agendamentos", "A-1", "Ana")
    taken.status, taken.closed_at, taken.opened_at = "AG", None, NOW - timedelta(minutes=1)
    stale = _attendance("Q4", "D-AG", "Agendamentos", "", "x")
    stale.status, stale.closed_at, stale.attendant_id, stale.opened_at = "AG", None, None, NOW - timedelta(days=3)
    other = _attendance("Q5", "D-SUP", "Suporte Técnico", "", "x")
    other.status, other.closed_at, other.attendant_id, other.opened_at = "AG", None, None, NOW - timedelta(minutes=5)
    db_session.add_all([waiting, newer, taken, stale, other])
    db_session.flush()

    queue = opa_tv_service.build_snapshot(db_session, now=NOW, scope="scheduling")["queue"]

    assert queue["total"] == 2
    assert queue["longest_wait_seconds"] == 12 * 60
    assert [(item["label"], item["wait_seconds"]) for item in queue["items"]] == [("Aline S.", 720), ("Rodrigo", 180)]


def test_support_snapshot_has_no_queue(db_session):
    assert opa_tv_service.build_snapshot(db_session, now=NOW)["queue"] is None


def test_scheduling_attendants_rank_by_conversations_in_progress_now(db_session):
    _seed(db_session)  # Ana 2 e Bia 1 hoje, todos encerrados
    for source_id, attendant, name in (("E1", "A-2", "Bia"), ("E2", "A-2", "Bia"), ("E3", "A-9", "Davi")):
        row = _attendance(source_id, "D-AG", "Agendamentos", attendant, name)
        row.status, row.closed_at = "EA", None
        db_session.add(row)
    stale = _attendance("E4", "D-AG", "Agendamentos", "A-1", "Ana")
    stale.status, stale.closed_at, stale.opened_at = "EA", None, NOW - timedelta(days=30)
    db_session.add(stale)
    db_session.flush()

    attendants = opa_tv_service.build_snapshot(db_session, now=NOW, scope="scheduling")["attendants"]

    assert [(item["name"], item["in_progress"]) for item in attendants] == [("Bia", 2), ("Davi", 1), ("Ana", 0)]


def test_support_attendants_also_rank_by_conversations_in_progress_now(db_session):
    _seed(db_session)
    open_row = _attendance("E1", "D-SUP", "Suporte Técnico", "A-3", "Caio")
    open_row.status, open_row.closed_at = "EA", None
    db_session.add(open_row)
    db_session.flush()

    attendants = opa_tv_service.build_snapshot(db_session, now=NOW)["attendants"]

    assert (attendants[0]["name"], attendants[0]["in_progress"]) == ("Caio", 1)


class _FakeOpa:
    """Responde só ao `GET /atendimento` com os registros combinados, sem tocar na rede."""

    def __init__(self, records):
        self.records = records

    def _get_with_body(self, path, *, json_body):
        return self.records

    @staticmethod
    def _extract_records(body):
        return body, None


def test_scheduling_queue_comes_live_from_opa_ignoring_stale_local_rows(db_session):
    opa_tv_service._queue_cache.update(at=0.0, key=None, records=None)
    stale = _attendance("OLDQ", "D-AG", "Agendamentos", "", "x")
    stale.status, stale.closed_at, stale.attendant_id, stale.opened_at = "AG", None, None, NOW - timedelta(minutes=30)
    db_session.add(stale)
    db_session.flush()
    live = [
        {"protocolo": "UNI1", "status": "AG", "id_cliente": "", "id_atendente": "", "date": (NOW - timedelta(minutes=4)).isoformat()},
        {"protocolo": "UNI2", "status": "AG", "id_cliente": "", "id_atendente": "A-1", "date": (NOW - timedelta(minutes=2)).isoformat()},
    ]

    queue = opa_tv_service.build_snapshot(db_session, now=NOW, scope="scheduling", opa_client=_FakeOpa(live))["queue"]

    assert queue["total"] == 1  # a linha local velha não vale; quem já tem atendente sai
    assert queue["items"] == [{"label": "Protocolo UNI1", "wait_seconds": 240}]
