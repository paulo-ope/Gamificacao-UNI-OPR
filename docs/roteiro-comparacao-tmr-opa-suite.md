# Roteiro — Comparação de TMR entre o sistema local e o painel oficial do OPA Suite

Documento de apoio pontual (Bloco B3). Não é norma permanente — a norma permanente de
métricas é [normas-qualidade-dados-metricas.md](normas-qualidade-dados-metricas.md).
Este roteiro persiste o procedimento de comparação pra não depender do histórico do
chat, e existe pra ser preenchido manualmente com números copiados do painel oficial
do OPA Suite (o sistema local não tem acesso a esse painel).

## 1. Objetivo da comparação

Descobrir se o **TMR do painel oficial do OPA Suite bate com o TMR humano ou com o
TMR geral** do sistema local (`/suporte`). As duas métricas locais são independentes
entre si (uma exclui atendimento de bot, a outra inclui) — sem essa comparação não dá
pra saber qual delas corresponde ao número que o OPA mostra como "TMR".

## 2. Pré-requisitos

- **Bloco B1 implementado**: campo `tmr_all_responses_coverage` (`count`, `total`,
  `percentage`) exposto em `/opa/overview`, `/opa/attendants/{id}/summary` e
  `by_reason` — mostra sobre quantos atendimentos o TMR geral foi calculado, porque a
  cobertura histórica é parcial (0% antes de 20/08/2026, 76–86% depois).
- **Bloco B2 implementado**: campo `imported_data_window` (`min_opened_at`,
  `max_opened_at`, `min_closed_at`, `max_closed_at`, `total_attendances`) exposto em
  `/opa/overview` — mostra a janela real da base importada, sem filtro de período.
- **Mesmo recorte e mesmos filtros dos dois lados** (seção 4) — sem isso qualquer
  divergência é inconclusiva.

## 3. Recortes recomendados

1. **Um dia recente com boa cobertura de TMR geral** — preferencialmente
   `>= 20/08/2026` (cobertura de 76–86% nesse período; antes disso a cobertura é 0%,
   o que invalidaria a comparação).
2. **Últimos 7 dias.**
3. **Mês atual / agosto inteiro** — usar, mas **explicitando a cobertura parcial** do
   TMR geral nesse recorte (a média local é sobre um subconjunto do total, não sobre
   o mês inteiro).

## 4. Filtros que precisam ser iguais nos dois painéis

- **Data usada**: abertura (`opened_at`) ou encerramento (`closed_at`) — escolher um
  e aplicar o mesmo lado a lado. Divergência aqui é a causa mais comum de
  "número diferente" sem ser bug.
- Status (aberto / fechado / todos)
- Canal
- Departamento
- Atendente
- Motivo
- Fuso horário local: `America/Porto_Velho` (UTC-4, sem horário de verão) — dia local
  no OPA precisa corresponder ao dia local calculado pelo sistema.

## 5. Números para copiar do painel oficial do OPA Suite

- Total de atendimentos
- Fechados
- Abertos
- TMA
- TMR (a métrica geral do OPA)
- Primeira resposta, se disponível
- Bot/humano, se disponível

## 6. Números que o sistema local deve mostrar (mesmo recorte)

- Total de atendimentos no mesmo recorte
- TMR humano
- TMR geral
- Cobertura do TMR geral (`tmr_all_responses_coverage`)
- Janela real da base importada (`imported_data_window`)

## 7. Tabela-modelo para preencher

| Recorte | Filtros aplicados | Número no OPA | Número no sistema local | Diferença | Classificação |
|---|---|---|---|---|---|
| 25/08/2026 (Recorte 1) | `closed_at`, status todos, depto. Suporte Técnico + Financeiro (equivalência não confirmada — ver seção 10) | Total 828 · TMA 01:01:47 (3707s) · TMR 00:03:54 (234s) | Total 981 · TMA 02:03:14 (7394s) · TMR humano 00:08:18 (498s) · TMR geral 00:03:44 (224s) | Total +153 (+18,5%) · TMA +3687s (+99,5%) · TMR geral -10s (-4,3%) vs. TMR OPA · TMR humano +264s (+112,8%) vs. TMR OPA | Inconclusivo — ver seção 10 |
| | | | | | |
| | | | | | |

Preencher uma linha por recorte da seção 3 (mínimo 3 linhas: dia recente, 7 dias,
mês atual). Repetir por atendente/motivo se a divergência do agregado não for clara.

