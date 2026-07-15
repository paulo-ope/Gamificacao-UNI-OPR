"""Regression tests for backend/app/services/point_balance.py - the ledger that tracks
warranty debits detected after their original month has already been paid."""
from datetime import datetime, timezone

import pytest

from app.models import (
    AppSetting,
    CalculationRun,
    Collaborator,
    CollaboratorScore,
    PointBalanceEntry,
    RecurrenceClassificationRule,
    ScoringSubjectRule,
    ServiceOrder,
)
from app.services import point_balance


@pytest.fixture()
def paid_june_run(db_session, scoring_setup):
    run = CalculationRun(reference_month=6, reference_year=2026, regional=None, point_value=2.5, status="paid")
    db_session.add(run)
    db_session.flush()
    return run


def _os(collaborator, code, opened, closed=None, **overrides):
    defaults = dict(
        os_code=code, contract_id="C-1", customer_login="cliente.x", customer_name="Cliente X",
        collaborator_id=collaborator.id, regional=collaborator.regional, os_type="Manutencao", os_subject="Reparo",
        diagnosis="Falha", status="Concluida",
        opened_at=opened, closed_at=closed or opened,
    )
    defaults.update(overrides)
    return ServiceOrder(**defaults)


def test_debit_is_attributed_to_original_collaborator_not_the_warranty_visit(db_session, make_collaborator, paid_june_run, recurrence_setup):
    """Regression: the debit must land on whoever earned the original points, not on
    whichever technician happened to attend the warranty visit."""
    tech_original = make_collaborator(name="Tecnico A Original")
    tech_warranty_visit = make_collaborator(name="Tecnico B Garantia")

    original = _os(tech_original, "OS-JUN-1", datetime(2026, 6, 25, tzinfo=timezone.utc))
    later = _os(tech_warranty_visit, "OS-JUL-1", datetime(2026, 7, 10, tzinfo=timezone.utc))
    db_session.add_all([original, later])
    db_session.flush()

    created = point_balance.detect_post_payment_warranty_debits(db_session, [later])
    db_session.commit()

    assert len(created) == 1
    entry = created[0]
    assert entry.collaborator_id == tech_original.id
    assert entry.collaborator_id != tech_warranty_visit.id


def test_detection_is_idempotent_for_the_same_pair(db_session, make_collaborator, paid_june_run, recurrence_setup):
    collaborator = make_collaborator()
    original = _os(collaborator, "OS-JUN-1", datetime(2026, 6, 25, tzinfo=timezone.utc))
    later = _os(collaborator, "OS-JUL-1", datetime(2026, 7, 10, tzinfo=timezone.utc))
    db_session.add_all([original, later])
    db_session.flush()

    first = point_balance.detect_post_payment_warranty_debits(db_session, [later])
    db_session.commit()
    second = point_balance.detect_post_payment_warranty_debits(db_session, [later])
    db_session.commit()

    assert len(first) == 1
    assert len(second) == 0, "the same original/later pair must not create a duplicate debit"


def test_full_ledger_cycle_preview_apply_carry_over_revert(db_session, make_collaborator, paid_june_run, recurrence_setup):
    collaborator = make_collaborator()
    original = _os(collaborator, "OS-JUN-1", datetime(2026, 6, 25, tzinfo=timezone.utc))
    later = _os(collaborator, "OS-JUL-1", datetime(2026, 7, 10, tzinfo=timezone.utc))
    db_session.add_all([original, later])
    db_session.flush()

    created = point_balance.detect_post_payment_warranty_debits(db_session, [later])
    db_session.commit()
    entry = created[0]
    assert entry.points == -15.0  # scoring_setup's Manutencao/Reparo default is 15 pts, fully annulled
    assert entry.status == "pending"

    # Draft preview must NOT mutate anything - it's shown before the July run is approved/paid.
    preview = point_balance.preview_pending_adjustment(db_session, collaborator.id, 10.0)
    assert preview["adjustment_points"] == -15.0
    assert preview["projected_balance"] == -5.0
    assert point_balance.pending_entries_for_collaborator(db_session, collaborator.id)[0].status == "pending"

    july_run = CalculationRun(reference_month=7, reference_year=2026, regional=None, point_value=2.5, status="draft")
    db_session.add(july_run)
    db_session.flush()
    july_score = CollaboratorScore(
        calculation_run_id=july_run.id, collaborator_id=collaborator.id, service_orders_count=1,
        gross_points=10.0, penalty_points=0.0, net_points=10.0, health_multiplier=1.0, health_status="Boa",
        final_points=10.0, estimated_payment=25.0,
    )
    db_session.add(july_score)
    db_session.flush()

    result = point_balance.apply_pending_entries_for_paid_run(
        db_session, collaborator=collaborator, calculation_run=july_run,
        reference_month=7, reference_year=2026, available_points=10.0,
    )
    db_session.commit()

    assert result["applied_points"] == -15.0
    assert result["balance_after"] == -5.0

    carry_over = point_balance.pending_entries_for_collaborator(db_session, collaborator.id)
    assert len(carry_over) == 1
    assert carry_over[0].entry_type == "period_settlement"
    assert carry_over[0].points == -5.0

    original_entry = db_session.get(PointBalanceEntry, entry.id)
    assert original_entry.status == "applied"
    assert point_balance.current_balance(db_session, collaborator.id) == -5.0

    with pytest.raises(Exception) as excinfo:
        point_balance.revert_entry(db_session, entry.id)
    assert getattr(excinfo.value, "status_code", None) == 409, "an already-applied entry must not be revertible directly"

    reverted = point_balance.revert_entry(db_session, carry_over[0].id, reason="teste")
    db_session.commit()
    assert reverted.status == "reverted"


