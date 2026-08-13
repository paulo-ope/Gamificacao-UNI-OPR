from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.management.models import (
    JUSTIFY_TARGET_STATUSES,
    OPERATIONAL_MEMBER_STATUSES,
    REVIEW_TARGET_STATUSES,
)


class ManagementOperationalMemberOut(BaseModel):
    id: int
    collaborator_id: int | None
    collaborator_name: str | None = None
    collaborator_is_registered: bool | None = None
    collaborator_employee_type: str | None = None
    collaborator_team_type: str | None = None
    collaborator_structure_status: str | None = None
    collaborator_supervisor_user_id: int | None = None
    collaborator_supervisor_name: str | None = None
    gamification_status: str
    ixc_employee_id: int | None
    responsible_name: str
    regional: str
    supervisor_user_id: int | None
    supervisor_name: str | None = None
    team_model_id: int | None
    team_model_name: str | None = None
    status: str
    source: str
    is_active: bool
    notes: str | None
    last_order_at: datetime | None
    alerts: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ManagementSummaryOut(BaseModel):
    total_members: int = 0
    active_members: int = 0
    pending_validation: int = 0
    without_supervisor: int = 0
    without_team_model: int = 0
    without_gamification: int = 0
    conflicts: int = 0
    open_cases: int = 0
    overdue_cases: int = 0


class ManagementDashboardOut(BaseModel):
    summary: ManagementSummaryOut
    members: list[ManagementOperationalMemberOut]


class ManagementOptionOut(BaseModel):
    id: int
    name: str


class ManagementOptionsOut(BaseModel):
    supervisors: list[ManagementOptionOut]
    team_models: list[ManagementOptionOut]


class ManagementMemberUpdate(BaseModel):
    supervisor_user_id: int | None = None
    team_model_id: int | None = None
    status: str | None = Field(default=None, max_length=40)
    notes: str | None = None

    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: str | None) -> str | None:
        if value is None:
            return value
        text = value.strip()
        if not text:
            raise ValueError("Status não pode ser vazio.")
        if text not in OPERATIONAL_MEMBER_STATUSES:
            allowed = ", ".join(OPERATIONAL_MEMBER_STATUSES)
            raise ValueError(f"Status inválido. Use um destes: {allowed}.")
        return text


class ManagementCaseReasonOut(BaseModel):
    id: int
    name: str
    description: str | None
    active: bool
    requires_description: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ManagementCaseReasonCreate(BaseModel):
    name: str = Field(min_length=2, max_length=140)
    description: str | None = None
    active: bool = True
    requires_description: bool = False


class ManagementCaseReasonUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=140)
    description: str | None = None
    active: bool | None = None
    requires_description: bool | None = None


class ManagementCaseOut(BaseModel):
    id: int
    case_type: str
    source_module: str
    reference_date: date | None
    reference_month: int | None
    reference_year: int | None
    regional: str | None
    collaborator_id: int | None
    collaborator_name: str | None = None
    responsible_name: str | None
    supervisor_user_id: int | None
    supervisor_name: str | None = None
    team_model_id: int | None
    team_model_name: str | None = None
    metric_name: str
    expected_value: float | None
    actual_value: float | None
    deviation_value: float | None
    severity: str
    status: str
    is_overdue: bool = False
    reason_id: int | None
    reason_name: str | None = None
    justification_text: str | None
    action_plan: str | None
    due_date: date | None
    comment_count: int = 0
    created_at: datetime
    updated_at: datetime
    justified_at: datetime | None
    reviewed_by: int | None
    reviewed_at: datetime | None


class ManagementCaseCreate(BaseModel):
    case_type: str = Field(max_length=60)
    source_module: str = Field(default="management", max_length=40)
    reference_date: date | None = None
    reference_month: int | None = None
    reference_year: int | None = None
    regional: str | None = Field(default=None, max_length=160)
    collaborator_id: int | None = None
    responsible_name: str | None = Field(default=None, max_length=180)
    supervisor_user_id: int | None = None
    team_model_id: int | None = None
    metric_name: str = Field(max_length=120)
    expected_value: float | None = None
    actual_value: float | None = None
    deviation_value: float | None = None
    severity: str = Field(default="medium", max_length=20)
    due_date: date | None = None


class ManagementDailyCaseRequest(BaseModel):
    """Abre (ou devolve, se já existir) o caso de justificativa de um dia específico marcado
    abaixo da meta no drill do calendário da Operação Analítica."""

    responsible_name: str = Field(min_length=1, max_length=180)
    regional: str = Field(min_length=1, max_length=160)
    reference_date: date
    expected_value: float | None = None
    actual_value: float = Field(ge=0)


class ManagementCaseJustification(BaseModel):
    reason_id: int | None = None
    justification_text: str = Field(min_length=3)
    action_plan: str | None = None
    status: str = Field(default="justified", max_length=30)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        # O supervisor só move o caso para "justificado" ou "em andamento". Encerrar (resolvido/
        # rejeitado) é decisão da matriz e passa por /review, que exige management:review.
        if value not in JUSTIFY_TARGET_STATUSES:
            allowed = ", ".join(JUSTIFY_TARGET_STATUSES)
            raise ValueError(f"Status inválido para justificativa. Use um destes: {allowed}.")
        return value


class ManagementCaseReview(BaseModel):
    """Decisão da matriz sobre um caso já justificado."""

    status: str
    review_note: str | None = None
    due_date: date | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in REVIEW_TARGET_STATUSES:
            allowed = ", ".join(REVIEW_TARGET_STATUSES)
            raise ValueError(f"Status inválido para revisão. Use um destes: {allowed}.")
        return value


class ManagementCaseCommentOut(BaseModel):
    id: int
    case_id: int
    user_id: int | None
    user_name: str | None = None
    comment: str
    created_at: datetime


class ManagementCaseCommentCreate(BaseModel):
    comment: str = Field(min_length=2)


class ManagementCaseSummaryOut(BaseModel):
    total_cases: int = 0
    open_cases: int = 0
    pending_cases: int = 0
    justified_cases: int = 0
    resolved_cases: int = 0
    overdue_cases: int = 0
    high_severity_open: int = 0


class ManagementCasePage(BaseModel):
    items: list[ManagementCaseOut]
    summary: ManagementCaseSummaryOut
    total: int
    page: int
    page_size: int


class ManagementCaseGenerateRequest(BaseModel):
    reference_year: int = Field(ge=2020, le=2100)
    reference_month: int = Field(ge=1, le=12)


class ManagementCaseGenerateResult(BaseModel):
    created_cases: int
    evaluated_members: int
    skipped_existing: int
    skipped_insufficient_data: int
    reference_year: int
    reference_month: int


class ManagementSettingsUpdate(BaseModel):
    management_case_min_deviation_pct: str | None = None
    management_case_high_severity_pct: str | None = None
    management_case_low_severity_pct: str | None = None
    management_case_min_days_worked: str | None = None
    management_case_due_days: str | None = None
