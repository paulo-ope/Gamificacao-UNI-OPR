"""Rotas administrativas da Gestão API/MCP (item 11/24 do pedido de governança IA/MCP) - CRUD sobre
`AiEndpoint`/`AiFieldPermission`/grants por perfil/tokens/auditoria. Toda escrita chama
`bump_policy_version` (efeito imediato, sem reiniciar o processo) e `record_audit_log` (mesma
trilha de auditoria administrativa já usada pelo resto do `admin` module)."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_api_key, hash_password, require_permission
from app.db.session import get_db
from app.models import AccessProfile, User
from app.modules.ai.auth import API_KEY_PREFIX_LENGTH
from app.modules.ai.models import ApiKeyCredential
from app.modules.ai_governance.field_registry import build_field_registry
from app.modules.ai_governance.models import (
    AiAccessAuditLog,
    AiApiToken,
    AiEndpoint,
    AiFieldPermission,
    AiProfileEndpointGrant,
    AiProfileFieldGrant,
)
from app.modules.ai_governance.policy import bump_policy_version
from app.modules.ai_governance.schemas import (
    AiAccessAuditLogOut,
    AiApiKeyCreate,
    AiApiKeyCreateResponse,
    AiApiKeyOut,
    AiEndpointOut,
    AiEndpointUpdate,
    AiFieldPermissionOut,
    AiFieldPermissionUpdate,
    AiProfileEndpointGrantOut,
    AiProfileEndpointGrantUpsert,
    AiProfileFieldGrantOut,
    AiProfileFieldGrantUpsert,
)
from app.services.audit_log import record_audit_log, snapshot

router = APIRouter(prefix="/admin/ai-governance", tags=["admin-ai-governance"])

SERVICE_USER_EMAIL = "ai-service@internal.souuni.com"
SERVICE_USER_NAME = "Serviço de IA"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/endpoints", response_model=list[AiEndpointOut])
def list_endpoints(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("admin:ai_governance:read")),
):
    return list(db.scalars(select(AiEndpoint).order_by(AiEndpoint.key.asc())))


@router.patch("/endpoints/{endpoint_key}", response_model=AiEndpointOut)
def update_endpoint(
    endpoint_key: str,
    payload: AiEndpointUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("admin:ai_governance:write")),
):
    endpoint = db.scalar(select(AiEndpoint).where(AiEndpoint.key == endpoint_key))
    if not endpoint:
        raise HTTPException(status_code=404, detail="Endpoint não encontrado.")
    before = snapshot(endpoint)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(endpoint, field, value)
    record_audit_log(db, user, "update", "ai_endpoints", endpoint.key, before, snapshot(endpoint))
    db.commit()
    bump_policy_version(db)
    db.refresh(endpoint)
    return endpoint


# ---------------------------------------------------------------------------
# Campos
# ---------------------------------------------------------------------------


def _ensure_field_permission_rows_exist(db: Session) -> None:
    """As linhas de `AiFieldPermission` são semeadas no startup (`bootstrap.py`), mas um campo novo
    introduzido depois (ex.: uma migration nova) só ganha linha na próxima subida do processo -
    aqui a tela de administração nunca deveria mostrar "campo inexistente" por causa disso, então
    completa qualquer lacuna sob demanda com os defaults calculados do catálogo."""
    existing = {(row.entity, row.field) for row in db.execute(select(AiFieldPermission.entity, AiFieldPermission.field)).all()}
    changed = False
    for entity_fields in build_field_registry().values():
        for descriptor in entity_fields.values():
            if (descriptor.entity, descriptor.field) in existing:
                continue
            db.add(
                AiFieldPermission(
                    entity=descriptor.entity,
                    field=descriptor.field,
                    filterable=descriptor.filterable,
                    text_filterable=descriptor.text_filterable,
                    groupable=descriptor.groupable,
                    returnable=descriptor.returnable,
                    selectable=descriptor.selectable,
                    detail_available=descriptor.detail_available,
                    sensitive=descriptor.sensitive,
                    enabled=descriptor.default_enabled,
                )
            )
            changed = True
    if changed:
        db.commit()


@router.get("/fields", response_model=list[AiFieldPermissionOut])
def list_field_permissions(
    entity: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("admin:ai_governance:read")),
):
    _ensure_field_permission_rows_exist(db)
    stmt = select(AiFieldPermission).order_by(AiFieldPermission.entity.asc(), AiFieldPermission.field.asc())
    if entity:
        stmt = stmt.where(AiFieldPermission.entity == entity)
    return list(db.scalars(stmt))


@router.patch("/fields/{entity}/{field}", response_model=AiFieldPermissionOut)
def update_field_permission(
    entity: str,
    field: str,
    payload: AiFieldPermissionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("admin:ai_governance:write")),
):
    _ensure_field_permission_rows_exist(db)
    permission = db.scalar(select(AiFieldPermission).where(AiFieldPermission.entity == entity, AiFieldPermission.field == field))
    if not permission:
        raise HTTPException(status_code=404, detail="Campo não encontrado no catálogo.")
    before = snapshot(permission)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(permission, key, value)
    permission.updated_by = user.id
    record_audit_log(db, user, "update", "ai_field_permissions", f"{entity}.{field}", before, snapshot(permission))
    db.commit()
    bump_policy_version(db)
    db.refresh(permission)
    return permission


# ---------------------------------------------------------------------------
# Perfis (grants) - reusa AccessProfile já existente, não cria RBAC paralelo (item 12 do pedido)
# ---------------------------------------------------------------------------


def _active_profile_or_404(db: Session, profile_id: int) -> AccessProfile:
    profile = db.get(AccessProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil de acesso não encontrado.")
    return profile


@router.get("/profiles/{profile_id}/endpoint-grants", response_model=list[AiProfileEndpointGrantOut])
def list_profile_endpoint_grants(
    profile_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("admin:ai_governance:read")),
):
    _active_profile_or_404(db, profile_id)
    return list(db.scalars(select(AiProfileEndpointGrant).where(AiProfileEndpointGrant.profile_id == profile_id)))


@router.put("/profiles/{profile_id}/endpoint-grants/{endpoint_key}", response_model=AiProfileEndpointGrantOut)
def upsert_profile_endpoint_grant(
    profile_id: int,
    endpoint_key: str,
    payload: AiProfileEndpointGrantUpsert,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("admin:ai_governance:write")),
):
    _active_profile_or_404(db, profile_id)
    if not db.scalar(select(AiEndpoint.key).where(AiEndpoint.key == endpoint_key)):
        raise HTTPException(status_code=404, detail="Endpoint não encontrado.")
    grant = db.scalar(
        select(AiProfileEndpointGrant).where(
            AiProfileEndpointGrant.profile_id == profile_id, AiProfileEndpointGrant.endpoint_key == endpoint_key
        )
    )
    before = snapshot(grant) if grant else None
    if not grant:
        grant = AiProfileEndpointGrant(profile_id=profile_id, endpoint_key=endpoint_key)
        db.add(grant)
    grant.granted = payload.granted
    record_audit_log(db, user, "upsert", "ai_profile_endpoint_grants", f"{profile_id}:{endpoint_key}", before, snapshot(grant))
    db.commit()
    bump_policy_version(db)
    db.refresh(grant)
    return grant


@router.delete("/profiles/{profile_id}/endpoint-grants/{endpoint_key}", status_code=204)
def delete_profile_endpoint_grant(
    profile_id: int,
    endpoint_key: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("admin:ai_governance:write")),
):
    grant = db.scalar(
        select(AiProfileEndpointGrant).where(
            AiProfileEndpointGrant.profile_id == profile_id, AiProfileEndpointGrant.endpoint_key == endpoint_key
        )
    )
    if not grant:
        raise HTTPException(status_code=404, detail="Restrição não encontrada.")
    record_audit_log(db, user, "delete", "ai_profile_endpoint_grants", f"{profile_id}:{endpoint_key}", snapshot(grant), None)
    db.delete(grant)
    db.commit()
    bump_policy_version(db)


@router.get("/profiles/{profile_id}/field-grants", response_model=list[AiProfileFieldGrantOut])
def list_profile_field_grants(
    profile_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("admin:ai_governance:read")),
):
    _active_profile_or_404(db, profile_id)
    return list(db.scalars(select(AiProfileFieldGrant).where(AiProfileFieldGrant.profile_id == profile_id)))


@router.put("/profiles/{profile_id}/field-grants", response_model=AiProfileFieldGrantOut)
def upsert_profile_field_grant(
    profile_id: int,
    payload: AiProfileFieldGrantUpsert,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("admin:ai_governance:write")),
):
    _active_profile_or_404(db, profile_id)
    grant = db.scalar(
        select(AiProfileFieldGrant).where(
            AiProfileFieldGrant.profile_id == profile_id,
            AiProfileFieldGrant.entity == payload.entity,
            AiProfileFieldGrant.field == payload.field,
        )
    )
    before = snapshot(grant) if grant else None
    if not grant:
        grant = AiProfileFieldGrant(profile_id=profile_id, entity=payload.entity, field=payload.field)
        db.add(grant)
    grant.granted = payload.granted
    record_audit_log(
        db, user, "upsert", "ai_profile_field_grants", f"{profile_id}:{payload.entity}.{payload.field}", before, snapshot(grant)
    )
    db.commit()
    bump_policy_version(db)
    db.refresh(grant)
    return grant


@router.delete("/profiles/{profile_id}/field-grants/{entity}/{field}", status_code=204)
def delete_profile_field_grant(
    profile_id: int,
    entity: str,
    field: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("admin:ai_governance:write")),
):
    grant = db.scalar(
        select(AiProfileFieldGrant).where(
            AiProfileFieldGrant.profile_id == profile_id,
            AiProfileFieldGrant.entity == entity,
            AiProfileFieldGrant.field == field,
        )
    )
    if not grant:
        raise HTTPException(status_code=404, detail="Restrição não encontrada.")
    record_audit_log(db, user, "delete", "ai_profile_field_grants", f"{profile_id}:{entity}.{field}", snapshot(grant), None)
    db.delete(grant)
    db.commit()
    bump_policy_version(db)


# ---------------------------------------------------------------------------
# Tokens - Fase 5 do plano de migração: novas emissões usam `AiApiToken` (escopo + expiração,
# `ai_governance.models`, criada na Fase 1); `ApiKeyCredential` (app.modules.ai.models, mesma
# tabela do CLI `ai/cli.py`) continua listada/revogável para as chaves emitidas antes desta fase -
# nunca perdem acesso por causa da migração (item 26 do pedido: preservar o comportamento atual).
# ---------------------------------------------------------------------------


def _token_out(token: AiApiToken) -> AiApiKeyOut:
    return AiApiKeyOut(
        id=token.id,
        source="token",
        name=token.name,
        owner_name=token.user.name if token.user else "",
        owner_email=token.user.email if token.user else "",
        key_prefix=token.key_prefix,
        scopes=list(token.scopes or []),
        expires_at=token.expires_at,
        active=token.active and token.revoked_at is None,
        last_used_at=token.last_used_at,
        created_at=token.created_at,
        revoked_at=token.revoked_at,
    )


def _legacy_credential_out(credential: ApiKeyCredential) -> AiApiKeyOut:
    return AiApiKeyOut(
        id=credential.id,
        source="legacy",
        name=credential.name,
        owner_name=credential.user.name if credential.user else "",
        owner_email=credential.user.email if credential.user else "",
        key_prefix=credential.key_prefix,
        scopes=None,
        expires_at=None,
        active=credential.active and credential.revoked_at is None,
        last_used_at=credential.last_used_at,
        created_at=credential.created_at,
        revoked_at=credential.revoked_at,
    )


@router.get("/tokens", response_model=list[AiApiKeyOut])
def list_tokens(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("admin:ai_governance:read")),
):
    tokens = db.scalars(select(AiApiToken).order_by(AiApiToken.created_at.desc())).all()
    credentials = db.scalars(select(ApiKeyCredential).order_by(ApiKeyCredential.created_at.desc())).all()
    combined = [_token_out(token) for token in tokens] + [_legacy_credential_out(credential) for credential in credentials]
    combined.sort(key=lambda item: item.created_at, reverse=True)
    return combined


def _service_user(db: Session) -> User:
    # Mesmo usuário de serviço do CLI (`ai/cli.py:create_service_user_and_key`) - uma única
    # identidade de máquina para todos os tokens emitidos pela tela, escopada só por `ai:query`
    # (papel `ai_service`). O escopo de FATO de cada token vem de `AiApiToken.scopes`, não deste
    # usuário - emitir um usuário de serviço por token não traz benefício adicional.
    service_user = db.scalar(select(User).where(User.email == SERVICE_USER_EMAIL))
    if not service_user:
        service_user = User(
            name=SERVICE_USER_NAME,
            email=SERVICE_USER_EMAIL,
            password_hash=hash_password(secrets.token_urlsafe(32)),
            role="ai_service",
            active=True,
        )
        db.add(service_user)
        db.flush()
    return service_user


@router.post("/tokens", response_model=AiApiKeyCreateResponse, status_code=201)
def create_token(
    payload: AiApiKeyCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("admin:ai_tokens:manage")),
):
    service_user = _service_user(db)
    expires_at = (
        datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days) if payload.expires_in_days else None
    )
    raw_key = secrets.token_urlsafe(32)
    token = AiApiToken(
        user_id=service_user.id,
        name=payload.name,
        scopes=payload.scopes,
        key_prefix=raw_key[:API_KEY_PREFIX_LENGTH],
        key_hash=hash_api_key(raw_key),
        expires_at=expires_at,
        created_by=user.id,
    )
    db.add(token)
    record_audit_log(db, user, "create", "ai_api_tokens", None, None, {"name": payload.name, "scopes": payload.scopes, "expires_at": expires_at.isoformat() if expires_at else None})
    db.commit()
    db.refresh(token)
    return AiApiKeyCreateResponse(key=_token_out(token), raw_key=raw_key)


@router.delete("/tokens/{source}/{token_id}", response_model=AiApiKeyOut)
def revoke_token(
    source: Literal["token", "legacy"],
    token_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("admin:ai_tokens:manage")),
):
    if source == "token":
        entity = db.get(AiApiToken, token_id)
        table_name = "ai_api_tokens"
        to_out = _token_out
    else:
        entity = db.get(ApiKeyCredential, token_id)
        table_name = "api_key_credentials"
        to_out = _legacy_credential_out
    if not entity:
        raise HTTPException(status_code=404, detail="Token não encontrado.")
    before = snapshot(entity)
    entity.active = False
    entity.revoked_at = datetime.now(timezone.utc)
    record_audit_log(db, user, "revoke", table_name, entity.id, before, snapshot(entity))
    db.commit()
    db.refresh(entity)
    return to_out(entity)


# ---------------------------------------------------------------------------
# Auditoria de uso (leitura) - item 14 do pedido
# ---------------------------------------------------------------------------


@router.get("/audit-logs", response_model=list[AiAccessAuditLogOut])
def list_audit_logs(
    origin: str | None = Query(default=None),
    endpoint_key: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("admin:ai_governance:read")),
):
    stmt = select(AiAccessAuditLog).order_by(AiAccessAuditLog.occurred_at.desc()).limit(limit)
    if origin:
        stmt = stmt.where(AiAccessAuditLog.origin == origin)
    if endpoint_key:
        stmt = stmt.where(AiAccessAuditLog.endpoint_key == endpoint_key)
    if status:
        stmt = stmt.where(AiAccessAuditLog.status == status)
    rows = db.scalars(stmt).all()
    users_by_id = {user.id: user for user in db.scalars(select(User))}
    token_names_by_id = {token.id: token.name for token in db.scalars(select(AiApiToken))}
    return [
        AiAccessAuditLogOut(
            id=row.id,
            occurred_at=row.occurred_at,
            user_name=users_by_id[row.user_id].name if row.user_id in users_by_id else None,
            user_email=users_by_id[row.user_id].email if row.user_id in users_by_id else None,
            token_name=token_names_by_id.get(row.token_id),
            origin=row.origin,
            endpoint_key=row.endpoint_key,
            filters_summary=row.filters_summary,
            fields_requested=row.fields_requested,
            response_mode=row.response_mode,
            result_count=row.result_count,
            duration_ms=row.duration_ms,
            status=row.status,
            error_message=row.error_message,
        )
        for row in rows
    ]
