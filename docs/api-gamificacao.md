# API — Gamificação Operacional (`/api`)

> Documento gerado por leitura direta do código em `backend/app/api/routes/`
> (17 arquivos de rota do módulo, mais `health.py`, compartilhado por toda a
> aplicação). Reflete o estado do código nesta branch em 2026-09-16. Se este
> documento divergir do código no futuro, o código vence (ver
> `docs/00-TRILHA-0.md`).

## Visão geral

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

## Autenticação e permissões

### Padrão de autenticação

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

### Rotas públicas (sem autenticação)

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

### Catálogo de permissões (`require_permission(...)`)

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

## Endpoints

Convenções usadas abaixo: **Perm.** é a permissão exigida (`—` = só
autenticado, **Público** = sem autenticação). Corpos de request/response
resumidos pelos nomes dos schemas Pydantic (`app/schemas`) quando existem;
detalhamento textual quando o retorno é montado ad-hoc no handler.

### Autenticação (`auth.py`, prefixo `/auth`, 3 rotas)

| Método + path | Descrição | Perm. |
|---|---|---|
| `POST /auth/login` | Login por e-mail/senha. Rate limit 5 tentativas/15 min por IP+email (`429` ao estourar). Retorna `TokenOut` (`access_token`, `user` serializado com permissões efetivas, `managed_regionals`, `portal_first_access_required`). | Público |
| `GET /auth/me` | Dados do usuário autenticado (`UserOut`, mesmo serializador de `login`). | — |
| `POST /auth/change-password` | Troca de senha voluntária. Exige apenas autenticação — vale para qualquer usuário do ecossistema, não só quem tem `collaborator_id`. Corpo `ChangePasswordRequest` (senha atual, nova, confirmação). | — |

### Usuários (`users.py`, prefixo `/users`, 6 rotas)

| Método + path | Descrição | Perm. |
|---|---|---|
| `GET /users` | Lista todos os usuários (`UserOut[]`). | `users:manage` |
| `POST /users` | Cria usuário. Valida `role` contra lista fechada (`viewer`, `operator`, `admin`, `collaborator`, `regional_manager_viewer`, `base_manager`, `workspace_restricted`), e-mail único, vínculo 1:1 com colaborador. Marca `must_change_password=true` automaticamente se vinculado a colaborador. | `users:manage` |
| `PUT /users/{user_id}` | Atualização parcial (`exclude_unset`). Revalida e-mail único, vínculo de colaborador, `managed_regionals`; remover todos os perfis de acesso rebaixa o usuário para `workspace_restricted`. | `users:manage` |
| `POST /users/{user_id}/force-password-reset` | Reset administrativo: gera senha temporária (`secrets`, alfabeto sem caracteres ambíguos) e força troca no próximo login. Retorna `AdminForcePasswordResetOut` (inclui `temporary_password` em texto puro, uma única vez). | `users:manage` |
| `POST /users/{user_id}/force-first-access` | Reabre o primeiro acesso completo (CPF/contato + senha), não só a senha. | `users:manage` |
| `DELETE /users/{user_id}` | Exclui usuário (bloqueia autoexclusão). Logs de auditoria do usuário excluído ficam órfãos (`user_id = NULL`), não são apagados. | `users:manage` |

### Convites (`invites.py`, prefixo `/invites`, 7 rotas)

| Método + path | Descrição | Perm. |
|---|---|---|
| `POST /invites` | Cria convite avulso (e-mail + `collaborator_id` + `role`), devolve token bruto uma única vez (`PortalInviteCreateOut`). | `users:manage` |
| `POST /invites/lookup-ixc-cpf` | Busca colaborador no IXC por CPF para sugerir convite; nunca cria nada sozinho. | `users:manage` |
| `POST /invites/from-ixc` | Confirma o colaborador encontrado no IXC e gera o convite; `collaborator_id` sempre explícito no corpo, nunca implícito. | `users:manage` |
| `GET /invites` | Lista convites (`PortalInviteOut[]`). | `users:manage` |
| `POST /invites/{invite_id}/revoke` | Revoga convite. | `users:manage` |
| `GET /invites/accept?token=` | Status do convite por token (válido/expirado/usado), sem revelar dado interno. | Público |
| `POST /invites/accept` | Aceita o convite com nova senha; devolve `TokenOut` igual ao login (entra direto no onboarding). Rate limit 10/15 min por IP. | Público |

