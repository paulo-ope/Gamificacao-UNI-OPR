from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.security import require_permission
from app.db.session import get_db
from app.models import (
    CalculationRun,
    CollaboratorScore,
    LeadershipBonusResult,
    LeadershipProfile,
    LeadershipRoleProfile,
    User,
    default_percentage_for_role,
)
from app.schemas import (
    LeadershipBonusSummaryOut,
    LeadershipProfileCreate,
    LeadershipProfileOut,
    LeadershipProfileUpdate,
    LeadershipRoleProfileCreate,
    LeadershipRoleProfileOut,
    LeadershipRoleProfileUpdate,
)
from app.services.audit_log import record_audit_log, snapshot
from app.services.calculation import latest_run
from app.services.leadership_bonus import (
    calculate_and_store_leadership_bonus,
    default_multiplier_for_role,
    ensure_default_role_profiles,
    effective_multiplier,
    normalize_average_source,
    normalize_regionals,
    normalize_role_type,
    replace_profile_regionals,
    serialize_profile,
    serialize_role_profile,
    validate_no_scope_overlap,
    validate_scope_regionals_required,
)

router = APIRouter(prefix="/leadership", tags=["leadership"])


@router.get("/profiles", response_model=list[LeadershipProfileOut])
def list_leadership_profiles(db: Session = Depends(get_db), user: User = Depends(require_permission("scoring:read"))):
    profiles = list(
        db.scalars(
            select(LeadershipProfile)
            .options(selectinload(LeadershipProfile.regionals), selectinload(LeadershipProfile.role_profile))
            .order_by(LeadershipProfile.role_type.asc(), LeadershipProfile.name.asc())
        )
    )
    return [serialize_profile(profile) for profile in profiles]


@router.get("/role-profiles", response_model=list[LeadershipRoleProfileOut])
def list_leadership_role_profiles(db: Session = Depends(get_db), user: User = Depends(require_permission("scoring:read"))):
    profiles = list(
        db.scalars(
            select(LeadershipRoleProfile)
            .options(selectinload(LeadershipRoleProfile.leaders))
            .order_by(LeadershipRoleProfile.name.asc())
        )
    )
    return [serialize_role_profile(profile) for profile in profiles]


@router.post("/role-profiles/ensure-defaults", response_model=list[LeadershipRoleProfileOut])
def ensure_leadership_role_profiles(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("settings:write")),
):
    profiles = ensure_default_role_profiles(db)
    db.commit()
    return [serialize_role_profile(profile) for profile in profiles]


@router.post("/role-profiles", response_model=LeadershipRoleProfileOut, status_code=201)
def create_leadership_role_profile(
    payload: LeadershipRoleProfileCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scoring:write")),
):
    role_profile = LeadershipRoleProfile(
        name=payload.name.strip(),
        scope_type=normalize_role_type(payload.scope_type),
        default_multiplier=float(payload.default_multiplier),
        active=payload.active,
    )
    db.add(role_profile)
    db.flush()
    record_audit_log(db, user, "create", "leadership_role_profiles", role_profile.id, None, serialize_role_profile(role_profile))
    db.commit()
    db.refresh(role_profile)
    return serialize_role_profile(role_profile)


@router.put("/role-profiles/{role_profile_id}", response_model=LeadershipRoleProfileOut)
def update_leadership_role_profile(
    role_profile_id: int,
    payload: LeadershipRoleProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scoring:write")),
):
    role_profile = db.scalar(
        select(LeadershipRoleProfile)
        .options(selectinload(LeadershipRoleProfile.leaders))
        .where(LeadershipRoleProfile.id == role_profile_id)
    )
    if not role_profile:
        raise HTTPException(status_code=404, detail="Perfil de cargo da liderança não encontrado.")

    before = serialize_role_profile(role_profile)
    if payload.name is not None:
        role_profile.name = payload.name.strip()
    if payload.scope_type is not None:
        role_profile.scope_type = normalize_role_type(payload.scope_type)
    if payload.default_multiplier is not None:
        role_profile.default_multiplier = float(payload.default_multiplier)
    if payload.active is not None:
        role_profile.active = payload.active

    for leader in role_profile.leaders:
        if not leader.use_custom_multiplier:
            leader.role_type = role_profile.scope_type
            leader.multiplier = effective_multiplier(leader)

    db.flush()
    after = serialize_role_profile(role_profile)
    record_audit_log(db, user, "update", "leadership_role_profiles", role_profile.id, before, after)
    db.commit()
    db.refresh(role_profile)
    return serialize_role_profile(role_profile)


