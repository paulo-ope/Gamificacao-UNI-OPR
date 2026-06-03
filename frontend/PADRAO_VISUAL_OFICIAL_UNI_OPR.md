# Padrão Visual Oficial — UNI Workspace / Gamificação Operacional

## 1. Objetivo

Este documento oficializa o padrão visual do frontend da plataforma UNI Workspace, começando pelo módulo de Gamificação Operacional. A referência-base é o guia visual apresentado pela operação, adaptado para um produto interno B2B de conferência, auditoria, fechamento e remuneração variável.

O objetivo não é transformar a interface em uma landing page ou dashboard genérico. O objetivo é criar um sistema visual consistente, reaproveitável e escalável para vários módulos no mesmo container, com aparência moderna, linguagem corporativa clara e alta previsibilidade de uso.

## 2. Princípios do padrão oficial

### 2.1 Foco operacional
- A interface deve priorizar leitura, conferência, auditoria e tomada de decisão.
- O layout deve favorecer blocos executivos no topo e detalhamento progressivo abaixo.
- O usuário precisa entender rapidamente: período, contexto, valor, pendência, status e ação.

### 2.2 Consistência
- Mesmo tipo de informação deve usar sempre o mesmo componente, peso visual e rótulo.
- Card financeiro, card operacional, badge, botão e tabela não devem mudar de estilo entre abas sem motivo funcional.

### 2.3 Clareza antes de decoração
- Evitar excesso de bordas fortes, gradientes concorrentes e textos explicativos longos na face principal da tela.
- Explicações de apoio devem aparecer sob demanda, via tooltip, hint, modal ou área recolhível.

### 2.4 Sistema antes de tela
- O frontend deve evoluir por tokens, componentes-base e padrões de layout.
- Telas novas ou refatoradas devem nascer em cima do sistema, não em cima de ajustes locais independentes.

### 2.5 Escalabilidade para múltiplos módulos
- O cabeçalho, a navegação principal, a barra de ações, os cards e as tabelas devem servir como base para outros produtos internos da UNI.

## 3. Padrão visual oficial

## 3.1 Identidade
- Marca principal: `UNI Workspace`
- Módulo ativo: `Gamificação Operacional`
- Estilo: SaaS B2B premium, corporativo, limpo, técnico sem frieza excessiva
- Público: diretoria, RH, financeiro, gestores, supervisores, operação e auditoria

## 3.2 Cores oficiais

### Primária
- Azul/ciano da UNI como eixo principal da identidade
- Uso: CTA principal, foco, seleção ativa, destaques institucionais

### Secundária
- Tons de azul claro e ciano suave para apoio visual
- Uso: superfícies de apoio, painéis secundários, badges informativas

### Neutras
- Base clara
- Branco predominante
- Escala de cinzas frios para texto, borda e fundo

### Semânticas
- Sucesso: verde
- Atenção: âmbar
- Erro/destrutivo: vermelho
- Informação: azul

### Regra prática
- A cor não deve substituir hierarquia tipográfica.
- O estado ativo deve ser percebido por contraste, borda, fundo e peso, não só pela cor.

## 3.3 Tipografia oficial

### Família
- `Inter`

### Hierarquia alvo
- H1: título principal de módulo
- H2: título de tela
- H3: título de seção
- H4/H5: títulos internos de card, painel, tabela ou bloco técnico
- Texto base: 14px a 16px
- Texto auxiliar: 12px a 13px

### Regras
- Nada de letter-spacing negativo
- Evitar textos muito longos na primeira dobra
- Usar uppercase apenas em labels pequenas, métricas e meta-informação

## 3.4 Espaçamento e grid

### Unidade base
- Escala baseada em múltiplos de 4px

### Padrão
- Espaçamento interno de cards e painéis: 16px a 24px
- Espaçamento entre blocos: 12px a 24px
- Grid principal responsivo com leitura clara em desktop e notebook

### Regra
- Um bloco deve respirar sem parecer “card em cima de card”.
- Evitar empilhar muitos painéis com mesma densidade visual na mesma dobra.

## 3.5 Bordas, raios e sombras

