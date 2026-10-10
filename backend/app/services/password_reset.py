from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import User
from app.services.audit_log import record_audit_log
from app.services.email_sender import send_email
from app.services.email_templates import build_password_reset_code_email
from app.services.verification_codes import (  # noqa: F401 - constantes reexportadas (testes e rotas)
    CODE_TTL_MINUTES,
    MAX_CODE_ATTEMPTS,
    MAX_REQUESTS_PER_HOUR,
    RESEND_COOLDOWN_SECONDS,
    issue_code,
    verify_code,
)

# Esqueci minha senha por código de 6 dígitos enviado por e-mail (evolução da Fase 2E, ver
# docs/portal-ciclo-vida-conta-colaborador.md seção 7). O mecanismo do código (emissão, limites,
# tentativas) é compartilhado com a verificação de e-mail da solicitação de acesso - ver
# `services/verification_codes.py`.
PURPOSE = "password_reset"

INVALID_CODE_MESSAGE = "Código inválido ou expirado. Confira os 6 dígitos ou peça um código novo."


def normalize_email(email: str) -> str:
    return email.strip().lower()


def request_password_reset(db: Session, email: str) -> tuple[User, str] | None:
    """Emite um código novo para o usuário ativo com este e-mail. Devolve `(usuário, código)` para
    quem chamou enviar o e-mail, ou `None` quando não há nada a enviar (e-mail desconhecido,
    conta inativa, pedido repetido cedo demais ou limite por hora atingido). Quem chama responde
    SEMPRE igual nos dois casos - a diferença nunca chega ao cliente (sem enumeração de contas)."""
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if not user or not user.active:
        return None

    issued = issue_code(db, purpose=PURPOSE, email=user.email, user_id=user.id)
    if not issued:
        return None
    code, expires_at = issued
    # Auditoria nunca inclui o código, nem o hash dele.
    record_audit_log(db, user, "password_reset.requested", "users", user.id, None, {"expires_at": expires_at.isoformat()})
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

    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if not user or not user.active or not verify_code(db, purpose=PURPOSE, email=user.email, code=code, user_id=user.id):
        raise HTTPException(status_code=400, detail=INVALID_CODE_MESSAGE)

    now = datetime.now(timezone.utc)
    previous_changed_at = user.password_changed_at
    user.password_hash = hash_password(new_password)
    user.password_changed_at = now
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
