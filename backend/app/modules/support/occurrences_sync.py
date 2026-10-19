"""Sincroniza diagnóstico e finalização das ocorrências (assunto 211 do IXC).

Roda logo depois da importação de atendimentos (`ixc_ticket_ingestion`), só para os tickets do
assunto 211 do lote: o diagnóstico vem do próprio ticket (`id_su_diagnostico`) e a finalização da
mensagem `su_mensagens` com `su_status = 'S'`. Idempotente por `source_id`."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services.ixc_client import IxcClient, fetch_diagnosticos, fetch_ticket_finalization_messages

from .ixc_ticket_ingestion import _clean, _parse_ixc_datetime
from .models import SupportIxcTicket, SupportIxcTicketRaw, SupportOccurrenceDetail
from .occurrences_service import OCCURRENCE_SUBJECT_ID

logger = logging.getLogger(__name__)

FINALIZED_STATUS = "S"
CHUNK_SIZE = 150


def _diagnosis_id(value: Any) -> str | None:
    text = _clean(value)
    return text if text and text != "0" else None


def sync_occurrence_details(db: Session, client: IxcClient, records: list[dict[str, Any]]) -> dict[str, int]:
    """`records` são `su_ticket` crus; só os do assunto 211 são processados."""
    tickets = [r for r in records if _clean(r.get("id_assunto")) == OCCURRENCE_SUBJECT_ID and _clean(r.get("id"))]
    result = {"tickets": len(tickets), "finalized": 0, "open": 0}
    if not tickets:
        return result

    diagnosis_names = {
        _clean(d.get("id")): _clean(d.get("descricao")) for d in fetch_diagnosticos(client) if _clean(d.get("id"))
    }

    finalized_ids = [_clean(t["id"]) for t in tickets if _clean(t.get("su_status")) == FINALIZED_STATUS]
    finalization_by_ticket: dict[str, dict[str, Any]] = {}
    for start in range(0, len(finalized_ids), CHUNK_SIZE):
        for message in fetch_ticket_finalization_messages(client, finalized_ids[start : start + CHUNK_SIZE]):
            ticket_id = _clean(message.get("id_ticket"))
            current = finalization_by_ticket.get(ticket_id)
            # Vale a finalização mais recente (um ticket reaberto pode ter finalizado mais de uma vez).
            if current is None or _clean(message.get("data")) >= _clean(current.get("data")):
                finalization_by_ticket[ticket_id] = message

    now = datetime.now(timezone.utc)
    for ticket in tickets:
        source_id = _clean(ticket["id"])
        message = finalization_by_ticket.get(source_id)
        diagnosis_id = _diagnosis_id(ticket.get("id_su_diagnostico")) or _diagnosis_id(
            (message or {}).get("id_su_diagnostico")
        )
        values = {
            "diagnosis_id": diagnosis_id,
            "diagnosis_name": diagnosis_names.get(diagnosis_id or "") or None,
            "ticket_status": _clean(ticket.get("su_status")) or None,
            "finalized_at": _parse_ixc_datetime(message.get("data")) if message else None,
            "finalization_report": (_clean(message.get("mensagem")) or None) if message else None,
            "finalized_by_id": (_clean(message.get("operador")).lstrip("0") or None) if message else None,
            "synced_at": now,
        }
        detail = db.scalar(select(SupportOccurrenceDetail).where(SupportOccurrenceDetail.source_id == source_id))
        if detail is None:
            db.add(SupportOccurrenceDetail(source_id=source_id, **values))
        else:
            for field_name, value in values.items():
                setattr(detail, field_name, value)
        result["finalized" if message else "open"] += 1
    db.commit()
    return result


def backfill_occurrence_details(db: Session, client: IxcClient) -> dict[str, int]:
    """Preenche o detalhe de todas as ocorrências já importadas (payload bruto dos tickets 211)."""
    source_ids = db.scalars(
        select(SupportIxcTicket.source_id).where(SupportIxcTicket.subject_id == OCCURRENCE_SUBJECT_ID)
    ).all()
    records: list[dict[str, Any]] = []
    for start in range(0, len(source_ids), 500):
        chunk = source_ids[start : start + 500]
        records.extend(
            db.scalars(select(SupportIxcTicketRaw.payload_json).where(SupportIxcTicketRaw.source_id.in_(chunk))).all()
        )
    return sync_occurrence_details(db, client, records)
