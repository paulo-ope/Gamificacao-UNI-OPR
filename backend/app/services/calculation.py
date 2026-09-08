from __future__ import annotations

import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session, selectinload

from app.core.performance import performance_step
from app.models import (
    AppSetting,
    CalculationRun,
    Collaborator,
    CollaboratorScore,
    GamificationConfigVersion,
    ImportRun,
    LeadershipBonusResult,
    PointBalanceEntry,
    ServiceOrder,
)
import logging

from app.services import cpk_health, point_balance, scoring_detail
from app.services.cpk_client import CpkApiError
from app.services.calculation_closure import (
    build_rule_snapshot,
    current_reference_period,
    ensure_period_not_closed,
    now_porto_velho,
    now_utc,
    pick_run_by_status_priority,
    serialize_run_status,
)
from app.services.leadership_bonus import calculate_and_store_leadership_bonus
from app.services.regional import (
    effective_managed_regionals_grouped,
    normalize_regional_grouped as normalize_regional,
)

logger = logging.getLogger("calculation")


def normalize(value: str | None) -> str:
    if not value:
        return ""
    cleaned = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in cleaned if not unicodedata.combining(ch)).strip().lower()


def get_setting(db: Session, key: str, default: str) -> str:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == key))
    return setting.value if setting else default


def upsert_setting(db: Session, key: str, value: str, description: str | None = None) -> AppSetting:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == key))
    if setting:
        setting.value = value
        if description is not None:
            setting.description = description
        return setting

    setting = AppSetting(key=key, value=value, description=description)
    db.add(setting)
    return setting


def _safe_float(value: str | int | float | None, default: float) -> float:
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def get_point_value(db: Session) -> float:
    return _safe_float(get_setting(db, "point_value", "2.50"), 2.50)


def _period_orders(db: Session, reference_month: int, reference_year: int, regional: str | None) -> list[ServiceOrder]:
    return scoring_detail.period_orders(db, reference_month, reference_year, regional)


def _official_collaborator_regional(collaborator: Collaborator, fallback: str | None = None) -> str | None:
    if collaborator.is_registered and collaborator.regional:
        return normalize_regional(collaborator.regional)
    return normalize_regional(fallback) if fallback else fallback


def calculate_regional_health(db: Session, orders: list[ServiceOrder]) -> dict[str, dict[str, float | int | str]]:
    return scoring_detail.calculate_regional_health(db, orders)


def _apply_cpk_adjustment(
    db: Session, health_by_regional: dict[str, dict[str, float | int | str]], month: int, year: int
) -> dict[str, dict[str, float | int | str]]:
    """Soma o ajuste de CPK (+/-cpk_bonus_points, ver cpk_health.py) ao multiplicador de cada
    regional, do MESMO mes/ano sendo calculado. Se `cpk_sync_enabled` estiver ligado, busca o
    snapshot mais recente na API da frota antes de aplicar - se a API falhar (fora do ar, rede),
    o erro e apenas logado e o calculo segue com o ultimo snapshot ja salvo (nunca trava o
    calculo de folha por causa de um sistema externo)."""
    if get_setting(db, cpk_health.CPK_SYNC_ENABLED_SETTING, "false") == "true":
        try:
            cpk_health.sync_cpk_snapshot(db, year, month)
        except CpkApiError as exc:
            logger.warning("Falha ao sincronizar CPK automaticamente (ano=%s mes=%s): %s", year, month, exc)
    adjustments = cpk_health.get_cpk_adjustment_by_regional(db, year, month)
    statuses = cpk_health.get_cpk_status_by_regional(db, year, month)
    # Uma regional que nao bateu NENHUMA faixa ativa de saude cai no multiplicador minimo
    # configurado (health_below_minimum_multiplier, default 0) - achado real: o bonus de CPK
    # (na_meta) somava por cima desse piso e "ressuscitava" um pagamento que o SLA tinha zerado
    # de proposito. O bonus de CPK so faz sentido complementar um multiplicador que a regional
    # ja conquistou por SLA/saude - nao pode ele mesmo tirar a regional do piso.
    below_minimum_multiplier = scoring_detail.get_health_below_minimum_multiplier(db)
    for regional, entry in health_by_regional.items():
        entry["cpk_status"] = statuses.get(regional)
        adjustment = adjustments.get(regional, 0.0)
        current_multiplier = float(entry.get("multiplier", 0.0))
        if current_multiplier <= below_minimum_multiplier:
            entry["cpk_adjustment"] = 0.0
            continue
        entry["cpk_adjustment"] = adjustment
        if adjustment:
            entry["multiplier"] = max(0.0, current_multiplier + adjustment)
    return health_by_regional


def calculate_penalty_distribution(
    db: Session,
    orders: list[ServiceOrder],
    details: list[dict] | None = None,
) -> list[dict[str, float | str]]:
    return scoring_detail.calculate_penalty_distribution(db, orders, details=details)


