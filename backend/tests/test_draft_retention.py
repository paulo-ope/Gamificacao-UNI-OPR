"""Regressao da auditoria financeira 2026-08-26 (achado A1): `recalculate_current_period` cria um
`CalculationRun` novo a cada ciclo do sincronizador do IXC (20 min) e nada nunca remove os
anteriores - a base chegou a 1.106 fechamentos e 225.121 linhas de `collaborator_scores`, sendo
223.811 em rascunhos descartaveis (779 so de julho/2026).

A rotina de retencao e destrutiva, entao nasce DESLIGADA: estes testes fixam que ela nao apaga
nada por padrao e que, quando ligada, nunca toca no que e registro (fechamento nao-rascunho) nem
no que o ledger de saldo referencia.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import AppSetting, CalculationRun, CollaboratorScore, PointBalanceEntry
from app.services.calculation import (
    DRAFT_RETENTION_ENABLED_SETTING,
    DRAFT_RETENTION_KEEP_SETTING,
    prune_superseded_drafts,
)

BASE = datetime(2026, 8, 1, tzinfo=timezone.utc)


@pytest.fixture()
def enable_retention(db_session):
    def _enable(keep: int = 3):
        db_session.add(AppSetting(key=DRAFT_RETENTION_ENABLED_SETTING, value="true"))
        db_session.add(AppSetting(key=DRAFT_RETENTION_KEEP_SETTING, value=str(keep)))
        db_session.flush()

    return _enable


def _run(db_session, collaborator, *, status="draft", minutes=0, month=8, year=2026):
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
            service_orders_count=1,
            final_points=100.0,
            estimated_payment=35.0,
            health_multiplier=1.0,
        )
    )
    db_session.flush()
    return run


def _existing_ids(db_session) -> set[int]:
    return {run.id for run in db_session.query(CalculationRun).all()}


def test_retention_is_disabled_by_default(db_session, make_collaborator):
    """Sem a configuracao ligada, nada e apagado - a rotina e destrutiva e quem opera decide
    quando liga-la."""
    collaborator = make_collaborator()
    old_runs = [_run(db_session, collaborator, minutes=index) for index in range(6)]
    newest = _run(db_session, collaborator, minutes=100)

    assert prune_superseded_drafts(db_session, newest) == 0
    assert _existing_ids(db_session) == {run.id for run in old_runs} | {newest.id}


def test_retention_keeps_the_newest_drafts_and_removes_the_rest(db_session, make_collaborator, enable_retention):
    enable_retention(keep=2)
    collaborator = make_collaborator()
    oldest = [_run(db_session, collaborator, minutes=index) for index in range(4)]
    newest = _run(db_session, collaborator, minutes=100)

    removed = prune_superseded_drafts(db_session, newest)

    assert removed == 2
    remaining = _existing_ids(db_session)
    assert newest.id in remaining
    # Os dois rascunhos mais recentes antes do novo continuam; os dois mais antigos saem.
    assert oldest[3].id in remaining and oldest[2].id in remaining
    assert oldest[0].id not in remaining and oldest[1].id not in remaining


def test_retention_never_removes_a_run_that_is_not_a_draft(db_session, make_collaborator, enable_retention):
    """Fechamento em conferencia, aprovado, pago ou cancelado e registro do que aconteceu -
    nunca cache descartavel."""
    enable_retention(keep=1)
    collaborator = make_collaborator()
    protected = [
        _run(db_session, collaborator, status=status, minutes=index)
        for index, status in enumerate(("review", "approved", "paid", "cancelled"))
    ]
    disposable = _run(db_session, collaborator, minutes=10)
    newest = _run(db_session, collaborator, minutes=100)

    prune_superseded_drafts(db_session, newest)

    remaining = _existing_ids(db_session)
    for run in protected:
        assert run.id in remaining
    assert disposable.id in remaining, "e o unico rascunho anterior, cabe no keep=1"


def test_retention_never_removes_a_draft_referenced_by_the_point_balance_ledger(
    db_session, make_collaborator, enable_retention
):
    """Um rascunho pode ser a origem rastreavel de um debito de garantia
    (`origin_calculation_run_id`). Apaga-lo quebraria a FK e, pior, a rastreabilidade do valor
    descontado de alguem. Na base real isso protege 9 rascunhos."""
    enable_retention(keep=1)
    collaborator = make_collaborator()
    referenced = _run(db_session, collaborator, minutes=0)
    plain = _run(db_session, collaborator, minutes=1)
    newest = _run(db_session, collaborator, minutes=100)
    db_session.add(
        PointBalanceEntry(
            collaborator_id=collaborator.id,
            entry_type="post_payment_warranty_debit",
            points=-14.0,
            status="pending",
            origin_calculation_run_id=referenced.id,
            reason="Garantia com origem neste rascunho.",
        )
    )
    db_session.flush()

    prune_superseded_drafts(db_session, newest)

    remaining = _existing_ids(db_session)
    assert referenced.id in remaining
    assert plain.id in remaining, "keep=1 preserva o rascunho anterior mais recente"


def test_retention_only_touches_the_same_period(db_session, make_collaborator, enable_retention):
    """Rascunho de outro mes nao e "substituido" por este recalculo."""
    enable_retention(keep=1)
    collaborator = make_collaborator()
    other_period = _run(db_session, collaborator, minutes=0, month=7)
    same_period = [_run(db_session, collaborator, minutes=index + 1) for index in range(3)]
    newest = _run(db_session, collaborator, minutes=100)

    prune_superseded_drafts(db_session, newest)

    remaining = _existing_ids(db_session)
    assert other_period.id in remaining
    assert same_period[2].id in remaining
    assert same_period[0].id not in remaining and same_period[1].id not in remaining


def test_retention_removes_the_scores_of_the_pruned_drafts(db_session, make_collaborator, enable_retention):
    """O ganho de verdade esta nas linhas de `collaborator_scores` - 223.811 delas hoje."""
    enable_retention(keep=1)
    collaborator = make_collaborator()
    doomed = _run(db_session, collaborator, minutes=0)
    _run(db_session, collaborator, minutes=1)
    newest = _run(db_session, collaborator, minutes=100)

    prune_superseded_drafts(db_session, newest)

    leftover = db_session.query(CollaboratorScore).filter_by(calculation_run_id=doomed.id).count()
    assert leftover == 0
