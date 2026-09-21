"""Fase 5 do plano de evolução analítica do Atendimento IXC (2026-09-15): camada de consumo por
IA, montada em cima das Fases 1-4 (nenhum cálculo novo aqui, só combinação e resumo) - "o que está
anormal AGORA" (`build_brief`) e "quais escopos têm sinal disparado" (`list_signals`), no formato
padronizado do item 10 do plano (`heuristic, status, severity, reason_codes`).

Exposto só via MCP (`opr_ixc_brief`/`opr_ixc_signals`, ver `mcp_connector/server.py`), mesmo padrão
de `opr_support_overview/breakdowns/timeseries` - este módulo NÃO segue o "response_mode"/token-
scope pesado de `ai/router.py` (`search_orders`, `AiSearchRequest`) porque essa máquina existe pra
expor O.S. individuais via API key externa; aqui, como no SGP Suporte, o consumidor é sempre um
usuário autenticado com `support:read`, o mesmo dado agregado que a tela já mostra."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.services.regional import REGIONAL_CODE_MAP, is_valid_regional

from .ixc_ticket_baseline import BURST_WINDOWS_HOURS, detect_bursts
from .ixc_ticket_context import resolve_context
from .ixc_ticket_momentum import daily_momentum
from .ixc_ticket_os_conversion import os_conversion_rate

# Um motivo só vira `DRIVER_CONCENTRATION` (reason_code) se explicar uma fatia relevante do
# excesso - abaixo disso, "o maior motivo" pode ser só o mais frequente, sem concentrar nada
# (mesmo raciocínio de `DAY_ABOVE_EXPECTED_RATIO` em momentum: limiar, não zero).
DRIVER_CONCENTRATION_THRESHOLD_PCT = 40.0

# Janela padrão do brief/signals - "os últimos 7 dias", não o mês-calendário da Visão Geral nem o
# período livre do drill-down: uma janela fixa e curta é o que faz sentido pra "o que está
# acontecendo agora", sem exigir que o consumidor (IA) escolha um período.
BRIEF_WINDOW_DAYS = 7

# Só entram no brief/signals as janelas de burst mais curtas (1h/2h) - a de 6h (BURST_WINDOWS_HOURS
# tem as três) é mais útil na tela interativa; aqui o objetivo é "started a burst", não decompor.
SIGNAL_BURST_WINDOWS_HOURS: tuple[int, ...] = BURST_WINDOWS_HOURS[:2]

# Uma regional só vira "sinal" se severity indicar algo fora do normal, ou se tiver aceleração
# sustentada, ou um burst ativo - severidade "dentro_da_curva"/"sem_dado" sozinha não é sinal.
_SIGNAL_SEVERITIES = {"critico", "em_melhora"}


def _window(reference_date: date | None) -> tuple[date, date]:
    reference_date = reference_date or date.today()
    return reference_date - timedelta(days=BRIEF_WINDOW_DAYS - 1), reference_date


def _valid_regionals() -> list[str]:
    return [r for r in dict.fromkeys(REGIONAL_CODE_MAP.values()) if is_valid_regional(r)]


def _reason_codes(*, context: dict[str, Any], momentum: dict[str, Any], bursts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cada código vem acompanhado dos NÚMEROS que o sustentam - pedido explícito do usuário
    (2026-09-17, item 6): "a IA deve conseguir entender o motivo do sinal lendo somente aquele
    item", sem precisar cruzar com outro payload pra saber o "porquê" numérico."""
    codes: list[dict[str, Any]] = []
    if context["severity"] in ("critico", "em_melhora") and context["effective_deviation_pct"] is not None:
        codes.append(
            {
                "code": "HIGH_DEVIATION" if context["severity"] == "critico" else "IMPROVING_DEVIATION",
                "current": context["ticket_count"],
                "expected": context["expected"],
                "delta_pct": context["effective_deviation_pct"],
                "basis": context["severity_basis"],
            }
        )
    if momentum["trend"] in ("accelerating", "decelerating"):
        codes.append(
            {
                "code": "MOMENTUM_ACCELERATING" if momentum["trend"] == "accelerating" else "MOMENTUM_DECELERATING",
                "recent_avg": momentum["recent_avg"],
                "previous_avg": momentum["previous_avg"],
                "change_pct": momentum["change_pct"],
            }
        )
    if momentum["consecutive_days_above_expected"] >= 3:
        codes.append({"code": "PERSISTENT_ABOVE_EXPECTED", "consecutive_days": momentum["consecutive_days_above_expected"]})
    for burst in bursts:
        if burst["active"]:
            codes.append(
                {
                    "code": "BURST_ACTIVE",
                    "window": burst["window"],
                    "current": burst["observed"],
                    "expected": burst["expected"],
                    "ratio": burst["ratio"],
                }
            )
    top_driver = context["drivers"][0] if context["drivers"] else None
    if top_driver is not None and top_driver["contribution_pct"] >= DRIVER_CONCENTRATION_THRESHOLD_PCT:
        codes.append(
            {
                "code": "DRIVER_CONCENTRATION",
                "subject": top_driver["subject_name"],
                "contribution_pct": top_driver["contribution_pct"],
            }
        )
    return codes


