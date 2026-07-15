from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AppSetting,
    DiagnosisPenaltyRule,
    GamificationConfigVersion,
    HealthRule,
    RecurrenceClassificationRule,
    ScoringGroup,
    ScoringSubjectRule,
    SlaPenaltyRule,
)
from app.services.calculation import upsert_setting
from app.seed import deleted_default_groups


CONFIG_NAME = "gamification_rules_config"

DEFAULT_SETTINGS = {
    "point_value": ("2.50", "Valor monetário pago por ponto final."),
    "recurrence_window_days": ("30", "Janela em dias para reconhecer reincidência operacional."),
    "recurrence_identity_fields": ("login,contract", "Campos usados para vincular O.S do mesmo cliente na reincidência."),
    "warranty_scores": ("true", "Compatibilidade: garantia resolvida também gera pontuação."),
    "warranty_mode": ("score_full", "Regra de garantia: score_full, score_reduced, no_points ou requires_review."),
    "warranty_reduction_percentage": ("0", "Percentual de redução quando garantia pontua com redução."),
    "recurrence_action": ("annul_original", "Regra de reincidência: annul_original, subtract_original, no_penalty ou requires_review."),
    "recurrence_penalty_points": ("0", "Desconto fixo quando reincidência usa subtract_original."),
    "payment_cap": ("0", "Teto de pagamento. Zero significa sem teto."),
    "health_below_minimum_multiplier": ("0", "Multiplicador aplicado quando a regional não atinge nenhuma faixa ativa de saúde operacional."),
}

DEFAULT_GROUPS = [
    ("Manutenção", "Precificação padrão para manutenções operacionais.", 15),
    (
        "Ativação / Mudança de Endereço / Retorno",
        "Precificação padrão para ativação, mudança de endereço e retorno.",
        10,
    ),
    ("Mudança de Tecnologia", "Precificação padrão para mudanças de tecnologia.", 15),
    ("Recolhimento", "Precificação padrão para recolhimentos.", 5),
]


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "sim", "yes", "ativo", "active"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def serialize_current_config(db: Session) -> dict[str, Any]:
    latest_version = db.scalar(
        select(GamificationConfigVersion)
        .where(GamificationConfigVersion.active.is_(True))
        .order_by(GamificationConfigVersion.updated_at.desc(), GamificationConfigVersion.id.desc())
        .limit(1)
    )
    settings = {setting.key: setting.value for setting in db.scalars(select(AppSetting).order_by(AppSetting.key.asc()))}
    return {
        "name": CONFIG_NAME,
        "version_id": latest_version.id if latest_version else None,
        "exported_at": _now().isoformat(),
        "settings": settings,
        "scoring_groups": [
            {
                "id": group.id,
                "name": group.name,
                "description": group.description,
                "default_points": group.default_points,
                "point_value_override": group.point_value_override,
                "active": group.active,
            }
            for group in db.scalars(select(ScoringGroup).order_by(ScoringGroup.name.asc()))
        ],
        "scoring_subject_rules": [
            {
                "id": rule.id,
                "group_id": rule.group_id,
                "group_name": rule.group.name if rule.group else None,
                "os_type": rule.os_type,
                "os_subject": rule.os_subject,
                "subject_category": rule.subject_category,
                "custom_points": rule.custom_points,
                "point_value_override": rule.point_value_override,
                "use_group_default": rule.use_group_default,
                "active": rule.active,
            }
            for rule in db.scalars(select(ScoringSubjectRule).order_by(ScoringSubjectRule.os_type.asc(), ScoringSubjectRule.os_subject.asc()))
        ],
        "diagnosis_penalty_rules": [
            {
                "id": rule.id,
                "diagnosis_name": rule.diagnosis_name,
                "action_type": rule.action_type,
                "penalty_points": rule.penalty_points,
                "force_points_value": rule.force_points_value,
                "description": rule.description,
                "active": rule.active,
            }
            for rule in db.scalars(select(DiagnosisPenaltyRule).order_by(DiagnosisPenaltyRule.diagnosis_name.asc()))
        ],
        "sla_penalty_rules": [
            {
                "id": rule.id,
                "name": rule.name,
                "condition_type": rule.condition_type,
                "penalty_type": rule.penalty_type,
                "penalty_value": rule.penalty_value,
                "active": rule.active,
            }
            for rule in db.scalars(select(SlaPenaltyRule).order_by(SlaPenaltyRule.id.asc()))
        ],
        "recurrence_classification_rules": [
            {
                "id": rule.id,
                "name": rule.name,
                "os_type_pattern": rule.os_type_pattern,
                "os_subject_pattern": rule.os_subject_pattern,
                "diagnosis_pattern": rule.diagnosis_pattern,
                "original_os_type_pattern": rule.original_os_type_pattern,
                "original_os_subject_pattern": rule.original_os_subject_pattern,
                "return_os_type_pattern": rule.return_os_type_pattern,
                "return_os_subject_pattern": rule.return_os_subject_pattern,
                "return_diagnosis_pattern": rule.return_diagnosis_pattern,
                "ignore_diagnosis_pattern": rule.ignore_diagnosis_pattern,
                "classification": rule.classification,
                "discount_points": rule.discount_points,
                "max_days": rule.max_days,
                "require_same_subject": rule.require_same_subject,
                "require_same_diagnosis": rule.require_same_diagnosis,
                "priority": rule.priority,
                "description": rule.description,
                "active": rule.active,
            }
            for rule in db.scalars(
                select(RecurrenceClassificationRule).order_by(
                    RecurrenceClassificationRule.priority.asc(),
                    RecurrenceClassificationRule.id.asc(),
                )
            )
        ],
        "health_rules": [
            {
                "id": rule.id,
                "name": rule.name,
                "min_sla": rule.min_sla,
                "max_recurrence_rate": rule.max_recurrence_rate,
                "multiplier": rule.multiplier,
                "condition_operator": rule.condition_operator,
                "active": rule.active,
            }
            for rule in db.scalars(select(HealthRule).order_by(HealthRule.id.asc()))
        ],
    }


