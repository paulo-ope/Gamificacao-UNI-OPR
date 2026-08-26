# Normas de Qualidade de Dados e Métricas

Norma permanente do UNI Workspace. Vale para **toda métrica, filtro, importação e
dashboard** de qualquer módulo — não só do SGP Suporte, que é apenas a fonte da
maioria dos exemplos aqui por ser o módulo onde essas regras foram descobertas na
prática.

Este documento existe porque, conforme a base cresce, divergência de número deixa de
ser detectável no olho: com 500 atendimentos alguém percebe que "faltou um dia"; com
55.000 ninguém percebe. As regras abaixo foram extraídas de causas raiz reais
encontradas em auditoria (ver `auditoria-divergencia-opa-suite-2026-08-25.md`), não
de teoria.

Se este documento conflitar com o código, **o código vence e o documento deve ser
corrigido** — mas a divergência precisa ser registrada, não ignorada.

---

## 1. Princípios de qualidade de dados e métricas

1. **Número errado é pior que número ausente.** Um KPI vazio faz alguém perguntar;
   um KPI errado vira decisão errada. Quando não há dado suficiente, mostre
   "Não disponível" / `null`, nunca `0` nem um palpite.
2. **`NULL` nunca é `False`.** Campo nulo significa "não sabemos", não "não
   aconteceu". Exemplo real: `handled_by_bot`, `reached_human` e
   `bot_to_human_handoff` em `support_opa_attendances` são nullable de propósito —
   `NULL` = atendimento sem mensagem recuperável para classificar. Tratar como
   `False` inflaria "atendimento 100% humano" com dado que simplesmente não existe.
3. **Denominador explícito.** Todo percentual precisa dizer sobre o que foi
   calculado. Exemplo real: `bot_human_metrics` calcula percentuais só sobre
   `classified_attendances`, e a tela informa quantos ficaram de fora
   (`unclassified_attendances`).
4. **Código interno não é rótulo de usuário.** Exemplo real: `customerNameLabel`
   nunca mostra o `customer_id` bruto como nome — cai para "Cliente sem nome
   cadastrado" (existe id, falta nome) ou "Cliente não informado" (não há nem id).
   São dois estados diferentes e a distinção importa para diagnóstico.
5. **Limite artificial é bug silencioso.** Um teto de paginação/coleta que ninguém
   revisita vira truncamento invisível quando a base cresce. Exemplo real:
   `list_clients` tinha `max_records=50000` fixo enquanto a base real do OPA tem
   176k+ clientes — o efeito visível era "cliente sem nome" em massa, e a causa
   levou uma auditoria inteira para ser encontrada.
6. **Toda métrica precisa de dono e definição escrita.** "TMR" não é definição;
   "média dos intervalos entre mensagem do cliente e a próxima resposta de atendente
   humano, ignorando bot" é.

---

## 2. Fonte única de regra

**A métrica oficial vive no backend, em `services/`.** Nunca na rota, nunca na tela.

- Rota (`router.py`) valida entrada, checa permissão e delega. Não calcula KPI.
- Service (`opa_overview_service.py`, `opa_attendant_service.py`, etc.) concentra o
  cálculo. É o único lugar onde a definição da métrica existe.
- Frontend **formata e apresenta**. Não recalcula.

### O frontend não pode recalcular KPI oficial com lista parcial

Esta é a regra mais fácil de violar sem perceber. Se a tela recebe uma página de 25
atendimentos e soma/faz média em cima disso, o número está errado — ele descreve a
página, não o período filtrado.

```ts
// ERRADO — descreve só a página atual, não o recorte de filtros
const tmaMedio = items.reduce((s, i) => s + (i.tma_seconds ?? 0), 0) / items.length;

// CERTO — o backend agrega sobre o recorte inteiro e devolve pronto
const tmaMedio = overview.average_duration_seconds.current;
```

Derivar valor de **apresentação** a partir de campos já entregues é permitido
(ex.: escolher a cor de um badge a partir de `closed_at`, ou montar a label
"X de Y atendimentos" com dois campos que a API já mandou). O que é proibido é
produzir um KPI novo agregando linhas que o frontend só tem parcialmente.

Se a tela precisa de um número que a API não entrega, o caminho é **adicionar o
campo no service**, não calcular no cliente.

### Métricas irmãs não se substituem

Quando uma métrica nova cobre um caso diferente da antiga, ela **soma**, não
substitui. Exemplo real: `tmr_seconds` (TMR humano, ignora bot) e
`tmr_all_responses_seconds` (TMR geral, conta bot) coexistem como colunas e campos
distintos. Trocar o significado de `tmr_seconds` teria quebrado silenciosamente todo
histórico e toda comparação anterior.

