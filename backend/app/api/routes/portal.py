from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.security import require_permission
from app.db.session import get_db
from app.models import Collaborator, User
from app.schemas import (
    PortalAuditOut,
    PortalOrderOut,
    PortalOverviewOut,
    PortalProfileOut,
    PortalProfileUpdate,
    PortalRulesOut,
    PortalSimulationOut,
    PortalSummaryOut,
    PortalTeamSummaryOut,
)
from app.services.audit_log import record_audit_log
from app.services.portal_dashboard import (
    build_portal_orders,
    build_portal_audit,
    build_portal_overview,
    build_portal_rules,
    build_portal_simulation,
    build_portal_summary,
    build_portal_team_summary,
)

router = APIRouter(prefix="/portal", tags=["portal"])

MAX_PORTAL_PROFILE_PHOTO_BYTES = 2 * 1024 * 1024
ALLOWED_PORTAL_PROFILE_PHOTO_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _own_collaborator(db: Session, user: User) -> Collaborator:
    if user.collaborator_id is None:
        raise HTTPException(status_code=403, detail="Seu usuário não está vinculado a um colaborador.")
    collaborator = db.get(Collaborator, user.collaborator_id)
    if not collaborator or not collaborator.active or not collaborator.is_registered:
        raise HTTPException(status_code=404, detail="Cadastro de colaborador não está disponível para edição.")
    return collaborator


def _profile_out(collaborator: Collaborator) -> dict:
    return {
        "collaborator_id": collaborator.id,
        "name": collaborator.name,
        "role": collaborator.role,
        "regional": collaborator.regional,
        "phone": collaborator.phone,
        "email": collaborator.email,
        "has_photo": collaborator.photo is not None,
    }


@router.get("/overview", response_model=PortalOverviewOut)
def portal_overview(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("portal:read_overview")),
):
    return build_portal_overview(db)


@router.get("/summary", response_model=PortalSummaryOut)
def portal_summary(
    reference_month: int | None = Query(None, ge=1, le=12),
    reference_year: int | None = Query(None, ge=2020, le=2100),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("portal:read_self")),
):
    if (reference_month is None) != (reference_year is None):
        raise HTTPException(status_code=422, detail="Informe mês e ano juntos para consultar um fechamento.")
    return build_portal_summary(db, user, reference_month, reference_year)


@router.get("/profile", response_model=PortalProfileOut)
def portal_profile(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("portal:read_self")),
):
    return _profile_out(_own_collaborator(db, user))


@router.put("/profile", response_model=PortalProfileOut)
def update_portal_profile(
    payload: PortalProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("portal:update_self_profile")),
):
    collaborator = _own_collaborator(db, user)
    before = {"phone": collaborator.phone, "email": collaborator.email}
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(collaborator, field, value)
    record_audit_log(db, user, "update_self_profile", "collaborators", collaborator.id, before, {"phone": collaborator.phone, "email": collaborator.email})
    db.commit()
    db.refresh(collaborator)
    return _profile_out(collaborator)


@router.post("/profile/photo", response_model=PortalProfileOut)
async def upload_portal_profile_photo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("portal:update_self_profile")),
):
    collaborator = _own_collaborator(db, user)
    if file.content_type not in ALLOWED_PORTAL_PROFILE_PHOTO_CONTENT_TYPES:
        raise HTTPException(status_code=422, detail="Formato de imagem não suportado. Use JPEG, PNG ou WEBP.")
    contents = await file.read()
    if len(contents) > MAX_PORTAL_PROFILE_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="Imagem maior que 2MB. Envie uma foto menor.")
    had_photo_before = collaborator.photo is not None
    collaborator.photo = contents
    collaborator.photo_content_type = file.content_type
    record_audit_log(db, user, "update_self_profile_photo", "collaborators", collaborator.id, {"has_photo": had_photo_before}, {"has_photo": True, "photo_content_type": file.content_type})
    db.commit()
    db.refresh(collaborator)
    return _profile_out(collaborator)


@router.get("/profile/photo")
def portal_profile_photo(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("portal:read_self")),
):
    collaborator = _own_collaborator(db, user)
    if not collaborator.photo:
        raise HTTPException(status_code=404, detail="Colaborador sem foto de perfil.")
    return Response(content=collaborator.photo, media_type=collaborator.photo_content_type or "application/octet-stream")


@router.delete("/profile/photo", response_model=PortalProfileOut)
def delete_portal_profile_photo(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("portal:update_self_profile")),
):
    collaborator = _own_collaborator(db, user)
    had_photo_before = collaborator.photo is not None
    collaborator.photo = None
    collaborator.photo_content_type = None
    record_audit_log(db, user, "delete_self_profile_photo", "collaborators", collaborator.id, {"has_photo": had_photo_before}, {"has_photo": False})
    db.commit()
    db.refresh(collaborator)
    return _profile_out(collaborator)


@router.get("/my-orders", response_model=list[PortalOrderOut])
def portal_my_orders(
    limit: int = Query(80, ge=1, le=200),
    reference_month: int | None = Query(None, ge=1, le=12),
    reference_year: int | None = Query(None, ge=2020, le=2100),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("portal:read_self")),
):
    if (reference_month is None) != (reference_year is None):
        raise HTTPException(status_code=422, detail="Informe mês e ano juntos para consultar um fechamento.")
    return build_portal_orders(db, user, limit=limit, reference_month=reference_month, reference_year=reference_year)


@router.get("/my-audit", response_model=PortalAuditOut)
def portal_my_audit(
    reference_month: int | None = Query(None, ge=1, le=12),
    reference_year: int | None = Query(None, ge=2020, le=2100),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("portal:read_self")),
):
    if (reference_month is None) != (reference_year is None):
        raise HTTPException(status_code=422, detail="Informe mês e ano juntos para consultar um fechamento.")
    return build_portal_audit(db, user, reference_month, reference_year)


@router.get("/team-summary", response_model=PortalTeamSummaryOut)
def portal_team_summary(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("portal:read_regional_summary")),
):
    return build_portal_team_summary(db, user)


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
