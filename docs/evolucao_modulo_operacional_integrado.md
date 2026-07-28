# Evolucao do Modulo Operacional Integrado

Data de referencia: 23/07/2026

## 1. Objetivo deste documento

Este documento registra a evolucao desejada do modulo operacional para transformar a operacao em uma gestao integrada, com foco em:

- monitoramento diario e em tempo quase real;
- acompanhamento por excecao;
- cobranca estruturada da supervisao;
- visao executiva para matriz e gerencia operacional;
- base analitica confiavel para exportacao e uso em modelos de chat/IA;
- preservacao da arquitetura atual do projeto, com evolucao incremental.

O objetivo nao e refazer o modulo. O objetivo e aproveitar a fundacao ja existente e organizar a proxima fase do produto com direcao clara.

## 2. Situacao atual observada no projeto

O projeto ja possui base relevante para essa evolucao:

- modulo operacional com frontend dedicado em `frontend/app/operacao/page.tsx`;
- calendario operacional mensal por regional e colaborador;
- configuracao de metas e modelos de equipe;
- visao analitica inicial com overview, SLA, backlog, detalhes e configuracoes;
- monitor preventivo tipo torre de controle;
- filtros operacionais persistiveis;
- base de analytics operacional ja introduzida no backend;
- permissao por perfil para leitura, calendario, backlog, detalhes e configuracoes;
- base de importacao operacional com historico e consolidacao de O.S.

Isso indica que a proxima etapa deve ser de consolidacao e ampliacao, nao de reconstrucao.

## 3. Visao de produto

O modulo operacional deve evoluir para ser um cockpit unico de gestao da operacao, atendendo perfis diferentes dentro do mesmo ecossistema:

- matriz e gerencia operacional: visao consolidada, riscos, pendencias e comparativos;
- regional: leitura do proprio desempenho e pontos de acao;
- supervisor: acompanhamento da equipe, justificativas e disciplina de execucao;
- analista: exploracao de desvios, causas, tendencias e exportacao;
- modelos de chat/IA: consumo de dados analiticos estruturados e contextuais.

Em termos praticos, o modulo deve responder com clareza:

- como a operacao esta agora;
- onde agir hoje;
- quem nao bateu meta;
- por que nao bateu meta;
- quem ainda nao justificou;
- quais regionais ou supervisores estao piorando;
- quais dados precisam ser exportados para estudos, BI ou IA.

## 4. Principios da evolucao

- evolucao incremental sobre a base existente;
- regra de negocio no backend e nao na interface;
- visoes diferentes sobre a mesma fonte de verdade;
- foco em gestao por excecao, nao apenas consulta historica;
- exportacao analitica segura e auditavel;
- desempenho adequado para consultas diarias e recorrentes;
- componentes reutilizaveis e aderentes ao padrao visual existente;
- permissao obrigatoria no backend para qualquer visao sensivel.

## 5. Problema de negocio a resolver

Hoje o calendario e util como apoio visual, mas nao resolve sozinho a necessidade da matriz e da gerencia operacional. A gestao precisa identificar rapidamente:

- colaborador abaixo da meta no dia;
- supervisor que ainda nao comentou o desvio;
- regional com piora recorrente;
- causa predominante dos desvios;
- reincidencia de baixa performance;
- relacao entre volume, capacidade, deslocamento, SLA e meta.

Sem essa camada, a operacao depende de leitura manual, perde agilidade e reduz a capacidade de acao no mesmo dia.

## 6. Estrutura alvo do modulo

O modulo deve ficar organizado em cinco camadas complementares.

### 6.1. Camada transacional operacional

Responsavel por receber, importar, consolidar e disponibilizar os dados brutos operacionais:

- O.S. abertas, em andamento e fechadas;
- tempos operacionais;
- responsavel e regional;
- assuntos, tipos e setores;
- status e SLA;
- dados de jornada, modelo e meta.

### 6.2. Camada de gestao por excecao

