# PRD — Módulo Operação Analítica

## 1. Contexto e objetivo

O módulo Operação Analítica será a fonte de análise operacional das Ordens de Serviço (O.S.) originadas no IXC. Ele permitirá acompanhar demanda, execução, prazo, garantia, backlog e produtividade por filtros operacionais, sem alterar as regras de remuneração da Gamificação.

O módulo faz parte do mesmo produto UNI Workspace e usa a infraestrutura atual de FastAPI, Next.js, PostgreSQL, Docker e autenticação. Nesta primeira fase, ele será um módulo do monólito, com fronteiras de código, dados e API que permitam extração futura sem reescrita.

## 2. Problema que resolve

Os dados hoje importados para Gamificação representam somente O.S. técnicas finalizadas e já normalizadas para cálculo de pontos. Essa visão não permite analisar O.S. abertas, andamento histórico, backlog, demandas internas, SLA por dimensões operacionais ou drill-through de uma métrica para a lista de O.S.

## 3. Objetivos de produto

- Consolidar O.S. do IXC em uma base analítica auditável.
- Oferecer filtros globais e persistentes para todas as visões.
- Exibir indicadores e hierarquias comparáveis ao relatório operacional de referência.
- Permitir abertura de detalhes mantendo o contexto do número ou total selecionado.
- Disponibilizar resultados de O.S. para a Gamificação sem compartilhar tabelas internas.

## 4. Usuários e permissões

| Perfil | Permissões iniciais | Acesso |
|---|---|---|
| Administrador | `operations:read`, `operations:manage` | Todas as visões, configuração e reprocessamento. |
| Gestor regional | `operations:read` | Dados somente das regionais autorizadas. |
| Analista | `operations:read` | Painéis e detalhe conforme escopo autorizado. |

A autorização de empresa, regional e módulo deve ser aplicada no backend em todas as consultas. O filtro visual nunca substitui a regra de acesso.

## 5. Escopo funcional

### 5.1 Navegação

O módulo tem rota raiz `/operacao` e navegação interna por menu lateral recolhível (hambúrguer). A primeira entrega expõe Visão Geral, SLA, Calendário, Andamento, Detalhes de O.S. e Equipes e Metas. Garantia, Abertura, Finalizadas e Internas entram como novas entradas do mesmo menu nas fases seguintes, sem criar outro domínio ou outro login.

### 5.2 Filtros globais

Os filtros disponíveis dependerão da página, mas o contrato comum incluirá período, empresa/filial, UF/cidade, tipo de contrato, tipo de pessoa, tipo geral, assunto, diagnóstico, departamento, setor, prioridade, criador e responsável. As páginas de detalhe também aceitarão contrato, cliente e protocolo.

Os filtros dimensionais aceitam seleção múltipla e são aplicados globalmente em Visão Geral, SLA, Andamento e Detalhes. Cada usuário pode salvar, renomear, atualizar e excluir combinações de filtros. Os presets pertencem ao usuário autenticado e não alteram seu escopo de autorização.

Os dropdowns são facetados: ao selecionar filial, cidade, assunto ou outra dimensão, as opções das demais dimensões são recalculadas dentro do mesmo contexto. Para responsável, o usuário pode escolher entre opções originadas de todas as O.S. ou somente de O.S. finalizadas no período.

O contexto de data deve ser explícito: abertura usa `opened_at`; SLA, Garantia e Finalizadas usam `closed_at`. Andamento é uma exceção intencional: consulta o estoque atual de todas as O.S. abertas já sincronizadas, sem restringir a data de abertura. Datas vazias são aceitas nessa visão e seus filtros dimensionais continuam ativos. Status incompatíveis, como Finalizada e Cancelada, são retirados ao entrar em Andamento e a interface informa essa adaptação.

Na etapa atual, o usuário seleciona datas entre o primeiro dia do terceiro mês-calendário disponível e a data atual. O frontend restringe os seletores e o backend rejeita qualquer período externo a essa janela. Atualizações interativas ficam limitadas a sete dias; cargas maiores usam backfill retomável no servidor, sempre em lotes diários e com limite de registros por consulta.

### 5.3 Visão Geral

- Cards para abertura, média diária, backlog do período, backlog acumulado, realizadas, média diária, atrasadas e no prazo.
- Gráfico mensal com abertura, realizadas, backlog e backlog acumulado.
- Medidores e série histórica para SLA técnico, IVC e IVT.
- Indicadores por filial e por departamento/setor.

