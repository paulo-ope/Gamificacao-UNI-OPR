# Auditoria técnica geral — 2026-09-15

Auditoria solicitada pelo usuário: varredura profunda do sistema (backend FastAPI +
frontend Next.js + banco Postgres) em busca de bugs, código morto, inconsistências,
riscos de segurança, performance, testes ausentes e oportunidades de produto/IA.
Executada por 7 investigações paralelas, cada uma lendo código real e citando
`arquivo:linha`. Nenhuma alteração foi feita no sistema nesta rodada — é só
diagnóstico, para decisão do usuário.

Convenção de confiança usada em todo o documento:
**CONFIRMADO** (código prova o problema) · **FORTE EVIDÊNCIA** (múltiplos indícios,
falta uma confirmação) · **HIPÓTESE** (merece investigação, não é bug).

---

## 1. Mapa do sistema

Monorepo com duas camadas convivendo:

- **Núcleo legado "Gamificação Operacional"** (o sistema original): cálculo/fechamento
  de pontuação e bônus de técnicos por O.S., holerite, portal do colaborador.
  `backend/app/api/routes/*.py` (calculation_runs, scoring, point_balance, rules,
  leadership, collaborators, invites, portal, audit, dashboard, gamification,
  settings, service_orders, imports, notifications, auth), modelos em
  `backend/app/models.py` (875 linhas) e schemas em `backend/app/schemas.py`
  (1815 linhas) — monolíticos.
- **Módulos "UNI Workspace"** (mais novos, modulares): `backend/app/modules/{admin,
  ai, ai_governance, intelligence, localiza, management, mcp_connector, operations,
  scheduling, support, workspace}`, cada um com seu próprio `router.py`/`models.py`/
  `queries.py`/`schemas.py`.
- **Banco**: PostgreSQL, 97 migrations Alembic, cadeia íntegra (uma raiz, uma head,
  sem branch quebrada).
- **Frontend**: Next.js/TypeScript, uma tela por módulo (`frontend/app/{operacao,
  visao-geral (overview), suporte, agendamento, gestao, gamificacao, intelligence,
  localiza, admin}`), chamadas centralizadas em `frontend/lib/{api.ts,
  operations-api.ts, scheduling-api.ts, ...}`.
- **IA/MCP**: `backend/app/modules/mcp_connector/server.py` (35 tools, OAuth remoto)
  + `backend/app/modules/ai` (`/api/ai/*`, reaproveitado pelo MCP) + `ai_governance`
  (controle de campo/permissão) + um segundo servidor **stdio** independente em
  `mcp-server/opr_analitica_mcp.py` (26 tools, defasado).
- **Autenticação**: JWT HS256 artesanal (`app/core/security.py`), PBKDF2-SHA256 para
  senha, permissões por perfil (`ROLE_PERMISSIONS`) + overrides por usuário.
- **Integrações externas**: IXC (O.S., tickets, colaboradores), OPA Suite (SGP
  Suporte), CPK, upvalue — todas com scheduler próprio.

---

## 2. Top melhorias

### [P0] Tela de Administração quebra para perfis com permissões `admin:*` — família de permissão errada — ✅ CORRIGIDO EM 2026-09-17
**Tipo:** Bug · Segurança
**Local:** `frontend/app/admin/page.tsx:109` (gate `admin:users:read`) vs.
`backend/app/api/routes/users.py:69-71` (exige `users:manage`); trava
"último administrador" em `user_permissions_service.py:87-99` (só cobre
`admin:users:write`).
**O que existe hoje:** o catálogo do módulo Admin declara uma família própria de
permissões (`admin:users:read/write/delete`, `admin:audit:read`) que **não é a
mesma** usada pelas rotas reais (`users:manage`, `audit:read`, do núcleo legado).
**Evidência:** a tela usa `admin:users:read` para decidir se carrega `/admin`, mas
`loadAdminData()` chama `api.users()` → `GET /users`, protegido por `users:manage`.
`admin:users:delete` é declarada e nunca é exigida por nenhuma rota real (permissão
morta). A trava que impede remover o último perfil de administração cobre
`admin:users:write`, não `users:manage`.
**Problema:** um perfil de acesso montado só com as permissões `admin:*` (exatamente
o que o próprio catálogo sugere ser suficiente) faz a tela de Administração inteira
falhar ao carregar, e nada impede alguém de remover `users:manage` de todos os
perfis pela própria tela sem aviso.
**Impacto:** perda de acesso à gestão de usuários para um perfil "corretamente"
configurado; no pior caso, lockout completo (ninguém mais consegue criar/resetar
conta).
**Causa provável:** as duas famílias de permissão foram criadas em momentos/módulos
diferentes e nunca foram unificadas.
**Melhoria proposta:** unificar em uma única família de permissão (migrar `users.py`
para exigir `admin:users:*`, ou aposentar `admin:users:*` e usar só `users:manage`
em todo lugar, incluindo a trava anti-lockout).
**Esforço:** Médio. **Risco da alteração:** Médio (mexe em autorização). **Confiança:** Confirmado.

