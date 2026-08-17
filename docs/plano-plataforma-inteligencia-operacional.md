# Plataforma de Inteligência Operacional — Estudo de Arquitetura e Produto

Data: 2026-08-16
Status: **ESTUDO — nada implementado.** Documento para validação antes de qualquer código, migration ou alteração de frontend/backend.
Base: leitura do código real (backend ~40.800 linhas em `app/`, frontend App Router, 65 migrations, docs/), não especificação genérica.

---

## A. Compreensão do produto

O UNI WorkSPACE hoje é um conjunto de módulos analíticos que **respondem perguntas quando alguém abre a tela**. A plataforma proposta inverte isso: o sistema passa a **avaliar a operação continuamente**, persistir o que encontrou (alertas, incidentes, insights, estado geral) e servir esse estado já processado para várias superfícies de exibição — a primeira sendo uma TV/cockpit 16:9, todas lendo o mesmo backend, com escopo e conteúdo definidos por configuração (dashboard profiles), não por páginas hardcoded.

A IA entra como **analista assíncrono do motor** (investiga detecções relevantes e produz insights estruturados persistidos), nunca como chamada síncrona da tela e nunca executando ação — mas com a arquitetura preparada para o ciclo futuro "IA recomenda → gestor aprova → sistema executa".

Três correções factuais à visão, encontradas no código:

1. **Slack não existe no projeto.** Zero ocorrências em código, config, `.env.example`, docker-compose e docs. Notificação hoje é exclusivamente in-app (sino, tabela `notifications`, polling de 60s). O item "depois notifica Slack" do fluxo desejado é construção nova, não integração existente.
2. **A fonte tipográfica oficial do projeto é Inter, não Poppins.** `app/layout.tsx` carrega Inter e `frontend/PADRAO_VISUAL_OFICIAL_UNI_OPR.md` §3.3 a define como padrão. Poppins não aparece em nenhum arquivo. Precisa de decisão (P.5).
3. **Parte do motor já existe em forma embrionária** — só que sem persistência: Torre de Controle Preventiva (baseline de 8 semanas, status critical/attention/normal/insufficient), `login_incident_analysis` (funil completo de incidente de rede), clusters DBSCAN de logins offline, volume-alerts, sla-risk e os 6 "insights da gestão" heurísticos. Tudo recalculado por request, nada registrado, nenhum lifecycle. A plataforma é, em grande parte, **dar memória, ciclo de vida e distribuição ao que já detecta**.

---

## B. Arquitetura proposta

### B.1 Crítica ao desenho conceitual apresentado

O desenho geral está certo, com três ajustes:

1. **"Rule Engine" e "AI Engine" não são camadas paralelas.** IA analisando tudo a cada ciclo é caro, lento e desnecessário. O fluxo correto é **serial com gate**: monitores heurísticos (baratos, determinísticos, a cada ciclo) produzem detecções; um *gate* decide quais detecções merecem análise de IA (severidade, novidade, orçamento, cooldown); a IA roda de forma assíncrona só nesses casos. A IA é um **estágio opcional do pipeline**, não um motor irmão.

2. **"Operational Data Layer" não deve ser construída — ela já existe.** `operations_orders`, `operations_login_current_status` + snapshots, `operations_onu_signal_current`, `operations_backlog_snapshots`, `support_opa_attendances`, e as funções de consulta (`login_incident_analysis`, `find_offline_login_clusters`, `control_tower`, `openings_analytics`, `backlog_aging`, `coordinate_quality_audit`...). Os monitores novos **chamam essas funções Python diretamente**, as mesmas que hoje servem REST/IA/MCP. Criar uma segunda camada de leitura seria a duplicação de arquitetura que queremos evitar.

3. **"Cockpit Backend" é fino.** Se monitores persistem alertas/insights/snapshots, o backend do cockpit vira essencialmente: resolver o profile → ler estado persistido filtrado pelo escopo → montar um payload único. Nada de recomputar analítica na leitura da TV.

### B.2 Desenho ajustado

```
Fontes (IXC ~20min · login 5min · ONU 15min · OPA ~20min · backlog diário)
        ↓  (loops asyncio existentes — inalterados)
Camada de dados operacionais (tabelas + funções de consulta existentes)
        ↓
┌──────────────────────── módulo novo: intelligence ────────────────────────┐
│ Monitor Scheduler (loop asyncio novo, mesmo padrão dos 5 existentes)      │
│   → executa monitores registrados em código (registry declarativo)        │
│   → cada execução grava intelligence_monitor_runs                         │
│ Monitores heurísticos (determinísticos)                                   │
│   → detecções → upsert com dedupe em intelligence_alerts (lifecycle)      │
│   → snapshot agregado por escopo em intelligence_snapshots                │
│ AI Gate → fila interna → AI Analyst (chamada LLM assíncrona)              │
│   → intelligence_insights (estruturado, versionado, com confidence)       │
│ Dispatcher de notificação (in-app hoje; Slack no futuro — best-effort,    │
│   nunca fonte da verdade: persiste primeiro, notifica depois)             │
└────────────────────────────────────────────────────────────────────────────┘
        ↓
Cockpit API: GET /api/intelligence/cockpit/{profile_key}  (payload único)
        ↓
intelligence_dashboard_profiles (escopo + widgets + refresh + modo)
        ↓
Frontend: rota única /cockpit/[profileKey]  (TV matriz, TVs regionais,
          sala de incidente, executivo — mesmo código, profiles diferentes)
```

