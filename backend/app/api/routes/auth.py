from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, get_current_user, permissions_for_role, verify_password
from app.db.session import get_db
from app.models import User
from app.schemas import LoginRequest, TokenOut, UserOut

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
        "permissions": sorted(permissions_for_role(user.role)),
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
