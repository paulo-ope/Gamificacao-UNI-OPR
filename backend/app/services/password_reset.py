from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.models import AccountActionToken, User
from app.services.audit_log import record_audit_log
from app.services.email_sender import send_email
from app.services.email_templates import build_password_reset_code_email

# Esqueci minha senha por código de 6 dígitos enviado por e-mail (evolução da Fase 2E, ver
# docs/portal-ciclo-vida-conta-colaborador.md seção 7). Reaproveita `AccountActionToken`
# (`purpose="password_reset"`): o código é só o "token", guardado como HMAC salgado, nunca em claro.
PURPOSE = "password_reset"
CODE_TTL_MINUTES = 10
MAX_CODE_ATTEMPTS = 5
# Um pedido novo só é aceito depois deste intervalo e no máximo N por hora por e-mail - impede usar a
# rota como gerador de spam para a caixa de uma pessoa. Persistido no banco (conta os tokens criados),
# então sobrevive a restart, ao contrário do limite por IP.
RESEND_COOLDOWN_SECONDS = 60
MAX_REQUESTS_PER_HOUR = 5

INVALID_CODE_MESSAGE = "Código inválido ou expirado. Confira os 6 dígitos ou peça um código novo."


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


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _revoke_pending(db: Session, user_id: int) -> None:
    pending = db.scalars(
        select(AccountActionToken).where(
            AccountActionToken.purpose == PURPOSE,
            AccountActionToken.user_id == user_id,
            AccountActionToken.status == "pending",
        )
    ).all()
    for token in pending:
        token.status = "revoked"


def request_password_reset(db: Session, email: str) -> tuple[User, str] | None:
    """Emite um código novo para o usuário ativo com este e-mail. Devolve `(usuário, código)` para
    quem chamou enviar o e-mail, ou `None` quando não há nada a enviar (e-mail desconhecido,
    conta inativa, pedido repetido cedo demais ou limite por hora atingido). Quem chama responde
    SEMPRE igual nos dois casos - a diferença nunca chega ao cliente (sem enumeração de contas)."""
    normalized = normalize_email(email)
    user = db.scalar(select(User).where(User.email == normalized))
    if not user or not user.active:
        return None

    now = datetime.now(timezone.utc)
    last_hour = db.scalar(
        select(func.count())
        .select_from(AccountActionToken)
        .where(
            AccountActionToken.purpose == PURPOSE,
            AccountActionToken.user_id == user.id,
            AccountActionToken.created_at >= now - timedelta(hours=1),
        )
    )
    if (last_hour or 0) >= MAX_REQUESTS_PER_HOUR:
        return None
    last_created = db.scalar(
        select(func.max(AccountActionToken.created_at)).where(
            AccountActionToken.purpose == PURPOSE, AccountActionToken.user_id == user.id
        )
    )
    if last_created and _aware(last_created) > now - timedelta(seconds=RESEND_COOLDOWN_SECONDS):
        return None

    _revoke_pending(db, user.id)
    code = f"{secrets.randbelow(1_000_000):06d}"
    token = AccountActionToken(
        purpose=PURPOSE,
        user_id=user.id,
        email=user.email,
        token_hash=_store_value(user.email, code),
        status="pending",
        expires_at=now + timedelta(minutes=CODE_TTL_MINUTES),
    )
    db.add(token)
    db.flush()
    # Auditoria nunca inclui o código, nem o hash dele.
    record_audit_log(
        db, user, "password_reset.requested", "users", user.id, None, {"expires_at": token.expires_at.isoformat()}
    )
    db.commit()
    return user, code


def send_password_reset_code(user_name: str, email: str, code: str) -> None:
    """Tarefa de segundo plano: roda depois da resposta HTTP, então o tempo de resposta não
    denuncia se o e-mail existe. Falha de envio só vira log (ver `send_email`)."""
    send_email(build_password_reset_code_email(to=email, name=user_name, code=code, ttl_minutes=CODE_TTL_MINUTES))


def confirm_password_reset(db: Session, *, email: str, code: str, new_password: str, confirm_password: str) -> None:
    """Valida o código e define a senha nova. Qualquer falha de código (e-mail desconhecido, sem
    pedido, expirado, errado, esgotado) devolve a MESMA mensagem - não revela se a conta existe.
    Não mexe em `must_change_password`/`first_access_completed_at`: é recuperação de senha, não
    reconfirmação de identidade (doc da Fase 2, seção 7)."""
    if new_password != confirm_password:
        raise HTTPException(status_code=422, detail="A nova senha e a confirmação não são iguais.")

    normalized = normalize_email(email)
    user = db.scalar(select(User).where(User.email == normalized))
    token = None
    if user and user.active:
        # `with_for_update` serializa tentativas concorrentes no mesmo código em PostgreSQL, para
        # que o limite de tentativas não possa ser furado em paralelo (SQLite ignora a cláusula).
        token = db.scalar(
            select(AccountActionToken)
            .where(
                AccountActionToken.purpose == PURPOSE,
                AccountActionToken.user_id == user.id,
                AccountActionToken.status == "pending",
            )
            .order_by(AccountActionToken.created_at.desc())
            .limit(1)
            .with_for_update()
        )
    now = datetime.now(timezone.utc)
    if not user or not token or _aware(token.expires_at) < now:
        if token:
            token.status = "expired"
            db.commit()
        raise HTTPException(status_code=400, detail=INVALID_CODE_MESSAGE)

    if not _matches(token.token_hash, user.email, code):
        token.attempts += 1
        if token.attempts >= MAX_CODE_ATTEMPTS:
            token.status = "revoked"
        db.commit()
        raise HTTPException(status_code=400, detail=INVALID_CODE_MESSAGE)

    previous_changed_at = user.password_changed_at
    user.password_hash = hash_password(new_password)
    user.password_changed_at = now
    token.status = "accepted"
    token.accepted_at = now
    _revoke_pending(db, user.id)
    # Auditoria sem a senha em nenhuma forma e sem o código.
    record_audit_log(
        db,
        user,
        "password_reset.completed",
        "users",
        user.id,
        {"password_changed_at": previous_changed_at.isoformat() if previous_changed_at else None},
        {"password_changed_at": now.isoformat()},
    )
    db.commit()
