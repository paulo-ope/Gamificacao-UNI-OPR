"""Regression tests for build_portal_team_summary (services/portal_dashboard.py) - the
regional_manager_viewer path: unlike a regular collaborator user, this account has no
collaborator_id, only users.managed_regional, and must see the aggregate of every collaborator
scored in that regional for the latest run."""

from datetime import datetime, timezone

from app.models import CalculationRun, Collaborator, CollaboratorScore, User
from app.services.portal_dashboard import build_portal_summary, build_portal_team_summary


def _make_run(db_session, **overrides):
    defaults = dict(
        reference_month=7,
        reference_year=2026,
        regional=None,
        status="approved",
        point_value=1.0,
        created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    run = CalculationRun(**defaults)
    db_session.add(run)
    db_session.flush()
    return run


def _make_score(db_session, run, collaborator, **overrides):
    defaults = dict(
        calculation_run_id=run.id,
        collaborator_id=collaborator.id,
        service_orders_count=10,
        gross_points=100.0,
        penalty_points=10.0,
        net_points=90.0,
        health_multiplier=1.0,
        final_points=90.0,
        estimated_payment=90.0,
    )
    defaults.update(overrides)
    score = CollaboratorScore(**defaults)
    db_session.add(score)
    db_session.flush()
    return score


def test_team_summary_without_managed_regional_returns_message(db_session):
    manager = User(name="Gestor", email="gestor@pytest.local", role="regional_manager_viewer", active=True, password_hash="x")
    db_session.add(manager)
    db_session.flush()
    run = _make_run(db_session)

    result = build_portal_team_summary(db_session, manager)
    assert result["regional"] is None
    assert "vinculada" in result["message"]


def test_team_summary_aggregates_only_managed_regional(db_session, make_collaborator):
    manager = User(
        name="Gestor Rolim",
        email="gestor-rolim@pytest.local",
        role="regional_manager_viewer",
        active=True,
        password_hash="x",
        managed_regional="UNI SUL",
    )
    db_session.add(manager)
    db_session.flush()

    run = _make_run(db_session)
    in_regional_a = make_collaborator(name="A", regional="UNI SUL")
    in_regional_b = make_collaborator(name="B", regional="UNI SUL")
    other_regional = make_collaborator(name="C", regional="UNI NORTE")
    score_a = _make_score(db_session, run, in_regional_a, final_points=100.0)
    score_b = _make_score(db_session, run, in_regional_b, final_points=50.0, health_multiplier=0.8)
    score_c = _make_score(db_session, run, other_regional, final_points=999.0)

    # serialize_run recalcula final_points a partir das O.S reais quando não há cache
    # (services/calculation.py:_run_extra_summaries) - sem nenhuma O.S no banco, isso zeraria os
    # valores que acabamos de definir. Pré-populamos o cache (mesmo formato de
    # cached_score_summaries) pra este teste focar só na agregação por regional, não no motor de
    # cálculo em si (isso já é coberto em test_calculation_closure.py/test_scoring_detail.py).
    run.result_summary = {
        "score_summaries": {
            str(in_regional_a.id): {"final_points": score_a.final_points, "sla_out_service_orders": 0},
            str(in_regional_b.id): {
                "final_points": score_b.final_points,
                "health_multiplier": 0.8,
                "sla_out_service_orders": 2,
            },
            str(other_regional.id): {"final_points": score_c.final_points},
        }
    }
    db_session.flush()

    result = build_portal_team_summary(db_session, manager)
    assert result["regional"] == "UNI SUL"
    assert result["totals"]["collaborators"] == 2
    assert result["totals"]["final_points"] == 150.0
    assert result["totals"]["sla_out_service_orders"] == 2
    assert result["totals"]["sla_rate"] == 90.0
    assert [item["collaborator_name"] for item in result["ranking"]] == ["A", "B"]
    assert result["ranking"][1]["performance_band"] == "Abaixo da faixa"
    assert result["attention"][0]["collaborator_name"] == "B"
    assert result["history"][0]["sla_rate"] == 90.0
    assert any(item["label"] == "Abaixo da faixa" and item["collaborators"] == 1 for item in result["bands"])


def test_team_summary_excludes_inactive_or_unregistered_collaborators(db_session, make_collaborator):
    manager = User(
        name="Gestor Rolim",
        email="gestor-cadastro@pytest.local",
        role="regional_manager_viewer",
        active=True,
        password_hash="x",
        managed_regional="UNI SUL",
    )
    db_session.add(manager)
    db_session.flush()

    run = _make_run(db_session)
    registered = make_collaborator(name="Cadastrado", regional="UNI SUL")
    inactive = make_collaborator(name="Inativo", regional="UNI SUL")
    unregistered = make_collaborator(name="Nao cadastrado", regional="UNI SUL", registered=False)
    inactive.active = False

    registered_score = _make_score(db_session, run, registered, final_points=100.0)
    inactive_score = _make_score(db_session, run, inactive, final_points=90.0)
    unregistered_score = _make_score(db_session, run, unregistered, final_points=80.0)
    run.result_summary = {
        "score_summaries": {
            str(registered.id): {"final_points": registered_score.final_points},
            str(inactive.id): {"final_points": inactive_score.final_points},
            str(unregistered.id): {"final_points": unregistered_score.final_points},
        }
    }
    db_session.flush()

    result = build_portal_team_summary(db_session, manager)

    assert result["totals"]["collaborators"] == 1
    assert result["totals"]["final_points"] == 100.0
    assert [item["collaborator_name"] for item in result["ranking"]] == ["Cadastrado"]


def test_summary_user_permissions_reflect_role(db_session):
    """Regression: build_portal_summary devolvia a instância crua do ORM em "user", e
    PortalSummaryOut.user (UserOut) lia isso via from_attributes - como `permissions` e
    `collaborator_name` não são colunas reais, sempre caíam no default do schema ([]/None) em vez
    de calcular de verdade. Isso deixava a lista de permissões sempre vazia, quebrando qualquer
    tela que decida o que mostrar a partir de summary.user.permissions (ex: aba "Minha equipe")."""
    manager = User(
        name="Gestor",
        email="gestor-permissoes@pytest.local",
        role="regional_manager_viewer",
        active=True,
        password_hash="x",
        managed_regional="UNI SUL",
    )
    db_session.add(manager)
    db_session.flush()

    result = build_portal_summary(db_session, manager)
    assert "portal:read_regional_summary" in result["user"]["permissions"]
