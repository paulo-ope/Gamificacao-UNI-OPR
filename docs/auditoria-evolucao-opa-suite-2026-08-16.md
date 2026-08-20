# Auditoria tecnica - evolucao OPA Suite

Data: 2026-08-16

Status: Fase 1 concluida. Este documento registra o diagnostico antes da evolucao estrutural do modulo SGP Suporte/OPA.

## Escopo

Evoluir a integracao OPA Suite de uma tela/importacao simples para uma central operacional e analitica, mantendo o dominio isolado em `support`.

Nao acoplar OPA ao modulo `operations`.

## Implementacao atual localizada

Backend:

- `backend/app/services/opa_client.py`
- `backend/app/services/opa_scheduler.py`
- `backend/app/modules/support/models.py`
- `backend/app/modules/support/opa_ingestion.py`
- `backend/app/modules/support/router.py`
- `backend/app/modules/support/schemas.py`
- `backend/alembic/versions/20260816_0060_support_opa_integration.py`
- `backend/alembic/versions/20260816_0062_support_opa_dimensions.py`
- `backend/tests/test_opa_client.py`
- `backend/tests/test_opa_ingestion.py`
- `backend/tests/test_opa_scheduler.py`

Frontend:

- `frontend/app/suporte/page.tsx`
- `frontend/lib/api.ts`
- `frontend/lib/types.ts`
- `frontend/lib/module-registry.ts`
- `frontend/components/workspace/notification-bell.tsx`
- `frontend/components/workspace/workspace-home.tsx`

Configuracao:

- `backend/app/core/config.py`
- `.env.example`
- `docker-compose.yml`
- `backend/app/main.py`

Permissoes:

- `support:read`
- `support:sync_opa`

## Rotas atuais

- `GET /api/support/opa-sync-settings`
- `PUT /api/support/opa-sync-settings`
- `GET /api/support/opa-sync-status`
- `POST /api/support/opa-imports`
- `GET /api/support/opa-metrics`

## Tabelas atuais

- `support_opa_import_runs`
- `support_opa_attendances_raw`
- `support_opa_attendances`
- `support_opa_dimensions`

## Endpoints OPA validados em ambiente real

Todos usam `GET` com corpo JSON no formato:

```json
{
  "filter": {},
  "options": {
    "limit": 100,
    "skip": 0
  }
}
```

Endpoints testados:

| Entidade | Endpoint | Status | Observacao |
| --- | --- | --- | --- |
| Atendimentos | `/api/v1/atendimento` | OK | Pagina por `limit` e `skip`; nao retornou `total` na amostra. |
| Detalhe do atendimento | `/api/v1/atendimento/{id}` | OK | Retorna dados expandidos de cliente, atendente e motivo. |
| Mensagens | `/api/v1/atendimento/mensagem` | Parcial | Retorna mensagens, mas filtros testados por atendimento/protocolo foram ignorados. |
| Periodos | `/api/v1/atendimento/periodo` | OK | Retorna configuracoes de periodo/expediente. |
| Usuarios | `/api/v1/usuario/` | OK | Retorna `_id`, `nome`, `status`, `tipo`. |
| Departamentos | `/api/v1/departamento/` | OK | Retorna `_id`, `nome`, status e configuracoes. |
| Motivos | `/api/v1/atendimento/motivo` | OK | Retorna `_id`, `motivo`, `departamentos`. |
| Etiquetas | `/api/v1/etiqueta/` | OK | Retorna `_id`, `nome`, `cor`. |

## Payload real de atendimento

Campos observados em `/api/v1/atendimento`:

- `_id`
- `id_cliente`
- `id_user`
- `id_atendente`
- `origem`
- `setor`
- `descricao`
- `status`
- `canal`
- `canal_id`
- `canal_cliente`
- `protocolo`
- `tags`
- `evaluations`
- `observacoes`
- `motivos`
- `date`
- `fim`

Campos ja utilizaveis com seguranca:

- identificador externo: `_id`
- protocolo: `protocolo`
- cliente: `id_cliente`
- usuario de origem: `id_user`
- atendente: `id_atendente`
- departamento/fila: `setor`
- canal: `canal`
- telefone/canal cliente: `canal_cliente`
- status: `status`
- abertura: `date`
- encerramento: `fim`
- motivos: `motivos[].idMotivo`
- tags: `tags[].id_tag`
- avaliacao: `evaluations[].likert.rating`, quando existir

## Payload real do detalhe

`/api/v1/atendimento/{id}` retorna o atendimento com alguns relacionamentos expandidos:

- `id_cliente` como objeto com `_id`, `nome`, `cpf_cnpj`, `status`
- `id_user` como objeto com `_id`, `nome`
- `id_atendente` como objeto com `_id`, `nome`
- `motivos[].idMotivo` como objeto com `_id`, `motivo`

Decisao recomendada:

- manter listagem paginada como fonte principal;
- usar detalhe por ID sob demanda para tela de drill-down e, se necessario, enriquecimento pontual;
- evitar chamar detalhe para todos os atendimentos em cargas grandes sem lote/fila/rate control.

## Diagnostico do limite de 1.000 registros

