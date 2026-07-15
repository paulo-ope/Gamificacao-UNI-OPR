"""Regression tests for backend/app/services/scoring_detail.py.

Each test here reproduces a real bug found and fixed during manual audits of this
payroll system. Keeping them as pytest cases (instead of one-off scratch scripts)
means a future change to this module gets caught automatically instead of silently
reintroducing the bug.
"""
from datetime import datetime, timezone

from app.models import ScoringGroup, ScoringSubjectRule, ServiceOrder, SlaPenaltyRule
from app.services import scoring_detail as sd


def test_recurrence_pairing_survives_out_of_window_candidate_sorted_first(db_session, make_collaborator, scoring_setup, recurrence_setup):
    """Regression: candidates must be scanned in opened_at order (not closed_at).

    A long-running later order that opened EARLY (inside the window) but closed LATE
    used to be scanned after an unrelated order that opened late but closed early and
    fell outside the window - the loop would `break` on the out-of-window candidate
    before ever reaching the valid one, silently losing a real recurrence discount.
    """
    collaborator = make_collaborator()
    original = ServiceOrder(
        os_code="ORIG", contract_id="C-1", customer_login="cli.x", customer_name="X",
        collaborator_id=collaborator.id, regional=collaborator.regional, os_type="Manutencao", os_subject="Reparo",
        diagnosis="Falha", status="Concluida",
        opened_at=datetime(2026, 3, 1, tzinfo=timezone.utc), closed_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )
    valid_but_long_running = ServiceOrder(
        os_code="L1-VALIDA", contract_id="C-1", customer_login="cli.x", customer_name="X",
        collaborator_id=collaborator.id, regional=collaborator.regional, os_type="Manutencao", os_subject="Reparo",
        diagnosis="Falha", status="Concluida",
        opened_at=datetime(2026, 3, 5, tzinfo=timezone.utc), closed_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )
    out_of_window_but_closes_early = ServiceOrder(
        os_code="L2-FORA", contract_id="C-1", customer_login="cli.x", customer_name="X",
        collaborator_id=collaborator.id, regional=collaborator.regional, os_type="Manutencao", os_subject="Reparo",
        diagnosis="Falha", status="Concluida",
        opened_at=datetime(2026, 4, 25, tzinfo=timezone.utc), closed_at=datetime(2026, 4, 26, tzinfo=timezone.utc),
    )
    db_session.add_all([original, valid_but_long_running, out_of_window_but_closes_early])
    db_session.flush()

    lookup = sd.build_scoring_rule_lookup(sd.active_scoring_rules(db_session))
    penalties = sd.recurrence_penalties(db_session, [original], lookup)

    assert original.id in penalties, "reincidencia valida nao foi detectada (bug de ordenacao voltou)"
    penalty = penalties[original.id]
    assert penalty["points"] > 0
    assert penalty["related_os_code"] == "L1-VALIDA"


def test_subject_rule_does_not_leak_across_os_type(db_session, make_collaborator):
    """Regression: a rule scoped to os_type=Instalacao must not score os_type=Manutencao
    just because the os_subject string matches - that inflated payouts for unrelated
    service types sharing a subject name."""
    collaborator = make_collaborator()
    group = ScoringGroup(name="Instalacao", default_points=5.0, active=True)
    db_session.add(group)
    db_session.flush()
    db_session.add(
        ScoringSubjectRule(group_id=group.id, os_type="Instalacao", os_subject="Reparo Fibra", use_group_default=True, active=True)
    )
    db_session.flush()
    lookup = sd.build_scoring_rule_lookup(sd.active_scoring_rules(db_session))

    wrong_type = ServiceOrder(
        os_code="OS-WRONG", contract_id="C", customer_login="c", customer_name="X",
        collaborator_id=collaborator.id, regional=collaborator.regional, os_type="Manutencao", os_subject="Reparo Fibra",
        diagnosis="Falha", status="Concluida",
    )
    right_type = ServiceOrder(
        os_code="OS-RIGHT", contract_id="C", customer_login="c", customer_name="X",
        collaborator_id=collaborator.id, regional=collaborator.regional, os_type="Instalacao", os_subject="Reparo Fibra",
        diagnosis="Falha", status="Concluida",
    )

    assert sd.matching_scoring_rule(wrong_type, lookup) is None
    matched = sd.matching_scoring_rule(right_type, lookup)
    assert matched is not None
    assert sd.effective_rule_points(matched) == 5.0


