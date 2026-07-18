from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _reject_blank(value: str | None) -> str | None:
    """Rejeita string vazia/só espaço em campos essenciais - por padrão o Pydantic só exige que a
    chave esteja presente, não que tenha conteúdo (achado real: dava pra salvar um cadastro de
    assunto ou colaborador com campo essencial em branco). `None` passa direto (usado pelos schemas
    de update, onde o campo é opcional e `None` significa "não alterar")."""
    if value is None:
        return value
    stripped = value.strip()
    if not stripped:
        raise ValueError("Este campo é obrigatório e não pode ficar em branco.")
    return stripped


class LoginRequest(BaseModel):
    email: str
    password: str


class UserBase(BaseModel):
    name: str
    email: str
    role: str = "viewer"
    active: bool = True
    collaborator_id: int | None = None


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    role: str | None = None
    active: bool | None = None
    password: str | None = None
    collaborator_id: int | None = None


class UserOut(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime
    permissions: list[str] = []
    collaborator_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class CollaboratorBase(BaseModel):
    name: str
    role: str
    regional: str
    active: bool = True
    is_registered: bool = True
    phone: str | None = None
    email: str | None = None

    _validate_not_blank = field_validator("name", "role", "regional")(_reject_blank)


class CollaboratorCreate(CollaboratorBase):
    pass


class CollaboratorUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    regional: str | None = None
    active: bool | None = None
    is_registered: bool | None = None
    phone: str | None = None
    email: str | None = None

    _validate_not_blank = field_validator("name", "role", "regional")(_reject_blank)


class CollaboratorOut(CollaboratorBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class CollaboratorRegistryItem(CollaboratorOut):
    service_orders_count: int = 0
    suggested_regional: str | None = None
    suggested_role: str | None = None
    has_linked_orders: bool = False
    has_photo: bool = False
    portal_user_id: int | None = None
    portal_user_email: str | None = None


class CollaboratorRegistryOut(BaseModel):
    registered: list[CollaboratorRegistryItem]
    unregistered: list[CollaboratorRegistryItem]


class CollaboratorDeleteResult(BaseModel):
    id: int
    deleted: bool
    soft_deleted: bool
    moved_to_unregistered: bool


class ServiceOrderBase(BaseModel):
    os_code: str
    contract_id: str
    customer_login: str | None = None
    customer_name: str
    collaborator_id: int
    regional: str
    os_type: str
    os_subject: str
    diagnosis: str = "Não informado"
    status: str = "Concluída"
    sla_status: str = "Dentro do prazo"
    sla_hours: float | None = 24
    closing_time_hours: float | None = 0
    opened_at: datetime
    closed_at: datetime | None = None
    is_warranty: bool = False
    is_recurrence: bool = False
    is_priority: bool = False
    has_reschedule: bool = False
    has_pending: bool = False


class ServiceOrderCreate(ServiceOrderBase):
    pass


class ServiceOrderOut(ServiceOrderBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ServiceOrderPeriodSummary(BaseModel):
    reference_month: int
    reference_year: int
    total_service_orders: int
    first_order_at: datetime | None = None
    last_order_at: datetime | None = None


class ServiceOrderSubjectSummary(BaseModel):
    os_type: str
    os_subject: str
    service_orders_count: int


class ServiceOrderDeletePeriodRequest(BaseModel):
    reference_month: int
    reference_year: int
    regional: str | None = None
    confirmation: str


class ServiceOrderDeletePeriodResult(BaseModel):
    reference_month: int
    reference_year: int
    regional: str | None = None
    deleted_service_orders: int
    deleted_calculation_runs: int


class ScoringGroupBase(BaseModel):
    name: str
    description: str | None = None
    default_points: float = 0
    point_value_override: float | None = None
    active: bool = True


class ScoringGroupCreate(ScoringGroupBase):
    pass


class ScoringGroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    default_points: float | None = None
    point_value_override: float | None = None
    active: bool | None = None


class ScoringGroupOut(ScoringGroupBase):
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ScoringGroupDeleteRequest(BaseModel):
    replacement_group_id: int | None = None
    delete_linked_rules: bool = False


class ScoringGroupDeleteResult(BaseModel):
    deleted_group_id: int
    deleted_group_name: str
    moved_subject_rules: int = 0
    deleted_subject_rules: int = 0
    moved_legacy_rules: int = 0
    deleted_legacy_rules: int = 0


class ScoringRuleBase(BaseModel):
    group_id: int
    os_type: str
    os_subject: str | None = None
    points: float = 0
    active: bool = True


class ScoringRuleCreate(ScoringRuleBase):
    pass


class ScoringRuleUpdate(BaseModel):
    group_id: int | None = None
    os_type: str | None = None
    os_subject: str | None = None
    points: float | None = None
    active: bool | None = None


class ScoringRuleOut(ScoringRuleBase):
    id: int
    group: ScoringGroupOut | None = None

    model_config = ConfigDict(from_attributes=True)


class ScoringSubjectRuleBase(BaseModel):
    group_id: int
    os_type: str
    os_subject: str
    subject_category: str | None = None
    custom_points: float | None = None
    point_value_override: float | None = None
    use_group_default: bool = True
    active: bool = True

    _validate_not_blank = field_validator("os_type", "os_subject")(_reject_blank)


class ScoringSubjectRuleCreate(ScoringSubjectRuleBase):
    pass


class ScoringSubjectRuleUpdate(BaseModel):
    group_id: int | None = None
    os_type: str | None = None
    os_subject: str | None = None
    subject_category: str | None = None
    custom_points: float | None = None
    point_value_override: float | None = None
    use_group_default: bool | None = None
    active: bool | None = None

    _validate_not_blank = field_validator("os_type", "os_subject")(_reject_blank)


class ScoringSubjectRuleOut(ScoringSubjectRuleBase):
    id: int
    effective_points: float = 0
    effective_point_value: float = 0
    orders_count: int = 0
    financial_impact: float = 0
    group: ScoringGroupOut | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ScoringSubjectRuleDeleteResult(BaseModel):
    deleted_rule_id: int
    os_type: str
    os_subject: str


class UnmappedSubjectOut(BaseModel):
    os_type: str
    os_subject: str
    service_orders_count: int
    collaborators_count: int
    predominant_regional: str
    estimated_points: float
    estimated_financial_impact: float


class PenaltyRuleBase(BaseModel):
    name: str
    penalty_type: str
    points: float = 0
    calculation_mode: str = "fixed"
    active: bool = True


class PenaltyRuleCreate(PenaltyRuleBase):
    pass


class PenaltyRuleUpdate(BaseModel):
    name: str | None = None
    penalty_type: str | None = None
    points: float | None = None
    calculation_mode: str | None = None
    active: bool | None = None


class PenaltyRuleOut(PenaltyRuleBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class DiagnosisPenaltyRuleBase(BaseModel):
    diagnosis_name: str
    penalty_points: float = 0
    force_points_value: float | None = None
    action_type: str = "no_penalty"
    description: str | None = None
    active: bool = True


class DiagnosisPenaltyRuleCreate(DiagnosisPenaltyRuleBase):
    pass


class DiagnosisPenaltyRuleUpdate(BaseModel):
    diagnosis_name: str | None = None
    penalty_points: float | None = None
    force_points_value: float | None = None
    action_type: str | None = None
    description: str | None = None
    active: bool | None = None


class DiagnosisPenaltyRuleOut(DiagnosisPenaltyRuleBase):
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ImportedDiagnosisOut(BaseModel):
    diagnosis_name: str
    service_orders_count: int
    subjects_count: int
    collaborators_count: int
    predominant_regional: str
    related_subjects: list[str]
    action_type: str | None = None
    penalty_points: float | None = None
    force_points_value: float | None = None
    estimated_impact: float
    active: bool | None = None
    rule_id: int | None = None
    has_rule: bool


class SlaPenaltyRuleBase(BaseModel):
    name: str
    condition_type: str = "status_sla_out_of_time"
    penalty_type: str = "none"
    penalty_value: float = 0
    active: bool = False


class SlaPenaltyRuleCreate(SlaPenaltyRuleBase):
    pass


class SlaPenaltyRuleUpdate(BaseModel):
    name: str | None = None
    condition_type: str | None = None
    penalty_type: str | None = None
    penalty_value: float | None = None
    active: bool | None = None


class SlaPenaltyRuleOut(SlaPenaltyRuleBase):
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class RecurrenceClassificationRuleBase(BaseModel):
    name: str
    os_type_pattern: str | None = None
    os_subject_pattern: str | None = None
    diagnosis_pattern: str | None = None
    original_os_type_pattern: str | None = None
    original_os_subject_pattern: str | None = None
    return_os_type_pattern: str | None = None
    return_os_subject_pattern: str | None = None
    return_diagnosis_pattern: str | None = None
    ignore_diagnosis_pattern: str | None = None
    classification: str = "nao_identificado"
    discount_points: bool = False
    max_days: int | None = None
    require_same_subject: bool = False
    require_same_diagnosis: bool = False
    priority: int = 100
    description: str | None = None
    active: bool = True


class RecurrenceClassificationRuleCreate(RecurrenceClassificationRuleBase):
    pass


class RecurrenceClassificationRuleUpdate(BaseModel):
    name: str | None = None
    os_type_pattern: str | None = None
    os_subject_pattern: str | None = None
    diagnosis_pattern: str | None = None
    original_os_type_pattern: str | None = None
    original_os_subject_pattern: str | None = None
    return_os_type_pattern: str | None = None
    return_os_subject_pattern: str | None = None
    return_diagnosis_pattern: str | None = None
    ignore_diagnosis_pattern: str | None = None
    classification: str | None = None
    discount_points: bool | None = None
    max_days: int | None = None
    require_same_subject: bool | None = None
    require_same_diagnosis: bool | None = None
    priority: int | None = None
    description: str | None = None
    active: bool | None = None


class RecurrenceClassificationRuleOut(RecurrenceClassificationRuleBase):
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class GamificationConfigOut(BaseModel):
    name: str = "gamification_rules_config"
    version_id: int | None = None
    exported_at: datetime | None = None
    settings: dict[str, str] = {}
    scoring_groups: list[dict] = []
    scoring_subject_rules: list[dict] = []
    diagnosis_penalty_rules: list[dict] = []
    sla_penalty_rules: list[dict] = []
    recurrence_classification_rules: list[dict] = []
    health_rules: list[dict] = []


class GamificationConfigImport(BaseModel):
    name: str | None = None
    settings: dict[str, str] = {}
    scoring_groups: list[dict] = []
    scoring_subject_rules: list[dict] = []
    diagnosis_penalty_rules: list[dict] = []
    sla_penalty_rules: list[dict] = []
    recurrence_classification_rules: list[dict] = []
    health_rules: list[dict] = []


class SubjectLinkToGroupRequest(BaseModel):
    group_id: int
    os_type: str
    os_subject: str

    _validate_not_blank = field_validator("os_type", "os_subject")(_reject_blank)


class SubjectLinkToGroupBulkRequest(BaseModel):
    items: list[SubjectLinkToGroupRequest] = Field(default_factory=list, min_length=1)


class DiagnosisConfigureRequest(BaseModel):
    diagnosis_name: str
    action_type: str = "no_penalty"
    penalty_points: float = 0
    force_points_value: float | None = None
    description: str | None = None
    active: bool = True


class DiagnosisConfigureBulkRequest(BaseModel):
    items: list[DiagnosisConfigureRequest] = Field(default_factory=list, min_length=1)


class HealthRuleBase(BaseModel):
    name: str
    min_sla: float = 0
    max_recurrence_rate: float = 100
    multiplier: float = 1
    condition_operator: str = "and"
    active: bool = True


class HealthRuleCreate(HealthRuleBase):
    pass


class HealthRuleUpdate(BaseModel):
    name: str | None = None
    min_sla: float | None = None
    max_recurrence_rate: float | None = None
    multiplier: float | None = None
    condition_operator: str | None = None
    active: bool | None = None


class HealthRuleOut(HealthRuleBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class AppSettingOut(BaseModel):
    key: str
    value: str
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)


class AppSettingUpdate(BaseModel):
    value: str = Field(..., min_length=1)


class CalculationRequest(BaseModel):
    reference_month: int | None = Field(default=None, ge=1, le=12)
    reference_year: int | None = Field(default=None, ge=2000, le=2100)
    regional: str | None = None
    point_value: float | None = None
    create_revision: bool = False
    execution_note: str | None = None


class CalculationRunStatusFields(BaseModel):
    status: str
    status_changed_at: datetime | None = None
    status_changed_by: int | None = None
    status_note: str | None = None
    approved_at: datetime | None = None
    approved_by: int | None = None
    paid_at: datetime | None = None
    paid_by: int | None = None
    executed_at: datetime | None = None
    executed_by: int | None = None


class CalculationRunStatusUpdate(BaseModel):
    status: str = Field(..., min_length=1)
    note: str | None = None


class CalculationRunSnapshotOut(BaseModel):
    id: int
    config_snapshot: dict | None = None


class CollaboratorScoreOut(BaseModel):
    id: int
    collaborator_id: int
    collaborator_name: str
    role: str
    regional: str
    is_registered: bool = True
    service_orders_count: int
    gross_points: float
    penalty_points: float
    net_points: float
    health_multiplier: float
    health_status: str
    final_points: float
    estimated_payment: float
    balance_adjustment_points: float = 0
    balance_after: float = 0
    scored_service_orders: int = 0
    unscored_service_orders: int = 0
    penalized_service_orders: int = 0
    warranty_service_orders: int = 0
    recurrence_service_orders: int = 0
    rescheduled_service_orders: int = 0
    pending_service_orders: int = 0
    sla_out_service_orders: int = 0
    annulled_service_orders: int = 0
    diagnosis_penalized_service_orders: int = 0
    manual_review_service_orders: int = 0
    diagnosis_unmapped_service_orders: int = 0


class CalculationRunOut(CalculationRunStatusFields):
    id: int
    reference_month: int
    reference_year: int
    regional: str | None = None
    point_value: float
    source_import_id: int | None = None
    source_filename: str | None = None
    rules_version_id: int | None = None
    result_summary: dict | None = None
    config_snapshot: dict | None = None
    created_at: datetime
    scores: list[CollaboratorScoreOut] = []


class CalculationRunHistoryOut(CalculationRunStatusFields):
    id: int
    reference_month: int
    reference_year: int
    regional: str | None = None
    point_value: float
    source_import_id: int | None = None
    source_filename: str | None = None
    rules_version_id: int | None = None
    created_at: datetime
    collaborators_count: int
    service_orders_count: int
    gross_points: float
    penalty_points: float
    net_points: float
    final_points: float
    estimated_payment: float
    top_collaborator_name: str | None = None
    top_collaborator_points: float | None = None


class LeadershipProfileBase(BaseModel):
    name: str = Field(..., min_length=1)
    role_type: str = "supervisor"
    multiplier: float = Field(default=1, ge=0)
    role_profile_id: int | None = None
    use_custom_multiplier: bool = False
    custom_multiplier: float | None = Field(default=None, ge=0)
    average_source: str = "collaborators"
    active: bool = True
    collaborator_id: int | None = None
    regional_names: list[str] = Field(default_factory=list)


class LeadershipProfileCreate(LeadershipProfileBase):
    pass


class LeadershipProfileUpdate(BaseModel):
    name: str | None = None
    role_type: str | None = None
    multiplier: float | None = Field(default=None, ge=0)
    role_profile_id: int | None = None
    use_custom_multiplier: bool | None = None
    custom_multiplier: float | None = Field(default=None, ge=0)
    average_source: str | None = None
    active: bool | None = None
    collaborator_id: int | None = None
    regional_names: list[str] | None = None


class LeadershipRoleProfileBase(BaseModel):
    name: str = Field(..., min_length=1)
    scope_type: str = "supervisor"
    default_multiplier: float = Field(default=1, ge=0)
    active: bool = True


class LeadershipRoleProfileCreate(LeadershipRoleProfileBase):
    pass


class LeadershipRoleProfileUpdate(BaseModel):
    name: str | None = None
    scope_type: str | None = None
    default_multiplier: float | None = Field(default=None, ge=0)
    active: bool | None = None


class LeadershipRoleProfileOut(LeadershipRoleProfileBase):
    id: int
    linked_leaders_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeadershipProfileOut(BaseModel):
    id: int
    name: str
    role_type: str
    multiplier: float
    role_profile_id: int | None = None
    role_profile_name: str | None = None
    use_custom_multiplier: bool = False
    custom_multiplier: float | None = None
    average_source: str = "collaborators"
    active: bool
    collaborator_id: int | None = None
    regional_names: list[str] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeadershipAverageAuditCollaboratorOut(BaseModel):
    collaborator_id: int
    collaborator_name: str
    role: str
    regional: str
    source_type: str = "collaborator"
    service_orders_count: int
    health_multiplier: float
    final_points: float
    estimated_payment: float


class LeadershipAverageAuditOut(BaseModel):
    scoped_collaborators: int
    total_final_points: float
    average_final_points: float
    point_value: float
    base_amount: float
    multiplier: float
    bonus_amount: float
    collaborators: list[LeadershipAverageAuditCollaboratorOut] = []


class LeadershipBonusResultOut(BaseModel):
    id: int | None = None
    calculation_run_id: int
    leadership_profile_id: int
    name: str
    role_type: str
    role_profile_id: int | None = None
    role_profile_name: str | None = None
    multiplier: float
    uses_custom_multiplier: bool = False
    average_source: str = "collaborators"
    average_final_points: float
    scoped_collaborators: int
    point_value: float
    base_amount: float
    bonus_amount: float
    regionals: list[str]
    audit: LeadershipAverageAuditOut | None = None


class LeadershipPendingCollaboratorOut(BaseModel):
    collaborator_id: int
    name: str
    regional: str
    suggested_regional: str | None = None
    service_orders_count: int
    estimated_payment: float = 0


class LeadershipBonusSummaryOut(BaseModel):
    calculation_run_id: int
    results: list[LeadershipBonusResultOut] = []
    pending_collaborators: list[LeadershipPendingCollaboratorOut] = []
    total_base_amount: float = 0
    total_bonus_amount: float = 0


class MetricCard(BaseModel):
    label: str
    value: float | int | str


class PenaltyDistributionItem(BaseModel):
    name: str
    value: float
    service_orders_count: int = 0


class RegionalHealthItem(BaseModel):
    regional: str
    health_status: str
    sla_rate: float
    recurrence_rate: float
    recurrence_orders: int = 0
    multiplier: float
    total_orders: int
    pending_orders: int
    rescheduled_orders: int


class DashboardSummary(BaseModel):
    run: CalculationRunOut | None
    cards: dict[str, float | int]
    ranking: list[CollaboratorScoreOut]
    leadership_bonus: LeadershipBonusSummaryOut | None = None
    penalty_distribution: list[PenaltyDistributionItem]
    health_by_regional: list[RegionalHealthItem]
    point_value: float
    cost_by_regional: list[dict[str, float | int | str]] = []
    cost_by_group: list[dict[str, float | int | str]] = []
    cost_by_subject: list[dict[str, float | int | str]] = []
    cost_by_collaborator: list[dict[str, float | int | str]] = []
    top_penalized_subjects: list[dict[str, float | int | str]] = []
    top_scoring_subjects: list[dict[str, float | int | str]] = []
    top_unmapped_subjects: list[dict[str, float | int | str]] = []


class DashboardFilteredBreakdownOut(BaseModel):
    calculation_run_id: int
    regionals: list[str] = []
    penalty_distribution: list[PenaltyDistributionItem] = []
    cost_by_regional: list[dict[str, float | int | str]] = []
    cost_by_group: list[dict[str, float | int | str]] = []
    top_unmapped_subjects: list[dict[str, float | int | str]] = []


class DashboardBootstrapOut(BaseModel):
    reference_month: int | None = None
    reference_year: int | None = None
    regional: str | None = None
    point_value: float = 0
    has_calculation_run: bool = False
    calculation_run_id: int | None = None


class ImportErrorItem(BaseModel):
    row: int
    reason: str
    data: dict


class ImportPreview(BaseModel):
    total_rows: int
    detected_columns: list[str]
    normalized_columns: list[str]
    mapped_columns: dict[str, str]
    sample_rows: list[dict]
    errors: list[ImportErrorItem] = []


class ImportSummary(BaseModel):
    total_rows: int
    processed_rows: int
    created_count: int
    updated_count: int
    skipped_count: int
    rejected_count: int
    error_count: int
    missing_date_count: int
    duplicate_count: int
    unknown_collaborator_count: int
    required_field_missing_count: int
    paid_period_blocked_count: int
    valid_rows: int
    invalid_rows: int


class ImportResult(BaseModel):
    status: str
    imported: int
    ignored: int
    errors: list[ImportErrorItem]
    first_errors: list[ImportErrorItem] = []
    detected_columns: list[str]
    mapped_columns: dict[str, str]
    summary: ImportSummary
    import_id: int | None = None
    file_name: str | None = None
    file_hash: str | None = None
    message: str | None = None


class ImportRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    file_hash: str | None = None
    source: str
    status: str
    total_rows: int
    processed_rows: int
    imported_rows: int
    created_count: int
    updated_count: int
    skipped_count: int
    rejected_count: int
    duplicate_count: int
    missing_date_count: int
    unknown_collaborator_count: int
    required_field_missing_count: int
    paid_period_blocked_count: int
    ignored_rows: int
    error_rows: int
    imported_by: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    notes: str | None = None
    detected_columns: list[str]
    mapped_columns: dict[str, str]
    errors: list[dict] = []
    created_at: datetime


class ImportServiceOrderAuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    import_run_id: int
    os_code: str | None = None
    service_order_id: int | None = None
    action: str
    field_name: str | None = None
    old_value: str | None = None
    new_value: str | None = None
    reason: str | None = None
    row_number: int | None = None
    created_at: datetime
    created_by: int | None = None


class CollaboratorMonthlyHistoryItem(BaseModel):
    reference_month: int
    reference_year: int
    regional: str | None = None
    calculation_run_id: int
    status: str
    service_orders_count: int
    gross_points: float
    net_points: float
    final_points: float
    estimated_payment: float
    balance_adjustment_points: float = 0
    health_multiplier: float = 1


class AuditLogOut(BaseModel):
    id: int
    user_id: int | None = None
    user_name: str | None = None
    user_email: str | None = None
    action: str
    entity: str
    entity_id: str | None = None
    before_data: dict | None = None
    after_data: dict | None = None
    created_at: datetime


class PointBalanceEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    collaborator_id: int
    collaborator_name: str | None = None
    entry_type: str
    points: float
    original_service_order_id: int | None = None
    original_os_code: str | None = None
    related_service_order_id: int | None = None
    related_os_code: str | None = None
    origin_calculation_run_id: int | None = None
    origin_run_month: int | None = None
    origin_run_year: int | None = None
    origin_run_status: str | None = None
    applied_calculation_run_id: int | None = None
    applied_run_status: str | None = None
    applied_reference_month: int | None = None
    applied_reference_year: int | None = None
    status: str
    requires_review: bool = False
    recurrence_classification: str | None = None
    recurrence_action: str | None = None
    reason: str | None = None
    created_by: int | None = None
    created_at: datetime


class CollaboratorPointBalanceOut(BaseModel):
    collaborator_id: int
    collaborator_name: str | None = None
    balance_points: float
    updated_at: datetime | None = None
    entries: list[PointBalanceEntryOut] = []


class PointBalanceRevertRequest(BaseModel):
    reason: str | None = None


class PointBalanceManualAdjustmentRequest(BaseModel):
    collaborator_id: int
    points: float = Field(..., description="Positivo = crédito, negativo = débito")
    reason: str = Field(..., min_length=1)


class PointBalanceResolveReviewRequest(BaseModel):
    points: float = Field(..., description="Valor do débito confirmado (deve ser negativo)")
    note: str | None = None


class CollaboratorDetailIdentity(BaseModel):
    id: int
    name: str
    role: str | None = None
    regional: str


class CollaboratorServiceOrderDetail(BaseModel):
    id: int
    os_code: str
    contract_id: str
    customer_login: str | None = None
    customer_name: str
    regional: str
    os_type: str
    os_subject: str
    diagnosis: str
    status: str
    sla_status: str
    sla_status_normalized: str = "NAO_IDENTIFICADO"
    sla_hours: float | None = None
    closing_time_hours: float | None = None
    opened_at: datetime
    closed_at: datetime | None = None
    is_warranty: bool
    is_recurrence: bool
    has_reschedule: bool
    has_pending: bool
    group_id: int | None = None
    group_name: str | None = None
    subject_rule_id: int | None = None
    rule_applied: str | None = None
    effective_points: float
    group_base_points: float = 0
    subject_override_points: float | None = None
    use_group_default: bool | None = None
    custom_points: float | None = None
    point_value: float = 0
    point_value_source: str | None = None
    point_value_override: float | None = None
    recurrence_classification: str | None = None
    recurrence_discount_applied: bool = False
    recurrence_related_os_code: str | None = None
    recurrence_days_between: int | None = None
    recurrence_evidence: list[str] = []
    recurrence_penalty_points: float = 0
    recurrence_rule_id: int | None = None
    recurrence_rule_name: str | None = None
    base_points: float
    penalty_points: float
    sla_penalty_points: float = 0
    sla_penalty_reason: str | None = None
    sla_rule_id: int | None = None
    sla_penalty_type: str | None = None
    additional_penalty_points: float = 0
    net_points: float
    scoring_rule_name: str | None = None
    diagnosis_rule_id: int | None = None
    diagnosis_rule_applied: str | None = None
    diagnosis_action_type: str | None = None
    diagnosis_rule_description: str | None = None
    diagnosis_penalty_points: float = 0
    diagnosis_penalty_reason: str | None = None
    diagnosis_force_points_value: float | None = None
    requires_manual_review: bool = False
    scoring_status: str
    penalty_reasons: list[str]
    reasons: list[str]
    is_scored: bool
    is_unscored: bool
    is_penalized: bool
    is_annulled: bool
    is_sla_out_of_time: bool = False


class CollaboratorServiceOrdersSummary(BaseModel):
    total_service_orders: int
    scored_service_orders: int
    unscored_service_orders: int
    penalized_service_orders: int
    warranty_service_orders: int
    recurrence_service_orders: int = 0
    rescheduled_service_orders: int
    pending_service_orders: int
    sla_out_service_orders: int = 0
    annulled_service_orders: int = 0
    diagnosis_penalized_service_orders: int = 0
    manual_review_service_orders: int = 0
    diagnosis_unmapped_service_orders: int = 0
    gross_points: float
    penalty_points: float
    net_points: float
    health_multiplier: float
    final_points: float
    estimated_payment: float


class CollaboratorServiceOrdersPeriod(BaseModel):
    reference_month: int
    reference_year: int
    regional: str | None = None


class CollaboratorServiceOrdersDetailOut(BaseModel):
    collaborator: CollaboratorDetailIdentity
    period: CollaboratorServiceOrdersPeriod
    summary: CollaboratorServiceOrdersSummary
    orders: list[CollaboratorServiceOrderDetail]


class AuditSummary(BaseModel):
    total_service_orders: int
    scored_service_orders: int
    unscored_service_orders: int
    penalized_service_orders: int
    warranty_service_orders: int
    recurrence_service_orders: int = 0
    rescheduled_service_orders: int
    pending_service_orders: int
    sla_out_service_orders: int = 0
    annulled_service_orders: int
    diagnosis_penalized_service_orders: int = 0
    manual_review_service_orders: int = 0
    diagnosis_unmapped_service_orders: int = 0
    gross_points: float
    penalty_points: float
    net_points: float
    final_points: float
    estimated_payment: float


class AuditServiceOrderDetail(CollaboratorServiceOrderDetail):
    collaborator_id: int
    collaborator_name: str


class AuditGroupSummary(BaseModel):
    label: str
    service_orders_count: int
    base_points: float = 0
    penalty_points: float = 0
    net_points: float = 0
    estimated_payment: float = 0
    unscored_service_orders: int = 0
    penalized_service_orders: int = 0


class RecurrenceAuditOut(BaseModel):
    identity_type: str
    identity_value: str
    classification: str | None = None
    discount_target_os_code: str | None = None
    discount_points: float = 0
    discount_applied: bool = False
    evidence: list[str] = []
    current_order: AuditServiceOrderDetail
    origin_order: AuditServiceOrderDetail | None = None
    posterior_order: AuditServiceOrderDetail | None = None
    related_orders: list[AuditServiceOrderDetail]


class AuditServiceOrdersOut(BaseModel):
    period: CollaboratorServiceOrdersPeriod
    summary: AuditSummary
    orders: list[AuditServiceOrderDetail]
    group_summaries: dict[str, list[AuditGroupSummary]] = {}
    total_orders: int = 0
    page: int = 1
    page_size: int = 100
    total_pages: int = 1


class PortalPeriodOut(BaseModel):
    calculation_run_id: int | None = None
    reference_month: int | None = None
    reference_year: int | None = None
    status: str | None = None
    updated_at: datetime | None = None


class PortalCollaboratorOut(BaseModel):
    id: int
    name: str
    role: str | None = None
    regional: str


class PortalScoreOut(BaseModel):
    collaborator_id: int
    collaborator_name: str
    role: str | None = None
    regional: str
    service_orders_count: int
    gross_points: float
    penalty_points: float
    net_points: float
    health_multiplier: float
    health_status: str
    final_points: float
    estimated_payment: float
    scored_service_orders: int
    unscored_service_orders: int
    penalized_service_orders: int
    warranty_service_orders: int
    recurrence_service_orders: int
    rescheduled_service_orders: int
    pending_service_orders: int
    sla_out_service_orders: int
    annulled_service_orders: int
    diagnosis_penalized_service_orders: int
    manual_review_service_orders: int
    diagnosis_unmapped_service_orders: int


class PortalRankingItemOut(BaseModel):
    position: int
    collaborator_id: int
    collaborator_name: str
    role: str | None = None
    regional: str
    final_points: float
    estimated_payment: float
    service_orders_count: int
    scored_service_orders: int
    penalty_points: float
    is_current_user: bool = False


class PortalSummaryOut(BaseModel):
    user: UserOut
    collaborator: PortalCollaboratorOut | None = None
    period: PortalPeriodOut
    score: PortalScoreOut | None = None
    regional_position: int | None = None
    regional_total: int = 0
    general_position: int | None = None
    general_total: int = 0
    next_position_gap: float | None = None
    ranking: list[PortalRankingItemOut] = []
    message: str | None = None


class PortalOrderOut(BaseModel):
    id: int
    os_code: str
    opened_at: datetime
    closed_at: datetime | None = None
    os_type: str
    os_subject: str
    diagnosis: str | None = None
    status: str
    sla_status: str
    base_points: float = 0
    penalty_points: float = 0
    net_points: float = 0
    status_label: str
    reason: str | None = None


class PortalRulesOut(BaseModel):
    groups: list[dict] = []
    subjects: list[dict] = []
    diagnosis_rules: list[dict] = []
    sla_rules: list[dict] = []
    recurrence_rules: list[dict] = []


class PortalSimulationOut(BaseModel):
    current_position: int | None = None
    simulated_position: int | None = None
    extra_points: float
    points_to_next: float | None = None
    disclaimer: str


class PortalRegionalOverviewOut(BaseModel):
    regional: str
    collaborators: int
    service_orders: int
    scored_service_orders: int
    final_points: float
    estimated_payment: float
    penalty_points: float
    health_average: float


class PortalOverviewOut(BaseModel):
    period: PortalPeriodOut
    total_collaborators: int = 0
    total_regionals: int = 0
    total_service_orders: int = 0
    scored_service_orders: int = 0
    final_points: float = 0
    estimated_payment: float = 0
    penalty_points: float = 0
    unscored_service_orders: int = 0
    manual_review_service_orders: int = 0
    regional_summary: list[PortalRegionalOverviewOut] = []
    ranking: list[PortalRankingItemOut] = []
    alerts: list[str] = []
    message: str | None = None


class PortalAuditOrderOut(BaseModel):
    os_code: str
    os_type: str
    os_subject: str
    group_name: str | None = None
    base_points: float
    net_points: float
    penalty_points: float
    status_label: str
    reason: str | None = None


class PortalAuditHistoryOut(BaseModel):
    reference_month: int
    reference_year: int
    final_points: float
    estimated_payment: float
    service_orders_count: int


class PortalAuditBreakdownOut(BaseModel):
    label: str
    service_orders: int
    base_points: float
    penalty_points: float
    net_points: float


class PortalAuditOut(BaseModel):
    gross_points: float = 0
    penalty_points: float = 0
    net_points: float = 0
    health_multiplier: float = 1
    final_points: float = 0
    estimated_payment: float = 0
    health_status: str = "Nao informado"
    service_orders_count: int = 0
    scored_service_orders: int = 0
    unscored_service_orders: int = 0
    penalized_service_orders: int = 0
    warranty_service_orders: int = 0
    recurrence_service_orders: int = 0
    pending_service_orders: int = 0
    sla_out_service_orders: int = 0
    manual_review_service_orders: int = 0
    points_to_next_position: float | None = None
    top_positive_orders: list[PortalAuditOrderOut] = []
    attention_orders: list[PortalAuditOrderOut] = []
    groups: list[PortalAuditBreakdownOut] = []
    subjects: list[PortalAuditBreakdownOut] = []
    orders: list[PortalAuditOrderOut] = []
    history: list[PortalAuditHistoryOut] = []
    message: str | None = None
