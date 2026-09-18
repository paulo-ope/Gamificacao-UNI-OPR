"""Perfil de acesso: remoção de permissão que fica de pé, e exclusão de perfil de verdade.

Dois achados reais (2026-09-09), a partir de "preciso poder excluir permissão" e "excluir perfil
de permissão tbm hoje nao consigo":

1. `ensure_access_profiles` roda a CADA start do backend e só adicionava (`permissions - existing`).
   Uma permissão removida na tela voltava sozinha no próximo restart do container - na prática,
   permissão de perfil de sistema não era removível, e nada na tela dizia isso.
2. Perfil de sistema não podia ser excluído (bloqueio explícito) e perfil comum vinculado a
   usuários respondia 409 sem oferecer saída nenhuma - não havia como desvincular pela tela.
"""
from __future__ import annotations

from sqlalchemy import select

from app.core.security import ROLE_PERMISSIONS, ensure_access_profiles
from app.models import AccessProfile, AccessProfilePermission, User, UserAccessProfile


def _profile(db_session, legacy_role: str) -> AccessProfile:
    return db_session.scalar(select(AccessProfile).where(AccessProfile.legacy_role == legacy_role))


def _permissions_of(profile: AccessProfile) -> set[str]:
    return {item.permission for item in profile.permissions}


def test_removed_permission_is_not_restored_by_the_next_startup(db_session):
    ensure_access_profiles(db_session)
    admin_profile = _profile(db_session, "admin")
    assert "management:review" in _permissions_of(admin_profile)

    db_session.query(AccessProfilePermission).filter(
        AccessProfilePermission.profile_id == admin_profile.id,
        AccessProfilePermission.permission == "management:review",
    ).delete(synchronize_session=False)
    db_session.commit()

    # Duas subidas seguidas: o bug antigo devolvia a permissão na primeira.
    ensure_access_profiles(db_session)
    ensure_access_profiles(db_session)
    db_session.refresh(admin_profile)

    assert "management:review" not in _permissions_of(admin_profile)


def test_a_brand_new_code_permission_still_reaches_existing_profiles(db_session, monkeypatch):
    """A contrapartida: semear uma vez não pode virar "nunca mais semeia nada".

    Módulo novo que entre em `ROLE_PERMISSIONS` precisa chegar aos perfis já existentes na primeira
    subida depois do deploy - é assim que `localiza:read` chegou ao perfil de admin desta instalação.
    """
    ensure_access_profiles(db_session)
    admin_profile = _profile(db_session, "admin")
    assert "modulo_novo:read" not in _permissions_of(admin_profile)

    monkeypatch.setitem(ROLE_PERMISSIONS, "admin", ROLE_PERMISSIONS["admin"] | {"modulo_novo:read"})
    ensure_access_profiles(db_session)
    db_session.refresh(admin_profile)

    assert "modulo_novo:read" in _permissions_of(admin_profile)


def test_deleted_system_profile_is_not_recreated_on_startup(db_session):
    ensure_access_profiles(db_session)
    viewer = _profile(db_session, "viewer")
    db_session.delete(viewer)
    db_session.commit()

    ensure_access_profiles(db_session)

    assert _profile(db_session, "viewer") is None


def test_system_profile_can_be_deleted_now(client, db_session):
    ensure_access_profiles(db_session)
    viewer = _profile(db_session, "viewer")

    response = client.delete(f"/api/admin/access-profiles/{viewer.id}")

    assert response.status_code == 200, response.text
    assert _profile(db_session, "viewer") is None


def test_profile_with_users_requires_a_destination_profile(client, db_session):
    ensure_access_profiles(db_session)
    source = AccessProfile(name="Perfil Origem", active=True, is_system=False)
    destination = AccessProfile(name="Perfil Destino", active=True, is_system=False)
    db_session.add_all([source, destination])
    db_session.flush()
    person = User(name="Pessoa", email="pessoa@pytest.local", role="viewer", active=True, password_hash="x")
    db_session.add(person)
    db_session.flush()
    db_session.add(UserAccessProfile(user_id=person.id, profile_id=source.id))
    db_session.commit()

    blocked = client.delete(f"/api/admin/access-profiles/{source.id}")
    assert blocked.status_code == 409
    assert "Escolha um perfil" in blocked.json()["detail"]

    moved = client.delete(f"/api/admin/access-profiles/{source.id}?reassign_profile_id={destination.id}")
    assert moved.status_code == 200, moved.text

    remaining = list(db_session.scalars(select(UserAccessProfile).where(UserAccessProfile.user_id == person.id)))
    assert [item.profile_id for item in remaining] == [destination.id]


def test_last_profile_that_administers_access_cannot_be_deleted(client, db_session):
    """Trava contra trancar o ecossistema por fora: se o último perfil ativo com
    `admin:users:write` fosse excluído, ninguém mais administraria acesso."""
    ensure_access_profiles(db_session)
    admin_profile = _profile(db_session, "admin")
    # Nenhum outro perfil de sistema concede admin:users:write, então este é o último.

    response = client.delete(f"/api/admin/access-profiles/{admin_profile.id}")

    assert response.status_code == 409
    assert "último perfil ativo" in response.json()["detail"]

    listed = client.get("/api/admin/access-profiles").json()
    row = next(item for item in listed if item["id"] == admin_profile.id)
    assert row["delete_blocked_reason"], "a tela precisa do motivo para explicar, não só esconder o botão"


def test_last_profile_that_administers_access_cannot_be_deactivated_either(client, db_session):
    """Inativar é o outro caminho para o mesmo estrago: perfil inativo não concede nada."""
    ensure_access_profiles(db_session)
    admin_profile = _profile(db_session, "admin")

    response = client.put(f"/api/admin/access-profiles/{admin_profile.id}", json={"active": False})

    assert response.status_code == 409
    assert "inativar" in response.json()["detail"]
    db_session.refresh(admin_profile)
    assert admin_profile.active is True


def test_profile_that_administers_access_is_deletable_when_another_one_exists(client, db_session):
    ensure_access_profiles(db_session)
    admin_profile = _profile(db_session, "admin")
    backup = AccessProfile(name="Admin Reserva", active=True, is_system=False)
    db_session.add(backup)
    db_session.flush()
    db_session.add(AccessProfilePermission(profile_id=backup.id, permission="admin:users:write"))
    db_session.commit()

    # `ensure_access_profiles` vincula o usuário admin ao perfil dele, então a exclusão exige
    # informar para onde essa pessoa vai - a mesma regra vale para perfil de sistema.
    response = client.delete(f"/api/admin/access-profiles/{admin_profile.id}?reassign_profile_id={backup.id}")

    assert response.status_code == 200, response.text
    assert _profile(db_session, "admin") is None
