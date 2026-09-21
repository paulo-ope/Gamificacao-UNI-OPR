# API — MCP Connector (opr_*)

> Fonte: `backend/app/modules/mcp_connector/server.py` (servidor MCP remoto), `backend/app/modules/mcp_connector/router.py`
> (tela de login/consentimento), `backend/app/modules/mcp_connector/provider.py` (OAuth) e `backend/app/main.py` (montagem).
> Este documento descreve o contrato tal como implementado no código nesta branch — não inclui nada que não tenha
> sido confirmado lendo a fonte.

## Visão geral

O **MCP Connector** é o servidor MCP (Model Context Protocol) remoto da Operação Analítica UNI OPR. Ele expõe, para um
agente de IA externo (Claude.ai, ChatGPT, Cowork, etc.) conectado via protocolo MCP sobre Streamable HTTP, **38 tools**
prefixadas com `opr_` que dão acesso de leitura (e uma única de escrita) aos dados operacionais do sistema:

- **Operação Analítica** (Ordens de Serviço/O.S.): agregações, séries temporais, busca paginada, detalhe por código,
  estado "agora" das O.S. em andamento, backlog (idade e histórico), garantia de ativação, metas de equipe x realizado,
  catálogo de campos disponíveis.
- **Frescor de dados / snapshot operacional**: quando a última importação de O.S. do IXC terminou com sucesso.
- **Rede / login / ONU**: status de conectividade por login (PPPoE/fibra), telemetria óptica (sinal RX/TX, causa de
  queda, PON/OLT), histórico de eventos de conexão, detecção de incidente coletivo (clusters geográficos de queda,
  funil de incidente), auditoria de qualidade de coordenadas.
- **Agendamento**: reagendamentos por técnico de campo e por operador de backoffice.
- **Casos de gestão** (Gestão Integrada): casos de produtividade abaixo da meta, fila de cobrança de justificativa,
  leitura do texto das justificativas.
- **Suporte / OPA Suite (SGP Suporte)**: indicadores consolidados (TMA/TMR), breakdowns por dimensão, série temporal
  diária.
- **Atendimento IXC** (`su_ticket`): indicador antecipado de incidente (não substitui a O.S. — ver `docs/STATUS.md`).
- **Cockpit / UNI Intelligence**: leitura do contexto completo de um profile da TV operacional e publicação de
  conteúdo (insight de IA, aviso, comunicado) — a única tool de escrita de toda a superfície.

O servidor roda **dentro do mesmo processo do backend**, chamando as funções de consulta do módulo `ai` (e dos demais
módulos) diretamente — sem dar a volta por HTTP interno. Ele é montado apenas quando `PUBLIC_BASE_URL` está
configurada (`backend/app/main.py`), em `{api_prefix}/mcp`, via `app.mount(...)` sobre o app ASGI devolvido por
`streamable_http_app()` do SDK do MCP. As rotas de consentimento OAuth (HTML) ficam num `APIRouter` separado,
incluído em `{api_prefix}/oauth` (prefixo do próprio router: `/oauth`).

Segundo o comentário de cabeçalho do arquivo fonte, este servidor remoto é um **superconjunto** do servidor local via
stdio usado por Claude Code/Desktop (`mcp-server/opr_analitica_mcp.py`) — as duas listas de tools **não são
sincronizadas automaticamente**; ao momento da leitura, o servidor remoto tinha 4 tools (as de reagendamento e as
duas de cockpit) que ainda não haviam sido portadas para o stdio.

## Autenticação

A autenticação é **OAuth 2.0** (SDK oficial do MCP), não uma chave de API fixa. Não há um conceito de escopo
granular: o único escopo reconhecido é `ai:query` (constante `SCOPE` em `provider.py`), o mesmo nome de permissão já
usado pela chave de API do módulo `ai`. Aprovar o consentimento concede **acesso de leitura** à Operação Analítica —
a exceção é `opr_publish_cockpit_content`, que exige adicionalmente a permissão `intelligence:publish` do usuário
autenticado (ver seção de Cockpit abaixo).

Fluxo, conforme implementado em `provider.py` e `router.py`:

1. O cliente MCP (ex.: Claude) inicia o fluxo OAuth padrão contra o `issuer_url` (`{PUBLIC_BASE_URL}{api_prefix}/mcp`),
   registrando-se dinamicamente (`ClientRegistrationOptions(enabled=True)`, com `valid_scopes=["ai:query"]` e
   `default_scopes=["ai:query"]`).
2. O SDK do MCP abre `/authorize`, que cria um `McpOAuthPendingAuthorization` e redireciona para a tela de
   consentimento própria do sistema: `GET /api/oauth/consent?request_id=...`.
3. Essa tela **reaproveita o login já existente** do sistema (`User.password_hash` / `verify_password`, mesmo
   limitador de tentativas de `app/api/routes/auth.py`) — não é uma conta nova. A sessão da tela de consentimento vive
   num cookie próprio `mcp_oauth_session` (HttpOnly, `secure` conforme HTTPS detectado via `X-Forwarded-Proto`,
   `SameSite=Lax`, `max_age=900` segundos), separado do token Bearer usado pelo resto da API.
