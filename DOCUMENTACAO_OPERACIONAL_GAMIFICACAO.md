# Documentação Operacional da Gamificação

## 1. Objetivo do módulo

O módulo de Gamificação Operacional transforma as O.S realizadas em uma apuração de pontos auditável. Ele permite acompanhar produtividade, qualidade operacional, pontos anulados, investimento estimado, ranking de colaboradores, desempenho por regional e pendências de configuração antes do fechamento.

Na prática, a tela ajuda a responder perguntas como:

- Quais colaboradores mais pontuaram no período?
- Quais O.S foram pontuadas, anuladas ou ficaram sem regra?
- Quais regionais têm melhor saúde operacional?
- Quais assuntos e diagnósticos precisam de configuração?
- Quais pontos foram anulados e por qual motivo?

A lógica atual está implementada principalmente em:

- Importação da planilha: `backend/app/services/upvalue_importer.py`
- Normalização de SLA: `backend/app/services/sla.py`
- Cálculo e auditoria detalhada: `backend/app/services/scoring_detail.py`
- Geração do ranking e apuração: `backend/app/services/calculation.py`
- Dashboard: `backend/app/api/routes/dashboard.py`
- Tela principal: `frontend/app/gamificacao/page.tsx`

## 2. Visão geral do funcionamento

O fluxo começa com a importação da planilha de O.S do UpValue. O sistema lê as informações principais de cada linha, como colaborador responsável, regional, cliente, contrato, tipo geral, assunto, diagnóstico, status, datas e SLA.

Depois da importação, cada O.S fica vinculada internamente a um colaborador e a uma regional. Em seguida, o sistema tenta encontrar uma regra de pontuação para o assunto da O.S. Essa regra define a qual grupo de pontuação a O.S pertence e quantos pontos ela deve receber.

Com a pontuação base definida, o sistema verifica se existe alguma regra que impeça a O.S de pontuar totalmente, como diagnóstico configurado para anular, reincidência/garantia, SLA fora do prazo com regra ativa ou ausência de regra de assunto.

Ao recalcular, o sistema consolida os pontos por colaborador. O resultado aparece no ranking, na auditoria operacional, no extrato do colaborador, nos cards de fechamento e nos gráficos.

O caminho completo é:

1. Importar planilha de O.S.
2. Identificar colaborador, regional, cliente, contrato, assunto, diagnóstico e SLA.
3. Verificar se o assunto está vinculado a um grupo.
4. Calcular a pontuação base.
5. Aplicar regras de anulação quando existirem.
6. Calcular pontos líquidos.
7. Aplicar multiplicador de saúde operacional da regional.
8. Gerar ranking, auditoria, gráficos e fechamento.

## 3. Importação da planilha

A importação aceita arquivos `.xlsx`, `.xls` e `.csv`. A lógica fica em `backend/app/services/upvalue_importer.py`.

O sistema não depende de um único nome exato de coluna. Ele possui uma lista de nomes alternativos para localizar cada informação. Por exemplo, para colaborador, ele reconhece colunas como `Responsavel`, `Tecnico`, `Colaborador`, `Equipe` e `Executor`.

As informações mais importantes da planilha são:

| Informação | Como é usada na gamificação |
|---|---|
| ID da O.S | Identifica a ordem de serviço. Se vier vazia, o sistema gera um código técnico. |
| Responsável/colaborador | Define para quem a O.S será atribuída no ranking e no extrato. |
| Regional/filial | Permite filtrar ranking, calcular saúde da base e comparar desempenho por unidade. |
| Cliente, login e contrato | Ajudam a identificar cliente e possíveis reincidências. |
| Tipo geral e assunto | Definem a regra de pontuação e o grupo da O.S. |
| Diagnóstico | Pode liberar, anular, forçar pontuação ou exigir revisão, conforme regra configurada. |
| Status | Define se a O.S deve entrar no cálculo como concluída ou ser ignorada. |
| SLA | Indica se a O.S foi encerrada dentro ou fora do prazo. |
| Datas | Definem o período da apuração e apoiam a lógica de reincidência. |

### SLA importado

O campo SLA recebe tratamento específico em `backend/app/services/sla.py`.

O mapeamento atual é:

| Valor na planilha | Interpretação operacional | Status normalizado |
|---|---|---|
| Encerrada no Prazo | O.S finalizada dentro do prazo | `NO_PRAZO` |
| Encerrada Atrasada | O.S finalizada fora do prazo | `FORA_DO_PRAZO` |

