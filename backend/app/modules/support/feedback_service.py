"""Feedback individual do Suporte (pedido do usuário, 2026-10-16).

Junta, para UM colaborador da equipe do Suporte Técnico (`dashboard_macros.SUPPORT_TEAM`), os indicadores do
OPA e do IXC com as metas individuais, para a conversa de feedback:

- Registro Operacional (motivo 90) e Registro Financeiro (motivo 29): protocolos que ele abriu no IXC;
- O.S. aberta a campo: O.S. dos setores de campo cujo criador é ele (vínculo pelo NOME, como nos Indicadores - aproximado);
- Atendimento OPASuite: atendimentos do OPA dele no período;
- Chamadas atendidas: atendimentos do canal `pabx` em que ELE foi o primeiro humano a falar
  (`first_human_attendant_id`); ligação que outra pessoa atendeu primeiro e transferiu para ele não conta;
- Avaliação individual (CSAT), TMA e TMR: mesma regra dos Indicadores do Suporte (`opa_overview_service`).

Metas (informadas pelo usuário, valem para todos os colaboradores): as de contagem são SEMANAIS e são
proporcionais ao tamanho do período escolhido (dias / 7, arredondado para cima); avaliação e tempos não escalam.
O status segue `dashboard_macros.metric_status` (margem de "Atenção" de 10% da meta).
"""

from __future__ import annotations

import math
import unicodedata
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.operations.models import OperationOrder
from app.modules.operations.scope import PRIMARY_SECTOR_NAMES

from . import dashboard_macros, ixc_n1, opa_overview_service, support_rules
from .models import SupportIxcTicket, SupportIxcUser, SupportOpaAttendance
from .opa_filters import OpaAttendanceFilters, apply_opa_attendance_filters

# Canal do OPA que representa a ligação telefônica (valores locais: whatsapp, pabx, page).
PHONE_CHANNEL = "pabx"

WEEK_DAYS = 7
# Período máximo da tela (pedido do usuário); o limite do OPA (32 dias) fica acima disso.
MAX_PERIOD_DAYS = 30

# (chave, rótulo, unidade, meta, sentido, escala com o período, fonte)
GOALS: tuple[tuple[str, str, str, float, str, bool, str], ...] = (
    ("operational", "Registros Operacional", "count", 38, "min", True, "ixc"),
    ("financial", "Registro Financeiro", "count", 38, "min", True, "ixc"),
    ("field", "O.S. Aberta a Campo", "count", 25, "max", True, "ixc"),
    ("opa_attendances", "Atendimento OPASuite", "count", 96, "min", True, "opa"),
    ("calls", "Chamadas Atendidas - OPA", "count", 12, "min", True, "opa"),
    ("rating", "Avaliação Individual", "score", 4.50, "min", False, "opa"),
    ("tma", "Tempo Médio de Atendimento", "seconds", 3600.0, "max", False, "opa"),
    ("tmr", "Tempo Médio de Resposta", "seconds", 120.0, "max", False, "opa"),
)


def goals_with(goals: support_rules.FeedbackGoals) -> tuple[tuple[str, str, str, float, str, bool, str], ...]:
    """`GOALS` com as metas salvas na Configuração > Regras no lugar dos valores padrão."""
    saved = {
        "operational": goals.operational, "financial": goals.financial, "field": goals.field,
        "opa_attendances": goals.opa_attendances, "calls": goals.calls, "rating": goals.rating,
        "tma": goals.tma_seconds, "tmr": goals.tmr_seconds,
    }
    return tuple((key, label, unit, float(saved[key]), direction, scales, source) for key, label, unit, _, direction, scales, source in GOALS)


def _name_key(value: str | None) -> str:
    return (value or "").strip().lower()


def find_collaborator(db: Session, attendant_id: str) -> dict[str, str] | None:
    """Colaborador da equipe fixa pelo id do usuário no OPA; `None` se não for da equipe."""
    for option in dashboard_macros.support_team_options(db):
        if option["value"] == attendant_id:
            return option
    return None