### Solicitações de Acesso (`access_requests.py`, prefixo `/access-requests`, 5 rotas)

| Método + path | Descrição | Perm. |
|---|---|---|
| `POST /access-requests/lookup-cpf` | Candidato confirma nome/telefone mascarado pelo CPF (nunca e-mail). Rate limit 10/15 min por IP. | Público |
| `POST /access-requests` | Submete solicitação (CPF, e-mail, senha escolhida, nome, telefone). Resposta sempre `{"received": true}` — nunca revela se já existe conta. Rate limit 10/15 min por IP. | Público |
| `GET /access-requests` | Lista solicitações pendentes/decididas (`PortalAccessRequestOut[]`). | `users:manage` |
| `POST /access-requests/{id}/approve` | Aprova e cria a conta direto, com a senha que o candidato já escolheu ao solicitar. `collaborator_id` sempre explícito no corpo. | `users:manage` |
| `POST /access-requests/{id}/reject` | Rejeita, com motivo (`decision_reason`). | `users:manage` |

### Importações (`imports.py`, prefixo `/imports`, 8 rotas)

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

### Auditoria (`audit.py`, prefixo `/audit`, 5 rotas)

| Método + path | Descrição | Perm. |
|---|---|---|
| `GET /audit/logs` | Log de auditoria genérico do sistema (`AuditLog`), com filtros `action`/`entity`/`entity_id`/`user_id`/`search` e paginação (`limit≤500`, `offset`). | `audit:read` |
| `GET /audit/service-orders` | Auditoria detalhada de O.S. do período/regional (default: fechamento mais recente), com dezenas de flags (`only_scored`, `only_penalized`, `only_sla_out`, `only_warranty`, `only_recurrence`, `only_diagnosis_blocked`, `only_registered` — este último `True` por padrão, restringindo à equipe cadastrada). Paginado (`page`, `page_size` até 5000). | `audit:read` |
| `GET /audit/service-orders-scoring` | Alias idêntico ao endpoint acima (mesmos parâmetros, mesma implementação). | `audit:read` |
| `GET /audit/service-orders/{id}/recurrence-audit` | Explica a classificação de reincidência de uma O.S. específica. `404` se não houver auditoria de reincidência para ela. | `audit:read` |
| `GET /audit/service-orders/{id}/detail` | Explicação completa (regras aplicadas, pontos, penalidades) de uma O.S., opcionalmente ancorada em um `calculation_run_id`. | `audit:read` |

### Colaboradores (`collaborators.py`, prefixo `/collaborators`, 12 rotas)

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

### Pontuação / Scoring (`scoring.py`, sem prefixo próprio — rotas soltas; router com `dependencies=[require_permission("scoring:read")]` aplicado a TODAS as rotas, 17 rotas)

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

### Regras (`rules.py`, sem prefixo próprio — router com `dependencies=[require_permission("scoring:read")]`, 13 rotas)

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

### Configuração de Gamificação (`gamification.py`, prefixo `/gamification`, 7 rotas)