**Status:** Corrigido em 2026-09-17 — ver `docs/STATUS.md` para o detalhe completo.
Resumo: `require_any_permission()` novo em `core/security.py` faz `/users`,
`/invites` e `/access-requests` aceitarem `users:manage` OU o
`admin:users:read/write/delete` correspondente (granularidade preservada — `read`
não libera escrita, `write` não libera exclusão), e as duas travas anti-lockout
(`admin/router.py` e `admin/user_permissions_service.py`) passaram a proteger as
duas permissões, não só `admin:users:write`. 9 testes novos em
`tests/test_users_admin_permission_fallback.py`.

---

### [P0] Endpoints de rede (`/operations/network/*`) não aplicam o escopo regional do usuário — ✅ CORRIGIDO EM 2026-09-17
**Tipo:** Segurança
**Local:** `backend/app/modules/operations/router.py:1402-1666` (logins, ONU signal,
offline-clusters, busca, incident-analysis, coordinate-quality) →
`login_geo_clusters.py`, `onu_signal_snapshot.py`, `login_search.py` — nenhuma dessas
funções recebe `user` nem aplica `effective_managed_regionals`.
**O que existe hoje:** o resto do módulo `operations` aplica corretamente o escopo
regional do gestor em `_dimension_conditions` (`queries.py:265-282`, com comentário
explícito de que "nunca amplia o acesso"). A família "network" do mesmo módulo não
segue essa regra.
**Evidência:** as funções chamadas por essas rotas não têm parâmetro `user`; o filtro
de regional vem só do que o cliente manda na query string.
**Problema:** um gestor regional (`regional_manager_viewer`/`base_manager`), que tem
`operations:read` e é corretamente restrito no resto do módulo, pode consultar
status de login, geolocalização e telemetria óptica de **qualquer regional**, não só
a sua.
**Impacto:** vazamento de dado operacional de outras regionais para quem não deveria
vê-lo.
**Melhoria proposta:** aplicar `effective_managed_regionals(user.managed_regional,
user.managed_regionals)` como condição obrigatória nessas 6+ funções, igual ao resto
do módulo.
**Esforço:** Baixo-Médio. **Risco da alteração:** Baixo. **Confiança:** Confirmado.

**Status:** Corrigido em 2026-09-17 — escopo real acabou sendo maior que o descrito
acima: **11 funções em 5 arquivos** (`login_geo_clusters.py`, `onu_signal_snapshot.py`,
`login_search.py`, `login_aggregate.py`, `coordinate_quality.py`), chamadas não só por
`/operations/network/*` mas também por `/api/ai/infra/*` (11 rotas que a auditoria não
tinha listado) e pelas tools MCP correspondentes - todos os call sites (34 no total)
agora passam `user` explicitamente. Novo `regional_scope_or_deny(user)` em
`services/regional.py` centraliza a regra (mesmo critério de
`operations.queries._dimension_conditions`); `user=None` é acesso irrestrito
deliberado, só para os 2 monitores de background do `intelligence` que varrem o
sistema inteiro sem usuário associado. Caso mais delicado: `login_timeseries` roda
sobre uma tabela sem coluna de regional própria - precisou de uma segunda versão da
query SQL bruta com JOIN, ativada só quando o escopo realmente restringe. 11 testes
novos em `tests/test_network_regional_scope.py`; suíte ampla (154+ testes) sem
nenhuma regressão nova.

---