### B.3 Decisões estruturais e por quê

- **Módulo novo `intelligence`** no padrão existente (`backend/app/modules/intelligence/` + entrada no `registry.py` + permissões `intelligence:*`), e **não** dentro de `operations`. Mesma lógica que separou `support` de `operations` (regra registrada em `auditoria-evolucao-opa-suite-2026-08-16.md`): o motor consome dados de operações, suporte e futuramente rede/financeiro — é transversal, não pertence a um domínio de dados.
- **Scheduler = 6º loop asyncio**, não APScheduler/Celery. O projeto já tem 5 loops com um padrão maduro: config em `app_settings` relida a cada ciclo, sono fatiado, próximo horário absoluto persistido, erro nunca derruba o loop. Introduzir broker/fila agora seria infra nova sem necessidade — a única exigência real de assíncrono pesado é a chamada LLM, que pode ser uma task asyncio separada alimentada por uma fila em memória + reprocesso na inicialização (mesma filosofia do run retomável do OPA).
- **Monitores registrados em código, configurados em banco.** Espelha o `modules/registry.py`: um `MONITORS` declarativo (key, nome, intervalo default, escopo, função) e liga/desliga + intervalos em `app_settings` (padrão já usado por login/ONU/IXC/OPA, editável pela Administração — commit `4d08d7a` já moveu esses toggles para lá).
- **Persistir primeiro, notificar depois.** O dispatcher (in-app agora, Slack depois) roda após o commit do alerta, best-effort, com falha registrada no próprio alerta (`notified_at`, `notify_error`) — exatamente o requisito "se Slack falhar, o alerta continua registrado".
- **O novo módulo nasce 100% no FilterContractV1**: nomes canônicos, envelope `meta` (`build_meta` de `ai_governance/response_meta.py`) em todo endpoint, desde o primeiro dia. Nenhum vocabulário paralelo novo.

---

## C. O que já existe e será reutilizado

| Existe hoje | Onde | Papel na plataforma |
|---|---|---|
| Funil de incidente de rede | `operations/login_aggregate.py::login_incident_analysis` (janela, quedas novas, ainda offline, reconexões, por regional/transmissor/PON/causa, clusters geo) | Vira o **detector do monitor de incidente coletivo** — chamado pelo monitor, não reescrito |
| Clusters DBSCAN de logins offline | `operations/login_geo_clusters.py` (grid espacial, union-find, semântica 'N' vs 'SS' medida em produção) | Núcleo da correlação geográfica; parâmetros viram config do monitor |
| Torre de Controle Preventiva | `GET /operations/overview/control-tower` (baseline 8 semanas, desvio, pressão, persistência em dias, nós críticos) | Detector do monitor de demanda/backlog; hoje só responde request — passa a ser executado e persistido |
| Insights heurísticos da gestão | `operations/queries.py::_insight` + `openings_analytics` (6 alertas com severidade) e `volume-alerts`, `sla-risk` | Detectores prontos de SLA/backlog/entrada×vazão |
| Telemetria ONU/PON/TX | `operations_onu_signal_current` (RX/TX dBm, `last_drop_cause`, `transmitter_id`, `pon_id`) | Evidência "PON/TX coincidentes" do incidente |
| Auditoria de coordenadas | `operations/coordinate_quality.py` (`valid_coverage_pct` por regional) | Fonte do **coverage** dos alertas geográficos (item K) |
| Padrão de run de job | `operations_import_runs`, `support_opa_import_runs` (contadores, status, checkpoint, retomada, advisory lock) | Molde de `intelligence_monitor_runs` |
| Padrão de scheduler | `ixc_scheduler.py` / `opa_scheduler.py` / snapshots login-ONU | Molde do Monitor Scheduler |
| Envelope `meta` / FilterContractV1 | `ai_governance/response_meta.py::build_meta` + 8 lotes concluídos | Confiabilidade de filtro/aviso em todos os endpoints novos |
| Notificações in-app | `services/notifications.py` + sino (`notification-bell.tsx`, polling 60s) | Primeiro canal do dispatcher (ex.: incidente CRITICAL notifica quem tem `intelligence:read`) |
| RBAC + perfis + visibilidade de módulo | `security.py`, `access_profiles`, `WorkspaceModuleVisibility` | Permissões `intelligence:*`; profile de TV restrito por perfil |
| Governança de IA + auditoria | `ai_governance/` (gate, field registry, audit best-effort) | O AI Analyst interno registra em `ai_access_audit_log` com origem própria (ex.: `origin="engine"`); tools MCP `opr_*` continuam como canal de IA interativa |
| Fuso e regionais canônicos | `parse_ixc_local_datetime`, `services/regional.py` / `lib/regional.ts` | Escopo de profile usa nomes canônicos de regional; tudo em `America/Porto_Velho` |
| UI base | ECharts, Leaflet imperativo, `section-card`, `summary-metric`, `tones.ts`, tokens de marca em `globals.css` | Base visual do cockpit (com camada de escala para TV) |
| Convenção de migrations | `YYYYMMDD_NNNN_desc.py`, cadeia linear | Migrations do módulo novo |

