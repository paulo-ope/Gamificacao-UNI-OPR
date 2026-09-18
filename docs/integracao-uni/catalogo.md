# Catálogo de dados — UNI Workspace (versão legível)

> Versão estruturada consumível por máquina: [catalogo.json](catalogo.json) (schema_version 1.0.0).
> Commit analisado: `6c0e69ea531ee28fa5f4fe2cf54a59c5b59cac08` — data da análise: 2026-09-17.
> Como atualizar: Reexecutar: (1) `docker compose up -d db backend` local; (2) `curl http://localhost:8000/openapi.json` para atualizar openapi.yaml (script de referência em docs/integracao-uni/README.md); (3) revisar catalogo.json/catalogo.md campo a campo contra o código dos módulos que mudaram desde o commit acima (ver docs/STATUS.md); (4) reexecutar docs/integracao-uni/exemplos/consumidor.py contra homologação para validar.

## Fora do escopo deste catálogo

- backend/app/modules/ai/ (camada de consulta, não tem dataset próprio além de ApiKeyCredential, que é segredo)
- backend/app/modules/mcp_connector/ (protocolo MCP, não REST — contrato nativo já documentado em docs/api-mcp-connector.md)
- Conteúdo binário (fotos de colaborador) — deliberadamente fora do escopo de um cubo analítico

## Datasets

Cada dataset abaixo traz: entidade/tabela, o que é 1 registro, chave, campos-chave com significado de nulos quando relevante, relações e a matriz de cobertura (encontrado/documentado/API/testado/validado pela área).

### Operação Analítica

#### `ds.operations.orders` — OperationOrder

- **Tabela**: `operations_orders`
- **Descrição**: 1 registro = 1 Ordem de Serviço (O.S.) do IXC, projetada/normalizada a partir de su_oss_chamado. Maior dataset de negócio do sistema.
- **Evidência**: `backend/app/modules/operations/models.py:96-163`
- **Chave**: id (interno); chave de negócio composta (source, source_order_id) — unique constraint, source é sempre 'ixc' hoje
- **Campos-chave**:
  - `order_code`: string, formato 'IXC-{id}', identificador legível
  - `regional`: string, normalizada via normalize_regional() — GRANULAR (uma linha por filial real do IXC), NÃO a versão agrupada usada pela Gamificação
  - `company_id`: string|null, id_empresa bruto do IXC, sem tabela Company associada, uso downstream não confirmado
  - `os_type`: string, tipo geral da O.S.
  - `os_subject`: string, assunto específico
  - `ticket_id`: string|null, referencia lógica (não FK de banco) a SupportIxcTicket.source_id — o atendimento IXC que originou a O.S.
  - `opened_at`: timestamptz, não nulo
  - `closed_at`: timestamptz, nulo enquanto aberta
  - `sla_status`: enum('unidentified','on_time','out_of_time'), calculado na importação contra meta_horas_abertura do assunto — 'unidentified' quando o assunto não tem meta cadastrada
  - `elapsed_hours`: float, calculado como max(0, (closed_at ou now) - opened_at) em horas, recongelado a cada reimportação
  - `raw_payload`: json, payload bruto do IXC preservado — classificar como sensível, nunca expor em bloco (ver acesso.md)
- **Nulos**: sla_status='unidentified' significa 'sem meta cadastrada para o assunto', não 'dentro do prazo'; closed_at nulo = O.S. ainda aberta
- **Histórico**: Snapshot upsert por (source, source_order_id) com first_imported_at/last_imported_at — não há tabela de versionamento linha a linha; a régua de SLA pode ser recalculada retroativamente em O.S. já fechadas se a meta do assunto mudar (ver metrics ds.operations SLA)
- **Consulta via API**: `GET /api/operations/orders`, `GET /api/operations/orders/{source_order_id}`, `GET /api/operations/overview`, `GET /api/operations/sla`
- **Cobertura**: encontrado=True · documentado=True · API=True · testado=parcial — cobertura via testes automatizados backend/tests/test_operations_module.py e correlatos, não 100% de campos · validado pela área=False

#### `ds.operations.login_current_status` — OperationLoginCurrentStatus

- **Tabela**: `operations_login_current_status`
- **Descrição**: Snapshot do estado ATUAL de conexão de cada login (1 linha por login_id, sempre upsertada). Complementa o histórico append-only.
- **Evidência**: `backend/app/modules/operations/models.py:388-422`
- **Chave**: login_id
- **Campos-chave**:
  - `online`: string ('S'/'N'/'SS'/vazio) — NÃO normalizado para boolean de propósito; 'SS' é status relevante para detecção de instabilidade
  - `status_changed_at`: timestamptz, só avança quando 'online' muda de valor de fato
  - `regional`: string, normalização GRANULAR (mesma de operations_orders)
- **Histórico**: Não é histórico — é o estado corrente; histórico append-only fica em ds.operations.login_status_snapshot com retenção de 14 dias (configurável, 3-180 dias) após incidente de disco em 2026-09-17
- **Consulta via API**: `GET /api/operations/network/logins`, `GET /api/operations/network/login-detail`
- **Cobertura**: encontrado=True · documentado=True · API=True · testado=False · validado pela área=False

#### `ds.operations.login_status_snapshot` — OperationLoginStatusSnapshot

- **Tabela**: `operations_login_status_snapshots`
- **Descrição**: Histórico append-only de status de conexão, capturado várias vezes ao dia. Retenção limitada (política de purga — ver history).
- **Evidência**: `backend/app/modules/operations/models.py:342-385`
- **Chave**: id (auto-incremento), sem unique composta de negócio confirmada
- **Histórico**: ATENÇÃO PARA O CUBO: retenção padrão de 14 dias (mín 3, máx 180, configurável via AppSetting), rotina de purga automática (login_status_snapshot.py:222-245) desde incidente real em que a tabela chegou a 66GB/87% do disco e derrubou o Postgres em 2026-09-17. Um cubo que dependa de histórico de conexão de longo prazo precisa de extração periódica própria — o sistema não preserva isso indefinidamente.
- **Consulta via API**: `GET /api/operations/network/login-outages`, `GET /api/operations/network/login-timeseries`
- **Cobertura**: encontrado=True · documentado=True · API=True · testado=False · validado pela área=False

