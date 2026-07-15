from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, desc, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.performance import performance_step
from app.core.security import require_permission
from app.db.session import get_db
from app.models import CalculationRun, CollaboratorScore, LeadershipBonusResult, LeadershipProfile, ServiceOrder
from app.schemas import DashboardBootstrapOut, DashboardFilteredBreakdownOut, DashboardSummary
from app.services.calculation import (
    _period_orders,
    _run_extra_summaries,
    calculate_penalty_distribution,
    cached_score_summaries,
    get_point_value,
    latest_run,
    serialize_run,
)
from app.services.leadership_bonus import leadership_bonus_from_ranking, pending_unregistered_for_run
from app.services.regional import same_regional
from app.services.scoring_matrix import real_service_orders
from app.services.scoring_detail import (
    calculate_regional_health,
    calculate_regional_health_from_details,
    completed,
    explain_orders,
    financial_breakdowns,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
FILTERED_BREAKDOWNS_CACHE: dict[tuple[int, tuple[str, ...]], dict] = {}


def _empty_dashboard_summary(point_value: float) -> dict:
    return {
        "run": None,
        "cards": {},
        "ranking": [],
        "leadership_bonus": {
            "calculation_run_id": 0,
            "results": [],
            "pending_collaborators": [],
            "total_base_amount": 0,
            "total_bonus_amount": 0,
        },
        "penalty_distribution": [],
        "health_by_regional": [],
        "point_value": point_value,
        "cost_by_regional": [],
        "cost_by_group": [],
        "cost_by_subject": [],
        "cost_by_collaborator": [],
        "top_penalized_subjects": [],
        "top_scoring_subjects": [],
        "top_unmapped_subjects": [],
    }


def _load_saved_run(
    db: Session,
    reference_month: int | None,
    reference_year: int | None,
    regional: str | None,
) -> CalculationRun | None:
    if reference_month is None and reference_year is None and regional is None:
        return latest_run(db)

    stmt = (
        select(CalculationRun)
        .options(selectinload(CalculationRun.scores).selectinload(CollaboratorScore.collaborator))
        .where(CalculationRun.reference_month == reference_month)
        .where(CalculationRun.reference_year == reference_year)
    )
    if regional is None:
        stmt = stmt.where(CalculationRun.regional.is_(None))
    else:
        stmt = stmt.where(CalculationRun.regional == regional)
    return db.scalar(stmt.order_by(desc(CalculationRun.created_at), desc(CalculationRun.id)).limit(1))


def _result_summary_cache(run: CalculationRun | None) -> dict:
    if not run or not isinstance(run.result_summary, dict):
        return {}
    return run.result_summary


def _collaborator_financial_context(db: Session, run: CalculationRun) -> dict[int, dict[str, float | int | str]]:
    summaries = cached_score_summaries(run)
    if not summaries:
        summaries = _run_extra_summaries(db, run)
    context: dict[int, dict[str, float | int | str]] = {}
    for collaborator_id, summary in summaries.items():
        if int(summary.get("total_service_orders", 0) or 0) <= 0:
            continue
        context[int(collaborator_id)] = {
            "regional": summary.get("regional"),
            "health_multiplier": summary.get("health_multiplier", 0),
        }
    return context


def _period_bounds(reference_month: int, reference_year: int) -> tuple[datetime, datetime]:
    period_start = datetime(reference_year, reference_month, 1)
    if reference_month == 12:
        return period_start, datetime(reference_year + 1, 1, 1)
    return period_start, datetime(reference_year, reference_month + 1, 1)


def _matching_regional_values(db: Session, selected_regionals: list[str]) -> list[str]:
    raw_values = [value for value in db.scalars(select(ServiceOrder.regional).distinct()) if value]
    return [
        value
        for value in raw_values
        if any(same_regional(value, selected_regional) for selected_regional in selected_regionals)
    ]


def _period_orders_for_selected_regionals(db: Session, run: CalculationRun, selected_regionals: list[str]):
    effective_regionals = [
        selected_regional
        for selected_regional in selected_regionals
        if not run.regional or same_regional(run.regional, selected_regional)
    ]
    if not effective_regionals:
        return []

    regional_values = _matching_regional_values(db, [run.regional] if run.regional else effective_regionals)
    if not regional_values:
        return []

    period_start, period_end = _period_bounds(run.reference_month, run.reference_year)
    stmt = (
        select(ServiceOrder)
        .options(selectinload(ServiceOrder.collaborator))
        .where(
            or_(
                and_(ServiceOrder.closed_at >= period_start, ServiceOrder.closed_at < period_end),
                and_(
                    ServiceOrder.closed_at.is_(None),
                    ServiceOrder.opened_at >= period_start,
                    ServiceOrder.opened_at < period_end,
                ),
            )
        )
        .where(ServiceOrder.regional.in_(regional_values))
    )
    orders = real_service_orders(list(db.scalars(stmt)))
    return [
        order
        for order in orders
        if any(same_regional(order.regional, selected_regional) for selected_regional in effective_regionals)
    ]


def _stored_leadership_bonus_summary(db: Session, run: CalculationRun) -> dict:
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
        for score in run.scores
    ]
    calculated_summary = leadership_bonus_from_ranking(db, run.id, ranking, run.point_value)
    calculated_results_by_profile = {
        int(item["leadership_profile_id"]): item for item in calculated_summary.get("results", [])
    }

    results = list(
        db.scalars(
            select(LeadershipBonusResult)
            .options(selectinload(LeadershipBonusResult.profile).selectinload(LeadershipProfile.role_profile))
            .where(LeadershipBonusResult.calculation_run_id == run.id)
            .order_by(LeadershipBonusResult.bonus_amount.desc(), LeadershipBonusResult.id.asc())
        )
    )
    serialized_results = [
        {
            "id": item.id,
            "calculation_run_id": item.calculation_run_id,
            "leadership_profile_id": item.leadership_profile_id,
            "name": item.profile.name if item.profile else "",
            "role_type": item.role_type,
            "role_profile_id": item.profile.role_profile_id if item.profile else None,
            "role_profile_name": item.profile.role_profile.name if item.profile and item.profile.role_profile else None,
            "multiplier": float(item.multiplier),
            "uses_custom_multiplier": bool(item.profile.use_custom_multiplier) if item.profile else False,
            "average_source": item.profile.average_source if item.profile else "collaborators",
            "average_final_points": float(item.average_final_points),
            "scoped_collaborators": int(item.scoped_collaborators),
            "point_value": float(item.point_value),
            "base_amount": float(item.base_amount),
            "bonus_amount": float(item.bonus_amount),
            "regionals": list(item.regionals_snapshot),
            "audit": calculated_results_by_profile.get(int(item.leadership_profile_id), {}).get("audit"),
        }
        for item in results
    ]
    return {
        "calculation_run_id": run.id,
        "results": serialized_results,
        "pending_collaborators": pending_unregistered_for_run(db, run),
        "total_base_amount": round(sum(item["base_amount"] for item in serialized_results), 2),
        "total_bonus_amount": round(sum(item["bonus_amount"] for item in serialized_results), 2),
    }


