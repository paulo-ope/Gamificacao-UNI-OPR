"""Regression tests for backend/app/services/point_balance.py - the ledger that tracks
warranty debits detected after their original month has already been paid."""
from datetime import datetime, timedelta, timezone

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


def test_only_one_debit_per_original_even_with_many_near_simultaneous_later_returns(
    db_session, make_collaborator, paid_june_run, recurrence_setup
):
    """Regression found in production: one original ticket (IXC-1081509) had 12 SEPARATE debit
    entries created against it, one per near-duplicate "return" ticket opened seconds apart on
    the same day. Because all those gaps round down to days_between=0, they tie on the "nearest
    candidate" sort, and each later ticket independently re-discovers the SAME original as its
    best match. A single original must only ever be debited once by this mechanism, no matter
    how many later tickets tie back to it."""
    collaborator = make_collaborator()
    original = _os(collaborator, "OS-JUN-ORIG", datetime(2026, 6, 25, 10, 0, tzinfo=timezone.utc))
    laters = [
        _os(collaborator, f"OS-JUN-DUP-{i}", datetime(2026, 6, 25, 10, i, tzinfo=timezone.utc))
        for i in range(1, 6)
    ]
    db_session.add(original)
    db_session.add_all(laters)
    db_session.flush()

    created_total = []
    for later in laters:
        created_total.extend(point_balance.detect_post_payment_warranty_debits(db_session, [later]))
        db_session.commit()

    assert len(created_total) == 1, "so o primeiro retorno deveria gerar debito - os demais batem na mesma original ja debitada"
    assert created_total[0].original_os_code == "OS-JUN-ORIG"


def _months_before(reference: datetime, months: int) -> tuple[int, int]:
    month = reference.month - months
    year = reference.year
    while month <= 0:
        month += 12
        year -= 1
    return month, year


def test_post_payment_debit_skips_originals_two_or_more_months_old(db_session, make_collaborator, recurrence_setup):
    """Regression: only the calendar month immediately before the current one is eligible for this
    mechanism. A rolling day-count window (the previous approach) could reach 2 calendar months
    back depending on which day of the month the detection ran on - a real incident where a
    collaborator was debited for an O.S closed in May while July was being calculated, which
    surprised the product owner. Anything 2+ months old must never generate a NEW debit."""
    collaborator = make_collaborator()
    now = datetime.now(timezone.utc)
    old_month, old_year = _months_before(now, 2)
    old_closed = datetime(old_year, old_month, 15, tzinfo=timezone.utc)
    run = CalculationRun(reference_month=old_month, reference_year=old_year, regional=None, point_value=2.5, status="paid")
    db_session.add(run)
    original = _os(collaborator, "OS-2MONTHS-ORIG", old_closed)
    later = _os(collaborator, "OS-2MONTHS-RET", old_closed + timedelta(days=5))
    db_session.add_all([original, later])
    db_session.flush()

    created = point_balance.detect_post_payment_warranty_debits(db_session, [later])
    db_session.commit()

    assert created == [], "original de 2+ meses atras nao deveria gerar debito - so o mes imediatamente anterior e elegivel"


def test_post_payment_debit_allowed_for_immediately_previous_month(db_session, make_collaborator, recurrence_setup):
    """Sanity check for the fix above: an original closed in the month right before the current
    one must keep generating the debit normally - the calendar-month rule must not weaken the
    real, intended case."""
    collaborator = make_collaborator()
    now = datetime.now(timezone.utc)
    last_month, last_year = _months_before(now, 1)
    recent_closed = datetime(last_year, last_month, 15, tzinfo=timezone.utc)
    run = CalculationRun(reference_month=last_month, reference_year=last_year, regional=None, point_value=2.5, status="paid")
    db_session.add(run)
    original = _os(collaborator, "OS-LASTMONTH-ORIG", recent_closed)
    later = _os(collaborator, "OS-LASTMONTH-RET", recent_closed + timedelta(days=5))
    db_session.add_all([original, later])
    db_session.flush()

    created = point_balance.detect_post_payment_warranty_debits(db_session, [later])
    db_session.commit()

    assert len(created) == 1, "original do mes imediatamente anterior deveria gerar debito normalmente"


def test_post_payment_debit_skips_unregistered_or_inactive_original_collaborator(
    db_session, make_collaborator, paid_june_run, recurrence_setup
):
    """A collaborator who is not registered (or not active) never enters a future payroll run,
    so a pending debit against them can NEVER be applied - it just accumulates forever with no
    effect, and becomes an unfair surprise backlog if they're registered later. This mechanism
    must skip creating a debit for those collaborators entirely."""
    unregistered = make_collaborator(name="Fantasma Nao Cadastrado", registered=False)
    inactive = make_collaborator(name="Ex Colaborador Inativo")
    inactive.active = False
    db_session.flush()

    original_unregistered = _os(unregistered, "OS-JUN-UNREG", datetime(2026, 6, 25, tzinfo=timezone.utc))
    later_unregistered = _os(unregistered, "OS-JUL-UNREG", datetime(2026, 7, 10, tzinfo=timezone.utc))
    original_inactive = _os(inactive, "OS-JUN-INACTIVE", datetime(2026, 6, 25, tzinfo=timezone.utc), customer_login="cliente.inactive")
    later_inactive = _os(inactive, "OS-JUL-INACTIVE", datetime(2026, 7, 10, tzinfo=timezone.utc), customer_login="cliente.inactive")
    db_session.add_all([original_unregistered, later_unregistered, original_inactive, later_inactive])
    db_session.flush()

    created = point_balance.detect_post_payment_warranty_debits(
        db_session, [later_unregistered, later_inactive]
    )
    db_session.commit()

    assert created == [], "colaborador nao cadastrado/inativo nao deveria acumular debito de garantia"


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


def test_snapshot_points_do_not_fallback_to_subject_only_for_wrong_os_type(make_collaborator):
    """Regression: post-payment warranty debits must use the same exact (os_type, os_subject)
    matching rule as the main scorer. Falling back to a unique subject from a different type
    creates a debit for an O.S that originally should have been unscored."""
    collaborator = make_collaborator()
    order = _os(
        collaborator,
        "OS-WRONG-TYPE",
        datetime(2026, 6, 25, tzinfo=timezone.utc),
        os_type="Manutencao",
        os_subject="Reparo Fibra",
    )
    snapshot = {
        "config": {
            "scoring_groups": [{"id": 1, "default_points": 12.0, "active": True}],
            "scoring_subject_rules": [
                {
                    "id": 1,
                    "group_id": 1,
                    "os_type": "Instalacao",
                    "os_subject": "Reparo Fibra",
                    "use_group_default": True,
                    "custom_points": None,
                    "active": True,
                }
            ],
        }
    }

    assert point_balance._order_points_from_snapshot(order, snapshot) == 0.0
