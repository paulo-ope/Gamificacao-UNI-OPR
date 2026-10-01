from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_permission
from app.db.session import get_db
from app.models import CalculationRun, CpkRegionalSnapshot, User
from app.schemas import (
    CpkRegionalSnapshotOut,
    CpkRuleOut,
    CpkRuleUpdate,
    CpkSyncRequest,
    GamificationConfigImport,
    GamificationConfigOut,
)
from app.services.audit_log import record_audit_log
from app.services.cpk_client import CpkApiError
from app.services.cpk_health import get_cpk_rule, set_cpk_rule, sync_cpk_snapshot
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


@router.get("/cpk/rule", response_model=CpkRuleOut)
def get_cpk_rule_endpoint(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scoring:read")),
):
    """Regra de CPK da competência: both (soma e desconta), penalty_only (só desconta fora da
    meta), bonus_only (só soma quem está na meta) ou none (CPK não interfere)."""
    return {"year": year, "month": month, "rule": get_cpk_rule(db, year, month)}


@router.put("/cpk/rule", response_model=CpkRuleOut)
def save_cpk_rule(
    payload: CpkRuleUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("settings:write")),
):
    """Define a regra de CPK de uma competência. Só afeta cálculos feitos depois - o fechamento
    do período precisa ser recalculado para refletir a mudança."""
    paid_run = db.scalar(
        select(CalculationRun.id)
        .where(
            CalculationRun.reference_year == payload.year,
            CalculationRun.reference_month == payload.month,
            CalculationRun.status == "paid",
        )
        .limit(1)
    )
    if paid_run:
        raise HTTPException(status_code=409, detail="Este período já está pago e não pode mudar a regra de CPK.")
    try:
        before = {"rule": get_cpk_rule(db, payload.year, payload.month)}
        set_cpk_rule(db, payload.year, payload.month, payload.rule)
        record_audit_log(
            db, user, "update", "cpk_rule", f"{payload.year}-{payload.month:02d}", before, {"rule": payload.rule},
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"year": payload.year, "month": payload.month, "rule": payload.rule}


@router.get("/cpk/snapshot",response_model=list[CpkRegionalSnapshotOut])
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
