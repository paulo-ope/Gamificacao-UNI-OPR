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
from app.services.regional import is_valid_regional, normalize_regional_grouped as normalize_regional


LEADERSHIP_ROLE_TYPES = {"supervisor", "regional_manager", "portfolio_manager"}
LEADERSHIP_AVERAGE_SOURCES = {"collaborators", "collaborators_and_leaders"}
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
        raise HTTPException(status_code=422, detail="Tipo de liderança inválido.")
    return role_type


def normalize_average_source(value: str | None) -> str:
    average_source = (value or "collaborators").strip()
    if average_source not in LEADERSHIP_AVERAGE_SOURCES:
        raise HTTPException(status_code=422, detail="Origem da média da liderança inválida.")
    return average_source


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
            raise HTTPException(status_code=422, detail=f"Regional inválida: {value}")
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
        "average_source": normalize_average_source(getattr(profile, "average_source", None)),
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


def validate_scope_regionals_required(role_type: str, regionals: list[str]) -> None:
    """Supervisor e gerente da unidade calculam o bonus como media dos colaboradores das
    filiais vinculadas (leadership_bonus_from_ranking acima) - sem nenhuma filial, o escopo
    fica sempre vazio e o bonus sai R$ 0 silenciosamente. Gerente de pasta ignora as filiais
    (usa todos os colaboradores registrados), entao nao precisa dessa exigencia."""
    if role_type != "portfolio_manager" and not regionals:
        raise HTTPException(
            status_code=422,
            detail="Selecione ao menos uma filial para supervisor ou gerente da unidade - sem filial, o bônus fica sempre R$ 0.",
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
                conflicts.append(f"{', '.join(overlap)} já está vinculada a {profile.name}")
        if conflicts:
            raise HTTPException(status_code=409, detail="; ".join(conflicts))


def replace_profile_regionals(db: Session, profile: LeadershipProfile, regionals: list[str]) -> None:
    if profile.id is not None:
        db.execute(delete(LeadershipProfileRegional).where(LeadershipProfileRegional.leadership_profile_id == profile.id))
        db.flush()
    profile.regionals = []
    for regional in regionals:
        profile.regionals.append(LeadershipProfileRegional(regional_name=regional))


def _audit_score_from_collaborator(item: dict) -> dict:
    return {
        "collaborator_id": int(item["collaborator_id"]),
        "collaborator_name": str(item["collaborator_name"]),
        "role": str(item["role"]),
        "regional": str(item["regional"]),
        "source_type": str(item.get("source_type") or "collaborator"),
        "service_orders_count": int(item["service_orders_count"]),
        "health_multiplier": float(item["health_multiplier"]),
        "final_points": float(item["final_points"]),
        "estimated_payment": float(item["estimated_payment"]),
    }


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
                    "collaborator_name": str(score.get("collaborator_name") or ""),
                    "role": str(score.get("role") or ""),
                    "regional": regional,
                    "service_orders_count": int(score.get("service_orders_count") or 0),
                    "health_multiplier": float(score.get("health_multiplier") or 0),
                    "final_points": final_points,
                    "estimated_payment": round(estimated, 2),
                    "source_type": "collaborator",
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
    base_scopes: dict[int, dict] = {}
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
        total_final_points = round(sum(float(item["final_points"]) for item in scoped_scores), 2)
        average_final_points = round(
            total_final_points / scoped_collaborators,
            2,
        ) if scoped_collaborators else 0.0
        base_scopes[int(profile.id)] = {
            "profile": profile,
            "role_type": role_type,
            "scope_regionals": scope_regionals,
            "scoped_scores": scoped_scores,
            "scoped_collaborators": scoped_collaborators,
            "total_final_points": total_final_points,
            "average_final_points": average_final_points,
        }

    for profile in profiles:
        base_scope = base_scopes[int(profile.id)]
        role_type = str(base_scope["role_type"])
        scope_regionals = list(base_scope["scope_regionals"])
        scoped_scores = list(base_scope["scoped_scores"])
        average_source = normalize_average_source(getattr(profile, "average_source", None))

        if average_source == "collaborators_and_leaders":
            scope_regionals_set = set(scope_regionals)
            leadership_scores = []
            for other_profile in profiles:
                if other_profile.id == profile.id:
                    continue
                other_scope = base_scopes[int(other_profile.id)]
                other_regionals = set(other_scope["scope_regionals"])
                if role_type != "portfolio_manager" and scope_regionals_set and other_regionals.isdisjoint(scope_regionals_set):
                    continue
                leadership_scores.append(
                    {
                        "collaborator_id": int(other_profile.collaborator_id or 0),
                        "collaborator_name": str(other_profile.name),
                        "role": str(other_profile.role_profile.name if other_profile.role_profile else effective_role_type(other_profile)),
                        "regional": ", ".join(other_scope["scope_regionals"]) or "Geral",
                        "source_type": "leader",
                        "service_orders_count": int(other_scope["scoped_collaborators"]),
                        "health_multiplier": 1.0,
                        "final_points": float(other_scope["average_final_points"]),
                        "estimated_payment": round(float(other_scope["average_final_points"]) * float(point_value), 2),
                    }
                )
            scoped_scores = scoped_scores + leadership_scores

        scoped_collaborators = len(scoped_scores)
        total_final_points = round(sum(float(item["final_points"]) for item in scoped_scores), 2)
        average_final_points = round(total_final_points / scoped_collaborators, 2) if scoped_collaborators else 0.0
        base_amount = round(average_final_points * float(point_value), 2)
        multiplier = effective_multiplier(profile)
        role_profile = profile.role_profile
        bonus_amount = round(base_amount * multiplier, 2)
        audit_collaborators = sorted(
            [
                _audit_score_from_collaborator(item) for item in scoped_scores
            ],
            key=lambda item: (-float(item["final_points"]), -float(item["estimated_payment"]), str(item["collaborator_name"])),
        )
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
                "average_source": average_source,
                "average_final_points": average_final_points,
                "scoped_collaborators": scoped_collaborators,
                "point_value": float(point_value),
                "base_amount": base_amount,
                "bonus_amount": bonus_amount,
                "regionals": scope_regionals,
                "audit": {
                    "scoped_collaborators": scoped_collaborators,
                    "total_final_points": total_final_points,
                    "average_final_points": average_final_points,
                    "point_value": float(point_value),
                    "base_amount": base_amount,
                    "multiplier": multiplier,
                    "bonus_amount": bonus_amount,
                    "collaborators": audit_collaborators,
                },
            }
        )

    return {
        "calculation_run_id": calculation_run_id,
        "results": results,
        "pending_collaborators": pending,
        "total_base_amount": round(sum(item["base_amount"] for item in results), 2),
        "total_bonus_amount": round(sum(item["bonus_amount"] for item in results), 2),
    }


