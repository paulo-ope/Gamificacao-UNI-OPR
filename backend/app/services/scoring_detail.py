from __future__ import annotations

import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Iterable

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AppSetting,
    Collaborator,
    DiagnosisPenaltyRule,
    HealthRule,
    RecurrenceClassificationRule,
    ScoringGroup,
    ScoringSubjectRule,
    ServiceOrder,
    SlaPenaltyRule,
)
from app.services.scoring_matrix import real_service_orders
from app.services.regional import is_valid_regional, normalize_regional, same_regional
from app.services.sla import SLA_FORA_DO_PRAZO, SLA_NO_PRAZO, normalize_sla_status, sla_status_label


def normalize(value: str | None) -> str:
    if not value:
        return ""
    cleaned = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in cleaned if not unicodedata.combining(ch)).strip().lower()


UNKNOWN_COLLABORATOR_NAMES = {
    normalize("NAO IDENTIFICADO"),
    normalize("NAO INFORMADO"),
    normalize("NÃO IDENTIFICADO"),
    normalize("NÃO INFORMADO"),
}


def is_identified_collaborator_detail(detail: dict[str, Any]) -> bool:
    name = normalize(str(detail.get("collaborator_name") or ""))
    return bool(name) and name not in UNKNOWN_COLLABORATOR_NAMES


def get_setting(db: Session, key: str, default: str) -> str:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == key))
    return setting.value if setting else default


def _safe_float(value: str | int | float | None, default: float) -> float:
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def get_point_value(db: Session) -> float:
    return _safe_float(get_setting(db, "point_value", "2.50"), 2.50)


def completed(order: ServiceOrder) -> bool:
    return normalize(order.status) in {
        "concluida",
        "concluido",
        "finalizada",
        "finalizado",
        "fechada",
        "fechado",
        "encerrada",
        "encerrado",
        "closed",
        "done",
    }


def period_orders(db: Session, reference_month: int, reference_year: int, regional: str | None = None) -> list[ServiceOrder]:
    stmt = select(ServiceOrder).options(selectinload(ServiceOrder.collaborator))
    period_start = datetime(reference_year, reference_month, 1)
    if reference_month == 12:
        period_end = datetime(reference_year + 1, 1, 1)
    else:
        period_end = datetime(reference_year, reference_month + 1, 1)
    stmt = stmt.where(
        or_(
            and_(ServiceOrder.closed_at >= period_start, ServiceOrder.closed_at < period_end),
            and_(
                ServiceOrder.closed_at.is_(None),
                ServiceOrder.opened_at >= period_start,
                ServiceOrder.opened_at < period_end,
            ),
        )
    )
    orders = list(db.scalars(stmt))
    filtered = []
    for order in orders:
        reference_date = order.closed_at or order.opened_at
        if (
            reference_date
            and reference_date.month == reference_month
            and reference_date.year == reference_year
            and (not regional or same_regional(order.regional, regional))
        ):
            filtered.append(order)
    return sorted(real_service_orders(filtered), key=lambda item: item.closed_at or item.opened_at)


def active_scoring_rules(db: Session) -> list[ScoringSubjectRule]:
    return list(
        db.scalars(
            select(ScoringSubjectRule)
            .options(selectinload(ScoringSubjectRule.group))
            .where(ScoringSubjectRule.active.is_(True))
            .order_by(ScoringSubjectRule.os_type.asc(), ScoringSubjectRule.os_subject.asc())
        )
    )


def build_scoring_rule_lookup(rules: Iterable[ScoringSubjectRule]) -> dict[str, dict]:
    exact: dict[tuple[str, str], ScoringSubjectRule] = {}
    subject_matches: dict[str, list[ScoringSubjectRule]] = defaultdict(list)
    for rule in rules:
        if not rule.group or not rule.group.active:
            continue
        exact.setdefault((normalize(rule.os_type), normalize(rule.os_subject)), rule)
        subject_matches[normalize(rule.os_subject)].append(rule)

    subject_unique = {
        subject: matched_rules[0]
        for subject, matched_rules in subject_matches.items()
        if len(matched_rules) == 1
    }
    return {"exact": exact, "subject_unique": subject_unique}


def matching_scoring_rule(order: ServiceOrder, rules: Iterable[ScoringSubjectRule] | dict[str, dict]) -> ScoringSubjectRule | None:
    os_type = normalize(order.os_type)
    os_subject = normalize(order.os_subject)

    if isinstance(rules, dict):
        return rules["exact"].get((os_type, os_subject)) or rules["subject_unique"].get(os_subject)

    return matching_scoring_rule(order, build_scoring_rule_lookup(rules))


def effective_rule_points(rule: ScoringSubjectRule | None) -> float:
    if not rule or not rule.group:
        return 0.0
    if not rule.use_group_default and rule.custom_points is not None:
        return float(rule.custom_points)
    return float(rule.group.default_points)


def effective_rule_point_value(rule: ScoringSubjectRule | None, default_point_value: float) -> tuple[float, str]:
    if rule and rule.point_value_override is not None:
        return float(rule.point_value_override), "Assunto"
    if rule and rule.group and rule.group.point_value_override is not None:
        return float(rule.group.point_value_override), "Grupo"
    return float(default_point_value), "Global"


def rule_application_label(rule: ScoringSubjectRule | None) -> str | None:
    if not rule or not rule.group:
        return None
    if not rule.use_group_default and rule.custom_points is not None:
        return "Pontos especificos do assunto"
    return "Pontuacao padrao do grupo"


def order_points(order: ServiceOrder, rules: Iterable[ScoringSubjectRule] | dict[str, dict]) -> float:
    return effective_rule_points(matching_scoring_rule(order, rules))


def active_diagnosis_rules(db: Session) -> list[DiagnosisPenaltyRule]:
    return list(
        db.scalars(
            select(DiagnosisPenaltyRule)
            .where(DiagnosisPenaltyRule.active.is_(True))
            .order_by(DiagnosisPenaltyRule.diagnosis_name.asc())
        )
    )


def active_sla_penalty_rules(db: Session) -> list[SlaPenaltyRule]:
    return list(
        db.scalars(
            select(SlaPenaltyRule)
            .where(SlaPenaltyRule.active.is_(True))
            .order_by(SlaPenaltyRule.id.asc())
        )
    )


def all_diagnosis_rules(db: Session) -> list[DiagnosisPenaltyRule]:
    return list(db.scalars(select(DiagnosisPenaltyRule).order_by(DiagnosisPenaltyRule.diagnosis_name.asc())))


def active_recurrence_classification_rules(db: Session) -> list[RecurrenceClassificationRule]:
    return list(
        db.scalars(
            select(RecurrenceClassificationRule)
            .where(RecurrenceClassificationRule.active.is_(True))
            .order_by(RecurrenceClassificationRule.priority.asc(), RecurrenceClassificationRule.id.asc())
        )
    )


def matching_diagnosis_rule(
    diagnosis_name: str | None,
    rules: Iterable[DiagnosisPenaltyRule],
) -> DiagnosisPenaltyRule | None:
    normalized = normalize(diagnosis_name)
    if not normalized or normalized == normalize("Nao informado"):
        return None
    for rule in rules:
        if normalize(rule.diagnosis_name) == normalized:
            return rule
    return None


NON_TECHNICAL_TERMS = {
    "alteracao de endereco",
    "mudanca de endereco",
    "viabilidade",
    "remocao de equipamentos",
    "recuperacao de equipamento",
    "recolhimento",
    "retorno de instalacao",
    "ativacao de login",
    "upgrade",
    "alteracao de plano",
    "mudanca contratual",
    "pendencia cadastral",
    "pendencia comercial",
    "pendencia operacional",
}

RECURRENCE_DISCOUNT_CLASSIFICATIONS = {"reincidencia_tecnica", "garantia"}

PLAN_LIKE_CONTRACT_TERMS = {
    "combo",
    "fibra",
    "radio",
    "mega",
    "mb",
    "residencial",
    "enterprise",
    "plano",
    "servico",
    "uplay",
    "standard",
    "turbo",
    "ultra",
    "promocional",
    "time uni",
}


def _order_date(order: ServiceOrder):
    return order.closed_at or order.opened_at


def _meaningful(value: str | None) -> bool:
    normalized = normalize(value)
    return bool(normalized and normalized not in {normalize("Nao informado"), normalize("NAO IDENTIFICADO")})


def _contains_pattern(value: str | None, pattern: str | None) -> bool:
    if not pattern:
        return True
    normalized_value = normalize(value)
    options = [item.strip() for item in str(pattern).replace(";", "|").split("|") if item.strip()]
    if not options:
        return True
    return any(normalize(option) in normalized_value for option in options)


def _is_non_technical(order: ServiceOrder) -> bool:
    haystack = normalize(" ".join([order.os_type or "", order.os_subject or "", order.diagnosis or ""]))
    return any(term in haystack for term in NON_TECHNICAL_TERMS)


def _diagnosis_action_label(action_type: str | None) -> str:
    labels = {
        "subtract_points": "descontar pontos",
        "cancel_points": "anular pontos",
        "no_penalty": "nao penalizar",
        "requires_review": "exigir revisao manual",
        "force_points": "forcar pontuacao",
    }
    return labels.get(action_type or "", action_type or "acao nao informada")


def _sla_penalty_label(penalty_type: str | None) -> str:
    labels = {
        "subtract_points": "descontar pontos",
        "percentage_reduction": "reduzir percentual",
        "cancel_points": "anular pontos",
        "requires_review": "exigir revisao manual",
        "none": "nao penalizar",
    }
    return labels.get(penalty_type or "", penalty_type or "acao nao informada")


def _safe_contract_identity(value: str | None) -> bool:
    normalized = normalize(value)
    compact = "".join(ch for ch in normalized if ch.isalnum())
    if not _meaningful(value) or len(compact) < 3:
        return False
    if not any(ch.isdigit() for ch in compact):
        return False
    return not any(term in normalized for term in PLAN_LIKE_CONTRACT_TERMS)


