# Revisão e modernização do frontend

Data: 04–05/10/2026. Prioridade final: experiência de gamificação.

## Escopo e arquitetura

Inventário estático de 17 páginas: entrada, Visão Geral, Gamificação, Operação, Agendamento, Suporte, Gestão, Administração, Intelligence, Portal, catálogo de módulos, Cockpit por perfil, Localiza, compartilhamento de localização, convite, solicitação de acesso e política de privacidade. Foram examinados o shell compartilhado, componentes de domínio, formulários, tabelas, gráficos e primitivas de interface.

O projeto usa Next.js 16, React 18, TypeScript, Tailwind 3, Radix, Lucide, ECharts e Leaflet. A arquitetura existente foi mantida. As alterações reutilizam essas bibliotecas; nenhuma dependência foi adicionada. A identidade segue o manual UNI: azul, superfícies claras, Inter e efeitos discretos.

## Diagnóstico e intervenções

| Área | Problema observado | Implementação |
| --- | --- | --- |
| Identidade | Bordas, raios, sombras e controles com estilos divergentes | Tokens de superfícies, controles, foco e espaçamento; componentes compartilhados padronizados |
| Navegação | Baixa distinção entre módulo, tela e conteúdo | Sidebar escura, item ativo, recolhimento, contexto da página e busca de telas por Ctrl/Cmd K respeitando o registro de permissões |
| Header | Competição visual e sobreposição dos filtros em determinadas atualizações | Header compacto; medição da altura corrigida para posicionamento dos filtros fixos |
| Dashboard | Filtros antes dos indicadores principais | KPIs antes dos filtros; filtros expansíveis com altura limitada e rolagem interna |
| Formulários | Selects avulsos e labels sem associação ao controle | Select nativo compartilhado; Field com IDs acessíveis; 46 associações de label/controle em 13 arquivos |
| Modais | Wrappers manuais sem tratamento uniforme de teclado | ModalFrame com Radix, título acessível, Escape, contenção e restauração de foco; nove wrappers migrados |
| Tabelas | Visual pesado e rolagem lateral pouco evidente | Cabeçalhos claros, linhas mais leves, região rolável acessível por teclado e indicação de rolagem |
| Feedback | Carregamento e ausência de dados pouco informativos | Skeletons, estados vazios, foco visível, mensagens de status e erro de notificações com nova tentativa |
| Gamificação | Fechamento sem sequência visual clara | Etapas Rascunho → Conferência → Aprovado → Pago derivadas do status existente; destaque do total e sua composição |
| Ranking | Muitos indicadores concorrentes e lista extensa | Nome completo, três indicadores principais, detalhes expansíveis, extrato, paginação de 20/50/100 e busca com limpeza |
| Financeiro | Apenas oito registros visíveis, sem acesso aos demais | Ação para mostrar todos os registros e recolher novamente |
| Responsividade | Alta densidade, textos pequenos e áreas difíceis de operar | Grids adaptáveis, títulos sem truncamento desnecessário, modais limitados ao viewport e controles móveis maiores |

## Padrões reutilizáveis

- `app/globals.css` e `tailwind.config.ts`: cores, raios, sombras, foco e movimento reduzido.
- `components/ui`: Button, Input, Select, Field, Label, Card, Tabs, Dialog, Sheet, ModalFrame, Table, Pagination, EmptyState, Loading e StatusToast.
- `components/workspace/navigation-search.tsx`: busca local nas telas permitidas.
- `components/ui/workspace-loading.tsx`: skeleton do workspace.
- `components/gamification/closure-progress.tsx`: apresentação das etapas do fechamento.

Preferir essas primitivas nas próximas telas, mantendo mensagens, estados vazios e nomes acessíveis específicos do contexto. As cores de status complementam o texto; não devem substituir rótulos. Tabelas extensas podem manter rolagem interna, sem provocar rolagem horizontal da página.

## Preservação funcional

APIs, endpoints, autenticação, permissões, regras de pontuação e integrações não foram alterados. A comparação SHA-256 com o backup confirmou os 58 arquivos existentes em `lib` e `hooks` sem alteração, assim como `package.json`. As modificações se concentram em páginas, componentes e estilos. A ordem recebida do ranking e os valores financeiros continuam vindo das fontes existentes.

Backup anterior à implementação: `C:\Users\paulo\AppData\Local\Temp\uni-frontend-before-20261004-225136.zip`.

## Validação