## D. O que precisa ser criado

**Backend (módulo `intelligence`):**
1. Registry de monitores + Monitor Scheduler (loop asyncio, config em `app_settings`).
2. Tabelas: `intelligence_monitor_runs`, `intelligence_alerts` (+ `intelligence_alert_events`), `intelligence_insights`, `intelligence_snapshots`, `intelligence_dashboard_profiles` (+ tokens de tela, se decidido em P.1).
3. Monitores fase 1 (adaptadores finos sobre funções existentes): incidente coletivo de rede, deterioração de SLA, crescimento de backlog / entrada×vazão, desvio de volume (torre de controle), saúde dos próprios monitores.
4. Lifecycle + dedupe + auto-resolve de alertas.
5. AI Gate + AI Analyst (primeira dependência de SDK LLM do projeto — hoje não há nenhuma chamada a LLM no backend; "IA" existente é governança de acesso + heurística determinística).
6. Cockpit API (`GET /cockpit/{profile_key}`) + CRUD de profiles na Administração.
7. Dispatcher de notificação (in-app; interface pronta para Slack depois).

**Frontend:**
8. Rota `/cockpit/[profileKey]` — layout novo, próprio para TV (o padrão visual atual é denso demais para leitura à distância: fontes de 9–11px onipresentes), polling no `refresh_seconds` do profile, sem sidebar/filtros interativos.
9. Painel de gestão de alertas/incidentes (ack, dismiss, histórico) — pode nascer simples dentro do cockpit ou da Administração.
10. Widgets iniciais (6–8): status geral, incidentes ativos, alertas por severidade, abertas×finalizadas, backlog, SLA, saúde dos monitores, AI insights.

**Não existe e é pré-requisito de decisão:** autenticação de TV (nenhum token público/kiosk existe hoje; as únicas rotas sem auth são health, login e OAuth do MCP) — ver P.1.

---

## E. Modelo conceitual das principais entidades

Nomes seguem a convenção de prefixo do módulo. Conceitual — colunas exatas na fase de implementação.

**`intelligence_monitor_runs`** — espelho do padrão `support_opa_import_runs`:
`monitor_key`, `started_at`, `finished_at`, `duration_ms`, `status` (`running|completed|completed_with_warnings|failed|interrupted`), `result_count`, `alerts_created`, `alerts_updated`, `alerts_resolved`, `error` (truncado), `stats_json`. O status `interrupted` cobre reinício de container no meio da execução (problema real do modelo lifespan-task).

**`intelligence_alerts`** — entidade única para alerta e incidente, diferenciada por `kind`:
- Identidade: `id`, `kind` (`alert|incident`), `alert_type` (`SLA_DETERIORATION`, `BACKLOG_GROWTH`, `VOLUME_ANOMALY`, `COLLECTIVE_OUTAGE`, `MONITOR_UNHEALTHY`, ...), `monitor_key`, **`dedupe_key`** (estável por monitor — ex.: `collective_outage:{regional}:{geohash_do_centroide}`; é o que impede "novo" a cada ciclo).
- Escopo: `scope_json` (`{regionals, cities, sector, team_model, ...}`) + colunas materializadas `regional`/`city` para índice e filtro de profile.
- Conteúdo: `severity` (`LOW|MEDIUM|HIGH|CRITICAL`), `title`, `summary`, `recommended_action`, `evidence_json`.
- Confiabilidade (item K): `confidence` (0–1), `coverage_json`, `warnings_json`, `source_last_sync`.
- Lifecycle: `status` (item I), `first_detected_at`, `last_seen_at`, `resolved_at`, `acknowledged_by/at`, `misses_count` (ciclos consecutivos sem re-detecção, para auto-resolve).
- Notificação: `notified_at`, `notify_error`.

