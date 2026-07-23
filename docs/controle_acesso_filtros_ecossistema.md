# Controle de acesso e filtros do ecossistema

## Status da implementação regional

- A Administração usa seletor múltiplo de regionais disponíveis na base analítica.
- Cada usuário mantém uma lista normalizada, sem regionais repetidas.
- A lista configurada é aplicada pelo backend como escopo obrigatório em todas as consultas da Operação; filtros e visões salvas não a ampliam.
- Gestor regional sem regional configurada continua sem acesso aos dados operacionais.

## Objetivo

Organizar como o UNI Workspace deve tratar usuários, perfis, permissões, escopos e filtros salvos em todos os módulos do ecossistema, começando por Gamificação e Operação Analítica.

Este documento serve como mapa para o próximo refinamento do módulo de Administração.

## Situação atual

Hoje já existem três peças importantes:

1. Usuários do ecossistema
   - Tabela `users`.
   - Login único.
   - Token usado por Gamificação, Portal e Operação.

2. Perfis de acesso configuráveis
   - Tabela `access_profiles`.
   - Tabela `access_profile_permissions`.
   - Tabela `user_access_profiles`.
   - O campo legado `users.role` continua existindo por compatibilidade.

3. Visões salvas da Operação
   - Tabela `operations_saved_filters`.
   - Cada visão possui `user_id` do criador e `visibility`.
   - `visibility = personal`: visão pessoal do usuário.
   - `visibility = global`: visão global compartilhada.
   - O backend lista as visões pessoais do usuário e as globais quando o perfil possui permissão de leitura global.

## Conceitos

### Filtro aplicado

É o filtro temporário usado naquele momento na tela.

Exemplo:

- Período: julho
- Regional: Jaru
- Tipo geral: Manutenção
- Responsável: João

Esse filtro pode ser alterado livremente enquanto o usuário navega.

### Visão pessoal

É uma combinação de filtros salva apenas para o usuário logado.

Exemplos:

- `Meu SLA crítico`
- `Machadinho — suporte fibra`
- `O.S. sem responsável`

Regra:

- Só o usuário dono vê.
- Só o usuário dono edita.
- Só o usuário dono exclui.

### Visão global

É uma combinação de filtros publicada para outros usuários ou para todo o módulo.

Exemplos:

- `SLA crítico — Diretoria`
- `Backlog geral`
- `Garantia e reincidência`
- `Alta pressão operacional`

Regra:

- Usuários com permissão podem criar/publicar.
- Usuários comuns podem apenas usar.
- Pode ser visível para todos ou para perfis específicos.

### Filtro obrigatório de escopo

É um filtro imposto pela permissão do usuário. Ele não é uma escolha da tela; é segurança.

Exemplos:

- Gestor de Jaru só pode ver Jaru.
- Supervisor de duas filiais só pode ver as duas.
- Colaborador do portal só pode ver seus próprios dados.
- Usuário de Operação pode ver O.S., mas não configurações.

Regra:

- Deve ser aplicado no backend.
- Não pode depender apenas do frontend.
- Na tela pode aparecer como chip bloqueado, exemplo: `Escopo: Jaru`.
- O usuário não consegue remover.

## Como deve funcionar na prática

### Cenário 1: filtro só daquele usuário

O usuário aplica filtros e salva como visão pessoal.

Fluxo:

1. Usuário escolhe os filtros.
2. Clica em `Visões`.
3. Clica em `Salvar como nova visão`.
4. Escolhe `Visão pessoal`.
5. A visão fica disponível apenas para ele.

Banco:

- `owner_user_id = id do usuário`
- `visibility = personal`

Permissão necessária:

- `operations:manage_filters` ou uma permissão futura mais específica:
  - `operations:views:create_personal`

### Cenário 2: filtro global para todos

Admin ou gestor cria uma visão global.

Fluxo:

1. Usuário com permissão escolhe os filtros.
2. Clica em `Salvar como nova visão`.
3. Escolhe `Visão global`.
4. Define o público:
   - Todos;
   - Perfis específicos;
   - Módulo específico;
   - Regionais específicas.

Banco:

- `owner_user_id = id de quem criou`
- `visibility = global`
- `shared_with_profile_ids = [...]`
- `shared_with_user_ids = [...]`, se necessário
- `shared_with_regionals = [...]`, se necessário

Permissões necessárias:

- `operations:views:create_global`
- `operations:views:update_global`
- `operations:views:delete_global`

Observação implementada:

- Quem possui `operations:read` nos perfis padrão da Operação recebe também `operations:views:read_global`.
- Salvar, atualizar ou excluir visão global depende das permissões específicas acima.
- A tela só mostra a opção `Global` para quem possui `operations:views:create_global`.

### Cenário 3: visão padrão ao abrir o módulo