---

## 3. Contrato único de filtros

### Fuso horário oficial

**`America/Porto_Velho` (UTC-4, sem horário de verão).** É o fuso operacional da UNI.

- Constante única: `SUPPORT_TIMEZONE` em `opa_filters.py` (equivalente no frontend
  em `opa-module-components.tsx`).
- "Hoje" é o dia corrente **nesse** fuso — não em UTC, não no fuso do navegador de
  quem está olhando a tela.
- O banco guarda `timestamptz` (UTC). A conversão para o dia local acontece na
  fronteira do filtro, uma vez, no lugar único que monta os bounds.

Erro clássico já cometido: um atendimento em `2026-08-25T02:00Z` é **24/08** no fuso
local (22h). Filtrar por UTC coloca ele no dia errado.

### `date_from` / `date_to` são inclusivos

O usuário que digita `01/08 até 26/08` espera os dois dias inteiros dentro do
resultado. Internamente isso vira meia-aberto (`>= início_do_dia_01` e
`< início_do_dia_27`), mas **o contrato exposto é inclusivo**. Nunca exponha
semântica meia-aberta na UI nem na documentação de API.

### `opened_at` vs `closed_at` — a base da data importa

Um atendimento aberto em 24/08 e encerrado em 25/08 **pertence aos dois dias**,
dependendo da pergunta:

- "Quantos atendimentos **entraram** ontem?" → `opened_at`
- "Quantos atendimentos **resolvemos** ontem?" → `closed_at`

O parâmetro `date_basis` (`opened_at` padrão | `closed_at`) existe exatamente para
isso. Regras:

- O **padrão preserva o comportamento anterior** (`opened_at`). Mudança de default
  em filtro é mudança de significado de todo número histórico — exige decisão
  registrada (ver seção 5).
- Métrica de tempo de resolução (TMA) só faz sentido sobre atendimento encerrado.
  Misturar aberto na média puxa o resultado para baixo sem avisar.

### Filtros compartilhados por endpoints

Todos os endpoints do mesmo módulo aplicam o **mesmo objeto de filtro**, pelo mesmo
caminho. No SGP Suporte: `OpaAttendanceFilters` + `apply_opa_attendance_filters`.

Se um endpoint monta os `WHERE` na mão, ele vai divergir dos outros na primeira
mudança de contrato. Exemplo real: `/opa-metrics` monta os bounds manualmente e
precisou de tratamento à parte quando `date_basis` foi adicionado — está registrado
como dívida técnica justamente porque quebra esta regra.

**Ao adicionar um filtro novo, ele precisa ser propagado para todos os endpoints do
módulo na mesma entrega**, ou a tela mostra recortes diferentes na mesma página.

---

## 4. Tempos e médias

### Banco e API sempre em segundos

Nenhuma coluna, nenhum campo de resposta guarda "minutos" ou string formatada.
Sempre inteiro de segundos: `tma_seconds`, `tmr_seconds`,
`tmr_all_responses_seconds`, `average_first_response_seconds`.

Unidade no nome do campo é obrigatória — `duration` é ambíguo, `duration_seconds`
não é.

### O frontend apenas formata

Existe **um** helper de formatação de duração: `secondsLabel` em
`frontend/lib/format-duration.ts`. Toda tela usa ele. Formato:

| Faixa | Saída |
|---|---|
| `< 60s` | `14 s` |
| `< 1h` | `1 min 29 s` |
| `>= 1h` | `1 h 02 min 15 s` |

Formatar não é calcular. O helper nunca muda o valor persistido nem o valor
comparado — só o texto exibido.

### Nunca arredondar antes de calcular a média

Arredondar cada parcela e depois somar acumula erro. A média é calculada sobre os
valores brutos em segundos, e só o **resultado final** é arredondado uma vez.

```python
# ERRADO — cada gap perde precisão antes da média
gaps = [round(g / 60) for g in raw_gaps]
media = sum(gaps) / len(gaps)

# CERTO — média sobre o bruto, arredonda uma vez no fim
media = round(sum(raw_gaps) / len(raw_gaps))
```

### Preservar segundos em valores pequenos

Um TMR de 89 segundos exibido como "1 min" perde a informação que importa — é a
diferença entre "o bot respondeu na hora" e "o bot demorou". Este foi um bug real:
a exibição antiga arredondava tudo acima de 60s para minuto cheio, escondendo
exatamente a granularidade que distingue TMR geral (bot, tipicamente segundos) de
TMR humano (tipicamente minutos/horas).

