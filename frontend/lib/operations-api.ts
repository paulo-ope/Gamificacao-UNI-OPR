export type OperationPeriod = {
  date_from: string;
  date_to: string;
  allowed_from: string;
  allowed_to: string;
  timezone: string;
};

export type OperationFilters = {
  team_models: string[];
  companies: string[];
  regionals: string[];
  states: string[];
  cities: string[];
  contract_types: string[];
  person_types: string[];
  os_types: string[];
  subjects: string[];
  diagnoses: string[];
  departments: string[];
  sectors: string[];
  priorities: string[];
  creators: string[];
  responsibles: string[];
  statuses: string[];
  sla_statuses: string[];
  projects: string[];
  pops: string[];
  opened_weekdays: string[];
  closed_weekdays: string[];
};

export type OperationOverview = {
  opened: number;
  opened_associated: number;
  responsible_filter_active: boolean;
  completed: number;
  in_progress: number;
  opened_out_of_time: number;
  completed_on_time: number;
  completed_out_of_time: number;
  sla_rate: number | null;
  average_daily_opened: number;
  average_daily_completed: number;
  average_closing_hours: number | null;
  average_wait_to_displacement_minutes: number | null;
  average_cycle_minutes: number | null;
};

export type OperationWorkScheduleOverview = {
  completed: number;
  classified: number;
  outside_schedule: number;
  before_start: number;
  after_end: number;
  unclassified: number;
  outside_rate: number | null;
  selected_model_ids: number[];
  available_models: Array<{ id: number; name: string }>;
  by_model: Array<{
    model_id: number;
    model_name: string;
    completed: number;
    outside_schedule: number;
    before_start: number;
    after_end: number;
    unclassified: number;
  }>;
};

export type OperationTrendGranularity = "day" | "week" | "month";

export type OperationTrendPoint = {
  period_start: string;
  period_end: string;
  opened_operation: number;
  opened_associated: number;
  completed: number;
  completed_on_time: number;
  completed_out_of_time: number;
  completed_unmeasurable: number;
  sla_rate: number | null;
  sla_cumulative_rate: number | null;
};

export type OperationTrendSeries = {
  granularity: OperationTrendGranularity;
  responsible_filter_active: boolean;
  openings_ignore_responsibles: boolean;
  points: OperationTrendPoint[];
};

export type OperationSubjectVolumeAlert = {
  subject: string;
  current_backlog: number;
  recent_average: number;
  expected_backlog: number;
  deviation_percentage: number | null;
  z_score: number | null;
  status: "normal" | "attention" | "critical" | "insufficient";
  sample_days: number;
};

export type OperationSubjectVolumeAlerts = {
  reference_date: string;
  baseline_days: number;
  recent_days: number;
  responsibles_ignored: boolean;
  items: OperationSubjectVolumeAlert[];
};

export type OperationControlTowerLevel =
  | "subject"
  | "regional"
  | "city"
  | "sector"
  | "responsible";
export type OperationControlTowerStatus =
  | "normal"
  | "attention"
  | "critical"
  | "insufficient";
export type OperationControlTowerPath = Partial<
  Record<OperationControlTowerLevel, string>
>;

export type OperationControlTowerSummary = {
  status: OperationControlTowerStatus;
  opened_recent: number;
  expected_opened: number;
  deviation_percentage: number | null;
  completed_recent: number;
  net_flow: number;
  pressure_ratio: number | null;
  backlog: number;
  overdue_backlog: number;
  average_backlog_age_hours: number | null;
  persistent_days: number;
  critical_nodes: number;
  attention_nodes: number;
  reasons: string[];
};

export type OperationControlTowerItem = Omit<
  OperationControlTowerSummary,
  "critical_nodes" | "attention_nodes"
> & {
  label: string;
  level: OperationControlTowerLevel;
  path: OperationControlTowerPath;
  has_children: boolean;
};

export type OperationControlTowerTimelinePoint = {
  date: string;
  opened: number;
  completed: number;
  expected_opened: number;
  upper_limit: number;
  outside_expected: boolean;
  backlog: number;
};

