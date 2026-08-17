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

# Meta de SLA percentual - não existe constante equivalente em `operations` (achado da
# investigação: `sla_target_hours` é por O.S. individual, não um percentual agregado). Usa o
# mesmo corte visual já usado no frontend (`lib/operations-sla.ts::slaTone`, 80%/60%), agora
# centralizado aqui para o cockpit não espalhar o número de novo.
SLA_TARGET_PCT = 80.0
SLA_CRITICAL_PCT = 50.0

# Limiares do status geral - centralizados aqui, nunca espalhados no frontend.
BACKLOG_GT15D_CRITICAL = 50
BACKLOG_GT7D_ATTENTION = 30

_SEVERITY_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


class CockpitContentValidationError(ValueError):
    """Erro de validação de publicação de conteúdo - vira 422 no REST e ValueError na tool MCP."""


# --- dashboard profiles -------------------------------------------------------------------------


def get_profile(db: Session, key: str) -> IntelligenceDashboardProfile | None:
    return db.scalar(select(IntelligenceDashboardProfile).where(IntelligenceDashboardProfile.key == key))


_DEFAULT_PROFILE_KEY = "uni-geral"


def ensure_default_dashboard_profile(db: Session) -> None:
    """Seed idempotente do profile 'UNI Geral' - mesmo padrão de `ensure_ai_governance_seed`
    (só insere se não existir, nunca sobrescreve configuração já feita pela Administração)."""
    if get_profile(db, _DEFAULT_PROFILE_KEY) is not None:
        return
    db.add(
        IntelligenceDashboardProfile(
            key=_DEFAULT_PROFILE_KEY,
            name="UNI Geral",
            purpose="MATRIX_TV",
            scope_json={"regionals": []},
            widgets_json=[
                "overall_status",
                "active_alerts",
                "active_incidents",
                "production",
                "backlog",
                "sla",
                "cockpit_content",
                "monitor_health",
            ],
            display_config_json={},
            refresh_seconds=60,
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


def _content_query(db: Session, profile_key: str) -> list[IntelligenceCockpitContent]:
    now = datetime.now(timezone.utc)
    rows = list(
        db.scalars(
            select(IntelligenceCockpitContent)
            .where(
                IntelligenceCockpitContent.status == "ACTIVE",
                (IntelligenceCockpitContent.profile_key == profile_key) | (IntelligenceCockpitContent.profile_key.is_(None)),
            )
            .order_by(IntelligenceCockpitContent.created_at.desc())
        )
    )
    # conteúdo expirado não aparece na TV, mesmo que ninguém tenha rodado a expiração em lote ainda
    return [row for row in rows if row.valid_until is None or row.valid_until > now]


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


def compute_overall_status(
    *,
    alerts: list[dict],
    incidents: list[dict],
    backlog_gt_15d: int,
    backlog_gt_7d: int,
    sla_current: float | None,
    any_monitor_unhealthy: bool,
) -> dict:
    """Regra determinística e centralizada (nunca IA, nunca hardcoded no frontend) - ver item
    "Status geral" do processo aprovado. Combina alertas ativos, incidentes, severidade,
    monitor_unhealthy, SLA e backlog."""
    max_incident_severity = max((item["severity"] for item in incidents), key=lambda sev: _SEVERITY_RANK.get(sev, -1), default=None)
    max_alert_severity = max((item["severity"] for item in alerts), key=lambda sev: _SEVERITY_RANK.get(sev, -1), default=None)

    if max_incident_severity == "CRITICAL":
        return {"status": "CRITICAL", "reason": "Incidente crítico ativo."}
    if sla_current is not None and sla_current < SLA_CRITICAL_PCT:
        return {"status": "CRITICAL", "reason": f"SLA em {sla_current}%, muito abaixo da meta ({SLA_TARGET_PCT}%)."}
    if backlog_gt_15d > BACKLOG_GT15D_CRITICAL:
        return {"status": "CRITICAL", "reason": f"{backlog_gt_15d} O.S. no backlog há mais de 15 dias."}

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
    filters: dict[str, Any] = {"regionals": regionals} if regionals else {}
    user = system_user()
    today = datetime.now(OPERATIONS_TIMEZONE).date()
    week_ago = today - timedelta(days=6)

    warnings: list[dict] = []

    overview_today = ops_queries.overview(db, today, today, user, **filters)
    trend = ops_services.overview_trends(db, week_ago, today, user, granularity="day", **filters)
    points = trend.get("points", [])
    avg_opened_7d = round(mean(p["opened_operation"] for p in points), 1) if points else 0.0
    avg_closed_7d = round(mean(p["completed"] for p in points), 1) if points else 0.0

    try:
        aging = ai_queries.backlog_aging(db, user, group_by="regional", date_to=today, **filters)
        aging_rows = aging.get("data", [])
    except Exception:  # backlog vazio ou dimensão sem dado não pode derrubar o cockpit inteiro
        aging_rows = []
        warnings.append({"code": "BACKLOG_AGING_UNAVAILABLE"})
    backlog_gt_3d = sum(row.get("over_3d", 0) for row in aging_rows)
    backlog_gt_7d = sum(row.get("over_7d", 0) for row in aging_rows)
    backlog_gt_15d = sum(row.get("over_15d", 0) for row in aging_rows)

    collab_sla = ops_queries.collaborator_sla(db, week_ago, today, user, **filters)
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

    sla_current = overview_today.get("sla_rate")

    freshness = ops_queries.data_freshness(db)

    active_alerts = [_alert_to_summary(a) for a in _active_alerts_query(db, regionals) if a.kind == "ALERT"]
    active_incidents = [_alert_to_summary(a) for a in _active_alerts_query(db, regionals) if a.kind == "INCIDENT"]
    content = [_content_to_summary(c) for c in _content_query(db, profile.key)]
    monitor_health = _monitor_health_summary(db)
    any_monitor_unhealthy = any(item["alert_type"] == "MONITOR_UNHEALTHY" for item in active_alerts)

    overall_status = compute_overall_status(
        alerts=active_alerts,
        incidents=active_incidents,
        backlog_gt_15d=backlog_gt_15d,
        backlog_gt_7d=backlog_gt_7d,
        sla_current=sla_current,
        any_monitor_unhealthy=any_monitor_unhealthy,
    )
    display_mode = _display_mode(overall_status["status"], active_incidents)

    if freshness.get("last_successful_import_at") is None:
        warnings.append({"code": "NO_SUCCESSFUL_IMPORT_YET"})

    meta = build_meta(
        applied_filters={"regionals": regionals} if regionals else {},
        warnings=warnings,
        source_last_sync=freshness.get("last_successful_import_at"),
    )

    return {
        "profile": {
            "key": profile.key,
            "name": profile.name,
            "purpose": profile.purpose,
            "widgets": profile.widgets_json,
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
            "total": overview_today.get("in_progress", 0),
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
        "data_freshness": freshness,
        "meta": meta,
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
