from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Literal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import User
from app.modules.operations import queries as operations_queries
from app.modules.operations.models import OperationOrder
from app.modules.operations.period import local_period_utc_bounds
from app.modules.operations.schemas import _text_from_payload

# As mesmas 9 dimensões que a tela de Operação já deixa filtrar/agrupar hoje (regional, cidade,
# tipo de O.S., assunto, diagnóstico, setor, prioridade, responsável, status) - deliberadamente um
# dict novo aqui, não reaproveitado de operations.queries, porque lá as listas de dimensão
# permitida variam por função (`FILTER_COLUMNS` é pra filtro, no plural; `in_progress_breakdown`/
# `sla_breakdown` têm cada uma seu próprio subconjunto no singular). Esta é a lista de agrupamento
# do módulo `ai`, que é uma decisão de produto própria dele.
AGGREGATION_DIMENSIONS = {
    "regional": OperationOrder.regional,
    "city": OperationOrder.city,
    "os_type": OperationOrder.os_type,
    "subject": OperationOrder.os_subject,
    "diagnosis": OperationOrder.diagnosis,
    "department": OperationOrder.department,
    "sector": OperationOrder.sector,
    "priority": OperationOrder.priority,
    "responsible": OperationOrder.responsible,
    "status": OperationOrder.status,
}

AggregationMetric = Literal["quantidade_aberta", "quantidade_fechada", "taxa_sla", "horas_medias"]
TimeseriesMetric = Literal["abertas", "fechadas", "saldo"]
Granularity = Literal["day", "week", "month"]

AI_SEARCH_MAX_PAGE_SIZE = 200


def _percentage(count: int, total: int) -> float:
    return round((count / total) * 100, 2) if total else 0.0


def aggregate_orders(
    db: Session,
    user: User,
    *,
    group_by: str,
    metric: AggregationMetric,
    date_from: date,
    date_to: date,
    **filters,
) -> list[dict]:
    """Agrupa O.S. por uma dimensão e devolve, por grupo: `quantity` (nº de O.S. por trás do
    número), `metric_value` (o valor pedido - contagem, taxa de SLA ou horas médias) e
    `percentage` (fatia do grupo sobre o total de `quantity` entre todos os grupos). Os dois
    últimos têm significado diferente de propósito porque "taxa de SLA" e "horas médias" não são
    frações de um total, então não caberiam sozinhos num único campo `percentage`."""
    field = AGGREGATION_DIMENSIONS.get(group_by, OperationOrder.regional)
    label = func.coalesce(field, "Não identificado")
    start, end = local_period_utc_bounds(date_from, date_to)

    if metric == "quantidade_aberta":
        conditions = operations_queries._dimension_conditions(db, user, operations_queries._opening_filters(filters))
        rows = db.execute(
            select(label, func.count(OperationOrder.id))
            .where(*conditions, OperationOrder.opened_at.between(start, end))
            .group_by(label)
        ).all()
        entries = [(str(row[0]), int(row[1]), float(row[1])) for row in rows]

    elif metric == "taxa_sla":
        conditions = operations_queries._dimension_conditions(db, user, filters)
        rows = db.execute(
            select(
                label,
                func.count(OperationOrder.id),
                func.sum(case((OperationOrder.sla_status == "on_time", 1), else_=0)),
            )
            .where(*conditions, OperationOrder.closed_at.between(start, end))
            .group_by(label)
        ).all()
        entries = [
            (str(row[0]), int(row[1]), _percentage(int(row[2] or 0), int(row[1])))
            for row in rows
        ]

    elif metric == "horas_medias":
        conditions = operations_queries._dimension_conditions(db, user, filters)
        elapsed = OperationOrder.elapsed_hours
        rows = db.execute(
            select(label, func.count(OperationOrder.id), func.avg(elapsed))
            .where(*conditions, OperationOrder.closed_at.between(start, end), elapsed.is_not(None))
            .group_by(label)
        ).all()
        entries = [(str(row[0]), int(row[1]), round(float(row[2] or 0), 1)) for row in rows]

    else:  # "quantidade_fechada"
        conditions = operations_queries._dimension_conditions(db, user, filters)
        rows = db.execute(
            select(label, func.count(OperationOrder.id))
            .where(*conditions, OperationOrder.closed_at.between(start, end))
            .group_by(label)
        ).all()
        entries = [(str(row[0]), int(row[1]), float(row[1])) for row in rows]

    total = sum(count for _, count, _ in entries)
    return [
        {
            "label": label_value,
            "quantity": count,
            "metric_value": metric_value,
            "percentage": _percentage(count, total),
        }
        for label_value, count, metric_value in sorted(entries, key=lambda item: (-item[1], item[0]))
    ]


