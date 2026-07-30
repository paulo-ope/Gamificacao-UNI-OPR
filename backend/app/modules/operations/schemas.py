from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field


def _text_from_payload(payload: dict | None, *keys: str) -> str | None:
    if not payload:
        return None
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _service_address_from_payload(payload: dict | None) -> str | None:
    if not payload:
        return None

    address = _text_from_payload(payload, "endereco", "endereco_os", "endereco_cliente", "logradouro")
    complement = _text_from_payload(payload, "complemento", "complemento_endereco")
    reference = _text_from_payload(payload, "referencia", "ponto_referencia", "referencia_endereco")

    parts: list[str] = []
    if address:
        parts.append(address)
    if complement and complement.casefold() not in (address or "").casefold():
        parts.append(f"Complemento: {complement}")
    if reference and reference.casefold() not in (address or "").casefold():
        parts.append(f"Referência: {reference}")

    return "\n".join(parts) if parts else None


class OperationPeriod(BaseModel):
    date_from: date
    date_to: date
    allowed_from: date
    allowed_to: date
    timezone: str


class OperationImportRequest(BaseModel):
    date_from: date
    date_to: date
    sector_ids: list[str] = Field(default_factory=list, max_length=100)


class OperationIxcSectorOut(BaseModel):
    id: str
    name: str


class OperationIxcSyncSettings(BaseModel):
    enabled: bool = False
    interval_minutes: int = Field(default=20, ge=5, le=1440)
    backlog_sweep_interval_minutes: int = Field(default=60, ge=15, le=1440)
    lookback_days: int = Field(default=1, ge=1, le=30)
    sector_ids: list[str] = Field(default_factory=list, max_length=100)
    sector_scope_label: str
    available_sectors: list[OperationIxcSectorOut] = Field(default_factory=list)


class OperationIxcSyncSettingsUpdate(BaseModel):
    enabled: bool | None = None
    interval_minutes: int | None = Field(default=None, ge=5, le=1440)
    backlog_sweep_interval_minutes: int | None = Field(default=None, ge=15, le=1440)
    lookback_days: int | None = Field(default=None, ge=1, le=30)
    sector_ids: list[str] | None = Field(default=None, max_length=100)


class OperationImportResult(BaseModel):
    run_id: int
    status: str
    date_from: date
    date_to: date
    fetched_count: int
    created_count: int
    updated_count: int
    unchanged_count: int
    rejected_count: int
    errors: list[dict] = Field(default_factory=list)


class OperationBackfillJobOut(BaseModel):
    id: int
    status: str
    date_from: date
    date_to: date
    next_date: date
    total_days: int
    processed_days: int
    fetched_count: int
    created_count: int
    updated_count: int
    unchanged_count: int
    rejected_count: int
    errors: list[dict] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class OperationOpenBacklogJobOut(BaseModel):
    id: int
    status: str
    sector_ids: list[str]
    total_sectors: int
    processed_sectors: int
    fetched_count: int
    created_count: int
    updated_count: int
    unchanged_count: int
    rejected_count: int
    errors: list[dict] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class OperationFilters(BaseModel):
    team_models: list[str] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    regionals: list[str] = Field(default_factory=list)
    states: list[str] = Field(default_factory=list)
    cities: list[str] = Field(default_factory=list)
    contract_types: list[str] = Field(default_factory=list)
    person_types: list[str] = Field(default_factory=list)
    os_types: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    diagnoses: list[str] = Field(default_factory=list)
    departments: list[str] = Field(default_factory=list)
    sectors: list[str] = Field(default_factory=list)
    priorities: list[str] = Field(default_factory=list)
    creators: list[str] = Field(default_factory=list)
    responsibles: list[str] = Field(default_factory=list)
    responsible_ixc_ids: list[int] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    sla_statuses: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    pops: list[str] = Field(default_factory=list)
    opened_weekdays: list[str] = Field(default_factory=list)
    closed_weekdays: list[str] = Field(default_factory=list)


