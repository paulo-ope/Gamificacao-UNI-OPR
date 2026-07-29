# Mapa funcional — Módulo Operação Analítica

> Documento de referência descrevendo **o que existe hoje**, aba por aba, função por função. Complementa o PRD original (`prd_modulo_operacao_analitica.md`, que descreve a intenção/planejamento) com o estado real e atual do módulo, incluindo tudo que foi ajustado/corrigido/adicionado nas últimas sessões de desenvolvimento.
>
> Módulo acessível em `/operacao`, dentro do UNI Workspace. Todas as telas dependem de um usuário autenticado com a permissão `operations:read`.

---

## 1. Estrutura geral

O módulo é organizado em abas, acessíveis pelo menu lateral (ícone de hambúrguer no topo):

| Aba | Permissão mínima | O que responde |
|---|---|---|
| Visão Geral | `operations:read` | "Como está a operação como um todo, agora?" |
| Aberturas | `operations:read` | "Quanta demanda está entrando, de onde, e isso é normal?" |
| SLA | `operations:view_sla` | "O que já foi resolvido, no prazo ou fora?" |
| Calendário | `operations:view_calendar` | "Quem produziu o quê, dia a dia, no mês?" |
| Andamento | `operations:view_backlog` | "O que ainda está pendente, e o que está em risco?" |
| Detalhes de O.S. | `operations:view_order_details` | Lista crua de O.S., para investigação pontual. |
| Configurações | `operations:manage_team_models` / `operations:manage_subjects` | Cadastro de modelos de equipe, metas e mapeamento de assuntos. |

Um mesmo conjunto de filtros (período, regional, modelo de equipe, tipo, assunto, responsável, e um painel de "Filtros avançados") fica fixo no topo e é compartilhado pela maioria das abas — com duas exceções documentadas: **Aberturas** ignora o filtro de Responsável/Modelo de equipe para a contagem de entradas (a O.S. ainda não tem um técnico atribuído no momento em que é aberta), e **Andamento** ignora as datas (é sempre "o estoque de hoje", não um recorte por período de abertura).

---

## 2. Visão Geral

Primeira tela ao entrar no módulo. Dá um resumo executivo de tudo, sem exigir nenhum clique.

**Cards do topo (4):**
- **Abertas no período** — quantidade de O.S. abertas no recorte de datas selecionado, com média diária. Se houver filtro de responsável ativo, mostra também quantas dessas aberturas estão hoje associadas a esse grupo (sem tratar isso como "quem abriu", já que a O.S. nasce sem técnico).
- **Finalizadas no período** — quantidade fechada no recorte, pela data de fechamento (não de abertura).
- **Backlog atual** — estoque de O.S. ainda em andamento na consulta, com quantas já estão atrasadas.
- **SLA de finalização** — percentual no prazo entre as O.S. finalizadas e mensuráveis (fórmula: no prazo ÷ mensuráveis). Cor: verde ≥80%, amarelo entre 60–80%, vermelho <60%.

**Painel de tempo médio:** tempo médio do ciclo completo (abertura → finalização) e tempo médio até o primeiro atendimento em campo (abertura → início do deslocamento). Se o tempo de espera até o deslocamento passar de 50% do ciclo total, aparece um aviso de gargalo destacado.

**Conformidade de jornada:** compara quantas finalizações aconteceram fora da janela de horário configurada para o modelo de equipe do responsável (ver Configurações) contra quantas ficaram dentro. Um botão "Ver detalhes" abre um filtro por modelo de equipe para esse recorte específico.

**Produção por equipe/modelo:** gráfico de barras comparando o volume finalizado por modelo de equipe, com destaque para o quanto ficou fora da jornada configurada.

**Evolução operacional (3 gráficos, com toggle Dia/Semana/Mês):**
1. **SLA operacional** — linha contínua de SLA acumulado ponderado + linha tracejada de SLA por agrupamento, com meta visual de 80%.
2. **Entrada x saída** — aberturas, finalizações e saldo por dia/semana/mês.
3. **Produção por equipe** — mesmo gráfico de produção acima, mas na série temporal completa.

