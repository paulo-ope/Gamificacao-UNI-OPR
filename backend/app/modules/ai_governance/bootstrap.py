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
    # default_enabled=True desde 2026-08-15 (achado real: a tool MCP nunca existiu, so agora
    # exposta - a versao REST equivalente, operations.network.offline_login_clusters, ja e True;
    # nao fazia sentido a mesma capacidade ficar inconsistente entre origem api/mcp).
    ("ai.offline_login_clusters", "Clusters de login offline para IA (POST /ai/infra/offline-login-clusters)", "api", True),
    ("ai.onu_signal", "Telemetria óptica/ONU para IA (POST /ai/infra/onu-signal)", "api", False),
    # Novo (pedido do usuário em 2026-08-14) - status individual de login para IA/MCP (chave de API
    # e conector remoto), distinto do agregado de cluster acima. Entra desabilitado por padrão,
    # mesmo racional de "operations.network.logins".
    ("ai.login_status", "Status individual de login para IA (POST /ai/infra/login-status)", "api", False),
    # Novo (pedido do usuário em 2026-08-15) - busca paginada e detalhamento completo de login
    # (ONU/PON, tempo no estado atual, histórico de eventos). `default_enabled=True` porque é a
    # continuação direta de uma feature já habilitada explicitamente hoje mesmo (ver migration
    # 20260815_0058) - não faria sentido a busca nova nascer desligada com o resto já ligado.
    ("operations.network.login_search", "Busca paginada de login (GET /operations/network/logins/search)", "api", True),
    ("operations.network.login_detail", "Detalhamento de login (GET /operations/network/login-detail)", "api", True),
    ("ai.search_logins", "Busca paginada de login para IA/MCP (opr_search_logins)", "mcp", True),
    ("ai.login_detail", "Detalhamento de login para IA/MCP (opr_get_login_detail)", "mcp", True),
    # Novo (pedido do usuário em 2026-08-15) - agregação/quedas por período/série temporal de login,
    # para detecção de incidente coletivo. Mesmo racional de default_enabled=True dos itens acima.
    ("operations.network.login_aggregate", "Agregação de login (GET /operations/network/login-aggregate)", "api", True),
    ("operations.network.login_outages", "Quedas por período (GET /operations/network/login-outages)", "api", True),
    ("operations.network.login_timeseries", "Série temporal de login (GET /operations/network/login-timeseries)", "api", True),
    ("ai.login_aggregate", "Agregação de login para IA/MCP (opr_login_aggregate)", "mcp", True),
    ("ai.login_outages", "Quedas por período para IA/MCP (opr_login_outages)", "mcp", True),
    ("ai.login_timeseries", "Série temporal de login para IA/MCP (opr_login_timeseries)", "mcp", True),
    # Novo (pedido do usuário em 2026-08-15) - funil de incidente coletivo numa unica chamada.
    ("operations.network.login_incident_analysis", "Funil de incidente (GET /operations/network/login-incident-analysis)", "api", True),
    ("ai.login_incident_analysis", "Funil de incidente para IA/MCP (opr_login_incident_analysis)", "mcp", True),
    # Novo (Fase 1 do plano de confiabilidade de dado, pedido do usuario em 2026-08-15) - auditoria
    # de qualidade de coordenadas, so leitura/classificacao, sem correcao automatica.
    ("operations.network.coordinate_quality", "Auditoria de coordenadas (GET /operations/network/coordinate-quality)", "api", True),
    ("ai.coordinate_quality", "Auditoria de coordenadas para IA/MCP (opr_coordinate_quality_audit)", "mcp", True),
    # Novo (pedido do usuário em 2026-08-17) - série histórica de sinal óptico/ONU (antes só existia
    # o valor mais recente, ver operations_onu_signal_current). Mesma chave compartilhada entre a
    # rota REST (origin "api") e a tool MCP (origin "mcp") - mesmo padrão de
    # "operations.network.onu_signal" para o estado atual. `default_enabled=True` porque nasce como
    # continuação direta de capacidade já habilitada hoje, não uma exposição nova e desconhecida.
    ("operations.network.onu_signal_history", "Histórico de sinal óptico/ONU (GET /operations/network/onu-signal/history, opr_onu_signal_history)", "api", True),
    ("ai.onu_signal_history", "Histórico de sinal óptico/ONU para IA (POST /ai/infra/onu-signal-history)", "api", True),
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
