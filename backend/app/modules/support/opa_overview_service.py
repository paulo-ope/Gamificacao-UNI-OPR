"""Regras de negócio da Visão Geral do SGP Suporte (OPA Suite).

Mantido fora de `router.py` por regra do AGENTS.md (regra de negócio pesada não
fica na rota). Este módulo só lê `SupportOpaAttendance` já normalizado — nenhuma
chamada à API do OPA Suite acontece aqui.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .models import SupportOpaAttendance
from .opa_filters import OpaAttendanceFilters, apply_opa_attendance_filters


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


def overview_metrics(db: Session, filters: OpaAttendanceFilters) -> dict[str, Any]:
    """Métricas base do período (comportamento idêntico ao `_overview_metrics`
    anterior em `router.py`), acrescido de `average_tmr_seconds` — único campo
    novo aqui, os demais preservam nome e cálculo originais."""
    closed_case = case((SupportOpaAttendance.closed_at.isnot(None), 1), else_=0)
    statement = apply_opa_attendance_filters(
        select(
            func.count(SupportOpaAttendance.id).label("total"),
            func.sum(closed_case).label("closed"),
            func.avg(case((SupportOpaAttendance.closed_at.isnot(None), SupportOpaAttendance.tma_seconds))).label("avg_duration"),
            func.avg(SupportOpaAttendance.rating).label("avg_rating"),
            func.avg(SupportOpaAttendance.tmr_seconds).label("avg_tmr"),
            func.avg(SupportOpaAttendance.tmr_all_responses_seconds).label("avg_tmr_all"),
            func.count(func.distinct(SupportOpaAttendance.attendant_id)).label("distinct_attendants"),
            func.count(func.distinct(SupportOpaAttendance.department_id)).label("distinct_departments"),
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
    atendimento no mesmo período filtrado", conforme escopo aprovado da Fase 2)."""
    base = (
        select(
            SupportOpaAttendance.customer_id.label("customer_id"),
            func.max(SupportOpaAttendance.customer_name).label("customer_name"),
            func.count(SupportOpaAttendance.id).label("total"),
        )
        .where(SupportOpaAttendance.customer_id.isnot(None), SupportOpaAttendance.customer_id != "")
        .group_by(SupportOpaAttendance.customer_id)
    )
    rows = db.execute(apply_opa_attendance_filters(base, filters)).all()

    unique_customers = len(rows)
    recurring_rows = [row for row in rows if (row.total or 0) > 1]
    recurring_customers = len(recurring_rows)
    top_recurring = sorted(recurring_rows, key=lambda row: row.total or 0, reverse=True)[:top_limit]

    return {
        "unique_customers": unique_customers,
        "recurring_customers": recurring_customers,
        "recurring_customers_percentage": (recurring_customers / unique_customers * 100) if unique_customers else 0.0,
        "average_attendances_per_customer": (sum(row.total or 0 for row in rows) / unique_customers) if unique_customers else 0.0,
        "top_recurring_customers": [
            {
                "customer_id": row.customer_id,
                "customer_name": row.customer_name,
                "total": int(row.total or 0),
            }
            for row in top_recurring
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
        }
        for row in rows
    ]


def average_first_response_seconds(db: Session, filters: OpaAttendanceFilters) -> float | None:
    """Calculado em Python (não em SQL) de propósito: `first_response_at -
    opened_at` é aritmética de data que o SQLite (usado nos testes) não resolve
    da mesma forma que o Postgres — subtrair em Python evita depender de função
    específica de dialeto."""
    statement = apply_opa_attendance_filters(
        select(SupportOpaAttendance.opened_at, SupportOpaAttendance.first_response_at).where(
            SupportOpaAttendance.first_response_at.isnot(None)
        ),
        filters,
    )
    rows = db.execute(statement).all()
    deltas = [
        (first_response_at - opened_at).total_seconds()
        for opened_at, first_response_at in rows
        if opened_at and first_response_at
    ]
    deltas = [delta for delta in deltas if delta >= 0]
    if not deltas:
        return None
    return sum(deltas) / len(deltas)


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
        "distinct_attendants": metric_comparison(current["distinct_attendants"], previous["distinct_attendants"]),
        "distinct_departments": metric_comparison(current["distinct_departments"], previous["distinct_departments"]),
        "by_channel": channel_counts(db, filters),
        "by_status": status_breakdown(db, filters),
        "customers": customer_metrics(db, filters),
        "top_reasons": top_reasons(db, filters),
        "average_first_response_seconds": average_first_response_seconds(db, filters),
        "bot_human": bot_human_metrics(db, filters),
    }
