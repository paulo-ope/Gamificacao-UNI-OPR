from datetime import datetime, timezone
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.security import require_permission
from app.models import CalculationRun, Collaborator, ServiceOrder, User
from app.schemas import (
    CollaboratorCreate,
    CollaboratorDeleteResult,
    CollaboratorOut,
    CollaboratorRegistryOut,
    CollaboratorServiceOrdersDetailOut,
    CollaboratorUpdate,
)
from app.services.calculation import latest_run
from app.services.regional import is_valid_regional, normalize_regional
from app.services.scoring_detail import get_collaborator_service_orders_detail, get_point_value
from app.services.audit_log import record_audit_log, snapshot

router = APIRouter(prefix="/collaborators", tags=["collaborators"])


@router.get("", response_model=list[CollaboratorOut])
def list_collaborators(db: Session = Depends(get_db), user: User = Depends(require_permission("audit:read"))):
    return (
        db.scalars(
            select(Collaborator)
            .join(ServiceOrder, ServiceOrder.collaborator_id == Collaborator.id)
            .distinct()
            .order_by(Collaborator.name.asc())
        )
        .all()
    )


@router.get("/registry", response_model=CollaboratorRegistryOut)
def collaborators_registry(db: Session = Depends(get_db), user: User = Depends(require_permission("audit:read"))):
    collaborators = list(db.scalars(select(Collaborator).order_by(Collaborator.name.asc(), Collaborator.id.asc())))
    orders = list(db.scalars(select(ServiceOrder)))
    orders_by_collaborator: dict[int, list[ServiceOrder]] = {}
    for order in orders:
        orders_by_collaborator.setdefault(order.collaborator_id, []).append(order)

    def build_item(collaborator: Collaborator):
        linked_orders = orders_by_collaborator.get(collaborator.id, [])
        regionals = [normalize_regional(order.regional) for order in linked_orders if is_valid_regional(order.regional)]
        roles = [collaborator.role] if collaborator.role and collaborator.role != "Importado UpValue" else []
        suggested_regional = Counter(regionals).most_common(1)[0][0] if regionals else normalize_regional(collaborator.regional)
        suggested_role = roles[0] if roles else ("Importado UpValue" if linked_orders else collaborator.role)
        return {
            "id": collaborator.id,
            "name": collaborator.name,
            "role": collaborator.role,
            "regional": normalize_regional(collaborator.regional),
            "active": collaborator.active,
            "is_registered": collaborator.is_registered,
            "service_orders_count": len(linked_orders),
            "suggested_regional": suggested_regional,
            "suggested_role": suggested_role,
            "has_linked_orders": bool(linked_orders),
        }

    items = [build_item(collaborator) for collaborator in collaborators if is_valid_regional(collaborator.regional) or orders_by_collaborator.get(collaborator.id)]
    registered = [item for item in items if item["is_registered"]]
    unregistered = [item for item in items if not item["is_registered"]]
    return {"registered": registered, "unregistered": unregistered}


@router.post("", response_model=CollaboratorOut, status_code=201)
def create_collaborator(
    payload: CollaboratorCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scoring:write")),
):
    data = payload.model_dump()
    data["regional"] = normalize_regional(data.get("regional"))
    collaborator = Collaborator(**data)
    db.add(collaborator)
    db.flush()
    record_audit_log(db, user, "create", "collaborators", collaborator.id, None, snapshot(collaborator))
    db.commit()
    db.refresh(collaborator)
    return collaborator


@router.delete("/{collaborator_id}", response_model=CollaboratorDeleteResult)
def delete_collaborator(
    collaborator_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scoring:write")),
):
    collaborator = db.get(Collaborator, collaborator_id)
    if not collaborator:
        raise HTTPException(status_code=404, detail="Colaborador nao encontrado.")

    linked_orders = list(db.scalars(select(ServiceOrder).where(ServiceOrder.collaborator_id == collaborator_id)))
    if linked_orders:
        before = snapshot(collaborator)
        collaborator.active = False
        collaborator.is_registered = False
        if not collaborator.role or collaborator.role.strip() == "":
            collaborator.role = "Importado UpValue"
        record_audit_log(db, user, "soft_delete", "collaborators", collaborator.id, before, snapshot(collaborator))
        db.commit()
        return {
            "id": collaborator.id,
            "deleted": False,
            "soft_deleted": True,
            "moved_to_unregistered": True,
        }

    before = snapshot(collaborator)
    record_audit_log(db, user, "delete", "collaborators", collaborator.id, before, None)
    db.delete(collaborator)
    db.commit()
    return {
        "id": collaborator_id,
        "deleted": True,
        "soft_deleted": False,
        "moved_to_unregistered": False,
    }