**Monitor preventivo** ("A demanda está saindo do controle?") — painel colapsável (clique em "Ver situação"). Quando aberto, mostra:
- Um badge de status (Normal / Atenção / Crítico / Histórico insuficiente) com uma frase de leitura direta e uma **lista explícita dos motivos** que levaram a esse status (ex.: "Aberturas 150% acima do esperado", "Entrando 1,2x mais O.S. do que a equipe está finalizando", "53% do backlog já está vencido"). Isso existe porque a classificação combina até 8 condições diferentes (persistência de dias fora do padrão, desvio percentual, pressão de entrada vs. saída, taxa de vencidos) — sem a lista de motivos, o usuário via só o resultado final sem entender por quê.
- 6 métricas: aberturas recentes, balanço operacional (aberturas − finalizadas), estoque aberto, quantos assuntos exigem atenção, índice entradas/saídas, e idade média do backlog.
- A tabela **"Onde agir"**: ranking de assuntos com pior situação, expansível por clique em cascata (Assunto → Regional → Cidade → Setor → Responsável), cada nível carregado sob demanda. Cada linha também mostra seus próprios motivos — inclusive um aviso específico quando o alerta aparece no total agregado mas "desaparece" ao abrir cada filho, porque o volume individual de cada recorte é pequeno demais para acionar o mesmo limite mínimo (o alerta exige pelo menos 3 O.S. recentes por recorte para considerar o desvio significativo).
- Um "Ver O.S." em cada linha, que abre a lista real de ordens daquele recorte na aba Detalhes.
- Um `<details>` no rodapé explicando a fórmula completa (comparação com o mesmo dia da semana nas últimas 8 semanas, condições de crítico vs. atenção).

O cálculo do "esperado" usado tanto no Monitor Preventivo quanto na aba Aberturas é sempre o mesmo: pega o mesmo dia da semana nas últimas 8 semanas e tira a média — isso evita comparar, por exemplo, um sábado com uma terça-feira comum.

---

## 3. Aberturas

Aba dedicada a entender a **demanda que está entrando**, independente de quem vai atender.

**Regra de negócio central:** todas as contagens de "abertas" nesta aba ignoram o filtro de Responsável e de Modelo de equipe — a O.S. nasce sem técnico atribuído, então filtrar por responsável não faz sentido para medir entrada. Já a linha "Finalizadas" e o cálculo de backlog **respeitam** esses filtros normalmente (uma O.S. finalizada tem um responsável real e conhecido).

**4 cards de métrica:**
- **Abertas no período** — total e média diária.
- **Desvio esperado** — quanto o volume do período ficou acima/abaixo da média estatística do mesmo dia da semana nas últimas 8 semanas.
- **Pressão operacional** — razão abertas/finalizadas (ex.: 1,25x significa que entra 25% mais do que sai), com o saldo líquido (abertas − finalizadas) mostrado ao lado.
- **Backlog no recorte** — estoque em aberto, com quantas estão vencidas e quantas sem responsável.

**Gráfico "Fluxo operacional"** (Aberturas, finalizações e backlog):
- 4 séries: Abertas (barra), Finalizadas (linha), Backlog (linha), Esperado (linha tracejada, baseline estatístico).
- Uma linha de média tracejada (calculada sobre o período visível).
- Toggle Dia / Semana / Mês (agrega a mesma série diária em blocos semanais ou mensais; o backlog, por ser um estoque e não algo somável, sempre mostra o valor do último dia do bloco, não a soma).
- **Clique numa barra** abre um filtro temporário só daquele recorte de data — o gráfico, os rankings e o resto da aba passam a refletir apenas aquele dia/semana/mês, sem alterar o filtro principal da tela. Clicar na mesma barra de novo, ou clicar fora do gráfico, desfaz e volta ao período completo.

**Painel "Leitura rápida" / Insights da gestão:** até 6 alertas automáticos com severidade (normal/atenção/crítico/insuficiente), como "O.S. sem responsável" ou "Maior origem de demanda", mais o tempo médio até a primeira ação (abertura → primeira de: assumir, deslocar ou executar).

