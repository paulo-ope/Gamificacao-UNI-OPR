export type Permission =
  | "dashboard:read"
  | "audit:read"
  | "orders:read"
  | "orders:import"
  | "scoring:read"
  | "scoring:write"
  | "penalties:write"
  | "health_rules:write"
  | "settings:write"
  | "calculation:run"
  | "users:manage";

export type AuthUser = {
  id: number;
  name: string;
  email: string;
  role: "viewer" | "operator" | "admin";
  active: boolean;
  created_at: string;
  updated_at: string;
  permissions: Permission[];
};

export type LoginResult = {
  access_token: string;
  token_type: string;
  user: AuthUser;
};

export type MetricCards = {
  total_collaborators: number;
  total_service_orders: number;
  scored_service_orders: number;
  unscored_service_orders: number;
  penalized_service_orders: number;
  warranty_service_orders: number;
  recurrence_service_orders: number;
  rescheduled_service_orders: number;
  pending_service_orders: number;
  sla_out_service_orders: number;
  annulled_service_orders: number;
  diagnosis_penalized_service_orders: number;
  manual_review_service_orders: number;
  diagnosis_unmapped_service_orders: number;
  closure_pending_service_orders: number;
  gross_points: number;
  penalty_points: number;
  lost_points: number;
  lost_payment: number;
  unscored_estimated_payment: number;
  final_points: number;
  estimated_payment: number;
  orders_without_scoring_rule: number;
};

export type CollaboratorScore = {
  id: number;
  collaborator_id: number;
  collaborator_name: string;
  role: string;
  regional: string;
  is_registered: boolean;
  service_orders_count: number;
  gross_points: number;
  penalty_points: number;
  net_points: number;
  health_multiplier: number;
  health_status: string;
  final_points: number;
  estimated_payment: number;
  scored_service_orders: number;
  unscored_service_orders: number;
  penalized_service_orders: number;
  warranty_service_orders: number;
  recurrence_service_orders: number;
  rescheduled_service_orders: number;
  pending_service_orders: number;
  sla_out_service_orders: number;
  annulled_service_orders: number;
  diagnosis_penalized_service_orders: number;
  manual_review_service_orders: number;
  diagnosis_unmapped_service_orders: number;
};

export type Collaborator = {
  id: number;
  name: string;
  role: string;
  regional: string;
  active: boolean;
  is_registered: boolean;
};

export type CollaboratorRegistryItem = Collaborator & {
  service_orders_count: number;
  suggested_regional: string | null;
  suggested_role: string | null;
  has_linked_orders: boolean;
};

export type CollaboratorRegistry = {
  registered: CollaboratorRegistryItem[];
  unregistered: CollaboratorRegistryItem[];
};

export type CollaboratorDeleteResult = {
  id: number;
  deleted: boolean;
  soft_deleted: boolean;
  moved_to_unregistered: boolean;
};

export type CalculationRun = {
  id: number;
  reference_month: number;
  reference_year: number;
  regional: string | null;
  point_value: number;
  source_import_id: number | null;
  source_filename: string | null;
  rules_version_id: number | null;
  result_summary: Record<string, unknown> | null;
  created_at: string;
  scores: CollaboratorScore[];
};

export type CalculationRunHistory = {
  id: number;
  reference_month: number;
  reference_year: number;
  regional: string | null;
  point_value: number;
  source_import_id: number | null;
  source_filename: string | null;
  rules_version_id: number | null;
  created_at: string;
  collaborators_count: number;
  service_orders_count: number;
  gross_points: number;
  penalty_points: number;
  net_points: number;
  final_points: number;
  estimated_payment: number;
  top_collaborator_name: string | null;
  top_collaborator_points: number | null;
};

export type ServiceOrder = {
  id: number;
  os_code: string;
  contract_id: string;
  customer_login: string | null;
  customer_name: string;
  collaborator_id: number;
  regional: string;
  os_type: string;
  os_subject: string;
  diagnosis: string;
  status: string;
  sla_status: string;
  sla_status_normalized: string;
  sla_hours: number | null;
  closing_time_hours: number | null;
  opened_at: string;
  closed_at: string | null;
  is_warranty: boolean;
  is_recurrence: boolean;
  is_priority: boolean;
  has_reschedule: boolean;
  has_pending: boolean;
  created_at: string;
};

export type ServiceOrderPeriodSummary = {
  reference_month: number;
  reference_year: number;
  total_service_orders: number;
  first_order_at: string | null;
  last_order_at: string | null;
};

export type ServiceOrderSubjectSummary = {
  os_type: string;
  os_subject: string;
  service_orders_count: number;
};

