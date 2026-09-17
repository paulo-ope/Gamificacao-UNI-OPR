"""P0-1 da auditoria técnica de 2026-09-15 (`docs/auditoria-tecnica-geral-2026-09-15.md`):
`/users`, `/invites` e `/access-requests` só aceitavam o legado `users:manage`, uma família de
permissão diferente da que o catálogo do módulo Admin (`admin:users:read/write/delete`) e a tela
`/admin` realmente usam para decidir o que mostrar - um perfil de acesso montado só com
`admin:users:*` (exatamente o que o catálogo do módulo sugere ser suficiente) via a tela inteira,
mas toda chamada a `/users` batia em 403.

`require_any_permission` (app/core/security.py) resolve isso aceitando `users:manage` OU a
permissão `admin:users:*` equivalente. Estes testes travam que:
1. um perfil só com `admin:users:read/write` consegue usar `/users` de verdade;
2. a granularidade read/write/delete é respeitada (não vira um "libera tudo se tiver qualquer uma");
3. `users:manage` sozinho continua funcionando (não regride quem já dependia só dele);
4. a trava anti-lockout (`admin/router.py` e `admin/user_permissions_service.py`) agora protege
   também quem só tem `users:manage`, não só `admin:users:write`.
"""
from __future__ import annotations

from app.models import AccessProfile, AccessProfilePermission, User, UserAccessProfile
from app.modules.admin.router import _profile_delete_blocked_reason
from app.modules.admin.user_permissions_service import _would_orphan_admin_gatekeeper


def _assign_only(db_session, user: User, *permissions: str) -> None:
    """Substitui o(s) perfil(is) do usuário por um perfil novo, só com as permissões dadas -
    diferente do papel legado (`role="admin"`), que concede tudo de uma vez."""
    profile = AccessProfile(name=f"Teste {'/'.join(permissions)}", active=True, is_system=False)
    db_session.add(profile)
    db_session.flush()
    for permission in permissions:
        db_session.add(AccessProfilePermission(profile_id=profile.id, permission=permission))
    db_session.query(UserAccessProfile).filter(UserAccessProfile.user_id == user.id).delete(synchronize_session=False)
    db_session.add(UserAccessProfile(user_id=user.id, profile_id=profile.id))
    db_session.commit()


def test_admin_users_read_alone_can_list_users(client, db_session, admin_user):
    """O achado central do P0-1: perfil montado só com o catálogo do módulo Admin (sem o legado
    `users:manage`) precisa conseguir listar usuários - é exatamente a tela `/admin` quebrando."""
    _assign_only(db_session, admin_user, "admin:users:read")

    response = client.get("/api/users")

    assert response.status_code == 200, response.text


def test_admin_users_read_alone_cannot_write(client, db_session, admin_user):
    """Granularidade preservada: `admin:users:read` não deve liberar escrita."""
    _assign_only(db_session, admin_user, "admin:users:read")

    response = client.post(
        "/api/users",
        json={"name": "Novo", "email": "novo.p0@pytest.local", "password": "senha-forte-123", "role": "viewer", "active": True},
    )

    assert response.status_code == 403


def test_admin_users_write_alone_can_create_user(client, db_session, admin_user):
    _assign_only(db_session, admin_user, "admin:users:write")

    response = client.post(
        "/api/users",
        json={"name": "Novo", "email": "novo.p0.write@pytest.local", "password": "senha-forte-123", "role": "viewer", "active": True},
    )

    assert response.status_code == 201, response.text


def test_admin_users_write_alone_cannot_delete(client, db_session, admin_user):
    """Granularidade preservada: `admin:users:write` não deve liberar exclusão - só
    `admin:users:delete` (ou o legado `users:manage`)."""
    target = User(name="Alvo", email="alvo.p0@pytest.local", role="viewer", active=True, password_hash="x")
    db_session.add(target)
    db_session.flush()
    db_session.commit()
    _assign_only(db_session, admin_user, "admin:users:write")

    response = client.delete(f"/api/users/{target.id}")

    assert response.status_code == 403


def test_admin_users_delete_alone_can_delete_user(client, db_session, admin_user):
    target = User(name="Alvo", email="alvo.p0.delete@pytest.local", role="viewer", active=True, password_hash="x")
    db_session.add(target)
    db_session.flush()
    db_session.commit()
    _assign_only(db_session, admin_user, "admin:users:delete")

    response = client.delete(f"/api/users/{target.id}")

    assert response.status_code == 200, response.text


def test_legacy_users_manage_alone_still_works(client, db_session, admin_user):
    """Regressão: quem já dependia só do legado `users:manage` (sem nenhum `admin:users:*`) não
    pode perder acesso com esta mudança."""
    _assign_only(db_session, admin_user, "users:manage")

    response = client.get("/api/users")

    assert response.status_code == 200, response.text


def test_neither_permission_is_still_forbidden(client, db_session, admin_user):
    """Sem nenhuma das duas famílias, continua 403 - a mudança não abriu a rota geral."""
    _assign_only(db_session, admin_user, "audit:read")

    response = client.get("/api/users")

    assert response.status_code == 403


def test_invites_and_access_requests_accept_admin_users_permissions_too(client, db_session, admin_user):
    """Mesmo achado do P0-1 vale para `/invites` e `/access-requests` - não só `/users`."""
    _assign_only(db_session, admin_user, "admin:users:read")

    assert client.get("/api/invites").status_code == 200
    assert client.get("/api/access-requests").status_code == 200


def test_gatekeeper_lockout_guard_now_also_covers_legacy_users_manage(db_session, admin_user):
    """Antes do P0-1, a trava anti-lockout só olhava `admin:users:write` - dava pra tirar
    `users:manage` da última pessoa que o tinha sem aviso nenhum, mesmo sabendo que as rotas reais
    de `/users` aceitam esse legado. Isolado (sem TestClient) porque `_would_orphan_admin_gatekeeper`
    é a unidade certa para testar a regra em si, sem precisar do fluxo HTTP inteiro de override."""
    _assign_only(db_session, admin_user, "users:manage")

    assert _would_orphan_admin_gatekeeper(db_session, excluded_user_id=admin_user.id) is True


def test_gatekeeper_lockout_guard_sees_the_other_permission_as_a_safety_net(db_session, admin_user):
    """Sem órfão: mesmo perdendo `admin:users:write`, `users:manage` continua cobrindo - a trava não
    deve bloquear à toa quando a outra permissão da dupla ainda está de pé em outra pessoa."""
    _assign_only(db_session, admin_user, "admin:users:write")
    other = User(name="Outra Pessoa", email="outra.p0@pytest.local", role="viewer", active=True, password_hash="x")
    db_session.add(other)
    db_session.flush()
    _assign_only(db_session, other, "users:manage")

    assert _would_orphan_admin_gatekeeper(db_session, excluded_user_id=admin_user.id) is False


def test_profile_delete_guard_also_considers_legacy_users_manage(db_session):
    """Espelha o teste acima, mas no lado de PERFIL (admin/router.py), não de pessoa
    (user_permissions_service.py) - as duas travas foram generalizadas juntas."""
    profile = AccessProfile(name="Só Users Manage", active=True, is_system=False)
    db_session.add(profile)
    db_session.flush()
    db_session.add(AccessProfilePermission(profile_id=profile.id, permission="users:manage"))
    db_session.commit()

    reason = _profile_delete_blocked_reason(db_session, profile)

    assert reason is not None
    assert "users:manage" in reason