#### `ds.operations.onu_signal_current` — OperationOnuSignalCurrent / OperationOnuSignalSnapshot

- **Tabela**: `operations_onu_signal_current / operations_onu_signal_snapshots`
- **Descrição**: Sinal óptico (ONU) atual e histórico PARCIAL (só cobre a fila de diagnóstico de cada ciclo — offline/transição recente/nunca capturado — não todo login monitorado a cada ciclo).
- **Evidência**: `backend/app/modules/operations/models.py:425-506`
- **Chave**: login_id (current) / id auto-incremento (snapshot)
- **Histórico**: Fonte no IXC (radpop_radio_cliente_fibra) não é documentada publicamente pelo IXC — descoberta por sondagem manual (comentário no código). Cobertura do histórico é parcial por desenho, não é falha.
- **Consulta via API**: `GET /api/operations/network/onu-signal`, `GET /api/operations/network/onu-signal/history`
- **Cobertura**: encontrado=True · documentado=True · API=True · testado=False · validado pela área=False

#### `ds.operations.backlog_snapshot` — OperationBacklogSnapshot

- **Tabela**: `operations_backlog_snapshots`
- **Descrição**: 1 fotografia diária (1x/dia) do backlog por (data, regional, modelo de equipe, setor, cidade).
- **Evidência**: `backend/app/modules/operations/models.py:306-339`
- **Chave**: unique(snapshot_date, regional, team_model, sector, city)
- **Histórico**: Não existe histórico anterior à criação desta tabela — o sistema não tinha snapshot/log de mudança de status de O.S. antes dela.
- **Consulta via API**: `GET /api/operations/overview/backlog-trend`
- **Cobertura**: encontrado=True · documentado=True · API=True · testado=False · validado pela área=False

#### `ds.operations.customer_contract` — OperationCustomerContract

- **Tabela**: `operations_customer_contracts`
- **Descrição**: 1 registro = 1 contrato de cliente (tabela IXC cliente_contrato), NÃO 1 cliente.
- **Evidência**: `backend/app/modules/operations/models.py:509-541`
- **Chave**: source_contract_id (unique)
- **Campos-chave**:
  - `status`: string, código CRU do IXC (ex.: 'P','AA') — NÃO inferir 'ativo' sem validar com a área; comentário no código adverte explicitamente contra essa inferência
- **Consulta via API**: `usado internamente por warranty_analytics, sem endpoint de listagem direta confirmado nesta análise`
- **Cobertura**: encontrado=True · documentado=True · API=parcial — não confirmado endpoint de listagem própria · testado=False · validado pela área=False

#### `ds.operations.branch_capacity` — OperationBranchCapacity

- **Tabela**: `operations_branch_capacity`
- **Descrição**: 1 registro = 1 filial (regional único), com 3 faixas de capacidade mensal configuráveis (indicador gerencial, independente das metas por modelo de equipe).
- **Evidência**: `backend/app/modules/operations/models.py:544-569`
- **Chave**: regional (unique)
- **Consulta via API**: `GET /api/operations/branch-capacity`, `GET /api/operations/capacity-summary`
- **Cobertura**: encontrado=True · documentado=True · API=True · testado=False · validado pela área=False

#### `ds.operations.team_target_version` — OperationTeamTargetVersion

- **Tabela**: `operations_team_target_versions`
- **Descrição**: Histórico append-only das metas de OperationTeamTargetRule (que é destrutiva/recriada a cada edição) — responde 'qual era a meta vigente numa data passada'.
- **Evidência**: `backend/app/modules/operations/models.py:225-254`
- **Histórico**: Sem retroatividade anterior à entrada em produção do recurso; guarda o NOME do modelo de equipe como snapshot, não FK resolvida em runtime.
- **Consulta via API**: `GET /api/operations/team-configuration`
- **Cobertura**: encontrado=True · documentado=True · API=True · testado=False · validado pela área=False

### SGP Suporte

#### `ds.support.opa_attendance` — SupportOpaAttendance

- **Tabela**: `support_opa_attendances`
- **Descrição**: 1 registro = 1 atendimento OPA Suite (chat/bot/humano) já normalizado. Sem geografia — atendimento por chat, não localizado.
- **Evidência**: `backend/app/modules/support/models.py:351-432`
- **Chave**: source_id (unique)
- **Campos-chave**:
  - `tma_seconds`: float|null, tempo médio de atendimento — preferencialmente do payload OPA; calculado como closed_at-opened_at se ausente no payload
  - `tmr_seconds`: float|null, TMR só de respostas HUMANAS (exclui bot)
  - `tmr_all_responses_seconds`: float|null, TMR de qualquer resposta (bot+humano) — cobertura histórica parcial: 0% antes de 2026-08-20, 76-86% depois
  - `handled_by_bot / reached_human / bot_to_human_handoff`: boolean|null — NULL significa 'não classificado', nunca tratar como False (aviso explícito no código)
- **Nulos**: tma_seconds/tmr_seconds nulos quando não há closed_at ou não há gap válido — ausência de medição, não zero
- **Relações**: attendant_id/department_id/reason_id/customer_id casam por CONVENÇÃO (string) com SupportOpaDimension.source_id, NÃO são FK de banco
- **Consulta via API**: `GET /api/support/opa/attendances`, `GET /api/support/opa/overview`, `GET /api/support/opa-metrics`
- **Cobertura**: encontrado=True · documentado=True · API=True · testado=parcial · validado pela área=inconclusivo — ver docs/roteiro-comparacao-tmr-opa-suite.md, comparação com painel oficial OPA terminou classificada como Inconclusivo

#### `ds.support.ixc_ticket` — SupportIxcTicket