def save_config_version(db: Session, config: dict[str, Any], name: str = CONFIG_NAME) -> GamificationConfigVersion:
    for version in db.scalars(select(GamificationConfigVersion).where(GamificationConfigVersion.active.is_(True))):
        version.active = False

    version = GamificationConfigVersion(name=name, config_json=config, active=True)
    db.add(version)
    db.flush()
    return version


def apply_config(db: Session, config: dict[str, Any], version_name: str | None = None) -> dict[str, Any]:
    group_id_map: dict[int, int] = {}
    group_name_map: dict[str, int] = {}

    for key, value in (config.get("settings") or {}).items():
        upsert_setting(db, str(key), str(value))

    for item in config.get("scoring_groups") or []:
        group = db.get(ScoringGroup, item.get("id")) if item.get("id") else None
        if not group and item.get("name"):
            group = db.scalar(select(ScoringGroup).where(ScoringGroup.name == str(item["name"])))
        if not group:
            group = ScoringGroup(name=str(item.get("name") or "Novo grupo"), default_points=float(item.get("default_points") or 0))
            db.add(group)
            db.flush()

        if item.get("id"):
            group_id_map[int(item["id"])] = group.id
        if group.name:
            group_name_map[group.name] = group.id
        group.name = str(item.get("name") or group.name)
        group.description = item.get("description")
        group.default_points = float(item.get("default_points") or 0)
        group.point_value_override = _float_or_none(item.get("point_value_override"))
        group.active = _bool(item.get("active"), True)
        group.updated_at = _now()
        group_name_map[group.name] = group.id

    db.flush()

    for item in config.get("scoring_subject_rules") or []:
        os_type = str(item.get("os_type") or "").strip()
        os_subject = str(item.get("os_subject") or "").strip()
        if not os_type or not os_subject:
            continue

        rule = db.get(ScoringSubjectRule, item.get("id")) if item.get("id") else None
        if not rule:
            rule = db.scalar(
                select(ScoringSubjectRule)
                .where(ScoringSubjectRule.os_type == os_type)
                .where(ScoringSubjectRule.os_subject == os_subject)
            )

        group_id = group_id_map.get(int(item["group_id"])) if item.get("group_id") else None
        if not group_id and item.get("group_name"):
            group_id = group_name_map.get(str(item["group_name"]))
        if not group_id:
            continue

        if not rule:
            rule = ScoringSubjectRule(group_id=group_id, os_type=os_type, os_subject=os_subject)
            db.add(rule)

        rule.group_id = group_id
        rule.os_type = os_type
        rule.os_subject = os_subject
        rule.subject_category = item.get("subject_category") or None
        rule.custom_points = _float_or_none(item.get("custom_points"))
        rule.point_value_override = _float_or_none(item.get("point_value_override"))
        rule.use_group_default = _bool(item.get("use_group_default"), True)
        rule.active = _bool(item.get("active"), True)
        rule.updated_at = _now()

    for item in config.get("diagnosis_penalty_rules") or []:
        diagnosis_name = str(item.get("diagnosis_name") or "").strip()
        if not diagnosis_name:
            continue
        rule = db.get(DiagnosisPenaltyRule, item.get("id")) if item.get("id") else None
        if not rule:
            rule = db.scalar(select(DiagnosisPenaltyRule).where(DiagnosisPenaltyRule.diagnosis_name == diagnosis_name))
        if not rule:
            rule = DiagnosisPenaltyRule(diagnosis_name=diagnosis_name)
            db.add(rule)
        rule.diagnosis_name = diagnosis_name
        rule.action_type = str(item.get("action_type") or "no_penalty")
        rule.penalty_points = float(item.get("penalty_points") or 0)
        rule.force_points_value = _float_or_none(item.get("force_points_value"))
        rule.description = item.get("description")
        rule.active = _bool(item.get("active"), True)
        rule.updated_at = _now()

    for item in config.get("sla_penalty_rules") or []:
        name = str(item.get("name") or item.get("condition_type") or "Regra SLA").strip()
        rule = db.get(SlaPenaltyRule, item.get("id")) if item.get("id") else None
        if not rule:
            rule = db.scalar(select(SlaPenaltyRule).where(SlaPenaltyRule.name == name))
        if not rule:
            rule = SlaPenaltyRule(name=name)
            db.add(rule)
        rule.name = name
        rule.condition_type = str(item.get("condition_type") or "status_sla_out_of_time")
        rule.penalty_type = str(item.get("penalty_type") or "none")
        rule.penalty_value = float(item.get("penalty_value") or 0)
        rule.active = _bool(item.get("active"), False)
        rule.updated_at = _now()

    for item in config.get("recurrence_classification_rules") or []:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        rule = db.get(RecurrenceClassificationRule, item.get("id")) if item.get("id") else None
        if not rule:
            rule = db.scalar(select(RecurrenceClassificationRule).where(RecurrenceClassificationRule.name == name))
        if not rule:
            rule = RecurrenceClassificationRule(name=name)
            db.add(rule)
        rule.name = name
        rule.os_type_pattern = item.get("os_type_pattern") or None
        rule.os_subject_pattern = item.get("os_subject_pattern") or None
        rule.diagnosis_pattern = item.get("diagnosis_pattern") or None
        rule.original_os_type_pattern = item.get("original_os_type_pattern") or None
        rule.original_os_subject_pattern = item.get("original_os_subject_pattern") or None
        rule.return_os_type_pattern = item.get("return_os_type_pattern") or None
        rule.return_os_subject_pattern = item.get("return_os_subject_pattern") or None
        rule.return_diagnosis_pattern = item.get("return_diagnosis_pattern") or None
        rule.ignore_diagnosis_pattern = item.get("ignore_diagnosis_pattern") or None
        rule.classification = str(item.get("classification") or "nao_identificado")
        rule.discount_points = _bool(item.get("discount_points"), False)
        rule.max_days = int(item["max_days"]) if item.get("max_days") not in (None, "") else None
        rule.require_same_subject = _bool(item.get("require_same_subject"), False)
        rule.require_same_diagnosis = _bool(item.get("require_same_diagnosis"), False)
        rule.priority = int(item.get("priority") or 100)
        rule.description = item.get("description")
        rule.active = _bool(item.get("active"), True)
        rule.updated_at = _now()

    for item in config.get("health_rules") or []:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        rule = db.get(HealthRule, item.get("id")) if item.get("id") else None
        if not rule:
            rule = db.scalar(select(HealthRule).where(HealthRule.name == name))
        if not rule:
            rule = HealthRule(name=name)
            db.add(rule)
        rule.name = name
        rule.min_sla = float(item.get("min_sla") or 0)
        rule.max_recurrence_rate = float(item.get("max_recurrence_rate") or 100)
        rule.multiplier = float(item.get("multiplier") or 1)
        rule.condition_operator = str(item.get("condition_operator") or "and")
        rule.active = _bool(item.get("active"), True)

    db.flush()
    current_config = serialize_current_config(db)
    save_config_version(db, current_config, version_name or str(config.get("name") or CONFIG_NAME))
    return serialize_current_config(db)


