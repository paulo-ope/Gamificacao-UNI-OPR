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
  | "users:manage"
  | "portal:read_self"
  | "portal:read_regional_ranking"
  | "portal:simulate_self"
  | "portal:read_rules"
  | "portal:read_regional_summary"
  | "portal:read_overview"
  | "operations:read"
  | "operations:manage"
  | "operations:views:read_global"
  | "operations:views:create_global"
  | "operations:views:update_global"
  | "operations:views:delete_global"
  | "operations:sync_ixc"
  | "operations:manage_filters"
  | "operations:manage_team_models"
  | "operations:manage_subjects"
  | "operations:view_order_details"
  | "operations:view_openings"
  | "operations:view_sla"
  | "operations:view_warranty"
  | "operations:view_calendar"
  | "operations:view_backlog"
  | "operations:export"
  | "scheduling:read"
  | "scheduling:sync"
  | "scheduling:manage"
  | "scheduling:manage_filters"
  | "scheduling:views:read_global"
  | "scheduling:views:manage_global"
  | "management:read"
  | "management:manage_structure"
  | "management:write_justification"
  | "management:review"
  | "management:admin"
  | "admin:users:read"
  | "admin:users:write"
  | "admin:users:delete"
  | "admin:roles:read"
  | "admin:roles:write"
  | "admin:permissions:read"
  | "admin:modules:read"
  | "admin:modules:write"
  | "admin:audit:read";

export type AuthUser = {
  id: number;
  name: string;
  email: string;
  role: "collaborator" | "regional_manager_viewer" | "viewer" | "operator" | "admin";
  active: boolean;
  created_at: string;
  updated_at: string;
  permissions: Permission[];
  access_profile_ids: number[];
  access_profile_names: string[];
  collaborator_id: number | null;
  collaborator_name: string | null;
  managed_regional: string | null;
  managed_regionals: string[];
};

export type EcosystemPermission = {
  key: Permission;
  label: string;
  module: string;
};

export type AccessProfile = {
  id: number;
  name: string;
  description: string | null;
  legacy_role: string | null;
  active: boolean;
  is_system: boolean;
  permission_keys: Permission[];
  user_count: number;
  created_at: string;
  updated_at: string;
};

export type ManagementSummary = {
  total_members: number;
  active_members: number;
  pending_validation: number;
  without_supervisor: number;
  without_team_model: number;
  without_gamification: number;
  conflicts: number;
  open_cases: number;
  overdue_cases: number;
};

export type ManagementOperationalMember = {
  id: number;
  collaborator_id: number | null;
  collaborator_name: string | null;
  collaborator_is_registered: boolean | null;
  collaborator_employee_type: string | null;
  collaborator_team_type: string | null;
  collaborator_structure_status: string | null;
  collaborator_supervisor_user_id: number | null;
  collaborator_supervisor_name: string | null;
  gamification_status: "registered" | "pending" | "missing" | "inactive" | string;
  ixc_employee_id: number | null;
  responsible_name: string;
  regional: string;
  supervisor_user_id: number | null;
  supervisor_name: string | null;
  team_model_id: number | null;
  team_model_name: string | null;
  status: string;
  source: string;
  is_active: boolean;
  notes: string | null;
  last_order_at: string | null;
  alerts: string[];
  created_at: string;
  updated_at: string;
};

export type WorkspaceVisibleModule = {
  key: "gamification" | "operations" | "scheduling" | "management" | "admin";
  name: string;
  description: string;
  web_path: string;
  api_prefix: string;
  required_permission: Permission;
  status: "active" | "planned" | "disabled" | string;
};

export type AdminModuleProfileVisibility = {
  profile_id: number;
  profile_name: string;
  visible: boolean;
  has_required_permission: boolean;
};

export type AdminModuleUserVisibility = {
  user_id: number;
  user_name: string;
  user_email: string;
  visible: boolean;
  reason: string | null;
};

export type AdminWorkspaceModule = WorkspaceVisibleModule & {
  profiles: AdminModuleProfileVisibility[];
  user_overrides: AdminModuleUserVisibility[];
};

export type AdminStructureOption = {
  id: number;
  name: string;
};

export type AdminPeopleStructureSummary = {
  total_people: number;
  active_people: number;
  without_supervisor: number;
  without_team_type: number;
  pending_review: number;
  field_team: number;
  scheduling_team: number;
};

