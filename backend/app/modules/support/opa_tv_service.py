"""Snapshot da TV do SGP Suporte.

Regra de negócio da tela de televisão fica aqui (AGENTS.md): a página só formata. Quase tudo é
reaproveitado de `opa_overview_service` (mesmo universo e mesmos filtros da Visão Geral) e dos
serviços IXC já existentes. Só duas consultas são próprias deste módulo: o ritmo por hora e o
ranking de atendentes humanos.

Cada bloco é calculado isoladamente: se um falhar (ex.: radar IXC sem baseline), os demais seguem
e o bloco vem como `None` + registrado em `unavailable`. Nunca devolve "tudo normal" por engano.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.services.calculation import get_setting, upsert_setting
from app.services.opa_scheduler import SUPPORT_OPA_SYNC_CONSECUTIVE_FAILURES_KEY, SUPPORT_OPA_SYNC_LAST_SUCCESS_AT_KEY

from . import (
    ixc_n1,
    ixc_operational_radar,
    opa_attendant_overrides,
    opa_overview_service,
)
from .models import SupportOpaAttendance, SupportOpaDimension
from .opa_filters import (
    SUPPORT_TIMEZONE,
    SUPPORT_TIMEZONE_NAME,
    OpaAttendanceFilters,
    apply_opa_attendance_filters,
    opa_period_bounds,
)

logger = logging.getLogger("support.tv")

# Meta operacional do TMR geral (conta resposta de bot): 02:20. Pode ser sobrescrita pela
# configuração do sistema sem novo deploy; não há tela de edição por enquanto.
TMR_TARGET_SECONDS_KEY = "support_tv_tmr_target_seconds"
TMR_TARGET_SECONDS_DEFAULT = 140
TMR_TARGET_SECONDS_MIN = 10
TMR_TARGET_SECONDS_MAX = 3600

# Departamentos que a TV considera (ids separados por vírgula, mesmo formato do filtro
# `department_id` da tela). Vazio = todos os departamentos.
TV_DEPARTMENT_IDS_KEY = "support_tv_department_ids"
MAX_TV_DEPARTMENTS = 50

# TV do Agendamento: o recorte é FIXO (sem configuração) = todo departamento do OPA cujo nome contém
# "agendament" (Agendamentos, (JPA) Agendamento, (RMM) Agendamento...). Casar por nome faz uma filial
# nova entrar sozinha, sem deploy.
SCHEDULING_DEPARTMENT_NAME_MARKER = "agendament"
# Ranking da TV do Agendamento mostra a equipe toda (a do Suporte mostra só o top 5).
SCHEDULING_ATTENDANTS_LIMIT = 12
# Id que nenhum atendimento tem: sem departamento de agendamento conhecido a TV fica zerada, nunca
# cai em "todos os departamentos" (lista vazia significa todos).
_NO_DEPARTMENT_SENTINEL = "__sem_departamento_agendamento__"

# "Em andamento agora" = sem encerramento e aberto nas últimas 24 h.
OPEN_NOW_LOOKBACK_HOURS = 24
# Ritmo por hora: hoje contra a média do mesmo dia da semana nas últimas N semanas.
HOURLY_BASELINE_WEEKS = 4
TOP_ATTENDANTS_LIMIT = 5
TOP_REASONS_LIMIT = 5

# Fila de espera (TV do Agendamento): atendimento `AG` ("aguardando" no OPA) ainda sem atendente. A API
# do OPA mantém `AG` parado por semanas (dado sujo, ver docs/opa-suite-api-referencia.md), então só
# conta o que abriu nas últimas 24 h - o mesmo corte do "em andamento agora".
IN_PROGRESS_STATUS = "EA"
QUEUE_WAITING_STATUS = "AG"
QUEUE_LIST_LIMIT = 6


def tmr_target_seconds(db: Session) -> int:
    try:
        value = int(get_setting(db, TMR_TARGET_SECONDS_KEY, str(TMR_TARGET_SECONDS_DEFAULT)))
    except ValueError:
        return TMR_TARGET_SECONDS_DEFAULT
    if not TMR_TARGET_SECONDS_MIN <= value <= TMR_TARGET_SECONDS_MAX:
        return TMR_TARGET_SECONDS_DEFAULT
    return value


def tv_department_ids(db: Session) -> list[str]:
    raw = get_setting(db, TV_DEPARTMENT_IDS_KEY, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def department_options(db: Session) -> list[dict[str, str]]:
    """Departamentos que já apareceram em atendimentos importados (mesma origem do filtro de
    departamento da tela de Suporte). Rótulo cai para o id só se nunca houve nome."""
    rows = db.execute(
        select(SupportOpaAttendance.department_id, func.max(SupportOpaAttendance.department_name))
        .where(SupportOpaAttendance.department_id.isnot(None), SupportOpaAttendance.department_id != "")
        .group_by(SupportOpaAttendance.department_id)
        .limit(500)
    ).all()
    options = [{"id": str(department_id), "name": (name or "").strip() or str(department_id)} for department_id, name in rows]
    return sorted(options, key=lambda option: option["name"].casefold())


def scheduling_department_ids(db: Session) -> list[str]:
    """Departamentos de agendamento do OPA (fixos por nome). Nunca vazio: ver `_NO_DEPARTMENT_SENTINEL`."""
    ids = [
        option["id"]
        for option in department_options(db)
        if SCHEDULING_DEPARTMENT_NAME_MARKER in option["name"].casefold()
    ]
    return ids or [_NO_DEPARTMENT_SENTINEL]


def save_tv_department_ids(db: Session, department_ids: list[str]) -> list[str]:
    """Valida e grava a lista. Só aceita departamentos conhecidos: um id digitado errado não pode
    virar uma TV zerada sem aviso. Lista vazia = todos."""
    cleaned = list(dict.fromkeys(item.strip() for item in department_ids if item and item.strip()))
    if len(cleaned) > MAX_TV_DEPARTMENTS:
        raise ValueError(f"Selecione no máximo {MAX_TV_DEPARTMENTS} departamentos.")
    known = {option["id"] for option in department_options(db)}
    unknown = [item for item in cleaned if item not in known or "," in item]
    if unknown:
        raise ValueError("Departamento desconhecido na seleção da TV.")
    upsert_setting(
        db,
        TV_DEPARTMENT_IDS_KEY,
        ",".join(cleaned),
        description="Departamentos do OPA Suite exibidos na TV do SGP Suporte (ids separados por vírgula; vazio = todos).",
    )
    return cleaned


def _department_scope(department_ids: list[str] | None) -> str | None:
    return ",".join(department_ids) if department_ids else None


def tmr_status(current_seconds: float | None, target_seconds: int) -> str:
    if current_seconds is None:
        return "no_data"
    return "ok" if current_seconds <= target_seconds else "above"


def _local_hour_expression(db: Session, column):
    """Hora local (0-23) de um timestamp UTC - mesmo padrão por dialeto de
    `opa_overview_service._local_day_expression` (Postgres em produção, SQLite nos testes)."""
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        return sa.cast(sa.extract("hour", column.op("AT TIME ZONE")(sa.literal(SUPPORT_TIMEZONE_NAME))), sa.Integer)
    return sa.cast(func.strftime("%H", column, "-4 hours"), sa.Integer)


def _as_date(value: Any) -> date:
    # SQLite devolve a data como texto; Postgres devolve `date`.
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def open_now(db: Session, now: datetime, department_ids: list[str] | None = None) -> int:
    since = now - timedelta(hours=OPEN_NOW_LOOKBACK_HOURS)
    statement = select(func.count(SupportOpaAttendance.id)).where(
        SupportOpaAttendance.closed_at.is_(None),
        SupportOpaAttendance.opened_at >= since,
        SupportOpaAttendance.opened_at <= now,
    )
    if department_ids:
        statement = statement.where(SupportOpaAttendance.department_id.in_(department_ids))
    return int(db.scalar(statement) or 0)


def build_kpis(db: Session, today: date, now: datetime, department_ids: list[str] | None = None) -> dict[str, Any]:
    today_filters = OpaAttendanceFilters(date_from=today, date_to=today, department_id=_department_scope(department_ids))
    previous_filters = today_filters.previous_period()
    current = opa_overview_service.overview_metrics(db, today_filters)
    previous = opa_overview_service.overview_metrics(db, previous_filters)
    target = tmr_target_seconds(db)
    tmr_current = current["average_tmr_all_responses_seconds"]
    return {
        "total_today": current["total_attendances"],
        "previous_day_total": previous["total_attendances"],
        "closed_today": current["closed_attendances"],
        "closure_rate": current["closure_rate"] if current["total_attendances"] else None,
        "open_now": open_now(db, now, department_ids),
        "tmr_all_responses": {
            "current_seconds": tmr_current,
            "previous_seconds": previous["average_tmr_all_responses_seconds"],
            "target_seconds": target,
            "status": tmr_status(tmr_current, target),
            "coverage": current["tmr_all_responses_coverage"],
        },
        "average_tmr_human_seconds": current["average_tmr_seconds"],
        "previous_average_tmr_human_seconds": previous["average_tmr_seconds"],
        "average_first_response_seconds": opa_overview_service.average_first_response_seconds(db, today_filters),
        "average_rating": current["average_rating"],
        "previous_average_rating": previous["average_rating"],
    }


def hourly_pace(db: Session, today: date, now_local: datetime, department_ids: list[str] | None = None) -> dict[str, Any]:
    """Atendimentos abertos por hora local hoje contra a média do mesmo dia da semana nas
    `HOURLY_BASELINE_WEEKS` semanas anteriores. Só semanas que têm dado entram na média (semana
    sem nenhum atendimento é lacuna de importação, não "zero atendimentos")."""
    baseline_days = [today - timedelta(weeks=week) for week in range(1, HOURLY_BASELINE_WEEKS + 1)]
    window_start, _ = opa_period_bounds(min(baseline_days), min(baseline_days))
    _, window_end = opa_period_bounds(today, today)

    day_bucket = opa_overview_service._local_day_expression(db, SupportOpaAttendance.opened_at).label("day")
    hour_bucket = _local_hour_expression(db, SupportOpaAttendance.opened_at).label("hour")
    statement = select(day_bucket, hour_bucket, func.count(SupportOpaAttendance.id).label("total")).where(
        SupportOpaAttendance.opened_at >= window_start, SupportOpaAttendance.opened_at < window_end
    )
    if department_ids:
        statement = statement.where(SupportOpaAttendance.department_id.in_(department_ids))
    rows = db.execute(statement.group_by(day_bucket, hour_bucket)).all()
    counts: dict[tuple[date, int], int] = {(_as_date(row.day), int(row.hour)): int(row.total or 0) for row in rows}

    days_with_data = [day for day in baseline_days if any(key[0] == day for key in counts)]
    current_hour = now_local.hour
    points = []
    for hour in range(24):
        baseline = (
            sum(counts.get((day, hour), 0) for day in days_with_data) / len(days_with_data)
            if days_with_data
            else None
        )
        points.append(
            {
                "hour": hour,
                "today": counts.get((today, hour), 0) if hour <= current_hour else None,
                "baseline_average": round(baseline, 2) if baseline is not None else None,
            }
        )
    return {"current_hour": current_hour, "baseline_weeks_used": len(days_with_data), "points": points}


def _bot_attendant_ids(db: Session) -> set[str]:
    """Atendentes que são agente virtual: cadastro manual ativo OU `tipo="bot"` da dimensão do OPA
    (mesma regra única de `opa_attendant_overrides.resolve_attendant_type`)."""
    overrides = opa_attendant_overrides.load_active_overrides(db)
    bot_ids: set[str] = set()
    for source_id, payload in db.execute(
        select(SupportOpaDimension.source_id, SupportOpaDimension.payload_json).where(
            SupportOpaDimension.dimension_type == "user"
        )
    ).all():
        opa_tipo = payload.get("tipo") if isinstance(payload, dict) else None
        if opa_attendant_overrides.resolve_attendant_type(source_id, opa_tipo, overrides) == "bot":
            bot_ids.add(source_id)
    bot_ids.update(
        attendant_id
        for attendant_id in overrides
        if opa_attendant_overrides.resolve_attendant_type(attendant_id, None, overrides) == "bot"
    )
    return bot_ids


def in_progress_by_attendant(db: Session, now: datetime, department_ids: list[str] | None) -> dict[str, int]:
    """Atendimentos em andamento AGORA por atendente: status `EA`, sem encerramento e abertos nas últimas
    24 h (o OPA mantém `EA` parado por meses - mesmo corte do "em andamento agora")."""
    statement = (
        select(SupportOpaAttendance.attendant_id, func.count(SupportOpaAttendance.id))
        .where(
            SupportOpaAttendance.status == IN_PROGRESS_STATUS,
            SupportOpaAttendance.closed_at.is_(None),
            SupportOpaAttendance.attendant_id.isnot(None),
            SupportOpaAttendance.attendant_id != "",
            SupportOpaAttendance.opened_at >= now - timedelta(hours=OPEN_NOW_LOOKBACK_HOURS),
            SupportOpaAttendance.opened_at <= now,
        )
        .group_by(SupportOpaAttendance.attendant_id)
    )
    if department_ids:
        statement = statement.where(SupportOpaAttendance.department_id.in_(department_ids))
    return {attendant_id: int(total) for attendant_id, total in db.execute(statement).all()}


def top_attendants(
    db: Session,
    filters: OpaAttendanceFilters,
    *,
    limit: int = TOP_ATTENDANTS_LIMIT,
    in_progress: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Ranking de atendentes HUMANOS por volume do dia. Agente virtual fica de fora: TMR humano e
    avaliação não descrevem um bot, e ele sozinho dominaria o topo."""
    closed_case = sa.case((SupportOpaAttendance.closed_at.isnot(None), 1), else_=0)
    statement = (
        select(
            SupportOpaAttendance.attendant_id.label("attendant_id"),
            func.max(SupportOpaAttendance.attendant_name).label("attendant_name"),
            func.count(SupportOpaAttendance.id).label("total"),
            func.sum(closed_case).label("closed"),
            # TMR do ranking = TMR GERAL (conta a resposta do bot também), a pedido da gestão: é o mesmo
            # critério do TMR principal da TV. NÃO é o TMR só-humano (`tmr_seconds`).
            func.avg(SupportOpaAttendance.tmr_all_responses_seconds).label("avg_tmr"),
            func.avg(SupportOpaAttendance.rating).label("avg_rating"),
        )
        .where(SupportOpaAttendance.attendant_id.isnot(None), SupportOpaAttendance.attendant_id != "")
        .group_by(SupportOpaAttendance.attendant_id)
        .order_by(func.count(SupportOpaAttendance.id).desc(), SupportOpaAttendance.attendant_id)
    )
    bot_ids = _bot_attendant_ids(db)
    if bot_ids:
        statement = statement.where(SupportOpaAttendance.attendant_id.notin_(bot_ids))
    # Painel "em atendimento agora" ordena por quem tem mais atendimentos abertos: o corte de `limit`
    # só vale depois de juntar, em Python, com quem tem algo em andamento mas nada aberto hoje.
    rows = db.execute(apply_opa_attendance_filters(statement if in_progress is not None else statement.limit(limit), filters)).all()
    extra_ids = [] if in_progress is None else [item for item in in_progress if item not in {row.attendant_id for row in rows} and item not in bot_ids]

    names = {
        source_id: name
        for source_id, name in db.execute(
            select(SupportOpaDimension.source_id, SupportOpaDimension.name).where(
                SupportOpaDimension.dimension_type == "user",
                SupportOpaDimension.source_id.in_([row.attendant_id for row in rows] + extra_ids),
            )
        ).all()
    }

    def readable(row) -> str:
        for candidate in (row.attendant_name, names.get(row.attendant_id)):
            value = (candidate or "").strip()
            if value and value != row.attendant_id:
                return value
        return "Atendente sem nome"

    result = [
        {
            "attendant_id": row.attendant_id,
            "name": readable(row),
            "total": int(row.total or 0),
            "closed": int(row.closed or 0),
            "average_tmr_seconds": float(row.avg_tmr) if row.avg_tmr is not None else None,
            "average_rating": float(row.avg_rating) if row.avg_rating is not None else None,
            "in_progress": in_progress.get(row.attendant_id, 0) if in_progress is not None else None,
        }
        for row in rows
    ]
    if in_progress is None:
        return result
    result.extend(
        {
            "attendant_id": item,
            "name": (names.get(item) or "").strip() or "Atendente sem nome",
            "total": 0,
            "closed": 0,
            "average_tmr_seconds": None,
            "average_rating": None,
            "in_progress": in_progress[item],
        }
        for item in extra_ids
    )
    result.sort(key=lambda entry: (-(entry["in_progress"] or 0), -entry["total"], entry["attendant_id"]))
    return result[:limit]


