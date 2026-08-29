from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import generate_temporary_password, hash_password, verify_password
from app.models import User
from app.services.audit_log import record_audit_log


def change_own_password(
    db: Session,
    user: User,
    *,
    current_password: str,
    new_password: str,
    confirm_password: str,
) -> None:
    """Troca de senha voluntária pelo próprio usuário autenticado (Fase 2A, ver
    docs/portal-ciclo-vida-conta-colaborador.md seção 3). Vale para qualquer usuário do
    ecossistema (colaborador, admin, operador...), não só quem usa o Portal - por isso não mexe em
    `must_change_password` nem `first_access_completed_at`, que são só da Fase 1 (primeiro acesso
    obrigatório do colaborador): essa troca é uma decisão voluntária do usuário, não uma
    confirmação de identidade."""
    if not verify_password(current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Senha atual incorreta.")
    if new_password != confirm_password:
        raise HTTPException(status_code=422, detail="A nova senha e a confirmação não são iguais.")
    if new_password == current_password:
        raise HTTPException(status_code=422, detail="A nova senha precisa ser diferente da senha atual.")

    previous_changed_at = user.password_changed_at
    now = datetime.now(timezone.utc)
    user.password_hash = hash_password(new_password)
    user.password_changed_at = now

    # Auditoria sem a senha em nenhuma forma - nem hash, nem tamanho, nem indicação de que mudou -
    # mesmo padrão já usado em `complete_first_access` (Fase 1).
    record_audit_log(
        db,
        user,
        "change_own_password",
        "users",
        user.id,
        {"password_changed_at": previous_changed_at.isoformat() if previous_changed_at else None},
        {"password_changed_at": now.isoformat()},
    )
    db.commit()
    db.refresh(user)


def admin_force_password_reset(db: Session, admin_user: User, target_user: User) -> str:
    """Reset administrativo de senha (Fase 2B, ver
    docs/portal-ciclo-vida-conta-colaborador.md seção 4) - gera uma senha temporária aleatória
    (nunca escolhida ou digitada pelo admin) e força `must_change_password=True`, então a pessoa
    é obrigada a trocar essa senha temporária no próximo login. Retorna a senha em texto puro só
    para esta chamada devolver ao admin uma única vez - não é armazenada em nenhum outro lugar."""
    temporary_password = generate_temporary_password()
    now = datetime.now(timezone.utc)
    previous_must_change = target_user.must_change_password
    target_user.password_hash = hash_password(temporary_password)
    target_user.password_changed_at = now
    target_user.must_change_password = True

    # Auditoria nunca inclui a senha temporária, nem hash, nem tamanho - só o fato de que um reset
    # administrativo aconteceu, quando e sobre quem, igual ao padrão de `change_own_password`.
    record_audit_log(
        db,
        admin_user,
        "user.password_reset_forced",
        "users",
        target_user.id,
        {"must_change_password": previous_must_change},
        {"must_change_password": True, "password_changed_at": now.isoformat()},
    )
    db.commit()
    db.refresh(target_user)
    return temporary_password


def admin_force_first_access(db: Session, admin_user: User, target_user: User) -> None:
    """Reabre o primeiro acesso completo (Fase 2B) - zera `first_access_completed_at` e força
    `must_change_password=True`, colocando a conta exatamente no mesmo estado "pendente" de um
    colaborador recém-criado (`create_user`, api/routes/users.py): a pessoa precisa reconfirmar
    CPF/telefone/e-mail e escolher uma senha nova, não só trocar a senha. Só se aplica a quem
    representa um colaborador (`collaborator_id` definido) - mesma regra de
    `portal_first_access_pending` em core/security.py."""
    if target_user.collaborator_id is None:
        raise HTTPException(
            status_code=422,
            detail="Este usuário não está vinculado a um colaborador - o primeiro acesso não se aplica a ele.",
        )

    previous_first_access = target_user.first_access_completed_at
    previous_must_change = target_user.must_change_password
    target_user.first_access_completed_at = None
    target_user.must_change_password = True

    record_audit_log(
        db,
        admin_user,
        "user.first_access_reset",
        "users",
        target_user.id,
        {
            "first_access_completed_at": previous_first_access.isoformat() if previous_first_access else None,
            "must_change_password": previous_must_change,
        },
        {"first_access_completed_at": None, "must_change_password": True},
    )
    db.commit()
    db.refresh(target_user)
