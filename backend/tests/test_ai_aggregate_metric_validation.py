from datetime import date, datetime, timezone

import pytest

from app.models import User
from app.modules.ai import queries as ai_queries
from app.modules.operations.models import OperationOrder

DATE_FROM = date(2026, 7, 1)
DATE_TO = date(2026, 7, 31)


@pytest.fixture()
def ai_user(db_session):
    user = User(name="IA", email="ia-metric@pytest.local", role="admin", active=True, password_hash="x")
    db_session.add(user)
    db_session.flush()
    return user


def _make_order(db_session, *, order_code, opened_at, **overrides):
    defaults = dict(
        source_order_id=order_code,
        order_code=order_code,
        os_type="Manutenção",
        os_subject="Suporte Externo",
        opened_at=opened_at,
        closed_at=opened_at,
        is_closed=True,
    )
    defaults.update(overrides)
    order = OperationOrder(**defaults)
    db_session.add(order)
    return order


def test_aggregate_orders_rejects_unknown_metric(db_session, ai_user):
    """Achado real: `metric` desconhecido (ex.: chamada direta via tool MCP, que não passa pelo
    schema Pydantic `AiAggregationRequest.metric`) caía silenciosamente no branch "quantidade_fechada"
    do `else` final, devolvendo dados plausíveis mas errados, sem erro nem aviso algum -
    inconsistente com `group_by` inválido, que já é rejeitado com ValueError. `metric` inválido deve
    ser rejeitado da mesma forma, citando os valores aceitos."""
    opened_at = datetime(2026, 7, 15, tzinfo=timezone.utc)
    _make_order(db_session, order_code="ANY", opened_at=opened_at)
    db_session.flush()

    with pytest.raises(ValueError, match="metric inválido"):
        ai_queries.aggregate_orders(
            db_session, ai_user, group_by="sector", metric="isso_nao_existe",
            date_from=DATE_FROM, date_to=DATE_TO,
        )


def test_aggregate_orders_accepts_known_metric(db_session, ai_user):
    """Garante que a validação nova não bloqueia nenhuma métrica legítima já suportada."""
    opened_at = datetime(2026, 7, 15, tzinfo=timezone.utc)
    _make_order(db_session, order_code="OK", opened_at=opened_at)
    db_session.flush()

    result = ai_queries.aggregate_orders(
        db_session, ai_user, group_by="sector", metric="quantidade_fechada",
        date_from=DATE_FROM, date_to=DATE_TO,
    )
    assert sum(item["quantity"] for item in result["data"]) == 1
