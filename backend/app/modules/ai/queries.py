from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import User
from app.modules.operations import queries as operations_queries
from app.modules.operations.models import (
    OperationBacklogSnapshot,
    OperationOrder,
    OperationResponsibleAssignment,
    OperationTeamModel,
)
from app.modules.operations.period import local_period_utc_bounds
from app.modules.operations.schemas import OperationFilters, _text_from_payload
from app.services.regional import effective_managed_regionals

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
    "sla_status": OperationOrder.sla_status,
}

AggregationMetric = Literal[
    "quantidade_aberta", "quantidade_fechada", "taxa_sla", "horas_medias",
    "quantidade_atrasada", "quantidade_backlog",
]
TimeseriesMetric = Literal["abertas", "fechadas", "saldo"]
Granularity = Literal["day", "week", "month"]

AI_SEARCH_MAX_PAGE_SIZE = 200

# Campos de texto livre onde "contém"/"começa com"/"termina com"/"diferente de" fazem sentido -
# não inclui campos tipo status_code, que são códigos curtos, não texto pra buscar por trecho.
TEXT_FILTER_COLUMNS = {
    "sector": OperationOrder.sector,
    "subject": OperationOrder.os_subject,
    "diagnosis": OperationOrder.diagnosis,
    "responsible": OperationOrder.responsible,
    "city": OperationOrder.city,
    "department": OperationOrder.department,
}


