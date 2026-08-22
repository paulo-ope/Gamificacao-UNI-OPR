from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Collaborator, User
from app.modules.management.models import (
    ALTERNATING_SHIFT_ELIGIBLE_TEAM_MODEL_NAMES,
    ManagementCase,
    ManagementOperationalMember,
)
from app.modules.management.schemas import ManagementOperationalMemberOut, ManagementSummaryOut
from app.modules.operations.models import OperationTeamModel
from app.modules.operations.responsible_regional import resolve_responsible_regional_candidates
from app.services.regional import normalize_regional


def _norm_name(value: str | None) -> str:
    return " ".join((value or "").strip().casefold().split())


def _member_status(member: ManagementOperationalMember, collaborator: Collaborator | None) -> str:
    if not collaborator:
        return "missing"
    if not collaborator.is_registered:
        return "pending"
    if not collaborator.active:
        return "inactive"
    return "registered"


def _member_alerts(member: ManagementOperationalMember, collaborator: Collaborator | None) -> list[str]:
    alerts: list[str] = []
    if member.status == "pending_validation":
        alerts.append("Pendente de validação operacional")
    if not member.supervisor_user_id:
        alerts.append("Sem supervisor vinculado")
    if not member.team_model_id:
        alerts.append("Sem modelo de equipe")
    if not collaborator:
        alerts.append("Sem cadastro na Gamificação")
    elif not collaborator.is_registered:
        alerts.append("Cadastro da Gamificação pendente")
    if member.status == "conflict":
        alerts.append("Conflito de cadastro")
    return alerts


def _find_collaborator(db: Session, responsible_name: str, ixc_employee_id: int | None) -> Collaborator | None:
    if ixc_employee_id is not None:
        collaborator = db.scalar(select(Collaborator).where(Collaborator.ixc_employee_id == ixc_employee_id))
        if collaborator:
            return collaborator
    normalized = _norm_name(responsible_name)
    if not normalized:
        return None
    return db.scalar(select(Collaborator).where(func.lower(Collaborator.name) == normalized))


def default_shift_pattern_for_team_model(team_model: OperationTeamModel | None) -> tuple[str, int, int] | None:
    """A escala alternada (dia sim, dia não) é intrínseca ao modelo de equipe 12x36 - pedido do
    usuário em 2026-08-22: "não seja uma config a parte", pra ninguém precisar lembrar de ligar
    manualmente pra cada colaborador novo. Devolve `(pattern, cycle_on, cycle_off)` quando o
    modelo é elegível, `None` caso contrário - quem chama só aplica se o membro ainda não tiver
    um `shift_pattern` explícito.

    A data-âncora (qual dia específico cada colaborador trabalha) continua de fora de propósito -
    decisão do usuário em 2026-08-21: como o 12x36 precisa de 2 turmas alternadas pra cobertura
    diária, não dá pra adivinhar em qual turma cada pessoa está, isso exige uma decisão manual
    (ou a sugestão de `cases.suggest_shift_pattern`, que o supervisor ainda confirma)."""
    if team_model is None or team_model.name not in ALTERNATING_SHIFT_ELIGIBLE_TEAM_MODEL_NAMES:
        return None
    return "alternating", 1, 1


