from __future__ import annotations

import unicodedata
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.core.security import permissions_for_role
from app.models import (
    CalculationRun,
    Collaborator,
    CollaboratorScore,
    DiagnosisPenaltyRule,
    RecurrenceClassificationRule,
    ScoringGroup,
    ScoringSubjectRule,
    SlaPenaltyRule,
    User,
)
from app.services.calculation import serialize_run
from app.services.regional import (
    effective_managed_regionals,
    effective_managed_regionals_grouped,
    normalize_regional_grouped as normalize_regional,
)
from app.services.scoring_detail import explain_orders, period_orders


def _serialize_portal_user(user: User) -> dict[str, Any]:
    """`PortalSummaryOut.user` é um `UserOut`, mas o valor embutido aqui vinha sendo a instância
    crua do ORM (from_attributes=True) - permissions/collaborator_name não são colunas reais, então
    o pydantic sempre caía no default do schema ([]/None) em vez de calcular de verdade. Isso
    quebrava silenciosamente qualquer tela que decidisse o que mostrar a partir de
    `summary.user.permissions` (ex: aba "Visão geral" do portal para admin, e agora "Minha equipe"
    pro gestor regional - nenhuma das duas jamais apareceria, já que a lista vinha sempre vazia)."""
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "active": user.active,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "permissions": sorted(permissions_for_role(user.role)),
        "collaborator_id": user.collaborator_id,
        "collaborator_name": user.collaborator.name if user.collaborator else None,
        "managed_regional": user.managed_regional,
        "managed_regionals": effective_managed_regionals(user.managed_regional, user.managed_regionals),
    }


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    without_accents = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(without_accents.lower().strip().split())


def _email_identity(email: str) -> str:
    return _normalize_text(email.split("@", 1)[0].replace(".", " ").replace("_", " ").replace("-", " "))


def _portal_run(
    db: Session,
    reference_month: int | None = None,
    reference_year: int | None = None,
) -> CalculationRun | None:
    statement = select(CalculationRun).options(
        selectinload(CalculationRun.scores).selectinload(CollaboratorScore.collaborator)
    )
    if reference_month is not None and reference_year is not None:
        statement = statement.where(
            CalculationRun.reference_month == reference_month,
            CalculationRun.reference_year == reference_year,
        ).order_by(desc(CalculationRun.created_at), desc(CalculationRun.id))
    else:
        statement = statement.order_by(desc(CalculationRun.created_at), desc(CalculationRun.id))
    return db.scalar(statement.limit(1))


def _latest_run(db: Session) -> CalculationRun | None:
    return _portal_run(db)


def _score_rows(db: Session, run: CalculationRun) -> list[dict[str, Any]]:
    registered_collaborator_ids = set(
        db.scalars(
            select(Collaborator.id).where(
                Collaborator.active.is_(True),
                Collaborator.is_registered.is_(True),
            )
        )
    )
    return [
        row
        for row in serialize_run(run, db).get("scores", [])
        if int(row.get("collaborator_id") or 0) in registered_collaborator_ids
    ]


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
        "balance_adjustment_points",
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


def _performance_band(final_points: float, average_points: float) -> str:
    if average_points <= 0:
        return "Sem faixa"
    if final_points >= average_points * 1.15:
        return "Acima da faixa"
    if final_points >= average_points * 0.7:
        return "Na faixa"
    return "Abaixo da faixa"


