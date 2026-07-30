from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AppSetting,
    Collaborator,
    DiagnosisPenaltyRule,
    GamificationConfigVersion,
    HealthRule,
    LeadershipProfile,
    LeadershipRoleProfile,
    RecurrenceClassificationRule,
    ScoringGroup,
    ScoringSubjectRule,
    SlaPenaltyRule,
    default_percentage_for_role,
)
from app.services.calculation import upsert_setting
from app.services.leadership_bonus import (
    default_multiplier_for_role,
    normalize_average_source,
    normalize_regionals,
    normalize_role_type,
    replace_profile_regionals,
    validate_no_scope_overlap,
    validate_scope_regionals_required,
)
from app.seed import deleted_default_groups


def _resolve_by_id_or_name(db: Session, model: type, id_value: Any, name_stmt: Any | None) -> Any:
    """Casa um item do JSON de config com sua linha no banco.

    Prioriza o casamento pelo nome (chave unica de negocio) quando id e nome apontam para
    linhas DIFERENTES - um JSON reimportado de outro momento/ambiente pode trazer um id que
    hoje pertence a outra linha no banco, e renomea-la pro nome do item colide com a
    constraint unica (achado real: reimport travou com IntegrityError em diagnosis_name).
    """
    by_id = db.get(model, id_value) if id_value else None
    by_name = db.scalar(name_stmt) if name_stmt is not None else None
    if by_id is not None and by_name is not None and by_id is not by_name:
        return by_name
    return by_id or by_name


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
    "cpk_bonus_points": ("0.2", "Ajuste somado (na meta) ou subtraído (fora da meta) do multiplicador de saúde da regional, com base no CPK da frota."),
    "cpk_sync_enabled": ("false", "Liga a sincronização automática do CPK da frota."),
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
                "min_hours_between": rule.min_hours_between,
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
                "active": rule.active,
            }
            for rule in db.scalars(select(HealthRule).order_by(HealthRule.id.asc()))
        ],
        "collaborators": [
            {
                "id": collaborator.id,
                "name": collaborator.name,
                "role": collaborator.role,
                "regional": collaborator.regional,
                "active": collaborator.active,
                "is_registered": collaborator.is_registered,
                "ixc_employee_id": collaborator.ixc_employee_id,
                "phone": collaborator.phone,
                "email": collaborator.email,
            }
            for collaborator in db.scalars(select(Collaborator).order_by(Collaborator.name.asc()))
        ],
        "leadership_role_profiles": [
            {
                "id": role_profile.id,
                "name": role_profile.name,
                "scope_type": role_profile.scope_type,
                "default_multiplier": role_profile.default_multiplier,
                "active": role_profile.active,
            }
            for role_profile in db.scalars(select(LeadershipRoleProfile).order_by(LeadershipRoleProfile.name.asc()))
        ],
        "leadership_profiles": _serialize_leadership_profiles(db),
    }


