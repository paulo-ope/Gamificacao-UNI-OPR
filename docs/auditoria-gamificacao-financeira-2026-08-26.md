# Auditoria financeira do módulo Gamificação — 2026-08-26

Auditoria de ponta a ponta do módulo **Gamificação Operacional** (`/gamificacao`, API `/api`),
focada em risco de divergência financeira, duplicidade, arredondamento, rastreabilidade,
performance sob crescimento e fragilidade operacional.

**Escopo desta rodada: somente diagnóstico.** Nenhum código de regra de negócio foi alterado,
nenhuma migration rodou, nenhum dado real foi modificado. Todas as consultas ao banco foram de
leitura. Ver seção 12 (“O que NÃO deve ser alterado ainda”) e seção 13 (confirmação de escopo).

Base auditada: banco de produção local (`opr-gamification-db`), 2026-08-26.
Documentos de referência lidos antes da auditoria: `AGENTS.md`, `docs/00-TRILHA-0.md`,
`docs/STATUS.md`, `docs/normas-qualidade-dados-metricas.md`, `docs/manual_programacao_senior.md`,
`docs/manual_frontend_senior.md`, `docs/code_review.md`,
`docs/spec-saldo-pontos-garantia-pos-pagamento.md`.

---

## 1. Resumo executivo

O módulo tem uma arquitetura correta no papel — regra concentrada em `services/`, fechamento com
máquina de estados, ledger de saldo com auditoria, snapshot de régua por fechamento, trava contra
pagamento duplicado por período. O problema **não** é ausência de regra: é que **o mesmo número
financeiro está persistido em três lugares diferentes, sem nenhuma invariante que os obrigue a
concordar**, e endpoints diferentes leem lugares diferentes.

Isso já produziu divergência real, agora, em um fechamento **pago**:

| Onde o número aparece | Fonte lida | Valor (fechamento #1601, 07/2026, pago) |
|---|---|---|
| Tela de fechamento / ranking / Excel de pagamento | `result_summary.score_summaries` (cache JSON) | **R$ 18.191,18** |
| Histórico de fechamentos / extrato PDF do colaborador | linhas de `collaborator_scores` | **R$ 18.271,68** |
| Tabela “Valor a ser pago por regional” | `result_summary.cost_by_regional` | **R$ 38.264,02** |

Diferença de **R$ 80,50 (230 pontos)** entre a tela e o extrato entregue ao colaborador, e de
**mais de R$ 14 mil** entre o card “Total a pagar” e a tabela “por regional” da mesma tela — em um
fechamento já marcado como pago. As três causas foram isoladas e reproduzidas (C1, C2).

Os cinco riscos que mais preocupam, em ordem:

1. **C1 — Três fontes de verdade para o mesmo valor pago**, com divergência já materializada.
2. **C2 — `cost_by_regional` acumula o bônus de liderança a cada recálculo** (não idempotente):
   o fechamento pago de julho tem o bônus somado 3 vezes e duas linhas duplicadas de
   “Liderança sem regional”.
3. **C3 — Identidade de reincidência por `contract_id`**, que **não** é único por cliente: um
   contrato chega a agrupar 20 logins distintos. 1.757 pares de O.S. de clientes diferentes são
   hoje elegíveis a virar “garantia” e anular pontos de quem não errou.
4. **C4 — Ajustes manuais de saldo sem autor**: 1.377 lançamentos manuais (+13.268 pontos ≈
   R$ 4.644) com `created_by = NULL`, criados por scripts fora da API. Há **R$ 3.218,81 líquidos
   de saldo pendente** que serão consumidos automaticamente no próximo fechamento pago.
5. **C5 — Marcar como pago não é serializado nem idempotente**: nenhum lock de linha, nenhuma
   trava contra clique duplo, e o consumo do ledger acontece dentro dessa mesma requisição.

Além disso, dois controles financeiros configuráveis na tela **não fazem nada** (`payment_cap` e
`warranty_mode` — A5, A6), e o crescimento do banco já está fora de controle: **1.106
`calculation_runs` e 225.121 `collaborator_scores`**, sendo 223.811 em rascunhos descartáveis,
sem nenhum índice em `closed_at`/`opened_at`/`calculation_run_id`.

**Contagem de achados: 5 críticos, 8 altos, 9 médios, 7 baixos.**

---

## 2. Mapa da arquitetura do módulo

### Rotas frontend
| Rota | Arquivo | Papel |
|---|---|---|
| `/gamificacao` | [page.tsx](../frontend/app/gamificacao/page.tsx) (2.117 linhas) | Orquestra todas as abas |
| `/portal` | [page.tsx](../frontend/app/portal/page.tsx) | Visão do colaborador |

Componentes: `frontend/components/gamification/` — `closure-tab.tsx` (fechamento),
`ranking-tab.tsx` / `ranking-table.tsx`, `financial-table.tsx`, `audit-panel.tsx`,
`order-audit-drawer.tsx`, `collaborator-orders-sheet.tsx`, `point-balance-panel.tsx`,
`collaborator-balance-history-sheet.tsx`, `leadership-bonus-panel.tsx`,
`logic-configuration-panel.tsx`, `governance-rules-panel.tsx`, `closure-history-panel.tsx`,
`upvalue-import-panel.tsx`, `unmapped-*-panel.tsx`, `collaborator-registry-panel.tsx`,
`user-management-panel.tsx`, `dashboard-charts.tsx`.
Hooks: `frontend/hooks/use-closure-data.ts`, `use-closure-actions.ts`.

### Endpoints backend
| Prefixo | Arquivo | Papel financeiro |
|---|---|---|
| `/calculation-runs` | [calculation_runs.py](../backend/app/api/routes/calculation_runs.py) | Calcular, listar, mudar status, **consumir saldo ao pagar** |
| `/dashboard` | [dashboard.py](../backend/app/api/routes/dashboard.py) | Cards, ranking, breakdowns financeiros |
| `/point-balance` | [point_balance.py](../backend/app/api/routes/point_balance.py) | Ledger de saldo, ajuste manual, estorno |
| `/leadership` | [leadership.py](../backend/app/api/routes/leadership.py) | Perfis e **recálculo** do bônus |
| `/collaborators` | [collaborators.py](../backend/app/api/routes/collaborators.py) | Cadastro + **extrato PDF de pagamento** |
| `/scoring`, `/rules` | [scoring.py](../backend/app/api/routes/scoring.py), [rules.py](../backend/app/api/routes/rules.py) | Matriz de pontos, penalidades, reincidência |
| `/gamification` | [gamification.py](../backend/app/api/routes/gamification.py) | Config consolidada + CPK |
| `/imports` | [imports.py](../backend/app/api/routes/imports.py) | Importação de planilha UpValue |
| `/audit` | [audit.py](../backend/app/api/routes/audit.py) | Trilha de auditoria |
| `/portal` | [portal.py](../backend/app/api/routes/portal.py) | Visão do colaborador |

### Services
| Arquivo | Linhas | Responsabilidade |
|---|---|---|
| [scoring_detail.py](../backend/app/services/scoring_detail.py) | 2.353 | **Núcleo**: período, pontos por O.S., penalidades, reincidência/garantia, saúde regional, breakdowns |
| [calculation.py](../backend/app/services/calculation.py) | 572 | Orquestra o fechamento, grava `CalculationRun` + `CollaboratorScore` |
| [calculation_closure.py](../backend/app/services/calculation_closure.py) | 339 | Máquina de estados, travas de período, snapshot de régua, fuso |
| [point_balance.py](../backend/app/services/point_balance.py) | 678 | Ledger de garantia pós-pagamento |
| [leadership_bonus.py](../backend/app/services/leadership_bonus.py) | 499 | Bônus de liderança |
| [upvalue_importer.py](../backend/app/services/upvalue_importer.py) | 910 | Importação de planilha |
| [ixc_importer.py](../backend/app/services/ixc_importer.py) | 698 | Importação da API do IXC (fonte real hoje) |
| [ixc_scheduler.py](../backend/app/services/ixc_scheduler.py) | 342 | Sincronização periódica + recálculo automático |
| [cpk_health.py](../backend/app/services/cpk_health.py) | 128 | Ajuste de multiplicador por CPK da frota |
| [statement_pdf.py](../backend/app/services/statement_pdf.py) | 306 | Extrato individual de pagamento |
| [portal_dashboard.py](../backend/app/services/portal_dashboard.py) | 891 | Visão do colaborador |
| [gamification_config.py](../backend/app/services/gamification_config.py) | 652 | Export/import/reset de configuração |
| [scoring_matrix.py](../backend/app/services/scoring_matrix.py) | 70 | Filtro de O.S./assuntos de demonstração |
| [audit_log.py](../backend/app/services/audit_log.py) | 61 | Trilha |

### Models financeiros ([models.py](../backend/app/models.py))
`ServiceOrder` (226) · `ScoringGroup` (256) · `ScoringSubjectRule` (271) ·
`DiagnosisPenaltyRule` (290) · `SlaPenaltyRule` (304) · `RecurrenceClassificationRule` (317) ·
`GamificationConfigVersion` (344) · `HealthRule` (355) · `CpkRegionalSnapshot` (366) ·
**`CalculationRun` (386)** · **`CollaboratorScore` (417)** · `CollaboratorPointBalance` (438) ·
**`PointBalanceEntry` (459)** · `LeadershipProfile` (509) · `LeadershipBonusResult` (560) ·
`AppSetting` (580) · `ImportRun` (589) · `ImportServiceOrderAudit` (628) · `AuditLog` (211).

### Migrations
77 arquivos em `backend/alembic/versions/`. Relevantes ao módulo:
`20260612_0002_phase2_import_audit.py`, `20260707_0003_point_balance_ledger.py`,
`20260710_0004_point_balance_os_code.py`, `20260715_0007_service_orders_accent_fallbacks.py`.

### Testes existentes
`test_calculation_closure.py`, `test_point_balance.py`, `test_scoring_detail.py`,
`test_leadership_bonus.py`, `test_gamification_config.py`, `test_collaborators.py`,
`test_upvalue_importer.py`, `test_portal_dashboard.py`, `test_portal_profile.py`,
`test_portal_team_summary.py`, `test_ixc_importer.py`, `test_ixc_scheduler.py`, `test_cpk_health.py`.

### Documentos de regra
`docs/spec-saldo-pontos-garantia-pos-pagamento.md`, `REGRAS_CONFIGURADAS_GAMIFICACAO.md`,
`DOCUMENTACAO_OPERACIONAL_GAMIFICACAO.md`, `docs/normas-qualidade-dados-metricas.md`.

---

## 3. Mapa do fluxo financeiro completo

```
IXC (API su_oss_chamado, status=F)
  └─ ixc_scheduler (a cada 20 min, lock consultivo pg_try_advisory_lock)
       └─ ixc_importer.import_ixc_service_orders  → upsert por os_code (chave única)
            · parse_ixc_datetime: hora LOCAL do IXC gravada com rótulo UTC  ← [M1]
            · bloqueia alteração de O.S. de período já pago
            └─ recalculate_current_period  (se ixc_sync_auto_recalculate=true)
                 └─ calculate_scores(mês corrente)  → CRIA UM NOVO CalculationRun  ← [A1]

calculate_scores (services/calculation.py:152)
  1. ensure_period_not_closed  (bloqueia período pago ou mês já virado)
  2. period_orders             (mês fechado por closed_at, senão opened_at)   ← [M2] [A3]
  3. detect_post_payment_warranty_debits → cria PointBalanceEntry pendentes    ← [C3] [C4]
  4. calculate_regional_health + _apply_cpk_adjustment → multiplicador por regional
  5. explain_orders → por O.S.: base_points, penalidades (diagnóstico, SLA,
     reincidência/garantia), net_points = max(base − penalidades, 0)           ← [M6]
  6. por colaborador: summarize_details → final_points = net × multiplicador
                                          estimated_payment = final × valor do ponto
  7. preview_pending_adjustment (prévia do saldo, NÃO consome)
  8. grava CollaboratorScore (linha) + result_summary.score_summaries (cache)  ← [C1]
  9. financial_breakdowns → cost_by_regional/group/subject/collaborator        ← [A4]
 10. calculate_and_store_leadership_bonus → soma bônus em cost_by_regional     ← [C2]

Fechamento: draft → review → approved → paid   (approved/paid exigem admin)
  PATCH /calculation-runs/{id}/status                                          ← [C5]
    · ensure_no_overlapping_paid_period (impede pagar o mesmo colaborador 2x no mês)
    · ensure_no_unregistered_payable_collaborators
    · _apply_point_balance_after_payment → CONSOME o ledger, recompõe do bruto  ← [C1]
    · _refresh_stale_draft_previews → varre TODOS os rascunhos do sistema       ← [A2]

Saída / pagamento
  · Excel "Exportar pagamento"  → montado no FRONTEND a partir de summary.ranking (cache)  ← [C1] [A7]
  · Extrato PDF individual      → lê collaborator_scores (linha)                            ← [C1] [A8]
  · Portal do colaborador       → pega o run mais recente por created_at, sem filtro         ← [A9]
```

---

## 4. Riscos críticos

### C1 — Três fontes de verdade para o mesmo valor pago, já divergentes em produção

**Onde:** [calculation.py:466-471](../backend/app/services/calculation.py#L466),
[calculation_runs.py:156-227](../backend/app/api/routes/calculation_runs.py#L156),
[calculation_runs.py:26-49](../backend/app/api/routes/calculation_runs.py#L26).

O valor de cada colaborador é persistido em **três** lugares:
1. a linha `collaborator_scores` (`final_points`, `estimated_payment`);
2. o cache JSON `calculation_runs.result_summary.score_summaries[<id>]`;
3. os totais `calculation_runs.result_summary.final_points/estimated_payment` e `.cards`.

E cada consumidor lê um lugar diferente:

| Consumidor | Fonte |
|---|---|
| `serialize_run` → `GET /calculation-runs/{id}`, `/latest`, `/dashboard/summary` (ranking + cards), **Excel de pagamento** | cache (`cached_score_summaries(run)` tem prioridade) |
| `_serialize_history_run` → `GET /calculation-runs` (histórico) | linhas |
| `statement_pdf` → extrato PDF do colaborador | linhas |
| `calculate_and_store_leadership_bonus` → bônus de liderança | linhas |

**Evidência (dado real, fechamento #1601, 07/2026, status `paid`):**

```
resumo_pagamento | soma_scores | diff    | resumo_pontos | soma_pontos
18191.18         | 18271.68    | -80.50  | 54370.80      | 54600.80
```

18 dos 223 colaboradores divergem. Exemplo — ANDRE PERES DA SILVA (id 11):

| Campo | Linha `collaborator_scores` | Cache `score_summaries` |
|---|---|---|
| `final_points` | 370,8 | 356,8 |
| `estimated_payment` | **R$ 129,78** | **R$ 124,88** |
| `balance_adjustment_points` | 0 | −14,0 |

Ou seja: a tela e o Excel de pagamento mostram R$ 124,88; o extrato PDF entregue a essa pessoa e
o histórico mostram R$ 129,78. **Para o mesmo fechamento pago.**

**Causa raiz de código (reproduzida):** em
[`_apply_point_balance_after_payment`](../backend/app/api/routes/calculation_runs.py#L210) as
escritas no cache (linhas 210-215) acontecem **sempre**, mas
`flag_modified(run, "result_summary")` só é chamado dentro de `if adjusted:` (linha 217). O
SQLAlchemy **não detecta mutação in-place de coluna JSON** — quando `adjusted` é `False`, as
escritas no cache são silenciosamente descartadas. Prova isolada executada (sqlite em memória,
nenhum dado real tocado):

```
sem flag_modified -> 356.8
com flag_modified  -> 370.8
```

O par 356,8 / 370,8 do resultado da prova é exatamente o par observado em produção.

**Agravante:** os breakdowns (`cost_by_regional`, `cost_by_group`, `cost_by_subject`,
`cost_by_collaborator`, `penalty_distribution`, `health_by_regional`) **nunca** são recalculados
ao marcar como pago — só `final_points`/`estimated_payment` são. Todos permanecem com os valores
do rascunho para sempre.

**Impacto:** pagamento conferido pela tela diverge do extrato entregue ao colaborador; o bônus de
liderança é calculado sobre uma base diferente da que a tela mostra; a conferência “tela vs
relatório” nunca fecha e ninguém consegue dizer qual dos dois está certo.

---

### C2 — `cost_by_regional` soma o bônus de liderança de novo a cada recálculo (não idempotente)

**Onde:** [leadership_bonus.py:379-418](../backend/app/services/leadership_bonus.py#L379)
(`apply_leadership_bonus_to_cost_by_regional`) e
[leadership_bonus.py:460-467](../backend/app/services/leadership_bonus.py#L460).

A função recebe o `cost_by_regional` **já gravado** e soma o bônus por cima, gravando o resultado
de volta em `run.result_summary`. Ela não parte de uma base limpa nem detecta que o bônus já está
ali. Como `calculate_and_store_leadership_bonus` pode rodar várias vezes sobre o mesmo run
(no cálculo, ao marcar como pago quando há ajuste, e via
`POST /leadership/bonus-results/calculate` — [leadership.py:316](../backend/app/api/routes/leadership.py#L316)),
o bônus é **somado repetidamente**.

**Evidência (fechamento #1601, pago):**

| Comparação | Valor |
|---|---|
| Soma de `cost_by_regional` | **R$ 38.264,02** |
| Total real (técnicos + liderança) | R$ 18.271,68 + R$ 6.011,09 = **R$ 24.282,77** |
| Excesso | **R$ 13.981,25** |

E a lista tem **duas linhas “Liderança sem regional”** (R$ 502,89 e R$ 500,67) — assinatura
inequívoca de aplicações repetidas, porque cada passagem faz `merged.append(...)` de uma linha
nova enquanto o `dict` colapsa as anteriores por nome.

Comparação por regional (mesmo fechamento):

| Regional | `cost_by_regional` | Soma real dos `collaborator_scores` |
|---|---|---|
| UNI - MACHADINHO DOESTE | R$ 6.755,09 | R$ 3.495,80 |
| UNI - JI PARANA | R$ 6.648,90 | R$ 4.133,85 |
| UNI - PRESIDENTE MEDICI | R$ 1.820,65 | R$ 609,21 |

**Impacto:** a tabela “Valor a ser pago por regional” — que é a tabela usada para distribuir o
pagamento por filial — está com mais que o dobro do valor real em um fechamento pago. Quem pagar
por essa tabela paga errado.

**Agravante de permissão:** `POST /leadership/bonus-results/calculate` exige apenas
`calculation:run` (não `is_admin_user`) e **não verifica o status do run** — um não-administrador
consegue alterar o `result_summary` de um fechamento **já pago**.

---

### C3 — Identidade de reincidência por `contract_id`, que não é único por cliente

**Onde:** [scoring_detail.py:385-399](../backend/app/services/scoring_detail.py#L385)
(`_recurrence_identity_for_fields`), configuração `recurrence_identity_fields = contract`.

A configuração ativa hoje usa **somente** `contract`. O `contract_id` vem do
`id_contrato` do IXC e **não identifica um cliente**:

```
contract_id      | O.S. | logins distintos
12371            |   42 |  20
132525           |   29 |  12
82440            |   28 |   7
142107           |   27 |   9
54381            |   26 |  19
```

Total: **509 contratos com mais de um login**, cobrindo **1.868 O.S. (2,52% da base)**. Consulta de
pares elegíveis (mesmo contrato, logins diferentes, ≤30 dias):

```
pares_mesmo_contrato_logins_diferentes_30d = 1757
```

Combinado com as regras de classificação ativas, isso é grave: a regra `#8 "Reincidência de
Alteração de Endereço"` (prioridade 100, `classification=garantia`, `discount_points=true`)
**não tem nenhum filtro no tipo/assunto da O.S. original** — qualquer O.S. seguida em até 30 dias
por uma O.S. de `Manutenção` no mesmo `contract_id` vira garantia e tem os pontos **anulados**
(`recurrence_action = annul_original`). A regra `#3` faz o mesmo com `reincidencia_tecnica`.

Em 07/2026 isso classificou **869 O.S. como garantia/reincidência** (8,1% de 10.685) e anulou
**22.784 pontos (R$ 7.974,40)**.

**Impacto:** técnico A atende o cliente X; técnico B atende o cliente Y no mesmo contrato-guarda-chuva
dentro de 30 dias; o técnico A perde os pontos. E, desde 07/2026, isso também gera **débito no
saldo** cobrado num mês futuro (`detect_post_payment_warranty_debits`).

> ### ⚠️ CORREÇÃO (auditoria pós-implementação, 2026-08-26)
>
> **O enquadramento acima está errado e os números dele não devem ser usados para decidir.**
> A afirmação "1.757 pares de O.S. de clientes diferentes" partiu de logins distintos sob o mesmo
> contrato. Ao comparar o **titular** (`customer_name`), o quadro se inverte:
>
> | Medição | Valor |
> |---|---|
> | Pares com login diferente sob o mesmo contrato, ≤30 dias | 1.757 |
> | Desses, com o **mesmo titular** | **1.756 (99,94%)** |
> | Com titular realmente diferente | **1** — e esse não é pego pela regra |
> | Pares do mesmo titular **pegos pela regra atual** | **798** (128 técnicos, 184 contratos) |
> | Contratos com um único login | 45.496 de 45.995 (98,9%) |
>
> Não é "cliente de outra pessoa anulando os pontos". É **o mesmo titular com mais de um login**
> — ora migração de login (`ana_silva.WMT` → `ana.cristina_UNI`), ora ponto de serviço distinto
> (`nbsteatromunicipalnbo` → `nbscamaramunicipalnbo`, Teatro e Câmara da mesma prefeitura;
> `camera15.riograndeonofre` → `camera8.br364dompedro`, câmeras em locais diferentes).
>
> **Consequência para a decisão: trocar `contract` por `login` NÃO é correção limpa.** Das 501
> combinações de login pegas pela regra, **129 (26%) têm um lado migrado para `_UNI`** — nesses
> casos o contrato está acertando e o login perderia a garantia legítima. O trade-off real é
> entre falso positivo em multi-ponto e falso negativo em migração de login, e resolvê-lo bem
> exige um identificador de instalação que a base hoje não tem.
>
> **Ligação com os créditos pendentes (C4): não existe.** Dos 1.347 débitos compensados por
> crédito manual, **1.329 (98,7%) eram garantias do mesmo login** — legítimas. Os créditos não
> nasceram de falso positivo; nasceram do problema de **atribuição de mês**.

> Observação: `customer_login` está preenchido em 74.065 de 75.177 O.S. (98,5%) e tem 46.665
> valores distintos contra 46.006 de `contract_id` — o login é a identidade mais confiável
> disponível hoje. `_recurrence_identity` (a função “padrão”, não usada por causa da configuração)
> já prioriza login. **Não alterar a configuração antes de decidir e testar** (ver seção 12).

---

### C4 — Ajustes manuais de saldo sem autor identificado, e R$ 3.218,81 pendentes de aplicação automática

**Onde:** [point_balance.py:590-622](../backend/app/services/point_balance.py#L590)
(`create_manual_adjustment`), [point_balance.py:490-560](../backend/app/services/point_balance.py#L490)
(`apply_pending_entries_for_paid_run`).

```
entry_type                  | sem created_by | total
post_payment_warranty_debit |          7358 |  7358
period_settlement           |            44 |    44
manual_adjustment           |          1377 |  1377

audit_logs de point_balance_entry: 8.557 de 9.647 com user_id NULL
```

**100% dos 1.377 ajustes manuais** — o único tipo de lançamento que exige um humano decidindo um
valor — foram criados **sem autor**. A rota oficial
([point_balance.py:88-106](../backend/app/api/routes/point_balance.py#L88)) exige `is_admin_user`
e grava `created_by`; portanto esses lançamentos vieram de **scripts fora da API**, que passaram
`user=None`. As razões (“Estorno de atribuicao errada…”, “Correcao 2026-08-06 (4)…”) confirmam
correções pontuais feitas por script.

Consequência direta — o saldo pendente hoje:

```
colaboradores com saldo pendente : 108
créditos pendentes               : +13.268,00 pontos
débitos pendentes                :  -4.071,40 pontos
saldo líquido pendente           :  +9.196,60 pontos
impacto no próximo fechamento pago: +R$ 3.218,81
colaboradores com saldo POSITIVO :  96
```

`apply_pending_entries_for_paid_run` consome **tudo** que estiver pendente e elegível no momento
em que qualquer fechamento vira `paid`, somando ao `final_points` do mês. Ou seja: **o próximo
fechamento marcado como pago vai pagar R$ 3.218,81 a mais que o trabalho daquele mês**, para 96
pessoas, sem nenhum alerta na tela e sem nenhum autor rastreável para justificar cada crédito.

**Agravante — duplicidade estrutural no ledger:**

```
pares (O.S. original, O.S. retorno) com mais de um lançamento vivo : 393
O.S. originais com mais de um débito vivo                          : 280
  · combinação applied+pending : 263
  · só pending                 :  17
```

Exemplo (`IXC-1165833` / `IXC-1239697`): o lançamento **#557 está `applied`** (já descontado do
fechamento pago #1350) e o **#7697 está `pending`** com o mesmo valor (−14) e mesmo par de O.S.,
criado depois com a razão “Re-lancamento com atribuicao correta… substituindo…”. O #557 **nunca
foi estornado**. O sistema depende de um crédito manual compensatório existir e estar correto para
que a pessoa não seja descontada duas vezes pelo mesmo evento. Isso é reconciliação manual em
ledger financeiro, sem invariante que a garanta.

**Por que os guards não impediram:** `_existing_entry`
([point_balance.py:114-133](../backend/app/services/point_balance.py#L114)) e
`_original_already_debited` ([point_balance.py:136-155](../backend/app/services/point_balance.py#L136))
existem e cobrem o caminho normal, mas (a) rodam com `autoflush=False`, então não enxergam
lançamentos criados no mesmo lote antes do `flush`; (b) **não existe constraint única no banco** em
`(original_os_code, related_os_code)` nem índice em `original_service_order_id`/`original_os_code`
— o guard é só aplicação, e qualquer script que insira direto o contorna.

---

### C5 — Marcar como pago não é serializado, não é idempotente e é longo

**Onde:** [calculation_runs.py:305-329](../backend/app/api/routes/calculation_runs.py#L305).

`PATCH /calculation-runs/{id}/status` carrega o run, valida a transição em memória, consome o
ledger e commita — **sem `SELECT ... FOR UPDATE`, sem lock consultivo, sem `UPDATE ... WHERE
status = 'approved'`**. Buscando por locks no backend inteiro, só os importadores têm
(`ixc_importer.py:90`, `opa_ingestion.py:712`, `operations/ixc_ingestion.py:124`,
`scheduling/sync.py:62`). **Nenhum no caminho de fechamento.**

Em `READ COMMITTED`, duas requisições concorrentes (clique duplo, retry do navegador, dois
operadores) leem `status='approved'`, ambas passam por `ensure_status_transition_allowed`, e ambas
executam `_apply_point_balance_after_payment` — que marca `entry.status = 'applied'` sem cláusula
`WHERE status = 'pending'`. Resultado possível: ledger consumido duas vezes, dois lançamentos
`period_settlement` de carry-over, auditoria duplicada.

**Evidência de que a janela é larga:** no fechamento #1601, `paid_at = 20:10:23` mas o `audit_log`
da mesma transação tem `created_at = 20:10:56` — **33 segundos** entre o início e o commit. A
janela de corrida é de dezenas de segundos, não de milissegundos. Os 33 s são consumidos por
`_refresh_stale_draft_previews` (ver A2).

`ensure_status_transition_allowed` **impede** `paid → paid` em uma requisição posterior (bom), mas
isso não protege contra duas requisições **simultâneas** — que é exatamente o caso do clique duplo.

---

## 5. Riscos altos

### A1 — Crescimento descontrolado de `CalculationRun` / `CollaboratorScore`

`recalculate_current_period` ([calculation.py:547](../backend/app/services/calculation.py#L547)) é
chamado a cada ciclo do `ixc_scheduler` (20 min) e **sempre cria um `CalculationRun` novo** com
~200 `CollaboratorScore`. Nada substitui, nada expira, nada é limpo.

```
período  | runs
2026-05  |    1
2026-06  |   10
2026-07  |  779
2026-08  |  316

calculation_runs      : 1.106  (1.100 draft, 3 paid, 3 cancelled)
collaborator_scores   : 225.121  — 223.811 em rascunhos
leadership_bonus_results: 23.226
```

**779 rascunhos para um único mês.** Isso já degrada `_refresh_stale_draft_previews` (A2),
`latest_run`, o portal (A9) e o histórico, e cresce linearmente com o tempo.

### A2 — `_refresh_stale_draft_previews` varre todos os rascunhos do sistema

[calculation_runs.py:230-251](../backend/app/api/routes/calculation_runs.py#L230): a consulta
seleciona **todos** os runs `draft`/`review`/`approved` **sem filtro de período, sem limite**, com
`selectinload(scores).selectinload(collaborator)` — hoje 1.100 runs × ~205 scores ≈ **224 mil
linhas carregadas em memória** dentro da transação que está marcando um pagamento. É a causa dos
33 s medidos em C5. Com o dobro da base isso vira timeout no meio de um pagamento.

### A3 — Nenhum índice nas colunas usadas por toda consulta de período

Índices reais em `service_orders`: `os_code` (único), `contract_id`, `customer_login`, `diagnosis`,
`os_subject`, `os_type`, `regional`, `id`. **Nenhum em `closed_at`, `opened_at` ou
`collaborator_id`** — exatamente as três colunas que `period_orders` e `recurrence_penalties` usam.

```sql
EXPLAIN (ANALYZE) SELECT * FROM service_orders
 WHERE (closed_at >= '2026-08-01' AND closed_at < '2026-09-01')
    OR (closed_at IS NULL AND opened_at >= '2026-08-01' AND opened_at < '2026-09-01');

Seq Scan on service_orders (cost=0.00..4174.76 rows=1) (actual rows=6989)
  Rows Removed by Filter: 68188
  Execution Time: 36.565 ms
```

Duas coisas: é **Seq Scan** de 75 mil linhas, e o planejador estima **1 linha** onde há **6.989**
(erro de 7.000×) — o que envenena o plano de qualquer join que use essa relação. Também faltam:
`collaborator_scores(calculation_run_id)` e `(collaborator_id)` — em uma tabela de **225 mil
linhas**; `calculation_runs(reference_year, reference_month, status)`;
`point_balance_entries(original_service_order_id)` / `(original_os_code)` / `(related_os_code)` —
lidos a cada par candidato em `_existing_entry`/`_original_already_debited`; `audit_logs(created_at)`.

Consultas que carregam a tabela inteira em memória:
`scoring_matrix.real_subject_keys` ([scoring_matrix.py:44](../backend/app/services/scoring_matrix.py#L44))
faz `SELECT os_code, os_type, os_subject FROM service_orders` sem `WHERE`;
`leadership_bonus.pending_unregistered_for_run`
([leadership_bonus.py:483](../backend/app/services/leadership_bonus.py#L483)) busca todas as O.S.
dos colaboradores sem cadastro sem filtro de período; `GET /point-balance/pending` sem período
retorna **todos** os lançamentos pendentes sem paginação.

### A4 — Limites artificiais de 30 itens em tabelas de custo apresentadas como totais

[scoring_detail.py:2115-2128](../backend/app/services/scoring_detail.py#L2115): `cost_by_subject`,
`cost_by_collaborator`, `top_penalized_subjects`, `top_scoring_subjects`, `top_unmapped_subjects`
são truncados em `[:30]`, sem nenhum campo indicando que houve corte.
[financial-table.tsx:22-23](../frontend/components/gamification/financial-table.tsx#L22) soma as
linhas recebidas e exibe o resultado como total. Medido no #1601: a soma dos 30 primeiros
colaboradores é **R$ 10.495,38** contra R$ 18.271,68 reais — **57% do valor**, apresentado sem
ressalva. Isso viola diretamente a norma §1.5 (“limite artificial é bug silencioso”).

### A5 — `payment_cap` é configurável e não faz absolutamente nada

Definido em [gamification_config.py:63](../backend/app/services/gamification_config.py#L63) e em
`seed.py:86` (“Teto de pagamento. Zero significa sem teto.”), gravado em `app_settings`
(`payment_cap = 0`). Busca em todo o backend e frontend: **não há um único ponto de leitura**. Um
gestor que configurar um teto de pagamento acreditará que ele está valendo.

### A6 — `warranty_mode` é configurável e é inerte para os dados reais

`warranty_mode = no_points` está configurado e o painel de configuração afirma explicitamente
“setting real, lido em explain_order”
([logic-configuration-panel.tsx:2110](../frontend/components/gamification/logic-configuration-panel.tsx#L2110)).
Mas o único ramo que o lê ([scoring_detail.py:1074](../backend/app/services/scoring_detail.py#L1074))
depende de `order.is_warranty or order.is_recurrence`, e o `ixc_importer` grava **ambos como
`False` fixo** ([ixc_importer.py:445-447](../backend/app/services/ixc_importer.py#L445)):

```
is_warranty = 0 · is_recurrence = 0 · de 75.177 O.S.
```

O tratamento de garantia real acontece no motor de reincidência (`RecurrenceClassificationRule`),
que é outro caminho. Resultado: o gestor configura “garantia não pontua”, vê a configuração salva,
e nada muda — porque nenhuma O.S. da base tem a flag.

### A7 — A planilha de pagamento é montada no frontend, a partir do cache, e não é auditada

[use-closure-actions.ts:141-321](../frontend/hooks/use-closure-actions.ts#L141): o Excel
“Exportar pagamento” é gerado inteiramente no cliente com ExcelJS, a partir de `summary.ranking`
(o caminho do cache — C1) e `summary.leadership_bonus`. O artefato usado para efetivamente pagar
pessoas: (a) usa a fonte divergente; (b) não gera nenhum `AuditLog` — não há registro de quem
exportou, quando, com qual filtro de regional, nem quais valores continha. Isso viola a exigência
de rastreabilidade de valores pagos.

### A8 — O extrato PDF do colaborador não fecha consigo mesmo e é acessível com `audit:read`

[statement_pdf.py:262](../backend/app/services/statement_pdf.py#L262): a coluna “Valor” de cada
O.S. é `net_points * point_value` — **sem o multiplicador de saúde**. Para ANDRE PERES
(multiplicador 0,30) a soma da coluna dá ≈ R$ 432,60 (1.236 pts × 0,35) enquanto o resumo do mesmo
PDF diz “Valor a pagar: R$ 129,78”. Diferença de **3,3×** dentro de um documento intitulado
“Extrato de Pagamento - Conferência Individual”.

Além disso: [collaborators.py:242-248](../backend/app/api/routes/collaborators.py#L242) exige
apenas `require_permission("audit:read")` e aceita **qualquer** `collaborator_id`. `audit:read` é
concedida aos perfis `viewer` e `operator` — ou seja, um leitor operacional baixa o extrato
financeiro individual de qualquer pessoa da empresa.

### A9 — O portal do colaborador olha para um fechamento diferente do resto do sistema

[portal_dashboard.py:66-84](../backend/app/services/portal_dashboard.py#L66): `_portal_run` pega
`order_by(desc(created_at), desc(id)).limit(1)` — **o run mais recente, sem filtrar status**,
incluindo rascunhos e cancelados. O resto do módulo usa `pick_run_by_status_priority`
([calculation_closure.py:288](../backend/app/services/calculation_closure.py#L288)), que prioriza
`paid`. Com 1.100 rascunhos gerados automaticamente (A1), **o colaborador vê os números do último
rascunho automático, não do fechamento pago**. Duas respostas oficiais diferentes para “quanto eu
recebi”.

Agravante menor: `_resolve_score` cai em heurística de nome quando não há vínculo direto, e a base
tem um par de homônimos (`thais maciel possamai`, ids 401 e 440).

---

## 6. Riscos médios

### M1 — Horário local do IXC gravado com rótulo UTC

[ixc_importer.py:224](../backend/app/services/ixc_importer.py#L224):
`parsed.replace(tzinfo=timezone.utc)` sobre a string local do IXC. O banco guarda `timestamptz`,
então `2026-08-15 14:00` (14h em Porto Velho) é persistido como `14:00Z` — 4 h adiantado do
instante real. Hoje isso é **internamente consistente** (o `TimeZone` da sessão Postgres é `UTC`,
confirmado, e `period_orders` compara com `datetime` naive), mas:

- qualquer consumidor que faça `astimezone(PORTO_VELHO_TZ)` erra por 4 h;
- `now_utc()` (real) comparado a `closed_at` (deslocado) erra por 4 h;
- **comparar `service_orders` com `operations_*` / `support_opa_*`** — que guardam UTC de verdade —
  produz 4 h de divergência entre módulos, exatamente o tipo de comparação que a norma §7 exige;
- a corretude depende do `TimeZone` da sessão Postgres continuar `UTC`, o que **não está declarado
  em lugar nenhum** (`docker-compose.yml` não fixa `TZ` nem `PGTZ`).

Não há evidência de erro financeiro **hoje**; é uma dependência não declarada que quebra em
silêncio se alguém mudar TZ do container ou comparar módulos.

### M2 — Fronteira de mês em `datetime` naive, sem fuso

[scoring_detail.py:106-135](../backend/app/services/scoring_detail.py#L106) e
[dashboard.py:113-117](../backend/app/api/routes/dashboard.py#L113):
`period_start = datetime(reference_year, reference_month, 1)` — **naive**, comparado contra colunas
`timestamptz`. O Postgres resolve pelo `TimeZone` da sessão. Funciona por causa de M1, mas os dois
erros se cancelando não é uma garantia. A norma §3 exige que a conversão para o dia local aconteça
“na fronteira do filtro, uma vez, no lugar único que monta os bounds” — aqui não há esse lugar
único: `scoring_detail.period_orders`, `scoring_detail.period_orders_for_aggregation` e
`dashboard._period_bounds` repetem a mesma aritmética.

**Ponto positivo:** a lógica de “qual é o mês corrente” usa corretamente `America/Porto_Velho`
([calculation_closure.py:21-38](../backend/app/services/calculation_closure.py#L21)).

### M3 — `FILTERED_BREAKDOWNS_CACHE` é um dict de processo, sem invalidação e sem limite

[dashboard.py:38](../backend/app/api/routes/dashboard.py#L38): cache em memória do módulo,
chaveado por `(run_id, regionais)`, **nunca invalidado** (nem ao recalcular, nem ao pagar) e
**sem teto**. Consequências: (a) valores financeiros congelados até reiniciar o processo;
(b) com mais de um worker uvicorn, requisições idênticas retornam números diferentes conforme o
worker sorteado; (c) crescimento de memória proporcional a `runs × combinações de filtro`.

### M4 — O caminho filtrado por regional não soma o bônus de liderança; o não filtrado soma

Em `/dashboard/filtered-breakdowns`, quando **há** filtro de regional o `cost_by_regional` sai de
`financial_breakdowns` **sem** o bônus ([dashboard.py:426-434](../backend/app/api/routes/dashboard.py#L426));
quando **não há** filtro, retorna o cache **com** o bônus (linha 344) — ou, se não houver cache,
recalcula **sem** o bônus (linha 375). Três composições diferentes no mesmo endpoint. Selecionar e
desselecionar uma regional muda o significado da coluna sem avisar.

### M5 — Todo o dinheiro é `Float`, com `round()` de meio-par

Nenhuma coluna financeira usa `Numeric`/`Decimal`: `CalculationRun.point_value`,
`CollaboratorScore.gross_points/penalty_points/net_points/final_points/estimated_payment/
balance_adjustment_points/balance_after`, `PointBalanceEntry.points`,
`LeadershipBonusResult.base_amount/bonus_amount`, `ScoringGroup.default_points`,
`ScoringSubjectRule.custom_points/point_value_override` — todos `Float`
([models.py:417-437](../backend/app/models.py#L417), [models.py:459-508](../backend/app/models.py#L459)).

O `round()` do Python é meio-par sobre binário (`round(2.675, 2) == 2.67`). Hoje o erro é pequeno
porque o código **acerta** os pontos mais sensíveis: `summarize_details`
([scoring_detail.py:1362-1372](../backend/app/services/scoring_detail.py#L1362)) deriva o valor de
`final` uma única vez quando a taxa é uniforme; `financial_breakdowns` acumula bruto e arredonda
uma vez por bucket; `_distribute_cents_exactly`
([leadership_bonus.py:365-375](../backend/app/services/leadership_bonus.py#L365)) usa o método do
maior resto. Mas a base é frágil: com 383 colaboradores, ~11 mil O.S./mês e valor de ponto de
R$ 0,35, qualquer regressão de arredondamento vira centavos por linha e reais no total, sem
nenhum teste de invariante que detecte.

### M6 — `gross − penalidades ≠ net` por causa do clamp em zero

[scoring_detail.py:1229](../backend/app/services/scoring_detail.py#L1229):
`net_points = round(max(base_points - penalty_points, 0), 2)`. Quando a penalidade supera a base, o
excedente é descartado no `net` mas **continua somando** em `penalty_points`. O extrato PDF
([statement_pdf.py:179-181](../backend/app/services/statement_pdf.py#L179)) exibe as três linhas em
sequência como se subtraíssem — e o fechamento #1601 tem `gross 109.650 − penalty 22.784 = 86.866`
contra um `net` diferente. Quem conferir na mão não fecha.

### M7 — Dois cards diferentes exibem exatamente o mesmo número

[calculation.py:357-358](../backend/app/services/calculation.py#L357): `warranty_service_orders` e
`recurrence_service_orders` são a **mesma expressão** (contam
`RECURRENCE_DISCOUNT_CLASSIFICATIONS`). No #1601 ambos valem 869. Dois rótulos distintos
(“garantia” e “reincidência”) prometendo dimensões diferentes e entregando o mesmo valor — quem
comparar concluirá algo errado sobre a operação.

### M8 — Importação de planilha sem lock e com `os_code` gerado instável

[upvalue_importer.py:533](../backend/app/services/upvalue_importer.py#L533) **não** usa lock
consultivo (diferente do IXC). E `generated_os_code`
([upvalue_importer.py:846-848](../backend/app/services/upvalue_importer.py#L846)) inclui
`row_number` e o `repr` do dicionário da linha inteira no hash — reordenar a planilha ou mudar um
espaço em qualquer coluna gera um `os_code` diferente para a mesma O.S. real. O fallback
`find_existing_service_order` por `(login|contrato, assunto, opened_at)` cobre parte disso, mas
também pode **fundir** duas O.S. legítimas com o mesmo carimbo. Hoje o risco é latente: 100% das
75.177 O.S. têm prefixo `IXC-`, nenhuma `UPV-`.

### M9 — `get_or_create_collaborator` casa só por nome normalizado

[upvalue_importer.py:851-891](../backend/app/services/upvalue_importer.py#L851): dois colaboradores
com o mesmo nome viram um só; um colaborador cujo nome muda de grafia vira dois. A base já tem um
par de homônimos (`thais maciel possamai`). Com 383 pessoas e crescendo, homônimo é questão de
tempo — e a consequência é pontuação e pagamento fundidos.

---

## 7. Riscos baixos

- **B1** — [calculation_runs.py:63-84](../backend/app/api/routes/calculation_runs.py#L63):
  `list_calculation_runs` aplica `.limit(100)` **antes** de filtrar `include_empty` e depois corta
  em `limit` — com 1.100 rascunhos, um filtro por período pode devolver menos do que existe sem
  avisar.
- **B2** — [audit-panel.tsx:204-205](../frontend/components/gamification/audit-panel.tsx#L204):
  o frontend deriva `pointValue = estimated_payment / final_points` e multiplica por O.S.
  (linha 735). Derivação de KPI no cliente — a API deveria entregar o valor por O.S.
- **B3** — [collaborator-orders-sheet.tsx:247](../frontend/components/gamification/collaborator-orders-sheet.tsx#L247):
  `effectivePointValue = pointValue ?? (estimated_payment / (net_points || 1))`. As duas pernas do
  `??` têm significados diferentes (uma inclui o multiplicador de saúde, a outra não) — o mesmo
  O.S. mostra valores diferentes conforme por onde a gaveta foi aberta.
- **B4** — [dashboard-charts.tsx:23-43](../frontend/components/gamification/dashboard-charts.tsx#L23):
  agrega `estimated_payment` por regional no cliente, produzindo um terceiro “por regional”
  diferente do backend (que inclui liderança e usa a regional oficial do colaborador).
- **B5** — [use-closure-data.ts:96-101](../frontend/hooks/use-closure-data.ts#L96):
  `totalAmount = technicianAmount + leadershipAmount` somado no cliente; deveria vir pronto.
- **B6** — [leadership_bonus.py:311-314](../backend/app/services/leadership_bonus.py#L311):
  `average_final_points` é arredondado antes de multiplicar por `point_value` e pelo multiplicador
  (até 3×), amplificando o erro de arredondamento. Efeito ≤ 1 centavo hoje, mas contraria a norma
  §4 (“nunca arredondar antes de calcular”).
- **B7** — Cabeçalho do fechamento
  ([closure-tab.tsx:164-220](../frontend/components/gamification/closure-tab.tsx#L164)) exibe
  período e status, mas **não** exibe origem dos dados nem data da última importação, embora
  `run.source_import_id`/`source_filename` existam. Ver seção 9.

---

## 8. Auditoria de idempotência, histórico e permissões (resumo dos pontos bons)

Para não gerar a impressão de que está tudo errado, os controles que **funcionam** e não devem ser
desfeitos:

- `ensure_no_overlapping_paid_period` ([calculation_closure.py:101](../backend/app/services/calculation_closure.py#L101))
  impede pagar o mesmo colaborador duas vezes no mesmo mês por runs distintos — supre a ausência
  de constraint única em `(mês, ano, regional)`.
- `ensure_period_not_closed` bloqueia recalcular período pago **e** mês já virado (fuso de Porto
  Velho), com mensagem clara.
- `ALLOWED_STATUS_TRANSITIONS` recusa até o reenvio do próprio status terminal.
- `config_snapshot` por `CalculationRun` congela a régua, e `_order_points_from_snapshot`
  ([point_balance.py:42](../backend/app/services/point_balance.py#L42)) usa a régua da época na
  cobrança do débito — decisão correta da spec, implementada.
- `ensure_no_unregistered_payable_collaborators` barra pagamento a quem não tem cadastro formal.
- Importação do IXC: lock consultivo, upsert por chave única, bloqueio de alteração em período
  pago, `ImportRun` + `ImportServiceOrderAudit` por linha.
- Trilha de auditoria ampla: 11.255 registros, cobrindo config, regras, colaboradores, perfis,
  status de fechamento e ledger. A lacuna é de **autor** (C4) e de **exportação** (A7), não de
  cobertura de eventos.
- `WARRANTY_DEBIT_TOOL_CUTOFF` e a restrição ao mês imediatamente anterior limitam corretamente o
  alcance retroativo do débito de garantia.

---

## 9. Auditoria de UX visual (item 12 do escopo)

Avaliado contra a norma visual permanente (`normas-qualidade-dados-metricas.md` §10).

**O que está bom:** o cabeçalho do fechamento tem hierarquia real — badge de status
(“Fechamento pago” / “liberado” / “com pendência”), badge de competência `MM/AAAA`, badge do
estado da apuração, e o “Total a pagar no período” em 40 px como o maior número da tela
([closure-tab.tsx:426-433](../frontend/components/gamification/closure-tab.tsx#L426)). Descontos de
garantia aparecem em vermelho e são clicáveis para a aba de saldo. Há `InfoHint` em cada seção.

**O que precisa mudar:**

1. **Origem e frescor dos dados não aparecem.** A sincronização do IXC está **desligada**
   (`ixc_sync_enabled = false`) e o último sucesso foi em **2026-08-21** — 5 dias atrás — com
   `ixc_sync_last_error = "Falha ao consultar 'su_oss_chamado' no IXC: Name or service not known"`.
   A tela de fechamento não diz nada disso: mostra os números como se fossem atuais. O módulo SGP
   Suporte já resolveu esse problema com um badge “Base até DD/MM · N”; a Gamificação precisa do
   equivalente, e ele é mais crítico aqui porque o número é dinheiro.
2. **Divergência não é sinalizada.** Não existe nenhum alerta quando a soma por colaborador difere
   do total do fechamento (C1) ou quando a soma por regional difere do total a pagar (C2) — as duas
   divergências existem **agora**, em um fechamento pago, e a tela mostra os dois números lado a
   lado sem qualquer aviso.
3. **Premissa escondida em tabela de custo.** “Valor a ser pago por assunto” e o ranking de
   colaboradores mostram um total que é a soma de 30 linhas de um conjunto maior (A4). Precisa de
   rodapé explícito: “30 de N itens · demais R$ X”.
4. **`gross − penalidades ≠ net`** aparece sem explicação na tela e no PDF (M6).
5. **Dois cards com o mesmo número e rótulos diferentes** (M7) — o leitor conclui coisa errada.
6. **O extrato PDF não fecha consigo mesmo** (A8): a coluna “Valor” por O.S. soma 3,3× o “Valor a
   pagar” do mesmo documento. É o artefato de maior risco de interpretação errada do módulo, porque
   é o que chega na mão do colaborador.

---

## 10. Consultas e testes executados

### Testes

| Comando | Resultado |
|---|---|
| `pytest tests/test_calculation_closure.py tests/test_point_balance.py tests/test_scoring_detail.py tests/test_leadership_bonus.py tests/test_gamification_config.py tests/test_collaborators.py tests/test_upvalue_importer.py tests/test_portal_dashboard.py -q` | **85 passed** |
| `pytest -q` (suíte completa) | **668 passed, 13 failed** |

As 13 falhas são **pré-existentes e alheias à Gamificação** — todas no módulo de IA/Operação
Analítica: `test_ai_fields.py` (1), `test_ai_geo.py` (1), `test_ai_governance_fase3.py` (1),
`test_ai_service_description_and_backlog_city.py` (1), `test_ai_sla_stage.py` (4),
`test_ai_team_model_consistency.py` (5). Causa comum verificada em uma delas:
`TypeError: string indices must be integers, not 'str'` em
`tests/test_ai_sla_stage.py:161` — o agregador devolve `str` onde o teste espera `dict`.
**Nenhum código foi alterado nesta sessão**, portanto nenhuma dessas falhas é regressão.

**Cobertura ausente** (norma §8) — nenhum teste existente cobre:
- soma por colaborador × total do run × cache `score_summaries` (C1);
- idempotência de `apply_leadership_bonus_to_cost_by_regional` (C2);
- reincidência entre logins diferentes sob o mesmo `contract_id` (C3);
- duplo `PATCH .../status` concorrente para `paid` (C5);
- `payment_cap` (A5) e `warranty_mode` com `is_warranty=False` (A6);
- soma da coluna por O.S. do PDF × “Valor a pagar” (A8);
- portal × fechamento pago (A9).

### Consultas de sanidade (todas somente leitura)

```sql
-- Volume atual
SELECT 'service_orders',count(*) FROM service_orders
UNION ALL SELECT 'calculation_runs',count(*) FROM calculation_runs
UNION ALL SELECT 'collaborator_scores',count(*) FROM collaborator_scores
UNION ALL SELECT 'point_balance_entries',count(*) FROM point_balance_entries
UNION ALL SELECT 'collaborators',count(*) FROM collaborators
UNION ALL SELECT 'audit_logs',count(*) FROM audit_logs
UNION ALL SELECT 'leadership_bonus_results',count(*) FROM leadership_bonus_results;
-- 75.177 / 1.106 / 225.121 / 8.779 / 383 / 11.255 / 23.226
```

```sql
-- [C1] resumo do run x soma das linhas, nos fechamentos não-rascunho
SELECT r.id, r.status,
       round((r.result_summary->>'estimated_payment')::numeric,2) AS resumo,
       round(SUM(cs.estimated_payment)::numeric,2)                AS soma_linhas,
       round((r.result_summary->>'estimated_payment')::numeric
             - SUM(cs.estimated_payment)::numeric,2)              AS diff
FROM calculation_runs r JOIN collaborator_scores cs ON cs.calculation_run_id=r.id
WHERE r.status IN ('paid','approved','review') GROUP BY r.id ORDER BY r.id;
-- #1350 diff 0.00 · #1354 diff 0.00 · #1601 diff -80.50   ← divergência
```

```sql
-- [C1] quais colaboradores divergem no #1601
WITH cache AS (
  SELECT (kv.key)::int AS collaborator_id,
         (kv.value->>'final_points')::numeric AS cache_final,
         (kv.value->>'estimated_payment')::numeric AS cache_pgto
  FROM calculation_runs r, jsonb_each(r.result_summary->'score_summaries') kv WHERE r.id=1601)
SELECT cs.collaborator_id, c.name, cs.final_points, cache.cache_final,
       cs.estimated_payment, cache.cache_pgto
FROM collaborator_scores cs JOIN cache USING (collaborator_id)
JOIN collaborators c ON c.id=cs.collaborator_id
WHERE cs.calculation_run_id=1601
  AND (cs.final_points<>cache.cache_final OR cs.estimated_payment<>cache.cache_pgto);
-- 18 linhas divergentes
```

```sql
-- [C2] soma por regional x total real
SELECT round(sum((e->>'estimated_payment')::numeric),2)
FROM calculation_runs r, jsonb_array_elements(r.result_summary->'cost_by_regional') e
WHERE r.id=1601;                                        -- 38.264,02
SELECT round(sum(bonus_amount)::numeric,2)
FROM leadership_bonus_results WHERE calculation_run_id=1601;   -- 6.011,09
-- 18.271,68 + 6.011,09 = 24.282,77  →  excesso de 13.981,25
-- e a lista contém DUAS linhas "Liderança sem regional"
```

```sql
-- [C3] contract_id não identifica cliente
SELECT contract_id, count(*) AS os, count(DISTINCT customer_login) AS logins
FROM service_orders GROUP BY 1 ORDER BY 2 DESC LIMIT 8;
-- 12371 → 42 O.S. em 20 logins distintos

WITH c AS (SELECT contract_id, count(DISTINCT customer_login) logins, count(*) os
           FROM service_orders
           WHERE contract_id<>'NAO IDENTIFICADO' AND customer_login IS NOT NULL GROUP BY 1)
SELECT count(*) FILTER (WHERE logins>1), sum(os) FILTER (WHERE logins>1),
       round(100.0*sum(os) FILTER (WHERE logins>1)/sum(os),2) FROM c;
-- 509 contratos · 1.868 O.S. · 2,52%

SELECT count(*) FROM service_orders a JOIN service_orders b
  ON a.contract_id=b.contract_id AND a.id<b.id
 AND a.contract_id<>'NAO IDENTIFICADO'
 AND a.customer_login IS NOT NULL AND b.customer_login IS NOT NULL
 AND a.customer_login<>b.customer_login
 AND b.opened_at>=a.opened_at AND b.opened_at<a.opened_at+interval '30 days';
-- 1.757 pares elegíveis a falsa garantia
```

```sql
-- [C4] rastreabilidade e saldo pendente
SELECT entry_type, count(*) FILTER (WHERE created_by IS NULL) AS sem_autor, count(*)
FROM point_balance_entries GROUP BY 1;
-- manual_adjustment: 1.377 de 1.377 sem autor

SELECT count(DISTINCT collaborator_id), round(sum(points)::numeric,2),
       round(sum(points) FILTER (WHERE points>0)::numeric,2),
       round(sum(points) FILTER (WHERE points<0)::numeric,2),
       round((sum(points)*0.35)::numeric,2)
FROM point_balance_entries WHERE status='pending' AND requires_review=false;
-- 108 colaboradores · +9.196,60 pts (+13.268,00 / -4.071,40) · R$ 3.218,81

SELECT count(*) FROM (SELECT original_os_code FROM point_balance_entries
  WHERE original_os_code IS NOT NULL AND status<>'reverted'
  GROUP BY 1 HAVING count(*)>1) t;
-- 280 O.S. originais com mais de um débito vivo (263 applied+pending, 17 só pending)
```

```sql
-- [A1] acúmulo de rascunhos
SELECT reference_year, reference_month, count(*) FROM calculation_runs GROUP BY 1,2 ORDER BY 1,2;
-- 2026-07: 779 runs · 2026-08: 316 runs
SELECT count(*) FROM collaborator_scores cs JOIN calculation_runs r ON r.id=cs.calculation_run_id
WHERE r.status='draft';   -- 223.811

-- [A3] plano de execução da consulta de período
EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM service_orders
 WHERE (closed_at>='2026-08-01' AND closed_at<'2026-09-01')
    OR (closed_at IS NULL AND opened_at>='2026-08-01' AND opened_at<'2026-09-01');
-- Seq Scan · estimativa 1 linha · real 6.989 · 68.188 removidas pelo filtro

-- [A6] flags de garantia na base
SELECT count(*) FILTER (WHERE is_warranty), count(*) FILTER (WHERE is_recurrence), count(*)
FROM service_orders;   -- 0 · 0 · 75.177

-- Índices reais (nenhum em closed_at/opened_at/calculation_run_id)
SELECT tablename, indexname FROM pg_indexes
WHERE tablename IN ('service_orders','calculation_runs','collaborator_scores','point_balance_entries');

SHOW TimeZone;   -- UTC
```

### Prova isolada (C1)

Script em `scratchpad/json_mutation_probe.py`, executado com **sqlite em memória** dentro do
container — nenhum dado real tocado. Demonstra que mutação in-place de coluna JSON sem
`flag_modified` não é persistida:

```
sem flag_modified -> 356.8
com flag_modified  -> 370.8
```

---

## 10.1 Correções aplicadas (2026-08-26, mesma data da auditoria)

Executadas as Etapas 0 a 4 do plano da seção 11, com aprovação explícita. **Nenhum commit,
nenhum push, nenhuma migration aplicada e nenhum dado real alterado.**

| Achado | O que mudou | Arquivo |
|---|---|---|
| **C1** | `serialize_run` passa a ler **sempre** a linha `collaborator_scores` nos campos financeiros; o cache só serve `regional` e contadores. Novos `result_summary_with_totals_from_scores` (leitura, não muta) e `recompute_run_totals_from_scores` (gravação no pagamento). `flag_modified` saiu de dentro do `if adjusted`. `collaborator_financial_context` centralizado e baseado na linha. | [calculation.py](../backend/app/services/calculation.py), [calculation_runs.py](../backend/app/api/routes/calculation_runs.py), [dashboard.py](../backend/app/api/routes/dashboard.py) |
| **C1 (agravante)** | Novo `refresh_run_breakdowns`: ao marcar como pago, `cost_by_*`, `penalty_distribution` e `health_by_regional` são recalculados em vez de ficarem congelados no rascunho. | [calculation.py](../backend/app/services/calculation.py) |
| **C2** | `apply_leadership_bonus_to_cost_by_regional` virou idempotente: cada linha carrega `leadership_amount` e a reaplicação desfaz o bônus anterior antes de somar o novo; "Liderança sem regional" é reconstruída, nunca duplicada. | [leadership_bonus.py](../backend/app/services/leadership_bonus.py) |
| **C2 (permissão)** | `POST /leadership/bonus-results/calculate` agora exige administrador e recusa (409) fechamento `paid`/`cancelled`. | [leadership.py](../backend/app/api/routes/leadership.py) |
| **C5** | `SELECT ... FOR UPDATE` no fechamento antes de ler o status; consumo do ledger virou `UPDATE ... WHERE status='pending'` com verificação de `rowcount`. | [calculation_runs.py](../backend/app/api/routes/calculation_runs.py), [point_balance.py](../backend/app/services/point_balance.py) |
| **A2** | `_refresh_stale_draft_previews` carrega só as linhas que podem mudar (~26 mil em vez de ~224 mil) e atualiza os totais por delta. | [calculation_runs.py](../backend/app/api/routes/calculation_runs.py) |
| **A8 (permissão)** | Extrato PDF saiu de `audit:read`: só administrador ou o próprio colaborador. Botões escondidos para quem não pode emitir. | [collaborators.py](../backend/app/api/routes/collaborators.py), [collaborator-orders-sheet.tsx](../frontend/components/gamification/collaborator-orders-sheet.tsx) |
| **A3** | Migration `20260826_0077` com 10 índices (`CREATE INDEX CONCURRENTLY`). **Criada, não aplicada.** | [20260826_0077](../backend/alembic/versions/20260826_0077_gamification_financial_indexes.py) |
| **A1** | `prune_superseded_drafts`: remove rascunhos superados do mesmo período, preservando não-rascunhos, os N mais recentes e os referenciados pelo ledger. **Desligada por padrão** (`gamification_draft_retention_enabled`). | [calculation.py](../backend/app/services/calculation.py) |

### Efeito medido no fechamento pago #1601 (somente leitura, banco intocado)

```
soma das linhas no banco      : R$ 18271.68
tabela de colaboradores (API) : R$ 18271.68
result_summary devolvido (API): R$ 18271.68
card Total a pagar (API)      : R$ 18271.68
result_summary GRAVADO no banco (intocado): R$ 18191.18
consistente: True   |   banco alterado: nenhum objeto
```

A API passou a responder um único número. O `result_summary` gravado continua com o valor
antigo — a reconciliação acontece na leitura, sem `UPDATE` em fechamento pago.

### Consumidores de API avaliados (exigência do `manual_desenvolvimento_senior.md`)

- `POST /leadership/bonus-results/calculate` é chamado como **efeito colateral** de salvar/remover
  uma liderança em [page.tsx](../frontend/app/gamificacao/page.tsx) (4 pontos), passando o run
  exibido — que pode ser o pago. Os 4 pontos foram substituídos por
  `refreshLeadershipBonusForCurrentRun()`, que só chama quando o fechamento é editável e o usuário
  é administrador. Sem isso, salvar um perfil de liderança com o fechamento pago aberto passaria a
  falhar em cima de uma operação bem-sucedida.
- `GET /collaborators/{id}/statement.pdf` é chamado pelos dois botões do drawer do colaborador,
  antes sem nenhum controle de permissão na tela.

### Testes criados (6 arquivos, 28 testes)

| Arquivo | Cobre | Falhavam antes |
|---|---|---|
| `test_calculation_run_totals_consistency.py` | C1: detalhe × histórico, linha × cache, totais | 3 de 4 |
| `test_payment_refreshes_breakdowns.py` | C1 agravante: detalhamentos após o pagamento | 2 de 4 |
| `test_leadership_bonus_idempotency.py` | C2: dupla aplicação e linha duplicada | 4 de 4 |
| `test_financial_endpoint_permissions.py` | C2/A8: permissão e fechamento pago | 4 de 5 |
| `test_draft_retention.py` | A1: retenção desligada por padrão e o que ela nunca remove | — (código novo) |
| `test_recurrence_identity.py` | C3: **caracterização**, documenta o risco sem corrigir | — (documental) |

Suíte completa: **696 passed, 13 failed** — as mesmas 13 falhas pré-existentes do módulo de IA
(`test_ai_*`), não relacionadas à Gamificação. Frontend: `typecheck`, `test` (35 passed) e `build`
limpos.

### Verificações NÃO executadas

- **Validação visual real no navegador** das duas mudanças de frontend. O container de produção
  não tem hot reload e exigiria `docker compose build frontend` + `up -d`, que é passo de deploy
  não autorizado nesta rodada.
- **Migration `20260826_0077` não aplicada** (`alembic current` = `20260826_0076`, os 10 índices
  não existem no banco). O arquivo foi removido do container em execução justamente para que um
  restart não a aplicasse sozinho pelo entrypoint.
- **`prune_superseded_drafts` nunca executada** contra a base real: nasce desligada.
- **API em execução ainda serve o código antigo** — os arquivos foram copiados para o container
  apenas para rodar a suíte; o processo uvicorn só carrega as mudanças após rebuild/restart.

---

## 10.2 Auditoria pós-implementação das Etapas 0–4 (2026-08-26)

Revisão independente do que foi entregue, verificando o código real e não as afirmações da
seção 10.1. **Nenhum código foi alterado nesta rodada; só esta documentação.**

### Confirmado no código

| Item | Verificação | Resultado |
|---|---|---|
| `serialize_run` lê a linha | 10 campos financeiros vêm de `score.*`; cache só serve `regional` e contadores | ✅ |
| `result_summary` não é fonte de dinheiro | `result_summary_with_totals_from_scores(run)` na serialização; nenhum leitor de dinheiro no cache além do `gross_*` (ver D3) | ✅ |
| `refresh_run_breakdowns` no pagamento | chamado entre `_apply_point_balance_after_payment` e o bônus | ✅ |
| Bônus idempotente | `leadership_amount` por linha + `UNASSIGNED_LEADERSHIP_REGIONAL` reconstruída | ✅ |
| Ledger com guarda `pending` | `UPDATE ... WHERE id=? AND status='pending'` + `if result.rowcount` | ✅ |
| `FOR UPDATE` no pagamento | `select(CalculationRun.id).where(...).with_for_update()` antes de ler o status | ✅ |
| Permissões | `is_admin_user` em `leadership.py:308` e `collaborators.py:257`; 409 em `paid`/`cancelled` | ✅ |
| Frontend não chama endpoint que dá 409 | 4 pontos → `refreshLeadershipBonusForCurrentRun()`, que barra `paid`/`cancelled` | ✅ |
| Migration criada e não aplicada | arquivo no repo, ausente do container, `alembic current` = `20260826_0076`, **0 dos 10 índices** no banco | ✅ |
| Retenção desligada | `get_setting(..., "false") != "true"` → retorna 0; ligada ao fluxo em `recalculate_current_period` | ✅ |

### Divergências encontradas

**D1 — A9 (portal do colaborador) estava no plano aprovado e NÃO foi entregue.** A Etapa 2 do
plano incluía "`portal_dashboard._portal_run` passa a usar `pick_run_by_status_priority`".
O código segue `order_by(desc(created_at), desc(id)).limit(1)` **sem filtrar status**. Com 1.100
rascunhos automáticos na base, o colaborador continua vendo o último rascunho em vez do
fechamento pago — enquanto a tela de fechamento e o extrato PDF mostram o pago. Nem a seção 10.1
nem o `STATUS.md` registravam essa ausência. **Risco ativo antes de pagar.**

**D2 — `/dashboard/filtered-breakdowns` não recebeu a guarda de consistência.** A guarda
`_regional_breakdown_is_consistent` só existe em `/dashboard/summary`. O caminho sem filtro de
regional desse outro endpoint ([dashboard.py:357](../backend/app/api/routes/dashboard.py#L357))
ainda serve `cost_by_regional` do cache — ou seja, ainda devolveria os R$ 38.264,02 inflados do
#1601. **Não é alcançável pela tela atual** (o frontend só chama esse endpoint com regionais
selecionadas, e nesse caminho o valor é recalculado), mas é alcançável por chamada direta à API.
Risco latente, não ativo.

**D3 — o valor bruto pré-saldo continua vivendo só no cache JSON.**
`_apply_point_balance_after_payment` lê `gross_final_points`/`gross_estimated_payment` de
`score_summaries` (não existem como coluna) para recompor o pagamento, com fallback
`round(net_points * health_multiplier, 2)` quando ausentes. É a única grandeza financeira que
ainda depende do cache. Se o cache estiver errado ou ausente num fechamento antigo, a
recomposição usa uma aproximação.

**D4 — inconsistência entre as duas guardas de administrador que o frontend usa.**
`refreshLeadershipBonusForCurrentRun` exige `currentUser?.role === "admin"`, enquanto
`canEmitStatement` aceita `role === "admin" || can("admin:users:write")` — que é o critério real
do backend (`is_admin_user`). Um administrador por perfil de acesso teria o recálculo do bônus
silenciosamente ignorado. Falha para o lado seguro, mas é incoerente.

### Medição da Etapa 4/A2 (substitui a estimativa)

O texto anterior dizia "~26 mil linhas em vez de ~224 mil" sem medição. Medido na base real:

| | Linhas materializadas | Tempo de SQL |
|---|---|---|
| Consulta antiga (todos os rascunhos) | **223.811** | 56,1 ms |
| Consulta nova (colaboradores afetados + ajuste ≠ 0) | **25.737** | 26,4 ms |

Redução de **8,7×** nas linhas. Ressalva honesta: os 33 segundos medidos no #1601 vinham da
materialização ORM e do laço em Python, não do SQL — 25.737 objetos ainda é muito para dentro de
uma transação de pagamento. **A correção decisiva continua sendo a retenção de rascunhos, que
está desligada.**

### Verificações somente leitura executadas

```
calculation_runs=1106  collaborator_scores=225121  point_balance_entries=8779
service_orders=75177   leadership_bonus_results=23226  collaborators=383  audit_logs=11255
   → idênticos aos números da auditoria original: nenhum efeito colateral.

#1350 paid | linhas=14403.48 tabela=14403.48 resumo=14403.48 cards=14403.48 | gravado=14403.48 | ok
#1354 paid | linhas=16250.85 tabela=16250.85 resumo=16250.85 cards=16250.85 | gravado=16250.85 | ok
#1601 paid | linhas=18271.68 tabela=18271.68 resumo=18271.68 cards=18271.68 | gravado=18191.18 | ok
   → sessão não suja (dirty/new/deleted = False)

lançamentos do ledger aplicados a 08/2026 : 0
último audit_log                          : 2026-08-26 16:41:20 (anterior a esta sessão)
índices da migration 0077 presentes       : 0 de 10
alembic current                           : 20260826_0076
```

### Itens da "Definição de pronto" NÃO satisfeitos

- **Lint**: o `package.json` do frontend não tem script `lint` (`dev | build | start | typecheck |
  test`). Não aplicável — registrado por exigência da seção 1.1 do manual.
- **Validação visual real** (desktop/tablet/celular, estados de loading/vazio/erro/sem permissão)
  das duas mudanças de frontend: não executada, exige build do container.
- **Teste de frontend para a permissão nova**: a seção 10 do manual pede que o frontend valide
  permissões importantes. `canEmitStatement` não tem teste.

---

## 10.3 D1 corrigido + investigação do C3 (2026-08-26)

### D1 — portal do colaborador: RESOLVIDO

Autorizado pelo dono do produto. `_portal_run` passa a usar `pick_run_by_status_priority`,
com uma trava adicional: **sem mês/ano informados, o período é resolvido antes do status** — vale
o período mais recente com apuração não cancelada, e só dentro dele o status decide.

Sem essa trava, a prioridade global por `paid` teria trocado a pergunta do portal: o padrão
pularia de 08/2026 (rascunho do mês corrente) para 07/2026 (pago), escondendo o mês em andamento.
Seria mudança de comportamento não pedida — vedada pela seção 3.1 do
`manual_desenvolvimento_senior.md`.

**O defeito real era pior do que a auditoria registrou.** Medido na base:

| Recorte | Antes | Depois |
|---|---|---|
| 07/2026 | run **#1646, `cancelled`**, R$ 18.453,47 | run **#1601, `paid`**, R$ 18.271,68 |
| 08/2026 | #1936 `draft`, R$ 11.967,06 | inalterado |
| Padrão do portal | #1936 `draft`, R$ 11.967,06 | inalterado |

O colaborador não estava vendo "um rascunho": estava vendo um fechamento **cancelado**, com
R$ 181,79 a mais que o pago. 8 testes novos em `test_portal_run_selection.py` (3 falhavam antes).

### C3 — investigação: o identificador de instalação existe

A dúvida era se o IXC expõe um id de ponto de serviço. **Expõe, e o importador já o lê.**

- `customer_login` vem de `radusuarios.login`, resolvido por `id_login`
  ([ixc_importer.py:399](../backend/app/services/ixc_importer.py#L399)).
- `contract_id` vem de `login.id_contrato` — ou seja, **é o próprio IXC que modela `login` como o
  ponto de serviço dentro de um contrato**.
- `fetch_logins_by_ids` busca o **registro completo** de `radusuarios`
  ([ixc_client.py:374](../backend/app/services/ixc_client.py#L374)), mas o importador persiste
  apenas o nome do login e o contrato — descarta `id_login`, `ativo`, endereço e coordenadas.

Portanto "opção B (login)" e "opção D (id de instalação)" **são a mesma coisa hoje**, e o problema
não é falta de identificador: é que o login **muda** quando o cliente é migrado, e a mesma
instalação passa a ter dois nomes.

**A pergunta que decide, e que não dá para responder com a base local:** `radusuarios.id`
(`id_login`) é estável quando o login é renomeado, ou a migração cria uma linha nova? Se for
estável, persistir `id_login` resolve os dois problemas de uma vez. A API do IXC está
inalcançável (`ixc_sync_last_error` = "Name or service not known"), então isso exige uma consulta
ao IXC.

**Discriminador testado como alternativa (parcial, não recomendado sozinho):** dois logins do
mesmo contrato são a mesma instalação se as janelas de atividade **não se sobrepõem** (um
substituiu o outro); são pontos distintos se **coexistem**. Dos 1.328 pares: **362 coexistem**
(pontos distintos), **966 não coexistem** (migração). Validado contra casos conhecidos: acerta
Teatro/Câmara/Sagrada Família (contrato 12371, janelas fev–ago sobrepostas), acerta
`ana_silva.WMT` → `ana.cristina_UNI` e `arlindonunes` → `arlindo.vieira.nunes_UNI`, acerta as
câmeras do contrato 37907. **Erra** o contrato 10323 (`produtosnaturais` 09/02 e
`adgarescritorio` 10/02): com uma única O.S. por login não há janela para comparar. A heurística
depende de histórico e não substitui o `id_login`.

**Recomendação:** persistir `id_login` em `service_orders` (mudança aditiva, exige migration) e
confirmar a estabilidade dele no IXC antes de alterar qualquer regra. Enquanto isso, **manter
`contract`** é mais seguro que trocar para `login`, que perderia 26% das detecções legítimas.

### Decisão registrada — créditos pendentes (C4)

**Decisão do dono do produto: pagar os créditos como estão, sem recriar os débitos.** Motivo: a
ferramenta de gamificação passou a operar em **julho/2026**; cobrar garantia de O.S. de junho não
faz sentido.

Isso **coincide com o que o código já define**: `WARRANTY_DEBIT_TOOL_CUTOFF = (2026, 7)` em
[point_balance.py:36](../backend/app/services/point_balance.py#L36) recusa origem anterior a
julho. Confirmado que os débitos compensados são exatamente esse caso legado:

| Mês de origem da O.S. | Débitos compensados por crédito | Pontos |
|---|---|---|
| **06/2026** (antes do corte — nunca deveriam existir) | **1.293 (96%)** | −12.686 |
| 07/2026 (legítimos, foram perdoados) | 54 | −582 |

**Consequência que a decisão precisa cobrir:** ainda existem **226 débitos PENDENTES com origem
em 06/2026** (−2.250 pontos = **−R$ 787,50**) que serão cobrados no próximo fechamento pago pela
mesma lógica legada. Pelo critério que a decisão estabeleceu, **eles precisam ser estornados** —
senão o sistema cobra em agosto exatamente o que se decidiu não cobrar. Os outros **189 pendentes
com origem em 07/2026** (−R$ 629,16) são legítimos e devem ser cobrados.

---

## 11. Recomendações e plano de correção por fases

Cada fase deve ser aprovada individualmente antes de virar código (AGENTS.md).

### Fase 0 — Conter o risco imediato, sem tocar em regra (dias)

Nada aqui muda cálculo; só impede que um valor errado seja pago hoje.

1. **Congelar o próximo “marcar como pago”** até C4 ser conferido: existem R$ 3.218,81 líquidos de
   saldo pendente para 96 pessoas que serão somados automaticamente ao próximo fechamento pago.
   Antes disso, um humano precisa validar linha a linha os 1.377 créditos sem autor.
2. **Reconciliar o fechamento #1601** manualmente: decidir qual das duas fontes (R$ 18.191,18 ou
   R$ 18.271,68) corresponde ao que foi efetivamente pago, e registrar a decisão em `STATUS.md`.
3. **Avisar quem opera** que a tabela “por regional” do #1601 está inflada (C2) e não deve ser usada
   para distribuir pagamento.
4. **Adicionar os testes de regressão que hoje faltam** (seção 10), ainda **antes** de corrigir —
   eles devem falhar contra o código atual e provar cada achado.
5. **Restringir o extrato PDF** (A8, permissão) e o `POST /leadership/bonus-results/calculate`
   (C2, permissão + recusa em run pago). São mudanças de autorização, não de cálculo.

### Fase 1 — Fonte única da verdade (C1, C2, M4)

6. Eleger `collaborator_scores` como **a única fonte** do valor por colaborador. `serialize_run`
   passa a ler a linha sempre; `score_summaries` fica apenas com os campos derivados de contagem
   que a linha não tem (ou é eliminado).
7. Recalcular `result_summary.cards` e **todos** os breakdowns ao marcar como pago, não só
   `final_points`/`estimated_payment`.
8. Tornar `apply_leadership_bonus_to_cost_by_regional` idempotente: guardar
   `cost_by_regional_base` (sem liderança) e sempre reaplicar sobre a base, nunca sobre o
   resultado anterior. Uma linha única “Liderança sem regional”, por construção.
9. Unificar a composição de `cost_by_regional` entre os três caminhos do endpoint filtrado.
10. Adicionar uma **invariante verificada em teste e em runtime** (log de aviso): a soma das linhas
    de `collaborator_scores` deve bater com `result_summary.estimated_payment` em qualquer run não
    cancelado.

### Fase 2 — Idempotência e concorrência (C5, C4)

11. `SELECT ... FOR UPDATE` no `CalculationRun` no início do `PATCH /status`, e mudança de status
    condicional (`UPDATE ... WHERE status = <esperado>`).
12. Consumo do ledger com `UPDATE point_balance_entries SET status='applied' WHERE id=... AND
    status='pending'`, verificando o `rowcount`.
13. Tirar `_refresh_stale_draft_previews` da transação de pagamento (fila/job assíncrono) e
    limitá-lo ao período e aos colaboradores afetados.
14. **Constraint única** em `point_balance_entries (original_os_code, related_os_code)` para
    lançamentos não estornados (índice parcial), mais os índices de A3.
15. Proibir criação de lançamento manual sem `created_by` (`NOT NULL` após backfill do histórico
    com um usuário técnico identificável) e exigir que scripts de manutenção passem pela API.

### Fase 3 — Correção de regra financeira (C3, A5, A6, M6) — exige decisão do dono do produto

16. **C3**: decidir a identidade de reincidência. Recomendação: `login` como primeira opção e
    `contract` só como fallback quando não houver login (é o que `_recurrence_identity` já faz).
    **Declarar explicitamente o escopo** (norma §5): só dado novo, ou reprocessar histórico?
    Reprocessar muda fechamentos passados e débitos de garantia já lançados.
17. **C3 (regras)**: revisar as regras `#3` e `#8`, que hoje não filtram tipo/assunto da O.S.
    original — qualquer O.S. seguida de uma `Manutenção` em 30 dias perde os pontos.
18. **A5**: implementar `payment_cap` no service **ou** removê-lo da tela. Não deixar um controle
    financeiro inerte.
19. **A6**: idem para `warranty_mode` — ou o importador passa a marcar `is_warranty`, ou o campo
    sai da tela e a documentação passa a dizer que garantia é tratada só pelo motor de
    reincidência.
20. **M6**: expor `penalidade_efetiva` (limitada à base) separada da penalidade bruta, para
    `gross − penalidade = net` fechar na tela e no PDF.
21. **A8**: a coluna “Valor” por O.S. do PDF passa a incluir o multiplicador de saúde, ou vira
    “Pontos” apenas, com o valor só no resumo.

### Fase 4 — Escala e crescimento (A1, A2, A3, M3)

22. Índices: `service_orders(closed_at)`, `(opened_at)`, `(collaborator_id)`;
    `collaborator_scores(calculation_run_id)`, `(collaborator_id)`;
    `calculation_runs(reference_year, reference_month, status)`;
    `point_balance_entries(original_service_order_id)`, `(original_os_code)`, `(related_os_code)`;
    `audit_logs(created_at)`. Migration aditiva, `CREATE INDEX CONCURRENTLY`.
23. Política de retenção de rascunhos: `recalculate_current_period` **atualiza** o rascunho
    corrente em vez de criar um novo, ou uma rotina apaga rascunhos antigos do mesmo período
    preservando o mais recente e todos os não-rascunho.
24. Paginação obrigatória em `GET /point-balance/pending` sem período.
25. Substituir `FILTERED_BREAKDOWNS_CACHE` por cache com TTL, teto e invalidação por `run_id`, ou
    remover.
26. Filtrar por regional em SQL (hoje é filtro em Python depois de carregar tudo).

### Fase 5 — Precisão, fuso e UX (M1, M2, M5, A4, A7, B7 e seção 9)

27. Migrar valores financeiros para `Numeric(12,2)` (dinheiro) e `Numeric(12,2)` (pontos), com
    `Decimal` e `ROUND_HALF_UP` explícito. Migration de tipo, com backfill validado.
28. Documentar a convenção de fuso (M1) e centralizar os bounds de período em **uma** função com
    `America/Porto_Velho` explícito (M2). Idealmente, corrigir a gravação no importador — mas isso
    exige backfill de 75 mil linhas e é decisão à parte.
29. Devolver `total_items`/`remaining_amount` junto de qualquer lista truncada (A4) e exibir na
    tabela.
30. Mover a geração da planilha de pagamento para o backend, com `AuditLog` do que foi exportado
    (A7).
31. Badge de origem/frescor no cabeçalho do fechamento (“Base do IXC até DD/MM HH:mm · sincronização
    desligada”), e alerta visível quando qualquer invariante de soma não fechar.

---

## 12. Itens que NÃO devem ser alterados ainda

Mexer em qualquer um destes **agora** muda valor histórico ou quebra uma trava que está protegendo:

1. **`recurrence_identity_fields`** — trocar `contract` por `login` muda quais O.S. são garantia e,
   portanto, quantos pontos foram anulados em todos os períodos já calculados. Exige decisão de
   escopo (só dado novo × histórico) registrada antes.
2. **Regras `#3` e `#8` de `recurrence_classification_rules`** — mesmo motivo.
3. **`recurrence_action` (`annul_original`), `recurrence_window_days` (30), `point_value` (0,35),
   `health_below_minimum_multiplier` (0), `cpk_bonus_points` (0,2)** — qualquer alteração é
   mudança de régua financeira.
4. **Os 1.377 ajustes manuais pendentes** — não estornar, não apagar, não “limpar”. Precisam ser
   conferidos um a um contra os débitos que compensam, com decisão registrada. Estornar em massa
   faria 96 pessoas perderem crédito legítimo; aplicar sem conferir pode pagar duas vezes.
5. **Os 3 `CalculationRun` pagos (#1350, #1354, #1601)** e suas linhas de `collaborator_scores` —
   são o registro do que foi pago. A reconciliação do #1601 deve ser **documentada**, não corrigida
   por `UPDATE`.
6. **`ensure_no_overlapping_paid_period`, `ensure_period_not_closed`,
   `ensure_no_unregistered_payable_collaborators`, `ALLOWED_STATUS_TRANSITIONS`,
   `WARRANTY_DEBIT_TOOL_CUTOFF`, restrição ao mês imediatamente anterior** — são as travas que
   estão segurando o resto. Nenhuma deve ser relaxada “para facilitar” uma correção.
7. **`config_snapshot` dos runs existentes** — é o único registro da régua vigente à época.
8. **A gravação de datas do `ixc_importer` (M1)** — corrigir sem backfill coordenado moveria O.S.
   de mês e mudaria fechamentos já pagos.
9. **As 13 falhas de teste do módulo de IA** — são de outro módulo e fora do escopo desta auditoria.

---

## 13. Confirmação de escopo desta rodada

- ❌ Nenhum **commit** feito.
- ❌ Nenhum **push** feito.
- ❌ Nenhum **arquivo de código** alterado (backend ou frontend).
- ❌ Nenhuma **migration** criada ou executada.
- ❌ Nada **apagado, resetado ou revertido**.
- ❌ Nenhum **dado real alterado** — todas as consultas ao Postgres foram `SELECT`/`EXPLAIN`.
- ✅ Testes executados (leitura, banco sqlite isolado da suíte).
- ✅ Prova isolada de C1 em sqlite **em memória**, fora do banco de produção.
- ✅ Documentação criada: este arquivo + atualização de `docs/STATUS.md`.

---

## Referências

- [AGENTS.md](../AGENTS.md) · [docs/00-TRILHA-0.md](00-TRILHA-0.md) · [docs/STATUS.md](STATUS.md)
- [docs/normas-qualidade-dados-metricas.md](normas-qualidade-dados-metricas.md) — §1.5 (limite
  artificial), §2 (fonte única), §3 (fuso e filtros), §4 (arredondamento), §5 (histórico),
  §8 (testes obrigatórios), §10 (regra visual)
- [docs/spec-saldo-pontos-garantia-pos-pagamento.md](spec-saldo-pontos-garantia-pos-pagamento.md)
- [docs/manual_programacao_senior.md](manual_programacao_senior.md) ·
  [docs/manual_frontend_senior.md](manual_frontend_senior.md) ·
  [docs/code_review.md](code_review.md)
- [docs/auditoria-divergencia-opa-suite-2026-08-25.md](auditoria-divergencia-opa-suite-2026-08-25.md)
  — auditoria irmã no SGP Suporte, mesma classe de problema (divergência silenciosa com o
  crescimento da base)