def waiting_queue(db: Session, now: datetime, department_ids: list[str] | None = None) -> dict[str, Any]:
    """Clientes aguardando na fila dos departamentos (status `AG`, sem atendente, sem encerramento),
    do mais antigo para o mais novo, com o tempo de espera em segundos. O nome sai abreviado
    ("Aline S."): a TV fica à vista de todos e o nome completo não acrescenta nada à fila."""
    since = now - timedelta(hours=OPEN_NOW_LOOKBACK_HOURS)
    conditions = [
        SupportOpaAttendance.status == QUEUE_WAITING_STATUS,
        SupportOpaAttendance.closed_at.is_(None),
        sa.or_(SupportOpaAttendance.attendant_id.is_(None), SupportOpaAttendance.attendant_id == ""),
        SupportOpaAttendance.opened_at >= since,
        SupportOpaAttendance.opened_at <= now,
    ]
    if department_ids:
        conditions.append(SupportOpaAttendance.department_id.in_(department_ids))
    total = int(db.scalar(select(func.count(SupportOpaAttendance.id)).where(*conditions)) or 0)
    rows = db.execute(
        select(SupportOpaAttendance.protocol, SupportOpaAttendance.customer_name, SupportOpaAttendance.opened_at)
        .where(*conditions)
        .order_by(SupportOpaAttendance.opened_at)
        .limit(QUEUE_LIST_LIMIT)
    ).all()

    def waited(opened_at: datetime) -> int:
        opened = opened_at if opened_at.tzinfo else opened_at.replace(tzinfo=timezone.utc)
        return max(0, int((now - opened).total_seconds()))

    return {
        "total": total,
        "longest_wait_seconds": waited(rows[0].opened_at) if rows else None,
        "items": [
            {"label": _short_customer_name(row.customer_name) or f"Protocolo {row.protocol}", "wait_seconds": waited(row.opened_at)}
            for row in rows
        ],
    }


