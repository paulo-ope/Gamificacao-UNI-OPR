"""Tabelas do servidor OAuth do conector MCP remoto (Claude.ai/Cowork).

Implementa o papel de "authorization server" descrito na especificação de autorização do MCP
(RFC 6749/7591/7636), usando o `User`/login já existentes deste sistema como identidade - não é
um provedor OAuth de propósito geral, é só o suficiente para o SDK do MCP
(`OAuthAuthorizationServerProvider`, ver provider.py) emitir/validar token para o Claude.

Quatro tabelas, cada uma cobrindo uma etapa do fluxo:
- `McpOAuthClient`: quem é o "app" pedindo acesso (o Claude, registrado via DCR - Dynamic Client
  Registration - na primeira conexão).
- `McpOAuthPendingAuthorization`: o pedido de autorização em andamento, entre o Claude redirecionar
  o navegador pro `/authorize` e a pessoa efetivamente logar/aprovar na tela de consentimento -
  vida curta (minutos), nunca reaproveitado.
- `McpOAuthAuthorizationCode`: o código de uso único trocado por token depois que a pessoa aprova -
  vida curta (minutos), descartado após o uso.
- `McpOAuthToken`: o par access_token/refresh_token de fato usado em toda chamada de tool.

Tokens e códigos são guardados só como hash (SHA-256, não pbkdf2) - são strings aleatórias de alta
entropia geradas por este servidor (não senhas escolhidas por humano), então não precisam do custo
computacional do pbkdf2 (que seria pago em TODA chamada de tool, não só no login); o hash serve só
pra não deixar o segredo em texto puro no banco caso ele vaze por outro caminho (backup, dump).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models import utc_now


class McpOAuthClient(Base):
    """Um cliente OAuth registrado (hoje, sempre o Claude, via DCR em `/register`) - `client_id`
    é público (aparece em URLs de redirecionamento), nunca um segredo. `client_secret_hash` fica
    `None` para clientes públicos (o caso normal de DCR, protegido por PKCE em vez de segredo)."""

    __tablename__ = "mcp_oauth_clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    client_secret_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    redirect_uris: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    grant_types: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    response_types: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    token_endpoint_auth_method: Mapped[str] = mapped_column(String(40), nullable=False, default="none")
    scope: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class McpOAuthPendingAuthorization(Base):
    """Ponte entre `provider.authorize()` (chamado pelo SDK do MCP quando o Claude acessa
    `/authorize`) e a tela de login/consentimento própria deste app (`/api/oauth/consent`) - carrega
    os parâmetros da requisição OAuth (PKCE, redirect_uri, escopo) até a pessoa efetivamente decidir
    aprovar ou negar. `request_id` é a única coisa que trafega na URL do navegador."""

    __tablename__ = "mcp_oauth_pending_authorizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    redirect_uri: Mapped[str] = mapped_column(String(1000), nullable=False)
    redirect_uri_provided_explicitly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    code_challenge: Mapped[str] = mapped_column(String(255), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    state: Mapped[str | None] = mapped_column(String(500), nullable=True)
    resource: Mapped[str | None] = mapped_column(String(500), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class McpOAuthAuthorizationCode(Base):
    """Código de uso único emitido depois que a pessoa aprova na tela de consentimento - trocado
    por um token em `/token` (`provider.exchange_authorization_code`). `code_hash` é o SHA-256 do
    código real (que só existe em texto puro na URL de redirecionamento pro Claude, nunca
    persistido). `used_at` marca uso (nunca é reutilizável - achado de segurança padrão do fluxo
    de authorization code: um código reaproveitado indica o código foi interceptado)."""

    __tablename__ = "mcp_oauth_authorization_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    redirect_uri: Mapped[str] = mapped_column(String(1000), nullable=False)
    redirect_uri_provided_explicitly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    code_challenge: Mapped[str] = mapped_column(String(255), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    resource: Mapped[str | None] = mapped_column(String(500), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class McpOAuthToken(Base):
    """Par access_token/refresh_token emitido pela troca do código (ou por um refresh). Uma linha
    por par - refresh rotaciona (gera uma linha nova, revoga a antiga) em vez de atualizar no
    lugar, seguindo a exigência da spec de autorização do MCP de rotacionar refresh token de
    cliente público a cada uso (mitiga replay de um refresh token roubado)."""

    __tablename__ = "mcp_oauth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    access_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    refresh_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    resource: Mapped[str | None] = mapped_column(String(500), nullable=True)
    access_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    refresh_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
