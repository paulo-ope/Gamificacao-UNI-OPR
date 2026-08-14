from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AiEndpoint(Base):
    """Um endpoint da API ou tool MCP governável pela Administração (item 11 do pedido de
    governança IA/MCP) - `key` é o identificador lógico usado pelo gate (`ai_governance/gate.py`),
    não necessariamente igual ao path HTTP ou ao nome da tool (ex.: "operations.orders.detail" cobre
    tanto `GET /operations/orders/{id}` quanto uma futura tool MCP equivalente)."""

    __tablename__ = "ai_endpoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # "api" | "mcp" | "both" - só documenta onde o endpoint existe fisicamente; o que de fato
    # controla acesso são os três switches abaixo.
    kind: Mapped[str] = mapped_column(String(10), nullable=False, default="both")
    enabled_api: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enabled_mcp: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enabled_ai: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class AiFieldPermission(Base):
    """Estado administrável de um campo de uma entidade (item 3/10/23 do pedido) - `entity`+`field`
    é a chave real (ver `field_registry.py` para o catálogo base de capacidades derivado dos models
    SQLAlchemy). Uma linha aqui é sempre um OVERRIDE do default do catálogo: a ausência de linha
    significa "usar o default calculado do código", nunca "bloqueado" nem "liberado"."""

    __tablename__ = "ai_field_permissions"
    __table_args__ = (UniqueConstraint("entity", "field", name="uq_ai_field_permissions_entity_field"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    field: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    filterable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    text_filterable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    groupable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    returnable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    selectable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    detail_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Chave-mestra: quando False, o campo fica indisponível independente das capacidades acima
    # (é o "liga/desliga" que a Administração usa sem precisar reconfigurar cada capacidade).
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class AiProfileEndpointGrant(Base):
    """Restrição adicional (opcional) de um `AccessProfile` já existente sobre um endpoint - reusa
    o RBAC do ecossistema (`app.models.AccessProfile`), não cria hierarquia de perfil paralela
    (item 12/13 do pedido). Ausência de qualquer linha para um perfil+endpoint significa "sem
    restrição adicional" (o endpoint fica disponível pelo estado geral de `AiEndpoint`); a presença
    de ao menos uma linha liga o perfil a um modo allow-list para aquele endpoint."""

    __tablename__ = "ai_profile_endpoint_grants"
    __table_args__ = (UniqueConstraint("profile_id", "endpoint_key", name="uq_ai_profile_endpoint_grant"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("access_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    endpoint_key: Mapped[str] = mapped_column(ForeignKey("ai_endpoints.key", ondelete="CASCADE"), nullable=False, index=True)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class AiProfileFieldGrant(Base):
    """Mesmo racional de `AiProfileEndpointGrant`, só que por campo - permite, por exemplo, liberar
    `technical_report` só para o perfil Gestor mesmo que o campo esteja `enabled=True` em
    `AiFieldPermission` para o sistema como um todo."""

    __tablename__ = "ai_profile_field_grants"
    __table_args__ = (UniqueConstraint("profile_id", "entity", "field", name="uq_ai_profile_field_grant"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("access_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    entity: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    field: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class AiApiToken(Base):
    """Evolução de `app.modules.ai.models.ApiKeyCredential` com escopo/expiração (item 15 do
    pedido) - a partir da Fase 5 do plano de migração é o que `app.modules.ai.auth` emite/valida
    para tokens novos; `ApiKeyCredential` continua sendo aceita para as chaves emitidas antes desta
    fase (sem escopo, acesso irrestrito - ver `ai/auth.py:ApiKeyContext`)."""

    __tablename__ = "ai_api_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("access_profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(foreign_keys=[user_id])  # noqa: F821


class AiAccessAuditLog(Base):
    """Auditoria de uso de API/MCP por agentes de IA (item 14 do pedido) - grava metadado da
    consulta, nunca o conteúdo sensível retornado (`filters_summary` guarda só nomes de campo e
    quantidade de valores, não os valores em si; ver `audit.py:summarize_filters`)."""

    __tablename__ = "ai_access_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    token_id: Mapped[int | None] = mapped_column(ForeignKey("ai_api_tokens.id", ondelete="SET NULL"), nullable=True, index=True)
    origin: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    endpoint_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    filters_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fields_requested: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    response_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    result_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True, default="success")
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
