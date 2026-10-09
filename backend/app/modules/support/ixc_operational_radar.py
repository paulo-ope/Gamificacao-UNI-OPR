"""Radar de incidente da TV: SÓ protocolos operacionais, SÓ de hoje.

"Protocolo operacional" = atendimento do IXC com assunto 90 ("Registro de Atendimento Operacional"),
o mesmo assunto que o Suporte Interno N1 usa (`ixc_n1.N1_OPERATIONAL_SUBJECT_ID`). Os demais assuntos
(financeiro, renovação, plano, instalação...) não indicam incidente de rede e ficam de fora - antes o
radar contava tudo e 40% do que ele enxergava era protocolo financeiro.

Referência ("esperado"): a MESMA janela do dia, nas últimas `BASELINE_WEEKS` semanas, no MESMO dia da
semana. Comparar com "o mesmo dia do mês" ou com os 3 dias anteriores misturava sábado/domingo com dia
útil e inflava os percentuais. Semana sem nenhum protocolo operacional no dia inteiro é lacuna de
importação (já houve 4 dias sem nada em setembro) e não entra como "zero" na média.

HORÁRIO: o IXC entrega `data_criacao` em hora LOCAL, sem fuso, e a importação grava esse horário como
se fosse UTC (`ixc_ticket_ingestion._parse_ixc_datetime`). Ou seja, `created_at` guarda a HORA DE PAREDE de
Porto Velho com a etiqueta "UTC". Por isso este módulo trabalha inteiro em "hora de parede" - o relógio
de agora é convertido para Porto Velho UMA vez e depois comparado direto com `created_at`, SEM nova
conversão de fuso (converter de novo deslocava tudo em 4 horas: "0 na última hora", dia pela metade).
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .ixc_n1 import N1_OPERATIONAL_SUBJECT_ID
from .models import SupportIxcTicket
from .opa_filters import SUPPORT_TIMEZONE

OPERATIONAL_SUBJECT_ID = N1_OPERATIONAL_SUBJECT_ID
BASELINE_WEEKS = 4
BURST_WINDOWS_HOURS = (1, 2, 6)

# Piso e margens: cidade pequena com 2-3 protocolos vira "+100%" por ruído e não é incidente.
MIN_CITY_TICKETS = 5
CITY_RATIO = 1.5
CITY_MIN_EXCESS = 3
CITIES_LIMIT = 3
MIN_BURST_TICKETS = 3
# Ritmo do dia (total operacional até agora contra o esperado até esta hora).
PACE_ATTENTION_RATIO = 1.25
PACE_CRITICAL_RATIO = 1.5
PACE_MIN_EXCESS = 5


def _wall(value: datetime) -> datetime:
    """`created_at` (hora de parede com etiqueta UTC) normalizado para aware-UTC, sem converter fuso."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=timezone.utc)


def _operational_rows(db: Session, start: datetime, end: datetime) -> list[tuple[datetime, str | None]]:
    rows = db.execute(
        select(SupportIxcTicket.created_at, SupportIxcTicket.city).where(
            SupportIxcTicket.subject_id == OPERATIONAL_SUBJECT_ID,
            SupportIxcTicket.created_at >= start,
            SupportIxcTicket.created_at < end,
        )
    ).all()
    return [(_wall(created_at), city) for created_at, city in rows if created_at is not None]


def _day_has_data(db: Session, day: date) -> bool:
    start = _day_start(day)
    return bool(
        db.scalar(
            select(func.count(SupportIxcTicket.id)).where(
                SupportIxcTicket.subject_id == OPERATIONAL_SUBJECT_ID,
                SupportIxcTicket.created_at >= start,
                SupportIxcTicket.created_at < start + timedelta(days=1),
            )
        )
    )


def _count_between(rows: list[tuple[datetime, str | None]], start: datetime, end: datetime) -> int:
    return sum(1 for created_at, _ in rows if start <= created_at < end)


def _burst_limit(samples: list[int]) -> tuple[float, float]:
    """(esperado, limite): `max(esperado + 2 desvios, esperado × 1,35, esperado + 2)` - o mesmo critério
    de `ixc_ticket_baseline.detect_bursts`, para a rajada daqui e a da tela do IXC não discordarem de regra."""
    expected = sum(samples) / len(samples)
    deviation = statistics.pstdev(samples) if len(samples) > 1 else 0.0
    return expected, max(expected + 2 * deviation, expected * 1.35, expected + 2)


