# API — Administração (`/api/admin`)

> Fonte: `backend/app/modules/admin/router.py`, `schemas.py`, `models.py` (tabelas em
> `app/models.py`) e `backend/app/modules/ai_governance/router.py`, `schemas.py`, `models.py`,
> `bootstrap.py`. Documento gerado a partir do código em 2026-09-16 — se divergir do código no
> futuro, o código vence (ver `docs/00-TRILHA-0.md`).

## Visão geral

O módulo **Administração** (rota web `/admin`, prefixo de API `/api/admin`) é o módulo de
governança de acesso do ecossistema UNI Workspace. Ele concentra:

- o catálogo de **permissões** do sistema (as strings `modulo:recurso:acao` que toda rota de
  todo módulo usa em `require_permission(...)`);
- a **visibilidade dos módulos** do workspace por perfil e por usuário individual (o que aparece
  no menu/roteamento do frontend);
- a **estrutura de pessoas** (colaboradores do IXC vinculados a um usuário de portal, hierarquia
  de supervisor/gerente regional, tipo de equipe);
- os **perfis de acesso** (`AccessProfile`), que agrupam permissões e são atribuídos a usuários;
- **overrides individuais de permissão** por usuário (conceder ou negar uma permissão específica
  sem mexer no perfil compartilhado da pessoa).

Dentro do mesmo módulo, com prefixo próprio `/api/admin/ai-governance`, vive o sub-escopo
**AI Governance**: a tela onde a Administração decide o que uma IA (agente conectado via MCP ou
via API key) pode consultar — quais endpoints/tools estão ligados, quais campos de cada entidade
são expostos, quais perfis têm restrição adicional, quais tokens de API existem, e o log de
auditoria de cada chamada feita por uma IA.

**Importância arquitetural:** este é o único módulo que **atribui as próprias permissões usadas
por todos os outros módulos**. `require_permission("operations:read")`,
`require_permission("support:write")`, etc., em qualquer outra rota do sistema, dependem de que
alguém aqui tenha: (1) criado/mantido a permissão no catálogo, (2) incluído essa permissão num
`AccessProfile`, e (3) atribuído esse perfil ao usuário (ou concedido um override individual). Se
a Administração ficar inacessível, nenhuma outra permissão do ecossistema pode ser
criada/ajustada — por isso existe uma trava específica (`ADMIN_GATEKEEPER_PERMISSION`, ver seção
de Perfis de Acesso) impedindo que o último perfil que concede `admin:users:write` seja excluído
ou inativado.

## Autenticação e permissões

Todas as rotas de `/api/admin` e `/api/admin/ai-governance` usam o esquema padrão de sessão do
ecossistema: `Authorization: Bearer <JWT>` obtido em `/api/auth/login`, validado por
`get_current_user` (`backend/app/core/security.py`). Cada rota individual usa
`Depends(require_permission("<chave>"))`, que:

1. resolve o usuário autenticado (`get_current_user`);
2. calcula a permissão efetiva dele (`permissions_for_user` = permissões do perfil ativo, ou do
   papel legado se não houver perfil, **mais** overrides de concessão, **menos** overrides de
   negação — negação sempre vence);
3. responde `403` se a chave exigida não estiver no conjunto efetivo.

Não há verificação adicional de escopo por regional ou por dado individual neste módulo — a
granularidade de acesso aqui é por permissão, não por linha de dado (diferente de outros módulos
operacionais que também filtram por regional do usuário).

Chaves de permissão usadas nas rotas deste documento (todas verificadas apenas no backend, nunca
só no frontend, conforme `AGENTS.md`):

| Chave | Usada em |
|---|---|
| `admin:permissions:read` / `admin:permissions:write` | Catálogo de permissões |
| `admin:modules:read` / `admin:modules:write` | Visibilidade de módulos do workspace |
| `admin:users:read` / `admin:users:write` | Regionais, estrutura de pessoas, overrides de permissão por usuário |
| `admin:roles:read` / `admin:roles:write` | Perfis de acesso |
| `admin:ai_governance:read` / `admin:ai_governance:write` | Endpoints, campos e grants de IA |
| `admin:ai_tokens:manage` | Emissão e revogação de tokens de API de IA |

