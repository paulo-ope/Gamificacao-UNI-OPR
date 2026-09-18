"""Fase 6 do plano de evolução analítica do Atendimento IXC (2026-09-15): `OS_CONVERSION_V1` -
mede quantos atendimentos viraram O.S. dentro de janelas de tempo, usando o join que já existe no
schema (`OperationOrder.ticket_id == SupportIxcTicket.source_id`)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.modules.operations.models import OperationOrder
from app.modules.support import ixc_ticket_os_conversion
from app.modules.support.models import SupportIxcTicket

REGIONAL = "UNI - NOVA BRASILANDIA DOESTE"


def _ticket(db, *, source_id, created_at, regional=REGIONAL, **overrides):
    base = dict(source_id=source_id, regional=regional, subject_name="Sem conexão", created_at=created_at)
    base.update(overrides)
    row = SupportIxcTicket(**base)
    db.add(row)
    return row


def _order(db, *, order_code, ticket_id, opened_at, **overrides):
    defaults = dict(
        source_order_id=order_code,
        order_code=order_code,
        os_type="Manutenção",
        os_subject="Suporte Externo",
        ticket_id=ticket_id,
        opened_at=opened_at,
        closed_at=opened_at,
        is_closed=True,
    )
    defaults.update(overrides)
    row = OperationOrder(**defaults)
    db.add(row)
    return row


def test_os_conversion_rate_with_no_tickets_returns_sem_dado(db_session):
    result = ixc_ticket_os_conversion.os_conversion_rate(db_session, date_from=None, date_to=None)

    assert result == {
        "sample": 0,
        "median_lead_minutes": None,
        "classification": "sem_dado",
        "conversions": {"2h": None, "6h": None, "24h": None, "48h": None},
    }


def test_os_conversion_rate_counts_orders_within_each_window(db_session):
    created_at = datetime(2026, 9, 10, 8, tzinfo=timezone.utc)
    _ticket(db_session, source_id="T1", created_at=created_at)
    _order(db_session, order_code="OS-1", ticket_id="T1", opened_at=created_at + timedelta(hours=1))
    db_session.commit()

    result = ixc_ticket_os_conversion.os_conversion_rate(
        db_session, date_from=date(2026, 9, 10), date_to=date(2026, 9, 10)
    )

    assert result["sample"] == 1
    assert result["conversions"] == {"2h": 100.0, "6h": 100.0, "24h": 100.0, "48h": 100.0}
    assert result["median_lead_minutes"] == 60.0
    assert result["classification"] == "alto"


def test_os_conversion_rate_ticket_without_order_never_converts(db_session):
    created_at = datetime(2026, 9, 10, 8, tzinfo=timezone.utc)
    _ticket(db_session, source_id="T1", created_at=created_at)
    db_session.commit()

    result = ixc_ticket_os_conversion.os_conversion_rate(
        db_session, date_from=date(2026, 9, 10), date_to=date(2026, 9, 10)
    )

    assert result["sample"] == 1
    assert result["conversions"] == {"2h": 0.0, "6h": 0.0, "24h": 0.0, "48h": 0.0}
    assert result["median_lead_minutes"] is None
    assert result["classification"] == "baixo"


def test_os_conversion_rate_order_outside_largest_window_does_not_count(db_session):
    created_at = datetime(2026, 9, 10, 8, tzinfo=timezone.utc)
    _ticket(db_session, source_id="T1", created_at=created_at)
    _order(db_session, order_code="OS-1", ticket_id="T1", opened_at=created_at + timedelta(hours=72))
    db_session.commit()

    result = ixc_ticket_os_conversion.os_conversion_rate(
        db_session, date_from=date(2026, 9, 10), date_to=date(2026, 9, 10)
    )

    assert result["conversions"]["48h"] == 0.0
    assert result["median_lead_minutes"] is None


def test_os_conversion_rate_order_before_ticket_is_ignored(db_session):
    """Uma O.S. aberta ANTES do atendimento não pode ter sido causada por ele - achado defensivo,
    não uma amostra real esperada (o `ticket_id` só é preenchido depois que o atendimento existe)."""
    created_at = datetime(2026, 9, 10, 8, tzinfo=timezone.utc)
    _ticket(db_session, source_id="T1", created_at=created_at)
    _order(db_session, order_code="OS-1", ticket_id="T1", opened_at=created_at - timedelta(hours=1))
    db_session.commit()

    result = ixc_ticket_os_conversion.os_conversion_rate(
        db_session, date_from=date(2026, 9, 10), date_to=date(2026, 9, 10)
    )

    assert result["conversions"]["48h"] == 0.0


def test_os_conversion_rate_uses_fastest_order_per_ticket_for_median(db_session):
    created_at = datetime(2026, 9, 10, 8, tzinfo=timezone.utc)
    _ticket(db_session, source_id="T1", created_at=created_at)
    _order(db_session, order_code="OS-1", ticket_id="T1", opened_at=created_at + timedelta(hours=5))
    _order(db_session, order_code="OS-2", ticket_id="T1", opened_at=created_at + timedelta(hours=1))
    db_session.commit()

    result = ixc_ticket_os_conversion.os_conversion_rate(
        db_session, date_from=date(2026, 9, 10), date_to=date(2026, 9, 10)
    )

    assert result["median_lead_minutes"] == 60.0


def test_os_conversion_rate_classification_thresholds(db_session):
    created_at = datetime(2026, 9, 10, 8, tzinfo=timezone.utc)
    for i in range(10):
        _ticket(db_session, source_id=f"T{i}", created_at=created_at)
    for i in range(3):
        _order(db_session, order_code=f"OS-{i}", ticket_id=f"T{i}", opened_at=created_at + timedelta(hours=1))
    db_session.commit()

    result = ixc_ticket_os_conversion.os_conversion_rate(
        db_session, date_from=date(2026, 9, 10), date_to=date(2026, 9, 10)
    )

    assert result["conversions"]["24h"] == 30.0
    assert result["classification"] == "moderado"
