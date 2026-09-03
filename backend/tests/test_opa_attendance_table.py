from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import event

from app.modules.support.models import SupportOpaAttendance, SupportOpaDimension
from app.modules.support import opa_timeline_service
from app.modules.support import router as support_router
from app.modules.support.router import (
    OpaExtraFilters,
    opa_attendance_detail,
    opa_attendance_timeline,
    opa_attendances,
    opa_attendant_summary,
    opa_breakdowns,
    opa_overview,
    opa_timeseries,
)


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
        # As rotas recebem os filtros adicionais por `Depends(OpaExtraFilters)`;
        # chamadas direto (sem FastAPI) precisam montar o objeto na mão.
        "extra": OpaExtraFilters(),
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
        # As rotas recebem os filtros adicionais por `Depends(OpaExtraFilters)`;
        # chamadas direto (sem FastAPI) precisam montar o objeto na mão.
        "extra": OpaExtraFilters(),
    }
    params.update(kwargs)
    return opa_overview(**params)


def _attendant_summary(db_session, admin_user, attendant_id, **kwargs):
    params = {
        "date_from": None,
        "date_to": None,
        "status": None,
        "channel": None,
        "department_id": None,
        "reason_id": None,
        "customer": None,
        "search": None,
        "db": db_session,
        "user": admin_user,
        # As rotas recebem os filtros adicionais por `Depends(OpaExtraFilters)`;
        # chamadas direto (sem FastAPI) precisam montar o objeto na mão.
        "extra": OpaExtraFilters(),
    }
    params.update(kwargs)
    return opa_attendant_summary(attendant_id, **params)


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
        # As rotas recebem os filtros adicionais por `Depends(OpaExtraFilters)`;
        # chamadas direto (sem FastAPI) precisam montar o objeto na mão.
        "extra": OpaExtraFilters(),
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


def test_opa_attendances_date_basis_opened_at_is_default_and_ignores_closed_at(db_session, admin_user):
    # Aberto 24/08, encerrado 25/08 — com date_basis padrão (abertura), só
    # aparece filtrando 24/08; filtrar 25/08 não deve trazer nada, exatamente
    # o comportamento atual preservado (critério de aceite).
    row = _attendance(
        1,
        opened_at=datetime(2026, 8, 24, 22, tzinfo=timezone.utc),
        closed_at=datetime(2026, 8, 25, 18, tzinfo=timezone.utc),
    )
    db_session.add(row)
    db_session.flush()

    on_open_day = _list(db_session, admin_user, date_from=date(2026, 8, 24), date_to=date(2026, 8, 24))
    on_close_day = _list(db_session, admin_user, date_from=date(2026, 8, 25), date_to=date(2026, 8, 25))

    assert on_open_day["total"] == 1
    assert on_close_day["total"] == 0


def test_opa_attendances_date_basis_closed_at_finds_attendance_by_closing_day(db_session, admin_user):
    row = _attendance(
        1,
        opened_at=datetime(2026, 8, 24, 22, tzinfo=timezone.utc),
        closed_at=datetime(2026, 8, 25, 18, tzinfo=timezone.utc),
    )
    db_session.add(row)
    db_session.flush()

    on_close_day = _list(
        db_session, admin_user, date_from=date(2026, 8, 25), date_to=date(2026, 8, 25), date_basis="closed_at"
    )
    on_open_day = _list(
        db_session, admin_user, date_from=date(2026, 8, 24), date_to=date(2026, 8, 24), date_basis="closed_at"
    )

    assert on_close_day["total"] == 1
    assert on_close_day["items"][0]["id"] == row.id
    # No dia de abertura, com date_basis=closed_at, não aparece (ainda não
    # tinha encerrado nesse dia).
    assert on_open_day["total"] == 0


def test_opa_attendances_date_basis_closed_at_excludes_still_open_attendances(db_session, admin_user):
    row = _attendance(1, opened_at=datetime(2026, 8, 25, 8, tzinfo=timezone.utc), closed_at=None)
    db_session.add(row)
    db_session.flush()

    body = _list(
        db_session, admin_user, date_from=date(2026, 8, 25), date_to=date(2026, 8, 25), date_basis="closed_at"
    )

    assert body["total"] == 0


def test_opa_overview_date_basis_closed_at_counts_attendance_on_closing_day(db_session, admin_user):
    row = _attendance(
        1,
        opened_at=datetime(2026, 8, 24, 22, tzinfo=timezone.utc),
        closed_at=datetime(2026, 8, 25, 18, tzinfo=timezone.utc),
    )
    db_session.add(row)
    db_session.flush()

    by_open = _overview(db_session, admin_user, date_from=date(2026, 8, 25), date_to=date(2026, 8, 25))
    by_close = _overview(
        db_session, admin_user, date_from=date(2026, 8, 25), date_to=date(2026, 8, 25), date_basis="closed_at"
    )

    assert by_open["total_attendances"]["current"] == 0
    assert by_close["total_attendances"]["current"] == 1


