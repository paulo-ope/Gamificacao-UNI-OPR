from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import event

from app.modules.support.models import SupportOpaAttendance
from app.modules.support import router as support_router
from app.modules.support.router import opa_attendance_detail, opa_attendances, opa_breakdowns, opa_overview


def _attendance(index: int, **overrides):
    opened_at = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc) + timedelta(hours=index)
    base = {
        "source_id": f"OPA-{index:04d}",
        "protocol": f"UNI2026{index:04d}",
        "customer_id": f"C-{index % 7}",
        "customer_name": f"Cliente {index % 7}",
        "attendant_id": f"A-{index % 3}",
        "attendant_name": ["Ana", "Bruno", "Carla"][index % 3],
        "department_id": f"D-{index % 2}",
        "department_name": ["Suporte", "Financeiro"][index % 2],
        "reason_id": f"R-{index % 4}",
        "reason_name": ["Informações", "Sem conexão", "Boleto", "Agendamento"][index % 4],
        "channel": ["whatsapp", "telefone"][index % 2],
        "channel_id": f"CH-{index % 2}",
        "channel_customer": f"559999000{index % 10}",
        "status": ["F", "A"][index % 2],
        "opened_at": opened_at,
        "closed_at": opened_at + timedelta(minutes=10),
        "rating": float((index % 5) + 1),
        "tma_seconds": 600 + index,
        "tmr_seconds": None,
        "raw_payload": {"index": index},
    }
    base.update(overrides)
    return SupportOpaAttendance(**base)


def _seed(db_session, total: int = 18):
    rows = [_attendance(index) for index in range(total)]
    db_session.add_all(rows)
    db_session.flush()
    return rows


def _list(db_session, admin_user, **kwargs):
    params = {
        "page": 1,
        "page_size": 50,
        "sort_by": "opened_at",
        "sort_dir": "desc",
        "db": db_session,
        "user": admin_user,
    }
    params.update(kwargs)
    return opa_attendances(**params)


def _overview(db_session, admin_user, **kwargs):
    params = {
        "date_from": datetime(2026, 8, 1).date(),
        "date_to": datetime(2026, 8, 1).date(),
        "status": None,
        "channel": None,
        "attendant_id": None,
        "department_id": None,
        "reason_id": None,
        "search": None,
        "db": db_session,
        "user": admin_user,
    }
    params.update(kwargs)
    return opa_overview(**params)


def _breakdowns(db_session, admin_user, **kwargs):
    params = {
        "dimension": "attendant",
        "sort_by": "total",
        "sort_dir": "desc",
        "limit": 20,
        "search": None,
        "date_from": None,
        "date_to": None,
        "status": None,
        "channel": None,
        "attendant_id": None,
        "attendant": None,
        "department_id": None,
        "department": None,
        "reason_id": None,
        "reason": None,
        "protocol": None,
        "customer": None,
        "db": db_session,
        "user": admin_user,
    }
    params.update(kwargs)
    return opa_breakdowns(**params)


def test_opa_attendances_paginates_and_reports_total(db_session, admin_user):
    _seed(db_session, 18)

    body = _list(db_session, admin_user, page=2, page_size=5, sort_dir="asc")

    assert body["page"] == 2
    assert body["page_size"] == 5
    assert body["total"] == 18
    assert body["total_pages"] == 4
    assert len(body["items"]) == 5
    assert body["items"][0]["source_id"] == "OPA-0005"


def test_opa_attendances_filters_by_period(db_session, admin_user):
    _seed(db_session, 10)

    body = _list(
        db_session,
        admin_user,
        date_from=datetime(2026, 8, 1).date(),
        date_to=datetime(2026, 8, 1).date(),
        page_size=50,
    )

    assert body["total"] == 10
    assert all(item["opened_at"].date() == datetime(2026, 8, 1).date() for item in body["items"])


def test_opa_attendances_filters_by_attendant(db_session, admin_user):
    _seed(db_session, 12)

    body = _list(db_session, admin_user, attendant_id="A-1", page_size=50)

    assert body["total"] == 4
    assert {item["attendant_id"] for item in body["items"]} == {"A-1"}