`admin:users:write` é a **permissão-trava** do ecossistema (`ADMIN_GATEKEEPER_PERMISSION` em
`router.py`): o último perfil ativo que a concede não pode ser excluído nem inativado, para o
ecossistema nunca ficar sem ninguém capaz de administrar acesso.

## Endpoints — Administração

### Permissões

Catálogo unificado: permissões declaradas em código (`PERMISSION_LABELS`, fixas, só
revogáveis dos perfis) + permissões próprias criadas pela tela (`CustomPermission`, editáveis e
excluíveis).

| Método + path | Descrição | Parâmetros | Permissão | Resposta |
|---|---|---|---|---|
| `GET /permissions` | Lista o catálogo completo, com uso atual de cada permissão (quantos perfis/usuários a têm, quantos overrides individuais existem). | — | `admin:permissions:read` | `EcosystemPermissionOut[]` |
| `POST /permissions` | Cria uma permissão própria (não declarada em código). | Body `CustomPermissionCreate`: `key`, `label`, `module_key?`, `description?`, `sensitive` | `admin:permissions:write` | `201` `EcosystemPermissionOut` |
| `PUT /permissions/{permission_key}` | Atualiza rótulo/módulo/descrição/sensibilidade/ativo de uma permissão própria. Chave nunca muda. | Path `permission_key`; body `CustomPermissionUpdate` (campos parciais) | `admin:permissions:write` | `EcosystemPermissionOut` |
| `DELETE /permissions/{permission_key}` | Exclui uma permissão própria. Permissão de código (`PERMISSION_LABELS`) não pode ser excluída — só removida dos perfis. | Path `permission_key` | `admin:permissions:write` | `204` |

`EcosystemPermissionOut` traz `custom` (própria vs. de código), `profile_count`, `user_count`,
`profile_names` e `override_count`, para a tela mostrar o impacto antes de revogar/excluir.

### Visibilidade de Módulos (workspace)

Controla quais módulos aparecem para quais perfis/usuários — independente da permissão
funcional exigida pela rota do módulo (ver aviso em `AdminModuleSettingsUpdate`: mudar a
permissão mínima do módulo pela tela deixaria o módulo visível para quem as rotas recusam com
`403`, por isso rota web, prefixo de API e permissão mínima **não** são editáveis por aqui).

| Método + path | Descrição | Parâmetros | Permissão | Resposta |
|---|---|---|---|---|
| `GET /modules` | Lista todos os módulos do `registry.py`, com visibilidade calculada por perfil e por overrides de usuário. | — | `admin:modules:read` | `AdminWorkspaceModuleOut[]` |
| `PUT /modules/{module_key}/settings` | Ajusta nome/descrição/status/ordem de apresentação do módulo. Campo enviado vazio/nulo restaura o padrão do `registry.py`. | Path `module_key`; body `AdminModuleSettingsUpdate` | `admin:modules:write` | `AdminWorkspaceModuleOut` |
| `PUT /modules/{module_key}/visibility` | Define se o módulo é visível para um perfil de acesso. | Path `module_key`; body `AdminModuleVisibilityUpdate`: `profile_id`, `visible`, `reason?` | `admin:modules:write` | `AdminWorkspaceModuleOut` |
| `PUT /modules/{module_key}/user-visibility` | Cria/atualiza uma exceção de visibilidade para UM usuário específico (sobrepõe o que o perfil dele definiria). | Path `module_key`; body `AdminModuleUserVisibilityUpsert`: `user_id`, `visible`, `reason?` | `admin:modules:write` | `AdminWorkspaceModuleOut` |
| `DELETE /modules/{module_key}/user-visibility/{user_id}` | Remove a exceção individual; o usuário volta a seguir a visibilidade do perfil dele. | Path `module_key`, `user_id` | `admin:modules:write` | `AdminWorkspaceModuleOut` |

