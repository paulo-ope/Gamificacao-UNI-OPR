# Plano — Módulo de Análise de Atendimentos (SGP / OPA Suite)

Documento de diagnóstico e planejamento da Fase 1, antes de qualquer alteração de
código. Ver [docs/00-TRILHA-0.md](00-TRILHA-0.md) para o contexto geral do módulo
Suporte e [docs/STATUS.md](STATUS.md) para o estado corrente do projeto.

## 1. Diagnóstico do que o sistema atual já possui

### Backend (`backend/app/modules/support/`)

Endpoints existentes (todos atrás de `support:read`; os de sincronização também
exigem `support:sync_opa`):

| Rota | Método | Função |
|---|---|---|
| `/support/opa/attendances` | GET | Lista paginada com filtros (período, status, canal, atendente, departamento, motivo, protocolo, cliente, busca livre) |
| `/support/opa/overview` | GET | KPIs do período com comparação vs período anterior (total, encerrados, abertos, taxa de encerramento, duração média, avaliação média, atendentes/departamentos distintos, por canal) |
| `/support/opa/breakdowns` | GET | Agrupamento por atendente/departamento/motivo/canal/status/cliente, com deltas vs período anterior |
| `/support/opa/attendances/{id}` | GET | Detalhe local + enriquecido ao vivo pela API do OPA Suite |
| `/support/opa/filters` | GET | Opções de filtro (atendentes, departamentos, canais, status, motivos) |
| `/support/opa-metrics` | GET | Métricas legadas por atendente/motivo, incluindo TMA e TMR agregados |
| `/support/opa-sync-*`, `/support/opa-imports`, `/support/opa/sync-runs/{id}/resume` | GET/PUT/POST | Configuração, status e execução da sincronização |

Modelo de dados: `SupportOpaAttendance` (atendimento normalizado, 1 linha por
atendimento), `SupportOpaAttendanceRaw` (payload bruto), `SupportOpaDimension`
(nome de usuário/motivo/departamento/etiqueta/cliente — **só guarda id+nome, não os
campos extras que a API expõe**), `SupportOpaImportRun` (telemetria de importação).

### Frontend (`frontend/app/suporte/`)

Tela única (`page.tsx`) com 4 abas ativas: **Visão Geral**, **Atendentes**, **Dados**
(tabela + drawer de detalhe) e **Sincronização**. Já existem no menu, mas
**desativadas** ("Planejado"): Operação, Filas, Agentes, Motivos, Horários,
Histórico — ou seja, a intenção de expandir já estava prevista na navegação.

Sem biblioteca de gráficos (nenhum ECharts/Recharts hoje — só cards e tabelas).
Tabelas são um componente próprio (não TanStack). Filtros de período, atendente,
departamento e canal já existem e já atualizam cards/tabelas de forma combinada.

### Padrões reutilizáveis já existentes no projeto (para o SGP seguir)

- **Metas versionadas com histórico**: módulo Operações tem exatamente o padrão
  pedido no item 9 — `OperationTeamTargetRule` (regra vigente) +
  `OperationTeamTargetVersion` (histórico append-only, fecha `valid_to` e abre nova
  versão a cada mudança, nunca edita/apaga). É o modelo a replicar para metas de
  TMR/TMA/nota do SGP.
- **Auditoria de alteração de configuração**: `record_audit_log(db, user, "update", ...)`
  já é usado em `opa-sync-settings`. Mesmo padrão serve para log de quem mudou uma meta.
- **Mascaramento de campo sensível**: módulo Operações já mascara chaves sensíveis
  do `raw_payload` do IXC (`_sanitize_raw_payload`) e `ai_governance/field_registry.py`
  tem um flag `sensitive` por campo. É o padrão a copiar para mascarar telefone do
  cliente no SGP.
- **Fuso horário local correto**: módulo Operações tem `operations/period.py`
  (`OPERATIONS_TIMEZONE = ZoneInfo("America/Porto_Velho")`,
  `local_period_utc_bounds`) — pronto pra ser generalizado/copiado.
- **Janela de reincidência configurável**: a Gamificação já tem o conceito
  (`app_settings.recurrence_window_days`) para identificar reincidência operacional
  por contrato+assunto. Mesmo conceito serve para "cliente reincidente" no SGP.

### Gap crítico já identificado: fuso horário