export type ServiceOrderDeletePeriodResult = {
  reference_month: number;
  reference_year: number;
  regional: string | null;
  deleted_service_orders: number;
  deleted_calculation_runs: number;
};

export type PenaltyDistributionItem = {
  name: string;
  value: number;
  service_orders_count: number;
};

export type RegionalHealthItem = {
  regional: string;
  health_status: string;
  sla_rate: number;
  recurrence_rate: number;
  recurrence_orders: number;
  multiplier: number;
  total_orders: number;
  pending_orders: number;
  rescheduled_orders: number;
};

export type DashboardSummary = {
  run: CalculationRun | null;
  cards: MetricCards;
  ranking: CollaboratorScore[];
  leadership_bonus: LeadershipBonusSummary | null;
  penalty_distribution: PenaltyDistributionItem[];
  health_by_regional: RegionalHealthItem[];
  point_value: number;
  cost_by_regional: FinancialBreakdownItem[];
  cost_by_group: FinancialBreakdownItem[];
  cost_by_subject: FinancialBreakdownItem[];
  cost_by_collaborator: FinancialBreakdownItem[];
  top_penalized_subjects: FinancialBreakdownItem[];
  top_scoring_subjects: FinancialBreakdownItem[];
  top_unmapped_subjects: FinancialBreakdownItem[];
};

export type LeadershipRoleType = "supervisor" | "regional_manager" | "portfolio_manager";

export type LeadershipRoleProfile = {
  id: number;
  name: string;
  scope_type: LeadershipRoleType;
  default_multiplier: number;
  active: boolean;
  linked_leaders_count: number;
  created_at: string;
  updated_at: string;
};

export type LeadershipProfile = {
  id: number;
  name: string;
  role_type: LeadershipRoleType;
  multiplier: number;
  role_profile_id: number | null;
  role_profile_name: string | null;
  use_custom_multiplier: boolean;
  custom_multiplier: number | null;
  active: boolean;
  collaborator_id: number | null;
  regional_names: string[];
  created_at: string;
  updated_at: string;
};

export type LeadershipBonusResult = {
  id: number | null;
  calculation_run_id: number;
  leadership_profile_id: number;
  name: string;
  role_type: LeadershipRoleType;
  role_profile_id: number | null;
  role_profile_name: string | null;
  multiplier: number;
  uses_custom_multiplier: boolean;
  average_final_points: number;
  scoped_collaborators: number;
  point_value: number;
  base_amount: number;
  bonus_amount: number;
  regionals: string[];
};

export type LeadershipPendingCollaborator = {
  collaborator_id: number;
  name: string;
  regional: string;
  suggested_regional: string | null;
  service_orders_count: number;
  estimated_payment: number;
};

export type LeadershipBonusSummary = {
  calculation_run_id: number;
  results: LeadershipBonusResult[];
  pending_collaborators: LeadershipPendingCollaborator[];
  total_base_amount: number;
  total_bonus_amount: number;
};

export type ScoringGroup = {
  id: number;
  name: string;
  description: string | null;
  default_points: number;
  point_value_override: number | null;
  active: boolean;
  created_at?: string | null;
  updated_at?: string | null;
};

export type ScoringGroupDeleteResult = {
  deleted_group_id: number;
  deleted_group_name: string;
  moved_subject_rules: number;
  deleted_subject_rules: number;
  moved_legacy_rules: number;
  deleted_legacy_rules: number;
};

export type ScoringRule = {
  id: number;
  group_id: number;
  os_type: string;
  os_subject: string | null;
  points: number;
  active: boolean;
  group?: ScoringGroup | null;
};

export type ScoringSubjectRule = {
  id: number;
  group_id: number;
  os_type: string;
  os_subject: string;
  subject_category: string | null;
  custom_points: number | null;
  point_value_override: number | null;
  use_group_default: boolean;
  active: boolean;
  effective_points: number;
  effective_point_value: number;
  orders_count: number;
  financial_impact: number;
  group?: ScoringGroup | null;
  created_at: string | null;
  updated_at: string | null;
};

export type ScoringSubjectRuleDeleteResult = {
  deleted_rule_id: number;
  os_type: string;
  os_subject: string;
};

export type UnmappedSubject = {
  os_type: string;
  os_subject: string;
  service_orders_count: number;
  collaborators_count: number;
  predominant_regional: string;
  estimated_points: number;
  estimated_financial_impact: number;
};

export type FinancialBreakdownItem = {
  regional?: string;
  group?: string;
  collaborator_id?: number;
  collaborator_name?: string;
  os_type?: string;
  os_subject?: string;
  orders: number;
  gross_points?: number;
  penalty_points?: number;
  net_points?: number;
  estimated_payment: number;
};

