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

    if run is None:
        # Sem periodo selecionado: mantem o comportamento antigo (acumulado de todos os tempos).
        query = select(PointBalanceEntry).where(PointBalanceEntry.status == "pending")
    elif run.status == "paid":
        # Fechamento ja pago: mostra o que REALMENTE foi descontado nesse pagamento (apply_pending_entries_for_paid_run
        # grava applied_calculation_run_id = este run ao consumir os pendentes do colaborador).
        query = select(PointBalanceEntry).where(PointBalanceEntry.applied_calculation_run_id == run.id)
    else:
        # Fechamento ainda em rascunho/revisao/aprovado: mostra o que SERIA descontado se este
        # periodo fosse marcado como pago agora - todo pendente dos colaboradores deste fechamento,
        # independente de quando a O.S original (origin_calculation_run_id) foi paga. Filtrar pela
        # origem mostraria o debito no mes da O.S antiga, nao no mes em que ele de fato vai ser
        # descontado - o que obrigaria o usuario a navegar ate o periodo errado para ver o pendente.
        collaborator_ids = select(CollaboratorScore.collaborator_id).where(CollaboratorScore.calculation_run_id == run.id)
        query = select(PointBalanceEntry).where(
            PointBalanceEntry.status == "pending",
            PointBalanceEntry.collaborator_id.in_(collaborator_ids),
        )

    entries = list(
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
    return [serialize_entry(entry) for entry in entries]


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
