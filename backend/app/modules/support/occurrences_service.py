"""Registros de Ocorrências do Suporte Interno: atendimentos do IXC (`su_ticket`) do assunto 211
("Registro de Ocorrência"), com o relato (`menssagem`), a filial/regional e, vindos de
`SupportOccurrenceDetail`, o diagnóstico e a finalização (horário + relato).

Só leitura. A regional vem de `id_filial` normalizada na importação (com fallback pelo contrato do
cliente). Ocorrência "em aberto" = sem finalização: nem mensagem de finalização sincronizada nem
`su_status = 'S'` no ticket.

Horários: seguem a convenção do módulo (relógio do IXC gravado como UTC), por isso "agora" é o
horário de Porto Velho marcado como UTC e as datas/horas são lidas sem conversão de fuso."""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.services.calculation_closure import now_porto_velho

from .ixc_ticket_queries import _apply_period, _previous_period_bounds
from .models import SupportIxcTicket, SupportOccurrenceDetail

OCCURRENCE_SUBJECT_ID = "211"
NO_REGIONAL_LABEL = "NAO IDENTIFICADO"
NO_DIAGNOSIS_LABEL = "Sem diagnóstico"
FINALIZED_STATUS = "S"
# Teto de linhas lidas por consulta: o assunto 211 tem dezenas de registros por dia.
MAX_ROWS = 20000
TOP_LIMIT = 8
OPEN_LIST_LIMIT = 50
FINALIZATION_LIST_LIMIT = 20

StatusFilter = Literal["all", "open", "finalized"]


def _ixc_now() -> datetime:
    """Horário atual do IXC (Porto Velho) marcado como UTC, comparável com os horários gravados."""
    return now_porto_velho().replace(tzinfo=timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _minutes_between(start: datetime | None, end: datetime | None) -> float | None:
    start, end = _as_utc(start), _as_utc(end)
    if start is None or end is None or end < start:
        return None
    return round((end - start).total_seconds() / 60, 1)


def _is_finalized(ticket: SupportIxcTicket, detail: SupportOccurrenceDetail | None) -> bool:
    if detail is not None and detail.finalized_at is not None:
        return True
    status = (detail.ticket_status if detail is not None else None) or ticket.sub_status
    return status == FINALIZED_STATUS


def _base_query(
    *,
    date_from: date | None,
    date_to: date | None,
    regional: str | None,
    search: str | None,
    allowed_regionals: list[str],
    deny_all: bool,
):
    query = (
        select(SupportIxcTicket, SupportOccurrenceDetail)
        .outerjoin(SupportOccurrenceDetail, SupportOccurrenceDetail.source_id == SupportIxcTicket.source_id)
        .where(SupportIxcTicket.subject_id == OCCURRENCE_SUBJECT_ID)
    )
    if deny_all:
        return query.where(SupportIxcTicket.id.is_(None))
    if allowed_regionals:
        query = query.where(SupportIxcTicket.regional.in_(allowed_regionals))
    if regional:
        query = query.where(SupportIxcTicket.regional == regional)
    if term := (search or "").strip():
        like = f"%{term}%"
        query = query.where(
            or_(
                SupportIxcTicket.report.ilike(like),
                SupportIxcTicket.protocol.ilike(like),
                SupportIxcTicket.customer_name.ilike(like),
                SupportOccurrenceDetail.finalization_report.ilike(like),
            )
        )
    return _apply_period(query, SupportIxcTicket.created_at, date_from, date_to)


def _load(db: Session, **filters: Any) -> list[dict[str, Any]]:
    rows = db.execute(
        _base_query(**filters).order_by(SupportIxcTicket.created_at.desc(), SupportIxcTicket.id.desc()).limit(MAX_ROWS)
    ).all()
    now = _ixc_now()
    items = []
    for ticket, detail in rows:
        finalized = _is_finalized(ticket, detail)
        finalized_at = _as_utc(detail.finalized_at) if detail is not None else None
        items.append(
            {
                "id": ticket.id,
                "source_id": ticket.source_id,
                "protocol": ticket.protocol,
                "created_at": ticket.created_at,
                "regional": ticket.regional or NO_REGIONAL_LABEL,
                "city": ticket.city,
                "neighborhood": ticket.neighborhood,
                "customer_name": ticket.customer_name,
                "status": ticket.status,
                "report": ticket.report,
                "diagnosis_id": detail.diagnosis_id if detail is not None else None,
                "diagnosis_name": (detail.diagnosis_name if detail is not None else None) or None,
                "is_open": not finalized,
                "finalized_at": finalized_at,
                "finalization_report": detail.finalization_report if detail is not None else None,
                "resolution_minutes": _minutes_between(ticket.created_at, finalized_at) if finalized else None,
                "open_minutes": None if finalized else _minutes_between(ticket.created_at, now),
            }
        )
    return items


def _matches(item: dict[str, Any], status: StatusFilter, diagnosis: str | None, hour: int | None = None) -> bool:
    if hour is not None and (item["created_at"] is None or _as_utc(item["created_at"]).hour != hour):
        return False
    if status == "open" and not item["is_open"]:
        return False
    if status == "finalized" and item["is_open"]:
        return False
    if diagnosis:
        # O diagnóstico só existe a partir da finalização: em aberto nunca é "sem diagnóstico".
        if item["is_open"]:
            return False
        label = item["diagnosis_name"] or NO_DIAGNOSIS_LABEL
        if label != diagnosis:
            return False
    return True


def _regional_counts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"regional": name, "count": count}
        for name, count in Counter(item["regional"] for item in items).most_common()
    ]