def _recurrence_identity(order: ServiceOrder) -> str:
    login = normalize(getattr(order, "customer_login", None))
    if _meaningful(login):
        return f"login:{login}"
    contract = normalize(order.contract_id)
    if _safe_contract_identity(order.contract_id):
        return f"contract:{contract}"
    return ""


def _configured_recurrence_identity_fields(db: Session) -> list[str]:
    raw_value = get_setting(db, "recurrence_identity_fields", "login,contract")
    fields = [normalize(field).replace("_", "") for field in raw_value.split(",") if normalize(field)]
    allowed = {"login", "contract", "contrato", "cliente", "customer"}
    selected = [field for field in fields if field in allowed]
    return selected or ["login", "contract"]


def _recurrence_identity_for_fields(order: ServiceOrder, fields: list[str]) -> str:
    for field in fields:
        if field == "login":
            login = normalize(getattr(order, "customer_login", None))
            if _meaningful(login):
                return f"login:{login}"
        if field in {"contract", "contrato"}:
            contract = normalize(order.contract_id)
            if _safe_contract_identity(order.contract_id):
                return f"contract:{contract}"
        if field in {"cliente", "customer"}:
            customer = normalize(order.customer_name)
            if _meaningful(customer):
                return f"customer:{customer}"
    return ""


def _recurrence_identity_label(order: ServiceOrder) -> tuple[str, str]:
    if _meaningful(getattr(order, "customer_login", None)):
        return "login", str(order.customer_login)
    if _safe_contract_identity(order.contract_id):
        return "ID contrato", str(order.contract_id)
    return "sem referencia valida", "Login/ID contrato nao importado"


def _recurrence_identity_label_for_fields(order: ServiceOrder, fields: list[str]) -> tuple[str, str]:
    for field in fields:
        if field == "login" and _meaningful(getattr(order, "customer_login", None)):
            return "login", str(order.customer_login)
        if field in {"contract", "contrato"} and _safe_contract_identity(order.contract_id):
            return "ID contrato", str(order.contract_id)
        if field in {"cliente", "customer"} and _meaningful(order.customer_name):
            return "cliente", str(order.customer_name)
    return "sem referencia valida", "Campos de vinculo configurados nao encontrados na O.S"


def _configured_recurrence_identity_label(fields: list[str]) -> str:
    labels = {
        "login": "login",
        "contract": "contrato",
        "contrato": "contrato",
        "cliente": "cliente",
        "customer": "cliente",
    }
    selected = [labels[field] for field in fields if field in labels]
    unique = list(dict.fromkeys(selected))
    return "/".join(unique) if unique else "login/contrato"


def _recurrence_rule_uses_specific_flow(rule: RecurrenceClassificationRule) -> bool:
    return any(
        _meaningful(getattr(rule, field, None))
        for field in (
            "original_os_type_pattern",
            "original_os_subject_pattern",
            "return_os_type_pattern",
            "return_os_subject_pattern",
            "return_diagnosis_pattern",
            "ignore_diagnosis_pattern",
        )
    )


def _rule_matches_order(
    rule: RecurrenceClassificationRule,
    order: ServiceOrder,
    *,
    os_type_pattern: str | None = None,
    os_subject_pattern: str | None = None,
    diagnosis_pattern: str | None = None,
) -> bool:
    return (
        _contains_pattern(order.os_type, os_type_pattern)
        and _contains_pattern(order.os_subject, os_subject_pattern)
        and _contains_pattern(order.diagnosis, diagnosis_pattern)
    )


def _rule_matches_recurrence_pair(
    rule: RecurrenceClassificationRule,
    original: ServiceOrder,
    later: ServiceOrder,
    days_between: int,
) -> tuple[bool, str | None]:
    if rule.max_days is not None and days_between > int(rule.max_days):
        return False, None
    if rule.require_same_subject and normalize(original.os_subject) != normalize(later.os_subject):
        return False, None
    if rule.require_same_diagnosis and normalize(original.diagnosis) != normalize(later.diagnosis):
        return False, None

    uses_specific_flow = _recurrence_rule_uses_specific_flow(rule)
    original_type_pattern = rule.original_os_type_pattern or rule.os_type_pattern
    original_subject_pattern = rule.original_os_subject_pattern or rule.os_subject_pattern
    original_diagnosis_pattern = None if uses_specific_flow else rule.diagnosis_pattern
    return_type_pattern = rule.return_os_type_pattern or rule.os_type_pattern
    return_subject_pattern = rule.return_os_subject_pattern or rule.os_subject_pattern
    return_diagnosis_pattern = rule.return_diagnosis_pattern or rule.diagnosis_pattern

    original_matches = _rule_matches_order(
        rule,
        original,
        os_type_pattern=original_type_pattern,
        os_subject_pattern=original_subject_pattern,
        diagnosis_pattern=original_diagnosis_pattern,
    )
    later_matches = _rule_matches_order(
        rule,
        later,
        os_type_pattern=return_type_pattern,
        os_subject_pattern=return_subject_pattern,
        diagnosis_pattern=return_diagnosis_pattern,
    )

    if uses_specific_flow:
        has_original_filter = bool(_meaningful(original_type_pattern) or _meaningful(original_subject_pattern))
        has_return_filter = bool(
            _meaningful(return_type_pattern) or _meaningful(return_subject_pattern) or _meaningful(return_diagnosis_pattern)
        )
        if has_original_filter and not original_matches:
            return False, None
        if has_return_filter and not later_matches:
            return False, None
        return True, "origem e retorno"

    if original_matches and later_matches:
        return True, "origem e posterior"
    if original_matches:
        return True, "origem"
    if later_matches:
        return True, "posterior"
    return False, None


def classify_recurrence_pair(
    original: ServiceOrder,
    later: ServiceOrder,
    days_between: int,
    window_days: int,
    rules: list[RecurrenceClassificationRule],
    identity_label: tuple[str, str] | None = None,
) -> dict[str, Any]:
    same_subject = normalize(original.os_subject) == normalize(later.os_subject)
    same_diagnosis = _meaningful(original.diagnosis) and normalize(original.diagnosis) == normalize(later.diagnosis)
    later_is_flagged_return = later.is_warranty or later.is_recurrence
    identity_type, identity_value = identity_label or _recurrence_identity_label(original)
    evidence: list[str] = [
        f"Mesmo {identity_type}: {identity_value}",
        f"O.S posterior aberta {days_between} dia(s) depois",
    ]

    for rule in rules:
        if _meaningful(rule.ignore_diagnosis_pattern) and _contains_pattern(later.diagnosis, rule.ignore_diagnosis_pattern):
            evidence.append(f"Regra configurada: {rule.name}")
            evidence.append(f"Diagnostico de retorno ignorado: {later.diagnosis}")
            return {
                "classification": "os_nao_reincidente",
                "discount_points": False,
                "evidence": evidence,
                "related_order": later,
                "days_between": days_between,
                "rule_id": rule.id,
                "rule_name": rule.name,
            }
        rule_matches, match_side = _rule_matches_recurrence_pair(rule, original, later, days_between)
        if not rule_matches:
            continue
        evidence.append(f"Regra configurada: {rule.name}")
        if match_side:
            evidence.append(f"Regra aplicada na O.S {match_side}")
        if rule.os_type_pattern:
            evidence.append(f"Tipo Geral contem '{rule.os_type_pattern}'")
        if rule.os_subject_pattern:
            evidence.append(f"Assunto contem '{rule.os_subject_pattern}'")
        if rule.diagnosis_pattern:
            evidence.append(f"Diagnostico contem '{rule.diagnosis_pattern}'")
        if rule.original_os_type_pattern:
            evidence.append(f"O.S original tipo contem '{rule.original_os_type_pattern}'")
        if rule.original_os_subject_pattern:
            evidence.append(f"O.S original assunto contem '{rule.original_os_subject_pattern}'")
        if rule.return_os_type_pattern:
            evidence.append(f"O.S retorno tipo contem '{rule.return_os_type_pattern}'")
        if rule.return_os_subject_pattern:
            evidence.append(f"O.S retorno assunto contem '{rule.return_os_subject_pattern}'")
        if rule.return_diagnosis_pattern:
            evidence.append(f"O.S retorno diagnostico contem '{rule.return_diagnosis_pattern}'")
        return {
            "classification": rule.classification,
            "discount_points": rule.discount_points,
            "evidence": evidence,
            "related_order": later,
            "days_between": days_between,
            "rule_id": rule.id,
            "rule_name": rule.name,
        }

    if _is_non_technical(original) or _is_non_technical(later):
        evidence.append("Tipo/assunto indica fluxo operacional ou demanda diferente, nao falha tecnica")
        return {
            "classification": "os_nao_reincidente",
            "discount_points": False,
            "evidence": evidence,
            "related_order": later,
            "days_between": days_between,
            "rule_id": None,
            "rule_name": None,
        }

    if same_diagnosis:
        evidence.append(f"Mesmo diagnostico tecnico: {later.diagnosis}")
    if same_subject:
        evidence.append(f"Mesmo assunto tecnico: {later.os_subject}")
    if later_is_flagged_return:
        evidence.append("Planilha sinalizou a O.S posterior como possivel retorno")

    has_technical_relation = bool(same_diagnosis or (same_subject and not _is_non_technical(later)) or later_is_flagged_return)
    if has_technical_relation and days_between <= window_days:
        return {
            "classification": "possivel_retorno_sem_regra",
            "discount_points": False,
            "evidence": evidence
            + [
                "Nenhuma regra de reincidencia aplicada",
                "Retorno encontrado dentro da janela, mas sem regra ativa para classificar como reincidencia",
            ],
            "related_order": later,
            "days_between": days_between,
            "rule_id": None,
            "rule_name": None,
        }
    if has_technical_relation:
        evidence.append("Nenhuma regra de reincidencia aplicada")
        evidence.append("Retorno encontrado, mas fora da janela configurada para classificacao")

    if _meaningful(original.os_subject) and _meaningful(later.os_subject):
        evidence.append(f"Mesmo {identity_type}, mas tipo/assunto/diagnostico nao demonstram repeticao tecnica")
        return {
            "classification": "demandas_diferentes",
            "discount_points": False,
            "evidence": evidence,
            "related_order": later,
            "days_between": days_between,
            "rule_id": None,
            "rule_name": None,
        }

    evidence.append("Sem diagnostico/assunto suficiente para afirmar relacao tecnica")
    return {
        "classification": "nao_identificado",
        "discount_points": False,
        "evidence": evidence,
        "related_order": later,
        "days_between": days_between,
        "rule_id": None,
        "rule_name": None,
    }