- **Tabela**: `support_ixc_tickets`
- **Descrição**: 1 registro = 1 atendimento REAL do IXC (su_ticket) — protocolo aberto na aba Atendimentos do IXC, que precede a abertura de O.S. Indicador antecipado de incidente de rede.
- **Evidência**: `backend/app/modules/support/models.py:194-267`
- **Chave**: source_id (unique)
- **Campos-chave**:
  - `regional`: string, derivada de id_filial via normalize_regional() (granular, mesma função de operations_orders)
  - `city / neighborhood / locality_type`: vêm do cadastro do CLIENTE, não do ticket
- **Relações**: OperationOrder.ticket_id == SupportIxcTicket.source_id — vínculo lógico confirmado por comentário de código, NÃO FK de banco. Entidade COMPLETAMENTE SEPARADA de SupportOpaAttendance (sem FK cruzada, fontes diferentes — IXC vs. API do OPA Suite).
- **Consulta via API**: `GET /api/support/ixc/tickets`, `GET /api/support/ixc/tickets/overview`, `GET /api/support/ixc/analytics/context`
- **Cobertura**: encontrado=True · documentado=True · API=True · testado=parcial · validado pela área=False

### Agendamento

#### `ds.scheduling.order` — SchedulingOrder

- **Tabela**: `scheduling_orders`
- **Descrição**: 1 registro = 1 O.S. dos setores sincronizados de agendamento.
- **Evidência**: `backend/app/modules/scheduling/models.py:36-59`
- **Chave**: ixc_os_id (unique)
- **Campos-chave**:
  - `filial_id`: string, campo mais próximo de 'regional/unidade' nesta tabela
  - `setor_id / setor_name`: setor operacional, não geografia
- **Consulta via API**: `GET /api/scheduling/orders`, `GET /api/scheduling/dashboard`
- **Cobertura**: encontrado=True · documentado=True · API=True · testado=parcial · validado pela área=False

#### `ds.scheduling.event` — SchedulingEvent

- **Tabela**: `scheduling_events`
- **Descrição**: 1 registro = 1 evento do log do IXC (su_oss_chamado_mensagem) — Abertura/Agendamento/Reagendar/Fechamento e outros.
- **Evidência**: `backend/app/modules/scheduling/models.py:62-83`
- **Chave**: ixc_message_id (unique)
- **Campos-chave**:
  - `event_at`: timestamptz, instante em que o operador interagiu — NÃO confundir com window_start/window_end (janela combinada com o cliente)
- **Consulta via API**: `GET /api/scheduling/operators/{id}/events`, `GET /api/scheduling/technicians/{id}/events`, `GET /api/scheduling/orders/{id}/timeline`
- **Cobertura**: encontrado=True · documentado=True · API=True · testado=parcial · validado pela área=False

### Gamificação Operacional

#### `ds.gamification.service_order` — ServiceOrder

- **Tabela**: `service_orders`
- **Descrição**: 1 registro = 1 O.S. executada, usada no cálculo de pontuação/pagamento da Gamificação. Vem de um pipeline de importação PRÓPRIO (IXC ou planilha UpValue), DISTINTO do pipeline que alimenta operations_orders.
- **Evidência**: `backend/app/models.py:427-454`
- **Chave**: os_code (unique)
- **Campos-chave**:
  - `collaborator_id`: FK NOT NULL para collaborators.id — toda O.S. pertence a um colaborador executante
  - `opened_at / closed_at`: timestamptz; mês de referência decidido no fuso America/Porto_Velho, não UTC
  - `diagnosis`: string, default 'Não informado' (valor de texto, não NULL)
- **Relações**: RELAÇÃO COM ds.operations.orders NÃO CONFIRMADA — são pipelines de importação separados (services/ixc_importer.py vs modules/operations/ixc_ingestion.py); NÃO presumir que a mesma O.S. do IXC aparece com o mesmo identificador nos dois datasets sem validação direta.
- **Consulta via API**: `GET /api/service-orders`, `GET /api/service-orders/period-summary`, `GET /api/service-orders/subject-summary`
- **Cobertura**: encontrado=True · documentado=True · API=True · testado=True · validado pela área=False

#### `ds.gamification.collaborator` — Collaborator

- **Tabela**: `collaborators`
- **Descrição**: 1 registro = 1 pessoa (técnico/executante), cadastrada ou apenas detectada via O.S. importada. Cadastro compartilhado com Gestão Integrada e Administração.
- **Evidência**: `backend/app/models.py:32-69`
- **Chave**: id; ixc_employee_id (unique) vincula com o IXC
- **Campos-chave**:
  - `is_registered`: boolean, default true — decide se a pessoa RECEBE PAGAMENTO de fato; false = aparece nas O.S. mas nunca gera valor a pagar
  - `active`: boolean, controla exclusão lógica (soft delete)
  - `cpf`: PII SENSÍVEL — ver acesso.md, sempre mascarado nas respostas de API existentes
  - `phone / email`: PII — não expostos pelas rotas de leitura hoje identificadas
  - `photo / photo_content_type`: binário, fora do escopo de um cubo analítico
- **Consulta via API**: `GET /api/collaborators/registry`, `GET /api/collaborators/{id}/service-orders-detail`, `GET /api/collaborators/{id}/monthly-history`
- **Cobertura**: encontrado=True · documentado=True · API=True · testado=True · validado pela área=False

#### `ds.gamification.calculation_run` — CalculationRun

- **Tabela**: `calculation_runs`
- **Descrição**: 1 registro = 1 fechamento/apuração de um período (mês/ano) e escopo (regional específico ou global).
- **Evidência**: `backend/app/models.py:587-615`
- **Chave**: id; sem unique(reference_month,reference_year,regional) no banco — múltiplos rascunhos do mesmo período coexistem, o run 'oficial' é resolvido em código (latest_run/pick_run_by_status_priority)
- **Campos-chave**:
  - `status`: enum(draft,review,approved,paid,cancelled)
  - `result_summary`: json — CACHE do dashboard, NÃO é mais a fonte de verdade para valores financeiros (achado de auditoria real de divergência de R$80,50 num fechamento)
  - `config_snapshot`: json — congela a régua de pontuação vigente no momento do cálculo
