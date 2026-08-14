from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import permissions_for_user, verify_api_key
from app.db.session import get_db
from app.models import User
from app.modules.ai.models import ApiKeyCredential
from app.modules.ai_governance.models import AiApiToken

# Não é segredo (o segredo é o hash) - só o tanto de caracteres do início da chave usado pra achar
# a linha candidata sem comparar hash contra a tabela inteira. cli.py usa a mesma constante ao
# gravar key_prefix na criação.
API_KEY_PREFIX_LENGTH = 12

_api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)


@dataclass(frozen=True)
class ApiKeyContext:
    """Resultado da autenticação por chave de API - `scopes=None` identifica uma chave legado
    (`ApiKeyCredential`, sem conceito de escopo, criada antes da Fase 5 do plano de migração) que
    mantém acesso irrestrito (item 26 do pedido: preservar o comportamento atual). `scopes=[...]`
    identifica um token novo (`AiApiToken`) - `enforce_token_scope` só nega quando a lista existe E
    não contém o escopo pedido."""

    user: User
    scopes: list[str] | None
    token_id: int | None


_INVALID_API_KEY = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Chave de API inválida.")


def _resolve_api_key_context(api_key: str | None, db: Session) -> ApiKeyContext:
    # Mensagem de erro sempre genérica (não distingue "chave não existe" de "revogada"/"expirada")
    # - evita que alguém tentando adivinhar chaves aprenda algo pelo tipo de resposta.
    if not api_key:
        raise _INVALID_API_KEY
    prefix = api_key[:API_KEY_PREFIX_LENGTH]
    now = datetime.now(timezone.utc)

    token_candidates = db.scalars(
        select(AiApiToken).where(
            AiApiToken.key_prefix == prefix,
            AiApiToken.active.is_(True),
            AiApiToken.revoked_at.is_(None),
        )
    ).all()
    for token in token_candidates:
        if not verify_api_key(api_key, token.key_hash):
            continue
        expires_at = token.expires_at
        # SQLite não preserva tzinfo em `DateTime(timezone=True)` (achado real, mesmo padrão já
        # tratado em operations/queries.py e services/ixc_scheduler.py) - sem isso, comparar contra
        # `now` (aware) levanta TypeError em vez de simplesmente decidir se expirou.
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at is not None and expires_at <= now:
            raise _INVALID_API_KEY
        user = db.get(User, token.user_id)
        if not user or not user.active:
            break
        token.last_used_at = now
        db.commit()
        return ApiKeyContext(user=user, scopes=list(token.scopes or []), token_id=token.id)

    credential_candidates = db.scalars(
        select(ApiKeyCredential).where(
            ApiKeyCredential.key_prefix == prefix,
            ApiKeyCredential.active.is_(True),
            ApiKeyCredential.revoked_at.is_(None),
        )
    ).all()
    for credential in credential_candidates:
        if not verify_api_key(api_key, credential.key_hash):
            continue
        user = db.get(User, credential.user_id)
        if not user or not user.active:
            break
        credential.last_used_at = now
        db.commit()
        return ApiKeyContext(user=user, scopes=None, token_id=None)

    raise _INVALID_API_KEY


def require_api_key_context(
    api_key: str | None = Security(_api_key_header),
    db: Session = Depends(get_db),
) -> ApiKeyContext:
    return _resolve_api_key_context(api_key, db)


def require_api_key_user(
    api_key: str | None = Security(_api_key_header),
    db: Session = Depends(get_db),
) -> User:
    return _resolve_api_key_context(api_key, db).user


def require_ai_permission(permission: str):
    def dependency(user: User = Depends(require_api_key_user)) -> User:
        if permission not in permissions_for_user(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permissão insuficiente.")
        return user

    return dependency


def enforce_token_scope(context: ApiKeyContext, scope: str) -> None:
    """Item 15 do pedido: escopos como `orders.read`/`orders.detail` restringem o que um TOKEN
    (não o usuário) pode fazer, além da política de campos/endpoints já aplicada por
    `ai_governance.gate`. Chave legado (`scopes is None`) nunca é bloqueada aqui."""
    if context.scopes is None:
        return
    if scope not in context.scopes:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Token sem o escopo necessário: '{scope}'.")
