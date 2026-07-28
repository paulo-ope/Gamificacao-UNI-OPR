# Especificações Técnicas Detalhadas - Módulo Operations (Modo Analítico)

## 📚 Índice
1. [Algoritmos de Cálculo](#algoritmos-de-cálculo)
2. [Transformações de Dados](#transformações-de-dados)
3. [Validações e Regras](#validações-e-regras)
4. [Padrões de Query](#padrões-de-query)
5. [Performance e Indexação](#performance-e-indexação)
6. [Tratamento de Erros](#tratamento-de-erros)

---

## Algoritmos de Cálculo

### 🔢 Cálculo de SLA Técnico

**Definição:**
```
SLA Técnico = (Ordens no prazo) / (Ordens mensuráveis)
```

**Implementação (queries.py):**
```python
# Condições de inclusão
on_time = (
    OperationOrder.sla_status == "on_time"
    AND OperationOrder.is_closed == True
    AND OperationOrder.closed_at IS NOT NULL
)

measurable = (
    OperationOrder.elapsed_hours IS NOT NULL
    AND OperationOrder.sla_target_hours IS NOT NULL
    AND OperationOrder.closed_at IS NOT NULL
)

sla_rate = (
    func.count(func.if_(on_time, 1)) / 
    func.count(func.if_(measurable, 1))
)
```

**Interpretação:**
- **Numerador:** COUNT WHERE sla_status='on_time' AND is_closed=TRUE
- **Denominador:** COUNT WHERE elapsed_hours IS NOT NULL AND sla_target_hours IS NOT NULL
- **Casos especiais:**
  - Denominador = 0 → SLA rate é NULL (não mensurável)
  - Seq. temporal inválida (finished_at < execution_started_at) → excluída
  - SLA unknown → não conta em nenhuma categoria

**Visualização (UI):**
```
Verde:   SLA ≥ 80% ✓
Amarelo: 60% ≤ SLA < 80% ⚠
Vermelho: SLA < 60% ✗
Cinza:   Não mensurável (0 denominador)
```

---

### ⏱️ Tempo Médio de Fechamento

**Fórmula:**
```
Tempo Médio = (∑ elapsed_hours) / (COUNT mensuráveis)
```

**Implementação:**
```python
elapsed_hours_sum = func.sum(
    func.if_(
        (OperationOrder.elapsed_hours.isnot(None)) &
        (OperationOrder.sla_target_hours.isnot(None)),
        OperationOrder.elapsed_hours,
        0
    )
)
measurable_count = func.count(
    func.if_(
        (OperationOrder.elapsed_hours.isnot(None)) &
        (OperationOrder.sla_target_hours.isnot(None)),
        1
    )
)
avg_closing_hours = elapsed_hours_sum / func.greatest(measurable_count, 1)
```

**Dados Fonte:**
- `OperationOrder.elapsed_hours` calculado como:
  ```
  elapsed_hours = (closed_at - opened_at).total_seconds() / 3600
  ```

**Casos Especiais:**
- NULL se nenhuma O.S. mensurável no período
- Não inclui O.S. ainda em execução (finished_at NULL)

---

### 📊 Tempo de Execução Efetiva (Colaborador)

**Fórmula (Tabela SLA por Colaborador):**
```
Execução Efetiva = finished_at - execution_started_at
Tempo Médio de Exec. = (∑ Exec. Efetiva) / (COUNT com execução)
```

**Implementação:**
```python
execution_time = (
    func.extract('epoch', OperationOrder.finished_at - 
                          OperationOrder.execution_started_at) / 60  # minutos
)

avg_execution_minutes = func.avg(
    func.if_(
        (OperationOrder.execution_started_at.isnot(None)) &
        (OperationOrder.finished_at.isnot(None)),
        execution_time
    )
)

min_execution = func.min(
    func.if_(
        (OperationOrder.execution_started_at.isnot(None)) &
        (OperationOrder.finished_at.isnot(None)),
        execution_time
    )
)

max_execution = func.max(
    func.if_(
        (OperationOrder.execution_started_at.isnot(None)) &
        (OperationOrder.finished_at.isnot(None)),
        execution_time
    )
)
```

**Estatísticas Retornadas:**
- Média
- Mediana (percentil 50)
- Mínimo
- Máximo

---

### 🎯 Classificação de Desempenho Diário

**Algoritmo (services.py):**
```python
def classify_daily_performance(
    quantity: int,
    team_model: OperationTeamModel,
    period_type: str  # "monday", "saturday", "monthly"
) -> PerformanceBand:
    """
    Classifica desempenho diário baseado em quantidade vs. metas.
    
    Retorna: "excellent" | "good" | "median" | "below" | "neutral" | "no_data"
    """
    
    # 1. Buscar regra específica para o período
    target_rule = next(
        (r for r in team_model.target_rules if r.period_type == period_type),
        None
    )
    
    if not target_rule:
        return "neutral"  # Modelo sem regra para este período
    
    if not target_rule.enabled:
        return "neutral"
    
    # 2. Classificar contra limiares
    if quantity == 0:
        return "neutral"  # Sem atividade
    
    if quantity <= target_rule.median_from_quantity:
        return "below"
    
    if quantity <= target_rule.good_from_quantity:
        return "median"
    
    if quantity < target_rule.target_quantity:
        return "good"
    
    return "excellent"
```

**Cores Associadas (HEX):**
```python
bands_colors = {
    "excellent": team_model.excellent_color,      # Default: #dbeafe (azul)
    "good": team_model.good_color,                # Default: #dcfce7 (verde)
    "median": team_model.median_color,            # Default: #fef3c7 (amarelo)
    "below": team_model.below_target_color,       # Default: #fee2e2 (vermelho)
    "neutral": "#d1d5db",                         # Cinza
    "no_data": "#f3f4f6"                          # Cinza claro
}
```

**Período Type Mapeamento:**
```python
period_type_map = {
    0: "monday",
    1: "tuesday",
    2: "wednesday",
    3: "thursday",
    4: "friday",
    5: "saturday",
    6: "sunday",
    "monthly": "monthly"  # Agregado mensal
}
```

---

### 📈 Desempenho Esperado (Control Tower)

**Fórmula Baseline:**
```
Expected = Média(mesmo dia semana em últimas 8 semanas)
Upper Limit = max(
    Expected + 2 * StdDev,
    Expected * 1.35,
    Expected + 2
)
Deviation% = ((Atual - Expected) / Expected) * 100
```

**Implementação (queries.py):**
```python
def _compute_baseline_for_date(target_date: date, baseline_weeks: int = 8) -> tuple[float, float]:
    """
    Calcula esperado e upper_limit comparando com mesmo dia da semana
    nas últimas N semanas, ignorando dados incompletos.
    """
    same_weekday_dates = [
        target_date - timedelta(weeks=w)
        for w in range(1, baseline_weeks + 1)
    ]
    
    # Query: SUM(opened) WHERE date IN same_weekday_dates AND filters
    values = db.query(
        func.sum(OperationOrder.id).filter(
            OperationOrder.opened_at.cast(Date).in_(same_weekday_dates)
        )
    ).scalars()
    
    baseline = np.mean(values) if values else 0
    std_dev = np.std(values) if len(values) > 1 else 0
    
    upper_limit = max(
        baseline + 2 * std_dev,
        baseline * 1.35,
        baseline + 2
    )
    
    return baseline, upper_limit
```

**Interpretação:**
- Esperado = baseline histórico (mesmo dia da semana)
- Upper Limit = gatilho de alerta (1.35x ou +2σ)
- Desvio% = (atual - esperado) / esperado

**Status Control Tower:**
```
Se deviation% > 50% E persistence >= 7 dias:
    status = "critical"  ← Pressão persistente
Else Se deviation% >= 25% OU backlog_crescente:
    status = "attention"
Else:
    status = "normal"
```

---

### 🔍 Janela Customizada (Custom Time Window)

**Suporta:**
```python
custom_window = {
    "basis": ["business_hours"],  # ou "all_hours"
    "start_weekday": "segunda",
    "start_time": "08:00",        # HH:MM
    "end_weekday": "sexta",
    "end_time": "18:00"
}
```

**Lógica de Cálculo (queries.py):**
```python
def _is_within_custom_window(
    timestamp: datetime,
    window: CustomWindowDefinition,
    timezone: str = "America/Porto_Velho"
) -> bool:
    # Converter para timezone local
    local_dt = timestamp.astimezone(pytz.timezone(timezone))
    local_weekday = local_dt.strftime("%A").lower()  # 'monday', 'tuesday', etc
    local_time = local_dt.time()
    
    # Suporta wrap: sexta 18:00 → segunda 08:00 (continuidade noite/dia)
    if window.end_weekday >= window.start_weekday:
        # Sem wrap
        weekday_ok = (
            weekday_to_num[window.start_weekday] <= weekday_to_num[local_weekday] <=
            weekday_to_num[window.end_weekday]
        )
    else:
        # Com wrap (e.g., sexta → segunda)
        weekday_ok = (
            weekday_to_num[local_weekday] >= weekday_to_num[window.start_weekday]
            OR weekday_to_num[local_weekday] <= weekday_to_num[window.end_weekday]
        )
    
    if not weekday_ok:
        return False
    
    # Validar horário
    start_time = time.fromisoformat(window.start_time)
    end_time = time.fromisoformat(window.end_time)
    
    return start_time <= local_time <= end_time
```

---

## Transformações de Dados

### 🔄 Normalização de Campos

**Tabela de Mapeamentos (DB):**
```python
OperationSubjectTypeMapping:
    subject: "Internet" → os_type: "INSTALAÇÃO CIDADE"
    subject: "Telefonia" → os_type: "SUPORTE TÉCNICO"
    subject: "WiFi" → os_type: "SUPORTE TÉCNICO"
```

**Aplicação (IXC Ingestion):**
```python
def normalize_subject(raw_subject: str) -> tuple[str, str]:
    """
    Retorna (normalized_subject, os_type) usando mapeamento.
    """
    mapping = db.query(OperationSubjectTypeMapping).filter_by(
        subject=raw_subject.strip(),
        active=True
    ).first()
    
    if mapping:
        return raw_subject, mapping.os_type
    
    return raw_subject, "Não classificado"
```

**Campos Sempre Normalizados:**
| IXC Raw | Descrição | Campo DB |
|---------|-----------|----------|
| 26 | Estado RO | state |
| F | Pessoa Física | person_type |
| J | Pessoa Jurídica | person_type |
| DS | Deslocamento | status_code |
| RAG | Reagendada | status_code |

---

### 🌍 Conversão de Timezone

**Configuração:**
```python
OPERATIONS_TIMEZONE_NAME = "America/Porto_Velho"  # UTC-4 (sem DST)
```

**Padrão de Conversão:**
```python
def to_local_timezone(utc_dt: datetime, tz_name: str = OPERATIONS_TIMEZONE_NAME) -> datetime:
    """Converte datetime UTC para timezone local."""
    utc_dt = utc_dt.replace(tzinfo=pytz.UTC) if utc_dt.tzinfo is None else utc_dt
    local_tz = pytz.timezone(tz_name)
    return utc_dt.astimezone(local_tz)

def to_local_date(utc_dt: datetime, tz_name: str = OPERATIONS_TIMEZONE_NAME) -> date:
    """Extrai data LOCAL (não UTC)."""
    return to_local_timezone(utc_dt, tz_name).date()

def to_local_hour(utc_dt: datetime, tz_name: str = OPERATIONS_TIMEZONE_NAME) -> int:
    """Extrai hora LOCAL (0-23)."""
    return to_local_timezone(utc_dt, tz_name).hour

def to_local_weekday(utc_dt: datetime, tz_name: str = OPERATIONS_TIMEZONE_NAME) -> str:
    """Retorna dia da semana em português."""
    local_dt = to_local_timezone(utc_dt, tz_name)
    weekday_names = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    return weekday_names[local_dt.weekday()]
```

**Exemplo:**
```
UTC:    2026-07-28 04:30:00+00:00
Local:  2026-07-28 00:30:00-04:00  (Porto Velho)
Date:   2026-07-28
Hour:   00 (madrugada)
Weekday: terça
```

---

### 📦 Agregação de Payload JSON

**Dados Armazenados Crus (raw_payload):**
```json
{
  "id_os": "12345",
  "data_hora_execucao": "2026-07-28 14:30:00",
  "data_inicio": "2026-07-28 14:00:00",
  "data_final": "2026-07-28 18:45:00",
  "data_fechamento": "2026-07-28 19:00:00",
  "endereco_os": "Rua das Flores, 123",
  "complemento_endereco": "Apto 456",
  "referencia_endereco": "Próximo ao mercado",
  "descricao_problema": "Internet não conecta",
  "solucao": "Reconfiguração do roteador",
  "observacoes": "Cliente reclamava de lentidão"
}
```

**Extração (schemas.py):**
```python
def _text_from_payload(payload: dict, *keys: str) -> str | None:
    """Tenta extrair valor de múltiplas chaves (fallback)."""
    if not payload:
        return None
    for key in keys:
        value = payload.get(key)
        if value:
            return str(value).strip() or None
    return None

def _service_address_from_payload(payload: dict) -> str:
    """Monta endereço completo do JSON bruto."""
    address = _text_from_payload(payload, "endereco", "endereco_os", "endereco_cliente")
    complement = _text_from_payload(payload, "complemento", "complemento_endereco")
    reference = _text_from_payload(payload, "referencia", "ponto_referencia")
    
    parts = []
    if address:
        parts.append(address)
    if complement and complement.casefold() not in (address or "").casefold():
        parts.append(f"Complemento: {complement}")
    if reference and reference.casefold() not in (address or "").casefold():
        parts.append(f"Referência: {reference}")
    
    return "\n".join(parts) or None
```

---

## Validações e Regras

### ✅ Validações de Período

**Regra Geral:**
```python
allowed_from: date = date(2026, 5, 1)  # 1º disponível + 3 meses atrás
allowed_to: date = today()

def validate_operations_period(date_from: date, date_to: date):
    """Valida janela temporal."""
    
    # 1. Ordem cronológica
    assert date_from <= date_to, "date_from deve ser ≤ date_to"
    
    # 2. Dentro da janela autorizada
    assert date_from >= ALLOWED_FROM, f"date_from antes de {ALLOWED_FROM}"
    assert date_to <= today(), "date_to não pode ser no futuro"
    
    # 3. Máximo de dias por tipo de requisição
    delta = (date_to - date_from).days
    if delta <= 7:
        # Importação rápida (allowed)
        pass
    else:
        # Backfill (requer background job)
        assert background_job_supported, "Períodos > 7 dias exigem backfill"
```

**Aplicação (router.py):**
```python
@router.get("/operations/period")
def get_operations_period() -> OperationPeriod:
    """Retorna janela válida para UI."""
    return OperationPeriod(
        date_from=ALLOWED_FROM,
        date_to=today(),
        allowed_from=ALLOWED_FROM,
        allowed_to=today(),
        timezone=OPERATIONS_TIMEZONE_NAME
    )
```

---

### 🔒 Validações de Segurança

**Escopo Regional (Obrigatório em Todas Queries):**
```python
def add_regional_scope(
    query: Select,
    user: User,
    operations_module: Module
) -> Select:
    """
    Filtra por regionais do usuário.
    Nunca confia em parametro do cliente para definir escopo.
    """
    
    # 1. Buscar regionais autorizadas do usuário
    user_managed_regionals = (
        db.query(UserModuleScope.region)
        .filter(
            UserModuleScope.user_id == user.id,
            UserModuleScope.module_id == operations_module.id
        )
        .all()
    )
    
    if not user_managed_regionals:
        # User sem acesso → retorna vazio
        return query.where(OperationOrder.regional == "INVALID_REGION")
    
    # 2. Aplicar na query
    return query.filter(
        OperationOrder.regional.in_(user_managed_regionals)
    )
```

**Permissões Requeridas:**
```python
@router.get("/operations/overview")
@require_permission("operations:read")  # Decorator obrigatório
def get_overview(
    filters: OperationFilters = Depends(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> OperationOverview:
    # Backend sempre revalida:
    user_permissions = permissions_for_user(user.id, db)
    if "operations:read" not in user_permissions:
        raise HTTPException(status_code=403, detail="Sem permissão")
    
    # Aplica escopo regional ANTES de consultar
    query = add_regional_scope(query, user, operations_module)
    
    # ... resto da lógica
```

---

### 🛡️ Validações de Dados

**Sequência Temporal:**
```python
def validate_order_timestamps(order: OperationOrder) -> list[str]:
    """Retorna lista de problemas encontrados."""
    
    issues = []
    
    # 1. Abertura é obrigatória
    if not order.opened_at:
        issues.append("opened_at is required")
    
    # 2. Sequência esperada
    timeline = [
        ("opened", order.opened_at),
        ("assumed", order.assumed_at),
        ("displacement_started", order.displacement_started_at),
        ("execution_started", order.execution_started_at),
        ("finished", order.finished_at),
        ("closed", order.closed_at),
    ]
    
    prev_name, prev_dt = None, None
    for name, dt in timeline:
        if dt is None:
            continue
        
        if prev_dt and dt < prev_dt:
            issues.append(f"{name} ({dt}) before {prev_name} ({prev_dt})")
        
        prev_name, prev_dt = name, dt
    
    return issues
```

**Aplicação (ixc_ingestion.py):**
```python
def ingest_order(raw_order: dict) -> tuple[OperationOrder | None, list[str]]:
    """Ingere ordem ou retorna erro."""
    
    # Parse de campos
    order = OperationOrder(...)
    
    # Validar
    issues = validate_order_timestamps(order)
    
    if issues:
        return None, issues
    
    # Persistir
    db.add(order)
    db.commit()
    
    return order, []
```

---

## Padrões de Query

### 📊 Agregação Multidimensional

**Padrão Genérico:**
```python
def aggregate_by_dimension(
    dimension: str,  # "regional" | "os_type" | "responsible" | ...
    date_from: date,
    date_to: date,
    extra_filters: dict = None
) -> list[dict]:
    """
    Agrupa por dimensão, retorna volume/SLA/tempo_médio por valor.
    """
    
    query = (
        db.query(
            getattr(OperationOrder, dimension),  # Coluna dinâmica
            func.count(OperationOrder.id).label("total"),
            func.count(func.if_(
                OperationOrder.sla_status == "on_time", 1
            )).label("on_time"),
            func.avg(
                func.if_(
                    OperationOrder.elapsed_hours.isnot(None),
                    OperationOrder.elapsed_hours
                )
            ).label("avg_hours")
        )
        .filter(
            OperationOrder.closed_at >= date_from,
            OperationOrder.closed_at <= date_to,
            OperationOrder.is_closed == True
        )
    )
    
    # Aplicar filtros adicionais
    if extra_filters:
        for col, values in extra_filters.items():
            query = query.filter(getattr(OperationOrder, col).in_(values))
    
    # Agrupar e ordenar
    query = query.group_by(dimension).order_by(desc("total"))
    
    return query.all()
```

**Uso:**
```python
# SLA por regional
sla_by_regional = aggregate_by_dimension(
    dimension="regional",
    date_from=date(2026, 7, 1),
    date_to=date(2026, 7, 28),
    extra_filters={"sector": ["7", "8", "9"]}
)

# Resultado:
# [
#   {regional: "REGIONAL SUL", total: 250, on_time: 210, avg_hours: 38.5},
#   {regional: "REGIONAL NORTE", total: 180, on_time: 144, avg_hours: 42.2},
# ]
```

---

### 🏆 Ranking com Limite

**Padrão:**
```python
def ranking_by_dimension(
    dimension: str,
    metric: str,  # "total" | "avg_hours" | "sla_rate"
    limit: int = 20,
    ascending: bool = False
) -> list[dict]:
    """
    Top/Bottom N por métrica.
    """
    
    query = aggregate_by_dimension(dimension=dimension)
    
    # Ordenar por métrica
    order_col = getattr(OperationOrder, metric)
    query = query.order_by(
        asc(order_col) if ascending else desc(order_col)
    ).limit(limit)
    
    return query.all()
```

**Aplicação (Control Tower):**
```python
# Top 10 assuntos com maior desvio (ranking por pressão)
top_subjects_by_deviation = ranking_by_dimension(
    dimension="os_subject",
    metric="deviation_percentage",
    limit=10,
    ascending=False  # Maior primeiro
)
```

---

### 🔗 Operações de Join

**Padrão com Team Model:**
```python
def collaborator_performance(
    responsible_name: str,
    regional: str,
    date_from: date,
    date_to: date
) -> dict:
    """
    Retorna performance do colaborador + modelo aplicável.
    """
    
    # 1. Buscar vínculo colaborador → modelo
    assignment = db.query(OperationResponsibleAssignment).filter(
        OperationResponsibleAssignment.responsible_name == responsible_name,
        OperationResponsibleAssignment.regional == regional
    ).first()
    
    team_model = assignment.team_model if assignment else None
    
    # 2. Agregar performance do colaborador
    perf = db.query(
        func.count(OperationOrder.id).label("completed"),
        func.count(func.if_(
            OperationOrder.sla_status == "on_time", 1
        )).label("on_time"),
        func.avg(
            func.extract('epoch', OperationOrder.finished_at - 
                                  OperationOrder.execution_started_at) / 60
        ).label("execution_minutes")
    ).filter(
        OperationOrder.responsible == responsible_name,
        OperationOrder.regional == regional,
        OperationOrder.closed_at >= date_from,
        OperationOrder.closed_at <= date_to
    ).first()
    
    return {
        "responsible": responsible_name,
        "regional": regional,
        "team_model": team_model,
        "completed": perf.completed,
        "sla_rate": perf.on_time / perf.completed if perf.completed else None,
        "execution_minutes": perf.execution_minutes
    }
```

---

## Performance e Indexação

### 🚀 Índices Otimizados

**Estratégia de Index:**
```python
# Índice composto para filtros temporais
Index("ix_operations_orders_opened_closed", 
      OperationOrder.opened_at, OperationOrder.closed_at)

# Índice para dimensões operacionais comuns
Index("ix_operations_orders_dimensions",
      OperationOrder.regional, OperationOrder.os_type, OperationOrder.os_subject)

# Índices simples para filtros únicos
OperationOrder.source_order_id (unique)
OperationOrder.responsible
OperationOrder.creator
OperationOrder.status_code
OperationOrder.sla_status
OperationOrder.is_closed
```

**Recomendações:**
```sql
-- Para queries de visão geral (período + filtros)
CREATE INDEX CONCURRENTLY idx_ops_period_dims
ON operations_orders (opened_at, closed_at, regional, os_type, is_closed);

-- Para drill-down de responsável
CREATE INDEX CONCURRENTLY idx_ops_responsible_regional
ON operations_orders (responsible, regional, opened_at);

-- Para agregações de calendário (performance crítica)
CREATE INDEX CONCURRENTLY idx_ops_calendar
ON operations_orders (responsible, regional, closed_at DESC) 
WHERE is_closed = TRUE;

-- ANALYZE para atualizar stats do planner
ANALYZE operations_orders;
```

---

### ⚡ Técnicas de Otimização

**1. Paginação em Grandes Resultsets:**
```python
# Evitar: SELECT * (sem LIMIT)
bad_query = db.query(OperationOrder).filter(...).all()  # 100K+ rows

# Bom:
good_query = (
    db.query(OperationOrder)
    .filter(...)
    .offset((page - 1) * limit)
    .limit(limit)
    .all()
)
```

**2. Lazy Loading de Relacionamentos:**
```python
# Evitar: N+1 queries
bad = db.query(OperationTeamModel).all()
for model in bad:
    print(model.target_rules)  # Query por modelo

# Bom: Eager loading
good = (
    db.query(OperationTeamModel)
    .options(selectinload(OperationTeamModel.target_rules))
    .all()
)
```

**3. Agregação no Banco (não em Python):**
```python
# Evitar:
orders = db.query(OperationOrder).all()
total = sum(1 for o in orders if o.sla_status == "on_time")

# Bom:
total = db.query(
    func.count(OperationOrder.id)
).filter(
    OperationOrder.sla_status == "on_time"
).scalar()
```

---

## Tratamento de Erros

### 🚨 Erros do IXC

**Tipos Capturados:**
```python
from app.services.ixc_client import IxcApiError, IxcQueryLimitError

class IxcApiError(Exception):
    """Erro genérico de API."""
    def __init__(self, status_code: int, message: str, ...):
        self.status_code = status_code
        self.message = message

class IxcQueryLimitError(IxcApiError):
    """Rate limit atingido."""
    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
```

**Tratamento (ixc_ingestion.py):**
```python
def import_with_retry(date_from: date, date_to: date, max_retries: int = 3):
    """Importa com retry exponencial."""
    
    for attempt in range(max_retries):
        try:
            return import_from_ixc(date_from, date_to)
        
        except IxcQueryLimitError as e:
            wait_time = e.retry_after_seconds * (2 ** attempt)  # Backoff
            logger.info(f"Rate limited. Waiting {wait_time}s...")
            time.sleep(wait_time)
        
        except IxcApiError as e:
            if e.status_code in [500, 502, 503]:
                # Retry em erros de servidor
                continue
            else:
                # Erro irrecuperável
                logger.error(f"IXC API error: {e.message}")
                raise
    
    raise RuntimeError(f"Failed after {max_retries} attempts")
```

---

### 📋 Logging e Auditoria

**Record Audit Log:**
```python
from app.services.audit_log import record_audit_log, snapshot

# Ao atualizar modelo
old_model = snapshot(team_model_before_update)
team_model.daily_target = new_target
db.commit()
new_model = snapshot(team_model_after_update)

record_audit_log(
    user_id=user.id,
    action="update",
    resource="operations_team_model",
    resource_id=team_model.id,
    before=old_model,
    after=new_model,
    details={"daily_target": f"{old_target} → {new_target}"}
)
```

**Níveis de Log:**
```python
logger = logging.getLogger("operations")

logger.debug("Query details: ...", extra={"query": str(sql)})
logger.info(f"Import started: {date_from} to {date_to}")
logger.warning(f"Collaborator {name} has no team model assigned")
logger.error(f"Failed to fetch from IXC: {exc}")
logger.critical("Database connection lost")
```

---

## Sumário Técnico

| Aspecto | Implementação |
|---------|---------------|
| **SLA Cálculo** | Ponderado por soma (não média simples) |
| **Tempo** | Sempre em UTC no banco, local em cálculos |
| **Segurança** | Filtro regional revalidado backend |
| **Performance** | Índices compostos + paginação obrigatória |
| **Auditoria** | Todos os CRUD registrados com snapshot |
| **Erros** | Retry exponencial para IXC rate limits |
| **Extensibilidade** | raw_payload armazenado para futuros campos |

**Próximas otimizações:**
- Materialized views para agregações de calendário
- Cache Redis para baseline de esperado (recalcular 1x/dia)
- Event-driven architecture para atualização em tempo real
