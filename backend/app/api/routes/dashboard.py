from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import require_permission
from app.db.session import get_db
from app.schemas import DashboardSummary
from app.services.calculation import (
    _period_orders,
    calculate_penalty_distribution,
    calculate_regional_health,
    calculate_scores,
    get_point_value,
    latest_run,
    serialize_run,
)
from app.services.scoring_detail import (
    RECURRENCE_DISCOUNT_CLASSIFICATIONS,
    average_group_default_points,
    calculate_regional_health_from_details,
    completed,
    explain_orders,
    financial_breakdowns,
    health_for_details as scoring_detail_health_for_details,
    is_identified_collaborator_detail,
    summarize_details,
)
from app.services.leadership_bonus import leadership_bonus_from_ranking

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(
    reference_month: int | None = None,
    reference_year: int | None = None,
    regional: str | None = None,
    db: Session = Depends(get_db),
    user=Depends(require_permission("dashboard:read")),
):
    run = latest_run(db)
    if not run:
        run = calculate_scores(db)

    point_value = float(run.point_value)
    selected_month = reference_month or run.reference_month
    selected_year = reference_year or run.reference_year
    selected_regional = regional if regional is not None else run.regional

    orders = _period_orders(db, selected_month, selected_year, selected_regional)
    details = explain_orders(db, orders, default_point_value=point_value)
    health_by_regional = calculate_regional_health(db, [order for order in orders if completed(order)])
    health_by_regional = calculate_regional_health_from_details(db, details, health_by_regional)
    details_by_collaborator: dict[int, list[dict]] = {}
    for detail in details:
        if not is_identified_collaborator_detail(detail):
            continue
        details_by_collaborator.setdefault(int(detail["collaborator_id"]), []).append(detail)

    if reference_month or reference_year or regional is not None:
        ranking = []
        for index, (collaborator_id, collaborator_details) in enumerate(details_by_collaborator.items(), start=1):
            order = next((item for item in orders if item.collaborator_id == collaborator_id), None)
            collaborator = order.collaborator if order and order.collaborator else None
            base_regional = collaborator.regional if collaborator else str(collaborator_details[0].get("regional") or "")
            effective_regional, health = scoring_detail_health_for_details(
                collaborator_details,
                health_by_regional,
                base_regional,
            )
            summary = summarize_details(
                collaborator_details,
                float(health.get("multiplier", 1.0)),
                point_value,
            )
            ranking.append(
                {
                    "id": index,
                    "collaborator_id": collaborator_id,
                    "collaborator_name": collaborator.name if collaborator else str(collaborator_details[0].get("collaborator_name") or ""),
                    "role": collaborator.role if collaborator else "",
                    "regional": effective_regional or base_regional,
                    "is_registered": bool(collaborator.is_registered) if collaborator else True,
                    "health_status": str(health.get("health_status", "Nao avaliado")),
                    **summary,
                    "service_orders_count": int(summary["total_service_orders"]),
                }
            )
        ranking = sorted(ranking, key=lambda item: float(item["final_points"]), reverse=True)
        serialized = {
            "id": run.id,
            "reference_month": selected_month,
            "reference_year": selected_year,
            "regional": selected_regional,
            "point_value": point_value,
            "source_import_id": run.source_import_id,
            "source_filename": run.source_filename,
            "rules_version_id": run.rules_version_id,
            "result_summary": run.result_summary,
            "created_at": datetime.now(timezone.utc),
            "scores": ranking,
        }
    else:
        extra_summaries = {}
        for score in run.scores:
            collaborator_details = details_by_collaborator.get(score.collaborator_id, [])
            effective_regional, health = scoring_detail_health_for_details(
                collaborator_details,
                health_by_regional,
                score.collaborator.regional,
            )
            summary = summarize_details(
                collaborator_details,
                float(health.get("multiplier", score.health_multiplier)),
                point_value,
            )
            summary["regional"] = effective_regional or score.collaborator.regional
            summary["health_status"] = str(health.get("health_status", score.health_status))
            extra_summaries[score.collaborator_id] = summary
        serialized = serialize_run(run, extra_summaries=extra_summaries)
        ranking = serialized["scores"] if serialized else []
    average_points = average_group_default_points(db)
    total_collaborators = len({int(item["collaborator_id"]) for item in details if is_identified_collaborator_detail(item)})
    unscored_count = sum(1 for item in details if item["is_unscored"])
    closure_pending_os_codes = {
        str(item["os_code"])
        for item in details
        if item["is_unscored"]
        or (
            item["diagnosis"]
            and item["diagnosis_rule_id"] is None
            and str(item["diagnosis"]).strip().lower() != "nao informado"
        )
    }

    cards = {
        "total_collaborators": total_collaborators,
        "total_service_orders": len(orders),
        "scored_service_orders": sum(1 for item in details if item["is_scored"]),
        "unscored_service_orders": unscored_count,
        "penalized_service_orders": sum(1 for item in details if item["is_penalized"]),
        "warranty_service_orders": sum(1 for item in details if item["recurrence_classification"] in RECURRENCE_DISCOUNT_CLASSIFICATIONS),
        "recurrence_service_orders": sum(1 for item in details if item["recurrence_classification"] in RECURRENCE_DISCOUNT_CLASSIFICATIONS),
        "rescheduled_service_orders": sum(1 for item in details if item["has_reschedule"]),
        "pending_service_orders": sum(1 for item in details if item["has_pending"]),
        "sla_out_service_orders": sum(1 for item in details if item["is_sla_out_of_time"]),
        "annulled_service_orders": sum(1 for item in details if item["is_annulled"]),
        "diagnosis_penalized_service_orders": sum(1 for item in details if float(item["diagnosis_penalty_points"]) > 0),
        "manual_review_service_orders": sum(1 for item in details if item["requires_manual_review"]),
        "diagnosis_unmapped_service_orders": sum(
            1
            for item in details
            if item["diagnosis"]
            and item["diagnosis_rule_id"] is None
            and str(item["diagnosis"]).strip().lower() != "nao informado"
        ),
        "closure_pending_service_orders": len(closure_pending_os_codes),
        "gross_points": round(sum(item["gross_points"] for item in ranking), 2),
        "penalty_points": round(sum(item["penalty_points"] for item in ranking), 2),
        "final_points": round(sum(item["final_points"] for item in ranking), 2),
        "estimated_payment": round(sum(item["estimated_payment"] for item in ranking), 2),
        "lost_points": round(sum(float(item["penalty_points"]) for item in details), 2),
        "lost_payment": round(
            sum(float(item["penalty_points"]) * float(item.get("point_value", point_value)) for item in details),
            2,
        ),
        "unscored_estimated_payment": round(
            sum(average_points for item in details if item["is_unscored"]) * point_value,
            2,
        ),
        "orders_without_scoring_rule": unscored_count,
    }
    breakdowns = financial_breakdowns(db, orders, point_value, details=details, health_by_regional=health_by_regional)

    return {
        "run": serialized,
        "cards": cards,
        "ranking": ranking,
        "leadership_bonus": leadership_bonus_from_ranking(
            db,
            int(serialized["id"]) if serialized else run.id,
            ranking,
            float(serialized["point_value"]) if serialized and serialized.get("point_value") is not None else float(run.point_value),
        ),
        "penalty_distribution": calculate_penalty_distribution(db, orders, details=details),
        "health_by_regional": list(health_by_regional.values()),
        "point_value": get_point_value(db),
        **breakdowns,
    }