**Mapa de calor de abertura:** matriz dia-da-semana × hora-do-dia mostrando em que momentos a demanda nasce com mais força. **Clique numa célula** abre inline a lista de O.S. daquele dia da semana + horário específico (mesmo padrão de toggle do gráfico acima).

**Envelhecimento do backlog gerado:** 4 barras (0-1 dia, 2-3 dias, 4-7 dias, 8+ dias) mostrando quantas das O.S. abertas no período seguem sem fechamento, com linha de média. **Clique numa barra** abre inline a lista de O.S. daquela faixa de idade.

**10 rankings** (cada um em formato de lista compacta, mostrando os 6 primeiros com "Mostrar mais N", ordenável por Abertas/Em aberto/Share, com clique em qualquer linha abrindo inline a lista de O.S. daquele grupo): Filiais, Cidades, Assuntos, Tipos, Setores, Prioridades, Criadores, POPs, Tipos de contrato, Tipos de pessoa.
- "Em aberto" nos rankings é o estoque atual daquele grupo (quantas ainda não fecharam) — diferente do "Saldo" mostrado no card de Pressão operacional (que é uma diferença abertas−finalizadas, não um estoque).

**Painel de detalhamento (drill-through) inline:** qualquer um dos pontos de clique acima (barra do gráfico, célula do mapa de calor, barra de envelhecimento, linha de ranking) abre um painel na própria aba — sem trocar de tela — com uma tabela das O.S. correspondentes (O.S., cliente, responsável, abertura, status) e um botão "Fechar" explícito. Clicar de novo no mesmo ponto fecha o painel (efeito de alternância).

---

## 4. Andamento

Aba dedicada ao **estoque atual** de O.S. ainda abertas — por isso ignora completamente o filtro de datas (o objetivo é "o que está pendente agora", não "o que abriu neste mês").

Banner no topo com botão "Atualizar abertas no IXC" (permissão de sincronização) para forçar uma nova consulta do backlog direto no IXC.

**6 cards de repartição** (listas compactas com "Mostrar mais", mesmo padrão da aba Aberturas):
- **Filial** e **Cidade** — dois ângulos da mesma composição geográfica (uma filial pode abranger mais de uma cidade administrativamente; ver observação sobre desmembramento abaixo).
- **Tipo geral** e **Assunto**.
- **SLA / Status**.
- **SLA em risco (backlog)** — 5 faixas (Vencido 100%+, Crítico 80-99%, Atenção 50-79%, Tranquilo <50%, Sem meta definida) calculadas por quanto do prazo de SLA já foi consumido em cada O.S. ainda aberta. Diferente do SLA da aba SLA (que só sabe dizer "venceu" depois que já venceu), este é **preditivo** — mostra o risco antes de estourar o prazo.

**Clique em qualquer linha de qualquer card** abre inline, na própria aba, um painel com a lista de O.S. daquele recorte (colunas: O.S., cliente, filial/cidade, assunto, responsável, abertura, status). Clicar de novo na mesma linha fecha o painel.

**Observação sobre "Filial":** três filiais do IXC (São Francisco do Guaporé, São Miguel do Guaporé e Seringueiras) eram tratadas como uma única regional agregada por decisão de negócio anterior; isso foi desfeito — hoje cada uma aparece separada, tanto no card "Filial" quanto no card "Cidade", e o histórico já sincronizado foi corrigido retroativamente para refletir isso.

---

## 5. SLA

Aba dedicada ao que **já aconteceu**: O.S. finalizadas, no prazo ou não. Só aparece para quem tem a permissão `operations:view_sla`. Não tem cartões numéricos próprios (o indicador-resumo de SLA geral do período já aparece na Visão Geral, calculado da mesma forma descrita abaixo) — são duas tabelas.

**Como o SLA é calculado (regra central, vale para toda a aba):** cada O.S. recebe, na sincronização com o IXC, um status de SLA: **"No prazo"** (tempo entre abertura e fechamento ≤ meta de horas cadastrada para o assunto), **"Fora do prazo"** (excedeu a meta) ou **"Não identificado"** (assunto sem meta cadastrada — essas O.S. não entram no cálculo). A fórmula usada em qualquer badge de SLA da tela é sempre:

```
Taxa de SLA = (O.S. no prazo) ÷ (O.S. no prazo + O.S. fora do prazo) × 100
```

Cores: verde ≥80%, amarelo 60–80%, vermelho <60%, cinza "—" quando não há O.S. mensurável no recorte.

**Tabela "SLA por hierarquia":** agrupa o desempenho por **Tipo geral → Assunto → Diagnóstico**, com cada linha expansível revelando o próximo nível (carregado sob demanda). Um seletor no cabeçalho troca a visão raiz entre Tipo geral / Assunto / Diagnóstico. Colunas de cada linha:
- **Realizadas** — quantidade fechada no período, naquele grupo.
- **SLA técnico** — a taxa de SLA do grupo.
- **Até 12h / 12–24h / 24–48h / 48–72h / Após 72h** — distribuição percentual do tempo total (abertura→fechamento) das O.S. daquele grupo em faixas de horas (aqui o critério é ter datas válidas, não depende de ter meta cadastrada — por isso o total dessas 5 colunas pode não bater exatamente com o total usado na Taxa de SLA).
- **T.M. fech. (h)** — tempo médio de fechamento (abertura→fechamento) das O.S. mensuráveis do grupo.
- Ordenar por cabeçalho, Ctrl/Cmd+clique cria um realce visual temporário (só marca a linha, não filtra), "Modo foco" expande em tela cheia, e uma linha "Total ponderado" soma tudo no final.

**Tabela "Produtividade e SLA por colaborador":** agrupada por Regional, expansível por técnico. Colunas:
- **Tipos de O.S.** (até 6 colunas dinâmicas + "Demais tipos") — quantidade por tipo que aquele colaborador fechou.
- **Realizadas**, **SLA** (mesma fórmula, agora só das O.S. daquele colaborador), **Dias** (dias distintos com pelo menos 1 fechamento), **Média/dia** (Realizadas ÷ Dias).
- **Aderência agenda** — compara o horário agendado ao cliente com o horário real de início do atendimento (início do deslocamento, ou da execução se não houver deslocamento registrado); considera "dentro" quando o desvio é de até 60 minutos. Só entram O.S. com agendamento registrado — sem isso, mostra "Sem agenda".
- **Exec. mensuráveis**, **Execução média/mín./máx.** — tempo de execução em campo, estritamente do início da execução até a finalização (não inclui deslocamento nem espera na fila).

---

## 6. Calendário

Calendário de produção mensal por competência, organizado em blocos por regional — uma linha por colaborador, uma coluna por dia do mês. Só aparece para quem tem `operations:view_calendar`.

**Agrupamento:** "Por filial" (cada regional isolada, só a produção atendida naquela filial) ou "Por colaborador" (um bloco único, somando toda produção do técnico mesmo em apoio a outras regionais — nesse modo o sistema registra qual é a "filial de referência" do colaborador, pra depois contar quanto ele atendeu fora dela).

**Estrutura da grade:** cabeçalho com os dias agrupados por semana (+ total semanal), coluna fixa "TOTAL O.S." no fim com o total do mês. Sábados/domingos com fundo diferente. Uma linha "Total" soma todos os colaboradores por dia/semana/mês (também clicável). Cada linha de colaborador mostra o modelo de equipe vinculado e a meta diária (ou "Sem modelo de equipe"). Dias fora do período liberado aparecem bloqueados.

**O que o número da célula representa:** contagem de O.S. **finalizadas** cuja data/hora de **fechamento** cai naquele dia (fuso Porto Velho) — não é abertura nem agendamento.

**Cor da célula (classificação de desempenho):**
- **Sem produção** (cinza claro) — 0 no dia.
- **Sem meta configurada** (cinza neutro) — produção >0, mas colaborador sem modelo vinculado.
- **Abaixo da meta** (vermelho) — menor que o limiar "mediano".
- **Mediano** (amarelo) — entre "mediano" e "bom".
- **Bom** (verde) — entre "bom" e a meta cheia.
- **Excelente** (azul) — igual ou acima da meta diária.
As cores exatas (hex) são configuráveis por modelo de equipe.