def recurrence_penalties(
    db: Session,
    orders: list[ServiceOrder],
    scoring_rules: Iterable[ScoringSubjectRule] | dict[str, dict],
) -> dict[int, dict[str, Any]]:
    action = get_setting(db, "recurrence_action", "annul_original")
    window_days = int(_safe_float(get_setting(db, "recurrence_window_days", "30"), 30))
    configured_points = _safe_float(get_setting(db, "recurrence_penalty_points", "0"), 0)
    identity_fields = _configured_recurrence_identity_fields(db)
    rules = active_recurrence_classification_rules(db)
    search_window_days = max([window_days, *[int(rule.max_days) for rule in rules if rule.max_days is not None]])
    penalties: dict[int, dict[str, Any]] = {}
    base_orders = [order for order in orders if completed(order)]
    base_dates = [_order_date(order) for order in base_orders if _order_date(order) is not None]
    if not base_dates:
        return penalties
    search_start = min(base_dates)
    search_end = max(base_dates) + timedelta(days=search_window_days)
    all_orders = sorted(
        [
            order
            for order in real_service_orders(
                list(
                    db.scalars(
                        select(ServiceOrder).where(
                            or_(
                                ServiceOrder.opened_at.between(search_start, search_end),
                                ServiceOrder.closed_at.between(search_start, search_end),
                            )
                        )
                    )
                )
            )
            if completed(order)
        ],
        key=lambda item: _order_date(item) or item.opened_at,
    )

    orders_by_login: dict[str, list[ServiceOrder]] = defaultdict(list)
    for order in all_orders:
        identity = _recurrence_identity_for_fields(order, identity_fields)
        if not identity:
            continue
        orders_by_login[identity].append(order)

    normalized_action = normalize(action)

    for original in base_orders:
        original_date = _order_date(original)
        if original_date is None:
            continue

        candidates: list[dict[str, Any]] = []
        identity = _recurrence_identity_for_fields(original, identity_fields)
        if not identity:
            continue

        for later in orders_by_login.get(identity, []):
            if later.id == original.id:
                continue
            later_date = later.opened_at or later.closed_at
            if later_date is None:
                continue
            delta = later_date - original_date
            if delta < timedelta(0):
                continue
            if delta > timedelta(days=search_window_days):
                break
            days_between = int(delta.days)
            classification = classify_recurrence_pair(
                original,
                later,
                days_between,
                window_days,
                rules,
                identity_label=_recurrence_identity_label_for_fields(original, identity_fields),
            )
            candidates.append(classification)

        discount_candidates = [
            item
            for item in candidates
            if item["classification"] in RECURRENCE_DISCOUNT_CLASSIFICATIONS and bool(item["discount_points"])
        ]
        if not candidates:
            continue

        selected = sorted(discount_candidates or candidates, key=lambda item: int(item["days_between"]))[0]
        later_order: ServiceOrder = selected["related_order"]
        selected_discounts = selected["classification"] in RECURRENCE_DISCOUNT_CLASSIFICATIONS and bool(selected["discount_points"])
        if not selected_discounts:
            points = 0.0
            requires_review = False
            reason = f"Classificacao {selected['classification']} pela O.S {later_order.os_code}, sem desconto"
        elif normalized_action in {normalize("no_penalty"), normalize("nao_penaliza")}:
            points = 0.0
            requires_review = False
            reason = f"{selected['classification']} identificada pela O.S {later_order.os_code}, sem desconto por configuracao"
        elif normalized_action == normalize("requires_review"):
            points = 0.0
            requires_review = True
            reason = f"{selected['classification']} pela O.S {later_order.os_code} exige revisao manual"
        elif normalized_action == normalize("subtract_original"):
            points = abs(float(configured_points))
            requires_review = False
            reason = f"Desconto por {selected['classification']} da O.S {later_order.os_code}: -{points:g}"
        else:
            points = order_points(original, scoring_rules)
            requires_review = False
            reason = f"Anulacao por {selected['classification']} da O.S {later_order.os_code}: -{points:g}"

        current = penalties.setdefault(
            original.id,
            {
                "points": 0.0,
                "reasons": [],
                "requires_review": False,
                "classification": selected["classification"],
                "related_os_code": later_order.os_code,
                "related_order_id": later_order.id,
                "days_between": selected["days_between"],
                "evidence": selected["evidence"],
                "discount_applied": points > 0,
                "rule_id": selected.get("rule_id"),
                "rule_name": selected.get("rule_name"),
            },
        )
        current["points"] += points
        current["reasons"].append(reason)
        current["reasons"].extend([f"Evidencia: {evidence}" for evidence in selected["evidence"]])
        current["requires_review"] = bool(current["requires_review"] or requires_review)
        current["discount_applied"] = bool(current["discount_applied"] or points > 0)

    return penalties


def sla_inside(order: ServiceOrder) -> bool:
    normalized_status = normalize_sla_status(order.sla_status)
    if normalized_status == SLA_FORA_DO_PRAZO:
        return False
    if normalized_status == SLA_NO_PRAZO:
        return True
    if order.sla_hours is None or order.closing_time_hours is None:
        return False
    return order.closing_time_hours <= order.sla_hours


def sla_rule_applies(order: ServiceOrder, rule: SlaPenaltyRule) -> bool:
    if rule.condition_type == "status_sla_out_of_time":
        return not sla_inside(order)
    if rule.condition_type == "sla_hours_greater_than":
        if order.sla_hours is None or order.closing_time_hours is None:
            return False
        return order.closing_time_hours > order.sla_hours
    if rule.condition_type == "closed_after_deadline":
        return not sla_inside(order)
    return False


def matching_sla_penalty_rule(order: ServiceOrder, rules: Iterable[SlaPenaltyRule]) -> SlaPenaltyRule | None:
    for rule in rules:
        if rule.active and sla_rule_applies(order, rule):
            return rule
    return None


def select_health_rule(rules: list[HealthRule], sla_rate: float, recurrence_rate: float) -> HealthRule | None:
    active_rules = [rule for rule in rules if rule.active]
    if not active_rules:
        return None

    critical = next((rule for rule in active_rules if normalize(rule.name).startswith("critica")), None)
    attention = next((rule for rule in active_rules if "atencao" in normalize(rule.name)), None)
    if attention and critical:
        if sla_rate < attention.min_sla or recurrence_rate > attention.max_recurrence_rate:
            return critical

    ranked = sorted(
        [rule for rule in active_rules if rule is not critical],
        key=lambda rule: (rule.min_sla, -rule.max_recurrence_rate),
        reverse=True,
    )
    for rule in ranked:
        if rule.condition_operator == "or":
            if sla_rate >= rule.min_sla or recurrence_rate <= rule.max_recurrence_rate:
                return rule
        elif sla_rate >= rule.min_sla and recurrence_rate <= rule.max_recurrence_rate:
            return rule

    return critical or min(active_rules, key=lambda rule: rule.multiplier)


def calculate_regional_health(db: Session, orders: list[ServiceOrder]) -> dict[str, dict[str, float | int | str]]:
    rules = list(db.scalars(select(HealthRule).where(HealthRule.active.is_(True))))
    grouped: dict[str, list[ServiceOrder]] = defaultdict(list)
    for order in orders:
        if not is_valid_regional(order.regional):
            continue
        grouped[normalize_regional(order.regional)].append(order)

    health: dict[str, dict[str, float | int | str]] = {}
    for regional, regional_orders in grouped.items():
        total = len(regional_orders)
        sla_ok = sum(1 for order in regional_orders if sla_inside(order))
        recurrences = sum(1 for order in regional_orders if order.is_warranty or order.is_recurrence)
        pending = sum(1 for order in regional_orders if order.has_pending)
        rescheduled = sum(1 for order in regional_orders if order.has_reschedule)
        sla_rate = round((sla_ok / total) * 100, 2) if total else 0
        recurrence_rate = round((recurrences / total) * 100, 2) if total else 0
        rule = select_health_rule(rules, sla_rate, recurrence_rate)

        health[regional] = {
            "regional": regional,
            "health_status": rule.name if rule else "Sem regra",
            "sla_rate": sla_rate,
            "recurrence_rate": recurrence_rate,
            "multiplier": float(rule.multiplier) if rule else 1.0,
            "total_orders": total,
            "pending_orders": pending,
            "rescheduled_orders": rescheduled,
        }
    return health


def calculate_regional_health_from_details(
    db: Session,
    details: list[dict[str, Any]],
    base_health: dict[str, dict[str, float | int | str]],
) -> dict[str, dict[str, float | int | str]]:
    rules = list(db.scalars(select(HealthRule).where(HealthRule.active.is_(True))))
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for detail in details:
        if not is_identified_collaborator_detail(detail) or not is_valid_regional(str(detail["regional"])):
            continue
        grouped[normalize_regional(str(detail["regional"]))].append(detail)

    health = {
        normalize_regional(regional): dict(item, regional=normalize_regional(regional))
        for regional, item in base_health.items()
        if is_valid_regional(regional)
    }
    for regional, regional_details in grouped.items():
        item = health.setdefault(
            regional,
            {
                "regional": regional,
                "health_status": "Sem regra",
                "sla_rate": 0,
                "recurrence_rate": 0,
                "multiplier": 1.0,
                "total_orders": len(regional_details),
                "pending_orders": 0,
                "rescheduled_orders": 0,
            },
        )
        total = int(item.get("total_orders") or len(regional_details))
        recurrences = sum(
            1
            for detail in regional_details
            if detail.get("recurrence_classification") in RECURRENCE_DISCOUNT_CLASSIFICATIONS
            or bool(detail.get("recurrence_discount_applied"))
        )
        recurrence_rate = round((recurrences / total) * 100, 2) if total else 0
        item["recurrence_rate"] = recurrence_rate
        item["recurrence_orders"] = recurrences
        rule = select_health_rule(rules, float(item.get("sla_rate", 0)), recurrence_rate)
        item["health_status"] = rule.name if rule else item.get("health_status", "Sem regra")
        item["multiplier"] = float(rule.multiplier) if rule else float(item.get("multiplier", 1.0))
    return health