O sistema considera variações de maiúsculas/minúsculas, espaços extras e acentos. Também reconhece termos como `fora do prazo`, `atrasada`, `atrasado`, `vencido` e `expirado`.

Na base atual, foram identificados:

| SLA original | Quantidade |
|---|---:|
| Encerrada no Prazo | 6815 |
| Encerrada Atrasada | 1238 |
| Dentro do prazo | 1 |

Esses dados alimentam o card e o filtro de Fora Prazo.

## 4. Colaboradores

O colaborador é identificado a partir do campo de responsável/técnico da planilha. Na importação, o sistema procura um colaborador já existente pelo nome normalizado. Se não encontrar, cria um novo colaborador com função `Importado UpValue`.

Essa lógica está em `get_or_create_collaborator`, no arquivo `backend/app/services/upvalue_importer.py`.

O vínculo técnico usa `collaborator_id`, mas esse ID é interno. Na interface, o usuário trabalha com o nome do colaborador.

No ranking, a busca é feita por nome:

- Implementação: `frontend/app/gamificacao/page.tsx`
- Campo usado: `collaborator_name`

Isso é importante porque o supervisor precisa localizar o colaborador pelo nome conhecido na operação, não por um ID interno.

O ranking considera colaboradores que possuem O.S no período calculado. Colaboradores ativos sem O.S são filtrados fora da apuração em `backend/app/services/calculation.py`.

## 5. Regionais e filiais

A regional é usada para segmentar a operação. Ela permite analisar produtividade e qualidade sem comparar bases com realidades muito diferentes.

No módulo, a regional serve para:

- Filtrar ranking.
- Filtrar gráficos.
- Filtrar auditoria.
- Calcular saúde operacional por base.
- Calcular investimento por regional.
- Apoiar a análise de pendências e desempenho.

A importação usa o valor textual da coluna `Regional`, `Filial`, `Unidade` ou `Base`. No frontend existe um mapeamento de códigos para nomes amigáveis em `frontend/lib/regional.ts`.

Exemplo:

| Código | Nome exibido |
|---|---|
| 6 | UNI - JI PARANA |
| 7 | UNI - MACHADINHO DOESTE |
| 8 | UNI - ROLIM DE MOURA |

Quando a planilha já traz o nome da regional, o sistema exibe o próprio nome.

O filtro de regional do ranking aceita mais de uma filial selecionada. O filtro compara a regional do colaborador no ranking com as regionais escolhidas.

## 6. Grupos de pontuação

Um grupo de pontuação representa uma família operacional de serviços. Ele define uma pontuação padrão para assuntos vinculados a ele.

Exemplo: uma O.S de `Sem Conexão Fibra Urbana` pertence a um grupo de manutenção urbana. Se esse grupo vale 6 pontos, a O.S começa com 6 pontos brutos, salvo regra específica do assunto.

Configuração atual encontrada no banco:

| Grupo | Assuntos vinculados | Pontos padrão | Valor específico por ponto | Ativo | Como afeta o cálculo |
|---|---:|---:|---|---|---|
| Ativacao / Mudanca de Endereco / Retorno (RURAL) | 10 | 20 | não identificado | Sim | O.S vinculadas começam com 20 pontos. |
| Ativacao / Mudanca de Endereco / Retorno (Urbano) | 5 | 14 | não identificado | Sim | O.S vinculadas começam com 14 pontos. |
| Manutencao Rural | 8 | 14 | não identificado | Sim | O.S vinculadas começam com 14 pontos. |
| Manutencao Urbana Simples | 10 | 6 | não identificado | Sim | O.S vinculadas começam com 6 pontos. |
| Manutencao Urbano Complexa | 5 | 8 | não identificado | Sim | O.S vinculadas começam com 8 pontos. |

O grupo interfere diretamente na pontuação inicial da O.S. Se o assunto da O.S está vinculado a um grupo ativo, o sistema usa os pontos do grupo, a menos que o assunto tenha uma pontuação própria configurada.

## 7. Assuntos configurados

O assunto detalha o tipo de serviço executado. É ele que liga a O.S a um grupo de pontuação.

Se o assunto está configurado, a O.S pode pontuar. Se o assunto não está configurado, a O.S aparece como `Sem regra` e entra na aba Pendências.