def test_opa_attendant_summary_date_basis_closed_at_counts_attendance_on_closing_day(db_session, admin_user):
    row = _attendance(
        1,
        attendant_id="A-1",
        opened_at=datetime(2026, 8, 24, 22, tzinfo=timezone.utc),
        closed_at=datetime(2026, 8, 25, 18, tzinfo=timezone.utc),
    )
    db_session.add(row)
    db_session.flush()

    by_open = _attendant_summary(db_session, admin_user, "A-1", date_from=date(2026, 8, 25), date_to=date(2026, 8, 25))
    by_close = _attendant_summary(
        db_session, admin_user, "A-1", date_from=date(2026, 8, 25), date_to=date(2026, 8, 25), date_basis="closed_at"
    )

    assert by_open["total_attendances"] == 0
    assert by_close["total_attendances"] == 1


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


def test_opa_overview_reports_status_breakdown(db_session, admin_user):
    db_session.add_all(
        [
            _attendance(1, status="F"),
            _attendance(2, status="F"),
            _attendance(3, status="AG"),
        ]
    )
    db_session.flush()

    body = _overview(db_session, admin_user)

    assert {item["status"]: item["total"] for item in body["by_status"]} == {"F": 2, "AG": 1}


def test_opa_overview_reports_unique_and_recurring_customers(db_session, admin_user):
    db_session.add_all(
        [
            _attendance(1, customer_id="C-1", customer_name="Cliente Um"),
            _attendance(2, customer_id="C-1", customer_name="Cliente Um"),
            _attendance(3, customer_id="C-2", customer_name="Cliente Dois"),
        ]
    )
    db_session.flush()

    body = _overview(db_session, admin_user)

    customers = body["customers"]
    assert customers["unique_customers"] == 2
    assert customers["recurring_customers"] == 1
    assert customers["recurring_customers_percentage"] == 50.0
    assert customers["top_recurring_customers"][0]["customer_id"] == "C-1"
    assert customers["top_recurring_customers"][0]["total"] == 2


def test_opa_overview_reports_top_reasons_with_tma_and_tmr(db_session, admin_user):
    opened = datetime(2026, 8, 1, 8, tzinfo=timezone.utc)
    db_session.add_all(
        [
            _attendance(1, reason_name="Sem conexão", closed_at=opened + timedelta(minutes=10), tma_seconds=600, tmr_seconds=100),
            _attendance(2, reason_name="Sem conexão", closed_at=opened + timedelta(minutes=20), tma_seconds=1200, tmr_seconds=200),
            _attendance(3, reason_name="Boleto", closed_at=opened + timedelta(minutes=5), tma_seconds=300, tmr_seconds=50),
        ]
    )
    db_session.flush()

    body = _overview(db_session, admin_user)

    top = body["top_reasons"][0]
    assert top["label"] == "Sem conexão"
    assert top["total"] == 2
    assert top["average_tma_seconds"] == 900
    assert top["average_tmr_seconds"] == 150


def test_opa_overview_reports_average_first_response_seconds(db_session, admin_user):
    opened = datetime(2026, 8, 1, 8, tzinfo=timezone.utc)
    db_session.add_all(
        [
            _attendance(1, opened_at=opened, first_response_at=opened + timedelta(minutes=5)),
            _attendance(2, opened_at=opened, first_response_at=opened + timedelta(minutes=15)),
            _attendance(3, opened_at=opened, first_response_at=None),
        ]
    )
    db_session.flush()

    body = _overview(db_session, admin_user)

    assert body["average_first_response_seconds"] == 600.0


def test_opa_overview_bot_human_percentages_use_classified_denominator_only(db_session, admin_user):
    db_session.add_all(
        [
            _attendance(1, handled_by_bot=True, reached_human=True, bot_to_human_handoff=True),
            _attendance(2, handled_by_bot=False, reached_human=True, bot_to_human_handoff=False),
            _attendance(3, handled_by_bot=None, reached_human=None, bot_to_human_handoff=None),
        ]
    )
    db_session.flush()

    body = _overview(db_session, admin_user)
    bot_human = body["bot_human"]

    assert bot_human["total_attendances"] == 3
    assert bot_human["classified_attendances"] == 2
    assert bot_human["unclassified_attendances"] == 1
    assert bot_human["with_bot"] == 1
    assert bot_human["with_bot_percentage"] == 50.0
    assert bot_human["reached_human"] == 2
    assert bot_human["reached_human_percentage"] == 100.0
    assert bot_human["bot_to_human_handoff"] == 1
    assert bot_human["bot_to_human_handoff_percentage"] == 50.0


def test_opa_overview_average_tmr_seconds_compares_with_previous_period(db_session, admin_user):
    db_session.add_all(
        [
            _attendance(1, opened_at=datetime(2026, 8, 1, 8, tzinfo=timezone.utc), tmr_seconds=100),
            _attendance(2, opened_at=datetime(2026, 8, 1, 9, tzinfo=timezone.utc), tmr_seconds=300),
            _attendance(3, opened_at=datetime(2026, 7, 31, 8, tzinfo=timezone.utc), tmr_seconds=50),
        ]
    )
    db_session.flush()

    body = _overview(db_session, admin_user)

    assert body["average_tmr_seconds"]["current"] == 200.0
    assert body["average_tmr_seconds"]["previous"] == 50.0


