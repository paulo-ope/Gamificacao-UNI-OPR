"""Cockpit (F2): payload único da TV + publicação genérica de conteúdo.

Reaproveita funções JÁ EXISTENTES de `operations`/`ai` (nenhuma consulta SQL nova contra
`operations_orders`): `queries.overview`, `services.overview_trends`, `queries.collaborator_sla`,
`queries.data_freshness` e `ai.queries.backlog_aging`. O cockpit só agrega o que essas funções já
calculam - não recalcula SLA, backlog ou produção do zero.

Usa o `system_user()` de `scope.py` (mesmo usado pelos monitores F0/F1) para consultar sem
recorte de gestor regional - o recorte de verdade é o `scope` do PROFILE, aplicado aqui."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from statistics import mean
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.ai import queries as ai_queries
from app.modules.ai_governance.response_meta import build_meta
from app.modules.operations import queries as ops_queries
from app.modules.operations import services as ops_services
from app.modules.operations.period import OPERATIONS_TIMEZONE
from app.modules.operations.scope import PRIMARY_SECTOR_NAMES

from . import scheduler as intelligence_scheduler
from .alerts import ACTIVE_STATUSES
from .models import IntelligenceAlert, IntelligenceCockpitContent, IntelligenceDashboardProfile
from .registry import list_monitors
from .scope import system_user

# --- catálogos fechados (validação de entrada, não widget engine) -----------------------------

WIDGET_CATALOG = (
    "overall_status",
    "active_alerts",
    "active_incidents",
    "production",
    "backlog",
    "sla",
    "monitor_health",
    "cockpit_content",
    "ai_insights",
)

# F5 - filtros que cada widget aceita, em nomes canônicos do FilterContractV1 (nunca vocabulário
# paralelo). Um widget só pode RESTRINGIR o scope do profile, nunca ampliar (ver
# _restrict_filter_values) - "regionals"/"cities"/"sectors"/"os_subjects"/"team_models"/
# "responsibles" recortam a população consultada; "severity"/"status"/"content_type" filtram a
# lista já recortada (alertas/incidentes/conteúdo não têm "scope" próprio de operations, então não
# há o que restringir além do que o profile já aplicou por regional).
WIDGET_ALLOWED_FILTERS: dict[str, frozenset[str]] = {
    "overall_status": frozenset(),
    "monitor_health": frozenset(),
    "production": frozenset({"regionals", "cities", "sectors", "os_subjects", "team_models"}),
    "backlog": frozenset({"regionals", "cities", "sectors", "os_subjects", "team_models", "responsibles"}),
    "sla": frozenset({"regionals", "cities", "sectors", "os_subjects", "team_models"}),
    "active_alerts": frozenset({"regionals", "severity", "status"}),
    "active_incidents": frozenset({"regionals", "severity", "status"}),
    "cockpit_content": frozenset({"content_type", "severity"}),
    "ai_insights": frozenset({"content_type", "severity"}),
}

# Campos de "scope de operations" (population-level) vs campos de "filtro de lista" (pós-consulta,
# sobre algo que não vem de operations_orders) - determina qual mecanismo de restrição usar.
_OPERATIONS_SCOPE_FIELDS = frozenset({"regionals", "cities", "sectors", "os_subjects", "team_models", "responsibles"})

CONTENT_TYPES = (
    "AI_INSIGHT",
    "MANUAL_MESSAGE",
    "ANNOUNCEMENT",
    "OPERATIONAL_PRIORITY",
    "INCIDENT_UPDATE",
    "MAINTENANCE_NOTICE",
    "INFO",
)
CONTENT_SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL", "INFO")
CONTENT_SOURCE_TYPES = ("SYSTEM", "MONITOR", "AI", "USER", "MCP")
CONTENT_STATUSES = ("ACTIVE", "EXPIRED", "DISMISSED")

MAX_TITLE_LENGTH = 200
MAX_BODY_LENGTH = 4000


class ProfileValidationError(ValueError):
    """Erro de validação de profile/widget - vira 422 no REST (admin de profiles)."""


def normalize_widget_entries(widgets_json: list) -> list[dict]:
    """Aceita tanto o formato legado (`["overall_status", "backlog", ...]`) quanto o formato com
    filtro (`[{"key": "backlog", "filters": {"team_models": [...]}}, ...]`) e sempre devolve a
    forma normalizada - a ORDEM da lista é a prioridade/ordem de exibição do widget (sem campo
    separado; "subir/descer" na Administração só reordena a lista)."""
    normalized = []
    for entry in widgets_json or []:
        if isinstance(entry, str):
            normalized.append({"key": entry, "filters": {}})
        elif isinstance(entry, dict) and "key" in entry:
            normalized.append({"key": entry["key"], "filters": dict(entry.get("filters") or {})})
    return normalized


def validate_widget_entries(widgets_json: list) -> list[dict]:
    """Validação de escrita (Administração cria/edita um profile): widget precisa existir no
    catálogo e cada filtro dele precisa estar na lista permitida daquele widget - nunca aceita
    filtro ignorado em silêncio (bloqueia aqui, não só avisa na leitura)."""
    normalized = normalize_widget_entries(widgets_json)
    seen_keys = set()
    for entry in normalized:
        key = entry["key"]
        if key not in WIDGET_CATALOG:
            raise ProfileValidationError(f"widget inválido: {key!r}. Use um de {WIDGET_CATALOG}.")
        if key in seen_keys:
            raise ProfileValidationError(f"widget duplicado: {key!r}.")
        seen_keys.add(key)
        allowed = WIDGET_ALLOWED_FILTERS.get(key, frozenset())
        for field in entry["filters"]:
            if field not in allowed:
                raise ProfileValidationError(
                    f"filtro {field!r} não é suportado pelo widget {key!r}. Filtros aceitos: {sorted(allowed) or 'nenhum'}."
                )
    return normalized


def _restrict_filter_values(base: list[str], override: list[str] | None) -> tuple[list[str], bool]:
    """Combina o valor BASE (scope do profile) com um filtro de WIDGET - o widget só pode
    RESTRINGIR, nunca ampliar. Retorna (valores_efetivos, houve_conflito).

    - base vazio (profile global/sem recorte naquele campo) + widget define -&gt; usa o do widget
      (é uma restrição válida de "tudo" para "isso").
    - base preenchido + widget define um valor DENTRO do base -&gt; interseção (mais restrito ainda).
    - base preenchido + widget define algo TOTALMENTE fora do base -&gt; conflito: mantém o base
      (nunca amplia, nunca zera pra "sem filtro"), e quem chamou registra o warning."""
    if not override:
        return base, False
    if not base:
        return list(override), False
    intersection = [v for v in base if v in override]
    if not intersection:
        return list(base), True
    return intersection, False


def _to_operations_rest_filters(filters: dict[str, Any]) -> dict[str, Any]:
    """`operations.queries`/`operations.services` (usadas por `overview`/`overview_trends`/
    `collaborator_sla`) ainda falam o vocabulário legado do REST - `"subjects"`, não `"os_subjects"`
    canônico (achado documentado em docs/proposta-filter-contract-v1.md: só `ai/queries.py` foi
    migrado ao FilterContractV1, o REST de `operations` nunca foi). Sem esta tradução, um filtro
    `os_subjects` do widget seria silenciosamente IGNORADO por essas duas funções (`FILTER_COLUMNS`
    delas nem reconhece a chave) - exatamente o anti-padrão que a Fase 1 de confiabilidade corrigiu
    em outros endpoints. O cockpit só fala canônico pra fora; a tradução fica só aqui, isolada."""
    translated = dict(filters)
    if "os_subjects" in translated:
        translated["subjects"] = translated.pop("os_subjects")
    return translated


def _widget_entry(widget_entries: list[dict], key: str) -> dict:
    return next((entry for entry in widget_entries if entry["key"] == key), {"key": key, "filters": {}})


def _effective_operations_filters(
    base_filters: dict[str, Any],
    widget_filters: dict[str, Any],
    widget_key: str,
    warnings: list[dict],
) -> dict[str, Any]:
    """Mescla o scope base (profile) com o filtro do widget para as consultas de `operations`/
    `ai` - só usado pelos widgets de "população" (production/backlog/sla). Filtro não suportado
    pelo widget vira warning estruturado e é descartado (nunca aplicado em silêncio)."""
    allowed = WIDGET_ALLOWED_FILTERS.get(widget_key, frozenset())
    effective = dict(base_filters)
    for field, value in widget_filters.items():
        if field not in allowed or field not in _OPERATIONS_SCOPE_FIELDS:
            warnings.append({"code": "FILTER_NOT_SUPPORTED_BY_WIDGET", "widget": widget_key, "field": field})
            continue
        base_value = base_filters.get(field) or []
        restricted, conflict = _restrict_filter_values(list(base_value), value)
        effective[field] = restricted
        if conflict:
            warnings.append({"code": "WIDGET_FILTER_CONFLICTS_WITH_SCOPE", "widget": widget_key, "field": field})
    return effective


def _apply_list_post_filters(
    items: list[dict],
    widget_filters: dict[str, Any],
    widget_key: str,
    warnings: list[dict],
    *,
    regional_field: str = "regional",
) -> list[dict]:
    """Filtra uma lista JÁ recortada pelo scope do profile (alertas/incidentes/conteúdo) - estes
    não têm "scope de operations" próprio, então o filtro do widget é só um refinamento posterior
    da mesma lista (nunca busca dado novo, nunca amplia o que o profile já decidiu mostrar)."""
    allowed = WIDGET_ALLOWED_FILTERS.get(widget_key, frozenset())
    result = items
    for field, value in widget_filters.items():
        if field not in allowed:
            warnings.append({"code": "FILTER_NOT_SUPPORTED_BY_WIDGET", "widget": widget_key, "field": field})
            continue
        if not value:
            continue
        wanted = set(value) if isinstance(value, (list, tuple, set)) else {value}
        if field == "regionals":
            result = [item for item in result if item.get(regional_field) in wanted]
        elif field in ("severity", "status", "content_type"):
            result = [item for item in result if item.get(field) in wanted]
    return result

# Meta de SLA percentual - não existe constante equivalente em `operations` (achado da
# investigação: `sla_target_hours` é por O.S. individual, não um percentual agregado). Usa o
# mesmo corte visual já usado no frontend (`lib/operations-sla.ts::slaTone`, 80%/60%), agora
# centralizado aqui para o cockpit não espalhar o número de novo.
SLA_TARGET_PCT = 80.0
SLA_CRITICAL_PCT = 50.0

# Limiares do status geral - centralizados aqui, nunca espalhados no frontend.
BACKLOG_GT15D_CRITICAL = 50
BACKLOG_GT7D_ATTENTION = 30

# Quantas regionais distintas com incidente/alerta CRITICAL simultâneo caracterizam um problema
# sistêmico (não mais "um problema local") - usado só quando o PROFILE tem escopo global (ver
# compute_overall_status). Um profile regional (ex.: machadinho-operacional) não usa este número:
# para ele, qualquer incidente crítico na sua própria regional já é 100% do escopo que ele mostra.
MULTI_REGIONAL_CRITICAL_THRESHOLD = 2

_SEVERITY_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


class CockpitContentValidationError(ValueError):
    """Erro de validação de publicação de conteúdo - vira 422 no REST e ValueError na tool MCP."""


# --- dashboard profiles -------------------------------------------------------------------------


def get_profile(db: Session, key: str) -> IntelligenceDashboardProfile | None:
    return db.scalar(select(IntelligenceDashboardProfile).where(IntelligenceDashboardProfile.key == key))


_STANDARD_WIDGETS = [
    "overall_status",
    "active_alerts",
    "active_incidents",
    "production",
    "backlog",
    "sla",
    "cockpit_content",
    "monitor_health",
]

# Profile executivo: menos widgets de propósito (sem alertas/incidentes/saúde de monitor - isso é
# operacional, não executivo) e refresh mais espaçado - visão de tendência, não de operação minuto
# a minuto. Mesmo frontend, profile diferente decide o que aparece (widgets_json).
_EXECUTIVE_WIDGETS = ["overall_status", "production", "backlog", "sla", "cockpit_content"]

# Seed default dos profiles desta rodada (F3). Não é CRUD - só os 3 profiles pedidos nascem
# prontos; edição/criação de profile fica para uma fase futura de administração.
_DEFAULT_PROFILES: tuple[dict, ...] = (
    {
        "key": "uni-geral",
        "name": "UNI Geral",
        "purpose": "MATRIX_TV",
        "scope_json": {"regionals": []},
        "widgets_json": _STANDARD_WIDGETS,
        "refresh_seconds": 60,
    },
    {
        "key": "machadinho-operacional",
        "name": "Machadinho Operacional",
        "purpose": "REGIONAL_TV",
        "scope_json": {"regionals": ["UNI - MACHADINHO DOESTE"]},
        "widgets_json": _STANDARD_WIDGETS,
        "refresh_seconds": 45,
    },
    {
        "key": "executivo-uni",
        "name": "Executivo UNI",
        "purpose": "EXECUTIVE",
        "scope_json": {"regionals": []},
        "widgets_json": _EXECUTIVE_WIDGETS,
        "refresh_seconds": 120,
    },
)


def ensure_default_dashboard_profile(db: Session) -> None:
    """Seed idempotente dos profiles default (uni-geral, machadinho-operacional, executivo-uni) -
    mesmo padrão de `ensure_ai_governance_seed`: só insere o que ainda não existe por `key`, nunca
    sobrescreve configuração já feita pela Administração em um profile já existente."""
    for spec in _DEFAULT_PROFILES:
        if get_profile(db, spec["key"]) is not None:
            continue
        db.add(
            IntelligenceDashboardProfile(
                key=spec["key"],
                name=spec["name"],
                purpose=spec["purpose"],
                scope_json=spec["scope_json"],
                widgets_json=spec["widgets_json"],
                display_config_json={},
                refresh_seconds=spec["refresh_seconds"],
                active=True,
            )
        )
    db.commit()


# --- payload do cockpit --------------------------------------------------------------------------


def _scope_regionals(profile: IntelligenceDashboardProfile) -> list[str]:
    return list((profile.scope_json or {}).get("regionals") or [])


def _active_alerts_query(db: Session, regionals: list[str]):
    conditions = [IntelligenceAlert.status.in_(ACTIVE_STATUSES)]
    if regionals:
        conditions.append((IntelligenceAlert.regional.in_(regionals)) | (IntelligenceAlert.regional.is_(None)))
    return list(db.scalars(select(IntelligenceAlert).where(*conditions).order_by(IntelligenceAlert.last_seen_at.desc())))


def _as_aware_utc(value: datetime) -> datetime:
    """SQLite não preserva tzinfo no round-trip (achado real, mesmo padrão já visto em
    scheduler.py::mark_interrupted_runs_on_startup) - normaliza antes de fazer aritmética de data."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _alert_to_summary(alert: IntelligenceAlert) -> dict:
    age_seconds = (datetime.now(timezone.utc) - _as_aware_utc(alert.first_detected_at)).total_seconds()
    return {
        "id": alert.id,
        "kind": alert.kind,
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "status": alert.status,
        "title": alert.title,
        "summary": alert.summary,
        "recommended_action": alert.recommended_action,
        "regional": alert.regional,
        "confidence": alert.confidence,
        "coverage": alert.coverage_json,
        "warnings": alert.warnings_json,
        "first_detected_at": alert.first_detected_at,
        "last_seen_at": alert.last_seen_at,
        "age_seconds": round(age_seconds),
        "source_type": alert.source_type,
    }