### 5.4 SLA

- Métricas de realizadas, SLA técnico e tempo médio de fechamento.
- Faixas: até 12h, 12–24h, 24–48h, 48–72h e acima de 72h.
- A tabela principal é hierárquica e expansível na ordem `Tipo geral → Assunto → Diagnóstico`. Tipo geral é o nível raiz; Assunto e Diagnóstico podem ser habilitados, e os filhos são consultados somente ao expandir a linha pai.
- As faixas horárias são exibidas como percentuais das O.S. com tempo de fechamento mensurável.
- A cor do SLA segue a regra operacional fixa: verde para `SLA ≥ 80%`, amarelo para `60% ≤ SLA < 80%` e vermelho para `SLA < 60%`.
- A última linha apresenta total ponderado: SLA calculado por `soma no prazo / soma mensurável`, faixas por suas contagens consolidadas e tempo médio pela soma dos tempos dividida pelas O.S. mensuráveis. Não é usada média simples dos percentuais das linhas.
- A tabela `Produtividade e SLA por colaborador` apresenta quantidades por tipo de O.S., realizadas, SLA, dias produtivos e média diária. Suas métricas de tempo médio, mínimo e máximo usam exclusivamente a execução efetiva, calculada por `finished_at - execution_started_at` para as O.S. do responsável agrupado.
- O.S. sem início de execução, sem finalização ou com sequência temporal negativa não entram nas estatísticas de execução; a tabela informa a quantidade efetivamente mensurável.

### 5.5 Calendário operacional mensal

- Ao abrir o módulo, o período padrão vai do primeiro dia do mês corrente até a data atual; os três meses carregados permanecem disponíveis para seleção manual.
- A competência é o mês da data final aplicada no painel e nunca pode ultrapassar a janela autorizada da base.
- A visualização é dividida em blocos por regional, com uma linha por responsável e uma coluna por dia do mês.
- Os cabeçalhos e totais de todas as regionais permanecem visíveis, mas somente uma regional por vez monta a grade de colaboradores; isso preserva o recorte completo sem manter milhares de células simultaneamente no navegador.
- Em desktop, as 31 colunas diárias devem se ajustar à largura do painel sem rolagem lateral. Em telas estreitas, a rolagem interna permanece disponível para preservar legibilidade e acessibilidade.
- Cada célula apresenta a quantidade de O.S. fechadas pelo responsável naquele dia; dias ainda indisponíveis permanecem visualmente inativos.
- Ao selecionar qualquer célula disponível, um drawer lateral apresenta responsável, regional, modelo, data, quantidade, desempenho e somente as O.S. daquele recorte, com status e observações operacionais quando existirem.
- Todas as agregações e o recorte do drill-through são executados no backend com autorização regional; o frontend não recebe o conjunto integral de O.S.
- Os modelos operacionais padronizados são: `INSTALAÇÃO CIDADE`, `TECNICO 12/36H`, `SUPORTE MOTO`, `SUPORTE CARRO`, `RURAL`, `FAZ TUDO`, `AUXILIAR` e `Nao informado`.
- Administradores configuram em um único ponto onde começam as faixas `Mediano`, `Bom` e `Excelente/meta`. O backend exige `1 < mediano < bom < excelente/meta`; o atalho de padrão legado preenche automaticamente `meta - 2`, `meta - 1` e `meta`.
- Cada identidade operacional (`responsável IXC + regional`) pode ser vinculada somente a um modelo operacional. Não há vínculo com o cadastro de colaboradores da Gamificação.
- A classificação é calculada exclusivamente no service do backend e retornada pronta para a UI: sem produção (neutro), abaixo da meta, mediano, bom e excelente. Cada modelo possui suas quatro cores e a legenda do calendário apresenta as faixas e cores efetivamente configuradas para os modelos presentes no recorte. Produção sem modelo vinculado permanece neutra e é identificada como `Sem meta configurada`.
- A exclusão definitiva de modelo exige a permissão `operations:manage`, é auditada e fica bloqueada enquanto houver colaboradores operacionais vinculados; a desativação continua disponível para preservação histórica.
- O nome de exibição do modelo é livremente editável e único, sem alterar seu identificador nem os vínculos existentes.
- O detalhe diário apresenta no backend: média, mediana, mínimo e máximo da execução; espera média entre abertura e execução; ciclo total médio; SLA do recorte; janela entre primeira execução e última finalização; cobertura dos tempos e distribuição por tipo.
- O início efetivo usa `data_hora_execucao` do IXC com fallback em `data_inicio`; a finalização usa `data_final` com fallback em `data_fechamento`. Sequências ausentes ou negativas não entram nas médias e são informadas como dados incompletos.
- Cada O.S. do recorte abre um detalhamento com timeline, duração das etapas, SLA, cliente, contrato, regional, cidade, responsável, criador, setor, prioridade, tipo, assunto, diagnóstico e observações operacionais.
- Cada aba consulta apenas os endpoints necessários ao seu conteúdo. O calendário, SLA, andamento e detalhes não são carregados antecipadamente na Visão Geral.
- A lista de responsáveis da configuração é paginada no cliente em lotes de 50 linhas para limitar o custo de renderização dos seletores.

