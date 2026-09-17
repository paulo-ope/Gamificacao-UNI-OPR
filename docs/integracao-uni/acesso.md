# Acesso — autenticação, permissões e provisionamento da identidade técnica

Commit analisado: `6c0e69ea531ee28fa5f4fe2cf54a59c5b59cac08` · Data: 2026-09-17

## 1. Como a autenticação funciona hoje (fato, não proposta)

O sistema **não tem middleware central de autenticação**. Cada rota (ou `APIRouter` inteiro, via
`dependencies=[Depends(...)]`) declara sua própria checagem — não existe uma rede de segurança
automática a nível de aplicação
([backend/app/main.py](../../backend/app/main.py), único `add_middleware` chamado é CORS).

Dois mecanismos de autenticação coexistem, para dois tipos de consumidor diferentes:

### 1.1 JWT de usuário (Bearer) — usado pela tela e pelo MCP

- Token HS256 caseiro (não é lib de terceiros), payload com `sub` (user id), `email`, `role`,
  `iat`, `exp` — [backend/app/core/security.py:386-404](../../backend/app/core/security.py).
- `Authorization: Bearer <token>`, validado por `get_current_user`
  ([security.py:424-434](../../backend/app/core/security.py)).
- Expira em `AUTH_TOKEN_EXPIRE_MINUTES` (default 720 min / 12h,
  [backend/app/core/config.py](../../backend/app/core/config.py)).
- Permissão efetiva de cada chamada = permissões do perfil (`AccessProfile`) ou do papel legado
  (`role`) **mais** concessões individuais **menos** negações individuais — resolvida sempre por
  `permissions_for_user` ([security.py:311-328](../../backend/app/core/security.py)), a fonte
  única usada por toda checagem do sistema, inclusive MCP.

### 1.2 `x-api-key` — usado pelo módulo `/api/ai` (Agente de IA)

- Header `x-api-key`, resolvido contra `ApiKeyCredential`/`AiApiToken` (hash SHA-256/PBKDF2 da
  chave, nunca a chave em claro no banco).
- Camada adicional de governança campo-a-campo (`AiFieldPermission` /
  `AiProfileFieldGrant`) — ver seção 3.

### 1.3 Já existe um precedente direto de "identidade de máquina read-only"

O papel legado `ai_service` ([security.py:198-203](../../backend/app/core/security.py)) tem uma
única permissão, `ai:query`, e é descrito no próprio código como "usado pela chave de API que
expõe dados analíticos de O.S. para consumo por IA (conector MCP/Actions)". É o modelo mais
próximo do que este pedido descreve — mas hoje é **escopado a `ai:query`**, que por sua vez é
escopado ao módulo `/api/ai` (Operações/Gestão), não à leitura corporativa completa que este
pacote descreve.

## 2. Por que a identidade do cubo não pode ser simplesmente "outro usuário `ai_service`"

`ai:query` hoje dá acesso só ao que o módulo `/api/ai` expõe (Operação, Rede, Gestão Integrada —
ver [cobertura.md](cobertura.md)). Não cobre Gamificação, Suporte, Agendamento, Intelligence nem
Administração. Para a cobertura corporativa completa pedida, a identidade técnica do cubo precisa
de uma combinação de permissões de leitura **explicitamente listada**, nunca do papel `admin`:

```
orders:read, scoring:read, audit:read, dashboard:read,
operations:read, operations:view_sla, operations:view_backlog,
operations:view_calendar, operations:view_order_details, operations:view_openings,
support:read, scheduling:read, management:read,
intelligence:read, ai:query
```

Explicitamente **excluídas**, mesmo que existam no catálogo de permissões do sistema:
`*:write`, `*:manage*`, `*:sync*`, `*:publish`, `management:review`, `management:admin`,
`admin:*` (todas), `intelligence:manage`, `intelligence:publish`,
`users:manage`, e qualquer permissão marcada em `SENSITIVE_PERMISSIONS`
([backend/app/modules/admin/permissions_service.py:43-53](../../backend/app/modules/admin/permissions_service.py)).

**A restrição precisa ser aplicada no backend, por operação, não só pela ausência de um botão na
tela** — é exatamente assim que o sistema já funciona hoje (`require_permission` por rota), então
a tarefa de provisionamento é **compor um novo `AccessProfile`** com só as permissões acima, não
criar um mecanismo novo de restrição.

## 3. Governança campo-a-campo (`AiFieldPermission`) — reusar, não reinventar

O módulo `ai_governance` já resolve exatamente o problema de "este consumidor automatizado pode
ver este campo, mas não aquele" para as entidades que cobre hoje (`operations_orders`,
`operations_login_current_status`, `operations_onu_signal_current`,
`operations_onu_signal_snapshots` —
[backend/app/modules/ai_governance/field_registry.py:25-28](../../backend/app/modules/ai_governance/field_registry.py)).

Regras fixas em código, não configuráveis pela Administração:
- Um campo marcado `sensitive=True` (hoje só `raw_payload`) **nunca** pode ser liberado além do
  detalhe individual, mesmo que um administrador tente ligar isso na tela
  ([ai_governance/policy.py:45-50](../../backend/app/modules/ai_governance/policy.py)).
- Um campo não catalogado nunca é autorizado por padrão
  ([policy.py:76-83](../../backend/app/modules/ai_governance/policy.py)).

**Recomendação para o cubo**: antes de consumir qualquer campo de `operations_orders` via REST,
consultar `GET /api/ai/fields` para saber o que está de fato liberado — o catálogo é dinâmico e
reflete decisões administrativas; não hardcodear a lista de campos no lado do cubo.

