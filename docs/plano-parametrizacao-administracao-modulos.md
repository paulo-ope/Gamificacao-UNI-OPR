# Plano: Administracao, parametrizacao e visibilidade dos modulos

## Objetivo

Registrar a direcao de produto e arquitetura para a Administracao virar o painel de controle do ecossistema, sem misturar regras de um modulo dentro de outro e sem mostrar telas para usuarios que nao vao usar.

Este plano complementa:

- `docs/estudo-administracao-controles-ecossistema.md`
- `docs/controle_acesso_filtros_ecossistema.md`
- `docs/estudo-kpis-agendamento.md`
- `docs/evolucao_modulo_operacional_integrado.md`

## Decisao principal

Todo modulo novo deve nascer com tres capacidades obrigatorias:

1. Parametrizacao propria.
2. Controle de acesso por permissao/perfil.
3. Controle de visibilidade para esconder o modulo de usuarios que nao precisam dele.

Na pratica, o usuario so deve ver um modulo quando:

- o modulo estiver ativo;
- o usuario tiver permissao minima para acessar;
- o perfil do usuario nao estiver bloqueado para aquele modulo;
- se houver regra individual, o usuario nao estiver ocultado explicitamente.

Isso evita que colaboradores vejam abas que nao fazem parte da rotina deles e fiquem perguntando o que e cada coisa.

## Papel da Administracao

A Administracao deve ser o centro de governanca do sistema, nao apenas uma tela de usuarios.

Ela deve controlar:

- usuarios;
- perfis de acesso;
- permissoes;
- vinculo de usuario com colaborador;
- CPF e dados cadastrais sensiveis, com mascara e cuidado de acesso;
- supervisor direto;
- gerente regional;
- tipo de equipe;
- tipo de colaborador;
- modulos visiveis por perfil;
- parametros globais;
- parametros dos modulos;
- integracoes;
- auditoria administrativa.

Regra importante: a Administracao governa quem pode acessar e quais parametros podem ser alterados. O modulo continua dono da sua regra de negocio operacional.

## Abas recomendadas para Administracao

### 1. Usuarios

Cadastro e manutencao de acesso ao sistema.

Campos desejados:

- nome;
- e-mail/login;
- status ativo/inativo;
- perfil de acesso;
- foto;
- CPF, com exibicao mascarada;
- colaborador IXC vinculado;
- regional;
- supervisor direto;
- gerente regional;
- tipo de colaborador.

### 2. Perfis e permissoes

Controle de quais acoes cada perfil pode executar.

Exemplos:

- ver Gestao;
- administrar estrutura;
- alterar parametrizacao;
- importar dados;
- ver dados globais;
- ver apenas propria equipe;
- editar usuarios.

### 3. Pessoas e estrutura

Cadastro organizacional dos colaboradores, separado do login.

Um colaborador pode existir como pessoa mesmo sem ter usuario para entrar no sistema. Isso permite monitorar tecnicos, operadores, supervisores e colaboradores sem obrigar login para todos.

Campos recomendados:

- nome;
- CPF;
- matricula ou codigo interno;
- ID do colaborador no IXC;
- regional;
- setor;
- tipo de equipe;
- supervisor;
- gerente regional;
- status operacional;
- data de entrada;
- data de desligamento, quando houver.

### 4. Modulos

Controle dos modulos existentes no ecossistema.

Cada modulo deve ter:

- chave tecnica, por exemplo `management`, `scheduling`, `operations`, `gamification`;
- nome exibido;
- descricao curta;
- rota no sistema;
- permissao minima de acesso;
- status: ativo, em teste, oculto ou desativado;
- perfis que podem visualizar;
- usuarios bloqueados ou liberados individualmente, quando necessario;
- indicador se o modulo e parametrizavel.

### 5. Parametrizacoes

Tela moderna para configurar regras sem precisar alterar codigo.

A Administracao deve exibir uma area central de parametrizacao, mas cada parametro continua associado ao modulo correto.

Exemplos de grupos:

- Gamificacao;
- Operacao Analitica;
- Agendamento;
- Gestao;
- Integracoes;
- Notificacoes;
- IA e analises.

