from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.modules.operations.models import OperationOrder
from app.modules.support import dashboard_macros, ixc_new_login
from app.modules.support.models import SupportIxcTicket, SupportIxcUser, SupportOpaAttendance


@pytest.fixture(autouse=True)
def _no_live_ixc(monkeypatch):
    """O Novo Login vem do IXC ao vivo; nos testes nunca vai à rede (cada teste troca o stub se precisar)."""
    monkeypatch.setattr(ixc_new_login, "finalized_in_period", lambda date_from, date_to, **kwargs: {"finalized": 0, "by_name": {}})


@pytest.mark.parametrize(
    "value,target,direction,expected",
    [
        (4.6, 4.5, "min", "ok"),
        (4.5, 4.5, "min", "ok"),
        (4.2, 4.5, "min", "attention"),  # a 6,7% da meta
        (3.5, 4.5, "min", "critical"),
        (100.0, 120.0, "max", "ok"),
        (130.0, 120.0, "max", "attention"),  # +8,3%
        (150.0, 120.0, "max", "critical"),
        (None, 120.0, "max", "no_data"),
        (10, None, "min", "no_target"),
    ],
)
def test_metric_status(value, target, direction, expected):
    assert dashboard_macros.metric_status(value, target, direction) == expected


def _ticket(db, source_id, subject_id, opened_by, day):
    db.add(
        SupportIxcTicket(
            source_id=source_id,
            subject_id=subject_id,
            opened_by_user_id=opened_by,
            created_at=datetime(2026, 10, day, 10, tzinfo=timezone.utc),
        )
    )


def _order(db, code, creator, day):
    db.add(
        OperationOrder(
            source_order_id=code,
            order_code=code,
            creator=creator,
            opened_at=datetime(2026, 10, day, 10, tzinfo=timezone.utc),
        )
    )


def test_macro_dashboard_combines_n1_protocols_field_orders_and_opa(db_session):
    db_session.add_all(
        [
            SupportIxcUser(ixc_user_id="10", name="Ana N1", group_id="105", active=True),
            SupportIxcUser(ixc_user_id="20", name="Carla Fora", group_id="32", active=True),
        ]
    )
    # 3 protocolos N1 (2 operacionais + 1 financeiro) + 1 de outro grupo (não conta).
    _ticket(db_session, "T1", "90", "10", 5)
    _ticket(db_session, "T2", "90", "10", 6)
    _ticket(db_session, "T3", "29", "10", 7)
    _ticket(db_session, "T4", "90", "20", 7)
    # 1 O.S. do N1 (nome com caixa/espaço diferente) e 1 de quem não é N1.
    _order(db_session, "OS1", " ana n1 ", 5)
    _order(db_session, "OS2", "Carla Fora", 5)
    db_session.add(
        SupportOpaAttendance(
            source_id="A1",
            opened_at=datetime(2026, 10, 5, 15, tzinfo=timezone.utc),
            closed_at=datetime(2026, 10, 5, 16, tzinfo=timezone.utc),
            status="encerrado",
            rating=4.0,
            tma_effective_seconds=1800,
            tmr_effective_seconds=60,
            tmr_human_live_seconds=45,
        )
    )
    db_session.commit()

    result = dashboard_macros.macro_dashboard(db_session, date_from=date(2026, 10, 1), date_to=date(2026, 10, 10))
    cards = {card["key"]: card for card in result["cards"]}

    assert cards["solved"]["value"] == 3
    assert cards["field"]["value"] == 1
    assert cards["performed"]["value"] == 4
    assert cards["resolutivity"]["value"] == pytest.approx(75.0)
    assert cards["resolutivity"]["status"] == "attention"  # 75% vs meta 80% (a 6,25%)
    assert cards["performed"]["status"] == "no_target"
    assert cards["csat"]["value"] == pytest.approx(4.0)
    assert cards["csat"]["status"] == "critical"  # 4.0 vs 4.5 (11,1% abaixo)
    assert cards["tmr"]["value"] == pytest.approx(60.0) and cards["tmr"]["status"] == "ok"
    assert cards["tmr_human"]["value"] == pytest.approx(45.0) and cards["tmr_human"]["status"] == "no_target"
    assert cards["tma"]["value"] == pytest.approx(1800.0) and cards["tma"]["status"] == "ok"
    # Série diária: um ponto por dia do recorte (10) e do período anterior (10), somando os totais.
    assert len(result["daily"]) == 10 and len(result["previous_daily"]) == 10
    assert sum(point["solved"] for point in result["daily"]) == 3
    assert sum(point["field"] for point in result["daily"]) == 1
    day_five = next(point for point in result["daily"] if point["day"] == date(2026, 10, 5))
    assert (day_five["solved"], day_five["field"], day_five["performed"]) == (1, 1, 2)
    assert day_five["rating"] == pytest.approx(4.0)
    assert result["previous_date_from"] == date(2026, 9, 21)
    assert result["previous_date_to"] == date(2026, 9, 30)


