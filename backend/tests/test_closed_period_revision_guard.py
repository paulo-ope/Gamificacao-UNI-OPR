"""Regression tests: revisão de período encerrado (setembro/2026, recalculado 3x sem rastro).

Cobre `ensure_revision_allowed`, `record_revision_comparison`, `cancel_superseded_drafts`,
o contexto gravado em `result_summary.calculation_context` e o CPK de mês fechado não ser
ressincronizado a cada recálculo."""
import pytest
from fastapi import HTTPException

from app.models import AppSetting, CalculationRun, CollaboratorScore, CpkRegionalSnapshot, User
from app.services import calculation, cpk_health
from app.services.calculation_closure import (
    cancel_superseded_drafts,
    ensure_revision_allowed,
    is_period_closed_for_scoring,
    record_revision_comparison,
)


def _run(db, *, status="draft", month=6, year=2026, regional=None, summary=None):
    run = CalculationRun(
        reference_month=month, reference_year=year, regional=regional, point_value=0.35, status=status,
        result_summary=summary,
    )
    db.add(run)
    db.flush()
    return run


def _score(db, run, collaborator_id, *, penalty, final, payment):
    db.add(
        CollaboratorScore(
            calculation_run_id=run.id, collaborator_id=collaborator_id, service_orders_count=1,
            gross_points=100, penalty_points=penalty, net_points=100 - penalty, health_multiplier=1,
            health_status="Boa", final_points=final, estimated_payment=payment,
            balance_adjustment_points=0, balance_after=0,
        )
    )
    db.flush()


@pytest.fixture()
def operator_user(db_session):
    user = User(name="Operador", email="operador@pytest.local", role="operator", active=True, password_hash="x")
    db_session.add(user)
    db_session.flush()
    return user


def test_revision_of_past_period_requires_admin(db_session, operator_user):
    with pytest.raises(HTTPException) as excinfo:
        ensure_revision_allowed(db_session, operator_user, 6, 2026, None, "Motivo suficientemente longo")
    assert excinfo.value.status_code == 403


def test_revision_of_past_period_requires_written_reason(db_session, admin_user):
    for note in (None, "", "   ", "curto"):
        with pytest.raises(HTTPException) as excinfo:
            ensure_revision_allowed(db_session, admin_user, 6, 2026, None, note)
        assert excinfo.value.status_code == 422


def test_admin_with_reason_can_revise_a_closed_period(db_session, admin_user):
    ensure_revision_allowed(db_session, admin_user, 6, 2026, None, "Garantias descobertas após o fechamento")


def test_revision_of_a_period_that_is_not_closed_stays_free(db_session, operator_user, monkeypatch):
    """Mês corrente ainda aberto: a "revisão" é só um recálculo, não exige admin nem motivo."""
    monkeypatch.setattr("app.services.calculation_closure.is_period_in_the_past", lambda month, year: False)
    ensure_revision_allowed(db_session, operator_user, 6, 2026, None, None)
    assert is_period_closed_for_scoring(db_session, 6, 2026, None) is False


def test_paid_period_is_closed_even_when_not_in_the_past(db_session, monkeypatch):
    monkeypatch.setattr("app.services.calculation_closure.is_period_in_the_past", lambda month, year: False)
    _run(db_session, status="paid")
    assert is_period_closed_for_scoring(db_session, 6, 2026, None) is True


def test_cancel_superseded_drafts_only_touches_drafts_of_the_same_period(db_session, admin_user):
    old_draft = _run(db_session)
    in_review = _run(db_session, status="review")
    paid_other_regional = _run(db_session, status="paid", regional="UNI SUL")
    other_month = _run(db_session, month=7)
    new_run = _run(db_session)

    cancelled = cancel_superseded_drafts(db_session, new_run, admin_user)

    assert cancelled == [old_draft.id]
    assert old_draft.status == "cancelled"
    assert f"#{new_run.id}" in (old_draft.status_note or "")
    assert in_review.status == "review"
    assert paid_other_regional.status == "paid"
    assert other_month.status == "draft"
    assert new_run.status == "draft"


