# Plano — Reestruturação da Gamificação Operacional

Data da auditoria: 2026-09-15. Última atualização deste documento: 2026-09-16.

Este documento existe pra qualquer sessão (IA ou pessoa) continuar o trabalho sem precisar
reler o histórico de commits ou repetir a auditoria. `docs/STATUS.md` tem o relato
cronológico completo (com trechos de código e citações); aqui fica o **plano ainda por
fazer**, organizado por fase, com critério de pronto.

## Como este trabalho começou

Pedido do usuário: *"AUDITE 100% O MODULO DE GAMIFICAÇÃO PARA FAZER UMA REESTRUTURAÇÃO
VISUAL DESSE MODULO E PADRONIZAR OTIMIZAR E CORRIGIR BUGS"*.

Rodei 4 auditorias em paralelo (visual/UX, bugs, performance, estrutura) sobre
`frontend/app/gamificacao/page.tsx` (2.064 linhas) e os 22 arquivos de
`frontend/components/gamification/` (14.831 linhas no total). O backend do módulo é o
"core" legado — não fica em `backend/app/modules/`, vive em `backend/app/api/routes/` e
`backend/app/services/`.

## O que já está feito (não repetir)

Detalhe completo com arquivo:linha, citação de código e teste de regressão em
`docs/STATUS.md`, entrada "Auditoria completa da Gamificação Operacional + 2 bugs críticos
corrigidos" (2026-09-15). Resumo:

- **2 bugs CRÍTICOS corrigidos**: débito de garantia em dobro
  (`backend/app/services/point_balance.py`, guarda em memória `debited_original_keys`) e
  `POST /service-orders/delete-period` apagando fechamento pago sem checar `status`
  (`backend/app/api/routes/service_orders.py`, bloqueio incondicional com 409).
- **6 bugs de gravidade ALTA corrigidos**: corridas sem guarda em
  `collaborator-orders-sheet.tsx`/`collaborator-balance-history-sheet.tsx`; exclusão sem
  confirmação em `leadership-bonus-panel.tsx`; `withFeedback` fechando drawer em erro
  (opção `{ rethrow: true }`); card `lost_payment` sem multiplicador de saúde
  (`services/calculation.py`); `FILTERED_BREAKDOWNS_CACHE` sem invalidar ao pagar
  (`api/routes/dashboard.py`); duplicação `lib/charts/chart-palette.ts` vs
  `lib/chart-palette.ts` (unificado no segundo, primeiro apagado).
- **Validado**: `tsc --noEmit` limpo, `vitest run` 83/83, suíte completa do backend
  **1340 passed, 0 failures** (rodada de 2026-09-15, 4h02min).

Isso fecha a **Fase 1 (bugs críticos)** e a **Fase 2 (bugs altos)** do plano original em 5
fases. As fases 3, 4 e 5 abaixo **não foram iniciadas**.

## Fase 3 — Fundação visual (itens 3.1 a 3.6 feitos em 2026-09-16 - ver critério de pronto)

**Objetivo**: alinhar a Gamificação ao design system que o resto do sistema já usa
(`frontend/components/ui/`), sem redesenhar do zero. Referência de "como deveria ser":
`frontend/components/operations/` e `frontend/components/scheduling/`.

### 3.1 — Sistema paralelo em `config-ui.tsx`

`frontend/components/gamification/config-ui.tsx` (809 linhas) exporta ~25 primitivos
próprios (`AppInput`, `AppCombobox`, `AppModal`, `AppDrawer`, `MetricCard`, `AppSwitch`,
`EmptyState` — colide de nome com `ui/empty-state.tsx` —, `PageHeader`, `StepHeroCard`,
`GuidanceCard`, `FilterToolbar`, `RowActionMenu`, `Avatar`, `RegionalMultiSelect`, etc.).

Trabalho, em ordem de segurança:

1. **FEITO (2026-09-16)** — `ErrorState` (linha ~724) era código morto, sem consumidor.
   Removido de `config-ui.tsx`.
2. **FEITO (2026-09-16)** — `AppModal`/`AppDrawer` avaliados: já compõem
   `ui/dialog`/`ui/sheet` por baixo (não são mais sistema paralelo, só um wrapper de
   layout padrão — header/corpo rolável/footer). Migrar os 3 consumidores pro primitivo
   cru duplicaria esse boilerplate em cada um. **Decisão: manter como está**, sem mudança
   de código.
3. **FEITO (2026-09-16)** — `AppMultiSelect` migrado pro `ui/multi-select.tsx` em
   `closure-tab.tsx` e `ranking-tab.tsx` (a duplicação byte-a-byte identificada: bloco de
   filtro de filiais idêntico nos dois arquivos). Sem consumidor restante,
   `AppMultiSelect` também foi removido de `config-ui.tsx` (virou código morto pela
   migração). Validado visualmente nas duas telas (Fechamento → Análise e Ranking):
   dropdown, busca, seleção e contador de filiais funcionam idênticos ao componente
   antigo. `tsc --noEmit` limpo, `vitest run` 83/83.
