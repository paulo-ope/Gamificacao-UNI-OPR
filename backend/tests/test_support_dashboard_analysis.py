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


def _fake_month(monkeypatch, tmr_value, tmr_count):
    metrics = {
        "average_tmr_effective_seconds": tmr_value, "tmr_effective_coverage": {"count": tmr_count},
        "average_tma_effective_seconds": None, "tma_effective_coverage": {"count": 0},
    }
    monkeypatch.setattr(dashboard_analysis.opa_overview_service, "overview_metrics", lambda db, filters: metrics)


def test_month_projection_gives_what_the_rest_of_the_month_must_close_at(db_session, monkeypatch):
    # 24 dias com 400 atendimentos medidos e TMR de 130 s; meta 120 s; restam 7 dias (~116,7 atendimentos).
    _fake_month(monkeypatch, 130.0, 400)

    result = dashboard_analysis.month_projection(db_session, FILTERS, date(2026, 10, 24), {"tmr": 120.0, "tma": 3600.0})

    assert (result["month_from"], result["month_to"], result["elapsed_days"], result["remaining_days"]) == (date(2026, 10, 1), date(2026, 10, 31), 24, 7)
    assert result["remaining_from"] == date(2026, 10, 25)
    tmr = next(item for item in result["items"] if item["key"] == "tmr")
    assert tmr["status"] == "reachable" and tmr["required_value"] == 85.7  # (120*516,67 - 130*400) / 116,67
    assert next(item for item in result["items"] if item["key"] == "tma")["status"] == "no_data"


def test_month_projection_is_unreachable_when_the_month_is_already_too_far(db_session, monkeypatch):
    _fake_month(monkeypatch, 180.0, 400)

    result = dashboard_analysis.month_projection(db_session, FILTERS, date(2026, 10, 24), {"tmr": 120.0, "tma": 3600.0})

    tmr = next(item for item in result["items"] if item["key"] == "tmr")
    assert tmr["status"] == "unreachable" and tmr["required_value"] is None


def test_month_projection_closed_month_has_no_remaining_days(db_session, monkeypatch):
    _fake_month(monkeypatch, 110.0, 500)

    result = dashboard_analysis.month_projection(db_session, FILTERS, date(2026, 10, 31), {"tmr": 120.0, "tma": 3600.0})

    assert result["remaining_days"] == 0 and result["remaining_from"] is None
    assert next(item for item in result["items"] if item["key"] == "tmr")["status"] == "closed"
