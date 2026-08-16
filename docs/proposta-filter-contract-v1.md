# Proposta: FilterContractV1

**Status:** **FASE 1 DE CONFIABILIDADE CONCLUÍDA** (2026-08-16, ver §15) — 8 lotes implementados e testados com dado real (`aggregate_orders`, `search_orders`, `backlog_aging`, `team_target_performance`, `orders_timeseries`, `warranty_analytics_for_ai`). Zero casos remanescentes de "schema aceita, query ignora, sem aviso" e zero casos de "`meta` afirma aplicação que a query não fez". P1/P2 remanescentes são dívida técnica de escopo de produto, listados em §15.4, não iniciados.
**Data:** 2026-08-16 (v1.2 — Fase 1 encerrada, §14-§15)
**Autor:** levantamento assistido (Claude Code), a partir de inventário exaustivo do código real (arquivo:linha).
**Depende de:** [Fase 1, item 1 do plano de confiabilidade de dado](#) — envelope `meta` (`applied_filters`/`ignored_filters`/`warnings`), já implementado e em produção nos endpoints de login/coordenadas.
**Não altera:** `ixc_importer.py::parse_ixc_datetime`, Gamificação, pagamentos, metas históricas, cobertura ONU percentual. Nenhum desses aparece neste documento.

## 0. Ajustes incorporados nesta revisão

1. **Seletores (`group_by`, `metric`, `entity`, `granularity`, `date_field`) não usam `ignored_filters`.** Valor inválido de seletor continua validado pelo próprio endpoint (erro explícito, como já é em `login_aggregate`) ou, quando aplicável, um `warnings` próprio `INVALID_SELECTOR_VALUE` — nunca misturado com o vocabulário de filtro. Ver §5 e §8.
2. **"Aplicado em população parcial" é diferente de "ignorado".** `pon_ids`/`transmitter_ids`/`contract_ids` em `search_logins` continuam em `applied_filters` (foram de fato usados) e ganham um aviso `PARTIAL_DIMENSION_COVERAGE` em vez de aparecer em `ignored_filters`. Ver §4.2 e §7.5.
3. **`search`/`keyword` confirmados como aliases verdadeiros por leitura de código**, não por suposição: `keyword` (IA) é convertido em `filters["search"]` (`ai/queries.py:870-871`) antes de chegar em `operations_queries._query_conditions`, que resolve `search` usando sempre a mesma tupla `SEARCH_COLUMNS` (`operations/queries.py:120-142,347-355`) — REST e IA caem exatamente na mesma função e no mesmo conjunto de colunas. Normalização aprovada sem ressalva.
4. **Migração de filtro escalar→lista em `management_cases` (`regional`, `severity`, `case_type`) fica como evolução própria do domínio**, não automática por este contrato: precisa provar antes que a consulta multi-valor preserva o escopo de autorização/índice atual (ver §4.3 e §6.1). O nome canônico plural continua proposto; a migração de código não está autorizada só por este documento.

---

## 1. Objetivo

Hoje o mesmo conceito de filtro tem nomes diferentes dependendo do canal (REST, IA/API-key, MCP remoto, MCP local) e do módulo (Ordens de Serviço vs Login/Rede vs Casos de Gestão). Isso já causou pelo menos um bug real documentado no próprio código (`ai/queries.py:394-408`, fallback silencioso de `group_by` desconhecido). Antes de tocar em qualquer endpoint, este documento propõe:

1. Um nome canônico único por conceito de filtro.
2. Os aliases atualmente em uso, pra nenhum cliente (dashboard, IA, MCP) quebrar.
3. Uma regra única de "o que fazer quando um filtro não se aplica" (usando o envelope `meta` já existente).
4. Uma matriz endpoint × filtro atual × filtro canônico, pra medir o tamanho real do impacto antes de decidir se/quando refatorar.

**Isto não é uma decisão de implementação.** É a base pra decidir, com o usuário, se e como refatorar. Depois de aprovado, cada mudança de código ainda precisa ser feita endpoint por endpoint, com teste real, como já vem sendo feito.

---

## 2. Achados que motivam o contrato (resumo do inventário completo)

Levantamento exaustivo em `backend/app/modules/{ai,operations,mcp_connector}` e `mcp-server/`, com arquivo:linha, encontrou 7 famílias de inconsistência:

| # | Caso | Nomes divergentes encontrados | Onde |
|---|------|-------------------------------|------|
| 1 | "Assunto da O.S." | `subjects` (filtro-lista), `subject` (dimensão/texto), `os_subject` (coluna real/campo de saída), `type_subject` (chave de `sort_by`), `return_os_subject` (campo de garantia) | `operations/queries.py`, `ai/queries.py`, `ai/schemas.py`, `router.py` |
| 2 | "Regional" | `regionals` (lista, ~15 endpoints), `regional` (escalar único, só em `opr_management_cases`) | `management/cases.py:416`, `mcp_connector/server.py:976` |
| 3 | "Status online" | `online_statuses` (filtro-lista), `online` (dimensão de agrupamento / coluna / campo de saída) | `login_aggregate.py`, `ai/schemas.py:544` |
| 4 | Filtro de tempo | 3 formatos coexistindo: `since`/`until` (login-outages/timeseries), `..._since` só-gte (REST login-search), `{gte,gt,lte,lt,eq}` completo (IA/MCP search-orders e search-logins) | `router.py:1260-1293`, `ai/schemas.py`, `login_search.py` |
| 5 | `group_by`/`entity` | `Literal` tipado só nos schemas IA; `str` livre em REST e nas duas tools MCP (validação só dentro da função) | `login_aggregate.py:53`, `ai/schemas.py:544,568`, `router.py:1320,1385` |
| 6 | `customer_logins` | Existe em `FILTER_COLUMNS` e no schema IA; **não existe** na rota REST `/operations/orders` (0 ocorrências) | `operations/queries.py:71` vs `router.py` |
| 7 | `fields`/`response_mode` | Só em `search_orders`/`order_details`/`orders`; ausentes em `aggregate_orders`, `backlog_aging`, `warranty_analytics`, login/coordinate_quality | vários |

O caso #1 é o mais grave: 6 nomes diferentes para o mesmo conceito, espalhados por 5 arquivos, incluindo um já usado como causa de bug real.

---

## 3. Convenções do FilterContractV1

| Categoria | Regra proposta | Exemplo |
|---|---|---|
| Filtro de igualdade em lista | plural, `snake_case`, sempre `list[T]` | `regionals`, `os_subjects`, `statuses` |
| Filtro de igualdade escalar | **eliminado** — todo filtro de igualdade passa a aceitar lista, mesmo com 1 item | `opr_management_cases.regional` (escalar) → `regionals: list[str]` |
| Filtro de texto parcial | sufixo `_query`, `str`, sempre `ILIKE contains` | `login_query` (já correto, mantido) |
| Filtro de texto genérico (multi-operador) | estrutura `text_filters: [{field, operator, value}]` — mantida como está, só padroniza `field` para os nomes canônicos desta tabela | `text_filters=[{"field":"os_subject","operator":"contains","value":"fibra"}]` |
| Filtro de data/hora em campo | dict `{gte?, gt?, lte?, lt?, eq?: datetime}` — **sempre** esse formato, nunca valor escalar solto | `opened_at={"gte": "..."}` |
| Filtro de janela (não é campo, é "desde/até agora") | `since`/`until` (escalares, mantidos como conceito próprio — ver §3.1) | `login_outages(since=..., until=...)` |
| Filtro booleano | nome afirmativo, sem prefixo `is_`/`has_` a menos que já exista e seja claro | `has_coordinates` (mantido, já é claro) |
| Seletor de dimensão/enum (`group_by`, `entity`, `metric`, `granularity`, `date_field`) | **não é filtro** (não filtra, seleciona forma da resposta) — fora do escopo deste contrato, mas mesma disciplina de tipagem (`Literal` em todos os canais) recomendada como item separado (§8) | — |
| Trio geográfico | `near_latitude`, `near_longitude`, `radius_km` — **já 100% consistente hoje**, nenhuma mudança | — |

### 3.1 Por que `since`/`until` não desaparece

`since`/`until` em `login_outages`/`login_timeseries`/`login_incident_analysis` não filtra um campo específico — define a **janela da consulta em si** (o que é "recente" pra aquela chamada). Isso é semanticamente diferente de "filtre `status_changed_at >= X`" mesmo que a implementação hoje seja idêntica. Por isso o contrato mantém os dois conceitos:

- **Filtro de campo** (`status_changed_at`, `opened_at`, etc.): sempre dict `{gte,gt,lte,lt,eq}`.
- **Janela da consulta** (`since`/`until`): continua escalar, mas o envelope `meta.applied_filters` deve expor a forma resolvida equivalente, para transparência (ver exemplo §6.2).

---

## 4. Tabela mestre de filtros canônicos

### 4.1 Domínio Ordens de Serviço / Backlog / Garantia

| Canônico | Tipo | Operadores | Aliases hoje (arquivo:linha) | Endpoints que suportam hoje |
|---|---|---|---|---|
| `companies` | `list[str]` | igualdade | — (já único) | search_orders, aggregate_orders, orders_timeseries, backlog_aging, warranty (origem), team_target_performance, REST `/operations/orders` |
| `regionals` | `list[str]` | igualdade | — (já único) | idem acima + branch_capacity_summary |
| `states` | `list[str]` | igualdade | — | idem |
| `cities` | `list[str]` | igualdade | — | idem |
| `contract_types` | `list[str]` | igualdade | — | idem |
| `person_types` | `list[str]` | igualdade | — | idem |
| `os_types` | `list[str]` | igualdade | — | idem (zerado à força no lado "retorno" de warranty, `ai/queries.py:1067`) |
| **`os_subjects`** | `list[str]` | igualdade | `subjects` (`operations/queries.py:53`, `ai/schemas.py:83`, `router.py:388`) | idem |
| `diagnoses` | `list[str]` | igualdade | — | idem |
| `departments` | `list[str]` | igualdade | — | idem |
| `sectors` | `list[str]` | igualdade | — | idem |
| `priorities` | `list[str]` | igualdade | — | idem |
| `creators` | `list[str]` | igualdade | — | idem |
| `responsibles` | `list[str]` | igualdade | — | idem |
| `responsible_ixc_ids` | `list[int]` | igualdade | — | **só backend** (`FILTER_COLUMNS`) — não exposto em `AiOrderFilters` (exclusão deliberada, `ai/queries.py:230-234`) nem em nenhum canal externo |
| `statuses` | `list[str]` | igualdade | — | idem (nome colide com `management_cases.statuses` — entidades diferentes, ok manter) |
| `sla_statuses` | `list[str]` | igualdade | — | idem |
| `projects` | `list[str]` | igualdade | — | idem |
| `pops` | `list[str]` | igualdade | — | idem |
| **`customer_logins`** | `list[str]` | igualdade | — | backend + IA/MCP; **ausente na rota REST** `/operations/orders` (gap, não alias — ver §7.3) |
| `team_models` | `list[str]` | igualdade (via subquery) | — | idem |
| `opened_weekdays` | `list[str]` (chaves `monday..sunday`) | igualdade | — | idem |
| `closed_weekdays` | `list[str]` | igualdade | — | idem |
| `custom_window_*` (5 campos compostos) | ver §4.1.1 | — | — | idem |
| `search` | `str` | `ILIKE` livre sobre colunas fixas | `keyword` (`ai/queries.py:870-871`, só em `search_orders`) | search_orders (como `keyword`), REST `/operations/orders` (como `search`), backlog/warranty/aggregate **não aceitam busca livre** |
| `closed_time_from` / `closed_time_to` | `str "HH:MM"` | intervalo de horário local | — | idem |
| `text_filters` | `list[{field, operator, value}]` | `contains/starts_with/ends_with/not_equals` | `field` deve usar nomes canônicos (`os_subject`, não `subject`) | idem |
| `scheduled_after_sla` | `bool` | igualdade | — | idem |
| `sla_expired_before_schedule` | `bool` | igualdade | — | idem |
| `has_coordinates` | `bool` | igualdade | — | idem |
| `near_latitude`/`near_longitude`/`radius_km` | `float` (trio) | raio | — | idem |
| `opened_at`, `closed_at`, `deadline_at`, `scheduled_at`, `assumed_at`, `displacement_started_at`, `execution_started_at`, `finished_at`, `source_updated_at` | `{gte,gt,lte,lt,eq: datetime}` | 5 operadores | — (já consistentes entre si) | idem — `search_orders`/REST usam só 1 desses por vez via `date_field` (seletor), não filtram por todos simultaneamente |
| `sector_filter` | `{operator, value}` | 4 operadores de texto | — | só `backlog_history` |
| `origin_excluded_diagnoses` | `list[str]` | exclusão | — | só `warranty_analytics` |

**4.1.1 — `custom_window_*` (mantido como está, é um filtro composto único sem alias):**
`custom_window_basis` (list, valores `opened`/`closed`), `custom_window_start_weekday`, `custom_window_start_time` (`HH:MM`), `custom_window_end_weekday`, `custom_window_end_time`. Os 5 só ativam juntos.

### 4.2 Domínio Login / Rede / ONU

| Canônico | Tipo | Operadores | Aliases hoje | Endpoints |
|---|---|---|---|---|
| `logins` | `list[str]` | igualdade | — | search_logins, query_login_status |
| `login_query` | `str` | `ILIKE contains` | — | search_logins |
| `login_ids` | `list[int]` | igualdade | — | search_logins, onu_signal |
| `online_statuses` | `list[str]` | igualdade | — | search_logins, login_aggregate, login_outages*(não!, ver nota), query_login_status |
| `regionals` | `list[str]` | igualdade | `regional` (escalar, só `opr_management_cases`, ver §4.3) | search_logins, login_aggregate, login_outages, login_incident_analysis, query_login_status |
| `pon_ids` | `list[str]` | igualdade (via JOIN com telemetria ONU) | — | search_logins — **aplicado normalmente** (`applied_filters`), mas só atinge logins com telemetria capturada; ver nota de cobertura parcial abaixo |
| `transmitter_ids` | `list[str]` | igualdade (via JOIN) | — | search_logins, onu_signal — mesma nota de cobertura parcial |
| `contract_ids` | `list[str]` | igualdade (via JOIN) | — | search_logins — mesma nota de cobertura parcial |
| `last_drop_causes` | `list[str]` | igualdade | — | onu_signal |
| `near_latitude`/`near_longitude`/`radius_km` | trio | raio | — | search_logins, query_login_status |
| `status_changed_at` | `{gte,gt,lte,lt,eq: datetime}` | 5 operadores | **`status_changed_since`** (REST `network_login_search`, só `gte`, `router.py:1291`) | search_logins (IA/MCP: completo; REST: só gte via alias) |
| `last_connected_at` | idem | idem | **`last_connected_since`** (REST, só gte) | idem |
| `last_disconnected_at` | idem | idem | **`last_disconnected_since`** (REST, só gte) | idem |
| `captured_at` | idem | idem | — (REST **nem aceita** este filtro, nem com alias) | search_logins (IA/MCP apenas) |
| `since` | `datetime` (piso da janela da consulta) | igualdade de janela (não é filtro de campo, ver §3.1) | — | login_outages, login_timeseries |
| `until` | `datetime` (teto da janela) | idem | — | login_outages, login_timeseries |
| `window_minutes` | `int` (açúcar sintático — resolve para `since = agora - window_minutes`) | — | — | login_incident_analysis, offline_login_clusters |
| `radius_meters` | `float` (parâmetro de clusterização, não filtro) | — | — | offline_login_clusters |
| `min_cluster_size` | `int` (idem) | — | — | offline_login_clusters |
| `limit` | `int` (paginação simples, não filtro) | — | — | login_outages, query_login_status, onu_signal, search_logins* (usa `page`/`page_size`, não `limit`) |

**Nota sobre `online_statuses` em `login_outages`:** a função filtra hoje por `online == "N"` fixo (queda), não recebe `online_statuses` como parâmetro — comportamento correto (é uma rota "quedas", não "status genérico"), listado aqui só para deixar explícito que a ausência é intencional, não uma lacuna.

**Nota sobre `pon_ids`/`transmitter_ids`/`contract_ids` (ajuste #2 da revisão):** esses 3 filtros usam `JOIN` com `operations_onu_signal_current` — quando usados, `search_logins` só retorna logins que têm telemetria ONU capturada. Isso **não é o filtro sendo ignorado**: ele foi recebido, é válido e foi de fato aplicado sobre a coluna certa. O que muda é a *população* sobre a qual ele atua. Por isso, quando qualquer um desses 3 filtros for usado, o filtro entra normalmente em `applied_filters` e o envelope `meta` ganha `warnings: [{"code": "PARTIAL_DIMENSION_COVERAGE", "dimension": "onu_telemetry"}]` — nunca `ignored_filters`. Exemplo completo em §7.5.

### 4.3 Domínio Casos de Gestão (`opr_management_cases`)

| Canônico | Tipo | Operadores | Aliases hoje | Observação |
|---|---|---|---|---|
| `statuses` | `list[str]` | igualdade | `status` (escalar, `mcp_connector/server.py:973`) + `only_open` (açúcar: vira `statuses=[pending, justified, in_progress]` — ver `OPEN_CASE_STATUSES`) | Só existe via tool MCP remota; sem schema IA dedicado |
| `severities` | `list[str]` | igualdade | `severity` (escalar) | idem |
| `regionals` | `list[str]` | igualdade | `regional` (escalar) | idem — mesmo nome canônico do §4.2, entidade diferente |
| `case_types` | `list[str]` | igualdade | `case_type` (escalar) | idem |
| `reference_year` / `reference_month` | `int` | igualdade | — | idem |
| `only_overdue` | `bool` | igualdade | — (mantido como açúcar, não um filtro de campo real) | idem |
| `search` | `str` | `ILIKE` sobre `responsible_name`/`regional`/`metric_name` | — | idem |
| `supervisor_user_id` | `int` | igualdade | — | **existe em `ManagementCaseFilters` mas não é exposto por nenhuma tool MCP hoje** — não é um alias, é um filtro real sem porta de entrada. Fica como candidato a `ignored_filters` com razão `NOT_YET_EXPOSED` se algum cliente tentar passá-lo via `filters` genérico (hoje a tool nem aceita `filters` livre, então isso é teórico). |

**Ajuste #4 da revisão — migração escalar→lista neste domínio NÃO está autorizada por este documento.** O nome canônico plural (`regionals`, `severities`, `case_types`) fica proposto e registrado, mas a troca de `status`/`severity`/`case_type` (escalares) por suas versões em lista em `opr_management_cases` é uma evolução própria do domínio de gestão, condicionada a provar antes que:
- a consulta multi-valor (`IN (...)` em vez de `= valor`) não muda o plano de índice de forma a degradar a rota;
- nenhuma regra de autorização (`supervisor_user_id`, escopo regional do usuário) dependia implicitamente de "exatamente um valor" na implementação atual.
Enquanto essa prova não for feita, `management_cases` continua com os parâmetros escalares atuais — normalização de nome (sem mudança de tipo) pode acontecer via alias reportado em `warnings`, sem migrar a assinatura da função.

### 4.4 Coordenadas

| Canônico | Tipo | Operadores | Aliases | Endpoints |
|---|---|---|---|---|
| `entity` | seletor (`Literal` proposto em todos os canais) | igualdade | — | coordinate_quality_audit |
| `outlier_km` | `float` (parâmetro, não filtro) | — | — | idem |
| `duplicate_threshold` | `int` (parâmetro, não filtro) | — | — | idem |

---

## 5. Comportamento proposto para filtro não aplicável

Reaproveita o envelope `meta` já implementado (Fase 1, item 1) — **nenhum filtro inválido se torna erro HTTP nesta etapa** (decisão já tomada e mantida). Regras:

1. **Filtro recebido E aplicado** → entra em `applied_filters` com o valor efetivamente usado (já é o comportamento atual de `build_meta`).
2. **Filtro recebido, reconhecido, mas não aplicável naquele endpoint** (ex.: `os_subjects` passado pra `login_aggregate`) → entra em `ignored_filters` com `{"field": "os_subjects", "reason": "NOT_APPLICABLE_TO_ENDPOINT", "detail": "login_aggregate opera sobre logins, não sobre O.S."}`.
3. **Alias depreciado recebido** (ex.: `subjects` em vez de `os_subjects`) → o filtro **é aplicado normalmente** (compatibilidade total) e um aviso entra em `warnings`:
   ```json
   {"code": "DEPRECATED_FILTER_ALIAS", "received": "subjects", "canonical": "os_subjects"}
   ```
4. **Filtro (não seletor) reconhecido mas com valor inválido** (ex.: `os_types=["valor_que_não_existe_no_ixc"]` — a lista em si é válida, o *conteúdo* não corresponde a nada) → **continua sem ser erro HTTP nesta etapa**; entra em `ignored_filters` com `reason: "INVALID_VALUE"`. Isso é sobre o *valor* de um filtro de campo, nunca sobre um seletor de forma da resposta (ver regra 4-bis).
5. **Filtro aplicado, mas só atinge parte da população da entidade** (ex.: `transmitter_ids` em `search_logins`, que só atinge logins com telemetria ONU) → o filtro **permanece em `applied_filters`** (foi de fato usado) e ganha um aviso dedicado em `warnings`: `{"code": "PARTIAL_DIMENSION_COVERAGE", "dimension": "<nome da dimensão que limita a cobertura>"}`. **Nunca** em `ignored_filters` — o filtro não foi ignorado, a população é que é menor que o total da entidade. (Ajuste #2 da revisão de aprovação.)
6. **Filtro completamente desconhecido** (não está em nenhum alias nem canônico) → `ignored_filters` com `reason: "UNKNOWN_FILTER"`.

**4-bis. Seletores (`group_by`, `metric`, `entity`, `granularity`, `date_field`) podem aparecer em `applied_filters` só como informação de transparência** (o que foi pedido, igual já acontece hoje em `login_aggregate`/`coordinate_quality_audit` em produção) — **mas nunca disparam a semântica de filtro** (`ignored_filters`, `DEPRECATED_FILTER_ALIAS`, `INVALID_VALUE`). Eles decidem a *forma* da resposta, não o que é incluído/excluído dos dados. Um valor de seletor inválido:
- continua gerando erro explícito dentro da função (padrão já adotado em `login_aggregate`, que levanta `ValueError` — preferível quando o endpoint já faz isso), **ou**
- quando o endpoint ainda não valida (ex.: REST/MCP com `group_by: str` livre, ver §8), gera um aviso próprio e distinto: `{"code": "INVALID_SELECTOR_VALUE", "selector": "group_by", "received": "...", "valid_values": [...]}`.
Este aviso nunca é misturado com `ignored_filters`/`DEPRECATED_FILTER_ALIAS` — é um vocabulário separado, reservado para quando o `SelectorContractV1` (§8) for formalizado. (Ajuste #1 da revisão de aprovação — corrige o exemplo anterior deste documento, que colocava `group_by` inválido dentro de `ignored_filters`.)

Essa é a mesma régua para os 4 canais (REST, IA, MCP remoto, MCP local) — a diferença de superfície de cada canal (nomes de query param vs corpo JSON vs argumento de tool) não muda o que aparece dentro de `meta`.

---

## 6. Estratégia de compatibilidade e depreciação

- **Nenhum nome atual deixa de funcionar nesta fase.** Todo alias listado nas tabelas do §4 continua aceito indefinidamente até uma decisão explícita de sunset (fora do escopo deste documento).
- Cada função de consulta ganha uma etapa de **normalização de entrada**: alias → nome canônico, antes de montar a query — muda só o código interno, não o formato aceito por fora.
- `warnings` sinaliza o uso do alias a cada chamada (visível pra IA/MCP e pro dashboard), sem forçar migração.
- REST mantém os nomes de query string que já existem (`status_changed_since`, `subjects`, etc.) — a normalização vira parte da função central chamada pela rota, igual ao padrão já estabelecido em `login_aggregate`/`search_logins` no item 1.
- Novos endpoints (Fase 2: `opr_team_performance`, `opr_sla_risk`, `opr_order_clusters`) usam **só** os nomes canônicos desde o início — não herdam alias.
- Não há prazo de remoção de alias proposto aqui. Isso é decisão de produto, não técnica, e fica fora deste documento.

---

## 7. Exemplos de request/response

### 7.1 Alias depreciado sendo usado (aggregate_orders via IA)

**Request** (`POST /ai/infra/aggregate-orders`):
```json
{
  "date_from": "2026-08-01",
  "date_to": "2026-08-16",
  "group_by": "regional",
  "metric": "quantidade_aberta",
  "filters": { "subjects": ["Sem sinal", "Lentidão"] }
}
```

**Response proposta** (hoje a resposta não tem `meta` neste endpoint — ficaria assim depois de estendido):
```json
{
  "meta": {
    "applied_filters": { "os_subjects": ["Sem sinal", "Lentidão"] },
    "ignored_filters": [],
    "warnings": [
      { "code": "DEPRECATED_FILTER_ALIAS", "received": "subjects", "canonical": "os_subjects" }
    ],
    "generated_at": "2026-08-16T20:10:00Z",
    "source_last_sync": null
  },
  "data": [
    { "label": "UNI - JI PARANA", "quantity": 480, "percentage": 23.0 }
  ]
}
```

### 7.2 Filtro não aplicável ao endpoint (login_aggregate recebendo filtro de O.S.)

**Request hipotético** (se um cliente MCP tentasse passar `os_subjects` — hoje a assinatura de `login_aggregate` nem aceita esse argumento, então isso descreve o comportamento se o contrato normalizasse a entrada por um dict genérico de filtros em vez de argumentos nomeados):
```json
{ "group_by": "regional", "filters": { "os_subjects": ["Sem sinal"] } }
```

**Response**:
```json
{
  "meta": {
    "applied_filters": { "group_by": "regional" },
    "ignored_filters": [
      { "field": "os_subjects", "reason": "NOT_APPLICABLE_TO_ENDPOINT" }
    ],
    "warnings": [],
    "generated_at": "2026-08-16T20:10:00Z",
    "source_last_sync": "2026-08-16T20:05:05Z"
  },
  "data": [ { "label": "UNI - JI PARANA", "quantity": 20292, "percentage": 23.01 } ]
}
```

### 7.3 Janela `since`/`until` com forma canônica exposta (login_outages)

**Request** (`POST /ai/infra/login-outages`):
```json
{ "since": "2026-08-16T13:00:00-04:00", "regionals": ["UNI - JARU"], "limit": 50 }
```

**Response** (já em produção hoje, sem os campos de `warnings` de exemplo abaixo — ilustra só a transparência da janela):
```json
{
  "meta": {
    "applied_filters": {
      "since": "2026-08-16T17:00:00Z",
      "until": "2026-08-16T23:00:00Z",
      "regionals": ["UNI - JARU"],
      "limit": 50,
      "resolved_as": { "status_changed_at": { "gte": "2026-08-16T17:00:00Z", "lte": "2026-08-16T23:00:00Z" } }
    },
    "ignored_filters": [],
    "warnings": [],
    "generated_at": "2026-08-16T23:00:00Z",
    "source_last_sync": "2026-08-16T22:55:05Z"
  },
  "data": [ ]
}
```

### 7.4 Alias `_since` do REST sendo normalizado (network_login_search)

**Request REST**: `GET /operations/network/logins/search?last_disconnected_since=2026-08-16T17:00:00-04:00`

**Response**:
```json
{
  "items": [],
  "total_encontrado": 0,
  "page": 1,
  "page_size": 50,
  "has_more": false,
  "meta": {
    "applied_filters": { "last_disconnected_at": { "gte": "2026-08-16T21:00:00Z" } },
    "ignored_filters": [],
    "warnings": [
      { "code": "DEPRECATED_FILTER_ALIAS", "received": "last_disconnected_since", "canonical": "last_disconnected_at" }
    ],
    "generated_at": "2026-08-16T23:00:00Z",
    "source_last_sync": "2026-08-16T22:55:05Z"
  }
}
```

### 7.5 Filtro aplicado em população parcial (search_logins com `transmitter_ids`)

**Request** (`POST /ai/infra/search-logins`):
```json
{ "transmitter_ids": ["903"], "page": 1, "page_size": 50 }
```

**Response** — o filtro foi de fato aplicado (permanece em `applied_filters`); o aviso `PARTIAL_DIMENSION_COVERAGE` só informa que a JOIN com telemetria ONU restringe a população, não que o filtro foi descartado:
```json
{
  "items": [ ],
  "total_encontrado": 214,
  "page": 1,
  "page_size": 50,
  "has_more": true,
  "meta": {
    "applied_filters": { "transmitter_ids": ["903"] },
    "ignored_filters": [],
    "warnings": [
      { "code": "PARTIAL_DIMENSION_COVERAGE", "dimension": "onu_telemetry" }
    ],
    "generated_at": "2026-08-16T23:00:00Z",
    "source_last_sync": "2026-08-16T22:55:05Z"
  }
}
```

---

## 8. Fora do escopo direto do contrato de filtros (observação, não proposta)

`group_by`, `entity`, `metric`, `granularity`, `date_field`, `sort_by` são **seletores de forma da resposta**, não filtros — mas têm a mesma doença: tipagem `Literal` só nos schemas Pydantic da IA (`ai/schemas.py`), e `str` livre nas rotas REST e nas duas tools MCP, com validação (quando existe) só dentro da função. Casos confirmados: `login_aggregate.group_by`, `coordinate_quality_audit.entity`. Recomendação (não decisão): tratar num `SelectorContractV1` separado, menor, quando este contrato for aprovado.

**Confirmado na revisão de aprovação (ajuste #1, §0):** até o `SelectorContractV1` existir, seletores continuam fora do vocabulário `applied_filters`/`ignored_filters` deste contrato, mesmo quando o valor recebido é inválido. Ver regra 4-bis em §5.

---

## 9. Matriz endpoint × filtro atual × filtro canônico

Legenda: ✅ suporta com o nome já canônico · 🔁 suporta com alias (nome diferente do canônico) · ⛔ não suporta (ausente) · 🅿️ parcial (suporta parte da capacidade, ex.: só `gte`)

### 9.1 Ordens de Serviço / Backlog / Garantia

| Filtro canônico | search_orders (IA) | aggregate_orders | orders_timeseries | backlog_aging | backlog_history | warranty_analytics | team_target_performance | REST `/operations/orders` |
|---|---|---|---|---|---|---|---|---|
| `os_subjects` | 🔁 `subjects` | 🔁 `subjects` | 🔁 `subjects` | 🔁 `subjects` | ⛔ | 🔁 `subjects` (só origem) | 🔁 `subjects` | 🔁 `subjects` |
| `regionals` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `customer_logins` | ✅ | ✅ | ✅ | ✅ | ⛔ | ✅ | ✅ | ⛔ (gap) |
| `search` | 🔁 `keyword` | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ | ✅ |
| `opened_at`..`source_updated_at` (9 campos) | ✅ (via `date_field` p/ 1 por vez) | ✅ | ✅ | ✅ | ⛔ (usa snapshot diário pré-agregado) | ✅ | ✅ | ✅ |
| `text_filters` | ✅ | ✅ | ✅ | ✅ | ⛔ | ✅ | ✅ | ⛔ (REST não expõe `text_filters` genérico, só filtros exatos) |
| `sector_filter` | ⛔ | ⛔ | ⛔ | ⛔ | ✅ (só este) | ⛔ | ⛔ | ⛔ |
| `fields`/`response_mode` | ✅ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ | ✅ |
| demais `FILTER_COLUMNS` (companies, states, cities, contract_types, person_types, os_types, diagnoses, departments, sectors, priorities, creators, responsibles, statuses, sla_statuses, projects, pops) | ✅ | ✅ | ✅ | ✅ | ⛔ | ✅ | ✅ | ✅ |
| `responsible_ixc_ids` | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ (só existe no backend, nenhum canal expõe) |

### 9.2 Login / Rede

| Filtro canônico | search_logins (IA/MCP) | REST `network_login_search` | login_aggregate | login_outages | login_timeseries | login_incident_analysis | query_login_status |
|---|---|---|---|---|---|---|---|
| `status_changed_at` | ✅ (5 operadores) | 🅿️🔁 `status_changed_since` (só gte) | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ |
| `last_connected_at` | ✅ | 🅿️🔁 `last_connected_since` (só gte) | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ |
| `last_disconnected_at` | ✅ | 🅿️🔁 `last_disconnected_since` (só gte) | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ |
| `captured_at` | ✅ | ⛔ (ausente, nem com alias) | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ |
| `since`/`until` | ⛔ (usa filtros de campo, não janela) | ⛔ | ⛔ (usa `status_changed_since`, ver §4.2 nota) | ✅ | ✅ | 🔁 `window_minutes` (açúcar) | ⛔ |
| `regionals` | ✅ | ✅ | ✅ | ✅ | ⛔ | ✅ | ✅ |
| `online_statuses` | ✅ | ✅ | ✅ | ⛔ (fixo em "N", intencional) | ⛔ | ✅ (fixo em "N" internamente) | ✅ |
| `pon_ids`/`transmitter_ids`/`contract_ids` | ✅ | ✅ | 🅿️ (`transmitter_id` só como `group_by`, não como filtro de lista) | ⛔ | ⛔ | ⛔ | ⛔ |
| trio geo | ✅ | ✅ | ⛔ | ⛔ | ⛔ | ⛔ | ✅ |

### 9.3 Casos de Gestão / Coordenadas

| Filtro canônico | opr_management_cases (só MCP remoto) | coordinate_quality_audit |
|---|---|---|
| `statuses` | 🔁 `status` (escalar) + `only_open` (açúcar) | — |
| `severities` | 🔁 `severity` (escalar) | — |
| `regionals` | 🔁 `regional` (escalar) | — |
| `case_types` | 🔁 `case_type` (escalar) | — |
| `supervisor_user_id` | ⛔ (existe no backend, não exposto) | — |
| `entity` | — | 🅿️ (`str` livre, sem `Literal` fora do schema IA) |

---

## 10. Ordem de implementação aprovada

Revisão do usuário trocou o piloto original (`search_logins`) por `aggregate_orders` — `search_logins` mistura ONU/geografia/4 filtros temporais e, se algo falhar, fica mais difícil isolar qual parte do contrato causou o problema. `aggregate_orders` foi justamente uma das fontes das inconsistências que motivaram este documento (o caso `subjects`/`os_subject`) e tem filtros de O.S. variados o suficiente para validar o padrão sem a complexidade extra do domínio de login.

1. **Piloto único: `aggregate_orders`.** Cobre `subjects → os_subjects`, `regionals`, `sectors`, `responsibles`, `team_models`, `statuses`, `text_filters`, datas (`opened_at` etc.) — normalização alias→canônico incorporada à função central (mesmo padrão já usado em `login_aggregate`/`search_logins` no item 1 da Fase 1), com o teste de paridade do §11 rodado com dado real antes de qualquer commit.
2. Só com o piloto aprovado (paridade 100% + `meta` correto): `search_orders`, `backlog_aging`, `team_target_performance` — mesmo padrão, mesmo teste de paridade cada um.
3. Só depois: `search_logins` (e demais endpoints de login/rede).
4. `SelectorContractV1` (§8) permanece proposta separada — não entra nesta rodada de implementação, para não misturar risco de filtro com risco de seletor na mesma mudança.

## 11. Critério de aceite: teste de paridade automatizado

Para cada endpoint migrado, antes de considerar a migração pronta, rodar a mesma consulta duas vezes contra dado real:

```
REQUEST LEGADO         REQUEST CANÔNICO
subjects=["X"]    vs   os_subjects=["X"]
```

E exigir, comparando as duas respostas:

- mesma quantidade de registros/grupos;
- mesmos IDs/registros retornados (quando o endpoint retorna itens, não só agregados);
- mesmas agregações e mesmos percentuais (quando o endpoint agrega);
- mesmo SQL lógico gerado (mesmas condições `WHERE`, verificável por inspeção da query ou do plano).

A **única** diferença permitida entre as duas respostas é o conteúdo de `meta`: a chamada com o nome legado deve trazer
```json
{"code": "DEPRECATED_FILTER_ALIAS", "received": "subjects", "canonical": "os_subjects"}
```
em `warnings`, e a chamada com o nome canônico não traz esse aviso. `data`/`items`/contagens/percentuais têm que ser idênticos byte a byte (ou numericamente idênticos, quando a serialização de ponto flutuante permitir).

Esse teste roda **antes** de qualquer commit do piloto, com dado real de produção (mesmo padrão já usado nas Fases anteriores deste plano — ver testes de `login_aggregate`/`coordinate_quality_audit`). Não é opcional: é o que protege contra o risco central desta refatoração — mudar nome de filtro e, por engano, mudar o número gerencial que ele produz.

### 11.1 Resultado do piloto (`aggregate_orders`) — executado em produção, 2026-08-16

| Verificação | Resultado |
|---|---|
| `subjects=["Suporte Externo Fibra Urbana"]` vs `os_subjects=["Suporte Externo Fibra Urbana"]`, `group_by="regional"`, período 2026-07-01..2026-08-16 | `data` idêntico byte a byte — 13 grupos, 2180 O.S. em ambos |
| `meta.warnings` do request legado | `[{"code": "DEPRECATED_FILTER_ALIAS", "received": "subjects", "canonical": "os_subjects"}]` |
| `meta.warnings` do request canônico | `[]` (sem aviso, como esperado) |
| Mesmo teste passando por `AiAggregationRequest` (schema real, `extra="forbid"`) | Confirmado — `os_subjects` só foi aceito porque o campo foi adicionado a `AiOrderFilters`; sem isso o schema teria rejeitado com 422 |
| Regressão dos demais filtros do checklist (`regionals`, `sectors` como `group_by`, `text_filters`, `statuses=[]`, `team_models=[]`, `responsibles=[]`) | Sem erro, resultado coerente (4 grupos de setor, 97,28% em "Suporte Externo Fibra") |
| `group_by` inválido (ex.: `"os_subject"`, o nome da coluna em vez da dimensão) | Continua levantando `ValueError` explícito — **não** virou `ignored_filters`, confirmando o ajuste #1 |
| Tool MCP remota `opr_aggregate_orders` | Continua registrada (22 tools no total) após a mudança |

**Conclusão do piloto: aprovado.** Nenhuma diferença numérica entre nome legado e canônico; `meta` reflete exatamente o que a especificação pede. Usuário aprovou em 2026-08-16 ("FilterContractV1: aprovado e validado por piloto real. Refatoração incremental autorizada por endpoint, com teste de paridade obrigatório.") — refatoração segue endpoint por endpoint, cada um com seu próprio teste de paridade antes do commit.

### 11.2 Resultado do lote 2 (`search_orders`) — executado em produção, 2026-08-16

| Verificação | Resultado |
|---|---|
| `subjects=["Suporte Externo Fibra Urbana"]` vs `os_subjects=[mesmo valor]`, período 2026-07-01..2026-08-16, page_size=50 | Itens idênticos (mesma ordem, mesmo `order_code` no topo: `IXC-1355271`) — 2315 O.S. em ambos, dict inteiro igual exceto `meta` |
| `meta.warnings` legado vs canônico | `DEPRECATED_FILTER_ALIAS` só no legado, ausente no canônico — igual ao piloto |
| Combinação `os_subjects` + `regionals` via schema real `AiSearchRequest` (`extra="forbid"`) | 551 O.S., `applied_filters` mostrando `os_subjects` e `regionals` juntos |
| Regressão de `keyword` (alias de `search`, mecanismo confirmado idêntico ao REST no ajuste #3) | 25529 O.S. encontradas com `keyword="fibra"`, `applied_filters` reportando `keyword` corretamente |

**Conclusão do lote 2: aprovado.** Mesmo padrão do piloto - `meta` adicionado como campo irmão de `items`/`total_encontrado` (não um wrapper `data`), consistente com `search_logins` já implementado na Fase 1.

### 11.3 Resultado do lote 3 (`backlog_aging`) — executado em produção, 2026-08-16

| Verificação | Resultado |
|---|---|
| `subjects=["Suporte Externo Fibra Urbana"]` vs `os_subjects=[mesmo valor]`, `group_by="regional"`, `date_to=2026-08-16` | `data` idêntico — 11 grupos em ambos, mesmos valores de `avg_age_days`/`median_age_days`/`oldest_order_code` |
| `meta.warnings` legado vs canônico | `DEPRECATED_FILTER_ALIAS` só no legado |
| Via schema real `AiBacklogAgingRequest` + `group_by="sector"` | 1 grupo, `applied_filters` correto |
| Tool MCP remota `opr_backlog_aging` | Continua registrada (22 tools) |

**Bug real encontrado e corrigido neste lote:** `OperationResponseMetaOut.warnings` (schema Pydantic) estava tipado como `list[str]`, mas `build_meta`/o próprio `DEPRECATED_FILTER_ALIAS` sempre produziram um `dict` (`{"code": ..., "received": ..., "canonical": ...}`). Isso já valia para `aggregate_orders`/`search_orders` (lotes 1 e 2), mas passou batido porque nenhuma das duas rotas tinha `response_model` estrito - `backlog_aging` foi a primeira desta série a validar a saída contra um schema Pydantic (`AiBacklogAgingResponse`, criado neste lote), e a validação falhou exatamente por isso. Corrigido em dois arquivos: `operations/schemas.py::OperationResponseMetaOut.warnings` e `ai_governance/response_meta.py::ResponseMeta.warnings`, ambos de `list[str]` para `list[dict]` - refletindo o que já era a realidade em produção, sem mudar nenhum dado retornado. Revalidado depois da correção: todos os 7 endpoints já enviados na Fase 1 (`login_aggregate`, `login_outages`, `login_timeseries`, `login_incident_analysis`, `search_logins`, `offline_login_clusters_response`, `coordinate_quality_audit`) continuam validando OK contra seus schemas.

**Conclusão do lote 3: aprovado**, com a correção de tipo acima incluída no mesmo commit.

### 11.4 Resultado do lote 4 (`team_target_performance`) — executado em produção, 2026-08-16

| Verificação | Resultado |
|---|---|
| `subjects=["Suporte Externo Fibra Urbana"]` vs `os_subjects=[mesmo valor]`, `granularity="week"`, período 2026-07-01..2026-08-16 | `data` idêntico — 56 linhas (bucket×modelo de equipe) em ambos |
| `meta.warnings` legado vs canônico | `DEPRECATED_FILTER_ALIAS` só no legado |
| Filtro vs baseline sem filtro (mesma função) | Confirmado que o filtro reduz de fato o resultado (soma de `actual`: 2256 filtrado vs 29927 sem filtro) - o número de linhas coincidir (56=56) era só o número de combinações bucket×modelo, não evidência de filtro inerte |
| Via schema real `AiTeamTargetPerformanceRequest` | 56 linhas, `applied_filters` correto |
| Tool MCP remota `opr_team_target_performance` | Continua registrada (22 tools) |

**Nota de escopo:** `team_target_performance` não filtra por si só - delega 100% pra `orders_timeseries` (não migrada nesta rodada). A normalização do alias foi implementada dentro de `team_target_performance`, antes de repassar os filtros já resolvidos pra `orders_timeseries` - a função interna em si permanece sem alteração, mantendo o escopo estritamente no endpoint autorizado.

**Conclusão do lote 4: aprovado.** Com este lote, os 4 endpoints do primeiro pacote de refatoração incremental (`aggregate_orders`, `search_orders`, `backlog_aging`, `team_target_performance`) estão completos.

### 11.5 Falha de produção confirmada pré-migração (`orders_timeseries`) — 2026-08-16

**Este achado é a própria justificativa de existência do FilterContractV1.** Antes da correção deste lote, `orders_timeseries` (`POST /ai/orders-timeseries`, `opr_orders_timeseries`) já aceitava `os_subjects` no schema (`AiOrderFilters.os_subjects`, adicionado no lote 1) sem erro de validação - mas a função não sabia reconhecer esse nome e descartava o filtro em silêncio, devolvendo a base inteira como se o filtro tivesse sido aplicado. Medido em produção antes da correção:

| Chamada | Resultado (`quantity` somado) |
|---|---|
| `subjects=["Suporte Externo Fibra Urbana"]` (nome legado) | 2.257 |
| `os_subjects=["Suporte Externo Fibra Urbana"]` (nome canônico, já aceito pelo schema) | 29.931 |
| sem filtro nenhum | 29.931 |

HTTP 200 nos três casos. Nenhum `ignored_filters`, nenhum aviso, nenhuma diferença visível na resposta que indicasse que o segundo caso era diferente do terceiro - a única forma de descobrir era comparar os números. Este é exatamente o padrão "schema aceita, função ignora" que o contrato existe para eliminar: mais perigoso que simplesmente não suportar um filtro, porque a resposta parece válida.

### 11.6 Resultado do lote 5 (`orders_timeseries`) — executado em produção, 2026-08-16

| Verificação | Resultado |
|---|---|
| `subjects=[...]` vs `os_subjects=[...]` depois da correção, `metric="fechadas"`, `granularity="week"` | `data` idêntico - soma de `quantity` = 2.258 em ambos (a pequena diferença de 2.257→2.258 frente à medição de §11.5 é drift natural do IXC entre as duas capturas, não uma divergência da correção) |
| `os_subjects` vs baseline sem filtro, depois da correção | 2.258 (filtrado) vs 29.934 (sem filtro) - confirma que o filtro canônico agora reduz de fato o resultado, ao contrário do comportamento pré-correção |
| `meta.warnings` legado vs canônico | `DEPRECATED_FILTER_ALIAS` só no legado |
| Via schema real `AiTimeseriesRequest` (`os_subjects` + `group_by="regional"`) | 90 pontos, `applied_filters` correto |
| Schema Pydantic (`AiTimeseriesResponse`, novo) | Validado OK |
| Tool MCP remota `opr_orders_timeseries` | Continua registrada (22 tools) |
| **Regressão pedida explicitamente: `team_target_performance` depois da mudança** | `data` idêntico à mesma chamada antes desta correção (56 linhas, soma de `actual` = 2.258) - **nenhuma dupla transformação** |
| Regressão dos 4 endpoints do pacote anterior (`aggregate_orders`, `search_orders`, `backlog_aging`) com `os_subjects` | Sem erro, contagens coerentes (13/2315/11 grupos respectivamente) |

**Simplificação aplicada em `team_target_performance` neste lote:** antes, `team_target_performance` tinha sua própria chamada a `_normalize_os_subjects_alias`, redundante com a de `orders_timeseries` (que ela chama internamente). Isso produzia uma dupla transformação silenciosa e inofensiva-mas-errada: o filtro chegava a `orders_timeseries` já resolvido para `subjects` (porque `team_target_performance` já tinha normalizado), e `orders_timeseries` interpretava isso como se o *chamador original* tivesse usado o alias legado, gerando um aviso `DEPRECATED_FILTER_ALIAS` incorreto dentro do `meta` que `orders_timeseries` retornava - nunca exposto ao usuário porque `team_target_performance` descartava esse `meta` por completo e construía o seu próprio. Corrigido removendo a normalização redundante de `team_target_performance`: agora ela repassa os filtros como recebeu e **reaproveita o `meta` de `orders_timeseries` diretamente**, sem reprocessar. `applied_filters` de `team_target_performance` ganhou 2 chaves novas como efeito colateral positivo (`metric: "fechadas"`, `group_by: "team_model"`) - mais transparente sobre o que de fato aconteceu por baixo, consistente com a regra 4-bis de seletores em `applied_filters` (§5).

**Conclusão do lote 5: aprovado.** P0 de confiabilidade corrigido, sem regressão em nenhum dos 4 endpoints anteriores, sem dupla transformação em `team_target_performance`. `FILTER_COLUMNS` global não foi tocado.

## 12. Próximos passos

1. ~~Usuário aprova (ou ajusta) os nomes canônicos e as regras de `ignored_filters`/`warnings` deste documento.~~ — feito: aprovado com os 4 ajustes de §0.
2. ~~Implementar o piloto único (`aggregate_orders`, §10.1) com o teste de paridade (§11) rodado e reportado antes do commit.~~ — feito, resultado em §11.1.
3. ~~Aguardar autorização explícita do usuário para o próximo lote.~~ — feito: aprovado em 2026-08-16, refatoração incremental autorizada por endpoint.
4. ~~`search_orders` (lote 2).~~ — feito, resultado em §11.2.
5. ~~`backlog_aging` (lote 3).~~ — feito, resultado em §11.3 (inclui correção de tipo em `OperationResponseMetaOut.warnings`).
6. ~~`team_target_performance` (lote 4).~~ — feito, resultado em §11.4. Primeiro pacote de refatoração incremental completo.
7. ~~`orders_timeseries` (lote 5, prioridade P0) - corrige a falha "schema aceita, função ignora" encontrada em produção.~~ — feito, resultado em §11.5 (achado registrado) e §11.6 (correção + regressão de `team_target_performance` sem dupla transformação).
8. ~~Nova varredura por todo endpoint que já aceita `AiOrderFilters`, procurando o padrão "schema aceita, função ignora".~~ — feita, resultado completo em §13. **Correção importante:** a varredura encontrou que a suposição do item 9 abaixo (baseada numa afirmação anterior deste mesmo documento) estava **errada** - há sim divergência real em `warranty_analytics_for_ai` para `os_subjects`. Nenhuma correção de código foi feita nesta etapa (só auditoria), por instrução explícita do usuário.
9. ~~`warranty_analytics_for_ai`: adiado por decisão do usuário - hoje `subjects`/`os_subjects` não são reconhecidos por nenhum dos dois nomes...~~ **Esta afirmação estava incorreta e foi corrigida pela varredura de §13.** `subjects` (legado) É reconhecido e aplicado no lado retorno/manutenção via `_dimension_conditions`; `os_subjects` (canônico, já aceito pelo schema) não é, e é descartado em silêncio - mesmo padrão do bug de `orders_timeseries` (§11.5). Ver §13.3 para evidência completa. Migração ainda não autorizada/feita, só o achado está registrado.
10. `text_filters.field="os_subject"`: risco real, mas bloqueado hoje pelo `Literal` fechado de `TextFilterField` (`ai/schemas.py`) - tratado como invariante de segurança, não como refatoração imediata. **Testado em 2026-08-16**: `AiOrderFilters.model_validate({"text_filters": [{"field": "os_subject", ...}]})` levanta `ValidationError` (422 na rota real) - invariante confirmado, nada a corrigir agora.
11. `sla_breakdown`/`sla_hierarchy` (dimensão `"subject"`, não filtro): permanece no futuro `SelectorContractV1` (§8), fora desta rodada.

Este documento não implica nenhum desses passos ter sido concluído além do que está explicitamente marcado como feito acima.

---

## 13. Auditoria completa — varredura "schema aceita, função ignora" (2026-08-16)

**Regra de segurança seguida nesta auditoria: nenhuma correção de código foi feita.** Só investigação, teste com dado real e registro de achados. Esta seção não altera nada das §0-§12 (contrato já aprovado) - é um relatório de achados anexado.

### 13.1 Endpoints auditados (inventário exaustivo, não presumido)

Busca exaustiva por toda referência a `AiOrderFilters` no backend (`grep -rn "AiOrderFilters"`) confirma que **exatamente 6 schemas de request** embutem `filters: AiOrderFilters`, e portanto exatamente 6 funções são o universo real desta auditoria - não há nenhum consumidor oculto:

| # | Request schema (`ai/schemas.py`) | Função (`ai/queries.py`) | Rota IA | Tool MCP remoto | Tool MCP local | Rota REST |
|---|---|---|---|---|---|---|
| 1 | `AiAggregationRequest` (linha 148) | `aggregate_orders` | `POST /ai/aggregate-orders` | `opr_aggregate_orders` | `opr_aggregate_orders` | não existe |
| 2 | `AiTimeseriesRequest` (linha 166) | `orders_timeseries` | `POST /ai/orders-timeseries` | `opr_orders_timeseries` | `opr_orders_timeseries` | não existe |
| 3 | `AiSearchRequest` (linha 188) | `search_orders` | `POST /ai/search-orders` | `opr_search_orders` | `opr_search_orders` | não existe |
| 4 | `AiBacklogAgingRequest` (linha ~333) | `backlog_aging` | `POST /ai/backlog-aging` | `opr_backlog_aging` | `opr_backlog_aging` | não existe |
| 5 | `AiWarrantyAnalyticsRequest` (linha ~390) | `warranty_analytics_for_ai` → `operations_queries.warranty_analytics` | `POST /ai/warranty-analytics` | `opr_warranty_analytics` | `opr_warranty_analytics` | não existe |
| 6 | `AiTeamTargetPerformanceRequest` (linha ~449) | `team_target_performance` (delega 100% pra `orders_timeseries`) | `POST /ai/team-target-performance` | `opr_team_target_performance` | `opr_team_target_performance` | não existe |

Confirmado por leitura de código (`operations/router.py` inteiro): **nenhuma dessas 6 funções tem rota REST equivalente** - REST (`/operations/orders`, `/operations/openings/orders`) usa seus próprios `Query()` params (`_filter_params`), uma estrutura paralela e mais antiga que nunca ganhou `os_subjects` - não é "estrutura derivada de `AiOrderFilters`", é um caminho de código diferente que alimenta o mesmo `_dimension_conditions` por baixo. Como as 3 rotas que existem (IA/MCP remoto/MCP local) chamam exatamente a mesma função Python de `ai/queries.py`, o comportamento de aplicação de filtro é **idêntico entre os 3 canais** para cada uma das 6 funções - a única diferença entre canais é on `os_subjects` é aceito pelo *schema* antes de chegar na função (todos os 3 usam o mesmo `AiOrderFilters`, então idêntico também nesse ponto).

**Confirmado como fora do escopo desta auditoria** (não usam `AiOrderFilters` nem estrutura equivalente): `backlog_history` (só aceita `sector_filter`, uma estrutura própria, e é pré-agregado por só 4 dimensões fixas - não tem nenhum dos ~30 filtros da lista), `team_targets_for_ai` (sem filtros), `filter_options_for_ai` (só período), `opr_management_cases` (schema próprio `ManagementCaseFilters`, domínio de gestão, não de O.S.).

### 13.2 Metodologia aplicada

Etapa A (análise de código) feita para as 6 funções, seguindo a cadeia real: schema (`AiOrderFilters`) → rota/tool → função `ai/queries.py` → `_dimension_conditions_with_text`/`_query_conditions`/chamada direta → `operations_queries._dimension_conditions` (FILTER_COLUMNS + team_models + weekdays + custom_window + search + closed_time) + `_text_filter_conditions` + `_sla_stage_filter_conditions` + `_geo_filter_conditions` + `_datetime_filter_conditions`. `_dimension_conditions` (`operations/queries.py:265-378`) foi lida linha a linha - é o funil comum a todas as 6 funções para os 19 campos de `FILTER_COLUMNS` + `team_models`/weekdays/custom_window/search/closed_time, e **não tem nenhuma lacuna** (todo campo é lido via `.get()` e aplicado se presente).

Etapa B (teste real) rodada para todo caso onde a etapa A não bastou para ter certeza - valores reais existentes na base (nunca um valor que dá zero nos dois lados), comparando total/soma filtrado vs. baseline sem filtro.

### 13.3 🔴 P0 confirmado: `warranty_analytics_for_ai` ignora `os_subjects` em silêncio (mesmo padrão do bug de `orders_timeseries`)

**Correção de uma afirmação anterior deste documento:** a versão anterior deste texto (§12, item 9) dizia que `warranty_analytics` não reconhecia nem `subjects` nem `os_subjects`, então não haveria divergência. **Isso estava errado** - a leitura mais profunda feita nesta auditoria (não feita antes) mostra que o lado retorno/manutenção da função (`operations/queries.py:1067`, `retorno_conditions = _dimension_conditions(db, user, {**filters, "os_types": []})`) recebe o `filters` **completo**, então `subjects` (nome de `FILTER_COLUMNS`) É reconhecido e aplicado ali - só `os_subjects` (o nome que o schema já aceita desde o lote 1) não é, porque `FILTER_COLUMNS` não tem essa chave.

Teste real, `date_from=2026-01-01`, `date_to=2026-08-16`, valor real `"Suporte Externo Fibra Urbana"`:

| Chamada | `numerator` (garantias encontradas) |
|---|---|
| sem filtro nenhum | 2.750 |
| `subjects=["Suporte Externo Fibra Urbana"]` (legado) | 649 |
| `os_subjects=["Suporte Externo Fibra Urbana"]` (canônico, já aceito pelo schema) | **2.750 — idêntico ao sem filtro** |

Mesmo padrão exato do bug de `orders_timeseries` (§11.5): HTTP 200, nenhum erro, nenhum `ignored_filters`, nenhum aviso - o schema aceita, a função ignora, a resposta parece válida.

- **arquivo:linha:** `ai/queries.py:1116-1141` (`warranty_analytics_for_ai`, repassa `**filters` sem normalizar) → `operations/queries.py:1067` (`retorno_conditions = _dimension_conditions(db, user, {**filters, "os_types": []})`, só reconhece `subjects`, não `os_subjects`).
- **causa raiz:** idêntica à de `orders_timeseries` antes da correção - `os_subjects` nunca foi ensinado a `FILTER_COLUMNS`/`_dimension_conditions` (decisão deliberada de não tocar em `FILTER_COLUMNS` global), e `warranty_analytics_for_ai` é a única das 6 funções que ainda não tem a etapa de normalização alias→canônico.
- **impacto operacional:** qualquer chamada de IA/MCP usando `os_subjects` (o nome que o próprio schema recomenda como canônico) pra restringir a análise de garantia por assunto de O.S. recebe silenciosamente a taxa de garantia **da base inteira**, não do assunto pedido - um número gerencial errado sem nenhum sinal de que algo está errado.

### 13.4 🔴 P0 confirmado: `warranty_analytics_for_ai` ignora `text_filters`, `has_coordinates`, trio geográfico e os 9 filtros de data - por completo, para qualquer nome

Achado adicional (não coberto pela suposição anterior deste documento): `operations_queries.warranty_analytics` (`operations/queries.py:995-1140`) **nunca chama** `_text_filter_conditions`, `_sla_stage_filter_conditions`, `_geo_filter_conditions` ou `_datetime_filter_conditions` em nenhum ponto da função - só `_dimension_conditions`, duas vezes (origem e retorno). Isso significa que **todo** o resto do contrato de filtros (não é questão de alias, é ausência total de aplicação) é aceito pelo schema e ignorado:

| Filtro testado | Valor usado | `numerator` sem filtro | `numerator` com filtro | Aplicado? |
|---|---|---|---|---|
| `text_filters` | `[{"field":"subject","operator":"contains","value":"Fibra"}]` | 2.750 | 2.750 | 🔴 Não |
| `has_coordinates` | `True` | 2.750 | 2.750 | 🔴 Não |
| trio geográfico | `near_latitude=-10.88, near_longitude=-61.95, radius_km=5` | 2.750 | 2.750 | 🔴 Não |
| `opened_at` | `{"gte": "2026-08-01"}` | 2.750 | 2.750 | 🔴 Não |
| `scheduled_after_sla` | `True` | 2.750 | 2.750 | 🔴 Não |

Por inferência de código (mesma chamada, mesmas 4 funções nunca invocadas): `closed_at`, `deadline_at`, `scheduled_at`, `assumed_at`, `displacement_started_at`, `execution_started_at`, `finished_at`, `source_updated_at` e `sla_expired_before_schedule` têm o mesmo destino - nenhum foi testado individualmente porque a causa raiz (a função nunca lê essas 4 categorias) já está confirmada por leitura direta do código-fonte da função inteira, sem nenhuma chamada condicional que pudesse variar por valor.

- **arquivo:linha:** `operations/queries.py:995-1141` (corpo completo de `warranty_analytics` - as únicas condições adicionadas ao `SELECT` são as de `_dimension_conditions`, `contract_id`/`order_code` não nulos, `closed_at`/`opened_at` do próprio período, e o `os_type` do tipo elegível).
- **causa raiz:** diferente do caso de `os_subjects` (que é um problema de nome/alias), este é estrutural - a função nunca foi escrita para aceitar esses 13 filtros, mas o schema (`AiOrderFilters`, compartilhado com as outras 5 funções) os aceita de qualquer forma porque é o mesmo `filters: AiOrderFilters` reaproveitado nos 6 request schemas.
- **impacto operacional:** mais amplo que o caso `os_subjects` - qualquer tentativa de restringir a análise de garantia por texto livre, geografia, ou qualquer marco de data/hora específico (não só o período `date_from`/`date_to` de granularidade dia) é descartada em silêncio.

### 13.5 🔴 P0 de observabilidade confirmado (cross-cutting, afeta os 5 endpoints já migrados): filtros compostos "tudo ou nada" com peça faltante fazem `meta.applied_filters` mentir

Achado novo, não coberto pelas Fases anteriores. Dois grupos de filtro só têm efeito quando **todas** as peças estão presentes (documentado no próprio código - `_geo_filter_conditions`/`_dimension_conditions`), mas `build_meta` não sabe disso e ecoa qualquer peça isolada como se tivesse sido aplicada:

**Trio geográfico** (`near_latitude`/`near_longitude`/`radius_km`) - teste real, `aggregate_orders`, período 2026-07-01..2026-08-16:

| Chamada | total (soma `quantity`) | `meta.applied_filters` |
|---|---|---|
| sem filtro | 31.365 | `{}` |
| `near_latitude=-10.88` (sozinho, sem `near_longitude`/`radius_km`) | **31.365 — idêntico** | `{"near_latitude": -10.88, ...}` **← mostra como aplicado** |

Reproduzido de forma idêntica em `search_orders` (33.276 = 33.276, `meta.applied_filters` mostrando `near_latitude` isolado).

**Composto `custom_window_*`** (5 peças: `custom_window_basis`, `custom_window_start_weekday`, `custom_window_start_time`, `custom_window_end_weekday`, `custom_window_end_time`) - teste real, `aggregate_orders`, mesmo período, só 2 das 5 peças enviadas:

| Chamada | total | `meta.applied_filters` |
|---|---|---|
| sem filtro | 31.365 | `{}` |
| `custom_window_basis=["opened"], custom_window_start_weekday="monday"` (2 de 5 peças) | **31.365 — idêntico** | `{"custom_window_basis": [...], "custom_window_start_weekday": "monday", ...}` **← mostra como aplicado** |

- **arquivo:linha:** `ai/queries.py` - `aggregate_orders`/`search_orders`/`backlog_aging`/`orders_timeseries` constroem `applied_filters` como `{**filters, ...seletores}` (echo direto do dict recebido, só removendo valores vazios) - nunca verificam se um filtro composto está *completo* antes de reportá-lo. A condição real "só ativa com as 5/3 peças" vive em `operations/queries.py:316-346` (`custom_window`) e `ai/queries.py:112-136` (`_geo_filter_conditions`), mas o código que monta `applied_filters` não consulta essa mesma regra.
- **causa raiz:** `build_meta`/os pontos de chamada tratam `applied_filters` como "o que o chamador enviou (não vazio)", não como "o que efetivamente formou uma condição SQL" - correto pra filtros atômicos (`regionals`, `os_subjects`, etc.), mas errado pra qualquer filtro que exija combinação.
- **impacto operacional:** exatamente o caso "meta mentindo" pedido para investigar - um chamador que envie só parte de um filtro composto (erro de integração comum, ex.: esquecer `radius_km`) recebe a base inteira sem nenhum aviso, e `meta` reforça a falsa impressão de que o filtro foi aplicado.
- **Endpoints afetados:** `aggregate_orders`, `search_orders`, `backlog_aging`, `orders_timeseries`, `team_target_performance` (delega a `orders_timeseries`, herda o problema) - os 5 já migrados. `warranty_analytics_for_ai` não é afetado por este ponto porque nem tem `meta` ainda (§13.4 cobre a ausência total de aplicação lá).

### 13.6 Matriz completa endpoint × filtro

Legenda: ✅ APPLIED · 🔴 IGNORED_SILENTLY · ⛔ REJECTED · ⬜ NOT_SUPPORTED_BY_DESIGN · 🟨 PARTIAL_COVERAGE

| Filtro | `aggregate_orders` | `orders_timeseries` | `search_orders` | `backlog_aging` | `team_target_performance` | `warranty_analytics_for_ai` |
|---|---|---|---|---|---|---|
| `companies` | ✅ | ✅ | ✅ | ✅ | ✅ (via orders_timeseries) | 🟨 (só retorno; não afeta denominador - não é um dos 5 `WARRANTY_ORIGIN_SHARED_FILTERS`... **correção:** `companies` **é** um dos 5 compartilhados, então ✅ pleno, afeta origem e retorno) |
| `regionals` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (um dos 5 `WARRANTY_ORIGIN_SHARED_FILTERS` - testado: 682 vs 2.750) |
| `states` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (compartilhado) |
| `cities` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (compartilhado) |
| `contract_types` | ✅ | ✅ | ✅ | ✅ | ✅ | 🟨 (só retorno, não afeta origem/denominador - não é compartilhado) |
| `person_types` | ✅ | ✅ | ✅ | ✅ | ✅ | 🟨 (só retorno) |
| `os_types` | ✅ | ✅ | ✅ | ✅ | ✅ | ⬜ (forçado `[]` no retorno por design documentado, `operations/queries.py:1067`) |
| `os_subjects` (canônico) | ✅ (corrigido lote 1) | ✅ (corrigido lote 5) | ✅ (corrigido lote 2) | ✅ (corrigido lote 3) | ✅ (corrigido lote 4) | 🔴 **P0 - §13.3** |
| `subjects` (legado) | ✅ (com aviso) | ✅ (com aviso) | ✅ (com aviso) | ✅ (com aviso) | ✅ (com aviso) | ✅ (aplicado no retorno, sem aviso - `warranty_analytics_for_ai` não tem `meta`) |
| `diagnoses` | ✅ | ✅ | ✅ | ✅ | ✅ | 🟨 (só retorno; testado: 0 vs 2.750 com valor real) |
| `departments` | ✅ | ✅ | ✅ | ✅ | ✅ | 🟨 (só retorno) |
| `sectors` | ✅ | ✅ | ✅ | ✅ | ✅ | 🟨 (só retorno; testado: 2.445 vs 2.750) |
| `priorities` | ✅ | ✅ | ✅ | ✅ | ✅ | 🟨 (só retorno) |
| `creators` | ✅ | ✅ | ✅ | ✅ | ✅ | 🟨 (só retorno) |
| `responsibles` | ✅ | ✅ | ✅ | ✅ | ✅ | 🟨 (só retorno) |
| `statuses` | ✅ | ✅ | ✅ | ✅ | ✅ | 🟨 (só retorno; testado: 2.731 vs 2.750) |
| `sla_statuses` | ✅ | ✅ | ✅ | ✅ | ✅ | 🟨 (só retorno) |
| `projects` | ✅ | ✅ | ✅ | ✅ | ✅ | 🟨 (só retorno) |
| `pops` | ✅ | ✅ | ✅ | ✅ | ✅ | 🟨 (só retorno) |
| `customer_logins` | ✅ | ✅ | ✅ | ✅ | ✅ | 🟨 (só retorno) |
| `team_models` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (5º campo compartilhado - testado: 26 vs 2.750; único que afeta origem+retorno por design explícito, ver docstring de `_warranty_origin_filters`) |
| `opened_weekdays` | ✅ | ✅ | ✅ | ✅ | ✅ | 🟨 (só retorno) |
| `closed_weekdays` | ✅ | ✅ | ✅ | ✅ | ✅ | 🟨 (só retorno) |
| `custom_window_*` (5 peças) | 🟡 ✅ se completo / 🔴 se incompleto (§13.5) | idem | idem | idem | idem | 🟨 (só retorno, e sujeito ao mesmo problema de completude) |
| `search`/`keyword` | ⬜ (schema não tem campo `search`; `keyword` só existe em `AiSearchRequest`) | ⬜ | ✅ (via `keyword`, testado: 25.529 resultados) | ⬜ | ⬜ | ⬜ |
| `text_filters` | ✅ | ✅ | ✅ | ✅ | ✅ | 🔴 **P0 - §13.4** |
| `scheduled_after_sla` | ✅ | ✅ | ✅ | ✅ | ✅ | 🔴 **§13.4** |
| `sla_expired_before_schedule` | ✅ (inferido, mesma função) | ✅ (inferido) | ✅ (inferido) | ✅ (inferido) | ✅ (inferido) | 🔴 (inferido, §13.4) |
| `has_coordinates` | ✅ (inferido) | ✅ (inferido) | ✅ (inferido) | ✅ (inferido) | ✅ (inferido) | 🔴 **§13.4** |
| `near_latitude`/`near_longitude`/`radius_km` | 🟡 ✅ se os 3 / 🔴 se parcial (§13.5) | idem | idem (testado) | idem | idem | 🔴 (nunca aplicado, §13.4) |
| `opened_at` | ✅ (testado: 2.566 vs 31.365) | ✅ (herdado da correção do lote 5) | ✅ (inferido, mesma `_datetime_filter_conditions`) | ✅ (inferido) | ✅ (inferido) | 🔴 **§13.4** (testado) |
| `closed_at`, `deadline_at`, `scheduled_at`, `assumed_at`, `displacement_started_at`, `execution_started_at`, `finished_at`, `source_updated_at` | ✅ (inferido, mesma função de `opened_at`) | ✅ (inferido) | ✅ (inferido) | ✅ (inferido) | ✅ (inferido) | 🔴 (inferido, mesma causa de `opened_at`, §13.4) |

**Nota sobre `companies` na coluna `warranty_analytics_for_ai`:** a primeira redação desta tabela classificou `companies` como 🟨, mas `companies` **é** um dos 5 campos de `WARRANTY_ORIGIN_SHARED_FILTERS` (`operations/queries.py:246`) - corrigido para ✅ pleno na célula acima. Erro cometido e corrigido durante a própria escrita desta seção, registrado aqui de propósito para não escondstruir o processo.

### 13.7 Auditoria de `text_filters` (pedida em separado)

| Valor de `AiTextFilter.field` (`Literal`, `ai/schemas.py:40-42`) | Chave em `TEXT_FILTER_COLUMNS` (`ai/queries.py:218-227`) | Coluna SQL | Implementado? |
|---|---|---|---|
| `sector` | `sector` | `OperationOrder.sector` | ✅ |
| `subject` | `subject` | `OperationOrder.os_subject` | ✅ |
| `diagnosis` | `diagnosis` | `OperationOrder.diagnosis` | ✅ |
| `responsible` | `responsible` | `OperationOrder.responsible` | ✅ |
| `city` | `city` | `OperationOrder.city` | ✅ |
| `department` | `department` | `OperationOrder.department` | ✅ |
| `service_description` | `service_description` | `_SERVICE_DESCRIPTION_EXPR` (expressão sobre `raw_payload`) | ✅ |
| `neighborhood` | `neighborhood` | `OperationOrder.neighborhood` | ✅ |

**Todo valor aceito pelo `Literal` tem implementação correspondente em `TEXT_FILTER_COLUMNS` - nenhuma lacuna encontrada.** Os dois dicts têm exatamente as mesmas 8 chaves, confirmado por comparação direta.

Caso conhecido revalidado: `field="os_subject"` (variante com nome de coluna, não de dimensão) **continua rejeitado** - testado em 2026-08-16: `AiOrderFilters.model_validate({"text_filters": [{"field": "os_subject", "operator": "contains", "value": "Fibra"}]})` levanta `pydantic.ValidationError` (`Input should be 'sector', 'subject', 'diagnosis', 'responsible', 'city', 'department', 'service_description' or 'neighborhood'`) - 422 garantido na rota real, nas 3 vias (IA, MCP remoto via `_validated_filters`, MCP local via HTTP pra rota IA). Nenhum outro caso de "Literal aceita, `TEXT_FILTER_COLUMNS` não reconhece" foi encontrado - os dois conjuntos são idênticos hoje.

### 13.8 Regressão de paridade dos 5 endpoints já migrados (verificação da auditoria, não bateria completa)

Rodado em 2026-08-16, valor real `"Suporte Externo Fibra Urbana"`, `subjects=[...]` vs `os_subjects=[...]`:

| Endpoint | `data`/`items` idênticos? | Aviso legado presente só no legado? |
|---|---|---|
| `aggregate_orders` | ✅ Sim | ✅ Sim |
| `search_orders` | ✅ Sim (2.315 itens, mesma ordem) | ✅ Sim |
| `backlog_aging` | ✅ Sim | ✅ Sim |
| `team_target_performance` | ✅ Sim | ✅ Sim |
| `orders_timeseries` | ✅ Sim | ✅ Sim |

Nenhuma regressão introduzida pelos lotes 1-5.

### 13.9 Resumo por severidade

**🔴 P0 (3 achados):**
1. `warranty_analytics_for_ai` ignora `os_subjects` em silêncio (§13.3) - mesmo padrão do bug pré-correção de `orders_timeseries`.
2. `warranty_analytics_for_ai` ignora `text_filters`/`has_coordinates`/trio geográfico/os 9 filtros de data por completo, para qualquer nome (§13.4) - estrutural, não é questão de alias.
3. `meta.applied_filters` mente sobre o trio geográfico e o composto `custom_window_*` quando enviados parcialmente, nos 5 endpoints já migrados (§13.5) - achado de observabilidade, cross-cutting.

**🟠 P1 (1 achado, já registrado nas Fases anteriores, não repetido aqui em detalhe):** cobertura parcial de `pon_ids`/`transmitter_ids`/`contract_ids` em `search_logins` (fora do escopo desta auditoria - é login, não O.S. - já tratada com `PARTIAL_DIMENSION_COVERAGE` desde a revisão de aprovação, §0 ajuste #2). Nesta auditoria (domínio O.S.), o equivalente estrutural é a cobertura parcial documentada e intencional de 14 filtros em `warranty_analytics_for_ai` que só afetam o lado retorno/numerador, nunca o lado origem/denominador (`contract_types`, `person_types`, `diagnoses`, `departments`, `sectors`, `priorities`, `creators`, `responsibles`, `statuses`, `sla_statuses`, `projects`, `pops`, `customer_logins`, `opened_weekdays`/`closed_weekdays`/`custom_window_*`) - comportamento correto e documentado em código, mas **sem nenhum aviso pro chamador** porque a função não tem `meta` ainda.

**🟡 P2 (2 achados, sem impacto atual):**
1. `os_types` forçado a `[]` no lado retorno de `warranty_analytics_for_ai` - documentado explicitamente no código (`NOT_SUPPORTED_BY_DESIGN`, correto).
2. `search`/`keyword` ausente de 5 das 6 funções - o schema (`AiOrderFilters`) nem tem campo `search`, então é `REJECTED`/`NOT_SUPPORTED_BY_DESIGN` por construção, não um filtro aceito-e-ignorado.

**✅ OK:** todos os 19 campos de `FILTER_COLUMNS` + `team_models` + `opened_weekdays`/`closed_weekdays`/`custom_window_*` (quando completo) + `text_filters` (8 campos, todos com implementação) + os 9 filtros de data + `scheduled_after_sla`/`sla_expired_before_schedule`/`has_coordinates`/trio geográfico (quando completo) nos **5 endpoints já migrados**. `os_subjects` funcionando corretamente com aviso de alias nos mesmos 5.

### 13.10 Respostas objetivas

1. **Quantos endpoints foram auditados?** 6 (`aggregate_orders`, `orders_timeseries`, `search_orders`, `backlog_aging`, `team_target_performance`, `warranty_analytics_for_ai`) - confirmado como o universo completo por busca exaustiva de `AiOrderFilters` no backend, não presumido.
2. **Quantos filtros/combinações foram verificados?** 29 campos de `AiOrderFilters` × 6 endpoints = 174 combinações possíveis; testadas com dado real (não só inferidas por código) 21 combinações específicas (as mais suspeitas + as que geraram achado); as demais confirmadas por leitura completa e sem ambiguidade do código-fonte das funções compartilhadas (`_dimension_conditions`, que não tem nenhuma ramificação condicional por valor que pudesse escapar da leitura estática).
3. **Quantos P0 foram encontrados?** 3 (§13.3, §13.4, §13.5).
4. **Quantos P1?** 1 categoria (cobertura parcial de 14 filtros em `warranty_analytics_for_ai`, sem aviso).
5. **Existe hoje algum outro caso igual ao bug pré-correção do `orders_timeseries`?** Sim - `warranty_analytics_for_ai` ignorando `os_subjects` (§13.3) é exatamente o mesmo padrão. Além dele, os 9 filtros de data + `text_filters` + `has_coordinates`/trio geográfico no mesmo endpoint (§13.4) são uma variante mais ampla do mesmo problema geral (schema aceita, função não aplica), só que por ausência estrutural de implementação, não por nome de alias.
6. **Existe algum caso em que `meta.applied_filters` afirma algo que a query não fez?** Sim - o trio geográfico e o composto `custom_window_*` quando enviados parcialmente, nos 5 endpoints já migrados (§13.5). `warranty_analytics_for_ai` não entra nesse item porque ainda não tem `meta` nenhum (a mentira não pode existir onde não há afirmação).
7. **Quais seriam os próximos endpoints/filtros a corrigir, em ordem de risco?**
   1. `warranty_analytics_for_ai` → `os_subjects` (§13.3) - mesma classe de correção já feita 5 vezes (`_normalize_os_subjects_alias`), risco/esforço já validado pelo padrão.
   2. `meta.applied_filters` mentindo no trio geográfico/`custom_window_*` incompletos (§13.5) - correção transversal (função utilitária que valida completude antes de reportar), afeta os 5 endpoints já migrados de uma vez.
   3. `warranty_analytics_for_ai` → adicionar `meta` (pré-requisito para os itens 4 e 5) e então decidir, com o usuário, se os 13 filtros de cobertura parcial (§13.9, P1) merecem um aviso `PARTIAL_DIMENSION_COVERAGE`-equivalente.
   4. `warranty_analytics_for_ai` → `text_filters`/`has_coordinates`/trio geográfico/9 filtros de data (§13.4) - maior esforço (nenhuma implementação existe, não é só renomear um alias) e menor urgência que o item 1 (esses filtros nunca funcionaram, então não há uma "promessa recente do schema" sendo quebrada como no caso `os_subjects`/`orders_timeseries`).

Nenhuma dessas correções foi implementada nesta etapa. Aguardando autorização explícita do usuário, endpoint por endpoint, como nos lotes anteriores.

---

## 14. Lotes 6 e 7 (correção dos P0 da auditoria) + reauditoria final (2026-08-16)

Autorizado pelo usuário na ordem de risco definida em §13.10, item 7: lote 6 (`os_subjects` em `warranty_analytics_for_ai`) primeiro, lote 7 (`meta` mentindo em filtro composto) depois. Escopo estrito - nenhuma expansão funcional além do autorizado.

### 14.1 Lote 6 — `warranty_analytics_for_ai` reconhece `os_subjects`

**Correção:** `_normalize_os_subjects_alias` (mesmo helper dos 5 lotes anteriores) chamada dentro de `warranty_analytics_for_ai` (`ai/queries.py`), antes de repassar `**filters` pra `operations_queries.warranty_analytics`. **`operations_queries.warranty_analytics` (compartilhada com a aba Garantias da tela, REST) não foi tocada** - continua sem `meta`, sem normalização, exatamente como estava. Novo campo `meta: OperationResponseMetaOut` em `AiWarrantyAnalyticsResponse` (sibling aos campos existentes).

**Teste de paridade (dado real, `date_from=2026-01-01`, `date_to=2026-08-16`, valor `"Suporte Externo Fibra Urbana"`):**

| Chamada | `numerator` |
|---|---|
| sem filtro (baseline) | 2.750 |
| `subjects=[...]` (legado) | 649 |
| `os_subjects=[...]` (canônico) | **649 - idêntico ao legado, não mais 2.750** |

`data` idêntico entre legado e canônico (exceto `meta`); `meta.warnings` do legado traz `DEPRECATED_FILTER_ALIAS`, canônico não traz nada. Validado via schema real `AiWarrantyAnalyticsRequest`. REST/UI (`operations_queries.warranty_analytics` chamada direta, sem passar pela camada de IA) confirmado inalterado: `numerator=649` com `subjects`, sem `meta` no retorno. Regressão dos 5 endpoints anteriores confirmada sem quebra. Tool MCP remota `opr_warranty_analytics` confirmada registrada (22 tools).

**Commit:** [f656980](https://github.com/paulo-ope/Gamificacao-UNI-OPR/commit/f656980).

### 14.2 Lote 7 — `meta.applied_filters` não ecoa mais filtro composto incompleto

**Correção:** nova função `_composite_filter_report(filters)` (`ai/queries.py`) - verifica os 2 grupos (`geo_radius`: `near_latitude`/`near_longitude`/`radius_km`; `custom_window`: as 5 peças de `custom_window_*`) contra o `filters` recebido. Grupo com **algumas mas não todas** as peças: remove essas peças de `applied_filters` e gera `{"code": "INCOMPLETE_COMPOSITE_FILTER", "filter": "geo_radius"|"custom_window", "received_fields": [...], "missing_fields": [...]}`. Grupo completo ou totalmente ausente: comportamento inalterado. Aplicada aos 4 pontos que constroem `applied_filters` (`aggregate_orders`, `orders_timeseries`, `search_orders`, `backlog_aging`) - `team_target_performance` herda automaticamente (reaproveita o `meta` de `orders_timeseries` por completo). **`warranty_analytics_for_ai` não recebeu esta correção** - não suporta esses filtros de forma alguma (§13.4), aplicar a função ali sem implementar o filtro em si seria expandir comportamento só pra participar do teste (explicitamente vedado pelo usuário).

**Teste completo/incompleto/baseline (dado real, `aggregate_orders`, período 2026-07-01..2026-08-16):**

| Cenário | total (`quantity`) | em `applied_filters`? | warning? |
|---|---|---|---|
| sem filtro (baseline) | 31.366 | - | - |
| `near_latitude` sozinho (incompleto) | **31.366 - idêntico ao baseline** | Não | `INCOMPLETE_COMPOSITE_FILTER`, `received_fields: ["near_latitude"]`, `missing_fields: ["near_longitude", "radius_km"]` |
| trio completo | 10.466 (diferente) | Sim, os 3 campos | Nenhum |
| `custom_window_basis`+`custom_window_start_weekday` sozinhos (2 de 5) | **31.366 - idêntico** | Não | `INCOMPLETE_COMPOSITE_FILTER`, `filter: "custom_window"`, 2 recebidos, 3 faltando |
| `custom_window_*` completo (5 peças) | 27.868 (diferente) | Sim, as 5 peças | Nenhum |

Mesmo padrão confirmado com dado real em `search_orders` (33.277 baseline = 33.277 incompleto ≠ 11.008 completo), `backlog_aging` (15.449 = 15.449 ≠ 4.901), `orders_timeseries` (29.938 = 29.938) e `team_target_performance` (herdado, mesmo `meta` de `orders_timeseries`). Regressão de `os_subjects`/`subjects` (lotes 1-6) confirmada sem quebra nos 5. Validado via schema real `AiAggregationRequest`. Tool MCP remota confirmada com as 22 tools intactas.

**Commit:** [c404749](https://github.com/paulo-ope/Gamificacao-UNI-OPR/commit/c404749).

### 14.3 Reauditoria dos 6 endpoints pós-lotes 6 e 7

**🔴 Achado novo, efeito colateral do lote 6 - `warranty_analytics_for_ai` ganhou uma NOVA instância de "`meta` mentindo" ao ganhar `meta`.**

Antes do lote 6, `warranty_analytics_for_ai` não tinha `meta` - a ausência de `meta` não é uma mentira (não havia afirmação nenhuma). Ao adicionar `meta` no lote 6 (necessário pra reportar `os_subjects`/`subjects` corretamente), `applied_filters` passou a ecoar **qualquer** campo de `filters` recebido, incluindo os 13 filtros que a função nunca aplica de verdade (`text_filters`, `has_coordinates`, trio geográfico, os 9 filtros de data, `scheduled_after_sla`, `sla_expired_before_schedule` - ver §13.4). Teste real, 2026-08-16, mesmo período de sempre:

```
text_filters=[{"field":"subject","operator":"contains","value":"Fibra"}] + opened_at={"gte":"2026-08-01"} + near_latitude=-10.88
numerator = 2.750 (idêntico ao baseline sem filtro nenhum)
meta.applied_filters = {"text_filters": [...], "opened_at": {...}, "near_latitude": -10.88, ...}  <- ecoando os 3 como aplicados
meta.warnings = []
```

Isto **não é a mesma causa raiz** do achado do lote 7 (que era especificamente sobre completude de filtro composto) - é o problema mais amplo e original do §13.4 (função não implementa o filtro, ponto), agora visível através de um `meta` que antes não existia. Classificado como **🔴 P0 de observabilidade, não corrigido nesta etapa** - corrigir exigiria ou (a) implementar de fato os 13 filtros em `warranty_analytics_for_ai` (era o item 4 do plano de risco de §13.10, deliberadamente fora do escopo dos lotes 6/7), ou (b) fazer `warranty_analytics_for_ai` reconhecer esses campos como não suportados e não ecoá-los/gerar `ignored_filters`/aviso próprio - qualquer uma das duas é uma mudança de comportamento nova, não autorizada nesta rodada. **Registrado, não corrigido, aguardando autorização.**

**Estado dos 3 P0 originais (§13.3, §13.4, §13.5):**

| P0 original | Status |
|---|---|
| §13.3 - `warranty_analytics_for_ai` ignora `os_subjects` | ✅ Corrigido (lote 6, §14.1) |
| §13.4 - `warranty_analytics_for_ai` nunca aplica `text_filters`/geo/9 filtros de data | 🔴 **Ainda existe** - deliberadamente não corrigido nesta rodada (fora do escopo autorizado para os lotes 6/7); e agora tem uma manifestação adicional em `meta` (achado acima) |
| §13.5 - `meta` mentindo no trio geo/`custom_window_*` incompletos | ✅ Corrigido (lote 7, §14.2) nos 5 endpoints já migrados. Não se aplica a `warranty_analytics_for_ai` (nunca aplicou esses filtros, completo ou não). |

**P1 (§13.9) - inalterado:** os 14 filtros de cobertura parcial em `warranty_analytics_for_ai` (afetam só o lado retorno/numerador, nunca o lado origem/denominador, exceto os 5 `WARRANTY_ORIGIN_SHARED_FILTERS`) continuam sem nenhum aviso equivalente a `PARTIAL_DIMENSION_COVERAGE`. Não corrigido nesta rodada, por instrução explícita do usuário.

**P2 (§13.9) - inalterado:** `os_types` forçado a `[]` no lado retorno (documentado, correto por design); `search`/`keyword` ausente de 5 das 6 funções (schema nem tem o campo, `NOT_SUPPORTED_BY_DESIGN`/`REJECTED` por construção).

### 14.4 Confirmação objetiva final

- **Existe algum caso "schema aceita → query ignora → 200 OK" remanescente?** Sim - os 13 filtros de `warranty_analytics_for_ai` cobertos em §13.4 (`text_filters`, `has_coordinates`, trio geográfico, 9 filtros de data, `scheduled_after_sla`, `sla_expired_before_schedule`). `os_subjects` (o caso que motivou o lote 6) está corrigido nos 6 endpoints.
- **Existe algum caso "`meta.applied_filters` diz aplicado → SQL não aplicou" remanescente?** Sim - a mesma lista de 13 filtros acima, em `warranty_analytics_for_ai`, agora visível porque o lote 6 deu `meta` à função (achado §14.3). Nos 5 endpoints já migrados (`aggregate_orders`, `search_orders`, `backlog_aging`, `orders_timeseries`, `team_target_performance`), este problema está **zerado** para todos os 29 campos de `AiOrderFilters`, incluindo os compostos.
- **P0 restantes:** 1 (o achado de §14.3, que é a mesma causa raiz de §13.4 - não são 2 P0 novos, é 1 causa com 2 manifestações: função não aplica E agora `meta` também não avisa).
- **P1 restantes:** 1 categoria (cobertura parcial sem aviso em `warranty_analytics_for_ai`, §13.9).
- **P2 restantes:** 2 (`os_types` forçado por design; `search`/`keyword` ausente por design).

Nenhuma correção adicional foi implementada nesta etapa além dos lotes 6 e 7 explicitamente autorizados. Próximo passo (implementar os 13 filtros faltantes em `warranty_analytics_for_ai`, ou fazer a função reconhecer e avisar sobre eles) aguarda autorização explícita, como todos os lotes anteriores.

---

## 15. Lote 8 (último P0) e encerramento da Fase 1 (2026-08-16)

Autorizado pelo usuário para fechar a Fase 1: corrigir só o `meta` de `warranty_analytics_for_ai` (achado de §14.3), sem implementar nenhum filtro novo.

### 15.1 Lote 8 — classificação dos filtros de `warranty_analytics_for_ai`

**Listas confirmadas por leitura de código** (`operations_queries.warranty_analytics`, `operations/queries.py:995-1141`) antes de qualquer alteração:

- **`NOT_SUPPORTED_BY_ENDPOINT` (16 campos + `os_types`):** `text_filters`, `scheduled_after_sla`, `sla_expired_before_schedule`, `has_coordinates`, `near_latitude`, `near_longitude`, `radius_km`, `opened_at`, `closed_at`, `deadline_at`, `scheduled_at`, `assumed_at`, `displacement_started_at`, `execution_started_at`, `finished_at`, `source_updated_at` - confirmado que a função nunca chama `_text_filter_conditions`/`_sla_stage_filter_conditions`/`_geo_filter_conditions`/`_datetime_filter_conditions`. `os_types` incluído à parte: é forçado a `[]` no lado retorno por design (`operations/queries.py:1067`) - o valor enviado nunca tem efeito, mesmo padrão de "aceito, sem efeito", então recebe o mesmo tratamento.
- **`PARTIAL_FILTER_SCOPE` (20 campos):** `contract_types`, `person_types`, `diagnoses`, `departments`, `sectors`, `priorities`, `creators`, `responsibles`, `statuses`, `sla_statuses`, `projects`, `pops`, `customer_logins`, `opened_weekdays`, `closed_weekdays`, mais o composto `custom_window_*` (5 peças) - todos aplicados via `_dimension_conditions(db, user, {**filters, "os_types": []})`, mas nunca no lado origem/denominador (que só recebe os 5 campos de `WARRANTY_ORIGIN_SHARED_FILTERS`).
- **`os_subjects`/`subjects`:** não alterado - só revalidado.

**Implementação:** `_warranty_filter_report()` (`ai/queries.py`) classifica os filtros antes de montar `meta`, sem tocar em nenhuma condição de consulta. Campo `detail: str | None` adicionado a `OperationIgnoredFilterOut`/`IgnoredFilter` (aditivo, revalidado que não quebra nenhum schema já em produção).

**Autocorreção durante o próprio lote:** a primeira versão deste lote tratou as 5 peças de `custom_window_*` peça por peça (`PARTIAL_FILTER_SCOPE` individual), sem checar completude do grupo - reproduzindo dentro de `warranty_analytics_for_ai` o mesmo bug que o lote 7 já tinha corrigido nos outros 5 endpoints. Corrigido antes de declarar a Fase 1 encerrada, reaproveitando `_COMPOSITE_FILTERS["custom_window"]` (mesma tupla do lote 7): grupo completo → `PARTIAL_FILTER_SCOPE`; incompleto → `INCOMPLETE_COMPOSITE_FILTER`, fora de `applied_filters`.

### 15.2 Testes obrigatórios (dado real, `date_from=2026-01-01`, `date_to=2026-08-16`)

| Teste | `numerator` | `applied_filters` | `ignored_filters` | `warnings` |
|---|---|---|---|---|
| Baseline (sem filtro) | 2.750 | - | - | - |
| **A) `regionals` (pleno)** | 682 (≠ baseline) | contém `regionals` | `[]` | `[]` |
| **B) `subjects` (legado)** | 649 | contém `os_subjects` | `[]` | `DEPRECATED_FILTER_ALIAS` |
| **B) `os_subjects` (canônico)** | 649 (= legado) | contém `os_subjects` | `[]` | `[]` |
| **C) `opened_at`+`text_filters` (não suportados)** | 2.750 (= baseline) | **não contém nenhum dos dois** | 2 entradas, `NOT_SUPPORTED_BY_ENDPOINT` | `[]` |
| **`os_types` (forçado)** | 2.750 (= baseline) | não contém `os_types` | 1 entrada, `NOT_SUPPORTED_BY_ENDPOINT` | `[]` |
| **D) `sectors` (escopo parcial)** | 2.445 (≠ baseline) | contém `sectors` | `[]` | `PARTIAL_FILTER_SCOPE` |
| **`custom_window_*` incompleto (2 de 5)** | 2.750 (= baseline) | **não contém as 2 peças** | `[]` | `INCOMPLETE_COMPOSITE_FILTER` |
| **`custom_window_*` completo (5 de 5)** | 2.283 (≠ baseline) | contém as 5 peças | `[]` | 5x `PARTIAL_FILTER_SCOPE` |

Todos os 8 cenários batem exatamente com o esperado. Validado via schema real `AiWarrantyAnalyticsRequest` (incluindo um teste combinado `os_subjects`+`sectors`+`opened_at` na mesma chamada, com os 3 comportamentos corretos simultaneamente). Regressão dos 5 endpoints anteriores confirmada sem quebra. Tool MCP remota `opr_warranty_analytics` confirmada registrada (22 tools, inalterado). `operations_queries.warranty_analytics`/`FILTER_COLUMNS` global não foram tocados.

**Commits:** [dbf832a](https://github.com/paulo-ope/Gamificacao-UNI-OPR/commit/dbf832a) (classificação inicial) + [0ef7e8f](https://github.com/paulo-ope/Gamificacao-UNI-OPR/commit/0ef7e8f) (correção do `custom_window_*` incompleto).

### 15.3 Reauditoria final dos 6 endpoints

1. **Existe algum caso "schema aceita → query ignora → sem aviso"?** **Não.** Os 16+1 campos de `warranty_analytics_for_ai` que a função não aplica agora saem de `applied_filters` e entram em `ignored_filters` com `NOT_SUPPORTED_BY_ENDPOINT`. Os 29 campos dos 5 endpoints já migrados continuam todos aplicados (confirmado em §13.6, sem regressão).
2. **Existe algum caso "`meta.applied_filters` diz aplicado → SQL não aplicou"?** **Não.** Composto incompleto (`near_latitude`/`near_longitude`/`radius_km`, `custom_window_*`) corrigido nos 5 endpoints migrados (lote 7) e em `warranty_analytics_for_ai` (lote 8 + autocorreção de §15.1). Filtro de escopo parcial (`PARTIAL_FILTER_SCOPE`) permanece em `applied_filters` porque **foi de fato aplicado** - a ressalva é só sobre onde, não uma mentira sobre se.
3. **Quantos P0 restam?** **Zero.**
4. **P1/P2 restantes (dívida técnica, não implementados nesta fase):**
   - **P1:** nenhum P0/P1 de "mentira" remanescente - o que resta é escopo de produto, não confiabilidade: os 20 campos de `PARTIAL_FILTER_SCOPE` em `warranty_analytics_for_ai` continuam sem afetar o lado origem/denominador (design documentado, agora com aviso claro).
   - **P2:** `os_types` forçado por design (documentado); `search`/`keyword` ausente do schema em 5 das 6 funções (não é filtro aceito-e-ignorado, o campo nem existe ali); os 16 filtros de `warranty_analytics_for_ai` continuam **não implementados de fato** (só corretamente declarados como não suportados) - se algum dia quiserem funcionar, é trabalho de implementação nova, fora desta fase.
   - Diferenças REST vs IA/MCP (REST nunca ganhou `os_subjects`, `_since` vs `{gte,...}` em login-search) - registradas em §2/§9, não tocadas.
   - `SelectorContractV1` (§8) - não iniciado.

### 15.4 Backlog para fase futura (somente listado, não implementado)

- Implementar de fato os 16 filtros hoje `NOT_SUPPORTED_BY_ENDPOINT` em `warranty_analytics_for_ai` (`text_filters`, geografia, os 9 filtros de data, `scheduled_after_sla`/`sla_expired_before_schedule`) - se o produto decidir que valem a pena.
- Decidir se os 20 campos de `PARTIAL_FILTER_SCOPE` deveriam também afetar o lado origem/denominador (mudança de semântica de negócio, não de confiabilidade - precisa de decisão de produto, não é bug).
- Alinhar REST aos nomes canônicos (`os_subjects`, filtros de data completos em vez de só `_since`) - REST nunca foi migrado, só IA/MCP.
- `SelectorContractV1` (`group_by`/`metric`/`entity`/`granularity`/`date_field` com `Literal` consistente nos 4 canais).
- Migração escalar→lista em `opr_management_cases` (`regional`→`regionals` etc.) - condicionada à prova de segurança/índice já registrada em §4.3/§6.1.
- Qualquer expansão funcional de `warranty_analytics_for_ai` além do que já existe hoje.

Nenhum destes itens foi iniciado. Ficam para outra fase, mediante nova autorização.

---

**FASE 1 DE CONFIABILIDADE: CONCLUÍDA**
