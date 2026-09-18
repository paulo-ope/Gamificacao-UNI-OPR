# API — UNI Intelligence (`/api/intelligence`)

## Visão geral

O UNI Intelligence é o motor de inteligência operacional da plataforma: roda **monitores**
periódicos que inspecionam os dados de operação/suporte, gera **alertas** (com deduplicação,
severidade, evidências e ciclo de vida confirmar/resolver) e monta o **payload único do cockpit**
consumido pelas TVs/gauges da operação (`/cockpit/{profile_key}`).

Além da leitura, o módulo permite **publicar conteúdo editorial** no cockpit (avisos, destaques)
tanto via REST (`POST /cockpit-content`) quanto pela mesma função usada pela tool MCP
`opr_publish_cockpit_content` — nunca há duas implementações da regra de validação.

A parte de administração (F5) cobre CRUD de **profiles de cockpit** (o que cada TV mostra),
**publicações** (aprovar/editar/descartar conteúdo) e **monitores/regras de alerta**
(habilitar, ajustar intervalo, parametrizar regras, simular impacto antes de ativar).

Todas as listagens seguem o `FilterContractV1`: filtros de igualdade em plural/`snake_case` e um
envelope `meta` (`applied_filters`, `ignored_filters`, `warnings`, `source_last_sync`) em toda
resposta — não herda o vocabulário do REST legado de `operations`.

## Autenticação e permissões

Sessão autenticada (cookie/token de usuário) é obrigatória em **todas** as rotas do módulo — não
há endpoint público.

- O router principal exige `intelligence:read` para qualquer rota (`dependencies` no nível do
  `APIRouter`, em `router.py`).
- `POST /alerts/{alert_id}/dismiss` exige adicionalmente `intelligence:manage`.
- `POST /cockpit-content` (publicação REST de conteúdo do cockpit) exige `intelligence:publish`.
- Todo o subrouter `/admin/*` (profiles, filter-catalog, content, monitores, alert-rules) exige
  `intelligence:manage` além do `intelligence:read` herdado do router pai — é a superfície de
  gestão, não a leitura da TV.

## Endpoints

### Monitores e execuções

- **`GET /monitors`** — lista o estado efetivo de cada monitor registrado: configuração atual
  (`app_settings`, com fallback pro default do registry), última execução, última execução com
  sucesso e falhas consecutivas. Mesmo material usado pelo meta-monitor de saúde, exposto para
  inspeção manual. Sem parâmetros. Resposta: `MonitorListOut` (`items: MonitorOut[]` + `meta`).
  Permissão: `intelligence:read`.

- **`GET /monitor-runs`** — histórico paginado de execuções de monitor.
  Parâmetros: `monitor_keys[]`, `statuses[]`, `page` (≥1, default 1), `page_size` (1–200,
  default 50). Chaves de monitor desconhecidas viram `ignored_filters` com motivo
  `NOT_SUPPORTED_BY_ENDPOINT`, não erro. Resposta: `MonitorRunPageOut`
  (`items`, `total`, `page`, `page_size`, `meta`). Permissão: `intelligence:read`.

### Alertas

- **`GET /alerts`** — lista paginada de alertas ativos/históricos.
  Parâmetros: `statuses[]`, `severities[]`, `monitor_keys[]`, `regionals[]`, `kinds[]`, `page`,
  `page_size` (1–200, default 50). Ordenado por `last_seen_at` desc. Resposta: `AlertPageOut`.
  Permissão: `intelligence:read`.

- **`GET /alerts/{alert_id}`** — detalhe de um alerta, incluindo o histórico de eventos
  (`events: AlertEventOut[]`). 404 se o alerta não existir. Resposta: `AlertDetailOut`.
  Permissão: `intelligence:read`.

- **`POST /alerts/{alert_id}/dismiss`** — descarta manualmente um alerta (registra evento e
  atualiza status). Body: `AlertDismissRequest` (`reason`). 404 se o alerta não existir.
  Resposta: `AlertDetailOut` (com eventos atualizados). Permissão: `intelligence:manage`.

### Cockpit (F2)

- **`GET /cockpit/{profile_key}`** — payload único da TV: tudo que o frontend precisa para
  renderizar o cockpit em um único request (produção, backlog, SLA, alertas/incidentes recentes,
  conteúdo publicado, saúde dos monitores, gráficos, frescor do dado). Monta no backend
  reaproveitando funções de `operations`/`ai` via `cockpit.py` — o frontend nunca chama dezenas
  de endpoints separados. 404 se o profile não existir ou estiver inativo (`profile.active`).
  Resposta: `CockpitPayloadOut`. Permissão: `intelligence:read`.

- **`POST /cockpit-content`** — publica conteúdo editorial no cockpit (aviso, destaque) via REST.
  Usa a mesma função (`cockpit.publish_cockpit_content`) chamada pela tool MCP
  `opr_publish_cockpit_content`, para nunca duplicar validação. A origem é sempre determinada pelo
  backend a partir do usuário logado — nunca aceita `publisher` arbitrário no payload; grava
  sempre `source_type="USER"` com `author_user_id` do chamador. Body: `PublishCockpitContentRequest`
  (`content_type`, `profile_key`, `scope`, `severity`, `title`, `body`, `evidence`, `confidence`,
  `valid_until`). 422 em `CockpitContentValidationError`. Resposta: `CockpitContentOut` (201).
  Permissão: `intelligence:publish`.

### Administração — profiles (`/admin/profiles`)

- **`GET /admin/profiles`** — lista todos os profiles de cockpit cadastrados.
  Resposta: `AdminProfileOut[]`. Permissão: `intelligence:manage`.
