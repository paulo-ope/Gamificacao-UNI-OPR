from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.core.security import require_permission
from app.db.session import get_db
from app.models import CalculationRun, CollaboratorScore, User
from app.schemas import CalculationRequest, CalculationRunHistoryOut, CalculationRunOut
from app.services.calculation import calculate_scores, latest_run, serialize_run
from app.services.audit_log import record_audit_log
from app.services.leadership_bonus import calculate_and_store_leadership_bonus

router = APIRouter(prefix="/calculation-runs", tags=["calculation-runs"])


def _serialize_history_run(run: CalculationRun) -> CalculationRunHistoryOut:
    scores = list(run.scores)
    top_score = max(scores, key=lambda score: float(score.final_points), default=None)
    return CalculationRunHistoryOut(
        id=run.id,
        reference_month=run.reference_month,
        reference_year=run.reference_year,
        regional=run.regional,
        point_value=float(run.point_value),
        source_import_id=run.source_import_id,
        source_filename=run.source_filename,
        rules_version_id=run.rules_version_id,
        created_at=run.created_at,
        collaborators_count=len(scores),
        service_orders_count=sum(int(score.service_orders_count) for score in scores),
        gross_points=round(sum(float(score.gross_points) for score in scores), 2),
        penalty_points=round(sum(float(score.penalty_points) for score in scores), 2),
        net_points=round(sum(float(score.net_points) for score in scores), 2),
        final_points=round(sum(float(score.final_points) for score in scores), 2),
        estimated_payment=round(sum(float(score.estimated_payment) for score in scores), 2),
        top_collaborator_name=top_score.collaborator.name if top_score and top_score.collaborator else None,
        top_collaborator_points=round(float(top_score.final_points), 2) if top_score else None,
    )


@router.get("", response_model=list[CalculationRunHistoryOut])
def list_calculation_runs(
    limit: int = 24,
    include_empty: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("dashboard:read")),
):
    runs = db.scalars(
        select(CalculationRun)
        .options(selectinload(CalculationRun.scores).selectinload(CollaboratorScore.collaborator))
        .order_by(desc(CalculationRun.created_at), desc(CalculationRun.id))
        .limit(100)
    ).all()
    history = [_serialize_history_run(run) for run in runs]
    if not include_empty:
        history = [run for run in history if run.service_orders_count > 0]
    return history[: min(max(limit, 1), 100)]


@router.post("/calculate", response_model=CalculationRunOut)
def calculate(
    payload: CalculationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("calculation:run")),
):
    run = calculate_scores(
        db,
        reference_month=payload.reference_month,
        reference_year=payload.reference_year,
        regional=payload.regional,
        point_value=payload.point_value,
    )
    calculate_and_store_leadership_bonus(db, run)
    record_audit_log(db, user, "run", "calculation_runs", run.id, None, payload)
    db.commit()
    return serialize_run(run, db)


@router.get("/latest", response_model=CalculationRunOut | None)
def get_latest_run(db: Session = Depends(get_db), user: User = Depends(require_permission("dashboard:read"))):
    return serialize_run(latest_run(db), db)