def _distribute_cents_exactly(total: float, count: int) -> list[float]:
    """Divide `total` (em reais) em `count` fatias que somam EXATAMENTE `round(total, 2)` - nunca
    perde nem sobra 1 centavo por arredondamento independente de cada fatia (ex.: R$10,00 / 3 =
    R$3,33+R$3,33+R$3,33 = R$9,99 se cada fatia fosse arredondada isoladamente; aqui vira
    R$3,34+R$3,33+R$3,33 = R$10,00). Metodo do maior resto: distribui os centavos restantes,
    um a um, para as primeiras fatias."""
    total_cents = round(total * 100)
    base_cents = total_cents // count
    remainder = total_cents - base_cents * count
    shares_cents = [base_cents + (1 if index < remainder else 0) for index in range(count)]
    return [cents / 100 for cents in shares_cents]


def apply_leadership_bonus_to_cost_by_regional(
    cost_by_regional: list[dict[str, float | int | str]],
    leadership_summary: dict,
) -> list[dict[str, float | int | str]]:
    """Soma o bonus de cada lider na(s) regional(is) vinculada(s) ao perfil dele, pra
    "Valor a ser pago por regional" bater com o Total a pagar (que ja soma tecnicos + lideranca).
    Quando um perfil cobre mais de uma filial, DIVIDE o bonus igualmente entre elas (decisao do
    usuario, depois de confirmar que somar o valor cheio em cada uma inflava a soma total sempre
    que houvesse lider multi-regional) - assim a soma de "por regional" sempre bate com o Total a
    pagar, sem excecao. Gerente de pasta cobre todas as regionais ao mesmo tempo por definicao
    (nao tem uma regional propria) - vira uma linha separada "Liderança sem regional" em vez de
    silenciosamente sumir do total quando comparado com o card do topo."""
    by_regional: dict[str, dict[str, float | int | str]] = {
        str(item["regional"]): dict(item) for item in cost_by_regional
    }
    unassigned_total = 0.0
    for result in leadership_summary.get("results", []):
        bonus = float(result.get("bonus_amount") or 0)
        if not bonus:
            continue
        if result.get("role_type") == "portfolio_manager":
            unassigned_total += bonus
            continue
        regionals = result.get("regionals") or []
        if not regionals:
            unassigned_total += bonus
            continue
        shares = _distribute_cents_exactly(bonus, len(regionals))
        for regional, share in zip(regionals, shares):
            regional_key = str(regional)
            item = by_regional.setdefault(
                regional_key, {"regional": regional_key, "orders": 0, "estimated_payment": 0.0}
            )
            item["estimated_payment"] = round(float(item.get("estimated_payment", 0.0)) + share, 2)

    merged = list(by_regional.values())
    if unassigned_total:
        merged.append({"regional": "Liderança sem regional", "orders": 0, "estimated_payment": round(unassigned_total, 2)})
    return sorted(merged, key=lambda item: float(item["estimated_payment"]), reverse=True)


def calculate_and_store_leadership_bonus(db: Session, run: CalculationRun) -> dict:
    db.execute(delete(LeadershipBonusResult).where(LeadershipBonusResult.calculation_run_id == run.id))
    scores = list(run.scores)
    ranking = [
        {
            "collaborator_id": score.collaborator_id,
            "collaborator_name": score.collaborator.name if score.collaborator else "",
            "role": score.collaborator.role if score.collaborator else "",
            "regional": score.collaborator.regional if score.collaborator else "",
            "is_registered": bool(score.collaborator and score.collaborator.is_registered),
            "service_orders_count": score.service_orders_count,
            "health_multiplier": score.health_multiplier,
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

    # Atualiza o cost_by_regional ja cacheado em result_summary com o bonus de lideranca - sem
    # isso, "Valor a ser pago por regional" nunca bate com o Total a pagar (que ja soma tecnicos +
    # lideranca). Reatribui o dict inteiro (nao muta em lugar) porque colunas JSON do SQLAlchemy so
    # detectam mudanca por reatribuicao, nao por mutacao profunda de um dict ja carregado.
    if isinstance(run.result_summary, dict) and run.result_summary.get("cost_by_regional"):
        updated_result_summary = dict(run.result_summary)
        updated_result_summary["cost_by_regional"] = apply_leadership_bonus_to_cost_by_regional(
            updated_result_summary["cost_by_regional"], summary
        )
        run.result_summary = updated_result_summary

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
