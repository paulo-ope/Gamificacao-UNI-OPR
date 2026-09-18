"""Regressao dos tres defeitos da Gamificacao levantados em 2026-09-10.

1. **Tela travada no mes 07**: `latest_run` priorizava `status="paid"` sobre o historico inteiro,
   nao dentro do periodo. Com 07/2026 pago (#1601) e 316 rascunhos de 08/2026, `/dashboard/bootstrap`
   e `/dashboard/summary` devolviam julho pra sempre - agosto so apareceria no dia em que alguem
   marcasse agosto como pago.

2. **Quantidade de O.S. inflada**: `cards.total_service_orders` conta todo o periodo, inclusive O.S.
   de tecnico sem cadastro, que nunca entram no ranking nem geram pagamento. Em 07/2026 a tela
   mostrava 10.685 no card do Fechamento enquanto a aba Ranking dizia "9.122 entraram no ranking,
   1.563 ficaram fora" - a mesma tela se contradizendo.

3. **Lentidao**: `_regional_breakdown_is_consistent` exigia IGUALDADE entre a soma de
   "por regional" e o total a pagar. O detalhamento por regional pode legitimamente somar MENOS
   (quem tem multiplicador de saude 0 e recebe so credito de saldo entra no total e em nenhuma
   regional - R$ 1.291,08 em 08/2026), entao a guarda reprovava o cache CORRETO e a rota
   recalculava o mes inteiro em cada requisicao: 4,44s contra 0,31s servindo o cache.
"""
from datetime import datetime, timezone

import pytest

from app.api.routes.dashboard import _regional_breakdown_is_consistent
from app.models import CalculationRun, CollaboratorScore
from app.services.calculation import latest_run, serialize_run


def _run(db_session, month, year, status, created_at, regional=None):
    run = CalculationRun(
        reference_month=month,
        reference_year=year,
        regional=regional,
        point_value=0.35,
        status=status,
        created_at=created_at,
    )
    db_session.add(run)
    db_session.flush()
    return run


def _score(db_session, run, collaborator, orders):
    score = CollaboratorScore(
        calculation_run_id=run.id,
        collaborator_id=collaborator.id,
        service_orders_count=orders,
        gross_points=orders * 10.0,
        penalty_points=0.0,
        net_points=orders * 10.0,
        health_multiplier=1.0,
        health_status="Boa",
        final_points=orders * 10.0,
        estimated_payment=round(orders * 10.0 * 0.35, 2),
        balance_adjustment_points=0.0,
        balance_after=0.0,
    )
    db_session.add(score)
    db_session.flush()
    return score


# --------------------------------------------------------------------------------------------
# 1. Periodo primeiro, status depois
# --------------------------------------------------------------------------------------------


def test_latest_run_escolhe_o_periodo_mais_recente_mesmo_com_mes_anterior_pago(db_session, make_collaborator):
    """O cenario exato da producao: julho pago, agosto so em rascunho."""
    tecnico = make_collaborator(name="Tecnico Agosto")
    julho = _run(db_session, 7, 2026, "paid", datetime(2026, 8, 3, tzinfo=timezone.utc))
    _score(db_session, julho, tecnico, 128)
    agosto = _run(db_session, 8, 2026, "draft", datetime(2026, 8, 21, tzinfo=timezone.utc))
    _score(db_session, agosto, tecnico, 96)

    escolhido = latest_run(db_session)

    assert escolhido is not None
    assert (escolhido.reference_month, escolhido.reference_year) == (8, 2026)
    assert escolhido.id == agosto.id


