# API — SGP Suporte (/api/support)

> Fonte única deste documento: `backend/app/modules/support/router.py` (1809 linhas),
> `backend/app/modules/support/schemas.py` e `backend/app/modules/support/models.py`.
> Qualquer divergência entre este texto e o código deve ser resolvida a favor do código.

## Visão geral

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

## Autenticação e permissões

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

## Endpoints

### Sincronização OPA (settings / status / imports)

| Método | Path | Descrição | Permissão |
|---|---|---|---|
| GET | `/opa-sync-settings` | Lê a configuração atual da sincronização automática (habilitado, intervalo em minutos, lookback em dias, backfill de madrugada e seu horário/lookback em meses, intervalo de refresh das dimensões). | `support:sync_opa` |
| PUT | `/opa-sync-settings` | Atualiza qualquer subconjunto dos campos acima (todos opcionais); grava auditoria (`record_audit_log`) do antes/depois. Ao alterar `interval_minutes`, recalcula `next_allowed_at` via `recompute_support_opa_next_allowed_at`. | `support:sync_opa` |
| GET | `/opa-sync-status` | Status operacional: se está `configured` (token/URL do OPA Suite presentes), últimos sucesso/tentativa/erro, run ativo (id/modo/início), se há trava de importação ocupada (`lock_busy`) e se a próxima janela está atrasada (`next_window_delayed`). | `support:sync_opa` |
| POST | `/opa-imports` | Dispara importação **em background** para um período (`date_from`/`date_to`, máx. 32 dias — `validate_opa_period`). Retorna imediatamente com `run_id` e status `pending`; o cliente acompanha via polling em `GET /opa/sync-runs/{run_id}`. Responde `409` se já houver import em andamento (`opa_import_lock_busy`). | `support:sync_opa` |
| GET | `/opa/sync-runs/{run_id}` | Status/progresso de uma run de importação (`pending`/`running`/`completed`/`failed`/`interrupted`), incluindo contagem de páginas processadas e registros criados/atualizados/inalterados/rejeitados. `404` se a run não existir. | `support:sync_opa` |
| POST | `/opa/sync-runs/{run_id}/resume` | Retoma uma run interrompida. Em sucesso, cria notificação in-app para o usuário e devolve o resultado consolidado. Mapeia erros do OPA Suite (`OpaApiError` → 502), interrupção nova (`OpaImportInterrupted` → 502), conflito de estado (`RuntimeError` → 409) e validação (`ValueError` → 422). | `support:sync_opa` |
| GET | `/opa/import-months` | Status (`missing`/`complete`, contagem de atendimentos, última verificação) dos últimos `months` meses-calendário (query `months`, 1–24, padrão 6), do mais antigo pro mais recente. Mesma fonte de dados (`import_months_status`) usada pelo backfill automático de madrugada. | `support:sync_opa` |

### Overrides de atendente

Cadastro que reclassifica manualmente um `attendant_id` do OPA Suite como agente
virtual (`classification="virtual_agent"`) — usado para corrigir casos em que o painel
externo não identifica corretamente bot vs. humano.

| Método | Path | Descrição | Permissão |
|---|---|---|---|
| GET | `/opa/attendant-overrides` | Lista todos os overrides cadastrados. | `support:sync_opa` |
| POST | `/opa/attendant-overrides` | Cria um override (`attendant_id`, `attendant_name` opcional, `classification`, `active`). `422` em erro de validação de negócio ou `attendant_id` duplicado (constraint única). Grava auditoria. Responde `201`. | `support:sync_opa` |
| PATCH | `/opa/attendant-overrides/{override_id}` | Atualiza campos parciais (`exclude_unset`). `422` em erro de validação. Grava auditoria. | `support:sync_opa` |
| DELETE | `/opa/attendant-overrides/{override_id}` | Remove o override. `404` se não encontrado. Grava auditoria. | `support:sync_opa` |

### Atendimentos (overview / timeseries / breakdowns / detail / timeline)

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

### Filtros salvos