def build_brief(db: Session, *, regional: str | None = None, reference_date: date | None = None) -> dict[str, Any]:
    """"O que está anormal agora?" - contexto agregado (últimos `BRIEF_WINDOW_DAYS` dias),
    momentum, bursts e conversão em O.S. de UM escopo (a operação inteira, se `regional` for
    `None`, ou uma regional específica). Consolida tudo o que antes exigia chamadas separadas
    (item 2/3/7 da correção, 2026-09-17) - nenhum cálculo novo aqui, só combinação: reaproveita
    `context["drivers"]` (lista completa, não só o principal) em vez de decompor de novo."""
    date_from, date_to = _window(reference_date)
    context = resolve_context(db, date_from=date_from, date_to=date_to, regional=regional)
    momentum = daily_momentum(db, regional=regional, reference_date=reference_date)
    bursts = detect_bursts(
        db,
        scope_type="regional" if regional else "global",
        scope_id=regional,
        windows_hours=SIGNAL_BURST_WINDOWS_HOURS,
    )
    # OS_CONVERSION_V1 usa a MESMA janela do brief (item 7: "integre os indicadores relevantes ao
    # brief consolidado") - não recalcula nada, só chama a função que já existe.
    os_conversion = os_conversion_rate(db, date_from=date_from, date_to=date_to, regional=regional)
    reason_codes = _reason_codes(context=context, momentum=momentum, bursts=bursts)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "context_key": context["context_key"],
        "period": {"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
        "scope": {"type": "regional" if regional else "global", "id": regional},
        "status": context["severity"],
        "severity_basis": context["severity_basis"],
        "ticket_count": context["ticket_count"],
        "expected": context["expected"],
        "deviation_pct": context["deviation_pct"],
        "peers_deviation_pct": context["peers_deviation_pct"],
        "effective_deviation_pct": context["effective_deviation_pct"],
        "tickets_per_1000_contracts": context["tickets_per_1000_contracts"],
        "top_driver": context["top_driver"],
        "drivers": context["drivers"][:5],
        "geographic_concentration": context["geographic_concentration"],
        "reach": context["reach"],
        "momentum": momentum,
        "bursts": bursts,
        "os_conversion": os_conversion,
        "reason_codes": reason_codes,
        "drill": {"next_dimension": context["next_dimension"]},
    }


def list_signals(db: Session, *, reference_date: date | None = None) -> list[dict[str, Any]]:
    """Uma linha por REGIONAL com algum sinal disparado (severidade crítica/em melhora - por
    histórico OU por pares -, momentum em aceleração/desaceleração sustentada, ou burst ativo) -
    regional "dentro da curva" e sem nada acontecendo não aparece na lista (a pergunta é "onde
    olhar", não "todas as regionais"). Cada item já traz `reason_codes` com evidência numérica
    (item 6) - não é preciso chamar `build_brief` de novo só pra entender o "porquê"."""
    date_from, date_to = _window(reference_date)
    signals: list[dict[str, Any]] = []
    for regional in _valid_regionals():
        context = resolve_context(db, date_from=date_from, date_to=date_to, regional=regional)
        momentum = daily_momentum(db, regional=regional, reference_date=reference_date)
        bursts = detect_bursts(
            db, scope_type="regional", scope_id=regional, windows_hours=SIGNAL_BURST_WINDOWS_HOURS
        )
        reason_codes = _reason_codes(context=context, momentum=momentum, bursts=bursts)
        is_signal = (
            context["severity"] in _SIGNAL_SEVERITIES
            or momentum["consecutive_days_above_expected"] >= 3
            or any(burst["active"] for burst in bursts)
        )
        if not is_signal:
            continue
        signals.append(
            {
                "context_key": context["context_key"],
                "scope": {"type": "regional", "id": regional},
                "severity": context["severity"],
                "severity_basis": context["severity_basis"],
                "ticket_count": context["ticket_count"],
                "expected": context["expected"],
                "deviation_pct": context["deviation_pct"],
                "effective_deviation_pct": context["effective_deviation_pct"],
                "tickets_per_1000_contracts": context["tickets_per_1000_contracts"],
                "top_driver": context["top_driver"],
                "drivers": context["drivers"][:5],
                "geographic_concentration": context["geographic_concentration"],
                "reach": context["reach"],
                "momentum_trend": momentum["trend"],
                "consecutive_days_above_expected": momentum["consecutive_days_above_expected"],
                "burst_active": any(burst["active"] for burst in bursts),
                "reason_codes": reason_codes,
                "drill": {"next_dimension": context["next_dimension"]},
            }
        )

    def _rank(signal: dict[str, Any]) -> tuple[int, float]:
        # Crítico primeiro, depois por magnitude do desvio (maior primeiro) - mesma lógica de
        # ordenação de `_priorities_for_scopes` (Visão Geral).
        severity_rank = 0 if signal["severity"] == "critico" else 1
        # `effective_deviation_pct` (histórico OU pares) - `deviation_pct` sozinho ficaria `None`
        # justamente nos casos que o fallback de pares existe pra resolver.
        deviation = signal["effective_deviation_pct"] or 0.0
        return (severity_rank, -abs(deviation))

    signals.sort(key=_rank)
    return signals
