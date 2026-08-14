"""Ponto único de aplicação da política (item 13/16 do pedido: "a validação deve ocorrer no
backend", "o MCP deve refletir a mesma camada de autorização da API"). `enforce_ai_endpoint` é uma
dependency do FastAPI para uso direto em rotas; `enforce_ai_endpoint_for_user` é a função crua por
trás dela, usada também pelas tools MCP (que não passam pelo sistema de dependencies do FastAPI)."""
from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models import User
from app.modules.ai_governance.policy import EffectivePolicy, resolve_effective_policy


def enforce_ai_endpoint_for_user(db: Session, user: User, endpoint_key: str, origin: str) -> EffectivePolicy:
    policy = resolve_effective_policy(db, user)
    if not policy.endpoint_allowed(endpoint_key, origin):
        raise HTTPException(
            status_code=403,
            detail=f"Endpoint '{endpoint_key}' não está habilitado para este perfil ({origin}).",
        )
    return policy


def enforce_ai_endpoint(endpoint_key: str, origin: str = "api"):
    """Dependency FastAPI - usar como `Depends(enforce_ai_endpoint("operations.orders.list"))` nos
    endpoints que a Fase 2 for migrando para a política central."""

    def dependency(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        enforce_ai_endpoint_for_user(db, user, endpoint_key, origin)
        return user

    return dependency


def enforce_requested_fields(policy: EffectivePolicy, entity: str, requested_fields: list[str] | None, capability: str = "selectable") -> list[str] | None:
    """Valida um `fields=[...]` explícito contra a política - item 4/13 do pedido: rejeitar
    explicitamente campos não autorizados, nunca omitir silenciosamente. `requested_fields=None`
    significa "nenhuma seleção pedida" (o chamador decide o conjunto default, não este gate)."""
    if requested_fields is None:
        return None
    invalid = [name for name in requested_fields if not policy.field_allowed(entity, name, capability)]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Campo(s) não autorizados em 'fields': {', '.join(sorted(invalid))}.",
        )
    return requested_fields


def enforce_filter_field(policy: EffectivePolicy, entity: str, field_name: str, capability: str = "filterable") -> None:
    """Mesma ideia de `enforce_requested_fields`, para um único campo de filtro/agrupamento -
    usar antes de aplicar cada filtro/`group_by` recebido de um endpoint já migrado para a política."""
    if not policy.field_allowed(entity, field_name, capability):
        raise HTTPException(
            status_code=422,
            detail=f"Campo '{field_name}' não autorizado para '{capability}'.",
        )


def enforce_date_field(policy: EffectivePolicy, entity: str, date_field: str | None, valid_date_fields: dict) -> str | None:
    """Valida um `date_field=...` explícito - item 7 do pedido (opened_at/closed_at/scheduled_at/
    etc.). `valid_date_fields` é o dict de colunas do módulo chamador (ex.:
    `operations.queries.DATE_FIELD_COLUMNS`) - este gate não conhece o schema de nenhum módulo
    específico, só valida nome+autorização; fonte única usada tanto por `operations/router.py`
    quanto por `ai/router.py`/`mcp_connector/server.py` (item 25/16 do pedido)."""
    if date_field is None:
        return None
    if date_field not in valid_date_fields:
        raise HTTPException(status_code=422, detail=f"date_field inválido: {date_field}.")
    enforce_filter_field(policy, entity, date_field, "filterable")
    return date_field
