"""Filtro pré-setado da Visão Geral executiva
(`GET`/`PUT /operations/overview/default-filter`).

O padrão aponta para uma visão GLOBAL já existente em vez de criar um catálogo de configuração
paralelo. Os testes travam as duas regras que protegem isso: só visão global pode ser padrão, e
só quem pode editar visão global pode trocar o padrão de todo mundo.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.security import get_current_user
from app.main import app
from app.modules.operations.models import OperationSavedFilter

ENDPOINT = "/api/operations/overview/default-filter"


@pytest.fixture()
def global_view(db_session, admin_user):
    item = OperationSavedFilter(
        user_id=admin_user.id,
        name="Visão da diretoria",
        filters={"team_models": ["EQUIPE PRÓPRIA"], "sectors": ["Suporte Externo Fibra"]},
        visibility="global",
    )
    db_session.add(item)
    db_session.flush()
    return item


@pytest.fixture()
def personal_view(db_session, admin_user):
    item = OperationSavedFilter(
        user_id=admin_user.id,
        name="Minha visão",
        filters={"team_models": ["TERCEIRIZADA"]},
        visibility="personal",
    )
    db_session.add(item)
    db_session.flush()
    return item


def test_no_default_configured_answers_unavailable_instead_of_error(client):
    response = client.get(ENDPOINT)

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False
    assert payload["saved_filter_id"] is None
    assert payload["filters"] is None
    assert payload["can_manage"] is True


def test_setting_a_global_view_as_the_default_returns_its_values(client, global_view):
    updated = client.put(ENDPOINT, json={"saved_filter_id": global_view.id})

    assert updated.status_code == 200
    payload = updated.json()
    assert payload["available"] is True
    assert payload["saved_filter_id"] == global_view.id
    assert payload["name"] == "Visão da diretoria"
    assert payload["filters"]["team_models"] == ["EQUIPE PRÓPRIA"]

    # Persistiu: uma leitura nova devolve o mesmo padrão.
    assert client.get(ENDPOINT).json()["saved_filter_id"] == global_view.id


def test_a_personal_view_cannot_be_the_default_of_everyone(client, personal_view):
    response = client.put(ENDPOINT, json={"saved_filter_id": personal_view.id})

    assert response.status_code == 422
    assert client.get(ENDPOINT).json()["available"] is False


def test_default_can_be_cleared(client, global_view):
    client.put(ENDPOINT, json={"saved_filter_id": global_view.id})

    cleared = client.put(ENDPOINT, json={"saved_filter_id": None})

    assert cleared.status_code == 200
    assert cleared.json()["available"] is False


def test_a_deleted_global_view_degrades_to_no_default(client, db_session, global_view):
    client.put(ENDPOINT, json={"saved_filter_id": global_view.id})
    db_session.delete(global_view)
    db_session.flush()

    response = client.get(ENDPOINT)

    assert response.status_code == 200
    assert response.json()["available"] is False


def test_changing_the_default_requires_the_global_view_permission(client, global_view):
    def user_with(*permissions: str):
        return SimpleNamespace(
            id=906,
            role="workspace_restricted",
            managed_regional=None,
            managed_regionals=[],
            access_profiles=[
                SimpleNamespace(
                    active=True,
                    permissions=[SimpleNamespace(permission=permission) for permission in permissions],
                )
            ],
        )

    try:
        # Gerenciar filtro pessoal não basta para trocar o padrão de todo mundo.
        app.dependency_overrides[get_current_user] = lambda: user_with(
            "operations:read", "operations:manage_filters"
        )
        denied = client.put(ENDPOINT, json={"saved_filter_id": global_view.id})
        readable = client.get(ENDPOINT)

        app.dependency_overrides[get_current_user] = lambda: user_with(
            "operations:read", "operations:views:update_global"
        )
        allowed = client.put(ENDPOINT, json={"saved_filter_id": global_view.id})
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert denied.status_code == 403
    # A leitura continua liberada: a tela precisa abrir pré-setada mesmo para quem só consulta.
    assert readable.status_code == 200
    assert readable.json()["can_manage"] is False
    assert allowed.status_code == 200
    assert allowed.json()["saved_filter_id"] == global_view.id