def test_month_week_buckets_october_2026():
    buckets = dashboard_macros.month_week_buckets(date(2026, 10, 14))

    assert [(b["label"], b["from"], b["to"]) for b in buckets] == [
        ("Última semana", date(2026, 9, 27), date(2026, 9, 30)),
        ("1ª semana", date(2026, 10, 1), date(2026, 10, 3)),
        ("2ª semana", date(2026, 10, 4), date(2026, 10, 10)),
        ("3ª semana", date(2026, 10, 11), date(2026, 10, 17)),
        ("4ª semana", date(2026, 10, 18), date(2026, 10, 24)),
        ("5ª semana", date(2026, 10, 25), date(2026, 10, 31)),
        ("Mensal", date(2026, 10, 1), date(2026, 10, 31)),
    ]


def test_month_week_buckets_month_starting_on_sunday_and_after_saturday_end():
    # 01/11/2026 é domingo e 31/10 é sábado: a "última semana" do mês anterior é a semana cheia 25/10-31/10.
    buckets = dashboard_macros.month_week_buckets(date(2026, 11, 5))
    assert (buckets[0]["from"], buckets[0]["to"]) == (date(2026, 10, 25), date(2026, 10, 31))
    assert (buckets[1]["from"], buckets[1]["to"]) == (date(2026, 11, 1), date(2026, 11, 7))
    assert (buckets[-2]["from"], buckets[-2]["to"]) == (date(2026, 11, 29), date(2026, 11, 30))
    assert buckets[-1]["label"] == "Mensal"


def test_weekly_evolution_counts_per_week(db_session):
    db_session.add(SupportIxcUser(ixc_user_id="10", name="Ana N1", group_id="105", active=True))
    _ticket(db_session, "T1", "90", "10", 2)   # 1ª semana (01-03)
    _ticket(db_session, "T2", "29", "10", 5)   # 2ª semana (04-10)
    _ticket(db_session, "T3", "90", "10", 6)   # 2ª semana
    _order(db_session, "OS1", "Ana N1", 6)     # 2ª semana
    db_session.commit()

    weekly = dashboard_macros.weekly_evolution(db_session, date(2026, 10, 14))
    by_key = {b["key"]: b for b in weekly["buckets"]}

    assert weekly["month"] == "2026-10"
    assert (by_key["week_1"]["solved"], by_key["week_1"]["field"]) == (1, 0)
    assert (by_key["week_2"]["solved"], by_key["week_2"]["field"], by_key["week_2"]["performed"]) == (2, 1, 3)
    assert by_key["week_2"]["resolutivity"] == pytest.approx(2 / 3 * 100)
    assert by_key["week_3"]["performed"] == 0 and by_key["week_3"]["resolutivity"] is None
    assert by_key["month"]["performed"] == 4


def test_n2_collaborators_are_excluded_from_n1_protocols_and_field_orders(db_session):
    db_session.add_all(
        [
            SupportIxcUser(ixc_user_id="10", name="Ana N1", group_id="105", active=True),
            # Id da lista de excluídos (N2), mesmo estando no grupo 117.
            SupportIxcUser(ixc_user_id="417", name="Emanuelly Ferreira Cavalheiro", group_id="117", active=True),
        ]
    )
    _ticket(db_session, "T1", "90", "10", 5)
    _ticket(db_session, "T2", "90", "417", 5)
    _order(db_session, "OS1", "Ana N1", 5)
    _order(db_session, "OS2", "Emanuelly Ferreira Cavalheiro", 5)
    _order(db_session, "OS3", "emanuelly ferreira cavalheiro ", 6)
    db_session.commit()

    result = dashboard_macros.macro_dashboard(db_session, date_from=date(2026, 10, 1), date_to=date(2026, 10, 10))
    cards = {card["key"]: card for card in result["cards"]}

    assert cards["solved"]["value"] == 1
    assert cards["field"]["value"] == 1
    assert cards["performed"]["value"] == 2


