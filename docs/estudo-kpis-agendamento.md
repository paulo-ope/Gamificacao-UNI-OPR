# Estudo — Métricas e KPIs para o setor de agendamento de um ISP

Status: proposta para validação · Autor: Claude (Cowork) · Data: 2026-07-29

## 1. Contexto e o que motivou este estudo

O setor de agendamento da UNI é quem transforma uma O.S. aberta em uma visita marcada com o
cliente. Hoje a única visão existente é uma aba dentro da Operação Analítica com duas métricas
(volume por operador e tempo médio até agendar), sem filtros e com apresentação pobre. O dono do
produto pediu: módulo próprio, filtros de verdade e métricas corretas.

### 1.1 A métrica atual está certa — mas conta a história errada

Investigação com dados reais (12 O.S. de julho/2026, setores técnicos) provou que a medição atual
**já usa a semântica certa**: o campo `data` do evento "Agendamento" (id 5) em
`su_oss_chamado_mensagem` é o instante em que o **operador interagiu** com a O.S., não o horário
combinado com o cliente (`data_inicio`). E `su_oss_chamado.data_abertura` é idêntico ao timestamp
do evento "Abertura" (id 1) do log — diferença máxima de 1 segundo na amostra. Ou seja, a conta
"abertura → interação de agendamento" já é log→log na prática.

O problema real é **como o número é agregado e apresentado**:

| O que a tela mostra hoje | O que os dados dizem |
|---|---|
| "Tempo médio até agendar: 12,4 h" | Mediana: **40 minutos**. A média é inflada pela cauda longa (O.S. abertas de madrugada/fim de semana só são tratadas no expediente seguinte). |

Uma média solta, sem mediana, percentil ou distribuição, faz um setor rápido parecer lento. É por
isso que a métrica "parece errada" — ela mede certo e comunica errado.

**Referência da amostra** (por que confiar na semântica): O.S. 1282925 aberta 07:58, operador
agendou às 08:15 (evento 5, `data`) para uma janela às 16:30 (`data_inicio`). A métrica registra
17 minutos (resposta do setor), não 8,5 horas (janela do cliente). Se usássemos `data_inicio`, a
média da amostra inflaria ~3 horas.

## 2. Dados disponíveis no IXC (todos já validados ao vivo)

| Fonte | Campos relevantes | Observação |
|---|---|---|
| `su_oss_chamado_mensagem` | `id_chamado`, `id_evento`, `data` (instante da interação), `data_inicio`/`data_final` (janela combinada), `id_operador`, `id_tecnico` | Um registro por evento do ciclo de vida da O.S. |
| `su_oss_evento` | 1=Abertura, 2=Alteração, 3=Reabertura, 4=Alteração de setor, 5=Agendamento, 6=Fechamento, 7=Em Análise, 8=Assumido, 9=Em Execução, 10=Reagendar | Dicionário dos eventos |
| `su_oss_chamado` | `data_abertura`, `data_agenda`, `melhor_horario_agenda` (Q/M/T), `setor`, `id_filial`, `id_assunto`, `status`, `data_hora_execucao`, `data_fechamento` | Dimensões para filtro |
| `usuarios` | `id`, `nome` | Resolve `id_operador` → nome do operador |

Volume real medido (julho/2026, setores técnicos): ~9,6 mil O.S. abertas, ~23 mil eventos de
agendamento/reagendamento, 170 operadores distintos com pelo menos 1 evento.

## 3. KPIs propostos

Baseados em prática de mercado para field service/dispatch de telecom (time-to-schedule,
reschedule rate, on-time arrival, backlog aging, metas estilo "X% em até Y tempo") cruzada com o
que o IXC efetivamente registra. Organizados em 4 grupos; a coluna "v1" marca o que proponho
construir primeiro.

### Grupo A — Velocidade de resposta (o coração do setor)

| # | KPI | Definição / fórmula | Fonte | v1 |
|---|---|---|---|---|
| A1 | **Tempo até 1º agendamento (TTFA)** | evento 1 → primeiro evento 5 da O.S. (`data` de ambos). Reportar **mediana, P90 e média** juntos, nunca média sozinha | log | ✔ |
| A2 | **Distribuição do TTFA** | buckets: ≤15min, 15min–1h, 1–4h, 4–24h, >24h — histograma clicável | log | ✔ |
| A3 | **SLA de agendamento** | % de O.S. agendadas em até X horas (meta configurável, ex.: 80% em 4h) — o formato "X% dentro de Y" é o padrão da indústria para metas de resposta | log | ✔ |
| A4 | **TTFA em horário útil** | mesmo cálculo descontando o tempo fora do expediente do setor (noites/domingos não penalizam) | log + janela configurável | opcional |

### Grupo B — Produtividade do operador

