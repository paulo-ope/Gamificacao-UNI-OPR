from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Collaborator, PortalAccessRequest, User
from app.services.audit_log import record_audit_log
from app.services.documents import is_valid_cpf, mask_document, normalize_document
from app.services.ixc_client import IxcApiError, IxcClient
from app.services.ixc_collaborator_lookup import find_funcionario_identity_by_cpf, find_local_collaborator


def _serialize_request(item: PortalAccessRequest) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "cpf_masked": mask_document(item.cpf),
        "phone": item.phone,
        "email": item.email,
        "suggested_collaborator_id": item.suggested_collaborator_id,
        "suggested_collaborator_name": item.suggested_collaborator.name if item.suggested_collaborator else None,
        "status": item.status,
        "reviewed_by_user_id": item.reviewed_by_user_id,
        "reviewed_by_name": item.reviewed_by.name if item.reviewed_by else None,
        "reviewed_at": item.reviewed_at,
        "decision_reason": item.decision_reason,
        "created_at": item.created_at,
    }


def list_access_requests(db: Session) -> list[dict[str, Any]]:
    items = db.scalars(select(PortalAccessRequest).order_by(PortalAccessRequest.created_at.desc())).all()
    return [_serialize_request(item) for item in items]


def submit_access_request(
    db: Session,
    client: IxcClient,
    *,
    cpf: str,
    email: str,
    new_password: str,
    confirm_password: str,
    name: str | None = None,
    phone: str | None = None,
) -> None:
    """Fase 2D - registra a solicitação (nunca cria `User`/vínculo). Resposta pública é sempre
    genérica (ver router) - a lógica aqui pode ramificar internamente (CPF já tem solicitação
    pendente, já tem correspondência de colaborador etc.) sem que isso vaze pra fora.

    `email` já chega validado/normalizado pelo schema (domínio corporativo). `name` nunca é
    aceito do cliente quando o CPF é encontrado no IXC - é a confirmação de identidade ("é você?"),
    não pode ser trocado por quem preenche o formulário. `phone` é diferente por pedido explícito
    do usuário em 2026-08-29: a pessoa pode não reconhecer o número que o IXC devolveu (cadastro
    desatualizado) e precisa poder CORRIGIR o telefone que fica salvo - por isso, quando o cliente
    manda um `phone` explícito, ele tem prioridade sobre o do IXC. Sem CPF encontrado (formulário
    manual, resguardo), tanto `name` quanto `phone` vêm do cliente, do jeito que já era antes.

    `new_password`/`confirm_password` (2026-08-29): a pessoa já escolhe a própria senha aqui - só
    o hash é armazenado (`PortalAccessRequest.password_hash`), nunca a senha em claro em nenhum
    lugar (nem auditoria). Se aprovada, a conta é criada direto com essa senha
    (`approve_access_request`), sem convite/link manual."""
    if new_password != confirm_password:
        raise HTTPException(status_code=422, detail="A nova senha e a confirmação não são iguais.")

    normalized_cpf = normalize_document(cpf)
    if not normalized_cpf or not is_valid_cpf(normalized_cpf):
        raise HTTPException(status_code=422, detail="CPF inválido. Confira os números e tente novamente.")

    resolved_name = name.strip() if name else None
    resolved_phone = phone.strip() if phone else None
    phone_source = "manual" if resolved_phone else None
    identity_ixc_employee_id: int | None = None
    try:
        identity = find_funcionario_identity_by_cpf(client, normalized_cpf)
    except IxcApiError:
        # Falha de rede do IXC não pode travar quem já tem os dados preenchidos manualmente (o
        # cadastro segue pro fluxo de revisão do admin do mesmo jeito) - só impede quando a pessoa
        # dependia do IXC preencher nome/telefone por ela.
        identity = None
    if identity:
        resolved_name = identity["name"]
        identity_ixc_employee_id = identity.get("ixc_employee_id")
        if not resolved_phone:
            resolved_phone = identity["phone"]
            phone_source = "ixc" if resolved_phone else None

    if not resolved_name or not resolved_phone:
        raise HTTPException(
            status_code=422,
            detail="Não foi possível confirmar seu nome e telefone automaticamente - informe os dois manualmente.",
        )

    # Correspondência automática - sempre uma SUGESTÃO pro admin revisar depois, nunca um vínculo
    # criado aqui (princípio de segurança da Fase 2, seção 2). Prioridade completa
    # (ixc_employee_id > CPF > nome, `find_local_collaborator`) só quando o nome foi CONFIRMADO
    # pelo IXC - no caminho manual (sem IXC) o nome vem do próprio cliente, sem verificação, então
    # casar por nome arriscaria sugerir o colaborador errado; mantém só CPF, como já era.
    if identity_ixc_employee_id is not None:
        suggested_collaborator, _match_kind = find_local_collaborator(
            db, ixc_employee_id=identity_ixc_employee_id, normalized_cpf=normalized_cpf, name=resolved_name
        )
    else:
        suggested_collaborator = db.scalar(select(Collaborator).where(Collaborator.cpf == normalized_cpf))

    password_hash = hash_password(new_password)

    # Dedup silenciosa contra solicitação pendente com o mesmo CPF - evita inflar a fila de
    # aprovação com o mesmo pedido repetido, sem que a resposta pública diferencie esse caso do
    # de uma solicitação nova (mesma resposta genérica nos dois casos, ver router).
    existing_pending = db.scalar(
        select(PortalAccessRequest).where(PortalAccessRequest.cpf == normalized_cpf, PortalAccessRequest.status == "pending")
    )
    if existing_pending:
        existing_pending.name = resolved_name
        existing_pending.phone = resolved_phone
        existing_pending.email = email
        existing_pending.password_hash = password_hash
        existing_pending.suggested_collaborator_id = suggested_collaborator.id if suggested_collaborator else None
        record_audit_log(
            db,
            None,
            "portal_access_request.resubmitted",
            "portal_access_request",
            existing_pending.id,
            None,
            {"cpf_masked": mask_document(normalized_cpf), "phone_source": phone_source},
        )
        db.commit()
        return

    item = PortalAccessRequest(
        name=resolved_name,
        cpf=normalized_cpf,
        phone=resolved_phone,
        email=email,
        password_hash=password_hash,
        suggested_collaborator_id=suggested_collaborator.id if suggested_collaborator else None,
        status="pending",
    )
    db.add(item)
    db.flush()

    # Auditoria nunca com o CPF completo (seção 9) - mesmo padrão já testado em
    # `test_audit_log_never_stores_full_cpf_or_password` (Fase 1). `user=None`: quem solicita
    # ainda não tem conta nenhuma.
    record_audit_log(
        db,
        None,
        "portal_access_request.created",
        "portal_access_request",
        item.id,
        None,
        {"cpf_masked": mask_document(normalized_cpf), "suggested_collaborator_id": item.suggested_collaborator_id, "phone_source": phone_source},
    )
    db.commit()


