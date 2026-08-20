"""Tipos compartilhados entre scheduler, registry e monitores - dataclasses simples, sem
acoplamento a schema de banco. `alerts.py` e quem traduz uma `MonitorDetection` em
`IntelligenceAlert` (dedupe/lifecycle); os monitores nunca tocam o modelo SQLAlchemy diretamente."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

AlertKind = Literal["ALERT", "INCIDENT"]
AlertSeverity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


@dataclass(frozen=True)
class MonitorDetection:
    """Uma ocorrencia detectada por um monitor em um ciclo de execucao.

    `dedupe_key` precisa ser estavel entre execucoes para a MESMA ocorrencia real - e o mecanismo
    central que impede o alerta de "nascer de novo" a cada ciclo (ver alerts.sync_alerts_for_monitor).
    Um monitor mal projetado que gera uma dedupe_key diferente a cada rodada (ex.: com timestamp
    embutido) quebra todo o lifecycle - por isso cada monitor documenta a formula da sua chave.
    """

    dedupe_key: str
    kind: AlertKind
    alert_type: str
    severity: AlertSeverity
    title: str
    summary: str
    regional: str | None = None
    city: str | None = None
    scope: dict[str, Any] = field(default_factory=dict)
    recommended_action: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None
    coverage: dict[str, Any] = field(default_factory=dict)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    source_last_sync: datetime | None = None


@dataclass(frozen=True)
class MonitorRunResult:
    """O que um monitor devolve ao scheduler em cada execucao. `stats` e informacao livre por
    monitor (ex.: quantas regionais avaliadas, quantos clusters descartados por tamanho) - grava
    em `IntelligenceMonitorRun.stats_json`, nao normalizada em coluna porque cada monitor mede
    coisas diferentes."""

    detections: list[MonitorDetection] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