| Método | Path | Descrição | Permissão |
|---|---|---|---|
| GET | `/opa/saved-filters` | Lista os filtros visíveis ao usuário: todos com `scope="global"` + os pessoais (`scope="personal"`) dele mesmo. Nunca devolve filtro pessoal de outro usuário. | `support:read` |
| POST | `/opa/saved-filters` | Cria um filtro salvo (`name`, `scope` `personal`\|`global`, `filters` — objeto livre). `scope="global"` exige `support:sync_opa` (checagem inline, `403` caso contrário); filtro global não tem `owner_id` (fica `None`, sobrevive à desativação do autor). Responde `201`. | `support:read` (+ `support:sync_opa` só para `scope="global"`) |
| DELETE | `/opa/saved-filters/{saved_filter_id}` | Remove um filtro salvo. Global exige `support:sync_opa` (`403` caso contrário); pessoal só pode ser removido pelo próprio dono (`404` — não `403` — se não for o dono, para não revelar existência). | `support:read` (+ `support:sync_opa` só para `scope="global"`) |

### Métricas OPA (`/opa-metrics`)

| Método | Path | Descrição | Permissão |
|---|---|---|---|
| GET | `/opa-metrics` | Métricas agregadas do período (`date_from`/`date_to` obrigatórios, `date_basis`): total, fechados, TMA/TMR/TMR-geral médios (com cobertura do TMR geral), avaliação média, e dois agrupamentos top-20 (`by_attendant`, `by_reason`) com as mesmas médias por grupo. Endpoint mais simples/direto que `/opa/overview` — sem comparação contra período anterior. | `support:read` |

`/opa/breakdowns` (agrupamento genérico por dimensão) já está documentado acima, na
seção de Atendimentos, por reaproveitar o mesmo conjunto de filtros dessa família de
rotas.

### TV do SGP Suporte (`/tv/snapshot`)

| Método | Path | Descrição | Permissão |
|---|---|---|---|
| GET | `/tv/snapshot` | Tudo o que a TV de Suporte (`/suporte/tv`) mostra, em uma chamada, sempre sobre **hoje** no fuso `America/Porto_Velho`. Sem parâmetros. Só agregados: nenhum atendimento individual nem nome de cliente. | `support:read` |

Código: `opa_tv_service.py` (regra), `tv_schemas.py` (contrato). Os números reaproveitam
`opa_overview_service` e os serviços IXC — a TV nunca mostra um valor diferente da tela de
Suporte para a mesma métrica. Blocos do payload:

- `kpis` — atendimentos de hoje (e total do dia anterior, **dia inteiro**, sem % de variação
  porque hoje é parcial), encerrados, taxa de encerramento, `open_now`, TMR humano, 1ª
  resposta e avaliação, mais `tmr_all_responses` (TMR geral, **inclui resposta de bot**):
  `current_seconds`, `previous_seconds`, `target_seconds`, `status` (`ok` ≤ meta, `above` > meta,
  `no_data`) e `coverage` (`count`/`total`).
- `open_now` — atendimentos **sem encerramento abertos nas últimas 24 h** (não depende da virada
  do dia; atendimento aberto há mais de 24 h e nunca encerrado não entra).
- `hourly` — atendimentos abertos por hora local hoje contra a média do **mesmo dia da semana**
  nas últimas 4 semanas. Só semanas com dado entram na média (`baseline_weeks_used`); semana sem
  nenhum atendimento é lacuna de importação, não "zero". Horas futuras vêm `today: null`.
- `top_reasons`, `channels`, `bot_human` — mesmas funções da Visão Geral, recortadas em hoje. (`bot_human` continua no payload, mas a TV **não o exibe mais** — o bloco "Bot e humano" foi retirado a pedido da gestão.)
- `attendants` — top 5 por volume do dia, **só atendentes humanos** (o TMR de cada um é o **TMR geral**, que conta a resposta do bot — `average_tmr_seconds`, o mesmo critério do TMR principal; não é o TMR só-humano) (agente virtual fica de fora,
  seja por cadastro manual ativo, seja por `tipo="bot"` da dimensão — mesma regra de
  `resolve_attendant_type`).
