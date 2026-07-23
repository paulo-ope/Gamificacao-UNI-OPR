from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import PERMISSION_LABELS, get_current_user, require_permission
from app.db.session import get_db
from app.models import AccessProfile, AccessProfilePermission, User, UserAccessProfile
from app.modules.operations.models import OperationOrder
from app.services.regional import normalize_regional
from app.modules.admin.schemas import (
    AccessProfileCreate,
    AccessProfileOut,
    AccessProfileUpdate,
    EcosystemPermissionOut,
)
from app.services.audit_log import record_audit_log, snapshot

router = APIRouter(prefix="/admin", tags=["admin"])


def _permission_module(permission: str) -> str:
    if permission.startswith("operations:"):
        return "Operação Analítica"
    if permission.startswith("admin:"):
        return "Administração"
    if permission.startswith("portal:"):
        return "Portal"
    return "Gamificação"


def _profile_out(profile: AccessProfile, user_count: int = 0) -> AccessProfileOut:
    return AccessProfileOut(
        id=profile.id,
        name=profile.name,
        description=profile.description,
        legacy_role=profile.legacy_role,
        active=profile.active,
        is_system=profile.is_system,
        permission_keys=sorted({item.permission for item in profile.permissions}),
        user_count=user_count,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def _validate_permissions(permission_keys: list[str]) -> list[str]:
    invalid = [permission for permission in permission_keys if permission not in PERMISSION_LABELS]
    if invalid:
        raise HTTPException(status_code=422, detail=f"Permissão inválida: {invalid[0]}.")
    return sorted(set(permission_keys))


def _replace_permissions(db: Session, profile: AccessProfile, permission_keys: list[str]) -> None:
    db.query(AccessProfilePermission).filter(AccessProfilePermission.profile_id == profile.id).delete(synchronize_session=False)
    for permission in _validate_permissions(permission_keys):
        db.add(AccessProfilePermission(profile_id=profile.id, permission=permission))


@router.get("/permissions", response_model=list[EcosystemPermissionOut])
def list_permissions(_: User = Depends(require_permission("admin:permissions:read"))):
    return [
        EcosystemPermissionOut(key=key, label=label, module=_permission_module(key))
        for key, label in sorted(PERMISSION_LABELS.items())
    ]


@router.get("/operation-regionals", response_model=list[str])
def list_operation_regionals(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("admin:users:read")),
):
    """Regionais disponíveis na base analítica para configurar escopos.

    O retorno é normalizado e único para que a mesma regional não apareça duas
    vezes por variações históricas de nome/código do IXC.
    """
    values = db.scalars(
        select(OperationOrder.regional)
        .where(OperationOrder.regional.is_not(None), OperationOrder.regional != "")
        .distinct()
    )
    return sorted(
        {
            normalized
            for value in values
            if (normalized := normalize_regional(str(value))) != "NAO IDENTIFICADO"
        },
        key=str.casefold,
    )


@router.get("/access-profiles", response_model=list[AccessProfileOut])
def list_access_profiles(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("admin:roles:read")),
):
    user_counts = {
        profile_id: count
        for profile_id, count in db.execute(
            select(UserAccessProfile.profile_id, func.count(UserAccessProfile.user_id)).group_by(UserAccessProfile.profile_id)
        ).all()
    }
    profiles = db.scalars(select(AccessProfile).order_by(AccessProfile.name.asc())).all()
    return [_profile_out(profile, user_counts.get(profile.id, 0)) for profile in profiles]


@router.post("/access-profiles", response_model=AccessProfileOut, status_code=201)
def create_access_profile(
    payload: AccessProfileCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("admin:roles:write")),
):
    name = payload.name.strip()
    exists = db.scalar(select(AccessProfile).where(func.lower(AccessProfile.name) == name.lower()))
    if exists:
        raise HTTPException(status_code=409, detail="Já existe um perfil com este nome.")
    profile = AccessProfile(name=name, description=payload.description, active=payload.active, is_system=False)
    db.add(profile)
    db.flush()
    _replace_permissions(db, profile, payload.permission_keys)
    record_audit_log(db, user, "create", "access_profiles", profile.id, None, snapshot(profile))
    db.commit()
    db.refresh(profile)
    return _profile_out(profile)


@router.put("/access-profiles/{profile_id}", response_model=AccessProfileOut)
def update_access_profile(
    profile_id: int,
    payload: AccessProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("admin:roles:write")),
):
    profile = db.get(AccessProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil de acesso não encontrado.")
    before = snapshot(profile)
    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"]:
        name = str(updates["name"]).strip()
        exists = db.scalar(select(AccessProfile).where(func.lower(AccessProfile.name) == name.lower()).where(AccessProfile.id != profile_id))
        if exists:
            raise HTTPException(status_code=409, detail="Já existe um perfil com este nome.")
        profile.name = name
    if "description" in updates:
        profile.description = updates["description"]
    if "active" in updates and updates["active"] is not None:
        profile.active = bool(updates["active"])
    if "permission_keys" in updates and updates["permission_keys"] is not None:
        _replace_permissions(db, profile, updates["permission_keys"])
    record_audit_log(db, user, "update", "access_profiles", profile.id, before, snapshot(profile))
    db.commit()
    db.refresh(profile)
    return _profile_out(profile)


@router.delete("/access-profiles/{profile_id}", response_model=AccessProfileOut)
def delete_access_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("admin:roles:write")),
):
    profile = db.get(AccessProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil de acesso não encontrado.")
    if profile.is_system:
        raise HTTPException(status_code=400, detail="Perfis do sistema não podem ser excluídos. Inative se necessário.")
    user_count = db.scalar(select(func.count(UserAccessProfile.user_id)).where(UserAccessProfile.profile_id == profile.id)) or 0
    if user_count:
        raise HTTPException(status_code=409, detail="Este perfil ainda está vinculado a usuários.")
    response = _profile_out(profile, user_count)
    before = snapshot(profile)
    record_audit_log(db, user, "delete", "access_profiles", profile.id, before, None)
    db.delete(profile)
    db.commit()
    return response