def _content_query(db: Session, profile: IntelligenceDashboardProfile, scope_regionals: list[str]) -> list[IntelligenceCockpitContent]:
    now = datetime.now(timezone.utc)
    rows = list(
        db.scalars(
            select(IntelligenceCockpitContent)
            .where(
                IntelligenceCockpitContent.status == "ACTIVE",
                (IntelligenceCockpitContent.profile_key == profile.key) | (IntelligenceCockpitContent.profile_key.is_(None)),
            )
            .order_by(IntelligenceCockpitContent.created_at.desc())
        )
    )
    filtered = []
    for row in rows:
        # conteúdo expirado não aparece na TV, mesmo que ninguém tenha rodado a expiração em lote ainda
        if row.valid_until is not None and row.valid_until <= now:
            continue
        # achado F3: conteúdo global (profile_key=None) com um `regional` próprio não pode
        # "vazar" para um profile de escopo regional diferente - ex.: um AI_INSIGHT publicado
        # sem profile_key mas com regional="UNI - JI PARANA" não deve aparecer em
        # machadinho-operacional. Profile de escopo global (scope_regionals vazio) continua vendo
        # tudo, exatamente como um alerta/incidente regional também aparece na visão UNI inteira.
        if scope_regionals and row.regional and row.regional not in scope_regionals:
            continue
        filtered.append(row)
    return filtered


