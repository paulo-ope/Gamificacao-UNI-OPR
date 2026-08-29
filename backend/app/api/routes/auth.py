from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, get_current_user, permissions_for_user, portal_first_access_pending, verify_password
from app.db.session import get_db
from app.models import User
from app.schemas import ChangePasswordRequest, LoginRequest, TokenOut, UserOut
from app.services.account_security import change_own_password
from app.services.regional import effective_managed_regionals

router = APIRouter(prefix="/auth", tags=["auth"])

LOGIN_WINDOW_MINUTES = 15
LOGIN_MAX_ATTEMPTS = 5
_login_attempts: dict[str, list[datetime]] = {}


def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "active": user.active,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "permissions": sorted(permissions_for_user(user)),
        "access_profile_ids": [profile.id for profile in user.access_profiles if profile.active],
        "access_profile_names": [profile.name for profile in user.access_profiles if profile.active],
        "collaborator_id": user.collaborator_id,
        "collaborator_name": user.collaborator.name if user.collaborator else None,
        "managed_regional": user.managed_regional,
        "managed_regionals": effective_managed_regionals(user.managed_regional, user.managed_regionals),
        # Único sinal que o frontend precisa pra decidir "mostrar o portal ou o onboarding" - a
        # regra em si (quem precisa, por quê) mora só em `portal_first_access_pending`; o frontend
        # não recalcula nada, só lê este booleano (norma de qualidade de dados, seção 2).
        "portal_first_access_required": portal_first_access_pending(user),
    }


def _attempt_key(request: Request, email: str) -> str:
    client_host = request.client.host if request.client else "unknown"
    return f"{client_host}:{email.strip().lower()}"


def _recent_attempts(key: str) -> list[datetime]:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=LOGIN_WINDOW_MINUTES)
    attempts = [attempt for attempt in _login_attempts.get(key, []) if attempt >= window_start]
    _login_attempts[key] = attempts
    return attempts


def _guard_login_attempts(request: Request, email: str) -> str:
    key = _attempt_key(request, email)
    if len(_recent_attempts(key)) >= LOGIN_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Muitas tentativas de login. Aguarde alguns minutos e tente novamente.")
    return key


def _register_login_failure(key: str) -> None:
    attempts = _recent_attempts(key)
    attempts.append(datetime.now(timezone.utc))
    _login_attempts[key] = attempts


def _clear_login_attempts(key: str) -> None:
    _login_attempts.pop(key, None)


@router.post("/login", response_model=TokenOut)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    attempt_key = _guard_login_attempts(request, payload.email)
    user = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
    if not user or not user.active or not verify_password(payload.password, user.password_hash):
        _register_login_failure(attempt_key)
        raise HTTPException(status_code=401, detail="Email ou senha inválidos.")
    _clear_login_attempts(attempt_key)
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": serialize_user(user)}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return serialize_user(user)


@router.post("/change-password", response_model=UserOut)
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Troca de senha voluntária (Fase 2A) - só exige autenticação, não `require_portal_access`
    nem nenhuma permissão de módulo: vale para qualquer usuário do ecossistema, não só quem tem
    `collaborator_id`, então não faz sentido gatear atrás de uma permissão de portal."""
    change_own_password(
        db,
        user,
        current_password=payload.current_password,
        new_password=payload.new_password,
        confirm_password=payload.confirm_password,
    )
    return serialize_user(user)
