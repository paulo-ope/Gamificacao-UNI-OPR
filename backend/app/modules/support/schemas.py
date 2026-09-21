from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SupportPeriodRequest(BaseModel):
    date_from: date
    date_to: date


class SupportOpaSyncSettings(BaseModel):
    enabled: bool = False
    interval_minutes: int = Field(default=20, ge=5, le=1440)
    lookback_days: int = Field(default=1, ge=1, le=30)
    # Backfill automático de meses completos (roda de madrugada) - ver
    # app/services/opa_scheduler.py::run_opa_backfill_once.
    backfill_enabled: bool = True
    backfill_run_hour: int = Field(default=3, ge=0, le=23)
    backfill_lookback_months: int = Field(default=3, ge=1, le=24)
    # De quantas em quantas horas a sincronização refaz a busca completa de dimensões
    # (usuários/motivos/departamentos/etiquetas/CLIENTES) do OPA Suite - achado real de
    # 2026-08-27: rodava em toda sincronização, e o cadastro de clientes sozinho (100 mil+
    # registros na base real) media mais de 100s por ciclo. Ver opa_ingestion._sync_opa_dimensions.
    dimensions_refresh_hours: int = Field(default=24, ge=1, le=168)
    # Backfill noturno de TMR HISTÓRICO (reprocessa tmr_all_responses_seconds de
    # atendimentos já fechados, diferente do backfill de meses acima) - nasce
    # DESLIGADO por padrão, 1 chamada extra à API do OPA Suite por atendimento. Ver
    # app/services/opa_scheduler.py::run_opa_tmr_backfill_once.
    tmr_backfill_enabled: bool = False
    tmr_backfill_run_hour: int = Field(default=1, ge=0, le=23)
    tmr_backfill_run_until_hour: int = Field(default=6, ge=0, le=23)
    tmr_backfill_daily_limit: int = Field(default=5000, ge=100, le=20000)


class SupportOpaSyncSettingsUpdate(BaseModel):
    enabled: bool | None = None
    interval_minutes: int | None = Field(default=None, ge=5, le=1440)
    lookback_days: int | None = Field(default=None, ge=1, le=30)
    backfill_enabled: bool | None = None
    backfill_run_hour: int | None = Field(default=None, ge=0, le=23)
    backfill_lookback_months: int | None = Field(default=None, ge=1, le=24)
    dimensions_refresh_hours: int | None = Field(default=None, ge=1, le=168)
    tmr_backfill_enabled: bool | None = None
    tmr_backfill_run_hour: int | None = Field(default=None, ge=0, le=23)
    tmr_backfill_run_until_hour: int | None = Field(default=None, ge=0, le=23)
    tmr_backfill_daily_limit: int | None = Field(default=None, ge=100, le=20000)


class SupportOpaImportMonthOut(BaseModel):
    year_month: str
    status: str
    attendance_count: int = 0
    last_verified_at: datetime | None = None


class SupportOpaSyncStatus(BaseModel):
    configured: bool
    enabled: bool
    interval_minutes: int
    lookback_days: int
    backfill_enabled: bool = True
    backfill_run_hour: int = 3
    backfill_lookback_months: int = 3
    dimensions_refresh_hours: int = 24
    tmr_backfill_enabled: bool = False
    tmr_backfill_run_hour: int = 1
    tmr_backfill_run_until_hour: int = 6
    tmr_backfill_daily_limit: int = 5000
    last_success_at: datetime | None = None
    last_attempt_at: datetime | None = None
    next_allowed_at: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None
    consecutive_failures: int = 0
    sync_in_progress: bool = False
    lock_busy: bool | None = None
    active_run_id: int | None = None
    active_run_mode: str | None = None
    active_run_started_at: datetime | None = None
    next_window_delayed: bool = False
    # Estado do backfill de TMR histórico - `pending_count` é uma contagem AO VIVO
    # (não um cache), sempre atual na hora que a tela carrega.
    tmr_backfill_pending_count: int = 0
    tmr_backfill_processed_today: int = 0
    tmr_backfill_last_success_at: datetime | None = None
    tmr_backfill_last_error: str | None = None
    tmr_backfill_last_error_at: datetime | None = None


