from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_permission
from app.db.session import get_db
from app.models import CpkRegionalSnapshot, User
from app.schemas import CpkRegionalSnapshotOut, CpkSyncRequest, GamificationConfigImport, GamificationConfigOut
from app.services.audit_log import record_audit_log
from app.services.cpk_client import CpkApiError
from app.services.cpk_health import sync_cpk_snapshot
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


@router.post("/cpk/sync", response_model=list[CpkRegionalSnapshotOut])
def sync_cpk(
    payload: CpkSyncRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("settings:write")),
):
    """Sincronização manual sob demanda do relatório de CPK por regional - grava/atualiza o
    snapshot local (backend/app/services/cpk_health.py) pra conferência na tela de configuração
    antes de qualquer cálculo de folha usar esse ajuste."""
    try:
        sync_cpk_snapshot(db, payload.year, payload.month)
        db.commit()
    except CpkApiError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=f"Falha ao comunicar com a API de CPK: {exc}") from exc
    except Exception:
        db.rollback()
        raise
    rows = db.scalars(
        select(CpkRegionalSnapshot)
        .where(
            CpkRegionalSnapshot.reference_year == payload.year,
            CpkRegionalSnapshot.reference_month == payload.month,
        )
        .order_by(CpkRegionalSnapshot.regional)
    )
    return list(rows)


@router.get("/cpk/snapshot", response_model=list[CpkRegionalSnapshotOut])
def get_cpk_snapshot(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scoring:read")),
):
    """Último snapshot sincronizado de CPK por regional pro período informado, sem chamar a API
    ao vivo - pra tela de configuração mostrar o que está de fato em uso no cálculo."""
    rows = db.scalars(
        select(CpkRegionalSnapshot)
        .where(
            CpkRegionalSnapshot.reference_year == year,
            CpkRegionalSnapshot.reference_month == month,
        )
        .order_by(CpkRegionalSnapshot.regional)
    )
    return list(rows)
