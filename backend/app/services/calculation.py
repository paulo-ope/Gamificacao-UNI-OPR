from __future__ import annotations

import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AppSetting,
    CalculationRun,
    Collaborator,
    CollaboratorScore,
    GamificationConfigVersion,
    HealthRule,
    ImportRun,
    ScoringRule,
    ServiceOrder,
)
from app.services import scoring_detail
from app.services.regional import normalize_regional
from app.services.sla import SLA_FORA_DO_PRAZO, SLA_NO_PRAZO, normalize_sla_status


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


def _completed(order: ServiceOrder) -> bool:
    return normalize(order.status) in {
        "concluida",
        "concluido",
        "finalizada",
        "finalizado",
        "fechada",
        "fechado",
        "encerrada",
        "encerrado",
        "closed",
        "done",
    }


def _period_orders(db: Session, reference_month: int, reference_year: int, regional: str | None) -> list[ServiceOrder]:
    return scoring_detail.period_orders(db, reference_month, reference_year, regional)


def _official_collaborator_regional(collaborator: Collaborator, fallback: str | None = None) -> str | None:
    if collaborator.is_registered and collaborator.regional:
        return normalize_regional(collaborator.regional)
    return normalize_regional(fallback) if fallback else fallback


def _active_scoring_rules(db: Session) -> list[ScoringRule]:
    return list(
        db.scalars(
            select(ScoringRule)
            .options(selectinload(ScoringRule.group))
            .where(ScoringRule.active.is_(True))
            .order_by(ScoringRule.os_type.asc(), ScoringRule.os_subject.asc())
        )
    )


def _matching_scoring_rule(order: ServiceOrder, rules: Iterable[ScoringRule]) -> ScoringRule | None:
    active_rules = [rule for rule in rules if rule.group and rule.group.active]
    os_type = normalize(order.os_type)
    os_subject = normalize(order.os_subject)

    for rule in active_rules:
        if normalize(rule.os_type) == os_type and normalize(rule.os_subject) == os_subject:
            return rule

    for rule in active_rules:
        if normalize(rule.os_type) == os_type and not rule.os_subject:
            return rule

    for rule in active_rules:
        if normalize(rule.os_type) == os_type:
            return rule

    return None


def _order_points(order: ServiceOrder, rules: Iterable[ScoringRule]) -> float:
    rule = _matching_scoring_rule(order, rules)
    return float(rule.points) if rule else 0.0


def count_orders_without_scoring_rule(db: Session, orders: list[ServiceOrder]) -> int:
    details = scoring_detail.explain_orders(db, orders)
    return sum(1 for order in details if order["is_unscored"])


def _sla_inside(order: ServiceOrder) -> bool:
    normalized_status = normalize_sla_status(order.sla_status)
    if normalized_status == SLA_FORA_DO_PRAZO:
        return False
    if normalized_status == SLA_NO_PRAZO:
        return True
    if order.sla_hours is None or order.closing_time_hours is None:
        return False
    return order.closing_time_hours <= order.sla_hours


def recurrence_penalties(
    db: Session,
    orders: list[ServiceOrder],
    scoring_rules: list[ScoringRule],
) -> dict[int, float]:
    centralized = scoring_detail.recurrence_penalties(
        db,
        orders,
        scoring_detail.build_scoring_rule_lookup(scoring_detail.active_scoring_rules(db)),
    )
    return {order_id: float(item.get("points", 0)) for order_id, item in centralized.items()}


def select_health_rule(rules: list[HealthRule], sla_rate: float, recurrence_rate: float) -> HealthRule | None:
    active_rules = [rule for rule in rules if rule.active]
    if not active_rules:
        return None

    critical = next((rule for rule in active_rules if normalize(rule.name).startswith("critica")), None)
    attention = next((rule for rule in active_rules if "atencao" in normalize(rule.name)), None)
    if attention and critical:
        if sla_rate < attention.min_sla or recurrence_rate > attention.max_recurrence_rate:
            return critical

    ranked = sorted(
        [rule for rule in active_rules if rule is not critical],
        key=lambda rule: (rule.min_sla, -rule.max_recurrence_rate),
        reverse=True,
    )
    for rule in ranked:
        if rule.condition_operator == "or":
            if sla_rate >= rule.min_sla or recurrence_rate <= rule.max_recurrence_rate:
                return rule
        elif sla_rate >= rule.min_sla and recurrence_rate <= rule.max_recurrence_rate:
            return rule

    return critical or min(active_rules, key=lambda rule: rule.multiplier)


def calculate_regional_health(db: Session, orders: list[ServiceOrder]) -> dict[str, dict[str, float | int | str]]:
    return scoring_detail.calculate_regional_health(db, orders)


def calculate_penalty_distribution(
    db: Session,
    orders: list[ServiceOrder],
    details: list[dict] | None = None,
) -> list[dict[str, float | str]]:
    return scoring_detail.calculate_penalty_distribution(db, orders, details=details)