def build_radar(db: Session, now: datetime) -> dict[str, Any]:
    # Agora em hora de parede de Porto Velho, com a MESMA etiqueta de `created_at` (UTC) - ver o cabeçalho.
    now_local = _wall(now).astimezone(SUPPORT_TIMEZONE).replace(tzinfo=timezone.utc)
    today = now_local.date()
    today_start = _day_start(today)
    elapsed = now_local - today_start

    today_rows = _operational_rows(db, today_start, now_local)

    # Mesmo dia da semana, últimas semanas, só as com dado (lacuna de importação não é "zero").
    history: dict[date, list[tuple[datetime, str | None]]] = {}
    for week in range(1, BASELINE_WEEKS + 1):
        day = today - timedelta(weeks=week)
        if not _day_has_data(db, day):
            continue
        start = _day_start(day)
        history[day] = _operational_rows(db, start, start + elapsed)
    weeks_used = len(history)

    observed_today = len(today_rows)
    expected_today = sum(len(rows) for rows in history.values()) / weeks_used if weeks_used else None

    # --- ritmo do dia -----------------------------------------------------------------------
    pace_status = "no_baseline"
    ratio = None
    if expected_today is not None:
        ratio = round(observed_today / expected_today, 2) if expected_today > 0 else None
        excess = observed_today - expected_today
        if ratio is not None and ratio >= PACE_CRITICAL_RATIO and excess >= PACE_MIN_EXCESS:
            pace_status = "critical"
        elif ratio is not None and ratio >= PACE_ATTENTION_RATIO and excess >= PACE_MIN_EXCESS:
            pace_status = "attention"
        else:
            pace_status = "normal"
    pace = {
        "observed_today": observed_today,
        "expected_so_far": round(expected_today, 1) if expected_today is not None else None,
        "ratio": ratio,
        "status": pace_status,
    }

    # --- rajada: janelas das últimas horas, sempre dentro de hoje ---------------------------
    bursts: list[dict[str, Any]] = []
    for hours in BURST_WINDOWS_HOURS:
        window_start = max(today_start, now_local - timedelta(hours=hours))
        offset_start = window_start - today_start
        observed = _count_between(today_rows, window_start, now_local)
        if not weeks_used:
            bursts.append({"window": f"{hours}h", "observed": observed, "expected": None, "ratio": None, "active": False, "basis": "none"})
            continue
        samples = [
            _count_between(rows, _day_start(day) + offset_start, _day_start(day) + elapsed)
            for day, rows in history.items()
        ]
        expected, upper_limit = _burst_limit(samples)
        bursts.append(
            {
                "window": f"{hours}h",
                "observed": observed,
                "expected": round(expected, 1),
                "ratio": round(observed / expected, 2) if expected > 0 else None,
                "active": observed > upper_limit and observed >= MIN_BURST_TICKETS,
                "basis": "same_weekday",
            }
        )

    # --- cidades fora do esperado hoje ------------------------------------------------------
    cities: list[dict[str, Any]] = []
    if weeks_used:
        today_by_city = Counter(city for _, city in today_rows if city)
        history_by_city: dict[str, list[int]] = defaultdict(list)
        for rows in history.values():
            counts = Counter(city for _, city in rows if city)
            for city in set(today_by_city) | set(counts):
                history_by_city[city].append(counts.get(city, 0))
        for city, count in today_by_city.items():
            expected = sum(history_by_city[city]) / weeks_used
            excess = count - expected
            if count >= MIN_CITY_TICKETS and excess >= CITY_MIN_EXCESS and count >= expected * CITY_RATIO:
                cities.append(
                    {
                        "city": city,
                        "today_count": count,
                        "expected": round(expected, 1),
                        "deviation_pct": round(excess / expected * 100, 1) if expected > 0 else None,
                    }
                )
        cities.sort(key=lambda item: item["today_count"] - item["expected"], reverse=True)

    return {
        "scope": "operational",
        "baseline_weeks_used": weeks_used,
        "pace": pace,
        "bursts": bursts,
        "cities_at_risk": cities[:CITIES_LIMIT],
    }
