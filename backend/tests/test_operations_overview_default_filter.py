"""Filtro pré-setado da Visão Geral executiva
(`GET`/`PUT /operations/overview/default-filter`).

O padrão é um blob PRÓPRIO da Visão Geral (guardado em `app_settings`), não uma referência a uma
visão global de `operations_saved_filters` - achado real, 2026-09-09: apontar pra uma visão global
fazia esse "padrão" aparecer também na lista de visões da Operação Analítica (indesejado) e não
tinha onde guardar os filtros do SGP Suporte (`support_department`/`support_channel`/
`support_reason`), que não existem em `OperationSavedFilterValues`. Os testes travam: o padrão
guarda os dois tipos de filtro, não vaza para `OperationSavedFilter`, e só quem pode editar visão
global pode trocar o padrão de todo mundo.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.security import get_current_user
from app.main import app

ENDPOINT = "/api/operations/overview/default-filter"


def test_no_default_configured_answers_unavailable_instead_of_error(client):
    response = client.get(ENDPOINT)

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False
    assert payload["filters"] is None
    assert payload["support_filters"] is None
    assert payload["can_manage"] is True


def test_setting_a_filter_as_the_default_returns_its_values(client):
    updated = client.put(
        ENDPOINT,
        json={
            "filters": {"team_models": ["EQUIPE PRÓPRIA"], "sectors": ["Suporte Externo Fibra"]},
            "support_filters": {"support_department": ["Comercial"]},
        },
    )

    assert updated.status_code == 200
    payload = updated.json()
    assert payload["available"] is True
    assert payload["filters"]["team_models"] == ["EQUIPE PRÓPRIA"]
    assert payload["support_filters"]["support_department"] == ["Comercial"]

    # Persistiu: uma leitura nova devolve o mesmo padrão.
    persisted = client.get(ENDPOINT).json()
    assert persisted["filters"]["sectors"] == ["Suporte Externo Fibra"]
    assert persisted["support_filters"]["support_department"] == ["Comercial"]


def test_default_can_be_cleared(client):
    client.put(ENDPOINT, json={"filters": {"team_models": ["EQUIPE PRÓPRIA"]}})

    cleared = client.put(ENDPOINT, json={"filters": None})

    assert cleared.status_code == 200
    payload = cleared.json()
    assert payload["available"] is False
    assert payload["filters"] is None
    assert payload["support_filters"] is None


def test_saving_without_support_filters_defaults_them_to_empty(client):
    updated = client.put(ENDPOINT, json={"filters": {"team_models": ["EQUIPE PRÓPRIA"]}})

    assert updated.status_code == 200
    payload = updated.json()
    assert payload["support_filters"] == {
        "support_department": [],
        "support_channel": [],
        "support_reason": [],
    }


def test_changing_the_default_requires_the_global_view_permission(client):
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

    body = {"filters": {"team_models": ["EQUIPE PRÓPRIA"]}}
    try:
        # Gerenciar filtro pessoal não basta para trocar o padrão de todo mundo.
        app.dependency_overrides[get_current_user] = lambda: user_with(
            "operations:read", "operations:manage_filters"
        )
        denied = client.put(ENDPOINT, json=body)
        readable = client.get(ENDPOINT)

        app.dependency_overrides[get_current_user] = lambda: user_with(
            "operations:read", "operations:views:update_global"
        )
        allowed = client.put(ENDPOINT, json=body)
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert denied.status_code == 403
    # A leitura continua liberada: a tela precisa abrir pré-setada mesmo para quem só consulta.
    assert readable.status_code == 200
    assert readable.json()["can_manage"] is False
    assert allowed.status_code == 200
    assert allowed.json()["filters"]["team_models"] == ["EQUIPE PRÓPRIA"]
