# Documentação de API — Gamificação UNI OPR

Documento único consolidando a referência completa de API do backend: 374 endpoints REST
distribuídos em 9 módulos + as 38 ferramentas do conector MCP (`opr_*`) usado por
integrações externas (ex.: time do Portal de Resultados). Gerado em 2026-09-16 lendo
diretamente o código-fonte (routers/schemas) de cada módulo — ver `docs/STATUS.md` para
o registro da frente e achados de código sinalizados durante a documentação.

Os arquivos individuais por módulo continuam existindo em `docs/` (`api-*.md`) caso
seja mais prático consultar um módulo isolado; este documento é a versão consolidada.

## Sumário

- [MCP Connector (opr_*)](#mcp-connector)
- [Operação Analítica](#operacao-analitica)
- [Gamificação Operacional](#gamificacao)
- [SGP Suporte](#suporte)
- [Gestão Integrada](#gestao)
- [Agendamento](#agendamento)
- [Administração + AI Governance](#admin)
- [Agente de IA](#ai)
- [UNI Intelligence](#intelligence)
- [UNI Localiza](#localiza)

---

<a id="mcp-connector"></a>

## MCP Connector (opr_*)


> Fonte: `backend/app/modules/mcp_connector/server.py` (servidor MCP remoto), `backend/app/modules/mcp_connector/router.py`
> (tela de login/consentimento), `backend/app/modules/mcp_connector/provider.py` (OAuth) e `backend/app/main.py` (montagem).
> Este documento descreve o contrato tal como implementado no código nesta branch — não inclui nada que não tenha
> sido confirmado lendo a fonte.

### Visão geral

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

### Autenticação

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

### Catálogo de ferramentas

Convenções gerais observadas no código:
- Datas simples usam o formato `AAAA-MM-DD`; datetimes exatos usam ISO 8601 com offset (ex.:
  `"2026-08-15T17:30:00-04:00"`), aceitando qualquer timezone de entrada.
- Toda resposta é uma string JSON (`_dump`/`_dump_iso` — `json.dumps(..., ensure_ascii=False, default=str/iso)`).
- Filtro com chave desconhecida **sempre gera erro explícito**, nunca é ignorado em silêncio — padrão repetido em
  praticamente todas as tools, resultado de "achados reais" documentados no próprio código (filtros descartados
  silenciosamente já causaram investigação de bug em produção).
- Todas as tools são `readOnlyHint: True` exceto `opr_publish_cockpit_content` (`readOnlyHint: False`).

#### Pedidos/O.S. e analytics

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

#### Rede / login / ONU

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

#### Agendamento

| Tool | Propósito | Parâmetros principais | Retorno |
|---|---|---|---|
| `opr_reschedule_by_technician` | Quantos reagendamentos (evento tipo 10) cada técnico de campo gerou pessoalmente (só técnicos cadastrados em modelo de equipe de campo). | `date_from`, `date_to` (obrig., por data de abertura, máx. 1 ano); `filial_ids`, `setor_ids`, `assunto_ids` (opcionais, IDs do IXC). | `{"date_from", "date_to", "items": [{"technician_id", "technician_name", "reschedule_events"}, ...]}`, do que mais reagendou pro que menos. Exige permissão `scheduling:read`. |
| `opr_reschedule_by_operator` | Quantas ações de reagendamento cada operador de backoffice registrou (agrupa por quem registrou, não pelo técnico responsável). | Mesmos parâmetros de `opr_reschedule_by_technician`. | `{"date_from", "date_to", "items": [{"operator_id", "operator_name", "is_team_member", "reschedule_events"}, ...]}`. Exige `scheduling:read`. |

#### Casos de gestão (Gestão Integrada)

Todas exigem `management:read`; visibilidade segue a mesma regra da tela (não-matriz só vê o que gerencia).

| Tool | Propósito | Parâmetros principais | Retorno |
|---|---|---|---|
| `opr_management_cases` | Lista paginada dos casos de gestão (desvio formal cobrado da matriz). | `status`, `severity`, `regional`, `case_type`, `reference_year`/`reference_month`, `only_overdue`, `only_open`, `search`, `supervisor_user_id`, `responsible_name`, `collaborator_id`, `reference_date_from`/`to`, `reason_id`, `pending_justification`, `awaiting_review`, `has_justification`, `min_days_pending`, `page`/`page_size` (máx. 200). | `{"total", "page", "page_size", "summary", "items": [{status, severity, responsible_name, regional, metric_name, expected_value, actual_value, deviation_value, is_overdue, justification_text, action_plan, reviewed_by, ...}, ...]}`. |
| `opr_management_cases_diagnostics` | Diagnóstico agregado ("quem mais não bate meta, por regional/colaborador/motivo"). | Mesmos filtros de `opr_management_cases` (sem paginação). | `{"total_cases", "by_regional", "by_responsible", "by_reason"}`, cada item `{key, label, total, open_cases, overdue_cases}` (até 15 por dimensão). |
| `opr_management_pending_justifications` | Fila de cobrança: "quem está devendo justificativa", uma linha por colaborador x regional, já ordenada por prioridade. | Filtros similares + `only_open` (default `true`), `limit` (1–1000, default 200). | `{"total_collaborators", "total_cases", "truncated", "items": [{responsible_name, regional, supervisor_name, team_model_name, total_cases, open_cases, pending_cases, justified_cases, overdue_cases, oldest_pending_date, max_days_pending, open_case_ids, ...}, ...]}`. |
| `opr_management_justifications` | Leitura enxuta do texto das justificativas, motivo, plano de ação e decisão da matriz. | Filtros similares + `include_comments` (default `false`), `page`/`page_size` (máx. 200). | `{"total", "page", "page_size", "items": [{case_id, reference_date, regional, responsible_name, status, justification_text, action_plan, justified_at, reviewed_at, reviewer_name, comment_count, comments}, ...]}`. |

Vocabulário de status comum às três: `pending` (cobrado, sem justificativa), `justified` (justificado, aguardando
matriz), `in_progress`, `resolved`, `rejected`.

#### Suporte / OPA (SGP Suporte)

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

#### IXC (Atendimento `su_ticket`)

Exigem `support:read`.

| Tool | Propósito | Parâmetros principais | Retorno |
|---|---|---|---|
| `opr_ixc_brief` | Resumo do estado atual do Atendimento IXC — indicador ANTECIPADO de incidente (não substitui a O.S.). Primeira chamada recomendada de qualquer análise sobre esse indicador. | `regional` (opcional; omitido = operação inteira). | `{generated_at, period, scope, status (critico/dentro_da_curva/em_melhora/sem_dado), ticket_count, deviation_pct, top_driver, reach, momentum, bursts}`. `deviation_pct`/`bursts` `null` quando não há amostra suficiente. |
| `opr_ixc_signals` | Lista as regionais com algum sinal disparado agora (severidade crítica, tendência sustentada, pico intra-dia ativo) — regional "na curva" não aparece. | Sem parâmetros. | `{"signals": [{scope, severity, deviation_pct, top_driver, momentum_trend, consecutive_days_above_expected, burst_active, reason_codes}]}`, ordenado por severidade e magnitude. `reason_codes` são códigos estáveis (ex.: `HIGH_DEVIATION`), sem texto narrativo. |

#### Cockpit / UNI Intelligence

| Tool | Propósito | Parâmetros principais | Retorno |
|---|---|---|---|
| `opr_get_cockpit_context` | Contexto operacional completo de um profile do cockpit numa única chamada, pensado para uma análise periódica decidir se vale publicar um novo insight. Reusa o MESMO cálculo da TV (nenhum número recalculado). Exige `intelligence:read`. | `profile_key` (obrig., ex.: `"uni-geral"`, `"machadinho-operacional"`, `"executivo-uni"`). | JSON com `profile`, `scope`, `generated_at`, `overall_status`, `production`, `backlog`, `sla`, `alerts`, `incidents`, `content`, `monitor_health`, `data_freshness`, `meta`, e `last_ai_insight` (para decidir se algo relevante mudou antes de publicar de novo). |
| `opr_publish_cockpit_content` | **Única tool de escrita** de todo o conector — publica conteúdo no cockpit (insight de IA, comunicado, aviso). Não altera alertas, não fecha O.S., não mexe em agenda/rede. Exige `intelligence:publish`. | `content_type` (obrig.: `AI_INSIGHT`, `MANUAL_MESSAGE`, `ANNOUNCEMENT`, `OPERATIONAL_PRIORITY`, `INCIDENT_UPDATE`, `MAINTENANCE_NOTICE`, `INFO`); `title` (até 200 car.); `body` (até 4000 car.); `profile_key` (opcional, `None` = global); `scope` (opcional, ex. `{"regional": "..."}`); `severity` (`LOW`/`MEDIUM`/`HIGH`/`CRITICAL`/`INFO`, default `INFO`); `evidence` (opcional); `confidence` (0.0–1.0, opcional); `valid_until` (ISO8601, opcional). | JSON com o conteúdo publicado: `{id, content_type, profile_key, severity, title, status, source_type, source_key, author_user_id, valid_until, created_at}`. `source_type` sempre `"MCP"`, `source_key` sempre `"mcp:{email do autor}"` — origem nunca anônima. |

### Exemplos de uso

#### `opr_aggregate_orders` — backlog atual por regional

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

#### `opr_search_orders` — O.S. fechadas no período, campos reduzidos

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

#### `opr_get_cockpit_context` — contexto para decidir se publica um insight

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

### Notas de contrato

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

---

<a id="operacao-analitica"></a>

## Operação Analítica


### Visão geral

O módulo Operação Analítica importa Ordens de Serviço (O.S.) da API do IXC, projeta esses
dados nas tabelas `operations_*` e calcula, em cima dessa projeção, os indicadores de SLA,
backlog, garantia e produtividade que alimentam a tela `/operacao`. Além das O.S., o módulo
também captura e expõe telemetria de rede (status de login/conexão e sinal óptico de ONU),
usada tanto pela tela quanto por consumidores de IA/MCP para investigação de incidentes de
rede.

Todas as rotas deste documento vivem sob o prefixo `/api/operations` (roteador FastAPI
montado com `prefix="/operations"` dentro do app, que já responde em `/api`).

### Autenticação e permissões

Toda rota do roteador exige sessão autenticada por padrão: o `APIRouter` é criado com
`dependencies=[Depends(require_permission("operations:read"))]`, ou seja, `operations:read`
é o piso mínimo de acesso ao módulo inteiro. A maioria das rotas de leitura não pede nada
além disso; endpoints mais sensíveis (dado de prazo, backlog, detalhe de O.S., importação,
administração de cadastro) declaram uma permissão adicional explícita via
`Depends(require_permission("..."))` ou no parâmetro `dependencies=[...]` do decorator.

Permissões distintas encontradas no router:

- `operations:read` — piso de acesso a todo o módulo (aplicado a todas as rotas).
- `operations:view_sla` — indicadores de SLA/prazo (`/sla*`, coluna de SLA da matriz regional).
- `operations:view_backlog` — backlog em aberto (`/in-progress*`).
- `operations:view_warranty` — analítico de garantia (`/warranty`).
- `operations:view_calendar` — calendário mensal e seus detalhamentos (`/calendar*`).
- `operations:view_order_details` — detalhe de O.S. individual e listagens de O.S.
  (`/orders*`, `/openings/orders`, `/calendar/orders`, `/calendar/*-detail`,
  `/in-progress/orders`) — em várias rotas é exigida em conjunto com outra permissão
  (ex.: `view_calendar` + `view_order_details`).
- `operations:view_openings` — analítico de aberturas (`/openings/analytics`,
  `/openings/orders`).
- `operations:sync_ixc` — disparar/consultar importação do IXC e configurar a sincronização
  automática (`/imports*`, `/ixc-sync-settings*`, `/responsible-directory/sync`).
- `operations:manage_team_models` — administrar modelos de equipe, capacidade por filial,
  diretório de responsáveis e o import/export de configuração (`/team-models*`,
  `/branch-capacity*`, `/responsible-directory`, `/configuration-json`).
- `operations:manage_own_team_members` — variante restrita: supervisor só reatribui o modelo
  de equipe dos colaboradores em que ele mesmo é o supervisor cadastrado (nunca cria/edita/
  exclui modelo, nunca vê colaborador alheio). Usada junto com `manage_team_models` para
  compor o escopo `full`/`own` de `/team-configuration` e `PUT /team-members`.
- `operations:manage_subjects` — classificação assunto → tipo de O.S. (`/subject-type-
  mappings`).
- `operations:manage_filters` — criar/editar/excluir visão salva **pessoal**
  (`/saved-filters*`).
- `operations:views:read_global`, `operations:views:create_global`,
  `operations:views:update_global`, `operations:views:delete_global` — administrar visões
  salvas **globais** (visíveis para todos) e o filtro/lista de filtros padrão da Visão Geral
  executiva. São checadas dinamicamente por ação (`_ensure_global_saved_filter_permission`),
  não como uma dependency fixa.

Algumas rotas de rede/telemetria (`/network/logins`, `/network/onu-signal*`, `/network/logins/
search`, `/network/login-detail`, `/network/login-aggregate`, `/network/login-outages`,
`/network/login-timeseries`, `/network/login-incident-analysis`, `/network/coordinate-
quality`, `/orders`, `/orders/{source_order_id}`) passam adicionalmente por
`enforce_ai_endpoint_for_user` (módulo `ai_governance`), que aplica a política de campos e
filtros liberados por perfil quando o acesso é tratado como acesso de dado sensível/IA —
mesmo quando chamadas pela própria tela web (origem `"api"`), e registra o acesso em auditoria
(`record_ai_access`) nas rotas de listagem/detalhe de O.S.

### Endpoints

#### Período e metadados
- `GET /period` — sessão autenticada (`operations:read`). Sem parâmetros. Devolve o intervalo
  permitido de datas (ano operacional corrente, de 1º de janeiro até hoje no fuso
  `America/Porto_Velho`), um período padrão (mês corrente) e o nome do fuso.
- `GET /data-freshness` — sessão autenticada. Devolve o horário da última importação/
  sincronização bem-sucedida por fonte (usado para o indicador de frescor de dado da tela).

#### Importação e sincronização com o IXC
- `GET /ixc-sync-settings` — `operations:sync_ixc`. Devolve a configuração atual da
  sincronização automática: liga/desliga, intervalo em minutos, intervalo da varredura de
  backlog aberto, janela de retroação em dias, setores IXC escopados, e os intervalos/estado
  da captura de status de login e de sinal ONU.
- `PUT /ixc-sync-settings` — `operations:sync_ixc`. Body `OperationIxcSyncSettingsUpdate`
  (todos os campos opcionais, só os enviados são alterados). Persiste em `app_settings`,
  recalcula o próximo horário permitido quando o intervalo muda, e grava log de auditoria.
- `POST /imports` — `operations:sync_ixc`. Body `{date_from, date_to, sector_ids}`. Importa um
  único dia por vez (`date_from` deve ser igual a `date_to` — a interface divide o período em
  chamadas diárias). Retorna contadores de importação (`OperationImportResult`). Erros da API
  do IXC viram 502, limite de consulta vira 422, conflito de execução concorrente vira 409.
- `POST /imports/backfill` — `operations:sync_ixc`. Body igual ao de `/imports`, mas aceita
  um intervalo maior: cria um job assíncrono (`OperationBackfillJobOut`) e dispara a
  reimportação histórica em `BackgroundTasks`.
- `GET /imports/backfill/{job_id}` — `operations:sync_ixc`. Status/progresso do job de
  backfill (404 se não existir).
- `POST /imports/open-backlog` — `operations:sync_ixc`. Query `sector_ids` (repetível). Cria e
  dispara em background uma varredura específica do backlog ainda aberto no IXC (não limitada
  à janela de data do backfill comum).
- `GET /imports/open-backlog/{job_id}` — `operations:sync_ixc`. Status desse job.
- `POST /responsible-directory/sync` — `operations:sync_ixc` **e** `operations:
  manage_team_models` (checagem dupla: a permissão da dependency mais uma checagem manual no
  corpo da função). Importa `funcionarios` do IXC para o cadastro interno de colaboradores
  (`OperationIxcCollaborator`), marcando como inativo quem saiu de cena na base de origem.

#### Visão Geral / Overview
- `GET /overview` — sessão autenticada. Query `date_from`, `date_to` + filtros comuns
  (`selected_filters`, ver seção de contrato de filtros). Retorna `OperationOverview`:
  abertas, concluídas, em aberto, fora do prazo, taxa de SLA, médias diárias de abertura/
  conclusão e tempos médios de fechamento/deslocamento/ciclo.
- `GET /overview/default-filter` — sessão autenticada. Devolve o filtro pré-setado global da
  Visão Geral (`available=false` quando nenhum foi definido).
- `PUT /overview/default-filter` — `operations:views:update_global`. Body
  `{filters, support_filters}` (envie `filters: null` para limpar). Persiste um blob próprio
  em `app_settings` (não é mais uma referência a uma visão salva).
- `GET /overview/visible-filters` — sessão autenticada. Lista quais filtros a barra da Visão
  Geral deve exibir, a partir de um catálogo fixo (`team_models`, `regional_groups`,
  `sectors`, `os_types`, `responsibles` do lado de O.S.; `support_department`,
  `support_channel`, `support_reason` do SGP Suporte).
- `PUT /overview/visible-filters` — `operations:views:update_global`. Body `{filters: [...]}`
  com chaves do catálogo; lista vazia volta ao padrão (os 5 filtros de O.S.); chave desconhecida
  é 422.
- `GET /overview/regional-matrix` — sessão autenticada. Quadro por regional com abertas,
  backlog, backlog vencido, concluídas e (se o usuário tiver `operations:view_sla`) taxa de
  SLA — sem a permissão, as colunas de prazo voltam em branco em vez da tabela inteira ser
  negada.
- `GET /overview/collaborator-production` — sessão autenticada (só `operations:read`, sem
  `view_sla`). Concluídas por responsável no recorte atual — drill do donut de modelo de
  equipe.
- `GET /capacity-summary` — sessão autenticada. Resumo de capacidade por filial no período
  (comparação contra a meta cadastrada em `branch-capacity`).
- `GET /branch-capacity` — `operations:manage_team_models`. Lista a capacidade cadastrada por
  filial.
- `PUT /branch-capacity/{regional}` — `operations:manage_team_models`. Atualiza a capacidade
  de uma filial.
- `GET /overview/work-schedule` — sessão autenticada. Query `date_from`, `date_to`,
  `model_ids` (repetível, limitado) + filtros comuns. Classifica conclusões dentro/fora da
  jornada configurada por modelo de equipe.
- `GET /overview/trends` — sessão autenticada. Query `granularity` (`day`/`week`/`month`).
  Série temporal de abertas/concluídas/SLA por período.
- `GET /overview/backlog-trend` — sessão autenticada. Série diária do estoque de backlog.
- `GET /overview/volume-alerts` — sessão autenticada. Compara o backlog atual por assunto
  contra a média recente (z-score) e classifica em `normal`/`attention`/`critical`/
  `insufficient`.
- `GET /overview/control-tower` — sessão autenticada. Query `level`
  (`subject`/`regional`/`city`/`sector`/`responsible`) + `parent_*` para drill hierárquico
  (cada nível exige que todo o caminho pai tenha sido informado). Visão executiva "torre de
  controle" com resumo e itens do nível pedido.

#### Aberturas (Openings)
- `GET /openings/analytics` — `operations:view_openings`. Query `granularity`. Analítico de
  aberturas: série temporal, heatmap (dia da semana × hora), ranking, aging e insights.
- `GET /openings/orders` — `operations:view_openings` **e** `operations:view_order_details`.
  Página de O.S. abertas no período, com filtros adicionais de `aging_bucket`, `weekday` e
  `hour`.

#### SLA
- `GET /sla` — `operations:view_sla`. Query `group_by`
  (`os_type`/`subject`/`diagnosis`/`department`/`sector`). Lista `OperationSlaItem` por grupo:
  concluídas, no prazo/fora do prazo, taxa de SLA, faixas de tempo de fechamento (até 12h,
  12–24h, 24–48h, 48–72h, acima de 72h) e média de horas de fechamento.
- `GET /sla/hierarchy` — `operations:view_sla`. Query `level`
  (`os_type`/`subject`/`diagnosis`) + `parent_os_type`/`parent_subject` para drill (exige o
  pai do nível acima ao filtrar um nível mais fundo). Mesmas métricas de `/sla`, em forma de
  hierarquia navegável, com uma linha de total.
- `GET /sla/collaborators` — `operations:view_sla`. SLA por colaborador: concluídas, taxa de
  SLA, dias ativos, média diária, tempo de execução mínimo/médio/máximo, contagem por tipo de
  O.S. e aderência a agendamento.

#### Garantia
- `GET /warranty` — `operations:view_warranty`. Query `period_basis` (`opened`/`closed`),
  `denominator` (`closed_origins`/`active_origins`/`maintenance_total`/`activation_closed`) e
  `origin_excluded_diagnoses`. Analítico de retorno em garantia: taxa por origem, ranking
  regional e por tipo de origem.

#### Calendário
- `GET /calendar` — `operations:view_calendar`. Query `group_by` (`regional`/`collaborator`).
  Grade mensal com desempenho diário/mensal por regional ou colaborador (classificado contra
  as faixas do modelo de equipe), já considerando escala alternada (12x36) importada de
  `management`.
- `GET /calendar/orders` — `operations:view_calendar` + `operations:view_order_details`.
  Página de O.S. de um `day`/`regional`/`responsible` específico do calendário.
- `GET /calendar/day-detail` — mesmas permissões. Detalhe de um dia (métricas +
  página de O.S.), com `reference_regional` opcional para desambiguar colaborador que atendeu
  mais de uma regional.
- `GET /calendar/week-detail` — mesmas permissões. Mesmo detalhe agregado por semana
  (`date_from`/`date_to`).
- `GET /calendar/month-detail` — mesmas permissões. Mesmo detalhe agregado pelo mês inteiro.

#### Backlog (em aberto)
- `GET /in-progress` — `operations:view_backlog`. Query `group_by`
  (`regional`/`city`/`os_type`/`subject`/`status`). Quebra do backlog atual (quantidade +
  percentual).
- `GET /in-progress/sla-risk` — `operations:view_backlog`. Backlog quebrado por risco de SLA
  (`breached`/`critical`/`attention`/`on_track`/`no_target`).
- `GET /in-progress/orders` — `operations:view_backlog` + `operations:view_order_details`.
  Página paginada/ordenável do backlog, com filtro opcional `sla_risk`.

#### Telemetria de rede (login/ONU)
- `GET /network/offline-login-clusters` — sessão autenticada. Agrupa logins que caíram
  recentemente (`window_minutes`) e estão geograficamente próximos (`radius_meters`,
  `min_cluster_size`) — candidato a rompimento de fibra num trecho, não uma queda isolada.
- `GET /network/logins` — sessão autenticada + gate de IA por campo filtrado. Consulta
  individual de status de conectividade por login/regional/status online, com busca
  geográfica opcional (`near_latitude`/`near_longitude`/`radius_km`, os três juntos ou
  nenhum).
- `GET /network/onu-signal` — sessão autenticada + gate de IA. Telemetria óptica atual
  (sinal RX/TX, serial da ONU, causa da última queda) só dos logins já monitorados (não varre
  a base inteira de ONUs do IXC).
- `GET /network/onu-signal/history` — sessão autenticada + gate de IA. Série histórica de
  sinal óptico; exige pelo menos `login_ids` ou `onu_serials`. Cobertura é parcial por
  desenho — só existe ponto para os momentos em que o login estava na fila de captura daquele
  ciclo.
- `GET /network/logins/search` — sessão autenticada + gate de IA. Busca paginada de login por
  vários critérios (login, regional, PON, transmissor, contrato, geolocalização, filtros de
  horário "a partir de"). Equivalente do `opr_search_logins` do MCP; operadores completos
  (gte/lte/gt/lt/eq) só existem via `POST /ai/infra/search-logins`.
- `GET /network/login-detail` — sessão autenticada + gate de IA. Exige `login` ou `login_id`.
  Detalhe completo de um login: identificação, status de conexão, telemetria ONU/PON e
  histórico recente (`history_hours`).
- `GET /network/login-aggregate` — sessão autenticada + gate de IA. Query `group_by`
  (`regional`/`online`/`transmitter_id`/`pon_id`/`last_drop_cause`). Contagem de logins por
  dimensão, para detectar incidente coletivo sem baixar registro a registro.
- `GET /network/login-outages` — sessão autenticada + gate de IA. Query `since`/`until`
  obrigatório/opcional. Logins offline agora que caíram dentro da janela — não inclui quedas
  já reconectadas.
- `GET /network/login-timeseries` — sessão autenticada + gate de IA. Série temporal de
  conectados/desconectados/quedas novas/reconexões, um ponto por captura real do snapshot
  periódico.
- `GET /network/login-incident-analysis` — sessão autenticada + gate de IA. Funil de incidente
  coletivo numa única chamada: quedas, ainda offline, reconexões, quebra por dimensão e
  clusters geográficos.
- `GET /network/coordinate-quality` — sessão autenticada + gate de IA. Query `entity`
  (`operations_orders`/`operations_login_current_status`/`operations_onu_signal_current`).
  Auditoria de qualidade de latitude/longitude por regional — só classifica e conta, nenhuma
  correção automática.

#### Ordens de serviço (O.S.)
- `GET /orders` — `operations:view_order_details` + gate de IA (campos/filtros liberados por
  perfil, `date_field`, `fields`, `response_mode=summary|full`). Página de O.S. do período,
  ordenável e paginável, com busca geográfica opcional. Toda chamada é registrada em
  auditoria de acesso a dado (`record_ai_access`).
- `GET /orders/{source_order_id}` — `operations:view_order_details` + gate de IA. Detalhe de
  uma O.S. por id de origem (IXC), com `raw_payload` redigido disponível via `response_mode`/
  `fields`. 404 se não encontrada.

#### Filtros e views salvas
- `GET /filters` — sessão autenticada. Query `date_from`/`date_to` (obrigatórios quando
  `scope=period`, opcionais quando `scope=in_progress`), `scope`
  (`period`/`in_progress`), `responsible_mode` (`all`/`completed`) + filtros comuns. Devolve
  as opções disponíveis para cada dimensão de filtro (`OperationFilters`), já restritas ao
  escopo pedido.
- `GET /saved-filters` — sessão autenticada. Lista as visões pessoais do usuário mais as
  globais, se ele tiver `operations:views:read_global`.
- `POST /saved-filters` — `operations:manage_filters` (visão global exige também
  `operations:views:create_global`). Cria uma visão salva; nome único por escopo
  (pessoal do usuário / global).
- `PATCH /saved-filters/{saved_filter_id}` — sessão autenticada, checagem de posse/permissão
  dentro da função (`_can_manage_saved_filter`: dono da visão pessoal com
  `operations:manage_filters`, ou `operations:views:update_global`/`create_global` para
  global). Atualiza nome/filtros/visibilidade.
- `DELETE /saved-filters/{saved_filter_id}` — mesma checagem de posse/permissão, ação
  `delete`.

#### Configuração de equipe
- `GET /team-configuration` — sessão autenticada; escopo `full` (`operations:
  manage_team_models`) ou `own` (`operations:manage_own_team_members`, resolvido por
  `_team_scope_for_user`). Catálogo completo de modelos de equipe + lista de colaboradores;
  no escopo `own`, só os colaboradores supervisionados pelo usuário aparecem.
- `PUT /responsible-directory` — `operations:manage_team_models`. Troca a fonte do diretório
  de responsáveis (`payload.source`).
- `POST /team-models` — `operations:manage_team_models`. Cria um modelo de equipe (faixas
  abaixo/mediano/bom/meta e cores, mais regras de meta por tipo de período). Nome único
  (case-insensitive).
- `PATCH /team-models/{model_id}` — `operations:manage_team_models`. Atualização parcial;
  revalida a ordem crescente das faixas resultantes.
- `DELETE /team-models/{model_id}` — `operations:manage_team_models`. Bloqueia (409) se
  houver colaborador vinculado ao modelo.
- `PUT /team-members` — sessão autenticada; escopo `full`/`own`. Reatribui o modelo de equipe
  de um colaborador (`responsible_name`); no escopo `own`, só se o colaborador for
  supervisionado pelo usuário (404, não 403, se não for — evita confirmar existência de nome
  fora da própria equipe). Também espelha a mudança em `management` e liga escala alternada
  automática quando aplicável.
- `GET /subject-type-mappings` — `operations:manage_subjects`. Lista o mapeamento
  assunto → tipo de O.S.
- `PUT /subject-type-mappings` — `operations:manage_subjects`. Atualiza em lote (vários
  assuntos para um mesmo tipo) e já reflete o novo tipo nas O.S. existentes com aquele
  assunto.

#### Import/export de configuração
- `GET /configuration-json` — `operations:manage_team_models`. Exporta um snapshot portátil
  (sem IDs de banco) de modelos de equipe, membros, e — se o usuário também tiver a permissão
  correspondente — mapeamentos de assunto (`operations:manage_subjects`) e visões salvas
  (`operations:manage_filters`).
- `POST /configuration-json` — `operations:manage_team_models` (subconjuntos de assunto/
  visões exigem também `manage_subjects`/`manage_filters`; visão global no arquivo exige
  `operations:views:create_global`). Faz merge do snapshot pelo nome (não pelo ID): cria ou
  atualiza modelos, membros, mapeamentos de assunto e visões salvas existentes.

### Contrato de filtros e dados

- **Fuso horário**: todas as datas de filtro (`date_from`/`date_to`) são interpretadas em
  `America/Porto_Velho` (constante `OPERATIONS_TIMEZONE_NAME`, ver
  `backend/app/modules/operations/period.py`). O período operacional permitido vai de 1º de
  janeiro do ano corrente (nesse fuso) até a data/hora atual convertida para esse fuso —
  período fora dessa janela é rejeitado com 422.
- **Datas inclusivas**: o intervalo de consulta cobre o dia inteiro de `date_from` (00:00:00
  local) até o fim do dia de `date_to` (23:59:59 local), ambos convertidos para UTC antes de
  bater no banco (`local_period_utc_bounds`) — ou seja, `date_from` e `date_to` são inclusivos
  nos dois extremos.
- **`opened_at` vs `closed_at`**: por padrão as métricas de período consideram uma O.S. dentro
  do intervalo quando ela **abriu OU fechou** no período (união `opened_at.between(...) OR
  closed_at.between(...)`, ver `_query_conditions` em `queries.py`). O parâmetro `date_field`
  de `GET /orders` restringe explicitamente a um único marco (`opened_at`, `closed_at`,
  `scheduled_at`, `execution_started_at`, `finished_at`, `displacement_started_at`,
  `assumed_at` ou `deadline_at`) em vez da regra padrão de união. Backlog (`/in-progress*`)
  é sempre o estoque de O.S. com `closed_at` nulo, sem filtro de período — filtros de dia da
  semana/horário de fechamento nessas rotas comparam contra `closed_at`, que é nulo em toda
  O.S. ainda aberta.
- **Paginação**: rotas de listagem de O.S. (`/orders`, `/openings/orders`, `/in-progress/
  orders`, `/calendar/orders` e variantes de detalhe) usam `page` (mínimo 1) e `page_size`
  (10 a 200, padrão 50), com `total`/`total_pages` na resposta (`OperationOrderPage`).
  Buscas de login (`/network/logins/search`) usam `page`/`page_size` (1 a 500, padrão 50).
- **Limite de filtros**: cada campo de filtro de lista (exceto busca textual e os filtros de
  janela customizada) aceita no máximo `MAX_FILTER_VALUES_PER_FIELD` valores; exceder retorna
  422.
- Para a norma geral de qualidade de dado, filtro de período, importação e dashboard que rege
  todos os módulos (não só este), ver `docs/normas-qualidade-dados-metricas.md` — este
  documento descreve apenas o que está de fato implementado no router/schemas lidos aqui.

### Exemplos

#### Visão Geral do mês corrente, filtrando por regional

```
GET /api/operations/overview?date_from=2026-09-01&date_to=2026-09-16&regional_groups=UNI+-+JI-PARANA
Authorization: Bearer <token>
```

```json
{
  "opened": 842,
  "opened_associated": 12,
  "responsible_filter_active": false,
  "completed": 790,
  "in_progress": 96,
  "opened_out_of_time": 18,
  "completed_on_time": 705,
  "completed_out_of_time": 85,
  "sla_rate": 89.24,
  "average_daily_opened": 52.6,
  "average_daily_completed": 49.4,
  "average_closing_hours": 14.7,
  "average_wait_to_displacement_minutes": 38.2,
  "average_cycle_minutes": 210.5
}
```

#### Backlog em aberto, quebrado por regional

```
GET /api/operations/in-progress?group_by=regional
Authorization: Bearer <token>
```

```json
[
  { "label": "UNI - JI-PARANA", "quantity": 41, "percentage": 42.7 },
  { "label": "UNI - ARIQUEMES", "quantity": 30, "percentage": 31.3 },
  { "label": "UNI - ROLIM DE MOURA", "quantity": 25, "percentage": 26.0 }
]
```

#### Página de O.S. do período, ordenada por data de abertura

```bash
curl -s "https://<host>/api/operations/orders?date_from=2026-09-01&date_to=2026-09-16&page=1&page_size=2&sort_by=opened_at&sort_dir=desc&response_mode=summary" \
  -H "Authorization: Bearer <token>"
```

```json
{
  "items": [
    {
      "order_code": "OS-000123456",
      "regional": "UNI - JI-PARANA",
      "city": "Ji-Paraná",
      "os_type": "Suporte Técnico",
      "os_subject": "Sem sinal",
      "sector": "Manutenção",
      "status": "Finalizada",
      "sla_status": "on_time",
      "opened_at": "2026-09-16T13:05:00-04:00",
      "closed_at": "2026-09-16T15:40:00-04:00",
      "responsible": "João da Silva",
      "priority": "Normal"
    }
  ],
  "total": 842,
  "page": 1,
  "page_size": 2,
  "total_pages": 421
}
```

Nesse último exemplo, `response_mode=summary` recorta a resposta para o conjunto enxuto de
campos definido em `ORDER_SUMMARY_FIELDS` (pensado para triagem por agentes de IA); sem esse
parâmetro (ou com `fields` explícito), a resposta traz todos os campos autorizados de
`OperationOrderOut`, incluindo os campos calculados (`service_address`,
`address_is_structured`, `service_description`, `technical_report`).

---

<a id="gamificacao"></a>

## Gamificação Operacional


> Documento gerado por leitura direta do código em `backend/app/api/routes/`
> (17 arquivos de rota do módulo, mais `health.py`, compartilhado por toda a
> aplicação). Reflete o estado do código nesta branch em 2026-09-16. Se este
> documento divergir do código no futuro, o código vence (ver
> `docs/00-TRILHA-0.md`).

### Visão geral

A Gamificação Operacional é o módulo de **remuneração variável, fechamento e
auditoria de produtividade** a partir das Ordens de Serviço (O.S.) da
operação. É o maior módulo do ecossistema UNI Workspace, montado no FastAPI
sob o prefixo **bare `/api`** (sem sub-prefixo de módulo, ao contrário de
`/api/operations`, `/api/support` etc. — ver `docs/00-TRILHA-0.md`).

Fluxo de negócio de ponta a ponta:

1. **Importação** das O.S. (via IXC, automática/periódica, ou planilha
   UpValue) — `imports.py`.
2. **Configuração** de regras de pontuação por assunto/tipo de O.S., regras
   de penalidade por diagnóstico e SLA, saúde operacional, liderança e
   parâmetros gerais — `scoring.py`, `rules.py`, `gamification.py`,
   `leadership.py`, `settings.py`.
3. **Cálculo/fechamento** mensal por regional, que gera um `CalculationRun`
   com a pontuação de cada colaborador (`CollaboratorScore`) e evolui por
   status (`draft → review → approved → paid`, ou `cancelled`) —
   `calculation_runs.py`.
4. **Auditoria** granular de cada O.S. pontuada, penalizada ou não mapeada,
   e do saldo de pontos/garantia de cada colaborador —
   `audit.py`, `point_balance.py`, `collaborators.py`.
5. **Consumo** pelos próprios colaboradores no Portal (extrato, regras,
   simulação de ganho) e por gestores no dashboard executivo —
   `portal.py`, `dashboard.py`.
6. **Gestão de acesso** ao sistema (usuários, convites, solicitações de
   acesso) e **auditoria de mudanças** (log de toda escrita relevante) —
   `users.py`, `invites.py`, `access_requests.py`, `audit.py`.

Regra de negócio pesada vive em `backend/app/services/`, nunca nas rotas
(ver `AGENTS.md`). As rotas aqui documentadas são, em sua maioria, finas:
validam entrada, delegam a um service e serializam a saída.

### Autenticação e permissões

#### Padrão de autenticação

- Esquema: `Authorization: Bearer <token>` (JWT), validado por
  `get_current_user` (`backend/app/core/security.py`). O token é emitido por
  `POST /api/auth/login` ou pelo fluxo de convite/aceite.
- `require_permission(permission: str)` é uma dependência que empilha sobre
  `get_current_user`: resolve as permissões efetivas do usuário
  (`permissions_for_user`, combinação de perfis de acesso + `role` legado) e
  responde `403 Permissão insuficiente.` se a permissão não estiver no
  conjunto.
- `require_portal_access(permission: str)` é o mesmo `require_permission`,
  mais o bloqueio de **primeiro acesso pendente**: usuário vinculado a um
  colaborador (`collaborator_id`) que nunca completou o onboarding (CPF,
  contato, senha nova) recebe `403 Conclua seu primeiro acesso para
  continuar.` em qualquer rota do Portal, exceto as duas de onboarding em si.
- `is_admin_user(user)` é um atalho usado em pontos sensíveis (extrato
  financeiro, ajustes manuais de saldo, recálculo de bônus de liderança):
  `True` se o usuário tem a permissão `admin:users:write` ou `role == "admin"`.

#### Rotas públicas (sem autenticação)

Único conjunto de endpoints do módulo que não passa por `get_current_user`:

| Rota | Arquivo | Por quê é pública |
|---|---|---|
| `GET /api/health` | `health.py` | Health check de infraestrutura. |
| `POST /api/auth/login` | `auth.py` | É como a sessão nasce. Rate limit próprio (5 tentativas/15 min por IP+email). |
| `GET /api/invites/accept` | `invites.py` | Confirma se um convite por token ainda é válido, antes do formulário de senha. Nunca expõe `collaborator_id`/`role`. |
| `POST /api/invites/accept` | `invites.py` | Aceitar o convite É como a conta nasce (Fase 2C). Rate limit próprio (10/15 min por IP). |
| `POST /api/access-requests/lookup-cpf` | `access_requests.py` | Candidato sem conta confirma nome/telefone parcialmente mascarado pelo CPF antes de pedir acesso. Rate limit próprio (10/15 min por IP). |
| `POST /api/access-requests` | `access_requests.py` | Canal formal de solicitação de acesso para quem não tem conta nem convite (ex.: colaborador recém-contratado). Resposta sempre idêntica (`{"received": true}`), de propósito — nunca revela se CPF/e-mail já existem. Rate limit próprio (10/15 min por IP). |

Todo o restante do módulo exige `Authorization: Bearer` válido; a maioria
também exige uma permissão específica via `require_permission`.

#### Catálogo de permissões (`require_permission(...)`)

Strings encontradas em uso em todo o módulo, por domínio:

| Permissão | Onde é usada |
|---|---|
| `users:manage` | CRUD de usuários, convites, solicitações de acesso, lookup de CPF no IXC (admin). |
| `orders:read` | Leitura de O.S., status de sincronização IXC, runs de importação. |
| `orders:import` | Backfill/importação de O.S. (IXC e UpValue), exclusão de O.S. por período. |
| `audit:read` | Logs de auditoria, auditoria de O.S. pontuadas/reincidência, registro de colaboradores, extrato/saldo/histórico de colaborador, saldo de pontos pendente/ajuste. |
| `scoring:read` | Leitura de grupos e regras de pontuação, regras de penalidade/saúde/reincidência, configuração de gamificação, snapshot de CPK, perfis de liderança. Também é dependência **de todo o router** de `scoring.py` e `rules.py` (`dependencies=[Depends(require_permission("scoring:read"))]` no `APIRouter`). |
| `scoring:write` | Escrita de colaboradores, grupos/regras de pontuação, vínculo de assunto a grupo, perfis de liderança. |
| `penalties:write` | Escrita de regras de penalidade por diagnóstico e por SLA, regras de classificação de reincidência. |
| `health_rules:write` | Escrita de regras de saúde operacional (`HealthRule`). |
| `settings:write` | Escrita de configurações do app (`AppSetting`), configuração/import/export/reset de gamificação, sincronização de CPK, seed manual (dev only). |
| `calculation:run` | Disparar cálculo/fechamento mensal, mudar status de um `CalculationRun`, calcular bônus de liderança. |
| `dashboard:read` | Bootstrap e resumo do dashboard, breakdowns filtrados, listagem/detalhe de runs de cálculo. |
| `portal:read_overview`, `portal:read_self`, `portal:update_self_profile`, `portal:read_regional_summary`, `portal:read_rules`, `portal:simulate_self` | Todas as rotas do Portal do Colaborador (`portal.py`), sempre via `require_portal_access`. |

Além disso, dentro de handlers específicos há checagens adicionais de
**admin puro** (`is_admin_user`), mais restritivas que a permissão de
entrada da rota:

- `GET /collaborators/{id}/statement.pdf` — exige `audit:read` na entrada,
  mas só emite o PDF para o admin ou para o próprio colaborador dono do
  extrato (`user.collaborator_id == collaborator_id`). Correção de um
  achado de auditoria (vazamento de extrato financeiro para qualquer leitor
  operacional).
- `POST /leadership/bonus-results/calculate` — exige `calculation:run`, mas
  só o admin pode de fato recalcular (reescreve valor financeiro já pago).
- `POST/POST/POST /point-balance/entries...` (criar ajuste manual, resolver
  revisão, reverter lançamento) — exigem `audit:read`, mas só o admin
  executa a ação.
- `POST /service-orders/delete-period` — exige `orders:import`, mas bloqueia
  incondicionalmente se o período tiver algum fechamento com status `paid`
  (mesmo o admin precisa reverter o pagamento antes).

### Endpoints

Convenções usadas abaixo: **Perm.** é a permissão exigida (`—` = só
autenticado, **Público** = sem autenticação). Corpos de request/response
resumidos pelos nomes dos schemas Pydantic (`app/schemas`) quando existem;
detalhamento textual quando o retorno é montado ad-hoc no handler.

#### Autenticação (`auth.py`, prefixo `/auth`, 3 rotas)

| Método + path | Descrição | Perm. |
|---|---|---|
| `POST /auth/login` | Login por e-mail/senha. Rate limit 5 tentativas/15 min por IP+email (`429` ao estourar). Retorna `TokenOut` (`access_token`, `user` serializado com permissões efetivas, `managed_regionals`, `portal_first_access_required`). | Público |
| `GET /auth/me` | Dados do usuário autenticado (`UserOut`, mesmo serializador de `login`). | — |
| `POST /auth/change-password` | Troca de senha voluntária. Exige apenas autenticação — vale para qualquer usuário do ecossistema, não só quem tem `collaborator_id`. Corpo `ChangePasswordRequest` (senha atual, nova, confirmação). | — |

#### Usuários (`users.py`, prefixo `/users`, 6 rotas)

| Método + path | Descrição | Perm. |
|---|---|---|
| `GET /users` | Lista todos os usuários (`UserOut[]`). | `users:manage` |
| `POST /users` | Cria usuário. Valida `role` contra lista fechada (`viewer`, `operator`, `admin`, `collaborator`, `regional_manager_viewer`, `base_manager`, `workspace_restricted`), e-mail único, vínculo 1:1 com colaborador. Marca `must_change_password=true` automaticamente se vinculado a colaborador. | `users:manage` |
| `PUT /users/{user_id}` | Atualização parcial (`exclude_unset`). Revalida e-mail único, vínculo de colaborador, `managed_regionals`; remover todos os perfis de acesso rebaixa o usuário para `workspace_restricted`. | `users:manage` |
| `POST /users/{user_id}/force-password-reset` | Reset administrativo: gera senha temporária (`secrets`, alfabeto sem caracteres ambíguos) e força troca no próximo login. Retorna `AdminForcePasswordResetOut` (inclui `temporary_password` em texto puro, uma única vez). | `users:manage` |
| `POST /users/{user_id}/force-first-access` | Reabre o primeiro acesso completo (CPF/contato + senha), não só a senha. | `users:manage` |
| `DELETE /users/{user_id}` | Exclui usuário (bloqueia autoexclusão). Logs de auditoria do usuário excluído ficam órfãos (`user_id = NULL`), não são apagados. | `users:manage` |

#### Convites (`invites.py`, prefixo `/invites`, 7 rotas)

| Método + path | Descrição | Perm. |
|---|---|---|
| `POST /invites` | Cria convite avulso (e-mail + `collaborator_id` + `role`), devolve token bruto uma única vez (`PortalInviteCreateOut`). | `users:manage` |
| `POST /invites/lookup-ixc-cpf` | Busca colaborador no IXC por CPF para sugerir convite; nunca cria nada sozinho. | `users:manage` |
| `POST /invites/from-ixc` | Confirma o colaborador encontrado no IXC e gera o convite; `collaborator_id` sempre explícito no corpo, nunca implícito. | `users:manage` |
| `GET /invites` | Lista convites (`PortalInviteOut[]`). | `users:manage` |
| `POST /invites/{invite_id}/revoke` | Revoga convite. | `users:manage` |
| `GET /invites/accept?token=` | Status do convite por token (válido/expirado/usado), sem revelar dado interno. | Público |
| `POST /invites/accept` | Aceita o convite com nova senha; devolve `TokenOut` igual ao login (entra direto no onboarding). Rate limit 10/15 min por IP. | Público |

#### Solicitações de Acesso (`access_requests.py`, prefixo `/access-requests`, 5 rotas)

| Método + path | Descrição | Perm. |
|---|---|---|
| `POST /access-requests/lookup-cpf` | Candidato confirma nome/telefone mascarado pelo CPF (nunca e-mail). Rate limit 10/15 min por IP. | Público |
| `POST /access-requests` | Submete solicitação (CPF, e-mail, senha escolhida, nome, telefone). Resposta sempre `{"received": true}` — nunca revela se já existe conta. Rate limit 10/15 min por IP. | Público |
| `GET /access-requests` | Lista solicitações pendentes/decididas (`PortalAccessRequestOut[]`). | `users:manage` |
| `POST /access-requests/{id}/approve` | Aprova e cria a conta direto, com a senha que o candidato já escolheu ao solicitar. `collaborator_id` sempre explícito no corpo. | `users:manage` |
| `POST /access-requests/{id}/reject` | Rejeita, com motivo (`decision_reason`). | `users:manage` |

#### Importações (`imports.py`, prefixo `/imports`, 8 rotas)

| Método + path | Descrição | Perm. |
|---|---|---|
| `POST /imports/ixc-backfill` | Importação retroativa sob demanda de um mês específico direto da API do IXC (fora do polling periódico). Corpo `{year, month}`. `409` se o lock de importação estiver ocupado; `502` em falha de comunicação com o IXC. | `orders:import` |
| `GET /imports/ixc-sync-status` | Saúde da sincronização automática com o IXC (`last_success_at`, `last_error_at`, `consecutive_failures`, `is_healthy`) — não há alerta ativo (e-mail/webhook), esta rota é o único jeito de checar. | `orders:read` |
| `POST /imports/upvalue-service-orders/preview` | Upload de planilha UpValue (`multipart/form-data`), devolve prévia (`ImportPreview`) sem gravar nada. | `orders:import` |
| `POST /imports/upvalue-service-orders` | Importa de fato a planilha UpValue. Em falha, registra `ImportRun` com status de erro antes de propagar a exceção. | `orders:import` |
| `GET /imports/runs` | Lista `ImportRun` com filtros (`status`, `file_name`, `imported_by`, `date_from/to`, `limit` até 200). | `orders:read` |
| `GET /imports/runs/{id}` | Detalhe de um `ImportRun`. | `orders:read` |
| `GET /imports/runs/{id}/audits` | Auditoria linha-a-linha de uma importação (`action`, `os_code`, `reason`), paginada. | `orders:read` |
| `GET /imports/runs/{id}/errors` | Mesmo endpoint acima, filtrado a `action in (error, rejected, blocked_paid_period)`. | `orders:read` |

#### Auditoria (`audit.py`, prefixo `/audit`, 5 rotas)

| Método + path | Descrição | Perm. |
|---|---|---|
| `GET /audit/logs` | Log de auditoria genérico do sistema (`AuditLog`), com filtros `action`/`entity`/`entity_id`/`user_id`/`search` e paginação (`limit≤500`, `offset`). | `audit:read` |
| `GET /audit/service-orders` | Auditoria detalhada de O.S. do período/regional (default: fechamento mais recente), com dezenas de flags (`only_scored`, `only_penalized`, `only_sla_out`, `only_warranty`, `only_recurrence`, `only_diagnosis_blocked`, `only_registered` — este último `True` por padrão, restringindo à equipe cadastrada). Paginado (`page`, `page_size` até 5000). | `audit:read` |
| `GET /audit/service-orders-scoring` | Alias idêntico ao endpoint acima (mesmos parâmetros, mesma implementação). | `audit:read` |
| `GET /audit/service-orders/{id}/recurrence-audit` | Explica a classificação de reincidência de uma O.S. específica. `404` se não houver auditoria de reincidência para ela. | `audit:read` |
| `GET /audit/service-orders/{id}/detail` | Explicação completa (regras aplicadas, pontos, penalidades) de uma O.S., opcionalmente ancorada em um `calculation_run_id`. | `audit:read` |

#### Colaboradores (`collaborators.py`, prefixo `/collaborators`, 12 rotas)

| Método + path | Descrição | Perm. |
|---|---|---|
| `GET /collaborators/registry` | Registro completo: separa colaboradores `registered`/`unregistered`, sugere regional/cargo a partir das O.S. vinculadas, sinaliza vínculo com usuário do Portal e presença de foto. | `audit:read` |
| `POST /collaborators` | Cria colaborador (normaliza `regional`). | `scoring:write` |
| `DELETE /collaborators/{id}` | Exclusão condicional: se o colaborador tem O.S. vinculadas ou pontuação calculada, faz **soft delete** (`active=false`, `is_registered=false`) em vez de apagar (evita `IntegrityError` de FK). Devolve `CollaboratorDeleteResult` indicando se foi hard ou soft delete. | `scoring:write` |
| `GET /collaborators/{id}/service-orders-detail` | Detalhamento de O.S. do colaborador no período (mesmo leque de flags `only_*` de `audit.py`). | `audit:read` |
| `GET /collaborators/{id}/scoring-detail` | Alias do endpoint acima (delega para a mesma função). | `audit:read` |
| `GET /collaborators/{id}/statement.pdf` | Gera PDF do extrato de pagamento individual para um `calculation_run_id`. Só admin ou o próprio colaborador (ver seção de permissões); `404` se colaborador/run/score não existirem. | `get_current_user` + checagem manual |
| `GET /collaborators/{id}/point-balance` | Saldo atual de pontos de garantia (`current_balance`) e histórico de lançamentos (`PointBalanceEntry`), com colaborador/O.S./run relacionados pré-carregados. | `audit:read` |
| `GET /collaborators/{id}/monthly-history` | Histórico mensal de pontuação: uma linha por (mês, ano, regional), preferindo o fechamento `paid` mais recente sobre outros status. | `audit:read` |
| `PUT /collaborators/{id}` | Atualização parcial de cadastro. | `scoring:write` |
| `POST /collaborators/{id}/photo` | Upload de foto de perfil (JPEG/PNG/WEBP, até 2MB, guardada como bytes no banco). | `scoring:write` |
| `GET /collaborators/{id}/photo` | Retorna os bytes da foto (`Response` binário, `404` se não houver). | `audit:read` |
| `DELETE /collaborators/{id}/photo` | Remove a foto. | `scoring:write` |

#### Pontuação / Scoring (`scoring.py`, sem prefixo próprio — rotas soltas; router com `dependencies=[require_permission("scoring:read")]` aplicado a TODAS as rotas, 17 rotas)

Todo o router exige no mínimo `scoring:read`; algumas rotas de escrita
exigem adicionalmente `scoring:write` ou `penalties:write`.

| Método + path | Descrição | Perm. adicional |
|---|---|---|
| `GET /scoring-groups` | Lista grupos de pontuação. | — |
| `POST /scoring-groups` | Cria grupo. | `scoring:write` |
| `PUT /scoring-groups/{id}` | Atualiza grupo. | `scoring:write` |
| `DELETE /scoring-groups/{id}` | Exclui grupo; se tem assuntos vinculados, exige `replacement_group_id` (move os vínculos) ou `delete_linked_rules=true` (apaga junto) — senão `409`. | `scoring:write` |
| `GET /scoring-subject-rules` | Lista regras de assunto com estatísticas agregadas (contagem de O.S. e impacto financeiro por regra, via `GROUP BY` no banco). | — |
| `POST /scoring-subject-rules` | Cria regra assunto↔grupo. `409` se o assunto já tiver regra. Se a criação muda o Tipo Geral (`os_type`) de O.S. já importadas, dispara recálculo automático do período corrente. | `scoring:write` |
| `PUT /scoring-subject-rules/{id}` | Atualiza regra; mesma lógica de recálculo em cascata ao mudar `os_type`. | `scoring:write` |
| `DELETE /scoring-subject-rules/{id}` | Exclui regra de assunto. | `scoring:write` |
| `GET /scoring-subject-rules/unmapped` | Assuntos de O.S. do período sem regra configurada. | — |
| `GET /scoring-matrix/unmapped-subjects` | Alias do endpoint acima. | — |
| `POST /scoring-matrix/subjects/link-to-group` | Vincula um assunto a um grupo (cria a regra se não existir), cascateando o Tipo Geral nas O.S. já importadas e reconciliando regras órfãs duplicadas. | `scoring:write` |
| `POST /scoring-matrix/subjects/link-to-group/bulk` | Mesmo vínculo, em lote. | `scoring:write` |
| `GET /diagnoses/imported` | Estatísticas de diagnósticos importados no período. | — |
| `GET /diagnoses/unmapped` | Mesmo endpoint, filtrado a diagnósticos sem regra de penalidade. | — |
| `GET /scoring-matrix/unmapped-diagnoses` | Alias de `diagnoses/unmapped`. | — |
| `POST /scoring-matrix/diagnoses/configure` | Configura (cria ou atualiza) a regra de penalidade de um diagnóstico. `action_type` restrito a `subtract_points`/`cancel_points`/`no_penalty`/`requires_review`/`force_points`. | `penalties:write` |
| `POST /scoring-matrix/diagnoses/configure/bulk` | Mesma configuração, em lote. | `penalties:write` |

#### Regras (`rules.py`, sem prefixo próprio — router com `dependencies=[require_permission("scoring:read")]`, 13 rotas)

| Método + path | Descrição | Perm. adicional |
|---|---|---|
| `GET /diagnosis-penalty-rules` | Lista regras de penalidade por diagnóstico. | — |
| `POST /diagnosis-penalty-rules` | Cria (nome de diagnóstico único). | `penalties:write` |
| `PUT /diagnosis-penalty-rules/{id}` | Atualiza. | `penalties:write` |
| `GET /sla-penalty-rules` | Lista regras de penalidade por SLA. | — |
| `POST /sla-penalty-rules` | Cria. `condition_type` restrito a 3 valores; `penalty_type` a 5 valores. | `penalties:write` |
| `PUT /sla-penalty-rules/{id}` | Atualiza. | `penalties:write` |
| `GET /recurrence-classification-rules` | Lista regras de classificação de reincidência, ordenadas por prioridade. | — |
| `POST /recurrence-classification-rules` | Cria. `classification` restrito a 6 valores (`recorrencia_operacional`, `reincidencia_tecnica`, `garantia`, `os_nao_reincidente`, `demandas_diferentes`, `nao_identificado`). | `penalties:write` |
| `PUT /recurrence-classification-rules/{id}` | Atualiza. | `penalties:write` |
| `DELETE /recurrence-classification-rules/{id}` | Exclui. | `penalties:write` |
| `GET /health-rules` | Lista regras de saúde operacional (multiplicador por SLA mínimo/reincidência máxima). | — |
| `POST /health-rules` | Cria; valida `min_sla`/`max_recurrence_rate` (0–100) e `multiplier` (≥0). | `health_rules:write` |
| `PUT /health-rules/{id}` | Atualiza, mesma validação. | `health_rules:write` |

#### Configuração de Gamificação (`gamification.py`, prefixo `/gamification`, 7 rotas)

| Método + path | Descrição | Perm. |
|---|---|---|
| `GET /gamification/config` | Configuração corrente completa (regras, parâmetros gerais) serializada. | `scoring:read` |
| `PUT /gamification/config` | Aplica uma configuração completa; registra log de auditoria com before/after. | `settings:write` |
| `POST /gamification/config/export` | Mesmo retorno de `GET /config` (endpoint dedicado para o fluxo de exportação no frontend). | `scoring:read` |
| `POST /gamification/config/import` | Importa configuração (mesmo `apply_config` de `PUT /config`, log de auditoria com ação `import`). | `settings:write` |
| `POST /gamification/config/reset-default` | Restaura a configuração padrão de fábrica (`ensure_default_logic_config`). | `settings:write` |
| `POST /gamification/cpk/sync` | Sincroniza sob demanda o relatório de CPK (custo por km) por regional a partir da API externa de CPK; grava snapshot local. `502` em falha de comunicação. | `settings:write` |
| `GET /gamification/cpk/snapshot?year=&month=` | Último snapshot de CPK sincronizado para o período (sem chamar a API ao vivo). | `scoring:read` |

#### O.S. / Service Orders (`service_orders.py`, prefixo `/service-orders`, 5 rotas)

| Método + path | Descrição | Perm. |
|---|---|---|
| `GET /service-orders?limit=` | Lista O.S. reais (exclui códigos demo), mais recentes primeiro. | `orders:read` |
| `GET /service-orders/period-summary` | Resumo por (ano, mês): total de O.S., primeira/última data de fechamento. | `orders:read` |
| `GET /service-orders/subject-summary?reference_month=&reference_year=&regional=` | Contagem de O.S. por (tipo, assunto) no período, ordenado por volume. | `orders:read` |
| `POST /service-orders/delete-period` | Exclusão em massa de O.S. de um período (+ `CalculationRun`s associados), com confirmação textual obrigatória (`"APAGAR MM/AAAA"`). Bloqueia (`409`) se houver fechamento `paid` no período, ou lançamentos de saldo de garantia vinculados sem O.S. rastreável. Desvincula (sem apagar) lançamentos de saldo que ainda podem ser reimportados. | `orders:import` |
| `POST /service-orders/seed` | Popula o banco com dados de lógica (sem O.S. demo); disponível **apenas em ambiente `development`** (`403` fora dele). | `settings:write` |

#### Liderança (`leadership.py`, prefixo `/leadership`, 10 rotas)

| Método + path | Descrição | Perm. |
|---|---|---|
| `GET /leadership/profiles` | Lista perfis de liderança (com regionais e perfil de cargo). | `scoring:read` |
| `GET /leadership/role-profiles` | Lista perfis de cargo de liderança (multiplicador padrão por tipo de escopo). | `scoring:read` |
| `POST /leadership/role-profiles/ensure-defaults` | Garante que os perfis de cargo padrão existam (idempotente). | `settings:write` |
| `POST /leadership/role-profiles` | Cria perfil de cargo. | `scoring:write` |
| `PUT /leadership/role-profiles/{id}` | Atualiza; propaga o novo multiplicador para todo líder vinculado que não usa multiplicador customizado. | `scoring:write` |
| `DELETE /leadership/role-profiles/{id}` | Exclui; bloqueia (`409`) se houver líder vinculado. | `scoring:write` |
| `POST /leadership/profiles` | Cria perfil de liderança individual; valida sobreposição de escopo regional entre perfis (`validate_no_scope_overlap`). | `scoring:write` |
| `PUT /leadership/profiles/{id}` | Atualiza; revalida sobreposição de escopo. | `scoring:write` |
| `DELETE /leadership/profiles/{id}` | Exclusão condicional: se há resultados de bônus históricos vinculados, apenas desativa (`active=false`); senão apaga de fato. | `scoring:write` |
| `POST /leadership/bonus-results/calculate?calculation_run_id=` | Recalcula e regrava o bônus de liderança de um fechamento. **Somente admin** (checagem extra além de `calculation:run`). Bloqueia (`409`) se o fechamento estiver `paid`/`cancelled` — é o registro do que foi de fato pago. | `calculation:run` + admin |

#### Runs de Cálculo (`calculation_runs.py`, prefixo `/calculation-runs`, 6 rotas)

O coração financeiro do módulo. Um `CalculationRun` representa um
fechamento mensal (por regional ou global) com status
`draft → review → approved → paid`, ou `cancelled`.

| Método + path | Descrição | Perm. |
|---|---|---|
| `GET /calculation-runs` | Histórico de fechamentos com totais agregados (pontos brutos/líquidos/finais, valor estimado, top colaborador), filtrável por período/regional/status; `include_empty=false` por padrão oculta runs sem O.S. | `dashboard:read` |
| `POST /calculation-runs/calculate` | Executa o cálculo/fechamento do período (`reference_month`/`reference_year` obrigatórios). Recalcula o bônus de liderança em seguida e grava log de auditoria. `allow_paid_revision` permite criar uma revisão em cima de um período já pago. | `calculation:run` |
| `GET /calculation-runs/latest` | Fechamento mais recente serializado (ou `null`). | `dashboard:read` |
| `GET /calculation-runs/{id}` | Detalhe completo de um fechamento, incluindo `config_snapshot` (config vigente no momento do cálculo). | `dashboard:read` |
| `GET /calculation-runs/{id}/snapshot` | Só o `config_snapshot` do run (retorno leve). | `dashboard:read` |
| `PATCH /calculation-runs/{id}/status` | **Rota mais crítica do módulo.** Muda o status do fechamento com lock de linha (`SELECT ... FOR UPDATE`) para evitar dupla transição concorrente. Ao transicionar para `paid`: (1) consome os lançamentos pendentes de saldo de garantia de cada colaborador e recompõe `final_points`/`estimated_payment` a partir do valor bruto; (2) atualiza os detalhamentos (`cost_by_*`, distribuição de penalidade) que ficavam congelados com a prévia do rascunho; (3) invalida o cache de breakdowns filtrados; (4) recalcula o bônus de liderança sobre a base já atualizada; (5) atualiza prévias de outros rascunhos do(s) mesmo(s) colaborador(es) cujo saldo de garantia acabou de ser consumido, para não mostrar um desconto fantasma. | `calculation:run` |

#### Dashboard (`dashboard.py`, prefixo `/dashboard`, 4 rotas)

| Método + path | Descrição | Perm. |
|---|---|---|
| `GET /dashboard/bootstrap` | Retorno mínimo para a tela inicial decidir o período/regional padrão: `reference_month/year`, `regional`, `point_value`, `has_calculation_run`. | `dashboard:read` |
| `GET /dashboard/gamification-preview` | Leitura leve (valor corrente + data do cálculo) para a Visão Geral executiva de outro módulo (`UNI Intelligence`/`operacao`), sem carregar ranking/breakdowns completos. | `dashboard:read` |
| `GET /dashboard/summary?reference_month=&reference_year=&regional=` | **Rota principal da tela de Gamificação.** Monta cards, ranking, bônus de liderança, distribuição de penalidade, saúde por regional e custos por regional/grupo/assunto/colaborador. Usa um cache versionado (`dashboard_cache_version == 3`) gravado no próprio `CalculationRun.result_summary`, com uma guarda de consistência (`_regional_breakdown_is_consistent`) que recusa o cache e recalcula se o total por regional exceder o teto financeiro do fechamento — proteção contra dado gravado desatualizado após um pagamento. Fechamentos imutáveis (`paid`/`cancelled`) têm um segundo nível de cache em memória de processo (`IMMUTABLE_BREAKDOWNS_CACHE`, até 64 entradas), porque recalcular o mês inteiro chegou a levar 6,36s medidos. | `dashboard:read` |
| `GET /dashboard/filtered-breakdowns?calculation_run_id=&regional=` | Breakdowns (distribuição de penalidade, custo por regional/grupo, assuntos não mapeados) recortados para um subconjunto de regionais dentro de um fechamento, com cache próprio por `(run_id, regionais)` — invalidado explicitamente quando o run muda de status para `paid`. | `dashboard:read` |

#### Configurações do App (`settings.py`, prefixo `/settings`, 2 rotas)

`app_settings` é uma tabela compartilhada entre módulos (Agendamento guarda
suas próprias chaves `scheduling_*` nela também); estas rotas só
leem/escrevem as chaves que pertencem à Gamificação.

| Método + path | Descrição | Perm. |
|---|---|---|
| `GET /settings` | Lista as configurações da Gamificação (`AppSettingOut[]`, filtradas às chaves conhecidas do módulo). | `scoring:read` |
| `PUT /settings/{key}` | Atualiza uma configuração pelo nome da chave. `404` se a chave não pertencer à Gamificação. | `settings:write` |

#### Saldo de Pontos (`point_balance.py`, prefixo `/point-balance`, 4 rotas)

Sistema de saldo/garantia pós-pagamento (ver
`docs/spec-saldo-pontos-garantia-pos-pagamento.md`): débitos e créditos de
pontos que ficam pendentes até serem consumidos num fechamento pago.

| Método + path | Descrição | Perm. |
|---|---|---|
| `GET /point-balance/pending?calculation_run_id=` ou `?reference_month=&reference_year=` | Lista lançamentos pendentes classificados em três buckets: `applied` (já consumido por este fechamento), `eligible_pending` (seria consumido se este fechamento fosse pago agora) e `deferred_pending` (alvo é um mês posterior, só informativo). Sem período informado, devolve o acumulado histórico como `eligible_pending`. | `audit:read` |
| `POST /point-balance/entries` | Cria ajuste manual de saldo (positivo ou negativo). **Somente admin.** | `audit:read` + admin |
| `POST /point-balance/entries/{id}/resolve` | Resolve uma entrada marcada para revisão manual, com os pontos finais decididos. **Somente admin.** | `audit:read` + admin |
| `POST /point-balance/entries/{id}/revert` | Estorna um lançamento, com motivo obrigatório. **Somente admin.** | `audit:read` + admin |

#### Notificações (`notifications.py`, prefixo `/notifications`, 4 rotas)

| Método + path | Descrição | Perm. |
|---|---|---|
| `GET /notifications?limit=` | Lista notificações do usuário autenticado (`limit≤100`). | — (autenticado) |
| `GET /notifications/unread-count` | Contagem de não lidas. | — (autenticado) |
| `POST /notifications/{id}/read` | Marca uma notificação como lida. `404` se não pertencer ao usuário. | — (autenticado) |
| `POST /notifications/read-all` | Marca todas como lidas; devolve `{"marked_read": N}`. | — (autenticado) |

#### Portal do Colaborador (`portal.py`, prefixo `/portal`, 14 rotas)

Área self-service do colaborador. Todas as rotas (exceto as duas de
primeiro acesso) usam `require_portal_access`, que bloqueia quem ainda não
completou o onboarding obrigatório.

| Método + path | Descrição | Perm. |
|---|---|---|
| `GET /portal/overview` | Visão geral agregada (provavelmente para tela de liderança/gestor no Portal). | `portal:read_overview` |
| `GET /portal/summary?reference_month=&reference_year=` | Resumo financeiro do próprio colaborador no período (ou fechamento mais recente se omitido). Mês e ano devem ser informados juntos (`422` se só um vier). | `portal:read_self` |
| `GET /portal/profile` | Dados de perfil do próprio colaborador. | `portal:read_self` |
| `PUT /portal/profile` | Atualiza campos do próprio perfil (`phone`, `email`); log de auditoria com ação `update_self_profile`. | `portal:update_self_profile` |
| `POST /portal/profile/photo` | Upload da própria foto (JPEG/PNG/WEBP, até 2MB). | `portal:update_self_profile` |
| `GET /portal/profile/photo` | Bytes da própria foto. | `portal:read_self` |
| `DELETE /portal/profile/photo` | Remove a própria foto. | `portal:update_self_profile` |
| `GET /portal/my-orders?limit=&reference_month=&reference_year=` | Lista as próprias O.S. no período (`limit` até `PORTAL_ORDERS_MAX`). | `portal:read_self` |
| `GET /portal/my-audit?reference_month=&reference_year=` | Auditoria detalhada da própria pontuação no período. | `portal:read_self` |
| `GET /portal/team-summary` | Resumo da equipe/regional para quem tem visão de gestor no Portal. | `portal:read_regional_summary` |
| `GET /portal/rules` | Regras de pontuação vigentes, em formato de consulta pelo colaborador. | `portal:read_rules` |
| `GET /portal/simulation?extra_points=` | Simula o ganho do colaborador somando pontos extras hipotéticos (0 a 100000). | `portal:simulate_self` |
| `GET /portal/first-access/status` | Status do primeiro acesso obrigatório. Exceção deliberada: usa `get_current_user` puro, não `require_portal_access` — senão criaria um círculo sem saída (usuário pendente jamais conseguiria consultar o próprio status). | — (autenticado) |
| `POST /portal/first-access/complete` | Completa o primeiro acesso (confirma CPF/telefone/e-mail e define senha nova). Mesma exceção acima. | — (autenticado) |

#### Health (`health.py`, prefixo `/health`, 1 rota)

| Método + path | Descrição | Perm. |
|---|---|---|
| `GET /health` | `{"status": "ok"}`, sem tocar banco nem dependências externas. | Público |

### Exemplos

#### 1. Login

```http
POST /api/auth/login
Content-Type: application/json

{
  "email": "gestor@uni.com.br",
  "password": "********"
}
```

Resposta `200`:

```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "user": {
    "id": 42,
    "name": "Maria Gestora",
    "email": "gestor@uni.com.br",
    "role": "admin",
    "active": true,
    "permissions": ["audit:read", "calculation:run", "scoring:write", "..."],
    "access_profile_ids": [3],
    "collaborator_id": null,
    "managed_regionals": [],
    "portal_first_access_required": false
  }
}
```

Chamadas subsequentes usam `Authorization: Bearer eyJhbGciOi...`.

#### 2. Colaboradores — saldo de pontos

```http
GET /api/collaborators/128/point-balance
Authorization: Bearer eyJhbGciOi...
```

Resposta `200` (`CollaboratorPointBalanceOut`):

```json
{
  "collaborator_id": 128,
  "collaborator_name": "João Técnico",
  "balance_points": 14.5,
  "updated_at": "2026-09-10T13:22:01Z",
  "entries": [
    {
      "id": 901,
      "collaborator_id": 128,
      "kind": "debit",
      "status": "applied",
      "points": -6.0,
      "reason": "Reincidência técnica detectada em O.S. 55231",
      "applied_calculation_run_id": 1601,
      "created_at": "2026-08-30T09:10:00Z"
    }
  ]
}
```

Exige a permissão `audit:read`.

#### 3. Fechamento — mudar status para pago

```http
PATCH /api/calculation-runs/1601/status
Authorization: Bearer eyJhbGciOi...
Content-Type: application/json

{
  "status": "paid",
  "note": "Pagamento confirmado via folha de 09/2026."
}
```

Exige `calculation:run`. A mudança para `paid` dispara em cadeia: consumo
dos lançamentos pendentes de saldo de garantia, recomposição de
`final_points`/`estimated_payment`, atualização dos detalhamentos por
regional/grupo/assunto e recálculo do bônus de liderança. Resposta `200` é
o `CalculationRunOut` completo, já com os valores recompostos.

#### 4. Portal do Colaborador — extrato do próprio mês

```http
GET /api/portal/summary?reference_month=8&reference_year=2026
Authorization: Bearer eyJhbGciOi... (token do próprio colaborador)
```

Exige `portal:read_self` (via `require_portal_access` — bloqueia se o
colaborador ainda não completou o primeiro acesso). Resposta `200`
(`PortalSummaryOut`) traz o resumo financeiro pessoal do colaborador para
aquele fechamento (pontos, penalidades, valor estimado a receber, saldo de
garantia aplicado).

### Observações e pontos não totalmente esclarecidos pelo código lido

- Os schemas de resposta (`PortalSummaryOut`, `DashboardSummary`,
  `PortalOverviewOut` etc.) estão em `backend/app/schemas` mas não foram
  lidos campo a campo nesta sessão — as descrições acima refletem o que os
  handlers e os nomes dos campos usados no código deixam explícito. Para o
  contrato de campo exato de cada schema, ler `backend/app/schemas.py`
  (ou o pacote `app/schemas/`, conforme a estrutura do projeto).
- As regras de negócio por trás de `calculate_scores`, `explain_orders`,
  `financial_breakdowns`, `calculate_and_store_leadership_bonus` etc. (em
  `backend/app/services/`) não foram auditadas aqui — este documento cobre
  a superfície HTTP (rota, parâmetro, permissão, formato), não a fórmula de
  cálculo em si.
- `portal:read_overview` (rota `GET /portal/overview`) e `PortalOverviewOut`
  não deixam claro pelo nome apenas se é uma visão de gestor ou uma tela
  agregada para todo colaborador — o handler delega inteiramente a
  `build_portal_overview(db)`, sem filtrar por usuário, o que sugere ser uma
  visão agregada/institucional, mas isso não foi confirmado lendo o service.

---

<a id="suporte"></a>

## SGP Suporte


> Fonte única deste documento: `backend/app/modules/support/router.py` (1809 linhas),
> `backend/app/modules/support/schemas.py` e `backend/app/modules/support/models.py`.
> Qualquer divergência entre este texto e o código deve ser resolvida a favor do código.

### Visão geral

O módulo **SGP Suporte** cobre duas frentes de negócio distintas, montadas sob o mesmo
prefixo `/api/support`:

1. **Atendimentos do OPA Suite** (sistema externo de atendimento ao cliente — chat/bot/
   humano). O módulo importa periodicamente os atendimentos via API do OPA Suite,
   calcula métricas de TMA (tempo médio de atendimento) e TMR (tempo médio de resposta),
   classifica participação bot/humano, e expõe tudo isso como indicador operacional:
   visão geral, série temporal, breakdowns por dimensão, detalhe/timeline de um
   atendimento, filtros salvos e configuração da sincronização automática.

2. **Analítico de tickets IXC** (`su_ticket`/`su_oss_chamado` do ERP IXC). Aqui o
   atendimento (ticket de suporte) é tratado como **indicador antecipado de incidente**
   de rede/operação — não substitui a Ordem de Serviço (O.S.) como fonte de verdade, mas
   serve para detectar anomalia (queda de conexão, instabilidade) antes que ela vire O.S.
   Inclui KPIs de incidência, série diária, drill-down geográfico
   (regional → cidade → bairro → motivo), detecção de rajada (burst), tendência recente
   (momentum), taxa de conversão em O.S. e uma camada de "analytics" com modelo de período
   livre (`date_from`/`date_to` + janela anterior de mesmo tamanho), aditiva à camada mais
   antiga de KPIs por mês-calendário.

O router é montado com `prefix="/support"` e tags `["support"]"`
(`backend/app/modules/support/router.py:96-100`); no gateway completo da API o prefixo
final observado externamente é `/api/support` (ver `backend/app/main.py`).

### Autenticação e permissões

Todas as rotas do módulo exigem usuário autenticado. Duas permissões nomeadas existem
hoje no código (`backend/app/core/security.py:106-107,228-229`):

- **`support:read`** — "Suporte: acessar módulo SGP". Aplicada como dependência **de
  router inteiro** (`dependencies=[Depends(require_permission("support:read"))]`,
  `router.py:99`), portanto **toda** rota sob `/support` já exige essa permissão, mesmo
  quando a assinatura da função só declara `Depends(get_current_user)` — o gate está no
  nível do `APIRouter`, não repetido rota a rota.
- **`support:sync_opa`** — "Suporte: sincronizar OPA Suite". Exigida adicionalmente (via
  `Depends(require_permission("support:sync_opa"))` na assinatura da rota) nos endpoints
  administrativos: configuração e status de sincronização, overrides de atendente,
  disparo/retomada de importação e listagem de meses importados.

Duas rotas fazem checagem de permissão **inline**, fora do padrão `Depends`, porque a
mesma rota é acessível a qualquer leitor mas só uma ação específica dentro dela é
restrita:

- `POST /opa/saved-filters` e `DELETE /opa/saved-filters/{id}`: qualquer usuário com
  `support:read` pode criar/remover um filtro **pessoal** (`scope="personal"`), mas
  publicar ou remover um filtro **global** (`scope="global"`, visível pra toda a
  operação) exige `support:sync_opa` — checado via `_can_sync_opa(user)`
  (`router.py:1262-1267`), que consulta `permissions_for_user(user)` diretamente.

Permissão **prevista mas não implementada**: os comentários em
`backend/app/modules/support/opa_timeline_service.py:6` e
`backend/app/modules/support/models.py:230-231` mencionam uma permissão granular futura
`support:view_pii`/`support:view_conversation` para mascarar texto de conversas — ela
**não existe** em `core/security.py` nem é usada em nenhum `require_permission()` do
router hoje; todo o conteúdo de conversa (mensagens, timeline) está, atualmente, sob o
mesmo nível de acesso de `support:read`.

### Endpoints

#### Sincronização OPA (settings / status / imports)

| Método | Path | Descrição | Permissão |
|---|---|---|---|
| GET | `/opa-sync-settings` | Lê a configuração atual da sincronização automática (habilitado, intervalo em minutos, lookback em dias, backfill de madrugada e seu horário/lookback em meses, intervalo de refresh das dimensões). | `support:sync_opa` |
| PUT | `/opa-sync-settings` | Atualiza qualquer subconjunto dos campos acima (todos opcionais); grava auditoria (`record_audit_log`) do antes/depois. Ao alterar `interval_minutes`, recalcula `next_allowed_at` via `recompute_support_opa_next_allowed_at`. | `support:sync_opa` |
| GET | `/opa-sync-status` | Status operacional: se está `configured` (token/URL do OPA Suite presentes), últimos sucesso/tentativa/erro, run ativo (id/modo/início), se há trava de importação ocupada (`lock_busy`) e se a próxima janela está atrasada (`next_window_delayed`). | `support:sync_opa` |
| POST | `/opa-imports` | Dispara importação **em background** para um período (`date_from`/`date_to`, máx. 32 dias — `validate_opa_period`). Retorna imediatamente com `run_id` e status `pending`; o cliente acompanha via polling em `GET /opa/sync-runs/{run_id}`. Responde `409` se já houver import em andamento (`opa_import_lock_busy`). | `support:sync_opa` |
| GET | `/opa/sync-runs/{run_id}` | Status/progresso de uma run de importação (`pending`/`running`/`completed`/`failed`/`interrupted`), incluindo contagem de páginas processadas e registros criados/atualizados/inalterados/rejeitados. `404` se a run não existir. | `support:sync_opa` |
| POST | `/opa/sync-runs/{run_id}/resume` | Retoma uma run interrompida. Em sucesso, cria notificação in-app para o usuário e devolve o resultado consolidado. Mapeia erros do OPA Suite (`OpaApiError` → 502), interrupção nova (`OpaImportInterrupted` → 502), conflito de estado (`RuntimeError` → 409) e validação (`ValueError` → 422). | `support:sync_opa` |
| GET | `/opa/import-months` | Status (`missing`/`complete`, contagem de atendimentos, última verificação) dos últimos `months` meses-calendário (query `months`, 1–24, padrão 6), do mais antigo pro mais recente. Mesma fonte de dados (`import_months_status`) usada pelo backfill automático de madrugada. | `support:sync_opa` |

#### Overrides de atendente

Cadastro que reclassifica manualmente um `attendant_id` do OPA Suite como agente
virtual (`classification="virtual_agent"`) — usado para corrigir casos em que o painel
externo não identifica corretamente bot vs. humano.

| Método | Path | Descrição | Permissão |
|---|---|---|---|
| GET | `/opa/attendant-overrides` | Lista todos os overrides cadastrados. | `support:sync_opa` |
| POST | `/opa/attendant-overrides` | Cria um override (`attendant_id`, `attendant_name` opcional, `classification`, `active`). `422` em erro de validação de negócio ou `attendant_id` duplicado (constraint única). Grava auditoria. Responde `201`. | `support:sync_opa` |
| PATCH | `/opa/attendant-overrides/{override_id}` | Atualiza campos parciais (`exclude_unset`). `422` em erro de validação. Grava auditoria. | `support:sync_opa` |
| DELETE | `/opa/attendant-overrides/{override_id}` | Remove o override. `404` se não encontrado. Grava auditoria. | `support:sync_opa` |

#### Atendimentos (overview / timeseries / breakdowns / detail / timeline)

Todos os endpoints abaixo (exceto onde indicado) compartilham o mesmo conjunto de
filtros de recorte — `date_from`/`date_to`, `date_basis` (`opened_at` ou `closed_at`,
padrão `opened_at`), `status`, `channel`, `attendant_id`/`attendant`,
`department_id`/`department`, `reason_id`/`reason`, `protocol`, `customer`, `search`, e
os filtros extras agrupados em `OpaExtraFilters` (`tag_id`, `customer_id`, `rating_min`,
`rating_max`, `bot_human` — um de `with_bot`, `without_bot`, `reached_human`,
`bot_only`, `handoff`, `unclassified`). Campos que aceitam múltiplos valores (`status`,
`channel`, `attendant_id`, `department_id`, `reason_id`, `customer_id`, `tag_id`) usam
lista separada por vírgula na querystring.

| Método | Path | Descrição | Permissão |
|---|---|---|---|
| GET | `/opa/attendances` | Lista paginada de atendimentos (`page`, `page_size` 1–200, `sort_by`/`sort_dir`). Campos ordenáveis: `opened_at`, `closed_at`, `protocol`, `customer_name`, `attendant_name`, `department_name`, `reason_name`, `channel`, `status`, `rating`, `tma_seconds`. `422` se `sort_by` inválido. | `support:read` (via `get_current_user`, sem exigência extra) |
| GET | `/opa/overview` | Cards da Visão Geral: total/fechados/abertos, taxa de fechamento, duração média, avaliação média, TMR e TMR geral (com cobertura), atendentes/departamentos distintos, distribuição por canal/status, métricas de cliente (únicos, recorrentes, top recorrentes), top motivos, primeira resposta média, métricas bot/humano e janela real de dados importados (`imported_data_window`). Cada métrica numérica vem como comparação (`current`/`previous`/`absolute_change`/`percentage_change`) contra o período imediatamente anterior de mesma duração (`filters.previous_period()`). `date_from`/`date_to` obrigatórios. | `support:read` |
| GET | `/opa/timeseries` | Série diária do MESMO recorte da Visão Geral (é uma decomposição dos cards, não um cálculo paralelo) — total/fechados/abertos, durações médias, avaliação média por dia local. | `support:read` |
| GET | `/opa/breakdowns` | Ranking por dimensão (`dimension`: `attendant`\|`department`\|`reason`\|`channel`\|`status`\|`customer`), com `sort_by`/`sort_dir`/`limit` (1–200). Cada item traz totais, taxa de fechamento, duração/avaliação média e comparação contra o período anterior (mesma lógica de `previous_period`). `422` se `dimension` ou `sort_by` inválidos. | `support:read` |
| GET | `/opa/attendants/{attendant_id}/summary` | Resumo consolidado de UM atendente no recorte de filtros: totais, taxa de fechamento, TMA/TMR/TMR-geral médios, primeira resposta média, avaliação, métricas de cliente, breakdown por status/motivo/canal e métricas bot/humano. `404` se o atendente não aparece no recorte. | `support:read` |
| GET | `/opa/attendances/{attendance_id}` | Detalhe de um atendimento: dados locais (`local`, sempre presentes) e, se `include_external=true` (padrão), dados enriquecidos ao vivo via API do OPA Suite (`enriched`) — reasons, tags, descrição, observações. Se a chamada externa falhar, `external_detail_available=false` e `external_detail_error` traz a mensagem; a rota não falha por isso. Efeito colateral: se o nome/id do cliente vier diferente do local, atualiza a linha (`db.commit()`). `404` se `attendance_id` não existir. | `support:read` |
| GET | `/opa/attendances/{attendance_id}/timeline` | Linha do tempo de eventos do atendimento (`events`), com flags bot/humano/handoff e, se `include_messages=true` (padrão), a fonte das mensagens (`messages_source`) e eventual erro (`messages_error`). `404` se não existir. | `support:read` |
| GET | `/opa/filters` | Opções para popular os dropdowns de filtro (atendentes, departamentos, canais, status, motivos, etiquetas), opcionalmente recortadas por `date_from`/`date_to`/`date_basis`. Etiquetas vêm da dimensão sincronizada (`SupportOpaDimension`, `dimension_type="tag"`), não do próprio atendimento — só assim há rótulo humano em vez de id cru. | `support:read` |

#### Filtros salvos

| Método | Path | Descrição | Permissão |
|---|---|---|---|
| GET | `/opa/saved-filters` | Lista os filtros visíveis ao usuário: todos com `scope="global"` + os pessoais (`scope="personal"`) dele mesmo. Nunca devolve filtro pessoal de outro usuário. | `support:read` |
| POST | `/opa/saved-filters` | Cria um filtro salvo (`name`, `scope` `personal`\|`global`, `filters` — objeto livre). `scope="global"` exige `support:sync_opa` (checagem inline, `403` caso contrário); filtro global não tem `owner_id` (fica `None`, sobrevive à desativação do autor). Responde `201`. | `support:read` (+ `support:sync_opa` só para `scope="global"`) |
| DELETE | `/opa/saved-filters/{saved_filter_id}` | Remove um filtro salvo. Global exige `support:sync_opa` (`403` caso contrário); pessoal só pode ser removido pelo próprio dono (`404` — não `403` — se não for o dono, para não revelar existência). | `support:read` (+ `support:sync_opa` só para `scope="global"`) |

#### Métricas OPA (`/opa-metrics`)

| Método | Path | Descrição | Permissão |
|---|---|---|---|
| GET | `/opa-metrics` | Métricas agregadas do período (`date_from`/`date_to` obrigatórios, `date_basis`): total, fechados, TMA/TMR/TMR-geral médios (com cobertura do TMR geral), avaliação média, e dois agrupamentos top-20 (`by_attendant`, `by_reason`) com as mesmas médias por grupo. Endpoint mais simples/direto que `/opa/overview` — sem comparação contra período anterior. | `support:read` |

`/opa/breakdowns` (agrupamento genérico por dimensão) já está documentado acima, na
seção de Atendimentos, por reaproveitar o mesmo conjunto de filtros dessa família de
rotas.

#### Tickets IXC / Analytics IXC

Camada "clássica" (KPIs por mês-calendário) e camada "analytics" (Fases 1–6 do plano de
evolução, com período livre `date_from`/`date_to` e janela anterior de mesmo tamanho)
convivem lado a lado — a camada nova é **aditiva**, não substitui a antiga.

| Método | Path | Descrição | Permissão |
|---|---|---|---|
| GET | `/ixc/tickets/overview` | KPIs do topo: incidência parcial do mês (ou só de um `day`, se informado), média histórica no mesmo corte de dia, desvio, severidade e base ativa comparável. `subject_id`/`sector_id` multi-seleção (vírgula), aplicam-se à Visão Geral inteira. | `support:read` |
| GET | `/ixc/tickets/daily-series` | Série diária: mês corrente, mês anterior, média histórica por dia-do-mês e média móvel de 7 dias. | `support:read` |
| GET | `/ixc/tickets/priorities` | Ranking por regional, ordenado pelo maior desvio contra a própria história (indicador antecipado, não substitui O.S.). | `support:read` |
| GET | `/ixc/tickets/city-priorities` | Mesmo ranking, por CIDADE — todas as cidades do sistema com base ativa suficiente, independente de regional (decisão de produto: 2026-09-11, pega problema hiperlocal que se dilui no nível regional). | `support:read` |
| GET | `/ixc/tickets/breakdown` | Drill-down `level` (`regional`\|`city`\|`neighborhood`\|`reason`); cada nível exige os pais já selecionados (`regional` obrigatório para `city`+, `city` obrigatório para `neighborhood`+, `neighborhood` obrigatório para `reason`) — `400` se faltar. `subject_id`/`sector_id` são ortogonais ao nível (filtram qualquer nível, multi-seleção). | `support:read` |
| GET | `/ixc/tickets/filter-options` | Motivos e setores distintos vistos nos atendimentos, para popular dropdowns do drill-down. | `support:read` |
| GET | `/ixc/tickets/taxonomy-mappings` | Lista o de-para motivo → tema → categoria (`support_ixc_taxonomy_mappings`). Tabela nasce vazia; popular é decisão de negócio separada. | `support:read` |
| GET | `/ixc/tickets` | Lista os tickets individuais (protocolo, status, motivo) de um recorte regional/cidade/bairro/motivo — nó final do drill-down. Enriquece cada item com taxonomia (tema/categoria, cache por `subject_id` distinto na página) e `risk_score`/`subtema_inferido` calculados a partir do texto do relato (`ixc_ticket_text_signal.resolve_ticket_risk`). `limit` 1–200, `offset`. | `support:read` |
| GET | `/ixc/analytics/context` | Fase 2: resumo executivo de um escopo qualquer (regional/cidade/bairro + motivo/setor) no modelo de período livre — contagem, contratos, desvio, severidade, alcance (clientes únicos/recorrentes) e principal motivo-driver. `regional` obrigatório para filtrar por `city`; `city` obrigatório para `neighborhood` (`400` caso contrário). | `support:read` |
| GET | `/ixc/analytics/priorities` | Fase 3: ranking do PRÓXIMO NÍVEL relevante, com `dimension` (`regional`\|`city`\|`neighborhood`\|`subject`) escolhida explicitamente. `400` em `ValueError` de domínio. | `support:read` |
| GET | `/ixc/analytics/drivers` | Decomposição do excesso por motivo (`current - esperado`, esperado = mesma janela no período anterior de tamanho igual) com `contribution_pct`. Mesmas regras de dependência hierárquica de `regional`/`city`/`neighborhood` que `/analytics/context`. | `support:read` |
| GET | `/ixc/analytics/bursts` | Fase 4 (`BURST_V1`): compara observado nas últimas 1h/2h/6h contra baseline pré-computado por hora-do-dia/dia-da-semana. `basis="none"` quando ainda não há baseline calculado para o escopo. Escopo `regional` (se informado) ou `global`. | `support:read` |
| GET | `/ixc/analytics/momentum` | Fase 4 (`MOMENTUM_V1`): tendência recente (últimos dias) — "piorando/melhorando/estável", complementar ao desvio pontual de `/tickets/overview` e `/analytics/context` (que respondem "fora da curva hoje", não tendência). | `support:read` |
| GET | `/ixc/analytics/os-conversion` | Fase 6 (`OS_CONVERSION_V1`): quantos atendimentos do recorte viraram O.S. dentro de 2h/6h/24h/48h, via vínculo `OperationOrder.ticket_id == SupportIxcTicket.source_id`. Mede se o indicador antecipado de fato antecipa ação real — não substitui a O.S. como fonte de verdade. | `support:read` |

### Contrato de dados

#### Fuso horário e convenção de datas

Todo filtro de período do módulo interpreta "o dia" no fuso operacional
**`America/Porto_Velho`** (`SUPPORT_TIMEZONE_NAME`, `opa_filters.py:14-15`), não em UTC.
`date_from`/`date_to` são datas locais; `opa_period_bounds()` converte o intervalo
`[date_from 00:00, date_to+1 00:00)` local para os limites UTC equivalentes, usados para
filtrar as colunas `opened_at`/`closed_at` (armazenadas em UTC). O ponto de corte de um
dia, portanto, não é meia-noite UTC. `SupportOpaTimeseriesPoint.day` é explicitamente o
dia **local** de operação, mesma convenção.

Toda janela de consulta de atendimentos OPA é limitada a **no máximo 32 dias**
(`validate_opa_period`, `422` se excedido ou se `date_from > date_to`).

`date_basis` (`opened_at` por padrão, ou `closed_at`) decide se o período filtra pela
abertura ou pelo encerramento do atendimento — em `closed_at`, atendimentos ainda
abertos (`closed_at IS NULL`) nunca aparecem, por definição.

#### TMA e TMR

- **TMA (tempo médio de atendimento)**: no cadastro local, é `tma_seconds`, obtido do
  próprio payload do OPA Suite (campo `tmaSegundos`/`tempo_medio_atendimento_segundos`/
  `tma`, ver `opa_ingestion._duration_seconds`). No detalhe enriquecido ao vivo
  (`_attendance_enriched_detail`), quando a duração vem calculada localmente, ela é
  `closed_at - opened_at` em segundos.
- **TMR (tempo médio de resposta humana)**: `tmr_seconds` é a média dos intervalos entre
  uma mensagem do cliente e a resposta do atendente **humano** seguinte
  (`_human_response_metrics`, `opa_ingestion.py:354-392`). Mensagens de bot são
  descartadas — não fecham o intervalo pendente nem contam como resposta.
- **TMR geral**: `tmr_all_responses_seconds` é a mesma ideia, mas conta resposta de
  **qualquer** atendente (bot, humano ou tipo desconhecido, incluindo o log interno do
  agente virtual "Theo") como resposta válida (`_all_response_metrics`,
  `opa_ingestion.py:399-419`). Serve para comparar com painéis que não distinguem bot de
  humano no TMR; não afeta nem é afetado pelo cálculo de `tmr_seconds`.
- **Cobertura parcial**: o TMR geral tem histórico parcial (campo entrou em produção
  depois do início da base). Por isso toda resposta que o expõe também expõe um
  denominador explícito (`SupportOpaMetricCoverage`: `count`/`total`/`percentage`) — a
  média nunca aparece sem indicar quantos registros do universo total entraram nela.
- **Classificação bot/humano**: `handled_by_bot`, `reached_human`,
  `bot_to_human_handoff` são `bool | None` — `NULL` significa "não classificado"
  (histórico anterior à fase de classificação, ou mensagens indisponíveis) e **nunca**
  deve ser tratado como `False`. O filtro `bot_human=unclassified` existe justamente
  para isolar esse caso; os demais valores (`with_bot`, `without_bot`, `reached_human`,
  `bot_only`, `handoff`) usam `IS TRUE`/`IS FALSE`, que exclui os não classificados dos
  dois lados.

#### Comparação contra período anterior

`/opa/overview` e `/opa/breakdowns` comparam cada métrica contra o período
**imediatamente anterior de mesma duração** (`OpaAttendanceFilters.previous_period()`,
`opa_filters.py:91-104`) — não contra o mesmo período do mês/ano passado. Todos os
demais filtros ativos (motivo, canal, atendente etc.) são preservados no cálculo do
período anterior, via `dataclasses.replace`, para que o "antes" e o "depois" sejam
sempre o mesmo universo de filtros.

#### Multi-seleção via querystring

Parâmetros que aceitam múltiplos valores (ex.: `status`, `channel`, `attendant_id`,
`department_id`, `reason_id`, `customer_id`, `tag_id` nos endpoints OPA; `subject_id`,
`sector_id` nos endpoints IXC) recebem uma string única com valores separados por
vírgula (ex.: `status=aberto,pendente`), nunca `?status=a&status=b` repetido.

#### Tickets IXC como indicador antecipado

Os KPIs/analytics de `/ixc/tickets/*` e `/ixc/analytics/*` **não substituem** a O.S.
como fonte de verdade operacional — são um sinal antecipado (o atendimento/ticket
chega antes da O.S. ser aberta). `/ixc/analytics/os-conversion` existe justamente para
medir se esse indicador de fato antecipa ação real, comparando o lead time entre o
ticket e a O.S. gerada a partir dele.

### Exemplos

#### 1. Visão geral de atendimentos OPA de um dia, filtrando por canal

```
GET /api/support/opa/overview?date_from=2026-09-15&date_to=2026-09-15&channel=whatsapp
Authorization: Bearer <token>
```

Resposta (resumida):

```json
{
  "current_period": { "date_from": "2026-09-15", "date_to": "2026-09-15" },
  "previous_period": { "date_from": "2026-09-14", "date_to": "2026-09-14" },
  "total_attendances": { "current": 312, "previous": 289, "absolute_change": 23, "percentage_change": 7.96 },
  "closure_rate": { "current": 94.2, "previous": 91.0, "absolute_change": 3.2, "percentage_change": 3.52 },
  "average_tmr_seconds": { "current": 58.4, "previous": 63.1, "absolute_change": -4.7, "percentage_change": -7.45 },
  "tmr_all_responses_coverage": { "count": 300, "total": 312, "percentage": 96.15 },
  "bot_human": { "total_attendances": 312, "with_bot": 210, "reached_human": 180, "bot_to_human_handoff": 95 },
  "imported_data_window": { "min_opened_at": "2026-06-01T04:00:00Z", "max_opened_at": "2026-09-16T02:10:00Z", "total_attendances": 48213 }
}
```

#### 2. Drill-down de tickets IXC (regional → cidade)

```
GET /api/support/ixc/tickets/breakdown?level=city&regional=Zona Sul&date_from=2026-09-01&date_to=2026-09-15
Authorization: Bearer <token>
```

Resposta (resumida):

```json
{
  "level": "city",
  "regional": "Zona Sul",
  "city": null,
  "neighborhood": null,
  "items": [
    {
      "key": "porto-velho",
      "label": "Porto Velho",
      "ticket_count": 148,
      "contract_count": 21340,
      "tickets_per_1000_contracts": 6.93,
      "coverage_pct": 98.4,
      "previous_ticket_count": 101,
      "deviation_pct": 46.53
    }
  ]
}
```

#### 3. Disparo de importação manual de um período do OPA Suite, com polling

```
POST /api/support/opa-imports
Authorization: Bearer <token>
Content-Type: application/json

{ "date_from": "2026-09-01", "date_to": "2026-09-15" }
```

```json
{ "run_id": 482, "status": "pending", "date_from": "2026-09-01", "date_to": "2026-09-15",
  "pages_processed": 0, "fetched_count": 0, "created_count": 0, "updated_count": 0,
  "unchanged_count": 0, "rejected_count": 0, "errors": [] }
```

O cliente então consulta `GET /api/support/opa/sync-runs/482` periodicamente até o
`status` mudar para `completed` (ou `failed`/`interrupted`, este último retomável via
`POST /api/support/opa/sync-runs/482/resume`).

---

<a id="gestao"></a>

## Gestão Integrada


> Fonte: `backend/app/modules/management/router.py`, `cases.py`, `schemas.py` e `models.py`.
> Todas as rotas deste documento têm o prefixo `/api/management` (o router é montado com
> `prefix="/management"` e o `main.py` acrescenta o prefixo global `/api`).

### Visão geral

O módulo de Gestão Integrada cobre três frentes que giram em torno da mesma pergunta: **quem
pertence à operação, quem está desviando da meta, e quem já respondeu por isso.**

1. **Estrutura operacional** — o "organograma" real de campo: quais colaboradores existem, quem é
   o supervisor de cada um, a qual modelo de equipe pertencem e sua escala de trabalho (padrão ou
   12x36/alternada). É a base sobre a qual os casos são abertos.
2. **Casos de gestão** — a cobrança formal de um desvio. Um caso nasce automaticamente quando a
   produção de um colaborador fica abaixo da meta do seu modelo de equipe (diário ou mensal), ou
   manualmente quando a matriz identifica um problema de conduta/processo. Cada caso percorre um
   ciclo de vida: `pending` (aberto, aguardando justificativa) → `justified`/`in_progress`
   (supervisor respondeu) → `resolved`/`rejected` (decisão final da matriz).
3. **Justificativas e decisão da matriz** — o supervisor explica o desvio (texto livre + motivo
   pré-cadastrado + plano de ação); a matriz aceita, rejeita ou devolve pedindo complemento. Toda a
   leitura agregada (diagnóstico, pendências por colaborador, justificativas paginadas) existe para
   responder "quem preciso cobrar hoje" sem abrir caso por caso.

Uma regra atravessa o módulo inteiro: **o escopo de visibilidade é aplicado no servidor**, nunca
confiando no filtro que a tela manda. Quem não tem a permissão `management:review` (a matriz) só
enxerga os casos e colaboradores onde é o supervisor responsável, ou que pertencem às regionais que
gerencia (`user.managed_regional`/`managed_regionals`). Ver `cases.case_scope_conditions` e
`cases.member_scope_conditions`.

### Autenticação e permissões

Todas as rotas exigem autenticação (dependência `require_permission("...")` do
`app.core.security`) — não há endpoint público neste módulo. As permissões usadas são:

| Permissão | Uso |
|---|---|
| `management:read` | Leitura geral: dashboard, options, listagem/export/diagnóstico de casos, pendências, justificativas, comentários, motivos, configurações. |
| `management:write_justification` | Justificar um caso (`POST /cases/{id}/justify`), abrir caso do dia/mês sob demanda (`POST /cases/daily`, `POST /cases/monthly`), comentar em um caso. |
| `management:review` | Decisão da matriz sobre um caso (`POST /cases/{id}/review`), revisão em lote (`POST /cases/bulk-review`), criação manual de caso (`POST /cases`). Também é a permissão que dá visibilidade irrestrita no escopo (`cases_engine.can_review`). |
| `management:manage_structure` | Atualizar/reprocessar a estrutura operacional (`POST /structure/refresh`, `PATCH /members/{id}`, sugestão de escala). |
| `management:claim_member` | Reivindicar (assumir supervisão de) um colaborador sem supervisor. |
| `management:audit_structure:read` | Auditoria da Estrutura Operacional Confiável (somente leitura). |
| `management:generate_cases` | Disparar a varredura em lote que abre casos de produtividade de um mês fechado. |
| `management:admin` | Administrar motivos de justificativa (case-reasons) e configurações de limiares/auto-geração. |

Escopo por regional: quando o usuário não tem `management:review`, toda consulta de casos e de
membros é restrita a `supervisor_user_id == user.id` OU `regional IN (regionais geridas pelo
usuário)`. Um caso ou colaborador fora do escopo retorna **404** (não 403) para não revelar sua
existência a quem não deveria vê-lo.

### Endpoints

#### Dashboard / Options / Estrutura

**`GET /options`** — Permissão: `management:read`.
Lista de apoio para formulários: supervisores ativos (`User`) e modelos de equipe ativos
(`OperationTeamModel`), cada um como `{id, name}`. Resposta: `ManagementOptionsOut`.

**`GET /dashboard`** — Permissão: `management:read`.
Painel da estrutura operacional: lista de colaboradores (até 500) com filtros opcionais
(`regional`, `supervisor_user_id`, `status`, `search`, `collaborator_regional`) e um resumo
(`ManagementSummaryOut`) com contadores de membros por status e de casos abertos/atrasados — **os
contadores de caso respeitam o mesmo escopo de visibilidade da lista de membros**, para o painel
nunca contradizer a tabela. Resposta: `ManagementDashboardOut { summary, members[] }`.

**`POST /structure/refresh`** — Permissão: `management:manage_structure`.
Reprocessa a estrutura operacional a partir dos dados de origem (colaboradores/atribuições),
criando candidatos a `ManagementOperationalMember`. Gera log de auditoria. Resposta:
`{ created_candidates: int }`.

**`GET /structure-audit`** — Permissão: `management:audit_structure:read`.
Auditoria somente leitura da "Estrutura Operacional Confiável" — nenhuma chamada ao IXC, nenhuma
alteração de dado. Detecta inconsistências como colaboradores sem tipo de equipe, atribuições sem
modelo de equipe, etc. Resposta: `StructureAuditOut { summary, findings[], critical_count,
attention_count, informative_count, total_findings, generated_at }`.

**`POST /members/{member_id}/claim`** — Permissão: `management:claim_member`.
Supervisor/gerente de base reivindica um colaborador **sem supervisor** para a própria base — sem
exigir `managed_regionals` (propositalmente, para não travar quem mais precisa reivindicar). Falha
com **409** se o colaborador já tiver sido reivindicado por outro supervisor
(`MemberAlreadyClaimedError`). "Roubar" colaborador de outro supervisor exige a ação administrativa
(`PATCH /members/{id}` com `management:manage_structure`), não esta rota. Resposta:
`ManagementOperationalMemberOut`.

**`GET /members/{member_id}/shift-pattern-suggestion`** — Permissão: `management:manage_structure`.
Analisa a produção real dos últimos 21 dias do colaborador e sugere uma escala 12x36 (dia sim, dia
não) quando o padrão bate de forma consistente (≥80% de acerto e sem gap de produção ≥4 dias, que
indicaria afastamento em vez de folga). Nunca grava nada — só preenche o formulário; o supervisor
ainda precisa salvar. Resposta: `ManagementShiftPatternSuggestionOut { suggested_pattern
("alternating"|"inconclusive"), suggested_cycle_days_on, suggested_cycle_days_off,
suggested_anchor_date, confidence, message, daily_production[] }`.

**`PATCH /members/{member_id}`** — Permissão: `management:manage_structure`.
Atualiza campos parciais de um colaborador operacional (`ManagementMemberUpdate`: supervisor, modelo
de equipe, status, notas, escala). Regras de negócio embutidas:
- Trocar `team_model_id` para um modelo 12x36 sem informar `shift_pattern` liga automaticamente a
  escala alternada com os valores padrão do modelo.
- `shift_pattern="alternating"` só é aceito se o modelo de equipe efetivo (pós-update) for elegível
  para 12x36 — caso contrário retorna **422**.
- Mudar `status` para `validated_operation` ou `active_management` grava `validated_by`/
  `validated_at` com o usuário atual.

Status válidos (`OPERATIONAL_MEMBER_STATUSES`): `pending_validation`, `validated_operation`,
`outside_operation` (e demais valores do enum do modelo). Resposta: `{ status: "ok" }`.

#### Casos de Gestão

Todos os endpoints de listagem/export/diagnóstico/pendências/justificativas compartilham a mesma
dependência de filtro (`case_filters_query` → `ManagementCaseFilters`), garantida para nunca
divergir entre telas. Parâmetros de filtro comuns:

| Parâmetro | Descrição |
|---|---|
| `status` | Status exato (`pending`, `justified`, `in_progress`, `resolved`, `rejected`). |
| `severity` | `low` \| `medium` \| `high`. |
| `regional`, `supervisor_user_id`, `case_type`, `reason_id`, `collaborator_id` | Filtros diretos. |
| `reference_year`, `reference_month` | Competência do caso. |
| `reference_date_from`, `reference_date_to` | Faixa de competência (inclusiva). |
| `only_overdue` | Só casos abertos com `due_date` vencido. |
| `only_open` | Só status abertos (`pending`, `justified`, `in_progress`). |
| `search` | ILIKE parcial em responsável, regional ou métrica. |
| `responsible_name` | Nome **exato** do colaborador (case-insensitive). |
| `pending_justification` | Atalho para `status=pending` (ainda sem justificativa). |
| `awaiting_review` | Atalho para `status=justified` (aguardando decisão da matriz). |
| `has_justification` | `true`/`false` — com/sem texto de justificativa. |
| `min_days_pending` | Só casos abertos há pelo menos N dias corridos. |

Combinações contraditórias (ex.: `status=resolved` + `only_open=true`, ou `pending_justification`
junto com `awaiting_review`) retornam **422** com mensagem explicando o conflito, em vez de devolver
0 resultados em silêncio.

**`GET /cases`** — Permissão: `management:read`.
Listagem paginada (`page`, `page_size` até 200), ordenada por severidade (alta primeiro), prazo
mais curto e mais recente. Resposta: `ManagementCasePage { items[], summary, total, page,
page_size }`, onde `summary` (`ManagementCaseSummaryOut`) traz contadores do mesmo recorte filtrado.

**`GET /cases/export`** — Permissão: `management:read`.
Exporta em CSV (delimitador `;`, BOM UTF-8 para abrir acentuação corretamente no Excel) **todo** o
recorte filtrado, sem paginação. Colunas: id, tipo, responsável, regional, competência, métrica,
esperado, realizado, desvio %, severidade, status, em atraso, motivo, justificativa, prazo,
supervisor, datas de criação/justificativa/revisão.

**`GET /cases/diagnostics`** — Permissão: `management:read`.
Agregado "quem mais falha" do recorte filtrado, em três dimensões (top 15 cada): por regional, por
responsável e por motivo — cada bucket com `total`, `open_cases`, `overdue_cases`. Resposta:
`ManagementCaseDiagnosticsOut`.

**`GET /cases/pending-by-collaborator`** — Permissão: `management:read`.
"Quem está devendo justificativa" — uma linha por (colaborador, regional), com idade da pendência e
os IDs dos casos abertos (até 20 por linha) prontos para abrir/justificar. Parâmetro `limit`
(1–1000, padrão 200). Combine com `pending_justification=true` para ver só quem nunca justificou, ou
com a faixa de data para recortar por dia/semana. Resposta: `ManagementPendingByCollaboratorOut {
total_collaborators, total_cases, items[], truncated }`.

**`GET /cases/justifications`** — Permissão: `management:read`.
Leitura achatada e paginada das justificativas do recorte: texto do supervisor, motivo, plano de
ação e decisão da matriz. Parâmetro `include_comments` (padrão `false`) também traz a thread de
comentários de cada caso. Resposta: `ManagementJustificationPage { total, page, page_size, items[]
}`.

**`POST /cases/bulk-review`** — Permissão: `management:review`.
Aplica a mesma decisão (`resolved`/`rejected`/`in_progress`) a vários casos de uma vez. Body:
`ManagementCaseBulkReview { case_ids[] (1–200), status, review_note }`. Casos fora do escopo do
revisor, ou ainda `pending` quando `status=resolved` (sem justificativa), são pulados sem falhar a
chamada inteira. Resposta: `ManagementCaseBulkReviewResult { updated_cases, skipped_pending,
not_found }`.

**`GET /cases/{case_id}`** — Permissão: `management:read`.
Detalhe de um caso (404 se não existir ou estiver fora do escopo). Resposta: `ManagementCaseOut`.

**`POST /cases`** — Permissão: `management:review`.
Criação manual de caso (usada quando o desvio não é de produtividade — conduta, processo,
retrabalho — por isso `metric_name` é texto livre). Se `due_date` não vier, é calculado como
`hoje + management_case_due_days`. Status inicial sempre `pending`. Resposta: `ManagementCaseOut`
(HTTP 201).

**`POST /cases/daily`** — Permissão: `management:write_justification`.
Abre (ou devolve, se já existir) o caso do dia vermelho clicado no drill do calendário. Usa a
mesma permissão de quem justifica (não exige `management:review`) — o supervisor pode abrir a
justificativa do próprio dia sem depender da matriz. Idempotente por (tipo, responsável, regional,
data). Body: `ManagementDailyCaseRequest { responsible_name, regional, reference_date,
expected_value?, actual_value }`. Resposta: `ManagementCaseOut`.

**`POST /cases/monthly`** — Permissão: `management:write_justification`.
Abre (ou devolve) o caso mensal de UM colaborador a partir do "Detalhe Operacional Mensal" do
calendário. Rejeita (**400**) mês corrente/futuro — só mês já fechado. Body:
`ManagementMonthlyCaseRequest { responsible_name, regional, reference_year, reference_month,
expected_value?, actual_value }`. Resposta: `ManagementCaseOut`.

**`POST /cases/generate`** — Permissão: `management:generate_cases`.
Varre a competência informada e abre casos de produtividade para todo colaborador abaixo da meta
(piso `median_from_quantity` do modelo de equipe, não o teto de "excelente"). Idempotente — rodar de
novo no mesmo mês não duplica caso, mas **recalcula** casos ainda `pending` com a produção mais
recente. Body: `ManagementCaseGenerateRequest { reference_year, reference_month }`. Resposta:
`ManagementCaseGenerateResult { created_cases, evaluated_members, skipped_existing,
skipped_insufficient_data, reference_year, reference_month }`.

**`POST /cases/{case_id}/justify`** — Permissão: `management:write_justification`.
Supervisor registra a justificativa. Retorna **409** se o caso já estiver encerrado
(`resolved`/`rejected`). Se `reason.requires_description` for verdadeiro, exige texto com ≥15
caracteres (**400** caso contrário). `status` só pode ser `justified` ou `in_progress`
(`JUSTIFY_TARGET_STATUSES`) — encerrar é decisão exclusiva da matriz via `/review`. Quando o status
final é `justified`, notifica todos os usuários com `management:review`. Body:
`ManagementCaseJustification { reason_id?, justification_text, action_plan?, status }`. Resposta:
`ManagementCaseOut`.

**`POST /cases/{case_id}/review`** — Permissão: `management:review`.
Decisão da matriz: `resolved`, `rejected` ou `in_progress` (devolve pedindo complemento)
(`REVIEW_TARGET_STATUSES`). Retorna **409** ao tentar resolver um caso ainda `pending` (sem
justificativa do supervisor). `review_note`, quando informado, vira um comentário no caso (não
sobrescreve a justificativa). Body: `ManagementCaseReview { status, review_note?, due_date? }`.
Resposta: `ManagementCaseOut`.

**`GET /cases/{case_id}/comments`** — Permissão: `management:read`.
Lista a thread de comentários do caso, ordenada por data de criação. Resposta:
`list[ManagementCaseCommentOut]`.

**`POST /cases/{case_id}/comments`** — Permissão: `management:write_justification`.
Adiciona um comentário ao caso. Body: `ManagementCaseCommentCreate { comment (min. 2 caracteres) }`.
Resposta: `ManagementCaseCommentOut` (HTTP 201).

#### Motivos de Caso (case-reasons)

**`GET /case-reasons`** — Permissão: `management:read`.
Lista os motivos de justificativa pré-cadastrados. Na primeira leitura, semeia 8 motivos padrão
(ex.: "Ausência / afastamento", "Equipe incompleta", "Desempenho individual", "Outro") caso a tabela
esteja vazia — idempotente, nunca sobrescreve o que já foi editado. Parâmetro `include_inactive`
(padrão `false`). Resposta: `list[ManagementCaseReasonOut]`.

**`POST /case-reasons`** — Permissão: `management:admin`.
Cria um motivo novo. Retorna **409** se já existir motivo com o mesmo nome (case-insensitive). Body:
`ManagementCaseReasonCreate { name, description?, active=true, requires_description=false }`.
Resposta: `ManagementCaseReasonOut` (HTTP 201).

**`PATCH /case-reasons/{reason_id}`** — Permissão: `management:admin`.
Atualiza campos parciais de um motivo (404 se não existir; 409 em conflito de nome). Body:
`ManagementCaseReasonUpdate`. Resposta: `ManagementCaseReasonOut`.

#### Configurações / Auto-geração

**`GET /settings`** — Permissão: `management:read`.
Lê os limiares atuais de geração de caso. Resposta: dicionário chave→valor (string) com defaults:

| Chave | Default | Significado |
|---|---|---|
| `management_case_min_deviation_pct` | `15` | Desvio % mínimo abaixo da meta para abrir caso. |
| `management_case_high_severity_pct` | `35` | A partir daqui, severidade `high`. |
| `management_case_low_severity_pct` | `25` | Entre `min_deviation` e este valor, severidade `low`; acima, `medium`. |
| `management_case_min_days_worked` | `5` | Mínimo de dias trabalhados no mês para a média ser considerada. |
| `management_case_due_days` | `7` | Prazo (dias corridos) para o supervisor justificar. |

**`PUT /settings`** — Permissão: `management:admin`.
Atualiza um ou mais limiares (campos `None` são ignorados). Body: `ManagementSettingsUpdate`.
Resposta: o dicionário de configurações atualizado.

**`GET /settings/auto-generate`** — Permissão: `management:read`.
Estado do toggle de geração automática diária. Resposta: `ManagementAutoGenerateSettingsOut {
enabled, last_run_date }`.

**`PUT /settings/auto-generate`** — Permissão: `management:admin`.
Liga/desliga a geração automática (diária) que abre casos de produtividade do mês anterior fechado
**e** casos de dia abaixo da meta de ontem — um único toggle controla os dois fluxos (ver
`modules/management/scheduler.py`). Os botões manuais ("Gerar casos do mês", "Justificar dia")
continuam disponíveis mesmo com o automático ligado. Body: `ManagementAutoGenerateSettingsUpdate {
enabled }`. Resposta: `ManagementAutoGenerateSettingsOut`.

### Exemplos

#### 1. Listar casos pendentes de justificativa, atrasados, de uma regional

```
GET /api/management/cases?pending_justification=true&only_overdue=true&regional=Porto%20Velho&page=1&page_size=50
Authorization: Bearer <token>
```

Resposta (resumida):

```json
{
  "items": [
    {
      "id": 4821,
      "case_type": "daily_performance_below_target",
      "responsible_name": "João da Silva",
      "regional": "Porto Velho",
      "metric_name": "O.S. concluídas no dia",
      "expected_value": 5.0,
      "actual_value": 2.0,
      "deviation_value": 60.0,
      "severity": "high",
      "status": "pending",
      "is_overdue": true,
      "due_date": "2026-09-10",
      "comment_count": 0
    }
  ],
  "summary": { "total_cases": 1, "open_cases": 1, "pending_cases": 1, "overdue_cases": 1, "high_severity_open": 1 },
  "total": 1,
  "page": 1,
  "page_size": 50
}
```

#### 2. Supervisor justifica um caso

```
POST /api/management/cases/4821/justify
Authorization: Bearer <token>
Content-Type: application/json

{
  "reason_id": 2,
  "justification_text": "Equipe operou incompleta no dia - faltou o parceiro de dupla, sem substituto disponível na base.",
  "action_plan": "Escalar reposição de dupla junto ao RH para a próxima semana.",
  "status": "justified"
}
```

Resposta: o `ManagementCaseOut` atualizado com `status="justified"`, `justified_at` preenchido, e
disparo de notificação para todos os usuários com `management:review`.

#### 3. Matriz revisa em lote

```
POST /api/management/cases/bulk-review
Authorization: Bearer <token>
Content-Type: application/json

{
  "case_ids": [4821, 4822, 4830],
  "status": "resolved",
  "review_note": "Justificativas aceitas - equipe incompleta confirmado no registro de escala."
}
```

Resposta:

```json
{ "updated_cases": 2, "skipped_pending": 1, "not_found": 0 }
```

(um dos três casos ainda estava `pending` — sem justificativa do supervisor — e foi pulado, não
resolvido à força.)

### Observações / pontos pouco claros no código

- A rota `PATCH /members/{member_id}` tem `response_model=dict` mas na prática sempre devolve
  `{"status": "ok"}` — o objeto atualizado não é retornado; quem chama precisa buscar o membro de
  novo (`GET /dashboard`) para ver o estado pós-update.
- `ManagementCaseCreate.case_type` e `metric_name` são texto livre (sem enum no schema) — os valores
  usados pelo próprio backend para os tipos automáticos são as constantes
  `CASE_TYPE_PRODUCTIVITY = "productivity_below_target"` e
  `CASE_TYPE_DAILY_BELOW = "daily_performance_below_target"`, mas nada impede a matriz de criar um
  `case_type` arbitrário na criação manual.
  - `severity` idem: aceito como string livre no `ManagementCaseCreate`, mas o backend só calcula
  automaticamente `low`/`medium`/`high` para os casos gerados por regra; num `POST /cases` manual,
  quem chama informa a severidade diretamente.
- Não há endpoint de exclusão (`DELETE`) para casos nem para motivos de justificativa neste
  router — motivos só podem ser desativados (`active=false`) via `PATCH /case-reasons/{id}`, nunca
  removidos.
- `refresh_pending_cases` e `generate_daily_cases_for_date` (funções centrais do motor de
  recalcular/gerar casos automaticamente) não têm endpoint HTTP próprio neste router — são
  chamadas pelo scheduler (`modules/management/scheduler.py`), não expostas diretamente pela API.

---

<a id="agendamento"></a>

## Agendamento


> Fonte: `backend/app/modules/scheduling/router.py`, `schemas.py` e `models.py`.
> Prefixo montado em `backend/app/main.py` (`app.include_router(scheduling_router, prefix=settings_obj.api_prefix)`,
> com `api_prefix = "/api"` e `router = APIRouter(prefix="/scheduling", ...)`).

### Visão geral

O módulo de Agendamento mede **tempo de resposta, produtividade e fila** do setor
responsável por agendar (e reagendar) Ordens de Serviço (O.S.) no IXC. Os principais
conceitos de negócio expostos pela API:

- **TTFA (time-to-first-appointment)**: tempo entre a abertura da O.S. e o primeiro
  agendamento, em minutos "corridos" (`ttfa_raw`) e em minutos "úteis"
  (`ttfa_business`, respeitando janela comercial configurável).
- **SLA de agendamento**: meta de tempo (`scheduling_sla_minutes`) e percentual alvo
  (`scheduling_sla_target_pct`) — uma O.S. é `sla_late` quando ultrapassa a meta.
- **Reagendamento**: evento tipo 10 no log do IXC. A API distingue duas óticas:
  - **por ação do operador** (quem no backoffice clicou em reagendar);
  - **por técnico de campo** (o técnico responsável pela O.S. reagendada, indicando
    instabilidade/retrabalho em campo, não quem operou o sistema).
- **Backlog**: O.S. abertas que ainda não têm agendamento (fila de trabalho pendente).
- **Timeline de O.S.**: histórico completo de eventos (Abertura, Agendamento,
  Reagendar, Fechamento) de uma O.S. específica.
- **Sync com IXC**: todos os KPIs acima respondem sobre dado local já sincronizado
  (rápido). A sincronização com o IXC roda como job assíncrono, com polling via
  `scheduling_jobs` (`job_type="sync"`), tanto em modo incremental (a partir de uma
  marca d'água) quanto em backfill de um intervalo de datas.

### Autenticação e permissões

Todas as rotas exigem **Bearer token** (`HTTPBearer`, `security.py`) e são protegidas
por `require_permission("scheduling:<ação>")`, que resolve o usuário autenticado e
verifica se ele possui a permissão exigida (403 caso não tenha).

Permissões encontradas no router:

| Permissão | Uso |
|---|---|
| `scheduling:read` | Leitura geral — dashboard, reagendamentos, backlog, detalhe/timeline de O.S., filtros salvos (listar), opções de filtro, configurações (leitura), equipe (leitura), resolução de técnicos, status/saúde de sincronização. |
| `scheduling:manage_filters` | Criar/editar/excluir **filtros salvos pessoais** (visão `personal`). Verificado tanto via `dependencies=[...]` no `POST` quanto internamente em `PATCH`/`DELETE` (através de `_can_manage_saved_filter`). |
| `scheduling:views:manage_global` | Criar/editar/excluir **filtros salvos globais** (visão `global`), verificado em `_ensure_global_saved_filter_permission`. |
| `scheduling:views:read_global` | Enxergar filtros salvos com visibilidade `global` de outros usuários na listagem (`GET /saved-filters`). |
| `scheduling:manage` | Atualizar configurações (`PUT /settings`), atualizar equipe (`PUT /team`) e disparar backfill de mensagens (`POST /messages/backfill`). |
| `scheduling:sync` | Disparar sincronização com o IXC (`POST /sync`). |

Regras adicionais de autorização em filtros salvos (implementadas em código, não só
como permissão simples):

- Um filtro `personal` só é visível/editável pelo próprio dono (`user_id`), mesmo
  para quem tem `scheduling:manage_filters`.
- Nome de filtro é único por escopo: um nome global não pode colidir com outro
  global; um nome pessoal não pode colidir com outro pessoal do mesmo usuário
  (case-insensitive).

### Endpoints

#### Dashboard

**`GET /dashboard`** — `scheduling:read`
KPIs agregados do período: resumo (`summary`), distribuição de TTFA, aging do
backlog, série diária, ranking por operador, ranking por filial e por assunto.
Parâmetros: `date_from`, `date_to` (obrigatórios, máx. 366 dias de intervalo),
`filial_ids[]`, `setor_ids[]`, `assunto_ids[]`, `operator_ids[]`, `technician_ids[]`
(todos opcionais, filtros multi-valor), `count_mode` (`all_events` padrão, ou
`distinct_orders`). Resposta: `SchedulingDashboard` (`settings`, `summary`,
`ttfa_distribution[]`, `backlog_aging[]`, `daily_series[]`, `operators[]`,
`filial_ranking[]`, `assunto_ranking[]`).

#### Reagendamento

**`GET /reschedules-by-technician`** — `scheduling:read`
Reagendamentos agrupados pelo **técnico de campo responsável** pela O.S. (métrica de
instabilidade/retrabalho por colaborador de campo — diferente de "quem clicou em
reagendar"). Parâmetros: `date_from`, `date_to`, `filial_ids[]`, `setor_ids[]`,
`assunto_ids[]`. Resposta: `SchedulingRescheduleByTechnician`
(`date_from`, `date_to`, `items[]` com `technician_id`, `technician_name`,
`reschedule_events`).

**`GET /reschedules-by-operator`** — `scheduling:read`
Reagendamentos agrupados **por ação de cada operador** (evento tipo 10, quem
efetivamente reagendou — exclui o 1º agendamento e ações de abrir/fechar O.S.).
Mesmos parâmetros do endpoint anterior. Resposta: `SchedulingRescheduleByOperator`
(`items[]` com `operator_id`, `operator_name`, `is_team_member`,
`reschedule_events`).

**`GET /reschedules/by-day`** — `scheduling:read`
Drilldown paginado do card "Reagendamentos por dia": lista os reagendamentos
(evento tipo 10) de um dia específico. Parâmetros: `day` (deve estar dentro de
`date_from`..`date_to`), `date_from`, `date_to`, `filial_ids[]`, `setor_ids[]`,
`assunto_ids[]`, `operator_ids[]`, `technician_ids[]`, `page` (≥1, padrão 1),
`page_size` (≤200, padrão 50). Resposta: `SchedulingRescheduleDayPage`
(`date`, `items[]`, `total`, `page`, `page_size` — cada item com `ixc_os_id`,
`event_at`, `operator_name`, `origin`, `technician_name`, `filial`, `assunto`,
`mensagem`, `historico`).

**`GET /reschedules/breakdown`** — `scheduling:read`
Ranking agregado (não paginado, sem risco de truncamento) de técnico/operador/filial
com mais reagendamentos naquele dia — usado no painel "Hoje". Mesmos parâmetros de
`/reschedules/by-day` (exceto paginação). Resposta: `SchedulingRescheduleDayBreakdown`
(`date`, `by_technician[]`, `by_operator[]`, `by_filial[]`, cada lista com `key`,
`label`, `count`).

#### Backlog

**`GET /backlog`** — `scheduling:read`
Lista de O.S. sem agendamento (fila pendente), limitada por `limit` (padrão 100,
máx. 500). Parâmetros: `date_from`, `date_to`, `filial_ids[]`, `setor_ids[]`,
`assunto_ids[]`. Resposta: `list[SchedulingBacklogItem]` (`ixc_os_id`, `opened_at`,
`age_hours`, `filial`, `setor`, `assunto`, `status`).

**`GET /backlog/breakdown`** — `scheduling:read`
Onde a fila está concentrada — agregado no banco (sem truncamento de `limit`), usado
pelo card "Fila de trabalho". Mesmos parâmetros de filtro (sem `limit`). Resposta:
`SchedulingBacklogBreakdown` (`by_filial[]`, `by_assunto[]`).

#### Detalhe / Timeline de O.S.

**`GET /orders`** — `scheduling:read`
Drill-through geral: lista as O.S. específicas por trás de qualquer card/gráfico do
dashboard, já com colaborador completo (operador que agendou + técnico designado).
Parâmetros: `date_from`, `date_to`, `filial_ids[]`, `setor_ids[]`, `assunto_ids[]`,
`operator_ids[]`, `technician_ids[]`, `status` (`pending`|`scheduled`), `sla_status`
(`late`|`on_time`, só entre agendadas), `ttfa_bucket`, `backlog_bucket`,
`only_rescheduled` (bool), `reschedule_origin` (`backoffice`|`campo`), `page`,
`page_size` (≤200), `sort_by` (uma das chaves de `ORDER_SORT_KEYS`: `opened_at`,
`first_scheduled_at`, `ttfa_business_minutes`, `reschedule_count`, `filial`, entre
outras), `sort_dir` (`asc`|`desc`). Resposta: `SchedulingOrderDetailPage`
(`items[]`, `total`, `page`, `page_size`).

**`GET /operators/{ixc_operator_id}/events`** — `scheduling:read`
Drill-through "cada ação conta": todo agendamento/reagendamento feito por esse
operador no período, uma linha por evento (diferente de `/orders`, que só enxerga a
O.S. que ele agendou primeiro). Parâmetros: `date_from`, `date_to`, `filial_ids[]`,
`setor_ids[]`, `assunto_ids[]`, `page`, `page_size`. Resposta:
`SchedulingOperatorEventPage` (`items[]` com `ixc_os_id`, `event_type`,
`event_label`, `event_at`, `window_start`, `window_end`, `technician_name`,
`filial`, `assunto`, `mensagem`, `historico`; `total`, `page`, `page_size`).

**`GET /technicians/{ixc_technician_id}/events`** — `scheduling:read`
Drill-through do card "Reagendamentos por técnico": só os reagendamentos (evento
tipo 10) em que esse técnico é o `technician_id` do próprio evento. Mesmos
parâmetros do endpoint de operador. Resposta: `SchedulingTechnicianEventPage`
(equivalente, com `operator_name` no lugar de `technician_name`).

**`GET /orders/{ixc_os_id}/timeline`** — `scheduling:read`
Log completo de uma O.S.: todo evento sincronizado (Abertura, Agendamento,
Reagendar, Fechamento) em ordem, com quem fez cada um. Sem parâmetros de filtro
(um único `ixc_os_id`). Retorna 404 se a O.S. não estiver no escopo sincronizado.
Resposta: `SchedulingOrderTimeline` (`ixc_os_id`, `opened_at`, `filial`, `setor`,
`assunto`, `status`, `events[]`).

#### Filtros Salvos

**`GET /saved-filters`** — `scheduling:read`
Lista os filtros salvos do usuário; inclui também os `global` se o usuário tiver
`scheduling:views:read_global`. Ordenado por visibilidade, atualização e nome.
Resposta: `list[SchedulingSavedFilterOut]`.

**`POST /saved-filters`** — `scheduling:manage_filters` (dependência dupla: no
`dependencies=[...]` do decorator e no parâmetro `user`)
Cria um filtro salvo. Body: `SchedulingSavedFilterCreate` (`name`, `filters`
[`SchedulingSavedFilterValues`], `visibility` — `personal` padrão ou `global`).
Criar com `visibility="global"` exige adicionalmente `scheduling:views:manage_global`.
Nome deve ser único no escopo (409 se duplicado). Resposta: `SchedulingSavedFilterOut`
(201).

**`PATCH /saved-filters/{saved_filter_id}`** — `scheduling:read` (autorização real
via `_can_manage_saved_filter`, não pela dependência de rota)
Atualiza nome/filtros/visibilidade. Filtro pessoal só pode ser editado pelo dono
com `scheduling:manage_filters`; filtro global exige
`scheduling:views:manage_global` (tanto para editar um já-global quanto para
promover um filtro a global). 404 se não encontrado/fora de escopo; 403 se sem
permissão de gerenciar. Body: `SchedulingSavedFilterUpdate` (todos os campos
opcionais). Resposta: `SchedulingSavedFilterOut`.

**`DELETE /saved-filters/{saved_filter_id}`** — `scheduling:read` (mesma checagem de
`_can_manage_saved_filter`)
Exclui o filtro salvo. 404/403 nas mesmas condições do `PATCH`. Resposta: 204 sem
corpo.

#### Configurações / Equipe

**`GET /filters`** — `scheduling:read`
Opções disponíveis para os seletores de filtro (filiais, setores, assuntos,
operadores, técnicos) e o intervalo de dados disponível. Resposta:
`SchedulingFilterOptions`.

**`GET /settings`** — `scheduling:read`
Configurações atuais do módulo (SLA em minutos, % alvo de SLA, janela comercial,
dias úteis, meta diária). Resposta: `dict[str, str]` (sem schema Pydantic
declarado na rota).

**`PUT /settings`** — `scheduling:manage`
Atualiza configurações. Body: `SchedulingSettingsUpdate`
(`scheduling_sla_target_pct`, `scheduling_sla_minutes`, `scheduling_business_start`,
`scheduling_business_end`, `scheduling_business_days`, `scheduling_daily_goal` —
todos opcionais; só os campos não-nulos são persistidos). Resposta: settings
atualizadas.

**`GET /team`** — `scheduling:read`
Operadores vistos no log local, com nome resolvido (busca uma única vez no IXC os
nomes ainda desconhecidos e cacheia em `scheduling_operators`). Resposta:
`list[SchedulingTeamMember]` (`ixc_user_id`, `name`, `is_team_member`), ordenado com
membros da equipe primeiro.

**`PUT /team`** — `scheduling:manage`
Define quais operadores são considerados membros da equipe (`is_team_member`). Body:
`SchedulingTeamUpdate` (`team_member_ids: list[int]`). Resposta:
`list[SchedulingTeamMember]` atualizada.

**`POST /technicians/resolve`** — `scheduling:read`
Resolve no IXC os técnicos (`id_tecnico`) vistos no log local que ainda não têm nome
em cache (`scheduling_technicians`) — chamado uma vez ao abrir a tela. Sem body.
Resposta: `{"resolved": int, "pending": int}`.

#### Sincronização (jobs / status / saúde)

**`POST /sync`** — `scheduling:sync`
Dispara sincronização assíncrona com o IXC como `BackgroundTasks`. Com
`date_from`/`date_to` (as duas ou nenhuma) faz backfill do intervalo; sem
parâmetros, sync incremental a partir da marca d'água. Retorna 409 se já houver job
`sync` em `pending`/`running`. Body: `SchedulingSyncRequest`. Resposta:
`SchedulingSyncJobOut` (`id`, `job_type`, `status`, `result`, `error`, `created_at`,
`finished_at`) — acompanhar evolução via `GET /sync/status`.

**`POST /messages/backfill`** — `scheduling:manage`
Preenche mensagem/histórico dos eventos sincronizados antes desses campos
existirem (operação de correção única — eventos novos já chegam com o texto pelo
sync normal). Retorna 409 se já houver job `backfill_messages` em andamento.
Resposta: `SchedulingSyncJobOut`.

**`GET /messages/backfill/status`** — `scheduling:read`
Último job de `job_type="backfill_messages"`. Resposta: `SchedulingSyncJobOut | null`.

**`GET /sync/status`** — `scheduling:read`
Estado atual da sincronização: marca d'água, último job de sync, totais de O.S. e
eventos no banco local. Resposta: `SchedulingSyncStatus` (`watermark`, `last_job`,
`orders_count`, `events_count`).

**`GET /sync-health`** — `scheduling:read`
Saúde do loop automático incremental (`scheduler.py`) — mesmo contrato usado por
`/ixc-sync-status`/`/opa-sync-status` em outros módulos, para a tela mostrar
"sincronizado há X min" sem depender de clique manual. Resposta:
`SchedulingSyncHealth` (`configured`, `enabled`, `interval_minutes`,
`last_success_at`, `last_attempt_at`, `next_allowed_at`, `last_error`,
`last_error_at`, `consecutive_failures`).

### Exemplos

**1. Dashboard do mês com filtro de filial**

```
GET /api/scheduling/dashboard?date_from=2026-09-01&date_to=2026-09-16&filial_ids=1&filial_ids=3
Authorization: Bearer <token>
```

Resposta (trecho):

```json
{
  "settings": { "scheduling_sla_minutes": "120", "scheduling_sla_target_pct": "90" },
  "summary": {
    "opened_orders": 842,
    "scheduled_orders": 790,
    "pending_orders": 52,
    "sla_rate": 0.91,
    "sla_met": true,
    "ttfa_business": { "median": 38.5, "p90": 105.0, "average": 44.2 },
    "reschedule_rate": 0.07,
    "rescheduled_orders": 55
  },
  "operators": [ { "ixc_operator_id": 214, "operator_name": "...", "total_events": 120 } ]
}
```

**2. Drill-through de O.S. atrasadas e reagendadas por campo**

```
GET /api/scheduling/orders?date_from=2026-09-01&date_to=2026-09-16&sla_status=late&only_rescheduled=true&reschedule_origin=campo&sort_by=ttfa_business_minutes&sort_dir=desc&page=1&page_size=50
Authorization: Bearer <token>
```

Retorna `SchedulingOrderDetailPage` com as O.S. fora do SLA, reagendadas por ação de
técnico de campo, ordenadas pelo TTFA (maior primeiro).

**3. Disparar backfill de sincronização e acompanhar**

```
POST /api/scheduling/sync
Authorization: Bearer <token>
Content-Type: application/json

{ "date_from": "2026-08-01", "date_to": "2026-08-31" }
```

Resposta: `{"id": 57, "job_type": "sync", "status": "pending", ...}`. Acompanhar com:

```
GET /api/scheduling/sync/status
Authorization: Bearer <token>
```

até `last_job.status` chegar em `completed` (ou `failed`, com `error` preenchido).

---

<a id="admin"></a>

## Administração + AI Governance


> Fonte: `backend/app/modules/admin/router.py`, `schemas.py`, `models.py` (tabelas em
> `app/models.py`) e `backend/app/modules/ai_governance/router.py`, `schemas.py`, `models.py`,
> `bootstrap.py`. Documento gerado a partir do código em 2026-09-16 — se divergir do código no
> futuro, o código vence (ver `docs/00-TRILHA-0.md`).

### Visão geral

O módulo **Administração** (rota web `/admin`, prefixo de API `/api/admin`) é o módulo de
governança de acesso do ecossistema UNI Workspace. Ele concentra:

- o catálogo de **permissões** do sistema (as strings `modulo:recurso:acao` que toda rota de
  todo módulo usa em `require_permission(...)`);
- a **visibilidade dos módulos** do workspace por perfil e por usuário individual (o que aparece
  no menu/roteamento do frontend);
- a **estrutura de pessoas** (colaboradores do IXC vinculados a um usuário de portal, hierarquia
  de supervisor/gerente regional, tipo de equipe);
- os **perfis de acesso** (`AccessProfile`), que agrupam permissões e são atribuídos a usuários;
- **overrides individuais de permissão** por usuário (conceder ou negar uma permissão específica
  sem mexer no perfil compartilhado da pessoa).

Dentro do mesmo módulo, com prefixo próprio `/api/admin/ai-governance`, vive o sub-escopo
**AI Governance**: a tela onde a Administração decide o que uma IA (agente conectado via MCP ou
via API key) pode consultar — quais endpoints/tools estão ligados, quais campos de cada entidade
são expostos, quais perfis têm restrição adicional, quais tokens de API existem, e o log de
auditoria de cada chamada feita por uma IA.

**Importância arquitetural:** este é o único módulo que **atribui as próprias permissões usadas
por todos os outros módulos**. `require_permission("operations:read")`,
`require_permission("support:write")`, etc., em qualquer outra rota do sistema, dependem de que
alguém aqui tenha: (1) criado/mantido a permissão no catálogo, (2) incluído essa permissão num
`AccessProfile`, e (3) atribuído esse perfil ao usuário (ou concedido um override individual). Se
a Administração ficar inacessível, nenhuma outra permissão do ecossistema pode ser
criada/ajustada — por isso existe uma trava específica (`ADMIN_GATEKEEPER_PERMISSION`, ver seção
de Perfis de Acesso) impedindo que o último perfil que concede `admin:users:write` seja excluído
ou inativado.

### Autenticação e permissões

Todas as rotas de `/api/admin` e `/api/admin/ai-governance` usam o esquema padrão de sessão do
ecossistema: `Authorization: Bearer <JWT>` obtido em `/api/auth/login`, validado por
`get_current_user` (`backend/app/core/security.py`). Cada rota individual usa
`Depends(require_permission("<chave>"))`, que:

1. resolve o usuário autenticado (`get_current_user`);
2. calcula a permissão efetiva dele (`permissions_for_user` = permissões do perfil ativo, ou do
   papel legado se não houver perfil, **mais** overrides de concessão, **menos** overrides de
   negação — negação sempre vence);
3. responde `403` se a chave exigida não estiver no conjunto efetivo.

Não há verificação adicional de escopo por regional ou por dado individual neste módulo — a
granularidade de acesso aqui é por permissão, não por linha de dado (diferente de outros módulos
operacionais que também filtram por regional do usuário).

Chaves de permissão usadas nas rotas deste documento (todas verificadas apenas no backend, nunca
só no frontend, conforme `AGENTS.md`):

| Chave | Usada em |
|---|---|
| `admin:permissions:read` / `admin:permissions:write` | Catálogo de permissões |
| `admin:modules:read` / `admin:modules:write` | Visibilidade de módulos do workspace |
| `admin:users:read` / `admin:users:write` | Regionais, estrutura de pessoas, overrides de permissão por usuário |
| `admin:roles:read` / `admin:roles:write` | Perfis de acesso |
| `admin:ai_governance:read` / `admin:ai_governance:write` | Endpoints, campos e grants de IA |
| `admin:ai_tokens:manage` | Emissão e revogação de tokens de API de IA |

`admin:users:write` é a **permissão-trava** do ecossistema (`ADMIN_GATEKEEPER_PERMISSION` em
`router.py`): o último perfil ativo que a concede não pode ser excluído nem inativado, para o
ecossistema nunca ficar sem ninguém capaz de administrar acesso.

### Endpoints — Administração

#### Permissões

Catálogo unificado: permissões declaradas em código (`PERMISSION_LABELS`, fixas, só
revogáveis dos perfis) + permissões próprias criadas pela tela (`CustomPermission`, editáveis e
excluíveis).

| Método + path | Descrição | Parâmetros | Permissão | Resposta |
|---|---|---|---|---|
| `GET /permissions` | Lista o catálogo completo, com uso atual de cada permissão (quantos perfis/usuários a têm, quantos overrides individuais existem). | — | `admin:permissions:read` | `EcosystemPermissionOut[]` |
| `POST /permissions` | Cria uma permissão própria (não declarada em código). | Body `CustomPermissionCreate`: `key`, `label`, `module_key?`, `description?`, `sensitive` | `admin:permissions:write` | `201` `EcosystemPermissionOut` |
| `PUT /permissions/{permission_key}` | Atualiza rótulo/módulo/descrição/sensibilidade/ativo de uma permissão própria. Chave nunca muda. | Path `permission_key`; body `CustomPermissionUpdate` (campos parciais) | `admin:permissions:write` | `EcosystemPermissionOut` |
| `DELETE /permissions/{permission_key}` | Exclui uma permissão própria. Permissão de código (`PERMISSION_LABELS`) não pode ser excluída — só removida dos perfis. | Path `permission_key` | `admin:permissions:write` | `204` |

`EcosystemPermissionOut` traz `custom` (própria vs. de código), `profile_count`, `user_count`,
`profile_names` e `override_count`, para a tela mostrar o impacto antes de revogar/excluir.

#### Visibilidade de Módulos (workspace)

Controla quais módulos aparecem para quais perfis/usuários — independente da permissão
funcional exigida pela rota do módulo (ver aviso em `AdminModuleSettingsUpdate`: mudar a
permissão mínima do módulo pela tela deixaria o módulo visível para quem as rotas recusam com
`403`, por isso rota web, prefixo de API e permissão mínima **não** são editáveis por aqui).

| Método + path | Descrição | Parâmetros | Permissão | Resposta |
|---|---|---|---|---|
| `GET /modules` | Lista todos os módulos do `registry.py`, com visibilidade calculada por perfil e por overrides de usuário. | — | `admin:modules:read` | `AdminWorkspaceModuleOut[]` |
| `PUT /modules/{module_key}/settings` | Ajusta nome/descrição/status/ordem de apresentação do módulo. Campo enviado vazio/nulo restaura o padrão do `registry.py`. | Path `module_key`; body `AdminModuleSettingsUpdate` | `admin:modules:write` | `AdminWorkspaceModuleOut` |
| `PUT /modules/{module_key}/visibility` | Define se o módulo é visível para um perfil de acesso. | Path `module_key`; body `AdminModuleVisibilityUpdate`: `profile_id`, `visible`, `reason?` | `admin:modules:write` | `AdminWorkspaceModuleOut` |
| `PUT /modules/{module_key}/user-visibility` | Cria/atualiza uma exceção de visibilidade para UM usuário específico (sobrepõe o que o perfil dele definiria). | Path `module_key`; body `AdminModuleUserVisibilityUpsert`: `user_id`, `visible`, `reason?` | `admin:modules:write` | `AdminWorkspaceModuleOut` |
| `DELETE /modules/{module_key}/user-visibility/{user_id}` | Remove a exceção individual; o usuário volta a seguir a visibilidade do perfil dele. | Path `module_key`, `user_id` | `admin:modules:write` | `AdminWorkspaceModuleOut` |

Toda escrita nesta seção grava em `record_audit_log` (tabelas `workspace_module_settings` /
`workspace_module_visibility`).

#### Estrutura de Pessoas

| Método + path | Descrição | Parâmetros | Permissão | Resposta |
|---|---|---|---|---|
| `GET /operation-regionals` | Regionais distintas e normalizadas encontradas na base analítica de O.S. (`OperationOrder`), para popular seletor de escopo regional em outras telas. | — | `admin:users:read` | `string[]` |
| `GET /people-structure` | Lista completa de colaboradores com resumo (total, ativos, sem supervisor, sem tipo de equipe, pendentes de revisão, por tipo de equipe), opções de supervisor/gerente regional e os enums válidos (`employee_types`, `team_types`, `statuses`). | — | `admin:users:read` | `AdminPeopleStructureOut` |
| `PATCH /people-structure/{collaborator_id}` | Atualiza CPF, tipo de colaborador/equipe, status/observações de estrutura, supervisor e gerente regional de UM colaborador. Campos enviados são parciais (`exclude_unset`). | Path `collaborator_id`; body `AdminPersonStructureUpdate` | `admin:users:write` | `AdminPersonStructureOut` |

Enums válidos (fixos em `router.py`, não editáveis pela tela):
- `employee_type`: `field_technician`, `scheduling_operator`, `internal_support`, `supervisor`,
  `regional_manager`, `headquarters`, `administrative`, `other`.
- `team_type`: `field`, `scheduling`, `internal_support`, `regional`, `administrative`,
  `headquarters`, `other`.
- `structure_status`: `pending_review`, `validated`, `needs_fix`, `outside_operation`,
  `inactive`.

CPF é mascarado na resposta (`cpf_masked`); nunca retornado em texto pleno por esta rota.

#### Perfis de Acesso

`AccessProfile` agrupa um conjunto de chaves de permissão e é atribuído a um ou mais usuários
(`UserAccessProfile`). Substituiu o antigo "papel" (`role`) fixo por usuário — usuário sem
nenhum perfil ativo ainda cai no conjunto de permissões do papel legado (compatibilidade).

| Método + path | Descrição | Parâmetros | Permissão | Resposta |
|---|---|---|---|---|
| `GET /access-profiles` | Lista todos os perfis, com contagem de usuários vinculados. | — | `admin:roles:read` | `AccessProfileOut[]` |
| `POST /access-profiles` | Cria um perfil novo. Nome único (case-insensitive). | Body `AccessProfileCreate`: `name`, `description?`, `active`, `permission_keys[]` | `admin:roles:write` | `201` `AccessProfileOut` |
| `PUT /access-profiles/{profile_id}` | Atualiza nome/descrição/ativo/permissões do perfil. Inativar o **último** perfil ativo que concede `admin:users:write` é bloqueado (`409`) pelo mesmo motivo da exclusão, abaixo. | Path `profile_id`; body `AccessProfileUpdate` (parcial) | `admin:roles:write` | `AccessProfileOut` |
| `DELETE /access-profiles/{profile_id}` | Exclui um perfil, inclusive um perfil de sistema (`is_system`). Se houver usuários vinculados, exige `reassign_profile_id` (query) — move as pessoas para o perfil de destino na mesma transação. Bloqueado (`409`) se for o último perfil ativo que concede `admin:users:write` (trava anti-lockout). | Path `profile_id`; query `reassign_profile_id?` | `admin:roles:write` | `AccessProfileOut` (estado do perfil excluído, com `user_count` antes da exclusão) |

`AccessProfileOut.delete_blocked_reason` informa, quando aplicável, por que o perfil não pode
ser excluído agora (a tela mostra o motivo em vez de só esconder o botão).

#### Overrides de Permissão por Usuário

Permite conceder ou negar UMA permissão específica para uma pessoa, sem criar um perfil
individual nem alterar o perfil compartilhado dela. Negação individual sempre vence concessão do
perfil; concessão individual só soma.

| Método + path | Descrição | Parâmetros | Permissão | Resposta |
|---|---|---|---|---|
| `GET /users/{user_id}/permissions` | O que o perfil da pessoa concede, as exceções (overrides) dela e o resultado efetivo — o mesmo cálculo que `permissions_for_user` roda em toda checagem de permissão do sistema. | Path `user_id` | `admin:users:read` | `UserPermissionOverviewOut` |
| `PUT /users/{user_id}/permissions/{permission_key}` | Cria ou substitui o override desta permissão para o usuário. Idempotente por chave: chamar de novo com efeito diferente TROCA a exceção em vez de empilhar. | Path `user_id`, `permission_key`; body `UserPermissionOverrideUpsert`: `effect` (`grant`\|`deny`), `reason?` | `admin:users:write` | `UserPermissionOverviewOut` |
| `DELETE /users/{user_id}/permissions/{permission_key}` | Remove o override; a pessoa volta a ter exatamente o que o perfil dela concede. | Path `user_id`, `permission_key` | `admin:users:write` | `UserPermissionOverviewOut` |

### Endpoints — AI Governance (`/api/admin/ai-governance`)

Este sub-escopo governa o que uma IA (agente MCP conectado, ou chamada autenticada por
`x-api-key` em `/api/ai/*`) pode ler. Ele não expõe `/api/ai` em si — apenas administra as
tabelas que o *gate* de `/api/ai` e das tools MCP consulta antes de responder qualquer chamada
(ver `app/modules/ai_governance/policy.py` e `gate.py`). Toda escrita aqui chama
`bump_policy_version(db)`, que faz o efeito valer imediatamente (sem reiniciar o processo), e
`record_audit_log` (mesma trilha de auditoria administrativa do restante do módulo `admin`).

No primeiro boot da aplicação, `bootstrap.ensure_ai_governance_seed` semeia `AiEndpoint` e
`AiFieldPermission` com o inventário de endpoints/tools que já existiam (todos entram
habilitados, replicando o comportamento anterior à governança) e capacidades genuinamente novas
que ainda não tinham sido exibidas em produção (entram desabilitadas até a Administração decidir
liberar — ex.: `operations.network.logins`, `operations.network.onu_signal`,
`ai.management_justifications`). O seed é idempotente e nunca sobrescreve uma linha já
configurada manualmente pela Administração.

#### Grants de Endpoint/Campo de IA

| Método + path | Descrição | Parâmetros | Permissão | Resposta |
|---|---|---|---|---|
| `GET /endpoints` | Lista todos os endpoints/tools governáveis (`AiEndpoint`), ordenados por chave. | — | `admin:ai_governance:read` | `AiEndpointOut[]` |
| `PATCH /endpoints/{endpoint_key}` | Liga/desliga um endpoint/tool nas três dimensões independentes: `enabled_api` (rotas REST `/api/ai/...`), `enabled_mcp` (tools MCP), `enabled_ai` (chave-mestra geral). | Path `endpoint_key`; body `AiEndpointUpdate` (campos parciais, `extra="forbid"`) | `admin:ai_governance:write` | `AiEndpointOut` |
| `GET /fields` | Lista o estado administrável de cada campo de cada entidade exposta a IA (filtro opcional por entidade). Completa sob demanda qualquer campo novo do catálogo (`field_registry`) que ainda não tenha linha, para a tela nunca mostrar "campo inexistente". | Query `entity?` | `admin:ai_governance:read` | `AiFieldPermissionOut[]` |
| `PATCH /fields/{entity}/{field}` | Ajusta as capacidades do campo: `filterable`, `text_filterable`, `groupable`, `returnable`, `selectable`, `detail_available`, e a chave-mestra `enabled` (campo indisponível quando `False`, independente das demais capacidades). `sensitive` fica fora deste schema de propósito — é calculado pelo catálogo, não um toggle administrativo. | Path `entity`, `field`; body `AiFieldPermissionUpdate` (parcial, `extra="forbid"`) | `admin:ai_governance:write` | `AiFieldPermissionOut` |
| `GET /profiles/{profile_id}/endpoint-grants` | Lista as restrições adicionais de endpoint para um `AccessProfile` (ausência de linha = sem restrição extra; presença de ao menos uma linha liga o perfil a um modo allow-list para os endpoints listados). | Path `profile_id` | `admin:ai_governance:read` | `AiProfileEndpointGrantOut[]` |
| `PUT /profiles/{profile_id}/endpoint-grants/{endpoint_key}` | Cria/atualiza a restrição de um endpoint para o perfil. | Path `profile_id`, `endpoint_key`; body `AiProfileEndpointGrantUpsert`: `granted` | `admin:ai_governance:write` | `AiProfileEndpointGrantOut` |
| `DELETE /profiles/{profile_id}/endpoint-grants/{endpoint_key}` | Remove a restrição (volta ao comportamento geral de `AiEndpoint`). | Path `profile_id`, `endpoint_key` | `admin:ai_governance:write` | `204` |
| `GET /profiles/{profile_id}/field-grants` | Lista as restrições adicionais de campo para o perfil. | Path `profile_id` | `admin:ai_governance:read` | `AiProfileFieldGrantOut[]` |
| `PUT /profiles/{profile_id}/field-grants` | Cria/atualiza a restrição de um campo (`entity`+`field`) para o perfil — por exemplo, liberar um campo sensível só para o perfil Gestor mesmo que esteja `enabled=True` no geral. | Path `profile_id`; body `AiProfileFieldGrantUpsert`: `entity`, `field`, `granted` | `admin:ai_governance:write` | `AiProfileFieldGrantOut` |
| `DELETE /profiles/{profile_id}/field-grants/{entity}/{field}` | Remove a restrição de campo do perfil. | Path `profile_id`, `entity`, `field` | `admin:ai_governance:write` | `204` |

Perfis reaproveitam o `AccessProfile` já existente do módulo Administração — não há uma
hierarquia de perfil paralela para IA.

#### Tokens de API

Uma chamada a `/api/ai/*` autentica por header `x-api-key` (`APIKeyHeader`, não Bearer/JWT). O
gate (`app/modules/ai/auth.py`) reconhece dois tipos de credencial, combinados nesta listagem:

- **`AiApiToken`** (`source: "token"`) — modelo atual (Fase 5 do plano de migração), com escopo
  (`scopes[]`) e expiração opcional (`expires_at`). É o que estas rotas emitem/revogam.
- **`ApiKeyCredential`** (`source: "legacy"`) — chaves emitidas antes da Fase 5, sem conceito de
  escopo (`scopes: null` = acesso irrestrito, nunca bloqueado por `enforce_token_scope`).
  Continuam listadas e revogáveis aqui para preservar o acesso já concedido, mas novas emissões
  usam sempre `AiApiToken`.

Todo token é emitido em nome de um **usuário de serviço** compartilhado
(`ai-service@internal.souuni.com`, papel `ai_service`), criado sob demanda na primeira emissão.
O escopo real de cada token vem de `AiApiToken.scopes`, não deste usuário — não há um usuário de
serviço por token.

| Método + path | Descrição | Parâmetros | Permissão | Resposta |
|---|---|---|---|---|
| `GET /tokens` | Lista tokens `AiApiToken` + chaves legado `ApiKeyCredential`, combinados e ordenados por data de criação (mais recente primeiro). | — | `admin:ai_governance:read` | `AiApiKeyOut[]` |
| `POST /tokens` | Emite um token novo. Gera a chave bruta com `secrets.token_urlsafe(32)`, grava só o hash (`hash_api_key`) e o prefixo (12 chars, usado para localizar candidatos sem varrer a tabela inteira). | Body `AiApiKeyCreate`: `name`, `scopes[]` (subconjunto de `AI_API_TOKEN_SCOPES`), `expires_in_days?` (1–3650) | `admin:ai_tokens:manage` | `201` `AiApiKeyCreateResponse` (`key` + `raw_key`) |
| `DELETE /tokens/{source}/{token_id}` | Revoga um token (`source="token"`) ou uma chave legado (`source="legacy"`): marca `active=False` e grava `revoked_at`. | Path `source` (`token`\|`legacy`), `token_id` | `admin:ai_tokens:manage` | `AiApiKeyOut` |

Escopos válidos hoje (`AI_API_TOKEN_SCOPES`): `orders.read`, `orders.detail`, `orders.sla`,
`orders.aggregate`, `infra.read`, `users.read`, `management.read`. Só `orders.read` e
`orders.detail` são de fato checados hoje (`enforce_token_scope`, em `opr_search_orders` e
`opr_order_details`) — os demais existem reservados para quando outras rotas passarem a validar
escopo, sem exigir migration nova (a coluna já é uma lista livre).

**A chave bruta (`raw_key`) só aparece nesta resposta de criação — não fica recuperável depois**
(o banco grava apenas o hash). A tela/cliente precisa copiá-la e guardá-la na hora.

#### Logs de Auditoria de Acesso

| Método + path | Descrição | Parâmetros | Permissão | Resposta |
|---|---|---|---|---|
| `GET /audit-logs` | Lista chamadas de IA registradas em `AiAccessAuditLog`, mais recentes primeiro. Nunca grava o conteúdo sensível retornado — `filters_summary` guarda só nomes de campo e quantidade de valores, não os valores em si. | Query `origin?`, `endpoint_key?`, `status?`, `limit` (1–500, padrão 100) | `admin:ai_governance:read` | `AiAccessAuditLogOut[]` |

Cada linha traz: usuário e/ou token associado (nome/e-mail resolvidos), origem (`api`\|`mcp`),
`endpoint_key`, resumo de filtros aplicados, campos solicitados, modo de resposta, quantidade de
resultados, duração em ms, status (`success`/erro) e mensagem de erro quando houver.

#### Como um grant/token aqui habilita uma chamada em `/api/ai`

Quando um agente de IA chama `/api/ai/...` com `x-api-key`, o fluxo passa por estas camadas,
todas alimentadas pelas tabelas que este sub-módulo administra:

1. **Autenticação da chave** (`ai/auth.py:_resolve_api_key_context`): resolve a chave contra
   `AiApiToken` (nova) ou `ApiKeyCredential` (legado) pelo prefixo + hash; rejeita chave
   revogada/expirada/inativa.
2. **Escopo do token** (`enforce_token_scope`): se o token tem `scopes` definidos, a rota
   individual (hoje só as duas citadas acima) exige que o escopo pedido esteja na lista.
3. **Permissão funcional do usuário de serviço** (`require_ai_permission` /
   `permissions_for_user`): a mesma checagem de permissão do resto do sistema, aplicada ao
   usuário de serviço vinculado ao token.
4. **Política de endpoint/campo** (`ai_governance/gate.py`, fora deste documento): verifica se
   `AiEndpoint.enabled_api`/`enabled_mcp`/`enabled_ai` está ligado para a chave do endpoint
   chamado, se há restrição adicional (`AiProfileEndpointGrant`) para o perfil do usuário de
   serviço, e filtra a resposta pelos campos permitidos em `AiFieldPermission` +
   `AiProfileFieldGrant`.
5. **Auditoria**: a chamada é registrada em `AiAccessAuditLog`, visível em `GET /audit-logs`.

Desligar um `AiEndpoint` ou um campo aqui bloqueia o endpoint/tool correspondente
**imediatamente**, sem reiniciar o processo — cada escrita chama `bump_policy_version`, que o
gate consulta antes de aplicar a política em cache.

### Exemplos

#### 1. Criar um perfil de acesso e atribuir permissões

```http
POST /api/admin/access-profiles
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "name": "Supervisor Regional Norte",
  "description": "Acesso de leitura à operação e gestão da regional Norte.",
  "active": true,
  "permission_keys": ["operations:read", "management:read", "support:read"]
}
```

Resposta `201`:

```json
{
  "id": 14,
  "name": "Supervisor Regional Norte",
  "description": "Acesso de leitura à operação e gestão da regional Norte.",
  "legacy_role": null,
  "active": true,
  "is_system": false,
  "permission_keys": ["management:read", "operations:read", "support:read"],
  "user_count": 0,
  "created_at": "2026-09-16T12:00:00Z",
  "updated_at": "2026-09-16T12:00:00Z",
  "delete_blocked_reason": null
}
```

#### 2. Habilitar um endpoint de IA e liberar um campo sensível só para um perfil

```http
PATCH /api/admin/ai-governance/endpoints/operations.network.onu_signal
Authorization: Bearer <jwt>
Content-Type: application/json

{ "enabled_api": true, "enabled_mcp": true, "enabled_ai": true }
```

```http
PUT /api/admin/ai-governance/profiles/14/field-grants
Authorization: Bearer <jwt>
Content-Type: application/json

{ "entity": "operation_order", "field": "technical_report", "granted": true }
```

Ambas as chamadas exigem `admin:ai_governance:write` e disparam `bump_policy_version` — o
efeito vale na próxima chamada de IA, sem reiniciar o backend.

#### 3. Emitir um token de API para um agente de IA

```http
POST /api/admin/ai-governance/tokens
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "name": "Agente de suporte N1 - piloto",
  "scopes": ["orders.read", "orders.detail"],
  "expires_in_days": 90
}
```

Resposta `201` (a única vez que a chave bruta aparece):

```json
{
  "key": {
    "id": 7,
    "source": "token",
    "name": "Agente de suporte N1 - piloto",
    "owner_name": "Serviço de IA",
    "owner_email": "ai-service@internal.souuni.com",
    "key_prefix": "aB3dE7fG9hJk",
    "scopes": ["orders.read", "orders.detail"],
    "expires_at": "2026-12-15T12:00:00Z",
    "active": true,
    "last_used_at": null,
    "created_at": "2026-09-16T12:00:00Z",
    "revoked_at": null
  },
  "raw_key": "aB3dE7fG9hJk...<resto do segredo>"
}
```

O agente passa a autenticar chamadas em `/api/ai/*` com `x-api-key: <raw_key>`, restrito aos
escopos `orders.read`/`orders.detail` e a tudo que a política de endpoint/campo já permitir.

### Observações / pontos de atenção

- `GET /access-profiles/{id}` (leitura de um único perfil) e `GET /users` (lista de usuários
  para escolher em `reassign_profile_id`/overrides) **não existem neste módulo** — a listagem
  completa (`GET /access-profiles`, `GET /people-structure`) é o que a tela usa para montar
  seletores; a criação/edição de usuário propriamente dita fica no módulo de autenticação
  (`users.router`, fora do escopo deste documento).
- O e-mail de serviço (`ai-service@internal.souuni.com`) e o papel `ai_service` são fixos em
  código (`router.py` / `security.py:PROFILE_LABELS`), não configuráveis pela tela.
- Não há paginação em nenhuma listagem deste módulo (`GET /permissions`, `/modules`,
  `/people-structure`, `/access-profiles`, `/endpoints`, `/fields`, `/tokens`) — todas retornam a
  coleção inteira. Só `GET /audit-logs` tem `limit` (paginação simples por corte, sem cursor).

---

<a id="ai"></a>

## Agente de IA


> Fonte: `backend/app/modules/ai/router.py`, `backend/app/modules/ai/schemas.py`,
> `backend/app/modules/ai/auth.py`, `backend/app/modules/ai_governance/gate.py`.
> Este documento cobre só o módulo `ai` (dados). Emissão/gestão de chaves e das
> permissões de IA fica em `/api/admin/ai-governance`
> (`backend/app/modules/ai_governance/router.py`) — ver `docs/api-admin.md`, seção
> "AI Governance"; não duplicado aqui.

### Visão geral

`/api/ai` é uma API **somente leitura**, pensada para ser consumida por um agente
de IA externo (ex.: uma Custom GPT Action) em vez de por um usuário navegando na
tela. Ela espelha os mesmos dados que as telas de Operação, Gestão Integrada e
Suporte já mostram — agregações, séries temporais, busca paginada de O.S. e de
login, telemetria de rede, casos de Gestão Integrada e suas justificativas — mas
devolve JSON em vez de HTML, com filtros e paginação pensados para uma IA montar a
própria consulta.

Não há nenhuma rota de escrita neste módulo. Todos os 26 endpoints de dado são
`GET`/`POST` de consulta; os `POST` existem só porque o corpo da requisição carrega
filtros compostos demais para caber numa query string (o schema OpenAPI publicado
por este módulo marca isso explicitamente, veja `openapi.json` mais abaixo).

Existe um 27º endpoint, `GET /api/ai/openapi.json`, que não é dado nenhum: é o
manual de instruções da própria API (schema OpenAPI reduzido, só com as rotas deste
módulo) para importação automática por um agente de IA.

### Autenticação

**Este módulo usa um esquema de autenticação separado do login normal de usuário
(sessão/JWT).** A equipe que for integrar um agente de IA a este sistema deve usar
chave de API, não as credenciais de um usuário humano.

#### Como o cliente se autentica

Toda chamada (exceto `GET /api/ai/openapi.json`) precisa do header:

```
x-api-key: <chave>
```

A chave é validada por `require_api_key_context`/`require_api_key_user`
(`backend/app/modules/ai/auth.py`), que:

1. Pega os 12 primeiros caracteres da chave (`API_KEY_PREFIX_LENGTH`) para localizar
   candidatas por `key_prefix`, e então confere o hash completo (`verify_api_key`) —
   a chave em si nunca é armazenada em texto puro.
2. Procura primeiro em `AiApiToken` (tokens novos, com escopo — tabela de
   `ai_governance`). Se achar um token ativo, não revogado e não expirado, resolve
   para esse usuário de serviço e para a lista de escopos do token
   (`ApiKeyContext.scopes`).
3. Se não achar em `AiApiToken`, procura em `ApiKeyCredential` (chave "legado", sem
   conceito de escopo, anterior à introdução da governança de IA). Uma chave legado
   resolve com `scopes=None`, o que **nunca** é bloqueado por
   `enforce_token_scope` — mantém o comportamento antigo de acesso irrestrito.
4. Qualquer falha (chave ausente, prefixo sem candidata, hash não bate, usuário
   inativo, token expirado/revogado) devolve sempre o mesmo erro genérico
   `401 — "Chave de API inválida."`, de propósito: a mensagem não distingue "não
   existe" de "revogada"/"expirada" para não ajudar quem estiver tentando adivinhar
   chaves.
5. Toda chamada autenticada com sucesso atualiza `last_used_at` da chave/token.

A chave resolve para um **usuário de serviço** (`role="ai_service"`), não para uma
pessoa da equipe — por isso as rotas de Gestão Integrada não aplicam escopo por
supervisor/regional a este usuário (ver seção Gestão abaixo): ele não é supervisor
de ninguém.

#### Duas camadas de autorização, aplicadas em conjunto

Depois que a chave é validada, cada rota (dependendo do endpoint — ver tabela mais
abaixo) aplica até três verificações adicionais, nesta ordem:

1. **Permissão da chave a nível de router** — todo o router tem
   `dependencies=[Depends(require_ai_permission("ai:query"))]`: se o usuário de
   serviço da chave não tiver a permissão `ai:query`, toda e qualquer rota deste
   módulo devolve `403` antes mesmo do corpo da requisição ser lido.
2. **Escopo do token** (só tokens novos — `AiApiToken`) — `enforce_token_scope`
   confere se o escopo específico da operação (ex.: `orders.read`,
   `management.read`, `infra.read`) está entre os escopos concedidos ao token.
   Chave legado (`scopes=None`) nunca é bloqueada aqui.
3. **Política de governança de IA por endpoint/campo** — `enforce_ai_endpoint_for_user`
   (`backend/app/modules/ai_governance/gate.py`) resolve a `EffectivePolicy` vigente
   para o usuário de serviço e confere se aquele `endpoint_key` específico (ex.:
   `ai.search_orders`, `ai.login_status`, `ai.management_cases`) está habilitado
   para a origem `"api"`. A mesma política também valida, campo a campo, qualquer
   `fields=[...]` explícito pedido no corpo (`enforce_requested_fields`) e qualquer
   `date_field` explícito (`enforce_date_field`) — rejeitando com `422` em vez de
   silenciosamente ignorar um campo não autorizado.

**Importante — nem toda rota passa pelas três camadas.** Só as rotas que recebem
`context: ApiKeyContext = Depends(require_api_key_context)` aplicam o escopo do
token (camada 2) e chamam `record_ai_access` para auditoria (log de quem chamou o
quê, com quais filtros, quantos resultados, em quantos ms). As rotas que recebem
apenas `user: User = Depends(require_api_key_user)` — `aggregate-orders`,
`orders-timeseries`, `backlog-aging`, `backlog-history`, `filter-options`,
`warranty-analytics`, `team-targets`, `team-target-performance` — ficam só na
camada 1 (permissão `ai:query` do router) e **não** geram registro de auditoria
nem exigem escopo de token. `GET /fields` é um caso intermediário: usa
`require_api_key_user` (sem escopo de token), mas chama
`enforce_ai_endpoint_for_user` para aplicar a política (camada 3) antes de devolver
o catálogo. Isso está refletido endpoint a endpoint na tabela da seção seguinte.

#### Onde tokens e permissões são administrados

A emissão de tokens (`AiApiToken`, com escopo e expiração), a concessão/revogação de
permissões (`endpoint_key` habilitado por perfil, campos habilitados/sensíveis) e a
consulta do log de auditoria (`record_ai_access`) são todas administradas pela API
de administração em `/api/admin/ai-governance`
(`backend/app/modules/ai_governance/router.py`) — **não documentada aqui**; veja
`docs/api-admin.md`, seção "AI Governance". Quem for integrar um agente de IA novo
precisa primeiro que um administrador crie um token lá (com os escopos e o acesso a
endpoints/campos necessários) antes de conseguir chamar qualquer rota deste módulo.

O catálogo dinâmico `GET /api/ai/fields` (abaixo) é a forma de o próprio agente
consultar, em tempo real, quais campos estão liberados para o token que ele está
usando — reflete a política vigente, não um estado estático do código.

### Endpoints

Legenda das colunas: **Camadas** = quais das 3 camadas de autorização descritas
acima se aplicam (sempre inclui a 1); **Escopo** = escopo de token exigido
(camada 2, só tokens novos); **endpoint_key** = chave de política de governança
(camada 3, quando existe).

#### Operação (espelha `operations/router.py` — Ordens de Serviço)

| Método + path | Descrição | Camadas | Escopo | endpoint_key | Resposta |
|---|---|---|---|---|---|
| `POST /api/ai/aggregate-orders` | Agrega O.S. por 1 a 3 dimensões (`group_by`) e uma métrica (`quantidade_aberta`, `quantidade_fechada`, `taxa_sla`, `horas_medias`, `quantidade_atrasada`, `quantidade_backlog`, ou métricas de horas entre marcos do ciclo de vida), com o mesmo conjunto de filtros (`AiOrderFilters`) usado no resto do sistema. | 1 | — | — | `dict` livre (chave `label` por dimensão única, ou uma chave por dimensão em agrupamento composto) |
| `POST /api/ai/orders-timeseries` | Série temporal de O.S. abertas/fechadas/saldo, por dia/semana/mês, com `group_by` opcional. | 1 | — | — | `AiTimeseriesResponse` (`meta` + `data: [{period_start, quantity, group?, sla_rate?}]`) |
| `POST /api/ai/search-orders` | Busca paginada de O.S. por período + filtros + palavra-chave, com seleção de campos (`fields`) e modo resumido (`response_mode=summary`). `date_field` escolhe explicitamente o marco de data usado no filtro (padrão: aberta OU fechada no período). | 1, 2, 3 | `orders.read` | `ai.search_orders` | `{items: [AiOrderSearchItem...], total_encontrado, page, page_size, has_more}` |
| `POST /api/ai/orders/details` | Detalhe de uma ou mais O.S. por `order_code` e/ou `source_order_id` (OS_ID do IXC) — não exige período, ao contrário de `search-orders`. | 1, 2, 3 | `orders.detail` | `ai.order_details` | `{items: [dict...], not_found_order_codes, not_found_source_order_ids}` |
| `POST /api/ai/backlog-aging` | Backlog aberto numa data, com idade média/mediana e faixas de atraso (>1/3/5/7/15 dias), agrupado por uma dimensão. | 1 | — | — | `AiBacklogAgingResponse` (`meta` + `data: [AiBacklogAgingItem...]`) |
| `POST /api/ai/backlog-history` | Série histórica diária de backlog/backlog atrasado (snapshot pré-agregado — só existe dado desde a entrada em produção da captura). `group_by` limitado a `regional`/`team_model`/`sector`/`city`. | 1 | — | — | `list[AiBacklogHistoryPoint]` (`snapshot_date, quantity, group?, captured_at`) |
| `POST /api/ai/warranty-analytics` | Taxa de garantia de ativação (Manutenção aberta ≤30 dias após fechamento de Ativação/Mud. Endereço/Mud. Tecnologia no mesmo contrato), com breakdown por regional/diagnóstico/assunto/tipo de origem. | 1 | — | — | `AiWarrantyAnalyticsResponse` |
| `POST /api/ai/team-targets` | Metas de equipe (por modelo + tipo de período: dia útil/sábado/domingo/mensal) vigentes numa data de referência. | 1 | — | — | `list[AiTeamTargetItem]` |
| `POST /api/ai/team-target-performance` | Produção realizada (O.S. fechadas) x meta vigente em cada bucket, por modelo de equipe. Só inclui modelos com produção real no período. | 1 | — | — | `AiTeamTargetPerformanceResponse` (`meta` + `data`) |
| `GET /api/ai/fields` | Catálogo dinâmico de campos e capacidades (`filterable`, `text_filterable`, `groupable`, `returnable`, `selectable`, `detail_available`, `sensitive`, habilitado ou não por origem) — reflete a política vigente para o token que chamou, não um estado fixo do código. | 1, 3 | — | `ai.list_fields` | `list[AiFieldCatalogItem]` |
| `POST /api/ai/filter-options` | Opções válidas de filtro (regionais, cidades, tipos, etc.) dentro de um período — mesma fonte que popula os `<select>` da tela. | 1 | — | — | `OperationFilters` |

#### Infraestrutura / rede (espelha `operations/router.py` — logins, ONU, incidente)

Todas as rotas abaixo exigem o escopo de token `infra.read` e passam pelas 3
camadas de autorização.

| Método + path | Descrição | endpoint_key | Resposta |
|---|---|---|---|
| `POST /api/ai/infra/offline-login-clusters` | Agrupa logins que caíram numa janela de tempo e estão geograficamente próximos — candidato a rompimento de fibra num trecho, distinto de queda isolada. | `ai.offline_login_clusters` | `OperationOfflineLoginClustersOut` |
| `POST /api/ai/infra/login-status` | Status ATUAL de conectividade por login (individual, por busca geográfica ou por regional) — estado agora e há quanto tempo (`status_changed_at`). | `ai.login_status` | `list[OperationLoginStatusOut]` |
| `POST /api/ai/infra/search-logins` | Busca paginada de login (paginação real, filtros de PON/transmissor/contrato via join com telemetria ONU, datetime completo `gte/gt/lte/lt/eq`). | `ai.search_logins` | `OperationLoginSearchResultOut` |
| `POST /api/ai/infra/login-detail` | Detalhamento completo de um login: identificação, status com tempo calculado, telemetria ONU/PON e histórico recente de conexão/desconexão. | `ai.login_detail` | `OperationLoginDetailOut` (404 se login não encontrado) |
| `POST /api/ai/infra/login-aggregate` | Contagem de logins por dimensão (`regional`, `online`, `transmitter_id`, `pon_id`, `last_drop_cause`) — detecção de incidente coletivo sem baixar registro a registro. | `ai.login_aggregate` | `OperationLoginAggregateResponseOut` |
| `POST /api/ai/infra/login-outages` | Logins offline agora que caíram dentro de `[since, until]` — candidatos a incidente coletivo quando concentrados na mesma regional/PON. | `ai.login_outages` | `OperationLoginOutagesResponseOut` |
| `POST /api/ai/infra/login-timeseries` | Série temporal de conectados/desconectados/quedas novas/reconexões novas, um ponto por captura real do snapshot periódico. | `ai.login_timeseries` | `OperationLoginTimeseriesResponseOut` |
| `POST /api/ai/infra/login-incident-analysis` | Funil de incidente coletivo numa chamada só: quedas novas, ainda offline, reconexões, quebra por regional/transmissor/PON/causa e clusters geográficos, já agregados no backend. | `ai.login_incident_analysis` | `OperationLoginIncidentAnalysisOut` |
| `POST /api/ai/infra/coordinate-quality` | Auditoria de qualidade de latitude/longitude por regional (`operations_orders`, `operations_login_current_status` ou `operations_onu_signal_current`) — só classifica/conta, nenhuma correção automática. Usar antes de confiar em qualquer cluster geográfico. | `ai.coordinate_quality` | `OperationCoordinateQualityResponseOut` |
| `POST /api/ai/infra/onu-signal` | Telemetria óptica/ONU atual (transmissor, sinal RX/TX em dBm, serial, causa da última queda). Só cobre logins já monitorados pelo sistema. | `ai.onu_signal` | `list[OperationOnuSignalOut]` |
| `POST /api/ai/infra/onu-signal-history` | Série histórica de telemetria óptica/ONU (um ponto por captura). Exige `login_ids` e/ou `onu_serials`. Cobertura parcial por desenho: ausência de ponto não significa sinal bom, significa que não foi medido naquele período. | `ai.onu_signal_history` | `list[OperationOnuSignalHistoryItemOut]` |

#### Gestão Integrada (espelha `management` — casos e justificativas de produtividade)

Todas as rotas abaixo exigem o escopo de token `management.read` e passam pelas
3 camadas de autorização. Compartilham o mesmo bloco de filtros
(`AiManagementCaseFiltersRequest`: `status`, `severity`, `regional`,
`supervisor_user_id`, `case_type`, `reference_year`/`reference_month`,
`only_overdue`, `only_open`, `search`, `responsible_name`, `collaborator_id`,
`reference_date_from`/`reference_date_to`, `reason_id`, `pending_justification`,
`awaiting_review`, `has_justification`, `min_days_pending`).

**Atenção — sem escopo de supervisor.** A chave de API resolve para o usuário de
serviço `ai_service`, que não é supervisor de ninguém nem tem regionais atribuídas;
por desenho, estas rotas **não** aplicam o mesmo recorte por supervisor que a tela
aplica a um usuário humano logado (isso resultaria em zero casos sempre). O
controle de acesso aqui é a permissão do token (`management.read`) + a política de
governança de IA (que um admin pode desabilitar por perfil), e o recorte por
pessoa/regional é feito de forma explícita pelos filtros acima
(`supervisor_user_id`, `regional`). O conector MCP, onde quem chama é um usuário
OAuth real, continua aplicando o escopo por supervisor/regional normalmente.

| Método + path | Descrição | endpoint_key | Resposta |
|---|---|---|---|
| `POST /api/ai/management/cases-diagnostics` | Diagnóstico agregado (produtividade abaixo da meta) — "quem mais não bate meta, por regional/colaborador/motivo". Visão de matriz. | `ai.management_cases_diagnostics` | `ManagementCaseDiagnosticsOut` |
| `POST /api/ai/management/pending-by-collaborator` | "Quem está devendo justificativa" — uma linha por colaborador x regional, com idade da pendência e ids dos casos abertos. Combine com `pending_justification=true` ou `reference_date_from`/`reference_date_to`. | `ai.management_pending_justifications` | `ManagementPendingByCollaboratorOut` |
| `POST /api/ai/management/justifications` | Leitura das justificativas escritas pelos supervisores (texto, motivo, plano de ação, decisão da matriz), paginada de verdade (`total` sempre presente). `include_comments=true` traz a thread de comentários do caso. | `ai.management_justifications` | `ManagementJustificationPage` |
| `POST /api/ai/management/cases` | Listagem paginada dos casos completos (não só a justificativa) — equivalente por API do que a tela lista. | `ai.management_cases` | `ManagementCasePage` |

#### Metadado (sem chave de API)

| Método + path | Descrição |
|---|---|
| `GET /api/ai/openapi.json` | Schema OpenAPI reduzido, só com as rotas deste módulo — para importação automática por um agente de IA (ex.: Custom GPT Action). Fica num router **separado** (`public_router`), sem a dependency de chave de API: é metadado sobre o formato das rotas, não dado operacional. Cada operação marca `x-openai-isConsequential: false` (nenhum POST daqui tem efeito colateral). Ao adicionar uma rota nova, confira o tamanho da docstring/description — o ChatGPT limita a 300 caracteres por operação e uma descrição maior já quebrou a importação inteira do schema (achado real de 2026-08-15). |

### Exemplos

#### 1. Buscar O.S. abertas numa regional em modo resumido

```bash
curl -X POST "https://<host>/api/ai/search-orders" \
  -H "x-api-key: <sua-chave>" \
  -H "Content-Type: application/json" \
  -d '{
        "date_from": "2026-09-01",
        "date_to": "2026-09-16",
        "page": 1,
        "page_size": 50,
        "response_mode": "summary",
        "filters": {
          "regionals": ["UNI - JI-PARANA"],
          "statuses": ["Aberta"]
        }
      }'
```

Requer token com escopo `orders.read` (ou chave legado) e o endpoint
`ai.search_orders` habilitado na política de governança para esse perfil.

#### 2. Detectar incidente coletivo de rede numa regional

```bash
curl -X POST "https://<host>/api/ai/infra/login-incident-analysis" \
  -H "x-api-key: <sua-chave>" \
  -H "Content-Type: application/json" \
  -d '{
        "window_minutes": 90,
        "regionals": ["UNI - ROLIM DE MOURA"],
        "cluster_radius_meters": 300,
        "cluster_min_size": 3
      }'
```

Requer token com escopo `infra.read` e o endpoint `ai.login_incident_analysis`
habilitado.

#### 3. Consultar o catálogo de campos liberados para o token atual

```bash
curl -X GET "https://<host>/api/ai/fields" \
  -H "x-api-key: <sua-chave>"
```

Não exige escopo de token (usa `require_api_key_user`), mas exige o endpoint
`ai.list_fields` habilitado na política — útil para o próprio agente de IA
descobrir, em runtime, quais campos ele pode pedir em `fields=[...]` nas demais
rotas antes de tentar e receber um `422`.

---

<a id="intelligence"></a>

## UNI Intelligence


### Visão geral

O UNI Intelligence é o motor de inteligência operacional da plataforma: roda **monitores**
periódicos que inspecionam os dados de operação/suporte, gera **alertas** (com deduplicação,
severidade, evidências e ciclo de vida confirmar/resolver) e monta o **payload único do cockpit**
consumido pelas TVs/gauges da operação (`/cockpit/{profile_key}`).

Além da leitura, o módulo permite **publicar conteúdo editorial** no cockpit (avisos, destaques)
tanto via REST (`POST /cockpit-content`) quanto pela mesma função usada pela tool MCP
`opr_publish_cockpit_content` — nunca há duas implementações da regra de validação.

A parte de administração (F5) cobre CRUD de **profiles de cockpit** (o que cada TV mostra),
**publicações** (aprovar/editar/descartar conteúdo) e **monitores/regras de alerta**
(habilitar, ajustar intervalo, parametrizar regras, simular impacto antes de ativar).

Todas as listagens seguem o `FilterContractV1`: filtros de igualdade em plural/`snake_case` e um
envelope `meta` (`applied_filters`, `ignored_filters`, `warnings`, `source_last_sync`) em toda
resposta — não herda o vocabulário do REST legado de `operations`.

### Autenticação e permissões

Sessão autenticada (cookie/token de usuário) é obrigatória em **todas** as rotas do módulo — não
há endpoint público.

- O router principal exige `intelligence:read` para qualquer rota (`dependencies` no nível do
  `APIRouter`, em `router.py`).
- `POST /alerts/{alert_id}/dismiss` exige adicionalmente `intelligence:manage`.
- `POST /cockpit-content` (publicação REST de conteúdo do cockpit) exige `intelligence:publish`.
- Todo o subrouter `/admin/*` (profiles, filter-catalog, content, monitores, alert-rules) exige
  `intelligence:manage` além do `intelligence:read` herdado do router pai — é a superfície de
  gestão, não a leitura da TV.

### Endpoints

#### Monitores e execuções

- **`GET /monitors`** — lista o estado efetivo de cada monitor registrado: configuração atual
  (`app_settings`, com fallback pro default do registry), última execução, última execução com
  sucesso e falhas consecutivas. Mesmo material usado pelo meta-monitor de saúde, exposto para
  inspeção manual. Sem parâmetros. Resposta: `MonitorListOut` (`items: MonitorOut[]` + `meta`).
  Permissão: `intelligence:read`.

- **`GET /monitor-runs`** — histórico paginado de execuções de monitor.
  Parâmetros: `monitor_keys[]`, `statuses[]`, `page` (≥1, default 1), `page_size` (1–200,
  default 50). Chaves de monitor desconhecidas viram `ignored_filters` com motivo
  `NOT_SUPPORTED_BY_ENDPOINT`, não erro. Resposta: `MonitorRunPageOut`
  (`items`, `total`, `page`, `page_size`, `meta`). Permissão: `intelligence:read`.

#### Alertas

- **`GET /alerts`** — lista paginada de alertas ativos/históricos.
  Parâmetros: `statuses[]`, `severities[]`, `monitor_keys[]`, `regionals[]`, `kinds[]`, `page`,
  `page_size` (1–200, default 50). Ordenado por `last_seen_at` desc. Resposta: `AlertPageOut`.
  Permissão: `intelligence:read`.

- **`GET /alerts/{alert_id}`** — detalhe de um alerta, incluindo o histórico de eventos
  (`events: AlertEventOut[]`). 404 se o alerta não existir. Resposta: `AlertDetailOut`.
  Permissão: `intelligence:read`.

- **`POST /alerts/{alert_id}/dismiss`** — descarta manualmente um alerta (registra evento e
  atualiza status). Body: `AlertDismissRequest` (`reason`). 404 se o alerta não existir.
  Resposta: `AlertDetailOut` (com eventos atualizados). Permissão: `intelligence:manage`.

#### Cockpit (F2)

- **`GET /cockpit/{profile_key}`** — payload único da TV: tudo que o frontend precisa para
  renderizar o cockpit em um único request (produção, backlog, SLA, alertas/incidentes recentes,
  conteúdo publicado, saúde dos monitores, gráficos, frescor do dado). Monta no backend
  reaproveitando funções de `operations`/`ai` via `cockpit.py` — o frontend nunca chama dezenas
  de endpoints separados. 404 se o profile não existir ou estiver inativo (`profile.active`).
  Resposta: `CockpitPayloadOut`. Permissão: `intelligence:read`.

- **`POST /cockpit-content`** — publica conteúdo editorial no cockpit (aviso, destaque) via REST.
  Usa a mesma função (`cockpit.publish_cockpit_content`) chamada pela tool MCP
  `opr_publish_cockpit_content`, para nunca duplicar validação. A origem é sempre determinada pelo
  backend a partir do usuário logado — nunca aceita `publisher` arbitrário no payload; grava
  sempre `source_type="USER"` com `author_user_id` do chamador. Body: `PublishCockpitContentRequest`
  (`content_type`, `profile_key`, `scope`, `severity`, `title`, `body`, `evidence`, `confidence`,
  `valid_until`). 422 em `CockpitContentValidationError`. Resposta: `CockpitContentOut` (201).
  Permissão: `intelligence:publish`.

#### Administração — profiles (`/admin/profiles`)

- **`GET /admin/profiles`** — lista todos os profiles de cockpit cadastrados.
  Resposta: `AdminProfileOut[]`. Permissão: `intelligence:manage`.
- **`GET /admin/profiles/{profile_key}`** — detalhe de um profile. 404 se inexistente.
  Permissão: `intelligence:manage`.
- **`POST /admin/profiles`** — cria um profile. Body: `AdminProfileCreateRequest` (`key`, `name`,
  `purpose`, `scope`, `widgets[]`, `display_config`, `refresh_seconds`, `active`). 422 em
  `ProfileValidationError`. Resposta: `AdminProfileOut` (201). Permissão: `intelligence:manage`.
- **`PUT /admin/profiles/{profile_key}`** — atualiza um profile existente (campos parciais).
  404 se inexistente, 422 em `ProfileValidationError`. Permissão: `intelligence:manage`.

#### Administração — catálogo de filtros

- **`GET /admin/filter-catalog`** — valores possíveis para montar filtros de profile/conteúdo:
  `regionals`, `sectors`, `team_models`, `os_subjects`, `content_types`, `content_severities`,
  `profile_purposes`, `widgets` (catálogo de widgets disponíveis). Resposta: `FilterCatalogOut`.
  Permissão: `intelligence:manage`.

#### Administração — publicações (`/admin/content`)

- **`GET /admin/content`** — lista publicações de cockpit para gestão (inclui `status`, diferente
  da rota pública de conteúdo já embutida no cockpit). Parâmetros: `profile_key`, `status`
  (alias de `status_filter`), `content_type`. Resposta: `AdminContentOut[]`.
  Permissão: `intelligence:manage`.
- **`PUT /admin/content/{content_id}`** — edita uma publicação (`title`, `body`, `severity`,
  `valid_until`). 404 se não encontrada, 422 em `CockpitContentValidationError`.
  Permissão: `intelligence:manage`.
- **`POST /admin/content/{content_id}/dismiss`** — descarta uma publicação. 404 se não
  encontrada. Permissão: `intelligence:manage`.

#### Administração — monitores

- **`PUT /admin/monitors/{monitor_key}`** — ajusta configuração de um monitor: `enabled`,
  `interval_minutes`, `resolve_after_misses` (`AdminMonitorUpdateRequest`). 404 se o monitor não
  existir no registry. Resposta: `MonitorOut` já com o estado recalculado.
  Permissão: `intelligence:manage`.

#### Administração — regras de alerta (`/admin/alert-rules`)

- **`GET /admin/alert-rules`** — lista as regras de alerta parametrizáveis cadastradas.
  Resposta: `AdminAlertRuleOut[]`. Permissão: `intelligence:manage`.
- **`GET /admin/alert-rules/catalog`** — catálogo de tipos de regra disponíveis e seus parâmetros
  aceitos. Resposta: `AlertRuleCatalogOut`. Permissão: `intelligence:manage`.
- **`POST /admin/alert-rules/{rule_key}/simulate`** — simula o impacto de uma alteração de regra
  (sem persistir) antes de aplicá-la: monta uma regra candidata com os campos enviados
  (sobrepostos aos da regra atual) e roda a simulação. 404 se a regra não existir, 422 em
  `AlertRuleValidationError`. Resposta: `AlertRuleSimulationOut`. Permissão: `intelligence:manage`.
- **`POST /admin/alert-rules`** — cria uma regra. Body: `AdminAlertRuleCreateRequest` (`key`,
  `name`, `rule_type`, `scope`, `params`, `severity`, `active`, `cooldown_minutes`,
  `confirm_cycles`, `resolve_cycles`). 422 em `AlertRuleValidationError`. Resposta:
  `AdminAlertRuleOut` (201). Permissão: `intelligence:manage`.
- **`PUT /admin/alert-rules/{rule_key}`** — atualiza uma regra existente (campos parciais). 404
  se inexistente, 422 em `AlertRuleValidationError`. Permissão: `intelligence:manage`.
- **`DELETE /admin/alert-rules/{rule_key}`** — remove uma regra. 404 se inexistente. Resposta:
  204 sem corpo. Permissão: `intelligence:manage`.

### Exemplos

**1. TV do cockpit buscando o payload de um profile:**

```
GET /api/intelligence/cockpit/visao-geral-operacao
Cookie: <sessão autenticada com intelligence:read>
```

Resposta (200, resumida):

```json
{
  "profile": { "key": "visao-geral-operacao", "name": "Visão Geral" },
  "generated_at": "2026-09-16T13:05:00Z",
  "overall_status": { "...": "..." },
  "production": { "...": "..." },
  "backlog": { "...": "..." },
  "sla": { "...": "..." },
  "alerts": [],
  "incidents": [],
  "recent_alerts": [],
  "content": [],
  "monitor_health": [],
  "charts": { "...": "..." },
  "data_freshness": { "...": "..." },
  "meta": { "applied_filters": {}, "source_last_sync": null }
}
```

**2. Publicando um aviso editorial no cockpit (usuário com `intelligence:publish`):**

```
POST /api/intelligence/cockpit-content
Content-Type: application/json

{
  "content_type": "AVISO",
  "profile_key": "visao-geral-operacao",
  "scope": {"regional": "Porto Velho"},
  "severity": "MEDIA",
  "title": "Manutenção programada às 22h",
  "body": "Janela de manutenção na regional Porto Velho, sem impacto esperado no SLA.",
  "evidence": null,
  "confidence": null,
  "valid_until": "2026-09-17T00:00:00Z"
}
```

Resposta: `201 Created` com o `CockpitContentOut` criado, `source_type="USER"` e
`author_user_id` preenchido automaticamente pelo backend a partir do usuário autenticado.

---

<a id="localiza"></a>

## UNI Localiza


### Visão geral

O UNI Localiza gera **links de compartilhamento de GPS** vinculados a uma O.S./atendimento: o
atendente cria uma solicitação (opcionalmente já ligada a uma O.S., protocolo OPA ou cliente do
IXC), o sistema gera um **token público** de alta entropia e o link (`{frontend_url}/l/{token}`)
é enviado ao cliente — normalmente por WhatsApp. O cliente abre o link em uma página pública
(sem login), autoriza o GPS do navegador e confirma a localização; o backend compara a
coordenada confirmada com a coordenada cadastrada do cliente no IXC e classifica a divergência
(`compatible` / `minor_divergence` / `relevant_divergence` / `high_divergence`), útil para
detectar endereço cadastral desatualizado antes do técnico ir a campo.

O módulo **não aparece no registro central de módulos** da aplicação (diferente de
`intelligence`, `operations` etc.), mas está com rotas ativas e mapeado direto em `main.py`:
`app.include_router(localiza_router, prefix=settings.api_prefix)` e
`app.include_router(localiza_public_router, prefix=settings.api_prefix)`.

### Autenticação e permissões

Este módulo tem **duas superfícies com modelos de acesso completamente diferentes** — distinção
importante porque uma delas fica exposta na internet sem login:

- **Rotas internas/autenticadas** (`router.py`, prefixo `/api/localiza`): exigem sessão de
  usuário autenticado, controlada por permissão granular via `require_permission(...)`:
  - `localiza:read` — apenas leitura (listar e ver detalhe de solicitações).
  - `localiza:manage` — criar, invalidar, reanexar O.S., regenerar link, buscar cliente no IXC e
    configurar o TTL do link.
- **Rotas públicas** (`public_router.py`, prefixo `/api/public/location`): **sem nenhuma
  autenticação de usuário** — é a página que o cliente final abre pelo link do WhatsApp. A
  proteção não é login, é o **token** (256 bits de entropia, nunca devolvido em texto puro fora
  da criação/regeneração — só o hash SHA-256 é persistido) somado a **rate limiting em memória
  por IP**: `RATE_WINDOW_MINUTES = 15`, `RATE_MAX_ATTEMPTS = 20`, aplicado via dependency
  `Depends(_guard_rate_limit)` tanto na consulta de status quanto na confirmação — porque a
  própria consulta de status já permite "adivinhar" se um token existe. Excedido o limite, a API
  responde `429 Muitas tentativas`. Mesmo padrão usado em `app/api/routes/invites.py`.

### Endpoints

#### Rotas internas — `/api/localiza` (autenticadas)

- **`GET /localiza`** — lista solicitações de localização.
  Parâmetros: `search`, `date_from`, `date_to`, `status` (`pending|confirmed|invalidated|expired`),
  `mine_only` (bool, só as criadas pelo usuário logado), `limit` (1–1000, default 200). 400 se
  `date_to < date_from`. Resposta: `LocationRequestOut[]`. Permissão: `localiza:read`.

- **`GET /localiza/settings`** — retorna a validade (TTL) atual configurada para os links, em
  horas. Resposta: `LocalizaSettingsOut` (`link_ttl_hours`). Permissão: `localiza:manage`.

- **`PUT /localiza/settings`** — atualiza o TTL dos links (1–720 horas), gravado em
  `AppSetting` (não exige redeploy) e registrado em audit log com valor anterior/novo. Body:
  `LocalizaSettingsUpdate` (`link_ttl_hours`). Resposta: `LocalizaSettingsOut`.
  Permissão: `localiza:manage`.

- **`POST /localiza`** — cria uma nova solicitação de localização e gera o token público (a
  string crua do token só existe nesta resposta e na de `/regenerate` — depois só o hash fica no
  banco). Nenhum campo é individualmente obrigatório, mas o service exige ao menos um
  identificador (`order_code`, `opa_protocol` ou dados de cliente), senão a solicitação fica
  impossível de localizar depois. Body: `LocationRequestCreate` (`order_code`, `opa_protocol`,
  `customer_id`, `customer_name`, `registered_latitude`/`registered_longitude`,
  `ixc_cliente_id`, `ixc_login_id`, `ixc_login`). Resposta: `LocationRequestCreateOut` (201) —
  `LocationRequestOut` + `token` (cru) + `public_link` (`{frontend_url}/l/{token}`).
  Permissão: `localiza:manage`.

- **`GET /localiza/ixc/search`** — busca ao vivo no IXC por `login` (número ou texto) **ou**
  `cpf`, nunca os dois juntos (422 se ambos ou nenhum for informado). Usada pelo formulário de
  criação para autopreencher nome/identificador/coordenada cadastrada a partir de um cadastro já
  existente, evitando digitação manual. Resposta: `IxcCustomerSearchOut` (`matches:
  IxcCustomerMatchOut[]`, com `cpf_masked`). Permissão: `localiza:manage`.

- **`GET /localiza/{item_id}`** — detalhe de uma solicitação, com status efetivo recalculado na
  hora (`pending` vira `expired` automaticamente se `expires_at` já passou). Resposta:
  `LocationRequestOut`. Permissão: `localiza:read`.

- **`POST /localiza/{item_id}/invalidate`** — invalida manualmente uma solicitação (ex.: link
  enviado por engano). Resposta: `LocationRequestOut`. Permissão: `localiza:manage`.

- **`POST /localiza/{item_id}/attach-order`** — associa/atualiza o código de O.S. de uma
  solicitação já existente (comum quando o link é enviado antes de a O.S. existir no IXC). Body:
  `LocationRequestAttachOrder` (`order_code`). Resposta: `LocationRequestOut`.
  Permissão: `localiza:manage`.

- **`POST /localiza/{item_id}/regenerate`** — gera um novo token/link para uma solicitação
  (ex.: o link anterior expirou ou foi comprometido), preservando os demais dados. Resposta:
  `LocationRequestCreateOut` (201) — mesmo formato de `POST /localiza`, com novo `token` cru e
  `public_link`. Permissão: `localiza:manage`.

#### Rotas públicas — `/api/public/location` (sem autenticação, com rate limit)

- **`GET /public/location/{token}`** — consulta o status de um link público, para a página
  exibir contexto ao cliente antes de pedir o GPS (nome do cliente, O.S./protocolo, status,
  validade). Não vaza dados sensíveis nem confirma univocamente a existência do token além do
  necessário. Resposta: `PublicLocationStatusOut` (`valid`, `reason`, `order_code`,
  `opa_protocol`, `customer_name`, `status`, `expires_at`). Sujeito ao rate limit por IP.

- **`POST /public/location/{token}/confirm`** — o cliente confirma a localização capturada pelo
  navegador. Body: `PublicLocationConfirmRequest` (`latitude`/`longitude` finais — podem ter sido
  ajustadas manualmente no mapa —, `accuracy_meters` (0–50000), `gps_latitude`/`gps_longitude`
  brutos do GPS, `adjusted_manually`). O backend calcula a distância Haversine entre a coordenada
  confirmada e a coordenada cadastrada do cliente e grava a classificação de divergência
  (`compatible` ≤50m, `minor_divergence` ≤150m, `relevant_divergence` ≤500m,
  `high_divergence` acima disso). Resposta: `PublicLocationConfirmOut`
  (`status="confirmed"`, `confirmed_at`). Sujeito ao rate limit por IP.

### Exemplos

**1. Atendente cria uma solicitação de localização (rota interna, `localiza:manage`):**

```
POST /api/localiza
Content-Type: application/json
Cookie: <sessão autenticada com localiza:manage>

{
  "order_code": "OS-458213",
  "customer_name": "Maria da Silva",
  "ixc_cliente_id": 88210,
  "ixc_login_id": 154032,
  "ixc_login": "maria.silva"
}
```

Resposta (`201 Created`):

```json
{
  "id": 512,
  "public_id": "A1B2C3D4",
  "order_code": "OS-458213",
  "customer_name": "Maria da Silva",
  "status": "pending",
  "expires_at": "2026-09-17T13:00:00Z",
  "token": "9f3c...(cru, só aparece aqui)",
  "public_link": "https://app.souuni.com/l/9f3c..."
}
```

O `public_link` é então enviado ao cliente pelo WhatsApp.

**2. Cliente abre o link e confirma a localização (rota pública, sem login):**

```
GET /api/public/location/9f3c...
```

```json
{ "valid": true, "order_code": "OS-458213", "customer_name": "Maria da Silva", "status": "pending", "expires_at": "2026-09-17T13:00:00Z" }
```

```
POST /api/public/location/9f3c.../confirm
Content-Type: application/json

{
  "latitude": -8.76077,
  "longitude": -63.90184,
  "accuracy_meters": 12.5,
  "gps_latitude": -8.76077,
  "gps_longitude": -63.90184,
  "adjusted_manually": false
}
```

Resposta: `{"status": "confirmed", "confirmed_at": "2026-09-16T13:07:22Z"}`. Se a taxa de
tentativas daquele IP já tiver estourado (20 em 15 minutos, somando consultas de status e
confirmações), a API responde `429 Muitas tentativas. Aguarde alguns minutos e tente novamente.`

---

