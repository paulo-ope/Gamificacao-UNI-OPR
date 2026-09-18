"""Permissão concedida ou negada diretamente numa pessoa, por cima do que o perfil dela dá.

Pedido do usuário (2026-09-09), depois da rodada anterior de Administração: dar (ou tirar) UMA
permissão específica de alguém sem precisar criar um perfil só para essa pessoa. `permissions_for_user`
(app/core/security.py) é a fonte única - perfil (ou papel legado) é a base, override soma ou
subtrai por cima, e negação sempre vence concessão do perfil.
"""
from __future__ import annotations

from app.core.security import permissions_for_user
from app.models import User
from app.modules.admin.user_permissions_service import ADMIN_GATEKEEPER_PERMISSION


def _make_user(db_session, *, name="Pessoa", email=None, role="viewer", active=True) -> User:
    user = User(
        name=name,
        email=email or f"{name.lower().replace(' ', '.')}@pytest.local",
        role=role,
        active=active,
        password_hash="x",
    )
    db_session.add(user)
    db_session.flush()
    return user


def test_grant_override_adds_a_permission_the_role_does_not_give(client, db_session):
    target = _make_user(db_session, role="viewer")
    db_session.commit()
    assert "operations:sync_ixc" not in permissions_for_user(target)

    response = client.put(f"/api/admin/users/{target.id}/permissions/operations:sync_ixc", json={"effect": "grant"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert "operations:sync_ixc" not in body["profile_permissions"], "a base (papel viewer) não muda"
    assert "operations:sync_ixc" in body["effective_permissions"]
    db_session.refresh(target)
    assert "operations:sync_ixc" in permissions_for_user(target)


def test_deny_override_removes_a_permission_the_role_gives(client, db_session):
    target = _make_user(db_session, role="viewer")
    db_session.commit()
    assert "operations:read" in permissions_for_user(target), "pré-condição: papel viewer já dá isto"

    response = client.put(f"/api/admin/users/{target.id}/permissions/operations:read", json={"effect": "deny"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert "operations:read" in body["profile_permissions"], "a base continua concedendo, no papel"
    assert "operations:read" not in body["effective_permissions"], "mas a negação individual vence"
    db_session.refresh(target)
    assert "operations:read" not in permissions_for_user(target)


def test_setting_override_twice_replaces_effect_instead_of_stacking(client, db_session):
    target = _make_user(db_session, role="viewer")
    db_session.commit()

    client.put(f"/api/admin/users/{target.id}/permissions/operations:sync_ixc", json={"effect": "grant"})
    second = client.put(f"/api/admin/users/{target.id}/permissions/operations:sync_ixc", json={"effect": "deny"})

    assert second.status_code == 200, second.text
    body = second.json()
    assert len(body["overrides"]) == 1
    assert body["overrides"][0]["effect"] == "deny"
    assert "operations:sync_ixc" not in body["effective_permissions"]


def test_removing_override_reverts_to_whatever_the_profile_gives(client, db_session):
    target = _make_user(db_session, role="viewer")
    db_session.commit()
    client.put(f"/api/admin/users/{target.id}/permissions/operations:sync_ixc", json={"effect": "grant"})

    response = client.delete(f"/api/admin/users/{target.id}/permissions/operations:sync_ixc")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["overrides"] == []
    assert "operations:sync_ixc" not in body["effective_permissions"]


def test_removing_an_override_that_does_not_exist_is_404(client, db_session):
    target = _make_user(db_session, role="viewer")
    db_session.commit()

    response = client.delete(f"/api/admin/users/{target.id}/permissions/operations:sync_ixc")

    assert response.status_code == 404


def test_invalid_permission_key_is_rejected(client, db_session):
    target = _make_user(db_session, role="viewer")
    db_session.commit()

    response = client.put(f"/api/admin/users/{target.id}/permissions/nao:existe", json={"effect": "grant"})

    assert response.status_code == 422
    assert "Permissão inválida" in response.json()["detail"]


def test_invalid_effect_is_rejected_by_schema(client, db_session):
    target = _make_user(db_session, role="viewer")
    db_session.commit()

    response = client.put(f"/api/admin/users/{target.id}/permissions/operations:read", json={"effect": "algo"})

    assert response.status_code == 422


def test_unknown_user_is_404(client):
    response = client.get("/api/admin/users/999999/permissions")

    assert response.status_code == 404


def test_reason_is_optional_and_stored(client, db_session):
    target = _make_user(db_session, role="viewer")
    db_session.commit()

    response = client.put(
        f"/api/admin/users/{target.id}/permissions/operations:sync_ixc",
        json={"effect": "grant", "reason": "Cobre férias do time de sync por 2 semanas."},
    )

    assert response.status_code == 200, response.text
    assert response.json()["overrides"][0]["reason"] == "Cobre férias do time de sync por 2 semanas."


def test_read_requires_admin_users_read(client, db_session, admin_user):
    from app.models import AccessProfile, AccessProfilePermission, UserAccessProfile

    target = _make_user(db_session, role="viewer")
    no_read = AccessProfile(name="Sem Leitura de Usuarios", active=True, is_system=False)
    db_session.add(no_read)
    db_session.flush()
    db_session.add(AccessProfilePermission(profile_id=no_read.id, permission="admin:permissions:read"))
    db_session.query(UserAccessProfile).filter(UserAccessProfile.user_id == admin_user.id).delete(synchronize_session=False)
    db_session.add(UserAccessProfile(user_id=admin_user.id, profile_id=no_read.id))
    db_session.commit()

    response = client.get(f"/api/admin/users/{target.id}/permissions")

    assert response.status_code == 403


def test_write_requires_admin_users_write(client, db_session, admin_user):
    from app.models import AccessProfile, AccessProfilePermission, UserAccessProfile

    target = _make_user(db_session, role="viewer")
    read_only = AccessProfile(name="Somente Leitura de Usuarios", active=True, is_system=False)
    db_session.add(read_only)
    db_session.flush()
    db_session.add(AccessProfilePermission(profile_id=read_only.id, permission="admin:users:read"))
    db_session.query(UserAccessProfile).filter(UserAccessProfile.user_id == admin_user.id).delete(synchronize_session=False)
    db_session.add(UserAccessProfile(user_id=admin_user.id, profile_id=read_only.id))
    db_session.commit()

    assert client.get(f"/api/admin/users/{target.id}/permissions").status_code == 200
    assert client.put(
        f"/api/admin/users/{target.id}/permissions/operations:sync_ixc", json={"effect": "grant"}
    ).status_code == 403


def test_last_admin_cannot_deny_their_own_gatekeeper_permission(client, db_session, admin_user):
    """`admin_user` (fixture) não tem perfil - tem `admin:users:write` só pelo papel legado
    ("admin"). Sem outra pessoa ativa que o conceda, negar deixaria ninguém administrando acesso."""
    response = client.put(
        f"/api/admin/users/{admin_user.id}/permissions/{ADMIN_GATEKEEPER_PERMISSION}",
        json={"effect": "deny"},
    )

    assert response.status_code == 409
    assert "ninguém que administre acessos" in response.json()["detail"]
    db_session.refresh(admin_user)
    assert ADMIN_GATEKEEPER_PERMISSION in permissions_for_user(admin_user)


def test_denying_gatekeeper_permission_is_allowed_when_another_admin_exists(client, db_session, admin_user):
    _make_user(db_session, name="Outro Admin", role="admin")
    db_session.commit()

    response = client.put(
        f"/api/admin/users/{admin_user.id}/permissions/{ADMIN_GATEKEEPER_PERMISSION}",
        json={"effect": "deny"},
    )

    assert response.status_code == 200, response.text
    db_session.refresh(admin_user)
    assert ADMIN_GATEKEEPER_PERMISSION not in permissions_for_user(admin_user)


def test_removing_the_last_grant_override_that_provides_gatekeeper_is_blocked(client, db_session, admin_user):
    """`the_only_admin` é viewer (o papel não dá admin:users:write) e só tem a permissão porque
    ganhou uma concessão individual. `admin_user` (fixture) é desativado para não contar como
    "outro administrador" - o mesmo estado de uma conta admin desligada de verdade."""
    the_only_admin = _make_user(db_session, name="Unico Admin", role="viewer")
    db_session.commit()
    granted = client.put(
        f"/api/admin/users/{the_only_admin.id}/permissions/{ADMIN_GATEKEEPER_PERMISSION}",
        json={"effect": "grant"},
    )
    assert granted.status_code == 200, granted.text

    admin_user.active = False
    db_session.commit()

    blocked = client.delete(f"/api/admin/users/{the_only_admin.id}/permissions/{ADMIN_GATEKEEPER_PERMISSION}")

    assert blocked.status_code == 409
    assert "ninguém que administre acessos" in blocked.json()["detail"]
    db_session.refresh(the_only_admin)
    assert ADMIN_GATEKEEPER_PERMISSION in permissions_for_user(the_only_admin)


def test_permission_catalog_reports_override_count(client, db_session):
    target = _make_user(db_session, role="viewer")
    db_session.commit()
    client.put(f"/api/admin/users/{target.id}/permissions/operations:sync_ixc", json={"effect": "grant"})

    catalog = client.get("/api/admin/permissions").json()
    entry = next(item for item in catalog if item["key"] == "operations:sync_ixc")

    assert entry["override_count"] == 1


def test_custom_permission_cannot_be_deleted_while_a_user_has_an_override(client, db_session):
    target = _make_user(db_session, role="viewer")
    db_session.commit()
    client.post(
        "/api/admin/permissions",
        json={"key": "localiza:qa_override_temp", "label": "QA: override temporário", "module_key": "localiza"},
    )
    client.put(f"/api/admin/users/{target.id}/permissions/localiza:qa_override_temp", json={"effect": "grant"})

    blocked = client.delete("/api/admin/permissions/localiza:qa_override_temp")
    assert blocked.status_code == 409
    assert target.name in blocked.json()["detail"]

    client.delete(f"/api/admin/users/{target.id}/permissions/localiza:qa_override_temp")
    freed = client.delete("/api/admin/permissions/localiza:qa_override_temp")
    assert freed.status_code == 204