## 8. Como classificar a divergência

- **Bate com TMR geral** — sistema correto para essa métrica; usar TMR geral como
  comparável ao OPA.
- **Bate com TMR humano** — OPA provavelmente exclui bot da métrica dele também.
- **Divergência por `opened_at` vs `closed_at`** — um dos dois lados usou base de
  data diferente.
- **Divergência por fuso** — dia local calculado de forma diferente nos dois painéis.
- **Divergência por cobertura parcial** — olhar `tmr_all_responses_coverage.percentage`;
  se baixo, a média local é sobre menos atendimentos que o total do OPA nesse recorte.
- **Divergência por ausência de histórico local** — olhar `imported_data_window`; se o
  recorte começa antes de `min_opened_at`, a base local não tem esses atendimentos.
- **Bug provável** — nenhuma das explicações acima se sustenta e os filtros são
  idênticos dos dois lados.
- **Divergência por equivalência de filtro incerta (categoria adicionada nesta
  execução)** — o total de atendimentos não bate entre OPA e local mesmo com data
  usada, status, fuso e cobertura conferidos. Sinal de que o "Canal"/"Departamento"
  do painel oficial não corresponde 1:1 ao `department_id` usado no filtro local
  (nomes parecidos, população diferente). Enquanto o total não bater, TMA/TMR não são
  comparáveis com confiança — são médias sobre populações diferentes. Precisa de mais
  informação do lado do OPA (screenshot do filtro aplicado, ou lista de
  departamentos/filas que compõem a seleção) antes de reclassificar.

## 9. Próxima decisão (depende do resultado)

- **Se o OPA bater com TMR geral** → usar TMR geral como a métrica comparável ao
  painel oficial daqui pra frente (relatórios, narrativa, cockpit).
- **Se bater com TMR humano** → ajustar a narrativa visual do sistema local pra
  deixar claro que o número comparável ao OPA é o TMR humano, não o geral.
- **Se não bater com nenhum dos dois** → abrir investigação específica (não cobrida
  por este roteiro) — provável bug de cálculo, filtro ou integração.

## 10. Execução — Recorte 1 (25/08/2026)

Executado em 2026-08-26, com os números oficiais do OPA informados pelo usuário.

**Filtros do OPA (informados pelo usuário)**: data 25/08/2026–25/08/2026, base de
data = encerramento, status = todos, canal = "Suporte/Financeiro", departamento =
"Suporte/Financeiro", atendente = todos, motivo = todos.

**Equivalência de filtro usada no sistema local**: o sistema local não tem um campo
"Canal" com valores "Suporte"/"Financeiro" — `channel` local só tem `whatsapp`,
`pabx` e `page` (canal de comunicação, não fila/departamento). O texto do OPA repete
o mesmo valor em "Canal" e "Departamento", então tratei os dois como a mesma
dimensão: departamento. Nomes mais próximos encontrados na base local:
- `Suporte Técnico` (`department_id = 5bf73d1d186f7d2b0d647a61`)
- `Financeiro` (`department_id = 5d1624085e74a002308aa25e`)

Consultado via `opa_overview_service.expanded_overview` (mesma função de serviço
usada pela API, sem SQL solto) com `date_from=2026-08-25`, `date_to=2026-08-25`,
`date_basis=closed_at`, `department_id="5bf73d1d186f7d2b0d647a61,5d1624085e74a002308aa25e"`.

**Números**

| Métrica | OPA oficial | Sistema local | Diferença |
|---|---|---|---|
| Total de atendimentos | 828 | 981 | +153 (+18,5%) |
| Encerrados | 828 | 981 | +153 (+18,5%) |
| Em aberto | 0 | 0 | 0 |
| TMA | 01:01:47 (3707 s) | 02:03:14 (7394 s) | +3687 s (+99,5%) |
| TMR (OPA) / TMR humano (local) | 00:03:54 (234 s) | 00:08:18 (498 s) | +264 s (+112,8%) |
| TMR (OPA) / TMR geral (local) | 00:03:54 (234 s) | 00:03:44 (224 s) | -10 s (-4,3%) |
| Cobertura do TMR geral | — (não existe no OPA) | 97,1% (953 de 981) | alta — não é fator limitante aqui |
| Janela real da base importada | — | 01/08/2026–26/08/2026, 55.925 no total | recorte de 25/08 está dentro da janela — não é ausência de histórico |

