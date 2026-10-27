from __future__ import annotations

from datetime import date, datetime, timezone

from app.modules.support import dashboard_analysis
from app.modules.support.models import SupportOpaAttendance
from app.modules.support.opa_filters import OpaAttendanceFilters

FILTERS = OpaAttendanceFilters(date_from=date(2026, 10, 1), date_to=date(2026, 10, 7))


def _attendance(db, source_id, day, reason):
    db.add(
        SupportOpaAttendance(
            source_id=source_id, attendant_id="a1", channel="whatsapp", reason_name=reason, status="F", reached_human=True,
            opened_at=datetime(2026, 10, day, 15, tzinfo=timezone.utc), closed_at=datetime(2026, 10, day, 16, tzinfo=timezone.utc),
        )
    )


def _seed_flat_week(db, per_day=2):
    for day in range(1, 8):
        for index in range(per_day):
            _attendance(db, f"F{day}-{index}", day, "Lentidão")


def test_peak_day_points_at_the_spike_and_its_reasons(db_session):
    _seed_flat_week(db_session)
    for index in range(6):
        _attendance(db_session, f"P{index}", 4, "Sem conexão")
    db_session.commit()

    result = dashboard_analysis.peak_day(db_session, FILTERS)

    assert result is not None and result["day"] == date(2026, 10, 4)
    assert result["total"] == 8 and result["average"] == 2.0 and result["percent_above"] == 300.0
    assert result["reasons"][0] == {"reason": "Sem conexão", "count": 6, "usual_per_day": 0.0}
    assert result["reasons"][1]["reason"] == "Lentidão" and result["reasons"][1]["usual_per_day"] == 2.0


def test_peak_day_is_none_without_a_real_increase(db_session):
    _seed_flat_week(db_session)
    db_session.commit()

    assert dashboard_analysis.peak_day(db_session, FILTERS) is None


def test_peak_day_labels_missing_reason(db_session):
    _seed_flat_week(db_session)
    for index in range(5):
        _attendance(db_session, f"N{index}", 5, None)
    db_session.commit()

    result = dashboard_analysis.peak_day(db_session, FILTERS)

    assert result is not None and result["reasons"][0]["reason"] == dashboard_analysis.NO_REASON_LABEL


OPA = {
    "total_attendances": 0, "average_tmr_effective_seconds": None, "tmr_effective_coverage": {"count": 0},
    "average_tma_effective_seconds": None, "tma_effective_coverage": {"count": 0}, "average_rating": None,
}
IXC = {"performed": 0, "field": 0, "solved": 0, "resolutivity": None}
TARGETS = {"tmr": 120.0, "tma": 3600.0, "csat": 4.5, "resolutivity": 80.0}


def _project(db, monkeypatch, *, month, period, date_to=date(2026, 10, 24), period_days=7, month_ixc=IXC, period_ixc=IXC, rated=(0, 0)):
    monkeypatch.setattr(dashboard_analysis.opa_overview_service, "overview_metrics", lambda db_, filters: {**OPA, **month})
    counts = iter(rated)
    monkeypatch.setattr(dashboard_analysis, "_rated_count", lambda db_, filters: next(counts))
    result = dashboard_analysis.month_projection(
        db, FILTERS, date_to=date_to, period_days=period_days, targets=TARGETS, current_opa={**OPA, **period},
        current_ixc=period_ixc, month_ixc=month_ixc,
    )
    return {item["key"]: item for item in result["items"]}


def test_month_projection_gives_what_the_rest_of_the_month_must_close_at(db_session, monkeypatch):
    # 24 dias: 400 atendimentos com TMR de 130 s; a semana selecionada fechou em 150 s com 120 atendimentos.
    month = {"average_tmr_effective_seconds": 130.0, "tmr_effective_coverage": {"count": 400}}
    period = {"average_tmr_effective_seconds": 150.0, "tmr_effective_coverage": {"count": 120}}

    items = _project(db_session, monkeypatch, month=month, period=period)

    tmr = items["tmr"]
    # Resto do mês: 120 / 7 x 7 = 120 atendimentos esperados -> (120 x 520 - 130 x 400) / 120 = 86,67.
    assert tmr["status"] == "reachable" and tmr["required_value"] == round(10400 / 120, 4)
    assert tmr["pace_value"] == round((130 * 400 + 150 * 120) / 520, 4) and tmr["pace_meets_target"] is False
    assert items["tma"]["status"] == "no_data"