def test_opa_attendances_filters_by_channel(db_session, admin_user):
    _seed(db_session, 12)

    body = _list(db_session, admin_user, channel="whatsapp", page_size=50)

    assert body["total"] == 6
    assert {item["channel"] for item in body["items"]} == {"whatsapp"}


def test_opa_attendances_searches_by_protocol(db_session, admin_user):
    _seed(db_session, 8)

    body = _list(db_session, admin_user, search="UNI20260003")

    assert body["total"] == 1
    assert body["items"][0]["protocol"] == "UNI20260003"


def test_opa_attendances_sorts_server_side(db_session, admin_user):
    _seed(db_session, 6)

    body = _list(db_session, admin_user, sort_by="protocol", sort_dir="desc", page_size=3)

    assert [item["protocol"] for item in body["items"]] == ["UNI20260005", "UNI20260004", "UNI20260003"]


def test_opa_attendances_combines_filters(db_session, admin_user):
    _seed(db_session, 30)

    body = _list(
        db_session,
        admin_user,
        date_from=datetime(2026, 8, 1).date(),
        date_to=datetime(2026, 8, 2).date(),
        attendant_id="A-1",
        channel="telefone",
        status="A",
        page_size=100,
    )

    assert body["total"] > 0
    assert all(item["attendant_id"] == "A-1" and item["channel"] == "telefone" and item["status"] == "A" for item in body["items"])


def test_opa_attendances_page_out_of_range_returns_empty_items(db_session, admin_user):
    _seed(db_session, 7)

    body = _list(db_session, admin_user, page=9, page_size=5)

    assert body["total"] == 7
    assert body["total_pages"] == 2
    assert body["items"] == []


def test_opa_attendances_large_dataset_returns_only_requested_page(db_session, admin_user):
    _seed(db_session, 260)

    body = _list(db_session, admin_user, page=4, page_size=25, sort_dir="asc")

    assert body["total"] == 260
    assert body["total_pages"] == 11
    assert len(body["items"]) == 25
    assert body["items"][0]["source_id"] == "OPA-0075"


def test_opa_overview_filters_by_period(db_session, admin_user):
    db_session.add_all(
        [
            _attendance(1, opened_at=datetime(2026, 8, 1, 10, tzinfo=timezone.utc)),
            _attendance(2, opened_at=datetime(2026, 8, 2, 10, tzinfo=timezone.utc)),
        ]
    )
    db_session.flush()

    body = _overview(db_session, admin_user, date_from=datetime(2026, 8, 2).date(), date_to=datetime(2026, 8, 2).date())

    assert body["total_attendances"]["current"] == 1
    assert body["current_period"] == {"date_from": datetime(2026, 8, 2).date(), "date_to": datetime(2026, 8, 2).date()}


def test_opa_overview_filters_by_status_channel_attendant_department_and_combination(db_session, admin_user):
    db_session.add_all(
        [
            _attendance(1, status="F", channel="whatsapp", attendant_id="A-1", department_id="D-1"),
            _attendance(2, status="A", channel="whatsapp", attendant_id="A-1", department_id="D-1"),
            _attendance(3, status="F", channel="telefone", attendant_id="A-2", department_id="D-1"),
            _attendance(4, status="F", channel="whatsapp", attendant_id="A-1", department_id="D-2"),
        ]
    )
    db_session.flush()

    assert _overview(db_session, admin_user, status="F")["total_attendances"]["current"] == 3
    assert _overview(db_session, admin_user, channel="telefone")["total_attendances"]["current"] == 1
    assert _overview(db_session, admin_user, attendant_id="A-1")["total_attendances"]["current"] == 3
    assert _overview(db_session, admin_user, department_id="D-1")["total_attendances"]["current"] == 3

    combined = _overview(db_session, admin_user, status="F", channel="whatsapp", attendant_id="A-1", department_id="D-1")

    assert combined["total_attendances"]["current"] == 1


def test_opa_overview_filters_by_reason_and_search(db_session, admin_user):
    db_session.add_all(
        [
            _attendance(1, reason_id="R-1", protocol="PROTO-ALVO"),
            _attendance(2, reason_id="R-2", protocol="PROTO-OUTRO"),
        ]
    )
    db_session.flush()

    body = _overview(db_session, admin_user, reason_id="R-1", search="ALVO")

    assert body["total_attendances"]["current"] == 1


