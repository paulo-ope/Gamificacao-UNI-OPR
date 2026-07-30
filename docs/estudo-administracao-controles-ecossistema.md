# Estudo: controles do modulo Administracao

## Objetivo

Mapear o que deve ser administrado na aba **Administracao** do UNI Workspace para evitar duplicidade de controle entre Gamificacao, Operacao Analitica, Agendamento e Portal.

Este documento e um estudo funcional/arquitetural. Ele nao altera regra de negocio, banco, telas ou permissoes por si so.

## Diagnostico curto

Hoje o sistema ja tem uma aba **Administracao** propria para usuarios, perfis, permissoes e escopo regional. Porem ainda existem controles administrativos espalhados dentro dos modulos, principalmente:

- configuracoes da Gamificacao;
- cadastro de colaboradores;
- regras de pontuacao, penalidade e fechamento;
- modelos de equipe da Operacao Analitica;
- assuntos operacionais;
- sincronizacao IXC;
- configuracoes do Agendamento;
- visoes/filtros globais.

Isso cria risco de duplicidade porque uma mesma decisao administrativa pode aparecer em mais de um lugar. Exemplo: o colaborador pode ser controlado na Gamificacao, mas o responsavel operacional fica configurado na Analitica. Outro exemplo: usuario/perfil ainda existe como tela legada dentro da Gamificacao, enquanto a Administracao ja possui controle central.

## Principio recomendado

A aba **Administracao** deve controlar aquilo que vale para o ecossistema inteiro ou que define acesso, escopo, governanca e integracoes.

Cada modulo deve continuar controlando apenas configuracoes operacionais muito especificas do proprio modulo.

Regra simples:

```text
Controle de acesso, escopo, identidade, integracao e governanca global -> Administracao
Regra operacional especifica do modulo -> fica no modulo, mas pode aparecer na Administracao como atalho ou resumo
```

## O que a Administracao ja controla hoje

| Area | Controle atual | Observacao |
| --- | --- | --- |
| Usuarios | Criar, editar, ativar, excluir e definir senha inicial | Deve ser a fonte oficial de usuarios do ecossistema. |
| Perfis de acesso | Criar, editar, ativar e excluir perfis | Deve substituir o controle legado de usuarios dentro da Gamificacao. |
| Permissoes | Listar permissoes por modulo | O cadastro das permissoes ainda e tecnico, vindo do backend. |
| Escopo regional por usuario | Definir regionais permitidas | Ja usa regionais da base analitica. |

Arquivos atuais principais:

- `frontend/app/admin/page.tsx`
- `backend/app/modules/admin/router.py`
- `backend/app/modules/admin/schemas.py`
- `backend/app/core/security.py`

## Mapa do que pode ser administrado nessa aba

### 1. Identidade e acesso

Deve ficar na Administracao:

- usuarios;
- senhas iniciais ou redefinicao de senha;
- usuarios ativos/inativos;
- perfis de acesso;
- permissoes por perfil;
- vinculo de usuario com colaborador;
- escopo regional por usuario;
- escopo por modulo.

Nao deve ficar duplicado dentro da Gamificacao. A tela legada de "Usuarios" da Gamificacao deve virar apenas atalho para Administracao ou ser removida no futuro.

### 2. Escopos e restricoes

Deve ficar na Administracao:

- quais regionais o usuario pode ver;
- quais modulos o usuario pode acessar;
- quais acoes ele pode executar;
- se pode ver detalhe de O.S.;
- se pode exportar dados;
- se pode gerenciar visoes globais;
- se pode sincronizar IXC;
- se pode alterar regras sensiveis.

Esse controle precisa ser aplicado sempre no backend. O frontend pode esconder botoes, mas nao pode ser a unica barreira.

### 3. Colaboradores e vinculos oficiais

Area com risco alto de duplicidade.

Hoje existem dois mundos:

- Gamificacao: cadastro de colaboradores que pontuam, recebem saldo, aparecem em fechamento e portal.
- Operacao Analitica: responsaveis operacionais vinculados a modelos de equipe.

Recomendacao:

- a Administracao deve ter uma visao central de "Pessoas e vinculos";
- a Gamificacao continua dona das regras de pontuacao e pagamento;
- a Operacao continua dona da leitura analitica de O.S.;
- o cadastro oficial da pessoa deve usar um identificador estavel, preferencialmente `ixc_employee_id`;
- se alguem tiver modelo de equipe na Analitica, deve aparecer como vinculado ou pendente na Gamificacao.

Controles recomendados na Administracao:

- pessoa/colaborador oficial;
- vinculo com usuario de login;
- vinculo com ID do IXC;
- status ativo/inativo;
- status cadastrado na Gamificacao;
- status integrante de equipe operacional;
- regional principal e regionais associadas;
- alertas de possivel duplicidade por nome.

