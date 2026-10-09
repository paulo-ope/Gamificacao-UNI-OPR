"""Radar de incidente da TV: só protocolos operacionais (assunto 90), só de hoje, contra o MESMO dia da
semana. Cobre o que errava antes: contar financeiro, comparar com sábado, média puxada por lacuna de
importação e cidade pequena virando alarme."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from app.modules.support import ixc_operational_radar as radar
from app.modules.support.models import SupportIxcTicket

# 18:00 UTC = 14:00 em America/Porto_Velho (UTC-4), quinta-feira 08/10/2026.
NOW = datetime(2026, 10, 8, 18, 0, tzinfo=timezone.utc)
TODAY = date(2026, 10, 8)
THURSDAYS_BEFORE = [TODAY - timedelta(weeks=week) for week in range(1, 5)]  # 01/10, 24/09, 17/09, 10/09
_counter = 0


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    # O IXC grava a hora local de Porto Velho com a etiqueta UTC: o `created_at` já É a hora de parede.
    return datetime.combine(day, time(hour, minute), tzinfo=timezone.utc)


def _add(db_session, day: date, hour: int, city: str = "Vale do Paraíso", subject: str = "90", count: int = 1, minute: int = 0):
    global _counter
    for _ in range(count):
        _counter += 1
        db_session.add(
            SupportIxcTicket(source_id=f"T{_counter}", subject_id=subject, city=city, created_at=_at(day, hour, minute), raw_payload={})
        )
    db_session.flush()


def _history(db_session, per_day: int, city: str = "Vale do Paraíso", hour: int = 9):
    for day in THURSDAYS_BEFORE:
        _add(db_session, day, hour, city=city, count=per_day)


def test_only_operational_protocols_are_counted_financial_is_ignored(db_session):
    _history(db_session, 2)
    _add(db_session, TODAY, 9, count=6)  # operacional
    _add(db_session, TODAY, 9, subject="29", count=10)  # financeiro: não é incidente

    result = radar.build_radar(db_session, NOW)

    assert result["pace"]["observed_today"] == 6


def test_city_is_flagged_when_far_above_the_same_weekday_average(db_session):
    _history(db_session, 2)
    _add(db_session, TODAY, 9, count=8)

    cities = radar.build_radar(db_session, NOW)["cities_at_risk"]

    assert cities == [{"city": "Vale do Paraíso", "today_count": 8, "expected": 2.0, "deviation_pct": 300.0}]


def test_small_city_never_becomes_an_alarm_even_with_zero_history(db_session):
    _history(db_session, 1, city="Outra Cidade")  # dá histórico ao dia, mas não à cidade pequena
    _add(db_session, TODAY, 9, city="Parecis", count=3)  # abaixo do piso de 5

    assert radar.build_radar(db_session, NOW)["cities_at_risk"] == []


def test_city_within_the_normal_range_is_not_flagged(db_session):
    _history(db_session, 6)
    _add(db_session, TODAY, 9, count=7)  # +17%: dentro do normal

    assert radar.build_radar(db_session, NOW)["cities_at_risk"] == []


def test_expected_uses_only_the_same_weekday_so_a_busy_saturday_does_not_matter(db_session):
    _history(db_session, 2)
    _add(db_session, date(2026, 10, 3), 9, count=50)  # sábado cheio: não entra na referência
    _add(db_session, date(2026, 10, 4), 9, count=0)
    _add(db_session, TODAY, 9, count=3)

    result = radar.build_radar(db_session, NOW)

    assert result["pace"]["expected_so_far"] == 2.0


def test_import_gap_week_is_excluded_not_averaged_as_zero(db_session):
    for day in THURSDAYS_BEFORE[:3]:
        _add(db_session, day, 9, count=3)
    # 10/09 (a 4ª quinta) sem NENHUM protocolo operacional no dia inteiro: lacuna de importação.
    _add(db_session, TODAY, 9, count=3)

    result = radar.build_radar(db_session, NOW)

    assert result["baseline_weeks_used"] == 3
    assert result["pace"]["expected_so_far"] == 3.0  # e não (3+3+3+0)/4 = 2,25


def test_without_any_history_the_radar_says_so_instead_of_inventing_a_baseline(db_session):
    _add(db_session, TODAY, 9, count=9)

    result = radar.build_radar(db_session, NOW)

    assert result["baseline_weeks_used"] == 0
    assert result["pace"]["status"] == "no_baseline" and result["pace"]["expected_so_far"] is None
    assert result["cities_at_risk"] == []
    assert all(burst["basis"] == "none" and burst["active"] is False for burst in result["bursts"])


def test_history_only_counts_up_to_the_same_time_of_day(db_session):
    _history(db_session, 2, hour=9)
    for day in THURSDAYS_BEFORE:
        _add(db_session, day, 20, count=30)  # à noite: depois de "agora" (14h), não entra no esperado até agora

    result = radar.build_radar(db_session, NOW)

    assert result["pace"]["expected_so_far"] == 2.0


def test_created_at_is_read_as_local_wall_clock_without_a_second_timezone_shift(db_session):
    _history(db_session, 2)
    # created_at = 02:00 etiquetado UTC = 02:00 de parede em Porto Velho, ainda HOJE. Converter de novo
    # (UTC-4) jogaria este protocolo para ontem às 22:00 - o erro que fazia o radar ver "0 na última hora".
    db_session.add(SupportIxcTicket(source_id="WALL1", subject_id="90", city="Vale do Paraíso", created_at=datetime(2026, 10, 8, 2, 0, tzinfo=timezone.utc), raw_payload={}))
    db_session.flush()

    assert radar.build_radar(db_session, NOW)["pace"]["observed_today"] == 1


def test_a_protocol_created_a_few_minutes_ago_counts_in_the_last_hour(db_session):
    for day in THURSDAYS_BEFORE:
        _add(db_session, day, 13, count=1, minute=40)
    _add(db_session, TODAY, 13, count=6, minute=40)  # 13:40 de parede; agora = 14:00 de parede

    burst_1h = next(b for b in radar.build_radar(db_session, NOW)["bursts"] if b["window"] == "1h")

    assert burst_1h["observed"] == 6


def test_pace_turns_critical_when_today_doubles_the_expected(db_session):
    _history(db_session, 10)
    _add(db_session, TODAY, 9, count=20)

    pace = radar.build_radar(db_session, NOW)["pace"]

    assert pace["status"] == "critical" and pace["ratio"] == 2.0


def test_pace_stays_normal_for_a_small_difference(db_session):
    _history(db_session, 10)
    _add(db_session, TODAY, 9, count=11)

    assert radar.build_radar(db_session, NOW)["pace"]["status"] == "normal"


def test_burst_is_active_only_when_the_last_hour_is_far_above_the_same_hour_before(db_session):
    for day in THURSDAYS_BEFORE:
        _add(db_session, day, 13, count=1, minute=30)  # 13:30 locais: 1 por quinta
    _add(db_session, TODAY, 13, count=8, minute=30)  # 8 na última hora

    bursts = {burst["window"]: burst for burst in radar.build_radar(db_session, NOW)["bursts"]}

    assert bursts["1h"]["active"] is True and bursts["1h"]["observed"] == 8 and bursts["1h"]["expected"] == 1.0
    assert bursts["1h"]["basis"] == "same_weekday"


def test_burst_not_active_for_normal_volume(db_session):
    for day in THURSDAYS_BEFORE:
        _add(db_session, day, 13, count=4, minute=30)
    _add(db_session, TODAY, 13, count=5, minute=30)

    assert not any(burst["active"] for burst in radar.build_radar(db_session, NOW)["bursts"])


def test_burst_windows_never_reach_back_before_midnight_of_today(db_session):
    early_now = datetime(2026, 10, 8, 5, 30, tzinfo=timezone.utc)  # 01:30 local: a janela de 6 h passaria da meia-noite
    for day in THURSDAYS_BEFORE:
        _add(db_session, day, 0, count=2, minute=30)
    _add(db_session, date(2026, 10, 7), 23, count=40)  # ontem à noite: não pode contar como "hoje"
    _add(db_session, TODAY, 0, count=2, minute=30)

    bursts = {burst["window"]: burst for burst in radar.build_radar(db_session, early_now)["bursts"]}

    assert bursts["6h"]["observed"] == 2
