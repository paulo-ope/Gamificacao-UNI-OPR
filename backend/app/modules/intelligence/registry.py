"""Registro declarativo dos monitores do UNI Intelligence.

Mesmo racional do `app/modules/registry.py`: o registro não executa nada sozinho, só descreve
metadados. Quem liga/desliga e define o intervalo de cada monitor é o `app_settings` (ver
scheduler.py), no mesmo padrão já usado por IXC/OPA/login-status/onu-signal - intervalos não
ficam espalhados hardcoded pelo código, e dá pra mudar pela tela de configuração sem deploy.

Adicionar um monitor novo é só acrescentar uma entrada aqui e escrever o `runner` correspondente
em `monitors/` - o scheduler e o router não precisam mudar."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from sqlalchemy.orm import Session

from .types import MonitorRunResult

ScopeStrategy = Literal["global", "regional"]


@dataclass(frozen=True)
class MonitorDefinition:
    key: str
    name: str
    description: str
    # Usado só como valor inicial/fallback - o efetivo vem de app_settings (ver scheduler.py).
    default_interval_minutes: int
    enabled_by_default: bool
    scope_strategy: ScopeStrategy
    # Ciclos consecutivos sem redetecção até um alerta deste monitor ser auto-resolvido
    # (ver alerts.sync_alerts_for_monitor). Também só o valor inicial/fallback.
    resolve_after_misses: int
    runner: Callable[[Session], MonitorRunResult]


def _collective_outage_runner(db: Session) -> MonitorRunResult:
    from .monitors.collective_outage import run_collective_outage_monitor

    return run_collective_outage_monitor(db)


def _sla_deterioration_runner(db: Session) -> MonitorRunResult:
    from .monitors.sla_deterioration import run_sla_deterioration_monitor

    return run_sla_deterioration_monitor(db)


def _operational_pressure_runner(db: Session) -> MonitorRunResult:
    from .monitors.operational_pressure import run_operational_pressure_monitor

    return run_operational_pressure_monitor(db)


def _monitor_health_runner(db: Session) -> MonitorRunResult:
    from .monitors.monitor_health import run_monitor_health_monitor

    return run_monitor_health_monitor(db)


MONITORS: tuple[MonitorDefinition, ...] = (
    MonitorDefinition(
        key="collective_outage",
        name="Incidente coletivo de rede",
        description=(
            "Detecta possivel incidente coletivo a partir de clusters geograficos de logins "
            "offline e do funil de quedas simultaneas (login_incident_analysis)."
        ),
        default_interval_minutes=5,
        enabled_by_default=True,
        scope_strategy="regional",
        resolve_after_misses=3,
        runner=_collective_outage_runner,
    ),
    MonitorDefinition(
        key="sla_deterioration",
        name="Deterioracao de SLA",
        description=(
            "Compara SLA recente (7 dias) contra baseline por regional e aponta deterioracao "
            "relevante - nao apenas SLA abaixo da meta."
        ),
        default_interval_minutes=30,
        enabled_by_default=True,
        scope_strategy="regional",
        resolve_after_misses=2,
        runner=_sla_deterioration_runner,
    ),
    MonitorDefinition(
        key="operational_pressure",
        name="Pressao operacional",
        description=(
            "Usa a Torre de Controle Preventiva (baseline de 8 semanas) para identificar "
            "regionais com desvio de volume/backlog em deterioracao."
        ),
        default_interval_minutes=30,
        enabled_by_default=True,
        scope_strategy="regional",
        resolve_after_misses=2,
        runner=_operational_pressure_runner,
    ),
    MonitorDefinition(
        key="monitor_health",
        name="Saude dos monitores",
        description="Meta-monitor: verifica se os demais monitores estao rodando dentro do intervalo esperado.",
        default_interval_minutes=5,
        enabled_by_default=True,
        scope_strategy="global",
        resolve_after_misses=2,
        runner=_monitor_health_runner,
    ),
)


def list_monitors() -> tuple[MonitorDefinition, ...]:
    return MONITORS


def get_monitor(key: str) -> MonitorDefinition | None:
    return next((monitor for monitor in MONITORS if monitor.key == key), None)
