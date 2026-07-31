from app.models import User


def test_admin_people_structure_lists_masked_cpf_and_pending_flags(client, make_collaborator, db_session):
    supervisor = User(name="Supervisor", email="supervisor@pytest.local", role="operator", active=True, password_hash="x")
    db_session.add(supervisor)
    collaborator = make_collaborator(name="Tecnico Campo", regional="UNI NORTE")
    collaborator.cpf = "12345678901"
    collaborator.team_type = "field"
    collaborator.employee_type = "field_technician"
    collaborator.supervisor_user_id = supervisor.id
    collaborator.structure_status = "validated"
    db_session.flush()

    response = client.get("/api/admin/people-structure")

    assert response.status_code == 200
    body = response.json()
    person = next(item for item in body["people"] if item["id"] == collaborator.id)
    assert person["cpf_masked"] == "***.***.***-01"
    assert person["supervisor_name"] == "Supervisor"
    assert body["summary"]["field_team"] >= 1


def test_admin_people_structure_update_validates_and_saves(client, make_collaborator, db_session):
    supervisor = User(name="Supervisor Dois", email="supervisor2@pytest.local", role="operator", active=True, password_hash="x")
    manager = User(name="Gerente", email="gerente@pytest.local", role="admin", active=True, password_hash="x")
    db_session.add_all([supervisor, manager])
    db_session.flush()
    collaborator = make_collaborator(name="Operador Agenda", regional="UNI SUL")

    response = client.patch(
        f"/api/admin/people-structure/{collaborator.id}",
        json={
            "cpf": "987.654.321-00",
            "employee_type": "scheduling_operator",
            "team_type": "scheduling",
            "supervisor_user_id": supervisor.id,
            "regional_manager_user_id": manager.id,
            "structure_status": "validated",
            "structure_notes": "Cadastro conferido",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["cpf_masked"] == "***.***.***-00"
    assert body["team_type"] == "scheduling"
    assert body["regional_manager_name"] == "Gerente"
    db_session.refresh(collaborator)
    assert collaborator.cpf == "98765432100"