| Método + path | Descrição | Perm. |
|---|---|---|
| `GET /gamification/config` | Configuração corrente completa (regras, parâmetros gerais) serializada. | `scoring:read` |
| `PUT /gamification/config` | Aplica uma configuração completa; registra log de auditoria com before/after. | `settings:write` |
| `POST /gamification/config/export` | Mesmo retorno de `GET /config` (endpoint dedicado para o fluxo de exportação no frontend). | `scoring:read` |
| `POST /gamification/config/import` | Importa configuração (mesmo `apply_config` de `PUT /config`, log de auditoria com ação `import`). | `settings:write` |
| `POST /gamification/config/reset-default` | Restaura a configuração padrão de fábrica (`ensure_default_logic_config`). | `settings:write` |
| `POST /gamification/cpk/sync` | Sincroniza sob demanda o relatório de CPK (custo por km) por regional a partir da API externa de CPK; grava snapshot local. `502` em falha de comunicação. | `settings:write` |
| `GET /gamification/cpk/snapshot?year=&month=` | Último snapshot de CPK sincronizado para o período (sem chamar a API ao vivo). | `scoring:read` |

### O.S. / Service Orders (`service_orders.py`, prefixo `/service-orders`, 5 rotas)

| Método + path | Descrição | Perm. |
|---|---|---|
| `GET /service-orders?limit=` | Lista O.S. reais (exclui códigos demo), mais recentes primeiro. | `orders:read` |
| `GET /service-orders/period-summary` | Resumo por (ano, mês): total de O.S., primeira/última data de fechamento. | `orders:read` |
| `GET /service-orders/subject-summary?reference_month=&reference_year=&regional=` | Contagem de O.S. por (tipo, assunto) no período, ordenado por volume. | `orders:read` |
| `POST /service-orders/delete-period` | Exclusão em massa de O.S. de um período (+ `CalculationRun`s associados), com confirmação textual obrigatória (`"APAGAR MM/AAAA"`). Bloqueia (`409`) se houver fechamento `paid` no período, ou lançamentos de saldo de garantia vinculados sem O.S. rastreável. Desvincula (sem apagar) lançamentos de saldo que ainda podem ser reimportados. | `orders:import` |
| `POST /service-orders/seed` | Popula o banco com dados de lógica (sem O.S. demo); disponível **apenas em ambiente `development`** (`403` fora dele). | `settings:write` |

### Liderança (`leadership.py`, prefixo `/leadership`, 10 rotas)

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

### Runs de Cálculo (`calculation_runs.py`, prefixo `/calculation-runs`, 6 rotas)

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

### Dashboard (`dashboard.py`, prefixo `/dashboard`, 4 rotas)

| Método + path | Descrição | Perm. |
|---|---|---|
| `GET /dashboard/bootstrap` | Retorno mínimo para a tela inicial decidir o período/regional padrão: `reference_month/year`, `regional`, `point_value`, `has_calculation_run`. | `dashboard:read` |
| `GET /dashboard/gamification-preview` | Leitura leve (valor corrente + data do cálculo) para a Visão Geral executiva de outro módulo (`UNI Intelligence`/`operacao`), sem carregar ranking/breakdowns completos. | `dashboard:read` |
| `GET /dashboard/summary?reference_month=&reference_year=&regional=` | **Rota principal da tela de Gamificação.** Monta cards, ranking, bônus de liderança, distribuição de penalidade, saúde por regional e custos por regional/grupo/assunto/colaborador. Usa um cache versionado (`dashboard_cache_version == 3`) gravado no próprio `CalculationRun.result_summary`, com uma guarda de consistência (`_regional_breakdown_is_consistent`) que recusa o cache e recalcula se o total por regional exceder o teto financeiro do fechamento — proteção contra dado gravado desatualizado após um pagamento. Fechamentos imutáveis (`paid`/`cancelled`) têm um segundo nível de cache em memória de processo (`IMMUTABLE_BREAKDOWNS_CACHE`, até 64 entradas), porque recalcular o mês inteiro chegou a levar 6,36s medidos. | `dashboard:read` |
| `GET /dashboard/filtered-breakdowns?calculation_run_id=&regional=` | Breakdowns (distribuição de penalidade, custo por regional/grupo, assuntos não mapeados) recortados para um subconjunto de regionais dentro de um fechamento, com cache próprio por `(run_id, regionais)` — invalidado explicitamente quando o run muda de status para `paid`. | `dashboard:read` |

