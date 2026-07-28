from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.performance import performance_step
from app.core.security import require_permission
from app.db.session import SessionLocal, get_db
from app.models import CalculationRun, DiagnosisPenaltyRule, ScoringGroup, ScoringSubjectRule, ServiceOrder, User
from app.seed import forget_deleted_default_group, remember_deleted_default_group
from app.schemas import (
    DiagnosisConfigureRequest,
    DiagnosisConfigureBulkRequest,
    DiagnosisPenaltyRuleOut,
    ScoringGroupCreate,
    ScoringGroupDeleteRequest,
    ScoringGroupDeleteResult,
    ScoringGroupOut,
    ScoringGroupUpdate,
    ScoringSubjectRuleCreate,
    ScoringSubjectRuleDeleteResult,
    ScoringSubjectRuleOut,
    ScoringSubjectRuleUpdate,
    SubjectLinkToGroupRequest,
    SubjectLinkToGroupBulkRequest,
    ImportedDiagnosisOut,
    UnmappedSubjectOut,
)
from app.services.calculation import latest_run, recalculate_current_period
from app.services.scoring_detail import (
    cascade_os_type_for_subject,
    effective_rule_point_value,
    effective_rule_points,
    get_point_value,
    imported_diagnosis_stats,
    unmapped_subjects,
)
from app.services.scoring_matrix import DEMO_SERVICE_ORDER_CODES, matrix_subject_rules, subject_key
from app.services.audit_log import record_audit_log, snapshot

router = APIRouter(tags=["scoring"], dependencies=[Depends(require_permission("scoring:read"))])
ALLOWED_DIAGNOSIS_ACTIONS = {"subtract_points", "cancel_points", "no_penalty", "requires_review", "force_points"}


def _subject_rule_stats_map(db: Session, rules: list[ScoringSubjectRule]) -> dict[int, dict[str, float | int]]:
    # Achado real (lentidao ao abrir Configuracao): antes buscava os_code/os_type/os_subject de
    # TODA a tabela service_orders (todos os meses, sem filtro) e contava em Python a cada
    # chamada - inclusive apos editar UMA regra, que so precisa da contagem dela. Deixa o Postgres
    # agregar (GROUP BY) e so traz um total por par (os_type, os_subject) distinto.
    counts: dict[tuple[str, str], int] = {}
    count_rows = db.execute(
        select(ServiceOrder.os_type, ServiceOrder.os_subject, func.count())
        .where(ServiceOrder.os_code.notin_(DEMO_SERVICE_ORDER_CODES))
        .group_by(ServiceOrder.os_type, ServiceOrder.os_subject)
    )
    for os_type, os_subject, count in count_rows:
        key = subject_key(os_type, os_subject)
        counts[key] = counts.get(key, 0) + count

    point_value = get_point_value(db)
    stats: dict[int, dict[str, float | int]] = {}
    for rule in rules:
        count = counts.get(subject_key(rule.os_type, rule.os_subject), 0)
        effective_points = effective_rule_points(rule)
        effective_point_value, _ = effective_rule_point_value(rule, point_value)
        stats[rule.id] = {
            "effective_points": round(effective_points, 2),
            "effective_point_value": round(effective_point_value, 4),
            "orders_count": count,
            "financial_impact": round(count * effective_points * effective_point_value, 2),
        }
    return stats


def _rule_stats(db: Session, rule: ScoringSubjectRule) -> dict[str, float | int]:
    return _subject_rule_stats_map(db, [rule]).get(
        rule.id,
        {"effective_points": 0.0, "effective_point_value": 0.0, "orders_count": 0, "financial_impact": 0.0},
    )


def _serialize_subject_rule(
    db: Session,
    rule: ScoringSubjectRule,
    stats: dict[str, float | int] | None = None,
) -> dict:
    rule_stats = stats or _rule_stats(db, rule)
    return {
        "id": rule.id,
        "group_id": rule.group_id,
        "os_type": rule.os_type,
        "os_subject": rule.os_subject,
        "subject_category": rule.subject_category,
        "custom_points": rule.custom_points,
        "point_value_override": rule.point_value_override,
        "use_group_default": rule.use_group_default,
        "active": rule.active,
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
        "group": rule.group,
        **rule_stats,
    }