4. Se o usuário logado não tiver a permissão `ai:query`, a tela mostra "Sem permissão" e para ali.
5. Ao aprovar (`POST /api/oauth/consent/decide`, `decision=approve`), o sistema gera um `authorization_code` (TTL de
   5 minutos, `AUTHORIZATION_CODE_TTL`) e redireciona de volta ao `redirect_uri` do cliente MCP.
6. O cliente troca o código pelo par de tokens via o endpoint `/token` padrão do SDK do MCP:
   - **Access token**: validade de **6 horas** (`ACCESS_TOKEN_TTL`; era 1h, ampliado por sessões de análise longas
     esbarrarem no vencimento no meio de uma investigação).
   - **Refresh token**: validade de **30 dias** (`REFRESH_TOKEN_TTL`).
7. Em cada chamada de tool, o servidor resolve o usuário autenticado a partir do access token via
   `get_access_token()` / `resolve_user_for_access_token` (função interna de `_current_user()` em `server.py`) — **não
   existe acesso irrestrito**: todas as consultas aplicam o escopo regional do usuário autenticado
   (`effective_managed_regionals`), a mesma regra usada em toda a aplicação. Um token inválido/expirado gera erro
   explícito ("Nenhum token de acesso encontrado" / "Usuário do token não encontrado ou inativo").

Descoberta de metadados: além do endpoint padrão `/.well-known/oauth-authorization-server` (RFC 8414) registrado
pelo SDK, o servidor também expõe os mesmos metadados em `/.well-known/openid-configuration` — não é um provedor
OIDC de verdade (sem `id_token`/`userinfo`), mas alguns clientes (ex.: o conector do ChatGPT, segundo comentário no
código) tentam essa descoberta depois do fluxo OAuth e travam a sessão sem ela.

Proteção de transporte: o `TransportSecuritySettings` do SDK restringe `allowed_hosts`/`allowed_origins` ao host
público configurado (`PUBLIC_BASE_URL`) mais `localhost`/`127.0.0.1` — chamadas com `Host` fora dessa lista recebem
421.

Cada permissão de módulo adicional é verificada dentro da própria tool, quando aplicável — não é coberta pelo escopo
OAuth único:
- **Suporte/OPA**: exige `support:read` (`_support_user()`), sem escopo por regional (quem tem a permissão vê o
  módulo inteiro, igual à tela `/suporte`).
- **Gestão Integrada**: exige `management:read` (`_management_user()`); visibilidade de casos segue a mesma regra da
  tela (quem não tem `management:review` só vê os casos das regionais que gerencia ou dos quais é supervisor).
- **Agendamento** (reagendamentos): exige `scheduling:read`.
- **Estado operacional agora** (`opr_operations_now`): exige `operations:view_backlog`, e adicionalmente
  `operations:view_order_details` quando `include_orders=true`.
- **Cockpit**: leitura exige `intelligence:read`; publicação exige `intelligence:publish`.
- Demais tools de O.S./rede passam pelo *gate* de governança de IA (`enforce_ai_endpoint_for_user` /
  `ai_governance.gate`), que aplica a política de exposição de campos vigente por perfil (ver `opr_list_fields`).

## Catálogo de ferramentas

Convenções gerais observadas no código:
- Datas simples usam o formato `AAAA-MM-DD`; datetimes exatos usam ISO 8601 com offset (ex.:
  `"2026-08-15T17:30:00-04:00"`), aceitando qualquer timezone de entrada.
- Toda resposta é uma string JSON (`_dump`/`_dump_iso` — `json.dumps(..., ensure_ascii=False, default=str/iso)`).
- Filtro com chave desconhecida **sempre gera erro explícito**, nunca é ignorado em silêncio — padrão repetido em
  praticamente todas as tools, resultado de "achados reais" documentados no próprio código (filtros descartados
  silenciosamente já causaram investigação de bug em produção).
- Todas as tools são `readOnlyHint: True` exceto `opr_publish_cockpit_content` (`readOnlyHint: False`).

### Pedidos/O.S. e analytics

