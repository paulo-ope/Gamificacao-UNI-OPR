# API — Agendamento (/api/scheduling)

> Fonte: `backend/app/modules/scheduling/router.py`, `schemas.py` e `models.py`.
> Prefixo montado em `backend/app/main.py` (`app.include_router(scheduling_router, prefix=settings_obj.api_prefix)`,
> com `api_prefix = "/api"` e `router = APIRouter(prefix="/scheduling", ...)`).

## Visão geral

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

## Autenticação e permissões

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

## Endpoints

### Dashboard

**`GET /dashboard`** — `scheduling:read`
KPIs agregados do período: resumo (`summary`), distribuição de TTFA, aging do
backlog, série diária, ranking por operador, ranking por filial e por assunto.
Parâmetros: `date_from`, `date_to` (obrigatórios, máx. 366 dias de intervalo),
`filial_ids[]`, `setor_ids[]`, `assunto_ids[]`, `operator_ids[]`, `technician_ids[]`
(todos opcionais, filtros multi-valor), `count_mode` (`all_events` padrão, ou
`distinct_orders`). Resposta: `SchedulingDashboard` (`settings`, `summary`,
`ttfa_distribution[]`, `backlog_aging[]`, `daily_series[]`, `operators[]`,
`filial_ranking[]`, `assunto_ranking[]`).

### Reagendamento

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

### Backlog

**`GET /backlog`** — `scheduling:read`
Lista de O.S. sem agendamento (fila pendente), limitada por `limit` (padrão 100,
máx. 500). Parâmetros: `date_from`, `date_to`, `filial_ids[]`, `setor_ids[]`,
`assunto_ids[]`. Resposta: `list[SchedulingBacklogItem]` (`ixc_os_id`, `opened_at`,
`age_hours`, `filial`, `setor`, `assunto`, `status`).

**`GET /backlog/breakdown`** — `scheduling:read`
Onde a fila está concentrada — agregado no banco (sem truncamento de `limit`), usado
pelo card "Fila de trabalho". Mesmos parâmetros de filtro (sem `limit`). Resposta:
`SchedulingBacklogBreakdown` (`by_filial[]`, `by_assunto[]`).

### Detalhe / Timeline de O.S.

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

### Filtros Salvos

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

### Configurações / Equipe

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

### Sincronização (jobs / status / saúde)

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

## Exemplos

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
