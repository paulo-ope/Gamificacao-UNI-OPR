from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.modules.operations.login_aggregate import login_timeseries
from app.modules.operations.models import OperationLoginStatusSnapshot


def _snapshot(db_session, *, login_id: int, captured_at: datetime, online: str):
    db_session.add(
        OperationLoginStatusSnapshot(
            captured_at=captured_at,
            login_id=login_id,
            login=f"login-{login_id}",
            online=online,
        )
    )


def test_login_timeseries_first_point_flags_missing_baseline(db_session):
    """Achado real da auditoria de 2026-08-21: sem captura anterior dentro do lookback de 20min,
    o primeiro ponto conta todo login como 'nova' transição - agora isso vem sinalizado."""
    since = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)
    _snapshot(db_session, login_id=1, captured_at=since, online="N")
    _snapshot(db_session, login_id=2, captured_at=since, online="S")
    _snapshot(db_session, login_id=1, captured_at=since + timedelta(minutes=2), online="N")
    _snapshot(db_session, login_id=2, captured_at=since + timedelta(minutes=2), online="N")
    db_session.commit()

    result = login_timeseries(db_session, since=since, until=since + timedelta(minutes=5))

    assert result["data"][0]["baseline_available"] is False
    assert result["data"][0]["new_drops"] == 1  # login 1, sem "antes" pra comparar
    assert result["data"][0]["new_reconnects"] == 1  # login 2, sem "antes" pra comparar
    assert result["data"][1]["baseline_available"] is True
    assert result["data"][1]["new_drops"] == 1  # login 2 virou N (era S)
    assert result["data"][1]["new_reconnects"] == 0

    warning_codes = [w["code"] for w in result["meta"]["warnings"]]
    assert "FIRST_POINT_MAY_BE_INFLATED" in warning_codes


def test_login_timeseries_with_prior_capture_has_no_warning(db_session):
    since = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)
    _snapshot(db_session, login_id=1, captured_at=since - timedelta(minutes=10), online="S")
    _snapshot(db_session, login_id=1, captured_at=since, online="N")
    db_session.commit()

    result = login_timeseries(db_session, since=since, until=since + timedelta(minutes=1))

    assert result["data"][0]["baseline_available"] is True
    assert result["data"][0]["new_drops"] == 1
    assert result["meta"]["warnings"] == []
