from __future__ import annotations

import unicodedata
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    CalculationRun,
    CollaboratorScore,
    DiagnosisPenaltyRule,
    RecurrenceClassificationRule,
    ScoringGroup,
    ScoringSubjectRule,
    SlaPenaltyRule,
    User,
)
from app.services.calculation import serialize_run
from app.services.regional import normalize_regional
from app.services.scoring_detail import explain_orders, period_orders


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    without_accents = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(without_accents.lower().strip().split())


def _email_identity(email: str) -> str:
    return _normalize_text(email.split("@", 1)[0].replace(".", " ").replace("_", " ").replace("-", " "))


def _latest_run(db: Session) -> CalculationRun | None:
    return db.scalar(
        select(CalculationRun)
        .options(selectinload(CalculationRun.scores).selectinload(CollaboratorScore.collaborator))
        .order_by(desc(CalculationRun.created_at), desc(CalculationRun.id))
        .limit(1)
    )


def _score_rows(db: Session, run: CalculationRun) -> list[dict[str, Any]]:
    return list(serialize_run(run, db).get("scores", []))


def _score_position(rows: list[dict[str, Any]], collaborator_id: int) -> int | None:
    for index, row in enumerate(rows, start=1):
        if int(row.get("collaborator_id") or 0) == collaborator_id:
            return index
    return None