def predominant_regional_from_details(details: list[dict[str, Any]], fallback: str | None = None) -> str | None:
    regionals = [normalize_regional(str(item.get("regional") or "")) for item in details if str(item.get("regional") or "").strip()]
    if not regionals:
        return normalize_regional(fallback) if fallback else fallback
    return Counter(regionals).most_common(1)[0][0]


def health_for_details(
    details: list[dict[str, Any]],
    health_by_regional: dict[str, dict[str, float | int | str]],
    fallback_regional: str | None = None,
) -> tuple[str | None, dict[str, float | int | str]]:
    regional = predominant_regional_from_details(details, fallback_regional)
    return regional, health_by_regional.get(regional or "", {})


def explain_order(
    order: ServiceOrder,
    scoring_rules: Iterable[ScoringSubjectRule] | dict[str, dict],
    diagnosis_rules: list[DiagnosisPenaltyRule],
    sla_rules: list[SlaPenaltyRule],
    recurrence_by_original_id: dict[int, dict[str, Any]],
    warranty_mode: str,
    warranty_reduction_percentage: float,
    default_point_value: float,
) -> dict[str, Any]:
    scoring_rule = matching_scoring_rule(order, scoring_rules)
    diagnosis_rule = matching_diagnosis_rule(order.diagnosis, diagnosis_rules)
    sla_rule = matching_sla_penalty_rule(order, sla_rules)
    is_completed = completed(order)
    is_sla_out = not sla_inside(order)
    normalized_sla_status = sla_status_label(order.sla_status)
    base_points = 0.0
    penalty_points = 0.0
    diagnosis_penalty_points = 0.0
    sla_penalty_points = 0.0
    diagnosis_penalty_reason: str | None = None
    diagnosis_rule_applied: str | None = None
    sla_penalty_reason: str | None = None
    requires_manual_review = False
    penalty_reasons: list[str] = []
    penalty_items: list[dict[str, float | str]] = []
    calculation_reasons: list[str] = []
    non_scoring_reasons: list[str] = []
    scoring_status = "Pontuada"
    diagnosis_name = order.diagnosis or "Nao informado"
    diagnosis_handles_penalty = False
    normalized_warranty_mode = normalize(warranty_mode)
    group_base_points = float(scoring_rule.group.default_points) if scoring_rule and scoring_rule.group else 0.0
    subject_override_points = (
        float(scoring_rule.custom_points)
        if scoring_rule and not scoring_rule.use_group_default and scoring_rule.custom_points is not None
        else None
    )
    point_value, point_value_source = effective_rule_point_value(scoring_rule, default_point_value)
    recurrence = recurrence_by_original_id.get(order.id)
    recurrence_classification = recurrence.get("classification") if recurrence else None
    recurrence_penalty_points = float(recurrence.get("points", 0)) if recurrence else 0.0
    has_recurrence_penalty = recurrence_penalty_points > 0
    recurrence_suppresses_point_penalties = has_recurrence_penalty

    if is_completed:
        calculation_reasons.append(f"SLA original da planilha: {order.sla_status or 'Nao informado'}")
        calculation_reasons.append(f"SLA normalizado: {normalized_sla_status}")

    if not order.collaborator_id:
        scoring_status = "Sem colaborador"
        non_scoring_reasons.append("O.S sem colaborador vinculado")
    elif not is_completed:
        scoring_status = "Ignorada"
        non_scoring_reasons.append(f"Status nao finalizado: {order.status}")
    elif not scoring_rule:
        scoring_status = "Sem regra"
        non_scoring_reasons.append("Assunto real do UpValue sem regra ativa na matriz")
    elif (order.is_warranty or order.is_recurrence) and normalized_warranty_mode in {
        normalize("no_points"),
        normalize("nao_pontua"),
    }:
        scoring_status = "Ignorada"
        non_scoring_reasons.append("Garantia/reincidencia configurada para nao pontuar")
    else:
        base_points = effective_rule_points(scoring_rule)
        calculation_reasons.append(f"Assunto vinculado ao grupo {scoring_rule.group.name}")
        if not scoring_rule.use_group_default and scoring_rule.custom_points is not None:
            calculation_reasons.append(f"Regra aplicada: {order.os_subject}")
            calculation_reasons.append(f"Pontuacao base do grupo: {group_base_points:g}")
            calculation_reasons.append(f"Sobrescrita do assunto aplicada: {base_points:g}")
        else:
            calculation_reasons.append(f"Regra aplicada: {order.os_subject}")
            calculation_reasons.append(f"Pontuacao base do grupo aplicada: {base_points:g}")
        if order.is_warranty or order.is_recurrence:
            scoring_status = "Garantia pontuada"
            if normalized_warranty_mode == normalize("requires_review"):
                requires_manual_review = True
                scoring_status = "Revisao manual"
                calculation_reasons.append("Garantia/reincidencia exige revisao manual")
            else:
                calculation_reasons.append("Garantia/reincidencia resolvida configurada para pontuar")

    if is_completed:
        if diagnosis_rule:
            diagnosis_rule_applied = diagnosis_rule.diagnosis_name
            action_type = diagnosis_rule.action_type
            configured_points = abs(float(diagnosis_rule.penalty_points))
            if recurrence_suppresses_point_penalties and action_type in {"subtract_points", "cancel_points"}:
                diagnosis_penalty_reason = (
                    f"Diagnostico {diagnosis_name} possui regra configurada para "
                    f"{_diagnosis_action_label(action_type)}, porem nao foi aplicado porque a O.S ja teve "
                    "pontuacao anulada por Garantia/Reincidencia"
                )
                calculation_reasons.append(diagnosis_penalty_reason)
            elif action_type == "subtract_points":
                diagnosis_handles_penalty = True
                if base_points > 0:
                    diagnosis_penalty_points = configured_points
                    penalty_points += diagnosis_penalty_points
                    diagnosis_penalty_reason = (
                        f"Diagnostico {diagnosis_name} aplicou -{diagnosis_penalty_points:g} pontos"
                    )
                    penalty_reasons.append(diagnosis_penalty_reason)
                    penalty_items.append({"name": f"Diagnostico: {diagnosis_name}", "points": diagnosis_penalty_points})
                else:
                    diagnosis_penalty_reason = f"Diagnostico {diagnosis_name} possui penalidade, mas a O.S nao tem pontuacao base"
                    calculation_reasons.append(diagnosis_penalty_reason)
            elif action_type == "cancel_points":
                diagnosis_handles_penalty = True
                diagnosis_penalty_points = base_points
                penalty_points += diagnosis_penalty_points
                diagnosis_penalty_reason = f"Diagnostico {diagnosis_name} anulou a pontuacao base"
                penalty_reasons.append(diagnosis_penalty_reason)
                penalty_items.append({"name": f"Diagnostico: {diagnosis_name}", "points": diagnosis_penalty_points})
                if base_points > 0:
                    scoring_status = "Anulada por diagnostico"
            elif action_type == "requires_review":
                requires_manual_review = True
                diagnosis_penalty_reason = f"Diagnostico {diagnosis_name} exige revisao manual"
                penalty_reasons.append(diagnosis_penalty_reason)
                if scoring_status == "Pontuada":
                    scoring_status = "Revisao manual"
            elif action_type == "force_points":
                forced_points = float(diagnosis_rule.force_points_value or 0)
                base_points = forced_points
                diagnosis_penalty_reason = f"Diagnostico {diagnosis_name} forcou pontuacao para {forced_points:g}"
                calculation_reasons.append(diagnosis_penalty_reason)
                if scoring_status in {"Sem regra", "Ignorada"} and forced_points > 0:
                    scoring_status = "Pontuada"
                    non_scoring_reasons = [
                        reason for reason in non_scoring_reasons if "sem regra" not in normalize(reason)
                    ]
            else:
                diagnosis_penalty_reason = f"Diagnostico {diagnosis_name} marcado como sem penalidade"
                calculation_reasons.append(diagnosis_penalty_reason)
        elif normalize(diagnosis_name) and normalize(diagnosis_name) != normalize("Nao informado"):
            calculation_reasons.append(f"Diagnostico {diagnosis_name} sem regra de penalidade configurada")

        if order.is_warranty or order.is_recurrence:
            if normalized_warranty_mode == normalize("score_reduced") and base_points > 0:
                points = round(base_points * (abs(float(warranty_reduction_percentage)) / 100), 2)
                if recurrence_suppresses_point_penalties and points > 0:
                    calculation_reasons.append(
                        "Reducao de garantia/reincidencia importada ignorada porque a O.S ja teve pontuacao anulada por Garantia/Reincidencia"
                    )
                elif points > 0:
                    penalty_points += points
                    penalty_reasons.append(f"Garantia/reincidencia pontua com reducao de {warranty_reduction_percentage:g}%: -{points:g}")
                    penalty_items.append({"name": "Garantia/Reincidencia", "points": points})

        if sla_rule and base_points > 0:
            if recurrence_suppresses_point_penalties and sla_rule.penalty_type in {"subtract_points", "percentage_reduction", "cancel_points"}:
                sla_penalty_reason = (
                    f"SLA possui regra configurada para {_sla_penalty_label(sla_rule.penalty_type)}, "
                    "porem nao foi aplicado porque a O.S ja teve pontuacao anulada por Garantia/Reincidencia"
                )
                calculation_reasons.append(sla_penalty_reason)
            elif sla_rule.penalty_type == "subtract_points":
                sla_penalty_points = abs(float(sla_rule.penalty_value))
                sla_penalty_reason = f"SLA fora do prazo aplicou {sla_penalty_points:g} pontos anulados"
            elif sla_rule.penalty_type == "percentage_reduction":
                sla_penalty_points = round(base_points * (abs(float(sla_rule.penalty_value)) / 100), 2)
                sla_penalty_reason = f"SLA fora do prazo reduziu {abs(float(sla_rule.penalty_value)):g}% da pontuacao"
            elif sla_rule.penalty_type == "cancel_points":
                sla_penalty_points = base_points
                sla_penalty_reason = "SLA fora do prazo anulou a pontuacao base"
                if base_points > 0:
                    scoring_status = "Anulada por SLA"
            elif sla_rule.penalty_type == "requires_review":
                requires_manual_review = True
                sla_penalty_reason = "SLA fora do prazo exige revisao manual"
                if scoring_status == "Pontuada":
                    scoring_status = "Revisao manual"
            else:
                sla_penalty_reason = "SLA fora do prazo configurado sem penalidade"
                calculation_reasons.append(sla_penalty_reason)

            if sla_penalty_points > 0:
                penalty_points += sla_penalty_points
                penalty_reasons.append(sla_penalty_reason or f"Penalidade SLA -{sla_penalty_points:g}")
                penalty_items.append({"name": "SLA fora do prazo", "points": sla_penalty_points})
        elif is_sla_out:
            calculation_reasons.append(f"SLA fora do prazo identificado por status {normalized_sla_status}, sem penalidade configurada")
        else:
            calculation_reasons.append(f"SLA no prazo identificado por status {normalized_sla_status}, sem penalidade")

        if recurrence:
            points = recurrence_penalty_points
            penalty_points += points
            penalty_reasons.extend(recurrence["reasons"])
            if points > 0:
                penalty_items.append({"name": "Reincidencias", "points": points})
            if recurrence.get("requires_review"):
                requires_manual_review = True
                if scoring_status == "Pontuada":
                    scoring_status = "Revisao manual"
            if base_points > 0 and penalty_points >= base_points:
                scoring_status = "Anulada por reincidencia"

        if recurrence and recurrence_classification not in RECURRENCE_DISCOUNT_CLASSIFICATIONS:
            scoring_status = "Pontuada" if base_points > 0 else scoring_status

    if (
        base_points > 0
        and penalty_points > 0
        and scoring_status not in {"Anulada por reincidencia", "Anulada por diagnostico", "Anulada por SLA"}
    ):
        scoring_status = "Penalizada"

    net_points = round(max(base_points - penalty_points, 0), 2)
    additional_penalty_points = round(max(penalty_points - diagnosis_penalty_points - sla_penalty_points, 0), 2)
    reasons = calculation_reasons + penalty_reasons + non_scoring_reasons

    return {
        "id": order.id,
        "collaborator_id": order.collaborator_id,
        "collaborator_name": order.collaborator.name if order.collaborator else "NAO IDENTIFICADO",
        "os_code": order.os_code,
        "contract_id": order.contract_id,
        "customer_login": order.customer_login,
        "customer_name": order.customer_name,
        "regional": normalize_regional(order.regional),
        "os_type": order.os_type,
        "os_subject": order.os_subject,
        "diagnosis": diagnosis_name,
        "status": order.status,
        "sla_status": order.sla_status,
        "sla_status_normalized": normalized_sla_status,
        "sla_hours": order.sla_hours,
        "closing_time_hours": order.closing_time_hours,
        "opened_at": order.opened_at,
        "closed_at": order.closed_at,
        "is_warranty": order.is_warranty or recurrence_classification == "garantia",
        "is_recurrence": order.is_recurrence or recurrence_classification in {"reincidencia_tecnica", "garantia"},
        "has_reschedule": order.has_reschedule,
        "has_pending": order.has_pending,
        "group_id": scoring_rule.group_id if scoring_rule else None,
        "group_name": scoring_rule.group.name if scoring_rule and scoring_rule.group else None,
        "subject_rule_id": scoring_rule.id if scoring_rule else None,
        "rule_applied": rule_application_label(scoring_rule),
        "effective_points": round(effective_rule_points(scoring_rule), 2),
        "group_base_points": round(group_base_points, 2),
        "subject_override_points": round(subject_override_points, 2) if subject_override_points is not None else None,
        "use_group_default": scoring_rule.use_group_default if scoring_rule else None,
        "custom_points": scoring_rule.custom_points if scoring_rule else None,
        "point_value": round(point_value, 4),
        "point_value_source": point_value_source,
        "point_value_override": scoring_rule.point_value_override if scoring_rule else None,
        "recurrence_classification": recurrence_classification,
        "recurrence_discount_applied": bool(recurrence.get("discount_applied")) if recurrence else False,
        "recurrence_related_os_code": recurrence.get("related_os_code") if recurrence else None,
        "recurrence_days_between": recurrence.get("days_between") if recurrence else None,
        "recurrence_evidence": recurrence.get("evidence", []) if recurrence else [],
        "recurrence_penalty_points": round(recurrence_penalty_points, 2),
        "recurrence_rule_id": recurrence.get("rule_id") if recurrence else None,
        "recurrence_rule_name": recurrence.get("rule_name") if recurrence else None,
        "base_points": round(base_points, 2),
        "penalty_points": round(penalty_points, 2),
        "sla_penalty_points": round(sla_penalty_points, 2),
        "sla_penalty_reason": sla_penalty_reason,
        "sla_rule_id": sla_rule.id if sla_rule else None,
        "sla_penalty_type": sla_rule.penalty_type if sla_rule else None,
        "additional_penalty_points": additional_penalty_points,
        "net_points": net_points,
        "scoring_rule_name": scoring_rule.group.name if scoring_rule and scoring_rule.group else None,
        "diagnosis_rule_id": diagnosis_rule.id if diagnosis_rule else None,
        "diagnosis_rule_applied": diagnosis_rule_applied,
        "diagnosis_action_type": diagnosis_rule.action_type if diagnosis_rule else None,
        "diagnosis_rule_description": diagnosis_rule.description if diagnosis_rule else None,
        "diagnosis_penalty_points": round(diagnosis_penalty_points, 2),
        "diagnosis_penalty_reason": diagnosis_penalty_reason,
        "diagnosis_force_points_value": diagnosis_rule.force_points_value if diagnosis_rule else None,
        "requires_manual_review": requires_manual_review,
        "scoring_status": scoring_status,
        "penalty_reasons": penalty_reasons,
        "penalty_items": penalty_items,
        "reasons": reasons,
        "is_scored": base_points > 0 and scoring_status in {"Pontuada", "Garantia pontuada", "Penalizada", "Revisao manual"},
        "is_unscored": scoring_status == "Sem regra",
        "is_penalized": penalty_points > 0,
        "is_annulled": scoring_status in {"Anulada por reincidencia", "Anulada por diagnostico", "Anulada por SLA"},
        "is_sla_out_of_time": is_sla_out,
    }


