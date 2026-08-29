from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.routes.auth import serialize_user
from app.core.security import create_access_token, require_permission
from app.db.session import get_db
from app.models import AccountActionToken, User
from app.schemas import (
    IxcCpfLookupOut,
    IxcCpfLookupRequest,
    PortalInviteAcceptRequest,
    PortalInviteCreate,
    PortalInviteCreateOut,
    PortalInviteFromIxcRequest,
    PortalInviteOut,
    PortalInviteStatusOut,
    TokenOut,
)
from app.services.ixc_client import get_ixc_client
from app.services.ixc_collaborator_lookup import create_invite_from_ixc, lookup_collaborator_by_cpf
from app.services.portal_invites import accept_invite, create_invite, get_invite_status, list_invites, revoke_invite

router = APIRouter(prefix="/invites", tags=["invites"])

# Rota pública (`/invites/accept`) - mesmo padrão de rate limiting já usado em `/auth/login`
# (api/routes/auth.py), implementado à parte aqui em vez de compartilhado: o risco real já é baixo
# (o token tem 256 bits de entropia, força bruta online é inviável), isso é só defesa em
# profundidade contra abuso/spam - não vale o acoplamento de mexer no rate limiter do login por
# causa disso (ver docs/manual_desenvolvimento_senior.md seção 3, "não fazer refatoração ampla sem
# relação com a tarefa").
ACCEPT_WINDOW_MINUTES = 15
ACCEPT_MAX_ATTEMPTS = 10
_accept_attempts: dict[str, list[datetime]] = {}


def _guard_accept_attempts(request: Request) -> None:
    client_host = request.client.host if request.client else "unknown"
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=ACCEPT_WINDOW_MINUTES)
    attempts = [attempt for attempt in _accept_attempts.get(client_host, []) if attempt >= window_start]
    if len(attempts) >= ACCEPT_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Muitas tentativas. Aguarde alguns minutos e tente novamente.")
    attempts.append(now)
    _accept_attempts[client_host] = attempts


@router.post("", response_model=PortalInviteCreateOut, status_code=201)
def create_invite_route(
    payload: PortalInviteCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("users:manage")),
):
    invite, raw_token = create_invite(db, user, email=payload.email, collaborator_id=payload.collaborator_id, role=payload.role)
    return {**invite, "token": raw_token}


@router.post("/lookup-ixc-cpf", response_model=IxcCpfLookupOut)
def lookup_ixc_cpf_route(
    payload: IxcCpfLookupRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("users:manage")),
):
    """Fase 2C - convite inteligente por CPF integrado ao IXC. Só busca e sugere - nunca cria
    usuário, convite ou vínculo sozinha (ver docs/portal-ciclo-vida-conta-colaborador.md)."""
    match = lookup_collaborator_by_cpf(db, user, get_ixc_client(), payload.cpf)
    return {
        "ixc_employee_id": match.ixc_employee_id,
        "name": match.name,
        "email": match.email,
        "phone": match.phone,
        "cpf_masked": match.cpf_masked,
        "active": match.active,
        "department_id": match.department_id,
        "sector_id": match.sector_id,
        "local_collaborator_id": match.local_collaborator_id,
        "local_collaborator_name": match.local_collaborator_name,
        "local_match_kind": match.local_match_kind,
    }


@router.post("/from-ixc", response_model=PortalInviteCreateOut, status_code=201)
def create_invite_from_ixc_route(
    payload: PortalInviteFromIxcRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("users:manage")),
):
    """Confirma o colaborador encontrado no IXC e gera o convite - `collaborator_id` é sempre
    exigido explicitamente no corpo (nunca aceito por omissão, mesmo quando bate com a sugestão
    automática do lookup)."""
    invite, raw_token = create_invite_from_ixc(
        db, user, get_ixc_client(), cpf=payload.cpf, collaborator_id=payload.collaborator_id, email=payload.email, role=payload.role
    )
    return {**invite, "token": raw_token}


@router.get("", response_model=list[PortalInviteOut])
def list_invites_route(db: Session = Depends(get_db), user: User = Depends(require_permission("users:manage"))):
    return list_invites(db)


@router.post("/{invite_id}/revoke", response_model=PortalInviteOut)
def revoke_invite_route(
    invite_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("users:manage")),
):
    invite = db.get(AccountActionToken, invite_id)
    if not invite or invite.purpose != "invite":
        raise HTTPException(status_code=404, detail="Convite não encontrado.")
    return revoke_invite(db, user, invite)


@router.get("/accept", response_model=PortalInviteStatusOut)
def invite_status_route(token: str, db: Session = Depends(get_db)):
    """Pública, sem autenticação - só confirma se o convite ainda é válido antes de mostrar o
    formulário de senha. Nunca expõe `collaborator_id`, `role` ou qualquer dado interno."""
    return get_invite_status(db, token)


@router.post("/accept", response_model=TokenOut)
def accept_invite_route(payload: PortalInviteAcceptRequest, request: Request, db: Session = Depends(get_db)):
    """Pública, sem autenticação - aceitar o convite É como a conta nasce (Fase 2C). Devolve um
    token de acesso, igual ao login, pra a pessoa já entrar direto no onboarding da Fase 1 sem
    precisar logar de novo com a senha que acabou de escolher."""
    _guard_accept_attempts(request)
    user = accept_invite(db, raw_token=payload.token, new_password=payload.new_password, confirm_password=payload.confirm_password)
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": serialize_user(user)}
