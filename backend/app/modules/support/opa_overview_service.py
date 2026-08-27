"""Regras de negócio da Visão Geral do SGP Suporte (OPA Suite).

Mantido fora de `router.py` por regra do AGENTS.md (regra de negócio pesada não
fica na rota). Este módulo só lê `SupportOpaAttendance` já normalizado — nenhuma
chamada à API do OPA Suite acontece aqui.
"""
from __future__ import annotations

from datetime import date as date_type, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .models import SupportOpaAttendance
from .opa_filters import (
    DATE_BASIS_COLUMNS,
    DEFAULT_DATE_BASIS,
    SUPPORT_TIMEZONE_NAME,
    OpaAttendanceFilters,
    apply_opa_attendance_filters,
)


def metric_comparison(current: float | int | None, previous: float | int | None) -> dict[str, Any]:
    if current is None and previous is None:
        return {"current": None, "previous": None, "absolute_change": None, "percentage_change": None}
    if previous in (None, 0):
        percentage_change = 0.0 if current in (None, 0) else None
    else:
        percentage_change = ((float(current or 0) - float(previous)) / float(previous)) * 100
    return {
        "current": current,
        "previous": previous,
        "absolute_change": (current or 0) - (previous or 0),
        "percentage_change": percentage_change,
    }


def coverage(count: int, total: int) -> dict[str, Any]:
    """Denominador explícito pra qualquer média que possa ter cobertura parcial
    do histórico (norma de qualidade de dados, seção 1: "todo percentual precisa
    dizer sobre o que foi calculado"). `count` é quantos registros do universo
    `total` realmente entraram na média (têm valor não-nulo) — nunca confundir
    com o `total` do recorte de filtros inteiro."""
    return {
        "count": count,
        "total": total,
        "percentage": (count / total * 100) if total else None,
    }


def imported_data_window(db: Session) -> dict[str, Any]:
    """Janela real da base importada — MIN/MAX/COUNT sobre a tabela INTEIRA, sem
    nenhum filtro de período aplicado. Existe pra separar duas perguntas que o
    usuário costuma confundir na hora de comparar com o painel oficial do OPA:
    "o que eu pedi no filtro" (pode incluir datas sem dado nenhum aqui) vs "o que
    a base realmente tem importado" (norma de qualidade de dados, seção 7 —
    divergência por ausência de histórico não é bug, mas precisa ficar visível
    pra não ser confundida com um). Nunca usar `apply_opa_attendance_filters`
    aqui de propósito — isso é sobre a base inteira, não sobre o recorte
    escolhido."""
    row = db.execute(
        select(
            func.min(SupportOpaAttendance.opened_at).label("min_opened_at"),
            func.max(SupportOpaAttendance.opened_at).label("max_opened_at"),
            func.min(SupportOpaAttendance.closed_at).label("min_closed_at"),
            func.max(SupportOpaAttendance.closed_at).label("max_closed_at"),
            func.count(SupportOpaAttendance.id).label("total"),
        )
    ).one()
    return {
        "min_opened_at": row.min_opened_at,
        "max_opened_at": row.max_opened_at,
        "min_closed_at": row.min_closed_at,
        "max_closed_at": row.max_closed_at,
        "total_attendances": int(row.total or 0),
    }