### Raio oficial
- Componentes pequenos: 6px a 8px
- Cards e painéis principais: 16px a 24px

### Bordas
- Bordas leves, com cinza neutro
- Bordas mais fortes apenas quando o bloco exige framing de leitura

### Sombras
- Sombra curta e suave
- Nada de sombra pesada como recurso decorativo padrão

## 3.6 Botões oficiais

### Primário
- Ações principais da tela: salvar, aplicar, recalcular, exportar prioritário

### Secundário
- Navegação de apoio e ações complementares

### Ghost
- Ações discretas e locais

### Destrutivo
- Excluir, resetar, remover vínculo, apagar

### Regras
- Toda tela deve deixar clara a ação principal
- Botão perigoso deve ficar visualmente separado
- Não misturar muitos botões com o mesmo peso visual na mesma linha

## 3.7 Inputs e filtros
- Inputs com altura e padding consistentes
- Select e busca visualmente alinhados
- Estados de foco claros
- Placeholders curtos e funcionais
- Filtros globais devem ficar agrupados e previsíveis

## 3.8 Cards oficiais

### Card financeiro
- Valor principal em destaque
- Rótulo curto
- Texto de apoio opcional

### Card operacional
- Quantidade, status ou métrica de volume

### Card de alerta
- Atenção visual controlada
- Deve chamar para ação sem poluir a leitura

### Regra
- Não repetir duas métricas com a mesma intenção na mesma dobra

## 3.9 Tabelas
- Cabeçalho leve, fixo quando necessário
- Colunas essenciais primeiro
- Ações no fim
- Texto alinhado com prioridade operacional
- Valores financeiros e pontos com formatação consistente

## 3.10 Modais, drawers e hints
- Modais devem abrir acima do layout, sem corte por overflow
- Drawers devem concentrar auditoria detalhada e extrato completo
- Hints devem usar ícone `i` discreto
- Explicações longas não devem ficar soltas na tela

## 4. Mapeamento do frontend atual

## 4.1 Estrutura atual

### Entrada da aplicação
- Layout global: [frontend/app/layout.tsx](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/app/layout.tsx>)
- Estilos globais: [frontend/app/globals.css](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/app/globals.css>)
- Página principal do módulo: [frontend/app/gamificacao/page.tsx](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/app/gamificacao/page.tsx>)

### Biblioteca UI local
- Botões: [frontend/components/ui/button.tsx](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/components/ui/button.tsx>)
- Inputs: [frontend/components/ui/input.tsx](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/components/ui/input.tsx>)
- Badges: [frontend/components/ui/badge.tsx](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/components/ui/badge.tsx>)
- Tabs: [frontend/components/ui/tabs.tsx](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/components/ui/tabs.tsx>)
- Tabelas: [frontend/components/ui/table.tsx](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/components/ui/table.tsx>)
- Accordion, sheet, tooltip, command e afins na pasta [frontend/components/ui](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/components/ui>)

### Componentes de domínio da gamificação
- Auditoria: [frontend/components/gamification/audit-panel.tsx](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/components/gamification/audit-panel.tsx>)
- Ranking: [frontend/components/gamification/ranking-table.tsx](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/components/gamification/ranking-table.tsx>)
- Configuração: [frontend/components/gamification/logic-configuration-panel.tsx](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/components/gamification/logic-configuration-panel.tsx>)
- Liderança: [frontend/components/gamification/leadership-bonus-panel.tsx](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/components/gamification/leadership-bonus-panel.tsx>)
- Gráficos: [frontend/components/gamification/dashboard-charts.tsx](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/components/gamification/dashboard-charts.tsx>)
- Extrato/auditoria individual: [frontend/components/gamification/collaborator-orders-sheet.tsx](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/components/gamification/collaborator-orders-sheet.tsx>) e [frontend/components/gamification/order-audit-drawer.tsx](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/components/gamification/order-audit-drawer.tsx>)

## 4.2 O que já está alinhado com o guia

### Base técnica boa
- Next.js + React + Tailwind + componentes Radix
- Biblioteca UI local já existe
- Tokens de cor via CSS variables já existem em [globals.css](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/app/globals.css>)
- Tailwind já consome os tokens em [tailwind.config.ts](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/tailwind.config.ts>)

