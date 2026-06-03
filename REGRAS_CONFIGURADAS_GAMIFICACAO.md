# Regras Configuradas Atuais - Gamificacao Operacional UNI OPR

Documento de apoio para reuniao executiva.

Data de referencia da extracao: `2026-05-29`

Fonte utilizada:
- configuracoes vivas do banco `opr_gamification`
- tabelas `app_settings`, `scoring_groups`, `scoring_subject_rules`, `diagnosis_penalty_rules`, `sla_penalty_rules`, `recurrence_classification_rules` e `health_rules`
- estrutura funcional implementada em `backend/app/services/scoring_detail.py`

## 1. Tese de funcionamento do sistema

O modulo de Gamificacao Operacional transforma O.S em uma apuracao auditavel.

O fluxo atual funciona assim:

1. A planilha importada identifica colaborador, regional, cliente, contrato/login, tipo geral, assunto, diagnostico e SLA.
2. Cada assunto e vinculado a um grupo de pontuacao.
3. O grupo ou o proprio assunto define a pontuacao base da O.S.
4. Regras de diagnostico, SLA e reincidencia verificam se a O.S pontua normalmente, apenas sinaliza ou tem a pontuacao anulada.
5. O resultado consolidado gera ranking, auditoria, extrato, fechamento e valor a ser pago.

## 2. Parametros gerais ativos

| Parametro | Valor atual | Leitura operacional |
|---|---:|---|
| Valor do ponto | `R$ 0,35` | Cada ponto final vale R$ 0,35 |
| Janela de reincidencia | `30 dias` | Retornos dentro dessa janela podem anular a O.S original |
| Acao padrao da reincidencia | `annul_original` | A regra confirmada anula a O.S original |
| Campos de vinculo da reincidencia | `login, contract` | O motor procura retorno pelo login e pelo contrato |
| Pontos fixos de reincidencia | `0` | Nao ha desconto fixo adicional configurado |
| Modo garantia | `no_points` | Internamente mantido como legado, mas a leitura visual foi padronizada para reincidencia |
| Payment cap | `0` | Sem teto financeiro configurado |

## 3. Grupos de pontuacao ativos

| Grupo | Pontos padrao | R$/ponto proprio | Status |
|---|---:|---:|---|
| Ativacao / Mudanca de Endereco / Retorno (RURAL) | 20 | Global | Ativo |
| Ativacao / Mudanca de Endereco / Retorno (Urbano) | 14 | Global | Ativo |
| Manutencao Rural | 14 | Global | Ativo |
| Manutencao Urbana Simples | 6 | Global | Ativo |
| Manutencao Urbano Complexa | 8 | Global | Ativo |

Leitura executiva:
- hoje existem `5 grupos ativos`
- nenhum grupo possui `R$/ponto` proprio; todos usam o valor global de `R$ 0,35`

## 4. Regras de assunto configuradas

Total atual: `40 assuntos configurados`, todos `ativos`.

### 4.1 Ativacao

| Assunto | Grupo vinculado | Pontos | Usa grupo | Status |
|---|---|---:|---|---|
| Instalação Evento/Permuta Fibra Urbana | Ativacao / Mudanca de Endereco / Retorno (Urbano) | 14 | Sim | Ativo |
| Instalação Fibra Rural | Ativacao / Mudanca de Endereco / Retorno (RURAL) | 20 | Sim | Ativo |
| Instalação Fibra Urbana | Ativacao / Mudanca de Endereco / Retorno (Urbano) | 14 | Sim | Ativo |
| Instalação Rádio | Ativacao / Mudanca de Endereco / Retorno (RURAL) | 20 | Sim | Ativo |
| Retorno de Instalação Fibra Rural | Ativacao / Mudanca de Endereco / Retorno (RURAL) | 20 | Sim | Ativo |
| Retorno de Instalação Fibra Urbana | Ativacao / Mudanca de Endereco / Retorno (Urbano) | 14 | Sim | Ativo |
| Retorno de Instalação Rádio | Ativacao / Mudanca de Endereco / Retorno (RURAL) | 20 | Sim | Ativo |

### 4.2 Informacao

