"""Comparativo semanal por regional (`GET /operations/overview/regional-weekly-comparison`)."""

from __future__ import annotations

from datetime import date, timedelta

from app.modules.operations.period import current_month_bounds
from app.modules.operations.queries import weekly_comparison_windows
from tests.test_operations_regional_matrix import _closed, _open

ENDPOINT = "/api/operations/overview/regional-weekly-comparison"


def test_windows_are_the_last_two_closed_sunday_to_saturday_weeks():
    # 25/10/2026 é domingo: a semana em curso (só hoje) fica de fora.
    assert weekly_comparison_windows(date(2026, 10, 25)) == (
        (date(2026, 10, 18), date(2026, 10, 24)),
        (date(2026, 10, 11), date(2026, 10, 17)),
    )


def test_windows_stay_the_same_until_the_next_sunday():
    expected = ((date(2026, 10, 18), date(2026, 10, 24)), (date(2026, 10, 11), date(2026, 10, 17)))
    for day in range(25, 32):  # domingo 25 até sábado 31: a semana em curso ainda não fechou
        assert weekly_comparison_windows(date(2026, 10, day)) == expected
    assert weekly_comparison_windows(date(2026, 11, 1)) == (
        (date(2026, 10, 25), date(2026, 10, 31)),
        (date(2026, 10, 18), date(2026, 10, 24)),
    )


def test_compares_each_regional_between_weeks(client, db_session):
    _, today = current_month_bounds()
    (_, current_end), (_, previous_end) = weekly_comparison_windows(today)
    today, last_week = current_end, previous_end
    db_session.add_all(
        [
            _closed("wk-now-1", today, sla_status="on_time"),
            _closed("wk-now-2", today, sla_status="on_time"),
            _closed("wk-prev-1", last_week, sla_status="out_of_time"),
            # Regional que só existe na semana anterior.
            _closed("wk-prev-only", last_week, sla_status="on_time", regional="UNI - SUL"),
            # Estoque aberto não entra no comparativo.
            _open("wk-open", today),
            _closed("wk-unidentified", today, sla_status="on_time", regional="NAO IDENTIFICADO"),
            # Regional só com estoque antigo: sem fluxo nas duas semanas, não entra.
            _open("wk-stock-only", today - timedelta(days=60), regional="UNI - LESTE"),
        ]
    )
    db_session.flush()

    response = client.get(ENDPOINT)

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_to"] == current_end.isoformat()
    assert payload["previous_to"] == previous_end.isoformat()
    north = next(item for item in payload["items"] if item["regional"] == "UNI - NORTE")
    assert north["current"]["completed"] == 2
    assert north["current"]["opened"] == 3
    assert north["current"]["sla_rate"] == 100.0
    assert north["previous"]["completed"] == 1
    assert north["previous"]["sla_rate"] == 0.0
    south = next(item for item in payload["items"] if item["regional"] == "UNI - SUL")
    assert south["current"]["completed"] == 0
    assert south["current"]["sla_rate"] is None
    assert south["previous"]["completed"] == 1
    assert all(item["regional"] not in {"UNI - LESTE", "NAO IDENTIFICADO"} for item in payload["items"])
    # O total é o do quadro geral (inclui a O.S. sem regional), para bater com o resto da tela.
    assert payload["total"]["current"]["completed"] == 3
    assert payload["total"]["previous"]["completed"] == 2
