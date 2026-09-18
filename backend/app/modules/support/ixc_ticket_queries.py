"""Drill-down do atendimento IXC (`su_ticket`): regional -> cidade -> bairro -> motivo/protocolo.

Ver docs/STATUS.md (2026-09-11): atendimento como indicador ANTECIPADO de incidente, normalizado
por 1.000 clientes ativos (`OperationCustomerContract`). Confirmado com o usuário em 2026-09-11
contra a distribuição real (`status`: A=84.022, I=30.529, N=1.092, D=1.061, P=146): "ativo" para
este denominador é `OperationCustomerContract.status == "A"` (contrato ativo) - decisão dele,
não `status_internet` (status do serviço, pode divergir do contrato).

Import cross-módulo deliberado (`operations.models.OperationCustomerContract`) - mesmo padrão que
Gestão Integrada/UNI Intelligence já usam para consumir projeção de outro módulo por leitura, sem
duplicar ingestão (ver docs/00-TRILHA-0.md)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.operations.models import OperationCustomerContract

from .ixc_ticket_taxonomy import NAO_MAPEADO, current_theme_map
from .models import SupportIxcTicket


def _apply_period(query, column, date_from: date | None, date_to: date | None):
    # Achado real em produção (2026-09-11): `func.date(column) >= "2026-09-01"` (string) funciona
    # no SQLite dos testes (tipagem solta) mas quebra no Postgres real - `date >= character
    # varying` não tem operador, precisa comparar contra um `date` de verdade, não string.
    if date_from:
        query = query.where(func.date(column) >= date_from)
    if date_to:
        query = query.where(func.date(column) <= date_to)
    return query


def selected_ids(value: str | None) -> list[str]:
    """Aceita um id único ou uma lista separada por vírgula (ex.: "90,91") - pedido do usuário
    (2026-09-12): filtro de motivo/setor é multi-seleção, não uma escolha só. Mesmo padrão já usado
    nos filtros do OPA (`opa_filters._selected_values`)."""
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _apply_extra_filters(query, *, subject_id: str | None, sector_id: str | None):
    """Filtro adicional de motivo/setor, ortogonal ao nível do drill-down (regional -> cidade ->
    bairro -> motivo) - pedido explícito do usuário (2026-09-12): poder filtrar QUALQUER nível por
    um ou mais motivos/setores, não só ver o motivo no fim da hierarquia."""
    if values := selected_ids(subject_id):
        query = query.where(SupportIxcTicket.subject_id.in_(values))
    if values := selected_ids(sector_id):
        query = query.where(SupportIxcTicket.sector_id.in_(values))
    return query


# Decisão do usuário (2026-09-11): "cliente ativo" pro denominador de atendimento por 1.000 é
# `status == ACTIVE_CONTRACT_STATUS` (contrato ativo), não `status_internet` (status do serviço).
ACTIVE_CONTRACT_STATUS = "A"


def _rate_per_1000(ticket_count: int, contract_count: int | None) -> float | None:
    if not contract_count:
        return None
    return round(ticket_count / contract_count * 1000, 2)


# Amostra mínima no período ANTERIOR pro desvio ser considerado sinal, não ruído - mesmo espírito
# de `ixc_ticket_overview.MIN_HISTORICAL_SAMPLE` (=10): 1 atendimento virando 2 já seria "+100%"
# por acaso estatístico, não anomalia de verdade.
MIN_DEVIATION_SAMPLE = 10


def _previous_period_bounds(date_from: date | None, date_to: date | None) -> tuple[date, date] | None:
    """Janela imediatamente anterior, do MESMO TAMANHO em dias - mesmo padrão de comparação já
    usado no OPA (`OpaAttendanceFilters.previous_period`). Pedido do usuário (2026-09-12): o
    drill-down (que usa um período livre escolhido na tela, não mês-calendário) "ainda está sem
    dados de desvio" - mostra volume, mas não diz se aquele volume é normal ou uma anomalia."""
    if not date_from or not date_to:
        return None
    span_days = (date_to - date_from).days + 1
    previous_to = date_from - timedelta(days=1)
    previous_from = previous_to - timedelta(days=span_days - 1)
    return previous_from, previous_to


def _deviation_pct(current: int, previous: int) -> float | None:
    if previous < MIN_DEVIATION_SAMPLE:
        return None
    return round((current - previous) / previous * 100, 1)