**Como as metas são configuradas:** cada colaborador é vinculado a um **Modelo de Equipe**, que carrega uma meta diária padrão e limiares "mediano"/"bom". Além do padrão, cada modelo pode ter regras específicas por tipo de dia (dia de semana, sábado, domingo, mensal), cada uma com sua própria meta e limiares, um interruptor de ativo/inativo (regra desativada = "sem meta" nesse tipo de dia, célula fica neutra) e, opcionalmente, um horário de expediente (usado no painel "Conformidade de jornada" da Visão Geral).

**Drawer de detalhe** (clique em qualquer célula, total semanal ou total mensal): mostra cabeçalho de contexto (filial, período, quantidade, cor de desempenho), um painel de indicadores (tempo ativo total, tempo de atendimento médio, tempo de deslocamento médio, taxa de SLA do recorte, janela operacional, quantas filiais atendidas e quanto foi "apoio" fora da filial de referência, repartição por tipo) e a lista de O.S. daquele recorte (código, cliente, contrato, tipo/assunto, filial/cidade, datas, endereço, observações) — clicável para abrir o detalhe completo. No detalhe mensal, soma-se ainda a repartição por filial do mês.

---

## 7. Detalhes de O.S.

Tabela crua de ordens de serviço, para investigação pontual. Permissão `operations:view_order_details`.

**Colunas:** O.S. (+ protocolo), Contrato/Cliente, Filial, Tipo/Assunto, Responsável, Abertura, Fechamento, Status, SLA (selo No prazo/Atrasada + horas).

**Ordenação:** clique no cabeçalho ordena (decrescente primeiro, alterna a cada clique) — e cobre **todo o conjunto filtrado**, não só as 50 linhas visíveis na página atual.

**Filtro rápido (Ctrl/Cmd + clique numa célula):** cria um realce visual temporário nas linhas com aquele mesmo valor — é só uma marcação em tela, não refaz a consulta ao servidor. Clicar de novo ou fora da tabela remove.

**Busca:** campo de texto (contrato, cliente ou O.S.), disparado ao pressionar Enter.

**Paginação:** 50 registros por página.

**Clique numa linha** abre um modal com a O.S. completa: selos de status/SLA, linha do tempo (Abertura → Agendada → Deslocamento → Execução → Finalização), os 4 tempos calculados (espera, deslocamento, atendimento, ciclo total), dados cadastrais completos, meta de SLA e prazo-limite, e observações/relatos do IXC.

**Escopo automático da tela (não é um botão, o sistema decide):** por padrão busca pelo período normal com os filtros do painel. Quando o usuário chega via um alerta do Monitor Preventivo (Visão Geral), a tela troca automaticamente pra um escopo restrito aos dias analisados pelo alerta, preservando o caminho clicado (assunto/regional/cidade/setor/responsável) — um aviso no topo do card avisa essa diferença.

---

## 8. Painel de filtros (comum à maioria das abas)

**Período:** calendário duplo (dois meses lado a lado), atalhos "Mês atual" e "Ano até hoje".

**Filtros principais:** Regional, Modelo de equipe, Tipo geral, Assunto, Responsável — todos multi-seleção com busca.

**Botões:** Filtrar (aplica e recarrega), Limpar (volta ao mês atual + setores padrão), Filtros avançados (expande o painel abaixo, com contador de quantos estão ativos), Visões (visões salvas).

**Filtros avançados**, por grupo: **Localização** (Empresa/filial, UF, Cidade); **Ordem de serviço** (Status, Prioridade, Diagnóstico); **Cliente** (Tipo de pessoa, Tipo de contrato); **Operação** (Departamento, Setor, Criador, Projeto, POP, + seletor "Todas as O.S. / Somente finalizadas"); **SLA** (situação do SLA, horário de fechamento de/até); **Dia da semana** (de abertura e de fechamento, cada um multi-seleção); **Janela personalizada** (recorte contínuo de dia+hora, ex.: sábado 12h a domingo 23h59, aplicável sobre abertura e/ou fechamento — ignora o filtro de Setor; no Calendário, que sempre agrupa por fechamento, só funciona de fato se a janela usar "Fechamento" como base).

