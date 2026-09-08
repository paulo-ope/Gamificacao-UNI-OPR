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

**2026-09-08** — branch `claude/suporte-sync-backfill-madrugada`

## O que foi feito recentemente

- **UNI Localiza — módulo novo: link de geolocalização para o cliente compartilhar posição por GPS**
  (2026-09-08, MVP completo + 4 rodadas de ajuste a partir de teste ao vivo do usuário). Atendente
  gera um link único (`/localiza`), envia pelo WhatsApp, cliente abre no celular sem login
  (`/l/{token}`), autoriza a localização, ajusta o marcador num mapa e confirma - o atendente vê o
  resultado e a divergência contra a coordenada cadastrada.
  - **Backend**: módulo isolado `backend/app/modules/localiza/` (`models.py`, `schemas.py`,
    `service.py`, `router.py`, `public_router.py`, `ixc_lookup.py`). Tabela `location_requests`
    (migrations `20260908_0085`/`0086`). Token de 256 bits, hash SHA-256 indexado (não pbkdf2 como
    convites - volume esperado é maior, precisa de busca O(1)), uso único, expiração configurável
    (`LOCALIZA_LINK_TTL_HOURS`, padrão 72h), rate limit em memória nas rotas públicas. Permissões
    `localiza:read`/`localiza:manage` (operator/admin). Haversine + classificação de divergência
    (compatível/pequena/relevante/forte) centralizada em `service.py`. 25 testes (`test_localiza.py`,
    `test_localiza_ixc_lookup.py`), todos passando.
  - **Código da O.S. é opcional** (pedido do usuário: o link costuma ser enviado ANTES de existir
    O.S. no IXC) - exige só QUALQUER identificador (O.S., protocolo OPA, ou dado do cliente).
    Protocolo OPA vira campo próprio; código da O.S. pode ser anexado depois
    (`POST /localiza/{id}/attach-order`), sem precisar gerar novo link.
  - **Busca ao vivo no IXC por login ou CPF** (`GET /localiza/ixc/search`): autopreenche nome,
    identificador e coordenada cadastrada a partir de `radusuarios`/`cliente` (campos confirmados
    contra a API real: `cnpj_cpf` com máscara, `latitude`/`longitude` em ambas as tabelas). CPF
    nunca aparece completo na resposta. Fluxo de criação foi redesenhado a pedido do usuário pra
    "só precisar do CPF": busca fica em destaque, os demais campos (O.S., protocolo, ajuste manual)
    ficam escondidos atrás de "Mais opções", só aparecem se o cliente não for achado no IXC.
  - **Página pública** (`/l/{token}`): Leaflet puro (sem `react-leaflet`, mesmo padrão anti-Strict-Mode
    do resto do app), pino desenhado em SVG (não o ícone padrão do Leaflet - achado real: o ícone
    default depende de imagens que o bundler do Next.js não resolve, aparecia quebrado). Círculo de
    incerteza do GPS no mapa (raio = precisão reportada, cor por qualidade), com zoom ajustado
    automaticamente pra caber o círculo quando a precisão é ruim (achado real: com ~4km de imprecisão
    a bolha ficava invisível no zoom fixo). Aviso em texto quando a precisão é baixa, e um guia
    "Como ativar a localização" (Android/iPhone) quando o navegador nega a permissão.
  - **Painel interno de consulta**: link só é mostrado uma vez, no momento em que é gerado (nunca
    reaparece depois - por segurança, o token só existe em claro nesta resposta); atualiza sozinho
    por polling a cada 4s enquanto pendente, sem precisar recarregar a página quando o cliente
    confirma. Botão de copiar (link pronto do Google Maps, pra colar no WhatsApp) tanto na listagem
    quanto no painel de detalhe, com indicador "Copiado!" em texto.
  - **`FRONTEND_URL` precisa ser HTTPS real na VM** (`.env.example` atualizado com o aviso) - é a
    partir dela que o link público é montado, e a Geolocation API do navegador exige HTTPS (exceto
    em `localhost`, que só serve pra desenvolvimento). Links já gerados com `localhost` não são
    recalculados - só afeta links novos.
  - **Verificado ao vivo**: fluxo completo (gerar → abrir no celular com geolocalização mockada →
    confirmar → painel atualiza sozinho) testado várias vezes contra o ambiente real (containers
    reconstruídos oficialmente via `docker compose build`), incluindo a busca real no IXC (login
    `72928`/CPF `70240110250`, dado de teste do próprio usuário). Dado de teste sempre inserido e
    removido só na tabela nova `location_requests` (+ usuário de teste descartável), nunca tocando
    dado real. **Achado incidental**: o usuário testou a feature em paralelo, no mesmo banco - os
    registros reais dele (`JUANDER BONATO SCARDINE`, `PAULO HENRIQUE ALVES PEIXOTO SOARES`) não
    foram tocados.
  - **Bug de UI encontrado e corrigido**: erro de validação do Pydantic (422, lista de objetos)
    aparecia como JSON cru na tela em `lib/localiza-api.ts` - `extractApiErrorMessage` só tratava
    `detail` como string. O mesmo bug existe em `lib/api.ts` (usado pelo resto do app) - **não
    corrigido ainda**, ver tarefa sugerida.
  - Frontend e backend desta máquina reconstruídos oficialmente (`docker compose build`) a cada
    rodada de ajuste; migrations aplicadas automaticamente no start do backend.

- **Visão Geral: linha de período anterior nos 3 gráficos de tendência + switch pra ligar/desligar**
  (2026-09-08, usuário: "quero em todos os graficos e eu possa selecionar se quero essa linha de
  compração ou nào"). Generaliza o item anterior (só o Fluxo diário tinha a linha).
  - **SLA e Backlog ganharam a linha de período anterior** que só o Fluxo diário tinha: "SLA
    acumulado (período anterior)" (`buildOverviewSlaTrendOption`, nova função própria da Visão
    Geral - mesma razão de sempre, não alterar `buildSlaTrendOption` do módulo de Operação) e
    "Backlog (período anterior)" (`buildBacklogTrendOption`, já era própria da Visão Geral).
  - **Alinhamento diferente entre os dois**: Fluxo diário e SLA vêm de `OperationTrendSeries`,
    sempre denso (um ponto por dia da janela) - alinha por ÍNDICE, dia 1 com dia 1. Backlog é
    naturalmente esparso (só tem fotografia a partir de `coverage_from`) - alinhar por índice bruto
    casaria dias errados quando os dois lados têm buracos em posições diferentes, então usa
    DESLOCAMENTO DE DIA dentro de cada janela (dia 5 da janela atual com dia 5 da anterior),
    calculado a partir do `date_from` de cada uma.
  - **Switch único** "Comparar com período anterior" (`AppSwitch`, reaproveitado de
    `components/gamification/config-ui.tsx` - já é importado fora da gamificação em outro lugar do
    app) perto do resumo "Período X · comparado com Y", só aparece quando existe janela anterior
    comparável. Liga/desliga as 3 linhas de uma vez (mesma pergunta em todos os gráficos), nasce
    ligado, lembra a escolha por navegador (`localStorage`, mesmo padrão do
    `EXPANDED_STORAGE_KEY` da barra de filtros).
  - **Verificado ao vivo** numa base sintética com 70 dias de fotografia de backlog (cobertura
    real nas duas janelas, atual e anterior): as 3 linhas aparecem com o switch ligado; desligar
    esconde as 3 ao mesmo tempo (incluindo a legenda do Backlog, que só aparece com mais de 1
    série); recarregar a página mantém a escolha.
  - Frontend de produção desta máquina reconstruído e reiniciado. Nenhuma mudança de backend.