Hoje o módulo Suporte (filtros de período, `/opa/overview`, `/opa/breakdowns`,
`/opa-metrics`) trabalha **inteiramente em UTC**, e os presets do frontend ("Hoje",
"Ontem" etc.) também são calculados em UTC. Isso viola o requisito deste projeto
("Todos os horários devem utilizar America/Porto_Velho, UTC-4") — quem abre "Hoje"
em Porto Velho (UTC-4) vê um recorte de dados deslocado em até 4 horas. Precisa ser
corrigido replicando o padrão de `operations/period.py`.

### Gap crítico já identificado: TMR construído na sessão anterior

Na sessão anterior implementei o TMR como "média de todos os intervalos
cliente→atendente da conversa" — mas **sem distinguir bot de humano**. A nova
especificação exige explicitamente não contar resposta automática como resposta
humana, e separar "tempo da primeira resposta" dos "tempos das respostas
seguintes". Isso vai precisar de rework (ver seção 6) usando o campo `tipo`
(`"bot"`/`"user"`) do endpoint `/api/v1/usuario/{id}`, que hoje não é sincronizado
para a dimensão local.

## 2. Métricas já existentes hoje

| Métrica | Onde |
|---|---|
| Total de atendimentos, encerrados, em aberto | `/opa/overview` |
| Taxa de encerramento | `/opa/overview` |
| Duração média (TMA de atendimentos fechados) | `/opa/overview`, `/opa-metrics` |
| Avaliação média | `/opa/overview`, `/opa-metrics` |
| Atendentes/departamentos distintos | `/opa/overview` |
| Volume por canal | `/opa/overview` |
| Volume/encerramento/duração/avaliação por atendente, departamento, motivo, canal, status, cliente | `/opa/breakdowns` |
| TMA e TMR por atendente e por motivo | `/opa-metrics` (não replicado em `/opa/breakdowns`) |
| TMR por atendimento individual | campo `tmr_seconds` na lista `/opa/attendances` |

## 3. Métricas que ainda precisam ser criadas

Classificadas por viabilidade real com os dados que a API do OPA Suite entrega hoje
(testei ao vivo contra `https://opasuite.souuni.com`, não estou supondo):

### A — Derivável com dados já disponíveis, só falta construir

- Atendimentos por IA / transferidos IA→humano (via `usuario.tipo = bot`)
- TMR só-humano e tempo da 1ª resposta humana, separados dos seguintes
- Tempo médio de espera até início do atendimento humano
- Tempo médio de permanência em cada departamento/fila (via `motivos[]`, timestamps de troca)
- Tempo médio até o transbordo (bot → humano), tempo total entre IA e humano
- Quantidade de transferências entre colaboradores e entre departamentos (confirmado: acontece **dentro do mesmo atendimento**, rastreável por `motivos[]` + mudança de `id_atend` na thread de mensagens — testei um atendimento real com handoff bot→humano no mesmo `_id`)
- Atendimentos sem resposta do colaborador (mensagem do cliente sem resposta subsequente antes do encerramento)
- Clientes únicos, % de reincidência (precisa de definição de janela, replicando o padrão já usado na Gamificação)
- % de avaliações positivas/neutras/negativas (precisa de definição de faixa — sugestão: 4-5 positiva, 3 neutra, 1-2 negativa, a confirmar com você)
- Maior tempo de espera, maior duração, percentis P50/P75/P90/P95 (agregação SQL sobre os tempos já calculados)
- Distribuição por dia/hora, evolução semanal/mensal, comparação com média da equipe (SQL novo sobre dado já existente)

### B — Não disponível na API do OPA Suite hoje (não vou simular)

- **Atendimentos abandonados** — não existe status ou flag para isso. Só dá pra
  aproximar com uma regra de negócio (ex.: aberto sem nenhuma mensagem do cliente
  há mais de X minutos, ou status `AG` que nunca evolui) — **precisa de definição
  sua antes de implementar**, e mesmo assim seria uma estimativa, não um dado exato.
- **Atendimentos encerrados por inatividade / encerrados automaticamente** — não
  encontrei campo de "motivo de encerramento" no payload do OPA Suite. Não é
  possível reportar essa métrica sem essa informação vinda da API.
