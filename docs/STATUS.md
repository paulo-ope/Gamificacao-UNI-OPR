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

**2026-08-26** — branch `claude/agendamentos-filtros-kpi-5xdjq1`

## O que foi feito recentemente

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

- Comparar TMR humano e TMR geral (ambos disponíveis agora) contra o painel
  oficial do OPA pra descobrir qual fórmula ele usa — última decisão em
  aberto da auditoria de divergência.
- Definir com o usuário se/quando avançar pra texto completo de mensagem
  (exige a permissão granular `support:view_conversation`, ainda não
  implementada) e/ou análise de conversa por IA (Fase 6, bloqueada por
  decisão de infra/autorização).
- Decidir se compensa fazer backfill do TMR geral histórico — medido em
  2026-08-26 contra o banco real: **45.009 de 55.700** atendimentos (81%)
  ainda sem `tmr_all_responses_seconds`, cobertura cai a 0% antes de
  2026-08-20 (corte exato do dia em que o campo entrou em produção — é o
  comportamento esperado de "só dado novo", não bug). Classificação
  bot/humano já está quase completa (190 de 55.700 sem classificar, 0,3%) —
  não precisa de backfill. Custo do backfill de TMR: 1 chamada extra à API
  do OPA Suite por atendimento — hoje descartado por custo, mas o número
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
