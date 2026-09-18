# Cobertura de dados — matriz módulo → dataset → interface → documentação → testes → pendências

Commit analisado: `6c0e69ea531ee28fa5f4fe2cf54a59c5b59cac08` · Data: 2026-09-17

Esta matriz distingue **documentação completa** de **acesso completo** — são resultados diferentes. Um dataset pode estar 100% documentado neste pacote e ainda não ter sido tecnicamente testado ponta-a-ponta, nem validado pela área de negócio responsável. As duas últimas colunas nunca devem ser lidas como concluídas só porque as três primeiras estão.

## Legenda

- **Encontrado**: confirmado no código-fonte nesta análise (arquivo:linha).
- **Documentado**: descrito neste pacote (catalogo.md/catalogo.json) e/ou em docs/api-*.md.
- **API**: existe endpoint GET funcional que expõe o dado hoje.
- **Testado**: existe teste automatizado cobrindo o dado/endpoint (backend/tests/), mesmo que parcial.
- **Validado pela área**: alguém do negócio confirmou que o número bate com a fonte/sistema de origem. **Nenhum item deste pacote está marcado como validado — isso é trabalho da área, não desta análise.**

## Matriz

| Módulo | Dataset | Interface de consulta | Documentação | Testes | Validação de negócio | Pendências |
|---|---|---|---|---|---|---|
| Operação Analítica | `ds.operations.orders` | `GET /api/operations/orders`, `GET /api/operations/orders/{source_order_id}`, `GET /api/operations/overview`, `GET /api/operations/sla` | catalogo.md#dsoperationsorders | parcial — cobertura via testes automatizados backend/tests/test_operations_module.py e correlatos, não 100% de campos | False | validação de negócio pendente |
| Operação Analítica | `ds.operations.login_current_status` | `GET /api/operations/network/logins`, `GET /api/operations/network/login-detail` | catalogo.md#dsoperationslogin_current_status | False | False | cobertura de teste automatizado incompleta; validação de negócio pendente |
| Operação Analítica | `ds.operations.login_status_snapshot` | `GET /api/operations/network/login-outages`, `GET /api/operations/network/login-timeseries` | catalogo.md#dsoperationslogin_status_snapshot | False | False | cobertura de teste automatizado incompleta; validação de negócio pendente |
| Operação Analítica | `ds.operations.onu_signal_current` | `GET /api/operations/network/onu-signal`, `GET /api/operations/network/onu-signal/history` | catalogo.md#dsoperationsonu_signal_current | False | False | cobertura de teste automatizado incompleta; validação de negócio pendente |
| Operação Analítica | `ds.operations.backlog_snapshot` | `GET /api/operations/overview/backlog-trend` | catalogo.md#dsoperationsbacklog_snapshot | False | False | cobertura de teste automatizado incompleta; validação de negócio pendente |
| Operação Analítica | `ds.operations.customer_contract` | `usado internamente por warranty_analytics, sem endpoint de listagem direta confirmado nesta análise` | catalogo.md#dsoperationscustomer_contract | False | False | cobertura de teste automatizado incompleta; validação de negócio pendente |
| Operação Analítica | `ds.operations.branch_capacity` | `GET /api/operations/branch-capacity`, `GET /api/operations/capacity-summary` | catalogo.md#dsoperationsbranch_capacity | False | False | cobertura de teste automatizado incompleta; validação de negócio pendente |
| Operação Analítica | `ds.operations.team_target_version` | `GET /api/operations/team-configuration` | catalogo.md#dsoperationsteam_target_version | False | False | cobertura de teste automatizado incompleta; validação de negócio pendente |
| SGP Suporte | `ds.support.opa_attendance` | `GET /api/support/opa/attendances`, `GET /api/support/opa/overview`, `GET /api/support/opa-metrics` | catalogo.md#dssupportopa_attendance | parcial | inconclusivo — ver docs/roteiro-comparacao-tmr-opa-suite.md, comparação com painel oficial OPA terminou classificada como Inconclusivo | cobertura de teste automatizado incompleta |
| SGP Suporte | `ds.support.ixc_ticket` | `GET /api/support/ixc/tickets`, `GET /api/support/ixc/tickets/overview`, `GET /api/support/ixc/analytics/context` | catalogo.md#dssupportixc_ticket | parcial | False | cobertura de teste automatizado incompleta; validação de negócio pendente |
| Agendamento | `ds.scheduling.order` | `GET /api/scheduling/orders`, `GET /api/scheduling/dashboard` | catalogo.md#dsschedulingorder | parcial | False | cobertura de teste automatizado incompleta; validação de negócio pendente |
| Agendamento | `ds.scheduling.event` | `GET /api/scheduling/operators/{id}/events`, `GET /api/scheduling/technicians/{id}/events`, `GET /api/scheduling/orders/{id}/timeline` | catalogo.md#dsschedulingevent | parcial | False | cobertura de teste automatizado incompleta; validação de negócio pendente |
| Gamificação Operacional | `ds.gamification.service_order` | `GET /api/service-orders`, `GET /api/service-orders/period-summary`, `GET /api/service-orders/subject-summary` | catalogo.md#dsgamificationservice_order | True | False | validação de negócio pendente |
| Gamificação Operacional | `ds.gamification.collaborator` | `GET /api/collaborators/registry`, `GET /api/collaborators/{id}/service-orders-detail`, `GET /api/collaborators/{id}/monthly-history` | catalogo.md#dsgamificationcollaborator | True | False | validação de negócio pendente |
| Gamificação Operacional | `ds.gamification.calculation_run` | `GET /api/calculation-runs`, `GET /api/calculation-runs/{id}`, `GET /api/calculation-runs/latest`, `GET /api/calculation-runs/{id}/snapshot` | catalogo.md#dsgamificationcalculation_run | True | False | validação de negócio pendente |
| Gamificação Operacional | `ds.gamification.collaborator_score` | `GET /api/calculation-runs/{id} (inclui breakdown)`, `GET /api/dashboard/summary` | catalogo.md#dsgamificationcollaborator_score | True | False | validação de negócio pendente |
| Gamificação Operacional | `ds.gamification.collaborator_point_balance` | `GET /api/collaborators/{id}/point-balance`, `GET /api/point-balance/pending` | catalogo.md#dsgamificationcollaborator_point_balance | True | False | validação de negócio pendente |
| Gamificação Operacional | `ds.gamification.import_run` | `GET /api/imports/runs`, `GET /api/imports/runs/{id}/audits`, `GET /api/imports/runs/{id}/errors` | catalogo.md#dsgamificationimport_run | True | False | validação de negócio pendente |
| Gestão Integrada | `ds.management.case` | `GET /api/management/cases`, `GET /api/management/cases/{id}`, `GET /api/management/cases/justifications` | catalogo.md#dsmanagementcase | parcial | False | cobertura de teste automatizado incompleta; validação de negócio pendente |
| Gestão Integrada | `ds.management.operational_member` | `GET /api/management/dashboard` | catalogo.md#dsmanagementoperational_member | parcial | False | cobertura de teste automatizado incompleta; validação de negócio pendente |
| UNI Intelligence | `ds.intelligence.alert` | `GET /api/intelligence/alerts`, `GET /api/intelligence/alerts/{id}` | catalogo.md#dsintelligencealert | False | False | cobertura de teste automatizado incompleta; validação de negócio pendente |
| UNI Intelligence | `ds.intelligence.monitor_run` | `GET /api/intelligence/monitors`, `GET /api/intelligence/monitor-runs` | catalogo.md#dsintelligencemonitor_run | False | False | cobertura de teste automatizado incompleta; validação de negócio pendente |
| Administração | `ds.admin.collaborator_pii` | `GET /api/admin/people-structure (CPF mascarado)` | catalogo.md#dsadmincollaborator_pii | False | False | cobertura de teste automatizado incompleta; validação de negócio pendente |

