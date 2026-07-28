# Exemplos Práticos - Dados Extraíveis do Modo Analítico

## 📋 Índice
1. [Dados de Ordem Individual](#dados-de-ordem-individual)
2. [Agregações Simples](#agregações-simples)
3. [Análises Dimensionais](#análises-dimensionais)
4. [Séries Temporais](#séries-temporais)
5. [Indicadores de Risco](#indicadores-de-risco)
6. [Exemplos de Query (SQL)](#exemplos-de-query-sql)

---

## Dados de Ordem Individual

### 📌 Registro Completo de uma O.S.

**Exemplo de Resposta GET `/operations/orders/42`:**

```json
{
  "id": 42,
  "source": "ixc",
  "source_order_id": "OS-20260728-12345",
  "order_code": "12345",
  "protocol": "PROTO-789456",
  "contract_id": "CT001",
  "customer_id": "CUST-5000",
  "customer_login": "joao.silva",
  "customer_name": "João Silva Oliveira",
  "company_id": "EMP-001",
  "regional": "REGIONAL SUL",
  "state": "RS",
  "city": "Porto Alegre",
  "contract_type": "Residencial",
  "person_type": "Pessoa Física",
  "os_type": "INSTALAÇÃO CIDADE",
  "os_subject": "Internet",
  "diagnosis": "Primeira ativação",
  "department": "Suporte Externo",
  "sector": "7",
  "priority": "Normal",
  "creator": "ADMIN-AUTO",
  "responsible": "Técnico Silva",
  "responsible_ixc_id": 5432,
  "project": null,
  "pop": "POP Petrópolis",
  "status_code": "FIN",
  "status": "Finalizada",
  "is_closed": true,
  "is_internal": false,
  "sla_status": "on_time",
  "sla_target_hours": 24.0,
  "elapsed_hours": 18.5,
  "opened_at": "2026-07-27T10:30:00-04:00",
  "assumed_at": "2026-07-27T10:45:00-04:00",
  "displacement_started_at": "2026-07-27T11:00:00-04:00",
  "execution_started_at": "2026-07-27T11:15:00-04:00",
  "finished_at": "2026-07-27T18:30:00-04:00",
  "deadline_at": "2026-07-28T10:30:00-04:00",
  "scheduled_at": "2026-07-27T09:00:00-04:00",
  "closed_at": "2026-07-27T18:45:00-04:00",
  "source_updated_at": "2026-07-27T18:50:00-04:00",
  "first_imported_at": "2026-07-27T20:00:00Z",
  "last_imported_at": "2026-07-28T08:15:00Z",
  "service_address": "Rua das Flores, 123\nComplemento: Apto 456\nReferência: Próximo ao mercado",
  "service_description": "Instalação de internet banda larga",
  "technical_report": "Cliente ativado com sucesso. Velocidade testada: 300 Mbps"
}
```

---

### 🔍 Detalhe de Execução (Timeline)

**GET `/operations/orders/42/timeline`:**

```json
{
  "order_code": "12345",
  "status": "Finalizada",
  "timeline": [
    {
      "stage": "Abertura",
      "timestamp": "2026-07-27T10:30:00-04:00",
      "status": "Aberta",
      "description": "O.S. criada no sistema"
    },
    {
      "stage": "Atribuição",
      "timestamp": "2026-07-27T10:45:00-04:00",
      "status": "Assumida",
      "assignee": "Técnico Silva",
      "description": "O.S. atribuída a técnico"
    },
    {
      "stage": "Deslocamento",
      "timestamp": "2026-07-27T11:00:00-04:00",
      "duration_minutes": 15,
      "description": "Técnico em deslocamento para local"
    },
    {
      "stage": "Execução",
      "timestamp": "2026-07-27T11:15:00-04:00",
      "duration_minutes": 435,  // 7h15m
      "description": "Execução do trabalho iniciada"
    },
    {
      "stage": "Finalização",
      "timestamp": "2026-07-27T18:30:00-04:00",
      "status": "Concluída",
      "sla_status": "on_time",
      "description": "O.S. finalizada dentro do SLA"
    },
    {
      "stage": "Fechamento",
      "timestamp": "2026-07-27T18:45:00-04:00",
      "status": "Fechada",
      "description": "O.S. registrada como finalizada"
    }
  ],
  "total_cycle_minutes": 1095,  // 18h15m total
  "sla_target_hours": 24.0,
  "sla_status": "on_time",
  "efficiency_score": 0.92
}
```

---

## Agregações Simples

### 📊 Dashboard de Visão Geral (Período: Jul 2026)

**GET `/operations/overview?date_from=2026-07-01&date_to=2026-07-28`:**

```json
{
  "period": {
    "date_from": "2026-07-01",
    "date_to": "2026-07-28",
    "total_days": 28
  },
  "opened": 520,
  "opened_associated": 485,
  "responsible_filter_active": false,
  "completed": 485,
  "in_progress": 45,
  "opened_out_of_time": 65,
  "completed_on_time": 410,
  "completed_out_of_time": 75,
  "sla_rate": 0.845,
  "average_daily_opened": 18.6,
  "average_daily_completed": 17.3,
  "average_closing_hours": 28.4,
  "average_wait_to_displacement_minutes": 22.3,
  "average_cycle_minutes": 1680,  // 28h
  "data_freshness": {
    "last_import": "2026-07-28T08:15:00Z",
    "import_range": {
      "date_from": "2026-07-28",
      "date_to": "2026-07-28"
    }
  }
}
```

**Interpretação:**
- **SLA de 84.5%** (acima da meta de 80%)
- **Backlog de 45 O.S.** em andamento
- **Média de 28.4 horas** para fechamento (meta: 24h)
- **Dados atualizados** há minutos

---

### 📈 Tendência (Day/Week/Month)

**GET `/operations/trends?date_from=2026-07-01&date_to=2026-07-28&granularity=week`:**

```json
{
  "granularity": "week",
  "responsible_filter_active": false,
  "openings_ignore_responsibles": true,
  "points": [
    {
      "period_start": "2026-07-01",
      "period_end": "2026-07-07",
      "opened_operation": 145,
      "opened_associated": 130,
      "completed": 132,
      "completed_on_time": 112,
      "completed_out_of_time": 20,
      "completed_unmeasurable": 0,
      "sla_rate": 0.848,
      "sla_cumulative_rate": 0.848
    },
    {
      "period_start": "2026-07-08",
      "period_end": "2026-07-14",
      "opened_operation": 168,
      "opened_associated": 155,
      "completed": 151,
      "completed_on_time": 128,
      "completed_out_of_time": 23,
      "completed_unmeasurable": 0,
      "sla_rate": 0.848,
      "sla_cumulative_rate": 0.848
    },
    {
      "period_start": "2026-07-15",
      "period_end": "2026-07-21",
      "opened_operation": 152,
      "opened_associated": 140,
      "completed": 148,
      "completed_on_time": 126,
      "completed_out_of_time": 22,
      "completed_unmeasurable": 0,
      "sla_rate": 0.852,
      "sla_cumulative_rate": 0.849
    },
    {
      "period_start": "2026-07-22",
      "period_end": "2026-07-28",
      "opened_operation": 155,
      "opened_associated": 140,
      "completed": 154,
      "completed_on_time": 128,
      "completed_out_of_time": 26,
      "completed_unmeasurable": 0,
      "sla_rate": 0.831,
      "sla_cumulative_rate": 0.844
    }
  ]
}
```

**Análise:**
- Semana 1-3: SLA estável ~85%
- Semana 4: Leve queda para 83% (investigar causa)

---

## Análises Dimensionais

### 🏢 SLA por Regional

**GET `/operations/sla-hierarchy?dimension=regional`:**

```json
{
  "level": "regional",
  "total_completed": 485,
  "overall_sla_rate": 0.845,
  "items": [
    {
      "label": "REGIONAL SUL",
      "level": "regional",
      "completed": 185,
      "completed_on_time": 160,
      "sla_rate": 0.865,
      "sla_color": "green",
      "average_closing_hours": 26.2,
      "time_ranges": {
        "up_to_12h": {
          "count": 55,
          "percentage": 29.7
        },
        "12_to_24h": {
          "count": 105,
          "percentage": 56.8
        },
        "24_to_48h": {
          "count": 20,
          "percentage": 10.8
        },
        "48_to_72h": {
          "count": 4,
          "percentage": 2.2
        },
        "over_72h": {
          "count": 1,
          "percentage": 0.5
        }
      }
    },
    {
      "label": "REGIONAL NORTE",
      "level": "regional",
      "completed": 145,
      "completed_on_time": 121,
      "sla_rate": 0.834,
      "sla_color": "yellow",
      "average_closing_hours": 31.5,
      "time_ranges": {
        "up_to_12h": {
          "count": 35,
          "percentage": 24.1
        },
        "12_to_24h": {
          "count": 86,
          "percentage": 59.3
        },
        "24_to_48h": {
          "count": 18,
          "percentage": 12.4
        },
        "48_to_72h": {
          "count": 5,
          "percentage": 3.4
        },
        "over_72h": {
          "count": 1,
          "percentage": 0.7
        }
      }
    },
    {
      "label": "REGIONAL NORDESTE",
      "level": "regional",
      "completed": 155,
      "completed_on_time": 129,
      "sla_rate": 0.832,
      "sla_color": "yellow",
      "average_closing_hours": 29.8,
      "time_ranges": {
        "up_to_12h": {
          "count": 40,
          "percentage": 25.8
        },
        "12_to_24h": {
          "count": 89,
          "percentage": 57.4
        },
        "24_to_48h": {
          "count": 22,
          "percentage": 14.2
        },
        "48_to_72h": {
          "count": 3,
          "percentage": 1.9
        },
        "over_72h": {
          "count": 1,
          "percentage": 0.6
        }
      }
    }
  ]
}
```

---

### 💼 Desempenho Individual (Colaborador)

**GET `/operations/sla-by-collaborator?responsible_filter_active=false`:**

```json
{
  "items": [
    {
      "responsible": "Técnico Silva",
      "regional": "REGIONAL SUL",
      "team_model": {
        "id": 1,
        "name": "INSTALAÇÃO CIDADE",
        "daily_target": 5
      },
      "types_summary": [
        {
          "type": "INSTALAÇÃO CIDADE",
          "completed": 42
        },
        {
          "type": "SUPORTE TÉCNICO",
          "completed": 18
        },
        {
          "type": "OUTROS",
          "completed": 5
        }
      ],
      "completed": 65,
      "sla_rate": 0.892,
      "productive_days": 22,
      "average_daily": 2.95,
      "execution_time_minutes": {
        "average": 285,
        "median": 265,
        "minimum": 45,
        "maximum": 720
      },
      "execution_coverage_percentage": 98.5,
      "comments": "Desempenho excelente, acima da meta"
    },
    {
      "responsible": "Técnico Santos",
      "regional": "REGIONAL SUL",
      "team_model": {
        "id": 1,
        "name": "INSTALAÇÃO CIDADE",
        "daily_target": 5
      },
      "types_summary": [
        {
          "type": "INSTALAÇÃO CIDADE",
          "completed": 38
        },
        {
          "type": "SUPORTE TÉCNICO",
          "completed": 15
        },
        {
          "type": "OUTROS",
          "completed": 4
        }
      ],
      "completed": 57,
      "sla_rate": 0.851,
      "productive_days": 22,
      "average_daily": 2.59,
      "execution_time_minutes": {
        "average": 312,
        "median": 295,
        "minimum": 60,
        "maximum": 840
      },
      "execution_coverage_percentage": 96.5,
      "comments": "Desempenho bom, atende à meta"
    }
  ]
}
```

---

## Séries Temporais

### 📅 Calendário Mensal Operacional

**GET `/operations/calendar?competency=2026-07`:**

```json
{
  "competency": "2026-07",
  "date_from": "2026-07-01",
  "date_to": "2026-07-31",
  "timezone": "America/Porto_Velho",
  "group_by": "regional",
  "regional_summaries": [
    {
      "regional": "REGIONAL SUL",
      "completed_total": 185,
      "average_daily": 6.6,
      "completeness": 1.0,
      "days_with_data": 28,
      "collaborators": [
        {
          "responsible": "Técnico Silva",
          "daily_counts": [3, 2, 4, 3, 5, 2, 0, 4, 3, 5, 2, 4, 3, 2, 4, 3, 2, 5, 3, 4, 2, 3, 4, 0, 5, 3, 2, 4],
          "daily_performance": ["good", "median", "good", "good", "excellent", "median", "no_data", "good", "good", "excellent", "median", "good", "good", "median", "good", "good", "median", "excellent", "good", "good", "median", "good", "good", "no_data", "excellent", "good", "median", "good"],
          "monthly_performance": "excellent",
          "monthly_total": 65,
          "team_model": {
            "id": 1,
            "name": "INSTALAÇÃO CIDADE",
            "daily_target": 5
          }
        },
        {
          "responsible": "Técnico Santos",
          "daily_counts": [2, 3, 3, 2, 4, 1, 0, 3, 2, 4, 1, 3, 2, 3, 3, 2, 1, 4, 2, 3, 2, 2, 3, 0, 4, 2, 2, 3],
          "daily_performance": ["median", "good", "good", "median", "good", "below", "no_data", "good", "median", "good", "below", "good", "median", "good", "good", "median", "below", "good", "median", "good", "median", "median", "good", "no_data", "good", "median", "median", "good"],
          "monthly_performance": "good",
          "monthly_total": 57,
          "team_model": {
            "id": 1,
            "name": "INSTALAÇÃO CIDADE",
            "daily_target": 5
          }
        }
      ]
    }
  ]
}
```

---

### 📍 Detalhe de Dia Específico

**GET `/operations/calendar/day-detail?date=2026-07-28&regional=REGIONAL+SUL&responsible=Técnico+Silva`:**

```json
{
  "date": "2026-07-28",
  "weekday": "segunda",
  "responsible": "Técnico Silva",
  "regional": "REGIONAL SUL",
  "team_model": {
    "id": 1,
    "name": "INSTALAÇÃO CIDADE",
    "daily_target": 5
  },
  "metrics": {
    "completed": 4,
    "performance_band": "good",
    "performance_color": "#dcfce7",
    "execution_time_minutes": {
      "average": 285,
      "median": 275,
      "minimum": 120,
      "maximum": 480
    },
    "displacement_time_minutes": {
      "average": 18,
      "median": 15,
      "minimum": 5,
      "maximum": 45
    },
    "wait_to_displacement_minutes": {
      "average": 12,
      "median": 10,
      "minimum": 2,
      "maximum": 30
    },
    "total_cycle_minutes": {
      "average": 315,
      "median": 305,
      "minimum": 140,
      "maximum": 510
    },
    "sla_rate": 0.89,
    "first_execution_to_last_close_minutes": 1125  // 18h45m
  },
  "orders": [
    {
      "order_code": "12340",
      "customer_name": "Maria dos Santos",
      "os_type": "INSTALAÇÃO",
      "os_subject": "Internet",
      "status": "Finalizada",
      "sla_status": "on_time",
      "opened_at": "2026-07-27T15:30:00-04:00",
      "execution_started_at": "2026-07-28T08:15:00-04:00",
      "finished_at": "2026-07-28T10:45:00-04:00",
      "closed_at": "2026-07-28T11:00:00-04:00",
      "execution_minutes": 150,
      "cycle_minutes": 1050
    },
    {
      "order_code": "12341",
      "customer_name": "João Oliveira",
      "os_type": "INSTALAÇÃO",
      "os_subject": "Telefonia",
      "status": "Finalizada",
      "sla_status": "on_time",
      "opened_at": "2026-07-28T09:00:00-04:00",
      "execution_started_at": "2026-07-28T11:30:00-04:00",
      "finished_at": "2026-07-28T13:45:00-04:00",
      "closed_at": "2026-07-28T14:00:00-04:00",
      "execution_minutes": 135,
      "cycle_minutes": 300
    }
  ]
}
```

---

## Indicadores de Risco

### 🚨 Torre de Controle (Preventiva)

**GET `/operations/control-tower?reference_date=2026-07-28&recent_days=7&baseline_weeks=8`:**

```json
{
  "reference_date": "2026-07-28",
  "level": "subject",
  "recent_days": 7,
  "baseline_weeks": 8,
  "responsible_ignored": true,
  "calculation_note": "Compara últimos 7 dias contra mesmo período em 8 semanas anteriores, ignorando responsável para preservar equação entrada-saída",
  "summary": {
    "status": "attention",
    "opened_recent": 145,
    "expected_opened": 120.5,
    "deviation_percentage": 20.3,
    "completed_recent": 128,
    "net_flow": 17,
    "pressure_ratio": 1.13,
    "backlog": 45,
    "overdue_backlog": 8,
    "average_backlog_age_hours": 42.5,
    "persistent_days": 3,
    "critical_nodes": 0,
    "attention_nodes": 2,
    "reasons": [
      "Aberturas 20% acima do esperado (145 vs. 120.5)",
      "Pressão operacional elevada (1.13x)",
      "Backlog crescendo nos últimos 3 dias"
    ]
  },
  "timeline": [
    {
      "date": "2026-07-22",
      "opened": 18,
      "completed": 19,
      "expected_opened": 16.8,
      "upper_limit": 22.4,
      "outside_expected": false,
      "backlog": 42
    },
    {
      "date": "2026-07-23",
      "opened": 19,
      "completed": 18,
      "expected_opened": 17.2,
      "upper_limit": 23.1,
      "outside_expected": false,
      "backlog": 43
    },
    {
      "date": "2026-07-24",
      "opened": 24,
      "completed": 20,
      "expected_opened": 17.5,
      "upper_limit": 23.6,
      "outside_expected": true,  // ⚠️ Pico
      "backlog": 47
    },
    {
      "date": "2026-07-25",
      "opened": 22,
      "completed": 19,
      "expected_opened": 18.0,
      "upper_limit": 24.2,
      "outside_expected": false,
      "backlog": 50
    },
    {
      "date": "2026-07-26",
      "opened": 21,
      "completed": 21,
      "expected_opened": 18.5,
      "upper_limit": 24.9,
      "outside_expected": false,
      "backlog": 50
    },
    {
      "date": "2026-07-27",
      "opened": 23,
      "completed": 22,
      "expected_opened": 19.0,
      "upper_limit": 25.6,
      "outside_expected": false,
      "backlog": 51
    },
    {
      "date": "2026-07-28",
      "opened": 18,
      "completed": 28,
      "expected_opened": 19.5,
      "upper_limit": 26.3,
      "outside_expected": false,
      "backlog": 41
    }
  ],
  "items": [
    {
      "label": "Internet",
      "level": "subject",
      "path": {"subject": "Internet"},
      "opened_recent": 52,
      "expected_opened": 43.2,
      "deviation_percentage": 20.4,
      "completed_recent": 48,
      "net_flow": 4,
      "pressure_ratio": 1.08,
      "backlog": 18,
      "overdue_backlog": 3,
      "average_backlog_age_hours": 36.2,
      "persistent_days": 3,
      "status": "attention",
      "reasons": ["Volume acima do esperado"],
      "has_children": true
    },
    {
      "label": "Telefonia",
      "level": "subject",
      "path": {"subject": "Telefonia"},
      "opened_recent": 48,
      "expected_opened": 40.5,
      "deviation_percentage": 18.5,
      "completed_recent": 44,
      "net_flow": 4,
      "pressure_ratio": 1.09,
      "backlog": 15,
      "overdue_backlog": 2,
      "average_backlog_age_hours": 38.8,
      "persistent_days": 2,
      "status": "normal",
      "reasons": [],
      "has_children": true
    }
  ]
}
```

---

## Exemplos de Query (SQL)

### 🔍 SLA por Tipo Geral (Raw SQL)

```sql
SELECT
    os_type,
    COUNT(*) as completed,
    SUM(CASE WHEN sla_status = 'on_time' THEN 1 ELSE 0 END) as on_time,
    ROUND(
        100.0 * SUM(CASE WHEN sla_status = 'on_time' THEN 1 ELSE 0 END) / 
        COUNT(*),
        2
    ) as sla_percentage,
    ROUND(AVG(elapsed_hours), 2) as avg_hours
FROM operations_orders
WHERE
    closed_at >= '2026-07-01'::date
    AND closed_at < '2026-08-01'::date
    AND is_closed = TRUE
    AND elapsed_hours IS NOT NULL
GROUP BY os_type
ORDER BY completed DESC;
```

**Resultado Esperado:**
```
os_type                 | completed | on_time | sla_percentage | avg_hours
------------------------|-----------|---------|----------------|----------
INSTALAÇÃO CIDADE       |       185 |     160 |          86.49 |     26.20
SUPORTE TÉCNICO         |       145 |     121 |          83.45 |     31.50
SUPORTE MOTO            |        85 |       72 |          84.71 |     29.80
TÉCNICO 12/36H          |        70 |       57 |          81.43 |     34.20
```

---

### 📊 Desempenho Diário por Colaborador (Calendário)

```sql
SELECT
    DATE(closed_at AT TIME ZONE 'America/Porto_Velho') as work_date,
    responsible,
    regional,
    COUNT(*) as completed,
    SUM(CASE WHEN sla_status = 'on_time' THEN 1 ELSE 0 END) as on_time,
    ROUND(AVG(EXTRACT('epoch' FROM (finished_at - execution_started_at)) / 60)::numeric, 1) as avg_execution_minutes
FROM operations_orders
WHERE
    closed_at >= '2026-07-01 00:00:00-04:00'::timestamp with time zone
    AND closed_at < '2026-08-01 00:00:00-04:00'::timestamp with time zone
    AND is_closed = TRUE
    AND execution_started_at IS NOT NULL
    AND finished_at IS NOT NULL
GROUP BY
    DATE(closed_at AT TIME ZONE 'America/Porto_Velho'),
    responsible,
    regional
ORDER BY work_date DESC, regional, responsible;
```

**Resultado Esperado:**
```
work_date  | responsible      | regional          | completed | on_time | avg_execution_minutes
-----------|------------------|-------------------|-----------|---------|---------------------
2026-07-28 | Técnico Silva    | REGIONAL SUL      |         4 |       4 |               285.0
2026-07-28 | Técnico Santos   | REGIONAL SUL      |         3 |       2 |               312.5
2026-07-27 | Técnico Silva    | REGIONAL SUL      |         5 |       5 |               278.0
2026-07-27 | Técnico Santos   | REGIONAL SUL      |         4 |       3 |               325.0
```

---

### ⚠️ Backlog Envelhecido (Aging)

```sql
SELECT
    os_type,
    os_subject,
    regional,
    CASE
        WHEN EXTRACT('days' FROM (NOW() - opened_at AT TIME ZONE 'America/Porto_Velho')) <= 1 THEN '0-1 dia'
        WHEN EXTRACT('days' FROM (NOW() - opened_at AT TIME ZONE 'America/Porto_Velho')) <= 3 THEN '2-3 dias'
        WHEN EXTRACT('days' FROM (NOW() - opened_at AT TIME ZONE 'America/Porto_Velho')) <= 7 THEN '4-7 dias'
        ELSE '8+ dias'
    END as age_bucket,
    COUNT(*) as quantity
FROM operations_orders
WHERE
    is_closed = FALSE
    AND opened_at IS NOT NULL
GROUP BY os_type, os_subject, regional, age_bucket
ORDER BY quantity DESC;
```

**Resultado Esperado:**
```
os_type        | os_subject | regional          | age_bucket | quantity
----------------|------------|-------------------|------------|----------
INSTALAÇÃO      | Internet   | REGIONAL NORTE    | 0-1 dia    |       12
SUPORTE TÉCNICO | Internet   | REGIONAL NORTE    | 2-3 dias   |        8
SUPORTE TÉCNICO | Telefonia  | REGIONAL SUL      | 4-7 dias   |        5
INSTALAÇÃO      | Telefonia  | REGIONAL NORDESTE | 8+ dias    |        3
```

---

### 🎯 Taxa de Pressão por Assunto (últimos 7 dias)

```sql
WITH daily_flow AS (
    SELECT
        os_subject,
        DATE(opened_at AT TIME ZONE 'America/Porto_Velho') as open_date,
        COUNT(*) as opened
    FROM operations_orders
    WHERE opened_at >= NOW() - INTERVAL '7 days'
    GROUP BY os_subject, open_date
),
daily_completion AS (
    SELECT
        os_subject,
        DATE(closed_at AT TIME ZONE 'America/Porto_Velho') as close_date,
        COUNT(*) as completed
    FROM operations_orders
    WHERE closed_at >= NOW() - INTERVAL '7 days'
        AND is_closed = TRUE
    GROUP BY os_subject, close_date
)
SELECT
    COALESCE(d.os_subject, c.os_subject) as os_subject,
    SUM(COALESCE(d.opened, 0)) as total_opened,
    SUM(COALESCE(c.completed, 0)) as total_completed,
    ROUND(
        100.0 * (SUM(COALESCE(d.opened, 0)) - SUM(COALESCE(c.completed, 0))) /
        NULLIF(SUM(COALESCE(d.opened, 0)), 0),
        2
    ) as net_flow_percentage,
    CASE
        WHEN SUM(COALESCE(c.completed, 0)) = 0 THEN NULL
        ELSE ROUND(
            SUM(COALESCE(d.opened, 0))::numeric / 
            SUM(COALESCE(c.completed, 0)),
            2
        )
    END as pressure_ratio
FROM daily_flow d
FULL OUTER JOIN daily_completion c 
    ON d.os_subject = c.os_subject
GROUP BY os_subject
ORDER BY pressure_ratio DESC NULLS LAST;
```

**Resultado Esperado:**
```
os_subject  | total_opened | total_completed | net_flow_percentage | pressure_ratio
----------------|--------------|-----------------|---------------------|---------------
Internet        |           52 |              48 |                8.33 |           1.08
Telefonia       |           48 |              44 |                9.09 |           1.09
Suporte Fibra   |           28 |              32 |               -12.50 |           0.88
Dados/Conectiv. |           17 |              20 |               -15.00 |           0.85
```

---

## Resumo de Dados Extraíveis

| Categoria | Tipo | Exemplo |
|-----------|------|---------|
| **Individual** | O.S. completa | 40+ campos + timeline |
| **Agregado Simples** | Dashboard | 12 métricas principais |
| **Série Temporal** | Day/Week/Month | SLA, volume, flow |
| **Dimensonal** | Breakdown por 20+ dimensões | SLA por tipo/regional/responsável |
| **Indicador** | KPI/Métrica | SLA rate, pressão, backlog aging |
| **Risco** | Monitoramento preventivo | Torre de Controle com drill-down |
| **Drill-through** | Detalhamento | Do agregado para lista de O.S. |

**Total de Combinações Possíveis:** 10.000+ análises diferentes, derivadas de ~500 O.S./mês
