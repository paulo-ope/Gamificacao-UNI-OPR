"""Testes do snapshot da TV do SGP Suporte (`opa_tv_service`).

Cobrem os casos exigidos pela norma de métricas (docs/normas-qualidade-dados-metricas.md, seção 8)
que se aplicam a este recorte: fuso local, atendimento atravessando a virada do dia, motivo
ausente, agente virtual fora do ranking humano, aberto x fechado - mais o isolamento de falha por
bloco e a meta do TMR.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.modules.support import opa_tv_service
from app.modules.support.models import SupportOpaAttendance, SupportOpaAttendantOverride, SupportOpaDimension
from app.modules.support.router import support_tv_snapshot
from app.modules.support.tv_schemas import SupportTvSnapshot
from app.services.calculation import upsert_setting

# 18:00 UTC = 14:00 em America/Porto_Velho (UTC-4). "Hoje" local é 08/10/2026 (quinta-feira).
NOW = datetime(2026, 10, 8, 18, 0, tzinfo=timezone.utc)
TODAY = date(2026, 10, 8)


def _attendance(source_id: str, opened_at: datetime, **overrides) -> SupportOpaAttendance:
    base = {
        "source_id": source_id,
        "protocol": f"UNI{source_id}",
        "customer_id": "C-1",
        "customer_name": "Cliente",
        "attendant_id": "A-1",
        "attendant_name": "Ana",
        "department_id": "D-1",
        "department_name": "Suporte",
        "reason_id": "R-1",
        "reason_name": "Sem conexão",
        "channel": "whatsapp",
        "status": "F",
        "opened_at": opened_at,
        "closed_at": opened_at + timedelta(minutes=20),
        "rating": 5.0,
        "tma_seconds": 1200,
        "tmr_seconds": 600,
        "tmr_all_responses_seconds": 100,
        "raw_payload": {},
    }
    base.update(overrides)
    return SupportOpaAttendance(**base)


def _seed_day(db_session):
    rows = [
        # Hoje (local): 08:00, 09:00 e 10:00.
        _attendance("T1", datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc), tmr_all_responses_seconds=100),
        _attendance("T2", datetime(2026, 10, 8, 13, 0, tzinfo=timezone.utc), tmr_all_responses_seconds=200),
        # Ainda aberto e sem motivo: conta em "hoje" e em "em andamento agora".
        _attendance(
            "T3",
            datetime(2026, 10, 8, 14, 0, tzinfo=timezone.utc),
            closed_at=None,
            status="A",
            reason_id=None,
            reason_name=None,
            tma_seconds=None,
            tmr_seconds=None,
            tmr_all_responses_seconds=None,
            rating=None,
        ),
        # Aberto às 23:30 locais de ONTEM e encerrado já HOJE (01:00 local): pertence a ontem
        # porque o padrão do filtro é `opened_at` - nunca ao dia do encerramento.
        _attendance(
            "Y1",
            datetime(2026, 10, 8, 3, 30, tzinfo=timezone.utc),
            closed_at=datetime(2026, 10, 8, 5, 0, tzinfo=timezone.utc),
        ),
        # Aberto há mais de 24 h e nunca encerrado: não é "em andamento agora".
        _attendance("OLD", datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc), closed_at=None, status="A"),
        # Mesmo dia da semana (quinta) da semana anterior, 08:00 local: 2 atendimentos.
        _attendance("W1", datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)),
        _attendance("W2", datetime(2026, 10, 1, 12, 30, tzinfo=timezone.utc)),
    ]
    db_session.add_all(rows)
    db_session.flush()


def test_tmr_status_respects_the_target_boundary():
    assert opa_tv_service.tmr_status(140.0, 140) == "ok"
    assert opa_tv_service.tmr_status(140.4, 140) == "above"
    assert opa_tv_service.tmr_status(None, 140) == "no_data"


def test_kpis_count_today_in_local_timezone_and_ignore_attendance_opened_yesterday(db_session):
    _seed_day(db_session)

    kpis = opa_tv_service.build_kpis(db_session, TODAY, NOW)

    assert kpis["total_today"] == 3  # T1, T2, T3 - Y1 abriu ontem no fuso local
    assert kpis["closed_today"] == 2
    assert kpis["previous_day_total"] == 1  # só Y1
    assert kpis["closure_rate"] == pytest.approx(2 / 3 * 100)


def test_open_now_counts_only_unclosed_attendance_from_the_last_24_hours(db_session):
    _seed_day(db_session)

    assert opa_tv_service.open_now(db_session, NOW) == 1  # T3; OLD tem mais de 24 h


def test_tmr_all_responses_uses_target_default_and_exposes_coverage(db_session):
    _seed_day(db_session)

    tmr = opa_tv_service.build_kpis(db_session, TODAY, NOW)["tmr_all_responses"]

    assert tmr["current_seconds"] == pytest.approx(150.0)  # média de 100 e 200; T3 sem TMR fica de fora
    assert tmr["target_seconds"] == 140
    assert tmr["status"] == "above"
    assert tmr["coverage"]["count"] == 2
    assert tmr["coverage"]["total"] == 3


def test_tmr_target_can_be_overridden_by_system_setting(db_session):
    _seed_day(db_session)
    upsert_setting(db_session, opa_tv_service.TMR_TARGET_SECONDS_KEY, "180")
    db_session.flush()

    tmr = opa_tv_service.build_kpis(db_session, TODAY, NOW)["tmr_all_responses"]

    assert tmr["target_seconds"] == 180
    assert tmr["status"] == "ok"


@pytest.mark.parametrize("raw", ["abc", "5", "99999"])
def test_invalid_tmr_target_falls_back_to_default(db_session, raw):
    upsert_setting(db_session, opa_tv_service.TMR_TARGET_SECONDS_KEY, raw)
    db_session.flush()

    assert opa_tv_service.tmr_target_seconds(db_session) == opa_tv_service.TMR_TARGET_SECONDS_DEFAULT


def test_tmr_without_data_is_none_and_never_zero(db_session):
    kpis = opa_tv_service.build_kpis(db_session, TODAY, NOW)

    assert kpis["total_today"] == 0
    assert kpis["closure_rate"] is None
    assert kpis["tmr_all_responses"]["current_seconds"] is None
    assert kpis["tmr_all_responses"]["status"] == "no_data"


def test_hourly_pace_hides_future_hours_and_ignores_weeks_without_data(db_session):
    _seed_day(db_session)

    hourly = opa_tv_service.hourly_pace(db_session, TODAY, NOW.astimezone(opa_tv_service.SUPPORT_TIMEZONE))
    points = {point["hour"]: point for point in hourly["points"]}

    assert hourly["current_hour"] == 14
    assert points[8]["today"] == 1 and points[9]["today"] == 1 and points[10]["today"] == 1
    assert points[14]["today"] == 0  # hora corrente: já chegou, sem atendimento
    assert points[15]["today"] is None  # futuro nunca vira 0
    # Só a quinta de 01/10 tem dado; as outras 3 semanas são lacuna, não "zero atendimentos".
    assert hourly["baseline_weeks_used"] == 1
    assert points[8]["baseline_average"] == pytest.approx(2.0)


def test_hourly_pace_has_no_baseline_without_history(db_session):
    db_session.add(_attendance("T1", datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)))
    db_session.flush()

    hourly = opa_tv_service.hourly_pace(db_session, TODAY, NOW.astimezone(opa_tv_service.SUPPORT_TIMEZONE))

    assert hourly["baseline_weeks_used"] == 0
    assert all(point["baseline_average"] is None for point in hourly["points"])


def test_top_attendants_excludes_virtual_agents_from_dimension_and_manual_override(db_session):
    opened = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
    rows = []
    for index in range(3):
        rows.append(_attendance(f"H{index}", opened + timedelta(minutes=index), attendant_id="A-1", attendant_name="Ana"))
    for index in range(6):
        rows.append(_attendance(f"B{index}", opened + timedelta(minutes=index), attendant_id="BOT-1", attendant_name="Theo"))
    for index in range(5):
        rows.append(_attendance(f"O{index}", opened + timedelta(minutes=index), attendant_id="A-OV", attendant_name="Agente"))
    db_session.add_all(rows)
    db_session.add(SupportOpaDimension(dimension_type="user", source_id="BOT-1", name="Theo", payload_json={"tipo": "bot"}))
    db_session.add(SupportOpaAttendantOverride(attendant_id="A-OV", classification="virtual_agent", active=True))
    db_session.flush()

    from app.modules.support.opa_filters import OpaAttendanceFilters

    ranking = opa_tv_service.top_attendants(db_session, OpaAttendanceFilters(date_from=TODAY, date_to=TODAY))

    assert [item["attendant_id"] for item in ranking] == ["A-1"]
    assert ranking[0]["name"] == "Ana"
    assert ranking[0]["total"] == 3


def test_top_attendants_never_shows_the_raw_id_as_a_name(db_session):
    db_session.add(
        _attendance("H1", datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc), attendant_id="abc123", attendant_name="abc123")
    )
    db_session.flush()

    from app.modules.support.opa_filters import OpaAttendanceFilters

    ranking = opa_tv_service.top_attendants(db_session, OpaAttendanceFilters(date_from=TODAY, date_to=TODAY))

    assert ranking[0]["name"] == "Atendente sem nome"


def test_snapshot_reports_missing_reason_as_not_informed(db_session):
    _seed_day(db_session)

    snapshot = opa_tv_service.build_snapshot(db_session, now=NOW)

    labels = {item["label"]: item["total"] for item in snapshot["top_reasons"]}
    assert labels["Sem conexão"] == 2
    assert labels["Não informado"] == 1


def test_snapshot_isolates_a_failing_block_instead_of_blanking_the_whole_tv(db_session, monkeypatch):
    _seed_day(db_session)

    def boom(*args, **kwargs):
        raise RuntimeError("baseline indisponível")

    monkeypatch.setattr(opa_tv_service.ixc_operational_radar, "build_radar", boom)

    snapshot = opa_tv_service.build_snapshot(db_session, now=NOW)

    assert "radar" in snapshot["unavailable"]
    assert snapshot["radar"]["bursts"] is None  # nunca "tudo normal"
    assert snapshot["radar"]["pace"] is None
    assert snapshot["kpis"]["total_today"] == 3  # o resto da TV continua


def test_snapshot_route_returns_payload_valid_against_the_public_schema(db_session, admin_user):
    _seed_day(db_session)

    payload = support_tv_snapshot(db=db_session, user=admin_user)

    parsed = SupportTvSnapshot.model_validate(payload)
    assert parsed.kpis is not None
    assert len(parsed.hourly.points) == 24


# --- filtro de departamento da TV ------------------------------------------------------------


def _seed_two_departments(db_session):
    opened = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
    rows = [
        _attendance("I1", opened, department_id="D-INT", department_name="Suporte Interno", attendant_id="A-INT", attendant_name="Ana"),
        _attendance("I2", opened + timedelta(minutes=5), department_id="D-INT", department_name="Suporte Interno", attendant_id="A-INT", attendant_name="Ana"),
        _attendance(
            "I3", opened + timedelta(hours=1), department_id="D-INT", department_name="Suporte Interno",
            attendant_id="A-INT", attendant_name="Ana", closed_at=None, status="A",
        ),
        _attendance("F1", opened, department_id="D-FIN", department_name="Financeiro", attendant_id="A-FIN", attendant_name="Bia"),
        _attendance(
            "F2", opened + timedelta(hours=1), department_id="D-FIN", department_name="Financeiro",
            attendant_id="A-FIN", attendant_name="Bia", closed_at=None, status="A",
        ),
    ]
    db_session.add_all(rows)
    db_session.flush()


def test_without_department_filter_the_tv_counts_every_department(db_session):
    _seed_two_departments(db_session)

    snapshot = opa_tv_service.build_snapshot(db_session, now=NOW)

    assert snapshot["kpis"]["total_today"] == 5
    assert snapshot["department_filter"] == {"department_ids": [], "department_names": []}


def test_department_filter_scopes_kpis_open_now_hourly_and_ranking(db_session):
    _seed_two_departments(db_session)
    opa_tv_service.save_tv_department_ids(db_session, ["D-INT"])
    db_session.flush()

    snapshot = opa_tv_service.build_snapshot(db_session, now=NOW)

    assert snapshot["kpis"]["total_today"] == 3
    assert snapshot["kpis"]["open_now"] == 1  # só I3; F2 é de outro departamento
    assert [item["attendant_id"] for item in snapshot["attendants"]] == ["A-INT"]
    assert sum(point["today"] or 0 for point in snapshot["hourly"]["points"]) == 3
    assert snapshot["department_filter"] == {"department_ids": ["D-INT"], "department_names": ["Suporte Interno"]}


def test_department_filter_also_scopes_the_previous_day_comparison(db_session):
    yesterday = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)
    db_session.add_all(
        [
            _attendance("P1", yesterday, department_id="D-INT", department_name="Suporte Interno"),
            _attendance("P2", yesterday, department_id="D-FIN", department_name="Financeiro"),
            _attendance("P3", yesterday, department_id="D-FIN", department_name="Financeiro"),
        ]
    )
    db_session.flush()

    kpis = opa_tv_service.build_kpis(db_session, TODAY, NOW, ["D-INT"])

    assert kpis["previous_day_total"] == 1


def test_save_department_filter_rejects_unknown_department_and_keeps_previous_value(db_session):
    _seed_two_departments(db_session)
    opa_tv_service.save_tv_department_ids(db_session, ["D-FIN"])

    with pytest.raises(ValueError):
        opa_tv_service.save_tv_department_ids(db_session, ["D-INT", "NAO-EXISTE"])

    assert opa_tv_service.tv_department_ids(db_session) == ["D-FIN"]


def test_save_department_filter_deduplicates_and_empty_list_means_all(db_session):
    _seed_two_departments(db_session)

    assert opa_tv_service.save_tv_department_ids(db_session, ["D-INT", " D-INT ", ""]) == ["D-INT"]
    assert opa_tv_service.save_tv_department_ids(db_session, []) == []
    assert opa_tv_service.tv_department_ids(db_session) == []


def test_department_options_use_the_readable_name_and_are_sorted(db_session):
    _seed_two_departments(db_session)

    options = opa_tv_service.department_options(db_session)

    assert options == [{"id": "D-FIN", "name": "Financeiro"}, {"id": "D-INT", "name": "Suporte Interno"}]


def test_tv_config_routes_save_and_audit_the_department_filter(db_session, admin_user):
    from app.modules.support.router import support_tv_config, update_support_tv_config
    from app.modules.support.tv_schemas import SupportTvConfigUpdate

    _seed_two_departments(db_session)

    saved = update_support_tv_config(SupportTvConfigUpdate(department_ids=["D-INT"]), db=db_session, user=admin_user)

    assert saved["department_ids"] == ["D-INT"]
    assert saved["tmr_target_seconds"] == 140
    assert {option["id"] for option in saved["available_departments"]} == {"D-INT", "D-FIN"}
    assert support_tv_config(db=db_session, user=admin_user)["department_ids"] == ["D-INT"]


def test_tv_config_route_returns_422_for_unknown_department(db_session, admin_user):
    from fastapi import HTTPException

    from app.modules.support.router import update_support_tv_config
    from app.modules.support.tv_schemas import SupportTvConfigUpdate

    _seed_two_departments(db_session)

    with pytest.raises(HTTPException) as exc:
        update_support_tv_config(SupportTvConfigUpdate(department_ids=["NAO-EXISTE"]), db=db_session, user=admin_user)

    assert exc.value.status_code == 422


def test_ranking_tmr_uses_the_general_tmr_that_counts_bot_responses(db_session):
    from app.modules.support.opa_filters import OpaAttendanceFilters

    # tmr_seconds (só humano) = 600; tmr_all_responses_seconds (com bot) = 100 e 200 -> média 150.
    opened = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
    db_session.add_all(
        [
            _attendance("R1", opened, tmr_seconds=600, tmr_all_responses_seconds=100),
            _attendance("R2", opened + timedelta(minutes=5), tmr_seconds=600, tmr_all_responses_seconds=200),
        ]
    )
    db_session.flush()

    ranking = opa_tv_service.top_attendants(db_session, OpaAttendanceFilters(date_from=TODAY, date_to=TODAY))

    assert ranking[0]["average_tmr_seconds"] == pytest.approx(150.0)
    assert "average_tmr_human_seconds" not in ranking[0]


def test_ranking_tmr_is_none_and_never_zero_without_general_tmr(db_session):
    from app.modules.support.opa_filters import OpaAttendanceFilters

    db_session.add(_attendance("R3", datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc), tmr_all_responses_seconds=None))
    db_session.flush()

    ranking = opa_tv_service.top_attendants(db_session, OpaAttendanceFilters(date_from=TODAY, date_to=TODAY))

    assert ranking[0]["average_tmr_seconds"] is None
