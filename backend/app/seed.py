from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AppSetting,
    DiagnosisPenaltyRule,
    HealthRule,
    RecurrenceClassificationRule,
    ScoringGroup,
    SlaPenaltyRule,
)
from app.services.calculation import upsert_setting


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
        "Grupos padrão removidos manualmente para o seed automático não recriar.",
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
        "Grupos padrão removidos manualmente para o seed automático não recriar.",
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


def ensure_setting(db: Session, key: str, value: str, description: str) -> None:
    if db.scalar(select(AppSetting).where(AppSetting.key == key)):
        return
    upsert_setting(db, key, value, description)


def seed_database(db: Session, include_demo: bool = False) -> None:
    ensure_setting(db, "point_value", "2.50", "Valor monetário pago por ponto final.")
    ensure_setting(db, "recurrence_window_days", "30", "Janela em dias para reconhecer reincidência operacional.")
    ensure_setting(db, "recurrence_identity_fields", "login,contract", "Campos usados para vincular O.S do mesmo cliente na reincidência.")
    ensure_setting(db, "warranty_scores", "true", "Define se garantia resolvida também gera pontuação.")
    ensure_setting(db, "warranty_mode", "score_full", "Regra de garantia: score_full, score_reduced, no_points ou requires_review.")
    ensure_setting(db, "warranty_reduction_percentage", "0", "Percentual de redução quando garantia pontua com redução.")
    ensure_setting(db, "recurrence_action", "annul_original", "Regra de reincidência: annul_original, subtract_original, no_penalty ou requires_review.")
    ensure_setting(db, "recurrence_penalty_points", "0", "Desconto fixo quando reincidência usa subtract_original.")
    ensure_setting(db, "payment_cap", "0", "Teto de pagamento. Zero significa sem teto.")

    _get_or_create_group(db, "Manutenção", "Precificação padrão para manutenções operacionais.", 15)
    _get_or_create_group(
        db,
        "Ativação / Mudança de Endereço / Retorno",
        "Precificação padrão para ativação, mudança de endereço e retorno.",
        10,
    )
    _get_or_create_group(db, "Mudança de Tecnologia", "Precificação padrão para mudanças de tecnologia.", 15)
    _get_or_create_group(db, "Recolhimento", "Precificação padrão para recolhimentos.", 5)

    diagnosis_rules = [
        ("Resolvido", 0, "no_penalty", "Diagnóstico conclusivo sem penalidade."),
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
                "name": "Reincidência de Manutenção",
                "original_os_type_pattern": "Manutenção",
                "return_os_type_pattern": "Manutenção",
                "classification": "reincidencia_tecnica",
                "discount_points": True,
                "max_days": 30,
                "priority": 10,
                "description": "Regra padrão: nova manutenção do mesmo vínculo dentro da janela caracteriza reincidência.",
            },
            {
                "name": "Reincidência de Ativação",
                "original_os_type_pattern": "Ativação",
                "return_os_type_pattern": "Manutenção",
                "classification": "garantia",
                "discount_points": True,
                "max_days": 30,
                "priority": 20,
                "description": "Regra padrão: manutenção após ativação dentro da janela caracteriza retorno operacional.",
            },
            {
                "name": "Alteração de Endereço não reincide",
                "original_os_type_pattern": "Mud. de Endereço",
                "return_os_type_pattern": "Mud. de Endereço",
                "classification": "os_nao_reincidente",
                "discount_points": False,
                "max_days": 30,
                "priority": 80,
                "description": "Regra padrão: alteração de endereço recorrente é tratada como demanda diferente.",
            },
            {
                "name": "Mudança de Tecnologia não reincide",
                "original_os_type_pattern": "Mud. de Tecnologia",
                "return_os_type_pattern": "Mud. de Tecnologia",
                "classification": "os_nao_reincidente",
                "discount_points": False,
                "max_days": 30,
                "priority": 90,
                "description": "Regra padrão: mudança de tecnologia recorrente é tratada como demanda diferente.",
            },
        ]
        for rule in recurrence_rules:
            db.add(RecurrenceClassificationRule(active=True, **rule))

    health_rules = [
        ("Excelente", 90, 3, 1.2),
        ("Boa", 80, 6, 1.0),
        ("Atenção", 70, 10, 0.8),
        ("Crítica", 0, 100, 0.6),
    ]
    for name, min_sla, max_recurrence, multiplier in health_rules:
        exists = db.scalar(select(HealthRule).where(HealthRule.name == name))
        if not exists:
            db.add(
                HealthRule(
                    name=name,
                    min_sla=min_sla,
                    max_recurrence_rate=max_recurrence,
                    multiplier=multiplier,
                    active=True,
                )
            )

    db.commit()
