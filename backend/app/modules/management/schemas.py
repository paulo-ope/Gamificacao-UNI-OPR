from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    reason_id: int | None
    reason_name: str | None = None
    justification_text: str | None
    action_plan: str | None
    due_date: date | None
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


class ManagementCaseJustification(BaseModel):
    reason_id: int | None = None
    justification_text: str = Field(min_length=3)
    action_plan: str | None = None
    status: str = Field(default="justified", max_length=30)