**O que os números descartam como causa da divergência**:
- **`opened_at` vs `closed_at`**: descartado — os dois lados usaram encerramento.
- **Ausência de histórico local**: descartado — 25/08 está dentro da janela importada
  (01/08–26/08).
- **Cobertura parcial do TMR geral**: descartado como causa principal — 97,1% de
  cobertura nesse recorte é alta, a média de TMR geral não está distorcida por
  universo pequeno.
- **Fuso horário**: sem evidência de erro — não é possível confirmar 100% sem saber
  o fuso configurado no painel do OPA, mas um erro de fuso normalmente desloca o
  recorte inteiro para o dia anterior/seguinte, o que não explicaria uma diferença de
  +18,5% no total mantendo "0 em aberto" dos dois lados.

**O que ficou pendente**: o **total de atendimentos não bate** (981 vs 828) mesmo com
todo o resto dos filtros alinhados — isso indica que "Suporte Técnico + Financeiro"
não é a mesma população que o filtro "Suporte/Financeiro" do OPA. Enquanto essa
população não bater, TMA e TMR não são estritamente comparáveis (são médias sobre
conjuntos diferentes de atendimentos).

**Sinal preliminar, não conclusivo**: mesmo com a população potencialmente diferente,
**TMR geral local (224 s) ficou muito mais perto do TMR do OPA (234 s) do que TMR
humano (498 s)** — diferença de apenas 10 segundos (-4,3%) contra +264 segundos
(+112,8%) do TMR humano. Isso é consistente com a hipótese de que o "TMR" do OPA
inclui respostas de bot, assim como o TMR geral local — mas não deve ser tratado
como confirmado até o total de atendimentos bater.
**TMA também ficou ~2x maior no sistema local** (7394s vs 3707s) — sinal adicional de
que a população comparada não é idêntica (não é algo que a norma de qualidade de
dados explica só por cobertura ou histórico).

### 10.1 Refinamento — usuário forneceu a tabela por atendente do OPA (828 confirmados)

O usuário colou a tabela oficial do OPA por colaborador para o mesmo recorte
(25/08/2026), com 21 atendentes somando exatamente 828 atendimentos. Isso permite
trocar a equivalência por nome de departamento (seção 10, incerta) por uma
equivalência **por atendente nomeado** — muito mais precisa, porque são pessoas
específicas, não uma categoria com nome parecido.

**O que foi feito**: localizei o `attendant_id` exato de cada um dos 21 nomes na base
local (por nome completo, evitando homônimos — ex.: "Ana Virgínia" ≠ "Ana Santana",
"Anna Heloisa" ≠ "Anna Andrade", "Bruno Assis" ≠ "Bruno Crestan"/"Bruno Caitano") e
rodei a mesma consulta (`expanded_overview`, `date_basis=closed_at`, 25/08/2026)
filtrando só por esses 21 `attendant_id`.

**Resultado agregado**: total local = **977** (ainda não bate com 828 — diferença de
+149, +18%). Ou seja, **trocar a equivalência de departamento por atendente nomeado
exato não fechou a conta** — o total continua divergindo por uma margem parecida à
da tentativa anterior (981 com departamento vs 977 com atendente). Isso descarta a
hipótese de que o problema era só "nome de departamento errado".

**Detalhe por atendente** (local vs OPA, no mesmo dia/mesma base de data):

| Atendente | Local | OPA | Diferença |
|---|---|---|---|
| Kaline Vitoria | 49 | 52 | -3 |
| Victoria Celestino | 65 | 54 | +11 |
| Gabrieli Milani | 78 | 63 | +15 |
| Jennyfer Tavares | 23 | 38 | -15 |
| Joao Barbosa | 24 | 32 | -8 |
| Weslley Meguro | 67 | 48 | +19 |
| Emanuele Araújo | 57 | 45 | +12 |
| Bruna Vieira | 65 | 54 | +11 |
| Bruno Assis | 46 | 33 | +13 |
| Ezequiel Ricardo | 63 | 46 | +17 |
| Eduardo Leite | 8 | 18 | -10 |
| Ana Virgínia | 86 | 64 | +22 |
| Willamy Carrilho | 93 | 80 | +13 |
| Julio César | 35 | 26 | +9 |
| Loryan Paulo | 6 | 6 | 0 |
| Matheus Henrique | 9 | 9 | 0 |
| Maycon Batista | 62 | 54 | +8 |
| Lucas de Oliveira | 63 | 49 | +14 |
| Welington Souza | 1 | 1 | 0 |
| Sabrina da Cunha | 1 | 1 | 0 |
| Anna Heloisa | 76 | 55 | +21 |