def approve_access_request(
    db: Session,
    admin_user: User,
    request: PortalAccessRequest,
    *,
    collaborator_id: int,
    decision_reason: str | None,
) -> dict[str, Any]:
    """Aprovar cria a conta DIRETO (2026-08-29) - com a senha que a própria pessoa já escolheu no
    formulário (`request.password_hash`), não gera mais convite/link manual (Fase 2C continua
    existindo pros outros dois caminhos de convite, só não é mais usada aqui). `collaborator_id` é
    sempre exigido explicitamente no schema, mesmo quando bate com `suggested_collaborator_id` -
    nunca vira vínculo automático (princípio de segurança da Fase 2, seção 2)."""
    if request.status != "pending":
        raise HTTPException(status_code=409, detail="Esta solicitação já foi decidida.")
    if not request.password_hash:
        # Solicitação criada antes de `password_hash` existir (2026-08-29) - nunca cria conta sem
        # senha; pede reenvio em vez de inventar ou reaproveitar senha de outro lugar.
        raise HTTPException(
            status_code=422,
            detail="Esta solicitação foi criada antes da senha ser exigida no formulário. Peça para a pessoa reenviar a solicitação em /solicitar-acesso.",
        )

    collaborator = db.get(Collaborator, collaborator_id)
    if not collaborator:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado.")
    if db.scalar(select(User).where(User.collaborator_id == collaborator_id)):
        raise HTTPException(status_code=409, detail="Este colaborador já está vinculado a um usuário.")
    if db.scalar(select(User).where(User.email == request.email)):
        raise HTTPException(status_code=409, detail="Já existe uma conta com este e-mail.")

    now = datetime.now(timezone.utc)
    user = User(
        name=request.name,
        email=request.email,
        password_hash=request.password_hash,
        role="collaborator",
        active=True,
        collaborator_id=collaborator_id,
        # A pessoa escolheu esta senha ela mesma, no momento da solicitação - não é uma senha
        # temporária de admin, então `must_change_password` NÃO é forçado (mesmo racional de
        # `accept_invite`). `first_access_completed_at` continua None: falta confirmar
        # CPF/telefone/e-mail, responsabilidade da Fase 1 (`portal_first_access_pending`).
        must_change_password=False,
        first_access_completed_at=None,
    )
    db.add(user)
    db.flush()

    request.status = "approved"
    request.reviewed_by_user_id = admin_user.id
    request.reviewed_at = now
    request.decision_reason = decision_reason
    # A conta já foi criada com esta senha - minimiza retenção de hash sem propósito (mesmo
    # racional do `password_hash = None` em `reject_access_request`).
    request.password_hash = None

    record_audit_log(
        db,
        admin_user,
        "portal_access_request.approved",
        "portal_access_request",
        request.id,
        {"status": "pending"},
        {"status": "approved", "collaborator_id": collaborator_id, "user_id": user.id},
    )
    # Entrada própria em "users" pro autor da aprovação manter rastreabilidade de quem criou a
    # conta e quando - nunca com a senha, nem hash (mesmo padrão de `portal_invite.account_created`
    # em `accept_invite`).
    record_audit_log(
        db,
        user,
        "portal_access_request.account_created",
        "users",
        user.id,
        None,
        {"email": request.email, "collaborator_id": collaborator_id, "role": user.role},
    )
    db.commit()
    db.refresh(request)
    return _serialize_request(request)


def reject_access_request(db: Session, admin_user: User, request: PortalAccessRequest, *, decision_reason: str) -> dict[str, Any]:
    if request.status != "pending":
        raise HTTPException(status_code=409, detail="Esta solicitação já foi decidida.")

    request.status = "rejected"
    request.reviewed_by_user_id = admin_user.id
    request.reviewed_at = datetime.now(timezone.utc)
    request.decision_reason = decision_reason
    # Rejeitada não precisa mais da senha que a pessoa escolheu - minimiza retenção de hash sem
    # propósito (mesmo espírito de nunca guardar CPF completo, seção 9).
    request.password_hash = None

    record_audit_log(
        db,
        admin_user,
        "portal_access_request.rejected",
        "portal_access_request",
        request.id,
        {"status": "pending"},
        {"status": "rejected", "decision_reason": decision_reason},
    )
    db.commit()
    db.refresh(request)
    return _serialize_request(request)
