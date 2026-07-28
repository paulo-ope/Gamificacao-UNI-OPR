# Auditoria de continuidade — Gamificação UNI OPR (2026-07-24)

Escopo: revisão manual, linha a linha, dos serviços de apuração/pontuação/saldo de pontos
(backend) e dos componentes de gamificação (frontend), procurando o mesmo padrão dos bugs já
corrigidos nesta sessão: comparações de data inconsistentes, falta de guarda de
dedup/lookback, filtros de colaborador ausentes, e a mesma regra de negócio reimplementada de
forma ligeiramente diferente em dois lugares.

Cada achado traz arquivo + linha, o defeito, um cenário concreto de falha, e o nível de
confiança (**confirmado** = código lido e comportamento verificado; **suspeito** = padrão
identificado mas efeito real não reproduzido contra dados/UI).

---

## Backend — Correctness bugs

### B1. `scoring_status` "Penalizada" pode sobrescrever "Revisão manual" — e isso aparece na tela
**Arquivo:** `backend/app/services/scoring_detail.py`, função `explain_order`, linhas 1174-1179.

```python
if (
    base_points > 0
    and penalty_points > 0
    and scoring_status not in {"Anulada por reincidência", "Anulada por diagnóstico", "Anulada por SLA"}
):
    scoring_status = "Penalizada"
```

Este bloco roda **depois** de qualquer regra (diagnóstico, SLA, reincidência) já ter setado
`scoring_status = "Revisão manual"` (linhas 1043-1046, 1084-1088, 1135-1139, 1160-1163). Como
`"Revisão manual"` não está na lista de exclusão do `not in {...}`, qualquer O.S que tenha
`requires_manual_review=True` **e também** algum outro ponto penalizado numericamente (ex.: SLA
com `subtract_points`, ou diagnóstico com `subtract_points`) tem seu rótulo de exibição
trocado de `"Revisão manual"` para `"Penalizada"`.

**Cenário de falha:** uma O.S cujo diagnóstico está configurado como `requires_review` e cujo
SLA está configurado como `subtract_points` (ambos ativos ao mesmo tempo) — o backend calcula
`requires_manual_review=True` corretamente (o booleano nunca é desfeito, então contagens como
`manual_review_service_orders` continuam certas), mas `scoring_status` vira `"Penalizada"`.

**Impacto confirmado no frontend:** isso não é só teórico.
- Em `frontend/components/gamification/order-audit-drawer.tsx`, o título "Resumo da decisão"
  (`auditOutcomeLabel`, linhas 77-83) é calculado a partir dos booleanos
  (`is_annulled`/`is_unscored`/`requires_manual_review`/`is_penalized`) e por isso mostra
  corretamente **"Revisão manual"**. Mas o badge ao lado (linha 365,
  `scoringStatusEntry(order.scoring_status)`) lê o texto cru do backend e mostra
  **"Penalizada"** em vermelho. O mesmo painel exibe as duas informações contraditórias lado a
  lado.
- Em `frontend/components/gamification/audit-panel.tsx`, o agrupamento por status (linha 74,
  `groupLabel(..., "status")`) e a exportação CSV usam `order.scoring_status` diretamente — uma
  O.S que precisa de revisão manual pode aparecer agrupada sob "Penalizada" em vez de "Revisão
  manual", tornando mais difícil para quem audita achar todas as O.S pendentes de revisão
  usando esse agrupamento (a contagem oficial do card "Aguardando revisão" continua correta
  porque usa o booleano, só o agrupamento textual é que erra).

**Confiança:** confirmado (código lido; efeito sobre a UI verificado por leitura direta dos
dois componentes).

---

### B2. Multiplicador de saúde regional aplicado de forma diferente no total do colaborador vs. na auditoria por período
**Arquivos:**
- `backend/app/services/scoring_detail.py`, `summarize_details` (linhas 1299-1323) — usada por
  `get_collaborator_service_orders_detail` (linha 1647) e por `calculate_scores` em
  `calculation.py` (linha 327) — recebe **um único** `health_multiplier` e aplica esse mesmo
  multiplicador a `net_points` de **todas** as O.S do colaborador no período
  (`final = net * health_multiplier`, linha 1307).