---

## 5. Histórico, backfill e reprocessamento

**Toda mudança de cálculo deve declarar, por escrito, o que ela afeta:**

| Escopo | Significa |
|---|---|
| Só dado novo | Vale a partir da próxima importação. Histórico mantém o valor antigo. |
| Só histórico | Backfill/reprocessamento pontual, sem mudar a regra corrente. |
| Ambos | Muda a regra **e** reprocessa o passado. Exige decisão explícita. |

O padrão deste projeto é **só dado novo**, porque reimportar histórico do OPA Suite
custa uma chamada de API por atendimento. Isso significa que o histórico é
legitimamente heterogêneo — e isso precisa estar documentado, não descoberto depois.

Casos reais registrados como "só dado novo":

- TMR geral (`tmr_all_responses_seconds`): atendimentos importados antes da coluna
  existir ficam com `NULL`.
- Classificação bot/humano: idem.
- Cadastro manual de agente virtual (`support_opa_attendant_overrides`): afeta a
  classificação de importações **futuras**; atendimentos já importados mantêm a
  classificação vigente na época.

### Quando backfill é obrigatório

- A mudança corrige um **erro** (não uma evolução) e o dado errado já está sendo
  usado para decisão.
- A métrica é comparada contra sistema externo e a diferença de tratamento entre
  período novo e antigo inviabiliza a comparação.
- O campo novo é `NOT NULL` — aí a migration precisa de valor de preenchimento
  pensado, não de um default acidental.

### Nunca mudar interpretação histórica sem registrar

Se `tmr_seconds` passasse a incluir bot, todo relatório anterior mudaria de
significado retroativamente, sem nenhum sinal na tela. Por isso a métrica nova ganhou
coluna nova. **Reinterpretar campo existente exige decisão registrada em
`docs/STATUS.md` com data e motivo.**

---

## 6. Importações

### Toda importação registra a própria execução

Cada execução grava uma linha em uma tabela de run (no SGP Suporte:
`support_opa_import_runs`) com, no mínimo:

| Campo | Para quê |
|---|---|
| `run_id` | Referência única em log, notificação e mensagem de erro |
| `started_at` / `finished_at` | Duração real do ciclo |
| `mode` | `manual` / `scheduled` / `resume` — quem disparou |
| `date_from` / `date_to` | Janela solicitada |
| lookback | Quantos dias para trás o ciclo automático reimporta |
| `created_count` / `updated_count` / `unchanged_count` | O que mudou de fato |
| `rejected_count` + `errors` | O que foi ignorado **e por quê** |
| `status` | `running` / `completed` / `completed_with_warnings` / `interrupted` / `failed` |
| `checkpoint_json` / `next_skip` | Permite retomar de onde parou |

"Rejeitado sem motivo registrado" é proibido — sem o motivo, ninguém consegue
distinguir dado sujo de bug de parser.

### A run precisa ficar visível durante a execução

Gravar a run só no fim da importação torna impossível responder "está rodando
agora?". A linha `status="running"` deve ser **commitada antes** do processamento
longo, em transação própria, para que outra conexão a enxergue.

Cuidado real já documentado: essa transação precisa ser **separada** da sessão que
segura o lock consultivo — dar `commit()` na sessão do lock devolve a conexão ao pool
e pode quebrar o `pg_advisory_unlock` no fim, vazando o lock.

### Status final precisa sobreviver a rollback

Se o chamador faz `db.rollback()` ao tratar a exceção, o `status="failed"` gravado na
mesma sessão some junto — e a run fica presa em `running` para sempre. O status
terminal é gravado em transação própria, já commitada.

### Automática e manual não disputam lock sem mensagem clara

Concorrência entre importações é bloqueada por lock consultivo do Postgres (chave
`913275003` no SGP Suporte). **O lock permanece — o que não pode faltar é
explicação.**

- A checagem de "lock ocupado" precisa ser **somente leitura e não destrutiva**:
  tentar adquirir e liberar imediatamente se conseguir, nunca roubar o lock de quem
  está usando.
- A mensagem ao usuário identifica **quem** está segurando: "A sincronização
  automática do OPA está em andamento. Aguarde a conclusão para iniciar uma
  importação manual." — não "Erro 409".
- Se o lock está ocupado mas a run ativa não é identificável, a mensagem diz isso
  em vez de mentir.