def cached_score_summaries(run: CalculationRun | None) -> dict[int, dict[str, float | int | str]]:
    if not run or not isinstance(run.result_summary, dict):
        return {}

    raw_summaries = run.result_summary.get("score_summaries")
    if not isinstance(raw_summaries, dict):
        return {}

    parsed: dict[int, dict[str, float | int | str]] = {}
    for collaborator_id, summary in raw_summaries.items():
        if not isinstance(summary, dict):
            continue
        try:
            parsed[int(collaborator_id)] = summary
        except (TypeError, ValueError):
            continue
    return parsed


def calculate_scores(
    db: Session,
    reference_month: int | None = None,
    reference_year: int | None = None,
    regional: str | None = None,
    point_value: float | None = None,
    executed_by: int | None = None,
    allow_paid_revision: bool = False,
    execution_note: str | None = None,
) -> CalculationRun:
    if reference_month is None or reference_year is None:
        raise HTTPException(status_code=422, detail="Informe explicitamente o mês e o ano da apuração.")
    month = reference_month
    year = reference_year
    selected_regional = normalize_regional(regional) if regional else None
    paid_run = ensure_period_not_closed(
        db,
        reference_month=month,
        reference_year=year,
        regional=selected_regional,
        allow_revision=allow_paid_revision,
    )
    value_per_point = point_value if point_value is not None else get_point_value(db)
    if point_value is not None:
        upsert_setting(db, "point_value", f"{point_value:.2f}", "Valor monetário pago por ponto final.")

    with performance_step("calculate_scores", "period_orders"):
        orders = _period_orders(db, month, year, selected_regional)
    if not orders:
        period_label = f"{month:02d}/{year}"
        scope_label = f" na regional {selected_regional}" if selected_regional else ""
        raise HTTPException(
            status_code=409,
            detail=f"Nenhuma O.S encontrada para {period_label}{scope_label}. Nenhuma apuração foi salva.",
        )
    completed_orders = [order for order in orders if scoring_detail.completed(order)]
    with performance_step("calculate_scores", f"detect_post_payment_warranty_debits[{len(completed_orders)} orders]"):
        point_balance.detect_post_payment_warranty_debits(db, completed_orders, triggered_by=executed_by)
    health_eligible_orders = [order for order in orders if scoring_detail.counts_for_regional_health(order)]
    with performance_step("calculate_scores", f"calculate_regional_health[{len(health_eligible_orders)} orders]"):
        health_by_regional = calculate_regional_health(db, health_eligible_orders)
    with performance_step("calculate_scores", f"explain_orders[{len(orders)} orders]"):
        order_details = scoring_detail.explain_orders(db, orders, default_point_value=float(value_per_point))
    with performance_step("calculate_scores", "calculate_regional_health_from_details"):
        health_by_regional = scoring_detail.calculate_regional_health_from_details(db, order_details, health_by_regional)
    with performance_step("calculate_scores", "apply_cpk_adjustment"):
        health_by_regional = _apply_cpk_adjustment(db, health_by_regional, month, year)
    details_by_collaborator: dict[int, list[dict]] = defaultdict(list)
    for detail in order_details:
        if not scoring_detail.is_identified_collaborator_detail(detail):
            continue
        details_by_collaborator[int(detail["collaborator_id"])].append(detail)

    collaborators_stmt = select(Collaborator).where(Collaborator.active.is_(True))
    collaborators = [
        collaborator
        for collaborator in db.scalars(collaborators_stmt.order_by(Collaborator.name.asc()))
        if details_by_collaborator.get(collaborator.id)
    ]

    source_import = db.scalar(select(ImportRun).order_by(desc(ImportRun.created_at), desc(ImportRun.id)).limit(1))
    rules_version = db.scalar(
        select(GamificationConfigVersion)
        .where(GamificationConfigVersion.active.is_(True))
        .order_by(desc(GamificationConfigVersion.updated_at), desc(GamificationConfigVersion.id))
        .limit(1)
    )

    run = CalculationRun(
        reference_month=month,
        reference_year=year,
        regional=selected_regional,
        point_value=float(value_per_point),
        source_import_id=source_import.id if source_import else None,
        source_filename=source_import.filename if source_import else None,
        rules_version_id=rules_version.id if rules_version else None,
        status="draft",
        status_changed_at=now_utc(),
        status_changed_by=executed_by,
        status_note=execution_note.strip() if execution_note else (
            f"Revisao criada a partir do fechamento pago #{paid_run.id}." if paid_run and allow_paid_revision else None
        ),
        executed_by=executed_by,
        executed_at=now_utc(),
        config_snapshot=build_rule_snapshot(db),
    )
    db.add(run)
    db.flush()

    result_summary = {
        "dashboard_cache_version": 3,
        "total_service_orders": len(orders),
        "gross_points": 0.0,
        "penalty_points": 0.0,
        "net_points": 0.0,
        "final_points": 0.0,
        "estimated_payment": 0.0,
    }
    cached_score_summaries: dict[str, dict[str, float | int | str]] = {}
    pending_entries_by_collaborator = point_balance.pending_entries_by_collaborator_batch(
        db, [collaborator.id for collaborator in collaborators]
    )

    for collaborator in collaborators:
        collaborator_details = details_by_collaborator.get(collaborator.id, [])
        effective_regional, health = scoring_detail.health_for_details(
            collaborator_details,
            health_by_regional,
            collaborator.regional,
        )
        official_regional = _official_collaborator_regional(collaborator, effective_regional)
        if official_regional and official_regional in health_by_regional:
            health = health_by_regional[official_regional]
            effective_regional = official_regional
        multiplier = float(health.get("multiplier", 0.0))
        summary = scoring_detail.summarize_details(
            collaborator_details,
            multiplier,
            float(value_per_point),
        )
        summary["regional"] = official_regional or effective_regional
        summary["health_status"] = str(health.get("health_status", scoring_detail.HEALTH_BELOW_MINIMUM_STATUS))

        # Colaborador nao cadastrado formalmente (is_registered=False) nunca gera valor a pagar:
        # pontos/O.S continuam visiveis para acompanhamento, mas o R$ fica zerado em toda a cadeia
        # (card agregado, CollaboratorScore individual, bonus de lideranca) ate que o cadastro seja
        # concluido - a garantia de que ele nao sera pago precisa nascer aqui, no calculo, e nao
        # depender de um filtro de tela (ex: exportacao de CSV).
        if not collaborator.is_registered:
            summary["estimated_payment"] = 0.0

        # Previa nao-destrutiva do saldo de garantias pendentes: nao consome nada aqui - o consumo
        # so acontece quando este fechamento efetivamente vira "paid" (calculation_runs.py).
        pre_balance_final_points = float(summary["final_points"])
        pre_balance_estimated_payment = float(summary["estimated_payment"])
        balance_preview = point_balance.preview_pending_adjustment(
            db,
            collaborator.id,
            pre_balance_final_points,
            pending=pending_entries_by_collaborator.get(collaborator.id, []),
        )
        summary["balance_adjustment_points"] = balance_preview["adjustment_points"]
        summary["balance_after"] = balance_preview["projected_balance"]
        # Preserva os valores "brutos" (antes do saldo) em cache para o momento em que este fechamento
        # for de fato marcado como pago: apply_pending_entries_for_paid_run precisa partir do bruto,
        # nao do valor ja ajustado pela previa do rascunho.
        summary["gross_final_points"] = round(pre_balance_final_points, 2)
        summary["gross_estimated_payment"] = round(pre_balance_estimated_payment, 2)
        if balance_preview["adjustment_points"]:
            effective_rate = (
                pre_balance_estimated_payment / pre_balance_final_points
                if pre_balance_final_points
                else float(value_per_point)
            )
            summary["final_points"] = round(max(balance_preview["projected_balance"], 0.0), 2)
            summary["estimated_payment"] = round(summary["final_points"] * effective_rate, 2)
            if not collaborator.is_registered:
                summary["estimated_payment"] = 0.0

        cached_score_summaries[str(collaborator.id)] = dict(summary)
        result_summary["gross_points"] = round(float(result_summary["gross_points"]) + float(summary["gross_points"]), 2)
        result_summary["penalty_points"] = round(float(result_summary["penalty_points"]) + float(summary["penalty_points"]), 2)
        result_summary["net_points"] = round(float(result_summary["net_points"]) + float(summary["net_points"]), 2)
        result_summary["final_points"] = round(float(result_summary["final_points"]) + float(summary["final_points"]), 2)
        result_summary["estimated_payment"] = round(
            float(result_summary["estimated_payment"]) + float(summary["estimated_payment"]),
            2,
        )

        db.add(
            CollaboratorScore(
                calculation_run_id=run.id,
                collaborator_id=collaborator.id,
                service_orders_count=int(summary["total_service_orders"]),
                gross_points=float(summary["gross_points"]),
                penalty_points=float(summary["penalty_points"]),
                net_points=float(summary["net_points"]),
                health_multiplier=multiplier,
                health_status=str(summary["health_status"]),
                final_points=float(summary["final_points"]),
                estimated_payment=float(summary["estimated_payment"]),
                balance_adjustment_points=float(summary["balance_adjustment_points"]),
                balance_after=float(summary["balance_after"]),
            )
        )

    average_points = scoring_detail.average_group_default_points(db)
    total_collaborators = len({int(item["collaborator_id"]) for item in order_details if scoring_detail.is_identified_collaborator_detail(item)})
    unscored_count = sum(1 for item in order_details if item["is_unscored"])
    closure_pending_os_codes = {
        str(item["os_code"])
        for item in order_details
        if item["is_unscored"]
        or (
            item["diagnosis"]
            and item["diagnosis_rule_id"] is None
            and str(item["diagnosis"]).strip().lower() != "não informado"
        )
    }
    result_summary["score_summaries"] = cached_score_summaries
    result_summary["cards"] = {
        "total_collaborators": total_collaborators,
        "total_service_orders": len(orders),
        "scored_service_orders": sum(1 for item in order_details if item["is_scored"]),
        "unscored_service_orders": unscored_count,
        "penalized_service_orders": sum(1 for item in order_details if item["is_penalized"]),
        "warranty_service_orders": sum(1 for item in order_details if item["recurrence_classification"] in scoring_detail.RECURRENCE_DISCOUNT_CLASSIFICATIONS),
        "recurrence_service_orders": sum(1 for item in order_details if item["recurrence_classification"] in scoring_detail.RECURRENCE_DISCOUNT_CLASSIFICATIONS),
        "rescheduled_service_orders": sum(1 for item in order_details if item["has_reschedule"]),
        "pending_service_orders": sum(1 for item in order_details if item["has_pending"]),
        "sla_out_service_orders": sum(1 for item in order_details if item["is_sla_out_of_time"]),
        "annulled_service_orders": sum(1 for item in order_details if item["is_annulled"]),
        "diagnosis_penalized_service_orders": sum(1 for item in order_details if float(item["diagnosis_penalty_points"]) > 0),
        "manual_review_service_orders": sum(1 for item in order_details if item["requires_manual_review"]),
        "diagnosis_unmapped_service_orders": sum(
            1
            for item in order_details
            if item["diagnosis"]
            and item["diagnosis_rule_id"] is None
            and str(item["diagnosis"]).strip().lower() != "não informado"
        ),
        "closure_pending_service_orders": len(closure_pending_os_codes),
        "gross_points": round(float(result_summary["gross_points"]), 2),
        "penalty_points": round(float(result_summary["penalty_points"]), 2),
        "final_points": round(float(result_summary["final_points"]), 2),
        "estimated_payment": round(float(result_summary["estimated_payment"]), 2),
        "lost_points": round(sum(float(item["penalty_points"]) for item in order_details), 2),
        "lost_payment": round(
            sum(float(item["penalty_points"]) * float(item.get("point_value", value_per_point)) for item in order_details),
            2,
        ),
        "unscored_estimated_payment": round(sum(average_points for item in order_details if item["is_unscored"]) * float(value_per_point), 2),
        "orders_without_scoring_rule": unscored_count,
    }
    result_summary["health_by_regional"] = list(health_by_regional.values())
    result_summary["penalty_distribution"] = calculate_penalty_distribution(db, orders, details=order_details)
    financial_context = {int(collaborator_id): summary for collaborator_id, summary in cached_score_summaries.items()}
    result_summary.update(
        scoring_detail.financial_breakdowns(
            db,
            orders,
            float(value_per_point),
            details=order_details,
            health_by_regional=health_by_regional,
            collaborator_context=financial_context,
        )
    )

    run.result_summary = result_summary
    db.flush()
    return run