def _ranking_item(row: dict[str, Any], position: int, current_id: int | None, average_points: float | None = None) -> dict[str, Any]:
    collaborator_id = int(row.get("collaborator_id") or 0)
    final_points = float(row.get("final_points") or 0)
    average = float(average_points or 0)
    return {
        "position": position,
        "collaborator_id": collaborator_id,
        "collaborator_name": str(row.get("collaborator_name") or "Colaborador"),
        "role": row.get("role"),
        "regional": str(row.get("regional") or "Sem regional"),
        "final_points": final_points,
        "estimated_payment": float(row.get("estimated_payment") or 0),
        "service_orders_count": int(row.get("service_orders_count") or 0),
        "scored_service_orders": int(row.get("scored_service_orders") or 0),
        "penalty_points": float(row.get("penalty_points") or 0),
        "health_multiplier": float(row.get("health_multiplier") or 1),
        "health_status": row.get("health_status"),
        "sla_out_service_orders": int(row.get("sla_out_service_orders") or 0),
        "recurrence_service_orders": int(row.get("recurrence_service_orders") or 0),
        "unscored_service_orders": int(row.get("unscored_service_orders") or 0),
        "manual_review_service_orders": int(row.get("manual_review_service_orders") or 0),
        "points_to_average": round(max(0, average - final_points), 2) if average > 0 else None,
        "performance_band": _performance_band(final_points, average),
        "is_current_user": collaborator_id == current_id,
    }