def refresh_operational_members(db: Session) -> int:
    """Cria/atualiza candidatos de estrutura operacional sem apagar ajustes manuais.

    A fonte principal é a configuração da Operação Analítica. O histórico de O.S. entra como
    complemento para encontrar responsáveis operacionais que ainda não foram validados.
    """

    now = datetime.now(timezone.utc)
    touched = 0
    team_models_by_id = {model.id: model for model in db.scalars(select(OperationTeamModel)).all()}

    for candidate in resolve_responsible_regional_candidates(db):
        responsible_name = candidate.responsible_name.strip()
        regional = normalize_regional(candidate.regional)
        if not responsible_name or regional == "NAO IDENTIFICADO":
            continue
        member = db.scalar(
            select(ManagementOperationalMember).where(
                ManagementOperationalMember.responsible_name == responsible_name,
                ManagementOperationalMember.regional == regional,
            )
        )
        collaborator = _find_collaborator(db, responsible_name, candidate.ixc_employee_id)
        status = "pending_validation"
        if candidate.team_model_id and not collaborator:
            status = "without_supervisor"
        if member:
            if member.team_model_id is None and candidate.team_model_id is not None:
                member.team_model_id = candidate.team_model_id
                if member.shift_pattern is None:
                    defaults = default_shift_pattern_for_team_model(team_models_by_id.get(candidate.team_model_id))
                    if defaults:
                        member.shift_pattern, member.shift_cycle_days_on, member.shift_cycle_days_off = defaults
            if member.ixc_employee_id is None and candidate.ixc_employee_id is not None:
                member.ixc_employee_id = candidate.ixc_employee_id
            if member.collaborator_id is None and collaborator:
                member.collaborator_id = collaborator.id
            if member.supervisor_user_id is None and collaborator and collaborator.supervisor_user_id is not None:
                member.supervisor_user_id = collaborator.supervisor_user_id
            if collaborator and collaborator.structure_status == "outside_operation" and member.status not in {"inactive", "outside_operation"}:
                member.status = "outside_operation"
            elif collaborator and collaborator.structure_status == "validated" and member.status == "pending_validation":
                member.status = "without_team_model" if member.team_model_id is None else "validated_operation"
            if candidate.last_order_at and (member.last_order_at is None or candidate.last_order_at > member.last_order_at):
                member.last_order_at = candidate.last_order_at
            member.updated_at = now
        else:
            member_supervisor_id = collaborator.supervisor_user_id if collaborator and collaborator.supervisor_user_id else None
            if collaborator and collaborator.structure_status == "outside_operation":
                status = "outside_operation"
            elif collaborator and collaborator.structure_status == "validated":
                status = "without_team_model" if candidate.team_model_id is None else "validated_operation"
            shift_defaults = default_shift_pattern_for_team_model(team_models_by_id.get(candidate.team_model_id))
            db.add(
                ManagementOperationalMember(
                    responsible_name=responsible_name,
                    regional=regional,
                    team_model_id=candidate.team_model_id,
                    supervisor_user_id=member_supervisor_id,
                    ixc_employee_id=candidate.ixc_employee_id,
                    collaborator_id=collaborator.id if collaborator else None,
                    last_order_at=candidate.last_order_at,
                    status=status,
                    source=candidate.source if candidate.source != "order_history" else "orders",
                    shift_pattern=shift_defaults[0] if shift_defaults else None,
                    shift_cycle_days_on=shift_defaults[1] if shift_defaults else None,
                    shift_cycle_days_off=shift_defaults[2] if shift_defaults else None,
                )
            )
            touched += 1
    db.flush()
    return touched


class ShiftPatternNotEligibleError(Exception):
    """Levantado quando alguém tenta ligar a escala alternada (`shift_pattern="alternating"`) num
    colaborador cujo modelo de equipe não é 12x36 - pedido do usuário em 2026-08-21: só quem é
    12x36 pode ter dia sim/dia não, os demais modelos já são comercial (segunda a sábado) e não
    devem poder sair dessa régua."""


def validate_shift_pattern_for_team_model(shift_pattern: str | None, team_model: OperationTeamModel | None) -> None:
    if shift_pattern != "alternating":
        return
    if team_model is None or team_model.name not in ALTERNATING_SHIFT_ELIGIBLE_TEAM_MODEL_NAMES:
        raise ShiftPatternNotEligibleError()


class MemberAlreadyClaimedError(Exception):
    """Levantado quando alguém tenta reivindicar um colaborador que já tem outro supervisor -
    "roubar" colaborador de outro supervisor não é o objetivo desta ação (ver `claim_member`);
    reatribuir deliberadamente continua sendo tarefa de quem tem `management:manage_structure`."""


def claim_member(db: Session, *, member: ManagementOperationalMember, claimer: User) -> ManagementOperationalMember:
    """Reivindica um colaborador operacional ainda SEM supervisor pra base do próprio supervisor/
    gerente de base que chama - pedido do usuário em 2026-08-20: montar o organograma de campo
    sem depender da matriz. Só funciona pra quem está sem supervisor (ou já é o próprio claimer);
    já ter outro supervisor exige a ação administrativa de `management:manage_structure`, não esta."""
    if member.supervisor_user_id is not None and member.supervisor_user_id != claimer.id:
        raise MemberAlreadyClaimedError()
    member.supervisor_user_id = claimer.id
    # Mesma transição que `refresh_operational_members` já usa ao sair de "pendente" - sem
    # supervisor era exatamente o que bloqueava a validação.
    if member.status in {"pending_validation", "without_supervisor"}:
        member.status = "without_team_model" if member.team_model_id is None else "validated_operation"
    member.updated_at = datetime.now(timezone.utc)
    db.flush()
    return member


