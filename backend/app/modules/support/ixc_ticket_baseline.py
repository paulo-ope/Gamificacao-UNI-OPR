"""Fase 4 do plano de evolução analítica do Atendimento IXC (2026-09-15): baseline pré-computado
de atendimentos esperados por hora-do-dia/dia-da-semana (`support_ixc_hourly_baselines`) e
detecção de picos (`BURST_V1`) em cima dele.

Existe porque comparar "quantos atendimentos chegaram na última hora" contra um valor esperado
exige uma média (e desvio-padrão) por hora-do-dia/dia-da-semana das últimas N semanas - caro
recalcular a cada request (a mesma pergunta que motivou `OperationBacklogSnapshot`, aqui aplicada
a uma média móvel em vez de uma fotografia). `recompute_all_hourly_baselines` é chamado 1x/dia por
`run_ixc_ticket_baseline_loop` (ligado em `main.py`, mesmo padrão assíncrono de idempotência-por-
dia de `backlog_snapshot.run_backlog_snapshot_loop`)."""

from __future__ import annotations

import asyncio
import logging
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.regional import REGIONAL_CODE_MAP, is_valid_regional

from .models import SupportIxcHourlyBaseline, SupportIxcTicket

logger = logging.getLogger(__name__)

# Quantas semanas anteriores entram na média/desvio-padrão de cada slot (dia-da-semana + hora) -
# mesmo valor usado como `baseline_weeks` padrão do `control_tower()` de Operações
# (app/modules/operations/services.py), reaproveitado aqui pelo mesmo raciocínio: amostra grande
# o bastante pra suavizar ruído semanal, pequena o bastante pra não diluir uma mudança real de
# padrão ocorrida há poucos meses.
BASELINE_WEEKS_DEFAULT = 8

# Janelas padrão de detecção de pico - "última 1h/2h/6h" cobre desde um pico agudo (rompimento de
# backbone) até uma degradação mais lenta ao longo da manhã, sem gerar uma lista longa demais.
BURST_WINDOWS_HOURS: tuple[int, ...] = (1, 2, 6)


def _delete_scope(db: Session, *, scope_type: str, scope_id: str | None) -> None:
    query = delete(SupportIxcHourlyBaseline).where(SupportIxcHourlyBaseline.scope_type == scope_type)
    query = query.where(
        SupportIxcHourlyBaseline.scope_id.is_(None) if scope_id is None else SupportIxcHourlyBaseline.scope_id == scope_id
    )
    db.execute(query)


