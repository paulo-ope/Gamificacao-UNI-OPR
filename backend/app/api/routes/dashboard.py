from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.performance import performance_step
from app.core.security import require_permission
from app.db.session import get_db
from app.models import CalculationRun, CollaboratorScore, LeadershipBonusResult, LeadershipProfile, ServiceOrder
from app.schemas import DashboardBootstrapOut, DashboardFilteredBreakdownOut, DashboardSummary
from app.services.calculation import (
    _apply_cpk_adjustment,
    _period_orders,
    calculate_penalty_distribution,
    collaborator_financial_context,
    get_point_value,
    latest_run,
    serialize_run,
)
from app.services.calculation_closure import pick_run_by_status_priority
from app.services.leadership_bonus import (
    apply_leadership_bonus_to_cost_by_regional,
    leadership_bonus_from_ranking,
    pending_unregistered_for_run,
)
from app.services.regional import same_regional_grouped as same_regional
from app.services.scoring_matrix import real_service_orders
from app.services.scoring_detail import (
    calculate_regional_health,
    calculate_regional_health_from_details,
    counts_for_regional_health,
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
    return pick_run_by_status_priority(db, stmt)


def _result_summary_cache(run: CalculationRun | None) -> dict:
    if not run or not isinstance(run.result_summary, dict):
        return {}
    return run.result_summary


# Tolerancia de 1 centavo: a soma de N valores de 2 casas pode oscilar no ultimo centavo por
# arredondamento, e isso nao e motivo pra descartar o cache inteiro.
BREAKDOWN_CONSISTENCY_TOLERANCE = 0.01


def _regional_breakdown_is_consistent(summary_cache: dict, cards: dict, leadership_bonus: dict) -> bool:
    """A soma de "Valor a ser pago por regional" tem que ser o valor dos tecnicos mais o bonus de
    lideranca. Quando nao e, o detalhamento gravado esta velho ou inflado e nao pode ser servido.

    Existe por causa de dois achados reais da auditoria 2026-08-26: o detalhamento ficava
    congelado com a previa do rascunho depois do pagamento (C1) e o bonus de lideranca era somado
    de novo a cada recalculo (C2) - o fechamento pago #1601 tem R$ 38.264,02 nesta tabela contra
    R$ 24.282,77 reais. Devolver `False` faz a rota recalcular na hora, curando a leitura sem
    depender de reprocessar o fechamento (nao da pra recalcular um periodo ja pago).
    """
    cached = summary_cache.get("cost_by_regional") or []
    if not cached:
        return False
    cached_total = round(sum(float(item.get("estimated_payment") or 0) for item in cached), 2)
    expected = round(
        float(cards.get("estimated_payment") or 0) + float(leadership_bonus.get("total_bonus_amount") or 0), 2
    )
    return abs(cached_total - expected) <= BREAKDOWN_CONSISTENCY_TOLERANCE


def _collaborator_financial_context(db: Session, run: CalculationRun) -> dict[int, dict[str, float | int | str]]:
    """Delega pra fonte unica em `services/calculation.py` - o valor a pagar de cada colaborador
    vem da linha `collaborator_scores`, nunca do cache JSON (achado C1 da auditoria 2026-08-26).
    Sem isso, "por regional/grupo" era proporcionalizado sobre um total diferente do que a pessoa
    de fato recebe."""
    return collaborator_financial_context(db, run)


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
    # `cards` sai do resumo ja reconciliado com as linhas (serialize_run), nao do JSON cru - o
    # card "Total a pagar" e a tabela de colaboradores da mesma tela precisam bater (achado C1).
    reconciled_cards = (serialized_run or {}).get("result_summary", {}).get("cards", {}) or {}
    leadership_bonus = _stored_leadership_bonus_summary(db, run)

    has_cached_breakdowns = bool(summary_cache.get("cost_by_regional"))
    if (
        summary_cache.get("dashboard_cache_version") == 3
        and has_cached_breakdowns
        and _regional_breakdown_is_consistent(summary_cache, reconciled_cards, leadership_bonus)
    ):
        return {
            "run": serialized_run,
            "cards": reconciled_cards,
            "ranking": serialized_run["scores"] if serialized_run else [],
            "leadership_bonus": leadership_bonus,
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
    health_by_regional = calculate_regional_health(db, [order for order in orders if counts_for_regional_health(order)])
    health_by_regional = calculate_regional_health_from_details(db, details, health_by_regional)
    health_by_regional = _apply_cpk_adjustment(db, health_by_regional, run.reference_month, run.reference_year)
    breakdowns = financial_breakdowns(
        db,
        orders,
        point_value,
        details=details,
        health_by_regional=health_by_regional,
        collaborator_context=_collaborator_financial_context(db, run),
    )
    breakdowns["cost_by_regional"] = apply_leadership_bonus_to_cost_by_regional(
        breakdowns["cost_by_regional"], leadership_bonus
    )

    return {
        "run": serialized_run,
        "cards": reconciled_cards,
        "ranking": serialized_run["scores"] if serialized_run else [],
        "leadership_bonus": leadership_bonus,
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
        health_by_regional = calculate_regional_health(db, [order for order in orders if counts_for_regional_health(order)])
        health_by_regional = calculate_regional_health_from_details(db, details, health_by_regional)
        health_by_regional = _apply_cpk_adjustment(db, health_by_regional, run.reference_month, run.reference_year)
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
        health_by_regional = calculate_regional_health(db, [order for order in orders if counts_for_regional_health(order)])
        health_by_regional = calculate_regional_health_from_details(db, details, health_by_regional)
        health_by_regional = _apply_cpk_adjustment(db, health_by_regional, run.reference_month, run.reference_year)
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