| # | KPI | Definição / fórmula | Fonte | v1 |
|---|---|---|---|---|
| B1 | **Agendamentos por operador/dia útil** | eventos 5+10 do operador ÷ dias úteis do período, contra a meta (40/dia) — modos "cada ação" e "O.S. distintas" | log | ✔ |
| B2 | **Evolução diária do time** | série temporal de eventos de agendamento por dia, com linha de capacidade esperada (operadores ativos × meta) | log | ✔ |
| B3 | **Quem agenda primeiro** | por operador: quantas O.S. ele foi o primeiro a agendar + TTFA mediano dele | log | ✔ |

### Grupo C — Qualidade do agendamento

| # | KPI | Definição / fórmula | Fonte | v1 |
|---|---|---|---|---|
| C1 | **Taxa de reagendamento** | % de O.S. agendadas que tiveram ≥1 evento posterior de agenda (evento 10, ou 5 repetido) + média de reagendas por O.S. — reschedule rate clássico | log | ✔ |
| C2 | **Antecedência da janela** | evento 5 `data` → `data_inicio` (para quantos dias/horas no futuro a agenda está sendo marcada). Antecedência crescente = agenda de campo lotada, alerta de capacidade | log | ✔ |
| C3 | **Aderência à janela combinada** | `data_inicio` da última agenda vs `data_hora_execucao` real (o técnico chegou na janela?) — on-time arrival. É métrica de campo, mas o estouro volta como reagendamento pro setor | log + O.S. | fase 2 |

### Grupo D — Fila e backlog

| # | KPI | Definição / fórmula | Fonte | v1 |
|---|---|---|---|---|
| D1 | **Backlog sem agendamento** | O.S. abertas sem nenhum evento 5, com envelhecimento (hoje, 1–2d, 3–7d, >7d) — é a lista de trabalho do dia do setor | log + O.S. | ✔ |
| D2 | **Heatmap de demanda** | hora × dia da semana de abertura das O.S. vs momento em que o setor age — insumo direto de escala/turno | log | fase 2 |

## 4. Arquitetura proposta para o módulo

### 4.1 O ponto que muda tudo: sincronizar, não consultar ao vivo

A versão atual consulta o IXC ao vivo e um mês inteiro leva **2–3 minutos** por consulta (46+
páginas de API). Isso já obrigou a criar jobs assíncronos com polling — e ficaria inviável num
módulo com filtros interativos (cada mudança de filtro custaria minutos).

A proposta é fazer o que a Operação Analítica já faz com O.S.: **sincronizar os eventos para uma
tabela local** (`scheduling_events`: eventos 1, 5, 10 e 6 dos setores de interesse, com snapshot
das dimensões — filial, setor, assunto, operador), com sync incremental por marca d'água. Volume
tranquilo (~35 mil linhas/mês). Com o dado local, **todo KPI vira SQL instantâneo e qualquer
combinação de filtro responde em milissegundos**, incluindo períodos livres (não só mês fechado).

### 4.2 Estrutura

- **Backend**: `app/modules/scheduling/` seguindo o padrão de `app/modules/operations/` (models,
  sync, router, schemas próprios). A permissão `operations:view_scheduling` vira
  `scheduling:read` (+ `scheduling:sync` para o backfill manual).
- **Frontend**: página própria `/agendamento` + card na home do ecossistema (mesmo padrão visual
  dos módulos existentes). A aba atual dentro da Operação Analítica é removida.
- **Filtros** (barra fixa no topo, como na Operação Analítica): período livre (de/até),
  filial/regional, setor, assunto, operador, modo de contagem.
- **Layout**: linha de cards de resposta (TTFA mediana/P90/SLA), histograma de distribuição,
  série diária de produção, ranking de operadores com meta, painel de reagendamento, tabela de
  backlog sem agendamento com aging.

## 5. Decisões que precisam do dono do produto

1. **SLA de agendamento**: qual a meta inicial? (ex.: 80% agendadas em até 4h corridas)
2. **Horário útil**: medir TTFA também em horas úteis? Qual o expediente do setor?
3. **Escopo do sync**: só setores técnicos (7, 8, 9) ou todos?
4. **Meta de produtividade**: 40/dia por operador — vale para todos, ou há operadores com função
   mista que não deveriam ser cobrados pela meta cheia?

## 6. Fontes de mercado consultadas

- BuildOps — 40+ Field Service Metrics & KPIs (time to schedule, reschedule rate)
- Sonar Software — Top Field Service Metrics Fiber Providers Should Be Tracking
- NetSuite — Comprehensive Guide to Field Service Metrics & KPIs
- ServiceTitan — Key Field Service Metrics (on-time arrival, jobs/tech/day)
- Zendesk / Invensis — metas de nível de serviço no formato "X% em até Y tempo"