### 6. Integracoes

Controle de conexoes externas, como IXC e futuras APIs internas.

Aqui devem ficar:

- status da integracao;
- ultima sincronizacao;
- credenciais somente no backend e `.env`;
- configuracoes de origem;
- logs resumidos sem dados sensiveis.

### 7. Auditoria

Registro de mudancas administrativas.

Deve guardar:

- quem alterou;
- o que alterou;
- valor anterior;
- valor novo;
- data e hora;
- origem da alteracao.

### 8. Solicitacoes de acesso

Fluxo futuro para colaborador solicitar cadastro com seguranca.

O colaborador pode preencher um pre-cadastro, mas nao deve ganhar acesso automaticamente sem validacao.

Fluxo recomendado:

1. colaborador informa CPF, nome, e-mail e setor;
2. sistema tenta localizar colaborador existente;
3. se encontrar, cria solicitacao pendente;
4. supervisor, RH ou administracao aprova;
5. somente depois o usuario e criado ou liberado;
6. tudo fica auditado.

## Papel da aba Gestao

A aba Gestao deve ser documentada como modulo de acompanhamento e decisao.

Ela deve servir para:

- ver colaboradores de operacao;
- identificar quem esta sem supervisor;
- identificar quem esta sem modelo de equipe;
- acompanhar estrutura por regional;
- apoiar justificativas de metas e desempenho;
- mostrar pendencias para supervisores e matriz;
- consolidar pontos de atencao.

Ela nao deve virar uma segunda Administracao. A Gestao acompanha, cobra, alerta e ajuda a tomar decisao. A Administracao cadastra, parametriza e governa.

## Separacao entre Gamificacao e Agendamento

O Agendamento nao deve ficar misturado com a parametrizacao da Gamificacao.

### Gamificacao

Parametros da Gamificacao:

- regras de pontuacao;
- grupos de assunto;
- penalidades;
- reincidencia;
- garantia;
- fechamento de periodo;
- valor financeiro do ponto;
- regras de pagamento;
- regras de saldo.

### Agendamento

Parametros do Agendamento:

- SLA de primeiro agendamento;
- meta diaria por operador;
- equipe de agendamento;
- horarios de trabalho;
- tipos de evento do IXC que contam como agendamento;
- regras de reagendamento;
- backlog sem agendamento;
- janelas e tolerancias;
- filtros padrao da tela de agendamento.

### Integracao compartilhada

O que pode ser compartilhado entre modulos:

- conexao IXC;
- credenciais protegidas;
- ultima sincronizacao;
- mapeamento geral de regionais;
- identificadores externos oficiais.

O que nao deve ser compartilhado:

- regra de pontuacao da Gamificacao;
- meta do Agendamento;
- tela de parametrizacao de um modulo dentro de outro;
- permissao operacional especifica de um modulo usada para controlar outro.

## Modelo tecnico recomendado para parametrizacao

Uma estrutura futura pode seguir este formato:

```text
module_parameters
- id
- module_key
- parameter_key
- label
- description
- value_type
- value_json
- default_value_json
- required
- editable
- sensitive
- validation_schema
- visible_to_profiles
- updated_by
- updated_at
```

Regras:

- parametro sensivel nunca aparece aberto no frontend;
- alteracao critica exige permissao;
- toda mudanca gera auditoria;
- validacao acontece no backend;
- parametros devem ter valor padrao seguro;
- cada parametro pertence a um modulo.

## Modelo tecnico recomendado para visibilidade

Uma estrutura futura pode seguir este formato:

```text
workspace_module_visibility
- id
- module_key
- profile_id
- user_id
- visible
- reason
- updated_by
- updated_at
```

Regra de exibicao:

```text
Modulo aparece = ativo + usuario tem permissao + perfil pode ver + usuario nao esta ocultado
```

Isso permite esconder, por exemplo, Gestao ou Administracao de colaboradores comuns.

## Tipos organizacionais recomendados

Para facilitar filtro e controle, o cadastro de pessoa deve ter classificacoes simples:

- tecnico de campo;
- equipe de campo;
- agendamento;
- suporte interno;
- supervisor;
- gerente regional;
- matriz;
- administrativo;
- outro.

O tipo de equipe tambem deve ser separado:

- campo;
- agendamento;
- suporte interno;
- regional;
- administrativo.

Assim, modelo de equipe de campo nao se mistura com operador de agendamento ou suporte interno.

## Plano de implementacao em fases

### Fase 1 - Documentacao e alinhamento

- Registrar este plano. Concluido em 2026-07-30.
- Revisar o que ja existe na Administracao. Concluido em 2026-07-30.
- Reorganizar a tela da Administracao em abas de governanca. Concluido em 2026-07-30.
- Confirmar quais perfis devem ver cada modulo.
- Confirmar quais parametros de Agendamento estao misturados ou confusos.

### Fase 2 - Administracao de pessoas e estrutura

- Evoluir cadastro de usuario para vincular colaborador, CPF, foto, supervisor, gerente regional e tipo de equipe. Parcialmente concluido em 2026-07-30: a estrutura passou a ficar no cadastro do colaborador, com CPF mascarado na API administrativa.
- Criar visao de colaboradores sem supervisor. Parcialmente concluido em 2026-07-30 para colaboradores de equipe de campo.
- Criar visao de colaboradores sem modelo de equipe. Parcialmente concluido em 2026-07-30 usando o tipo de equipe.
- Integrar Gestao e Administracao. Parcialmente concluido em 2026-07-30: a Gestao passa a refletir supervisor/status estrutural do colaborador e abre a Administracao filtrada para correcao.
- Garantir que o backend valide tudo.

### Fase 3 - Modulos e visibilidade

- Criar controle administrativo de modulos. Parcialmente concluido em 2026-07-30.
- Permitir ocultar modulo por perfil. Concluido em 2026-07-30 para a Home do ecossistema.
- Permitir liberar ou ocultar usuario especifico.
- Atualizar home do ecossistema para respeitar a visibilidade. Concluido em 2026-07-30.

### Fase 4 - Parametrizacoes modernas

- Criar tela central de Parametrizacoes na Administracao.
- Separar parametros por modulo.
- Padronizar campos, validacoes e auditoria.
- Comecar pelos parametros ja existentes.

### Fase 5 - Separar Agendamento da Gamificacao

- Mapear parametros atuais do Agendamento.
- Mover o que for do Agendamento para grupo proprio.
- Manter Gamificacao apenas com regras de pontuacao e pagamento.
- Validar se nenhuma tela depende de parametro errado.

### Fase 6 - Cadastro seguro pelo proprio colaborador

- Criar pre-cadastro sem acesso imediato.
- Exigir aprovacao de supervisor, RH ou Administracao.
- Validar CPF e vinculo com colaborador existente.
- Registrar auditoria.

## Riscos e protecoes

| Risco | Protecao |
| --- | --- |
| Poluir a Administracao com regra de todos os modulos | Administracao edita parametros; regra operacional continua no modulo |
| Quebrar banco de dados | Usar migrations aditivas e sem apagar dados |
| Expor CPF ou dados sensiveis | Mascarar no frontend e validar permissao no backend |
| Mostrar modulo para usuario errado | Visibilidade por perfil e permissao no backend/frontend |
| Misturar Agendamento com Gamificacao | Separar `module_key` e grupos de parametrizacao |
| Alteracao critica sem rastreio | Auditoria obrigatoria |
| Auto-cadastro inseguro | Pre-cadastro pendente de aprovacao |

## Criterio de pronto

Este plano estara implementado quando:

- a Administracao tiver abas claras para Usuarios, Perfis, Pessoas/Estrutura, Modulos, Parametrizacoes, Integracoes e Auditoria;
- cada modulo declarar se e parametrizavel;
- cada parametro pertencer a um modulo;
- Agendamento tiver parametrizacao propria;
- Gamificacao nao carregar configuracoes operacionais de Agendamento;
- usuarios comuns so enxergarem os modulos autorizados;
- colaboradores sem supervisor ou sem modelo de equipe aparecerem como pendencia para a Gestao;
- alteracoes sensiveis ficarem auditadas.
