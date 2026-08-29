"""Regression tests for backend/app/api/routes/users.py - focused on the new
users.collaborator_id link (identidade do portal): role allowlist now includes collaborator/
regional_manager_viewer, and the link must be validated (collaborator exists, one user per
collaborator)."""

from app.models import AuditLog, User


def test_create_user_accepts_collaborator_role(client):
    response = client.post(
        "/api/users",
        json={"name": "Colaborador Portal", "email": "portal1@pytest.local", "password": "x", "role": "collaborator", "active": True},
    )
    assert response.status_code == 201
    assert response.json()["role"] == "collaborator"


def test_create_user_rejects_unknown_role(client):
    response = client.post(
        "/api/users",
        json={"name": "Teste", "email": "invalido@pytest.local", "password": "x", "role": "superadmin", "active": True},
    )
    assert response.status_code == 422


def test_create_user_with_collaborator_id_links_and_appears_in_registry(client, make_collaborator):
    collaborator = make_collaborator(name="Fulano de Tal")
    response = client.post(
        "/api/users",
        json={
            "name": "Fulano de Tal",
            "email": "fulano@pytest.local",
            "password": "x",
            "role": "collaborator",
            "active": True,
            "collaborator_id": collaborator.id,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["collaborator_id"] == collaborator.id
    assert body["collaborator_name"] == "Fulano de Tal"

    registry = client.get("/api/collaborators/registry")
    registered = registry.json()["registered"]
    item = next(i for i in registered if i["id"] == collaborator.id)
    assert item["portal_user_id"] == body["id"]
    assert item["portal_user_email"] == "fulano@pytest.local"


def test_create_user_rejects_nonexistent_collaborator_id(client):
    response = client.post(
        "/api/users",
        json={"name": "Teste", "email": "semcolab@pytest.local", "password": "x", "role": "collaborator", "active": True, "collaborator_id": 999999},
    )
    assert response.status_code == 404


def test_create_user_rejects_collaborator_already_linked(client, make_collaborator):
    collaborator = make_collaborator()
    first = client.post(
        "/api/users",
        json={"name": "A", "email": "a@pytest.local", "password": "x", "role": "collaborator", "active": True, "collaborator_id": collaborator.id},
    )
    assert first.status_code == 201

    second = client.post(
        "/api/users",
        json={"name": "B", "email": "b@pytest.local", "password": "x", "role": "collaborator", "active": True, "collaborator_id": collaborator.id},
    )
    assert second.status_code == 409


def test_update_user_can_link_and_unlink_collaborator(client, make_collaborator):
    collaborator = make_collaborator()
    created = client.post(
        "/api/users",
        json={"name": "Ciclano", "email": "ciclano@pytest.local", "password": "x", "role": "viewer", "active": True},
    )
    user_id = created.json()["id"]

    linked = client.put(f"/api/users/{user_id}", json={"collaborator_id": collaborator.id})
    assert linked.status_code == 200
    assert linked.json()["collaborator_id"] == collaborator.id

    unlinked = client.put(f"/api/users/{user_id}", json={"collaborator_id": None})
    assert unlinked.status_code == 200
    assert unlinked.json()["collaborator_id"] is None


def test_update_user_rejects_linking_to_already_linked_collaborator(client, make_collaborator, db_session):
    collaborator = make_collaborator()
    owner = User(name="Dono", email="dono@pytest.local", role="collaborator", active=True, password_hash="x", collaborator_id=collaborator.id)
    db_session.add(owner)
    db_session.flush()

    other = client.post(
        "/api/users",
        json={"name": "Outro", "email": "outro@pytest.local", "password": "x", "role": "viewer", "active": True},
    )
    other_id = other.json()["id"]

    response = client.put(f"/api/users/{other_id}", json={"collaborator_id": collaborator.id})
    assert response.status_code == 409


def test_create_user_audit_log_never_stores_password_hash(client, db_session):
    response = client.post(
        "/api/users",
        json={"name": "Senha Segura", "email": "senha.segura@pytest.local", "password": "SenhaSecreta123", "role": "viewer", "active": True},
    )
    assert response.status_code == 201
    user_id = response.json()["id"]
    password_hash = db_session.get(User, user_id).password_hash

    entry = db_session.query(AuditLog).filter(AuditLog.action == "create", AuditLog.entity == "users", AuditLog.entity_id == str(user_id)).one()
    assert entry.before_data is None
    assert "password_hash" not in entry.after_data
    assert password_hash not in str(entry.after_data)


def test_update_user_audit_log_never_stores_password_hash(client, db_session):
    created = client.post(
        "/api/users",
        json={"name": "Antes da Troca", "email": "antes.troca@pytest.local", "password": "SenhaAntiga123", "role": "viewer", "active": True},
    )
    user_id = created.json()["id"]

    response = client.put(f"/api/users/{user_id}", json={"password": "SenhaNova456"})
    assert response.status_code == 200
    password_hash = db_session.get(User, user_id).password_hash

    entry = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "update", AuditLog.entity == "users", AuditLog.entity_id == str(user_id))
        .one()
    )
    assert "password_hash" not in entry.before_data
    assert "password_hash" not in entry.after_data
    assert password_hash not in str(entry.before_data) + str(entry.after_data)


def test_delete_user_audit_log_never_stores_password_hash(client, db_session, admin_user):
    created = client.post(
        "/api/users",
        json={"name": "Vai Ser Excluido", "email": "vai.ser.excluido@pytest.local", "password": "SenhaQueSai789", "role": "viewer", "active": True},
    )
    user_id = created.json()["id"]
    password_hash = db_session.get(User, user_id).password_hash

    response = client.delete(f"/api/users/{user_id}")
    assert response.status_code == 200

    entry = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "delete", AuditLog.entity == "users", AuditLog.entity_id == str(user_id))
        .one()
    )
    assert "password_hash" not in entry.before_data
    assert entry.after_data is None
    assert password_hash not in str(entry.before_data)