- Base anterior: TypeScript aprovado; 83 testes aprovados.
- Após a implementação: TypeScript aprovado; 87 testes em 15 arquivos aprovados, incluindo associação acessível dos campos e etapas do fechamento.
- Build de produção (`npm run build`) aprovado, incluindo compilação, TypeScript e geração das páginas.
- Navegador autenticado: navegação entre módulos, busca de telas, dashboard, abertura de editor de perfil e telas de gamificação.
- Ranking: próxima página, troca para 50 registros, filtro por nome, resultado vazio, limpeza, expansão de indicadores e abertura/fechamento de extrato.
- Fechamento: alternância de painéis, expansão financeira e exibição de 12 registros; cinco gráficos renderizados na análise.
- Larguras verificadas: desktop 1440, notebook 1280 e smartphone 390 pixels. Fechamento/ranking sem overflow horizontal da página; tabelas extensas usam rolagem interna.
- Nenhum erro de console na conferência dos gráficos de gamificação.
- Versão compilada: fechamento carregado com os dados existentes; editor de perfil aberto e fechado por Escape, com foco devolvido ao botão “Novo perfil”.

Registro visual: [Fechamento](screenshots/gamificacao-fechamento.jpg).

As verificações de navegador são uma amostra dos fluxos de consulta, não uma certificação exaustiva de todas as combinações de dados, perfis e permissões. Não foram executados pagamentos, aprovação/cancelamento de fechamento, recálculos nem gravações administrativas durante a validação visual. A homologação dessas ações deve ocorrer com dados de teste apropriados.

## Segunda etapa — organização de todas as abas da gamificação (06/10/2026)

| Aba | Organização aplicada |
| --- | --- |
| Fechamento | Análise em duas colunas no desktop; cinco painéis com gráfico e tabela dos mesmos dados; barras com nomes legíveis; comparação horizontal de SLA e reincidência por filial |
| Ranking | Alternância entre cartões detalhados e tabela comparativa, mantendo extratos, busca, valores e paginação |
| Pendências | Subabas de assuntos e diagnósticos com contagem; conteúdo permanece montado para preservar buscas e seleções durante a alternância; ações em lote distribuídas conforme a largura |
| Configuração | Indicadores compactos, navegação por seção com estado ativo, modos simples/avançado preservados; raios e sombras padronizados nas subseções; grades de colaboradores e liderança adaptáveis |
| Auditoria | Cabeçalhos claros, filtros em colunas menos comprimidas, estados selecionados acessíveis e títulos com hierarquia consistente |
| Saldo de pontos | Cabeçalho e filtros agrupados, três situações em cartões separados, indicação de carregamento e distinção visual entre crédito positivo e débito |
| Histórico | Busca por apuração/período/filial/arquivo, paginação e sete colunas principais; arquivo, versão, colaboradores e demais pontos acessíveis por expansão; comparação das oito apurações recentes sem somar recálculos |
| Período | Resumo de competências, volume da competência ativa e referência em uso; tabela com números alinhados e datas legíveis |

A competência aparece no cabeçalho do módulo. No celular, uma barra de abas permite navegar sem depender da abertura do menu lateral. Os gráficos têm estados vazios e botões nomeados para uso por teclado. Barras com resultados negativos usam uma linha de zero e direção oposta aos resultados positivos.

### Preservação e validação desta etapa

- Comparação por AST das **133 chamadas `api.*`** com o backup anterior: nenhuma chamada alterada.
- Sem alterações em regras de negócio, permissões, autenticação, endpoints ou banco de dados.
- **90 testes em 16 arquivos aprovados**, incluindo apresentação de valor zero, resultados negativos e estado sem dados dos gráficos.
- Build de produção aprovado com TypeScript e geração de páginas. Checagem de tipos adicional após os ajustes finais de apresentação.
- Navegador autenticado: gráfico/tabela do Top 15 com 15 registros; ranking com 20 linhas por página; troca de pendências preservando a busca; configuração simples/avançada; histórico com busca, resultado vazio, expansão e próxima página; busca do saldo; aba Período; agrupamento da Auditoria com dados carregados.
- Revisão em 1440 e 390 pixels; rolagem lateral contida nas tabelas e barras de navegação. A auditoria foi recarregada após a sincronização automática substituir a apuração anteriormente consultada.

Backup desta etapa: `C:\Users\paulo\AppData\Local\Temp\uni-gamification-tabs-before-20261005-150207.zip`.

Prévia do código deste workspace: `http://127.0.0.1:3100/gamificacao`. A aplicação Docker da porta 3000 é uma instância separada e não foi sobrescrita.

Revisão responsiva final: corrigidas as trilhas de grade dos cadastros de colaboradores, liderança e usuários. Em 390 px, os painéis mantêm a largura disponível e as tabelas possuem rolagem própria. Captura final: screenshots/gamificacao-ranking-colunas.jpg. A revisão foi visual e de navegação; nenhuma operação de pagamento, exclusão ou alteração de cadastro foi executada.