### [P0] Governança de campo da IA não tem efeito na chamada padrão de `opr_order_details`/`opr_search_orders`
**Tipo:** Segurança · API/MCP
**Local:** `backend/app/modules/mcp_connector/server.py:769,809-812` (tool
`opr_order_details`); `ai/router.py:164-174,227-233`
(`resolve_ai_search_output_fields`/`resolve_ai_order_details_output_fields`).
**O que existe hoje:** existe uma tabela (`AiFieldPermission`) e uma tela de
Administração para desligar campos sensíveis da IA (ex. `customer_name`).
**Evidência:** o filtro por `policy.selectable_fields` só é aplicado quando
`response_mode="summary"`. O modo padrão da tool é `"full"`, e com `fields=None`
(o uso mais natural) `output_fields` fica `None`, e nesse caso **nenhum filtro é
aplicado** — `OperationOrderDetailOut.model_validate(order).model_dump()` sai
inteiro.
**Problema:** um administrador que desliga `customer_name` (ou outro campo) na tela
de governança da IA não tem efeito algum sobre a chamada mais comum dessas duas
tools — a restrição só funciona se o cliente MCP explicitamente pedir
`response_mode="summary"`.
**Impacto:** falsa sensação de controle: a governança existe, mas não protege o
caminho padrão.
**Melhoria proposta:** aplicar `enforce_requested_fields`/filtro por
`policy.selectable_fields` também no modo `"full"` (a menos que seja
deliberadamente "modo administrador sem filtro", caso em que precisa de permissão
própria e não pode ser o default).
**Esforço:** Médio. **Risco da alteração:** Médio (pode quebrar clientes MCP que
dependem do payload completo hoje — avisar/versionar). **Confiança:** Confirmado.

---