- **Consulta via API**: `GET /api/calculation-runs`, `GET /api/calculation-runs/{id}`, `GET /api/calculation-runs/latest`, `GET /api/calculation-runs/{id}/snapshot`
- **Cobertura**: encontrado=True · documentado=True · API=True · testado=True · validado pela área=False

#### `ds.gamification.collaborator_score` — CollaboratorScore

- **Tabela**: `collaborator_scores`
- **Descrição**: 1 registro = pontuação e valor a pagar de UM colaborador dentro de UM CalculationRun. FONTE DE VERDADE FINANCEIRA (não usar result_summary do run).
- **Evidência**: `backend/app/models.py:618-636`
- **Chave**: id; padrão de uso é 1 linha por (calculation_run_id, collaborator_id), sem UniqueConstraint declarada no schema
- **Campos-chave**:
  - `gross_points / penalty_points / net_points`: bruto, penalidades, líquido = bruto - penalidade
  - `health_multiplier`: multiplicador de saúde regional aplicado
  - `final_points`: = net_points * health_multiplier, ajustado por saldo de garantia
  - `estimated_payment`: = final_points * point_value, ajustado por saldo de garantia
- **Consulta via API**: `GET /api/calculation-runs/{id} (inclui breakdown)`, `GET /api/dashboard/summary`
- **Cobertura**: encontrado=True · documentado=True · API=True · testado=True · validado pela área=False

#### `ds.gamification.collaborator_point_balance` — CollaboratorPointBalance / PointBalanceEntry

- **Tabela**: `collaborator_point_balances / point_balance_entries`
- **Descrição**: Saldo de garantia (ver spec-saldo-pontos-garantia-pos-pagamento.md). CollaboratorPointBalance é 1 linha por colaborador (cache do saldo corrente, PODE FICAR DESATUALIZADO — usar sempre o ledger). PointBalanceEntry é o ledger append-only (fonte de verdade).
- **Evidência**: `backend/app/models.py:639-707`
- **Chave**: CollaboratorPointBalance: collaborator_id (unique). PointBalanceEntry: id, sem unique de negócio.
- **Campos-chave**:
  - `entry_type`: enum(post_payment_warranty_debit, period_settlement, manual_adjustment)
  - `status`: enum(pending, applied, reverted) — nunca deletado, só muda de status
  - `points`: negativo=débito, positivo=crédito/estorno
  - `target_reference_month/year`: só preenchido em post_payment_warranty_debit — mês/ano do RETORNO (garantia), não da O.S. original
- **Nulos**: CollaboratorPointBalance.balance_points é CACHE, não fonte de verdade — pode divergir se um lançamento pendente for estornado depois; leitura correta soma PointBalanceEntry ao vivo (current_balance())
- **Consulta via API**: `GET /api/collaborators/{id}/point-balance`, `GET /api/point-balance/pending`
- **Cobertura**: encontrado=True · documentado=True · API=True · testado=True · validado pela área=False

#### `ds.gamification.import_run` — ImportRun / ImportServiceOrderAudit

- **Tabela**: `imports / import_service_order_audits`
- **Descrição**: Rastreabilidade de importação da Gamificação (IXC ou planilha UpValue), com trilha linha-a-linha por O.S.
- **Evidência**: `backend/app/models.py:792-849`
- **Consulta via API**: `GET /api/imports/runs`, `GET /api/imports/runs/{id}/audits`, `GET /api/imports/runs/{id}/errors`
- **Cobertura**: encontrado=True · documentado=True · API=True · testado=True · validado pela área=False

### Gestão Integrada

#### `ds.management.case` — ManagementCase

- **Tabela**: `management_cases`
- **Descrição**: 1 registro = 1 caso de gestão (cobrança formal de um desvio operacional, diário/mensal/manual).
- **Evidência**: `backend/app/modules/management/models.py:154-195`
- **Chave**: id; idempotência de criação garantida em código de aplicação (get_or_create_daily_case/get_or_create_monthly_case), não confirmada constraint de banco adicional
- **Campos-chave**:
  - `status`: pending -> justified|in_progress -> resolved|rejected
  - `reference_date / due_date`: Date
  - `status calculado 'overdue'`: nunca gravado — calculado na leitura a partir de due_date
- **Relações**: collaborator_id/supervisor_user_id/reason_id são FK reais para collaborators/users/management_case_reasons (SET NULL)
- **Consulta via API**: `GET /api/management/cases`, `GET /api/management/cases/{id}`, `GET /api/management/cases/justifications`
- **Cobertura**: encontrado=True · documentado=True · API=True · testado=parcial · validado pela área=False

#### `ds.management.operational_member` — ManagementOperationalMember

- **Tabela**: `management_operational_members`
- **Descrição**: 1 registro = a visão do módulo Gestão sobre um colaborador EM UMA REGIONAL (pode haver mais de 1 registro por pessoa).
- **Evidência**: `backend/app/modules/management/models.py:106-134`
- **Chave**: unique(responsible_name, regional)
- **Relações**: Casamento com OperationOrder/OperationResponsibleAssignment é por NOME NORMALIZADO + ixc_employee_id quando disponível — não FK de banco.
- **Consulta via API**: `GET /api/management/dashboard`
- **Cobertura**: encontrado=True · documentado=True · API=True · testado=parcial · validado pela área=False

### UNI Intelligence

#### `ds.intelligence.alert` — IntelligenceAlert / IntelligenceAlertEvent

- **Tabela**: `intelligence_alerts / intelligence_alert_events`
- **Descrição**: Alerta OU incidente operacional detectado por monitores heurísticos (mesma tabela, diferenciados por 'kind'). Timeline append-only em IntelligenceAlertEvent.
- **Evidência**: `backend/app/modules/intelligence/models.py:55-161`
- **Chave**: id; dedupe_key não é unique de banco — unicidade aplicada em código só entre alertas ATIVOS
- **Consulta via API**: `GET /api/intelligence/alerts`, `GET /api/intelligence/alerts/{id}`
- **Cobertura**: encontrado=True · documentado=True · API=True · testado=False · validado pela área=False

