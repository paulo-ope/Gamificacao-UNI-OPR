from __future__ import annotations

from collections import Counter
from typing import Iterable

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    CalculationRun,
    Collaborator,
    LeadershipBonusResult,
    LeadershipProfile,
    LeadershipRoleProfile,
    LeadershipProfileRegional,
    ServiceOrder,
)
from app.services.regional import is_valid_regional, normalize_regional


LEADERSHIP_ROLE_TYPES = {"supervisor", "regional_manager", "portfolio_manager"}
DEFAULT_MULTIPLIERS = {
    "supervisor": 1.5,
    "regional_manager": 2.0,
    "portfolio_manager": 3.0,
}
DEFAULT_ROLE_PROFILES = (
    ("Supervisor", "supervisor"),
    ("Gerente da unidade", "regional_manager"),
    ("Gerente de pasta", "portfolio_manager"),
)


def normalize_role_type(value: str | None) -> str:
    role_type = (value or "").strip()
    if role_type not in LEADERSHIP_ROLE_TYPES:
        raise HTTPException(status_code=422, detail="Tipo de lideranca invalido.")
    return role_type


def default_multiplier_for_role(role_type: str) -> float:
    return float(DEFAULT_MULTIPLIERS.get(role_type, 1.0))


def serialize_role_profile(profile: LeadershipRoleProfile) -> dict:
    return {
        "id": profile.id,
        "name": profile.name,
        "scope_type": profile.scope_type,
        "default_multiplier": float(profile.default_multiplier),
        "active": profile.active,
        "linked_leaders_count": len(profile.leaders),
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


def ensure_default_role_profiles(db: Session) -> list[LeadershipRoleProfile]:
    existing = list(db.scalars(select(LeadershipRoleProfile).order_by(LeadershipRoleProfile.id.asc())))
    by_name = {profile.name: profile for profile in existing}
    created = False
    for name, scope_type in DEFAULT_ROLE_PROFILES:
        if name in by_name:
            continue
        profile = LeadershipRoleProfile(
            name=name,
            scope_type=scope_type,
            default_multiplier=default_multiplier_for_role(scope_type),
            active=True,
        )
        db.add(profile)
        existing.append(profile)
        created = True
    if created:
        db.flush()
    return existing


def effective_role_profile(profile: LeadershipProfile, role_profiles: list[LeadershipRoleProfile] | None = None) -> LeadershipRoleProfile | None:
    if profile.role_profile is not None:
        return profile.role_profile
    if role_profiles is None:
        return None
    by_scope = {item.scope_type: item for item in role_profiles}
    return by_scope.get(profile.role_type)


def effective_role_type(profile: LeadershipProfile) -> str:
    return normalize_role_type(profile.role_profile.scope_type if profile.role_profile else profile.role_type)


def effective_multiplier(profile: LeadershipProfile) -> float:
    if getattr(profile, "use_custom_multiplier", False) and profile.custom_multiplier is not None:
        return float(profile.custom_multiplier)
    if profile.role_profile is not None:
        return float(profile.role_profile.default_multiplier)
    return float(getattr(profile, "multiplier", default_multiplier_for_role(profile.role_type)))


def normalize_regionals(values: Iterable[str]) -> list[str]:
    regionals: list[str] = []
    seen: set[str] = set()
    for value in values:
        regional = normalize_regional(value)
        if not regional or not is_valid_regional(regional):
            raise HTTPException(status_code=422, detail=f"Regional invalida: {value}")
        if regional not in seen:
            seen.add(regional)
            regionals.append(regional)
    return regionals


def serialize_profile(profile: LeadershipProfile) -> dict:
    role_profile = profile.role_profile
    return {
        "id": profile.id,
        "name": profile.name,
        "role_type": effective_role_type(profile),
        "multiplier": effective_multiplier(profile),
        "role_profile_id": role_profile.id if role_profile else None,
        "role_profile_name": role_profile.name if role_profile else None,
        "use_custom_multiplier": bool(getattr(profile, "use_custom_multiplier", False)),
        "custom_multiplier": float(profile.custom_multiplier) if profile.custom_multiplier is not None else None,
        "active": profile.active,
        "collaborator_id": profile.collaborator_id,
        "regional_names": sorted([item.regional_name for item in profile.regionals]),
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


def active_profiles(db: Session) -> list[LeadershipProfile]:
    return list(
        db.scalars(
            select(LeadershipProfile)
            .options(selectinload(LeadershipProfile.regionals), selectinload(LeadershipProfile.role_profile))
            .where(LeadershipProfile.active.is_(True))
            .order_by(LeadershipProfile.role_type.asc(), LeadershipProfile.name.asc())
        )
    )


def validate_no_scope_overlap(
    db: Session,
    role_type: str,
    regionals: list[str],
    profile_id: int | None = None,
) -> None:
    if not regionals:
        return
    stmt = (
        select(LeadershipProfile)
        .join(LeadershipProfileRegional)
        .options(selectinload(LeadershipProfile.regionals), selectinload(LeadershipProfile.role_profile))
        .where(LeadershipProfile.active.is_(True))
        .where(LeadershipProfile.role_type == role_type)
        .where(LeadershipProfileRegional.regional_name.in_(regionals))
    )
    if profile_id is not None:
        stmt = stmt.where(LeadershipProfile.id != profile_id)
    existing = list(db.scalars(stmt).unique())
    if existing:
        conflicts = []
        for profile in existing:
            overlap = sorted({item.regional_name for item in profile.regionals if item.regional_name in regionals})
            if overlap:
                conflicts.append(f"{', '.join(overlap)} ja esta vinculada a {profile.name}")
        if conflicts:
            raise HTTPException(status_code=409, detail="; ".join(conflicts))


def replace_profile_regionals(db: Session, profile: LeadershipProfile, regionals: list[str]) -> None:
    if profile.id is not None:
        db.execute(delete(LeadershipProfileRegional).where(LeadershipProfileRegional.leadership_profile_id == profile.id))
        db.flush()
    profile.regionals = []
    for regional in regionals:
        profile.regionals.append(LeadershipProfileRegional(regional_name=regional))


def leadership_bonus_from_ranking(db: Session, calculation_run_id: int, ranking: list[dict], point_value: float) -> dict:
    profiles = active_profiles(db)
    registered_scores: list[dict] = []
    pending: list[dict] = []
    for score in ranking:
        regional = normalize_regional(str(score.get("regional") or ""))
        estimated = float(score.get("estimated_payment") or 0)
        final_points = float(score.get("final_points") or 0)
        is_registered = bool(score.get("is_registered", True))
        if is_registered:
            registered_scores.append(
                {
                    "collaborator_id": int(score.get("collaborator_id") or 0),
                    "regional": regional,
                    "final_points": final_points,
                }
            )
        else:
            pending.append(
                {
                    "collaborator_id": int(score.get("collaborator_id") or 0),
                    "name": str(score.get("collaborator_name") or ""),
                    "regional": regional,
                    "suggested_regional": regional,
                    "service_orders_count": int(score.get("service_orders_count") or 0),
                    "estimated_payment": round(estimated, 2),
                }
            )

    results = []
    all_scope_regionals = sorted({item["regional"] for item in registered_scores if item["regional"]})
    for profile in profiles:
        configured_regionals = sorted({item.regional_name for item in profile.regionals})
        role_type = effective_role_type(profile)
        if role_type == "portfolio_manager":
            scoped_scores = registered_scores
            scope_regionals = all_scope_regionals
        else:
            scoped_scores = [item for item in registered_scores if item["regional"] in configured_regionals]
            scope_regionals = configured_regionals

        scoped_collaborators = len(scoped_scores)
        average_final_points = round(
            sum(float(item["final_points"]) for item in scoped_scores) / scoped_collaborators,
            2,
        ) if scoped_collaborators else 0.0
        base_amount = round(average_final_points * float(point_value), 2)
        multiplier = effective_multiplier(profile)
        role_profile = profile.role_profile
        bonus_amount = round(base_amount * multiplier, 2)
        results.append(
            {
                "id": None,
                "calculation_run_id": calculation_run_id,
                "leadership_profile_id": profile.id,
                "name": profile.name,
                "role_type": role_type,
                "role_profile_id": role_profile.id if role_profile else None,
                "role_profile_name": role_profile.name if role_profile else None,
                "multiplier": multiplier,
                "uses_custom_multiplier": bool(getattr(profile, "use_custom_multiplier", False)),
                "average_final_points": average_final_points,
                "scoped_collaborators": scoped_collaborators,
                "point_value": float(point_value),
                "base_amount": base_amount,
                "bonus_amount": bonus_amount,
                "regionals": scope_regionals,
            }
        )

    return {
        "calculation_run_id": calculation_run_id,
        "results": results,
        "pending_collaborators": pending,
        "total_base_amount": round(sum(item["base_amount"] for item in results), 2),
        "total_bonus_amount": round(sum(item["bonus_amount"] for item in results), 2),
    }


def calculate_and_store_leadership_bonus(db: Session, run: CalculationRun) -> dict:
    db.execute(delete(LeadershipBonusResult).where(LeadershipBonusResult.calculation_run_id == run.id))
    scores = list(run.scores)
    ranking = [
        {
            "collaborator_id": score.collaborator_id,
            "collaborator_name": score.collaborator.name if score.collaborator else "",
            "regional": score.collaborator.regional if score.collaborator else "",
            "is_registered": bool(score.collaborator and score.collaborator.is_registered),
            "service_orders_count": score.service_orders_count,
            "final_points": score.final_points,
            "estimated_payment": score.estimated_payment,
        }
        for score in scores
    ]
    summary = leadership_bonus_from_ranking(db, run.id, ranking, run.point_value)
    result_rows = []
    for item in summary["results"]:
        result = LeadershipBonusResult(
            calculation_run_id=run.id,
            leadership_profile_id=int(item["leadership_profile_id"]),
            role_type=str(item["role_type"]),
            multiplier=float(item["multiplier"]),
            average_final_points=float(item["average_final_points"]),
            scoped_collaborators=int(item["scoped_collaborators"]),
            point_value=float(item["point_value"]),
            base_amount=float(item["base_amount"]),
            bonus_amount=float(item["bonus_amount"]),
            regionals_snapshot=list(item["regionals"]),
        )
        db.add(result)
        result_rows.append(result)
    db.flush()
    for item, result in zip(summary["results"], result_rows):
        item["id"] = result.id
    db.commit()
    return summary


def pending_unregistered_for_run(db: Session, run: CalculationRun) -> list[dict]:
    scores_by_collaborator = {score.collaborator_id: score for score in run.scores}
    collaborators = [
        score.collaborator
        for score in run.scores
        if score.collaborator and not score.collaborator.is_registered
    ]
    if not collaborators:
        return []
    orders = list(db.scalars(select(ServiceOrder).where(ServiceOrder.collaborator_id.in_([item.id for item in collaborators]))))
    regionals_by_collaborator: dict[int, Counter] = {}
    for order in orders:
        regionals_by_collaborator.setdefault(order.collaborator_id, Counter())[normalize_regional(order.regional)] += 1
    pending = []
    for collaborator in collaborators:
        score = scores_by_collaborator.get(collaborator.id)
        suggested = regionals_by_collaborator.get(collaborator.id, Counter()).most_common(1)
        pending.append(
            {
                "collaborator_id": collaborator.id,
                "name": collaborator.name,
                "regional": normalize_regional(collaborator.regional),
                "suggested_regional": suggested[0][0] if suggested else normalize_regional(collaborator.regional),
                "service_orders_count": int(score.service_orders_count if score else 0),
                "estimated_payment": round(float(score.estimated_payment if score else 0), 2),
            }
        )
    return pending
