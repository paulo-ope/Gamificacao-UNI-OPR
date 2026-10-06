from __future__ import annotations

from datetime import date, datetime, timezone

from app.modules.support import ixc_n1
from app.modules.support.ixc_ticket_ingestion import import_tickets_for_period
from app.modules.support.models import SupportIxcTicket, SupportIxcUser

from tests.test_ixc_ticket_ingestion import FakeIxcClient, _cidade, _cliente, _ticket


def _user(db, user_id, *, group_id="105", name=None, active=True):
    db.add(SupportIxcUser(ixc_user_id=user_id, name=name or f"Usuário {user_id}", group_id=group_id, active=active))


def _n1_ticket(db, source_id, *, subject_id, opened_by, day=1, month=9):
    db.add(
        SupportIxcTicket(
            source_id=source_id,
            subject_id=subject_id,
            opened_by_user_id=opened_by,
            created_at=datetime(2026, month, day, 10, tzinfo=timezone.utc),
        )
    )


def test_summary_counts_only_n1_groups_and_n1_subjects(db_session):
    _user(db_session, "10", name="Ana N1")
    _user(db_session, "11", name="Bruno N1", active=False)
    _user(db_session, "30", group_id="117", name="Maycon 117")  # grupo 117 também entra
    _user(db_session, "20", group_id="32", name="Fora do N1")
    _n1_ticket(db_session, "T1", subject_id="90", opened_by="10")
    _n1_ticket(db_session, "T2", subject_id="90", opened_by="10", day=2)
    _n1_ticket(db_session, "T3", subject_id="29", opened_by="10")
    _n1_ticket(db_session, "T4", subject_id="29", opened_by="11")
    _n1_ticket(db_session, "T9", subject_id="90", opened_by="30", day=3)
    _n1_ticket(db_session, "T10", subject_id="29", opened_by="30", day=3)
    _n1_ticket(db_session, "T5", subject_id="90", opened_by="20")  # outro grupo
    _n1_ticket(db_session, "T6", subject_id="90", opened_by=None)  # sem operador
    _n1_ticket(db_session, "T7", subject_id="80", opened_by="10")  # motivo fora do N1
    _n1_ticket(db_session, "T8", subject_id="90", opened_by="10", month=7)  # fora do período
    db_session.commit()

    summary = ixc_n1.n1_summary(db_session, date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))

    assert summary["operational"] == 3
    assert summary["financial"] == 3
    assert summary["total"] == 6
    assert summary["group_ids"] == ["105", "117"]
    # Um ponto por dia do período (30), inclusive os dias sem protocolo.
    assert len(summary["daily"]) == 30
    assert [(row["day"], row["operational"], row["financial"]) for row in summary["daily"] if row["operational"] or row["financial"]] == [
        (date(2026, 9, 1), 1, 2),
        (date(2026, 9, 2), 1, 0),
        (date(2026, 9, 3), 1, 1),
    ]
    by_name = {row["name"]: row for row in summary["attendants"]}
    assert set(by_name) == {"Ana N1", "Bruno N1", "Maycon 117"}
    assert by_name["Ana N1"]["total"] == 3 and by_name["Ana N1"]["active"] is True
    assert by_name["Bruno N1"]["financial"] == 1 and by_name["Bruno N1"]["active"] is False
    assert by_name["Maycon 117"]["operational"] == 1 and by_name["Maycon 117"]["financial"] == 1
    assert [row["name"] for row in summary["attendants"]] == ["Ana N1", "Maycon 117", "Bruno N1"]


def test_summary_reports_previous_period_totals(db_session):
    _user(db_session, "10")
    _n1_ticket(db_session, "T1", subject_id="90", opened_by="10", day=20, month=8)
    _n1_ticket(db_session, "T2", subject_id="29", opened_by="10", day=21, month=8)
    _n1_ticket(db_session, "T3", subject_id="90", opened_by="10", day=5)
    db_session.commit()

    # Período de 30 dias (01 a 30/09) -> anterior = 02 a 31/08.
    summary = ixc_n1.n1_summary(db_session, date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))

    assert (summary["operational"], summary["financial"]) == (1, 0)
    assert (summary["previous_operational"], summary["previous_financial"]) == (1, 1)


