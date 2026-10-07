"""Pontos de atenção da Visão Geral (`attention.py` + `GET /operations/overview/attention-points`).

As regras são puras, então cada uma é travada com dicts - sem banco. Um teste de integração garante
a rota, o filtro de período e o contrato "sem achado" (com a contagem de regras verificadas)."""

from __future__ import annotations

from datetime import date, datetime, time, timezone

from app.modules.operations import attention
from app.modules.operations.models import OperationOrder
from app.modules.operations.period import OPERATIONS_TIMEZONE, current_month_bounds

ENDPOINT = "/api/operations/overview/attention-points"


def _overview(**over):
    base = {
        "opened": 100, "completed": 100, "completed_on_time": 90, "completed_out_of_time": 10, "sla_rate": 90.0,
    }
    return {**base, **over}


def _regional(name="UNI - NORTE", **over):
    base = {
        "regional": name, "opened": 50, "backlog": 10, "overdue_backlog": 0, "completed": 50,
        "completed_on_time": 45, "completed_out_of_time": 5, "sla_rate": 90.0,
    }
    return {**base, **over}


def _matrix(items=None, **total_over):
    items = items if items is not None else [_regional()]
    total = {**_regional("TOTAL"), **total_over}
    return {"items": items, "total": total}


def _backlog(open_=50, overdue=0, by_regional=None):
    return {"open": open_, "overdue": overdue, "by_regional": by_regional or [{"regional": "UNI - NORTE", "open": open_, "overdue": overdue}]}


def _run(overview=None, previous=None, matrix=None, period_backlog=None, include_sla=True):
    return attention.evaluate_attention_points(
        overview=overview or _overview(),
        previous_overview=previous,
        matrix=matrix or _matrix(),
        period_backlog=period_backlog or _backlog(),
        include_sla=include_sla,
    )


def _rules(result):
    return [item["rule"] for item in result["items"]]


def test_healthy_period_has_no_findings_and_reports_rules_checked():
    result = _run(previous=_overview())
    assert result["items"] == []
    assert result["rules_checked"] == result["rules_total"] == 5
    assert result["skipped_rules"] == []


def test_overall_sla_below_target_and_critical_level():
    result = _run(overview=_overview(completed_on_time=75, completed_out_of_time=25, sla_rate=75.0))
    assert result["items"][0]["rule"] == "sla_below_target" and result["items"][0]["severity"] == "attention"
    critical = _run(overview=_overview(completed_on_time=60, completed_out_of_time=40, sla_rate=60.0))
    assert critical["items"][0]["severity"] == "critical"


def test_sla_rules_ignore_small_samples():
    result = _run(overview=_overview(completed=10, completed_on_time=5, completed_out_of_time=5, sla_rate=50.0, opened=10))
    assert "sla_below_target" not in _rules(result)


def test_regional_sla_lists_only_worst_three_with_enough_volume():
    regionals = [
        _regional(f"R{i}", sla_rate=60.0 + i, completed_on_time=20 + i, completed_out_of_time=20) for i in range(5)
    ] + [_regional("Pequena", sla_rate=10.0, completed_on_time=1, completed_out_of_time=9)]
    result = _run(matrix=_matrix(regionals))
    listed = [item["regional"] for item in result["items"] if item["rule"] == "regional_sla_below_target"]
    assert listed == ["R0", "R1", "R2"]


def test_without_sla_permission_sla_rules_are_skipped_not_run():
    result = _run(overview=_overview(sla_rate=10.0, completed_on_time=10, completed_out_of_time=90), include_sla=False, previous=_overview())
    assert "sla_below_target" not in _rules(result)
    assert result["skipped_rules"] == ["sla_below_target", "regional_sla_below_target"]
    assert result["rules_checked"] == 3