def overview_metrics(db: Session, filters: OpaAttendanceFilters) -> dict[str, Any]:
    """Métricas base do período (comportamento idêntico ao `_overview_metrics`
    anterior em `router.py`), acrescido de `average_tmr_seconds` — único campo
    novo aqui, os demais preservam nome e cálculo originais.

    Achado da auditoria de performance 2026-08-27 (`EXPLAIN ANALYZE` real):
    `COUNT(DISTINCT attendant_id)` e `COUNT(DISTINCT department_id)` juntos no
    MESMO `SELECT` forçam o Postgres a fazer `Sort Method: external merge,
    Disk` (~155ms de ~176ms da consulta inteira, medido ao vivo) - dois
    `COUNT(DISTINCT)` de colunas diferentes não cabem no mesmo `HashAggregate`.
    Reescrito como duas subconsultas escalares (`SELECT DISTINCT col ...`),
    que o planejador resolve com `HashAggregate` em memória em vez de ordenar
    em disco - mesmo resultado, ~110ms medido (ver auditoria de performance).
    """
    closed_case = case((SupportOpaAttendance.closed_at.isnot(None), 1), else_=0)
    distinct_attendants_subquery = apply_opa_attendance_filters(
        select(SupportOpaAttendance.attendant_id)
        .where(SupportOpaAttendance.attendant_id.isnot(None))
        .distinct(),
        filters,
    ).subquery()
    distinct_departments_subquery = apply_opa_attendance_filters(
        select(SupportOpaAttendance.department_id)
        .where(SupportOpaAttendance.department_id.isnot(None))
        .distinct(),
        filters,
    ).subquery()
    statement = apply_opa_attendance_filters(
        select(
            func.count(SupportOpaAttendance.id).label("total"),
            func.sum(closed_case).label("closed"),
            func.avg(case((SupportOpaAttendance.closed_at.isnot(None), SupportOpaAttendance.tma_seconds))).label("avg_duration"),
            func.avg(SupportOpaAttendance.rating).label("avg_rating"),
            func.avg(SupportOpaAttendance.tmr_seconds).label("avg_tmr"),
            func.avg(SupportOpaAttendance.tmr_all_responses_seconds).label("avg_tmr_all"),
            # COUNT ignora NULL igual AVG — dá o denominador real da média de
            # TMR geral sem precisar de uma segunda consulta. Ver `coverage()`.
            func.count(SupportOpaAttendance.tmr_all_responses_seconds).label("tmr_all_count"),
            select(func.count()).select_from(distinct_attendants_subquery).scalar_subquery().label("distinct_attendants"),
            select(func.count()).select_from(distinct_departments_subquery).scalar_subquery().label("distinct_departments"),
        ),
        filters,
    )
    row = db.execute(statement).one()
    total = int(row.total or 0)
    closed = int(row.closed or 0)
    open_total = max(0, total - closed)
    return {
        "total_attendances": total,
        "closed_attendances": closed,
        "open_attendances": open_total,
        "closure_rate": (closed / total) * 100 if total else 0.0,
        "average_duration_seconds": float(row.avg_duration) if row.avg_duration is not None else None,
        "average_rating": float(row.avg_rating) if row.avg_rating is not None else None,
        "average_tmr_seconds": float(row.avg_tmr) if row.avg_tmr is not None else None,
        "average_tmr_all_responses_seconds": float(row.avg_tmr_all) if row.avg_tmr_all is not None else None,
        "tmr_all_responses_coverage": coverage(int(row.tmr_all_count or 0), total),
        "distinct_attendants": int(row.distinct_attendants or 0),
        "distinct_departments": int(row.distinct_departments or 0),
    }


def channel_counts(db: Session, filters: OpaAttendanceFilters) -> list[dict[str, Any]]:
    """Idêntico ao `_channel_counts` anterior em `router.py` — sem alteração."""
    channel_label = func.coalesce(SupportOpaAttendance.channel, "Não identificado")
    rows = db.execute(
        apply_opa_attendance_filters(
            select(channel_label.label("channel"), func.count(SupportOpaAttendance.id).label("total"))
            .group_by(channel_label)
            .order_by(func.count(SupportOpaAttendance.id).desc()),
            filters,
        )
    ).all()
    return [{"channel": row.channel, "total": int(row.total or 0)} for row in rows]