- **Condição esperada não é erro.** Uma tentativa que esbarrou num ciclo anterior
  ainda rodando não deve aparecer em caixa vermelha de "Último erro" — é informação,
  não falha. Isso já causou alarme falso real.

### Intervalo vs duração real do ciclo

Se o ciclo demora mais que o intervalo configurado, `next_allowed_at` calculado no
**início** já nasce no passado. O intervalo é contado a partir do **fim** da
execução anterior.

---

## 7. Validação cruzada

Antes de declarar uma métrica confiável, compare com o sistema de origem em **três
recortes**, sempre no fuso oficial:

1. **Dia pequeno** — baixo volume, dá para conferir na mão. Pega erro grosseiro de
   filtro, fuso e inclusividade de data.
2. **Dia grande** — pico de volume. Pega truncamento de paginação, timeout e limite
   artificial (foi assim que o teto de 50.000 clientes apareceria mais cedo).
3. **Período de 7 dias** — pega erro de borda entre dias e de atendimento que
   atravessa a virada.

### Documentar divergência esperada vs bug

Nem toda diferença é defeito. O que muda é a obrigação de **classificar e registrar**:

| Tipo | Exemplo real | O que fazer |
|---|---|---|
| Divergência esperada | TMR humano (3735s) menor que o painel oficial porque nosso cálculo ignora bot e o deles provavelmente inclui | Documentar a definição de cada lado; manter as duas métricas |
| Divergência de janela | Nosso recorte usa `opened_at`, o painel origem usa data de encerramento | Alinhar `date_basis` ou registrar que são perguntas diferentes |
| Divergência de cobertura | Histórico sem TMR geral porque a coluna é posterior | Registrar como "só dado novo" (seção 5) |
| **Bug** | Nome de cliente ausente em massa por truncamento de sincronização | Corrigir, testar e registrar a causa raiz |

Divergência não classificada vira folclore ("esse número sempre foi meio diferente")
e destrói a confiança no painel inteiro.

---

## 8. Testes obrigatórios para métrica nova

Toda métrica, filtro ou campo derivado novo precisa cobrir estes casos antes de ser
considerado pronto. Eles não são hipotéticos — cada um já quebrou algo neste projeto.

1. **Atendimento aberto em um dia e fechado em outro.**
   Cobre fuso, inclusividade e `date_basis`. Caso real usado: aberto 24/08,
   encerrado 25/08 no fuso local — deve aparecer em `opened_at` só no filtro de
   24/08 e em `closed_at` só no de 25/08.
2. **Bot respondendo antes do humano.**
   Cobre TMR humano vs TMR geral e o handoff. O resultado esperado é TMR geral
   sensivelmente menor que TMR humano — se derem igual, um dos dois está errado.
3. **Cliente sem nome.**
   Duas variações: com `customer_id` e sem. Cobre os dois fallbacks distintos e
   garante que o código bruto nunca vaza como nome.
4. **Atendente virtual manual.**
   Atendente que o sistema de origem **não** marca como bot, mas que está cadastrado
   como `virtual_agent`. Cobre a precedência override > origem > `NULL`.
5. **Status aberto e fechado.**
   Garante que média de duração ignora atendimento aberto e que contagem de
   aberto/encerrado fecha com o total.
6. **Motivo ausente ou múltiplo.**
   Atendimento sem motivo e atendimento com vários. Cobre o "Não informado" e a
   regra de qual motivo entra na agregação (no SGP Suporte: só o primeiro).

Além desses, todo campo novo precisa de um teste de **compatibilidade**: o
comportamento padrão (sem o parâmetro novo) permanece idêntico ao anterior.

---

## 9. Checklist antes de concluir alteração de KPI, filtro ou importação

Copie e responda item a item. "Não se aplica" é resposta válida; deixar em branco não é.

**Definição**
- [ ] A métrica tem definição escrita, em uma frase, sem ambiguidade?
- [ ] O cálculo vive em `services/`, não na rota nem na tela?
- [ ] O frontend só formata, sem recalcular KPI com lista parcial?

**Filtros e tempo**
- [ ] Usa o fuso oficial (`America/Porto_Velho`), não UTC nem o do navegador?
- [ ] `date_from`/`date_to` continuam inclusivos para o usuário?
- [ ] `date_basis` (`opened_at`/`closed_at`) foi considerado e o default preserva o
      comportamento anterior?
- [ ] O filtro novo foi propagado para **todos** os endpoints do módulo?