Justificativa da entidade única: lifecycle, dedupe, severidade, escopo e notificação são idênticos para os dois; incidente é um alerta com evidência de correlação mais rica (clusters, PON/TX, O.S. de infra) e maior peso visual. Duas tabelas duplicariam toda a máquina de estados.

**`intelligence_alert_events`** — timeline append-only por alerta: `alert_id`, `event_type` (`detected|updated|escalated|confidence_changed|status_changed|ai_analyzed|notified|acknowledged|resolved`), `payload_json`, `created_at`, `created_by` (null = sistema). Dá o histórico do incidente e o "acompanhar evolução".

**`intelligence_insights`** — produção da IA, sempre estruturada:
`insight_type`, `severity`, `scope_json`, `confidence`, `title`, `summary`, `evidence_json`, `recommended_action`, `alert_id` (opcional — insight pode nascer de análise periódica sem alerta), `model`, `prompt_version`, `input_digest` (hash do input, para reprodutibilidade/custo), `status` (`active|superseded|expired|dismissed`), `valid_until`, `created_at`. O exemplo da visão (`SLA_DETERIORATION` em Ji-Paraná) é exatamente uma linha desta tabela.

**`intelligence_snapshots`** — estado agregado pré-computado por escopo, por ciclo:
`scope_key` (`global` ou regional canônica), `captured_at`, `overall_status` (`NORMAL|ATTENTION|RISK|CRITICAL`), `kpis_json` (abertas, finalizadas, backlog, SLA, quedas...), `active_alerts_count` por severidade, `data_freshness_json` (última sync por fonte). É o que a TV lê no topo; também vira histórico ("como estava a operação às 14h de ontem"). Segue o padrão consagrado do projeto: *tabela current implícita (última linha) + histórico append-only*.

**`intelligence_dashboard_profiles`** — item F.

**Futuro (não construir agora, só não impedir):** `intelligence_actions` — `insight_id/alert_id`, `action_type`, `status` (`recommended|approved|rejected|executed|failed`), `approved_by`, `executed_at`, `result_json`. O ciclo "IA recomenda → gestor aprova → sistema executa" é só esta tabela + executores; `recommended_action` como valor de enum (não texto livre) já deixa o encaixe pronto.

## F. Dashboard profiles

Tabela `intelligence_dashboard_profiles`:

```jsonc
{
  "key": "machadinho-operacional",        // slug, usado na URL da TV
  "name": "Machadinho Operacional",
  "purpose": "regional_tv",               // matrix_tv | regional_tv | incident_room | executive | noc
  "scope": {
    "regionals": ["UNI - MACHADINHO DOESTE"]   // nomes canônicos de regional.py; [] = UNI inteira
  },
  "widgets": [                             // ordem = prioridade visual
    {"type": "overall_status"},
    {"type": "incidents",   "min_severity": "MEDIUM"},
    {"type": "sla"},
    {"type": "backlog"},
    {"type": "production"},
    {"type": "ai_insights", "max_items": 3},
    {"type": "monitor_health"}
  ],
  "refresh_seconds": 60,
  "display": {
    "mode_rules": {"auto_incident_focus": true, "min_severity": "HIGH"},
    "show_ai": true
  },
  "active": true
}
```

- **Escopo é aplicado no servidor** (mesmo princípio do escopo regional obrigatório documentado em `controle_acesso_filtros_ecossistema.md`): o endpoint do cockpit filtra alertas/insights/snapshots pelo `scope` do profile; a TV não escolhe o que vê.
- **Widgets são um catálogo fechado em código** (como o registry de módulos): o profile escolhe quais, em que ordem e com que parâmetros. Sem editor drag-and-drop na fase 1 — CRUD de profile é um formulário na Administração (padrão das telas de config existentes, com `record_audit_log`).
- `purpose` diferencia pesos default (executivo = poucos números + tendências; incident room = incidentes em tela cheia), mas é o mesmo renderizador.

## G. Como diferentes TVs usam a mesma plataforma

- **Uma rota**: `/cockpit/[profileKey]`. TV da matriz abre `/cockpit/uni-geral`, Machadinho abre `/cockpit/machadinho-operacional`, sala de incidente abre `/cockpit/incidentes`. Zero páginas por regional.
- **Um endpoint**: `GET /api/intelligence/cockpit/{profile_key}` devolve payload único e completo:

```jsonc
{
  "profile": {"key": "...", "name": "...", "refresh_seconds": 60, "widgets": [...]},
  "snapshot": {"overall_status": "ATTENTION", "captured_at": "...", "kpis": {...}},
  "alerts":   [ ...ativos no escopo, ordenados por severidade/first_detected_at... ],
  "insights": [ ...ativos no escopo... ],
  "monitor_health": [ {"monitor_key": "...", "healthy": true, "last_run_at": "...", "next_expected_at": "..."} ],
  "display_mode": "NORMAL",          // NORMAL | ATTENTION | INCIDENT — calculado no servidor
  "meta": { "generated_at": "...", "data_freshness": {"ixc_orders": "...", "login_status": "...", "opa": "..."}, "warnings": [...] }
}
```

