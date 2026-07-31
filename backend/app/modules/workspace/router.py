from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user, permissions_for_user
from app.db.session import get_db
from app.models import User, WorkspaceModuleVisibility
from app.modules.admin.schemas import WorkspaceVisibleModuleOut
from app.modules.registry import list_modules

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
        item.module_key: item.visible
        for item in db.scalars(select(WorkspaceModuleVisibility).where(WorkspaceModuleVisibility.user_id == user.id))
    }

    visible = []
    for module in list_modules():
        if module.status != "active" or module.required_permission not in permissions:
            continue
        if module.key in user_overrides:
            if not user_overrides[module.key]:
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
            )
        )
    return visible