- `backend/app/services/scoring_detail.py`, `summarize_audit_details` (linhas 1354-1406) e
  `calculate_audit_group_summaries` (linhas 1422-1471) — usadas por `get_period_audit` (tela de
  auditoria por período) — buscam o multiplicador **por O.S individual**, usando a regional de
  cada `detail` (`health_by_regional.get(normalize_regional(str(item["regional"])), ...)`,
  linhas 1365 e 1400).

Se um colaborador tiver O.S em mais de uma regional dentro do mesmo período (ex.: um
colaborador "fantasma"/não registrado cuja regional efetiva é só a predominante, ou um técnico
que atende O.S fora da sua regional oficial), o total pago a ele (via `summarize_details`, que
usa só a regional efetiva/oficial) pode divergir do total que a tela de auditoria por período
mostraria somando O.S individualmente com o multiplicador de cada regional.

Na prática, para colaboradores **registrados** (`is_registered=True`), `calculate_scores`
força `official_regional` = regional cadastrada do colaborador sempre que ela é válida (linhas
322-325 de `calculation.py`), então o efeito prático fica limitado a colaboradores não
registrados/"fantasma" (cujo pagamento já é zerado por outra trava, linha 340-341) ou a uma
regional oficial que não bate com nenhuma chave de `health_by_regional`.

**Confiança:** suspeito — o padrão de "mesmo cálculo, duas implementações" está confirmado por
leitura; o cenário de disparidade real (colaborador registrado com O.S relevantes em >1
regional no mesmo período, oficialmente atribuído a uma regional que não é a predominante)
precisaria ser checado contra dados reais para confirmar se ocorre na prática.

---

## Backend — Data integrity / consistency risks

### B3. Reativar um colaborador via sincronização zera `is_registered` sem nenhum comentário justificando
**Arquivos (padrão idêntico em dois lugares):**
- `backend/app/services/upvalue_importer.py`, `get_or_create_collaborator`, linhas 866-868.
- `backend/app/services/operations_sync.py`, `_resolve_collaborator`, linhas 68-70.

```python
if not collaborator.active:
    collaborator.active = True
    collaborator.is_registered = False
```

Sempre que uma nova O.S é casada (por nome ou por `ixc_employee_id`) com um colaborador que
está `active=False`, o código reativa (`active=True`) **e força `is_registered=False`**,
mesmo que o colaborador estivesse `is_registered=True` antes de ser desativado.

**Cenário de falha:** um colaborador formalmente cadastrado (`is_registered=True`) é marcado
`active=False` manualmente por afastamento temporário (férias, licença). Quando ele volta ao
trabalho e o IXC volta a reportar O.S no nome dele, a próxima sincronização o reativa
automaticamente, mas silenciosamente derruba `is_registered` para `False` — fazendo
`estimated_payment` ser zerado para ele (`calculation.py` linha 340-341) até alguém perceber e
recadastrá-lo manualmente. Diferente de todo o resto do código (que documenta cada decisão
deste tipo com um comentário "achado real"), esta linha não tem nenhuma explicação de por que
o reset é intencional.

**Confiança:** suspeito quanto à intenção (o comportamento em si está confirmado por leitura;
não há como saber sem o dono do produto se isso é desejado ou um efeito colateral não
percebido do mecanismo pensado para colaboradores-fantasma recém-descobertos).

---

### B4. `gamification_config.apply_config` descarta silenciosamente regras de assunto sem grupo resolvido
**Arquivo:** `backend/app/services/gamification_config.py`, linhas 219-237 (dentro de `apply_config`).

```python
group_id = group_id_map.get(int(item["group_id"])) if item.get("group_id") else None
if not group_id and item.get("group_name"):
    group_id = group_name_map.get(str(item["group_name"]))
if not group_id:
    continue
```

Se um item de `scoring_subject_rules` referenciar um `group_id`/`group_name` que não existe
mais no ambiente onde a config está sendo aplicada (grupo apagado, renomeado, ou config
aplicada num ambiente diferente do que a exportou), a regra é **silenciosamente ignorada** —
sem contagem de erro, sem warning no retorno da função, sem log.

**Cenário de falha:** um backup/restore de configuração entre ambientes (ex.: produção →
homologação, ou depois de uma limpeza de grupos "zerados") perde regras de pontuação sem
nenhum sinal visível para quem aplicou a config — a régua fica silenciosamente menor do que
antes.