**Opções dependentes (facetadas):** as opções de cada filtro (regionais, cidades, assuntos etc.) já vêm do backend recalculadas conforme o contexto atual selecionado — um grupo só aparece se tiver opções disponíveis. Esse recálculo só acontece quando o usuário aplica o filtro (clique em "Filtrar" ou ao escolher uma visão salva).

**Visões salvas:** combinações reutilizáveis de filtros, marcadas como Pessoal ou Global. Qualquer usuário com `operations:manage_filters` pode salvar/renomear/excluir; criar uma visão **Global** exige a permissão adicional `operations:views:create_global` (sem ela, a opção fica desabilitada).

**Sincronização com o IXC:** visível só para quem tem `operations:sync_ixc`. Botão "Sincronizar dados" importa o período selecionado (em lotes diários; períodos maiores que 7 dias rodam como importação histórica em segundo plano, com progresso "X/Y dias"). Mostra também o escopo de setores configurado e a data/hora da última sincronização bem-sucedida.

---

## 9. Configurações

Só aparece no menu para quem tem `operations:manage_team_models`, `operations:manage_subjects` ou `operations:sync_ixc`. Quatro blocos, cada um com seu próprio controle de acesso:

**9.1 Modelos de equipe** — cadastro das metas de produtividade de um time: nome, meta diária, a partir de quantas O.S. o dia é "mediano" e "bom", 4 cores (abaixo/mediano/bom/excelente) e status ativo/inativo. Cada modelo pode ter regras específicas por tipo de dia (semana/sábado/domingo/mensal), cada uma com seus próprios limiares e, quando aplicável, horário de início/fim de jornada (usado no painel "Conformidade de jornada" da Visão Geral). Editável só com `operations:manage_team_models`.
- **Validações:** nome único e obrigatório; limiares precisam obedecer **1 &lt; mediano &lt; bom &lt; meta**, tanto no modelo geral quanto em cada regra por período (se violar, o sistema recusa com a mensagem "As faixas precisam respeitar a ordem: abaixo, mediano, bom e excelente/meta"); regra de período não-mensal habilitada exige horário de início e fim; não pode haver duas regras para o mesmo tipo de período no mesmo modelo; um modelo não pode ser excluído enquanto tiver colaboradores vinculados; cores precisam ser hexadecimal válido.

**9.2 Atribuição de responsável a modelo de equipe** — vincula cada colaborador (pelo nome como aparece nas O.S.) a um modelo de equipe, guardando a regional de origem mais recente conhecida (só como referência histórica — o modelo pertence ao colaborador, não à regional). Editável só com `operations:manage_team_models`. Só permite vincular a modelo ativo; um novo vínculo substitui o anterior.

**9.3 Mapeamento de assunto → tipo geral** — traduz o texto livre de "assunto" que vem do IXC para um "tipo geral" padronizado usado em filtros e relatórios. Editável só com `operations:manage_subjects` (permissão separada da gestão de modelos — dá pra administrar assuntos sem poder alterar metas de equipe, e vice-versa). Ao salvar, atualiza retroativamente as O.S. já importadas que tinham aquele assunto.

**9.4 Diretório de responsáveis** — define de onde vem a lista de "responsáveis" nos filtros: O.S. importadas ("orders"), cadastro de funcionários do IXC ("ixc"), ou os dois juntos ("both"). Trocar a fonte exige `operations:manage_team_models`. Existe uma ação de sincronizar a lista de funcionários direto do IXC — exige `operations:sync_ixc`, mas na prática o sistema também checa `operations:manage_team_models`, então só quem administra modelos de equipe consegue disparar essa sincronização.

---

## 10. Permissões e controle de acesso

**Permissões do módulo:**