Responsavel por mostrar o que foge do esperado:

- abaixo da meta;
- backlog vencido;
- volume acima da capacidade;
- supervisor com pendencia;
- reincidencia por colaborador;
- regional em atencao.

### 6.3. Camada executiva

Responsavel pela leitura sintetica para matriz e gerencia:

- situacao geral do dia;
- principais alertas;
- comparativos contra ontem e ultimos dias;
- ranking de risco;
- indicadores de disciplina operacional.

### 6.4. Camada analitica

Responsavel por consolidar fatos, snapshots, indicadores derivados e exportacoes:

- fatos diarios;
- fatos mensais;
- agregados por supervisor e regional;
- indicadores historicos;
- datasets para BI e IA.

### 6.5. Camada de inteligencia assistida

Responsavel por alimentar consultas em modelos de chat/IA com dados estruturados e contexto suficiente para respostas mais confiaveis:

- exportacoes JSON ou tabelas resumidas;
- snapshots textuais;
- indicadores derivados;
- contexto de causas e justificativas.

## 7. Evolucao funcional recomendada

## 7.1. Painel de excecoes do dia

Nova visao centrada em quem exige acao imediata.

Objetivo:

- permitir que matriz, gerencia e lideranca vejam rapidamente quem esta abaixo da meta e o que ainda depende de tratativa.

Itens esperados:

- colaborador;
- regional;
- supervisor;
- meta do dia;
- realizado do dia;
- diferenca;
- status da justificativa;
- motivo informado;
- horario da ultima atualizacao;
- reincidencia recente.

Filtros esperados:

- data;
- regional;
- supervisor;
- colaborador;
- modelo de equipe;
- status da justificativa;
- reincidencia;
- faixa de desvio.

## 7.2. Justificativa obrigatoria da supervisao

Quando o colaborador nao bater a meta diaria, o supervisor deve registrar uma justificativa obrigatoria.

Campos recomendados:

- data de referencia;
- colaborador;
- supervisor responsavel;
- regional;
- meta esperada;
- realizado;
- diferenca;
- motivo padronizado;
- observacao livre;
- status da justificativa;
- criado em;
- atualizado em.

Motivos padronizados sugeridos:

- falta;
- atestado;
- baixa demanda;
- deslocamento elevado;
- apoio em outra regional;
- treinamento;
- problema sistemico;
- bloqueio operacional;
- improdutividade;
- outro.

Regras recomendadas:

- a obrigatoriedade so vale quando existir meta valida para o dia;
- supervisor so pode justificar equipe sob sua responsabilidade;
- matriz e gerencia podem consultar tudo;
- alteracoes devem ficar auditadas;
- justificativas em atraso devem aparecer em destaque;
- fechamento gerencial do dia pode considerar pendencias em aberto.

## 7.3. Consolidado mensal de meta e disciplina

O modulo deve permitir uma leitura mensal por colaborador, supervisor e regional.

Indicadores recomendados:

- meta mensal;
- realizado mensal;
- dias abaixo da meta;
- dias com justificativa;
- dias sem justificativa;
- percentual de justificativa no prazo;
- reincidencia em 7, 15 e 30 dias;
- principal causa dos desvios;
- comparativo entre equipes e regionais.

## 7.4. Painel da matriz

Essa visao deve priorizar decisao rapida.

Blocos recomendados:

- situacao operacional do dia;
- colaboradores abaixo da meta;
- supervisores com pendencia;
- regionais em atencao;
- backlog vencido;
- principais causas dos desvios;
- tendencia de melhora ou piora nos ultimos dias.

## 7.5. Painel de gestao da supervisao

Foco em disciplina de acompanhamento.

Indicadores recomendados:

- quantidade de colaboradores abaixo da meta por supervisor;
- quantidade de justificativas pendentes;
- taxa de justificativa no prazo;
- equipe com maior reincidencia;
- media de desvio por colaborador;
- regional atendida;
- historico de acompanhamento.

