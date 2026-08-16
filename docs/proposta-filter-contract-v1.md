# Proposta: FilterContractV1

**Status:** **Aprovado com ajustes** (revisão do usuário em 2026-08-16) — os 4 ajustes abaixo (§0) já incorporados ao texto. Nenhum código de endpoint foi alterado por este documento; a implementação começa pelo piloto único descrito em §10.
**Data:** 2026-08-16 (v1.1 — incorpora ajustes da revisão)
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
8. **Próximo, autorizado pelo usuário:** nova varredura por todo endpoint que já aceita `AiOrderFilters` (ou seja, já expõe `os_subjects` no schema), procurando especificamente o padrão "schema aceita, função ignora" - não apenas "filtro ainda não suportado". Ainda não iniciada.
9. `warranty_analytics_for_ai`: adiado por decisão do usuário - hoje `subjects`/`os_subjects` não são reconhecidos por nenhum dos dois nomes (`WARRANTY_ORIGIN_SHARED_FILTERS` não inclui nenhum dos dois), então não há divergência entre alias e canônico ali, só ausência simétrica.
10. `text_filters.field="os_subject"`: risco real, mas bloqueado hoje pelo `Literal` fechado de `TextFilterField` (`ai/schemas.py`) - tratado como invariante de segurança, não como refatoração imediata. **Testado em 2026-08-16**: `AiOrderFilters.model_validate({"text_filters": [{"field": "os_subject", ...}]})` levanta `ValidationError` (422 na rota real) - invariante confirmado, nada a corrigir agora.
11. `sla_breakdown`/`sla_hierarchy` (dimensão `"subject"`, não filtro): permanece no futuro `SelectorContractV1` (§8), fora desta rodada.

Este documento não implica nenhum desses passos ter sido concluído além do que está explicitamente marcado como feito acima.