### Configurações do App (`settings.py`, prefixo `/settings`, 2 rotas)

`app_settings` é uma tabela compartilhada entre módulos (Agendamento guarda
suas próprias chaves `scheduling_*` nela também); estas rotas só
leem/escrevem as chaves que pertencem à Gamificação.

| Método + path | Descrição | Perm. |
|---|---|---|
| `GET /settings` | Lista as configurações da Gamificação (`AppSettingOut[]`, filtradas às chaves conhecidas do módulo). | `scoring:read` |
| `PUT /settings/{key}` | Atualiza uma configuração pelo nome da chave. `404` se a chave não pertencer à Gamificação. | `settings:write` |

### Saldo de Pontos (`point_balance.py`, prefixo `/point-balance`, 4 rotas)

Sistema de saldo/garantia pós-pagamento (ver
`docs/spec-saldo-pontos-garantia-pos-pagamento.md`): débitos e créditos de
pontos que ficam pendentes até serem consumidos num fechamento pago.

| Método + path | Descrição | Perm. |
|---|---|---|
| `GET /point-balance/pending?calculation_run_id=` ou `?reference_month=&reference_year=` | Lista lançamentos pendentes classificados em três buckets: `applied` (já consumido por este fechamento), `eligible_pending` (seria consumido se este fechamento fosse pago agora) e `deferred_pending` (alvo é um mês posterior, só informativo). Sem período informado, devolve o acumulado histórico como `eligible_pending`. | `audit:read` |
| `POST /point-balance/entries` | Cria ajuste manual de saldo (positivo ou negativo). **Somente admin.** | `audit:read` + admin |
| `POST /point-balance/entries/{id}/resolve` | Resolve uma entrada marcada para revisão manual, com os pontos finais decididos. **Somente admin.** | `audit:read` + admin |
| `POST /point-balance/entries/{id}/revert` | Estorna um lançamento, com motivo obrigatório. **Somente admin.** | `audit:read` + admin |

### Notificações (`notifications.py`, prefixo `/notifications`, 4 rotas)

| Método + path | Descrição | Perm. |
|---|---|---|
| `GET /notifications?limit=` | Lista notificações do usuário autenticado (`limit≤100`). | — (autenticado) |
| `GET /notifications/unread-count` | Contagem de não lidas. | — (autenticado) |
| `POST /notifications/{id}/read` | Marca uma notificação como lida. `404` se não pertencer ao usuário. | — (autenticado) |
| `POST /notifications/read-all` | Marca todas como lidas; devolve `{"marked_read": N}`. | — (autenticado) |

### Portal do Colaborador (`portal.py`, prefixo `/portal`, 14 rotas)

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

### Health (`health.py`, prefixo `/health`, 1 rota)

| Método + path | Descrição | Perm. |
|---|---|---|
| `GET /health` | `{"status": "ok"}`, sem tocar banco nem dependências externas. | Público |

## Exemplos

### 1. Login

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

### 2. Colaboradores — saldo de pontos

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

### 3. Fechamento — mudar status para pago

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

### 4. Portal do Colaborador — extrato do próprio mês

```http
GET /api/portal/summary?reference_month=8&reference_year=2026
Authorization: Bearer eyJhbGciOi... (token do próprio colaborador)
```

Exige `portal:read_self` (via `require_portal_access` — bloqueia se o
colaborador ainda não completou o primeiro acesso). Resposta `200`
(`PortalSummaryOut`) traz o resumo financeiro pessoal do colaborador para
aquele fechamento (pontos, penalidades, valor estimado a receber, saldo de
garantia aplicado).

## Observações e pontos não totalmente esclarecidos pelo código lido

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
