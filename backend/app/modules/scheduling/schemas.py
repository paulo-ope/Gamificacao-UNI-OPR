from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class SchedulingStats(BaseModel):
    median: float | None = None
    p90: float | None = None
    average: float | None = None


class SchedulingSummary(BaseModel):
    opened_orders: int
    scheduled_orders: int
    pending_orders: int
    sla_minutes: int
    sla_target_pct: float
    sla_rate: float | None = None
    sla_met: bool | None = None
    ttfa_business: SchedulingStats
    ttfa_raw: SchedulingStats
    reschedule_rate: float | None = None
    rescheduled_orders: int
    window_lead_hours: SchedulingStats
    total_schedule_events: int
    active_period_days: int
    team_size: int | None = None
    expected_capacity: int | None = None


class SchedulingBucket(BaseModel):
    bucket: str
    label: str
    count: int


class SchedulingDailyPoint(BaseModel):
    date: str
    opened: int
    schedule_events: int


class SchedulingOperatorRow(BaseModel):
    ixc_operator_id: int
    operator_name: str
    is_team_member: bool
    total_events: int
    distinct_orders: int
    per_day: float
    daily_goal: int | None = None
    goal_percentage: float | None = None
    first_schedules: int
    ttfa_business_median_minutes: float | None = None


class SchedulingRankingItem(BaseModel):
    key: str
    label: str
    scheduled: int
    late_rate: float
    ttfa_median_minutes: float | None = None


class SchedulingDashboard(BaseModel):
    settings: dict[str, str]
    summary: SchedulingSummary
    ttfa_distribution: list[SchedulingBucket]
    backlog_aging: list[SchedulingBucket]
    daily_series: list[SchedulingDailyPoint]
    operators: list[SchedulingOperatorRow]
    filial_ranking: list[SchedulingRankingItem] = Field(default_factory=list)
    assunto_ranking: list[SchedulingRankingItem] = Field(default_factory=list)


class SchedulingBacklogItem(BaseModel):
    ixc_os_id: int
    opened_at: datetime
    age_hours: float
    filial: str
    setor: str
    assunto: str
    status: str | None = None


class SchedulingFilterOption(BaseModel):
    id: str | int
    name: str
    is_team_member: bool | None = None


class SchedulingFilterOptions(BaseModel):
    filiais: list[SchedulingFilterOption]
    setores: list[SchedulingFilterOption]
    assuntos: list[SchedulingFilterOption]
    operators: list[SchedulingFilterOption]
    data_available_from: datetime | None = None
    data_available_to: datetime | None = None


class SchedulingSettingsUpdate(BaseModel):
    scheduling_sla_target_pct: str | None = None
    scheduling_sla_minutes: str | None = None
    scheduling_business_start: str | None = None
    scheduling_business_end: str | None = None
    scheduling_business_days: str | None = None
    scheduling_daily_goal: str | None = None


class SchedulingTeamMember(BaseModel):
    ixc_user_id: int
    name: str
    is_team_member: bool

    model_config = ConfigDict(from_attributes=True)


class SchedulingTeamUpdate(BaseModel):
    team_member_ids: list[int]


class SchedulingSyncRequest(BaseModel):
    date_from: date | None = None
    date_to: date | None = None


class SchedulingSyncJobOut(BaseModel):
    id: int
    job_type: str
    status: str
    result: dict | None = None
    error: str | None = None
    created_at: datetime
    finished_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SchedulingOrderDetailItem(BaseModel):
    ixc_os_id: int
    opened_at: datetime
    filial: str
    setor: str
    assunto: str
    status: str | None = None
    first_scheduled_at: datetime | None = None
    ttfa_business_minutes: float | None = None
    sla_late: bool | None = None
    reschedule_count: int
    operator_name: str | None = None
    technician_name: str | None = None
    age_hours: float | None = None


class SchedulingOrderDetailPage(BaseModel):
    items: list[SchedulingOrderDetailItem]
    total: int
    page: int
    page_size: int


class SchedulingOperatorEventItem(BaseModel):
    ixc_os_id: int
    event_type: str
    event_label: str
    event_at: datetime
    window_start: datetime | None = None
    window_end: datetime | None = None
    technician_name: str | None = None
    filial: str
    assunto: str


class SchedulingOperatorEventPage(BaseModel):
    items: list[SchedulingOperatorEventItem]
    total: int
    page: int
    page_size: int


class SchedulingTimelineEvent(BaseModel):
    event_type: str
    event_label: str
    event_at: datetime
    window_start: datetime | None = None
    window_end: datetime | None = None
    operator_name: str | None = None
    technician_name: str | None = None
    mensagem: str | None = None
    historico: str | None = None


class SchedulingOrderTimeline(BaseModel):
    ixc_os_id: int
    opened_at: datetime
    filial: str
    setor: str
    assunto: str
    status: str | None = None
    events: list[SchedulingTimelineEvent]


class SchedulingSavedFilterValues(BaseModel):
    filial_ids: list[str] = Field(default_factory=list)
    setor_ids: list[str] = Field(default_factory=list)
    assunto_ids: list[str] = Field(default_factory=list)
    operator_ids: list[int] = Field(default_factory=list)
    count_mode: str = "all_events"


class SchedulingSavedFilterOut(BaseModel):
    id: int
    name: str
    filters: SchedulingSavedFilterValues
    visibility: str
    user_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SchedulingSavedFilterCreate(BaseModel):
    name: str
    filters: SchedulingSavedFilterValues
    visibility: str = "personal"


class SchedulingSavedFilterUpdate(BaseModel):
    name: str | None = None
    filters: SchedulingSavedFilterValues | None = None
    visibility: str | None = None


class SchedulingSyncStatus(BaseModel):
    watermark: datetime | None = None
    last_job: SchedulingSyncJobOut | None = None
    orders_count: int = Field(default=0)
    events_count: int = Field(default=0)