- A TV é **burra por desenho**: renderiza o payload e refaz o fetch a cada `refresh_seconds`. Polling é suficiente (dados de origem mudam a cada 5–20 min; não há SSE/WebSocket no projeto e não vale introduzir agora).
- `display_mode` calculado no servidor (a partir de `mode_rules` + alertas ativos) é o que permite a TV destacar um incidente crítico automaticamente e voltar ao normal — a automação futura muda regra no servidor, não a TV.
- Perfis novos (NOC, executivo, Ji-Paraná com peso em backlog) = linhas novas na tabela, sem deploy.

## H. Como AI Insights entram no sistema

```
monitor detecta / atualiza alerta
   → AI Gate decide se merece análise:
       severidade ≥ limiar? é novidade (dedupe_key novo ou escalada)? 
       cooldown do escopo respeitado? orçamento diário de chamadas ok?
   → enfileira job de análise (task asyncio separada — nunca no loop dos monitores,
     nunca no request da TV)
   → AI Analyst monta o contexto chamando as MESMAS funções de consulta
     (login_incident_analysis, control_tower, backlog_aging, coordinate_quality...),
     inclui meta/coverage/warnings no prompt
   → chamada LLM com saída estruturada forçada (JSON schema = intelligence_insights;
     tool use / structured output, não parsing de texto livre)
   → validação (Pydantic; insight_type/severity/recommended_action são enums;
     confidence obrigatória; resposta inválida = retry limitado, depois descarte logado)
   → persiste intelligence_insights + evento ai_analyzed no alerta
   → dispatcher notifica se aplicável
   → cockpit lê da tabela — a TV NUNCA espera a IA
```

Pontos firmes:

- **A IA nunca é chamada no caminho de leitura.** Se a análise ainda não rodou, a tela mostra o alerta heurístico sem o insight; o insight aparece no refresh seguinte.
- **Prompt versionado** (`prompt_version` no insight) e `input_digest` para reprodutibilidade e auditoria de custo.
- **Além do modo reativo (por alerta), um modo periódico barato**: 1–2 análises/dia por escopo do tipo "o que mudou e merece decisão" para o widget executivo — também via gate/orçamento.
- **Escopo de escrita zero**: o AI Analyst só lê funções de consulta e só escreve em `intelligence_insights`. Ação crítica é estruturalmente impossível nesta fase; a evolução futura é o `intelligence_actions` (item E), não permissão nova para o modelo.
- Auditoria: cada chamada registrada (padrão best-effort do `ai_governance/audit.py`, sem gravar dado sensível, como já é feito — `summarize_filters` nunca grava valores).
- Novidade real: **primeira dependência de SDK de LLM do backend** (hoje não há nenhuma). Chave via `.env`/`app_settings`, mesma disciplina dos tokens IXC/OPA (só backend/VM). Decisão P.2.

## I. Lifecycle de alertas/incidentes

Estados (coluna `status` de `intelligence_alerts`):

```
NEW ──→ INVESTIGATING ──→ CONFIRMED ──→ IN_PROGRESS ──→ RECOVERING ──→ RESOLVED
 │            │                                              ↑
 │            └── (IA ou re-detecção eleva confiança) ───────┘
 └──→ DISMISSED (humano)          qualquer estado ──→ EXPIRED (dado ficou velho)
```

- **NEW** — primeira detecção do `dedupe_key`.
- **INVESTIGATING** — análise de IA enfileirada/em curso, ou confiança abaixo do limiar de confirmação.
- **CONFIRMED** — confiança ≥ limiar (heurística forte ou IA) e re-detecção persistente.
- **IN_PROGRESS** — sinal de tratamento (ex.: O.S. de infra em execução na área do cluster — evidência que `login_incident_analysis` + busca de O.S. já permitem) ou marcação manual do gestor.
- **RECOVERING** — o monitor observa reversão (reconexões superando quedas, backlog caindo) mas ainda não estabilizou.
- **RESOLVED** — `misses_count` ≥ N ciclos sem re-detecção (auto-resolve), ou resolução manual. Guarda tudo para histórico.
- **DISMISSED/EXPIRED** — descarte humano / dado-fonte velho demais para sustentar o alerta (ligado ao `source_last_sync`).

Mecânica anti-"novo a cada ciclo": o monitor calcula o `dedupe_key`; se já existe alerta não-resolvido com essa chave, **atualiza** (`last_seen_at`, evidência, severidade — com evento `escalated` se subir, confiança) em vez de criar. Cada transição vira linha em `intelligence_alert_events`. Alerta resolvido há mais de X horas com nova detecção do mesmo `dedupe_key` = alerta novo (reincidência, linkável ao anterior via evento).