def _content_to_summary(content: IntelligenceCockpitContent) -> dict:
    return {
        "id": content.id,
        "content_type": content.content_type,
        "profile_key": content.profile_key,
        "regional": content.regional,
        "severity": content.severity,
        "title": content.title,
        "body": content.body,
        "evidence": content.evidence_json,
        "confidence": content.confidence,
        "source_type": content.source_type,
        "source_key": content.source_key,
        "author_user_id": content.author_user_id,
        "valid_from": content.valid_from,
        "valid_until": content.valid_until,
        "created_at": content.created_at,
    }


def _monitor_health_summary(db: Session) -> list[dict]:
    rows = []
    for monitor in list_monitors():
        runs = intelligence_scheduler.recent_runs(db, monitor.key, limit=20)
        last_run = runs[0] if runs else None
        success_run = intelligence_scheduler.last_success_run(db, monitor.key)
        rows.append(
            {
                "monitor_key": monitor.key,
                "name": monitor.name,
                "enabled": intelligence_scheduler.get_monitor_enabled(db, monitor),
                "last_run_at": last_run.started_at if last_run else None,
                "last_run_status": last_run.status if last_run else None,
                "last_success_at": success_run.started_at if success_run else None,
                "consecutive_failures": intelligence_scheduler.count_consecutive_failures(runs),
            }
        )
    return rows


