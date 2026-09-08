"""Quadro por filial da Visão Geral executiva (`GET /operations/overview/regional-matrix`).

O ponto central destes testes é o contrato de escopo de filtro por coluna, que é a parte da
tela mais fácil de alguém reimplementar errado depois: "abertas" é demanda (ignora quem executa),
"em aberto" é estoque (ignora período e quem executa) e "finalizadas"/SLA são produção (respeitam
todos os filtros).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

from app.core.security import get_current_user
from app.main import app
from app.modules.operations.models import (
    OperationOrder,
    OperationResponsibleAssignment,
    OperationTeamModel,
)
from app.modules.operations.period import OPERATIONS_TIMEZONE, current_month_bounds

ENDPOINT = "/api/operations/overview/regional-matrix"


def _utc_at(day: date, hour: int = 12) -> datetime:
    return datetime.combine(day, time(hour=hour), tzinfo=OPERATIONS_TIMEZONE).astimezone(timezone.utc)


def _order(source_order_id: str, **overrides) -> OperationOrder:
    defaults = dict(
        source="ixc",
        source_order_id=source_order_id,
        order_code=source_order_id.upper(),
        sector="Suporte Externo Fibra",
        regional="UNI - NORTE",
        raw_payload={},
    )
    defaults.update(overrides)
    return OperationOrder(**defaults)


def _closed(source_order_id: str, day: date, *, sla_status: str, **overrides) -> OperationOrder:
    return _order(
        source_order_id,
        status="Finalizada",
        status_code="F",
        is_closed=True,
        sla_status=sla_status,
        opened_at=_utc_at(day, 8),
        closed_at=_utc_at(day, 10),
        **overrides,
    )


def _open(source_order_id: str, day: date, **overrides) -> OperationOrder:
    return _order(
        source_order_id,
        status="Aberta",
        status_code="A",
        is_closed=False,
        opened_at=_utc_at(day, 8),
        closed_at=None,
        **overrides,
    )


def _team_models(db_session) -> tuple[OperationTeamModel, OperationTeamModel]:
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
                responsible_name="Técnico Terceiro", regional="UNI - NORTE", team_model_id=outsourced.id
            ),
        ]
    )
    db_session.flush()
    return own, outsourced


def _row(payload: dict, regional: str) -> dict:
    return next(item for item in payload["items"] if item["regional"] == regional)


def test_opened_ignores_team_model_while_completed_and_sla_respect_it(client, db_session):
    """A regra do módulo: abertura é demanda, não produção. Filtrar por modelo de equipe muda
    "finalizadas" e SLA, e NÃO pode mudar "abertas" - senão o diretor vê a demanda encolher só
    porque escolheu um time."""
    _, date_to = current_month_bounds()
    _team_models(db_session)
    db_session.add_all(
        [
            _closed("rm-own-on-time", date_to, sla_status="on_time", responsible="Técnico Próprio"),
            _closed("rm-own-late", date_to, sla_status="out_of_time", responsible="Técnico Próprio"),
            _closed("rm-third-on-time", date_to, sla_status="on_time", responsible="Técnico Terceiro"),
            _closed("rm-third-late-2", date_to, sla_status="out_of_time", responsible="Técnico Terceiro"),
            _closed("rm-third-late-3", date_to, sla_status="out_of_time", responsible="Técnico Terceiro"),
        ]
    )
    db_session.flush()
    params = {"date_from": date_to.isoformat(), "date_to": date_to.isoformat()}

    unfiltered = client.get(ENDPOINT, params=params)
    filtered = client.get(ENDPOINT, params={**params, "team_models": "EQUIPE PRÓPRIA"})

    assert unfiltered.status_code == 200
    assert filtered.status_code == 200
    unfiltered_row = _row(unfiltered.json(), "UNI - NORTE")
    filtered_row = _row(filtered.json(), "UNI - NORTE")

    # Demanda: idêntica nas duas chamadas.
    assert unfiltered_row["opened"] == 5
    assert filtered_row["opened"] == 5
    # Produção e prazo: recortados pelo modelo de equipe.
    assert unfiltered_row["completed"] == 5
    assert unfiltered_row["sla_rate"] == 40.0
    assert filtered_row["completed"] == 2
    assert filtered_row["sla_rate"] == 50.0
    assert filtered.json()["opened_ignores_team_scope"] is True


def test_opened_ignores_responsible_filter(client, db_session):
    _, date_to = current_month_bounds()
    _team_models(db_session)
    db_session.add_all(
        [
            _closed("rm-resp-a", date_to, sla_status="on_time", responsible="Técnico Próprio"),
            _closed("rm-resp-b", date_to, sla_status="on_time", responsible="Técnico Terceiro"),
        ]
    )
    db_session.flush()
    params = {
        "date_from": date_to.isoformat(),
        "date_to": date_to.isoformat(),
        "responsibles": "Técnico Próprio",
    }

    response = client.get(ENDPOINT, params=params)

    assert response.status_code == 200
    row = _row(response.json(), "UNI - NORTE")
    assert row["opened"] == 2
    assert row["completed"] == 1


def test_backlog_is_a_stock_that_ignores_the_selected_period_and_the_team_filter(client, db_session):
    """"Em aberto" é retrato de agora: uma O.S. aberta fora do período selecionado continua no
    estoque, e o filtro de modelo de equipe não a remove (convenção `_backlog_filters`)."""
    _, date_to = current_month_bounds()
    old_day = max(date_to - timedelta(days=40), date(date_to.year, 1, 1))
    _team_models(db_session)
    db_session.add_all(
        [
            _open("rm-backlog-old", old_day, responsible="Técnico Terceiro", sla_status="out_of_time"),
            _open("rm-backlog-new", date_to, responsible="Técnico Próprio", sla_status="on_time"),
        ]
    )
    db_session.flush()
    params = {"date_from": date_to.isoformat(), "date_to": date_to.isoformat()}

    response = client.get(ENDPOINT, params={**params, "team_models": "EQUIPE PRÓPRIA"})

    assert response.status_code == 200
    payload = response.json()
    row = _row(payload, "UNI - NORTE")
    # As duas O.S. em aberto entram, mesmo com a antiga fora do período e de outro modelo.
    assert row["backlog"] == 2
    assert row["overdue_backlog"] == 1
    # Só a aberta dentro do período conta como demanda do período.
    assert row["opened"] == 1
    assert payload["backlog_ignores_period"] is True
    assert payload["backlog_ignores_team_scope"] is True


def test_total_recomputes_sla_from_counts_instead_of_averaging_rates(client, db_session):
    """Média de percentuais das filiais daria um SLA que não corresponde a nenhuma O.S. real."""
    _, date_to = current_month_bounds()
    db_session.add_all(
        [
            # Filial pequena: 1 de 1 no prazo (100%).
            _closed("rm-small-1", date_to, sla_status="on_time", regional="UNI - SUL"),
            # Filial grande: 1 de 4 no prazo (25%).
            _closed("rm-big-1", date_to, sla_status="on_time", regional="UNI - NORTE"),
            _closed("rm-big-2", date_to, sla_status="out_of_time", regional="UNI - NORTE"),
            _closed("rm-big-3", date_to, sla_status="out_of_time", regional="UNI - NORTE"),
            _closed("rm-big-4", date_to, sla_status="out_of_time", regional="UNI - NORTE"),
        ]
    )
    db_session.flush()

    response = client.get(
        ENDPOINT, params={"date_from": date_to.isoformat(), "date_to": date_to.isoformat()}
    )

    assert response.status_code == 200
    payload = response.json()
    assert _row(payload, "UNI - SUL")["sla_rate"] == 100.0
    assert _row(payload, "UNI - NORTE")["sla_rate"] == 25.0
    # 2 no prazo de 5 medíveis = 40%, não a média de 100% e 25% (62,5%).
    assert payload["total"]["sla_rate"] == 40.0
    assert payload["total"]["completed"] == 5
    assert payload["total"]["opened"] == 5


def test_items_are_alphabetical_and_include_regionals_that_only_have_backlog(client, db_session):
    _, date_to = current_month_bounds()
    db_session.add_all(
        [
            _closed("rm-order-c", date_to, sla_status="on_time", regional="UNI - CENTRO"),
            _open("rm-order-a", date_to, regional="UNI - ALFA", sla_status="on_time"),
            _order(
                "rm-order-no-regional",
                regional=None,
                status="Aberta",
                status_code="A",
                is_closed=False,
                opened_at=_utc_at(date_to, 8),
                sla_status="on_time",
            ),
        ]
    )
    db_session.flush()

    response = client.get(
        ENDPOINT, params={"date_from": date_to.isoformat(), "date_to": date_to.isoformat()}
    )

    assert response.status_code == 200
    labels = [item["regional"] for item in response.json()["items"]]
    assert labels == sorted(labels)
    assert "UNI - ALFA" in labels
    assert "Não identificada" in labels


def test_sla_columns_are_blank_without_view_sla_permission(client, db_session):
    """A tela é compartilhada entre perfis: sem `operations:view_sla` o quadro continua vindo com
    os volumes, só as colunas de prazo ficam em branco."""
    _, date_to = current_month_bounds()
    db_session.add_all(
        [
            _closed("rm-perm-1", date_to, sla_status="on_time"),
            _closed("rm-perm-2", date_to, sla_status="out_of_time"),
        ]
    )
    db_session.flush()
    params = {"date_from": date_to.isoformat(), "date_to": date_to.isoformat()}

    def user_with(*permissions: str):
        return SimpleNamespace(
            id=903,
            role="workspace_restricted",
            managed_regional=None,
            managed_regionals=[],
            access_profiles=[
                SimpleNamespace(
                    active=True,
                    permissions=[SimpleNamespace(permission=permission) for permission in permissions],
                )
            ],
        )

    try:
        app.dependency_overrides[get_current_user] = lambda: user_with("operations:read")
        without_sla = client.get(ENDPOINT, params=params)

        app.dependency_overrides[get_current_user] = lambda: user_with(
            "operations:read", "operations:view_sla"
        )
        with_sla = client.get(ENDPOINT, params=params)
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert without_sla.status_code == 200
    payload = without_sla.json()
    row = _row(payload, "UNI - NORTE")
    assert payload["sla_available"] is False
    assert row["completed"] == 2
    assert row["opened"] == 2
    assert row["sla_rate"] is None
    assert row["completed_on_time"] is None
    assert payload["total"]["sla_rate"] is None

    assert with_sla.status_code == 200
    assert with_sla.json()["sla_available"] is True
    assert _row(with_sla.json(), "UNI - NORTE")["sla_rate"] == 50.0


def test_regional_scope_of_the_user_restricts_the_table(client, db_session):
    """O escopo regional pertence ao usuário, não ao filtro da tela - um gestor regional recebe a
    mesma tabela, já recortada, e nenhuma linha das outras filiais."""
    _, date_to = current_month_bounds()
    db_session.add_all(
        [
            _closed("rm-scope-mine", date_to, sla_status="on_time", regional="UNI - NORTE"),
            _closed("rm-scope-other", date_to, sla_status="on_time", regional="UNI - SUL"),
        ]
    )
    db_session.flush()

    scoped_user = SimpleNamespace(
        id=904,
        role="regional_manager_viewer",
        managed_regional=None,
        managed_regionals=["UNI - NORTE"],
        access_profiles=[
            SimpleNamespace(
                active=True,
                permissions=[
                    SimpleNamespace(permission="operations:read"),
                    SimpleNamespace(permission="operations:view_sla"),
                ],
            )
        ],
    )

    try:
        app.dependency_overrides[get_current_user] = lambda: scoped_user
        response = client.get(
            ENDPOINT, params={"date_from": date_to.isoformat(), "date_to": date_to.isoformat()}
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    payload = response.json()
    assert [item["regional"] for item in payload["items"]] == ["UNI - NORTE"]
    assert payload["total"]["completed"] == 1
