from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.security import require_permission
from app.db.session import get_db
from app.models import User
from app.modules.management.models import ManagementCase, ManagementCaseReason, ManagementOperationalMember
from app.modules.management.schemas import (
    ManagementCaseCreate,
    ManagementCaseJustification,
    ManagementCaseOut,
    ManagementCaseReasonOut,
    ManagementDashboardOut,
    ManagementMemberUpdate,
    ManagementOptionOut,
    ManagementOptionsOut,
)
from app.modules.management.services import member_out, refresh_operational_members, summarize_members, visible_member_filters
from app.modules.operations.models import OperationTeamModel
from app.services.audit_log import record_audit_log, snapshot

router = APIRouter(prefix="/management", tags=["management"])


@router.get("/options", response_model=ManagementOptionsOut)
def options(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("management:read")),
):
    supervisors = db.scalars(select(User).where(User.active.is_(True)).order_by(User.name.asc())).all()
    team_models = db.scalars(select(OperationTeamModel).where(OperationTeamModel.active.is_(True)).order_by(OperationTeamModel.name.asc())).all()
    return ManagementOptionsOut(
        supervisors=[ManagementOptionOut(id=item.id, name=item.name) for item in supervisors],
        team_models=[ManagementOptionOut(id=item.id, name=item.name) for item in team_models],
    )


def _case_out(item: ManagementCase) -> ManagementCaseOut:
    return ManagementCaseOut(
        id=item.id,
        case_type=item.case_type,
        source_module=item.source_module,
        reference_date=item.reference_date,
        reference_month=item.reference_month,
        reference_year=item.reference_year,
        regional=item.regional,
        collaborator_id=item.collaborator_id,
        collaborator_name=item.collaborator.name if item.collaborator else None,
        responsible_name=item.responsible_name,
        supervisor_user_id=item.supervisor_user_id,
        supervisor_name=item.supervisor.name if item.supervisor else None,
        team_model_id=item.team_model_id,
        team_model_name=item.team_model.name if item.team_model else None,
        metric_name=item.metric_name,
        expected_value=item.expected_value,
        actual_value=item.actual_value,
        deviation_value=item.deviation_value,
        severity=item.severity,
        status=item.status,
        reason_id=item.reason_id,
        reason_name=item.reason.name if item.reason else None,
        justification_text=item.justification_text,
        action_plan=item.action_plan,
        due_date=item.due_date,
        created_at=item.created_at,
        updated_at=item.updated_at,
        justified_at=item.justified_at,
        reviewed_by=item.reviewed_by,
        reviewed_at=item.reviewed_at,
    )


@router.get("/dashboard", response_model=ManagementDashboardOut)
def dashboard(
    regional: str | None = None,
    supervisor_user_id: int | None = None,
    status: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("management:read")),
):
    filters = visible_member_filters(regional, supervisor_user_id, status, search)
    members = db.scalars(
        select(ManagementOperationalMember)
        .options(
            selectinload(ManagementOperationalMember.collaborator),
            selectinload(ManagementOperationalMember.supervisor),
            selectinload(ManagementOperationalMember.team_model),
        )
        .where(*filters)
        .order_by(ManagementOperationalMember.status.asc(), ManagementOperationalMember.regional.asc(), ManagementOperationalMember.responsible_name.asc())
        .limit(500)
    ).all()
    open_cases = db.scalar(
        select(func.count(ManagementCase.id)).where(ManagementCase.status.in_(["pending", "justified", "in_progress"]))
    ) or 0
    overdue_cases = db.scalar(
        select(func.count(ManagementCase.id))
        .where(ManagementCase.status.in_(["pending", "justified", "in_progress"]))
        .where(ManagementCase.due_date.is_not(None), ManagementCase.due_date < date.today())
    ) or 0
    return ManagementDashboardOut(summary=summarize_members(list(members), open_cases, overdue_cases), members=[member_out(item) for item in members])


@router.post("/structure/refresh")
def refresh_structure(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management:manage_structure")),
):
    created = refresh_operational_members(db)
    record_audit_log(db, user, "refresh", "management_operational_members", "structure", None, {"created_candidates": created})
    db.commit()
    return {"created_candidates": created}


@router.patch("/members/{member_id}", response_model=dict)
def update_member(
    member_id: int,
    payload: ManagementMemberUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management:manage_structure")),
):
    member = db.get(ManagementOperationalMember, member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Colaborador operacional não encontrado.")
    before = snapshot(member)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(member, field, value)
    if "status" in updates and updates["status"] in {"validated_operation", "active_management"}:
        member.validated_by = user.id
        member.validated_at = datetime.now(timezone.utc)
    record_audit_log(db, user, "update", "management_operational_members", member.id, before, snapshot(member))
    db.commit()
    return {"status": "ok"}


@router.get("/cases", response_model=list[ManagementCaseOut])
def list_cases(
    status: str | None = None,
    regional: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("management:read")),
):
    filters = []
    if status:
        filters.append(ManagementCase.status == status)
    if regional:
        filters.append(ManagementCase.regional == regional)
    rows = db.scalars(
        select(ManagementCase)
        .options(
            selectinload(ManagementCase.collaborator),
            selectinload(ManagementCase.supervisor),
            selectinload(ManagementCase.team_model),
            selectinload(ManagementCase.reason),
        )
        .where(*filters)
        .order_by(ManagementCase.created_at.desc())
        .limit(300)
    ).all()
    return [_case_out(item) for item in rows]


@router.post("/cases", response_model=ManagementCaseOut, status_code=201)
def create_case(
    payload: ManagementCaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management:review")),
):
    item = ManagementCase(**payload.model_dump(), status="pending", created_by=user.id)
    db.add(item)
    db.flush()
    record_audit_log(db, user, "create", "management_cases", item.id, None, snapshot(item))
    db.commit()
    db.refresh(item)
    return _case_out(item)


@router.post("/cases/{case_id}/justify", response_model=ManagementCaseOut)
def justify_case(
    case_id: int,
    payload: ManagementCaseJustification,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management:write_justification")),
):
    item = db.get(ManagementCase, case_id)
    if not item:
        raise HTTPException(status_code=404, detail="Caso de gestão não encontrado.")
    before = snapshot(item)
    item.reason_id = payload.reason_id
    item.justification_text = payload.justification_text.strip()
    item.action_plan = payload.action_plan.strip() if payload.action_plan else None
    item.status = payload.status
    item.justified_at = datetime.now(timezone.utc)
    record_audit_log(db, user, "justify", "management_cases", item.id, before, snapshot(item))
    db.commit()
    db.refresh(item)
    return _case_out(item)


@router.get("/case-reasons", response_model=list[ManagementCaseReasonOut])
def list_reasons(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("management:read")),
):
    return db.scalars(select(ManagementCaseReason).order_by(ManagementCaseReason.name.asc())).all()
