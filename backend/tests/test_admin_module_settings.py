"""Módulo do ecossistema parametrizável pela Administração (nome, descrição, status e ordem).

O `app/modules/registry.py` continua sendo a fonte estrutural (rota, prefixo de API, permissão
mínima - ver `modules_service`). O que a tela ajusta é apresentação e disponibilidade, e o ponto
central destes testes é que a Administração e a navegação do usuário leem a MESMA fonte: não pode
existir módulo "desativado na Administração e visível na barra lateral".
"""
from __future__ import annotations

from app.core.security import ensure_access_profiles


def _module(payload: list[dict], key: str) -> dict:
    return next(item for item in payload if item["key"] == key)


def test_module_starts_with_the_registry_values(client):
    modules = client.get("/api/admin/modules").json()
    localiza = _module(modules, "localiza")

    assert localiza["name"] == "UNI Localiza"
    assert localiza["status"] == "active"
    assert localiza["customized"] is False
    assert localiza["default_name"] == "UNI Localiza"


def test_renaming_a_module_reaches_the_user_navigation(client, db_session):
    ensure_access_profiles(db_session)

    response = client.put(
        "/api/admin/modules/localiza/settings",
        json={"name": "UNI Localizador", "description": "Posição do cliente por GPS"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "UNI Localizador"
    assert response.json()["customized"] is True

    visible = client.get("/api/workspace/modules").json()
    assert _module(visible, "localiza")["name"] == "UNI Localizador"
    assert _module(visible, "localiza")["description"] == "Posição do cliente por GPS"


def test_disabling_a_module_removes_it_from_the_user_navigation(client, db_session):
    ensure_access_profiles(db_session)
    assert any(item["key"] == "localiza" for item in client.get("/api/workspace/modules").json())

    response = client.put("/api/admin/modules/localiza/settings", json={"status": "disabled"})
    assert response.status_code == 200, response.text

    visible = client.get("/api/workspace/modules").json()
    assert not any(item["key"] == "localiza" for item in visible)
    # Continua listado na Administração, onde o admin pode reativar.
    assert _module(client.get("/api/admin/modules").json(), "localiza")["status"] == "disabled"


def test_empty_value_restores_the_registry_default(client):
    client.put("/api/admin/modules/localiza/settings", json={"name": "Outro nome"})

    response = client.put("/api/admin/modules/localiza/settings", json={"name": ""})

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "UNI Localiza"
    assert response.json()["customized"] is False


def test_invalid_status_is_refused(client):
    response = client.put("/api/admin/modules/localiza/settings", json={"status": "meio_ativo"})

    assert response.status_code == 422
    assert "Status inválido" in response.json()["detail"]


def test_unknown_module_is_not_found(client):
    response = client.put("/api/admin/modules/inexistente/settings", json={"name": "X"})

    assert response.status_code == 404


def test_sort_order_changes_the_navigation_order(client, db_session):
    ensure_access_profiles(db_session)
    before = [item["key"] for item in client.get("/api/workspace/modules").json()]
    assert before[0] != "localiza", "o Localiza é o último do registry, é o que dá sentido ao teste"

    client.put("/api/admin/modules/localiza/settings", json={"sort_order": 0})

    after = [item["key"] for item in client.get("/api/workspace/modules").json()]
    assert after[0] == "localiza"


def test_module_settings_require_the_write_permission(client, db_session, admin_user):
    """Reconfigurar módulo é `admin:modules:write` - não vem de carona em `admin:modules:read`."""
    from app.models import AccessProfile, AccessProfilePermission, UserAccessProfile

    read_only = AccessProfile(name="Somente Leitura Modulos", active=True, is_system=False)
    db_session.add(read_only)
    db_session.flush()
    db_session.add(AccessProfilePermission(profile_id=read_only.id, permission="admin:modules:read"))
    db_session.query(UserAccessProfile).filter(UserAccessProfile.user_id == admin_user.id).delete(
        synchronize_session=False
    )
    db_session.add(UserAccessProfile(user_id=admin_user.id, profile_id=read_only.id))
    db_session.commit()
    db_session.refresh(admin_user)

    assert client.get("/api/admin/modules").status_code == 200
    assert client.put("/api/admin/modules/localiza/settings", json={"name": "X"}).status_code == 403
