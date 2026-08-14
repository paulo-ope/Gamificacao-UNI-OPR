"""Implementação de `OAuthAuthorizationServerProvider` (SDK do MCP) ligada ao `User`/login já
existentes deste sistema - ver models.py para o que cada tabela guarda e por quê.

Cada método aqui abre e fecha sua própria sessão de banco (`SessionLocal`) - o SDK chama estes
métodos diretamente (fora do ciclo de request do FastAPI), então não há `Depends(get_db)`
disponível, mesmo padrão já usado em `ai/cli.py` para código que roda fora de uma rota HTTP normal.

A maior parte da validação de segurança (PKCE, expiração de código, client_id/redirect_uri
batendo) já é feita pelo SDK ANTES de chamar `exchange_authorization_code`/`exchange_refresh_token`
(conferido lendo o código-fonte do SDK, `mcp.server.auth.handlers.token`) - os métodos aqui só
precisam ler/gravar o estado correspondente, não reimplementar essas checagens.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    RegistrationError,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import AccessProfile, User

from .models import (
    McpOAuthAuthorizationCode,
    McpOAuthClient,
    McpOAuthPendingAuthorization,
    McpOAuthToken,
)

# Único escopo que este servidor conhece - o mesmo nome de permissão já usado pela chave de API
# do módulo `ai` (ver app/core/security.py). Não existe conceito de escopo mais granular aqui: quem
# aprova o consentimento está dando acesso de LEITURA à Operação Analítica, ponto.
SCOPE = "ai:query"

ACCESS_TOKEN_TTL = timedelta(hours=1)
REFRESH_TOKEN_TTL = timedelta(days=30)
AUTHORIZATION_CODE_TTL = timedelta(minutes=5)
PENDING_AUTHORIZATION_TTL = timedelta(minutes=15)


def _hash_token(raw: str) -> str:
    # SHA-256 simples (não pbkdf2/hash_api_key) - ver docstring de models.py sobre por quê:
    # tokens de alta entropia gerados por nós, não segredo escolhido por humano.
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _generate_secret(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def _as_utc(value: datetime) -> datetime:
    """SQLite (usado nos testes) devolve `DateTime(timezone=True)` sem tzinfo mesmo tendo guardado
    um valor UTC-aware (o Postgres de produção preserva certinho) - sem isso, comparar ou chamar
    `.timestamp()` num datetime "naive" lido do banco assumiria fuso LOCAL da máquina em vez de
    UTC, quebrando expiração de código/token de forma silenciosa e dependente de fuso horário."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _mcp_issuer_url() -> str:
    settings = get_settings()
    if not settings.public_base_url:
        raise RuntimeError(
            "PUBLIC_BASE_URL não configurada - obrigatória para o conector MCP remoto "
            "(usada como issuer/resource server nos metadados OAuth)."
        )
    return f"{settings.public_base_url.rstrip('/')}{settings.api_prefix}/mcp"