def test_overdue_backlog_share_uses_period_backlog_and_names_worst_regional():
    backlog = _backlog(
        open_=100,
        overdue=25,
        by_regional=[
            {"regional": "A", "open": 40, "overdue": 5},
            {"regional": "B", "open": 60, "overdue": 20},
        ],
    )
    point = next(i for i in _run(period_backlog=backlog)["items"] if i["rule"] == "overdue_backlog_share")
    assert point["severity"] == "attention" and "B" in point["detail"] and point["value"] == 25.0
    worse = _run(period_backlog=_backlog(open_=100, overdue=45))
    assert next(i for i in worse["items"] if i["rule"] == "overdue_backlog_share")["severity"] == "critical"


def test_overdue_backlog_ignores_old_residue_in_matrix_total():
    """O estoque de hoje (matriz) pode estar 92% vencido por resíduo antigo; só o que abriu no
    período entra na regra."""
    matrix = _matrix(backlog=15670, overdue_backlog=14514)
    assert "overdue_backlog_share" not in _rules(_run(matrix=matrix, period_backlog=_backlog(open_=200, overdue=10)))


def test_overdue_backlog_ignored_for_tiny_period_backlog():
    assert "overdue_backlog_share" not in _rules(_run(period_backlog=_backlog(open_=10, overdue=10)))


def test_completed_drop_vs_previous_and_skipped_without_previous():
    result = _run(overview=_overview(completed=70, opened=70), previous=_overview(completed=100))
    assert "completed_drop" in _rules(result)
    assert "completed_drop" in _run(previous=None)["skipped_rules"]
    assert "completed_drop" not in _rules(_run(overview=_overview(completed=90, opened=90), previous=_overview(completed=100)))


def test_inflow_exceeds_output():
    result = _run(overview=_overview(opened=130, completed=100), previous=_overview())
    assert "inflow_exceeds_output" in _rules(result)


def test_critical_findings_come_first():
    result = _run(
        overview=_overview(completed_on_time=60, completed_out_of_time=40, sla_rate=60.0, opened=140),
        previous=_overview(),
    )
    severities = [item["severity"] for item in result["items"]]
    assert severities == sorted(severities, key=lambda s: 0 if s == "critical" else 1)


def test_previous_window_same_length_and_none_when_cut():
    allowed_from = date(2026, 1, 1)
    assert attention.previous_window(date(2026, 3, 11), date(2026, 3, 20), allowed_from) == (
        date(2026, 3, 1), date(2026, 3, 10),
    )
    assert attention.previous_window(date(2026, 1, 5), date(2026, 1, 20), allowed_from) is None


def test_endpoint_returns_findings_for_real_orders(client, db_session):
    _, date_to = current_month_bounds()
    opened = datetime.combine(date_to, time(8), tzinfo=OPERATIONS_TIMEZONE).astimezone(timezone.utc)
    closed = datetime.combine(date_to, time(10), tzinfo=OPERATIONS_TIMEZONE).astimezone(timezone.utc)
    db_session.add_all(
        OperationOrder(
            source="ixc", source_order_id=f"ap-{i}", order_code=f"AP{i}", sector="Suporte Externo Fibra",
            regional="UNI - NORTE", raw_payload={}, status="Finalizada", status_code="F", is_closed=True,
            sla_status="out_of_time", opened_at=opened, closed_at=closed,
        )
        for i in range(35)
    )
    db_session.flush()

    response = client.get(ENDPOINT, params={"date_from": date_to.isoformat(), "date_to": date_to.isoformat()})

    assert response.status_code == 200
    body = response.json()
    assert body["rules_total"] == 5
    assert "sla_below_target" in [item["rule"] for item in body["items"]]


def test_endpoint_rejects_inverted_period(client):
    response = client.get(ENDPOINT, params={"date_from": "2026-03-10", "date_to": "2026-03-01"})
    assert response.status_code == 422


