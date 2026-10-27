"""Detalhe analítico do Feedback individual (pedido do usuário, 2026-10-27): O.S. abertas indevidamente (IXC) e
distribuição das notas de avaliação (OPA). Valores e listas saem prontos daqui; a tela só desenha.

"O.S. indevida" é uma O.S. de campo aberta pelo colaborador que cai em pelo menos um destes motivos:
  - diagnóstico de encerramento em `IMPROPER_DIAGNOSES` (desistência, assunto errado, duplicada);
  - duplicidade: o mesmo cliente já tinha outra O.S. de campo aberta até `DUPLICATE_WINDOW_HOURS` antes.
Nota boa = 4 a 5, neutra = entre 2 e 4, ruim = até 2 (corte definido pelo usuário)."""
from __future__ import annotations

import unicodedata
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.operations.models import OperationOrder
from app.modules.operations.scope import PRIMARY_SECTOR_NAMES

from . import feedback_service, ixc_n1
from .models import SupportOpaAttendance
from .opa_filters import OpaAttendanceFilters, apply_opa_attendance_filters

DUPLICATE_WINDOW_HOURS = 72
MAX_ROWS = 200
GOOD_MIN = 4.0
BAD_MAX = 2.0

# Chave (sem acento e sem caixa) -> motivo exibido. Diagnósticos reais do IXC (set-out/2026).
IMPROPER_DIAGNOSES: dict[str, str] = {
    "desistencia da solicitacao": "Desistência da solicitação",
    "atendimento com assunto errado": "Assunto errado",
    "ordem de servico duplicada": "O.S. duplicada (diagnóstico)",
}
DUPLICATE_REASON = f"Duplicada (mesmo cliente em até {DUPLICATE_WINDOW_HOURS} h)"

# O.S. que não entram nas indevidas mas a análise destaca (casam por trecho do diagnóstico, sem acento e sem caixa):
# resolvíveis por orientação remota e a revisar. Uma O.S. conta em só um grupo: indevida > remota > revisar.
REMOTE_DIAGNOSES: dict[str, str] = {
    "equipamentos travados": "Equipamento travado",
    "equipamento resetado": "Equipamento resetado",
    "procedimento organizacional": "Procedimento organizacional",
}
REVIEW_DIAGNOSES: dict[str, str] = {
    "atualizacao de configuracao": "Atualização de configuração",
    "problemas na rede interna": "Problema na rede interna do cliente",
}
NO_DIAGNOSIS_REASON = "Finalizada sem diagnóstico"
REPEAT_CUSTOMER_MIN = 2
REPORT_MAX_CHARS = 600