## Lacunas de acesso (dado existe, mas não é acessível hoje por API de leitura adequada ao cubo)

- **`gap.no_central_company_regional_table`** — Não existe tabela central de Empresa/Regional/Unidade com FK. 'Regional' é texto normalizado via backend/app/services/regional.py, com DUAS normalizações divergentes: granular (Operação Analítica, Suporte) e agrupada (Gamificação). A mesma palavra 'regional' tem dois significados diferentes dependendo do módulo consumido. _(impacto: cubo de dados corporativo precisa decidir explicitamente qual granularidade usar por indicador, e documentar a escolha — não pode assumir que 'regional' em duas tabelas é comparável sem checar qual normalização cada módulo aplica)_
- **`gap.no_secrets_manager`** — Não há secrets manager integrado (Vault/AWS Secrets Manager/etc.) — segredos hoje são variáveis de ambiente simples (.env / Docker Compose). A regra do projeto (docs/manual_programacao_senior.md) exige secret manager 'quando houver', mas não há um configurado. _(impacto: criação da credencial técnica read-only do cubo (seção 5 do pedido original) fica sem local seguro dedicado até esta lacuna ser resolvida — ver acesso.md)_
- **`gap.no_central_auth_middleware`** — Não há middleware ASGI central de autenticação/autorização — proteção é 100% via dependency injection do FastAPI, declarada rota a rota ou por APIRouter. Uma rota nova fica pública por padrão se o desenvolvedor esquecer a dependency. _(impacto: qualquer endpoint novo criado para o cubo precisa ser auditado individualmente quanto à presença da dependency de permissão — não há rede de segurança automática)_
- **`gap.mcp_connector_scope`** — O conector MCP existente (opr_* tools) já é essencialmente uma identidade técnica read-only, mas cobre só Operação Analítica, Suporte, Agendamento, Gestão e Cockpit — NÃO cobre Gamificação, Administração nem UNI Localiza. _(impacto: se o cubo precisar de Gamificação (pontuação/pagamento), a integração REST (openapi.yaml) é a via, não o MCP existente)_
- **`gap.docs_exposed_outside_production`** — /docs, /redoc e /openapi.json do FastAPI ficam habilitados sempre que APP_ENV != 'production' (backend/app/main.py:209-217) — usado nesta análise para extrair o openapi.yaml real. Se algum ambiente de homologação acessível publicamente estiver com APP_ENV diferente de 'production', a superfície completa da API (incluindo rotas de escrita) fica documentada sem exigir login para visualizar o contrato. _(impacto: não é uma vulnerabilidade de dado (ainda exige autenticação para CHAMAR as rotas), mas é exposição de superfície de ataque — confirmar com a equipe de infraestrutura o APP_ENV de cada ambiente antes de considerar o pacote 'pronto' para qualquer ambiente que não seja desenvolvimento local)_
- **`gap.login_status_history_retention`** — Histórico de status de login (operations_login_status_snapshots) tem retenção padrão de 14 dias, com purga automática desde o incidente de disco de 2026-09-17. _(impacto: um cubo que precise de histórico de conectividade de longo prazo precisa de extração periódica própria — o sistema operacional não é a fonte de verdade de longo prazo para esse dado)_
- **`gap.service_order_vs_operation_order`** — Ver relationship rel.service_order__operation_order_NOT_CONFIRMED — dois datasets de O.S. que podem ou não representar as mesmas ordens de serviço, sem chave comprovada de cruzamento. _(impacto: risco de dupla contagem se o cubo tentar somar métricas de Gamificação e Operação Analítica sobre 'O.S.' sem entender que são dois pipelines/possivelmente duas populações distintas)_
- **`gap.management_case_race_condition`** — ManagementCase não tem UniqueConstraint de banco sobre a chave lógica de negócio (case_type+responsible_name+regional+período) — só índices normais. A idempotência de get_or_create_daily_case/monthly_case e generate_performance_cases é garantida inteiramente em código Python (SELECT + checagem em memória), sem SELECT...FOR UPDATE nem lock explícito. _(impacto: sob concorrência real (duas requisições/jobs simultâneos para o mesmo responsável/dia), existe uma janela teórica de corrida que pode gerar casos duplicados logicamente — um cubo que agregue 'quantidade de casos' por responsável/dia pode contar duplicidade real de dados, não erro de consulta, se esse cenário já tiver ocorrido em produção)_
- **`gap.period_orders_ambiguity`** — Existem duas funções de filtro de período na Gamificação (scoring_detail.py): period_orders (filtro estrito, exige mês/ano exato calculado a partir de closed_at ou opened_at) e period_orders_for_aggregation (mesma janela SQL, mas SEM o filtro estrito de mês/ano em Python — mais permissiva). Não há comentário no código explicando por que as duas existem nem quando usar cada uma. _(impacto: um cubo que replique 'contagem de O.S. do período' pode obter números diferentes dependendo de qual das duas lógicas usar como referência — não presumir que ambas retornam o mesmo conjunto)_

