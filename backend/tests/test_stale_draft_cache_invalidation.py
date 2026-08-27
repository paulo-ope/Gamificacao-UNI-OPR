"""Achado real de 2026-08-27: `_refresh_stale_draft_previews` (calculation_runs.py) corrige
final_points/estimated_payment de OUTROS rascunhos quando um débito de garantia compartilhado é
consumido por um pagamento - mas nunca tocava em cost_by_regional/cost_by_group/cost_by_subject/
cost_by_collaborator desses rascunhos. O detalhamento ficava congelado com o valor de ANTES do
débito ser consumido, enquanto cards/final_points já refletiam o valor de depois - GET
/dashboard/summary detectava a divergência (corretamente, via `_regional_breakdown_is_consistent`)
e recomputava tudo do zero a cada carregamento (5-7s medidos num caso real: run com O.S. reais,
R$ 15.073,50 em cache vs R$ 11.967,06 reconciliado).

Corrigido invalidando `dashboard_cache_version` no rascunho afetado em vez de tentar redistribuir
o delta pelos detalhamentos (arriscaria uma versão mais sutil do mesmo bug) - a rota já sabe
recomputar ao vivo quando esse marcador está ausente."""
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm.attributes import flag_modified

from app.models import CalculationRun, CollaboratorScore, PointBalanceEntry

REGIONAL = "UNI - JI PARANA"


@pytest.fixture()
def paid_run_and_stale_draft(db_session, make_collaborator, make_service_order, scoring_setup):
    collaborator = make_collaborator(name="Tecnico Compartilhado", regional=REGIONAL)
    for day in (10, 20):
        make_service_order(
            collaborator,
            opened_at=datetime(2026, 8, day, tzinfo=timezone.utc),
            closed_at=datetime(2026, 8, day, tzinfo=timezone.utc),
            regional=REGIONAL,
        )

    # Run A: sera marcado como pago agora - o debito abaixo tem alvo no mes/ano dele, entao e
    # consumido de verdade nesse pagamento.
    run_a = CalculationRun(
        reference_month=8, reference_year=2026, regional=None, point_value=0.35,
        status="approved", created_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
    )
    db_session.add(run_a)
    db_session.flush()
    db_session.add(CollaboratorScore(
        calculation_run_id=run_a.id, collaborator_id=collaborator.id, service_orders_count=2,
        gross_points=1000.0, penalty_points=0.0, net_points=1000.0, health_multiplier=1.0,
        health_status="Boa", final_points=986.0, estimated_payment=345.1,
        balance_adjustment_points=-14.0, balance_after=986.0,
    ))
    run_a.result_summary = {
        "dashboard_cache_version": 3, "final_points": 986.0, "estimated_payment": 345.1,
        "cards": {"final_points": 986.0, "estimated_payment": 345.1, "total_service_orders": 2},
        "score_summaries": {
            str(collaborator.id): {
                "total_service_orders": 2, "gross_points": 1000.0, "penalty_points": 0.0,
                "net_points": 1000.0, "health_multiplier": 1.0, "health_status": "Boa",
                "regional": REGIONAL, "final_points": 986.0, "estimated_payment": 345.1,
                "balance_adjustment_points": -14.0, "balance_after": 986.0,
                "gross_final_points": 1000.0, "gross_estimated_payment": 350.0,
            }
        },
    }
    flag_modified(run_a, "result_summary")

    # Debito com alvo no periodo de run_a - sera consumido quando run_a for pago.
    db_session.add(PointBalanceEntry(
        collaborator_id=collaborator.id, entry_type="post_payment_warranty_debit", points=-14.0,
        status="pending", target_reference_month=8, target_reference_year=2026,
        reason="Garantia com alvo no mes que sera pago.",
    ))

    # Run B: rascunho de OUTRO periodo, mesmo colaborador, com a MESMA previa de desconto (o
    # preview olha os lancamentos pendentes do colaborador, nao um run especifico) - e o rascunho
    # "stale" que _refresh_stale_draft_previews deve atualizar quando run_a for pago.
    run_b = CalculationRun(
        reference_month=9, reference_year=2026, regional=None, point_value=0.35,
        status="draft", created_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
    )
    db_session.add(run_b)
    db_session.flush()
    db_session.add(CollaboratorScore(
        calculation_run_id=run_b.id, collaborator_id=collaborator.id, service_orders_count=1,
        gross_points=500.0, penalty_points=0.0, net_points=500.0, health_multiplier=1.0,
        health_status="Boa", final_points=486.0, estimated_payment=170.1,
        balance_adjustment_points=-14.0, balance_after=486.0,
    ))
    run_b.result_summary = {
        "dashboard_cache_version": 3, "final_points": 486.0, "estimated_payment": 170.1,
        "cards": {"final_points": 486.0, "estimated_payment": 170.1, "total_service_orders": 1},
        "score_summaries": {
            str(collaborator.id): {
                "total_service_orders": 1, "gross_points": 500.0, "penalty_points": 0.0,
                "net_points": 500.0, "health_multiplier": 1.0, "health_status": "Boa",
                "regional": REGIONAL, "final_points": 486.0, "estimated_payment": 170.1,
                "balance_adjustment_points": -14.0, "balance_after": 486.0,
                "gross_final_points": 500.0, "gross_estimated_payment": 175.0,
            }
        },
        # Detalhamento gravado com o valor JA descontado - fica desatualizado (nao apagado, nao
        # redistribuido) quando o debito for consumido por run_a.
        "cost_by_regional": [{"regional": REGIONAL, "orders": 1, "estimated_payment": 170.1}],
    }
    flag_modified(run_b, "result_summary")

    db_session.commit()
    return run_a, run_b, collaborator


