"""Timeline/histórico de um atendimento do SGP Suporte (OPA Suite).

Fase 3C: primeira versão segura. Nunca expõe TEXTO de mensagem — só quem
enviou (cliente/bot/atendente) e o instante, o suficiente para visualizar o
fluxo da conversa sem tocar em conteúdo sensível. Texto completo de mensagem
fica para quando existir a permissão granular `support:view_conversation`
(ainda não implementada — ver docs/plano-analise-opa-suite-atendimentos.md,
seção "Regras de acesso e privacidade").

Não persiste mensagem nenhuma: a busca ao vivo no OPA Suite é sob demanda,
só para o atendimento aberto no detalhe (nunca em lote), e uma falha nela
nunca derruba a timeline estrutural (que já vem 100% do banco local).
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.services.opa_client import get_opa_client

from .models import SupportOpaAttendance
from .opa_ingestion import (
    _load_attendant_types,
    _message_is_from_client,
    _message_is_from_theo_bot,
    _message_timestamp,
)

logger = logging.getLogger("support")

MESSAGES_SOURCE_LIVE = "live"
MESSAGES_SOURCE_UNAVAILABLE = "unavailable"
MESSAGES_SOURCE_NOT_ATTEMPTED = "not_attempted"


def _structural_events(row: SupportOpaAttendance) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = [
        {
            "type": "opened",
            "actor_type": "system",
            "occurred_at": row.opened_at,
            "label": "Atendimento aberto",
            "description": None,
        }
    ]
    if row.bot_to_human_handoff:
        events.append(
            {
                "type": "bot_handoff",
                "actor_type": "bot",
                "occurred_at": row.first_response_at,
                "label": "Transferido do atendimento automatizado para um atendente humano",
                "description": (
                    "Inferido pela classificação bot/humano do atendimento; ainda não há "
                    "timestamp exato do momento da transferência."
                ),
            }
        )
    if row.first_response_at is not None:
        events.append(
            {
                "type": "first_human_response",
                "actor_type": "human",
                "occurred_at": row.first_response_at,
                "label": "Primeira resposta do atendente humano",
                "description": None,
            }
        )
    if row.closed_at is not None:
        events.append(
            {
                "type": "closed",
                "actor_type": "system",
                "occurred_at": row.closed_at,
                "label": "Atendimento encerrado",
                "description": None,
            }
        )
    events.sort(key=lambda event: event["occurred_at"] or row.opened_at)
    return events


def _message_events(messages: list[dict[str, Any]], attendant_types: dict[str, str]) -> list[dict[str, Any]]:
    """Converte mensagens brutas do OPA Suite em eventos de timeline SEM texto —
    só remetente (cliente/bot/atendente) e instante."""
    events: list[dict[str, Any]] = []
    for message in messages:
        timestamp = _message_timestamp(message)
        if timestamp is None:
            continue
        if _message_is_from_client(message):
            actor_type = "client"
            label = "Mensagem do cliente"
        elif _message_is_from_theo_bot(message):
            # Log interno do agente virtual (chamada de ferramenta/retorno) —
            # sem `id_atend` porque não é atribuído a um cadastro de
            # atendente, mas é participação real do bot. Sem esta checagem
            # aparecia como "remetente não identificado" na tela.
            actor_type = "bot"
            label = "Mensagem do atendimento automatizado"
        else:
            attendant_id = message.get("id_atend")
            attendant_type = attendant_types.get(attendant_id) if attendant_id else None
            if attendant_type == "bot":
                actor_type = "bot"
                label = "Mensagem do atendimento automatizado"
            elif attendant_type is not None:
                actor_type = "human"
                label = "Mensagem do atendente"
            else:
                actor_type = "unknown"
                label = "Mensagem (remetente não identificado)"
        events.append(
            {"type": "message", "actor_type": actor_type, "occurred_at": timestamp, "label": label, "description": None}
        )
    events.sort(key=lambda event: event["occurred_at"])
    return events


def build_timeline(db: Session, row: SupportOpaAttendance, *, include_messages: bool = True) -> dict[str, Any]:
    events = _structural_events(row)
    messages_source = MESSAGES_SOURCE_NOT_ATTEMPTED
    messages_error: str | None = None

    if include_messages:
        try:
            client = get_opa_client()
            messages = client.list_messages(row.source_id)
            attendant_types = _load_attendant_types(db)
            events.extend(_message_events(messages, attendant_types))
            events.sort(key=lambda event: event["occurred_at"] or row.opened_at)
            messages_source = MESSAGES_SOURCE_LIVE
        except Exception as exc:
            # Nunca deixa a falha da API externa derrubar a timeline estrutural
            # (já montada acima, só com dado local). Mensagem amigável ao
            # usuário, sem stack trace nem conteúdo de conversa no log.
            logger.warning("falha_buscar_mensagens_timeline source_id=%s erro=%s", row.source_id, exc)
            messages_source = MESSAGES_SOURCE_UNAVAILABLE
            messages_error = (
                "Não foi possível carregar as mensagens do OPA Suite agora. "
                "O restante da timeline continua disponível."
            )

    return {
        "attendance_id": row.id,
        "source_id": row.source_id,
        "protocol": row.protocol,
        "status": row.status,
        "reason_name": row.reason_name,
        "department_name": row.department_name,
        "attendant_name": row.attendant_name,
        "handled_by_bot": row.handled_by_bot,
        "reached_human": row.reached_human,
        "bot_to_human_handoff": row.bot_to_human_handoff,
        "opened_at": row.opened_at,
        "closed_at": row.closed_at,
        "first_response_at": row.first_response_at,
        "events": events,
        "messages_source": messages_source,
        "messages_error": messages_error,
    }
