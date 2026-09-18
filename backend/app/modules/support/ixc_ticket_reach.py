"""Abrangência e reincidência do Atendimento IXC - Fase 1 do plano de evolução analítica
(2026-09-14). Duas perguntas que "atendimentos por 1.000 clientes ativos" não responde: quantos
CLIENTES DIFERENTES foram afetados (um pico pode ser 1 cliente ligando 20 vezes ou 20 clientes
ligando 1 vez cada - são problemas muito diferentes), e quantos deles voltaram a entrar em contato
pelo MESMO motivo pouco tempo depois (sinal de que o atendimento anterior não resolveu).

Funções puras de leitura, no mesmo padrão de filtro/escopo de `ixc_ticket_queries.py`
(`_apply_period`/`_apply_extra_filters`, reaproveitados daqui) - nenhuma delas grava nada.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .ixc_ticket_queries import _apply_extra_filters, _apply_period
from .models import SupportIxcTicket

# Janelas de reincidência do mesmo motivo, em horas - pedido do usuário (2026-09-14): 24h/72h/7d.
REPEAT_CONTACT_WINDOWS_HOURS: dict[str, float] = {"24h": 24.0, "72h": 72.0, "7d": 24.0 * 7}


def _scope(query, *, regional: str | None, city: str | None):
    if regional:
        query = query.where(SupportIxcTicket.regional == regional)
    if city:
        query = query.where(SupportIxcTicket.city == city)
    return query


def unique_customers_count(
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    regional: str | None = None,
    city: str | None = None,
    subject_id: str | None = None,
    sector_id: str | None = None,
) -> int:
    """Clientes DISTINTOS com pelo menos 1 atendimento no recorte - `customer_id` nulo (achado real
    de produção: atendimento sem cliente vinculado, existe) nunca conta, senão "1 cliente" viraria
    o cliente "nenhum"."""
    query = select(func.count(func.distinct(SupportIxcTicket.customer_id))).where(
        SupportIxcTicket.customer_id.is_not(None)
    )
    query = _scope(query, regional=regional, city=city)
    query = _apply_extra_filters(query, subject_id=subject_id, sector_id=sector_id)
    query = _apply_period(query, SupportIxcTicket.created_at, date_from, date_to)
    return int(db.scalar(query) or 0)


def repeat_customers_count(
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    regional: str | None = None,
    city: str | None = None,
    subject_id: str | None = None,
    sector_id: str | None = None,
    min_tickets: int = 2,
) -> int:
    """Quantos clientes distintos tiveram `min_tickets` OU MAIS atendimentos no recorte (qualquer
    motivo) - "voltou a ligar", não necessariamente pelo mesmo assunto (ver
    `repeat_contact_counts` pra reincidência do MESMO motivo numa janela de tempo)."""
    query = select(SupportIxcTicket.customer_id, func.count(SupportIxcTicket.id).label("ticket_count")).where(
        SupportIxcTicket.customer_id.is_not(None)
    )
    query = _scope(query, regional=regional, city=city)
    query = _apply_extra_filters(query, subject_id=subject_id, sector_id=sector_id)
    query = _apply_period(query, SupportIxcTicket.created_at, date_from, date_to)
    query = query.group_by(SupportIxcTicket.customer_id).having(func.count(SupportIxcTicket.id) >= min_tickets)
    return int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)


def repeat_contact_counts(
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    regional: str | None = None,
    city: str | None = None,
    subject_id: str | None = None,
    sector_id: str | None = None,
) -> dict[str, int]:
    """Conta PARES consecutivos de atendimento do MESMO cliente + MESMO motivo, dentro de cada
    janela (`REPEAT_CONTACT_WINDOWS_HOURS`) - um cliente com 3 atendimentos seguidos do mesmo
    motivo em poucas horas conta 2 pares, não 3, porque a pergunta é "quantas vezes ele precisou
    voltar", e o par (1º,2º) e o par (2º,3º) são dois retornos, não três atendimentos soltos.

    Agrupamento e comparação de intervalo são feitos em PYTHON, não em SQL - mesma escolha de
    `_dominant_category`/`_priorities_for_scopes`, que já buscam linhas agregadas e comparam em
    Python; aqui evita depender de window functions (nem toda versão do SQLite dos testes suporta
    `LAG`/`ROW_NUMBER` do mesmo jeito que o Postgres de produção).

    LIMITAÇÃO CONHECIDA: um par cujo atendimento MAIS ANTIGO caiu antes de `date_from` não é
    contado, mesmo que o mais novo esteja dentro do recorte - o recorte de período corta o
    histórico igual em qualquer consulta deste módulo, não é exclusivo desta função. Períodos
    maiores (ex.: 30 dias) sofrem menos com isso do que um recorte de 1 dia só."""
    query = select(SupportIxcTicket.customer_id, SupportIxcTicket.subject_id, SupportIxcTicket.created_at).where(
        SupportIxcTicket.customer_id.is_not(None),
        SupportIxcTicket.subject_id.is_not(None),
    )
    query = _scope(query, regional=regional, city=city)
    query = _apply_extra_filters(query, subject_id=subject_id, sector_id=sector_id)
    query = _apply_period(query, SupportIxcTicket.created_at, date_from, date_to)

    grouped: dict[tuple[str, str], list[datetime]] = {}
    for customer_id, subj_id, created_at in db.execute(query).all():
        if created_at is None:
            continue
        grouped.setdefault((customer_id, subj_id), []).append(created_at)

    counts = {window: 0 for window in REPEAT_CONTACT_WINDOWS_HOURS}
    for timestamps in grouped.values():
        if len(timestamps) < 2:
            continue
        timestamps.sort()
        for previous, current in zip(timestamps, timestamps[1:]):
            gap_hours = (current - previous).total_seconds() / 3600
            for window, max_hours in REPEAT_CONTACT_WINDOWS_HOURS.items():
                if gap_hours <= max_hours:
                    counts[window] += 1
    return counts


def reach_summary(
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    regional: str | None = None,
    city: str | None = None,
    subject_id: str | None = None,
    sector_id: str | None = None,
    ticket_count: int | None = None,
) -> dict[str, Any]:
    """Agrupa as métricas de abrangência/reincidência num único dict - conveniência pros
    consumidores da Fase 2 (endpoints de contexto/prioridades) não terem que chamar 3 funções
    separadas. `ticket_count`, se já calculado pelo chamador (evita reconsultar), alimenta
    `tickets_per_customer`; se omitido, é recontado aqui."""
    unique_customers = unique_customers_count(
        db, date_from=date_from, date_to=date_to, regional=regional, city=city, subject_id=subject_id, sector_id=sector_id
    )
    if ticket_count is None:
        count_query = _apply_period(
            _apply_extra_filters(
                _scope(select(func.count(SupportIxcTicket.id)), regional=regional, city=city),
                subject_id=subject_id,
                sector_id=sector_id,
            ),
            SupportIxcTicket.created_at,
            date_from,
            date_to,
        )
        ticket_count = int(db.scalar(count_query) or 0)

    return {
        "unique_customers": unique_customers,
        "tickets_per_customer": round(ticket_count / unique_customers, 2) if unique_customers else None,
        "repeat_customers": repeat_customers_count(
            db, date_from=date_from, date_to=date_to, regional=regional, city=city, subject_id=subject_id, sector_id=sector_id
        ),
        "repeat_contact": repeat_contact_counts(
            db, date_from=date_from, date_to=date_to, regional=regional, city=city, subject_id=subject_id, sector_id=sector_id
        ),
    }