GAMIFICATION_PREVIEW_MISSING_RUN = (
    "A prévia do mês corrente ainda não foi calculada."
)
GAMIFICATION_PREVIEW_NO_REGIONAL = (
    "Nenhuma filial foi vinculada ao seu usuário."
)


def gamification_preview(db: Session, user) -> dict:
    """Valor da gamificação "de agora": a PRÉVIA do mês corrente, não o último fechamento pago.

    Não recalcula nada. `recalculate_current_period` já regrava o rascunho do mês corrente a cada
    ciclo do sincronizador do IXC (e a cada correção de Tipo Geral), então aqui é só leitura do
    rascunho mais recente daquele período. Por isso o payload devolve `calculated_at` e `status`:
    uma prévia velha (sincronização parada, ou mês já pago e portanto congelado) precisa aparecer
    como velha na tela, nunca como número fresco.

    Os totais saem reconciliados das linhas `collaborator_scores`, nunca do JSON gravado - foi
    exatamente a divergência entre os dois que gerou o achado C1 (o card "Total a pagar"
    contradizendo a lista de colaboradores da mesma resposta).

    Escopo: gestor regional recebe só a soma das filiais dele, somando as linhas dos próprios
    colaboradores em vez do total da empresa. A regional aqui é comparada AGRUPADA
    (`normalize_regional` = `normalize_regional_grouped`), igual ao resto da gamificação.

    Procura só o run global do mês (`regional IS NULL`), que é o que o recálculo automático
    produz. Um fechamento avulso de uma única filial não é o total da empresa e não serve como
    prévia geral - nesse caso a resposta vem indisponível, em vez de um número parcial disfarçado
    de total.
    """
    reference_month, reference_year = current_reference_period()
    point_value = get_point_value(db)
    unavailable = {
        "available": False,
        "reference_month": reference_month,
        "reference_year": reference_year,
        "status": None,
        "is_preview": False,
        "estimated_payment": None,
        "final_points": None,
        "collaborators": None,
        "point_value": point_value,
        "calculated_at": None,
        "scope_regionals": [],
        "unavailable_reason": GAMIFICATION_PREVIEW_MISSING_RUN,
    }

    run = pick_run_by_status_priority(
        db,
        select(CalculationRun)
        .where(CalculationRun.reference_month == reference_month)
        .where(CalculationRun.reference_year == reference_year)
        .where(CalculationRun.regional.is_(None))
        .options(selectinload(CalculationRun.scores).selectinload(CollaboratorScore.collaborator)),
    )
    if run is None:
        return unavailable

    scoped_regionals = effective_managed_regionals_grouped(user.managed_regional, user.managed_regionals)
    scores = list(run.scores)
    if scoped_regionals:
        allowed = set(scoped_regionals)
        scores = [
            score
            for score in scores
            if _official_collaborator_regional(score.collaborator) in allowed
        ]
    elif getattr(user, "role", None) == "regional_manager_viewer":
        # Mesma regra da Operação Analítica: gestor regional sem filial configurada não recebe
        # escopo implícito de "empresa toda".
        return {**unavailable, "unavailable_reason": GAMIFICATION_PREVIEW_NO_REGIONAL}

    return {
        "available": True,
        "reference_month": run.reference_month,
        "reference_year": run.reference_year,
        "status": run.status,
        "is_preview": run.status == "draft",
        "estimated_payment": round(sum(float(score.estimated_payment) for score in scores), 2),
        "final_points": round(sum(float(score.final_points) for score in scores), 2),
        "collaborators": len(scores),
        "point_value": float(run.point_value) or point_value,
        "calculated_at": run.executed_at or run.created_at,
        "scope_regionals": scoped_regionals,
        "unavailable_reason": None,
    }


