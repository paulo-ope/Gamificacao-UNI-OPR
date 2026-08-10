from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import permissions_for_user, verify_api_key
from app.db.session import get_db
from app.models import User
from app.modules.ai.models import ApiKeyCredential

# Não é segredo (o segredo é o hash) - só o tanto de caracteres do início da chave usado pra achar
# a linha candidata sem comparar hash contra a tabela inteira. cli.py usa a mesma constante ao
# gravar key_prefix na criação.
API_KEY_PREFIX_LENGTH = 12

_api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)


def require_api_key_user(
    api_key: str | None = Security(_api_key_header),
    db: Session = Depends(get_db),
) -> User:
    # Mensagem de erro sempre genérica (não distingue "chave não existe" de "chave revogada") -
    # isso evita que alguém tentando adivinhar chaves aprenda algo pelo tipo de resposta.
    invalid = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Chave de API inválida.")
    if not api_key:
        raise invalid

    prefix = api_key[:API_KEY_PREFIX_LENGTH]
    candidates = db.scalars(
        select(ApiKeyCredential).where(
            ApiKeyCredential.key_prefix == prefix,
            ApiKeyCredential.active.is_(True),
            ApiKeyCredential.revoked_at.is_(None),
        )
    ).all()

    for credential in candidates:
        if not verify_api_key(api_key, credential.key_hash):
            continue
        user = db.get(User, credential.user_id)
        if not user or not user.active:
            break
        credential.last_used_at = datetime.now(timezone.utc)
        db.commit()
        return user

    raise invalid


def require_ai_permission(permission: str):
    def dependency(user: User = Depends(require_api_key_user)) -> User:
        if permission not in permissions_for_user(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permissão insuficiente.")
        return user

    return dependency