def status_breakdown(db: Session, filters: OpaAttendanceFilters) -> list[dict[str, Any]]:
    """Contagem por status bruto do OPA Suite (AG/EA/F/PS/...). O rótulo
    amigável é responsabilidade do frontend (`opaStatusLabel`), pra não manter
    dois mapas de tradução divergentes."""
    status_label = func.coalesce(SupportOpaAttendance.status, "Não informado")
    rows = db.execute(
        apply_opa_attendance_filters(
            select(status_label.label("status"), func.count(SupportOpaAttendance.id).label("total"))
            .group_by(status_label)
            .order_by(func.count(SupportOpaAttendance.id).desc()),
            filters,
        )
    ).all()
    return [{"status": row.status, "total": int(row.total or 0)} for row in rows]


def customer_metrics(db: Session, filters: OpaAttendanceFilters, *, top_limit: int = 10) -> dict[str, Any]:
    """Clientes únicos e reincidência DENTRO DO PERÍODO consultado (não é a
    janela de reincidência configurável da Gamificação — aqui é só "mais de um
    atendimento no mesmo período filtrado", conforme escopo aprovado da Fase 2).

    Achado da auditoria de performance 2026-08-27: a versão anterior trazia
    TODAS as linhas agrupadas por cliente pra Python (25.492 linhas medidas ao
    vivo num recorte de 31 dias) só pra contar/somar/ordenar - exatamente o
    que `COUNT`/`SUM`/`ORDER BY ... LIMIT` já fazem em SQL. Agora só os
    `top_limit` primeiros cruzam a fronteira banco↔aplicação; o resto vira 2
    agregados escalares sobre a mesma subconsulta agrupada."""
    per_customer = apply_opa_attendance_filters(
        select(
            SupportOpaAttendance.customer_id.label("customer_id"),
            func.max(SupportOpaAttendance.customer_name).label("customer_name"),
            func.count(SupportOpaAttendance.id).label("total"),
        )
        .where(SupportOpaAttendance.customer_id.isnot(None), SupportOpaAttendance.customer_id != "")
        .group_by(SupportOpaAttendance.customer_id),
        filters,
    ).subquery()
    recurring_case = case((per_customer.c.total > 1, 1), else_=0)

    summary = db.execute(
        select(
            func.count().label("unique_customers"),
            func.sum(recurring_case).label("recurring_customers"),
            func.coalesce(func.sum(per_customer.c.total), 0).label("total_attendances"),
        ).select_from(per_customer)
    ).one()
    unique_customers = int(summary.unique_customers or 0)
    recurring_customers = int(summary.recurring_customers or 0)
    total_attendances = int(summary.total_attendances or 0)

    top_rows = db.execute(
        select(per_customer.c.customer_id, per_customer.c.customer_name, per_customer.c.total)
        .where(per_customer.c.total > 1)
        .order_by(per_customer.c.total.desc())
        .limit(top_limit)
    ).all()

    return {
        "unique_customers": unique_customers,
        "recurring_customers": recurring_customers,
        "recurring_customers_percentage": (recurring_customers / unique_customers * 100) if unique_customers else 0.0,
        "average_attendances_per_customer": (total_attendances / unique_customers) if unique_customers else 0.0,
        "top_recurring_customers": [
            {
                "customer_id": row.customer_id,
                "customer_name": row.customer_name,
                "total": int(row.total or 0),
            }
            for row in top_rows
        ],
    }


