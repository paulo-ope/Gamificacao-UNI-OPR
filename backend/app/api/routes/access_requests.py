from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.security import require_permission
from app.db.session import get_db
from app.models import PortalAccessRequest, User
from app.schemas import (
    PortalAccessRequestApprove,
    PortalAccessRequestCpfLookupOut,
    PortalAccessRequestCpfLookupRequest,
    PortalAccessRequestCreate,
    PortalAccessRequestOut,
    PortalAccessRequestReject,
    PortalAccessRequestSubmitOut,
)
from app.services.ixc_client import get_ixc_client
from app.services.ixc_collaborator_lookup import lookup_own_identity_by_cpf
from app.services.portal_access_requests import approve_access_request, list_access_requests, reject_access_request, submit_access_request

router = APIRouter(prefix="/access-requests", tags=["access-requests"])

# Rota pública (`POST /access-requests`) - mesmo padrão de rate limiting já usado em
# `/invites/accept` (api/routes/invites.py): implementado à parte, não compartilhado, pelo mesmo
# racional já registrado lá (não vale o acoplamento de mexer no rate limiter do login por causa
# disso - ver docs/manual_desenvolvimento_senior.md seção 3).
SUBMIT_WINDOW_MINUTES = 15
SUBMIT_MAX_ATTEMPTS = 10
_submit_attempts: dict[str, list[datetime]] = {}


def _guard_submit_attempts(request: Request) -> None:
    client_host = request.client.host if request.client else "unknown"
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=SUBMIT_WINDOW_MINUTES)
    attempts = [attempt for attempt in _submit_attempts.get(client_host, []) if attempt >= window_start]
    if len(attempts) >= SUBMIT_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Muitas tentativas. Aguarde alguns minutos e tente novamente.")
    attempts.append(now)
    _submit_attempts[client_host] = attempts


# Rota própria pro autoatendimento por CPF (Fase 2D, pedido do usuário em 2026-08-29) - devolve
# nome + telefone parcialmente mascarado pra QUALQUER CPF de dígito verificador válido, então
# precisa de um limite independente do de envio (é mais sensível: revela dado pessoal real de
# funcionário pra quem só acertou um CPF sintaticamente válido, não necessariamente o dono dele).
LOOKUP_WINDOW_MINUTES = 15
LOOKUP_MAX_ATTEMPTS = 10
_lookup_attempts: dict[str, list[datetime]] = {}


def _guard_lookup_attempts(request: Request) -> None:
    client_host = request.client.host if request.client else "unknown"
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=LOOKUP_WINDOW_MINUTES)
    attempts = [attempt for attempt in _lookup_attempts.get(client_host, []) if attempt >= window_start]
    if len(attempts) >= LOOKUP_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Muitas tentativas. Aguarde alguns minutos e tente novamente.")
    attempts.append(now)
    _lookup_attempts[client_host] = attempts


@router.post("/lookup-cpf", response_model=PortalAccessRequestCpfLookupOut)
def lookup_access_request_cpf_route(payload: PortalAccessRequestCpfLookupRequest, request: Request, db: Session = Depends(get_db)):
    """Pública, sem autenticação - o próprio colaborador confirma nome e telefone antes de
    solicitar acesso. Nunca devolve e-mail (sempre digitado por quem solicita) nem dado interno do
    IXC (isso é só pro admin, ver `/invites/lookup-ixc-cpf`)."""
    _guard_lookup_attempts(request)
    return lookup_own_identity_by_cpf(db, get_ixc_client(), payload.cpf)


@router.post("", response_model=PortalAccessRequestSubmitOut, status_code=201)
def submit_access_request_route(payload: PortalAccessRequestCreate, request: Request, db: Session = Depends(get_db)):
    """Pública, sem autenticação - canal formal pra quem não tem conta nem convite pedir acesso
    (Fase 2D). A resposta é sempre a mesma, de propósito (ver PortalAccessRequestSubmitOut) - não
    revela se o CPF/e-mail já existe no sistema."""
    _guard_submit_attempts(request)
    submit_access_request(
        db,
        get_ixc_client(),
        cpf=payload.cpf,
        email=payload.email,
        new_password=payload.new_password,
        confirm_password=payload.confirm_password,
        name=payload.name,
        phone=payload.phone,
    )
    return {"received": True}


@router.get("", response_model=list[PortalAccessRequestOut])
def list_access_requests_route(db: Session = Depends(get_db), user: User = Depends(require_permission("users:manage"))):
    return list_access_requests(db)


def _get_request_or_404(db: Session, request_id: int) -> PortalAccessRequest:
    item = db.get(PortalAccessRequest, request_id)
    if not item:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
    return item


@router.post("/{request_id}/approve", response_model=PortalAccessRequestOut)
def approve_access_request_route(
    request_id: int,
    payload: PortalAccessRequestApprove,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("users:manage")),
):
    """Aprovar cria a conta direto, com a senha que a pessoa já escolheu ao solicitar (2026-08-29) -
    `collaborator_id` é exigido explicitamente no corpo, mesmo quando bate com
    `suggested_collaborator_id`, pra nunca virar vínculo automático."""
    item = _get_request_or_404(db, request_id)
    return approve_access_request(db, user, item, collaborator_id=payload.collaborator_id, decision_reason=payload.decision_reason)


@router.post("/{request_id}/reject", response_model=PortalAccessRequestOut)
def reject_access_request_route(
    request_id: int,
    payload: PortalAccessRequestReject,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("users:manage")),
):
    item = _get_request_or_404(db, request_id)
    return reject_access_request(db, user, item, decision_reason=payload.decision_reason)