# F5 - os 3 setores canônicos ("Suporte Externo", "Suporte Externo Rádio", "Suporte Externo
# Fibra") compartilham o prefixo "Suporte Externo" - `backlog_history` só aceita um filtro de
# TEXTO sobre `sector` (`sector_filter`, não uma lista como as outras funções), então
# "starts_with" é o jeito honesto de escopar pro mesmo recorte operacional sem inventar um
# mecanismo novo de filtro só pra este gráfico.
_BACKLOG_HISTORY_SECTOR_FILTER = {"operator": "starts_with", "value": "Suporte Externo"}


def _backlog_history_series(db: Session, user, *, date_from: date, date_to: date, regionals: list[str]) -> list[dict]:
    """Série diária de backlog (evolução) - lida do snapshot já existente
    (`operations_backlog_snapshots`/`ai.queries.backlog_history`), nenhuma consulta nova. Só tem
    dado a partir do dia em que o job de captura entrou em produção (sem retroatividade) - dias
    sem snapshot simplesmente não aparecem na série, não são preenchidos com zero."""
    try:
        rows = ai_queries.backlog_history(
            db, user, metric="backlog", date_from=date_from, date_to=date_to,
            group_by="regional", sector_filter=_BACKLOG_HISTORY_SECTOR_FILTER,
        )
    except Exception:
        return []
    if regionals:
        rows = [row for row in rows if row.get("group") in regionals]
    daily: dict[date, int] = {}
    for row in rows:
        daily[row["snapshot_date"]] = daily.get(row["snapshot_date"], 0) + row["quantity"]
    return [{"date": day, "quantity": quantity} for day, quantity in sorted(daily.items())]


def _uni_wide_critical_incident(incidents: list[dict]) -> bool:
    """Um incidente CRITICAL é "de fato UNI-wide" quando não tem regional (achado genuinamente
    global, ex.: MONITOR_UNHEALTHY) OU quando atinge múltiplas regionais ao mesmo tempo
    (indício de problema sistêmico, não um rompimento físico local isolado)."""
    critical = [item for item in incidents if item["severity"] == "CRITICAL"]
    if any(item["regional"] is None for item in critical):
        return True
    affected_regionals = {item["regional"] for item in critical if item["regional"]}
    return len(affected_regionals) >= MULTI_REGIONAL_CRITICAL_THRESHOLD


def compute_overall_status(
    *,
    alerts: list[dict],
    incidents: list[dict],
    backlog_gt_15d: int,
    backlog_gt_7d: int,
    sla_current: float | None,
    any_monitor_unhealthy: bool,
    is_global_scope: bool,
) -> dict:
    """Regra determinística e centralizada (nunca IA, nunca hardcoded no frontend) - ver item
    "Status geral" do processo aprovado. Combina alertas ativos, incidentes, severidade,
    monitor_unhealthy, SLA e backlog.

    Escopo importa (achado F3): um profile de escopo GLOBAL (ex.: uni-geral, `regionals: []`) não
    pode virar CRITICAL só porque UMA regional específica tem um incidente crítico local - isso
    inflaria toda leitura da UNI por um problema pontual de uma cidade. Um profile de escopo
    REGIONAL (ex.: machadinho-operacional) já enxerga só a própria regional, então qualquer
    incidente crítico ali É, por definição, 100% do escopo dele - vira CRITICAL normalmente."""
    max_incident_severity = max((item["severity"] for item in incidents), key=lambda sev: _SEVERITY_RANK.get(sev, -1), default=None)
    max_alert_severity = max((item["severity"] for item in alerts), key=lambda sev: _SEVERITY_RANK.get(sev, -1), default=None)
    has_critical_incident = max_incident_severity == "CRITICAL"
    uni_wide_critical = _uni_wide_critical_incident(incidents) if has_critical_incident else False

    if has_critical_incident and (not is_global_scope or uni_wide_critical):
        return {"status": "CRITICAL", "reason": "Incidente crítico ativo no escopo desta tela."}
    if sla_current is not None and sla_current < SLA_CRITICAL_PCT:
        return {"status": "CRITICAL", "reason": f"SLA em {sla_current}%, muito abaixo da meta ({SLA_TARGET_PCT}%)."}
    if backlog_gt_15d > BACKLOG_GT15D_CRITICAL:
        return {"status": "CRITICAL", "reason": f"{backlog_gt_15d} O.S. no backlog há mais de 15 dias."}

    if has_critical_incident:
        # CRITICAL real, mas local e isolado (só 1 regional) dentro de um profile de escopo
        # global - a UNI inteira não está crítica, mas o assunto pesa mais que "atenção".
        return {"status": "RISK", "reason": "Incidente crítico localizado em uma regional específica."}
    if max_incident_severity == "HIGH" or max_alert_severity == "CRITICAL":
        return {"status": "RISK", "reason": "Alerta ou incidente de alta severidade ativo."}
    if any_monitor_unhealthy:
        return {"status": "RISK", "reason": "Um ou mais monitores de inteligência não estão saudáveis."}
    if sla_current is not None and sla_current < SLA_TARGET_PCT:
        return {"status": "RISK", "reason": f"SLA em {sla_current}%, abaixo da meta de {SLA_TARGET_PCT}%."}

    if alerts or incidents:
        return {"status": "ATTENTION", "reason": "Há alertas ativos que merecem atenção."}
    if backlog_gt_7d > BACKLOG_GT7D_ATTENTION:
        return {"status": "ATTENTION", "reason": f"{backlog_gt_7d} O.S. no backlog há mais de 7 dias."}

    return {"status": "NORMAL", "reason": "Operação dentro do esperado."}


