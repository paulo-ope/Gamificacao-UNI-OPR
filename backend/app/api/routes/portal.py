from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import require_permission
from app.db.session import get_db
from app.models import User
from app.schemas import PortalAuditOut, PortalOrderOut, PortalOverviewOut, PortalRulesOut, PortalSimulationOut, PortalSummaryOut
from app.services.portal_dashboard import (
    build_portal_orders,
    build_portal_audit,
    build_portal_overview,
    build_portal_rules,
    build_portal_simulation,
    build_portal_summary,
)

router = APIRouter(prefix="/portal", tags=["portal"])


@router.get("/overview", response_model=PortalOverviewOut)
def portal_overview(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("portal:read_overview")),
):
    return build_portal_overview(db)


@router.get("/summary", response_model=PortalSummaryOut)
def portal_summary(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("portal:read_self")),
):
    return build_portal_summary(db, user)


@router.get("/my-orders", response_model=list[PortalOrderOut])
def portal_my_orders(
    limit: int = Query(80, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("portal:read_self")),
):
    return build_portal_orders(db, user, limit=limit)


@router.get("/my-audit", response_model=PortalAuditOut)
def portal_my_audit(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("portal:read_self")),
):
    return build_portal_audit(db, user)


@router.get("/rules", response_model=PortalRulesOut)
def portal_rules(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("portal:read_rules")),
):
    return build_portal_rules(db)


@router.get("/simulation", response_model=PortalSimulationOut)
def portal_simulation(
    extra_points: float = Query(0, ge=0, le=100000),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("portal:simulate_self")),
):
    return build_portal_simulation(db, user, extra_points=extra_points)