def top_reasons(db: Session, filters: OpaAttendanceFilters, *, limit: int = 5) -> list[dict[str, Any]]:
    """Motivos com mais volume, com TMA/TMR médios — ajuda a achar "alto volume
    e alto tempo médio" pedido na Fase 2. Herda a limitação já conhecida (ver
    docs/plano-analise-opa-suite-atendimentos.md): só o primeiro motivo de cada
    atendimento é normalizado, atendimentos com múltiplos motivos aparecem só
    uma vez, pelo primeiro."""
    label = func.coalesce(SupportOpaAttendance.reason_name, "Não informado")
    statement = apply_opa_attendance_filters(
        select(
            label.label("label"),
            func.count(SupportOpaAttendance.id).label("total"),
            func.avg(case((SupportOpaAttendance.closed_at.isnot(None), SupportOpaAttendance.tma_seconds))).label("avg_tma_seconds"),
            func.avg(SupportOpaAttendance.tmr_seconds).label("avg_tmr_seconds"),
            func.avg(SupportOpaAttendance.tmr_all_responses_seconds).label("avg_tmr_all_responses_seconds"),
            func.count(SupportOpaAttendance.tmr_all_responses_seconds).label("tmr_all_count"),
        )
        .group_by(label)
        .order_by(func.count(SupportOpaAttendance.id).desc())
        .limit(limit),
        filters,
    )
    rows = db.execute(statement).all()
    return [
        {
            "label": row.label,
            "total": int(row.total or 0),
            "average_tma_seconds": float(row.avg_tma_seconds) if row.avg_tma_seconds is not None else None,
            "average_tmr_seconds": float(row.avg_tmr_seconds) if row.avg_tmr_seconds is not None else None,
            "average_tmr_all_responses_seconds": (
                float(row.avg_tmr_all_responses_seconds) if row.avg_tmr_all_responses_seconds is not None else None
            ),
            "tmr_all_responses_coverage": coverage(int(row.tmr_all_count or 0), int(row.total or 0)),
        }
        for row in rows
    ]


def _seconds_diff_expression(db: Session, end_column, start_column):
    """`end_column - start_column` em segundos, nos dois dialetos - mesmo padrão
    de dialeto explícito já usado em `_local_day_expression` (Postgres em
    produção, SQLite na suíte de testes).

    SQLite: `strftime('%s', ...)` (segundos inteiros desde a época, texto) em
    vez de `julianday()` (dias fracionários em ponto flutuante) - achado real
    ao rodar a suíte de testes: `julianday()` introduzia ruído de
    ponto-flutuante (~0,00002%, ex. 599.9999843... em vez de 600.0) porque a
    parte inteira enorme (dias desde 4714 a.C.) dilui a precisão do `double`
    disponível pra hora do dia. `strftime('%s', ...)` é inteiro exato."""
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        return sa.extract("epoch", end_column - start_column)
    return sa.cast(func.strftime("%s", end_column), sa.Integer) - sa.cast(func.strftime("%s", start_column), sa.Integer)


def average_first_response_seconds(db: Session, filters: OpaAttendanceFilters) -> float | None:
    """Achado da auditoria de performance 2026-08-27: a versão anterior trazia
    TODO par (opened_at, first_response_at) pra Python (23.819 linhas medidas
    ao vivo num recorte de 31 dias) só pra subtrair e tirar a média - de
    propósito, porque a aritmética de data no SQLite dos testes não bate 1:1
    com o Postgres de produção. Resolvido com `_seconds_diff_expression`
    (mesmo padrão de branch-por-dialeto já usado em `_local_day_expression`
    logo abaixo) em vez de deixar de usar SQL - agora só o escalar final
    cruza a fronteira banco↔aplicação."""
    diff_seconds = _seconds_diff_expression(db, SupportOpaAttendance.first_response_at, SupportOpaAttendance.opened_at)
    statement = apply_opa_attendance_filters(
        select(func.avg(diff_seconds)).where(
            SupportOpaAttendance.first_response_at.isnot(None),
            diff_seconds >= 0,
        ),
        filters,
    )
    result = db.execute(statement).scalar()
    return float(result) if result is not None else None