def test_opa_overview_totals_closed_rate_duration_rating_and_distincts(db_session, admin_user):
    opened = datetime(2026, 8, 1, 8, tzinfo=timezone.utc)
    db_session.add_all(
        [
            _attendance(1, opened_at=opened, closed_at=opened + timedelta(minutes=10), tma_seconds=600, rating=5, attendant_id="A-1", department_id="D-1", channel="whatsapp"),
            _attendance(2, opened_at=opened + timedelta(hours=1), closed_at=opened + timedelta(hours=1, minutes=20), tma_seconds=1200, rating=3, attendant_id="A-2", department_id="D-1", channel="telefone"),
            _attendance(3, opened_at=opened + timedelta(hours=2), closed_at=None, tma_seconds=None, rating=None, attendant_id="A-2", department_id="D-2", channel="whatsapp"),
        ]
    )
    db_session.flush()

    body = _overview(db_session, admin_user)

    assert body["total_attendances"]["current"] == 3
    assert body["closed_attendances"]["current"] == 2
    assert body["open_attendances"]["current"] == 1
    assert round(body["closure_rate"]["current"], 2) == 66.67
    assert body["average_duration_seconds"]["current"] == 900
    assert body["average_rating"]["current"] == 4
    assert body["distinct_attendants"]["current"] == 2
    assert body["distinct_departments"]["current"] == 2
    assert body["by_channel"] == [{"channel": "whatsapp", "total": 2}, {"channel": "telefone", "total": 1}]


def test_opa_overview_compares_with_previous_period(db_session, admin_user):
    db_session.add_all(
        [
            _attendance(1, opened_at=datetime(2026, 8, 1, 8, tzinfo=timezone.utc)),
            _attendance(2, opened_at=datetime(2026, 8, 1, 9, tzinfo=timezone.utc)),
            _attendance(3, opened_at=datetime(2026, 7, 31, 8, tzinfo=timezone.utc)),
        ]
    )
    db_session.flush()

    body = _overview(db_session, admin_user)

    assert body["previous_period"] == {"date_from": datetime(2026, 7, 31).date(), "date_to": datetime(2026, 7, 31).date()}
    assert body["total_attendances"] == {
        "current": 2,
        "previous": 1,
        "absolute_change": 1,
        "percentage_change": 100.0,
    }


def test_opa_overview_previous_period_without_data_and_division_by_zero(db_session, admin_user):
    db_session.add(_attendance(1, opened_at=datetime(2026, 8, 1, 8, tzinfo=timezone.utc)))
    db_session.flush()

    body = _overview(db_session, admin_user)

    assert body["total_attendances"]["previous"] == 0
    assert body["total_attendances"]["absolute_change"] == 1
    assert body["total_attendances"]["percentage_change"] is None

    empty = _overview(db_session, admin_user, date_from=datetime(2026, 8, 3).date(), date_to=datetime(2026, 8, 3).date())

    assert empty["total_attendances"]["current"] == 0
    assert empty["total_attendances"]["previous"] == 0
    assert empty["total_attendances"]["percentage_change"] == 0.0


def test_opa_overview_and_table_filters_use_same_universe(db_session, admin_user):
    _seed(db_session, 24)

    overview = _overview(db_session, admin_user, channel="telefone", attendant_id="A-1", status="A")
    table = _list(
        db_session,
        admin_user,
        date_from=datetime(2026, 8, 1).date(),
        date_to=datetime(2026, 8, 1).date(),
        channel="telefone",
        attendant_id="A-1",
        status="A",
        page_size=100,
    )

    assert overview["total_attendances"]["current"] == table["total"]


@pytest.mark.parametrize("dimension", ["attendant", "department", "reason", "channel", "status", "customer"])
def test_opa_breakdowns_support_all_validated_dimensions(db_session, admin_user, dimension):
    _seed(db_session, 18)

    body = _breakdowns(db_session, admin_user, dimension=dimension)

    assert body["dimension"] == dimension
    assert body["total"] == 18
    assert sum(item["total"] for item in body["items"]) == 18


