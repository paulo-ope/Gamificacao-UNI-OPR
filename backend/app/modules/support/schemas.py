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


class SupportOpaSyncSettingsUpdate(BaseModel):
    enabled: bool | None = None
    interval_minutes: int | None = Field(default=None, ge=5, le=1440)
    lookback_days: int | None = Field(default=None, ge=1, le=30)
    backfill_enabled: bool | None = None
    backfill_run_hour: int | None = Field(default=None, ge=0, le=23)
    backfill_lookback_months: int | None = Field(default=None, ge=1, le=24)
    dimensions_refresh_hours: int | None = Field(default=None, ge=1, le=168)


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
