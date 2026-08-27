"""Regressao da auditoria financeira 2026-08-26 (achado C2): recalcular o bonus de lideranca
sobre um fechamento que ja tem `cost_by_regional` gravado SOMA o bonus de novo, por cima do
valor que ja incluia o bonus da rodada anterior.

`apply_leadership_bonus_to_cost_by_regional` recebe a lista ja gravada e devolve ela com o bonus
somado; `calculate_and_store_leadership_bonus` grava o resultado de volta em `run.result_summary`.
Como o recalculo pode acontecer varias vezes sobre o MESMO run (no calculo, ao marcar como pago
quando ha ajuste de saldo, e via `POST /leadership/bonus-results/calculate`), o bonus entra
multiplas vezes.

Evidencia real: no fechamento #1601 (07/2026, pago) a soma de `cost_by_regional` da
R$ 38.264,02 contra R$ 24.282,77 reais (R$ 18.271,68 de tecnicos + R$ 6.011,09 de lideranca), e a
lista tem DUAS linhas "Lideranca sem regional" - assinatura de aplicacoes repetidas.
"""
from datetime import datetime, timezone

import pytest

from app.models import (
    CalculationRun,
    CollaboratorScore,
    LeadershipProfile,
    LeadershipProfileRegional,
)
from app.services.leadership_bonus import (
    apply_leadership_bonus_to_cost_by_regional,
    calculate_and_store_leadership_bonus,
)

REGIONAL = "UNI - JI PARANA"
UNASSIGNED_LABEL = "Liderança sem regional"


@pytest.fixture()
def run_with_leadership(db_session, make_collaborator):
    """Fechamento com um tecnico, um supervisor com regional e um gerente de pasta (sem regional,
    portanto vai para a linha 'Lideranca sem regional')."""
    technician = make_collaborator(name="Tecnico Um", regional=REGIONAL)
    run = CalculationRun(
        reference_month=7,
        reference_year=2026,
        regional=None,
        point_value=0.35,
        status="draft",
        created_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
    )
    db_session.add(run)
    db_session.flush()
    db_session.add(
        CollaboratorScore(
            calculation_run_id=run.id,
            collaborator_id=technician.id,
            service_orders_count=10,
            gross_points=200.0,
            penalty_points=0.0,
            net_points=200.0,
            health_multiplier=1.0,
            health_status="Boa",
            final_points=200.0,
            estimated_payment=70.0,
        )
    )

    supervisor = LeadershipProfile(name="Supervisor Ji-Parana", role_type="supervisor", multiplier=1.5, active=True)
    supervisor.regionals.append(LeadershipProfileRegional(regional_name=REGIONAL))
    matrix = LeadershipProfile(name="Gerente de Pasta", role_type="portfolio_manager", multiplier=3.0, active=True)
    db_session.add_all([supervisor, matrix])

    run.result_summary = {
        "dashboard_cache_version": 3,
        "final_points": 200.0,
        "estimated_payment": 70.0,
        "cards": {"final_points": 200.0, "estimated_payment": 70.0},
        "score_summaries": {},
        # Custo por regional SEM lideranca, exatamente como `financial_breakdowns` produz.
        "cost_by_regional": [{"regional": REGIONAL, "orders": 10, "estimated_payment": 70.0}],
    }
    db_session.flush()
    return run


def _total(cost_by_regional: list[dict]) -> float:
    return round(sum(float(item["estimated_payment"]) for item in cost_by_regional), 2)


def test_applying_the_bonus_twice_does_not_double_count(db_session, run_with_leadership):
    """Recalcular o bonus duas vezes tem que dar o mesmo `cost_by_regional` que recalcular uma
    vez. Hoje o segundo recalculo soma o bonus de novo sobre um valor que ja o continha."""
    run = run_with_leadership

    first = calculate_and_store_leadership_bonus(db_session, run)
    after_first = _total(run.result_summary["cost_by_regional"])

    second = calculate_and_store_leadership_bonus(db_session, run)
    after_second = _total(run.result_summary["cost_by_regional"])

    assert second["total_bonus_amount"] == first["total_bonus_amount"]
    assert after_second == after_first


def test_regional_breakdown_matches_technicians_plus_leadership(db_session, run_with_leadership):
    """Invariante permanente: a soma de 'Valor a ser pago por regional' tem que ser exatamente
    o valor dos tecnicos mais o bonus de lideranca. E a tabela usada pra distribuir o pagamento
    por filial - se ela infla, alguem paga a mais."""
    run = run_with_leadership

    summary = calculate_and_store_leadership_bonus(db_session, run)
    calculate_and_store_leadership_bonus(db_session, run)

    technicians = round(sum(float(score.estimated_payment) for score in run.scores), 2)
    expected = round(technicians + float(summary["total_bonus_amount"]), 2)

    assert _total(run.result_summary["cost_by_regional"]) == expected


def test_unassigned_leadership_line_is_never_duplicated(db_session, run_with_leadership):
    """Gerente de pasta nao tem regional propria e vira uma linha 'Liderança sem regional'. Cada
    reaplicacao adicionava uma linha nova em vez de atualizar a existente."""
    run = run_with_leadership

    calculate_and_store_leadership_bonus(db_session, run)
    calculate_and_store_leadership_bonus(db_session, run)
    calculate_and_store_leadership_bonus(db_session, run)

    unassigned = [item for item in run.result_summary["cost_by_regional"] if item["regional"] == UNASSIGNED_LABEL]
    assert len(unassigned) == 1


def test_helper_is_idempotent_on_an_already_merged_list():
    """A funcao pura tambem precisa ser segura: reaplicar sobre uma lista que ja recebeu o bonus
    nao pode somar de novo. Sem isso, qualquer chamador novo reintroduz o defeito."""
    base = [{"regional": REGIONAL, "orders": 10, "estimated_payment": 70.0}]
    leadership_summary = {
        "results": [
            {"role_type": "supervisor", "regionals": [REGIONAL], "bonus_amount": 30.0},
            {"role_type": "portfolio_manager", "regionals": [], "bonus_amount": 20.0},
        ]
    }

    once = apply_leadership_bonus_to_cost_by_regional(base, leadership_summary)
    twice = apply_leadership_bonus_to_cost_by_regional(once, leadership_summary)

    assert _total(once) == 120.0
    assert _total(twice) == _total(once)
    assert len([item for item in twice if item["regional"] == UNASSIGNED_LABEL]) == 1