def test_opa_breakdowns_return_closed_duration_rating_and_share(db_session, admin_user):
    opened = datetime(2026, 8, 1, 8, tzinfo=timezone.utc)
    db_session.add_all(
        [
            _attendance(1, attendant_id="A-1", attendant_name="Ana", closed_at=opened + timedelta(minutes=10), tma_seconds=600, rating=5),
            _attendance(2, attendant_id="A-1", attendant_name="Ana", closed_at=None, tma_seconds=None, rating=None),
            _attendance(3, attendant_id="A-2", attendant_name="Bruno", closed_at=opened + timedelta(minutes=20), tma_seconds=1200, rating=3),
        ]
    )
    db_session.flush()

    body = _breakdowns(db_session, admin_user, dimension="attendant")
    ana = next(item for item in body["items"] if item["id"] == "A-1")

    assert ana == {
        "id": "A-1",
        "label": "Ana",
        "total": 2,
        "closed": 1,
        "open": 1,
        "closure_rate": 50.0,
        "avg_duration_seconds": 600.0,
        "avg_rating": 5.0,
        "rating_count": 1,
        "share_percentage": pytest.approx(66.66666666666666),
        "previous_total": 0,
        "total_change": 2,
        "total_change_percentage": None,
        "previous_closure_rate": 0.0,
        "closure_rate_change_pp": 50.0,
        "previous_avg_duration_seconds": None,
        "avg_duration_change_percentage": None,
        "previous_avg_rating": None,
        "avg_rating_change": None,
    }


def test_opa_breakdowns_apply_global_filters_ordering_and_limit(db_session, admin_user):
    _seed(db_session, 24)

    body = _breakdowns(
        db_session,
        admin_user,
        dimension="department",
        date_from=datetime(2026, 8, 1).date(),
        date_to=datetime(2026, 8, 1).date(),
        status="F",
        channel="whatsapp",
        attendant_id="A-0",
        department_id="D-0",
        reason_id="R-0",
        search="UNI20260012",
        sort_by="label",
        sort_dir="asc",
        limit=1,
    )

    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["label"] == "Suporte"
    assert body["items"][0]["total"] == 1


def test_opa_breakdowns_returns_empty_items_for_empty_universe(db_session, admin_user):
    _seed(db_session, 3)

    body = _breakdowns(db_session, admin_user, dimension="customer", customer="inexistente")

    assert body == {"dimension": "customer", "total": 0, "items": []}


def test_opa_breakdowns_customer_uses_identifier_when_name_is_unavailable(db_session, admin_user):
    db_session.add(_attendance(1, customer_id="C-SEM-NOME", customer_name=None))
    db_session.flush()

    body = _breakdowns(db_session, admin_user, dimension="customer")

    assert body["items"] == [
        {
            "id": "C-SEM-NOME",
            "label": "C-SEM-NOME",
            "total": 1,
            "closed": 1,
            "open": 0,
            "closure_rate": 100.0,
            "avg_duration_seconds": 601.0,
            "avg_rating": 2.0,
            "rating_count": 1,
            "share_percentage": 100.0,
            "previous_total": 0,
            "total_change": 1,
            "total_change_percentage": None,
            "previous_closure_rate": 0.0,
            "closure_rate_change_pp": 100.0,
            "previous_avg_duration_seconds": None,
            "avg_duration_change_percentage": None,
            "previous_avg_rating": None,
            "avg_rating_change": None,
        }
    ]


