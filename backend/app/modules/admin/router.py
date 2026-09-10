from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import PERMISSION_LABELS, get_current_user, require_permission
from app.db.session import get_db
from app.models import (
    AccessProfile,
    AccessProfilePermission,
    Collaborator,
    CustomPermission,
    User,
    UserAccessProfile,
    WorkspaceModuleSetting,
    WorkspaceModuleVisibility,
)
from app.modules.admin.user_permissions_service import (
    overview as user_permission_overview,
    remove_override as remove_user_permission_override,
    set_override as set_user_permission_override,
)
from app.modules.operations.models import OperationOrder
from app.services.documents import mask_document as _mask_document, normalize_document as _normalize_document
from app.services.regional import normalize_regional
from app.modules.admin.modules_service import (
    EffectiveModule,
    ModuleValidationError,
    effective_module,
    effective_modules,
    update_module_settings,
)
from app.modules.admin.permissions_service import (
    SENSITIVE_PERMISSIONS,
    PermissionValidationError,
    create_custom_permission,
    delete_custom_permission,
    permission_catalog,
    update_custom_permission,
    validate_permission_keys,
)
from app.modules.admin.schemas import (
    AccessProfileCreate,
    AccessProfileOut,
    AccessProfileUpdate,
    AdminPeopleStructureOut,
    AdminModuleSettingsUpdate,
    AdminModuleUserVisibilityOut,
    AdminModuleUserVisibilityUpsert,
    AdminModuleVisibilityUpdate,
    AdminWorkspaceModuleOut,
    AdminModuleProfileVisibilityOut,
    AdminPersonStructureOut,
    AdminPersonStructureUpdate,
    AdminStructureOption,
    CustomPermissionCreate,
    CustomPermissionUpdate,
    EcosystemPermissionOut,
    UserPermissionOverrideOut,
    UserPermissionOverrideUpsert,
    UserPermissionOverviewOut,
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



# Permissão que define "quem administra o acesso das outras pessoas". Serve de trava contra o
# ecossistema ficar sem administrador: o último perfil ATIVO que a concede não pode ser excluído
# nem inativado por engano (ver `_profile_delete_blocked_reason`).
ADMIN_GATEKEEPER_PERMISSION = "admin:users:write"


def _profile_delete_blocked_reason(db: Session, profile: AccessProfile, action: str = "excluir") -> str | None:
    """Motivo para NÃO poder excluir este perfil, ou None quando pode.

    Perfil do sistema deixou de ser bloqueado aqui (2026-09-09): com o registro de semeadura
    (`AccessProfilePermissionSeed`) ele não é mais recriado no restart, então excluir passou a ser
    uma decisão que fica de pé. Continua bloqueado só o que trancaria o ecossistema por fora: o
    último perfil ativo que concede o poder de administrar acesso.

    Perfil vinculado a usuários NÃO é bloqueio: a exclusão exige informar um perfil que recebe
    essas pessoas (ver `delete_access_profile`), porque usuário sem nenhum perfil cai no conjunto
    de permissões do papel legado (`permissions_for_user`), o que seria uma mudança de acesso
    silenciosa em vez de uma remoção.
    """
    grants_gatekeeper = any(item.permission == ADMIN_GATEKEEPER_PERMISSION for item in profile.permissions)
    if not grants_gatekeeper or not profile.active:
        return None
    others = db.scalars(
        select(AccessProfile)
        .join(AccessProfilePermission, AccessProfilePermission.profile_id == AccessProfile.id)
        .where(
            AccessProfile.id != profile.id,
            AccessProfile.active.is_(True),
            AccessProfilePermission.permission == ADMIN_GATEKEEPER_PERMISSION,
        )
    ).all()
    if others:
        return None
    return (
        "É o último perfil ativo que concede a administração de acessos "
        f"({ADMIN_GATEKEEPER_PERMISSION}). Crie outro perfil com essa permissão antes de {action} "
        "este, ou ninguém mais consegue administrar o ecossistema."
    )


def _profile_out(db: Session, profile: AccessProfile, user_count: int = 0) -> AccessProfileOut:
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
        delete_blocked_reason=_profile_delete_blocked_reason(db, profile),
    )