def _resolve_score(user: User, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None

    # Vínculo direto (`users.collaborator_id`) é a fonte da verdade - criado explicitamente pelo
    # admin ao vincular/criar o acesso na aba Colaboradores. Prioriza sobre a heurística de
    # nome/e-mail abaixo, que fica só como fallback pra contas antigas ainda não vinculadas.
    if user.collaborator_id is not None:
        for row in rows:
            if int(row.get("collaborator_id") or 0) == user.collaborator_id:
                return row
        return None

    user_name = _normalize_text(user.name)
    email_identity = _email_identity(user.email)

    for row in rows:
        collaborator_name = _normalize_text(str(row.get("collaborator_name") or ""))
        if collaborator_name and collaborator_name == user_name:
            return row

    for row in rows:
        collaborator_name = _normalize_text(str(row.get("collaborator_name") or ""))
        if email_identity and (email_identity == collaborator_name or email_identity in collaborator_name):
            return row

    # Sem vínculo direto e sem match por nome/e-mail: não existe mais fallback pro primeiro
    # colocado do ranking (achado de revisão - isso vazava a pontuação de outro colaborador pra
    # qualquer admin/operator/viewer sem correspondência). Devolve "sem colaborador vinculado".
    return None


def _portal_score(row: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "collaborator_id",
        "collaborator_name",
        "role",
        "regional",
        "service_orders_count",
        "gross_points",
        "penalty_points",
        "net_points",
        "health_multiplier",
        "health_status",
        "final_points",
        "estimated_payment",
        "scored_service_orders",
        "unscored_service_orders",
        "penalized_service_orders",
        "warranty_service_orders",
        "recurrence_service_orders",
        "rescheduled_service_orders",
        "pending_service_orders",
        "sla_out_service_orders",
        "annulled_service_orders",
        "diagnosis_penalized_service_orders",
        "manual_review_service_orders",
        "diagnosis_unmapped_service_orders",
    ]
    return {key: row.get(key, 0 if key.endswith("_orders") or key.endswith("_points") else "") for key in keys}


def _ranking_item(row: dict[str, Any], position: int, current_id: int | None) -> dict[str, Any]:
    collaborator_id = int(row.get("collaborator_id") or 0)
    return {
        "position": position,
        "collaborator_id": collaborator_id,
        "collaborator_name": str(row.get("collaborator_name") or "Colaborador"),
        "role": row.get("role"),
        "regional": str(row.get("regional") or "Sem regional"),
        "final_points": float(row.get("final_points") or 0),
        "estimated_payment": float(row.get("estimated_payment") or 0),
        "service_orders_count": int(row.get("service_orders_count") or 0),
        "scored_service_orders": int(row.get("scored_service_orders") or 0),
        "penalty_points": float(row.get("penalty_points") or 0),
        "is_current_user": collaborator_id == current_id,
    }


def build_portal_summary(db: Session, user: User) -> dict[str, Any]:
    run = _latest_run(db)
    if not run:
        return {
            "user": user,
            "period": {},
            "ranking": [],
            "message": "Nenhum fechamento foi calculado ainda.",
        }

    rows = _score_rows(db, run)
    current = _resolve_score(user, rows)
    sorted_rows = sorted(rows, key=lambda item: float(item.get("final_points") or 0), reverse=True)
    current_id = int(current.get("collaborator_id")) if current else None
    current_regional = normalize_regional(str(current.get("regional") or "")) if current else ""
    regional_rows = [
        row for row in sorted_rows if current_regional and normalize_regional(str(row.get("regional") or "")) == current_regional
    ]
    regional_position = _score_position(regional_rows, current_id) if current_id else None
    general_position = _score_position(sorted_rows, current_id) if current_id else None
    next_position_gap = None
    if current and regional_position and regional_position > 1:
        next_row = regional_rows[regional_position - 2]
        next_position_gap = max(0, round(float(next_row.get("final_points") or 0) - float(current.get("final_points") or 0), 2))

    return {
        "user": user,
        "collaborator": {
            "id": current_id,
            "name": str(current.get("collaborator_name") or ""),
            "role": current.get("role"),
            "regional": str(current.get("regional") or ""),
        }
        if current
        else None,
        "period": {
            "calculation_run_id": run.id,
            "reference_month": run.reference_month,
            "reference_year": run.reference_year,
            "status": run.status,
            "updated_at": run.executed_at or run.created_at,
        },
        "score": _portal_score(current) if current else None,
        "regional_position": regional_position,
        "regional_total": len(regional_rows),
        "general_position": general_position,
        "general_total": len(sorted_rows),
        "next_position_gap": next_position_gap,
        "ranking": [_ranking_item(row, index, current_id) for index, row in enumerate(regional_rows, start=1)],
        "message": None if current else "Nao foi encontrado um colaborador vinculado ao seu usuario.",
    }


def _order_label(detail: dict[str, Any]) -> tuple[str, str | None]:
    reasons = detail.get("reasons") or detail.get("penalty_reasons") or []
    reason = "; ".join(str(item) for item in reasons[:3]) if isinstance(reasons, list) else None
    if detail.get("is_unscored"):
        return "Sem regra de pontuacao", reason
    if detail.get("is_annulled"):
        return str(detail.get("scoring_status") or "Pontos anulados"), reason
    if detail.get("is_penalized"):
        return "Pontuada com desconto", reason
    if detail.get("requires_manual_review"):
        return "Revisao manual", reason
    if detail.get("is_scored"):
        return "Pontuada", reason
    return str(detail.get("scoring_status") or "Nao pontuada"), reason


def build_portal_orders(db: Session, user: User, limit: int = 80) -> list[dict[str, Any]]:
    run = _latest_run(db)
    if not run:
        return []
    summary = build_portal_summary(db, user)
    collaborator = summary.get("collaborator")
    if not collaborator:
        return []

    orders = [
        order
        for order in period_orders(db, run.reference_month, run.reference_year, str(collaborator["regional"]))
        if order.collaborator_id == int(collaborator["id"])
    ][: max(1, min(limit, 200))]
    details = explain_orders(db, orders, default_point_value=run.point_value)
    detail_by_id = {int(detail.get("id") or detail.get("service_order_id") or 0): detail for detail in details}

    result = []
    for order in orders:
        detail = detail_by_id.get(order.id, {})
        status_label, reason = _order_label(detail)
        result.append(
            {
                "id": order.id,
                "os_code": order.os_code,
                "opened_at": order.opened_at,
                "closed_at": order.closed_at,
                "os_type": order.os_type,
                "os_subject": order.os_subject,
                "group_name": detail.get("group_name"),
                "diagnosis": order.diagnosis,
                "status": order.status,
                "sla_status": order.sla_status,
                "base_points": float(detail.get("base_points") or 0),
                "penalty_points": float(detail.get("penalty_points") or 0),
                "net_points": float(detail.get("net_points") or 0),
                "status_label": status_label,
                "reason": reason,
            }
        )
    return result


def build_portal_rules(db: Session) -> dict[str, Any]:
    groups = db.scalars(select(ScoringGroup).where(ScoringGroup.active.is_(True)).order_by(ScoringGroup.name)).all()
    subjects = db.scalars(
        select(ScoringSubjectRule)
        .options(selectinload(ScoringSubjectRule.group))
        .where(ScoringSubjectRule.active.is_(True))
        .order_by(ScoringSubjectRule.os_type, ScoringSubjectRule.os_subject)
        .limit(300)
    ).all()
    diagnosis = db.scalars(
        select(DiagnosisPenaltyRule).where(DiagnosisPenaltyRule.active.is_(True)).order_by(DiagnosisPenaltyRule.diagnosis_name)
    ).all()
    sla_rules = db.scalars(select(SlaPenaltyRule).where(SlaPenaltyRule.active.is_(True)).order_by(SlaPenaltyRule.name)).all()
    recurrence = db.scalars(
        select(RecurrenceClassificationRule)
        .where(RecurrenceClassificationRule.active.is_(True))
        .order_by(RecurrenceClassificationRule.priority, RecurrenceClassificationRule.name)
    ).all()
    return {
        "groups": [
            {"id": item.id, "name": item.name, "description": item.description, "default_points": item.default_points}
            for item in groups
        ],
        "subjects": [
            {
                "id": item.id,
                "os_type": item.os_type,
                "os_subject": item.os_subject,
                "group_name": item.group.name if item.group else None,
                "points": item.custom_points if not item.use_group_default else item.group.default_points if item.group else 0,
            }
            for item in subjects
        ],
        "diagnosis_rules": [
            {
                "id": item.id,
                "diagnosis_name": item.diagnosis_name,
                "action_type": item.action_type,
                "penalty_points": item.penalty_points,
                "description": item.description,
            }
            for item in diagnosis
        ],
        "sla_rules": [
            {"id": item.id, "name": item.name, "condition_type": item.condition_type, "penalty_type": item.penalty_type, "penalty_value": item.penalty_value}
            for item in sla_rules
        ],
        "recurrence_rules": [
            {
                "id": item.id,
                "name": item.name,
                "classification": item.classification,
                "discount_points": item.discount_points,
                "max_days": item.max_days,
                "description": item.description,
            }
            for item in recurrence
        ],
    }


def build_portal_simulation(db: Session, user: User, extra_points: float) -> dict[str, Any]:
    summary = build_portal_summary(db, user)
    current = summary.get("score")
    if not current:
        return {
            "current_position": None,
            "simulated_position": None,
            "extra_points": extra_points,
            "points_to_next": None,
            "disclaimer": "Simulacao indisponivel sem colaborador vinculado ao usuario.",
        }
    current_id = int(current["collaborator_id"])
    ranking = [dict(item) for item in summary.get("ranking", [])]
    for item in ranking:
        if int(item["collaborator_id"]) == current_id:
            item["final_points"] = float(item["final_points"]) + extra_points
    simulated = sorted(ranking, key=lambda item: float(item["final_points"]), reverse=True)
    simulated_position = _score_position(simulated, current_id)
    points_to_next = None
    if simulated_position and simulated_position > 1:
        next_row = simulated[simulated_position - 2]
        current_row = simulated[simulated_position - 1]
        points_to_next = max(0, round(float(next_row["final_points"]) - float(current_row["final_points"]), 2))
    return {
        "current_position": summary.get("regional_position"),
        "simulated_position": simulated_position,
        "extra_points": extra_points,
        "points_to_next": points_to_next,
        "disclaimer": "Simulacao simples: soma pontos extras ao fechamento atual e nao recalcula regras, descontos, saude ou pagamento.",
    }


def build_portal_overview(db: Session) -> dict[str, Any]:
    run = _latest_run(db)
    if not run:
        return {"period": {}, "message": "Nenhum fechamento foi calculado ainda."}

    rows = sorted(_score_rows(db, run), key=lambda item: float(item.get("final_points") or 0), reverse=True)
    regionals: dict[str, dict[str, Any]] = {}
    for row in rows:
        regional = normalize_regional(str(row.get("regional") or "")) or "Sem regional"
        item = regionals.setdefault(regional, {"regional": regional, "collaborators": 0, "service_orders": 0, "scored_service_orders": 0, "final_points": 0.0, "estimated_payment": 0.0, "penalty_points": 0.0, "_health_total": 0.0})
        item["collaborators"] += 1
        item["service_orders"] += int(row.get("service_orders_count") or 0)
        item["scored_service_orders"] += int(row.get("scored_service_orders") or 0)
        item["final_points"] += float(row.get("final_points") or 0)
        item["estimated_payment"] += float(row.get("estimated_payment") or 0)
        item["penalty_points"] += float(row.get("penalty_points") or 0)
        item["_health_total"] += float(row.get("health_multiplier") or 0)

    regional_summary = []
    for item in regionals.values():
        collaborators = int(item["collaborators"])
        item["health_average"] = round(float(item.pop("_health_total")) / collaborators, 2) if collaborators else 0
        for key in ("final_points", "estimated_payment", "penalty_points"):
            item[key] = round(float(item[key]), 2)
        regional_summary.append(item)
    regional_summary.sort(key=lambda item: (-float(item["final_points"]), str(item["regional"])))

    total_orders = sum(int(row.get("service_orders_count") or 0) for row in rows)
    scored_orders = sum(int(row.get("scored_service_orders") or 0) for row in rows)
    unscored_orders = sum(int(row.get("unscored_service_orders") or 0) for row in rows)
    manual_review = sum(int(row.get("manual_review_service_orders") or 0) for row in rows)
    alerts: list[str] = []
    if unscored_orders:
        alerts.append(f"{unscored_orders} O.S. sem regra de pontuacao.")
    if manual_review:
        alerts.append(f"{manual_review} O.S. aguardando revisao manual.")
    if any(float(row.get("health_multiplier") or 1) < 1 for row in rows):
        alerts.append("Ha colaboradores com multiplicador de saude abaixo de 1.")

    return {
        "period": {"calculation_run_id": run.id, "reference_month": run.reference_month, "reference_year": run.reference_year, "status": run.status, "updated_at": run.executed_at or run.created_at},
        "total_collaborators": len(rows), "total_regionals": len(regional_summary), "total_service_orders": total_orders, "scored_service_orders": scored_orders,
        "final_points": round(sum(float(row.get("final_points") or 0) for row in rows), 2),
        "estimated_payment": round(sum(float(row.get("estimated_payment") or 0) for row in rows), 2),
        "penalty_points": round(sum(float(row.get("penalty_points") or 0) for row in rows), 2),
        "unscored_service_orders": unscored_orders, "manual_review_service_orders": manual_review,
        "regional_summary": regional_summary, "ranking": [_ranking_item(row, index, None) for index, row in enumerate(rows, start=1)], "alerts": alerts, "message": None,
    }


def _audit_order(order: dict[str, Any]) -> dict[str, Any]:
    return {
        "os_code": str(order.get("os_code") or ""),
        "os_type": str(order.get("os_type") or ""),
        "os_subject": str(order.get("os_subject") or "Sem assunto"),
        "group_name": order.get("group_name"),
        "base_points": float(order.get("base_points") or 0),
        "net_points": float(order.get("net_points") or 0),
        "penalty_points": float(order.get("penalty_points") or 0),
        "status_label": str(order.get("status_label") or "Nao pontuada"),
        "reason": order.get("reason"),
    }


def build_portal_audit(db: Session, user: User) -> dict[str, Any]:
    summary = build_portal_summary(db, user)
    score = summary.get("score")
    collaborator = summary.get("collaborator")
    if not score or not collaborator:
        return {"message": "Auditoria indisponivel sem colaborador vinculado ao usuario."}

    orders = build_portal_orders(db, user, limit=200)
    positive_orders = sorted(
        (order for order in orders if float(order.get("net_points") or 0) > 0),
        key=lambda item: float(item.get("net_points") or 0),
        reverse=True,
    )[:5]
    attention_orders = sorted(
        (
            order
            for order in orders
            if float(order.get("penalty_points") or 0) > 0
            or str(order.get("status_label") or "") in {"Sem regra de pontuacao", "Revisao manual"}
        ),
        key=lambda item: (float(item.get("penalty_points") or 0), -float(item.get("net_points") or 0)),
        reverse=True,
    )[:5]

    def breakdown(label_key: str) -> list[dict[str, Any]]:
        items: dict[str, dict[str, Any]] = {}
        for order in orders:
            label = str(order.get(label_key) or "Sem regra de pontuacao")
            item = items.setdefault(label, {"label": label, "service_orders": 0, "base_points": 0.0, "penalty_points": 0.0, "net_points": 0.0})
            item["service_orders"] += 1
            item["base_points"] += float(order.get("base_points") or 0)
            item["penalty_points"] += float(order.get("penalty_points") or 0)
            item["net_points"] += float(order.get("net_points") or 0)
        return [
            {**item, "base_points": round(float(item["base_points"]), 2), "penalty_points": round(float(item["penalty_points"]), 2), "net_points": round(float(item["net_points"]), 2)}
            for item in sorted(items.values(), key=lambda item: (-float(item["net_points"]), str(item["label"])))[:8]
        ]

    historical_scores = db.execute(
        select(CalculationRun, CollaboratorScore)
        .join(CollaboratorScore, CollaboratorScore.calculation_run_id == CalculationRun.id)
        .where(CollaboratorScore.collaborator_id == int(collaborator["id"]))
        .order_by(desc(CalculationRun.reference_year), desc(CalculationRun.reference_month), desc(CalculationRun.id))
        .limit(6)
    ).all()
    history = [
        {
            "reference_month": run.reference_month,
            "reference_year": run.reference_year,
            "final_points": float(item.final_points),
            "estimated_payment": float(item.estimated_payment),
            "service_orders_count": int(item.service_orders_count),
        }
        for run, item in reversed(historical_scores)
    ]
    return {
        **{key: score.get(key) for key in (
            "gross_points", "penalty_points", "net_points", "health_multiplier", "final_points", "estimated_payment",
            "health_status", "service_orders_count", "scored_service_orders", "unscored_service_orders", "penalized_service_orders",
            "warranty_service_orders", "recurrence_service_orders", "pending_service_orders", "sla_out_service_orders", "manual_review_service_orders",
        )},
        "points_to_next_position": summary.get("next_position_gap"),
        "top_positive_orders": [_audit_order(order) for order in positive_orders],
        "attention_orders": [_audit_order(order) for order in attention_orders],
        "groups": breakdown("group_name"),
        "subjects": breakdown("os_subject"),
        "orders": [_audit_order(order) for order in sorted(orders, key=lambda item: float(item.get("net_points") or 0), reverse=True)],
        "history": history,
        "message": None,
    }