def test_opa_breakdowns_compare_current_and_previous_periods(db_session, admin_user):
    current = datetime(2026, 8, 1, 8, tzinfo=timezone.utc)
    previous = datetime(2026, 7, 31, 8, tzinfo=timezone.utc)
    db_session.add_all(
        [
            _attendance(1, opened_at=current, attendant_id="A-1", attendant_name="Ana", channel="whatsapp", closed_at=current + timedelta(minutes=10), tma_seconds=600, rating=5),
            _attendance(2, opened_at=current + timedelta(hours=1), attendant_id="A-1", attendant_name="Ana", channel="whatsapp", closed_at=current + timedelta(minutes=20), tma_seconds=1200, rating=3),
            _attendance(3, opened_at=previous, attendant_id="A-1", attendant_name="Ana", channel="whatsapp", closed_at=previous + timedelta(minutes=20), tma_seconds=1200, rating=4),
            _attendance(4, opened_at=previous + timedelta(hours=1), attendant_id="A-1", attendant_name="Ana", channel="whatsapp", closed_at=None, tma_seconds=None, rating=2),
        ]
    )
    db_session.flush()

    body = _breakdowns(
        db_session,
        admin_user,
        dimension="attendant",
        date_from=current.date(),
        date_to=current.date(),
        channel="whatsapp",
        attendant_id="A-1",
    )

    item = body["items"][0]
    assert item["total"] == 2
    assert item["previous_total"] == 2
    assert item["total_change"] == 0
    assert item["total_change_percentage"] == 0.0
    assert item["closure_rate"] == 100.0
    assert item["previous_closure_rate"] == 50.0
    assert item["closure_rate_change_pp"] == 50.0
    assert item["avg_duration_seconds"] == 900.0
    assert item["previous_avg_duration_seconds"] == 1200.0
    assert item["avg_duration_change_percentage"] == -25.0
    assert item["avg_rating"] == 4.0
    assert item["previous_avg_rating"] == 3.0
    assert item["avg_rating_change"] == 1.0


def test_opa_breakdowns_handle_new_item_and_previous_period_without_data(db_session, admin_user):
    current = datetime(2026, 8, 1, 8, tzinfo=timezone.utc)
    db_session.add(_attendance(1, opened_at=current, attendant_id="A-NOVO", attendant_name="Novo", rating=5))
    db_session.flush()

    body = _breakdowns(
        db_session,
        admin_user,
        dimension="attendant",
        date_from=current.date(),
        date_to=current.date(),
    )

    item = body["items"][0]
    assert item["previous_total"] == 0
    assert item["total_change"] == 1
    assert item["total_change_percentage"] is None
    assert item["previous_closure_rate"] == 0.0
    assert item["closure_rate_change_pp"] == 100.0
    assert item["previous_avg_duration_seconds"] is None
    assert item["avg_duration_change_percentage"] is None
    assert item["previous_avg_rating"] is None
    assert item["avg_rating_change"] is None


def test_opa_breakdowns_use_constant_query_count_for_period_comparison(db_session, admin_user):
    current = datetime(2026, 8, 1, 8, tzinfo=timezone.utc)
    previous = datetime(2026, 7, 31, 8, tzinfo=timezone.utc)
    _seed(db_session, 40)
    db_session.add(_attendance(99, opened_at=previous))
    db_session.flush()
    statements = []

    def capture_statement(*args):
        statements.append(args[2])

    event.listen(db_session.bind, "before_cursor_execute", capture_statement)
    try:
        _breakdowns(
            db_session,
            admin_user,
            dimension="attendant",
            date_from=current.date(),
            date_to=current.date(),
        )
    finally:
        event.remove(db_session.bind, "before_cursor_execute", capture_statement)

    assert len(statements) == 3


def test_opa_attendance_detail_existing_local_record(db_session, admin_user):
    row = _attendance(
        1,
        raw_payload={
            "descricao": "Cliente sem conexão",
            "observacoes": "Retornar por WhatsApp",
            "motivos": [{"idMotivo": "R-1"}],
            "tags": [{"id_tag": "T-1"}],
        },
    )
    db_session.add(row)
    db_session.flush()

    body = opa_attendance_detail(row.id, include_external=False, db=db_session, user=admin_user)

    assert body["id"] == row.id
    assert body["local"]["protocol"] == row.protocol
    assert body["local"]["description"] == "Cliente sem conexão"
    assert body["local"]["observations"] == "Retornar por WhatsApp"
    assert body["external_detail_available"] is False


def test_opa_attendance_detail_missing_record(db_session, admin_user):
    with pytest.raises(HTTPException) as exc:
        opa_attendance_detail(999, include_external=False, db=db_session, user=admin_user)

    assert exc.value.status_code == 404