## Achados validados contra o Painel Executivo real (2026-09-17)

Validação cruzada de um painel real ("Painel do CEO — Operações", ambiente de produção) contra a
API documentada. Achados por bloco do painel:

| Bloco do painel | Endpoint real | Status |
|---|---|---|
| SLA de Ativação / SLA de Suporte, por Fibra Urbana/Fibra Rural/Rádio | `GET /api/operations/sla?group_by=subject` (`operations:view_sla`) | **Resolvido nesta validação** — não é uma dimensão nativa da API. O endpoint devolve SLA por `subject` (assunto granular de O.S., ex. "Instalação Fibra Urbana", "Suporte Externo Fibra Rural"); o painel agrupa esses valores em 6 buckets usando uma tabela de regras fornecida pelo usuário (`regras-agrupamento-sla-tecnologia.json`, cópia salva neste pacote) e calcula o % agregado do lado do consumidor. Confirmado no código: `backend/app/services/ixc_importer.py:227-239` já usa a mesma granularidade de `os_subject` para uma classificação análoga (`os_type`), e o `subject` é opção válida de `group_by` em `backend/app/modules/operations/router.py:1145`. |
| CSAT Suporte Interno (atendimento/call center) | `GET /api/support/opa/overview` → campo `avg_rating`, de `SupportOpaAttendance.rating` | **Confirmado real** — avaliação do cliente por atendimento, calculada em `opa_overview_service.py:114/387`. |
| CSAT Suporte de Campo (visita técnica) | — | **Gap real, não resolvido.** Nenhum campo de avaliação/pesquisa de satisfação existe em Operação Analítica (`operations_orders`) nesta análise. O número desse bloco do painel não tem fonte confirmada nesta API. |
| Atendimentos por IA x Humano | `GET /api/support/opa/breakdowns` (agrupamento `bot_human`) | Confirmado. |
| Atendimentos por Canal (WhatsApp/PABX/Page) | `GET /api/support/opa/breakdowns` (agrupamento `channel`) | Confirmado. |
| OS Finalizadas por Unidade Regional | `GET /api/operations/overview/regional-matrix` | Confirmado. |
| Análise do Diretor / Pontos de Atenção / Recomendações | — | Não é dado de API — texto analítico gerado pelo lado do cubo em cima dos números acima. |