## 7.6. Painel de causas operacionais

Foco em explicar o desvio, nao apenas aponta-lo.

Indicadores recomendados:

- distribuicao de motivos de justificativa;
- relacao entre deslocamento e baixa performance;
- impacto de apoio cruzado entre regionais;
- relacao entre volume do dia e meta nao atingida;
- principais causas por regional;
- principais causas por supervisor;
- tendencia semanal e mensal das causas.

## 8. Novos cards recomendados para a visao geral

Os cards da visao geral devem responder "o que aconteceu", "qual o risco" e "o que fazer".

### 8.1. Abaixo da meta hoje

- quantidade de colaboradores abaixo da meta;
- variacao versus ontem;
- clique para abrir lista detalhada.

### 8.2. Pendencias de justificativa

- total de justificativas obrigatorias ainda nao preenchidas;
- destaque de supervisor e regional.

### 8.3. Backlog vencido

- total de O.S. vencidas;
- tendencia nos ultimos dias;
- abertura do detalhamento.

### 8.4. Risco operacional

- score consolidado de risco do dia;
- semaforo verde, amarelo e vermelho;
- abertura para entender composicao do score.

### 8.5. Regionais em atencao

- quantidade de regionais com piora recente;
- criterio baseado em persistencia e tendencia.

### 8.6. SLA do dia

- taxa do dia;
- diferenca contra media recente;
- alertas de queda.

### 8.7. Reincidencia de baixa performance

- quantidade de colaboradores que repetiram baixa performance em janelas curtas;
- acesso rapido ao historico.

### 8.8. Eficiencia da supervisao

- taxa de justificativas no prazo;
- taxa de acompanhamento da equipe;
- visao comparativa entre supervisores.

### 8.9. Capacidade versus demanda

- chegaram mais O.S. do que a operacao absorveu?;
- leitura simples da pressao operacional.

### 8.10. Apoio cruzado entre regionais

- quantidade de atendimentos fora da regional de origem;
- dado importante para contextualizar desvios de meta.

## 9. Base analitica para exportacao e IA

O uso de modelo de chat/IA exige mais do que exportar planilhas soltas. E necessario uma base analitica estruturada e consistente.

### 9.1. Objetivos da base analitica

- exportar dados confiaveis para analise manual, BI e IA;
- reduzir dependencia de consultas operacionais pesadas;
- manter contexto suficiente para interpretacao dos desvios;
- permitir reprocessamento e historico;
- separar dado bruto, dado consolidado e indicador derivado.

### 9.2. Datasets recomendados

#### a) fato_operacao_diaria

Granularidade:

- um colaborador por dia.

Campos recomendados:

- data;
- regional;
- supervisor;
- colaborador;
- modelo de equipe;
- meta_dia;
- realizado_dia;
- bateu_meta;
- diferenca_meta;
- quantidade_os;
- sla_dia;
- tempo_medio_execucao;
- deslocamento_medio;
- apoio_outra_regional;
- justificativa_status;
- justificativa_motivo;
- score_risco_dia.

#### b) fato_operacao_mensal

Granularidade:

- um colaborador por mes.

Campos recomendados:

- competencia;
- regional;
- supervisor;
- colaborador;
- meta_mes;
- realizado_mes;
- dias_abaixo_meta;
- dias_com_justificativa;
- dias_sem_justificativa;
- taxa_justificativa_no_prazo;
- reincidencia_score;
- produtividade_media;
- sla_medio.

#### c) fato_supervisao

Granularidade:

- um supervisor por periodo.

Campos recomendados:

- periodo;
- supervisor;
- regional;
- total_colaboradores;
- qtd_abaixo_meta;
- qtd_pendencias_justificativa;
- taxa_justificativa_no_prazo;
- reincidencia_media_equipe;
- score_disciplina_supervisao.

#### d) fato_regional

Granularidade:

- uma regional por periodo.

Campos recomendados:

- periodo;
- regional;
- volume;
- backlog;
- backlog_vencido;
- sla;
- aderencia_meta;
- tendencia_7_dias;
- tendencia_30_dias;
- principais_causas;
- score_risco_operacional.

#### e) dimensao_eventos_operacionais

Granularidade:

- um evento por data e escopo.

Campos recomendados:

- data;
- regional;
- tipo_evento;
- descricao;
- severidade;
- origem;
- observacao.

Eventos tipicos:

- feriado;
- chuva forte;
- indisponibilidade sistemica;
- falta de equipe;
- pico de demanda;
- acao especial;
- mudanca operacional.

### 9.3. Formatos de exportacao recomendados

- CSV para analise tabular;
- XLSX para uso operacional e compartilhamento;
- JSON estruturado para integracao com chat/IA;
- snapshot textual resumido para contextualizacao rapida.

### 9.4. Exportacoes pensadas para IA

Para modelos de chat, o ideal e oferecer:

- dados agregados por periodo;
- top desvios;
- causas consolidadas;
- rankings de risco;
- comparativos versus periodo anterior;
- texto sintetico por dia, semana e mes.

Exemplo de snapshot textual:

"Em 23/07/2026, 14 colaboradores ficaram abaixo da meta. A regional X concentrou 41% dos desvios. O principal motivo informado foi deslocamento elevado. Tres supervisores encerraram o dia com pendencias de justificativa."

Esse formato nao substitui o dado bruto, mas melhora muito a qualidade de respostas em IA.

## 10. Indicadores derivados recomendados

Para suportar analise executiva e IA, alguns scores e indicadores derivados sao recomendados:

- tendencia_7_dias;
- tendencia_30_dias;
- risco_operacional_score;
- reincidencia_score;
- disciplina_supervisao_score;
- estabilidade_regional_score;
- eficiencia_deslocamento_score;
- aderencia_meta_score;
- pressao_operacional_score.

Esses indicadores devem ser documentados e calculados no backend, nunca inferidos apenas na interface.

## 11. Permissoes e seguranca

Toda evolucao deve manter e ampliar a seguranca ja adotada no projeto.

Diretrizes:

- permissao validada no backend;
- supervisor acessa apenas sua equipe ou escopo permitido;
- regional acessa apenas sua abrangencia;
- matriz e gerencia acessam visao consolidada conforme perfil;
- exportacao de dados deve ter permissao propria;
- justificativas e alteracoes precisam de trilha de auditoria;
- logs nao devem expor dados sensiveis desnecessarios;
- nenhuma regra critica depende apenas de validacao visual da tela.

Permissoes futuras recomendadas:

- `operations:view_exceptions`
- `operations:justify_team_results`
- `operations:view_supervision`
- `operations:export_analytics`
- `operations:view_executive_panel`

## 12. Recomendacoes de arquitetura

### 12.1. Fluxo desejado

Tela -> API -> validacao -> autenticacao -> permissao -> service -> banco -> resposta tratada

### 12.2. Recomendacoes tecnicas

- manter regras de meta, justificativa e consolidacao no backend;
- usar snapshots ou fatos consolidados para consultas executivas pesadas;
- preservar o calendario como apoio visual, nao como centro unico da gestao;
- evitar consultas on demand excessivamente custosas para cards executivos;
- separar claramente:
  - dado operacional bruto;
  - dado consolidado diario;
  - dado consolidado mensal;
  - dado exportavel para IA.

### 12.3. Recomendacoes de banco

Quando a implementacao comecar, considerar criacao de entidades ou snapshots equivalentes a:

- daily_goal_snapshot;
- daily_goal_exception;
- daily_supervisor_justification;
- monthly_goal_summary;
- analytics_export_snapshot.

Campos de auditoria recomendados:

- created_at;
- updated_at;
- created_by;
- updated_by;
- reason_change, quando houver alteracao relevante.

## 13. Recomendacoes de UX e layout

Toda nova tela deve preservar o padrao visual atual do sistema.

Pontos obrigatorios:

