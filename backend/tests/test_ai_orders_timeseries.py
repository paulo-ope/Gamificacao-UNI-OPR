"""opr_orders_timeseries - achado real da auditoria de 2026-08-21: metric="taxa_sla" não existia
e devolvia data: [] em silêncio, sem erro; metric desconhecido em geral nunca era validado."""

from datetime import date, datetime, timezone

import pytest

from app.models import User
from app.modules.ai import queries as ai_queries
from app.modules.operations.models import OperationOrder

DATE_FROM = date(2026, 7, 1)
DATE_TO = date(2026, 7, 31)


@pytest.fixture()
def ai_user(db_session):
    user = User(name="IA", email="ia-timeseries@pytest.local", role="admin", active=True, password_hash="x")
    db_session.add(user)
    db_session.flush()
    return user


def _closed_order(db_session, *, order_code, closed_at, sla_status):
    order = OperationOrder(
        source_order_id=order_code,
        order_code=order_code,
        os_type="Manutenção",
        os_subject="Suporte Externo",
        opened_at=closed_at,
        closed_at=closed_at,
        is_closed=True,
        sla_status=sla_status,
        raw_payload={},
    )
    db_session.add(order)
    return order


def test_orders_timeseries_rejects_unknown_metric(db_session, ai_user):
    with pytest.raises(ValueError, match="metric inválido"):
        ai_queries.orders_timeseries(
            db_session, ai_user, metric="taxa_algo_que_nao_existe", granularity="day",
            date_from=DATE_FROM, date_to=DATE_TO,
        )


def test_orders_timeseries_taxa_sla_computes_rate_per_bucket(db_session, ai_user):
    day1 = datetime(2026, 7, 10, 15, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 7, 11, 15, 0, tzinfo=timezone.utc)
    _closed_order(db_session, order_code="OS-1", closed_at=day1, sla_status="on_time")
    _closed_order(db_session, order_code="OS-2", closed_at=day1, sla_status="on_time")
    _closed_order(db_session, order_code="OS-3", closed_at=day1, sla_status="out_of_time")
    _closed_order(db_session, order_code="OS-4", closed_at=day2, sla_status="out_of_time")
    db_session.flush()

    result = ai_queries.orders_timeseries(
        db_session, ai_user, metric="taxa_sla", granularity="day", date_from=DATE_FROM, date_to=DATE_TO,
    )

    by_day = {item["period_start"]: item for item in result["data"]}
    assert by_day[date(2026, 7, 10)]["quantity"] == 3
    assert by_day[date(2026, 7, 10)]["sla_rate"] == pytest.approx(66.67, abs=0.01)
    assert by_day[date(2026, 7, 11)]["quantity"] == 1
    assert by_day[date(2026, 7, 11)]["sla_rate"] == 0.0


def test_orders_timeseries_other_metrics_have_no_sla_rate(db_session, ai_user):
    day1 = datetime(2026, 7, 10, 15, 0, tzinfo=timezone.utc)
    _closed_order(db_session, order_code="OS-1", closed_at=day1, sla_status="on_time")
    db_session.flush()

    result = ai_queries.orders_timeseries(
        db_session, ai_user, metric="fechadas", granularity="day", date_from=DATE_FROM, date_to=DATE_TO,
    )
    assert result["data"][0]["quantity"] == 1
    assert "sla_rate" not in result["data"][0]