def test_reverting_before_payment_restores_gross_points_when_run_is_paid(db_session, make_collaborator, paid_june_run, recurrence_setup, admin_user):
    """Regression: if the pending debit was previewed in a draft and then reverted
    (false positive) BEFORE the run was marked paid, the paid-time apply logic used to
    only recompute when applied_points != 0 - so a reverted debit left the score stuck
    at the discounted preview value instead of restoring the gross points."""
    from app.api.routes.calculation_runs import _apply_point_balance_after_payment

    collaborator = make_collaborator()
    original = _os(collaborator, "OS-JUN-1", datetime(2026, 6, 25, tzinfo=timezone.utc))
    later = _os(collaborator, "OS-JUL-1", datetime(2026, 7, 10, tzinfo=timezone.utc))
    db_session.add_all([original, later])
    db_session.flush()

    created = point_balance.detect_post_payment_warranty_debits(db_session, [later])
    db_session.commit()
    entry = created[0]

    july_run = CalculationRun(
        reference_month=7, reference_year=2026, regional=None, point_value=2.5, status="approved",
        result_summary={
            "score_summaries": {
                str(collaborator.id): {
                    "gross_final_points": 20.0, "gross_estimated_payment": 50.0,
                    "final_points": 5.0, "estimated_payment": 12.5,
                    "balance_adjustment_points": -15.0, "balance_after": 5.0,
                }
            }
        },
    )
    db_session.add(july_run)
    db_session.flush()
    score = CollaboratorScore(
        calculation_run_id=july_run.id, collaborator_id=collaborator.id, service_orders_count=2,
        gross_points=20.0, penalty_points=0.0, net_points=20.0, health_multiplier=1.0, health_status="Boa",
        final_points=5.0, estimated_payment=12.5, balance_adjustment_points=-15.0, balance_after=5.0,
    )
    db_session.add(score)
    db_session.flush()

    point_balance.revert_entry(db_session, entry.id, reason="diagnostico de garantia incorreto")
    db_session.commit()

    changed = _apply_point_balance_after_payment(db_session, july_run, admin_user)
    db_session.commit()
    db_session.refresh(score)

    assert score.final_points == 20.0
    assert score.estimated_payment == 50.0
    assert score.balance_adjustment_points == 0.0
    assert changed is True

    # And the pair must stay reverted, not silently regenerate a new debit.
    regenerated = point_balance.detect_post_payment_warranty_debits(db_session, [later])
    db_session.commit()
    assert len(regenerated) == 0


def test_current_balance_reflects_revert_immediately_not_stale_column(db_session, make_collaborator):
    """Regression: CollaboratorPointBalance.balance_points (denormalized column) was
    never updated by revert_entry, so the displayed balance stayed stuck at the old
    value after a revert. current_balance() must compute live from pending entries."""
    from app.models import CollaboratorPointBalance

    collaborator = make_collaborator(name="Teste Drift")
    carry = PointBalanceEntry(collaborator_id=collaborator.id, entry_type="period_settlement", points=-12.0, status="pending")
    db_session.add(carry)
    db_session.add(CollaboratorPointBalance(collaborator_id=collaborator.id, balance_points=-12.0))
    db_session.commit()

    assert point_balance.current_balance(db_session, collaborator.id) == -12.0

    point_balance.revert_entry(db_session, carry.id, reason="correcao")
    db_session.commit()

    assert point_balance.current_balance(db_session, collaborator.id) == 0.0