export type OperationControlTower = {
  reference_date: string;
  level: OperationControlTowerLevel;
  next_level: Exclude<OperationControlTowerLevel, "subject"> | null;
  path: OperationControlTowerPath;
  recent_days: number;
  baseline_weeks: number;
  timeline_days: number;
  responsibles_ignored: boolean;
  calculation_note: string;
  summary: OperationControlTowerSummary;
  timeline: OperationControlTowerTimelinePoint[];
  items: OperationControlTowerItem[];
};

export type OperationOpeningsSummary = {
  opened: number;
  completed: number;
  net_flow: number;
  pressure_ratio: number | null;
  average_daily_opened: number;
  expected_opened: number;
  deviation_percentage: number | null;
  backlog: number;
  overdue_backlog: number;
  without_responsible: number;
  average_first_action_minutes: number | null;
};

export type OperationOpeningsTimelinePoint = {
  date: string;
  opened: number;
  completed: number;
  expected_opened: number;
  upper_limit: number;
  outside_expected: boolean;
  backlog: number;
};

export type OperationOpeningsHeatmapItem = {
  weekday: number;
  hour: number;
  opened: number;
};

export type OperationOpeningsRankingItem = {
  label: string;
  opened: number;
  completed: number;
  backlog: number;
  overdue_backlog: number;
  share_percentage: number;
};

export type OperationOpeningsAgingItem = {
  bucket: string;
  label: string;
  quantity: number;
};

export type OperationOpeningsInsight = {
  severity: OperationControlTowerStatus;
  title: string;
  description: string;
};

export type OpeningsDrillField =
  | "regionals"
  | "cities"
  | "subjects"
  | "os_types"
  | "sectors"
  | "priorities"
  | "creators"
  | "pops"
  | "contract_types"
  | "person_types";

export type OpeningsDrillTarget =
  | { kind: "dimension"; field: OpeningsDrillField; value: string; key: string }
  | { kind: "aging"; bucket: string; label: string; key: string }
  | { kind: "heatmap"; weekday: number; hour: number; label: string; key: string };

export type OperationOpeningsAnalytics = {
  date_from: string;
  date_to: string;
  baseline_weeks: number;
  granularity: OperationTrendGranularity;
  calculation_note: string;
  summary: OperationOpeningsSummary;
  timeline: OperationOpeningsTimelinePoint[];
  heatmap: OperationOpeningsHeatmapItem[];
  aging: OperationOpeningsAgingItem[];
  rankings: Record<string, OperationOpeningsRankingItem[]>;
  insights: OperationOpeningsInsight[];
};

export type OperationDataFreshness = {
  last_successful_import_at: string | null;
  status: string | null;
  date_from: string | null;
  date_to: string | null;
};

export type OperationSlaItem = {
  label: string;
  completed: number;
  on_time: number;
  out_of_time: number;
  sla_rate: number | null;
  up_to_12h: number;
  from_12h_to_24h: number;
  from_24h_to_48h: number;
  from_48h_to_72h: number;
  after_72h: number;
  average_closing_hours: number | null;
};

export type OperationSlaHierarchyLevel = "os_type" | "subject" | "diagnosis";

export type OperationSlaHierarchyItem = {
  label: string;
  completed: number;
  on_time: number;
  out_of_time: number;
  sla_rate: number | null;
  timed_orders: number;
  up_to_12h_rate: number | null;
  from_12h_to_24h_rate: number | null;
  from_24h_to_48h_rate: number | null;
  from_48h_to_72h_rate: number | null;
  after_72h_rate: number | null;
  average_closing_hours: number | null;
};

export type OperationSlaHierarchy = {
  level: OperationSlaHierarchyLevel;
  parent_os_type: string | null;
  parent_subject: string | null;
  items: OperationSlaHierarchyItem[];
  total: OperationSlaHierarchyItem;
};

