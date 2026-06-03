from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AppSetting,
    DiagnosisPenaltyRule,
    HealthRule,
    RecurrenceClassificationRule,
    ScoringGroup,
    ScoringRule,
    ScoringSubjectRule,
    SlaPenaltyRule,
)
from app.services.calculation import upsert_setting
from app.services.scoring_matrix import is_demo_subject


DELETED_DEFAULT_GROUPS_SETTING = "deleted_default_scoring_groups"


def deleted_default_groups(db: Session) -> set[str]:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == DELETED_DEFAULT_GROUPS_SETTING))
    if not setting or not setting.value.strip():
        return set()
    return {item.strip().casefold() for item in setting.value.split("|") if item.strip()}


def remember_deleted_default_group(db: Session, name: str) -> None:
    deleted = deleted_default_groups(db)
    deleted.add(name.strip().casefold())
    upsert_setting(
        db,
        DELETED_DEFAULT_GROUPS_SETTING,
        "|".join(sorted(deleted)),
        "Grupos padrao removidos manualmente para o seed automatico nao recriar.",
    )


def forget_deleted_default_group(db: Session, name: str) -> None:
    deleted = deleted_default_groups(db)
    normalized = name.strip().casefold()
    if normalized not in deleted:
        return
    deleted.remove(normalized)
    upsert_setting(
        db,
        DELETED_DEFAULT_GROUPS_SETTING,
        "|".join(sorted(deleted)),
        "Grupos padrao removidos manualmente para o seed automatico nao recriar.",
    )


def _get_or_create_group(
    db: Session,
    name: str,
    description: str,
    default_points: float,
) -> ScoringGroup | None:
    if name.strip().casefold() in deleted_default_groups(db):
        return None

    group = db.scalar(select(ScoringGroup).where(ScoringGroup.name == name))
    if group:
        return group

    group = ScoringGroup(name=name, description=description, default_points=default_points, active=True)
    db.add(group)
    db.flush()
    return group


def _get_or_create_subject_rule(
    db: Session,
    group: ScoringGroup,
    os_type: str,
    os_subject: str,
    points: float,
) -> ScoringSubjectRule:
    rule = db.scalar(
        select(ScoringSubjectRule)
        .where(ScoringSubjectRule.os_type == os_type)
        .where(ScoringSubjectRule.os_subject == os_subject)
    )
    if rule:
        return rule

    use_default = float(points) == float(group.default_points)
    rule = ScoringSubjectRule(
        group_id=group.id,
        os_type=os_type,
        os_subject=os_subject,
        custom_points=None if use_default else points,
        use_group_default=use_default,
        active=True,
    )
    db.add(rule)
    db.flush()
    return rule


def migrate_legacy_scoring_rules(db: Session) -> None:
    legacy_rules = list(db.scalars(select(ScoringRule)))
    for legacy in legacy_rules:
        group = db.get(ScoringGroup, legacy.group_id)
        if not group or not legacy.os_subject or is_demo_subject(legacy.os_type, legacy.os_subject):
            continue
        _get_or_create_subject_rule(db, group, legacy.os_type, legacy.os_subject, legacy.points)


def ensure_setting(db: Session, key: str, value: str, description: str) -> None:
    if db.scalar(select(AppSetting).where(AppSetting.key == key)):
        return
    upsert_setting(db, key, value, description)


