from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.core.performance import performance_step
from app.core.security import require_permission
from app.db.session import get_db
from app.models import AuditLog, CalculationRun, ServiceOrder
from app.schemas import AuditLogOut, AuditServiceOrderDetail, AuditServiceOrdersOut, RecurrenceAuditOut
from app.services.calculation import latest_run
from app.services.scoring_detail import explain_orders, get_period_audit, get_point_value, get_recurrence_audit

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs", response_model=list[AuditLogOut])
def list_audit_logs(
    action: str | None = None,
    entity: str | None = None,
    entity_id: str | None = None,
    user_id: int | None = None,
    search: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user=Depends(require_permission("audit:read")),
):
    stmt = select(AuditLog).options(selectinload(AuditLog.user))
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if entity:
        stmt = stmt.where(AuditLog.entity == entity)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == str(entity_id))
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if search:
        term = f"%{search.strip().lower()}%"
        stmt = stmt.where(AuditLog.action.ilike(term) | AuditLog.entity.ilike(term) | AuditLog.entity_id.ilike(term))
    stmt = stmt.order_by(desc(AuditLog.created_at), desc(AuditLog.id)).limit(limit).offset(offset)

    logs = list(db.scalars(stmt))
    return [
        AuditLogOut(
            id=log.id,
            user_id=log.user_id,
            user_name=log.user.name if log.user else None,
            user_email=log.user.email if log.user else None,
            action=log.action,
            entity=log.entity,
            entity_id=log.entity_id,
            before_data=log.before_data if isinstance(log.before_data, dict) else None,
            after_data=log.after_data if isinstance(log.after_data, dict) else None,
            created_at=log.created_at,
        )
        for log in logs
    ]


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
            raise HTTPException(status_code=404, detail="Apuração não encontrada.")
    else:
        run = latest_run(db)

    now = datetime.now(timezone.utc)
    month = reference_month or (run.reference_month if run else now.month)
    year = reference_year or (run.reference_year if run else now.year)
    selected_regional = regional if regional is not None else (run.regional if run else None)
    point_value = run.point_value if run else get_point_value(db)

    with performance_step("audit.service-orders-scoring", "get_period_audit"):
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
        raise HTTPException(status_code=404, detail="Auditoria de reincidência não encontrada para a O.S. informada.") from exc


@router.get("/service-orders/{service_order_id}/detail", response_model=AuditServiceOrderDetail)
def service_order_detail_audit(
    service_order_id: int,
    calculation_run_id: int | None = None,
    db: Session = Depends(get_db),
    user=Depends(require_permission("audit:read")),
):
    order = db.get(ServiceOrder, service_order_id)
    if not order:
        raise HTTPException(status_code=404, detail="O.S não encontrada.")

    run: CalculationRun | None = None
    if calculation_run_id:
        run = db.get(CalculationRun, calculation_run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Apuração não encontrada.")

    point_value = float(run.point_value) if run else float(get_point_value(db))
    details = explain_orders(
        db,
        [order],
        default_point_value=point_value,
        include_explanations=True,
    )
    if not details:
        raise HTTPException(status_code=404, detail="Auditoria detalhada não encontrada para a O.S. informada.")
    return details[0]


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
