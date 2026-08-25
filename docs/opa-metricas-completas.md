# Operações Analíticas (OPA) - Catálogo Completo de Métricas

## Visão Geral

Este documento lista TODAS as métricas, dados e agregações capazes de serem extraídas do módulo de Operações Analíticas (OPA) a partir do banco de dados e APIs disponíveis.

---

## 1. Tabelas Base do Banco de Dados

### 1.1 `operations_orders` (Tabela Principal)

Armazena todas as Ordens de Serviço importadas do IXC, com mais de 30 campos:

#### Identificação
- `id` - ID único interno
- `source` - Origem (ex: "ixc")
- `source_order_id` - ID no sistema origem
- `order_code` - Código da O.S.
- `protocol` - Protocolo/Ticket

#### Cliente
- `contract_id` - ID do contrato
- `customer_id` - ID do cliente
- `customer_login` - Login do cliente
- `customer_name` - Nome do cliente

#### Localização
- `regional` - Regional/Filial
- `state` - Estado (UF)
- `city` - Cidade
- `company_id` - ID da empresa

#### Tipo e Assunto
- `contract_type` - Tipo de contrato
- `person_type` - Pessoa (Física/Jurídica)
- `os_type` - Tipo de O.S. (Instalação, Manutenção, etc.)
- `os_subject` - Assunto (Sem Conexão, Fatura, Hardware, etc.)
- `diagnosis` - Diagnóstico (Rompimento, CTO Sem Sinal, etc.)

#### Responsabilidade
- `department` - Departamento
- `sector` - Setor (7, 8, 9, etc.)
- `creator` - Criador
- `responsible` - Responsável pela execução

#### Projeto
- `project` - Nome do projeto
- `pop` - Ponto de Presença

#### Status
- `status_code` - Código do status
- `status` - Status texto (Aberta, Fechada, etc.)
- `is_closed` - Boolean: está fechada?
- `is_internal` - Boolean: é chamado interno?

#### SLA e Tempo
- `sla_status` - Status SLA (dentro, fora, etc.)
- `sla_target_hours` - Horas alvo de SLA
- `elapsed_hours` - Horas decorridas
- `opened_at` - Data/hora abertura
- `deadline_at` - Data/hora limite SLA
- `scheduled_at` - Data/hora agendamento
- `closed_at` - Data/hora fechamento
- `source_updated_at` - Última atualização no IXC

#### Auditoria
- `raw_payload` - Payload JSON original do IXC
- `normalization_notes` - Anotações de normalização
- `first_imported_at` - Primeira importação
- `last_imported_at` - Última importação

**Índices disponíveis:**
- `source`, `order_code`, `contract_id`, `customer_login`
- `regional`, `os_type`, `os_subject`, `diagnosis`
- `status`, `is_closed`, `sla_status`
- `opened_at`, `closed_at`, `deadline_at`
- `(regional, os_type, os_subject)` - Índice de dimensionalidade

---

### 1.2 `operations_team_models` (Configuração de Metas)

Define metas diárias e ranges de performance por time:

```json
{
  "id": 1,
  "name": "Time Técnico",
  "daily_target": 5,
  "critical_max_percent": 69,
  "attention_max_percent": 99,
  "target_max_percent": 119,
  "zero_color": "#f1f5f9",
  "critical_color": "#fee2e2",
  "attention_color": "#fef3c7",
  "target_color": "#dcfce7",
  "exceeded_color": "#dbeafe"
}
```

### 1.3 `operations_team_target_rules` (Metas por Período)

Define metas diferentes para weekday/saturday/sunday/monthly:

```json
{
  "team_model_id": 1,
  "period_type": "weekday",
  "enabled": true,
  "median_from_quantity": 3,
  "good_from_quantity": 4,
  "target_quantity": 5,
  "start_time": "08:00",
  "end_time": "18:00"
}
```

### 1.4 `operations_responsible_assignments` (Responsáveis)

Mapeia responsáveis IXC para colaboradores gamificação:

```json
{
  "responsible_name": "João Silva",
  "regional": "JI PARANA",
  "team_model_id": 1,
  "collaborator_id": 42
}
```

