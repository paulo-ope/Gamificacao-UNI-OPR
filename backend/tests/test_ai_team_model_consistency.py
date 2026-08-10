from datetime import date, datetime, timezone

import pytest

from app.models import User
from app.modules.ai import queries as ai_queries
from app.modules.operations.models import OperationOrder, OperationResponsibleAssignment, OperationTeamModel

DATE_FROM = date(2026, 7, 1)
DATE_TO = date(2026, 7, 31)


@pytest.fixture()
def ai_user(db_session):
    user = User(name="IA", email="ia@pytest.local", role="admin", active=True, password_hash="x")
    db_session.add(user)
    db_session.flush()
    return user


def _make_order(db_session, *, order_code, responsible, regional, closed_at):
    order = OperationOrder(
        source_order_id=order_code,
        order_code=order_code,
        responsible=responsible,
        regional=regional,
        os_type="Manutenção",
        os_subject="Suporte Externo",
        opened_at=closed_at,
        closed_at=closed_at,
        is_closed=True,
    )
    db_session.add(order)
    return order


def test_filter_and_group_by_team_model_agree_even_across_regionals(db_session, ai_user):
    """Achado real: o responsável tem uma atribuição de modelo de equipe numa regional, mas a O.S.
    em si está registrada com uma regional diferente (comum quando o técnico atende fora da sua
    base). O filtro `team_models` sempre casou só pelo nome do responsável - `group_by`
    precisa fazer exatamente o mesmo, senão uma O.S. capturada pelo filtro aparece como "Não
    identificado" no agrupamento."""
    team_model = OperationTeamModel(name="SUPORTE CARRO")
    db_session.add(team_model)
    db_session.flush()

    db_session.add(
        OperationResponsibleAssignment(
            responsible_name="JOAO SILVA",
            regional="UNI - REGIONAL A",
            team_model_id=team_model.id,
        )
    )

    closed_at = datetime(2026, 7, 15, tzinfo=timezone.utc)
    # A O.S. está numa regional DIFERENTE da atribuição de "JOAO SILVA" - é exatamente o cenário
    # relatado (a O.S. entra no filtro por nome, mas antes não entrava no agrupamento por regional).
    _make_order(db_session, order_code="OS-1", responsible="JOAO SILVA", regional="UNI - REGIONAL B", closed_at=closed_at)
    # Sem nenhuma atribuição - deve permanecer "Não identificado" nos dois caminhos.
    _make_order(db_session, order_code="OS-2", responsible="MARIA SEM EQUIPE", regional="UNI - REGIONAL B", closed_at=closed_at)
    db_session.flush()

    filtered = ai_queries.aggregate_orders(
        db_session, ai_user, group_by="regional", metric="quantidade_fechada",
        date_from=DATE_FROM, date_to=DATE_TO, team_models=["SUPORTE CARRO"],
    )
    filtered_total = sum(item["quantity"] for item in filtered)

    grouped = ai_queries.aggregate_orders(
        db_session, ai_user, group_by="team_model", metric="quantidade_fechada",
        date_from=DATE_FROM, date_to=DATE_TO,
    )
    grouped_by_label = {item["label"]: item["quantity"] for item in grouped}

    assert filtered_total == 1
    assert grouped_by_label.get("SUPORTE CARRO") == 1
    assert grouped_by_label.get("Não identificado") == 1
    # A regra central pedida: quem entra no filtro por um modelo tem que aparecer com esse mesmo
    # modelo no agrupamento - nunca em "Não identificado".
    assert filtered_total == grouped_by_label["SUPORTE CARRO"]


@pytest.mark.parametrize("metric", ["quantidade_aberta", "quantidade_fechada", "quantidade_atrasada", "quantidade_backlog"])
def test_filter_and_group_by_team_model_agree_across_metrics(db_session, ai_user, metric):
    team_model = OperationTeamModel(name="RURAL")
    db_session.add(team_model)
    db_session.flush()
    db_session.add(
        OperationResponsibleAssignment(responsible_name="PEDRO", regional="UNI - REGIONAL A", team_model_id=team_model.id)
    )

    reference = datetime(2026, 7, 10, tzinfo=timezone.utc)
    order = OperationOrder(
        source_order_id="OS-3",
        order_code="OS-3",
        responsible="PEDRO",
        regional="UNI - REGIONAL B",
        os_type="Manutenção",
        os_subject="Suporte Externo",
        opened_at=reference,
        closed_at=None,
        is_closed=False,
        sla_status="out_of_time",
    )
    db_session.add(order)
    db_session.flush()

    filtered = ai_queries.aggregate_orders(
        db_session, ai_user, group_by="regional", metric=metric,
        date_from=DATE_FROM, date_to=DATE_TO, team_models=["RURAL"],
    )
    filtered_total = sum(item["quantity"] for item in filtered)

    grouped = ai_queries.aggregate_orders(
        db_session, ai_user, group_by="team_model", metric=metric,
        date_from=DATE_FROM, date_to=DATE_TO,
    )
    grouped_by_label = {item["label"]: item["quantity"] for item in grouped}

    assert filtered_total == grouped_by_label.get("RURAL", 0)