def _display_mode(overall_status: str, incidents: list[dict]) -> str:
    if any(item["severity"] == "CRITICAL" for item in incidents):
        return "INCIDENT"
    if overall_status in ("ATTENTION", "RISK", "CRITICAL"):
        return "ATTENTION"
    return "NORMAL"


def build_cockpit_payload(db: Session, profile: IntelligenceDashboardProfile) -> dict:
    regionals = _scope_regionals(profile)
    # Achado real (F3): sem filtro de setor, overview/backlog_aging/collaborator_sla contam TODA
    # operations_orders - inclui Cobrança, Comercial, Estoque, Financeiro etc, que não são backlog
    # operacional de campo. O restante da Operação Analítica já teria esse problema se não fosse o
    # próprio frontend aplicar por padrão os "3 setores principais" (ver
    # frontend/app/operacao/page.tsx::DEFAULT_PRIORITY_SECTORS, espelho de
    # operations/scope.py::PRIMARY_SECTOR_NAMES). O cockpit precisa do mesmo default - profile pode
    # sobrescrever via scope_json["sectors"], mas nasce sempre escopado por padrão.
    sectors = list((profile.scope_json or {}).get("sectors") or PRIMARY_SECTOR_NAMES)
    base_filters: dict[str, Any] = {"sectors": sectors}
    if regionals:
        base_filters["regionals"] = regionals
    user = system_user()
    today = datetime.now(OPERATIONS_TIMEZONE).date()
    week_ago = today - timedelta(days=6)

    warnings: list[dict] = []

    # F5 - regra de filtros: scope do profile = filtro base de toda a TV; widget.filters só pode
    # RESTRINGIR esse scope (nunca ampliar) - ver _effective_operations_filters/
    # _restrict_filter_values. Cada widget de "população" (production/backlog/sla) pode ter seu
    # próprio recorte adicional, então cada um calcula seu PRÓPRIO filtro efetivo em vez de
    # compartilhar um único `filters` fixo.
    widget_entries = normalize_widget_entries(profile.widgets_json)
    production_filters = _effective_operations_filters(base_filters, _widget_entry(widget_entries, "production")["filters"], "production", warnings)
    backlog_filters = _effective_operations_filters(base_filters, _widget_entry(widget_entries, "backlog")["filters"], "backlog", warnings)
    sla_filters = _effective_operations_filters(base_filters, _widget_entry(widget_entries, "sla")["filters"], "sla", warnings)

    overview_today = ops_queries.overview(db, today, today, user, **_to_operations_rest_filters(production_filters))
    trend = ops_services.overview_trends(db, week_ago, today, user, granularity="day", **_to_operations_rest_filters(production_filters))
    points = trend.get("points", [])
    avg_opened_7d = round(mean(p["opened_operation"] for p in points), 1) if points else 0.0
    avg_closed_7d = round(mean(p["completed"] for p in points), 1) if points else 0.0

    # F5 - poucos gráficos, só com fonte confiável (validado com dado real antes de expor):
    # abertas x finalizadas usa o MESMO `trend` já calculado acima (nenhuma consulta extra);
    # SLA por dia vem do mesmo ponto (`sla_rate` já é confiável - validado sem None em 7 dias
    # reais); evolução de backlog usa o snapshot diário já existente (uma consulta a mais).
    charts = {
        "production_7d": [{"date": p["period_start"], "opened": p["opened_operation"], "closed": p["completed"]} for p in points],
        "sla_7d": [{"date": p["period_start"], "sla_rate": p["sla_rate"]} for p in points],
        "backlog_7d": _backlog_history_series(db, user, date_from=week_ago, date_to=today, regionals=regionals),
    }

    try:
        aging = ai_queries.backlog_aging(db, user, group_by="regional", date_to=today, **backlog_filters)
        aging_rows = aging.get("data", [])
    except Exception:  # backlog vazio ou dimensão sem dado não pode derrubar o cockpit inteiro
        aging_rows = []
        warnings.append({"code": "BACKLOG_AGING_UNAVAILABLE"})
    backlog_gt_3d = sum(row.get("over_3d", 0) for row in aging_rows)
    backlog_gt_7d = sum(row.get("over_7d", 0) for row in aging_rows)
    backlog_gt_15d = sum(row.get("over_15d", 0) for row in aging_rows)
    # backlog.total precisa refletir o MESMO filtro do widget backlog (não o de production) -
    # só recalcula `overview` de novo se o filtro efetivo realmente mudou (caso comum: igual ao
    # de production, reusa sem custo extra de query).
    backlog_overview = (
        overview_today if backlog_filters == production_filters else ops_queries.overview(db, today, today, user, **_to_operations_rest_filters(backlog_filters))
    )

    collab_sla = ops_queries.collaborator_sla(db, week_ago, today, user, **_to_operations_rest_filters(sla_filters))
    regional_sla_totals: dict[str, dict[str, int]] = {}
    for item in collab_sla.get("items", []):
        regional_name = item.get("regional") or "NAO IDENTIFICADO"
        bucket = regional_sla_totals.setdefault(regional_name, {"on_time": 0, "out_of_time": 0})
        bucket["on_time"] += item.get("on_time", 0)
        bucket["out_of_time"] += item.get("out_of_time", 0)
    critical_regionals = []
    for regional_name, agg in regional_sla_totals.items():
        total = agg["on_time"] + agg["out_of_time"]
        if total == 0:
            continue
        rate = round(agg["on_time"] / total * 100, 1)
        if rate < SLA_TARGET_PCT:
            critical_regionals.append({"regional": regional_name, "sla_rate": rate})
    critical_regionals.sort(key=lambda item: item["sla_rate"])

    sla_overview = (
        overview_today if sla_filters == production_filters else ops_queries.overview(db, today, today, user, **_to_operations_rest_filters(sla_filters))
    )
    sla_current = sla_overview.get("sla_rate")

    freshness = ops_queries.data_freshness(db)

    alerts_filters = _widget_entry(widget_entries, "active_alerts")["filters"]
    incidents_filters = _widget_entry(widget_entries, "active_incidents")["filters"]
    content_filters = _widget_entry(widget_entries, "cockpit_content")["filters"]

    active_alerts = _apply_list_post_filters(
        [_alert_to_summary(a) for a in _active_alerts_query(db, regionals) if a.kind == "ALERT"], alerts_filters, "active_alerts", warnings
    )
    active_incidents = _apply_list_post_filters(
        [_alert_to_summary(a) for a in _active_alerts_query(db, regionals) if a.kind == "INCIDENT"], incidents_filters, "active_incidents", warnings
    )
    content = _apply_list_post_filters(
        [_content_to_summary(c) for c in _content_query(db, profile, regionals)], content_filters, "cockpit_content", warnings
    )
    monitor_health = _monitor_health_summary(db)
    any_monitor_unhealthy = any(item["alert_type"] == "MONITOR_UNHEALTHY" for item in active_alerts)

    overall_status = compute_overall_status(
        alerts=active_alerts,
        incidents=active_incidents,
        backlog_gt_15d=backlog_gt_15d,
        backlog_gt_7d=backlog_gt_7d,
        sla_current=sla_current,
        any_monitor_unhealthy=any_monitor_unhealthy,
        is_global_scope=not regionals,
    )
    display_mode = _display_mode(overall_status["status"], active_incidents)

    if freshness.get("last_successful_import_at") is None:
        warnings.append({"code": "NO_SUCCESSFUL_IMPORT_YET"})

    applied_filters: dict[str, Any] = {"sectors": sectors}
    if regionals:
        applied_filters["regionals"] = regionals
    meta = build_meta(
        applied_filters=applied_filters,
        warnings=warnings,
        source_last_sync=freshness.get("last_successful_import_at"),
    )

    return {
        "profile": {
            "key": profile.key,
            "name": profile.name,
            "purpose": profile.purpose,
            "widgets": [entry["key"] for entry in widget_entries],
            "refresh_seconds": profile.refresh_seconds,
            "display_config": profile.display_config_json,
        },
        "generated_at": datetime.now(timezone.utc),
        "overall_status": overall_status,
        "display_mode": display_mode,
        "production": {
            "opened_today": overview_today.get("opened", 0),
            "closed_today": overview_today.get("completed", 0),
            "balance_today": overview_today.get("opened", 0) - overview_today.get("completed", 0),
            "avg_opened_7d": avg_opened_7d,
            "avg_closed_7d": avg_closed_7d,
        },
        "backlog": {
            "total": backlog_overview.get("in_progress", 0),
            "gt_3d": backlog_gt_3d,
            "gt_7d": backlog_gt_7d,
            "gt_15d": backlog_gt_15d,
        },
        "sla": {
            "current": sla_current,
            "target": SLA_TARGET_PCT,
            "critical_regionals": critical_regionals,
        },
        "alerts": active_alerts,
        "incidents": active_incidents,
        "content": content,
        "monitor_health": monitor_health,
        "charts": charts,
        "data_freshness": freshness,
        "meta": meta,
    }


