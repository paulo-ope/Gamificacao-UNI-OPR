from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.core.security import is_admin_user
from app.models import CALCULATION_RUN_STATUSES, CalculationRun, CollaboratorScore, LeadershipProfile, LeadershipRoleProfile, User
from app.services.audit_log import snapshot
from app.services.leadership_bonus import serialize_profile, serialize_role_profile
from app.services.regional import normalize_regional


ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"review", "cancelled"},
    "review": {"approved", "cancelled"},
    "approved": {"paid", "cancelled"},
    "paid": set(),
    "cancelled": set(),
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def normalize_run_status(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized not in CALCULATION_RUN_STATUSES:
        raise HTTPException(status_code=422, detail="Status de fechamento inválido.")
    return normalized


def serialize_run_status(run: CalculationRun) -> dict[str, Any]:
    return {
        "status": run.status,
        "status_changed_at": run.status_changed_at,
        "status_changed_by": run.status_changed_by,
        "status_note": run.status_note,
        "approved_at": run.approved_at,
        "approved_by": run.approved_by,
        "paid_at": run.paid_at,
        "paid_by": run.paid_by,
        "executed_at": run.executed_at,
        "executed_by": run.executed_by,
    }


def ensure_status_transition_allowed(current_status: str, next_status: str) -> None:
    current = normalize_run_status(current_status)
    target = normalize_run_status(next_status)
    if current == target:
        # Estados terminais nao aceitam nem o reenvio do proprio status: re-marcar como "pago"
        # re-executaria o consumo de saldo de pontos contra um fechamento ja encerrado.
        if current in {"paid", "cancelled"}:
            raise HTTPException(
                status_code=409,
                detail=f"Fechamento já está em '{current}' e não pode ser alterado.",
            )
        return
    if target not in ALLOWED_STATUS_TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=409,
            detail=f"Transição de status inválida: {current} -> {target}.",
        )


def ensure_status_change_permission(user: User, next_status: str) -> None:
    target = normalize_run_status(next_status)
    if target in {"approved", "paid"} and not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Somente administrador pode aprovar ou marcar como pago.")


def ensure_no_overlapping_paid_period(db: Session, run: CalculationRun) -> None:
    """Impede marcar como PAGO um fechamento cujos colaboradores ja foram pagos para o
    mesmo periodo (mes/ano) por OUTRO CalculationRun - cobre tanto a sobreposicao entre
    um fechamento agregado (regional=None) e um fechamento regional especifico quanto uma
    revisao (allow_paid_revision) que seria marcada como paga depois do fechamento original.
    Sem esta trava, o mesmo colaborador pode ser pago duas vezes no mesmo mes via dois
    CalculationRun distintos, porque nao existe unique constraint em (mes, ano, regional)."""
    db.flush()
    collaborator_ids = {score.collaborator_id for score in run.scores}
    if not collaborator_ids:
        return

    rows = db.execute(
        select(CollaboratorScore.collaborator_id, CalculationRun.id)
        .join(CalculationRun, CalculationRun.id == CollaboratorScore.calculation_run_id)
        .where(CalculationRun.reference_month == run.reference_month)
        .where(CalculationRun.reference_year == run.reference_year)
        .where(CalculationRun.status == "paid")
        .where(CalculationRun.id != run.id)
        .where(CollaboratorScore.collaborator_id.in_(collaborator_ids))
    ).all()

    if rows:
        overlapping_collaborators = {row[0] for row in rows}
        conflicting_run_ids = sorted({row[1] for row in rows})
        run_list = ", ".join(f"#{rid}" for rid in conflicting_run_ids)
        raise HTTPException(
            status_code=409,
            detail=(
                f"{len(overlapping_collaborators)} colaborador(es) deste fechamento ja foram pagos para "
                f"{run.reference_month:02d}/{run.reference_year} pelo(s) fechamento(s) {run_list}. "
                "Não é possível marcar como pago para evitar pagamento em duplicidade. "
                "Cancele este fechamento ou reconcilie com o outro antes de continuar."
            ),
        )


def update_run_status(db: Session, run: CalculationRun, next_status: str, user: User, note: str | None = None) -> CalculationRun:
    current_status = normalize_run_status(run.status)
    target_status = normalize_run_status(next_status)
    ensure_status_transition_allowed(current_status, target_status)
    ensure_status_change_permission(user, target_status)
    if target_status == "paid":
        ensure_no_overlapping_paid_period(db, run)

    changed_at = now_utc()
    run.status = target_status
    run.status_changed_at = changed_at
    run.status_changed_by = user.id
    run.status_note = note.strip() if note else None

    if target_status == "approved":
        run.approved_at = changed_at
        run.approved_by = user.id
    if target_status == "paid":
        run.paid_at = changed_at
        run.paid_by = user.id

    return run


def build_rule_snapshot(db: Session) -> dict[str, Any]:
    from app.services.gamification_config import serialize_current_config

    config = serialize_current_config(db)
    role_profiles = list(
        db.scalars(
            select(LeadershipRoleProfile)
            .options(selectinload(LeadershipRoleProfile.leaders))
            .order_by(LeadershipRoleProfile.name.asc())
        )
    )
    leadership_profiles = list(
        db.scalars(
            select(LeadershipProfile)
            .options(selectinload(LeadershipProfile.role_profile), selectinload(LeadershipProfile.regionals))
            .order_by(LeadershipProfile.role_type.asc(), LeadershipProfile.name.asc())
        )
    )

    return snapshot(
        {
            "captured_at": now_utc(),
            "config": config,
            "leadership_role_profiles": [serialize_role_profile(profile) for profile in role_profiles],
            "leadership_profiles": [serialize_profile(profile) for profile in leadership_profiles],
        }
    )


def find_paid_run_for_period(
    db: Session,
    reference_month: int,
    reference_year: int,
    regional: str | None,
) -> CalculationRun | None:
    stmt = (
        select(CalculationRun)
        .where(CalculationRun.reference_month == reference_month)
        .where(CalculationRun.reference_year == reference_year)
        .where(CalculationRun.status == "paid")
    )
    if regional is None:
        stmt = stmt.where(CalculationRun.regional.is_(None))
    else:
        stmt = stmt.where(CalculationRun.regional == regional)
    return db.scalar(stmt.order_by(desc(CalculationRun.created_at), desc(CalculationRun.id)).limit(1))


def find_paid_run_for_service_order_context(
    db: Session,
    reference_date: datetime | None,
    regional: str | None,
) -> CalculationRun | None:
    if reference_date is None:
        return None
    normalized_regional = normalize_regional(regional) if regional else None
    direct = find_paid_run_for_period(db, reference_date.month, reference_date.year, normalized_regional)
    if direct:
        return direct
    if normalized_regional is not None:
        return find_paid_run_for_period(db, reference_date.month, reference_date.year, None)
    return None


def ensure_period_not_paid(
    db: Session,
    reference_month: int,
    reference_year: int,
    regional: str | None,
    allow_revision: bool = False,
) -> CalculationRun | None:
    db.flush()
    paid_run = find_paid_run_for_period(db, reference_month, reference_year, regional)
    if paid_run and not allow_revision:
        raise HTTPException(
            status_code=409,
            detail="Este período já está marcado como pago. Para revisar, crie uma nova revisão em rascunho sem alterar o fechamento pago original.",
        )
    return paid_run
