"""Regressao da auditoria financeira 2026-08-26 (achado C1, agravante): marcar um fechamento como
pago recompoe `final_points`/`estimated_payment` a partir do valor bruto, mas NAO recalcula nenhum
dos detalhamentos financeiros - `cost_by_regional`, `cost_by_group`, `cost_by_subject`,
`cost_by_collaborator`, `penalty_distribution` e `health_by_regional` ficam congelados com os
valores da previa do rascunho, para sempre.

Cenario reproduzido: o rascunho previu um desconto de garantia de 14 pontos, mas no pagamento o
lancamento nao era elegivel (o alvo e um mes posterior), entao o valor volta ao bruto. A tela de
fechamento mostra o card "Total a pagar" ja corrigido e, logo abaixo, a tabela
"Valor a ser pago por regional" ainda com o valor descontado.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm.attributes import flag_modified

from app.models import CalculationRun, CollaboratorScore, PointBalanceEntry

REGIONAL = "UNI - JI PARANA"
GROSS_POINTS = 370.8
GROSS_PAYMENT = 129.78
PREVIEW_POINTS = 356.8
PREVIEW_PAYMENT = 124.88


@pytest.fixture()
def approved_run_with_deferred_debit(db_session, make_collaborator, make_service_order, scoring_setup):
    collaborator = make_collaborator(name="Tecnico Com Previa", regional=REGIONAL)
    # O.S reais do periodo: `refresh_run_breakdowns` reconstroi os detalhamentos a partir delas.
    # Os valores em dinheiro continuam vindo da linha `collaborator_scores` (fonte unica) - as
    # O.S so definem como esse total se distribui entre regional/grupo/assunto.
    for day in (10, 20):
        make_service_order(
            collaborator,
            opened_at=datetime(2026, 7, day, tzinfo=timezone.utc),
            closed_at=datetime(2026, 7, day, tzinfo=timezone.utc),
            regional=REGIONAL,
        )
    run = CalculationRun(
        reference_month=7,
        reference_year=2026,
        regional=None,
        point_value=0.35,
        status="approved",
        created_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
    )
    db_session.add(run)
    db_session.flush()

    db_session.add(
        CollaboratorScore(
            calculation_run_id=run.id,
            collaborator_id=collaborator.id,
            service_orders_count=2,
            gross_points=1400.0,
            penalty_points=164.0,
            net_points=1236.0,
            health_multiplier=0.3,
            health_status="Critica",
            final_points=PREVIEW_POINTS,
            estimated_payment=PREVIEW_PAYMENT,
            balance_adjustment_points=-14.0,
            balance_after=PREVIEW_POINTS,
        )
    )
    # Debito de garantia cujo alvo e 09/2026: nao pode ser consumido por um fechamento de 07/2026,
    # entao o pagamento devolve os 14 pontos que a previa do rascunho tinha descontado.
    db_session.add(
        PointBalanceEntry(
            collaborator_id=collaborator.id,
            entry_type="post_payment_warranty_debit",
            points=-14.0,
            status="pending",
            target_reference_month=9,
            target_reference_year=2026,
            reason="Garantia com alvo em setembro/2026.",
        )
    )

    run.result_summary = {
        "dashboard_cache_version": 3,
        "final_points": PREVIEW_POINTS,
        "estimated_payment": PREVIEW_PAYMENT,
        "cards": {"final_points": PREVIEW_POINTS, "estimated_payment": PREVIEW_PAYMENT, "total_service_orders": 2},
        "score_summaries": {
            str(collaborator.id): {
                "total_service_orders": 2,
                "gross_points": 1400.0,
                "penalty_points": 164.0,
                "net_points": 1236.0,
                "health_multiplier": 0.3,
                "health_status": "Critica",
                "regional": REGIONAL,
                "final_points": PREVIEW_POINTS,
                "estimated_payment": PREVIEW_PAYMENT,
                "balance_adjustment_points": -14.0,
                "balance_after": PREVIEW_POINTS,
                "gross_final_points": GROSS_POINTS,
                "gross_estimated_payment": GROSS_PAYMENT,
            }
        },
        # Detalhamento gravado no rascunho, com o valor JA descontado pela previa.
        "cost_by_regional": [{"regional": REGIONAL, "orders": 2, "estimated_payment": PREVIEW_PAYMENT}],
        "cost_by_collaborator": [
            {
                "collaborator_id": collaborator.id,
                "collaborator_name": collaborator.name,
                "regional": REGIONAL,
                "orders": 2,
                "net_points": 1236.0,
                "estimated_payment": PREVIEW_PAYMENT,
            }
        ],
    }
    flag_modified(run, "result_summary")
    db_session.commit()
    return run, collaborator


def _pay(client, run_id):
    return client.patch(f"/api/calculation-runs/{run_id}/status", json={"status": "paid"})


def test_payment_restores_the_gross_value_when_the_debit_is_not_eligible(
    client, db_session, approved_run_with_deferred_debit
):
    """Trava de sanidade do cenario (ja funciona hoje): o desconto previsto no rascunho e
    devolvido no pagamento porque o lancamento tem alvo num mes posterior."""
    run, collaborator = approved_run_with_deferred_debit

    response = _pay(client, run.id)
    assert response.status_code == 200

    db_session.expire_all()
    score = db_session.query(CollaboratorScore).filter_by(calculation_run_id=run.id).one()
    assert score.final_points == GROSS_POINTS
    assert score.estimated_payment == GROSS_PAYMENT
    assert score.balance_adjustment_points == 0.0


def test_payment_refreshes_cost_by_regional(client, db_session, approved_run_with_deferred_debit):
    """O detalhamento por regional precisa acompanhar o valor efetivamente pago. Hoje ele fica
    com o valor da previa do rascunho e a mesma tela mostra dois numeros diferentes."""
    run, _ = approved_run_with_deferred_debit

    assert _pay(client, run.id).status_code == 200
    db_session.expire_all()
    reloaded = db_session.get(CalculationRun, run.id)

    total_by_regional = round(
        sum(float(item["estimated_payment"]) for item in reloaded.result_summary["cost_by_regional"]), 2
    )
    assert total_by_regional == GROSS_PAYMENT


def test_payment_refreshes_cost_by_collaborator(client, db_session, approved_run_with_deferred_debit):
    """Mesma exigencia para o detalhamento por colaborador - e o que a aba de ranking financeiro
    usa pra explicar de onde vem o valor de cada pessoa."""
    run, collaborator = approved_run_with_deferred_debit

    assert _pay(client, run.id).status_code == 200
    db_session.expire_all()
    reloaded = db_session.get(CalculationRun, run.id)

    entry = next(
        item for item in reloaded.result_summary["cost_by_collaborator"] if item["collaborator_id"] == collaborator.id
    )
    assert round(float(entry["estimated_payment"]), 2) == GROSS_PAYMENT


def test_paid_run_totals_agree_across_summary_cards_and_rows(client, db_session, approved_run_with_deferred_debit):
    """Depois de pago, os tres numeros que a tela mostra juntos - card 'Total a pagar'
    (`cards.estimated_payment`), total do resumo e soma das linhas - tem que ser identicos."""
    run, _ = approved_run_with_deferred_debit

    assert _pay(client, run.id).status_code == 200
    db_session.expire_all()
    reloaded = db_session.get(CalculationRun, run.id)

    rows_total = round(sum(float(score.estimated_payment) for score in reloaded.scores), 2)
    assert round(float(reloaded.result_summary["estimated_payment"]), 2) == rows_total
    assert round(float(reloaded.result_summary["cards"]["estimated_payment"]), 2) == rows_total
