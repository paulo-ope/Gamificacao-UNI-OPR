"""Resolução da política efetiva de exposição - fonte única consultada por API e MCP (item 25 do
pedido: "não espalhar permissões em vários arquivos hardcoded"). Combina, nesta ordem:

1. `field_registry.build_field_registry()` - capacidade base calculada do código (o que a query
   já sabe fazer hoje).
2. `AiFieldPermission`/`AiEndpoint` - overrides administrativos persistidos (ausência de linha =
   usa o default do passo 1).
3. `AiProfileFieldGrant`/`AiProfileEndpointGrant` - restrição adicional por perfil do usuário
   (ausência de qualquer linha para aquele perfil = sem restrição além do passo 2).

O resultado é cacheado em memória de processo por usuário, invalidado por uma versão incremental
gravada em `AppSetting` (mesmo padrão de cache-bust já usado no projeto para outras configurações)
- qualquer escrita nas tabelas de governança deve chamar `bump_policy_version()`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppSetting, User
from app.modules.ai_governance.field_registry import FieldDescriptor, build_field_registry
from app.modules.ai_governance.models import (
    AiEndpoint,
    AiFieldPermission,
    AiProfileEndpointGrant,
    AiProfileFieldGrant,
)

POLICY_VERSION_SETTING_KEY = "ai_governance_policy_version"

FieldCapability = str  # "filterable" | "text_filterable" | "groupable" | "returnable" | "selectable" | "detail_available"


@dataclass(frozen=True)
class EffectiveField:
    descriptor: FieldDescriptor
    enabled: bool
    profile_restricted: bool  # True quando o perfil tem allow-list e este campo não está nela

    def allows(self, capability: FieldCapability) -> bool:
        if not self.enabled or self.profile_restricted:
            return False
        if self.descriptor.sensitive and capability != "detail_available":
            # Campo sensível nunca é filtrável/agrupável/retornável/selecionável - só pode
            # aparecer no detalhe, e mesmo assim redigido pela camada de schema existente (ver
            # operations/schemas.py:_sanitize_raw_payload). Isso é código, não configuração: a
            # Administração pode desligar um campo sensível, nunca "ligá-lo" além do detalhe.
            return False
        return bool(getattr(self.descriptor, capability, False))


@dataclass(frozen=True)
class EffectiveEndpoint:
    key: str
    enabled_api: bool
    enabled_mcp: bool
    enabled_ai: bool
    profile_restricted_api: bool
    profile_restricted_mcp: bool

    def allowed(self, origin: str) -> bool:
        if origin == "api":
            return self.enabled_api and self.enabled_ai and not self.profile_restricted_api
        if origin == "mcp":
            return self.enabled_mcp and self.enabled_ai and not self.profile_restricted_mcp
        raise ValueError(f"origem desconhecida: {origin}")


@dataclass(frozen=True)
class EffectivePolicy:
    fields: dict[tuple[str, str], EffectiveField] = field(default_factory=dict)
    endpoints: dict[str, EffectiveEndpoint] = field(default_factory=dict)

    def field_allowed(self, entity: str, field_name: str, capability: FieldCapability) -> bool:
        effective = self.fields.get((entity, field_name))
        if effective is None:
            # Campo não catalogado: nunca autorizado por padrão (item 2 do pedido - "não significa
            # liberar tudo automaticamente"; um campo desconhecido não pode ser mais permissivo que
            # um campo conhecido e desabilitado).
            return False
        return effective.allows(capability)

    def selectable_fields(self, entity: str) -> list[str]:
        return sorted(
            field_name
            for (field_entity, field_name), effective in self.fields.items()
            if field_entity == entity and effective.allows("selectable")
        )

    def endpoint_allowed(self, endpoint_key: str, origin: str) -> bool:
        endpoint = self.endpoints.get(endpoint_key)
        if endpoint is None:
            # Mesmo racional: endpoint não cadastrado na governança não é autorizado por padrão.
            return False
        return endpoint.allowed(origin)

    def field_catalog(self) -> list[dict]:
        """Catálogo dinâmico de campos e capacidades (item 10 do pedido) - substitui
        `ai.queries.available_fields()` (estático) por um retorno que já reflete overrides
        administrativos e restrição por perfil vigentes para o usuário desta política.

        `enabled_for_api`/`enabled_for_mcp`/`enabled_for_ai` hoje espelham o mesmo `enabled` geral
        do campo - a governança atual distingue API/MCP/IA no nível de ENDPOINT (`AiEndpoint`), não
        por campo; um grant de campo por origem é uma extensão possível de uma fase futura, não
        implementada ainda."""
        items = []
        for (entity, field_name), effective in sorted(self.fields.items()):
            enabled = effective.enabled and not effective.profile_restricted
            items.append(
                {
                    "entity": entity,
                    "field": field_name,
                    "type": effective.descriptor.type,
                    "description": None,
                    "filterable": effective.allows("filterable"),
                    "text_filterable": effective.allows("text_filterable"),
                    "groupable": effective.allows("groupable"),
                    "returnable": effective.allows("returnable"),
                    "selectable": effective.allows("selectable"),
                    "detail_available": effective.allows("detail_available"),
                    "sensitive": effective.descriptor.sensitive,
                    "enabled_for_api": enabled,
                    "enabled_for_mcp": enabled,
                    "enabled_for_ai": enabled,
                }
            )
        return items


_cache: dict[tuple[int, int], EffectivePolicy] = {}


def _current_policy_version(db: Session) -> int:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == POLICY_VERSION_SETTING_KEY))
    if not setting:
        return 0
    try:
        return int(setting.value)
    except (TypeError, ValueError):
        return 0


def bump_policy_version(db: Session) -> None:
    """Chamar após qualquer escrita em `AiEndpoint`/`AiFieldPermission`/`AiProfileEndpointGrant`/
    `AiProfileFieldGrant` - invalida o cache em memória de todo o processo (Fase 4 usará isto nos
    endpoints administrativos de escrita)."""
    setting = db.scalar(select(AppSetting).where(AppSetting.key == POLICY_VERSION_SETTING_KEY))
    next_version = _current_policy_version(db) + 1
    if setting:
        setting.value = str(next_version)
    else:
        db.add(AppSetting(key=POLICY_VERSION_SETTING_KEY, value=str(next_version), description="Versão da política de exposição IA/MCP - incrementada a cada mudança administrativa."))
    db.commit()
    _cache.clear()


def _user_profile_ids(user: User) -> list[int]:
    return [profile.id for profile in getattr(user, "access_profiles", []) or [] if profile.active]


def resolve_effective_policy(db: Session, user: User) -> EffectivePolicy:
    profile_ids = tuple(sorted(_user_profile_ids(user)))
    cache_key = (user.id, hash(profile_ids) ^ _current_policy_version(db))
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    registry = build_field_registry()
    field_overrides = {
        (row.entity, row.field): row for row in db.scalars(select(AiFieldPermission))
    }
    endpoint_rows = {row.key: row for row in db.scalars(select(AiEndpoint))}

    profile_field_grants: dict[tuple[str, str], list[bool]] = {}
    if profile_ids:
        for row in db.scalars(select(AiProfileFieldGrant).where(AiProfileFieldGrant.profile_id.in_(profile_ids))):
            profile_field_grants.setdefault((row.entity, row.field), []).append(row.granted)

    profile_endpoint_grants: dict[str, list[bool]] = {}
    if profile_ids:
        for row in db.scalars(select(AiProfileEndpointGrant).where(AiProfileEndpointGrant.profile_id.in_(profile_ids))):
            profile_endpoint_grants.setdefault(row.endpoint_key, []).append(row.granted)

    fields: dict[tuple[str, str], EffectiveField] = {}
    for entity, entity_fields in registry.items():
        for field_name, descriptor in entity_fields.items():
            override = field_overrides.get((entity, field_name))
            if override is not None:
                descriptor = FieldDescriptor(
                    entity=entity,
                    field=field_name,
                    type=descriptor.type,
                    filterable=override.filterable,
                    text_filterable=override.text_filterable,
                    groupable=override.groupable,
                    returnable=override.returnable,
                    selectable=override.selectable,
                    detail_available=override.detail_available,
                    sensitive=override.sensitive,
                )
                enabled = override.enabled
            else:
                enabled = descriptor.default_enabled
            grants = profile_field_grants.get((entity, field_name))
            profile_restricted = grants is not None and not any(grants)
            fields[(entity, field_name)] = EffectiveField(descriptor=descriptor, enabled=enabled, profile_restricted=profile_restricted)

    endpoints: dict[str, EffectiveEndpoint] = {}
    for key, row in endpoint_rows.items():
        grants = profile_endpoint_grants.get(key)
        restricted = grants is not None and not any(grants)
        endpoints[key] = EffectiveEndpoint(
            key=key,
            enabled_api=row.enabled_api,
            enabled_mcp=row.enabled_mcp,
            enabled_ai=row.enabled_ai,
            profile_restricted_api=restricted,
            profile_restricted_mcp=restricted,
        )

    policy = EffectivePolicy(fields=fields, endpoints=endpoints)
    _cache[cache_key] = policy
    return policy
