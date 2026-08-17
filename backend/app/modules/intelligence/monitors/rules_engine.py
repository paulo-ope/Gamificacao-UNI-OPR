"""Motor de execução das Regras de Alertas configuráveis (Administração → UNI Intelligence →
Regras de Alertas). Único monitor NOVO desta rodada - todo o resto é camada de configuração sobre
detectores/consultas JÁ EXISTENTES:

- OS_CONCENTRATION_AREA / OS_CONCENTRATION_LINEAR: reaproveita `_cluster_points` de
  `operations.login_geo_clusters` (mesmo DBSCAN por raio já usado no incidente coletivo de rede),
  mas sobre coordenadas de O.S. (`OperationOrder.latitude/longitude`) em vez de login - detecta
  concentração de abertura de O.S. SEM exigir queda de login antes (pedido explícito).
  OS_CONCENTRATION_LINEAR usa o MESMO algoritmo com raio maior por padrão (simplificação honesta:
  o projeto não tem topologia de rua/trecho estruturada - só `endereco` como string única - um
  corredor rural/linear na prática já aparece como cluster por raio quando o raio é generoso o
  suficiente, como confirmado num AI_INSIGHT real publicado nesta base).
- OS_OPENING_ABOVE_AVERAGE / OS_GROWTH_ANOMALY: contagem de O.S. abertas na janela, comparada a um
  baseline histórico simples (mesma janela de horário, N dias anteriores, ver
  `_historical_average_count`).
- BACKLOG_THRESHOLD / SLA_THRESHOLD: reaproveita `operations.queries.overview` (mesma função usada
  pelo cockpit).
- COLLECTIVE_OUTAGE: reaproveita `find_offline_login_clusters` (mesma função do monitor
  `collective_outage`) - permite regras adicionais com parâmetros próprios (ex.: mais sensível para
  uma regional específica) sem tocar no monitor padrão.
- MONITOR_UNHEALTHY: reaproveita `scheduler.recent_runs`/`count_consecutive_failures` (mesma base
  do monitor `monitor_health`) para um monitor-alvo configurável.

Confirmação/cooldown são avaliados AQUI (não em alerts.py, que continua genérico para todos os
monitores): `confirm_cycles` usa um contador em `app_settings` por dedupe_key (mesmo padrão de
estado leve já usado por scheduler.py); `cooldown_minutes` consulta o histórico de eventos já
existente (`alert_rules.last_resolution_at`) - nenhum dos dois precisa de tabela nova."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import mean

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.operations import queries as ops_queries
from app.modules.operations.login_geo_clusters import _cluster_points
from app.modules.operations.login_aggregate import login_incident_analysis
from app.modules.operations.models import OperationLoginCurrentStatus, OperationOrder
from app.modules.operations.period import OPERATIONS_TIMEZONE
from app.modules.operations.schemas import _service_address_from_payload
from app.modules.operations.scope import PRIMARY_SECTOR_NAMES
from app.services.calculation import get_setting, upsert_setting

from ..alert_rules import last_resolution_at, list_alert_rules
from ..cockpit import _to_operations_rest_filters
from ..models import IntelligenceAlertRule
from ..scheduler import count_consecutive_failures, recent_runs
from ..scope import system_user
from ..types import MonitorDetection, MonitorRunResult

MIN_BASELINE_SAMPLES = 3


class _OrderPoint:
    __slots__ = ("order_id", "order_code", "address", "neighborhood", "latitude", "longitude", "regional", "city", "os_subject")

    def __init__(
        self,
        order_id: int,
        order_code: str,
        address: str | None,
        neighborhood: str | None,
        latitude: float,
        longitude: float,
        regional: str | None,
        city: str | None,
        os_subject: str | None,
    ) -> None:
        self.order_id = order_id
        self.order_code = order_code
        self.address = address
        self.neighborhood = neighborhood
        self.latitude = latitude
        self.longitude = longitude
        self.regional = regional
        self.city = city
        self.os_subject = os_subject


def _scope_conditions(scope: dict, *, default_sectors: bool = True) -> list:
    conditions = []
    regionals = scope.get("regionals") or []
    if regionals:
        conditions.append(OperationOrder.regional.in_(regionals))
    cities = scope.get("cities") or []
    if cities:
        conditions.append(OperationOrder.city.in_(cities))
    sectors = scope.get("sectors") or (list(PRIMARY_SECTOR_NAMES) if default_sectors else [])
    if sectors:
        conditions.append(OperationOrder.sector.in_(sectors))
    os_subjects = scope.get("os_subjects") or []
    if os_subjects:
        conditions.append(OperationOrder.os_subject.in_(os_subjects))
    return conditions


def _historical_average_count(db: Session, *, conditions_builder, window_minutes: int, baseline_days: int, now: datetime) -> float:
    """Média de O.S. abertas em janelas do MESMO tamanho e MESMO horário do dia, nos
    `baseline_days` dias anteriores (mesmo escopo) - baseline simples pedido explicitamente
    (7/14/28 dias), sem cruzar regional/assunto/faixa horária em múltiplas dimensões ao mesmo
    tempo (isso ficaria pesado e o pedido foi "algo simples inicialmente"). NÃO decide sozinha se a
    amostra é suficiente - uma janela sem nenhuma O.S. é uma medição válida (zero), não uma
    ausência de dado; ver `_days_of_history_available` para essa decisão."""
    counts: list[int] = []
    for day_offset in range(1, baseline_days + 1):
        window_end = now - timedelta(days=day_offset)
        window_start = window_end - timedelta(minutes=window_minutes)
        conditions = conditions_builder(window_start, window_end)
        count = db.scalar(select(func.count(OperationOrder.id)).where(*conditions)) or 0
        counts.append(count)
    return mean(counts) if counts else 0.0


def _days_of_history_available(db: Session, *, scope_conditions: list, now: datetime) -> int:
    """Quantos dias de histórico realmente EXISTEM para este escopo (da O.S. mais antiga até
    agora) - "achado real" F5: uma janela de baseline sempre produz `baseline_days` números (zero
    é uma medição válida), então não dá pra usar a quantidade de dias verificados como prova de
    amostra suficiente. O que importa é se o sistema tem dado antigo o bastante para comparar -
    checado aqui pela data da O.S. mais antiga que bate o escopo, não pela contagem por janela."""
    earliest = db.scalar(select(func.min(OperationOrder.opened_at)).where(*scope_conditions))
    if earliest is None:
        return 0
    earliest = earliest if earliest.tzinfo else earliest.replace(tzinfo=timezone.utc)
    return max((now - earliest).days, 0)


def _confirm_hits(db: Session, rule_key: str, dedupe_key: str, confirm_cycles: int) -> int:
    """Contador de ciclos consecutivos que esta dedupe_key bateu a condição da regra - estado leve
    em app_settings (mesmo padrão de scheduler.py::_set_next_allowed_at), não uma tabela nova.
    Retorna a contagem JÁ incrementada neste ciclo."""
    setting_key = f"intelligence_rule_hits_{rule_key}_{abs(hash(dedupe_key))}"
    current = int(get_setting(db, setting_key, "0") or "0")
    current += 1
    upsert_setting(db, setting_key, str(current))
    return current


def _reset_hits(db: Session, rule_key: str, dedupe_key: str) -> None:
    setting_key = f"intelligence_rule_hits_{rule_key}_{abs(hash(dedupe_key))}"
    upsert_setting(db, setting_key, "0")


def _in_cooldown(db: Session, dedupe_key: str, cooldown_minutes: int) -> bool:
    if cooldown_minutes <= 0:
        return False
    resolved_at = last_resolution_at(db, dedupe_key)
    if resolved_at is None:
        return False
    return datetime.now(timezone.utc) < resolved_at + timedelta(minutes=cooldown_minutes)


def _gate_by_confirm_and_cooldown(db: Session, rule: IntelligenceAlertRule, candidates: list[MonitorDetection]) -> list[MonitorDetection]:
    """Aplica confirm_cycles (só emite após N ciclos consecutivos batendo) e cooldown_minutes (não
    reabre logo após resolver) - a mesma dedupe_key de um candidato que NÃO aparece mais neste
    ciclo tem seu contador de confirmação zerado (não é "consecutivo" se sumiu no meio)."""
    accepted: list[MonitorDetection] = []
    for detection in candidates:
        if _in_cooldown(db, detection.dedupe_key, rule.cooldown_minutes):
            continue
        hits = _confirm_hits(db, rule.key, detection.dedupe_key, rule.confirm_cycles)
        if hits >= max(rule.confirm_cycles, 1):
            accepted.append(detection)
    return accepted


# --- OS_CONCENTRATION_AREA / OS_CONCENTRATION_LINEAR --------------------------------------------


def _run_os_concentration_rule(db: Session, rule: IntelligenceAlertRule) -> list[MonitorDetection]:
    params = rule.params_json
    scope = rule.scope_json
    window_minutes = int(params.get("window_minutes", 60))
    min_count = int(params.get("min_count", 5))
    radius_meters = float(params.get("radius_meters", 300 if rule.rule_type == "OS_CONCENTRATION_AREA" else 800))
    historical_comparison = bool(params.get("historical_comparison", False))
    multiplier = float(params.get("min_multiplier_over_average", 1.5))
    baseline_days = int(params.get("baseline_days", 14))

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=window_minutes)
    conditions = _scope_conditions(scope) + [
        OperationOrder.opened_at >= window_start,
        OperationOrder.latitude.is_not(None),
        OperationOrder.longitude.is_not(None),
    ]
    # Objeto completo (não só colunas soltas) porque `service_address` é uma property calculada
    # em cima de `raw_payload` (ver operations/schemas.py::_service_address_from_payload) - é a
    # mesma fonte de endereço já usada no restante do app, não um campo novo.
    orders = list(db.scalars(select(OperationOrder).where(*conditions)))
    points = [
        _OrderPoint(
            order_id=order.id,
            order_code=order.order_code,
            address=_service_address_from_payload(order.raw_payload),
            neighborhood=order.neighborhood,
            latitude=order.latitude,
            longitude=order.longitude,
            regional=order.regional,
            city=order.city,
            os_subject=order.os_subject,
        )
        for order in orders
    ]

    groups = _cluster_points(points, radius_meters=radius_meters, min_samples=min_count)
    detections: list[MonitorDetection] = []
    for group in groups:
        if len(group) < min_count:
            continue
        center_lat = sum(p.latitude for p in group) / len(group)
        center_lng = sum(p.longitude for p in group) / len(group)
        regional = group[0].regional
        lat_key, lng_key = round(center_lat, 3), round(center_lng, 3)
        dedupe_key = f"rule:{rule.key}:{regional or 'sem_regional'}:{lat_key}:{lng_key}"

        confidence = 0.6
        warnings: list[dict] = []
        if historical_comparison:
            # Achado real: comparar o tamanho do CLUSTER (uma área de `radius_meters`) contra o
            # volume histórico de TODA a regional é uma comparação incorreta (regional grande tem
            # volume alto mesmo sem nenhuma concentração real, o que nunca dispararia o gate) -
            # reaproveita `ops_queries.geo_radius_condition` (mesmo raio, mesmo centro do cluster)
            # para comparar o cluster com o histórico DA MESMA área, não da regional inteira.
            def _area_conditions(_scope=scope, _lat=center_lat, _lng=center_lng, _radius_km=radius_meters / 1000.0):
                base = _scope_conditions(_scope)
                base.append(ops_queries.geo_radius_condition(_lat, _lng, _radius_km))
                return base

            def _baseline_conditions(window_start_h: datetime, window_end_h: datetime):
                return _area_conditions() + [OperationOrder.opened_at >= window_start_h, OperationOrder.opened_at < window_end_h]

            days_available = _days_of_history_available(db, scope_conditions=_area_conditions(), now=now)
            average = _historical_average_count(db, conditions_builder=_baseline_conditions, window_minutes=window_minutes, baseline_days=baseline_days, now=now)
            if days_available < MIN_BASELINE_SAMPLES:
                warnings.append({"code": "BASELINE_INSUFFICIENT_SAMPLE", "days_available": days_available})
            elif average > 0 and len(group) < average * multiplier:
                # amostra suficiente e o volume NÃO supera o baseline configurado - não é anomalia.
                continue
            else:
                confidence = 0.85

        detections.append(
            MonitorDetection(
                dedupe_key=dedupe_key,
                kind="ALERT",
                alert_type=rule.rule_type,
                severity=rule.severity,
                title=f"{rule.name}{f' - {regional}' if regional else ''}",
                summary=(
                    f"{len(group)} O.S. concentradas em um raio de {radius_meters:.0f}m nos últimos {window_minutes} minutos"
                    + (f", assunto predominante {group[0].os_subject}" if group[0].os_subject else "")
                    + "."
                ),
                regional=regional,
                city=group[0].city,
                scope={"regional": regional, "center_latitude": center_lat, "center_longitude": center_lng, "rule_key": rule.key},
                recommended_action="validar causa comum na área antes de despachar equipe individualmente",
                evidence={
                    "os_count": len(group),
                    "radius_meters": radius_meters,
                    "window_minutes": window_minutes,
                    # Centro do agrupamento (média das coordenadas do grupo) - pedido explícito para
                    # localizar o alerta sem abrir o detalhe.
                    "center_latitude": round(center_lat, 6),
                    "center_longitude": round(center_lng, 6),
                    # Amostra identificável (código real da O.S. + endereço/bairro/coordenadas, não o
                    # id interno do banco) - pedido explícito: dá pra saber QUAIS O.S./endereços
                    # formam o agrupamento sem precisar consultar o banco na mão.
                    "os_sample": [
                        {
                            "order_code": p.order_code,
                            "address": p.address,
                            "neighborhood": p.neighborhood,
                            "latitude": round(p.latitude, 6),
                            "longitude": round(p.longitude, 6),
                        }
                        for p in group[:10]
                    ],
                },
                confidence=confidence,
                warnings=warnings,
            )
        )
    return detections


# --- OS_OPENING_ABOVE_AVERAGE / OS_GROWTH_ANOMALY -----------------------------------------------

_GROUP_BY_COLUMNS = {"regional": OperationOrder.regional, "city": OperationOrder.city, "os_subject": OperationOrder.os_subject}


def _run_opening_above_average_rule(db: Session, rule: IntelligenceAlertRule) -> list[MonitorDetection]:
    params = rule.params_json
    scope = rule.scope_json
    window_minutes = int(params.get("window_minutes", 60))
    min_count = int(params.get("min_count", 10))
    multiplier = float(params.get("min_multiplier_over_average", 1.5))
    baseline_days = int(params.get("baseline_days", 14))
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=window_minutes)

    detections: list[MonitorDetection] = []

    def _make_detection(*, count: int, dimension_label: str | None, dimension_value: str | None, average: float, days_available: int) -> MonitorDetection:
        warnings: list[dict] = []
        confidence = 0.6
        if days_available < MIN_BASELINE_SAMPLES:
            warnings.append({"code": "BASELINE_INSUFFICIENT_SAMPLE", "days_available": days_available})
        else:
            confidence = 0.85
        label = f" - {dimension_value}" if dimension_value else ""
        dedupe_key = f"rule:{rule.key}:{dimension_value or 'geral'}"
        ratio = round(count / average, 2) if average > 0 else None
        return MonitorDetection(
            dedupe_key=dedupe_key,
            kind="ALERT",
            alert_type=rule.rule_type,
            severity=rule.severity,
            title=f"{rule.name}{label}",
            summary=(
                f"{count} O.S. abertas nos últimos {window_minutes} minutos"
                + (f" vs média histórica de {average:.1f} ({ratio}x)" if average else "")
                + f"{' em ' + dimension_label if dimension_label else ''}."
            ),
            regional=dimension_value if dimension_label == "regional" else None,
            city=dimension_value if dimension_label == "city" else None,
            scope={dimension_label: dimension_value, "rule_key": rule.key} if dimension_label else {"rule_key": rule.key},
            recommended_action="avaliar reforço de equipe ou investigar causa comum",
            evidence={"count": count, "baseline_average": average, "baseline_days_available": days_available, "window_minutes": window_minutes},
            confidence=confidence,
            warnings=warnings,
        )

    if rule.rule_type == "OS_GROWTH_ANOMALY":
        group_by = params.get("group_by", "regional")
        column = _GROUP_BY_COLUMNS[group_by]
        conditions = _scope_conditions(scope) + [OperationOrder.opened_at >= window_start, OperationOrder.opened_at < now, column.is_not(None)]
        rows = db.execute(select(column, func.count(OperationOrder.id)).where(*conditions).group_by(column)).all()
        for value, count in rows:
            if count < min_count:
                continue

            def _dimension_scope(_value=value, _column=column):
                return _scope_conditions(scope) + [_column == _value]

            def _baseline_conditions(window_start_h: datetime, window_end_h: datetime, _value=value, _column=column):
                return _dimension_scope(_value, _column) + [OperationOrder.opened_at >= window_start_h, OperationOrder.opened_at < window_end_h]

            days_available = _days_of_history_available(db, scope_conditions=_dimension_scope(), now=now)
            average = _historical_average_count(db, conditions_builder=_baseline_conditions, window_minutes=window_minutes, baseline_days=baseline_days, now=now)
            if days_available >= MIN_BASELINE_SAMPLES and average > 0 and count < average * multiplier:
                continue
            detections.append(_make_detection(count=count, dimension_label=group_by, dimension_value=str(value), average=average, days_available=days_available))
    else:
        conditions = _scope_conditions(scope) + [OperationOrder.opened_at >= window_start, OperationOrder.opened_at < now]
        count = db.scalar(select(func.count(OperationOrder.id)).where(*conditions)) or 0
        if count >= min_count:
            def _baseline_conditions(window_start_h: datetime, window_end_h: datetime):
                return _scope_conditions(scope) + [OperationOrder.opened_at >= window_start_h, OperationOrder.opened_at < window_end_h]

            days_available = _days_of_history_available(db, scope_conditions=_scope_conditions(scope), now=now)
            average = _historical_average_count(db, conditions_builder=_baseline_conditions, window_minutes=window_minutes, baseline_days=baseline_days, now=now)
            if not (days_available >= MIN_BASELINE_SAMPLES and average > 0 and count < average * multiplier):
                detections.append(_make_detection(count=count, dimension_label=None, dimension_value=None, average=average, days_available=days_available))
    return detections


# --- BACKLOG_THRESHOLD / SLA_THRESHOLD -----------------------------------------------------------


def _run_backlog_threshold_rule(db: Session, rule: IntelligenceAlertRule) -> list[MonitorDetection]:
    params = rule.params_json
    scope = rule.scope_json
    threshold = float(params.get("threshold_value", 500))
    conditions = _scope_conditions(scope) + [OperationOrder.is_closed.is_(False)]
    total = db.scalar(select(func.count(OperationOrder.id)).where(*conditions)) or 0
    if total < threshold:
        return []
    regional = (scope.get("regionals") or [None])[0]
    dedupe_key = f"rule:{rule.key}:{regional or 'geral'}"
    return [
        MonitorDetection(
            dedupe_key=dedupe_key,
            kind="ALERT",
            alert_type=rule.rule_type,
            severity=rule.severity,
            title=f"{rule.name}",
            summary=f"Backlog em {total} O.S. abertas, acima do limite configurado de {threshold:.0f}.",
            regional=regional,
            scope={"rule_key": rule.key},
            recommended_action="revisar priorização de fechamento de O.S. em aberto",
            evidence={"backlog_total": total, "threshold": threshold},
            confidence=0.9,
        )
    ]


def _run_sla_threshold_rule(db: Session, rule: IntelligenceAlertRule) -> list[MonitorDetection]:
    params = rule.params_json
    scope = rule.scope_json
    threshold = float(params.get("threshold_value", 80.0))
    window_days = int(params.get("window_days", 7))
    today = datetime.now(OPERATIONS_TIMEZONE).date()
    date_from = today - timedelta(days=window_days)
    filters = {"sectors": scope.get("sectors") or list(PRIMARY_SECTOR_NAMES)}
    for field in ("regionals", "cities", "os_subjects", "team_models"):
        if scope.get(field):
            filters[field] = scope[field]
    overview = ops_queries.overview(db, date_from, today, system_user(), **_to_operations_rest_filters(filters))
    sla_rate = overview.get("sla_rate")
    if sla_rate is None or sla_rate >= threshold:
        return []
    regional = (scope.get("regionals") or [None])[0]
    dedupe_key = f"rule:{rule.key}:{regional or 'geral'}"
    return [
        MonitorDetection(
            dedupe_key=dedupe_key,
            kind="ALERT",
            alert_type=rule.rule_type,
            severity=rule.severity,
            title=f"{rule.name}",
            summary=f"SLA em {sla_rate}% nos últimos {window_days} dias, abaixo do limite configurado de {threshold:.0f}%.",
            regional=regional,
            scope={"rule_key": rule.key},
            recommended_action="priorizar O.S. ainda salváveis dentro do SLA",
            evidence={"sla_rate": sla_rate, "threshold": threshold, "window_days": window_days},
            confidence=0.9,
        )
    ]


# --- COLLECTIVE_OUTAGE (variante configurável) -----------------------------------------------


def _run_collective_outage_rule(db: Session, rule: IntelligenceAlertRule) -> list[MonitorDetection]:
    params = rule.params_json
    scope = rule.scope_json
    window_minutes = int(params.get("window_minutes", 90))
    min_count = int(params.get("min_count", 3))
    radius_meters = float(params.get("radius_meters", 300))
    regionals_filter = set(scope.get("regionals") or [])

    analysis = login_incident_analysis(db, window_minutes=window_minutes, regionals=None, cluster_radius_meters=radius_meters, cluster_min_size=min_count)
    detections: list[MonitorDetection] = []
    for cluster in analysis.get("geo_clusters", []):
        logins = cluster.get("logins", [])
        regional = None
        if logins:
            regional = db.scalar(select(OperationLoginCurrentStatus.regional).where(OperationLoginCurrentStatus.login == logins[0]))
        if regionals_filter and regional not in regionals_filter:
            continue
        lat_key, lng_key = round(cluster["center_latitude"], 3), round(cluster["center_longitude"], 3)
        dedupe_key = f"rule:{rule.key}:{regional or 'sem_regional'}:{lat_key}:{lng_key}"
        detections.append(
            MonitorDetection(
                dedupe_key=dedupe_key,
                kind="INCIDENT",
                alert_type=rule.rule_type,
                severity=rule.severity,
                title=f"{rule.name}{f' - {regional}' if regional else ''}",
                summary=f"{cluster['size']} logins offline concentrados em um raio de {cluster['radius_meters']:.0f}m nos últimos {window_minutes} minutos.",
                regional=regional,
                scope={"rule_key": rule.key, "regional": regional},
                recommended_action="evitar despacho individual até validação da equipe de infraestrutura",
                evidence={"cluster_size": cluster["size"], "radius_meters": cluster["radius_meters"]},
                confidence=0.8,
            )
        )
    return detections


# --- MONITOR_UNHEALTHY (variante configurável) -----------------------------------------------


def _run_monitor_unhealthy_rule(db: Session, rule: IntelligenceAlertRule) -> list[MonitorDetection]:
    params = rule.params_json
    target_key = params.get("target_monitor_key")
    max_failures = int(params.get("max_consecutive_failures", 2))
    if not target_key:
        return []
    runs = recent_runs(db, target_key, limit=20)
    failures = count_consecutive_failures(runs)
    if failures < max_failures:
        return []
    dedupe_key = f"rule:{rule.key}:{target_key}"
    return [
        MonitorDetection(
            dedupe_key=dedupe_key,
            kind="ALERT",
            alert_type=rule.rule_type,
            severity=rule.severity,
            title=f"{rule.name} - {target_key}",
            summary=f"Monitor '{target_key}' com {failures} falhas consecutivas (limite configurado: {max_failures}).",
            scope={"rule_key": rule.key, "target_monitor_key": target_key},
            recommended_action="verificar logs do monitor e causa das falhas",
            evidence={"consecutive_failures": failures, "threshold": max_failures},
            confidence=0.95,
        )
    ]


_RULE_RUNNERS = {
    "OS_CONCENTRATION_AREA": _run_os_concentration_rule,
    "OS_CONCENTRATION_LINEAR": _run_os_concentration_rule,
    "OS_OPENING_ABOVE_AVERAGE": _run_opening_above_average_rule,
    "OS_GROWTH_ANOMALY": _run_opening_above_average_rule,
    "BACKLOG_THRESHOLD": _run_backlog_threshold_rule,
    "SLA_THRESHOLD": _run_sla_threshold_rule,
    "COLLECTIVE_OUTAGE": _run_collective_outage_rule,
    "MONITOR_UNHEALTHY": _run_monitor_unhealthy_rule,
}


def run_alert_rules_monitor(db: Session) -> MonitorRunResult:
    rules = list_alert_rules(db, active=True)
    all_detections: list[MonitorDetection] = []
    evaluated_dedupe_keys: set[str] = set()
    stats = {"rules_evaluated": len(rules), "candidates_before_confirm": 0}

    for rule in rules:
        runner = _RULE_RUNNERS.get(rule.rule_type)
        if runner is None:
            continue
        try:
            candidates = runner(db, rule)
        except Exception:
            continue
        stats["candidates_before_confirm"] += len(candidates)
        confirmed = _gate_by_confirm_and_cooldown(db, rule, candidates)
        all_detections.extend(confirmed)
        for candidate in candidates:
            evaluated_dedupe_keys.add(f"{rule.key}:{candidate.dedupe_key}")

    return MonitorRunResult(detections=all_detections, stats=stats)
