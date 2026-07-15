from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import require_permission
from app.db.session import get_db
from app.models import User
from app.schemas import GamificationConfigImport, GamificationConfigOut
from app.services.audit_log import record_audit_log
from app.services.gamification_config import apply_config, ensure_default_logic_config, serialize_current_config

router = APIRouter(prefix="/gamification", tags=["gamification"])


@router.get("/config", response_model=GamificationConfigOut)
def get_gamification_config(db: Session = Depends(get_db), user: User = Depends(require_permission("scoring:read"))):
    return serialize_current_config(db)


@router.put("/config", response_model=GamificationConfigOut)
def save_gamification_config(payload: GamificationConfigImport, db: Session = Depends(get_db), user: User = Depends(require_permission("settings:write"))):
    try:
        before = serialize_current_config(db)
        result = apply_config(db, payload.model_dump(), payload.name)
        record_audit_log(db, user, "update", "gamification_config", payload.name, before, result)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@router.post("/config/export", response_model=GamificationConfigOut)
def export_gamification_config(db: Session = Depends(get_db), user: User = Depends(require_permission("scoring:read"))):
    return serialize_current_config(db)


@router.post("/config/import", response_model=GamificationConfigOut)
def import_gamification_config(payload: GamificationConfigImport, db: Session = Depends(get_db), user: User = Depends(require_permission("settings:write"))):
    try:
        before = serialize_current_config(db)
        result = apply_config(db, payload.model_dump(), payload.name)
        record_audit_log(db, user, "import", "gamification_config", payload.name, before, result)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@router.post("/config/reset-default", response_model=GamificationConfigOut)
def reset_default_gamification_config(db: Session = Depends(get_db), user: User = Depends(require_permission("settings:write"))):
    try:
        before = serialize_current_config(db)
        result = ensure_default_logic_config(db)
        record_audit_log(db, user, "reset_default", "gamification_config", None, before, result)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
