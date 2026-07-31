from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import PERMISSION_LABELS, get_current_user, require_permission
from app.db.session import get_db
from app.models import AccessProfile, AccessProfilePermission, Collaborator, User, UserAccessProfile, WorkspaceModuleVisibility
from app.modules.registry import get_module, list_modules
from app.modules.operations.models import OperationOrder
from app.services.regional import normalize_regional
from app.modules.admin.schemas import (
    AccessProfileCreate,
    AccessProfileOut,
    AccessProfileUpdate,
    AdminPeopleStructureOut,
    AdminModuleUserVisibilityOut,
    AdminModuleUserVisibilityUpsert,
    AdminModuleVisibilityUpdate,
    AdminWorkspaceModuleOut,
    AdminModuleProfileVisibilityOut,
    AdminPersonStructureOut,
    AdminPersonStructureUpdate,
    AdminStructureOption,
    EcosystemPermissionOut,
)
from app.services.audit_log import record_audit_log, snapshot

router = APIRouter(prefix="/admin", tags=["admin"])

EMPLOYEE_TYPES = (
    "field_technician",
    "scheduling_operator",
    "internal_support",
    "supervisor",
    "regional_manager",
    "headquarters",
    "administrative",
    "other",
)
TEAM_TYPES = ("field", "scheduling", "internal_support", "regional", "administrative", "headquarters", "other")
STRUCTURE_STATUSES = ("pending_review", "validated", "needs_fix", "outside_operation", "inactive")


def _permission_module(permission: str) -> str:
    if permission.startswith("operations:"):
        return "Operação Analítica"
    if permission.startswith("management:"):
        return "Gestão"
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


def _normalize_document(value: str | None) -> str | None:
    if value is None:
        return None
    digits = "".join(char for char in value if char.isdigit())
    return digits or None


def _mask_document(value: str | None) -> str | None:
    digits = _normalize_document(value)
    if not digits:
        return None
    if len(digits) <= 4:
        return "***"
    return f"***.***.***-{digits[-2:]}"


def _validate_choice(field: str, value: str | None, choices: tuple[str, ...]) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if normalized not in choices:
        raise HTTPException(status_code=422, detail=f"Valor inválido para {field}.")
    return normalized


def _resolve_optional_user(db: Session, user_id: int | None, field: str) -> User | None:
    if user_id is None:
        return None
    item = db.get(User, user_id)
    if not item or not item.active:
        raise HTTPException(status_code=422, detail=f"{field} inválido ou inativo.")
    return item


def _person_out(collaborator: Collaborator, portal_user: User | None = None) -> AdminPersonStructureOut:
    return AdminPersonStructureOut(
        id=collaborator.id,
        name=collaborator.name,
        role=collaborator.role,
        regional=normalize_regional(collaborator.regional),
        active=collaborator.active,
        is_registered=collaborator.is_registered,
        cpf_masked=_mask_document(collaborator.cpf),
        employee_type=collaborator.employee_type,
        team_type=collaborator.team_type,
        supervisor_user_id=collaborator.supervisor_user_id,
        supervisor_name=collaborator.supervisor_user.name if collaborator.supervisor_user else None,
        regional_manager_user_id=collaborator.regional_manager_user_id,
        regional_manager_name=collaborator.regional_manager_user.name if collaborator.regional_manager_user else None,
        structure_status=collaborator.structure_status,
        structure_notes=collaborator.structure_notes,
        ixc_employee_id=collaborator.ixc_employee_id,
        portal_user_id=portal_user.id if portal_user else None,
        portal_user_email=portal_user.email if portal_user else None,
        has_photo=collaborator.photo is not None,
    )


def _replace_permissions(db: Session, profile: AccessProfile, permission_keys: list[str]) -> None:
    db.query(AccessProfilePermission).filter(AccessProfilePermission.profile_id == profile.id).delete(synchronize_session=False)
    for permission in _validate_permissions(permission_keys):
        db.add(AccessProfilePermission(profile_id=profile.id, permission=permission))


def _module_visibility_by_profile(db: Session) -> dict[tuple[str, int], WorkspaceModuleVisibility]:
    return {
        (item.module_key, item.profile_id): item
        for item in db.scalars(select(WorkspaceModuleVisibility).where(WorkspaceModuleVisibility.profile_id.is_not(None))).all()
    }


def _module_visibility_by_user(db: Session) -> dict[tuple[str, int], WorkspaceModuleVisibility]:
    return {
        (item.module_key, item.user_id): item
        for item in db.scalars(select(WorkspaceModuleVisibility).where(WorkspaceModuleVisibility.user_id.is_not(None))).all()
    }