def test_estimated_payment_matches_final_points_times_point_value_when_rate_is_uniform():
    """Regression: estimated_payment used to be computed as an independent weighted sum
    that could round differently than final_points * point_value by a cent, even when
    every order in the period used the exact same point value."""
    details = [
        {
            "base_points": 3.0, "penalty_points": 0.0, "net_points": 2.59, "point_value": 2.50,
            "is_scored": True, "is_unscored": False, "is_penalized": False, "recurrence_classification": None,
            "has_reschedule": False, "has_pending": False, "is_sla_out_of_time": False, "is_annulled": False,
            "diagnosis_penalty_points": 0, "requires_manual_review": False, "diagnosis": "x", "diagnosis_rule_id": None,
        }
        for _ in range(3)
    ]

    summary = sd.summarize_details(details, health_multiplier=0.85, point_value=2.50)
    manual_check = round(summary["final_points"] * 2.50, 2)

    assert summary["estimated_payment"] == manual_check


def test_estimated_payment_uses_weighted_sum_when_point_values_are_mixed():
    """When orders carry different point value overrides, the simple final*rate formula
    doesn't apply - the weighted sum per order must be preserved."""
    mixed = [
        {
            "base_points": 10.0, "penalty_points": 0.0, "net_points": 10.0, "point_value": 2.00,
            "is_scored": True, "is_unscored": False, "is_penalized": False, "recurrence_classification": None,
            "has_reschedule": False, "has_pending": False, "is_sla_out_of_time": False, "is_annulled": False,
            "diagnosis_penalty_points": 0, "requires_manual_review": False, "diagnosis": "x", "diagnosis_rule_id": None,
        },
        {
            "base_points": 10.0, "penalty_points": 0.0, "net_points": 10.0, "point_value": 5.00,
            "is_scored": True, "is_unscored": False, "is_penalized": False, "recurrence_classification": None,
            "has_reschedule": False, "has_pending": False, "is_sla_out_of_time": False, "is_annulled": False,
            "diagnosis_penalty_points": 0, "requires_manual_review": False, "diagnosis": "x", "diagnosis_rule_id": None,
        },
    ]

    summary = sd.summarize_details(mixed, health_multiplier=1.0, point_value=2.00)

    assert summary["estimated_payment"] == 70.0  # 10*2.00 + 10*5.00