# A fila muda em segundos e a importação do OPA roda de tempos em tempos: ler só o banco mostraria quem
# já foi atendido (ou esconderia quem acabou de entrar). Por isso a fila vem AO VIVO da API do OPA, com
# cache curto para várias TVs abertas não multiplicarem as chamadas.
QUEUE_LIVE_CACHE_SECONDS = 10
_queue_cache_lock = threading.Lock()
_queue_cache: dict[str, Any] = {"at": 0.0, "key": None, "records": None}


def _fetch_live_waiting(client, department_ids: list[str], now: datetime) -> list[dict[str, Any]]:
    key = ",".join(sorted(department_ids))
    with _queue_cache_lock:
        if _queue_cache["key"] == key and _queue_cache["records"] is not None and time.monotonic() - _queue_cache["at"] < QUEUE_LIVE_CACHE_SECONDS:
            return _queue_cache["records"]
        since = (now - timedelta(hours=OPEN_NOW_LOOKBACK_HOURS)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        records: list[dict[str, Any]] = []
        for department_id in department_ids:
            # `setor` e `status` são filtros respeitados pela API (docs/opa-suite-api-referencia.md).
            body = {"filter": {"status": QUEUE_WAITING_STATUS, "setor": department_id, "dataInicialAbertura": since}, "options": {"limit": 200, "skip": 0}}
            page, _ = client._extract_records(client._get_with_body("/api/v1/atendimento", json_body=body))
            records.extend(page)
        _queue_cache.update(at=time.monotonic(), key=key, records=records)
        return records


def waiting_queue_live(db: Session, client, now: datetime, department_ids: list[str]) -> dict[str, Any]:
    """Mesmo contrato de `waiting_queue`, mas lendo o OPA ao vivo. Levanta exceção se o OPA não responder
    (quem chama cai no banco)."""
    waiting = []
    for record in _fetch_live_waiting(client, department_ids, now):
        opened_raw = record.get("date")
        if record.get("id_atendente") or record.get("status") != QUEUE_WAITING_STATUS or not opened_raw:
            continue
        opened = datetime.fromisoformat(str(opened_raw).replace("Z", "+00:00"))
        opened = opened if opened.tzinfo else opened.replace(tzinfo=timezone.utc)
        if now - timedelta(hours=OPEN_NOW_LOOKBACK_HOURS) <= opened <= now:
            waiting.append((opened, record))
    waiting.sort(key=lambda item: item[0])
    shown = waiting[:QUEUE_LIST_LIMIT]
    customer_ids = [str(rec.get("id_cliente")) for _, rec in shown if rec.get("id_cliente")]
    names = dict(
        db.execute(
            select(SupportOpaDimension.source_id, SupportOpaDimension.name).where(
                SupportOpaDimension.dimension_type == "customer", SupportOpaDimension.source_id.in_(customer_ids)
            )
        ).all()
    ) if customer_ids else {}
    return {
        "total": len(waiting),
        "longest_wait_seconds": max(0, int((now - shown[0][0]).total_seconds())) if shown else None,
        "items": [
            {
                "label": _short_customer_name(names.get(str(rec.get("id_cliente")))) or f"Protocolo {rec.get('protocolo')}",
                "wait_seconds": max(0, int((now - opened).total_seconds())),
            }
            for opened, rec in shown
        ],
    }


def _queue_block(db: Session, now: datetime, department_ids: list[str], opa_client) -> dict[str, Any]:
    if opa_client is not None and department_ids and department_ids != [_NO_DEPARTMENT_SENTINEL]:
        try:
            return waiting_queue_live(db, opa_client, now, department_ids)
        except Exception:  # noqa: BLE001 - OPA fora do ar: cai no banco em vez de apagar o painel
            logger.warning("Fila ao vivo do OPA indisponível; usando o banco local.", exc_info=True)
    return waiting_queue(db, now, department_ids)


def _short_customer_name(name: str | None) -> str | None:
    parts = (name or "").split()
    if not parts:
        return None
    first = parts[0].capitalize()
    return f"{first} {parts[-1][0].upper()}." if len(parts) > 1 else first


def n1_today(db: Session, today: date) -> dict[str, Any]:
    summary = ixc_n1.n1_summary(db, date_from=today, date_to=today)
    return {
        "operational": summary["operational"],
        "financial": summary["financial"],
        "total": summary["total"],
        "previous_total": summary["previous_operational"] + summary["previous_financial"],
    }


def sync_freshness(db: Session) -> dict[str, Any]:
    raw = get_setting(db, SUPPORT_OPA_SYNC_LAST_SUCCESS_AT_KEY, "")
    last_success_at = None
    if raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            last_success_at = parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
        except ValueError:
            last_success_at = None
    try:
        failures = int(get_setting(db, SUPPORT_OPA_SYNC_CONSECUTIVE_FAILURES_KEY, "0") or "0")
    except ValueError:
        failures = 0
    return {"last_success_at": last_success_at, "consecutive_failures": failures}


def department_filter_view(db: Session, department_ids: list[str]) -> dict[str, Any]:
    names_by_id = {option["id"]: option["name"] for option in department_options(db)}
    return {
        "department_ids": department_ids,
        "department_names": [names_by_id.get(item, item) for item in department_ids if item != _NO_DEPARTMENT_SENTINEL],
    }


def _isolated(db: Session, name: str, unavailable: list[str], builder: Callable[[], Any]) -> Any:
    """Roda um bloco sem derrubar os outros. Em falha, desfaz a transação (a sessão fica
    inutilizável após erro de SQL), registra e devolve `None`."""
    try:
        return builder()
    except Exception:  # noqa: BLE001 - bloco de painel não pode derrubar a TV inteira
        logger.exception("Bloco da TV de Suporte falhou: %s", name)
        db.rollback()
        unavailable.append(name)
        return None


def build_snapshot(db: Session, *, now: datetime | None = None, scope: Literal["support", "scheduling"] = "support", opa_client=None) -> dict[str, Any]:
    """`scope="scheduling"`: recorte fixo nos departamentos de agendamento, ranking com a equipe toda e fila.
    Nas duas TVs o painel de atendentes mostra os atendimentos em andamento agora, não o volume do dia."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    now_local = now.astimezone(SUPPORT_TIMEZONE)
    today = now_local.date()
    unavailable: list[str] = []
    resolve_departments = (lambda: scheduling_department_ids(db)) if scope == "scheduling" else (lambda: tv_department_ids(db))
    department_ids = _isolated(db, "department_filter", unavailable, resolve_departments) or []
    attendants_limit = SCHEDULING_ATTENDANTS_LIMIT if scope == "scheduling" else TOP_ATTENDANTS_LIMIT
    today_filters = OpaAttendanceFilters(date_from=today, date_to=today, department_id=_department_scope(department_ids))

    kpis = _isolated(db, "kpis", unavailable, lambda: build_kpis(db, today, now, department_ids))
    hourly = _isolated(db, "hourly", unavailable, lambda: hourly_pace(db, today, now_local, department_ids))
    reasons = _isolated(
        db,
        "top_reasons",
        unavailable,
        lambda: [
            {"label": item["label"], "total": item["total"]}
            for item in opa_overview_service.top_reasons(db, today_filters, limit=TOP_REASONS_LIMIT)
        ],
    )
    channels = _isolated(
        db,
        "channels",
        unavailable,
        lambda: [
            {"label": item["channel"], "total": item["total"]}
            for item in opa_overview_service.channel_counts(db, today_filters)
        ],
    )
    bot_human = _isolated(db, "bot_human", unavailable, lambda: opa_overview_service.bot_human_metrics(db, today_filters))
    in_progress_map = lambda: in_progress_by_attendant(db, now, department_ids)  # noqa: E731
    attendants = _isolated(db, "attendants", unavailable, lambda: top_attendants(db, today_filters, limit=attendants_limit, in_progress=in_progress_map()))
    # Radar: só protocolos operacionais (assunto 90) e só de hoje - ver ixc_operational_radar.
    radar = _isolated(db, "radar", unavailable, lambda: ixc_operational_radar.build_radar(db, now)) or {
        "scope": "operational",
        "baseline_weeks_used": 0,
        "pace": None,
        "bursts": None,
        "cities_at_risk": None,
    }
    # N1 (protocolos do IXC) é do Suporte; a TV do Agendamento não mostra.
    n1 = None if scope == "scheduling" else _isolated(db, "n1", unavailable, lambda: n1_today(db, today))
    queue = (
        _isolated(db, "queue", unavailable, lambda: _queue_block(db, now, department_ids, opa_client)) if scope == "scheduling" else None
    )
    sync = _isolated(db, "sync", unavailable, lambda: sync_freshness(db)) or {"last_success_at": None, "consecutive_failures": 0}

    return {
        "generated_at": now,
        "local_date": today,
        "department_filter": _isolated(db, "department_names", unavailable, lambda: department_filter_view(db, department_ids))
        or {"department_ids": department_ids, "department_names": []},
        "kpis": kpis,
        "hourly": hourly,
        "top_reasons": reasons,
        "channels": channels,
        "bot_human": bot_human,
        "attendants": attendants,
        "radar": radar,
        "n1": n1,
        "queue": queue,
        "sync": sync,
        "unavailable": unavailable,
    }
