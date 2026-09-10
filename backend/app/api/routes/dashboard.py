import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.performance import performance_step
from app.core.security import require_permission
from app.db.session import get_db
from app.models import CalculationRun, CollaboratorScore, LeadershipBonusResult, LeadershipProfile, ServiceOrder
from app.schemas import (
    DashboardBootstrapOut,
    DashboardFilteredBreakdownOut,
    DashboardSummary,
    GamificationPreviewOut,
)
from app.services.calculation import (
    _apply_cpk_adjustment,
    _period_orders,
    calculate_penalty_distribution,
    collaborator_financial_context,
    gamification_preview,
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

logger = logging.getLogger("dashboard")

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
FILTERED_BREAKDOWNS_CACHE: dict[tuple[int, tuple[str, ...]], dict] = {}

# Detalhamento recalculado de fechamentos IMUTAVEIS (pago/cancelado), memorizado por id de run.
# Existe pra fechamentos cujo `result_summary` gravado esta velho ou inflado e por isso e
# recusado pela guarda de consistencia: sem isso a rota refazia `explain_orders` sobre o mes
# inteiro em CADA requisicao - 6,36s por leitura no #1601 (07/2026, 10.685 O.S.) contra 0,31s
# quando o cache e servido (medido em 2026-09-10). Um run pago ou cancelado e registro do que
# aconteceu e nao muda mais, entao guardar o resultado pelo tempo de vida do processo e seguro.
# Rascunho NAO entra aqui de proposito: `calculate_and_store_leadership_bonus` pode ser
# reexecutado sobre um rascunho existente e mudaria o bonus por baixo do valor memorizado.
IMMUTABLE_RUN_STATUSES = {"paid", "cancelled"}
IMMUTABLE_BREAKDOWNS_CACHE: dict[int, dict] = {}
# Teto simples pros dois dicionarios: eles vivem no processo e nada os invalidava. Com um run
# novo a cada ciclo do sincronizador do IXC, sem teto isso cresce pra sempre.
BREAKDOWNS_CACHE_MAX_ENTRIES = 64


def _remember(cache: dict, key, value: dict) -> dict:
    if len(cache) >= BREAKDOWNS_CACHE_MAX_ENTRIES:
        cache.pop(next(iter(cache)), None)
    cache[key] = value
    return value


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

# Um aviso por fechamento, nao um por requisicao: a inconsistencia e do dado gravado e nao muda
# entre leituras, e a tela chama esta rota a cada abertura.
WARNED_INCONSISTENT_RUNS: set[int] = set()


def _regional_breakdown_is_consistent(
    summary_cache: dict, cards: dict, leadership_bonus: dict, run_id: int | None = None
) -> bool:
    """A soma de "Valor a ser pago por regional" nunca pode ser MAIOR que o valor dos tecnicos
    mais o bonus de lideranca. Quando e, o detalhamento gravado esta velho ou inflado e nao pode
    ser servido - devolver `False` faz a rota recalcular, curando a leitura sem depender de
    reprocessar o fechamento (nao da pra recalcular um periodo ja pago).

    Existe por causa de dois achados reais da auditoria 2026-08-26: o detalhamento ficava
    congelado com a previa do rascunho depois do pagamento (C1) e o bonus de lideranca era somado
    de novo a cada recalculo (C2) - o fechamento pago #1601 tem R$ 38.264,02 nesta tabela contra
    R$ 24.282,77 reais.

    A comparacao era de IGUALDADE e estava errada nessa direcao (achado real, 2026-09-10): o
    detalhamento por regional pode legitimamente somar MENOS que o total, porque
    `financial_breakdowns` so consegue atribuir a uma regional o valor que tem base de pontos
    naquela regional. Quem tem multiplicador de saude 0 e recebe apenas credito de saldo entra no
    total a pagar sem entrar em nenhuma regional - em 08/2026 sao R$ 1.291,08 de 37 pessoas. Com a
    igualdade, a guarda reprovava o cache CORRETO de agosto pra sempre e a tela recalculava o mes
    inteiro em cada requisicao (4,44s contra 0,31s servindo o cache). O piso ficou aberto de
    proposito e a diferenca e logada, porque uma diferenca grande e sinal de problema de dado, nao
    motivo pra jogar o cache fora.
    """
    cached = summary_cache.get("cost_by_regional") or []
    if not cached:
        return False
    cached_total = round(sum(float(item.get("estimated_payment") or 0) for item in cached), 2)
    ceiling = round(
        float(cards.get("estimated_payment") or 0) + float(leadership_bonus.get("total_bonus_amount") or 0), 2
    )
    should_log = run_id is None or run_id not in WARNED_INCONSISTENT_RUNS
    if cached_total > ceiling + BREAKDOWN_CONSISTENCY_TOLERANCE:
        if should_log:
            logger.warning(
                "Fechamento #%s: detalhamento por regional inflado (R$ %.2f contra teto de R$ %.2f). "
                "Recalculando na leitura.",
                run_id,
                cached_total,
                ceiling,
            )
            if run_id is not None:
                WARNED_INCONSISTENT_RUNS.add(run_id)
        return False
    shortfall = round(ceiling - cached_total, 2)
    if shortfall > BREAKDOWN_CONSISTENCY_TOLERANCE and should_log:
        logger.info(
            "Fechamento #%s: R$ %.2f do valor a pagar nao tem regional atribuivel "
            "(colaborador com multiplicador de saude 0 recebendo somente credito de saldo).",
            run_id,
            shortfall,
        )
        if run_id is not None:
            WARNED_INCONSISTENT_RUNS.add(run_id)
    return True


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


@router.get("/gamification-preview", response_model=GamificationPreviewOut)
def dashboard_gamification_preview(
    db: Session = Depends(get_db),
    user=Depends(require_permission("dashboard:read")),
):
    """Leitura leve do valor corrente da gamificação, para a Visão Geral executiva.

    Separado de `/dashboard/summary` de propósito: aquele monta a tela inteira do módulo (ranking,
    breakdowns, distribuição de penalidade) e recalcula quando o cache está frio. Aqui a Visão Geral
    precisa de um número e do quando-foi-calculado, sem carregar o resto.
    """
    return gamification_preview(db, user)


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
        and _regional_breakdown_is_consistent(summary_cache, reconciled_cards, leadership_bonus, run_id=run.id)
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

    # Fechamento imutavel com cache recusado: recalcula UMA vez e memoriza. Sem isso, cada leitura
    # da tela refazia `explain_orders` sobre o mes inteiro (6,36s no #1601 contra 0,31s servindo
    # cache) - e um fechamento pago nao pode ter o `result_summary` reescrito pra curar o cache,
    # porque esse JSON e o registro do que foi pago.
    memoized = IMMUTABLE_BREAKDOWNS_CACHE.get(run.id) if run.status in IMMUTABLE_RUN_STATUSES else None
    if memoized is None:
        with performance_step("dashboard.summary", "recompute_breakdowns"):
            memoized = _recompute_summary_breakdowns(db, run, point_value, leadership_bonus)
        if run.status in IMMUTABLE_RUN_STATUSES:
            _remember(IMMUTABLE_BREAKDOWNS_CACHE, run.id, memoized)

    return {
        "run": serialized_run,
        "cards": reconciled_cards,
        "ranking": serialized_run["scores"] if serialized_run else [],
        "leadership_bonus": leadership_bonus,
        "point_value": point_value,
        **memoized,
    }


def _recompute_summary_breakdowns(
    db: Session, run: CalculationRun, point_value: float, leadership_bonus: dict
) -> dict:
    """Reconstroi na hora tudo que o `result_summary` gravado deveria ter servido.

    Devolve exatamente as chaves que a resposta de `/dashboard/summary` consome, pra poder ser
    memorizada inteira em `IMMUTABLE_BREAKDOWNS_CACHE`. `leadership_bonus` entra como parametro
    (nao e recalculado aqui) porque ele ja foi lido das linhas `leadership_bonus_results` pelo
    chamador - recalcular de novo seria trabalho repetido.
    """
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
        "penalty_distribution": calculate_penalty_distribution(db, orders, details=details),
        "health_by_regional": list(health_by_regional.values()),
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
        return _remember(FILTERED_BREAKDOWNS_CACHE, cache_key, result)

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
        return _remember(FILTERED_BREAKDOWNS_CACHE, cache_key, result)

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
    return _remember(FILTERED_BREAKDOWNS_CACHE, cache_key, result)
