# Status do Projeto

Log vivo de curto prazo. Antes de começar qualquer tarefa, leia esta seção inteira —
ela existe pra qualquer IA ou pessoa entrar no meio do trabalho sem precisar
reconstruir o contexto lendo o histórico de commits inteiro.

Regra de manutenção: ao final de uma sessão de trabalho relevante, atualize este
arquivo (peça confirmação ao usuário antes de gravar, como qualquer outra alteração).
Mantenha só o estado atual — não vire changelog. Histórico detalhado já existe no
`git log`; aqui entra só o que não está óbvio no diff.

---

## Última atualização

**2026-08-27** — branch `claude/suporte-sync-backfill-madrugada` (auditoria de
performance do módulo OPA Suite; ver PRs abertas abaixo pras outras frentes)

## O que foi feito recentemente

- **Auditoria de performance do módulo SGP Suporte/OPA Suite — maior gargalo do
  backend inteiro encontrado e corrigido (branch
  `claude/suporte-sync-backfill-madrugada`, aguardando merge)**: pedido do
  usuário "preciso validar o backend do módulo opa suite... ser o mais rápido
  possível sem perder a confiabilidade de dados", em cima da auditoria geral já
  feita. **Achado real, medido ao vivo direto na API do OPA Suite (não
  simulado)**: `_sync_opa_dimensions` buscava o cadastro de USUÁRIOS/MOTIVOS/
  DEPARTAMENTOS/ETIQUETAS/CLIENTES do OPA Suite em TODA sincronização — a
  periódica (a cada ~20 min), todo import manual, todo backfill de mês, todo
  resume. Só o cadastro de clientes (177.870 registros na base real) media
  **mais de 100 segundos por ciclo**, e depois disso `_sync_dimension_records`
  fazia **um SELECT por registro** pra decidir criar vs. atualizar — mais de
  100 mil consultas individuais na MESMA sincronização. Isso sozinho era maior
  que qualquer lentidão já medida nas telas de leitura do módulo.
  Corrigido em 3 frentes, validadas ao vivo (100s+ → **2,73s**, ~35-40x):
  (1) throttle configurável (padrão 24h, exposto na tela de sincronização como
  "Atualizar cadastros") — entre uma janela e outra usa só o cache já no
  banco, zero chamada à API; nomes de cliente/usuário/motivo mudam raramente
  comparado à frequência de sync de atendimentos, uma defasagem de até 24h no
  NOME exibido não afeta nenhum número financeiro/operacional; (2) upsert em
  lote em `_sync_dimension_records` (carrega os existentes de uma vez, em
  lotes de 2000, em vez de um SELECT por registro); (3) `_load_dimension_map`
  selecionava a entidade ORM inteira (hidratando `payload_json`, que ninguém
  usa ali) só pra ler 2 colunas — sozinho foi de 5,6s pra 0,9s, medido ao vivo,
  e essa função roda toda vez mesmo quando o throttle pula a busca na API.
  Testes: 6 novos (`test_opa_dimensions_throttle.py`) + 741 passed na suíte
  completa (as 13 falhas restantes são pré-existentes e alheias, módulo
  `test_ai_*`).
  **Segunda rodada — otimização das consultas de LEITURA de `/opa/overview`
  (mesma branch, commit `d963b17`)**: dos achados do agente investigador (com
  evidência de `EXPLAIN ANALYZE` real — não é falta de índice, os índices já
  existem e funcionam), implementados os 3 mais seguros: (1)
  `overview_metrics` — os dois `COUNT(DISTINCT attendant_id)`/`COUNT(DISTINCT
  department_id)` no mesmo `SELECT` forçavam `Sort Method: external merge,
  Disk` (~155ms de ~176ms da query) porque dois `COUNT(DISTINCT)` de colunas
  diferentes não cabem no mesmo `HashAggregate` — viraram 2 subconsultas
  escalares resolvidas em memória (~110ms); (2) `customer_metrics` — trazia
  TODAS as linhas agrupadas por cliente pra Python (25.492 linhas medidas ao
  vivo) só pra contar/somar/ordenar — agora só o top 10 cruza a fronteira
  banco↔aplicação, o resto vira 2 agregados escalares em SQL; (3)
  `average_first_response_seconds` — trazia TODO par de datas pra Python
  (23.819 linhas medidas ao vivo) por causa de uma limitação conhecida do
  SQLite dos testes — resolvido com uma expressão SQL por dialeto (mesmo
  padrão já usado em `_local_day_expression`), **achado durante a correção**:
  `julianday()` do SQLite introduzia ruído de ponto-flutuante
  (599.9999843... em vez de 600.0) por causa da parte inteira enorme (dias
  desde 4714 a.C.) diluir a precisão do `double` — trocado por
  `strftime('%s', ...)` (segundos inteiros exatos).
  **Validado número por número contra a base real** (118 mil atendimentos,
  resultado novo comparado lado a lado com o antigo): tudo idêntico, só a
  ordem de exibição entre 2 clientes empatados em 27 atendimentos mudou (nunca
  foi garantida em nenhuma das duas versões). `GET /support/opa/overview` em
  regime estável: ~930ms → **~480-570ms** (~15-25%, menor que o fix de
  sincronização porque deliberadamente não combinei as 8 consultas
  separadas). Testes: suíte completa do módulo (179 opa/support) + 741 passed
  na suíte inteira, sem regressão.
  **Descartado por decisão explícita do usuário** (não é "ainda não
  implementado" — é "não vai ser", ver "Frentes em andamento" pro raciocínio
  completo): combinar as 8-9 consultas separadas de `expanded_overview` num
  recorte físico só. Só é possível com recurso Postgres-only (tabela
  temporária ou `GROUPING SETS`, este último confirmado ausente no SQLite
  3.46.1 usado pelos testes) — significaria código sem cobertura de teste
  automatizado dali pra frente, pelo ganho estimado (~480ms → ~300-350ms) não
  compensar. Ainda em aberto (motivo diferente, não bloqueado por isso):
  verificar se `GET /support/opa-metrics` duplica o núcleo do que
  `/opa/overview` já calcula.

