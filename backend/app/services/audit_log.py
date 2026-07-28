from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models import AuditLog, User


def _json_safe(value: Any) -> Any:
    """Substitui bytes crus (ex: Collaborator.photo) por um marcador de tamanho, em qualquer nível
    de aninhamento. Bytes não são JSON-serializáveis de forma segura - `jsonable_encoder` tenta
    decodificar como UTF-8 e quebra com `UnicodeDecodeError` em qualquer conteúdo binário de
    verdade (uma foto JPEG, por exemplo). Só o tamanho é suficiente pra auditoria saber que mudou -
    o conteúdo em si nunca precisa ir pro log."""
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def snapshot(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return jsonable_encoder(_json_safe(value))
    data: dict[str, Any] = {}
    for key in getattr(value, "__table__").columns.keys():
        item = getattr(value, key)
        if hasattr(item, "isoformat"):
            item = item.isoformat()
        data[key] = item
    return jsonable_encoder(_json_safe(data))


def record_audit_log(
    db: Session,
    user: User | None,
    action: str,
    entity: str,
    entity_id: str | int | None = None,
    before_data: Any = None,
    after_data: Any = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            action=action,
            entity=entity,
            entity_id=str(entity_id) if entity_id is not None else None,
            before_data=snapshot(before_data),
            after_data=snapshot(after_data),
        )
    )
