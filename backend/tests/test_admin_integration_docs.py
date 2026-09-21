"""Swagger protegido e filtrado de integração externa (`app/modules/admin/integration_docs.py`).

Cobre as duas formas de autenticação aceitas (sessão do workspace e token de integração) e o
filtro do schema para só os endpoints de leitura dos módulos de negócio autorizados (ver
`INTEGRATION_DOCS_TAGS`) - todos os 9 módulos desde 2026-09-21 (pedido do Cubo de Dados
Corporativo / Portal Executivo UNI), nunca método de escrita.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.security import create_access_token, hash_api_key
from app.modules.admin.integration_docs import INTEGRATION_DOCS_TAGS
from app.modules.ai.models import ApiKeyCredential
from app.models import User, UserPermissionOverride
from app.modules.ai_governance.models import AiApiToken


def test_requires_auth(client):
    response = client.get("/api/admin/docs/integracao-uni/openapi.json")
    assert response.status_code == 401


def test_session_bearer_without_permission_is_rejected(client, db_session):
    limited = User(name="Sem Permissao", email="sem-integracoes@pytest.local", role="collaborator", active=True, password_hash="x")
    db_session.add(limited)
    db_session.flush()
    token = create_access_token(limited)
    response = client.get("/api/admin/docs/integracao-uni/openapi.json", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_session_bearer_with_permission_returns_filtered_schema(client, db_session, admin_user):
    db_session.add(UserPermissionOverride(user_id=admin_user.id, permission="admin:integrations:read", effect="grant"))
    db_session.flush()
    token = create_access_token(admin_user)

    response = client.get("/api/admin/docs/integracao-uni/openapi.json", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    schema = response.json()
    assert schema["paths"]
    allowed_tags = set(INTEGRATION_DOCS_TAGS)
    for path, methods in schema["paths"].items():
        # Trava estrutural: só GET pode aparecer, mesmo que a tag do router misture leitura e
        # escrita (ex.: calculation-runs tem GET de status e POST /calculate).
        assert set(methods.keys()) == {"get"}, path
        for operation in methods.values():
            assert allowed_tags & set(operation.get("tags", [])), path
            # Toda operação carrega a permissão exigida (extraída por introspecção do código) -
            # ver docstring de _permission_keys_from_dependant.
            assert "x-permission" in operation, path
    # Módulo fora da lista autorizada (ex.: legado /users, OAuth do MCP) não pode aparecer.
    assert not any(path.startswith("/api/users") for path in schema["paths"])


def test_session_bearer_as_query_token_works_for_swagger_ui_fetch(client, db_session, admin_user):
    db_session.add(UserPermissionOverride(user_id=admin_user.id, permission="admin:integrations:read", effect="grant"))
    db_session.flush()
    token = create_access_token(admin_user)

    html = client.get(f"/api/admin/docs/integracao-uni?token={token}")
    assert html.status_code == 200
    assert f"token={token}" in html.text

    schema = client.get(f"/api/admin/docs/integracao-uni/openapi.json?token={token}")
    assert schema.status_code == 200


def test_integration_api_token_grants_access(client, db_session):
    service_user = User(name="Integracao UNI", email="integracao-uni@pytest.local", role="ai_service", active=True, password_hash="x")
    db_session.add(service_user)
    db_session.flush()

    raw_key = "raw-key-for-integration-docs-test"
    db_session.add(
        AiApiToken(
            name="Token Integração UNI",
            user_id=service_user.id,
            scopes=[],
            key_prefix=raw_key[:12],
            key_hash=hash_api_key(raw_key),
            active=True,
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
    )
    db_session.flush()

    response = client.get("/api/admin/docs/integracao-uni/openapi.json", headers={"x-api-key": raw_key})
    assert response.status_code == 200

    via_query = client.get(f"/api/admin/docs/integracao-uni/openapi.json?token={raw_key}")
    assert via_query.status_code == 200


def test_revoked_integration_token_is_rejected(client, db_session):
    service_user = User(name="Integracao Revogada", email="integracao-revogada@pytest.local", role="ai_service", active=True, password_hash="x")
    db_session.add(service_user)
    db_session.flush()

    raw_key = "raw-key-for-revoked-token-test"
    db_session.add(
        AiApiToken(
            name="Token Revogado",
            user_id=service_user.id,
            scopes=[],
            key_prefix=raw_key[:12],
            key_hash=hash_api_key(raw_key),
            active=False,
            revoked_at=datetime.now(timezone.utc),
        )
    )
    db_session.flush()

    response = client.get("/api/admin/docs/integracao-uni/openapi.json", headers={"x-api-key": raw_key})
    assert response.status_code == 401


def test_legacy_api_key_credential_grants_access(client, db_session):
    """Chave legado (`ApiKeyCredential`, sem escopo) - continua aceita, mesmo padrão de
    `ai/auth.py`."""
    service_user = User(name="Integracao Legado", email="integracao-legado@pytest.local", role="ai_service", active=True, password_hash="x")
    db_session.add(service_user)
    db_session.flush()

    raw_key = "raw-key-for-legacy-credential-test"
    db_session.add(
        ApiKeyCredential(
            name="Chave Legado",
            user_id=service_user.id,
            key_prefix=raw_key[:12],
            key_hash=hash_api_key(raw_key),
            active=True,
        )
    )
    db_session.flush()

    response = client.get("/api/admin/docs/integracao-uni/openapi.json", headers={"x-api-key": raw_key})
    assert response.status_code == 200
