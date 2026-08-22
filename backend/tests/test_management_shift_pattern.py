"""Escala alternada (12x36 etc.) por colaborador - achado real 2026-08-20: a geração automática
de caso diário tratava o dia de folga de equipes 12x36 como "produção zero num dia esperado",
abrindo caso indevido. `is_scheduled_workday` e sua integração em `generate_daily_cases_for_date`
corrigem isso."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.modules.management import cases as cases_engine
from app.modules.management import services as management_services
from app.modules.management.models import ManagementCase, ManagementOperationalMember
from app.modules.operations.models import OperationOrder, OperationTeamModel

MONDAY = date(2026, 7, 6)  # verificado: date(2026, 7, 6).weekday() == 0
TODAY = date(2026, 8, 21)  # "hoje" fixo usado pelos testes de suggest_shift_pattern


def _order(responsible: str, day: date, index: int = 0) -> OperationOrder:
    closed = datetime(day.year, day.month, day.day, 15, 0, tzinfo=timezone.utc)
    return OperationOrder(
        source="ixc",
        source_order_id=f"OS-{responsible}-{day.isoformat()}-{index}",
        order_code=f"OS-{responsible}-{day.isoformat()}-{index}",
        regional="UNI JARU",
        os_type="Suporte",
        os_subject="Fibra",
        responsible=responsible,
        opened_at=closed,
        closed_at=closed,
        is_closed=True,
        raw_payload={},
    )


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


def test_update_member_endpoint_accepts_shift_pattern_fields_for_a_12x36_member(client, db_session):
    """Achado real da auditoria de 2026-08-21: escala alternada só pode ser ligada em quem é do
    modelo de equipe 12x36 - este teste já cadastra o membro nesse modelo antes do PATCH."""
    model = OperationTeamModel(name="TECNICO 12/36H", daily_target=7, median_from_quantity=5, good_from_quantity=6, active=True)
    db_session.add(model)
    db_session.flush()
    member = _member(team_model_id=model.id)
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
    model = OperationTeamModel(name="TECNICO 12/36H", daily_target=7, active=True)
    db_session.add(model)
    db_session.flush()
    member = _member(team_model_id=model.id)
    db_session.add(member)
    db_session.commit()

    response = client.patch(f"/api/management/members/{member.id}", json={"shift_pattern": "nao-existe"})

    assert response.status_code == 422


def test_update_member_endpoint_rejects_alternating_without_a_12x36_team_model(client, db_session):
    """Membro sem modelo de equipe nenhum - não pode ligar escala alternada."""
    member = _member()
    db_session.add(member)
    db_session.commit()

    response = client.patch(f"/api/management/members/{member.id}", json={"shift_pattern": "alternating"})

    assert response.status_code == 422


def test_update_member_endpoint_rejects_alternating_for_a_non_12x36_team_model(client, db_session):
    model = OperationTeamModel(name="SUPORTE MOTO", daily_target=7, active=True)
    db_session.add(model)
    db_session.flush()
    member = _member(team_model_id=model.id)
    db_session.add(member)
    db_session.commit()

    response = client.patch(f"/api/management/members/{member.id}", json={"shift_pattern": "alternating"})

    assert response.status_code == 422


def test_update_member_endpoint_allows_setting_team_model_and_shift_pattern_together(client, db_session):
    """Membro ainda sem modelo de equipe - troca pra 12x36 e liga a escala alternada na MESMA
    chamada (o efetivo pós-update precisa ser validado, não o estado antes do PATCH)."""
    model = OperationTeamModel(name="TECNICO 12/36H", daily_target=7, active=True)
    db_session.add(model)
    db_session.flush()
    member = _member()
    db_session.add(member)
    db_session.commit()

    response = client.patch(
        f"/api/management/members/{member.id}",
        json={"team_model_id": model.id, "shift_pattern": "alternating", "shift_cycle_days_on": 1, "shift_cycle_days_off": 1, "shift_anchor_date": MONDAY.isoformat()},
    )

    assert response.status_code == 200
    db_session.refresh(member)
    assert member.team_model_id == model.id
    assert member.shift_pattern == "alternating"


def test_update_member_endpoint_rejects_switching_team_model_away_while_alternating_stays_set(client, db_session):
    """Membro já 12x36 com escala alternada ligada - trocar o modelo de equipe pra outro SEM
    também voltar shift_pattern pra "standard" na mesma chamada é rejeitado (senão o colaborador
    ficaria com "alternating" travado num modelo que não é mais 12x36)."""
    model_12x36 = OperationTeamModel(name="TECNICO 12/36H", daily_target=7, active=True)
    other_model = OperationTeamModel(name="SUPORTE MOTO", daily_target=7, active=True)
    db_session.add_all([model_12x36, other_model])
    db_session.flush()
    member = _member(team_model_id=model_12x36.id, shift_pattern="alternating", shift_cycle_days_on=1, shift_cycle_days_off=1, shift_anchor_date=MONDAY)
    db_session.add(member)
    db_session.commit()

    response = client.patch(f"/api/management/members/{member.id}", json={"team_model_id": other_model.id})

    assert response.status_code == 422


def test_validate_shift_pattern_for_team_model_helper():
    model = OperationTeamModel(name="TECNICO 12/36H")
    other = OperationTeamModel(name="SUPORTE MOTO")
    management_services.validate_shift_pattern_for_team_model("standard", None)
    management_services.validate_shift_pattern_for_team_model("alternating", model)
    with pytest.raises(management_services.ShiftPatternNotEligibleError):
        management_services.validate_shift_pattern_for_team_model("alternating", other)
    with pytest.raises(management_services.ShiftPatternNotEligibleError):
        management_services.validate_shift_pattern_for_team_model("alternating", None)


# --- suggest_shift_pattern ------------------------------------------------------------------------
# Pedido do usuário em 2026-08-21: "sistema sugere, supervisor confirma" - a função só analisa
# produção real e devolve uma sugestão, nunca grava nada.


def test_suggest_shift_pattern_detects_a_clean_1x1_cycle(db_session):
    member = _member(responsible_name="Cleison Alternado")
    db_session.add(member)
    # Últimos 21 dias (até TODAY), trabalhando em dias pares a partir do início da janela.
    window_start = TODAY - timedelta(days=cases_engine.SHIFT_SUGGESTION_WINDOW_DAYS - 1)
    for offset in range(cases_engine.SHIFT_SUGGESTION_WINDOW_DAYS):
        if offset % 2 == 0:
            db_session.add(_order(member.responsible_name, window_start + timedelta(days=offset)))
    db_session.commit()

    suggestion = cases_engine.suggest_shift_pattern(db_session, member, today=TODAY)

    assert suggestion.suggested_pattern == "alternating"
    assert suggestion.suggested_cycle_days_on == 1
    assert suggestion.suggested_cycle_days_off == 1
    assert suggestion.suggested_anchor_date == window_start
    assert suggestion.confidence == 1.0
    assert len(suggestion.daily_production) == cases_engine.SHIFT_SUGGESTION_WINDOW_DAYS


def test_suggest_shift_pattern_flags_a_long_production_gap_as_inconclusive(db_session):
    """Achado real da auditoria de 2026-08-21 (Diolvane/Thalison): um buraco grande de produção
    não pode virar sugestão de folga - tem que virar aviso de possível afastamento."""
    member = _member(responsible_name="Diolvane Ausente")
    db_session.add(member)
    window_start = TODAY - timedelta(days=cases_engine.SHIFT_SUGGESTION_WINDOW_DAYS - 1)
    # Produz normalmente na primeira semana, depois some até hoje.
    for offset in range(7):
        db_session.add(_order(member.responsible_name, window_start + timedelta(days=offset)))
    db_session.commit()

    suggestion = cases_engine.suggest_shift_pattern(db_session, member, today=TODAY)

    assert suggestion.suggested_pattern == "inconclusive"
    assert suggestion.suggested_anchor_date is None
    assert suggestion.confidence == 0.0
    assert "afastamento" in suggestion.message.lower()


def test_suggest_shift_pattern_flags_an_irregular_history_as_inconclusive(db_session):
    member = _member(responsible_name="Wender Irregular")
    db_session.add(member)
    window_start = TODAY - timedelta(days=cases_engine.SHIFT_SUGGESTION_WINDOW_DAYS - 1)
    # Trabalha 3 dias seguidos, folga 1, trabalha 2, folga 2... nunca alterna limpo em 1x1.
    pattern = [True, True, True, False, True, True, False, False]
    for offset in range(cases_engine.SHIFT_SUGGESTION_WINDOW_DAYS):
        if pattern[offset % len(pattern)]:
            db_session.add(_order(member.responsible_name, window_start + timedelta(days=offset)))
    db_session.commit()

    suggestion = cases_engine.suggest_shift_pattern(db_session, member, today=TODAY)

    assert suggestion.suggested_pattern == "inconclusive"
    assert suggestion.confidence < cases_engine.SHIFT_SUGGESTION_MIN_MATCH_RATIO


def test_suggest_shift_pattern_endpoint_returns_the_suggestion(client, db_session):
    # O endpoint usa `date.today()` real (sem parâmetro) - a janela aqui é montada a partir do
    # relógio real do teste também, pra não precisar mockar nada nem depender de uma data fixa.
    today = date.today()
    model = OperationTeamModel(name="TECNICO 12/36H", daily_target=7, active=True)
    db_session.add(model)
    db_session.flush()
    member = _member(responsible_name="Pablo Alternado", team_model_id=model.id)
    db_session.add(member)
    window_start = today - timedelta(days=cases_engine.SHIFT_SUGGESTION_WINDOW_DAYS - 1)
    for offset in range(cases_engine.SHIFT_SUGGESTION_WINDOW_DAYS):
        if offset % 2 == 0:
            db_session.add(_order(member.responsible_name, window_start + timedelta(days=offset)))
    db_session.commit()

    response = client.get(f"/api/management/members/{member.id}/shift-pattern-suggestion")

    assert response.status_code == 200
    body = response.json()
    assert body["suggested_pattern"] in {"alternating", "inconclusive"}
    assert len(body["daily_production"]) == cases_engine.SHIFT_SUGGESTION_WINDOW_DAYS


def test_suggest_shift_pattern_endpoint_404s_for_an_unknown_member(client, db_session):
    response = client.get("/api/management/members/999999/shift-pattern-suggestion")
    assert response.status_code == 404
