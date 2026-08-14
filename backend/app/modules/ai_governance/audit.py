"""Auditoria de uso de API/MCP por agentes de IA - item 14 do pedido. `record_ai_access` é best
effort: uma falha ao gravar auditoria nunca deve derrubar a resposta real ao chamador, então
qualquer exceção é engolida (com rollback) em vez de propagada.

Como em `gate.py`, nada chama isto ainda nesta fase - fica pronto para a Fase 2/5 do plano de
migração conectarem nos endpoints/tools já existentes."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import User
from app.modules.ai_governance.models import AiAccessAuditLog


def summarize_filters(filters: dict | None) -> dict | None:
    """Reduz um dict de filtros a `{campo: quantidade_de_valores}` - nunca grava o valor em si
    (item 14 do pedido: "não armazenar desnecessariamente conteúdo sensível dos relatos no log")."""
    if not filters:
        return None
    summary: dict[str, int] = {}
    for key, value in filters.items():
        if isinstance(value, (list, tuple, set)):
            summary[key] = len(value)
        elif value not in (None, ""):
            summary[key] = 1
    return summary or None


def record_ai_access(
    db: Session,
    *,
    origin: str,
    endpoint_key: str,
    user: User | None = None,
    token_id: int | None = None,
    filters: dict | None = None,
    fields_requested: list[str] | None = None,
    response_mode: str | None = None,
    result_count: int | None = None,
    duration_ms: int | None = None,
    status: str = "success",
    error_message: str | None = None,
) -> None:
    try:
        db.add(
            AiAccessAuditLog(
                user_id=user.id if user else None,
                token_id=token_id,
                origin=origin,
                endpoint_key=endpoint_key,
                filters_summary=summarize_filters(filters),
                fields_requested=fields_requested,
                response_mode=response_mode,
                result_count=result_count,
                duration_ms=duration_ms,
                status=status,
                error_message=error_message[:500] if error_message else None,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