## J. monitor_runs na arquitetura

Resolve o problema real já vivido: distinguir "não houve alerta" de "o monitor não rodou".

- Toda execução grava `intelligence_monitor_runs` com início, fim, duração, status, contagens e erro — antes de qualquer avaliação de resultado (padrão `OperationImportRun`: a run nasce `running` e é finalizada no `finally`).
- Saúde derivada, por monitor: `last_run`, `last_success`, `consecutive_failures`, `next_expected_at` (agora + intervalo configurado). **Stale = agora > next_expected_at + tolerância** → o próprio sistema abre alerta `MONITOR_UNHEALTHY` (o meta-monitor de saúde é um monitor como os outros, e o widget `monitor_health` da TV mostra isso).
- Difere do padrão atual dos syncs (que guardam só último estado em `app_settings`, sem histórico — limitação anotada em `ixc_scheduler.py`: "não existe alerta ativo neste projeto"): aqui queremos histórico consultável e alerta ativo, por isso tabela própria.
- Retenção com purga (ex.: 90 dias) desde o dia 1 — o projeto já tem tabela de 11M linhas (`operations_login_status_snapshots`) e sabemos o custo de crescer sem plano.
- Reinício de container no meio da execução → run fica `interrupted` na inicialização seguinte (detectável: `running` com `started_at` velho), nunca `running` fantasma.

## K. Confiança / coverage / warnings

Regra de ouro, herdada da Fase 1 de confiabilidade: **nenhum número na TV sem a incerteza que o acompanha.**

1. **Todo detector propaga o `meta` que já recebe.** As funções de consulta já devolvem `applied_filters`, `warnings`, `source_last_sync`. O monitor copia isso para `warnings_json` e `source_last_sync` do alerta — não reinventa.
2. **Coverage explícito para conclusões geográficas.** Antes de afirmar "nenhum cluster encontrado", o monitor de incidente consulta `coordinate_quality_audit` para o escopo e grava `coverage_json` (ex.: `{"coordinate_coverage_pct": 71.4, "population": 8812}`). A TV exibe: *"Sem clusters detectados — cobertura de coordenadas: 71%"*. Coverage abaixo de limiar rebaixa a confiança da ausência, nunca vira certeza.
3. **Confidence com semântica definida**: heurística pura recebe faixas fixas por tipo de detecção (documentadas no registry do monitor); IA fornece a sua, e a maior evidência convergente (cluster + quedas simultâneas + TX/PON + O.S. de infra) soma — o exemplo "Confiança: 92%" da visão é a soma dessas evidências, cada uma listada em `evidence_json`.
4. **Freshness sempre visível**: `data_freshness` no payload do cockpit (por fonte: O.S., login, ONU, OPA) + `source_last_sync` por alerta. Fonte atrasada além do intervalo esperado gera warning no snapshot e pode acionar `MONITOR_UNHEALTHY` — dado velho exibido como fresco é o pior modo de falha de uma TV de operação.
5. **Warnings estruturados com `code`** (padrão já estabelecido: `PARTIAL_FILTER_SCOPE`, `PARTIAL_DIMENSION_COVERAGE`...), nunca strings soltas.

## L. Wireframe textual do Cockpit de TV (1920×1080)

```
┌────────────────────────────────────────────────────────────────────────────────┐
│  UNI INTERNET — OPERAÇÃO AGORA          [logo]        🟡 ATENÇÃO    14:32       │  ~10%
│  Machadinho Operacional · dados de 14:28 · monitores 🟢 5/5                    │
├───────────────────────────────┬────────────────────────────────────────────────┤
│  PROBLEMAS AGORA (prioridade) │   OPERAÇÃO                                     │
│                               │  ┌──────────┬──────────┬──────────┬─────────┐  │
│  🔴 POSSÍVEL INCIDENTE        │  │ ABERTAS  │ FINALIZ. │ BACKLOG  │  SLA    │  │
│  Castanheiras — Linha 160     │  │   47     │   39     │  212     │  78%    │  │
│  7 O.S. · 18 logins offline   │  │  hoje    │  hoje    │ ▲ +14 7d │ ▼ meta  │  │
│  quedas em 2 min · TX/PON     │  └──────────┴──────────┴──────────┴─────────┘  │
│  coincidentes · Infra em      │                                                │  ~55%
│  execução                     │   ABERTAS × FINALIZADAS (7d)     [gráfico]     │
│  Confiança 92% · CONFIRMED    │   ▁▂▃▅▃▂▅  entrada                             │
│  → evitar despacho individual │   ▁▂▂▃▃▂▃  vazão                               │
│                               │                                                │
│  🟠 SLA deteriorando          │   BACKLOG POR REGIONAL           [barras]      │
│  Ji-Paraná · 7d: 65% (MTD 69%)│                                                │
│  entrada estável → gargalo    │                                                │
│  de fechamento · conf. 91%    │                                                │
│  → priorizar O.S. salváveis   │                                                │
├───────────────────────────────┴────────────────────────────────────────────────┤
│  💡 IA: Perfil de demanda em Ariquemes mudou — assunto "Sem conexão" 2,3× acima│
│  do padrão de terça; produção compatível. Acompanhar sem realocar equipe.      │  ~15%
├────────────────────────────────────────────────────────────────────────────────┤
│  Fontes: O.S. 14:28 · Logins 14:30 · ONU 14:20 · OPA 14:15   Cobertura geo 71% │  ~5%
└────────────────────────────────────────────────────────────────────────────────┘
```