| Permissão | O que libera |
|---|---|
| `operations:read` | Acessar o módulo (visão básica) |
| `operations:manage` | Administrar rotinas gerais (ex.: importações) |
| `operations:sync_ixc` | Sincronizar dados com o IXC |
| `operations:manage_filters` | Gerenciar visões/filtros salvos |
| `operations:views:read_global` / `create_global` / `update_global` / `delete_global` | Ver / criar / editar / excluir visões globais |
| `operations:manage_team_models` | Configurar modelos de equipe, metas, diretório de responsáveis e vínculos |
| `operations:manage_subjects` | Configurar mapeamento de assunto → tipo geral |
| `operations:view_order_details` | Ver detalhes de O.S. individuais |
| `operations:view_sla` | Ver a aba SLA |
| `operations:view_calendar` | Ver a aba Calendário |
| `operations:view_backlog` | Ver a aba Andamento |
| `operations:export` | Exportar dados |

**Matriz de papéis (perfis "de fábrica" — um admin pode montar combinações diferentes por usuário):**

| Papel | read | manage | sync_ixc | view_order_details | view_sla | view_calendar | view_backlog | manage_team_models | manage_subjects |
|---|---|---|---|---|---|---|---|---|---|
| Colaborador | — | — | — | — | — | — | — | — | — |
| Gestor Regional | ✔ | — | — | — | — | — | — | — | — |
| Leitor Operacional | ✔ | — | — | — | — | — | — | — | — |
| Operador | ✔ | ✔ | ✔ | ✔ | — | — | — | — | — |
| Admin | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |

Ou seja: hoje, só o **Admin** enxerga por padrão a configuração de modelos/assuntos, o SLA, o Calendário e o Andamento. **Operador** acessa o módulo, administra rotinas gerais e sincroniza o IXC, mas não vê SLA/Calendário/Andamento nem configura metas, por padrão. **Gestor Regional** e **Leitor Operacional** têm só leitura básica. **Colaborador** não tem nenhuma permissão deste módulo.

**Escopo regional do Gestor Regional:** cada usuário pode ter uma regional única (campo legado) e/ou uma lista de regionais. O sistema combina os dois, normaliza os nomes e aplica esse escopo **automaticamente em toda consulta**, independente do filtro que a tela manda — mesmo uma tentativa de forçar acesso a outra regional pela API é ignorada; só vale o escopo do próprio usuário. Se o usuário for Gestor Regional e não tiver nenhuma regional cadastrada, o sistema não libera "acesso a tudo" por padrão — retorna vazio, até que o cadastro seja feito.

---

## 11. Glossário de conceitos transversais

- **"Esperado" / baseline estatístico:** em qualquer gráfico que mostre uma linha "Esperado", o cálculo é sempre: pega o mesmo dia da semana nas últimas 8 semanas, tira a média, e usa o desvio padrão para definir um "limite de atenção" acima da média (o maior entre média+2×desvio, média×1,35 e média+2). Isso evita alarme falso por sazonalidade normal (ex.: segunda-feira sempre tem mais abertura que domingo).
- **Backlog / estoque:** contagem de O.S. ainda não fechadas num determinado corte de tempo. Não é somável entre dias (por isso os gráficos por semana/mês mostram o valor do último dia do período, não uma soma).
- **SLA (retroativo) vs. SLA em risco (preditivo):** a aba SLA mede o que já aconteceu (venceu ou não, depois do fato). O card "SLA em risco" da aba Andamento mede o quanto do prazo já foi consumido em O.S. **ainda abertas**, para agir antes do vencimento.
- **Drill-through inline vs. navegação:** desde a última rodada de ajustes, todo clique de detalhamento dentro de Aberturas e Andamento expande **na própria aba**, sem trocar de tela e sem alterar os filtros principais; clicar de novo no mesmo ponto desfaz.
- **Filiais desmembradas (São Francisco/São Miguel do Guaporé/Seringueiras):** o módulo de Operação já mostra essas três separadas (ver seção 4). Existe também uma integração à parte, de bônus por custo-por-km ("CPK"), que reaproveita o nome "São Francisco" só para casar com o formato de uma API externa — é um sistema diferente, fora do escopo deste módulo, e não foi alterado.