def _previous_period_counts(
    db: Session,
    *,
    group_column,
    date_from: date | None,
    date_to: date | None,
    subject_id: str | None,
    sector_id: str | None,
    extra_where: tuple = (),
) -> dict[Any, int]:
    """Contagem por `group_column` no período anterior de mesmo tamanho, com o MESMO recorte
    (regional/cidade/bairro pai + motivo/setor) da consulta atual - senão o desvio compararia
    universos diferentes."""
    bounds = _previous_period_bounds(date_from, date_to)
    if bounds is None:
        return {}
    previous_from, previous_to = bounds
    query = select(group_column, func.count(SupportIxcTicket.id)).group_by(group_column)
    if extra_where:
        query = query.where(*extra_where)
    query = _apply_period(query, SupportIxcTicket.created_at, previous_from, previous_to)
    query = _apply_extra_filters(query, subject_id=subject_id, sector_id=sector_id)
    return dict(db.execute(query).all())


def regional_breakdown(
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    subject_id: str | None = None,
    sector_id: str | None = None,
) -> list[dict[str, Any]]:
    ticket_query = _apply_period(
        select(SupportIxcTicket.regional, func.count(SupportIxcTicket.id)).group_by(SupportIxcTicket.regional),
        SupportIxcTicket.created_at,
        date_from,
        date_to,
    )
    ticket_query = _apply_extra_filters(ticket_query, subject_id=subject_id, sector_id=sector_id)
    ticket_counts = dict(db.execute(ticket_query).all())

    previous_counts = _previous_period_counts(
        db,
        group_column=SupportIxcTicket.regional,
        date_from=date_from,
        date_to=date_to,
        subject_id=subject_id,
        sector_id=sector_id,
    )

    contract_counts = dict(
        db.execute(
            select(OperationCustomerContract.regional, func.count(OperationCustomerContract.id))
            .where(OperationCustomerContract.status == ACTIVE_CONTRACT_STATUS)
            .group_by(OperationCustomerContract.regional)
        ).all()
    )

    keys = {k for k in set(ticket_counts) | set(contract_counts) if k}
    items = []
    for regional in keys:
        tickets = ticket_counts.get(regional, 0)
        contracts = contract_counts.get(regional)
        previous = previous_counts.get(regional, 0)
        items.append({
            "key": regional,
            "label": regional,
            "ticket_count": tickets,
            "contract_count": contracts,
            "tickets_per_1000_contracts": _rate_per_1000(tickets, contracts),
            "previous_ticket_count": previous,
            "deviation_pct": _deviation_pct(tickets, previous),
        })
    items.sort(key=lambda r: r["ticket_count"], reverse=True)
    return items


# Achado real em produção (2026-09-11): a maioria dos contratos ativos não tem cidade cadastrada
# no IXC (`cidade=0`) - visto ao vivo numa regional real com só 4,8% de cobertura (95 de 1.977
# contratos ativos com cidade resolvida). Sem esse piso, uma cidade que por acaso concentra os
# poucos contratos resolvidos daquela regional mostra uma taxa "por 1.000" absurda (>10.000/1.000
# num caso real) - matematicamente correta com o denominador que existe, mas enganosa, porque o
# denominador real da cidade é uma fração desconhecida dos ~95% sem cidade. Abaixo deste piso de
# cobertura da REGIONAL inteira, a tela mostra "base insuficiente" em vez de um número que parece
# preciso e não é.
MIN_CITY_COVERAGE_PCT = 30.0


