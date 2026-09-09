"""Permissão concedida ou negada diretamente numa pessoa, por cima do que o perfil dela dá.

Existe para o caso em que dar (ou tirar) UMA permissão específica de uma pessoa não justifica criar
um perfil só para ela, nem mexer no perfil dela (que pode ser compartilhado com outras pessoas) -
pedido do usuário em 2026-09-09.

A fonte de verdade do acesso efetivo continua sendo `permissions_for_user`
(app/core/security.py): perfil (ou papel legado, na ausência de perfil) é a BASE, e os overrides
são aplicados por cima - concessão soma, negação subtrai e vence a concessão do perfil. Este
serviço só cuida do CICLO DE VIDA da exceção (criar, trocar, remover) e da leitura formatada para a
tela; o cálculo de "o que a pessoa tem de verdade" mora só em `security.py`, para nunca haver duas
implementações do mesmo cálculo divergindo entre si.

Regra de negócio pesada fica aqui, não na rota (ver AGENTS.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import base_permissions_for_user, permissions_for_user
from app.models import User, UserPermissionOverride
from app.modules.admin.permissions_service import (
    OTHER_PERMISSIONS_LABEL,
    PermissionValidationError,
    permission_catalog,
    valid_permission_keys,
)

VALID_EFFECTS = ("grant", "deny")

# Mesma chave-trava de `ADMIN_GATEKEEPER_PERMISSION` em `admin/router.py`, mas checada por outro
# ângulo: aquela olha PERFIS (nenhum perfil ativo concede a permissão); esta olha PESSOAS (todo
# mundo com a permissão negada individualmente, mesmo que algum perfil ainda a conceda "no papel").
# As duas guardam o mesmo risco - o ecossistema ficar sem ninguém que administre acesso.
ADMIN_GATEKEEPER_PERMISSION = "admin:users:write"


@dataclass(frozen=True)
class OverrideEntry:
    permission: str
    label: str
    module: str
    effect: str
    reason: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class UserPermissionOverview:
    profile_permissions: list[str]
    overrides: list[OverrideEntry] = field(default_factory=list)
    effective_permissions: list[str] = field(default_factory=list)


def _overrides_by_permission(user: User) -> dict[str, UserPermissionOverride]:
    return {item.permission: item for item in getattr(user, "permission_overrides", []) or []}


def overview(db: Session, user: User) -> UserPermissionOverview:
    """Estado completo pra tela: o que o perfil dá, as exceções, e o resultado efetivo."""
    catalog = {entry.key: entry for entry in permission_catalog(db, with_usage=False)}
    entries = [
        OverrideEntry(
            permission=item.permission,
            label=catalog[item.permission].label if item.permission in catalog else item.permission,
            module=catalog[item.permission].module if item.permission in catalog else OTHER_PERMISSIONS_LABEL,
            effect=item.effect,
            reason=item.reason,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item in sorted(_overrides_by_permission(user).values(), key=lambda item: item.permission)
    ]
    return UserPermissionOverview(
        profile_permissions=sorted(base_permissions_for_user(user)),
        overrides=entries,
        effective_permissions=sorted(permissions_for_user(user)),
    )


def _would_orphan_admin_gatekeeper(db: Session, excluded_user_id: int) -> bool:
    """True se, sem contar o usuário informado, nenhuma outra pessoa ATIVA teria de verdade
    `admin:users:write` - perfil e exceções individuais já aplicados, o mesmo cálculo do login.

    Existe para o mesmo motivo do bloqueio equivalente em perfil (`_profile_delete_blocked_reason`
    em admin/router.py): sem essa checagem, negar (ou remover a única concessão de) esta permissão
    da última pessoa que a tem trancaria o ecossistema por fora - ninguém mais conseguiria
    administrar acesso, nem para desfazer o próprio erro.
    """
    return not any(
        ADMIN_GATEKEEPER_PERMISSION in permissions_for_user(other)
        for other in db.scalars(select(User).where(User.active.is_(True), User.id != excluded_user_id))
    )


def set_override(
    db: Session,
    target: User,
    permission: str,
    effect: str,
    reason: str | None,
    created_by: int | None = None,
) -> UserPermissionOverride:
    if effect not in VALID_EFFECTS:
        raise PermissionValidationError("Efeito inválido. Use 'grant' ou 'deny'.")
    if permission not in valid_permission_keys(db):
        raise PermissionValidationError(f"Permissão inválida: {permission}.")
    if (
        effect == "deny"
        and permission == ADMIN_GATEKEEPER_PERMISSION
        and _would_orphan_admin_gatekeeper(db, target.id)
    ):
        raise PermissionValidationError(
            "Negar esta permissão deixaria o ecossistema sem ninguém que administre acessos "
            f"({ADMIN_GATEKEEPER_PERMISSION}). Garanta que outra pessoa ativa a tenha antes de negar.",
            status_code=409,
        )

    existing = db.scalar(
        select(UserPermissionOverride).where(
            UserPermissionOverride.user_id == target.id,
            UserPermissionOverride.permission == permission,
        )
    )
    if not existing:
        existing = UserPermissionOverride(user_id=target.id, permission=permission, created_by=created_by)
        db.add(existing)
    existing.effect = effect
    existing.reason = (reason or "").strip() or None
    db.flush()
    return existing


def remove_override(db: Session, target: User, permission: str) -> None:
    existing = db.scalar(
        select(UserPermissionOverride).where(
            UserPermissionOverride.user_id == target.id,
            UserPermissionOverride.permission == permission,
        )
    )
    if not existing:
        raise PermissionValidationError("Este usuário não tem uma exceção para esta permissão.", status_code=404)

    # Remover uma CONCESSÃO individual que hoje é a única fonte de admin:users:write para esta
    # pessoa (o perfil dela não concede) trancaria o ecossistema do mesmo jeito que negar -
    # mesma checagem, só que olhando o estado ANTES de remover em vez do estado depois de negar.
    if (
        existing.effect == "grant"
        and permission == ADMIN_GATEKEEPER_PERMISSION
        and ADMIN_GATEKEEPER_PERMISSION not in base_permissions_for_user(target)
        and _would_orphan_admin_gatekeeper(db, target.id)
    ):
        raise PermissionValidationError(
            "Remover esta concessão deixaria o ecossistema sem ninguém que administre acessos "
            f"({ADMIN_GATEKEEPER_PERMISSION}). Garanta que outra pessoa ativa a tenha antes de remover.",
            status_code=409,
        )

    db.delete(existing)
    db.flush()
