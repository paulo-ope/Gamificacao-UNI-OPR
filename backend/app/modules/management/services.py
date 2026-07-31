from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Collaborator, User
from app.modules.management.models import ManagementCase, ManagementOperationalMember
from app.modules.management.schemas import ManagementOperationalMemberOut, ManagementSummaryOut
from app.modules.operations.models import OperationOrder, OperationResponsibleAssignment, OperationTeamModel
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


def refresh_operational_members(db: Session) -> int:
    """Cria/atualiza candidatos de estrutura operacional sem apagar ajustes manuais.

    A fonte principal é a configuração da Operação Analítica. O histórico de O.S. entra como
    complemento para encontrar responsáveis operacionais que ainda não foram validados.
    """

    now = datetime.now(timezone.utc)
    touched = 0

    last_orders = {
        (row.responsible_name, row.regional): row
        for row in db.execute(
            select(
                OperationOrder.responsible.label("responsible_name"),
                OperationOrder.regional.label("regional"),
                func.max(OperationOrder.responsible_ixc_id).label("ixc_employee_id"),
                func.max(func.coalesce(OperationOrder.closed_at, OperationOrder.opened_at)).label("last_order_at"),
            )
            .where(OperationOrder.responsible.is_not(None), OperationOrder.responsible != "")
            .where(OperationOrder.regional.is_not(None), OperationOrder.regional != "")
            .group_by(OperationOrder.responsible, OperationOrder.regional)
        ).all()
    }

    assignments = db.scalars(select(OperationResponsibleAssignment)).all()
    candidates: dict[tuple[str, str], dict] = {}
    for assignment in assignments:
        key = (assignment.responsible_name, assignment.regional)
        order_info = last_orders.get(key)
        candidates[key] = {
            "responsible_name": assignment.responsible_name,
            "regional": assignment.regional,
            "team_model_id": assignment.team_model_id,
            "ixc_employee_id": int(order_info.ixc_employee_id) if order_info and order_info.ixc_employee_id else None,
            "last_order_at": order_info.last_order_at if order_info else None,
            "source": "assignment",
        }

    for key, order_info in last_orders.items():
        if key in candidates:
            continue
        candidates[key] = {
            "responsible_name": order_info.responsible_name,
            "regional": order_info.regional,
            "team_model_id": None,
            "ixc_employee_id": int(order_info.ixc_employee_id) if order_info.ixc_employee_id else None,
            "last_order_at": order_info.last_order_at,
            "source": "orders",
        }

    for candidate in candidates.values():
        responsible_name = str(candidate["responsible_name"]).strip()
        regional = normalize_regional(str(candidate["regional"]))
        if not responsible_name or regional == "NAO IDENTIFICADO":
            continue
        member = db.scalar(
            select(ManagementOperationalMember).where(
                ManagementOperationalMember.responsible_name == responsible_name,
                ManagementOperationalMember.regional == regional,
            )
        )
        collaborator = _find_collaborator(db, responsible_name, candidate["ixc_employee_id"])
        status = "pending_validation"
        if candidate["team_model_id"] and not collaborator:
            status = "without_supervisor"
        if member:
            if member.team_model_id is None and candidate["team_model_id"] is not None:
                member.team_model_id = candidate["team_model_id"]
            if member.ixc_employee_id is None and candidate["ixc_employee_id"] is not None:
                member.ixc_employee_id = candidate["ixc_employee_id"]
            if member.collaborator_id is None and collaborator:
                member.collaborator_id = collaborator.id
            if member.supervisor_user_id is None and collaborator and collaborator.supervisor_user_id is not None:
                member.supervisor_user_id = collaborator.supervisor_user_id
            if collaborator and collaborator.structure_status == "outside_operation" and member.status not in {"inactive", "outside_operation"}:
                member.status = "outside_operation"
            elif collaborator and collaborator.structure_status == "validated" and member.status == "pending_validation":
                member.status = "without_team_model" if member.team_model_id is None else "validated_operation"
            if candidate["last_order_at"] and (member.last_order_at is None or candidate["last_order_at"] > member.last_order_at):
                member.last_order_at = candidate["last_order_at"]
            member.updated_at = now
        else:
            member_supervisor_id = collaborator.supervisor_user_id if collaborator and collaborator.supervisor_user_id else None
            if collaborator and collaborator.structure_status == "outside_operation":
                status = "outside_operation"
            elif collaborator and collaborator.structure_status == "validated":
                status = "without_team_model" if candidate["team_model_id"] is None else "validated_operation"
            db.add(
                ManagementOperationalMember(
                    responsible_name=responsible_name,
                    regional=regional,
                    team_model_id=candidate["team_model_id"],
                    supervisor_user_id=member_supervisor_id,
                    ixc_employee_id=candidate["ixc_employee_id"],
                    collaborator_id=collaborator.id if collaborator else None,
                    last_order_at=candidate["last_order_at"],
                    status=status,
                    source=candidate["source"],
                )
            )
            touched += 1
    db.flush()
    return touched


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
):
    filters = []
    if regional:
        filters.append(ManagementOperationalMember.regional == normalize_regional(regional))
    if supervisor_user_id:
        filters.append(ManagementOperationalMember.supervisor_user_id == supervisor_user_id)
    if status:
        filters.append(ManagementOperationalMember.status == status)
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
