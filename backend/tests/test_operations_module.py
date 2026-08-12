from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.api.routes.users import _set_user_profiles
from app.core.security import get_current_user, permissions_for_user
from app.main import app
from app.modules.operations import router as operations_router
from app.modules.operations.ixc_ingestion import OPEN_BACKLOG_STATUS_CODES, import_current_month_period, import_open_backlog
from app.modules.operations.models import (
    OperationImportRun,
    OperationIxcCollaborator,
    OperationOrder,
    OperationResponsibleAssignment,
    OperationResponsibleDirectorySetting,
    OperationTeamModel,
    OperationTeamTargetVersion,
)
from app.modules.operations.period import OPERATIONS_TIMEZONE, current_month_bounds
from app.modules.operations.services import classify_daily_performance
from app.services.ixc_client import IxcApiError, IxcClient, IxcPage, IxcQueryLimitError


def _utc_at(day, hour=12):
    return datetime.combine(day, time(hour=hour), tzinfo=OPERATIONS_TIMEZONE).astimezone(timezone.utc)


def test_calendar_daily_performance_is_centralized_by_team_model():
    model = {"median_from_quantity": 3, "good_from_quantity": 4, "daily_target": 5}

    assert classify_daily_performance(0, model) == "neutral"
    assert classify_daily_performance(2, model) == "below"
    assert classify_daily_performance(3, model) == "median"
    assert classify_daily_performance(4, model) == "good"
    assert classify_daily_performance(5, model) == "excellent"
    assert classify_daily_performance(10, None) == "neutral"


def test_calendar_uses_specific_weekend_and_monthly_rules():
    model = {
        "target_rules": [
            {"period_type": "weekday", "enabled": True, "median_from_quantity": 3, "good_from_quantity": 4, "target_quantity": 5},
            {"period_type": "saturday", "enabled": True, "median_from_quantity": 1, "good_from_quantity": 2, "target_quantity": 3},
            {"period_type": "sunday", "enabled": False, "median_from_quantity": 1, "good_from_quantity": 2, "target_quantity": 3},
        ]
    }

    assert classify_daily_performance(3, model, date(2026, 7, 17)) == "median"
    assert classify_daily_performance(3, model, date(2026, 7, 18)) == "excellent"
    assert classify_daily_performance(3, model, date(2026, 7, 19)) == "neutral"


def test_work_schedule_supports_regular_and_overnight_shifts():
    from app.modules.operations.services import _outside_schedule

    regular = SimpleNamespace(enabled=True, start_time=time(8), end_time=time(18))
    overnight = SimpleNamespace(enabled=True, start_time=time(20), end_time=time(6))

    assert _outside_schedule(datetime(2026, 7, 17, 17, 59), regular) == (False, None)
    assert _outside_schedule(datetime(2026, 7, 17, 18, 1), regular) == (True, "after_end")
    assert _outside_schedule(datetime(2026, 7, 17, 7, 59), regular) == (True, "before_start")
    assert _outside_schedule(datetime(2026, 7, 17, 23, 0), overnight) == (False, None)
    assert _outside_schedule(datetime(2026, 7, 18, 7, 0), overnight) == (True, "after_end")


def test_orders_can_be_filtered_by_local_closing_time(client, db_session):
    date_from, _ = current_month_bounds()
    db_session.add_all(
        [
            OperationOrder(
                source="ixc",
                source_order_id="closing-time-before",
                order_code="TIME-BEFORE",
                sector="Suporte Externo Fibra",
                responsible="Técnico Horário",
                status="Finalizada",
                status_code="F",
                is_closed=True,
                sla_status="on_time",
                opened_at=_utc_at(date_from, 8),
                closed_at=_utc_at(date_from, 17),
                raw_payload={},
            ),
            OperationOrder(
                source="ixc",
                source_order_id="closing-time-after",
                order_code="TIME-AFTER",
                sector="Suporte Externo Fibra",
                responsible="Técnico Horário",
                status="Finalizada",
                status_code="F",
                is_closed=True,
                sla_status="on_time",
                opened_at=_utc_at(date_from, 8),
                closed_at=_utc_at(date_from, 19),
                raw_payload={},
            ),
        ]
    )
    db_session.flush()

    response = client.get(
        "/api/operations/orders",
        params={
            "date_from": date_from.isoformat(),
            "date_to": date_from.isoformat(),
            "responsibles": "Técnico Horário",
            "closed_time_from": "18:00",
        },
    )

    assert response.status_code == 200
    assert [item["order_code"] for item in response.json()["items"]] == [
        "TIME-AFTER"
    ]


def test_explicit_regional_scope_is_enforced_for_any_operations_user(client, db_session, admin_user):
    date_from, _ = current_month_bounds()
    admin_user.role = "admin"
    admin_user.managed_regionals = ["UNI - JARU", "UNI - JARU"]
    db_session.add_all(
        [
            OperationOrder(
                source="ixc",
                source_order_id="scope-jaru",
                order_code="SCOPE-JARU",
                regional="UNI - JARU",
                sector="Suporte Externo Fibra",
                opened_at=_utc_at(date_from),
                raw_payload={},
            ),
            OperationOrder(
                source="ixc",
                source_order_id="scope-outra",
                order_code="SCOPE-OUTRA",
                regional="UNI - MACHADINHO DOESTE",
                sector="Suporte Externo Fibra",
                opened_at=_utc_at(date_from),
                raw_payload={},
            ),
        ]
    )
    db_session.flush()

    response = client.get(
        "/api/operations/orders",
        params={"date_from": date_from.isoformat(), "date_to": date_from.isoformat()},
    )

    assert response.status_code == 200
    assert [item["order_code"] for item in response.json()["items"]] == ["SCOPE-JARU"]


def test_removing_last_access_profile_revokes_legacy_permissions(db_session):
    from app.models import User

    user = User(
        name="Sem perfil",
        email="sem-perfil@teste.local",
        password_hash="x",
        role="operator",
        active=True,
    )
    db_session.add(user)
    db_session.flush()

    _set_user_profiles(db_session, user, [])
    db_session.flush()
    db_session.refresh(user)

    assert user.role == "workspace_restricted"
    assert permissions_for_user(user) == set()


