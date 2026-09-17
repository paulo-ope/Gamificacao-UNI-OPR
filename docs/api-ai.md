# API — Agente de IA (`/api/ai`)

> Fonte: `backend/app/modules/ai/router.py`, `backend/app/modules/ai/schemas.py`,
> `backend/app/modules/ai/auth.py`, `backend/app/modules/ai_governance/gate.py`.
> Este documento cobre só o módulo `ai` (dados). Emissão/gestão de chaves e das
> permissões de IA fica em `/api/admin/ai-governance`
> (`backend/app/modules/ai_governance/router.py`) — ver `docs/api-admin.md`, seção
> "AI Governance"; não duplicado aqui.

## Visão geral

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

## Autenticação

**Este módulo usa um esquema de autenticação separado do login normal de usuário
(sessão/JWT).** A equipe que for integrar um agente de IA a este sistema deve usar
chave de API, não as credenciais de um usuário humano.

### Como o cliente se autentica

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

### Duas camadas de autorização, aplicadas em conjunto

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

### Onde tokens e permissões são administrados

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

## Endpoints

Legenda das colunas: **Camadas** = quais das 3 camadas de autorização descritas
acima se aplicam (sempre inclui a 1); **Escopo** = escopo de token exigido
(camada 2, só tokens novos); **endpoint_key** = chave de política de governança
(camada 3, quando existe).

### Operação (espelha `operations/router.py` — Ordens de Serviço)

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

### Infraestrutura / rede (espelha `operations/router.py` — logins, ONU, incidente)

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

### Gestão Integrada (espelha `management` — casos e justificativas de produtividade)

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

### Metadado (sem chave de API)

| Método + path | Descrição |
|---|---|
| `GET /api/ai/openapi.json` | Schema OpenAPI reduzido, só com as rotas deste módulo — para importação automática por um agente de IA (ex.: Custom GPT Action). Fica num router **separado** (`public_router`), sem a dependency de chave de API: é metadado sobre o formato das rotas, não dado operacional. Cada operação marca `x-openai-isConsequential: false` (nenhum POST daqui tem efeito colateral). Ao adicionar uma rota nova, confira o tamanho da docstring/description — o ChatGPT limita a 300 caracteres por operação e uma descrição maior já quebrou a importação inteira do schema (achado real de 2026-08-15). |

## Exemplos

### 1. Buscar O.S. abertas numa regional em modo resumido

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

### 2. Detectar incidente coletivo de rede numa regional

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

### 3. Consultar o catálogo de campos liberados para o token atual

```bash
curl -X GET "https://<host>/api/ai/fields" \
  -H "x-api-key: <sua-chave>"
```

Não exige escopo de token (usa `require_api_key_user`), mas exige o endpoint
`ai.list_fields` habilitado na política — útil para o próprio agente de IA
descobrir, em runtime, quais campos ele pode pedir em `fields=[...]` nas demais
rotas antes de tentar e receber um `422`.
