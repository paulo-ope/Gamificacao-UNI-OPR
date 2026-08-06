from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm import Session

from app.core.security import is_admin_user, require_permission
from app.db.session import get_db
from app.models import CalculationRun, CollaboratorScore, PointBalanceEntry, User
from app.schemas import (
    PointBalanceEntryOut,
    PointBalanceManualAdjustmentRequest,
    PointBalanceResolveReviewRequest,
    PointBalanceRevertRequest,
)
from app.services.point_balance import create_manual_adjustment, resolve_review_entry, revert_entry, serialize_entry

router = APIRouter(prefix="/point-balance", tags=["point-balance"])


@router.get("/pending", response_model=list[PointBalanceEntryOut])
def list_pending_point_balance_entries(
    calculation_run_id: int | None = Query(default=None),
    reference_month: int | None = Query(default=None),
    reference_year: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("audit:read")),
):
    run: CalculationRun | None = None
    if calculation_run_id is not None:
        run = db.get(CalculationRun, calculation_run_id)
    elif reference_month is not None and reference_year is not None:
        run = db.scalar(
            select(CalculationRun)
            .where(CalculationRun.reference_month == reference_month, CalculationRun.reference_year == reference_year)
            .order_by(CalculationRun.id.desc())
        )

    def _load(query):
        return list(
            db.scalars(
                query.options(
                    selectinload(PointBalanceEntry.collaborator),
                    selectinload(PointBalanceEntry.original_service_order),
                    selectinload(PointBalanceEntry.related_service_order),
                    selectinload(PointBalanceEntry.origin_calculation_run),
                    selectinload(PointBalanceEntry.applied_calculation_run),
                )
                .order_by(PointBalanceEntry.created_at.asc(), PointBalanceEntry.id.asc())
            )
        )

    if run is None:
        # Sem periodo selecionado: mantem o comportamento antigo (acumulado de todos os tempos),
        # tudo pendente entra como "eligible" - nao ha um periodo de referencia pra separar por alvo.
        entries = _load(select(PointBalanceEntry).where(PointBalanceEntry.status == "pending"))
        return [{**serialize_entry(entry), "bucket": "eligible_pending"} for entry in entries]

    # Tres grupos sempre calculados juntos - o usuario precisa ver os tres num so lugar em vez de
    # adivinhar qual consulta corresponde a qual: (1) ja foi de fato descontado deste fechamento
    # pago (apply_pending_entries_for_paid_run grava applied_calculation_run_id = este run ao
    # consumir os pendentes), (2) ainda pendente mas ELEGIVEL para este fechamento (seria
    # descontado se ele fosse pago agora - alvo e deste mes ou anterior, ou sem alvo), (3)
    # pendente com alvo num mes POSTERIOR a este (nao tem nada a ver com este fechamento, so
    # aparece para dar visibilidade de que ainda existe e vai cair num pagamento futuro).
    period = (run.reference_year, run.reference_month)
    collaborator_ids = select(CollaboratorScore.collaborator_id).where(CollaboratorScore.calculation_run_id == run.id)

    applied_entries = _load(select(PointBalanceEntry).where(PointBalanceEntry.applied_calculation_run_id == run.id))
    pending_entries = _load(
        select(PointBalanceEntry).where(
            PointBalanceEntry.status == "pending",
            PointBalanceEntry.collaborator_id.in_(collaborator_ids),
        )
    )

    result = [{**serialize_entry(entry), "bucket": "applied"} for entry in applied_entries]
    for entry in pending_entries:
        target = (
            (entry.target_reference_year, entry.target_reference_month)
            if entry.target_reference_year is not None and entry.target_reference_month is not None
            else None
        )
        bucket = "deferred_pending" if target is not None and target > period else "eligible_pending"
        result.append({**serialize_entry(entry), "bucket": bucket})
    return result


@router.post("/entries", response_model=PointBalanceEntryOut)
def create_point_balance_manual_adjustment(
    payload: PointBalanceManualAdjustmentRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("audit:read")),
):
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Somente administrador pode lançar ajuste manual de saldo.")

    entry = create_manual_adjustment(
        db,
        collaborator_id=payload.collaborator_id,
        points=payload.points,
        reason=payload.reason,
        user=user,
    )
    db.commit()
    db.refresh(entry)
    return serialize_entry(entry)


@router.post("/entries/{entry_id}/resolve", response_model=PointBalanceEntryOut)
def resolve_point_balance_review(
    entry_id: int,
    payload: PointBalanceResolveReviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("audit:read")),
):
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Somente administrador pode resolver uma revisão manual.")

    entry = resolve_review_entry(db, entry_id, points=payload.points, user=user, note=payload.note)
    db.commit()
    db.refresh(entry)
    return serialize_entry(entry)


@router.post("/entries/{entry_id}/revert", response_model=PointBalanceEntryOut)
def revert_point_balance_entry(
    entry_id: int,
    payload: PointBalanceRevertRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("audit:read")),
):
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Somente administrador pode estornar um lancamento de saldo.")

    entry = revert_entry(db, entry_id, user=user, reason=payload.reason)
    db.commit()
    db.refresh(entry)
    return serialize_entry(entry)