class OperationSavedFilterValues(BaseModel):
    team_models: list[str] = Field(default_factory=list, max_length=100)
    companies: list[str] = Field(default_factory=list, max_length=100)
    regionals: list[str] = Field(default_factory=list, max_length=100)
    states: list[str] = Field(default_factory=list, max_length=100)
    cities: list[str] = Field(default_factory=list, max_length=100)
    contract_types: list[str] = Field(default_factory=list, max_length=100)
    person_types: list[str] = Field(default_factory=list, max_length=100)
    os_types: list[str] = Field(default_factory=list, max_length=100)
    subjects: list[str] = Field(default_factory=list, max_length=100)
    diagnoses: list[str] = Field(default_factory=list, max_length=100)
    departments: list[str] = Field(default_factory=list, max_length=100)
    sectors: list[str] = Field(default_factory=list, max_length=100)
    priorities: list[str] = Field(default_factory=list, max_length=100)
    creators: list[str] = Field(default_factory=list, max_length=100)
    responsibles: list[str] = Field(default_factory=list, max_length=100)
    responsible_ixc_ids: list[int] = Field(default_factory=list, max_length=100)
    statuses: list[str] = Field(default_factory=list, max_length=100)
    sla_statuses: list[str] = Field(default_factory=list, max_length=100)
    projects: list[str] = Field(default_factory=list, max_length=100)
    pops: list[str] = Field(default_factory=list, max_length=100)
    opened_weekdays: list[str] = Field(default_factory=list, max_length=7)
    closed_weekdays: list[str] = Field(default_factory=list, max_length=7)
    custom_window_basis: list[str] = Field(default_factory=list, max_length=2)
    custom_window_start_weekday: str | None = Field(default=None, max_length=20)
    custom_window_start_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    custom_window_end_weekday: str | None = Field(default=None, max_length=20)
    custom_window_end_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    responsible_mode: Literal["all", "completed"] = "all"
    search: str | None = Field(default=None, max_length=160)
    closed_time_from: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    closed_time_to: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")

    model_config = ConfigDict(extra="forbid")


class OperationSavedFilterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    filters: OperationSavedFilterValues
    visibility: Literal["personal", "global"] = "personal"


class OperationSavedFilterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    filters: OperationSavedFilterValues | None = None
    visibility: Literal["personal", "global"] | None = None


class OperationSavedFilterOut(BaseModel):
    id: int
    name: str
    filters: OperationSavedFilterValues
    visibility: Literal["personal", "global"] = "personal"
    user_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OperationOverview(BaseModel):
    opened: int
    opened_associated: int
    responsible_filter_active: bool
    completed: int
    in_progress: int
    opened_out_of_time: int
    completed_on_time: int
    completed_out_of_time: int
    sla_rate: float | None
    average_daily_opened: float
    average_daily_completed: float
    average_closing_hours: float | None
    average_wait_to_displacement_minutes: float | None
    average_cycle_minutes: float | None


class OperationWorkScheduleBreakdown(BaseModel):
    model_id: int
    model_name: str
    completed: int
    outside_schedule: int
    before_start: int
    after_end: int
    unclassified: int


class OperationWorkScheduleOverview(BaseModel):
    completed: int
    classified: int
    outside_schedule: int
    before_start: int
    after_end: int
    unclassified: int
    outside_rate: float | None
    selected_model_ids: list[int] = Field(default_factory=list)
    available_models: list[dict] = Field(default_factory=list)
    by_model: list[OperationWorkScheduleBreakdown] = Field(default_factory=list)


class OperationTrendPoint(BaseModel):
    period_start: date
    period_end: date
    opened_operation: int
    opened_associated: int
    completed: int
    completed_on_time: int
    completed_out_of_time: int
    completed_unmeasurable: int
    sla_rate: float | None
    sla_cumulative_rate: float | None


class OperationTrendSeries(BaseModel):
    granularity: Literal["day", "week", "month"]
    responsible_filter_active: bool
    openings_ignore_responsibles: bool
    points: list[OperationTrendPoint]


class OperationSubjectVolumeAlert(BaseModel):
    subject: str
    current_backlog: int
    recent_average: float
    expected_backlog: float
    deviation_percentage: float | None
    z_score: float | None
    status: Literal["normal", "attention", "critical", "insufficient"]
    sample_days: int


