"""Regressao da auditoria financeira 2026-08-26 (achado C1): o mesmo valor pago esta persistido
em tres lugares - a linha `collaborator_scores`, o cache JSON `result_summary.score_summaries` e
os totais `result_summary`/`cards` - e cada endpoint le um lugar diferente.

Evidencia real que originou estes testes: o fechamento #1601 (07/2026, pago) responde
R$ 18.191,18 em `GET /calculation-runs/{id}` (cache) e R$ 18.271,68 em `GET /calculation-runs`
(soma das linhas). Diferenca de R$ 80,50 em 18 colaboradores, no mesmo fechamento pago.

A linha `collaborator_scores` e a fonte da verdade: e o que o extrato PDF entregue ao
colaborador, o historico de fechamentos e o bonus de lideranca ja usam hoje.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm.attributes import flag_modified

from app.api.routes.calculation_runs import _apply_point_balance_after_payment
from app.models import CalculationRun, CollaboratorScore


@pytest.fixture()
def run_with_divergent_cache(db_session, make_collaborator):
    """Fechamento cujo cache JSON discorda das linhas gravadas.

    Nao e um cenario inventado: e exatamente o estado em que o #1601 esta em producao, depois de
    um script de manutencao ter reescrito as linhas de `collaborator_scores` sem tocar no
    `result_summary` (ver achado C4 - lancamentos de saldo criados fora da API).
    """
    collaborator = make_collaborator(name="Tecnico Divergente")
    run = CalculationRun(
        reference_month=7,
        reference_year=2026,
        regional=None,
        point_value=0.35,
        status="paid",
        paid_at=datetime(2026, 8, 5, tzinfo=timezone.utc),
    )
    db_session.add(run)
    db_session.flush()

    # LINHA: valor bruto, sem desconto de garantia (o que o PDF e o historico mostram).
    db_session.add(
        CollaboratorScore(
            calculation_run_id=run.id,
            collaborator_id=collaborator.id,
            service_orders_count=128,
            gross_points=1400.0,
            penalty_points=164.0,
            net_points=1236.0,
            health_multiplier=0.3,
            health_status="Critica",
            final_points=370.8,
            estimated_payment=129.78,
            balance_adjustment_points=0.0,
            balance_after=370.8,
        )
    )
    # CACHE: previa do rascunho, com um desconto de 14 pontos que nao foi consumido no pagamento.
    run.result_summary = {
        "dashboard_cache_version": 3,
        "final_points": 356.8,
        "estimated_payment": 124.88,
        "cards": {"final_points": 356.8, "estimated_payment": 124.88, "total_service_orders": 128},
        "score_summaries": {
            str(collaborator.id): {
                "total_service_orders": 128,
                "gross_points": 1400.0,
                "penalty_points": 164.0,
                "net_points": 1236.0,
                "health_multiplier": 0.3,
                "health_status": "Critica",
                "regional": collaborator.regional,
                "final_points": 356.8,
                "estimated_payment": 124.88,
                "balance_adjustment_points": -14.0,
                "balance_after": 356.8,
                "gross_final_points": 370.8,
                "gross_estimated_payment": 129.78,
            }
        },
    }
    flag_modified(run, "result_summary")
    db_session.commit()
    return run, collaborator


def test_run_detail_and_history_report_the_same_total(client, run_with_divergent_cache):
    """Dois endpoints do mesmo modulo nao podem responder valores diferentes para o mesmo
    fechamento. Hoje `GET /calculation-runs/{id}` le o cache e `GET /calculation-runs` soma as
    linhas - quem confere pela tela e quem confere pelo historico chegam a numeros diferentes e
    nao ha como saber qual esta certo."""
    run, _ = run_with_divergent_cache

    detail = client.get(f"/api/calculation-runs/{run.id}")
    assert detail.status_code == 200
    detail_total = round(sum(float(score["estimated_payment"]) for score in detail.json()["scores"]), 2)

    history = client.get("/api/calculation-runs", params={"include_empty": True})
    assert history.status_code == 200
    history_run = next(item for item in history.json() if item["id"] == run.id)

    assert detail_total == history_run["estimated_payment"]


def test_run_detail_reports_the_persisted_row_not_the_cache(client, run_with_divergent_cache):
    """A linha `collaborator_scores` e a fonte unica: e o que o extrato PDF do colaborador, o
    historico e o bonus de lideranca ja leem. O detalhe do fechamento tem que concordar com ela,
    nao com um cache que pode ter sido escrito num rascunho anterior."""
    run, collaborator = run_with_divergent_cache

    payload = client.get(f"/api/calculation-runs/{run.id}").json()
    score = next(item for item in payload["scores"] if item["collaborator_id"] == collaborator.id)

    assert score["final_points"] == 370.8
    assert score["estimated_payment"] == 129.78
    assert score["balance_adjustment_points"] == 0.0


def test_result_summary_totals_match_the_sum_of_the_rows(client, run_with_divergent_cache):
    """Invariante permanente: o total gravado em `result_summary` (que alimenta o card
    'Total a pagar') tem que ser exatamente a soma das linhas. Sem isso, o card e a tabela da
    mesma tela discordam."""
    run, _ = run_with_divergent_cache

    payload = client.get(f"/api/calculation-runs/{run.id}").json()
    rows_total = round(sum(float(score["estimated_payment"]) for score in payload["scores"]), 2)
    rows_points = round(sum(float(score["final_points"]) for score in payload["scores"]), 2)

    assert round(float(payload["result_summary"]["estimated_payment"]), 2) == rows_total
    assert round(float(payload["result_summary"]["final_points"]), 2) == rows_points
    assert round(float(payload["result_summary"]["cards"]["estimated_payment"]), 2) == rows_total


def test_payment_persists_cache_updates_even_when_nothing_changed(db_session, admin_user, run_with_divergent_cache):
    """Regressao especifica do defeito de codigo: `_apply_point_balance_after_payment` escreve no
    cache SEMPRE, mas so chamava `flag_modified` dentro de `if adjusted:`. O SQLAlchemy nao detecta
    mutacao in-place de coluna JSON - quando nada mudou nas linhas (`adjusted == False`), as
    escritas no cache eram descartadas silenciosamente e a divergencia sobrevivia ao pagamento.

    Aqui a linha ja esta no valor final (nada a ajustar), entao `adjusted` e False - e mesmo assim
    o cache precisa terminar igual a linha depois do commit.
    """
    run, collaborator = run_with_divergent_cache

    _apply_point_balance_after_payment(db_session, run, admin_user)
    db_session.commit()
    db_session.expire_all()

    reloaded = db_session.get(CalculationRun, run.id)
    cached = reloaded.result_summary["score_summaries"][str(collaborator.id)]
    row = next(score for score in reloaded.scores if score.collaborator_id == collaborator.id)

    assert cached["final_points"] == row.final_points
    assert cached["estimated_payment"] == row.estimated_payment
    assert cached["balance_adjustment_points"] == row.balance_adjustment_points