def _serialize_leadership_profiles(db: Session) -> list[dict[str, Any]]:
    profiles = list(db.scalars(select(LeadershipProfile).order_by(LeadershipProfile.name.asc())))
    collaborator_ids = {profile.collaborator_id for profile in profiles if profile.collaborator_id}
    collaborators_by_id = (
        {c.id: c for c in db.scalars(select(Collaborator).where(Collaborator.id.in_(collaborator_ids)))}
        if collaborator_ids
        else {}
    )
    return [
        {
            "id": profile.id,
            "name": profile.name,
            "role_type": profile.role_type,
            "multiplier": profile.multiplier,
            "role_profile_id": profile.role_profile_id,
            "role_profile_name": profile.role_profile.name if profile.role_profile else None,
            "use_custom_multiplier": profile.use_custom_multiplier,
            "custom_multiplier": profile.custom_multiplier,
            "average_source": profile.average_source,
            "active": profile.active,
            # ixc_employee_id (nao collaborator_id) - o id de colaborador nao e portavel entre
            # ambientes, igual ja resolvido para "collaborators" acima (ver casamento por
            # ixc_employee_id em apply_config).
            "collaborator_ixc_employee_id": (
                collaborators_by_id[profile.collaborator_id].ixc_employee_id if profile.collaborator_id in collaborators_by_id else None
            ),
            "collaborator_name": (
                collaborators_by_id[profile.collaborator_id].name if profile.collaborator_id in collaborators_by_id else None
            ),
            "regional_names": sorted(item.regional_name for item in profile.regionals),
        }
        for profile in profiles
    ]


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
    warnings: list[str] = []

    for key, value in (config.get("settings") or {}).items():
        upsert_setting(db, str(key), str(value))

    for item in config.get("scoring_groups") or []:
        group = _resolve_by_id_or_name(
            db,
            ScoringGroup,
            item.get("id"),
            select(ScoringGroup).where(ScoringGroup.name == str(item["name"])) if item.get("name") else None,
        )
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
            warnings.append(
                f"Regra de assunto ignorada: item sem tipo geral ou assunto preenchido ({item!r})."
            )
            continue

        rule = _resolve_by_id_or_name(
            db,
            ScoringSubjectRule,
            item.get("id"),
            select(ScoringSubjectRule)
            .where(ScoringSubjectRule.os_type == os_type)
            .where(ScoringSubjectRule.os_subject == os_subject),
        )

        group_id = group_id_map.get(int(item["group_id"])) if item.get("group_id") else None
        if not group_id and item.get("group_name"):
            group_id = group_name_map.get(str(item["group_name"]))
        if not group_id:
            # Achado real: sem este aviso, uma config restaurada entre ambientes (ou depois de
            # limpar grupos zerados) perdia regras de pontuação silenciosamente - a regra
            # desaparecia da regua sem nenhum sinal pra quem aplicou a config.
            group_reference = item.get("group_name") or item.get("group_id") or "desconhecido"
            warnings.append(
                f"Regra de assunto '{os_type} / {os_subject}' ignorada: grupo '{group_reference}' não encontrado."
            )
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
        rule = _resolve_by_id_or_name(
            db,
            DiagnosisPenaltyRule,
            item.get("id"),
            select(DiagnosisPenaltyRule).where(DiagnosisPenaltyRule.diagnosis_name == diagnosis_name),
        )
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
        rule = _resolve_by_id_or_name(
            db,
            SlaPenaltyRule,
            item.get("id"),
            select(SlaPenaltyRule).where(SlaPenaltyRule.name == name),
        )
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
        rule = _resolve_by_id_or_name(
            db,
            RecurrenceClassificationRule,
            item.get("id"),
            select(RecurrenceClassificationRule).where(RecurrenceClassificationRule.name == name),
        )
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
        rule.min_hours_between = float(item["min_hours_between"]) if item.get("min_hours_between") not in (None, "") else None
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
        rule = _resolve_by_id_or_name(
            db,
            HealthRule,
            item.get("id"),
            select(HealthRule).where(HealthRule.name == name),
        )
        if not rule:
            rule = HealthRule(name=name)
            db.add(rule)
        rule.name = name
        rule.min_sla = float(item.get("min_sla") or 0)
        rule.max_recurrence_rate = float(item.get("max_recurrence_rate") or 100)
        rule.multiplier = float(item.get("multiplier") or 1)
        rule.active = _bool(item.get("active"), True)

    role_profile_id_map: dict[int, int] = {}
    role_profile_name_map: dict[str, int] = {}
    for item in config.get("leadership_role_profiles") or []:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        role_profile = _resolve_by_id_or_name(
            db,
            LeadershipRoleProfile,
            item.get("id"),
            select(LeadershipRoleProfile).where(LeadershipRoleProfile.name == name),
        )
        if not role_profile:
            role_profile = LeadershipRoleProfile(name=name)
            db.add(role_profile)
        role_profile.name = name
        role_profile.scope_type = str(item.get("scope_type") or "supervisor")
        role_profile.default_multiplier = float(item.get("default_multiplier") or 1)
        role_profile.active = _bool(item.get("active"), True)
        role_profile.updated_at = _now()
        db.flush()
        if item.get("id"):
            role_profile_id_map[int(item["id"])] = role_profile.id
        role_profile_name_map[role_profile.name] = role_profile.id

    for item in config.get("collaborators") or []:
        name = str(item.get("name") or "").strip()
        if not name:
            continue

        # Casamento por ixc_employee_id primeiro (vale entre ambientes, nao depende do nome
        # bater exato) - so cai pra nome quando o colaborador ainda nao tem esse vinculo.
        ixc_employee_id_raw = item.get("ixc_employee_id")
        ixc_employee_id = int(ixc_employee_id_raw) if ixc_employee_id_raw not in (None, "") else None

        collaborator = None
        if ixc_employee_id is not None:
            collaborator = db.scalar(select(Collaborator).where(Collaborator.ixc_employee_id == ixc_employee_id))
        if not collaborator:
            collaborator = db.scalar(select(Collaborator).where(func.lower(Collaborator.name) == name.lower()))
        if not collaborator:
            collaborator = Collaborator(name=name, role=str(item.get("role") or "Importado"), regional=str(item.get("regional") or ""))
            db.add(collaborator)
            db.flush()

        collaborator.name = name
        collaborator.role = str(item.get("role") or collaborator.role)
        collaborator.regional = str(item.get("regional") or collaborator.regional)
        collaborator.active = _bool(item.get("active"), True)
        collaborator.is_registered = _bool(item.get("is_registered"), True)
        collaborator.phone = item.get("phone") or collaborator.phone
        collaborator.email = item.get("email") or collaborator.email
        # Seguro sempre atribuir aqui: se esse ixc_employee_id ja pertencesse a OUTRO
        # colaborador, a busca por id no topo do loop ja teria encontrado e casado com ELE (nao
        # com o resultado da busca por nome) - nunca chegamos aqui com um id de outro dono.
        if ixc_employee_id is not None:
            collaborator.ixc_employee_id = ixc_employee_id

    db.flush()

    for item in config.get("leadership_profiles") or []:
        name = str(item.get("name") or "").strip()
        if not name:
            continue

        role_profile = None
        role_profile_ref = item.get("role_profile_id")
        if role_profile_ref not in (None, ""):
            resolved_role_profile_id = role_profile_id_map.get(int(role_profile_ref))
            if resolved_role_profile_id:
                role_profile = db.get(LeadershipRoleProfile, resolved_role_profile_id)
        if not role_profile and item.get("role_profile_name"):
            resolved_role_profile_id = role_profile_name_map.get(str(item["role_profile_name"]))
            if resolved_role_profile_id:
                role_profile = db.get(LeadershipRoleProfile, resolved_role_profile_id)

        try:
            role_type = normalize_role_type(role_profile.scope_type if role_profile else item.get("role_type"))
        except HTTPException as exc:
            warnings.append(f"Perfil de liderança '{name}' ignorado: {exc.detail}")
            continue

        try:
            regionals = normalize_regionals(item.get("regional_names") or [])
            validate_scope_regionals_required(role_type, regionals)
        except HTTPException as exc:
            warnings.append(f"Perfil de liderança '{name}' ignorado: {exc.detail}")
            continue

        # LeadershipProfile nao tem constraint unica de nome, ao contrario das outras entidades
        # deste arquivo - confiar no id bruto (mesmo com _resolve_by_id_or_name) e inseguro
        # mesmo dentro do MESMO reimport: apos apagar a tabela, o autoincrement pode reatribuir
        # o id antigo de um perfil a um OUTRO perfil recem-criado nesta mesma passada, e sem
        # constraint unica isso sobrescreve silenciosamente os dados errados (achado real: um
        # round-trip export->wipe->reimport trocava os dados de dois perfis). Mesmo criterio
        # usado para collaborators acima - nunca confiar no id interno cru, so em chave de
        # negocio (aqui, nome + tipo de lideranca).
        profile = db.scalar(
            select(LeadershipProfile).where(LeadershipProfile.name == name, LeadershipProfile.role_type == role_type)
        )

        try:
            validate_no_scope_overlap(db, role_type, regionals, profile_id=profile.id if profile else None)
        except HTTPException as exc:
            warnings.append(f"Perfil de liderança '{name}' ignorado: {exc.detail}")
            continue

        # Casamento do colaborador vinculado por ixc_employee_id (portavel entre ambientes) antes
        # do nome, mesmo criterio usado no loop de collaborators acima - collaborator_id sozinho
        # nao sobrevive a um reimport de outro ambiente.
        collaborator_id = None
        ixc_employee_id_raw = item.get("collaborator_ixc_employee_id")
        if ixc_employee_id_raw not in (None, ""):
            linked = db.scalar(select(Collaborator).where(Collaborator.ixc_employee_id == int(ixc_employee_id_raw)))
            collaborator_id = linked.id if linked else None
        if collaborator_id is None and item.get("collaborator_name"):
            linked = db.scalar(select(Collaborator).where(func.lower(Collaborator.name) == str(item["collaborator_name"]).lower()))
            collaborator_id = linked.id if linked else None

        if not profile:
            profile = LeadershipProfile(name=name, role_type=role_type, percentage=default_percentage_for_role(role_type))
            db.add(profile)

        profile.name = name
        profile.role_type = role_type
        profile.percentage = default_percentage_for_role(role_type)
        profile.role_profile_id = role_profile.id if role_profile else None
        use_custom_multiplier = _bool(item.get("use_custom_multiplier"), False)
        custom_multiplier = _float_or_none(item.get("custom_multiplier"))
        profile.use_custom_multiplier = use_custom_multiplier
        profile.custom_multiplier = custom_multiplier
        profile.multiplier = float(
            custom_multiplier
            if use_custom_multiplier and custom_multiplier is not None
            else (
                role_profile.default_multiplier
                if role_profile
                else (item.get("multiplier") if item.get("multiplier") is not None else default_multiplier_for_role(role_type))
            )
        )
        profile.average_source = normalize_average_source(item.get("average_source"))
        profile.active = _bool(item.get("active"), True)
        profile.collaborator_id = collaborator_id
        profile.updated_at = _now()
        db.add(profile)
        db.flush()
        replace_profile_regionals(db, profile, regionals)

    db.flush()
    current_config = serialize_current_config(db)
    save_config_version(db, current_config, version_name or str(config.get("name") or CONFIG_NAME))
    if warnings:
        current_config = dict(current_config, warnings=warnings)
    return current_config


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