def test_non_discount_recurrence_match_does_not_erase_sla_annulment(db_session, make_collaborator, scoring_setup):
    """Regression: an order fully annulled by SLA that also happens to match ANY other
    order from the same customer within the recurrence window (even a completely
    unrelated demand, classified 'demandas_diferentes') used to have its scoring_status
    silently reset to 'Pontuada'/'Penalizada', dropping it out of the annulled-orders
    count even though it scored zero points. See scoring_detail.py around
    `pre_recurrence_status`.
    """
    collaborator = make_collaborator()
    db_session.add(
        SlaPenaltyRule(name="SLA fora do prazo", condition_type="status_sla_out_of_time", penalty_type="cancel_points", penalty_value=0, active=True)
    )
    db_session.flush()

    annulled_by_sla = ServiceOrder(
        os_code="OS-A", contract_id="C1", customer_login="cliente1", customer_name="Cliente Um",
        collaborator_id=collaborator.id, regional=collaborator.regional, os_type="Manutencao", os_subject="Reparo A",
        diagnosis="Falha eletrica", status="Concluida", sla_status="Fora do prazo",
        opened_at=datetime(2026, 6, 1, tzinfo=timezone.utc), closed_at=datetime(2026, 6, 3, tzinfo=timezone.utc),
    )
    unrelated_later_order = ServiceOrder(
        os_code="OS-B", contract_id="C1", customer_login="cliente1", customer_name="Cliente Um",
        collaborator_id=collaborator.id, regional=collaborator.regional, os_type="Manutencao", os_subject="Reparo B",
        diagnosis="Duvida de fatura", status="Concluida", sla_status="Encerrada no Prazo",
        opened_at=datetime(2026, 6, 10, tzinfo=timezone.utc), closed_at=datetime(2026, 6, 11, tzinfo=timezone.utc),
    )
    db_session.add(ScoringSubjectRule(group_id=scoring_setup.id, os_type="Manutencao", os_subject="Reparo A", use_group_default=True, active=True))
    db_session.add(ScoringSubjectRule(group_id=scoring_setup.id, os_type="Manutencao", os_subject="Reparo B", use_group_default=True, active=True))
    db_session.add_all([annulled_by_sla, unrelated_later_order])
    db_session.flush()

    rules = sd.active_scoring_rules(db_session)
    diagnosis_rules = sd.active_diagnosis_rules(db_session)
    sla_rules = sd.active_sla_penalty_rules(db_session)
    recurrence = sd.recurrence_penalties(db_session, [annulled_by_sla, unrelated_later_order], rules)
    assert recurrence.get(annulled_by_sla.id, {}).get("classification") == "demandas_diferentes"

    detail = sd.explain_order(
        annulled_by_sla, rules, diagnosis_rules, sla_rules, recurrence,
        warranty_mode="score_normally", warranty_reduction_percentage=0, default_point_value=1.0,
    )

    assert detail["net_points"] == 0
    assert detail["scoring_status"] == "Anulada por SLA"
    assert detail["is_annulled"] is True
    assert detail["is_scored"] is False


def test_real_recurrence_discount_still_annuls_the_original_order(db_session, make_collaborator, scoring_setup, recurrence_setup):
    """Sanity check for the fix above: a genuine warranty return (classification=garantia,
    discount_points=True) must still annul the original order's points and be labeled
    'Anulada por reincidência' - the fix must not weaken the real case."""
    collaborator = make_collaborator()
    original = ServiceOrder(
        os_code="OS-ORIG", contract_id="C1", customer_login="cliente2", customer_name="Cliente Dois",
        collaborator_id=collaborator.id, regional=collaborator.regional, os_type="Manutencao", os_subject="Reparo",
        diagnosis="Falha", status="Concluida",
        opened_at=datetime(2026, 6, 1, tzinfo=timezone.utc), closed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    warranty_return = ServiceOrder(
        os_code="OS-RETORNO", contract_id="C1", customer_login="cliente2", customer_name="Cliente Dois",
        collaborator_id=collaborator.id, regional=collaborator.regional, os_type="Manutencao", os_subject="Reparo",
        diagnosis="Falha", status="Concluida",
        opened_at=datetime(2026, 6, 5, tzinfo=timezone.utc), closed_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
        is_warranty=True,
    )
    db_session.add_all([original, warranty_return])
    db_session.flush()

    rules = sd.active_scoring_rules(db_session)
    diagnosis_rules = sd.active_diagnosis_rules(db_session)
    sla_rules = sd.active_sla_penalty_rules(db_session)
    recurrence = sd.recurrence_penalties(db_session, [original, warranty_return], rules)

    detail = sd.explain_order(
        original, rules, diagnosis_rules, sla_rules, recurrence,
        warranty_mode="score_normally", warranty_reduction_percentage=0, default_point_value=1.0,
    )

    assert detail["scoring_status"] == "Anulada por reincidência"
    assert detail["net_points"] == 0
    assert detail["is_annulled"] is True