@router.get("/bootstrap", response_model=DashboardBootstrapOut)
def dashboard_bootstrap(
    db: Session = Depends(get_db),
    user=Depends(require_permission("dashboard:read")),
):
    run = latest_run(db)
    point_value = get_point_value(db)
    if not run:
        return {
            "reference_month": None,
            "reference_year": None,
            "regional": None,
            "point_value": point_value,
            "has_calculation_run": False,
            "calculation_run_id": None,
        }
    return {
        "reference_month": run.reference_month,
        "reference_year": run.reference_year,
        "regional": run.regional,
        "point_value": point_value,
        "has_calculation_run": True,
        "calculation_run_id": run.id,
    }


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(
    reference_month: int | None = None,
    reference_year: int | None = None,
    regional: str | None = None,
    db: Session = Depends(get_db),
    user=Depends(require_permission("dashboard:read")),
):
    point_value = get_point_value(db)
    run = _load_saved_run(db, reference_month, reference_year, regional)
    if not run:
        return _empty_dashboard_summary(point_value)

    point_value = float(run.point_value)
    serialized_run = serialize_run(run, db)
    summary_cache = _result_summary_cache(run)

    has_cached_breakdowns = bool(summary_cache.get("cost_by_regional"))
    if summary_cache.get("dashboard_cache_version") == 3 and has_cached_breakdowns:
        return {
            "run": serialized_run,
            "cards": summary_cache.get("cards", {}),
            "ranking": serialized_run["scores"] if serialized_run else [],
            "leadership_bonus": _stored_leadership_bonus_summary(db, run),
            "penalty_distribution": summary_cache.get("penalty_distribution", []),
            "health_by_regional": summary_cache.get("health_by_regional", []),
            "point_value": point_value,
            "cost_by_regional": summary_cache.get("cost_by_regional", []),
            "cost_by_group": summary_cache.get("cost_by_group", []),
            "cost_by_subject": summary_cache.get("cost_by_subject", []),
            "cost_by_collaborator": summary_cache.get("cost_by_collaborator", []),
            "top_penalized_subjects": summary_cache.get("top_penalized_subjects", []),
            "top_scoring_subjects": summary_cache.get("top_scoring_subjects", []),
            "top_unmapped_subjects": summary_cache.get("top_unmapped_subjects", []),
        }

    orders = _period_orders(db, run.reference_month, run.reference_year, run.regional)
    details = explain_orders(db, orders, default_point_value=point_value)
    health_by_regional = calculate_regional_health(db, [order for order in orders if completed(order)])
    health_by_regional = calculate_regional_health_from_details(db, details, health_by_regional)
    breakdowns = financial_breakdowns(
        db,
        orders,
        point_value,
        details=details,
        health_by_regional=health_by_regional,
        collaborator_context=_collaborator_financial_context(db, run),
    )

    return {
        "run": serialized_run,
        "cards": summary_cache.get("cards", {}),
        "ranking": serialized_run["scores"] if serialized_run else [],
        "leadership_bonus": _stored_leadership_bonus_summary(db, run),
        "penalty_distribution": calculate_penalty_distribution(db, orders, details=details),
        "health_by_regional": list(health_by_regional.values()),
        "point_value": point_value,
        **breakdowns,
    }