def test_opa_overview_average_tmr_all_responses_seconds_compares_with_previous_period(db_session, admin_user):
    db_session.add_all(
        [
            _attendance(1, opened_at=datetime(2026, 8, 1, 8, tzinfo=timezone.utc), tmr_seconds=100, tmr_all_responses_seconds=20),
            _attendance(2, opened_at=datetime(2026, 8, 1, 9, tzinfo=timezone.utc), tmr_seconds=300, tmr_all_responses_seconds=40),
            _attendance(3, opened_at=datetime(2026, 7, 31, 8, tzinfo=timezone.utc), tmr_seconds=50, tmr_all_responses_seconds=10),
        ]
    )
    db_session.flush()

    body = _overview(db_session, admin_user)

    # TMR geral e TMR humano coexistem e são independentes um do outro.
    assert body["average_tmr_all_responses_seconds"]["current"] == 30.0
    assert body["average_tmr_all_responses_seconds"]["previous"] == 10.0
    assert body["average_tmr_seconds"]["current"] == 200.0


def test_opa_attendant_summary_and_top_reasons_expose_tmr_all_responses_seconds(db_session, admin_user):
    opened = datetime(2026, 8, 1, 8, tzinfo=timezone.utc)
    db_session.add_all(
        [
            _attendance(
                1,
                attendant_id="A-1",
                reason_name="Sem conexão",
                opened_at=opened,
                tmr_seconds=400,
                tmr_all_responses_seconds=50,
            ),
            _attendance(
                2,
                attendant_id="A-1",
                reason_name="Sem conexão",
                opened_at=opened,
                tmr_seconds=200,
                tmr_all_responses_seconds=30,
            ),
        ]
    )
    db_session.flush()

    summary = _attendant_summary(db_session, admin_user, "A-1")
    assert summary["average_tmr_seconds"] == 300.0
    assert summary["average_tmr_all_responses_seconds"] == 40.0

    overview = _overview(db_session, admin_user)
    top_reason = overview["top_reasons"][0]
    assert top_reason["label"] == "Sem conexão"
    assert top_reason["average_tmr_seconds"] == 300.0
    assert top_reason["average_tmr_all_responses_seconds"] == 40.0


def test_tmr_all_responses_coverage_reports_partial_history(db_session, admin_user):
    """Caso real da auditoria: parte do histórico ainda não tem TMR geral
    calculado (campo entrou em produção depois). A média (40.0) precisa
    continuar exatamente igual a antes - só o denominador é novo."""
    opened = datetime(2026, 8, 1, 8, tzinfo=timezone.utc)
    db_session.add_all(
        [
            _attendance(1, attendant_id="A-1", opened_at=opened, tmr_all_responses_seconds=50),
            _attendance(2, attendant_id="A-1", opened_at=opened, tmr_all_responses_seconds=30),
            # Histórico sem TMR geral (anterior à ativação do cálculo) - NULL,
            # nunca 0. Não pode entrar na média nem no numerador da cobertura.
            _attendance(3, attendant_id="A-1", opened_at=opened, tmr_all_responses_seconds=None),
            _attendance(4, attendant_id="A-1", opened_at=opened, tmr_all_responses_seconds=None),
        ]
    )
    db_session.flush()

    overview = _overview(db_session, admin_user)
    assert overview["average_tmr_all_responses_seconds"]["current"] == 40.0
    assert overview["tmr_all_responses_coverage"] == {"count": 2, "total": 4, "percentage": 50.0}

    summary = _attendant_summary(db_session, admin_user, "A-1")
    assert summary["average_tmr_all_responses_seconds"] == 40.0
    assert summary["tmr_all_responses_coverage"] == {"count": 2, "total": 4, "percentage": 50.0}

    top_reason = overview["top_reasons"][0]
    assert top_reason["tmr_all_responses_coverage"]["count"] <= top_reason["tmr_all_responses_coverage"]["total"]


def test_tmr_all_responses_coverage_is_zero_when_nothing_calculated(db_session, admin_user):
    opened = datetime(2026, 8, 1, 8, tzinfo=timezone.utc)
    db_session.add_all(
        [
            _attendance(1, attendant_id="A-1", opened_at=opened, tmr_all_responses_seconds=None),
            _attendance(2, attendant_id="A-1", opened_at=opened, tmr_all_responses_seconds=None),
        ]
    )
    db_session.flush()

    overview = _overview(db_session, admin_user)
    assert overview["average_tmr_all_responses_seconds"]["current"] is None
    assert overview["tmr_all_responses_coverage"] == {"count": 0, "total": 2, "percentage": 0.0}


def test_tmr_all_responses_coverage_is_full_when_everything_calculated(db_session, admin_user):
    opened = datetime(2026, 8, 1, 8, tzinfo=timezone.utc)
    db_session.add_all(
        [
            _attendance(1, attendant_id="A-1", opened_at=opened, tmr_all_responses_seconds=20),
            _attendance(2, attendant_id="A-1", opened_at=opened, tmr_all_responses_seconds=40),
        ]
    )
    db_session.flush()

    overview = _overview(db_session, admin_user)
    assert overview["average_tmr_all_responses_seconds"]["current"] == 30.0
    assert overview["tmr_all_responses_coverage"] == {"count": 2, "total": 2, "percentage": 100.0}


