"""Regras de alerta parametrizáveis (Administração → UNI Intelligence → Regras de Alertas).

Camada de CONFIGURAÇÃO sobre os detectores/consultas já existentes (`login_geo_clusters.
find_offline_login_clusters`, `operations.queries.overview`/`collaborator_sla`,
`intelligence.scheduler.recent_runs`) - nenhuma regra reimplementa detecção do zero. Quem
executa as regras é `monitors/rules_engine.py` (o único monitor novo do registry): a cada ciclo,
lê todas as regras ATIVAS e delega para a função de avaliação do `rule_type`.

Mesmo espírito de validação de `cockpit.py::validate_widget_entries` - campo de scope/param não
suportado pelo `rule_type` nunca é ignorado em silêncio, sempre bloqueia na escrita."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import IntelligenceAlertRule

RULE_TYPES = (
    "OS_CONCENTRATION_AREA",
    "OS_CONCENTRATION_LINEAR",
    "OS_OPENING_ABOVE_AVERAGE",
    "OS_GROWTH_ANOMALY",
    "BACKLOG_THRESHOLD",
    "SLA_THRESHOLD",
    "COLLECTIVE_OUTAGE",
    "MONITOR_UNHEALTHY",
)

SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

# Campos de escopo (FilterContractV1) que cada rule_type aceita - uma regra que não opera sobre
# `operations_orders`/logins de uma população recortável (ex.: MONITOR_UNHEALTHY, que olha a saúde
# de UM monitor específico) não aceita escopo nenhum.
RULE_TYPE_ALLOWED_SCOPE: dict[str, frozenset[str]] = {
    "OS_CONCENTRATION_AREA": frozenset({"regionals", "cities", "sectors", "os_subjects"}),
    "OS_CONCENTRATION_LINEAR": frozenset({"regionals", "cities", "sectors", "os_subjects"}),
    "OS_OPENING_ABOVE_AVERAGE": frozenset({"regionals", "cities", "sectors", "os_subjects", "team_models"}),
    "OS_GROWTH_ANOMALY": frozenset({"regionals", "cities", "sectors", "os_subjects", "team_models"}),
    "BACKLOG_THRESHOLD": frozenset({"regionals", "cities", "sectors", "os_subjects", "team_models"}),
    "SLA_THRESHOLD": frozenset({"regionals", "cities", "sectors", "os_subjects", "team_models"}),
    "COLLECTIVE_OUTAGE": frozenset({"regionals"}),
    "MONITOR_UNHEALTHY": frozenset(),
}

# Parâmetros que cada rule_type aceita em `params_json`. Tipo/uso de cada um documentado em
# rules_engine.py (quem efetivamente os lê).
RULE_TYPE_ALLOWED_PARAMS: dict[str, frozenset[str]] = {
    "OS_CONCENTRATION_AREA": frozenset(
        {"min_count", "window_minutes", "radius_meters", "historical_comparison", "min_multiplier_over_average", "baseline_days"}
    ),
    "OS_CONCENTRATION_LINEAR": frozenset(
        {"min_count", "window_minutes", "radius_meters", "historical_comparison", "min_multiplier_over_average", "baseline_days"}
    ),
    "OS_OPENING_ABOVE_AVERAGE": frozenset(
        {"min_count", "window_minutes", "historical_comparison", "min_multiplier_over_average", "baseline_days"}
    ),
    "OS_GROWTH_ANOMALY": frozenset(
        {"min_count", "window_minutes", "historical_comparison", "min_multiplier_over_average", "baseline_days", "group_by"}
    ),
    "BACKLOG_THRESHOLD": frozenset({"threshold_value"}),
    "SLA_THRESHOLD": frozenset({"threshold_value", "window_days"}),
    "COLLECTIVE_OUTAGE": frozenset({"min_count", "window_minutes", "radius_meters"}),
    "MONITOR_UNHEALTHY": frozenset({"target_monitor_key", "max_consecutive_failures"}),
}

# group_by de OS_GROWTH_ANOMALY - dimensão que a comparação "acima da média" particiona (pedido
# explícito: "por regional/cidade/assunto").
GROUP_BY_VALUES = ("regional", "city", "os_subject")

DEFAULT_PARAMS_BY_TYPE: dict[str, dict] = {
    "OS_CONCENTRATION_AREA": {"min_count": 5, "window_minutes": 60, "radius_meters": 300, "historical_comparison": False, "baseline_days": 14},
    "OS_CONCENTRATION_LINEAR": {"min_count": 5, "window_minutes": 90, "radius_meters": 800, "historical_comparison": False, "baseline_days": 14},
    "OS_OPENING_ABOVE_AVERAGE": {"window_minutes": 60, "historical_comparison": True, "min_multiplier_over_average": 1.5, "baseline_days": 14},
    "OS_GROWTH_ANOMALY": {"window_minutes": 60, "historical_comparison": True, "min_multiplier_over_average": 1.5, "baseline_days": 14, "group_by": "regional"},
    "BACKLOG_THRESHOLD": {"threshold_value": 500},
    "SLA_THRESHOLD": {"threshold_value": 80.0, "window_days": 7},
    "COLLECTIVE_OUTAGE": {"min_count": 3, "window_minutes": 90, "radius_meters": 300},
    "MONITOR_UNHEALTHY": {"max_consecutive_failures": 2},
}


class AlertRuleValidationError(ValueError):
    """Erro de validação de regra de alerta - vira 422 no REST."""


def _validate_scope(rule_type: str, scope: dict) -> dict:
    allowed = RULE_TYPE_ALLOWED_SCOPE.get(rule_type, frozenset())
    for field in scope or {}:
        if field not in allowed:
            raise AlertRuleValidationError(
                f"escopo {field!r} não é suportado pelo tipo de regra {rule_type!r}. Campos aceitos: {sorted(allowed) or 'nenhum'}."
            )
    return dict(scope or {})


def _validate_params(rule_type: str, params: dict) -> dict:
    allowed = RULE_TYPE_ALLOWED_PARAMS.get(rule_type, frozenset())
    for field in params or {}:
        if field not in allowed:
            raise AlertRuleValidationError(
                f"parâmetro {field!r} não é suportado pelo tipo de regra {rule_type!r}. Parâmetros aceitos: {sorted(allowed) or 'nenhum'}."
            )
    merged = {**DEFAULT_PARAMS_BY_TYPE.get(rule_type, {}), **(params or {})}
    if "group_by" in merged and merged["group_by"] not in GROUP_BY_VALUES:
        raise AlertRuleValidationError(f"group_by inválido: {merged['group_by']!r}. Use um de {GROUP_BY_VALUES}.")
    for numeric_field in ("min_count", "window_minutes", "radius_meters", "baseline_days", "threshold_value", "window_days", "max_consecutive_failures"):
        if numeric_field in merged and merged[numeric_field] is not None:
            try:
                merged[numeric_field] = float(merged[numeric_field]) if numeric_field in ("threshold_value", "radius_meters") else int(merged[numeric_field])
            except (TypeError, ValueError):
                raise AlertRuleValidationError(f"{numeric_field} precisa ser numérico.") from None
            if merged[numeric_field] <= 0:
                raise AlertRuleValidationError(f"{numeric_field} precisa ser maior que zero.")
    if "min_multiplier_over_average" in merged and merged["min_multiplier_over_average"] is not None:
        try:
            merged["min_multiplier_over_average"] = float(merged["min_multiplier_over_average"])
        except (TypeError, ValueError):
            raise AlertRuleValidationError("min_multiplier_over_average precisa ser numérico.") from None
        if merged["min_multiplier_over_average"] < 1.0:
            raise AlertRuleValidationError("min_multiplier_over_average precisa ser >= 1.0 (senão qualquer volume dispararia a regra).")
    return merged


def validate_alert_rule(*, rule_type: str, scope: dict, params: dict) -> tuple[dict, dict]:
    if rule_type not in RULE_TYPES:
        raise AlertRuleValidationError(f"rule_type inválido: {rule_type!r}. Use um de {RULE_TYPES}.")
    return _validate_scope(rule_type, scope), _validate_params(rule_type, params)


def list_alert_rules(db: Session, *, active: bool | None = None) -> list[IntelligenceAlertRule]:
    conditions = []
    if active is not None:
        conditions.append(IntelligenceAlertRule.active.is_(active))
    return list(db.scalars(select(IntelligenceAlertRule).where(*conditions).order_by(IntelligenceAlertRule.key)))


def get_alert_rule(db: Session, key: str) -> IntelligenceAlertRule | None:
    return db.scalar(select(IntelligenceAlertRule).where(IntelligenceAlertRule.key == key))


def create_alert_rule(
    db: Session,
    *,
    key: str,
    name: str,
    rule_type: str,
    scope: dict,
    params: dict,
    severity: str = "MEDIUM",
    active: bool = True,
    cooldown_minutes: int = 0,
    confirm_cycles: int = 1,
    resolve_cycles: int = 2,
) -> IntelligenceAlertRule:
    if not key or not key.strip():
        raise AlertRuleValidationError("key é obrigatória.")
    if get_alert_rule(db, key) is not None:
        raise AlertRuleValidationError(f"já existe uma regra com key {key!r}.")
    if not name or not name.strip():
        raise AlertRuleValidationError("name é obrigatório.")
    if severity not in SEVERITIES:
        raise AlertRuleValidationError(f"severity inválida: {severity!r}. Use um de {SEVERITIES}.")
    validated_scope, validated_params = validate_alert_rule(rule_type=rule_type, scope=scope, params=params)
    rule = IntelligenceAlertRule(
        key=key.strip(),
        name=name.strip(),
        rule_type=rule_type,
        active=active,
        scope_json=validated_scope,
        params_json=validated_params,
        severity=severity,
        cooldown_minutes=max(cooldown_minutes, 0),
        confirm_cycles=max(confirm_cycles, 1),
        resolve_cycles=max(resolve_cycles, 1),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def update_alert_rule(
    db: Session,
    rule: IntelligenceAlertRule,
    *,
    name: str | None = None,
    active: bool | None = None,
    scope: dict | None = None,
    params: dict | None = None,
    severity: str | None = None,
    cooldown_minutes: int | None = None,
    confirm_cycles: int | None = None,
    resolve_cycles: int | None = None,
) -> IntelligenceAlertRule:
    if name is not None:
        if not name.strip():
            raise AlertRuleValidationError("name não pode ficar vazio.")
        rule.name = name.strip()
    if severity is not None:
        if severity not in SEVERITIES:
            raise AlertRuleValidationError(f"severity inválida: {severity!r}. Use um de {SEVERITIES}.")
        rule.severity = severity
    if scope is not None or params is not None:
        validated_scope, validated_params = validate_alert_rule(
            rule_type=rule.rule_type,
            scope=scope if scope is not None else rule.scope_json,
            params=params if params is not None else rule.params_json,
        )
        rule.scope_json = validated_scope
        rule.params_json = validated_params
    if active is not None:
        rule.active = active
    if cooldown_minutes is not None:
        rule.cooldown_minutes = max(cooldown_minutes, 0)
    if confirm_cycles is not None:
        rule.confirm_cycles = max(confirm_cycles, 1)
    if resolve_cycles is not None:
        rule.resolve_cycles = max(resolve_cycles, 1)
    db.commit()
    db.refresh(rule)
    return rule


def alert_rule_to_out(rule: IntelligenceAlertRule) -> dict:
    return {
        "id": rule.id,
        "key": rule.key,
        "name": rule.name,
        "rule_type": rule.rule_type,
        "active": rule.active,
        "scope": rule.scope_json,
        "params": rule.params_json,
        "severity": rule.severity,
        "cooldown_minutes": rule.cooldown_minutes,
        "confirm_cycles": rule.confirm_cycles,
        "resolve_cycles": rule.resolve_cycles,
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
    }


def build_alert_rule_catalog() -> dict:
    return {
        "rule_types": [
            {
                "key": rule_type,
                "allowed_scope": sorted(RULE_TYPE_ALLOWED_SCOPE.get(rule_type, frozenset())),
                "allowed_params": sorted(RULE_TYPE_ALLOWED_PARAMS.get(rule_type, frozenset())),
                "default_params": DEFAULT_PARAMS_BY_TYPE.get(rule_type, {}),
            }
            for rule_type in RULE_TYPES
        ],
        "severities": list(SEVERITIES),
        "group_by_values": list(GROUP_BY_VALUES),
    }


def last_resolution_at(db: Session, dedupe_key: str) -> datetime | None:
    """Quando a ocorrência ativa mais recente desta dedupe_key foi RESOLVED/DISMISSED pela última
    vez - usado só para `cooldown_minutes` (rules_engine.py). Consulta o histórico de eventos já
    existente (`intelligence_alert_events`), não cria nenhum estado novo."""
    from .models import IntelligenceAlert, IntelligenceAlertEvent

    row = db.execute(
        select(IntelligenceAlertEvent.created_at)
        .join(IntelligenceAlert, IntelligenceAlert.id == IntelligenceAlertEvent.alert_id)
        .where(
            IntelligenceAlert.dedupe_key == dedupe_key,
            IntelligenceAlertEvent.event_type.in_(("RESOLVED", "DISMISSED")),
        )
        .order_by(IntelligenceAlertEvent.created_at.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    value = row[0]
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