Assuntos configurados atualmente:

| Assunto | Grupo vinculado | Pontuação usada | Regra | Status |
|---|---|---:|---|---|
| Instalação Fibra Rural | Ativacao / Mudanca de Endereco / Retorno (RURAL) | 20 | Grupo | Ativo |
| Instalação Rádio | Ativacao / Mudanca de Endereco / Retorno (RURAL) | 20 | Grupo | Ativo |
| Retorno de Instalação Fibra Rural | Ativacao / Mudanca de Endereco / Retorno (RURAL) | 20 | Grupo | Ativo |
| Retorno de Instalação Rádio | Ativacao / Mudanca de Endereco / Retorno (RURAL) | 20 | Grupo | Ativo |
| Alteração de Endereço Fibra Rural | Ativacao / Mudanca de Endereco / Retorno (RURAL) | 20 | Grupo | Ativo |
| Alteração de Endereço Rádio | Ativacao / Mudanca de Endereco / Retorno (RURAL) | 20 | Grupo | Ativo |
| Retorno de Alteração de Endereço Fibra Rural | Ativacao / Mudanca de Endereco / Retorno (RURAL) | 20 | Grupo | Ativo |
| Retorno de Alteração de Endereço Rádio | Ativacao / Mudanca de Endereco / Retorno (RURAL) | 20 | Grupo | Ativo |
| Alteração da Tecnologia para Fibra | Ativacao / Mudanca de Endereco / Retorno (RURAL) | 20 | Grupo | Ativo |
| Retorno de Alteração de Tecnologia para Fibra | Ativacao / Mudanca de Endereco / Retorno (RURAL) | 20 | Grupo | Ativo |
| Instalação Evento/Permuta Fibra Urbana | Ativacao / Mudanca de Endereco / Retorno (Urbano) | 14 | Grupo | Ativo |
| Instalação Fibra Urbana | Ativacao / Mudanca de Endereco / Retorno (Urbano) | 14 | Grupo | Ativo |
| Retorno de Instalação Fibra Urbana | Ativacao / Mudanca de Endereco / Retorno (Urbano) | 14 | Grupo | Ativo |
| Alteração de Endereço Fibra Urbana | Ativacao / Mudanca de Endereco / Retorno (Urbano) | 14 | Grupo | Ativo |
| Retorno de Alteração de Endereço Fibra Urbana | Ativacao / Mudanca de Endereco / Retorno (Urbano) | 14 | Grupo | Ativo |
| Alteração na Rede Interna Fibra Rural | Manutencao Rural | 14 | Grupo | Ativo |
| Alteração na Rede Interna Rádio | Manutencao Rural | 14 | Grupo | Ativo |
| Reincidência de Suporte Fibra Rural | Manutencao Rural | 14 | Grupo | Ativo |
| Reincidência de Suporte Rádio | Manutencao Rural | 14 | Grupo | Ativo |
| Sem Conexão Fibra Rural | Manutencao Rural | 14 | Grupo | Ativo |
| Sem Conexão Rádio | Manutencao Rural | 14 | Grupo | Ativo |
| Suporte Externo Fibra Rural | Manutencao Rural | 14 | Grupo | Ativo |
| Suporte Externo Rádio | Manutencao Rural | 14 | Grupo | Ativo |
| Viabilidade | Manutencao Urbana Simples | 6 | Grupo | Ativo |
| Ativação de Login Presencial | Manutencao Urbana Simples | 6 | Grupo | Ativo |
| Manutenção Preventiva Operacional | Manutencao Urbana Simples | 6 | Grupo | Ativo |
| Remoção de Flashman | Manutencao Urbana Simples | 6 | Grupo | Ativo |
| Sem Conexão Fibra Urbana | Manutencao Urbana Simples | 6 | Grupo | Ativo |
| Suporte Externo Fibra Urbana | Manutencao Urbana Simples | 6 | Grupo | Ativo |
| Suporte Streaming/Apps | Manutencao Urbana Simples | 6 | Grupo | Ativo |
| Troca de Equipamentos | Manutencao Urbana Simples | 6 | Grupo | Ativo |
| Recuperação de Equipamento por Cobrança | Manutencao Urbana Simples | 6 | Grupo | Ativo |
| Remoção de Equipamentos | Manutencao Urbana Simples | 6 | Grupo | Ativo |
| Alteração na Rede Interna Fibra Urbana | Manutencao Urbano Complexa | 8 | Grupo | Ativo |
| Regulagem de Sinal | Manutencao Urbano Complexa | 8 | Grupo | Ativo |
| Reincidência de Suporte Fibra Urbana | Manutencao Urbano Complexa | 8 | Grupo | Ativo |
| Sem Conexão (Link LOS) | Manutencao Urbano Complexa | 8 | Grupo | Ativo |
| Suporte Prioritário | Manutencao Urbano Complexa | 8 | Grupo | Ativo |

