"""Cadastro manual de classificação de atendente do OPA Suite (agente virtual/bot).

Existe pra cobrir dois casos que a dimensão sincronizada da API
(`SupportOpaDimension.payload_json.tipo`) não resolve sozinha:
1. Um atendente cujo `tipo` no OPA não é (ou deixou de ser) `"bot"`, mas que na
   prática é um agente virtual — TMR humano não faz sentido como métrica principal
   pra ele, TMR geral sim.
2. Atendentes futuros que o OPA nunca chegue a marcar como bot de forma alguma.

`resolve_attendant_type` é a única fonte de verdade de prioridade
(override manual > `payload_json.tipo` > `None`), usada tanto na classificação de
mensagens da ingestão (`opa_ingestion._load_attendant_types`) quanto na identidade
exibida no painel individual (`opa_attendant_service.resolve_attendant_identity`) —
nunca duplicar essa regra em outro lugar.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import SupportOpaAttendantOverride

VIRTUAL_AGENT_CLASSIFICATION = "virtual_agent"
ALLOWED_CLASSIFICATIONS = {VIRTUAL_AGENT_CLASSIFICATION}

# Classificação manual -> `attendant_type` interno que ela força. Hoje só existe um
# valor útil (agente virtual força "bot", o mesmo valor que o OPA usaria), mas o
# mapeamento fica separado do valor de cadastro pra não confundir "o que o usuário
# escolhe" com "o que o sistema entende internamente como bot".
_CLASSIFICATION_TO_ATTENDANT_TYPE = {
    VIRTUAL_AGENT_CLASSIFICATION: "bot",
}


def resolve_attendant_type(
    attendant_id: str | None, opa_tipo: str | None, overrides: dict[str, str]
) -> str | None:
    """Prioridade: override manual ativo > `payload_json.tipo` da dimensão OPA >
    `None` (desconhecido). Nunca inferir `None` como humano nem como bot."""
    if attendant_id:
        override = overrides.get(attendant_id)
        if override in _CLASSIFICATION_TO_ATTENDANT_TYPE:
            return _CLASSIFICATION_TO_ATTENDANT_TYPE[override]
    return opa_tipo or None


def load_active_overrides(db: Session) -> dict[str, str]:
    rows = db.execute(
        select(SupportOpaAttendantOverride.attendant_id, SupportOpaAttendantOverride.classification).where(
            SupportOpaAttendantOverride.active.is_(True)
        )
    ).all()
    return {attendant_id: classification for attendant_id, classification in rows}


def list_overrides(db: Session) -> list[SupportOpaAttendantOverride]:
    return list(
        db.scalars(select(SupportOpaAttendantOverride).order_by(SupportOpaAttendantOverride.created_at.desc()))
    )


def create_override(
    db: Session,
    *,
    attendant_id: str,
    attendant_name: str | None,
    classification: str,
    active: bool,
    created_by: int | None,
) -> SupportOpaAttendantOverride:
    attendant_id = attendant_id.strip()
    if not attendant_id:
        raise ValueError("attendant_id é obrigatório.")
    if classification not in ALLOWED_CLASSIFICATIONS:
        raise ValueError(f"Classificação inválida. Valores aceitos: {sorted(ALLOWED_CLASSIFICATIONS)}.")
    existing = db.scalar(
        select(SupportOpaAttendantOverride).where(SupportOpaAttendantOverride.attendant_id == attendant_id)
    )
    if existing is not None:
        raise ValueError("Já existe um cadastro para este attendant_id.")

    override = SupportOpaAttendantOverride(
        attendant_id=attendant_id,
        attendant_name=(attendant_name or "").strip() or None,
        classification=classification,
        active=active,
        created_by=created_by,
    )
    db.add(override)
    db.flush()
    return override


def update_override(db: Session, override_id: int, changes: dict[str, Any]) -> SupportOpaAttendantOverride:
    override = db.get(SupportOpaAttendantOverride, override_id)
    if override is None:
        raise ValueError("Cadastro de atendente não encontrado.")

    if "classification" in changes and changes["classification"] is not None:
        classification = changes["classification"]
        if classification not in ALLOWED_CLASSIFICATIONS:
            raise ValueError(f"Classificação inválida. Valores aceitos: {sorted(ALLOWED_CLASSIFICATIONS)}.")
        override.classification = classification
    if "attendant_name" in changes:
        name = changes["attendant_name"]
        override.attendant_name = (name or "").strip() or None
    if "active" in changes and changes["active"] is not None:
        override.active = changes["active"]

    db.flush()
    return override


def delete_override(db: Session, override_id: int) -> bool:
    override = db.get(SupportOpaAttendantOverride, override_id)
    if override is None:
        return False
    db.delete(override)
    db.flush()
    return True
