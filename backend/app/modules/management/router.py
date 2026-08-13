"""Rotas do módulo de Gestão Integrada.

Três blocos: estrutura operacional (quem pertence à operação), casos de gestão (a cobrança formal
de um desvio) e a configuração dos limiares que geram esses casos.

Escopo de visibilidade é aplicado no SERVIDOR, nunca no filtro que a tela manda: quem não tem
`management:review` (a matriz) só enxerga os casos e colaboradores sob sua supervisão ou nas
regionais que gerencia. Ver `cases.case_scope_conditions`.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case as sql_case, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.security import require_permission
from app.db.session import get_db
from app.models import User
from app.modules.management import cases as cases_engine
from app.modules.management.models import (
    CLOSED_CASE_STATUSES,
    OPEN_CASE_STATUSES,
    ManagementCase,
    ManagementCaseComment,
    ManagementCaseReason,
    ManagementOperationalMember,
)
from app.modules.management.schemas import (
    ManagementCaseCommentCreate,
    ManagementCaseCommentOut,
    ManagementCaseCreate,
    ManagementCaseGenerateRequest,
    ManagementCaseGenerateResult,
    ManagementCaseJustification,
    ManagementDailyCaseRequest,
    ManagementCaseOut,
    ManagementCasePage,
    ManagementCaseReasonCreate,
    ManagementCaseReasonOut,
    ManagementCaseReasonUpdate,
    ManagementCaseReview,
    ManagementCaseSummaryOut,
    ManagementDashboardOut,
    ManagementMemberUpdate,
    ManagementOptionOut,
    ManagementOptionsOut,
    ManagementSettingsUpdate,
)
from app.modules.management.services import member_out, refresh_operational_members, summarize_members, visible_member_filters
from app.modules.operations.models import OperationTeamModel
from app.services import notifications as notifications_service
from app.services.audit_log import record_audit_log, snapshot
from app.services.regional import normalize_regional

router = APIRouter(prefix="/management", tags=["management"])

# Ordenação da fila de trabalho da matriz. `severity` é texto, então ordenar direto pela coluna
# daria "high, low, medium" (alfabético) - com "low" na frente de "medium", que é o inverso da
# urgência real.
SEVERITY_RANK = sql_case({"high": 0, "medium": 1, "low": 2}, value=ManagementCase.severity, else_=3)


@router.get("/options", response_model=ManagementOptionsOut)
def options(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("management:read")),
):
    supervisors = db.scalars(select(User).where(User.active.is_(True)).order_by(User.name.asc())).all()
    team_models = db.scalars(select(OperationTeamModel).where(OperationTeamModel.active.is_(True)).order_by(OperationTeamModel.name.asc())).all()
    return ManagementOptionsOut(
        supervisors=[ManagementOptionOut(id=item.id, name=item.name) for item in supervisors],
        team_models=[ManagementOptionOut(id=item.id, name=item.name) for item in team_models],
    )


# --- Estrutura operacional --------------------------------------------------------------------


@router.get("/dashboard", response_model=ManagementDashboardOut)
def dashboard(
    regional: str | None = None,
    supervisor_user_id: int | None = None,
    status: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management:read")),
):
    filters = visible_member_filters(regional, supervisor_user_id, status, search)
    scope = cases_engine.member_scope_conditions(user)
    members = db.scalars(
        select(ManagementOperationalMember)
        .options(
            selectinload(ManagementOperationalMember.collaborator),
            selectinload(ManagementOperationalMember.supervisor),
            selectinload(ManagementOperationalMember.team_model),
        )
        .where(*filters, *scope)
        .order_by(ManagementOperationalMember.status.asc(), ManagementOperationalMember.regional.asc(), ManagementOperationalMember.responsible_name.asc())
        .limit(500)
    ).all()
    # Os contadores de caso respeitam o MESMO escopo da lista de membros - números globais numa tela
    # filtrada por regional faziam o painel contradizer a tabela logo abaixo.
    case_scope = cases_engine.case_scope_conditions(user)
    open_cases = db.scalar(
        select(func.count(ManagementCase.id)).where(ManagementCase.status.in_(OPEN_CASE_STATUSES), *case_scope)
    ) or 0
    overdue_cases = db.scalar(
        select(func.count(ManagementCase.id))
        .where(ManagementCase.status.in_(OPEN_CASE_STATUSES), *case_scope)
        .where(ManagementCase.due_date.is_not(None), ManagementCase.due_date < date.today())
    ) or 0
    return ManagementDashboardOut(summary=summarize_members(list(members), open_cases, overdue_cases), members=[member_out(item) for item in members])


@router.post("/structure/refresh")
def refresh_structure(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management:manage_structure")),
):
    created = refresh_operational_members(db)
    record_audit_log(db, user, "refresh", "management_operational_members", "structure", None, {"created_candidates": created})
    db.commit()
    return {"created_candidates": created}


@router.patch("/members/{member_id}", response_model=dict)
def update_member(
    member_id: int,
    payload: ManagementMemberUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management:manage_structure")),
):
    member = db.get(ManagementOperationalMember, member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Colaborador operacional não encontrado.")
    before = snapshot(member)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(member, field, value)
    if "status" in updates and updates["status"] in {"validated_operation", "active_management"}:
        member.validated_by = user.id
        member.validated_at = datetime.now(timezone.utc)
    record_audit_log(db, user, "update", "management_operational_members", member.id, before, snapshot(member))
    db.commit()
    return {"status": "ok"}


# --- Casos de gestão --------------------------------------------------------------------------


def _load_case_or_404(db: Session, case_id: int, user: User) -> ManagementCase:
    """Carrega o caso já validando o escopo do usuário.

    Devolve 404 (não 403) quando o caso existe mas está fora do escopo: um supervisor não deve nem
    conseguir descobrir que existe um caso de outra regional testando IDs.
    """
    item = db.scalar(
        select(ManagementCase)
        .options(
            selectinload(ManagementCase.collaborator),
            selectinload(ManagementCase.supervisor),
            selectinload(ManagementCase.team_model),
            selectinload(ManagementCase.reason),
        )
        .where(ManagementCase.id == case_id, *cases_engine.case_scope_conditions(user))
    )
    if not item:
        raise HTTPException(status_code=404, detail="Caso de gestão não encontrado.")
    return item


@router.get("/cases", response_model=ManagementCasePage)
def list_cases(
    status: str | None = None,
    severity: str | None = None,
    regional: str | None = None,
    supervisor_user_id: int | None = None,
    case_type: str | None = None,
    reference_year: int | None = None,
    reference_month: int | None = Query(default=None, ge=1, le=12),
    only_overdue: bool = False,
    only_open: bool = False,
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management:read")),
):
    filters = cases_engine.ManagementCaseFilters(
        status=status,
        severity=severity,
        regional=regional,
        supervisor_user_id=supervisor_user_id,
        case_type=case_type,
        reference_year=reference_year,
        reference_month=reference_month,
        only_overdue=only_overdue,
        search=search,
        statuses=list(OPEN_CASE_STATUSES) if only_open else [],
    )
    conditions = [*cases_engine.case_scope_conditions(user), *cases_engine.case_filter_conditions(filters)]
    total = db.scalar(select(func.count(ManagementCase.id)).where(*conditions)) or 0
    rows = db.scalars(
        select(ManagementCase)
        .options(
            selectinload(ManagementCase.collaborator),
            selectinload(ManagementCase.supervisor),
            selectinload(ManagementCase.team_model),
            selectinload(ManagementCase.reason),
        )
        .where(*conditions)
        # Severidade alta e prazo mais curto primeiro: a fila de trabalho da matriz, não a ordem de
        # cadastro.
        .order_by(SEVERITY_RANK.asc(), ManagementCase.due_date.asc().nulls_last(), ManagementCase.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    counts = cases_engine.comment_counts(db, [item.id for item in rows])
    return ManagementCasePage(
        items=[cases_engine.case_out(item, comment_count=counts.get(item.id, 0)) for item in rows],
        summary=ManagementCaseSummaryOut(**cases_engine.summarize_cases(db, conditions)),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/cases/{case_id}", response_model=ManagementCaseOut)
def get_case(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management:read")),
):
    item = _load_case_or_404(db, case_id, user)
    counts = cases_engine.comment_counts(db, [item.id])
    return cases_engine.case_out(item, comment_count=counts.get(item.id, 0))


@router.post("/cases", response_model=ManagementCaseOut, status_code=201)
def create_case(
    payload: ManagementCaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management:review")),
):
    settings = cases_engine.load_settings(db)
    data = payload.model_dump()
    if data.get("regional"):
        data["regional"] = normalize_regional(data["regional"])
    # Prazo padrão de justificativa quando a matriz não informa um - sem prazo o caso nunca fica
    # em atraso e a cobrança perde a régua.
    if data.get("due_date") is None:
        due_days = int(float(settings["management_case_due_days"]))
        data["due_date"] = date.today() + timedelta(days=due_days)
    item = ManagementCase(**data, status="pending", created_by=user.id)
    db.add(item)
    db.flush()
    record_audit_log(db, user, "create", "management_cases", item.id, None, snapshot(item))
    db.commit()
    db.refresh(item)
    return cases_engine.case_out(item)


@router.post("/cases/daily", response_model=ManagementCaseOut)
def open_daily_case(
    payload: ManagementDailyCaseRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management:write_justification")),
):
    """Abre (ou devolve) o caso do dia vermelho clicado no drill do calendário - o mesmo permissao
    de quem justifica (não exige `management:review`, ao contrário da criação manual de caso via
    POST /cases): o supervisor pode abrir a justificativa do próprio dia sem depender da matriz."""
    item, was_created = cases_engine.get_or_create_daily_case(
        db,
        responsible_name=payload.responsible_name,
        regional=payload.regional,
        reference_date=payload.reference_date,
        expected_value=payload.expected_value,
        actual_value=payload.actual_value,
        created_by=user.id,
    )
    scope = cases_engine.case_scope_conditions(user)
    if scope:
        in_scope = db.scalar(select(ManagementCase.id).where(ManagementCase.id == item.id, *scope))
        if not in_scope:
            raise HTTPException(status_code=404, detail="Caso de gestão não encontrado.")
    if was_created:
        record_audit_log(db, user, "open_daily", "management_cases", item.id, None, snapshot(item))
    db.commit()
    db.refresh(item)
    counts = cases_engine.comment_counts(db, [item.id])
    return cases_engine.case_out(item, comment_count=counts.get(item.id, 0))


@router.post("/cases/generate", response_model=ManagementCaseGenerateResult)
def generate_cases(
    payload: ManagementCaseGenerateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management:review")),
):
    """Varre a competência e abre casos de produtividade abaixo da meta. Idempotente: rodar de novo
    no mesmo mês não duplica caso."""
    result = cases_engine.generate_performance_cases(
        db, year=payload.reference_year, month=payload.reference_month, created_by=user.id
    )
    record_audit_log(db, user, "generate", "management_cases", "batch", None, result)
    db.commit()
    return ManagementCaseGenerateResult(**result)


@router.post("/cases/{case_id}/justify", response_model=ManagementCaseOut)
def justify_case(
    case_id: int,
    payload: ManagementCaseJustification,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management:write_justification")),
):
    item = _load_case_or_404(db, case_id, user)
    if item.status in CLOSED_CASE_STATUSES:
        raise HTTPException(status_code=409, detail="Este caso já foi encerrado pela matriz e não aceita nova justificativa.")

    reason = None
    if payload.reason_id is not None:
        reason = db.get(ManagementCaseReason, payload.reason_id)
        if reason is None or not reason.active:
            raise HTTPException(status_code=400, detail="Motivo de justificativa inválido ou inativo.")
    # `requires_description` existia no banco mas nunca era cobrado - o motivo "Outro" aceitava
    # justificativa vazia de conteúdo, que é justamente o que ele deveria impedir.
    if reason is not None and reason.requires_description and len((payload.justification_text or "").strip()) < 15:
        raise HTTPException(
            status_code=400,
            detail=f'O motivo "{reason.name}" exige uma descrição detalhada (mínimo de 15 caracteres).',
        )

    before = snapshot(item)
    item.reason_id = payload.reason_id
    item.justification_text = payload.justification_text.strip()
    item.action_plan = payload.action_plan.strip() if payload.action_plan else None
    item.status = payload.status
    item.justified_at = datetime.now(timezone.utc)
    record_audit_log(db, user, "justify", "management_cases", item.id, before, snapshot(item))

    if item.status == "justified":
        # So neste status ha algo pronto pra decisao da matriz - "in_progress" (o supervisor
        # pedindo mais tempo/complemento) nao gera aviso, ninguem precisa agir ainda.
        notifications_service.notify_users_with_permission(
            db,
            permission="management:review",
            title="Caso pronto para revisão",
            message=f"{item.responsible_name or 'Colaborador'} justificou o caso #{item.id} ({item.metric_name}) - pronto para decisão da matriz.",
            link_url=f"/gestao?case_id={item.id}",
            entity_type="management_case",
            entity_id=item.id,
            exclude_user_id=user.id,
        )

    db.commit()
    db.refresh(item)
    return cases_engine.case_out(item)


@router.post("/cases/{case_id}/review", response_model=ManagementCaseOut)
def review_case(
    case_id: int,
    payload: ManagementCaseReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management:review")),
):
    """Decisão da matriz: aceita (resolved), rejeita (rejected) ou devolve para complemento
    (in_progress). É o passo que faltava para o caso ter fim."""
    item = _load_case_or_404(db, case_id, user)
    if item.status == "pending" and payload.status == "resolved":
        raise HTTPException(
            status_code=409,
            detail="Não é possível resolver um caso que ainda não foi justificado pelo supervisor.",
        )
    before = snapshot(item)
    item.status = payload.status
    item.reviewed_by = user.id
    item.reviewed_at = datetime.now(timezone.utc)
    if payload.due_date is not None:
        item.due_date = payload.due_date
    if payload.review_note:
        # A nota da revisão vira comentário para não sobrescrever a justificativa do supervisor -
        # o histórico da discussão é a prova de como a decisão foi tomada.
        db.add(ManagementCaseComment(case_id=item.id, user_id=user.id, comment=payload.review_note.strip()))
    record_audit_log(db, user, "review", "management_cases", item.id, before, snapshot(item))
    db.commit()
    db.refresh(item)
    counts = cases_engine.comment_counts(db, [item.id])
    return cases_engine.case_out(item, comment_count=counts.get(item.id, 0))


@router.get("/cases/{case_id}/comments", response_model=list[ManagementCaseCommentOut])
def list_case_comments(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management:read")),
):
    _load_case_or_404(db, case_id, user)
    rows = db.execute(
        select(ManagementCaseComment, User.name)
        .outerjoin(User, User.id == ManagementCaseComment.user_id)
        .where(ManagementCaseComment.case_id == case_id)
        .order_by(ManagementCaseComment.created_at.asc())
    ).all()
    return [
        ManagementCaseCommentOut(
            id=comment.id,
            case_id=comment.case_id,
            user_id=comment.user_id,
            user_name=user_name,
            comment=comment.comment,
            created_at=comment.created_at,
        )
        for comment, user_name in rows
    ]


@router.post("/cases/{case_id}/comments", response_model=ManagementCaseCommentOut, status_code=201)
def create_case_comment(
    case_id: int,
    payload: ManagementCaseCommentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management:write_justification")),
):
    _load_case_or_404(db, case_id, user)
    comment = ManagementCaseComment(case_id=case_id, user_id=user.id, comment=payload.comment.strip())
    db.add(comment)
    db.flush()
    record_audit_log(db, user, "comment", "management_cases", case_id, None, {"comment_id": comment.id})
    db.commit()
    db.refresh(comment)
    return ManagementCaseCommentOut(
        id=comment.id,
        case_id=comment.case_id,
        user_id=comment.user_id,
        user_name=user.name,
        comment=comment.comment,
        created_at=comment.created_at,
    )


# --- Motivos de justificativa -------------------------------------------------------------------


@router.get("/case-reasons", response_model=list[ManagementCaseReasonOut])
def list_reasons(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("management:read")),
):
    # Semeia na primeira leitura: sem motivo cadastrado o fluxo de justificativa nasce inutilizável.
    if cases_engine.seed_default_reasons(db):
        db.commit()
    stmt = select(ManagementCaseReason).order_by(ManagementCaseReason.name.asc())
    if not include_inactive:
        stmt = stmt.where(ManagementCaseReason.active.is_(True))
    return db.scalars(stmt).all()


@router.post("/case-reasons", response_model=ManagementCaseReasonOut, status_code=201)
def create_reason(
    payload: ManagementCaseReasonCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management:admin")),
):
    name = payload.name.strip()
    if db.scalar(select(ManagementCaseReason.id).where(func.lower(ManagementCaseReason.name) == name.casefold())):
        raise HTTPException(status_code=409, detail="Já existe um motivo com esse nome.")
    item = ManagementCaseReason(
        name=name,
        description=payload.description,
        active=payload.active,
        requires_description=payload.requires_description,
    )
    db.add(item)
    db.flush()
    record_audit_log(db, user, "create", "management_case_reasons", item.id, None, snapshot(item))
    db.commit()
    db.refresh(item)
    return item


@router.patch("/case-reasons/{reason_id}", response_model=ManagementCaseReasonOut)
def update_reason(
    reason_id: int,
    payload: ManagementCaseReasonUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management:admin")),
):
    item = db.get(ManagementCaseReason, reason_id)
    if not item:
        raise HTTPException(status_code=404, detail="Motivo não encontrado.")
    before = snapshot(item)
    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates:
        name = updates["name"].strip()
        clash = db.scalar(
            select(ManagementCaseReason.id).where(
                func.lower(ManagementCaseReason.name) == name.casefold(), ManagementCaseReason.id != reason_id
            )
        )
        if clash:
            raise HTTPException(status_code=409, detail="Já existe um motivo com esse nome.")
        updates["name"] = name
    for field, value in updates.items():
        setattr(item, field, value)
    record_audit_log(db, user, "update", "management_case_reasons", item.id, before, snapshot(item))
    db.commit()
    db.refresh(item)
    return item


# --- Configuração dos limiares ------------------------------------------------------------------


@router.get("/settings")
def get_settings(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("management:read")),
):
    return cases_engine.load_settings(db)


@router.put("/settings")
def update_settings(
    payload: ManagementSettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management:admin")),
):
    values = {key: value for key, value in payload.model_dump().items() if value is not None}
    result = cases_engine.save_settings(db, values)
    record_audit_log(db, user, "update", "management_settings", "thresholds", None, values)
    db.commit()
    return result