### 5.6 Garantia

- Quantidade e percentual de garantia de 30 dias.
- Evolução mensal de garantias e percentual.
- Lista de contrato, cliente, data de referência, O.S. origem, garantia e assunto.
- A definição definitiva de vínculo de garantia deve ser configurável e validada com a operação.

### 5.7 Abertura, Andamento, Finalizadas e Internas

- Abertura: volume mensal e matrizes por SLA/status e classificações operacionais. O total operacional e sua série ignoram exclusivamente o filtro de responsável, pois o responsável atual não comprova a atribuição no instante da abertura. Quando esse filtro estiver ativo, a tela apresenta separadamente a quantidade atualmente associada aos selecionados, sem tratá-la como autoria histórica.
- A Visão Geral apresenta tendências por dia, semana ou mês: SLA com meta visual de 80%, volume finalizado e atrasado, aberturas operacionais, associações atuais e finalizadas empilhadas por situação SLA. Todos os gráficos, exceto a exceção explícita de responsável nas aberturas, respeitam os filtros aplicados.
- A Visão Geral possui uma Torre de Controle Preventiva. O monitor compara os sete dias recentes com o mesmo dia da semana nas oito semanas anteriores, evitando comparar dias operacionais diferentes. A classificação combina desvio de aberturas, persistência, entradas versus finalizações, crescimento do backlog e proporção vencida. Um pico isolado tende a gerar atenção; criticidade exige persistência ou combinação de pressão e incapacidade de absorção.
- O mapa de desvios inicia por assunto e permite expansão sob demanda por `assunto -> regional -> cidade -> setor -> responsável`. Cada nível é agregado no backend apenas quando aberto, preservando desempenho e permissão regional. O drill-through lista somente as O.S. abertas na janela recente analisada.
- Toda a Torre de Controle ignora o filtro de responsável para manter entradas e capacidade na mesma base operacional. O responsável aparece no último nível como associação atual, sem ser apresentado como autoria histórica da abertura. Histórico inferior a quatro semanas é sinalizado como insuficiente.
- Andamento: estoque atual completo por filial, tipo geral, assunto e SLA/status, incluindo O.S. abertas em meses anteriores e drill-through sem filtro de data.
- Finalizadas: realizadas e percentual por filial, tipo geral e responsável, com série temporal que respeita todos os filtros.
- Internas: acompanhamento por projeto e POP, com O.S. abertas no prazo e atrasadas.

- Ao lado de `Mais filtros`, o módulo exibe a data e a hora da última importação IXC concluída. Esse horário vem da auditoria de importação do backend e não do carregamento da página.
- Em telas pequenas, o detalhe diário prioriza a lista de O.S.: métricas completas ficam recolhidas por padrão, cards usam uma coluna quando necessário e o detalhamento completo ocupa a tela do dispositivo.

### 5.8 Drill-through e detalhe

Qualquer card, linha ou total elegível deve oferecer a ação **Ver detalhes**. A tela resultante deve herdar filtros, origem e critério do agregado, informar a quantidade de linhas e oferecer busca, paginação, ordenação, retorno ao painel e seleção de colunas por usuário.

## 6. Dados e integração IXC

O IXC é a origem. O módulo reutilizará o cliente HTTP existente, mas terá ingestão própria. O filtro oferece os 21 setores ativos confirmados no IXC. A primeira cobertura histórica completa, de 01/05/2026 a 21/07/2026, abrange os setores `7` (Suporte Externo), `8` (Suporte Externo Rádio) e `9` (Suporte Externo Fibra); os demais setores permanecem identificados como cobertura parcial até o backfill completo.