def resolve_collaborator(db: Session, attendant_id: str) -> tuple[dict[str, str], SupportIxcUser | None] | None:
    """Colaborador da equipe e o usuário dele no IXC (`None` no segundo item se não achar); `None` se não é da equipe."""
    collaborator = find_collaborator(db, attendant_id)
    if collaborator is None:
        return None
    opa_name = next((opa for label, opa in dashboard_macros.SUPPORT_TEAM if label == collaborator["label"]), collaborator["label"])
    return collaborator, _ixc_user(db, collaborator["label"], opa_name)


def _name_tokens(value: str | None) -> list[str]:
    """Palavras do nome sem acento e sem caixa ("Julio César" -> ["julio", "cesar"])."""
    plain = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    return plain.lower().split()


def _ixc_user(db: Session, label: str, opa_name: str) -> SupportIxcUser | None:
    """Usuário do IXC do colaborador, procurado SÓ nos grupos N1 (105 e 117). O IXC guarda o nome completo
    ("Adelaidy Vitoria de Oliveira Leite") e o OPA o nome curto, então casa quando todas as palavras do nome do OPA
    estão no nome do IXC (sem acento nem caixa); havendo mais de um, vale o de nome mais curto, e empate sem desempate
    não vincula ninguém (melhor sem valor do que o número de outra pessoa)."""
    wanted = [set(_name_tokens(label)), set(_name_tokens(opa_name))]
    users = db.scalars(select(SupportIxcUser).where(SupportIxcUser.group_id.in_(ixc_n1.N1_IXC_GROUP_IDS))).all()
    candidates: list[tuple[int, int, SupportIxcUser]] = []
    for user in users:
        tokens = set(_name_tokens(user.name))
        extra = [len(tokens - words) for words in wanted if words and words <= tokens]
        if extra:
            candidates.append((min(extra), 0 if user.active else 1, user))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    if len(candidates) > 1 and candidates[0][:2] == candidates[1][:2]:
        return None
    return candidates[0][2]


def _protocol_counts(db: Session, user_id: str, date_from: date, date_to: date) -> dict[str, int]:
    query = (
        select(SupportIxcTicket.subject_id, func.count(SupportIxcTicket.id))
        .where(SupportIxcTicket.opened_by_user_id == user_id, SupportIxcTicket.subject_id.in_(ixc_n1.N1_SUBJECT_IDS))
        .group_by(SupportIxcTicket.subject_id)
    )
    query = ixc_n1.apply_period_utc(query, SupportIxcTicket.created_at, date_from, date_to)
    counts = {ixc_n1.N1_OPERATIONAL_SUBJECT_ID: 0, ixc_n1.N1_FINANCIAL_SUBJECT_ID: 0}
    for subject_id, count in db.execute(query).all():
        counts[subject_id] = int(count)
    return {"operational": counts[ixc_n1.N1_OPERATIONAL_SUBJECT_ID], "financial": counts[ixc_n1.N1_FINANCIAL_SUBJECT_ID]}


def _field_orders(db: Session, name_key: str, date_from: date, date_to: date) -> int:
    query = select(func.count(OperationOrder.id)).where(
        func.lower(func.trim(OperationOrder.creator)) == name_key,
        OperationOrder.sector.in_(PRIMARY_SECTOR_NAMES),
    )
    return int(db.scalar(ixc_n1.apply_period_utc(query, OperationOrder.opened_at, date_from, date_to)) or 0)