@router.get("/filtered-breakdowns", response_model=DashboardFilteredBreakdownOut)
def dashboard_filtered_breakdowns(
    calculation_run_id: int,
    regional: list[str] = Query(default=[]),
    db: Session = Depends(get_db),
    user=Depends(require_permission("dashboard:read")),
):
    run = db.scalar(
        select(CalculationRun)
        .options(selectinload(CalculationRun.scores).selectinload(CollaboratorScore.collaborator))
        .where(CalculationRun.id == calculation_run_id)
        .limit(1)
    )
    if not run:
        raise HTTPException(status_code=404, detail="Apuração não encontrada.")

    selected_regionals = [item.strip() for item in regional if item and item.strip()]
    if not selected_regionals:
        summary_cache = _result_summary_cache(run)
        if summary_cache.get("cost_by_regional"):
            return {
                "calculation_run_id": run.id,
                "regionals": [],
                "penalty_distribution": summary_cache.get("penalty_distribution", []),
                "cost_by_regional": summary_cache.get("cost_by_regional", []),
                "cost_by_group": summary_cache.get("cost_by_group", []),
                "top_unmapped_subjects": summary_cache.get("top_unmapped_subjects", []),
            }

        with performance_step("dashboard.filtered-breakdowns", "load_all_orders"):
            orders = _period_orders(db, run.reference_month, run.reference_year, run.regional)
        if not orders:
            return {
                "calculation_run_id": run.id,
                "regionals": [],
                "penalty_distribution": [],
                "cost_by_regional": [],
                "cost_by_group": [],
                "top_unmapped_subjects": [],
            }

        point_value = float(run.point_value)
        details = explain_orders(db, orders, default_point_value=point_value)
        health_by_regional = calculate_regional_health(db, [order for order in orders if completed(order)])
        health_by_regional = calculate_regional_health_from_details(db, details, health_by_regional)
        breakdowns = financial_breakdowns(
            db,
            orders,
            point_value,
            details=details,
            health_by_regional=health_by_regional,
            collaborator_context=_collaborator_financial_context(db, run),
        )
        return {
            "calculation_run_id": run.id,
            "regionals": [],
            "penalty_distribution": calculate_penalty_distribution(db, orders, details=details),
            "cost_by_regional": breakdowns.get("cost_by_regional", []),
            "cost_by_group": breakdowns.get("cost_by_group", []),
            "top_unmapped_subjects": breakdowns.get("top_unmapped_subjects", []),
        }

    cache_key = (run.id, tuple(sorted(selected_regionals)))
    cached = FILTERED_BREAKDOWNS_CACHE.get(cache_key)
    if cached:
        return cached

    collaborator_context = _collaborator_financial_context(db, run)
    selected_regionals_normalized = {item.strip() for item in selected_regionals if item and item.strip()}
    collaborator_context = {
        collaborator_id: context
        for collaborator_id, context in collaborator_context.items()
        if str(context.get("regional") or "") in selected_regionals_normalized
    }
    if not collaborator_context:
        result = {
            "calculation_run_id": run.id,
            "regionals": selected_regionals,
            "penalty_distribution": [],
            "cost_by_regional": [],
            "cost_by_group": [],
            "top_unmapped_subjects": [],
        }
        FILTERED_BREAKDOWNS_CACHE[cache_key] = result
        return result

    with performance_step("dashboard.filtered-breakdowns", "load_filtered_orders"):
        orders = _period_orders(db, run.reference_month, run.reference_year, run.regional)
    if not orders:
        result = {
            "calculation_run_id": run.id,
            "regionals": selected_regionals,
            "penalty_distribution": [],
            "cost_by_regional": [],
            "cost_by_group": [],
            "top_unmapped_subjects": [],
        }
        FILTERED_BREAKDOWNS_CACHE[cache_key] = result
        return result

    point_value = float(run.point_value)
    with performance_step("dashboard.filtered-breakdowns", "explain_orders"):
        details = explain_orders(db, orders, default_point_value=point_value)
    with performance_step("dashboard.filtered-breakdowns", "regional_health"):
        health_by_regional = calculate_regional_health(db, [order for order in orders if completed(order)])
        health_by_regional = calculate_regional_health_from_details(db, details, health_by_regional)
    with performance_step("dashboard.filtered-breakdowns", "financial_breakdowns"):
        breakdowns = financial_breakdowns(
            db,
            orders,
            point_value,
            details=details,
            health_by_regional=health_by_regional,
            collaborator_context=collaborator_context,
        )

    with performance_step("dashboard.filtered-breakdowns", "penalty_distribution"):
        penalty_distribution = calculate_penalty_distribution(db, orders, details=details)

    result = {
        "calculation_run_id": run.id,
        "regionals": selected_regionals,
        "penalty_distribution": penalty_distribution,
        "cost_by_regional": breakdowns.get("cost_by_regional", []),
        "cost_by_group": breakdowns.get("cost_by_group", []),
        "top_unmapped_subjects": breakdowns.get("top_unmapped_subjects", []),
    }
    FILTERED_BREAKDOWNS_CACHE[cache_key] = result
    return result