def _validate_permissions(db: Session, permission_keys: list[str]) -> list[str]:
    """Aceita as permissões de código e as próprias criadas na aba Permissões (ver
    `permissions_service.valid_permission_keys`)."""
    try:
        return validate_permission_keys(db, permission_keys)
    except PermissionValidationError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error



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
    validated = _validate_permissions(db, permission_keys)
    db.query(AccessProfilePermission).filter(AccessProfilePermission.profile_id == profile.id).delete(synchronize_session=False)
    for permission in validated:
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
    module: EffectiveModule,
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
        default_name=module.default_name,
        default_description=module.default_description,
        default_status=module.default_status,
        customized=module.customized,
        sort_order=module.sort_order,
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


def _require_module(db: Session, module_key: str) -> EffectiveModule:
    module = effective_module(db, module_key)
    if not module:
        raise HTTPException(status_code=404, detail="Módulo não encontrado.")
    return module


def _build_single_module_out(db: Session, module: EffectiveModule) -> AdminWorkspaceModuleOut:
    profiles = db.scalars(select(AccessProfile).order_by(AccessProfile.name.asc())).all()
    users_by_id = {item.id: item for item in db.scalars(select(User))}
    visibility_by_profile = _module_visibility_by_profile(db)
    visibility_by_user = _module_visibility_by_user(db)
    return _admin_module_out(module, profiles, visibility_by_profile, users_by_id, visibility_by_user)


def _permission_catalog_entry_out(entry) -> EcosystemPermissionOut:
    return EcosystemPermissionOut(
        key=entry.key,
        label=entry.label,
        module=entry.module,
        module_key=entry.module_key,
        sensitive=entry.sensitive,
        custom=entry.custom,
        description=entry.description,
        profile_count=entry.profile_count,
        user_count=entry.user_count,
        profile_names=entry.profile_names,
        override_count=entry.override_count,
    )


@router.get("/permissions", response_model=list[EcosystemPermissionOut])
def list_permissions(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("admin:permissions:read")),
):
    """Catálogo completo: permissões de código + próprias, com o uso atual de cada uma."""
    return [_permission_catalog_entry_out(entry) for entry in permission_catalog(db)]


@router.post("/permissions", response_model=EcosystemPermissionOut, status_code=201)
def create_permission(
    payload: CustomPermissionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("admin:permissions:write")),
):
    try:
        permission = create_custom_permission(
            db,
            key=payload.key,
            label=payload.label,
            module_key=payload.module_key,
            description=payload.description,
            sensitive=payload.sensitive,
            created_by=user.id,
        )
    except PermissionValidationError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    record_audit_log(db, user, "create", "custom_permissions", permission.id, None, snapshot(permission))
    db.commit()
    return _custom_permission_out(db, permission.key)


@router.put("/permissions/{permission_key}", response_model=EcosystemPermissionOut)
def update_permission(
    permission_key: str,
    payload: CustomPermissionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("admin:permissions:write")),
):
    permission = _require_custom_permission(db, permission_key)
    before = snapshot(permission)
    updates = payload.model_dump(exclude_unset=True)
    try:
        update_custom_permission(
            db,
            permission,
            label=updates.get("label"),
            module_key=updates.get("module_key"),
            description=updates.get("description"),
            sensitive=updates.get("sensitive"),
            active=updates.get("active"),
            module_key_provided="module_key" in updates,
        )
    except PermissionValidationError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    record_audit_log(db, user, "update", "custom_permissions", permission.id, before, snapshot(permission))
    db.commit()
    return _custom_permission_out(db, permission_key)


@router.delete("/permissions/{permission_key}", status_code=204)
def delete_permission(
    permission_key: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("admin:permissions:write")),
):
    """Só permissão própria é excluível. Permissão de código não: apagar o rótulo não apagaria a
    exigência da rota, só deixaria a rota inalcançável sem aviso nenhum na tela."""
    permission = _require_custom_permission(db, permission_key)
    before = snapshot(permission)
    permission_id = permission.id
    try:
        delete_custom_permission(db, permission)
    except PermissionValidationError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    record_audit_log(db, user, "delete", "custom_permissions", permission_id, before, None)
    db.commit()
    return None


def _require_custom_permission(db: Session, permission_key: str) -> CustomPermission:
    key = permission_key.strip().lower()
    permission = db.scalar(select(CustomPermission).where(CustomPermission.key == key))
    if permission:
        return permission
    if key in PERMISSION_LABELS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Esta é uma permissão do sistema, declarada em código, e não pode ser alterada nem "
                "excluída pela tela. Remova-a dos perfis que não devem tê-la."
            ),
        )
    raise HTTPException(status_code=404, detail="Permissão não encontrada.")