# --- contexto para consulta horária (F4 - ChatGPT agendado) --------------------------------------


def _last_active_content_by_type(content: list[dict], content_type: str) -> dict | None:
    # `content` já vem ordenado por created_at desc (ver _content_query) - o primeiro que bate o
    # tipo é o mais recente ativo.
    for item in content:
        if item["content_type"] == content_type:
            return {
                "id": item["id"],
                "title": item["title"],
                "summary": item["body"][:280],
                "created_at": item["created_at"],
                "source_type": item["source_type"],
                "source_key": item["source_key"],
            }
    return None


def build_cockpit_context(db: Session, profile: IntelligenceDashboardProfile) -> dict:
    """Contexto compacto para a consulta horária do ChatGPT (`opr_get_cockpit_context`) - reusa
    INTEIRAMENTE `build_cockpit_payload` (mesmo cálculo da TV, nenhuma consulta nova) e só
    acrescenta o escopo bruto do profile e o último AI_INSIGHT ativo. O objetivo do
    `last_ai_insight` é dar pra quem consome (a análise horária) decidir "nada relevante mudou,
    não preciso publicar outro insight" sem precisar de um mecanismo de hash/versionamento à
    parte - o `id`/`created_at` do último insight já bastam pra essa comparação."""
    payload = build_cockpit_payload(db, profile)
    return {
        **payload,
        "scope": profile.scope_json,
        "last_ai_insight": _last_active_content_by_type(payload["content"], "AI_INSIGHT"),
    }


# --- publicação de conteúdo -----------------------------------------------------------------------


