from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Collaborator, User
from app.services.audit_log import record_audit_log
from app.services.documents import is_valid_cpf, mask_document, normalize_document


def _own_pending_collaborator(db: Session, user: User) -> Collaborator:
    """Mesma checagem de posse que `portal._own_collaborator` (vínculo direto via
    `users.collaborator_id`, colaborador ativo e cadastrado) - garante que um usuário só conclui o
    PRÓPRIO primeiro acesso, nunca o de outro colaborador."""
    if user.collaborator_id is None:
        raise HTTPException(status_code=403, detail="Seu usuário não está vinculado a um colaborador.")
    collaborator = db.get(Collaborator, user.collaborator_id)
    if not collaborator or not collaborator.active or not collaborator.is_registered:
        raise HTTPException(status_code=404, detail="Cadastro de colaborador não está disponível para o primeiro acesso.")
    return collaborator


def build_first_access_status(db: Session, user: User) -> dict[str, Any]:
    if user.collaborator_id is None:
        return {"required": False, "phone": None, "email": None, "has_cpf": False, "cpf_masked": None}
    collaborator = _own_pending_collaborator(db, user)
    return {
        "required": user.must_change_password or user.first_access_completed_at is None,
        "phone": collaborator.phone,
        "email": collaborator.email,
        "has_cpf": collaborator.cpf is not None,
        "cpf_masked": mask_document(collaborator.cpf),
    }


def complete_first_access(
    db: Session,
    user: User,
    *,
    cpf: str,
    phone: str,
    email: str,
    new_password: str,
    confirm_password: str,
) -> dict[str, Any]:
    """Valida e grava o primeiro acesso. Levanta `HTTPException` (422/409) em qualquer falha de
    validação - nenhuma escrita parcial acontece antes de todas as checagens passarem, porque só
    fazemos `db.add`/mutação de atributo depois da última validação, e só commitamos no fim."""
    collaborator = _own_pending_collaborator(db, user)
    had_cpf_before = collaborator.cpf is not None

    if new_password != confirm_password:
        raise HTTPException(status_code=422, detail="A senha e a confirmação não são iguais.")

    normalized_cpf = normalize_document(cpf)
    if not normalized_cpf or not is_valid_cpf(normalized_cpf):
        raise HTTPException(status_code=422, detail="CPF inválido. Confira os números e tente novamente.")
    if collaborator.cpf:
        # Colaborador já tem CPF cadastrado (veio do RH/importação) - o primeiro acesso CONFIRMA,
        # nunca sobrescreve. Se o número digitado não bate, é sinal de erro de digitação ou de
        # tentativa de confirmar o primeiro acesso de outra pessoa - qualquer um dos dois casos
        # deve parar aqui, não seguir com um CPF que pode estar errado.
        if normalize_document(collaborator.cpf) != normalized_cpf:
            raise HTTPException(status_code=409, detail="O CPF informado não confere com o cadastro existente.")
    else:
        collaborator.cpf = normalized_cpf

    phone_value = phone.strip()
    email_value = email.strip()
    if not phone_value:
        raise HTTPException(status_code=422, detail="Informe um telefone de contato.")
    if "@" not in email_value:
        raise HTTPException(status_code=422, detail="Informe um e-mail de contato válido.")
    collaborator.phone = phone_value
    collaborator.email = email_value

    now = datetime.now(timezone.utc)
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    user.first_access_completed_at = now
    user.password_changed_at = now

    # Auditoria sem CPF completo (só mascarado) e sem senha em nenhuma forma - nem hash, nem
    # tamanho, nem indicação de que mudou. `before`/`after` descrevem só o que um administrador
    # revisando o log precisa saber: que o onboarding aconteceu e quando.
    record_audit_log(
        db,
        user,
        "complete_first_access",
        "users",
        user.id,
        {"first_access_completed_at": None, "had_cpf": had_cpf_before},
        {"first_access_completed_at": now.isoformat(), "cpf_masked": mask_document(collaborator.cpf), "phone": phone_value, "email": email_value},
    )
    db.commit()
    db.refresh(user)
    return {"success": True}