def test_opa_attendance_detail_returns_reasons_and_tags(db_session, admin_user):
    row = _attendance(
        2,
        reason_id="R-local",
        reason_name="Motivo local",
        raw_payload={
            "motivos": [{"idMotivo": {"_id": "R-remote", "motivo": "Sem conexão"}}],
            "tags": [{"id_tag": {"_id": "T-1", "nome": "Urgente"}}],
        },
    )
    db_session.add(row)
    db_session.flush()

    body = opa_attendance_detail(row.id, include_external=False, db=db_session, user=admin_user)

    assert body["local"]["reasons"] == [{"id": "R-remote", "name": "Sem conexão"}]
    assert body["local"]["tags"] == [{"id": "T-1", "name": "Urgente"}]


def test_opa_attendance_detail_handles_missing_optional_fields(db_session, admin_user):
    row = _attendance(
        3,
        protocol=None,
        customer_name=None,
        attendant_name=None,
        reason_id=None,
        reason_name=None,
        channel=None,
        closed_at=None,
        rating=None,
        tma_seconds=None,
        raw_payload={},
    )
    db_session.add(row)
    db_session.flush()

    body = opa_attendance_detail(row.id, include_external=False, db=db_session, user=admin_user)

    assert body["local"]["protocol"] is None
    assert body["local"]["customer_name"] is None
    assert body["local"]["duration_seconds"] is None
    assert body["local"]["reasons"] == []
    assert body["local"]["tags"] == []


def test_opa_attendance_detail_returns_duration(db_session, admin_user):
    opened_at = datetime(2026, 8, 16, 9, 0, tzinfo=timezone.utc)
    row = _attendance(4, opened_at=opened_at, closed_at=opened_at + timedelta(minutes=42), tma_seconds=None)
    db_session.add(row)
    db_session.flush()

    body = opa_attendance_detail(row.id, include_external=False, db=db_session, user=admin_user)

    assert body["local"]["duration_seconds"] == 2520


def test_opa_attendance_detail_enriches_from_external_detail(db_session, admin_user, monkeypatch):
    row = _attendance(5)
    db_session.add(row)
    db_session.flush()

    class Client:
        def get_attendance_detail(self, source_id):
            assert source_id == row.source_id
            return {
                "_id": row.source_id,
                "protocolo": "OPA-EXT",
                "id_cliente": {"_id": "C-EXT", "nome": "Cliente externo"},
                "id_atendente": {"_id": "A-EXT", "nome": "Atendente externo"},
                "setor": {"_id": "D-EXT", "nome": "N2"},
                "canal": "whatsapp",
                "canal_cliente": "55999999999",
                "status": "F",
                "date": "2026-08-16T09:00:00+00:00",
                "fim": "2026-08-16T09:30:00+00:00",
                "motivos": [{"idMotivo": {"_id": "R-EXT", "motivo": "Suporte"}}],
                "tags": [{"id_tag": {"_id": "T-EXT", "nome": "VIP"}}],
                "evaluations": [{"likert": {"rating": 5}}],
                "descricao": "Detalhe remoto",
                "observacoes": "Observação remota",
            }

    monkeypatch.setattr(support_router, "get_opa_client", lambda: Client())

    body = opa_attendance_detail(row.id, include_external=True, db=db_session, user=admin_user)

    assert body["external_detail_available"] is True
    assert body["enriched"]["protocol"] == "OPA-EXT"
    assert body["enriched"]["customer_name"] == "Cliente externo"
    assert body["enriched"]["duration_seconds"] == 1800
    assert body["enriched"]["reasons"] == [{"id": "R-EXT", "name": "Suporte"}]
    assert body["enriched"]["tags"] == [{"id": "T-EXT", "name": "VIP"}]
    assert row.customer_name == "Cliente externo"


def test_opa_attendance_detail_keeps_local_fallback_when_external_fails(db_session, admin_user, monkeypatch):
    row = _attendance(6)
    db_session.add(row)
    db_session.flush()

    class Client:
        def get_attendance_detail(self, source_id):
            raise RuntimeError("OPA fora")

    monkeypatch.setattr(support_router, "get_opa_client", lambda: Client())

    body = opa_attendance_detail(row.id, include_external=True, db=db_session, user=admin_user)

    assert body["local"]["source_id"] == row.source_id
    assert body["enriched"] is None
    assert body["external_detail_available"] is False
    assert "OPA fora" in body["external_detail_error"]