| Tool | Propósito | Parâmetros principais | Retorno (campos principais) |
|---|---|---|---|
| `opr_aggregate_orders` | Agrupa O.S. por 1–3 dimensões e calcula uma métrica por grupo (ex.: backlog por bairro, taxa de SLA por regional). | `date_from`, `date_to` (obrig., AAAA-MM-DD); `group_by` (obrig., string ou lista até 3 — ver dimensões abaixo); `metric` (obrig.: `quantidade_aberta`, `quantidade_fechada`, `taxa_sla`, `horas_medias`, `quantidade_atrasada`, `quantidade_backlog`, `horas_abertura_agenda`, `horas_agenda_execucao`, `horas_execucao_fechamento`, `horas_abertura_fechamento`); `filters` (opcional, ver bloco de filtros abaixo). | `{"meta": {...}, "data": [{"label", "quantity", "metric_value", "percentage"}, ...]}`, ordenado por quantidade decrescente. |
| `opr_orders_timeseries` | Série temporal (dia/semana/mês) de O.S. abertas/fechadas/saldo/taxa de SLA. | `date_from`, `date_to` (obrig.); `metric` (obrig.: `abertas`, `fechadas`, `saldo`, `taxa_sla`); `granularity` (`day`/`week`/`month`, default `day`); `group_by` (opcional); `filters` (opcional). | `{"meta": {...}, "data": [{"period_start", "quantity", "group", "sla_rate"}, ...]}`. `sla_rate` só preenchido com `metric="taxa_sla"`. |
| `opr_search_orders` | Busca paginada de O.S. individuais, com busca livre e todos os campos de SLA/tempo calculados. | `date_from`, `date_to` (obrig.); `page` (default 1); `page_size` (10–200, default 50); `keyword` (opcional); `filters` (opcional); `date_field` (opcional — marco único de data); `fields` (opcional, subconjunto de campos); `response_mode` (`full`/`summary`, default `full`). | `{"items": [...], "total_encontrado", "page", "page_size", "has_more", "meta"}`. Item inclui `order_code`, `regional`, `city`, `neighborhood`, `sector`, `subject`, coordenadas, `distance_km` (com filtro de raio), datas do ciclo de vida, indicadores de SLA e meta de equipe. |
| `opr_order_details` | Detalhe de uma ou várias O.S. por `order_code`/`source_order_id` (OS_ID), sem exigir período. | `order_codes` e/ou `source_order_ids` (listas, até 50 cada — pelo menos uma obrigatória); `fields` (opcional); `response_mode` (`full`/`summary`). | `{"items": [...], "not_found_order_codes": [...], "not_found_source_order_ids": [...]}`. Campo de assunto chama-se `os_subject` aqui (vs. `subject` em `opr_search_orders`). |
| `opr_operations_now` | Estado "agora" das O.S. **em andamento** (`is_closed=false`) e risco preditivo de SLA — não recebe período. | `group_by` (`regional`/`city`/`os_type`/`subject`/`status`, default `regional`); `filters` (chaves restritas — ver nota abaixo); `sla_risk` (balde, só com `include_orders=true`); `include_orders` (default `false`); `page`/`page_size` (10–200); `sort_by`; `sort_dir`; `fields`; `response_mode` (default `summary`). | `{"checked_at", "total_in_progress", "sla_risk": [5 baldes sempre presentes], "breakdown", "applied_filters", "orders"}`. Baldes: `breached`, `critical`, `attention`, `on_track`, `no_target`. |
| `opr_backlog_aging` | Idade do backlog (O.S. abertas em `date_to`) por dimensão: quantidade, idade média/mediana, mais antiga, faixas 1/3/5/7/15 dias. | `date_to` (obrig.); `group_by` (default `regional`); `filters` (opcional). | `{"meta", "data": [{"label", "quantity", "avg_age_days", "median_age_days", "oldest_order_code", "oldest_age_days", "over_1d"…"over_15d"}, ...]}`. |
| `opr_backlog_history` | Série histórica **diária** de backlog (ou backlog atrasado), lida de snapshot 1x/dia. | `date_from`, `date_to` (obrig.); `metric` (obrig.: `backlog`/`backlog_atrasado`); `group_by` (`none`/`regional`/`team_model`/`sector`/`city`, default `none`); `sector_filter` (opcional, um único operador — sem "in"). | Lista `[{"snapshot_date", "quantity", "group", "captured_at"}, ...]`. Snapshot captura na primeira checagem após a virada do dia em `America/Porto_Velho`; `captured_at` (UTC) pode estar até ~1h "atrás" de uma consulta ao vivo. |
| `opr_filter_options` | Lista os valores realmente cadastrados no período (regionais, setores, assuntos, responsáveis, status, etc.), para montar filtro exato com a grafia certa. | `date_from`, `date_to` (obrig.). | JSON com listas de valores por categoria. |
| `opr_warranty_analytics` | Garantia de ativação: Manutenção que abre no mesmo contrato até 30 dias após fechamento de Ativação/Mud. elegível. | `date_from`, `date_to` (obrig.); `period_basis` (`opened`/`closed`, default `opened`); `denominator` (`closed_origins`/`active_origins`/`maintenance_total`/`activation_closed`, default `active_origins`); `origin_excluded_diagnoses` (opcional); `filters` (subconjunto suportado apenas: regional, empresa, estado, cidade, modelo de equipe). | `{"numerator", "denominator_count", "percentage", "contracts_with_warranty", "customers_with_warranty", "breakdown", "items", "items_truncated", "meta"}`. |
| `opr_team_targets` | Metas de equipe (por modelo e tipo de período) vigentes numa data específica — histórico append-only, não a config atual. | `reference_date` (obrig.). | Lista de metas por modelo/tipo de período. |
| `opr_team_target_performance` | Produção realizada (O.S. fechadas) x meta prevista por modelo de equipe, usando a meta vigente em cada período. | `date_from`, `date_to` (obrig.); `granularity` (`day`/`week`/`month`, default `day`); `filters` (opcional). | `{"meta", "data": [{"period_start", "team_model", "actual", "target", "delta", "percentage_of_target"}, ...]}`. |
| `opr_list_fields` | Catálogo dinâmico de campos e capacidades expostos — reflete a política de exposição vigente para quem chama (config administrativa + perfil), não um estado fixo do código. | Sem parâmetros. | Lista de `{"entity", "field", "type", "description", "filterable", "text_filterable", "groupable", "returnable", "selectable", "detail_available", "sensitive", "enabled_for_api", "enabled_for_mcp", "enabled_for_ai"}`. |
| `opr_data_freshness` | Frescor da última importação de O.S. do IXC — checar ANTES de confiar em qualquer análise sensível a "agora". | Sem parâmetros. | `{"last_successful_import_at", "status", "date_from", "date_to", "checked_at", "age_seconds", "has_data"}`. Cobre só a Operação Analítica (IXC), não SGP Suporte nem Agendamento. |
| `opr_coordinate_quality_audit` | Auditoria de qualidade de latitude/longitude por regional — só classifica/conta, não corrige nada. | `entity` (obrig.: `operations_orders`, `operations_login_current_status` ou `operations_onu_signal_current`); `outlier_km` (default 300); `duplicate_threshold` (default 20). | `{"meta", "data": [{"entity", "regional", "total", "validated", "missing", "invalid_range", "zero_zero", "outside_region", "suspicious_duplicates", "valid_coverage_pct"}, ...]}` por regional. |

