from datetime import date, datetime, timezone

import pytest

from app.models import User
from app.modules.ai import queries as ai_queries
from app.modules.operations.backlog_snapshot import capture_backlog_snapshot
from app.modules.operations.models import OperationBacklogSnapshot, OperationOrder
from app.modules.operations.period import OPERATIONS_TIMEZONE

DATE_FROM = date(2026, 7, 1)
DATE_TO = date(2026, 7, 31)


@pytest.fixture()
def ai_user(db_session):
    user = User(name="IA", email="ia-desc@pytest.local", role="admin", active=True, password_hash="x")
    db_session.add(user)
    db_session.flush()
    return user


def _make_order(db_session, *, order_code, raw_payload, opened_at):
    order = OperationOrder(
        source_order_id=order_code,
        order_code=order_code,
        os_type="Manutenção",
        os_subject="Suporte Externo",
        opened_at=opened_at,
        closed_at=opened_at,
        is_closed=True,
        raw_payload=raw_payload,
    )
    db_session.add(order)
    return order


def test_ai_text_filter_service_description_matches_raw_payload_only(db_session, ai_user):
    """Item 13, lado da IA: `text_filters` com field="service_description" precisa achar termo
    dentro do raw_payload bruto (mensagem/descricao/descricao_servico), igual à busca livre do
    módulo Operação."""
    opened_at = datetime(2026, 7, 15, tzinfo=timezone.utc)
    _make_order(db_session, order_code="DESC-HIT", raw_payload={"mensagem": "Sinal caindo toda noite"}, opened_at=opened_at)
    _make_order(db_session, order_code="DESC-MISS", raw_payload={"mensagem": "Troca de senha do wifi"}, opened_at=opened_at)
    db_session.flush()

    result = ai_queries.search_orders(
        db_session, ai_user, date_from=DATE_FROM, date_to=DATE_TO,
        text_filters=[{"field": "service_description", "operator": "contains", "value": "sinal caindo"}],
    )
    assert [item["order_code"] for item in result["items"]] == ["DESC-HIT"]


def test_ai_aggregate_orders_groups_by_neighborhood(db_session, ai_user):
    """Item 3: bairro confirmado como campo separado (ver migration 20260811_0048) - precisa dar
    pra agrupar O.S. por ele, respondendo ao pedido original de mapear concentração por bairro."""
    opened_at = datetime(2026, 7, 15, tzinfo=timezone.utc)
    _make_order(db_session, order_code="NEI-1", raw_payload={}, opened_at=opened_at)
    _make_order(db_session, order_code="NEI-2", raw_payload={}, opened_at=opened_at)
    db_session.query(OperationOrder).filter(OperationOrder.order_code == "NEI-1").update({"neighborhood": "Centro"})
    db_session.query(OperationOrder).filter(OperationOrder.order_code == "NEI-2").update({"neighborhood": "Nova Brasília"})
    db_session.flush()

    result = ai_queries.aggregate_orders(
        db_session, ai_user, group_by="neighborhood", metric="quantidade_fechada", date_from=DATE_FROM, date_to=DATE_TO,
    )
    by_label = {item["label"]: item["quantity"] for item in result}
    assert by_label == {"Centro": 1, "Nova Brasília": 1}


def test_ai_text_filter_neighborhood_is_case_insensitive_contains(db_session, ai_user):
    """Achado real: a grafia de bairro é inconsistente na fonte (ex.: "Centro" e "CENTRO"
    convivem) - por isso "neighborhood" também entra como filtro de texto "contém", não só como
    dimensão de agrupamento exato."""
    opened_at = datetime(2026, 7, 15, tzinfo=timezone.utc)
    _make_order(db_session, order_code="NEI-CASE-1", raw_payload={}, opened_at=opened_at)
    _make_order(db_session, order_code="NEI-CASE-2", raw_payload={}, opened_at=opened_at)
    db_session.query(OperationOrder).filter(OperationOrder.order_code == "NEI-CASE-1").update({"neighborhood": "CENTRO"})
    db_session.query(OperationOrder).filter(OperationOrder.order_code == "NEI-CASE-2").update({"neighborhood": "Zona Rural"})
    db_session.flush()

    result = ai_queries.search_orders(
        db_session, ai_user, date_from=DATE_FROM, date_to=DATE_TO,
        text_filters=[{"field": "neighborhood", "operator": "contains", "value": "centro"}],
    )
    assert [item["order_code"] for item in result["items"]] == ["NEI-CASE-1"]


def test_ai_fields_lists_service_description_expression_without_crashing():
    """`available_fields()` não deve quebrar por causa da expressão calculada de
    "service_description" em TEXT_FILTER_COLUMNS (que não tem `.key` de coluna real)."""
    result = ai_queries.available_fields()
    assert "raw_payload" in result["all_fields"]
    # A expressão calculada não corresponde a nenhuma coluna isolada - não deve aparecer nem em
    # exposed_to_ai nem em not_exposed como "service_description" (não é um nome de coluna real).
    assert "service_description" not in result["exposed_to_ai"]
    assert "service_description" not in result["not_exposed"]


def test_capture_backlog_snapshot_groups_by_city(db_session):
    """Item 14: o snapshot diário de backlog agora quebra também por cidade."""
    now_local = datetime.now(OPERATIONS_TIMEZONE)
    db_session.add_all(
        [
            OperationOrder(
                source_order_id="BACKLOG-CITY-1",
                order_code="BACKLOG-CITY-1",
                regional="UNI - JI PARANA",
                city="Ji-Paraná",
                sector="Suporte Externo Fibra",
                opened_at=now_local,
                is_closed=False,
            ),
            OperationOrder(
                source_order_id="BACKLOG-CITY-2",
                order_code="BACKLOG-CITY-2",
                regional="UNI - JI PARANA",
                city="Presidente Médici",
                sector="Suporte Externo Fibra",
                opened_at=now_local,
                is_closed=False,
            ),
            OperationOrder(
                source_order_id="BACKLOG-CITY-CLOSED",
                order_code="BACKLOG-CITY-CLOSED",
                regional="UNI - JI PARANA",
                city="Ji-Paraná",
                sector="Suporte Externo Fibra",
                opened_at=now_local,
                closed_at=now_local,
                is_closed=True,
            ),
        ]
    )
    db_session.flush()

    captured = capture_backlog_snapshot(db_session)
    assert captured == 2

    rows = list(db_session.query(OperationBacklogSnapshot).all())
    by_city = {row.city: row.backlog_count for row in rows}
    assert by_city == {"Ji-Paraná": 1, "Presidente Médici": 1}


def test_ai_backlog_history_groups_by_city(db_session, ai_user):
    db_session.add_all(
        [
            OperationBacklogSnapshot(
                snapshot_date=date(2026, 7, 10),
                regional="UNI - JI PARANA",
                team_model="Não identificado",
                sector="Suporte Externo Fibra",
                city="Ji-Paraná",
                backlog_count=5,
                backlog_atrasado_count=1,
            ),
            OperationBacklogSnapshot(
                snapshot_date=date(2026, 7, 10),
                regional="UNI - JI PARANA",
                team_model="Não identificado",
                sector="Suporte Externo Fibra",
                city="Presidente Médici",
                backlog_count=3,
                backlog_atrasado_count=0,
            ),
        ]
    )
    db_session.flush()

    result = ai_queries.backlog_history(
        db_session, ai_user, metric="backlog", date_from=date(2026, 7, 1), date_to=date(2026, 7, 31), group_by="city",
    )
    by_group = {item["group"]: item["quantity"] for item in result}
    assert by_group == {"Ji-Paraná": 5, "Presidente Médici": 3}