def latest_run(db: Session) -> CalculationRun | None:
    with_orders_stmt = (
        select(CalculationRun)
        .join(CalculationRun.scores)
        .where(CollaboratorScore.service_orders_count > 0)
        .options(selectinload(CalculationRun.scores).selectinload(CollaboratorScore.collaborator))
    )
    run_with_orders = pick_run_by_status_priority(db, with_orders_stmt)
    if run_with_orders:
        return run_with_orders

    any_run_stmt = select(CalculationRun).options(
        selectinload(CalculationRun.scores).selectinload(CollaboratorScore.collaborator)
    )
    return pick_run_by_status_priority(db, any_run_stmt)


def _run_extra_summaries(db: Session, run: CalculationRun) -> dict[int, dict[str, float | int | str]]:
    orders = _period_orders(db, run.reference_month, run.reference_year, run.regional)
    details = scoring_detail.explain_orders(db, orders, default_point_value=float(run.point_value))
    grouped: dict[int, list[dict]] = defaultdict(list)
    for detail in details:
        grouped[int(detail["collaborator_id"])].append(detail)

    summaries: dict[int, dict[str, float | int | str]] = {}
    health_by_regional = scoring_detail.calculate_regional_health(db, [order for order in orders if scoring_detail.counts_for_regional_health(order)])
    health_by_regional = scoring_detail.calculate_regional_health_from_details(db, details, health_by_regional)
    health_by_regional = _apply_cpk_adjustment(db, health_by_regional, run.reference_month, run.reference_year)
    for score in run.scores:
        collaborator_details = grouped.get(score.collaborator_id, [])
        effective_regional, health = scoring_detail.health_for_details(
            collaborator_details,
            health_by_regional,
            score.collaborator.regional,
        )
        official_regional = _official_collaborator_regional(score.collaborator, effective_regional)
        if official_regional and official_regional in health_by_regional:
            health = health_by_regional[official_regional]
            effective_regional = official_regional
        summaries[score.collaborator_id] = scoring_detail.summarize_details(
            collaborator_details,
            float(health.get("multiplier", score.health_multiplier)),
            run.point_value,
        )
        summaries[score.collaborator_id]["regional"] = official_regional or effective_regional
        summaries[score.collaborator_id]["health_status"] = str(health.get("health_status", score.health_status))
        # summarize_details recalcula final_points/estimated_payment BRUTOS (sem saber de
        # nenhum debito de garantia). Este e um caminho de contingencia (so roda quando o
        # cache score_summaries do run esta ausente) - se o colaborador JA teve um debito
        # aplicado de verdade (persistido em CollaboratorScore por _apply_point_balance_after_payment),
        # os valores oficiais sao os da linha do banco, nao a reconta bruta feita aqui.
        # Sem isto, um fechamento pago sem cache mostraria o valor pre-desconto.
        summaries[score.collaborator_id]["final_points"] = float(score.final_points)
        summaries[score.collaborator_id]["estimated_payment"] = float(score.estimated_payment)
        summaries[score.collaborator_id]["balance_adjustment_points"] = float(score.balance_adjustment_points or 0)
        summaries[score.collaborator_id]["balance_after"] = float(score.balance_after or 0)
    return summaries