def seed_database(db: Session, include_demo: bool = False) -> None:
    ensure_setting(db, "point_value", "2.50", "Valor monetario pago por ponto final.")
    ensure_setting(db, "recurrence_window_days", "30", "Janela em dias para reconhecer reincidencia operacional.")
    ensure_setting(db, "recurrence_identity_fields", "login,contract", "Campos usados para vincular O.S do mesmo cliente na reincidencia.")
    ensure_setting(db, "warranty_scores", "true", "Define se garantia resolvida tambem gera pontuacao.")
    ensure_setting(db, "warranty_mode", "score_full", "Regra de garantia: score_full, score_reduced, no_points ou requires_review.")
    ensure_setting(db, "warranty_reduction_percentage", "0", "Percentual de reducao quando garantia pontua com reducao.")
    ensure_setting(db, "recurrence_action", "annul_original", "Regra de reincidencia: annul_original, subtract_original, no_penalty ou requires_review.")
    ensure_setting(db, "recurrence_penalty_points", "0", "Desconto fixo quando reincidencia usa subtract_original.")
    ensure_setting(db, "payment_cap", "0", "Teto de pagamento. Zero significa sem teto.")

    _get_or_create_group(db, "Manutencao", "Precificacao padrao para manutencoes operacionais.", 15)
    _get_or_create_group(
        db,
        "Ativacao / Mudanca de Endereco / Retorno",
        "Precificacao padrao para ativacao, mudanca de endereco e retorno.",
        10,
    )
    _get_or_create_group(db, "Mudanca de Tecnologia", "Precificacao padrao para mudancas de tecnologia.", 15)
    _get_or_create_group(db, "Recolhimento", "Precificacao padrao para recolhimentos.", 5)

    migrate_legacy_scoring_rules(db)

    diagnosis_rules = [
        ("Resolvido", 0, "no_penalty", "Diagnostico conclusivo sem penalidade."),
    ]
    for diagnosis_name, penalty_points, action_type, description in diagnosis_rules:
        exists = db.scalar(select(DiagnosisPenaltyRule).where(DiagnosisPenaltyRule.diagnosis_name == diagnosis_name))
        if not exists:
            db.add(
                DiagnosisPenaltyRule(
                    diagnosis_name=diagnosis_name,
                    penalty_points=penalty_points,
                    force_points_value=None,
                    action_type=action_type,
                    description=description,
                    active=True,
                )
            )

    if not db.scalar(select(SlaPenaltyRule).where(SlaPenaltyRule.condition_type == "status_sla_out_of_time")):
        db.add(
            SlaPenaltyRule(
                name="Fora do prazo",
                condition_type="status_sla_out_of_time",
                penalty_type="none",
                penalty_value=0,
                active=True,
            )
        )

    if not db.scalar(select(RecurrenceClassificationRule)):
        recurrence_rules = [
            {
                "name": "Reincidencia de Manutencao",
                "original_os_type_pattern": "Manutencao",
                "return_os_type_pattern": "Manutencao",
                "classification": "reincidencia_tecnica",
                "discount_points": True,
                "max_days": 30,
                "priority": 10,
                "description": "Regra padrao: nova manutencao do mesmo vinculo dentro da janela caracteriza reincidencia.",
            },
            {
                "name": "Reincidencia de Ativacao",
                "original_os_type_pattern": "Ativacao",
                "return_os_type_pattern": "Manutencao",
                "classification": "garantia",
                "discount_points": True,
                "max_days": 30,
                "priority": 20,
                "description": "Regra padrao: manutencao apos ativacao dentro da janela caracteriza retorno operacional.",
            },
            {
                "name": "Alteracao de Endereco nao reincide",
                "original_os_type_pattern": "Mud. de Endereco",
                "return_os_type_pattern": "Mud. de Endereco",
                "classification": "os_nao_reincidente",
                "discount_points": False,
                "max_days": 30,
                "priority": 80,
                "description": "Regra padrao: alteracao de endereco recorrente e tratada como demanda diferente.",
            },
            {
                "name": "Mudanca de Tecnologia nao reincide",
                "original_os_type_pattern": "Mud. de Tecnologia",
                "return_os_type_pattern": "Mud. de Tecnologia",
                "classification": "os_nao_reincidente",
                "discount_points": False,
                "max_days": 30,
                "priority": 90,
                "description": "Regra padrao: mudanca de tecnologia recorrente e tratada como demanda diferente.",
            },
        ]
        for rule in recurrence_rules:
            db.add(RecurrenceClassificationRule(active=True, **rule))

    health_rules = [
        ("Excelente", 90, 3, 1.2, "and"),
        ("Boa", 80, 6, 1.0, "and"),
        ("Atencao", 70, 10, 0.8, "or"),
        ("Critica", 0, 100, 0.6, "fallback"),
    ]
    for name, min_sla, max_recurrence, multiplier, operator in health_rules:
        exists = db.scalar(select(HealthRule).where(HealthRule.name == name))
        if not exists:
            db.add(
                HealthRule(
                    name=name,
                    min_sla=min_sla,
                    max_recurrence_rate=max_recurrence,
                    multiplier=multiplier,
                    condition_operator=operator,
                    active=True,
                )
            )

    db.commit()