**Unidades**
- [ ] Banco e API em segundos, com a unidade no nome do campo?
- [ ] Média calculada sobre valores brutos, arredondando só no fim?
- [ ] Exibição usa o helper único de formatação?

**Histórico**
- [ ] Está declarado se afeta dado novo, histórico ou ambos?
- [ ] Se precisa de backfill, está dito explicitamente (mesmo que a decisão seja
      "não fazer por custo")?
- [ ] Nenhum campo existente mudou de significado sem decisão registrada?

**Importação** (quando aplicável)
- [ ] A run registra id, início, fim, modo, janela, lookback, contadores e erros?
- [ ] A run fica visível **durante** a execução, não só no fim?
- [ ] O status final sobrevive a rollback do chamador?
- [ ] Concorrência bloqueada com mensagem clara, sem erro técnico cru?

**Validação**
- [ ] Comparado com a origem em dia pequeno, dia grande e 7 dias?
- [ ] Cada divergência foi classificada como esperada ou bug, e registrada?
- [ ] Os 6 casos da seção 8 estão cobertos por teste?
- [ ] Suíte relevante passa, sem regressão nova?

**Documentação**
- [ ] `docs/STATUS.md` atualizado com o que mudou, o que foi validado e o que ficou
      pendente?

---

## 10. Regra visual permanente

Métrica correta em tela ruim continua não sendo usada. Esta seção é norma
permanente, não fase de projeto: **toda evolução de tela ou dashboard deve melhorar
clareza, densidade e hierarquia visual.**

### O que perseguir

- **Hierarquia clara**: o número que importa é o maior da tela. Label é secundária.
  Ajuda/contexto é terciário e discreto.
- **Densidade organizada**: painel operacional é para análise diária, não para
  impressionar. Informação por centímetro importa — desde que continue escaneável.
- **Composição, não repetição**: agrupe estatísticas relacionadas em um painel único
  com células divididas, em vez de N cards idênticos com moldura própria.
- **Identidade por dimensão**: blocos que respondem perguntas diferentes (Operação,
  Tempo, Clientes, Automação, Distribuição) devem ser visualmente distinguíveis à
  primeira olhada.

### O que evitar

- **Aparência de protótipo cru.** Se parece uma lista de funcionalidades empilhadas
  na ordem em que foram implementadas, precisa de mais uma rodada.
- **Grid infinito de cards iguais.** Repetir o mesmo card com borda, ícone e sombra
  dezenas de vezes anula a hierarquia — tudo com o mesmo peso é o mesmo que nada
  com destaque.
- **Espaço branco sem função.** Atenção especial ao caso já corrigido neste projeto:
  painel pequeno ao lado de lista/tabela longa em grid `items-stretch` — o lado menor
  estica e sobra um vazio grande. Resolva com altura máxima + scroll interno na
  lista, e centralização vertical no bloco menor.
- **Decoração sem informação.** Ícone, cor e borda precisam significar algo. Cor
  repetida em tudo deixa de ser destaque.
- **Erro técnico cru na tela.** `Not Found`, `TypeError`, stack trace ou JSON de
  erro nunca chegam ao usuário final — mensagem amigável em pt-BR, sempre.

### Responsividade e validação

- Desktop, tablet e mobile continuam utilizáveis. Tabela larga usa scroll horizontal
  **interno**; a página nunca rola horizontalmente.
- Texto não corta, não sobrepõe e não estoura container — nem em botão, nem em card,
  nem em drawer.
- Estados de `loading`, `empty` e `error` existem em todo bloco que depende de API.
- **Sempre que mexer em frontend, valide visualmente de verdade**: print da tela ou
  inspeção real no navegador com dado de produção. Typecheck e build passando não
  provam nada sobre layout.
- O frontend roda em container de produção **sem hot reload**. Depois de alterar
  código é obrigatório `docker compose build frontend` + `docker compose up -d
  frontend`, senão o navegador continua mostrando a versão antiga — e a "validação
  visual" valida o build errado.

---

## Referências

- `AGENTS.md` — regras obrigatórias de código, arquitetura e segurança.
- `docs/manual_programacao_senior.md` — backend, banco, Docker, testes.
- `docs/manual_frontend_senior.md` — componentes, estado, responsividade, erros.
- `docs/code_review.md` — checklist de revisão antes do merge.
- `docs/auditoria-divergencia-opa-suite-2026-08-25.md` — auditoria que originou boa
  parte destas regras.
- `docs/proposta-filter-contract-v1.md` — contrato de filtros entre módulos.
- `docs/STATUS.md` — estado atual, decisões recentes e pendências.