- `radar` — **só protocolos operacionais (assunto 90 do IXC, "Registro de Atendimento Operacional") e só de
  hoje.** Código: `ixc_operational_radar.py`. Protocolos financeiros, renovação, plano, instalação etc.
  ficam de fora (antes o radar contava tudo e ~40% era financeiro). Referência ("esperado"): a **mesma
  janela do dia, no mesmo dia da semana, nas últimas 4 semanas**; semana sem nenhum protocolo operacional
  no dia inteiro é lacuna de importação e não entra como zero (`baseline_weeks_used` diz quantas entraram).
  **Horário:** o IXC entrega a data em hora local sem fuso e a importação a grava como se fosse UTC (`created_at` = hora de parede de Porto Velho com etiqueta UTC); o radar lê assim, **sem converter de novo** (converter deslocava tudo 4 h). Partes: `pace` (total de hoje até agora contra o esperado até esta
  hora: `normal`/`attention` ≥ ×1,25/`critical` ≥ ×1,5, com excesso mínimo de 5), `bursts` (últimas 1, 2 e 6 h,
  sempre dentro de hoje; ativa quando passa de `max(esperado + 2 desvios, ×1,35, +2)` e tem ≥ 3 protocolos) e
  `cities_at_risk` (cidades com ≥ 5 protocolos hoje, ≥ ×1,5 e ≥ +3 sobre o esperado; top 3, com
  `today_count`/`expected`). O campo `momentum` (tendência de 3 dias) foi **removido** do radar da TV: comparava
  dias úteis com fim de semana e dava "+193%" sem haver escalada.
- `n1` — protocolos do Suporte Interno N1 de hoje.
- `sync` — `last_success_at` e `consecutive_failures` da sincronização do OPA (nunca a mensagem de
  erro técnica).
- `unavailable` — nomes dos blocos que falharam (ex.: `"radar.bursts"`). **Cada bloco falha
  isolado**: o bloco vem `null` e o resto da TV continua. `null` significa "não sabemos", nunca
  "tudo normal".

**Filtro de departamento da TV.** O snapshot considera só os departamentos configurados
(`support_tv_department_ids`, ids separados por vírgula em `app_settings`; **vazio = todos**). O
filtro vale para todos os blocos do OPA (`kpis`, `open_now`, `hourly`, motivos, canais, bot/humano,
atendentes, comparação com o dia anterior). O radar de incidente e o N1 vêm do IXC e **não** são
afetados. O recorte aplicado volta em `department_filter` (`department_ids`/`department_names`).

| Método | Path | Descrição | Permissão |
|---|---|---|---|
| GET | `/tv/config` | Departamentos escolhidos, lista de departamentos disponíveis (os que já apareceram em atendimentos importados) e a meta do TMR. | `support:sync_opa` |
| PUT | `/tv/config` | Grava os departamentos (`department_ids`; lista vazia = todos). `422` se algum id não existir nos atendimentos importados ou se passar de 50. Grava auditoria (`support_tv_config`). | `support:sync_opa` |

| Método | Path | Descrição | Permissão |
|---|---|---|---|
| GET | `/tv/presence` | Status (presença) dos atendentes da TV. A TV consulta a cada ~10 s, separado do snapshot (30 s). `502` com mensagem amigável se o OPA não responder. | `support:read` |

Código: `opa_presence_service.py`. A presença vem do campo **`online`** de cada usuário em
`GET /api/v1/usuario/` do OPA (confirmado ao vivo em 2026-10-08). Códigos: `on` online, `off`
offline, `pause` em pausa, `au` ausente, `oc` ocupado, `call` em ligação. **O campo `status` do
mesmo registro não é presença**: é só ativo (`A`) / inativo (`I`) do cadastro. Código desconhecido
vira "Outros" e é listado em `unmapped_codes`.

- **Quem conta:** usuário humano ativo que atendeu ao menos uma vez nos últimos 30 dias, nos
  departamentos escolhidos na configuração da TV (qualquer departamento se não houver escolha). O
  id do atendente no atendimento é o `_id` do usuário no OPA.