class OperationSubjectVolumeAlerts(BaseModel):
    reference_date: date
    baseline_days: int
    recent_days: int
    responsibles_ignored: bool
    items: list[OperationSubjectVolumeAlert]


class OperationControlTowerSummary(BaseModel):
    status: Literal["normal", "attention", "critical", "insufficient"]
    opened_recent: int
    expected_opened: float
    deviation_percentage: float | None
    completed_recent: int
    net_flow: int
    pressure_ratio: float | None
    backlog: int
    overdue_backlog: int
    average_backlog_age_hours: float | None
    persistent_days: int
    critical_nodes: int
    attention_nodes: int
    reasons: list[str] = Field(default_factory=list)


class OperationControlTowerItem(BaseModel):
    label: str
    level: Literal["subject", "regional", "city", "sector", "responsible"]
    path: dict[str, str]
    opened_recent: int
    expected_opened: float
    deviation_percentage: float | None
    completed_recent: int
    net_flow: int
    pressure_ratio: float | None
    backlog: int
    overdue_backlog: int
    average_backlog_age_hours: float | None
    persistent_days: int
    status: Literal["normal", "attention", "critical", "insufficient"]
    reasons: list[str] = Field(default_factory=list)
    has_children: bool


class OperationControlTowerTimelinePoint(BaseModel):
    date: date
    opened: int
    completed: int
    expected_opened: float
    upper_limit: float
    outside_expected: bool
    backlog: int


class OperationControlTower(BaseModel):
    reference_date: date
    level: Literal["subject", "regional", "city", "sector", "responsible"]
    next_level: Literal["regional", "city", "sector", "responsible"] | None
    path: dict[str, str]
    recent_days: int
    baseline_weeks: int
    timeline_days: int
    responsibles_ignored: bool
    calculation_note: str
    summary: OperationControlTowerSummary
    timeline: list[OperationControlTowerTimelinePoint]
    items: list[OperationControlTowerItem]


class OperationOpeningsSummary(BaseModel):
    opened: int
    completed: int
    net_flow: int
    pressure_ratio: float | None
    average_daily_opened: float
    expected_opened: float
    deviation_percentage: float | None
    backlog: int
    overdue_backlog: int
    without_responsible: int
    average_first_action_minutes: float | None


class OperationOpeningsTimelinePoint(BaseModel):
    date: date
    opened: int
    completed: int
    expected_opened: float
    upper_limit: float
    outside_expected: bool
    backlog: int


class OperationOpeningsHeatmapItem(BaseModel):
    weekday: int
    hour: int
    opened: int


class OperationOpeningsRankingItem(BaseModel):
    label: str
    opened: int
    completed: int
    backlog: int
    overdue_backlog: int
    share_percentage: float


class OperationOpeningsAgingItem(BaseModel):
    bucket: str
    label: str
    quantity: int


class OperationOpeningsInsight(BaseModel):
    severity: Literal["normal", "attention", "critical", "insufficient"]
    title: str
    description: str


class OperationOpeningsAnalytics(BaseModel):
    date_from: date
    date_to: date
    baseline_weeks: int
    granularity: Literal["day", "week", "month"]
    calculation_note: str
    summary: OperationOpeningsSummary
    timeline: list[OperationOpeningsTimelinePoint]
    heatmap: list[OperationOpeningsHeatmapItem]
    aging: list[OperationOpeningsAgingItem]
    rankings: dict[str, list[OperationOpeningsRankingItem]]
    insights: list[OperationOpeningsInsight]


class OperationDataFreshness(BaseModel):
    last_successful_import_at: datetime | None
    status: str | None
    date_from: date | None
    date_to: date | None


class OperationSlaItem(BaseModel):
    label: str
    completed: int
    on_time: int
    out_of_time: int
    sla_rate: float | None
    up_to_12h: int
    from_12h_to_24h: int
    from_24h_to_48h: int
    from_48h_to_72h: int
    after_72h: int
    average_closing_hours: float | None