def publish_cockpit_content(
    db: Session,
    *,
    content_type: str,
    profile_key: str | None,
    scope: dict | None,
    severity: str,
    title: str,
    body: str,
    evidence: dict | None,
    confidence: float | None,
    valid_until: datetime | None,
    source_type: str,
    source_key: str | None,
    author_user_id: int | None,
) -> IntelligenceCockpitContent:
    """Única porta de escrita de `intelligence_cockpit_content` - usada tanto pelo endpoint REST
    quanto pela tool MCP `opr_publish_cockpit_content`, para não duplicar regra de negócio (decisão
    explícita aprovada)."""

    if content_type not in CONTENT_TYPES:
        raise CockpitContentValidationError(f"content_type inválido: {content_type!r}. Use um de {CONTENT_TYPES}.")
    if severity not in CONTENT_SEVERITIES:
        raise CockpitContentValidationError(f"severity inválida: {severity!r}. Use um de {CONTENT_SEVERITIES}.")
    if source_type not in CONTENT_SOURCE_TYPES:
        raise CockpitContentValidationError(f"source_type inválido: {source_type!r}. Use um de {CONTENT_SOURCE_TYPES}.")
    if not title or not title.strip():
        raise CockpitContentValidationError("title é obrigatório.")
    if len(title) > MAX_TITLE_LENGTH:
        raise CockpitContentValidationError(f"title excede o limite de {MAX_TITLE_LENGTH} caracteres.")
    if not body or not body.strip():
        raise CockpitContentValidationError("body é obrigatório.")
    if len(body) > MAX_BODY_LENGTH:
        raise CockpitContentValidationError(f"body excede o limite de {MAX_BODY_LENGTH} caracteres.")
    # nenhuma publicação anônima: precisa de origem identificável, seja humana ou de sistema/IA.
    if not source_key and not author_user_id:
        raise CockpitContentValidationError("Publicação precisa de origem identificável (source_key ou author_user_id).")
    if profile_key is not None and get_profile(db, profile_key) is None:
        raise CockpitContentValidationError(f"Profile '{profile_key}' não existe.")
    if confidence is not None and not (0.0 <= confidence <= 1.0):
        raise CockpitContentValidationError("confidence precisa estar entre 0.0 e 1.0.")
    if valid_until is not None and valid_until <= datetime.now(timezone.utc):
        raise CockpitContentValidationError("valid_until precisa ser uma data futura.")

    scope = scope or {}
    regional = scope.get("regional")
    if not regional:
        scope_regionals = scope.get("regionals") or []
        regional = scope_regionals[0] if len(scope_regionals) == 1 else None

    content = IntelligenceCockpitContent(
        content_type=content_type,
        profile_key=profile_key,
        scope_json=scope,
        regional=regional,
        severity=severity,
        title=title.strip(),
        body=body.strip(),
        evidence_json=evidence or {},
        confidence=confidence,
        source_type=source_type,
        source_key=source_key,
        author_user_id=author_user_id,
        status="ACTIVE",
        valid_from=datetime.now(timezone.utc),
        valid_until=valid_until,
    )
    db.add(content)
    db.commit()
    db.refresh(content)
    return content


def dismiss_cockpit_content(db: Session, content: IntelligenceCockpitContent) -> IntelligenceCockpitContent:
    """Expira manualmente uma publicação (Administração → Publicações) - status vira DISMISSED,
    o que já é suficiente pra `_content_query` parar de mostrar na TV (só aceita status ACTIVE)."""
    content.status = "DISMISSED"
    db.commit()
    db.refresh(content)
    return content


def update_cockpit_content(
    db: Session,
    content: IntelligenceCockpitContent,
    *,
    title: str | None = None,
    body: str | None = None,
    severity: str | None = None,
    valid_until: datetime | None = None,
) -> IntelligenceCockpitContent:
    """Edição simples de uma publicação ativa (Administração → Publicações) - só os campos
    editoriais (título/corpo/severidade/validade); origem, tipo e profile/scope não mudam depois
    de publicados (evita reescrever a proveniência de um conteúdo já entregue)."""
    if content.status != "ACTIVE":
        raise CockpitContentValidationError("só é possível editar conteúdo ACTIVE.")
    if title is not None:
        if not title.strip():
            raise CockpitContentValidationError("title não pode ficar vazio.")
        if len(title) > MAX_TITLE_LENGTH:
            raise CockpitContentValidationError(f"title excede o limite de {MAX_TITLE_LENGTH} caracteres.")
        content.title = title.strip()
    if body is not None:
        if not body.strip():
            raise CockpitContentValidationError("body não pode ficar vazio.")
        if len(body) > MAX_BODY_LENGTH:
            raise CockpitContentValidationError(f"body excede o limite de {MAX_BODY_LENGTH} caracteres.")
        content.body = body.strip()
    if severity is not None:
        if severity not in CONTENT_SEVERITIES:
            raise CockpitContentValidationError(f"severity inválida: {severity!r}. Use um de {CONTENT_SEVERITIES}.")
        content.severity = severity
    if valid_until is not None:
        if valid_until <= datetime.now(timezone.utc):
            raise CockpitContentValidationError("valid_until precisa ser uma data futura.")
        content.valid_until = valid_until
    db.commit()
    db.refresh(content)
    return content


def list_cockpit_content(
    db: Session,
    *,
    profile_key: str | None = None,
    status: str | None = None,
    content_type: str | None = None,
    limit: int = 100,
) -> list[IntelligenceCockpitContent]:
    """Listagem para Administração → Publicações (ativos + histórico básico) - diferente de
    `_content_query` (que é o que a TV vê): aqui mostra QUALQUER status e não aplica recorte de
    regional, porque é uma tela de gestão, não a TV."""
    conditions = []
    if profile_key is not None:
        conditions.append(IntelligenceCockpitContent.profile_key == profile_key)
    if status is not None:
        conditions.append(IntelligenceCockpitContent.status == status)
    if content_type is not None:
        conditions.append(IntelligenceCockpitContent.content_type == content_type)
    return list(
        db.scalars(
            select(IntelligenceCockpitContent).where(*conditions).order_by(IntelligenceCockpitContent.created_at.desc()).limit(limit)
        )
    )


# --- administração de profiles (F5) ---------------------------------------------------------------