#### `ds.intelligence.monitor_run` — IntelligenceMonitorRun

- **Tabela**: `intelligence_monitor_runs`
- **Descrição**: 1 execução de 1 monitor heurístico (6 monitores registrados: collective_outage, sla_deterioration, operational_pressure, monitor_health, alert_rules, ixc_ticket_burst).
- **Evidência**: `backend/app/modules/intelligence/models.py:22-52; registry.py:73-152`
- **Consulta via API**: `GET /api/intelligence/monitors`, `GET /api/intelligence/monitor-runs`
- **Cobertura**: encontrado=True · documentado=True · API=True · testado=False · validado pela área=False

### Administração

#### `ds.admin.collaborator_pii` — Collaborator (campos PII) / User

- **Tabela**: `collaborators / users`
- **Descrição**: Dados pessoais e credenciais de acesso. INCLUÍDO NO CATÁLOGO POR OBRIGAÇÃO DE MAPEAMENTO, NÃO significa liberado para o cubo — ver acesso.md classificação de dados pessoais.
- **Evidência**: `backend/app/models.py:32-128`
- **Campos-chave**:
  - `password_hash`: SEGREDO — pbkdf2_sha256, nunca serializado por nenhuma rota, NUNCA deve ir para o cubo
  - `cpf`: PII sensível — só mascarado é servido hoje
  - `email / phone`: PII — não expostos pelas rotas de leitura administrativas identificadas nesta análise
- **Consulta via API**: `GET /api/admin/people-structure (CPF mascarado)`
- **Cobertura**: encontrado=True · documentado=True · API=parcial — só campos mascarados/não-sensíveis · testado=False · validado pela área=False

## Indicadores

### `m.operations.sla_rate` — Taxa de SLA (Operação Analítica)

- **Módulo**: operacao_analitica
- **Definição**: Percentual de O.S. concluídas dentro do prazo, entre as O.S. concluídas com SLA identificado.
- **Fórmula**: round((completed_on_time / measurable_count) * 100, 1); measurable_count = completed_on_time + completed_out_of_time (exclui sla_status='unidentified')
- **Tratamento de nulo/divisão por zero**: resultado é null (não 0) quando measurable_count=0
- **Dimensões permitidas**: regional (granular ou agrupada conforme endpoint), período (opened_at OR closed_at, união por padrão)
- **Serviço/evidência**: `backend/app/modules/operations/queries.py:606-696 (overview), 736-859 (regional_matrix)`
- **Status de validação de negócio**: não validado nesta análise — pendente de confirmação da área
- **Atenção**: 'unidentified' significa 'assunto sem meta de horas cadastrada', não 'dentro do prazo' — nunca tratar como sucesso

### `m.operations.warranty_rate` — Taxa de garantia (retorno em manutenção)

- **Módulo**: operacao_analitica
- **Definição**: Proporção de O.S. de manutenção que são 'garantia' de uma ativação/mudança de endereço/mudança de tecnologia fechada no mesmo contrato até N dias antes.
- **Fórmula**: numerador = contagem de manutenções cujo opened_at cai na janela [closed_at, closed_at+janela] de uma O.S. de origem elegível do mesmo contract_id (a mais recente, se houver mais de uma); denominador é escolhido entre 4 populações (closed_origins/active_origins/maintenance_total/activation_closed) via parâmetro
- **Serviço/evidência**: `backend/app/modules/operations/queries.py:1299-1418`
- **Status de validação de negócio**: não validado nesta análise
- **Atenção**: janela em dias não confirmada literalmente no código nesta análise (assumida como citada em docstring, não lida na constante) — validar valor exato antes de publicar para terceiros

### `m.support.tmr_human` — TMR humano (tempo médio de resposta)

- **Módulo**: sgp_suporte
- **Definição**: Média dos intervalos entre mensagem do cliente e a primeira resposta de um atendente HUMANO (exclui bot).
- **Fórmula**: média simples dos gaps individuais (segundos) por atendimento; sem gaps válidos => null
- **Serviço/evidência**: `backend/app/modules/support/opa_ingestion.py:354-392`
- **Status de validação de negócio**: INCONCLUSIVO — docs/roteiro-comparacao-tmr-opa-suite.md registra divergência de totais (981 local vs 828 OPA) na única execução registrada; não confirmar publicamente que bate com o painel oficial OPA Suite
- **Atenção**: não confundir com m.support.tmr_all — este exclui respostas de bot

### `m.support.tmr_all` — TMR geral (qualquer resposta)

- **Módulo**: sgp_suporte
- **Definição**: Mesmo cálculo do TMR humano, mas conta qualquer resposta (bot ou humano) como fechamento do intervalo pendente.
- **Serviço/evidência**: `backend/app/modules/support/opa_ingestion.py:399-433`
- **Status de validação de negócio**: inconclusivo, mesma ressalva de m.support.tmr_human
- **Atenção**: cobertura histórica parcial: 0% antes de 2026-08-20, 76-86% depois

### `m.support.tma` — TMA (tempo médio de atendimento)

- **Módulo**: sgp_suporte
- **Definição**: Duração do atendimento OPA, preferencialmente lida do payload, calculada como closed_at-opened_at se ausente.
- **Serviço/evidência**: `backend/app/modules/support/opa_ingestion.py:707, 150-154`
- **Status de validação de negócio**: não validado nesta análise

### `m.scheduling.ttfa_business` — TTFA útil (time-to-first-appointment)

- **Módulo**: agendamento
- **Definição**: Tempo entre abertura (evento 1) e primeiro agendamento (evento 5) de uma O.S., descontando fora do expediente configurável (padrão 07:30-20:00, todos os dias).
- **Agregação**: SEMPRE reportado como mediana + P90 + média juntos, nunca média sozinha (decisão documentada explicitamente no código — distribuição de cauda longa distorce a média)
- **Serviço/evidência**: `backend/app/modules/scheduling/metrics.py (módulo inteiro, ver docstring linhas 3-11)`
- **Status de validação de negócio**: documento de proposta (docs/estudo-kpis-agendamento.md) valida a semântica, não uma validação formal de negócio