Toda escrita nesta seção grava em `record_audit_log` (tabelas `workspace_module_settings` /
`workspace_module_visibility`).

### Estrutura de Pessoas

| Método + path | Descrição | Parâmetros | Permissão | Resposta |
|---|---|---|---|---|
| `GET /operation-regionals` | Regionais distintas e normalizadas encontradas na base analítica de O.S. (`OperationOrder`), para popular seletor de escopo regional em outras telas. | — | `admin:users:read` | `string[]` |
| `GET /people-structure` | Lista completa de colaboradores com resumo (total, ativos, sem supervisor, sem tipo de equipe, pendentes de revisão, por tipo de equipe), opções de supervisor/gerente regional e os enums válidos (`employee_types`, `team_types`, `statuses`). | — | `admin:users:read` | `AdminPeopleStructureOut` |
| `PATCH /people-structure/{collaborator_id}` | Atualiza CPF, tipo de colaborador/equipe, status/observações de estrutura, supervisor e gerente regional de UM colaborador. Campos enviados são parciais (`exclude_unset`). | Path `collaborator_id`; body `AdminPersonStructureUpdate` | `admin:users:write` | `AdminPersonStructureOut` |

Enums válidos (fixos em `router.py`, não editáveis pela tela):
- `employee_type`: `field_technician`, `scheduling_operator`, `internal_support`, `supervisor`,
  `regional_manager`, `headquarters`, `administrative`, `other`.
- `team_type`: `field`, `scheduling`, `internal_support`, `regional`, `administrative`,
  `headquarters`, `other`.
- `structure_status`: `pending_review`, `validated`, `needs_fix`, `outside_operation`,
  `inactive`.

CPF é mascarado na resposta (`cpf_masked`); nunca retornado em texto pleno por esta rota.

### Perfis de Acesso

`AccessProfile` agrupa um conjunto de chaves de permissão e é atribuído a um ou mais usuários
(`UserAccessProfile`). Substituiu o antigo "papel" (`role`) fixo por usuário — usuário sem
nenhum perfil ativo ainda cai no conjunto de permissões do papel legado (compatibilidade).

| Método + path | Descrição | Parâmetros | Permissão | Resposta |
|---|---|---|---|---|
| `GET /access-profiles` | Lista todos os perfis, com contagem de usuários vinculados. | — | `admin:roles:read` | `AccessProfileOut[]` |
| `POST /access-profiles` | Cria um perfil novo. Nome único (case-insensitive). | Body `AccessProfileCreate`: `name`, `description?`, `active`, `permission_keys[]` | `admin:roles:write` | `201` `AccessProfileOut` |
| `PUT /access-profiles/{profile_id}` | Atualiza nome/descrição/ativo/permissões do perfil. Inativar o **último** perfil ativo que concede `admin:users:write` é bloqueado (`409`) pelo mesmo motivo da exclusão, abaixo. | Path `profile_id`; body `AccessProfileUpdate` (parcial) | `admin:roles:write` | `AccessProfileOut` |
| `DELETE /access-profiles/{profile_id}` | Exclui um perfil, inclusive um perfil de sistema (`is_system`). Se houver usuários vinculados, exige `reassign_profile_id` (query) — move as pessoas para o perfil de destino na mesma transação. Bloqueado (`409`) se for o último perfil ativo que concede `admin:users:write` (trava anti-lockout). | Path `profile_id`; query `reassign_profile_id?` | `admin:roles:write` | `AccessProfileOut` (estado do perfil excluído, com `user_count` antes da exclusão) |

`AccessProfileOut.delete_blocked_reason` informa, quando aplicável, por que o perfil não pode
ser excluído agora (a tela mostra o motivo em vez de só esconder o botão).

