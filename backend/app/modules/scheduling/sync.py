"""Sincronização IXC → tabelas locais do módulo de Agendamento.

Espelha O.S. dos setores técnicos e os eventos 1/5/10/6 do log de mensagens. Roda de duas formas:
- backfill por intervalo de datas (primeira carga / recuperação de buraco);
- incremental por marca d'água (`AppSetting` chave `scheduling_sync_last_event_at`), com overlap
  de 30 minutos para não perder evento gravado durante a paginação (mesma lição da sincronização
  da gamificação - ver docs/plano-integracao-ixc.md sobre paginação por offset).

Serializado por advisory lock do Postgres: sync incremental e backfill manual nunca escrevem ao
mesmo tempo (mesmo padrão do `_ixc_import_lock` do importador da gamificação).
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from datetime import datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import AppSetting
from app.modules.scheduling.models import SchedulingEvent, SchedulingOrder, SYNCED_EVENT_TYPES
from app.services.calculation_closure import PORTO_VELHO_TZ
from app.services.ixc_client import IxcClient, fetch_assuntos, fetch_setores

logger = logging.getLogger("scheduling_sync")

WATERMARK_KEY = "scheduling_sync_last_event_at"
TECHNICAL_SECTOR_IDS = ["7", "8", "9"]
SCHEDULING_SYNC_LOCK_KEY = 913_027_401  # arbitrário, distinto dos locks já usados no projeto
_WATERMARK_OVERLAP = timedelta(minutes=30)
_FMT = "%Y-%m-%d %H:%M:%S"


def _parse_dt(value) -> datetime | None:
    """Todo datetime bruto do IXC já vem em horário LOCAL de Rondônia, sem informação de fuso
    (achado real, docs/plano-integracao-ixc.md seção 6). Anexa `PORTO_VELHO_TZ` explicitamente -
    sem isso, o driver do Postgres grava o valor naive como se já fosse UTC, deslocando todo
    horário exibido em 4h (achado real, 2026-07-29: "Aberta em" mostrava 03:59 quando o IXC e o
    relógio de Rondônia diziam 07:59)."""
    raw = str(value or "")
    if not raw or raw.startswith("0000-00-00"):
        return None
    try:
        naive = datetime.strptime(raw, _FMT)
    except ValueError:
        return None
    return naive.replace(tzinfo=PORTO_VELHO_TZ)


@contextmanager
def _sync_lock(db: Session):
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        yield
        return
    waited = 0.0
    acquired = False
    while waited <= 30:
        acquired = bool(db.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": SCHEDULING_SYNC_LOCK_KEY}).scalar())
        if acquired:
            break
        time.sleep(1)
        waited += 1
    if not acquired:
        raise RuntimeError("Outra sincronização do módulo de Agendamento já está em andamento.")
    try:
        yield
    finally:
        db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": SCHEDULING_SYNC_LOCK_KEY})


def _get_watermark(db: Session) -> datetime | None:
    row = db.execute(select(AppSetting).where(AppSetting.key == WATERMARK_KEY)).scalar_one_or_none()
    return _parse_dt(row.value) if row else None


def _set_watermark(db: Session, value: datetime) -> None:
    row = db.execute(select(AppSetting).where(AppSetting.key == WATERMARK_KEY)).scalar_one_or_none()
    formatted = value.strftime(_FMT)
    if row:
        row.value = formatted
    else:
        db.add(AppSetting(key=WATERMARK_KEY, value=formatted, description="Marca d'água do sync de eventos de agendamento (relógio do IXC)."))


def _order_payload(record: dict, assuntos: dict[str, str], setores: dict[str, str]) -> dict | None:
    opened_at = _parse_dt(record.get("data_abertura"))
    if opened_at is None:
        return None
    setor_id = str(record.get("setor") or "")
    assunto_id = str(record.get("id_assunto") or "") or None
    return {
        "ixc_os_id": int(record["id"]),
        "opened_at": opened_at,
        "setor_id": setor_id,
        "setor_name": setores.get(setor_id, f"Setor {setor_id}"),
        "filial_id": str(record.get("id_filial") or ""),
        "assunto_id": assunto_id,
        "assunto_name": assuntos.get(assunto_id or "", None),
        "status": str(record.get("status") or "") or None,
        "closed_at": _parse_dt(record.get("data_fechamento")),
    }


def _sync_orders(db: Session, client: IxcClient, *, opened_after: str, opened_before: str) -> dict:
    assuntos = {str(a.get("id")): str(a.get("assunto") or "") for a in fetch_assuntos(client)}
    setores = {str(s.get("id")): str(s.get("setor") or "") for s in fetch_setores(client)}

    created = updated = 0
    page = 1
    while True:
        result = client.list(
            "su_oss_chamado",
            grid_param=[
                {"TB": "su_oss_chamado.data_abertura", "OP": ">=", "P": opened_after},
                {"TB": "su_oss_chamado.data_abertura", "OP": "<=", "P": opened_before},
                {"TB": "su_oss_chamado.setor", "OP": "IN", "P": ",".join(TECHNICAL_SECTOR_IDS)},
            ],
            page=page, rp=200, sortname="su_oss_chamado.id", sortorder="asc",
        )
        if not result.records:
            break
        ids = [int(r["id"]) for r in result.records]
        existing = {
            o.ixc_os_id: o
            for o in db.execute(select(SchedulingOrder).where(SchedulingOrder.ixc_os_id.in_(ids))).scalars()
        }
        for record in result.records:
            payload = _order_payload(record, assuntos, setores)
            if payload is None:
                continue
            order = existing.get(payload["ixc_os_id"])
            if order is None:
                db.add(SchedulingOrder(**payload))
                created += 1
            else:
                for key, value in payload.items():
                    setattr(order, key, value)
                updated += 1
        db.flush()
        if len(result.records) >= result.total or page * 200 >= result.total:
            break
        page += 1
    return {"orders_created": created, "orders_updated": updated}


def _fetch_missing_orders(db: Session, client: IxcClient, os_ids: list[int]) -> int:
    """Eventos podem referenciar O.S. abertas ANTES da janela sincronizada (ex.: reagendamento de
    uma O.S. do mês anterior). Busca essas O.S. por id, em lotes, para o evento não ficar órfão."""
    if not os_ids:
        return 0
    assuntos = {str(a.get("id")): str(a.get("assunto") or "") for a in fetch_assuntos(client)}
    setores = {str(s.get("id")): str(s.get("setor") or "") for s in fetch_setores(client)}
    created = 0
    for start in range(0, len(os_ids), 200):
        batch = os_ids[start:start + 200]
        result = client.list(
            "su_oss_chamado",
            grid_param=[{"TB": "su_oss_chamado.id", "OP": "IN", "P": ",".join(str(i) for i in batch)}],
            page=1, rp=len(batch), sortname="su_oss_chamado.id",
        )
        for record in result.records:
            # O filtro de setor não entra na busca por id (o evento já passou pelo recorte do
            # módulo indiretamente?) - entra sim: fora dos setores técnicos, descarta.
            if str(record.get("setor") or "") not in TECHNICAL_SECTOR_IDS:
                continue
            payload = _order_payload(record, assuntos, setores)
            if payload is not None:
                db.add(SchedulingOrder(**payload))
                created += 1
    db.flush()
    return created


def _sync_events(db: Session, client: IxcClient, *, events_after: str, events_before: str | None) -> dict:
    grid_param = [
        {"TB": "su_oss_chamado_mensagem.id_evento", "OP": "IN", "P": ",".join(SYNCED_EVENT_TYPES)},
        {"TB": "su_oss_chamado_mensagem.data", "OP": ">=", "P": events_after},
    ]
    if events_before:
        grid_param.append({"TB": "su_oss_chamado_mensagem.data", "OP": "<=", "P": events_before})

    known_orders: set[int] = set(db.execute(select(SchedulingOrder.ixc_os_id)).scalars())
    created = skipped_foreign = 0
    touched_orders: set[int] = set()
    missing_order_events: list[dict] = []
    latest_event_at: datetime | None = None

    page = 1
    while True:
        result = client.list(
            "su_oss_chamado_mensagem",
            grid_param=grid_param,
            page=page, rp=500, sortname="su_oss_chamado_mensagem.id", sortorder="asc",
        )
        if not result.records:
            break
        message_ids = [int(r["id"]) for r in result.records]
        existing_ids = set(
            db.execute(select(SchedulingEvent.ixc_message_id).where(SchedulingEvent.ixc_message_id.in_(message_ids))).scalars()
        )
        for record in result.records:
            event_at = _parse_dt(record.get("data"))
            if event_at is None:
                continue
            if latest_event_at is None or event_at > latest_event_at:
                latest_event_at = event_at
            if int(record["id"]) in existing_ids:
                continue
            os_id = int(record.get("id_chamado") or 0)
            if os_id not in known_orders:
                missing_order_events.append(record)
                continue
            db.add(_event_from_record(record, event_at))
            touched_orders.add(os_id)
            created += 1
        db.flush()
        seen = page * 500
        if len(result.records) < 500 or (result.total and seen >= result.total):
            break
        page += 1

    # Segunda passada: eventos de O.S. que o módulo ainda não conhecia (abertas fora da janela).
    if missing_order_events:
        candidate_ids = sorted({int(r.get("id_chamado") or 0) for r in missing_order_events if r.get("id_chamado")})
        _fetch_missing_orders(db, client, candidate_ids)
        known_orders = set(db.execute(select(SchedulingOrder.ixc_os_id).where(SchedulingOrder.ixc_os_id.in_(candidate_ids))).scalars())
        for record in missing_order_events:
            os_id = int(record.get("id_chamado") or 0)
            if os_id not in known_orders:
                skipped_foreign += 1  # O.S. de setor fora do escopo - descartada de propósito
                continue
            event_at = _parse_dt(record.get("data"))
            if event_at is None:
                continue
            db.add(_event_from_record(record, event_at))
            touched_orders.add(os_id)
            created += 1
        db.flush()

    return {
        "events_created": created,
        "events_skipped_foreign": skipped_foreign,
        "touched_orders": touched_orders,
        "latest_event_at": latest_event_at,
    }


def _event_from_record(record: dict, event_at: datetime) -> SchedulingEvent:
    operator_raw = str(record.get("id_operador") or "").strip()
    technician_raw = str(record.get("id_tecnico") or "").strip()
    return SchedulingEvent(
        ixc_message_id=int(record["id"]),
        ixc_os_id=int(record["id_chamado"]),
        event_type=str(record.get("id_evento") or ""),
        event_at=event_at,
        window_start=_parse_dt(record.get("data_inicio")),
        window_end=_parse_dt(record.get("data_final")),
        operator_id=int(operator_raw) if operator_raw.isdigit() and operator_raw != "0" else None,
        technician_id=int(technician_raw) if technician_raw.isdigit() and technician_raw != "0" else None,
        mensagem=str(record.get("mensagem") or "").strip() or None,
        historico=str(record.get("historico") or "").strip() or None,
    )


def backfill_messages(db: Session, client: IxcClient, *, batch_size: int = 200) -> dict:
    """Preenche `mensagem`/`historico` dos eventos já sincronizados ANTES desses campos existirem
    (a extração original descartava o texto, ver achado de 2026-07-30). Reconsulta cada evento por
    `ixc_message_id` em lotes - não dá pra refazer o sync inteiro só por isso."""
    pending_ids = list(
        db.execute(select(SchedulingEvent.ixc_message_id).where(SchedulingEvent.mensagem.is_(None))).scalars()
    )
    updated = 0
    for start in range(0, len(pending_ids), batch_size):
        batch = pending_ids[start:start + batch_size]
        result = client.list(
            "su_oss_chamado_mensagem",
            grid_param=[{"TB": "su_oss_chamado_mensagem.id", "OP": "IN", "P": ",".join(str(i) for i in batch)}],
            page=1, rp=len(batch), sortname="su_oss_chamado_mensagem.id",
        )
        by_message_id = {int(r["id"]): r for r in result.records}
        events = db.execute(select(SchedulingEvent).where(SchedulingEvent.ixc_message_id.in_(batch))).scalars()
        for event in events:
            record = by_message_id.get(event.ixc_message_id)
            if record is None:
                continue
            event.mensagem = str(record.get("mensagem") or "").strip() or None
            event.historico = str(record.get("historico") or "").strip() or None
            updated += 1
        db.flush()
    db.commit()
    return {"events_updated": updated, "events_pending_before": len(pending_ids)}


def _recompute_derived(db: Session, os_ids: set[int]) -> None:
    """Recalcula os campos derivados (`first_scheduled_at` etc.) das O.S. tocadas na rodada."""
    if not os_ids:
        return
    ids = sorted(os_ids)
    for start in range(0, len(ids), 500):
        batch = ids[start:start + 500]
        orders = {o.ixc_os_id: o for o in db.execute(select(SchedulingOrder).where(SchedulingOrder.ixc_os_id.in_(batch))).scalars()}
        events = db.execute(
            select(SchedulingEvent).where(SchedulingEvent.ixc_os_id.in_(batch)).order_by(SchedulingEvent.event_at.asc())
        ).scalars()
        by_order: dict[int, list[SchedulingEvent]] = {}
        for event in events:
            by_order.setdefault(event.ixc_os_id, []).append(event)
        for os_id, order in orders.items():
            order_events = by_order.get(os_id, [])
            schedules = [e for e in order_events if e.event_type in ("5", "10")]
            first_five = next((e for e in order_events if e.event_type == "5"), None)
            closure = next((e for e in order_events if e.event_type == "6"), None)
            order.schedule_event_count = len(schedules)
            order.first_scheduled_at = first_five.event_at if first_five else None
            order.first_window_start = first_five.window_start if first_five else None
            order.first_operator_id = first_five.operator_id if first_five else None
            order.first_technician_id = first_five.technician_id if first_five else None
            if closure and order.closed_at is None:
                order.closed_at = closure.event_at
        db.flush()


def run_sync(
    db: Session,
    client: IxcClient,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Executa uma rodada de sincronização.

    Com `date_from`/`date_to` (formato YYYY-MM-DD): backfill daquele intervalo de abertura de O.S.
    Sem parâmetros: incremental a partir da marca d'água de eventos (e O.S. abertas nos últimos
    2 dias, para pegar aberturas novas cujo evento ainda não veio).
    """
    with _sync_lock(db):
        if date_from and date_to:
            opened_after = f"{date_from} 00:00:00"
            opened_before = f"{date_to} 23:59:59"
            events_after = opened_after
            events_before = None  # eventos de O.S. do período podem acontecer depois do período
        else:
            watermark = _get_watermark(db)
            if watermark is None:
                raise RuntimeError("Sem marca d'água - rode um backfill com intervalo de datas primeiro.")
            events_start = watermark - _WATERMARK_OVERLAP
            events_after = events_start.strftime(_FMT)
            events_before = None
            opened_after = (watermark - timedelta(days=2)).strftime(_FMT)
            opened_before = (watermark + timedelta(days=365)).strftime(_FMT)

        started = time.monotonic()
        order_stats = _sync_orders(db, client, opened_after=opened_after, opened_before=opened_before)
        event_stats = _sync_events(db, client, events_after=events_after, events_before=events_before)
        _recompute_derived(db, event_stats["touched_orders"])

        if event_stats["latest_event_at"] is not None:
            _set_watermark(db, event_stats["latest_event_at"])
        db.commit()

        result = {
            **order_stats,
            "events_created": event_stats["events_created"],
            "events_skipped_foreign": event_stats["events_skipped_foreign"],
            "orders_recomputed": len(event_stats["touched_orders"]),
            "duration_seconds": round(time.monotonic() - started, 1),
        }
        logger.info("Sync de agendamento concluído: %s", result)
        return result