@router.delete("/role-profiles/{role_profile_id}", response_model=LeadershipRoleProfileOut)
def delete_leadership_role_profile(
    role_profile_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scoring:write")),
):
    role_profile = db.scalar(
        select(LeadershipRoleProfile)
        .options(selectinload(LeadershipRoleProfile.leaders))
        .where(LeadershipRoleProfile.id == role_profile_id)
    )
    if not role_profile:
        raise HTTPException(status_code=404, detail="Perfil de cargo da liderança não encontrado.")
    if role_profile.leaders:
        raise HTTPException(status_code=409, detail="Existem lideres vinculados a este perfil. Reatribua-os antes de excluir.")
    before = serialize_role_profile(role_profile)
    db.delete(role_profile)
    record_audit_log(db, user, "delete", "leadership_role_profiles", role_profile.id, before, None)
    db.commit()
    return before


@router.post("/profiles", response_model=LeadershipProfileOut, status_code=201)
def create_leadership_profile(
    payload: LeadershipProfileCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scoring:write")),
):
    role_profiles = ensure_default_role_profiles(db)
    role_profile = None
    if payload.role_profile_id is not None:
        role_profile = db.get(LeadershipRoleProfile, payload.role_profile_id)
        if not role_profile:
            raise HTTPException(status_code=404, detail="Perfil de cargo da liderança não encontrado.")
    role_type = normalize_role_type(role_profile.scope_type if role_profile else payload.role_type)
    regionals = normalize_regionals(payload.regional_names)
    validate_scope_regionals_required(role_type, regionals)
    validate_no_scope_overlap(db, role_type, regionals)
    profile = LeadershipProfile(
        name=payload.name.strip(),
        role_type=role_type,
        percentage=default_percentage_for_role(role_type),
        role_profile_id=role_profile.id if role_profile else None,
        use_custom_multiplier=bool(payload.use_custom_multiplier),
        custom_multiplier=float(payload.custom_multiplier) if payload.custom_multiplier is not None else None,
        average_source=normalize_average_source(payload.average_source),
        multiplier=float(
            payload.custom_multiplier
            if payload.use_custom_multiplier and payload.custom_multiplier is not None
            else (
                role_profile.default_multiplier
                if role_profile
                else (payload.multiplier if payload.multiplier is not None else default_multiplier_for_role(role_type))
            )
        ),
        active=payload.active,
        collaborator_id=payload.collaborator_id,
    )
    replace_profile_regionals(db, profile, regionals)
    db.add(profile)
    db.flush()
    record_audit_log(db, user, "create", "leadership_profiles", profile.id, None, serialize_profile(profile))
    db.commit()
    db.refresh(profile)
    return serialize_profile(profile)