**Padrão observado**: os 4 atendentes de volume muito baixo (1–9 atendimentos) batem
exatamente; todos os demais (volume médio/alto) divergem, majoritariamente com o
local **acima** do OPA (+8 a +22), com 4 exceções pra baixo (-3 a -15). Não é um
padrão aleatório — é consistente com atendimentos sendo contados/atribuídos de forma
diferente entre os dois sistemas quando há transferência entre atendentes (handoff),
não com erro de fuso ou de filtro de data.

**Achado à parte, resolvido**: a linha "TOTAL / MÉDIA" da tabela por atendente que o
usuário colou mostra TMR = 00:03:13 (193 s) — diferente do TMR do painel geral do OPA
informado antes (00:03:54, 234 s). Recalculei manualmente a média simples (não
ponderada) dos 19 valores de TMR por atendente com dado (excluindo os 2 "-"): dá
**193,4 s — bate exatamente com a linha TOTAL/MÉDIA da tabela**. Ou seja, essa linha
é a **média das médias por atendente** (cada atendente pesa igual, não pesa pelo
volume dele), não uma média ponderada por atendimento — é um cálculo diferente do
painel geral do OPA (que aparenta ser ponderado, como o TMR geral local). **Os dois
números do OPA (234 s no painel, 193 s na tabela por atendente) não divergem entre
si por erro — são fórmulas diferentes.** O comparável ao TMR geral local (ponderado
por atendimento) é o do painel geral (234 s), não o da tabela por atendente.

**Classificação (mantida, refinada)**: **divergência por equivalência de filtro
incerta** — agora com evidência de que não é um problema de nome de departamento (já
testado com atendente exato e o total continua sem bater). A causa mais provável,
ainda não confirmada, é diferença de atribuição/contagem em atendimentos com
transferência entre atendentes (handoff) — não é algo resolvível tentando outro
valor de filtro, precisa comparar atendimentos individualmente (por protocolo) entre
os dois sistemas.

**Próximo passo sugerido**: escolher 1–2 atendentes com a maior diferença (ex.: Anna
Heloisa +21, Ana Virgínia +22) e comparar, atendimento por atendimento (protocolo),
a lista de atendimentos do OPA vs local nesse dia — isso aponta se são registros
duplicados, atribuição diferente em transferências, ou algo mais específico. Não fiz
essa comparação nesta tarefa (exigiria acesso ao detalhamento por atendimento do
OPA, que não foi fornecido) — sem alterar cálculo de TMR nem filtro no sistema local
até essa confirmação.

### 10.2 Investigação da regra de atribuição — banco local (não conclusiva sobre o OPA)

Investigação puramente de leitura no Postgres local (consultas SQL diretas e via
`opa_overview_service`, sem chamar a API do OPA, sem alterar dado nenhum).

**Limitação estrutural encontrada primeiro (importante)**: `support_opa_attendances`
tem `UniqueConstraint("source_id")` — **uma linha por atendimento**, sempre
atualizada (upsert) pro estado mais recente que a API de listagem do OPA retornou.
O schema **não guarda histórico de transferência** — não existe "primeiro atendente",
"atendente responsável final" separado de "atendente atual", nem um log de handoff.
`attendant_id` é sempre o último valor de `id_atendente` que a API do OPA retornou
pra aquele atendimento. Também não há duplicidade por protocolo: nos 977 atendimentos
filtrados pelos 21 IDs, **977 protocolos distintos e 977 `source_id` distintos** —
zero duplicação.
**Conclusão direta**: não dá pra medir localmente "conta só último atendente" vs
"conta só responsável final" vs "usa outro vínculo" — o dado que distinguiria essas
hipóteses simplesmente não é persistido. Só um envio (mensagem por mensagem, via API
do OPA) revelaria histórico de transferência, e isso está fora do escopo desta tarefa
(leitura local, sem chamar a API do OPA).

**Hipóteses testadas e descartadas** (cada uma com evidência numérica):
- **Deduplicação por protocolo**: descartada — 977 = 977 = 977 (total, protocolos
  distintos, `source_id` distintos).