### 1.5 `operations_subject_type_mappings` (Assunto → Tipo)

Mapeia assuntos para tipos de O.S.:

```json
{
  "subject": "Sem Conexão (Link LOS)",
  "os_type": "Suporte",
  "active": true
}
```

### 1.6 `operations_saved_filters` (Filtros Salvos)

Permite usuários salvar combinações de filtros

### 1.7 `operations_import_runs` (Histórico de Importações)

Registra cada sincronização com IXC:
- Data importação
- Status (running, completed, failed)
- Contagens (fetched, created, updated, rejected)
- Tempo de execução

---

## 2. Métricas de Visão Geral (`/overview`)

### 2.1 Métricas Agregadas

**Contadores básicos:**
- Total de O.S. no período
- Total aberto vs fechado
- Total por status (Aberta, Fechada, Pendente, etc.)

**Breakdown por dimensão:**
```
{
  "regional": {
    "JI PARANA": {"opened": 150, "closed": 120, "percentage": 80},
    "PORTO": {"opened": 90, "closed": 85, "percentage": 94},
    ...
  },
  "os_type": {
    "Suporte": {"opened": 100, "closed": 95, ...},
    "Instalação": {...},
    ...
  },
  "os_subject": {
    "Sem Conexão": {...},
    "Fatura": {...},
    ...
  },
  "diagnosis": {
    "Rompimento": {...},
    "CTO Sem Sinal": {...},
    ...
  }
}
```

**SLA Agregado:**
- % Dentro do SLA
- % Fora do SLA
- Tempo médio de resolução
- Tendência (melhorando/piorando)

---

### 2.2 Gráfico de Tendências (`/overview/trends`)

Séries temporais diárias/horárias de:
- Volume de aberturas (por dia)
- Volume de encerramentos (por dia)
- SLA compliance % (por dia)
- Taxa de recorrência (por dia)

**Granularidades disponíveis:**
- Horária
- Diária
- Semanal
- Mensal

---

### 2.3 Alertas de Volume (`/overview/volume-alerts`)

Detecta anomalias em volume de tipos/assuntos:

```json
{
  "alert_type": "unusual_volume",
  "subject": "Sem Conexão Fibra Rural",
  "expected": 5,
  "actual": 23,
  "deviation_percent": 360,
  "severity": "high"
}
```

---

### 2.4 Control Tower (`/overview/control-tower`)

Agregação multinível detalhada:

```
Suporte → Sem Conexão → JI PARANA → Rompimento
```

Para cada caminho (ou "drilldown"):
- Volume total
- SLA status
- Tempo médio
- Tendência
- Insights (anomalias detectadas)

**Níveis de agregação:**
1. Assunto (subject)
2. Regional
3. Cidade (city)
4. Setor (sector)
5. Responsável (responsible)

---

### 2.5 Schedule de Trabalho (`/overview/work-schedule`)

Classifica O.S. fechadas por horário de conclusão:

```json
{
  "completed": 150,
  "classified": 145,
  "outside_schedule": 32,
  "before_start": 10,
  "after_end": 22,
  "outside_rate": 22.1,
  "by_model": [
    {
      "model_name": "Time Técnico",
      "completed": 100,
      "outside_schedule": 15,
      "outside_rate": 15
    }
  ]
}
```

---

## 3. Métricas de SLA

### 3.1 SLA Hierarchy (`/sla/hierarchy`)

Breakdown agregado de SLA por dimensão:

```json
{
  "total": {
    "within_sla": 120,
    "outside_sla": 20,
    "percentage": 85.7
  },
  "by_regional": {
    "JI PARANA": {"within_sla": 80, "outside_sla": 10, "percentage": 88.9},
    "PORTO": {"within_sla": 40, "outside_sla": 10, "percentage": 80}
  },
  "by_os_type": {...},
  "by_os_subject": {...}
}
```

### 3.2 SLA por Colaborador (`/sla/collaborators`)

**Tabela de colaboradores com:**
- Total de O.S. atribuídas
- % dentro do SLA
- Tempo médio de resolução
- Trending (melhora/piora)
- Performance band (crítica, atenção, meta, excelente)

**Agregações:**
- Por regional
- Por tipo de O.S.
- Por assunto