def _reconcile_duplicate_subject_rules(db: Session, os_subject: str, keep_rule_id: int) -> None:
    """Tipo Geral é uma classificação do assunto (`os_subject`), não deveria conviver com mais de uma
    regra pro mesmo assunto sob um `os_type` diferente. Quando o Tipo Geral de um assunto é definido/
    corrigido, apaga qualquer outra `ScoringSubjectRule` órfã que ainda exista pro mesmo assunto sob o
    tipo antigo - sem isso, cada correção de Tipo Geral reacumula duplicatas (achado real: foi preciso
    limpar 41 regras órfãs à mão nesta mesma sessão antes desta função existir)."""
    stale_rules = list(
        db.scalars(
            select(ScoringSubjectRule)
            .where(ScoringSubjectRule.os_subject == os_subject)
            .where(ScoringSubjectRule.id != keep_rule_id)
        )
    )
    for stale in stale_rules:
        db.delete(stale)


def _link_subject_rule(db: Session, payload: SubjectLinkToGroupRequest) -> tuple[ScoringSubjectRule, int]:
    group = db.get(ScoringGroup, payload.group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Grupo de pontuação não encontrado.")

    rule = db.scalar(
        select(ScoringSubjectRule)
        .where(ScoringSubjectRule.os_type == payload.os_type)
        .where(ScoringSubjectRule.os_subject == payload.os_subject)
    )
    if not rule:
        rule = ScoringSubjectRule(
            group_id=payload.group_id,
            os_type=payload.os_type,
            os_subject=payload.os_subject,
            subject_category=getattr(payload, "subject_category", None),
            use_group_default=True,
            custom_points=None,
            active=True,
        )
        db.add(rule)
        db.flush()
    else:
        rule.group_id = payload.group_id
        rule.use_group_default = True
        rule.custom_points = None
        rule.active = True
        rule.updated_at = datetime.now(timezone.utc)

    _reconcile_duplicate_subject_rules(db, rule.os_subject, rule.id)
    # Vincular um assunto sempre carimba o Tipo Geral escolhido nas O.S já importadas com esse
    # assunto - sem isso, O.S antigas ficam com o os_type velho (setor/pendente) e nunca casam com a
    # regra recém-criada (achado real - ver docs/plano-integracao-ixc.md).
    cascaded = cascade_os_type_for_subject(db, payload.os_subject, payload.os_type)
    return rule, cascaded


def _configure_diagnosis_rule(db: Session, payload: DiagnosisConfigureRequest) -> DiagnosisPenaltyRule:
    if payload.action_type not in ALLOWED_DIAGNOSIS_ACTIONS:
        raise HTTPException(status_code=422, detail="Tipo de ação de diagnóstico inválido.")

    rule = db.scalar(select(DiagnosisPenaltyRule).where(DiagnosisPenaltyRule.diagnosis_name == payload.diagnosis_name))
    if not rule:
        rule = DiagnosisPenaltyRule(diagnosis_name=payload.diagnosis_name)
        db.add(rule)

    rule.action_type = payload.action_type
    rule.penalty_points = payload.penalty_points
    rule.force_points_value = payload.force_points_value
    rule.description = payload.description
    rule.active = payload.active
    rule.updated_at = datetime.now(timezone.utc)
    return rule


@router.get("/scoring-groups", response_model=list[ScoringGroupOut])
def list_scoring_groups(db: Session = Depends(get_db)):
    return db.scalars(select(ScoringGroup).order_by(ScoringGroup.id.asc())).all()


@router.post("/scoring-groups", response_model=ScoringGroupOut, status_code=201)
def create_scoring_group(payload: ScoringGroupCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("scoring:write"))):
    group = ScoringGroup(**payload.model_dump())
    db.add(group)
    db.flush()
    forget_deleted_default_group(db, group.name)
    record_audit_log(db, user, "create", "scoring_groups", group.id, None, snapshot(group))
    db.commit()
    db.refresh(group)
    return group