def test_summary_previous_daily_is_zero_filled_and_aligned_with_current_period(db_session):
    _user(db_session, "10")
    _n1_ticket(db_session, "T1", subject_id="90", opened_by="10", day=20, month=8)
    _n1_ticket(db_session, "T2", subject_id="29", opened_by="10", day=22, month=8)
    _n1_ticket(db_session, "T3", subject_id="90", opened_by="10", day=3)
    db_session.commit()

    # 01 a 05/09 (5 dias) -> período anterior = 27/08 a 31/08, sem protocolo do N1 ali.
    short = ixc_n1.n1_summary(db_session, date_from=date(2026, 9, 1), date_to=date(2026, 9, 5))
    assert len(short["daily"]) == len(short["previous_daily"]) == 5
    assert short["previous_daily"][0]["day"] == date(2026, 8, 27)
    assert all(p["operational"] == 0 and p["financial"] == 0 for p in short["previous_daily"])

    # 21 a 25/08 -> anterior = 16 a 20/08 (T1 em 20/08); o T2 de 22/08 entra no período atual.
    shifted = ixc_n1.n1_summary(db_session, date_from=date(2026, 8, 21), date_to=date(2026, 8, 25))
    assert [(p["day"].day, p["operational"]) for p in shifted["previous_daily"]] == [(16, 0), (17, 0), (18, 0), (19, 0), (20, 1)]
    assert [(d["day"].day, d["financial"]) for d in shifted["daily"]] == [(21, 0), (22, 1), (23, 0), (24, 0), (25, 0)]


def test_summary_is_empty_without_n1_users(db_session):
    _n1_ticket(db_session, "T1", subject_id="90", opened_by="10")
    db_session.commit()

    summary = ixc_n1.n1_summary(db_session, date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))

    assert summary["total"] == 0 and summary["attendants"] == []
    assert all(p["operational"] == 0 and p["financial"] == 0 for p in summary["daily"])


def test_ingestion_stores_operator_and_syncs_ixc_users(db_session):
    client = FakeIxcClient(
        {
            "su_ticket": [
                _ticket(1, id_usuarios="961"),
                _ticket(2, id_usuarios="0"),  # sem operador
                _ticket(3, id_usuarios="999", id_assunto="29"),
            ],
            "cliente": [_cliente(500)],
            "cidade": [_cidade(60, "Cacoal")],
            "usuarios": [
                {"id": "961", "nome": "Eduardo Oliveira Leite", "id_grupo": "105", "status": "A"},
                {"id": "999", "nome": "Fora do N1", "id_grupo": "32", "status": "I"},
            ],
        }
    )

    import_tickets_for_period(db_session, client, created_after="2026-09-01 00:00:00", created_before="2026-09-30 23:59:59")

    operators = {
        t.source_id: t.opened_by_user_id for t in db_session.query(SupportIxcTicket).all()
    }
    assert operators == {"1": "961", "2": None, "3": "999"}
    users = {u.ixc_user_id: u for u in db_session.query(SupportIxcUser).all()}
    assert set(users) == {"961", "999"}
    assert users["961"].group_id == "105" and users["961"].active is True
    assert users["999"].group_id == "32" and users["999"].active is False

    summary = ixc_n1.n1_summary(db_session, date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))
    assert (summary["operational"], summary["financial"]) == (1, 0)
    assert [row["name"] for row in summary["attendants"]] == ["Eduardo Oliveira Leite"]


def test_sync_resolves_historical_operators_without_user_row(db_session):
    # Histórico retroalimentado pela migração: ticket com operador, mas sem linha em support_ixc_users.
    _n1_ticket(db_session, "T1", subject_id="90", opened_by="961")
    db_session.commit()
    client = FakeIxcClient({"usuarios": [{"id": "961", "nome": "Eduardo", "id_grupo": "105", "status": "A"}]})

    written = ixc_n1.sync_ixc_users(db_session, client)

    assert written == 1
    summary = ixc_n1.n1_summary(db_session, date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))
    assert summary["operational"] == 1


def test_n1_summary_endpoint_validates_period_and_returns_payload(db_session, client):
    _user(db_session, "10", name="Ana N1")
    _n1_ticket(db_session, "T1", subject_id="29", opened_by="10")
    db_session.commit()

    ok = client.get("/api/support/ixc/n1/summary", params={"date_from": "2026-09-01", "date_to": "2026-09-30"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["financial"] == 1 and body["operational"] == 0
    assert body["daily"][0]["day"] == "2026-09-01"
    assert body["attendants"][0]["name"] == "Ana N1"

    inverted = client.get("/api/support/ixc/n1/summary", params={"date_from": "2026-09-30", "date_to": "2026-09-01"})
    assert inverted.status_code == 400
    too_long = client.get("/api/support/ixc/n1/summary", params={"date_from": "2024-01-01", "date_to": "2026-09-01"})
    assert too_long.status_code == 400
