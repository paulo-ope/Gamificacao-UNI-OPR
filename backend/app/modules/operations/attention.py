"""Pontos de atenção da Visão Geral (`GET /operations/overview/attention-points`).

Regras determinísticas sobre `queries.overview`, `queries.regional_matrix` e `queries.period_open_backlog`
para o recorte da tela (a regra vive no service, o frontend só exibe). Cada achado carrega o número que
o justifica e o limiar usado, para que quem lê consiga conferir.

`evaluate_attention_points` é pura (recebe dicts, devolve dict): os testes cobrem cada regra sem
banco. A resposta também informa quantas regras foram verificadas e quais foram puladas (sem
permissão de SLA, sem janela anterior), porque "nenhum achado" só significa algo se o painel disser
o que olhou.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

SLA_TARGET = 80.0  # mesma meta exibida no gráfico "SLA ponderado por dia" da Visão Geral
SLA_CRITICAL = 70.0
MIN_MEASURED_ORDERS = 30  # abaixo disso a taxa oscila demais para apontar problema
OVERDUE_SHARE_ATTENTION = 20.0
OVERDUE_SHARE_CRITICAL = 40.0
MIN_BACKLOG = 20  # O.S. abertas no período; abaixo disso o percentual não diz nada
COMPLETED_DROP_ATTENTION = 20.0
COMPLETED_DROP_CRITICAL = 35.0
INFLOW_EXCESS_ATTENTION = 10.0
MAX_LISTED_REGIONALS = 3

RULES_TOTAL = (
    "sla_below_target",
    "regional_sla_below_target",
    "overdue_backlog_share",
    "completed_drop",
    "inflow_exceeds_output",
)


# Recomendação padrão de cada regra (caminho "sem IA": texto fixo, versionado no código). É sugestão
# de ação, não diagnóstico - o painel não sabe a causa, só o sintoma. `{regional}` é preenchido nas
# regras por regional. Qualquer regra nova em `RULES_TOTAL` precisa de uma entrada aqui (há teste).
RECOMMENDATIONS = {
    "sla_below_target": (
        "Priorizar as O.S. mais antigas em aberto, revisar a distribuição da fila entre as equipes e "
        "conferir se os assuntos com meta mais curta estão sendo atendidos primeiro."
    ),
    "regional_sla_below_target": (
        "Alinhar com a gestão de {regional}: ver quais assuntos e técnicos concentram as O.S. fora do "
        "prazo e redistribuir a fila ou reforçar a escala."
    ),  # {regional}: as regionais afetadas, separadas por vírgula
    "overdue_backlog_share": (
        "Fazer uma varredura nas O.S. abertas e vencidas: fechar no IXC as que já foram resolvidas, "
        "reagendar as que dependem do cliente e atribuir responsável às paradas."
    ),
    "completed_drop": (
        "Conferir escala, ausências e agenda do período e verificar se houve parada de sistema, falta de "
        "material ou queda de agendamentos que explique a redução."
    ),
    "inflow_exceeds_output": (
        "Reforçar a capacidade (hora extra ou remanejamento entre regionais) ou reduzir a entrada, e "
        "acompanhar o backlog nos próximos dias para não acumular."
    ),
}


def build_recommendations(points: list[dict]) -> list[dict]:
    """Recomendações GERAIS do recorte: uma por regra que disparou (não uma por achado), na ordem de
    gravidade. Para a regra por regional, o texto cita todas as regionais afetadas de uma vez."""
    grouped: dict[str, list[dict]] = {}
    for point in points:
        grouped.setdefault(point["rule"], []).append(point)
    recommendations = []
    for rule, group in grouped.items():
        regionals = [point["regional"] for point in group if point["regional"]]
        recommendations.append(
            {
                "rule": rule,
                "severity": "critical" if any(point["severity"] == "critical" for point in group) else "attention",
                "problem": group[0]["title"] if len(group) == 1 else f"{group[0]['title'].split(' em ')[0]} em {len(group)} regionais",
                "action": RECOMMENDATIONS[rule].format(regional=", ".join(regionals)),
            }
        )
    order = {"critical": 0, "attention": 1}
    recommendations.sort(key=lambda item: (order[item["severity"]], item["rule"]))
    return recommendations


def previous_window(date_from: date, date_to: date, allowed_from: date) -> tuple[date, date] | None:
    """Janela imediatamente anterior e de mesmo tamanho (espelha `previousWindow` do frontend).

    Devolve `None` quando ela cai inteira antes do ano operacional aceito, ou quando seria cortada:
    comparar uma janela menor com uma maior gera queda falsa, então aqui a regra de comparação
    simplesmente não roda."""
    length = (date_to - date_from).days + 1
    prev_to = date_from - timedelta(days=1)
    prev_from = prev_to - timedelta(days=length - 1)
    if prev_from < allowed_from:
        return None
    return prev_from, prev_to


def _measured(item: dict) -> int:
    return (item.get("completed_on_time") or 0) + (item.get("completed_out_of_time") or 0)


def _point(rule: str, severity: str, title: str, detail: str, value: float, threshold: float, regional: str | None = None) -> dict:
    return {
        "rule": rule,
        "severity": severity,
        "title": title,
        "detail": detail,
        "value": round(value, 1),
        "threshold": threshold,
        "regional": regional,
    }


def _pct(value: float) -> str:
    return f"{value:.1f}".replace(".", ",") + "%"


def evaluate_attention_points(
    *,
    overview: dict[str, Any],
    previous_overview: dict[str, Any] | None,
    matrix: dict[str, Any],
    period_backlog: dict[str, Any],
    include_sla: bool,
) -> dict[str, Any]:
    items: list[dict] = []
    skipped: list[str] = []

    # --- SLA geral -------------------------------------------------------------------------
    if include_sla:
        sla = overview.get("sla_rate")
        measured = overview["completed_on_time"] + overview["completed_out_of_time"]
        if sla is not None and measured >= MIN_MEASURED_ORDERS and sla < SLA_TARGET:
            items.append(
                _point(
                    "sla_below_target",
                    "critical" if sla < SLA_CRITICAL else "attention",
                    "SLA abaixo da meta",
                    f"SLA de {_pct(sla)} no período, contra meta de {_pct(SLA_TARGET)} ({measured} O.S. finalizadas com prazo medido).",
                    sla,
                    SLA_TARGET,
                )
            )

        # --- SLA por regional ----------------------------------------------------------------
        weak = [
            item
            for item in matrix["items"]
            if item.get("sla_rate") is not None and _measured(item) >= MIN_MEASURED_ORDERS and item["sla_rate"] < SLA_TARGET
        ]
        weak.sort(key=lambda item: item["sla_rate"])
        for item in weak[:MAX_LISTED_REGIONALS]:
            items.append(
                _point(
                    "regional_sla_below_target",
                    "critical" if item["sla_rate"] < SLA_CRITICAL else "attention",
                    f"SLA abaixo da meta em {item['regional']}",
                    f"{item['regional']} fechou o período com SLA de {_pct(item['sla_rate'])} ({_measured(item)} O.S. medidas), meta {_pct(SLA_TARGET)}.",
                    item["sla_rate"],
                    SLA_TARGET,
                    item["regional"],
                )
            )
    else:
        skipped.extend(["sla_below_target", "regional_sla_below_target"])

    # --- backlog vencido do período ------------------------------------------------------------
    # Só O.S. ABERTAS NO PERÍODO que seguem em aberto (`queries.period_open_backlog`): o estoque
    # total de hoje inclui resíduo administrativo de anos anteriores (Cobrança, conferência) que
    # ninguém fecha no IXC e deixaria o alerta permanentemente vermelho. Esse resíduo fica fora.
    open_count = period_backlog["open"]
    if open_count >= MIN_BACKLOG:
        share = period_backlog["overdue"] / open_count * 100
        if share >= OVERDUE_SHARE_ATTENTION:
            worst = max(period_backlog["by_regional"], key=lambda item: item["overdue"], default=None)
            where = (
                f" A maior parte está em {worst['regional']} ({worst['overdue']} vencidas)."
                if worst and worst["overdue"] > 0
                else ""
            )
            items.append(
                _point(
                    "overdue_backlog_share",
                    "critical" if share >= OVERDUE_SHARE_CRITICAL else "attention",
                    "O.S. do período ainda abertas e vencidas",
                    f"Das {open_count} O.S. abertas no período que seguem em aberto, {period_backlog['overdue']} já passaram da meta ({_pct(share)}).{where}",
                    share,
                    OVERDUE_SHARE_ATTENTION,
                )
            )

    # --- queda de finalizações ---------------------------------------------------------------
    if previous_overview is None:
        skipped.append("completed_drop")
    elif previous_overview["completed"] >= MIN_MEASURED_ORDERS:
        drop = (previous_overview["completed"] - overview["completed"]) / previous_overview["completed"] * 100
        if drop >= COMPLETED_DROP_ATTENTION:
            items.append(
                _point(
                    "completed_drop",
                    "critical" if drop >= COMPLETED_DROP_CRITICAL else "attention",
                    "Queda nas finalizações",
                    f"{overview['completed']} finalizadas, {_pct(drop)} a menos que as {previous_overview['completed']} do período anterior de mesmo tamanho.",
                    drop,
                    COMPLETED_DROP_ATTENTION,
                )
            )

    # --- entrada maior que saída -------------------------------------------------------------
    opened, completed = overview["opened"], overview["completed"]
    if opened >= MIN_MEASURED_ORDERS and completed > 0:
        excess = (opened - completed) / completed * 100
        if excess >= INFLOW_EXCESS_ATTENTION:
            items.append(
                _point(
                    "inflow_exceeds_output",
                    "attention",
                    "Entrou mais O.S. do que saiu",
                    f"{opened} abertas contra {completed} finalizadas (+{_pct(excess)}): o backlog tende a crescer.",
                    excess,
                    INFLOW_EXCESS_ATTENTION,
                )
            )

    order = {"critical": 0, "attention": 1}
    items.sort(key=lambda point: (order[point["severity"]], point["rule"]))
    return {
        "items": items,
        "recommendations": build_recommendations(items),
        "rules_checked": len(RULES_TOTAL) - len(skipped),
        "rules_total": len(RULES_TOTAL),
        "skipped_rules": skipped,
    }


def scope_notes(*, team_models_selected: bool, completed_without_model: int) -> list[str]:
    """Avisos sobre o que as regras de SLA/finalização estão (ou não) contando.

    Com filtro de modelo de equipe, só entram O.S. de responsáveis atribuídos a esses modelos; sem
    filtro, entram todas - inclusive as de responsáveis sem modelo cadastrado, que o filtro com
    "todos os modelos" deixaria de fora e por isso o SLA pode diferir da tela de SLA por modelo."""
    if team_models_selected:
        return [
            "Filtro de modelo de equipe aplicado: SLA e finalizações consideram só O.S. de responsáveis "
            "atribuídos aos modelos selecionados."
        ]
    if completed_without_model > 0:
        return [
            f"SLA e finalizações incluem {completed_without_model} O.S. finalizadas de responsáveis sem modelo de "
            "equipe cadastrado; ao filtrar por modelo de equipe (mesmo com todos), essas ficam de fora e o SLA "
            "pode ser diferente."
        ]
    return []