@router.put("/scoring-groups/{group_id}", response_model=ScoringGroupOut)
def update_scoring_group(group_id: int, payload: ScoringGroupUpdate, db: Session = Depends(get_db), user: User = Depends(require_permission("scoring:write"))):
    group = db.get(ScoringGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Grupo de pontuação não encontrado.")

    before = snapshot(group)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(group, field, value)
    group.updated_at = datetime.now(timezone.utc)
    record_audit_log(db, user, "update", "scoring_groups", group.id, before, snapshot(group))
    db.commit()
    db.refresh(group)
    return group


@router.delete("/scoring-groups/{group_id}", response_model=ScoringGroupDeleteResult)
def delete_scoring_group(
    group_id: int,
    payload: ScoringGroupDeleteRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scoring:write")),
):
    group = db.get(ScoringGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Grupo de pontuação não encontrado.")

    delete_request = payload or ScoringGroupDeleteRequest()
    replacement_group: ScoringGroup | None = None
    if delete_request.replacement_group_id is not None:
        if delete_request.replacement_group_id == group_id:
            raise HTTPException(status_code=400, detail="Selecione um grupo diferente para receber os vínculos.")
        replacement_group = db.get(ScoringGroup, delete_request.replacement_group_id)
        if not replacement_group:
            raise HTTPException(status_code=404, detail="Grupo de destino não encontrado.")

    subject_rules = list(db.scalars(select(ScoringSubjectRule).where(ScoringSubjectRule.group_id == group_id)))

    if subject_rules and not replacement_group and not delete_request.delete_linked_rules:
        raise HTTPException(
            status_code=409,
            detail=(
                f"O grupo possui {len(subject_rules)} assunto(s) vinculado(s). "
                "Escolha um grupo de destino ou confirme a exclusão dos vínculos."
            ),
        )

    result = ScoringGroupDeleteResult(
        deleted_group_id=group.id,
        deleted_group_name=group.name,
    )

    if replacement_group:
        for rule in subject_rules:
            rule.group = replacement_group
            rule.updated_at = datetime.now(timezone.utc)
        result.moved_subject_rules = len(subject_rules)
    else:
        for rule in subject_rules:
            db.delete(rule)
        result.deleted_subject_rules = len(subject_rules)

    record_audit_log(db, user, "delete", "scoring_groups", group.id, snapshot(group), result.model_dump(mode="json"))
    remember_deleted_default_group(db, group.name)
    db.delete(group)
    db.commit()
    return result


@router.get("/scoring-subject-rules", response_model=list[ScoringSubjectRuleOut])
def list_scoring_subject_rules(db: Session = Depends(get_db)):
    rules = matrix_subject_rules(db)
    stats = _subject_rule_stats_map(db, rules)
    return [_serialize_subject_rule(db, rule, stats.get(rule.id)) for rule in rules]


@router.post("/scoring-subject-rules", response_model=ScoringSubjectRuleOut, status_code=201)
def create_scoring_subject_rule(payload: ScoringSubjectRuleCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("scoring:write"))):
    group = db.get(ScoringGroup, payload.group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Grupo de pontuação não encontrado.")

    exists = db.scalar(
        select(ScoringSubjectRule)
        .where(ScoringSubjectRule.os_type == payload.os_type)
        .where(ScoringSubjectRule.os_subject == payload.os_subject)
    )
    if exists:
        raise HTTPException(status_code=409, detail="Assunto ja possui regra na matriz.")

    rule = ScoringSubjectRule(**payload.model_dump())
    db.add(rule)
    db.flush()
    _reconcile_duplicate_subject_rules(db, rule.os_subject, rule.id)
    cascaded = cascade_os_type_for_subject(db, rule.os_subject, rule.os_type)
    record_audit_log(db, user, "create", "scoring_subject_rules", rule.id, None, snapshot(rule))
    db.commit()
    if cascaded:
        with SessionLocal() as recalculation_db:
            recalculate_current_period(
                recalculation_db,
                triggered_by=user.id,
                execution_note=f'Recálculo automático após cadastrar o Tipo Geral do assunto "{rule.os_subject}".',
            )
    db.refresh(rule)
    rule = db.scalar(
        select(ScoringSubjectRule).options(selectinload(ScoringSubjectRule.group)).where(ScoringSubjectRule.id == rule.id)
    )
    return _serialize_subject_rule(db, rule)


@router.put("/scoring-subject-rules/{rule_id}", response_model=ScoringSubjectRuleOut)
def update_scoring_subject_rule(rule_id: int, payload: ScoringSubjectRuleUpdate, db: Session = Depends(get_db), user: User = Depends(require_permission("scoring:write"))):
    rule = db.get(ScoringSubjectRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Regra de assunto não encontrada.")

    before = snapshot(rule)
    previous_os_type = rule.os_type
    previous_os_subject = rule.os_subject
    updates = payload.model_dump(exclude_unset=True)
    if "group_id" in updates and not db.get(ScoringGroup, updates["group_id"]):
        raise HTTPException(status_code=404, detail="Grupo de pontuação não encontrado.")

    for field, value in updates.items():
        setattr(rule, field, value)
    rule.updated_at = datetime.now(timezone.utc)

    cascaded = 0
    if "os_type" in updates and updates["os_type"] != previous_os_type:
        _reconcile_duplicate_subject_rules(db, rule.os_subject, rule.id)
        cascaded = cascade_os_type_for_subject(db, rule.os_subject, rule.os_type)

    record_audit_log(db, user, "update", "scoring_subject_rules", rule.id, before, snapshot(rule))
    db.commit()
    if cascaded:
        with SessionLocal() as recalculation_db:
            recalculate_current_period(
                recalculation_db,
                triggered_by=user.id,
                execution_note=f'Recálculo automático após corrigir o Tipo Geral do assunto "{rule.os_subject}".',
            )
    rule = db.scalar(
        select(ScoringSubjectRule).options(selectinload(ScoringSubjectRule.group)).where(ScoringSubjectRule.id == rule.id)
    )
    return _serialize_subject_rule(db, rule)


@router.delete("/scoring-subject-rules/{rule_id}", response_model=ScoringSubjectRuleDeleteResult)
def delete_scoring_subject_rule(rule_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission("scoring:write"))):
    rule = db.get(ScoringSubjectRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Regra de assunto não encontrada.")

    result = ScoringSubjectRuleDeleteResult(
        deleted_rule_id=rule.id,
        os_type=rule.os_type,
        os_subject=rule.os_subject,
    )
    record_audit_log(db, user, "delete", "scoring_subject_rules", rule.id, snapshot(rule), None)
    db.delete(rule)
    db.commit()
    return result


@router.get("/scoring-subject-rules/unmapped", response_model=list[UnmappedSubjectOut])
def list_unmapped_subjects(
    calculation_run_id: int | None = None,
    reference_month: int | None = Query(default=None, ge=1, le=12),
    reference_year: int | None = Query(default=None, ge=2000),
    regional: str | None = None,
    db: Session = Depends(get_db),
):
    run: CalculationRun | None = db.get(CalculationRun, calculation_run_id) if calculation_run_id else latest_run(db)
    now = datetime.now(timezone.utc)
    month = reference_month or (run.reference_month if run else now.month)
    year = reference_year or (run.reference_year if run else now.year)
    selected_regional = regional if regional is not None else (run.regional if run else None)
    with performance_step("scoring.unmapped-subjects", "aggregate_unmapped_subjects"):
        return unmapped_subjects(db, month, year, selected_regional)


@router.get("/scoring-matrix/unmapped-subjects", response_model=list[UnmappedSubjectOut])
def list_unmapped_subjects_alias(
    calculation_run_id: int | None = None,
    reference_month: int | None = Query(default=None, ge=1, le=12),
    reference_year: int | None = Query(default=None, ge=2000),
    regional: str | None = None,
    db: Session = Depends(get_db),
):
    return list_unmapped_subjects(calculation_run_id, reference_month, reference_year, regional, db)


@router.post("/scoring-matrix/subjects/link-to-group", response_model=ScoringSubjectRuleOut)
def link_subject_to_group(payload: SubjectLinkToGroupRequest, db: Session = Depends(get_db), user: User = Depends(require_permission("scoring:write"))):
    rule, cascaded = _link_subject_rule(db, payload)
    db.flush()
    record_audit_log(db, user, "link_to_group", "scoring_subject_rules", rule.id, None, snapshot(rule))
    db.commit()
    if cascaded:
        with SessionLocal() as recalculation_db:
            recalculate_current_period(
                recalculation_db,
                triggered_by=user.id,
                execution_note=f'Recálculo automático após classificar o Tipo Geral do assunto "{payload.os_subject}".',
            )
    rule = db.scalar(
        select(ScoringSubjectRule).options(selectinload(ScoringSubjectRule.group)).where(ScoringSubjectRule.id == rule.id)
    )
    return _serialize_subject_rule(db, rule)


@router.post("/scoring-matrix/subjects/link-to-group/bulk", response_model=list[ScoringSubjectRuleOut])
def link_subjects_to_group_bulk(payload: SubjectLinkToGroupBulkRequest, db: Session = Depends(get_db), user: User = Depends(require_permission("scoring:write"))):
    results = [_link_subject_rule(db, item) for item in payload.items]
    rules = [rule for rule, _ in results]
    total_cascaded = sum(count for _, count in results)
    db.flush()
    for rule in rules:
        record_audit_log(db, user, "link_to_group", "scoring_subject_rules", rule.id, None, snapshot(rule))
    db.commit()
    if total_cascaded:
        with SessionLocal() as recalculation_db:
            recalculate_current_period(
                recalculation_db,
                triggered_by=user.id,
                execution_note="Recálculo automático após classificar o Tipo Geral de assuntos em lote.",
            )
    rule_ids = [rule.id for rule in rules]
    persisted_rules = list(
        db.scalars(
            select(ScoringSubjectRule)
            .options(selectinload(ScoringSubjectRule.group))
            .where(ScoringSubjectRule.id.in_(rule_ids))
        )
    )
    by_id = {rule.id: rule for rule in persisted_rules}
    stats = _subject_rule_stats_map(db, persisted_rules)
    return [_serialize_subject_rule(db, by_id[rule_id], stats.get(rule_id)) for rule_id in rule_ids if rule_id in by_id]


@router.get("/diagnoses/imported", response_model=list[ImportedDiagnosisOut])
def list_imported_diagnoses(
    calculation_run_id: int | None = None,
    reference_month: int | None = Query(default=None, ge=1, le=12),
    reference_year: int | None = Query(default=None, ge=2000),
    regional: str | None = None,
    db: Session = Depends(get_db),
):
    run: CalculationRun | None = db.get(CalculationRun, calculation_run_id) if calculation_run_id else latest_run(db)
    now = datetime.now(timezone.utc)
    month = reference_month or (run.reference_month if run else now.month)
    year = reference_year or (run.reference_year if run else now.year)
    selected_regional = regional if regional is not None else (run.regional if run else None)
    with performance_step("scoring.imported-diagnoses", "aggregate_imported_diagnoses"):
        return imported_diagnosis_stats(db, month, year, selected_regional)


@router.get("/diagnoses/unmapped", response_model=list[ImportedDiagnosisOut])
def list_unmapped_diagnoses(
    calculation_run_id: int | None = None,
    reference_month: int | None = Query(default=None, ge=1, le=12),
    reference_year: int | None = Query(default=None, ge=2000),
    regional: str | None = None,
    db: Session = Depends(get_db),
):
    run: CalculationRun | None = db.get(CalculationRun, calculation_run_id) if calculation_run_id else latest_run(db)
    now = datetime.now(timezone.utc)
    month = reference_month or (run.reference_month if run else now.month)
    year = reference_year or (run.reference_year if run else now.year)
    selected_regional = regional if regional is not None else (run.regional if run else None)
    with performance_step("scoring.unmapped-diagnoses", "aggregate_unmapped_diagnoses"):
        return imported_diagnosis_stats(db, month, year, selected_regional, only_unmapped=True)


@router.get("/scoring-matrix/unmapped-diagnoses", response_model=list[ImportedDiagnosisOut])
def list_unmapped_diagnoses_alias(
    calculation_run_id: int | None = None,
    reference_month: int | None = Query(default=None, ge=1, le=12),
    reference_year: int | None = Query(default=None, ge=2000),
    regional: str | None = None,
    db: Session = Depends(get_db),
):
    return list_unmapped_diagnoses(calculation_run_id, reference_month, reference_year, regional, db)


@router.post("/scoring-matrix/diagnoses/configure", response_model=DiagnosisPenaltyRuleOut)
def configure_diagnosis_rule(payload: DiagnosisConfigureRequest, db: Session = Depends(get_db), user: User = Depends(require_permission("penalties:write"))):
    rule = _configure_diagnosis_rule(db, payload)
    db.flush()
    record_audit_log(db, user, "configure", "diagnosis_penalty_rules", rule.id, None, snapshot(rule))
    db.commit()
    db.refresh(rule)
    return rule


@router.post("/scoring-matrix/diagnoses/configure/bulk", response_model=list[DiagnosisPenaltyRuleOut])
def configure_diagnosis_rules_bulk(payload: DiagnosisConfigureBulkRequest, db: Session = Depends(get_db), user: User = Depends(require_permission("penalties:write"))):
    rules = [_configure_diagnosis_rule(db, item) for item in payload.items]
    db.flush()
    for rule in rules:
        record_audit_log(db, user, "configure", "diagnosis_penalty_rules", rule.id, None, snapshot(rule))
    db.commit()
    for rule in rules:
        db.refresh(rule)
    return rules