def _custom_permission_out(db: Session, permission_key: str) -> EcosystemPermissionOut:
    entry = next((item for item in permission_catalog(db) if item.key == permission_key), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Permissão não encontrada.")
    return _permission_catalog_entry_out(entry)


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
        for module in effective_modules(db)
    ]


@router.put("/modules/{module_key}/settings", response_model=AdminWorkspaceModuleOut)
def update_module_settings_endpoint(
    module_key: str,
    payload: AdminModuleSettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("admin:modules:write")),
):
    """Nome, descrição, status e ordem do módulo. Campo enviado vazio volta ao padrão do registry."""
    _require_module(db, module_key)
    updates = payload.model_dump(exclude_unset=True)
    existing = db.scalar(select(WorkspaceModuleSetting).where(WorkspaceModuleSetting.module_key == module_key))
    before = snapshot(existing) if existing else None
    try:
        setting = update_module_settings(
            db,
            module_key,
            name=updates.get("name"),
            description=updates.get("description"),
            status=updates.get("status"),
            sort_order=updates.get("sort_order"),
            updated_by=user.id,
            fields_provided=set(updates.keys()),
        )
    except ModuleValidationError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    record_audit_log(db, user, "update_settings", "workspace_module_settings", setting.id, before, snapshot(setting))
    db.commit()
    return _build_single_module_out(db, _require_module(db, module_key))


@router.put("/modules/{module_key}/visibility", response_model=AdminWorkspaceModuleOut)
def update_module_visibility(
    module_key: str,
    payload: AdminModuleVisibilityUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("admin:modules:write")),
):
    module = _require_module(db, module_key)
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
    module = _require_module(db, module_key)
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
    module = _require_module(db, module_key)
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
    return [_profile_out(db, profile, user_counts.get(profile.id, 0)) for profile in profiles]


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
    return _profile_out(db, profile)


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
        # Inativar é o outro caminho para o mesmo estrago que a exclusão do último perfil
        # administrador causaria: perfil inativo não concede nada (ver `permissions_for_user`), e
        # quem ficasse sem nenhum perfil ativo cairia no papel legado. Mesma trava.
        if not bool(updates["active"]) and profile.active:
            blocked = _profile_delete_blocked_reason(db, profile, action="inativar")
            if blocked:
                raise HTTPException(status_code=409, detail=blocked)
        profile.active = bool(updates["active"])
    if "permission_keys" in updates and updates["permission_keys"] is not None:
        _replace_permissions(db, profile, updates["permission_keys"])
    record_audit_log(db, user, "update", "access_profiles", profile.id, before, snapshot(profile))
    db.commit()
    db.refresh(profile)
    return _profile_out(db, profile)


@router.delete("/access-profiles/{profile_id}", response_model=AccessProfileOut)
def delete_access_profile(
    profile_id: int,
    reassign_profile_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("admin:roles:write")),
):
    """Exclui um perfil de acesso, inclusive do sistema.

    Duas mudanças de 2026-09-09, a partir de "excluir perfil de permissão hoje não consigo":

    - **Perfil do sistema passou a ser excluível.** O bloqueio existia porque
      `ensure_access_profiles` recriava o perfil no restart, então "excluir" era uma ilusão. Com o
      registro de semeadura (`AccessProfilePermissionSeed`) a exclusão fica de pé.
    - **Perfil vinculado a usuários deixou de ser um beco sem saída.** Antes respondia 409 e ponto:
      não havia caminho pela tela para desvincular as pessoas. Agora a exclusão aceita
      `reassign_profile_id` e MOVE as pessoas para o perfil informado, numa transação só. É
      exigido, não opcional: usuário sem nenhum perfil cai no conjunto do papel legado
      (`permissions_for_user`), o que poderia AMPLIAR o acesso dele em silêncio.

    Continua bloqueada a exclusão do último perfil ativo que administra acessos - ver
    `_profile_delete_blocked_reason`.
    """
    profile = db.get(AccessProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil de acesso não encontrado.")

    blocked = _profile_delete_blocked_reason(db, profile)
    if blocked:
        raise HTTPException(status_code=409, detail=blocked)

    linked_user_ids = list(
        db.scalars(select(UserAccessProfile.user_id).where(UserAccessProfile.profile_id == profile.id))
    )
    if linked_user_ids:
        if reassign_profile_id is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Este perfil está vinculado a {len(linked_user_ids)} usuário(s). "
                    "Escolha um perfil para receber essas pessoas antes de excluir."
                ),
            )
        if reassign_profile_id == profile.id:
            raise HTTPException(status_code=422, detail="O perfil de destino tem de ser diferente do excluído.")
        target = db.get(AccessProfile, reassign_profile_id)
        if not target or not target.active:
            raise HTTPException(status_code=422, detail="Perfil de destino inválido ou inativo.")
        already_linked = set(
            db.scalars(select(UserAccessProfile.user_id).where(UserAccessProfile.profile_id == target.id))
        )
        for user_id in linked_user_ids:
            if user_id not in already_linked:
                db.add(UserAccessProfile(user_id=user_id, profile_id=target.id))
        record_audit_log(
            db,
            user,
            "reassign_users",
            "access_profiles",
            profile.id,
            {"profile_id": profile.id, "user_ids": sorted(linked_user_ids)},
            {"profile_id": target.id, "profile_name": target.name},
        )

    response = _profile_out(db, profile, len(linked_user_ids))
    before = snapshot(profile)
    record_audit_log(db, user, "delete", "access_profiles", profile.id, before, None)
    # Os vínculos e as permissões do perfil saem por ON DELETE CASCADE (ver models.py).
    db.delete(profile)
    db.commit()
    return response


