from math import isfinite

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_permission
from app.db.session import get_db
from app.models import DiagnosisPenaltyRule, HealthRule, RecurrenceClassificationRule, SlaPenaltyRule, User
from app.schemas import (
    DiagnosisPenaltyRuleCreate,
    DiagnosisPenaltyRuleOut,
    DiagnosisPenaltyRuleUpdate,
    HealthRuleCreate,
    HealthRuleOut,
    HealthRuleUpdate,
    RecurrenceClassificationRuleCreate,
    RecurrenceClassificationRuleOut,
    RecurrenceClassificationRuleUpdate,
    SlaPenaltyRuleCreate,
    SlaPenaltyRuleOut,
    SlaPenaltyRuleUpdate,
)
from app.services.audit_log import record_audit_log, snapshot

router = APIRouter(tags=["rules"], dependencies=[Depends(require_permission("scoring:read"))])

ALLOWED_DIAGNOSIS_ACTIONS = {"subtract_points", "cancel_points", "no_penalty", "requires_review", "force_points"}
ALLOWED_SLA_CONDITIONS = {"status_sla_out_of_time", "sla_hours_greater_than", "closed_after_deadline"}
ALLOWED_SLA_PENALTIES = {"none", "subtract_points", "percentage_reduction", "cancel_points", "requires_review"}
ALLOWED_RECURRENCE_CLASSIFICATIONS = {
    "recorrencia_operacional",
    "reincidencia_tecnica",
    "garantia",
    "os_nao_reincidente",
    "demandas_diferentes",
    "nao_identificado",
}


def _validate_health_rule_payload(updates: dict) -> None:
    for field in ("min_sla", "max_recurrence_rate"):
        if field in updates and updates[field] is None:
            raise HTTPException(status_code=422, detail="SLA mínimo e reincidência máxima são obrigatórios.")
        if field in updates and (not isfinite(float(updates[field])) or float(updates[field]) < 0 or float(updates[field]) > 100):
            raise HTTPException(status_code=422, detail="SLA mínimo e reincidência máxima devem ficar entre 0 e 100.")
    if "multiplier" in updates and updates["multiplier"] is None:
        raise HTTPException(status_code=422, detail="Multiplicador é obrigatório.")
    if "multiplier" in updates and (not isfinite(float(updates["multiplier"])) or float(updates["multiplier"]) < 0):
        raise HTTPException(status_code=422, detail="Multiplicador deve ser um número maior ou igual a zero.")
    if "condition_operator" in updates and updates["condition_operator"] not in {"and", "or", "fallback"}:
        raise HTTPException(status_code=422, detail="Operador da faixa de saúde inválido.")


@router.get("/diagnosis-penalty-rules", response_model=list[DiagnosisPenaltyRuleOut])
def list_diagnosis_penalty_rules(db: Session = Depends(get_db)):
    return db.scalars(select(DiagnosisPenaltyRule).order_by(DiagnosisPenaltyRule.diagnosis_name.asc())).all()


@router.post("/diagnosis-penalty-rules", response_model=DiagnosisPenaltyRuleOut, status_code=201)
def create_diagnosis_penalty_rule(payload: DiagnosisPenaltyRuleCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("penalties:write"))):
    if payload.action_type not in ALLOWED_DIAGNOSIS_ACTIONS:
        raise HTTPException(status_code=422, detail="Tipo de ação de diagnóstico inválido.")

    exists = db.scalar(select(DiagnosisPenaltyRule).where(DiagnosisPenaltyRule.diagnosis_name == payload.diagnosis_name))
    if exists:
        raise HTTPException(status_code=409, detail="Diagnóstico já possui regra configurada.")

    rule = DiagnosisPenaltyRule(**payload.model_dump())
    db.add(rule)
    db.flush()
    record_audit_log(db, user, "create", "diagnosis_penalty_rules", rule.id, None, snapshot(rule))
    db.commit()
    db.refresh(rule)
    return rule


@router.put("/diagnosis-penalty-rules/{rule_id}", response_model=DiagnosisPenaltyRuleOut)
def update_diagnosis_penalty_rule(
    rule_id: int,
    payload: DiagnosisPenaltyRuleUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("penalties:write")),
):
    rule = db.get(DiagnosisPenaltyRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Regra de diagnóstico não encontrada.")

    updates = payload.model_dump(exclude_unset=True)
    if "action_type" in updates and updates["action_type"] not in ALLOWED_DIAGNOSIS_ACTIONS:
        raise HTTPException(status_code=422, detail="Tipo de ação de diagnóstico inválido.")

    before = snapshot(rule)
    for field, value in updates.items():
        setattr(rule, field, value)
    record_audit_log(db, user, "update", "diagnosis_penalty_rules", rule.id, before, snapshot(rule))
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/sla-penalty-rules", response_model=list[SlaPenaltyRuleOut])
def list_sla_penalty_rules(db: Session = Depends(get_db)):
    return db.scalars(select(SlaPenaltyRule).order_by(SlaPenaltyRule.id.asc())).all()


@router.post("/sla-penalty-rules", response_model=SlaPenaltyRuleOut, status_code=201)
def create_sla_penalty_rule(payload: SlaPenaltyRuleCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("penalties:write"))):
    if payload.condition_type not in ALLOWED_SLA_CONDITIONS:
        raise HTTPException(status_code=422, detail="Condição de SLA inválida.")
    if payload.penalty_type not in ALLOWED_SLA_PENALTIES:
        raise HTTPException(status_code=422, detail="Tipo de penalidade SLA inválido.")

    rule = SlaPenaltyRule(**payload.model_dump())
    db.add(rule)
    db.flush()
    record_audit_log(db, user, "create", "sla_penalty_rules", rule.id, None, snapshot(rule))
    db.commit()
    db.refresh(rule)
    return rule


