"""Preferência pessoal de atalho na sidebar (fixar/reordenar) - endpoint self-service, ao
contrário de `admin/router.py` (que muda visibilidade de OUTRO usuário/perfil). E a Visão Geral
(`/workspace/overview`), que só agrega o que cada módulo já expõe."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.security import get_current_user
from app.db.session import get_db
from app.main import app
from app.models import User


@pytest.fixture()
def viewer_user(db_session):
    user = User(name="Gestor Viewer", email="viewer@pytest.local", role="viewer", active=True, password_hash="x")
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture()
def viewer_client(db_session, viewer_user):
    """Cliente autenticado como um usuário SEM permissão de admin - prova que a preferência é
    self-service de verdade, não uma rota disfarçada que exige admin."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: viewer_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_update_module_preference_self_service_no_admin_required(viewer_client, viewer_user):
    response = viewer_client.put(
        "/api/workspace/modules/operations/preference",
        json={"pinned": True, "order_index": 0},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["pinned"] is True
    assert body["order_index"] == 0


def test_update_module_preference_rejects_module_without_permission(viewer_client):
    # "viewer" não tem admin:users:read -> não pode fixar o módulo de Administração.
    response = viewer_client.put(
        "/api/workspace/modules/admin/preference",
        json={"pinned": True},
    )

    assert response.status_code == 404


def test_update_module_preference_does_not_touch_visibility(viewer_client, viewer_user, db_session):
    from sqlalchemy import select

    from app.models import WorkspaceModuleVisibility

    viewer_client.put("/api/workspace/modules/operations/preference", json={"pinned": True})

    row = db_session.scalar(
        select(WorkspaceModuleVisibility).where(
            WorkspaceModuleVisibility.module_key == "operations",
            WorkspaceModuleVisibility.user_id == viewer_user.id,
        )
    )
    assert row.visible is True  # nasceu visível por padrão, preferência nunca mexe nisso
    assert row.pinned is True


def test_modules_endpoint_returns_pinned_and_order(viewer_client):
    viewer_client.put("/api/workspace/modules/operations/preference", json={"pinned": True, "order_index": 3})

    response = viewer_client.get("/api/workspace/modules")

    assert response.status_code == 200
    by_key = {item["key"]: item for item in response.json()}
    assert by_key["operations"]["pinned"] is True
    assert by_key["operations"]["order_index"] == 3


def test_overview_only_includes_cards_for_permitted_modules(viewer_client):
    response = viewer_client.get("/api/workspace/overview")

    assert response.status_code == 200
    cards = response.json()["cards"]
    module_keys = {card["module_key"] for card in cards}
    # "viewer" tem operations:read mas não scheduling:read/support:read/management:read.
    assert "operations" in module_keys
    assert "scheduling" not in module_keys
    assert "support" not in module_keys
    assert "management" not in module_keys


def test_overview_admin_sees_multiple_cards(client):
    response = client.get("/api/workspace/overview")

    assert response.status_code == 200
    cards = response.json()["cards"]
    module_keys = {card["module_key"] for card in cards}
    assert {"operations", "scheduling", "support", "management"}.issubset(module_keys)