- **Auditoria de performance do backend — P0 e P1 corrigidos, P2 avaliado e adiado**:
  pedido do usuário "preciso de uma auditoria na velocidade do backend, como deixar
  mais rápido sem perder confiança nos dados". Relatório completo publicado como
  artifact (achados + evidência medida ao vivo, não só leitura de código).
  **P0 (branch `claude/auditoria-performance-p0`, aguardando merge)**:
  - **Achado real, medido ao vivo**: `GET /dashboard/summary` levava **5-7 segundos**
    em quase todo carregamento (reprocessando 10.685 O.S. em Python por requisição).
    Causa raiz: `_refresh_stale_draft_previews` (calculation_runs.py) corrige
    `final_points`/`estimated_payment` de OUTROS rascunhos quando um débito de
    garantia compartilhado é consumido por um pagamento, mas nunca tocava em
    `cost_by_regional`/`cost_by_group`/`cost_by_subject`/`cost_by_collaborator`
    desses rascunhos — o detalhamento ficava congelado com o valor de ANTES do
    débito ser consumido. A checagem de consistência do dashboard detectava
    corretamente a divergência (medida: R$ 15.073,50 em cache contra R$ 11.967,06
    reconciliado, run #1936) e recusava servir o cache, forçando recálculo completo
    a cada carregamento. Corrigido invalidando `dashboard_cache_version` no
    rascunho afetado em vez de redistribuir o delta pelos detalhamentos (arriscaria
    uma versão mais sutil do mesmo bug) — a checagem de consistência continua
    intacta como rede de segurança.
  - `ANALYZE` nas 6 tabelas maiores do backend (nunca tinham sido analisadas pelo
    planejador de consultas do Postgres, mesmo com autovacuum ligado) — ação em
    banco, não versionável em código, **precisa rodar de novo na VM após o deploy**.
  - Script novo `scripts/enable_draft_retention.py` liga a poda de rascunhos
    superados (já implementada e testada na auditoria financeira de agosto, nunca
    tinha sido ligada) — confirmado por dry-run: 1.085 dos 1.100 rascunhos hoje
    seriam removidos, mantendo os 3 mais recentes por período e tudo que o ledger
    financeiro ainda referencia. Ligado no ambiente local; **precisa rodar
    `python -m scripts.enable_draft_retention` na VM após o deploy** (confirmado
    com o usuário antes de ligar - ação destrutiva, ainda que bem protegida).
  - Testes: 2 novos (`test_stale_draft_cache_invalidation.py`) + 78 passed na
    varredura ampla da Gamificação.
  **P1 (branch `claude/auditoria-performance-p1`, aguardando merge)**:
  - `POST /imports/ixc-backfill` rodava inline na requisição HTTP (busca paginada de
    um mês inteiro da API do IXC, sem job/status) — virou background job
    (`BackgroundTasks.add_task` + `ixc_import_lock_busy` pra 409 imediato se já
    tiver outra importação do IXC rodando), resultado consultável em
    `GET /imports/runs` (já existia). Sem consumidor no frontend, sem breaking
    change de UI.
  - N+1 real em `rules_engine._run_collective_outage_rule` (monitor de fundo): 2
    consultas por cluster geográfico detectado, viraram 1 consulta batendo todos os
    logins de todos os clusters de uma vez.
  - Query duplicada em `cockpit.build_cockpit_payload`: alertas ativos consultados
    2x (uma pra `active_alerts`, outra pra `active_incidents`, diferindo só por um
    filtro de `kind` em Python) — agora 1 consulta só.
  - Pool de conexões do SQLAlchemy configurável por variável de ambiente
    (`db_pool_size`/`db_max_overflow`/etc.) em vez do padrão da biblioteca (15
    conexões pro processo inteiro) — o backend roda com um único worker uvicorn,
    então esse pool é o orçamento de conexão do processo todo.
  - Testes: 2 novos (`test_ixc_backfill_background.py`) + 728 passed na suíte
    completa (as 13 falhas restantes são pré-existentes e alheias, módulo `test_ai_*`).
  **Adiado deliberadamente** (avaliado, não esquecido): `POST /operations/imports`
  (já limitado a 1 dia por chamada, converter exigiria reescrever o loop do
  frontend) e `POST /operations/responsible-directory/sync` (ação administrativa
  pontual, frontend espera resposta síncrona hoje) seguem síncronos. Cache em
  `GET /operations/overview` foi avaliado e adiado de propósito: o endpoint escopa
  o resultado pelo usuário (gestor regional só vê a própria regional) e cachear sem
  incluir esse escopo no risco de vazar dado de uma regional pra gestor de outra —
  precisa de desenho cuidadoso antes de implementar.

- **Menu lateral único (sidebar + visão geral) — construído, depois revertido a
  pedido do usuário antes do deploy**: Fase 1 da modernização de navegação (shell
  único substituindo o header duplicado por módulo, customização fixar/reordenar
  estendendo `WorkspaceModuleVisibility`, tela de Visão Geral agregando summaries
  já existentes de cada módulo). Código funcional e testado, mas o usuário pediu
  pra não ir pra VM ainda nesta rodada de deploy — revertido via commit dedicado
  (`revert: menu lateral unico`, branch `claude/revert-menu-lateral`, já mergeada).
  **Achado real durante o revert**: o commit original tinha, por acidente,
  incorporado partes do trabalho do SGP Suporte (tipos/chamadas de API como
  `SupportOpaTimeseries`, `tmr_all_responses_coverage`) em `frontend/lib/types.ts`
  e `api.ts` — arquivos editados enquanto ainda havia mudanças não commitadas de
  outra frente ali dentro. Um revert automático (`git revert`) teria quebrado os
  gráficos/filtros salvos do Suporte junto — corrigido manualmente, mantendo todas
  as adições do Suporte e revertendo só o que era genuinamente do menu. Pra
  reativar o menu no futuro: reverter o commit de revert (o código já existe no
  histórico, só está fora do que roda em produção).

- **SGP Suporte — import de período em background, backfill automático de meses e
  fix de campo numérico (branch `claude/suporte-sync-backfill-madrugada`,
  aguardando merge)**: pedido do usuário "preciso melhorar a sincronização... ao
  apagar números fica um 0 sempre... preciso poder agendar essas buscas pra
  madrugada". **Bug do campo "0"**: `Number(event.target.value)` a cada tecla
  fazia o campo de intervalo/dias de histórico mostrar "0" ao apagar (`Number("")`
  é 0, não `NaN`) — corrigido com rascunho de texto local por campo, só
  convertendo/gravando no blur. **Import manual virou job em background**
  (`POST /opa-imports` blocava a requisição HTTP num mês inteiro, risco de
  timeout) — mesmo padrão depois reaproveitado no P1 da auditoria de performance
  pro backfill do IXC. **Backfill automático de madrugada**: tabela nova
  `support_opa_import_months` rastreia "este mês já foi totalmente importado"
  (não existia nenhum jeito de saber isso antes, só um MIN/MAX global da base
  inteira); novo scheduler roda 1x por dia a partir de uma hora configurável
  (padrão 3h) e importa os últimos N meses (padrão 3) ainda não completos; painel
  novo na tela mostra o status de cada mês recente com botão de reimportação
  manual. Testes: 9 novos (`test_opa_backfill.py`) + 189 passed na varredura ampla
  (opa/support/workspace/scheduling), sem regressão.

- **Reagendamentos por técnico — corrigido duas vezes na mesma rodada (já
  mergeado)**: primeiro achado, "reagendamentos por técnico" contava qualquer O.S.
  atribuída ao técnico que foi reagendada por QUALQUER pessoa, não só pelo próprio
  técnico — corrigido pra contar só eventos cujo `technician_id` é o próprio
  técnico. Segundo achado, ao validar: `SchedulingEvent.technician_id` às vezes
  carrega o funcionário associado à O.S., não necessariamente um técnico de campo
  de verdade — gente do backoffice/agendamento (ex.: um operador de equipe)
  aparecia na lista como se fosse técnico. Restrito a colaboradores cadastrados no
  módulo de Gestão com um modelo de equipe de campo de verdade (TECNICO 12/36H,
  FAZ TUDO etc.) via `ManagementOperationalMember`.

- **Gráficos, drill-down e filtros novos na `/suporte` (mergeado)**:
  rodada pedida como "preciso ter gráficos, drill-down, melhorar os filtros".
  **Filtros novos** (aditivos, em `opa_filters.py`): `tag_id` (etiqueta,
  multivalorada com semântica OU), `rating_min`/`rating_max` (faixa de nota),
  `bot_human` (6 recortes) e `customer_id`. Todos passam por um
  `Depends(OpaExtraFilters)` único em vez de repetidos em cada rota — são 5
  endpoints lendo o mesmo recorte, e um parâmetro esquecido em um deles
  produziria a tela mostrando números de universos diferentes lado a lado sem
  erro nenhum. `previous_period()` passou a usar `dataclasses.replace` pelo
  mesmo motivo (a cópia campo a campo deixava filtro novo vazar do
  comparativo).
  **Etiqueta exigiu projeção**: era a única dimensão que o OPA só entrega
  dentro do JSON (`raw_payload.tags[].id_tag`). Filtrar direto no JSON foi
  medido em **411 ms por consulta** — inviável numa tela que dispara ~8
  agregações por carga. Migration `0078` cria `tag_ids_text` (string
  delimitada, separador nas duas pontas pra `LIKE` não casar id que contém
  outro) e **faz backfill local** a partir do próprio `raw_payload` da mesma
  linha — sem chamar a API do OPA, sem alterar métrica nenhuma. Resultado:
  mesma contagem (1.698) em **98 ms**, 4,2x mais rápido; 0 nulos, 31.195 com
  etiqueta.
  **Gráficos** (ECharts, já era dependência do projeto — zero lib nova):
  volume por dia (barras empilhadas encerrado/aberto), tempos por dia (TMA,
  TMR humano e TMR geral — os três sempre juntos, dia sem cálculo vira buraco
  na linha e nunca zero), ranking horizontal de atendentes e rosca bot vs.
  humano com o denominador no centro. Endpoint novo `/opa/timeseries` usa os
  MESMOS filtros dos cards — o gráfico é decomposição, não cálculo paralelo
  (há teste travando que a soma da série bate com o total da Visão Geral).
  Agrupa por dia LOCAL (UTC-4 fixo), com teste provando que 02:00 UTC do dia 2
  cai no dia 1.
  **Drill-down**: clicar num dia ou num atendente abre um drawer com o recorte
  daquele clique aplicado POR CIMA dos filtros globais, nunca no lugar deles.
  Validado ao vivo: drill-down do dia 25/08 devolveu 3.027, exatamente o valor
  daquele dia no gráfico, preservando o `bot_human=with_bot` da tela.
  **Filtros salvos** (migration `0079`, tabela nova): três escopos — local
  (localStorage, rascunho do navegador), pessoal (backend, sincroniza entre
  dispositivos) e global (backend, visível pra toda a operação). Publicar ou
  remover global exige `support:sync_opa`; filtro global fica com
  `owner_id=NULL` pra não sumir junto com o autor (a FK é CASCADE). 6 testes
  cobrindo as duas barreiras de permissão e o não-vazamento entre usuários.
  **Bug encontrado na validação ao vivo e corrigido**: as funções de
  ida e volta da URL tinham listas de chaves separadas, então `tag_id` era
  escrito mas não lido — o recorte não sobrevivia a reload nem a link
  compartilhado. Unificado numa lista só (`URL_FILTER_KEYS`), com validação do
  valor de `bot_human` pra link torto não virar 422.
  **Validado ao vivo**: 11.662 (com bot) + 2.001 (sem bot) + 101 (não
  classificado) = 13.764 = total sem filtro — prova que os recortes são
  exclusivos e que "não classificado" não vira "sem bot". Filtro de etiqueta
  pela URL devolveu 442 com badge "Etiqueta: Atendimento Suporte" (rótulo
  resolvido da dimensão, não o hash). Console sem erro novo, mobile 375px sem
  overflow.
  **Limitação da validação**: não foi possível confirmar visualmente que os
  gráficos PINTAM — o navegador headless desta sessão não compõe frames de
  canvas. As instâncias ECharts montam com dimensão correta (589x240), e a
  página `/operacao` (gráficos pré-existentes, em produção) apresenta
  exatamente o mesmo comportamento no mesmo painel, o que indica limitação do
  ambiente e não do código. **Vale uma olhada num navegador real.**
  Backend **720 passed / 13 failed** (as mesmas 13 falhas pré-existentes do
  módulo AI). Frontend: typecheck, 35 testes e build limpos.
  Arquivos: `opa_filters.py`, `models.py`, `opa_ingestion.py`,
  `opa_overview_service.py`, `router.py`, `schemas.py`, migrations `0078`/`0079`,
  `test_opa_attendance_table.py`, `test_opa_saved_filters.py` (novo),
  `types.ts`, `api.ts`, `support-chart-options.ts` (novo), `opa-charts.tsx`
  (novo), `opa-drilldown.tsx` (novo), `opa-saved-filters.tsx` (novo),
  `opa-module-components.tsx`, `page.tsx`.
  **Mergeado** (parte do commit `f17e4c0`, PR #15).

- **D1 corrigido (portal) + investigação do C3 + decisão dos créditos registrada**:
  seção 10.3 de
  [auditoria-gamificacao-financeira-2026-08-26.md](auditoria-gamificacao-financeira-2026-08-26.md).
  **Portal**: `_portal_run` passa a usar `pick_run_by_status_priority`, com trava
  extra — sem mês/ano, o **período** é resolvido antes do status (período mais recente
  com apuração não cancelada), senão a prioridade global por `paid` trocaria o padrão
  do portal de 08/2026 (mês corrente) para 07/2026 (pago) e esconderia o mês em
  andamento; seria mudança de comportamento não pedida. **O defeito era pior do que a
  auditoria registrou**: em 07/2026 o portal mostrava o run **#1646, CANCELADO**
  (R$ 18.453,47), não um rascunho — agora mostra o #1601 pago (R$ 18.271,68); 08/2026
  e o padrão do portal ficaram inalterados. 8 testes em
  `test_portal_run_selection.py` (3 falhavam antes).
  **C3 investigado**: o identificador de ponto de serviço **existe e o importador já o
  lê** — `customer_login` vem de `radusuarios.login` via `id_login`, e `contract_id`
  vem de `login.id_contrato`, ou seja o próprio IXC modela login como ponto de serviço
  dentro do contrato. `fetch_logins_by_ids` traz o registro completo de `radusuarios`
  mas o importador descarta `id_login`, `ativo`, endereço e coordenadas. Logo "opção
  B (login)" e "opção D (id de instalação)" são a mesma coisa hoje. **A pergunta que
  decide não é respondível com a base local**: `radusuarios.id` é estável quando o
  login é renomeado? A API do IXC está inalcançável ("Name or service not known").
  Testei um discriminador alternativo (dois logins do mesmo contrato são a mesma
  instalação se as janelas de atividade não se sobrepõem): 362 coexistem/pontos
  distintos, 966 não coexistem/migração; acerta Teatro-Câmara (contrato 12371), as
  migrações `.WMT`→`_UNI` e as câmeras (37907), **erra** quando cada login tem só 1
  O.S. (contrato 10323). Recomendação: persistir `id_login` (aditivo, exige migration)
  e confirmar a estabilidade no IXC antes de mexer na regra; **manter `contract`** por
  enquanto, porque `login` perderia 26% das detecções legítimas.
  **Decisão registrada (créditos)**: pagar como estão, sem recriar débitos — a
  ferramenta só passou a operar em julho/2026, cobrar garantia de junho não faz
  sentido. **Coincide com o `WARRANTY_DEBIT_TOOL_CUTOFF = (2026, 7)` que o código já
  tem**: 1.293 dos 1.347 débitos compensados (96%) têm origem em 06/2026, ou seja
  nunca deveriam ter sido criados. **Pendência que a decisão gera**: sobraram **226
  débitos pendentes com origem em 06/2026 (−R$ 787,50)** que serão cobrados no próximo
  fechamento pela mesma lógica legada e **precisam ser estornados**; os 189 pendentes
  com origem em 07/2026 (−R$ 629,16) são legítimos e devem ser cobrados.
  **Correção de auditoria**: o enquadramento do C3 no relatório estava errado — não
  são "1.757 pares de clientes diferentes"; **1.756 dos 1.757 têm o mesmo titular**.
  Corrigido no documento com aviso destacado.
  Suíte completa: **704 passed, 13 failed** (as mesmas 13 pré-existentes de
  `test_ai_*`). Sem commit, sem push, sem migration aplicada, sem dado alterado.
- **Auditoria pós-implementação das Etapas 0–4 (só documentação, nenhum código
  alterado)**: seção 10.2 de
  [auditoria-gamificacao-financeira-2026-08-26.md](auditoria-gamificacao-financeira-2026-08-26.md).
  Os 10 itens verificados estão implementados como descrito. **4 divergências
  encontradas**: (D1) **A9 estava no plano aprovado da Etapa 2 e não foi entregue** —
  `portal_dashboard._portal_run` continua pegando o run mais recente sem filtrar
  status, então o colaborador vê o último rascunho automático enquanto a tela de
  fechamento e o extrato PDF mostram o pago; nem a seção 10.1 nem esta lista
  registravam a ausência; (D2) `/dashboard/filtered-breakdowns` não recebeu a guarda
  de consistência — risco latente, não alcançável pela tela atual; (D3)
  `gross_final_points`/`gross_estimated_payment` continuam vivendo só no cache JSON,
  única grandeza financeira que ainda depende dele; (D4) as duas guardas de admin do
  frontend usam critérios diferentes (`role === "admin"` vs `is_admin_user`), falha
  para o lado seguro mas é incoerente. A estimativa de performance da A2 foi
  substituída por medição real: **223.811 → 25.737 linhas materializadas**, SQL de
  56,1 ms → 26,4 ms (8,7×) — com a ressalva de que 25.737 objetos ORM dentro de uma
  transação de pagamento ainda é muito, e a correção decisiva segue sendo a retenção
  de rascunhos, desligada. Confirmado somente leitura: contagens de
  runs/scores/ledger/O.S. idênticas às da auditoria original, `result_summary` do
  #1601 intocado em R$ 18.191,18 com a API respondendo R$ 18.271,68 consistente nos
  quatro lugares, 0 lançamentos aplicados a 08/2026, último `audit_log` anterior à
  sessão, 0 dos 10 índices da migration no banco, `alembic current` = `20260826_0076`.
  Testes: Gamificação **119 passed**; suíte completa **696 passed, 13 failed** — as 13
  são pré-existentes e provadamente alheias (nenhum arquivo alterado está na cadeia de
  imports delas). Frontend `typecheck`, `test` (35 passed) e `build` limpos; **não
  existe script `lint`** no `package.json`.
- **Correção das Etapas 0–4 da auditoria da Gamificação (sem commit, sem push, sem
  migration aplicada, sem alteração de dado real)**: detalhe completo na seção 10.1
  de [auditoria-gamificacao-financeira-2026-08-26.md](auditoria-gamificacao-financeira-2026-08-26.md).
  **Etapa 0 (conciliação)** — novo `backend/scripts/audit_point_balance_reconciliation.py`
  (somente leitura) classifica os 1.781 lançamentos pendentes. Resultado:
  **841 créditos (+8.186 pts / R$ 2.865,10) SEM CONTRAPARTIDA** — o débito que eles
  compensam já foi aplicado e não existe re-lançamento vivo, ou seja, a pessoa
  recebe o crédito e nunca mais é cobrada por aquela garantia; 489 compensados;
  17 compensando débito nunca cobrado; 415 débitos a cobrar. Saída em
  `outputs/conciliacao-saldo-pontos-2026-08-26.csv`. **Ainda pendente de decisão
  sua** — o próximo fechamento marcado como pago aplica +R$ 3.218,81 para 96 pessoas.
  Achado colateral: o texto dos próprios lançamentos afirma que a folha de 07/2026
  saiu de uma planilha extraída **antes** da correção de saldo de 2026-08-05, o que
  é evidência (não confirmação) de qual valor do #1601 foi realmente pago.
  **Etapa 1 (testes)** — 6 arquivos, 28 testes; 13 falhavam contra o código antigo.
  **Etapa 2 (fonte única)** — `serialize_run` lê sempre a linha `collaborator_scores`
  nos campos financeiros (cache só para `regional` e contadores); novos
  `result_summary_with_totals_from_scores` (leitura, não muta), 
  `recompute_run_totals_from_scores`, `collaborator_financial_context` e
  `refresh_run_breakdowns` (recalcula `cost_by_*` no pagamento em vez de deixá-los
  congelados no rascunho); `flag_modified` saiu de dentro do `if adjusted`;
  `apply_leadership_bonus_to_cost_by_regional` virou idempotente via
  `leadership_amount` por linha. **Efeito medido no #1601 (leitura pura): a API
  passou a responder R$ 18.271,68 nos quatro lugares** (tabela, resumo, card e soma
  das linhas), com o `result_summary` gravado intocado em R$ 18.191,18 — a
  reconciliação acontece na leitura, sem `UPDATE` em fechamento pago.
  **Etapa 3 (concorrência e permissão)** — `SELECT ... FOR UPDATE` no fechamento antes
  de ler o status; consumo do ledger virou `UPDATE ... WHERE status='pending'` com
  checagem de `rowcount`; `_refresh_stale_draft_previews` carrega ~26 mil linhas em
  vez de ~224 mil; `POST /leadership/bonus-results/calculate` exige admin e recusa
  fechamento pago/cancelado; extrato PDF saiu de `audit:read` (só admin ou o próprio
  colaborador). **Etapa 4 (escala)** — migration `20260826_0077` com 10 índices
  (`CREATE INDEX CONCURRENTLY`) **criada e NÃO aplicada**, e `prune_superseded_drafts`
  **desligada por padrão** (`gamification_draft_retention_enabled`), preservando
  não-rascunhos, os N mais recentes e os 9 rascunhos referenciados pelo ledger.
  **Consumidores de API avaliados**: os 4 pontos de `page.tsx` que recalculavam o
  bônus como efeito colateral de salvar liderança passariam a falhar com o fechamento
  pago aberto — viraram `refreshLeadershipBonusForCurrentRun()`, que só chama quando
  faz sentido; e os botões do extrato PDF agora só aparecem para quem pode emitir.
  **Validação**: backend **696 passed, 13 failed** (as mesmas 13 pré-existentes de
  `test_ai_*`, outro módulo); frontend `typecheck`, `test` (35 passed) e `build` limpos.
  **NÃO executado**: validação visual real no navegador (exigiria `docker compose build
  frontend` + `up -d`, que é deploy); migration não aplicada (`alembic current` =
  `20260826_0076`, os 10 índices não existem no banco, e o arquivo foi removido do
  container em execução pra que um restart não a aplicasse sozinho pelo entrypoint);
  `prune_superseded_drafts` nunca rodada contra a base real; a API em execução ainda
  serve o código antigo (os arquivos foram copiados pro container só pra rodar a suíte).
  **Próximos passos**: decidir os 841 créditos sem contrapartida antes de marcar
  qualquer fechamento como pago; Etapa 5 (regra financeira — identidade de
  reincidência C3, `payment_cap` A5, `warranty_mode` A6, clamp do net M6) **exige
  decisão do dono do produto**; Etapa 6 (`Decimal`, listas truncadas em 30, planilha
  de pagamento no backend com auditoria, coluna do PDF com multiplicador, badge de
  origem/frescor dos dados).
- **Auditoria financeira completa do módulo Gamificação (somente diagnóstico —
  nenhum código, migration ou dado alterado)**: relatório em
  [auditoria-gamificacao-financeira-2026-08-26.md](auditoria-gamificacao-financeira-2026-08-26.md).
  Auditou arquitetura, fluxo financeiro ponta a ponta, fonte única da verdade,
  filtros/datas/fuso, arredondamento, crescimento do banco, idempotência,
  rastreabilidade, permissões, testes, divergência operacional e UX.
  **5 críticos, 8 altos, 9 médios, 7 baixos.**
  **Diagnóstico central**: o mesmo valor financeiro está persistido em três
  lugares — a linha `collaborator_scores`, o cache JSON
  `result_summary.score_summaries` e os totais `result_summary`/`cards` — sem
  nenhuma invariante que os obrigue a concordar, e cada endpoint lê um lugar
  diferente. Isso **já divergiu em produção**: o fechamento **#1601 (07/2026,
  pago)** mostra R$ 18.191,18 na tela/ranking/Excel de pagamento (cache) contra
  R$ 18.271,68 no histórico e no extrato PDF do colaborador (linhas do banco) —
  **R$ 80,50 / 230 pontos de diferença, 18 colaboradores afetados**. Causa de
  código isolada e reproduzida em sqlite isolado:
  `_apply_point_balance_after_payment` (`api/routes/calculation_runs.py:210-217`)
  escreve no cache sempre, mas só chama `flag_modified` dentro de `if adjusted:`
  — e o SQLAlchemy não detecta mutação in-place de coluna JSON.
  **Outros 4 críticos**: (C2) `apply_leadership_bonus_to_cost_by_regional` não é
  idempotente e soma o bônus de liderança de novo a cada recálculo — o #1601 tem
  a tabela "por regional" somando **R$ 38.264,02** contra R$ 24.282,77 reais, com
  **duas linhas duplicadas** de "Liderança sem regional"; e
  `POST /leadership/bonus-results/calculate` altera `result_summary` de fechamento
  **já pago** exigindo só `calculation:run`. (C3) a identidade de reincidência
  configurada é `contract`, e `contract_id` **não identifica cliente** — um
  contrato agrupa até **20 logins distintos**, 509 contratos/1.868 O.S. (2,52%)
  afetados, **1.757 pares** de clientes diferentes elegíveis a virar falsa
  garantia e anular pontos de quem não errou (as regras `#3` e `#8` não filtram
  tipo/assunto da O.S. original). (C4) **100% dos 1.377 ajustes manuais de saldo
  estão sem `created_by`** (criados por script fora da API), e há **+R$ 3.218,81
  líquidos pendentes para 96 pessoas** que serão somados automaticamente ao
  próximo fechamento marcado como pago; além disso **280 O.S. originais têm mais
  de um débito vivo** (263 em `applied`+`pending`), sem constraint única no banco.
  (C5) marcar como pago **não tem lock de linha nem idempotência** — janela de
  corrida medida de **33 segundos** no #1601.
  **Altos**: 1.106 `calculation_runs` e 225.121 `collaborator_scores` (223.811 em
  rascunhos descartáveis, 779 só de julho) porque `recalculate_current_period`
  cria um run novo a cada ciclo de 20 min; `_refresh_stale_draft_previews` carrega
  **todos** os rascunhos do sistema dentro da transação de pagamento; **nenhum
  índice** em `closed_at`/`opened_at`/`collaborator_id`/`calculation_run_id`
  (Seq Scan com estimativa de 1 linha para 6.989 reais); tabelas de custo
  truncadas em 30 itens exibindo o corte como total (57% do valor no #1601);
  **`payment_cap` não é lido em lugar nenhum** e **`warranty_mode` é inerte**
  (`is_warranty`/`is_recurrence` = 0 em todas as 75.177 O.S.); planilha de
  pagamento montada no frontend a partir do cache e **sem auditoria**; extrato
  PDF com coluna por O.S. **3,3× maior** que o "Valor a pagar" do próprio
  documento e acessível a qualquer perfil com `audit:read`; portal do colaborador
  lê o run **mais recente sem filtrar status** (mostra rascunho automático, não o
  pago).
  **Testes**: suíte do módulo — **85 passed**. Suíte completa — **668 passed, 13
  failed**, todas **pré-existentes e de outro módulo** (`test_ai_*`, Operação
  Analítica/IA; ex.: `TypeError: string indices must be integers` em
  `test_ai_sla_stage.py:161`). Nenhuma é regressão — nenhum código foi tocado.
  **Próximos passos (nada implementado ainda, cada fase precisa de aprovação)**:
  Fase 0 — **não marcar nenhum fechamento como pago** até conferir os 1.377
  créditos manuais; reconciliar e registrar qual valor do #1601 foi realmente
  pago; avisar quem opera que a tabela "por regional" do #1601 está inflada;
  escrever os testes de regressão que hoje faltam (devem falhar contra o código
  atual); restringir permissão do extrato PDF e do recálculo de bônus.
  Fase 1 — fonte única da verdade. Fase 2 — idempotência/concorrência/constraints.
  Fase 3 — correção de regra financeira (exige decisão do dono do produto sobre
  escopo histórico). Fase 4 — índices e retenção de rascunhos. Fase 5 — `Decimal`,
  fuso centralizado e UX (origem/frescor dos dados e alerta de divergência).
  A lista do que **não** pode ser alterado ainda está na seção 12 do relatório.
- **Backend: campos aditivos pra investigar handoff (preparação B3) + rodada
  visual forte nos painéis de segunda camada de `/suporte` (ainda sem
  commit)**:
  **Backend** — migration `20260826_0076` (aditiva, aplicada: `alembic
  current` = `20260826_0076 (head)`) adiciona 6 colunas nullable em
  `support_opa_attendances`: `distinct_human_attendant_ids` (JSON),
  `first_human_attendant_id`, `last_human_attendant_id`,
  `human_message_count`, `bot_message_count`, `client_message_count`. Todas
  calculadas por `_message_attendant_summary()` (novo, em `opa_ingestion.py`)
  a partir das MESMAS mensagens que `list_messages` já busca pra TMR — **zero
  chamada nova à API do OPA**. Preenchidas só quando `list_messages` já foi
  chamada com sucesso (mesmo bloco `try` de `handled_by_bot`/`reached_human`);
  lista de mensagens vazia → tudo `None` (dado insuficiente, nunca vira
  zero); mensagens presentes → contagens são zero real quando aplicável (ex.:
  atendimento só de bot tem `human_message_count == 0`, não `None`).
  **Não altera nenhum cálculo existente** — `tmr_seconds`,
  `tmr_all_responses_seconds`, `tma_seconds`, `handled_by_bot`,
  `reached_human`, `bot_to_human_handoff` continuam exatamente como antes
  (confirmado por `git diff` nas funções de cálculo — nenhuma linha tocada).
  5 testes novos em `test_opa_ingestion.py`: sem mensagens (tudo `None`),
  mensagens só de bot (`human_message_count == 0` real), um atendente
  humano, múltiplos atendentes humanos com ordenação cronológica correta
  (a lista de teste é montada propositalmente fora de ordem). Suíte do
  módulo support — **135 passed** (`test_opa_attendance_table.py`,
  `test_opa_ingestion.py`, `test_opa_scheduler.py`, `test_opa_client.py`,
  `test_opa_attendant_overrides.py`).
  Esses campos preparam uma investigação futura (não resolvem sozinhos a
  divergência de +149 do B3 — ver
  [roteiro-comparacao-tmr-opa-suite.md](roteiro-comparacao-tmr-opa-suite.md),
  seção 11) e não mudam nenhum KPI visível hoje.
  **Frontend** — rodada de modernização visual nos painéis de segunda
  camada, sem alterar dado nenhum: (1) painel de Atendentes trocou linhas de
  tabela administrativa por avatar em gradiente + barra de participação do
  volume + cores de estado (encerramento/avaliação coloridos por faixa) nas
  visões desktop e mobile; (2) drawer do atendente ganhou cabeçalho com
  gradiente e avatar maior (`h-14 w-14`), mais identidade visual — TMR
  geral/humano continuam ambos visíveis, cobertura do TMR geral continua
  visível; (3) drawer de detalhe do atendimento: os 6 blocos tipo formulário
  (Atendimento/Cliente/Atendente/Canal/Motivos/Datas) viraram um resumo
  executivo único (`AttendanceSummaryHeader`) — status colorido, protocolo
  discreto em monoespaçado, cliente e atendente como informação primária,
  códigos internos (cliente/atendente/departamento/canal) rebaixados pra uma
  linha de metadados no rodapé, tempos como StatCell de destaque; blocos
  restantes (Canal e contexto, Descrição/observações) só aparecem quando têm
  conteúdo; (4) tabela de Dados: protocolo virou código discreto
  monoespaçado (já feito na rodada visual anterior, mantido); (5) painel de
  Atendentes virtuais (aba Sincronização) ganhou cabeçalho com contador,
  avatar de iniciais por atendente, status com indicador de cor — mesma
  permissão e comportamento de antes.
  **Validado ao vivo** (usuário QA temporário, removido depois): Visão
  Geral, Atendentes (avatar em gradiente confirmado via `getComputedStyle`),
  drawer do atendente (cabeçalho em gradiente confirmado), Dados, drawer de
  detalhe do atendimento (resumo executivo renderiza protocolo/status/
  cliente/atendente/tempos corretamente, códigos internos no rodapé),
  Sincronização/Atendentes virtuais — todas sem erro novo no console (só o
  401 pré-login esperado) em desktop e mobile 375px, sem overflow
  horizontal em nenhuma tela (`scrollWidth === clientWidth` em todas).
  `npm run typecheck`, `npm run test -- --run` (35 passed) e `npm run build`
  limpos. `docker compose build backend frontend` + `up -d` rodados pros
  dois serviços.
  Arquivos: `models.py`, `opa_ingestion.py`, `test_opa_ingestion.py`,
  `20260826_0076_support_opa_message_attendant_summary.py` (novo),
  `opa-module-components.tsx`, `page.tsx`.
  **Mergeado** (parte do commit `f17e4c0`, PR #15).
- **Bloco B3 — 1ª execução real da comparação com o OPA oficial (Recorte 1,
  25/08/2026)**: usuário informou os números oficiais do painel do OPA para
  esse dia (total 828, TMA 01:01:47, TMR 00:03:54, base = encerramento,
  canal/depto = "Suporte/Financeiro"). Sistema local não tem um filtro
  "Canal" equivalente (`channel` local é só whatsapp/pabx/page — canal de
  comunicação, não fila) — tratei canal e departamento do OPA como a mesma
  dimensão e usei os departamentos locais mais próximos por nome (`Suporte
  Técnico` + `Financeiro`). **Resultado: o total não bateu** (981 local vs
  828 OPA, +18,5%) — indício de que essa equivalência de departamento não é
  exata. Isso impede uma comparação de TMA/TMR com confiança total (médias
  sobre populações diferentes), mas rendeu um sinal preliminar relevante:
  **TMR geral local (3min44s) ficou a apenas 10s do TMR do OPA (3min54s)**,
  enquanto TMR humano local (8min18s) ficou 264s acima — descartadas como
  causa as hipóteses de `opened_at`/`closed_at` (os dois usaram encerramento),
  ausência de histórico (25/08 está dentro da janela importada) e cobertura
  parcial (97,1% nesse recorte). Classificado como **"divergência por
  equivalência de filtro incerta"** — categoria nova adicionada ao roteiro,
  não uma das 7 originais, porque nenhuma delas descreve esse caso.
  **Refinamento (mesma sessão)**: usuário forneceu a tabela oficial do OPA por
  atendente (21 pessoas somando exatamente 828). Troquei a equivalência de
  departamento por **atendente nomeado exato** (localizado por nome completo
  na base, evitando homônimos) — mais preciso que nome de departamento. **O
  total ainda não bateu** (977 local vs 828 OPA, +18%), descartando a
  hipótese de que o problema era só o nome do departamento errado. Padrão por
  atendente: os 4 de volume baixíssimo (1–9 atendimentos) batem exatamente;
  os demais divergem, majoritariamente pra cima no local (+8 a +22),
  consistente com diferença de atribuição em atendimentos com transferência
  entre atendentes (handoff) — não parece ser fuso ou filtro de data.
  **Achado à parte, resolvido**: a linha "TOTAL/MÉDIA" da tabela por
  atendente do OPA (TMR 00:03:13) é uma **média simples das médias por
  atendente** (confirmado recalculando manualmente — bate exato), diferente
  do TMR do painel geral (00:03:54, aparenta ser ponderado por atendimento
  como o TMR geral local) — são fórmulas diferentes do próprio OPA, não uma
  divergência entre sistemas. O comparável ao TMR geral local continua sendo
  o valor do painel geral (234s), que segue a apenas 10s do TMR geral local.
  **Investigação da regra de atribuição (mesma sessão)**: checagem só de
  leitura no Postgres (sem chamar a API do OPA). **Achado estrutural**:
  `support_opa_attendances` tem uma linha por `source_id` (upsert), sem
  histórico de transferência — não existe "primeiro atendente" separado de
  "atendente atual" no schema, então não dá pra testar diretamente "conta só
  último atendente/responsável final" só com o banco local. Descartadas com
  evidência numérica: deduplicação por protocolo (977 protocolos distintos =
  977 linhas), vazamento pra outro departamento (100% dos 977 são Suporte
  Técnico ou Financeiro), múltiplos atendentes no mesmo registro (nenhum),
  fuso horário (só 2 dos 977 caem na hora mais sensível do dia), atendimento
  só-bot (97,2% tem `reached_human=true`), status diferente de finalizado
  (100% é "F"). **Hipótese nova com evidência favorável, não confirmada**:
  encerramento em massa por inatividade/timeout — o TMA desses 977 tem cauda
  longa grande (mediana 1h30, média 2h03, máximo ~100h); filtrando só TMA até
  2h a média cai pra 3.636s, a 1,9% do TMA oficial do OPA (3.707s); vários
  exemplos concretos (ex.: `UNI2026760877`, aberto 21/08 e fechado só 25/08,
  ~100h de TMA) mostram atendimentos abandonados sendo fechados em lote no
  fim do expediente. **Não é possível confirmar 100% só com o banco local**
  — precisaria de confirmação do lado do OPA (se o relatório por atendente
  exclui encerramento automático) ou da API de detalhe do OPA (fora do
  escopo desta tarefa). **Recomendação (não implementar agora)**: se
  confirmado, capturar/persistir o motivo do encerramento e mostrar TMA
  bruto vs. "trabalhado" lado a lado — nunca substituir um pelo outro. É
  mudança de cálculo, precisa de autorização explícita separada.
  **Busca exaustiva por campo de encerramento automático (mesma sessão)**:
  vasculhei `models.py`, todas as migrations do módulo, `opa_ingestion.py`
  (mapeamento completo de campos do payload) e `opa_client.py`, além do
  payload bruto salvo integralmente (`raw_payload = record`, sem filtro —
  confirmado no código). Levantei todas as chaves distintas numa amostra de
  3.000 registros recentes: `_id, canal, canal_cliente, canal_id, date,
  descricao, evaluations, fim, id_atendente, id_cliente, id_user, motivos,
  observacoes, origem, protocolo, setor, status, tags`. **Nenhuma delas é
  motivo de encerramento, flag de automático/timeout ou "encerrado por"** —
  `origem.tipo` só tem valor vazio ou `"anuncioWhatsapp"` (origem de
  campanha, não de encerramento); `status` só tem `"F"` nos dados
  analisados. **Conclusão: NÃO TESTÁVEL** — o campo não existe no payload
  que a API de listagem do OPA retorna, não é uma omissão do código de
  ingestão. Achado colateral (real, mas raro): `observacoes`/`motivos` têm
  um `id_atendente` por item que às vezes diverge do atendente final do
  registro (prova de handoff — ex.: `UNI2026760877` tem nota interna
  assinada por outra pessoa no dia da abertura) — mas só em 11/977 (1,1%) e
  10/977 (1,0%) dos casos, e 68% dos 977 não têm nenhuma nota registrada, o
  que é raro demais pra explicar sozinho os 149 de excedente. A hipótese de
  inatividade/timeout (evidência indireta pela distribuição de TMA)
  continua sendo a mais provável, mas sem campo dedicado pra confirmar.
  **Recomendação (não implementar agora)**: a única fonte com mais detalhe
  seria o histórico de mensagens por atendimento (`opa_client.list_messages`,
  já chamado durante a importação pra calcular TMR, mas hoje descartado
  depois do cálculo — não persistido) — capturar um resumo dele (atendentes
  distintos que responderam, o primeiro deles) seria a mudança mínima pra
  testar handoff com rigor. É mudança de ingestão/schema, precisa de
  autorização explícita separada.
  Nenhum cálculo de TMR foi alterado, nenhum backfill ou importação rodou,
  nenhuma chamada à API do OPA foi feita — só consultas de leitura via
  `opa_overview_service.expanded_overview` e SQL direto (sem escrita), e
  leitura de código-fonte.
  Resultado completo, tabela por atendente, protocolos de exemplo e números
  em [roteiro-comparacao-tmr-opa-suite.md](roteiro-comparacao-tmr-opa-suite.md),
  seções 10, 10.1, 10.2 e 10.3.
  **Validado que a rodada visual da tarefa anterior segue ativa**: `/suporte`
  abre sem erro novo no console nas abas Visão Geral/Atendentes/Dados,
  gradiente do card de volume e borda de destaque do cabeçalho confirmados
  via `getComputedStyle`, protocolo em fonte monoespaçada discreta
  confirmado, mobile 375px sem overflow horizontal.
- **Refinamento visual da tela `/suporte` (ainda sem commit)**: rodada de
  modernização visual sobre a base já implementada (B1+B2), sem alterar
  nenhum dado, contrato de API ou regra de negócio. Objetivo: tirar a
  aparência de sistema cru — mais contraste, hierarquia e cor com intenção,
  sem virar decoração vazia (norma visual permanente).
  Mudanças: (1) cabeçalho ganhou uma borda de destaque azul e um badge
  compacto "Base até DD/MM · N" ao lado do status de sincronização, deixando
  a janela real da base (B2) visível também no topo, não só no painel de
  filtros; (2) card de "Volume no período" da Visão Geral virou um destaque
  em gradiente azul (era um bloco branco igual aos demais) — é o número mais
  importante da tela e agora se comporta como tal; (3) título de cada seção
  (`OverviewSection`) ganhou uma barra de acento azul, reforçando hierarquia
  sem texto extra; (4) `BarListPanel` (canal/status) e "Clientes mais
  recorrentes" trocaram badge de posição cinza neutro por uma paleta com
  intensidade decrescente por rank (1º mais forte, últimos mais claros) —
  comunica ranking sem precisar de legenda; (5) cabeçalhos de painel (Motivos,
  Automação, Atendentes, Dados) ganharam fundo levemente tingido
  (`bg-slate-50/60`) e ícone/texto em azul em vez de cinza puro, tirando a
  repetição de branco-sobre-branco; (6) tabela de "Motivos" ganhou
  zebra-striping e a coluna TMR geral virou destaque em azul (é a métrica com
  cobertura registrada em B1, faz sentido chamar mais atenção pra ela); (7)
  tabela de "Dados": protocolo virou código discreto (monospace, cinza
  pequeno) em vez de texto preto igual ao nome do cliente — cliente continua
  sendo a informação primária da linha — e ganhou zebra-striping + hover azul
  suave.
  Nenhuma informação de B1/B2 foi removida: cobertura do TMR geral e janela
  da base importada continuam visíveis nos mesmos lugares (mais o badge novo
  no cabeçalho). Nenhum dado, filtro, cálculo ou endpoint foi tocado.
  **Validado ao vivo** (usuário QA temporário, removido depois): gradiente do
  card de volume, borda de destaque do cabeçalho e badge de base importada
  confirmados via `getComputedStyle`; abas Visão Geral, Atendentes e Dados
  navegadas sem erro novo no console (só o 401 pré-login esperado); mobile
  375px sem overflow horizontal (`scrollWidth === clientWidth`).
  `npm run typecheck`, `npm run test -- --run` (35 passed) e `npm run build`
  limpos. `docker compose build frontend` + `up -d` rodados.
  Arquivos: `opa-module-components.tsx`, `page.tsx`.
  **Mergeado** (parte do commit `f17e4c0`, PR #15).
- **Bloco B2 — janela real da base importada, visível na UI (mergeado)**:
  a base só tem atendimentos importados a partir de 01/08/2026 — sem essa
  informação visível, qualquer comparação com um período maior no painel
  oficial do OPA parece divergência/bug quando na verdade é ausência de
  histórico local (norma de qualidade de dados, seção 7). Campo novo aditivo
  `imported_data_window: {min_opened_at, max_opened_at, min_closed_at,
  max_closed_at, total_attendances}` (schema `SupportOpaImportedDataWindow`)
  em `/opa/overview`. Calculado por `imported_data_window()` — `MIN`/`MAX`/
  `COUNT` sobre a tabela **inteira**, sem nenhum filtro de período aplicado
  (propositalmente sem usar `apply_opa_attendance_filters`) — é sobre a base
  toda, não sobre o recorte escolhido pelo usuário; os dois nunca podem ser
  confundidos.
  Frontend: nota discreta nos filtros globais (`OpaGlobalFilters`), abaixo do
  texto "O mesmo recorte é aplicado à Visão Geral e aos Dados" — ex.: *"Base
  importada: 01/08/2026 até 26/08/2026 · 55.925 atendimentos"*. Quando o
  filtro escolhido (`date_from`) começa antes do início real da base, aparece
  um aviso amber ao lado: *"Este recorte começa antes da primeira data
  importada — a comparação com o OPA pode divergir por ausência de histórico
  local."* Nenhum alerta vermelho/alarmista — nota integrada ao painel.
  **Validado com dado real**: nota mostra corretamente 01/08/2026–26/08/2026,
  55.925 atendimentos; aviso amber testado navegando com
  `date_from=2026-07-20` (antes do início real) — renderiza corretamente, sem
  erro novo no console, sem overflow horizontal em mobile (375px). Validação
  de período de 32 dias (pré-existente, não é desta sessão) continua
  funcionando (422 fora do range).
  Testes novos (`test_opa_attendance_table.py`): janela reporta MIN/MAX/COUNT
  da base inteira mesmo filtrando um recorte que não cobre os extremos
  semeados; janela totalmente `None`/`total_attendances: 0` com base vazia.
  Suíte completa — **664 passed / 13 failed** (mesmas 13 falhas pré-existentes
  do módulo AI/governança, não relacionadas; +2 sobre o baseline do B1,
  confirmando os testes novos).
  Frontend: `npm run test -- --run` 35 passed, `typecheck` e `build` limpos.
  `docker compose build` + `up -d` rodados pros dois serviços.
  Arquivos: `opa_overview_service.py`, `schemas.py`,
  `test_opa_attendance_table.py`, `opa-module-components.tsx`, `page.tsx`,
  `frontend/lib/types.ts`.
  **Bloco B3 (comparação com painel oficial do OPA) — documentado, execução
  PENDENTE de dados do usuário.** Roteiro completo em
  [roteiro-comparacao-tmr-opa-suite.md](roteiro-comparacao-tmr-opa-suite.md),
  com tabela-modelo e critérios de classificação de divergência. A tabela de
  coleta foi entregue ao usuário no chat, ainda não preenchida. **Faltam,
  para cada recorte (dia recente ≥20/08, últimos 7 dias, agosto até hoje):**
  se o OPA usa abertura ou encerramento como base de data; filtros aplicados
  (status/canal/departamento/atendente/motivo); total de atendimentos;
  encerrados; em aberto; TMA; TMR; primeira resposta (se existir). **Enquanto
  esses dados não existirem, nenhuma divergência entre o sistema local e o
  OPA deve ser classificada como bug** — só dá pra distinguir "diverge por
  cobertura parcial" / "diverge por ausência de histórico local" / "diverge
  por abertura vs encerramento" / "bug provável" depois de ter os números
  reais dos dois lados lado a lado (seção 8 do roteiro).
  **Mergeado** (parte do commit `f17e4c0`, PR #15) — junto com o B1.
- **Bloco B1 — TMR geral ganhou denominador explícito (cobertura do histórico)**:
  auditoria anterior mediu 0% de cobertura de `tmr_all_responses_seconds` entre
  01/08–19/08 e 76–86% entre 20/08–26/08 — a UI mostrava a média sem dizer sobre
  quantos atendimentos ela foi calculada, violando a norma de qualidade de dados
  (seção 1: "todo percentual precisa dizer sobre o que foi calculado"; "número
  errado é pior que número ausente"). Nenhum backfill rodado, nenhum cálculo
  alterado — só o denominador ficou visível.
  Campo novo aditivo `tmr_all_responses_coverage: {count, total, percentage}`
  (schema `SupportOpaMetricCoverage`) em `/opa/overview`,
  `/opa/attendants/{id}/summary`, `top_reasons`/`by_reason` (por motivo) e
  `/opa-metrics` (API pública, embora nenhuma tela a consuma). `count` vem de
  `func.count(tmr_all_responses_seconds)` na MESMA query que já calculava a
  média — `COUNT` ignora `NULL` igual `AVG`, zero consulta nova ao banco.
  Frontend: `TimeMetricsStrip` (usado na Visão Geral e no painel individual)
  ganhou um rodapé discreto dentro do próprio painel (sem card novo) quando a
  cobertura é parcial — ex.: *"TMR geral: média sobre 10.865 de 55.925
  atendimentos (cobertura de 19,4%) — histórico mais antigo ainda não foi
  reprocessado."* Nada aparece quando a cobertura é 100% ou quando não há
  atendimento no recorte. `TopReasonsSummary` (tabela de motivos) ganhou
  tooltip com o denominador por motivo, sem adicionar coluna.
  **Validado com dado real de produção**: `tmr_all_responses_coverage` =
  `{count: 10865, total: 55925, percentage: 19.4}` no período 01/08–26/08 —
  bate com a estimativa da auditoria anterior. Painel do Theo (agente virtual)
  mostra a mesma nota com o denominador escopado ao atendente (4.152 de
  23.271, 17,8%) — TMR geral continua em destaque, TMR humano continua
  visível como secundário, nenhum dos dois foi escondido.
  Testes novos (`test_opa_attendance_table.py`): cobertura parcial (com a
  média inalterada), cobertura zero, cobertura 100%, `percentage=None` pra
  universo vazio, e confirmação de que TMR humano fica independente da
  cobertura de TMR geral. Suíte completa — **662 passed / 13 failed**
  (mesmas falhas pré-existentes do módulo AI/governança, não relacionadas).
  Frontend: 35 passed, build e typecheck limpos. `docker compose build` +
  `up -d` rodados pros dois serviços (container roda em produção, sem hot
  reload).
  Arquivos: `opa_overview_service.py`, `opa_attendant_service.py`,
  `router.py`, `schemas.py`, `test_opa_attendance_table.py`,
  `opa-module-components.tsx`, `page.tsx`, `frontend/lib/types.ts`.
- **Bloco A de estabilização — worktree versionada, risco crítico removido**:
  auditoria anterior identificou que 40 arquivos (~3.000 linhas) estavam sem commit
  havia várias sessões, incluindo **3 migrations já aplicadas no Postgres real**
  (`20260825_0073`, `20260825_0074`, `20260826_0075`) que existiam só como arquivo
  local — se a worktree fosse perdida, o schema real (colunas de TMR geral,
  classificação bot/humano, tabela de agente virtual) ficaria irreprodutível por
  nenhum commit do repositório. Organizado em **8 commits temáticos**, sem push:
  1. Colunas de TMR geral + classificação bot/humano (migrations 0073+0074)
  2. Tabela de cadastro de agente virtual (migration 0075)
  3. Backend consolidado do SGP Suporte (TMR geral, `date_basis`, integração do
     agente virtual, status de sincronização, limite de sync de clientes,
     services de fases anteriores nunca commitados)
  4. Formatação de duração sem arredondar segundos pequenos (`secondsLabel`)
  5. Frontend consolidado do SGP Suporte (mesmos temas do commit 3 + Fase 4A visual)
  6. Padronização do token de autenticação em `localStorage` entre módulos
     (achado da auditoria, não é trabalho desta sessão — preservado, não revertido)
  7. Zoom nos mini-gráficos do cockpit (idem, não é trabalho desta sessão)
  8. Scripts pontuais de manutenção (monitor de outage, publicações de teste)
  Commits 6, 7 e 8 são trabalho de outras tarefas encontrado na worktree — commitados
  para eliminar o risco, não implementados nesta sessão.
  **Limitação registrada nos commits 3 e 5**: os arquivos centrais do módulo
  (`opa_ingestion.py`, `router.py`, `schemas.py`, `page.tsx`,
  `opa-module-components.tsx`) foram evoluídos em sessões sequenciais tocando as
  mesmas funções repetidamente — separar por hunk entre os 4 temas arriscaria
  commits intermediários com estado inconsistente, então cada um desses dois
  commits reúne múltiplos temas com a justificativa completa na mensagem.
  Migrations, models.py e todo o resto (arquivos novos) foram separados por tema
  normalmente.
  **Confirmado**: `alembic heads` == `alembic current` == `20260826_0075`, e os 3
  arquivos de migration correspondentes estão commitados. `git status` limpo após
  a sequência.
  Baseline de testes registrado: backend **657 passed / 13 failed** — as 13 falhas
  são em `test_ai_geo.py`, `test_ai_fields.py`, `test_ai_sla_stage.py` e
  `test_ai_team_model_consistency.py` (`TypeError: string indices must be
  integers`), bug real do módulo AI/governança, não relacionado ao SGP Suporte,
  pré-existente a este bloco — não escondido, registrado como pendência própria.
  Frontend: 35 passed, build e typecheck limpos (confirmado nesta rodada).
- **Norma de qualidade de dados e métricas criada** —
  `docs/normas-qualidade-dados-metricas.md`, indexada em `docs/00-TRILHA-0.md` como
  **norma permanente** (não é plano de fase). Vale para todos os módulos, não só o
  SGP Suporte. Existe porque divergência de número deixa de ser detectável no olho
  conforme a base cresce: com 500 atendimentos alguém percebe que faltou um dia; com
  55.000 ninguém percebe. As regras foram extraídas de causas raiz reais deste
  projeto (auditoria de divergência com o OPA, truncamento de 50.000 clientes,
  arredondamento que escondia TMR pequeno, lock de importação sem mensagem clara),
  não de teoria. Cobre: fonte única de regra (KPI vive no service, frontend só
  formata e **nunca** recalcula KPI oficial com lista parcial), contrato de filtros
  (fuso `America/Porto_Velho`, `date_from`/`date_to` inclusivos, `opened_at` vs
  `closed_at`, filtro novo propagado para todos os endpoints do módulo), tempos
  sempre em segundos com média sobre bruto, política de histórico/backfill (toda
  mudança declara se afeta dado novo, histórico ou ambos), exigências de importação
  (run rastreável e visível durante a execução, status terminal que sobrevive a
  rollback, lock preservado mas com mensagem amigável), validação cruzada em dia
  pequeno/dia grande/7 dias com divergência classificada como esperada ou bug, 6
  testes obrigatórios para métrica nova, checklist de conclusão e **regra visual
  permanente** para dashboards. Nenhum código foi alterado nesta tarefa.
- **SGP Suporte / OPA Suite — Fase 4A rodada 3 (refino de espaço/densidade)**:
  continuação da rodada 2 (item abaixo) — mesma composição visual, sem
  mudança estrutural nova. Objetivo: eliminar área branca sem função onde um
  painel pequeno era esticado pela altura de uma lista/tabela ao lado. Só
  frontend (`page.tsx`, `opa-module-components.tsx`).
  1. **Bloco Clientes** (`CustomerSummaryPanel`, `OpaOverview`): a coluna da
     esquerda (Clientes únicos / Reincidentes / Pressão de recorrência) tinha
     bem menos conteúdo que o ranking de recorrentes ao lado — como as duas
     ficam num grid `items-stretch`, a esquerda esticava até a altura do
     ranking e sobrava um vazio grande sob os cards. Correção: ranking
     ganhou altura máxima de 420px com scroll interno próprio (não perde
     nenhum item, só limita o quanto pode crescer), e a coluna da esquerda
     passou a centralizar o conteúdo verticalmente (`flex flex-col
     justify-center`) dentro da mesma altura — as duas colunas agora batem
     exatamente na mesma altura, sem sobra visível. Confirmado ao vivo:
     420px/420px (antes a esquerda ficava bem mais curta que a direita com
     10 itens de ranking).
  2. **Mesmo ajuste no card "Volume no período" da Visão Geral** (Operação)
     e no equivalente do painel individual do atendente — a coluna de
     resumo (número grande + tendência) tinha menos altura que a grade de
     6 (Operação) ou 4 (atendente) `StatCell` ao lado; agora o conteúdo fica
     centralizado verticalmente em vez de colado no topo com vazio embaixo.
  3. Confirmado que o ranking de clientes recorrentes **não é mais tabela**
     (já tinha sido convertido numa rodada anterior — número + nome + código
     secundário + badge, sem `<table>`) e que "Pressão de recorrência" (com
     barra de progresso) já existia e continua visível.
  **Validado ao vivo** (usuário de QA temporário, criado e removido ao
  final): medi a altura real das duas colunas via JS no navegador contra
  dado de produção — Operação 161px/161px, Clientes 420px/420px (iguais).
  Testei também o painel do Theo (agente virtual): badge, TMR geral em
  destaque, TMR humano visível como secundário — nada mudou de
  comportamento, só o espaçamento ao redor. Desktop e mobile (375px) sem
  overflow horizontal em nenhuma tela (Visão Geral, Atendentes, Dados,
  painel individual aberto). Console sem erro novo (só o 401 de
  `/api/auth/me` que já acontecia antes do login completar, comportamento
  do app inteiro, não desta tela).
  Validações executadas: `npm run typecheck` (via `docker compose build
  frontend`, limpo — o build roda `next build` que inclui o typecheck),
  `npm run test -- --run` (35 passed), `docker compose build frontend` e
  `docker compose up -d frontend` (obrigatório pra ver o resultado, já que o
  container roda em modo produção sem hot reload).
  **Limitação que ainda depende do usuário**: a validação visual foi feita
  por extração de estrutura/medidas via JavaScript no navegador real, não
  por screenshot (o ambiente desta sessão não expõe captura de tela). Se
  ainda sobrar alguma área "quase vazia" que só aparece visualmente (ex.:
  espaçamento fino, alinhamento de texto), o jeito mais rápido de resolver é
  abrir `/suporte` você mesmo e apontar exatamente onde.
- **SGP Suporte / OPA Suite — caixa "Último erro" da Sincronização deixava
  de ser confiável**: usuário reportou (com print da tela real) a aba
  Sincronização mostrando uma caixa vermelha de "Último erro" com o texto
  *"A sincronização automática do OPA está em andamento. Aguarde a
  conclusão..."* — que não é uma falha, é só o retrato de uma tentativa que
  esbarrou numa importação anterior ainda rodando. Investigado ao vivo
  contra o Postgres real: confirmado que é exatamente esse cenário (ciclo
  anterior, iniciado às 10:30 local, ainda processando às 11:14+ porque o
  lookback de 5 dias com busca de mensagem por atendimento pra TMR ultrapassa
  o intervalo de 60min configurado — mesmo comportamento já documentado na
  entrega anterior de status de sync, só que agora visto na prática com
  `consecutive_failures=1`). O "Último sucesso" parado em 09:00 também é
  esperado: é o horário do último ciclo que **terminou**; o ciclo iniciado às
  10:30 ainda não terminou.
  Correção (só frontend, mensagem de apresentação — nenhum dado novo, nenhum
  cálculo de retry/falha alterado no backend): `isTransientBusyMessage` (nova
  função exportada em `opa-module-components.tsx`) detecta esse padrão de
  mensagem e faz a UI parar de tratá-lo como erro real — a caixa vermelha
  vira uma caixa neutra explicando o que aconteceu e que o próximo ciclo
  segue normal; o badge discreto de sincronização no topo da tela (adicionado
  na Fase 4A) também para de mostrar "Sincronização com erro" nesse caso,
  virando "Sincronizando (automático)". `Falhas seguidas` continua mostrando
  o número real (dado cru, não escondido) — só a leitura textual do erro que
  deixou de alarmar por algo que não é uma falha de verdade.
  **Validado ao vivo**: confirmado com o cenário real de produção (mesmo
  ciclo travado) que a caixa vermelha some e vira a explicação neutra, e o
  badge do topo muda de "Sincronização com erro" pra "Sincronizando
  (automático)". `docker compose build frontend` limpo, `npm run test`
  35/35.
  **Pendência real (backend, fora do escopo desta correção visual)**: o
  problema de fundo continua — o intervalo de 60min é mais curto que o tempo
  real de um ciclo completo (5 dias de lookback com busca de mensagem por
  atendimento). Se isso incomodar, as opções são aumentar o intervalo,
  reduzir o lookback, ou revisar a estratégia de busca de mensagens — nenhuma
  foi decidida nem implementada aqui.
- **SGP Suporte / OPA Suite — Fase 4A rodada 2 (evolução real de layout, não
  só reagrupamento)**: a rodada 1 (item abaixo) só reagrupou cards em seções
  tituladas — o usuário validou e apontou que ainda parecia "grade infinita
  de cards iguais", sem identidade visual própria. Esta rodada reconstrói a
  composição visual da Visão Geral e do painel individual, mantendo 100% dos
  dados/contratos/cálculos da rodada 1 intactos. Só frontend
  (`page.tsx`, `opa-module-components.tsx`).
  1. **Operação virou um painel composto, não mais 7 cards soltos**: um
     único container com "Volume no período" em destaque (número grande +
     tendência) numa coluna, e as métricas secundárias (Encerrados, Em
     aberto, Taxa de encerramento, Avaliação, Atendentes, Departamentos) em
     células divididas por `divide-x`/`divide-y` do lado — sem borda própria
     por célula. Mesmo padrão aplicado ao resumo de KPIs da aba Atendentes.
  2. **Tempo ganhou identidade visual própria** (`TimeMetricsStrip`, novo
     componente exportado e reaproveitado no painel individual): faixa com
     fundo âmbar suave, sem selo de ícone por célula — deliberadamente
     diferente da paleta azul/neutra de Operação, pra não parecer "mais do
     mesmo". TMR geral e TMR humano continuam os dois sempre visíveis (TMR
     geral com destaque quando o atendente é agente virtual).
  3. **Removida a borda azul superior repetida** de todo card (`MetricCard`
     foi eliminado do arquivo — ficou sem uso depois da mudança acima).
  4. **Canal e Status viraram lista de barras horizontais** (`BarListPanel`,
     CSS puro — sem biblioteca de gráfico nova) em vez de tabela de duas
     colunas — melhora leitura de proporção e uso da largura. Motivos e
     Clientes recorrentes mantidos como tabela (fazem mais sentido tabulares
     por terem várias colunas/métricas).
  5. **Clientes virou painel composto**: célula dividida (únicos/reincidentes)
     ao lado da tabela de clientes mais recorrentes, lado a lado em telas
     largas (`lg:grid-cols-[1fr_1.3fr]`) em vez de empilhado.
  6. **Painel individual do atendente**: cabeçalho ganhou avatar com iniciais
     (círculo azul se agente virtual, cinza se humano); "Volume no período"
     + tendência viraram um painel composto igual ao da Visão Geral
     (a antiga seção separada "Tendência vs período anterior" foi
     incorporada aqui, um bloco a menos); bloco "Tempos" passou a usar o
     mesmo `TimeMetricsStrip` da Visão Geral; Clientes e Automação (bot vs.
     humano) viraram um painel composto lado a lado.
  Cabeçalhos de seção (Distribuição, Motivos, Clientes recorrentes, Bot vs.
  humano) foram uniformizados: título pequeno em maiúsculas + ícone
  discreto cinza, no lugar do ícone azul + título grande de antes.
  **Validado ao vivo de novo** (mesmo processo: usuário de QA temporário,
  criado e removido ao final): confirmado visualmente via extração de texto
  da página real (54.963 atendimentos, dado de produção) que o painel
  "Operação" mostra volume em destaque com células divididas, "Tempo"
  aparece com sua própria faixa, e o painel do Theo mostra avatar "TH",
  badge "Agente virtual", TMR geral (1 min 31s) em destaque e TMR humano
  (18 min 32s) esmaecido — os dois continuam visíveis, nenhum foi escondido.
  Testado em desktop (1280px) e mobile (375px) sem overflow horizontal em
  nenhuma das duas passagens (Visão Geral e painel individual aberto).
  Console sem erro novo. `npm run typecheck` (via `docker compose build
  frontend`, limpo), `npm run test` (35 passed, sem suíte própria desta
  tela), `docker compose build frontend` OK.
  **Pendência**: sem screenshot/imagem real anexada nesta sessão — a
  validação visual foi feita por extração de texto/estrutura da página real
  via navegador (o ambiente não expõe captura de tela nesta sessão); se o
  resultado visual (cores, alinhamento fino, espaçamento) ainda não
  satisfizer, path de iteração mais rápido é abrir `/suporte` e apontar o
  que exatamente incomoda (cor, tamanho, alinhamento) em vez de pedir nova
  rodada estrutural.
- **SGP Suporte / OPA Suite — Fase 4A rodada 1 (UX/layout visual)**: só
  frontend, nenhum contrato/cálculo/endpoint tocado — plano em
  `docs/plano-ux-visual-sgp-suporte-fase-4a.md`. Superada pela rodada 2
  acima (o usuário achou insuficiente — ainda parecia grade de cards
  repetidos); mantida aqui como histórico do que foi tentado primeiro.
  1. **Topo compactado**: removido o card-hero (ícone grande + título 2xl +
     subtítulo isolado); virou um cabeçalho de página de uma linha (título +
     descrição curta) com um indicador discreto de sincronização
     (`SyncStatusIndicator`) ao lado — badge pequena que muda de cor/texto
     conforme `syncStatus` (erro, em andamento, automático ligado/desligado) e
     leva direto pra aba de sincronização ao clicar. Reaproveita o
     `syncStatus` que já era carregado — nenhuma chamada nova.
  2. **Visão Geral reagrupada** (`OpaOverview`): os 8 KPIs soltos + 5 cards
     empilhados viraram 5 seções tituladas — Operação, Tempo, Clientes,
     Automação, Distribuição — via um wrapper leve (`OverviewSection`, só
     título + espaçamento, sem borda própria). Canal e Status agora ficam
     lado a lado (2 colunas) dentro de "Distribuição" em vez de empilhados.
     Nenhuma métrica foi removida, só reorganizada.
  3. **Tabela de atendimentos**: status virou `Badge` (cor muda se encerrado
     vs em aberto, usando `closed_at`); ação de detalhe virou ícone
     `ghost` só com `aria-label`, no lugar do botão `outline` com texto —
     nome do cliente já era principal e código secundário, mantido.
  4. **Painel individual por atendente**: cabeçalho ganhou uma linha-resumo
     em texto (volume · taxa de encerramento · avaliação) abaixo do nome +
     badge; o bloco "Painel individual" ganhou subtítulos (Tempos, Clientes,
     Automação, Distribuição) e Canal/Status também passaram a ficar lado a
     lado. A priorização de TMR geral para agente virtual (feita numa fase
     anterior) foi preservada e validada ao vivo com o Theo.
  5. **Timeline do atendimento**: linha vertical conectando os eventos
     (antes os pontos ficavam soltos); aviso de privacidade reforçado com
     ícone e reposicionado no topo da seção — texto e dados continuam
     exatamente os mesmos, só a apresentação mudou.
  6. **Sincronização/agente virtual**: sem mudança estrutural (já estavam
     organizados de fases anteriores) — só o indicador discreto do item 1
     que leva até essa aba.
  **Validação real feita no navegador** (não só typecheck): criado um
  usuário temporário só pra login de QA (removido ao final da validação),
  logado de verdade em `/suporte` contra o backend e Postgres reais, com
  54.963 atendimentos carregados. Confirmado: as 5 seções da Visão Geral
  renderizam na ordem certa; a tabela de dados mostra nome do cliente como
  principal e código como secundário; abrir um atendimento mostra o detalhe
  completo + timeline com linha conectora, badges por ator (Cliente/IA-Bot/
  Atendente/Sistema/Não identificado) e aviso de privacidade — sem texto de
  mensagem em nenhum momento; abrir o painel do Theo (atendente cadastrado
  como agente virtual numa fase anterior) mostra badge "Agente virtual",
  linha-resumo, TMR geral em destaque (1 min 31s) e TMR humano esmaecido
  como "não aplicável" (18 min 32s) — comportamento correto; aba de
  sincronização mostra o indicador discreto e o painel completo sem erro.
  Testado em desktop (1280px) e mobile (375px, emulado) — sem overflow
  horizontal na página em nenhum dos dois (a tabela mantém seu próprio
  scroll horizontal interno, como já era e como o objetivo pedia pra manter
  por enquanto). Console do navegador sem erro novo — só os dois 401 de
  `/api/auth/me` que já aconteciam antes do login completar (comportamento
  pré-existente do app inteiro, não desta tela).
  Validações executadas: `npm run typecheck` (via `docker compose build
  frontend`, limpo), `npm run test` (35 passed, nenhum teste cobre
  `/suporte` diretamente — não há suíte própria desta tela), `docker
  compose build frontend` (build de produção OK), validação visual real
  descrita acima.
  **Observação (não corrigida nesta fase, fora de escopo)**: durante a
  validação, o cadastro de agente virtual do Theo feito numa fase anterior
  não apareceu na tabela de "Atendentes virtuais" (`Nenhum atendente
  virtual cadastrado.`), embora a classificação de Theo como bot continue
  funcionando (dimensão `payload_json.tipo="bot"` do próprio OPA já cobre
  esse caso — só o registro manual em si que sumiu). Não investigado nem
  alterado por estar fora do escopo desta tarefa (só visual/frontend,
  proibido mexer em banco/backend); registrar como pendência para uma
  próxima tarefa.
  Arquivos alterados: `frontend/app/suporte/page.tsx`,
  `frontend/app/suporte/_components/opa-module-components.tsx`. Nenhuma
  mudança em `types.ts`, `api.ts`, backend, banco ou migrations.
- **SGP Suporte / OPA Suite — cadastro de "atendente virtual" (agente virtual/bot
  manual), pra classificar corretamente atendentes que o OPA não marca como bot**:
  o Theo (`5d1642ad4b16a50312cc8f4d`) já está `tipo="bot"` na dimensão sincronizada
  do OPA — não era um bug de classificação, era falta de mecanismo pra **forçar**
  essa classificação em casos futuros onde o OPA não mande `tipo="bot"`, e falta de
  hierarquia visual no painel individual entre TMR humano e TMR geral pra esses
  casos.
  Nova tabela `support_opa_attendant_overrides` (migration `20260826_0075`):
  `attendant_id` (único), `attendant_name` opcional, `classification` (hoje só
  `"virtual_agent"` é aceito — validado no schema, não em enum de banco, pra não
  exigir migration se surgir um novo valor), `active`, auditoria. CRUD completo em
  `/support/opa/attendant-overrides` (`GET`/`POST`/`PATCH`/`DELETE`), permissão
  `support:sync_opa` (mesma da config de sync — é administração do módulo).
  Resolução unificada em `opa_attendant_overrides.resolve_attendant_type`
  (override manual ativo > `payload_json.tipo` da dimensão OPA > `None`), usada nos
  DOIS lugares que antes liam `tipo` de forma independente e duplicada:
  `opa_ingestion._load_attendant_types` (classificação de mensagens na ingestão —
  agora cobre atendente que nem chegou a existir na dimensão sincronizada, só no
  cadastro manual) e `opa_attendant_service.resolve_attendant_identity`
  (`attendant_type` exposto no painel individual). Zero chamada nova à API do OPA —
  overrides são só mais uma query local.
  `tmr_seconds` e `tmr_all_responses_seconds` continuam com o mesmo significado e
  cálculo de sempre; o que muda é só QUAIS mensagens contam como "bot" na hora de
  montar `human_attendant_ids`/`_classify_bot_human`.
  Frontend: painel de cadastro (`OpaAttendantOverridesPanel`) na aba
  "Sincronização" (tabela + form de criar + ativar/desativar + remover, sem
  polling novo). No painel individual do atendente: badge do bot renomeado pra
  "Agente virtual"; quando `attendant_type === "bot"`, TMR geral vira o card em
  destaque (`emphasis`) e TMR humano fica esmaecido com helper "não aplicável a
  agente virtual" — troca puramente visual, nenhum cálculo muda.
  **Validado com dado real de produção**: Theo cadastrado como `virtual_agent` via
  chamada direta ao endpoint (mesmo mecanismo que o botão "Cadastrar" do painel
  usa) — `resolve_attendant_identity` confirmou `attendant_type: "bot"` puxando do
  override, não mais só da dimensão OPA.
  Testes novos: 16 em `test_opa_attendant_overrides.py` — função pura de
  resolução (prioridade override > OPA > `None`), CRUD completo (criar, duplicar
  rejeitado, desativar, remover, remover inexistente 404), regressão (bot com
  `tipo="bot"` continua funcionando sem override), atendente sem `tipo` nenhum
  classificado via override, override vencendo `tipo="user"` da dimensão OPA,
  `attendant_summary` marcando `attendant_type="bot"` e priorizando TMR geral,
  atendente cadastrado nunca mais aparece como desconhecido mesmo sem nenhum
  atendimento importado ainda. Suíte completa — **657 passed**, mesmas 13 falhas
  pré-existentes não relacionadas (`ai`/`ai_governance`), zero regressão nova.
  Frontend: build + `tsc` sem erro. Backend e frontend rebuildados e reiniciados;
  migration aplicada no Postgres real (via `alembic upgrade head` automático do
  entrypoint).
  **Pendência**: reprocessamento em massa dos atendimentos antigos do Theo (e de
  qualquer outro atendente que ganhe override daqui pra frente) não foi feito —
  overrides só afetam **novas** importações, mesma regra já aplicada ao TMR-geral;
  histórico já importado mantém a classificação salva na época. Decidir se
  compensa reimportar quando/se aparecer outro caso relevante.
- **SGP Suporte / OPA Suite — a run ativa de importação agora fica visível
  DURANTE a execução, não só depois que tudo termina**: correção de uma
  lacuna descoberta em validação real do item anterior (status de
  sincronização). Diagnóstico confirmado: `import_opa_attendances` criava a
  `SupportOpaImportRun` com `db.add(run); db.flush()` — visível só dentro da
  própria transação, nunca commitada até o fim de todas as páginas. Isso
  fazia `lock_busy=true` aparecer corretamente (lock do Postgres é por
  sessão, não por transação) mas `active_run_id`/`active_run_mode` ficarem
  vazios durante importações reais longas, porque
  `select * from support_opa_import_runs where status='running'` não
  enxergava a linha ainda não commitada.
  Correção: `_create_running_import_run` cria e commita a run numa **sessão
  própria e curta**, chamada só depois que o lock já foi adquirido (evita
  linha órfã se o lock estiver ocupado) e antes do processamento longo de
  páginas — outras conexões passam a ver `status="running"` no instante em
  que a importação realmente começa. Usar uma sessão separada (não um
  `db.commit()` no meio da sessão principal) foi deliberado: um commit no
  meio devolveria a conexão da sessão principal pro pool, podendo trocar de
  conexão física na sequência e quebrar o `pg_advisory_unlock` (que precisa
  rodar na MESMA conexão que adquiriu o lock) — o lock vazaria
  silenciosamente. Mesmo padrão aplicado em `resume_opa_import_run`
  (retomada de run interrompida) e em `_persist_run_terminal_status`, que
  agora grava o status final (completed/completed_with_warnings/interrupted/
  failed) também numa sessão à parte e já commitada — sem isso, uma falha
  cujo tipo não é `OpaImportInterrupted` faz o router reverter
  (`db.rollback()`) a sessão inteira, incluindo o `status="failed"` recém-
  gravado, deixando a run presa em "running" pra sempre (o mesmo problema de
  visibilidade, só que permanente). `_opa_import_busy_message` ganhou um
  terceiro caso (lock ocupado, nenhuma run "running" visível — corrida
  residual entre lock e commit): *"Há uma importação do OPA Suite em
  andamento, mas a run ativa ainda não pôde ser identificada. Aguarde alguns
  instantes e tente novamente."* — mesmo texto no painel do frontend.
  Nenhuma mudança no lock em si, no cálculo de TMR, nem nos endpoints de
  dados da OPA Suite.
  **Risco residual documentado (não corrigido, fora do escopo)**: se o
  processo morrer no meio do processamento (kill -9, OOM) sem passar pelo
  `finally`, a run fica presa em "running" pra sempre — o Postgres libera o
  lock automaticamente ao fechar a conexão, mas a linha em
  `support_opa_import_runs` não tem um mecanismo de expiração/heartbeat.
  Precisaria de um job de limpeza (ex.: marcar como "failed" runs
  "running" há mais de N horas) se isso se tornar um problema real.
  Testes novos: 6 em `test_opa_ingestion.py` — run visível durante
  `list_attendances` (via cliente fake "espião"), ordem commit-antes-do-
  fetch (via spy no `db.commit()`), status final sobrevive a rollback do
  chamador, `active_opa_import_run` volta a `None` após sucesso, mensagem de
  fallback do lock, `/opa-sync-status` mostrando a run ativa em tempo real
  durante uma importação simulada. Precisou de um fixture novo em
  `conftest.py` (`_bind_opa_ingestion_session_local`, autouse): as sessões
  próprias que `opa_ingestion.py` agora abre (`SessionLocal()`) apontavam
  pro engine `:memory:` global do app, diferente do engine isolado por
  teste que `db_session` usa — sem o bind, os testes não enxergariam as
  runs criadas pelas novas sessões. Suíte completa — **641 passed, 13
  failed** (mesmas falhas pré-existentes de sempre, `ai`/`ai_governance`;
  a duplicação da suíte pelo artefato `tests/tests/` sumiu porque o
  `docker cp` desta sessão substituiu a pasta inteira — bônus, não
  intencional). Frontend: build + `tsc` sem erro. Backend e frontend
  rebuildados e reiniciados; validado ao vivo contra o Postgres real
  (`lock_busy=false`, nada em andamento no momento).
  **Pendência**: não foi disparada uma importação manual/automática real em
  produção pra confirmar visualmente `active_run_id` populado durante uma
  execução de verdade (regra explícita da tarefa: não rodar importação sem
  autorização) — a cobertura de teste (commit-antes-do-fetch, visibilidade
  mid-flight via cliente espião) já prova o mecanismo, mas falta essa
  confirmação final ao vivo.
- **SGP Suporte / OPA Suite — status de sincronização automática mais claro,
  sem tocar no lock**: o lock consultivo do Postgres (`913275003`,
  `_support_opa_import_lock` em `opa_ingestion.py`) já funcionava
  corretamente e continua exatamente igual — o problema era só a experiência
  ao esbarrar nele. Como a rotina agora busca mensagens por atendimento pra
  calcular TMR, um ciclo automático pode legitimamente durar mais que o
  intervalo configurado, e quem tentava importar manualmente nesse meio
  tempo só via `"Outra importação do OPA Suite já está em andamento."` cru,
  sem saber se era a automática ainda rodando ou um lock travado.
  Mudanças:
  1. Duas funções novas e só-leitura em `opa_ingestion.py`:
     `active_opa_import_run` (última `SupportOpaImportRun` com
     `status="running"`) e `opa_import_lock_busy` (tenta adquirir o lock e,
     se conseguir, libera na hora — nunca fica com ele; só confirma se
     estava livre). `_opa_import_busy_message` usa a run ativa pra decidir o
     texto do erro 409: se for `mode="scheduled"`, mensagem = *"A
     sincronização automática do OPA está em andamento. Aguarde a conclusão
     para iniciar uma importação manual."*; senão, mensagem genérica de
     importação manual concorrente (nunca expõe erro técnico cru).
  2. `/opa-sync-status` ganhou campos aditivos (`SupportOpaSyncStatus`):
     `sync_in_progress`, `lock_busy` (`null` fora do Postgres, ex.: testes em
     SQLite), `active_run_id`, `active_run_mode`, `active_run_started_at`,
     `next_window_delayed` (true quando `next_allowed_at` já passou e ainda
     há import em andamento — sinaliza pra UI que a próxima janela está
     esperando a execução atual terminar, não é erro).
  3. `opa_scheduler.py`: `next_allowed_at` agora é recalculado a partir do
     **fim** de cada execução (sucesso, interrompida ou falha), não mais só
     do início (`_push_next_allowed_at_from_now`) — decisão documentada no
     código. Antes, um ciclo mais longo que o intervalo deixava
     `next_allowed_at` no passado antes mesmo de terminar, confundindo a UI.
  4. Frontend: painel de sincronização (`OpaSyncPanel`) ganhou linha
     "Importação agora" e um aviso inline quando há sync em andamento,
     citando se é automática ou manual e avisando quando a próxima janela
     está represada por ela. Sem polling novo — usa as mesmas chamadas a
     `supportOpaSyncStatus()` que já existiam.
  **Validado com dado real**: chamada direta a `opa_sync_status` no backend
  em produção confirma `lock_busy=False` (probe funcionando contra o
  Postgres real, diferente do `None` visto nos testes em SQLite) com nenhum
  import em andamento no momento.
  Testes novos: 8 em `test_opa_ingestion.py` (helpers de lock/run ativa e
  mensagem dinâmica) e 4 em `test_opa_scheduler.py` (recálculo de
  `next_allowed_at` no fim da execução, sucesso e falha; status do endpoint
  com/sem run ativa). Suíte completa — **1225 passed**, mesmas 26 falhas
  pré-existentes não relacionadas (`ai`/`ai_governance`, duplicadas pelo
  artefato `tests/tests/`), zero regressão nova. Frontend: build + `tsc` sem
  erro. Backend e frontend rebuildados e reiniciados. Nenhuma migration —
  mudança 100% aditiva em código, sem alteração de schema, TMR ou lock.
- **SGP Suporte / OPA Suite — formatação de tempo sem perda de precisão e
  filtro de período por data de abertura ou encerramento**: dois ajustes
  independentes.
  1. Novo helper `frontend/lib/format-duration.ts` (`secondsLabel`) substitui
     a exibição antiga que arredondava qualquer valor acima de 60s pro
     minuto cheio (TMR pequeno tipo 89s virava só "1 min", perdendo
     precisão). Formato novo: `< 60s → "14 s"`, `< 1h → "1 min 29 s"`,
     `>= 1h → "1 h 02 min 15 s"`. Nenhum cálculo/persistência em segundos foi
     alterado — só a camada de exibição (TMA, TMR humano, TMR geral, 1ª
     resposta). Aplicado em `opa-module-components.tsx` (cards, tabela de
     motivos, detalhe do atendimento, painel individual).
  2. Novo parâmetro `date_basis` (`opened_at` padrão, ou `closed_at`) em
     `apply_opa_attendance_filters` (`opa_filters.py`), propagado pros 6
     endpoints do módulo: `/opa/overview`, `/opa/attendances`,
     `/opa/attendants/{id}/summary`, `/opa/breakdowns`, `/opa/filters`,
     `/opa-metrics` (este último monta os bounds manualmente, sem passar
     pelo filtro compartilhado — tratado com uma coluna de data local em vez
     de refatorar o endpoint inteiro). Filtro novo "Data usada" no painel de
     filtros avançados do frontend (Abertura/Encerramento), com badge de
     filtro ativo quando `closed_at` está selecionado. Comportamento padrão
     (`opened_at`) inalterado — mudança 100% aditiva.
     **Validado com dado real de produção**: atendimento `51150`
     (`source_id=6a8d120d48902bf508339458`), aberto 24/08 e encerrado 25/08
     no fuso local — aparece em `date_basis=opened_at` só no filtro de 24/08,
     e em `date_basis=closed_at` só no filtro de 25/08, exatamente o
     critério de aceite.
  Testes novos: `frontend/lib/format-duration.test.ts` (5 casos) e 5 testes
  de `date_basis` em `test_opa_attendance_table.py`. Suíte completa —
  **1214 passed**, mesmas 13 falhas pré-existentes não relacionadas
  (`ai`/`ai_governance`), duplicadas pra 26 pelo artefato conhecido
  `tests/tests/`, zero regressão nova. Frontend: `npm run test` 35/35,
  build + `tsc` sem erro. Backend e frontend reiniciados/rebuildados com o
  código novo.
- **SGP Suporte / OPA Suite — TMR geral (`tmr_all_responses_seconds`)
  adicionado ao lado do TMR humano, sem substituí-lo**: `tmr_seconds`
  continua sendo o TMR só-humano, intocado — critério de aceite validado nos
  testes (mesmos valores de antes). Coluna nova nullable
  `tmr_all_responses_seconds` (migration `20260825_0074`), calculada na
  ingestão (`_all_response_metrics` em `opa_ingestion.py`) reaproveitando as
  mesmas mensagens já buscadas pro TMR humano — zero chamada nova à API.
  Conta resposta de **qualquer** atendente (bot ou humano) como válida, ao
  contrário do TMR humano que ignora bot. Serve pra comparar com o painel
  oficial do OPA, que provavelmente inclui bot (hipótese da auditoria).
  Exposto nos 5 endpoints pedidos: `/opa/overview` (com comparação de
  período), `/opa/attendants/{id}/summary`, `/opa/attendances` (lista),
  `/opa/attendances/{id}` (detalhe — TMR não aparecia lá antes, os dois
  passaram a aparecer), `/opa-metrics` (geral + por atendente/motivo).
  Frontend: card "TMR geral" ao lado de "TMR humano" na Visão Geral e no
  painel individual, coluna "TMR geral" na tabela de motivos, par TMR
  humano/geral no bloco "Datas e duração" do detalhe do atendimento — sem
  redesign, mesmos componentes.
  **Validado com dado real de produção** (mesmo atendimento de handoff
  bot→humano já usado nas fases anteriores): TMR humano 3735s vs TMR geral
  14s — confirma na prática que TMR geral fica bem menor quando o bot
  responde rápido antes do humano, exatamente o padrão que explicaria a
  divergência com o painel oficial.
  Testes novos: `test_opa_ingestion.py` (2, incluindo o caso do critério de
  aceite "TMR geral < TMR humano") e `test_opa_attendance_table.py` (2).
  Suíte completa — **1209 passed**, mesmas 13 falhas pré-existentes não
  relacionadas (`ai`/`ai_governance`/`operations`), zero regressão nova.
  Frontend: build + `tsc` sem erro. Backend e frontend
  reiniciados/rebuildados; migration aplicada no Postgres real.
  **`support_opa_sync_enabled` já está `true`** (o usuário ligou) — única
  decisão pendente da auditoria que resta é confirmar a fórmula oficial de
  TMR do painel do OPA (agora com TMR geral disponível pra comparar).
- **SGP Suporte / OPA Suite — estado consolidado**: Fases 1 a 3C concluídas
  (diagnóstico, visão geral expandida, painel individual por atendente,
  timeline por atendimento) — plano completo em
  `docs/plano-analise-opa-suite-atendimentos.md`. Auditoria de divergência
  com o painel oficial do OPA em
  `docs/auditoria-divergencia-opa-suite-2026-08-25.md`, com 3 causas raiz já
  corrigidas (fuso `America/Porto_Velho` em todo filtro de período,
  sincronização de clientes sem limite artificial — era 50.000, base real
  tem 176k+ —, `TopRecurringCustomers` nunca mostra código bruto como nome).
  Fase 4A (UX/visual) **implementada em três rodadas** (reagrupamento →
  composição/identidade visual → refino de espaço e densidade) — guia em
  `docs/plano-ux-visual-sgp-suporte-fase-4a.md`, detalhes nos itens acima. O
  visual ainda não está fechado: ver "Frentes em andamento".
  **Backfill de nome de cliente: não é mais pendência.** Auditoria em
  2026-08-26 contra o banco real confirmou **0** atendimentos com
  `customer_id` preenchido e sem `customer_name` — o teto de 50.000 em
  `list_clients` (corrigido na auditoria anterior) já resolveu isso; a
  sincronização de dimensão de clientes hoje cobre 177k+ registros. Os
  8.276 atendimentos sem nome de cliente na base atual **não têm
  `customer_id` nenhum** (canal anônimo/PABX) — não há nome pra buscar, não
  é backfill, é ausência de dado na origem. Pendências gerais restantes:
  expor `first_response_at`/TMR em `/opa/breakdowns`; texto completo de
  mensagem (precisa da permissão granular `support:view_conversation`,
  ainda não implementada); análise de conversa por IA (Fase 6, bloqueada
  por decisão de infra/autorização); distribuição por etiqueta (bloqueada
  por SQLite nos testes); FCR (sem dado confiável).
- **Agendamento**: modernização da tela (filtros padronizados), drill de
  reagendamento por técnico/operador, correção de contagem de reagendamento
  (contava O.S. do técnico, não reagendamentos gerados por ele).
- **Gestão Integrada / Calendário**: correções de sincronia entre o calendário e a
  matriz de casos (bolinha de pendência, casos resolvidos pela matriz vs sozinhos,
  escala 12x36 intrínseca ao modelo de equipe, geração diária cobrindo mais que só
  "ontem").
- **SLA**: painel de gauges por Tipo Geral.

## Frentes em andamento / conhecidas

- **4 PRs abertas aguardando merge** (nenhuma na VM ainda):
  `claude/suporte-sync-backfill-madrugada` (import em background + backfill de
  meses + fix de campo numérico + throttle de sincronização de dimensões do
  OPA Suite), `claude/auditoria-performance-p0` (fix do cache do dashboard +
  ANALYZE + poda de rascunhos) e `claude/auditoria-performance-p1` (IXC
  backfill em background + N+1 + query duplicada + pool de conexão) — mais
  esta própria PR de docs (`claude/status-md-2026-08-27`). **Depois do
  merge/deploy da P0, faltam 2 comandos manuais na VM** (ação em banco, não
  fazem parte do `docker compose up`):
  `ANALYZE service_orders, collaborator_scores, operations_orders,
  scheduling_orders, scheduling_events, management_cases;` e
  `docker exec opr-gamification-backend python -m scripts.enable_draft_retention`.
- **Otimização da tela de leitura do SGP Suporte/OPA Suite — concluída, com
  uma parte deliberadamente descartada**: `GET /support/opa/overview` foi de
  ~930ms pra ~480-570ms (ver entrada acima em "O que foi feito recentemente").
  **Combinar as 8-9 consultas separadas de `expanded_overview` num recorte
  físico só foi avaliado e descartado por decisão explícita do usuário**: só
  é possível com recursos exclusivos do Postgres (tabela temporária ou
  `GROUPING SETS`) - o SQLite usado pela suíte de testes automatizados não
  suporta nenhum dos dois (confirmado: SQLite 3.46.1 rejeita `GROUPING SETS`
  com erro de sintaxe). Isso significaria um trecho de código Postgres-only
  sem NENHUMA cobertura de teste automatizado dali pra frente - só validável
  manualmente contra a base real a cada mudança. Ganho estimado (~480ms →
  ~300-350ms) não compensou perder a rede de segurança dos testes. **Não
  reabrir essa discussão sem uma mudança real na composição da suíte de
  testes** (ex.: rodar os testes deste módulo contra Postgres em vez de
  SQLite) que resolva a lacuna de cobertura pela raiz. Verificar se
  `GET /support/opa-metrics` duplica `/opa/overview` continua em aberto (não
  é a mesma limitação - não depende de recurso Postgres-only, só precisa
  checar o frontend antes).
- **Menu lateral único — código pronto no histórico, fora de produção por
  decisão do usuário**: revertido antes do deploy (ver acima). Reativar quando
  o usuário pedir: reverter o commit de revert numa branch nova.
- **SGP Suporte — visual ainda está cru e deve continuar evoluindo**: as 3 rodadas
  da Fase 4A melhoraram estrutura, composição e densidade, mas o resultado ainda não
  é o de um painel operacional maduro. **Toda evolução futura do módulo deve incluir
  melhoria visual, não só função** — isso agora é norma permanente, registrada na
  seção 10 de `docs/normas-qualidade-dados-metricas.md` (evitar aparência de
  protótipo, grid infinito de cards iguais e espaço branco sem função; preservar
  responsividade; validar visualmente de verdade a cada mexida no frontend).
  Limitação conhecida das últimas rodadas: a validação visual foi feita por inspeção
  de estrutura/medidas no navegador real, sem screenshot — refino fino de cor,
  alinhamento e espaçamento depende de alguém abrir `/suporte` e apontar o que
  incomoda.
- **SGP Suporte / OPA Suite — sincronização automática LIGADA**
  (`support_opa_sync_enabled=true`) — o módulo agora se atualiza sozinho, não
  é mais só retrato do último import manual. Confirmado no banco em
  2026-08-25. Como ciclos com busca de mensagens (TMR) podem passar do
  intervalo configurado, uma importação manual pode encontrar o lock
  ocupado por ela — isso agora aparece com status claro em
  `/opa-sync-status` e mensagem amigável no 409 (ver item acima), não é bug.
- **Divergência de TMR com o painel oficial do OPA — última decisão em
  aberto da auditoria**: agora com TMR humano E TMR geral disponíveis (ver
  acima) pra comparar contra o painel oficial e descobrir qual fórmula ele
  usa. Ver `docs/auditoria-divergencia-opa-suite-2026-08-25.md`.
- `/opa/breakdowns` (usado pela aba Atendentes do frontend) ainda NÃO traz
  TMR (humano nem geral) agregado por atendente/departamento —
  `/opa/overview`, `/opa-metrics` e o summary por atendente já trazem.
- Documentos `docs/proposta-filter-contract-v1.md` e
  `docs/plano-plataforma-inteligencia-operacional.md` descrevem trabalho de
  plataforma ainda em curso (contrato de filtro único entre módulos, UNI
  Intelligence) — consultar antes de mexer em filtros ou cockpit.

## Próximos passos sugeridos

- Mergear as 4 PRs abertas (ver "Frentes em andamento") e rodar os 2 comandos
  manuais na VM depois do deploy da P0.
- Verificar se `GET /support/opa-metrics` duplica o núcleo do que
  `/opa/overview` já calcula (checar o frontend primeiro) — único item de
  performance do SGP Suporte/OPA Suite ainda em aberto; a otimização de
  `/opa/overview` está concluída (ver "Frentes em andamento" pro item
  descartado por decisão do usuário, e o motivo).
- P2 da auditoria de performance geral, ainda não desenhada: cache de curto prazo em
  `GET /operations/overview` e `GET /support/opa/overview` — precisa incluir o
  escopo por usuário (gestor regional) na chave do cache, não só os filtros da
  URL, senão risco de vazar dado de uma regional pra gestor de outra. Também
  ficaram de fora desta rodada (avaliados, não esquecidos):
  `POST /operations/imports` e `POST /operations/responsible-directory/sync`
  ainda rodam síncronos dentro da requisição HTTP.
- Comparar TMR humano e TMR geral (ambos disponíveis agora) contra o painel
  oficial do OPA pra descobrir qual fórmula ele usa — última decisão em
  aberto da auditoria de divergência.
- Definir com o usuário se/quando avançar pra texto completo de mensagem
  (exige a permissão granular `support:view_conversation`, ainda não
  implementada) e/ou análise de conversa por IA (Fase 6, bloqueada por
  decisão de infra/autorização).
- Decidir se compensa fazer backfill do TMR geral histórico — cobertura agora
  visível na própria UI (Bloco B1, item acima), medida em 2026-08-26 contra o
  banco real: **45.060 de 55.925** atendimentos (81%) ainda sem
  `tmr_all_responses_seconds`, cobertura cai a 0% antes de 2026-08-20 (corte
  exato do dia em que o campo entrou em produção — é o comportamento esperado
  de "só dado novo", não bug). Classificação bot/humano já está quase
  completa (190 de 55.925 sem classificar, 0,3%) — não precisa de backfill.
  Custo do backfill de TMR: 1 chamada extra à API do OPA Suite por
  atendimento — hoje descartado por custo, mas o número
  real agora permite decidir com base em dado, não estimativa.
- Seguir consolidando o contrato de filtros único (`proposta-filter-contract-v1.md`)
  entre Operação Analítica, Agendamento e Gestão — agora com a seção 3 de
  `docs/normas-qualidade-dados-metricas.md` como norma de referência.
- Continuar o refino visual do SGP Suporte (ver "Frentes em andamento"): a tela ainda
  está crua e cada rodada seguinte deve avançar em clareza, densidade e hierarquia,
  seguindo a seção 10 da norma.
- Aplicar o checklist da seção 9 da norma nas próximas alterações de KPI, filtro ou
  importação — e, quando algum endpoint antigo violar a norma (caso conhecido:
  `/opa-metrics` monta os bounds de data na mão em vez de usar
  `apply_opa_attendance_filters`), decidir se compensa alinhar.

## Scripts/uso pontual (não fazem parte do fluxo automático)

- `backend/scripts/disable_collective_outage_monitor.py`
- `backend/scripts/dismiss_test_cockpit_content.py`

Se algum desses vira rotina permanente, mover a lógica pra dentro do módulo e
remover daqui.