O limite atual nao veio da API na validacao feita. Ele esta no backend.

Em `backend/app/modules/support/opa_ingestion.py`, a importacao chama:

```python
client.iter_attendances(..., max_records=1000)
```

O cliente `OpaClient.iter_attendances` ja possui paginacao por `skip`, mas respeita `max_records`. Portanto, uma importacao manual por periodo e interrompida artificialmente ao chegar em 1.000 registros.

Problema:

- se o periodo tiver mais de 1.000 atendimentos, a importacao nunca percorre todas as paginas;
- repetir a importacao tende a buscar os mesmos primeiros registros porque `skip` comeca em 0 novamente;
- nao ha checkpoint persistido para retomar da pagina seguinte.

Correcao necessaria:

- remover o teto fixo de 1.000 da ingestao manual;
- criar controle por pagina/checkpoint;
- persistir `skip`, paginas processadas, registros processados e status da execucao;
- permitir retomar execucao interrompida.

## Idempotencia atual

Ja existe UPSERT logico por `source_id`.

Tabelas:

- `support_opa_attendances.source_id` possui unique constraint.
- `support_opa_attendances_raw.source_id` possui unique constraint.
- `support_opa_dimensions` possui unique por `dimension_type + source_id`.

Chave recomendada para padrao de mercado:

- `provider = "opa"`
- `entity = "attendance"`
- `external_id = atendimento._id`

No modelo atual, `source_id` equivale ao `external_id`. Para suportar multiplas entidades, a proxima estrutura deve explicitar provider/entidade ou criar tabelas raw por entidade.

## Sincronizacao atual

`opa_scheduler.py` executa reimportacao por janela de dias:

- le `support_opa_sync_enabled`;
- usa `support_opa_sync_interval_minutes`;
- usa `support_opa_sync_lookback_days`;
- registra `last_success_at`, `last_attempt_at`, `next_allowed_at`, `last_error`, `consecutive_failures`.

Limites:

- nao usa `updated_at`/watermark;
- nao possui checkpoint por pagina;
- nao separa execucao por entidade;
- se falhar no meio da importacao, a retomada volta do inicio do periodo;
- nao registra pagina inicial/final nem cursor final.

## Campos incrementais

Campos possiveis observados:

- atendimento possui `date` e `fim`;
- o normalizador procura `updated_at`, `updatedAt`, `ultima_atualizacao`, `data_atualizacao`, mas o payload real de listagem observado nao trouxe esses campos;
- mensagens possuem `data`;
- tags/motivos dentro do atendimento possuem `data`.

Conclusao:

- incremental por `updated_at` ainda nao esta confirmado para atendimento;
- a estrategia segura inicial deve combinar reimportacao por janela recente + checkpoint por pagina + idempotencia;
- se a API/documentacao confirmar filtro por atualizacao, migrar para watermark real com sobreposicao.

## Mensagens e TMR

`/api/v1/atendimento/mensagem` retornou payload com:

- `_id`
- `id_atend`
- `id_user`
- `mensagem`
- `data`
- `statusEnvio`
- `objeto`
- `chamada`

Limite encontrado:

- filtros testados por `id_atend`, `id_atendimento`, `atendimento` e `protocolo` retornaram registros antigos de 2021 e aparentaram ser ignorados.

Impacto:

- ainda nao da para calcular TMR/primeira resposta com seguranca usando mensagens;
- nao criar KPI de TMR definitivo antes de validar o filtro correto ou outra rota de mensagens por atendimento.

Proxima acao:

- validar na documentacao/Postman do OPA o contrato correto de filtro para mensagens;
- se nao houver filtro confiavel, tratar mensagens como entidade paginada propria por data e relacionar por `id_atend`.

## Indicadores confiaveis hoje

Com o payload atual, ja da para calcular:

- total de atendimentos recebidos;
- total encerrado;
- taxa de encerramento;
- TMA/ciclo de atendimento por `fim - date`;
- media de avaliacao quando `evaluations` existir;
- volume por atendente;
- volume por departamento/fila;
- volume por motivo quando `motivos` vier preenchido;
- volume por canal;
- volume por tag;
- volume por hora/dia da semana;
- evolucao diaria;
- comparacao com periodo anterior;
- drill-down ate atendimento individual;
- detalhe do atendimento via `/api/v1/atendimento/{id}`.

## Indicadores ainda nao confiaveis

Nao criar como definitivo antes de validar fonte:

- TMR/primeira resposta;
- tempo de espera na fila;
- abandono;
- taxa de abandono;
- SLA de espera/resposta;
- tempo logado do agente;
- tempo disponivel/ocupado/pausa;
- produtividade baseada em login;
- pos-atendimento/after-call work.

## Arquitetura alvo recomendada

### Ingestao

Criar um motor de sincronizacao por entidade:

- `OpaEntitySyncPlan`
- `OpaPageCheckpoint`
- `OpaSyncRunner`

Entidades iniciais:

- `attendance`
- `attendance_detail` sob demanda/lote controlado
- `user`
- `department`
- `reason`
- `tag`
- `period`
- `message` apenas apos validar filtro/paginacao segura

### Controle de sincronizacao