def test_tmr_all_responses_coverage_percentage_is_none_for_empty_universe(db_session, admin_user):
    overview = _overview(db_session, admin_user, date_from=date(2099, 1, 1), date_to=date(2099, 1, 1))
    assert overview["tmr_all_responses_coverage"] == {"count": 0, "total": 0, "percentage": None}


def test_tmr_humano_stays_independent_of_tmr_geral_coverage(db_session, admin_user):
    """TMR humano (tmr_seconds) não pode ser afetado pela cobertura parcial de
    TMR geral - são campos e denominadores independentes."""
    opened = datetime(2026, 8, 1, 8, tzinfo=timezone.utc)
    db_session.add_all(
        [
            _attendance(1, attendant_id="A-1", opened_at=opened, tmr_seconds=100, tmr_all_responses_seconds=None),
            _attendance(2, attendant_id="A-1", opened_at=opened, tmr_seconds=300, tmr_all_responses_seconds=None),
        ]
    )
    db_session.flush()

    overview = _overview(db_session, admin_user)
    assert overview["average_tmr_seconds"]["current"] == 200.0
    assert overview["average_tmr_all_responses_seconds"]["current"] is None
    assert overview["tmr_all_responses_coverage"] == {"count": 0, "total": 2, "percentage": 0.0}


def test_imported_data_window_reports_min_max_over_whole_base_ignoring_filters(db_session, admin_user):
    """`imported_data_window` é sobre a BASE INTEIRA, nunca sobre o recorte de
    filtros escolhido - por isso o teste passa um período (10/08) que não cobre
    o menor/maior opened_at real dos dados semeados (01/08 e 20/08) e ainda
    assim espera ver a janela completa."""
    db_session.add_all(
        [
            _attendance(1, opened_at=datetime(2026, 8, 1, 9, tzinfo=timezone.utc), closed_at=datetime(2026, 8, 1, 10, tzinfo=timezone.utc)),
            _attendance(2, opened_at=datetime(2026, 8, 10, 9, tzinfo=timezone.utc), closed_at=datetime(2026, 8, 10, 10, tzinfo=timezone.utc)),
            _attendance(3, opened_at=datetime(2026, 8, 20, 9, tzinfo=timezone.utc), closed_at=datetime(2026, 8, 20, 10, tzinfo=timezone.utc)),
        ]
    )
    db_session.flush()

    overview = _overview(db_session, admin_user, date_from=date(2026, 8, 10), date_to=date(2026, 8, 10))
    window = overview["imported_data_window"]
    assert window["total_attendances"] == 3
    assert window["min_opened_at"].date() == date(2026, 8, 1)
    assert window["max_opened_at"].date() == date(2026, 8, 20)
    assert window["min_closed_at"].date() == date(2026, 8, 1)
    assert window["max_closed_at"].date() == date(2026, 8, 20)
    # o recorte filtrado (10/08) só bate 1 atendimento - prova que a janela
    # acima não veio da mesma consulta filtrada.
    assert overview["total_attendances"]["current"] == 1


def test_imported_data_window_is_all_none_when_base_is_empty(db_session, admin_user):
    overview = _overview(db_session, admin_user)
    window = overview["imported_data_window"]
    assert window == {
        "min_opened_at": None,
        "max_opened_at": None,
        "min_closed_at": None,
        "max_closed_at": None,
        "total_attendances": 0,
    }


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


def test_opa_attendant_summary_returns_totals_and_rates(db_session, admin_user):
    opened = datetime(2026, 8, 1, 8, tzinfo=timezone.utc)
    db_session.add_all(
        [
            _attendance(1, attendant_id="A-1", attendant_name="Ana", closed_at=opened + timedelta(minutes=10), tma_seconds=600, rating=5),
            _attendance(2, attendant_id="A-1", attendant_name="Ana", closed_at=None, tma_seconds=None, rating=None),
            _attendance(3, attendant_id="A-2", attendant_name="Bruno", closed_at=opened + timedelta(minutes=20), tma_seconds=1200, rating=3),
        ]
    )
    db_session.flush()

    body = _attendant_summary(db_session, admin_user, "A-1")

    assert body["attendant_id"] == "A-1"
    assert body["attendant_name"] == "Ana"
    assert body["total_attendances"] == 2
    assert body["closed_attendances"] == 1
    assert body["open_attendances"] == 1
    assert body["closure_rate"] == 50.0
    assert body["average_tma_seconds"] == 600
    assert body["average_rating"] == 5
    assert body["rating_count"] == 1


