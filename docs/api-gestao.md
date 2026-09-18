# API — Gestão Integrada (/api/management)

> Fonte: `backend/app/modules/management/router.py`, `cases.py`, `schemas.py` e `models.py`.
> Todas as rotas deste documento têm o prefixo `/api/management` (o router é montado com
> `prefix="/management"` e o `main.py` acrescenta o prefixo global `/api`).

## Visão geral

O módulo de Gestão Integrada cobre três frentes que giram em torno da mesma pergunta: **quem
pertence à operação, quem está desviando da meta, e quem já respondeu por isso.**

1. **Estrutura operacional** — o "organograma" real de campo: quais colaboradores existem, quem é
   o supervisor de cada um, a qual modelo de equipe pertencem e sua escala de trabalho (padrão ou
   12x36/alternada). É a base sobre a qual os casos são abertos.
2. **Casos de gestão** — a cobrança formal de um desvio. Um caso nasce automaticamente quando a
   produção de um colaborador fica abaixo da meta do seu modelo de equipe (diário ou mensal), ou
   manualmente quando a matriz identifica um problema de conduta/processo. Cada caso percorre um
   ciclo de vida: `pending` (aberto, aguardando justificativa) → `justified`/`in_progress`
   (supervisor respondeu) → `resolved`/`rejected` (decisão final da matriz).
3. **Justificativas e decisão da matriz** — o supervisor explica o desvio (texto livre + motivo
   pré-cadastrado + plano de ação); a matriz aceita, rejeita ou devolve pedindo complemento. Toda a
   leitura agregada (diagnóstico, pendências por colaborador, justificativas paginadas) existe para
   responder "quem preciso cobrar hoje" sem abrir caso por caso.

Uma regra atravessa o módulo inteiro: **o escopo de visibilidade é aplicado no servidor**, nunca
confiando no filtro que a tela manda. Quem não tem a permissão `management:review` (a matriz) só
enxerga os casos e colaboradores onde é o supervisor responsável, ou que pertencem às regionais que
gerencia (`user.managed_regional`/`managed_regionals`). Ver `cases.case_scope_conditions` e
`cases.member_scope_conditions`.

## Autenticação e permissões

Todas as rotas exigem autenticação (dependência `require_permission("...")` do
`app.core.security`) — não há endpoint público neste módulo. As permissões usadas são:

| Permissão | Uso |
|---|---|
| `management:read` | Leitura geral: dashboard, options, listagem/export/diagnóstico de casos, pendências, justificativas, comentários, motivos, configurações. |
| `management:write_justification` | Justificar um caso (`POST /cases/{id}/justify`), abrir caso do dia/mês sob demanda (`POST /cases/daily`, `POST /cases/monthly`), comentar em um caso. |
| `management:review` | Decisão da matriz sobre um caso (`POST /cases/{id}/review`), revisão em lote (`POST /cases/bulk-review`), criação manual de caso (`POST /cases`). Também é a permissão que dá visibilidade irrestrita no escopo (`cases_engine.can_review`). |
| `management:manage_structure` | Atualizar/reprocessar a estrutura operacional (`POST /structure/refresh`, `PATCH /members/{id}`, sugestão de escala). |
| `management:claim_member` | Reivindicar (assumir supervisão de) um colaborador sem supervisor. |
| `management:audit_structure:read` | Auditoria da Estrutura Operacional Confiável (somente leitura). |
| `management:generate_cases` | Disparar a varredura em lote que abre casos de produtividade de um mês fechado. |
| `management:admin` | Administrar motivos de justificativa (case-reasons) e configurações de limiares/auto-geração. |

Escopo por regional: quando o usuário não tem `management:review`, toda consulta de casos e de
membros é restrita a `supervisor_user_id == user.id` OU `regional IN (regionais geridas pelo
usuário)`. Um caso ou colaborador fora do escopo retorna **404** (não 403) para não revelar sua
existência a quem não deveria vê-lo.

## Endpoints

### Dashboard / Options / Estrutura

**`GET /options`** — Permissão: `management:read`.
Lista de apoio para formulários: supervisores ativos (`User`) e modelos de equipe ativos
(`OperationTeamModel`), cada um como `{id, name}`. Resposta: `ManagementOptionsOut`.