export type OperationCollaboratorSlaItem = {
  responsible: string;
  regional: string;
  completed: number;
  on_time: number;
  out_of_time: number;
  sla_rate: number | null;
  active_days: number;
  daily_average: number;
  measurable_execution_orders: number;
  average_execution_minutes: number | null;
  minimum_execution_minutes: number | null;
  maximum_execution_minutes: number | null;
  type_counts: Record<string, number>;
  scheduled_orders: number;
  schedule_adherence_rate: number | null;
};

export type OperationCollaboratorSla = {
  type_columns: string[];
  items: OperationCollaboratorSlaItem[];
};

export type OperationCalendarDay = {
  date: string;
  day: number;
  weekday: number;
  week: number;
  available: boolean;
};

export type OperationCalendarCollaborator = {
  responsible: string;
  total: number;
  daily_counts: Record<string, number>;
  daily_performance: Record<string, OperationPerformanceBand>;
  monthly_performance: OperationPerformanceBand;
  team_model: OperationCalendarTeamModel | null;
  reference_regional: string | null;
  attended_regionals: string[];
};

export type OperationPerformanceBand =
  | "neutral"
  | "below"
  | "median"
  | "good"
  | "excellent";

export type OperationCalendarTeamModel = {
  id: number;
  name: string;
  daily_target: number;
  median_from_quantity: number;
  good_from_quantity: number;
  below_target_color: string;
  median_color: string;
  good_color: string;
  excellent_color: string;
  target_rules: OperationTeamTargetRule[];
};

export type OperationTeamTargetRule = {
  id?: number;
  period_type: "weekday" | "saturday" | "sunday" | "monthly";
  enabled: boolean;
  median_from_quantity: number;
  good_from_quantity: number;
  target_quantity: number;
  start_time: string | null;
  end_time: string | null;
};

export type OperationCalendarRegional = {
  regional: string;
  total: number;
  daily_counts: Record<string, number>;
  collaborators: OperationCalendarCollaborator[];
};

export type OperationCalendar = {
  competence: string;
  date_from: string;
  date_to: string;
  group_by: "regional" | "collaborator";
  days: OperationCalendarDay[];
  regionals: OperationCalendarRegional[];
};

export type OperationBreakdownItem = {
  label: string;
  quantity: number;
  percentage: number;
};

export type OperationWarrantyPeriodBasis = "opened" | "closed";

export type OperationWarrantyDenominator =
  | "closed_origins"
  | "active_origins"
  | "maintenance_total"
  | "activation_closed";

export type OperationWarrantyItem = {
  contract_id: string | null;
  customer_name: string | null;
  regional: string | null;
  diagnosis: string | null;
  return_os_subject: string | null;
  origin_order_code: string;
  origin_os_type: string | null;
  origin_closed_at: string;
  return_order_code: string;
  return_opened_at: string;
  return_closed_at: string | null;
  origin_order: OperationOrder | null;
  return_order: OperationOrder | null;
};

export type OperationWarrantyRegionalRankingItem = {
  label: string;
  quantity: number;
  denominator_count: number;
  percentage: number | null;
};

export type OperationWarrantyAnalytics = {
  period_basis: OperationWarrantyPeriodBasis;
  denominator: OperationWarrantyDenominator;
  origin_excluded_diagnoses: string[];
  numerator: number;
  denominator_count: number;
  percentage: number | null;
  contracts_with_warranty: number;
  customers_with_warranty: number;
  breakdown: OperationBreakdownItem[];
  by_regional: OperationWarrantyRegionalRankingItem[];
  by_diagnosis: OperationBreakdownItem[];
  by_subject: OperationBreakdownItem[];
  items: OperationWarrantyItem[];
  items_truncated: boolean;
};

export type OperationSlaRiskItem = {
  bucket: "breached" | "critical" | "attention" | "on_track" | "no_target";
  label: string;
  quantity: number;
  percentage: number;
};