### Overrides de Permissão por Usuário

Permite conceder ou negar UMA permissão específica para uma pessoa, sem criar um perfil
individual nem alterar o perfil compartilhado dela. Negação individual sempre vence concessão do
perfil; concessão individual só soma.

| Método + path | Descrição | Parâmetros | Permissão | Resposta |
|---|---|---|---|---|
| `GET /users/{user_id}/permissions` | O que o perfil da pessoa concede, as exceções (overrides) dela e o resultado efetivo — o mesmo cálculo que `permissions_for_user` roda em toda checagem de permissão do sistema. | Path `user_id` | `admin:users:read` | `UserPermissionOverviewOut` |
| `PUT /users/{user_id}/permissions/{permission_key}` | Cria ou substitui o override desta permissão para o usuário. Idempotente por chave: chamar de novo com efeito diferente TROCA a exceção em vez de empilhar. | Path `user_id`, `permission_key`; body `UserPermissionOverrideUpsert`: `effect` (`grant`\|`deny`), `reason?` | `admin:users:write` | `UserPermissionOverviewOut` |
| `DELETE /users/{user_id}/permissions/{permission_key}` | Remove o override; a pessoa volta a ter exatamente o que o perfil dela concede. | Path `user_id`, `permission_key` | `admin:users:write` | `UserPermissionOverviewOut` |

## Endpoints — AI Governance (`/api/admin/ai-governance`)

Este sub-escopo governa o que uma IA (agente MCP conectado, ou chamada autenticada por
`x-api-key` em `/api/ai/*`) pode ler. Ele não expõe `/api/ai` em si — apenas administra as
tabelas que o *gate* de `/api/ai` e das tools MCP consulta antes de responder qualquer chamada
(ver `app/modules/ai_governance/policy.py` e `gate.py`). Toda escrita aqui chama
`bump_policy_version(db)`, que faz o efeito valer imediatamente (sem reiniciar o processo), e
`record_audit_log` (mesma trilha de auditoria administrativa do restante do módulo `admin`).

No primeiro boot da aplicação, `bootstrap.ensure_ai_governance_seed` semeia `AiEndpoint` e
`AiFieldPermission` com o inventário de endpoints/tools que já existiam (todos entram
habilitados, replicando o comportamento anterior à governança) e capacidades genuinamente novas
que ainda não tinham sido exibidas em produção (entram desabilitadas até a Administração decidir
liberar — ex.: `operations.network.logins`, `operations.network.onu_signal`,
`ai.management_justifications`). O seed é idempotente e nunca sobrescreve uma linha já
configurada manualmente pela Administração.

### Grants de Endpoint/Campo de IA