Cidade, UF, tipo de pessoa, status e situação SLA devem ser armazenados/exibidos com nomes de negócio. IDs e códigos do IXC permanecem somente como chaves de origem e auditoria. Exemplos: `26` → `RO`, `F` → `Pessoa Física`, `J` → `Pessoa Jurídica`, `RAG` → `Reagendada` e `DS` → `Deslocamento`.

Dados mínimos: identificador IXC, protocolo, abertura, prazo, fechamento, status, substatus, última atualização, empresa, filial, UF, cidade, contrato, cliente, tipo de contrato, tipo de pessoa, tipo geral, assunto, diagnóstico, departamento, setor, prioridade, criador, responsável, agendamento, turno, projeto e POP quando aplicáveis.

O módulo deve guardar no MVP:

- registro canônico atual da O.S.;
- payload de origem para auditoria da normalização.

Eventos e snapshots diários ficam para uma fase posterior. Até lá, Andamento representa o estado atual sincronizado e não pretende reconstruir qual era a posição do backlog em uma data histórica.

Datas recebidas sem fuso devem ser interpretadas no fuso operacional definido antes de serem convertidas e armazenadas. Não é permitido assumir UTC silenciosamente.

## 7. Regras e métricas iniciais

- `SLA técnico = realizadas no prazo / realizadas com SLA mensurável`.
- Meta visual inicial de SLA: 80%, configurável.
- Backlog acumulado usa a posição de O.S. pendentes na data de corte.
- Garantia de 30 dias, IVC e IVT permanecem como fórmulas pendentes de validação com a base real; nenhuma fórmula inferida deve ser tratada como regra oficial sem configuração/versionamento.

## 8. Requisitos não funcionais

- Consultas ordinárias ao IXC são filtradas pelo lote diário do período autorizado. A atualização do backlog aberto usa uma rotina separada e limitada, particionada pelos três setores prioritários e por cada status aberto conhecido; ela não faz uma leitura irrestrita da tabela. IDs locais anteriormente abertos que não reaparecem nessas partições são reconciliados diretamente por ID, em lotes de até 200, para confirmar fechamento ou cancelamento. Cadastros auxiliares são consultados somente pelos IDs presentes no lote.
- Backfills históricos possuem checkpoint por dia, retomada, auditoria, concorrência única e `upsert` idempotente. Painéis nunca consultam o IXC diretamente.
- Consultas agregadas no backend; o frontend não calcula métricas sobre o conjunto integral de O.S.
- Tabelas de detalhe paginadas e com filtros indexados.
- Auditoria de importações, alterações, reprocessamentos e contexto de drill-through.
- Migrations Alembic para toda alteração estrutural.
- Tratamento de loading, vazio, erro, responsividade e acessibilidade básica.
- Tokens IXC e credenciais exclusivamente em variáveis de ambiente do backend.

## 9. Integração com Gamificação

Operação Analítica é dona da ingestão e da medição operacional. Gamificação continua dona de pontos, remuneração e fechamento. A integração ocorrerá por contrato versionado de leitura/projeção, por exemplo: situação de SLA, horas de fechamento, garantia, recorrência e identificador da O.S.

Na transição, a tabela atual `service_orders` não será ampliada para conter todas as O.S. analíticas. Quando o módulo estiver validado, a Gamificação poderá consumir uma projeção de O.S. técnicas finalizadas, eliminando a duplicação de consultas ao IXC.

## 10. Fases de entrega

1. Fundação: registro de módulos, contratos, migrations e ingestão canônica sob demanda do mês atual.
2. Visão Geral, filtros e detalhe de O.S.
3. SLA, Abertura, Andamento e Finalizadas.
4. Garantia e Internas.
5. Projeção para Gamificação e otimização de agregados.

## 11. Critérios de aceite da fundação

- O módulo consta como ativo no registro somente após possuir rota, permissão e estado vazio funcional.
- Nenhuma tabela, cálculo, rota ou tela da Gamificação muda de comportamento.
- O PRD, a arquitetura e os contratos descrevem fronteiras, permissões, dados e fases.
- A estrutura de código permite adicionar rotas, schemas, serviços, modelos e testes sob o domínio `operations`.
