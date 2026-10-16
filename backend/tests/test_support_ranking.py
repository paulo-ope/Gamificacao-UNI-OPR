from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.modules.support import ranking_service
from app.modules.support.models import SupportOpaAttendance, SupportOpaDimension


@pytest.mark.parametrize(
    "value,expected",
    [(5.0, 5), (4.0, 5), (3.99, 0), (3.95, 0), (3.9, -3), (2.0, -3), (None, 0)],
)
def test_rating_points(value, expected):
    assert ranking_service.rating_points(value) == expected


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (30, 5), (60, 5), (61, 3), (120, 3), (121, 1), (180, 1),
        (181, -2), (360, -2),  # 3:01 a 6:00
        (361, -4), (540, -4),  # 6:01 a 9:00
        (541, -6), (None, 0),
    ],
)
def test_tmr_points(seconds, expected):
    assert ranking_service.tmr_points(seconds) == expected


@pytest.mark.parametrize(
    "calls,weeks_below,expected",
    [
        (0, 0, 0), (11, 0, 0), (12, 0, 20), (23, 0, 20), (24, 0, 40),
        (48, 0, 80),  # exemplo do usuário: 48 no mês = 80 pontos
        (48, 1, 70), (6, 4, -40), (30, 2, 20),
    ],
)
def test_calls_points(calls, weeks_below, expected):
    assert ranking_service.calls_points(calls, weeks_below) == expected


def test_complete_weeks_are_whole_sunday_to_saturday_inside_the_month_and_finished():
    # Outubro/2026: 01/10 é quinta; as semanas inteiras são 04-10, 11-17, 18-24 e 25-31 (4, como no exemplo de 48 = 4x12).
    full = ranking_service.complete_weeks(date(2026, 10, 1), date(2026, 10, 31), date(2026, 11, 5))
    assert full == [(date(2026, 10, 4), date(2026, 10, 10)), (date(2026, 10, 11), date(2026, 10, 17)), (date(2026, 10, 18), date(2026, 10, 24)), (date(2026, 10, 25), date(2026, 10, 31))]
    # Mês em andamento: só as que já terminaram antes de hoje.
    assert ranking_service.complete_weeks(date(2026, 10, 1), date(2026, 10, 31), date(2026, 10, 16)) == [(date(2026, 10, 4), date(2026, 10, 10))]
    # Setembro/2026 (01/09 é terça): 06-12, 13-19, 20-26; a de 27/09 a 03/10 sai do mês.
    assert len(ranking_service.complete_weeks(date(2026, 9, 1), date(2026, 9, 30), date(2026, 10, 16))) == 3


def test_month_bounds_and_listed_months():
    assert ranking_service.month_bounds(date(2026, 10, 16)) == (date(2026, 10, 1), date(2026, 10, 31))
    assert ranking_service.month_bounds(date(2026, 2, 3)) == (date(2026, 2, 1), date(2026, 2, 28))
    assert ranking_service.month_bounds(date(2026, 12, 31)) == (date(2026, 12, 1), date(2026, 12, 31))
    months = ranking_service.listed_months(date(2026, 10, 16))
    # O mês em andamento vem primeiro; a virada de ano é tratada.
    assert months[0] == {"date_from": date(2026, 10, 1), "date_to": date(2026, 10, 31)}
    assert months[1]["date_from"] == date(2026, 9, 1)
    assert ranking_service.listed_months(date(2026, 2, 10))[2]["date_from"] == date(2025, 12, 1)
    assert len(months) == ranking_service.MONTHS_LISTED


def _attendance(db, source_id, attendant, *, day, rating=None, tmr=None, channel="whatsapp"):
    db.add(
        SupportOpaAttendance(
            source_id=source_id,
            attendant_id=attendant,
            first_human_attendant_id=attendant,
            channel=channel,
            status="F",
            opened_at=datetime(2026, 10, day, 15, tzinfo=timezone.utc),
            closed_at=datetime(2026, 10, day, 16, tzinfo=timezone.utc),
            reached_human=True,
            rating=rating,
            tma_active_seconds=600,
            tmr_gap_sum_seconds=None if tmr is None else tmr,
            tmr_gap_count=None if tmr is None else 1,
            active_metrics_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
        )
    )


def test_monthly_ranking_orders_by_points_then_tie_break_and_parks_inactive(db_session):
    for source_id, name in [("a", "Maycon Batista"), ("b", "Eduardo Leite"), ("c", "Julio César"), ("d", "Kaline Vitoria")]:
        db_session.add(SupportOpaDimension(dimension_type="user", source_id=source_id, name=name))
    # Maycon: 12 ligações (+20), nota 4,5 (+5), TMR 50 s (+5) = 30.
    for n in range(12):
        _attendance(db_session, f"M{n}", "a", day=6, rating=4.5, tmr=50, channel="pabx")
    # Eduardo: mesma pontuação (30), mas TMR maior (55 s): fica atrás no desempate.
    for n in range(12):
        _attendance(db_session, f"E{n}", "b", day=6, rating=4.5, tmr=55, channel="pabx")
    # Julio: 2 ligações (-10), nota 3,5 (-3), TMR 200 s (-2) = -15.
    for n in range(2):
        _attendance(db_session, f"J{n}", "c", day=7, rating=3.5, tmr=200, channel="pabx")
    # Kaline: nada no mês -> sem atividade.
    db_session.commit()

    result = ranking_service.monthly_ranking(db_session, month=date(2026, 10, 7), reference=date(2026, 10, 16))

    assert (result["date_from"], result["date_to"]) == (date(2026, 10, 1), date(2026, 10, 31))
    by_name = {row["name"]: row for row in result["rows"]}
    assert by_name["Maycon Batista"]["total_points"] == 30 and by_name["Maycon Batista"]["position"] == 1
    assert by_name["Eduardo Leite"]["total_points"] == 30 and by_name["Eduardo Leite"]["position"] == 2
    assert by_name["Julio César"]["total_points"] == -15 and by_name["Julio César"]["position"] == 3
    assert by_name["Kaline Vitoria"]["active"] is False
    assert by_name["Kaline Vitoria"]["position"] is None and by_name["Kaline Vitoria"]["total_points"] is None
    assert result["rows"][-1]["name"] == "Kaline Vitoria"
    assert (by_name["Maycon Batista"]["calls"]["value"], by_name["Maycon Batista"]["calls"]["points"]) == (12, 20)
    assert (by_name["Julio César"]["calls"]["value"], by_name["Julio César"]["calls"]["points"]) == (2, -10)
    assert "1 bloco de 12 (+20)" in by_name["Maycon Batista"]["calls"]["detail"]