export type OperationOrder = {
  id: number;
  source_order_id: string;
  order_code: string;
  protocol: string | null;
  contract_id: string | null;
  customer_name: string | null;
  regional: string | null;
  city: string | null;
  os_type: string | null;
  os_subject: string | null;
  diagnosis: string | null;
  department: string | null;
  sector: string | null;
  priority: string | null;
  creator: string | null;
  responsible: string | null;
  status: string | null;
  status_code: string | null;
  sla_status: string;
  sla_target_hours: number | null;
  elapsed_hours: number | null;
  opened_at: string;
  assumed_at: string | null;
  displacement_started_at: string | null;
  execution_started_at: string | null;
  finished_at: string | null;
  deadline_at: string | null;
  scheduled_at: string | null;
  closed_at: string | null;
  normalization_notes: string | null;
  service_address: string | null;
  service_description: string | null;
  technical_report: string | null;
};

export type OperationOrderPage = {
  items: OperationOrder[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export type OperationCalendarDayMetrics = {
  total_orders: number;
  active_days: number;
  timed_orders: number;
  missing_execution_times: number;
  average_execution_minutes: number | null;
  median_execution_minutes: number | null;
  minimum_execution_minutes: number | null;
  maximum_execution_minutes: number | null;
  average_pre_displacement_minutes: number | null;
  average_total_minutes: number | null;
  sla_rate: number | null;
  first_displacement_at: string | null;
  last_finished_at: string | null;
  operational_window_orders: number;
  missing_operational_window_times: number;
  total_execution_minutes: number | null;
  average_displacement_minutes: number | null;
  total_displacement_minutes: number | null;
  displacement_orders: number;
  attended_regionals: string[];
  cross_regional_orders: number;
  type_counts: Record<string, number>;
};

export type OperationCalendarDayDetail = {
  metrics: OperationCalendarDayMetrics;
  orders: OperationOrderPage;
};

export type OperationCalendarMonthlyMetrics = {
  total_orders: number;
  active_days: number;
  timed_orders: number;
  missing_execution_times: number;
  average_execution_minutes: number | null;
  median_execution_minutes: number | null;
  average_total_minutes: number | null;
  total_execution_minutes: number | null;
  average_displacement_minutes: number | null;
  total_displacement_minutes: number | null;
  displacement_orders: number;
  sla_rate: number | null;
  attended_regionals: string[];
  cross_regional_orders: number;
};

export type OperationCalendarMonthlyDetail = {
  metrics: OperationCalendarMonthlyMetrics;
  by_regional: OperationBreakdownItem[];
  orders: OperationOrderPage;
};

export type OperationImportResult = {
  run_id: number;
  status: string;
  date_from: string;
  date_to: string;
  fetched_count: number;
  created_count: number;
  updated_count: number;
  unchanged_count: number;
  rejected_count: number;
  errors: Array<{ source_order_id?: string | null; reason: string }>;
};

export type OperationBackfillJob = {
  id: number;
  status: "pending" | "running" | "completed" | "failed" | string;
  date_from: string;
  date_to: string;
  next_date: string;
  total_days: number;
  processed_days: number;
  fetched_count: number;
  created_count: number;
  updated_count: number;
  unchanged_count: number;
  rejected_count: number;
  errors: Array<Record<string, unknown>>;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
};

export type OperationOpenBacklogJob = {
  id: number;
  status: "pending" | "running" | "completed" | "failed" | string;
  sector_ids: string[];
  total_sectors: number;
  processed_sectors: number;
  fetched_count: number;
  created_count: number;
  updated_count: number;
  unchanged_count: number;
  rejected_count: number;
  errors: Array<Record<string, unknown>>;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
};

export type OperationIxcSector = {
  id: string;
  name: string;
};

export type OperationIxcSyncSettings = {
  enabled: boolean;
  interval_minutes: number;
  backlog_sweep_interval_minutes: number;
  lookback_days: number;
  sector_ids: string[];
  sector_scope_label: string;
  available_sectors: OperationIxcSector[];
};

export type OperationFilterState = {
  date_from: string;
  date_to: string;
  team_models?: string[];
  companies?: string[];
  regionals?: string[];
  states?: string[];
  cities?: string[];
  contract_types?: string[];
  person_types?: string[];
  os_types?: string[];
  subjects?: string[];
  diagnoses?: string[];
  departments?: string[];
  sectors?: string[];
  priorities?: string[];
  creators?: string[];
  responsibles?: string[];
  statuses?: string[];
  sla_statuses?: string[];
  projects?: string[];
  pops?: string[];
  opened_weekdays?: string[];
  closed_weekdays?: string[];
  custom_window_basis?: string[];
  custom_window_start_weekday?: string;
  custom_window_start_time?: string;
  custom_window_end_weekday?: string;
  custom_window_end_time?: string;
  closed_time_from?: string;
  closed_time_to?: string;
  responsible_mode?: "all" | "completed";
  search?: string;
};

export type OperationSavedFilterValues = Omit<
  OperationFilterState,
  "date_from" | "date_to"
>;

export type OperationSavedFilter = {
  id: number;
  name: string;
  filters: OperationSavedFilterValues;
  visibility: "personal" | "global";
  user_id: number;
  created_at: string;
  updated_at: string;
};

export type OperationTeamModel = OperationCalendarTeamModel & {
  active: boolean;
  created_at: string;
  updated_at: string;
};

export type OperationResponsibleProfile = {
  responsible_name: string;
  regional: string;
  regionals: string[];
  team_model_id: number | null;
};

export type OperationTeamConfiguration = {
  models: OperationTeamModel[];
  members: OperationResponsibleProfile[];
  responsible_source: "orders" | "ixc" | "both";
  ixc_collaborators_synced_at: string | null;
};

export type OperationSubjectTypeMapping = {
  id: number | null;
  subject: string;
  os_type: string;
  order_count: number;
  active: boolean;
};

export type OperationTeamModelPayload = Omit<
  OperationTeamModel,
  "id" | "created_at" | "updated_at"
>;

export type OperationConfigurationJson = {
  schema_version: 1;
  team_models: OperationTeamModelPayload[];
  team_members: Array<{
    responsible_name: string;
    regional?: string | null;
    team_model_name?: string | null;
  }>;
  subject_mappings: Array<{
    subject: string;
    os_type: string;
    active: boolean;
  }>;
  saved_filters: Array<{
    name: string;
    filters: OperationSavedFilterValues;
    visibility: "personal" | "global";
  }>;
};

export type OperationConfigurationImportResult = {
  team_models: number;
  team_members: number;
  subject_mappings: number;
  saved_filters: number;
};

export type OperationOfflineLogin = {
  login_id: number;
  login: string;
  online: string;
  latitude: number;
  longitude: number;
  last_disconnected_at: string | null;
};

export type OperationOfflineLoginCluster = {
  center_latitude: number;
  center_longitude: number;
  radius_meters: number;
  size: number;
  logins: OperationOfflineLogin[];
};

export type OperationOfflineLoginClusters = {
  radius_meters: number;
  min_cluster_size: number;
  window_minutes: number;
  clusters: OperationOfflineLoginCluster[];
};

const API_URL = process.env.NEXT_PUBLIC_API_URL || "/api";
const TOKEN_KEY = "gamification_auth_token";

function authToken() {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(TOKEN_KEY);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");
  const token = authToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  if (!response.ok) {
    const text = await response.text();
    let message = text || `Erro HTTP ${response.status}`;
    try {
      const body = JSON.parse(text) as {
        detail?: string | Array<{ loc?: Array<string | number>; msg?: string }>;
      };
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) {
        message = body.detail
          .map((item) => item.msg || "Parâmetro inválido.")
          .join(" ");
      }
    } catch {
      // Resposta não JSON: mantém o texto amigável/fallback já definido.
    }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function query(
  filters: OperationFilterState,
  extras?: Record<string, string | number | string[] | number[] | undefined>,
  omitDates = false,
) {
  const params = new URLSearchParams();
  Object.entries({ ...filters, ...extras }).forEach(([key, value]) => {
    if (omitDates && (key === "date_from" || key === "date_to")) return;
    if (Array.isArray(value)) {
      value.forEach((item) => params.append(key, item));
    } else if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  });
  return params.toString();
}

export const operationsApi = {
  period: () => request<OperationPeriod>("/operations/period"),
  ixcSyncSettings: () =>
    request<OperationIxcSyncSettings>("/operations/ixc-sync-settings"),
  updateIxcSyncSettings: (payload: Partial<Omit<OperationIxcSyncSettings, "available_sectors" | "sector_scope_label">>) =>
    request<OperationIxcSyncSettings>("/operations/ixc-sync-settings", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  importPeriod: (dateFrom: string, dateTo: string, sectorIds: string[] = []) =>
    request<OperationImportResult>("/operations/imports", {
      method: "POST",
      body: JSON.stringify({ date_from: dateFrom, date_to: dateTo, sector_ids: sectorIds }),
    }),
  startBackfillImport: (dateFrom: string, dateTo: string, sectorIds: string[] = []) =>
    request<OperationBackfillJob>("/operations/imports/backfill", {
      method: "POST",
      body: JSON.stringify({ date_from: dateFrom, date_to: dateTo, sector_ids: sectorIds }),
    }),
  backfillImportStatus: (jobId: number) =>
    request<OperationBackfillJob>(`/operations/imports/backfill/${jobId}`),
  startOpenBacklogImport: (sectorIds: string[] = []) => {
    const params = new URLSearchParams();
    sectorIds.forEach((sectorId) => params.append("sector_ids", sectorId));
    const queryString = params.toString();
    return request<OperationOpenBacklogJob>(`/operations/imports/open-backlog${queryString ? `?${queryString}` : ""}`, {
      method: "POST",
    });
  },
  openBacklogImportStatus: (jobId: number) =>
    request<OperationOpenBacklogJob>(`/operations/imports/open-backlog/${jobId}`),
  filters: (
    filters: OperationFilterState,
    scope: "period" | "in_progress" = "period",
  ) =>
    request<OperationFilters>(
      `/operations/filters?${query(filters, { scope }, scope === "in_progress")}`,
    ),
  overview: (filters: OperationFilterState) =>
    request<OperationOverview>(`/operations/overview?${query(filters)}`),
  overviewWorkSchedule: (
    filters: OperationFilterState,
    modelIds: number[] = [],
  ) =>
    request<OperationWorkScheduleOverview>(
      `/operations/overview/work-schedule?${query(filters, { model_ids: modelIds })}`,
    ),
  overviewTrends: (
    filters: OperationFilterState,
    granularity: OperationTrendGranularity,
  ) =>
    request<OperationTrendSeries>(
      `/operations/overview/trends?${query(filters, { granularity })}`,
    ),
  overviewVolumeAlerts: (filters: OperationFilterState) =>
    request<OperationSubjectVolumeAlerts>(
      `/operations/overview/volume-alerts?${query(filters)}`,
    ),
  controlTower: (
    filters: OperationFilterState,
    level: OperationControlTowerLevel = "subject",
    path: OperationControlTowerPath = {},
  ) =>
    request<OperationControlTower>(
      `/operations/overview/control-tower?${query(filters, {
        level,
        parent_subject: path.subject,
        parent_regional: path.regional,
        parent_city: path.city,
        parent_sector: path.sector,
      })}`,
    ),
  openingsAnalytics: (
    filters: OperationFilterState,
    granularity: OperationTrendGranularity = "day",
  ) =>
    request<OperationOpeningsAnalytics>(
      `/operations/openings/analytics?${query(filters, { granularity })}`,
    ),
  dataFreshness: () =>
    request<OperationDataFreshness>("/operations/data-freshness"),
  sla: (filters: OperationFilterState, groupBy: string) =>
    request<OperationSlaItem[]>(
      `/operations/sla?${query(filters, { group_by: groupBy })}`,
    ),
  slaHierarchy: (
    filters: OperationFilterState,
    level: OperationSlaHierarchyLevel,
    parentOsType?: string,
    parentSubject?: string,
  ) =>
    request<OperationSlaHierarchy>(
      `/operations/sla/hierarchy?${query(filters, {
        level,
        parent_os_type: parentOsType,
        parent_subject: parentSubject,
      })}`,
    ),
  collaboratorSla: (filters: OperationFilterState) =>
    request<OperationCollaboratorSla>(
      `/operations/sla/collaborators?${query(filters)}`,
    ),
  warranty: (
    filters: OperationFilterState,
    periodBasis: OperationWarrantyPeriodBasis,
    denominator: OperationWarrantyDenominator,
    originExcludedDiagnoses: string[] = [],
  ) =>
    request<OperationWarrantyAnalytics>(
      `/operations/warranty?${query(filters, {
        period_basis: periodBasis,
        denominator,
        origin_excluded_diagnoses: originExcludedDiagnoses,
      })}`,
    ),
  calendar: (
    filters: OperationFilterState,
    groupBy: "regional" | "collaborator" = "regional",
  ) =>
    request<OperationCalendar>(
      `/operations/calendar?${query(filters, { group_by: groupBy })}`,
    ),
  calendarOrders: (
    filters: OperationFilterState,
    day: string,
    regional: string,
    responsible: string,
    groupBy: "regional" | "collaborator" = "regional",
    page = 1,
    pageSize = 50,
  ) =>
    request<OperationOrderPage>(
      `/operations/calendar/orders?${query(filters, {
        day,
        regional,
        responsible,
        group_by: groupBy,
        page,
        page_size: pageSize,
      })}`,
    ),
  calendarDayDetail: (
    filters: OperationFilterState,
    day: string,
    regional: string,
    responsible: string,
    groupBy: "regional" | "collaborator" = "regional",
    referenceRegional: string | null = null,
    page = 1,
    pageSize = 50,
  ) =>
    request<OperationCalendarDayDetail>(
      `/operations/calendar/day-detail?${query(filters, {
        day,
        regional,
        responsible,
        group_by: groupBy,
        reference_regional: referenceRegional || undefined,
        page,
        page_size: pageSize,
      })}`,
    ),
  calendarWeekDetail: (
    filters: OperationFilterState,
    dateFrom: string,
    dateTo: string,
    regional: string,
    responsible: string,
    groupBy: "regional" | "collaborator" = "regional",
    referenceRegional: string | null = null,
    page = 1,
    pageSize = 50,
  ) =>
    request<OperationCalendarDayDetail>(
      `/operations/calendar/week-detail?${query(filters, {
        date_from: dateFrom,
        date_to: dateTo,
        regional,
        responsible,
        group_by: groupBy,
        reference_regional: referenceRegional || undefined,
        page,
        page_size: pageSize,
      })}`,
    ),
  calendarMonthDetail: (
    filters: OperationFilterState,
    regional: string,
    responsible: string,
    groupBy: "regional" | "collaborator" = "regional",
    referenceRegional: string | null = null,
    page = 1,
    pageSize = 50,
  ) =>
    request<OperationCalendarMonthlyDetail>(
      `/operations/calendar/month-detail?${query(filters, {
        regional,
        responsible,
        group_by: groupBy,
        reference_regional: referenceRegional || undefined,
        page,
        page_size: pageSize,
      })}`,
    ),
  inProgress: (filters: OperationFilterState, groupBy: string) =>
    request<OperationBreakdownItem[]>(
      `/operations/in-progress?${query(filters, { group_by: groupBy }, true)}`,
    ),
  inProgressSlaRisk: (filters: OperationFilterState) =>
    request<OperationSlaRiskItem[]>(
      `/operations/in-progress/sla-risk?${query(filters, {}, true)}`,
    ),
  inProgressOrders: (
    filters: OperationFilterState,
    page = 1,
    pageSize = 50,
    sort?: { key: string; direction: "asc" | "desc" },
    slaRisk?: string,
  ) =>
    request<OperationOrderPage>(
      `/operations/in-progress/orders?${query(filters, { page, page_size: pageSize, sort_by: sort?.key, sort_dir: sort?.direction, sla_risk: slaRisk }, true)}`,
    ),
  orders: (
    filters: OperationFilterState,
    page = 1,
    pageSize = 50,
    sort?: { key: string; direction: "asc" | "desc" },
  ) =>
    request<OperationOrderPage>(
      `/operations/orders?${query(filters, { page, page_size: pageSize, sort_by: sort?.key, sort_dir: sort?.direction })}`,
    ),
  openingOrders: (
    filters: OperationFilterState,
    page = 1,
    pageSize = 50,
    sort?: { key: string; direction: "asc" | "desc" },
    extra?: { aging_bucket?: string; weekday?: number; hour?: number },
  ) =>
    request<OperationOrderPage>(
      `/operations/openings/orders?${query(filters, { page, page_size: pageSize, sort_by: sort?.key, sort_dir: sort?.direction, ...extra })}`,
    ),
  savedFilters: () =>
    request<OperationSavedFilter[]>("/operations/saved-filters"),
  createSavedFilter: (name: string, filters: OperationSavedFilterValues, visibility: "personal" | "global" = "personal") =>
    request<OperationSavedFilter>("/operations/saved-filters", {
      method: "POST",
      body: JSON.stringify({ name, filters, visibility }),
    }),
  updateSavedFilter: (
    id: number,
    payload: { name?: string; filters?: OperationSavedFilterValues; visibility?: "personal" | "global" },
  ) =>
    request<OperationSavedFilter>(`/operations/saved-filters/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteSavedFilter: (id: number) =>
    request<void>(`/operations/saved-filters/${id}`, { method: "DELETE" }),
  teamConfiguration: () =>
    request<OperationTeamConfiguration>("/operations/team-configuration"),
  updateResponsibleDirectory: (source: "orders" | "ixc" | "both") =>
    request<OperationTeamConfiguration>("/operations/responsible-directory", {
      method: "PUT",
      body: JSON.stringify({ source }),
    }),
  syncResponsibleDirectory: () =>
    request<{ imported: number; active: number; synced_at: string }>("/operations/responsible-directory/sync", {
      method: "POST",
    }),
  exportConfiguration: () =>
    request<OperationConfigurationJson>("/operations/configuration-json"),
  importConfiguration: (payload: OperationConfigurationJson) =>
    request<OperationConfigurationImportResult>("/operations/configuration-json", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  createTeamModel: (payload: OperationTeamModelPayload) =>
    request<OperationTeamModel>("/operations/team-models", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateTeamModel: (id: number, payload: Partial<OperationTeamModelPayload>) =>
    request<OperationTeamModel>(`/operations/team-models/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteTeamModel: (id: number) =>
    request<void>(`/operations/team-models/${id}`, { method: "DELETE" }),
  assignTeamMember: (payload: OperationResponsibleProfile) =>
    request<void>("/operations/team-members", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  subjectTypeMappings: () =>
    request<OperationSubjectTypeMapping[]>("/operations/subject-type-mappings"),
  updateSubjectTypeMappings: (subjects: string[], osType: string) =>
    request<OperationSubjectTypeMapping[]>(
      "/operations/subject-type-mappings",
      {
        method: "PUT",
        body: JSON.stringify({ subjects, os_type: osType }),
      },
    ),
  networkOfflineLoginClusters: (params: {
    radiusMeters: number;
    minClusterSize: number;
    windowMinutes: number;
  }) => {
    const search = new URLSearchParams({
      radius_meters: String(params.radiusMeters),
      min_cluster_size: String(params.minClusterSize),
      window_minutes: String(params.windowMinutes),
    });
    return request<OperationOfflineLoginClusters>(
      `/operations/network/offline-login-clusters?${search.toString()}`,
    );
  },
};