def _ixc_daily(db: Session, user_id: str, name_key: str, date_from: date, date_to: date) -> dict[str, dict[str, int]]:
    """Por dia: protocolos operacionais/financeiros e O.S. a campo dele (dias sem registro ficam de fora)."""
    days: dict[str, dict[str, int]] = {}
    ticket_day = func.date(SupportIxcTicket.created_at)
    tickets = (
        select(ticket_day, SupportIxcTicket.subject_id, func.count(SupportIxcTicket.id))
        .where(SupportIxcTicket.opened_by_user_id == user_id, SupportIxcTicket.subject_id.in_(ixc_n1.N1_SUBJECT_IDS))
        .group_by(ticket_day, SupportIxcTicket.subject_id)
    )
    for day, subject_id, count in db.execute(ixc_n1.apply_period_utc(tickets, SupportIxcTicket.created_at, date_from, date_to)).all():
        key = "operational" if subject_id == ixc_n1.N1_OPERATIONAL_SUBJECT_ID else "financial"
        days.setdefault(str(day)[:10], {})[key] = int(count)
    order_day = func.date(OperationOrder.opened_at)
    orders = (
        select(order_day, func.count(OperationOrder.id))
        .where(func.lower(func.trim(OperationOrder.creator)) == name_key, OperationOrder.sector.in_(PRIMARY_SECTOR_NAMES))
        .group_by(order_day)
    )
    for day, count in db.execute(ixc_n1.apply_period_utc(orders, OperationOrder.opened_at, date_from, date_to)).all():
        days.setdefault(str(day)[:10], {})["field"] = int(count)
    return days


def phone_calls_answered(db: Session, attendant_id: str, filters: OpaAttendanceFilters) -> int:
    """Atendimentos pelo canal telefone (pabx) em que o colaborador foi o PRIMEIRO humano a falar.
    `filters` NÃO pode trazer `attendant_id`: o atendimento pode ter sido transferido para outra pessoa depois."""
    query = apply_opa_attendance_filters(
        select(func.count(SupportOpaAttendance.id)).where(
            func.lower(SupportOpaAttendance.channel) == PHONE_CHANNEL,
            SupportOpaAttendance.first_human_attendant_id == attendant_id,
        ),
        filters,
    )
    return int(db.scalar(query) or 0)


def goal_scale(date_from: date, date_to: date) -> float:
    """Fator das metas semanais de contagem para o período (dias / 7)."""
    return ((date_to - date_from).days + 1) / WEEK_DAYS


def _target(base: float, scales: bool, factor: float) -> float:
    return float(math.ceil(base * factor - 1e-9)) if scales else base


def _indicator(
    key: str, label: str, unit: str, value: float | int | None, previous: float | int | None, *, base_target: float,
    direction: str, scales: bool, factor: float, source: str, coverage: dict[str, Any] | None = None, note: str | None = None,
    margin: float = dashboard_macros.ATTENTION_MARGIN,
) -> dict[str, Any]:
    target = _target(base_target, scales, factor)
    status = dashboard_macros.metric_status(value, target, direction, margin)
    if coverage is not None and status not in ("no_data", "no_target") and (coverage["percentage"] or 0) < dashboard_macros.MIN_COVERAGE_PERCENT:
        status = "partial"
    return {
        "key": key,
        "label": label,
        "unit": unit,
        "value": value,
        "previous": previous,
        "target": target,
        "weekly_target": base_target,
        "direction": direction,
        "status": status,
        "source": source,
        "coverage": coverage,
        "note": note,
    }


def _opa_values(db: Session, filters: OpaAttendanceFilters) -> dict[str, Any]:
    metrics = opa_overview_service.overview_metrics(db, filters)
    return {
        "opa_attendances": metrics["total_attendances"],
        "rating": metrics["average_rating"],
        "tma": metrics["average_tma_effective_seconds"],
        "tmr": metrics["average_tmr_effective_seconds"],
    }


def _ixc_values(db: Session, ixc_user: SupportIxcUser | None, date_from: date, date_to: date) -> dict[str, int | None]:
    if ixc_user is None:
        return {"operational": None, "financial": None, "field": None}
    protocols = _protocol_counts(db, ixc_user.ixc_user_id, date_from, date_to)
    return {**protocols, "field": _field_orders(db, _name_key(ixc_user.name), date_from, date_to)}