**`GET /dashboard`** — Permissão: `management:read`.
Painel da estrutura operacional: lista de colaboradores (até 500) com filtros opcionais
(`regional`, `supervisor_user_id`, `status`, `search`, `collaborator_regional`) e um resumo
(`ManagementSummaryOut`) com contadores de membros por status e de casos abertos/atrasados — **os
contadores de caso respeitam o mesmo escopo de visibilidade da lista de membros**, para o painel
nunca contradizer a tabela. Resposta: `ManagementDashboardOut { summary, members[] }`.

**`POST /structure/refresh`** — Permissão: `management:manage_structure`.
Reprocessa a estrutura operacional a partir dos dados de origem (colaboradores/atribuições),
criando candidatos a `ManagementOperationalMember`. Gera log de auditoria. Resposta:
`{ created_candidates: int }`.

**`GET /structure-audit`** — Permissão: `management:audit_structure:read`.
Auditoria somente leitura da "Estrutura Operacional Confiável" — nenhuma chamada ao IXC, nenhuma
alteração de dado. Detecta inconsistências como colaboradores sem tipo de equipe, atribuições sem
modelo de equipe, etc. Resposta: `StructureAuditOut { summary, findings[], critical_count,
attention_count, informative_count, total_findings, generated_at }`.

**`POST /members/{member_id}/claim`** — Permissão: `management:claim_member`.
Supervisor/gerente de base reivindica um colaborador **sem supervisor** para a própria base — sem
exigir `managed_regionals` (propositalmente, para não travar quem mais precisa reivindicar). Falha
com **409** se o colaborador já tiver sido reivindicado por outro supervisor
(`MemberAlreadyClaimedError`). "Roubar" colaborador de outro supervisor exige a ação administrativa
(`PATCH /members/{id}` com `management:manage_structure`), não esta rota. Resposta:
`ManagementOperationalMemberOut`.

**`GET /members/{member_id}/shift-pattern-suggestion`** — Permissão: `management:manage_structure`.
Analisa a produção real dos últimos 21 dias do colaborador e sugere uma escala 12x36 (dia sim, dia
não) quando o padrão bate de forma consistente (≥80% de acerto e sem gap de produção ≥4 dias, que
indicaria afastamento em vez de folga). Nunca grava nada — só preenche o formulário; o supervisor
ainda precisa salvar. Resposta: `ManagementShiftPatternSuggestionOut { suggested_pattern
("alternating"|"inconclusive"), suggested_cycle_days_on, suggested_cycle_days_off,
suggested_anchor_date, confidence, message, daily_production[] }`.

**`PATCH /members/{member_id}`** — Permissão: `management:manage_structure`.
Atualiza campos parciais de um colaborador operacional (`ManagementMemberUpdate`: supervisor, modelo
de equipe, status, notas, escala). Regras de negócio embutidas:
- Trocar `team_model_id` para um modelo 12x36 sem informar `shift_pattern` liga automaticamente a
  escala alternada com os valores padrão do modelo.
- `shift_pattern="alternating"` só é aceito se o modelo de equipe efetivo (pós-update) for elegível
  para 12x36 — caso contrário retorna **422**.
- Mudar `status` para `validated_operation` ou `active_management` grava `validated_by`/
  `validated_at` com o usuário atual.

Status válidos (`OPERATIONAL_MEMBER_STATUSES`): `pending_validation`, `validated_operation`,
`outside_operation` (e demais valores do enum do modelo). Resposta: `{ status: "ok" }`.

### Casos de Gestão

Todos os endpoints de listagem/export/diagnóstico/pendências/justificativas compartilham a mesma
dependência de filtro (`case_filters_query` → `ManagementCaseFilters`), garantida para nunca
divergir entre telas. Parâmetros de filtro comuns:

| Parâmetro | Descrição |
|---|---|
| `status` | Status exato (`pending`, `justified`, `in_progress`, `resolved`, `rejected`). |
| `severity` | `low` \| `medium` \| `high`. |
| `regional`, `supervisor_user_id`, `case_type`, `reason_id`, `collaborator_id` | Filtros diretos. |
| `reference_year`, `reference_month` | Competência do caso. |
| `reference_date_from`, `reference_date_to` | Faixa de competência (inclusiva). |
| `only_overdue` | Só casos abertos com `due_date` vencido. |
| `only_open` | Só status abertos (`pending`, `justified`, `in_progress`). |
| `search` | ILIKE parcial em responsável, regional ou métrica. |
| `responsible_name` | Nome **exato** do colaborador (case-insensitive). |
| `pending_justification` | Atalho para `status=pending` (ainda sem justificativa). |
| `awaiting_review` | Atalho para `status=justified` (aguardando decisão da matriz). |
| `has_justification` | `true`/`false` — com/sem texto de justificativa. |
| `min_days_pending` | Só casos abertos há pelo menos N dias corridos. |