| Método + path | Descrição | Parâmetros | Permissão | Resposta |
|---|---|---|---|---|
| `GET /endpoints` | Lista todos os endpoints/tools governáveis (`AiEndpoint`), ordenados por chave. | — | `admin:ai_governance:read` | `AiEndpointOut[]` |
| `PATCH /endpoints/{endpoint_key}` | Liga/desliga um endpoint/tool nas três dimensões independentes: `enabled_api` (rotas REST `/api/ai/...`), `enabled_mcp` (tools MCP), `enabled_ai` (chave-mestra geral). | Path `endpoint_key`; body `AiEndpointUpdate` (campos parciais, `extra="forbid"`) | `admin:ai_governance:write` | `AiEndpointOut` |
| `GET /fields` | Lista o estado administrável de cada campo de cada entidade exposta a IA (filtro opcional por entidade). Completa sob demanda qualquer campo novo do catálogo (`field_registry`) que ainda não tenha linha, para a tela nunca mostrar "campo inexistente". | Query `entity?` | `admin:ai_governance:read` | `AiFieldPermissionOut[]` |
| `PATCH /fields/{entity}/{field}` | Ajusta as capacidades do campo: `filterable`, `text_filterable`, `groupable`, `returnable`, `selectable`, `detail_available`, e a chave-mestra `enabled` (campo indisponível quando `False`, independente das demais capacidades). `sensitive` fica fora deste schema de propósito — é calculado pelo catálogo, não um toggle administrativo. | Path `entity`, `field`; body `AiFieldPermissionUpdate` (parcial, `extra="forbid"`) | `admin:ai_governance:write` | `AiFieldPermissionOut` |
| `GET /profiles/{profile_id}/endpoint-grants` | Lista as restrições adicionais de endpoint para um `AccessProfile` (ausência de linha = sem restrição extra; presença de ao menos uma linha liga o perfil a um modo allow-list para os endpoints listados). | Path `profile_id` | `admin:ai_governance:read` | `AiProfileEndpointGrantOut[]` |
| `PUT /profiles/{profile_id}/endpoint-grants/{endpoint_key}` | Cria/atualiza a restrição de um endpoint para o perfil. | Path `profile_id`, `endpoint_key`; body `AiProfileEndpointGrantUpsert`: `granted` | `admin:ai_governance:write` | `AiProfileEndpointGrantOut` |
| `DELETE /profiles/{profile_id}/endpoint-grants/{endpoint_key}` | Remove a restrição (volta ao comportamento geral de `AiEndpoint`). | Path `profile_id`, `endpoint_key` | `admin:ai_governance:write` | `204` |
| `GET /profiles/{profile_id}/field-grants` | Lista as restrições adicionais de campo para o perfil. | Path `profile_id` | `admin:ai_governance:read` | `AiProfileFieldGrantOut[]` |
| `PUT /profiles/{profile_id}/field-grants` | Cria/atualiza a restrição de um campo (`entity`+`field`) para o perfil — por exemplo, liberar um campo sensível só para o perfil Gestor mesmo que esteja `enabled=True` no geral. | Path `profile_id`; body `AiProfileFieldGrantUpsert`: `entity`, `field`, `granted` | `admin:ai_governance:write` | `AiProfileFieldGrantOut` |
| `DELETE /profiles/{profile_id}/field-grants/{entity}/{field}` | Remove a restrição de campo do perfil. | Path `profile_id`, `entity`, `field` | `admin:ai_governance:write` | `204` |

Perfis reaproveitam o `AccessProfile` já existente do módulo Administração — não há uma
hierarquia de perfil paralela para IA.

### Tokens de API

Uma chamada a `/api/ai/*` autentica por header `x-api-key` (`APIKeyHeader`, não Bearer/JWT). O
gate (`app/modules/ai/auth.py`) reconhece dois tipos de credencial, combinados nesta listagem:

- **`AiApiToken`** (`source: "token"`) — modelo atual (Fase 5 do plano de migração), com escopo
  (`scopes[]`) e expiração opcional (`expires_at`). É o que estas rotas emitem/revogam.
- **`ApiKeyCredential`** (`source: "legacy"`) — chaves emitidas antes da Fase 5, sem conceito de
  escopo (`scopes: null` = acesso irrestrito, nunca bloqueado por `enforce_token_scope`).
  Continuam listadas e revogáveis aqui para preservar o acesso já concedido, mas novas emissões
  usam sempre `AiApiToken`.

Todo token é emitido em nome de um **usuário de serviço** compartilhado
(`ai-service@internal.souuni.com`, papel `ai_service`), criado sob demanda na primeira emissão.
O escopo real de cada token vem de `AiApiToken.scopes`, não deste usuário — não há um usuário de
serviço por token.

