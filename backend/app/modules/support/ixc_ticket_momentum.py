"""Fase 4 do plano de evolução analítica do Atendimento IXC (2026-09-15): `MOMENTUM_V1` -
tendência recente (últimos dias) de um escopo, complementar ao desvio pontual já calculado em
`ixc_ticket_overview.py`/`ixc_ticket_context.py`. Responde uma pergunta diferente: não "está fora
da curva HOJE", mas "está piorando, melhorando ou estável nos últimos dias" - útil pra separar um
pico de um dia (ruído ou incidente pontual, já coberto por `ixc_ticket_baseline.detect_bursts`) de
uma escalada sustentada (vários dias seguidos acima do esperado)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .ixc_ticket_queries import _apply_extra_filters, _apply_period
from .models import SupportIxcTicket

# Quantas semanas anteriores entram na expectativa de cada dia (mesmo dia-da-semana) - mesmo valor
# de `ixc_ticket_baseline.BASELINE_WEEKS_DEFAULT`, não importado de lá de propósito (cada
# heurística deste módulo é uma função pura independente, item 7 do plano - acoplar as duas faria
# uma mudança na janela do burst mudar o momentum sem ninguém perceber).
BASELINE_WEEKS_DEFAULT = 8

# Janela "recente" vs. "anterior" comparada pra tendência - 3 dias suaviza ruído de dia-da-semana
# sem diluir uma escalada real que já dura menos de uma semana.
RECENT_WINDOW_DAYS = 3

# Quantos dias pra trás procurar "dias consecutivos acima do esperado", a partir de ontem.
CONSECUTIVE_DAYS_LOOKBACK = 14

# Mesmo vocabulário de limiar da Visão Geral (`ixc_ticket_overview.CRITICAL_DEVIATION_PCT`/
# `IMPROVING_DEVIATION_PCT`) - reaproveita os NÚMEROS por consistência de leitura entre as duas
# heurísticas, mas são constantes próprias (não importadas) porque respondem perguntas diferentes
# (desvio pontual vs. variação dia-a-dia) e podem divergir no futuro sem quebrar a outra.
MOMENTUM_ACCELERATING_PCT = 20.0
MOMENTUM_DECELERATING_PCT = -10.0

# Um dia só "conta" como acima do esperado se exceder o esperado por uma margem real - mesmo
# espírito do `upper_limit` de `ixc_ticket_baseline.detect_bursts`, versão mais simples (sem
# desvio-padrão por dia, que exigiria mais amostra do que faz sentido pedir aqui).
DAY_ABOVE_EXPECTED_RATIO = 1.2
DAY_ABOVE_EXPECTED_MARGIN = 2.0


def _daily_counts(
    db: Session,
    *,
    regional: str | None,
    city: str | None,
    subject_id: str | None,
    sector_id: str | None,
    date_from: date,
    date_to: date,
) -> dict[date, int]:
    query = select(func.date(SupportIxcTicket.created_at), func.count(SupportIxcTicket.id)).group_by(
        func.date(SupportIxcTicket.created_at)
    )
    if regional:
        query = query.where(SupportIxcTicket.regional == regional)
    if city:
        query = query.where(SupportIxcTicket.city == city)
    query = _apply_period(query, SupportIxcTicket.created_at, date_from, date_to)
    query = _apply_extra_filters(query, subject_id=subject_id, sector_id=sector_id)

    result: dict[date, int] = {}
    for raw_date, count in db.execute(query).all():
        # Mesma normalização Postgres (date de verdade) vs. SQLite (string "YYYY-MM-DD") já usada
        # em `ixc_ticket_overview.daily_incidence_series`.
        d = raw_date if isinstance(raw_date, date) else date.fromisoformat(raw_date)
        result[d] = count
    return result


def daily_momentum(
    db: Session,
    *,
    regional: str | None = None,
    city: str | None = None,
    subject_id: str | None = None,
    sector_id: str | None = None,
    reference_date: date | None = None,
) -> dict[str, Any]:
    """`recent_avg`/`previous_avg`: média diária dos últimos `RECENT_WINDOW_DAYS` dias completos
    (terminando ontem - hoje é excluído, dia parcial) contra os `RECENT_WINDOW_DAYS` dias
    imediatamente anteriores. `consecutive_days_above_expected`: quantos dias seguidos, contando
    de ontem pra trás, cada dia superou seu próprio esperado (média do mesmo dia-da-semana nas
    `BASELINE_WEEKS_DEFAULT` semanas anteriores) - pára no primeiro dia que não superar."""
    reference_date = reference_date or date.today()
    yesterday = reference_date - timedelta(days=1)
    history_start = yesterday - timedelta(days=BASELINE_WEEKS_DEFAULT * 7 + CONSECUTIVE_DAYS_LOOKBACK)

    counts = _daily_counts(
        db, regional=regional, city=city, subject_id=subject_id, sector_id=sector_id,
        date_from=history_start, date_to=yesterday,
    )

    def count_on(day: date) -> int:
        return counts.get(day, 0)

    recent_days = [yesterday - timedelta(days=i) for i in range(RECENT_WINDOW_DAYS)]
    previous_days = [yesterday - timedelta(days=i) for i in range(RECENT_WINDOW_DAYS, RECENT_WINDOW_DAYS * 2)]
    recent_avg = sum(count_on(d) for d in recent_days) / RECENT_WINDOW_DAYS
    previous_avg = sum(count_on(d) for d in previous_days) / RECENT_WINDOW_DAYS
    change_pct = round((recent_avg - previous_avg) / previous_avg * 100, 1) if previous_avg else None

    def expected_for(day: date) -> float:
        samples = [count_on(day - timedelta(weeks=week)) for week in range(1, BASELINE_WEEKS_DEFAULT + 1)]
        return sum(samples) / len(samples) if samples else 0.0

    consecutive = 0
    cursor = yesterday
    for _ in range(CONSECUTIVE_DAYS_LOOKBACK):
        expected = expected_for(cursor)
        threshold = max(expected * DAY_ABOVE_EXPECTED_RATIO, expected + DAY_ABOVE_EXPECTED_MARGIN)
        if expected > 0 and count_on(cursor) > threshold:
            consecutive += 1
            cursor -= timedelta(days=1)
        else:
            break

    if change_pct is None:
        trend = "sem_dado"
    elif change_pct >= MOMENTUM_ACCELERATING_PCT:
        trend = "accelerating"
    elif change_pct <= MOMENTUM_DECELERATING_PCT:
        trend = "decelerating"
    else:
        trend = "stable"

    return {
        "recent_avg": round(recent_avg, 2),
        "previous_avg": round(previous_avg, 2),
        "change_pct": change_pct,
        "consecutive_days_above_expected": consecutive,
        "trend": trend,
    }