---

## 4. Métricas de Calendário

### 4.1 Visão Mensal (`/calendar`)

Grade 7x5 com células representando dias do mês:
- Cor: performance band (crítico, atenção, normal, excelente)
- Número: quantidade de O.S. fechadas
- Hover: datas em que o responsável saiu do turno

### 4.2 Detalhe do Dia (`/calendar/day-detail`)

Para um dia específico (ou semana/mês):

```json
{
  "date": "2026-08-15",
  "period": "day",
  "completed": 45,
  "by_responsible": [
    {
      "responsible": "João Silva",
      "completed": 8,
      "target": 5,
      "band": "excellent"
    }
  ],
  "orders": [
    {
      "order_code": "OS-12345",
      "customer": "Client XYZ",
      "subject": "Sem Conexão",
      "status": "Fechada",
      "closed_at": "2026-08-15 14:30"
    }
  ]
}
```

---

## 5. Métricas de Backlog

### 5.1 Em Progresso (`/in-progress`)

Agregação de O.S. abertas (não fechadas):

```json
{
  "by_subject": {
    "Sem Conexão": {
      "count": 45,
      "oldest_hours": 72,
      "sla_at_risk": 12,
      "sla_out_of_time": 3
    }
  }
}
```

### 5.2 Risco de SLA (`/in-progress/sla-risk`)

O.S. em progresso ordenadas por risco SLA:

```json
{
  "order_code": "OS-12345",
  "customer": "Client XYZ",
  "subject": "Sem Conexão",
  "opened_at": "2026-08-13 09:00",
  "hours_elapsed": 48,
  "sla_target_hours": 24,
  "hours_remaining": -24,
  "risk_level": "critical"
}
```

---

## 6. Análise de Aberturas (`/openings/analytics`)

Quebra analítica de O.S. abertas no período:

```json
{
  "total_openings": 500,
  "by_subject": {
    "Sem Conexão": {
      "count": 250,
      "percentage": 50,
      "closed_rate": 85,
      "avg_resolution_hours": 36
    }
  },
  "by_regional": {...},
  "sla_impact": "HIGH"
}
```

---

## 7. Filtros e Dimensões

### 7.1 Opções de Filtro (`/filters`)

Para cada dimensão, retorna valores únicos presentes nos dados:

```json
{
  "regionals": ["JI PARANA", "PORTO", ...],
  "os_types": ["Suporte", "Instalação", ...],
  "os_subjects": ["Sem Conexão (Link LOS)", "Fatura Vencida", ...],
  "diagnosis": ["Rompimento", "CTO Sem Sinal", ...],
  "statuses": ["Aberta", "Fechada", "Pendente"],
  "max_values_per_field": 500
}
```

### 7.2 Filtros Salvos (`/saved-filters`)

Cada usuário pode salvar combinações de filtros:
- Nome do filtro
- Dimensões selecionadas
- Visibilidade (pessoal/global)
- Criado em
- Atualizado em

---

## 8. Gestão de Dados

### 8.1 Freshness (`/data-freshness`)

Status de atualização dos dados:

```json
{
  "last_sync": "2026-08-25 14:32:15",
  "last_sync_duration_seconds": 145,
  "total_orders": 125430,
  "orders_today": 450,
  "sync_status": "up_to_date",
  "next_sync_in_seconds": 298
}
```

### 8.2 Import Runs

Histórico completo de importações:

```json
{
  "id": 1,
  "date_from": "2026-08-20",
  "date_to": "2026-08-25",
  "status": "completed",
  "fetched_count": 500,
  "created_count": 120,
  "updated_count": 380,
  "unchanged_count": 0,
  "rejected_count": 0,
  "started_at": "2026-08-25 14:00:00",
  "finished_at": "2026-08-25 14:02:25"
}
```

---

## 9. Ordenação de O.S. (Search)

### 9.1 Endpoint `/orders`

Retorna lista paginada de O.S. com filtros:

**Parâmetros:**
- `date_from`, `date_to` - Período
- `regional` - Regional específico
- `os_type` - Tipo de O.S.
- `os_subject` - Assunto
- `diagnosis` - Diagnóstico
- `status` - Status
- `sort_by` - Campo para ordenação
- `sort_dir` - Direção (asc/desc)
- `limit` - Paginação
- `offset` - Paginação