| Assunto | Grupo vinculado | Pontos | Usa grupo | Status |
|---|---|---:|---|---|
| Viabilidade | Manutencao Urbana Simples | 6 | Sim | Ativo |

### 4.3 Manutencao

| Assunto | Grupo vinculado | Pontos | Usa grupo | Status |
|---|---|---:|---|---|
| Alteração na Rede Interna Fibra Rural | Manutencao Rural | 14 | Sim | Ativo |
| Alteração na Rede Interna Fibra Urbana | Manutencao Urbano Complexa | 8 | Sim | Ativo |
| Alteração na Rede Interna Rádio | Manutencao Rural | 14 | Sim | Ativo |
| Ativação de Login Presencial | Manutencao Urbana Simples | 6 | Sim | Ativo |
| Manutenção Preventiva Operacional | Manutencao Urbana Simples | 6 | Sim | Ativo |
| Regulagem de Sinal | Manutencao Urbano Complexa | 8 | Sim | Ativo |
| Reincidência de Suporte Fibra Rural | Manutencao Rural | 14 | Sim | Ativo |
| Reincidência de Suporte Fibra Urbana | Manutencao Urbano Complexa | 8 | Sim | Ativo |
| Reincidência de Suporte Rádio | Manutencao Rural | 14 | Sim | Ativo |
| Remoção de Flashman | Manutencao Urbana Simples | 6 | Sim | Ativo |
| Sem Conexão (Link LOS) | Manutencao Urbano Complexa | 8 | Sim | Ativo |
| Sem Conexão Fibra Rural | Manutencao Rural | 14 | Sim | Ativo |
| Sem Conexão Fibra Urbana | Manutencao Urbana Simples | 6 | Sim | Ativo |
| Sem Conexão Rádio | Manutencao Rural | 14 | Sim | Ativo |
| Suporte Externo Fibra Rural | Manutencao Rural | 14 | Sim | Ativo |
| Suporte Externo Fibra Urbana | Manutencao Urbana Simples | 6 | Sim | Ativo |
| Suporte Externo Rádio | Manutencao Rural | 14 | Sim | Ativo |
| Suporte Prioritário | Manutencao Urbano Complexa | 8 | Sim | Ativo |
| Suporte Streaming/Apps | Manutencao Urbana Simples | 6 | Sim | Ativo |
| Troca de Equipamentos | Manutencao Urbana Simples | 6 | Sim | Ativo |

### 4.4 Mudanca de Endereco

| Assunto | Grupo vinculado | Pontos | Usa grupo | Status |
|---|---|---:|---|---|
| Alteração de Endereço Fibra Rural | Ativacao / Mudanca de Endereco / Retorno (RURAL) | 20 | Sim | Ativo |
| Alteração de Endereço Fibra Urbana | Ativacao / Mudanca de Endereco / Retorno (Urbano) | 14 | Sim | Ativo |
| Alteração de Endereço Rádio | Ativacao / Mudanca de Endereco / Retorno (RURAL) | 20 | Sim | Ativo |
| Retorno de Alteração de Endereço Fibra Rural | Ativacao / Mudanca de Endereco / Retorno (RURAL) | 20 | Sim | Ativo |
| Retorno de Alteração de Endereço Fibra Urbana | Ativacao / Mudanca de Endereco / Retorno (Urbano) | 14 | Sim | Ativo |
| Retorno de Alteração de Endereço Rádio | Ativacao / Mudanca de Endereco / Retorno (RURAL) | 20 | Sim | Ativo |

### 4.5 Mudanca de Tecnologia

| Assunto | Grupo vinculado | Pontos | Usa grupo | Status |
|---|---|---:|---|---|
| Alteração da Tecnologia para Fibra | Ativacao / Mudanca de Endereco / Retorno (RURAL) | 20 | Sim | Ativo |
| Retorno de Alteração de Tecnologia para Fibra | Ativacao / Mudanca de Endereco / Retorno (RURAL) | 20 | Sim | Ativo |

### 4.6 Outros

| Assunto | Grupo vinculado | Pontos | Usa grupo | Status |
|---|---|---:|---|---|
| Instalação Evento/Permuta Fibra Rural | Ativacao / Mudanca de Endereco / Retorno (RURAL) | 20 | Sim | Ativo |
| Retorno de Instalação Evento/Permuta Fibra Urbana | Ativacao / Mudanca de Endereco / Retorno (Urbano) | 14 | Sim | Ativo |

