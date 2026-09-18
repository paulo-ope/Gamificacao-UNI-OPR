"""Catálogo de permissões da Administração: agrupamento derivado do registry e permissões próprias.

Dois achados reais motivam este arquivo (2026-09-09):

1. O agrupamento por módulo era uma lista escrita à mão no router. O UNI Localiza, criado depois
   dela, caía em "Outras permissões" na tela de Perfis de Acesso - era o único módulo ativo nessa
   condição. O agrupamento passou a ser derivado de `app/modules/registry.py`, e
   `test_every_code_permission_belongs_to_a_named_group` é a trava para o próximo módulo novo.
2. Não havia como criar nem excluir permissão pela tela. Agora existe, com a fronteira clara:
   permissão de código não é excluível (apagar o rótulo não apagaria a exigência da rota).
"""
from __future__ import annotations

from app.core.security import PERMISSION_LABELS
from app.models import AccessProfile, AccessProfilePermission, CustomPermission, UserAccessProfile
from app.modules.admin.permissions_service import OTHER_PERMISSIONS_LABEL, permission_catalog


def _catalog(db_session):
    return {item.key: item for item in permission_catalog(db_session)}


def test_localiza_permissions_are_grouped_under_the_module(db_session):
    catalog = _catalog(db_session)

    assert catalog["localiza:read"].module == "UNI Localiza"
    assert catalog["localiza:read"].module_key == "localiza"
    assert catalog["localiza:manage"].module == "UNI Localiza"


def test_every_code_permission_belongs_to_a_named_group(db_session):
    """Nenhuma permissão de código pode cair em "Outras permissões".

    É a trava contra a regressão que o Localiza expôs: módulo novo cujo prefixo não estivesse na
    lista manual desaparecia num grupo genérico no fim da tela.
    """
    catalog = _catalog(db_session)
    unnamed = sorted(key for key in PERMISSION_LABELS if catalog[key].module == OTHER_PERMISSIONS_LABEL)

    assert unnamed == []


def test_all_active_modules_have_at_least_one_permission_in_the_catalog(db_session):
    from app.modules.registry import list_modules

    catalog = permission_catalog(db_session)
    module_keys_with_permissions = {item.module_key for item in catalog}
    active_modules = {module.key for module in list_modules() if module.status == "active"}

    assert active_modules.issubset(module_keys_with_permissions)


def test_catalog_reports_usage_per_permission(db_session, admin_user):
    profile = AccessProfile(name="Perfil Uso", description=None, active=True, is_system=False)
    db_session.add(profile)
    db_session.flush()
    db_session.add(AccessProfilePermission(profile_id=profile.id, permission="localiza:read"))
    db_session.add(UserAccessProfile(user_id=admin_user.id, profile_id=profile.id))
    db_session.flush()

    entry = _catalog(db_session)["localiza:read"]

    assert entry.profile_count == 1
    assert entry.profile_names == ["Perfil Uso"]
    assert entry.user_count == 1


def test_create_custom_permission_and_assign_to_profile(client, db_session):
    response = client.post(
        "/api/admin/permissions",
        json={
            "key": "Localiza:Exportar",
            "label": "UNI Localiza: exportar solicitações",
            "module_key": "localiza",
            "description": "Baixar a lista em planilha.",
            "sensitive": False,
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["key"] == "localiza:exportar", "a chave é normalizada em minúsculas"
    assert body["custom"] is True
    assert body["module"] == "UNI Localiza"

    created = client.post(
        "/api/admin/access-profiles",
        json={"name": "Atendente Exportador", "active": True, "permission_keys": ["localiza:exportar"]},
    )
    assert created.status_code == 201, created.text
    assert created.json()["permission_keys"] == ["localiza:exportar"]


def test_custom_permission_key_must_follow_the_project_convention(client):
    response = client.post(
        "/api/admin/permissions",
        json={"key": "Exportar Tudo!", "label": "Exportar tudo", "module_key": None},
    )

    assert response.status_code == 422
    assert "modulo:acao" in response.json()["detail"]


def test_custom_permission_cannot_shadow_a_code_permission(client):
    response = client.post(
        "/api/admin/permissions",
        json={"key": "localiza:read", "label": "Outra coisa", "module_key": "localiza"},
    )

    assert response.status_code == 409
    assert "sistema" in response.json()["detail"]


def test_system_permission_cannot_be_deleted(client):
    response = client.delete("/api/admin/permissions/localiza:read")

    assert response.status_code == 400
    assert "não pode ser alterada nem excluída" in response.json()["detail"]


def test_custom_permission_in_use_is_not_deleted_before_being_removed_from_profiles(client, db_session):
    client.post(
        "/api/admin/permissions",
        json={"key": "localiza:exportar", "label": "UNI Localiza: exportar", "module_key": "localiza"},
    )
    profile = client.post(
        "/api/admin/access-profiles",
        json={"name": "Perfil Com Custom", "active": True, "permission_keys": ["localiza:exportar"]},
    ).json()

    blocked = client.delete("/api/admin/permissions/localiza:exportar")
    assert blocked.status_code == 409
    assert "Perfil Com Custom" in blocked.json()["detail"]

    client.put(
        f"/api/admin/access-profiles/{profile['id']}",
        json={"permission_keys": []},
    )
    freed = client.delete("/api/admin/permissions/localiza:exportar")

    assert freed.status_code == 204
    assert db_session.query(CustomPermission).count() == 0


def test_custom_permission_label_changes_but_key_never_does(client):
    client.post(
        "/api/admin/permissions",
        json={"key": "localiza:exportar", "label": "Nome antigo", "module_key": "localiza"},
    )

    response = client.put(
        "/api/admin/permissions/localiza:exportar",
        json={"label": "Nome novo", "sensitive": True},
    )

    assert response.status_code == 200
    assert response.json()["label"] == "Nome novo"
    assert response.json()["key"] == "localiza:exportar"
    assert response.json()["sensitive"] is True