def test_latest_run_ainda_prefere_o_pago_dentro_do_mesmo_periodo(db_session, make_collaborator):
    """A prioridade de status continua valendo - so deixou de atravessar periodos.

    Sem isso, uma revisao CANCELADA criada depois do pagamento voltaria a esconder o fechamento
    pago do mesmo mes (achado A9, ja corrigido antes no Portal).
    """
    tecnico = make_collaborator(name="Tecnico Julho")
    pago = _run(db_session, 7, 2026, "paid", datetime(2026, 8, 3, tzinfo=timezone.utc))
    _score(db_session, pago, tecnico, 128)
    cancelado = _run(db_session, 7, 2026, "cancelled", datetime(2026, 8, 6, tzinfo=timezone.utc))
    _score(db_session, cancelado, tecnico, 128)

    escolhido = latest_run(db_session)

    assert escolhido is not None
    assert escolhido.id == pago.id


def test_latest_run_ignora_periodo_cujo_unico_fechamento_foi_cancelado(db_session, make_collaborator):
    tecnico = make_collaborator(name="Tecnico Base")
    julho = _run(db_session, 7, 2026, "paid", datetime(2026, 8, 3, tzinfo=timezone.utc))
    _score(db_session, julho, tecnico, 128)
    agosto_cancelado = _run(db_session, 8, 2026, "cancelled", datetime(2026, 9, 1, tzinfo=timezone.utc))
    _score(db_session, agosto_cancelado, tecnico, 96)

    escolhido = latest_run(db_session)

    assert escolhido is not None
    assert escolhido.id == julho.id


def test_dashboard_bootstrap_abre_no_periodo_mais_recente(client, db_session, make_collaborator):
    tecnico = make_collaborator(name="Tecnico Bootstrap")
    julho = _run(db_session, 7, 2026, "paid", datetime(2026, 8, 3, tzinfo=timezone.utc))
    _score(db_session, julho, tecnico, 128)
    agosto = _run(db_session, 8, 2026, "draft", datetime(2026, 8, 21, tzinfo=timezone.utc))
    _score(db_session, agosto, tecnico, 96)

    payload = client.get("/api/dashboard/bootstrap").json()

    assert payload["reference_month"] == 8
    assert payload["reference_year"] == 2026
    assert payload["calculation_run_id"] == agosto.id


# --------------------------------------------------------------------------------------------
# 2. Quantidade de O.S. por equipe cadastrada
# --------------------------------------------------------------------------------------------


@pytest.fixture()
def run_com_tecnico_sem_cadastro(db_session, make_collaborator):
    """Fechamento com 100 O.S. de equipe cadastrada e 40 de tecnico sem cadastro."""
    cadastrado = make_collaborator(name="Tecnico Cadastrado", registered=True)
    sem_cadastro = make_collaborator(name="Tecnico Sem Cadastro", registered=False)
    run = _run(db_session, 8, 2026, "draft", datetime(2026, 8, 21, tzinfo=timezone.utc))
    _score(db_session, run, cadastrado, 100)
    sem_cadastro_score = _score(db_session, run, sem_cadastro, 40)
    # Nao cadastrado nunca gera valor a pagar (regra ja existente em `calculate_scores`).
    sem_cadastro_score.estimated_payment = 0.0
    run.result_summary = {
        "dashboard_cache_version": 3,
        "cards": {"total_service_orders": 140, "estimated_payment": 350.0},
    }
    db_session.flush()
    return run


def test_cards_separam_os_de_equipe_cadastrada_do_total_do_periodo(db_session, run_com_tecnico_sem_cadastro):
    cards = (serialize_run(run_com_tecnico_sem_cadastro, db_session) or {})["result_summary"]["cards"]

    assert cards["total_service_orders"] == 140
    assert cards["registered_service_orders"] == 100
    assert cards["unregistered_service_orders"] == 40
    assert cards["registered_collaborators"] == 1
    assert cards["unregistered_collaborators"] == 1


def test_contadores_de_cadastro_aparecem_em_fechamento_antigo_sem_recalcular(db_session, run_com_tecnico_sem_cadastro):
    """O `result_summary` gravado nao tem os campos novos - a reconciliacao vem das linhas.

    E o que faz a correcao valer retroativamente pra todo o historico (inclusive fechamentos pagos,
    que nao podem ser recalculados) sem reprocessar nada.
    """
    assert "registered_service_orders" not in run_com_tecnico_sem_cadastro.result_summary["cards"]

    cards = (serialize_run(run_com_tecnico_sem_cadastro, db_session) or {})["result_summary"]["cards"]

    assert cards["registered_service_orders"] == 100


