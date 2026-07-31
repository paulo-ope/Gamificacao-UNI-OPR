from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_permission
from app.db.session import get_db
from app.models import AppSetting, User
from app.schemas import AppSettingOut, AppSettingUpdate
from app.services.audit_log import record_audit_log, snapshot
from app.services.gamification_config import DEFAULT_SETTINGS as GAMIFICATION_DEFAULT_SETTINGS

router = APIRouter(prefix="/settings", tags=["settings"])

# `app_settings` e uma tabela compartilhada - Agendamento guarda suas proprias chaves
# (scheduling_*) nela tambem. Essas rotas sao especificas da Gamificacao, entao so podem
# ler/escrever as chaves que a Gamificacao realmente possui - sem isso, o import/export de config
# da Gamificacao vaza (e pode sobrescrever) parametros do Agendamento.
GAMIFICATION_SETTING_KEYS = set(GAMIFICATION_DEFAULT_SETTINGS.keys())


@router.get("", response_model=list[AppSettingOut])
def list_settings(db: Session = Depends(get_db), user: User = Depends(require_permission("scoring:read"))):
    return db.scalars(
        select(AppSetting).where(AppSetting.key.in_(GAMIFICATION_SETTING_KEYS)).order_by(AppSetting.key.asc())
    ).all()


@router.put("/{key}", response_model=AppSettingOut)
def update_setting(key: str, payload: AppSettingUpdate, db: Session = Depends(get_db), user: User = Depends(require_permission("settings:write"))):
    if key not in GAMIFICATION_SETTING_KEYS:
        raise HTTPException(status_code=404, detail="Configuração não pertence à Gamificação.")
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