class OperationSlaHierarchyItem(BaseModel):
    label: str
    completed: int
    on_time: int
    out_of_time: int
    sla_rate: float | None
    timed_orders: int
    up_to_12h_rate: float | None
    from_12h_to_24h_rate: float | None
    from_24h_to_48h_rate: float | None
    from_48h_to_72h_rate: float | None
    after_72h_rate: float | None
    average_closing_hours: float | None


class OperationSlaHierarchy(BaseModel):
    level: Literal["os_type", "subject", "diagnosis"]
    parent_os_type: str | None = None
    parent_subject: str | None = None
    items: list[OperationSlaHierarchyItem]
    total: OperationSlaHierarchyItem


class OperationCollaboratorSlaItem(BaseModel):
    responsible: str
    regional: str
    completed: int
    on_time: int
    out_of_time: int
    sla_rate: float | None
    active_days: int
    daily_average: float
    measurable_execution_orders: int
    average_execution_minutes: float | None
    minimum_execution_minutes: float | None
    maximum_execution_minutes: float | None
    type_counts: dict[str, int] = Field(default_factory=dict)
    scheduled_orders: int
    schedule_adherence_rate: float | None


class OperationCollaboratorSla(BaseModel):
    type_columns: list[str]
    items: list[OperationCollaboratorSlaItem]


class OperationCalendarDay(BaseModel):
    date: date
    day: int
    weekday: int
    week: int
    available: bool


class OperationCalendarCollaborator(BaseModel):
    responsible: str
    total: int
    daily_counts: dict[str, int] = Field(default_factory=dict)
    daily_performance: dict[str, Literal["neutral", "below", "median", "good", "excellent"]] = Field(default_factory=dict)
    monthly_performance: Literal["neutral", "below", "median", "good", "excellent"] = "neutral"
    team_model: "OperationCalendarTeamModel | None" = None
    reference_regional: str | None = None
    attended_regionals: list[str] = Field(default_factory=list)


class OperationTeamTargetRuleValues(BaseModel):
    period_type: Literal["weekday", "saturday", "sunday", "monthly"]
    enabled: bool = True
    median_from_quantity: int = Field(ge=2, le=10_000)
    good_from_quantity: int = Field(ge=3, le=10_001)
    target_quantity: int = Field(ge=4, le=10_002)
    start_time: time | None = None
    end_time: time | None = None


class OperationTeamTargetRuleOut(OperationTeamTargetRuleValues):
    id: int
    model_config = ConfigDict(from_attributes=True)


class OperationCalendarTeamModel(BaseModel):
    id: int
    name: str
    daily_target: int
    median_from_quantity: int
    good_from_quantity: int
    below_target_color: str
    median_color: str
    good_color: str
    excellent_color: str
    target_rules: list[OperationTeamTargetRuleOut] = Field(default_factory=list)


class OperationCalendarRegional(BaseModel):
    regional: str
    total: int
    daily_counts: dict[str, int] = Field(default_factory=dict)
    collaborators: list[OperationCalendarCollaborator]


class OperationCalendar(BaseModel):
    competence: str
    date_from: date
    date_to: date
    group_by: Literal["regional", "collaborator"] = "regional"
    days: list[OperationCalendarDay]
    regionals: list[OperationCalendarRegional]


HEX_COLOR_PATTERN = r"^#[0-9a-fA-F]{6}$"