Combinações contraditórias (ex.: `status=resolved` + `only_open=true`, ou `pending_justification`
junto com `awaiting_review`) retornam **422** com mensagem explicando o conflito, em vez de devolver
0 resultados em silêncio.

**`GET /cases`** — Permissão: `management:read`.
Listagem paginada (`page`, `page_size` até 200), ordenada por severidade (alta primeiro), prazo
mais curto e mais recente. Resposta: `ManagementCasePage { items[], summary, total, page,
page_size }`, onde `summary` (`ManagementCaseSummaryOut`) traz contadores do mesmo recorte filtrado.

**`GET /cases/export`** — Permissão: `management:read`.
Exporta em CSV (delimitador `;`, BOM UTF-8 para abrir acentuação corretamente no Excel) **todo** o
recorte filtrado, sem paginação. Colunas: id, tipo, responsável, regional, competência, métrica,
esperado, realizado, desvio %, severidade, status, em atraso, motivo, justificativa, prazo,
supervisor, datas de criação/justificativa/revisão.

**`GET /cases/diagnostics`** — Permissão: `management:read`.
Agregado "quem mais falha" do recorte filtrado, em três dimensões (top 15 cada): por regional, por
responsável e por motivo — cada bucket com `total`, `open_cases`, `overdue_cases`. Resposta:
`ManagementCaseDiagnosticsOut`.

**`GET /cases/pending-by-collaborator`** — Permissão: `management:read`.
"Quem está devendo justificativa" — uma linha por (colaborador, regional), com idade da pendência e
os IDs dos casos abertos (até 20 por linha) prontos para abrir/justificar. Parâmetro `limit`
(1–1000, padrão 200). Combine com `pending_justification=true` para ver só quem nunca justificou, ou
com a faixa de data para recortar por dia/semana. Resposta: `ManagementPendingByCollaboratorOut {
total_collaborators, total_cases, items[], truncated }`.

**`GET /cases/justifications`** — Permissão: `management:read`.
Leitura achatada e paginada das justificativas do recorte: texto do supervisor, motivo, plano de
ação e decisão da matriz. Parâmetro `include_comments` (padrão `false`) também traz a thread de
comentários de cada caso. Resposta: `ManagementJustificationPage { total, page, page_size, items[]
}`.

**`POST /cases/bulk-review`** — Permissão: `management:review`.
Aplica a mesma decisão (`resolved`/`rejected`/`in_progress`) a vários casos de uma vez. Body:
`ManagementCaseBulkReview { case_ids[] (1–200), status, review_note }`. Casos fora do escopo do
revisor, ou ainda `pending` quando `status=resolved` (sem justificativa), são pulados sem falhar a
chamada inteira. Resposta: `ManagementCaseBulkReviewResult { updated_cases, skipped_pending,
not_found }`.

**`GET /cases/{case_id}`** — Permissão: `management:read`.
Detalhe de um caso (404 se não existir ou estiver fora do escopo). Resposta: `ManagementCaseOut`.

**`POST /cases`** — Permissão: `management:review`.
Criação manual de caso (usada quando o desvio não é de produtividade — conduta, processo,
retrabalho — por isso `metric_name` é texto livre). Se `due_date` não vier, é calculado como
`hoje + management_case_due_days`. Status inicial sempre `pending`. Resposta: `ManagementCaseOut`
(HTTP 201).

**`POST /cases/daily`** — Permissão: `management:write_justification`.
Abre (ou devolve, se já existir) o caso do dia vermelho clicado no drill do calendário. Usa a
mesma permissão de quem justifica (não exige `management:review`) — o supervisor pode abrir a
justificativa do próprio dia sem depender da matriz. Idempotente por (tipo, responsável, regional,
data). Body: `ManagementDailyCaseRequest { responsible_name, regional, reference_date,
expected_value?, actual_value }`. Resposta: `ManagementCaseOut`.

**`POST /cases/monthly`** — Permissão: `management:write_justification`.
Abre (ou devolve) o caso mensal de UM colaborador a partir do "Detalhe Operacional Mensal" do
calendário. Rejeita (**400**) mês corrente/futuro — só mês já fechado. Body:
`ManagementMonthlyCaseRequest { responsible_name, regional, reference_year, reference_month,
expected_value?, actual_value }`. Resposta: `ManagementCaseOut`.