Evoluir `support_opa_import_runs` ou criar tabela generica:

`support_opa_sync_runs`

Campos recomendados:

- id
- provider
- entity
- status
- mode (`manual`, `scheduled`, `resume`)
- period_start
- period_end
- started_at
- finished_at
- initiated_by
- request_filter_json
- checkpoint_json
- last_skip
- next_skip
- page_limit
- pages_processed
- fetched_count
- created_count
- updated_count
- unchanged_count
- rejected_count
- error_count
- last_error
- duration_ms

### Dados raw

Criar raw extensivel por entidade:

`support_opa_raw_records`

Campos recomendados:

- id
- provider
- entity
- external_id
- payload_json
- payload_hash
- source_created_at
- source_updated_at
- first_seen_at
- last_seen_at
- sync_run_id

Unique:

- `(provider, entity, external_id)`

### Dados normalizados

Manter `support_opa_attendances`, mas evoluir campos:

- channel
- channel_id
- channel_customer
- user_id
- user_name
- tag_ids / tags_json ou tabela relacional `support_opa_attendance_tags`
- status normalizado
- opened_hour
- opened_weekday
- duration_seconds
- source_payload_hash

Criar relacoes analiticas se necessario:

- `support_opa_attendance_reasons`
- `support_opa_attendance_tags`

### Indices

Prioridade:

- `opened_at`
- `closed_at`
- `source_id`
- `attendant_id`
- `department_id`
- `reason_id`
- `status`
- `channel`
- compostos para dashboard:
  - `(opened_at, department_id)`
  - `(opened_at, attendant_id)`
  - `(opened_at, reason_id)`
  - `(opened_at, channel)`

## Backend analitico alvo

Endpoints recomendados:

- `GET /api/support/opa/overview`
- `GET /api/support/opa/timeseries`
- `GET /api/support/opa/breakdowns`
- `GET /api/support/opa/heatmap`
- `GET /api/support/opa/agents`
- `GET /api/support/opa/departments`
- `GET /api/support/opa/reasons`
- `GET /api/support/opa/attendances`
- `GET /api/support/opa/attendances/{id}`
- `GET /api/support/opa/filters`
- `GET /api/support/opa/sync-runs`
- `POST /api/support/opa/sync-runs`
- `POST /api/support/opa/sync-runs/{id}/resume`

Todos os endpoints de listagem devem ser server-side:

- paginacao;
- ordenacao;
- filtros;
- busca;
- selecao de colunas no frontend sem carregar toda a base.

## Frontend alvo

Reestruturar `frontend/app/suporte/page.tsx` em subcomponentes.

Navegacao interna sugerida:

- Visao Geral
- Operacao
- Atendimentos
- Filas
- Agentes
- Motivos
- Horarios
- Historico
- Dados
- Sincronizacao

Regra:

- mostrar apenas indicadores suportados por dados reais;
- TMR/SLA/abandono devem aparecer como indisponiveis ou experimentais enquanto a fonte nao estiver validada.

## Plano de implementacao recomendado

### Fase 2 - Ingestao

1. Remover teto fixo de 1.000 na importacao manual.
2. Criar sync runner com checkpoint por entidade/pagina.
3. Persistir execucao em `support_opa_sync_runs`.
4. Usar payload hash para detectar alteracao real.
5. Garantir resume de run interrompida.
6. Adicionar retry controlado por pagina.
7. Testar cenario com mais de 1.000 registros.

### Fase 3 - Banco

1. Criar `support_opa_raw_records`.
2. Evoluir `support_opa_attendances`.
3. Criar tabelas relacionais para tags/motivos se necessario.
4. Criar indices analiticos.

### Fase 4 - Backend analitico

1. Criar filtros globais.
2. Criar overview com comparacao temporal.
3. Criar breakdowns por agente/fila/motivo/canal.
4. Criar heatmap hora x dia.
5. Criar endpoint de tabela analitica server-side.
6. Criar endpoint de detalhe.

### Fase 5 - Frontend

1. Quebrar pagina em layout modular.
2. Criar filtros globais.
3. Criar abas internas.
4. Criar cards com comparacao temporal.
5. Criar tabelas e drill-down.
6. Criar tela de sincronizacao com historico de runs.

## Criterios de aceite da proxima fase

- importar periodo com mais de 1.000 registros sem intervencao manual;
- nao duplicar registros ao reexecutar;
- atualizar registro alterado;
- registrar paginas processadas;
- permitir retomar run interrompida;
- manter status claro da ultima sincronizacao;
- testes automatizados cobrindo paginacao, checkpoint, idempotencia e falha no meio da pagina.

---

## Estudo de capacidade analitica do OPA Suite

Atualizado em: 2026-08-16

Este complemento substitui suposicoes por evidencias do ambiente OPA configurado. Nao cria novos dashboards nem altera regras de negocio.

### Metodo e limites da evidencia

Fontes usadas:

- este documento e o codigo atual em `backend/app/services/opa_client.py` e `backend/app/modules/support`;
- sondas controladas na API real com `limit=1` e sem registrar dados pessoais;
- base local `support_opa_attendances` apos as importacoes existentes;
- nenhum arquivo Postman, Insomnia, OpenAPI ou Swagger foi encontrado no repositorio.