| Método + path | Descrição | Parâmetros | Permissão | Resposta |
|---|---|---|---|---|
| `GET /tokens` | Lista tokens `AiApiToken` + chaves legado `ApiKeyCredential`, combinados e ordenados por data de criação (mais recente primeiro). | — | `admin:ai_governance:read` | `AiApiKeyOut[]` |
| `POST /tokens` | Emite um token novo. Gera a chave bruta com `secrets.token_urlsafe(32)`, grava só o hash (`hash_api_key`) e o prefixo (12 chars, usado para localizar candidatos sem varrer a tabela inteira). | Body `AiApiKeyCreate`: `name`, `scopes[]` (subconjunto de `AI_API_TOKEN_SCOPES`), `expires_in_days?` (1–3650) | `admin:ai_tokens:manage` | `201` `AiApiKeyCreateResponse` (`key` + `raw_key`) |
| `DELETE /tokens/{source}/{token_id}` | Revoga um token (`source="token"`) ou uma chave legado (`source="legacy"`): marca `active=False` e grava `revoked_at`. | Path `source` (`token`\|`legacy`), `token_id` | `admin:ai_tokens:manage` | `AiApiKeyOut` |

Escopos válidos hoje (`AI_API_TOKEN_SCOPES`): `orders.read`, `orders.detail`, `orders.sla`,
`orders.aggregate`, `infra.read`, `users.read`, `management.read`. Só `orders.read` e
`orders.detail` são de fato checados hoje (`enforce_token_scope`, em `opr_search_orders` e
`opr_order_details`) — os demais existem reservados para quando outras rotas passarem a validar
escopo, sem exigir migration nova (a coluna já é uma lista livre).

**A chave bruta (`raw_key`) só aparece nesta resposta de criação — não fica recuperável depois**
(o banco grava apenas o hash). A tela/cliente precisa copiá-la e guardá-la na hora.

### Logs de Auditoria de Acesso

| Método + path | Descrição | Parâmetros | Permissão | Resposta |
|---|---|---|---|---|
| `GET /audit-logs` | Lista chamadas de IA registradas em `AiAccessAuditLog`, mais recentes primeiro. Nunca grava o conteúdo sensível retornado — `filters_summary` guarda só nomes de campo e quantidade de valores, não os valores em si. | Query `origin?`, `endpoint_key?`, `status?`, `limit` (1–500, padrão 100) | `admin:ai_governance:read` | `AiAccessAuditLogOut[]` |

Cada linha traz: usuário e/ou token associado (nome/e-mail resolvidos), origem (`api`\|`mcp`),
`endpoint_key`, resumo de filtros aplicados, campos solicitados, modo de resposta, quantidade de
resultados, duração em ms, status (`success`/erro) e mensagem de erro quando houver.

### Como um grant/token aqui habilita uma chamada em `/api/ai`

Quando um agente de IA chama `/api/ai/...` com `x-api-key`, o fluxo passa por estas camadas,
todas alimentadas pelas tabelas que este sub-módulo administra:

1. **Autenticação da chave** (`ai/auth.py:_resolve_api_key_context`): resolve a chave contra
   `AiApiToken` (nova) ou `ApiKeyCredential` (legado) pelo prefixo + hash; rejeita chave
   revogada/expirada/inativa.
2. **Escopo do token** (`enforce_token_scope`): se o token tem `scopes` definidos, a rota
   individual (hoje só as duas citadas acima) exige que o escopo pedido esteja na lista.
3. **Permissão funcional do usuário de serviço** (`require_ai_permission` /
   `permissions_for_user`): a mesma checagem de permissão do resto do sistema, aplicada ao
   usuário de serviço vinculado ao token.
4. **Política de endpoint/campo** (`ai_governance/gate.py`, fora deste documento): verifica se
   `AiEndpoint.enabled_api`/`enabled_mcp`/`enabled_ai` está ligado para a chave do endpoint
   chamado, se há restrição adicional (`AiProfileEndpointGrant`) para o perfil do usuário de
   serviço, e filtra a resposta pelos campos permitidos em `AiFieldPermission` +
   `AiProfileFieldGrant`.
5. **Auditoria**: a chamada é registrada em `AiAccessAuditLog`, visível em `GET /audit-logs`.