class OperationTeamModelValues(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    daily_target: int = Field(default=5, ge=4, le=500)
    median_from_quantity: int = Field(default=3, ge=2, le=498)
    good_from_quantity: int = Field(default=4, ge=3, le=499)
    below_target_color: str = Field(default="#fee2e2", pattern=HEX_COLOR_PATTERN)
    median_color: str = Field(default="#fef3c7", pattern=HEX_COLOR_PATTERN)
    good_color: str = Field(default="#dcfce7", pattern=HEX_COLOR_PATTERN)
    excellent_color: str = Field(default="#dbeafe", pattern=HEX_COLOR_PATTERN)
    active: bool = True
    target_rules: list[OperationTeamTargetRuleValues] = Field(default_factory=list)


class OperationTeamModelCreate(OperationTeamModelValues):
    pass


class OperationTeamModelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    daily_target: int | None = Field(default=None, ge=4, le=500)
    median_from_quantity: int | None = Field(default=None, ge=2, le=498)
    good_from_quantity: int | None = Field(default=None, ge=3, le=499)
    below_target_color: str | None = Field(default=None, pattern=HEX_COLOR_PATTERN)
    median_color: str | None = Field(default=None, pattern=HEX_COLOR_PATTERN)
    good_color: str | None = Field(default=None, pattern=HEX_COLOR_PATTERN)
    excellent_color: str | None = Field(default=None, pattern=HEX_COLOR_PATTERN)
    active: bool | None = None
    target_rules: list[OperationTeamTargetRuleValues] | None = None


class OperationTeamModelOut(OperationTeamModelValues):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OperationSubjectTypeMappingUpdate(BaseModel):
    subject: str = Field(min_length=1, max_length=220)
    os_type: str = Field(min_length=1, max_length=160)


class OperationSubjectTypeBulkUpdate(BaseModel):
    subjects: list[str] = Field(min_length=1, max_length=500)
    os_type: str = Field(min_length=1, max_length=160)


class OperationSubjectTypeMappingOut(BaseModel):
    id: int | None = None
    subject: str
    os_type: str
    order_count: int = 0
    active: bool = True


class OperationResponsibleAssignmentUpdate(BaseModel):
    responsible_name: str = Field(min_length=1, max_length=180)
    regional: str = Field(min_length=1, max_length=160)
    team_model_id: int | None = None


class OperationResponsibleProfileOut(BaseModel):
    responsible_name: str
    regional: str
    regionals: list[str] = Field(default_factory=list)
    team_model_id: int | None = None


class OperationTeamConfiguration(BaseModel):
    models: list[OperationTeamModelOut]
    members: list[OperationResponsibleProfileOut]
    responsible_source: Literal["orders", "ixc", "both"] = "orders"
    ixc_collaborators_synced_at: datetime | None = None


class OperationResponsibleDirectoryUpdate(BaseModel):
    source: Literal["orders", "ixc", "both"]


class OperationIxcCollaboratorSyncResult(BaseModel):
    imported: int
    active: int
    synced_at: datetime


class OperationConfigurationModelImport(OperationTeamModelValues):
    pass


class OperationConfigurationAssignmentImport(BaseModel):
    responsible_name: str = Field(min_length=1, max_length=180)
    regional: str | None = Field(default=None, max_length=160)
    team_model_name: str | None = Field(default=None, max_length=120)


class OperationConfigurationSavedFilterImport(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    filters: OperationSavedFilterValues
    visibility: Literal["personal", "global"] = "personal"


class OperationConfigurationSubjectMappingImport(BaseModel):
    subject: str = Field(min_length=1, max_length=220)
    os_type: str = Field(min_length=1, max_length=160)
    active: bool = True


class OperationConfigurationJson(BaseModel):
    schema_version: Literal[1] = 1
    team_models: list[OperationConfigurationModelImport] = Field(default_factory=list, max_length=200)
    team_members: list[OperationConfigurationAssignmentImport] = Field(default_factory=list, max_length=10_000)
    subject_mappings: list[OperationConfigurationSubjectMappingImport] = Field(default_factory=list, max_length=2_000)
    saved_filters: list[OperationConfigurationSavedFilterImport] = Field(default_factory=list, max_length=500)


class OperationConfigurationImportResult(BaseModel):
    team_models: int = 0
    team_members: int = 0
    subject_mappings: int = 0
    saved_filters: int = 0


class OperationBreakdownItem(BaseModel):
    label: str
    quantity: int
    percentage: float


class OperationSlaRiskItem(BaseModel):
    bucket: Literal["breached", "critical", "attention", "on_track", "no_target"]
    label: str
    quantity: int
    percentage: float


class OperationOrderOut(BaseModel):
    id: int
    source_order_id: str
    order_code: str
    protocol: str | None
    contract_id: str | None
    customer_name: str | None
    regional: str | None
    city: str | None
    os_type: str | None
    os_subject: str | None
    diagnosis: str | None
    department: str | None
    sector: str | None
    priority: str | None
    creator: str | None
    responsible: str | None
    status: str | None
    status_code: str | None
    sla_status: str
    sla_target_hours: float | None
    elapsed_hours: float | None
    opened_at: datetime
    assumed_at: datetime | None
    displacement_started_at: datetime | None
    execution_started_at: datetime | None
    finished_at: datetime | None
    deadline_at: datetime | None
    scheduled_at: datetime | None
    closed_at: datetime | None
    normalization_notes: str | None
    raw_payload: dict = Field(exclude=True)

    @computed_field
    @property
    def service_address(self) -> str | None:
        return _service_address_from_payload(self.raw_payload)

    @computed_field
    @property
    def service_description(self) -> str | None:
        return _text_from_payload(self.raw_payload, "mensagem", "descricao", "descricao_servico")

    @computed_field
    @property
    def technical_report(self) -> str | None:
        return _text_from_payload(self.raw_payload, "mensagem_resposta", "relato_tecnico", "relato")

    model_config = ConfigDict(from_attributes=True)


class OperationOrderPage(BaseModel):
    items: list[OperationOrderOut]
    total: int
    page: int
    page_size: int
    total_pages: int


class OperationCalendarDayMetrics(BaseModel):
    total_orders: int
    active_days: int = 0
    timed_orders: int
    missing_execution_times: int
    average_execution_minutes: float | None
    median_execution_minutes: float | None
    minimum_execution_minutes: float | None
    maximum_execution_minutes: float | None
    average_pre_displacement_minutes: float | None
    average_total_minutes: float | None
    sla_rate: float | None
    first_displacement_at: datetime | None
    last_finished_at: datetime | None
    operational_window_orders: int
    missing_operational_window_times: int
    total_execution_minutes: float | None
    average_displacement_minutes: float | None
    total_displacement_minutes: float | None
    displacement_orders: int
    attended_regionals: list[str] = Field(default_factory=list)
    cross_regional_orders: int = 0
    type_counts: dict[str, int] = Field(default_factory=dict)


class OperationCalendarDayDetail(BaseModel):
    metrics: OperationCalendarDayMetrics
    orders: OperationOrderPage


class OperationCalendarMonthlyMetrics(BaseModel):
    total_orders: int
    active_days: int
    timed_orders: int
    missing_execution_times: int
    average_execution_minutes: float | None
    median_execution_minutes: float | None
    average_total_minutes: float | None
    total_execution_minutes: float | None
    average_displacement_minutes: float | None
    total_displacement_minutes: float | None
    displacement_orders: int
    sla_rate: float | None
    attended_regionals: list[str] = Field(default_factory=list)
    cross_regional_orders: int = 0


class OperationCalendarMonthlyDetail(BaseModel):
    metrics: OperationCalendarMonthlyMetrics
    by_regional: list[OperationBreakdownItem] = Field(default_factory=list)
    orders: OperationOrderPage


class OperationQuery(BaseModel):
    date_from: date
    date_to: date
    team_models: list[str] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    regionals: list[str] = Field(default_factory=list)
    states: list[str] = Field(default_factory=list)
    cities: list[str] = Field(default_factory=list)
    contract_types: list[str] = Field(default_factory=list)
    person_types: list[str] = Field(default_factory=list)
    os_types: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    diagnoses: list[str] = Field(default_factory=list)
    departments: list[str] = Field(default_factory=list)
    sectors: list[str] = Field(default_factory=list)
    priorities: list[str] = Field(default_factory=list)
    creators: list[str] = Field(default_factory=list)
    responsibles: list[str] = Field(default_factory=list)
    responsible_ixc_ids: list[int] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    sla_statuses: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    pops: list[str] = Field(default_factory=list)
    opened_weekdays: list[str] = Field(default_factory=list)
    closed_weekdays: list[str] = Field(default_factory=list)
    custom_window_basis: list[str] = Field(default_factory=list)
    custom_window_start_weekday: str | None = Field(default=None)
    custom_window_start_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    custom_window_end_weekday: str | None = Field(default=None)
    custom_window_end_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    closed_time_from: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    closed_time_to: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    responsible_mode: Literal["all", "completed"] = "all"
    search: str | None = Field(default=None, max_length=160)