- **Visão Geral: linha de período anterior no Fluxo diário, KPIs e tabela por filial responsivos
  no celular** (2026-09-08, usuário: "preciso melhorar os graficos deixar mais responsivel, trazer
  algumas metricas melhores" → esclarecido: responsivo = celular/tablet; métrica = "linha
  comparando com um período anterior").
  - **Linha "Finalizadas (período anterior)"** no gráfico "Fluxo diário": reaproveita a mesma
    janela que já alimenta o card de comparação do topo (`previousFilters`/`previousWindow`), só
    que como linha (formato da curva), não só número agregado. Alinhamento por ÍNDICE (dia 1 com
    dia 1), não por data - os dois períodos têm datas diferentes por definição; se o período
    anterior for cortado no início do ano operacional e ficar mais curto, os dias que faltam no
    fim ficam sem ponto (`connectNulls: false`), nunca inventados. Função própria da Visão Geral
    (`buildOverviewOpeningsTrendOption`, `lib/overview-chart-options.ts`) - não mudou a função
    compartilhada com a Operação Analítica.
  - **Cards de KPI: 1 coluna no celular** (`overview-kpi-strip.tsx`). Eram 2 colunas até `sm`, e
    com `SummaryMetric` usando `truncate` (uma linha só) em rótulo/valor/dica, o card ficava
    estreito demais em 375px: "ABERTAS NO PE...", "Demanda que entr..." ilegíveis. Corrigido
    ajustando só o grid da Visão Geral (`grid-cols-1 sm:grid-cols-2 ...`), sem tocar no
    `SummaryMetric` (compartilhado com outros módulos).
  - **Bug real encontrado: tabela por filial não rolava no celular, só espremia as colunas**. Causa
    raiz no componente compartilhado `Table` (`components/ui/table.tsx`): a tag `<table>` usa
    `w-full`, que trava a largura em 100% do contêiner - numa tela estreita isso força as 6
    colunas + botão de detalhar a espremer (texto de cabeçalho cortado, "UNI - MACHADINHO DOESTE"
    quebrando em 3 linhas) em vez de a tabela vazar e rolar horizontalmente, apesar do wrapper já
    ter `overflow-x-auto`. Corrigido só na tabela da Visão Geral, com `min-w-[720px]` passado via
    `className` (não mexeu no componente `Table` compartilhado, que outras telas podem depender do
    comportamento atual).
  - **Verificado ao vivo em 375px** (base sintética isolada, nunca no banco de produção): os 3
    gráficos de tendência (Fluxo diário/SLA/Backlog) já se ajustavam bem sem mudança nenhuma
    (ECharts encolhe a densidade de rótulos sozinho); os cards de KPI passaram a mostrar rótulo,
    valor, delta e dica por completo, sem cortar; a tabela por filial confirmada rolando de
    verdade (`scrollWidth` 720 > `clientWidth` 341, testado arrastando e conferindo que
    Finalizadas/SLA/Meta aparecem).
  - Frontend de produção desta máquina reconstruído e reiniciado. Nenhuma mudança de backend.

- **Tooltip do ECharts cortado perto da borda do card - varredura em todo o app, não só onde o
  usuário viu** (2026-09-08, usuário mandou um print do donut "Finalizadas por filial" com o texto
  do tooltip cortado: "Alguns bug de texto cortado, procure por todos os lugares que apresneta esse
  mesmo erro e corrija"). Causa raiz: `SectionCard` (`components/ui/section-card.tsx`) e
  `OperationsTrendChart` (`components/operations/operations-trend-chart.tsx`) tinham
  `overflow-hidden` no Card sem necessidade real - nada neles sangra até a borda arredondada
  (header/conteúdo sempre têm padding) - então o clipe só existia como efeito colateral, cortando o
  tooltip do ECharts (que é um `<div>` posicionado dentro do próprio container do gráfico) sempre
  que ele precisava desenhar perto da borda esquerda/direita/superior do card.
  - **Corrigido removendo o `overflow-hidden`** dos dois componentes - como são compartilhados,
    resolve de uma vez os donuts e os 3 gráficos de tendência da Visão Geral, os gráficos da
    Operação Analítica que reaproveitam `OperationsTrendChart` (SLA operacional, Aberturas x
    finalizações, Produção por equipe), e os widgets do cockpit da UNI Intelligence que usam
    `SectionCard`.
  - **Varredura em todo o app** (grep por `overflow-hidden` + `ReactECharts`/`SectionCard`/`Card`)
    achou um caso onde o clipe é PROPOSITAL: `ChartPanel` do SGP Suporte
    (`app/suporte/_components/opa-charts.tsx`) usa `overflow-hidden` pra clipar o cabeçalho colorido
    do card nos cantos arredondados - remover ali quebraria esse visual. Corrigido lá com
    `tooltip.appendToBody: true` no `TOOLTIP` compartilhado de `lib/support-chart-options.ts` -
    opção oficial do ECharts pra exatamente esse problema (tira o DOM do tooltip de dentro do
    container, anexa direto no `<body>`), sem mexer no CSS do card.
  - Outros lugares com ECharts checados e confirmados SEM esse problema (sem `overflow-hidden` no
    ancestral do gráfico): gamificação (`dashboard-charts.tsx`), agendamento
    (`scheduling-trend-chart.tsx`, `scheduling-backlog-panel.tsx`,
    `scheduling-day-breakdown-charts.tsx`, `scheduling-performance-panel.tsx`), e os gráficos de
    `operations-openings-analytics.tsx` (o único `overflow-hidden` ali é num `MetricCard` sem
    gráfico dentro, usado pra clipar uma faixa de cor decorativa - não relacionado).
  - **Verificado ao vivo**: mouse bem na borda esquerda do donut "Finalizadas por filial" (mesmo
    ponto do print do usuário) - tooltip aparece completo agora, sem cortar. Frontend de produção
    desta máquina reconstruído e reiniciado.

- **Aviso de saída do drill (Visão Geral) virou fixo (sticky), logo abaixo do cabeçalho** (2026-09-05,
  usuário: "pense em um local obvio e evidente para deixar o botao de sair do drill"). Causa do
  problema: o aviso vivia só no topo da página (logo abaixo da barra de filtros) - quem clicava pra
  detalhar num gráfico ou na tabela mais embaixo (SLA, Backlog, "Quadro geral das filiais") tinha
  que rolar de volta pro topo só pra achar o "Voltar". "Óbvio e evidente" virou, na prática, "sempre
  à vista": `sticky top-[79px]` (79px = altura medida do cabeçalho fixo do ecossistema,
  `app-shell.tsx`), acompanhando a rolagem, com `shadow-md` pra parecer flutuar sobre o conteúdo.
  Cor trocada de azul (já usado no resto da barra de filtros) pra âmbar, e o botão "Voltar" virou
  sólido em vez de contorno - mais destaque pra um estado que é temporário, não mais um filtro comum.
  **Verificado ao vivo**: rolando a tela inteira (do topo até o rodapé) com o drill ativo, o aviso
  continuou visível e clicável o tempo todo, em desktop (1600px) e mobile (375px, reflow em coluna
  única sem quebrar layout). Frontend de produção desta máquina reconstruído e reiniciado.

- **Visão Geral: donut de filial mostra TODAS (nunca dobra em "Outros"), cor própria por entidade
  além do 8º slot, lista recolhível, e drill temporário generalizado pra todo clique da tela**
  (2026-09-04/05, dois pedidos do usuário em sequência: "que os donnuts apareça todas filial" e,
  depois de ver ao vivo, "cada filkial com uma cor e deixa RECOLHIDO A lista... depois eu clico em
  ver mais que deve expandir"; e "vamos adicionar o drill temporario em todos os driwll da visão
  macro").
  - **Todas as filiais nomeadas**: `overview-screen.tsx` passa `maxSlices={completedByRegional.length}`
    pro donut "Finalizadas por filial" - nunca dobra a cauda em "Outros", só nesse donut (os outros
    dois - modelo de equipe, canal SGP - continuam no teto padrão de 8, que na prática nunca é
    atingido por eles).
  - **Cor própria além do 8º**: `assignSeriesColors` (`lib/share-breakdown.ts`) não cai mais no
    cinza neutro passado o fim da paleta validada (`CATEGORICAL_SLOTS`, 8 cores) - volta pro início
    da paleta num tom claro/escuro alternado (`shade()`, nova função). Tom extra não passou pela
    validação formal de contraste/daltonismo (só a base passou), mas preserva o matiz da cor
    validada, então a distinção por matiz continua.
  - **Lista recolhível**: `OverviewShareDonut` mostra só as 6 primeiras linhas por padrão
    (`COLLAPSED_ROWS`) com botão "Ver mais (+N)"/"Ver menos" - o ANEL sempre desenha todas as
    fatias (nenhum dado escondido), só a lista lateral é que fica curta até pedir o resto, pro card
    não crescer proporcional à contagem de filiais.
  - **Drill temporário generalizado**: antes só existia no clique por dia (ver item mais abaixo);
    agora `drillFilters()` (`overview-screen.tsx`) é o caminho único de TODO drill da tela - donut de
    filial, donut de modelo de equipe, tabela por filial, e os 3 gráficos de tendência. Cliques em
    sequência (filial → dia, por exemplo) se acumulam sem perder a memória do estado original -
    `preDrillFilters` só é capturado na PRIMEIRA vez, e "Voltar" desfaz a sequência inteira de uma
    vez, nunca passo a passo.
  - **Bug real encontrado e corrigido durante a verificação ao vivo**: "Voltar" restaurava o
    período mas deixava a filial clicada durante o drill presa no filtro. Causa: `update()` é um
    PATCH (mescla sobre o estado atual) - a fotografia de "antes do drill" pode legitimamente não
    ter a chave `regionals`/`team_models` (ausente, não lista vazia, quando a tela carrega sem
    nenhum filtro selecionado), e um PATCH sem essa chave simplesmente preserva o valor atual em vez
    de limpá-lo. Corrigido com uma função nova, `replace()` (`hooks/use-overview-filters.ts`), que
    SUBSTITUI o recorte inteiro em vez de mesclar - usada só pelo "Voltar" do drill.
  - **Verificado ao vivo numa base sintética**: clique numa filial (donut) → aviso aparece, filtro
    aplicado; clique num dia (gráfico) em cima disso → os dois efeitos acumulam, aviso continua
    apontando pro período ORIGINAL (não pro estado intermediário só-com-filial); "Voltar" restaura
    filial E período de uma vez (antes do fix, filial ficava presa). Repetido a partir da tabela por
    filial, mesmo resultado.
  - Frontend de produção desta máquina reconstruído e reiniciado.

- **Visão Geral: SLA ponderado em gráfico próprio, backlog separado do fluxo diário, e drill por
  dia com "voltar" dedicado** (2026-09-04, usuário: "coloque linhas do sla ponderado no grafico,
  coloque drill e pense em como ao usar o drill nao ficar fixo nos filtros").
  - **SLA ponderado**: reaproveitado `buildSlaTrendOption` (`lib/operations-chart-options.ts`), o
    MESMO construtor já usado no gráfico "SLA operacional" da Operação Analítica - sem lógica nova,
    só uma segunda tela consumindo o que já existia. Linha contínua = SLA acumulado ponderado do
    período; linha tracejada = SLA do dia; barras empilhadas no prazo/fora do prazo em eixo
    secundário. Card só aparece com `operations:view_sla` (mesma regra do resto da tela).
  - **Backlog voltou a ter gráfico próprio**, separado do "Fluxo diário": a rodada anterior (ver
    item mais abaixo) tinha colocado backlog como 3ª linha, eixo secundário, no mesmo gráfico de
    abertas/finalizadas - o usuário viu ao vivo e achou "carregado" (a escala do backlog ficou
    parecida com a de abertas/finalizadas neste banco, cruzando por cima das barras em vez de ficar
    em segundo plano). `buildOverviewFlowTrendOption` foi removida; "Fluxo diário" voltou a usar
    `buildOpeningsTrendOption` (o MESMO construtor do módulo de Operação, sem uma cópia própria da
    Visão Geral) e backlog ganhou `buildBacklogTrendOption` (`lib/overview-chart-options.ts`) -
    gráfico simples, uma linha, área sombreada leve.
  - **Drill por dia**: clicar numa barra/ponto de qualquer um dos 3 gráficos (Fluxo diário, SLA,
    Backlog) recorta a Visão Geral inteira pra aquele dia (`date_from = date_to = dia clicado`),
    mesmo mecanismo de filtro que os donuts já usavam (`onSelect` → `update`). `OperationsTrendChart`
    ganhou um `onEvents` opcional (repassado direto pro `ReactECharts`) - não existia antes.
  - **"Não ficar fixo nos filtros"** (risco que o próprio usuário pediu pra evitar): recortar por
    DIA muda a escala da tela inteira de uma vez, e "Restaurar padrão" não seria o caminho de volta
    certo (apagaria também filial/modelo/setor que o usuário tivesse escolhido antes do drill). A
    tela guarda `drillBackRange` - o período de ANTES do primeiro drill, só uma vez (um segundo
    clique não pisa nessa memória) - e mostra um aviso dedicado, distinto de "Restaurar padrão":
    "Detalhando {dia} · Voltar para {período anterior}".
  - **Verificado ao vivo numa base sintética isolada** (30 dias de O.S., SLA variando de propósito
    ao longo do período): clique numa barra do Fluxo diário recortou a tela pro dia certo (KPIs,
    tabela por filial, tudo recalculado), "Voltar" restaurou EXATAMENTE o período de antes; repetido
    a partir do gráfico de SLA - o "Voltar" continuou apontando pro período original (não pro dia do
    primeiro drill), confirmando que a memória não é pisada por cliques seguintes.
  - Frontend de produção desta máquina reconstruído e reiniciado. Nenhuma mudança de backend nesta
    rodada (reaproveita os mesmos endpoints já existentes).

- **Linha de backlog do "Fluxo diário" quebrava no meio do gráfico** (2026-09-04, usuário viu o
  gráfico ao vivo e reportou: "linha tracejada está falhada"). Causa raiz confirmada no banco real:
  a fotografia diária tinha 2 dias sem nenhuma linha dentro do próprio período já coberto (19/08 e
  23/08 - o job de captura não rodou naquela hora), e `connectNulls: false` interrompia a linha
  exatamente ali, parecendo um bug de renderização em vez de "sem dado". Essa situação é diferente
  do prefixo antes de `coverage_from` (10/08 em produção) - lá não existe NENHUM valor conhecido pra
  mostrar; num buraco interno existe, só não foi remedido naquela hora. `queries.backlog_daily_trend`
  passou a preencher buracos internos com o último valor conhecido (carry-forward, inclusive
  buscando a fotografia anterior mesmo fora da janela pedida, se o primeiro dia pedido já for um
  buraco) - só o prefixo antes de `coverage_from` continua ausente de verdade. 3 testes novos
  (buraco interno carrega o valor anterior; semente de fora da janela; prefixo antes da cobertura
  continua ausente). **Verificado contra o banco real** (leitura direta, função é 100% SELECT):
  19/08 e 23/08 agora vêm com o valor do dia anterior, contagem de pontos bate exatamente
  (26 = 30 dias pedidos − 4 antes da cobertura). Backend de produção desta máquina reconstruído e
  reiniciado.

- **Donuts da Visão Geral: "Outros" virava a MAIOR fatia** (2026-09-04, usuário: "esse negocio de
  outros lai nos donnuts não se se ficou legal"). Medido contra dado real: com as ~15 filiais de
  produção, o teto de 5 fatias nomeadas (`DEFAULT_MAX_SLICES`) deixava um "Outros" de **44%** no
  donut "Finalizadas por filial" - maior que qualquer filial nomeada, escondendo mais do que
  mostrava. Subiu para **8** (`frontend/lib/share-breakdown.ts`) - não é um número arbitrário, casa
  com o tamanho da paleta categórica (`CATEGORICAL_SLOTS`, 8 cores); além de 8, a cor deixaria de
  identificar a entidade de qualquer forma (cairia no mesmo cinza do "Outros", ver
  `assignSeriesColors`). Verificado numa base sintética com 13 filiais (mesma forma de cauda longa
  do dado real): "Outros" caiu para 20%, menor que várias filiais nomeadas.

- **Histórico de backlog no gráfico "Fluxo diário" da Visão Geral** (2026-09-04, usuário: "preccico
  que mostre o historico de backlog tbm"). Backlog é ESTOQUE, não fluxo - não dá pra só somar junto
  com abertas/finalizadas. Reaproveitada a fotografia diária que já existia
  (`OperationBacklogSnapshot`, capturada por `backlog_snapshot.py`, já usada pelo módulo `ai`) em vez
  de recalcular ao vivo de `OperationOrder`.
  - Backend: `queries.backlog_daily_trend` (nova) soma `backlog_count` por dia, respeitando o
    escopo regional do usuário e os filtros `regionals`/`sectors` - ignora `team_models`/
    `responsibles`/`os_types` (mesma convenção de `_backlog_filters`; a fotografia nem guarda as
    duas últimas dimensões). Endpoint novo `GET /operations/overview/backlog-trend`
    (`OperationBacklogTrend`), 5 testes em `test_operations_overview_backlog_trend.py`.
  - Frontend: nova função dedicada `buildOverviewFlowTrendOption`
    (`lib/overview-chart-options.ts`) - a Visão Geral passou a montar seu PRÓPRIO gráfico de fluxo
    diário em vez de importar `buildOpeningsTrendOption` do módulo de Operação, pra essa mudança não
    vazar pro gráfico do módulo. Backlog entra como uma 3ª linha, em eixo Y secundário (mesmo padrão
    dual-axis já usado em `buildSlaTrendOption` pro par SLA×contagem) - a escala de estoque tende a
    ser bem diferente da variação diária de abertas/finalizadas.
  - **Sem retroatividade, de propósito**: a fotografia só existe a partir de quando o job entrou em
    produção (10/08/2026 em produção real) - pontos sem fotografia ficam ausentes
    (`connectNulls: false`), nunca viram zero, que afirmaria um backlog nunca medido. Tela mostra um
    aviso textual quando o recorte pedido começa antes da cobertura existir.
  - **Verificado numa base sintética isolada** (10 dias de fotografia, gap propositalmente antes
    disso): a linha de backlog apareceu só a partir da data de cobertura, com o aviso de texto
    citando a data certa, e o eixo secundário com a escala de estoque (centenas) separada da escala
    de fluxo diário.
  - Imagens de produção (frontend e backend) desta máquina reconstruídas e reiniciadas com as duas
    mudanças.

- **Donuts da Visão Geral cortavam/escondiam o rótulo de %** (2026-09-04,
  usuário: "vejo que alguns numeros no grafico de pizza ainda está com
  numeros escondidos"). Causa raiz medida via DOM: o gráfico
  (`OverviewShareDonut`) vivia lado a lado com a lista, dentro de um grid de
  3 colunas — o canvas resultante tinha só **~180px de largura** contra
  **220px de altura**. O ECharts calcula o raio da rosca pela MENOR
  dimensão do canvas (a altura, aqui), então a largura sobrando pro rótulo
  de % fora do anel (com linha guia) ficava perto de zero — o texto era
  cortado pela própria borda do canvas. Não era um problema de fatia pequena:
  a fatia MAIOR (16,4%) já vinha cortada ("16,..."), e a fatia "Outros"
  virava pontinhos ilegíveis.
  **Corrigido** empilhando o gráfico (largura cheia do card) acima da lista,
  em vez de lado a lado — `components/overview/overview-share-donut.tsx`.
  Com a largura cheia (~400px+), sobra margem de sobra pra qualquer rótulo,
  em qualquer tamanho de tela (era esse layout, sem quebra, que já valia
  para telas < `sm`; agora vale sempre).
  **Verificado numa base sintética isolada** (schema clonado via
  `pg_dump --schema-only`, nunca dado real): 7 filiais com finalizadas
  próximas (42/40/38/37/35/33/31 — o cenário que reproduz o corte), antes e
  depois da correção, com o canvas ampliado via CSS pra inspeção pixel a
  pixel. Antes: "16,4%" cortado, "Outros" ilegível. Depois: as 6 fatias
  (16,4%/15,6%/14,8%/14,5%/13,7%/25%) legíveis por completo, em desktop
  (1600px), no recorte apertado de 3 colunas, e em mobile. Frontend de
  produção desta máquina reconstruído e reiniciado com a correção.

- **Mensagens do agente virtual Theo classificadas como "remetente não
  identificado" (corrigido)**: investigando `UNI2026810881` (TMR humano
  registrado em 13min), a timeline mostrava 14 eventos "remetente não
  identificado" no meio da conversa. Inspeção do payload bruto: `tipo:
  "assistant"`, com `role: "assistant"`/`role: "tool"` e `tool_calls` — é o
  **log interno do agente virtual Theo**, sem `id_user` nem `id_atend` porque
  não é atribuído a um cadastro de atendente. Confirmado como padrão (não
  coincidência do caso): amostra de 40 atendimentos recentes de qualquer
  atendente/departamento → 100 mensagens nessa condição, **100%**
  `tipo=="assistant"`.
  **Efeito antes da correção**: essas mensagens não batiam em nenhuma
  categoria (client/bot/human) e eram completamente descartadas de toda
  métrica — não fechavam intervalo no TMR geral, não contavam em
  `bot_message_count`. O Theo desaparecia do TMR geral exatamente quando era
  ele quem tinha respondido.
  **Pedido explícito do usuário**: "preciso que ele entre na mesma metrica de
  tmr geral, e o tmr humano seja so os identificados". Implementado como
  helper único `_message_is_from_theo_bot()` em `opa_ingestion.py`
  (`tipo=="assistant"` sem `id_user` nem `id_atend`), aplicado em 4 pontos —
  `_all_response_metrics` (TMR geral: fecha intervalo pendente, como
  qualquer bot), `_classify_bot_human` (conta como participação de bot),
  `_message_attendant_summary` (soma em `bot_message_count`), e a timeline
  (`opa_timeline_service.py`: rótulo "Mensagem do atendimento automatizado",
  não mais "remetente não identificado"). **TMR humano
  (`_human_response_metrics`) não foi tocado** — já excluía essas mensagens
  corretamente, que é o comportamento pedido.
  4 testes novos (TMR geral conta, TMR humano não; atendimento 100% Theo sem
  humano nenhum; contagens não vazam entre categorias; timeline classifica
  como bot). 168 testes do módulo passando, sem regressão. Imagem do backend
  reconstruída; `support_opa_sync_enabled` pausado durante o rebuild e
  reimportação de 03/09 (validação do caso real), **restaurado para `true`**
  ao final.
  Detalhamento completo em
  [roteiro-comparacao-tmr-opa-suite.md](roteiro-comparacao-tmr-opa-suite.md),
  seção 13.
  Arquivos: `opa_ingestion.py`, `opa_timeline_service.py`,
  `test_opa_ingestion.py`, `test_opa_attendance_table.py`.

- **Visão Geral executiva + navegação do ecossistema em barra lateral única (tela em
  tela, não módulo em módulo)**: entrada do sistema deixou de ser a grade de módulos.
  `/` virou só login e encaminha quem tem `operations:read` para **`/visao-geral`**;
  a grade antiga virou a tela `/modulos`. Quem NÃO tem `operations:read` (caso real
  do colaborador, que só usa o Portal) continua vendo a grade em `/`, senão cairia
  numa tela vazia.

  **Casca única** (`components/workspace/app-shell.tsx`): barra lateral completa +
  cabeçalho único, adotada pelas **7 páginas de módulo**. Cada módulo perdeu o
  cabeçalho e o menu hambúrguer próprios; as telas internas dele viraram submenu da
  barra, com link direto (`/operacao?tab=sla`). A autenticação saiu das páginas e
  ficou na casca — era trecho copiado nas 7. Barra nasce completa; recolher para
  trilha de ícones é escolha do usuário, guardada em `localStorage`.

  **Catálogo de telas** (`lib/module-screens.ts`): rótulos, descrições e ícones vêm
  das MESMAS listas que cada módulo já usava (`OPERATION_NAV_ITEMS`, `OPA_NAV_ITEMS`,
  `ADMIN_NAV_ITEMS`...), importadas — nunca uma segunda cópia. O que o catálogo
  acrescenta é a permissão por tela, para o menu não oferecer destino que o módulo
  recusa. **Atenção de manutenção**: essas permissões espelham o `visibleTabs` de cada
  página; aba nova com permissão própria precisa entrar nos dois lugares.

  **Backend novo** (3 endpoints, 19 testes):
  - `GET /operations/overview/regional-matrix` — quadro por filial. Cada coluna com
    escopo de filtro DELIBERADAMENTE diferente: `opened` ignora modelo de equipe e
    responsável (`_opening_filters`), `backlog` ignora também o período
    (`_backlog_filters`), `completed`/`sla_rate` respeitam tudo. O total soma
    contagens e recalcula o percentual (média de percentuais daria SLA que não
    corresponde a nenhuma O.S.). Sem `operations:view_sla` vem com volumes e colunas
    de prazo em branco, em vez de negar a tabela.
  - `GET /dashboard/gamification-preview` — valor corrente da gamificação. **Não**
    criou motor de prévia: `recalculate_current_period` já regrava o rascunho do mês
    corrente a cada ciclo do IXC, então o endpoint só lê, com `calculated_at` e
    `status` no payload para a tela poder dizer que a prévia está velha. Totais
    reconciliados das linhas `collaborator_scores`, nunca do JSON gravado (achado C1).
  - `GET`/`PUT /operations/overview/default-filter` — filtro pré-setado da tela,
    apontando para uma **visão global** existente (`app_settings`, sem migration).
    Visão pessoal é recusada com 422 e trocar o padrão exige
    `operations:views:update_global`.

  **Filtro na URL**: a Visão Geral publica período e dimensões em query string
  (`hooks/use-overview-filters.ts`) — recarregar mantém o recorte e o link filtrado
  é compartilhável. Período padrão: últimos 30 dias, cortados no início do ano
  operacional (em janeiro, 30 dias cairia em dezembro e `validate_operations_period`
  responderia 422).

  **Três bugs que só apareceram validando no navegador**:
  1. `router.replace` chamado dentro do updater do `setState` é descartado (React
     executa o updater durante a renderização) — o filtro não chegava na URL e o
     drill-through da tabela por filial não fazia nada. Virou efeito.
  2. Ler `?tab=` de `window.location.search` na montagem funciona ao recarregar mas
     NÃO em navegação pelo lado do cliente: a URL do navegador ainda não está
     atualizada na primeira renderização da rota nova, e o módulo abria sempre na aba
     padrão. Trocado por `useSearchParams` nas 5 páginas que faltavam (Suporte e
     Administração já tinham a leitura), cada uma com invólucro `<Suspense>`.
  3. Botão de expandir o submenu nascia fora da barra: o item de menu é `w-full` e
     não sobrava espaço.
  4. Trocar de tela ESTANDO dentro da Operação Analítica não fazia nada: mudar só a
     query não remonta a página, e o efeito que aplicava `?tab=` dependia de
     `filters`, que não muda nesse caso. Agora depende de `urlTab` também, com um
     `lastAppliedUrlTab` para o efeito não desfazer navegação interna (drill-through
     e o painel de Aberturas trocam de aba sem mexer na URL).

- **NÃO deixar o local no overlay de desenvolvimento nesta máquina.** Ficou medido:
  `docker compose -f docker-compose.yml -f docker-compose.dev.yml up` compila cada
  rota sob demanda em **8 a 21 segundos** neste disco (fonte no OneDrive, com
  polling), e ainda produz `500` com
  `SyntaxError: Unexpected end of JSON input (page: '/suporte')` — o servidor de dev
  lendo manifesto do `.next` pela metade. No build de produção as mesmas rotas
  respondem em **15–63ms**. O overlay serve para desenvolver com hot-reload; para
  usar o sistema, `docker compose build frontend backend && docker compose up -d`.

- **SGP Suporte não trocava de aba pelo submenu da barra lateral** (2026-09-03,
  "suporte?tab=attendants tem modulos que não está abrndo"). MESMA causa das outras 6
  correções de `?tab=` já registradas acima - `activeView` só era seedado da URL na
  MONTAGEM (`useState(initialTab)`), sem ressincronizar depois. O SGP escapou da
  varredura anterior por já importar `useSearchParams` - o que não basta sozinho, é
  preciso um efeito que reaja a ele. Corrigido com
  `useEffect(() => setActiveView(initialTab), [initialTab])`, reaproveitando
  `initialTab` (já resolve o alias "agents"→"attendants" e valida contra
  `ACTIVE_OPA_TABS`) em vez de duplicar a lógica. **Alarme falso durante a
  verificação**: o script de teste procurou um botão "Expandir telas de SGP Suporte"
  e não achou - mas o módulo ativo abre o próprio submenu sozinho (por desenho), então
  o botão já dizia "Recolher", não "Expandir". **Verificado de verdade**: Atendentes
  → Dados → Atendentes → sair para Gestão Integrada → voltar a Suporte → Atendentes,
  cada clique abrindo a tela certa.

- **Filtros do SGP (Departamento/Canal/Motivo) viraram multi-seleção estilizada**
  (2026-09-03, usuário viu o `<select>` nativo do navegador - "isso tá padrão?
  consigo selecionar mais de um?"). Os dois pontos eram válidos:
  - **Visual**: `SingleSelect` (um `<select>` HTML puro) destoava do resto da tela,
    que usa o `MultiSelect` com busca/checkbox estilizado. Componente removido
    (nenhum outro lugar do app usava).
  - **Funcional**: a rota `/support/opa/overview` declara `channel`/`department_id`/
    `reason_id` como `str | None`, mas por baixo
    (`opa_filters.py::_selected_values`) já quebra a string por vírgula e monta um
    `IN (...)` na consulta - **a lista já era aceita**, só nunca tinha sido ligada a
    uma seleção múltipla em tela nenhuma (nem o próprio módulo SGP Suporte usa isso
    hoje). Descoberto lendo a função de consulta, não só a assinatura da rota - a
    assinatura sozinha levaria a repetir o erro.
  - `hooks/use-overview-filters.ts`: os 3 campos do SGP passam a ser `string[]`
    (igual aos filtros de O.S.), guardados na URL como parâmetros repetidos
    (`?support_channel=A&support_channel=B`); só na hora de chamar
    `/support/opa/overview` (`overview-screen.tsx`) viram string separada por
    vírgula, no formato que o backend espera.
  - **Verificado ao vivo**: selecionar 2 canais mostrou a chamada de rede como
    `channel=Chat,Telefone` e o card "Atendimentos" somou os dois (50+50=100,
    confirmando o `IN (...)` funcionando); chip fechado mostrou "Canal (SGP): Chat,
    Telefone"; URL da página manteve os dois parâmetros separados (compartilhável).

- **Barra de filtros da Visão Geral recolhível** (2026-09-03, pedido do usuário:
  "moderno e recolhível"). `components/overview/overview-filter-bar.tsx` ganhou um
  cabeçalho sempre visível (ícone + "Filtros" + período em texto) com um toggle; o
  formulário completo (data, selects de O.S., bloco do SGP, rodapé com
  Restaurar/Definir padrão) recolhe atrás dele. Fechada, mostra **chips** removíveis
  com o resumo de cada filtro ativo (ex.: "Filial: UNI - VILHENA"), clicando o X do
  chip limpa só aquele campo. Preferência aberta/fechada persiste por navegador
  (`localStorage`, mesmo padrão já usado pela barra lateral) e nasce ABERTA no
  primeiro uso. Transição via truque de CSS Grid (`grid-rows-[0fr]`/`[1fr]`), sem
  medir altura em JS. **Verificado** no navegador: expandir/recolher, remover chip
  individual, persistência, mobile sem transbordo - inclusive um alarme falso (uma
  captura de tela pegou o quadro intermediário da transição de 200ms; confirmado
  como artefato de tempo, não bug, com a mesma tela após esperar assentar).

- **"Not Found" no painel de filtros da Administração (2026-09-03, reportado pelo
  usuário com screenshot)**: o backend em PRODUÇÃO nunca tinha sido reconstruído desde
  que os endpoints da Fase 3 (`/operations/overview/visible-filters`) foram escritos -
  as reconstruções das rodadas anteriores fizeram só `docker compose build frontend`,
  nunca `backend`. O container rodava código de antes da Fase 3, sem a rota, daí o
  404 puro (não um JSON de erro do FastAPI) que apareceu como "Not Found" na tela.
  Confirmado com `curl` direto no backend antes/depois: 404 → 401 (rota existe, só
  exige login) após `docker compose build backend && up -d backend`. **Regra daí em
  diante**: qualquer mudança de rota no backend exige reconstruir o backend também, não
  só o frontend - os dois builds são independentes e um não substitui o outro.

- **Correções na navegação (2026-09-03, relatadas pelo usuário após usar a barra por um
  tempo, verificadas ao vivo por simulação de clique no navegador)**:
  1. **A Administração não trocava de aba pelo submenu da barra lateral.** Ficou de fora
     da correção de `?tab=` feita na Fase 2 da Visão Geral (achado #4 já registrado
     acima) - continuava lendo `window.location.search` num `useEffect(..., [])` que só
     roda uma vez. Clicar num submenu da Administração (ex.: "Perfis") trocava a URL mas
     o conteúdo continuava mostrando a aba anterior, porque a navegação do Next.js não
     remonta a página. Corrigido com o mesmo padrão `useSearchParams` + `<Suspense>` já
     usado nos outros 6 módulos. Verificado clicando de verdade: Perfis → Módulos trocou
     o conteúdo sem recarregar a página.
  2. **Removida a tela "Módulos" (grade de cards) do grupo "Telas" da barra lateral**
     (decisão do usuário: com o submenu de cada módulo já disponível na própria barra,
     ela virou uma segunda forma de chegar ao mesmo lugar). Fica só "Visão Geral" no
     grupo. A rota `/modulos` continua existindo (é para onde `/` manda quem não tem
     `operations:read`) - só não tem mais entrada na barra. **NÃO confundir com** a aba
     "Módulos" de DENTRO da Administração (`/admin?tab=modules`, visibilidade por
     perfil) - essa continua existindo, foi pedido explicitamente preservado (pergunta
     feita ao usuário para desambiguar as duas telas com o mesmo nome).
  3. **Vão em branco na barra lateral, crescendo sem limite com a altura da página** -
     medido em 934px numa Visão Geral de 1599px de altura. Causa raiz: `<aside>` era só
     mais um item do `flex-row` da casca, e `align-items: stretch` (padrão) o esticava até
     a altura da COLUNA DE CONTEÚDO (que cresce com o tanto de gráfico/cartão da tela) -
     não até a altura da viewport. O `flex-1` do `<nav>` interno enchia esse excesso todo
     de vazio entre o último módulo e o rodapé (nome/e-mail do usuário). Corrigido com
     `lg:sticky lg:top-0 lg:h-screen` no `<aside>` (`components/workspace/app-shell.tsx`):
     a barra agora fica presa à altura da viewport, independente de quão alta a tela de
     conteúdo fique, e continua visível enquanto a página rola. **Medido**: vão caiu de
     934px para 236px numa viewport de 900px (o vão residual agora é limitado pela
     viewport, não pela página, e cresce/encolhe com a altura da tela do usuário, não
     com a altura do conteúdo). Verificado também: barra permanece fixa ao rolar a
     página, modo recolhido (trilha de ícones) continua ocupando a viewport inteira sem
     esticar, mobile sem regressão (`aside` continua `display:none` abaixo do breakpoint
     `lg`, gaveta `Sheet` inalterada).

- **Fase 3 — Filtros da Visão Geral configuráveis pela Administração** (2026-09-03,
  validada no navegador com dado sintético em banco isolado). Decisão do usuário: a
  configuração fica na Administração, não na própria Visão Geral.
  - **Catálogo único no backend** (`operations/router.py::OVERVIEW_FILTER_CATALOG`): 5
    filtros de O.S. (grupo `operations`) + 3 do SGP - departamento, canal, motivo (grupo
    `support`). Guardado em `app_settings` (`overview_visible_filters`), chave separada por
    vírgula; PUT rejeita chave fora do catálogo com 422 — a tela só sabe desenhar o que o
    catálogo lista, então não há como configurar algo que não funcione. Sem configuração,
    volta aos 5 filtros de O.S. de sempre (`GET`/`PUT /operations/overview/visible-filters`,
    mesma permissão do filtro padrão: `operations:views:update_global`). 5 testes.
  - **Os dois grupos NUNCA se misturam na tela** — era o risco explícito do pedido
    ("filial" de O.S. e "departamento" do OPA são universos diferentes; misturar geraria
    números de recortes distintos lado a lado, sem erro nenhum). Os filtros do SGP entram
    num bloco visualmente separado ("recortam só os blocos de atendimento"), aceitam UM
    valor cada (é o que `/support/opa/overview` recebe: `department_id`/`channel`/
    `reason_id` escalares, daí o `SingleSelect` novo em vez do multi-select), e mudar um
    filtro do SGP **não** dispara os endpoints de O.S. (confirmado contando chamadas de
    rede antes/depois: 2→2). `hooks/use-overview-filters.ts` ganhou `OverviewFilters` (O.S.
    + SGP) e `operationFiltersOf()`, que extrai só a parte de O.S. para os endpoints que
    não entendem o resto.
  - **Painel na Administração** (`components/admin/overview-settings-panel.tsx`), encaixado
    na aba Módulos: dois grupos de checkbox (um por catálogo), botão Salvar só habilitado
    com mudança pendente, mostra (só leitura) qual visão global está pré-setada e linka
    para defini-la na própria Visão Geral. Quem não tem a permissão vê os checkboxes
    desabilitados, não a tela inteira bloqueada.
  - **Verificado**: salvar no painel grava no backend (confirmado lendo o endpoint direto);
    a Visão Geral reflete a configuração (selects do SGP aparecem só quando marcados);
    selecionar um canal filtra o donut e o card do SGP sem recarregar os blocos de O.S.
    Limite da validação: uma checagem de texto pelo título do painel deu falso negativo
    (quebra de linha diferente do esperado no `innerText`) — os checkboxes com os rótulos
    certos apareceram e o salvamento funcionou, então o painel estava lá; não foi
    reconfirmado por screenshot.

- **Fase 2 — Visão Geral "premium"** (2026-09-03, validada no navegador com dado sintético em
  banco isolado). Decisões do usuário: donuts de Finalizadas por filial, por modelo de equipe
  e Atendimentos por canal; comparação com a janela imediatamente anterior do mesmo tamanho.
  - **Gráficos seguem um método, não gosto** (skill `dataviz`): paleta categórica única em
    `lib/chart-palette.ts`, **validada por script** contra o fundo branco dos cards (PASS; pior
    par adjacente sob protanopia ΔE 9,1). Slots 3–5 ficam abaixo de 3:1 de contraste → todo
    donut mostra rótulo direto (%) + lista lateral com valor, que faz o papel de legenda e de
    vista em tabela. Os azuis da marca são próximos demais entre si para identificar séries;
    ficam na interface, não nos dados.
  - **Donut só até 6 fatias**: `lib/share-breakdown.ts` dobra a cauda em "Outros" (5 nomeadas
    + Outros) e atribui cor pela ENTIDADE em ordem alfabética, nunca pela posição — filtrar não
    repinta quem sobrou. Com 14 filiais reais, o donut por filial responde *concentração*; o
    quadro abaixo continua respondendo *quanto cada uma*. Tudo testado (`share-breakdown.test`).
  - **Comparação de período** nos KPIs de O.S.: segunda chamada de `/operations/overview` com a
    janela anterior (`lib/period.ts`, testado), cortada no início do ano operacional quando
    preciso e ausente quando não há janela comparável. Backlog não compara (é retrato). Delta
    no `SummaryMetric` (prop nova `delta`): cor = direção × se subir é bom.
  - **Meta por filial** no quadro: `/operations/capacity-summary` já existia e estava sem uso
    na tela; agora coluna "Meta da filial" com faixa (rótulo + fundo, nunca só cor) e
    "realizado de limiar · faltam N". Filial sem faixa mostra "sem meta cadastrada".
  - **Frescor do dado** (`/operations/data-freshness`) na linha de contexto sob os filtros;
    prévia da gamificação deixou de aparecer duas vezes (saiu da faixa de KPIs, ficou o card);
    bloco "Navegação do módulo" da Gamificação removido (redundante com a barra lateral) —
    com ele foram os tooltips de ajuda por aba (`TAB_HELP`), que não tinham outro uso.
  - **Código**: `hooks/use-block-query.ts` substituiu as 6 cópias de
    `useState(dado)/useState(status)/useEffect(carregar)` na tela — garante que resposta
    atrasada de filtro antigo não sobrescreve a nova e que recarga não pisca esqueleto.
    Todo gráfico novo deve nascer com construtor de opção em `lib/*-chart-options.ts` e cor
    vinda de `chart-palette.ts`.
  - **Verificado**: KPIs com delta, 3 donuts com lista, coluna de meta nos 3 estados, clique
    na lista aplica o filtro (URL e quadro reagem), mobile sem transbordo horizontal, console
    limpo. Limite: o painel embutido colapsa a viewport de forma intermitente, então a
    renderização do canvas dos donuts foi conferida por amostragem, não em toda medição.

- **Fase 1 do plano de performance — Gamificação abrindo rápido** (medido no bundle de
  produção e na cascata de requisições, 2026-09-03). O backend não era o gargalo
  (`/dashboard/summary` no caminho de cache: 26 KB, 224 linhas). Três causas no frontend:
  1. `dashboard-charts.tsx` era o **único** lugar do sistema importando o ECharts de
     forma estática (chunk de 1.040 KB no carregamento inicial) — agora `dynamic()`
     como os outros 8 componentes.
  2. ExcelJS importado no topo de 3 hooks de exportação (`use-closure-actions`,
     `use-calendar-export`, `use-sla-export`) e **duplicado** em dois chunks de 912 KB —
     agora `import type` + `await import("exceljs")` só ao clicar em exportar. Total de
     chunks: 6,9 → 6,0 MB; ~1,9 MB fora do carregamento inicial da Gamificação.
  3. Cadeia serial `me`+`bootstrap` → `summary`: sem parâmetro, `/dashboard/summary`
     resolve o MESMO `latest_run` que o `bootstrap`, então o summary agora parte na
     montagem, junto com os dois (`prefetchedSummary` em `loadAll`, sem GET duplicado —
     confirmado na cascata: summary e bootstrap no mesmo lote).
  Os 5 gráficos do fechamento (seção "Análise") só renderizam ao rolar até eles
  (`components/ui/defer-until-visible.tsx`), com dois caminhos: `IntersectionObserver`
  e geometria (`lib/viewport.ts`, testada). O segundo existe por achado real: o navegador
  embutido usado na validação não entrega callbacks de `IntersectionObserver` nem com um
  observer criado à mão sobre elemento visível — sem a via geométrica, esqueleto para
  sempre. **Limite da validação**: o adiamento dos gráficos foi provado por teste
  unitário da regra e por typecheck, não visualmente — o painel embutido colapsa a
  viewport para 0px de forma intermitente. Conferir abrindo `/gamificacao` → Fechamento
  → Análise e rolando.

- **Responsividade da navegação: cache curto das chamadas da casca**
  (`lib/api.ts`, `SESSION_CACHED_PATHS`). Com a barra em todas as telas, cada troca
  de tela remontava a casca e refazia `/auth/me` + `/workspace/modules` antes de
  desenhar o menu — aparecia como "Carregando UNI Workspace..." piscando em cada
  navegação. Agora são 30s de cache por sessão, invalidado em qualquer troca de token
  (cobre também o login/logout legado da Gamificação, que chama `setAuthToken`
  direto), e os dois hooks (`use-workspace-auth`, `use-visible-modules`) nascem
  semeados do cache de forma síncrona. **Medido**: 3 navegações pela barra passaram de
  3 para 1 requisição de cada endpoint (a única restante é o TTL vencendo). Contador
  de notificações ficou de fora de propósito — precisa estar fresco.


- **Bug de importação do SGP Suporte: 4 horas perdidas em todo último dia de
  cada importação (corrigido + reimportado)**: investigação da divergência de
  Jennyfer Tavares (cockpit 260 × SGP 216 em 23–31/08) com exportação real do
  cockpit em CSV — primeira comparação protocolo a protocolo.
  **Causa raiz** (`opa_ingestion.py`, guarda de período): comparava a data
  **UTC** de `opened_at` contra `run.date_from`/`date_to`, que são datas
  **locais** (America/Porto_Velho, UTC-4). Atendimento aberto às 21h locais já
  é o dia seguinte em UTC → rejeitado, mesmo tendo sido devolvido corretamente
  pela API. Silencioso: só engordava `rejected_count` e o dia aparecia
  completo na tela. Como o guard só corta o **último dia do intervalo**,
  backfills mensais perdiam só a cauda do último dia, mas runs diárias perdem
  4h **todo dia**.
  **Prova aritmética**: run de 31/08 tinha `fetched 2660 / rejeitados 182` e a
  base tinha exatamente 2.478 (`2478 + 182 = 2660`). Após a correção: `criados
  182, rejeitados 0`.
  **Correção**: converter para o fuso local antes de comparar
  (`.astimezone(SUPPORT_TIMEZONE).date()`), com 2 testes de regressão (aceita
  23:30 local do dia importado; continua rejeitando outro dia). 164 testes do
  módulo passando.
  **Reimportação**: 587 atendimentos recuperados nos 5 dias afetados de 94
  analisados — 30/06 +143, 31/07 +89, 31/08 +182, 01/09 +136, 02/09 +37,
  todos com `rejeitados 0`. Imagem do backend reconstruída para o scheduler
  carregar a correção; `support_opa_sync_enabled` pausado durante a operação e
  **restaurado para `true`** ao final.
  **Resultado**: dos 260 do cockpit, o SGP passou a ter **260/260**. Total,
  regra de atribuição e avaliação (**4,49 exato**) agora batem.
  **Regra de atribuição confirmada**: o CSV do cockpit tem a coluna "Último
  atendente" = nosso `attendant_id`. Zero divergência de atribuição — encerra
  a hipótese de "equivalência de filtro incerta" levantada na seção 10.1 do
  roteiro. `first_human_attendant_id` e `distinct_human_attendant_ids` são
  conceitos diferentes e não são o que o cockpit usa.
  **TMA — pendência conhecida, não é bug**: o endpoint de detalhe do OPA
  devolve as mesmas 18 chaves da listagem, ou seja **não existe campo de TMA
  na API deles**. Medido com mensagens reais (amostra de 20): bruto 00:42:48,
  ativo descontando ocioso >10min **00:20:50** contra o alvo **00:19:18** do
  cockpit. O TMA do OPA é **tempo efetivo com desconto de ociosidade**; o
  nosso `tma_seconds` (`fim` − `date`) é outra métrica. O mesmo mecanismo
  explica o TMR: os 44 recuperados têm TMR médio 00:03:40 contra 00:00:15 dos
  demais, mas **mediana igual** (12s vs 10s) — a responsividade é a mesma, o
  que difere são as lacunas de madrugada. **Encaminhamento**: (1) renomear
  nossa métrica para "duração total" — imediato e risco zero; (2) calcular
  tempo efetivo no mesmo passo que já busca mensagens, exibindo ao lado do
  bruto, nunca no lugar; (3) pedir a definição oficial ao OPA — único caminho
  definitivo, já que o limiar de ociosidade foi ajustado para casar com o
  agregado (confirma a classe da métrica, não a fórmula).
  Detalhamento completo em
  [roteiro-comparacao-tmr-opa-suite.md](roteiro-comparacao-tmr-opa-suite.md),
  seção 12.
  Arquivos: `opa_ingestion.py`, `test_opa_ingestion.py`.

- **Correção de nomes de atendente do SGP Suporte na VM**:
  na VM vários atendentes apareciam como ID na tela; local está normalizado.
  **Causa**: `_normalize_attendance` já resolve o nome pela dimensão `user`,
  mas o fallback só entra quando o campo de nome vem **vazio**. Quando a API do
  OPA devolve o próprio `id_atendente` no campo de nome — ou quando o
  atendimento foi importado antes de a dimensão existir localmente — o id fica
  gravado em `attendant_name`, e ranking, tabela, filtros e `/opa-metrics` leem
  essa coluna crua. Já existia `_backfill_customer_names` fazendo exatamente
  essa auto-cura para **cliente**; não havia equivalente para **atendente**.
  **Solução versionada, em três partes**:
  1. `backfill_attendant_names(db)` em `opa_ingestion.py` — helper único,
     espelha o de cliente e cobre também `attendant_name == attendant_id`.
     Exige que o nome da dimensão seja diferente do id, senão trocar id por id
     quebraria a idempotência.
  2. Chamado no sync de dimensões, ao lado do de cliente — **auto-cura**: toda
     sincronização normaliza o que passou a ter tradução disponível.
  3. `backend/scripts/fix_opa_attendant_names.py` — correção explícita e
     idempotente, `--dry-run` como padrão seguro, `--apply` para gravar. Usa o
     mesmo helper (fonte única). Não chama API do OPA, não importa, não toca
     `attendant_id`, `raw_payload`, TMA nem TMR.
  **Correção preventiva adicional**: `resolve_attendant_identity` usava
  `attendance_name or dimension_name` — o id gravado como nome é "truthy" e
  vencia o nome bom da dimensão, então o painel individual mostrava hash mesmo
  com a dimensão sincronizada. Passou a usar `_readable_name()`, helper único
  no service (sem duplicar lógica em rota).
  **Detalhe que teria quebrado na VM**: rodando `python scripts/x.py`, o Python
  põe `/app/scripts` em `sys.path[0]`, não `/app` — `import app` falhava com
  `ModuleNotFoundError`. O script tem bootstrap de `sys.path`, então as duas
  formas de chamada funcionam sem PYTHONPATH nem ajuste de ambiente na VM.
  **Comandos na VM** (sem instalar nada):
  ```
  docker compose build backend
  docker compose up -d backend
  docker compose exec -T backend python scripts/fix_opa_attendant_names.py --dry-run
  docker compose exec -T backend python scripts/fix_opa_attendant_names.py --apply
  docker compose exec -T backend python scripts/fix_opa_attendant_names.py --dry-run
  ```
  A terceira execução confirma a idempotência (deve reportar 0 corrigíveis).
  Se sobrar "pendentes sem dimensão", é atendente que o OPA não tem no cadastro
  de usuários: sincronizar dimensões e rodar de novo. O script nunca inventa
  nome.
  **Validado**: o diagnóstico reproduz exatamente o baseline local medido
  (122.208 atendimentos, 121.730 com id, 0 com nome == id, 11 com nome vazio,
  245 dimensões `user`); `--apply` em dado real local é no-op (0 atualizados,
  exit 0). 13 testes novos em `test_opa_attendant_name_fix.py` (dry-run não
  grava, corrige vazio, corrige nome == id, não sobrescreve nome humano, deixa
  pendente sem dimensão, idempotência, não toca id/payload, ranking passa a
  exibir nome, painel individual prefere dimensão). Suíte backend
  **888 passed / 13 failed** (as mesmas 13 falhas pré-existentes do módulo AI).
  Frontend não foi tocado.
  Arquivos: `opa_ingestion.py`, `opa_attendant_service.py`,
  `scripts/fix_opa_attendant_names.py` (novo),
  `tests/test_opa_attendant_name_fix.py` (novo).


- **Auditoria da Estrutura Operacional Confiável - nova (backend + frontend, sem migration)**:
  pedido do usuário em 2026-08-29 - fase preparatória antes de
  "capacidade regional automática": mostrar de forma clara as divergências entre Gamificação
  (`Collaborator`), Operação (`OperationOrder`/`OperationResponsibleAssignment`/
  `OperationTeamModel`/`OperationBranchCapacity`) e Gestão (`ManagementOperationalMember`) antes de
  avançar. **Só leitura, nenhuma chamada ao IXC, nenhum dado alterado.**

  **Backend**: novo service dedicado `backend/app/modules/management/structure_audit.py`
  (`run_structure_audit`) - reaproveita `resolve_responsible_regional_candidates`
  (operations/responsible_regional.py) e `_find_collaborator`/`_norm_name`
  (management/services.py), mesmas funções já usadas por `refresh_operational_members`, em vez de
  duplicar a lógica de casamento responsável×colaborador. Novo endpoint
  `GET /api/management/structure-audit` (permissão nova `management:audit_structure:read`,
  registrada em `PERMISSION_LABELS`/`ROLE_PERMISSIONS["admin"]`, `core/security.py`), schemas
  `StructureAuditFinding`/`StructureAuditSummary`/`StructureAuditOut`
  (management/schemas.py).

  **13 auditorias cobertas** (uma função por grupo, todas independentes e aditivas à mesma lista de
  achados): colaborador ativo sem `ixc_employee_id`; sem CPF local; sem `team_type`; campo sem
  supervisor; responsável da Operação sem `Collaborator` correspondente; responsável com produção
  em mais de uma regional; regional oficial do colaborador divergente da regional predominante das
  O.S. (via `responsible_ixc_id`); membro de Gestão sem modelo de equipe; modelo de equipe inativo
  ainda referenciado por membro/cadastro ativo; regional com estrutura ativa mas sem
  `OperationBranchCapacity` configurada; capacidade com limiar zerado/ausente/fora de ordem
  (bom < ótimo < excelente); membro pendente de validação; membro com produção nos últimos 30 dias
  mas status estrutural ainda pendente (o achado mais acionável - já está trabalhando sem estrutura
  resolvida). Cada achado carrega severidade (`critico`/`atencao`/`informativo`), descrição em
  pt-BR, entidade/regional/responsável afetados, sugestão de correção e se bloqueia o cálculo de
  capacidade - nunca CPF completo (só ausência/presença).

  **Achado real corrigido durante a própria validação ao vivo**: o corte de segurança contra lista
  ilimitada (`manual_desenvolvimento_senior.md`) inicialmente cortava a lista JÁ ORDENADA por
  severidade (crítico primeiro) - com `atencao` tendo muito mais linhas que `informativo`, um corte
  global de "top N" deixava `informativo` inteiro de fora da lista (aparecia certo no card com
  contador, mas filtrar por ele mostrava "nenhum achado"). Corrigido para cortar POR SEVERIDADE
  (`MAX_FINDINGS_PER_SEVERITY = 700`) - toda severidade com achado real aparece com pelo menos uma
  amostra. Os contadores (`critical_count`/`attention_count`/`informative_count`/`total_findings`)
  sempre refletem o total real, mesmo com a lista cortada.

  **Frontend**: novo componente `frontend/components/management/structure-audit-panel.tsx` (busca
  os próprios dados, sem props - mesmo padrão de `ManagementCaseDiagnosticsPanel`) - resumo com
  KPIs, 3 cards clicáveis por severidade (cor própria, funcionam como filtro), filtros de
  severidade/regional/tipo, tabela escaneável com badge de severidade e de "bloqueia capacidade",
  estados de loading/vazio/erro, aviso visível quando a lista está cortada pelo limite de
  segurança. Nova aba "Auditoria da estrutura" em `/gestao` (`management-module-sidebar.tsx`,
  `gestao/page.tsx`), atrás da permissão nova.

  **Corrigido de propósito, fora do escopo original mas no mesmo arquivo tocado**: o mesmo menu
  lateral de Gestão Integrada (`management-module-sidebar.tsx`) tinha o mesmo bug de rolagem já
  corrigido em `module-navigation-sidebar.tsx` (`nav` sem `overflow-y-auto`/`min-h-0` corta o
  último item em telas baixas) - corrigido junto, antes de adicionar o 5º item.

  **Testes**: `backend/tests/test_management_structure_audit.py` (28 casos) - um por tipo de
  achado (presente e ausente), contadores de resumo batendo com o dado bruto, permissão (403 sem
  `management:audit_structure:read`, 200 com ela), nenhum CPF completo em nenhum campo da resposta,
  e um teste de regressão específico do bug do corte por severidade (via `monkeypatch` no limite,
  reproduz o "informativo sumia da lista" e confirma a correção).

  **Validado**: backend **874 passed, as mesmas 13 falhas pré-existentes do módulo de IA**; `npx
  tsc --noEmit`, `npm run test -- --run` (45/45), `npm run build` - limpos. **Validado ao vivo
  contra o banco real de desenvolvimento**: números batem exatamente com o levantamento manual que
  motivou a tarefa (383 colaboradores, 356 com `ixc_employee_id`, 1 com CPF local - o pedido
  original registrava 0, diferença de dado real entre o levantamento e agora, não bug -, 370
  ativos, 369 sem `team_type`, 207 `OperationResponsibleAssignment` todos com modelo de equipe, 0
  linhas em `operations_branch_capacity`, 1283 membros de Gestão, 206 com modelo de equipe);
  resultado real: **491 achados críticos, 3027 de atenção, 382 informativos**. Filtro por
  severidade/regional/tipo conferido na tela (incluindo o cenário que expôs e validou a correção do
  bug de corte). Nenhum dado alterado - endpoint é 100% leitura.

  **Limitações conhecidas**: lista de achados tem limite de segurança de 700 por severidade
  (`MAX_FINDINGS_PER_SEVERITY`) - com a base de hoje (3900 achados totais) a severidade `atencao`
  fica cortada (700 de 3027), os contadores continuam exatos. "Regional divergente da produção"
  (achado 7) só compara contra o histórico de `OperationOrder.responsible_ixc_id` - não considera
  peso por recência (uma mudança de base recente pode não superar meses de histórico antigo na
  regional anterior). Auditoria é um retrato do momento da chamada (sem histórico/tendência) -
  correto para o objetivo desta fase (fase preparatória), mas não serve pra acompanhar evolução ao
  longo do tempo ainda.

  **Próximos passos sugeridos para a Fase 3B (capacidade regional automática)**: usar os achados
  desta auditoria como pré-requisito de bloqueio (`blocks_capacity=true`) antes de calcular
  capacidade por regional de verdade - hoje `operations_branch_capacity` está com 0 linhas, então
  nenhuma regional tem capacidade configurada; decidir se a Fase 3B exige zerar os achados críticos
  primeiro ou se calcula capacidade só para as regionais sem achado bloqueante; considerar guardar
  um snapshot periódico desta auditoria (`management_structure_audit_runs`, mesmo padrão de outras
  tabelas de execução já usadas no projeto) para medir se o número de achados está diminuindo ao
  longo do tempo.

  Sem migration (nenhuma tabela nova, só service/schema/rota/permissão/tela). Arquivos:
  `backend/app/core/security.py`, `backend/app/modules/management/structure_audit.py` (novo),
  `backend/app/modules/management/schemas.py`, `backend/app/modules/management/router.py`,
  `backend/tests/test_management_structure_audit.py` (novo), `frontend/lib/types.ts`,
  `frontend/lib/api.ts`, `frontend/components/management/structure-audit-panel.tsx` (novo),
  `frontend/components/management/management-module-sidebar.tsx`, `frontend/app/gestao/page.tsx`.
  Sem commit, sem push, sem regra financeira alterada, sem regra de gamificação alterada, sem
  chamada ao IXC, sem dado real alterado (endpoint só de leitura).

- **Fase 2D: aprovação de solicitação de acesso passa a criar a conta direto, sem convite/link
  manual (backend + frontend + migration aplicada, ainda sem commit, sem push)**: pedido do
  usuário em 2026-08-29, em três partes - (1) prioridade de sugestão de colaborador na aprovação,
  (2) aprovar não gera mais convite, a pessoa já define a própria senha ao solicitar, (3) reforço
  visual de pendências/sugestão em `/admin` (a separação de contas internas/Portal/convites/
  solicitações já tinha sido entregue na rodada anterior, ver entrada abaixo).

  **Backend**: `submit_access_request` (`services/portal_access_requests.py`) agora reaproveita
  `find_local_collaborator` (mesma função já usada pelo convite por CPF/IXC, Fase 2C) pra sugerir
  colaborador com prioridade completa `ixc_employee_id` > CPF > nome - antes só casava por CPF
  exato. Só entra em jogo quando o nome vem CONFIRMADO pelo IXC (o caminho manual, sem IXC, segue
  casando só por CPF, porque ali o nome não é verificado). `find_funcionario_identity_by_cpf`
  (`services/ixc_collaborator_lookup.py`) passou a expor `ixc_employee_id` internamente pra isso -
  nunca serializado em resposta pública.

  **Mudança de segurança principal**: `PortalAccessRequestCreate` ganhou `new_password`/
  `confirm_password` (mesmos limites de `PortalInviteAcceptRequest`, min. 8 caracteres) - a pessoa
  já escolhe a própria senha ao solicitar acesso; só o hash vai para `PortalAccessRequest.
  password_hash` (coluna nova, nullable - migration `20260829_0084_portal_access_request_password.py`,
  puramente aditiva). `approve_access_request` não chama mais `create_invite` (Fase 2C) - cria o
  `User` DIRETO, reaproveitando exatamente o padrão de `accept_invite` (role `collaborator`,
  `active=True`, senha já hasheada, `must_change_password=False`, `first_access_completed_at=None`
  - o onboarding da Fase 1 continua rodando depois, normalmente). Continua exigindo
  `collaborator_id` explícito no corpo (nunca aceito por omissão) e recusa (409) colaborador já
  vinculado ou e-mail já cadastrado. Solicitação criada ANTES desta coluna existir (havia uma real
  em uso) fica com `password_hash` nulo - a aprovação recusa com erro claro (422) pedindo reenvio,
  nunca cria conta sem senha nem apaga o dado antigo. `password_hash` é limpo da solicitação
  (aprovada ou rejeitada) depois de decidida - minimiza retenção de hash sem propósito. **O
  convite manual e o convite por CPF/IXC (Fase 2C) continuam exatamente como estavam** - só a
  aprovação de solicitação de acesso mudou de mecanismo.

  **Frontend**: `access-request-form.tsx` ganhou campos de senha + confirmação nas duas telas
  finais (achou no IXC / manual), texto de conclusão atualizado (já pode entrar, sem mencionar
  link). `access-requests-panel.tsx` (`/admin`) ganhou badge "Sugestão por CPF/IXC: {nome}" visível
  acima do select (antes só um `(sugestão)` discreto dentro da opção) e destaque de fundo nas
  linhas pendentes; aprovar mostra mensagem de conta criada em vez de abrir banner de link.

  **Testes**: `test_portal_access_requests.py` reescrito - 31 casos (era 23). Novos: prioridade
  `ixc_employee_id` sobre CPF conflitante; prioridade por nome quando não há match mais forte;
  senha armazenada como hash (nunca em claro, nem na auditoria); confirmação de senha divergente
  e senha curta rejeitadas (422); aprovação cria o `User` direto (sem `AccountActionToken`) com
  todos os campos certos; **login real no `/portal` com o e-mail e a senha da solicitação,
  depois de aprovado**; solicitação sem senha (legado) recusa aprovação; colaborador/e-mail já
  vinculado recusa aprovação (409); `password_hash` limpo após aprovar/rejeitar.

  **Validado**: backend **847 passed, as mesmas 13 falhas pré-existentes do módulo AI**; `npx tsc
  --noEmit`, `npm run test -- --run` (45/45), `npm run build` - limpos. **Validado ao vivo, de
  ponta a ponta, no navegador real**: solicitação enviada pelo formulário público (CPF de teste
  sintético, caminho manual) com senha definida na hora → confirmado no banco que só o hash foi
  gravado e que ele valida a senha digitada → aprovada em `/admin` contra um colaborador QA
  temporário → confirmado no banco **exatamente 1 `User` criado**, sem nenhum `AccountActionToken`,
  `password_hash` da solicitação limpo → **login real em `/portal` com o e-mail e a senha
  cadastrados funcionou**, caiu no onboarding da Fase 1 normalmente (esperado, mesmo
  comportamento de quem entra por convite). Colaborador, usuário e solicitação de teste apagados
  ao final (mais as entradas de auditoria correspondentes) - 0 linhas residuais.

  Migration aplicada ao banco real (`docker exec ... alembic upgrade head`, confirmado `alembic
  current` = `20260829_0084`). Rebuild de produção feito (`docker compose build backend frontend`
  + `up -d`) - confirmado que a imagem de produção reflete o código novo.

  Arquivos: `backend/app/models.py`,
  `backend/alembic/versions/20260829_0084_portal_access_request_password.py` (novo, migration
  aplicada ao banco real), `backend/app/schemas.py`,
  `backend/app/services/ixc_collaborator_lookup.py`,
  `backend/app/services/portal_access_requests.py`, `backend/app/api/routes/access_requests.py`,
  `backend/tests/test_portal_access_requests.py`, `frontend/lib/types.ts`, `frontend/lib/api.ts`,
  `frontend/components/portal/access-request-form.tsx`, `frontend/app/admin/page.tsx`,
  `frontend/components/admin/access-requests-panel.tsx`. Sem commit, sem push, sem regra
  financeira alterada, sem dado real alterado (colaborador/usuário/solicitação eram só QA,
  apagados ao final).

- **Refatoração visual da Administração + tela inicial sem menção à "Gamificação" (frontend, sem
  commit, sem push)**: pedido do usuário em 2026-08-29 pra modernizar `/admin` (hoje um arquivo
  único de 1834 linhas com uma aba "Usuários" misturando contas internas, contas do Portal,
  convites e solicitações) e ajustar a tela inicial de login.

  **`/admin` quebrado em componentes** dentro de `frontend/components/admin/` - `admin/page.tsx`
  manteve 100% do estado, handlers e chamadas de API (nada de regra de negócio movida), só o JSX
  virou orquestração de componentes menores: `admin-overview-panel` (novo painel "Visão geral" -
  KPIs, cards de pendências clicáveis pra convites/solicitações/estrutura, absorve o conteúdo da
  antiga aba "Parametrizações"), `accounts-table` + `internal-accounts-panel`/
  `portal-accounts-panel` (split da antiga tabela única de usuários por `collaborator_id` - null
  = conta interna, preenchido = conta do Portal, só um filtro visual sobre os mesmos dados),
  `invites-panel`, `access-requests-panel`, `people-structure-panel`, `profiles-panel` +
  `profile-editor-drawer`, `modules-panel`, `integrations-panel`, `audit-panel-section`,
  `user-editor-drawer`, `person-editor-drawer`, `admin-shared.ts` (tipos/constantes/helpers
  compartilhados). Menu lateral passou de 8 para 10 itens (Visão geral, Contas internas, Contas
  do Portal, Convites, Solicitações, Pessoas, Perfis, Módulos, Integrações, Auditoria) - "Gestão
  API/MCP" e a antiga aba "Parametrizações" saíram do menu, mas continuam 100% acessíveis (a
  primeira pelo card de atalho que já existia dentro de Integrações, a segunda incorporada à Visão
  geral). `"structure"` manteve o mesmo valor de aba de propósito - `frontend/app/gestao/page.tsx`
  linka `/admin?tab=structure&person=...` de fora deste arquivo.

  **Tela inicial (`workspace-login.tsx`, variant padrão usada por `/`)**: subtítulo trocado de
  "Use o mesmo usuário da Gamificação." para "Use seu usuário do UNI Workspace." (única menção a
  "Gamificação" na tela inicial - conferido não haver outra). Novo botão secundário "Acessar
  Portal do Colaborador" abaixo do "Entrar", visível só na tela inicial via prop `showPortalLink`
  (não aparece nos outros 9 logins de módulo que reaproveitam o mesmo componente).

  **Validado**: `npx tsc --noEmit`, `npm run build`, `npm run test -- --run` (45/45) - limpos.
  Validado ao vivo no navegador com admin QA temporário: os 10 itens do menu, os dois drawers
  (perfil, colaborador) e o atalho pra "Gestão API/MCP" conferidos um a um contra dados reais
  (usuários, perfis, módulos, convites e a única solicitação pendente real da época, todos exibidos
  corretamente, nenhum decidido/alterado); tela inicial conferida em mobile (375px) e desktop, com
  o botão novo levando a `/portal` corretamente.

  Rebuild de produção feito. Sem migration, sem alteração de backend, sem regra de negócio nova no
  frontend, sem dado real alterado.

  Arquivos: `frontend/app/admin/page.tsx`, `frontend/components/admin/admin-shared.ts` (novo),
  `admin-overview-panel.tsx` (novo), `accounts-table.tsx` (novo), `internal-accounts-panel.tsx`
  (novo), `portal-accounts-panel.tsx` (novo), `invites-panel.tsx` (novo),
  `access-requests-panel.tsx` (novo), `people-structure-panel.tsx` (novo), `profiles-panel.tsx`
  (novo), `profile-editor-drawer.tsx` (novo), `modules-panel.tsx` (novo),
  `integrations-panel.tsx` (novo), `audit-panel-section.tsx` (novo), `user-editor-drawer.tsx`
  (novo), `person-editor-drawer.tsx` (novo), `frontend/components/workspace/workspace-login.tsx`,
  `frontend/components/workspace/workspace-home.tsx`.

- **Fase 2D: correção de telefone no autoatendimento por CPF (backend + frontend, sem migration,
  ainda sem commit, sem push)**: pedido do usuário em 2026-08-29, logo depois da entrega anterior
  - se o colaborador não reconhecer o telefone que o IXC devolveu (cadastro desatualizado), ele
  precisa poder atualizar o número que fica salvo, não só recusar ou ser mandado falar com o
  gestor. **O nome continua intocável** (sempre do IXC, é a confirmação de identidade) - só o
  telefone ganhou essa flexibilidade, por pedido explícito.

  **Backend**: `submit_access_request` (`services/portal_access_requests.py`) agora dá
  PRIORIDADE ao telefone que o cliente manda explicitamente sobre o do IXC (antes, o IXC sempre
  vencia) - continua preferindo o do IXC quando o cliente não manda nada (fluxo normal de
  confirmação). Auditoria ganhou `phone_source` (`"ixc"` ou `"manual"`, nunca o número em si) pro
  admin saber, sem dado sensível, se o telefone da solicitação veio confirmado ou corrigido.

  **Frontend**: novo passo "Qual é o seu telefone atual?" em `access-request-form.tsx` - aparece
  quando a pessoa clica em "Não é o meu" na etapa de confirmação de telefone (antes só reiniciava
  o fluxo ou apontava pro gestor). O número digitado aí é o que vai no envio, com prioridade sobre
  o do IXC.

  **Testes**: `test_portal_access_requests.py` ganhou 3 casos novos (23 no total, era 20) -
  telefone do cliente vence o do IXC quando informado; telefone do IXC continua vencendo quando o
  cliente não informa nada; nome nunca muda mesmo quando o telefone é corrigido; auditoria grava
  `phone_source` corretamente nos dois casos.

  **Validado**: backend **839 passed, as mesmas 13 falhas pré-existentes do módulo AI**; `npx tsc
  --noEmit`, `npm run test -- --run` (45/45), `npm run build` - limpos. **Validado ao vivo, de
  ponta a ponta, contra a API real do IXC** (mesmo CPF de teste real das duas entregas
  anteriores): cliquei em "Não é o meu", digitei um telefone diferente do que o IXC tinha,
  completei o envio - **confirmado no banco que o nome salvo continuou vindo do IXC
  ("PAULO HENRIQUE ALVES PEIXOTO SOARES") e o telefone salvo foi exatamente o que digitei
  (`(69) 91234-5678`), não o do IXC**. Solicitação de teste apagada ao final - 0 linhas residuais.

  Rebuild de produção feito (`docker compose build backend frontend` + `up -d`). Sem migration.

  Arquivos: `backend/app/services/portal_access_requests.py`,
  `backend/tests/test_portal_access_requests.py`,
  `frontend/components/portal/access-request-form.tsx`. Sem commit, sem push, sem regra
  financeira alterada, sem migration, sem dado real alterado (linha de teste apagada).

- **Fase 2D redesenhada: autoatendimento por CPF na solicitação de acesso (backend + frontend,
  sem migration, ainda sem commit, sem push)**: pedido do usuário em 2026-08-29 pra que o próprio
  colaborador sem acesso digite o CPF, confirme o próprio nome, confirme o próprio telefone (os
  dois vindos do IXC, nunca digitados) e só então informe o e-mail - sempre digitado por quem
  solicita, nunca herdado do IXC, e restrito ao domínio corporativo `@souuni.com`.

  **Backend**: novo endpoint público `POST /access-requests/lookup-cpf` (rate limit próprio,
  10/15min por IP - mais sensível que o de envio, porque revela nome + telefone parcialmente
  mascarado pra qualquer CPF de dígito verificador válido, não só pra quem de fato é o dono) -
  novo `lookup_own_identity_by_cpf` em `services/ixc_collaborator_lookup.py`, reaproveita
  `_fetch_funcionarios_by_cpf` (mesma correção do formato mascarado da entrada anterior). Nunca
  devolve e-mail, `ixc_employee_id`, departamento, setor ou vínculo local - isso é informação só
  do admin (`/invites/lookup-ixc-cpf`, Fase 2C). Telefone mascarado parcialmente (DDD + últimos 4
  dígitos, ex. `(69) ****-8543`) - o suficiente pra a pessoa reconhecer "é o meu número" sem expor
  o telefone inteiro a quem só adivinhou um CPF válido.

  **`POST /access-requests` redesenhado**: `name`/`phone` agora são OPCIONAIS no schema - só
  usados como resguardo quando o CPF NÃO é encontrado no IXC (cadastro ainda não sincronizado,
  preserva a capacidade original do formulário manual). Quando o CPF É encontrado, o servidor
  **revalida contra o IXC de novo, na mesma chamada de envio, e usa esse nome/telefone como
  autoridade - nunca o que o cliente mandar** (mesmo princípio de "nunca confia no cliente pra
  dado que o servidor já pode verificar" já usado em `create_invite_from_ixc`, Fase 2C). `email`
  ganhou validação de domínio (`field_validator`, rejeita qualquer coisa que não termine em
  `@souuni.com`, com 422 e mensagem clara).

  **Frontend**: `components/portal/access-request-form.tsx` virou um assistente em etapas (CPF →
  confirma nome → confirma telefone → e-mail → enviado), com fallback pro formulário manual
  original quando o CPF não é encontrado no IXC - preserva essa capacidade, não regride.

  **Testes**: `backend/tests/test_portal_access_requests.py` reescrito (20 casos, era 13) -
  cobre a busca própria (achado/não achado/CPF inválido nunca consulta/auditoria mascarada), o
  envio ignorando nome/telefone forjados pelo cliente quando o IXC encontra, o fallback manual
  quando não encontra (com e sem dados preenchidos), e-mail fora do domínio corporativo rejeitado,
  e todos os casos antigos de sugestão/duplicação/aprovação/rejeição adaptados pro novo contrato.

  **Validado**: backend **836 passed, as mesmas 13 falhas pré-existentes do módulo AI**; `npx tsc
  --noEmit`, `npm run test -- --run` (45/45), `npm run build` - limpos. **Validado ao vivo, de
  ponta a ponta, contra a API real do IXC** (mesmo CPF de teste real da correção anterior): CPF →
  nome real apareceu pra confirmação → telefone mascarado apareceu pra confirmação → e-mail fora
  do domínio corporativo rejeitado no cliente (sem chamar o servidor) → e-mail corporativo aceito
  → solicitação enviada com sucesso, **confirmado no banco que nome e telefone gravados vieram do
  IXC** (não foram digitados em nenhuma etapa). Solicitação de teste apagada ao final (usava CPF
  de uma pessoa real só para validar o fluxo) - 0 linhas residuais. Auditoria confirmada sem CPF
  completo em nenhuma entrada, incluindo as do autoatendimento público.

  Rebuild de produção feito (`docker compose build backend frontend` + `up -d`). Sem migration
  (nenhuma coluna/tabela nova).

  Arquivos: `backend/app/schemas.py`, `backend/app/services/ixc_collaborator_lookup.py`,
  `backend/app/services/portal_access_requests.py`, `backend/app/api/routes/access_requests.py`,
  `backend/tests/test_portal_access_requests.py`, `frontend/lib/types.ts`, `frontend/lib/api.ts`,
  `frontend/components/portal/access-request-form.tsx`. Sem commit, sem push, sem regra
  financeira alterada, sem migration, sem dado real alterado (linha de teste apagada).

- **Correção: busca por CPF no IXC não achava funcionário que existia de verdade (backend, sem
  commit, sem push)**: o usuário reportou em 2026-08-29 que o CPF `70240110250` (dígito
  verificador válido) não era encontrado na busca por CPF/IXC recém-implementada. Investigado ao
  vivo, direto contra a API real (não só teste): **`funcionarios.cpf_cnpj` nesta instalação do
  IXC guarda o CPF COM MÁSCARA** (`702.401.102-50`), não só dígitos - confirmado consultando o
  campo com os dois formatos manualmente (mascarado achou 1 registro na hora; só dígitos, 0). A
  implementação original normalizava o CPF pra dígitos puros antes de consultar (seguindo a
  instrução literal do pedido original e o padrão do resto do projeto, onde `Collaborator.cpf`
  guarda só dígitos) - certo em geral, errado especificamente pra esse campo do IXC.

  **Corrigido em `services/ixc_collaborator_lookup.py`**: nova função `_fetch_funcionarios_by_cpf`
  tenta primeiro o formato mascarado (`format_cpf_with_mask`, novo em `services/documents.py`,
  reaproveitável por qualquer integração futura que precise do mesmo formato) - confirmado como o
  formato real desta instalação; só tenta dígitos puros depois, como resguardo pra um eventual
  registro legado gravado sem máscara, nunca o contrário (evita pagar uma segunda chamada no caso
  comum). **`OP: IN` com os dois formatos numa única chamada foi tentado e descartado** - o
  webservice desta instalação devolve uma página de erro (`RESPOSTA_INVALIDA`) pra `IN` com
  valores contendo pontuação, achado também ao vivo contra a API real.

  **Validado ao vivo, contra a API real, antes e depois da correção**: antes, `70240110250` → 404
  "não encontrado"; depois, mesmo CPF → encontra "Paulo Henrique Alves Peixoto Soares" (funcionário
  #378, ativo), na primeira tentativa (sem precisar do fallback). Testes novos em
  `test_ixc_collaborator_lookup.py` (+2, agora 18 no arquivo) fixam os dois casos - mascarado
  encontrado de primeira, e o fallback pra dígitos puros quando o mascarado não bate. Suíte
  completa: **829 passed, as mesmas 13 falhas pré-existentes do módulo AI** (nada novo quebrado).

  **Achado operacional**: os containers do projeto tinham caído (provavelmente reinício da
  máquina/Docker Desktop - `docker ps -a` mostrou os três com `Exited (137)`/`Exited (143)`,
  código de SIGKILL) - subidos de novo antes de investigar. Rebuild de produção feito depois da
  correção (`docker compose build backend` + `up -d`) - confirmado ao vivo contra a imagem nova
  que o CPF agora é encontrado. Sem migration (mudança é só na consulta ao IXC, nenhuma tabela
  nova).

  Arquivos: `backend/app/services/documents.py` (`format_cpf_with_mask`, novo),
  `backend/app/services/ixc_collaborator_lookup.py`,
  `backend/tests/test_ixc_collaborator_lookup.py`. Sem commit, sem push, sem regra financeira
  alterada, sem migration, sem dado real alterado.

- **Fase 2C estendida: convite inteligente por CPF integrado ao IXC (backend + frontend, sem
  migration, ainda sem commit, sem push)**: pedido do usuário em 2026-08-29 pra resolver o maior
  atrito do convite manual - o admin tinha que saber de cor o `collaborator_id` certo e digitar
  o e-mail à mão, sem nenhuma confirmação de que estava vinculando a pessoa certa. Contexto já
  validado pelo usuário antes de pedir a implementação: tabela `funcionarios` do IXC (~864
  registros) é a fonte correta de colaborador (RH/técnico de campo) - **nunca** `cliente`
  (assinante de contrato); filtro `funcionarios.cpf_cnpj = <CPF>` devolve exatamente 1
  funcionário; campos `id`, `funcionario`, `cpf_cnpj`, `email`, `fone_celular`, `ativo`,
  `id_departamento`, `id_setor_padrao` confirmados presentes.

  **Segurança crítica corrigida ANTES de usar a busca por CPF** (pré-requisito do próprio
  pedido): `IxcClient.list` (`services/ixc_client.py`) logava o valor bruto de qualquer filtro em
  nível INFO - inofensivo até então (só id/data/status já eram filtrados na integração
  existente), mas vira vazamento sério assim que uma busca por `funcionarios.cpf_cnpj` passa a
  existir. Corrigido pra mascarar CPF/CNPJ (reaproveita `mask_document` de
  `services/documents.py`, mesmo formato `***.***.***-NN`), e-mail (`fu***@dominio.com`) e
  telefone (`***NNNN`) antes de logar - **confirmado ao vivo, contra a API real do IXC**, não só
  em teste: o log mostrou `filtros=[funcionarios.cpf_cnpj = ***.***.***-35]`, nunca o CPF cru.
  Os logs úteis de tabela/página/rp/total/duração continuam intactos.

  **Backend**: novo service `services/ixc_collaborator_lookup.py` e dois endpoints em
  `api/routes/invites.py` (reaproveita o router da Fase 2C, não cria um módulo novo):
  - `POST /invites/lookup-ixc-cpf` (admin, `users:manage`) - CPF vai no CORPO, nunca em
    URL/query string; valida formato (`is_valid_cpf`, mesma função da Fase 1); consulta
    `funcionarios.cpf_cnpj = <CPF>`; devolve nome/e-mail/telefone/ativo/departamento/setor +
    `cpf_masked` (nunca o CPF completo); tenta correspondência local por `ixc_employee_id` → CPF
    → nome normalizado, nessa ordem de força - sempre uma SUGESTÃO, nunca vínculo automático
    (princípio da seção 2 do documento de planejamento). CPF não encontrado → 404 controlado;
    múltiplos resultados (nunca deveria acontecer, CPF é único) → 409, exige revisão manual;
    falha de rede do IXC → 502 controlado, sem stack trace.
  - `POST /invites/from-ixc` - **revalida o CPF contra o IXC de novo**, dentro da mesma chamada
    que cria o convite (nunca confia em dado ecoado de uma busca anterior vinda do cliente).
    `collaborator_id` é sempre exigido explicitamente no corpo, mesmo quando bate com a sugestão
    automática - nunca aceito por omissão. Enriquece o `Collaborator` (preenche
    `ixc_employee_id`/CPF/e-mail/telefone só quando estão VAZIOS - nunca sobrescreve valor já
    cadastrado; diverge do que já existe → bloqueia com 409, mesmo princípio "confirma, nunca
    sobrescreve" da Fase 1, estendido a `ixc_employee_id` porque esse campo também é usado pela
    Operação Analítica pra casar colaborador com técnico de O.S. - trocá-lo por engano
    reatribuiria esse histórico pra outra pessoa) e só então chama `create_invite` (Fase 2C
    original, sem duplicar a lógica de token/expiração). **Sem `Collaborator` local
    correspondente, o sistema NÃO cria um cadastro novo sozinho** - `role`/`regional` (campos
    obrigatórios do modelo) não vêm dessa busca, e inventar um placeholder poluiria uma entidade
    usada por outros módulos; a busca continua útil (mostra nome/e-mail), mas exige cadastro
    manual do colaborador antes de convidar.
  - Auditoria própria (`entity="ixc_collaborator"`) pra toda consulta - achada, não achada,
    ambígua ou erro - sempre com CPF mascarado, **commitada mesmo quando a consulta termina em
    erro** (a tentativa de consulta não pode se perder por causa de `get_db` não fazer rollback
    automático). Enriquecimento audita separado (`entity="collaborators"`,
    `action="collaborator.enriched_from_ixc"`), só quando algo de fato muda.

  **Frontend**: novo componente `components/admin/ixc-cpf-invite-panel.tsx` - card com header em
  gradiente (`uni-gradient`, mesma linguagem visual do login/portal), campo de CPF com máscara
  (reaproveita `formatCpf`/`isValidCpf` de `lib/masks.ts`, não duplicado), botão "Buscar no IXC"
  com loading, estado encontrado (nome, e-mail, telefone, CPF mascarado, badge ativo/inativo,
  alerta quando o colaborador sugerido já tem conta ou convite pendente - cruza com
  `peopleStructure`/`invites` que a página já carrega, sem endpoint novo só pra isso), estado não
  encontrado com orientação clara, estado de erro amigável. "Gerar convite" só habilita depois de
  escolher explicitamente o colaborador (pré-preenchido com a sugestão, mas sempre editável) e
  confirmar o e-mail. Sucesso reaproveita o mesmo banner "copie agora" já usado pra convite manual
  e senha temporária. Adicionado em `/admin`, acima do card de convite manual (que continua
  existindo, renomeado "Convite manual e histórico", pra quando o colaborador ainda não estiver
  no IXC).

  **Testes novos**: `backend/tests/test_ixc_collaborator_lookup.py` (11 casos) - CPF inválido
  nunca chega a consultar o IXC; usuário sem permissão não consulta (403); CPF não encontrado
  (404) e erro de API (502) controlados, sem stack trace, auditados com CPF mascarado; múltiplos
  resultados exigem revisão manual (409); CPF encontrado devolve dados seguros (CPF nunca
  completo na resposta nem na auditoria); sugestão por `ixc_employee_id` já vinculado; convite
  usa o `ixc_employee_id` corretamente e enriquece só os campos vazios; não duplica colaborador
  quando já existe (por CPF); bloqueia CPF conflitante (409) e `ixc_employee_id` conflitante
  (409), sem criar convite nesses casos. `backend/tests/test_ixc_client_log_masking.py` (5 casos)
  - CPF/CNPJ/e-mail/telefone nunca em claro no log; filtros não sensíveis (ids, datas, status) e
  os campos de tabela/página/rp/total/duração continuam aparecendo normalmente.

  **Validado**: backend **827 passed, as mesmas 13 falhas pré-existentes do módulo AI** (nada
  novo quebrado, os 16 testes novos incluídos no total); `npx tsc --noEmit`, `npm run test --
  run` (45/45), `npm run build` - limpos. **Sem infraestrutura de teste de componente React
  neste projeto** (sem `@testing-library/react`/jsdom) - a cobertura de máscara de CPF/loading/
  estados pedida no escopo foi feita por leitura cuidadosa do componente + validação ao vivo
  abaixo, não por teste automatizado de UI; registrado aqui como limitação real, não omitido em
  silêncio.

  **Validado ao vivo, contra a API real do IXC** (não só contra fake em teste): CPF de formato
  inválido bloqueado antes de qualquer chamada ao IXC; CPF de formato válido mas sem funcionário
  correspondente fez o round-trip completo contra o `funcionarios` real (206ms, confirmado no log
  mascarado) e mostrou o estado "não encontrado" corretamente na tela; máscara de CPF confirmada
  no campo do formulário. **O caminho "encontrado + gerar convite" não foi testado ao vivo contra
  um funcionário real** - de propósito: exigiria usar o CPF de uma pessoa real da empresa e criar
  um convite de verdade pra ela, uma ação com efeito real que não deveria ser disparada por mim
  sem uma pessoa específica autorizada; esse caminho está coberto pelos 11 testes automatizados
  (com IXC fake) e pela leitura cuidadosa do fluxo - fica como validação recomendada pro usuário
  fazer com um CPF real da própria escolha. Usuário admin QA temporário criado e apagado só pra
  esta validação, 0 linhas residuais.

  **Rebuild de produção feito** (`docker compose build backend frontend` + `up -d`) - sem
  migration nesta entrega (nenhuma tabela nova, só service/rotas/schemas novos e a correção de
  log), então não há achado de banco à frente do código desta vez.

  Arquivos: `backend/app/services/ixc_client.py` (mascaramento de log), `backend/app/schemas.py`,
  `backend/app/services/ixc_collaborator_lookup.py` (novo),
  `backend/app/api/routes/invites.py`, `backend/tests/test_ixc_collaborator_lookup.py` (novo),
  `backend/tests/test_ixc_client_log_masking.py` (novo), `frontend/lib/types.ts`,
  `frontend/lib/api.ts`, `frontend/components/admin/ixc-cpf-invite-panel.tsx` (novo),
  `frontend/app/admin/page.tsx`,
  [`docs/portal-ciclo-vida-conta-colaborador.md`](portal-ciclo-vida-conta-colaborador.md) (seção
  5.1 nova). Sem commit, sem push, sem regra financeira alterada, sem migration, sem dado real
  alterado além do enriquecimento opt-in que só acontece quando um admin confirma um convite
  (nenhum aconteceu nesta validação).

- **Correção: revogar convite e rejeitar solicitação de acesso não funcionavam de verdade
  (frontend, sem commit, sem push)**: o usuário reportou em 2026-08-29 que não conseguia deletar
  um convite nem recusar uma solicitação de acesso em `/admin` (Fase 2C/2D). Causa raiz encontrada
  ao reproduzir ao vivo: as duas ações (e mais quatro outras já existentes na mesma tela) dependiam
  de `window.confirm()`/`window.prompt()` nativos do navegador - `window.prompt()` chegou a lançar
  uma exceção não tratada (`prompt() is not supported.`) e `window.confirm()` podia ser
  silenciosamente ignorado, dependendo do contexto de navegador/ambiente (iframe, extensão,
  política de segurança) - a ação simplesmente não fazia nada, sem erro visível pro usuário.

  **Corrigido reaproveitando componentes já existentes no projeto** (não inventado do zero):
  `hooks/use-confirm.tsx` (`useConfirm`, já usado em `app/gamificacao/page.tsx`) substitui todo
  `window.confirm()` por um diálogo controlado (`components/ui/dialog.tsx`, Radix). Criado
  `hooks/use-prompt.tsx` (novo, mesmo padrão do `useConfirm`, mas devolve o texto digitado em vez
  de um booleano - não existia equivalente pra `window.prompt()` no projeto) pra substituir o
  `window.prompt()` do motivo de rejeição.

  **Seis ações corrigidas em `app/admin/page.tsx`** (todas usavam diálogo nativo, mesma causa
  raiz): revogar convite, rejeitar solicitação de acesso, aprovar solicitação de acesso, forçar
  troca de senha, forçar primeiro acesso completo, excluir usuário, excluir perfil de acesso -
  corrigidas juntas porque são o mesmo defeito, não seis defeitos separados (ver
  `manual_desenvolvimento_senior.md` seção 3.1, "não corrigir apenas o efeito visível quando há
  causa raiz identificável no mesmo escopo).

  **Validado**: `npx tsc --noEmit`, `npm run test -- --run` (45/45), `npm run build` - limpos.
  Confirmado ao vivo, sem nenhum stub/simulação (diferente da validação de fases anteriores, que
  precisava contornar a supressão de diálogo nativo do navegador de teste - aqui não há mais
  diálogo nativo nenhum): revogar convite abre o diálogo, mostra "Revogar o convite de
  [email]?", clique em "Revogar" chama a API de verdade (200) e atualiza a lista; rejeitar
  solicitação abre o diálogo com campo de texto, botão "Rejeitar" fica desabilitado até haver
  texto digitado, confirma e chama a API (200), toast "Solicitação rejeitada." aparece. Dados QA
  criados só para reproduzir e validar (1 admin, 1 colaborador, 2 convites, 1 solicitação) - todos
  apagados ao final, 0 linhas residuais. Confirmado que dados reais pré-existentes na mesma tela
  (um convite revogado e uma solicitação pendente de pessoas reais) permaneceram intocados durante
  toda a reprodução e correção.

  Arquivos: `frontend/hooks/use-prompt.tsx` (novo), `frontend/app/admin/page.tsx`. Sem commit, sem
  push, sem alteração de backend, sem migration, sem regra financeira, sem dado real alterado.

- **Fase 2D do Portal implementada: solicitação de acesso (backend + frontend + migration
  aplicada, ainda sem commit, sem push)**: pedido do usuário em 2026-08-28 para implementar a
  sub-fase 2D descrita em
  [`docs/portal-ciclo-vida-conta-colaborador.md`](portal-ciclo-vida-conta-colaborador.md) seção 6 -
  canal formal pra quem não tem conta nem convite pedir acesso, dependia da Fase 2C já existir
  (aprovar gera um convite, não duplica a criação de conta).

  **Modelo de dados**: `PortalAccessRequest` (tabela `portal_access_requests`, `models.py`) -
  exatamente o desenho da seção 8 do documento de planejamento. Migration
  `20260828_0083_portal_access_requests.py` (aditiva, só cria a tabela nova).

  **Backend**: novo router `api/routes/access_requests.py` (`/access-requests`), novo service
  `services/portal_access_requests.py`:
  - `POST /access-requests` (**pública, sem autenticação**) - nome/CPF/telefone/e-mail, mesma
    validação de CPF da Fase 1 (`is_valid_cpf`/`normalize_document`); tenta correspondência
    automática por CPF contra `Collaborator` (só SUGESTÃO, nunca vínculo - princípio de segurança
    da seção 2); dedup silenciosa contra solicitação pendente com o mesmo CPF (atualiza em vez de
    duplicar a fila); **resposta sempre genérica** (`{"received": true}`) - nunca revela se o
    CPF/e-mail já existe no sistema, nem se era um reenvio, seguindo a regra da seção 9 à risca.
    Rate limiting próprio (10/15min por IP, mesmo padrão de `/invites/accept`).
  - `GET /access-requests` (admin, `users:manage`) - lista com `cpf_masked` (nunca o CPF completo,
    nem pro admin).
  - `POST /access-requests/{id}/approve` (admin) - `collaborator_id` é **sempre exigido no corpo**,
    mesmo quando bate com `suggested_collaborator_id` - nunca aceito por omissão. Aprovar chama
    `create_invite` (reaproveita a Fase 2C direto, não duplica a criação de conta) e devolve o
    token do convite uma única vez, igual ao fluxo direto de convite.
  - `POST /access-requests/{id}/reject` (admin) - exige `decision_reason` não vazio.
  - Só solicitação `pending` pode ser decidida (409 em decisão duplicada).

  **Frontend**: seção "Solicitações de acesso" nova em `/admin` (aba Usuários, abaixo de
  Convites) - CPF mascarado, select de colaborador (pré-preenchido com a sugestão quando existe,
  mas sempre exigindo confirmação explícita pra aprovar), rejeitar pede motivo
  (`window.prompt`). Tela pública nova `/solicitar-acesso`
  (`components/portal/access-request-form.tsx`) - mesmo padrão visual das outras telas da Fase 2,
  reaproveita `formatCpf`/`formatPhone`/`isValidCpf` de `lib/masks.ts`; tela de sucesso sempre
  genérica, sem confirmar nem negar que os dados já existiam. `WorkspaceLogin.helperText` passou a
  aceitar `ReactNode` (era só `string`) para o Portal (`app/portal/page.tsx`) linkar
  "/solicitar-acesso" no lugar do texto estático anterior ("peça ao seu gestor") - só usuário desse
  prop antes, sem quebra.

  **Testes novos**: `backend/tests/test_portal_access_requests.py` (13 casos) - resposta pública
  sempre genérica; CPF inválido rejeitado (422); sugestão de colaborador por CPF (com e sem
  correspondência); reenvio com mesmo CPF atualiza em vez de duplicar; não-admin não lista nem
  decide (403); listagem sempre com CPF mascarado; aprovar gera convite com o `collaborator_id`
  exato informado (não o da sugestão, ainda que iguais); aprovar sem `collaborator_id` é rejeitado
  mesmo havendo sugestão (422); decisão duplicada é rejeitada (409) tanto para aprovar quanto para
  rejeitar; rejeitar exige motivo; auditoria nunca guarda CPF completo. Fixture de teste própria
  (`_reset_submit_rate_limit`) pra isolar o rate limiter entre testes - achado real: sem isso, o
  contador em memória (mesmo padrão do `/auth/login`) acumulava entre os 13 testes do arquivo e um
  no meio do caminho tomava 429 em vez do status esperado (só isolamento de teste, não muda o
  rate limiter de verdade).

  **Validado**: backend **811 passed, as mesmas 13 falhas pré-existentes do módulo AI** (nada novo
  quebrado); `npx tsc --noEmit`, `npm run test -- --run` (45/45), `npm run build` - limpos (rota
  `/solicitar-acesso` nova aparece no build). Fluxo completo validado ao vivo: solicitação enviada
  pelo navegador de verdade em `/solicitar-acesso` (tela de sucesso genérica confirmada); seção
  "Solicitações de acesso" em `/admin` conferida visualmente (CPF mascarado, select de colaborador,
  botões Aprovar/Rejeitar) - **decisão de aprovar/rejeitar feita por chamada direta de API, não
  clique na tela**, para não repetir o incidente da rodada anterior (a tabela de admin tem linhas
  de dados reais ao lado das de teste); aprovação gerou convite com o `collaborator_id` exato;
  rejeição registrou o motivo e bloqueou nova decisão (409). Confirmado que um convite PRÉ-EXISTENTE
  de uma pessoa real (não criado por mim) na mesma tela permaneceu intocado durante toda a
  validação. Todos os dados QA (2 solicitações, 1 convite gerado, 1 colaborador, 1 admin) apagados
  ao final, 0 linhas residuais.

  **Achado operacional (mesmo padrão das duas entregas anteriores, resolvido nesta rodada)**:
  alternar o backend pro modo dev pra rodar os testes aplicou a migration `20260828_0083`
  automaticamente ao Postgres real via entrypoint. Resolvido reconstruindo as duas imagens
  (`docker compose build backend frontend`) antes da validação ao vivo - confirmado `alembic
  current` = `head` = `20260828_0083`, rotas `/api/access-requests` respondendo, `/solicitar-acesso`
  respondendo 200, tabela `portal_access_requests` com **0 linhas** ao final. A imagem de produção
  agora reflete todo o código até a Fase 2D.

  Arquivos: `backend/app/models.py`, `backend/alembic/versions/20260828_0083_*.py` (novo, migration
  aplicada ao banco real), `backend/app/schemas.py`,
  `backend/app/services/portal_access_requests.py` (novo),
  `backend/app/api/routes/access_requests.py` (novo), `backend/app/main.py`,
  `backend/tests/test_portal_access_requests.py` (novo), `frontend/lib/types.ts`,
  `frontend/lib/api.ts`, `frontend/app/admin/page.tsx`, `frontend/app/portal/page.tsx`,
  `frontend/app/solicitar-acesso/page.tsx` (novo),
  `frontend/components/portal/access-request-form.tsx` (novo),
  `frontend/components/workspace/workspace-login.tsx`. Sem commit, sem push, sem regra financeira
  alterada, sem dado real alterado (tabela nova permanece vazia; o convite real pré-existente de
  outra pessoa foi conferido intocado).

  **Próxima sub-fase recomendada: 2E (esqueci minha senha)** - ver
  `docs/portal-ciclo-vida-conta-colaborador.md` seção 7. Reaproveita a mesma tabela
  `account_action_tokens` da Fase 2C (`purpose="password_reset"`) - antes dela, avaliar o risco já
  registrado de não existir infraestrutura de e-mail no projeto (seção 12): sem isso, o link de
  reset não tem como ser entregue automaticamente.

- **Fase 2C do Portal implementada: convite seguro com token (backend + frontend + migration
  aplicada, ainda sem commit, sem push)**: pedido do usuário em 2026-08-28 para implementar a
  sub-fase 2C descrita em
  [`docs/portal-ciclo-vida-conta-colaborador.md`](portal-ciclo-vida-conta-colaborador.md) seção 5 -
  primeira sub-fase da Fase 2 que precisa de tabela nova.

  **Modelo de dados**: `AccountActionToken` (tabela `account_action_tokens`, `models.py`) -
  compartilhada entre convite (`purpose="invite"`, implementado agora) e reset de senha por
  e-mail (`purpose="password_reset"`, Fase 2E futura), exatamente como o documento de
  planejamento (seção 8) desenhou, pra não duplicar o mecanismo de token depois. Migration
  `20260828_0082_account_action_tokens.py` (aditiva, só cria a tabela nova).

  **Backend**: novo router `api/routes/invites.py` (`/invites`), novo service
  `services/portal_invites.py`:
  - `POST /invites` (admin, `users:manage`) - cria convite com `email` + `collaborator_id`
    (obrigatório - é aqui que o vínculo é fixado, princípio de segurança da seção 2) + `role`
    (default `"collaborator"`); gera token com `secrets.token_urlsafe(32)`, guarda só o HASH
    (`hash_password`, mesmo algoritmo de `hash_api_key`); expira em 72h
    (`INVITE_EXPIRES_HOURS`); rejeita colaborador já vinculado, e-mail/CPF inválido e convite
    pendente duplicado (409).
  - `GET /invites` (admin) - lista convites; `status` exibido (`pending`/`accepted`/`revoked`/
    `expired`) é sempre CALCULADO na leitura para expiração (uma consulta GET nunca escreve no
    banco) - só criação/aceite/revogação mudam a coluna de verdade.
  - `POST /invites/{id}/revoke` (admin) - só convite `pending` pode ser revogado.
  - `GET /invites/accept?token=` e `POST /invites/accept` (**públicas, sem autenticação** - é
    assim que a conta nasce) - a primeira só confirma se o convite ainda vale (pra tela mostrar
    e-mail/colaborador antes do formulário); a segunda valida o token (hash, expiração, uso
    único), cria o `User` com `collaborator_id` EXATAMENTE igual ao do convite, senha escolhida
    pela própria pessoa (`must_change_password=False` - diferente de `create_user`, aqui não é
    senha temporária de admin) e devolve um token de acesso (mesmo formato do login) pra entrar
    direto no Portal. **Decisão registrada explicitamente, como o documento pedia**: o convite só
    resolve a senha inicial - `first_access_completed_at` continua `None` de propósito, então o
    onboarding da Fase 1 (CPF/telefone/e-mail) roda normalmente depois, sem duplicar essa coleta
    dentro do fluxo de convite. Rate limiting próprio em `/invites/accept` (10 tentativas/15min
    por IP, mesmo padrão de `/auth/login`, implementado à parte para não mexer no login por causa
    disso).

  **Frontend**: seção "Convites de colaborador" nova na tela `/admin` (aba Usuários, abaixo da
  tabela) - formulário (colaborador ainda sem usuário + e-mail) reaproveitando
  `peopleStructure.people` que a aba "Estrutura" já carrega (nenhum endpoint novo só pra listar
  colaborador); tabela de convites com badge de status e revogar; link de convite revelado uma
  vez no mesmo padrão "copie agora" já usado pra chave de API e senha temporária. Tela pública
  nova `/convite` (`app/convite/page.tsx` + `components/portal/invite-accept.tsx`) - mesmo
  padrão visual de `WorkspaceLogin`/`FirstAccessOnboarding` (painel azul responsivo, logo branca),
  valida o token, formulário de senha, ao concluir guarda o token de acesso e manda pro `/portal`
  (que já mostra o onboarding da Fase 1 sozinho).

  **Testes novos**: `backend/tests/test_portal_invites.py` (13 casos) - token nunca em claro no
  banco; não-admin não cria convite (403); colaborador inexistente (404) ou já vinculado (409);
  convite duplicado pendente (409); aceite cria a conta com o `collaborator_id` exato do convite e
  a senha escolhida pela própria pessoa; aceite ainda deixa o primeiro acesso pendente (confirma
  bloqueio real do portal); confirmação de senha divergente (422); token usado ou expirado não
  pode ser reaproveitado; listagem mostra "expirado" sem escrever isso no banco; revogar convite
  pendente e impedir reaceite; revogar duas vezes rejeita (409); auditoria nunca guarda token nem
  senha.

  **Validado**: backend **795 passed, as mesmas 13 falhas pré-existentes do módulo AI** (nada novo
  quebrado, os 13 testes novos incluídos); `npx tsc --noEmit`, `npm run test -- --run` (45/45),
  `npm run build` - limpos (rota `/convite` nova aparece no build). Fluxo completo validado ao vivo
  com admin e colaborador QA temporários: convite criado via API, tela `/convite` renderiza e
  valida o token corretamente, formulário de senha aceito pelo navegador de verdade → login
  automático → redirecionado ao `/portal` → onboarding da Fase 1 disparado (CPF/contato), exatamente
  como desenhado; conferido direto no banco que `collaborator_id`, senha e os dois campos da Fase 1
  ficaram certos. Todos os dados QA apagados ao final (usuário, colaborador, convite), 0 linhas
  residuais.

  **Achado operacional durante a validação (resolvido nesta mesma rodada)**: alternar o backend
  para o modo dev (bind mount, pra rodar os testes) faz o entrypoint rodar `alembic upgrade head`
  automaticamente contra o Postgres real - isso **aplicou a migration `20260828_0082` ao banco
  real** sem um comando explícito meu (mesmo mecanismo, não uma ação nova). Como é puramente
  aditiva (tabela nova, vazia, nenhuma coluna existente tocada), o risco é baixo, mas isso deixou a
  imagem de produção (código antigo, sem o router `/invites`) com o banco à frente do código -
  estado inconsistente. Resolvido reconstruindo as duas imagens (`docker compose build backend
  frontend`) e subindo de novo: confirmado `alembic current` = `head` = `20260828_0082`, rotas
  `/api/invites` respondendo, `/convite` respondendo 200, tabela `account_action_tokens` com
  **0 linhas** antes e depois de toda a validação (nenhum dado real tocado). Diferente das
  entregas anteriores desta sessão, **a imagem de produção agora reflete todo o código até a Fase
  2C**, não só até a Fase 1.

  **Achado real fora do escopo, sinalizado para tarefa separada (não corrigido aqui)**:
  `create_user`/`update_user` (`api/routes/users.py`) gravam `snapshot(item)` inteiro no
  `AuditLog.after_data`, o que inclui `password_hash` - diferente de todo o resto da Fase 2
  (2A/2B/2C), que sempre monta um before/after explícito sem senha. Sinalizado via tarefa em
  segundo plano, não alterado nesta entrega (fora do escopo da Fase 2C).

  Arquivos: `backend/app/models.py`, `backend/alembic/versions/20260828_0082_*.py` (novo, **migration
  aplicada ao banco real** - ver achado operacional acima), `backend/app/schemas.py`,
  `backend/app/services/portal_invites.py` (novo), `backend/app/api/routes/invites.py` (novo),
  `backend/app/main.py`, `backend/tests/test_portal_invites.py` (novo), `frontend/lib/types.ts`,
  `frontend/lib/api.ts`, `frontend/app/admin/page.tsx`, `frontend/app/convite/page.tsx` (novo),
  `frontend/components/portal/invite-accept.tsx` (novo). Sem commit, sem push, sem regra
  financeira alterada, sem dado real alterado (tabela nova permanece vazia).

  **Próxima sub-fase recomendada: 2D (solicitação de acesso)** - ver
  `docs/portal-ciclo-vida-conta-colaborador.md` seção 6. Depende desta 2C já existir (aprovar uma
  solicitação deve gerar um convite, não duplicar a criação de conta).

- **Fase 2B do Portal implementada: reset administrativo de senha e forçar primeiro acesso
  (backend + frontend, ainda sem commit, sem push)**: pedido do usuário em 2026-08-28 para
  implementar a sub-fase 2B descrita em
  [`docs/portal-ciclo-vida-conta-colaborador.md`](portal-ciclo-vida-conta-colaborador.md) seção 4 -
  duas ações administrativas distintas, resolvendo a pendência "painel admin pra resetar primeiro
  acesso" registrada várias vezes nas entradas anteriores deste log.

  **Backend**: dois endpoints novos em `api/routes/users.py`, ambos atrás de `users:manage` (mesma
  permissão de `create_user`/`update_user`):
  - `POST /users/{id}/force-password-reset` - gera uma senha temporária aleatória
    (`generate_temporary_password`, novo em `core/security.py`, usa `secrets.choice` sobre um
    alfabeto sem caracteres ambíguos como `0/O/1/l/I` - é lida e digitada por uma pessoa, diferente
    de `secrets.token_urlsafe` já usado pra chave de API), grava o hash, força
    `must_change_password=True` e **retorna a senha temporária em texto puro só nesta resposta,
    uma única vez** - nunca fica em log nem em auditoria. **Não mexe em
    `first_access_completed_at`** - só reseta a senha, de propósito, ação distinta da outra.
  - `POST /users/{id}/force-first-access` - zera `first_access_completed_at` **e** força
    `must_change_password=True` juntos (mesmo estado "pendente" de um colaborador recém-criado em
    `create_user`) - reabre CPF/telefone/e-mail, não só a senha. Rejeita (422) usuário sem
    `collaborator_id` - primeiro acesso não existe pra quem não representa um colaborador.
  - Lógica em `services/account_security.py` (`admin_force_password_reset`,
    `admin_force_first_access`), reaproveitando 100% o gate já existente da Fase 1
    (`require_portal_access`/`portal_first_access_pending`) - nenhuma lógica de bloqueio nova.
    Auditoria (`action="user.password_reset_forced"` / `"user.first_access_reset"`) sem a senha
    temporária em nenhuma forma. Schema `AdminForcePasswordResetOut` (`schemas.py`).

  **Frontend**: dois botões novos na tabela de usuários já existente em `/admin`
  (`app/admin/page.tsx`) - ícone `KeyRound` ("Forçar troca de senha", todo usuário) e `RotateCcw`
  ("Forçar primeiro acesso completo", só quando `collaborator_id` existe), ambos atrás de
  `canWriteUsers`, com confirmação antes de agir. A senha temporária gerada aparece num banner
  âmbar "Copie agora - não será mostrada de novo" - reaproveita **literalmente o mesmo padrão
  visual** já usado em `components/admin/ai-governance-panel.tsx` pra revelar uma chave de API
  nova, em vez de inventar um componente novo. `api.forcePasswordReset`/`api.forceFirstAccessReset`
  novos em `lib/api.ts`.

  **Testes novos**: `backend/tests/test_admin_account_reset.py` (8 casos) - senha temporária
  funciona de verdade e bloqueia o portal até trocar; `first_access_completed_at` não é tocado
  pelo reset de senha; primeiro acesso reaberto não toca na senha atual; rejeita usuário sem
  `collaborator_id`; ambos os endpoints exigem `users:manage` (403 sem a permissão); 404 pra
  usuário inexistente; auditoria nunca guarda a senha temporária.

  **Validado**: backend **782 passed, as mesmas 13 falhas pré-existentes do módulo AI** (nada novo
  quebrado, os 8 testes novos incluídos); `npx tsc --noEmit`, `npm run test -- --run` (45/45),
  `npm run build` - limpos.

  **Achado real durante a validação no navegador (corrigido na hora)**: um clique de teste
  (coordenada de tela, não por seletor) acabou acertando, por engano, o botão de "forçar primeiro
  acesso" de um **colaborador real** (`WILKER MENEZES DE OLIVEIRA`, `users.id=66`) em vez da conta
  QA - a tabela de usuários reflow/reordenou entre uma ação e outra. Detectado imediatamente ao
  conferir o `AuditLog` (entrada `user.first_access_reset` com o autor sendo o admin QA temporário)
  e **revertido na hora, direto no banco, para o estado exato anterior** (`must_change_password` e
  `first_access_completed_at` restaurados com o mesmo timestamp que o próprio audit log
  registrava) - confirmado depois que o colaborador real ficou exatamente como estava antes,
  0 dado real alterado ao final. A partir daí, a validação do segundo endpoint passou a ser feita
  por chamada HTTP direta (mesmo JWT do admin QA, sem clique de UI) para eliminar esse risco -
  confirmado que `force-first-access` bloqueia o portal (`403 Conclua seu primeiro acesso`) e que
  `force-password-reset` gera uma senha que realmente autentica. Usuários e colaborador QA temporários
  apagados ao final, 0 linhas residuais (além da conta real já restaurada).

  **Achado operacional**: como nas entregas anteriores, a imagem de produção rodando agora **não
  contém** este código (só validado em modo dev) - precisa de rebuild antes de ir para produção.

  Arquivos: `backend/app/core/security.py`, `backend/app/schemas.py`,
  `backend/app/services/account_security.py`, `backend/app/api/routes/users.py`,
  `backend/tests/test_admin_account_reset.py` (novo), `frontend/lib/types.ts`, `frontend/lib/api.ts`,
  `frontend/app/admin/page.tsx`. Sem commit, sem push, sem migration, sem regra financeira alterada,
  sem dado real alterado ao final (o toque acidental foi revertido na mesma sessão).

  **Próxima sub-fase recomendada: 2C (convite seguro com token)** - ver
  `docs/portal-ciclo-vida-conta-colaborador.md` seção 5. Antes dela, avaliar o risco já registrado
  de não existir infraestrutura de e-mail no projeto (seção 12).

- **Fase 2A do Portal implementada: troca de senha pelo próprio usuário (backend + frontend,
  ainda sem commit, sem push)**: pedido do usuário em 2026-08-28 para implementar a sub-fase 2A
  descrita em [`docs/portal-ciclo-vida-conta-colaborador.md`](portal-ciclo-vida-conta-colaborador.md)
  seção 3 - primeira sub-fase da Fase 2, a de menor risco, sem tabela nova.

  **Backend**: `POST /auth/change-password` (novo, `api/routes/auth.py`) - só exige autenticação
  (`get_current_user`), sem `require_portal_access` nem permissão de módulo, porque vale pra
  qualquer usuário do ecossistema (admin, operador, colaborador...), não só quem tem
  `collaborator_id`. Lógica em `services/account_security.py` (novo,
  `change_own_password`): confirma a senha atual (`verify_password`), exige nova senha ≠
  confirmação, exige nova senha ≠ senha atual, grava `password_hash`/`password_changed_at` - **não
  mexe em `must_change_password` nem `first_access_completed_at`** (troca voluntária não é
  primeiro acesso, ao contrário da Fase 1). Schema `ChangePasswordRequest` (`schemas.py`) reaproveita
  a mesma política mínima de 8 caracteres da Fase 1. Auditoria via `record_audit_log`
  (`action="change_own_password"`) sem a senha em nenhuma forma, nem hash.

  **Frontend**: nova seção "Trocar senha" dentro de `ProfileSettings`
  (`components/portal/profile-settings.tsx`), a tela "Perfil" que já existia no Portal - card
  próprio com senha atual/nova/confirmação, mostrar/ocultar senha, campos limpos após sucesso.
  `api.changePassword` novo em `lib/api.ts`.

  **Testes novos**: `backend/tests/test_change_password.py` (7 casos) - sucesso mantém
  `must_change_password`/`first_access_completed_at` intocados; senha atual errada (401);
  confirmação divergente (422); nova igual à atual (422); senha fraca (422); usuário interno sem
  `collaborator_id` também consegue trocar (a 2A não é exclusiva do Portal); auditoria sem senha em
  nenhuma forma.

  **Validado**: backend **774 passed, as mesmas 13 falhas pré-existentes do módulo AI** (nada novo
  quebrado, os 7 testes novos incluídos no total); `npx tsc --noEmit`, `npm run test -- --run`
  (45/45), `npm run build` - limpos. Navegador (modo dev temporário, revertido pro modo produção ao
  final), com usuário e colaborador QA temporários (senha conhecida só para o teste, apagados ao
  final, 0 linhas residuais): senha atual incorreta → "Senha atual incorreta." sem alterar nada;
  fluxo correto → sucesso, campos limpos; confirmado direto no banco que a senha nova passou a
  validar e a antiga não, e que `must_change_password`/`first_access_completed_at` continuam
  exatamente como estavam antes da troca.

  **Achado operacional**: como nas entregas anteriores desta sessão, a imagem de produção rodando
  agora **não contém** este código (só foi validado em modo dev, com bind mount) - precisa de
  rebuild (`docker compose build backend frontend`) antes de ir para produção de fato.

  Arquivos: `backend/app/schemas.py`, `backend/app/api/routes/auth.py`,
  `backend/app/services/account_security.py` (novo), `backend/tests/test_change_password.py`
  (novo), `frontend/lib/api.ts`, `frontend/components/portal/profile-settings.tsx`. Sem commit,
  sem push, sem migration (reaproveita colunas da Fase 1), sem dado real alterado.

  **Próxima sub-fase recomendada: 2B (reset administrativo e forçar primeiro acesso)** - ver
  `docs/portal-ciclo-vida-conta-colaborador.md` seção 4.

- **Fase 2 do Portal estruturada em documento próprio (só documentação, sem commit, sem
  push)**: pedido do usuário em 2026-08-28 para documentar o ciclo de vida da conta do
  colaborador depois do primeiro acesso obrigatório (Fase 1) - a pendência que já
  aparecia registrada duas vezes nesta mesma entrada de log ("painel admin pra
  acompanhar e resetar primeiro acesso") agora tem plano detalhado.

  Novo documento: [`docs/portal-ciclo-vida-conta-colaborador.md`](portal-ciclo-vida-conta-colaborador.md)
  - princípio de segurança (colaborador troca a própria senha e completa o próprio
    cadastro, mas nunca escolhe o próprio `collaborator_id` - esse vínculo só nasce de
    admin, convite ou aprovação de solicitação);
  - cinco sub-fases: **2A** troca de senha pelo próprio usuário, **2B** reset
    administrativo e forçar primeiro acesso, **2C** convite seguro com token, **2D**
    solicitação de acesso, **2E** esqueci minha senha;
  - modelo de dados sugerido (`account_action_tokens` compartilhada entre convite e
    reset de senha, `portal_access_requests` para a fila de solicitação);
  - regras de segurança, ordem recomendada de implementação, critérios de aceite por
    fase e riscos com mitigação - incluindo o risco real já identificado de **não
    existir nenhuma infraestrutura de envio de e-mail no projeto hoje**, o que bloqueia
    a entrega automática de convite (2C) e reset de senha (2E) até existir um serviço
    mínimo de envio.

  **Próxima implementação recomendada: Fase 2A (troca de senha pelo próprio
  usuário)** - menor risco, nenhuma tabela nova, reaproveita 100% do que a Fase 1 já
  criou (`verify_password`, `hash_password`, `password_changed_at`).

  Também atualizado: [`docs/00-TRILHA-0.md`](00-TRILHA-0.md) (novo documento adicionado
  ao índice comentado).

  **Nenhum código, migration, dado real, commit ou push nesta entrega** - só os três
  arquivos de documentação citados.

- **Card azul (painel de marca) também no mobile do login/onboarding do Portal (sem commit, sem
  push)**: pedido do usuário em 2026-08-28, logo depois da troca de logo pra branca: no mobile, o
  painel `uni-gradient` era `hidden md:flex` - sumia por completo, sobrava só a logo colorida
  pequena e o formulário branco puro, sem o mesmo acabamento do desktop. Trocado pra aparecer em
  toda largura de tela: como o container pai já usa `md:grid-cols-[1fr_1.1fr]` (1 coluna abaixo de
  `md`), bastou tirar o `hidden` do painel gradiente pra ele empilhar sozinho acima do formulário no
  mobile, sem precisar duplicar nenhum bloco de markup.

  **O que aparece no card azul do mobile**: logo branca, selo (ex. "Portal do Colaborador"), título
  e subtítulo - mesmo conteúdo do desktop. **O que fica só a partir de `md`**: a lista de destaques
  (`highlights`) e o rodapé "UNI Internet · Ecossistema operacional", pra não empurrar os campos de
  e-mail/senha pra fora da primeira tela num celular. Como consequência, o bloco de
  título/subtítulo que existia duplicado dentro do formulário (visível em toda largura antes) agora
  só aparece a partir de `md` - no mobile, ele ficaria colado embaixo do título que o card azul já
  mostra, uma repetição sem função; o mesmo vale pro `<img>` de logo colorida que ficava solto no
  topo do formulário no mobile - removido, porque a logo branca do card azul já cumre esse papel.
  Afeta `frontend/components/workspace/workspace-login.tsx` (todos os 9 logins de módulo, já que é
  o componente compartilhado) e `frontend/components/portal/first-access-onboarding.tsx`.

  **Validações executadas**: `npx tsc --noEmit`, `npm run test -- --run` (45/45), `npm run build` -
  limpos. Navegador em 375px (modo dev temporário, revertido pro modo produção ao final): `/suporte`
  e `/portal` deslogados com card azul completo no topo (logo, selo, título, subtítulo), formulário
  branco embaixo, sem overflow horizontal (`scrollWidth === clientWidth`); onboarding de primeiro
  acesso também com card azul no mobile, validado com usuário+colaborador QA temporários
  (`must_change_password=true`, apagados ao final, 0 linhas residuais); desktop conferido sem
  regressão (lista de destaques e título duplicado no formulário continuam só a partir de `md`,
  como já era); console sem erro novo.

  **Sem push, sem alteração de backend, sem migration, sem regra financeira, sem dado real tocado.**

- **Logo branca no painel escuro do login/onboarding do Portal (sem commit, sem push)**: pedido do
  usuário em 2026-08-28 pra trocar a logo colorida por uma versão branca nas áreas escuras/gradiente
  do login e do onboarding de primeiro acesso, melhorando contraste. Puramente visual/asset - nenhum
  fluxo de login, CPF, senha, permissão, regra financeira ou dado real foi tocado; nenhum arquivo de
  backend foi aberto para edição nesta rodada.

  **Asset**: `frontend/public/brand/uni-logo-white.png` (novo arquivo, 804×535, mesma arte-base da
  logo colorida existente, PNG com canal alpha real). Validado visualmente antes de usar: dimensão
  natural igual à logo colorida; transparência real confirmada (mapa de alpha gerado via
  PowerShell/`System.Drawing`, já que o host Windows não tem Python instalado); composição sobre um
  fundo azul sólido aproximando `--uni-midnight` mostrou a marca "uni Internet" nítida, sem
  artefatos. A varredura de bounding box (alpha>10 e alpha>128) já mostrava a arte ocupando quase
  todo o canvas 804×535 - **sem espaço vazio sobrando pra recortar**, então o arquivo foi usado como
  veio, sem crop.

  **Onde foi usada**: só no `<img>` do painel gradiente (`uni-gradient`, fundo escuro) de
  `frontend/components/workspace/workspace-login.tsx` e
  `frontend/components/portal/first-access-onboarding.tsx` - `object-contain` adicionado (faltava),
  `self-start` mantido (evita o bug antigo de esticar a logo, já documentado nesses arquivos),
  `h-9 w-auto` mantido (mesma proporção 804:535, sem distorção). Como `WorkspaceLogin` é o
  componente compartilhado por **todos os 9 logins** de módulo (Suporte, Gestão, Operação etc.), a
  troca vale pra todos eles no painel escuro - validado ao vivo que `/suporte` continua correto. O
  `<img>` do painel branco/mobile (`md:hidden`) **continua com a logo colorida** em ambos os
  arquivos, como pedido - nenhuma mudança de espaçamento foi necessária (badge/título/subtítulo
  intactos), porque a nova logo tem exatamente a mesma proporção natural da colorida.

  **Validações executadas**: `npx tsc --noEmit`, `npm run test -- --run` (45/45), `npm run build` -
  todos limpos. Navegador, modo dev temporário (`docker compose -f docker-compose.yml -f
  docker-compose.dev.yml up -d`, revertido pro modo produção ao final): `/portal` deslogado com logo
  branca nítida sobre o gradiente, proporção 804:535 preservada no render (`naturalWidth/Height` vs.
  `getBoundingClientRect` conferidos via JS); `/suporte` (logo compartilhada) sem quebra; onboarding
  de primeiro acesso validado com usuário e colaborador QA temporários (`must_change_password=true`,
  criados e apagados só pra este teste, nenhuma senha real usada, 0 linhas residuais confirmadas
  depois) - logo branca renderiza igual no painel do onboarding; mobile 375px sem overflow
  horizontal (`scrollWidth === clientWidth`); console sem erro novo (só os 401/403 esperados de
  fluxo deslogado/pendente, já existentes antes desta mudança).

  **Sem push, sem alteração de backend, sem migration, sem regra financeira, sem dado real tocado.**
  `git status --branch` confirma o branch local sem `[ahead]` do remoto - nada commitado nesta
  rodada.

- **Checkpoint seguro do Portal/primeiro acesso: risco de imagem de produção divergente
  RESOLVIDO (sem commit, sem push)**: pedido do usuário em 2026-08-28 pra revalidar o estado real
  e preparar o ambiente pra não quebrar por divergência entre banco e imagem. Nenhuma feature nova,
  nenhuma regra de negócio alterada - só checkpoint e operação.

  **Estado real revalidado, idêntico ao das duas entradas anteriores**: `alembic current` e
  `alembic heads` == `20260828_0081 (head)` (cadeia linear, sem branching); as 3 colunas
  (`must_change_password`, `first_access_completed_at`, `password_changed_at`) confirmadas em
  `users` no Postgres real; **13 usuários, 0 pendentes, 0 forçados** - backfill continua íntegro,
  nada mudou desde a aplicação da migration.

  **Rebuild de produção FEITO nesta rodada** (`docker compose build backend` +
  `docker compose build frontend`, depois `docker compose up -d backend frontend`) - resolve
  definitivamente o aviso operacional registrado nas duas entradas anteriores. Confirmado ao vivo:
  o entrypoint rodou `alembic upgrade head` **sem erro** (a imagem agora contém o arquivo da
  migration `0081`, então reconcilia com o banco - que já estava em `head` - em vez de falhar com
  `Can't locate revision`); container subiu saudável, sem bind mount de dev, `uvicorn` rodando sem
  `--reload` (modo produção real, não dev); `GET /portal` → 200; `GET /api/auth/me` e
  `GET /api/portal/summary` → 401 sem token (correto) e 200 com token de usuário real autenticado,
  `portal_first_access_required:false` confirmado pra usuário já onboardado.
  **O risco de "subir a imagem antiga e falhar" não existe mais** - a imagem rodando agora é a
  mesma que subiria em um restart/deploy real.

  **Validações executadas**: backend (`test_portal_first_access.py` + `test_portal_profile.py` +
  `test_portal_dashboard.py` + `test_portal_run_selection.py` + `test_portal_team_summary.py`) -
  **48/48 passed**; `npx tsc --noEmit`, `npm run test -- --run` (45/45), `npm run build` - limpos.
  Navegador, **contra a imagem de produção recém-reconstruída** (não mais modo dev), com usuário e
  colaborador de teste criados e apagados só para a validação (nenhum dado real tocado): deslogado
  com logo nítido; senha errada → "Email ou senha inválidos."; login válido sem pendência → entra
  direto no portal; mesmo usuário revertido pra pendente → onboarding aparece; onboarding
  concluído numa aba nova (sem nenhuma ação de teste anterior) → CPF/telefone/e-mail salvos
  corretamente, **console sem nenhum erro**; mobile 375px sem overflow horizontal
  (`scrollWidth === clientWidth`).

  **Estado final dos containers**: `opr-gamification-backend` e `opr-gamification-frontend`
  saudáveis, rodando as imagens reconstruídas nesta rodada (modo produção, sem bind mount);
  `opr-gamification-db` saudável, inalterado.

  **Sem push.** `git status --branch` confirma o branch local no mesmo commit do remoto
  (`origin/claude/suporte-sync-backfill-madrugada`, sem `[ahead]`) - tudo que existe desde a
  Fase 1 até este checkpoint está só no working tree, não commitado.

  **Sugestão de commits para quando houver autorização** (não executado): ver seção própria
  abaixo, "Commits sugeridos (checkpoint 2026-08-28)".

  **Pendência real declarada (Fase 2, fora do escopo)**: painel admin pra acompanhar e resetar
  primeiro acesso - hoje só existe o campo `must_change_password` no banco, sem tela.

- **Rodada final de validação e refinamento visual do login/onboarding do Portal (só frontend,
  sem commit)**: pedido do usuário em 2026-08-28 depois da Fase 1 já estar com a migration
  aplicada - confirmar o estado real do ambiente e polir o visual, sem mudar regra de negócio.
  **Nenhuma linha de backend foi tocada nesta rodada** - não apareceu bug bloqueante causado pela
  Fase 1 (a única condição que autorizaria mexer lá).

  **Estado real confirmado**: `alembic current` → `20260828_0081 (head)`; as 3 colunas
  (`must_change_password`, `first_access_completed_at`, `password_changed_at`) existem em `users`
  no Postgres real; **13 usuários, 0 pendentes** (backfill continua íntegro); containers
  `opr-gamification-backend`/`frontend` saudáveis, rodando em modo dev (`docker-compose.dev.yml`)
  pelo motivo já registrado na entrada anterior.

  **Bug real encontrado e corrigido - o logo "grande/borrado/esticado" que o usuário reportou**:
  não era resolução de imagem, era CSS. `<img className="h-10 w-auto">` dentro de um container
  `flex-col` sem `align-items` explícito herda `stretch` (o padrão do flexbox) - o navegador
  ignorava a proporção natural da imagem (804×535) e forçava o elemento a ocupar 100% da largura
  do painel, medido ao vivo em **367×40px** (proporção ~9:1) onde deveria ser ~60×40px (proporção
  ~1,5:1, a da imagem original). Corrigido com `self-start` nos dois componentes
  (`workspace-login.tsx`, `first-access-onboarding.tsx`) - o logo agora renderiza nítido, na
  proporção certa, em qualquer um dos 9 lugares que usam `WorkspaceLogin`.

  **Outros refinamentos visuais** (`WorkspaceLogin` e `FirstAccessOnboarding`, mesma linguagem
  visual nos dois):
  - proporção do grid ajustada de `1fr/1fr` pra `1fr/1.1fr` - formulário ganha um pouco mais de
    espaço, painel de marca fica menos "genérico 50/50";
  - **novo achado durante a validação visual**: ao adicionar a lista de destaques, o
    `justify-between` do painel zerou o espaço entre o último item e o rodapé (`gap` medido em
    **0px** via DOM) - o conteúdo do meio cresceu e passou a ocupar 100% do espaço que o
    `justify-between` tinha pra distribuir. Trocado por um espaçador flexível
    (`<div className="flex-1" />`) + margem mínima garantida (`mt-8`) no rodapé, que não colapsa
    mesmo sem espaço sobrando - confirmado depois em 32px de gap real;
  - foco ciano (`--ring`, token global usado em todo o app) suavizado só nestas duas telas pra
    `#2d5fff` (`--uni-royal`, a cor primária do produto) via `focus-visible:ring-[#2d5fff]` local -
    **o token global não foi alterado**, então nenhuma outra tela do sistema muda de comportamento;
  - hierarquia de texto reforçada (`tracking-tight` nos títulos, `leading-relaxed` na descrição);
  - **elementos úteis, não decorativos, adicionados só na variante `portal`** (`WorkspaceLogin`
    ganhou um campo `highlights` por variante - vazio pro `workspace` genérico, preenchido só pro
    portal, pra não impor copy específica do Portal nos outros 8 logins que usam o mesmo
    componente): "Acesso seguro e individual", "Só os seus próprios dados", "Pontuação, O.S. e
    fechamento", "Mesmo login do ecossistema UNI". No onboarding: "CPF só confirma quem é você",
    "Nunca exibido por completo depois", "Senha nova, só sua, a partir de agora";
  - reforço textual de que o CPF é confirmação cadastral: texto de ajuda dinâmico abaixo do campo
    - "É só uma confirmação de identidade - o CPF já cadastrado não muda" quando já existe CPF, ou
    a explicação de privacidade quando ainda não existe. CPF continua sempre mascarado
    (`***.***.***-XX`) quando já cadastrado, nunca completo em tela nenhuma - comportamento da
    Fase 1, não tocado.

  **Validado ao vivo, com usuário e colaborador de teste criados e apagados só para a validação
  (nenhum dado real tocado)**: `/portal` deslogado → visual novo confirmado; senha errada → "Email
  ou senha inválidos." com o mesmo visual; login válido com primeiro acesso pendente → onboarding
  com logo nítido, CPF já cadastrado mostrando "Confirme seu CPF (cadastrado como ***.***.***-25)"
  e o texto de reforço certo; máscaras de CPF e telefone testadas digitando de verdade
  (`529.982.247-25`, `(69) 99999-0000`); conclusão → CPF confirmado sem sobrescrever, telefone e
  e-mail salvos, `AuditLog` conferido no banco sem CPF completo nem senha; mobile 375px sem
  overflow horizontal (`scrollWidth === clientWidth`); console **sem nenhum erro** numa aba nova
  que só passou pelo fluxo válido (os 401 vistos em abas anteriores eram os testes deliberados de
  senha errada, não erro novo). `/suporte` (variante `workspace`, sem lista de destaques)
  conferido sem regressão - mesma copy de sempre, só o logo e a proporção mudaram.

  **Validações executadas**: `npx tsc --noEmit`, `npm run test -- --run` (45/45), `npm run build` -
  limpos. Backend: `test_portal_first_access.py` + `test_portal_profile.py` +
  `test_portal_dashboard.py` + `test_portal_run_selection.py` + `test_portal_team_summary.py` -
  **48/48 passed**, sem precisar de mudança de banco (nenhum arquivo de backend foi alterado nesta
  rodada).

  **Aviso operacional (repetido da entrada anterior, continua valendo)**: a imagem de produção
  atual (última reconstruída, antes da Fase 1) não contém o arquivo da migration `20260828_0081` -
  o Postgres real já está na revisão `head`, então **subir essa imagem antiga vai falhar**
  (`Can't locate revision identified by '20260828_0081'`, confirmado ao vivo). Antes de qualquer
  restart ou deploy em produção, é obrigatório reconstruir a imagem com o código atual (`docker
  compose build backend`). Isso não foi feito nesta rodada porque não foi pedido.

  **Pendência real declarada (Fase 2, fora do escopo)**: painel admin pra acompanhar e resetar
  primeiro acesso - hoje só existe o campo `must_change_password` no banco, sem tela.

  Arquivos: `frontend/components/workspace/workspace-login.tsx`,
  `frontend/components/portal/first-access-onboarding.tsx`. Nenhum arquivo de backend, migration
  ou dado real alterado. Sem commit, sem push.

- **Fase 1 do primeiro acesso obrigatório do colaborador no Portal (backend + frontend, ainda sem
  commit; migration aplicada - ver o parágrafo "Migration aplicada" mais abaixo nesta mesma
  entrada, e a entrada mais recente acima para a rodada de validação/refinamento visual)**: pedido
  do usuário em 2026-08-28 para forçar CPF/telefone/e-mail + troca de senha no primeiro acesso,
  antes de ver ranking, O.S., auditoria ou qualquer dado financeiro/operacional individual.

  **Campos novos em `users`** (migration `20260828_0081_users_first_access.py`): `must_change_password` (bool, default false), `first_access_completed_at` (datetime
  nullable - `NULL` é o sinal canônico de "nunca completou"), `password_changed_at` (datetime
  nullable, informativo). **A migration faz backfill de `first_access_completed_at = created_at`
  para toda linha já existente** - sem isso, todo colaborador que já usa o portal hoje seria
  bloqueado retroativamente na primeira requisição depois do deploy. Só usuário **novo** criado com
  `collaborator_id` (`create_user`, api/routes/users.py) nasce com `must_change_password=true`.

  **Bloqueio real no backend**: `require_portal_access` (core/security.py), um wrapper de
  `require_permission` trocado 1:1 em toda rota de `portal.py` (nunca espalhado rota por rota, pra
  não ter como esquecer uma) - se `user.collaborator_id` existe e (`must_change_password` OU
  `first_access_completed_at is None`), devolve 403 com mensagem amigável. Usuário interno
  (admin/operator/viewer sem `collaborator_id`) nunca é afetado. As duas rotas de onboarding (`GET
  /portal/first-access/status`, `POST /portal/first-access/complete`) usam só `get_current_user` -
  gatear elas também criaria um círculo sem saída.

  **CPF**: `backend/app/services/documents.py` (novo) centraliza `normalize_document`,
  `mask_document` (nunca CPF completo pro frontend) e `is_valid_cpf` (dígito verificador módulo
  11, que não existia em lugar nenhum do projeto antes). `_mask_document`/`_normalize_document` de
  `modules/admin/router.py` foram promovidas pra lá em vez de duplicadas - o admin agora importa
  do mesmo lugar. Se o colaborador já tem CPF cadastrado, o primeiro acesso CONFIRMA (precisa
  bater) e nunca sobrescreve; se não tem, o primeiro acesso é quem grava.

  **Senha**: não existia política de senha no projeto - mínimo de 8 caracteres introduzido
  especificamente para esta troca (decisão nova, registrada como tal, não "política existente"
  reaproveitada).

  **Auditoria**: `complete_first_access` grava em `AuditLog` sem CPF completo (só mascarado) e sem
  senha em nenhuma forma (nem hash, nem indicação de tamanho) - testado explicitamente
  (`test_audit_log_never_stores_full_cpf_or_password`).

  **Frontend**: `FirstAccessOnboarding` (novo, `components/portal/first-access-onboarding.tsx`) -
  mesma linguagem visual do `WorkspaceLogin` modernizado (painel `.uni-gradient` + formulário),
  três seções (Identificação/Contato/Nova senha), máscara de CPF e telefone
  (`frontend/lib/masks.ts`, novo - não existia utilitário de máscara no projeto), validação de CPF
  no cliente (mesmo algoritmo do backend, só feedback imediato - quem decide é sempre o servidor).
  `useWorkspaceAuth` ganhou `refresh()` (reconsulta `/auth/me` sem novo login) - usado depois de
  completar o onboarding pra sair do estado de pendência sem reload de página inteira.
  `portal/page.tsx` ganhou um gate novo: `user.portal_first_access_required` (calculado no backend,
  em `serialize_user`/`UserOut`, o frontend só lê) decide entre onboarding e portal normal.

  **Testes**: `backend/tests/test_portal_first_access.py` (novo, 13 casos) cobre as 8 cenários
  pedidos - pendente bloqueia as 4 rotas nomeadas, status/complete continuam alcançáveis, CPF já
  cadastrado confirma, CPF ausente grava, CPF divergente recusa (409) sem mudar nada, senha ≠
  confirmação recusa, senha fraca recusa, CPF com dígito verificador inválido recusa, admin nunca é
  bloqueado, auditoria sem CPF/senha, usuário novo nasce pendente, usuário "antigo" (backfill)
  continua liberado. `frontend/lib/masks.test.ts` (novo, 10 casos) cobre CPF/telefone/checksum.

  **Migration aplicada em 2026-08-28, autorizada explicitamente pelo usuário.** Rodou pelo
  entrypoint padrão do container (`alembic upgrade head` na subida). Backfill conferido no banco:
  13 usuários existentes, **0 ficaram pendentes, 0 com `must_change_password` forçado** - ninguém
  foi bloqueado retroativamente.

  **Achado operacional durante a aplicação**: o `lifespan` do app roda `ensure_initial_admin`/
  `ensure_access_profiles` direto contra o Postgres real (`SessionLocal()`, não o `get_db` que os
  testes sobrescrevem) - não existe banco de teste separado neste projeto. Antes da migration, isso
  já quebrava **13 testes que existiam desde antes desta entrega** (`test_portal_profile.py`,
  `test_management_cases.py`, `test_opa_backfill.py`) com `UndefinedColumn`, característica
  estrutural do projeto, não regressão. Depois de aplicar a migration, a imagem de produção antiga
  (não reconstruída, sem o arquivo da migration) passou a falhar ao subir
  (`Can't locate revision identified by '20260828_0081'`) - alembic não consegue reconciliar um
  banco que já está numa revisão que o histórico local não conhece. **Efeito prático**: o ambiente
  só roda de forma saudável no modo dev (`docker-compose.dev.yml`, código via bind mount) até a
  imagem de produção ser reconstruída com o código atual - não fiz esse rebuild/publish porque não
  foi pedido nesta tarefa (só a migration foi autorizada).

  **Validado ao vivo, tudo confirmado**: `npx tsc --noEmit`, `npm run test -- --run` (45/45),
  `npm run build` - limpos. Backend: **767 passed, as mesmas 13 falhas pré-existentes do módulo
  AI** (nada novo quebrado) - inclui os 13 testes que estavam bloqueados antes da migration, agora
  passando de novo. Navegador, com usuário e colaborador de teste criados e apagados só para a
  validação (nenhum dado real tocado): deslogado → tela de login nova; senha errada → "Email ou
  senha inválidos."; login válido com primeiro acesso pendente → tela de onboarding (rótulo
  "Cadastre seu CPF", máscaras de CPF/telefone corretas em tempo real digitando de verdade);
  conclusão → CPF gravado só em dígitos, telefone com máscara (mesmo padrão do `/portal/profile`
  já existente), `auditLogs` confirmado sem CPF completo (`cpf_masked: "***.***.***-25"`) nem
  senha em nenhuma forma; logout + login de novo com a senha nova → entra direto no portal, sem
  onboarding; mesma conta, segunda passagem pelo onboarding revertido manualmente → campos vêm
  pré-preenchidos (`GET /first-access/status`) e o rótulo do CPF muda pra "Confirme seu CPF
  (cadastrado como ***.***.***-25)"; mobile 375px sem overflow horizontal
  (`scrollWidth === clientWidth`).

  **Pendência real declarada (Fase 2, fora do escopo desta entrega)**: painel admin pra acompanhar
  e resetar primeiro acesso (hoje só existe o campo `must_change_password` no banco, sem tela pra
  um admin forçar reset manualmente).

  Arquivos: `models.py`, `schemas.py`, `core/security.py`, `api/routes/auth.py`,
  `api/routes/portal.py`, `api/routes/users.py`, `modules/admin/router.py`, `services/documents.py`
  (novo), `services/portal_first_access.py` (novo), `alembic/versions/20260828_0081_*.py` (novo,
  não aplicada), `tests/test_portal_first_access.py` (novo), `tests/test_portal_profile.py`,
  `hooks/use-workspace-auth.ts`, `components/portal/first-access-onboarding.tsx` (novo),
  `components/workspace/workspace-login.tsx`, `app/portal/page.tsx`, `lib/api.ts`, `lib/types.ts`,
  `lib/masks.ts` (novo), `lib/masks.test.ts` (novo). Sem commit, sem push, sem migration aplicada,
  sem dado real alterado.

- **Login do Portal unificado com a base do UNI Workspace (frontend, ainda sem commit)**:
  o Portal (`/portal`) tinha formulário de login manual próprio (`handleLogin`,
  `email`/`password`/`loginLoading` locais), diferente do resto do ecossistema, que já
  usa `WorkspaceLogin` + `useWorkspaceAuth` (`/admin`, `/agendamento`, `/cockpit`,
  `/gestao`, `/intelligence`, `/operacao`, `/suporte`, `politica-de-privacidade`,
  `workspace-home`). O Portal passou a usar os dois também - formulário próprio
  removido, autenticação (login válido, login inválido, logout, checagem de sessão)
  agora vem do mesmo hook que todo o resto do Workspace já usa. **Nada de backend,
  regra de negócio, migration ou dado real foi tocado** - troca só da camada de UI de
  autenticação; permissões do portal continuam vindo 100% de `/portal/summary` no
  backend, sem mudança.
  `WorkspaceLogin` (`frontend/components/workspace/workspace-login.tsx`) evoluiu pra
  reutilizável: props opcionais `eyebrow`, `title`, `subtitle`, `description`,
  `helperText` e `variant` ("workspace" | "portal", copy padrão por contexto). Visual
  modernizado - painel de marca com `.uni-gradient` (token oficial já usado no
  Portal) exibindo o logo, hierarquia clara, formulário em coluna única no mobile,
  `Label` associado a cada campo (`useId`), erro anunciado via `aria-describedby`.
  **Os 8 outros consumidores do componente não mudaram de copy nem de comportamento**
  - só ganharam o layout novo automaticamente, por ser o mesmo componente
  compartilhado (confirmado ao vivo em `/suporte`: mesmo texto "Acesse o
  ecossistema" / "Use o mesmo usuário da Gamificação.").
  **Efeito colateral necessário e deliberado**: antes, `/portal` usava
  `summary === null` como proxy de "não está logado" - uma falha ao *carregar dado*
  do portal (backend fora do ar, por exemplo) também jogava a pessoa de volta pro
  formulário de login, mesmo com sessão válida. Separar "está autenticado"
  (`useWorkspaceAuth`) de "os dados carregaram" (`loadPortal`) tornou essa reação
  sem sentido (reenviar e-mail/senha não resolveria um dado que falhou ao
  carregar), então esse caso agora mostra um estado de erro com botão "Tentar
  novamente" em vez de voltar pro login.
  **Validado**: `npx tsc --noEmit` limpo, `npm run test -- --run` 35/35, `npm run
  build` limpo. Ao vivo no navegador (Docker dev, `docker-compose.dev.yml`): `/portal`
  deslogado mostra a tela nova; login com credencial errada mostra "Email ou senha
  inválidos." sem sair da tela; login válido carrega o portal normalmente (testado
  com usuário `viewer` temporário criado só para a validação e removido logo depois
  - nenhum dado real foi criado, alterado ou lido); logout limpa o token
  (`localStorage` confirmado vazio) e volta pro login; mobile 375px sem overflow
  horizontal (`scrollWidth === clientWidth` confirmado). Console sem erro
  inesperado - os únicos 401 registrados são a checagem de sessão antes do login e
  o teste deliberado de senha errada.
  **Pendência real, fora do escopo desta tarefa**: o pedido original também incluía
  forçar CPF e redefinição de senha no primeiro acesso do colaborador. Isso exige
  campo novo em `Collaborator`/`User`, endpoint e migration - inevitavelmente
  backend, o que as instruções desta tarefa proibiram explicitamente ("não mexer em
  backend", "não alterar dados reais"). Não foi implementado. O desenho do login
  já comporta esse fluxo depois (ex: checar uma flag em `summary.user` e mostrar um
  passo extra antes do portal), mas isso é decisão e trabalho de uma tarefa futura,
  com backend liberado.
  Arquivos: `workspace-login.tsx`, `portal/page.tsx`. Nenhum arquivo de backend,
  teste de backend ou migration alterado nesta entrega. Sem commit, sem push.

- **Gráficos, drill-down e filtros novos na `/suporte` (ainda sem commit)**:
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
  **Ainda sem commit por decisão do usuário.**
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
  **Ainda sem commit por decisão do usuário.**
- **Bloco B2 — janela real da base importada, visível na UI (ainda sem commit)**:
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
  **Ainda sem commit por decisão do usuário** — mudanças na worktree,
  preservadas junto com o B1 (que também segue sem commit).
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

- **Backlog tem DUAS convenções no backend e a divergência está visível — decisão
  pendente do usuário**: `in_progress` de `/operations/overview` aplica TODOS os
  filtros ao estoque (inclusive modelo de equipe), enquanto `openings_analytics` e o
  novo `regional_matrix` usam `_backlog_filters`, que ignora modelo de equipe e
  responsável. Com o mesmo filtro, o card da Visão Geral mostrava 23 e o total da
  tabela logo abaixo, 45. A Visão Geral foi resolvida usando uma fonte só (a do
  quadro por filial), mas a tela da Operação Analítica segue mostrando o outro
  número. Decidir qual convenção vale antes de mexer.
- **Gamificação tem tela de login própria, duplicada**: mesma sessão e mesma API do
  resto (`api.login`/`setAuthToken`/`api.me`), mas implementação separada
  (`currentUser`/`authChecked`, usados em ~15 pontos da página). A página foi
  envolvida na casca sem desmontar esse miolo — na prática a casca já garante a
  sessão antes, então aquela tela não aparece. Unificar é frente própria.
- **Suspeita de custo no `/operations/overview`, NÃO medida**: ele traz 4 colunas de
  timestamp de TODA O.S. finalizada no período para calcular médias em Python
  (`timeline_rows`). Num período de 30 dias da empresa inteira são milhares de linhas
  por request. É pré-existente e a Visão Geral também consome. Antes de otimizar,
  medir contra o banco real — mover as médias para SQL preserva o resultado, mas não
  vale mexer no que serve a dois módulos sem número na mão.
- **Suite de testes do backend está quebrada NO AMBIENTE, não no código**: rodando
  tudo dão ~101 falhas e ~203 erros com
  `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in
  that same thread`. Confirmado pré-existente com `git stash`:
  `tests/test_admin_account_reset.py` falha 8/8 na árvore limpa também
  (Python 3.14 + TestClient). Os 19 testes novos da Visão Geral passam. Vale abrir
  como frente própria — enquanto isso, "suite verde" não é critério confiável aqui.

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

- Decidir a convenção única de backlog (ver "Frentes em andamento") e alinhar
  `/operations/overview` ou o `regional_matrix`, com teste que trave a escolha.
- Definir a visão global que será o filtro padrão da Visão Geral (botão "Definir como
  padrão" na própria tela, exige `operations:views:update_global`). Sem isso a tela
  abre sem pré-set de modelo de equipe.
- Medir `/operations/overview` contra o banco real antes de otimizar `timeline_rows`.
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