- **`GET /admin/profiles/{profile_key}`** — detalhe de um profile. 404 se inexistente.
  Permissão: `intelligence:manage`.
- **`POST /admin/profiles`** — cria um profile. Body: `AdminProfileCreateRequest` (`key`, `name`,
  `purpose`, `scope`, `widgets[]`, `display_config`, `refresh_seconds`, `active`). 422 em
  `ProfileValidationError`. Resposta: `AdminProfileOut` (201). Permissão: `intelligence:manage`.
- **`PUT /admin/profiles/{profile_key}`** — atualiza um profile existente (campos parciais).
  404 se inexistente, 422 em `ProfileValidationError`. Permissão: `intelligence:manage`.

### Administração — catálogo de filtros

- **`GET /admin/filter-catalog`** — valores possíveis para montar filtros de profile/conteúdo:
  `regionals`, `sectors`, `team_models`, `os_subjects`, `content_types`, `content_severities`,
  `profile_purposes`, `widgets` (catálogo de widgets disponíveis). Resposta: `FilterCatalogOut`.
  Permissão: `intelligence:manage`.

### Administração — publicações (`/admin/content`)

- **`GET /admin/content`** — lista publicações de cockpit para gestão (inclui `status`, diferente
  da rota pública de conteúdo já embutida no cockpit). Parâmetros: `profile_key`, `status`
  (alias de `status_filter`), `content_type`. Resposta: `AdminContentOut[]`.
  Permissão: `intelligence:manage`.
- **`PUT /admin/content/{content_id}`** — edita uma publicação (`title`, `body`, `severity`,
  `valid_until`). 404 se não encontrada, 422 em `CockpitContentValidationError`.
  Permissão: `intelligence:manage`.
- **`POST /admin/content/{content_id}/dismiss`** — descarta uma publicação. 404 se não
  encontrada. Permissão: `intelligence:manage`.

### Administração — monitores

- **`PUT /admin/monitors/{monitor_key}`** — ajusta configuração de um monitor: `enabled`,
  `interval_minutes`, `resolve_after_misses` (`AdminMonitorUpdateRequest`). 404 se o monitor não
  existir no registry. Resposta: `MonitorOut` já com o estado recalculado.
  Permissão: `intelligence:manage`.

### Administração — regras de alerta (`/admin/alert-rules`)

- **`GET /admin/alert-rules`** — lista as regras de alerta parametrizáveis cadastradas.
  Resposta: `AdminAlertRuleOut[]`. Permissão: `intelligence:manage`.
- **`GET /admin/alert-rules/catalog`** — catálogo de tipos de regra disponíveis e seus parâmetros
  aceitos. Resposta: `AlertRuleCatalogOut`. Permissão: `intelligence:manage`.
- **`POST /admin/alert-rules/{rule_key}/simulate`** — simula o impacto de uma alteração de regra
  (sem persistir) antes de aplicá-la: monta uma regra candidata com os campos enviados
  (sobrepostos aos da regra atual) e roda a simulação. 404 se a regra não existir, 422 em
  `AlertRuleValidationError`. Resposta: `AlertRuleSimulationOut`. Permissão: `intelligence:manage`.
- **`POST /admin/alert-rules`** — cria uma regra. Body: `AdminAlertRuleCreateRequest` (`key`,
  `name`, `rule_type`, `scope`, `params`, `severity`, `active`, `cooldown_minutes`,
  `confirm_cycles`, `resolve_cycles`). 422 em `AlertRuleValidationError`. Resposta:
  `AdminAlertRuleOut` (201). Permissão: `intelligence:manage`.
- **`PUT /admin/alert-rules/{rule_key}`** — atualiza uma regra existente (campos parciais). 404
  se inexistente, 422 em `AlertRuleValidationError`. Permissão: `intelligence:manage`.
- **`DELETE /admin/alert-rules/{rule_key}`** — remove uma regra. 404 se inexistente. Resposta:
  204 sem corpo. Permissão: `intelligence:manage`.

## Exemplos

**1. TV do cockpit buscando o payload de um profile:**

```
GET /api/intelligence/cockpit/visao-geral-operacao
Cookie: <sessão autenticada com intelligence:read>
```

Resposta (200, resumida):

```json
{
  "profile": { "key": "visao-geral-operacao", "name": "Visão Geral" },
  "generated_at": "2026-09-16T13:05:00Z",
  "overall_status": { "...": "..." },
  "production": { "...": "..." },
  "backlog": { "...": "..." },
  "sla": { "...": "..." },
  "alerts": [],
  "incidents": [],
  "recent_alerts": [],
  "content": [],
  "monitor_health": [],
  "charts": { "...": "..." },
  "data_freshness": { "...": "..." },
  "meta": { "applied_filters": {}, "source_last_sync": null }
}
```

**2. Publicando um aviso editorial no cockpit (usuário com `intelligence:publish`):**

```
POST /api/intelligence/cockpit-content
Content-Type: application/json

{
  "content_type": "AVISO",
  "profile_key": "visao-geral-operacao",
  "scope": {"regional": "Porto Velho"},
  "severity": "MEDIA",
  "title": "Manutenção programada às 22h",
  "body": "Janela de manutenção na regional Porto Velho, sem impacto esperado no SLA.",
  "evidence": null,
  "confidence": null,
  "valid_until": "2026-09-17T00:00:00Z"
}
```

Resposta: `201 Created` com o `CockpitContentOut` criado, `source_type="USER"` e
`author_user_id` preenchido automaticamente pelo backend a partir do usuário autenticado.