- **Modo INCIDENT** (automático via `display_mode`): a coluna esquerda expande para ~60% da tela com o incidente crítico + mapa do cluster (Leaflet já dominado no projeto); KPIs comprimem.
- Regras de leitura à distância: título/status geral legível a 5 m (números ≥ ~72px, títulos ≥ ~40px), no máximo 2 gráficos simultâneos, sem tabela densa, sem interação. Fundo branco (identidade), cores semânticas atuais (emerald/amber/red) + azuis da marca.
- Nada de excesso: se não há problema, a coluna esquerda diz "🟢 Nenhum problema ativo" e lista os últimos resolvidos — a ausência também é informação (com coverage, item K).

## M. Roadmap em fases pequenas

Cada fase entrega valor sozinha, no padrão de lotes com commit de código + doc + teste contra dado real que o projeto já pratica.

- **F0 — Fundação (sem tela):** módulo `intelligence` + registry de monitores + scheduler + `intelligence_monitor_runs` + meta-monitor de saúde. Primeiro monitor: incidente coletivo (adaptador sobre `login_incident_analysis`), ainda sem alerta persistido — só runs. *Prova: distinguir "não rodou" de "não alertou".*
- **F1 — Alertas com memória:** `intelligence_alerts` + `intelligence_alert_events`, dedupe, lifecycle, auto-resolve. Migrar 3 detectores (incidente coletivo, torre de controle/volume, SLA). Notificação in-app para CRITICAL. *Prova: mesmo incidente não renasce a cada ciclo; histórico consultável.*
- **F2 — Cockpit v1:** `intelligence_snapshots` + `intelligence_dashboard_profiles` + endpoint `GET /cockpit/{key}` + rota `/cockpit/[profileKey]` com widgets essenciais (status geral, problemas, KPIs, saúde dos monitores, freshness). Um profile: UNI Geral. Autenticação conforme P.1. *Prova: TV da matriz no ar.*
- **F3 — Perfis e escopo:** CRUD de profiles na Administração, escopo por regional aplicado no servidor, profiles Machadinho e Ji-Paraná, widget de backlog/produção por escopo. *Prova: 3 TVs, zero páginas novas.*
- **F4 — IA analista:** SDK LLM, AI Gate, `intelligence_insights`, análise reativa de alertas HIGH/CRITICAL, widget `ai_insights`, prompt/orçamento versionados. *Prova: insight estruturado real na TV, custo sob controle.*
- **F5 — Modos e sala de incidente:** `display_mode` com `mode_rules`, layout INCIDENT com mapa, profile "Sala de Incidente", ack/dismiss na UI de gestão.
- **F6 — Canais externos e executivo:** Slack (construção nova — dispatcher já pronto para plugar), análise periódica executiva, profile executivo.

## N. O que NÃO construir agora

- **Slack** — não existe nenhuma integração hoje; entra só na F6, atrás do dispatcher (persistência primeiro já garantida por desenho).
- **WebSocket/SSE/push** — polling de 30–60s cobre TV com fontes de 5–20 min; nada no projeto usa streaming.
- **Fila/broker (Celery/RQ/Redis)** — o padrão asyncio + tabelas de run resolve; broker é custo operacional novo em VM única.
- **Execução de ações pela IA** (fechar O.S., transferir técnico...) — só o encaixe conceitual (`intelligence_actions`, `recommended_action` como enum).
- **Editor visual de dashboards (drag-and-drop)** — catálogo fechado de widgets + formulário admin basta por muito tempo.
- **Automação completa de modos de exibição** — F2/F3 usam regra simples no servidor; sofisticação depois.
- **Dark mode geral do Workspace** — declarado no Tailwind mas nunca usado; a TV define a própria aparência e não puxa esse débito.
- **Correlação PON/TX avançada além do que `operations_onu_signal_current` já dá** — a auditoria OPA mostrou o custo de prometer indicador sem fonte validada; mesmo princípio aqui.
- **Reescrever detectores existentes** — torre de controle, clusters e heurísticas continuam onde estão; monitores são adaptadores.
- **`meta` retroativo nos endpoints REST antigos** — é backlog do FilterContractV1 (fase própria), não desta plataforma.