def test_paying_a_run_invalidates_stale_draft_dashboard_cache(client, db_session, paid_run_and_stale_draft):
    run_a, run_b, _ = paid_run_and_stale_draft

    response = client.patch(f"/api/calculation-runs/{run_a.id}/status", json={"status": "paid"})
    assert response.status_code == 200

    db_session.expire_all()
    reloaded_b = db_session.get(CalculationRun, run_b.id)

    # O debito foi consumido por run_a - run_b nao deve mais descontar 14 pontos do colaborador.
    score_b = db_session.query(CollaboratorScore).filter_by(calculation_run_id=run_b.id).one()
    assert score_b.balance_adjustment_points == 0.0
    assert reloaded_b.result_summary["final_points"] == 500.0
    assert reloaded_b.result_summary["cards"]["final_points"] == 500.0

    # O marcador de cache foi invalidado - a rota de dashboard sabe que precisa recomputar os
    # detalhamentos ao vivo em vez de confiar no cost_by_regional desatualizado abaixo.
    assert "dashboard_cache_version" not in reloaded_b.result_summary
    # cost_by_regional continua desatualizado de propósito (nao foi redistribuído por delta) -
    # é exatamente por isso que o marcador precisa estar ausente.
    assert reloaded_b.result_summary["cost_by_regional"][0]["estimated_payment"] == 170.1


def test_paying_a_run_does_not_touch_unrelated_drafts(client, db_session, paid_run_and_stale_draft, make_collaborator):
    """Rascunho de um colaborador NAO afetado pelo pagamento mantem o cache intacto - a
    invalidacao e cirurgica, nao um apagar geral."""
    run_a, _, _ = paid_run_and_stale_draft
    other_collaborator = make_collaborator(name="Sem Relacao", regional=REGIONAL)
    unrelated_run = CalculationRun(
        reference_month=9, reference_year=2026, regional=None, point_value=0.35, status="draft",
        created_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
    )
    db_session.add(unrelated_run)
    db_session.flush()
    db_session.add(CollaboratorScore(
        calculation_run_id=unrelated_run.id, collaborator_id=other_collaborator.id,
        service_orders_count=1, gross_points=100.0, penalty_points=0.0, net_points=100.0,
        health_multiplier=1.0, health_status="Boa", final_points=100.0, estimated_payment=35.0,
        balance_adjustment_points=0.0, balance_after=100.0,
    ))
    unrelated_run.result_summary = {"dashboard_cache_version": 3, "cost_by_regional": []}
    flag_modified(unrelated_run, "result_summary")
    db_session.commit()

    assert client.patch(f"/api/calculation-runs/{run_a.id}/status", json={"status": "paid"}).status_code == 200

    db_session.expire_all()
    reloaded = db_session.get(CalculationRun, unrelated_run.id)
    assert reloaded.result_summary["dashboard_cache_version"] == 3