- **Vazamento pra outro departamento**: descartada — os 977 atendimentos desses 21
  atendentes são 100% `Suporte Técnico` (781) ou `Financeiro` (196); nenhum está em
  outro departamento.
- **Múltiplos atendentes no mesmo atendimento** (campo `motivos` do payload bruto,
  que registra histórico de tags): descartada — nenhum dos 977 tem mais de um
  `idAtendente`/`idDepartamento` distinto dentro do próprio registro.
- **Fuso horário** (limite do dia deslocado entre OPA e local): descartada
  quantitativamente — só 2 dos 977 atendimentos caem na primeira hora local do dia
  (janela mais sensível a erro de fuso) e 0 na última hora; não sustenta um gap de
  149.
- **Atendimento só de bot** (sem humano de fato, mas com `attendant_id` preenchido
  por algum padrão da API): descartada — 950 dos 977 têm `reached_human = true`
  (97,2%).
- **Status diferente de "finalizado"**: descartada — 100% dos 977 têm `status = "F"`.
- **Atendimento aberto em outro dia** (multi-dia): fator menor, não explica o gap —
  só 5 dos 977 foram abertos num dia local diferente de 25/08.

**Hipótese nova, com evidência favorável (não confirmada)**: encerramento em massa
por inatividade. A distribuição de `tma_seconds` desses 977 atendimentos tem uma
cauda longa muito grande — mediana 5.431 s (~1h30) mas média 7.424 s (~2h03) e máximo
361.064 s (~100 horas). Isso é consistente com atendimentos abertos e esquecidos, que
ficam "pendurados" até serem fechados automaticamente por timeout de inatividade (ou
por uma rotina de faxina de fim de expediente), não por um atendimento contínuo real.
Ao filtrar só os atendimentos com TMA até 2h (7.200 s), a média de TMA cai pra
**3.636 s — a apenas 71s (1,9%) do TMA oficial do OPA (3.707 s)**, mas o total cai
pra 634 (menos que os 828 do OPA, então esse corte específico não é a regra exata,
só evidência de que os atendimentos de TMA muito alto puxam a média local pra cima e
provavelmente não entram na contagem/TMA do OPA).
**Padrão visual nos exemplos** (ver protocolos abaixo): vários atendimentos abertos
de manhã (10h–13h) e todos fechados quase juntos no fim da tarde (17h30–19h,
horário local ≈13h30-15h em UTC-4) — consistente com uma rotina de encerramento em
lote no fim do turno, não com o atendente realmente trabalhando neles até aquele
horário.

**Exemplos de protocolos suspeitos (TMA muito alto, candidatos ao excedente)**:

| Atendente | Protocolo | Aberto (UTC) | Fechado (UTC) | TMA |
|---|---|---|---|---|
| Anna Heloisa | UNI2026760877 | 21/08 12:39 | 25/08 16:56 | ~100,3h (aberto há 4 dias) |
| Anna Heloisa | UNI2026773301 | 25/08 12:26 | 25/08 18:20 | ~5,9h |
| Anna Heloisa | UNI2026772203 | 25/08 11:08 | 25/08 17:02 | ~5,9h |
| Anna Heloisa | UNI2026774281 | 25/08 13:15 | 25/08 18:55 | ~5,7h |
| Ana Virgínia | UNI2026772567 | 25/08 11:40 | 25/08 17:47 | ~6,1h |
| Ana Virgínia | UNI2026772543 | 25/08 11:37 | 25/08 17:09 | ~5,5h |
| Ana Virgínia | UNI2026773123 | 25/08 12:15 | 25/08 17:43 | ~5,5h |
| Ana Virgínia | UNI2026772023 | 25/08 10:08 | 25/08 15:24 | ~5,3h |

O caso `UNI2026760877` é o mais extremo — aberto em 21/08 e só fechado em 25/08,
quatro dias depois, com TMA de ~100 horas. Um atendimento assim, se contado no total
do local mas excluído do relatório do OPA (por não representar trabalho real do
atendente naquele dia), já é um candidato direto ao tipo de registro que infla o
total local sem aparecer no oficial.