def explain_orders(
    db: Session,
    orders: list[ServiceOrder],
    default_point_value: float | None = None,
) -> list[dict[str, Any]]:
    scoring_rules = active_scoring_rules(db)
    scoring_lookup = build_scoring_rule_lookup(scoring_rules)
    diagnosis_rules = active_diagnosis_rules(db)
    sla_rules = active_sla_penalty_rules(db)
    recurrence_by_original_id = recurrence_penalties(db, orders, scoring_lookup)
    legacy_warranty_scores = normalize(get_setting(db, "warranty_scores", "true")) in {"true", "1", "sim", "yes"}
    warranty_mode = get_setting(db, "warranty_mode", "score_full" if legacy_warranty_scores else "no_points")
    warranty_reduction_percentage = float(get_setting(db, "warranty_reduction_percentage", "0"))
    default_point_value = default_point_value if default_point_value is not None else get_point_value(db)

    return [
        explain_order(
            order,
            scoring_lookup,
            diagnosis_rules,
            sla_rules,
            recurrence_by_original_id,
            warranty_mode,
            warranty_reduction_percentage,
            default_point_value,
        )
        for order in orders
    ]


def summarize_details(
    details: list[dict[str, Any]],
    health_multiplier: float,
    point_value: float,
) -> dict[str, float | int]:
    gross = round(sum(float(item["base_points"]) for item in details), 2)
    penalty = round(sum(float(item["penalty_points"]) for item in details), 2)
    net = round(sum(float(item["net_points"]) for item in details), 2)
    final = round(net * health_multiplier, 2)
    estimated = round(
        sum(float(item["net_points"]) * health_multiplier * float(item.get("point_value", point_value)) for item in details),
        2,
    )

    return {
        "total_service_orders": len(details),
        "scored_service_orders": sum(1 for item in details if item["is_scored"]),
        "unscored_service_orders": sum(1 for item in details if item["is_unscored"]),
        "penalized_service_orders": sum(1 for item in details if item["is_penalized"]),
        "warranty_service_orders": sum(1 for item in details if item["recurrence_classification"] in RECURRENCE_DISCOUNT_CLASSIFICATIONS),
        "recurrence_service_orders": sum(1 for item in details if item["recurrence_classification"] in RECURRENCE_DISCOUNT_CLASSIFICATIONS),
        "rescheduled_service_orders": sum(1 for item in details if item["has_reschedule"]),
        "pending_service_orders": sum(1 for item in details if item["has_pending"]),
        "sla_out_service_orders": sum(1 for item in details if item["is_sla_out_of_time"]),
        "annulled_service_orders": sum(1 for item in details if item["is_annulled"]),
        "diagnosis_penalized_service_orders": sum(1 for item in details if float(item["diagnosis_penalty_points"]) > 0),
        "manual_review_service_orders": sum(1 for item in details if item["requires_manual_review"]),
        "diagnosis_unmapped_service_orders": sum(
            1
            for item in details
            if item["diagnosis"]
            and normalize(str(item["diagnosis"])) != normalize("Nao informado")
            and not item["diagnosis_rule_id"]
        ),
        "gross_points": gross,
        "penalty_points": penalty,
        "net_points": net,
        "health_multiplier": health_multiplier,
        "final_points": final,
        "estimated_payment": estimated,
    }