def test_opa_attendant_summary_applies_global_filters(db_session, admin_user):
    db_session.add_all(
        [
            _attendance(1, attendant_id="A-1", status="F", channel="whatsapp", department_id="D-1", reason_id="R-1"),
            _attendance(2, attendant_id="A-1", status="A", channel="telefone", department_id="D-2", reason_id="R-2"),
            _attendance(3, attendant_id="A-2", status="F", channel="whatsapp", department_id="D-1", reason_id="R-1"),
        ]
    )
    db_session.flush()

    assert _attendant_summary(db_session, admin_user, "A-1", status="F")["total_attendances"] == 1
    assert _attendant_summary(db_session, admin_user, "A-1", channel="telefone")["total_attendances"] == 1
    assert _attendant_summary(db_session, admin_user, "A-1", department_id="D-1")["total_attendances"] == 1
    assert _attendant_summary(db_session, admin_user, "A-1", reason_id="R-2")["total_attendances"] == 1

    combined = _attendant_summary(
        db_session, admin_user, "A-1", status="F", channel="whatsapp", department_id="D-1", reason_id="R-1"
    )
    assert combined["total_attendances"] == 1


def test_opa_attendant_summary_filters_by_period_customer_and_search(db_session, admin_user):
    db_session.add_all(
        [
            _attendance(
                1,
                attendant_id="A-1",
                opened_at=datetime(2026, 8, 1, 8, tzinfo=timezone.utc),
                customer_id="C-1",
                customer_name="Cliente Um",
                protocol="PROTO-A",
            ),
            _attendance(
                2,
                attendant_id="A-1",
                opened_at=datetime(2026, 8, 2, 8, tzinfo=timezone.utc),
                customer_id="C-2",
                customer_name="Cliente Dois",
                protocol="PROTO-B",
            ),
        ]
    )
    db_session.flush()

    by_period = _attendant_summary(db_session, admin_user, "A-1", date_from=date(2026, 8, 1), date_to=date(2026, 8, 1))
    assert by_period["total_attendances"] == 1

    by_customer = _attendant_summary(db_session, admin_user, "A-1", customer="Cliente Dois")
    assert by_customer["total_attendances"] == 1

    by_search = _attendant_summary(db_session, admin_user, "A-1", search="PROTO-A")
    assert by_search["total_attendances"] == 1


def test_opa_attendant_summary_computes_tma_tmr_and_first_response(db_session, admin_user):
    opened = datetime(2026, 8, 1, 8, tzinfo=timezone.utc)
    db_session.add_all(
        [
            _attendance(
                1,
                attendant_id="A-1",
                opened_at=opened,
                closed_at=opened + timedelta(minutes=10),
                tma_seconds=600,
                tmr_seconds=100,
                first_response_at=opened + timedelta(minutes=2),
            ),
            _attendance(
                2,
                attendant_id="A-1",
                opened_at=opened,
                closed_at=opened + timedelta(minutes=20),
                tma_seconds=1200,
                tmr_seconds=300,
                first_response_at=opened + timedelta(minutes=8),
            ),
        ]
    )
    db_session.flush()

    body = _attendant_summary(db_session, admin_user, "A-1")

    assert body["average_tma_seconds"] == 900
    assert body["average_tmr_seconds"] == 200
    assert body["average_first_response_seconds"] == 300.0


def test_opa_attendant_summary_reports_unique_and_recurring_customers(db_session, admin_user):
    db_session.add_all(
        [
            _attendance(1, attendant_id="A-1", customer_id="C-1"),
            _attendance(2, attendant_id="A-1", customer_id="C-1"),
            _attendance(3, attendant_id="A-1", customer_id="C-2"),
        ]
    )
    db_session.flush()

    body = _attendant_summary(db_session, admin_user, "A-1")

    assert body["customers"]["unique_customers"] == 2
    assert body["customers"]["recurring_customers"] == 1


def test_opa_attendant_summary_reports_status_reason_and_channel_breakdown(db_session, admin_user):
    db_session.add_all(
        [
            _attendance(1, attendant_id="A-1", status="F", reason_name="Sem conexão", channel="whatsapp"),
            _attendance(2, attendant_id="A-1", status="F", reason_name="Sem conexão", channel="whatsapp"),
            _attendance(3, attendant_id="A-1", status="AG", reason_name="Boleto", channel="telefone"),
        ]
    )
    db_session.flush()

    body = _attendant_summary(db_session, admin_user, "A-1")

    assert {item["status"]: item["total"] for item in body["by_status"]} == {"F": 2, "AG": 1}
    assert {item["label"]: item["total"] for item in body["by_reason"]} == {"Sem conexão": 2, "Boleto": 1}
    assert {item["channel"]: item["total"] for item in body["by_channel"]} == {"whatsapp": 2, "telefone": 1}


def test_opa_attendant_summary_bot_human_uses_classified_denominator(db_session, admin_user):
    db_session.add_all(
        [
            _attendance(1, attendant_id="A-1", handled_by_bot=True, reached_human=True, bot_to_human_handoff=True),
            _attendance(2, attendant_id="A-1", handled_by_bot=False, reached_human=True, bot_to_human_handoff=False),
            _attendance(3, attendant_id="A-1", handled_by_bot=None, reached_human=None, bot_to_human_handoff=None),
        ]
    )
    db_session.flush()

    body = _attendant_summary(db_session, admin_user, "A-1")
    bot_human = body["bot_human"]

    assert bot_human["total_attendances"] == 3
    assert bot_human["classified_attendances"] == 2
    assert bot_human["unclassified_attendances"] == 1
    assert bot_human["with_bot_percentage"] == 50.0
    assert bot_human["reached_human_percentage"] == 100.0
    assert bot_human["bot_to_human_handoff_percentage"] == 50.0


