"""Monitor de pressão operacional - adaptador fino sobre a Torre de Controle Preventiva
(`operations/services.py::control_tower`, baseline de 8 semanas), no nível "regional". Não
recalcula nada: só decide, a partir do status que a torre já atribui a cada regional
(normal/attention/critical/insufficient), quais viram um IntelligenceAlert.

`control_tower` exige um `User` só para aplicar escopo regional (gestor com `managed_regionals`
configurado) - usamos o usuário transiente de scope.py para enxergar todas as regionais."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.modules.operations.period import OPERATIONS_TIMEZONE
from app.modules.operations.queries import data_freshness
from app.modules.operations.scope import PRIMARY_SECTOR_NAMES
from app.modules.operations.services import control_tower

from ..scope import system_user
from ..types import MonitorDetection, MonitorRunResult

RECENT_DAYS = 7
BASELINE_WEEKS = 8
TIMELINE_DAYS = 28

# control_tower ainda não produz o envelope `meta` do FilterContractV1 (é uma função anterior à
# Fase 1 de confiabilidade) - por isso este monitor não preenche `coverage`/`warnings` a partir
# dela. Debt documentado: quando control_tower ganhar `meta`, propagar aqui (ver item N do estudo
# de arquitetura - não é escopo desta plataforma mudar o FilterContractV1 retroativamente).
_STATUS_TO_SEVERITY = {"critical": "HIGH", "attention": "MEDIUM"}
_PERSISTENT_DAYS_FOR_CRITICAL = 3


def _severity_for_item(status: str, persistent_days: int) -> str | None:
    base = _STATUS_TO_SEVERITY.get(status)
    if base is None:
        return None
    if base == "HIGH" and persistent_days >= _PERSISTENT_DAYS_FOR_CRITICAL:
        return "CRITICAL"
    return base


def _confidence_for_item(persistent_days: int, deviation_percentage: float | None) -> float:
    """Base 0.5 + até 0.3 por persistência (dias seguidos no mesmo estado) + até 0.15 pela
    magnitude do desvio - a torre de controle já usa 8 semanas de baseline, então a confiança
    parte de um piso mais alto que a de um monitor sem baseline histórico."""
    persistence_factor = min(persistent_days / 10, 1.0)
    deviation_factor = min(abs(deviation_percentage or 0) / 100, 1.0)
    confidence = 0.5 + persistence_factor * 0.3 + deviation_factor * 0.15
    return round(min(confidence, 0.95), 2)


def run_operational_pressure_monitor(db: Session) -> MonitorRunResult:
    reference_date = datetime.now(OPERATIONS_TIMEZONE).date()
    user = system_user()
    tower = control_tower(
        db,
        reference_date,
        user,
        level="regional",
        recent_days=RECENT_DAYS,
        baseline_weeks=BASELINE_WEEKS,
        timeline_days=TIMELINE_DAYS,
        # F4 - achado F3: mesma correcao do backlog/SLA - sem isso, a torre de controle mede
        # pressao sobre TODA operations_orders (Cobranca/Comercial/Estoque etc), nao so a
        # operacao de campo. Fonte canonica unica (operations/scope.py), sem duplicar a lista.
        sectors=list(PRIMARY_SECTOR_NAMES),
    )
    source_last_sync = data_freshness(db).get("last_successful_import_at")

    detections: list[MonitorDetection] = []
    for item in tower.get("items", []):
        severity = _severity_for_item(item["status"], item.get("persistent_days", 0))
        if severity is None:
            continue

        regional = item["label"]
        dedupe_key = f"operational_pressure:{regional}"
        deviation = item.get("deviation_percentage")
        reasons = item.get("reasons") or []
        summary = (
            f"Regional {regional} em estado '{item['status']}' há {item.get('persistent_days', 0)} dia(s): "
            f"{item.get('opened_recent', 0)} aberturas recentes vs {round(item.get('expected_opened', 0) or 0, 1)} esperadas"
            + (f" ({deviation:+.1f}%)" if deviation is not None else "")
            + f", backlog de {item.get('backlog', 0)} ({item.get('overdue_backlog', 0)} vencido)."
        )

        detections.append(
            MonitorDetection(
                dedupe_key=dedupe_key,
                kind="ALERT",
                alert_type="OPERATIONAL_PRESSURE",
                severity=severity,
                title=f"Pressão operacional em {regional}",
                summary=summary,
                regional=regional,
                scope={"regional": regional, "level": "regional"},
                recommended_action=(
                    "avaliar reforço de equipe ou priorização de backlog"
                    if item.get("net_flow", 0) < 0
                    else "acompanhar - vazão ainda supera entrada"
                ),
                evidence={
                    "status": item["status"],
                    "opened_recent": item.get("opened_recent"),
                    "expected_opened": item.get("expected_opened"),
                    "deviation_percentage": deviation,
                    "completed_recent": item.get("completed_recent"),
                    "net_flow": item.get("net_flow"),
                    "pressure_ratio": item.get("pressure_ratio"),
                    "backlog": item.get("backlog"),
                    "overdue_backlog": item.get("overdue_backlog"),
                    "average_backlog_age_hours": item.get("average_backlog_age_hours"),
                    "persistent_days": item.get("persistent_days"),
                    "reasons": reasons,
                },
                confidence=_confidence_for_item(item.get("persistent_days", 0), deviation),
                coverage={},
                warnings=[],
                source_last_sync=source_last_sync,
            )
        )

    return MonitorRunResult(
        detections=detections,
        stats={
            "regionals_evaluated": len(tower.get("items", [])),
            "summary_status": tower.get("summary", {}).get("status"),
        },
    )