def summarize_audit_details(
    db: Session,
    details: list[dict[str, Any]],
    orders: list[ServiceOrder],
    point_value: float,
) -> dict[str, float | int]:
    health_by_regional = calculate_regional_health(db, [order for order in orders if completed(order)])
    final_points = round(
        sum(
            float(item["net_points"])
            * float(health_by_regional.get(normalize_regional(str(item["regional"])), {}).get("multiplier", 1.0))
            for item in details
        ),
        2,
    )
    gross = round(sum(float(item["base_points"]) for item in details), 2)
    penalty = round(sum(float(item["penalty_points"]) for item in details), 2)
    net = round(sum(float(item["net_points"]) for item in details), 2)
    return {
        "total_service_orders": len(details),
        "scored_service_orders": sum(1 for item in details if item["is_scored"]),
        "unscored_service_orders": sum(1 for item in details if item["is_unscored"]),
        "penalized_service_orders": sum(1 for item in details if item["is_penalized"]),
        "warranty_service_orders": sum(1 for item in details if item["recurrence_classification"] in RECURRENCE_DISCOUNT_CLASSIFICATIONS),
        "recurrence_service_orders": sum(1 for item in details if item["recurrence_classification"] in RECURRENCE_DISCOUNT_CLASSIFICATIONS),
        "rescheduled_service_orders": sum(1 for item in details if item["has_reschedule"]),
        "pending_service_orders": sum(1 for item in details if item["has_pending"]),
        "sla_out_service_orders": sum(1 for item in details if item["is_sla_out_of_time"]),
        "annulled_service_orders": sum(1 for item in details if item["is_annulled"]),
        "diagnosis_penalized_service_orders": sum(1 for item in details if float(item["diagnosis_penalty_points"]) > 0),
        "manual_review_service_orders": sum(1 for item in details if item["requires_manual_review"]),
        "diagnosis_unmapped_service_orders": sum(
            1
            for item in details
            if item["diagnosis"]
            and normalize(str(item["diagnosis"])) != normalize("Nao informado")
            and not item["diagnosis_rule_id"]
        ),
        "gross_points": gross,
        "penalty_points": penalty,
        "net_points": net,
        "final_points": final_points,
        "estimated_payment": round(
            sum(
                float(item["net_points"])
                * float(health_by_regional.get(normalize_regional(str(item["regional"])), {}).get("multiplier", 1.0))
                * float(item.get("point_value", point_value))
                for item in details
            ),
            2,
        ),
    }


def build_audit_group_label(detail: dict[str, Any], mode: str) -> str:
    mode = mode if mode in {"group", "subject", "regional", "collaborator", "status"} else "group"
    if mode == "group":
        return str(detail.get("group_name") or "Sem regra de pontuacao")
    if mode == "subject":
        return f"{detail.get('os_type') or ''} - {detail.get('os_subject') or ''}"
    if mode == "regional":
        return normalize_regional(str(detail.get("regional") or "Sem regional"))
    if mode == "collaborator":
        return str(detail.get("collaborator_name") or "Sem colaborador")
    return str(detail.get("scoring_status") or "Sem status")


def calculate_audit_group_summaries(
    db: Session,
    details: list[dict[str, Any]],
    orders: list[ServiceOrder],
    point_value: float,
    modes: Iterable[str] | None = None,
) -> dict[str, list[dict[str, float | int | str]]]:
    health_by_regional = calculate_regional_health(db, [order for order in orders if completed(order)])
    summaries: dict[str, list[dict[str, float | int | str]]] = {}
    available_modes = {"group", "subject", "regional", "collaborator", "status"}
    selected_modes = [mode for mode in (modes or ["group"]) if mode in available_modes] or ["group"]
    for mode in selected_modes:
        grouped: dict[str, dict[str, float | int | str]] = {}
        for detail in details:
            label = build_audit_group_label(detail, mode)
            item = grouped.setdefault(
                label,
                {
                    "label": label,
                    "service_orders_count": 0,
                    "base_points": 0.0,
                    "penalty_points": 0.0,
                    "net_points": 0.0,
                    "estimated_payment": 0.0,
                    "unscored_service_orders": 0,
                    "penalized_service_orders": 0,
                },
            )
            multiplier = float(health_by_regional.get(normalize_regional(str(detail["regional"])), {}).get("multiplier", 1.0))
            item_point_value = float(detail.get("point_value", point_value))
            item["service_orders_count"] = int(item["service_orders_count"]) + 1
            item["base_points"] = float(item["base_points"]) + float(detail["base_points"])
            item["penalty_points"] = float(item["penalty_points"]) + float(detail["penalty_points"])
            item["net_points"] = float(item["net_points"]) + float(detail["net_points"])
            item["estimated_payment"] = float(item["estimated_payment"]) + float(detail["net_points"]) * multiplier * item_point_value
            item["unscored_service_orders"] = int(item["unscored_service_orders"]) + (1 if detail["is_unscored"] else 0)
            item["penalized_service_orders"] = int(item["penalized_service_orders"]) + (1 if detail["is_penalized"] else 0)

        summaries[mode] = [
            {
                **item,
                "base_points": round(float(item["base_points"]), 2),
                "penalty_points": round(float(item["penalty_points"]), 2),
                "net_points": round(float(item["net_points"]), 2),
                "estimated_payment": round(float(item["estimated_payment"]), 2),
            }
            for item in sorted(grouped.values(), key=lambda value: int(value["service_orders_count"]), reverse=True)
        ]
    return summaries


def calculate_penalty_distribution(
    db: Session,
    orders: list[ServiceOrder],
    details: list[dict[str, Any]] | None = None,
) -> list[dict[str, float | int | str]]:
    details = details if details is not None else explain_orders(db, orders)
    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for detail in details:
        for penalty in detail["penalty_items"]:
            name = str(penalty["name"])
            totals[name] += float(penalty["points"])
            counts[name] += 1

    for fixed_name in ("Reincidencias", "SLA fora do prazo"):
        totals.setdefault(fixed_name, 0.0)
        counts.setdefault(fixed_name, 0)

    return [
        {"name": name, "value": round(value, 2), "service_orders_count": counts[name]}
        for name, value in sorted(totals.items(), key=lambda item: item[1], reverse=True)
    ]


def prefilter_orders_for_detail_processing(
    db: Session,
    orders: list[ServiceOrder],
    collaborator_id: int | None = None,
    group_id: int | None = None,
    os_type: str | None = None,
    os_subject: str | None = None,
    status_sla: str | None = None,
) -> list[ServiceOrder]:
    filtered = orders
    if collaborator_id:
        filtered = [order for order in filtered if int(order.collaborator_id or 0) == collaborator_id]
    if os_type:
        filtered = [order for order in filtered if normalize(os_type) in normalize(order.os_type)]
    if os_subject:
        filtered = [order for order in filtered if normalize(os_subject) in normalize(order.os_subject)]
    if status_sla:
        normalized_filter = sla_status_label(status_sla)
        if normalized_filter != "NAO_IDENTIFICADO":
            filtered = [order for order in filtered if sla_status_label(order.sla_status) == normalized_filter]
        else:
            filtered = [order for order in filtered if normalize(status_sla) in normalize(order.sla_status)]
    if group_id:
        scoring_lookup = build_scoring_rule_lookup(active_scoring_rules(db))
        matched_orders: list[ServiceOrder] = []
        for order in filtered:
            rule = matching_scoring_rule(order, scoring_lookup)
            if rule and rule.group_id == group_id:
                matched_orders.append(order)
        filtered = matched_orders
    return filtered


def filter_details(
    details: list[dict[str, Any]],
    only_scored: bool = False,
    only_unscored: bool = False,
    only_penalized: bool = False,
    only_sla_out: bool = False,
    only_warranty: bool = False,
    only_recurrence: bool = False,
    only_non_recurrent: bool = False,
    only_diagnosis_blocked: bool = False,
    os_type: str | None = None,
    os_subject: str | None = None,
    status_sla: str | None = None,
    group_id: int | None = None,
    collaborator_id: int | None = None,
    regional: str | None = None,
) -> list[dict[str, Any]]:
    filtered = details
    if collaborator_id:
        filtered = [item for item in filtered if int(item["collaborator_id"]) == collaborator_id]
    if regional:
        filtered = [item for item in filtered if same_regional(str(item["regional"]), regional)]
    if only_scored:
        filtered = [item for item in filtered if item["is_scored"]]
    if only_unscored:
        filtered = [item for item in filtered if item["is_unscored"]]
    if only_penalized:
        filtered = [item for item in filtered if item["is_penalized"]]
    if only_sla_out:
        filtered = [item for item in filtered if item["is_sla_out_of_time"]]
    if only_warranty:
        filtered = [item for item in filtered if item["is_warranty"]]
    if only_recurrence:
        filtered = [
            item
            for item in filtered
            if item["recurrence_classification"] in RECURRENCE_DISCOUNT_CLASSIFICATIONS
            or (item["recurrence_discount_applied"] and (item["is_recurrence"] or item["is_warranty"]))
        ]
    if only_non_recurrent:
        filtered = [
            item
            for item in filtered
            if item["recurrence_classification"] in {"os_nao_reincidente", "nao_identificado", "demandas_diferentes", "recorrencia_operacional", "possivel_retorno_sem_regra"}
        ]
    if only_diagnosis_blocked:
        filtered = [
            item
            for item in filtered
            if item["diagnosis_rule_id"]
            and item["diagnosis_action_type"] in {"subtract_points", "cancel_points", "requires_review", "force_points"}
        ]
    if group_id:
        filtered = [item for item in filtered if item["group_id"] == group_id]
    if os_type:
        filtered = [item for item in filtered if normalize(os_type) in normalize(item["os_type"])]
    if os_subject:
        filtered = [item for item in filtered if normalize(os_subject) in normalize(item["os_subject"])]
    if status_sla:
        normalized_filter = sla_status_label(status_sla)
        if normalized_filter != "NAO_IDENTIFICADO":
            filtered = [item for item in filtered if item.get("sla_status_normalized") == normalized_filter]
        else:
            filtered = [item for item in filtered if normalize(status_sla) in normalize(item["sla_status"])]
    return filtered