def test_month_projection_is_unreachable_when_the_month_is_already_too_far(db_session, monkeypatch):
    month = {"average_tmr_effective_seconds": 180.0, "tmr_effective_coverage": {"count": 400}}
    period = {"average_tmr_effective_seconds": 150.0, "tmr_effective_coverage": {"count": 120}}

    tmr = _project(db_session, monkeypatch, month=month, period=period)["tmr"]

    assert tmr["status"] == "unreachable" and tmr["required_value"] is None


def test_month_projection_closed_month_has_no_remaining_days(db_session, monkeypatch):
    month = {"average_tmr_effective_seconds": 110.0, "tmr_effective_coverage": {"count": 500}}

    items = _project(db_session, monkeypatch, month=month, period={}, date_to=date(2026, 10, 31))

    assert items["tmr"]["status"] == "closed" and items["tmr"]["pace_meets_target"] is True and items["tmr"]["pace_value"] == 110.0


def test_month_projection_volume_follows_the_period_pace(db_session, monkeypatch):
    # 2.400 atendimentos até o dia 24; a semana selecionada teve 700 (100 por dia); faltam 7 dias -> 2.400 + 700.
    items = _project(db_session, monkeypatch, month={"total_attendances": 2400}, period={"total_attendances": 700})

    assert items["opa_total"]["pace_value"] == 3100.0 and items["opa_total"]["status"] == "no_target"


def test_month_projection_csat_is_unreachable_above_the_scale(db_session, monkeypatch):
    # Média do mês 4,0 em 1.000 avaliações; para chegar a 4,5 o resto (250 avaliações) precisaria passar de 5.
    items = _project(db_session, monkeypatch, month={"average_rating": 4.0}, period={"average_rating": 4.2}, rated=(1000, 250))

    assert items["csat"]["status"] == "unreachable"


def test_month_projection_resolutivity_uses_performed_as_weight(db_session, monkeypatch):
    month_ixc = {"performed": 1000, "field": 300, "solved": 700, "resolutivity": 70.0}
    period_ixc = {"performed": 300, "field": 90, "solved": 210, "resolutivity": 70.0}

    resolutivity = _project(db_session, monkeypatch, month={}, period={}, month_ixc=month_ixc, period_ixc=period_ixc)["resolutivity"]

    # Para fechar em 80 % o resto precisaria de mais de 100 %: não dá.
    assert resolutivity["status"] == "unreachable" and resolutivity["pace_value"] == 70.0


def test_weeks_opa_leaves_future_weeks_empty(db_session, monkeypatch):
    monkeypatch.setattr(dashboard_analysis.opa_overview_service, "overview_metrics", lambda db_, filters: {**OPA, "total_attendances": 7})
    buckets = [
        {"key": "previous_last_week", "label": "Última semana", "from": date(2026, 9, 27), "to": date(2026, 9, 30)},
        {"key": "week_1", "label": "1ª semana", "from": date(2026, 10, 1), "to": date(2026, 10, 3)},
        {"key": "week_2", "label": "2ª semana", "from": date(2026, 10, 4), "to": date(2026, 10, 10)},
        {"key": "week_3", "label": "3ª semana", "from": date(2026, 10, 11), "to": date(2026, 10, 17)},
        {"key": "week_4", "label": "4ª semana", "from": date(2026, 10, 18), "to": date(2026, 10, 24)},
        {"key": "month", "label": "Mensal", "from": date(2026, 10, 1), "to": date(2026, 10, 31)},
    ]

    weeks = dashboard_analysis.weeks_opa(db_session, FILTERS, buckets, date(2026, 10, 14))

    assert [week["key"] for week in weeks] == ["week_1", "week_2", "week_3", "week_4"]
    assert [(week["future"], week["partial"]) for week in weeks] == [(False, False), (False, False), (False, True), (True, False)]
    assert weeks[0]["total"] == 7 and weeks[3]["total"] is None
