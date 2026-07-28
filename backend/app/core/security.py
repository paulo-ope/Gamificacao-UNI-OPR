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
from app.models import AccessProfile, AccessProfilePermission, User, UserAccessProfile

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "collaborator": {
        "portal:read_self",
        "portal:update_self_profile",
        "portal:read_regional_ranking",
        "portal:simulate_self",
        "portal:read_rules",
    },
    "regional_manager_viewer": {
        "portal:read_self",
        "portal:update_self_profile",
        "portal:read_regional_ranking",
        "portal:simulate_self",
        "portal:read_rules",
        "portal:read_regional_summary",
        "operations:read",
        "operations:views:read_global",
    },
    "viewer": {
        "dashboard:read",
        "audit:read",
        "orders:read",
        "scoring:read",
        "portal:read_self",
        "portal:update_self_profile",
        "portal:read_regional_ranking",
        "portal:simulate_self",
        "portal:read_rules",
        "operations:read",
        "operations:views:read_global",
    },
    "operator": {
        "dashboard:read",
        "audit:read",
        "orders:read",
        "scoring:read",
        "orders:import",
        "portal:read_self",
        "portal:update_self_profile",
        "portal:read_regional_ranking",
        "portal:simulate_self",
        "portal:read_rules",
        "operations:read",
        "operations:manage",
        "operations:views:read_global",
        "operations:sync_ixc",
        "operations:view_order_details",
    },
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
        "portal:read_self",
        "portal:update_self_profile",
        "portal:read_regional_ranking",
        "portal:simulate_self",
        "portal:read_rules",
        "portal:read_regional_summary",
        "portal:read_overview",
        "operations:read",
        "operations:manage",
        "operations:sync_ixc",
        "operations:manage_filters",
        "operations:views:read_global",
        "operations:views:create_global",
        "operations:views:update_global",
        "operations:views:delete_global",
        "operations:manage_team_models",
        "operations:manage_subjects",
        "operations:view_order_details",
        "operations:view_sla",
        "operations:view_calendar",
        "operations:view_backlog",
        "operations:export",
        "admin:users:read",
        "admin:users:write",
        "admin:users:delete",
        "admin:roles:read",
        "admin:roles:write",
        "admin:permissions:read",
        "admin:audit:read",
    },
}

PERMISSION_LABELS: dict[str, str] = {
    "dashboard:read": "Ver dashboard da gamificação",
    "audit:read": "Ver auditoria",
    "orders:read": "Ver O.S. da gamificação",
    "orders:import": "Importar O.S.",
    "scoring:read": "Ver pontuação",
    "scoring:write": "Alterar pontuação",
    "penalties:write": "Configurar penalidades",
    "health_rules:write": "Configurar saúde/regras",
    "settings:write": "Alterar configurações",
    "calculation:run": "Rodar fechamento",
    "users:manage": "Gerenciar usuários legado",
    "portal:read_self": "Portal: ver próprio acesso",
    "portal:update_self_profile": "Portal: atualizar perfil",
    "portal:read_regional_ranking": "Portal: ranking regional",
    "portal:simulate_self": "Portal: simular pontuação",
    "portal:read_rules": "Portal: ver regras",
    "portal:read_regional_summary": "Portal: resumo regional",
    "portal:read_overview": "Portal: visão geral",
    "operations:read": "Operação: acessar módulo",
    "operations:manage": "Operação: administrar módulo",
    "operations:sync_ixc": "Operação: sincronizar IXC",
    "operations:manage_filters": "Operação: gerenciar visões/filtros",
    "operations:views:read_global": "Operação: ver visões globais",
    "operations:views:create_global": "Operação: criar visões globais",
    "operations:views:update_global": "Operação: atualizar visões globais",
    "operations:views:delete_global": "Operação: excluir visões globais",
    "operations:manage_team_models": "Operação: configurar modelos de equipe",
    "operations:manage_subjects": "Operação: configurar assuntos",
    "operations:view_order_details": "Operação: ver detalhes de O.S.",
    "operations:view_sla": "Operação: ver SLA",
    "operations:view_calendar": "Operação: ver calendário",
    "operations:view_backlog": "Operação: ver backlog",
    "operations:export": "Operação: exportar dados",
    "admin:users:read": "Administração: listar usuários",
    "admin:users:write": "Administração: criar/editar usuários",
    "admin:users:delete": "Administração: excluir usuários",
    "admin:roles:read": "Administração: listar perfis",
    "admin:roles:write": "Administração: criar/editar perfis",
    "admin:permissions:read": "Administração: listar permissões",
    "admin:audit:read": "Administração: ver auditoria",
}

PROFILE_LABELS: dict[str, tuple[str, str]] = {
    "collaborator": ("Colaborador Portal", "Acesso próprio ao portal do colaborador."),
    "regional_manager_viewer": ("Gestor Regional Portal", "Acompanha portal e operação das regionais vinculadas."),
    "viewer": ("Leitor Operacional", "Consulta dashboards, auditoria e operação sem alterações críticas."),
    "operator": ("Operador Operacional", "Opera importações e rotinas da operação com acesso gerencial."),
    "admin": ("Admin Ecossistema", "Controle total de módulos, usuários, perfis e configurações."),
}

security = HTTPBearer(auto_error=False)


def permissions_for_role(role: str) -> set[str]:
    return ROLE_PERMISSIONS.get(role, set())


def permissions_for_user(user: User) -> set[str]:
    profile_permissions = {
        permission.permission
        for profile in getattr(user, "access_profiles", []) or []
        if profile.active
        for permission in profile.permissions
    }
    return profile_permissions or permissions_for_role(user.role)


def is_admin_user(user: User | None) -> bool:
    return bool(user and ("admin:users:write" in permissions_for_user(user) or user.role == "admin"))


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
        if permission not in permissions_for_user(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permissão insuficiente.")
        return user

    return dependency


def ensure_access_profiles(db: Session) -> None:
    for legacy_role, permissions in ROLE_PERMISSIONS.items():
        name, description = PROFILE_LABELS[legacy_role]
        profile = db.scalar(select(AccessProfile).where(AccessProfile.legacy_role == legacy_role))
        if not profile:
            profile = AccessProfile(
                name=name,
                description=description,
                legacy_role=legacy_role,
                active=True,
                is_system=True,
            )
            db.add(profile)
            db.flush()
        existing = {item.permission for item in profile.permissions}
        for permission in permissions - existing:
            db.add(AccessProfilePermission(profile_id=profile.id, permission=permission))

    db.flush()
    for user in db.scalars(select(User)).all():
        if user.access_profiles:
            continue
        profile = db.scalar(select(AccessProfile).where(AccessProfile.legacy_role == user.role))
        if profile:
            db.add(UserAccessProfile(user_id=user.id, profile_id=profile.id))
    db.commit()


def ensure_initial_admin(db: Session) -> None:
    settings = get_settings()
    email = settings.initial_admin_email.strip().lower()
    if not email:
        return
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        ensure_access_profiles(db)
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
    ensure_access_profiles(db)