**Conclusão provável (não confirmada — precisa de dado do lado do OPA pra fechar)**:
o OPA provavelmente **exclui do seu relatório por atendente atendimentos encerrados
por inatividade/timeout** (ou por uma rotina automática de fim de expediente), que o
sistema local conta normalmente porque só enxerga "status = finalizado, fechado no
dia, atendente X" — sem diferenciar um fechamento "trabalhado" de um fechamento
"por inatividade". Isso é consistente com os três sinais observados juntos: TMA ~2x
maior no local, TMR muito próximo (perguntas sobre 1ª resposta não são afetadas por
tempo de inatividade no fim), e vários exemplos de atendimentos com TMA de 5h+
fechados em lote no fim do dia.

**Não é possível confirmar com 100% de certeza a partir do banco local** — o schema
não tem um campo tipo "motivo do encerramento" (manual vs. automático/timeout) que
permitiria testar essa hipótese diretamente por contagem. Confirmar exigiria um dos
dois: (a) o usuário perguntar ao suporte/admin do OPA se o relatório por atendente
exclui encerramentos automáticos por inatividade, ou (b) consultar a API de detalhe
do OPA por atendimento (fora do escopo desta tarefa, que ficou restrita a leitura
local).

**Recomendação de ajuste futuro (não implementar agora)**: se a hipótese acima for
confirmada, um caminho seria capturar/persistir o "motivo do encerramento" retornado
pela API do OPA (se existir esse campo no payload de detalhe) e excluir encerramentos
automáticos por inatividade do TMA/contagem "de atendente" — mantendo os dois números
(bruto vs. "trabalhado") visíveis, nunca substituindo um pelo outro (norma de
qualidade de dados: número ausente é melhor que número errado, e nenhum dos dois
deve desaparecer silenciosamente). Isso é uma mudança de cálculo — precisa de
autorização explícita separada antes de ser implementada.

### 10.3 Busca exaustiva por campo de encerramento automático/timeout — resultado: campo não existe

Investigação de código e dado (sem chamar a API do OPA), pra testar diretamente se
existe algum campo — no modelo, na migration, no payload bruto salvo ou no código de
ingestão — que identifique encerramento automático, timeout/inatividade, quem
encerrou, ou o motivo do encerramento.

**Onde procurei**:
- `backend/app/modules/support/models.py` — todas as colunas de `SupportOpaAttendance`,
  `SupportOpaAttendanceRaw` e `SupportOpaImportRun`.
- Todas as migrations do módulo support (`backend/alembic/versions/*support*`).
- `backend/app/modules/support/opa_ingestion.py` — a função `_normalize_attendance`
  que mapeia o payload bruto do OPA pros campos do banco (com a cadeia completa de
  nomes alternativos que ela tenta pra cada campo, ex. `_first(record,
  "data_encerramento", "dataEncerramento", "closed_at", "closedAt", "encerramento",
  "fim")` — nenhuma dessas cadeias inclui nada como "motivo_encerramento",
  "encerrado_por", "auto_encerramento" ou "timeout").
- `backend/app/services/opa_client.py` — os parâmetros que a integração manda pra API
  do OPA (a única ocorrência de "timeout" no arquivo é o timeout HTTP da própria
  requisição, 30s — não tem relação com o assunto).
- **O payload bruto salvo** (`SupportOpaAttendance.raw_payload` e
  `SupportOpaAttendanceRaw.payload_json` — confirmei no código que
  `raw_payload = record`, ou seja, o dicionário inteiro que a API do OPA devolve é
  salvo sem filtro nenhum, então essas duas tabelas refletem 100% do que a API manda).
  Levantei todas as chaves distintas presentes numa amostra de 3.000 registros
  recentes da tabela raw: **`_id`, `canal`, `canal_cliente`, `canal_id`, `date`,
  `descricao`, `evaluations`, `fim`, `id_atendente`, `id_cliente`, `id_user`,
  `motivos`, `observacoes`, `origem`, `protocolo`, `setor`, `status`, `tags`**.
  Nenhuma dessas chaves representa motivo de encerramento, flag de
  automático/timeout, ou "encerrado por".
  - `origem.tipo`: único campo que parecia promissor pelo nome — na prática só tem
    dois valores em toda a base: string vazia (56.145 registros) ou
    `"anuncioWhatsapp"` (42 registros, indica que a conversa veio de um anúncio) —
    é origem de marketing/campanha, não motivo de encerramento.
  - `status`: só tem o valor `"F"` (finalizado) nos dados analisados — não distingue
    tipo de finalização.