**Bloco de filtros (`filters`)** — usado por `opr_aggregate_orders`, `opr_orders_timeseries`, `opr_search_orders`,
`opr_backlog_aging`, `opr_warranty_analytics` e `opr_team_target_performance`, validado contra o mesmo schema
`AiOrderFilters` (`extra="forbid"`) usado pela rota HTTP equivalente: filtros exatos em lista
(`team_models`, `companies`, `regionals`, `states`, `cities`, `contract_types`, `person_types`, `os_types`,
`subjects`/`os_subjects`, `diagnoses`, `departments`, `sectors`, `priorities`, `creators`, `responsibles`, `statuses`,
`sla_statuses`, `projects`, `pops`); `regional_groups` (agrupamento adicional de "Regional"); `text_filters`
(`contains`/`starts_with`/`ends_with`/`not_equals` sobre campos como `sector`, `subject`, `city`, `service_description`,
`neighborhood`); `scheduled_after_sla`/`sla_expired_before_schedule` (booleanos); `has_coordinates`;
`near_latitude`/`near_longitude`/`radius_km` (busca por raio); `customer_logins`; e filtros datetime exatos por campo
(`opened_at`, `closed_at`, `deadline_at`, `scheduled_at`, `assumed_at`, `displacement_started_at`,
`execution_started_at`, `finished_at`, `source_updated_at`, cada um com `{"gte"/"gt"/"lte"/"lt"/"eq": ISO8601}`,
aditivos a `date_from`/`date_to`). Chave desconhecida devolve erro apontando o formato correto (achado real: um
cliente MCP tentou `sector`/`sector_contains` antes de acertar `sectors: [...]`). `os_subjects` é o nome canônico
piloto do "FilterContractV1" (`docs/proposta-filter-contract-v1.md`); `subjects` continua funcionando como alias
depreciado, emitindo `DEPRECATED_FILTER_ALIAS` em `meta.warnings`.

**`group_by`** aceita: `regional`, `city`, `neighborhood`, `os_type`, `subject`, `diagnosis`, `department`, `sector`,
`priority`, `responsible`, `status`, `sla_status`, `team_model`, `scheduled_after_sla`, `sla_expired_before_schedule`,
`geo_cluster` (agrupa O.S. de ponto geográfico coincidente, ~111m) — uma dimensão ou lista de até 3, para agrupamento
composto.

Nota sobre `opr_operations_now`: o conjunto de chaves de `filters` aceito aqui é **diferente e mais restrito** do
bloco genérico acima (não inclui `text_filters`, `has_coordinates`, nem o raio geográfico) — declarado à parte de
propósito, pois a camada de consulta desta tool (`_dimension_conditions`) não sabe interpretar esses campos; usá-los
aqui geraria descarte silencioso se reaproveitasse o schema genérico.

### Rede / login / ONU

