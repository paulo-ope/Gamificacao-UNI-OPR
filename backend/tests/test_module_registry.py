from app.core.security import get_current_user
from app.main import app
from app.modules.registry import get_module, list_modules
from app.models import AccessProfile, AccessProfilePermission, User, UserAccessProfile, WorkspaceModuleVisibility


def _modules_visible_to(client, db_session, user):
    """Chama /workspace/modules autenticado como `user`, sem perder o override do admin do
    fixture `client` (que outros testes ainda vão usar depois)."""
    original_override = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        response = client.get("/api/workspace/modules")
    finally:
        if original_override is not None:
            app.dependency_overrides[get_current_user] = original_override
    return response


def test_module_registry_has_unique_stable_keys_and_paths():
    modules = list_modules()

    assert len({module.key for module in modules}) == len(modules)
    assert len({module.web_path for module in modules}) == len(modules)
    assert all(module.web_path.startswith("/") for module in modules)
    assert all(module.api_prefix.startswith("/api") for module in modules)


def test_operations_module_is_registered_and_active_after_mvp_foundation():
    operations = get_module("operations")

    assert operations is not None
    assert operations.status == "active"
    assert operations.required_permission == "operations:read"


def test_workspace_modules_respect_profile_visibility(client, db_session, admin_user):
    profile = AccessProfile(name="Agenda", active=True, is_system=False)
    db_session.add(profile)
    db_session.flush()
    db_session.add(AccessProfilePermission(profile_id=profile.id, permission="scheduling:read"))
    db_session.add(UserAccessProfile(user_id=admin_user.id, profile_id=profile.id))
    db_session.add(WorkspaceModuleVisibility(module_key="scheduling", profile_id=profile.id, visible=False))
    db_session.commit()

    response = client.get("/api/workspace/modules")

    assert response.status_code == 200
    assert "scheduling" not in {item["key"] for item in response.json()}


def test_admin_can_update_module_visibility(client, db_session):
    profile = AccessProfile(name="Operacao Restrita", active=True, is_system=False)
    db_session.add(profile)
    db_session.flush()

    response = client.put(
        "/api/admin/modules/operations/visibility",
        json={"profile_id": profile.id, "visible": False, "reason": "Perfil nao usa operacao"},
    )

    assert response.status_code == 200
    profile_row = next(item for item in response.json()["profiles"] if item["profile_id"] == profile.id)
    assert profile_row["visible"] is False


def test_user_override_hides_module_even_when_profile_allows_it(client, db_session, admin_user):
    target_user = User(name="Operador", email="operador@pytest.local", role="operator", active=True, password_hash="x")
    db_session.add(target_user)
    db_session.flush()
    profile = AccessProfile(name="Operacao Liberada", active=True, is_system=False)
    db_session.add(profile)
    db_session.flush()
    db_session.add(AccessProfilePermission(profile_id=profile.id, permission="operations:read"))
    db_session.add(UserAccessProfile(user_id=target_user.id, profile_id=profile.id))
    db_session.commit()

    response = client.put(
        "/api/admin/modules/operations/user-visibility",
        json={"user_id": target_user.id, "visible": False, "reason": "Usuario nao deve ver operacao"},
    )
    assert response.status_code == 200
    override = next(item for item in response.json()["user_overrides"] if item["user_id"] == target_user.id)
    assert override["visible"] is False

    modules_response = _modules_visible_to(client, db_session, target_user)
    assert modules_response.status_code == 200
    assert "operations" not in {item["key"] for item in modules_response.json()}


def test_user_override_shows_module_even_when_profile_hides_it(client, db_session, admin_user):
    target_user = User(name="Operador Agenda", email="operador-agenda@pytest.local", role="operator", active=True, password_hash="x")
    db_session.add(target_user)
    db_session.flush()
    profile = AccessProfile(name="Agenda Restrita", active=True, is_system=False)
    db_session.add(profile)
    db_session.flush()
    db_session.add(AccessProfilePermission(profile_id=profile.id, permission="scheduling:read"))
    db_session.add(UserAccessProfile(user_id=target_user.id, profile_id=profile.id))
    db_session.add(WorkspaceModuleVisibility(module_key="scheduling", profile_id=profile.id, visible=False))
    db_session.commit()

    response = client.put(
        "/api/admin/modules/scheduling/user-visibility",
        json={"user_id": target_user.id, "visible": True, "reason": "Excecao liberada"},
    )
    assert response.status_code == 200

    modules_response = _modules_visible_to(client, db_session, target_user)
    assert modules_response.status_code == 200
    assert "scheduling" in {item["key"] for item in modules_response.json()}

    delete_response = client.delete(f"/api/admin/modules/scheduling/user-visibility/{target_user.id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["user_overrides"] == []

    modules_after_delete = _modules_visible_to(client, db_session, target_user)
    assert "scheduling" not in {item["key"] for item in modules_after_delete.json()}