def _plain(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    return " ".join(text.lower().split())


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _match_part(plain_diagnosis: str, table: dict[str, str]) -> str | None:
    return next((label for key, label in table.items() if key in plain_diagnosis), None)


def _group(by_reason: dict[str, int]) -> dict[str, Any]:
    return {
        "count": sum(by_reason.values()),
        "by_reason": [{"reason": reason, "count": count} for reason, count in sorted(by_reason.items(), key=lambda item: -item[1])],
    }


def _report(order: OperationOrder) -> str | None:
    """Relato de finalização da O.S. (`mensagem_resposta` do IXC, escrito pelo técnico), sem quebras e limitado."""
    text = " ".join(str((order.raw_payload or {}).get("mensagem_resposta") or "").split())
    if not text:
        return None
    return text if len(text) <= REPORT_MAX_CHARS else text[: REPORT_MAX_CHARS - 1].rstrip() + "…"


def _empty_bands() -> dict[str, int]:
    return {"good": 0, "neutral": 0, "bad": 0}


def improper_orders(db: Session, *, name_key: str, date_from: date, date_to: date) -> dict[str, Any]:
    """O.S. de campo abertas pelo colaborador no período, com as indevidas e o motivo de cada uma."""
    query = select(OperationOrder).where(
        func.lower(func.trim(OperationOrder.creator)) == name_key,
        OperationOrder.sector.in_(PRIMARY_SECTOR_NAMES),
    )
    orders = db.scalars(ixc_n1.apply_period_utc(query, OperationOrder.opened_at, date_from, date_to).order_by(OperationOrder.opened_at)).all()

    # Outras O.S. de campo dos mesmos clientes, de antes do início do período até o fim, para achar a "original".
    customers = {order.customer_id for order in orders if order.customer_id}
    siblings: dict[str, list[tuple[datetime, int]]] = defaultdict(list)
    if customers:
        earliest = datetime.combine(date_from, time.min, tzinfo=timezone.utc) - timedelta(hours=DUPLICATE_WINDOW_HOURS + 24)
        sibling_query = select(OperationOrder.id, OperationOrder.customer_id, OperationOrder.opened_at).where(
            OperationOrder.customer_id.in_(customers),
            OperationOrder.sector.in_(PRIMARY_SECTOR_NAMES),
            OperationOrder.opened_at >= earliest,
        )
        for order_id, customer_id, opened_at in db.execute(sibling_query).all():
            siblings[customer_id].append((_aware(opened_at), order_id))

    window = timedelta(hours=DUPLICATE_WINDOW_HOURS)
    rows: list[dict[str, Any]] = []
    by_reason: dict[str, int] = defaultdict(int)
    remote: dict[str, int] = defaultdict(int)
    review: dict[str, int] = defaultdict(int)
    no_diagnosis_codes: list[str] = []
    for order in orders:
        reasons: list[str] = []
        label = IMPROPER_DIAGNOSES.get(_plain(order.diagnosis))
        if label is not None:
            reasons.append(label)
        opened = _aware(order.opened_at)
        if order.customer_id and any(
            other_id != order.id and opened - window <= other_at < opened for other_at, other_id in siblings.get(order.customer_id, [])
        ):
            reasons.append(DUPLICATE_REASON)
        if not reasons:
            plain = _plain(order.diagnosis)
            if (label := _match_part(plain, REMOTE_DIAGNOSES)) is not None:
                remote[label] += 1
            elif (label := _match_part(plain, REVIEW_DIAGNOSES)) is not None:
                review[label] += 1
            elif not plain and _plain(order.status) == "finalizada":
                review[NO_DIAGNOSIS_REASON] += 1
                no_diagnosis_codes.append(order.order_code)
            continue
        for reason in reasons:
            by_reason[reason] += 1
        rows.append(
            {
                "order_code": order.order_code,
                "customer_name": order.customer_name,
                "opened_at": opened,
                "status": order.status,
                "diagnosis": order.diagnosis,
                "reasons": reasons,
                "report": _report(order),
            }
        )
    total = len(orders)
    per_customer: dict[str, int] = defaultdict(int)
    for order in orders:
        if order.customer_id:
            per_customer[order.customer_id] += 1
    names = {order.customer_id: order.customer_name for order in orders if order.customer_id}
    repeats = sorted(((names[cid] or cid, count) for cid, count in per_customer.items() if count >= REPEAT_CUSTOMER_MIN), key=lambda item: -item[1])
    return {
        "total_orders": total,
        "remote_resolvable": _group(remote),
        "to_review": _group(review),
        "no_diagnosis_codes": no_diagnosis_codes[:5],
        "repeat_customers": [{"customer_name": name, "count": count} for name, count in repeats[:5]],
        "improper_count": len(rows),
        "improper_percent": round(len(rows) / total * 100, 1) if total else None,
        "by_reason": [{"reason": reason, "count": count} for reason, count in sorted(by_reason.items(), key=lambda item: -item[1])],
        "orders": rows[:MAX_ROWS],
        "truncated": len(rows) > MAX_ROWS,
    }


def rating_band(rating: float) -> str:
    if rating >= GOOD_MIN:
        return "good"
    if rating <= BAD_MAX:
        return "bad"
    return "neutral"


def rating_breakdown(db: Session, *, attendant_id: str, date_from: date, date_to: date) -> dict[str, Any]:
    """Notas do OPA do colaborador no período: faixas, por dia, por canal e a lista dos atendimentos avaliados."""
    filters = OpaAttendanceFilters(date_from=date_from, date_to=date_to, attendant_id=attendant_id)
    statement = apply_opa_attendance_filters(
        select(SupportOpaAttendance).where(SupportOpaAttendance.rating.is_not(None)).order_by(SupportOpaAttendance.opened_at.desc()), filters
    )
    attendances = db.scalars(statement).all()

    counts = _empty_bands()
    per_day: dict[date, dict[str, int]] = defaultdict(_empty_bands)
    per_channel: dict[str, dict[str, int]] = defaultdict(_empty_bands)
    rows = []
    for item in attendances:
        band = rating_band(float(item.rating))
        counts[band] += 1
        per_day[_aware(item.opened_at).date()][band] += 1
        per_channel[item.channel or "Sem canal"][band] += 1
        rows.append(
            {
                "protocol": item.protocol,
                "opened_at": _aware(item.opened_at),
                "channel": item.channel,
                "rating": float(item.rating),
                "band": band,
                "reason": item.reason_name,
                "tma_seconds": item.tma_seconds,
                "tmr_seconds": item.tmr_seconds,
            }
        )
    total = len(attendances)

    def band_view(key: str) -> dict[str, Any]:
        return {"count": counts[key], "percent": round(counts[key] / total * 100, 1) if total else None}

    return {
        "rated_count": total,
        "average": round(sum(row["rating"] for row in rows) / total, 2) if total else None,
        "good": band_view("good"),
        "neutral": band_view("neutral"),
        "bad": band_view("bad"),
        "by_day": [{"day": day, **values} for day, values in sorted(per_day.items())],
        "by_channel": [{"channel": channel, **values} for channel, values in sorted(per_channel.items(), key=lambda item: -sum(item[1].values()))],
        "attendances": rows[:MAX_ROWS],
        "truncated": total > MAX_ROWS,
    }


def collaborator_details(db: Session, *, date_from: date, date_to: date, attendant_id: str) -> dict[str, Any] | None:
    """`None` quando `attendant_id` não é da equipe do Suporte; sem usuário no IXC, `improper_orders` vem `None`."""
    resolved = feedback_service.resolve_collaborator(db, attendant_id)
    if resolved is None:
        return None
    collaborator, ixc_user = resolved
    orders = improper_orders(db, name_key=feedback_service._name_key(ixc_user.name), date_from=date_from, date_to=date_to) if ixc_user else None
    return {
        "attendant_id": attendant_id,
        "name": collaborator["label"],
        "date_from": date_from,
        "date_to": date_to,
        "ixc_linked": ixc_user is not None,
        "ratings": rating_breakdown(db, attendant_id=attendant_id, date_from=date_from, date_to=date_to),
        "improper_orders": orders,
    }