**Confiança:** confirmado o comportamento (código lido); não verifiquei se
`backend/app/api/routes/rules.py` (endpoint que expõe `apply_config`) devolve alguma contagem
de itens ignorados para a tela — se não devolver, o risco é maior.

---

### B5. Default de `active` inconsistente entre tipos de regra na mesma função de import de config
**Arquivo:** `backend/app/services/gamification_config.py`, `apply_config`.

- `ScoringGroup.active` → default `True` (linha 213).
- `ScoringSubjectRule.active` → default `True` (linha 250).
- `DiagnosisPenaltyRule.active` → default `True` (linha 268).
- `RecurrenceClassificationRule.active` → default `True` (linha 314).
- `HealthRule.active` → default `True` (linha 332).
- `SlaPenaltyRule.active` → default **`False`** (linha 283): `rule.active = _bool(item.get("active"), False)`.

O default `False` para `SlaPenaltyRule` bate com o default do próprio modelo
(`models.py` linha 268, `active: Mapped[bool] = mapped_column(Boolean, default=False, ...)`),
então é plausível que seja intencional (regra de SLA nova entra desligada por segurança) — mas
é o único tipo de regra com esse comportamento, e nada no código comenta o motivo da
assimetria.

**Confiança:** suspeito de ser inconsistência não-intencional (baixa severidade — o pior caso
é uma regra de SLA importada sem o campo `active` no payload ficar inativa quando deveria ficar
ativa, o que é um erro "seguro" e não silenciosamente perigoso).

---

## Backend — Dead code / cleanup opportunities

### B6. `calculation.py` mantém uma reimplementação morta e desatualizada de `sla_inside`/matching de regra
**Arquivo:** `backend/app/services/calculation.py`.

Confirmado por busca em todo o repositório (`grep` por `calculation\.(_sla_inside|_matching_scoring_rule|select_health_rule|_order_points|count_orders_without_scoring_rule|recurrence_penalties|_active_scoring_rules)` e por chamadas internas ao próprio arquivo): as funções abaixo são definidas mas **nunca chamadas**, nem de fora do módulo nem de dentro dele:
- `_active_scoring_rules` (linha 103)
- `_matching_scoring_rule` (linha 114)
- `_order_points` (linha 134)
- `count_orders_without_scoring_rule` (linha 139)
- `_sla_inside` (linha 144)
- `recurrence_penalties` (linha 155, wrapper local — não confundir com `scoring_detail.recurrence_penalties`)
- `select_health_rule` (linha 168)

O problema não é só código morto: **`_sla_inside` (linha 144-152) não tem o arredondamento
`round()`** que `scoring_detail.sla_inside` tem (linhas 789-800 de `scoring_detail.py`, com
comentário explicando que o arredondamento é necessário pra bater com o relatório de BI). E
`_matching_scoring_rule` (linha 114-131) ainda implementa o **fallback antigo e já removido**
de "casar por assunto único entre tipos diferentes" — exatamente o comportamento que o
comentário em `scoring_detail.matching_scoring_rule` (linhas 176-183) diz explicitamente que
foi removido por pontuar O.S de um tipo sem regra emprestando pontos de outro tipo.

**Risco:** hoje é só peso morto (nenhuma chamada ativa), mas é uma armadilha para quem for
mexer em `calculation.py` no futuro e reaproveitar essas funções ao invés de delegar para
`scoring_detail` — reintroduziria os dois bugs já corrigidos uma vez.

**Confiança:** confirmado (nenhuma chamada em todo o backend, verificado por grep completo).

---

### B7. Modelo `PenaltyRule` inteiramente morto
**Arquivo:** `backend/app/models.py`, linhas 235-243.

Busca em todo o repositório por `PenaltyRule` só encontra a própria definição do modelo em
`models.py` — nenhuma rota, serviço, seed ou schema o referencia. A tabela provavelmente ainda
existe no banco (via migration), mas não há nenhum caminho de código que leia ou escreva nela.

**Confiança:** confirmado (grep de repositório inteiro, único resultado é a própria classe).

---

### B8. `ScoringRule` ("legado") é mantido sincronizado mas nunca influencia o cálculo real, e tem uma tela/endpoint próprios que ninguém chama
**Arquivos:**
- `backend/app/models.py`, linhas 221-233 (modelo `ScoringRule`).
- `backend/app/api/routes/scoring.py`, linhas 109-160 (`_find_legacy_subject_rules`,
  `_sync_legacy_subject_rule` — mantém `ScoringRule` em sincronia toda vez que uma
  `ScoringSubjectRule` real é criada/editada) e linhas 584-627 (endpoints
  `GET/POST/PUT /scoring-rules`, CRUD completo sobre `ScoringRule`).
