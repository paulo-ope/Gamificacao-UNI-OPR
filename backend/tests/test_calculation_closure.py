"""Regression tests for backend/app/services/calculation_closure.py."""
from datetime import datetime, timezone

import pytest

from app.models import AppSetting, CalculationRun, CollaboratorScore, HealthRule, ScoringGroup, ScoringSubjectRule, ServiceOrder
from app.services.calculation_closure import ensure_status_transition_allowed, pick_run_by_status_priority, update_run_status
from sqlalchemy import select


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


def test_paid_run_wins_over_a_more_recent_cancelled_review(db_session):
    """Regression: telas que buscam "o fechamento deste periodo" ordenavam so por
    created_at desc, ignorando status - uma revisao explicita criada (e depois cancelada) DEPOIS
    de um fechamento pago "vencia" so por ser mais nova, escondendo o pagamento real ja fechado.
    Pago deve sempre vencer sobre qualquer outro status, independente de quando foi criado."""
    paid_run = CalculationRun(reference_month=7, reference_year=2026, regional=None, point_value=2.5, status="paid")
    db_session.add(paid_run)
    db_session.flush()

    later_cancelled_review = CalculationRun(
        reference_month=7, reference_year=2026, regional=None, point_value=2.5, status="cancelled"
    )
    db_session.add(later_cancelled_review)
    db_session.flush()
    assert later_cancelled_review.created_at >= paid_run.created_at

    stmt = select(CalculationRun).where(
        CalculationRun.reference_month == 7, CalculationRun.reference_year == 2026, CalculationRun.regional.is_(None)
    )
    chosen = pick_run_by_status_priority(db_session, stmt)
    assert chosen.id == paid_run.id


def test_non_cancelled_wins_over_a_more_recent_cancelled_run_when_nothing_is_paid(db_session):
    draft_run = CalculationRun(reference_month=9, reference_year=2026, regional=None, point_value=2.5, status="draft")
    db_session.add(draft_run)
    db_session.flush()

    later_cancelled = CalculationRun(reference_month=9, reference_year=2026, regional=None, point_value=2.5, status="cancelled")
    db_session.add(later_cancelled)
    db_session.flush()

    stmt = select(CalculationRun).where(
        CalculationRun.reference_month == 9, CalculationRun.reference_year == 2026, CalculationRun.regional.is_(None)
    )
    chosen = pick_run_by_status_priority(db_session, stmt)
    assert chosen.id == draft_run.id


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
        # create_revision=True: 06/2026 e um mes fixo no passado (nao o mes corrente de verdade),
        # entao precisa bypassar a trava de "periodo ja encerrado por ter virado o mes" - o foco
        # deste teste e a protecao contra pagamento duplicado, nao o bloqueio de periodo passado.
        resp = client.post(
            "/api/calculation-runs/calculate",
            json={"reference_month": 6, "reference_year": 2026, "regional": regional, "create_revision": True},
        )
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


def test_calculate_scores_zeroes_estimated_payment_for_unregistered_collaborator(client, db_session, make_collaborator):
    """Regression: a collaborator auto-created from an import (is_registered=False) must never
    accrue a payable estimated_payment, even though their points/O.S stay visible for tracking.
    Guaranteeing they won't be paid has to start at calculation time, not at a CSV export filter."""
    unregistered = make_collaborator(name="Nao Cadastrado", regional="UNI SUL", registered=False)
    # Colaborador cadastrado extra, apenas para estabelecer a saude/SLA da regional: uma O.S de
    # colaborador nao cadastrado nunca conta para o calculo de saude da regional (regra ja existente,
    # ver calculate_regional_health) - sem isto, health_by_regional ficaria vazio e o multiplicador
    # do nao cadastrado cairia para "abaixo da faixa minima" (0x) por falta de referencia, mascarando
    # o que este teste realmente quer verificar (o zeramento do estimated_payment).
    baseline = make_collaborator(name="Colaborador Base", regional="UNI SUL", registered=True)
    group = ScoringGroup(name="Instalacao", default_points=10.0, active=True)
    db_session.add(group)
    db_session.flush()
    db_session.add(ScoringSubjectRule(group_id=group.id, os_type="Instalacao", os_subject="Padrao", use_group_default=True, active=True))
    db_session.add(AppSetting(key="point_value", value="2.00"))
    db_session.add(HealthRule(name="Boa", min_sla=0, max_recurrence_rate=100, multiplier=1.0, active=True))
    db_session.add(
        ServiceOrder(
            os_code="OS-BASE-1", contract_id="C-0", customer_login="cli.base", customer_name="Z",
            collaborator_id=baseline.id, regional="UNI SUL", os_type="Instalacao", os_subject="Padrao",
            diagnosis="Falha", status="Concluida", sla_status="Dentro do prazo",
            opened_at=datetime(2026, 6, 5, tzinfo=timezone.utc), closed_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
        )
    )
    db_session.add(
        ServiceOrder(
            os_code="OS-UNREG-1", contract_id="C-1", customer_login="cli.unreg", customer_name="Y",
            collaborator_id=unregistered.id, regional="UNI SUL", os_type="Instalacao", os_subject="Padrao",
            diagnosis="Falha", status="Concluida", sla_status="Dentro do prazo",
            opened_at=datetime(2026, 6, 5, tzinfo=timezone.utc), closed_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
        )
    )
    db_session.commit()

    resp = client.post(
        "/api/calculation-runs/calculate",
        json={"reference_month": 6, "reference_year": 2026, "regional": "UNI SUL", "create_revision": True},
    )
    assert resp.status_code == 200, resp.text
    run = resp.json()

    score = next(s for s in run["scores"] if s["collaborator_id"] == unregistered.id)
    baseline_score = next(s for s in run["scores"] if s["collaborator_id"] == baseline.id)
    assert score["final_points"] > 0, "points must stay visible for an unregistered collaborator"
    assert score["estimated_payment"] == 0, "an unregistered collaborator must never accrue a payable amount"
    assert baseline_score["estimated_payment"] > 0, "a registered collaborator's payment must remain untouched"
    assert run["result_summary"]["cards"]["estimated_payment"] == baseline_score["estimated_payment"], (
        "the aggregate payable total must exclude the unregistered collaborator entirely"
    )