### `m.scheduling.reschedule_rate` — Reagendamento — duas óticas distintas

- **Módulo**: agendamento
- **Definição**: Por TÉCNICO (quem foi reagendado, sinaliza instabilidade de campo) vs. por OPERADOR (quem clicou em reagendar, sinaliza ação do backoffice) — NÃO são a mesma métrica e não devem ser somadas.
- **Serviço/evidência**: `backend/app/modules/scheduling/metrics.py:272 (technician), 311 (operator)`
- **Status de validação de negócio**: não validado nesta análise

### `m.gamification.order_score` — Pontuação de uma O.S. individual (antes de agregação por colaborador)

- **Módulo**: gamificacao
- **Definição**: base_points da regra casada (ScoringSubjectRule por par exato os_type+os_subject normalizado, sem fallback por assunto isolado) menos penalidades de diagnóstico, SLA e reincidência/garantia aplicadas nesta ordem; nunca negativo.
- **Fórmula**: effective_rule_points(rule) = float(rule.custom_points) if (not rule.use_group_default and rule.custom_points is not None) else float(rule.group.default_points); net_points = round(max(base_points - penalty_points, 0), 2). base_points é zerado se: sem collaborator_id, O.S. não completa, sem regra casada, ou (is_warranty/is_recurrence e warranty_mode='no_points').
- **Tratamento de nulo/divisão por zero**: sem regra casada => status 'Sem regra', base_points=0 (não é erro, é o comportamento correto quando o assunto não está mapeado)
- **Serviço/evidência**: `backend/app/services/scoring_detail.py:183-211 (casamento e pontos base), 1012-1307 (explain_order, função central), 1310-1347 (explain_orders, recálculo ao vivo — sem cache)`
- **Status de validação de negócio**: não validado nesta análise
- **Atenção**: explain_orders/get_period_audit recalculam 100% ao vivo a partir de ServiceOrder + regras/settings VIGENTES no momento da chamada — não há congelamento histórico das regras dentro deste arquivo (o congelamento por fechamento fica em CalculationRun.config_snapshot, usado só no ledger de saldo de garantia, não nesta auditoria).

### `m.gamification.penalties` — Penalidades de diagnóstico, SLA e reincidência/garantia

- **Módulo**: gamificacao
- **Definição**: Três fontes independentes de penalidade, somadas em penalty_points, cada uma podendo ser suprimida se a O.S. já foi anulada por reincidência (recurrence_suppresses_point_penalties).
- **Fórmula**: Diagnóstico (scoring_detail.py:1097-1150): subtract_points => abs(penalty_points) se base_points>0; cancel_points => anula 100% (diagnosis_penalty_points=base_points); requires_review => só marca revisão, não altera pontos; force_points => SOBRESCREVE base_points (não é penalidade, é substituição da base). SLA (scoring_detail.py:1164-1198): subtract_points => abs(penalty_value); percentage_reduction => base_points*abs(penalty_value)/100; cancel_points => anula 100%. Reincidência/garantia (scoring_detail.py:658-811, pareamento por login/contrato dentro de search_window_days, classificação por RecurrenceClassificationRule ou heurística): recurrence_action='annul_original' (default) => anula 100% dos pontos brutos da regra da O.S. original; 'subtract_original' => pontos fixos configurados; 'no_penalty' => 0; 'requires_review' => 0 + marca revisão.
- **Serviço/evidência**: `backend/app/services/scoring_detail.py:658-811 (pareamento e classificação de reincidência), 1097-1219 (aplicação das 3 penalidades em explain_order)`
- **Status de validação de negócio**: não validado nesta análise
- **Atenção**: o pareamento de reincidência escolhe o par MAIS PRÓXIMO EM DIAS entre os candidatos que geram desconto (reincidencia_tecnica/garantia); se nenhum candidato gerar desconto, usa o mais próximo entre todos — isso pode anular pontos de uma O.S. que não é tecnicamente uma reincidência de garantia se a classificação heurística errar; não presumir que 'anulada por reincidência' sempre significa fraude/erro do colaborador sem checar a classificação

### `m.gamification.final_points_estimated_payment` — Pontuação final e pagamento estimado do colaborador

- **Módulo**: gamificacao
- **Definição**: net_points = gross_points - penalty_points; final_points = net_points * health_multiplier (ajustado por saldo de garantia); estimated_payment = final_points * point_value (ajustado por saldo de garantia). Colaborador com is_registered=false NUNCA gera estimated_payment > 0, mesmo com pontos.
- **Serviço/evidência**: `backend/app/services/calculation.py:158-439 (nível colaborador, agregando m.gamification.order_score e m.gamification.penalties por O.S. do período)`
- **Status de validação de negócio**: validado operacionalmente (é o valor efetivamente pago) mas com achado de auditoria histórico de divergência entre cache e linha — hoje CollaboratorScore é a fonte de verdade, não CalculationRun.result_summary
- **Atenção**: leitura de fechamento em rascunho (draft) é PRÉVIA — não é o valor final até status='paid'

### `m.gamification.leadership_bonus` — Bônus de liderança