- `frontend/lib/api.ts`, linhas 354-358 (`scoringRules()`, `updateScoringRule()`).

O cálculo real de pontos (`scoring_detail.explain_orders` → `matching_scoring_rule`, usado por
`calculate_scores`) só lê `ScoringSubjectRule`. `ScoringRule` nunca é consultado no caminho de
cálculo (confirmado: as únicas leituras de `ScoringRule` no cálculo são as funções mortas do
achado B6). Mesmo assim, toda edição de `ScoringSubjectRule` dispara
`_sync_legacy_subject_rule`, que cria/atualiza/apaga linhas espelho em `ScoringRule` — trabalho
sem efeito nenhum no resultado da apuração.

Pior: existe um endpoint HTTP completo (`/scoring-rules`) para editar essas regras
diretamente, e ele **realmente aceita escritas** — mas **nenhum componente do frontend chama
`api.scoringRules()` ou `api.updateScoringRule()`** (confirmado por grep em todo
`frontend/`). Ou seja, hoje é só overhead invisível; mas se algum dia alguém reativar essa
tela (ou chamar o endpoint via API diretamente, achando que está editando a régua), a edição
não teria efeito nenhum sobre o pagamento real.

**Confiança:** confirmado (grep completo backend + frontend).

---

### B9. `GET /collaborators` (lista simples) não tem nenhum chamador no frontend
**Arquivo:** `backend/app/api/routes/collaborators.py`, linhas 32-42.

```python
@router.get("", response_model=list[CollaboratorOut])
def list_collaborators(...):
    return (
        db.scalars(
            select(Collaborator)
            .join(ServiceOrder, ServiceOrder.collaborator_id == Collaborator.id)
            .distinct()
            ...
```

Note também que este endpoint faz **INNER JOIN** com `ServiceOrder` — um colaborador recém
cadastrado sem nenhuma O.S ainda não apareceria nele mesmo se alguém voltasse a usá-lo.
Busca em `frontend/lib/api.ts` mostra que só existe wrapper para
`collaboratorsRegistry()` (`/collaborators/registry`) e para o `POST /collaborators`; não há
nenhum wrapper nem chamada direta para `GET /collaborators` em nenhum componente.

**Confiança:** confirmado (grep completo do frontend por `"/collaborators"` sem sufixo).

---

### B10. `HealthRule.condition_operator` confirmado morto também no frontend
Complementa o achado #6 já levantado nesta sessão (`select_health_rule` nunca lê o campo).
Verificação adicional feita agora: `frontend/lib/types.ts` linha 820 declara o campo no tipo
`HealthRule`, mas busca em todos os `.tsx` do frontend por `condition_operator` não encontra
nenhum componente que o exiba ou edite. Ou seja, o campo é gravável via `apply_config`
(`gamification_config.py` linha 331), exportável/serializável (`serialize_current_config`,
linha 171), mas não tem UI nenhuma nem efeito nenhum no cálculo — está morto ponta a ponta.

**Confiança:** confirmado.

---

## Frontend — Bugs

### F1. `PointBalancePanel` não protege contra respostas fora de ordem (race condition)
**Arquivo:** `frontend/components/gamification/point-balance-panel.tsx`, `load` (linhas 90-107)
e o `useEffect` que o dispara (linhas 109-111).

```tsx
const load = useCallback(async () => {
  setLoading(true);
  ...
  const data = await api.pointBalancePending(...);
  setEntries(data);
  ...
}, [calculationRunId, referenceMonth, referenceYear]);

useEffect(() => {
  void load();
}, [load]);
```

Não há flag de cancelamento nem AbortController. Se `calculationRunId`/`referenceMonth`/
`referenceYear` mudarem rapidamente (usuário troca de período duas vezes seguidas antes da
primeira resposta chegar), e a primeira requisição (período antigo) responder **depois** da
segunda (período novo) — cenário plausível já que são invocações de rede independentes — o
`setEntries(data)` da resposta antiga sobrescreve os dados corretos do período novo, e a tela
mostra o saldo de garantia do período errado até o usuário atualizar manualmente.

