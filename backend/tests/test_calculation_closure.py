"""Regression tests for backend/app/services/calculation_closure.py."""
from datetime import datetime, timezone

import pytest

from app.models import AppSetting, CalculationRun, HealthRule, ScoringGroup, ScoringSubjectRule, ServiceOrder
from app.services.calculation_closure import ensure_status_transition_allowed, update_run_status


def test_paid_and_cancelled_are_truly_terminal():
    """Regression: paid->paid and cancelled->cancelled used to be silent no-ops,
    which would let a paid run re-trigger point-balance application a second time."""
    with pytest.raises(Exception) as excinfo:
        ensure_status_transition_allowed("paid", "paid")
    assert getattr(excinfo.value, "status_code", None) == 409

    with pytest.raises(Exception) as excinfo:
        ensure_status_transition_allowed("cancelled", "cancelled")
    assert getattr(excinfo.value, "status_code", None) == 409


def test_non_terminal_self_transition_is_still_a_permitted_no_op():
    ensure_status_transition_allowed("draft", "draft")
    ensure_status_transition_allowed("review", "review")


def test_normal_status_chain_still_works(db_session, admin_user):
    run = CalculationRun(reference_month=8, reference_year=2026, regional=None, point_value=2.5, status="draft")
    db_session.add(run)
    db_session.flush()

    update_run_status(db_session, run, "review", admin_user)
    update_run_status(db_session, run, "approved", admin_user)
    update_run_status(db_session, run, "paid", admin_user)

    assert run.status == "paid"


def test_same_collaborator_cannot_be_paid_twice_via_aggregate_and_regional_runs(client, db_session, make_collaborator):
    """Regression (critical): an aggregate run (regional=None) and a regional-specific
    run covering the same month used to both be payable independently, double-paying
    any collaborator counted in both."""
    tech = make_collaborator(name="Tech Duplicado", regional="UNI SUL")
    group = ScoringGroup(name="Manutencao", default_points=10.0, active=True)
    db_session.add(group)
    db_session.flush()
    db_session.add(ScoringSubjectRule(group_id=group.id, os_type="Manutencao", os_subject="Reparo", use_group_default=True, active=True))
    db_session.add(AppSetting(key="point_value", value="2.00"))
    db_session.add(HealthRule(name="Boa", min_sla=0, max_recurrence_rate=100, multiplier=1.0, active=True))
    db_session.add(
        ServiceOrder(
            os_code="OS-DUP-1", contract_id="C-1", customer_login="cli.dup", customer_name="X",
            collaborator_id=tech.id, regional="UNI SUL", os_type="Manutencao", os_subject="Reparo",
            diagnosis="Falha", status="Concluida", sla_status="Dentro do prazo",
            opened_at=datetime(2026, 6, 5, tzinfo=timezone.utc), closed_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
        )
    )
    db_session.commit()

    def calculate(regional):
        resp = client.post("/api/calculation-runs/calculate", json={"reference_month": 6, "reference_year": 2026, "regional": regional})
        assert resp.status_code == 200, resp.text
        return resp.json()

    run_aggregate = calculate(None)
    run_regional = calculate("UNI SUL")

    for status in ["review", "approved", "paid"]:
        resp = client.patch(f"/api/calculation-runs/{run_aggregate['id']}/status", json={"status": status})
        assert resp.status_code == 200, resp.text

    blocked_at = None
    for status in ["review", "approved", "paid"]:
        resp = client.patch(f"/api/calculation-runs/{run_regional['id']}/status", json={"status": status})
        if resp.status_code != 200:
            blocked_at = (status, resp.status_code)
            break

    assert blocked_at is not None, "the regional run must be blocked before reaching 'paid' once the aggregate run already paid this collaborator"
    assert blocked_at[1] == 409

    run_regional_final = client.get(f"/api/calculation-runs/{run_regional['id']}").json()
    assert run_regional_final["status"] != "paid"
