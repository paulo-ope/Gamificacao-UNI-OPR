from datetime import datetime, timezone

from app.models import Collaborator, User
from app.modules.management.models import ManagementOperationalMember
from app.modules.operations.models import OperationOrder, OperationResponsibleAssignment, OperationTeamModel


def test_management_refresh_creates_operational_member_from_assignment(client, db_session):
    supervisor = User(name="Supervisora", email="supervisora@pytest.local", role="operator", active=True, password_hash="x")
    model = OperationTeamModel(name="Suporte Moto", daily_target=5, active=True)
    collaborator = Collaborator(
        name="Joao Operacao",
        role="Tecnico",
        regional="UNI JARU",
        active=True,
        is_registered=True,
        ixc_employee_id=123,
    )
    db_session.add_all([supervisor, model, collaborator])
    db_session.flush()
    db_session.add(
        OperationResponsibleAssignment(
            responsible_name="Joao Operacao",
            regional="UNI JARU",
            team_model_id=model.id,
        )
    )
    db_session.add(
        OperationOrder(
            source="ixc",
            source_order_id="OS-1",
            order_code="OS-1",
            regional="UNI JARU",
            os_type="Suporte",
            os_subject="Fibra",
            responsible="Joao Operacao",
            responsible_ixc_id=123,
            opened_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
            raw_payload={},
        )
    )
    db_session.commit()

    response = client.post("/api/management/structure/refresh")

    assert response.status_code == 200
    member = db_session.query(ManagementOperationalMember).one()
    assert member.responsible_name == "Joao Operacao"
    assert member.team_model_id == model.id
    assert member.collaborator_id == collaborator.id
    assert member.ixc_employee_id == 123


def test_management_refresh_uses_admin_structure_supervisor(client, db_session):
    supervisor = User(name="Supervisora Admin", email="supervisora.admin@pytest.local", role="operator", active=True, password_hash="x")
    collaborator = Collaborator(
        name="Ana Campo",
        role="Tecnica",
        regional="UNI JARU",
        active=True,
        is_registered=True,
        supervisor_user_id=None,
        team_type="field",
        structure_status="validated",
    )
    db_session.add_all([supervisor, collaborator])
    db_session.flush()
    collaborator.supervisor_user_id = supervisor.id
    db_session.add(
        OperationOrder(
            source="ixc",
            source_order_id="OS-ADMIN-1",
            order_code="OS-ADMIN-1",
            regional="UNI JARU",
            os_type="Suporte",
            os_subject="Fibra",
            responsible="Ana Campo",
            opened_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
            raw_payload={},
        )
    )
    db_session.commit()

    response = client.post("/api/management/structure/refresh")

    assert response.status_code == 200
    member = db_session.query(ManagementOperationalMember).one()
    assert member.supervisor_user_id == supervisor.id
    assert member.status == "without_team_model"

    dashboard = client.get("/api/management/dashboard")
    body = dashboard.json()["members"][0]
    assert body["collaborator_team_type"] == "field"
    assert body["collaborator_structure_status"] == "validated"
    assert body["collaborator_supervisor_name"] == "Supervisora Admin"


def test_management_dashboard_reports_missing_supervisor_and_model(client, db_session):
    db_session.add(
        ManagementOperationalMember(
            responsible_name="Maria Campo",
            regional="UNI JARU",
            status="pending_validation",
            source="orders",
        )
    )
    db_session.commit()

    response = client.get("/api/management/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total_members"] == 1
    assert payload["summary"]["without_supervisor"] == 1
    assert payload["summary"]["without_team_model"] == 1
    assert payload["summary"]["without_gamification"] == 1
    assert payload["members"][0]["alerts"]


def test_management_member_update_sets_supervisor_model_and_status(client, db_session):
    supervisor = User(name="Supervisor", email="sup@pytest.local", role="operator", active=True, password_hash="x")
    model = OperationTeamModel(name="Suporte Carro", daily_target=6, active=True)
    member = ManagementOperationalMember(
        responsible_name="Carlos Campo",
        regional="UNI JARU",
        status="pending_validation",
        source="orders",
    )
    db_session.add_all([supervisor, model, member])
    db_session.commit()

    response = client.patch(
        f"/api/management/members/{member.id}",
        json={
            "supervisor_user_id": supervisor.id,
            "team_model_id": model.id,
            "status": "active_management",
        },
    )

    assert response.status_code == 200
    db_session.refresh(member)
    assert member.supervisor_user_id == supervisor.id
    assert member.team_model_id == model.id
    assert member.status == "active_management"
    assert member.validated_by is not None