Comparar com `frontend/components/gamification/order-audit-drawer.tsx`, linhas 323-350, que
resolve exatamente esse problema com uma flag `cancelled` dentro do `useEffect` — o mesmo
padrão não foi replicado aqui. É o padrão "mesma necessidade, duas implementações
inconsistentes" outra vez, agora entre dois componentes React em vez de duas funções Python.

**Confiança:** confirmado o gap de proteção (código lido); a manifestação real depende de
timing de rede (não reproduzido nesta sessão, que é somente leitura).

---

### F2. `groupLabel`/CSV export do painel de auditoria herdam o problema do achado B1
**Arquivo:** `frontend/components/gamification/audit-panel.tsx`, linha 74 (`groupLabel`) e
linha 334 (uso em export/agrupamento).

Como descrito em B1, agrupar ou exportar por `order.scoring_status` bruto pode colocar uma O.S
que precisa de revisão manual sob o rótulo "Penalizada" em vez de "Revisão manual", dificultando
que quem está auditando encontre todos os itens pendentes de revisão usando esse agrupamento.

**Confiança:** confirmado (decorre diretamente de B1, que está confirmado).

---

## Frontend — UX/consistency improvements

### F3. Badge/headline resiliente a status desconhecido, mas nenhuma verificação equivalente para `recurrence_classification` livre
**Arquivo:** `frontend/lib/tones.ts`, linhas 55-86 — o padrão usado para `scoring_status`
(registro de valores canônicos + fallback por substring, comentado explicitamente como "texto
livre vindo do backend... nunca indexar o registry direto sem fallback") é uma boa prática que
já mitiga proativamente o risco descrito na B1/F2 headline de "enum novo do backend sem case no
frontend". Vale generalizar esse mesmo padrão (registry + fallback por substring, nunca só
indexação direta) para os pontos onde `recurrence_classification` (que também é parcialmente
texto livre, pois `RecurrenceClassificationRule.classification` é editável pelo admin em
`governance-rules-panel.tsx`) é exibido — não houve tempo nesta sessão para inspecionar todos
os pontos de exibição de `recurrence_classification` e confirmar se todos usam
`recurrence-display.ts`/`recurrenceClassificationLabel` com um fallback seguro; recomenda-se
uma checagem dedicada.

**Confiança:** suspeito / recomendação preventiva — não é um bug confirmado, é uma lacuna de
cobertura desta auditoria (tempo insuficiente para verificar todos os pontos de exibição).

---

## Architecture observations

1. **O padrão raiz dos bugs 1, 2 e 4 (já corrigidos) e do achado B1 (novo) é o mesmo**: uma
   regra de negócio de "tudo ou nada" (anular pontuação, negar pontuação, exigir revisão) é
   calculada em múltiplas etapas sequenciais dentro de `explain_order`, e uma etapa posterior
   pode sobrescrever o rótulo de exibição decidido por uma etapa anterior sem que isso seja
   óbvio a partir do nome da variável (`scoring_status` é uma string mutável reatribuída ~8
   vezes ao longo da função). Um enum/estado imutável com prioridade explícita (ex.: uma lista
   ordenada de prioridades: anulação > revisão manual > penalização > pontuada) eliminaria essa
   classe de bug de uma vez, em vez de depender de `not in {...}` cada vez mais crescente.

2. **Lógica duplicada "centralizada vs. legada" continua presente no código, mesmo já
   desativada.** `calculation.py` ainda carrega uma cópia completa (mas morta) da lógica de SLA
   e matching de regra que já foi corrigida em `scoring_detail.py` (achado B6) — a correção dos
   bugs 1/2 desta sessão foi feita só no lugar certo, mas o lugar errado não foi limpo, criando
   risco de regressão se alguém reconectar essas funções no futuro (ex.: durante uma
   refatoração apressada). O mesmo vale para o par `ScoringRule`/`ScoringSubjectRule` (achado
   B8): a tabela legada continua sendo escrita a cada edição real, então parece "viva" para
   quem olha o histórico de writes, mas é inerte para o resultado financeiro.

