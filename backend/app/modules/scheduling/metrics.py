"""Motor de cálculo dos KPIs do módulo de Agendamento (ver docs/estudo-kpis-agendamento.md).

Tudo roda sobre as tabelas locais sincronizadas - nenhuma chamada ao IXC aqui. As medidas de tempo
de resposta saem em duas réguas:
- corrida: diferença simples entre abertura e primeiro agendamento;
- útil: desconta o tempo fora do expediente configurado do setor (por padrão, todos os dias
  07:30-20:00) - uma O.S. aberta às 23h e agendada às 07h40 do dia seguinte conta 10 minutos
  úteis, não 8h40. É a régua usada pelo SLA, porque é a única justa com o turno real do setor.

Decisão de agregação (achado do estudo): média sozinha mente em distribuição de cauda longa -
todo indicador de tempo reporta mediana, P90 e média juntos, mais a distribuição em faixas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AppSetting
from app.modules.scheduling.models import SchedulingEvent, SchedulingOperator, SchedulingOrder, SchedulingTechnician
from app.services.calculation_closure import PORTO_VELHO_TZ, now_porto_velho
from app.services.regional import REGIONAL_CODE_MAP

# Rótulo de exibição de cada `su_oss_evento` sincronizado (ver SYNCED_EVENT_TYPES em models.py) -
# usado na visão de log completo por O.S. (pedido do dono do produto: "clicando no mais detalhado
# eu queria ter todo o log da O.S.").
EVENT_TYPE_LABELS = {
    "1": "Abertura",
    "5": "Agendamento",
    "10": "Reagendar",
    "6": "Fechamento",
    "2": "Alteração",
    "3": "Reabertura",
    "4": "Alteração de setor",
    "7": "Em Análise",
    "8": "Assumido",
    "9": "Em Execução",
}


def _local(value: datetime) -> datetime:
    """Componentes de hora em Porto Velho, sem tzinfo (pronto para aritmética/comparação com
    `business_minutes_between`). NUNCA usar `.replace(tzinfo=None)` direto num datetime vindo do
    banco - ele chega com tzinfo=UTC (a sessão do Postgres), então isso preservaria os componentes
    em UTC, não em horário local, e todo o cálculo de expediente ficaria 4h deslocado."""
    return value.astimezone(PORTO_VELHO_TZ).replace(tzinfo=None)


DEFAULT_SETTINGS = {
    "scheduling_sla_target_pct": "80",
    "scheduling_sla_minutes": "60",
    "scheduling_business_start": "07:30",
    "scheduling_business_end": "20:00",
    # Dias da semana ativos do setor, 0=segunda ... 6=domingo. Hoje o setor opera todos os dias.
    "scheduling_business_days": "0,1,2,3,4,5,6",
    "scheduling_daily_goal": "40",
}

TTFA_BUCKETS = [
    ("ate_15min", "Até 15 min", 15),
    ("15min_1h", "15 min – 1h", 60),
    ("1h_4h", "1h – 4h", 240),
    ("4h_24h", "4h – 24h", 1440),
    ("acima_24h", "Mais de 24h", None),
]

BACKLOG_BUCKETS = [
    ("hoje", "Aberta hoje", 1),
    ("1_2_dias", "1–2 dias", 3),
    ("3_7_dias", "3–7 dias", 8),
    ("acima_7_dias", "Mais de 7 dias", None),
]


def load_settings(db: Session) -> dict[str, str]:
    rows = db.execute(select(AppSetting).where(AppSetting.key.in_(DEFAULT_SETTINGS.keys()))).scalars()
    stored = {row.key: row.value for row in rows}
    return {**DEFAULT_SETTINGS, **stored}


def save_settings(db: Session, values: dict[str, str]) -> dict[str, str]:
    for key, value in values.items():
        if key not in DEFAULT_SETTINGS:
            continue
        row = db.execute(select(AppSetting).where(AppSetting.key == key)).scalar_one_or_none()
        if row:
            row.value = str(value)
        else:
            db.add(AppSetting(key=key, value=str(value), description="Configuração do módulo de Agendamento."))
    db.commit()
    return load_settings(db)


def _parse_business_window(settings: dict[str, str]) -> tuple[dtime, dtime, set[int]]:
    def parse_time(raw: str, fallback: dtime) -> dtime:
        try:
            hours, minutes = raw.strip().split(":")
            return dtime(int(hours), int(minutes))
        except (ValueError, AttributeError):
            return fallback

    start = parse_time(settings["scheduling_business_start"], dtime(7, 30))
    end = parse_time(settings["scheduling_business_end"], dtime(20, 0))
    try:
        days = {int(d) for d in settings["scheduling_business_days"].split(",") if d.strip() != ""}
    except ValueError:
        days = {0, 1, 2, 3, 4, 5, 6}
    return start, end, days or {0, 1, 2, 3, 4, 5, 6}


def business_minutes_between(start: datetime, end: datetime, window_start: dtime, window_end: dtime, active_days: set[int]) -> float:
    """Minutos úteis entre dois instantes, contando só o expediente configurado."""
    if end <= start:
        return 0.0
    total = 0.0
    day = start.date()
    # Guarda de sanidade: nenhuma O.S. real fica anos sem agendar; evita loop degenerado.
    last_day = min(end.date(), start.date() + timedelta(days=400))
    while day <= last_day:
        if day.weekday() in active_days:
            day_open = datetime.combine(day, window_start)
            day_close = datetime.combine(day, window_end)
            overlap_start = max(start, day_open)
            overlap_end = min(end, day_close)
            if overlap_end > overlap_start:
                total += (overlap_end - overlap_start).total_seconds() / 60
        day += timedelta(days=1)
    return total


@dataclass
class SchedulingFilters:
    date_from: date
    date_to: date
    filial_ids: list[str] = field(default_factory=list)
    setor_ids: list[str] = field(default_factory=list)
    assunto_ids: list[str] = field(default_factory=list)
    operator_ids: list[int] = field(default_factory=list)


def _percentile(sorted_values: list[float], pct: float) -> float | None:
    if not sorted_values:
        return None
    index = min(len(sorted_values) - 1, max(0, round((pct / 100) * (len(sorted_values) - 1))))
    return sorted_values[index]


def _stats(values: list[float]) -> dict:
    if not values:
        return {"median": None, "p90": None, "average": None}
    ordered = sorted(values)
    return {
        "median": round(_percentile(ordered, 50), 1),
        "p90": round(_percentile(ordered, 90), 1),
        "average": round(sum(ordered) / len(ordered), 1),
    }


def _cohort_query(filters: SchedulingFilters):
    stmt = select(SchedulingOrder).where(
        SchedulingOrder.opened_at >= datetime.combine(filters.date_from, dtime.min, tzinfo=PORTO_VELHO_TZ),
        SchedulingOrder.opened_at <= datetime.combine(filters.date_to, dtime.max, tzinfo=PORTO_VELHO_TZ),
    )
    if filters.filial_ids:
        stmt = stmt.where(SchedulingOrder.filial_id.in_(filters.filial_ids))
    if filters.setor_ids:
        stmt = stmt.where(SchedulingOrder.setor_id.in_(filters.setor_ids))
    if filters.assunto_ids:
        stmt = stmt.where(SchedulingOrder.assunto_id.in_(filters.assunto_ids))
    if filters.operator_ids:
        stmt = stmt.where(SchedulingOrder.first_operator_id.in_(filters.operator_ids))
    return stmt


def _resolve_operator_names(db: Session, operator_ids: set[int]) -> dict[int, str]:
    if not operator_ids:
        return {}
    rows = db.execute(select(SchedulingOperator).where(SchedulingOperator.ixc_user_id.in_(operator_ids))).scalars()
    return {row.ixc_user_id: row.name for row in rows}


def _resolve_technician_names(db: Session, technician_ids: set[int]) -> dict[int, str]:
    if not technician_ids:
        return {}
    rows = db.execute(select(SchedulingTechnician).where(SchedulingTechnician.ixc_funcionario_id.in_(technician_ids))).scalars()
    return {row.ixc_funcionario_id: row.name for row in rows}


def _team_operator_ids(db: Session) -> set[int]:
    rows = db.execute(select(SchedulingOperator).where(SchedulingOperator.is_team_member.is_(True))).scalars()
    return {row.ixc_user_id for row in rows}


def _classify_reschedule_origin(operator_id: int | None, team_ids: set[int]) -> str:
    """Heurística (não há campo de canal no IXC): reagendamento feito por operador cadastrado como
    membro da equipe do setor conta como Backoffice; qualquer outro caso (operador fora da equipe,
    ou evento só com técnico de campo) conta como Campo."""
    return "backoffice" if operator_id is not None and operator_id in team_ids else "campo"


def _reschedule_origins_by_order(db: Session, os_ids: set[int], team_ids: set[int]) -> dict[int, list[str]]:
    """Origem de cada evento de Reagendar (tipo 10) das O.S. informadas, agrupada por O.S. - uma
    entrada por EVENTO (não deduplicada), para permitir tanto contagem de ações (dashboard) quanto
    o conjunto de origens por O.S. (filtro/exibição no drill, via `set(...)`)."""
    if not os_ids:
        return {}
    rows = db.execute(
        select(SchedulingEvent.ixc_os_id, SchedulingEvent.operator_id).where(
            SchedulingEvent.ixc_os_id.in_(os_ids), SchedulingEvent.event_type == "10",
        )
    )
    origins_by_order: dict[int, list[str]] = {}
    for os_id, operator_id in rows:
        origins_by_order.setdefault(os_id, []).append(_classify_reschedule_origin(operator_id, team_ids))
    return origins_by_order


def build_dashboard(db: Session, filters: SchedulingFilters, *, count_mode: str = "all_events") -> dict:
    settings = load_settings(db)
    window_start, window_end, active_days = _parse_business_window(settings)
    sla_minutes = int(float(settings["scheduling_sla_minutes"]))
    sla_target = float(settings["scheduling_sla_target_pct"])
    daily_goal = int(float(settings["scheduling_daily_goal"]))
    now_local = now_porto_velho().replace(tzinfo=None)

    orders = list(db.execute(_cohort_query(filters)).scalars())
    team_ids = _team_operator_ids(db)

    # --- Grupo A: velocidade de resposta (coorte = O.S. ABERTAS no período) ---
    raw_minutes: list[float] = []
    business_minutes: list[float] = []
    within_sla = 0
    bucket_counts = {key: 0 for key, _, _ in TTFA_BUCKETS}
    lead_hours: list[float] = []  # antecedência da janela combinada (C2)
    rescheduled = 0
    rescheduled_os_ids: set[int] = set()
    scheduled_count = 0

    # Volume + tempo útil por filial/assunto - base do ranking "quem mais atrasa" (grupo E).
    # Agrupado por ID (não pelo nome) pra dar pra clicar num item do ranking e abrir o drill já
    # filtrado por aquela filial/assunto - o mesmo filtro que o painel de filtros usa.
    by_filial: dict[str, list[float]] = {}
    by_filial_late: dict[str, int] = {}
    by_assunto: dict[str, list[float]] = {}
    by_assunto_late: dict[str, int] = {}
    assunto_names: dict[str, str] = {}

    for order in orders:
        if order.first_scheduled_at is None:
            continue
        scheduled_count += 1
        opened = _local(order.opened_at)
        scheduled = _local(order.first_scheduled_at)
        raw = max(0.0, (scheduled - opened).total_seconds() / 60)
        useful = business_minutes_between(opened, scheduled, window_start, window_end, active_days)
        raw_minutes.append(raw)
        business_minutes.append(useful)
        is_late = useful > sla_minutes
        if not is_late:
            within_sla += 1
        for key, _, upper in TTFA_BUCKETS:
            if upper is None or useful <= upper:
                bucket_counts[key] += 1
                break
        if order.schedule_event_count > 1:
            rescheduled += 1
            rescheduled_os_ids.add(order.ixc_os_id)
        if order.first_window_start is not None:
            lead = (_local(order.first_window_start) - scheduled).total_seconds() / 3600
            if lead >= 0:
                lead_hours.append(lead)

        by_filial.setdefault(order.filial_id, []).append(useful)
        by_filial_late[order.filial_id] = by_filial_late.get(order.filial_id, 0) + (1 if is_late else 0)
        assunto_key = order.assunto_id or ""
        by_assunto.setdefault(assunto_key, []).append(useful)
        by_assunto_late[assunto_key] = by_assunto_late.get(assunto_key, 0) + (1 if is_late else 0)
        assunto_names[assunto_key] = order.assunto_name or "Não informado"

    # Origem do reagendamento (C1 estendido): heurística sobre o operador de cada evento "Reagendar"
    # (tipo 10) - não existe campo de canal no IXC, ver `_classify_reschedule_origin`.
    reschedule_origins_by_order = _reschedule_origins_by_order(db, rescheduled_os_ids, team_ids)
    all_reschedule_origins = [origin for origins in reschedule_origins_by_order.values() for origin in origins]
    reschedule_backoffice_count = sum(1 for origin in all_reschedule_origins if origin == "backoffice")
    reschedule_campo_count = sum(1 for origin in all_reschedule_origins if origin == "campo")
    reschedule_origin_total = reschedule_backoffice_count + reschedule_campo_count

    # --- Grupo D: backlog sem agendamento (só O.S. ainda abertas) ---
    backlog_counts = {key: 0 for key, _, _ in BACKLOG_BUCKETS}
    backlog_total = 0
    for order in orders:
        if order.first_scheduled_at is not None or order.closed_at is not None:
            continue
        if (order.status or "").upper() in ("F", "C"):  # finalizada/cancelada sem evento de agenda
            continue
        backlog_total += 1
        age_days = (now_local - _local(order.opened_at)).days
        for key, _, upper in BACKLOG_BUCKETS:
            if upper is None or age_days < upper:
                backlog_counts[key] += 1
                break

    sla_rate = round(within_sla / scheduled_count * 100, 1) if scheduled_count else None

    # --- Grupo B: produtividade (eventos DENTRO do período, independente de quando a O.S. abriu) ---
    events_stmt = (
        select(SchedulingEvent, SchedulingOrder)
        .join(SchedulingOrder, SchedulingOrder.ixc_os_id == SchedulingEvent.ixc_os_id)
        .where(
            SchedulingEvent.event_type.in_(("5", "10")),
            SchedulingEvent.event_at >= datetime.combine(filters.date_from, dtime.min, tzinfo=PORTO_VELHO_TZ),
            SchedulingEvent.event_at <= datetime.combine(filters.date_to, dtime.max, tzinfo=PORTO_VELHO_TZ),
        )
    )
    if filters.filial_ids:
        events_stmt = events_stmt.where(SchedulingOrder.filial_id.in_(filters.filial_ids))
    if filters.setor_ids:
        events_stmt = events_stmt.where(SchedulingOrder.setor_id.in_(filters.setor_ids))
    if filters.assunto_ids:
        events_stmt = events_stmt.where(SchedulingOrder.assunto_id.in_(filters.assunto_ids))
    if filters.operator_ids:
        events_stmt = events_stmt.where(SchedulingEvent.operator_id.in_(filters.operator_ids))

    daily_counts: dict[str, int] = {}
    operator_events: dict[int, int] = {}
    operator_distinct: dict[int, set[int]] = {}
    for event, _order in db.execute(events_stmt):
        day_key = event.event_at.strftime("%Y-%m-%d")
        daily_counts[day_key] = daily_counts.get(day_key, 0) + 1
        if event.operator_id:
            operator_events[event.operator_id] = operator_events.get(event.operator_id, 0) + 1
            operator_distinct.setdefault(event.operator_id, set()).add(event.ixc_os_id)

    opened_daily: dict[str, int] = {}
    for order in orders:
        day_key = order.opened_at.strftime("%Y-%m-%d")
        opened_daily[day_key] = opened_daily.get(day_key, 0) + 1

    active_period_days = max(1, sum(
        1 for offset in range((filters.date_to - filters.date_from).days + 1)
        if (filters.date_from + timedelta(days=offset)).weekday() in active_days
        and filters.date_from + timedelta(days=offset) <= now_local.date()
    ))

    # Primeiro agendamento por operador + TTFA mediano individual (grupo B3)
    first_by_operator: dict[int, list[float]] = {}
    for order in orders:
        if order.first_scheduled_at is None or order.first_operator_id is None:
            continue
        useful = business_minutes_between(
            _local(order.opened_at), _local(order.first_scheduled_at),
            window_start, window_end, active_days,
        )
        first_by_operator.setdefault(order.first_operator_id, []).append(useful)

    all_operator_ids = set(operator_events) | set(first_by_operator)
    names = _resolve_operator_names(db, all_operator_ids)

    operators = []
    for op_id in sorted(all_operator_ids, key=lambda i: -(operator_events.get(i, 0))):
        total = operator_events.get(op_id, 0)
        distinct = len(operator_distinct.get(op_id, set()))
        counted = distinct if count_mode == "distinct_orders" else total
        firsts = first_by_operator.get(op_id, [])
        operators.append({
            "ixc_operator_id": op_id,
            "operator_name": names.get(op_id, f"Operador IXC {op_id}"),
            "is_team_member": op_id in team_ids,
            "total_events": total,
            "distinct_orders": distinct,
            "per_day": round(counted / active_period_days, 1),
            "daily_goal": daily_goal if op_id in team_ids else None,
            "goal_percentage": round(counted / active_period_days / daily_goal * 100, 1) if op_id in team_ids and daily_goal else None,
            "first_schedules": len(firsts),
            "ttfa_business_median_minutes": _stats(firsts)["median"],
        })

    day_cursor = filters.date_from
    daily_series = []
    while day_cursor <= filters.date_to:
        key = day_cursor.strftime("%Y-%m-%d")
        daily_series.append({
            "date": key,
            "opened": opened_daily.get(key, 0),
            "schedule_events": daily_counts.get(key, 0),
        })
        day_cursor += timedelta(days=1)

    team_size = len(team_ids) or None

    # Ranking "quem mais atrasa" - amostra mínima pra não expor taxa de 100%/0% de filial ou
    # assunto com 1-2 O.S. no período (ruído estatístico, não sinal de operação).
    RANKING_MIN_SAMPLE = 5

    def _ranking(values_by_key: dict[str, list[float]], late_by_key: dict[str, int], label_by_key: dict[str, str]) -> list[dict]:
        rows = [
            {
                "key": key,
                "label": label_by_key.get(key, key),
                "scheduled": len(values),
                "late_rate": round(late_by_key.get(key, 0) / len(values) * 100, 1),
                "ttfa_median_minutes": _stats(values)["median"],
            }
            for key, values in values_by_key.items()
            if len(values) >= RANKING_MIN_SAMPLE
        ]
        rows.sort(key=lambda item: -item["late_rate"])
        return rows[:10]

    filial_by_name = {fid: REGIONAL_CODE_MAP.get(fid, f"Filial {fid}") for fid in by_filial}
    filial_ranking = _ranking(by_filial, by_filial_late, filial_by_name)
    assunto_ranking = _ranking(by_assunto, by_assunto_late, assunto_names)

    return {
        "settings": settings,
        "summary": {
            "opened_orders": len(orders),
            "scheduled_orders": scheduled_count,
            "pending_orders": backlog_total,
            "sla_minutes": sla_minutes,
            "sla_target_pct": sla_target,
            "sla_rate": sla_rate,
            "sla_met": (sla_rate is not None and sla_rate >= sla_target) if sla_rate is not None else None,
            "ttfa_business": _stats(business_minutes),
            "ttfa_raw": _stats(raw_minutes),
            "reschedule_rate": round(rescheduled / scheduled_count * 100, 1) if scheduled_count else None,
            "rescheduled_orders": rescheduled,
            "reschedule_backoffice_count": reschedule_backoffice_count,
            "reschedule_backoffice_pct": (
                round(reschedule_backoffice_count / reschedule_origin_total * 100, 1) if reschedule_origin_total else None
            ),
            "reschedule_campo_count": reschedule_campo_count,
            "reschedule_campo_pct": (
                round(reschedule_campo_count / reschedule_origin_total * 100, 1) if reschedule_origin_total else None
            ),
            "window_lead_hours": _stats(lead_hours),
            "total_schedule_events": sum(daily_counts.values()),
            "active_period_days": active_period_days,
            "team_size": team_size,
            "expected_capacity": (team_size * daily_goal * active_period_days) if team_size else None,
        },
        "ttfa_distribution": [
            {"bucket": key, "label": label, "count": bucket_counts[key]}
            for key, label, _ in TTFA_BUCKETS
        ],
        "backlog_aging": [
            {"bucket": key, "label": label, "count": backlog_counts[key]}
            for key, label, _ in BACKLOG_BUCKETS
        ],
        "daily_series": daily_series,
        "operators": operators,
        "filial_ranking": filial_ranking,
        "assunto_ranking": assunto_ranking,
    }


def backlog_items(db: Session, filters: SchedulingFilters, *, limit: int = 100) -> list[dict]:
    now_local = now_porto_velho().replace(tzinfo=None)
    stmt = (
        _cohort_query(filters)
        .where(
            SchedulingOrder.first_scheduled_at.is_(None),
            SchedulingOrder.closed_at.is_(None),
        )
        .order_by(SchedulingOrder.opened_at.asc())
        .limit(limit)
    )
    items = []
    for order in db.execute(stmt).scalars():
        if (order.status or "").upper() in ("F", "C"):
            continue
        opened = _local(order.opened_at)
        items.append({
            "ixc_os_id": order.ixc_os_id,
            "opened_at": order.opened_at,
            "age_hours": round((now_local - opened).total_seconds() / 3600, 1),
            "filial": REGIONAL_CODE_MAP.get(order.filial_id, f"Filial {order.filial_id}"),
            "setor": order.setor_name,
            "assunto": order.assunto_name or "Não informado",
            "status": order.status,
        })
    return items


ORDER_SORT_KEYS = {
    "opened_at": lambda o, u, l: (o.opened_at is None, o.opened_at),
    "first_scheduled_at": lambda o, u, l: (o.first_scheduled_at is None, o.first_scheduled_at),
    "ttfa_business_minutes": lambda o, u, l: (u is None, u),
    "reschedule_count": lambda o, u, l: (False, o.schedule_event_count or 0),
    "filial": lambda o, u, l: (False, REGIONAL_CODE_MAP.get(o.filial_id, f"Filial {o.filial_id}")),
    "assunto": lambda o, u, l: (o.assunto_name is None, o.assunto_name or ""),
}


def order_details(
    db: Session,
    filters: SchedulingFilters,
    *,
    status: str | None = None,
    sla_status: str | None = None,
    ttfa_bucket: str | None = None,
    backlog_bucket: str | None = None,
    only_rescheduled: bool = False,
    reschedule_origin: str | None = None,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = "opened_at",
    sort_dir: str = "desc",
) -> dict:
    """Lista as O.S. por trás de qualquer número do dashboard - o drill-through que faltava.

    Os filtros de tempo (`sla_status`, `ttfa_bucket`) dependem do expediente configurável, que não
    dá pra empurrar pro SQL sem reimplementar `business_minutes_between` como função de banco - por
    isso a filtragem roda em Python sobre a coorte já filtrada por SQL (mesmo custo do dashboard,
    que já faz exatamente isso).
    """
    settings = load_settings(db)
    window_start, window_end, active_days = _parse_business_window(settings)
    sla_minutes = int(float(settings["scheduling_sla_minutes"]))
    now_local = now_porto_velho().replace(tzinfo=None)

    stmt = _cohort_query(filters)
    if status == "pending":
        stmt = stmt.where(SchedulingOrder.first_scheduled_at.is_(None), SchedulingOrder.closed_at.is_(None))
    elif status == "scheduled":
        stmt = stmt.where(SchedulingOrder.first_scheduled_at.is_not(None))
    if only_rescheduled or reschedule_origin:
        stmt = stmt.where(SchedulingOrder.schedule_event_count > 1)

    filtered: list[tuple[SchedulingOrder, float | None, bool | None]] = []
    for order in db.execute(stmt).scalars():
        useful: float | None = None
        is_late: bool | None = None
        if order.first_scheduled_at is not None:
            opened = _local(order.opened_at)
            scheduled = _local(order.first_scheduled_at)
            useful = business_minutes_between(opened, scheduled, window_start, window_end, active_days)
            is_late = useful > sla_minutes
            if sla_status == "late" and not is_late:
                continue
            if sla_status == "on_time" and is_late:
                continue
            if ttfa_bucket:
                matched = next((key for key, _, upper in TTFA_BUCKETS if upper is None or useful <= upper), None)
                if matched != ttfa_bucket:
                    continue
        elif sla_status or ttfa_bucket:
            continue  # essas métricas só existem para O.S. já agendada

        if backlog_bucket:
            if order.first_scheduled_at is not None or order.closed_at is not None:
                continue
            if (order.status or "").upper() in ("F", "C"):
                continue
            age_days = (now_local - _local(order.opened_at)).days
            matched_backlog = next((key for key, _, upper in BACKLOG_BUCKETS if upper is None or age_days < upper), None)
            if matched_backlog != backlog_bucket:
                continue

        filtered.append((order, useful, is_late))

    reschedule_origins_by_order: dict[int, list[str]] = {}
    if reschedule_origin:
        team_ids = _team_operator_ids(db)
        candidate_ids = {o.ixc_os_id for o, _, _ in filtered if o.schedule_event_count > 1}
        reschedule_origins_by_order = _reschedule_origins_by_order(db, candidate_ids, team_ids)
        filtered = [
            (o, u, l) for o, u, l in filtered
            if reschedule_origin in set(reschedule_origins_by_order.get(o.ixc_os_id, []))
        ]

    total = len(filtered)
    key_fn = ORDER_SORT_KEYS.get(sort_by, ORDER_SORT_KEYS["opened_at"])
    filtered.sort(key=lambda item: key_fn(*item), reverse=(sort_dir != "asc"))
    page_items = filtered[(page - 1) * page_size: (page - 1) * page_size + page_size]

    operator_ids = {o.first_operator_id for o, _, _ in page_items if o.first_operator_id}
    technician_ids = {o.first_technician_id for o, _, _ in page_items if o.first_technician_id}
    operator_names = _resolve_operator_names(db, operator_ids)
    technician_names = _resolve_technician_names(db, technician_ids)

    # Reaproveita o que já foi buscado para o filtro de origem; só busca o que falta para a página.
    page_rescheduled_ids = {o.ixc_os_id for o, _, _ in page_items if o.schedule_event_count > 1}
    missing_ids = page_rescheduled_ids - set(reschedule_origins_by_order)
    if missing_ids:
        team_ids = _team_operator_ids(db)
        reschedule_origins_by_order.update(_reschedule_origins_by_order(db, missing_ids, team_ids))

    items = []
    for order, useful, is_late in page_items:
        items.append({
            "ixc_os_id": order.ixc_os_id,
            "opened_at": order.opened_at,
            "filial": REGIONAL_CODE_MAP.get(order.filial_id, f"Filial {order.filial_id}"),
            "setor": order.setor_name,
            "assunto": order.assunto_name or "Não informado",
            "status": order.status,
            "first_scheduled_at": order.first_scheduled_at,
            "ttfa_business_minutes": round(useful, 1) if useful is not None else None,
            "sla_late": is_late,
            "reschedule_count": max(0, order.schedule_event_count - 1) if order.schedule_event_count else 0,
            "reschedule_origins": sorted(set(reschedule_origins_by_order.get(order.ixc_os_id, []))),
            "operator_name": operator_names.get(order.first_operator_id) if order.first_operator_id else None,
            "technician_name": technician_names.get(order.first_technician_id) if order.first_technician_id else None,
            "age_hours": (
                round((now_local - _local(order.opened_at)).total_seconds() / 3600, 1)
                if order.first_scheduled_at is None else None
            ),
        })

    return {"items": items, "total": total, "page": page, "page_size": page_size}


def operator_events(
    db: Session,
    filters: SchedulingFilters,
    *,
    operator_id: int,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Cada agendamento/reagendamento (evento 5/10) feito por um operador dentro do período - a
    visão "cada ação conta" do drill, distinta do drill por O.S. (`order_details`, que só enxerga
    quem agendou PRIMEIRO). Mesma cohort de evento usada no card de produtividade (grupo B de
    `build_dashboard`) - pedido do dono do produto pra clicar num operador e ver TODAS as ações dele,
    não só as O.S. que ele agendou primeiro."""
    stmt = (
        select(SchedulingEvent, SchedulingOrder)
        .join(SchedulingOrder, SchedulingOrder.ixc_os_id == SchedulingEvent.ixc_os_id)
        .where(
            SchedulingEvent.event_type.in_(("5", "10")),
            SchedulingEvent.operator_id == operator_id,
            SchedulingEvent.event_at >= datetime.combine(filters.date_from, dtime.min, tzinfo=PORTO_VELHO_TZ),
            SchedulingEvent.event_at <= datetime.combine(filters.date_to, dtime.max, tzinfo=PORTO_VELHO_TZ),
        )
    )
    if filters.filial_ids:
        stmt = stmt.where(SchedulingOrder.filial_id.in_(filters.filial_ids))
    if filters.setor_ids:
        stmt = stmt.where(SchedulingOrder.setor_id.in_(filters.setor_ids))
    if filters.assunto_ids:
        stmt = stmt.where(SchedulingOrder.assunto_id.in_(filters.assunto_ids))

    rows = list(db.execute(stmt))
    rows.sort(key=lambda pair: pair[0].event_at, reverse=True)
    total = len(rows)
    page_rows = rows[(page - 1) * page_size: (page - 1) * page_size + page_size]

    technician_ids = {event.technician_id for event, _ in page_rows if event.technician_id}
    technician_names = _resolve_technician_names(db, technician_ids)

    items = [
        {
            "ixc_os_id": order.ixc_os_id,
            "event_type": event.event_type,
            "event_label": EVENT_TYPE_LABELS.get(event.event_type, f"Evento {event.event_type}"),
            "event_at": event.event_at,
            "window_start": event.window_start,
            "window_end": event.window_end,
            "technician_name": technician_names.get(event.technician_id) if event.technician_id else None,
            "filial": REGIONAL_CODE_MAP.get(order.filial_id, f"Filial {order.filial_id}"),
            "assunto": order.assunto_name or "Não informado",
        }
        for event, order in page_rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def filter_options(db: Session) -> dict:
    filiais = [
        {"id": fid, "name": REGIONAL_CODE_MAP.get(fid, f"Filial {fid}")}
        for (fid,) in db.execute(select(SchedulingOrder.filial_id).distinct().order_by(SchedulingOrder.filial_id))
    ]
    setores = [
        {"id": sid, "name": name}
        for sid, name in db.execute(select(SchedulingOrder.setor_id, SchedulingOrder.setor_name).distinct().order_by(SchedulingOrder.setor_id))
    ]
    assuntos = [
        {"id": aid, "name": name or f"Assunto {aid}"}
        for aid, name in db.execute(
            select(SchedulingOrder.assunto_id, SchedulingOrder.assunto_name)
            .where(SchedulingOrder.assunto_id.is_not(None)).distinct().order_by(SchedulingOrder.assunto_name)
        )
    ]
    operator_ids = {
        int(op_id) for (op_id,) in db.execute(
            select(SchedulingEvent.operator_id).where(SchedulingEvent.operator_id.is_not(None)).distinct()
        )
    }
    names = _resolve_operator_names(db, operator_ids)
    team_ids = {row.ixc_user_id for row in db.execute(select(SchedulingOperator).where(SchedulingOperator.is_team_member.is_(True))).scalars()}
    operators = sorted(
        (
            {"id": op_id, "name": names.get(op_id, f"Operador IXC {op_id}"), "is_team_member": op_id in team_ids}
            for op_id in operator_ids
        ),
        key=lambda item: item["name"],
    )
    bounds = db.execute(select(func.min(SchedulingOrder.opened_at), func.max(SchedulingOrder.opened_at))).one()
    return {
        "filiais": filiais,
        "setores": setores,
        "assuntos": assuntos,
        "operators": operators,
        "data_available_from": bounds[0],
        "data_available_to": bounds[1],
    }


def order_timeline(db: Session, ixc_os_id: int) -> dict | None:
    """Linha do tempo completa de uma O.S.: todo evento sincronizado (Abertura, Agendamento,
    Reagendar, Fechamento), em ordem, com o colaborador (operador/técnico) de cada um resolvido por
    nome. É a visão "log completo" pedida ao clicar numa O.S. específica do drill-through."""
    order = db.execute(select(SchedulingOrder).where(SchedulingOrder.ixc_os_id == ixc_os_id)).scalar_one_or_none()
    if order is None:
        return None

    events = list(
        db.execute(
            select(SchedulingEvent).where(SchedulingEvent.ixc_os_id == ixc_os_id).order_by(SchedulingEvent.event_at.asc())
        ).scalars()
    )
    operator_ids = {e.operator_id for e in events if e.operator_id}
    technician_ids = {e.technician_id for e in events if e.technician_id}
    operator_names = _resolve_operator_names(db, operator_ids)
    technician_names = _resolve_technician_names(db, technician_ids)

    return {
        "ixc_os_id": order.ixc_os_id,
        "opened_at": order.opened_at,
        "filial": REGIONAL_CODE_MAP.get(order.filial_id, f"Filial {order.filial_id}"),
        "setor": order.setor_name,
        "assunto": order.assunto_name or "Não informado",
        "status": order.status,
        "events": [
            {
                "event_type": event.event_type,
                "event_label": EVENT_TYPE_LABELS.get(event.event_type, f"Evento {event.event_type}"),
                "event_at": event.event_at,
                "window_start": event.window_start,
                "window_end": event.window_end,
                "operator_name": operator_names.get(event.operator_id) if event.operator_id else None,
                "technician_name": technician_names.get(event.technician_id) if event.technician_id else None,
                "mensagem": event.mensagem,
                "historico": event.historico,
            }
            for event in events
        ],
    }