- cabecalho e navegacao consistentes;
- cards executivos com leitura simples;
- tabelas com drill down claro;
- filtros padronizados;
- estados de loading, vazio e erro;
- responsividade desktop, tablet e mobile;
- linguagem direta para matriz, supervisor e analista;
- destaque visual forte para pendencias e riscos.

Recomendacao de organizacao visual:

- topo com cards executivos;
- bloco central com excecoes e alertas;
- bloco analitico com tendencias e causas;
- area de detalhamento para tabelas e exportacao.

## 14. Roadmap proposto

### Fase 1 - Base analitica consolidada

Objetivo:

- organizar fatos diarios, mensais e por supervisao;
- preparar exportacao segura e performatica.

Entregas:

- definicao dos datasets;
- snapshots diarios;
- endpoint ou rotina de exportacao;
- indices e ajustes de consulta.

### Fase 2 - Gestao por excecao

Objetivo:

- identificar e expor quem nao bateu meta e o que requer acao no dia.

Entregas:

- painel de excecoes;
- status de justificativa;
- filtros dedicados;
- destaque de reincidencia.

### Fase 3 - Justificativa obrigatoria da supervisao

Objetivo:

- formalizar acompanhamento e disciplina gerencial.

Entregas:

- cadastro de justificativa;
- motivos padronizados;
- auditoria;
- pendencias por supervisor e regional.

### Fase 4 - Visao executiva integrada

Objetivo:

- melhorar a visao geral com cards, scores e leitura orientada a decisao.

Entregas:

- novos cards;
- score de risco;
- ranking de regionais e supervisores;
- painel da matriz.

### Fase 5 - Preparacao para IA e inteligencia assistida

Objetivo:

- permitir exportacao e uso confiavel por chat/IA.

Entregas:

- JSON estruturado;
- snapshots textuais;
- indicadores derivados;
- documentacao de consumo dos dados.

## 15. Ganhos esperados

Com a evolucao proposta, o modulo operacional tende a gerar ganhos em:

- velocidade de leitura da operacao;
- capacidade de acao no mesmo dia;
- disciplina da supervisao;
- visibilidade da matriz sobre regionais;
- rastreabilidade dos desvios;
- qualidade da analise historica;
- preparo para BI e IA;
- integracao entre operacao, gestao e inteligencia.

## 16. Riscos e mitigacoes

### Risco: excesso de visual sem ganho real

Mitigacao:

- cada card e painel deve responder claramente qual acao ele habilita.

### Risco: performance ruim em consultas executivas

Mitigacao:

- usar snapshots e consolidacoes, com indices adequados.

### Risco: justificativa virar texto solto sem padrao

Mitigacao:

- motivo estruturado + observacao livre + auditoria.

### Risco: IA responder mal por falta de contexto

Mitigacao:

- incluir causas, agregados, eventos operacionais e snapshots textuais.

### Risco: sobreposicao de permissao

Mitigacao:

- validar escopo sempre no backend e revisar matriz de acesso.

## 17. Direcao recomendada

A direcao recomendada para o modulo operacional e:

- manter o calendario como ferramenta de apoio;
- transformar a visao geral em cockpit executivo;
- colocar excecoes e justificativas no centro da rotina de acompanhamento;
- criar uma base analitica formal para exportacao;
- preparar o modulo para consumo por chat/IA com contexto suficiente;
- evoluir por fases, com impacto controlado e arquitetura limpa.

## 18. Proximos passos sugeridos

Antes da implementacao, e recomendado fechar:

1. lista oficial de indicadores do modulo;
2. definicao exata dos cards executivos;
3. regra oficial de meta diaria e mensal;
4. regra oficial de obrigatoriedade e prazo da justificativa;
5. desenho final dos datasets de exportacao;
6. ordem de execucao das fases no backlog tecnico.

Com isso, o projeto fica preparado para evoluir o modulo operacional sem perder coerencia, seguranca e capacidade de manutencao.