**`POST /cases/generate`** — Permissão: `management:generate_cases`.
Varre a competência informada e abre casos de produtividade para todo colaborador abaixo da meta
(piso `median_from_quantity` do modelo de equipe, não o teto de "excelente"). Idempotente — rodar de
novo no mesmo mês não duplica caso, mas **recalcula** casos ainda `pending` com a produção mais
recente. Body: `ManagementCaseGenerateRequest { reference_year, reference_month }`. Resposta:
`ManagementCaseGenerateResult { created_cases, evaluated_members, skipped_existing,
skipped_insufficient_data, reference_year, reference_month }`.

**`POST /cases/{case_id}/justify`** — Permissão: `management:write_justification`.
Supervisor registra a justificativa. Retorna **409** se o caso já estiver encerrado
(`resolved`/`rejected`). Se `reason.requires_description` for verdadeiro, exige texto com ≥15
caracteres (**400** caso contrário). `status` só pode ser `justified` ou `in_progress`
(`JUSTIFY_TARGET_STATUSES`) — encerrar é decisão exclusiva da matriz via `/review`. Quando o status
final é `justified`, notifica todos os usuários com `management:review`. Body:
`ManagementCaseJustification { reason_id?, justification_text, action_plan?, status }`. Resposta:
`ManagementCaseOut`.

**`POST /cases/{case_id}/review`** — Permissão: `management:review`.
Decisão da matriz: `resolved`, `rejected` ou `in_progress` (devolve pedindo complemento)
(`REVIEW_TARGET_STATUSES`). Retorna **409** ao tentar resolver um caso ainda `pending` (sem
justificativa do supervisor). `review_note`, quando informado, vira um comentário no caso (não
sobrescreve a justificativa). Body: `ManagementCaseReview { status, review_note?, due_date? }`.
Resposta: `ManagementCaseOut`.

**`GET /cases/{case_id}/comments`** — Permissão: `management:read`.
Lista a thread de comentários do caso, ordenada por data de criação. Resposta:
`list[ManagementCaseCommentOut]`.

**`POST /cases/{case_id}/comments`** — Permissão: `management:write_justification`.
Adiciona um comentário ao caso. Body: `ManagementCaseCommentCreate { comment (min. 2 caracteres) }`.
Resposta: `ManagementCaseCommentOut` (HTTP 201).

### Motivos de Caso (case-reasons)

**`GET /case-reasons`** — Permissão: `management:read`.
Lista os motivos de justificativa pré-cadastrados. Na primeira leitura, semeia 8 motivos padrão
(ex.: "Ausência / afastamento", "Equipe incompleta", "Desempenho individual", "Outro") caso a tabela
esteja vazia — idempotente, nunca sobrescreve o que já foi editado. Parâmetro `include_inactive`
(padrão `false`). Resposta: `list[ManagementCaseReasonOut]`.

**`POST /case-reasons`** — Permissão: `management:admin`.
Cria um motivo novo. Retorna **409** se já existir motivo com o mesmo nome (case-insensitive). Body:
`ManagementCaseReasonCreate { name, description?, active=true, requires_description=false }`.
Resposta: `ManagementCaseReasonOut` (HTTP 201).

**`PATCH /case-reasons/{reason_id}`** — Permissão: `management:admin`.
Atualiza campos parciais de um motivo (404 se não existir; 409 em conflito de nome). Body:
`ManagementCaseReasonUpdate`. Resposta: `ManagementCaseReasonOut`.

### Configurações / Auto-geração

**`GET /settings`** — Permissão: `management:read`.
Lê os limiares atuais de geração de caso. Resposta: dicionário chave→valor (string) com defaults:

| Chave | Default | Significado |
|---|---|---|
| `management_case_min_deviation_pct` | `15` | Desvio % mínimo abaixo da meta para abrir caso. |
| `management_case_high_severity_pct` | `35` | A partir daqui, severidade `high`. |
| `management_case_low_severity_pct` | `25` | Entre `min_deviation` e este valor, severidade `low`; acima, `medium`. |
| `management_case_min_days_worked` | `5` | Mínimo de dias trabalhados no mês para a média ser considerada. |
| `management_case_due_days` | `7` | Prazo (dias corridos) para o supervisor justificar. |

**`PUT /settings`** — Permissão: `management:admin`.
Atualiza um ou mais limiares (campos `None` são ignorados). Body: `ManagementSettingsUpdate`.
Resposta: o dicionário de configurações atualizado.

