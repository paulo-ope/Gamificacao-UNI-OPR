from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AiEndpointOut(BaseModel):
    key: str
    label: str
    description: str | None
    kind: str
    enabled_api: bool
    enabled_mcp: bool
    enabled_ai: bool
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AiEndpointUpdate(BaseModel):
    enabled_api: bool | None = None
    enabled_mcp: bool | None = None
    enabled_ai: bool | None = None

    model_config = ConfigDict(extra="forbid")


class AiFieldPermissionOut(BaseModel):
    entity: str
    field: str
    filterable: bool
    text_filterable: bool
    groupable: bool
    returnable: bool
    selectable: bool
    detail_available: bool
    sensitive: bool
    enabled: bool
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AiFieldPermissionUpdate(BaseModel):
    """`sensitive` de propósito fora deste schema - é um julgamento de segurança calculado pelo
    catálogo (`field_registry.py`), não um toggle administrativo casual (item 23 do pedido)."""

    filterable: bool | None = None
    text_filterable: bool | None = None
    groupable: bool | None = None
    returnable: bool | None = None
    selectable: bool | None = None
    detail_available: bool | None = None
    enabled: bool | None = None

    model_config = ConfigDict(extra="forbid")


class AiProfileEndpointGrantOut(BaseModel):
    profile_id: int
    endpoint_key: str
    granted: bool

    model_config = ConfigDict(from_attributes=True)


class AiProfileEndpointGrantUpsert(BaseModel):
    granted: bool

    model_config = ConfigDict(extra="forbid")


class AiProfileFieldGrantOut(BaseModel):
    profile_id: int
    entity: str
    field: str
    granted: bool

    model_config = ConfigDict(from_attributes=True)


class AiProfileFieldGrantUpsert(BaseModel):
    entity: str
    field: str
    granted: bool

    model_config = ConfigDict(extra="forbid")


# Item 15 do pedido: escopos que restringem o que um TOKEN pode fazer, além da política de
# campos/endpoints já aplicada por `ai_governance.gate`. Só "orders.read" (opr_search_orders) e
# "orders.detail" (opr_order_details) são de fato aplicados hoje (ver `ai/auth.py:enforce_token_scope`
# nas duas rotas correspondentes) - os demais ficam reservados para quando outros endpoints
# passarem a checar escopo, sem precisar de migration nova (a coluna já é uma lista livre).
AI_API_TOKEN_SCOPES = ["orders.read", "orders.detail", "orders.sla", "orders.aggregate", "infra.read", "users.read"]


class AiApiKeyOut(BaseModel):
    id: int
    source: Literal["token", "legacy"] = Field(
        description="'token' = AiApiToken (com escopo/expiração, Fase 5); 'legacy' = ApiKeyCredential (chaves emitidas antes da Fase 5, sem escopo - acesso irrestrito preservado)."
    )
    name: str
    owner_name: str
    owner_email: str
    key_prefix: str
    scopes: list[str] | None
    expires_at: datetime | None
    active: bool
    last_used_at: datetime | None
    created_at: datetime
    revoked_at: datetime | None


class AiApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = Field(default_factory=list)
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)

    model_config = ConfigDict(extra="forbid")

    @field_validator("scopes")
    @classmethod
    def _validate_scopes(cls, value: list[str]) -> list[str]:
        invalid = sorted(set(value) - set(AI_API_TOKEN_SCOPES))
        if invalid:
            raise ValueError(f"Escopo(s) inválido(s): {', '.join(invalid)}.")
        return value


class AiApiKeyCreateResponse(BaseModel):
    key: AiApiKeyOut
    raw_key: str = Field(description="Só é mostrada nesta resposta - não fica recuperável depois (só o hash é gravado).")


class AiAccessAuditLogOut(BaseModel):
    id: int
    occurred_at: datetime
    user_name: str | None
    user_email: str | None
    token_name: str | None
    origin: str
    endpoint_key: str
    filters_summary: dict | None
    fields_requested: list[str] | None
    response_mode: str | None
    result_count: int | None
    duration_ms: int | None
    status: str
    error_message: str | None
