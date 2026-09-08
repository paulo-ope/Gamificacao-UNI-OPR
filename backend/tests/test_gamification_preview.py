"""Prévia do valor da gamificação para a Visão Geral executiva
(`GET /api/dashboard/gamification-preview`).

"Valor de agora" aqui é o rascunho do mês corrente que `recalculate_current_period` regrava a
cada ciclo do IXC - não o último fechamento pago. Estes testes travam três coisas fáceis de
quebrar depois: os totais vêm das linhas `collaborator_scores` (achado C1), o escopo regional do
usuário é respeitado, e um fechamento avulso de uma única filial não é servido como se fosse o
total da empresa.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.security import get_current_user
from app.main import app
from app.models import CalculationRun, CollaboratorScore
from app.services.calculation_closure import current_reference_period

ENDPOINT = "/api/dashboard/gamification-preview"


def _score(run_id: int, collaborator_id: int, *, final_points: float, estimated_payment: float) -> CollaboratorScore:
    return CollaboratorScore(
        calculation_run_id=run_id,
        collaborator_id=collaborator_id,
        service_orders_count=10,
        gross_points=final_points,
        penalty_points=0.0,
        net_points=final_points,
        health_multiplier=1.0,
        health_status="Boa",
        final_points=final_points,
        estimated_payment=estimated_payment,
        balance_adjustment_points=0.0,
        balance_after=final_points,
    )


@pytest.fixture()
def current_month_draft(db_session, make_collaborator):
    """Rascunho do mês corrente com o cache JSON DE PROPÓSITO divergente das linhas: a prévia tem
    que devolver a soma das linhas (R$ 300,00), nunca o total gravado (R$ 111,11)."""
    reference_month, reference_year = current_reference_period()
    run = CalculationRun(
        reference_month=reference_month,
        reference_year=reference_year,
        regional=None,
        point_value=0.50,
        status="draft",
        created_at=datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc),
    )
    db_session.add(run)
    db_session.flush()

    north = make_collaborator(name="Técnico Norte", regional="UNI - PORTO VELHO")
    south = make_collaborator(name="Técnico Sul", regional="UNI - VILHENA")
    db_session.add_all(
        [
            _score(run.id, north.id, final_points=200.0, estimated_payment=100.0),
            _score(run.id, south.id, final_points=400.0, estimated_payment=200.0),
        ]
    )
    run.result_summary = {
        "cards": {"estimated_payment": 111.11, "final_points": 222.22},
        "estimated_payment": 111.11,
        "final_points": 222.22,
    }
    db_session.flush()
    return run


def _user(*, regionals: list[str] | None = None, role: str = "admin", permissions=("dashboard:read",)):
    return SimpleNamespace(
        id=905,
        role=role,
        managed_regional=None,
        managed_regionals=regionals or [],
        access_profiles=[
            SimpleNamespace(
                active=True,
                permissions=[SimpleNamespace(permission=permission) for permission in permissions],
            )
        ],
    )


def test_preview_reads_the_current_month_draft_and_totals_come_from_the_score_rows(
    client, current_month_draft
):
    response = client.get(ENDPOINT)

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["is_preview"] is True
    assert payload["status"] == "draft"
    assert payload["reference_month"] == current_month_draft.reference_month
    assert payload["reference_year"] == current_month_draft.reference_year
    # Soma das linhas, não o total gravado no JSON (achado C1).
    assert payload["estimated_payment"] == 300.0
    assert payload["final_points"] == 600.0
    assert payload["collaborators"] == 2
    assert payload["point_value"] == 0.5
    # A tela precisa poder dizer "prévia de tal hora" - sem isso um número velho parece fresco.
    assert payload["calculated_at"] is not None


def test_preview_is_unavailable_when_the_current_month_has_no_run(client, db_session):
    response = client.get(ENDPOINT)

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False
    assert payload["estimated_payment"] is None
    assert payload["unavailable_reason"]


def test_preview_ignores_a_closing_of_a_single_regional(client, db_session, make_collaborator):
    """Um fechamento avulso de uma filial não é o total da empresa: melhor indisponível do que um
    número parcial disfarçado de total."""
    reference_month, reference_year = current_reference_period()
    run = CalculationRun(
        reference_month=reference_month,
        reference_year=reference_year,
        regional="UNI - VILHENA",
        point_value=0.5,
        status="draft",
    )
    db_session.add(run)
    db_session.flush()
    collaborator = make_collaborator(name="Técnico Avulso", regional="UNI - VILHENA")
    db_session.add(_score(run.id, collaborator.id, final_points=100.0, estimated_payment=50.0))
    db_session.flush()

    response = client.get(ENDPOINT)

    assert response.status_code == 200
    assert response.json()["available"] is False


def test_preview_is_scoped_to_the_regionals_of_the_user(client, current_month_draft):
    del current_month_draft
    try:
        app.dependency_overrides[get_current_user] = lambda: _user(
            regionals=["UNI - PORTO VELHO"], role="regional_manager_viewer"
        )
        response = client.get(ENDPOINT)
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    # Só o colaborador da filial do gestor.
    assert payload["estimated_payment"] == 100.0
    assert payload["collaborators"] == 1
    assert payload["scope_regionals"] == ["UNI - PORTO VELHO"]


def test_regional_manager_without_a_regional_gets_no_implicit_company_scope(client, current_month_draft):
    del current_month_draft
    try:
        app.dependency_overrides[get_current_user] = lambda: _user(
            regionals=[], role="regional_manager_viewer"
        )
        response = client.get(ENDPOINT)
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False
    assert payload["estimated_payment"] is None


def test_preview_requires_the_dashboard_permission(client, current_month_draft):
    del current_month_draft
    try:
        app.dependency_overrides[get_current_user] = lambda: _user(permissions=("operations:read",))
        response = client.get(ENDPOINT)
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 403