TOTAL_FIELDS_FROM_SCORES = ("gross_points", "penalty_points", "net_points", "final_points", "estimated_payment")


def _totals_from_scores(run: CalculationRun) -> dict[str, float]:
    return {
        "gross_points": round(sum(float(score.gross_points) for score in run.scores), 2),
        "penalty_points": round(sum(float(score.penalty_points) for score in run.scores), 2),
        "net_points": round(sum(float(score.net_points) for score in run.scores), 2),
        "final_points": round(sum(float(score.final_points) for score in run.scores), 2),
        "estimated_payment": round(sum(float(score.estimated_payment) for score in run.scores), 2),
    }


def result_summary_with_totals_from_scores(run: CalculationRun) -> dict | None:
    """Copia do `result_summary` com os totais reconciliados a partir das linhas.

    NAO muta o objeto ORM - e usada em caminho de leitura, onde escrever no `run` provocaria um
    UPDATE inesperado. Serve pra que a API nunca devolva um total que contradiz a lista de
    colaboradores da mesma resposta, inclusive em fechamentos antigos cujo `result_summary`
    gravado ja nasceu divergente (achado C1 - o #1601 esta assim em producao). A gravacao
    definitiva desses totais acontece em `recompute_run_totals_from_scores`, no pagamento.
    """
    if not isinstance(run.result_summary, dict):
        return run.result_summary

    totals = _totals_from_scores(run)
    summary = dict(run.result_summary)
    summary.update(totals)
    cards = summary.get("cards")
    if isinstance(cards, dict):
        updated_cards = dict(cards)
        for field in TOTAL_FIELDS_FROM_SCORES:
            if field in updated_cards:
                updated_cards[field] = totals[field]
        summary["cards"] = updated_cards
    return summary


