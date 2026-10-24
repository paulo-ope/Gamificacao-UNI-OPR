"""Rotas da aba Especialista/Analista (projetos e tarefas). Montadas dentro do router do Suporte,
que já exige `support:read`; escrever exige também `support:plan_write`."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import require_permission
from app.db.session import get_db
from app.models import User
from app.services.audit_log import record_audit_log

from . import planning_service
from .schemas import (
    SupportPlanArchive,
    SupportPlanItemCreate,
    SupportPlanItemDetail,
    SupportPlanItemPage,
    SupportPlanItemUpdate,
    SupportPlanPerson,
    SupportPlanSummary,
    SupportPlanUpdateCreate,
)

router = APIRouter(prefix="/planning")

_WRITE = "support:plan_write"
_ENTITY = "support_plan_item"


@router.get("/items", response_model=SupportPlanItemPage)
def list_plan_items(
    status: str | None = Query(default=None, description="Status separados por vírgula"),
    kind: str | None = Query(default=None, pattern="^(project|task)$"),
    assignee_id: int | None = Query(default=None, ge=1),
    q: str | None = Query(default=None, max_length=120),
    include_archived: bool = False,
    only_overdue: bool = False,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    statuses = [value.strip() for value in status.split(",") if value.strip()] if status else None
    return planning_service.list_items(
        db,
        statuses=statuses,
        kind=kind,
        assignee_id=assignee_id,
        search=q,
        include_archived=include_archived,
        only_overdue=only_overdue,
        limit=limit,
        offset=offset,
    )


@router.get("/summary", response_model=SupportPlanSummary)
def plan_summary(db: Session = Depends(get_db)):
    return planning_service.summary(db)


@router.get("/people", response_model=list[SupportPlanPerson])
def plan_people(db: Session = Depends(get_db)):
    return planning_service.people(db)


@router.get("/items/{item_id}", response_model=SupportPlanItemDetail)
def plan_item_detail(item_id: int, db: Session = Depends(get_db)):
    return planning_service.item_detail(db, item_id)


@router.post("/items", response_model=SupportPlanItemDetail, status_code=201)
def create_plan_item(
    payload: SupportPlanItemCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(_WRITE)),
):
    item = planning_service.create_item(db, user, payload)
    record_audit_log(db, user, "create", _ENTITY, item.id, None, planning_service.audit_snapshot(item))
    db.commit()
    return planning_service.item_detail(db, item.id)


@router.patch("/items/{item_id}", response_model=SupportPlanItemDetail)
def update_plan_item(
    item_id: int,
    payload: SupportPlanItemUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(_WRITE)),
):
    item, before = planning_service.update_item(db, item_id, payload)
    record_audit_log(db, user, "update", _ENTITY, item.id, before, planning_service.audit_snapshot(item))
    db.commit()
    return planning_service.item_detail(db, item.id)


@router.post("/items/{item_id}/updates", response_model=SupportPlanItemDetail, status_code=201)
def add_plan_update(
    item_id: int,
    payload: SupportPlanUpdateCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(_WRITE)),
):
    item, before = planning_service.add_update(db, user, item_id, payload)
    record_audit_log(db, user, "progress", _ENTITY, item.id, before, planning_service.audit_snapshot(item))
    db.commit()
    return planning_service.item_detail(db, item.id)


@router.post("/items/{item_id}/archive", response_model=SupportPlanItemDetail)
def archive_plan_item(
    item_id: int,
    payload: SupportPlanArchive,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(_WRITE)),
):
    item, before = planning_service.set_archived(db, item_id, payload)
    record_audit_log(db, user, "archive" if item.archived else "unarchive", _ENTITY, item.id, before, planning_service.audit_snapshot(item))
    db.commit()
    return planning_service.item_detail(db, item.id)
