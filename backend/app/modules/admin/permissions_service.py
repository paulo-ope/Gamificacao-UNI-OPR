"""Catálogo de permissões do ecossistema e ciclo de vida das permissões próprias.

O catálogo efetivo é a UNIÃO de duas fontes:

- `PERMISSION_LABELS` (app/core/security.py): permissões **do sistema**, declaradas em código -
  são as que as rotas exigem em `require_permission(...)`. Podem ser concedidas e revogadas de
  qualquer perfil, mas NÃO podem ser excluídas do catálogo: apagar o rótulo não apagaria a
  exigência da rota, só deixaria a rota inalcançável sem nenhum aviso na tela.
- `custom_permissions` (banco): permissões **próprias**, criadas na aba Permissões. Essas sim são
  excluíveis, desde que não estejam em uso por nenhum perfil.

Regra de negócio pesada fica aqui, não na rota nem na tela (ver AGENTS.md).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import PERMISSION_LABELS
from app.models import (
    AccessProfile,
    AccessProfilePermission,
    CustomPermission,
    User,
    UserAccessProfile,
    UserPermissionOverride,
)
from app.modules.registry import get_module, list_modules

# Permissões que concedem autoridade de aprovação/administração acima do uso rotineiro do módulo -
# aceitar/rejeitar a decisão da matriz (`management:review`), gerência avançada da Gestão
# (`management:admin`) ou poder sobre o acesso de outras pessoas (`admin:users:*`,
# `admin:roles:write`).
# Achado real: a tela de Perfis de Acesso tinha um único botão "Selecionar módulo" por módulo, e
# `management:review`/`management:admin` caem no mesmo módulo ("Gestão Integrada") que permissões
# de rotina (`management:read`, `management:write_justification`) - marcar o módulo inteiro para
# dar acesso de supervisor concedia, sem aviso, poder de aprovar/rejeitar o caso da matriz. Essas
# permissões ficam de fora do toggle de módulo e exigem clique individual (ver frontend).
SENSITIVE_PERMISSIONS = {
    "management:review",
    "management:admin",
    "admin:users:write",
    "admin:users:delete",
    "admin:roles:write",
    # Quem cria/exclui permissão e reconfigura módulo redesenha o próprio controle de acesso do
    # ecossistema - não pode entrar de carona num "Selecionar módulo" da Administração.
    "admin:permissions:write",
    "admin:modules:write",
}

# Prefixos de permissão que NÃO pertencem a um módulo do registry: transversais (portal do
# colaborador, auditoria da gamificação), infraestrutura de IA e o legado. Módulo do registry fica
# deliberadamente fora daqui - o mapa dele é DERIVADO de `app/modules/registry.py` em
# `module_by_permission_prefix()`. Achado real (2026-09-09): esta lista era escrita à mão e o UNI
# Localiza, criado depois dela, caía em "Outras permissões" na tela de Perfis de Acesso. Derivando
# do registry, módulo novo entra agrupado no mesmo dia em que é registrado.
TRANSVERSAL_MODULE_BY_PREFIX = {
    "ai": "IA e API",
    "audit": "Auditoria",
    "portal": "Portal do Colaborador",
    "users": "Administração legada",
}

# A Gamificação é o único módulo cujas permissões não compartilham um prefixo único (`dashboard:`,
# `orders:`, `scoring:`...). O prefixo da permissão mínima dela (`dashboard`) já vem do registry;
# os demais são declarados aqui e apontam para o mesmo módulo.
GAMIFICATION_PERMISSION_PREFIXES = {
    "calculation",
    "dashboard",
    "health_rules",
    "orders",
    "penalties",
    "scoring",
    "settings",
}

OTHER_PERMISSIONS_LABEL = "Outras permissões"

# `modulo:acao` em minúsculas, com `_` e `:` extras permitidos (`operations:views:read_global` é
# uma chave real). Mesmo formato das chaves de código - permissão própria fora desse padrão viraria
# um catálogo com duas convenções de nome.
PERMISSION_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(:[a-z][a-z0-9_]*){1,3}$")


class PermissionValidationError(ValueError):
    """Erro de regra de negócio do catálogo, traduzido para HTTP 4xx pela rota."""

    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class PermissionCatalogEntry:
    key: str
    label: str
    module: str
    module_key: str | None
    sensitive: bool
    custom: bool
    description: str | None = None
    profile_count: int = 0
    user_count: int = 0
    profile_names: list[str] = field(default_factory=list)
    #: Pessoas com exceção individual (concessão ou negação) para esta permissão - ver
    #: `_override_counts`. Não está incluído em `user_count` de propósito: são duas perguntas
    #: diferentes ("quem tem pelo perfil" vs. "quem tem uma exceção pessoal").
    override_count: int = 0


def module_by_permission_prefix() -> dict[str, tuple[str, str]]:
    """Prefixo da permissão -> (chave do módulo, nome do módulo), derivado do registry.

    O prefixo sai da permissão mínima de cada módulo (`operations:read` -> `operations`), que é a
    convenção de nomenclatura do projeto (ver docs/00-TRILHA-0.md): módulo novo agrupa sozinho, sem
    ninguém precisar lembrar de editar uma lista à mão.
    """
    mapping = {
        module.required_permission.split(":", 1)[0]: (module.key, module.name)
        for module in list_modules()
    }
    gamification = get_module("gamification")
    if gamification:
        for prefix in GAMIFICATION_PERMISSION_PREFIXES:
            mapping.setdefault(prefix, (gamification.key, gamification.name))
    return mapping


def permission_module_info(permission: str) -> tuple[str | None, str]:
    """(chave do módulo, rótulo do grupo) de uma permissão de código.

    A chave é None em permissão transversal (portal, auditoria, IA, legado), que não pertence a
    nenhum módulo do registry.
    """
    prefix = permission.split(":", 1)[0]
    from_registry = module_by_permission_prefix().get(prefix)
    if from_registry:
        return from_registry
    if prefix in TRANSVERSAL_MODULE_BY_PREFIX:
        return None, TRANSVERSAL_MODULE_BY_PREFIX[prefix]
    return None, OTHER_PERMISSIONS_LABEL


def _module_label(module_key: str | None, permission: str) -> tuple[str | None, str]:
    """Grupo de uma permissão própria: o módulo escolhido no cadastro; sem ele, cai na convenção
    de prefixo das permissões de código."""
    if module_key:
        module = get_module(module_key)
        if module:
            return module.key, module.name
    return permission_module_info(permission)


def custom_permissions(db: Session, *, only_active: bool = True) -> list[CustomPermission]:
    statement = select(CustomPermission).order_by(CustomPermission.key.asc())
    if only_active:
        statement = statement.where(CustomPermission.active.is_(True))
    return list(db.scalars(statement))


def valid_permission_keys(db: Session) -> set[str]:
    """Chaves aceitáveis num perfil: as de código mais as próprias ativas."""
    return set(PERMISSION_LABELS) | {item.key for item in custom_permissions(db)}


def validate_permission_keys(db: Session, permission_keys: list[str]) -> list[str]:
    allowed = valid_permission_keys(db)
    invalid = [permission for permission in permission_keys if permission not in allowed]
    if invalid:
        raise PermissionValidationError(f"Permissão inválida: {invalid[0]}.")
    return sorted(set(permission_keys))


def _usage_index(db: Session) -> tuple[dict[str, list[str]], dict[str, set[int]]]:
    """(perfis por permissão, usuários por permissão via PERFIL).

    Usuário entra uma vez só por permissão, mesmo que dois perfis dele a concedam - a pergunta que
    a tela responde é "quantas pessoas perdem este acesso se eu revogar", não "quantos vínculos".
    Não inclui exceção individual de propósito (ver `_override_counts`): esta função mede o que o
    PERFIL concede, que é justamente o que muda se o admin editar um perfil.
    """
    profiles_by_permission: dict[str, list[str]] = {}
    users_by_permission: dict[str, set[int]] = {}

    rows = db.execute(
        select(AccessProfilePermission.permission, AccessProfile.id, AccessProfile.name)
        .join(AccessProfile, AccessProfile.id == AccessProfilePermission.profile_id)
        .order_by(AccessProfile.name.asc())
    ).all()

    users_by_profile: dict[int, set[int]] = {}
    for profile_id, user_id in db.execute(
        select(UserAccessProfile.profile_id, UserAccessProfile.user_id)
        .join(User, User.id == UserAccessProfile.user_id)
        .where(User.active.is_(True))
    ).all():
        users_by_profile.setdefault(profile_id, set()).add(user_id)

    for permission, profile_id, profile_name in rows:
        profiles_by_permission.setdefault(permission, []).append(profile_name)
        users_by_permission.setdefault(permission, set()).update(users_by_profile.get(profile_id, set()))

    return profiles_by_permission, users_by_permission


def _override_counts(db: Session) -> dict[str, int]:
    """Quantas pessoas ATIVAS têm uma exceção individual (concessão ou negação) para cada
    permissão - separado da contagem por perfil de propósito (ver `_usage_index`): é o aviso de
    "cuidado, isto tem exceção" antes de mexer no perfil ou excluir a permissão."""
    return dict(
        db.execute(
            select(UserPermissionOverride.permission, func.count(UserPermissionOverride.id))
            .join(User, User.id == UserPermissionOverride.user_id)
            .where(User.active.is_(True))
            .group_by(UserPermissionOverride.permission)
        ).all()
    )


def permission_catalog(db: Session, *, with_usage: bool = True) -> list[PermissionCatalogEntry]:
    """Catálogo completo (código + próprias), ordenado por grupo e depois por chave."""
    profiles_by_permission: dict[str, list[str]] = {}
    users_by_permission: dict[str, set[int]] = {}
    override_counts: dict[str, int] = {}
    if with_usage:
        profiles_by_permission, users_by_permission = _usage_index(db)
        override_counts = _override_counts(db)

    entries: list[PermissionCatalogEntry] = []
    for key, label in PERMISSION_LABELS.items():
        module_key, module_label = permission_module_info(key)
        entries.append(
            PermissionCatalogEntry(
                key=key,
                label=label,
                module=module_label,
                module_key=module_key,
                sensitive=key in SENSITIVE_PERMISSIONS,
                custom=False,
                profile_count=len(profiles_by_permission.get(key, [])),
                user_count=len(users_by_permission.get(key, set())),
                profile_names=profiles_by_permission.get(key, []),
                override_count=override_counts.get(key, 0),
            )
        )

    for item in custom_permissions(db):
        module_key, module_label = _module_label(item.module_key, item.key)
        entries.append(
            PermissionCatalogEntry(
                key=item.key,
                label=item.label,
                module=module_label,
                module_key=module_key,
                sensitive=item.sensitive,
                custom=True,
                description=item.description,
                profile_count=len(profiles_by_permission.get(item.key, [])),
                user_count=len(users_by_permission.get(item.key, set())),
                profile_names=profiles_by_permission.get(item.key, []),
                override_count=override_counts.get(item.key, 0),
            )
        )

    return sorted(entries, key=lambda entry: (entry.module.casefold(), entry.key))


def _normalized_key(raw: str) -> str:
    key = raw.strip().lower()
    if not PERMISSION_KEY_PATTERN.match(key):
        raise PermissionValidationError(
            "Chave inválida. Use o formato modulo:acao, só com letras minúsculas, números e _ "
            "(exemplo: localiza:exportar)."
        )
    return key


def _validate_module_key(module_key: str | None) -> str | None:
    if not module_key:
        return None
    if not get_module(module_key):
        raise PermissionValidationError("Módulo inválido para agrupar a permissão.")
    return module_key


def create_custom_permission(
    db: Session,
    *,
    key: str,
    label: str,
    module_key: str | None,
    description: str | None,
    sensitive: bool,
    created_by: int | None,
) -> CustomPermission:
    normalized = _normalized_key(key)
    if normalized in PERMISSION_LABELS:
        raise PermissionValidationError(
            "Esta chave já é uma permissão do sistema, declarada em código.", status_code=409
        )
    exists = db.scalar(select(CustomPermission).where(func.lower(CustomPermission.key) == normalized))
    if exists:
        raise PermissionValidationError("Já existe uma permissão própria com esta chave.", status_code=409)
    text_label = label.strip()
    if len(text_label) < 3:
        raise PermissionValidationError("Descreva a permissão em pelo menos 3 caracteres.")
    permission = CustomPermission(
        key=normalized,
        label=text_label,
        description=(description or "").strip() or None,
        module_key=_validate_module_key(module_key),
        sensitive=bool(sensitive),
        active=True,
        created_by=created_by,
    )
    db.add(permission)
    db.flush()
    return permission


def update_custom_permission(
    db: Session,
    permission: CustomPermission,
    *,
    label: str | None = None,
    module_key: str | None = None,
    description: str | None = None,
    sensitive: bool | None = None,
    active: bool | None = None,
    module_key_provided: bool = False,
) -> CustomPermission:
    """A CHAVE nunca muda: perfis já a referenciam por texto (`access_profile_permissions`), e
    renomear silenciosamente deixaria os vínculos apontando para uma permissão que não existe
    mais. Quem errou a chave exclui e cria de novo."""
    if label is not None:
        text_label = label.strip()
        if len(text_label) < 3:
            raise PermissionValidationError("Descreva a permissão em pelo menos 3 caracteres.")
        permission.label = text_label
    if module_key_provided:
        permission.module_key = _validate_module_key(module_key)
    if description is not None:
        permission.description = description.strip() or None
    if sensitive is not None:
        permission.sensitive = bool(sensitive)
    if active is not None:
        permission.active = bool(active)
    db.flush()
    return permission


def delete_custom_permission(db: Session, permission: CustomPermission) -> None:
    profiles = db.scalars(
        select(AccessProfile.name)
        .join(AccessProfilePermission, AccessProfilePermission.profile_id == AccessProfile.id)
        .where(AccessProfilePermission.permission == permission.key)
        .order_by(AccessProfile.name.asc())
    ).all()
    if profiles:
        raise PermissionValidationError(
            "Esta permissão ainda está em uso por: " + ", ".join(profiles) + ". Remova dos perfis antes de excluir.",
            status_code=409,
        )
    # Mesma checagem, para a exceção individual (ver `UserPermissionOverride`) - sem isto, excluir
    # uma permissão própria deixaria um override órfão apontando pra uma chave que não existe mais
    # no catálogo, sem nenhum aviso.
    people_with_override = db.scalars(
        select(User.name)
        .join(UserPermissionOverride, UserPermissionOverride.user_id == User.id)
        .where(UserPermissionOverride.permission == permission.key)
        .order_by(User.name.asc())
    ).all()
    if people_with_override:
        raise PermissionValidationError(
            "Esta permissão ainda está concedida ou negada individualmente para: "
            + ", ".join(people_with_override)
            + ". Remova essas exceções antes de excluir.",
            status_code=409,
        )
    db.delete(permission)