### Caminho visual já iniciado
- Header da Gamificação já foi elevado para um shell mais moderno
- Cards financeiros do fechamento já foram reorganizados
- Tooltips/hints já foram externalizados em [info-hint.tsx](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/components/gamification/info-hint.tsx>)
- Tabs e blocos recolhíveis já existem e suportam evolução sem reescrita completa

## 4.3 O que ainda está desalinhado

### Tipografia
- O layout atual não define `Inter` oficialmente no root
- Existem muitos tamanhos e pesos decididos localmente dentro de [page.tsx](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/app/gamificacao/page.tsx>)

### Tokens
- A paleta atual está funcional, mas ainda não foi formalizada como sistema visual oficial da plataforma
- Faltam tokens documentados para:
  - títulos
  - estados de botão
  - badges semânticas
  - espaçamento
  - shadow scale
  - superfícies

### Componentes-base
- `Button`, `Input`, `Badge`, `Tabs` e `Table` já existem, mas ainda não cobrem todas as variantes do guia
- Há muito ajuste de classe direto na tela, em vez de variações encapsuladas no componente base

### Layout
- [frontend/app/gamificacao/page.tsx](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/app/gamificacao/page.tsx>) concentra shell, lógica, visual e composição de muitas seções
- O módulo já melhorou bastante, mas ainda depende demais de classes locais para refino visual

### Consistência
- O padrão de card ainda varia bastante entre fechamento, ranking, pendências e configuração
- Filtros globais e filtros locais ainda não seguem um único modelo
- Alguns blocos ainda têm densidade de informação muito diferente para funções semelhantes

## 4.4 Estado por camada

| Camada | Estado atual | Observação |
|---|---|---|
| Tokens visuais | Parcial | Existem, mas sem governança formal |
| Tipografia | Parcial | Sem Inter oficial e sem escala documentada |
| Componentes-base UI | Parcial | Estrutura pronta, faltam variantes oficiais |
| Shell da plataforma | Parcial | Header bom, navegação ainda pode amadurecer |
| Fechamento | Parcial/Bom | Já está mais executivo, ainda precisa lapidar consistência |
| Ranking | Parcial | Melhorou, mas precisa consolidar filtros, cards e subtabs |
| Auditoria | Parcial | Funcional, mas ainda com espaço para refino de leitura |
| Configuração | Atenção | É a área mais densa e com maior chance de poluição visual |
| Extrato e drawers | Parcial | Precisam seguir mais firmemente o sistema de modais e tabelas |

## 5. Padrão oficial de componentes

## 5.1 Componentes que passam a ser base oficial
- `Button`
- `Input`
- `Badge`
- `Tabs`
- `Table`
- `Sheet`
- `Accordion`
- `InfoHint`

## 5.2 Componentes que precisam ser promovidos a padrão
- `PageHeaderShell`
- `ExecutiveMetricCard`
- `OperationalMetricCard`
- `SectionCard`
- `FilterBar`
- `EmptyState`
- `DataPanelHeader`
- `FinancialSummaryRow`

Hoje esses padrões estão espalhados principalmente em [frontend/app/gamificacao/page.tsx](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/app/gamificacao/page.tsx>) e devem ser extraídos em etapas.

## 6. Plano de migração

## Fase 1 — Oficialização dos tokens
**Objetivo:** transformar o guia em base formal do projeto.

### Entregas
- Definir `Inter` como fonte oficial do app
- Formalizar tokens em `globals.css`
- Revisar `tailwind.config.ts` com nomes estáveis
- Documentar:
  - cores
  - tipografia
  - radius
  - spacing
  - shadows
  - estados semânticos

### Arquivos-alvo
- [frontend/app/layout.tsx](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/app/layout.tsx>)
- [frontend/app/globals.css](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/app/globals.css>)
- [frontend/tailwind.config.ts](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/tailwind.config.ts>)

### Risco
- Baixo

## Fase 2 — Consolidação da biblioteca UI
**Objetivo:** parar de resolver visual importante com classes soltas em tela.