def orders_timeseries(
    db: Session,
    user: User,
    *,
    metric: TimeseriesMetric,
    granularity: Granularity,
    date_from: date,
    date_to: date,
    **filters,
) -> list[dict]:
    """Série temporal (dia/semana/mês) de abertas, fechadas, ou saldo (abertas - fechadas) por
    bucket - mesma lógica de bucketing de `operations_queries._period_group_start`."""
    start, end = local_period_utc_bounds(date_from, date_to)
    opened_day = operations_queries._local_date(db, OperationOrder.opened_at)
    closed_day = operations_queries._local_date(db, OperationOrder.closed_at)

    opened_counts: dict[date, int] = {}
    closed_counts: dict[date, int] = {}

    if metric in ("abertas", "saldo"):
        opening_conditions = operations_queries._dimension_conditions(db, user, operations_queries._opening_filters(filters))
        rows = db.execute(
            select(opened_day, func.count(OperationOrder.id))
            .where(*opening_conditions, OperationOrder.opened_at.between(start, end))
            .group_by(opened_day)
        ).all()
        opened_counts = {row[0]: int(row[1]) for row in rows}

    if metric in ("fechadas", "saldo"):
        closed_conditions = operations_queries._dimension_conditions(db, user, filters)
        rows = db.execute(
            select(closed_day, func.count(OperationOrder.id))
            .where(*closed_conditions, OperationOrder.closed_at.between(start, end))
            .group_by(closed_day)
        ).all()
        closed_counts = {row[0]: int(row[1]) for row in rows}

    buckets: dict[date, int] = defaultdict(int)
    if metric == "abertas":
        for day, count in opened_counts.items():
            buckets[operations_queries._period_group_start(day, granularity)] += count
    elif metric == "fechadas":
        for day, count in closed_counts.items():
            buckets[operations_queries._period_group_start(day, granularity)] += count
    else:
        for day in set(opened_counts) | set(closed_counts):
            bucket = operations_queries._period_group_start(day, granularity)
            buckets[bucket] += opened_counts.get(day, 0) - closed_counts.get(day, 0)

    return [{"period_start": bucket, "quantity": quantity} for bucket, quantity in sorted(buckets.items())]


def search_orders(
    db: Session,
    user: User,
    *,
    date_from: date,
    date_to: date,
    page: int = 1,
    page_size: int = 50,
    keyword: str | None = None,
    **filters,
) -> dict:
    """Busca paginada de O.S. com diagnóstico/relato técnico, para leitura qualitativa. Período
    obrigatório + paginação real (mesmo padrão de `operations_queries.order_page`) para nunca
    devolver um volume de texto capaz de lotar o contexto da IA de uma vez só."""
    page_size = min(page_size, AI_SEARCH_MAX_PAGE_SIZE)
    if keyword:
        filters = {**filters, "search": keyword}

    conditions, _, _ = operations_queries._query_conditions(db, date_from, date_to, user, filters)
    total = int(db.scalar(select(func.count(OperationOrder.id)).where(*conditions)) or 0)
    offset = (page - 1) * page_size
    orders = list(
        db.scalars(
            select(OperationOrder)
            .where(*conditions)
            .order_by(OperationOrder.opened_at.desc(), OperationOrder.id.desc())
            .offset(offset)
            .limit(page_size)
        )
    )
    items = [
        {
            "order_code": order.order_code,
            "regional": order.regional,
            "os_type": order.os_type,
            "subject": order.os_subject,
            "diagnosis": order.diagnosis,
            "technical_report": _text_from_payload(order.raw_payload, "mensagem_resposta", "relato_tecnico", "relato"),
            "status": order.status,
            "opened_at": order.opened_at,
            "closed_at": order.closed_at,
        }
        for order in orders
    ]
    return {
        "items": items,
        "total_encontrado": total,
        "page": page,
        "page_size": page_size,
        "has_more": total > page * page_size,
    }