| Tool | Propósito | Parâmetros principais | Retorno |
|---|---|---|---|
| `opr_login_status` | Status **atual** de conectividade por login (não é evento de queda, é o estado agora e há quanto tempo). | `logins`, `online_statuses` (`S`/`N`/`SS`), `regionals`, `near_latitude`/`near_longitude`/`radius_km` (juntos ou nenhum), `limit` (até 500, default 200). | Lista de `{"login_id", "login", "online", "regional", "latitude", "longitude", "last_connected_at", "last_disconnected_at", "status_changed_at", "captured_at"}`. `status_changed_at` só avança quando `online` muda. |
| `opr_search_logins` | Busca paginada de login (equivalente de `opr_search_orders` para logins). | `logins`/`login_query` (exato/parcial); `login_ids`, `online_statuses`, `regionals`; `pon_ids`, `transmitter_ids`, `contract_ids` (via join com telemetria); busca por raio; filtros datetime (`status_changed_at`, `last_connected_at`, `last_disconnected_at`, `captured_at`); `page`/`page_size` (até 500). | `{"items", "total_encontrado", "page", "page_size", "has_more", "meta"}`. |
| `opr_get_login_detail` | Detalhe completo de um único login: identificação, status com tempo já calculado, telemetria ONU/PON e histórico recente de eventos. | `login` ou `login_id` (ao menos um); `history_hours` (1–168, default 24). | JSON com `seconds_in_current_state`, campos de telemetria e `recent_events`: `[{"event": "connected"\|"disconnected", "at"}, ...]`. |
| `opr_login_aggregate` | Contagem de logins por dimensão (detecção de concentração/incidente coletivo). | `group_by` (obrig.: `regional`, `online`, `transmitter_id`, `pon_id`, `last_drop_cause`); `regionals`, `online_statuses` (opcionais). | `{"meta", "data": [{"label", "quantity", "percentage"}, ...]}`. |
| `opr_login_outages` | Logins offline **agora** que caíram dentro de uma janela — candidatos a incidente coletivo. | `since` (obrig., ISO8601); `until` (default agora); `regionals`; `limit` (até 1000, default 200). | `{"meta", "data": [{"login_id", "login", "regional", "latitude", "longitude", "status_changed_at", "last_disconnected_at"}, ...]}`, mais recente primeiro. |
| `opr_login_timeseries` | Série temporal de conectados/desconectados/quedas novas/reconexões novas. | `since` (obrig.); `until` (default agora). | `{"meta", "data": [{"captured_at", "connected", "disconnected", "new_drops", "new_reconnects", "baseline_available"}, ...]}`. `baseline_available=false` no primeiro ponto (sem captura anterior para comparar). |
| `opr_offline_login_clusters` | Agrupamento geográfico (DBSCAN) de quedas recentes — candidato a rompimento de fibra num trecho. | `radius_meters` (10–5000, default 300); `min_cluster_size` (2–100, default 3); `window_minutes` (5–1440, default 30). | `{"radius_meters", "min_cluster_size", "window_minutes", "clusters": [{"center_latitude", "center_longitude", "radius_meters", "size", "logins": [...]}], "meta"}`. |
| `opr_login_incident_analysis` | Funil de incidente coletivo numa única chamada (quedas, offline, reconexões, breakdown por regional/transmissor/PON/causa, clusters geográficos). Recomendada como primeira chamada ao investigar incidente. | `window_minutes` (5–1440, default 90); `regionals` (não se aplica aos `geo_clusters`); `cluster_radius_meters`, `cluster_min_size`. | `{"window_minutes", "since", "new_drops", "still_offline", "reconnects", "by_regional", "by_transmitter", "by_pon", "by_drop_cause", "geo_clusters", "meta"}`. |
| `opr_onu_signal` | Telemetria óptica/ONU atual (sinal RX/TX em dBm, causa de queda, OLT, PON/slot) dos logins já monitorados. Não cobre toda a base de ONUs do IXC. | `login_ids`, `last_drop_causes`, `transmitter_ids`; `limit` (até 500, default 200). | Com `login_ids`: `{"requested_count", "found_count", "not_found_login_ids", "not_monitored_login_ids", "items"}`. Sem `login_ids`: lista simples de telemetria. |
| `opr_onu_signal_history` | Série histórica de telemetria óptica (um ponto por captura) para um login/serial específico — exige `login_ids` ou `onu_serials`. | `login_ids` ou `onu_serials` (ao menos um); `date_from`/`date_to` (ISO8601, opcionais); `limit` (até 2000, default 500). | Lista ordenada por `captured_at` (mais antigo primeiro). Cobertura parcial por desenho: só há ponto quando o login estava na fila de diagnóstico daquele ciclo. |
| `opr_coordinate_quality_audit` | (ver tabela de Pedidos/O.S. acima — também cobre `operations_login_current_status` e `operations_onu_signal_current`.) | — | — |

### Agendamento

| Tool | Propósito | Parâmetros principais | Retorno |
|---|---|---|---|
| `opr_reschedule_by_technician` | Quantos reagendamentos (evento tipo 10) cada técnico de campo gerou pessoalmente (só técnicos cadastrados em modelo de equipe de campo). | `date_from`, `date_to` (obrig., por data de abertura, máx. 1 ano); `filial_ids`, `setor_ids`, `assunto_ids` (opcionais, IDs do IXC). | `{"date_from", "date_to", "items": [{"technician_id", "technician_name", "reschedule_events"}, ...]}`, do que mais reagendou pro que menos. Exige permissão `scheduling:read`. |
| `opr_reschedule_by_operator` | Quantas ações de reagendamento cada operador de backoffice registrou (agrupa por quem registrou, não pelo técnico responsável). | Mesmos parâmetros de `opr_reschedule_by_technician`. | `{"date_from", "date_to", "items": [{"operator_id", "operator_name", "is_team_member", "reschedule_events"}, ...]}`. Exige `scheduling:read`. |