**Resposta:**
```json
{
  "orders": [
    {
      "id": 1,
      "order_code": "OS-12345",
      "customer_name": "Client XYZ",
      "regional": "JI PARANA",
      "os_type": "Suporte",
      "os_subject": "Sem Conexão",
      "status": "Fechada",
      "sla_status": "Dentro do prazo",
      "opened_at": "2026-08-20 09:00",
      "closed_at": "2026-08-20 14:30",
      "elapsed_hours": 5.5,
      "sla_target_hours": 24
    }
  ],
  "total": 1250,
  "page": 1,
  "page_size": 50
}
```

### 9.2 Endpoint `/openings/orders`

O.S. que abriram no período (subset de `/orders`)

---

## 10. Configuração e Administração

### 10.1 Modelos de Time (`/team-configuration`)

CRUD de modelos de time:
- Criar novo modelo
- Atualizar metas diárias
- Definir ranges de performance (crítica%, atenção%, alvo%, acima)
- Definir cores do calendário
- Ativar/desativar modelo

### 10.2 Mapeamento de Responsáveis

**Sync com IXC:**
- Importar responsáveis do IXC
- Mapear para colaboradores (gamificação)
- Vincular a modelo de time
- Atualizar regional

**Criação manual:**
- Adicionar responsável
- Definir regional
- Opcional: vincular a modelo

### 10.3 Mapeamento de Assuntos

**Automático:**
- Ao importar O.S., criar mapeamento subject → os_type

**Manual:**
- Atualizar mapeamento (bulk)
- Ativar/desativar
- Audit trail

### 10.4 Sincronização IXC

**Endpoints:**
- `POST /imports` - Importar período específico (com modo backfill)
- `POST /imports/backfill` - Job de backfill pausável
- `POST /imports/open-backlog` - Sincronizar todas as O.S. abertas

**Configurações:**
- Ativa/desativa
- Intervalo de sincronização (minutos)
- Lookback dias (quantos dias voltam)
- Setores IXC a importar

---

## 11. Exportação de Dados

### 11.1 Configuration JSON (`/configuration-json`)

Export/import de configuração completa:
- Modelos de time + metas
- Responsáveis + mapeamentos
- Assuntos + mapeamentos
- Filtros salvos (globais)

---

## 12. Agregações Estatísticas Derivadas

Além dos dados brutos, o sistema calcula:

### 12.1 Estatísticas Descritivas
- Média, mediana, desvio padrão de tempo de resolução
- Moda de assunto mais frequente
- Percentis (p25, p50, p75, p95)

### 12.2 Taxas
- Taxa de SLA compliance (%)
- Taxa de recorrência (%)
- Taxa de chegada (por hora/dia)
- Taxa de conclusão (throughput)

### 12.3 Tendências
- Slope (melhora/piora)
- Ciclos (semanal, mensal)
- Anomalias (desvio > 2σ)

### 12.4 Correlações
- Sujeito com maior tempo médio
- Regional com pior SLA
- Horário de pico
- Dia da semana com mais volume

---

## 13. Dimensões de Análise

Todas as métricas acima podem ser **cortadas por qualquer combinação de**:

| Dimensão | Valores | Exemplo |
|----------|---------|---------|
| **Regional** | ~15-20 regionais | JI PARANA, PORTO, GOIANIA |
| **Tipo O.S.** | ~10-20 tipos | Suporte, Instalação, Manutenção |
| **Assunto** | ~50-100 assuntos | Sem Conexão, Fatura, Hardware |
| **Diagnóstico** | ~30-50 diagnósticos | Rompimento, CTO Sem Sinal |
| **Status** | ~5-10 status | Aberta, Fechada, Pendente |
| **Setor IXC** | 1-21 setores | 7, 8, 9 (principais), ... |
| **Responsável** | ~50-200 responsáveis | João Silva, Maria Santos |
| **Pessoa** | 2 valores | Física, Jurídica |
| **Contrato** | ~20-50 tipos | PPP, Pessoa Física, Empresa |