Convencoes desta secao:

- `[CONFIAVEL]`: fonte, relacionamento e formula estao comprovados para o conceito descrito;
- `[VALIDAR]`: existe campo ou rota, mas falta confirmar semantica, contrato ou cobertura;
- `[INDISPONIVEL]`: nao ha fonte utilizavel com os dados e contratos conhecidos.

Nao foi feita enumeracao cega de rotas. Endpoints sem contrato confirmado foram apenas consultados quando eram candidatos diretos das entidades solicitadas.

### Cobertura observada na base local

Consulta realizada em 2026-08-16:

| Medida | Resultado |
| --- | ---: |
| Atendimentos armazenados | 34.030 |
| Periodo coberto por abertura | 2026-08-01 04:02 UTC a 2026-08-16 22:32 UTC |
| Encerrados (`fim` presente) | 33.702 |
| Em aberto | 328 |
| Atendimentos com avaliacao | 4.025 |
| Atendimentos com tags | 18.228 |
| Atendimentos com motivo | 12.813 |
| Com identificador de cliente | 28.728 |
| Com nome de cliente armazenado | 3 |
| Atendentes distintos | 133 |
| Departamentos distintos | 33 |
| Motivos distintos | 23 |
| Clientes distintos por identificador | 17.287 |
| Canais distintos | 3 |

Status efetivamente observados:

| Codigo OPA | Total | Encerrados | Rotulo de interface atual |
| --- | ---: | ---: | --- |
| `F` | 33.702 | 33.702 | Finalizado |
| `EA` | 242 | 0 | Em atendimento |
| `AG` | 84 | 0 | Aguardando atendimento |
| `PS` | 2 | 0 | Pausado |

Os rotulos de `EA`, `AG` e `PS` ainda precisam de confirmacao funcional com o responsavel pelo OPA. A relacao de `F` com encerramento esta comprovada na amostra; os outros rotulos sao apresentacao de interface, nao nova regra de calculo.

### Inventario de endpoints

Todas as colecoes abaixo aceitaram o envelope JSON `{"filter": {}, "options": {"limit": 1, "skip": 0}}`. Em todas elas, a sonda de `skip=1` devolveu outro registro: paginacao por `limit` e `skip` foi comprovada. Nenhuma das respostas trouxe total confiavel no envelope.

| Entidade | Rota | Filtros confirmados | Paginacao | Campos observados | Relacionamentos e limitacoes |
| --- | --- | --- | --- | --- | --- |
| Atendimento | `GET /api/v1/atendimento` com corpo | `dataInicialAbertura` e `dataFinalAbertura` (data futura retornou vazio) | Sim, `limit`/`skip`; sem `total` | `_id`, `id_cliente`, `id_user`, `id_atendente`, `origem`, `setor`, `descricao`, `status`, `canal`, `canal_id`, `canal_cliente`, `protocolo`, `tags`, `evaluations`, `observacoes`, `motivos`, `date`, `fim` | Fonte principal. A listagem traz ID de cliente, nao necessariamente nome. |
| Detalhe de atendimento | `GET /api/v1/atendimento/{id}` | ID na rota | Nao aplicavel | Mesmo conjunto, com relacionamentos expandidos quando existentes | `id_cliente` pode trazer nome e documento; usar sob demanda ou com fila controlada. |
| Mensagem | `GET /api/v1/atendimento/mensagem` com corpo | Nenhum comprovado. `id_atend` e `protocolo` inexistentes foram ignorados e retornaram dados. | Sim, `limit`/`skip` | `_id`, `id_atend`, `id_rota`, `mensagem`, `data`, `statusEnvio`, `objeto`, `chamada`, `__v` | Relaciona por `id_atend`, mas sem filtro seguro o consumo integral e o vinculo analitico ainda nao sao seguros. |
| Periodo/expediente | `GET /api/v1/atendimento/periodo` com corpo | Desconhecidos | Sim, `limit`/`skip` | `_id`, `ativo`, `nome`, `periodos[]` | `periodos[]` contem dia da semana, feriado, `horaInicio`, `horaFim` e nome. Sem associacao comprovada a atendimento ou departamento. |
| Usuario | `GET /api/v1/usuario/` com corpo | Desconhecidos | Sim, `limit`/`skip` | `_id`, `nome`, `status`, `tipo` | Pode enriquecer `id_user` e `id_atendente`; esta parcialmente ingerido como dimensao. |
| Departamento | `GET /api/v1/departamento/` com corpo | Desconhecidos | Sim, `limit`/`skip` | `_id`, `nome`, `descricao`, `status`, `ordem`, `tipoEncaminhamentoLigacoes`, `recebeAtendimento`, `pesquisaSatisfacao`, `inatividade`, configuracoes de PABX e encaminhamento | Pode enriquecer fila/departamento e indicar se recebe atendimento. Campos de configuracao nao provam capacidade real. |
| Motivo | `GET /api/v1/atendimento/motivo` com corpo | Desconhecidos | Sim, `limit`/`skip` | `_id`, `motivo`, `departamentos` | Relaciona motivo a departamentos; dimensao ja ingerida. |
| Etiqueta | `GET /api/v1/etiqueta/` com corpo | Desconhecidos | Sim, `limit`/`skip` | `_id`, `nome`, `cor` | Tags tambem aparecem dentro do atendimento. Dimensao ja ingerida, mas relacao atendimento-tag esta somente no JSON bruto. |
| Cliente | `GET /api/v1/cliente/` com corpo | Desconhecidos | Sim, `limit`/`skip` | `_id`, `nome`, `fantasia`, `cpf_cnpj`, `status`, `fornecedor`, `id_fornecedor`, `country`, `latitude`, `longitude` | Rota real descoberta nesta auditoria. Ainda nao e ingerida. Resolve nomes de clientes sem consultar detalhe por atendimento. |
| Transferencia | `GET /api/v1/atendimento/transferencia` com corpo | Desconhecidos | Nao comprovada | Nao inspecionado | Retornou HTTP 400 para o contrato generico: a rota aparenta existir, mas exige contrato especifico. |
| Pausa | `GET /api/v1/atendimento/pausa` com corpo | Desconhecidos | Nao comprovada | Nao inspecionado | Retornou HTTP 400 para o contrato generico: a rota aparenta existir, mas exige contrato especifico. |
| Fila | `GET /api/v1/fila/` | Nao confirmado | Nao confirmado | Nao inspecionado | Redirecionou para login. Nao e endpoint de API autenticado com o contrato atual ou rota incorreta. |
| Sessao/login | `GET /api/v1/sessao/` | Nao confirmado | Nao confirmado | Nao inspecionado | Redirecionou para login. Sem fonte de jornada, disponibilidade ou pausa. |

