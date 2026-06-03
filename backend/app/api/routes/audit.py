from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import require_permission
from app.db.session import get_db
from app.models import CalculationRun
from app.schemas import AuditServiceOrdersOut, RecurrenceAuditOut
from app.services.calculation import latest_run
from app.services.scoring_detail import get_period_audit, get_point_value, get_recurrence_audit

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/service-orders", response_model=AuditServiceOrdersOut)
def service_orders_audit(
    calculation_run_id: int | None = None,
    reference_month: int | None = Query(default=None, ge=1, le=12),
    reference_year: int | None = Query(default=None, ge=2000),
    regional: str | None = None,
    collaborator_id: int | None = None,
    group_id: int | None = None,
    os_type: str | None = None,
    os_subject: str | None = None,
    status_sla: str | None = None,
    only_scored: bool = False,
    only_unscored: bool = False,
    only_penalized: bool = False,
    only_sla_out: bool = False,
    only_warranty: bool = False,
    only_recurrence: bool = False,
    only_non_recurrent: bool = False,
    only_diagnosis_blocked: bool = False,
    audit_group_mode: str | None = None,
    audit_group_label: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=25, le=5000),
    db: Session = Depends(get_db),
    user=Depends(require_permission("audit:read")),
):
    run: CalculationRun | None = None
    if calculation_run_id:
        run = db.get(CalculationRun, calculation_run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Apuracao nao encontrada.")
    else:
        run = latest_run(db)

    now = datetime.now(timezone.utc)
    month = reference_month or (run.reference_month if run else now.month)
    year = reference_year or (run.reference_year if run else now.year)
    selected_regional = regional if regional is not None else (run.regional if run else None)
    point_value = run.point_value if run else get_point_value(db)

    return get_period_audit(
        db,
        reference_month=month,
        reference_year=year,
        regional=selected_regional,
        collaborator_id=collaborator_id,
        group_id=group_id,
        only_scored=only_scored,
        only_unscored=only_unscored,
        only_penalized=only_penalized,
        only_sla_out=only_sla_out,
        only_warranty=only_warranty,
        only_recurrence=only_recurrence,
        only_non_recurrent=only_non_recurrent,
        only_diagnosis_blocked=only_diagnosis_blocked,
        audit_group_mode=audit_group_mode,
        audit_group_label=audit_group_label,
        os_type=os_type,
        os_subject=os_subject,
        status_sla=status_sla,
        point_value=point_value,
        page=page,
        page_size=page_size,
    )


@router.get("/service-orders/{service_order_id}/recurrence-audit", response_model=RecurrenceAuditOut)
def service_order_recurrence_audit(
    service_order_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_permission("audit:read")),
):
    try:
        return get_recurrence_audit(db, service_order_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/service-orders-scoring", response_model=AuditServiceOrdersOut)
def service_orders_scoring_audit(
    calculation_run_id: int | None = None,
    reference_month: int | None = Query(default=None, ge=1, le=12),
    reference_year: int | None = Query(default=None, ge=2000),
    regional: str | None = None,
    collaborator_id: int | None = None,
    group_id: int | None = None,
    os_type: str | None = None,
    os_subject: str | None = None,
    status_sla: str | None = None,
    only_scored: bool = False,
    only_unscored: bool = False,
    only_penalized: bool = False,
    only_sla_out: bool = False,
    only_warranty: bool = False,
    only_recurrence: bool = False,
    only_non_recurrent: bool = False,
    only_diagnosis_blocked: bool = False,
    audit_group_mode: str | None = None,
    audit_group_label: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=25, le=5000),
    db: Session = Depends(get_db),
    user=Depends(require_permission("audit:read")),
):
    return service_orders_audit(
        calculation_run_id=calculation_run_id,
        reference_month=reference_month,
        reference_year=reference_year,
        regional=regional,
        collaborator_id=collaborator_id,
        group_id=group_id,
        os_type=os_type,
        os_subject=os_subject,
        status_sla=status_sla,
        only_scored=only_scored,
        only_unscored=only_unscored,
        only_penalized=only_penalized,
        only_sla_out=only_sla_out,
        only_warranty=only_warranty,
        only_recurrence=only_recurrence,
        only_non_recurrent=only_non_recurrent,
        only_diagnosis_blocked=only_diagnosis_blocked,
        audit_group_mode=audit_group_mode,
        audit_group_label=audit_group_label,
        page=page,
        page_size=page_size,
        db=db,
        user=user,
    )
