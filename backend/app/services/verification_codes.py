from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AccountActionToken

# Código de 6 dígitos de uso único, compartilhado por "esqueci minha senha" (`purpose="password_reset"`,
# dono = `user_id`) e pela verificação de e-mail na solicitação de acesso (`purpose="email_verification"`,
# dono = `access_request_id`). Reaproveita `AccountActionToken`: o código é só o "token", guardado como
# HMAC salgado, nunca em claro. 6 dígitos são 1 milhão de combinações, então o que impede força bruta é
# o limite de tentativas por código, não o tamanho dele.
CODE_TTL_MINUTES = 10
MAX_CODE_ATTEMPTS = 5
# Um pedido novo só é aceito depois deste intervalo e no máximo N por hora por dono - impede usar as
# rotas públicas como gerador de spam para a caixa de uma pessoa. Persistido no banco (conta os tokens
# criados), então sobrevive a restart, ao contrário do limite por IP.
RESEND_COOLDOWN_SECONDS = 60
MAX_REQUESTS_PER_HOUR = 5


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _digest(salt: str, email: str, code: str) -> str:
    key = get_settings().auth_secret_key.encode("utf-8")
    return hmac.new(key, f"{salt}:{email}:{code}".encode("utf-8"), hashlib.sha256).hexdigest()


def _store_value(email: str, code: str) -> str:
    salt = secrets.token_hex(8)
    return f"{salt}${_digest(salt, email, code)}"


def _matches(stored: str, email: str, code: str) -> bool:
    try:
        salt, expected = stored.split("$", 1)
    except ValueError:
        return False
    return hmac.compare_digest(_digest(salt, email, code), expected)


def _owner_clauses(purpose: str, user_id: int | None, access_request_id: int | None) -> list:
    if (user_id is None) == (access_request_id is None):
        raise ValueError("Informe exatamente um dono do código: user_id ou access_request_id.")
    clauses = [AccountActionToken.purpose == purpose]
    if user_id is not None:
        clauses.append(AccountActionToken.user_id == user_id)
    else:
        clauses.append(AccountActionToken.access_request_id == access_request_id)
    return clauses


def revoke_pending(db: Session, *, purpose: str, user_id: int | None = None, access_request_id: int | None = None) -> None:
    pending = db.scalars(
        select(AccountActionToken).where(*_owner_clauses(purpose, user_id, access_request_id), AccountActionToken.status == "pending")
    ).all()
    for token in pending:
        token.status = "revoked"


def issue_code(
    db: Session, *, purpose: str, email: str, user_id: int | None = None, access_request_id: int | None = None
) -> tuple[str, datetime] | None:
    """Emite um código novo e invalida os anteriores do mesmo dono. Devolve `(código, expira_em)`, ou
    `None` quando não há nada a enviar (intervalo mínimo entre pedidos ou limite por hora). Quem chama
    responde SEMPRE igual nos dois casos - a diferença nunca chega ao cliente. Não faz commit."""
    clauses = _owner_clauses(purpose, user_id, access_request_id)
    now = datetime.now(timezone.utc)
    last_hour = db.scalar(
        select(func.count()).select_from(AccountActionToken).where(*clauses, AccountActionToken.created_at >= now - timedelta(hours=1))
    )
    if (last_hour or 0) >= MAX_REQUESTS_PER_HOUR:
        return None
    last_created = db.scalar(select(func.max(AccountActionToken.created_at)).where(*clauses))
    if last_created and _aware(last_created) > now - timedelta(seconds=RESEND_COOLDOWN_SECONDS):
        return None

    revoke_pending(db, purpose=purpose, user_id=user_id, access_request_id=access_request_id)
    code = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = now + timedelta(minutes=CODE_TTL_MINUTES)
    db.add(
        AccountActionToken(
            purpose=purpose,
            user_id=user_id,
            access_request_id=access_request_id,
            email=email,
            token_hash=_store_value(email, code),
            status="pending",
            expires_at=expires_at,
        )
    )
    db.flush()
    return code, expires_at


def verify_code(
    db: Session, *, purpose: str, email: str, code: str, user_id: int | None = None, access_request_id: int | None = None
) -> bool:
    """Confere o código mais recente ainda pendente do dono. Código errado conta uma tentativa (e é
    revogado ao atingir o máximo); expirado também deixa de valer. Falhas já fazem commit - o contador
    de tentativas não pode ser desfeito por um rollback do chamador. No sucesso NÃO faz commit: o
    chamador grava a mudança que o código autorizou na mesma transação."""
    # `with_for_update` serializa tentativas concorrentes no mesmo código em PostgreSQL, para que o
    # limite de tentativas não possa ser furado em paralelo (SQLite ignora a cláusula).
    token = db.scalar(
        select(AccountActionToken)
        .where(*_owner_clauses(purpose, user_id, access_request_id), AccountActionToken.status == "pending")
        .order_by(AccountActionToken.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    if not token:
        return False
    now = datetime.now(timezone.utc)
    if _aware(token.expires_at) < now:
        token.status = "expired"
        db.commit()
        return False
    if not _matches(token.token_hash, email, code):
        token.attempts += 1
        if token.attempts >= MAX_CODE_ATTEMPTS:
            token.status = "revoked"
        db.commit()
        return False
    # Revoga os pendentes ANTES de marcar este como aceito: a sessão do app não faz autoflush, então a
    # consulta de `revoke_pending` ainda enxerga este token como pendente e o sobrescreveria como
    # "revoked" se rodasse depois.
    revoke_pending(db, purpose=purpose, user_id=user_id, access_request_id=access_request_id)
    token.status = "accepted"
    token.accepted_at = now
    return True