Observacao de seguranca: o campo `token` retornado em departamento foi detectado apenas como nome de campo e nao deve ser exposto, persistido em telas ou usado como dado analitico.

### Mapa de campos e utilidade analitica

| Entidade | Campo | Significado observado | Tipo | Pode filtrar? | Pode agrupar? | Utilidade analitica |
| --- | --- | --- | --- | --- | --- | --- |
| Atendimento | `_id` | Identificador externo | texto | Sim, localmente | Sim | Chave de idempotencia e detalhe. |
| Atendimento | `protocolo` | Protocolo visivel | texto | Sim, localmente | Sim | Busca, auditoria e drill-down. |
| Atendimento | `id_cliente` | Identificador de cliente; detalhe pode expandir | texto ou objeto | Sim, localmente | Sim | Volume por cliente; nome depende de cliente/detalhe. |
| Atendimento | `id_user` | Usuario de origem; detalhe expande nome | texto ou objeto | Ainda nao | Sim, apos normalizacao | Analise de origem, nao confundir com atendente. |
| Atendimento | `id_atendente` | Atendente; detalhe expande nome | texto ou objeto | Sim, localmente | Sim | Volume, encerramento, ciclo e avaliacao por atendente. |
| Atendimento | `setor` | Setor/departamento/fila no payload | texto ou objeto conforme resposta | Sim, localmente | Sim | Volume, backlog e ciclo por departamento. |
| Atendimento | `origem` | Origem declarada | texto | Ainda nao | Sim, apos normalizacao | Possivel recorte de demanda; sem semantica documentada. |
| Atendimento | `status` | Codigo de estado | texto | Sim, localmente | Sim | Encerramento, em aberto e distribuicao. Rotulos precisam validacao. |
| Atendimento | `canal` | Canal principal | texto | Sim, localmente | Sim | Volume e qualidade por canal. |
| Atendimento | `canal_id` | Identificador do canal | texto | Ainda nao | Sim | Diferenciar subcanais se necessario. |
| Atendimento | `canal_cliente` | Contato/origem do cliente | texto | Busca local | Nao recomendado | Busca e vinculacao, contem dado pessoal. |
| Atendimento | `date` | Data/hora de abertura | data/hora | Sim, API e local | Sim | Periodo, hora, dia, semana e comparacao temporal. |
| Atendimento | `fim` | Data/hora de encerramento | data/hora ou nulo | Sim, localmente | Sim | Encerramento e duracao de ciclo. |
| Atendimento | `descricao` | Descricao textual | texto | Busca local potencial | Nao recomendado | Drill-down e classificacao futura. |
| Atendimento | `observacoes` | Observacoes textuais | texto | Busca local potencial | Nao recomendado | Drill-down e auditoria. |
| Atendimento | `motivos[]` | Um ou mais motivos | lista de objetos | Nao na API comprovada; local parcial | Sim | Demanda por motivo. Hoje o primeiro motivo e normalizado; todos ficam no raw. |
| Atendimento | `tags[]` | Tags do atendimento | lista de objetos | Nao na API comprovada; raw local | Sim | Segmentacao por etiqueta; requer tabela relacional para analise robusta. |
| Atendimento | `evaluations[]` | Avaliacoes; `likert.rating` observada | lista de objetos | Nao na API comprovada; local por nota | Sim | Media, distribuicao e ausencia de avaliacao. Escala precisa validacao. |
| Mensagem | `_id` | Identificador da mensagem | texto | Nao comprovado | Sim | Deduplicacao futura. |
| Mensagem | `id_atend` | Atendimento relacionado | texto | Filtro ignorado na sonda | Sim | Base potencial para interacoes e primeira resposta. |
| Mensagem | `id_rota` | Rota da mensagem | texto | Desconhecido | Sim | Possivel transferencia/roteamento; sem semantica validada. |
| Mensagem | `mensagem` | Conteudo da mensagem | texto | Nao recomendado | Nao recomendado | Auditoria; dado pessoal/conteudo. |
| Mensagem | `data` | Data/hora da mensagem | data/hora | Desconhecido | Sim | Sequencia e intervalo entre mensagens, se ingestao ficar segura. |
| Mensagem | `statusEnvio` | Estado de envio | texto | Desconhecido | Sim | Possivel classificacao de entrega; sem semantica validada. |
| Mensagem | `objeto`, `chamada` | Metadados de mensagem/chamada | objeto/booleano desconhecido | Desconhecido | Validar | Possivel identificacao de chamada, ainda sem contrato. |
| Cliente | `_id` | Identificador do cliente | texto | Desconhecido | Sim | Chave para enriquecer atendimentos. |
| Cliente | `nome`, `fantasia` | Nome civil e nome fantasia | texto | Desconhecido | Sim | Nome exibivel e volume por cliente. |
| Cliente | `cpf_cnpj` | Documento | texto | Nao recomendado | Nao recomendado | Somente auditoria sob controle de acesso. |
| Cliente | `status`, `fornecedor`, `id_fornecedor`, `country` | Cadastros auxiliares | texto/booleano | Desconhecido | Validar | Segmentacao futura, sem demanda atual comprovada. |
| Cliente | `latitude`, `longitude` | Localizacao | numero | Desconhecido | Validar | Dado sensivel; nao usar sem caso de uso e governanca. |
| Usuario | `_id`, `nome` | Identidade do usuario | texto | Desconhecido | Sim | Enriquecer origem e atendente. |
| Usuario | `status`, `tipo` | Cadastro/status do usuario | texto | Desconhecido | Validar | Nao prova login, disponibilidade ou jornada. |
| Departamento | `_id`, `nome`, `descricao`, `status`, `ordem` | Cadastro de departamento | texto | Desconhecido | Sim | Fila/departamento e ordenacao de exibicao. |
| Departamento | `recebeAtendimento`, `pesquisaSatisfacao`, `inatividade` | Configuracoes | booleano/texto | Desconhecido | Validar | Configuracao, nao evidencia de produtividade/capacidade. |
| Departamento | PABX, encaminhamento e transbordo | Configuracoes de telefone/roteamento | texto/booleano | Desconhecido | Validar | Podem explicar roteamento, mas nao medem transferencia real. |
| Motivo | `_id`, `motivo` | Cadastro de motivo | texto | Desconhecido | Sim | Classificacao de demanda. |
| Motivo | `departamentos` | Departamentos associados | lista | Desconhecido | Sim | Matriz motivo-departamento. |
| Etiqueta | `_id`, `nome`, `cor` | Cadastro da etiqueta | texto | Desconhecido | Sim | Segmentacao e apresentacao de tags. |
| Periodo | `_id`, `ativo`, `nome` | Configuracao de expediente | texto/booleano | Desconhecido | Validar | Janela de referencia potencial. |
| Periodo | `periodos[].segunda` a `domingo`, `feriado`, `horaInicio`, `horaFim` | Horarios configurados | booleano/hora | Desconhecido | Validar | Necessario relacionamento explicito antes de calcular SLA/horas uteis. |

