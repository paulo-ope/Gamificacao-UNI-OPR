"""Filtros exibidos na Visão Geral executiva
(`GET`/`PUT /operations/overview/visible-filters`).

O catálogo no backend é a única fonte do que a tela sabe desenhar; estes testes travam o padrão
(cinco filtros de O.S.), a validação por catálogo e a permissão para mudar o padrão de todos.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.core.security import get_current_user
from app.main import app

ENDPOINT = "/api/operations/overview/visible-filters"


def _user_with(*permissions: str):
    return SimpleNamespace(
        id=907,
        role="workspace_restricted",
        managed_regional=None,
        managed_regionals=[],
        access_profiles=[
            SimpleNamespace(active=True, permissions=[SimpleNamespace(permission=p) for p in permissions])
        ],
    )


def test_default_is_the_five_operations_filters_and_catalog_has_both_groups(client):
    response = client.get(ENDPOINT)

    assert response.status_code == 200
    payload = response.json()
    assert payload["filters"] == ["team_models", "regionals", "sectors", "os_types", "responsibles"]
    groups = {item["group"] for item in payload["available"]}
    assert groups == {"operations", "support"}
    assert any(item["key"] == "support_channel" for item in payload["available"])
    assert payload["can_manage"] is True


def test_put_persists_in_catalog_order_and_deduplicates(client):
    updated = client.put(ENDPOINT, json={"filters": ["support_channel", "regionals", "regionals", "team_models"]})

    assert updated.status_code == 200
    # Ordem do catálogo, não a ordem enviada; sem duplicata.
    assert updated.json()["filters"] == ["team_models", "regionals", "support_channel"]
    assert client.get(ENDPOINT).json()["filters"] == ["team_models", "regionals", "support_channel"]


def test_unknown_key_is_rejected(client):
    response = client.put(ENDPOINT, json={"filters": ["regionals", "cidade_qualquer"]})

    assert response.status_code == 422
    assert "cidade_qualquer" in response.json()["detail"]


def test_empty_list_restores_the_default(client):
    client.put(ENDPOINT, json={"filters": ["regionals"]})

    restored = client.put(ENDPOINT, json={"filters": []})

    assert restored.status_code == 200
    assert restored.json()["filters"] == ["team_models", "regionals", "sectors", "os_types", "responsibles"]


def test_changing_requires_global_view_permission_but_reading_does_not(client):
    try:
        app.dependency_overrides[get_current_user] = lambda: _user_with("operations:read")
        denied = client.put(ENDPOINT, json={"filters": ["regionals"]})
        readable = client.get(ENDPOINT)
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert denied.status_code == 403
    assert readable.status_code == 200
    assert readable.json()["can_manage"] is False