**`GET /settings/auto-generate`** — Permissão: `management:read`.
Estado do toggle de geração automática diária. Resposta: `ManagementAutoGenerateSettingsOut {
enabled, last_run_date }`.

**`PUT /settings/auto-generate`** — Permissão: `management:admin`.
Liga/desliga a geração automática (diária) que abre casos de produtividade do mês anterior fechado
**e** casos de dia abaixo da meta de ontem — um único toggle controla os dois fluxos (ver
`modules/management/scheduler.py`). Os botões manuais ("Gerar casos do mês", "Justificar dia")
continuam disponíveis mesmo com o automático ligado. Body: `ManagementAutoGenerateSettingsUpdate {
enabled }`. Resposta: `ManagementAutoGenerateSettingsOut`.

## Exemplos

### 1. Listar casos pendentes de justificativa, atrasados, de uma regional

```
GET /api/management/cases?pending_justification=true&only_overdue=true&regional=Porto%20Velho&page=1&page_size=50
Authorization: Bearer <token>
```

Resposta (resumida):

```json
{
  "items": [
    {
      "id": 4821,
      "case_type": "daily_performance_below_target",
      "responsible_name": "João da Silva",
      "regional": "Porto Velho",
      "metric_name": "O.S. concluídas no dia",
      "expected_value": 5.0,
      "actual_value": 2.0,
      "deviation_value": 60.0,
      "severity": "high",
      "status": "pending",
      "is_overdue": true,
      "due_date": "2026-09-10",
      "comment_count": 0
    }
  ],
  "summary": { "total_cases": 1, "open_cases": 1, "pending_cases": 1, "overdue_cases": 1, "high_severity_open": 1 },
  "total": 1,
  "page": 1,
  "page_size": 50
}
```

### 2. Supervisor justifica um caso

```
POST /api/management/cases/4821/justify
Authorization: Bearer <token>
Content-Type: application/json

{
  "reason_id": 2,
  "justification_text": "Equipe operou incompleta no dia - faltou o parceiro de dupla, sem substituto disponível na base.",
  "action_plan": "Escalar reposição de dupla junto ao RH para a próxima semana.",
  "status": "justified"
}
```

Resposta: o `ManagementCaseOut` atualizado com `status="justified"`, `justified_at` preenchido, e
disparo de notificação para todos os usuários com `management:review`.

### 3. Matriz revisa em lote

```
POST /api/management/cases/bulk-review
Authorization: Bearer <token>
Content-Type: application/json

{
  "case_ids": [4821, 4822, 4830],
  "status": "resolved",
  "review_note": "Justificativas aceitas - equipe incompleta confirmado no registro de escala."
}
```

Resposta:

```json
{ "updated_cases": 2, "skipped_pending": 1, "not_found": 0 }
```

(um dos três casos ainda estava `pending` — sem justificativa do supervisor — e foi pulado, não
resolvido à força.)

## Observações / pontos pouco claros no código

- A rota `PATCH /members/{member_id}` tem `response_model=dict` mas na prática sempre devolve
  `{"status": "ok"}` — o objeto atualizado não é retornado; quem chama precisa buscar o membro de
  novo (`GET /dashboard`) para ver o estado pós-update.
- `ManagementCaseCreate.case_type` e `metric_name` são texto livre (sem enum no schema) — os valores
  usados pelo próprio backend para os tipos automáticos são as constantes
  `CASE_TYPE_PRODUCTIVITY = "productivity_below_target"` e
  `CASE_TYPE_DAILY_BELOW = "daily_performance_below_target"`, mas nada impede a matriz de criar um
  `case_type` arbitrário na criação manual.
  - `severity` idem: aceito como string livre no `ManagementCaseCreate`, mas o backend só calcula
  automaticamente `low`/`medium`/`high` para os casos gerados por regra; num `POST /cases` manual,
  quem chama informa a severidade diretamente.
- Não há endpoint de exclusão (`DELETE`) para casos nem para motivos de justificativa neste
  router — motivos só podem ser desativados (`active=false`) via `PATCH /case-reasons/{id}`, nunca
  removidos.
- `refresh_pending_cases` e `generate_daily_cases_for_date` (funções centrais do motor de
  recalcular/gerar casos automaticamente) não têm endpoint HTTP próprio neste router — são
  chamadas pelo scheduler (`modules/management/scheduler.py`), não expostas diretamente pela API.