### Entregas
- Expandir variantes de `Button`
- Revisar `Input`, `Badge`, `Tabs`, `Table`
- Padronizar hover, focus, active, disabled
- Criar:
  - `ExecutiveMetricCard`
  - `OperationalMetricCard`
  - `SectionCard`
  - `FilterBar`
  - `EmptyState`

### Arquivos-alvo
- [frontend/components/ui/button.tsx](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/components/ui/button.tsx>)
- [frontend/components/ui/input.tsx](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/components/ui/input.tsx>)
- [frontend/components/ui/badge.tsx](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/components/ui/badge.tsx>)
- [frontend/components/ui/tabs.tsx](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/components/ui/tabs.tsx>)
- [frontend/components/ui/table.tsx](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/components/ui/table.tsx>)
- novos componentes em [frontend/components/ui](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/components/ui>)

### Risco
- Baixo para médio

## Fase 3 — Shell oficial da plataforma
**Objetivo:** consolidar o padrão para múltiplos módulos no mesmo ambiente.

### Entregas
- Transformar o header atual em shell reaproveitável
- Padronizar:
  - área da marca
  - identificação do módulo
  - bloco de usuário
  - barra de ações
  - navegação principal

### Arquivos-alvo
- [frontend/app/gamificacao/page.tsx](</C:/Users/paulo/OneDrive/Documentos/Gamificação UNI OPR/frontend/app/gamificacao/page.tsx>)
- componente novo sugerido: `frontend/components/ui/page-header-shell.tsx`

### Risco
- Médio

## Fase 4 — Refino das telas executivas
**Objetivo:** elevar leitura e confiança das áreas mais visíveis.

### Ordem sugerida
1. `Fechamento`
2. `Ranking`
3. `Auditoria`
4. `Extrato do colaborador`

### Entregas
- padronização de cards
- padronização de headers de seção
- padronização de linhas financeiras
- melhoria de filtros e estados vazios
- redução de poluição visual

### Risco
- Médio

## Fase 5 — Refino da Configuração
**Objetivo:** atacar a área mais densa sem quebrar usabilidade.

### Entregas
- dividir por blocos claros
- separar configuração operacional de configuração técnica
- reduzir redundância visual
- reaproveitar cards e tabelas oficiais
- padronizar painéis de liderança, grupos, assuntos, diagnósticos e reincidência

### Risco
- Médio para alto

## Fase 6 — Governança visual contínua
**Objetivo:** impedir regressão.

### Entregas
- checklist visual para novos componentes
- convenção de nomes e classes
- guideline de quando usar:
  - card financeiro
  - card operacional
  - tabela
  - drawer
  - modal
  - accordion

### Risco
- Baixo

## 7. Prioridade prática

### Alta prioridade
1. Formalizar tokens e tipografia
2. Consolidar `Button`, `Input`, `Badge`, `Tabs` e `Table`
3. Extrair cards executivos e operacionais

### Média prioridade
4. Criar shell oficial reutilizável
5. Refatorar `Fechamento` e `Ranking` para usar os novos componentes

### Próxima onda
6. Auditoria
7. Extrato
8. Configuração

## 8. Regras de migração

- Não alterar regras de negócio durante migração visual
- Não misturar cálculo e redesign no mesmo lote quando o escopo puder ser separado
- Toda melhoria visual nova deve preferir componente compartilhado
- Nova tela não deve nascer com classe avulsa antes de verificar se já existe padrão equivalente
- Quando houver conflito entre “bonito” e “operacionalmente claro”, vence o segundo

## 9. Decisão oficial

Fica definido que:

1. O guia visual apresentado passa a ser a referência oficial do frontend da plataforma UNI Workspace.
2. A Gamificação Operacional será o módulo piloto dessa padronização.
3. A evolução do frontend seguirá primeiro por `tokens -> componentes -> shell -> telas`.
4. O padrão visual deve servir como fundação para os próximos sistemas internos da UNI.

## 10. Próximo passo recomendado

Iniciar a **Fase 1 — Oficialização dos tokens**, seguida da **Fase 2 — Consolidação da biblioteca UI**.

Isso cria uma base correta para continuar modernizando a Gamificação sem retrabalho nas próximas telas.