### 4.7 Recolhimento

| Assunto | Grupo vinculado | Pontos | Usa grupo | Status |
|---|---|---:|---|---|
| Recuperação de Equipamento por Cobrança | Manutencao Urbana Simples | 6 | Sim | Ativo |
| Remoção de Equipamentos | Manutencao Urbana Simples | 6 | Sim | Ativo |

## 5. Regras de diagnostico configuradas

Total atual: `108 diagnosticos configurados`

Resumo por acao:

| Acao | Quantidade | Leitura operacional |
|---|---:|---|
| `cancel_points` | 7 | Diagnosticos que anulam a pontuacao da O.S |
| `no_penalty` | 101 | Diagnosticos que nao anulam a pontuacao |

### 5.1 Diagnosticos que anulam pontuacao

| Diagnostico | Acao | Status |
|---|---|---|
| Desistência da Solicitação | cancel_points | Ativo |
| Instalação Fibra Pendente: Cabo foi passado | cancel_points | Ativo |
| Instalação Fibra Pendente: Sem cabo passado | cancel_points | Ativo |
| Instalação Rádio Pendente: Não concluída | cancel_points | Ativo |
| Ordem de Serviço Improdutiva | cancel_points | Ativo |
| Remoção de Flashman: Cliente ausente | cancel_points | Ativo |
| Viabilidade: Negativa | cancel_points | Ativo |

### 5.2 Diagnosticos configurados sem anulacao