def get_collaborator_service_orders_detail(
    db: Session,
    collaborator_id: int,
    reference_month: int,
    reference_year: int,
    regional: str | None = None,
    only_scored: bool = False,
    only_unscored: bool = False,
    only_penalized: bool = False,
    only_sla_out: bool = False,
    only_warranty: bool = False,
    only_recurrence: bool = False,
    only_non_recurrent: bool = False,
    only_diagnosis_blocked: bool = False,
    os_type: str | None = None,
    os_subject: str | None = None,
    status_sla: str | None = None,
    group_id: int | None = None,
    point_value: float | None = None,
) -> dict[str, Any]:
    collaborator = db.get(Collaborator, collaborator_id)
    if not collaborator:
        raise ValueError("Colaborador nao encontrado.")

    all_period_orders = period_orders(db, reference_month, reference_year, regional)
    orders = prefilter_orders_for_detail_processing(
        db,
        all_period_orders,
        collaborator_id=collaborator_id,
        group_id=group_id,
        os_type=os_type,
        os_subject=os_subject,
        status_sla=status_sla,
    )
    health_by_regional = calculate_regional_health(db, [order for order in all_period_orders if completed(order)])
    value_per_point = point_value if point_value is not None else get_point_value(db)
    details = explain_orders(db, orders, default_point_value=float(value_per_point))
    effective_regional, health = health_for_details(details, health_by_regional, collaborator.regional)
    official_regional = normalize_regional(collaborator.regional) if collaborator.is_registered and is_valid_regional(collaborator.regional) else None
    multiplier = float(health.get("multiplier", 1.0))
    summary = summarize_details(details, multiplier, value_per_point)
    filtered_base = filter_details(
        details,
        only_scored=only_scored,
        only_unscored=only_unscored,
        only_penalized=only_penalized,
        only_sla_out=only_sla_out,
        only_warranty=only_warranty,
        only_recurrence=only_recurrence,
        only_non_recurrent=only_non_recurrent,
        only_diagnosis_blocked=only_diagnosis_blocked,
        os_type=os_type,
        os_subject=os_subject,
        status_sla=status_sla,
        group_id=group_id,
    )

    return {
        "collaborator": {
            "id": collaborator.id,
            "name": collaborator.name,
            "role": collaborator.role,
            "regional": official_regional or effective_regional or normalize_regional(collaborator.regional),
        },
        "period": {
            "reference_month": reference_month,
            "reference_year": reference_year,
            "regional": regional,
        },
        "summary": summary,
        "orders": filtered_base,
    }