- **Atendimentos reabertos** — não há flag de reabertura. Só dá pra aproximar
  (mesmo protocolo com novo `_id`, ou mesmo cliente+motivo em janela curta), com o
  mesmo aviso de estimativa.
- **Significado exato dos status `PS`** — inferi que `AG`/`EA`/`PS` são os 3
  estados "em aberto" (batem exatamente com os 1.253 atendimentos sem
  `closed_at`) e `F` é finalizado, mas o OPA Suite não expõe um enum/documentação
  desses códigos. Vou rotular como "inferido" na tela até confirmação oficial.
- **Filas como conceito separado de Departamento** — não existe na API
  (`/api/v1/fila`, `/api/v1/equipe` não existem). "Fila"/"Equipe" no módulo será
  sempre = Departamento (`setor`).
- **Metas configuráveis (item 9) e classificação normal/atenção/crítico (item 5)**
  — não vêm da API, são regras de negócio internas do SGP a construir (ver seção 6
  e 7 abaixo).

### C — Análise de conteúdo por IA (item 5 da sua especificação)

Tecnicamente possível (temos o texto completo das mensagens via
`/api/v1/atendimento/mensagem`), mas depende de decisão explícita sua antes de
qualquer implementação, porque **a sua própria seção 10 exige "não enviar
conversas para serviços externos sem autorização"** — e gerar resumo/sentimento por
IA normalmente significa mandar o texto da conversa para um modelo (interno ou
externo). Preciso que você decida:
- Qual modelo/infra usar (local vs. API externa, e se já há contrato/autorização).
- Quais atendimentos podem ser processados (todos? só amostra? só quando o cliente
  autorizou?).
Enquanto isso não for decidido, deixo esse item como Fase 6 (conforme suas fases
sugeridas), sem escopo técnico fechado ainda.

## 4. Mapeamento dos endpoints do OPA Suite (testados ao vivo)

| Endpoint | Finalidade | Paginação | Filtro | Chave de relação | Uso hoje |
|---|---|---|---|---|---|
| `POST-like GET /api/v1/atendimento` | Lista de atendimentos | `options.limit/skip` | `filter.dataInicialAbertura/dataFinalAbertura/dataInicialEncerramento/dataFinalEncerramento` | `_id` | Já usado (`OpaClient.list_attendances`) |
| `GET /api/v1/atendimento/{id}` | Detalhe (expande cliente/atendente/usuário embutidos) | — | — | `_id` | Já usado (`get_attendance_detail`) |
| `GET /api/v1/atendimento/mensagem` (filtro `id_rota`) | Histórico de mensagens da conversa | `options.limit/skip` | `filter.id_rota` = `_id` do atendimento | `id_rota` = `atendimento._id` | Já usado (novo, para TMR) |
| `GET /api/v1/usuario/` e `/api/v1/usuario/{id}` | Atendentes/usuários, com `tipo` (`user`/`bot`) e `status` | `options.limit/skip` (lista) | `filter` livre | `_id` | Parcialmente usado (só nome é sincronizado hoje) |
| `GET /api/v1/departamento/` | Departamentos/filas, com config completa (PABX, pesquisa de satisfação, mensagens automáticas) | `options.limit/skip` | `filter` livre | `_id` | Parcialmente usado (só nome é sincronizado hoje) |
| `GET /api/v1/atendimento/motivo` | Motivos, com `departamentos[]` associados | `options.limit/skip` | `filter` livre | `_id` | Parcialmente usado |
| `GET /api/v1/etiqueta/` | Etiquetas/tags, com `cor` | `options.limit/skip` | `filter` livre | `_id` | Parcialmente usado (cor não é sincronizada) |
| `GET /api/v1/cliente/` | Clientes, com `cpf_cnpj`, `status`, `fornecedor`, lat/long | `options.limit/skip` | `filter` livre | `_id` | Parcialmente usado (só nome é sincronizado) |

**Não existem** (testado, retornam 302/erro): `/api/v1/fila`, `/api/v1/equipe`,
`/api/v1/atendimento/transferencia`, `/api/v1/atendimento/evento`,
`/api/v1/atendimento/status`, e não há Swagger/OpenAPI público exposto. Ou seja,
**todo evento de transferência/transbordo precisa ser reconstruído a partir de
`motivos[]` do próprio atendimento e da sequência de `id_atend` na thread de
mensagens** — não existe um log de eventos dedicado.

