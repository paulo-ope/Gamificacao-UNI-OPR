from __future__ import annotations

from app.core.security import ensure_access_profiles, get_current_user
from app.main import app
from app.models import User
from app.modules.operations.period import current_month_bounds

_DATE_FROM, _DATE_TO = current_month_bounds()
_ORDERS_QUERY = f"date_from={_DATE_FROM.isoformat()}&date_to={_DATE_TO.isoformat()}"


def test_list_endpoints_requires_read_permission(client, db_session):
    limited_user = User(name="Sem Permissao", email="sem-permissao@pytest.local", role="collaborator", active=True, password_hash="x")
    db_session.add(limited_user)
    db_session.flush()
    app.dependency_overrides[get_current_user] = lambda: limited_user
    try:
        response = client.get("/api/admin/ai-governance/endpoints")
        assert response.status_code == 403
    finally:
        app.dependency_overrides[get_current_user] = lambda: db_session.query(User).filter_by(email="admin@pytest.local").one()


def test_admin_can_list_and_toggle_endpoint(client):
    listing = client.get("/api/admin/ai-governance/endpoints")
    assert listing.status_code == 200
    endpoints = listing.json()
    assert any(item["key"] == "operations.orders.list" for item in endpoints)

    toggled = client.patch("/api/admin/ai-governance/endpoints/operations.orders.list", json={"enabled_api": False})
    assert toggled.status_code == 200
    assert toggled.json()["enabled_api"] is False

    # Efeito imediato: o gate real deve refletir a mudança sem reiniciar o processo.
    orders_response = client.get(f"/api/operations/orders?{_ORDERS_QUERY}")
    assert orders_response.status_code == 403


def test_admin_can_list_and_toggle_field_permission(client):
    listing = client.get("/api/admin/ai-governance/fields?entity=operations_orders")
    assert listing.status_code == 200
    fields = listing.json()
    assert any(item["field"] == "order_code" for item in fields)

    toggled = client.patch("/api/admin/ai-governance/fields/operations_orders/regional", json={"enabled": False})
    assert toggled.status_code == 200
    assert toggled.json()["enabled"] is False

    filtered = client.get(
        f"/api/operations/orders?{_ORDERS_QUERY}&fields=regional"
    )
    assert filtered.status_code == 422


def test_admin_can_create_and_revoke_token(client):
    created = client.post("/api/admin/ai-governance/tokens", json={"name": "Teste MCP", "scopes": ["orders.read"], "expires_in_days": 30})
    assert created.status_code == 201
    body = created.json()
    assert body["raw_key"]
    assert body["key"]["source"] == "token"
    assert body["key"]["scopes"] == ["orders.read"]
    assert body["key"]["expires_at"] is not None
    token_id = body["key"]["id"]

    listing = client.get("/api/admin/ai-governance/tokens")
    assert any(item["id"] == token_id and item["source"] == "token" and item["active"] for item in listing.json())

    revoked = client.delete(f"/api/admin/ai-governance/tokens/token/{token_id}")
    assert revoked.status_code == 200
    assert revoked.json()["active"] is False


def test_admin_token_creation_rejects_unknown_scope(client):
    response = client.post("/api/admin/ai-governance/tokens", json={"name": "Escopo invalido", "scopes": ["nao-existe"]})
    assert response.status_code == 422


def test_scoped_token_restricts_search_orders(client, db_session):
    from app.core.security import hash_api_key
    from app.models import User
    from app.modules.ai.models import ApiKeyCredential
    from app.modules.ai_governance.models import AiApiToken

    service_user = User(name="Servico IA Teste", email="ai-scope-test@pytest.local", role="ai_service", active=True, password_hash="x")
    db_session.add(service_user)
    db_session.flush()

    raw_key = "raw-key-for-scope-test-000000"
    db_session.add(
        AiApiToken(
            user_id=service_user.id,
            name="Somente detalhe",
            scopes=["orders.detail"],
            key_prefix=raw_key[:12],
            key_hash=hash_api_key(raw_key),
        )
    )
    db_session.commit()

    denied = client.post(
        "/api/ai/search-orders",
        json={"date_from": _DATE_FROM.isoformat(), "date_to": _DATE_TO.isoformat()},
        headers={"x-api-key": raw_key},
    )
    assert denied.status_code == 403

    allowed = client.post(
        "/api/ai/orders/details",
        json={"order_codes": ["IXC-NAO-EXISTE"]},
        headers={"x-api-key": raw_key},
    )
    assert allowed.status_code == 200


def test_profile_endpoint_grant_restricts_only_that_profile(client, db_session, admin_user):
    # `AccessProfile` só existe na base real via `ensure_access_profiles` (chamado no lifespan do
    # app contra `SessionLocal`, não contra o `db_session` isolado deste teste) - precisa rodar
    # aqui explicitamente para o perfil "Admin Ecossistema" existir nesta base de teste.
    ensure_access_profiles(db_session)
    db_session.refresh(admin_user)

    profiles = client.get("/api/admin/access-profiles").json()
    admin_profile = next(item for item in profiles if item["legacy_role"] == "admin")

    restrict = client.put(
        f"/api/admin/ai-governance/profiles/{admin_profile['id']}/endpoint-grants/operations.orders.list",
        json={"granted": False},
    )
    assert restrict.status_code == 200

    blocked = client.get(f"/api/operations/orders?{_ORDERS_QUERY}")
    assert blocked.status_code == 403

    removed = client.delete(f"/api/admin/ai-governance/profiles/{admin_profile['id']}/endpoint-grants/operations.orders.list")
    assert removed.status_code == 204

    allowed_again = client.get(f"/api/operations/orders?{_ORDERS_QUERY}")
    assert allowed_again.status_code == 200


def test_audit_log_records_orders_list_call(client):
    response = client.get(f"/api/operations/orders?{_ORDERS_QUERY}")
    assert response.status_code == 200

    logs = client.get("/api/admin/ai-governance/audit-logs?endpoint_key=operations.orders.list")
    assert logs.status_code == 200
    entries = logs.json()
    assert len(entries) >= 1
    assert entries[0]["endpoint_key"] == "operations.orders.list"
    assert entries[0]["status"] == "success"
