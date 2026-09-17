"""Monitor de picos de atendimento IXC (item 9 do plano de evolução analítica do Atendimento IXC:
"escalonamento automático quando bursts detectados"). Não cria canal de alerta/notificação novo -
integra o `BURST_V1` (já existia, só era consultado sob demanda pelo endpoint
`/support/ixc/analytics/bursts`) no MESMO motor de alertas/incidentes que já escala SLA,
pressão operacional e incidente coletivo de rede pro cockpit do UNI Intelligence (dedupe por
`dedupe_key`, lifecycle NEW -> CONFIRMED, auto-resolve por `resolve_after_misses` ciclos sem
redetecção - ver `alerts.sync_alerts_for_monitor`).

Não recalcula nada: só chama `ixc_ticket_baseline.detect_bursts` (mesma função do endpoint) pra
cada escopo (operação inteira + cada regional válida) e traduz toda janela `active=True` numa
`MonitorDetection`."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.modules.support.ixc_ticket_baseline import detect_bursts
from app.services.regional import REGIONAL_CODE_MAP, is_valid_regional

from ..types import MonitorDetection, MonitorRunResult

# Só escalona a partir da janela de 2h em diante - a de 1h sozinha (também computada pelo
# endpoint, ver BURST_WINDOWS_HOURS em ixc_ticket_baseline.py) é sensível demais a ruído de
# minuto pra virar alerta; um pico real e sustentado também aparece na janela de 2h/6h.
ESCALATED_WINDOWS_HOURS = (2, 6)


def _severity_for_ratio(ratio: float | None, observed: int) -> str:
    if ratio is not None:
        if ratio >= 3.0:
            return "CRITICAL"
        if ratio >= 2.0:
            return "HIGH"
        return "MEDIUM"
    # `expected` era ~0 (baseline nunca viu atendimento nesses slots) - "vezes o esperado" não
    # tem sentido aqui, a severidade cai só sobre o volume observado.
    return "HIGH" if observed >= 10 else "MEDIUM"


def _scope_label(scope_type: str, scope_id: str | None) -> str:
    return "operação inteira" if scope_type == "global" else (scope_id or "regional desconhecida")


def _detections_for_scope(
    db: Session, *, scope_type: str, scope_id: str | None, reference_time: datetime
) -> list[MonitorDetection]:
    windows = detect_bursts(
        db, scope_type=scope_type, scope_id=scope_id, reference_time=reference_time, windows_hours=ESCALATED_WINDOWS_HOURS
    )
    detections: list[MonitorDetection] = []
    for item in windows:
        if not item["active"]:
            continue
        ratio = item["ratio"]
        dedupe_key = f"ixc_ticket_burst:{scope_type}:{scope_id or 'global'}:{item['window']}"
        summary = (
            f"{item['observed']} atendimentos na janela de {item['window']} em {_scope_label(scope_type, scope_id)}"
            + (f", {ratio:.2f}x o esperado ({item['expected']:.1f})" if ratio is not None else f" (esperado ~{item['expected']:.1f})")
            + "."
        )
        detections.append(
            MonitorDetection(
                dedupe_key=dedupe_key,
                kind="ALERT",
                alert_type="IXC_TICKET_BURST",
                severity=_severity_for_ratio(ratio, item["observed"]),
                title=f"Pico de atendimento IXC - {_scope_label(scope_type, scope_id)} ({item['window']})",
                summary=summary,
                regional=scope_id if scope_type == "regional" else None,
                scope={"scope_type": scope_type, "scope_id": scope_id, "window": item["window"]},
                recommended_action="validar causa comum (rompimento/queda coletiva) antes de tratar atendimento por atendimento",
                evidence=dict(item),
                confidence=0.85 if ratio is not None else 0.6,
            )
        )
    return detections


def run_ixc_ticket_burst_monitor(db: Session, *, reference_time: datetime | None = None) -> MonitorRunResult:
    reference_time = reference_time or datetime.now()
    detections: list[MonitorDetection] = list(
        _detections_for_scope(db, scope_type="global", scope_id=None, reference_time=reference_time)
    )

    regionals = [regional for regional in dict.fromkeys(REGIONAL_CODE_MAP.values()) if is_valid_regional(regional)]
    for regional in regionals:
        detections.extend(_detections_for_scope(db, scope_type="regional", scope_id=regional, reference_time=reference_time))

    return MonitorRunResult(
        detections=detections,
        stats={"regionals_evaluated": len(regionals), "scopes_evaluated": len(regionals) + 1},
    )