**Limite de requisições**: não documentado publicamente; hoje a ingestão já usa
paginação de 100 registros por página com retry (`SUPPORT_OPA_PAGE_RETRIES = 3`).
Buscar mensagens por atendimento adiciona **1 chamada extra por atendimento
importado** — já em produção para o cálculo de TMR. Qualquer novo enriquecimento
(dimensões completas de usuário/departamento/cliente) deve continuar sendo feito em
lote (como já é: `list_users`, `list_departments` etc.), nunca por atendimento.

## 5. Matriz "métrica × campos necessários × endpoint" (resumo das novas)

| Métrica nova | Campos necessários | Endpoint/fonte |
|---|---|---|
| Atendimento por IA / transbordo IA→humano | `usuario.tipo` de cada `id_atend` distinto na thread | `/api/v1/usuario/{id}` (sincronizar em lote) + `/api/v1/atendimento/mensagem` |
| TMR só-humano / 1ª resposta humana | mesmo acima + `data` das mensagens | idem |
| Tempo em cada departamento / até o transbordo | `motivos[].data`, `motivos[].idDepartamento`, `opened_at` | `atendimento.motivos[]` (já baixado, só não é persistido detalhadamente hoje) |
| Transferências entre colaboradores | `id_atend` distintos + ordem temporal na thread | `/api/v1/atendimento/mensagem` |
| Sem resposta do colaborador | última mensagem da thread é do cliente e atendimento fechado | `/api/v1/atendimento/mensagem` + `closed_at` |
| Clientes únicos / reincidência | `customer_id`, `opened_at`, janela configurável | já persistido |
| % avaliação positiva/neutra/negativa | `rating` + faixa de corte (a definir) | já persistido |
| Percentis de tempo | `tma_seconds`/`tmr_seconds` já persistidos | SQL (`percentile_cont`) |
| Dentro/fora de meta | métrica calculada + meta configurada | novo modelo de meta (seção 6) |
| PF/PJ, cliente ativo/fornecedor | `cpf_cnpj`, `status`, `fornecedor` do cliente | `/api/v1/cliente/` (sincronizar campos extras) |
| Config de departamento (pesquisa vinculada, PABX) | campos extras de departamento | `/api/v1/departamento/` (sincronizar campos extras) |

## 6. Regras exatas de cálculo (revisão sobre o que já existe)

- **TMA**: `closed_at - opened_at`, só quando ambos existem. Sem alteração —
  já está correto.