### [P0] Fechamento manual de ciclo (`/calculation-runs/calculate`) não tem lock nem trava de duplicata — já causou incidente real em produção
**Tipo:** Bug · Dados
**Local:** `backend/app/api/routes/calculation_runs.py:93-123` →
`app/services/calculation.py:158-244` (`calculate_scores`); poda de duplicatas em
`calculation.py:851-886` (`prune_superseded_drafts`), desligada por padrão
(`DRAFT_RETENTION_ENABLED_SETTING="false"`) e só chamada pelo caminho automático.
**O que existe hoje:** o **aprovar/pagar** de um ciclo já tem lock (`SELECT ... FOR
UPDATE`, `calculation_runs.py:349`, com comentário citando o incidente #1601). A
**criação** de um rascunho novo (`/calculate`) não tem proteção equivalente: sem
lock, sem `UniqueConstraint(reference_month, reference_year, regional)`.
**Evidência:** o próprio comentário do código (`calculation.py:854-858`) admite que
essa omissão já gerou **1.106 fechamentos duplicados e 225 mil linhas de
`collaborator_scores`** em produção.
**Impacto:** inchaço de dados já comprovado; risco de um operador ver o rascunho
"errado" (não o mais recente) se a poda automática não rodar.
**Melhoria proposta:** adicionar lock (ou `UniqueConstraint` com tratamento de
conflito) na criação do rascunho, e/ou ligar `DRAFT_RETENTION_ENABLED_SETTING` por
padrão com chamada também no caminho manual.
**Esforço:** Médio. **Risco da alteração:** Médio (mexe no caminho de cálculo
financeiro — testar bem). **Confiança:** Confirmado (incidente já documentado no
próprio código).

---

### [P1] FKs sem `ondelete` quebram exclusão de colaborador em cenários não cobertos pelo soft-delete
**Tipo:** Bug · Dados
**Local:** `backend/app/models.py:723` (`LeadershipProfile.collaborator_id`),
`:645-647` (`CollaboratorPointBalance.collaborator_id`), `:666`
(`PointBalanceEntry.collaborator_id`) → todas sem `ondelete`, apontando para
`collaborators.id`. Tratamento existente em
`backend/app/api/routes/collaborators.py:98-126`.
**O que existe hoje:** a rota de exclusão de colaborador já sabe que
`CollaboratorScore` bloqueia o delete e faz soft-delete quando há
`ServiceOrder`/`CollaboratorScore` vinculada (comentário próprio já documenta isso).
**Problema:** essa checagem não cobre `LeadershipProfile`, `CollaboratorPointBalance`
nem `PointBalanceEntry`. Um colaborador sem O.S./pontuação, mas cadastrado como
líder ou com saldo de garantia, ainda cai no `db.delete()` direto e quebra com
`IntegrityError` não tratado.
**Impacto:** erro 500 ao tentar excluir um colaborador nesse estado específico.
**Melhoria proposta:** estender a checagem de "tem vínculo, faz soft-delete" para
essas 3 tabelas, ou adicionar `ondelete="RESTRICT"` explícito + mensagem amigável.
**Esforço:** Baixo. **Risco:** Baixo. **Confiança:** Confirmado.

---

### [P1] Campos financeiros/pontuação em `Float` — risco de arredondamento acumulado
**Tipo:** Dados · Arquitetura
**Local:** `backend/app/models.py:618-633` (`CollaboratorScore`: `gross_points`,
`penalty_points`, `net_points`, `health_multiplier`, `final_points`,
`estimated_payment`, `balance_adjustment_points`, `balance_after`), `:594`
(`CalculationRun.point_value`), `:668` (`PointBalanceEntry.points`).
**Problema:** valores monetários e de pontuação acumulados ao longo de vários
períodos usam `Float` (IEEE-754), suscetível a erro de arredondamento cumulativo.
**Evidência de impacto real:** `docs/STATUS.md` (2026-09-14) já registra uma
divergência de **R$ 1.291,08 em 37 pessoas** num rascunho, num incidente da mesma
classe (conversão de multiplicador).
**Melhoria proposta:** migrar para `Numeric`/`Integer` (centavos) nos campos
monetários; avaliar caso a caso os de pontuação.
**Esforço:** Alto (migração de dado + todo o pipeline de cálculo). **Risco:** Alto
(é o coração financeiro do sistema — precisa de plano próprio, não é ajuste
pontual). **Confiança:** Confirmado (Float) + Forte evidência (causa raiz do
incidente de R$1.291,08 documentado).

---

### [P1] `intelligence`: contador de confirmação de alerta (`confirm_cycles`) nunca reseta — quebra a garantia de "hits consecutivos"
**Tipo:** Bug
**Local:** `backend/app/modules/intelligence/monitors/rules_engine.py:139-142`
(`_reset_hits`, definida) — sem nenhum call site em todo o módulo.
**Problema:** o parâmetro `confirm_cycles` de uma regra promete "só alerta depois de
N ciclos **consecutivos**" — mas como o contador nunca é zerado quando a condição
desaparece por um ciclo, hits não-consecutivos continuam somando e disparam alerta
como se fossem consecutivos.
**Impacto:** taxa de falso positivo mais alta que o configurado nas regras de
monitoramento operacional (SLA, outage coletivo etc.).
**Melhoria proposta:** chamar `_reset_hits` quando a condição da regra não bate no
ciclo atual.
**Esforço:** Baixo. **Risco:** Baixo. **Confiança:** Confirmado.

---

### [P1] `management/cases.py` reimplementa a regra de meta por dia da semana com divergência ADMITIDA no próprio código
**Tipo:** Bug · Arquitetura
**Local:** `backend/app/modules/management/cases.py:558-573` (`_rule_for_day`) vs.
`backend/app/modules/operations/services.py:121-139` (`_target_rule`/
`classify_daily_performance`, a fonte "oficial" já usada pelo Calendário).
**Problema:** a engine de casos de não-conformidade recalcula a mesma regra de meta
diária de um jeito próprio, e o comentário do código já admite que o fallback de
fim de semana diverge da implementação original.
**Impacto:** um caso pode ser aberto (ou deixar de ser aberto) por "abaixo da meta"
usando uma regra diferente da que a própria tela do Calendário usa para mostrar a
mesma meta — divergência de dado percebida pelo usuário sem explicação.
**Melhoria proposta:** management passar a chamar `operations.services._target_rule`
em vez de reimplementar.
**Esforço:** Médio. **Risco:** Médio (motor de geração automática de casos —
testar contra o histórico antes de trocar). **Confiança:** Confirmado.

---

### [P1] Superfície MCP (a "principal", por design do próprio código) não gera nenhum log de auditoria
**Tipo:** Observabilidade · API/MCP
**Local:** `backend/app/modules/mcp_connector/server.py` — `record_ai_access`
(definida em `ai_governance/audit.py:29-63`, chamada 17× em `ai/router.py` e 2× em
`operations/router.py`) tem **zero ocorrências** no arquivo do conector MCP. Só 2
das 35 tools (`opr_aggregate_orders`, `opr_orders_timeseries`) têm qualquer
`logger.*`.
**Problema:** a tabela de auditoria de acesso de IA (`AiAccessAuditLog`) existe e
funciona para as rotas HTTP, mas fica cega para o canal que o próprio código chama
de superfície principal.
**Impacto:** impossível responder "quem perguntou o quê à IA, quando, com que
filtro" para 33 das 35 tools — inclusive a única de escrita
(`opr_publish_cockpit_content`).
**Melhoria proposta:** chamar `record_ai_access` em cada tool do conector MCP, no
mesmo padrão já usado por `ai/router.py`.
**Esforço:** Médio (repetitivo, mas direto). **Risco:** Baixo. **Confiança:**
Confirmado.

---

### [P1] Importação retroativa de O.S. (`/operations/imports/backfill`) sem teto de dias nem trava de concorrência
**Tipo:** Segurança · Performance
**Local:** `backend/app/modules/operations/backfill.py:27-49`
(`create_backfill_job`) vs. o equivalente em Suporte,
`backend/app/modules/support/router.py:807-808` (`opa_import_lock_busy`) +
`opa_filters.py:23-27` (teto de 31 dias, `validate_opa_period`).
**Problema:** o backfill de `operations` só valida `date_from <= date_to` dentro do
ano corrente — sem limite de tamanho de janela nem checagem de "já tem um backfill
rodando". Hoje (15/09) já dá para pedir ~8,5 meses num único job em background.
**Impacto:** uma requisição (por engano ou abuso) pode disparar uma importação
enorme, competindo por recursos com o sync automático, sem nenhuma trava.
**Melhoria proposta:** aplicar o mesmo padrão do Suporte: teto de dias por
requisição + lock de "só um backfill ativo por vez".
**Esforço:** Baixo. **Risco:** Baixo. **Confiança:** Confirmado.

---

### [P1] Divergência de fuso horário (UTC vs. Porto Velho) entre rotas de leitura e o motor de fechamento
**Tipo:** Bug
**Local:** `backend/app/api/routes/collaborators.py:166`, `scoring.py:369,445,462`
— usam `datetime.now(timezone.utc)` como fallback de mês/ano; a fonte canônica é
`current_reference_period()` (`app/services/calculation_closure.py:24-34`, Porto
Velho, UTC-4), criada especificamente para evitar esse tipo de bug (comentário na
linha 311 cita um "achado real" anterior).
**Problema:** nas últimas ~4h de qualquer mês, essas 3 rotas de leitura podem
mostrar dado do mês "seguinte" (já virado em UTC) enquanto o motor de fechamento
ainda considera o mês anterior como corrente.
**Impacto:** tela mostrando período diferente do que está realmente sendo fechado,
numa janela pequena mas real, todo mês.
**Melhoria proposta:** trocar os 3 fallbacks para `current_reference_period()`.
**Esforço:** Baixo. **Risco:** Baixo. **Confiança:** Forte evidência.

---

### [P1] Testes ausentes em código de alto risco do núcleo legado
**Tipo:** Testes
**Local:** `backend/app/api/routes/service_orders.py` (244 linhas, inclui
`POST /delete-period` **destrutivo** e `POST /seed`), `imports.py` (198 linhas,
integração externa com lock/timeout), `rules.py` (237 linhas, motor de
validação de regras de pontuação/penalidade) — **zero testes** confirmados
para os três. `auth.py`: `conftest.py:95-99` sobrescreve `get_current_user`
globalmente, então o fluxo real de `/auth/login` nunca é exercitado via HTTP em
nenhum teste.
**Impacto:** a operação mais destrutiva do sistema (`delete-period`), a integração
externa com mais efeito colateral, e o motor que alimenta o cálculo de pontuação de
todo mundo não têm rede de segurança nenhuma.
**Melhoria proposta:** priorizar teste para `service_orders.py` (destrutivo) →
`imports.py` (integração externa) → `rules.py` (motor de cálculo) → `auth.py`
(login real via HTTP, não só override).
**Esforço:** Médio. **Risco:** Baixo (só adiciona teste). **Confiança:** Confirmado.

---

### [P2] N+1 em 3 pontos de ingestão (uma query por registro em vez de lote)
**Tipo:** Performance
**Local:** `backend/app/modules/operations/ixc_ingestion.py:533-542` (1 query por
O.S.), `backend/app/modules/support/ixc_ticket_ingestion.py:319-349` (2 queries por
ticket), `backend/app/modules/support/opa_ingestion.py:988-1051` (2 queries por
atendimento) — todas dentro de `for record in records:` verificando existência
antes de inserir/atualizar.
**Melhoria proposta:** pré-carregar os IDs existentes com um único `SELECT ... WHERE
source_id IN (...)` antes do loop.
**Esforço:** Médio. **Risco:** Baixo-Médio (mexe em pipeline de sync que roda
sozinho — testar bem contra volume real). **Confiança:** Confirmado.

---

### [P2] Divergência de convenção de backlog entre `/overview` e `regional_matrix`/`openings_analytics` — já conhecida, ainda sem decisão
**Tipo:** Arquitetura · Dados
**Local:** `backend/app/modules/operations/queries.py:233-243`
(`_opening_filters`/`_backlog_filters`, zeram `responsibles`/`team_models`) usados
em `regional_matrix` (l.784) e `openings_analytics` (l.1865); `overview()`
(l.606-636) calcula o mesmo backlog com o filtro **completo**.
**Impacto:** o número de "backlog" pode divergir entre a Visão Geral e o quadro por
regional/aberturas, dependendo se modelo de equipe/responsável está filtrado — já
registrado em `docs/STATUS.md` como decisão pendente do usuário, confirmado ainda
presente no código de hoje.
**Melhoria proposta:** decidir uma convenção única (a proposta já está em
STATUS.md) e alinhar as três funções, travando com teste.
**Esforço:** Médio. **Risco:** Médio (muda número exibido — comunicar). **Confiança:** Confirmado.

---

### [P2] Acoplamento direto entre módulos sem contrato (`scheduling` → ORM de `management`)
**Tipo:** Arquitetura
**Local:** `backend/app/modules/scheduling/metrics.py:23` — `from
app.modules.management.models import ManagementOperationalMember`, consultado
diretamente.
**Impacto:** uma mudança em `ManagementOperationalMember` quebra Agendamento em
silêncio, sem nenhum contrato declarado entre os dois módulos (o projeto tem
`docs/contratos_modulos.md` propondo exatamente evitar isso).
**Melhoria proposta:** expor um contrato/função pública em `management` para o dado
que `scheduling` precisa, em vez de importar o model direto.
**Esforço:** Médio. **Risco:** Baixo. **Confiança:** Confirmado.

---

### [P2] Acessibilidade: combos reutilizados em Gestão/Gamificação sem papel ARIA de lista
**Tipo:** UX
**Local:** `frontend/components/gamification/config-ui.tsx` (`AppCombobox`,
usado nas linhas 214, 324, 667) usa `CommandItem` do primitivo
`frontend/components/ui/command.tsx` (linhas 6-26, sem `role`/`aria-*` por padrão)
**sem** adicionar `role="option"`/`aria-selected` — diferente de
`components/ui/multi-select.tsx:168-169`, que compensa isso manualmente.
**Impacto:** esses seletores não são percebidos como widget de lista por leitor de
tela; dependem só da apresentação visual (check/borda) para indicar seleção.
**Melhoria proposta:** replicar em `config-ui.tsx` o mesmo padrão de
`role`/`aria-selected` já usado em `multi-select.tsx`.
**Esforço:** Baixo. **Risco:** Baixo. **Confiança:** Confirmado.

---

### [P2] Falhas silenciosas na UI deixam filtros travados sem aviso
**Tipo:** UX
**Local:** `frontend/app/suporte/page.tsx:425,432` (`api.supportOpaFilters(...)
.catch(() => undefined)`) e
`frontend/components/management/management-cases-panel.tsx:131,136`
(motivos/toggle de geração automática).
**Impacto:** se a chamada falhar (rede/500), o filtro do Suporte fica vazio e
travado permanentemente sem mensagem nem retry; o painel de Gestão mostra
dropdown/toggle com dado ausente sem indicar que houve erro.
**Melhoria proposta:** tratar erro explicitamente (mensagem + retry), como já é
feito no carregamento crítico dessas mesmas telas.
**Esforço:** Baixo. **Risco:** Baixo. **Confiança:** Confirmado.

---

### [P3] Diversos itens de código morto e dívida técnica menor
Ver seção 7 (Código possivelmente obsoleto) para a lista completa com evidência.
Inclui: funções órfãs (`effective_role_profile`, `_recurrence_identity`), rotas
sem consumidor (10 em `/operations/network/*`, 5 em `support`, `ensure-defaults`,
aliases de "unmapped"), colunas write-only (`workflow_process_id`, 6 colunas de
`SupportOpaAttendance`, `priority`/`channel_id` de `SupportIxcTicket`), `COALESCE()`
neutralizando índice no drill-down do calendário (baixo impacto hoje), senha padrão
fraca do Postgres em `docker-compose.yml`, upload validando só `content_type`
(não magic bytes), rate limiting de login em memória de processo (não escala
horizontalmente), 5 passagens de `.reduce()` em `gamificacao/page.tsx` onde 1
bastaria.

---

## 3. Quick wins (baixo esforço, impacto relevante)

1. Aplicar `effective_managed_regionals` nas 6 funções de `/operations/network/*`
   (P0 de segurança, mudança pequena e localizada).
2. Trocar os 3 fallbacks `datetime.now(timezone.utc)` por
   `current_reference_period()` em `collaborators.py`/`scoring.py`.
3. Chamar `_reset_hits` no lugar certo em `intelligence/monitors/rules_engine.py`.
4. Adicionar teto de dias + lock de concorrência no backfill de `operations`
   (copiar o padrão já pronto do `support`).
5. Estender a checagem de vínculo de `collaborators.py:98-126` para
   `LeadershipProfile`/`CollaboratorPointBalance`/`PointBalanceEntry`.
6. Corrigir `POST /scheduling/technicians/resolve` para exigir `scheduling:manage`
   (hoje só exige `scheduling:read` para uma escrita).
7. Adicionar `role="option"`/`aria-selected` em `config-ui.tsx` (mesmo padrão já
   existente em `multi-select.tsx`).
8. Remover o fallback de senha `opr`/`opr:opr` do Postgres em
   `docker-compose.yml`/`config.py`, ou aplicar a mesma validação "fraco em
   produção → falha" já usada para `AUTH_SECRET_KEY`.

## 4. Melhorias estruturais (planejamento próprio)

1. **Unificar as famílias de permissão de Administração** (`admin:users:*` vs.
   `users:manage`, `admin:audit:read` vs. `audit:read`) — mexe em autorização,
   precisa de plano de migração de perfis existentes.
2. **Migrar campos financeiros/pontuação de `Float` para `Numeric`/`Integer`**
   (`CollaboratorScore`, `CalculationRun.point_value`, `PointBalanceEntry.points`) —
   mudança de schema + todo o pipeline de cálculo, precisa de plano de dados e
   validação contra histórico.
3. **Adicionar lock/unique constraint na criação de rascunho de cálculo**
   (`/calculation-runs/calculate`) e decidir se a poda de duplicatas
   (`prune_superseded_drafts`) deve ficar ligada por padrão.
4. **Instrumentar auditoria (`record_ai_access`) em todas as 35 tools do conector
   MCP** — trabalho repetitivo mas direto, vale um lote próprio.
5. **Resolver a divergência de convenção de backlog** entre `/overview`,
   `regional_matrix` e `openings_analytics` (decisão de produto pendente, já
   identificada, só falta decidir e implementar).
6. **Separar `scheduling` de um acoplamento direto a `management.models`** via um
   contrato explícito.

## 5. Oportunidades de produto

Aproveitando dado e infraestrutura que já existem:

- **Resumo agregado de quedas de login por regional/período** (hoje
  `opr_login_outages` só devolve eventos crus, até 1000 linhas, sem duração
  calculada nem agrupamento) — os dados (status_changed_at, last_disconnected_at,
  regional) já existem, falta só o agregado.
- **Alertas de intelligence mais confiáveis** depois de corrigir o `_reset_hits` —
  hoje a taxa de falso positivo é maior que a configurada, o que provavelmente já
  reduz a confiança de quem usa o cockpit.
- **Unificar a regra de meta diária** entre Calendário (`operations`) e geração de
  casos (`management`) elimina uma fonte de "os números não batem" que o usuário já
  vê hoje sem explicação.
- **Histórico de execução dos monitores de intelligence visível na tela**
  (`GET /monitor-runs` já existe, não tem client no frontend) — daria transparência
  de "os monitores estão rodando?" sem precisar perguntar ao backend.

## 6. IA / MCP

| Módulo | Capacidade atual | API existente | MCP existente | Lacuna | Ferramenta sugerida | Benefício |
|---|---|---|---|---|---|---|
| Operations | Ampla (O.S., login, ONU, backlog, garantia, metas) | Sim, extensa | 24 tools | `opr_login_outages` sem agregação/duração | `opr_login_outages_summary` (group_by regional/causa, duração média) | Evita paginar até 1000 eventos crus + cálculo manual pra "quantas quedas por regional no mês" |
| Operations | `/overview/control-tower` já existe, não exposto | Sim | Não | Torre de controle sem tool | `opr_control_tower` (reaproveita função já pronta) | Baixo esforço, fecha lacuna já anotada em STATUS.md |
| Gamificação | Dashboard/ranking/preview já existem | Sim (`/dashboard/*`) | **0 tools** | Módulo inteiro fora do MCP | `opr_gamification_summary`/`opr_gamification_current_value` (reaproveita `/dashboard/summary`, `/dashboard/gamification-preview`) | IA passa a responder sobre pontuação/ranking sem acesso nenhum hoje |
| Admin | Estrutura de colaboradores/supervisão já existe | Sim (`/admin/people-structure`) | **0 tools** | Módulo inteiro fora do MCP | `opr_people_structure` | Perguntas de governança ("quem supervisiona quem") sem tocar em credencial |
| Localiza | Histórico de solicitação de localização | Sim (`GET /localiza`) | **0 tools** | Dado sensível (GPS de cliente) sem tool nem decisão de sensibilidade | Definir sensibilidade em `field_registry` **antes** de expor | Evita expor coordenada de cliente sem governança |
| Scheduling | Dashboard/backlog do módulo | Sim | Só reagendamento (2 tools) | Dashboard/backlog fora do MCP | Tool de leitura do dashboard de agendamento | Fecha lacuna já anotada em STATUS.md |
| Governança (`ai_governance`) | Tabela `AiFieldPermission` pronta | Sim | Ignorada no modo padrão de 2 tools | Ver achado P0 acima | Aplicar filtro também em `response_mode="full"` | Governança passa a valer no caminho mais usado |
| Observabilidade | `AiAccessAuditLog` + `record_ai_access` prontos | Sim (usado 17× em `ai/router.py`) | **0 chamadas em 33 de 35 tools** | Superfície "principal" sem rastro nenhum | Instrumentar `record_ai_access` em todas as tools MCP | Auditoria de "quem perguntou o quê" volta a existir na superfície mais usada |
| Servidor stdio | Espelha o remoto | — | 26 de 35 tools (defasado) | 9 tools remotas não replicadas | Sincronizar as 9 faltantes ou aposentar o stdio | Evita dois contratos MCP divergentes para o mesmo backend |

## 7. Código possivelmente obsoleto

Confirmado sem consumidor (verificado com grep dos dois lados antes de listar):

- `backend/app/services/leadership_bonus.py:88` `effective_role_profile` — sem
  chamador; existe irmã usada (`effective_role_type`).
- `backend/app/services/scoring_detail.py:367` `_recurrence_identity` — sem
  chamador; substituída por `_recurrence_identity_for_fields`.
- `POST /leadership/role-profiles/ensure-defaults`
  (`app/api/routes/leadership.py:71-78`) — redundante, já chamada internamente por
  `create_leadership_profile`.
- `GET /collaborators/{id}/service-orders-detail`
  (`app/api/routes/collaborators.py:136-194`) — sem chamador HTTP direto (só existe
  para `/scoring-detail` delegar); duplica ~15 parâmetros.
- `GET /scoring-subject-rules/unmapped` e `/diagnoses/unmapped`
  (`app/api/routes/scoring.py:360,453`) — aliases mortos (frontend usa as versões
  `/scoring-matrix/unmapped-*`).
- 10 rotas `GET /operations/network/*`
  (`backend/app/modules/operations/router.py:1422-1666`) — lógica é usada
  internamente pelo MCP (chamada Python direta), mas a rota HTTP em si não tem
  consumidor (nem frontend, nem MCP via HTTP). **Atenção**: mesmas rotas do achado
  de segurança P0 — corrigir o escopo regional em vez de simplesmente apagar, já
  que podem voltar a ter uso.
- `GET /support/opa-metrics`, `/opa/sync-runs/{id}/resume`,
  `/ixc/tickets/city-priorities`, `/ixc/tickets/taxonomy-mappings`,
  `/ixc/analytics/{context,priorities,drivers}` — sem consumidor confirmado.
- `SupportIxcTicket.workflow_process_id/priority/channel_id` e 6 colunas de
  handoff de `SupportOpaAttendance` (`distinct_human_attendant_ids`,
  `first_human_attendant_id`, `last_human_attendant_id`, `human_message_count`,
  `bot_message_count`, `client_message_count`) — gravadas na ingestão, nunca lidas.
- `intelligence`: `acknowledge_alert` (`alerts.py:185-190`) sem rota nem uso;
  colunas `acknowledged_by/at` nunca preenchidas.

## 8. Plano recomendado

**Fase 1 — Correções críticas (P0)**
1. ~~Unificar permissões de Administração (`admin:users:*` ↔ `users:manage`).~~ ✅ Corrigido em 2026-09-17.
2. ~~Escopo regional em `/operations/network/*` (e `/api/ai/infra/*`, achado durante a
   correção).~~ ✅ Corrigido em 2026-09-17.
3. Aplicar governança de campo também no modo `"full"` de
   `opr_order_details`/`opr_search_orders`.
4. Lock/dedup na criação de rascunho de cálculo (`/calculation-runs/calculate`).

**Fase 2 — Quick wins (ver seção 3)**
Os 8 itens listados, agrupados por módulo, em paralelo — nenhum depende de outro.

**Fase 3 — Arquitetura/dados**
1. Migração de campos financeiros para `Numeric`.
2. Resolver divergência de convenção de backlog.
3. Separar `scheduling` do acoplamento direto a `management.models`.
4. Testes para `service_orders.py`, `imports.py`, `rules.py`, `auth.py` (login real).

**Fase 4 — Produto/automação/IA**
1. Instrumentar `record_ai_access` em todas as tools MCP.
2. Tools novas de baixo esforço: `opr_control_tower`, `opr_gamification_summary`,
   `opr_people_structure`.
3. `opr_login_outages_summary` (agregado).
4. Decidir sensibilidade de dado de `localiza` antes de expor via MCP.
5. Sincronizar ou aposentar o servidor stdio.
