"""Regressao da auditoria financeira 2026-08-26 (achado A9 / divergencia D1): o portal do
colaborador escolhia o fechamento pelo `created_at` mais recente, SEM filtrar status.

Consequencia real: `recalculate_current_period` cria um `CalculationRun` novo a cada ciclo do
sincronizador do IXC (20 min) e a base acumulou 1.100 rascunhos. O colaborador via o valor do
ultimo rascunho automatico enquanto a tela de fechamento, o historico e o extrato PDF mostravam o
fechamento PAGO - dois numeros oficiais diferentes para "quanto eu recebi".

O resto do modulo ja resolvia isso com `pick_run_by_status_priority` (paga > nao cancelada >
qualquer, sempre a mais recente dentro de cada nivel). O portal passa a usar o mesmo criterio.

MUDANCA DE COMPORTAMENTO DECLARADA: o numero exibido no portal muda quando existe fechamento pago
do periodo e um rascunho mais novo. Passa a mostrar o pago - que e o valor que a pessoa recebeu.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import CalculationRun, CollaboratorScore
from app.services.portal_dashboard import _portal_run

BASE = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _run(db_session, collaborator, *, status, minutes, payment, month=7, year=2026):
    run = CalculationRun(
        reference_month=month,
        reference_year=year,
        regional=None,
        point_value=0.35,
        status=status,
        created_at=BASE + timedelta(minutes=minutes),
    )
    db_session.add(run)
    db_session.flush()
    db_session.add(
        CollaboratorScore(
            calculation_run_id=run.id,
            collaborator_id=collaborator.id,
            service_orders_count=5,
            gross_points=100.0,
            net_points=100.0,
            final_points=100.0,
            estimated_payment=payment,
            health_multiplier=1.0,
        )
    )
    db_session.flush()
    return run


def test_portal_prefers_the_paid_closure_over_a_newer_draft(db_session, make_collaborator):
    """O caso da base real: fechamento pago em 05/08 e centenas de rascunhos automaticos criados
    depois. O portal tem que mostrar o pago."""
    collaborator = make_collaborator()
    paid = _run(db_session, collaborator, status="paid", minutes=0, payment=70.0)
    _run(db_session, collaborator, status="draft", minutes=500, payment=99.99)

    selected = _portal_run(db_session)

    assert selected is not None
    assert selected.id == paid.id
    assert selected.status == "paid"


def test_portal_ignores_a_newer_cancelled_revision(db_session, make_collaborator):
    """Mesmo racional de `pick_run_by_status_priority`: uma revisao cancelada criada DEPOIS do
    pagamento nao pode vencer so por ser mais nova e esconder o pagamento real."""
    collaborator = make_collaborator()
    paid = _run(db_session, collaborator, status="paid", minutes=0, payment=70.0)
    _run(db_session, collaborator, status="cancelled", minutes=500, payment=0.0)

    assert _portal_run(db_session).id == paid.id


def test_portal_respects_the_requested_period(db_session, make_collaborator):
    """Com mes/ano informados, a escolha continua restrita a esse periodo - o pago de OUTRO mes
    nao pode vazar para o recorte pedido."""
    collaborator = make_collaborator()
    _run(db_session, collaborator, status="paid", minutes=0, payment=70.0, month=7)
    august_draft = _run(db_session, collaborator, status="draft", minutes=10, payment=35.0, month=8)

    selected = _portal_run(db_session, reference_month=8, reference_year=2026)

    assert selected is not None
    assert selected.id == august_draft.id
    assert (selected.reference_month, selected.reference_year) == (8, 2026)


def test_portal_falls_back_to_the_newest_draft_when_nothing_was_paid(db_session, make_collaborator):
    """Mes corrente, ainda sem pagamento: o rascunho mais recente continua sendo a melhor resposta
    disponivel - o comportamento antigo se preserva onde ele estava correto."""
    collaborator = make_collaborator()
    _run(db_session, collaborator, status="draft", minutes=0, payment=10.0)
    newest = _run(db_session, collaborator, status="draft", minutes=100, payment=20.0)

    assert _portal_run(db_session).id == newest.id


def test_portal_prefers_a_non_cancelled_draft_over_a_newer_cancelled_one(db_session, make_collaborator):
    """Sem nenhum pago, cancelado nunca vence uma apuracao viva mais antiga."""
    collaborator = make_collaborator()
    alive = _run(db_session, collaborator, status="review", minutes=0, payment=50.0)
    _run(db_session, collaborator, status="cancelled", minutes=100, payment=0.0)

    assert _portal_run(db_session).id == alive.id


def test_portal_returns_none_without_any_run(db_session):
    assert _portal_run(db_session) is None


def test_default_entry_keeps_showing_the_current_period_not_the_last_paid_one(db_session, make_collaborator):
    """A prioridade por `paid` resolve o status DENTRO do periodo, nunca escolhe o periodo.

    Sem esta trava, a entrada normal do portal (sem mes/ano) passaria a mostrar sempre a ultima
    competencia PAGA e esconderia o mes corrente em andamento - medido na base real, o padrao
    pularia de 08/2026 (rascunho) para 07/2026 (pago), trocando "como estou este mes" por "quanto
    recebi no mes passado".
    """
    collaborator = make_collaborator()
    _run(db_session, collaborator, status="paid", minutes=0, payment=70.0, month=7)
    current = _run(db_session, collaborator, status="draft", minutes=10, payment=35.0, month=8)

    selected = _portal_run(db_session)

    assert selected is not None
    assert selected.id == current.id
    assert (selected.reference_month, selected.reference_year) == (8, 2026)


def test_default_entry_skips_a_period_whose_only_run_was_cancelled(db_session, make_collaborator):
    """Um periodo cujo unico fechamento foi cancelado nao e "o periodo mais recente" util - o
    portal cai para o anterior em vez de mostrar um cancelado ou nada."""
    collaborator = make_collaborator()
    july_paid = _run(db_session, collaborator, status="paid", minutes=0, payment=70.0, month=7)
    _run(db_session, collaborator, status="cancelled", minutes=10, payment=0.0, month=8)

    assert _portal_run(db_session).id == july_paid.id