def test_period_open_backlog_counts_only_orders_opened_in_period(client, db_session):
    from app.modules.operations import queries
    from app.core.security import get_current_user  # noqa: F401 - mesmo usuário admin da fixture
    from app.main import app

    _, date_to = current_month_bounds()
    in_period = datetime.combine(date_to, time(8), tzinfo=OPERATIONS_TIMEZONE).astimezone(timezone.utc)
    old = datetime(2024, 10, 26, 8, tzinfo=timezone.utc)

    def order(code, opened, closed, sla):
        return OperationOrder(
            source="ixc", source_order_id=code, order_code=code.upper(), sector="Suporte Externo Fibra",
            regional="UNI - NORTE", raw_payload={}, status="Aberta", status_code="A", is_closed=closed,
            sla_status=sla, opened_at=opened,
        )

    db_session.add_all(
        [
            order("pb-1", in_period, False, "out_of_time"),
            order("pb-2", in_period, False, "on_time"),
            order("pb-3", in_period, True, "out_of_time"),  # fechada: fora
            order("pb-4", old, False, "out_of_time"),  # resíduo antigo: fora
        ]
    )
    db_session.flush()

    user = app.dependency_overrides[get_current_user]()
    result = queries.period_open_backlog(db_session, date_to, date_to, user)

    assert (result["open"], result["overdue"]) == (2, 1)
    assert result["by_regional"] == [{"regional": "UNI - NORTE", "open": 2, "overdue": 1}]


def test_scope_notes_cover_team_model_filter_and_unassigned_production():
    assert "Filtro de modelo de equipe aplicado" in attention.scope_notes(team_models_selected=True, completed_without_model=9)[0]
    assert "84 O.S." in attention.scope_notes(team_models_selected=False, completed_without_model=84)[0]
    assert attention.scope_notes(team_models_selected=False, completed_without_model=0) == []


def test_completed_without_team_model_counts_only_unassigned_responsibles(client, db_session):
    from app.core.security import get_current_user
    from app.main import app
    from app.modules.operations import queries
    from app.modules.operations.models import OperationResponsibleAssignment, OperationTeamModel

    _, date_to = current_month_bounds()
    closed = datetime.combine(date_to, time(10), tzinfo=OPERATIONS_TIMEZONE).astimezone(timezone.utc)
    model = OperationTeamModel(name="EQUIPE PRÓPRIA", daily_target=5)
    db_session.add(model)
    db_session.flush()
    db_session.add(OperationResponsibleAssignment(responsible_name="Com Modelo", regional="UNI - NORTE", team_model_id=model.id))
    db_session.add_all(
        OperationOrder(
            source="ixc", source_order_id=f"nm-{i}", order_code=f"NM{i}", sector="Suporte Externo Fibra",
            regional="UNI - NORTE", raw_payload={}, status="Finalizada", status_code="F", is_closed=True,
            sla_status="on_time", responsible=who, opened_at=closed, closed_at=closed,
        )
        for i, who in enumerate(["Com Modelo", "Sem Modelo", "Sem Modelo"])
    )
    db_session.flush()

    user = app.dependency_overrides[get_current_user]()
    assert queries.completed_without_team_model(db_session, date_to, date_to, user) == 2


def test_every_rule_has_a_recommendation_text():
    assert set(attention.RECOMMENDATIONS) == set(attention.RULES_TOTAL)


def test_recommendations_are_general_one_per_rule_and_cite_all_regionals():
    weak = [
        _regional("UNI - A", sla_rate=60.0, completed_on_time=20, completed_out_of_time=20),
        _regional("UNI - B", sla_rate=75.0, completed_on_time=30, completed_out_of_time=10),
    ]
    result = _run(matrix=_matrix(weak), period_backlog=_backlog(open_=100, overdue=50))
    recs = result["recommendations"]
    rules = [rec["rule"] for rec in recs]
    assert len(rules) == len(set(rules))  # uma por regra, não uma por achado
    regional = next(rec for rec in recs if rec["rule"] == "regional_sla_below_target")
    assert "UNI - A" in regional["action"] and "UNI - B" in regional["action"] and "{" not in regional["action"]
    assert recs[0]["severity"] == "critical"
    assert "recommendation" not in result["items"][0]


def test_no_findings_means_no_recommendations():
    assert _run(previous=_overview())["recommendations"] == []
