from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models import AuditLog, User


def snapshot(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return jsonable_encoder(value)
    data: dict[str, Any] = {}
    for key in getattr(value, "__table__").columns.keys():
        item = getattr(value, key)
        if hasattr(item, "isoformat"):
            item = item.isoformat()
        data[key] = item
    return jsonable_encoder(data)


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
