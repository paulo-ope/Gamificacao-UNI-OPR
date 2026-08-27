from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user, permissions_for_user
from app.db.session import get_db
from app.models import User, WorkspaceModuleVisibility
from app.modules.admin.schemas import WorkspaceModulePreferenceUpdate, WorkspaceVisibleModuleOut
from app.modules.registry import list_modules
from app.modules.workspace import overview_service
from app.modules.workspace.schemas import WorkspaceOverviewOut

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("/modules", response_model=list[WorkspaceVisibleModuleOut])
def visible_modules(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    permissions = permissions_for_user(user)
    active_profile_ids = [profile.id for profile in user.access_profiles if profile.active]
    hidden_by_profile = set()
    if active_profile_ids:
        hidden_by_profile = {
            item.module_key
            for item in db.scalars(
                select(WorkspaceModuleVisibility).where(
                    WorkspaceModuleVisibility.profile_id.in_(active_profile_ids),
                    WorkspaceModuleVisibility.visible.is_(False),
                )
            )
        }
    user_overrides = {
        item.module_key: item
        for item in db.scalars(select(WorkspaceModuleVisibility).where(WorkspaceModuleVisibility.user_id == user.id))
    }

    visible = []
    for module in list_modules():
        if module.status != "active" or module.required_permission not in permissions:
            continue
        override = user_overrides.get(module.key)
        if override is not None:
            if not override.visible:
                continue
        elif module.key in hidden_by_profile:
            continue
        visible.append(
            WorkspaceVisibleModuleOut(
                key=module.key,
                name=module.name,
                description=module.description,
                web_path=module.web_path,
                api_prefix=module.api_prefix,
                required_permission=module.required_permission,
                status=module.status,
                pinned=override.pinned if override is not None else False,
                order_index=override.order_index if override is not None else None,
            )
        )
    return visible


@router.put("/modules/{module_key}/preference", response_model=WorkspaceVisibleModuleOut)
def update_module_preference(
    module_key: str,
    payload: WorkspaceModulePreferenceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Preferência PESSOAL de atalho na sidebar (fixar/reordenar) - self-service, ao contrário de
    `admin/router.py` (que muda visibilidade de OUTRO usuário/perfil). Nunca mexe em `visible`;
    quem pode ver o módulo continua decidido só por permissão + hide de admin."""
    permissions = permissions_for_user(user)
    module = next((m for m in list_modules() if m.key == module_key), None)
    if module is None or module.status != "active" or module.required_permission not in permissions:
        raise HTTPException(status_code=404, detail="Módulo não encontrado ou não acessível para este usuário.")

    row = db.scalar(
        select(WorkspaceModuleVisibility).where(
            WorkspaceModuleVisibility.module_key == module_key,
            WorkspaceModuleVisibility.user_id == user.id,
        )
    )
    if row is None:
        row = WorkspaceModuleVisibility(module_key=module_key, user_id=user.id, visible=True)
        db.add(row)
    if payload.pinned is not None:
        row.pinned = payload.pinned
    if payload.order_index is not None:
        row.order_index = payload.order_index
    row.updated_by = user.id
    db.commit()
    db.refresh(row)

    return WorkspaceVisibleModuleOut(
        key=module.key,
        name=module.name,
        description=module.description,
        web_path=module.web_path,
        api_prefix=module.api_prefix,
        required_permission=module.required_permission,
        status=module.status,
        pinned=row.pinned,
        order_index=row.order_index,
    )


@router.get("/overview", response_model=WorkspaceOverviewOut)
def workspace_overview(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return overview_service.build_overview(db, user)

