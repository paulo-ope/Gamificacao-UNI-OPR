"""Fase 2 do plano de evolução analítica do Atendimento IXC (2026-09-14): contrato de contexto
único (`ixc_ticket_context.py`) - generaliza breakdown/prioridades por `dimension` + filtros
independentes, no modelo de período livre (date_from/date_to + janela anterior de mesmo
tamanho)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.modules.operations.models import OperationCustomerContract
from app.modules.support import ixc_ticket_context
from app.modules.support.models import SupportIxcTicket

REGIONAL = "UNI - NOVA BRASILANDIA DOESTE"
CITY = "Nova Brasilândia D'Oeste"
NEIGHBORHOOD = "Centro"


def _ticket(db, *, source_id, **overrides):
    base = dict(
        source_id=source_id,
        customer_id="500",
        regional=REGIONAL,
        city=CITY,
        neighborhood=NEIGHBORHOOD,
        subject_id="90",
        subject_name="Sem conexão",
        created_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
    )
    base.update(overrides)
    row = SupportIxcTicket(**base)
    db.add(row)
    return row


def _contract(db, *, id_seq, **overrides):
    base = dict(source_contract_id=id_seq, regional=REGIONAL, city=CITY, status="A")
    base.update(overrides)
    row = OperationCustomerContract(**base)
    db.add(row)
    return row


def test_resolve_context_computes_deviation_vs_previous_period_of_same_length(db_session):
    for i in range(12):
        _ticket(db_session, source_id=f"CUR{i}", created_at=datetime(2026, 9, 10, tzinfo=timezone.utc))
    for i in range(10):
        _ticket(db_session, source_id=f"PREV{i}", created_at=datetime(2026, 9, 8, tzinfo=timezone.utc))
    db_session.commit()

    context = ixc_ticket_context.resolve_context(
        db_session, date_from=date(2026, 9, 9), date_to=date(2026, 9, 10), regional=REGIONAL
    )

    assert context["ticket_count"] == 12
    assert context["previous_ticket_count"] == 10
    assert context["deviation_pct"] == 20.0
    assert context["severity"] == "critico"


def test_resolve_context_next_dimension_progresses_through_hierarchy(db_session):
    _ticket(db_session, source_id="T1")
    db_session.commit()

    assert ixc_ticket_context.resolve_context(db_session, date_from=None, date_to=None)["next_dimension"] == "regional"
    assert ixc_ticket_context.resolve_context(
        db_session, date_from=None, date_to=None, regional=REGIONAL
    )["next_dimension"] == "city"
    assert ixc_ticket_context.resolve_context(
        db_session, date_from=None, date_to=None, regional=REGIONAL, city=CITY
    )["next_dimension"] == "neighborhood"
    assert ixc_ticket_context.resolve_context(
        db_session, date_from=None, date_to=None, regional=REGIONAL, city=CITY, neighborhood=NEIGHBORHOOD
    )["next_dimension"] == "subject"
    assert ixc_ticket_context.resolve_context(
        db_session, date_from=None, date_to=None, regional=REGIONAL, city=CITY, neighborhood=NEIGHBORHOOD, subject_id="90"
    )["next_dimension"] is None


def test_resolve_context_contract_count_is_none_without_regional_or_city(db_session):
    _ticket(db_session, source_id="T1")
    db_session.commit()

    context = ixc_ticket_context.resolve_context(db_session, date_from=None, date_to=None)

    assert context["contract_count"] is None
    assert context["tickets_per_1000_contracts"] is None


def test_resolve_context_includes_reach_summary(db_session):
    _ticket(db_session, source_id="T1", customer_id="500")
    _ticket(db_session, source_id="T2", customer_id="501")
    db_session.commit()

    context = ixc_ticket_context.resolve_context(
        db_session, date_from=date(2026, 9, 1), date_to=date(2026, 9, 30), regional=REGIONAL
    )

    assert context["reach"]["unique_customers"] == 2


def test_resolve_context_top_driver_is_none_without_tickets(db_session):
    context = ixc_ticket_context.resolve_context(db_session, date_from=None, date_to=None)

    assert context["top_driver"] is None


def test_driver_decomposition_for_period_uses_previous_period_as_expected(db_session):
    for i in range(5):
        _ticket(
            db_session, source_id=f"CUR{i}", subject_name="Lentidão",
            created_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
        )
    _ticket(db_session, source_id="PREV1", subject_name="Lentidão", created_at=datetime(2026, 9, 8, tzinfo=timezone.utc))
    db_session.commit()

    items = ixc_ticket_context.driver_decomposition_for_period(
        db_session, date_from=date(2026, 9, 9), date_to=date(2026, 9, 10)
    )

    assert items[0]["subject_name"] == "Lentidão"
    assert items[0]["current"] == 5
    assert items[0]["expected"] == 1
    assert items[0]["excess"] == 4
    assert items[0]["contribution_pct"] == 100.0


def test_priorities_for_context_requires_parent_filters():
    with pytest.raises(ValueError):
        ixc_ticket_context.priorities_for_context(
            None, dimension="city", date_from=None, date_to=None  # regional ausente
        )


def test_priorities_for_context_regional_dimension_adds_severity_and_label(db_session):
    for i in range(30):
        _ticket(db_session, source_id=f"T{i}", created_at=datetime(2026, 9, 10, tzinfo=timezone.utc))
    for i in range(10):
        _ticket(db_session, source_id=f"P{i}", created_at=datetime(2026, 9, 8, tzinfo=timezone.utc))
    db_session.commit()

    items = ixc_ticket_context.priorities_for_context(
        db_session, dimension="regional", date_from=date(2026, 9, 9), date_to=date(2026, 9, 10)
    )

    assert items[0]["key"] == REGIONAL
    assert items[0]["dimension"] == "regional"
    assert items[0]["severity"] == "critico"