- **TMR (revisão necessária)**: hoje calcula a média de **todo** intervalo
  cliente→atendente, incluindo bot. Nova regra: classificar cada `id_atend` da
  thread via `usuario.tipo`; ignorar mensagens de `tipo="bot"` para fins de "TMR
  humano"; manter separadamente:
  - `tmr_first_human_seconds`: intervalo entre a mensagem do cliente e a **primeira**
    mensagem de um atendente humano depois dela (por atendimento).
  - `tmr_avg_human_seconds`: média de **todos** os intervalos cliente→humano
    (substituindo o cálculo atual, que hoje mistura bot).
  - Métrica adicional apenas informativa: `tempo_medio_ia_seconds` (o que hoje
    chamamos de TMR, mas correto seria rotular como "tempo médio de resposta do
    atendimento automatizado", não do "nosso atendente").
- **Tempo de espera até início do atendimento humano**: `primeira mensagem de
  id_atend com tipo=user` menos `opened_at`.
- **Tempo em cada departamento**: diferença entre timestamps consecutivos de
  `motivos[]` (troca de `idDepartamento`); último trecho vai até `closed_at`.
- **Reincidência**: cliente com novo atendimento do mesmo motivo dentro de N dias
  (configurável, mesmo padrão de `recurrence_window_days` da Gamificação — valor
  default a definir com você).
- **Dentro/fora de meta**: comparação direta do valor calculado contra a meta
  vigente (`SupportOpaTargetVersion`, ver seção 7) na data do atendimento.
- **Não calcular quando faltar dado**: qualquer métrica sem os campos-base
  (ex.: atendimento sem nenhuma mensagem recuperável) deve retornar `null` e a
  tela deve mostrar "Não disponível" — nunca zero ou vazio silencioso.
- **Fuso**: todo cálculo de "dia"/período usa `America/Porto_Velho`
  (`local_period_utc_bounds`, a replicar de `operations/period.py`); os timestamps
  continuam armazenados em UTC (boa prática), só a interpretação de período muda.

## 7. Modelo de dados proposto (novo, incremental — nada é removido)

- **`support_opa_dimensions`**: passar a persistir campos extras já disponíveis
  (hoje descartados) dentro do `payload_json` que já existe — sem migration nova,
  só ajustar leitura. Adicionar coluna `extra_json` seria redundante já que
  `payload_json` já guarda o registro bruto completo; o trabalho é só **usar** esse
  payload (ex.: ler `tipo` do usuário a partir do `payload_json` já salvo).
- **`support_opa_attendance_events`** (nova tabela): timeline reconstruída por
  atendimento — uma linha por evento (`troca_departamento`, `troca_atendente`,
  `mensagem_cliente`, `mensagem_atendente`, `avaliacao`), com `attendance_id`,
  `event_type`, `actor_type` (`client`/`human`/`bot`/`system`), `occurred_at`,
  `payload_json`. Evita recomputar a thread inteira toda vez que a tela de
  histórico/timeline for aberta.
- **`support_opa_targets`** + **`support_opa_target_versions`** (novas tabelas,
  espelhando `OperationTeamTargetRule`/`OperationTeamTargetVersion`): meta vigente
  + histórico append-only de `target_tma_seconds`, `target_tmr_seconds`,
  `target_rating`, `max_transfers`, `max_recurrence_pct`, escopo (global / por
  departamento — a definir com você se precisa por atendente também), `valid_from`,
  `valid_to`, `created_by`.
- **Colunas novas em `support_opa_attendances`**: `tmr_first_human_seconds`,
  `tmr_avg_human_seconds` (substituindo o uso solitário de `tmr_seconds`, que passa
  a representar "tempo médio de resposta do atendimento automatizado" para não
  quebrar quem já consome o campo), `first_human_response_at`,
  `handled_by_ai_only` (bool), `transferred_ai_to_human` (bool),
  `department_transfer_count`, `attendant_transfer_count`, `is_recurrent` (bool).

## 8. Estrutura das telas (aproveitando o que já existe)

- **Visão Geral** (existente, expandir): novos cards (clientes únicos,
  reincidência, IA vs humano, transbordos) + gráfico de tendência (será necessário
  **adicionar uma lib de gráfico** — hoje não existe nenhuma no frontend; sugestão:
  reaproveitar o que outros módulos já usam, como ECharts citado no
  [README.md](../README.md), para manter consistência visual).
- **Atendentes** (existente, expandir): já tem drawer individual — vira a base do
  "Painel Individual" pedido no item 3, adicionando distribuição por
  assunto/dia/hora, evolução semanal/mensal, comparação com a média da equipe,
  pontos fortes/a melhorar (texto gerado a partir dos indicadores, não por IA).
- **Dados** (existente): já é o histórico com filtros e paginação — precisa dos
  novos filtros (seção 6 da sua especificação) e de uma nova aba de **Linha do
  Tempo** dentro do drawer de detalhe.
- **Filas/Departamentos** (hoje "Planejado", ativar): breakdown por departamento já
  existe no backend (`/opa/breakdowns?dimension=department`) — só falta habilitar a
  aba no frontend e adicionar tempo médio por fila.
- **Qualidade da integração** (nova aba, item 11 da sua especificação): última
  sincronização, período coberto, registros processados/descartados/incompletos,
  erros — já há boa parte disso em `SupportOpaImportRun`, só falta expor numa tela.
- **Análise de conversas por IA**: fica de fora desta primeira leva de telas até a
  decisão da seção 3-C ser tomada.

## 9. Regras de acesso e privacidade

Hoje `support:read` é tudo-ou-nada (quem tem a permissão vê telefone do cliente e
detalhe completo do atendimento). Proposta, seguindo o padrão que o próprio projeto
já usa em Operações (mascaramento de `raw_payload`) e no `field_registry` do
`ai_governance`:

- Nova permissão `support:view_pii` (ou nome equivalente) para exibir
  `channel_customer` (telefone) e o conteúdo textual das mensagens sem
  mascaramento. Sem essa permissão, mostrar parcialmente mascarado (ex.:
  `55699*****71`).
- Nova permissão `support:view_conversation` para acessar a linha do tempo/histórico
  completo da conversa — granularidade que a especificação pede ("histórico
  completo somente para cargos autorizados").
- Registrar auditoria (`record_audit_log`, já existe) toda vez que alguém abrir a
  conversa completa de um atendimento — rastreabilidade de acesso, pedida no item
  10.
- Continuar sem enviar conversa a serviço externo sem autorização explícita
  (bloqueia a Fase 6 até decisão).

## 10. Plano de implementação em fases

Adoto as fases que você sugeriu, com o que cada uma entrega de fato:

- **Fase 1 (esta entrega)**: diagnóstico, mapeamento de endpoints, matriz de
  métricas, plano de dados — **concluída neste documento**, aguardando sua validação.
- **Fase 2**: visão geral expandida — clientes únicos, reincidência, IA vs humano,
  transbordos, correção de fuso horário (`America/Porto_Velho`).
- **Fase 3**: TMR revisado (só-humano + 1ª resposta), tempo em fila, tempo até
  transbordo, TMA já existente mantido, percentis.
- **Fase 4**: painel individual do colaborador (evolução, comparação com equipe,
  distribuição por assunto/dia/hora).
- **Fase 5**: histórico + linha do tempo por atendimento (nova tabela de eventos).
- **Fase 6**: análise de conversas por IA — **bloqueada até decisão de infra/autorização**.
- **Fase 7**: metas configuráveis, alertas, exportação.
- **Fase 8**: testes, auditoria e validação dos cálculos com dados reais.

Cada fase entra em código só depois de validação sua, conforme a regra do
[AGENTS.md](../AGENTS.md).

## 11. Riscos técnicos e dependências

- **Custo de API**: reconstruir a timeline completa (mensagens) por atendimento já
  é 1 chamada extra por atendimento na importação (TMR). Backfill histórico de
  39.300 atendimentos para preencher os novos campos (IA/humano, transbordo, tempo
  em fila) teria o mesmo custo que decidimos não pagar para o TMR — mesma decisão
  a confirmar aqui: só novas importações, ou vale um backfill pontual agora que o
  ganho de informação é maior?
- **Significado de `status=PS`** e de qualquer "motivo de encerramento" não
  documentado — depende de confirmação externa (suporte do OPA Suite) ou de
  observação de mais dados ao longo do tempo.
- **Falta de endpoint de transferência/evento dedicado**: a reconstrução via
  `motivos[]` + thread de mensagens é uma inferência razoável (confirmei que
  funciona num caso real), mas pode não cobrir 100% dos padrões de transferência
  do OPA Suite — recomendo validar com uma amostra maior antes de tratar como
  fonte de verdade em relatório executivo.
- **Fuso horário**: corrigir o filtro de período do módulo Suporte para
  `America/Porto_Velho` muda os números que a Visão Geral mostra hoje (mesmo sem
  nenhuma feature nova) — é uma correção de bug, mas usuários que já se
  acostumaram com os números atuais vão ver diferença.
- **Gráficos**: não há biblioteca de visualização no frontend hoje — entra como
  nova dependência, mesmo que pequena.

## 12. Critérios de aceite e testes

- Toda métrica nova deve ter: fórmula documentada (seção 6), teste automatizado
  cobrindo o caso "dado suficiente" e o caso "dado insuficiente → null/'Não
  disponível'", e rastreabilidade até o(s) atendimento(s) que a compõem (drill-down
  já é o padrão do projeto — replicar).
- Nenhuma métrica pode ser exibida com valor calculado a partir de dado simulado —
  se a fonte não tiver o campo, a tela mostra "Não disponível" ou "Base
  insuficiente" (conforme sua própria regra).
- TMR revisado deve bater, para o caso de teste manual já validado nesta sessão
  (atendimento `6a83d9addcf2d55a984ff776`, bot respondeu em 9s), mostrando esse
  atendimento como 100% IA (sem TMR humano, "Não disponível").
- Correção de fuso horário validada comparando contagem de "Hoje" antes/depois da
  mudança, com um dia de exemplo perto da meia-noite UTC.
- Nenhuma funcionalidade das 4 abas ativas hoje pode regredir — cobrir com teste de
  regressão antes de expandir cada uma.