def calculate_scores(
    db: Session,
    reference_month: int | None = None,
    reference_year: int | None = None,
    regional: str | None = None,
    point_value: float | None = None,
) -> CalculationRun:
    now = datetime.now(timezone.utc)
    month = reference_month or now.month
    year = reference_year or now.year
    selected_regional = normalize_regional(regional) if regional else None
    value_per_point = point_value if point_value is not None else get_point_value(db)
    if point_value is not None:
        upsert_setting(db, "point_value", f"{point_value:.2f}", "Valor monetario pago por ponto final.")

    orders = _period_orders(db, month, year, selected_regional)
    completed_orders = [order for order in orders if scoring_detail.completed(order)]
    health_by_regional = calculate_regional_health(db, completed_orders)
    order_details = scoring_detail.explain_orders(db, orders, default_point_value=float(value_per_point))
    health_by_regional = scoring_detail.calculate_regional_health_from_details(db, order_details, health_by_regional)
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
    )
    db.add(run)
    db.flush()

    result_summary = {
        "total_service_orders": len(orders),
        "gross_points": 0.0,
        "penalty_points": 0.0,
        "net_points": 0.0,
        "final_points": 0.0,
        "estimated_payment": 0.0,
    }

    for collaborator in collaborators:
        collaborator_details = details_by_collaborator.get(collaborator.id, [])
        effective_regional, health = scoring_detail.health_for_details(
            collaborator_details,
            health_by_regional,
            collaborator.regional,
        )
        multiplier = float(health.get("multiplier", 1.0))
        summary = scoring_detail.summarize_details(
            collaborator_details,
            multiplier,
            float(value_per_point),
        )
        summary["regional"] = _official_collaborator_regional(collaborator, effective_regional)
        summary["health_status"] = str(health.get("health_status", "Boa"))
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
            )
        )

    run.result_summary = result_summary
    db.commit()
    return latest_run(db)


def latest_run(db: Session) -> CalculationRun | None:
    run_with_orders = db.scalar(
        select(CalculationRun)
        .join(CalculationRun.scores)
        .where(CollaboratorScore.service_orders_count > 0)
        .options(selectinload(CalculationRun.scores).selectinload(CollaboratorScore.collaborator))
        .order_by(desc(CalculationRun.created_at), desc(CalculationRun.id))
        .limit(1)
    )
    if run_with_orders:
        return run_with_orders

    return db.scalar(
        select(CalculationRun)
        .options(selectinload(CalculationRun.scores).selectinload(CollaboratorScore.collaborator))
        .order_by(desc(CalculationRun.created_at), desc(CalculationRun.id))
        .limit(1)
    )


def _run_extra_summaries(db: Session, run: CalculationRun) -> dict[int, dict[str, float | int | str]]:
    orders = _period_orders(db, run.reference_month, run.reference_year, run.regional)
    details = scoring_detail.explain_orders(db, orders, default_point_value=float(run.point_value))
    grouped: dict[int, list[dict]] = defaultdict(list)
    for detail in details:
        grouped[int(detail["collaborator_id"])].append(detail)

    summaries: dict[int, dict[str, float | int | str]] = {}
    health_by_regional = scoring_detail.calculate_regional_health(db, [order for order in orders if scoring_detail.completed(order)])
    health_by_regional = scoring_detail.calculate_regional_health_from_details(db, details, health_by_regional)
    for score in run.scores:
        collaborator_details = grouped.get(score.collaborator_id, [])
        effective_regional, health = scoring_detail.health_for_details(
            collaborator_details,
            health_by_regional,
            score.collaborator.regional,
        )
        summaries[score.collaborator_id] = scoring_detail.summarize_details(
            collaborator_details,
            float(health.get("multiplier", score.health_multiplier)),
            run.point_value,
        )
        summaries[score.collaborator_id]["regional"] = _official_collaborator_regional(score.collaborator, effective_regional)
        summaries[score.collaborator_id]["health_status"] = str(health.get("health_status", score.health_status))
    return summaries


def serialize_run(
    run: CalculationRun | None,
    db: Session | None = None,
    extra_summaries: dict[int, dict[str, float | int | str]] | None = None,
) -> dict | None:
    if not run:
        return None

    if extra_summaries is None:
        extra_summaries = _run_extra_summaries(db, run) if db else {}
    scores_with_orders = [
        score
        for score in run.scores
        if int(extra_summaries.get(score.collaborator_id, {}).get("total_service_orders", score.service_orders_count)) > 0
    ]
    scores = sorted(
        scores_with_orders,
        key=lambda score: float(extra_summaries.get(score.collaborator_id, {}).get("final_points", score.final_points)),
        reverse=True,
    )
    return {
        "id": run.id,
        "reference_month": run.reference_month,
        "reference_year": run.reference_year,
        "regional": run.regional,
        "point_value": run.point_value,
        "source_import_id": run.source_import_id,
        "source_filename": run.source_filename,
        "rules_version_id": run.rules_version_id,
        "result_summary": run.result_summary,
        "created_at": run.created_at,
        "scores": [
            {
                "id": score.id,
                "collaborator_id": score.collaborator_id,
                "collaborator_name": score.collaborator.name,
                "role": score.collaborator.role,
                "regional": extra_summaries.get(score.collaborator_id, {}).get("regional", score.collaborator.regional),
                "is_registered": bool(score.collaborator.is_registered),
                "service_orders_count": int(extra_summaries.get(score.collaborator_id, {}).get("total_service_orders", score.service_orders_count)),
                "gross_points": float(extra_summaries.get(score.collaborator_id, {}).get("gross_points", score.gross_points)),
                "penalty_points": float(extra_summaries.get(score.collaborator_id, {}).get("penalty_points", score.penalty_points)),
                "net_points": float(extra_summaries.get(score.collaborator_id, {}).get("net_points", score.net_points)),
                "health_multiplier": float(extra_summaries.get(score.collaborator_id, {}).get("health_multiplier", score.health_multiplier)),
                "health_status": str(extra_summaries.get(score.collaborator_id, {}).get("health_status", score.health_status)),
                "final_points": float(extra_summaries.get(score.collaborator_id, {}).get("final_points", score.final_points)),
                "estimated_payment": float(extra_summaries.get(score.collaborator_id, {}).get("estimated_payment", score.estimated_payment)),
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