Arquivo de referência: [regras-agrupamento-sla-tecnologia.json](regras-agrupamento-sla-tecnologia.json)
— mapeamento `assunto granular → grupo por tecnologia`, fornecido pelo dono do sistema, usado para
reproduzir a mesma segmentação do painel a partir de `GET /api/operations/sla?group_by=subject`.

## Cobertura por interface de integração

| Interface | Cobre | Não cobre | Observação |
|---|---|---|---|
| REST (`openapi.yaml`, gerado do schema real do FastAPI) | Todos os 7 módulos de negócio (330 rotas, 392 operações) | — | Inclui rotas de ESCRITA que pertencem às telas — o cubo deve consumir só as operações GET, ver acesso.md |
| Conector MCP (`docs/api-mcp-connector.md`, 38 tools `opr_*`) | Operação Analítica, Suporte, Agendamento, Gestão, Cockpit (leitura) | Gamificação, Administração, UNI Localiza | Já é read-only por design (37/38 tools); pensado para agentes de IA, não para um conector de BI tradicional |
| `/api/ai` (API de IA, header `x-api-key`) | Operação (10 rotas), Rede/infraestrutura (11 rotas), Gestão Integrada (4 rotas) | Gamificação, Suporte, Agendamento, Intelligence, Administração | Camada de consulta sobre Operações/Gestão, com governança campo-a-campo (`AiFieldPermission`) — ver acesso.md |