### Casos de gestão (Gestão Integrada)

Todas exigem `management:read`; visibilidade segue a mesma regra da tela (não-matriz só vê o que gerencia).

| Tool | Propósito | Parâmetros principais | Retorno |
|---|---|---|---|
| `opr_management_cases` | Lista paginada dos casos de gestão (desvio formal cobrado da matriz). | `status`, `severity`, `regional`, `case_type`, `reference_year`/`reference_month`, `only_overdue`, `only_open`, `search`, `supervisor_user_id`, `responsible_name`, `collaborator_id`, `reference_date_from`/`to`, `reason_id`, `pending_justification`, `awaiting_review`, `has_justification`, `min_days_pending`, `page`/`page_size` (máx. 200). | `{"total", "page", "page_size", "summary", "items": [{status, severity, responsible_name, regional, metric_name, expected_value, actual_value, deviation_value, is_overdue, justification_text, action_plan, reviewed_by, ...}, ...]}`. |
| `opr_management_cases_diagnostics` | Diagnóstico agregado ("quem mais não bate meta, por regional/colaborador/motivo"). | Mesmos filtros de `opr_management_cases` (sem paginação). | `{"total_cases", "by_regional", "by_responsible", "by_reason"}`, cada item `{key, label, total, open_cases, overdue_cases}` (até 15 por dimensão). |
| `opr_management_pending_justifications` | Fila de cobrança: "quem está devendo justificativa", uma linha por colaborador x regional, já ordenada por prioridade. | Filtros similares + `only_open` (default `true`), `limit` (1–1000, default 200). | `{"total_collaborators", "total_cases", "truncated", "items": [{responsible_name, regional, supervisor_name, team_model_name, total_cases, open_cases, pending_cases, justified_cases, overdue_cases, oldest_pending_date, max_days_pending, open_case_ids, ...}, ...]}`. |
| `opr_management_justifications` | Leitura enxuta do texto das justificativas, motivo, plano de ação e decisão da matriz. | Filtros similares + `include_comments` (default `false`), `page`/`page_size` (máx. 1000 - volume total do sistema nunca passou de alguns milhares). | `{"total", "page", "page_size", "items": [{case_id, reference_date, regional, responsible_name, status, justification_text, action_plan, justified_at, reviewed_at, reviewer_name, comment_count, comments}, ...]}`. |

Vocabulário de status comum às três: `pending` (cobrado, sem justificativa), `justified` (justificado, aguardando
matriz), `in_progress`, `resolved`, `rejected`.

### Suporte / OPA (SGP Suporte)

Todas exigem `support:read`, sem escopo por regional. Período máximo de **32 dias** por chamada, dia local
**America/Porto_Velho**.

| Tool | Propósito | Parâmetros principais | Retorno |
|---|---|---|---|
| `opr_support_overview` | Indicadores consolidados (TMA, TMR, comparação automática com período anterior de mesma duração) — mesmo cálculo dos cards da tela `/suporte`. | `date_from`, `date_to` (obrig., máx. 32 dias); `date_basis` (`opened_at`/`closed_at`, default `opened_at`); `support_filters` (opcional). | Campos de comparação como `{"current", "previous", "absolute_change", "percentage_change"}` para `total_attendances`, `closure_rate`, `average_duration_seconds` (TMA), `average_tmr_seconds`, `average_rating`, etc. Sem comparação: `by_channel`, `by_status`, `top_reasons`, `bot_human`. Tempos sempre em segundos; média `null` = sem base para calcular (não é zero). |
| `opr_support_breakdowns` | Agrupa indicadores por dimensão (quem/qual mais atendeu, com que TMA e nota). | `dimension` (obrig.: `attendant`, `department`, `reason`, `channel`, `status`, `customer`); `date_from`/`date_to` (opcionais aqui); `date_basis`; `sort_by` (`label`/`total`/`closed`/`open`/`closure_rate`/`avg_duration_seconds`/`avg_rating`/`rating_count`/`share_percentage`); `sort_dir`; `limit` (1–200, default 20); `support_filters`. | `{"dimension", "total", "limit", "items": [{id, label, total, closed, open, closure_rate, avg_duration_seconds, avg_rating, share_percentage, ...}]}`. `label` "Não identificado" = origem não informou nome. |
| `opr_support_timeseries` | Decomposição diária do mesmo recorte de `opr_support_overview` (só granularidade diária). | `date_from`, `date_to` (obrig.); `date_basis`; `support_filters`. | `{"date_basis", "date_from", "date_to", "points": [{day, total, closed, open, average_duration_seconds, average_tmr_seconds, average_rating, tmr_all_responses_coverage}, ...]}`. Dias sem atendimento: total/closed/open=0 (de propósito), médias `null`. |