class SupportOpaAttendantOverride(BaseModel):
    id: int
    attendant_id: str
    attendant_name: str | None = None
    classification: str
    active: bool
    created_at: datetime
    updated_at: datetime


class SupportOpaAttendantOverrideCreate(BaseModel):
    attendant_id: str = Field(min_length=1, max_length=100)
    attendant_name: str | None = Field(default=None, max_length=180)
    classification: Literal["virtual_agent"] = "virtual_agent"
    active: bool = True


class SupportOpaAttendantOverrideUpdate(BaseModel):
    attendant_name: str | None = None
    classification: Literal["virtual_agent"] | None = None
    active: bool | None = None


class SupportImportResult(BaseModel):
    run_id: int
    status: str
    date_from: date
    date_to: date
    pages_processed: int = 0
    fetched_count: int
    created_count: int
    updated_count: int
    unchanged_count: int
    rejected_count: int
    errors: list[dict] = Field(default_factory=list)


class SupportOpaMetricCoverage(BaseModel):
    """Denominador explícito de uma média que pode ter cobertura parcial do
    histórico (ex.: TMR geral, calculado só pra importações a partir da data em
    que o campo entrou em produção — ver docs/normas-qualidade-dados-metricas.md,
    seção 1). `count` é quantos registros de `total` entraram na média; `total`
    é o universo do mesmo recorte de filtros. `percentage` é `None` quando
    `total` é 0 (nada a cobrir)."""

    count: int
    total: int
    percentage: float | None = None


class SupportOpaMetricItem(BaseModel):
    label: str
    total: int
    average_tma_seconds: float | None = None
    average_tmr_seconds: float | None = None
    average_tmr_all_responses_seconds: float | None = None
    tmr_all_responses_coverage: SupportOpaMetricCoverage | None = None
    average_rating: float | None = None


class SupportOpaMetrics(BaseModel):
    date_from: date
    date_to: date
    total_attendances: int
    closed_attendances: int
    average_tma_seconds: float | None = None
    average_tmr_seconds: float | None = None
    average_tmr_all_responses_seconds: float | None = None
    tmr_all_responses_coverage: SupportOpaMetricCoverage | None = None
    average_rating: float | None = None
    by_attendant: list[SupportOpaMetricItem] = Field(default_factory=list)
    by_reason: list[SupportOpaMetricItem] = Field(default_factory=list)


class SupportOpaMetricComparison(BaseModel):
    current: float | int | None = None
    previous: float | int | None = None
    absolute_change: float | int | None = None
    percentage_change: float | None = None


class SupportOpaChannelCount(BaseModel):
    channel: str
    total: int


class SupportOpaOverviewPeriod(BaseModel):
    date_from: date
    date_to: date


class SupportOpaStatusCount(BaseModel):
    status: str
    total: int


class SupportOpaRecurringCustomer(BaseModel):
    customer_id: str | None = None
    customer_name: str | None = None
    total: int


class SupportOpaCustomerMetrics(BaseModel):
    unique_customers: int
    recurring_customers: int
    recurring_customers_percentage: float
    average_attendances_per_customer: float
    top_recurring_customers: list[SupportOpaRecurringCustomer] = Field(default_factory=list)


class SupportOpaReasonMetric(BaseModel):
    label: str
    total: int
    average_tma_seconds: float | None = None
    average_tmr_seconds: float | None = None
    average_tmr_all_responses_seconds: float | None = None
    tmr_all_responses_coverage: SupportOpaMetricCoverage | None = None


class SupportOpaBotHumanMetrics(BaseModel):
    total_attendances: int
    classified_attendances: int
    unclassified_attendances: int
    with_bot: int
    with_bot_percentage: float | None = None
    reached_human: int
    reached_human_percentage: float | None = None
    bot_to_human_handoff: int
    bot_to_human_handoff_percentage: float | None = None