def test_operations_feature_routes_require_their_specific_permissions(client):
    date_from, _ = current_month_bounds()
    read_only_module_user = SimpleNamespace(
        role="viewer",
        managed_regional=None,
        managed_regionals=[],
        access_profiles=[
            SimpleNamespace(
                active=True,
                permissions=[
                    SimpleNamespace(permission="operations:read"),
                    SimpleNamespace(permission="operations:manage"),
                ],
            )
        ],
    )
    app.dependency_overrides[get_current_user] = lambda: read_only_module_user
    try:
        calendar = client.get(
            "/api/operations/calendar",
            params={"date_from": date_from.isoformat(), "date_to": date_from.isoformat()},
        )
        sla = client.get(
            "/api/operations/sla",
            params={"date_from": date_from.isoformat(), "date_to": date_from.isoformat()},
        )
        sync = client.post(
            "/api/operations/imports",
            json={"date_from": date_from.isoformat(), "date_to": date_from.isoformat()},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert calendar.status_code == 403
    assert sla.status_code == 403
    assert sync.status_code == 403


def test_operations_sync_permission_is_independent_from_module_administration(client, monkeypatch):
    """Only operations:sync_ixc can import, and it still requires module access."""
    date_from, _ = current_month_bounds()
    payload = {"date_from": date_from.isoformat(), "date_to": date_from.isoformat()}

    def user_with(*permissions: str):
        return SimpleNamespace(
            id=901,
            role="workspace_restricted",
            managed_regional=None,
            managed_regionals=[],
            access_profiles=[
                SimpleNamespace(
                    active=True,
                    permissions=[SimpleNamespace(permission=permission) for permission in permissions],
                )
            ],
        )

    def fake_import(*_args, **_kwargs):
        return {
            "run_id": 1,
            "status": "completed",
            "date_from": date_from,
            "date_to": date_from,
            "fetched_count": 0,
            "created_count": 0,
            "updated_count": 0,
            "unchanged_count": 0,
            "rejected_count": 0,
            "errors": [],
        }

    monkeypatch.setattr(operations_router, "get_ixc_client", lambda: object())
    monkeypatch.setattr(operations_router, "import_current_month_period", fake_import)
    scenarios = [
        ("sync_without_module_access", ("operations:sync_ixc",), 403),
        ("module_access_only", ("operations:read",), 403),
        ("module_administration_without_sync", ("operations:read", "operations:manage"), 403),
        ("module_access_with_sync", ("operations:read", "operations:sync_ixc"), 200),
    ]

    try:
        for _name, permissions, expected_status in scenarios:
            app.dependency_overrides[get_current_user] = lambda permissions=permissions: user_with(*permissions)
            response = client.post("/api/operations/imports", json=payload)
            assert response.status_code == expected_status
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_operations_configuration_permissions_are_specific(client):
    def user_with(*permissions: str):
        return SimpleNamespace(
            id=902,
            role="workspace_restricted",
            managed_regional=None,
            managed_regionals=[],
            access_profiles=[
                SimpleNamespace(
                    active=True,
                    permissions=[SimpleNamespace(permission=permission) for permission in permissions],
                )
            ],
        )

    try:
        app.dependency_overrides[get_current_user] = lambda: user_with(
            "operations:read", "operations:manage_team_models"
        )
        assert client.get("/api/operations/team-configuration").status_code == 200
        assert client.get("/api/operations/subject-type-mappings").status_code == 403
        assert client.post("/api/operations/team-models", json={"name": "Teste Permissao Equipe"}).status_code == 201

        app.dependency_overrides[get_current_user] = lambda: user_with(
            "operations:read", "operations:manage_subjects"
        )
        assert client.get("/api/operations/team-configuration").status_code == 403
        assert client.get("/api/operations/subject-type-mappings").status_code == 200
        assert client.put(
            "/api/operations/subject-type-mappings",
            json={"subjects": ["Assunto teste de permissao"], "os_type": "Informacao"},
        ).status_code == 200

        app.dependency_overrides[get_current_user] = lambda: user_with(
            "operations:read", "operations:manage"
        )
        assert client.get("/api/operations/team-configuration").status_code == 403
        assert client.get("/api/operations/subject-type-mappings").status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_calendar_week_groups_follow_monday_boundaries(client):
    _, date_to = current_month_bounds()
    date_from = date_to.replace(day=1)

    response = client.get(
        "/api/operations/calendar",
        params={"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
    )

    assert response.status_code == 200
    days = {item["date"]: item["week"] for item in response.json()["days"]}
    assert days[date_from.isoformat()] == 1
    first_monday = date_from + timedelta(days=(7 - date_from.weekday()) % 7)
    if first_monday <= date_to and first_monday != date_from:
        assert days[first_monday.isoformat()] == 2


def test_calendar_can_consolidate_collaborator_support_and_measure_attendance_and_travel(client, db_session):
    date_from, _ = current_month_bounds()
    day = date_from
    first_execution = _utc_at(day, 8)
    first_finished = _utc_at(day, 9)
    second_execution = _utc_at(day, 10)
    second_finished = _utc_at(day, 11)
    db_session.add_all(
        [
            OperationOrder(
                source="ixc",
                source_order_id="calendar-consolidated-a",
                order_code="CAL-A",
                regional="UNI - BASE",
                sector="Suporte Externo Fibra",
                os_type="Manutenção",
                responsible="Técnico Apoio",
                status="Finalizada",
                status_code="F",
                is_closed=True,
                sla_status="on_time",
                opened_at=_utc_at(day, 7),
                displacement_started_at=_utc_at(day, 7) + timedelta(minutes=30),
                execution_started_at=first_execution,
                finished_at=first_finished,
                closed_at=first_finished,
                raw_payload={},
            ),
            OperationOrder(
                source="ixc",
                source_order_id="calendar-consolidated-b",
                order_code="CAL-B",
                regional="UNI - APOIO",
                sector="Suporte Externo Fibra",
                os_type="Manutenção",
                responsible="Técnico Apoio",
                status="Finalizada",
                status_code="F",
                is_closed=True,
                sla_status="on_time",
                opened_at=_utc_at(day, 7),
                displacement_started_at=_utc_at(day, 9) + timedelta(minutes=30),
                execution_started_at=second_execution,
                finished_at=second_finished,
                closed_at=second_finished,
                raw_payload={},
            ),
        ]
    )
    db_session.flush()
    params = {"date_from": day.isoformat(), "date_to": day.isoformat(), "group_by": "collaborator"}

    calendar = client.get("/api/operations/calendar", params=params)
    assert calendar.status_code == 200
    payload = calendar.json()
    assert payload["group_by"] == "collaborator"
    collaborator = next(item for item in payload["regionals"][0]["collaborators"] if item["responsible"] == "Técnico Apoio")
    assert collaborator["total"] == 2
    assert collaborator["attended_regionals"] == ["UNI - APOIO", "UNI - BASE"]

    detail = client.get(
        "/api/operations/calendar/day-detail",
        params={**params, "day": day.isoformat(), "regional": "Todos os colaboradores", "responsible": "Técnico Apoio", "reference_regional": "UNI - BASE"},
    )
    assert detail.status_code == 200
    metrics = detail.json()["metrics"]
    assert metrics["attended_regionals"] == ["UNI - APOIO", "UNI - BASE"]
    assert metrics["cross_regional_orders"] == 1
    assert metrics["total_execution_minutes"] == 120.0
    assert metrics["average_displacement_minutes"] == 30.0
    assert metrics["total_displacement_minutes"] == 60.0
    assert metrics["displacement_orders"] == 2
    assert metrics["first_displacement_at"] == (_utc_at(day, 7) + timedelta(minutes=30)).replace(tzinfo=None).isoformat()
    assert metrics["last_finished_at"] == second_finished.replace(tzinfo=None).isoformat()
    assert metrics["operational_window_orders"] == 2
    assert metrics["missing_operational_window_times"] == 0
    assert metrics["average_pre_displacement_minutes"] == 90.0

    monthly = client.get(
        "/api/operations/calendar/month-detail",
        params={"date_from": day.isoformat(), "date_to": day.isoformat(), "regional": "Todos os colaboradores", "responsible": "Técnico Apoio", "group_by": "collaborator", "reference_regional": "UNI - BASE"},
    )
    assert monthly.status_code == 200
    monthly_payload = monthly.json()
    assert monthly_payload["metrics"]["total_orders"] == 2
    assert monthly_payload["metrics"]["cross_regional_orders"] == 1
    assert [item["label"] for item in monthly_payload["by_regional"]] == ["UNI - APOIO", "UNI - BASE"]


def test_operations_period_defaults_to_current_month_and_keeps_three_month_window(client):
    response = client.get("/api/operations/period")
    assert response.status_code == 200
    payload = response.json()
    default_from = datetime.fromisoformat(payload["date_from"]).date()
    default_to = datetime.fromisoformat(payload["date_to"]).date()
    allowed_from = datetime.fromisoformat(payload["allowed_from"]).date()
    assert default_from.day == 1
    assert default_from.year == default_to.year and default_from.month == default_to.month
    assert allowed_from < default_from


def test_operations_overview_and_detail_are_limited_to_selected_current_period(client, db_session):
    date_from, date_to = current_month_bounds()
    opened_at = _utc_at(date_from, 8)
    closed_at = _utc_at(date_from, 10)
    db_session.add_all(
        [
            OperationOrder(
                source="ixc",
                source_order_id="1",
                order_code="IXC-1",
                regional="UNI - JI PARANA",
                sector="Suporte Externo Fibra",
                os_type="Manutenção",
                os_subject="Reparo",
                responsible="Técnico 1",
                status="Finalizada",
                status_code="F",
                is_closed=True,
                sla_status="on_time",
                sla_target_hours=24,
                elapsed_hours=2,
                opened_at=opened_at,
                closed_at=closed_at,
                raw_payload={},
            ),
            OperationOrder(
                source="ixc",
                source_order_id="2",
                order_code="IXC-2",
                regional="UNI - JI PARANA",
                sector="Suporte Externo Rádio",
                os_type="Manutenção",
                os_subject="Sem conexão",
                responsible="Técnico 2",
                status="Aberta",
                status_code="A",
                is_closed=False,
                sla_status="out_of_time",
                sla_target_hours=4,
                elapsed_hours=8,
                opened_at=opened_at,
                raw_payload={},
            ),
        ]
    )
    db_session.flush()

    query = f"date_from={date_from.isoformat()}&date_to={date_to.isoformat()}"
    overview = client.get(f"/api/operations/overview?{query}")
    assert overview.status_code == 200
    assert overview.json()["opened"] == 2
    assert overview.json()["completed"] == 1
    assert overview.json()["in_progress"] == 1
    assert overview.json()["sla_rate"] == 100.0

    details = client.get(f"/api/operations/orders?{query}&sla_statuses=out_of_time")
    assert details.status_code == 200
    assert details.json()["total"] == 1
    assert details.json()["items"][0]["order_code"] == "IXC-2"


def test_order_detail_exposes_new_fields_and_sanitizes_raw_payload(client, db_session):
    opened_at = _utc_at(current_month_bounds()[0], 8)
    db_session.add(
        OperationOrder(
            source="ixc",
            source_order_id="DETAIL-1",
            order_code="IXC-DETAIL-1",
            protocol="PROT-1",
            contract_id="CONTRACT-1",
            customer_id="CUST-1",
            customer_login="cliente.login",
            customer_name="Cliente Detalhe",
            company_id="EMP-1",
            regional="UNI - JI PARANA",
            state="RO",
            city="Ji-Paraná",
            contract_type="Residencial",
            person_type="PF",
            sector="Suporte Externo Fibra",
            os_type="Manutenção",
            os_subject="Reparo",
            responsible="Técnico Detalhe",
            status="Finalizada",
            status_code="F",
            is_closed=True,
            sla_status="on_time",
            opened_at=opened_at,
            closed_at=opened_at,
            raw_payload={
                "mensagem": "Relato normal do atendimento",
                "senha_wifi": "segredo123",
                "cliente_cpf": "000.000.000-00",
                "aninhado": {"cartao_credito": "4111", "obs": "sem problema"},
            },
        )
    )
    db_session.flush()

    response = client.get("/api/operations/orders/DETAIL-1")
    assert response.status_code == 200
    payload = response.json()

    assert payload["customer_id"] == "CUST-1"
    assert payload["customer_login"] == "cliente.login"
    assert payload["company_id"] == "EMP-1"
    assert payload["contract_type"] == "Residencial"
    assert payload["person_type"] == "PF"
    # Item 2: descrição de abertura precisa aparecer no detalhe também, não só na listagem.
    assert payload["service_description"] == "Relato normal do atendimento"
    # Item 3: sem rua/bairro/CEP/coordenadas estruturados na ingestão atual - a API documenta essa
    # limitação de forma explícita em vez de fingir uma estrutura que não existe.
    assert payload["address_is_structured"] is False

    raw_payload = payload["raw_payload"]
    assert raw_payload["mensagem"] == "Relato normal do atendimento"
    assert raw_payload["senha_wifi"] == "***"
    assert raw_payload["cliente_cpf"] == "***"
    assert raw_payload["aninhado"]["cartao_credito"] == "***"
    assert raw_payload["aninhado"]["obs"] == "sem problema"


def test_order_detail_is_not_found_outside_user_regional_scope(client, db_session, admin_user):
    admin_user.managed_regionals = ["UNI - JARU"]
    db_session.add(
        OperationOrder(
            source="ixc",
            source_order_id="DETAIL-OUT-OF-SCOPE",
            order_code="IXC-DETAIL-2",
            regional="UNI - MACHADINHO DOESTE",
            sector="Suporte Externo Fibra",
            opened_at=_utc_at(current_month_bounds()[0], 8),
            raw_payload={},
        )
    )
    db_session.flush()

    response = client.get("/api/operations/orders/DETAIL-OUT-OF-SCOPE")
    assert response.status_code == 404


def test_order_detail_returns_404_for_unknown_source_order_id(client):
    response = client.get("/api/operations/orders/does-not-exist")
    assert response.status_code == 404


def test_overview_trends_keep_openings_operational_when_responsible_is_filtered(client, db_session):
    date_from, date_to = current_month_bounds()
    first_day = date_from
    second_day = date_from + timedelta(days=1)
    for source_id, responsible, opened_day, closed_day, sla_status, subject in (
        ("trend-a", "Técnico A", first_day, first_day, "on_time", "Instalação"),
        ("trend-b", "Técnico B", first_day, second_day, "out_of_time", "Reparo"),
        ("trend-c", "Técnico B", second_day, None, "out_of_time", "Sem conexão"),
    ):
        db_session.add(
            OperationOrder(
                source="ixc",
                source_order_id=source_id,
                order_code=source_id.upper(),
                regional="UNI - TESTE",
                sector="Suporte Externo Fibra",
                os_type="Manutenção",
                os_subject=subject,
                responsible=responsible,
                status="Finalizada" if closed_day else "Aberta",
                status_code="F" if closed_day else "A",
                is_closed=bool(closed_day),
                sla_status=sla_status,
                opened_at=_utc_at(opened_day, 8),
                closed_at=_utc_at(closed_day, 12) if closed_day else None,
                raw_payload={},
            )
        )
    db_session.flush()
    params = {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "responsibles": "Técnico A",
        "granularity": "day",
    }

    overview = client.get("/api/operations/overview", params=params)
    assert overview.status_code == 200
    assert overview.json()["opened"] == 3
    assert overview.json()["opened_associated"] == 1
    assert overview.json()["responsible_filter_active"] is True
    assert overview.json()["completed"] == 1

    trend = client.get("/api/operations/overview/trends", params=params)
    assert trend.status_code == 200
    payload = trend.json()
    assert payload["openings_ignore_responsibles"] is True
    assert payload["responsible_filter_active"] is True
    first_point = payload["points"][0]
    assert first_point["opened_operation"] == 2
    assert first_point["opened_associated"] == 1
    assert first_point["completed"] == 1
    assert first_point["sla_rate"] == 100.0
    assert first_point["sla_cumulative_rate"] == 100.0

    second_point = payload["points"][1]
    assert second_point["completed"] == 0
    assert second_point["sla_rate"] is None
    assert second_point["sla_cumulative_rate"] == 100.0


def test_subject_volume_alerts_and_data_freshness_are_structured(client, db_session):
    date_from, date_to = current_month_bounds()
    opened_day = date_to - timedelta(days=50)
    db_session.add(
        OperationOrder(
            source="ixc",
            source_order_id="stable-backlog",
            order_code="IXC-STABLE",
            regional="UNI - TESTE",
            sector="Suporte Externo Fibra",
            os_type="Manutenção",
            os_subject="Sem conexão",
            responsible="Técnico Histórico",
            status="Aberta",
            status_code="A",
            is_closed=False,
            sla_status="out_of_time",
            opened_at=_utc_at(opened_day, 8),
            raw_payload={},
        )
    )
    finished_at = datetime.now(timezone.utc)
    db_session.add(
        OperationImportRun(
            date_from=date_to,
            date_to=date_to,
            status="completed",
            finished_at=finished_at,
        )
    )
    db_session.flush()

    alerts = client.get(
        "/api/operations/overview/volume-alerts",
        params={"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
    )
    assert alerts.status_code == 200
    alert_payload = alerts.json()
    assert alert_payload["responsibles_ignored"] is True
    subject = next(item for item in alert_payload["items"] if item["subject"] == "Sem conexão")
    assert subject["current_backlog"] == 1
    assert subject["sample_days"] == 56

    freshness = client.get("/api/operations/data-freshness")
    assert freshness.status_code == 200
    assert freshness.json()["status"] == "completed"
    assert freshness.json()["date_to"] == date_to.isoformat()


def test_control_tower_detects_persistent_pressure_and_expands_hierarchy(client, db_session):
    _, date_to = current_month_bounds()
    history_start = date_to - timedelta(days=76)
    sequence = 0
    current_start = date_to - timedelta(days=6)
    for offset in range(77):
        day = history_start + timedelta(days=offset)
        sequence += 1
        db_session.add(
            OperationOrder(
                source="ixc",
                source_order_id=f"tower-base-{sequence}",
                order_code=f"TOWER-{sequence}",
                regional="UNI - NORTE",
                city="Cidade A",
                sector="Suporte Externo Fibra",
                os_type="Manutenção",
                os_subject="Sem conexão",
                responsible="Técnico A",
                status="Finalizada",
                status_code="F",
                is_closed=True,
                sla_status="on_time",
                opened_at=_utc_at(day, 8),
                closed_at=_utc_at(day, 12),
                raw_payload={},
            )
        )
        if day >= date_to - timedelta(days=2):
            for extra in range(4):
                sequence += 1
                db_session.add(
                    OperationOrder(
                        source="ixc",
                        source_order_id=f"tower-pressure-{sequence}",
                        order_code=f"TOWER-{sequence}",
                        regional="UNI - NORTE",
                        city="Cidade A",
                        sector="Suporte Externo Fibra",
                        os_type="Manutenção",
                        os_subject="Sem conexão",
                        responsible="Técnico B",
                        status="Aberta",
                        status_code="A",
                        is_closed=False,
                        sla_status="out_of_time",
                        opened_at=_utc_at(day, 9 + extra),
                        deadline_at=_utc_at(day, 10 + extra),
                        raw_payload={},
                    )
                )
    db_session.flush()

    params = {
        "date_from": current_start.isoformat(),
        "date_to": date_to.isoformat(),
        "responsibles": "Técnico A",
    }
    root = client.get("/api/operations/overview/control-tower", params=params)
    assert root.status_code == 200
    payload = root.json()
    assert payload["responsibles_ignored"] is True
    assert payload["summary"]["status"] == "critical"
    assert payload["summary"]["opened_recent"] == 19
    assert payload["summary"]["completed_recent"] == 7
    assert payload["summary"]["persistent_days"] == 3
    subject = next(item for item in payload["items"] if item["label"] == "Sem conexão")
    assert subject["status"] == "critical"
    assert subject["backlog"] == 12
    assert len(payload["timeline"]) == 28

    regional = client.get(
        "/api/operations/overview/control-tower",
        params={**params, "level": "regional", "parent_subject": "Sem conexão"},
    )
    assert regional.status_code == 200
    regional_payload = regional.json()
    assert regional_payload["level"] == "regional"
    assert regional_payload["items"][0]["label"] == "UNI - NORTE"
    assert regional_payload["items"][0]["path"]["subject"] == "Sem conexão"

    openings = client.get(
        "/api/operations/openings/orders",
        params={
            "date_from": current_start.isoformat(),
            "date_to": date_to.isoformat(),
            "subjects": "Sem conexão",
            "regionals": "UNI - NORTE",
        },
    )
    assert openings.status_code == 200
    assert openings.json()["total"] == 19


def test_operations_collaborator_sla_and_monthly_calendar_drill_through(client, db_session):
    date_from, date_to = current_month_bounds()
    previous_day = date_to.fromordinal(date_to.toordinal() - 1)
    records = [
        ("calendar-1", "IXC-C1", "Técnico A", previous_day, "Manutenção", "on_time", 2.0),
        ("calendar-2", "IXC-C2", "Técnico A", date_to, "Ativação", "out_of_time", 5.0),
        ("calendar-3", "IXC-C3", "Técnico B", date_to, "Manutenção", "on_time", 1.0),
    ]
    for source_id, code, responsible, closed_day, os_type, sla_status, elapsed_hours in records:
        db_session.add(
            OperationOrder(
                source="ixc",
                source_order_id=source_id,
                order_code=code,
                regional="UNI - ALTA FLORESTA DOESTE",
                sector="Suporte Externo Fibra",
                os_type=os_type,
                os_subject="Teste operacional",
                responsible=responsible,
                status="Finalizada",
                status_code="F",
                is_closed=True,
                sla_status=sla_status,
                elapsed_hours=elapsed_hours,
                opened_at=_utc_at(closed_day, 8),
                assumed_at=_utc_at(closed_day, 9),
                displacement_started_at=_utc_at(closed_day, 9) + timedelta(minutes=30),
                execution_started_at=_utc_at(closed_day, 10),
                finished_at=_utc_at(closed_day, 12),
                closed_at=_utc_at(closed_day, 12),
                raw_payload={},
            )
        )
    db_session.flush()
    params = {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "sectors": "Suporte Externo Fibra",
    }

    collaborator_response = client.get("/api/operations/sla/collaborators", params=params)
    assert collaborator_response.status_code == 200
    collaborator_data = collaborator_response.json()
    technician_a = next(item for item in collaborator_data["items"] if item["responsible"] == "Técnico A")
    assert technician_a["completed"] == 2
    assert technician_a["sla_rate"] == 50.0
    assert technician_a["active_days"] == 2
    assert technician_a["daily_average"] == 1.0
    assert technician_a["measurable_execution_orders"] == 2
    assert technician_a["average_execution_minutes"] == 120.0
    assert technician_a["minimum_execution_minutes"] == 120.0
    assert technician_a["maximum_execution_minutes"] == 120.0
    assert technician_a["type_counts"] == {"Manutenção": 1, "Ativação": 1}

    calendar_response = client.get("/api/operations/calendar", params=params)
    assert calendar_response.status_code == 200
    calendar_data = calendar_response.json()
    assert calendar_data["competence"] == f"{date_to.year:04d}-{date_to.month:02d}"
    branch = next(item for item in calendar_data["regionals"] if item["regional"] == "UNI - ALTA FLORESTA DOESTE")
    assert branch["total"] == 3
    assert branch["daily_counts"][date_to.isoformat()] == 2

    detail_response = client.get(
        "/api/operations/calendar/orders",
        params={
            "day": date_to.isoformat(),
            "regional": "UNI - ALTA FLORESTA DOESTE",
            "responsible": "Técnico A",
            "sectors": "Suporte Externo Fibra",
        },
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["total"] == 1
    assert detail_response.json()["items"][0]["order_code"] == "IXC-C2"

    day_detail_response = client.get(
        "/api/operations/calendar/day-detail",
        params={
            "day": date_to.isoformat(),
            "regional": "UNI - ALTA FLORESTA DOESTE",
            "responsible": "Técnico A",
            "sectors": "Suporte Externo Fibra",
        },
    )
    assert day_detail_response.status_code == 200
    day_detail = day_detail_response.json()
    assert day_detail["orders"]["total"] == 1
    assert day_detail["metrics"]["timed_orders"] == 1
    assert day_detail["metrics"]["average_execution_minutes"] == 120.0
    assert day_detail["metrics"]["median_execution_minutes"] == 120.0
    assert day_detail["metrics"]["average_pre_displacement_minutes"] == 90.0
    assert day_detail["metrics"]["average_displacement_minutes"] == 30.0
    assert day_detail["metrics"]["sla_rate"] == 0.0
    assert day_detail["metrics"]["type_counts"] == {"Ativação": 1}


def test_operations_sla_hierarchy_expands_and_uses_weighted_totals(client, db_session):
    date_from, date_to = current_month_bounds()
    records = [
        ("hierarchy-1", "Manutenção", "Sem conexão", "Fibra rompida", "on_time", 10.0, 60),
        ("hierarchy-2", "Manutenção", "Sem conexão", "Conector", "out_of_time", 20.0, 120),
        ("hierarchy-3", "Ativação", "Instalação", "Casa", "on_time", 50.0, 180),
    ]
    for source_id, os_type, subject, diagnosis, sla_status, elapsed_hours, execution_minutes in records:
        execution_started_at = _utc_at(date_to, 9)
        db_session.add(
            OperationOrder(
                source="ixc",
                source_order_id=source_id,
                order_code=f"IXC-{source_id}",
                regional="UNI - JI PARANA",
                sector="Suporte Externo Fibra",
                os_type=os_type,
                os_subject=subject,
                diagnosis=diagnosis,
                responsible="Técnico Hierarquia",
                status="Finalizada",
                status_code="F",
                is_closed=True,
                sla_status=sla_status,
                elapsed_hours=elapsed_hours,
                opened_at=_utc_at(date_to, 8),
                execution_started_at=execution_started_at,
                finished_at=execution_started_at + timedelta(minutes=execution_minutes),
                closed_at=_utc_at(date_to, 18),
                raw_payload={},
            )
        )
    db_session.flush()
    base_params = {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "sectors": "Suporte Externo Fibra",
    }

    root_response = client.get("/api/operations/sla/hierarchy", params=base_params)
    assert root_response.status_code == 200
    root = root_response.json()
    assert [item["label"] for item in root["items"]] == ["Manutenção", "Ativação"]
    assert root["items"][0]["sla_rate"] == 50.0
    assert root["total"]["completed"] == 3
    assert root["total"]["sla_rate"] == 66.7
    assert root["total"]["up_to_12h_rate"] == 33.3
    assert root["total"]["from_12h_to_24h_rate"] == 33.3
    assert root["total"]["from_48h_to_72h_rate"] == 33.3
    assert root["total"]["average_closing_hours"] == 26.67

    subject_response = client.get(
        "/api/operations/sla/hierarchy",
        params={**base_params, "level": "subject", "parent_os_type": "Manutenção"},
    )
    assert subject_response.status_code == 200
    assert subject_response.json()["items"][0]["label"] == "Sem conexão"
    assert subject_response.json()["items"][0]["completed"] == 2

    diagnosis_response = client.get(
        "/api/operations/sla/hierarchy",
        params={
            **base_params,
            "level": "diagnosis",
            "parent_os_type": "Manutenção",
            "parent_subject": "Sem conexão",
        },
    )
    assert diagnosis_response.status_code == 200
    assert {item["label"] for item in diagnosis_response.json()["items"]} == {"Fibra rompida", "Conector"}

    root_diagnosis_response = client.get(
        "/api/operations/sla/hierarchy",
        params={**base_params, "level": "diagnosis"},
    )
    assert root_diagnosis_response.status_code == 200
    assert {item["label"] for item in root_diagnosis_response.json()["items"]} == {
        "Fibra rompida",
        "Conector",
        "Casa",
    }


def test_operations_collaborator_sla_uses_a_unique_column_for_aggregated_types(client, db_session):
    date_from, date_to = current_month_bounds()
    for index, os_type in enumerate(("Outros", "Ativação", "Manutenção", "Reparo", "Instalação", "Mudança", "Vistoria"), start=1):
        db_session.add(
            OperationOrder(
                source="ixc",
                source_order_id=f"sla-other-{index}",
                order_code=f"IXC-OTHER-{index}",
                regional="UNI - MACHADINHO DOESTE",
                sector="Suporte Externo Fibra",
                os_type=os_type,
                responsible="Técnico Tipos",
                status="Finalizada",
                status_code="F",
                is_closed=True,
                sla_status="on_time",
                opened_at=_utc_at(date_to, 8),
                closed_at=_utc_at(date_to, 12),
                raw_payload={},
            )
        )
    db_session.flush()

    response = client.get(
        "/api/operations/sla/collaborators",
        params={
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "sectors": "Suporte Externo Fibra",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["type_columns"]) == len(set(data["type_columns"]))
    assert "Outros" in data["type_columns"]
    assert "Demais tipos" in data["type_columns"]


def test_operations_filters_orders_by_assigned_team_model(client, db_session):
    date_from, date_to = current_month_bounds()
    own_model = OperationTeamModel(name="EQUIPE PRÓPRIA", daily_target=5)
    outsourced_model = OperationTeamModel(name="TERCEIRIZADA", daily_target=5)
    db_session.add_all([own_model, outsourced_model])
    db_session.flush()
    db_session.add_all(
        [
            OperationResponsibleAssignment(
                responsible_name="Técnico Próprio",
                regional="UNI - TESTE",
                team_model_id=own_model.id,
            ),
            OperationResponsibleAssignment(
                responsible_name="Técnico Terceiro",
                regional="UNI - TESTE",
                team_model_id=outsourced_model.id,
            ),
            OperationOrder(
                source="ixc", source_order_id="team-model-own", order_code="TEAM-OWN",
                regional="UNI - TESTE", sector="Suporte Externo Fibra",
                responsible="Técnico Próprio", status="Finalizada", status_code="F",
                is_closed=True, sla_status="on_time", opened_at=_utc_at(date_to, 8),
                closed_at=_utc_at(date_to, 10), raw_payload={},
            ),
            OperationOrder(
                source="ixc", source_order_id="team-model-outsourced", order_code="TEAM-OUT",
                regional="UNI - TESTE", sector="Suporte Externo Fibra",
                responsible="Técnico Terceiro", status="Finalizada", status_code="F",
                is_closed=True, sla_status="on_time", opened_at=_utc_at(date_to, 8),
                closed_at=_utc_at(date_to, 10), raw_payload={},
            ),
        ]
    )
    db_session.flush()

    response = client.get(
        "/api/operations/orders",
        params={
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "team_models": "EQUIPE PRÓPRIA",
        },
    )
    options = client.get(
        "/api/operations/filters",
        params={"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
    )

    assert response.status_code == 200
    assert [item["order_code"] for item in response.json()["items"]] == ["TEAM-OWN"]
    assert options.status_code == 200
    assert "EQUIPE PRÓPRIA" in options.json()["team_models"]


def test_ixc_responsible_options_respect_selected_team_model(client, db_session):
    own = OperationTeamModel(name="MODELO IXC A", daily_target=5)
    other = OperationTeamModel(name="MODELO IXC B", daily_target=5)
    db_session.add_all([own, other])
    db_session.flush()
    db_session.add_all([
        OperationResponsibleAssignment(responsible_name="Colaborador A", regional="UNI - TESTE", team_model_id=own.id),
        OperationResponsibleAssignment(responsible_name="Colaborador B", regional="UNI - TESTE", team_model_id=other.id),
        OperationIxcCollaborator(source_employee_id="a", name="Colaborador A", active=True),
        OperationIxcCollaborator(source_employee_id="b", name="Colaborador B", active=True),
        OperationResponsibleDirectorySetting(id=1, source="ixc"),
    ])
    db_session.commit()
    date_from, date_to = current_month_bounds()
    response = client.get(
        "/api/operations/filters",
        params={"date_from": date_from.isoformat(), "date_to": date_to.isoformat(), "team_models": "MODELO IXC A"},
    )
    assert response.status_code == 200
    assert response.json()["responsibles"] == ["Colaborador A"]


def test_operations_accepts_all_sectors_and_repeated_multi_filters(client, db_session):
    date_from, date_to = current_month_bounds()
    opened_at = _utc_at(date_from, 8)
    db_session.add_all(
        [
            OperationOrder(
                source="ixc", source_order_id="scope-7", order_code="IXC-S7",
                regional="UNI - MACHADINHO DOESTE", sector="Suporte Externo",
                responsible="Técnico A", status="Aberta", status_code="A", is_closed=False,
                sla_status="on_time", opened_at=opened_at, raw_payload={},
            ),
            OperationOrder(
                source="ixc", source_order_id="scope-9", order_code="IXC-S9",
                regional="UNI - JI PARANA", sector="Suporte Externo Fibra",
                responsible="Técnico B", status="Aberta", status_code="A", is_closed=False,
                sla_status="on_time", opened_at=opened_at, raw_payload={},
            ),
            OperationOrder(
                source="ixc", source_order_id="scope-other", order_code="IXC-OTHER",
                regional="UNI - JI PARANA", sector="Faturamento",
                responsible="Técnico B", status="Aberta", status_code="A", is_closed=False,
                sla_status="on_time", opened_at=opened_at, raw_payload={},
            ),
        ]
    )
    db_session.flush()

    params = [
        ("date_from", date_from.isoformat()), ("date_to", date_to.isoformat()),
        ("regionals", "UNI - MACHADINHO DOESTE"), ("regionals", "UNI - JI PARANA"),
        ("responsibles", "Técnico A"), ("responsibles", "Técnico B"),
    ]
    details = client.get("/api/operations/orders", params=params)
    assert details.status_code == 200
    assert {item["order_code"] for item in details.json()["items"]} == {"IXC-S7", "IXC-S9", "IXC-OTHER"}

    options = client.get(
        "/api/operations/filters",
        params={"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
    )
    assert options.status_code == 200
    assert len(options.json()["sectors"]) == 21
    assert "Faturamento" in options.json()["sectors"]
    assert "Suporte Externo Fibra" in options.json()["sectors"]


def test_operation_filter_options_are_faceted_and_responsible_mode_can_use_only_completed(client, db_session):
    date_from, date_to = current_month_bounds()
    opened_at = _utc_at(date_from, 8)
    closed_at = _utc_at(date_from, 12)
    db_session.add_all(
        [
            OperationOrder(
                source="ixc", source_order_id="facet-closed", order_code="IXC-FC",
                regional="UNI - MACHADINHO DOESTE", sector="Suporte Externo Fibra",
                city="Machadinho D'Oeste", responsible="Técnico Finalizador",
                status="Finalizada", status_code="F", is_closed=True, sla_status="on_time",
                opened_at=opened_at, closed_at=closed_at, raw_payload={},
            ),
            OperationOrder(
                source="ixc", source_order_id="facet-open", order_code="IXC-FO",
                regional="UNI - MACHADINHO DOESTE", sector="Suporte Externo Fibra",
                city="Machadinho D'Oeste", responsible="Técnico com O.S. aberta",
                status="Aberta", status_code="A", is_closed=False, sla_status="on_time",
                opened_at=opened_at, raw_payload={},
            ),
            OperationOrder(
                source="ixc", source_order_id="facet-other", order_code="IXC-FJ",
                regional="UNI - JI PARANA", sector="Suporte Externo Fibra",
                city="Ji-Paraná", responsible="Técnico de outra filial",
                status="Finalizada", status_code="F", is_closed=True, sla_status="on_time",
                opened_at=opened_at, closed_at=closed_at, raw_payload={},
            ),
        ]
    )
    db_session.flush()
    base_params = [
        ("date_from", date_from.isoformat()),
        ("date_to", date_to.isoformat()),
        ("regionals", "UNI - MACHADINHO DOESTE"),
    ]

    all_orders = client.get("/api/operations/filters", params=[*base_params, ("responsible_mode", "all")])
    assert all_orders.status_code == 200
    assert all_orders.json()["responsibles"] == ["Técnico com O.S. aberta", "Técnico Finalizador"]
    assert all_orders.json()["cities"] == ["Machadinho D'Oeste"]

    completed = client.get(
        "/api/operations/filters",
        params=[*base_params, ("responsible_mode", "completed")],
    )
    assert completed.status_code == 200
    assert completed.json()["responsibles"] == ["Técnico Finalizador"]


def test_operations_saved_filters_are_crud_scoped_to_authenticated_user(client, db_session, admin_user):
    created = client.post(
        "/api/operations/saved-filters",
        json={
            "name": "Machadinho — Suporte Fibra",
            "filters": {
                "regionals": ["UNI - MACHADINHO DOESTE"],
                "sectors": ["Suporte Externo Fibra"],
                "responsibles": ["Técnico A", "Técnico B"],
            },
        },
    )
    assert created.status_code == 201
    saved_id = created.json()["id"]

    duplicate = client.post(
        "/api/operations/saved-filters",
        json={"name": "machadinho — suporte fibra", "filters": {}},
    )
    assert duplicate.status_code == 409

    listed = client.get("/api/operations/saved-filters")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [saved_id]

    updated = client.patch(
        f"/api/operations/saved-filters/{saved_id}",
        json={"name": "Machadinho — Equipe Externa", "filters": {"sectors": ["Suporte Externo"]}},
    )
    assert updated.status_code == 200
    assert updated.json()["filters"]["sectors"] == ["Suporte Externo"]

    other_user = type(admin_user)(
        name="Outro", email="outro@pytest.local", role="admin", active=True, password_hash="x"
    )
    db_session.add(other_user)
    db_session.flush()
    from app.core.security import get_current_user
    from app.main import app
    app.dependency_overrides[get_current_user] = lambda: other_user
    assert client.get("/api/operations/saved-filters").json() == []
    assert client.delete(f"/api/operations/saved-filters/{saved_id}").status_code == 404
    app.dependency_overrides[get_current_user] = lambda: admin_user

    deleted = client.delete(f"/api/operations/saved-filters/{saved_id}")
    assert deleted.status_code == 204
    assert client.get("/api/operations/saved-filters").json() == []


def test_operations_api_rejects_dates_outside_available_operational_year(client):
    date_from, _ = current_month_bounds()
    previous_day = date_from.fromordinal(date_from.toordinal() - 1)

    response = client.get(
        "/api/operations/overview",
        params={"date_from": previous_day.isoformat(), "date_to": date_from.isoformat()},
    )

    assert response.status_code == 422
    assert "somente datas do ano operacional" in response.json()["detail"]


def test_in_progress_scope_has_no_date_requirement_and_includes_old_open_orders(client, db_session):
    date_from, date_to = current_month_bounds()
    old_opened_at = _utc_at(date_from, 8) - timedelta(days=240)
    db_session.add(
        OperationOrder(
            source="ixc",
            source_order_id="old-open-order",
            order_code="IXC-OLD-OPEN",
            regional="UNI - MACHADINHO DOESTE",
            sector="Suporte Externo Fibra",
            os_type="Manutenção",
            responsible="Técnico Histórico",
            status="Aberta",
            status_code="A",
            is_closed=False,
            sla_status="out_of_time",
            opened_at=old_opened_at,
            raw_payload={},
        )
    )
    db_session.flush()

    overview = client.get(
        "/api/operations/overview",
        params={
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "regionals": "UNI - MACHADINHO DOESTE",
        },
    )
    assert overview.status_code == 200
    assert overview.json()["in_progress"] == 1
    assert overview.json()["opened_out_of_time"] == 1

    breakdown = client.get(
        "/api/operations/in-progress",
        params={"group_by": "regional", "regionals": "UNI - MACHADINHO DOESTE"},
    )
    assert breakdown.status_code == 200
    assert breakdown.json() == [
        {"label": "UNI - MACHADINHO DOESTE", "quantity": 1, "percentage": 100.0}
    ]

    by_subject = client.get(
        "/api/operations/in-progress",
        params={"group_by": "subject", "regionals": "UNI - MACHADINHO DOESTE"},
    )
    assert by_subject.status_code == 200
    assert by_subject.json() == [
        {"label": "Não identificado", "quantity": 1, "percentage": 100.0}
    ]

    details = client.get(
        "/api/operations/in-progress/orders",
        params={"regionals": "UNI - MACHADINHO DOESTE"},
    )
    assert details.status_code == 200
    assert details.json()["total"] == 1
    assert details.json()["items"][0]["order_code"] == "IXC-OLD-OPEN"

    options = client.get(
        "/api/operations/filters",
        params={"scope": "in_progress", "regionals": "UNI - MACHADINHO DOESTE"},
    )
    assert options.status_code == 200
    assert options.json()["responsibles"] == ["Técnico Histórico"]


def test_team_model_assignment_is_returned_by_monthly_calendar(client, db_session):
    date_from, date_to = current_month_bounds()
    db_session.add(
        OperationOrder(
            source="ixc",
            source_order_id="team-calendar-order",
            order_code="IXC-TEAM-1",
            regional="UNI - MACHADINHO DOESTE",
            sector="Suporte Externo Fibra",
            os_type="Manutenção",
            responsible="Técnico Equipe",
            status="Finalizada",
            status_code="F",
            is_closed=True,
            sla_status="on_time",
            opened_at=_utc_at(date_to, 8),
            closed_at=_utc_at(date_to, 12),
            raw_payload={},
        )
    )
    db_session.flush()

    created = client.post(
        "/api/operations/team-models",
        json={
            "name": "RURAL",
            "daily_target": 6,
            "median_from_quantity": 4,
            "good_from_quantity": 5,
            "below_target_color": "#fecaca",
            "median_color": "#fde68a",
            "good_color": "#bbf7d0",
            "excellent_color": "#bfdbfe",
            "active": True,
        },
    )
    assert created.status_code == 201
    model_id = created.json()["id"]

    assigned = client.put(
        "/api/operations/team-members",
        json={
            "responsible_name": "Técnico Equipe",
            "regional": "UNI - MACHADINHO DOESTE",
            "team_model_id": model_id,
        },
    )
    assert assigned.status_code == 204

    configuration = client.get("/api/operations/team-configuration")
    assert configuration.status_code == 200
    member = next(item for item in configuration.json()["members"] if item["responsible_name"] == "Técnico Equipe")
    assert member["team_model_id"] == model_id

    calendar = client.get(
        "/api/operations/calendar",
        params={
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "regionals": "UNI - MACHADINHO DOESTE",
        },
    )
    assert calendar.status_code == 200
    person = calendar.json()["regionals"][0]["collaborators"][0]
    assert person["team_model"]["name"] == "RURAL"
    assert person["team_model"]["daily_target"] == 6
    assert person["team_model"]["excellent_color"] == "#bfdbfe"
    assert person["daily_performance"][date_to.isoformat()] == "below"


def test_team_model_rejects_overlapping_color_thresholds(client):
    response = client.post(
        "/api/operations/team-models",
        json={
            "name": "AUXILIAR",
            "daily_target": 5,
            "median_from_quantity": 4,
            "good_from_quantity": 4,
        },
    )

    assert response.status_code == 422
    assert "ordem" in response.json()["detail"]


def test_team_model_can_be_renamed_without_losing_identity(client):
    created = client.post(
        "/api/operations/team-models",
        json={"name": "RURAL", "daily_target": 5, "median_from_quantity": 3, "good_from_quantity": 4},
    )
    assert created.status_code == 201
    model_id = created.json()["id"]

    renamed = client.patch(f"/api/operations/team-models/{model_id}", json={"name": "Plantão Rural Especial"})
    assert renamed.status_code == 200
    assert renamed.json()["id"] == model_id
    assert renamed.json()["name"] == "Plantão Rural Especial"


def test_creating_team_model_opens_one_target_version_per_period(client, db_session):
    created = client.post(
        "/api/operations/team-models",
        json={"name": "VERSIONADO", "daily_target": 5, "median_from_quantity": 3, "good_from_quantity": 4},
    )
    assert created.status_code == 201
    model_id = created.json()["id"]

    versions = db_session.query(OperationTeamTargetVersion).filter(
        OperationTeamTargetVersion.team_model_id == model_id
    ).all()
    assert len(versions) == 4  # weekday/saturday/sunday/monthly (regras padrão)
    assert all(version.valid_to is None for version in versions)
    weekday = next(version for version in versions if version.period_type == "weekday")
    assert weekday.target_quantity == 5
    assert weekday.team_model_name == "VERSIONADO"


def test_updating_team_model_closes_old_target_version_and_opens_new(client, db_session):
    """Achado que motivou esta tabela: editar a meta hoje apaga a regra antiga sem deixar rastro -
    a versão precisa fechar (`valid_to`) em vez de desaparecer, pra ainda ser possível saber qual
    era a meta vigente antes desta edição."""
    created = client.post(
        "/api/operations/team-models",
        json={"name": "VERSIONADO 2", "daily_target": 5, "median_from_quantity": 3, "good_from_quantity": 4},
    )
    model_id = created.json()["id"]

    updated = client.patch(
        f"/api/operations/team-models/{model_id}",
        json={
            "target_rules": [
                {"period_type": "weekday", "target_quantity": 8, "median_from_quantity": 4, "good_from_quantity": 6, "start_time": "08:00", "end_time": "18:00"},
                {"period_type": "saturday", "target_quantity": 8, "median_from_quantity": 4, "good_from_quantity": 6, "start_time": "08:00", "end_time": "18:00"},
                {"period_type": "sunday", "target_quantity": 4, "median_from_quantity": 2, "good_from_quantity": 3, "enabled": False},
                {"period_type": "monthly", "target_quantity": 176, "median_from_quantity": 88, "good_from_quantity": 132},
            ]
        },
    )
    assert updated.status_code == 200

    db_session.expire_all()
    all_versions = db_session.query(OperationTeamTargetVersion).filter(
        OperationTeamTargetVersion.team_model_id == model_id
    ).all()
    open_versions = {v.period_type: v for v in all_versions if v.valid_to is None}
    closed_versions = {v.period_type: v for v in all_versions if v.valid_to is not None}

    assert len(open_versions) == 4
    assert len(closed_versions) == 4
    assert open_versions["weekday"].target_quantity == 8
    assert closed_versions["weekday"].target_quantity == 5
    assert closed_versions["weekday"].valid_to is not None


def test_team_model_can_be_deleted_only_without_linked_members(client):
    unused = client.post(
        "/api/operations/team-models",
        json={"name": "SUPORTE CARRO", "daily_target": 5, "median_from_quantity": 3, "good_from_quantity": 4},
    )
    assert unused.status_code == 201
    assert client.delete(f"/api/operations/team-models/{unused.json()['id']}").status_code == 204

    linked = client.post(
        "/api/operations/team-models",
        json={"name": "SUPORTE MOTO", "daily_target": 7, "median_from_quantity": 5, "good_from_quantity": 6},
    )
    assert linked.status_code == 201
    model_id = linked.json()["id"]
    assigned = client.put(
        "/api/operations/team-members",
        json={"responsible_name": "Técnico Vinculado", "regional": "UNI - TESTE", "team_model_id": model_id},
    )
    assert assigned.status_code == 204

    blocked = client.delete(f"/api/operations/team-models/{model_id}")
    assert blocked.status_code == 409
    assert "1 colaborador" in blocked.json()["detail"]


def test_supervisor_scope_can_only_reassign_own_team_members(client, db_session):
    """Cobre o autoatendimento pedido pela operação: um supervisor (`operations:manage_own_team_members`,
    sem `operations:manage_team_models`) só pode reatribuir modelo de equipe de quem está vinculado a
    ele em `ManagementOperationalMember` - nunca vê nem edita colaborador de outro supervisor, e nunca
    cria/exclui modelo (isso continua exclusivo de `operations:manage_team_models`)."""
    from app.modules.management.models import ManagementOperationalMember

    date_from, date_to = current_month_bounds()
    for name in ("Tecnico Da Equipe A", "Tecnico De Outro Supervisor"):
        db_session.add(
            OperationOrder(
                source="ixc",
                source_order_id=f"supervisor-scope-{name}",
                order_code=f"IXC-SUP-{name}",
                regional="UNI - TESTE",
                sector="Suporte Externo Fibra",
                os_type="Manutenção",
                responsible=name,
                status="Finalizada",
                status_code="F",
                is_closed=True,
                sla_status="on_time",
                opened_at=_utc_at(date_to, 8),
                closed_at=_utc_at(date_to, 12),
                raw_payload={},
            )
        )
    db_session.flush()

    model_a = client.post(
        "/api/operations/team-models",
        json={"name": "EQUIPE SUPERVISOR A", "daily_target": 5, "median_from_quantity": 3, "good_from_quantity": 4},
    )
    assert model_a.status_code == 201
    model_a_id = model_a.json()["id"]

    db_session.add_all(
        [
            ManagementOperationalMember(
                responsible_name="Tecnico Da Equipe A",
                regional="UNI - TESTE",
                supervisor_user_id=501,
                is_active=True,
            ),
            ManagementOperationalMember(
                responsible_name="Tecnico De Outro Supervisor",
                regional="UNI - TESTE",
                supervisor_user_id=999,
                is_active=True,
            ),
        ]
    )
    db_session.commit()

    supervisor = SimpleNamespace(
        id=501,
        role="workspace_restricted",
        managed_regional=None,
        managed_regionals=[],
        access_profiles=[
            SimpleNamespace(
                active=True,
                permissions=[
                    SimpleNamespace(permission="operations:read"),
                    SimpleNamespace(permission="operations:manage_own_team_members"),
                ],
            )
        ],
    )
    app.dependency_overrides[get_current_user] = lambda: supervisor
    try:
        # Não pode criar modelo - isso continua exclusivo de operations:manage_team_models.
        assert client.post(
            "/api/operations/team-models",
            json={"name": "NOVO MODELO", "daily_target": 5, "median_from_quantity": 3, "good_from_quantity": 4},
        ).status_code == 403

        # A lista só mostra quem é dele.
        configuration = client.get("/api/operations/team-configuration")
        assert configuration.status_code == 200
        names = {member["responsible_name"] for member in configuration.json()["members"]}
        assert "Tecnico Da Equipe A" in names
        assert "Tecnico De Outro Supervisor" not in names

        # Reatribuir quem é dele funciona.
        assigned = client.put(
            "/api/operations/team-members",
            json={"responsible_name": "Tecnico Da Equipe A", "regional": "UNI - TESTE", "team_model_id": model_a_id},
        )
        assert assigned.status_code == 204

        # Reatribuir quem NÃO é dele dá 404 (não 403 - não deve nem confirmar que existe).
        blocked = client.put(
            "/api/operations/team-members",
            json={"responsible_name": "Tecnico De Outro Supervisor", "regional": "UNI - TESTE", "team_model_id": model_a_id},
        )
        assert blocked.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    db_session.expire_all()
    member = db_session.scalar(
        select(ManagementOperationalMember).where(ManagementOperationalMember.responsible_name == "Tecnico Da Equipe A")
    )
    assert member.team_model_id == model_a_id
    untouched = db_session.scalar(
        select(ManagementOperationalMember).where(ManagementOperationalMember.responsible_name == "Tecnico De Outro Supervisor")
    )
    assert untouched.team_model_id is None


def test_team_model_assignment_is_global_for_the_collaborator(client, db_session):
    created = client.post(
        "/api/operations/team-models",
        json={"name": "GLOBAL RURAL", "daily_target": 5, "median_from_quantity": 3, "good_from_quantity": 4},
    )
    assert created.status_code == 201
    model_id = created.json()["id"]
    for regional in ("UNI - JARU", "UNI - MACHADINHO"):
        response = client.put(
            "/api/operations/team-members",
            json={"responsible_name": "Técnico Global", "regional": regional, "team_model_id": model_id},
        )
        assert response.status_code == 204

    assignments = list(
        db_session.scalars(
            select(OperationResponsibleAssignment).where(OperationResponsibleAssignment.responsible_name == "Técnico Global")
        )
    )
    assert len(assignments) == 1
    assert assignments[0].team_model_id == model_id


def test_configuration_json_import_and_export(client):
    imported = client.post(
        "/api/operations/configuration-json",
        json={
            "schema_version": 1,
            "team_models": [
                {
                    "name": "IMPORTADO JSON",
                    "daily_target": 6,
                    "median_from_quantity": 4,
                    "good_from_quantity": 5,
                    "target_rules": [],
                }
            ],
            "team_members": [
                {"responsible_name": "Técnico JSON", "regional": "UNI - JARU", "team_model_name": "IMPORTADO JSON"}
            ],
            "subject_mappings": [],
            "saved_filters": [],
        },
    )
    assert imported.status_code == 200
    assert imported.json()["team_models"] == 1
    assert imported.json()["team_members"] == 1

    exported = client.get("/api/operations/configuration-json")
    assert exported.status_code == 200
    assert any(item["name"] == "IMPORTADO JSON" for item in exported.json()["team_models"])
    member = next(item for item in exported.json()["team_members"] if item["responsible_name"] == "Técnico JSON")
    assert member["team_model_name"] == "IMPORTADO JSON"


class FakeIxcClient:
    def __init__(self, order_record, reconciliation_record=None):
        self.order_record = order_record
        self.reconciliation_record = reconciliation_record
        self.calls: list[tuple[str, list[dict[str, str]] | None]] = []

    def list_all(self, table, *, grid_param=None, **kwargs):
        self.calls.append((table, grid_param, kwargs))
        if table == "su_oss_chamado":
            if self.reconciliation_record and any(
                part.get("TB") == "su_oss_chamado.id" for part in (grid_param or [])
            ):
                return iter([self.reconciliation_record])
            return iter([self.order_record])
        fixtures = {
            "su_ticket": [{"id": "70", "id_usuarios": "80"}],
            "usuarios": [{"id": "80", "nome": "Criador Teste"}],
            "su_oss_assunto": [{"id": "10", "assunto": "Suporte Externo Fibra Urbana", "meta_horas_abertura": "24"}],
            "su_diagnostico": [{"id": "20", "descricao": "Conector danificado"}],
            "funcionarios": [{"id": "30", "funcionario": "Técnico Teste"}],
            "empresa_setor": [{"id": "9", "setor": "Suporte Externo Fibra"}],
            "cliente": [{"id": "40", "razao": "Cliente Teste", "id_cidade": "60", "tipo_pessoa": "F"}],
            "radusuarios": [{"id": "50", "login": "cliente.teste", "id_contrato": "900"}],
            "cidade": [{"id": "60", "nome": "Ji-Paraná", "uf": "26"}],
            "uf": [{"id": "26", "nome": "Estado de Rondônia", "sigla": "RO"}],
            "cliente_contrato": [{"id": "900", "contrato": "Uni Fibra 350 MEGA"}],
        }
        return iter(fixtures.get(table, []))


def test_ixc_analytics_import_queries_only_period_and_targeted_lookup_ids(db_session, admin_user):
    date_from, _ = current_month_bounds()
    date_to = date_from
    opened = datetime.combine(date_from, time(hour=8)).strftime("%Y-%m-%d %H:%M:%S")
    closed = datetime.combine(date_from, time(hour=10)).strftime("%Y-%m-%d %H:%M:%S")
    fake_client = FakeIxcClient(
        {
            "id": "123",
            "protocolo": "PROTO-123",
            "id_filial": "6",
            "id_assunto": "10",
            "id_su_diagnostico": "20",
            "id_tecnico": "30",
            "id_ticket": "70",
            "setor": "9",
            "id_cliente": "40",
            "id_login": "50",
            "status": "F",
            "data_abertura": opened,
            "data_hora_assumido": opened,
            "data_hora_execucao": opened,
            "data_inicio": opened,
            "data_final": closed,
            "data_fechamento": closed,
            "ultima_atualizacao": closed,
        }
    )

    result = import_current_month_period(
        db_session,
        fake_client,
        date_from=date_from,
        date_to=date_to,
        imported_by=admin_user.id,
        sector_ids=["7", "8", "9"],
    )

    assert result["fetched_count"] == 1
    assert result["created_count"] == 1
    imported = db_session.scalar(select(OperationOrder).where(OperationOrder.source_order_id == "123"))
    assert imported is not None
    assert imported.regional == "UNI - JI PARANA"
    assert imported.city == "Ji-Paraná"
    assert imported.state == "RO"
    assert imported.person_type == "Pessoa Física"
    assert imported.contract_type == "Uni Fibra 350 MEGA"
    assert imported.creator == "Criador Teste"
    assert imported.sla_status == "on_time"
    assert imported.assumed_at is not None
    assert imported.displacement_started_at is not None
    assert imported.execution_started_at is not None
    assert imported.finished_at == imported.closed_at

    os_calls = [call for call in fake_client.calls if call[0] == "su_oss_chamado"]
    assert len(os_calls) == 2
    assert all(call[1] for call in os_calls)
    assert all(call[2]["max_records"] == 3_000 for call in os_calls)
    assert all(any(part["TB"] == "su_oss_chamado.setor" and part["P"] == "7,8,9" for part in call[1]) for call in os_calls)
    support_calls = [call for call in fake_client.calls if call[0] != "su_oss_chamado"]
    assert support_calls
    assert all(call[1] and call[1][0]["OP"] == "IN" for call in support_calls)
    assert all(call[2]["max_records"] == 200 for call in support_calls)


def test_ixc_import_populates_neighborhood_and_coordinates_confirmed_against_real_sample(db_session, admin_user):
    """Item 3: bairro/latitude/longitude confirmados como campos separados numa amostra real de
    104k+ O.S. já importadas (ver migration 20260811_0048) - a ingestão precisa popular as três
    colunas novas de OperationOrder a partir dessas chaves. Latitude usa vírgula como separador
    decimal (achado real, confirmado em 177 das O.S. da amostra) - `_float_or_none` já converte."""
    date_from, _ = current_month_bounds()
    opened = datetime.combine(date_from, time(hour=8)).strftime("%Y-%m-%d %H:%M:%S")
    fake_client = FakeIxcClient(
        {
            "id": "555",
            "protocolo": "PROTO-555",
            "id_filial": "6",
            "id_assunto": "10",
            "id_su_diagnostico": "20",
            "id_tecnico": "30",
            "id_ticket": "70",
            "setor": "9",
            "id_cliente": "40",
            "id_login": "50",
            "status": "A",
            "data_abertura": opened,
            "bairro": "Nova Brasília",
            "latitude": "-9,2306221",
            "longitude": "-61,9940897",
        }
    )

    import_current_month_period(
        db_session, fake_client, date_from=date_from, date_to=date_from, imported_by=admin_user.id, sector_ids=["7", "8", "9"],
    )

    imported = db_session.scalar(select(OperationOrder).where(OperationOrder.source_order_id == "555"))
    assert imported is not None
    assert imported.neighborhood == "Nova Brasília"
    assert imported.latitude == pytest.approx(-9.2306221)
    assert imported.longitude == pytest.approx(-61.9940897)


def test_sla_target_change_bumps_source_updated_at_even_without_ixc_timestamp_change(db_session, admin_user):
    """sla_status/sla_target_hours/elapsed_hours sao derivados da meta de horas do ASSUNTO atual,
    nao de um campo proprio da O.S - se a meta muda na IXC, uma O.S ja fechada ha muito tempo pode
    ser recalculada sem que seu proprio "ultima_atualizacao" mude. sync_service_orders_from_operations
    usa source_updated_at como cursor incremental, entao sem este ajuste o ServiceOrder usado para
    pontuar/pagar ficaria com o SLA desatualizado para sempre."""
    date_from, _ = current_month_bounds()
    opened = datetime.combine(date_from, time(hour=8)).strftime("%Y-%m-%d %H:%M:%S")
    closed = datetime.combine(date_from, time(hour=10)).strftime("%Y-%m-%d %H:%M:%S")
    record = {
        "id": "999",
        "protocolo": "PROTO-999",
        "id_filial": "6",
        "id_assunto": "10",
        "id_su_diagnostico": "20",
        "id_tecnico": "30",
        "id_ticket": "70",
        "setor": "9",
        "id_cliente": "40",
        "id_login": "50",
        "status": "F",
        "data_abertura": opened,
        "data_hora_assumido": opened,
        "data_hora_execucao": opened,
        "data_inicio": opened,
        "data_final": closed,
        "data_fechamento": closed,
        "ultima_atualizacao": closed,
    }
    fake_client = FakeIxcClient(dict(record))
    import_current_month_period(
        db_session, fake_client, date_from=date_from, date_to=date_from,
        imported_by=admin_user.id, sector_ids=["7", "8", "9"],
    )
    imported = db_session.scalar(select(OperationOrder).where(OperationOrder.source_order_id == "999"))
    assert imported.sla_target_hours == 24.0
    assert imported.sla_status == "on_time"
    original_cursor = imported.source_updated_at

    class StaleMetaIxcClient(FakeIxcClient):
        def list_all(self, table, *, grid_param=None, **kwargs):
            self.calls.append((table, grid_param, kwargs))
            if table == "su_oss_assunto":
                return iter([{"id": "10", "assunto": "Suporte Externo Fibra Urbana", "meta_horas_abertura": "1"}])
            return super().list_all(table, grid_param=grid_param, **kwargs)

    stale_meta_client = StaleMetaIxcClient(dict(record))
    import_current_month_period(
        db_session, stale_meta_client, date_from=date_from, date_to=date_from,
        imported_by=admin_user.id, sector_ids=["7", "8", "9"],
    )
    db_session.refresh(imported)
    assert imported.sla_target_hours == 1.0
    assert imported.sla_status == "out_of_time"
    assert imported.source_updated_at > original_cursor


def test_ixc_open_backlog_import_is_partitioned_by_sector_and_status(db_session, admin_user):
    date_from, _ = current_month_bounds()
    opened = datetime.combine(date_from, time(hour=8)).strftime("%Y-%m-%d %H:%M:%S")
    fake_client = FakeIxcClient(
        {
            "id": "backlog-123",
            "id_filial": "6",
            "id_assunto": "10",
            "id_su_diagnostico": "20",
            "id_tecnico": "30",
            "setor": "9",
            "id_cliente": "40",
            "id_login": "50",
            "status": "A",
            "data_abertura": opened,
            "ultima_atualizacao": opened,
        }
    )

    result = import_open_backlog(
        db_session,
        fake_client,
        imported_by=admin_user.id,
        sector_ids=["7", "8", "9"],
    )

    assert result["fetched_count"] == 1
    assert result["created_count"] == 1
    os_calls = [call for call in fake_client.calls if call[0] == "su_oss_chamado"]
    assert len(os_calls) == 3 * len(OPEN_BACKLOG_STATUS_CODES)
    observed_statuses = set()
    observed_sectors = set()
    for _, grid, kwargs in os_calls:
        assert kwargs["max_records"] == 3_000
        assert grid
        status_filter = next(part for part in grid if part["TB"] == "su_oss_chamado.status")
        sector_filter = next(part for part in grid if part["TB"] == "su_oss_chamado.setor")
        assert status_filter["OP"] == "="
        assert sector_filter["OP"] == "="
        observed_statuses.add(status_filter["P"])
        observed_sectors.add(sector_filter["P"])
    assert observed_statuses == set(OPEN_BACKLOG_STATUS_CODES)
    assert observed_sectors == {"7", "8", "9"}


def test_ixc_open_backlog_reconciles_previously_open_ids_that_are_now_closed(db_session, admin_user):
    date_from, _ = current_month_bounds()
    opened = datetime.combine(date_from, time(hour=8)).strftime("%Y-%m-%d %H:%M:%S")
    closed = datetime.combine(date_from, time(hour=10)).strftime("%Y-%m-%d %H:%M:%S")
    stale = OperationOrder(
        source="ixc",
        source_order_id="999",
        order_code="IXC-999",
        regional="UNI - JI PARANA",
        sector="Suporte Externo",
        status="Aberta",
        status_code="A",
        is_closed=False,
        sla_status="out_of_time",
        opened_at=_utc_at(date_from, 8),
        raw_payload={},
    )
    db_session.add(stale)
    db_session.flush()
    fake_client = FakeIxcClient(
        {
            "id": "123",
            "id_filial": "6",
            "id_assunto": "10",
            "id_tecnico": "30",
            "setor": "7",
            "status": "A",
            "data_abertura": opened,
        },
        reconciliation_record={
            "id": "999",
            "id_filial": "6",
            "id_assunto": "10",
            "id_tecnico": "30",
            "setor": "7",
            "status": "F",
            "data_abertura": opened,
            "data_fechamento": closed,
        },
    )

    import_open_backlog(
        db_session,
        fake_client,
        imported_by=admin_user.id,
        sector_ids=["7", "8", "9"],
    )

    db_session.refresh(stale)
    assert stale.is_closed is True
    assert stale.status == "Finalizada"
    assert stale.closed_at is not None
    reconciliation_calls = [
        call for call in fake_client.calls
        if call[0] == "su_oss_chamado"
        and any(part.get("TB") == "su_oss_chamado.id" for part in (call[1] or []))
    ]
    assert len(reconciliation_calls) == 1
    assert reconciliation_calls[0][1][0]["P"] == "999"


def test_operations_import_endpoint_requires_daily_batches(client):
    date_from, _ = current_month_bounds()
    date_to = date_from.fromordinal(date_from.toordinal() + 1)

    response = client.post(
        "/api/operations/imports",
        json={"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
    )

    assert response.status_code == 422
    assert "um dia por vez" in response.json()["detail"]


class OversizedIxcClient(IxcClient):
    def __init__(self):
        pass

    def list(self, table, **kwargs):
        return IxcPage(records=[{"id": "1"}], total=3_001, page=1)


def test_ixc_client_aborts_before_paginating_oversized_filtered_query():
    client = OversizedIxcClient()

    with pytest.raises(IxcQueryLimitError, match="3001"):
        list(client.list_all("su_oss_chamado", max_records=3_000))


def test_ixc_client_turns_non_json_response_into_safe_api_error(monkeypatch):
    def fake_post(*args, **kwargs):
        return type(
            "NonJsonResponse",
            (),
            {
                "status_code": 200,
                "headers": {"content-type": "text/html; charset=UTF-8"},
                "raise_for_status": lambda self: None,
                "json": lambda self: (_ for _ in ()).throw(ValueError("invalid json")),
            },
        )()

    monkeypatch.setattr("app.services.ixc_client.httpx.post", fake_post)
    client = IxcClient("https://ixc.example.test", "token")

    with pytest.raises(IxcApiError, match="formato inválido"):
        client.list("su_oss_chamado")


def test_operations_backfill_is_daily_auditable_and_resumable(db_session, monkeypatch):
    from app.modules.operations import backfill

    date_from, _ = current_month_bounds()
    date_to = date_from.fromordinal(date_from.toordinal() + 2)
    processed_days = []

    monkeypatch.setattr(backfill, "get_ixc_client", lambda: object())

    def fake_import(db, client, *, date_from, date_to, imported_by, sector_ids):
        processed_days.append(date_from)
        return {
            "fetched_count": 10,
            "created_count": 4,
            "updated_count": 3,
            "unchanged_count": 3,
            "rejected_count": 0,
            "errors": [],
        }

    monkeypatch.setattr(backfill, "import_current_month_period", fake_import)
    job = backfill.run_backfill(
        db_session,
        date_from=date_from,
        date_to=date_to,
        sector_ids=["7", "8", "9"],
        delay_seconds=0,
    )

    assert job.status == "completed"
    assert job.processed_days == 3
    assert job.fetched_count == 30
    assert job.created_count == 12
    assert processed_days == [date_from, date_from.fromordinal(date_from.toordinal() + 1), date_to]

    resumed = backfill.run_backfill(
        db_session,
        date_from=date_from,
        date_to=date_to,
        sector_ids=["7", "8", "9"],
        resume_job_id=job.id,
        delay_seconds=0,
    )
    assert resumed.id == job.id
    assert processed_days == [date_from, date_from.fromordinal(date_from.toordinal() + 1), date_to]