def list_profiles(db: Session) -> list[IntelligenceDashboardProfile]:
    return list(db.scalars(select(IntelligenceDashboardProfile).order_by(IntelligenceDashboardProfile.key)))


def create_profile(
    db: Session,
    *,
    key: str,
    name: str,
    purpose: str,
    scope: dict,
    widgets: list[dict],
    display_config: dict,
    refresh_seconds: int,
    active: bool,
) -> IntelligenceDashboardProfile:
    if not key or not key.strip():
        raise ProfileValidationError("key é obrigatória.")
    if get_profile(db, key) is not None:
        raise ProfileValidationError(f"já existe um profile com key {key!r}.")
    if not name or not name.strip():
        raise ProfileValidationError("name é obrigatório.")
    if refresh_seconds < 15:
        raise ProfileValidationError("refresh_seconds precisa ser >= 15 (mesmo piso do polling da TV).")
    validated_widgets = validate_widget_entries(widgets)
    profile = IntelligenceDashboardProfile(
        key=key.strip(),
        name=name.strip(),
        purpose=purpose,
        scope_json=scope or {"regionals": []},
        widgets_json=validated_widgets,
        display_config_json=display_config or {},
        refresh_seconds=refresh_seconds,
        active=active,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def update_profile(
    db: Session,
    profile: IntelligenceDashboardProfile,
    *,
    name: str | None = None,
    purpose: str | None = None,
    scope: dict | None = None,
    widgets: list[dict] | None = None,
    display_config: dict | None = None,
    refresh_seconds: int | None = None,
    active: bool | None = None,
) -> IntelligenceDashboardProfile:
    if name is not None:
        if not name.strip():
            raise ProfileValidationError("name não pode ficar vazio.")
        profile.name = name.strip()
    if purpose is not None:
        profile.purpose = purpose
    if scope is not None:
        profile.scope_json = scope
    if widgets is not None:
        profile.widgets_json = validate_widget_entries(widgets)
    if display_config is not None:
        profile.display_config_json = display_config
    if refresh_seconds is not None:
        if refresh_seconds < 15:
            raise ProfileValidationError("refresh_seconds precisa ser >= 15 (mesmo piso do polling da TV).")
        profile.refresh_seconds = refresh_seconds
    if active is not None:
        profile.active = active
    db.commit()
    db.refresh(profile)
    return profile


def profile_to_admin_out(profile: IntelligenceDashboardProfile) -> dict:
    return {
        "id": profile.id,
        "key": profile.key,
        "name": profile.name,
        "purpose": profile.purpose,
        "scope": profile.scope_json,
        "widgets": normalize_widget_entries(profile.widgets_json),
        "display_config": profile.display_config_json,
        "refresh_seconds": profile.refresh_seconds,
        "active": profile.active,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


# --- catálogo de filtros para a Administração (F5) -------------------------------------------------

# Achado real (investigação de performance): `build_filter_catalog` chamava `ops_queries.
# filter_options()` só para extrair `os_subjects` - essa função varre ~16 colunas de
# `operations_orders` (uma query DISTINCT por coluna), cada uma um Seq Scan completo na tabela
# (janela de 400 dias cobre 95% das linhas, o índice de data não ajuda) - medido em produção:
# 1.8-3.4s na aba Profiles só por causa disso, para usar 1 de 16 resultados. Query dedicada abaixo
# faz 1 scan em vez de 16. `os_subjects` muda pouco (é catálogo de opções, não dado operacional em
# tempo real) - por isso também cacheado por alguns minutos em processo (nunca por usuário/request,
# o valor é o mesmo para qualquer chamador).
_OS_SUBJECTS_CACHE_TTL_SECONDS = 300
_os_subjects_cache: dict[str, Any] = {"values": None, "expires_at": None}


def _distinct_os_subjects(db: Session) -> list[str]:
    from app.modules.operations.models import OperationOrder

    cached_values = _os_subjects_cache["values"]
    expires_at = _os_subjects_cache["expires_at"]
    now = datetime.now(timezone.utc)
    if cached_values is not None and expires_at is not None and now < expires_at:
        return cached_values

    values = db.scalars(
        select(OperationOrder.os_subject).where(OperationOrder.os_subject.is_not(None), OperationOrder.os_subject != "").distinct()
    )
    result = sorted({str(value) for value in values}, key=str.casefold)
    _os_subjects_cache["values"] = result
    _os_subjects_cache["expires_at"] = now + timedelta(seconds=_OS_SUBJECTS_CACHE_TTL_SECONDS)
    return result


def build_filter_catalog(db: Session) -> dict:
    """Fontes REAIS para popular selects na Administração (perfis/widgets) - nunca JSON bruto
    como interface principal. `os_subjects`/regionais/setores vêm dos mesmos catálogos que o
    resto da Operação Analítica já usa; `team_models` vem da tabela real de modelos de equipe."""
    from app.modules.operations.models import OperationTeamModel
    from app.modules.operations.scope import ALL_SECTOR_NAMES
    from app.services.regional import REGIONAL_CODE_MAP

    team_models = list(db.scalars(select(OperationTeamModel.name).where(OperationTeamModel.active.is_(True)).order_by(OperationTeamModel.name)))

    try:
        os_subjects = _distinct_os_subjects(db)
    except Exception:
        os_subjects = []

    return {
        "regionals": sorted(set(REGIONAL_CODE_MAP.values())),
        "sectors": list(ALL_SECTOR_NAMES),
        "team_models": team_models,
        "os_subjects": os_subjects,
        "content_types": list(CONTENT_TYPES),
        "content_severities": list(CONTENT_SEVERITIES),
        "profile_purposes": ["MATRIX_TV", "REGIONAL_TV", "EXECUTIVE", "INCIDENT_ROOM", "NOC"],
        "widgets": [{"key": key, "allowed_filters": sorted(allowed)} for key, allowed in WIDGET_ALLOWED_FILTERS.items()],
    }
