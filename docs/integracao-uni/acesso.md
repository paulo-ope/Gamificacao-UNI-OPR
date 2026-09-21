# Acesso — autenticação, permissões e provisionamento da identidade técnica

Commit analisado: `6c0e69ea531ee28fa5f4fe2cf54a59c5b59cac08` · Data: 2026-09-17.
**Atualizado em 2026-09-21** com o mecanismo real implementado, testado e mesclado em `master`
(pendente só o deploy físico na VM de produção — ver [deploy.md](deploy.md)). O texto original de
2026-09-17 (seções 1-4) permanece como registro histórico do que já existia; a seção 5 foi
reescrita porque o procedimento nela proposto (token `AiApiToken`/`x-api-key`) **não funciona**
para os routers de módulo (só `/api/ai/*` aceita `x-api-key` — os demais exigem Bearer JWT de
sessão). O mecanismo real acabou sendo diferente, mais simples: login com e-mail/senha de uma
conta de serviço dedicada.

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

> Nota de 2026-09-21: a lista de permissões proposta abaixo (2026-09-17) foi o ponto de partida.
> A lista **realmente implementada e testada** — que inclui também `admin:*:read` (por decisão do
> dono do sistema: escopo "todos os módulos, sem exceção") — está na seção 5.

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

## 5. Provisionamento da credencial — o que foi de fato feito (2026-09-21)

O dono do sistema decidiu, nesta sessão, os dois pontos que bloqueavam a análise de 2026-09-17:
**escopo = todos os módulos, sem exceção** (item 1 abaixo já não é uma escolha em aberto) e
**canal do segredo = entrega direta via SSH** (resolve o item 5 — sem depender de um secrets
manager formal ainda não configurado).

Mecanismo real implementado (diferente do proposto em 2026-09-17): como só `/api/ai/*` aceita
`x-api-key`, e os routers de módulo (`operations`, `management`, `support`, `gamification` etc.)
só aceitam **Bearer JWT de sessão** (`get_current_user`, o mesmo usado por qualquer login humano),
a identidade do cubo é uma **conta de serviço com e-mail/senha**, não um `AiApiToken`. O login
(`POST /api/auth/login`) já É o mecanismo de renovação: o Bearer expira
(`AUTH_TOKEN_EXPIRE_MINUTES`, 720 min/12h por padrão) e a própria conta loga de novo quando
precisar — não existe refresh token separado, nem precisa existir.

1. ✅ **Escopo decidido**: todos os 9 módulos de negócio, só leitura. Permissões concedidas
   (28 no total, zero com sufixo `:write`/`:manage`/`:sync`/`:delete`/`:review`/`calculation:run`
   nem qualquer `admin:*:write`):
   ```
   dashboard:read, audit:read, orders:read, scoring:read,
   operations:read, operations:views:read_global, operations:view_order_details,
   operations:view_openings, operations:view_sla, operations:view_warranty,
   operations:view_calendar, operations:view_backlog, operations:export,
   support:read, scheduling:read, scheduling:views:read_global, localiza:read,
   management:read, management:audit_structure:read,
   admin:users:read, admin:roles:read, admin:permissions:read, admin:modules:read,
   admin:audit:read, admin:ai_governance:read, admin:integrations:read,
   intelligence:read, ai:query
   ```
2. ✅ **`AccessProfile` dedicado criado**: `"Cubo de Dados Corporativo - Leitura"`, com exatamente
   essas 28 permissões, `is_system=False`. Nada de papel `admin` nem usuário humano existente.
3. ✅ **Usuário de serviço criado**: `cubo-uni@internal.souuni.com`, sem `collaborator_id`
   (não representa pessoa), papel legado `ai_service` (irrelevante para a permissão de fato — quem
   manda é o perfil), vinculado só a este perfil.
4. ✅ **Validado com login real** (não simulado): `POST /api/auth/login` com essa conta devolve um
   Bearer JWT com as 28 permissões no payload de resposta. Testado contra endpoint de leitura
   (`GET /api/operations/period` → `200`) e contra endpoint de escrita
   (`PUT /api/operations/ixc-sync-settings` → `403`, `POST /api/calculation-runs/calculate` →
   `403`) — a restrição é aplicada pelo backend de verdade, não só pela ausência de botão na tela.
5. ✅ **Ambiente**: feito e verificado em **desenvolvimento local** primeiro. Replicação para
   **produção** planejada para acontecer via o mesmo script (ORM direto, mesmo padrão usado para
   semear os grupos de SLA por tecnologia faltantes em produção), rodado pelo dono do sistema via
   SSH — ver [deploy.md](deploy.md) para o status exato (pode já estar feito quando você ler isto;
   `deploy.md` é a fonte da verdade sobre o que já aconteceu em produção, este arquivo descreve o
   mecanismo).
6. ⏳ **Entrega do segredo**: por decisão do dono do sistema, o canal é a própria sessão SSH dele
   na VM de produção — o comando de criação roda lá, a senha gerada aparece só na tela do terminal
   dele, nunca passa pelo assistente de IA nem fica registrada neste pacote. **Sem gerenciador de
   segredos formal configurado ainda** (Vault/1Password/etc.) — decisão consciente de usar o canal
   mais simples disponível agora; revisitar se a equipe de integração central pedir algo mais
   robusto (rotação automática, auditoria de acesso ao segredo em si).
7. **Renovação**: automática por design — login expira em 12h, a própria chamada de login seguinte
   gera um novo Bearer. Não há passo manual de "renovar token".
8. **Revogação**: `active=false` no usuário `cubo-uni@internal.souuni.com` (via tela de
   Administração ou diretamente no banco) invalida todo acesso imediatamente — `get_current_user`
   rejeita usuário inativo mesmo com um Bearer ainda não expirado.

## 6. O que este pacote fez e não fez

- ✅ Criou o perfil de acesso e o usuário de serviço (local, confirmado; produção conforme
  `deploy.md`).
- ✅ Validou leitura permitida / escrita bloqueada com chamadas reais (não simuladas).
- ❌ Não alterou nenhuma rota de negócio nem criou endpoint de dado novo — só a rota de
  documentação (`/admin/docs/integracao-uni`) e o schema OpenAPI filtrado que ela serve.
- ❌ Não imprimiu nem gravou a senha real em nenhum arquivo deste pacote, commit, log ou resposta
  de chat — só o e-mail da conta (não é segredo) aparece aqui.
- ⏳ Ainda não configurou um secrets manager formal (decisão consciente, ver item 6 acima).