- **Módulo**: gamificacao
- **Definição**: base_amount (média de final_points do escopo de liderança, só colaboradores com is_registered=true) * multiplier = bonus_amount, recalculado a partir do ranking já persistido de CalculationRun.scores (não recalcula do zero via scoring_detail.py).
- **Fórmula**: average_final_points = round(sum(final_points do escopo)/scoped_collaborators, 2) if scoped_collaborators else 0.0. Escopo: portfolio_manager => todos os registered_scores do run, sem filtro de regional; supervisor/regional_manager => só colaboradores cuja regional está nas regionais vinculadas ao perfil. Se average_source='collaborators_and_leaders' (setting por perfil), a média TAMBÉM inclui outros perfis de liderança (exceto ele mesmo) com interseção de escopo, cada um entrando como um score sintético com final_points=average_final_points do outro líder e health_multiplier=1.0 fixo. base_amount = round(average_final_points * point_value, 2); multiplier = custom_multiplier (se ativo) senão default do role_profile senão default hardcoded (supervisor=1.5, regional_manager=2.0, portfolio_manager=3.0); bonus_amount = round(base_amount * multiplier, 2).
- **Tratamento de nulo/divisão por zero**: escopo vazio (nenhum colaborador registrado na(s) regional(is) do perfil) => average_final_points=0.0, nunca ZeroDivisionError
- **Serviço/evidência**: `backend/app/services/leadership_bonus.py:101-106 (multiplier), 217-363 (fórmula principal), 456-505 (persistência em LeadershipBonusResult)`
- **Status de validação de negócio**: não validado nesta análise
- **Atenção**: frontend/app/gamificacao/page.tsx recalcula uma versão APROXIMADA desta métrica quando o backend não retorna auditoria persistida — o próprio código rotula esse valor como 'reconstituído para conferência rápida', não oficial. Além disso, a gravação em LeadershipBonusResult persiste só os 7 campos agregados (multiplier, average_final_points, scoped_collaborators, point_value, base_amount, bonus_amount, regionals_snapshot) — NÃO foi encontrada nenhuma coluna que persista a lista individual de colaboradores/líderes que entraram na média (audit.collaborators existe só na resposta em memória do cálculo, não confirmado como persistido). Um cubo de dados deve usar sempre o valor oficial da API no momento do fechamento, nunca reproduzir o recálculo aproximado de tela nem presumir que o detalhe por colaborador fica disponível para consulta posterior.

### `m.management.case_deviation` — Severidade de caso por percentual de desvio

- **Módulo**: gestao_integrada
- **Definição**: Desvio = quanto a produção real ficou abaixo do piso esperado (não do teto/meta), em percentual. Severidade classificada em 3 faixas por limiares configuráveis.
- **Fórmula**: deviation_pct = round(max(0.0, (expected - actual) / expected * 100), 1), onde expected = ManagementOperationalMember.team_model.median_from_quantity (o PISO da faixa 'boa' do modelo de equipe, deliberadamente não o teto) e actual = quantidade do dia (caso diário) ou total/dias_trabalhados do mês (caso mensal, dias corridos não contam). severity_for: deviation_pct >= high (default 35%) => 'high'; >= low (default 25%) => 'medium'; caso contrário => 'low'. Abertura automática de caso exige deviation_pct >= min_deviation_pct (default 15%) só em generate_performance_cases (geração em lote) — get_or_create_daily_case/monthly_case (criação sob demanda) NÃO aplicam esse corte mínimo.
- **Tratamento de nulo/divisão por zero**: n/a — expected nunca é 0 por construção (modelo de equipe sem median_from_quantity configurado simplesmente não gera caso, não é dividido por zero explicitamente tratado no trecho lido)
- **Serviço/evidência**: `backend/app/modules/management/cases.py:185-192 (severity_for), 305 e 440 e 492 e 564 (cálculo do desvio em 3 pontos do código), 62-74 (defaults de settings)`
- **Status de validação de negócio**: não validado nesta análise
- **Atenção**: usar o PISO da faixa boa como denominador (não a meta/teto) é uma decisão de produto documentada no próprio código — não presumir que 'desvio de X%' é sobre a meta ideal de produtividade, é sobre o mínimo aceitável

## Relacionamentos

| id | de | para | cardinalidade | tipo | confiança |
|---|---|---|---|---|---|
| `rel.operations_order__ixc_ticket` | ds.operations.orders.ticket_id | ds.support.ixc_ticket.source_id | N:1 (várias O.S. podem referenciar o mesmo ticket de origem) | lógica (valor), NÃO FK de banco | comprovada — citada explicitamente no código, não inferida por nome |
| `rel.point_balance_entry__service_order` | ds.gamification.collaborator_point_balance (PointBalanceEntry.original_service_order_id / related_service_order_id) | ds.gamification.service_order.id | N:1 | FK real de banco (nullable) | comprovada — FK declarada |
| `rel.collaborator__user` | ds.gamification.collaborator.id | ds.admin.collaborator_pii (User.collaborator_id) | 1:1 (opcional) | FK real de banco, unique | comprovada |
| `rel.management_member__collaborator` | ds.management.operational_member | ds.gamification.collaborator | N:1 | casamento por NOME NORMALIZADO + ixc_employee_id quando disponível; existe também FK opcional collaborator_id (SET NULL) | parcial — FK existe mas é opcional/nullable; casamento primário é textual |
| `rel.service_order__operation_order_NOT_CONFIRMED` | ds.gamification.service_order | ds.operations.orders | desconhecida | AMBIGUIDADE EXPLÍCITA — dois pipelines de importação separados (services/ixc_importer.py para Gamificação vs. modules/operations/ixc_ingestion.py para Operação Analítica) podem descrever a MESMA O.S. do IXC, mas não há evidência de código de uma FK ou chave compartilhada entre as duas tabelas | NÃO COMPROVADA — não presumir que os dois datasets podem ser cruzados por id_ixc sem validação direta com a área de dados |
| `rel.scheduling_order__operation_order_UNKNOWN` | ds.scheduling.order | ds.operations.orders | desconhecida | ambos representam O.S. do IXC (ixc_os_id vs source_order_id), possível mesma chave de negócio, NÃO VERIFICADO nesta análise | NÃO COMPROVADA — pendência de validação |

Detalhe de evidência de cada relacionamento:

- **`rel.operations_order__ixc_ticket`**: comentário em backend/app/modules/operations/models.py:109-113 e backend/app/modules/support/router.py:1896-1897
- **`rel.point_balance_entry__service_order`**: backend/app/models.py:670-671
- **`rel.collaborator__user`**: backend/app/models.py:86
- **`rel.management_member__collaborator`**: backend/app/modules/management/models.py:12-27,114
- **`rel.service_order__operation_order_NOT_CONFIRMED`**: docs/plano-integracao-ixc.md trata exclusivamente do pipeline da Gamificação e não menciona operations_orders; busca por referências cruzadas entre os dois modelos não encontrou FK nem uso compartilhado de id
- **`rel.scheduling_order__operation_order_UNKNOWN`**: nenhuma referência cruzada (FK ou uso compartilhado de id) encontrada entre backend/app/modules/scheduling/models.py e backend/app/modules/operations/models.py nesta análise