def recompute_hourly_baseline(
    db: Session,
    *,
    scope_type: str,
    scope_id: str | None = None,
    reference_date: date | None = None,
    baseline_weeks: int = BASELINE_WEEKS_DEFAULT,
) -> int:
    """Recalcula os 168 slots (7 dias x 24 horas) de UM escopo (`("global", None)` ou
    `("regional", <regional>)`), a partir dos `baseline_weeks` dias completos ANTERIORES a
    `reference_date` (hoje é excluído - dia parcial distorceria a média). Apaga e reinsere as
    linhas daquele escopo (não é histórico incremental, é sempre "o baseline vigente agora").
    Devolve quantas linhas foram escritas (sempre 168, mesmo pra slot sem nenhuma amostra - fica
    com `avg_count=0`/`sample_weeks=baseline_weeks`, não some da tabela)."""
    reference_date = reference_date or date.today()
    window_end = reference_date - timedelta(days=1)
    window_start = reference_date - timedelta(days=baseline_weeks * 7)

    query = select(SupportIxcTicket.created_at).where(
        func.date(SupportIxcTicket.created_at) >= window_start,
        func.date(SupportIxcTicket.created_at) <= window_end,
    )
    if scope_type == "regional":
        query = query.where(SupportIxcTicket.regional == scope_id)

    # slot (weekday, hour) -> semana (0 = semana mais recente do período) -> contagem
    slot_week_counts: dict[tuple[int, int], dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for (created_at,) in db.execute(query).all():
        if created_at is None:
            continue
        ticket_date = created_at.date()
        week_index = (window_end - ticket_date).days // 7
        if 0 <= week_index < baseline_weeks:
            slot_week_counts[(ticket_date.weekday(), created_at.hour)][week_index] += 1

    _delete_scope(db, scope_type=scope_type, scope_id=scope_id)

    rows_written = 0
    for weekday in range(7):
        for hour in range(24):
            counts = [slot_week_counts.get((weekday, hour), {}).get(week, 0) for week in range(baseline_weeks)]
            avg_count = sum(counts) / baseline_weeks if baseline_weeks else 0.0
            stddev_count = statistics.pstdev(counts) if len(counts) > 1 else 0.0
            db.add(
                SupportIxcHourlyBaseline(
                    scope_type=scope_type,
                    scope_id=scope_id,
                    weekday=weekday,
                    hour=hour,
                    avg_count=round(avg_count, 3),
                    stddev_count=round(stddev_count, 3),
                    sample_weeks=baseline_weeks,
                )
            )
            rows_written += 1
    db.commit()
    return rows_written


def recompute_all_hourly_baselines(
    db: Session, *, reference_date: date | None = None, baseline_weeks: int = BASELINE_WEEKS_DEFAULT
) -> int:
    """Recalcula o baseline da operação inteira (`scope_type="global"`) e de cada regional válida
    - idempotente por dia: se a linha mais recentemente computada já é de hoje, não faz nada
    (mesmo espírito de `backlog_snapshot.capture_backlog_snapshot`, mas comparando `computed_at`
    em vez de existência de linha, porque aqui SEMPRE existe alguma linha depois do primeiro
    cálculo - a pergunta certa é "já rodou hoje", não "já existe"). Devolve o total de linhas
    escritas (0 se já tinha rodado hoje)."""
    reference_date = reference_date or date.today()
    last_computed = db.scalar(select(func.max(SupportIxcHourlyBaseline.computed_at)))
    if last_computed is not None:
        last_computed_date = last_computed.date() if isinstance(last_computed, datetime) else date.fromisoformat(str(last_computed)[:10])
        if last_computed_date >= reference_date:
            return 0

    total = recompute_hourly_baseline(db, scope_type="global", scope_id=None, reference_date=reference_date, baseline_weeks=baseline_weeks)
    regionals = [r for r in dict.fromkeys(REGIONAL_CODE_MAP.values()) if is_valid_regional(r)]
    for regional in regionals:
        total += recompute_hourly_baseline(
            db, scope_type="regional", scope_id=regional, reference_date=reference_date, baseline_weeks=baseline_weeks
        )
    return total


def _hour_slots(window_start: datetime, window_end: datetime) -> list[tuple[int, int]]:
    """Enumera os slots (dia-da-semana, hora) cobertos por `[window_start, window_end)`, um por
    hora cheia cruzada - aproximação deliberada (a janela raramente cai exatamente na hora cheia);
    documentada em `detect_bursts`, não escondida."""
    slots: list[tuple[int, int]] = []
    cursor = window_start.replace(minute=0, second=0, microsecond=0)
    while cursor < window_end:
        slots.append((cursor.weekday(), cursor.hour))
        cursor += timedelta(hours=1)
    return slots


def detect_bursts(
    db: Session,
    *,
    scope_type: str = "global",
    scope_id: str | None = None,
    reference_time: datetime | None = None,
    windows_hours: tuple[int, ...] = BURST_WINDOWS_HOURS,
) -> list[dict[str, Any]]:
    """`BURST_V1`: compara o observado nas últimas N horas contra a soma do baseline dos slots
    cobertos. Limiar (`upper_limit`) no mesmo formato de `control_tower._weekday_expectation`
    (Operações): `max(esperado + 2*desvio, esperado*1.35, esperado + 2)` - reaproveita o mesmo
    raciocínio (nunca dispara por um esperado ~0 virar "infinito por cento", nem por ruído puro de
    desvio-padrão pequeno). Soma de variâncias assume independência entre slots (aproximação
    razoável pra horas do mesmo dia, documentada aqui, não validada estatisticamente).

    `basis="none"` (em vez de `active=False` silencioso) quando o escopo ainda não tem baseline
    calculado - `recompute_all_hourly_baselines` não rodou ainda, ou é um escopo sem dado
    suficiente (`sample_weeks == 0` em todos os slots cobertos)."""
    reference_time = reference_time or datetime.now()
    baseline_rows = {
        (row.weekday, row.hour): row
        for row in db.scalars(
            select(SupportIxcHourlyBaseline).where(
                SupportIxcHourlyBaseline.scope_type == scope_type,
                SupportIxcHourlyBaseline.scope_id.is_(None) if scope_id is None else SupportIxcHourlyBaseline.scope_id == scope_id,
            )
        ).all()
    }

    items: list[dict[str, Any]] = []
    for window in windows_hours:
        window_start = reference_time - timedelta(hours=window)
        observed_query = select(func.count(SupportIxcTicket.id)).where(
            SupportIxcTicket.created_at >= window_start, SupportIxcTicket.created_at < reference_time
        )
        if scope_type == "regional":
            observed_query = observed_query.where(SupportIxcTicket.regional == scope_id)
        observed = int(db.scalar(observed_query) or 0)

        slots = _hour_slots(window_start, reference_time)
        matched = [baseline_rows[slot] for slot in slots if slot in baseline_rows]
        has_sample = any(row.sample_weeks > 0 for row in matched) if matched else False

        if not has_sample:
            items.append(
                {
                    "window": f"{window}h",
                    "observed": observed,
                    "expected": None,
                    "upper_limit": None,
                    "ratio": None,
                    "active": False,
                    "basis": "none",
                }
            )
            continue

        expected = sum(row.avg_count for row in matched)
        variance = sum(row.stddev_count**2 for row in matched)
        upper_limit = max(expected + 2 * (variance**0.5), expected * 1.35, expected + 2)
        items.append(
            {
                "window": f"{window}h",
                "observed": observed,
                "expected": round(expected, 2),
                "upper_limit": round(upper_limit, 2),
                "ratio": round(observed / expected, 2) if expected > 0 else None,
                "active": observed > upper_limit,
                "basis": "baseline",
            }
        )
    return items


async def run_ixc_ticket_baseline_loop() -> None:
    """Confere de hora em hora se o baseline de hoje já foi calculado; se não, calcula - mesmo
    padrão assíncrono de `backlog_snapshot.run_backlog_snapshot_loop` (tolera reinício do processo
    sem depender de agendador externo)."""
    POLL_SECONDS = 3600.0
    while True:
        try:
            with SessionLocal() as db:
                written = await asyncio.to_thread(recompute_all_hourly_baselines, db)
            if written:
                logger.info("Baseline horário do Atendimento IXC recalculado: %d linha(s).", written)
        except Exception:
            logger.exception("Falha ao recalcular o baseline horário do Atendimento IXC.")
        await asyncio.sleep(POLL_SECONDS)