### 4. Integracoes

Deve ficar na Administracao, ou pelo menos ter painel central de governanca:

- status da integracao IXC;
- setores IXC sincronizados;
- intervalo de sincronizacao;
- ultima sincronizacao por modulo;
- falhas recentes;
- permissao de sincronizar manualmente.

O modulo pode manter o botao operacional "Sincronizar agora", mas a configuracao da integracao deve ser centralizada para evitar cada modulo ter sua propria versao do IXC.

### 5. Visoes, filtros globais e padroes

Deve ficar na Administracao:

- quem pode criar filtro global;
- quem pode editar/excluir filtro global;
- visao padrao por perfil;
- visao padrao por usuario;
- visao padrao por modulo;
- escopo obrigatorio que nenhuma visao pode ampliar.

O usuario ainda pode salvar visoes pessoais dentro do modulo. Mas visoes globais e padroes corporativos sao governanca, entao pertencem a Administracao.

### 6. Auditoria

Deve ficar na Administracao:

- trilha de alteracoes de usuarios;
- alteracoes de perfil/permissao;
- alteracoes de escopo;
- alteracoes de configuracoes criticas;
- imports/exportacoes de configuracao;
- sincronizacoes manuais.

A Gamificacao pode continuar exibindo auditoria de O.S. e pontuacao, porque isso e operacional. Mas auditoria de administracao deve ficar no modulo Administracao.

### 7. Configuracoes da Gamificacao

Devem continuar na Gamificacao:

- grupos de pontuacao;
- assuntos e regras de pontuacao;
- diagnosticos e penalidades;
- regras de SLA;
- regras de reincidencia/garantia;
- fechamento e pagamento;
- multiplicadores de lideranca;
- saldo de pontos.

Podem aparecer na Administracao apenas como resumo ou atalho, porque sao regras de negocio do modulo Gamificacao.

Excecao: permissoes para alterar essas regras devem ser controladas na Administracao.

### 8. Configuracoes da Operacao Analitica

Devem continuar na Operacao:

- modelos de equipe;
- jornada por modelo;
- metas operacionais;
- mapeamento de assuntos operacionais;
- paineis de SLA, backlog, calendario e produtividade.

Podem subir para Administracao no futuro:

- governanca de modelos de equipe;
- relacao oficial pessoa -> modelo de equipe;
- auditoria de mudanca de equipe;
- padroes globais de visualizacao.

### 9. Configuracoes do Agendamento

Devem continuar no Agendamento:

- meta diaria;
- SLA de agendamento;
- expediente usado no calculo;
- equipe de agendamento;
- backlog e eventos.

Podem subir para Administracao:

- quem pode configurar metas;
- quem pode sincronizar IXC;
- filtros globais;
- equipe oficial quando houver cadastro unico de pessoas.

## Classificacao recomendada

| Tipo de controle | Onde deve morar | Motivo |
| --- | --- | --- |
| Usuario, senha, ativo/inativo | Administracao | Identidade e seguranca do ecossistema. |
| Perfil de acesso | Administracao | Evita permissoes duplicadas por modulo. |
| Permissoes | Administracao | Define o que cada perfil pode fazer. |
| Escopo regional | Administracao | E seguranca, nao filtro visual. |
| Vinculo usuario-colaborador | Administracao | Afeta Portal, Gamificacao e supervisao. |
| Cadastro oficial de pessoa | Administracao, com consumo pelos modulos | Evita colaborador duplicado. |
| Regras de pontuacao | Gamificacao | Regra especifica de remuneracao. |
| Fechamento/pagamento | Gamificacao | Operacao financeira do modulo. |
| Modelos de equipe | Operacao, com resumo na Administracao | Regra operacional especifica. |
| Vinculo pessoa-modelo de equipe | Administracao ou Operacao com sincronizacao obrigatoria | Afeta controle do supervisor e Gamificacao. |
| Integracao IXC | Administracao para governanca, modulo para uso operacional | Evita varias configuracoes IXC separadas. |
| Filtros pessoais | Cada modulo | Preferencia individual do usuario. |
| Filtros globais e padroes | Administracao | Governanca compartilhada. |
| Auditoria administrativa | Administracao | Rastreabilidade de acesso e configuracao. |

## Estudo especifico: colaborador da Analitica cadastrado na Gamificacao

Regra desejada:

```text
Todo responsavel com modelo de equipe cadastrado na Analitica deve existir na Gamificacao.
```

Fluxo recomendado:

1. Supervisor vincula responsavel a um modelo de equipe na Analitica.
2. Backend procura colaborador na Gamificacao usando `ixc_employee_id`.
3. Se nao houver ID, usa nome normalizado como fallback.
4. Se encontrar, apenas vincula/atualiza.
5. Se nao encontrar, cria cadastro na Gamificacao.
6. A tela mostra status: cadastrado, pendente, nao encontrado ou conflito.