def test_opa_attendant_summary_missing_attendant_returns_404(db_session, admin_user):
    with pytest.raises(HTTPException) as exc:
        _attendant_summary(db_session, admin_user, "NUNCA-EXISTIU")

    assert exc.value.status_code == 404


def test_opa_attendant_summary_resolves_identity_from_dimension_only(db_session, admin_user):
    db_session.add(
        SupportOpaDimension(
            dimension_type="user",
            source_id="BOT-1",
            name="Bot Assistente",
            payload_json={"tipo": "bot"},
        )
    )
    db_session.flush()

    body = _attendant_summary(db_session, admin_user, "BOT-1")

    assert body["attendant_name"] == "Bot Assistente"
    assert body["attendant_type"] == "bot"
    assert body["total_attendances"] == 0
    assert body["closure_rate"] == 0.0


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


def test_opa_attendance_timeline_returns_structural_events_without_messages(db_session, admin_user):
    opened = datetime(2026, 8, 1, 8, tzinfo=timezone.utc)
    row = _attendance(
        1,
        opened_at=opened,
        closed_at=opened + timedelta(minutes=30),
        first_response_at=opened + timedelta(minutes=5),
        bot_to_human_handoff=True,
    )
    db_session.add(row)
    db_session.flush()

    body = opa_attendance_timeline(row.id, include_messages=False, db=db_session, user=admin_user)

    assert body["attendance_id"] == row.id
    assert body["source_id"] == row.source_id
    assert body["messages_source"] == "not_attempted"
    assert body["messages_error"] is None
    assert [event["type"] for event in body["events"]] == [
        "opened",
        "bot_handoff",
        "first_human_response",
        "closed",
    ]


def test_opa_attendance_timeline_missing_attendance_returns_404(db_session, admin_user):
    with pytest.raises(HTTPException) as exc:
        opa_attendance_timeline(999999, include_messages=False, db=db_session, user=admin_user)

    assert exc.value.status_code == 404


def test_opa_attendance_timeline_includes_first_response_event(db_session, admin_user):
    opened = datetime(2026, 8, 1, 8, tzinfo=timezone.utc)
    row = _attendance(2, opened_at=opened, first_response_at=opened + timedelta(minutes=3), closed_at=None)
    db_session.add(row)
    db_session.flush()

    body = opa_attendance_timeline(row.id, include_messages=False, db=db_session, user=admin_user)

    types = [event["type"] for event in body["events"]]
    assert "first_human_response" in types
    assert "closed" not in types


def test_opa_attendance_timeline_without_first_response_has_no_event(db_session, admin_user):
    row = _attendance(3, first_response_at=None, closed_at=None)
    db_session.add(row)
    db_session.flush()

    body = opa_attendance_timeline(row.id, include_messages=False, db=db_session, user=admin_user)

    assert [event["type"] for event in body["events"]] == ["opened"]


def test_opa_attendance_timeline_bot_human_nullable_produces_no_handoff_event(db_session, admin_user):
    row = _attendance(4, handled_by_bot=None, reached_human=None, bot_to_human_handoff=None)
    db_session.add(row)
    db_session.flush()

    body = opa_attendance_timeline(row.id, include_messages=False, db=db_session, user=admin_user)

    assert body["handled_by_bot"] is None
    assert body["reached_human"] is None
    assert body["bot_to_human_handoff"] is None
    assert "bot_handoff" not in [event["type"] for event in body["events"]]


def test_opa_attendance_timeline_live_messages_classify_client_bot_and_human(db_session, admin_user, monkeypatch):
    row = _attendance(5, opened_at=datetime(2026, 8, 1, 8, tzinfo=timezone.utc))
    db_session.add(row)
    db_session.add_all(
        [
            SupportOpaDimension(dimension_type="user", source_id="BOT-1", name="Bot", payload_json={"tipo": "bot"}),
            SupportOpaDimension(dimension_type="user", source_id="A-1", name="Ana", payload_json={"tipo": "user"}),
        ]
    )
    db_session.flush()

    class Client:
        def list_messages(self, source_id):
            assert source_id == row.source_id
            return [
                {"id_user": "U-1", "data": "2026-08-01T08:00:05+00:00"},
                {"id_atend": "BOT-1", "data": "2026-08-01T08:00:10+00:00"},
                {"id_atend": "A-1", "data": "2026-08-01T08:05:00+00:00"},
            ]

    monkeypatch.setattr(opa_timeline_service, "get_opa_client", lambda: Client())

    body = opa_attendance_timeline(row.id, include_messages=True, db=db_session, user=admin_user)

    assert body["messages_source"] == "live"
    assert body["messages_error"] is None
    message_events = [event for event in body["events"] if event["type"] == "message"]
    assert [event["actor_type"] for event in message_events] == ["client", "bot", "human"]
    # Nunca expõe texto de mensagem na timeline (Fase 3C: só metadado do fluxo).
    assert all("mensagem" not in event or event.get("mensagem") is None for event in message_events)