def bot_human_metrics(db: Session, filters: OpaAttendanceFilters) -> dict[str, Any]:
    """Percentuais calculados só sobre atendimentos CLASSIFICADOS
    (`handled_by_bot IS NOT NULL`) — atendimentos antigos sem classificação
    (NULL) entram em `unclassified_attendances`, nunca no denominador do
    percentual, pra não distorcer a proporção real bot/humano."""
    classified_case = case((SupportOpaAttendance.handled_by_bot.isnot(None), 1), else_=0)
    bot_case = case((SupportOpaAttendance.handled_by_bot.is_(True), 1), else_=0)
    human_case = case((SupportOpaAttendance.reached_human.is_(True), 1), else_=0)
    handoff_case = case((SupportOpaAttendance.bot_to_human_handoff.is_(True), 1), else_=0)
    statement = apply_opa_attendance_filters(
        select(
            func.count(SupportOpaAttendance.id).label("total"),
            func.sum(classified_case).label("classified"),
            func.sum(bot_case).label("with_bot"),
            func.sum(human_case).label("reached_human"),
            func.sum(handoff_case).label("handoff"),
        ),
        filters,
    )
    row = db.execute(statement).one()
    total = int(row.total or 0)
    classified = int(row.classified or 0)
    with_bot = int(row.with_bot or 0)
    reached_human = int(row.reached_human or 0)
    handoff = int(row.handoff or 0)

    def percentage(count: int) -> float | None:
        return (count / classified * 100) if classified else None

    return {
        "total_attendances": total,
        "classified_attendances": classified,
        "unclassified_attendances": total - classified,
        "with_bot": with_bot,
        "with_bot_percentage": percentage(with_bot),
        "reached_human": reached_human,
        "reached_human_percentage": percentage(reached_human),
        "bot_to_human_handoff": handoff,
        "bot_to_human_handoff_percentage": percentage(handoff),
    }


def _local_day_expression(db: Session, column):
    """Expressão SQL que reduz um timestamp UTC ao DIA LOCAL de operação.

    `America/Porto_Velho` é UTC-4 fixo, sem horário de verão (mesma premissa que
    `opa_filters.opa_period_bounds` já usa pra converter o período do filtro), o
    que permite uma expressão simples nos dois dialetos — Postgres em produção e
    SQLite na suíte de testes. Sem isso, agrupar por dia cairia no fuso do banco
    e o gráfico mostraria atendimentos da madrugada no dia errado, contradizendo
    o total do mesmo recorte já exibido nos cards.
    """
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        return sa.cast(column.op("AT TIME ZONE")(sa.literal(SUPPORT_TIMEZONE_NAME)), sa.Date)
    return func.date(column, "-4 hours")


def daily_timeseries(db: Session, filters: OpaAttendanceFilters) -> list[dict[str, Any]]:
    """Série diária do recorte atual, pro gráfico de tendência.

    Usa exatamente os mesmos filtros das demais métricas da tela
    (`apply_opa_attendance_filters`) — o gráfico é uma decomposição do mesmo
    universo dos cards, nunca um número calculado por outro caminho (norma de
    qualidade de dados, seção "fonte única de regra").

    Dias sem nenhum atendimento aparecem com zero em vez de sumir da série: um
    buraco no eixo esconderia justamente o dia parado, que costuma ser o mais
    relevante de enxergar.
    """
    date_column = DATE_BASIS_COLUMNS.get(filters.date_basis, DATE_BASIS_COLUMNS[DEFAULT_DATE_BASIS])
    bucket = _local_day_expression(db, date_column).label("day")
    closed_case = case((SupportOpaAttendance.closed_at.isnot(None), 1), else_=0)

    statement = apply_opa_attendance_filters(
        select(
            bucket,
            func.count(SupportOpaAttendance.id).label("total"),
            func.sum(closed_case).label("closed"),
            func.avg(case((SupportOpaAttendance.closed_at.isnot(None), SupportOpaAttendance.tma_seconds))).label("avg_tma"),
            func.avg(SupportOpaAttendance.tmr_seconds).label("avg_tmr"),
            func.avg(SupportOpaAttendance.tmr_all_responses_seconds).label("avg_tmr_all"),
            func.count(SupportOpaAttendance.tmr_all_responses_seconds).label("tmr_all_count"),
            func.avg(SupportOpaAttendance.rating).label("avg_rating"),
        ),
        filters,
    ).group_by(bucket).order_by(bucket)

    rows = {}
    for row in db.execute(statement).all():
        day = row.day
        # SQLite devolve a data como texto; Postgres devolve `date`.
        key = day if isinstance(day, date_type) else date_type.fromisoformat(str(day))
        total = int(row.total or 0)
        closed = int(row.closed or 0)
        rows[key] = {
            "day": key,
            "total": total,
            "closed": closed,
            "open": max(0, total - closed),
            "average_duration_seconds": float(row.avg_tma) if row.avg_tma is not None else None,
            "average_tmr_seconds": float(row.avg_tmr) if row.avg_tmr is not None else None,
            "average_tmr_all_responses_seconds": float(row.avg_tmr_all) if row.avg_tmr_all is not None else None,
            "average_rating": float(row.avg_rating) if row.avg_rating is not None else None,
            "tmr_all_responses_coverage": coverage(int(row.tmr_all_count or 0), total),
        }

    if not filters.date_from or not filters.date_to:
        return [rows[key] for key in sorted(rows)]

    series: list[dict[str, Any]] = []
    cursor = filters.date_from
    while cursor <= filters.date_to:
        series.append(
            rows.get(
                cursor,
                {
                    "day": cursor,
                    "total": 0,
                    "closed": 0,
                    "open": 0,
                    "average_duration_seconds": None,
                    "average_tmr_seconds": None,
                    "average_tmr_all_responses_seconds": None,
                    "average_rating": None,
                    "tmr_all_responses_coverage": coverage(0, 0),
                },
            )
        )
        cursor += timedelta(days=1)
    return series