def member_out(member: ManagementOperationalMember) -> ManagementOperationalMemberOut:
    collaborator = member.collaborator
    return ManagementOperationalMemberOut(
        id=member.id,
        collaborator_id=member.collaborator_id,
        collaborator_name=collaborator.name if collaborator else None,
        collaborator_is_registered=collaborator.is_registered if collaborator else None,
        collaborator_employee_type=collaborator.employee_type if collaborator else None,
        collaborator_team_type=collaborator.team_type if collaborator else None,
        collaborator_structure_status=collaborator.structure_status if collaborator else None,
        collaborator_supervisor_user_id=collaborator.supervisor_user_id if collaborator else None,
        collaborator_supervisor_name=collaborator.supervisor_user.name if collaborator and collaborator.supervisor_user else None,
        collaborator_regional=collaborator.regional if collaborator else None,
        gamification_status=_member_status(member, collaborator),
        ixc_employee_id=member.ixc_employee_id,
        responsible_name=member.responsible_name,
        regional=member.regional,
        supervisor_user_id=member.supervisor_user_id,
        supervisor_name=member.supervisor.name if member.supervisor else None,
        team_model_id=member.team_model_id,
        team_model_name=member.team_model.name if member.team_model else None,
        status=member.status,
        source=member.source,
        is_active=member.is_active,
        notes=member.notes,
        shift_pattern=member.shift_pattern,
        shift_cycle_days_on=member.shift_cycle_days_on,
        shift_cycle_days_off=member.shift_cycle_days_off,
        shift_anchor_date=member.shift_anchor_date,
        last_order_at=member.last_order_at,
        alerts=_member_alerts(member, collaborator),
        created_at=member.created_at,
        updated_at=member.updated_at,
    )


def summarize_members(members: list[ManagementOperationalMember], open_cases: int = 0, overdue_cases: int = 0) -> ManagementSummaryOut:
    status_counts = Counter(member.status for member in members)
    without_gamification = sum(1 for member in members if not member.collaborator or not member.collaborator.is_registered)
    return ManagementSummaryOut(
        total_members=len(members),
        active_members=sum(1 for member in members if member.is_active and member.status not in {"outside_operation", "inactive"}),
        pending_validation=status_counts["pending_validation"],
        without_supervisor=sum(1 for member in members if not member.supervisor_user_id),
        without_team_model=sum(1 for member in members if not member.team_model_id),
        without_gamification=without_gamification,
        conflicts=status_counts["conflict"],
        open_cases=open_cases,
        overdue_cases=overdue_cases,
    )


def visible_member_filters(
    regional: str | None = None,
    supervisor_user_id: int | None = None,
    status: str | None = None,
    search: str | None = None,
    collaborator_regional: str | None = None,
):
    filters = []
    if regional:
        filters.append(ManagementOperationalMember.regional == normalize_regional(regional))
    if supervisor_user_id:
        filters.append(ManagementOperationalMember.supervisor_user_id == supervisor_user_id)
    if status:
        filters.append(ManagementOperationalMember.status == status)
    if collaborator_regional:
        # "Regional de origem" (Collaborator.regional) - distinta da regional operacional acima
        # (onde a produção foi apurada). Subquery em vez de join, pra não mudar a forma como o
        # restante da consulta já é montada (ver `list_members`/`dashboard`, router.py).
        filters.append(
            ManagementOperationalMember.collaborator_id.in_(
                select(Collaborator.id).where(Collaborator.regional == normalize_regional(collaborator_regional))
            )
        )
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                ManagementOperationalMember.responsible_name.ilike(pattern),
                ManagementOperationalMember.regional.ilike(pattern),
            )
        )
    return filters


def list_supervisors(db: Session) -> list[User]:
    return db.scalars(
        select(User)
        .where(User.active.is_(True))
        .where(
            or_(
                User.role.in_(["admin", "operator", "regional_manager_viewer"]),
                User.managed_regionals != [],
                User.managed_regional.is_not(None),
            )
        )
        .order_by(User.name.asc())
    ).all()
