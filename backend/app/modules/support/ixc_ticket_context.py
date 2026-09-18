"""Fase 2 do plano de evolução analítica do Atendimento IXC (2026-09-14): contrato de contexto
único, generalizando `_priorities_for_scopes`/breakdown por nível numa única API baseada em
`dimension` + filtros independentes, inspirado no `control_tower()` de Operações
(`app/modules/operations/services.py`) - `path`/`next_level` calculado a partir de quais filtros
já estão fixados, em vez de uma hierarquia de rota rígida.

Diferença deliberada em relação a `ixc_ticket_overview.py` (Visão Geral, mês-calendário +
histórico de N meses no mesmo corte de dia): este módulo usa o MESMO modelo de período livre
(`date_from`/`date_to` + janela anterior de mesmo tamanho) que `ixc_ticket_queries.py`
(drill-down) já usa - unifica em cima do modelo mais simples dos dois, não inventa um terceiro.
Isso é ADITIVO: as rotas antigas (`/ixc/tickets/overview`, `/priorities`, `/breakdown`, ...)
continuam existindo e servindo o frontend atual sem mudança (estratégia strangler, item 15 do
plano) - nenhuma delas foi tocada.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.operations.models import OperationCustomerContract

from .ixc_ticket_overview import CRITICAL_DEVIATION_PCT, IMPROVING_DEVIATION_PCT
from .ixc_ticket_queries import (
    ACTIVE_CONTRACT_STATUS,
    _apply_extra_filters,
    _apply_period,
    _deviation_pct,
    _previous_period_bounds,
    _previous_period_counts,
    city_breakdown,
    neighborhood_breakdown,
    reason_breakdown,
    regional_breakdown,
)
from .ixc_ticket_reach import reach_summary
from .models import SupportIxcTicket

# Ordem-padrão de drill quando `dimension` não é informado - mesmo espírito do
# `CONTROL_TOWER_LEVELS` de Operações: cada nível só entra na lista se ainda não estiver fixado
# por um filtro. `subject`/`sector` não têm hierarquia entre si (são ortogonais, não pai/filho),
# então só `subject` aparece como "próximo nível" natural depois de bairro.
DIMENSION_ORDER = ("regional", "city", "neighborhood", "subject")


def _classify_severity(deviation_pct: float | None) -> str:
    if deviation_pct is None:
        return "sem_dado"
    if deviation_pct >= CRITICAL_DEVIATION_PCT:
        return "critico"
    if deviation_pct <= IMPROVING_DEVIATION_PCT:
        return "em_melhora"
    return "dentro_da_curva"


def _next_dimension(*, regional: str | None, city: str | None, neighborhood: str | None, subject_id: str | None) -> str | None:
    if regional is None:
        return "regional"
    if city is None:
        return "city"
    if neighborhood is None:
        return "neighborhood"
    if subject_id is None:
        return "subject"
    return None


def _scope_where(*, regional: str | None, city: str | None, neighborhood: str | None) -> tuple:
    clauses = []
    if regional:
        clauses.append(SupportIxcTicket.regional == regional)
    if city:
        clauses.append(SupportIxcTicket.city == city)
    if neighborhood:
        clauses.append(SupportIxcTicket.neighborhood == neighborhood)
    return tuple(clauses)


def _scope_ticket_count(
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    regional: str | None,
    city: str | None,
    neighborhood: str | None,
    subject_id: str | None,
    sector_id: str | None,
) -> int:
    query = select(func.count(SupportIxcTicket.id))
    where = _scope_where(regional=regional, city=city, neighborhood=neighborhood)
    if where:
        query = query.where(*where)
    query = _apply_period(query, SupportIxcTicket.created_at, date_from, date_to)
    query = _apply_extra_filters(query, subject_id=subject_id, sector_id=sector_id)
    return int(db.scalar(query) or 0)


def _scope_contract_count(db: Session, *, regional: str | None, city: str | None) -> int | None:
    """Só existe base de contratos ativos cadastrada por regional/cidade - no nível bairro/motivo
    não há `OperationCustomerContract.neighborhood` populado o bastante pra ser confiável (mesmo
    limite já documentado em `ixc_ticket_queries.MIN_CITY_COVERAGE_PCT`), então devolve `None`
    (não calcula) em vez de um número que parece preciso e não é."""
    if not regional and not city:
        return None
    query = select(func.count(OperationCustomerContract.id)).where(
        OperationCustomerContract.status == ACTIVE_CONTRACT_STATUS
    )
    if regional:
        query = query.where(OperationCustomerContract.regional == regional)
    if city:
        query = query.where(OperationCustomerContract.city == city)
    return int(db.scalar(query) or 0)


def driver_decomposition_for_period(
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    regional: str | None = None,
    city: str | None = None,
    neighborhood: str | None = None,
    subject_id: str | None = None,
    sector_id: str | None = None,
) -> list[dict[str, Any]]:
    """Mesma ideia de `ixc_ticket_overview.driver_decomposition` (excesso por motivo +
    `contribution_pct`), mas com "esperado" = contagem do MESMO motivo na janela anterior de
    mesmo tamanho (modelo de período livre), em vez da média de N meses-calendário anteriores -
    coerente com o resto deste módulo, que já usa esse modelo pro drill-down."""
    where = _scope_where(regional=regional, city=city, neighborhood=neighborhood)

    current_query = select(SupportIxcTicket.subject_name, func.count(SupportIxcTicket.id)).group_by(
        SupportIxcTicket.subject_name
    )
    if where:
        current_query = current_query.where(*where)
    current_query = _apply_period(current_query, SupportIxcTicket.created_at, date_from, date_to)
    current_query = _apply_extra_filters(current_query, subject_id=subject_id, sector_id=sector_id)
    current_counts = {(name or "Não informado"): count for name, count in db.execute(current_query).all()}

    previous_counts = _previous_period_counts(
        db,
        group_column=SupportIxcTicket.subject_name,
        date_from=date_from,
        date_to=date_to,
        subject_id=subject_id,
        sector_id=sector_id,
        extra_where=where,
    )

    items: list[dict[str, Any]] = []
    for name, current in current_counts.items():
        expected = previous_counts.get(name, 0)
        excess = current - expected
        items.append({"subject_name": name, "current": current, "expected": expected, "excess": excess})

    total_positive_excess = sum(item["excess"] for item in items if item["excess"] > 0)
    for item in items:
        item["contribution_pct"] = (
            round(item["excess"] / total_positive_excess * 100, 1)
            if total_positive_excess > 0 and item["excess"] > 0
            else 0.0
        )

    items.sort(key=lambda item: item["excess"], reverse=True)
    return items


def resolve_context(
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    regional: str | None = None,
    city: str | None = None,
    neighborhood: str | None = None,
    subject_id: str | None = None,
    sector_id: str | None = None,
) -> dict[str, Any]:
    """Contexto agregado de um escopo (qualquer combinação de filtros) - o "resumo executivo" que
    alimenta o topo da tela única do item 4 do plano: contagem/base/desvio/severidade, abrangência
    (`ixc_ticket_reach`), motivo dominante do excesso e qual é o próximo nível relevante pra
    continuar o drill (`next_dimension`, `None` quando já não há nível seguinte a abrir)."""
    ticket_count = _scope_ticket_count(
        db,
        date_from=date_from,
        date_to=date_to,
        regional=regional,
        city=city,
        neighborhood=neighborhood,
        subject_id=subject_id,
        sector_id=sector_id,
    )
    contract_count = _scope_contract_count(db, regional=regional, city=city)
    tickets_per_1000 = round(ticket_count / contract_count * 1000, 2) if contract_count else None

    previous_ticket_count = 0
    bounds = _previous_period_bounds(date_from, date_to)
    if bounds is not None:
        previous_from, previous_to = bounds
        previous_ticket_count = _scope_ticket_count(
            db,
            date_from=previous_from,
            date_to=previous_to,
            regional=regional,
            city=city,
            neighborhood=neighborhood,
            subject_id=subject_id,
            sector_id=sector_id,
        )
    deviation_pct = _deviation_pct(ticket_count, previous_ticket_count)

    drivers = driver_decomposition_for_period(
        db,
        date_from=date_from,
        date_to=date_to,
        regional=regional,
        city=city,
        neighborhood=neighborhood,
        subject_id=subject_id,
        sector_id=sector_id,
    )
    top_driver = drivers[0] if drivers else None

    reach = reach_summary(
        db,
        date_from=date_from,
        date_to=date_to,
        regional=regional,
        city=city,
        subject_id=subject_id,
        sector_id=sector_id,
        ticket_count=ticket_count if not neighborhood else None,
    )

    return {
        "regional": regional,
        "city": city,
        "neighborhood": neighborhood,
        "date_from": date_from,
        "date_to": date_to,
        "ticket_count": ticket_count,
        "contract_count": contract_count,
        "tickets_per_1000_contracts": tickets_per_1000,
        "previous_ticket_count": previous_ticket_count,
        "deviation_pct": deviation_pct,
        "severity": _classify_severity(deviation_pct),
        "next_dimension": _next_dimension(regional=regional, city=city, neighborhood=neighborhood, subject_id=subject_id),
        "reach": reach,
        "top_driver": top_driver,
    }


def priorities_for_context(
    db: Session,
    *,
    dimension: str,
    date_from: date | None,
    date_to: date | None,
    regional: str | None = None,
    city: str | None = None,
    neighborhood: str | None = None,
    subject_id: str | None = None,
    sector_id: str | None = None,
) -> list[dict[str, Any]]:
    """Ranking do PRÓXIMO NÍVEL (item 3 do plano: filtros independentes escolhem a dimensão, não
    uma rota fixa por nível) - camada fina sobre as funções de breakdown já existentes e testadas
    em `ixc_ticket_queries.py`, só acrescentando `severity` (mesmos limiares da Visão Geral) e o
    rótulo de `dimension` em cada item."""
    if dimension not in DIMENSION_ORDER:
        raise ValueError(f"dimension inválida: {dimension!r}")
    if dimension in ("city", "neighborhood", "subject") and not regional:
        raise ValueError("regional é obrigatório para esta dimensão")
    if dimension in ("neighborhood", "subject") and not city:
        raise ValueError("city é obrigatório para esta dimensão")
    if dimension == "subject" and not neighborhood:
        raise ValueError("neighborhood é obrigatório para a dimensão 'subject'")

    if dimension == "regional":
        items = regional_breakdown(db, date_from=date_from, date_to=date_to, subject_id=subject_id, sector_id=sector_id)
    elif dimension == "city":
        items = city_breakdown(
            db, regional=regional, date_from=date_from, date_to=date_to, subject_id=subject_id, sector_id=sector_id
        )
    elif dimension == "neighborhood":
        items = neighborhood_breakdown(
            db,
            regional=regional,
            city=city,
            date_from=date_from,
            date_to=date_to,
            subject_id=subject_id,
            sector_id=sector_id,
        )
    else:
        items = reason_breakdown(
            db,
            regional=regional,
            city=city,
            neighborhood=neighborhood,
            date_from=date_from,
            date_to=date_to,
            subject_id=subject_id,
            sector_id=sector_id,
        )

    for item in items:
        item["dimension"] = dimension
        item["severity"] = _classify_severity(item["deviation_pct"])
    return items