**Achado colateral, com evidência real (mas fraca em volume)**: os campos
`observacoes` (notas internas) e `motivos` (tags aplicadas) guardam um `id_atendente`
por item, que **às vezes diverge do `attendant_id` final do registro** — prova
concreta de que handoff acontece (ex.: `UNI2026760877`, aberto 21/08, tem uma nota
interna assinada por "Leticia Santana" no dia da abertura, mas fechou em 25/08 com
`attendant_id` de Anna Heloisa). Medindo nos 977 atendimentos do recorte: só **11**
(1,1%) têm nota (`observacoes`) de autor diferente do atendente final, **10** (1,0%)
têm `motivos` com `idAtendente` diferente, e **665 dos 977 (68%) não têm nenhuma
`observação` registrada** — ou seja, esse sinal existe mas é raro demais (a nota
interna é opcional, a maioria dos atendimentos não tem nenhuma) pra, sozinho,
explicar um excedente de 149 atendimentos.

**Conclusão**: **NÃO TESTÁVEL** — não existe, no payload que a API de listagem do OPA
retorna (e que o sistema local salva integralmente, sem descartar nada), nenhum
campo que sirva como flag confiável de "encerramento automático/timeout". A hipótese
de encerramento em massa por inatividade (seção 10.2) continua sendo a mais provável
por evidência indireta (distribuição de TMA — mediana 1h30, mas cauda até ~100h, e
filtrar TMA>2h aproxima a média do TMA oficial do OPA), mas **não pode ser confirmada
por um campo dedicado porque ele simplesmente não existe nos dados disponíveis
localmente**. O sinal de handoff via `observacoes`/`motivos` é real, mas raro demais
(≈1%) pra ser a explicação principal do excedente sozinho.

**Recomendação de próximo dado a capturar (não implementar agora)**: a única fonte
que poderia ter mais detalhe é o endpoint de **mensagens por atendimento**
(`opa_client.list_messages`, já chamado durante a importação pra calcular TMR, mas
hoje **descartado depois do cálculo — não é persistido**). O histórico de mensagens
tem `id_atend` por mensagem (usado pra classificar bot/humano — ver
`_human_attendant_ids`/`_message_is_from_human_attendant` em `opa_ingestion.py`), e
**pode** revelar troca de atendente ao longo da conversa de forma mais completa do
que `observacoes`/`motivos` (que são anotações manuais opcionais, não um log
automático). Persistir esse histórico (ou um resumo dele — ex.: lista de
`attendant_id` distintos que responderam, e o primeiro deles) seria a mudança mínima
necessária pra testar a hipótese de handoff com rigor. Isso é uma mudança de
ingestão/schema — precisa de autorização explícita separada, e não resolve sozinho
se a causa real for a inatividade/timeout em vez de handoff propriamente dito.

## 11. Campos preparatórios implementados — resumo por mensagem (ainda sem dado pra 25/08)

A recomendação da seção 10.3 foi implementada (migration `20260826_0076`, aditiva).
`support_opa_attendances` ganhou 6 colunas novas, todas `nullable`, calculadas por
`_message_attendant_summary()` a partir das MESMAS mensagens que `list_messages` já
busca pra TMR — **zero chamada nova à API do OPA**:

- `distinct_human_attendant_ids` (lista de `attendant_id` humanos que responderam)
- `first_human_attendant_id` / `last_human_attendant_id` (por ordem cronológica real
  das mensagens, não pela ordem em que chegam da API)
- `human_message_count` / `bot_message_count` / `client_message_count`

**Importante — isso NÃO resolve a divergência do Recorte 1 (25/08/2026) sozinho**:
esses campos só são preenchidos em importações **novas ou re-processadas** a partir
de agora — os 977 atendimentos já analisados nas seções 10/10.1/10.2 foram
importados antes desta mudança e não têm esses campos preenchidos retroativamente
(nenhum backfill foi rodado, por instrução explícita). Quando o usuário autorizar
uma reimportação/backfill do período de 25/08, esses campos vão permitir testar
diretamente: `first_human_attendant_id != attendant_id` (o atendimento mudou de mão
depois do primeiro humano) seria evidência direta de handoff, algo que antes só dava
pra inferir indiretamente via `observacoes`/`motivos` (seção 10.3, ~1% de cobertura).

**Não altera nenhum cálculo existente** — `tmr_seconds`, `tmr_all_responses_seconds`,
`handled_by_bot`, `reached_human`, `bot_to_human_handoff` continuam calculados
exatamente como antes; os campos novos são só um resumo adicional, aditivo.