export type AdminPersonStructure = {
  id: number;
  name: string;
  role: string;
  regional: string;
  active: boolean;
  is_registered: boolean;
  cpf_masked: string | null;
  employee_type: string | null;
  team_type: string | null;
  supervisor_user_id: number | null;
  supervisor_name: string | null;
  regional_manager_user_id: number | null;
  regional_manager_name: string | null;
  structure_status: string;
  structure_notes: string | null;
  ixc_employee_id: number | null;
  portal_user_id: number | null;
  portal_user_email: string | null;
  has_photo: boolean;
};

export type AdminPeopleStructure = {
  summary: AdminPeopleStructureSummary;
  people: AdminPersonStructure[];
  supervisors: AdminStructureOption[];
  regional_managers: AdminStructureOption[];
  employee_types: string[];
  team_types: string[];
  statuses: string[];
};

export type ManagementDashboard = {
  summary: ManagementSummary;
  members: ManagementOperationalMember[];
};

export type ManagementOption = {
  id: number;
  name: string;
};

export type ManagementOptions = {
  supervisors: ManagementOption[];
  team_models: ManagementOption[];
};

export type ManagementCaseReason = {
  id: number;
  name: string;
  description: string | null;
  active: boolean;
  requires_description: boolean;
  created_at: string;
  updated_at: string;
};

export type ManagementCase = {
  id: number;
  case_type: string;
  source_module: string;
  reference_date: string | null;
  reference_month: number | null;
  reference_year: number | null;
  regional: string | null;
  collaborator_id: number | null;
  collaborator_name: string | null;
  responsible_name: string | null;
  supervisor_user_id: number | null;
  supervisor_name: string | null;
  team_model_id: number | null;
  team_model_name: string | null;
  metric_name: string;
  expected_value: number | null;
  actual_value: number | null;
  deviation_value: number | null;
  severity: string;
  status: string;
  reason_id: number | null;
  reason_name: string | null;
  justification_text: string | null;
  action_plan: string | null;
  due_date: string | null;
  created_at: string;
  updated_at: string;
  justified_at: string | null;
  reviewed_by: number | null;
  reviewed_at: string | null;
};

export type LoginResult = {
  access_token: string;
  token_type: string;
  user: AuthUser;
};

export type PortalPeriod = {
  calculation_run_id: number | null;
  reference_month: number | null;
  reference_year: number | null;
  status: string | null;
  updated_at: string | null;
};

export type PortalCollaborator = {
  id: number;
  name: string;
  role: string | null;
  regional: string;
};