`support_filters` aceita: `status`, `channel`, `attendant_id`/`department_id`/`reason_id`/`customer_id`/`tag_id`
(múltiplos IDs por vírgula, OU entre eles), `attendant`/`department`/`reason` (nome exato), `protocol`, `customer`,
`search`, `rating_min`/`rating_max` (0–5), `bot_human` (`with_bot`/`without_bot`/`reached_human`/`bot_only`/
`handoff`/`unclassified` — os classificados excluem os não classificados dos dois lados). `date_from`/`date_to`/
`date_basis` são parâmetros próprios da tool, não vão dentro de `support_filters`.

### IXC (Atendimento `su_ticket`)

Exigem `support:read`.

| Tool | Propósito | Parâmetros principais | Retorno |
|---|---|---|---|
| `opr_ixc_brief` | Resumo do estado atual do Atendimento IXC — indicador ANTECIPADO de incidente (não substitui a O.S.). Primeira chamada recomendada de qualquer análise sobre esse indicador. Consolidado em 2026-09-17 (correção da auditoria): não exige mais chamadas separadas pra drivers/conversão em O.S. | `regional` (opcional; omitido = operação inteira). | `{generated_at, context_key, period, scope, status, severity_basis (historical\|peers\|insufficient_data), ticket_count, expected, deviation_pct, peers_deviation_pct, effective_deviation_pct, tickets_per_1000_contracts, top_driver, drivers (top 5), geographic_concentration, reach, momentum, bursts, os_conversion, reason_codes, drill}`. `reason_codes` é lista de OBJETOS com os números que sustentam cada código (ex.: `{"code":"BURST_ACTIVE","window":"2h","current":34,"expected":10,"ratio":3.4}`), não strings soltas. `context_key` é decodificável em `GET /support/ixc/analytics/context/{context_key}(/tickets)` — mesmo agrupamento, sem reconstruir filtros. |
| `opr_ixc_signals` | Lista as regionais com algum sinal disparado agora (severidade crítica/em melhora — por histórico OU por pares —, tendência sustentada, pico intra-dia ativo) — regional "na curva" não aparece. | Sem parâmetros. | `{"signals": [{context_key, scope, severity, severity_basis, ticket_count, expected, deviation_pct, effective_deviation_pct, tickets_per_1000_contracts, top_driver, drivers, geographic_concentration, reach, momentum_trend, consecutive_days_above_expected, burst_active, reason_codes, drill}]}`, ordenado por severidade e magnitude. `reason_codes` traz os números de cada código no mesmo item (ver `opr_ixc_brief`), sem texto narrativo. |

### Cockpit / UNI Intelligence

| Tool | Propósito | Parâmetros principais | Retorno |
|---|---|---|---|
| `opr_get_cockpit_context` | Contexto operacional completo de um profile do cockpit numa única chamada, pensado para uma análise periódica decidir se vale publicar um novo insight. Reusa o MESMO cálculo da TV (nenhum número recalculado). Exige `intelligence:read`. | `profile_key` (obrig., ex.: `"uni-geral"`, `"machadinho-operacional"`, `"executivo-uni"`). | JSON com `profile`, `scope`, `generated_at`, `overall_status`, `production`, `backlog`, `sla`, `alerts`, `incidents`, `content`, `monitor_health`, `data_freshness`, `meta`, e `last_ai_insight` (para decidir se algo relevante mudou antes de publicar de novo). |
| `opr_publish_cockpit_content` | **Única tool de escrita** de todo o conector — publica conteúdo no cockpit (insight de IA, comunicado, aviso). Não altera alertas, não fecha O.S., não mexe em agenda/rede. Exige `intelligence:publish`. | `content_type` (obrig.: `AI_INSIGHT`, `MANUAL_MESSAGE`, `ANNOUNCEMENT`, `OPERATIONAL_PRIORITY`, `INCIDENT_UPDATE`, `MAINTENANCE_NOTICE`, `INFO`); `title` (até 200 car.); `body` (até 4000 car.); `profile_key` (opcional, `None` = global); `scope` (opcional, ex. `{"regional": "..."}`); `severity` (`LOW`/`MEDIUM`/`HIGH`/`CRITICAL`/`INFO`, default `INFO`); `evidence` (opcional); `confidence` (0.0–1.0, opcional); `valid_until` (ISO8601, opcional). | JSON com o conteúdo publicado: `{id, content_type, profile_key, severity, title, status, source_type, source_key, author_user_id, valid_until, created_at}`. `source_type` sempre `"MCP"`, `source_key` sempre `"mcp:{email do autor}"` — origem nunca anônima. |

## Exemplos de uso

### `opr_aggregate_orders` — backlog atual por regional

Requisição (parâmetros da tool):
```json
{
  "date_from": "2026-08-01",
  "date_to": "2026-08-31",
  "group_by": "regional",
  "metric": "quantidade_backlog",
  "filters": {
    "team_models": ["TECNICO 12/36H"]
  }
}
```

Resposta esperada (formato real, valores ilustrativos):
```json
{
  "meta": {
    "applied_filters": {"team_models": ["TECNICO 12/36H"]},
    "warnings": []
  },
  "data": [
    {"label": "UNI - JI PARANA", "quantity": 184, "metric_value": 184.0, "percentage": 22.4},
    {"label": "UNI - ROLIM DE MOURA", "quantity": 121, "metric_value": 121.0, "percentage": 14.7}
  ]
}
```