def city_breakdown(
    db: Session,
    *,
    regional: str,
    date_from: date | None,
    date_to: date | None,
    subject_id: str | None = None,
    sector_id: str | None = None,
) -> list[dict[str, Any]]:
    ticket_query = _apply_period(
        select(SupportIxcTicket.city, func.count(SupportIxcTicket.id))
        .where(SupportIxcTicket.regional == regional)
        .group_by(SupportIxcTicket.city),
        SupportIxcTicket.created_at,
        date_from,
        date_to,
    )
    ticket_query = _apply_extra_filters(ticket_query, subject_id=subject_id, sector_id=sector_id)
    ticket_counts = dict(db.execute(ticket_query).all())

    previous_counts = _previous_period_counts(
        db,
        group_column=SupportIxcTicket.city,
        date_from=date_from,
        date_to=date_to,
        subject_id=subject_id,
        sector_id=sector_id,
        extra_where=(SupportIxcTicket.regional == regional,),
    )

    contract_counts = dict(
        db.execute(
            select(OperationCustomerContract.city, func.count(OperationCustomerContract.id))
            .where(
                OperationCustomerContract.regional == regional,
                OperationCustomerContract.status == ACTIVE_CONTRACT_STATUS,
            )
            .group_by(OperationCustomerContract.city)
        ).all()
    )

    regional_active_total = int(
        db.scalar(
            select(func.count(OperationCustomerContract.id)).where(
                OperationCustomerContract.regional == regional,
                OperationCustomerContract.status == ACTIVE_CONTRACT_STATUS,
            )
        )
        or 0
    )
    # `contract_counts` vem de um GROUP BY que inclui uma chave `None` pra quem não tem cidade -
    # só soma as chaves com cidade de verdade pro numerador de cobertura.
    regional_city_resolved = sum(count for city_key, count in contract_counts.items() if city_key is not None)
    coverage_pct = round(regional_city_resolved / regional_active_total * 100, 1) if regional_active_total else None
    reliable_denominator = coverage_pct is not None and coverage_pct >= MIN_CITY_COVERAGE_PCT

    keys = {k for k in set(ticket_counts) | set(contract_counts) if k}
    items = []
    for city in keys:
        tickets = ticket_counts.get(city, 0)
        contracts = contract_counts.get(city)
        previous = previous_counts.get(city, 0)
        items.append({
            "key": city,
            "label": city,
            "ticket_count": tickets,
            "contract_count": contracts,
            "tickets_per_1000_contracts": _rate_per_1000(tickets, contracts) if reliable_denominator else None,
            "coverage_pct": coverage_pct,
            "previous_ticket_count": previous,
            "deviation_pct": _deviation_pct(tickets, previous),
        })
    items.sort(key=lambda r: r["ticket_count"], reverse=True)
    return items


def neighborhood_breakdown(
    db: Session,
    *,
    regional: str,
    city: str,
    date_from: date | None,
    date_to: date | None,
    subject_id: str | None = None,
    sector_id: str | None = None,
) -> list[dict[str, Any]]:
    query = _apply_period(
        select(SupportIxcTicket.neighborhood, func.count(SupportIxcTicket.id))
        .where(SupportIxcTicket.regional == regional, SupportIxcTicket.city == city)
        .group_by(SupportIxcTicket.neighborhood),
        SupportIxcTicket.created_at,
        date_from,
        date_to,
    )
    query = _apply_extra_filters(query, subject_id=subject_id, sector_id=sector_id)
    rows = db.execute(query).all()

    previous_counts = _previous_period_counts(
        db,
        group_column=SupportIxcTicket.neighborhood,
        date_from=date_from,
        date_to=date_to,
        subject_id=subject_id,
        sector_id=sector_id,
        extra_where=(SupportIxcTicket.regional == regional, SupportIxcTicket.city == city),
    )

    items = [
        {
            "key": neighborhood or "",
            "label": neighborhood or "Não informado",
            "ticket_count": count,
            "contract_count": None,
            "tickets_per_1000_contracts": None,
            "previous_ticket_count": previous_counts.get(neighborhood, 0),
            "deviation_pct": _deviation_pct(count, previous_counts.get(neighborhood, 0)),
        }
        for neighborhood, count in rows
        if neighborhood is not None
    ]
    items.sort(key=lambda r: r["ticket_count"], reverse=True)
    return items


