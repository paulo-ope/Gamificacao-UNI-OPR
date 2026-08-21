"""Escala alternada (12x36 etc.) por colaborador - achado real 2026-08-20: a geração automática
de caso diário tratava o dia de folga de equipes 12x36 como "produção zero num dia esperado",
abrindo caso indevido. `is_scheduled_workday` e sua integração em `generate_daily_cases_for_date`
corrigem isso."""
from __future__ import annotations

from datetime import date, timedelta

from app.modules.management import cases as cases_engine
from app.modules.management.models import ManagementCase, ManagementOperationalMember
from app.modules.operations.models import OperationTeamModel

MONDAY = date(2026, 7, 6)  # verificado: date(2026, 7, 6).weekday() == 0


def _member(**overrides) -> ManagementOperationalMember:
    defaults = dict(responsible_name="Tecnico 12x36", regional="UNI JARU", is_active=True, status="validated_operation")
    defaults.update(overrides)
    return ManagementOperationalMember(**defaults)


# --- is_scheduled_workday (pura, sem banco) -----------------------------------------------------


def test_standard_pattern_is_always_a_workday():
    member = _member(shift_pattern="standard")
    assert cases_engine.is_scheduled_workday(member, MONDAY) is True
    assert cases_engine.is_scheduled_workday(member, MONDAY + timedelta(days=1)) is True


def test_no_pattern_configured_is_always_a_workday():
    member = _member(shift_pattern=None)
    assert cases_engine.is_scheduled_workday(member, MONDAY) is True


def test_alternating_pattern_alternates_from_the_anchor_date():
    # Ancora numa segunda-feira "de trabalho" - terça é folga, quarta é trabalho, e assim por diante.
    member = _member(shift_pattern="alternating", shift_cycle_days_on=1, shift_cycle_days_off=1, shift_anchor_date=MONDAY)

    assert cases_engine.is_scheduled_workday(member, MONDAY) is True
    assert cases_engine.is_scheduled_workday(member, MONDAY + timedelta(days=1)) is False
    assert cases_engine.is_scheduled_workday(member, MONDAY + timedelta(days=2)) is True
    assert cases_engine.is_scheduled_workday(member, MONDAY + timedelta(days=3)) is False


def test_alternating_pattern_works_for_dates_before_the_anchor():
    member = _member(shift_pattern="alternating", shift_cycle_days_on=1, shift_cycle_days_off=1, shift_anchor_date=MONDAY)

    assert cases_engine.is_scheduled_workday(member, MONDAY - timedelta(days=1)) is False
    assert cases_engine.is_scheduled_workday(member, MONDAY - timedelta(days=2)) is True


def test_alternating_pattern_with_incomplete_data_defaults_to_workday():
    member = _member(shift_pattern="alternating", shift_cycle_days_on=None, shift_cycle_days_off=None, shift_anchor_date=None)
    assert cases_engine.is_scheduled_workday(member, MONDAY) is True


def test_alternating_pattern_supports_multi_day_cycles():
    # 4x2 (4 dias trabalhando, 2 de folga) - não é só 12x36 1x1.
    member = _member(shift_pattern="alternating", shift_cycle_days_on=4, shift_cycle_days_off=2, shift_anchor_date=MONDAY)

    for offset in range(4):
        assert cases_engine.is_scheduled_workday(member, MONDAY + timedelta(days=offset)) is True
    for offset in range(4, 6):
        assert cases_engine.is_scheduled_workday(member, MONDAY + timedelta(days=offset)) is False
    assert cases_engine.is_scheduled_workday(member, MONDAY + timedelta(days=6)) is True


# --- Integração com generate_daily_cases_for_date -----------------------------------------------


def test_generate_daily_cases_skips_a_rest_day_for_an_alternating_member(db_session):
    """Terça é folga (âncora = segunda de trabalho) - zero produção nessa terça NÃO deve abrir
    caso, mesmo sendo dia de semana com meta configurada no modelo."""
    model = OperationTeamModel(name="Suporte 12x36", daily_target=5, median_from_quantity=3, good_from_quantity=4, active=True)
    db_session.add(model)
    db_session.flush()
    db_session.add(
        _member(
            team_model_id=model.id,
            shift_pattern="alternating",
            shift_cycle_days_on=1,
            shift_cycle_days_off=1,
            shift_anchor_date=MONDAY,
        )
    )
    db_session.commit()

    rest_day = MONDAY + timedelta(days=1)
    result = cases_engine.generate_daily_cases_for_date(db_session, day=rest_day)

    assert result["created_cases"] == 0
    assert result["evaluated_members"] == 0
    assert db_session.query(ManagementCase).count() == 0


def test_generate_daily_cases_still_evaluates_a_scheduled_workday_for_an_alternating_member(db_session):
    """Segunda (a própria âncora) é dia de trabalho - zero produção aí continua abrindo caso."""
    model = OperationTeamModel(name="Suporte 12x36", daily_target=5, median_from_quantity=3, good_from_quantity=4, active=True)
    db_session.add(model)
    db_session.flush()
    db_session.add(
        _member(
            team_model_id=model.id,
            shift_pattern="alternating",
            shift_cycle_days_on=1,
            shift_cycle_days_off=1,
            shift_anchor_date=MONDAY,
        )
    )
    db_session.commit()

    result = cases_engine.generate_daily_cases_for_date(db_session, day=MONDAY)

    assert result["created_cases"] == 1
    assert result["evaluated_members"] == 1
    case = db_session.query(ManagementCase).one()
    assert case.reference_date == MONDAY


# --- Endpoint de atualização (PATCH /members/{id}) ----------------------------------------------


def test_update_member_endpoint_accepts_shift_pattern_fields(client, db_session):
    member = _member()
    db_session.add(member)
    db_session.commit()

    response = client.patch(
        f"/api/management/members/{member.id}",
        json={
            "shift_pattern": "alternating",
            "shift_cycle_days_on": 1,
            "shift_cycle_days_off": 1,
            "shift_anchor_date": MONDAY.isoformat(),
        },
    )

    assert response.status_code == 200
    db_session.refresh(member)
    assert member.shift_pattern == "alternating"
    assert member.shift_cycle_days_on == 1
    assert member.shift_cycle_days_off == 1
    assert member.shift_anchor_date == MONDAY


def test_update_member_endpoint_rejects_an_unknown_shift_pattern(client, db_session):
    member = _member()
    db_session.add(member)
    db_session.commit()

    response = client.patch(f"/api/management/members/{member.id}", json={"shift_pattern": "nao-existe"})

    assert response.status_code == 422