3. **Campos de configuração persistidos e editáveis sem contrato de leitura garantido.**
   `HealthRule.condition_operator` (achado #6 original + B10) é o exemplo mais claro: o campo
   é modelado, serializado, tem default, e é aceito de volta por `apply_config` — mas nenhuma
   função de leitura (`select_health_rule`) o consulta, e nenhuma tela o expõe. Não há teste
   automatizado nem convenção de código que garanta que todo campo de regra gravável tem um
   consumidor no motor de cálculo. Uma varredura dedicada "todo campo de `*Rule`/`AppSetting`
   tem pelo menos um `db.scalar`/leitura fora do CRUD de configuração" identificaria outros
   campos na mesma situação sem precisar de uma nova sessão de investigação manual como esta.

4. **Proteção contra race condition em fetch assíncrono é aplicada de forma pontual, não
   sistemática.** `order-audit-drawer.tsx` protege corretamente contra respostas fora de ordem;
   `point-balance-panel.tsx` não (achado F1). Não há um hook compartilhado
   (`useEffect`+`AbortController`/flag de cancelamento) reaproveitado pelos componentes de
   gamificação — cada tela resolve (ou não) o problema à mão. Vale um hook utilitário comum
   (ex. `useAsyncData`) usado por todos os painéis que buscam dados dependentes de filtros que
   mudam rapidamente (período, regional, calculation run).

5. **Decisões de negócio "silenciosas" nem sempre são comentadas, ao contrário do padrão forte
   do resto do código.** A maior parte deste código-base documenta decisões sutis com
   comentários "achado real" explicando o motivo (isso é visivelmente uma prática consciente da
   equipe, encontrada dezenas de vezes durante esta auditoria). O achado B3 (reset de
   `is_registered` ao reativar colaborador) e o achado B4 (drop silencioso de regra sem grupo
   resolvido) quebram esse padrão — nenhum dos dois tem um comentário explicando a intenção,
   o que é o próprio sinal de alerta de que pode não ter sido uma decisão deliberada.

---

## Cobertura desta sessão / limitações

**Lido integralmente, linha a linha:** `scoring_detail.py` (2229 linhas), `point_balance.py`
(561 linhas), `calculation.py` (629 linhas), `calculation_closure.py` (325 linhas),
`operations_sync.py` (337 linhas), `ixc_scheduler.py` (343 linhas), `gamification_config.py`
(378 linhas), `models.py` (575 linhas), `api/routes/calculation_runs.py`,
`api/routes/point_balance.py`, `api/routes/collaborators.py`, trechos relevantes de
`api/routes/scoring.py` e `upvalue_importer.py` (para cross-reference), `use-closure-data.ts`,
`order-audit-drawer.tsx`, `components/ui/collapsible.tsx`, `lib/tones.ts`, e trechos de
`point-balance-panel.tsx`, `closure-tab.tsx` e `audit-panel.tsx`.

**Não lidos integralmente nesta sessão** (verificados só por grep/amostragem ou não
verificados): `api/routes/rules.py` (não li o arquivo inteiro — só inferi seu comportamento a
partir de `gamification_config.apply_config`, achado B4 merece confirmação direta nesse
arquivo), `leadership_bonus.py` (chamado por `calculation.py` mas fora do escopo pedido),
`financial-table.tsx`, `ranking-table.tsx`, `ranking-tab.tsx`, `closure-history-panel.tsx`,
`collaborator-registry-panel.tsx`, `collaborator-balance-history-sheet.tsx`,
`collaborator-orders-sheet.tsx`, `config-ui.tsx`, `logic-configuration-panel.tsx`,
`governance-rules-panel.tsx`, `unmapped-diagnoses-panel.tsx`, `unmapped-subjects-panel.tsx`,
`upvalue-import-panel.tsx`, `user-management-panel.tsx`, `dashboard-charts.tsx`,
`module-sidebar.tsx`, `audit-trail-panel.tsx`, `frontend/app/gamificacao/page.tsx` — foram
abertos parcialmente ou apenas via grep direcionado (ex.: buscando `scoring_status`,
`condition_operator`), não lidos por completo. Uma segunda passada dedicada a esses arquivos
provavelmente renderia mais achados do mesmo tipo, especialmente em
`logic-configuration-panel.tsx`/`governance-rules-panel.tsx` (telas que editam
`RecurrenceClassificationRule`/`SlaPenaltyRule`/`HealthRule` e são o par natural para checar
contra os achados B4/B5/B10) e em `ranking-table.tsx`/`financial-table.tsx` (que provavelmente
também renderizam `scoring_status`/`recurrence_classification`).