- `available_percentage` = online ÷ total (mesma conta do painel do OPA: 6 de 48 = 12,5%).
- `agents` / `agents_total` — quem está **em ligação, ocupado, em pausa ou ausente** (online e offline são muitos e não ficam na lista), com `state_label` e `seconds_in_state`. Ordem: ligação, ocupado, pausa, ausente; dentro de cada estado, o mais antigo primeiro. A lista traz no máximo 4 (`AGENT_LIST_LIMIT`); `agents_total` é o total real, para a tela mostrar "+N outros".
- **`seconds_in_state` é uma APROXIMAÇÃO.** O OPA não expõe o instante em que o status mudou; usamos `updatedAt` do usuário (última gravação do registro), que acompanha a troca de presença, mas também se move com qualquer outra alteração do cadastro. Sem data válida vem `null` e a tela omite o tempo (nunca 0 nem um palpite).
- **`ringing_available: false` — a API não informa ligação tocando.** Nenhum campo de conexão
  (`conexoes`, `sip`, `siga_me`) traz isso; a TV declara na tela em vez de sugerir que monitora.
- A lista de usuários do OPA fica em cache por 5 s, para várias TVs/abas não multiplicarem as
  chamadas.

**Mudança da API do OPA (2026-10-08):** o OPA passou a recusar listagens sem filtro
(`400 NO_ARGUMENT_ERROR: At least one valid filter is required`) em usuário, departamento, etiqueta
e cliente — a sincronização de dimensões falhava em silêncio (só um aviso no log). Correção em
`OpaClient.list_collection_union`: junta consultas por um campo de valores conhecidos e deduplica por
`_id` — usuários por `tipo` (user, bot), departamentos por `recebeAtendimento` (true, false) e
clientes por `status` (A, I). **Ainda não corrigido:** etiquetas (só aceitam `nome` exato, sem como
enumerar) e motivos (a rota agora é `/api/v1/motivo` e o token responde `Invalid permissions
profile` — falta liberar a permissão no perfil de API do OPA). O nome do motivo do atendimento
continua vindo do próprio payload do atendimento.

**Meta do TMR geral:** 140 s (02:20). Vem da configuração do sistema
`support_tv_tmr_target_seconds` (valor inteiro em segundos, entre 10 e 3600); ausente ou inválida,
vale o padrão 140. Não há tela de edição — ajuste direto em `app_settings`.

**Histórico:** só dado novo. O TMR geral (`tmr_all_responses_seconds`) só existe para atendimentos
importados depois da coluna; por isso a cobertura aparece ao lado do número.