def ensure_default_logic_config(db: Session) -> dict[str, Any]:
    for key, (value, description) in DEFAULT_SETTINGS.items():
        upsert_setting(db, key, value, description)

    deleted_groups = deleted_default_groups(db)
    for name, description, points in DEFAULT_GROUPS:
        if name.strip().casefold() in deleted_groups:
            continue
        group = db.scalar(select(ScoringGroup).where(ScoringGroup.name == name))
        if not group:
            db.add(ScoringGroup(name=name, description=description, default_points=points, active=True))
        else:
            group.description = group.description or description
            group.default_points = points
            group.active = True

    if not db.scalar(select(SlaPenaltyRule).where(SlaPenaltyRule.condition_type == "status_sla_out_of_time")):
        db.add(
            SlaPenaltyRule(
                name="Fora do prazo",
                condition_type="status_sla_out_of_time",
                penalty_type="none",
                penalty_value=0,
                active=False,
            )
        )

    db.flush()
    current_config = serialize_current_config(db)
    save_config_version(db, current_config, CONFIG_NAME)
    return serialize_current_config(db)


def ensure_active_config_version(db: Session) -> None:
    exists = db.scalar(select(GamificationConfigVersion.id).where(GamificationConfigVersion.active.is_(True)).limit(1))
    if exists:
        return
    save_config_version(db, serialize_current_config(db), CONFIG_NAME)
