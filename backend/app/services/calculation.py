from __future__ import annotations

import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Iterable

from fastapi import HTTPException
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
from app.services import point_balance, scoring_detail
from app.services.calculation_closure import build_rule_snapshot, ensure_period_not_paid, now_utc, serialize_run_status
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

    def rule_matches(rule: HealthRule) -> bool:
        sla_matches = sla_rate >= float(rule.min_sla)
        # `100` means "do not restrict by recurrence yet"; smaller values activate the gate.
        recurrence_gate_enabled = float(rule.max_recurrence_rate) < 100
        recurrence_matches = recurrence_rate <= float(rule.max_recurrence_rate) if recurrence_gate_enabled else True
        return sla_matches and recurrence_matches

    ranked = sorted(
        active_rules,
        key=lambda rule: (rule.min_sla, -rule.max_recurrence_rate),
        reverse=True,
    )
    for rule in ranked:
        if rule_matches(rule):
            return rule

    return None


def calculate_regional_health(db: Session, orders: list[ServiceOrder]) -> dict[str, dict[str, float | int | str]]:
    return scoring_detail.calculate_regional_health(db, orders)


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
    paid_run = ensure_period_not_paid(
        db,
        reference_month=month,
        reference_year=year,
        regional=selected_regional,
        allow_revision=allow_paid_revision,
    )
    value_per_point = point_value if point_value is not None else get_point_value(db)
    if point_value is not None:
        upsert_setting(db, "point_value", f"{point_value:.2f}", "Valor monetário pago por ponto final.")

    orders = _period_orders(db, month, year, selected_regional)
    if not orders:
        period_label = f"{month:02d}/{year}"
        scope_label = f" na regional {selected_regional}" if selected_regional else ""
        raise HTTPException(
            status_code=409,
            detail=f"Nenhuma O.S encontrada para {period_label}{scope_label}. Nenhuma apuração foi salva.",
        )
    completed_orders = [order for order in orders if scoring_detail.completed(order)]
    point_balance.detect_post_payment_warranty_debits(db, completed_orders, triggered_by=executed_by)
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

        # Previa nao-destrutiva do saldo de garantias pendentes: nao consome nada aqui - o consumo
        # so acontece quando este fechamento efetivamente vira "paid" (calculation_runs.py).
        pre_balance_final_points = float(summary["final_points"])
        pre_balance_estimated_payment = float(summary["estimated_payment"])
        balance_preview = point_balance.preview_pending_adjustment(db, collaborator.id, pre_balance_final_points)
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
    result_summary.update(
        scoring_detail.financial_breakdowns(
            db,
            orders,
            float(value_per_point),
            details=order_details,
            health_by_regional=health_by_regional,
            collaborator_context=cached_score_summaries,
        )
    )

    run.result_summary = result_summary
    db.flush()
    return run


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


def serialize_run(
    run: CalculationRun | None,
    db: Session | None = None,
    extra_summaries: dict[int, dict[str, float | int | str]] | None = None,
) -> dict | None:
    if not run:
        return None

    if extra_summaries is None:
        extra_summaries = cached_score_summaries(run)
        if not extra_summaries and db:
            extra_summaries = _run_extra_summaries(db, run)
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
        **serialize_run_status(run),
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
                "balance_adjustment_points": float(
                    extra_summaries.get(score.collaborator_id, {}).get("balance_adjustment_points", score.balance_adjustment_points)
                ),
                "balance_after": float(extra_summaries.get(score.collaborator_id, {}).get("balance_after", score.balance_after)),
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