def test_n2_block_counts_protocols_orders_and_new_login(db_session, monkeypatch):
    db_session.add_all(
        [
            SupportIxcUser(ixc_user_id="417", name="Emanuelly Ferreira Cavalheiro", group_id="117", active=True),
            SupportIxcUser(ixc_user_id="10", name="Ana N1", group_id="105", active=True),
        ]
    )
    _ticket(db_session, "N1", "80", "417", 5)   # interno N2
    _ticket(db_session, "N2", "81", "417", 5)   # externo N2
    _ticket(db_session, "N3", "81", None, 6)    # externo N2 sem operador também conta
    _ticket(db_session, "N4", "90", "10", 5)    # N1: não entra no N2
    _order(db_session, "OS1", "Emanuelly Ferreira Cavalheiro", 5)  # aberta pelo N2
    _order(db_session, "OS2", "Ana N1", 5)
    db_session.commit()
    # O IXC devolve o responsável em caixa alta; "Sem responsável" = O.S. sem técnico.
    monkeypatch.setattr(
        ixc_new_login,
        "finalized_in_period",
        lambda date_from, date_to, **kwargs: {"finalized": 4, "by_name": {"EMANUELLY FERREIRA CAVALHEIRO": 2, "ANA N1": 1, "": 1}},
    )

    result = dashboard_macros.macro_dashboard(db_session, date_from=date(2026, 10, 1), date_to=date(2026, 10, 10))

    assert result["n2"] == {
        "internal": 1,
        "external": 2,
        "total": 3,
        "orders": 1,
        "new_login_finalized": 4,
        "new_login_finalized_by_n2": 2,
        "new_login_error": None,
    }
    assert result["previous_n2"]["total"] == 0
    # O mesmo total N2 sobe para a faixa de cartões, com a série diária para o mini-gráfico.
    cards = {card["key"]: card for card in result["cards"]}
    assert cards["n2_total"]["value"] == 3 and cards["n2_total"]["status"] == "no_target"
    assert sum(point["n2_total"] for point in result["daily"]) == 3


def test_n2_by_collaborator_counts_protocols_and_orders_per_person(db_session):
    db_session.add_all(
        [
            SupportIxcUser(ixc_user_id="417", name="Emanuelly Ferreira Cavalheiro", group_id="117", active=True),
            SupportIxcUser(ixc_user_id="165", name="Alessandro Diniz Loss", group_id="117", active=True),
            SupportIxcUser(ixc_user_id="10", name="Ana N1", group_id="105", active=True),  # não é N2
            SupportIxcUser(ixc_user_id="999", name="Fora da lista", group_id="32", active=True),  # abre N2, mas fora da lista
        ]
    )
    _ticket(db_session, "A1", "80", "417", 5)
    _ticket(db_session, "A2", "81", "417", 5)
    _ticket(db_session, "A3", "81", "417", 6)
    _ticket(db_session, "A4", "81", "165", 6)
    _ticket(db_session, "A5", "81", "999", 6)   # outros
    _ticket(db_session, "A6", "80", None, 6)    # sem operador: outros
    _ticket(db_session, "A7", "90", "417", 6)   # N1: não conta
    _ticket(db_session, "A8", "81", "417", 25)  # fora do período
    _order(db_session, "OS1", "Emanuelly Ferreira Cavalheiro", 5)
    _order(db_session, "OS2", "emanuelly ferreira cavalheiro", 6)
    _order(db_session, "OS3", "Alessandro Diniz Loss", 7)
    _order(db_session, "OS4", "Ana N1", 7)  # não é N2
    db_session.commit()

    result = dashboard_macros.n2_by_collaborator(db_session, date(2026, 10, 1), date(2026, 10, 10))

    rows = {row["name"]: row for row in result["rows"]}
    assert set(rows) == {"Emanuelly Ferreira Cavalheiro", "Alessandro Diniz Loss"}
    emanuelly = rows["Emanuelly Ferreira Cavalheiro"]
    assert (emanuelly["internal"], emanuelly["external"], emanuelly["total"], emanuelly["orders"]) == (1, 2, 3, 2)
    alessandro = rows["Alessandro Diniz Loss"]
    assert (alessandro["internal"], alessandro["external"], alessandro["total"], alessandro["orders"]) == (0, 1, 1, 1)
    assert result["rows"][0]["name"] == "Emanuelly Ferreira Cavalheiro"  # maior atividade primeiro
    # A tabela fecha com o total N2: 2 internos (1 + sem operador) e 4 externos (3 + fora da lista).
    assert (result["others_internal"], result["others_external"]) == (1, 1)


def test_new_login_unavailable_when_ixc_fails_is_not_zero(db_session, monkeypatch):
    def broken(date_from, date_to, **kwargs):
        raise RuntimeError("IXC fora do ar")

    monkeypatch.setattr(ixc_new_login, "finalized_in_period", broken)

    result = dashboard_macros.macro_dashboard(db_session, date_from=date(2026, 10, 1), date_to=date(2026, 10, 10))

    assert result["n2"]["new_login_finalized"] is None
    assert result["n2"]["new_login_finalized_by_n2"] is None
    assert "IXC indisponível" in result["n2"]["new_login_error"]
    assert "new_login_by_responsible" not in result["n2"]


def test_macro_dashboard_empty_period_has_no_data(db_session):
    result = dashboard_macros.macro_dashboard(db_session, date_from=date(2026, 10, 1), date_to=date(2026, 10, 10))
    cards = {card["key"]: card for card in result["cards"]}

    assert cards["performed"]["value"] == 0
    assert cards["resolutivity"]["value"] is None
    assert cards["resolutivity"]["status"] == "no_data"
    assert cards["csat"]["status"] == "no_data"
