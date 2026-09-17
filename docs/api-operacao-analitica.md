# API — Operação Analítica (/api/operations)

## Visão geral

O módulo Operação Analítica importa Ordens de Serviço (O.S.) da API do IXC, projeta esses
dados nas tabelas `operations_*` e calcula, em cima dessa projeção, os indicadores de SLA,
backlog, garantia e produtividade que alimentam a tela `/operacao`. Além das O.S., o módulo
também captura e expõe telemetria de rede (status de login/conexão e sinal óptico de ONU),
usada tanto pela tela quanto por consumidores de IA/MCP para investigação de incidentes de
rede.

Todas as rotas deste documento vivem sob o prefixo `/api/operations` (roteador FastAPI
montado com `prefix="/operations"` dentro do app, que já responde em `/api`).

## Autenticação e permissões

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

## Endpoints

### Período e metadados
- `GET /period` — sessão autenticada (`operations:read`). Sem parâmetros. Devolve o intervalo
  permitido de datas (ano operacional corrente, de 1º de janeiro até hoje no fuso
  `America/Porto_Velho`), um período padrão (mês corrente) e o nome do fuso.
- `GET /data-freshness` — sessão autenticada. Devolve o horário da última importação/
  sincronização bem-sucedida por fonte (usado para o indicador de frescor de dado da tela).

### Importação e sincronização com o IXC
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

### Visão Geral / Overview
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

### Aberturas (Openings)
- `GET /openings/analytics` — `operations:view_openings`. Query `granularity`. Analítico de
  aberturas: série temporal, heatmap (dia da semana × hora), ranking, aging e insights.
- `GET /openings/orders` — `operations:view_openings` **e** `operations:view_order_details`.
  Página de O.S. abertas no período, com filtros adicionais de `aging_bucket`, `weekday` e
  `hour`.

### SLA
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

### Garantia
- `GET /warranty` — `operations:view_warranty`. Query `period_basis` (`opened`/`closed`),
  `denominator` (`closed_origins`/`active_origins`/`maintenance_total`/`activation_closed`) e
  `origin_excluded_diagnoses`. Analítico de retorno em garantia: taxa por origem, ranking
  regional e por tipo de origem.

### Calendário
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

### Backlog (em aberto)
- `GET /in-progress` — `operations:view_backlog`. Query `group_by`
  (`regional`/`city`/`os_type`/`subject`/`status`). Quebra do backlog atual (quantidade +
  percentual).
- `GET /in-progress/sla-risk` — `operations:view_backlog`. Backlog quebrado por risco de SLA
  (`breached`/`critical`/`attention`/`on_track`/`no_target`).
- `GET /in-progress/orders` — `operations:view_backlog` + `operations:view_order_details`.
  Página paginada/ordenável do backlog, com filtro opcional `sla_risk`.

### Telemetria de rede (login/ONU)
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

### Ordens de serviço (O.S.)
- `GET /orders` — `operations:view_order_details` + gate de IA (campos/filtros liberados por
  perfil, `date_field`, `fields`, `response_mode=summary|full`). Página de O.S. do período,
  ordenável e paginável, com busca geográfica opcional. Toda chamada é registrada em
  auditoria de acesso a dado (`record_ai_access`).
- `GET /orders/{source_order_id}` — `operations:view_order_details` + gate de IA. Detalhe de
  uma O.S. por id de origem (IXC), com `raw_payload` redigido disponível via `response_mode`/
  `fields`. 404 se não encontrada.

### Filtros e views salvas
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

### Configuração de equipe
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

### Import/export de configuração
- `GET /configuration-json` — `operations:manage_team_models`. Exporta um snapshot portátil
  (sem IDs de banco) de modelos de equipe, membros, e — se o usuário também tiver a permissão
  correspondente — mapeamentos de assunto (`operations:manage_subjects`) e visões salvas
  (`operations:manage_filters`).
- `POST /configuration-json` — `operations:manage_team_models` (subconjuntos de assunto/
  visões exigem também `manage_subjects`/`manage_filters`; visão global no arquivo exige
  `operations:views:create_global`). Faz merge do snapshot pelo nome (não pelo ID): cria ou
  atualiza modelos, membros, mapeamentos de assunto e visões salvas existentes.

## Contrato de filtros e dados

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

## Exemplos

### Visão Geral do mês corrente, filtrando por regional

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

### Backlog em aberto, quebrado por regional

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

### Página de O.S. do período, ordenada por data de abertura

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