4. **FEITO (2026-09-16), com correção de escopo** — investigando antes de mexer: só
   `AppSwitch` realmente vazava por IMPORT cruzado (`overview-screen.tsx` e
   `ixc-sync-settings-card.tsx` importavam direto de
   `@/components/gamification/config-ui`). `MetricCard` não tinha esse problema -
   `operations-openings-analytics.tsx` tem sua PRÓPRIA implementação local de mesmo nome
   (`tone` com paleta diferente: `blue/cyan/amber/red/slate`), duplicação de componente,
   não import cruzado; `app/suporte/page.tsx` não usa nenhum dos dois. Migrar `MetricCard`
   agora seria prematuro - a consolidação dele pertence à Fase 5 ("`SummaryCard`
   triplicado", que já lista `ui/summary-metric.tsx` como candidato). Então:
   - `AppSwitch` movido pra `components/ui/switch.tsx`. `config-ui.tsx` passou a
     reexportar de lá (mesmo padrão que `AppCheckbox` já usava), preservando os 5
     consumidores internos sem alteração. Os 2 consumidores externos
     (`overview-screen.tsx`, `ixc-sync-settings-card.tsx`) passaram a importar direto de
     `@/components/ui/switch`.
   - `MetricCard` **não foi movido** - fica pra Fase 5, junto da consolidação com
     `SummaryCard`/`StatStrip`/o `MetricCard` duplicado de `operations-openings-analytics.tsx`.
   - Validado visualmente ao vivo: switch de "Comparar com período anterior" em
     `/visao-geral` e switch de "Sincronização com o IXC" em `/admin` → Integrações,
     ambos alternando corretamente. `tsc --noEmit` limpo, `vitest run` 83/83.
5. **DEFERIDO pra Fase 5, por decisão do próprio plano** — 8 exports (`PageHeader`,
   `StepHeroCard`, `GuidanceCard`, `FilterToolbar`, `ToolbarSearch`, `ToolbarCount`,
   `DataTableFrame`, `SearchableMultiSelect`) são usados por **um único arquivo**:
   `logic-configuration-panel.tsx` (3.075 linhas). Migrar isso isoladamente agora seria
   trabalho perdido - decidir junto com a Fase 5, quando esse arquivo for quebrado em
   seções.

**Seção 3.1 completa** (2026-09-16): itens 1-5 todos resolvidos (3 implementados, 1
avaliado e mantido, 1 formalmente deferido pra Fase 5). Próximo: seção 3.2.

### 3.2 — Card/painel — FEITO (2026-09-16), exceto o deferido

Levantamento antes de migrar: a lista original do item (`closure-history-panel.tsx`,
`point-balance-panel.tsx`) estava desatualizada — `point-balance-panel.tsx` **já não usa
`.panel`** (não tem wrapper próprio, é embutido puro numa `TabsContent` de
`app/gamificacao/page.tsx`; commits anteriores a este já removeram o shell). Levantei o
uso REAL de `.panel`/`.panel-header`/`.panel-title`/`.panel-subtitle` no código antes de
mexer: 10 arquivos, dos quais 1 (`logic-configuration-panel.tsx`) fica deferido junto da
Fase 5 (é o mesmo arquivo do item 3.1.5) e 1 (o `PageHeader` de `config-ui.tsx`) é um dos 8
exports também deferidos - migrar teria efeito zero até a quebra do arquivo grande.

Migrados pra `ui/card` (`Card`/`CardHeader`/`CardTitle`), menor pra maior, cada um com
`tsc --noEmit`/`vitest run` limpos e validado visualmente ao vivo (login real):
`closure-history-panel.tsx`, `governance-rules-panel.tsx`, `ranking-tab.tsx`,
`unmapped-diagnoses-panel.tsx`, `unmapped-subjects-panel.tsx`, `dashboard-charts.tsx` (5
cards de gráfico), `upvalue-import-panel.tsx`, `audit-panel.tsx`, e o wrapper de
`AuditTrailPanel` em `app/gamificacao/page.tsx` (linha ~1866).

**Decisão de escopo**: os 12 estados de "Carregando..." espalhados por `page.tsx`
(`className="panel p-8"...`) NÃO foram tocados aqui, mesmo usando `.panel` - são
exatamente o alvo do item 3.4 (trocar por `<Loading />`), migrar a classe agora seria
trabalho jogado fora assim que 3.4 rodar.

Zero raio de borda arbitrário novo introduzido: mantive o `className` de cada arquivo
migrado batendo com o visual anterior (`rounded-2xl`, ou `rounded-[24px]` onde já era
assim) - a consolidação da escala de raio é o item 3.3, próximo da fila.

### 3.3 — Escala de raio de borda — FEITO (2026-09-16)

Contagem real antes de mexer: 30 ocorrências de `rounded-[Npx]` (a auditoria contou 31,
diferença irrelevante), 6 valores distintos (14/16/18/20/22/24px), em 11 arquivos +
`app/gamificacao/page.tsx`. `components/gamification/config-ui.tsx` já dava a pista da
convenção certa: `configCardClass`/`configSoftCardClass` (usados no mesmo arquivo) já eram
`rounded-2xl` - só `configSectionClass` (usado como string LITERAL duplicada por 5
consumidores diferentes, nunca importada) tinha ficado pra trás em `rounded-[24px]`.

**Regra aplicada, sem inventar critério novo**: container de topo (o "panel" da tela, ou o
próprio `Card` migrado em 3.2) → `rounded-2xl` (16px, mesmo valor de `.panel` no
`globals.css` e do `ui/card`/`ui/section-card`); elemento aninhado dentro de um desses
(sub-card, bloco de estatística, table-frame sem shell próprio) → `rounded-xl` (12px) -
mesmo padrão de dois níveis que `components/operations/` já usa (verificado: 9x
`rounded-lg`, 7x `rounded-xl`, 6x `rounded-2xl` num único arquivo de referência, nunca um
valor arbitrário). Uma exceção deliberada: `AppModal` (`config-ui.tsx`) mantém a aparência
"mais arredondada que o normal" documentada no próprio comentário do componente - vira
`rounded-3xl` (24px exato, sem mudar o visual), não `rounded-2xl`.

Arquivos tocados: `config-ui.tsx` (`configSectionClass` + `AppModal`),
`logic-configuration-panel.tsx` (10 ocorrências idênticas, ainda como `<section>` cru - só
o raio mudou, a migração pra `Card` continua deferida pra Fase 5), `user-management-panel.tsx`,
`collaborator-registry-panel.tsx`, `leadership-bonus-panel.tsx`, `governance-rules-panel.tsx`
(o `Card` que eu mesmo migrei em 3.2, preservando por engano o raio antigo - corrigido
agora), `closure-tab.tsx` (7 ocorrências: 2 de topo + 5 aninhadas), `point-balance-panel.tsx`,
`financial-table.tsx`, `ranking-tab.tsx`, `app/gamificacao/page.tsx` (5 ocorrências,
incluindo o esqueleto de carregamento inicial da tela - não é um dos "12 Carregando..." do
item 3.4, é uma UI de skeleton diferente).

Zero `rounded-[` restante em `components/gamification/` e `app/gamificacao/page.tsx`
(conferido por grep). `tsc --noEmit`/`vitest run` limpos, validação visual ao vivo em
Fechamento (hero card + Liderança + Análise/gráficos).

### 3.4 — Estados (loading/vazio/erro) — FEITO (2026-09-16)

- **Loading**: os 12 "Carregando..." de `page.tsx` (linhas 1148-1890) viraram
  `<Card className="p-8"><Loading label="..." /></Card>` (mesmo padrão de container das
  Fases 3.2/3.3), removendo o último uso de `.panel` fora do arquivo deferido. O esqueleto
  rico de carregamento inicial (`!bootstrap`, linha ~1108) não é um dos 12 - é uma UI de
  skeleton própria, só teve o raio de borda corrigido na 3.3, não virou `<Loading />`.
- **Vazio**: convertidos pra `<EmptyState />` (o componente COMPARTILHADO,
  `components/ui/empty-state.tsx`) em 13 arquivos: `user-management-panel`,
  `unmapped-subjects-panel`, `unmapped-diagnoses-panel`, `ranking-tab`,
  `collaborator-registry-panel` (×2), `financial-table`, `collaborator-balance-history-sheet`,
  `leadership-bonus-panel` (×2), `closure-history-panel`, `logic-configuration-panel`
  (só a ocorrência solta - as 2 que já usavam `<EmptyState>` corretamente foram
  reapontadas pro componente certo, ver achado abaixo), `upvalue-import-panel`,
  `point-balance-panel`, `ranking-table.tsx` (variant="card", formato "sem resultado"
  standalone), `audit-panel` (variant com ícone + descrição + ação "Limpar filtros").
  Ficaram de fora de propósito: os "Nenhuma opção encontrada"/"Nenhuma filial encontrada"
  de dentro de dropdowns/combobox (`config-ui.tsx`, `logic-configuration-panel.tsx`) -
  contexto de popover pequeno, o `EmptyState` (padding de card inteiro) não cabe ali.
  - **Achado real durante a migração**: `config-ui.tsx` tinha um `EmptyState` LOCAL
    duplicado (só `title`/`description`, sem `icon`/`action`/`variant`) - exatamente a
    colisão de nome já flagada na Fase 3.1 ("`EmptyState` — colide de nome com
    `ui/empty-state.tsx`"), usado só por `logic-configuration-panel.tsx` (2 pontos).
    Resolvido: os 2 pontos passaram a importar o componente compartilhado (drop-in,
    mesma API), e o duplicado morto foi removido de `config-ui.tsx`.
- **Erro**: a afirmação original do item ("nenhum painel tem estado de erro próprio") não
  procedia mais - `audit-panel`, `point-balance-panel`, `upvalue-import-panel` e
  `collaborator-balance-history-sheet` já tinham cada um seu próprio banner de erro
  (`error`/`setError` local, bloco vermelho), só com 3 variações de estilo (raio, padding,
  tamanho de texto, ícone presente/ausente). Unificados num único formato (`rounded-lg`,
  `px-3 py-2`, `text-sm`, ícone `AlertTriangle`) nos 4 arquivos, sem mudar a lógica de
  quando o erro aparece.

Validado visualmente ao vivo: 12 loadings confirmados por leitura de código (dado real
carrega rápido demais pra capturar em screenshot) + `EmptyState` forçado de verdade
filtrando "Assuntos sem regra" por um texto sem resultado. `tsc --noEmit`/`vitest run`
limpos a cada bloco de arquivos.

### 3.5 — Tabelas sem scroll — FEITO (2026-09-16)

Levantamento antes de mexer: das 12 tabelas listadas, 6 já tinham `table-frame`
(`overflow-x-auto`) por causa das Fases 3.2/3.4 (`point-balance-panel`, `ranking-tab`,
`financial-table`, `unmapped-subjects-panel`, `unmapped-diagnoses-panel`,
`closure-history-panel`). As 6 restantes ganharam a classe `table-frame` no wrapper já
existente (`collaborator-registry-panel` ×2, `leadership-bonus-panel` ×3,
`user-management-panel`, `governance-rules-panel`) - mesmo padrão em todo lugar:
`table-frame overflow-hidden rounded-2xl border border-slate-200`. Também corrigidas 2
tabelas fora da lista original que tinham o mesmo problema:
`collaborator-orders-sheet.tsx` (`table-fixed`, sem nenhum scroll) e a segunda tabela de
`collaborator-balance-history-sheet.tsx` (lançamentos de saldo - só a primeira, histórico
mês a mês, tinha `table-frame`).

**Tabela da Auditoria (`audit-panel.tsx`)**: migrada de `<table>`/`<thead>`/`<tr>`/`<th>`/
`<tbody>`/`<td>` crus pro `ui/table` compartilhado (`Table`/`TableHeader`/`TableRow`/
`TableHead`/`TableBody`/`TableCell`), preservando exatamente as classes originais (larguras
fixas por coluna, header escuro sticky, zebra striping, padding denso via seletor
`[&>td]`). O wrapper próprio `.audit-table-frame` (`app/globals.css`) virou `table-frame`
(mesmo padrão do resto do módulo) e foi removido do CSS global por não ter mais
consumidor. Achado real: `ui/table.tsx`'s `<Table>` já embrulha a si mesmo num
`overflow-auto` E adiciona sozinho os gradientes de "tem mais coluna pra rolar" nas bordas
(`useHorizontalScrollHints`) - a migração não só resolveu o scroll, ganhou de graça uma
UX que a versão crua não tinha. Validado ao vivo: header escuro continua sticky ao rolar
(mesmo padrão já usado em `closure-history-panel.tsx`, `Table` aninhado dentro de um
wrapper com `min-h-0 flex-1 overflow-auto`), zebra striping e truncamento de texto
mantidos, scroll horizontal ativo (colunas cortadas na borda direita, como antes).

`tsc --noEmit`/`vitest run` limpos.

### 3.6 — Cor de gráfico de marca — FEITO (2026-09-16)

Levantamento antes de mexer: só **2** dos usos de `UNI_ROYAL`/`UNI_TURQUOISE` em
`dashboard-charts.tsx` eram série de dado de verdade (não os "~20 pontos" estimados na
auditoria original - a maioria das ocorrências no arquivo eram o mesmo texto de comentário
repetido, não usos novos de cor):

1. `healthOption` ("Saúde operacional por regional/base") - `color: [UNI_ROYAL, "#e11d48"]`
   no nível do gráfico (2 séries: SLA e Reincidência) → `color: [CATEGORICAL_SLOTS[0],
   CATEGORICAL_SLOTS[7]]`. O vermelho `"#e11d48"` (também fora da paleta validada) trocado
   junto, por consistência - as duas séries do mesmo gráfico devem vir da mesma fonte.
2. `healthScatterOption` ("Dispersão saúde da base x pontuação") - série única
   `itemStyle.color: UNI_ROYAL` → `CATEGORICAL_SLOTS[0]`.

**Mantido de propósito** (já estava correto, confirmado pela leitura): `UNI_BAR_GRADIENT`
(gradiente royal→turquoise do bar chart de ranking, elemento de INTERFACE de uma série
única, não identidade de dado) e `UNI_MIDNIGHT` (cor de texto do rótulo, não de série).
`scatterOption` (verde/vermelho sem-reincidência/com-reincidência) e o gradiente vermelho
de `penaltyOption` não usam azul de marca, fora do escopo do item.

Validado ao vivo: os dois gráficos renderizam com a paleta categórica (`#2a78d6` visualmente
quase idêntico ao antigo `#2d5fff`, mas agora semanticamente correto - slot de dado, não
token de marca) e a legenda "SLA"/"Reincidência" com as cores certas. `tsc --noEmit`/
`vitest run` limpos.

**Fase 3 (fundação visual): itens 3.1 a 3.6 todos endereçados - ver "Critério de pronto"
abaixo pro que ficou de exceção documentada (arquivo deferido) e o que falta (passada
dedicada de breakpoints).**

### Critério de pronto da Fase 3

- [x] Nenhum `.panel`/`.panel-header`/`.panel-title` na Gamificação **exceto**
  `logic-configuration-panel.tsx` (usa `PageHeader`, um dos 8 exports formalmente
  deferidos pra Fase 5 desde o item 3.1.5 - migrar isoladamente seria trabalho perdido
  quando o arquivo for quebrado em seções lá).
- [x] `config-ui.tsx` só com o que não tem equivalente em `ui/` — `ErrorState` e
  `AppMultiSelect` (mortos) removidos, `AppSwitch`/`AppCheckbox` reexportados de
  `components/ui/`, `EmptyState` local duplicado removido (usava o compartilhado). Resta
  só o que segue sem equivalente ou é exclusivo do arquivo deferido.
- [x] Toda tabela com scroll container (`table-frame`), incluindo a tabela crua da
  Auditoria migrada pro `ui/table`.
- [x] Todo loading/vazio/erro usando os componentes compartilhados (`Loading`,
  `EmptyState`, banner de erro padronizado nos 4 painéis que fazem fetch próprio).
- [x] `tsc --noEmit`/`vitest run` limpos em cada passo (13 arquivos de teste, 83 testes).
- [ ] Validação visual nas 8 abas em 1920×1080, 1366×768, 1024×768 e 768×1024 — feita ao
  vivo por navegação real a cada mudança (não por captura sistemática nos 4 breakpoints
  nem nas 8 abas exaustivamente); considerar uma passada final dedicada a isso antes de
  dar a Fase 3 por encerrada de vez.

## Fase 4 — Navegação e hierarquia (não iniciada)

- **Seletor de período no cabeçalho**: hoje o único jeito de trocar o mês é um botão dentro
  da aba "Período" (`upvalue-import-panel.tsx`, prop `onViewPeriod`). Já registrado como
  débito desde 2026-09-10. Mover pra um controle visível no cabeçalho da tela, ao lado do
  botão de recalcular.
- **Um único botão de recálculo**: hoje "Recalcular pontuação" aparece fixo nas 8 abas
  (inclusive nas que não têm o que recalcular), e a aba Período tem **três** gatilhos de
  recálculo na mesma tela (um deles grafado "Recalcular **P**ontuação", maiúscula
  divergente do resto). Definir um único padrão de onde e quando esse botão aparece.
- **Achatar aninhamento**: 8 abas no topo → até 4 sub-abas em Configuração → até 3
  sub-abas em Liderança/Auditoria (4 níveis de profundidade). Avaliar se sub-abas viram
  seções na mesma tela ou se a navegação principal precisa de outra forma.
- **2 abas mortas**: `TabsContent value="unmapped"` e `"diagnosis-unmapped"`
  (`page.tsx:1757,1806`) existem mas não estão em `GAMIFICATION_NAV_ITEMS` nem em
  `visibleTabs` — painéis duplicados de `UnmappedSubjectsPanel`/`UnmappedDiagnosesPanel`
  que já aparecem em Pendências. Decidir: remover a duplicata ou remover a aba que ficou
  invisível.
- **`visibleTabs` calculado e nunca aplicado** (`page.tsx:1066-1068`): hoje um usuário
  `viewer` consegue abrir `?tab=config` direto pela URL e ver o painel de configuração
  inteiro (o backend recusa a escrita com 403, mas a tela promete o que não entrega).
  Aplicar o mesmo padrão de guarda que `operacao/page.tsx:1540` já usa.
- **Terminologia inconsistente**: a aba se chama "Período" no menu
  (`gamification-nav-items.ts`), o valor interno é `"import"` e o componente é
  `upvalue-import-panel.tsx` — três nomes pra mesma tela. Não é bug, mas dificulta achar
  código; alinhar nomenclatura ao mexer nesta aba de qualquer forma.

## Fase 5 — Estrutura (não iniciada)

- **Autenticação duplicada — FEITO (2026-09-17)**: `GamificacaoPageContent` agora recebe
  `user: AuthUser` via `WorkspaceAppShell` (`{(user) => <GamificacaoPageContent
  user={user} />}`), mesmo padrão já usado em `app/suporte/page.tsx`. Removidos: estado
  `currentUser`/`authChecked`/`loginEmail`/`loginPassword`, a função `login()`, os dois
  early-returns de guarda (`if (!authChecked)`/`if (!currentUser)`) e a tela de login
  inteira própria (~75 linhas). Os 17 pontos que usavam `currentUser?.` viraram `user.`
  (não-nulo, sem optional chaining), incluindo `hooks/use-closure-actions.ts` (o hook
  também deixou de aceitar `currentUser: AuthUser | null`, agora exige `AuthUser`).
  Imports mortos removidos: `Loader2`, `Mail`, `LockKeyhole`, `Input`, `setAuthToken`.
  **Achado real durante a implementação**: o efeito de bootstrap original desestruturava
  `[user, bootstrapData]` de `Promise.all([api.me(), ...])` - esse `user` local SOMBREAVA
  silenciosamente o prop `user` que passou a existir; reescrito sem essa colisão, mantendo
  a mesma sequência de carregamento (summary pré-buscado em paralelo, período de análise
  derivado do bootstrap antes do primeiro `loadAll`), só sem o `api.me()` redundante.
  Validado ao vivo (login real): Fechamento (botões condicionados a permissão), aba
  Usuários (exige `users:manage`, carrega junto com o `SummaryCard` consolidado do item
  anterior) e Saldo de pontos (`isAdmin` de `user.role`) - todas corretas.
- **`SummaryCard` triplicado**: cópias quase idênticas em `collaborator-registry-panel.tsx`,
  `leadership-bonus-panel.tsx`, `user-management-panel.tsx`, convivendo com `MetricCard`,
  `StatStrip` (`ranking-tab.tsx`) e 2 blocos inline em `page.tsx` — 5 variações do mesmo
  cartão de resumo. Consolidar num único componente (candidato natural:
  `ui/summary-metric.tsx`, que já existe).
- **Regra de negócio na tela — investigado (2026-09-17), 1 de N pontos corrigido**: a
  lista original (~12 pontos) misturava coisas bem diferentes; investigando cada uma
  antes de mexer (ver `docs/STATUS.md`):
  - **Reconstrução da média de liderança em `page.tsx`** (o "mais grave" apontado pela
    auditoria original): investigado a fundo no backend
    (`services/leadership_bonus.py`) - hoje `audit` é SEMPRE populado no cálculo atual,
    sem exceção. O fallback do frontend só existe pra resultados de liderança
    calculados ANTES do campo `audit` existir (fechamentos antigos, alguns já pagos e
    portanto imutáveis) e já se rotula honestamente como reconstrução ("Esta visualização
    foi reconstituída no frontend..."), mostrando a diferença pra quem quiser conferir.
    **Não é um bug — é um fallback de compatibilidade retroativa deliberado e
    transparente. Não mexido** (mover pra backend recalcularia um fechamento talvez já
    pago, o que o sistema já recusa fazer em outros pontos por design).
  - **`rankingScopeTotals`/`rankingPeriodTotalOrders` (`page.tsx`) e as somas de
    `use-closure-data.ts`**: são somas simples (`reduce`) sobre dados que o frontend JÁ
    tem carregados por inteiro (`summary.ranking`, `summary.health_by_regional`), só pra
    agregar por filtro de regional selecionado na tela. Não são regra de negócio
    reimplementada nem podem divergir do backend (a fonte é a mesma lista, só filtrada/
    somada) - mover isso pro backend trocaria uma conta trivial por uma chamada de API
    nova a cada troca de filtro, sem ganho de correção nenhum. **Não mexido.**
  - **R$/ponto duplicado 3x (`audit-panel.tsx`, `collaborator-orders-sheet.tsx`,
    `ranking-table.tsx`) — CORRIGIDO**: este sim era duplicação real, com 3
    implementações levemente diferentes da mesma conta (uma delas usava `|| 1` pra
    evitar divisão por zero, fazendo `pagamento / 1` aparecer como "valor do ponto"
    quando pontos = 0, em vez de indicar "sem base"). Consolidado num helper novo,
    `pointValueFromTotals` (`lib/gamificacao-helpers.ts`), com UM critério só (`null`
    quando não há pontos pra dividir) - corrige a inconsistência de verdade, sem tocar
    no backend (é conta de exibição, não regra de negócio que possa divergir da fonte).
    Validado ao vivo na Auditoria (coluna "Valor" calculando certo). `tsc`/`vitest`
    limpos.
  - **Conclusão**: dos itens investigados, só 1 era duplicação real corrigível sem
    risco; os outros 2 eram ou um fallback deliberado (não bug) ou agregação de tela
    (não é a regra que a norma "KPI vive no service" está protegendo). Itens restantes
    da lista original (não investigados ainda): somas adicionais eventualmente
    espalhadas em outros arquivos — se aparecerem, tratar com o mesmo critério: só mexer
    se for de fato divergência/duplicação de CÁLCULO, não agregação de dado já correto.
- **`logic-configuration-panel.tsx` (3.075 linhas, 38 `useState`) — EM ANDAMENTO,
  passo 1 de N feito em 2026-09-17**: quebrar em arquivos por seção é maior e mais
  arriscado do que os itens rápidos da Fase 5 (usuário concordou explicitamente em ir
  "com cuidado, mesmo mais devagar"). Mapeamento real antes de mexer: a função principal
  só começa em `export function LogicConfigurationPanel(...)` (linha ~401 do arquivo
  original) - tudo ANTES disso (linhas 98-399: tipos, constantes, ~20 funções puras e o
  componente `SearchableMultiSelect`) não dependia de nenhum estado do componente, então
  saiu inteiro, sem risco de comportamento, pra
  `components/gamification/logic-configuration-helpers.tsx` (arquivo novo). Achado real:
  a lista original de "8 exports usados só por este arquivo" (Fase 3.1, item 5) estava
  levemente errada - `SearchableMultiSelect` NUNCA foi um export de `config-ui.tsx`, é
  (era) uma função local deste próprio arquivo; a lista correta de exports realmente
  exclusivos é `DataTableFrame`/`FilterToolbar`/`GuidanceCard`/`PageHeader`/
  `StepHeroCard`/`ToolbarCount`/`ToolbarSearch` (7, não 8) - ainda pendentes, ficam pro
  próximo passo junto da quebra dos 9 blocos de JSX (a parte grande e de verdade
  arriscada: threading de ~30-40 props por seção a partir dos 38 `useState`/`useMemo` que
  continuam no arquivo principal, ainda não tocados). Resultado deste passo: arquivo
  principal caiu de 3.075 para 2.813 linhas, `tsc --noEmit`/`vitest run` limpos,
  validado ao vivo (seções Governança e Tipos gerais, que já usam as funções movidas,
  renderizando idênticas). **Não interpretar como o item fechado** - é só a base
  (helpers compartilhados) que as próximas extrações de seção vão precisar.
  - **Passo 2 de N (2026-09-17) — concluído**: extraídas as 6 seções de JSX mais
    autocontidas do modo "avançado" para arquivos próprios, cada um com props explícitas
    tipadas (sem `any`), recebendo valores já calculados (`typeRows`, `diagnosisRows`,
    `filteredSlaRules` etc.) em vez de recalcular: `logic-configuration-categories-section.tsx`
    (212 linhas, "Tipos gerais"), `logic-configuration-diagnoses-section.tsx` (176 linhas),
    `logic-configuration-sla-section.tsx` (241 linhas, inclui multiplicadores de saúde),
    `logic-configuration-recurrence-section.tsx` (609 linhas, a maior - passo a passo +
    config geral + formulário de nova regra + lista de regras cadastradas),
    `logic-configuration-integration-section.tsx` (209 linhas, IXC + CPK),
    `logic-configuration-advanced-section.tsx` (49 linhas, snapshot/export/import/
    restaurar). `logic-configuration-panel.tsx` foi de 3.110 linhas (no `HEAD` da hora,
    que já tinha recebido outros commits de outra sessão) para **1.687 linhas**.
    **Não extraído, de propósito**: as seções "Grupos" e "Assuntos" (tabelas + os 2
    `AppDrawer` de edição no fim do arquivo + os modais de exclusão em lote) continuam no
    arquivo principal - o drawer de edição é compartilhado pelas duas seções e os modais
    de exclusão em lote também, então separar isso exige uma decisão de design (estado
    compartilhado entre 2-3 arquivos, ou manter junto) ainda não tomada. Fica pro próximo
    passo.
    **Incidente durante a execução, registrado por transparência**: o agente que fez essa
    extração corrompeu o arquivo com um comando malformado e rodou `git checkout --`
    nele pra tentar recuperar - operação destrutiva que não deveria ter usado sem
    perguntar, ainda mais num checkout compartilhado por várias sessões (ver
    `[[shared_checkout_uncommitted_wip]]`). Investigado depois, com `git show HEAD:...`
    comparado ao arquivo atual: o único conteúdo perdido foi a própria edição não
    commitada do passo 1 (acima), que o agente reconstruiu a partir do `HEAD` +
    `logic-configuration-helpers.tsx` (arquivo separado, não afetado). Todo o trabalho de
    padronização das Fases 3/5 feito nesse arquivo em sessões anteriores já estava
    commitado (`7702004`) e sobreviveu intacto. Nenhum outro arquivo do repositório foi
    tocado (o `checkout` teve escopo de um único arquivo). `tsc --noEmit` e `vitest run`
    (83/83) re-verificados de forma independente depois do incidente, e as 6 seções novas
    + Grupos + Assuntos (não tocados) validados ao vivo no navegador, uma por uma.
  - **Passo 3 de N (2026-09-17) — concluído, feito diretamente (sem subagente) por causa do
    incidente do passo 2**: extraídas as duas últimas tabelas grandes, "Grupos" e "Assuntos",
    pra `logic-configuration-groups-section.tsx` (213 linhas) e
    `logic-configuration-subjects-section.tsx` (225 linhas) - cada uma só a tabela +
    toolbar de filtro/criação, como componente de apresentação puro (recebe tudo via
    props, sem estado próprio). Os 4 modais de exclusão (em lote e individual, de grupo e
    de assunto) e os 2 `AppDrawer` de edição continuam no arquivo principal, porque são
    genuinamente compartilhados entre as duas seções (o mesmo drawer de edição de grupo
    é aberto tanto a partir da tabela de Grupos quanto referenciado pelo estado
    `editingGroupId` que a seção usa) - separar isso exigiria um contexto compartilhado
    ou prop-drilling ainda maior, sem ganho real de legibilidade. `logic-configuration-panel.tsx`
    foi de 1.687 para **1.428 linhas**. Imports órfãos removidos manualmente após a
    extração (`DataTableFrame`, `RowActionMenu`, `sameGroupSnapshot`, `subjectStatus`,
    `subjectStatusClass`, `subjectStatusLabel`, `cn`, `Trash2` - migraram pros 2 arquivos
    novos). `tsc --noEmit` (0 erros) e `vitest run` (83/83) limpos; validado ao vivo:
    tabela de Grupos, tabela de Assuntos, drawer de edição de grupo E de assunto abertos
    e conferidos um a um (o `AppDrawer` compartilhado, que ficou no arquivo pai, abre e
    fecha certo vindo de ambas as seções extraídas).
    **Considerar o item fechado**: as 9 seções JSX do modo avançado foram todas
    extraídas (6 do passo 2 + 2 deste passo + Governança, que já era `GovernanceRulesPanel`
    desde antes). O que ficou no arquivo principal (modais de exclusão + drawers de
    edição + toda a lógica/estado/`useMemo`) é o núcleo que de fato precisa ficar junto -
    não há mais nenhuma seção JSX solta esperando extração.
- **Tipos redeclarados localmente**: `CreatePayload`/`EditDraft`
  (`collaborator-registry-panel.tsx`), `UserPayload` (`user-management-panel.tsx`,
  diverge do payload real de `api.createUser`), `DiagnosisDraft`/`DiagnosisConfigurePayload`
  (`unmapped-diagnoses-panel.tsx`) — conferir contra `lib/types.ts` e `lib/api.ts` e
  alinhar ou apontar pro tipo canônico.

## Fase 6 (à parte) — Performance

Não numerada nas fases originais porque não depende delas — pode ser feita em paralelo ou
antes. Achados completos em `docs/STATUS.md`/histórico desta auditoria; resumo por
impacto:

| Impacto | Onde | Ação |
|---|---|---|
| ALTO | `backend/app/api/routes/collaborators.py` (`/collaborators/registry`) | `select(ServiceOrder)` sem WHERE, agrupado em Python — trocar por `GROUP BY` em SQL |
| ALTO | `/dashboard/summary` (schema + rota `dashboard.py`) | devolve a lista de 224 scores duas vezes (`ranking` e `run.scores`) mais `result_summary`/`config_snapshot` crus que o frontend nunca lê — criar `CalculationRunOut` enxuto pro summary |
| ALTO | `backend/app/models.py` | `closed_at`/`opened_at`/`collaborator_id` sem índice — toda consulta de período faz seq scan |
| ALTO | `/audit/service-orders` (`routes/audit.py`) | reprocessa o mês inteiro (~11k O.S.) a cada requisição, inclusive troca de página — memoizar por `(run_id, mês, ano, regional)` |
| ALTO | `collaborator-registry-panel.tsx` (fotos) | até 224 GETs sequenciais em loop — endpoint em lote ou `<img src>` direto com cache HTTP |
| MÉDIO | `page.tsx` (montagem) | `/scoring-groups` e `/settings` pedidos na montagem mas não usados na aba padrão (Fechamento) — mover pra quando a aba Configuração abrir |
| MÉDIO | `page.tsx` (busca do ranking) | sem debounce, `RankingTable` sem memo — cada tecla repinta ~4.500 nós DOM |
| MÉDIO | `page.tsx:1310` (`loadAll` em ações unitárias) | vincular 1 assunto em Pendências invalida o cache de todas as abas |
| MÉDIO | `routes/calculation_runs.py` (histórico) | `selectinload` de 100×224 linhas só pra somar 7 números — `GROUP BY` em SQL |
| MÉDIO | `routes/service_orders.py` (`/subject-summary`) | carrega o período inteiro, conta em Python — `GROUP BY` em SQL |
| MÉDIO | `routes/dashboard.py` (`/filtered-breakdowns`) | não usa `_period_orders_for_selected_regionals` (já existe, filtra no SQL) quando há regional selecionada |
| BAIXO | `page.tsx` (imports de painel) | painéis de todas as 8 abas importados estaticamente — `next/dynamic` nos que não são a aba padrão |

## Fora de escopo (nesta reestruturação)

- Migrar Tailwind v3→v4.
- Implementar dark mode.
- Reescrever regra de negócio (multiplicador de saúde, garantia, CPK) — só corrigir onde
  já é bug confirmado (ver Fase 1/2, já feito).
- Adicionar permissão granular nova ou mudar o modelo de perfis.
- Migrar módulos além da Gamificação.

## Ordem sugerida ao retomar

1. Fase 3 (visual) — maior valor percebido, mais isolada, menor risco de regressão
   funcional já que não mexe em lógica de cálculo.
2. Fase 6 (performance) — pode entrar em paralelo com a Fase 3 por quem preferir; toca
   arquivos diferentes na maior parte dos itens.
3. Fase 4 (navegação) — depende de decisão de produto (onde fica o seletor de período,
   se sub-aba vira seção), então convém alinhar com o usuário antes de implementar.
4. Fase 5 (estrutura) — maior risco de regressão (autenticação, tipos, quebra de arquivo
   grande), deixar por último e com testes reforçados a cada passo.

Cada fase deve seguir o fluxo do `AGENTS.md`: diagnóstico curto → plano → validação do
usuário → implementação → `tsc --noEmit`/`vitest run`/testes de backend relevantes →
validação visual/funcional real (não só ausência de erro) → atualizar `docs/STATUS.md`.
