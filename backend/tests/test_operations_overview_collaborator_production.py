"""Produção por técnico da Visão Geral (`GET /operations/overview/collaborator-production`).

Segundo nível do donut de modelo de equipe ("quem produziu dentro deste modelo"). Os testes travam
as três decisões que motivaram a rota existir em vez de reaproveitar `/operations/sla/collaborators`
(ver `queries.overview_collaborator_production`): agrupa por responsável SEM quebrar por filial,
respeita o filtro de modelo de equipe, e NÃO exige `operations:view_sla` - a resposta não tem dado
de prazo nenhum.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from types import SimpleNamespace

from app.core.security import get_current_user
from app.main import app
from app.modules.operations.models import (
    OperationOrder,
    OperationResponsibleAssignment,
    OperationTeamModel,
)
from app.modules.operations.period import OPERATIONS_TIMEZONE, current_month_bounds

ENDPOINT = "/api/operations/overview/collaborator-production"


def _utc_at(day: date, hour: int = 12) -> datetime:
    return datetime.combine(day, time(hour=hour), tzinfo=OPERATIONS_TIMEZONE).astimezone(timezone.utc)


def _closed(source_order_id: str, day: date, responsible: str, regional: str = "UNI - NORTE") -> OperationOrder:
    return OperationOrder(
        source="ixc",
        source_order_id=source_order_id,
        order_code=source_order_id.upper(),
        sector="Suporte Externo Fibra",
        regional=regional,
        raw_payload={},
        status="Finalizada",
        status_code="F",
        is_closed=True,
        sla_status="on_time",
        responsible=responsible,
        opened_at=_utc_at(day, 8),
        closed_at=_utc_at(day, 10),
    )


def _team_models(db_session) -> None:
    own = OperationTeamModel(name="EQUIPE PRÓPRIA", daily_target=5)
    outsourced = OperationTeamModel(name="TERCEIRIZADA", daily_target=5)
    db_session.add_all([own, outsourced])
    db_session.flush()
    db_session.add_all(
        [
            OperationResponsibleAssignment(
                responsible_name="Técnico Próprio", regional="UNI - NORTE", team_model_id=own.id
            ),
            OperationResponsibleAssignment(
                responsible_name="Outro Próprio", regional="UNI - NORTE", team_model_id=own.id
            ),
            OperationResponsibleAssignment(
                responsible_name="Técnico Terceiro", regional="UNI - NORTE", team_model_id=outsourced.id
            ),
        ]
    )
    db_session.flush()


def test_groups_by_responsible_and_orders_by_production(client, db_session):
    _, date_to = current_month_bounds()
    _team_models(db_session)
    db_session.add_all(
        [
            _closed("cp-1", date_to, "Técnico Próprio"),
            _closed("cp-2", date_to, "Técnico Próprio"),
            _closed("cp-3", date_to, "Técnico Próprio"),
            _closed("cp-4", date_to, "Outro Próprio"),
        ]
    )
    db_session.flush()

    response = client.get(ENDPOINT, params={"date_from": date_to.isoformat(), "date_to": date_to.isoformat()})

    assert response.status_code == 200
    items = response.json()["items"]
    assert [(item["responsible"], item["completed"]) for item in items] == [
        ("Técnico Próprio", 3),
        ("Outro Próprio", 1),
    ]


def test_same_responsible_in_two_regionals_is_a_single_row(db_session, client):
    """A rota de SLA por colaborador agrupa por responsável E filial, o que fazia a mesma pessoa
    virar duas fatias do donut. Aqui o `GROUP BY` é só por responsável - de propósito."""
    _, date_to = current_month_bounds()
    _team_models(db_session)
    db_session.add_all(
        [
            _closed("cp-norte-1", date_to, "Técnico Próprio", regional="UNI - NORTE"),
            _closed("cp-norte-2", date_to, "Técnico Próprio", regional="UNI - NORTE"),
            _closed("cp-sul-1", date_to, "Técnico Próprio", regional="UNI - SUL"),
        ]
    )
    db_session.flush()

    response = client.get(ENDPOINT, params={"date_from": date_to.isoformat(), "date_to": date_to.isoformat()})

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["responsible"] for item in items] == ["Técnico Próprio"]
    assert items[0]["completed"] == 3


def test_team_model_filter_restricts_who_appears(client, db_session):
    _, date_to = current_month_bounds()
    _team_models(db_session)
    db_session.add_all(
        [
            _closed("cp-own", date_to, "Técnico Próprio"),
            _closed("cp-third", date_to, "Técnico Terceiro"),
        ]
    )
    db_session.flush()
    params = {"date_from": date_to.isoformat(), "date_to": date_to.isoformat()}

    response = client.get(ENDPOINT, params={**params, "team_models": "EQUIPE PRÓPRIA"})

    assert response.status_code == 200
    assert [item["responsible"] for item in response.json()["items"]] == ["Técnico Próprio"]


def test_does_not_require_the_sla_permission(client, db_session):
    """Produção por técnico não é dado de prazo: a resposta não tem nenhum campo de SLA, e nome +
    contagem já são alcançáveis nesta tela por quem escolhe um colaborador no filtro. Travado em
    teste porque o caminho fácil (reaproveitar a rota de SLA) traria `operations:view_sla` de
    carona e esconderia o bloco de quem só tem `operations:read`."""
    _, date_to = current_month_bounds()
    _team_models(db_session)
    db_session.add(_closed("cp-only-read", date_to, "Técnico Próprio"))
    db_session.flush()

    try:
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=907,
            role="workspace_restricted",
            managed_regional=None,
            managed_regionals=[],
            access_profiles=[
                SimpleNamespace(
                    active=True,
                    permissions=[SimpleNamespace(permission="operations:read")],
                )
            ],
        )
        response = client.get(ENDPOINT, params={"date_from": date_to.isoformat(), "date_to": date_to.isoformat()})
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    items = response.json()["items"]
    assert items[0]["responsible"] == "Técnico Próprio"
    assert set(items[0].keys()) == {"responsible", "completed"}