### Relacionamentos comprovados e lacunas de armazenamento

| Relacionamento | Situacao no OPA | Situacao local | Impacto |
| --- | --- | --- | --- |
| Atendimento -> Atendente | `id_atendente`; detalhe expande | ID e nome normalizados | Pronto para analise. |
| Atendimento -> Departamento | `setor`; dimensao de departamento | ID/nome normalizados | Pronto para analise, mas confirmar se `setor` equivale sempre a fila final. |
| Atendimento -> Motivo | `motivos[]` | Primeiro motivo normalizado; lista completa no raw | Breakdown simples pronto; multipla classificacao exige relacao propria. |
| Atendimento -> Tag | `tags[]` | Somente raw; dimensao de tag existe | Nao ha tabela relacional para consultas analiticas eficientes. |
| Atendimento -> Cliente | `id_cliente`; detalhe e `/cliente/` fornecem nome | ID em 28.728 linhas, nome em 3 | Principal lacuna para exibicao e volume nomeado por cliente. |
| Atendimento -> Mensagem | `mensagem.id_atend` | Nao ingerido | TMR, interacoes, primeira resposta e chamadas nao sao calculaveis. |
| Atendimento -> Transferencia | Rota candidata retorna 400 | Nao ingerido | Nao calcular transferencias. |
| Atendimento/Agente -> Pausa/Sessao | Rotas nao documentadas/sem contrato | Nao ingerido | Nao calcular disponibilidade, pausa ou login. |
| Departamento -> Periodo | Ambos existem | Nao relacionado | Nao calcular horas uteis, SLA ou capacidade. |

### Indicadores e formulas