@router.get("/{collaborator_id}/service-orders-detail", response_model=CollaboratorServiceOrdersDetailOut)
def collaborator_service_orders_detail(
    collaborator_id: int,
    calculation_run_id: int | None = None,
    reference_month: int | None = Query(default=None, ge=1, le=12),
    reference_year: int | None = Query(default=None, ge=2000),
    regional: str | None = None,
    only_scored: bool = False,
    only_unscored: bool = False,
    only_penalized: bool = False,
    only_sla_out: bool = False,
    only_warranty: bool = False,
    only_recurrence: bool = False,
    only_non_recurrent: bool = False,
    only_diagnosis_blocked: bool = False,
    os_type: str | None = None,
    os_subject: str | None = None,
    status_sla: str | None = None,
    group_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("audit:read")),
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

    try:
        return get_collaborator_service_orders_detail(
            db,
            collaborator_id=collaborator_id,
            reference_month=month,
            reference_year=year,
            regional=selected_regional,
            only_scored=only_scored,
            only_unscored=only_unscored,
            only_penalized=only_penalized,
            only_sla_out=only_sla_out,
            only_warranty=only_warranty,
            only_recurrence=only_recurrence,
            only_non_recurrent=only_non_recurrent,
            only_diagnosis_blocked=only_diagnosis_blocked,
            os_type=os_type,
            os_subject=os_subject,
            status_sla=status_sla,
            group_id=group_id,
            point_value=point_value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{collaborator_id}/scoring-detail", response_model=CollaboratorServiceOrdersDetailOut)
def collaborator_scoring_detail(
    collaborator_id: int,
    calculation_run_id: int | None = None,
    reference_month: int | None = Query(default=None, ge=1, le=12),
    reference_year: int | None = Query(default=None, ge=2000),
    regional: str | None = None,
    only_scored: bool = False,
    only_unscored: bool = False,
    only_penalized: bool = False,
    only_sla_out: bool = False,
    only_warranty: bool = False,
    only_recurrence: bool = False,
    only_non_recurrent: bool = False,
    only_diagnosis_blocked: bool = False,
    os_type: str | None = None,
    os_subject: str | None = None,
    status_sla: str | None = None,
    group_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("audit:read")),
):
    return collaborator_service_orders_detail(
        collaborator_id=collaborator_id,
        calculation_run_id=calculation_run_id,
        reference_month=reference_month,
        reference_year=reference_year,
        regional=regional,
        only_scored=only_scored,
        only_unscored=only_unscored,
        only_penalized=only_penalized,
        only_sla_out=only_sla_out,
        only_warranty=only_warranty,
        only_recurrence=only_recurrence,
        only_non_recurrent=only_non_recurrent,
        only_diagnosis_blocked=only_diagnosis_blocked,
        os_type=os_type,
        os_subject=os_subject,
        status_sla=status_sla,
        group_id=group_id,
        db=db,
        user=user,
    )


@router.put("/{collaborator_id}", response_model=CollaboratorOut)
def update_collaborator(
    collaborator_id: int,
    payload: CollaboratorUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scoring:write")),
):
    collaborator = db.get(Collaborator, collaborator_id)
    if not collaborator:
        raise HTTPException(status_code=404, detail="Colaborador nao encontrado.")

    before = snapshot(collaborator)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(collaborator, field, normalize_regional(value) if field == "regional" else value)
    record_audit_log(db, user, "update", "collaborators", collaborator.id, before, snapshot(collaborator))
    db.commit()
    db.refresh(collaborator)
    return collaborator