def recompute_run_totals_from_scores(run: CalculationRun) -> None:
    """Grava no `result_summary` os totais reconstruidos a partir das linhas `collaborator_scores`.

    Reatribui o dicionario inteiro em vez de mutar in-place: coluna JSON do SQLAlchemy so detecta
    mudanca por reatribuicao (ou `flag_modified` explicito) - foi exatamente essa mutacao in-place
    invisivel que deixou o cache do #1601 divergente depois do pagamento.
    """
    if not isinstance(run.result_summary, dict):
        return
    run.result_summary = result_summary_with_totals_from_scores(run)


def collaborator_financial_context(
    db: Session | None, run: CalculationRun
) -> dict[int, dict[str, float | int | str]]:
    """Contexto por colaborador usado por `financial_breakdowns` pra proporcionalizar o valor de
    cada O.S. O valor a pagar vem SEMPRE da linha `collaborator_scores` (fonte unica, achado C1);
    o cache so contribui com a regional efetiva do periodo, que nao existe como coluna."""
    summaries = cached_score_summaries(run)
    if not summaries and db:
        summaries = _run_extra_summaries(db, run)

    context: dict[int, dict[str, float | int | str]] = {}
    for score in run.scores:
        if int(score.service_orders_count) <= 0:
            continue
        summary = summaries.get(score.collaborator_id, {})
        context[score.collaborator_id] = {
            "regional": summary.get("regional") or (score.collaborator.regional if score.collaborator else ""),
            "health_multiplier": float(score.health_multiplier),
            "gross_estimated_payment": float(summary.get("gross_estimated_payment", score.estimated_payment)),
            "estimated_payment": float(score.estimated_payment),
        }
    return context


def refresh_run_breakdowns(db: Session, run: CalculationRun) -> None:
    """Recalcula os detalhamentos financeiros (`cost_by_*`, `penalty_distribution`,
    `health_by_regional`) a partir dos valores ATUAIS das linhas do fechamento.

    Achado C1 (agravante): marcar como pago recompunha `final_points`/`estimated_payment` mas
    deixava todos os detalhamentos congelados com a previa do rascunho - a mesma tela mostrava o
    card "Total a pagar" corrigido e, logo abaixo, "Valor a ser pago por regional" com o valor
    antigo. O bonus de lideranca NAO e somado aqui: quem chama deve rodar
    `calculate_and_store_leadership_bonus` em seguida (agora idempotente, achado C2).
    """
    orders = _period_orders(db, run.reference_month, run.reference_year, run.regional)
    if not orders:
        return

    point_value = float(run.point_value)
    details = scoring_detail.explain_orders(db, orders, default_point_value=point_value)
    health_by_regional = scoring_detail.calculate_regional_health(
        db, [order for order in orders if scoring_detail.counts_for_regional_health(order)]
    )
    health_by_regional = scoring_detail.calculate_regional_health_from_details(db, details, health_by_regional)
    health_by_regional = _apply_cpk_adjustment(db, health_by_regional, run.reference_month, run.reference_year)

    updated = dict(run.result_summary or {})
    updated.update(
        scoring_detail.financial_breakdowns(
            db,
            orders,
            point_value,
            details=details,
            health_by_regional=health_by_regional,
            collaborator_context=collaborator_financial_context(db, run),
        )
    )
    updated["penalty_distribution"] = calculate_penalty_distribution(db, orders, details=details)
    updated["health_by_regional"] = list(health_by_regional.values())
    run.result_summary = updated