def list_occurrences(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    regional: str | None = None,
    search: str | None = None,
    status: StatusFilter = "all",
    diagnosis: str | None = None,
    hour: int | None = None,
    allowed_regionals: list[str] | None = None,
    deny_all: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Página de ocorrências (mais recentes primeiro) + total por regional do MESMO recorte
    (sem o filtro de regional, para os cartões continuarem mostrando as outras regionais)."""
    scope = {"allowed_regionals": allowed_regionals or [], "deny_all": deny_all}
    everywhere = _load(db, date_from=date_from, date_to=date_to, regional=None, search=search, **scope)
    scoped = [item for item in everywhere if _matches(item, status, diagnosis, hour)]
    selected = [item for item in scoped if not regional or item["regional"] == regional]
    return {
        "total": len(selected),
        "items": selected[offset : offset + limit],
        "by_regional": _regional_counts(scoped),
    }


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def _delta_pct(current: int, previous: int) -> float | None:
    # Mesma regra de `ixc_ticket_queries._deviation_pct`: sem amostra mínima anterior não há percentual honesto.
    if previous < 10:
        return None
    return round((current - previous) / previous * 100, 1)


def _group_stats(items: list[dict[str, Any]], key: str, fallback: str, total: int) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        groups[item[key] or fallback].append(item)
    result = []
    for name, members in groups.items():
        resolution = [m["resolution_minutes"] for m in members if m["resolution_minutes"] is not None]
        result.append(
            {
                "name": name,
                "total": len(members),
                "open": sum(1 for m in members if m["is_open"]),
                "finalized": sum(1 for m in members if not m["is_open"]),
                "share_pct": round(len(members) / total * 100, 1) if total else 0.0,
                "avg_resolution_minutes": _avg(resolution),
            }
        )
    result.sort(key=lambda row: (-row["total"], row["name"]))
    return result


def overview(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    regional: str | None = None,
    allowed_regionals: list[str] | None = None,
    deny_all: bool = False,
) -> dict[str, Any]:
    """Visão geral analítica do período: KPIs, regional mais afetada, diagnóstico mais usado,
    cruzamento regional x diagnóstico, fluxo diário, horário de abertura, ocorrências em aberto
    (mais antigas primeiro) e as finalizações mais recentes com horário e relato."""
    scope = {"allowed_regionals": allowed_regionals or [], "deny_all": deny_all}
    items = _load(db, date_from=date_from, date_to=date_to, regional=regional, search=None, **scope)
    total = len(items)
    open_items = [i for i in items if i["is_open"]]
    finalized_items = [i for i in items if not i["is_open"]]
    resolution = [i["resolution_minutes"] for i in finalized_items if i["resolution_minutes"] is not None]

    previous_total = None
    bounds = _previous_period_bounds(date_from, date_to)
    if bounds is not None:
        previous_total = len(
            _load(db, date_from=bounds[0], date_to=bounds[1], regional=regional, search=None, **scope)
        )

    by_regional = [
        {"regional": row["name"], **{key: value for key, value in row.items() if key != "name"}}
        for row in _group_stats(items, "regional", NO_REGIONAL_LABEL, total)
    ]
    # Diagnóstico só entra a partir da finalização: as em aberto ficam fora destes números (não são
    # "sem diagnóstico", só ainda não têm um) e as participações são sobre as finalizadas.
    by_diagnosis = _group_stats(finalized_items, "diagnosis_name", NO_DIAGNOSIS_LABEL, len(finalized_items))

    top_regionals = [row["regional"] for row in by_regional[:TOP_LIMIT]]
    top_diagnoses = [row["name"] for row in by_diagnosis[:TOP_LIMIT]]
    cross = Counter((i["regional"], i["diagnosis_name"] or NO_DIAGNOSIS_LABEL) for i in finalized_items)
    matrix = [
        {"regional": reg, "diagnosis": diag, "count": cross[(reg, diag)]}
        for reg in top_regionals
        for diag in top_diagnoses
        if cross[(reg, diag)]
    ]

    opened_per_day = Counter(_as_utc(i["created_at"]).date() for i in items if i["created_at"])
    finalized_per_day = Counter(i["finalized_at"].date() for i in finalized_items if i["finalized_at"])
    open_per_day = Counter(_as_utc(i["created_at"]).date() for i in open_items if i["created_at"])
    resolution_per_day: dict[date, list[float]] = defaultdict(list)
    for item in finalized_items:
        if item["created_at"] and item["resolution_minutes"] is not None:
            resolution_per_day[_as_utc(item["created_at"]).date()].append(item["resolution_minutes"])
    daily = []
    cursor = date_from
    while cursor <= date_to:
        daily.append(
            {
                "day": cursor,
                "opened": opened_per_day.get(cursor, 0),
                "finalized": finalized_per_day.get(cursor, 0),
                # Das abertas NESTE dia, quantas seguem em aberto / tempo médio das já finalizadas.
                "open": open_per_day.get(cursor, 0),
                "avg_resolution_minutes": _avg(resolution_per_day.get(cursor, [])),
            }
        )
        cursor += timedelta(days=1)

    by_hour_counter = Counter(_as_utc(i["created_at"]).hour for i in items if i["created_at"])
    by_hour = [{"hour": hour, "count": by_hour_counter.get(hour, 0)} for hour in range(24)]

    open_sorted = sorted(open_items, key=lambda i: i["open_minutes"] if i["open_minutes"] is not None else -1, reverse=True)
    recent_finalizations = sorted(
        (i for i in finalized_items if i["finalized_at"] is not None),
        key=lambda i: i["finalized_at"],
        reverse=True,
    )

    return {
        "kpis": {
            "total": total,
            "previous_total": previous_total,
            "delta_pct": _delta_pct(total, previous_total) if previous_total is not None else None,
            "open": len(open_items),
            "finalized": len(finalized_items),
            "finalization_rate_pct": round(len(finalized_items) / total * 100, 1) if total else None,
            "avg_resolution_minutes": _avg(resolution),
            "median_resolution_minutes": round(statistics.median(resolution), 1) if resolution else None,
            "oldest_open_minutes": open_sorted[0]["open_minutes"] if open_sorted else None,
            "without_diagnosis": sum(1 for i in finalized_items if not i["diagnosis_name"]),
        },
        "top_regional": by_regional[0] if by_regional else None,
        "top_open_regional": (
            max(
                (row for row in by_regional if row["open"]),
                key=lambda row: (row["open"], row["total"]),
                default=None,
            )
        ),
        "top_diagnosis": next((row for row in by_diagnosis if row["name"] != NO_DIAGNOSIS_LABEL), None),
        "by_regional": by_regional,
        "by_diagnosis": by_diagnosis,
        "matrix": matrix,
        "matrix_regionals": top_regionals,
        "matrix_diagnoses": top_diagnoses,
        "daily": daily,
        "by_hour": by_hour,
        "open_items": open_sorted[:OPEN_LIST_LIMIT],
        "recent_finalizations": recent_finalizations[:FINALIZATION_LIST_LIMIT],
    }