Cada usuário pode ter uma visão padrão.

Exemplo:

- Ao abrir Operação, gestor de Jaru já entra em `Jaru — mês atual`.
- Diretoria entra em `Visão geral — mês atual`.

Regra sugerida:

1. Se o usuário tiver visão padrão pessoal, usar ela.
2. Senão, se o perfil tiver visão padrão, usar ela.
3. Senão, usar padrão do sistema:
   - Período: mês atual.
   - Demais filtros: todos dentro do escopo permitido.

### Cenário 4: filtro global + escopo do usuário

Mesmo uma visão global nunca pode furar o escopo do usuário.

Exemplo:

- Visão global: `Todas as regionais`.
- Usuário tem escopo: `Jaru`.
- Resultado real: só `Jaru`.

Regra:

```text
filtro efetivo = visão selecionada + filtros manuais + escopo obrigatório do usuário
```

O backend sempre aplica o escopo obrigatório por último.

## Modelo de dados recomendado

Evoluir `operations_saved_filters` para suportar visibilidade:

```text
operations_saved_filters
- id
- owner_user_id
- name
- description
- filters
- visibility
  - personal
  - global
  - profile
  - user
- module_key
  - operations
- is_default
- active
- created_at
- updated_at
```

Criar tabela para compartilhamento por perfil:

```text
saved_filter_profiles
- id
- saved_filter_id
- profile_id
```

Opcionalmente criar tabela para compartilhamento por usuário:

```text
saved_filter_users
- id
- saved_filter_id
- user_id
```

Opcionalmente criar tabela para escopo regional da visão:

```text
saved_filter_regionals
- id
- saved_filter_id
- regional
```

## Permissões futuras para visões e filtros

Operação Analítica:

- `operations:views:read_personal`
- `operations:views:create_personal`
- `operations:views:update_personal`
- `operations:views:delete_personal`
- `operations:views:read_global`
- `operations:views:create_global`
- `operations:views:update_global`
- `operations:views:delete_global`
- `operations:views:set_default`

Administração:

- `admin:scopes:read`
- `admin:scopes:write`
- `admin:default_views:read`
- `admin:default_views:write`

## Escopos recomendados por usuário/perfil

O escopo deve poder ser configurado por:

- Módulo;
- Regional;
- Empresa/filial;
- Setor;
- Modelo de equipe;
- Colaborador;
- Tipo de ação.

Exemplo:

```json
{
  "module": "operations",
  "regionals": ["UNI - JARU", "UNI - MACHADINHO DOESTE"],
  "team_models": ["SUPORTE MOTO", "SUPORTE CARRO"],
  "can_see_order_details": true,
  "can_sync_ixc": false
}
```

## Comportamento visual recomendado

### Barra de filtros

Manter:

- Filtros manuais da tela;
- Visões salvas;
- Limpar filtros.

Adicionar:

- Separação entre:
  - `Minhas visões`;
  - `Visões globais`;
  - `Padrões do sistema`.

### Chips de filtro

Separar chips em três tipos:

1. Filtro manual removível
   - Exemplo: `Assunto: Instalação ×`

2. Filtro vindo de visão salva
   - Exemplo: `Visão: SLA crítico`

3. Escopo obrigatório bloqueado
   - Exemplo: `Escopo: Jaru 🔒`

### Ao clicar em limpar

`Limpar filtros` deve remover apenas filtros manuais.

Não deve remover:

- Escopo obrigatório;
- Visão padrão, se configurada como obrigatória;
- Permissões do usuário.

## Regras de segurança

- Visão global não dá acesso a dados fora do escopo do usuário.
- Frontend pode esconder opções, mas backend sempre valida.
- Endpoints de listagem precisam aplicar escopo obrigatório.
- Endpoints de detalhe de O.S. também precisam aplicar escopo.
- Exportação deve aplicar os mesmos filtros e escopos da tela.

## Próximo refinamento recomendado

Fase 1:

- [x] Adicionar `visibility` em `operations_saved_filters`.
- [ ] Renomear internamente `user_id` para `owner_user_id`, mantendo compatibilidade.
- [x] Exibir visão pessoal/global no frontend.
- [x] Criar permissões de visão global.
- [x] Permitir parametrizar no perfil se o usuário pode salvar visão global.

Fase 2:

- Permitir visão padrão por usuário.
- Permitir visão padrão por perfil.
- Mostrar chip bloqueado de escopo obrigatório.

Fase 3:

- Criar tela de escopos dentro de Administração.
- Permitir escopo por módulo, regional, filial, setor, modelo de equipe e colaborador.
- Aplicar escopo obrigatório em todos os endpoints sensíveis.

Fase 4:

- Generalizar visões salvas para outros módulos, não só Operação.
- Criar uma tabela `workspace_saved_views`.