| Diagnostico | Acao | Status |
|---|---|---|
| Alteração de Cômodo: Utilizado mesmo cabo | no_penalty | Ativo |
| Alteração de Cômodo: Utilizado novo cabo | no_penalty | Ativo |
| Apps: Canais em funcionamento | no_penalty | Ativo |
| Apps: Deezer + Canais em funcionamento | no_penalty | Ativo |
| Apps: Deezer em funcionamento | no_penalty | Ativo |
| Apps: Max + Canais em funcionamento | no_penalty | Ativo |
| Apps: Max + Dezeer + Canais em funcionamento | no_penalty | Ativo |
| Apps: Max em funcionamento | no_penalty | Ativo |
| Apps: TV / Aparelho não compatível | no_penalty | Ativo |
| Atendimento com Assunto Errado | no_penalty | Ativo |
| Configuração de Segundo Ponto | no_penalty | Ativo |
| Equipamento era de Propriedade do cliente | no_penalty | Ativo |
| Equipamento não Trocado sem Necessidade de Substituição | no_penalty | Ativo |
| Equipamentos: Não Removidos | no_penalty | Ativo |
| Equipamentos: Parcialmente Removidos | no_penalty | Ativo |
| Equipamentos: Removidos | no_penalty | Ativo |
| Excedente drop - Instalação Fibra: Não tinha cabo passado | no_penalty | Ativo |
| Excedente drop/poste - Instalação Fibra: Não tinha cabo passado | no_penalty | Ativo |
| Excedente poste - Instalação Fibra: Não tinha cabo passado | no_penalty | Ativo |
| IFR -  Reparo em Splitter/Conectores. | no_penalty | Ativo |
| IFR - Ampliação de Portas CTO | no_penalty | Ativo |
| IFR - Atualização de Documentação | no_penalty | Ativo |
| IFR - Documentação de POP/Site | no_penalty | Ativo |
| IFR - Documentação de Rede Óptica | no_penalty | Ativo |
| IFR - Emendas e Fusões. | no_penalty | Ativo |
| IFR - Estrutura suja (poeira/barro/fuligem) | no_penalty | Ativo |
| IFR - Fibra Rompida. | no_penalty | Ativo |
| IFR - Implantação de Equipamento | no_penalty | Ativo |
| IFR - Instalação de Infraestrutura. | no_penalty | Ativo |
| IFR - Instalação de Novo Equipamento | no_penalty | Ativo |
| IFR - Lançamento de Rede. | no_penalty | Ativo |
| IFR - Manutenção Interna CTO | no_penalty | Ativo |
| IFR - Manutenção Preventiva | no_penalty | Ativo |
| IFR - Manutenção em Cabeamento | no_penalty | Ativo |
| IFR - Manutenção em Rádio/Antena | no_penalty | Ativo |
| IFR - Preventiva - Equipamentos Ativos. | no_penalty | Ativo |
| IFR - Preventiva Geral. | no_penalty | Ativo |
| IFR - Refusão/Emenda. | no_penalty | Ativo |
| IFR - Remanejamento de Equipamento | no_penalty | Ativo |
| IFR - Rompimento por manutenção em poste. | no_penalty | Ativo |
| IFR - Splitter Danificado | no_penalty | Ativo |
| IFR - Substituição de Equipamento | no_penalty | Ativo |
| IFR - Upgrade de Equipamento | no_penalty | Ativo |
| IFR -Rompimento Causa não identificada | no_penalty | Ativo |
| IFR: Equipamento legado trocado | no_penalty | Ativo |
| IFR: Equipamento novo instalado | no_penalty | Ativo |
| Instalação Fibra: Com cabo passado | no_penalty | Ativo |
| Instalação Fibra: Não tinha cabo passado | no_penalty | Ativo |
| Instalação Fibra: com cabo passado (realocação de cabo) | no_penalty | Ativo |
| Instalação Rádio: Concluída | no_penalty | Ativo |
| Instalação Rádio: Não Concluída | no_penalty | Ativo |
| Limpeza de Trecho/POP | no_penalty | Ativo |
| Login ativado - Com substituição de equipamento | no_penalty | Ativo |
| Login ativado - Equipamento original mantido | no_penalty | Ativo |
| Login não ativado | no_penalty | Ativo |
| Login não ativado e Comodato não transferido | no_penalty | Ativo |
| Man. OPR - Danos provocados por terceiros | no_penalty | Ativo |
| Man. OPR - Organização de CTO | no_penalty | Ativo |
| Man. OPR - Organização de Cabos | no_penalty | Ativo |
| Manutenção Corretiva NBS | no_penalty | Ativo |
| O.S. NÃO Homologada | no_penalty | Ativo |
| Ordem de Serviço Duplicada | no_penalty | Ativo |
| Passagem de cabo para TV/Computador | no_penalty | Ativo |
| Preventiva - Infraestrutura (gerador, ar condicionado, diesel, etc.). | no_penalty | Ativo |
| Preventiva - Rede Óptica (fibra, caixas, conectores, etc.) | no_penalty | Ativo |
| Remoção de Flashman: Concluída | no_penalty | Ativo |
| Remoção de Flashman: Não concluída / Trocado equipamento | no_penalty | Ativo |
| Resolvido | no_penalty | Ativo |
| Rompimento - Causa não identificada NBS | no_penalty | Ativo |
| SUP: Acoplador Danificado | no_penalty | Ativo |
| SUP: Alteração de Senha/Wifi (Fibra) | no_penalty | Ativo |
| SUP: Alteração de Senha/Wifi (Rádio) | no_penalty | Ativo |
| SUP: Antena Queimada | no_penalty | Ativo |
| SUP: Atualização de configuração de equipamento ((Fibra)) | no_penalty | Ativo |
| SUP: Atualização de configuração de equipamento (Rádio) | no_penalty | Ativo |
| SUP: Cabo Lan invertido (Fibra) | no_penalty | Ativo |
| SUP: Cabo Lan invertido (Rádio) | no_penalty | Ativo |
| SUP: Cabo Rompido ou Danificado (Fibra) | no_penalty | Ativo |
| SUP: Cabo Rompido ou Danificado (Rádio) | no_penalty | Ativo |
| SUP: Conector Danificado (Fibra) | no_penalty | Ativo |
| SUP: Conector Danificado (Rádio) | no_penalty | Ativo |
| SUP: Equipamento resetado (Fibra) | no_penalty | Ativo |
| SUP: Equipamento resetado (Rádio) | no_penalty | Ativo |
| SUP: Equipamentos travados (Fibra) | no_penalty | Ativo |
| SUP: Equipamentos travados (Rádio) | no_penalty | Ativo |
| SUP: Fonte (Fibra) | no_penalty | Ativo |
| SUP: Fonte / PoE (Rádio) | no_penalty | Ativo |
| SUP: IPTV não licenciado (Fibra) | no_penalty | Ativo |
| SUP: IPTV não licenciado (Rádio) | no_penalty | Ativo |
| SUP: Perca de potência da Antena (Rádio) | no_penalty | Ativo |
| SUP: Problema de Infraestrutura | no_penalty | Ativo |
| SUP: Problemas na rede interna do cliente (Fibra) | no_penalty | Ativo |
| SUP: Problemas na rede interna do cliente (Rádio) | no_penalty | Ativo |
| SUP: Procedimento Organizacional | no_penalty | Ativo |
| SUP: Sinal Degradado (Fibra) | no_penalty | Ativo |
| SUP: Sinal Degradado (Rádio) | no_penalty | Ativo |
| SUP: Troca de Antena (Rádio) | no_penalty | Ativo |
| SUP: Troca de Roteador (Rádio) | no_penalty | Ativo |
| SUP: Troca de Roteador/ONU (Fibra) | no_penalty | Ativo |
| Vazio | no_penalty | Ativo |
| Viabilidade: Positiva | no_penalty | Ativo |

