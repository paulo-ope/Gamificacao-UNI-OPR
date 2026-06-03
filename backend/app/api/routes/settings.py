from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_permission
from app.db.session import get_db
from app.models import AppSetting, User
from app.schemas import AppSettingOut, AppSettingUpdate
from app.services.audit_log import record_audit_log, snapshot

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=list[AppSettingOut])
def list_settings(db: Session = Depends(get_db), user: User = Depends(require_permission("scoring:read"))):
    return db.scalars(select(AppSetting).order_by(AppSetting.key.asc())).all()


@router.put("/{key}", response_model=AppSettingOut)
def update_setting(key: str, payload: AppSettingUpdate, db: Session = Depends(get_db), user: User = Depends(require_permission("settings:write"))):
    setting = db.scalar(select(AppSetting).where(AppSetting.key == key))
    before = snapshot(setting)
    if not setting:
        setting = AppSetting(key=key, value=payload.value)
        db.add(setting)
    else:
        setting.value = payload.value
    db.flush()
    record_audit_log(db, user, "update", "app_settings", key, before, snapshot(setting))
    db.commit()
    db.refresh(setting)
    return setting
