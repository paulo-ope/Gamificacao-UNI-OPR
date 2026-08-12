"""Testes do conector MCP remoto (app/modules/mcp_connector). O fluxo OAuth completo (registro
DCR, authorize->consent->approve->code->token, chamada de tool via MCP Streamable HTTP, refresh
com rotação, revoke) já foi validado manualmente de ponta a ponta contra o backend rodando de
verdade (Postgres real, container real) antes deste arquivo existir - aqui cobrimos a lógica do
provider e das rotas de consentimento em isolamento, pra pegar regressão futura."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

from app.core.security import hash_password
from app.models import User
from app.modules.mcp_connector import provider as provider_module
from app.modules.mcp_connector.models import McpOAuthAuthorizationCode, McpOAuthClient, McpOAuthToken
from app.modules.mcp_connector.provider import OprMcpOAuthProvider
from app.modules.mcp_connector.router import router as consent_router
from app.modules.mcp_connector.provider import SCOPE
from app.modules.mcp_connector.server import _validated_filters


class _FakeSettings:
    public_base_url = "https://operacao.souuni.test"
    api_prefix = "/api"


@pytest.fixture(autouse=True)
def _mcp_settings(monkeypatch, db_session):
    """Toda a lógica do provider abre sua PRÓPRIA sessão via `SessionLocal()` (ver docstring de
    provider.py - o SDK do MCP chama esses métodos fora do ciclo de request do FastAPI, sem
    `Depends(get_db)` disponível) - por isso os testes precisam apontar `SessionLocal` para o
    MESMO engine em memória do `db_session` da fixture, senão o provider escreveria num banco
    completamente à parte, invisível pros asserts do teste."""
    @contextmanager
    def _shared_session():
        # NÃO fecha `db_session` ao sair do `with` - o provider real usa `with SessionLocal() as
        # db: ...` (fechando a sessão ao final de cada método), mas aqui a mesma `db_session` da
        # fixture precisa sobreviver entre chamadas sucessivas dentro do mesmo teste.
        yield db_session

    monkeypatch.setattr(provider_module, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(provider_module, "SessionLocal", _shared_session)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def registered_client(db_session) -> OAuthClientInformationFull:
    provider = OprMcpOAuthProvider()
    client_info = OAuthClientInformationFull(
        client_id="test-client-1",
        redirect_uris=[AnyUrl("http://127.0.0.1:9999/callback")],
        token_endpoint_auth_method="none",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
    )
    _run(provider.register_client(client_info))
    db_session.commit()
    return client_info


@pytest.fixture()
def user_with_scope(db_session):
    user = User(name="MCP User", email="mcp-scope@pytest.local", password_hash=hash_password("Segredo123!"), role="ai_service", active=True)
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture()
def user_without_scope(db_session):
    user = User(name="Sem Escopo", email="mcp-noscope@pytest.local", password_hash=hash_password("Segredo123!"), role="viewer", active=True)
    db_session.add(user)
    db_session.flush()
    return user


def test_register_client_persists_and_get_client_round_trips(db_session, registered_client):
    provider = OprMcpOAuthProvider()
    loaded = _run(provider.get_client(registered_client.client_id))
    assert loaded is not None
    assert loaded.client_id == registered_client.client_id
    assert str(loaded.redirect_uris[0]) == "http://127.0.0.1:9999/callback"
    assert loaded.token_endpoint_auth_method == "none"

    row = db_session.query(McpOAuthClient).filter(McpOAuthClient.client_id == registered_client.client_id).one()
    assert row.client_secret_hash is None  # cliente público (DCR sem segredo)


def test_get_client_returns_none_for_unknown_id():
    provider = OprMcpOAuthProvider()
    assert _run(provider.get_client("does-not-exist")) is None


def test_authorize_creates_pending_row_and_returns_consent_url(db_session, registered_client):
    provider = OprMcpOAuthProvider()
    params = AuthorizationParams(
        state="abc",
        scopes=[SCOPE],
        code_challenge="challenge-value",
        redirect_uri=AnyUrl("http://127.0.0.1:9999/callback"),
        redirect_uri_provided_explicitly=True,
    )
    url = _run(provider.authorize(registered_client, params))
    assert url.startswith("https://operacao.souuni.test/api/oauth/consent?request_id=")
    request_id = url.split("request_id=")[1]

    from app.modules.mcp_connector.models import McpOAuthPendingAuthorization

    pending = db_session.query(McpOAuthPendingAuthorization).filter(McpOAuthPendingAuthorization.request_id == request_id).one()
    assert pending.client_id == registered_client.client_id
    assert pending.code_challenge == "challenge-value"
    assert pending.state == "abc"


def _full_code_exchange(db_session, provider, client_info, user, code_challenge="chal"):
    """Simula o que a rota de consentimento faz depois de um "approve" - emite um código
    diretamente (sem passar pela tela HTML), pra testar `load_authorization_code`/
    `exchange_authorization_code` isoladamente."""
    raw_code = provider_module._generate_secret()
    db_session.add(
        McpOAuthAuthorizationCode(
            code_hash=provider_module._hash_token(raw_code),
            client_id=client_info.client_id,
            user_id=user.id,
            redirect_uri="http://127.0.0.1:9999/callback",
            redirect_uri_provided_explicitly=True,
            code_challenge=code_challenge,
            scopes=[SCOPE],
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
    )
    db_session.commit()
    return raw_code


def test_exchange_authorization_code_issues_token_and_marks_code_used(db_session, registered_client, user_with_scope):
    provider = OprMcpOAuthProvider()
    raw_code = _full_code_exchange(db_session, provider, registered_client, user_with_scope)

    loaded = _run(provider.load_authorization_code(registered_client, raw_code))
    assert loaded is not None
    assert loaded.subject == str(user_with_scope.id)

    token = _run(provider.exchange_authorization_code(registered_client, loaded))
    assert token.access_token
    assert token.refresh_token
    assert token.scope == SCOPE

    # Código já usado - carregar de novo deve devolver None (não reutilizável).
    assert _run(provider.load_authorization_code(registered_client, raw_code)) is None

    access = _run(provider.load_access_token(token.access_token))
    assert access is not None
    assert access.subject == str(user_with_scope.id)


def test_load_access_token_returns_none_when_revoked_or_expired(db_session, registered_client, user_with_scope):
    provider = OprMcpOAuthProvider()
    raw_code = _full_code_exchange(db_session, provider, registered_client, user_with_scope)
    loaded = _run(provider.load_authorization_code(registered_client, raw_code))
    token = _run(provider.exchange_authorization_code(registered_client, loaded))

    access = _run(provider.load_access_token(token.access_token))
    assert access is not None

    _run(provider.revoke_token(access))
    assert _run(provider.load_access_token(token.access_token)) is None

    # Token expirado (não revogado) também deve falhar.
    row = db_session.query(McpOAuthToken).filter(McpOAuthToken.access_token_hash == provider_module._hash_token(token.access_token)).one()
    row.revoked_at = None
    row.access_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    assert _run(provider.load_access_token(token.access_token)) is None


def test_refresh_token_rotates_and_invalidates_old_refresh_token(db_session, registered_client, user_with_scope):
    provider = OprMcpOAuthProvider()
    raw_code = _full_code_exchange(db_session, provider, registered_client, user_with_scope)
    loaded = _run(provider.load_authorization_code(registered_client, raw_code))
    first_token = _run(provider.exchange_authorization_code(registered_client, loaded))

    refresh = _run(provider.load_refresh_token(registered_client, first_token.refresh_token))
    assert refresh is not None
    assert refresh.subject == str(user_with_scope.id)

    second_token = _run(provider.exchange_refresh_token(registered_client, refresh, [SCOPE]))
    assert second_token.access_token != first_token.access_token
    assert second_token.refresh_token != first_token.refresh_token

    # Refresh antigo não pode mais ser usado (rotacionado/revogado).
    assert _run(provider.load_refresh_token(registered_client, first_token.refresh_token)) is None
    # O novo funciona.
    assert _run(provider.load_refresh_token(registered_client, second_token.refresh_token)) is not None


def _pending_authorization(db_session, client_id="test-client-1"):
    from app.modules.mcp_connector.models import McpOAuthPendingAuthorization

    request_id = provider_module._generate_secret()
    db_session.add(
        McpOAuthPendingAuthorization(
            request_id=request_id,
            client_id=client_id,
            redirect_uri="http://127.0.0.1:9999/callback",
            redirect_uri_provided_explicitly=True,
            code_challenge="chal",
            scopes=[SCOPE],
            state="state-1",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
    )
    db_session.commit()
    return request_id


def test_consent_screen_returns_404_for_unknown_request_id(client):
    response = client.get("/api/oauth/consent", params={"request_id": "does-not-exist"})
    assert response.status_code == 404


def test_consent_screen_shows_login_form_when_not_authenticated(client, db_session):
    request_id = _pending_authorization(db_session)
    response = client.get("/api/oauth/consent", params={"request_id": request_id})
    assert response.status_code == 200
    assert "senha" in response.text.lower()
    assert request_id in response.text


def test_consent_login_rejects_wrong_password(client, db_session, user_with_scope):
    request_id = _pending_authorization(db_session)
    response = client.post(
        "/api/oauth/consent/login",
        data={"request_id": request_id, "email": user_with_scope.email, "password": "senha-errada"},
    )
    assert response.status_code == 200
    assert "inválidos" in response.text.lower()
    assert "mcp_oauth_session" not in response.cookies


def test_consent_login_success_sets_cookie_and_shows_permit_button_when_scoped(client, db_session, user_with_scope):
    request_id = _pending_authorization(db_session)
    login = client.post(
        "/api/oauth/consent/login",
        data={"request_id": request_id, "email": user_with_scope.email, "password": "Segredo123!"},
        follow_redirects=False,
    )
    assert login.status_code in (302, 303)
    assert "mcp_oauth_session" in login.cookies

    consent = client.get("/api/oauth/consent", params={"request_id": request_id})
    assert "permitir" in consent.text.lower()


def test_consent_login_success_shows_permission_error_when_not_scoped(client, db_session, user_without_scope):
    request_id = _pending_authorization(db_session)
    client.post(
        "/api/oauth/consent/login",
        data={"request_id": request_id, "email": user_without_scope.email, "password": "Segredo123!"},
    )
    consent = client.get("/api/oauth/consent", params={"request_id": request_id})
    assert "sem permissão" in consent.text.lower()


def test_consent_decide_without_login_returns_401(client, db_session):
    request_id = _pending_authorization(db_session)
    response = client.post("/api/oauth/consent/decide", data={"request_id": request_id, "decision": "approve"})
    assert response.status_code == 401


def test_consent_decide_deny_redirects_with_access_denied(client, db_session, user_with_scope):
    request_id = _pending_authorization(db_session)
    client.post("/api/oauth/consent/login", data={"request_id": request_id, "email": user_with_scope.email, "password": "Segredo123!"})
    response = client.post("/api/oauth/consent/decide", data={"request_id": request_id, "decision": "deny"}, follow_redirects=False)
    assert response.status_code in (302, 303)
    assert "error=access_denied" in response.headers["location"]
    assert "state=state-1" in response.headers["location"]


def test_consent_decide_approve_issues_code_and_deletes_pending(client, db_session, user_with_scope):
    request_id = _pending_authorization(db_session)
    client.post("/api/oauth/consent/login", data={"request_id": request_id, "email": user_with_scope.email, "password": "Segredo123!"})
    response = client.post("/api/oauth/consent/decide", data={"request_id": request_id, "decision": "approve"}, follow_redirects=False)
    assert response.status_code in (302, 303)
    location = response.headers["location"]
    assert "code=" in location
    assert "state=state-1" in location

    from app.modules.mcp_connector.models import McpOAuthPendingAuthorization

    assert db_session.query(McpOAuthPendingAuthorization).filter(McpOAuthPendingAuthorization.request_id == request_id).one_or_none() is None
    assert db_session.query(McpOAuthAuthorizationCode).filter(McpOAuthAuthorizationCode.user_id == user_with_scope.id).count() == 1


def test_consent_decide_approve_without_scope_returns_403(client, db_session, user_without_scope):
    request_id = _pending_authorization(db_session)
    client.post("/api/oauth/consent/login", data={"request_id": request_id, "email": user_without_scope.email, "password": "Segredo123!"})
    response = client.post("/api/oauth/consent/decide", data={"request_id": request_id, "decision": "approve"})
    assert response.status_code == 403


def test_validated_filters_rejects_unknown_key():
    """Regressão: `filters={"regional": ...}` (singular) era descartado em silêncio antes desta
    validação - a chave certa é `regionals` (plural, ver AiOrderFilters). Sem checagem nenhuma,
    isso passava como se o filtro tivesse sido aplicado, sem nenhum efeito real na consulta."""
    with pytest.raises(ValueError):
        _validated_filters({"regional": "UNI - JI PARANA"})


def test_validated_filters_accepts_known_keys_and_fills_defaults():
    result = _validated_filters({"regionals": ["UNI - JI PARANA"], "sectors": ["Manutenção"]})
    assert result["regionals"] == ["UNI - JI PARANA"]
    assert result["sectors"] == ["Manutenção"]
    assert result["team_models"] == []  # default de quem não foi filtrado, não ausente


def test_validated_filters_accepts_none():
    assert _validated_filters(None)["regionals"] == []
