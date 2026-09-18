# API — UNI Localiza (`/api/localiza` + `/api/public/location`)

## Visão geral

O UNI Localiza gera **links de compartilhamento de GPS** vinculados a uma O.S./atendimento: o
atendente cria uma solicitação (opcionalmente já ligada a uma O.S., protocolo OPA ou cliente do
IXC), o sistema gera um **token público** de alta entropia e o link (`{frontend_url}/l/{token}`)
é enviado ao cliente — normalmente por WhatsApp. O cliente abre o link em uma página pública
(sem login), autoriza o GPS do navegador e confirma a localização; o backend compara a
coordenada confirmada com a coordenada cadastrada do cliente no IXC e classifica a divergência
(`compatible` / `minor_divergence` / `relevant_divergence` / `high_divergence`), útil para
detectar endereço cadastral desatualizado antes do técnico ir a campo.

O módulo **não aparece no registro central de módulos** da aplicação (diferente de
`intelligence`, `operations` etc.), mas está com rotas ativas e mapeado direto em `main.py`:
`app.include_router(localiza_router, prefix=settings.api_prefix)` e
`app.include_router(localiza_public_router, prefix=settings.api_prefix)`.

## Autenticação e permissões

Este módulo tem **duas superfícies com modelos de acesso completamente diferentes** — distinção
importante porque uma delas fica exposta na internet sem login:

- **Rotas internas/autenticadas** (`router.py`, prefixo `/api/localiza`): exigem sessão de
  usuário autenticado, controlada por permissão granular via `require_permission(...)`:
  - `localiza:read` — apenas leitura (listar e ver detalhe de solicitações).
  - `localiza:manage` — criar, invalidar, reanexar O.S., regenerar link, buscar cliente no IXC e
    configurar o TTL do link.
- **Rotas públicas** (`public_router.py`, prefixo `/api/public/location`): **sem nenhuma
  autenticação de usuário** — é a página que o cliente final abre pelo link do WhatsApp. A
  proteção não é login, é o **token** (256 bits de entropia, nunca devolvido em texto puro fora
  da criação/regeneração — só o hash SHA-256 é persistido) somado a **rate limiting em memória
  por IP**: `RATE_WINDOW_MINUTES = 15`, `RATE_MAX_ATTEMPTS = 20`, aplicado via dependency
  `Depends(_guard_rate_limit)` tanto na consulta de status quanto na confirmação — porque a
  própria consulta de status já permite "adivinhar" se um token existe. Excedido o limite, a API
  responde `429 Muitas tentativas`. Mesmo padrão usado em `app/api/routes/invites.py`.

## Endpoints

### Rotas internas — `/api/localiza` (autenticadas)

- **`GET /localiza`** — lista solicitações de localização.
  Parâmetros: `search`, `date_from`, `date_to`, `status` (`pending|confirmed|invalidated|expired`),
  `mine_only` (bool, só as criadas pelo usuário logado), `limit` (1–1000, default 200). 400 se
  `date_to < date_from`. Resposta: `LocationRequestOut[]`. Permissão: `localiza:read`.

- **`GET /localiza/settings`** — retorna a validade (TTL) atual configurada para os links, em
  horas. Resposta: `LocalizaSettingsOut` (`link_ttl_hours`). Permissão: `localiza:manage`.

- **`PUT /localiza/settings`** — atualiza o TTL dos links (1–720 horas), gravado em
  `AppSetting` (não exige redeploy) e registrado em audit log com valor anterior/novo. Body:
  `LocalizaSettingsUpdate` (`link_ttl_hours`). Resposta: `LocalizaSettingsOut`.
  Permissão: `localiza:manage`.

- **`POST /localiza`** — cria uma nova solicitação de localização e gera o token público (a
  string crua do token só existe nesta resposta e na de `/regenerate` — depois só o hash fica no
  banco). Nenhum campo é individualmente obrigatório, mas o service exige ao menos um
  identificador (`order_code`, `opa_protocol` ou dados de cliente), senão a solicitação fica
  impossível de localizar depois. Body: `LocationRequestCreate` (`order_code`, `opa_protocol`,
  `customer_id`, `customer_name`, `registered_latitude`/`registered_longitude`,
  `ixc_cliente_id`, `ixc_login_id`, `ixc_login`). Resposta: `LocationRequestCreateOut` (201) —
  `LocationRequestOut` + `token` (cru) + `public_link` (`{frontend_url}/l/{token}`).
  Permissão: `localiza:manage`.

