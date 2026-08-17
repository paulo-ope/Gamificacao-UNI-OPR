"""Monitor de deterioração de SLA - adaptador fino sobre `operations/queries.py::sla_breakdown`
(a mesma função que alimenta a aba SLA do módulo Operação Analítica). Não recalcula SLA: só chama
essa função duas vezes por regional (janela recente x baseline) e compara.

Objetivo explícito (pedido do usuário): detectar DETERIORAÇÃO relevante, não simplesmente "SLA
abaixo da meta" - por isso a comparação é sempre relativa a um baseline recente da própria
regional, nunca contra um limiar fixo isolado."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.modules.operations.period import OPERATIONS_TIMEZONE
from app.modules.operations.queries import data_freshness, sla_breakdown
from app.services.regional import REGIONAL_CODE_MAP

from ..scope import system_user
from ..types import MonitorDetection, MonitorRunResult

RECENT_WINDOW_DAYS = 7
BASELINE_WINDOW_DAYS = 28
# Abaixo disso, o baseline não tem O.S. suficiente para sustentar uma comparação - o monitor
# prefere não detectar a arriscar falso positivo sobre amostra pequena.
MIN_BASELINE_MEASURABLE = 10
MIN_RECENT_MEASURABLE = 3
# Queda mínima (em pontos percentuais) para considerar "deterioração relevante".
DETERIORATION_THRESHOLD_PP = 8.0

REGIONALS = sorted(set(REGIONAL_CODE_MAP.values()))


def _windows(reference_date: date) -> tuple[tuple[date, date], tuple[date, date]]:
    recent_to = reference_date
    recent_from = reference_date - timedelta(days=RECENT_WINDOW_DAYS - 1)
    baseline_to = recent_from - timedelta(days=1)
    baseline_from = baseline_to - timedelta(days=BASELINE_WINDOW_DAYS - 1)
    return (recent_from, recent_to), (baseline_from, baseline_to)


def _aggregate_sla(db: Session, date_from: date, date_to: date, user, regional: str) -> tuple[float | None, int]:
    rows = sla_breakdown(db, date_from, date_to, user, group_by="os_type", regionals=[regional])
    on_time = sum(row["on_time"] for row in rows)
    out_of_time = sum(row["out_of_time"] for row in rows)
    measurable = on_time + out_of_time
    if measurable == 0:
        return None, 0
    return round((on_time / measurable) * 100, 1), measurable


def _severity_for_drop(drop_pp: float) -> str:
    if drop_pp >= 25:
        return "CRITICAL"
    if drop_pp >= 15:
        return "HIGH"
    return "MEDIUM"


def _confidence_for_samples(recent_measurable: int, baseline_measurable: int) -> float:
    """Base 0.5 + até 0.25 pela amostra recente + até 0.2 pela amostra do baseline - mais O.S.
    medidas em cada janela sustentam mais confiança na comparação."""
    recent_factor = min(recent_measurable / 50, 1.0)
    baseline_factor = min(baseline_measurable / 100, 1.0)
    confidence = 0.5 + recent_factor * 0.25 + baseline_factor * 0.2
    return round(min(confidence, 0.95), 2)


def run_sla_deterioration_monitor(db: Session) -> MonitorRunResult:
    reference_date = datetime.now(OPERATIONS_TIMEZONE).date()
    (recent_from, recent_to), (baseline_from, baseline_to) = _windows(reference_date)
    user = system_user()
    source_last_sync = data_freshness(db).get("last_successful_import_at")

    detections: list[MonitorDetection] = []
    regionals_with_data = 0
    regionals_insufficient = 0

    for regional in REGIONALS:
        baseline_rate, baseline_measurable = _aggregate_sla(db, baseline_from, baseline_to, user, regional)
        recent_rate, recent_measurable = _aggregate_sla(db, recent_from, recent_to, user, regional)

        if baseline_measurable < MIN_BASELINE_MEASURABLE or recent_measurable < MIN_RECENT_MEASURABLE:
            regionals_insufficient += 1
            continue
        regionals_with_data += 1

        if baseline_rate is None or recent_rate is None:
            continue

        drop_pp = baseline_rate - recent_rate
        if drop_pp < DETERIORATION_THRESHOLD_PP:
            continue

        dedupe_key = f"sla_deterioration:{regional}"
        summary = (
            f"SLA de {regional} caiu de {baseline_rate}% (baseline de {BASELINE_WINDOW_DAYS}d) "
            f"para {recent_rate}% (últimos {RECENT_WINDOW_DAYS}d) - queda de {drop_pp:.1f}pp."
        )

        detections.append(
            MonitorDetection(
                dedupe_key=dedupe_key,
                kind="ALERT",
                alert_type="SLA_DETERIORATION",
                severity=_severity_for_drop(drop_pp),
                title=f"Deterioração de SLA em {regional}",
                summary=summary,
                regional=regional,
                scope={"regional": regional},
                recommended_action="priorizar O.S. ainda salváveis dentro do SLA",
                evidence={
                    "sla_recent_pct": recent_rate,
                    "sla_baseline_pct": baseline_rate,
                    "drop_percentage_points": round(drop_pp, 1),
                    "recent_window_days": RECENT_WINDOW_DAYS,
                    "baseline_window_days": BASELINE_WINDOW_DAYS,
                    "recent_measurable_count": recent_measurable,
                    "baseline_measurable_count": baseline_measurable,
                },
                confidence=_confidence_for_samples(recent_measurable, baseline_measurable),
                coverage={
                    "recent_measurable_count": recent_measurable,
                    "baseline_measurable_count": baseline_measurable,
                },
                warnings=[],
                source_last_sync=source_last_sync,
            )
        )

    return MonitorRunResult(
        detections=detections,
        stats={
            "regionals_evaluated": len(REGIONALS),
            "regionals_with_data": regionals_with_data,
            "regionals_insufficient_data": regionals_insufficient,
        },
    )