#### [CONFIAVEL] Podemos implementar agora

| Indicador | Definicao e formula | Fonte | Filtros/granularidade | Limites |
| --- | --- | --- | --- | --- |
| Atendimentos recebidos | `COUNT(atendimento)` por `date` de abertura | `date`, `_id` | Periodo, canal, status, atendente, departamento, motivo; hora/dia/semana | Mede aberturas no recorte, nao contatos abandonados. |
| Encerrados | `COUNT(fim IS NOT NULL)` | `fim` | Mesmos filtros | Tambem pode ser apresentado como `status=F` apos validar catalogo de status. |
| Em aberto/backlog no recorte | `COUNT(fim IS NULL)` na consulta | `fim`, `status` | Mesmos filtros; fotografia do momento da consulta | Nao reconstrui backlog historico sem snapshots. |
| Taxa de encerramento | `encerrados / atendimentos recebidos * 100` | `fim`, `_id` | Mesmos filtros e periodo | Divisao por zero deve retornar indisponivel. |
| Duracao de ciclo media | `AVG(fim - date)` apenas para encerrados | `date`, `fim` | Mesmos filtros; por dimensao/hora/dia | Chamar de ciclo/duracao, nao de TMA oficial sem definicao do OPA. |
| Duracao de ciclo mediana/percentis | `percentile_cont(0.5/0.9)` sobre `fim - date` | `date`, `fim` | Mesmos filtros e dimensoes | Estatisticamente confiavel; depende de suporte SQL no endpoint futuro. |
| Volume por hora, dia e dia da semana | `COUNT(*)` agrupado por partes de `date` | `date` | Todos os filtros globais | Horario deve usar fuso de negocio definido. |
| Volume/encerramento por canal, departamento, atendente e status | `COUNT(*)`, `COUNT(fim)` por dimensao | campos normalizados | Filtros globais | Status e setor precisam semantica de negocio confirmada para rotulos. |
| Volume por motivo | `COUNT(*)` por motivo normalizado | `reason_id`, `reason_name` | Filtros globais | Hoje representa o primeiro motivo quando ha mais de um. |
| Avaliacao media | `AVG(likert.rating)` quando existe | `evaluations[].likert.rating`, `rating` local | Periodo e dimensoes existentes | A escala e o significado (CSAT/NPS) ainda nao foram confirmados. |
| Distribuicao de avaliacoes | `COUNT(*)` por nota | `rating` | Periodo e dimensoes existentes | Deve exibir notas, sem batizar como NPS. |
| Sem avaliacao | `COUNT(*) - COUNT(rating)` | `rating` | Periodo e dimensoes existentes | Ausencia nao prova que a pesquisa foi oferecida. |
| Avaliacao por atendente/departamento/motivo/canal | `AVG(rating)` e `COUNT(rating)` por dimensao | `rating` e dimensoes | Filtros globais | Exigir tamanho minimo de amostra para comparacao justa. |
| Atendimentos e encerramentos por atendente | Contagens por `attendant_id` | `id_atendente`, `fim` | Periodo, canal, departamento, status | Nao equivale a produtividade por hora trabalhada. |
| Comparacao entre periodos | Aplicar a mesma formula em periodo atual e anterior equivalente | Campos de cada indicador | Todos os filtros globais | Base atual cobre apenas 16 dias; periodos anteriores podem ficar vazios. |

#### [VALIDAR] Ha fonte potencial, mas falta contrato, modelagem ou interpretacao

| Indicador/dado | Potencial fonte | O que falta | Classificacao da lacuna |
| --- | --- | --- | --- |
| Volume por tag | `tags[]` no atendimento | Criar relacao atendimento-tag ou consulta JSON indexada; definir se tag e atual ou historica | Campo armazenado somente no raw/relacionamento nao normalizado. |
| Volume por cliente nomeado | `id_cliente`, detalhe e `/api/v1/cliente/` | Ingerir clientes e relacionar por ID; definir nome vs fantasia e privacidade | Endpoint ainda nao integrado. |
| Reincidencia/retorno | Cliente + assunto/motivo + janela temporal | Regra de negocio para definir retorno e fonte de classificacao comparavel | Relacionamento e regra nao normalizados. |
| Quantidade de interacoes | Mensagens por `id_atend` | Contrato de filtro ou ingestao segura de mensagens por pagina/data | Filtro da API desconhecido/ignorado. |
| Primeira resposta/TMR | `mensagem.data`, remetente/status possivel | Identificar qual mensagem e primeira resposta humana e filtrar mensagens por atendimento/data | Endpoint existe, mas relacionamento e semantica insuficientes. |
| Tempo entre mensagens | Sequencia de `mensagem.data` | Ingestao paginada e classificacao de origem da mensagem | Endpoint nao integrado e contrato de filtros invalido. |
| Chamadas e chats | `mensagem.chamada`, `objeto`, `statusEnvio` | Semantica e filtro dos campos | Campo potencial sem documentacao. |
| Transferencias entre departamentos | `/api/v1/atendimento/transferencia`, `id_rota` | Contrato aceito pela rota e campos retornados | Endpoint candidato retorna 400. |
| Horarios criticos por expediente | `atendimento/periodo` e `date` | Vinculo entre periodo, departamento e atendimento; fuso e feriados | Relacionamento nao normalizado. |
| Capacidade configurada de fila | Configuracoes de departamento | Definir formula e validar se campos representam capacidade operacional | Campo existe, sem semantica de capacidade. |
| CSAT | `likert.rating` | Confirmar escala, pergunta e criterio de inclusao | Semantica da avaliacao nao documentada. |
| Crescimento de motivo/canal | Series por `date` e dimensoes | Aumentar janela historica e definir comparacao/minimo de base | Dados atuais cobrem 16 dias. |
| Produtividade por hora do calendario | Encerramentos agrupados por hora | Nomear como producao por faixa horaria, nao por hora trabalhada | Formula possivel, conceito deve ser rotulado corretamente. |

