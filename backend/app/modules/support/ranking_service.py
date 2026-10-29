"""Ranking MENSAL do Suporte Interno (pedido do usuário, 2026-10-16), pelo "Quadro de Pontuação".

Por colaborador da equipe do Suporte Técnico (`dashboard_macros.SUPPORT_TEAM`), num mês corrente ou fechado. Os
valores abaixo são o PADRÃO; a Configuração > Regras pode alterá-los (`support_rules.RankingRules`) e o ranking de
cada mês usa as regras em vigor no último dia dele:

- Qualidade da avaliação (CSAT do OPA): nota >= 4,5 (meta) vale +10; nota abaixo de 4,0 vale -10; entre as duas, 0;
- TMR (TMR Geral, regra do OPA): até 2 min (meta) +10; acima disso -10 (penalidade única);
- Ligações atendidas (canal `pabx` com o colaborador como primeiro humano), SEMANA a semana (domingo a sábado): cada
  ligação vale +1 até o teto de 12 na semana; quem não bate a meta perde 1 ponto por ligação que faltou (7 ligações =
  +7 -5 = +2). Os dias soltos nas pontas do mês formam uma semana parcial, com meta e teto proporcionais aos dias
  (12 x dias / 7, arredondado para cima); a semana em andamento só pontua depois de encerrada. Mês de 5 semanas
  cheias: teto de 60 pontos.

Desempate: menor TMR, depois maior avaliação ("TMR menor" e "Avaliação individual" são ponto positivo no quadro).
Quem não teve nenhum atendimento no mês fica no fim, sem pontos (férias/folga não deve levar -10 de ligações).
Fora desta versão, por decisão do usuário: O.S. incorreta (-2 por O.S.) e desclassificação por advertência ou falta
injustificada - ainda não existe fonte de dados para elas.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from . import dashboard_macros, feedback_service, opa_overview_service, support_rules
from .opa_filters import OpaAttendanceFilters
from .support_rules import RankingRules

MONTHS_LISTED = 6

TIE_BREAK = "Desempate: menor TMR e, depois, maior avaliação."
NOT_INCLUDED = "Ainda fora da pontuação: O.S. incorreta, advertência e faltas injustificadas (sem fonte de dados)."

DEFAULT_RANKING_RULES = support_rules.DEFAULT_RULES.ranking


def _num(value: float) -> str:
    """4.0 -> "4,0"; 3.9 -> "3,9"; 12.0 -> "12"."""
    if value == int(value):
        return f"{value:.1f}".replace(".", ",") if value < 10 else str(int(value))
    return f"{value:g}".replace(".", ",")


def _points(value: int) -> str:
    return f"{value:+d} {'ponto' if abs(value) == 1 else 'pontos'}"


def _minutes(seconds: float) -> str:
    if seconds % 60 == 0:
        minutes = int(seconds // 60)
        return f"{minutes} {'minuto' if minutes == 1 else 'minutos'}"
    return f"{int(seconds)} segundos"


def rule_lines(rules: RankingRules) -> list[dict[str, Any]]:
    """Texto das regras para a tela, gerado a partir dos valores em vigor (nunca fica diferente da pontuação)."""
    rating, penalty, calls = rules.rating, rules.tmr_penalty, rules.calls
    tmr_lines = [f"Até {_minutes(step.max_seconds)}: {_points(step.points)}" for step in rules.tmr_steps]
    if penalty.flat:
        tmr_lines.append(f"Acima de {_minutes(penalty.after_seconds)}: {_points(penalty.points)}")
    else:
        tmr_lines.append(f"Acima de {_minutes(penalty.after_seconds)}: {_points(penalty.points)} a cada {_minutes(penalty.block_seconds)} excedidos")
    return [
        {
            "key": "rating",
            "label": "Qualidade da avaliação",
            "lines": [
                f"Nota a partir de {_num(rating.good_min)}: {_points(rating.good_points)}",
                f"Nota até {_num(rating.bad_max)}: {_points(rating.bad_points)}",
                f"Entre {_num(rating.bad_max)} e {_num(rating.good_min)}: 0 ponto",
            ],
        },
        {"key": "tmr", "label": "TMR (tempo médio de resposta)", "lines": tmr_lines},
        {
            "key": "calls",
            "label": "Ligações atendidas",
            "lines": [
                f"Cada ligação atendida na semana: {_points(calls.call_points)}, até {calls.week_target} por semana (teto)",
                f"Cada ligação que faltou para a meta da semana: {_points(calls.missing_penalty)}",
                "Dias soltos nas pontas do mês formam uma semana parcial, com meta e teto proporcionais aos dias.",
            ],
        },
    ]


def rating_points(value: float | None, rules: RankingRules = DEFAULT_RANKING_RULES) -> int:
    if value is None:
        return 0
    if value >= rules.rating.good_min:
        return rules.rating.good_points
    if value <= rules.rating.bad_max:
        return rules.rating.bad_points
    return 0


def tmr_points(seconds: float | None, rules: RankingRules = DEFAULT_RANKING_RULES) -> int:
    if seconds is None:
        return 0
    for step in rules.tmr_steps:
        if seconds <= step.max_seconds:
            return step.points
    penalty = rules.tmr_penalty
    if seconds <= penalty.after_seconds:
        return 0  # entre o limite da última faixa e o início da penalidade
    if penalty.flat:
        return penalty.points
    return penalty.points * math.ceil((seconds - penalty.after_seconds) / penalty.block_seconds)


def week_target(days: int, rules: RankingRules = DEFAULT_RANKING_RULES) -> int:
    """Meta (e teto) de ligações de uma semana de `days` dias: a cheia vale `week_target`; a parcial é proporcional."""
    return math.ceil(rules.calls.week_target * days / 7 - 1e-9)


def calls_points(weeks: list[tuple[int, int]], rules: RankingRules = DEFAULT_RANKING_RULES) -> int:
    """Soma das semanas, cada uma como (ligações, meta): ligações até a meta valem `call_points`; as que faltaram
    para a meta descontam `missing_penalty`."""
    total = 0
    for calls, target in weeks:
        total += min(calls, target) * rules.calls.call_points + max(target - calls, 0) * rules.calls.missing_penalty
    return total


def scoring_weeks(date_from: date, date_to: date, reference: date) -> list[tuple[date, date]]:
    """Semanas dom-sáb de [date_from, date_to] já encerradas antes de `reference`; as pontas do mês viram semanas
    parciais (recortadas no mês)."""
    weeks = []
    cursor = date_from
    while cursor <= date_to:
        end = min(cursor + timedelta(days=(5 - cursor.weekday()) % 7), date_to)  # próximo sábado
        if end < reference:
            weeks.append((cursor, end))
        cursor = end + timedelta(days=1)
    return weeks


def month_bounds(day: date) -> tuple[date, date]:
    """Primeiro e último dia do mês que contém `day`."""
    start = day.replace(day=1)
    next_start = (start + timedelta(days=32)).replace(day=1)
    return start, next_start - timedelta(days=1)


def listed_months(reference: date) -> list[dict[str, Any]]:
    """O mês de `reference` (em andamento) e os anteriores, o mais recente primeiro, para o seletor da tela."""
    months = []
    cursor = reference.replace(day=1)
    for _ in range(MONTHS_LISTED):
        start, end = month_bounds(cursor)
        months.append({"date_from": start, "date_to": end})
        cursor = (start - timedelta(days=1)).replace(day=1)
    return months


def _sort_key(row: dict[str, Any]) -> tuple:
    tmr = row["tmr"]["value"]
    rating = row["rating"]["value"]
    return (
        0 if row["active"] else 1,
        -(row["total_points"] or 0),
        tmr if tmr is not None else float("inf"),
        -(rating if rating is not None else float("-inf")),
        row["name"].lower(),
    )


def _member_row(
    db: Session, option: dict[str, str], date_from: date, date_to: date, weeks: list[tuple[date, date]], rules: RankingRules
) -> dict[str, Any]:
    attendant_id = option["value"]
    filters = OpaAttendanceFilters(date_from=date_from, date_to=date_to, attendant_id=attendant_id)
    metrics = opa_overview_service.overview_metrics(db, filters)
    calls = feedback_service.phone_calls_answered(db, attendant_id, OpaAttendanceFilters(date_from=date_from, date_to=date_to))
    active = metrics["total_attendances"] > 0 or calls > 0
    week_results: list[tuple[int, int]] = []
    if active:
        for week_from, week_to in weeks:
            week_calls = feedback_service.phone_calls_answered(db, attendant_id, OpaAttendanceFilters(date_from=week_from, date_to=week_to))
            week_results.append((week_calls, week_target((week_to - week_from).days + 1, rules)))
    on_target = sum(1 for week_calls, target in week_results if week_calls >= target)
    calls_detail = f"{on_target} de {len(weeks)} semanas na meta de ligações ({calls_points(week_results, rules):+d} pontos)"

    rating = metrics["average_rating"]
    tmr = metrics["average_tmr_effective_seconds"]
    coverage = dashboard_macros.time_coverage(db, filters) if active else None
    tmr_partial = bool(coverage) and tmr is not None and (coverage["percentage"] or 0) < dashboard_macros.MIN_COVERAGE_PERCENT

    row = {
        "attendant_id": attendant_id,
        "name": option["label"],
        "active": active,
        "attendances": metrics["total_attendances"],
        "rating": {"value": rating, "points": rating_points(rating, rules) if active else 0, "partial": False},
        "tmr": {"value": tmr, "points": tmr_points(tmr, rules) if active else 0, "partial": tmr_partial},
        "calls": {"value": calls, "points": calls_points(week_results, rules) if active else 0, "partial": False, "detail": calls_detail},
    }
    row["total_points"] = row["rating"]["points"] + row["tmr"]["points"] + row["calls"]["points"] if active else None
    return row


def monthly_ranking(db: Session, *, month: date, reference: date) -> dict[str, Any]:
    """Ranking do mês de `month` (qualquer dia do mês), com as regras em vigor no último dia dele."""
    date_from, date_to = month_bounds(month)
    rules = support_rules.ranking_rules_for_month(db, date_to)
    weeks = scoring_weeks(date_from, date_to, reference)
    rows = [_member_row(db, option, date_from, date_to, weeks, rules) for option in dashboard_macros.support_team_options(db)]
    rows.sort(key=_sort_key)
    position = 0
    for row in rows:
        if row["active"]:
            position += 1
            row["position"] = position
        else:
            row["position"] = None
    return {
        "date_from": date_from,
        "date_to": date_to,
        "months": listed_months(reference),
        "rows": rows,
        "rules": rule_lines(rules),
        "tie_break": TIE_BREAK,
        "not_included": NOT_INCLUDED,
    }