## 6. Regra de SLA configurada

| Regra | Condicao | Efeito configurado | Status |
|---|---|---|---|
| Fora do prazo | `status_sla_out_of_time` | `none` | Ativa |

Leitura executiva:
- a O.S fora do prazo e identificada
- a regra atual de SLA esta configurada para `nao anular pontos`
- portanto, hoje o SLA fora do prazo funciona como sinalizacao operacional

## 7. Regras de reincidencia configuradas

Total atual: `2 regras ativas`

| Regra | Classificacao visual | Prioridade | Janela | O.S original | O.S retorno | Anula O.S original | Status |
|---|---|---:|---:|---|---|---|---|
| Reincidencia de Manutencao | Reincidencia de manutencao | 10 | 30 dias | Tipo `Manutencao` | Tipo `Manutencao` | Sim | Ativa |
| Reincidencia de Ativacao | Reincidencia apos ativacao | 20 | 30 dias | Tipo `Ativacao` | Tipo `Manutencao` | Sim | Ativa |

Leitura executiva:
- o sistema esta configurado para olhar `login` e `contrato`
- a reincidencia confirmada hoje `anula a O.S original`
- nao existe regra ativa para `Ativacao -> Ativacao`
- nao existe regra ativa baseada em diagnostico de confirmacao ou diagnostico de bloqueio no estado atual

## 8. Regras de saude operacional configuradas

| Faixa | SLA minimo | Reincidencia maxima | Multiplicador | Operador | Status |
|---|---:|---:|---:|---|---|
| Excelente | 95 | 100 | 1.5 | and | Ativa |
| Boa | 92 | 100 | 1.2 | and | Ativa |
| Atencao | 90 | 100 | 1.0 | or | Ativa |
| Critica | 1 | 100 | 0.8 | fallback | Ativa |

Leitura executiva:
- a base com melhor saude recebe multiplicador maior
- a base critica reduz o valor final para `0,8x`
- a tela hoje usa SLA e reincidencia como indicadores de saude

## 9. Conclusao para defesa em reuniao

Hoje o sistema esta sustentado por uma matriz explicita e auditavel:

- `5 grupos ativos`
- `40 assuntos configurados`
- `108 diagnosticos configurados`
- `1 regra de SLA`
- `2 regras de reincidencia`
- `4 faixas de saude operacional`

Isso significa que a plataforma nao trabalha com pontuacao solta ou sem rastreabilidade. A O.S passa por uma cadeia de governanca clara:

1. assunto define grupo e pontos
2. diagnostico define se a O.S pontua ou nao pontua
3. SLA sinaliza conformidade de prazo
4. reincidencia verifica retorno dentro da janela
5. saude da base aplica multiplicador final

Em termos executivos, a plataforma entrega:

- rastreabilidade da regra aplicada em cada O.S
- capacidade de auditoria por colaborador, assunto, diagnostico e regional
- fechamento com valor a ser pago sustentado por regras configuradas
- visao de governanca para impedir pagamento sobre O.S sem regra