#### [INDISPONIVEL] A API atual nao permite calcular corretamente

| Indicador | Motivo | O que seria necessario |
| --- | --- | --- |
| TMA oficial | `fim - date` mede ciclo total, nao ha definicao/campo de tempo medio de atendimento ativo | Campo definido pelo OPA ou regra de negocio formal. |
| Tempo de espera/fila | Nao ha timestamp comprovado de entrada na fila nem de aceite pelo agente | Eventos de fila/roteamento com timestamps. |
| SLA de espera/resposta | Falta inicio, meta vinculada e evento de resposta/atendimento | Contrato de SLA + eventos de mensagem/fila. |
| Abandono e taxa de abandono | Nao ha entidade ou status comprovado para contatos que desistiram antes do atendimento | Eventos de abandono/nivel de fila. |
| Tempo logado, disponivel, ocupado | Usuario traz cadastro/status, nao sessoes ou presencia | Endpoint autenticado de sessoes/estados com timestamps. |
| Tempo em pausa | Rota candidata retorna 400 e nao ha contrato | Endpoint de pausa documentado e ingestao. |
| Pos-atendimento/after-call work | Nenhum evento ou timestamp observado | Evento de encerramento de pos-atendimento. |
| Produtividade por hora trabalhada | Falta denominador de horas logadas/disponiveis | Sessoes, jornada ou presenca. |
| Taxa de ocupacao | Falta tempo ocupado e tempo disponivel | Eventos de estado de agente. |

### Dados do OPA ainda nao ingeridos

| Dado | Situacao | Beneficio futuro | Prioridade |
| --- | --- | --- | --- |
| Clientes (`/api/v1/cliente/`) | Endpoint real, nao integrado | Nome/fantasia de cliente, filtro e volume nomeado | Alta |
| Todos os motivos por atendimento | Apenas primeiro normalizado; lista no raw | Classificacao multipla correta | Alta |
| Relacao atendimento-tag | Apenas raw; dimensao de tag ja existe | Volume e qualidade por tag | Alta |
| Usuario de origem (`id_user`) | Presente no raw, nao normalizado na tabela | Separar origem de responsavel | Media |
| Detalhe expandido de atendimento | Sob demanda e cache pontual | Completar cliente, usuario e atendente para registros consultados | Media |
| Mensagens | Endpoint real, nao integrado | Interacoes e tempos, apos contrato seguro | Media, bloqueada por validacao |
| Periodos/expediente | Endpoint real, nao integrado | Horarios configurados, apos vinculo a departamento | Baixa, bloqueada por validacao |
| Transferencias | Endpoint candidato sem contrato | Fluxo entre filas/departamentos | Bloqueada |
| Pausas/sessoes | Endpoint nao confirmado | Jornada, disponibilidade e ocupacao | Bloqueada |

### Recomendacao para composicao do modulo

Prioridade recomendada para a proxima fase analitica:

1. Implementar breakdowns confiaveis de volume, encerramento, ciclo e avaliacao por canal, departamento, atendente, motivo e status.
2. Criar series por dia/hora/dia da semana e comparacao entre periodos, usando `date` e `fim` como fontes explicitas.
3. Integrar `/api/v1/cliente/` com paginacao e cache local para resolver `customer_id -> nome/fantasia`; nao chamar detalhe para toda a tabela.
4. Modelar relacoes `attendance_tags` e `attendance_reasons` antes de publicar rankings por tag ou motivo multiplo.
5. Validar com o dono do OPA o dicionario de status e a escala/pergunta de `evaluations[].likert.rating`.
6. Solicitar ou localizar contrato formal das rotas de mensagem, transferencia, pausa e sessao antes de propor TMR, SLA, abandono, login ou ocupacao.

Os breakdowns incluem comparacao com o periodo anterior de mesma duracao, reutilizando `OpaAttendanceFilters.previous_period()`. A primeira versao mantem a ordenacao pelas metricas do periodo atual; ordenar por variacoes fica para a proxima etapa, pois exige compor as duas agregacoes em uma unica consulta ordenavel sem ampliar o contrato prematuramente.

Conclusao: o OPA ja sustenta uma analitica solida de demanda, encerramento, ciclo e avaliacao. Ele ainda nao sustenta indicadores de fila, SLA, abandono ou jornada de agentes sem novos contratos e novas entidades ingeridas.