class SupportOpaAttendantSummary(BaseModel):
    attendant_id: str
    attendant_name: str | None = None
    attendant_type: str | None = None
    total_attendances: int
    closed_attendances: int
    open_attendances: int
    closure_rate: float
    average_tma_seconds: float | None = None
    average_tmr_seconds: float | None = None
    average_tmr_all_responses_seconds: float | None = None
    tmr_all_responses_coverage: SupportOpaMetricCoverage | None = None
    average_first_response_seconds: float | None = None
    average_rating: float | None = None
    rating_count: int
    customers: SupportOpaCustomerMetrics
    by_status: list[SupportOpaStatusCount] = Field(default_factory=list)
    by_reason: list[SupportOpaReasonMetric] = Field(default_factory=list)
    by_channel: list[SupportOpaChannelCount] = Field(default_factory=list)
    bot_human: SupportOpaBotHumanMetrics


class SupportOpaTimelineEvent(BaseModel):
    type: str
    actor_type: str
    occurred_at: datetime | None = None
    label: str
    description: str | None = None


class SupportOpaAttendanceTimeline(BaseModel):
    attendance_id: int
    source_id: str
    protocol: str | None = None
    status: str | None = None
    reason_name: str | None = None
    department_name: str | None = None
    attendant_name: str | None = None
    handled_by_bot: bool | None = None
    reached_human: bool | None = None
    bot_to_human_handoff: bool | None = None
    opened_at: datetime
    closed_at: datetime | None = None
    first_response_at: datetime | None = None
    events: list[SupportOpaTimelineEvent] = Field(default_factory=list)
    messages_source: str
    messages_error: str | None = None


class SupportOpaImportedDataWindow(BaseModel):
    """Janela real da base importada (MIN/MAX/COUNT sem filtro de período) —
    diferente de `current_period`/`previous_period`, que são o recorte escolhido
    pelo usuário. Serve pra distinguir "divergência por ausência de histórico"
    de bug de verdade quando alguém compara com o painel oficial do OPA."""

    min_opened_at: datetime | None = None
    max_opened_at: datetime | None = None
    min_closed_at: datetime | None = None
    max_closed_at: datetime | None = None
    total_attendances: int


class SupportOpaOverview(BaseModel):
    current_period: SupportOpaOverviewPeriod
    previous_period: SupportOpaOverviewPeriod
    total_attendances: SupportOpaMetricComparison
    closed_attendances: SupportOpaMetricComparison
    open_attendances: SupportOpaMetricComparison
    closure_rate: SupportOpaMetricComparison
    average_duration_seconds: SupportOpaMetricComparison
    average_rating: SupportOpaMetricComparison
    average_tmr_seconds: SupportOpaMetricComparison
    average_tmr_all_responses_seconds: SupportOpaMetricComparison
    tmr_all_responses_coverage: SupportOpaMetricCoverage
    distinct_attendants: SupportOpaMetricComparison
    distinct_departments: SupportOpaMetricComparison
    by_channel: list[SupportOpaChannelCount] = Field(default_factory=list)
    by_status: list[SupportOpaStatusCount] = Field(default_factory=list)
    customers: SupportOpaCustomerMetrics
    top_reasons: list[SupportOpaReasonMetric] = Field(default_factory=list)
    average_first_response_seconds: float | None = None
    bot_human: SupportOpaBotHumanMetrics
    imported_data_window: SupportOpaImportedDataWindow


class SupportOpaAttendanceListItem(BaseModel):
    id: int
    source_id: str
    protocol: str | None = None
    customer_id: str | None = None
    customer_name: str | None = None
    attendant_id: str | None = None
    attendant_name: str | None = None
    department_id: str | None = None
    department_name: str | None = None
    reason_id: str | None = None
    reason_name: str | None = None
    channel: str | None = None
    channel_id: str | None = None
    channel_customer: str | None = None
    status: str | None = None
    opened_at: datetime
    closed_at: datetime | None = None
    rating: float | None = None
    tma_seconds: int | None = None
    tmr_seconds: int | None = None
    tmr_all_responses_seconds: int | None = None


