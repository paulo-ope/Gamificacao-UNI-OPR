"""Histórico diário de backlog da Visão Geral (`GET /operations/overview/backlog-trend`).

Backlog é ESTOQUE, lido da fotografia diária (`OperationBacklogSnapshot`), não recalculado de
`OperationOrder` - por isso estes testes semeiam a própria tabela de snapshot, não O.S., e
verificam o contrato de escopo (regionais/setor recortam, modelo de equipe não existe aqui, e o
escopo regional do usuário nunca é ampliado pelo filtro).
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

from app.modules.operations.models import OperationBacklogSnapshot

ENDPOINT = "/api/operations/overview/backlog-trend"


def _snapshot(day: date, regional: str, sector: str, backlog: int, **overrides) -> OperationBacklogSnapshot:
    defaults = dict(
        snapshot_date=day,
        regional=regional,
        team_model="Não identificado",
        sector=sector,
        city="Não identificado",
        backlog_count=backlog,
        backlog_atrasado_count=0,
    )
    defaults.update(overrides)
    return OperationBacklogSnapshot(**defaults)


def test_sums_across_regionals_and_ignores_team_model(client, db_session):
    day = date(2026, 8, 20)
    db_session.add_all(
        [
            _snapshot(day, "UNI - NORTE", "Suporte Externo Fibra", 10),
            _snapshot(day, "UNI - SUL", "Suporte Externo Fibra", 7),
        ]
    )
    db_session.flush()

    response = client.get(ENDPOINT, params={"date_from": day.isoformat(), "date_to": day.isoformat()})

    assert response.status_code == 200
    payload = response.json()
    assert payload["points"] == [{"snapshot_date": day.isoformat(), "backlog": 17}]
    assert payload["coverage_from"] == day.isoformat()


def test_regionals_filter_restricts_the_sum(client, db_session):
    day = date(2026, 8, 20)
    db_session.add_all(
        [
            _snapshot(day, "UNI - NORTE", "Suporte Externo Fibra", 10),
            _snapshot(day, "UNI - SUL", "Suporte Externo Fibra", 7),
        ]
    )
    db_session.flush()

    response = client.get(
        ENDPOINT,
        params={"date_from": day.isoformat(), "date_to": day.isoformat(), "regionals": "UNI - NORTE"},
    )

    assert response.status_code == 200
    assert response.json()["points"] == [{"snapshot_date": day.isoformat(), "backlog": 10}]


def test_sectors_filter_restricts_the_sum(client, db_session):
    day = date(2026, 8, 20)
    db_session.add_all(
        [
            _snapshot(day, "UNI - NORTE", "Suporte Externo Fibra", 10),
            _snapshot(day, "UNI - NORTE", "Comercial", 4),
        ]
    )
    db_session.flush()

    response = client.get(
        ENDPOINT,
        params={"date_from": day.isoformat(), "date_to": day.isoformat(), "sectors": "Comercial"},
    )

    assert response.status_code == 200
    assert response.json()["points"] == [{"snapshot_date": day.isoformat(), "backlog": 4}]


def test_days_before_coverage_are_absent_not_zero(client, db_session):
    """Antes de `coverage_from` (o job ainda não existia) nenhum ponto é inventado - o consumidor
    decide como desenhar o buraco (a linha não deve afirmar "zero" onde nunca houve medição)."""
    day = date(2026, 8, 20)
    db_session.add(_snapshot(day, "UNI - NORTE", "Suporte Externo Fibra", 10))
    db_session.flush()

    response = client.get(
        ENDPOINT,
        params={"date_from": (day - timedelta(days=2)).isoformat(), "date_to": day.isoformat()},
    )

    assert response.status_code == 200
    assert response.json()["points"] == [{"snapshot_date": day.isoformat(), "backlog": 10}]


def test_internal_gap_carries_forward_the_last_known_value(client, db_session):
    """Um dia SEM fotografia dentro do período já coberto (job que não rodou naquela hora - achado
    real em produção: 2 dias faltando num intervalo de 26) não é a mesma situação que "antes da
    cobertura começar" - o backlog não zera nem some, carrega o último valor conhecido. Só assim a
    linha do gráfico não aparece com buracos que pareciam bug (usuário: "linha tracejada está
    falhada")."""
    day1, day2, day3 = date(2026, 8, 20), date(2026, 8, 21), date(2026, 8, 22)
    db_session.add_all(
        [
            _snapshot(day1, "UNI - NORTE", "Suporte Externo Fibra", 10),
            # day2 sem fotografia nenhuma.
            _snapshot(day3, "UNI - NORTE", "Suporte Externo Fibra", 14),
        ]
    )
    db_session.flush()

    response = client.get(ENDPOINT, params={"date_from": day1.isoformat(), "date_to": day3.isoformat()})

    assert response.status_code == 200
    assert response.json()["points"] == [
        {"snapshot_date": day1.isoformat(), "backlog": 10},
        {"snapshot_date": day2.isoformat(), "backlog": 10},
        {"snapshot_date": day3.isoformat(), "backlog": 14},
    ]


def test_internal_gap_seeds_carry_forward_from_before_the_requested_window(client, db_session):
    """O primeiro dia pedido já pode ser um buraco - a semente vem do dia anterior mais recente
    com fotografia, mesmo fora da janela solicitada."""
    seed_day, gap_day = date(2026, 8, 19), date(2026, 8, 20)
    db_session.add(_snapshot(seed_day, "UNI - NORTE", "Suporte Externo Fibra", 22))
    db_session.flush()

    response = client.get(ENDPOINT, params={"date_from": gap_day.isoformat(), "date_to": gap_day.isoformat()})

    assert response.status_code == 200
    assert response.json()["points"] == [{"snapshot_date": gap_day.isoformat(), "backlog": 22}]


def test_regional_scope_of_the_user_restricts_the_sum(client, db_session):
    from app.core.security import get_current_user
    from app.main import app

    day = date(2026, 8, 20)
    db_session.add_all(
        [
            _snapshot(day, "UNI - NORTE", "Suporte Externo Fibra", 10),
            _snapshot(day, "UNI - SUL", "Suporte Externo Fibra", 7),
        ]
    )
    db_session.flush()

    scoped_user = SimpleNamespace(
        id=905,
        role="regional_manager_viewer",
        managed_regional=None,
        managed_regionals=["UNI - NORTE"],
        access_profiles=[
            SimpleNamespace(
                active=True,
                permissions=[SimpleNamespace(permission="operations:read")],
            )
        ],
    )

    try:
        app.dependency_overrides[get_current_user] = lambda: scoped_user
        response = client.get(ENDPOINT, params={"date_from": day.isoformat(), "date_to": day.isoformat()})
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.json()["points"] == [{"snapshot_date": day.isoformat(), "backlog": 10}]