class OprMcpOAuthProvider(OAuthAuthorizationServerProvider):
    # --- Clientes (registro dinâmico, RFC 7591) --------------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        with SessionLocal() as db:
            row = db.query(McpOAuthClient).filter(McpOAuthClient.client_id == client_id).one_or_none()
            if row is None:
                return None
            return OAuthClientInformationFull(
                client_id=row.client_id,
                client_secret=None,  # nunca devolvido de volta - só validado na hora de usar
                redirect_uris=[AnyUrl(uri) for uri in row.redirect_uris],
                token_endpoint_auth_method=row.token_endpoint_auth_method,
                grant_types=row.grant_types or ["authorization_code", "refresh_token"],
                response_types=row.response_types or ["code"],
                client_name=row.client_name,
                scope=row.scope,
            )

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            raise RegistrationError(error="invalid_client_metadata", error_description="client_id ausente.")
        with SessionLocal() as db:
            db.add(
                McpOAuthClient(
                    client_id=client_info.client_id,
                    client_secret_hash=_hash_token(client_info.client_secret) if client_info.client_secret else None,
                    client_name=client_info.client_name,
                    redirect_uris=[str(uri) for uri in (client_info.redirect_uris or [])],
                    grant_types=list(client_info.grant_types),
                    response_types=list(client_info.response_types),
                    token_endpoint_auth_method=client_info.token_endpoint_auth_method or "none",
                    scope=client_info.scope,
                )
            )
            db.commit()

    # --- Autorização (redireciona pra tela de login/consentimento própria) -----------------

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        requested_scopes = params.scopes or [SCOPE]
        if any(scope != SCOPE for scope in requested_scopes):
            raise AuthorizeError(error="invalid_scope", error_description=f"Único escopo suportado: {SCOPE}.")

        request_id = _generate_secret()
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            db.add(
                McpOAuthPendingAuthorization(
                    request_id=request_id,
                    client_id=client.client_id,
                    redirect_uri=str(params.redirect_uri),
                    redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
                    code_challenge=params.code_challenge,
                    scopes=requested_scopes,
                    state=params.state,
                    resource=params.resource,
                    expires_at=now + PENDING_AUTHORIZATION_TTL,
                )
            )
            db.commit()

        settings = get_settings()
        base = settings.public_base_url.rstrip("/")
        return f"{base}{settings.api_prefix}/oauth/consent?request_id={request_id}"

    # --- Código de autorização --------------------------------------------------------------

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        code_hash = _hash_token(authorization_code)
        with SessionLocal() as db:
            row = (
                db.query(McpOAuthAuthorizationCode)
                .filter(McpOAuthAuthorizationCode.code_hash == code_hash, McpOAuthAuthorizationCode.client_id == client.client_id)
                .one_or_none()
            )
            if row is None or row.used_at is not None:
                return None
            return AuthorizationCode(
                code=authorization_code,
                scopes=row.scopes,
                expires_at=_as_utc(row.expires_at).timestamp(),
                client_id=row.client_id,
                code_challenge=row.code_challenge,
                redirect_uri=AnyUrl(row.redirect_uri),
                redirect_uri_provided_explicitly=row.redirect_uri_provided_explicitly,
                resource=row.resource,
                subject=str(row.user_id),
            )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        code_hash = _hash_token(authorization_code.code)
        with SessionLocal() as db:
            row = db.query(McpOAuthAuthorizationCode).filter(McpOAuthAuthorizationCode.code_hash == code_hash).one_or_none()
            if row is None or row.used_at is not None:
                raise TokenError(error="invalid_grant", error_description="Código de autorização já usado ou inexistente.")
            row.used_at = datetime.now(timezone.utc)
            return _issue_token(db, client_id=client.client_id, user_id=row.user_id, scopes=row.scopes, resource=row.resource)

    # --- Refresh token -----------------------------------------------------------------------

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        token_hash = _hash_token(refresh_token)
        with SessionLocal() as db:
            row = (
                db.query(McpOAuthToken)
                .filter(McpOAuthToken.refresh_token_hash == token_hash, McpOAuthToken.client_id == client.client_id)
                .one_or_none()
            )
            if row is None or row.revoked_at is not None:
                return None
            return RefreshToken(
                token=refresh_token,
                client_id=row.client_id,
                scopes=row.scopes,
                expires_at=int(_as_utc(row.refresh_expires_at).timestamp()) if row.refresh_expires_at else None,
                subject=str(row.user_id),
            )

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        token_hash = _hash_token(refresh_token.token)
        with SessionLocal() as db:
            row = db.query(McpOAuthToken).filter(McpOAuthToken.refresh_token_hash == token_hash).one_or_none()
            if row is None or row.revoked_at is not None:
                raise TokenError(error="invalid_grant", error_description="Refresh token inexistente ou revogado.")
            # Rotação: revoga o par antigo e emite um novo, em vez de reescrever no lugar (ver
            # docstring de McpOAuthToken sobre por quê - exigência da spec pra cliente público).
            row.revoked_at = datetime.now(timezone.utc)
            return _issue_token(db, client_id=client.client_id, user_id=row.user_id, scopes=scopes or row.scopes, resource=row.resource)

    # --- Access token (validado em toda chamada de tool) --------------------------------------

    async def load_access_token(self, token: str) -> AccessToken | None:
        token_hash = _hash_token(token)
        with SessionLocal() as db:
            row = db.query(McpOAuthToken).filter(McpOAuthToken.access_token_hash == token_hash).one_or_none()
            if row is None or row.revoked_at is not None:
                return None
            if _as_utc(row.access_expires_at) < datetime.now(timezone.utc):
                return None
            return AccessToken(
                token=token,
                client_id=row.client_id,
                scopes=row.scopes,
                expires_at=int(_as_utc(row.access_expires_at).timestamp()),
                resource=row.resource,
                subject=str(row.user_id),
            )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        token_hash = _hash_token(token.token)
        with SessionLocal() as db:
            row = (
                db.query(McpOAuthToken)
                .filter(
                    (McpOAuthToken.access_token_hash == token_hash) | (McpOAuthToken.refresh_token_hash == token_hash)
                )
                .one_or_none()
            )
            if row is not None:
                row.revoked_at = datetime.now(timezone.utc)
                db.commit()


def _issue_token(db, *, client_id: str, user_id: int, scopes: list[str], resource: str | None) -> OAuthToken:
    now = datetime.now(timezone.utc)
    raw_access = _generate_secret()
    raw_refresh = _generate_secret()
    db.add(
        McpOAuthToken(
            access_token_hash=_hash_token(raw_access),
            refresh_token_hash=_hash_token(raw_refresh),
            client_id=client_id,
            user_id=user_id,
            scopes=scopes,
            resource=resource,
            access_expires_at=now + ACCESS_TOKEN_TTL,
            refresh_expires_at=now + REFRESH_TOKEN_TTL,
        )
    )
    db.commit()
    return OAuthToken(
        access_token=raw_access,
        refresh_token=raw_refresh,
        expires_in=int(ACCESS_TOKEN_TTL.total_seconds()),
        scope=" ".join(scopes),
    )


def resolve_user_for_access_token(access_token: AccessToken) -> User | None:
    """Resolve o `User` autenticado a partir do `AccessToken.subject` (id do usuário, guardado
    como string) - chamado pelas tools do MCP (ver server.py) via `get_access_token()`."""
    if not access_token.subject:
        return None
    with SessionLocal() as db:
        # Carrega `access_profiles`/`permissions` ANTES do expunge - achado real: sem isso,
        # `permissions_for_user` (chamado pelas tools do MCP com a sessão original já fechada)
        # tentava lazy-load em `user.access_profiles` e estourava "Parent instance <User> is not
        # bound to a Session".
        user = db.get(
            User,
            int(access_token.subject),
            options=[selectinload(User.access_profiles).selectinload(AccessProfile.permissions)],
        )
        if user is None or not user.active:
            return None
        db.expunge(user)
        return user