def _escape_like(value: str) -> str:
    """Escapa os caracteres especiais do LIKE/ILIKE (`%`, `_`, e a própria barra de escape) antes
    de embutir o valor do usuário no padrão - sem isso, um valor com "%" ou "_" se comportaria
    como wildcard em vez de caractere literal."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _text_operator_condition(column, operator: str, raw_value: str):
    if operator == "not_equals":
        return func.lower(column) != raw_value.lower()
    escaped = _escape_like(raw_value)
    pattern = {
        "contains": f"%{escaped}%",
        "starts_with": f"{escaped}%",
        "ends_with": f"%{escaped}",
    }.get(operator)
    return column.ilike(pattern, escape="\\") if pattern is not None else None


def _text_filter_conditions(text_filters: list[dict] | None) -> list:
    conditions = []
    for item in text_filters or []:
        column = TEXT_FILTER_COLUMNS.get(item["field"])
        if column is None:
            continue
        condition = _text_operator_condition(column, item["operator"], item["value"])
        if condition is not None:
            conditions.append(condition)
    return conditions


def _dimension_conditions_with_text(db: Session, user: User, filters: dict, *, opening: bool = False) -> list:
    """Wrapper fino sobre `operations_queries._dimension_conditions` - aplica os filtros exatos
    de sempre e, além deles, os filtros textuais novos (item 10), que não existem no motor de
    filtro do resto do sistema."""
    base_filters = operations_queries._opening_filters(filters) if opening else filters
    conditions = operations_queries._dimension_conditions(db, user, base_filters)
    conditions.extend(_text_filter_conditions(filters.get("text_filters")))
    return conditions


def _group_labels(group_by: str | list[str]) -> list[str]:
    """Normaliza `group_by` (uma dimensão ou várias) numa lista de 1 a 3 - limite pra não deixar
    o resultado explodir combinatorialmente (ex.: 20 regionais x 50 assuntos)."""
    dims = [group_by] if isinstance(group_by, str) else list(group_by)
    return dims[:3] or ["regional"]


def _group_label(group_by: str):
    """"team_model" não é uma coluna de OperationOrder - é calculado casando o responsável (e a
    regional, mesma chave de identidade de OperationResponsibleAssignment) contra a atribuição de
    modelo de equipe, igual ao filtro `team_models` já faz em operations.queries."""
    if group_by == "team_model":
        team_model_name = (
            select(OperationTeamModel.name)
            .join(OperationResponsibleAssignment, OperationResponsibleAssignment.team_model_id == OperationTeamModel.id)
            .where(
                func.lower(OperationResponsibleAssignment.responsible_name) == func.lower(OperationOrder.responsible),
                OperationResponsibleAssignment.regional == OperationOrder.regional,
            )
            .limit(1)
            .scalar_subquery()
        )
        return func.coalesce(team_model_name, "Não identificado")
    field = AGGREGATION_DIMENSIONS.get(group_by, OperationOrder.regional)
    return func.coalesce(field, "Não identificado")


def _team_model_lookup(db: Session, orders: list[OperationOrder]) -> dict[tuple[str, str], str]:
    """Resolve o modelo de equipe de uma página de O.S. já carregada, numa única query extra (em
    vez de juntar essa tabela na query paginada principal) - o volume por página é pequeno (no
    máximo AI_SEARCH_MAX_PAGE_SIZE), então uma segunda query simples é mais barata que um join a
    mais em toda busca, inclusive quando ninguém pede o campo."""
    pairs = {(order.responsible, order.regional) for order in orders if order.responsible and order.regional}
    if not pairs:
        return {}
    lowered_names = {name.lower() for name, _ in pairs}
    rows = db.execute(
        select(OperationResponsibleAssignment.responsible_name, OperationResponsibleAssignment.regional, OperationTeamModel.name)
        .join(OperationTeamModel, OperationTeamModel.id == OperationResponsibleAssignment.team_model_id)
        .where(func.lower(OperationResponsibleAssignment.responsible_name).in_(lowered_names))
    ).all()
    return {(responsible_name.lower(), regional): team_model_name for responsible_name, regional, team_model_name in rows}


def _percentage(count: int, total: int) -> float:
    return round((count / total) * 100, 2) if total else 0.0


def _sla_risk_bucket(elapsed_hours: float | None, sla_target_hours: float | None) -> str:
    """Mesmos limiares de `operations_queries._sla_risk_bucket_case()` (queries.py:2228-2240),
    replicados em Python porque `search_orders` já carrega o objeto `OperationOrder` inteiro (não
    um select de colunas) - calcular aqui evita misturar ORM completo com expressão SQL bruta na
    mesma query. Se aqueles limiares mudarem lá, precisam mudar aqui também."""
    if not sla_target_hours or sla_target_hours <= 0:
        return "no_target"
    ratio = (elapsed_hours or 0) / sla_target_hours * 100
    if ratio >= 100:
        return "breached"
    if ratio >= 80:
        return "critical"
    if ratio >= 50:
        return "attention"
    return "on_track"


def aggregate_orders(
    db: Session,
    user: User,
    *,
    group_by: str | list[str],
    metric: AggregationMetric,
    date_from: date,
    date_to: date,
    **filters,
) -> list[dict]:
    """Agrupa O.S. por uma ou mais dimensões (até 3) e devolve, por grupo: `quantity` (nº de O.S.
    por trás do número), `metric_value` (o valor pedido - contagem, taxa de SLA ou horas médias) e
    `percentage` (fatia do grupo sobre o total de `quantity` entre todos os grupos). Os dois
    últimos têm significado diferente de propósito porque "taxa de SLA" e "horas médias" não são
    frações de um total, então não caberiam sozinhos num único campo `percentage`.

    Com 1 dimensão só, cada item da resposta tem um campo `label` (formato já em uso pelos
    conectores configurados). Com 2+ dimensões, `label` some e cada dimensão pedida aparece como
    sua própria chave (ex.: `{"regional": "...", "subject": "...", "quantity": ...}`) - aditivo,
    não quebra quem já chama com 1 dimensão só."""
    dims = _group_labels(group_by)
    labels = [_group_label(dim) for dim in dims]
    start, end = local_period_utc_bounds(date_from, date_to)

    if metric == "quantidade_aberta":
        conditions = _dimension_conditions_with_text(db, user, filters, opening=True)
        rows = db.execute(
            select(*labels, func.count(OperationOrder.id))
            .where(*conditions, OperationOrder.opened_at.between(start, end))
            .group_by(*labels)
        ).all()
        entries = [(row[:-1], int(row[-1]), float(row[-1])) for row in rows]

    elif metric == "taxa_sla":
        conditions = _dimension_conditions_with_text(db, user, filters)
        rows = db.execute(
            select(
                *labels,
                func.count(OperationOrder.id),
                func.sum(case((OperationOrder.sla_status == "on_time", 1), else_=0)),
            )
            .where(*conditions, OperationOrder.closed_at.between(start, end))
            .group_by(*labels)
        ).all()
        entries = [(row[:-2], int(row[-2]), _percentage(int(row[-1] or 0), int(row[-2]))) for row in rows]

    elif metric == "quantidade_atrasada":
        # Diferente de "quantidade_aberta" (que ignora de propósito equipe/responsável, porque
        # abertura é demanda), aqui o filtro de equipe faz sentido - queremos saber o atraso de
        # QUEM está com a O.S. hoje, então usa os filtros normais, não `_opening_filters`.
        conditions = _dimension_conditions_with_text(db, user, filters)
        rows = db.execute(
            select(*labels, func.count(OperationOrder.id))
            .where(
                *conditions,
                OperationOrder.is_closed.is_(False),
                OperationOrder.opened_at.between(start, end),
                OperationOrder.sla_status == "out_of_time",
            )
            .group_by(*labels)
        ).all()
        entries = [(row[:-1], int(row[-1]), float(row[-1])) for row in rows]

    elif metric == "quantidade_backlog":
        conditions = _dimension_conditions_with_text(db, user, filters)
        rows = db.execute(
            select(*labels, func.count(OperationOrder.id))
            .where(
                *conditions,
                OperationOrder.is_closed.is_(False),
                OperationOrder.opened_at.between(start, end),
            )
            .group_by(*labels)
        ).all()
        entries = [(row[:-1], int(row[-1]), float(row[-1])) for row in rows]

    elif metric == "horas_medias":
        conditions = _dimension_conditions_with_text(db, user, filters)
        elapsed = OperationOrder.elapsed_hours
        rows = db.execute(
            select(*labels, func.count(OperationOrder.id), func.avg(elapsed))
            .where(*conditions, OperationOrder.closed_at.between(start, end), elapsed.is_not(None))
            .group_by(*labels)
        ).all()
        entries = [(row[:-2], int(row[-2]), round(float(row[-1] or 0), 1)) for row in rows]

    else:  # "quantidade_fechada"
        conditions = _dimension_conditions_with_text(db, user, filters)
        rows = db.execute(
            select(*labels, func.count(OperationOrder.id))
            .where(*conditions, OperationOrder.closed_at.between(start, end))
            .group_by(*labels)
        ).all()
        entries = [(row[:-1], int(row[-1]), float(row[-1])) for row in rows]

    total = sum(count for _, count, _ in entries)
    results = []
    for label_values, count, metric_value in sorted(entries, key=lambda item: (-item[1], [str(v) for v in item[0]])):
        percentage = _percentage(count, total)
        if len(dims) == 1:
            item = {"label": str(label_values[0]), "quantity": count, "metric_value": metric_value, "percentage": percentage}
        else:
            item = {dim: str(value) for dim, value in zip(dims, label_values)}
            item.update({"quantity": count, "metric_value": metric_value, "percentage": percentage})
        results.append(item)
    return results


def orders_timeseries(
    db: Session,
    user: User,
    *,
    metric: TimeseriesMetric,
    granularity: Granularity,
    date_from: date,
    date_to: date,
    group_by: str | None = None,
    **filters,
) -> list[dict]:
    """Série temporal (dia/semana/mês) de abertas, fechadas, ou saldo (abertas - fechadas) por
    bucket - mesma lógica de bucketing de `operations_queries._period_group_start`.

    `group_by` é opcional: sem ele, cada ponto é `{period_start, quantity}` (formato já em uso).
    Com ele, cada ponto ganha `group` com o valor da dimensão naquele bucket (ex.: "quantidade
    fechada por dia por modelo de equipe") - aditivo, não muda a chamada sem `group_by`."""
    start, end = local_period_utc_bounds(date_from, date_to)
    opened_day = operations_queries._local_date(db, OperationOrder.opened_at)
    closed_day = operations_queries._local_date(db, OperationOrder.closed_at)
    label = _group_label(group_by) if group_by else None

    def _counts(day_expr, conditions, date_column) -> dict[tuple[date, str | None], int]:
        columns = (day_expr, label) if label is not None else (day_expr,)
        rows = db.execute(
            select(*columns, func.count(OperationOrder.id))
            .where(*conditions, date_column.between(start, end))
            .group_by(*columns)
        ).all()
        result: dict[tuple[date, str | None], int] = {}
        for row in rows:
            key = (row[0], str(row[1])) if label is not None else (row[0], None)
            result[key] = result.get(key, 0) + int(row[-1])
        return result

    opened_counts: dict[tuple[date, str | None], int] = {}
    closed_counts: dict[tuple[date, str | None], int] = {}

    if metric in ("abertas", "saldo"):
        opening_conditions = _dimension_conditions_with_text(db, user, filters, opening=True)
        opened_counts = _counts(opened_day, opening_conditions, OperationOrder.opened_at)

    if metric in ("fechadas", "saldo"):
        closed_conditions = _dimension_conditions_with_text(db, user, filters)
        closed_counts = _counts(closed_day, closed_conditions, OperationOrder.closed_at)

    buckets: dict[tuple[date, str | None], int] = defaultdict(int)
    if metric == "abertas":
        for (day, group), count in opened_counts.items():
            buckets[(operations_queries._period_group_start(day, granularity), group)] += count
    elif metric == "fechadas":
        for (day, group), count in closed_counts.items():
            buckets[(operations_queries._period_group_start(day, granularity), group)] += count
    else:
        for key in set(opened_counts) | set(closed_counts):
            day, group = key
            bucket = (operations_queries._period_group_start(day, granularity), group)
            buckets[bucket] += opened_counts.get(key, 0) - closed_counts.get(key, 0)

    results = []
    for (period_start, group), quantity in sorted(buckets.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
        item = {"period_start": period_start, "quantity": quantity}
        if label is not None:
            item["group"] = group
        results.append(item)
    return results


def _build_search_item(order: OperationOrder, team_model: str | None) -> dict:
    target = order.sla_target_hours
    elapsed = order.elapsed_hours
    is_open = order.closed_at is None

    has_target = target is not None and elapsed is not None
    horas_para_vencer = round(target - elapsed, 1) if has_target else None
    horas_atrasada = round(max(0.0, elapsed - target), 1) if has_target else None
    dias_em_aberto = round((datetime.now(timezone.utc) - order.opened_at).total_seconds() / 86400, 1) if is_open else None
    sla_deadline_at = order.opened_at + timedelta(hours=target) if target is not None else None

    return {
        "order_code": order.order_code,
        "regional": order.regional,
        "os_type": order.os_type,
        "subject": order.os_subject,
        "diagnosis": order.diagnosis,
        "technical_report": _text_from_payload(order.raw_payload, "mensagem_resposta", "relato_tecnico", "relato"),
        "responsible": order.responsible,
        "team_model": team_model,
        "status": order.status,
        "opened_at": order.opened_at,
        "scheduled_at": order.scheduled_at,
        "assumed_at": order.assumed_at,
        "execution_started_at": order.execution_started_at,
        "finished_at": order.finished_at,
        "closed_at": order.closed_at,
        "sla_status": order.sla_status,
        # Só se aplica a O.S. ainda aberta (ver _sla_risk_bucket_case em operations/queries.py) -
        # numa O.S. já fechada o "risco" não tem mais sentido preditivo, fica None.
        "sla_risk": _sla_risk_bucket(elapsed, target) if is_open else None,
        "sla_target_hours": target,
        # `deadline_at` bruto do IXC está majoritariamente vazio nesta instância (ver
        # docs/plano-integracao-ixc.md) - este é o prazo EFETIVO, calculado a partir da meta de
        # horas do assunto (o mesmo que o sistema já usa por baixo pra decidir sla_status).
        "sla_deadline_at": sla_deadline_at,
        "horas_para_vencer": horas_para_vencer,
        "horas_atrasada": horas_atrasada,
        "dias_em_aberto": dias_em_aberto,
        "sla_estourado": order.sla_status == "out_of_time",
    }


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
    conditions.extend(_text_filter_conditions(filters.get("text_filters")))
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
    team_model_by_responsible = _team_model_lookup(db, orders)
    items = [
        _build_search_item(order, team_model_by_responsible.get(((order.responsible or "").lower(), order.regional)))
        for order in orders
    ]
    return {
        "items": items,
        "total_encontrado": total,
        "page": page,
        "page_size": page_size,
        "has_more": total > page * page_size,
    }


def backlog_aging(db: Session, user: User, *, group_by: str, date_to: date, **filters) -> list[dict]:
    """Idade do backlog (O.S. ainda abertas em `date_to`), por dimensão: quantidade, idade média
    e mediana em dias, a O.S. mais antiga, e quantas passam de 1/3/5/7/15 dias. Calculado em
    Python (não em SQL) porque o volume é do tamanho do backlog atual - milhares, não a base toda
    - e mediana não é portável entre Postgres/SQLite sem depender de extensão específica."""
    label = _group_label(group_by)
    conditions = _dimension_conditions_with_text(db, user, filters)
    _, reference_at = local_period_utc_bounds(date_to, date_to)
    rows = db.execute(
        select(label, OperationOrder.order_code, OperationOrder.opened_at).where(
            *conditions,
            OperationOrder.is_closed.is_(False),
            OperationOrder.opened_at <= reference_at,
        )
    ).all()

    by_group: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for label_value, order_code, opened_at in rows:
        age_days = (reference_at - opened_at).total_seconds() / 86400
        by_group[str(label_value)].append((order_code, age_days))

    results = []
    for label_value, entries in by_group.items():
        ages = [age for _, age in entries]
        oldest_code, oldest_age = max(entries, key=lambda entry: entry[1])
        results.append(
            {
                "label": label_value,
                "quantity": len(entries),
                "avg_age_days": round(sum(ages) / len(ages), 1),
                "median_age_days": round(statistics.median(ages), 1),
                "oldest_order_code": oldest_code,
                "oldest_age_days": round(oldest_age, 1),
                "over_1d": sum(1 for age in ages if age > 1),
                "over_3d": sum(1 for age in ages if age > 3),
                "over_5d": sum(1 for age in ages if age > 5),
                "over_7d": sum(1 for age in ages if age > 7),
                "over_15d": sum(1 for age in ages if age > 15),
            }
        )
    results.sort(key=lambda item: -item["quantity"])
    return results


def filter_options_for_ai(db: Session, user: User, date_from: date, date_to: date) -> OperationFilters:
    """Repassa direto pra `operations_queries.filter_options` - a mesma função que alimenta os
    dropdowns da tela de Operação (já cobre regionais, modelos de equipe, setores, assuntos,
    diagnósticos, responsáveis, status, status de SLA, prioridades etc.). Nenhuma lógica nova:
    resolve o problema de a IA não conseguir listar valores cadastrados sem reimplementar nada."""
    return operations_queries.filter_options(db, date_from, date_to, user, scope="period")


BacklogHistoryMetric = Literal["backlog", "backlog_atrasado"]
BacklogHistoryGroupBy = Literal["none", "regional", "team_model", "sector"]


def backlog_history(
    db: Session,
    user: User,
    *,
    metric: BacklogHistoryMetric,
    date_from: date,
    date_to: date,
    group_by: BacklogHistoryGroupBy = "none",
    sector_filter: dict | None = None,
) -> list[dict]:
    """Série histórica de backlog/backlog atrasado, lida do snapshot diário (ver
    `operations/backlog_snapshot.py`). Limitações que a IA precisa saber (documentadas na
    descrição da ferramenta, ver schemas.py): (1) só tem dado a partir do dia em que o job de
    captura entrou em produção, sem retroatividade nenhuma; (2) só quebra/filtra por "regional",
    "team_model" ou "sector" - o snapshot já vem pré-agregado por essas três dimensões, não por
    qualquer uma como as outras ferramentas.

    `sector_filter` é `{"operator": "contains"|"starts_with"|"ends_with"|"not_equals", "value":
    str}` - reaproveita `_text_filter_conditions` (mesma sintaxe/escape das outras ferramentas),
    fixando o campo em "sector"."""
    # Snapshot não passa por `_dimension_conditions` (não é uma O.S. individual) - o escopo
    # regional do usuário precisa ser aplicado aqui manualmente, mesma regra de sempre.
    allowed_regionals = effective_managed_regionals(user.managed_regional, user.managed_regionals)
    conditions = [OperationBacklogSnapshot.snapshot_date.between(date_from, date_to)]
    if allowed_regionals:
        conditions.append(OperationBacklogSnapshot.regional.in_(allowed_regionals))
    elif user.role == "regional_manager_viewer":
        conditions.append(OperationBacklogSnapshot.id == -1)
    if sector_filter:
        condition = _text_operator_condition(OperationBacklogSnapshot.sector, sector_filter["operator"], sector_filter["value"])
        if condition is not None:
            conditions.append(condition)

    count_column = (
        OperationBacklogSnapshot.backlog_atrasado_count
        if metric == "backlog_atrasado"
        else OperationBacklogSnapshot.backlog_count
    )
    group_column = {
        "regional": OperationBacklogSnapshot.regional,
        "team_model": OperationBacklogSnapshot.team_model,
        "sector": OperationBacklogSnapshot.sector,
    }.get(group_by)

    columns = (OperationBacklogSnapshot.snapshot_date, group_column) if group_column is not None else (OperationBacklogSnapshot.snapshot_date,)
    rows = db.execute(select(*columns, func.sum(count_column)).where(*conditions).group_by(*columns)).all()

    results = []
    for row in rows:
        item = {"snapshot_date": row[0], "quantity": int(row[-1] or 0)}
        if group_column is not None:
            item["group"] = row[1]
        results.append(item)
    results.sort(key=lambda item: (item["snapshot_date"], item.get("group") or ""))
    return results


def warranty_analytics_for_ai(
    db: Session,
    user: User,
    *,
    date_from: date,
    date_to: date,
    period_basis: str = "opened",
    denominator: str = "active_origins",
    origin_excluded_diagnoses: list[str] | None = None,
    **filters,
) -> dict:
    """Reaproveita `operations_queries.warranty_analytics` - a mesma função que alimenta a aba
    Garantias da tela - sem nenhuma lógica nova. Só troca os itens individuais: a versão da tela
    embute o objeto completo de 2 O.S. (origem e retorno) por item, pro drill clicável; aqui isso
    seria pesado demais pra IA (mesmo motivo de `search_orders` ser paginado) - fica só os campos
    planos de cada garantia encontrada."""
    result = operations_queries.warranty_analytics(
        db,
        date_from,
        date_to,
        user,
        period_basis=period_basis,
        denominator=denominator,
        origin_excluded_diagnoses=origin_excluded_diagnoses,
        **filters,
    )
    result["items"] = [
        {key: value for key, value in item.items() if key not in ("origin_order", "return_order")}
        for item in result["items"]
    ]
    return result
