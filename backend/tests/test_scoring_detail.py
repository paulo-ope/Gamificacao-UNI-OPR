"""Regression tests for backend/app/services/scoring_detail.py.

Each test here reproduces a real bug found and fixed during manual audits of this
payroll system. Keeping them as pytest cases (instead of one-off scratch scripts)
means a future change to this module gets caught automatically instead of silently
reintroducing the bug.
"""
from datetime import datetime, timezone

from app.models import (
    AppSetting,
    CpkRegionalSnapshot,
    DiagnosisPenaltyRule,
    HealthRule,
    RecurrenceClassificationRule,
    ScoringGroup,
    ScoringSubjectRule,
    ServiceOrder,
    SlaPenaltyRule,
)
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


def test_audit_screen_uses_collaborators_official_regional_not_the_orders_own_regional(
    db_session, make_collaborator, scoring_setup
):
    """Regression (audit finding B2): the period-audit screen looked up the health multiplier
    using each O.S's OWN regional, while the real payment always uses the collaborator's
    OFFICIAL registered regional for every O.S in the period (see _official_collaborator_regional
    in calculation.py). A registered collaborator who attends an O.S outside their official
    regional got a DIFFERENT (wrong) multiplier on the audit screen than what they're actually
    paid."""
    db_session.add(HealthRule(name="Excelente", min_sla=90, max_recurrence_rate=100, multiplier=2.0, active=True))
    db_session.add(HealthRule(name="Critica", min_sla=0, max_recurrence_rate=100, multiplier=0.4, active=True))
    db_session.flush()

    collaborator = make_collaborator(name="Tecnico Oficial Ji-Parana", regional="UNI - JI PARANA")
    filler_a = make_collaborator(name="Tecnico Filler A", regional="UNI - JI PARANA")
    filler_b = make_collaborator(name="Tecnico Filler B", regional="UNI - MACHADINHO DOESTE")

    filler_order_a = ServiceOrder(
        os_code="OS-FILLER-A", contract_id="CA", customer_login="clia", customer_name="Cliente A",
        collaborator_id=filler_a.id, regional="UNI - JI PARANA", os_type="Manutencao", os_subject="Reparo",
        diagnosis="Falha", status="Concluida", sla_status="Encerrada no Prazo",
        opened_at=datetime(2026, 6, 1, tzinfo=timezone.utc), closed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    filler_order_b = ServiceOrder(
        os_code="OS-FILLER-B", contract_id="CB", customer_login="clib", customer_name="Cliente B",
        collaborator_id=filler_b.id, regional="UNI - MACHADINHO DOESTE", os_type="Manutencao", os_subject="Reparo",
        diagnosis="Falha", status="Concluida", sla_status="Fora do prazo",
        opened_at=datetime(2026, 6, 1, tzinfo=timezone.utc), closed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    order_out_of_official_regional = ServiceOrder(
        os_code="OS-CROSS-REGIONAL", contract_id="CC", customer_login="clic", customer_name="Cliente C",
        collaborator_id=collaborator.id, regional="UNI - MACHADINHO DOESTE", os_type="Manutencao", os_subject="Reparo",
        diagnosis="Falha", status="Concluida", sla_status="Encerrada no Prazo",
        opened_at=datetime(2026, 6, 2, tzinfo=timezone.utc), closed_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
    )
    db_session.add_all([filler_order_a, filler_order_b, order_out_of_official_regional])
    db_session.flush()

    orders = [filler_order_a, filler_order_b, order_out_of_official_regional]
    details = sd.explain_orders(db_session, orders)
    detail = next(d for d in details if d["os_code"] == "OS-CROSS-REGIONAL")
    assert detail["net_points"] > 0  # sanity: scoring_setup da pontos reais pra Manutencao/Reparo

    summary = sd.summarize_audit_details(db_session, [detail], orders, point_value=1.0)

    assert summary["final_points"] == round(detail["net_points"] * 2.0, 2), (
        "deveria usar o multiplicador da regional OFICIAL do colaborador (Excelente, 2.0), nao da regional da O.S (Critica, 0.4)"
    )


def test_manual_review_status_is_not_overwritten_by_a_later_numeric_penalty(db_session, make_collaborator, scoring_setup):
    """Regression (audit finding B1): an order flagged 'Revisão manual' by one rule (ex.: a
    diagnosis configured as requires_review) had its display status silently overwritten to
    'Penalizada' if ANY other rule (ex.: an SLA penalty) also added numeric penalty points
    afterward - the requires_manual_review boolean stayed correct, but the label shown in the
    audit drawer/panel lied about why the order needs attention."""
    collaborator = make_collaborator()
    db_session.add(
        DiagnosisPenaltyRule(diagnosis_name="Falha critica", action_type="requires_review", penalty_points=0, active=True)
    )
    db_session.add(
        SlaPenaltyRule(name="SLA fora do prazo", condition_type="status_sla_out_of_time", penalty_type="subtract_points", penalty_value=3, active=True)
    )
    db_session.flush()

    order = ServiceOrder(
        os_code="OS-REVIEW", contract_id="C1", customer_login="cliente1", customer_name="Cliente Um",
        collaborator_id=collaborator.id, regional=collaborator.regional, os_type="Manutencao", os_subject="Reparo",
        diagnosis="Falha critica", status="Concluida", sla_status="Fora do prazo",
        opened_at=datetime(2026, 6, 1, tzinfo=timezone.utc), closed_at=datetime(2026, 6, 3, tzinfo=timezone.utc),
    )
    db_session.add(order)
    db_session.flush()

    rules = sd.active_scoring_rules(db_session)
    diagnosis_rules = sd.active_diagnosis_rules(db_session)
    sla_rules = sd.active_sla_penalty_rules(db_session)

    detail = sd.explain_order(
        order, rules, diagnosis_rules, sla_rules, {},
        warranty_mode="score_normally", warranty_reduction_percentage=0, default_point_value=1.0,
    )

    assert detail["requires_manual_review"] is True
    assert detail["scoring_status"] == "Revisão manual", "status nao deveria ter sido trocado para 'Penalizada'"


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


def test_warranty_and_recurrence_flags_are_mutually_exclusive_in_audit_payload(
    db_session, make_collaborator, scoring_setup, recurrence_setup
):
    """Regression: classification='garantia' used to set BOTH is_warranty AND is_recurrence in the
    audit payload (explain_order), making the frontend show two labels on one O.S. Product decision:
    at most ONE label per order - garantia keeps counting as discountable (health/points math via
    RECURRENCE_DISCOUNT_CLASSIFICATIONS is untouched), but the display flags are exclusive."""
    collaborator = make_collaborator()
    original = ServiceOrder(
        os_code="OS-EXCL-ORIG", contract_id="C9", customer_login="cliente9", customer_name="Cliente Nove",
        collaborator_id=collaborator.id, regional=collaborator.regional, os_type="Manutencao", os_subject="Reparo",
        diagnosis="Falha", status="Concluida",
        opened_at=datetime(2026, 6, 1, tzinfo=timezone.utc), closed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    warranty_return = ServiceOrder(
        os_code="OS-EXCL-RET", contract_id="C9", customer_login="cliente9", customer_name="Cliente Nove",
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

    assert detail["recurrence_classification"] == "garantia"
    assert detail["is_warranty"] is True
    assert detail["is_recurrence"] is False, "garantia nao pode ligar a flag de reincidencia junto (etiqueta unica)"


def test_recurrence_pairing_survives_a_gap_of_exactly_the_window_plus_hours(
    db_session, make_collaborator, scoring_setup, recurrence_setup
):
    """Regression found via a real audit screenshot: two O.S opened "30 dias e 17 horas" apart
    (days_between=30, within a 30-day window by the same integer day-count used for the rule's
    max_days check and the evidence text) were silently excluded, because the loop's cutoff
    compared the RAW timedelta (which includes the extra hours) against timedelta(days=30) -
    making it stricter than the days_between=30 metric used everywhere else. The cutoff must use
    the same floored days_between, not the raw timedelta."""
    collaborator = make_collaborator()
    original = ServiceOrder(
        os_code="OS-EDGE-ORIG", contract_id="C12", customer_login="cliente12", customer_name="Cliente Doze",
        collaborator_id=collaborator.id, regional=collaborator.regional, os_type="Manutencao", os_subject="Reparo",
        diagnosis="Falha", status="Concluida",
        opened_at=datetime(2026, 6, 19, 21, 18, 55, tzinfo=timezone.utc),
        closed_at=datetime(2026, 6, 30, 20, 15, 49, tzinfo=timezone.utc),
    )
    later_at_the_edge = ServiceOrder(
        os_code="OS-EDGE-RET", contract_id="C12", customer_login="cliente12", customer_name="Cliente Doze",
        collaborator_id=collaborator.id, regional=collaborator.regional, os_type="Manutencao", os_subject="Reparo",
        diagnosis="Falha", status="Concluida",
        opened_at=datetime(2026, 7, 20, 15, 7, 26, tzinfo=timezone.utc),
        closed_at=datetime(2026, 7, 21, 15, 50, 22, tzinfo=timezone.utc),
        is_warranty=True,
    )
    db_session.add_all([original, later_at_the_edge])
    db_session.flush()

    lookup = sd.build_scoring_rule_lookup(sd.active_scoring_rules(db_session))
    penalties = sd.recurrence_penalties(db_session, [original, later_at_the_edge], lookup)

    assert original.id in penalties, "par na borda da janela (30 dias e horas) nao deveria ser cortado pelo loop"
    assert penalties[original.id]["related_os_code"] == "OS-EDGE-RET"
    assert penalties[original.id]["days_between"] == 30


def test_non_technical_subject_is_never_classified_as_recurrence_even_with_a_catch_all_rule(
    db_session, make_collaborator, scoring_setup, recurrence_setup
):
    """Regression (achado real, 2026-07-31): toda RecurrenceClassificationRule ativa no ambiente
    real tinha os campos de tipo/assunto/diagnostico em branco (inclusive a 'Garantia' criada por
    recurrence_setup) - um padrao vazio casa com QUALQUER O.S (_contains_pattern retorna True pra
    padrao vazio), entao essas regras "catch-all" ganhavam mesmo pra tipos que sao fluxo
    operacional/comercial, nao falha tecnica (ex.: uma O.S de 'Remoção de Equipamentos' virava
    'Reincidência de Manutenção' so por coincidir com a mesma identidade dentro do prazo). A
    exclusao de tipos nao-tecnicos (_is_non_technical) precisa vencer QUALQUER regra configurada,
    nao so o fallback sem regra nenhuma."""
    collaborator = make_collaborator()
    original = ServiceOrder(
        os_code="OS-REMOCAO-ORIG", contract_id="C20", customer_login="cliente20", customer_name="Cliente Vinte",
        collaborator_id=collaborator.id, regional=collaborator.regional,
        os_type="Recolhimento", os_subject="Remoção de Equipamentos",
        diagnosis="Desistência da Solicitação", status="Concluida",
        opened_at=datetime(2026, 6, 23, 9, 0, tzinfo=timezone.utc),
        closed_at=datetime(2026, 6, 23, 10, 0, tzinfo=timezone.utc),
    )
    later_removal = ServiceOrder(
        os_code="OS-REMOCAO-RET", contract_id="C20", customer_login="cliente20", customer_name="Cliente Vinte",
        collaborator_id=collaborator.id, regional=collaborator.regional,
        os_type="Recolhimento", os_subject="Remoção de Equipamentos",
        diagnosis="Desistência da Solicitação", status="Concluida",
        opened_at=datetime(2026, 6, 26, 9, 0, tzinfo=timezone.utc),
        closed_at=datetime(2026, 6, 26, 9, 30, tzinfo=timezone.utc),
        is_warranty=True,
    )
    db_session.add_all([original, later_removal])
    db_session.flush()

    lookup = sd.build_scoring_rule_lookup(sd.active_scoring_rules(db_session))
    penalties = sd.recurrence_penalties(db_session, [original, later_removal], lookup)

    assert original.id not in penalties or not penalties[original.id]["discount_applied"], (
        "Remoção de Equipamentos é fluxo operacional (desistência), não falha técnica - "
        "não pode virar reincidência/garantia só por coincidir com a mesma identidade dentro do prazo"
    )
    if original.id in penalties:
        assert penalties[original.id]["classification"] == "os_nao_reincidente"


def test_address_change_is_never_classified_as_recurrence_even_with_a_catch_all_rule(
    db_session, make_collaborator, scoring_setup, recurrence_setup
):
    """Regression: mesmo achado do teste acima, aplicado especificamente a 'Alteração de
    Endereço' (também listado em NON_TECHNICAL_TERMS) - confirmado com o usuário que mudança de
    endereço repetida não deveria gerar desconto de garantia, igual remoção de equipamentos."""
    collaborator = make_collaborator()
    original = ServiceOrder(
        os_code="OS-ENDERECO-ORIG", contract_id="C21", customer_login="cliente21", customer_name="Cliente Vinte e Um",
        collaborator_id=collaborator.id, regional=collaborator.regional,
        os_type="Mud. de Endereço", os_subject="Alteração de Endereço Fibra Urbana",
        diagnosis="Endereço divergente", status="Concluida",
        opened_at=datetime(2026, 6, 10, 9, 0, tzinfo=timezone.utc),
        closed_at=datetime(2026, 6, 10, 10, 0, tzinfo=timezone.utc),
    )
    later_change = ServiceOrder(
        os_code="OS-ENDERECO-RET", contract_id="C21", customer_login="cliente21", customer_name="Cliente Vinte e Um",
        collaborator_id=collaborator.id, regional=collaborator.regional,
        os_type="Mud. de Endereço", os_subject="Alteração de Endereço Fibra Urbana",
        diagnosis="Endereço divergente", status="Concluida",
        opened_at=datetime(2026, 6, 15, 9, 0, tzinfo=timezone.utc),
        closed_at=datetime(2026, 6, 15, 9, 30, tzinfo=timezone.utc),
        is_warranty=True,
    )
    db_session.add_all([original, later_change])
    db_session.flush()

    lookup = sd.build_scoring_rule_lookup(sd.active_scoring_rules(db_session))
    penalties = sd.recurrence_penalties(db_session, [original, later_change], lookup)

    assert original.id not in penalties or not penalties[original.id]["discount_applied"], (
        "alteração de endereço é fluxo comercial, não falha técnica - "
        "não pode virar reincidência/garantia só por coincidir com a mesma identidade dentro do prazo"
    )
    if original.id in penalties:
        assert penalties[original.id]["classification"] == "os_nao_reincidente"


def test_recurrence_pairing_is_not_lost_when_original_takes_long_to_close(
    db_session, make_collaborator, scoring_setup, recurrence_setup
):
    """Regression: the gap used to be computed as later.opened_at - original.closed_at (mixed
    fields). When the original order stayed open for a while and only closed AFTER the return
    order had already been opened, that mix produced a negative delta and the loop silently
    skipped a legitimate, later-opened recurrence. Comparing opened_at-vs-opened_at on both
    sides fixes this without changing the outcome for the normal (same-day close) case."""
    collaborator = make_collaborator()
    original = ServiceOrder(
        os_code="OS-SLOW-ORIG", contract_id="C10", customer_login="cliente10", customer_name="Cliente Dez",
        collaborator_id=collaborator.id, regional=collaborator.regional, os_type="Manutencao", os_subject="Reparo",
        diagnosis="Falha", status="Concluida",
        opened_at=datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc),
        closed_at=datetime(2026, 6, 5, 16, 0, tzinfo=timezone.utc),
    )
    later_return = ServiceOrder(
        os_code="OS-SLOW-RET", contract_id="C10", customer_login="cliente10", customer_name="Cliente Dez",
        collaborator_id=collaborator.id, regional=collaborator.regional, os_type="Manutencao", os_subject="Reparo",
        diagnosis="Falha", status="Concluida",
        opened_at=datetime(2026, 6, 3, 9, 0, tzinfo=timezone.utc),
        closed_at=datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc),
        is_warranty=True,
    )
    db_session.add_all([original, later_return])
    db_session.flush()

    lookup = sd.build_scoring_rule_lookup(sd.active_scoring_rules(db_session))
    penalties = sd.recurrence_penalties(db_session, [original, later_return], lookup)

    assert original.id in penalties, "reincidencia com O.S original demorada pra fechar voltou a ser perdida"
    assert penalties[original.id]["related_os_code"] == "OS-SLOW-RET"


def test_min_hours_between_blocks_near_simultaneous_orders_from_counting_as_recurrence(
    db_session, make_collaborator, scoring_setup
):
    """The configurable minimum-gap field on RecurrenceClassificationRule.min_hours_between:
    two orders opened minutes apart (e.g. the tech split one visit into two O.S) must NOT be
    classified as recurrence when the rule requires a minimum gap that they don't meet, even
    though they match every other pattern/window criterion."""
    collaborator = make_collaborator()
    db_session.add(
        RecurrenceClassificationRule(
            name="Garantia com intervalo minimo", classification="garantia", discount_points=True,
            active=True, priority=1, max_days=30, min_hours_between=4,
        )
    )
    db_session.add(AppSetting(key="recurrence_action", value="annul_original"))
    db_session.add(AppSetting(key="recurrence_window_days", value="30"))
    db_session.flush()

    original = ServiceOrder(
        os_code="OS-NEARSIM-ORIG", contract_id="C11", customer_login="cliente11", customer_name="Cliente Onze",
        collaborator_id=collaborator.id, regional=collaborator.regional, os_type="Manutencao", os_subject="Reparo",
        diagnosis="Falha", status="Concluida",
        opened_at=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
        closed_at=datetime(2026, 6, 1, 9, 30, tzinfo=timezone.utc),
    )
    near_simultaneous = ServiceOrder(
        os_code="OS-NEARSIM-RET", contract_id="C11", customer_login="cliente11", customer_name="Cliente Onze",
        collaborator_id=collaborator.id, regional=collaborator.regional, os_type="Manutencao", os_subject="Reparo",
        diagnosis="Falha", status="Concluida",
        opened_at=datetime(2026, 6, 1, 9, 20, tzinfo=timezone.utc),
        closed_at=datetime(2026, 6, 1, 9, 45, tzinfo=timezone.utc),
        is_warranty=True,
    )
    db_session.add_all([original, near_simultaneous])
    db_session.flush()

    lookup = sd.build_scoring_rule_lookup(sd.active_scoring_rules(db_session))
    penalties = sd.recurrence_penalties(db_session, [original, near_simultaneous], lookup)

    assert original.id not in penalties or penalties[original.id]["classification"] != "garantia", (
        "par quase simultaneo nao deveria contar como reincidencia com intervalo minimo de 4h configurado"
    )


def test_cascade_os_type_for_subject_updates_only_matching_subject(db_session, make_collaborator):
    """Regression: ServiceOrder.os_type is stamped once at import time and never rewritten
    afterward - correcting a subject's Tipo Geral via the rule (ScoringSubjectRule) used to
    only affect FUTURE imports, leaving already-imported orders permanently unmatched
    against the corrected rule until someone ran a manual bulk UPDATE (this happened for
    real, ~15k rows, before this cascade existed). `cascade_os_type_for_subject` must
    rewrite every existing order for that exact os_subject, and touch nothing else."""
    collaborator = make_collaborator()
    stale_order_1 = ServiceOrder(
        os_code="OS-1", contract_id="C1", customer_login="cli1", customer_name="X",
        collaborator_id=collaborator.id, regional=collaborator.regional,
        os_type="Suporte Externo", os_subject="Reativação de Suspensão Temporária - Externo",
        diagnosis="Falha", status="Concluida",
        opened_at=datetime(2026, 6, 1, tzinfo=timezone.utc), closed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    stale_order_2 = ServiceOrder(
        os_code="OS-2", contract_id="C1", customer_login="cli2", customer_name="X",
        collaborator_id=collaborator.id, regional=collaborator.regional,
        os_type="PENDENTE DE CLASSIFICAÇÃO", os_subject="Reativação de Suspensão Temporária - Externo",
        diagnosis="Falha", status="Concluida",
        opened_at=datetime(2026, 6, 2, tzinfo=timezone.utc), closed_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
    )
    unrelated_order = ServiceOrder(
        os_code="OS-3", contract_id="C1", customer_login="cli3", customer_name="X",
        collaborator_id=collaborator.id, regional=collaborator.regional,
        os_type="Suporte Externo", os_subject="Um Assunto Completamente Diferente",
        diagnosis="Falha", status="Concluida",
        opened_at=datetime(2026, 6, 3, tzinfo=timezone.utc), closed_at=datetime(2026, 6, 3, tzinfo=timezone.utc),
    )
    db_session.add_all([stale_order_1, stale_order_2, unrelated_order])
    db_session.flush()

    changed = sd.cascade_os_type_for_subject(
        db_session, "Reativação de Suspensão Temporária - Externo", "Outros"
    )
    db_session.flush()

    assert changed == 2
    assert stale_order_1.os_type == "Outros"
    assert stale_order_2.os_type == "Outros"
    assert unrelated_order.os_type == "Suporte Externo", "assunto diferente nao deveria ser afetado"

    # Idempotente: rodar de novo depois que ja esta tudo corrigido nao acha mais nada pra mudar.
    assert sd.cascade_os_type_for_subject(db_session, "Reativação de Suspensão Temporária - Externo", "Outros") == 0


def test_penalty_distribution_excludes_unregistered_collaborator_orders(db_session, make_collaborator, scoring_setup):
    """Regression: the "Distribuição de pontos anulados" chart (Fechamento > Análise) must only
    count O.S from formally registered collaborators - same rule already applied to
    calculate_regional_health. An O.S penalized by SLA from an unregistered collaborator used to
    still show up in this breakdown even though it never contributes to anything payable."""
    db_session.add(
        SlaPenaltyRule(name="SLA fora do prazo", condition_type="status_sla_out_of_time", penalty_type="cancel_points", penalty_value=0, active=True)
    )
    db_session.flush()

    registered = make_collaborator(name="Registrado", regional="UNI SUL", registered=True)
    unregistered = make_collaborator(name="Nao Registrado", regional="UNI SUL", registered=False)

    order_registered = ServiceOrder(
        os_code="OS-REG-SLA", contract_id="C1", customer_login="cli.reg", customer_name="Cliente Reg",
        collaborator_id=registered.id, regional="UNI SUL", os_type="Manutencao", os_subject="Reparo",
        diagnosis="Falha", status="Concluida", sla_status="Fora do prazo",
        opened_at=datetime(2026, 6, 1, tzinfo=timezone.utc), closed_at=datetime(2026, 6, 3, tzinfo=timezone.utc),
    )
    order_unregistered = ServiceOrder(
        os_code="OS-UNREG-SLA", contract_id="C1", customer_login="cli.unreg", customer_name="Cliente Unreg",
        collaborator_id=unregistered.id, regional="UNI SUL", os_type="Manutencao", os_subject="Reparo",
        diagnosis="Falha", status="Concluida", sla_status="Fora do prazo",
        opened_at=datetime(2026, 6, 1, tzinfo=timezone.utc), closed_at=datetime(2026, 6, 3, tzinfo=timezone.utc),
    )
    db_session.add_all([order_registered, order_unregistered])
    db_session.flush()

    details = sd.explain_orders(db_session, [order_registered, order_unregistered])
    distribution = sd.calculate_penalty_distribution(db_session, [order_registered, order_unregistered], details=details)

    sla_entry = next(item for item in distribution if item["name"] == "SLA fora do prazo")
    assert sla_entry["service_orders_count"] == 1, "only the registered collaborator's O.S should be counted"


def test_counts_for_regional_health_includes_cancelled_but_completed_does_not(db_session, make_collaborator, make_service_order):
    """Alinhamento com a Operacao Analitica (decisao do usuario): O.S. cancelada passa a contar
    no SLA/saude/multiplicador da regional, mas continua fora da pontuacao normal - completed()
    (usado pra pontuacao/reincidencia/debito de garantia) nao pode mudar, so
    counts_for_regional_health() (usado exclusivamente pra calculate_regional_health)."""
    collaborator = make_collaborator(regional="UNI SUL")
    cancelled = make_service_order(collaborator, os_code="OS-CANC", status="Cancelada", sla_status="Dentro do prazo")

    assert sd.completed(cancelled) is False, "cancelada nao deve contar como concluida pra pontuacao/reincidencia"
    assert sd.counts_for_regional_health(cancelled) is True, "cancelada deve contar no calculo de saude/SLA"


def test_calculate_regional_health_counts_cancelled_orders_in_denominator(db_session, make_collaborator, make_service_order, scoring_setup):
    """Uma O.S. cancelada fora do prazo deve puxar o sla_rate da regional pra baixo quando a lista
    passada usa counts_for_regional_health - o mesmo calculo usando completed() (comportamento
    antigo) nao deveria enxergar essa O.S. de jeito nenhum."""
    collaborator = make_collaborator(regional="UNI SUL")
    on_time = make_service_order(collaborator, os_code="OS-OK", status="Concluida", sla_status="Dentro do prazo")
    cancelled_late = make_service_order(collaborator, os_code="OS-CANC", status="Cancelada", sla_status="Fora do prazo")

    all_orders = [on_time, cancelled_late]
    old_scope = [order for order in all_orders if sd.completed(order)]
    new_scope = [order for order in all_orders if sd.counts_for_regional_health(order)]

    old_health = sd.calculate_regional_health(db_session, old_scope)
    new_health = sd.calculate_regional_health(db_session, new_scope)

    assert old_health["UNI SUL"]["total_orders"] == 1, "regra antiga nunca via a O.S. cancelada"
    assert old_health["UNI SUL"]["sla_rate"] == 100.0

    assert new_health["UNI SUL"]["total_orders"] == 2, "regra nova (alinhada a Analitica) inclui a cancelada"
    assert new_health["UNI SUL"]["sla_rate"] == 50.0, "a cancelada fora do prazo derruba o sla_rate"


def test_get_collaborator_service_orders_detail_applies_cpk_adjustment(db_session, make_collaborator, make_service_order, scoring_setup):
    """Regression: get_collaborator_service_orders_detail (extrato do colaborador) tinha o mesmo
    bug encontrado no dashboard - calculava a saude/multiplicador da regional sem aplicar o
    ajuste de CPK, entao o valor mostrado no extrato podia divergir do que de fato seria usado
    no fechamento de folha."""
    collaborator = make_collaborator(regional="UNI SUL")
    make_service_order(collaborator, sla_status="Dentro do prazo")

    db_session.add(CpkRegionalSnapshot(reference_year=2026, reference_month=6, regional="UNI SUL", status="na_meta"))
    db_session.add(AppSetting(key="cpk_bonus_points", value="0.3"))
    db_session.flush()

    result = sd.get_collaborator_service_orders_detail(db_session, collaborator.id, 6, 2026)

    net_points = float(result["summary"]["net_points"])
    assert float(result["summary"]["final_points"]) == round(net_points * 1.3, 2), (
        "HealthRule 'Boa' (scoring_setup) da multiplier=1.0; com CPK na_meta (+0.3) o efetivo deveria ser 1.3"
    )


def test_financial_breakdowns_exclude_unregistered_collaborators(db_session, make_collaborator, make_service_order, scoring_setup):
    """Regression: unregistered collaborators can have visible points for audit, but they must
    not inflate financial cost breakdowns because they are not payable."""
    registered = make_collaborator(name="Registrado", regional="UNI SUL", registered=True)
    unregistered = make_collaborator(name="Nao Cadastrado", regional="UNI SUL", registered=False)
    make_service_order(registered, os_code="OS-REG")
    make_service_order(unregistered, os_code="OS-UNREG")
    orders = sd.period_orders(db_session, 6, 2026, "UNI SUL")
    details = sd.explain_orders(db_session, orders, default_point_value=2.0)

    breakdowns = sd.financial_breakdowns(db_session, orders, 2.0, details=details)

    assert breakdowns["cost_by_regional"][0]["orders"] == 1
    assert breakdowns["cost_by_regional"][0]["estimated_payment"] == 30.0
    assert breakdowns["cost_by_collaborator"][0]["collaborator_id"] == registered.id
    assert all(item["collaborator_id"] != unregistered.id for item in breakdowns["cost_by_collaborator"])


def test_financial_breakdowns_applies_collaborator_discount_ratio_to_each_order(db_session, make_collaborator, make_service_order, scoring_setup):
    """Regression: o desconto de garantia (point_balance.py) e lancado uma vez no total do
    colaborador, sem estar amarrado a nenhuma O.S especifica - "por regional/grupo/assunto"
    somava o valor BRUTO de cada O.S e nunca batia com "Total a pagar" (que ja vem liquido do
    desconto) sempre que havia garantia no periodo, sem nenhum aviso pra quem comparava as duas
    telas. financial_breakdowns agora aplica a mesma proporcao liquido/bruto do colaborador
    (vinda de collaborator_context) em cada O.S dele, entao a soma por regional volta a bater
    com o valor realmente pago."""
    collaborator = make_collaborator(name="Tecnico Com Garantia", regional="UNI SUL")
    make_service_order(collaborator, os_code="OS-1")
    make_service_order(collaborator, os_code="OS-2")
    orders = sd.period_orders(db_session, 6, 2026, "UNI SUL")
    details = sd.explain_orders(db_session, orders, default_point_value=2.0)

    gross_total = round(sum(float(item["net_points"]) * 1.0 * 2.0 for item in details), 2)
    net_total = round(gross_total * 0.6, 2)  # simula 40% descontado de garantia
    context = {
        collaborator.id: {
            "regional": "UNI SUL",
            "health_multiplier": 1.0,
            "gross_estimated_payment": gross_total,
            "estimated_payment": net_total,
        }
    }

    breakdowns = sd.financial_breakdowns(db_session, orders, 2.0, details=details, collaborator_context=context)

    total_by_regional = round(sum(float(item["estimated_payment"]) for item in breakdowns["cost_by_regional"]), 2)
    assert total_by_regional == net_total, (
        "a soma por regional deveria bater com o valor liquido (ja com o desconto de garantia), nao com o bruto"
    )


def test_financial_breakdowns_sum_matches_exact_paid_amount_with_many_fractional_orders(db_session, make_collaborator, make_service_order, scoring_setup):
    """Regression: arredondar o valor de cada O.S individualmente (em vez de arredondar so a soma
    final por bucket) acumulava um residuo de poucos centavos ao longo de muitas O.S - um
    fechamento real (07/2026) fechava com R$0,21 de diferenca entre "Total a pagar" e a soma de
    "por regional", porque summarize_details (o calculo oficial) arredonda UMA VEZ por
    colaborador, enquanto financial_breakdowns arredondava a CADA O.S. Numeros redondos (ex.:
    desconto de 40% exato) escondem esse bug por coincidencia - este teste usa 7 O.S e um desconto
    "feio" (87,34%) de proposito, o cenario que expunha a diferenca."""
    collaborator = make_collaborator(name="Tecnico Fracionado", regional="UNI SUL")
    for index in range(7):
        make_service_order(collaborator, os_code=f"OS-FRAC-{index}")
    orders = sd.period_orders(db_session, 6, 2026, "UNI SUL")
    details = sd.explain_orders(db_session, orders, default_point_value=2.0)

    gross_total = round(sum(float(item["net_points"]) * 1.0 * 2.0 for item in details), 2)
    net_total = round(gross_total * 0.8734, 2)
    context = {
        collaborator.id: {
            "regional": "UNI SUL",
            "health_multiplier": 1.0,
            "gross_estimated_payment": gross_total,
            "estimated_payment": net_total,
        }
    }

    breakdowns = sd.financial_breakdowns(db_session, orders, 2.0, details=details, collaborator_context=context)

    total_by_regional = round(sum(float(item["estimated_payment"]) for item in breakdowns["cost_by_regional"]), 2)
    assert total_by_regional == net_total, "a soma por regional precisa bater EXATO, nao so aproximado"


def test_sla_comparison_is_exact_without_hour_rounding(db_session, make_collaborator, make_service_order, scoring_setup):
    """Alinhamento com a Operacao Analitica (decisao do usuario): a comparacao de horas do SLA e
    EXATA - 24,4h contra meta de 24h e fora do prazo, o mesmo numero que o painel analitico
    mostra. Antes, round(24,4)=24 fazia a gamificacao considerar 'no prazo' uma O.S que a
    Analitica mostrava como atrasada."""
    collaborator = make_collaborator(regional="UNI SUL")
    barely_late = make_service_order(
        collaborator, os_code="OS-244", sla_status="", sla_hours=24.0, closing_time_hours=24.4
    )
    exactly_on_time = make_service_order(
        collaborator, os_code="OS-240", sla_status="", sla_hours=24.0, closing_time_hours=24.0
    )

    assert sd.sla_measurement(barely_late) is False, "24,4h > meta de 24h = fora do prazo (sem arredondar)"
    assert sd.sla_measurement(exactly_on_time) is True


def test_sla_unmeasurable_orders_are_excluded_from_regional_sla_rate(db_session, make_collaborator, make_service_order, scoring_setup):
    """Alinhamento com a Operacao Analitica (decisao do usuario): O.S sem meta de horas
    configurada (assunto sem meta no IXC, sla_status 'unidentified') fica FORA do calculo de SLA
    da regional - nem numerador nem denominador. Antes ela contava como 'fora do prazo' e
    derrubava o SLA/multiplicador/pagamento da regional por uma O.S que nunca teve prazo."""
    collaborator = make_collaborator(regional="UNI SUL")
    on_time_1 = make_service_order(collaborator, os_code="OS-OK1", sla_status="on_time")
    on_time_2 = make_service_order(collaborator, os_code="OS-OK2", sla_status="on_time")
    unmeasurable = make_service_order(collaborator, os_code="OS-SEM-META", sla_status="unidentified")
    # Atribuido DEPOIS da criacao: as colunas tem default (sla_hours=24, closing_time_hours=0)
    # que e aplicado no INSERT quando o valor chega como None - passar None no construtor nao
    # produz NULL de verdade.
    unmeasurable.sla_hours = None
    unmeasurable.closing_time_hours = None
    db_session.flush()

    assert sd.sla_measurement(unmeasurable) is None
    assert sd.sla_inside(unmeasurable) is True, "nao mensuravel nunca deve ser tratada como atrasada"

    health = sd.calculate_regional_health(db_session, [on_time_1, on_time_2, unmeasurable])

    assert health["UNI SUL"]["sla_rate"] == 100.0, "2 de 2 mensuraveis no prazo; a sem meta fica fora da conta"
    assert health["UNI SUL"]["total_orders"] == 3, "total de O.S (denominador da reincidencia) continua contando todas"