@router.put("/profiles/{profile_id}", response_model=LeadershipProfileOut)
def update_leadership_profile(
    profile_id: int,
    payload: LeadershipProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scoring:write")),
):
    profile = db.scalar(
        select(LeadershipProfile)
        .options(selectinload(LeadershipProfile.regionals), selectinload(LeadershipProfile.role_profile))
        .where(LeadershipProfile.id == profile_id)
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil de liderança não encontrado.")

    before = serialize_profile(profile)
    role_profile = profile.role_profile
    if payload.role_profile_id is not None:
        role_profile = db.get(LeadershipRoleProfile, payload.role_profile_id)
        if not role_profile:
            raise HTTPException(status_code=404, detail="Perfil de cargo da liderança não encontrado.")
        profile.role_profile_id = role_profile.id
    role_type = normalize_role_type(
        role_profile.scope_type if role_profile else (payload.role_type if payload.role_type is not None else profile.role_type)
    )
    if payload.name is not None:
        profile.name = payload.name.strip()
    profile.role_type = role_type
    profile.percentage = default_percentage_for_role(role_type)
    if payload.multiplier is not None:
        profile.multiplier = float(payload.multiplier)
    if payload.use_custom_multiplier is not None:
        profile.use_custom_multiplier = payload.use_custom_multiplier
    if payload.custom_multiplier is not None or payload.use_custom_multiplier is False:
        profile.custom_multiplier = float(payload.custom_multiplier) if payload.custom_multiplier is not None else None
    if payload.average_source is not None:
        profile.average_source = normalize_average_source(payload.average_source)
    if payload.active is not None:
        profile.active = payload.active
    if payload.collaborator_id is not None:
        profile.collaborator_id = payload.collaborator_id
    if payload.regional_names is not None:
        regionals = normalize_regionals(payload.regional_names)
        validate_scope_regionals_required(role_type, regionals)
        validate_no_scope_overlap(db, role_type, regionals, profile_id=profile.id)
        replace_profile_regionals(db, profile, regionals)
    else:
        existing_regionals = [item.regional_name for item in profile.regionals]
        validate_scope_regionals_required(role_type, existing_regionals)
        validate_no_scope_overlap(db, role_type, existing_regionals, profile_id=profile.id)

    profile.multiplier = effective_multiplier(profile)

    db.flush()
    after = serialize_profile(profile)
    record_audit_log(db, user, "update", "leadership_profiles", profile.id, before, after)
    db.commit()
    db.refresh(profile)
    return serialize_profile(profile)


@router.delete("/profiles/{profile_id}", response_model=LeadershipProfileOut)
def delete_leadership_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scoring:write")),
):
    profile = db.scalar(
        select(LeadershipProfile)
        .options(selectinload(LeadershipProfile.regionals), selectinload(LeadershipProfile.role_profile))
        .where(LeadershipProfile.id == profile_id)
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil de liderança não encontrado.")
    before = serialize_profile(profile)
    has_results = db.scalar(
        select(LeadershipBonusResult.id)
        .where(LeadershipBonusResult.leadership_profile_id == profile.id)
        .limit(1)
    )
    if has_results:
        profile.active = False
        db.flush()
        record_audit_log(db, user, "deactivate", "leadership_profiles", profile.id, before, serialize_profile(profile))
        deleted = serialize_profile(profile)
    else:
        deleted = before
        db.delete(profile)
        record_audit_log(db, user, "delete", "leadership_profiles", profile.id, before, None)
    db.commit()
    return deleted


@router.post("/bonus-results/calculate", response_model=LeadershipBonusSummaryOut)
def calculate_leadership_bonus_results(
    calculation_run_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("calculation:run")),
):
    try:
        run = db.get(CalculationRun, calculation_run_id) if calculation_run_id else latest_run(db)
        if not run:
            raise HTTPException(status_code=404, detail="Cálculo de referência não encontrado.")
        run = db.scalar(
            select(CalculationRun)
            .options(selectinload(CalculationRun.scores).selectinload(CollaboratorScore.collaborator))
            .where(CalculationRun.id == run.id)
        )
        if not run:
            raise HTTPException(status_code=404, detail="Cálculo de referência não encontrado.")
        summary = calculate_and_store_leadership_bonus(db, run)
        record_audit_log(db, user, "calculate", "leadership_bonus_results", run.id, None, summary)
        db.commit()
        return summary
    except Exception:
        db.rollback()
        raise