Quando um assunto não tem regra, a O.S não recebe pontuação base. Ela aparece na aba Pendências para que o usuário vincule o assunto a um grupo antes de fechar a apuração.

## 8. Diagnósticos

O diagnóstico ajuda a interpretar o resultado técnico ou operacional da O.S. Ele pode indicar que a O.S deve pontuar normalmente, ser anulada, ter pontuação forçada ou ser tratada de outra forma conforme regra configurada.

A regra de diagnóstico fica em `diagnosis_penalty_rules` e é aplicada em `backend/app/services/scoring_detail.py`.

### Diagnósticos com regra

Atualmente existem 108 regras de diagnóstico configuradas no banco.

As ações usadas são:

| Ação | Interpretação operacional |
|---|---|
| `no_penalty` | O diagnóstico não impede a pontuação. |
| `cancel_points` | A O.S pode ter sua pontuação anulada. |
| `force_points` | A pontuação pode ser forçada para um valor específico. |

Exemplos de diagnósticos configurados para anular:

| Diagnóstico | Efeito |
|---|---|
| Desistência da Solicitação | Pode anular a pontuação da O.S. |
| Instalação Fibra Pendente: Cabo foi passado | Pode anular a pontuação da O.S. |
| Instalação Fibra Pendente: Sem cabo passado | Pode anular a pontuação da O.S. |
| Instalação Rádio Pendente: Não concluída | Pode anular a pontuação da O.S. |
| Ordem de Serviço Improdutiva | Pode anular a pontuação da O.S. |
| Remoção de Flashman: Cliente ausente | Pode anular a pontuação da O.S. |
| Remoção de Flashman: Não concluída / Trocado equipamento | Pode anular a pontuação da O.S. |
| Viabilidade: Negativa | Pode anular a pontuação da O.S. |

Diagnósticos configurados como `no_penalty` não bloqueiam a pontuação. Eles servem para registrar que aquele diagnóstico foi mapeado e não deve anular.

### Diagnósticos sem regra

Quando um diagnóstico aparece na planilha e não existe regra para ele, ele entra nas pendências de diagnóstico. A tela permite criar regra para esse diagnóstico antes do fechamento.

### Diagnósticos bloqueados

Na auditoria, o filtro de diagnósticos bloqueados considera O.S com regra de diagnóstico cuja ação seja uma ação de bloqueio ou alteração da pontuação. Essa lógica está em `filter_details`, no arquivo `backend/app/services/scoring_detail.py`.

Não foi identificada no código atual uma regra de compatibilidade de diagnóstico por assunto.

## 9. Regra de pontuação

A pontuação inicial da O.S vem do assunto. O sistema procura uma regra ativa para o par `Tipo Geral + Assunto`. Se encontrar, usa o grupo vinculado ao assunto.

Se o assunto usa regra do grupo, a pontuação é a pontuação padrão do grupo. Se o assunto tiver pontuação própria, essa pontuação substitui a do grupo.

Os conceitos usados na apuração são:

| Conceito | Significado |
|---|---|
| Pontos brutos | Pontos iniciais das O.S antes das anulações. |
| Pontos anulados | Pontos que deixaram de contar por alguma regra de anulação. |
| Pontos líquidos | Pontos brutos menos pontos anulados. |
| Pontos finais | Pontos líquidos após o multiplicador de saúde operacional. |
| Investimento estimado | Pontos finais convertidos pelo valor por ponto. |

Exemplo simples:

Uma O.S de Manutenção está ligada a um grupo de 6 pontos. Ela entra com 6 pontos brutos. Se nenhuma regra de anulação for aplicada, esses 6 pontos seguem para os pontos líquidos. Se uma regra anular essa O.S, os 6 pontos aparecem como pontos anulados e não entram nos pontos líquidos.

O valor estimado considera:

```text
pontos líquidos x multiplicador da regional x valor por ponto
```

O valor global do ponto considerado para a documentação operacional é de `R$ 0,35` por ponto.

## 10. Regras de anulação

### Reincidência/garantia

- Verifica se houve nova O.S para o mesmo cliente/contrato dentro da janela configurada.
- Quando confirma a reincidência ou garantia, a O.S de origem pode deixar de pontuar.
- Aparece na auditoria como reincidência, com O.S relacionada, dias entre os atendimentos e evidências.
- Exemplo: uma O.S de suporte foi fechada e, poucos dias depois, o cliente abriu nova O.S técnica relacionada. O sistema pode anular a pontuação da primeira O.S conforme configuração.

### SLA fora do prazo

- Verifica se o SLA normalizado é `FORA_DO_PRAZO`.
- A regra atual de SLA está ativa, mas configurada como `none`, portanto hoje sinaliza a O.S fora do prazo sem anular pontuação.
- Aparece no card e no filtro Fora Prazo.
- Exemplo: se a planilha marca `Encerrada Atrasada`, a O.S aparece como fora do prazo.

### Diagnóstico bloqueado

- Verifica se o diagnóstico possui regra configurada para anular ou alterar pontuação.
- Quando a regra é de anulação, os pontos da O.S deixam de entrar nos pontos líquidos.
- Aparece na auditoria como diagnóstico bloqueado/anulado.
- Exemplo: `Desistência da Solicitação` pode fazer a O.S não pontuar.

### Diagnóstico incompatível

Não identificado no código atual.

### Assunto sem regra

- Verifica se a O.S não possui regra ativa para seu tipo e assunto.
- A O.S fica como `Sem regra`.
- Aparece em Pendências e na Auditoria.
- Exemplo: uma O.S de assunto novo importado ainda não vinculado a grupo não recebe pontos até ser configurada.

### Grupo sem regra

A regra prática aparece como assunto sem regra. Não foi identificada uma regra separada chamada “grupo sem regra” no código atual.

### Serviço duplicado

Existe diagnóstico `Ordem de Serviço Duplicada` configurado como `no_penalty` atualmente. Não foi identificada regra automática específica de duplicidade fora da atualização da O.S pelo mesmo código na importação.

### Desistência

Existe diagnóstico `Desistência da Solicitação` configurado para anular pontos.

### O.S sem colaborador

O cálculo possui tratamento para O.S sem colaborador interno. Porém, na importação atual, quando não vem responsável, o sistema cria/vincula `NAO IDENTIFICADO`. Portanto a situação técnica existe no cálculo, mas tende a ser evitada pela importação.

### O.S sem regional

Quando a regional não vem na planilha, o sistema usa `NAO IDENTIFICADO`. Não foi identificada regra de anulação específica por regional ausente.

## 11. SLA e prazo

O SLA indica se a O.S foi encerrada dentro ou fora do prazo.

No sistema:

- `Encerrada no Prazo` significa O.S dentro do prazo.
- `Encerrada Atrasada` significa O.S fora do prazo.

Esses textos são normalizados para:

| Texto da planilha | Status interno |
|---|---|
| Encerrada no Prazo | `NO_PRAZO` |
| Encerrada Atrasada | `FORA_DO_PRAZO` |

O filtro Fora Prazo usa esse status normalizado. Assim, ao clicar em Fora Prazo, a tabela deve listar apenas O.S identificadas como fora do prazo.

O card Fora Prazo é calculado contando todas as O.S cujo campo normalizado indica fora do prazo.

Exemplo:

Se a planilha trouxer 55 O.S como `Encerrada Atrasada`, o card Fora Prazo deve mostrar 55 e o filtro Fora Prazo deve listar essas 55 O.S.

Regra atual:

| Nome | Condição | Ação atual |
|---|---|---|
| Fora do prazo | O.S com SLA fora do prazo | Sinaliza, não anula |

Isso acontece porque a regra de SLA está configurada como `none`.

## 12. Reincidência e garantia

A reincidência serve para identificar situações em que o cliente precisou de novo atendimento depois de uma O.S anterior. A ideia operacional é verificar se a O.S anterior deve continuar pontuando ou se deve ser anulada por ter gerado retorno.

A lógica fica em `backend/app/services/scoring_detail.py`.

### Janela de dias

A janela atual é de 30 dias, configurada em:

```text
recurrence_window_days = 30
```