def expanded_overview(db: Session, filters: OpaAttendanceFilters) -> dict[str, Any]:
    """Monta a resposta completa de `/opa/overview`. Os campos que já existiam
    (`total_attendances` ... `distinct_departments`) preservam exatamente o
    mesmo cálculo e formato (`SupportOpaMetricComparison`) de antes da Fase 2 —
    só troca a origem (agora vem de `overview_metrics`, migrado 1:1 de
    `_overview_metrics` do router). `average_tmr_seconds` é o único campo de
    comparação novo; o resto das seções novas (clientes, motivos, status,
    bot/humano) traz só o período atual, sem duplicar a consulta pro período
    anterior — não há pedido de comparação histórica pra elas nesta fase."""
    previous_filters = filters.previous_period()
    current = overview_metrics(db, filters)
    previous = overview_metrics(db, previous_filters)
    return {
        "total_attendances": metric_comparison(current["total_attendances"], previous["total_attendances"]),
        "closed_attendances": metric_comparison(current["closed_attendances"], previous["closed_attendances"]),
        "open_attendances": metric_comparison(current["open_attendances"], previous["open_attendances"]),
        "closure_rate": metric_comparison(current["closure_rate"], previous["closure_rate"]),
        "average_duration_seconds": metric_comparison(
            current["average_duration_seconds"], previous["average_duration_seconds"]
        ),
        "average_rating": metric_comparison(current["average_rating"], previous["average_rating"]),
        "average_tmr_seconds": metric_comparison(current["average_tmr_seconds"], previous["average_tmr_seconds"]),
        "average_tmr_all_responses_seconds": metric_comparison(
            current["average_tmr_all_responses_seconds"], previous["average_tmr_all_responses_seconds"]
        ),
        "tmr_all_responses_coverage": current["tmr_all_responses_coverage"],
        "distinct_attendants": metric_comparison(current["distinct_attendants"], previous["distinct_attendants"]),
        "distinct_departments": metric_comparison(current["distinct_departments"], previous["distinct_departments"]),
        "by_channel": channel_counts(db, filters),
        "by_status": status_breakdown(db, filters),
        "customers": customer_metrics(db, filters),
        "top_reasons": top_reasons(db, filters),
        "average_first_response_seconds": average_first_response_seconds(db, filters),
        "bot_human": bot_human_metrics(db, filters),
        "imported_data_window": imported_data_window(db),
    }