### Tickets IXC / Analytics IXC

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
| GET | `/ixc/n1/summary` | Suporte Interno N1: protocolos do IXC abertos por colaboradores dos grupos 105 e 117 (`usuarios.id_grupo`), `operational` (motivo 90) e `financial` (motivo 29). Exige `date_from`/`date_to` (`400` se invertidas ou acima de 366 dias). Devolve totais, total do período anterior de mesmo tamanho, série diária (`daily[].day`) e quebra por atendente. Protocolos sem operador (`id_usuarios = 0`) não entram. | `support:read` |
| GET | `/ixc/tickets/filter-options` | Motivos e setores distintos vistos nos atendimentos, para popular dropdowns do drill-down. | `support:read` |
| GET | `/ixc/tickets/taxonomy-mappings` | Lista o de-para motivo → tema → categoria (`support_ixc_taxonomy_mappings`). Tabela nasce vazia; popular é decisão de negócio separada. | `support:read` |
| GET | `/ixc/tickets` | Lista os tickets individuais (protocolo, status, motivo) de um recorte regional/cidade/bairro/motivo — nó final do drill-down. Enriquece cada item com taxonomia (tema/categoria, cache por `subject_id` distinto na página) e `risk_score`/`subtema_inferido` calculados a partir do texto do relato (`ixc_ticket_text_signal.resolve_ticket_risk`). `limit` 1–200, `offset`. | `support:read` |
| GET | `/ixc/analytics/context` | Resumo executivo de um escopo qualquer (regional/cidade/bairro + motivo/setor) no modelo de período livre — contagem, contratos, desvio, `severity`/`severity_basis` (`historical`\|`peers`\|`insufficient_data` — correção de 2026-09-17: regional/cidade sem amostra histórica suficiente cai pra comparação com PARES antes de virar "sem dado", nunca classifica ausência de amostra como normal), `peers_deviation_pct`/`peers_avg`/`expected`, alcance (clientes únicos/recorrentes), `drivers` (lista completa, não só o principal) e `geographic_concentration` (principal cidade/bairro do escopo, com `share_pct` sobre o total). Traz `context_key` — identificador determinístico do agrupamento (ver rotas abaixo). `regional` obrigatório para filtrar por `city`; `city` obrigatório para `neighborhood` (`400` caso contrário). | `support:read` |
| GET | `/ixc/analytics/context/{context_key}` | Decodifica `context_key` e devolve o MESMO contexto que o gerou, sem reconstruir os filtros na mão. `400` se a chave for malformada ou de versão não suportada. | `support:read` |
| GET | `/ixc/analytics/context/{context_key}/tickets` | Protocolos EXATOS que compõem o agrupamento de `context_key` — fecha o fluxo "sinal → context_key → drill → tickets", mesmo enriquecimento (tema/`risk_score`) de `/ixc/tickets`. `limit` 1–200, `offset`. | `support:read` |
| GET | `/ixc/analytics/priorities` | Ranking do PRÓXIMO NÍVEL relevante, com `dimension` (`regional`\|`city`\|`neighborhood`\|`subject`) escolhida explicitamente. Cada item traz `severity_basis` (mesmo fallback de pares de `/analytics/context`) e `context_key` (o agrupamento que resultaria de drillar naquele item). `400` em `ValueError` de domínio. | `support:read` |
| GET | `/ixc/analytics/drivers` | Decomposição do excesso por motivo (`current - esperado`, esperado = mesma janela no período anterior de tamanho igual) com `contribution_pct`. Mesmas regras de dependência hierárquica de `regional`/`city`/`neighborhood` que `/analytics/context`. | `support:read` |
| GET | `/ixc/analytics/bursts` | Fase 4 (`BURST_V1`): compara observado nas últimas 1h/2h/6h contra baseline pré-computado por hora-do-dia/dia-da-semana. `basis="none"` quando ainda não há baseline calculado para o escopo. Escopo `regional` (se informado) ou `global`. | `support:read` |
| GET | `/ixc/analytics/momentum` | Fase 4 (`MOMENTUM_V1`): tendência recente (últimos dias) — "piorando/melhorando/estável", complementar ao desvio pontual de `/tickets/overview` e `/analytics/context` (que respondem "fora da curva hoje", não tendência). | `support:read` |
| GET | `/ixc/analytics/os-conversion` | Fase 6 (`OS_CONVERSION_V1`): quantos atendimentos do recorte viraram O.S. dentro de 2h/6h/24h/48h, via vínculo `OperationOrder.ticket_id == SupportIxcTicket.source_id`. Mede se o indicador antecipado de fato antecipa ação real — não substitui a O.S. como fonte de verdade. | `support:read` |

## Contrato de dados

### Fuso horário e convenção de datas

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

### TMA e TMR

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

### Comparação contra período anterior

`/opa/overview` e `/opa/breakdowns` comparam cada métrica contra o período
**imediatamente anterior de mesma duração** (`OpaAttendanceFilters.previous_period()`,
`opa_filters.py:91-104`) — não contra o mesmo período do mês/ano passado. Todos os
demais filtros ativos (motivo, canal, atendente etc.) são preservados no cálculo do
período anterior, via `dataclasses.replace`, para que o "antes" e o "depois" sejam
sempre o mesmo universo de filtros.

### Multi-seleção via querystring

Parâmetros que aceitam múltiplos valores (ex.: `status`, `channel`, `attendant_id`,
`department_id`, `reason_id`, `customer_id`, `tag_id` nos endpoints OPA; `subject_id`,
`sector_id` nos endpoints IXC) recebem uma string única com valores separados por
vírgula (ex.: `status=aberto,pendente`), nunca `?status=a&status=b` repetido.

### Tickets IXC como indicador antecipado

Os KPIs/analytics de `/ixc/tickets/*` e `/ixc/analytics/*` **não substituem** a O.S.
como fonte de verdade operacional — são um sinal antecipado (o atendimento/ticket
chega antes da O.S. ser aberta). `/ixc/analytics/os-conversion` existe justamente para
medir se esse indicador de fato antecipa ação real, comparando o lead time entre o
ticket e a O.S. gerada a partir dele.

## Exemplos

### 1. Visão geral de atendimentos OPA de um dia, filtrando por canal

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

### 2. Drill-down de tickets IXC (regional → cidade)

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

### 3. Disparo de importação manual de um período do OPA Suite, com polling

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