Para os módulos que `ai_governance` **não cobre** hoje (Gamificação, Suporte, Agendamento,
Intelligence), a única camada de controle de campo é o schema Pydantic de cada endpoint — ou seja,
"o que o endpoint retorna é o que está liberado", sem granularidade adicional. Isso é uma lacuna
real (ver `gap.mcp_connector_scope` em [catalogo.json](catalogo.json)) que fica registrada como
pendência, não resolvida por este pacote.

## 4. Classificação de dados pessoais e sensíveis

| Dado | Onde | Pode ir para o cubo? |
|---|---|---|
| `User.password_hash` | `users` | **Nunca.** Segredo — hash pbkdf2_sha256, nenhuma rota do sistema o serializa hoje. |
| `AiApiToken.key_hash` / `ApiKeyCredential.key_hash` / tokens de qualquer tipo | vários módulos | **Nunca.** |
| `Collaborator.cpf` | `collaborators` | Só **mascarado** (`cpf_masked`), como já é servido hoje por `GET /admin/people-structure`. Nunca em claro. |
| `Collaborator.phone` / `email` | `collaborators` | **Não incluído** — nenhuma rota de leitura identificada nesta análise expõe esses campos; não adicionar exposição nova sem aprovação explícita da área de RH/DPO. |
| `Collaborator.photo` (binário) | `collaborators` | **Fora de escopo** de um cubo analítico — nenhuma rota atual expõe os bytes, só `has_photo: bool`. |
| `raw_payload` (O.S., IXC) | `operations_orders` | **Nunca em bloco.** Marcado `sensitive=True` no código — só pode aparecer no detalhe individual de uma O.S., nunca em listagem/filtro/agregação. |
| Comentários de justificativa de gestão (`justification_text`, `action_plan`) | `management_cases`, `management_case_comments` | **Desabilitado por decisão administrativa já tomada** — `ai.management_justifications` nasce desligado no bootstrap de governança ([ai_governance/bootstrap.py:130-135](../../backend/app/modules/ai_governance/bootstrap.py)), porque é texto livre de supervisor sobre uma pessoa específica (motivo de falta, saúde, conflito). Manter desligado até decisão explícita da área. |
| Coordenadas de cliente (UNI Localiza) | `location_requests` | **Fora do escopo deste pacote** — módulo é de compartilhamento de GPS sob consentimento do cliente final via link, não um dataset analítico corporativo. Não incluído na matriz de cobertura como liberado. |

Nenhum destes itens foi aprovado por uma área de negócio/DPO nesta análise — a classificação acima
é técnica (o que o código já trata como segredo/PII vs. o que já é servido hoje), não uma aprovação
de compliance.

## 5. Provisionamento da credencial — procedimento (NÃO EXECUTADO nesta análise)

Esta análise **não criou nenhuma credencial real**. O procedimento abaixo é o que precisa
acontecer, e cada passo exige aprovação explícita antes de execução:

1. **Decisão de escopo** — a área de negócio confirma a lista de permissões da seção 2 (adicionar
   ou remover módulos conforme necessidade real do Portal Executivo).
2. **Criar `AccessProfile` dedicado** (ex.: `"cubo_corporativo_readonly"`) com exatamente essas
   permissões, via tela de Administração ou migration — nunca reaproveitar o papel `admin` nem
   um usuário humano existente.
3. **Criar usuário de serviço** vinculado a esse perfil, sem `collaborator_id` (não representa uma
   pessoa), com `managed_regional`/`managed_regionals` **vazios** (para não herdar o recorte
   regional de um gestor específico — o cubo precisa de visão corporativa completa).
4. **Gerar token de API** (não senha) — reusar o padrão já existente de `AiApiToken`
   (`key_prefix` + `key_hash`, chave crua exibida **uma única vez** na criação, nunca recuperável
   depois — mesmo padrão de
   [backend/app/modules/ai_governance/models.py:103-118](../../backend/app/modules/ai_governance/models.py)).
   Preferir esse mecanismo a JWT de usuário porque já tem expiração/revogação/escopo por design.
5. **Armazenar no gerenciador de segredos aprovado** — **pendência real**: esta análise confirmou
   que **não há secrets manager integrado** no projeto hoje (só `.env`/Docker Compose, ver
   `gap.no_secrets_manager` em [catalogo.json](catalogo.json)). Antes de gerar a chave real, a
   equipe de infraestrutura precisa decidir onde ela será armazenada — a regra do projeto
   ([docs/manual_programacao_senior.md](../manual_programacao_senior.md)) exige "secrets apenas em
   `.env` ou secret manager", mas nenhum secret manager está configurado. **Não gerar a chave real
   até esta decisão existir.**
6. **Consumo pelo serviço central de integração** — a chave é usada pelo backend do time do
   cubo/Portal Executivo, nunca pelo navegador do usuário final nem diretamente por um modelo de
   IA sem essa camada intermediária.
7. **Renovação e revogação** — seguir o padrão de `AiApiToken.expires_at`/`revoked_at`; definir
   janela de renovação com a equipe operadora antes de emitir a chave real (não definida nesta
   análise — pendência).

### Se o provisionamento não puder ser feito com segurança agora

Registrar como pendência explícita (não simular, não contornar): **hoje o provisionamento está
bloqueado pela ausência de um secrets manager aprovado** (passo 5). O procedimento acima é
suficiente para executar assim que essa decisão de infraestrutura existir; até lá, qualquer chave
gerada manualmente deve ficar fora do Git e comunicada por canal seguro (não e-mail, não chat),
como já orienta [AGENTS.md](../../AGENTS.md).

## 6. O que este pacote NÃO fez

- Não criou usuário, perfil, token ou qualquer credencial real.
- Não alterou nenhuma rota nem criou endpoint novo.
- Não imprimiu nem gerou nenhum segredo em nenhum arquivo deste pacote.
