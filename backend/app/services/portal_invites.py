from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models import AccountActionToken, Collaborator, User
from app.services.audit_log import record_audit_log

# Fase 2C, ver docs/portal-ciclo-vida-conta-colaborador.md seção 5 ("Expiração curta (sugestão: 72
# horas, configurável)") - constante de código em vez de parâmetro por requisição: nenhum caso de
# uso pediu prazo variável, e um valor fixo evita um admin criar um convite com validade
# acidentalmente longa demais.
INVITE_EXPIRES_HOURS = 72


def _aware(value: datetime) -> datetime:
    """SQLite (usado nos testes) não preserva `tzinfo` em `DateTime(timezone=True)` na leitura -
    todo datetime desta tabela é gravado em UTC por convenção, então é seguro completar o que
    faltar. Mesmo padrão já usado em outros módulos (ex.: `modules/intelligence/scheduler.py`,
    `modules/operations/login_search.py`)."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _display_status(token: AccountActionToken, *, now: datetime) -> str:
    """`status` só muda de coluna em ações explícitas (criado/aceito/revogado) - expiração é
    sempre CALCULADA, nunca gravada por uma leitura (uma consulta GET não deveria ter efeito
    colateral). Isso é o que a listagem e a validação de aceite mostram como status real."""
    if token.status == "pending" and _aware(token.expires_at) < now:
        return "expired"
    return token.status


def _serialize_invite(token: AccountActionToken, *, now: datetime) -> dict[str, Any]:
    return {
        "id": token.id,
        "email": token.email,
        "collaborator_id": token.collaborator_id,
        "collaborator_name": token.collaborator.name if token.collaborator else None,
        "role": token.role,
        "status": _display_status(token, now=now),
        "created_by_user_id": token.created_by_user_id,
        "created_by_name": token.created_by.name if token.created_by else None,
        "expires_at": token.expires_at,
        "accepted_at": token.accepted_at,
        "created_at": token.created_at,
    }


def list_invites(db: Session) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    tokens = db.scalars(
        select(AccountActionToken).where(AccountActionToken.purpose == "invite").order_by(AccountActionToken.created_at.desc())
    ).all()
    return [_serialize_invite(token, now=now) for token in tokens]


def create_invite(db: Session, admin_user: User, *, email: str, collaborator_id: int, role: str) -> tuple[dict[str, Any], str]:
    """Cria um convite de colaborador (Fase 2C). O vínculo `collaborator_id` é fixado AQUI, pelo
    admin - nunca pela pessoa convidada (princípio de segurança da Fase 2, seção 2 do documento).
    Retorna o convite serializado e o token em CLARO, que só existe nesta chamada - a partir daqui
    só o hash é persistido."""
    normalized_email = email.strip().lower()
    if not normalized_email or "@" not in normalized_email:
        raise HTTPException(status_code=422, detail="Informe um e-mail válido para o convite.")

    collaborator = db.get(Collaborator, collaborator_id)
    if not collaborator:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado.")
    if db.scalar(select(User).where(User.collaborator_id == collaborator_id)):
        raise HTTPException(status_code=409, detail="Este colaborador já está vinculado a um usuário.")

    now = datetime.now(timezone.utc)
    pending_conflict = db.scalar(
        select(AccountActionToken).where(
            AccountActionToken.purpose == "invite",
            AccountActionToken.status == "pending",
            AccountActionToken.expires_at >= now,
            (AccountActionToken.collaborator_id == collaborator_id) | (AccountActionToken.email == normalized_email),
        )
    )
    if pending_conflict:
        raise HTTPException(status_code=409, detail="Já existe um convite pendente para este colaborador ou e-mail. Revogue-o antes de criar outro.")

    raw_token = secrets.token_urlsafe(32)
    invite = AccountActionToken(
        purpose="invite",
        email=normalized_email,
        collaborator_id=collaborator_id,
        role=role,
        token_hash=hash_password(raw_token),
        status="pending",
        created_by_user_id=admin_user.id,
        expires_at=now + timedelta(hours=INVITE_EXPIRES_HOURS),
    )
    db.add(invite)
    db.flush()

    # Auditoria nunca inclui o token, nem em hash - antes/depois descrevem só o que um admin
    # revisando o log precisa saber: pra quem, qual vínculo, quando expira.
    record_audit_log(
        db,
        admin_user,
        "portal_invite.created",
        "portal_invite",
        invite.id,
        None,
        {"email": normalized_email, "collaborator_id": collaborator_id, "role": role, "expires_at": invite.expires_at.isoformat()},
    )
    db.commit()
    db.refresh(invite)
    return _serialize_invite(invite, now=now), raw_token


def revoke_invite(db: Session, admin_user: User, invite: AccountActionToken) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    if _display_status(invite, now=now) != "pending":
        raise HTTPException(status_code=409, detail="Só é possível revogar um convite pendente.")

    invite.status = "revoked"
    record_audit_log(db, admin_user, "portal_invite.revoked", "portal_invite", invite.id, {"status": "pending"}, {"status": "revoked"})
    db.commit()
    db.refresh(invite)
    return _serialize_invite(invite, now=now)


def _find_pending_invite_by_token(db: Session, raw_token: str) -> AccountActionToken | None:
    """Não dá pra indexar/buscar por igualdade de hash sem recalcular com o mesmo salt de cada
    linha (o hash de senha usa salt aleatório por design - `verify_password` de um por um é a
    forma correta de comparar). O volume de convites pendentes é pequeno o bastante pra isso não
    ser um problema de desempenho (ver docs/manual_desenvolvimento_senior.md seção 5.3 - medir
    antes de otimizar; não há indício de que este volume algum dia justifique outra estratégia)."""
    now = datetime.now(timezone.utc)
    candidates = db.scalars(
        select(AccountActionToken).where(AccountActionToken.purpose == "invite", AccountActionToken.status == "pending")
    ).all()
    for candidate in candidates:
        if verify_password(raw_token, candidate.token_hash):
            return candidate if _aware(candidate.expires_at) >= now else None
    return None


def get_invite_status(db: Session, raw_token: str) -> dict[str, Any]:
    invite = _find_pending_invite_by_token(db, raw_token)
    if not invite:
        return {"valid": False, "reason": "Convite inválido, expirado ou já utilizado."}
    return {"valid": True, "email": invite.email, "collaborator_name": invite.collaborator.name if invite.collaborator else None}


def accept_invite(db: Session, *, raw_token: str, new_password: str, confirm_password: str) -> User:
    """Aceita o convite e cria a conta (Fase 2C). Só resolve a senha inicial - CPF/telefone/e-mail
    continuam sendo confirmados depois, pelo onboarding já existente da Fase 1
    (`first_access_completed_at` fica `None` de propósito, então `portal_first_access_pending`
    continua exigindo esse passo). Decisão registrada explicitamente aqui porque o documento de
    planejamento (seção 5) pedia isso: reaproveitar a Fase 1 em vez de duplicar a coleta de
    CPF/contato dentro do fluxo de convite."""
    if new_password != confirm_password:
        raise HTTPException(status_code=422, detail="A nova senha e a confirmação não são iguais.")

    invite = _find_pending_invite_by_token(db, raw_token)
    if not invite:
        raise HTTPException(status_code=409, detail="Convite inválido, expirado ou já utilizado.")

    collaborator = db.get(Collaborator, invite.collaborator_id)
    if not collaborator:
        raise HTTPException(status_code=404, detail="Colaborador do convite não foi encontrado.")
    if db.scalar(select(User).where(User.collaborator_id == invite.collaborator_id)):
        raise HTTPException(status_code=409, detail="Este colaborador já está vinculado a um usuário.")
    if db.scalar(select(User).where(User.email == invite.email)):
        raise HTTPException(status_code=409, detail="Já existe uma conta com este e-mail.")

    now = datetime.now(timezone.utc)
    user = User(
        name=collaborator.name,
        email=invite.email,
        password_hash=hash_password(new_password),
        role=invite.role or "collaborator",
        active=True,
        collaborator_id=invite.collaborator_id,
        # A pessoa escolheu esta senha agora mesmo - não é uma senha temporária de admin, então
        # `must_change_password` NÃO é forçado (compare com `create_user`, que força porque lá é
        # o ADMIN quem escolhe a senha inicial). `first_access_completed_at` continua None de
        # propósito: falta confirmar CPF/telefone/e-mail, que é responsabilidade da Fase 1.
        must_change_password=False,
        first_access_completed_at=None,
    )
    db.add(user)
    db.flush()

    invite.status = "accepted"
    invite.accepted_at = now
    invite.user_id = user.id

    record_audit_log(db, user, "portal_invite.accepted", "portal_invite", invite.id, {"status": "pending"}, {"status": "accepted", "user_id": user.id})
    # Entrada própria em "users" pro autor do convite manter rastreabilidade de quem criou a conta
    # e quando - nunca com a senha, nem hash (diferente do `create_user` existente, que loga um
    # snapshot completo do usuário; aqui optamos por um antes/depois explícito e seguro, no mesmo
    # padrão já usado em `complete_first_access`/`change_own_password`).
    record_audit_log(db, user, "portal_invite.account_created", "users", user.id, None, {"email": invite.email, "collaborator_id": invite.collaborator_id, "role": user.role})
    db.commit()
    db.refresh(user)
    return user
