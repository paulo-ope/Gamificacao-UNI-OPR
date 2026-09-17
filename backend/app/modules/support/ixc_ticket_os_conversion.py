"""Fase 6 do plano de evolução analítica do Atendimento IXC (2026-09-15): `OS_CONVERSION_V1` -
mede quantos atendimentos (`SupportIxcTicket`) viraram O.S. (`OperationOrder`) dentro de janelas de
tempo, usando o vínculo que JÁ EXISTE no schema (`OperationOrder.ticket_id ==
SupportIxcTicket.source_id`, migração `20260911_0091`) - nenhuma migração nova nesta fase, só
leitura cruzada entre os dois módulos (mesmo padrão de import cross-módulo já usado em
`ixc_ticket_queries.py` pra `OperationCustomerContract`).

Desvio deliberado do contrato original do plano (seção 8): o campo `lift` (associação "inferida"
por `customer_id`+janela, pra atendimentos sem vínculo direto) NÃO foi implementado - exigiria
definir uma heurística de correlação probabilística própria, fora do escopo desta primeira versão
(documentado aqui, não escondido). `classification` é um bucket simples calibrado visualmente
(mesmo espírito de `CRITICAL_DEVIATION_PCT` em `ixc_ticket_overview.py` - primeira versão, espera
calibração com o usuário)."""

from __future__ import annotations

from datetime import date
from statistics import median
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.operations.models import OperationOrder

from .ixc_ticket_queries import _apply_extra_filters, _apply_period
from .models import SupportIxcTicket

OS_CONVERSION_WINDOWS_HOURS: tuple[int, ...] = (2, 6, 24, 48)

# Limiares de classificação - primeira calibração visual, não regra de negócio validada (mesmo
# aviso de `ixc_ticket_overview.CRITICAL_DEVIATION_PCT`).
HIGH_CONVERSION_PCT = 50.0
MODERATE_CONVERSION_PCT = 20.0


def os_conversion_rate(
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    regional: str | None = None,
    subject_id: str | None = None,
    sector_id: str | None = None,
    windows_hours: tuple[int, ...] = OS_CONVERSION_WINDOWS_HOURS,
) -> dict[str, Any]:
    """De todos os atendimentos do recorte (com `source_id` preenchido), quantos tiveram uma O.S.
    vinculada aberta dentro de cada janela A PARTIR do atendimento. `median_lead_minutes` usa a
    PRIMEIRA O.S. vinculada de cada atendimento que converteu dentro da MAIOR janela pedida - um
    atendimento com mais de uma O.S. só conta a mais rápida (a pergunta é "quanto tempo até a
    primeira ação", não todas as O.S. geradas)."""
    ticket_query = select(SupportIxcTicket.source_id, SupportIxcTicket.created_at).where(
        SupportIxcTicket.source_id.is_not(None)
    )
    if regional:
        ticket_query = ticket_query.where(SupportIxcTicket.regional == regional)
    ticket_query = _apply_period(ticket_query, SupportIxcTicket.created_at, date_from, date_to)
    ticket_query = _apply_extra_filters(ticket_query, subject_id=subject_id, sector_id=sector_id)
    tickets = db.execute(ticket_query).all()
    sample = len(tickets)

    empty_conversions = {f"{window}h": None for window in windows_hours}
    if sample == 0:
        return {"sample": 0, "median_lead_minutes": None, "classification": "sem_dado", "conversions": empty_conversions}

    ticket_ids = [source_id for source_id, _ in tickets]
    max_window = max(windows_hours)
    order_rows = db.execute(
        select(OperationOrder.ticket_id, OperationOrder.opened_at).where(
            OperationOrder.ticket_id.in_(ticket_ids), OperationOrder.opened_at.is_not(None)
        )
    ).all()

    orders_by_ticket: dict[str, list] = {}
    for ticket_id, opened_at in order_rows:
        orders_by_ticket.setdefault(ticket_id, []).append(opened_at)

    conversions = {window: 0 for window in windows_hours}
    lead_minutes: list[float] = []
    for source_id, created_at in tickets:
        # `>= created_at` é defensivo: uma O.S. reaproveitando o mesmo `ticket_id` por acidente de
        # origem, aberta ANTES deste atendimento, nunca poderia ter sido causada por ele.
        candidate_orders = [opened_at for opened_at in orders_by_ticket.get(source_id, []) if opened_at >= created_at]
        if not candidate_orders:
            continue
        gap_hours = (min(candidate_orders) - created_at).total_seconds() / 3600
        if gap_hours <= max_window:
            lead_minutes.append(gap_hours * 60)
        for window in windows_hours:
            if gap_hours <= window:
                conversions[window] += 1

    conversion_pct = {f"{window}h": round(count / sample * 100, 1) for window, count in conversions.items()}
    median_lead = round(median(lead_minutes), 1) if lead_minutes else None

    conversion_24h = conversion_pct.get("24h")
    if conversion_24h is None:
        classification = "sem_dado"
    elif conversion_24h >= HIGH_CONVERSION_PCT:
        classification = "alto"
    elif conversion_24h >= MODERATE_CONVERSION_PCT:
        classification = "moderado"
    else:
        classification = "baixo"

    return {"sample": sample, "median_lead_minutes": median_lead, "classification": classification, "conversions": conversion_pct}
