from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.rate_limit import SlidingWindowLimiter
from app.core.security import require_any_permission
from app.db.session import get_db
from app.models import PortalAccessRequest, User
from app.schemas import (
    PortalAccessRequestApprove,
    PortalAccessRequestCpfLookupOut,
    PortalAccessRequestCpfLookupRequest,
    PortalAccessRequestCreate,
    PortalAccessRequestOut,
    PortalAccessRequestReject,
    PortalAccessRequestResendCode,
    PortalAccessRequestSubmitOut,
    PortalAccessRequestVerifyEmail,
    PortalAccessRequestVerifyOut,
)
from app.services.ixc_client import get_ixc_client
from app.services.ixc_collaborator_lookup import lookup_own_identity_by_cpf
from app.services.portal_access_requests import (
    approve_access_request,
    list_access_requests,
    reject_access_request,
    resend_email_verification,
    send_email_verification_code,
    submit_access_request,
    verify_access_request_email,
)

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


# Verificação de e-mail (2026-10-10): limites por IP próprios, além do limite por código (5 tentativas) e
# por solicitação (intervalo e teto por hora, no banco - ver services/verification_codes.py).
_verify_limiter = SlidingWindowLimiter(
    window_minutes=15, max_attempts=15, message="Muitas tentativas. Aguarde alguns minutos e tente novamente."
)
_resend_limiter = SlidingWindowLimiter(
    window_minutes=15, max_attempts=10, message="Muitas tentativas. Aguarde alguns minutos e tente novamente."
)


@router.post("/lookup-cpf", response_model=PortalAccessRequestCpfLookupOut)
def lookup_access_request_cpf_route(payload: PortalAccessRequestCpfLookupRequest, request: Request, db: Session = Depends(get_db)):
    """Pública, sem autenticação - o próprio colaborador confirma nome e telefone antes de
    solicitar acesso. Nunca devolve e-mail (sempre digitado por quem solicita) nem dado interno do
    IXC (isso é só pro admin, ver `/invites/lookup-ixc-cpf`)."""
    _guard_lookup_attempts(request)
    return lookup_own_identity_by_cpf(db, get_ixc_client(), payload.cpf)


@router.post("", response_model=PortalAccessRequestSubmitOut, status_code=201)
def submit_access_request_route(
    payload: PortalAccessRequestCreate, request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    """Pública, sem autenticação - canal formal pra quem não tem conta nem convite pedir acesso
    (Fase 2D). A resposta é sempre a mesma, de propósito (ver PortalAccessRequestSubmitOut) - não
    revela se o CPF/e-mail já existe no sistema. Envia um código de 6 dígitos para o e-mail informado
    (em segundo plano) - o admin só aprova depois que a pessoa confirmá-lo em `/verify-email`."""
    _guard_submit_attempts(request)
    issued = submit_access_request(
        db,
        get_ixc_client(),
        cpf=payload.cpf,
        email=payload.email,
        new_password=payload.new_password,
        confirm_password=payload.confirm_password,
        name=payload.name,
        phone=payload.phone,
    )
    if issued:
        background_tasks.add_task(send_email_verification_code, *issued)
    return {"received": True}


@router.post("/verify-email", response_model=PortalAccessRequestVerifyOut)
def verify_access_request_email_route(payload: PortalAccessRequestVerifyEmail, request: Request, db: Session = Depends(get_db)):
    """Pública. Confirma o código de 6 dígitos enviado ao e-mail da solicitação. Toda falha devolve a mesma
    mensagem (400) - não revela se um CPF tem solicitação."""
    _verify_limiter.check(request)
    verify_access_request_email(db, cpf=payload.cpf, email=payload.email, code=payload.code)
    return {"verified": True}


@router.post("/resend-code", response_model=PortalAccessRequestSubmitOut, status_code=202)
def resend_access_request_code_route(
    payload: PortalAccessRequestResendCode, request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    """Pública. Reenvia o código de verificação. Resposta SEMPRE igual (exista ou não solicitação para o
    CPF/e-mail, ou ainda esteja no intervalo mínimo entre envios)."""
    _resend_limiter.check(request)
    issued = resend_email_verification(db, cpf=payload.cpf, email=payload.email)
    if issued:
        background_tasks.add_task(send_email_verification_code, *issued)
    return {"received": True}


@router.get("", response_model=list[PortalAccessRequestOut])
def list_access_requests_route(db: Session = Depends(get_db), user: User = Depends(require_any_permission("users:manage", "admin:users:read"))):
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
    user: User = Depends(require_any_permission("users:manage", "admin:users:write")),
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
    user: User = Depends(require_any_permission("users:manage", "admin:users:write")),
):
    item = _get_request_or_404(db, request_id)
    return reject_access_request(db, user, item, decision_reason=payload.decision_reason)