export type PenaltyRule = {
  id: number;
  name: string;
  penalty_type: string;
  points: number;
  calculation_mode: string;
  active: boolean;
};

export type DiagnosisActionType = "subtract_points" | "cancel_points" | "no_penalty" | "requires_review" | "force_points";

export type DiagnosisPenaltyRule = {
  id: number;
  diagnosis_name: string;
  penalty_points: number;
  force_points_value: number | null;
  action_type: DiagnosisActionType;
  description: string | null;
  active: boolean;
  created_at: string | null;
  updated_at: string | null;
};

export type ImportedDiagnosis = {
  diagnosis_name: string;
  service_orders_count: number;
  subjects_count: number;
  collaborators_count: number;
  predominant_regional: string;
  related_subjects: string[];
  action_type: DiagnosisActionType | null;
  penalty_points: number | null;
  force_points_value: number | null;
  estimated_impact: number;
  active: boolean | null;
  rule_id: number | null;
  has_rule: boolean;
};

export type HealthRule = {
  id: number;
  name: string;
  min_sla: number;
  max_recurrence_rate: number;
  multiplier: number;
  condition_operator: string;
  active: boolean;
};

export type SlaPenaltyType = "none" | "subtract_points" | "percentage_reduction" | "cancel_points" | "requires_review";

export type SlaPenaltyRule = {
  id: number;
  name: string;
  condition_type: "status_sla_out_of_time" | "sla_hours_greater_than" | "closed_after_deadline";
  penalty_type: SlaPenaltyType;
  penalty_value: number;
  active: boolean;
  created_at: string | null;
  updated_at: string | null;
};

export type RecurrenceClassification =
  | "recorrencia_operacional"
  | "reincidencia_tecnica"
  | "garantia"
  | "possivel_retorno_sem_regra"
  | "os_nao_reincidente"
  | "demandas_diferentes"
  | "nao_identificado";

export type RecurrenceClassificationRule = {
  id: number;
  name: string;
  os_type_pattern: string | null;
  os_subject_pattern: string | null;
  diagnosis_pattern: string | null;
  original_os_type_pattern: string | null;
  original_os_subject_pattern: string | null;
  return_os_type_pattern: string | null;
  return_os_subject_pattern: string | null;
  return_diagnosis_pattern: string | null;
  ignore_diagnosis_pattern: string | null;
  classification: RecurrenceClassification;
  discount_points: boolean;
  max_days: number | null;
  require_same_subject: boolean;
  require_same_diagnosis: boolean;
  priority: number;
  description: string | null;
  active: boolean;
  created_at: string | null;
  updated_at: string | null;
};

export type GamificationConfig = {
  name: string;
  version_id: number | null;
  exported_at: string | null;
  settings: Record<string, string>;
  scoring_groups: ScoringGroup[];
  scoring_subject_rules: Array<ScoringSubjectRule & { group_name?: string | null }>;
  diagnosis_penalty_rules: DiagnosisPenaltyRule[];
  sla_penalty_rules: SlaPenaltyRule[];
  recurrence_classification_rules: RecurrenceClassificationRule[];
  health_rules: HealthRule[];
};

export type AppSetting = {
  key: string;
  value: string;
  description: string | null;
};

export type ImportErrorItem = {
  row: number;
  reason: string;
  data: Record<string, unknown>;
};

export type ImportPreview = {
  total_rows: number;
  detected_columns: string[];
  normalized_columns: string[];
  mapped_columns: Record<string, string>;
  sample_rows: Record<string, unknown>[];
  errors: ImportErrorItem[];
};

export type ImportResult = {
  imported: number;
  ignored: number;
  errors: ImportErrorItem[];
  first_errors: ImportErrorItem[];
  detected_columns: string[];
  mapped_columns: Record<string, string>;
  summary: {
    total_rows: number;
    valid_rows: number;
    invalid_rows: number;
  };
  import_id: number | null;
};