def serialize_run(
    run: CalculationRun | None,
    db: Session | None = None,
    extra_summaries: dict[int, dict[str, float | int | str]] | None = None,
) -> dict | None:
    """Serializa um fechamento lendo SEMPRE a linha `collaborator_scores` para tudo que e valor
    persistido (pontos, pagamento, multiplicador, saldo, contagem de O.S).

    Achado C1 da auditoria 2026-08-26: este serializador preferia o cache
    `result_summary.score_summaries`, enquanto o historico de fechamentos, o extrato PDF do
    colaborador e o bonus de lideranca ja liam a linha. Quando os dois divergiam - e divergiam:
    o fechamento pago #1601 respondia R$ 18.191,18 aqui e R$ 18.271,68 no historico, R$ 80,50 de
    diferenca em 18 colaboradores - nao havia como saber qual era o valor certo, e a planilha de
    pagamento saia por este caminho enquanto o extrato entregue a pessoa saia pelo outro.

    A linha e a fonte unica. O cache continua servindo apenas o que NAO existe como coluna: a
    regional efetiva do periodo e os contadores derivados (`scored_service_orders`,
    `warranty_service_orders`, ...), que sao informativos e nao entram em nenhuma conta de valor.
    """
    if not run:
        return None

    if extra_summaries is None:
        extra_summaries = cached_score_summaries(run)
        if not extra_summaries and db:
            extra_summaries = _run_extra_summaries(db, run)
    scores_with_orders = [score for score in run.scores if int(score.service_orders_count) > 0]
    scores = sorted(scores_with_orders, key=lambda score: float(score.final_points), reverse=True)
    return {
        "id": run.id,
        "reference_month": run.reference_month,
        "reference_year": run.reference_year,
        "regional": run.regional,
        "point_value": run.point_value,
        "source_import_id": run.source_import_id,
        "source_filename": run.source_filename,
        "rules_version_id": run.rules_version_id,
        "result_summary": result_summary_with_totals_from_scores(run),
        "created_at": run.created_at,
        **serialize_run_status(run),
        "scores": [
            {
                "id": score.id,
                "collaborator_id": score.collaborator_id,
                "collaborator_name": score.collaborator.name,
                "role": score.collaborator.role,
                "regional": extra_summaries.get(score.collaborator_id, {}).get("regional", score.collaborator.regional),
                "is_registered": bool(score.collaborator.is_registered),
                # Valores persistidos: sempre da linha, nunca do cache (ver docstring).
                "service_orders_count": int(score.service_orders_count),
                "gross_points": float(score.gross_points),
                "penalty_points": float(score.penalty_points),
                "net_points": float(score.net_points),
                "health_multiplier": float(score.health_multiplier),
                "health_status": str(score.health_status),
                "final_points": float(score.final_points),
                "estimated_payment": float(score.estimated_payment),
                "balance_adjustment_points": float(score.balance_adjustment_points or 0),
                "balance_after": float(score.balance_after or 0),
                "scored_service_orders": int(extra_summaries.get(score.collaborator_id, {}).get("scored_service_orders", 0)),
                "unscored_service_orders": int(extra_summaries.get(score.collaborator_id, {}).get("unscored_service_orders", 0)),
                "penalized_service_orders": int(extra_summaries.get(score.collaborator_id, {}).get("penalized_service_orders", 0)),
                "warranty_service_orders": int(extra_summaries.get(score.collaborator_id, {}).get("warranty_service_orders", 0)),
                "recurrence_service_orders": int(extra_summaries.get(score.collaborator_id, {}).get("recurrence_service_orders", 0)),
                "rescheduled_service_orders": int(extra_summaries.get(score.collaborator_id, {}).get("rescheduled_service_orders", 0)),
                "pending_service_orders": int(extra_summaries.get(score.collaborator_id, {}).get("pending_service_orders", 0)),
                "sla_out_service_orders": int(extra_summaries.get(score.collaborator_id, {}).get("sla_out_service_orders", 0)),
                "annulled_service_orders": int(extra_summaries.get(score.collaborator_id, {}).get("annulled_service_orders", 0)),
                "diagnosis_penalized_service_orders": int(
                    extra_summaries.get(score.collaborator_id, {}).get("diagnosis_penalized_service_orders", 0)
                ),
                "manual_review_service_orders": int(
                    extra_summaries.get(score.collaborator_id, {}).get("manual_review_service_orders", 0)
                ),
                "diagnosis_unmapped_service_orders": int(
                    extra_summaries.get(score.collaborator_id, {}).get("diagnosis_unmapped_service_orders", 0)
                ),
            }
            for score in scores
        ],
    }


DRAFT_RETENTION_ENABLED_SETTING = "gamification_draft_retention_enabled"
DRAFT_RETENTION_KEEP_SETTING = "gamification_draft_retention_keep"
DRAFT_RETENTION_DEFAULT_KEEP = 3