def _admin_module_out(
    module,
    profiles: list[AccessProfile],
    visibility_by_profile: dict[tuple[str, int], WorkspaceModuleVisibility],
    users_by_id: dict[int, User],
    visibility_by_user: dict[tuple[str, int], WorkspaceModuleVisibility],
) -> AdminWorkspaceModuleOut:
    return AdminWorkspaceModuleOut(
        key=module.key,
        name=module.name,
        description=module.description,
        web_path=module.web_path,
        api_prefix=module.api_prefix,
        required_permission=module.required_permission,
        status=module.status,
        profiles=[
            AdminModuleProfileVisibilityOut(
                profile_id=profile.id,
                profile_name=profile.name,
                visible=visibility_by_profile.get((module.key, profile.id)).visible if visibility_by_profile.get((module.key, profile.id)) else True,
                has_required_permission=any(item.permission == module.required_permission for item in profile.permissions),
            )
            for profile in profiles
            if profile.active
        ],
        user_overrides=[
            AdminModuleUserVisibilityOut(
                user_id=user_id,
                user_name=users_by_id[user_id].name,
                user_email=users_by_id[user_id].email,
                visible=item.visible,
                reason=item.reason,
            )
            for (module_key, user_id), item in visibility_by_user.items()
            if module_key == module.key and user_id in users_by_id
        ],
    )


def _build_single_module_out(db: Session, module) -> AdminWorkspaceModuleOut:
    profiles = db.scalars(select(AccessProfile).order_by(AccessProfile.name.asc())).all()
    users_by_id = {item.id: item for item in db.scalars(select(User))}
    visibility_by_profile = _module_visibility_by_profile(db)
    visibility_by_user = _module_visibility_by_user(db)
    return _admin_module_out(module, profiles, visibility_by_profile, users_by_id, visibility_by_user)


@router.get("/permissions", response_model=list[EcosystemPermissionOut])
def list_permissions(_: User = Depends(require_permission("admin:permissions:read"))):
    return [
        EcosystemPermissionOut(key=key, label=label, module=_permission_module(key))
        for key, label in sorted(PERMISSION_LABELS.items())
    ]


@router.get("/modules", response_model=list[AdminWorkspaceModuleOut])
def list_admin_modules(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("admin:modules:read")),
):
    profiles = db.scalars(select(AccessProfile).order_by(AccessProfile.name.asc())).all()
    users_by_id = {item.id: item for item in db.scalars(select(User))}
    visibility_by_profile = _module_visibility_by_profile(db)
    visibility_by_user = _module_visibility_by_user(db)
    return [
        _admin_module_out(module, profiles, visibility_by_profile, users_by_id, visibility_by_user)
        for module in list_modules()
    ]


@router.put("/modules/{module_key}/visibility", response_model=AdminWorkspaceModuleOut)
def update_module_visibility(
    module_key: str,
    payload: AdminModuleVisibilityUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("admin:modules:write")),
):
    module = get_module(module_key)
    if not module:
        raise HTTPException(status_code=404, detail="Módulo não encontrado.")
    profile = db.get(AccessProfile, payload.profile_id)
    if not profile or not profile.active:
        raise HTTPException(status_code=404, detail="Perfil não encontrado ou inativo.")
    visibility = db.scalar(
        select(WorkspaceModuleVisibility).where(
            WorkspaceModuleVisibility.module_key == module_key,
            WorkspaceModuleVisibility.profile_id == payload.profile_id,
        )
    )
    before = snapshot(visibility) if visibility else None
    if not visibility:
        visibility = WorkspaceModuleVisibility(module_key=module_key, profile_id=payload.profile_id)
        db.add(visibility)
        db.flush()
    visibility.visible = payload.visible
    visibility.reason = payload.reason
    visibility.updated_by = user.id
    record_audit_log(db, user, "update_visibility", "workspace_module_visibility", visibility.id, before, snapshot(visibility))
    db.commit()
    return _build_single_module_out(db, module)


@router.put("/modules/{module_key}/user-visibility", response_model=AdminWorkspaceModuleOut)
def update_module_user_visibility(
    module_key: str,
    payload: AdminModuleUserVisibilityUpsert,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("admin:modules:write")),
):
    module = get_module(module_key)
    if not module:
        raise HTTPException(status_code=404, detail="Módulo não encontrado.")
    target_user = db.get(User, payload.user_id)
    if not target_user or not target_user.active:
        raise HTTPException(status_code=404, detail="Usuário não encontrado ou inativo.")
    visibility = db.scalar(
        select(WorkspaceModuleVisibility).where(
            WorkspaceModuleVisibility.module_key == module_key,
            WorkspaceModuleVisibility.user_id == payload.user_id,
        )
    )
    before = snapshot(visibility) if visibility else None
    if not visibility:
        visibility = WorkspaceModuleVisibility(module_key=module_key, user_id=payload.user_id)
        db.add(visibility)
        db.flush()
    visibility.visible = payload.visible
    visibility.reason = payload.reason
    visibility.updated_by = user.id
    record_audit_log(db, user, "update_user_visibility", "workspace_module_visibility", visibility.id, before, snapshot(visibility))
    db.commit()
    return _build_single_module_out(db, module)