def build_portal_summary(
    db: Session,
    user: User,
    reference_month: int | None = None,
    reference_year: int | None = None,
) -> dict[str, Any]:
    run = _portal_run(db, reference_month, reference_year)
    if not run:
        return {
            "user": _serialize_portal_user(user),
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
    # O portal mostra o mesmo SLA do fechamento oficial, vindo do snapshot da execução.
    # O ranking continua ocultando inativos, mas eles fazem parte do SLA regional calculado.
    regional_sla_rows = [
        row
        for row in serialize_run(run, db).get("scores", [])
        if current_regional and normalize_regional(str(row.get("regional") or "")) == current_regional
    ]
    regional_service_orders = sum(int(row.get("service_orders_count") or 0) for row in regional_sla_rows)
    regional_sla_out_service_orders = sum(int(row.get("sla_out_service_orders") or 0) for row in regional_sla_rows)
    regional_sla_rate = round(
        ((regional_service_orders - regional_sla_out_service_orders) / regional_service_orders) * 100,
        2,
    ) if regional_service_orders else None
    next_position_gap = None
    if current and regional_position and regional_position > 1:
        next_row = regional_rows[regional_position - 2]
        next_position_gap = max(0, round(float(next_row.get("final_points") or 0) - float(current.get("final_points") or 0), 2))

    return {
        "user": _serialize_portal_user(user),
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
        "regional_service_orders": regional_service_orders,
        "regional_sla_out_service_orders": regional_sla_out_service_orders,
        "regional_sla_rate": regional_sla_rate,
        "general_position": general_position,
        "general_total": len(sorted_rows),
        "next_position_gap": next_position_gap,
        "ranking": [_ranking_item(row, index, current_id) for index, row in enumerate(regional_rows, start=1)],
        "message": None if current else "Nao foi encontrado um colaborador vinculado ao seu usuario.",
    }


def _order_label(detail: dict[str, Any]) -> tuple[str, str | None]:
    reasons = detail.get("reasons") or detail.get("penalty_reasons") or []
    technical_reason_prefixes = ("SLA original importado:", "SLA normalizado:", "Assunto vinculado ao grupo")
    visible_reasons = [
        str(item)
        for item in reasons
        if not str(item).startswith(technical_reason_prefixes)
    ] if isinstance(reasons, list) else []
    reason = "; ".join(visible_reasons[:2]) or None
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


def build_portal_orders(
    db: Session,
    user: User,
    limit: int = 80,
    reference_month: int | None = None,
    reference_year: int | None = None,
) -> list[dict[str, Any]]:
    run = _portal_run(db, reference_month, reference_year)
    if not run:
        return []
    summary = build_portal_summary(db, user, reference_month, reference_year)
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
                "customer_name": order.customer_name,
                "group_name": detail.get("group_name"),
                "diagnosis": order.diagnosis,
                "status": order.status,
                "sla_status": order.sla_status,
                "sla_status_normalized": detail.get("sla_status_normalized") or "NAO_IDENTIFICADO",
                "base_points": float(detail.get("base_points") or 0),
                "penalty_points": float(detail.get("penalty_points") or 0),
                "net_points": float(detail.get("net_points") or 0),
                "status_label": status_label,
                "reason": reason,
                "diagnosis_action_type": detail.get("diagnosis_action_type"),
                "diagnosis_penalty_reason": detail.get("diagnosis_penalty_reason"),
                "recurrence_related_os_code": detail.get("recurrence_related_os_code"),
                "recurrence_days_between": detail.get("recurrence_days_between"),
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
                "point_source": "Valor padrão do grupo" if item.use_group_default else "Valor específico deste assunto",
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


def build_portal_team_summary(db: Session, user: User) -> dict[str, Any]:
    """Resumo da equipe de uma ou mais regionais, pro perfil "regional_manager_viewer" - esse
    usuário não representa um colaborador individual (users.managed_regional/managed_regionals em
    vez de users.collaborator_id), então não passa por _resolve_score: filtra as pontuações de todo
    mundo daquelas regionais direto, igual o bloco por-regional de build_portal_overview, mas
    escopado às regionais vinculadas a este gestor (uma ou várias - migration 20260718_0011)."""
    run = _latest_run(db)
    # Agrupado (São Miguel do Guaporé, Seringueiras e São Francisco do Guaporé como uma regional só)
    # porque compara contra `row["regional"]`, que já sai agrupado de `_score_rows`/scoring_detail.
    target_regionals = effective_managed_regionals_grouped(user.managed_regional, user.managed_regionals)
    if not run:
        return {"period": {}, "regional": ", ".join(target_regionals) or None, "regionals": target_regionals, "message": "Nenhum fechamento foi calculado ainda."}

    if not target_regionals:
        return {
            "period": {
                "calculation_run_id": run.id,
                "reference_month": run.reference_month,
                "reference_year": run.reference_year,
                "status": run.status,
                "updated_at": run.executed_at or run.created_at,
            },
            "regional": None,
            "regionals": [],
            "message": "Nenhuma regional foi vinculada ao seu usuario.",
        }

    target_regional_set = set(target_regionals)
    rows = [row for row in _score_rows(db, run) if normalize_regional(str(row.get("regional") or "")) in target_regional_set]
    sorted_rows = sorted(rows, key=lambda item: float(item.get("final_points") or 0), reverse=True)

    collaborators = len(sorted_rows)
    service_orders = sum(int(row.get("service_orders_count") or 0) for row in sorted_rows)
    recurrence_orders = sum(int(row.get("recurrence_service_orders") or 0) for row in sorted_rows)
    sla_out_orders = sum(int(row.get("sla_out_service_orders") or 0) for row in sorted_rows)
    final_points = round(sum(float(row.get("final_points") or 0) for row in sorted_rows), 2)
    average_points = round(final_points / collaborators, 2) if collaborators else 0
    totals = {
        "regional": ", ".join(target_regionals),
        "collaborators": collaborators,
        "service_orders": service_orders,
        "scored_service_orders": sum(int(row.get("scored_service_orders") or 0) for row in sorted_rows),
        "final_points": final_points,
        "estimated_payment": round(sum(float(row.get("estimated_payment") or 0) for row in sorted_rows), 2),
        "penalty_points": round(sum(float(row.get("penalty_points") or 0) for row in sorted_rows), 2),
        "health_average": round(sum(float(row.get("health_multiplier") or 0) for row in sorted_rows) / collaborators, 2) if collaborators else 0,
        "sla_out_service_orders": sla_out_orders,
        "recurrence_service_orders": recurrence_orders,
        "unscored_service_orders": sum(int(row.get("unscored_service_orders") or 0) for row in sorted_rows),
        "manual_review_service_orders": sum(int(row.get("manual_review_service_orders") or 0) for row in sorted_rows),
        "sla_rate": round(((service_orders - sla_out_orders) / service_orders) * 100, 2) if service_orders else 0,
        "recurrence_rate": round((recurrence_orders / service_orders) * 100, 2) if service_orders else 0,
    }
    ranking = [_ranking_item(row, index, None, average_points=average_points) for index, row in enumerate(sorted_rows, start=1)]
    attention = []
    for item in ranking:
        reasons = []
        if item["performance_band"] == "Abaixo da faixa":
            reasons.append("pontuação abaixo da faixa")
        if float(item["health_multiplier"] or 1) < 1:
            reasons.append("saúde operacional abaixo do neutro")
        if int(item["sla_out_service_orders"] or 0) > 0:
            reasons.append("O.S. fora do SLA")
        if int(item["unscored_service_orders"] or 0) > 0 or int(item["manual_review_service_orders"] or 0) > 0:
            reasons.append("pendências de regra ou revisão")
        if reasons:
            attention.append(
                {
                    **item,
                    "attention_reason": ", ".join(reasons),
                    "target_gap": round(float(item.get("points_to_average") or 0), 2),
                }
            )
    attention.sort(
        key=lambda item: (
            item["performance_band"] != "Abaixo da faixa",
            -int(item["sla_out_service_orders"] or 0),
            -float(item["target_gap"] or 0),
        )
    )
    bands = []
    band_meta = {
        "Acima da faixa": "15% ou mais acima da média regional.",
        "Na faixa": "Entre 70% da média e 15% acima dela.",
        "Abaixo da faixa": "Abaixo de 70% da média regional.",
        "Sem faixa": "Sem média suficiente para comparar.",
    }
    for label in ("Acima da faixa", "Na faixa", "Abaixo da faixa", "Sem faixa"):
        items = [item for item in ranking if item.get("performance_band") == label]
        if not items and label != "Sem faixa":
            continue
        bands.append(
            {
                "label": label,
                "collaborators": len(items),
                "min_points": round(min((float(item["final_points"]) for item in items), default=0), 2),
                "max_points": round(max((float(item["final_points"]) for item in items), default=0), 2),
                "description": band_meta[label],
            }
        )

    historical_runs = db.scalars(
        select(CalculationRun)
        .order_by(desc(CalculationRun.reference_year), desc(CalculationRun.reference_month), desc(CalculationRun.id))
        .limit(12)
    ).all()
    history = []
    seen_periods: set[tuple[int, int]] = set()
    for historical_run in historical_runs:
        period = (historical_run.reference_year, historical_run.reference_month)
        if period in seen_periods:
            continue
        seen_periods.add(period)
        period_rows = [
            row
            for row in _score_rows(db, historical_run)
            if normalize_regional(str(row.get("regional") or "")) in target_regional_set
        ]
        period_collaborators = len(period_rows)
        period_orders = sum(int(row.get("service_orders_count") or 0) for row in period_rows)
        period_sla_out = sum(int(row.get("sla_out_service_orders") or 0) for row in period_rows)
        period_recurrence = sum(int(row.get("recurrence_service_orders") or 0) for row in period_rows)
        history.append(
            {
                "reference_month": historical_run.reference_month,
                "reference_year": historical_run.reference_year,
                "collaborators": period_collaborators,
                "service_orders": period_orders,
                "sla_out_service_orders": period_sla_out,
                "recurrence_service_orders": period_recurrence,
                "final_points": round(sum(float(row.get("final_points") or 0) for row in period_rows), 2),
                "estimated_payment": round(sum(float(row.get("estimated_payment") or 0) for row in period_rows), 2),
                "health_average": round(sum(float(row.get("health_multiplier") or 0) for row in period_rows) / period_collaborators, 2)
                if period_collaborators
                else 0,
                "sla_rate": round(((period_orders - period_sla_out) / period_orders) * 100, 2) if period_orders else 0,
                "recurrence_rate": round((period_recurrence / period_orders) * 100, 2) if period_orders else 0,
            }
        )
        if len(history) >= 6:
            break
    history.reverse()
    alerts: list[str] = []
    below_count = sum(1 for item in ranking if item.get("performance_band") == "Abaixo da faixa")
    if below_count:
        alerts.append(f"{below_count} colaborador(es) abaixo da faixa da regional.")
    if sla_out_orders:
        alerts.append(f"{sla_out_orders} O.S. fora do SLA no fechamento atual.")
    if totals["manual_review_service_orders"]:
        alerts.append(f"{totals['manual_review_service_orders']} O.S. aguardando revisão manual.")

    return {
        "period": {
            "calculation_run_id": run.id,
            "reference_month": run.reference_month,
            "reference_year": run.reference_year,
            "status": run.status,
            "updated_at": run.executed_at or run.created_at,
        },
        "regional": ", ".join(target_regionals),
        "regionals": target_regionals,
        "totals": totals,
        "ranking": ranking,
        "attention": attention[:8],
        "history": history,
        "bands": bands,
        "alerts": alerts,
        "message": None if sorted_rows else "Nenhum colaborador com pontuacao encontrado nesta regional no periodo.",
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
        "customer_name": order.get("customer_name"),
        "group_name": order.get("group_name"),
        "base_points": float(order.get("base_points") or 0),
        "net_points": float(order.get("net_points") or 0),
        "penalty_points": float(order.get("penalty_points") or 0),
        "status_label": str(order.get("status_label") or "Nao pontuada"),
        "sla_status_normalized": str(order.get("sla_status_normalized") or "NAO_IDENTIFICADO"),
        "reason": order.get("reason"),
        "diagnosis_action_type": order.get("diagnosis_action_type"),
        "diagnosis_penalty_reason": order.get("diagnosis_penalty_reason"),
        "recurrence_related_os_code": order.get("recurrence_related_os_code"),
        "recurrence_days_between": order.get("recurrence_days_between"),
    }


def build_portal_audit(
    db: Session,
    user: User,
    reference_month: int | None = None,
    reference_year: int | None = None,
) -> dict[str, Any]:
    summary = build_portal_summary(db, user, reference_month, reference_year)
    score = summary.get("score")
    collaborator = summary.get("collaborator")
    if not score or not collaborator:
        return {"message": "Auditoria indisponivel sem colaborador vinculado ao usuario."}

    orders = build_portal_orders(db, user, limit=200, reference_month=reference_month, reference_year=reference_year)
    sla_on_time_service_orders = sum(1 for order in orders if order.get("sla_status_normalized") == "NO_PRAZO")
    sla_out_service_orders = sum(1 for order in orders if order.get("sla_status_normalized") == "FORA_DO_PRAZO")
    sla_unidentified_service_orders = max(0, len(orders) - sla_on_time_service_orders - sla_out_service_orders)
    sla_measured_service_orders = sla_on_time_service_orders + sla_out_service_orders
    sla_rate = round((sla_on_time_service_orders / sla_measured_service_orders) * 100, 1) if sla_measured_service_orders else None
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
        .limit(120)
    ).all()
    history = []
    seen_periods: set[tuple[int, int]] = set()
    for run, item in historical_scores:
        period = (run.reference_year, run.reference_month)
        if period in seen_periods:
            continue
        seen_periods.add(period)
        history.append(
            {
                "reference_month": run.reference_month,
                "reference_year": run.reference_year,
                "final_points": float(item.final_points),
                "estimated_payment": float(item.estimated_payment),
                "service_orders_count": int(item.service_orders_count),
            }
        )
        if len(history) == 12:
            break
    history.reverse()
    return {
        **{key: score.get(key) for key in (
            "gross_points", "penalty_points", "net_points", "health_multiplier", "final_points", "estimated_payment",
            "balance_adjustment_points",
            "health_status", "service_orders_count", "scored_service_orders", "unscored_service_orders", "penalized_service_orders",
            "warranty_service_orders", "recurrence_service_orders", "pending_service_orders", "sla_out_service_orders", "manual_review_service_orders",
        )},
        "sla_on_time_service_orders": sla_on_time_service_orders,
        "sla_unidentified_service_orders": sla_unidentified_service_orders,
        "sla_rate": sla_rate,
        "points_to_next_position": summary.get("next_position_gap"),
        "top_positive_orders": [_audit_order(order) for order in positive_orders],
        "attention_orders": [_audit_order(order) for order in attention_orders],
        "groups": breakdown("group_name"),
        "subjects": breakdown("os_subject"),
        "orders": [_audit_order(order) for order in sorted(orders, key=lambda item: float(item.get("net_points") or 0), reverse=True)],
        "history": history,
        "message": None,
    }
