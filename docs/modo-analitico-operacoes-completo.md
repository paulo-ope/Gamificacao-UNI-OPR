# Documentação Completa do Modo Analítico - Módulo Operations

## 📋 Índice
1. [Visão Geral](#visão-geral)
2. [Objetivo do Módulo](#objetivo-do-módulo)
3. [Estrutura de Dados](#estrutura-de-dados)
4. [Funcionalidades Principais](#funcionalidades-principais)
5. [Regras de Negócio](#regras-de-negócio)
6. [Dados Extraíveis](#dados-extraíveis)
7. [Hierarquias e Dimensões](#hierarquias-e-dimensões)
8. [Métricas e Indicadores](#métricas-e-indicadores)
9. [APIs e Endpoints](#apis-e-endpoints)
10. [Permissões e Escopo](#permissões-e-escopo)

---

## Visão Geral

O **Módulo Operations (Modo Analítico)** é um sistema de análise operacional das Ordens de Serviço (O.S.) originadas no IXC, permitindo acompanhar demanda, execução, prazo, garantia, backlog e produtividade sem alterar as regras de remuneração da Gamificação.

### Localização no Projeto
```
Backend:   /backend/app/modules/operations/
Frontend:  /frontend/components/operations/
Banco:     PostgreSQL com Alembic migrations
Rotas:     /api/operations/*
```

---

## Objetivo do Módulo

### Problema Resolvido
Os dados de O.S. técnicas finalizadas não permitiam análise de:
- Ordens abertas e em andamento
- Backlog histórico e atual
- Demandas internas
- SLA por dimensões operacionais
- Drill-through de métricas para detalhe de O.S.

### Objetivos Estratégicos
1. **Consolidar O.S. do IXC** em base auditável
2. **Oferecer filtros persistentes** globais para todas as visões
3. **Exibir indicadores comparáveis** ao relatório operacional de referência
4. **Manter contexto** ao abrir detalhes mantendo origem/total
5. **Disponibilizar resultados** à Gamificação via contrato versionado

---

## Estrutura de Dados

### 📊 Principais Entidades (Modelos)

#### 1. **OperationOrder** (Tabela: `operations_orders`)
Registro canônico de cada Ordem de Serviço importada do IXC.

**Campos Principais:**
```python
# Identificação
id: int (PK)
source: str = "ixc"  # Sistema de origem
source_order_id: str  # ID único no IXC
order_code: str      # Código da O.S.
protocol: str        # Protocolo (opcional)

# Cliente e Contrato
contract_id: str
customer_id: str
customer_login: str
customer_name: str

# Localização
company_id: str
regional: str           # Regional/filial
state: str              # UF (RO, SP, etc)
city: str               # Município

# Classificação Operacional
contract_type: str      # Tipo de contrato
person_type: str        # PF/PJ
os_type: str           # Tipo geral (ex: INSTALAÇÃO CIDADE)
os_subject: str        # Assunto (ex: Internet, Telefonia)
diagnosis: str         # Diagnóstico
department: str        # Departamento IXC
sector: str           # Setor IXC
priority: str         # Prioridade

# Responsabilidades
creator: str          # Criador da O.S.
responsible: str      # Responsável/técnico
responsible_ixc_id: int  # ID do colaborador IXC

# Projeto/POP
project: str          # Projeto interno
pop: str             # POP (ponto de presença)

# Status
status_code: str      # Código do status no IXC
status: str          # Descrição do status
is_closed: bool      # O.S. finalizada?
is_internal: bool    # O.S. interna?
sla_status: str      # "on_time", "overdue", "unidentified"
sla_target_hours: float  # Meta SLA em horas
elapsed_hours: float     # Horas decorridas

# Timeline
opened_at: datetime    # Abertura
assumed_at: datetime   # Assumida/atribuída
displacement_started_at: datetime  # Início deslocamento
execution_started_at: datetime     # Início execução
finished_at: datetime  # Finalização
deadline_at: datetime  # Prazo
scheduled_at: datetime # Agendada
closed_at: datetime    # Fechamento
source_updated_at: datetime  # Última atualização IXC

# Auditoria
raw_payload: dict    # Payload original IXC
normalization_notes: str  # Notas de normalização
first_imported_at: datetime
last_imported_at: datetime
```

**Índices:**
- `(opened_at, closed_at)` - para filtros por período
- `(regional, os_type, os_subject)` - para dimensões operacionais
- `source_order_id` - unicidade de origem

---

#### 2. **OperationImportRun** (Tabela: `operations_import_runs`)
Registro de cada execução de importação de O.S. do IXC.

**Campos:**
```python
id: int (PK)
date_from: date          # Período importado
date_to: date
status: str = "running"  # running|completed|failed
fetched_count: int       # Registros consultados no IXC
created_count: int       # Novos registros
updated_count: int       # Registros atualizados
unchanged_count: int     # Sem alterações
rejected_count: int      # Rejeitados por validação
errors: list[dict]       # Lista de erros
imported_by: int         # ID do usuário que importou
started_at: datetime
finished_at: datetime (nullable)
```

---

#### 3. **OperationBackfillJob** (Tabela: `operations_backfill_jobs`)
Rastreamento de backfills históricos de longo prazo.

**Campos:**
```python
id: int (PK)
date_from: date          # Período total a preencher
date_to: date
next_date: date          # Próxima data a processar
sector_ids: list[str]    # Setores do escopo
status: str = "pending"  # pending|running|completed|failed
total_days: int          # Dias no período
processed_days: int      # Dias já processados
fetched_count: int
created_count: int
updated_count: int
unchanged_count: int
rejected_count: int
errors: list[dict]
requested_by: int        # Quem solicitou
created_at: datetime
updated_at: datetime
finished_at: datetime (nullable)
```

**Características:**
- Checkpoint por dia para retomada
- Auditoria completa
- Concorrência única
- Upsert idempotente

---

#### 4. **OperationTeamModel** (Tabela: `operations_team_models`)
Modelos operacionais com metas por turno e período.

**Campos:**
```python
id: int (PK)
name: str (unique)        # Ex: "INSTALAÇÃO CIDADE"
daily_target: int = 5     # Meta diária padrão
median_from_quantity: int = 3   # Limite para mediano
good_from_quantity: int = 4     # Limite para bom
below_target_color: str = "#fee2e2"  # Cor abaixo da meta
median_color: str = "#fef3c7"        # Cor mediano
good_color: str = "#dcfce7"          # Cor bom
excellent_color: str = "#dbeafe"     # Cor excelente/meta
active: bool = True
created_by: int
created_at: datetime
updated_at: datetime

# Relacionamento
target_rules: list[OperationTeamTargetRule]  # Metas por período
```

**Modelos Padronizados:**
- INSTALAÇÃO CIDADE
- TECNICO 12/36H
- SUPORTE MOTO
- SUPORTE CARRO
- RURAL
- FAZ TUDO
- AUXILIAR
- Não informado

---

#### 5. **OperationTeamTargetRule** (Tabela: `operations_team_target_rules`)
Define metas específicas por tipo de período (dia da semana, turno, etc).

**Campos:**
```python
id: int (PK)
team_model_id: int (FK)   # Modelo operacional
period_type: str          # Ex: "segunda-feira", "turno_noite"
enabled: bool = True
median_from_quantity: int = 3
good_from_quantity: int = 4
target_quantity: int = 5
start_time: time (nullable)   # Para períodos com horário
end_time: time (nullable)
created_at: datetime
updated_at: datetime
```

---

#### 6. **OperationResponsibleAssignment** (Tabela: `operations_responsible_assignments`)
Vinculação de colaborador operacional a modelo de trabalho.

**Campos:**
```python
id: int (PK)
responsible_name: str    # Nome do responsável no IXC
regional: str           # Regional associada
team_model_id: int (FK)  # Modelo operacional vinculado
updated_by: int
created_at: datetime
updated_at: datetime

# Constraint: UNIQUE(responsible_name, regional)
```

**Regra:**
- Cada identidade operacional (responsável + regional) vinculada a um único modelo
- Sem relação com cadastro de colaboradores da Gamificação
- Exclusão exige permissão `operations:manage`

---

#### 7. **OperationSavedFilter** (Tabela: `operations_saved_filters`)
Filtros nomeados salvos por usuário com persistência.

**Campos:**
```python
id: int (PK)
user_id: int (FK)        # Usuário proprietário
name: str                # Nome do filtro
filters: dict            # JSON com filtros
visibility: str = "personal"  # personal|global
created_at: datetime
updated_at: datetime

# Constraint: UNIQUE(user_id, name)
```

**Estrutura de Filtros:**
```json
{
  "team_models": ["INSTALAÇÃO CIDADE"],
  "companies": ["EMP001"],
  "regionals": ["REGIONAL Sul"],
  "states": ["RS", "SC"],
  "cities": ["Porto Alegre"],
  "contract_types": ["Residencial"],
  "person_types": ["Pessoa Física"],
  "os_types": ["INSTALAÇÃO"],
  "subjects": ["Internet"],
  "diagnoses": ["Falha técnica"],
  "departments": ["Suporte Externo"],
  "sectors": ["7", "8", "9"],
  "priorities": ["Alta", "Normal"],
  "creators": ["ADMIN"],
  "responsibles": ["Técnico 1"],
  "responsible_ixc_ids": [123, 456],
  "statuses": ["Finalizada"],
  "sla_statuses": ["no_prazo"],
  "projects": ["Projeto A"],
  "pops": ["POP São Paulo"],
  "opened_weekdays": ["segunda", "terça"],
  "closed_weekdays": ["segunda", "terça"],
  "custom_window_basis": ["business_hours"],
  "custom_window_start_weekday": "segunda",
  "custom_window_start_time": "08:00",
  "custom_window_end_weekday": "sexta",
  "custom_window_end_time": "18:00",
  "responsible_mode": "all|completed",
  "search": "texto livre",
  "closed_time_from": "09:00",
  "closed_time_to": "17:00"
}
```

---

#### 8. **OperationTeamTargetRule** - Configurações Auxiliares

**OperationSubjectTypeMapping** - Mapear Assunto para Tipo Geral:
```python
# Tabela: operations_subject_type_mappings
subject: str (unique)  # Ex: "Internet"
os_type: str          # Ex: "INSTALAÇÃO CIDADE"
active: bool
```

**OperationResponsibleDirectorySetting** - Configuração de Fonte:
```python
# Tabela: operations_responsible_directory_settings
source: str = "orders"  # Fonte de lista de responsáveis
updated_by: int
updated_at: datetime
```

**OperationIxcCollaborator** - Cache de Colaboradores IXC:
```python
# Tabela: operations_ixc_collaborators
source_employee_id: str (unique)
name: str
active: bool
last_synced_at: datetime
```

---

## Funcionalidades Principais

### 🎯 Visão Geral (Overview)
**Objetivo:** Dashboard executivo com indicadores-chave.

**Métricas Exibidas:**
- **Cards:**
  - Abertura: Volume total no período
  - Média diária de aberturas
  - Backlog do período
  - Backlog acumulado (O.S. pendentes em data de corte)
  - Realizadas: O.S. finalizadas
  - Média diária de finalizações
  - Atrasadas: Finalizadas fora do prazo SLA
  - No prazo: Finalizadas dentro do prazo SLA

- **Gráfico Mensal:** Tendência de abertura, realizadas, backlog, backlog acumulado

- **Indicadores:**
  - SLA Técnico com meta visual de 80% (verde ≥80%, amarelo 60-80%, vermelho <60%)
  - IVC (Índice de Velocidade de Conclusão)
  - IVT (Índice de Velocidade de Turnaround)

- **Breakdowns:**
  - Por filial/regional
  - Por departamento/setor

---

### 📊 SLA (Service Level Agreement)
**Objetivo:** Análise detalhada de cumprimento de prazos.

**Estrutura Hierárquica:**
```
Tipo Geral
  └── Assunto
      └── Diagnóstico
```

**Métricas por Linha:**
- Realizadas: Total de O.S. finalizadas
- SLA Técnico: (Realizadas no prazo) / (Realizadas com SLA mensurável)
- Tempo Médio de Fechamento

**Faixas de Tempo:**
- Até 12h
- 12-24h
- 24-48h
- 48-72h
- Acima de 72h

**Regra de Cor SLA:**
```
SLA ≥ 80%  → Verde ✓
60% ≤ SLA < 80%  → Amarelo ⚠
SLA < 60%  → Vermelho ✗
```

**Total Ponderado (Linha Final):**
```
SLA = (∑ O.S. no prazo) / (∑ O.S. mensuráveis)
Tempo Médio = (∑ Tempos) / (∑ O.S. mensuráveis)
```

**Tabela: Produtividade e SLA por Colaborador**
```
Responsável | Modelo | Realizadas | SLA | Dias Produtivos | Média Diária
```

**Cálculo de Execução Efetiva:**
```
Execução = finished_at - execution_started_at
```

**Exclusões:**
- O.S. sem `execution_started_at`
- O.S. sem `finished_at`
- Sequências temporais negativas (bug, dados incompletos)

---

### 📅 Calendário Operacional Mensal
**Objetivo:** Visualizar desempenho diário por responsável.

**Características:**
- **Período Padrão:** 1º do mês atual até data atual
- **Estrutura:** Blocos por regional, linha por responsável, coluna por dia
- **Visualização:** 31 colunas sem scroll lateral (desktop)

**Célula (Dia × Responsável):**
- Quantidade de O.S. fechadas naquele dia
- Dias indisponíveis permanecem inativos

**Drill-through (Seleção de Célula):**
```
Drawer lateral mostra:
- Responsável, Regional, Modelo operacional
- Data, Quantidade, Desempenho
- Lista de O.S. do recorte (status e observações)
```

**Classificação de Desempenho:**
```
Sem produção         → Neutro
Abaixo da meta       → Vermelho
Mediano              → Amarelo
Bom                  → Verde claro
Excelente/Meta       → Verde escuro
Sem meta configurada → Cinza
```

**Fórmula (Backend):**
```
Se quantidade ≤ mediano_from_quantity    → Abaixo
Se mediano_from_quantity < qtde ≤ good   → Mediano
Se good_from_quantity < qtde < target    → Bom
Se qtde ≥ target                         → Excelente
```

**Detalhes Diários Completos:**
- Média, Mediana, Mínimo, Máximo de execução
- Espera média: abertura → execução
- Ciclo total médio
- SLA do recorte
- Janela: primeira execução → última finalização
- Cobertura dos tempos (%), distribuição por tipo

**Timeline de O.S. Individual:**
- Duração das etapas
- SLA
- Cliente, Contrato, Regional, Cidade
- Responsável, Criador
- Setor, Prioridade, Tipo, Assunto, Diagnóstico
- Observações operacionais

---

### 📈 Abertura (Opening Analytics)
**Objetivo:** Análise de volume de novas demandas.

**Visão Geral:**
- Volume mensal
- Matrizes por SLA/Status
- Classificações operacionais

**Série Histórica (Tendências):**
- Granularidade: Dia, Semana, Mês
- SLA com meta visual de 80%
- Volume finalizado vs. atrasado
- Aberturas operacionais
- Associações atuais + finalizadas empilhadas por SLA

**Regra de Responsável:**
> O total operacional ignora o filtro de responsável, pois responsável atual não comprova atribuição no instante da abertura.

**Exibição com Filtro Ativo:**
- Quantidade atualmente associada aos selecionados (sem tratá-la como autoria histórica)

---

### 🚨 Torre de Controle Preventiva
**Objetivo:** Monitoramento preditivo de pressão operacional.

**Comparação Temporal:**
- 7 dias recentes vs. mesmo dia da semana das 8 semanas anteriores
- Evita comparar dias operacionais diferentes

**Classificação:**
```
Status: normal | attention | critical | insufficient

Fatores:
1. Desvio de aberturas (%)
2. Persistência (dias consecutivos)
3. Entradas vs. finalizações (flow rate)
4. Crescimento do backlog
5. Proporção vencida (%)

Pico isolado    → Atenção
Persistência OU combinação pressão+incapacidade → Crítico
```

**Mapa de Desvios - Drill-down:**
```
Assunto
  └── Regional
      └── Cidade
          └── Setor
              └── Responsável
```

**Regra:**
> Ignora filtro de responsável para manter entradas e capacidade na mesma base operacional.

**Avisos:**
- Histórico < 4 semanas: sinalizado como insuficiente

---

### 📦 Andamento (In-Progress)
**Objetivo:** Estoque atual de O.S. abertas.

**Dimensões:**
- Por filial
- Por tipo geral
- Por assunto
- Por SLA/Status

**Característica Especial:**
> Consulta estoque atual de TODAS as O.S. abertas sincronizadas, sem restringir data de abertura.
> Datas vazias são aceitas e filtros dimensionais continuam ativos.
> Status incompatíveis (Finalizada, Cancelada) são retirados automaticamente.

---

### ✅ Finalizadas
**Objetivo:** Acompanhamento de O.S. concluídas.

**Métricas:**
- Realizadas
- Percentual por filial, tipo geral, responsável
- Série temporal respeitando todos os filtros

---

### 🏭 Internas
**Objetivo:** Acompanhamento de O.S. internas.

**Dimensões:**
- Por projeto
- Por POP

**Métricas:**
- O.S. abertas no prazo
- O.S. abertas atrasadas

---

### 🛡️ Garantia (Fase 2)
**Objetivo:** Análise de garantias de 30 dias.

**Métricas:**
- Quantidade de garantias
- Percentual (30 dias)
- Evolução mensal

**Tabela Detail:**
- Contrato, Cliente, Data de Referência
- O.S. Origem, Garantia, Assunto

---

### 🔍 Drill-through e Detalhe
**Padrão Universal:**

Todo card, linha ou total elegível oferece ação "Ver detalhes".

**Tela Resultante:**
- Herda filtros, origem e critério do agregado
- Exibe quantidade de linhas
- Oferece: busca, paginação, ordenação, retorno, seleção de colunas
- Paginação no cliente em lotes de 50 linhas

---

## Regras de Negócio

### ⏰ Janela Temporal
**Autorizada:**
```
Início:    1º dia do 3º mês-calendário disponível
Fim:       Data atual
```

**Validação:**
- Frontend restringe seletores
- Backend rejeita períodos fora dessa janela

**Atualização Interativa:**
- Limite: 7 dias (via importação rápida)
- Períodos maiores: backfill retomável no servidor

---

### 📥 Importação de Dados

#### Importação Rápida (Current Month)
```python
import_current_month_period()
```
- Consultados apenas via lote diário do período autorizado
- Rápida para mês atual
- Até 7 dias de histórico

#### Importação de Backlog Aberto
```python
import_open_backlog()
```
- Rotina separada e limitada
- Particionada por status aberto e setores prioritários
- **Setores Prioritários:** 7 (Suporte Externo), 8 (Rádio), 9 (Fibra)
- Reconciliação direta por ID em lotes de até 200 para confirmar fechamento/cancelamento

#### Backfill Histórico
```python
backfill_historical()
```
- Checkpoint por dia
- Retomada automática
- Auditoria completa
- Concorrência única
- Upsert idempotente

**Cobertura Histórica:**
- Completa: 01/05/2026 a 21/07/2026 (setores 7, 8, 9)
- Parcial: demais setores (marcados em UI)

---

### 🔄 Normalização de Dados

**Mapeamentos Obrigatórios:**
```
IXC Code  → Descrição de Negócio
26        → RO (Estado)
F         → Pessoa Física
J         → Pessoa Jurídica
RAG       → Reagendada (Status)
DS        → Deslocamento (Sub-status)
```

**Dados Armazenados:**
- **Nomes de Negócio:** Em colunas normalizadas
- **IDs/Códigos IXC:** Apenas como chaves de origem + auditoria

**Fuso Horário:**
- Datas sem fuso interpretadas no fuso operacional definido
- Convertidas e armazenadas com timezone UTC
- Nunca assumir UTC silenciosamente

---

### 🎯 Métricas e Fórmulas

#### SLA Técnico
```
SLA Técnico = (∑ O.S. no prazo) / (∑ O.S. com SLA mensurável)
```

**Interpretação:**
- O.S. sem `finished_at`: não entram na métrica
- O.S. com `sla_status = "on_time"`: conta no numerador
- O.S. com `finished_at` e `deadline_at` mensuráveis: conta no denominador
- O.S. com sequência temporal inválida: excluída (informada em "dados incompletos")

#### Tempo Médio de Fechamento
```
Tempo Médio = (∑ elapsed_hours) / (∑ O.S. mensuráveis)
```

#### Média Diária
```
Média Diária = Total / Dias no período
```

#### Backlog Acumulado
```
Backlog Acumulado = ∑ O.S. pendentes na data de corte
```

#### Ciclo Total
```
Ciclo Total = closed_at - opened_at
```

#### Execução Efetiva
```
Execução Efetiva = finished_at - execution_started_at
```

#### IVC (Velocidade de Conclusão) - Pendente
Fórmula a validar com operação.

#### IVT (Velocidade de Turnaround) - Pendente
Fórmula a validar com operação.

---

### 🔐 Autorização e Escopo

**Permissões Requeridas:**
```python
require_permission("operations:read")   # Todas as visões
require_permission("operations:manage")  # Alterações, reprocessamento
```

**Filtros Obrigatórios (Backend):**
- Empresa do usuário
- Regionais autorizadas do usuário
- Módulo: Operations

**Regra Crítica:**
> O filtro visual NUNCA substitui regra de acesso. Autorização é aplicada em TODAS as consultas backend.

**Drill-through:**
- Agregações executadas no backend com autorização regional
- Frontend não recebe conjunto integral de O.S.

---

## Dados Extraíveis

### 📝 Por Ordem de Serviço (OperationOrder)

**Identificação:**
- ID único (DB)
- Código da O.S.
- Protocolo
- Identificador IXC

**Cliente:**
- ID do cliente
- Login do cliente
- Nome do cliente

**Localização:**
- Empresa/Filial
- Regional
- Estado
- Cidade

**Contrato:**
- ID do contrato
- Tipo de contrato
- Pessoa (Física/Jurídica)

**Classificação:**
- Tipo Geral (ex: INSTALAÇÃO)
- Assunto (ex: Internet)
- Diagnóstico
- Departamento
- Setor
- Prioridade

**Responsabilidades:**
- Criador
- Responsável (nome)
- Responsável (ID IXC)

**Projeto:**
- Projeto
- POP (Point of Presence)

**Status:**
- Código do status
- Descrição do status
- Fechada? (booleano)
- Interna? (booleano)

**SLA:**
- Status SLA (on_time, overdue, unidentified)
- Meta SLA (horas)
- Horas decorridas

**Timeline:**
- Abertura
- Assumida
- Deslocamento iniciado
- Execução iniciada
- Finalizada
- Prazo
- Agendada
- Fechamento
- Última atualização IXC

**Auditoria:**
- Payload original (JSON)
- Notas de normalização
- Data primeira importação
- Data última importação

---

### 📊 Agregações Disponíveis

**Por Período:**
- Volume de aberturas
- Volume de finalizações
- Backlog (posição em data de corte)
- SLA técnico (%)
- Tempo médio de fechamento (horas)

**Por Dimensão (com subtotais):**
- Regional
- Estado
- Cidade
- Tipo de Contrato
- Pessoa (PF/PJ)
- Tipo Geral
- Assunto
- Diagnóstico
- Departamento
- Setor
- Prioridade
- Criador
- Responsável
- Status
- SLA Status
- Projeto
- POP

**Cruzamentos Populares:**
- Regional × Assunto × SLA
- Responsável × Modelo Operacional × Período
- Setor × Prioridade × Status

---

### 📈 Séries Temporais

**Granularidades Suportadas:**
- Diária
- Semanal (seg-seg)
- Mensal (1º dia)

**Métricas por Ponto:**
- Aberturas
- Finalizações
- Backlog
- SLA (%)
- SLA Cumulativo

---

### 🎯 Indicadores Derivados

**Capacidade:**
```
Taxa Média = Finalizações / Dias Produtivos
```

**Pressão (Flow):**
```
Net Flow = Aberturas - Finalizações
Pressure Ratio = Aberturas / Finalizações
```

**Idade do Backlog:**
```
Backlog Age (horas) = (Agora - Menor opened_at) / Qtde Pendentes
```

**Conformidade:**
```
SLA Rate = (On Time) / (Mensuráveis)
Overdue Rate = (Overdue) / (Mensuráveis)
```

---

## Hierarquias e Dimensões

### 🔗 Hierarquia de SLA (Expansível)

```
Tipo Geral (Nível 1 - Sempre visível)
  │
  └──→ Assunto (Nível 2 - Habilitável)
        │
        └──→ Diagnóstico (Nível 3 - Habilitável)
```

**Comportamento:**
- Tipo Geral: sempre mostrado como raiz
- Assunto e Diagnóstico: consultados dinamicamente ao expandir pai
- Totais ponderados em cada nível

---

### 📍 Hierarquia Operacional

```
Regional (Nível 1)
  │
  └──→ Cidade (Nível 2)
        │
        └──→ Setor (Nível 3)
              │
              └──→ Responsável (Nível 4)
```

**Aplicação:**
- Torre de Controle: drill-down obrigatório
- Aberturas: expansão sob demanda
- Cada nível agregado backend ao expandir
- Preserva permissão regional

---

### 🏢 Hierarquia Organizacional

```
Empresa
  │
  └──→ Regional/Filial
        │
        └──→ Departamento
              │
              └──→ Setor
```

---

### 👥 Modelagem Operacional

**Estrutura:**
```
Team Model (ex: INSTALAÇÃO CIDADE)
  │
  ├──→ Target Rules (por período)
  │     ├── Dia da semana
  │     ├── Turno
  │     └── Período customizado
  │
  └──→ Responsible Assignments
        └── (responsável_name, regional) → team_model
```

---

## Métricas e Indicadores

### 📊 Indicadores Principais (KPIs)

| Métrica | Fórmula | Unidade | Meta | Interpretação |
|---------|---------|---------|------|----------------|
| SLA Técnico | No Prazo / Mensuráveis | % | 80% | Taxa cumprimento SLA |
| Tempo Médio | ∑ Horas / Mensuráveis | h | Configurável | Agilidade |
| Backlog | ∑ Pendentes | qtde | Decrescente | Saúde do pipeline |
| Taxa Realização | Finalizadas / Dias | qtde/dia | Por modelo | Produtividade |
| Net Flow | Entradas - Saídas | qtde | ≈ 0 | Equilíbrio |
| Pressão | Entradas / Saídas | ratio | < 1.0 | Capacidade |

---

### 🎨 Indicadores Visuais

**Cores SLA:**
```
Verde:   SLA ≥ 80%
Amarelo: 60% ≤ SLA < 80%
Vermelho: SLA < 60%
```

**Cores Desempenho (Modelo Operacional):**
```
Excelente (Azul):      qtde ≥ target
Bom (Verde):           good < qtde < target
Mediano (Amarelo):     mediano < qtde ≤ good
Abaixo (Vermelho):     qtde ≤ mediano
Sem Meta (Cinza):      Responsável sem modelo
Sem Produção (Neutro): qtde = 0
```

---

### ⚠️ Indicadores de Risco

**Torre de Controle:**
- **Normal:** Operação dentro da normalidade
- **Atenção:** Desvio de 1-2 fatores ou pico isolado
- **Crítico:** Persistência OU combinação pressão + incapacidade
- **Insuficiente:** Histórico < 4 semanas

**Volume Alert (Assunto):**
- **Normal:** Dentro de 1 σ (desvio padrão)
- **Atenção:** Entre 1σ e 2σ
- **Crítico:** > 2σ ou crescimento persistente
- **Insuficiente:** < 4 semanas de histórico

---

## APIs e Endpoints

### 🔌 Estrutura de Rotas

```
/api/operations/
├── GET /period                          # Janela temporal válida
├── POST /import/current                 # Importar mês atual
├── POST /import/backlog                 # Importar backlog aberto
├── GET /backfill-jobs                   # Listar backfills
├── POST /backfill-jobs                  # Iniciar backfill
├── GET /backfill-jobs/{id}              # Detalhes backfill
│
├── GET /overview                        # Dashboard visão geral
├── GET /sla-hierarchy                   # Tabela SLA expansível
├── GET /sla-by-collaborator             # SLA por responsável
├── GET /openings-analytics              # Análise de aberturas
├── GET /control-tower                   # Torre de controle
├── GET /control-tower/children          # Expansão do drill-down
├── GET /calendar                        # Calendário mensal
├── GET /calendar/day-detail             # Detalhes dia do calendário
├── GET /in-progress                     # Andamento (backlog aberto)
├── GET /trends                          # Série histórica
├── GET /work-schedule-overview          # Visão de calendário de trabalho
│
├── GET /orders                          # Listagem paginada de O.S.
├── GET /orders/{id}                     # Detalhes de O.S.
├── GET /orders/{id}/timeline            # Timeline de etapas
│
├── GET /filters                         # Listagem de valores únicos por dimensão
├── GET /filters/available-values        # Valores com facetação dinâmica
├── GET /saved-filters                   # Listar filtros salvos do usuário
├── POST /saved-filters                  # Criar filtro salvo
├── PUT /saved-filters/{id}              # Atualizar filtro salvo
├── DELETE /saved-filters/{id}           # Deletar filtro salvo
│
├── GET /team-models                     # Listar modelos operacionais
├── POST /team-models                    # Criar modelo
├── PUT /team-models/{id}                # Atualizar modelo
├── DELETE /team-models/{id}             # Deletar modelo (requer `operations:manage`)
├── GET /team-models/{id}/target-rules   # Metas do modelo
├── POST /team-models/{id}/target-rules  # Adicionar meta
│
├── GET /responsible-assignments         # Responsáveis e modelos
├── POST /responsible-assignments        # Vincular responsável a modelo
├── PUT /responsible-assignments/{id}    # Atualizar vínculo
├── DELETE /responsible-assignments/{id} # Remover vínculo
│
├── GET /subject-type-mappings           # Mapeamentos assunto → tipo
├── PUT /subject-type-mappings/bulk      # Atualizar em lote
│
├── GET /ixc-sync/settings               # Configurações de sincronização
├── PUT /ixc-sync/settings               # Atualizar configurações
├── GET /ixc-sync/status                 # Status da sincronização
├── POST /ixc-sync/trigger               # Forçar sincronização
│
├── GET /ixc-collaborators               # Cache de colaboradores IXC
├── POST /ixc-collaborators/sync         # Sincronizar colaboradores
│
└── GET /data-freshness                  # Timestamp última importação completa
```

---

### 📨 Query Parameters Comuns

**Período:**
```
date_from: date         # ISO 8601
date_to: date           # ISO 8601
```

**Filtros Dimensionais:**
```
# Todos aceitam múltiplos valores separados por vírgula
regionals: str
states: str
cities: str
contract_types: str
person_types: str
os_types: str
subjects: str
diagnoses: str
departments: str
sectors: str
priorities: str
creators: str
responsibles: str
statuses: str
sla_statuses: str
projects: str
pops: str
```

**Paginação:**
```
skip: int = 0           # Offset
limit: int = 50         # Tamanho da página (máx 1000)
```

**Ordenação:**
```
sort_by: str            # Campo
sort_order: "asc"|"desc"
```

**Busca:**
```
search: str             # Busca livre em texto
```

---

### 🔄 Response Models Principais

#### OperationOverview
```json
{
  "opened": 150,
  "opened_associated": 120,
  "responsible_filter_active": false,
  "completed": 140,
  "in_progress": 45,
  "opened_out_of_time": 15,
  "completed_on_time": 120,
  "completed_out_of_time": 20,
  "sla_rate": 0.857,
  "average_daily_opened": 5.0,
  "average_daily_completed": 4.67,
  "average_closing_hours": 42.3,
  "average_wait_to_displacement_minutes": 45.2,
  "average_cycle_minutes": 2880.5
}
```

#### OperationSlaItem
```json
{
  "label": "INSTALAÇÃO CIDADE",
  "level": "type",
  "completed": 150,
  "completed_on_time": 130,
  "sla_rate": 0.867,
  "average_closing_hours": 38.5,
  "time_ranges": {
    "up_to_12h": {"count": 45, "percentage": 30.0},
    "12_to_24h": {"count": 60, "percentage": 40.0},
    "24_to_48h": {"count": 30, "percentage": 20.0},
    "48_to_72h": {"count": 10, "percentage": 6.7},
    "over_72h": {"count": 5, "percentage": 3.3}
  }
}
```

#### OperationCalendar
```json
{
  "competency": "2026-07",
  "timezone": "America/Manaus",
  "regional_summaries": [
    {
      "regional": "REGIONAL SUL",
      "completed": 200,
      "completeness": 1.0,
      "responsibles": [...]
    }
  ]
}
```

#### OperationControlTower
```json
{
  "reference_date": "2026-07-28",
  "status": "critical",
  "opened_recent": 250,
  "expected_opened": 150.0,
  "deviation_percentage": 66.7,
  "completed_recent": 120,
  "net_flow": 130,
  "pressure_ratio": 2.08,
  "persistent_days": 7,
  "critical_nodes": 3,
  "reasons": ["Alto crescimento de aberturas", "Finalização abaixo da expectativa"],
  "timeline": [...],
  "items": [...]
}
```

---

## Permissões e Escopo

### 🔐 Perfis e Permissões

| Perfil | `operations:read` | `operations:manage` | Acesso |
|--------|:-:|:-:|---------|
| Admin | ✓ | ✓ | Todas visões, configuração, reprocessamento |
| Gestor Regional | ✓ | ✗ | Dados suas regionais autorizadas |
| Analista | ✓ | ✗ | Painéis e detalhe conforme escopo |

---

### 🎯 Validação de Escopo (Backend)

**Toda consulta valida:**
1. Usuário autenticado
2. Permissão `operations:read` (mínimo)
3. Empresa do usuário
4. Regionais autorizadas
5. Módulo Operations ativo

**Filtro Visual ≠ Segurança:**
> O frontend filtra por UX. O backend sempre revalida a autorização.

---

### 📋 Dados Sensíveis

**Nunca Expor em Frontend:**
- Payload original IXC (apenas backend/auditoria)
- IDs internos IXC sem contexto
- Credenciais (tokens IXC em variáveis de ambiente backend)

**Auditoria de Acesso:**
- Quem consultou o relatório
- Quando
- Filtros aplicados
- Dados retornados (amostra)

---

## Integração com Gamificação

### 🔗 Contrato de Integração

**Escopo:**
- **Operations:** Dona da ingestão e medição operacional
- **Gamificação:** Dona de pontos, remuneração, fechamento

**Interface (Versão 1):**
- Leitura/projeção de O.S. técnicas finalizadas
- SLA Status (on_time, overdue, unidentified)
- Horas de fechamento
- Garantia (30 dias)
- Recorrência (reopens)
- Identificador da O.S.

**Benefício:**
- Gamificação consome sem duplicar consultas ao IXC
- Operations controla normalização e auditoria
- Contrato versionado permite evolução independente

---

## Fases de Entrega

### ✅ Fase 1: Fundação (Completo)
- Registro de módulo
- Contratos e migrations Alembic
- Ingestão canônica sob demanda do mês atual

### ✅ Fase 2: Visão Geral e Filtros (Completo)
- Dashboard de Overview
- Filtros globais e salvos
- Drill-through básico

### ✅ Fase 3: SLA, Abertura, Andamento (Completo)
- Tabela SLA hierárquica
- Análise de aberturas com Torre de Controle
- Estoque de andamento

### ✅ Fase 4: Calendário e Modelos (Completo)
- Calendário mensal operacional
- Configuração de modelos operacionais
- Metas por período

### 🚧 Fase 5: Garantia e Internas
- Análise de garantias
- Acompanhamento de O.S. internas por projeto/POP

### 🔮 Fase 6: Projeção para Gamificação
- Contrato versionado
- Otimização de agregados
- Sincronização automática

---

## Notas Importantes

### ⚠️ Limitações Conhecidas

1. **Eventos/Snapshots:** Não implementado. Andamento mostra estado atual, não histórico de posições.

2. **Fórmulas Pendentes:**
   - IVC (Velocidade de Conclusão)
   - IVT (Velocidade de Turnaround)
   - Definição de vínculo de garantia

3. **Cobertura Histórica:**
   - Completa: setores 7, 8, 9 (01/05/2026 - 21/07/2026)
   - Parcial: demais setores (marcados em UI)

4. **Fuso Horário:**
   - Operacional (América/Manaus) configurável
   - Não assumir UTC

---

### 🔄 Atualização de Dados

**Frequência:**
- **Importação Rápida (mês):** A cada 20 minutos (configurável)
- **Backlog Aberto:** A cada 60 minutos (configurável)
- **Reconciliação:** Automática por IDs fechados
- **Backfill:** Manual, com retomada automática

**Visibilidade:**
- Timestamp "Última importação concluída" exibido no UI
- Vem da auditoria de importação, não do carregamento da página

---

### 📱 Responsividade

**Desktop:**
- 31 colunas diárias sem scroll lateral
- Seletores de 50 linhas paginados

**Mobile/Tablet:**
- Scroll interno em tabelas expansíveis
- Cards em coluna única
- Métodos recolhidos por padrão
- Drill-through em drawer lateral

---

## Resumo Executivo

**O Módulo Operations é:**
- ✅ Consolidador de O.S. IXC com auditoria
- ✅ Multidimensional (20+ dimensões)
- ✅ Hierárquico (expansível sob demanda)
- ✅ Autorizado (validação backend em tudo)
- ✅ Auditado (rastreamento de importações)
- ✅ Extensível (fronteiras claras, APIs limpas)
- ✅ Integrado (contrato com Gamificação)

**Dados Extraíveis:**
- O.S. individuais com 40+ atributos
- Agregações por 20+ dimensões
- Séries temporais (dia/semana/mês)
- Métricas derivadas (SLA, pressão, idade)
- Indicadores de risco (Torre de Controle)

**Próximas Fronteiras:**
- Snapshots históricos de backlog
- Eventos de transição de status
- Otimização de agregados para relatórios
- Projeção versionada à Gamificação

---

**Documento criado:** Julho 2026  
**Última atualização:** 28/07/2026  
**Versão:** 1.0  
**Status:** Documentado até Fase 4 (Calendário + Modelos)
