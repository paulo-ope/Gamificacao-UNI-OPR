from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models import User

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "viewer": {"dashboard:read", "audit:read", "orders:read", "scoring:read"},
    "operator": {"dashboard:read", "audit:read", "orders:read", "scoring:read", "orders:import"},
    "admin": {
        "dashboard:read",
        "audit:read",
        "orders:read",
        "orders:import",
        "scoring:read",
        "scoring:write",
        "penalties:write",
        "health_rules:write",
        "settings:write",
        "calculation:run",
        "users:manage",
    },
}

security = HTTPBearer(auto_error=False)


def permissions_for_role(role: str) -> set[str]:
    return ROLE_PERMISSIONS.get(role, set())


def is_admin_user(user: User | None) -> bool:
    return bool(user and user.role == "admin")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 260_000)
    return f"pbkdf2_sha256${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, salt_b64, digest_b64 = password_hash.split("$", 2)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(digest_b64.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 260_000)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def create_access_token(user: User) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.auth_token_expire_minutes)).timestamp()),
    }
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = ".".join(
        [
            _b64url(json.dumps(header, separators=(",", ":")).encode()),
            _b64url(json.dumps(payload, separators=(",", ":")).encode()),
        ]
    )
    signature = hmac.new(settings.auth_secret_key.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(signature)}"


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    try:
        header_b64, payload_b64, signature_b64 = token.split(".", 2)
        signing_input = f"{header_b64}.{payload_b64}"
        expected = hmac.new(settings.auth_secret_key.encode(), signing_input.encode(), hashlib.sha256).digest()
        signature = _b64url_decode(signature_b64)
        if not hmac.compare_digest(signature, expected):
            raise ValueError("bad signature")
        payload = json.loads(_b64url_decode(payload_b64))
        if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
            raise ValueError("expired")
        return payload
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido ou expirado.") from exc


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Session = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticação obrigatória.")
    payload = decode_access_token(credentials.credentials)
    user = db.get(User, int(payload.get("sub") or 0))
    if not user or not user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário inativo ou não encontrado.")
    return user


def require_permission(permission: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if permission not in permissions_for_role(user.role):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permissão insuficiente.")
        return user

    return dependency


def ensure_initial_admin(db: Session) -> None:
    settings = get_settings()
    email = settings.initial_admin_email.strip().lower()
    if not email:
        return
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        return
    db.add(
        User(
            name=settings.initial_admin_name,
            email=email,
            password_hash=hash_password(settings.initial_admin_password),
            role="admin",
            active=True,
        )
    )
    db.commit()