## Lacunas conhecidas (gaps)

### `gap.no_central_company_regional_table`

- **Descrição**: Não existe tabela central de Empresa/Regional/Unidade com FK. 'Regional' é texto normalizado via backend/app/services/regional.py, com DUAS normalizações divergentes: granular (Operação Analítica, Suporte) e agrupada (Gamificação). A mesma palavra 'regional' tem dois significados diferentes dependendo do módulo consumido.
- **Impacto**: cubo de dados corporativo precisa decidir explicitamente qual granularidade usar por indicador, e documentar a escolha — não pode assumir que 'regional' em duas tabelas é comparável sem checar qual normalização cada módulo aplica
- **Status**: pendente de decisão da área de dados

### `gap.no_secrets_manager`

- **Descrição**: Não há secrets manager integrado (Vault/AWS Secrets Manager/etc.) — segredos hoje são variáveis de ambiente simples (.env / Docker Compose). A regra do projeto (docs/manual_programacao_senior.md) exige secret manager 'quando houver', mas não há um configurado.
- **Impacto**: criação da credencial técnica read-only do cubo (seção 5 do pedido original) fica sem local seguro dedicado até esta lacuna ser resolvida — ver acesso.md
- **Status**: pendente de decisão de infraestrutura

### `gap.no_central_auth_middleware`

- **Descrição**: Não há middleware ASGI central de autenticação/autorização — proteção é 100% via dependency injection do FastAPI, declarada rota a rota ou por APIRouter. Uma rota nova fica pública por padrão se o desenvolvedor esquecer a dependency.
- **Impacto**: qualquer endpoint novo criado para o cubo precisa ser auditado individualmente quanto à presença da dependency de permissão — não há rede de segurança automática
- **Status**: achado técnico, não uma ação deste pacote

### `gap.mcp_connector_scope`

- **Descrição**: O conector MCP existente (opr_* tools) já é essencialmente uma identidade técnica read-only, mas cobre só Operação Analítica, Suporte, Agendamento, Gestão e Cockpit — NÃO cobre Gamificação, Administração nem UNI Localiza.
- **Impacto**: se o cubo precisar de Gamificação (pontuação/pagamento), a integração REST (openapi.yaml) é a via, não o MCP existente
- **Status**: achado técnico

### `gap.docs_exposed_outside_production`

- **Descrição**: /docs, /redoc e /openapi.json do FastAPI ficam habilitados sempre que APP_ENV != 'production' (backend/app/main.py:209-217) — usado nesta análise para extrair o openapi.yaml real. Se algum ambiente de homologação acessível publicamente estiver com APP_ENV diferente de 'production', a superfície completa da API (incluindo rotas de escrita) fica documentada sem exigir login para visualizar o contrato.
- **Impacto**: não é uma vulnerabilidade de dado (ainda exige autenticação para CHAMAR as rotas), mas é exposição de superfície de ataque — confirmar com a equipe de infraestrutura o APP_ENV de cada ambiente antes de considerar o pacote 'pronto' para qualquer ambiente que não seja desenvolvimento local
- **Status**: achado de segurança, fora do escopo de correção deste pacote

### `gap.login_status_history_retention`

- **Descrição**: Histórico de status de login (operations_login_status_snapshots) tem retenção padrão de 14 dias, com purga automática desde o incidente de disco de 2026-09-17.
- **Impacto**: um cubo que precise de histórico de conectividade de longo prazo precisa de extração periódica própria — o sistema operacional não é a fonte de verdade de longo prazo para esse dado
- **Status**: achado técnico, decisão de arquitetura deliberada do sistema operacional

### `gap.service_order_vs_operation_order`

- **Descrição**: Ver relationship rel.service_order__operation_order_NOT_CONFIRMED — dois datasets de O.S. que podem ou não representar as mesmas ordens de serviço, sem chave comprovada de cruzamento.
- **Impacto**: risco de dupla contagem se o cubo tentar somar métricas de Gamificação e Operação Analítica sobre 'O.S.' sem entender que são dois pipelines/possivelmente duas populações distintas
- **Status**: pendente de validação direta com a área de dados/engenharia

### `gap.management_case_race_condition`

- **Descrição**: ManagementCase não tem UniqueConstraint de banco sobre a chave lógica de negócio (case_type+responsible_name+regional+período) — só índices normais. A idempotência de get_or_create_daily_case/monthly_case e generate_performance_cases é garantida inteiramente em código Python (SELECT + checagem em memória), sem SELECT...FOR UPDATE nem lock explícito.
- **Impacto**: sob concorrência real (duas requisições/jobs simultâneos para o mesmo responsável/dia), existe uma janela teórica de corrida que pode gerar casos duplicados logicamente — um cubo que agregue 'quantidade de casos' por responsável/dia pode contar duplicidade real de dados, não erro de consulta, se esse cenário já tiver ocorrido em produção
- **Status**: achado técnico confirmado por leitura de código (backend/app/modules/management/cases.py, backend/app/modules/management/models.py:154-158) — não testado em runtime nesta análise, não se sabe se já ocorreu na prática

### `gap.period_orders_ambiguity`

- **Descrição**: Existem duas funções de filtro de período na Gamificação (scoring_detail.py): period_orders (filtro estrito, exige mês/ano exato calculado a partir de closed_at ou opened_at) e period_orders_for_aggregation (mesma janela SQL, mas SEM o filtro estrito de mês/ano em Python — mais permissiva). Não há comentário no código explicando por que as duas existem nem quando usar cada uma.
- **Impacto**: um cubo que replique 'contagem de O.S. do período' pode obter números diferentes dependendo de qual das duas lógicas usar como referência — não presumir que ambas retornam o mesmo conjunto
- **Status**: achado técnico, divergência de código não documentada — não investigada a fundo nesta análise (fora do escopo pedido)