def get_period_audit(
    db: Session,
    reference_month: int,
    reference_year: int,
    regional: str | None = None,
    collaborator_id: int | None = None,
    group_id: int | None = None,
    only_scored: bool = False,
    only_unscored: bool = False,
    only_penalized: bool = False,
    only_sla_out: bool = False,
    only_warranty: bool = False,
    only_recurrence: bool = False,
    only_non_recurrent: bool = False,
    only_diagnosis_blocked: bool = False,
    os_type: str | None = None,
    os_subject: str | None = None,
    status_sla: str | None = None,
    audit_group_mode: str | None = None,
    audit_group_label: str | None = None,
    point_value: float | None = None,
    page: int = 1,
    page_size: int = 100,
) -> dict[str, Any]:
    period_base_orders = period_orders(db, reference_month, reference_year, regional)
    orders = prefilter_orders_for_detail_processing(
        db,
        period_base_orders,
        collaborator_id=collaborator_id,
        group_id=group_id,
        os_type=os_type,
        os_subject=os_subject,
        status_sla=status_sla,
    )
    value_per_point = point_value if point_value is not None else get_point_value(db)
    details = explain_orders(db, orders, default_point_value=float(value_per_point))
    filtered_base = filter_details(
        details,
        only_scored=only_scored,
        only_unscored=only_unscored,
        only_penalized=only_penalized,
        only_sla_out=only_sla_out,
        only_warranty=only_warranty,
        only_recurrence=only_recurrence,
        only_non_recurrent=only_non_recurrent,
        only_diagnosis_blocked=only_diagnosis_blocked,
        os_type=os_type,
        os_subject=os_subject,
        status_sla=status_sla,
        group_id=group_id,
        collaborator_id=collaborator_id,
        regional=regional,
    )
    requested_group_mode = audit_group_mode if audit_group_mode in {"group", "subject", "regional", "collaborator", "status"} else "group"
    group_summaries = calculate_audit_group_summaries(
        db,
        filtered_base,
        period_base_orders,
        float(value_per_point),
        modes=[requested_group_mode],
    )
    filtered = filtered_base
    if audit_group_label:
        filtered = [item for item in filtered_base if build_audit_group_label(item, requested_group_mode) == audit_group_label]
    page = max(page, 1)
    page_size = min(max(page_size, 25), 5000)
    total_orders = len(filtered)
    total_pages = max((total_orders + page_size - 1) // page_size, 1)
    if page > total_pages:
        page = total_pages
    start = (page - 1) * page_size
    paginated = filtered[start : start + page_size]
    return {
        "period": {
            "reference_month": reference_month,
            "reference_year": reference_year,
            "regional": regional,
        },
        "summary": summarize_audit_details(db, filtered, period_base_orders, value_per_point),
        "orders": paginated,
        "group_summaries": group_summaries,
        "total_orders": total_orders,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


def get_recurrence_audit(db: Session, service_order_id: int) -> dict[str, Any]:
    target = db.scalar(
        select(ServiceOrder)
        .options(selectinload(ServiceOrder.collaborator))
        .where(ServiceOrder.id == service_order_id)
    )
    if not target:
        raise ValueError("O.S nao encontrada.")

    all_orders = sorted(
        real_service_orders(
            list(
                db.scalars(
                    select(ServiceOrder).options(selectinload(ServiceOrder.collaborator))
                )
            )
        ),
        key=lambda item: _order_date(item) or item.opened_at,
    )
    identity_fields = _configured_recurrence_identity_fields(db)
    identity = _recurrence_identity_for_fields(target, identity_fields)
    if not identity:
        related_orders = [target]
        identity_type = "Vinculo configurado"
        identity_value = f"{_configured_recurrence_identity_label(identity_fields)} nao importado"
    else:
        identity_kind, _ = identity.split(":", 1)
        if identity_kind == "login":
            identity_type = "Login"
            identity_value = target.customer_login
        elif identity_kind == "contract":
            identity_type = "Contrato"
            identity_value = target.contract_id
        else:
            identity_type = "Cliente"
            identity_value = target.customer_name
        related_orders = [order for order in all_orders if _recurrence_identity_for_fields(order, identity_fields) == identity]

    related_details = explain_orders(db, related_orders)
    details_by_id = {int(detail["id"]): detail for detail in related_details}
    current_detail = details_by_id.get(target.id) or explain_order(
        target,
        build_scoring_rule_lookup(active_scoring_rules(db)),
        active_diagnosis_rules(db),
        active_sla_penalty_rules(db),
        recurrence_penalties(db, related_orders, build_scoring_rule_lookup(active_scoring_rules(db))),
        get_setting(db, "warranty_mode", "score_full"),
        float(get_setting(db, "warranty_reduction_percentage", "0")),
        get_point_value(db),
    )

    origin_detail: dict[str, Any] | None = current_detail if current_detail.get("recurrence_classification") else None
    posterior_detail: dict[str, Any] | None = None
    related_code = current_detail.get("recurrence_related_os_code")
    if related_code:
        posterior_detail = next((detail for detail in related_details if detail["os_code"] == related_code), None)
    else:
        origin_detail = next(
            (detail for detail in related_details if detail.get("recurrence_related_os_code") == target.os_code),
            origin_detail,
        )
        if origin_detail and origin_detail.get("recurrence_related_os_code"):
            posterior_detail = next(
                (detail for detail in related_details if detail["os_code"] == origin_detail.get("recurrence_related_os_code")),
                current_detail,
            )

    audit_source = origin_detail or current_detail
    return {
        "identity_type": identity_type,
        "identity_value": identity_value,
        "classification": audit_source.get("recurrence_classification"),
        "discount_target_os_code": origin_detail.get("os_code") if origin_detail and origin_detail.get("recurrence_discount_applied") else None,
        "discount_points": float(origin_detail.get("recurrence_penalty_points", 0)) if origin_detail else 0.0,
        "discount_applied": bool(origin_detail.get("recurrence_discount_applied")) if origin_detail else False,
        "evidence": audit_source.get("recurrence_evidence", [])
        or (
            []
            if identity
            else [f"Os campos de vinculo configurados ({_configured_recurrence_identity_label(identity_fields)}) nao foram encontrados nesta O.S."]
        ),
        "current_order": current_detail,
        "origin_order": origin_detail,
        "posterior_order": posterior_detail,
        "related_orders": related_details,
    }


def financial_breakdowns(
    db: Session,
    orders: list[ServiceOrder],
    point_value: float,
    details: list[dict[str, Any]] | None = None,
    health_by_regional: dict[str, dict[str, float | int | str]] | None = None,
) -> dict[str, list[dict[str, float | int | str]]]:
    details = details if details is not None else explain_orders(db, orders)
    health_by_regional = health_by_regional or calculate_regional_health(db, [order for order in orders if completed(order)])
    regional_totals: dict[str, dict[str, float | int | str]] = {}
    group_totals: dict[str, dict[str, float | int | str]] = {}
    subject_totals: dict[str, dict[str, float | int | str]] = {}
    collaborator_totals: dict[int, dict[str, float | int | str]] = {}
    penalized_subject_totals: dict[str, dict[str, float | int | str]] = {}
    scoring_subject_totals: dict[str, dict[str, float | int | str]] = {}
    unmapped_subject_totals: dict[str, dict[str, float | int | str]] = {}
    estimated_unmapped_points = average_group_default_points(db)

    for detail in details:
        if not is_identified_collaborator_detail(detail):
            continue
        regional = normalize_regional(str(detail["regional"]))
        multiplier = float(health_by_regional.get(regional, {}).get("multiplier", 1.0))
        detail_point_value = float(detail.get("point_value", point_value))
        estimated = round(float(detail["net_points"]) * multiplier * detail_point_value, 2)
        penalty_impact = round(float(detail["penalty_points"]) * multiplier * detail_point_value, 2)
        gross_impact = round(float(detail["base_points"]) * multiplier * detail_point_value, 2)

        regional_item = regional_totals.setdefault(regional, {"regional": regional, "orders": 0, "estimated_payment": 0.0})
        regional_item["orders"] = int(regional_item["orders"]) + 1
        regional_item["estimated_payment"] = round(float(regional_item["estimated_payment"]) + estimated, 2)

        group = str(detail["group_name"] or "Sem regra")
        group_item = group_totals.setdefault(group, {"group": group, "orders": 0, "net_points": 0.0, "estimated_payment": 0.0})
        group_item["orders"] = int(group_item["orders"]) + 1
        group_item["net_points"] = round(float(group_item["net_points"]) + float(detail["net_points"]), 2)
        group_item["estimated_payment"] = round(float(group_item["estimated_payment"]) + estimated, 2)

        subject_key = f"{detail['os_type']} | {detail['os_subject']}"
        subject_item = subject_totals.setdefault(
            subject_key,
            {
                "os_type": detail["os_type"],
                "os_subject": detail["os_subject"],
                "group": group,
                "orders": 0,
                "net_points": 0.0,
                "estimated_payment": 0.0,
            },
        )
        subject_item["orders"] = int(subject_item["orders"]) + 1
        subject_item["net_points"] = round(float(subject_item["net_points"]) + float(detail["net_points"]), 2)
        subject_item["estimated_payment"] = round(float(subject_item["estimated_payment"]) + estimated, 2)

        collaborator_id = int(detail["collaborator_id"])
        collaborator_item = collaborator_totals.setdefault(
            collaborator_id,
            {
                "collaborator_id": collaborator_id,
                "collaborator_name": detail["collaborator_name"],
                "regional": regional,
                "orders": 0,
                "net_points": 0.0,
                "estimated_payment": 0.0,
            },
        )
        collaborator_item["orders"] = int(collaborator_item["orders"]) + 1
        collaborator_item["net_points"] = round(float(collaborator_item["net_points"]) + float(detail["net_points"]), 2)
        collaborator_item["estimated_payment"] = round(float(collaborator_item["estimated_payment"]) + estimated, 2)

        scoring_item = scoring_subject_totals.setdefault(
            subject_key,
            {
                "os_type": detail["os_type"],
                "os_subject": detail["os_subject"],
                "group": group,
                "orders": 0,
                "gross_points": 0.0,
                "estimated_payment": 0.0,
            },
        )
        scoring_item["orders"] = int(scoring_item["orders"]) + 1
        scoring_item["gross_points"] = round(float(scoring_item["gross_points"]) + float(detail["base_points"]), 2)
        scoring_item["estimated_payment"] = round(float(scoring_item["estimated_payment"]) + gross_impact, 2)

        if float(detail["penalty_points"]) > 0:
            penalty_item = penalized_subject_totals.setdefault(
                subject_key,
                {
                    "os_type": detail["os_type"],
                    "os_subject": detail["os_subject"],
                    "group": group,
                    "orders": 0,
                    "penalty_points": 0.0,
                    "estimated_payment": 0.0,
                },
            )
            penalty_item["orders"] = int(penalty_item["orders"]) + 1
            penalty_item["penalty_points"] = round(float(penalty_item["penalty_points"]) + float(detail["penalty_points"]), 2)
            penalty_item["estimated_payment"] = round(float(penalty_item["estimated_payment"]) + penalty_impact, 2)

        if detail["is_unscored"]:
            unmapped_item = unmapped_subject_totals.setdefault(
                subject_key,
                {
                    "os_type": detail["os_type"],
                    "os_subject": detail["os_subject"],
                    "orders": 0,
                    "estimated_payment": 0.0,
                },
            )
            unmapped_item["orders"] = int(unmapped_item["orders"]) + 1
            unmapped_item["estimated_payment"] = round(
                float(unmapped_item["estimated_payment"]) + estimated_unmapped_points * point_value,
                2,
            )

    return {
        "cost_by_regional": sorted(regional_totals.values(), key=lambda item: float(item["estimated_payment"]), reverse=True),
        "cost_by_group": sorted(group_totals.values(), key=lambda item: float(item["estimated_payment"]), reverse=True),
        "cost_by_subject": sorted(subject_totals.values(), key=lambda item: float(item["estimated_payment"]), reverse=True)[:30],
        "cost_by_collaborator": sorted(
            collaborator_totals.values(), key=lambda item: float(item["estimated_payment"]), reverse=True
        )[:30],
        "top_penalized_subjects": sorted(
            penalized_subject_totals.values(), key=lambda item: float(item["estimated_payment"]), reverse=True
        )[:30],
        "top_scoring_subjects": sorted(
            scoring_subject_totals.values(), key=lambda item: float(item["gross_points"]), reverse=True
        )[:30],
        "top_unmapped_subjects": sorted(
            unmapped_subject_totals.values(), key=lambda item: int(item["orders"]), reverse=True
        )[:30],
    }


def average_group_default_points(db: Session) -> float:
    groups = list(db.scalars(select(ScoringGroup).where(ScoringGroup.active.is_(True))))
    if not groups:
        return 0.0
    return round(sum(float(group.default_points) for group in groups) / len(groups), 2)


def unmapped_subjects(
    db: Session,
    reference_month: int,
    reference_year: int,
    regional: str | None = None,
) -> list[dict[str, Any]]:
    orders = real_service_orders(period_orders(db, reference_month, reference_year, regional))
    details = [detail for detail in explain_orders(db, orders) if detail["is_unscored"]]
    point_value = get_point_value(db)
    estimated_points_per_order = average_group_default_points(db)
    grouped: dict[tuple[str, str], dict[str, Any]] = {}

    for detail in details:
        key = (str(detail["os_type"]), str(detail["os_subject"]))
        item = grouped.setdefault(
            key,
            {
                "os_type": key[0],
                "os_subject": key[1],
                "service_orders_count": 0,
                "collaborator_ids": set(),
                "regionals": [],
            },
        )
        item["service_orders_count"] += 1
        item["collaborator_ids"].add(detail["collaborator_id"])
        item["regionals"].append(normalize_regional(str(detail["regional"])))

    result = []
    for item in grouped.values():
        count = int(item["service_orders_count"])
        regional_counts = Counter(item["regionals"])
        estimated_points = round(count * estimated_points_per_order, 2)
        result.append(
            {
                "os_type": item["os_type"],
                "os_subject": item["os_subject"],
                "service_orders_count": count,
                "collaborators_count": len(item["collaborator_ids"]),
                "predominant_regional": regional_counts.most_common(1)[0][0] if regional_counts else "-",
                "estimated_points": estimated_points,
                "estimated_financial_impact": round(estimated_points * point_value, 2),
            }
        )

    return sorted(result, key=lambda item: item["service_orders_count"], reverse=True)


def imported_diagnosis_stats(
    db: Session,
    reference_month: int,
    reference_year: int,
    regional: str | None = None,
    only_unmapped: bool = False,
) -> list[dict[str, Any]]:
    orders = real_service_orders(period_orders(db, reference_month, reference_year, regional))
    details = explain_orders(db, orders)
    point_value = get_point_value(db)
    average_points = average_group_default_points(db)
    rules_by_name = {normalize(rule.diagnosis_name): rule for rule in all_diagnosis_rules(db)}
    grouped: dict[str, dict[str, Any]] = {}

    for detail in details:
        diagnosis_name = str(detail["diagnosis"] or "Nao informado")
        if normalize(diagnosis_name) == normalize("Nao informado"):
            continue

        key = normalize(diagnosis_name)
        item = grouped.setdefault(
            key,
            {
                "diagnosis_name": diagnosis_name,
                "service_orders_count": 0,
                "subjects": [],
                "collaborator_ids": set(),
                "regionals": [],
                "estimated_impact": 0.0,
            },
        )
        item["service_orders_count"] += 1
        item["subjects"].append(str(detail["os_subject"]))
        item["collaborator_ids"].add(detail["collaborator_id"])
        item["regionals"].append(normalize_regional(str(detail["regional"])))
        item["estimated_impact"] = round(
            float(item["estimated_impact"])
            + float(detail["diagnosis_penalty_points"]) * float(detail.get("point_value", point_value)),
            2,
        )

    result: list[dict[str, Any]] = []
    for key, item in grouped.items():
        rule = rules_by_name.get(key)
        if only_unmapped and rule:
            continue
        subject_counts = Counter(item["subjects"])
        regional_counts = Counter(item["regionals"])
        count = int(item["service_orders_count"])
        impact = float(item["estimated_impact"])
        if impact == 0 and not rule:
            impact = round(count * average_points * point_value, 2)

        result.append(
            {
                "diagnosis_name": item["diagnosis_name"],
                "service_orders_count": count,
                "subjects_count": len(subject_counts),
                "collaborators_count": len(item["collaborator_ids"]),
                "predominant_regional": regional_counts.most_common(1)[0][0] if regional_counts else "-",
                "related_subjects": [subject for subject, _ in subject_counts.most_common(8)],
                "action_type": rule.action_type if rule else None,
                "penalty_points": rule.penalty_points if rule else None,
                "force_points_value": rule.force_points_value if rule else None,
                "estimated_impact": round(impact, 2),
                "active": rule.active if rule else None,
                "rule_id": rule.id if rule else None,
                "has_rule": rule is not None,
            }
        )

    return sorted(result, key=lambda item: int(item["service_orders_count"]), reverse=True)