@router.delete("/modules/{module_key}/user-visibility/{user_id}", response_model=AdminWorkspaceModuleOut)
def delete_module_user_visibility(
    module_key: str,
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("admin:modules:write")),
):
    module = get_module(module_key)
    if not module:
        raise HTTPException(status_code=404, detail="Módulo não encontrado.")
    visibility = db.scalar(
        select(WorkspaceModuleVisibility).where(
            WorkspaceModuleVisibility.module_key == module_key,
            WorkspaceModuleVisibility.user_id == user_id,
        )
    )
    if not visibility:
        raise HTTPException(status_code=404, detail="Exceção de usuário não encontrada para este módulo.")
    before = snapshot(visibility)
    record_audit_log(db, user, "delete_user_visibility", "workspace_module_visibility", visibility.id, before, None)
    db.delete(visibility)
    db.commit()
    return _build_single_module_out(db, module)


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


@router.get("/people-structure", response_model=AdminPeopleStructureOut)
def list_people_structure(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("admin:users:read")),
):
    collaborators = list(db.scalars(select(Collaborator).order_by(Collaborator.name.asc(), Collaborator.id.asc())))
    portal_users_by_collaborator: dict[int, User] = {
        item.collaborator_id: item
        for item in db.scalars(select(User).where(User.collaborator_id.is_not(None)))
        if item.collaborator_id is not None
    }
    active_users = list(db.scalars(select(User).where(User.active.is_(True)).order_by(User.name.asc())))
    people = [_person_out(collaborator, portal_users_by_collaborator.get(collaborator.id)) for collaborator in collaborators]
    return AdminPeopleStructureOut(
        summary={
            "total_people": len(collaborators),
            "active_people": sum(1 for item in collaborators if item.active),
            "without_supervisor": sum(1 for item in collaborators if item.active and item.team_type == "field" and item.supervisor_user_id is None),
            "without_team_type": sum(1 for item in collaborators if item.active and not item.team_type),
            "pending_review": sum(1 for item in collaborators if item.structure_status == "pending_review"),
            "field_team": sum(1 for item in collaborators if item.team_type == "field"),
            "scheduling_team": sum(1 for item in collaborators if item.team_type == "scheduling"),
        },
        people=people,
        supervisors=[AdminStructureOption(id=item.id, name=item.name) for item in active_users],
        regional_managers=[AdminStructureOption(id=item.id, name=item.name) for item in active_users],
        employee_types=list(EMPLOYEE_TYPES),
        team_types=list(TEAM_TYPES),
        statuses=list(STRUCTURE_STATUSES),
    )


@router.patch("/people-structure/{collaborator_id}", response_model=AdminPersonStructureOut)
def update_person_structure(
    collaborator_id: int,
    payload: AdminPersonStructureUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("admin:users:write")),
):
    collaborator = db.get(Collaborator, collaborator_id)
    if not collaborator:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado.")
    before = snapshot(collaborator)
    updates = payload.model_dump(exclude_unset=True)

    if "cpf" in updates:
        collaborator.cpf = _normalize_document(updates["cpf"])
    if "employee_type" in updates:
        collaborator.employee_type = _validate_choice("tipo de colaborador", updates["employee_type"], EMPLOYEE_TYPES)
    if "team_type" in updates:
        collaborator.team_type = _validate_choice("tipo de equipe", updates["team_type"], TEAM_TYPES)
    if "structure_status" in updates:
        collaborator.structure_status = _validate_choice("status de estrutura", updates["structure_status"], STRUCTURE_STATUSES) or "pending_review"
    if "structure_notes" in updates:
        collaborator.structure_notes = updates["structure_notes"]
    if "supervisor_user_id" in updates:
        _resolve_optional_user(db, updates["supervisor_user_id"], "Supervisor")
        collaborator.supervisor_user_id = updates["supervisor_user_id"]
    if "regional_manager_user_id" in updates:
        _resolve_optional_user(db, updates["regional_manager_user_id"], "Gerente regional")
        collaborator.regional_manager_user_id = updates["regional_manager_user_id"]

    record_audit_log(db, user, "update_structure", "collaborators", collaborator.id, before, snapshot(collaborator))
    db.commit()
    db.refresh(collaborator)
    portal_user = db.scalar(select(User).where(User.collaborator_id == collaborator.id))
    return _person_out(collaborator, portal_user)


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