### Campo que conecta as O.S

O sistema tenta conectar as O.S pelo:

1. Login do cliente.
2. ID do contrato, quando o login não existe.

Na base atual, não há login preenchido nas O.S importadas. Por isso, a análise depende principalmente do contrato.

### Origem e retorno

- O.S origem: atendimento anterior.
- O.S retorno: atendimento posterior do mesmo cliente/contrato.

Quando encontra relação técnica, o sistema pode classificar como garantia ou reincidência técnica.

### Efeito na pontuação

A configuração atual é:

```text
recurrence_action = annul_original
```

Isso significa que, quando a reincidência é confirmada, a pontuação da O.S origem pode ser anulada.

Na auditoria, a O.S mostra evidências como:

- Mesmo contrato ou login.
- O.S posterior relacionada.
- Quantidade de dias entre os atendimentos.
- Classificação encontrada.

## 13. Saúde operacional e multiplicadores

A saúde operacional mede a qualidade da regional. Ela usa indicadores de prazo e reincidência para aplicar um multiplicador nos pontos líquidos dos colaboradores daquela base.

A lógica fica em:

- `calculate_regional_health`
- `calculate_regional_health_from_details`
- `select_health_rule`

Indicadores usados:

| Indicador | Como é calculado |
|---|---|
| SLA | Percentual de O.S no prazo na regional. |
| Reincidência | Percentual de O.S com garantia/reincidência na regional. |

Faixas atuais:

| Saúde | SLA mínimo | Reincidência máxima | Multiplicador | Ativo |
|---|---:|---:|---:|---|
| Excelente | 95% | 100% | 1.5 | Sim |
| Boa | 92% | 100% | 1.2 | Sim |
| Atenção | 90% | 100% | 1.0 | Sim |
| Crítica | 1% | 100% | 0.8 | Sim |

O multiplicador é aplicado depois dos pontos líquidos:

```text
pontos finais = pontos líquidos x multiplicador
```

Ele também afeta o investimento estimado, porque o investimento é calculado sobre os pontos finais.

## 14. Ranking

O ranking mostra o resultado final da apuração por colaborador.

Entram no ranking os colaboradores ativos que possuem O.S no período calculado. Colaboradores sem O.S no período são filtrados fora do ranking.

O ranking não é apenas uma contagem de O.S. Ele considera:

- Total de O.S.
- O.S pontuadas.
- O.S sem regra.
- O.S anuladas.
- Pontos brutos.
- Pontos anulados.
- Pontos líquidos.
- Multiplicador da regional.
- Pontos finais.
- Investimento estimado.

O ranking geral mostra todos os colaboradores do período. O ranking por regional aplica o filtro de uma ou mais filiais selecionadas.

A busca de colaborador é por nome, não por ID interno.

## 15. Auditoria operacional

A Auditoria Operacional serve para justificar o resultado da apuração. Ela mostra O.S por O.S, com a regra aplicada, status, pontos, SLA, diagnóstico e motivo da pontuação ou anulação.

### Filtros

| Filtro | O que mostra |
|---|---|
| Todas | Todas as O.S do período/filtro atual. |
| Pontuadas | O.S que entraram na pontuação. |
| Sem regra | O.S sem assunto configurado. |
| O.S anuladas | O.S cuja pontuação foi anulada. |
| Fora prazo | O.S com SLA fora do prazo. |
| Reincidências | O.S relacionadas a garantia/reincidência. |
| Diagnósticos bloqueados | O.S com diagnóstico que interfere na pontuação. |
| Sem reincidência | Casos analisados como não reincidentes. |
| Por grupo | Agrupa O.S pelo grupo de pontuação. |

### Cards

| Card | Interpretação |
|---|---|
| Total | Total de O.S no filtro atual. |
| Sem regra | O.S que ainda não possuem regra de assunto. |
| O.S anuladas | O.S que não entram total ou parcialmente nos pontos líquidos. |
| Fora prazo | O.S identificadas como fora do prazo. |
| Pontos anulados | Soma dos pontos que deixaram de contar. |
| Reincidências | O.S classificadas como garantia/reincidência. |
| Diagnósticos bloqueados | O.S com diagnóstico que altera ou anula pontuação. |

Essa tela é a principal referência para explicar por que um colaborador recebeu determinado resultado.

## 16. Pendências

