"""Exclusão de geração de caso (colaborador/regional, período opcional) - pedido do usuário em
2026-09-21: suspender a cobrança automática E manual pra um colaborador específico (permanente ou
só num período de férias/atestado) ou pra uma regional inteira, sem precisar mudar o modelo de
equipe inteiro (`OperationTeamModel.requires_justification`, afeta todo mundo que usa ele) nem
desativar o cadastro do colaborador (remove ele de tudo, não só da cobrança).

Cobre os dois caminhos que abrem um caso: a geração automática em lote
(`generate_daily_cases_for_date`/`generate_performance_cases`) e a abertura manual sob demanda
(`active_generation_exclusion_for_daily_request`/`_monthly_request`, checados por
`POST /cases/daily`/`/cases/monthly` em router.py antes de chamar `get_or_create_*`)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.security import get_current_user
from app.db.session import get_db
from app.main import app
from app.models import User
from app.modules.management import cases as cases_engine
from app.modules.management.models import (
    ManagementCase,
    ManagementCaseGenerationExclusion,
    ManagementOperationalMember,
)
from app.modules.operations.models import OperationOrder, OperationTeamModel

YEAR, MONTH = 2026, 7
MONDAY = date(2026, 7, 6)  # date(2026, 7, 6).weekday() == 0


def _order(responsible: str, regional: str, day: int, index: int = 0) -> OperationOrder:
    closed = datetime(YEAR, MONTH, day, 15, 0, tzinfo=timezone.utc)
    return OperationOrder(
        source="ixc",
        source_order_id=f"OS-{responsible}-{day}-{index}",
        order_code=f"OS-{responsible}-{day}-{index}",
        regional=regional,
        os_type="Suporte",
        os_subject="Fibra",
        responsible=responsible,
        opened_at=closed,
        closed_at=closed,
        is_closed=True,
        raw_payload={},
    )


@pytest.fixture()
def setup(db_session):
    model = OperationTeamModel(name="Suporte Moto", daily_target=5, median_from_quantity=3, good_from_quantity=4, active=True)
    db_session.add(model)
    db_session.flush()
    member = ManagementOperationalMember(
        responsible_name="Joao Campo", regional="UNI JARU", team_model_id=model.id,
        status="validated_operation", is_active=True,
    )
    db_session.add(member)
    db_session.commit()
    return {"model": model, "member": member}


# --- Geração automática mensal -------------------------------------------------------------------


def test_monthly_generation_skips_member_excluded_permanently(db_session, setup):
    for day in range(1, 3):
        db_session.add(_order("Joao Campo", "UNI JARU", day, 0))
    db_session.add(
        ManagementCaseGenerationExclusion(
            scope_type="member", member_id=setup["member"].id, reason="Desligamento em curso.",
        )
    )
    db_session.flush()

    result = cases_engine.generate_performance_cases(db_session, year=YEAR, month=MONTH)

    assert result["created_cases"] == 0
    assert result["excluded_members"] == 1
    assert db_session.query(ManagementCase).count() == 0


def test_monthly_generation_skips_member_excluded_for_an_overlapping_window(db_session, setup):
    """Exclusão de férias que cobre só uma FATIA do mês - decisão conservadora: qualquer
    sobreposição já é motivo pra pular o mês inteiro, em vez de exigir cobertura total."""
    for day in range(1, 7):
        for index in range(2):
            db_session.add(_order("Joao Campo", "UNI JARU", day, index))
    db_session.add(
        ManagementCaseGenerationExclusion(
            scope_type="member",
            member_id=setup["member"].id,
            date_from=date(YEAR, MONTH, 5),
            date_to=date(YEAR, MONTH, 10),
            reason="Férias.",
        )
    )
    db_session.flush()

    result = cases_engine.generate_performance_cases(db_session, year=YEAR, month=MONTH)

    assert result["created_cases"] == 0
    assert result["excluded_members"] == 1


def test_monthly_generation_ignores_exclusion_outside_its_date_window(db_session, setup):
    for day in range(1, 7):
        for index in range(2):
            db_session.add(_order("Joao Campo", "UNI JARU", day, index))
    db_session.add(
        ManagementCaseGenerationExclusion(
            scope_type="member",
            member_id=setup["member"].id,
            date_from=date(YEAR, MONTH - 1, 1),
            date_to=date(YEAR, MONTH - 1, 28),
            reason="Férias do mês anterior.",
        )
    )
    db_session.flush()

    result = cases_engine.generate_performance_cases(db_session, year=YEAR, month=MONTH)

    assert result["created_cases"] == 1
    assert result["excluded_members"] == 0


def test_monthly_generation_ignores_an_inactive_exclusion(db_session, setup):
    for day in range(1, 7):
        for index in range(2):
            db_session.add(_order("Joao Campo", "UNI JARU", day, index))
    db_session.add(
        ManagementCaseGenerationExclusion(
            scope_type="member", member_id=setup["member"].id, reason="Motivo qualquer.", active=False,
        )
    )
    db_session.flush()

    result = cases_engine.generate_performance_cases(db_session, year=YEAR, month=MONTH)

    assert result["created_cases"] == 1


def test_monthly_generation_skips_member_via_regional_exclusion(db_session, setup):
    for day in range(1, 3):
        db_session.add(_order("Joao Campo", "UNI JARU", day, 0))
    db_session.add(
        ManagementCaseGenerationExclusion(
            scope_type="regional", regional="UNI JARU", reason="Filial nova, estrutura ainda não validada.",
        )
    )
    db_session.flush()

    result = cases_engine.generate_performance_cases(db_session, year=YEAR, month=MONTH)

    assert result["created_cases"] == 0
    assert result["excluded_members"] == 1


def test_monthly_generation_regional_exclusion_does_not_affect_other_regionals(db_session, setup):
    other_model = OperationTeamModel(name="Suporte Ariquemes", daily_target=5, median_from_quantity=3, good_from_quantity=4, active=True)
    db_session.add(other_model)
    db_session.flush()
    db_session.add(
        ManagementOperationalMember(
            responsible_name="Maria Souza", regional="UNI ARIQUEMES", team_model_id=other_model.id,
            status="validated_operation", is_active=True,
        )
    )
    for day in range(1, 3):
        db_session.add(_order("Joao Campo", "UNI JARU", day, 0))
    for day in range(1, 7):
        for index in range(2):
            db_session.add(_order("Maria Souza", "UNI ARIQUEMES", day, index))
    db_session.add(
        ManagementCaseGenerationExclusion(scope_type="regional", regional="UNI JARU", reason="Motivo.")
    )
    db_session.flush()

    result = cases_engine.generate_performance_cases(db_session, year=YEAR, month=MONTH)

    assert result["excluded_members"] == 1
    assert result["created_cases"] == 1
    remaining = db_session.query(ManagementCase).one()
    assert remaining.responsible_name == "Maria Souza"


# --- Geração automática diária -------------------------------------------------------------------


def test_daily_generation_skips_member_excluded_for_that_day(db_session, setup):
    result = cases_engine.generate_daily_cases_for_date(db_session, day=MONDAY)
    assert result["created_cases"] == 1  # sanity: sem exclusão, produção zero abre caso.
    db_session.query(ManagementCase).delete()
    db_session.commit()

    db_session.add(
        ManagementCaseGenerationExclusion(
            scope_type="member",
            member_id=setup["member"].id,
            date_from=MONDAY,
            date_to=MONDAY,
            reason="Atestado médico.",
        )
    )
    db_session.flush()

    result = cases_engine.generate_daily_cases_for_date(db_session, day=MONDAY)

    assert result["created_cases"] == 0
    assert result["excluded_members"] == 1
    assert db_session.query(ManagementCase).count() == 0


def test_daily_generation_still_evaluates_the_day_after_the_exclusion_window(db_session, setup):
    db_session.add(
        ManagementCaseGenerationExclusion(
            scope_type="member",
            member_id=setup["member"].id,
            date_from=MONDAY,
            date_to=MONDAY,
            reason="Atestado médico de 1 dia.",
        )
    )
    db_session.flush()

    next_day = MONDAY + timedelta(days=1)
    result = cases_engine.generate_daily_cases_for_date(db_session, day=next_day)

    assert result["created_cases"] == 1
    assert result["excluded_members"] == 0


# --- Bloqueio da abertura MANUAL (POST /cases/daily e /cases/monthly) ----------------------------


def test_manual_daily_request_is_blocked_by_an_active_exclusion(db_session, setup):
    db_session.add(
        ManagementCaseGenerationExclusion(scope_type="member", member_id=setup["member"].id, reason="Férias.")
    )
    db_session.commit()

    exclusion = cases_engine.active_generation_exclusion_for_daily_request(
        db_session, responsible_name="Joao Campo", regional="UNI JARU", day=MONDAY
    )

    assert exclusion is not None
    assert exclusion.reason == "Férias."


def test_manual_monthly_request_is_blocked_by_an_active_exclusion(db_session, setup):
    db_session.add(
        ManagementCaseGenerationExclusion(scope_type="regional", regional="UNI JARU", reason="Incidente regional.")
    )
    db_session.commit()

    exclusion = cases_engine.active_generation_exclusion_for_monthly_request(
        db_session, responsible_name="Joao Campo", regional="UNI JARU", reference_year=YEAR, reference_month=MONTH
    )

    assert exclusion is not None


def test_manual_request_is_not_blocked_without_a_matching_exclusion(db_session, setup):
    assert cases_engine.active_generation_exclusion_for_daily_request(
        db_session, responsible_name="Joao Campo", regional="UNI JARU", day=MONDAY
    ) is None
    assert cases_engine.active_generation_exclusion_for_monthly_request(
        db_session, responsible_name="Joao Campo", regional="UNI JARU", reference_year=YEAR, reference_month=MONTH
    ) is None


# --- CRUD via API (permissão management:admin) ---------------------------------------------------


def _client_as(db_session, user: User):
    from fastapi.testclient import TestClient

    def _override_db():
        yield db_session

    def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return TestClient(app)


def test_create_exclusion_requires_management_admin(db_session, setup):
    viewer = User(name="Visualizador", email="viewer.excl@pytest.local", role="viewer", active=True, password_hash="x")
    db_session.add(viewer)
    db_session.commit()

    try:
        client = _client_as(db_session, viewer)
        response = client.post(
            "/api/management/case-generation-exclusions",
            json={"scope_type": "member", "member_id": setup["member"].id, "reason": "Motivo qualquer aqui."},
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_create_and_list_member_exclusion(db_session, setup):
    admin = User(name="Admin", email="admin.excl@pytest.local", role="admin", active=True, password_hash="x")
    db_session.add(admin)
    db_session.commit()

    try:
        client = _client_as(db_session, admin)
        create_response = client.post(
            "/api/management/case-generation-exclusions",
            json={"scope_type": "member", "member_id": setup["member"].id, "reason": "Férias programadas."},
        )
        assert create_response.status_code == 201
        body = create_response.json()
        assert body["member_responsible_name"] == "Joao Campo"
        assert body["active"] is True

        list_response = client.get("/api/management/case-generation-exclusions")
        assert list_response.status_code == 200
        assert len(list_response.json()) == 1

        patch_response = client.patch(
            f"/api/management/case-generation-exclusions/{body['id']}", json={"active": False}
        )
        assert patch_response.status_code == 200
        assert patch_response.json()["active"] is False

        empty_response = client.get("/api/management/case-generation-exclusions")
        assert empty_response.json() == []
    finally:
        app.dependency_overrides.clear()


def test_create_exclusion_rejects_mismatched_scope_fields(db_session, setup):
    admin = User(name="Admin", email="admin.excl2@pytest.local", role="admin", active=True, password_hash="x")
    db_session.add(admin)
    db_session.commit()

    try:
        client = _client_as(db_session, admin)
        response = client.post(
            "/api/management/case-generation-exclusions",
            json={"scope_type": "member", "regional": "UNI JARU", "reason": "Sem member_id, com regional."},
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