## O. Principais riscos técnicos

1. **Loop asyncio único / reinício de container.** Deploy no meio de um ciclo mata monitor e análise de IA. Mitigação: runs `interrupted` + idempotência por dedupe (re-detecção no próximo ciclo reconstrói estado), fila de IA reprocessável na inicialização.
2. **Fadiga de alerta / falso positivo.** O maior risco de produto: TV que grita sempre vira TV ignorada. Mitigação: dedupe rígido, cooldown, limiar de persistência antes de CONFIRMED, tuning com dado real antes de expor (prática já usada nos clusters — a semântica 'SS' crônico foi medida antes de codificar).
3. **Custo/latência/variabilidade do LLM.** Mitigação: gate com orçamento diário, saída estruturada com schema forçado + validação Pydantic + descarte logado, IA fora do caminho de leitura, `input_digest` para evitar reanálise do mesmo estado.
4. **Crescimento de tabelas.** `alert_events`, `monitor_runs` e `snapshots` crescem para sempre. Retenção/purga definida na migration inicial, índices pensados para a consulta do cockpit (status ativo + escopo).
5. **Token de TV = dado operacional sem login.** Qualquer esquema de tela pública expõe dados. Escopo mínimo (`cockpit:read` de um profile específico), revogável, auditado — decisão P.1 antes de qualquer código.
6. **Contaminação por vocabulário legado de filtros.** O REST antigo ainda usa nomes não-canônicos (`subjects` etc.). O módulo novo só fala canônico + `meta`; nunca importar o vocabulário do `operations-api.ts` para o cockpit.
7. **Frontend sem camada de estado/servidor.** Páginas atuais são máquinas de `useState` gigantes. O cockpit deve nascer simples (1 fetch, 1 payload, render); o painel de gestão de alertas é a hora de considerar React Query — sem refatorar o legado junto.
8. **Fuso.** Tudo em `America/Porto_Velho` via helpers existentes; erro de 4h já aconteceu (commit `2260693`) e numa TV de "operação agora" seria desastroso.
9. **Confiança na ausência.** "Nenhum incidente" com fonte atrasada ou cobertura baixa é o modo de falha mais perigoso do cockpit — por isso freshness e coverage são obrigatórios no payload, não opcionais.

## P. Decisões necessárias antes de implementar

1. **Autenticação da TV.** Opções: (a) token de dispositivo somente-leitura, vinculado a um profile, criado/revogado na Administração — *recomendada*; (b) usuário kiosk com perfil de acesso mínimo (zero código novo de auth, mas senha em TV e sessão de 12h que expira); (c) rota sem auth restrita por rede. Impacta F2 inteira.
2. **LLM: provedor, modelo e orçamento.** Recomendação: API da Anthropic (Claude) com saída estruturada; definir modelo por tarefa (análise reativa × resumo executivo), teto diário de chamadas e onde vive a chave (`.env` da VM, como IXC/OPA).
3. **Fronteira do módulo.** Confirmar módulo novo `intelligence` (recomendado) vs. crescer dentro de `operations`. Define permissões (`intelligence:read`, `intelligence:manage`), prefixos e o registro no workspace.
4. **Entidade única alerta+incidente** (com `kind`) vs. tabelas separadas. Recomendação: única — item E.
5. **Tipografia da TV: Poppins ou Inter?** A visão pede Poppins; o padrão oficial do projeto (`PADRAO_VISUAL_OFICIAL_UNI_OPR.md`) e o código usam Inter. Se Poppins, decidir se é só no cockpit ou se muda o padrão oficial.
6. **Widgets da F2** — quais 6–8 exatos entram no primeiro cockpit (proposta no item L).
7. **Limiares iniciais** — o que é ATTENTION/RISK/CRITICAL no status geral; N ciclos para auto-resolve; severidade mínima para IA e para notificação in-app. Podem viver em `app_settings` (ajustáveis sem deploy), mas os valores de partida precisam ser definidos com a operação.
8. **Retenção** — quantos dias de `monitor_runs`, `alert_events` e `snapshots`.
9. **Quem vê o quê** — TV regional mostra só a regional (escopo duro) ou também o status geral da UNI no rodapé? Executivo enxerga alertas LOW? Define o resolvedor de escopo.
10. **Ordem F4 × F3** — IA antes de multi-profile (mais "wow", valida o motor) ou multi-profile antes (mais TVs úteis rápido)? O roadmap propõe profiles primeiro; inverter é barato se preferir.

---

*Documento de estudo — nenhuma linha de código, migration ou alteração de frontend/backend foi feita. Próximo passo: validar as decisões do item P e escolher a fase inicial.*