A aba Pendências é uma área de preparação antes do fechamento. Ela existe para evitar que a apuração seja fechada com O.S sem regra.

Ela mostra principalmente:

- Assuntos sem grupo.
- Diagnósticos sem regra.
- Quantidade de O.S afetadas.
- Impacto estimado.

### Assuntos sem grupo

Quando um assunto aparece na planilha, mas não está vinculado a nenhum grupo, o sistema não sabe quantos pontos aquela O.S deve receber. Por isso, ela entra como pendência.

A tela permite:

- Vincular o assunto a um grupo existente.
- Criar um grupo a partir do assunto.
- Aplicar vínculo em massa.

### Diagnósticos sem regra

Quando um diagnóstico novo aparece na planilha, ele pode ser configurado para pontuar normalmente ou anular, conforme a governança operacional.

Após corrigir pendências, o usuário deve recalcular a pontuação para que o ranking e a auditoria reflitam as novas regras.

## 17. Configuração

A aba Configuração é o centro de governança da apuração.

### Valor global do ponto

Define quanto vale cada ponto final em investimento estimado. Se um assunto ou grupo não tiver valor específico, usa esse valor global.

### Janela de reincidência

Define por quantos dias o sistema procura uma O.S posterior do mesmo cliente/contrato para avaliar garantia ou reincidência.

### Grupos

Definem famílias de serviço e pontuação padrão.

### Assuntos

Ligam o serviço real da planilha a um grupo de pontuação.

### Diagnósticos

Definem como o resultado técnico da O.S interfere na apuração.

### Multiplicadores

Definem como a saúde da regional altera os pontos líquidos.

### Modo simples

Organiza as configurações em etapas mais guiadas, voltadas ao ajuste operacional.

### Modo avançado

Abre uma matriz mais completa para editar assuntos, diagnósticos e grupos com mais detalhe.

### Importar/exportar JSON

Existe exportação e importação de configuração em JSON. Ela serve para versionar ou restaurar conjuntos de regras.

## 18. Histórico e fechamento

Existe histórico de cálculo em `CalculationRun`. Ele registra período, data do cálculo, arquivo/importação de origem, versão de regra, colaboradores, pontos e investimento estimado.

A tela de Fechamento mostra um resumo do período e pendências antes de pagar.

Não identificado no código atual:

- Status formal de prévia.
- Status formal de auditoria.
- Aprovação.
- Fechamento mensal imutável.
- Bloqueio de reprocessamento após fechamento.

O sistema permite recalcular o período, gerando novo registro de cálculo.

## 19. Gráficos e indicadores

### Top 15 por pontos finais

Mostra os colaboradores com maior pontuação final. Responde quem ficou melhor posicionado depois das anulações e do multiplicador de saúde.

Origem: `summary.ranking`.

### Distribuição de pontos anulados

Mostra os principais motivos de anulação, com quantidade de O.S e pontos anulados.

Origem: `penalty_distribution`, calculado a partir dos itens de penalidade de cada O.S.

Quando há filtro de regional, o gráfico recalcula usando as O.S auditadas daquela seleção.

### Investimento por regional

Mostra o investimento estimado agrupado por base/regional.

Origem: `financial_breakdowns`.

### Investimento por grupo

Mostra o investimento estimado agrupado por grupo de pontuação.

Origem: `financial_breakdowns`.

### Saúde operacional por regional

Mostra SLA e reincidência por regional. Ajuda a entender qual multiplicador pode ser aplicado à base.

Origem: `health_by_regional`.

### Gráfico de dispersão

Compara colaboradores por quantidade de O.S e pontos finais. Também diferencia colaboradores com e sem reincidência.

Serve para enxergar produtividade e qualidade juntas: um colaborador pode ter muitas O.S, mas resultado menor se houver anulações ou multiplicador inferior.

## 20. Conclusão operacional

A Gamificação Operacional funciona como uma camada de apuração sobre as O.S importadas. Ela transforma serviços realizados em pontos, aplica regras de governança, identifica pendências, permite auditoria detalhada e consolida ranking, saúde regional e investimento estimado.

O objetivo não é apenas contar O.S, mas qualificar o resultado: uma O.S só deve contribuir para o ranking quando possui regra de assunto, diagnóstico tratado, SLA identificado e ausência de regra que anule sua pontuação. Dessa forma, o módulo apoia tanto a gestão de produtividade quanto a conferência operacional antes do fechamento.