def reason_breakdown(
    db: Session,
    *,
    regional: str,
    city: str,
    neighborhood: str,
    date_from: date | None,
    date_to: date | None,
    subject_id: str | None = None,
    sector_id: str | None = None,
) -> list[dict[str, Any]]:
    # Multi-seleção (2026-09-12): filtrar por 1+ motivos aqui é válido mesmo o nível já agrupando
    # por motivo - restringe a lista aos motivos escolhidos em vez de colapsar a 1 linha só
    # (só colapsaria se exatamente 1 fosse selecionado, e mesmo assim é o resultado esperado).
    query = _apply_period(
        select(
            SupportIxcTicket.subject_id,
            SupportIxcTicket.subject_name,
            func.count(SupportIxcTicket.id),
        )
        .where(
            SupportIxcTicket.regional == regional,
            SupportIxcTicket.city == city,
            SupportIxcTicket.neighborhood == neighborhood,
        )
        .group_by(SupportIxcTicket.subject_id, SupportIxcTicket.subject_name),
        SupportIxcTicket.created_at,
        date_from,
        date_to,
    )
    query = _apply_extra_filters(query, subject_id=subject_id, sector_id=sector_id)
    rows = db.execute(query).all()

    previous_counts = _previous_period_counts(
        db,
        group_column=SupportIxcTicket.subject_id,
        date_from=date_from,
        date_to=date_to,
        subject_id=subject_id,
        sector_id=sector_id,
        extra_where=(
            SupportIxcTicket.regional == regional,
            SupportIxcTicket.city == city,
            SupportIxcTicket.neighborhood == neighborhood,
        ),
    )

    items = [
        {
            "key": row_subject_id or "",
            "label": row_subject_name or "Não informado",
            "ticket_count": count,
            "contract_count": None,
            "tickets_per_1000_contracts": None,
            "previous_ticket_count": previous_counts.get(row_subject_id, 0),
            "deviation_pct": _deviation_pct(count, previous_counts.get(row_subject_id, 0)),
        }
        for row_subject_id, row_subject_name, count in rows
    ]
    items.sort(key=lambda r: r["ticket_count"], reverse=True)
    return items


def list_tickets(
    db: Session,
    *,
    regional: str | None = None,
    city: str | None = None,
    neighborhood: str | None = None,
    subject_id: str | None = None,
    sector_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[SupportIxcTicket]]:
    """Lista os atendimentos individuais (protocolo, status, motivo) do nó final do drill-down -
    "clica no bairro, mostra os motivos E os protocolos" (pedido explícito do usuário)."""
    query = select(SupportIxcTicket)
    if regional:
        query = query.where(SupportIxcTicket.regional == regional)
    if city:
        query = query.where(SupportIxcTicket.city == city)
    if neighborhood:
        query = query.where(SupportIxcTicket.neighborhood == neighborhood)
    query = _apply_extra_filters(query, subject_id=subject_id, sector_id=sector_id)
    query = _apply_period(query, SupportIxcTicket.created_at, date_from, date_to)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.order_by(SupportIxcTicket.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return total, list(rows)


def filter_options(db: Session) -> dict[str, list[dict[str, Any]]]:
    """Motivos e setores distintos vistos nos atendimentos, pra popular os dropdowns de filtro
    (pedido do usuário, 2026-09-12: "poder filtrar os assuntos... nao sei se tem setor").

    `themes` (pedido do usuário, 2026-09-17: "filtrar só por assuntos de problema de internet")
    agrupa os MESMOS motivos por tema/categoria da taxonomia (item 8 do plano) - cada tema já
    carrega a lista de `subject_ids` que ele cobre, pra tela expandir a seleção de tema em
    motivos concretos sem reimplementar a regra de vigência no frontend. Motivo sem taxonomia
    (`NAO_MAPEADO`) não entra em nenhum tema - continua só selecionável em "Motivo"."""
    subject_rows = db.execute(
        select(SupportIxcTicket.subject_id, SupportIxcTicket.subject_name)
        .where(SupportIxcTicket.subject_id.is_not(None))
        .distinct()
    ).all()
    sector_rows = db.execute(
        select(SupportIxcTicket.sector_id, SupportIxcTicket.sector_name)
        .where(SupportIxcTicket.sector_id.is_not(None))
        .distinct()
    ).all()

    subjects = sorted(
        (
            {"id": subject_id, "name": subject_name or subject_id}
            for subject_id, subject_name in subject_rows
        ),
        key=lambda s: s["name"],
    )
    sectors = sorted(
        (
            {"id": sector_id, "name": sector_name or sector_id}
            for sector_id, sector_name in sector_rows
        ),
        key=lambda s: s["name"],
    )

    theme_map = current_theme_map(db)
    themes_by_id: dict[str, dict[str, Any]] = {}
    for subject in subjects:
        theme = theme_map.get(subject["id"])
        if theme is None or theme["theme_id"] == NAO_MAPEADO:
            continue
        entry = themes_by_id.setdefault(
            theme["theme_id"],
            {
                "id": theme["theme_id"],
                "name": theme["theme_label"],
                "category_id": theme["category_id"],
                "category_name": theme["category_label"],
                "subject_ids": [],
            },
        )
        entry["subject_ids"].append(subject["id"])
    themes = sorted(themes_by_id.values(), key=lambda t: (t["category_name"], t["name"]))

    return {"subjects": subjects, "sectors": sectors, "themes": themes}