def prune_superseded_drafts(db: Session, run: CalculationRun) -> int:
    """Apaga rascunhos antigos do MESMO periodo que `run` acabou de substituir.

    Motivo (achado A1 da auditoria 2026-08-26): `recalculate_current_period` cria um
    `CalculationRun` novo a cada ciclo do sincronizador do IXC (20 min) e nada nunca remove os
    anteriores. A base chegou a 1.106 fechamentos e 225.121 linhas de `collaborator_scores`,
    sendo 223.811 em rascunhos descartaveis - 779 so de julho/2026. Isso degrada toda tela do
    modulo e, principalmente, o caminho de pagamento.

    DESLIGADO POR PADRAO (`gamification_draft_retention_enabled`). E uma rotina destrutiva:
    quem opera decide quando liga-la, depois de conferir o que seria removido. Enquanto estiver
    desligada esta funcao nao apaga nada e devolve 0.

    Nunca remove:
      - fechamentos que nao sao `draft` (review/approved/paid/cancelled sao registro, nao cache);
      - o proprio `run` recem-criado e os `keep` rascunhos mais recentes do periodo;
      - rascunhos referenciados pelo ledger de saldo (`origin_calculation_run_id` ou
        `applied_calculation_run_id`) - sao a origem rastreavel de um debito de garantia. Na base
        real isso protege 9 rascunhos.
    """
    if get_setting(db, DRAFT_RETENTION_ENABLED_SETTING, "false").strip().lower() != "true":
        return 0

    keep = max(int(_safe_float(get_setting(db, DRAFT_RETENTION_KEEP_SETTING, str(DRAFT_RETENTION_DEFAULT_KEEP)), DRAFT_RETENTION_DEFAULT_KEEP)), 1)

    stmt = (
        select(CalculationRun.id)
        .where(CalculationRun.reference_month == run.reference_month)
        .where(CalculationRun.reference_year == run.reference_year)
        .where(CalculationRun.status == "draft")
        .order_by(desc(CalculationRun.created_at), desc(CalculationRun.id))
    )
    stmt = stmt.where(CalculationRun.regional.is_(None)) if run.regional is None else stmt.where(CalculationRun.regional == run.regional)

    candidate_ids = [run_id for run_id in db.scalars(stmt) if run_id != run.id][keep:]
    if not candidate_ids:
        return 0

    referenced = set(
        db.scalars(
            select(PointBalanceEntry.origin_calculation_run_id).where(
                PointBalanceEntry.origin_calculation_run_id.in_(candidate_ids)
            )
        )
    ) | set(
        db.scalars(
            select(PointBalanceEntry.applied_calculation_run_id).where(
                PointBalanceEntry.applied_calculation_run_id.in_(candidate_ids)
            )
        )
    )
    removable = [run_id for run_id in candidate_ids if run_id not in referenced]
    if not removable:
        return 0

    # `LeadershipBonusResult` tem FK para o fechamento e nao esta em cascade - precisa sair antes.
    # `CollaboratorScore` sai junto pelo cascade="all, delete-orphan" do relacionamento.
    db.execute(delete(LeadershipBonusResult).where(LeadershipBonusResult.calculation_run_id.in_(removable)))
    db.execute(delete(CollaboratorScore).where(CollaboratorScore.calculation_run_id.in_(removable)))
    db.execute(delete(CalculationRun).where(CalculationRun.id.in_(removable)))
    logger.info(
        "Retenção de rascunhos: %d rascunho(s) de %02d/%d removidos (mantidos os %d mais recentes).",
        len(removable),
        run.reference_month,
        run.reference_year,
        keep,
    )
    return len(removable)


def recalculate_current_period(
    db: Session,
    triggered_by: int | None = None,
    execution_note: str = "Recálculo automático após atualização de dados.",
) -> None:
    """Recalcula automaticamente só o rascunho do mês/ano corrente (nunca período já pago ou já
    encerrado por ter virado o mês - `calculate_scores` recusa com um erro claro nesses casos, e esse
    erro é só logado, não interrompe quem chamou). "Mês corrente" é sempre decidido no fuso de Porto
    Velho (não UTC) - usar o relógio UTC do container erraria a virada do mês em até 4h (achado real,
    ver docs/plano-integracao-ixc.md).

    Compartilhada por dois gatilhos: a sincronização periódica com o IXC (`ixc_scheduler.py`) e uma
    correção de Tipo Geral que afeta O.S já importadas (`api/routes/scoring.py`) - ambos querem que o
    efeito da mudança apareça no fechamento corrente sem precisar de um clique manual."""
    now = now_porto_velho()
    try:
        run = calculate_scores(
            db,
            reference_month=now.month,
            reference_year=now.year,
            regional=None,
            executed_by=triggered_by,
            allow_paid_revision=False,
            execution_note=execution_note,
        )
        calculate_and_store_leadership_bonus(db, run)
        prune_superseded_drafts(db, run)
        db.commit()
        logger.info("Recálculo automático do período %02d/%d concluído (run #%s).", now.month, now.year, run.id)
    except Exception:
        db.rollback()
        logger.exception("Falha ao recalcular automaticamente o período %02d/%d", now.month, now.year)