class SupportOpaAttendancePage(BaseModel):
    items: list[SupportOpaAttendanceListItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class SupportOpaBreakdownItem(BaseModel):
    id: str | None = None
    label: str
    total: int
    closed: int
    open: int
    closure_rate: float
    avg_duration_seconds: float | None = None
    avg_rating: float | None = None
    rating_count: int
    share_percentage: float
    previous_total: int = 0
    total_change: int = 0
    total_change_percentage: float | None = None
    previous_closure_rate: float = 0.0
    closure_rate_change_pp: float = 0.0
    previous_avg_duration_seconds: float | None = None
    avg_duration_change_percentage: float | None = None
    previous_avg_rating: float | None = None
    avg_rating_change: float | None = None


class SupportOpaBreakdowns(BaseModel):
    dimension: str
    total: int
    items: list[SupportOpaBreakdownItem] = Field(default_factory=list)


class SupportIxcTicketBreakdownItem(BaseModel):
    """Um nó do drill-down regional -> cidade -> bairro -> motivo do atendimento IXC (`su_ticket`).
    `contract_count`/`tickets_per_1000_contracts` só vêm preenchidos nos níveis "regional" e
    "city" (onde existe base de clientes cadastrada em `OperationCustomerContract`) - `None` nos
    demais níveis, nunca zero (ver docs/normas-qualidade-dados-metricas.md: não calcular quando
    faltar dado)."""

    key: str
    label: str
    ticket_count: int
    contract_count: int | None = None
    tickets_per_1000_contracts: float | None = None
    # % dos contratos ativos da REGIONAL inteira com cidade resolvida - só preenchido no nível
    # "city" (ver MIN_CITY_COVERAGE_PCT em ixc_ticket_queries.py). Cobertura baixa é o motivo de
    # `tickets_per_1000_contracts` vir None mesmo com `contract_count` preenchido - a tela precisa
    # mostrar "base insuficiente", não um número que parece preciso e não é.
    coverage_pct: float | None = None
    # Desvio vs. a janela IMEDIATAMENTE ANTERIOR de mesmo tamanho em dias (pedido do usuário,
    # 2026-09-12: "no drill ainda está sem dados de desvio") - o drill-down usa um período livre,
    # não mês-calendário, então o "histórico" comparável aqui é diferente do usado na Visão Geral
    # (que compara contra os N meses anteriores no mesmo corte de dia). `deviation_pct` vem `None`
    # quando `previous_ticket_count` está abaixo de MIN_DEVIATION_SAMPLE - sinal insuficiente, não
    # "sem mudança".
    previous_ticket_count: int = 0
    deviation_pct: float | None = None


class SupportIxcTicketBreakdown(BaseModel):
    level: str
    regional: str | None = None
    city: str | None = None
    neighborhood: str | None = None
    items: list[SupportIxcTicketBreakdownItem] = Field(default_factory=list)


class SupportIxcTicketOut(BaseModel):
    id: int
    source_id: str
    protocol: str | None = None
    customer_name: str | None = None
    regional: str | None = None
    city: str | None = None
    neighborhood: str | None = None
    locality_type: str | None = None
    subject_id: str | None = None
    subject_name: str | None = None
    sector_id: str | None = None
    sector_name: str | None = None
    status: str | None = None
    sub_status: str | None = None
    title: str | None = None
    report: str | None = None
    created_at: datetime | None = None
    # Taxonomia (tema/categoria) e risco (ICC) do motivo - pedido do usuário (2026-09-15):
    # combina o peso-base do TEMA (`SupportIxcTaxonomyMapping.risk_weight`) com o sinal textual do
    # `report` (`ixc_ticket_text_signal.py`) - um "Registro de Atendimento Operacional" com relato
    # de queda de conexão sobe de risco mesmo sendo um motivo genérico. `None` quando o motivo
    # ainda não está mapeado (NAO_MAPEADO).
    theme_id: str | None = None
    theme_label: str | None = None
    category_id: str | None = None
    category_label: str | None = None
    risk_score: int | None = None
    subtema_inferido: str | None = None


class SupportIxcTicketOverviewKpis(BaseModel):
    month: str
    cutoff_day: int
    incidencia_parcial: float | None = None
    ticket_count: int
    media_historica: float | None = None
    history_months_used: int
    desvio_pct: float | None = None
    severity: str
    contract_count: int
    coverage_pct: float | None = None
    # % dos atendimentos do recorte com tema de taxonomia mapeado (item 8 do plano de evolução
    # analítica) - None só quando não há nenhum atendimento no recorte, nunca 0% escondido.
    taxonomy_coverage_pct: float | None = None


class SupportIxcTicketDailyPoint(BaseModel):
    day: int
    current: int | None = None
    previous_month: int | None = None
    historical_avg: float | None = None
    moving_avg_7d: float | None = None


class SupportIxcTicketPriorityItem(BaseModel):
    regional: str
    category: str
    incidencia_parcial: float | None = None
    historical_deviation_pct: float | None = None
    peers_deviation_pct: float | None = None
    severity: str
    # Qual comparação decidiu `severity`: "historical" (padrão), "peers" (fallback quando o
    # histórico não tem amostra suficiente - ver MIN_HISTORICAL_SAMPLE) ou "none" (nenhuma base
    # comparável). O frontend usa isso pra rotular certo o desvio mostrado.
    severity_basis: str


class SupportIxcTicketCityPriorityItem(BaseModel):
    """Mesma forma de `SupportIxcTicketPriorityItem`, mas por CIDADE - pares são todas as cidades
    do sistema com base ativa suficiente, independente de regional (decisão do usuário,
    2026-09-11)."""

    city: str
    category: str
    incidencia_parcial: float | None = None
    historical_deviation_pct: float | None = None
    peers_deviation_pct: float | None = None
    severity: str
    severity_basis: str


class SupportIxcTicketPage(BaseModel):
    total: int
    items: list[SupportIxcTicketOut] = Field(default_factory=list)


class SupportIxcTicketBurstWindow(BaseModel):
    """Uma janela de detecção de `ixc_ticket_baseline.detect_bursts` (Fase 4, `BURST_V1`)."""

    window: str
    observed: int
    expected: float | None = None
    upper_limit: float | None = None
    ratio: float | None = None
    active: bool
    basis: str


class SupportIxcTicketMomentum(BaseModel):
    """`ixc_ticket_momentum.daily_momentum` (Fase 4, `MOMENTUM_V1`)."""

    recent_avg: float
    previous_avg: float
    change_pct: float | None = None
    consecutive_days_above_expected: int
    trend: str


class SupportIxcTicketOsConversion(BaseModel):
    """`ixc_ticket_os_conversion.os_conversion_rate` (Fase 6, `OS_CONVERSION_V1`)."""

    sample: int
    median_lead_minutes: float | None = None
    classification: str
    conversions: dict[str, float | None] = Field(default_factory=dict)


class SupportIxcTaxonomyMappingOut(BaseModel):
    """Uma linha de `support_ixc_taxonomy_mappings` - Fase 0 do plano de evolução analítica
    (2026-09-14). A tabela nasce vazia; este schema só formaliza o contrato de leitura antes de
    haver qualquer linha popular pra listar."""

    subject_id: str
    theme_id: str
    theme_label: str
    category_id: str
    category_label: str
    version: int
    effective_from: date
    risk_weight: int = 0


class SupportIxcTicketSavedFilterValues(BaseModel):
    """Só as duas dimensões que `IxcTicketFiltersBar` controla hoje - ver docstring de
    `SupportIxcTicketSavedFilter` (models.py)."""

    subject_ids: list[str] = Field(default_factory=list)
    sector_ids: list[str] = Field(default_factory=list)


class SupportIxcTicketSavedFilterOut(BaseModel):
    id: int
    name: str
    filters: SupportIxcTicketSavedFilterValues
    is_default: bool
    updated_at: datetime


class SupportIxcTicketSavedFilterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    filters: SupportIxcTicketSavedFilterValues
    is_default: bool = False


class SupportIxcTicketSavedFilterUpdate(BaseModel):
    is_default: bool


class SupportIxcAnalyticsReach(BaseModel):
    """Abrangência/reincidência do escopo (Fase 1) - ver `ixc_ticket_reach.reach_summary`."""

    unique_customers: int
    tickets_per_customer: float | None = None
    repeat_customers: int
    repeat_contact: dict[str, int] = Field(default_factory=dict)


class SupportIxcAnalyticsDriverItem(BaseModel):
    subject_name: str
    current: int
    expected: int
    excess: int
    contribution_pct: float


class SupportIxcGeographicConcentrationEntry(BaseModel):
    value: str
    count: int
    share_pct: float


class SupportIxcGeographicConcentration(BaseModel):
    """Item 5 da correção pedida (2026-09-17) - `share_pct` dos dois níveis é sobre o TOTAL DO
    ESCOPO, não em cascata cidade->bairro. Lembrete: `city`/`neighborhood` vêm do CADASTRO DO
    CLIENTE, não são localização exata de falha de rede."""

    city: SupportIxcGeographicConcentrationEntry | None = None
    neighborhood: SupportIxcGeographicConcentrationEntry | None = None


class SupportIxcAnalyticsContextOut(BaseModel):
    """Fase 2 do plano de evolução analítica (2026-09-14): resumo executivo de um escopo
    qualquer (regional/cidade/bairro + motivo/setor), no modelo de período livre unificado
    (`date_from`/`date_to` + janela anterior de mesmo tamanho) - ver `ixc_ticket_context.py`."""

    # Identificador determinístico do agrupamento (item 3, 2026-09-17) - os MESMOS filtros sempre
    # geram a MESMA chave; decodificável via `GET /ixc/analytics/context/{context_key}` e
    # `GET /ixc/analytics/context/{context_key}/tickets`, sem reconstruir os parâmetros na mão.
    context_key: str
    regional: str | None = None
    city: str | None = None
    neighborhood: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    ticket_count: int
    contract_count: int | None = None
    tickets_per_1000_contracts: float | None = None
    previous_ticket_count: int = 0
    deviation_pct: float | None = None
    # Desvio vs. a MÉDIA DOS PARES (demais itens do mesmo nível) - só preenchido quando
    # `deviation_pct` (histórico próprio) não tinha amostra suficiente (item 1, 2026-09-17: mesmo
    # fallback que a Visão Geral clássica já tinha, `ixc_ticket_overview.severity_basis`, portado
    # pro contrato de contexto único que faltava essa proteção).
    peers_deviation_pct: float | None = None
    # Média bruta dos pares (mesma unidade de `tickets_per_1000_contracts` quando disponível,
    # senão `ticket_count`) - o número por trás de `peers_deviation_pct`.
    peers_avg: float | None = None
    # Qual dos dois campos acima decidiu `severity` - nunca `None` quando um dos dois existe.
    effective_deviation_pct: float | None = None
    # "Esperado" numérico que sustenta `effective_deviation_pct` - `previous_ticket_count` quando
    # `severity_basis="historical"`, `peers_avg` quando `"peers"`, `None` quando `"insufficient_data"`.
    expected: float | None = None
    severity: str
    # "historical" (padrão) | "peers" (fallback) | "insufficient_data" (nem um nem outro - NUNCA
    # confundir com "dentro_da_curva": ausência de amostra não é normalidade).
    severity_basis: str
    next_dimension: str | None = None
    reach: SupportIxcAnalyticsReach
    top_driver: SupportIxcAnalyticsDriverItem | None = None
    # Lista completa de motivos decompostos (não só o principal) - item 4 da correção pedida
    # (2026-09-17): "não quero apenas saber qual é o maior motivo".
    drivers: list[SupportIxcAnalyticsDriverItem] = Field(default_factory=list)
    geographic_concentration: SupportIxcGeographicConcentration | None = None


class SupportIxcAnalyticsPriorityItem(BaseModel):
    """Um item do ranking do PRÓXIMO NÍVEL (`dimension`) - mesma forma de
    `SupportIxcTicketBreakdownItem`, acrescida de `dimension`/`severity`/`severity_basis`."""

    key: str
    label: str
    dimension: str
    ticket_count: int
    contract_count: int | None = None
    tickets_per_1000_contracts: float | None = None
    coverage_pct: float | None = None
    previous_ticket_count: int = 0
    deviation_pct: float | None = None
    peers_deviation_pct: float | None = None
    severity: str
    severity_basis: str
    # Chave do agrupamento que resultaria de drillar NESTE item (item 3, 2026-09-17).
    context_key: str


class SupportOpaAttendanceDetailData(BaseModel):
    source_id: str | None = None
    protocol: str | None = None
    customer_id: str | None = None
    customer_name: str | None = None
    attendant_id: str | None = None
    attendant_name: str | None = None
    department_id: str | None = None
    department_name: str | None = None
    channel: str | None = None
    channel_id: str | None = None
    channel_customer: str | None = None
    status: str | None = None
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    first_response_at: datetime | None = None
    duration_seconds: int | None = None
    tma_seconds: int | None = None
    tmr_seconds: int | None = None
    tmr_all_responses_seconds: int | None = None
    rating: float | None = None
    reasons: list[dict] = Field(default_factory=list)
    tags: list[dict] = Field(default_factory=list)
    description: str | None = None
    observations: str | None = None


class SupportOpaAttendanceDetail(BaseModel):
    id: int
    source_id: str
    local: SupportOpaAttendanceDetailData
    enriched: SupportOpaAttendanceDetailData | None = None
    external_detail_available: bool = False
    external_detail_error: str | None = None


class SupportOpaFilterOption(BaseModel):
    value: str
    label: str


class SupportOpaFilters(BaseModel):
    attendants: list[SupportOpaFilterOption] = Field(default_factory=list)
    departments: list[SupportOpaFilterOption] = Field(default_factory=list)
    channels: list[SupportOpaFilterOption] = Field(default_factory=list)
    statuses: list[SupportOpaFilterOption] = Field(default_factory=list)
    reasons: list[SupportOpaFilterOption] = Field(default_factory=list)
    tags: list[SupportOpaFilterOption] = Field(default_factory=list)


class SupportOpaTimeseriesPoint(BaseModel):
    """Um dia da série. `day` é o dia LOCAL de operação (America/Porto_Velho),
    não UTC — mesma convenção do filtro de período da tela."""

    day: date
    total: int
    closed: int
    open: int
    average_duration_seconds: float | None = None
    average_tmr_seconds: float | None = None
    average_tmr_all_responses_seconds: float | None = None
    average_rating: float | None = None
    tmr_all_responses_coverage: SupportOpaMetricCoverage | None = None


class SupportOpaTimeseries(BaseModel):
    date_basis: str
    points: list[SupportOpaTimeseriesPoint] = Field(default_factory=list)


class SupportOpaSavedFilter(BaseModel):
    id: int
    name: str
    scope: str
    filters: dict[str, Any] = Field(default_factory=dict)
    owner_id: int | None = None
    updated_at: datetime | None = None


class SupportOpaSavedFilterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scope: Literal["personal", "global"] = "personal"
    filters: dict[str, Any] = Field(default_factory=dict)