def test_requires_review_entry_can_be_resolved_with_a_negative_value(db_session, make_collaborator, paid_june_run, admin_user):
    """When recurrence_action=requires_review, the debit is created with points=0 and
    requires_review=True until an admin confirms the real value via resolve_review_entry."""
    collaborator = make_collaborator()
    db_session.add(
        RecurrenceClassificationRule(name="Garantia", classification="garantia", discount_points=True, active=True, priority=1, max_days=30)
    )
    db_session.add(AppSetting(key="recurrence_action", value="requires_review"))
    db_session.add(AppSetting(key="recurrence_window_days", value="30"))
    db_session.flush()

    original = _os(collaborator, "OS-A", datetime(2026, 6, 5, tzinfo=timezone.utc))
    later = _os(collaborator, "OS-B", datetime(2026, 7, 5, tzinfo=timezone.utc))
    db_session.add_all([original, later])
    db_session.commit()

    created = point_balance.detect_post_payment_warranty_debits(db_session, [later])
    db_session.commit()
    entry = created[0]
    assert entry.requires_review is True
    assert entry.points == 0.0

    preview_before = point_balance.preview_pending_adjustment(db_session, collaborator.id, 20.0)
    assert preview_before["adjustment_points"] == 0.0, "an unresolved review entry must not affect payment yet"

    resolved = point_balance.resolve_review_entry(db_session, entry.id, points=-7.0, user=admin_user, note="confirmado apos analise")
    db_session.commit()
    assert resolved.requires_review is False
    assert resolved.points == -7.0
    assert resolved.status == "pending"

    preview_after = point_balance.preview_pending_adjustment(db_session, collaborator.id, 20.0)
    assert preview_after["adjustment_points"] == -7.0

    with pytest.raises(Exception) as excinfo:
        point_balance.resolve_review_entry(db_session, entry.id, points=-5.0, user=admin_user)
    assert getattr(excinfo.value, "status_code", None) == 409

    other = _os(collaborator, "OS-C", datetime(2026, 7, 10, tzinfo=timezone.utc), customer_login="cli2")
    db_session.add(other)
    db_session.commit()
    other_created = point_balance.detect_post_payment_warranty_debits(db_session, [other])
    db_session.commit()
    if other_created:
        with pytest.raises(Exception) as excinfo:
            point_balance.resolve_review_entry(db_session, other_created[0].id, points=5.0, user=admin_user)
        assert getattr(excinfo.value, "status_code", None) == 422, "resolving with a positive (credit) value must be rejected"


def test_debit_survives_deleting_and_reimporting_the_related_service_order(db_session, make_collaborator, paid_june_run, recurrence_setup):
    """Regression: deleting a period's raw O.S rows (to re-import fresh data) used to be
    impossible without first reverting any garantia debit that referenced one of those O.S,
    because the ledger only tracked the internal ServiceOrder.id. Re-importing recreates the
    O.S under a NEW id, so identity must survive via os_code instead - both to unblock the
    delete and to avoid detecting the same warranty pair twice and double-charging it."""
    collaborator = make_collaborator()
    original = _os(collaborator, "OS-JUN-1", datetime(2026, 6, 25, tzinfo=timezone.utc))
    later = _os(collaborator, "OS-JUL-1", datetime(2026, 7, 10, tzinfo=timezone.utc))
    db_session.add_all([original, later])
    db_session.flush()

    created = point_balance.detect_post_payment_warranty_debits(db_session, [later])
    db_session.commit()
    entry = created[0]
    assert entry.related_os_code == "OS-JUL-1"
    assert entry.original_os_code == "OS-JUN-1"

    # Simulate deleting July's raw O.S rows (the /service-orders/delete-period flow): the ledger
    # entry's FK is nulled out, but the os_code stays - this is what unblocks the deletion.
    entry.related_service_order_id = None
    db_session.delete(later)
    db_session.commit()

    assert point_balance.pending_entries_for_collaborator(db_session, collaborator.id)[0].related_os_code == "OS-JUL-1"

    # Re-importing the same file recreates OS-JUL-1 under a brand new ServiceOrder.id.
    reimported_later = _os(collaborator, "OS-JUL-1", datetime(2026, 7, 10, tzinfo=timezone.utc))
    db_session.add(reimported_later)
    db_session.commit()

    duplicate_check = point_balance.detect_post_payment_warranty_debits(db_session, [reimported_later])
    db_session.commit()

    assert duplicate_check == [], "re-importing the same O.S must not create a second debit for the same warranty pair"
    assert len(point_balance.pending_entries_for_collaborator(db_session, collaborator.id)) == 1