def _require_target_user(db: Session, user_id: int) -> User:
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return target


def _user_permission_overview_out(db: Session, target: User) -> UserPermissionOverviewOut:
    data = user_permission_overview(db, target)
    return UserPermissionOverviewOut(
        user_id=target.id,
        profile_permissions=data.profile_permissions,
        overrides=[
            UserPermissionOverrideOut(
                permission=item.permission,
                label=item.label,
                module=item.module,
                effect=item.effect,
                reason=item.reason,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in data.overrides
        ],
        effective_permissions=data.effective_permissions,
    )


@router.get("/users/{user_id}/permissions", response_model=UserPermissionOverviewOut)
def get_user_permissions(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("admin:users:read")),
):
    """O que o perfil da pessoa dá, as exceções individuais e o resultado efetivo - a mesma conta
    que `permissions_for_user` faz em toda checagem de permissão do sistema."""
    target = _require_target_user(db, user_id)
    return _user_permission_overview_out(db, target)


@router.put("/users/{user_id}/permissions/{permission_key}", response_model=UserPermissionOverviewOut)
def upsert_user_permission_override(
    user_id: int,
    permission_key: str,
    payload: UserPermissionOverrideUpsert,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("admin:users:write")),
):
    """Concede ou nega UMA permissão específica desta pessoa, sem mexer no perfil dela.

    Idempotente por chave: chamar de novo com efeito diferente TROCA a exceção (não empilha), e é
    assim que a tela alterna "Conceder"/"Negar" com um clique cada.
    """
    target = _require_target_user(db, user_id)
    before = user_permission_overview(db, target)
    try:
        set_user_permission_override(db, target, permission_key, payload.effect, payload.reason, created_by=actor.id)
    except PermissionValidationError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    db.refresh(target)
    after = user_permission_overview(db, target)
    record_audit_log(
        db,
        actor,
        "set_permission_override",
        "user_permission_overrides",
        target.id,
        {"effective_permissions": before.effective_permissions},
        {
            "permission": permission_key,
            "effect": payload.effect,
            "reason": payload.reason,
            "effective_permissions": after.effective_permissions,
        },
    )
    db.commit()
    db.refresh(target)
    return _user_permission_overview_out(db, target)


@router.delete("/users/{user_id}/permissions/{permission_key}", response_model=UserPermissionOverviewOut)
def delete_user_permission_override(
    user_id: int,
    permission_key: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("admin:users:write")),
):
    """Remove a exceção: a pessoa volta a ter exatamente o que o perfil dela concede."""
    target = _require_target_user(db, user_id)
    before = user_permission_overview(db, target)
    try:
        remove_user_permission_override(db, target, permission_key)
    except PermissionValidationError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    db.refresh(target)
    after = user_permission_overview(db, target)
    record_audit_log(
        db,
        actor,
        "remove_permission_override",
        "user_permission_overrides",
        target.id,
        {"permission": permission_key, "effective_permissions": before.effective_permissions},
        {"effective_permissions": after.effective_permissions},
    )
    db.commit()
    db.refresh(target)
    return _user_permission_overview_out(db, target)