Decisao de produto pendente:

- criar automaticamente como `is_registered=true`; ou
- criar como pendente para o supervisor confirmar.

Recomendacao inicial:

- criar automaticamente, mas com protecao contra duplicidade por `ixc_employee_id`;
- quando nao houver ID confiavel, mostrar pendencia em vez de criar duplicado automaticamente.

## Riscos de duplicidade

1. Mesmo colaborador com nomes diferentes.
   - Mitigacao: priorizar `ixc_employee_id`.

2. Cadastro na Gamificacao sem correspondente na Analitica.
   - Mitigacao: painel de "Pessoas e vinculos" mostrando origem e status.

3. Usuario de login sem colaborador vinculado.
   - Mitigacao: alerta na Administracao.

4. Perfil antigo `users.role` divergindo dos novos perfis.
   - Mitigacao: Administracao deve ser a fonte oficial; role legado so compatibilidade.

5. Configuracao IXC duplicada por modulo.
   - Mitigacao: painel central de integracoes.

6. Filtro global furando escopo regional.
   - Mitigacao: backend sempre aplica escopo obrigatorio depois dos filtros.

## Abas recomendadas para a Administracao

### Fase 1: consolidar o que ja existe

- Usuarios
- Perfis de acesso
- Permissoes
- Escopos regionais

### Fase 2: evitar duplicidade operacional

- Pessoas e vinculos
- Duplicidades encontradas
- Vinculos com Gamificacao
- Vinculos com Operacao Analitica
- Vinculos com Portal

### Fase 3: governanca do ecossistema

- Integracoes
- Visoes globais
- Padroes por perfil
- Auditoria administrativa

### Fase 4: painel de saude administrativa

- usuarios sem perfil;
- usuarios inativos com perfil;
- colaboradores sem usuario de portal;
- responsaveis da Analitica sem cadastro na Gamificacao;
- pessoas com nome duplicado;
- cadastros sem `ixc_employee_id`;
- modulos com sincronizacao atrasada;
- permissoes sensiveis concentradas em muitos usuarios.

## Permissoes futuras sugeridas

Administracao:

- `admin:users:read`
- `admin:users:write`
- `admin:users:delete`
- `admin:roles:read`
- `admin:roles:write`
- `admin:permissions:read`
- `admin:scopes:read`
- `admin:scopes:write`
- `admin:people:read`
- `admin:people:write`
- `admin:integrations:read`
- `admin:integrations:write`
- `admin:global_views:read`
- `admin:global_views:write`
- `admin:audit:read`

Permissoes sensiveis que devem continuar existindo nos modulos, mas serem concedidas pela Administracao:

- `scoring:write`
- `penalties:write`
- `settings:write`
- `calculation:run`
- `operations:manage_team_models`
- `operations:manage_subjects`
- `operations:sync_ixc`
- `scheduling:manage`
- `scheduling:sync`

## Fronteira recomendada entre Administracao e modulos

Administracao nao deve virar uma tela gigante que edita todas as regras internas dos modulos. Ela deve ser o centro de governanca.

Fronteira recomendada:

- Administracao define quem pode, onde pode, quais vinculos existem e quais configuracoes sao globais.
- Gamificacao define como pontua, penaliza, fecha e paga.
- Operacao define como mede O.S., SLA, backlog, calendario, equipe e produtividade.
- Agendamento define como mede fila, SLA de agendamento, eventos e equipe de agendamento.
- Portal consome os vinculos e permissoes, mas nao administra o ecossistema.

## Plano de implementacao futuro

1. Documentar Administracao como fonte oficial de usuarios, perfis e permissoes.
2. Remover ou redirecionar a tela legada de usuarios dentro da Gamificacao.
3. Criar leitura administrativa de pessoas/vinculos.
4. Mapear responsaveis da Analitica contra colaboradores da Gamificacao.
5. Exibir alertas de duplicidade e pendencias.
6. Criar sincronizacao segura Analitica -> Gamificacao para quem tem modelo de equipe.
7. Centralizar auditoria administrativa.
8. Centralizar governanca de integracoes e visoes globais.

## Decisao recomendada

A Administracao deve ser tratada como o **painel de controle do ecossistema**, nao como mais uma configuracao de modulo.

O caminho mais seguro e:

1. manter regras especificas dentro dos modulos;
2. centralizar identidade, permissoes, escopos, pessoas, vinculos, integracoes e auditoria na Administracao;
3. criar indicadores de duplicidade antes de criar automatismos;
4. automatizar apenas quando houver identificador confiavel, principalmente `ixc_employee_id`.