def test_opa_attendance_timeline_classifies_theo_tool_calls_as_bot(db_session, admin_user, monkeypatch):
    """Reproduz UNI2026810881: mensagens `tipo="assistant"` sem `id_user` nem
    `id_atend` sao o log interno do Theo, nao "remetente nao identificado"."""
    row = _attendance(6, opened_at=datetime(2026, 8, 1, 8, tzinfo=timezone.utc))
    db_session.add(row)
    db_session.flush()

    class Client:
        def list_messages(self, source_id):
            return [
                {"id_user": "U-1", "data": "2026-08-01T08:00:00+00:00"},
                {"tipo": "assistant", "mensagem": "tool_call interno", "data": "2026-08-01T08:00:05+00:00"},
            ]

    monkeypatch.setattr(opa_timeline_service, "get_opa_client", lambda: Client())

    body = opa_attendance_timeline(row.id, include_messages=True, db=db_session, user=admin_user)

    message_events = [event for event in body["events"] if event["type"] == "message"]
    assert [event["actor_type"] for event in message_events] == ["client", "bot"]
    assert message_events[1]["label"] == "Mensagem do atendimento automatizado"
    assert "unknown" not in [event["actor_type"] for event in message_events]


def test_opa_attendance_timeline_external_failure_keeps_structural_events(db_session, admin_user, monkeypatch):
    row = _attendance(6)
    db_session.add(row)
    db_session.flush()

    class Client:
        def list_messages(self, source_id):
            raise RuntimeError("OPA fora do ar")

    monkeypatch.setattr(opa_timeline_service, "get_opa_client", lambda: Client())

    body = opa_attendance_timeline(row.id, include_messages=True, db=db_session, user=admin_user)

    assert body["messages_source"] == "unavailable"
    assert body["messages_error"] is not None
    assert any(event["type"] == "opened" for event in body["events"])


# --- Filtros novos (etiqueta, avaliação, bot/humano) e série diária -----------


def _timeseries(db_session, admin_user, **kwargs):
    params = {
        "date_from": date(2026, 8, 1),
        "date_to": date(2026, 8, 1),
        "status": None,
        "channel": None,
        "attendant_id": None,
        "department_id": None,
        "reason_id": None,
        "customer": None,
        "search": None,
        "db": db_session,
        "user": admin_user,
        "extra": OpaExtraFilters(),
    }
    params.update(kwargs)
    return opa_timeseries(**params)


def test_tag_filter_matches_only_attendances_carrying_the_tag(db_session, admin_user):
    db_session.add_all(
        [
            _attendance(1, tag_ids_text=",tag-a,tag-b,"),
            _attendance(2, tag_ids_text=",tag-b,"),
            _attendance(3, tag_ids_text=","),
            _attendance(4, tag_ids_text=None),
        ]
    )
    db_session.flush()

    only_a = _list(db_session, admin_user, extra=OpaExtraFilters(tag_id="tag-a"))
    assert {item["protocol"] for item in only_a["items"]} == {"UNI20260001"}

    # Multivalorado é OU: "tem pelo menos uma das selecionadas".
    a_or_b = _list(db_session, admin_user, extra=OpaExtraFilters(tag_id="tag-a,tag-b"))
    assert {item["protocol"] for item in a_or_b["items"]} == {"UNI20260001", "UNI20260002"}


def test_tag_filter_does_not_match_id_that_merely_contains_another(db_session, admin_user):
    """O separador nas duas pontas existe justamente pra isso: sem ele,
    LIKE '%tag%' casaria com 'tag-a' e o filtro devolveria a mais."""
    db_session.add_all(
        [
            _attendance(1, tag_ids_text=",tag,"),
            _attendance(2, tag_ids_text=",tag-a,"),
        ]
    )
    db_session.flush()

    result = _list(db_session, admin_user, extra=OpaExtraFilters(tag_id="tag"))
    assert {item["protocol"] for item in result["items"]} == {"UNI20260001"}


def test_rating_range_filter_excludes_unrated_attendances(db_session, admin_user):
    db_session.add_all(
        [
            _attendance(1, rating=5.0),
            _attendance(2, rating=3.0),
            _attendance(3, rating=None),
        ]
    )
    db_session.flush()

    result = _list(db_session, admin_user, extra=OpaExtraFilters(rating_min=4))
    protocols = {item["protocol"] for item in result["items"]}
    assert protocols == {"UNI20260001"}
    # Atendimento sem avaliação nunca entra num recorte por nota — `NULL >= 4`
    # não é verdadeiro, e tratá-lo como 0 inventaria uma nota que não existe.
    assert "UNI20260003" not in protocols

    faixa = _list(db_session, admin_user, extra=OpaExtraFilters(rating_min=3, rating_max=4))
    assert {item["protocol"] for item in faixa["items"]} == {"UNI20260002"}