@router.put("/sla-penalty-rules/{rule_id}", response_model=SlaPenaltyRuleOut)
def update_sla_penalty_rule(rule_id: int, payload: SlaPenaltyRuleUpdate, db: Session = Depends(get_db), user: User = Depends(require_permission("penalties:write"))):
    rule = db.get(SlaPenaltyRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Regra de SLA não encontrada.")

    updates = payload.model_dump(exclude_unset=True)
    if "condition_type" in updates and updates["condition_type"] not in ALLOWED_SLA_CONDITIONS:
        raise HTTPException(status_code=422, detail="Condição de SLA inválida.")
    if "penalty_type" in updates and updates["penalty_type"] not in ALLOWED_SLA_PENALTIES:
        raise HTTPException(status_code=422, detail="Tipo de penalidade SLA inválido.")

    before = snapshot(rule)
    for field, value in updates.items():
        setattr(rule, field, value)
    record_audit_log(db, user, "update", "sla_penalty_rules", rule.id, before, snapshot(rule))
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/recurrence-classification-rules", response_model=list[RecurrenceClassificationRuleOut])
def list_recurrence_classification_rules(db: Session = Depends(get_db)):
    return db.scalars(
        select(RecurrenceClassificationRule).order_by(
            RecurrenceClassificationRule.priority.asc(),
            RecurrenceClassificationRule.id.asc(),
        )
    ).all()


@router.post("/recurrence-classification-rules", response_model=RecurrenceClassificationRuleOut, status_code=201)
def create_recurrence_classification_rule(
    payload: RecurrenceClassificationRuleCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("penalties:write")),
):
    if payload.classification not in ALLOWED_RECURRENCE_CLASSIFICATIONS:
        raise HTTPException(status_code=422, detail="Classificação de reincidência inválida.")
    rule = RecurrenceClassificationRule(**payload.model_dump())
    db.add(rule)
    db.flush()
    record_audit_log(db, user, "create", "recurrence_classification_rules", rule.id, None, snapshot(rule))
    db.commit()
    db.refresh(rule)
    return rule


@router.put("/recurrence-classification-rules/{rule_id}", response_model=RecurrenceClassificationRuleOut)
def update_recurrence_classification_rule(
    rule_id: int,
    payload: RecurrenceClassificationRuleUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("penalties:write")),
):
    rule = db.get(RecurrenceClassificationRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Regra de reincidência não encontrada.")

    updates = payload.model_dump(exclude_unset=True)
    if "classification" in updates and updates["classification"] not in ALLOWED_RECURRENCE_CLASSIFICATIONS:
        raise HTTPException(status_code=422, detail="Classificação de reincidência inválida.")

    before = snapshot(rule)
    for field, value in updates.items():
        setattr(rule, field, value)
    record_audit_log(db, user, "update", "recurrence_classification_rules", rule.id, before, snapshot(rule))
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/recurrence-classification-rules/{rule_id}", response_model=RecurrenceClassificationRuleOut)
def delete_recurrence_classification_rule(rule_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission("penalties:write"))):
    rule = db.get(RecurrenceClassificationRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Regra de reincidência não encontrada.")

    snapshot = RecurrenceClassificationRuleOut.model_validate(rule)
    record_audit_log(db, user, "delete", "recurrence_classification_rules", rule.id, snapshot, None)
    db.delete(rule)
    db.commit()
    return snapshot


@router.get("/health-rules", response_model=list[HealthRuleOut])
def list_health_rules(db: Session = Depends(get_db)):
    return db.scalars(select(HealthRule).order_by(HealthRule.id.asc())).all()


@router.post("/health-rules", response_model=HealthRuleOut, status_code=201)
def create_health_rule(payload: HealthRuleCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("health_rules:write"))):
    _validate_health_rule_payload(payload.model_dump())
    rule = HealthRule(**payload.model_dump())
    db.add(rule)
    db.flush()
    record_audit_log(db, user, "create", "health_rules", rule.id, None, snapshot(rule))
    db.commit()
    db.refresh(rule)
    return rule


@router.put("/health-rules/{rule_id}", response_model=HealthRuleOut)
def update_health_rule(rule_id: int, payload: HealthRuleUpdate, db: Session = Depends(get_db), user: User = Depends(require_permission("health_rules:write"))):
    rule = db.get(HealthRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Regra de saúde operacional não encontrada.")

    updates = payload.model_dump(exclude_unset=True)
    _validate_health_rule_payload(updates)
    before = snapshot(rule)
    for field, value in updates.items():
        setattr(rule, field, value)
    record_audit_log(db, user, "update", "health_rules", rule.id, before, snapshot(rule))
    db.commit()
    db.refresh(rule)
    return rule