- **`GET /localiza/ixc/search`** — busca ao vivo no IXC por `login` (número ou texto) **ou**
  `cpf`, nunca os dois juntos (422 se ambos ou nenhum for informado). Usada pelo formulário de
  criação para autopreencher nome/identificador/coordenada cadastrada a partir de um cadastro já
  existente, evitando digitação manual. Resposta: `IxcCustomerSearchOut` (`matches:
  IxcCustomerMatchOut[]`, com `cpf_masked`). Permissão: `localiza:manage`.

- **`GET /localiza/{item_id}`** — detalhe de uma solicitação, com status efetivo recalculado na
  hora (`pending` vira `expired` automaticamente se `expires_at` já passou). Resposta:
  `LocationRequestOut`. Permissão: `localiza:read`.

- **`POST /localiza/{item_id}/invalidate`** — invalida manualmente uma solicitação (ex.: link
  enviado por engano). Resposta: `LocationRequestOut`. Permissão: `localiza:manage`.

- **`POST /localiza/{item_id}/attach-order`** — associa/atualiza o código de O.S. de uma
  solicitação já existente (comum quando o link é enviado antes de a O.S. existir no IXC). Body:
  `LocationRequestAttachOrder` (`order_code`). Resposta: `LocationRequestOut`.
  Permissão: `localiza:manage`.

- **`POST /localiza/{item_id}/regenerate`** — gera um novo token/link para uma solicitação
  (ex.: o link anterior expirou ou foi comprometido), preservando os demais dados. Resposta:
  `LocationRequestCreateOut` (201) — mesmo formato de `POST /localiza`, com novo `token` cru e
  `public_link`. Permissão: `localiza:manage`.

### Rotas públicas — `/api/public/location` (sem autenticação, com rate limit)

- **`GET /public/location/{token}`** — consulta o status de um link público, para a página
  exibir contexto ao cliente antes de pedir o GPS (nome do cliente, O.S./protocolo, status,
  validade). Não vaza dados sensíveis nem confirma univocamente a existência do token além do
  necessário. Resposta: `PublicLocationStatusOut` (`valid`, `reason`, `order_code`,
  `opa_protocol`, `customer_name`, `status`, `expires_at`). Sujeito ao rate limit por IP.

- **`POST /public/location/{token}/confirm`** — o cliente confirma a localização capturada pelo
  navegador. Body: `PublicLocationConfirmRequest` (`latitude`/`longitude` finais — podem ter sido
  ajustadas manualmente no mapa —, `accuracy_meters` (0–50000), `gps_latitude`/`gps_longitude`
  brutos do GPS, `adjusted_manually`). O backend calcula a distância Haversine entre a coordenada
  confirmada e a coordenada cadastrada do cliente e grava a classificação de divergência
  (`compatible` ≤50m, `minor_divergence` ≤150m, `relevant_divergence` ≤500m,
  `high_divergence` acima disso). Resposta: `PublicLocationConfirmOut`
  (`status="confirmed"`, `confirmed_at`). Sujeito ao rate limit por IP.

## Exemplos

**1. Atendente cria uma solicitação de localização (rota interna, `localiza:manage`):**

```
POST /api/localiza
Content-Type: application/json
Cookie: <sessão autenticada com localiza:manage>

{
  "order_code": "OS-458213",
  "customer_name": "Maria da Silva",
  "ixc_cliente_id": 88210,
  "ixc_login_id": 154032,
  "ixc_login": "maria.silva"
}
```

Resposta (`201 Created`):

```json
{
  "id": 512,
  "public_id": "A1B2C3D4",
  "order_code": "OS-458213",
  "customer_name": "Maria da Silva",
  "status": "pending",
  "expires_at": "2026-09-17T13:00:00Z",
  "token": "9f3c...(cru, só aparece aqui)",
  "public_link": "https://app.souuni.com/l/9f3c..."
}
```

O `public_link` é então enviado ao cliente pelo WhatsApp.

**2. Cliente abre o link e confirma a localização (rota pública, sem login):**

```
GET /api/public/location/9f3c...
```

```json
{ "valid": true, "order_code": "OS-458213", "customer_name": "Maria da Silva", "status": "pending", "expires_at": "2026-09-17T13:00:00Z" }
```

```
POST /api/public/location/9f3c.../confirm
Content-Type: application/json

{
  "latitude": -8.76077,
  "longitude": -63.90184,
  "accuracy_meters": 12.5,
  "gps_latitude": -8.76077,
  "gps_longitude": -63.90184,
  "adjusted_manually": false
}
```

Resposta: `{"status": "confirmed", "confirmed_at": "2026-09-16T13:07:22Z"}`. Se a taxa de
tentativas daquele IP já tiver estourado (20 em 15 minutos, somando consultas de status e
confirmações), a API responde `429 Muitas tentativas. Aguarde alguns minutos e tente novamente.`