export type PortalScore = {
  collaborator_id: number;
  collaborator_name: string;
  role: string | null;
  regional: string;
  service_orders_count: number;
  gross_points: number;
  penalty_points: number;
  net_points: number;
  health_multiplier: number;
  health_status: string;
  final_points: number;
  estimated_payment: number;
  balance_adjustment_points: number;
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

export type PortalRankingItem = {
  position: number;
  collaborator_id: number;
  collaborator_name: string;
  role: string | null;
  regional: string;
  final_points: number;
  estimated_payment: number;
  service_orders_count: number;
  scored_service_orders: number;
  penalty_points: number;
  health_multiplier: number;
  health_status: string | null;
  sla_out_service_orders: number;
  recurrence_service_orders: number;
  unscored_service_orders: number;
  manual_review_service_orders: number;
  points_to_average: number | null;
  performance_band: string | null;
  is_current_user: boolean;
};

export type PortalSummary = {
  user: AuthUser;
  collaborator: PortalCollaborator | null;
  period: PortalPeriod;
  score: PortalScore | null;
  regional_position: number | null;
  regional_total: number;
  regional_service_orders: number;
  regional_sla_out_service_orders: number;
  regional_sla_rate: number | null;
  general_position: number | null;
  general_total: number;
  next_position_gap: number | null;
  ranking: PortalRankingItem[];
  message: string | null;
};

export type PortalProfile = {
  collaborator_id: number;
  name: string;
  role: string;
  regional: string;
  phone: string | null;
  email: string | null;
  has_photo: boolean;
};

export type PortalOrder = {
  id: number;
  os_code: string;
  opened_at: string;
  closed_at: string | null;
  os_type: string;
  os_subject: string;
  customer_name: string | null;
  group_name: string | null;
  diagnosis: string | null;
  status: string;
  sla_status: string;
  sla_status_normalized: string;
  base_points: number;
  penalty_points: number;
  net_points: number;
  status_label: string;
  reason: string | null;
  diagnosis_action_type: DiagnosisActionType | null;
  diagnosis_penalty_reason: string | null;
  recurrence_related_os_code: string | null;
  recurrence_days_between: number | null;
};

export type PortalAuditOrder = {
  os_code: string;
  os_type: string;
  os_subject: string;
  customer_name: string | null;
  group_name: string | null;
  base_points: number;
  net_points: number;
  penalty_points: number;
  status_label: string;
  sla_status_normalized: string;
  reason: string | null;
  diagnosis_action_type: DiagnosisActionType | null;
  diagnosis_penalty_reason: string | null;
  recurrence_related_os_code: string | null;
  recurrence_days_between: number | null;
};

export type PortalAuditBreakdown = {
  label: string;
  service_orders: number;
  base_points: number;
  penalty_points: number;
  net_points: number;
};

export type PortalAuditHistory = {
  reference_month: number;
  reference_year: number;
  final_points: number;
  estimated_payment: number;
  service_orders_count: number;
};

export type PortalScoreStep = {
  key: string;
  label: string;
  value: number;
  kind: "positive" | "negative" | "neutral" | "subtotal" | "total" | string;
  description: string | null;
};

export type PortalCpkInsight = {
  status: "na_meta" | "fora_meta" | "sem_base" | null;
  status_label: string;
  cpk_realizado: number | null;
  cpk_meta: number | null;
  adjustment: number;
  mes_fechado: boolean;
  synced_at: string | null;
  description: string;
};

export type PortalAudit = {
  gross_points: number;
  penalty_points: number;
  net_points: number;
  health_multiplier: number;
  final_points: number;
  estimated_payment: number;
  balance_adjustment_points: number;
  health_status: string;
  service_orders_count: number;
  scored_service_orders: number;
  unscored_service_orders: number;
  penalized_service_orders: number;
  warranty_service_orders: number;
  recurrence_service_orders: number;
  pending_service_orders: number;
  sla_out_service_orders: number;
  sla_on_time_service_orders: number;
  sla_unidentified_service_orders: number;
  sla_rate: number | null;
  manual_review_service_orders: number;
  points_to_next_position: number | null;
  top_positive_orders: PortalAuditOrder[];
  attention_orders: PortalAuditOrder[];
  groups: PortalAuditBreakdown[];
  subjects: PortalAuditBreakdown[];
  orders: PortalAuditOrder[];
  history: PortalAuditHistory[];
  score_steps: PortalScoreStep[];
  cpk: PortalCpkInsight | null;
  message: string | null;
};

export type PortalRules = {
  groups: Array<Record<string, string | number | boolean | null>>;
  subjects: Array<Record<string, string | number | boolean | null>>;
  diagnosis_rules: Array<Record<string, string | number | boolean | null>>;
  sla_rules: Array<Record<string, string | number | boolean | null>>;
  recurrence_rules: Array<Record<string, string | number | boolean | null>>;
};

export type PortalSimulation = {
  current_position: number | null;
  simulated_position: number | null;
  extra_points: number;
  points_to_next: number | null;
  disclaimer: string;
};

export type PortalRegionalOverview = {
  regional: string;
  collaborators: number;
  service_orders: number;
  scored_service_orders: number;
  final_points: number;
  estimated_payment: number;
  penalty_points: number;
  health_average: number;
  sla_out_service_orders: number;
  recurrence_service_orders: number;
  unscored_service_orders: number;
  manual_review_service_orders: number;
  sla_rate: number;
  recurrence_rate: number;
};

export type PortalTeamHistoryItem = {
  reference_month: number;
  reference_year: number;
  collaborators: number;
  service_orders: number;
  sla_out_service_orders: number;
  recurrence_service_orders: number;
  final_points: number;
  estimated_payment: number;
  health_average: number;
  sla_rate: number;
  recurrence_rate: number;
};

export type PortalTeamAttentionItem = PortalRankingItem & {
  attention_reason: string;
  target_gap: number;
};

export type PortalTeamBand = {
  label: string;
  collaborators: number;
  min_points: number;
  max_points: number;
  description: string;
};

export type PortalTeamSummary = {
  period: PortalPeriod;
  regional: string | null;
  regionals: string[];
  totals: PortalRegionalOverview | null;
  ranking: PortalRankingItem[];
  attention: PortalTeamAttentionItem[];
  history: PortalTeamHistoryItem[];
  bands: PortalTeamBand[];
  alerts: string[];
  message: string | null;
};

export type PortalOverview = {
  period: PortalPeriod;
  total_collaborators: number;
  total_regionals: number;
  total_service_orders: number;
  scored_service_orders: number;
  final_points: number;
  estimated_payment: number;
  penalty_points: number;
  unscored_service_orders: number;
  manual_review_service_orders: number;
  regional_summary: PortalRegionalOverview[];
  ranking: PortalRankingItem[];
  alerts: string[];
  message: string | null;
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
  balance_adjustment_points: number;
  balance_after: number;
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
  phone: string | null;
  email: string | null;
};

export type CollaboratorRegistryItem = Collaborator & {
  service_orders_count: number;
  suggested_regional: string | null;
  suggested_role: string | null;
  has_linked_orders: boolean;
  has_photo: boolean;
  portal_user_id: number | null;
  portal_user_email: string | null;
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
  config_snapshot: Record<string, unknown> | null;
  status: "draft" | "review" | "approved" | "paid" | "cancelled";
  status_changed_at: string | null;
  status_changed_by: number | null;
  status_note: string | null;
  approved_at: string | null;
  approved_by: number | null;
  paid_at: string | null;
  paid_by: number | null;
  executed_at: string | null;
  executed_by: number | null;
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
  status: "draft" | "review" | "approved" | "paid" | "cancelled";
  status_changed_at: string | null;
  status_changed_by: number | null;
  status_note: string | null;
  approved_at: string | null;
  approved_by: number | null;
  paid_at: string | null;
  paid_by: number | null;
  executed_at: string | null;
  executed_by: number | null;
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

export type CalculationRunSnapshot = {
  id: number;
  config_snapshot: Record<string, unknown> | null;
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
  cpk_status: "na_meta" | "fora_meta" | "sem_base" | null;
  cpk_adjustment: number;
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

export type DashboardFilteredBreakdown = {
  calculation_run_id: number;
  regionals: string[];
  penalty_distribution: PenaltyDistributionItem[];
  cost_by_regional: FinancialBreakdownItem[];
  cost_by_group: FinancialBreakdownItem[];
  top_unmapped_subjects: FinancialBreakdownItem[];
};

export type DashboardBootstrap = {
  reference_month: number | null;
  reference_year: number | null;
  regional: string | null;
  point_value: number;
  has_calculation_run: boolean;
  calculation_run_id: number | null;
};

export type LeadershipRoleType = "supervisor" | "regional_manager" | "portfolio_manager";
export type LeadershipAverageSource = "collaborators" | "collaborators_and_leaders";

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
  average_source: LeadershipAverageSource;
  active: boolean;
  collaborator_id: number | null;
  regional_names: string[];
  created_at: string;
  updated_at: string;
};

export type LeadershipAverageAuditCollaborator = {
  collaborator_id: number;
  collaborator_name: string;
  role: string;
  regional: string;
  source_type: "collaborator" | "leader";
  service_orders_count: number;
  health_multiplier: number;
  final_points: number;
  estimated_payment: number;
};

export type LeadershipAverageAudit = {
  scoped_collaborators: number;
  total_final_points: number;
  average_final_points: number;
  point_value: number;
  base_amount: number;
  multiplier: number;
  bonus_amount: number;
  collaborators: LeadershipAverageAuditCollaborator[];
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
  average_source: LeadershipAverageSource;
  average_final_points: number;
  scoped_collaborators: number;
  point_value: number;
  base_amount: number;
  bonus_amount: number;
  regionals: string[];
  audit: LeadershipAverageAudit | null;
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
  active: boolean;
};

export type CpkRegionalSnapshot = {
  regional: string;
  status: "na_meta" | "fora_meta" | "sem_base";
  cpk_realizado: number | null;
  cpk_meta: number | null;
  mes_fechado: boolean;
  synced_at: string;
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
  min_hours_between: number | null;
  require_same_subject: boolean;
  require_same_diagnosis: boolean;
  priority: number;
  description: string | null;
  active: boolean;
  created_at: string | null;
  updated_at: string | null;
};

export type GamificationConfigLeadershipRoleProfile = {
  id: number | null;
  name: string;
  scope_type: LeadershipRoleType;
  default_multiplier: number;
  active: boolean;
};

export type GamificationConfigLeadershipProfile = {
  id: number | null;
  name: string;
  role_type: LeadershipRoleType;
  multiplier: number;
  role_profile_id: number | null;
  role_profile_name: string | null;
  use_custom_multiplier: boolean;
  custom_multiplier: number | null;
  average_source: LeadershipAverageSource;
  active: boolean;
  collaborator_ixc_employee_id: number | null;
  collaborator_name: string | null;
  regional_names: string[];
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
  collaborators?: GamificationConfigCollaborator[];
  leadership_role_profiles?: GamificationConfigLeadershipRoleProfile[];
  leadership_profiles?: GamificationConfigLeadershipProfile[];
  warnings?: string[];
};

export type GamificationConfigCollaborator = {
  id: number;
  name: string;
  role: string;
  regional: string;
  active: boolean;
  is_registered: boolean;
  ixc_employee_id: number | null;
  phone: string | null;
  email: string | null;
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
  status: string;
  imported: number;
  ignored: number;
  errors: ImportErrorItem[];
  first_errors: ImportErrorItem[];
  detected_columns: string[];
  mapped_columns: Record<string, string>;
  summary: {
    total_rows: number;
    processed_rows: number;
    created_count: number;
    updated_count: number;
    skipped_count: number;
    rejected_count: number;
    error_count: number;
    missing_date_count: number;
    duplicate_count: number;
    unknown_collaborator_count: number;
    required_field_missing_count: number;
    paid_period_blocked_count: number;
    valid_rows: number;
    invalid_rows: number;
  };
  import_id: number | null;
  file_name: string | null;
  file_hash: string | null;
  message: string | null;
};

export type ImportRun = {
  id: number;
  filename: string;
  file_hash: string | null;
  source: string;
  status: string;
  total_rows: number;
  processed_rows: number;
  imported_rows: number;
  created_count: number;
  updated_count: number;
  skipped_count: number;
  rejected_count: number;
  duplicate_count: number;
  missing_date_count: number;
  unknown_collaborator_count: number;
  required_field_missing_count: number;
  paid_period_blocked_count: number;
  ignored_rows: number;
  error_rows: number;
  imported_by: number | null;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
  notes: string | null;
  detected_columns: string[];
  mapped_columns: Record<string, string>;
  errors: Record<string, unknown>[];
  created_at: string;
};

export type ImportServiceOrderAudit = {
  id: number;
  import_run_id: number;
  os_code: string | null;
  service_order_id: number | null;
  action: string;
  field_name: string | null;
  old_value: string | null;
  new_value: string | null;
  reason: string | null;
  row_number: number | null;
  created_at: string;
  created_by: number | null;
};

export type CollaboratorMonthlyHistoryItem = {
  reference_month: number;
  reference_year: number;
  regional: string | null;
  calculation_run_id: number;
  status: string;
  service_orders_count: number;
  gross_points: number;
  net_points: number;
  final_points: number;
  estimated_payment: number;
  balance_adjustment_points: number;
  health_multiplier: number;
};

export type AuditLog = {
  id: number;
  user_id: number | null;
  user_name: string | null;
  user_email: string | null;
  action: string;
  entity: string;
  entity_id: string | null;
  before_data: Record<string, unknown> | null;
  after_data: Record<string, unknown> | null;
  created_at: string;
};

export type PointBalanceEntry = {
  // Calculado pelo backend em relacao ao periodo consultado (nao existe no banco): "applied" = ja
  // descontado deste fechamento; "eligible_pending" = pendente, seria descontado se este
  // fechamento fosse pago agora; "deferred_pending" = pendente com alvo num mes posterior.
  bucket: "applied" | "eligible_pending" | "deferred_pending";
  id: number;
  collaborator_id: number;
  collaborator_name: string | null;
  entry_type: "post_payment_warranty_debit" | "period_settlement" | "manual_adjustment";
  points: number;
  original_service_order_id: number | null;
  original_os_code: string | null;
  related_service_order_id: number | null;
  related_os_code: string | null;
  origin_calculation_run_id: number | null;
  origin_run_month: number | null;
  origin_run_year: number | null;
  origin_run_status: string | null;
  target_reference_month: number | null;
  target_reference_year: number | null;
  applied_calculation_run_id: number | null;
  applied_run_status: string | null;
  applied_reference_month: number | null;
  applied_reference_year: number | null;
  status: "pending" | "applied" | "reverted";
  requires_review: boolean;
  recurrence_classification: string | null;
  recurrence_action: string | null;
  reason: string | null;
  created_by: number | null;
  created_at: string;
};

export type CollaboratorPointBalance = {
  collaborator_id: number;
  collaborator_name: string | null;
  balance_points: number;
  updated_at: string | null;
  entries: PointBalanceEntry[];
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