def test_calculate_scores_populates_financial_breakdowns_from_cached_score_context(client, db_session, make_collaborator):
    """Regression: calculate_scores stores score_summaries with JSON string keys, but the
    financial breakdown builder expects integer collaborator ids. The saved run must still
    include the cost breakdowns used by the dashboard cache."""
    collaborator = make_collaborator(name="Tecnico Financeiro", regional="UNI SUL", registered=True)
    group = ScoringGroup(name="Manutencao", default_points=10.0, active=True)
    db_session.add(group)
    db_session.flush()
    db_session.add(ScoringSubjectRule(group_id=group.id, os_type="Manutencao", os_subject="Reparo", use_group_default=True, active=True))
    db_session.add(AppSetting(key="point_value", value="2.00"))
    db_session.add(HealthRule(name="Boa", min_sla=0, max_recurrence_rate=100, multiplier=1.0, active=True))
    db_session.add(
        ServiceOrder(
            os_code="OS-FIN-1", contract_id="C-1", customer_login="cli.fin", customer_name="X",
            collaborator_id=collaborator.id, regional="UNI SUL", os_type="Manutencao", os_subject="Reparo",
            diagnosis="Falha", status="Concluida", sla_status="Dentro do prazo",
            opened_at=datetime(2026, 6, 5, tzinfo=timezone.utc), closed_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
        )
    )
    db_session.commit()

    resp = client.post(
        "/api/calculation-runs/calculate",
        json={"reference_month": 6, "reference_year": 2026, "regional": "UNI SUL", "create_revision": True},
    )
    assert resp.status_code == 200, resp.text
    summary = resp.json()["result_summary"]

    assert summary["cost_by_regional"] == [{"regional": "UNI SUL", "orders": 1, "estimated_payment": 20.0}]
    assert summary["cost_by_group"][0]["estimated_payment"] == 20.0
    assert summary["cost_by_collaborator"][0]["collaborator_id"] == collaborator.id


def test_marking_run_as_paid_is_blocked_while_unregistered_collaborator_has_payable_amount(db_session, admin_user, make_collaborator):
    """Regression: this is the last-resort safety net, independent of the calculation-time zeroing
    above - even if stale/edited data slips an unregistered collaborator through with a nonzero
    estimated_payment, marking the run as paid must be refused rather than silently paying them."""
    unregistered = make_collaborator(name="Sem Cadastro", regional="UNI SUL", registered=False)
    run = CalculationRun(reference_month=9, reference_year=2026, regional="UNI SUL", point_value=2.0, status="approved")
    db_session.add(run)
    db_session.flush()
    db_session.add(
        CollaboratorScore(
            calculation_run_id=run.id,
            collaborator_id=unregistered.id,
            service_orders_count=1,
            gross_points=10,
            penalty_points=0,
            net_points=10,
            final_points=10,
            estimated_payment=20.0,
        )
    )
    db_session.commit()
    db_session.refresh(run)

    with pytest.raises(Exception) as excinfo:
        update_run_status(db_session, run, "paid", admin_user)
    assert getattr(excinfo.value, "status_code", None) == 409
    assert "não cadastrado" in str(getattr(excinfo.value, "detail", "")).lower()
    assert run.status == "approved", "the run must remain unpaid after the block"