def test_dashboard_summary_entrega_a_contagem_de_equipe_cadastrada(client, run_com_tecnico_sem_cadastro):
    payload = client.get("/api/dashboard/summary?reference_month=8&reference_year=2026").json()

    assert payload["cards"]["registered_service_orders"] == 100
    assert payload["cards"]["unregistered_service_orders"] == 40
    assert payload["cards"]["total_service_orders"] == 140


def test_auditoria_do_periodo_conta_so_equipe_cadastrada_por_padrao(
    client, db_session, make_collaborator, make_service_order, scoring_setup
):
    cadastrado = make_collaborator(name="Auditoria Cadastrado", registered=True)
    sem_cadastro = make_collaborator(name="Auditoria Sem Cadastro", registered=False)
    for _ in range(3):
        make_service_order(cadastrado)
    make_service_order(sem_cadastro)

    padrao = client.get("/api/audit/service-orders-scoring?reference_month=6&reference_year=2026").json()
    assert padrao["summary"]["total_service_orders"] == 3
    assert padrao["registration_scope"] == {
        "only_registered": True,
        "period_total_service_orders": 4,
        "period_registered_service_orders": 3,
        "period_unregistered_service_orders": 1,
    }
    assert {order["collaborator_name"] for order in padrao["orders"]} == {"Auditoria Cadastrado"}

    completo = client.get(
        "/api/audit/service-orders-scoring?reference_month=6&reference_year=2026&only_registered=false"
    ).json()
    assert completo["summary"]["total_service_orders"] == 4
    assert completo["summary"]["registered_service_orders"] == 3
    assert completo["summary"]["unregistered_service_orders"] == 1
    assert completo["registration_scope"]["only_registered"] is False


# --------------------------------------------------------------------------------------------
# 3. Guarda de consistencia do detalhamento por regional
# --------------------------------------------------------------------------------------------

CARDS = {"estimated_payment": 11967.06}
BONUS = {"total_bonus_amount": 4397.52}  # teto = 16.364,58


def test_detalhamento_menor_que_o_total_e_servido():
    """Cenario real de 08/2026: R$ 1.291,08 de 37 pessoas com multiplicador 0 recebendo apenas
    credito de saldo entram no total a pagar e em nenhuma regional. O cache esta correto."""
    cache = {"cost_by_regional": [{"estimated_payment": 15073.50}]}

    assert _regional_breakdown_is_consistent(cache, CARDS, BONUS) is True


def test_detalhamento_inflado_e_recusado():
    """Cenario real do #1601 (07/2026, pago): R$ 38.264,02 gravados contra R$ 24.282,77 reais."""
    cache = {"cost_by_regional": [{"estimated_payment": 38264.02}]}

    assert _regional_breakdown_is_consistent(cache, {"estimated_payment": 18271.68}, {"total_bonus_amount": 6011.09}) is False


def test_detalhamento_exatamente_igual_ao_total_e_servido():
    cache = {"cost_by_regional": [{"estimated_payment": 16364.58}]}

    assert _regional_breakdown_is_consistent(cache, CARDS, BONUS) is True


def test_diferenca_de_um_centavo_nao_derruba_o_cache():
    """Tolerancia que ja existia: somar N valores de 2 casas oscila no ultimo centavo."""
    cache = {"cost_by_regional": [{"estimated_payment": 16364.59}]}

    assert _regional_breakdown_is_consistent(cache, CARDS, BONUS) is True


def test_cache_sem_detalhamento_continua_sendo_recusado():
    assert _regional_breakdown_is_consistent({}, CARDS, BONUS) is False
    assert _regional_breakdown_is_consistent({"cost_by_regional": []}, CARDS, BONUS) is False