def collaborator_feedback(db: Session, *, date_from: date, date_to: date, attendant_id: str) -> dict[str, Any] | None:
    """Feedback do colaborador no período, com o período anterior (mesmo tamanho) para comparação.
    `None` quando `attendant_id` não é da equipe do Suporte Técnico."""
    resolved = resolve_collaborator(db, attendant_id)
    if resolved is None:
        return None
    collaborator, ixc_user = resolved

    filters = OpaAttendanceFilters(date_from=date_from, date_to=date_to, attendant_id=attendant_id)
    phone_filters = OpaAttendanceFilters(date_from=date_from, date_to=date_to)
    previous_filters = filters.previous_period()
    has_previous = previous_filters.date_from != date_from

    current = {**_opa_values(db, filters), **_ixc_values(db, ixc_user, date_from, date_to), "calls": phone_calls_answered(db, attendant_id, phone_filters)}
    if has_previous:
        previous_phone = OpaAttendanceFilters(date_from=previous_filters.date_from, date_to=previous_filters.date_to)
        previous = {
            **_opa_values(db, previous_filters),
            **_ixc_values(db, ixc_user, previous_filters.date_from, previous_filters.date_to),
            "calls": phone_calls_answered(db, attendant_id, previous_phone),
        }
    else:
        previous = {}

    coverage = dashboard_macros.time_coverage(db, filters)
    factor = goal_scale(date_from, date_to)
    indicators = []
    saved = support_rules.load_current(db)
    margin = saved.indicator_goals.attention_margin_percent / 100
    for key, label, unit, base_target, direction, scales, source in goals_with(saved.feedback_goals):
        ixc_missing = source == "ixc" and ixc_user is None
        indicators.append(
            _indicator(
                key, label, unit, current.get(key), previous.get(key), base_target=base_target, direction=direction,
                scales=scales, factor=factor, source=source,
                coverage=coverage if key in ("tma", "tmr") else None,
                note="Colaborador não encontrado no IXC pelo nome" if ixc_missing else None, margin=margin,
            )
        )

    statuses = [item["status"] for item in indicators]
    summary = {
        "ok": statuses.count("ok"),
        "attention": statuses.count("attention"),
        "critical": statuses.count("critical"),
        "overall": "critical" if "critical" in statuses else "attention" if "attention" in statuses else "ok",
    }

    ixc_daily = _ixc_daily(db, ixc_user.ixc_user_id, _name_key(ixc_user.name), date_from, date_to) if ixc_user else {}
    opa_daily = {point["day"]: point for point in opa_overview_service.daily_timeseries(db, filters)}
    daily = []
    for offset in range((date_to - date_from).days + 1):
        day = date_from + timedelta(days=offset)
        opa_point = opa_daily.get(day, {})
        ixc_point = ixc_daily.get(day.isoformat(), {})
        daily.append(
            {
                "day": day,
                "opa_attendances": int(opa_point.get("total", 0)),
                "operational": ixc_point.get("operational", 0),
                "financial": ixc_point.get("financial", 0),
                "field": ixc_point.get("field", 0),
                "rating": opa_point.get("average_rating"),
                "tma_seconds": opa_point.get("average_tma_effective_seconds"),
                "tmr_seconds": opa_point.get("average_tmr_effective_seconds"),
            }
        )

    return {
        "attendant_id": attendant_id,
        "name": collaborator["label"],
        "date_from": date_from,
        "date_to": date_to,
        "previous_date_from": previous_filters.date_from if has_previous else None,
        "previous_date_to": previous_filters.date_to if has_previous else None,
        "goal_scale": factor,
        "ixc_linked": ixc_user is not None,
        "indicators": indicators,
        "summary": summary,
        "daily": daily,
    }