---

## 14. Capacidades de Query Avançadas

### 14.1 Período Flexível
- Data fixa
- Intervalo (data_from / data_to)
- "Últimos N dias"
- Período fechado (mês/trimestre/ano)

### 14.2 Acesso Baseado em Roles

| Rol | Dados Vistos | Limitações |
|-----|--------------|-----------|
| Colaborador | Apenas suas O.S. | Sem acesso a OPA |
| Gestor Regional | Sua regional | Pode ver SLA/Calendário |
| Operador | Sua regional | Acesso total (menos admin) |
| Admin OPA | Todas regiões | Sem limitações |

### 14.3 Filtros Multinível

```
1. Selecionar regional(is)
2. Selecionar tipo(s)
3. Selecionar assunto(s)
4. Selecionar diagnóstico(s)
5. Resultado: apenas O.S. que combinam TODOS
```

Sem valores = assume ALL

---

## 15. Limites de Query

Para performance em 100k+ O.S.:

```
GET /orders
  max 50 dimensões por filtro
  max 200 O.S. por página
  timeout 30s
  sem wildcard (*) em search
```

```
GET /overview/control-tower
  max 5 níveis de drill-down
  agregação em cache (1 min)
  refresh manual via POST
```

---

## 16. Latência e Performance

### 16.1 Queries Rápidas (<100ms)
- `/filters` - cache estático, 5 min TTL
- `/data-freshness` - última importação
- `/calendar` - tabela agregada
- `/saved-filters` - índice por usuário

### 16.2 Queries Médias (100-500ms)
- `/overview` - full scan com índices
- `/sla/hierarchy` - joins + agg
- `/overview/trends` - série temporal
- `/in-progress` - WHERE is_closed=false

### 16.3 Queries Lentas (500ms-5s)
- `/control-tower` - 5-way agg
- `/overview/volume-alerts` - detecção anomalia
- `/calendar/month-detail` - full mês + drill
- Backfill import - 100k+ registros

---

## 17. Exemplo de Cenários de Uso

### Cenário 1: "Qual regional tem pior SLA?"
```
GET /sla/hierarchy?date_from=2026-08-01&date_to=2026-08-25
→ breakdown by regional
→ order by "outside_sla" DESC
→ resposta: PORTO (15% fora de SLA)
```

### Cenário 2: "Detectar anomalia em um assunto"
```
GET /overview/volume-alerts?date_from=2026-08-15&date_to=2026-08-25
→ filtra apenas HIGH severity
→ resposta: "Sem Conexão Fibra Rural" 4x acima do normal
```

### Cenário 3: "Comparar performance entre times"
```
GET /overview/work-schedule?model_ids=1,2,3
→ by_model array
→ resposta: Time A 15% fora turno, Time B 8% fora turno
```

### Cenário 4: "Prever quando esse ticket vai fechar"
```
GET /in-progress/sla-risk?regional=JI%20PARANA
+ histórico similar (GET /orders?os_subject=...)
→ calcular ETA baseado em tempo médio
→ resposta: "45 min de diferença até SLA bater"
```

---

## 18. Informações Não Disponíveis (Gaps)

O que o sistema **NÃO** consegue fazer hoje:

- ❌ Exportar para Excel diretamente (apenas JSON)
- ❌ Agendar relatórios automáticos
- ❌ Alertas push em tempo real
- ❌ Feedback do cliente (CSAT)
- ❌ Comparação O.S. atual vs. período anterior
- ❌ Previsão de demanda (forecasting)
- ❌ Análise de causa raiz automatizada
- ❌ Rastreamento de resolução por steps

---

## Conclusão

O módulo OPA extrai **50+ métricas distintas** a partir de **6 tabelas** e **30+ campos**, oferecendo visibilidade completa em 4 dimensões:

1. **Temporal** - Hoje vs. semana vs. mês
2. **Geográfica** - Por regional/cidade
3. **Operacional** - Por tipo/assunto/diagnóstico
4. **Pessoal** - Por responsável/colaborador

Com índices bem planejados, consegue responder qualquer pergunta sobre operação em <5s na escala de 100k+ O.S./mês.