def test_revision_comparison_records_why_the_total_moved(db_session):
    previous = _run(db_session, summary={"cards": {"warranty_service_orders": 766}})
    _score(db_session, previous, 1, penalty=20386, final=62706.6, payment=20577.83)
    new_run = _run(db_session, summary={"cards": {"warranty_service_orders": 839}, "calculation_context": {"timezone": "America/Porto_Velho"}})
    _score(db_session, new_run, 1, penalty=21014, final=61767.8, payment=20259.19)

    comparison = record_revision_comparison(db_session, new_run)

    assert comparison["run_id"] == previous.id
    assert comparison["estimated_payment_delta"] == pytest.approx(-318.64)
    assert comparison["penalty_points_delta"] == pytest.approx(628.0)
    assert comparison["warranty_service_orders_delta"] == 73
    stored = new_run.result_summary["calculation_context"]
    assert stored["compared_to"]["run_id"] == previous.id
    assert stored["timezone"] == "America/Porto_Velho"


def test_revision_comparison_prefers_paid_run_over_newer_draft(db_session):
    paid = _run(db_session, status="paid")
    _score(db_session, paid, 1, penalty=10, final=90, payment=100)
    _run(db_session)  # rascunho mais novo, não deve ser a referência
    new_run = _run(db_session)
    _score(db_session, new_run, 1, penalty=20, final=80, payment=90)

    comparison = record_revision_comparison(db_session, new_run)

    assert comparison["run_id"] == paid.id
    assert comparison["estimated_payment_delta"] == pytest.approx(-10.0)


def test_revision_comparison_is_none_without_a_previous_run(db_session):
    only = _run(db_session)
    assert record_revision_comparison(db_session, only) is None


def test_closed_cpk_month_is_not_resynced_on_recalculation(db_session, monkeypatch):
    db_session.add(AppSetting(key=cpk_health.CPK_SYNC_ENABLED_SETTING, value="true"))
    db_session.add(CpkRegionalSnapshot(reference_year=2026, reference_month=9, regional="UNI - JARU", status="na_meta", mes_fechado=True))
    db_session.flush()
    called = []
    monkeypatch.setattr(cpk_health, "sync_cpk_snapshot", lambda db, ano, mes: called.append((ano, mes)))

    calculation._apply_cpk_adjustment(db_session, {}, 9, 2026)

    assert called == []


def test_open_cpk_month_is_still_synced(db_session, monkeypatch):
    db_session.add(AppSetting(key=cpk_health.CPK_SYNC_ENABLED_SETTING, value="true"))
    db_session.add(CpkRegionalSnapshot(reference_year=2026, reference_month=9, regional="UNI - JARU", status="na_meta", mes_fechado=False))
    db_session.flush()
    called = []
    monkeypatch.setattr(cpk_health, "sync_cpk_snapshot", lambda db, ano, mes: called.append((ano, mes)))

    calculation._apply_cpk_adjustment(db_session, {}, 9, 2026)

    assert called == [(2026, 9)]


def test_cpk_period_final_needs_every_regional_closed(db_session):
    assert cpk_health.is_cpk_period_final(db_session, 2026, 9) is False
    db_session.add(CpkRegionalSnapshot(reference_year=2026, reference_month=9, regional="UNI - JARU", status="na_meta", mes_fechado=True))
    db_session.add(CpkRegionalSnapshot(reference_year=2026, reference_month=9, regional="UNI - JI PARANA", status="fora_meta", mes_fechado=False))
    db_session.flush()
    assert cpk_health.is_cpk_period_final(db_session, 2026, 9) is False


def test_route_rejects_revision_of_a_closed_period_without_a_reason(client):
    response = client.post(
        "/api/calculation-runs/calculate",
        json={"reference_month": 6, "reference_year": 2026, "create_revision": True},
    )
    assert response.status_code == 422
    assert "motivo" in response.json()["detail"].lower()


def test_statement_apurado_em_is_shown_in_porto_velho_time():
    from datetime import datetime, timezone

    from app.services.statement_pdf import _format_porto_velho

    # 03/10 17:32 UTC é 13:32 em Porto Velho (UTC-4, sem horário de verão).
    assert _format_porto_velho(datetime(2026, 10, 3, 17, 32, tzinfo=timezone.utc)) == "03/10/2026 13:32"
    # SQLite devolve datetime sem fuso: tratado como UTC, nunca como horário local.
    assert _format_porto_velho(datetime(2026, 10, 3, 17, 32)) == "03/10/2026 13:32"
    assert _format_porto_velho(None) == "-"