Desligar um `AiEndpoint` ou um campo aqui bloqueia o endpoint/tool correspondente
**imediatamente**, sem reiniciar o processo — cada escrita chama `bump_policy_version`, que o
gate consulta antes de aplicar a política em cache.

## Exemplos

### 1. Criar um perfil de acesso e atribuir permissões

```http
POST /api/admin/access-profiles
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "name": "Supervisor Regional Norte",
  "description": "Acesso de leitura à operação e gestão da regional Norte.",
  "active": true,
  "permission_keys": ["operations:read", "management:read", "support:read"]
}
```

Resposta `201`:

```json
{
  "id": 14,
  "name": "Supervisor Regional Norte",
  "description": "Acesso de leitura à operação e gestão da regional Norte.",
  "legacy_role": null,
  "active": true,
  "is_system": false,
  "permission_keys": ["management:read", "operations:read", "support:read"],
  "user_count": 0,
  "created_at": "2026-09-16T12:00:00Z",
  "updated_at": "2026-09-16T12:00:00Z",
  "delete_blocked_reason": null
}
```

### 2. Habilitar um endpoint de IA e liberar um campo sensível só para um perfil

```http
PATCH /api/admin/ai-governance/endpoints/operations.network.onu_signal
Authorization: Bearer <jwt>
Content-Type: application/json

{ "enabled_api": true, "enabled_mcp": true, "enabled_ai": true }
```

```http
PUT /api/admin/ai-governance/profiles/14/field-grants
Authorization: Bearer <jwt>
Content-Type: application/json

{ "entity": "operation_order", "field": "technical_report", "granted": true }
```

Ambas as chamadas exigem `admin:ai_governance:write` e disparam `bump_policy_version` — o
efeito vale na próxima chamada de IA, sem reiniciar o backend.

### 3. Emitir um token de API para um agente de IA

```http
POST /api/admin/ai-governance/tokens
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "name": "Agente de suporte N1 - piloto",
  "scopes": ["orders.read", "orders.detail"],
  "expires_in_days": 90
}
```

Resposta `201` (a única vez que a chave bruta aparece):

```json
{
  "key": {
    "id": 7,
    "source": "token",
    "name": "Agente de suporte N1 - piloto",
    "owner_name": "Serviço de IA",
    "owner_email": "ai-service@internal.souuni.com",
    "key_prefix": "aB3dE7fG9hJk",
    "scopes": ["orders.read", "orders.detail"],
    "expires_at": "2026-12-15T12:00:00Z",
    "active": true,
    "last_used_at": null,
    "created_at": "2026-09-16T12:00:00Z",
    "revoked_at": null
  },
  "raw_key": "aB3dE7fG9hJk...<resto do segredo>"
}
```

O agente passa a autenticar chamadas em `/api/ai/*` com `x-api-key: <raw_key>`, restrito aos
escopos `orders.read`/`orders.detail` e a tudo que a política de endpoint/campo já permitir.

## Observações / pontos de atenção

- `GET /access-profiles/{id}` (leitura de um único perfil) e `GET /users` (lista de usuários
  para escolher em `reassign_profile_id`/overrides) **não existem neste módulo** — a listagem
  completa (`GET /access-profiles`, `GET /people-structure`) é o que a tela usa para montar
  seletores; a criação/edição de usuário propriamente dita fica no módulo de autenticação
  (`users.router`, fora do escopo deste documento).
- O e-mail de serviço (`ai-service@internal.souuni.com`) e o papel `ai_service` são fixos em
  código (`router.py` / `security.py:PROFILE_LABELS`), não configuráveis pela tela.
- Não há paginação em nenhuma listagem deste módulo (`GET /permissions`, `/modules`,
  `/people-structure`, `/access-profiles`, `/endpoints`, `/fields`, `/tokens`) — todas retornam a
  coleção inteira. Só `GET /audit-logs` tem `limit` (paginação simples por corte, sem cursor).
