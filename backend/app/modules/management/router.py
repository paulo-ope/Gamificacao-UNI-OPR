"""Rotas do módulo de Gestão Integrada.

Três blocos: estrutura operacional (quem pertence à operação), casos de gestão (a cobrança formal
de um desvio) e a configuração dos limiares que geram esses casos.

Escopo de visibilidade é aplicado no SERVIDOR, nunca no filtro que a tela manda: quem não tem
`management:review` (a matriz) só enxerga os casos e colaboradores sob sua supervisão ou nas
regionais que gerencia. Ver `cases.case_scope_conditions`.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
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
    ManagementAutoGenerateSettingsOut,
    ManagementAutoGenerateSettingsUpdate,
    ManagementCaseBulkReview,
    ManagementCaseBulkReviewResult,
    ManagementCaseCommentCreate,
    ManagementCaseCommentOut,
    ManagementCaseCreate,
    ManagementCaseDiagnosticsOut,
    ManagementCaseGenerateRequest,
    ManagementCaseGenerateResult,
    ManagementCaseJustification,
    ManagementDailyCaseRequest,
    ManagementMonthlyCaseRequest,
    ManagementCaseOut,
    ManagementCasePage,
    ManagementCaseReasonCreate,
    ManagementCaseReasonOut,
    ManagementCaseReasonUpdate,
    ManagementCaseReview,
    ManagementCaseSummaryOut,
    ManagementDashboardOut,
    ManagementMemberUpdate,
    ManagementOperationalMemberOut,
    ManagementOptionOut,
    ManagementOptionsOut,
    ManagementSettingsUpdate,
)
from app.modules.management.scheduler import (
    AUTO_GENERATE_LAST_RUN_DATE_KEY,
    auto_generate_enabled,
    set_auto_generate_enabled,
)
from app.modules.management import services as management_services
from app.modules.management.services import member_out, refresh_operational_members, summarize_members, visible_member_filters
from app.modules.operations.models import OperationTeamModel
from app.services import notifications as notifications_service
from app.services.audit_log import record_audit_log, snapshot
from app.services.calculation import get_setting
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
    collaborator_regional: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management:read")),
):
    filters = visible_member_filters(regional, supervisor_user_id, status, search, collaborator_regional)
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


@router.post("/members/{member_id}/claim", response_model=ManagementOperationalMemberOut)
def claim_member(
    member_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management:claim_member")),
):
    """Supervisor/gerente de base reivindica um colaborador SEM supervisor pra própria base -
    monta o próprio "organograma" de campo sem depender da matriz clicar em algo.

    Sem restrição por `member_scope_conditions` de propósito: essa restrição usa
    `managed_regionals`, que nem todo supervisor/gerente de base tem configurado - exigi-la aqui
    tornaria a reivindicação impossível justamente para quem mais precisa dela. A única guarda
    necessária é a de ownership (`MemberAlreadyClaimedError`, abaixo): reivindicar só funciona
    enquanto ninguém mais é o supervisor - "roubar" colaborador de outro exige a ação
    administrativa (`management:manage_structure`), não esta."""
    member = db.get(ManagementOperationalMember, member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Colaborador operacional não encontrado.")
    before = snapshot(member)
    try:
        management_services.claim_member(db, member=member, claimer=user)
    except management_services.MemberAlreadyClaimedError:
        raise HTTPException(status_code=409, detail="Este colaborador já pertence à base de outro supervisor.")
    record_audit_log(db, user, "claim", "management_operational_members", member.id, before, snapshot(member))
    db.commit()
    db.refresh(member)
    return member_out(member)


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

    # Escala alternada (12x36) só pode ser ligada em quem é desse modelo de equipe - valida contra
    # o estado EFETIVO pós-update (o PATCH é parcial: team_model_id pode não vir no payload,
    # sobrando o valor já salvo; ou vir junto com shift_pattern na mesma chamada).
    effective_shift_pattern = updates.get("shift_pattern", member.shift_pattern)
    effective_team_model_id = updates.get("team_model_id", member.team_model_id)
    effective_team_model = (
        db.get(OperationTeamModel, effective_team_model_id) if effective_team_model_id is not None else None
    )
    try:
        management_services.validate_shift_pattern_for_team_model(effective_shift_pattern, effective_team_model)
    except management_services.ShiftPatternNotEligibleError:
        raise HTTPException(
            status_code=422,
            detail=(
                "Escala alternada (dia sim, dia não) só pode ser ligada em colaboradores do "
                "modelo de equipe 12x36. Troque o modelo de equipe junto nesta mesma chamada, ou "
                "deixe shift_pattern como \"standard\"."
            ),
        )

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
    try:
        conditions = [*cases_engine.case_scope_conditions(user), *cases_engine.case_filter_conditions(filters)]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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


def _diagnostics_filters(
    status: str | None,
    severity: str | None,
    regional: str | None,
    supervisor_user_id: int | None,
    case_type: str | None,
    reference_year: int | None,
    reference_month: int | None,
    only_overdue: bool,
    only_open: bool,
    search: str | None,
) -> cases_engine.ManagementCaseFilters:
    return cases_engine.ManagementCaseFilters(
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


@router.get("/cases/export")
def export_cases(
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
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management:read")),
):
    """Exporta em CSV o MESMO recorte filtrado hoje na tabela de casos - sem paginação (a tela
    lista só `page_size` por vez, o export precisa de todo o recorte). Escopo de visibilidade
    aplicado igual à listagem: quem não é matriz só exporta o que já enxergaria na tela."""
    import csv
    import io

    filters = _diagnostics_filters(
        status, severity, regional, supervisor_user_id, case_type, reference_year, reference_month,
        only_overdue, only_open, search,
    )
    try:
        conditions = [*cases_engine.case_scope_conditions(user), *cases_engine.case_filter_conditions(filters)]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    rows = db.scalars(
        select(ManagementCase)
        .options(selectinload(ManagementCase.supervisor), selectinload(ManagementCase.reason))
        .where(*conditions)
        .order_by(ManagementCase.created_at.desc())
    ).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow([
        "id", "tipo", "responsavel", "regional", "competencia", "metrica", "esperado", "realizado",
        "desvio_pct", "severidade", "status", "em_atraso", "motivo", "justificativa", "prazo",
        "supervisor", "criado_em", "justificado_em", "revisado_em",
    ])
    for item in rows:
        writer.writerow([
            item.id,
            item.case_type,
            item.responsible_name or "",
            item.regional or "",
            f"{item.reference_month:02d}/{item.reference_year}" if item.reference_month and item.reference_year else "",
            item.metric_name,
            item.expected_value if item.expected_value is not None else "",
            item.actual_value if item.actual_value is not None else "",
            item.deviation_value if item.deviation_value is not None else "",
            item.severity,
            item.status,
            "sim" if cases_engine.is_overdue(item) else "não",
            item.reason.name if item.reason else "",
            (item.justification_text or "").replace("\n", " "),
            item.due_date.isoformat() if item.due_date else "",
            item.supervisor.name if item.supervisor else "",
            item.created_at.isoformat(),
            item.justified_at.isoformat() if item.justified_at else "",
            item.reviewed_at.isoformat() if item.reviewed_at else "",
        ])
    csv_content = "﻿" + buffer.getvalue()  # BOM: Excel abre acentuação corretamente
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=casos_gestao.csv"},
    )


@router.get("/cases/diagnostics", response_model=ManagementCaseDiagnosticsOut)
def case_diagnostics(
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
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management:read")),
):
    """Diagnóstico agregado (quem mais falha, por regional/responsável/motivo) do MESMO recorte
    filtrado na tela - pedido do usuário em 2026-08-20 pra não precisar contar caso por caso."""
    filters = _diagnostics_filters(
        status, severity, regional, supervisor_user_id, case_type, reference_year, reference_month,
        only_overdue, only_open, search,
    )
    try:
        conditions = [*cases_engine.case_scope_conditions(user), *cases_engine.case_filter_conditions(filters)]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ManagementCaseDiagnosticsOut(**cases_engine.case_diagnostics(db, conditions))


@router.post("/cases/bulk-review", response_model=ManagementCaseBulkReviewResult)
def bulk_review_cases(
    payload: ManagementCaseBulkReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management:review")),
):
    """Aprova/rejeita/devolve vários casos de uma vez - pedido do usuário em 2026-08-20 pra matriz
    não precisar abrir caso por caso quando o motivo é o mesmo pra todos."""
    result = cases_engine.bulk_review_cases(
        db,
        case_ids=payload.case_ids,
        status=payload.status,
        review_note=payload.review_note,
        reviewer_id=user.id,
        scope_conditions=cases_engine.case_scope_conditions(user),
    )
    record_audit_log(db, user, "bulk_review", "management_cases", "batch", None, {**result, "case_ids": payload.case_ids, "status": payload.status})
    db.commit()
    return ManagementCaseBulkReviewResult(**result)


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


@router.post("/cases/monthly", response_model=ManagementCaseOut)
def open_monthly_case(
    payload: ManagementMonthlyCaseRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management:write_justification")),
):
    """Abre (ou devolve) o caso mensal de UM colaborador a partir do "Detalhe Operacional Mensal"
    do calendário - mesma permissão de quem justifica, mesmo racional de `open_daily_case`: o
    supervisor abre a justificativa do próprio colaborador sem depender da matriz clicar em "Gerar
    casos do mês"."""
    today = date.today()
    if (payload.reference_year, payload.reference_month) >= (today.year, today.month):
        raise HTTPException(
            status_code=400,
            detail="Só é possível justificar um mês já fechado - o mês corrente ainda está em andamento.",
        )
    item, was_created = cases_engine.get_or_create_monthly_case(
        db,
        responsible_name=payload.responsible_name,
        regional=payload.regional,
        reference_year=payload.reference_year,
        reference_month=payload.reference_month,
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
        record_audit_log(db, user, "open_monthly", "management_cases", item.id, None, snapshot(item))
    db.commit()
    db.refresh(item)
    counts = cases_engine.comment_counts(db, [item.id])
    return cases_engine.case_out(item, comment_count=counts.get(item.id, 0))


@router.post("/cases/generate", response_model=ManagementCaseGenerateResult)
def generate_cases(
    payload: ManagementCaseGenerateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management:generate_cases")),
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


@router.get("/settings/auto-generate", response_model=ManagementAutoGenerateSettingsOut)
def get_auto_generate_settings(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("management:read")),
):
    raw_last_run = get_setting(db, AUTO_GENERATE_LAST_RUN_DATE_KEY, "")
    last_run_date = date.fromisoformat(raw_last_run) if raw_last_run else None
    return ManagementAutoGenerateSettingsOut(enabled=auto_generate_enabled(), last_run_date=last_run_date)


@router.put("/settings/auto-generate", response_model=ManagementAutoGenerateSettingsOut)
def update_auto_generate_settings(
    payload: ManagementAutoGenerateSettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management:admin")),
):
    """Liga/desliga a geração automática (diária) dos casos de produtividade do mês anterior
    fechado E dos casos de dia abaixo da meta de ontem - ver `modules/management/scheduler.py`
    (um único toggle controla os dois). Os botões manuais ("Gerar casos do mês" em Gestão,
    "Justificar dia" no calendário) continuam disponíveis mesmo com o automático ligado, para
    reprocessar uma competência/dia específico."""
    set_auto_generate_enabled(payload.enabled)
    record_audit_log(db, user, "update", "management_settings", "auto_generate", None, {"enabled": payload.enabled})
    db.commit()
    raw_last_run = get_setting(db, AUTO_GENERATE_LAST_RUN_DATE_KEY, "")
    last_run_date = date.fromisoformat(raw_last_run) if raw_last_run else None
    return ManagementAutoGenerateSettingsOut(enabled=payload.enabled, last_run_date=last_run_date)