export type CollaboratorOrderDetail = {
  id: number;
  os_code: string;
  contract_id: string;
  customer_login: string | null;
  customer_name: string;
  regional: string;
  os_type: string;
  os_subject: string;
  diagnosis: string;
  status: string;
  sla_status: string;
  sla_status_normalized: string;
  sla_hours: number | null;
  closing_time_hours: number | null;
  opened_at: string;
  closed_at: string | null;
  is_warranty: boolean;
  is_recurrence: boolean;
  has_reschedule: boolean;
  has_pending: boolean;
  group_id: number | null;
  group_name: string | null;
  subject_rule_id: number | null;
  rule_applied: string | null;
  effective_points: number;
  group_base_points: number;
  subject_override_points: number | null;
  use_group_default: boolean | null;
  custom_points: number | null;
  point_value: number;
  point_value_source: string | null;
  point_value_override: number | null;
  recurrence_classification: RecurrenceClassification | null;
  recurrence_discount_applied: boolean;
  recurrence_related_os_code: string | null;
  recurrence_days_between: number | null;
  recurrence_evidence: string[];
  recurrence_penalty_points: number;
  recurrence_rule_id: number | null;
  recurrence_rule_name: string | null;
  base_points: number;
  penalty_points: number;
  sla_penalty_points: number;
  sla_penalty_reason: string | null;
  sla_rule_id: number | null;
  sla_penalty_type: SlaPenaltyType | null;
  additional_penalty_points: number;
  net_points: number;
  scoring_rule_name: string | null;
  diagnosis_rule_id: number | null;
  diagnosis_rule_applied: string | null;
  diagnosis_action_type: DiagnosisActionType | null;
  diagnosis_rule_description: string | null;
  diagnosis_penalty_points: number;
  diagnosis_penalty_reason: string | null;
  diagnosis_force_points_value: number | null;
  requires_manual_review: boolean;
  scoring_status: string;
  penalty_reasons: string[];
  reasons: string[];
  is_scored: boolean;
  is_unscored: boolean;
  is_penalized: boolean;
  is_annulled: boolean;
  is_sla_out_of_time: boolean;
};

export type CollaboratorOrdersDetail = {
  collaborator: {
    id: number;
    name: string;
    role: string | null;
    regional: string;
  };
  period: {
    reference_month: number;
    reference_year: number;
    regional: string | null;
  };
  summary: {
    total_service_orders: number;
    scored_service_orders: number;
    unscored_service_orders: number;
    penalized_service_orders: number;
    warranty_service_orders: number;
    recurrence_service_orders: number;
    rescheduled_service_orders: number;
    pending_service_orders: number;
    sla_out_service_orders: number;
    annulled_service_orders: number;
    diagnosis_penalized_service_orders: number;
    manual_review_service_orders: number;
    diagnosis_unmapped_service_orders: number;
    gross_points: number;
    penalty_points: number;
    net_points: number;
    health_multiplier: number;
    final_points: number;
    estimated_payment: number;
  };
  orders: CollaboratorOrderDetail[];
};

export type CollaboratorOrderFilters = {
  calculation_run_id?: number;
  regional?: string;
  only_scored?: boolean;
  only_unscored?: boolean;
  only_penalized?: boolean;
  only_sla_out?: boolean;
  only_warranty?: boolean;
  only_recurrence?: boolean;
  only_non_recurrent?: boolean;
  only_diagnosis_blocked?: boolean;
  group_id?: number;
  os_type?: string;
  os_subject?: string;
  status_sla?: string;
  audit_group_mode?: string;
  audit_group_label?: string;
  page?: number;
  page_size?: number;
};

export type RecurrenceAudit = {
  identity_type: string;
  identity_value: string;
  classification: RecurrenceClassification | null;
  discount_target_os_code: string | null;
  discount_points: number;
  discount_applied: boolean;
  evidence: string[];
  current_order: CollaboratorOrderDetail & { collaborator_id: number; collaborator_name: string };
  origin_order: (CollaboratorOrderDetail & { collaborator_id: number; collaborator_name: string }) | null;
  posterior_order: (CollaboratorOrderDetail & { collaborator_id: number; collaborator_name: string }) | null;
  related_orders: Array<CollaboratorOrderDetail & { collaborator_id: number; collaborator_name: string }>;
};

export type AuditOrders = {
  period: {
    reference_month: number;
    reference_year: number;
    regional: string | null;
  };
  summary: {
    total_service_orders: number;
    scored_service_orders: number;
    unscored_service_orders: number;
    penalized_service_orders: number;
    warranty_service_orders: number;
    recurrence_service_orders: number;
    rescheduled_service_orders: number;
    pending_service_orders: number;
    sla_out_service_orders: number;
    annulled_service_orders: number;
    diagnosis_penalized_service_orders: number;
    manual_review_service_orders: number;
    diagnosis_unmapped_service_orders: number;
    gross_points: number;
    penalty_points: number;
    net_points: number;
    final_points: number;
    estimated_payment: number;
  };
  orders: Array<CollaboratorOrderDetail & { collaborator_id: number; collaborator_name: string }>;
  group_summaries?: Record<string, Array<{
    label: string;
    service_orders_count: number;
    base_points: number;
    penalty_points: number;
    net_points: number;
    estimated_payment: number;
    unscored_service_orders: number;
    penalized_service_orders: number;
  }>>;
  total_orders: number;
  page: number;
  page_size: number;
  total_pages: number;
};