### `opr_search_orders` — O.S. fechadas no período, campos reduzidos

```json
{
  "date_from": "2026-09-01",
  "date_to": "2026-09-15",
  "date_field": "closed_at",
  "page": 1,
  "page_size": 50,
  "response_mode": "summary",
  "filters": {
    "regionals": ["UNI - MACHADINHO DOESTE"],
    "sla_statuses": ["dentro_prazo"]
  }
}
```

Resposta esperada:
```json
{
  "items": [
    {
      "order_code": "IXC-482913",
      "regional": "UNI - MACHADINHO DOESTE",
      "subject": "Manutenção",
      "status": "Finalizada",
      "sla_status": "dentro_prazo",
      "closed_at": "2026-09-05T14:22:10-04:00"
    }
  ],
  "total_encontrado": 37,
  "page": 1,
  "page_size": 50,
  "has_more": false,
  "meta": {"applied_filters": {"...": "..."}, "warnings": []}
}
```

### `opr_get_cockpit_context` — contexto para decidir se publica um insight

```json
{
  "profile_key": "uni-geral"
}
```

Resposta esperada (estrutura confirmada pela docstring; valores ilustrativos):
```json
{
  "profile": "uni-geral",
  "scope": {},
  "generated_at": "2026-09-16T09:00:00-04:00",
  "overall_status": "ATENCAO",
  "production": {"opened_7d": 812, "closed_7d": 790, "balance_7d": 22},
  "backlog": {"total": 1043, "aging": {"over_7d": 96}},
  "sla": {"current": 0.87, "target": 0.9, "critical_regionals": ["UNI - SAO FELIPE DOESTE"]},
  "alerts": [],
  "incidents": [],
  "content": [],
  "monitor_health": {},
  "data_freshness": {"age_seconds": 340},
  "meta": {"coverage": {}, "warnings": [], "applied_filters": {}},
  "last_ai_insight": null
}
```

Em seguida, se algo relevante tiver mudado, o consumidor chamaria `opr_publish_cockpit_content` com
`content_type="AI_INSIGHT"`, `profile_key="uni-geral"` e o texto da análise.

## Notas de contrato

- **Timezone operacional**: `America/Porto_Velho` (UTC-4, sem horário de verão) é o fuso usado para "dia local" em
  `opr_support_overview`/`opr_support_breakdowns`/`opr_support_timeseries` (SGP Suporte) e no snapshot diário de
  `opr_backlog_history` ("primeira checagem após a virada do dia"). Datas simples (`AAAA-MM-DD`) em filtros de O.S.
  são interpretadas nesse fuso pelas funções de `ai.queries` subjacentes.
- **Datas inclusivas**: todos os pares `date_from`/`date_to` documentados no código são explicitamente inclusivos
  nas duas pontas (confirmado nas docstrings de `opr_support_overview`, `opr_management_*`, `opr_backlog_aging`,
  etc.).
- **Filtros datetime exatos são aditivos, não substitutos**: campos como `opened_at`/`closed_at` dentro de `filters`
  (com operadores `gte`/`gt`/`lte`/`lt`/`eq`) complementam `date_from`/`date_to` (que continuam obrigatórios, em
  granularidade de dia) — não os substituem.
- **`opr_search_orders` sem `date_field`**: uma O.S. entra no resultado se teve qualquer atividade no período (abriu
  OU fechou dentro do intervalo — união, não interseção). Para um marco único, passar `date_field` explicitamente.
- **Serialização de datas**: a maioria das tools usa `_dump` (equivalente a `str(datetime)`, formato
  `"AAAA-MM-DD HH:MM:SS"`, **sem** "T"); as tools mais novas (marcadas no código como "precisam bater campo a campo
  com a rota HTTP equivalente") usam `_dump_iso`, que produz ISO 8601 real (`"AAAA-MM-DDTHH:MM:SS"`). O próprio
  código documenta essa divergência como um achado de paridade MCP x HTTP (2026-09-10) e afirma que a mudança para
  um formato único em todas as tools é uma decisão de compatibilidade ainda pendente — um consumidor externo deve
  tratar ambos os formatos como possíveis, dependendo da tool.
- **Chave de filtro desconhecida sempre gera erro**, nunca é silenciosamente descartada — comportamento
  intencional e recorrente em todo o arquivo (documentado como resposta a mais de um incidente real de
  "filtro não funciona" sem erro nenhum).
- **Escopo regional do usuário sempre se aplica**: nenhuma tool amplia o acesso do usuário autenticado além do que
  ele já veria nas telas equivalentes (`effective_managed_regionals`, visibilidade de casos de gestão, etc.). Um
  consumidor de integração deve estar ciente de que os dados retornados dependem da conta usada para autorizar a
  conexão OAuth — não é uma visão "global" garantida.
- **Escrita**: de todo o catálogo, **apenas `opr_publish_cockpit_content`** grava dado. Todas as demais 37 tools são
  somente leitura (`readOnlyHint: True` nas suas `annotations`).
