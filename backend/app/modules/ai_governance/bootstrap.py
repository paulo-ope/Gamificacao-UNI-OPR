"""Seed inicial da governança IA/MCP - item 26 do pedido ("na primeira migração, preserve o
comportamento atual"). Roda no `lifespan` do app (mesmo padrão de `ensure_access_profiles`), é
idempotente (só insere o que ainda não existe) e nunca sobrescreve uma linha já configurada pela
Administração - rodar de novo depois de a Administração mudar algo não desfaz a mudança.

Os endpoints/tools abaixo são exatamente os que já existem e já funcionam hoje (levantados no
inventário técnico que precedeu esta implementação) - todos entram habilitados, replicando o
estado atual. Campos entram com a capacidade calculada por `field_registry` e `enabled` igual ao
`default_enabled` do descritor (True para tudo que já é exposto hoje pela API/MCP; False para
capacidade nova ainda não usada por nenhum endpoint, como os campos de status de login)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.ai_governance.field_registry import build_field_registry
from app.modules.ai_governance.models import AiEndpoint, AiFieldPermission

# (key, label, kind, default_enabled) - kind documenta onde o endpoint vive hoje ("api" | "mcp");
# é só documentação (o gate de verdade depende de `enabled_api`/`enabled_mcp`/`enabled_ai`, não de
# `kind`). Desde a Fase 2/3 do plano de migração, `operations/router.py` e `ai/router.py` já
# consultam estas linhas de verdade (`enforce_ai_endpoint_for_user`) - desabilitar uma linha aqui
# bloqueia o endpoint/tool correspondente imediatamente (ver `ai_governance/policy.py:bump_policy_version`).
# `default_enabled=False` é só para capacidade GENUINAMENTE NOVA (item 26 do pedido) - tudo que já
# funcionava antes desta governança existir entra habilitado, replicando o estado atual.
_SEED_ENDPOINTS: list[tuple[str, str, str, bool]] = [
    ("ai.search_orders", "Buscar O.S. (opr_search_orders)", "mcp", True),
    ("ai.order_details", "Detalhe de O.S. por order_code/OS_ID (opr_order_details)", "mcp", True),
    ("ai.aggregate_orders", "Agregar O.S. por dimensão (opr_aggregate_orders)", "mcp", True),
    ("ai.orders_timeseries", "Série temporal de O.S. (opr_orders_timeseries)", "mcp", True),
    ("ai.backlog_aging", "Idade do backlog (opr_backlog_aging)", "mcp", True),
    ("ai.backlog_history", "Histórico de backlog (opr_backlog_history)", "mcp", True),
    ("ai.filter_options", "Opções de filtro (opr_filter_options)", "mcp", True),
    ("ai.warranty_analytics", "Análise de garantia (opr_warranty_analytics)", "mcp", True),
    ("ai.team_targets", "Metas de equipe vigentes (opr_team_targets)", "mcp", True),
    ("ai.team_target_performance", "Realizado x meta (opr_team_target_performance)", "mcp", True),
    ("ai.list_fields", "Catálogo de campos (opr_list_fields)", "mcp", True),
    ("ai.management_cases", "Casos de Gestão Integrada (opr_management_cases)", "mcp", True),
    ("operations.orders.list", "Listagem de O.S. (GET /operations/orders)", "api", True),
    ("operations.orders.detail", "Detalhe de O.S. (GET /operations/orders/{id})", "api", True),
    ("operations.filters", "Opções de filtro (GET /operations/filters)", "api", True),
    ("operations.sla", "Quebra de SLA (GET /operations/sla)", "api", True),
    ("operations.sla.hierarchy", "Hierarquia de SLA (GET /operations/sla/hierarchy)", "api", True),
    ("operations.sla.collaborators", "SLA por colaborador (GET /operations/sla/collaborators)", "api", True),
    ("operations.warranty", "Análise de garantia (GET /operations/warranty)", "api", True),
    ("operations.calendar", "Mapa de produtividade (GET /operations/calendar)", "api", True),
    ("operations.in_progress", "Backlog por dimensão (GET /operations/in-progress)", "api", True),
    ("operations.in_progress.orders", "O.S. em backlog (GET /operations/in-progress/orders)", "api", True),
    ("operations.openings.analytics", "Dashboard de aberturas (GET /operations/openings/analytics)", "api", True),
    ("operations.openings.orders", "O.S. abertas (GET /operations/openings/orders)", "api", True),
    ("operations.network.offline_login_clusters", "Clusters de login offline (GET /operations/network/offline-login-clusters)", "api", True),
    # Novo (item 20 do pedido) - consulta individual de status/geo de login nunca existiu antes
    # desta governança, então entra desabilitado até a Administração decidir liberar.
    ("operations.network.logins", "Status individual de login (GET /operations/network/logins)", "api", False),
    # Novo (pedido do usuário em 2026-08-14) - telemetria óptica/ONU (sinal RX/TX, causa da última
    # queda, transmissor) nunca foi capturada nem exposta antes - entra desabilitado por padrão.
    ("operations.network.onu_signal", "Telemetria óptica/ONU (GET /operations/network/onu-signal)", "api", False),
    ("ai.offline_login_clusters", "Clusters de login offline para IA (POST /ai/infra/offline-login-clusters)", "api", False),
    ("ai.onu_signal", "Telemetria óptica/ONU para IA (POST /ai/infra/onu-signal)", "api", False),
]


def ensure_ai_governance_seed(db: Session) -> None:
    existing_endpoint_keys = set(db.scalars(select(AiEndpoint.key)))
    for key, label, kind, default_enabled in _SEED_ENDPOINTS:
        if key in existing_endpoint_keys:
            continue
        db.add(
            AiEndpoint(
                key=key,
                label=label,
                kind=kind,
                enabled_api=default_enabled,
                enabled_mcp=default_enabled,
                enabled_ai=default_enabled,
            )
        )

    # `db.scalars()` só devolveria a 1a coluna de um select multi-coluna (achado real, confirmado
    # no smoke test) - `db.execute(...).all()` é o jeito certo de pegar as duas colunas como tupla.
    existing_field_keys = {
        (entity, field_name) for entity, field_name in db.execute(select(AiFieldPermission.entity, AiFieldPermission.field)).all()
    }
    for entity_fields in build_field_registry().values():
        for descriptor in entity_fields.values():
            if (descriptor.entity, descriptor.field) in existing_field_keys:
                continue
            db.add(
                AiFieldPermission(
                    entity=descriptor.entity,
                    field=descriptor.field,
                    filterable=descriptor.filterable,
                    text_filterable=descriptor.text_filterable,
                    groupable=descriptor.groupable,
                    returnable=descriptor.returnable,
                    selectable=descriptor.selectable,
                    detail_available=descriptor.detail_available,
                    sensitive=descriptor.sensitive,
                    enabled=descriptor.default_enabled,
                )
            )

    db.commit()