def test_bot_human_filter_never_treats_unclassified_as_false(db_session, admin_user):
    db_session.add_all(
        [
            _attendance(1, handled_by_bot=True, reached_human=True, bot_to_human_handoff=True),
            _attendance(2, handled_by_bot=False, reached_human=True, bot_to_human_handoff=False),
            _attendance(3, handled_by_bot=None, reached_human=None, bot_to_human_handoff=None),
        ]
    )
    db_session.flush()

    com_bot = _list(db_session, admin_user, extra=OpaExtraFilters(bot_human="with_bot"))
    assert {item["protocol"] for item in com_bot["items"]} == {"UNI20260001"}

    sem_bot = _list(db_session, admin_user, extra=OpaExtraFilters(bot_human="without_bot"))
    # O não classificado (NULL) NÃO aparece aqui: "não sei" nunca vira "sem bot".
    assert {item["protocol"] for item in sem_bot["items"]} == {"UNI20260002"}

    handoff = _list(db_session, admin_user, extra=OpaExtraFilters(bot_human="handoff"))
    assert {item["protocol"] for item in handoff["items"]} == {"UNI20260001"}

    nao_classificado = _list(db_session, admin_user, extra=OpaExtraFilters(bot_human="unclassified"))
    assert {item["protocol"] for item in nao_classificado["items"]} == {"UNI20260003"}


def test_new_filters_apply_to_overview_and_previous_period_alike(db_session, admin_user):
    """`previous_period()` passou a usar `dataclasses.replace`; este teste trava
    a regressão que a versão antiga (cópia campo a campo) permitiria — um filtro
    novo valendo só no período atual faria o comparativo medir outro universo."""
    db_session.add_all(
        [
            _attendance(1, opened_at=datetime(2026, 8, 2, 10, tzinfo=timezone.utc), handled_by_bot=True),
            _attendance(2, opened_at=datetime(2026, 8, 2, 11, tzinfo=timezone.utc), handled_by_bot=False),
            _attendance(3, opened_at=datetime(2026, 8, 1, 10, tzinfo=timezone.utc), handled_by_bot=True),
            _attendance(4, opened_at=datetime(2026, 8, 1, 11, tzinfo=timezone.utc), handled_by_bot=False),
        ]
    )
    db_session.flush()

    overview = _overview(
        db_session,
        admin_user,
        date_from=date(2026, 8, 2),
        date_to=date(2026, 8, 2),
        extra=OpaExtraFilters(bot_human="with_bot"),
    )
    assert overview["total_attendances"]["current"] == 1
    # Se o filtro vazasse do período anterior, `previous` viria 2 em vez de 1.
    assert overview["total_attendances"]["previous"] == 1


def test_daily_timeseries_fills_days_without_attendances_with_zero(db_session, admin_user):
    db_session.add_all(
        [
            _attendance(1, opened_at=datetime(2026, 8, 1, 12, tzinfo=timezone.utc)),
            _attendance(2, opened_at=datetime(2026, 8, 3, 12, tzinfo=timezone.utc)),
        ]
    )
    db_session.flush()

    body = _timeseries(db_session, admin_user, date_from=date(2026, 8, 1), date_to=date(2026, 8, 3))
    points = body["points"]

    assert [point["day"] for point in points] == [date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3)]
    assert [point["total"] for point in points] == [1, 0, 1]
    # Dia vazio não pode inventar tempo: some da média, não vira zero.
    assert points[1]["average_duration_seconds"] is None
    assert points[1]["tmr_all_responses_coverage"] == {"count": 0, "total": 0, "percentage": None}


def test_daily_timeseries_totals_match_the_overview_of_the_same_period(db_session, admin_user):
    """O gráfico é decomposição dos cards — se as duas somas divergirem, a tela
    está mostrando dois universos diferentes lado a lado."""
    _seed(db_session, total=18)

    overview = _overview(db_session, admin_user, date_from=date(2026, 8, 1), date_to=date(2026, 8, 2))
    body = _timeseries(db_session, admin_user, date_from=date(2026, 8, 1), date_to=date(2026, 8, 2))

    assert sum(point["total"] for point in body["points"]) == overview["total_attendances"]["current"]
    assert sum(point["closed"] for point in body["points"]) == overview["closed_attendances"]["current"]


def test_daily_timeseries_buckets_by_local_day_not_utc(db_session, admin_user):
    """02:00 UTC do dia 2 é ainda 22:00 do dia 1 em America/Porto_Velho (UTC-4).
    Agrupar em UTC jogaria esse atendimento no dia errado do gráfico."""
    db_session.add_all(
        [
            _attendance(1, opened_at=datetime(2026, 8, 2, 2, 0, tzinfo=timezone.utc)),
            _attendance(2, opened_at=datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)),
        ]
    )
    db_session.flush()

    body = _timeseries(db_session, admin_user, date_from=date(2026, 8, 1), date_to=date(2026, 8, 2))
    by_day = {point["day"]: point["total"] for point in body["points"]}

    assert by_day[date(2026, 8, 1)] == 1
    assert by_day[date(2026, 8, 2)] == 1
