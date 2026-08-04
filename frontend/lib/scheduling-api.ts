export type SchedulingCountMode = "all_events" | "distinct_orders";

export type SchedulingStats = {
  median: number | null;
  p90: number | null;
  average: number | null;
};

export type SchedulingSummary = {
  opened_orders: number;
  scheduled_orders: number;
  pending_orders: number;
  sla_minutes: number;
  sla_target_pct: number;
  sla_rate: number | null;
  sla_met: boolean | null;
  ttfa_business: SchedulingStats;
  ttfa_raw: SchedulingStats;
  reschedule_rate: number | null;
  rescheduled_orders: number;
  reschedule_backoffice_count: number;
  reschedule_backoffice_pct: number | null;
  reschedule_campo_count: number;
  reschedule_campo_pct: number | null;
  window_lead_hours: SchedulingStats;
  total_schedule_events: number;
  active_period_days: number;
  team_size: number | null;
  expected_capacity: number | null;
};

export type SchedulingBucket = { bucket: string; label: string; count: number };
export type SchedulingDailyPoint = { date: string; opened: number; schedule_events: number };

export type SchedulingOperatorRow = {
  ixc_operator_id: number;
  operator_name: string;
  is_team_member: boolean;
  total_events: number;
  distinct_orders: number;
  per_day: number;
  daily_goal: number | null;
  goal_percentage: number | null;
  first_schedules: number;
  ttfa_business_median_minutes: number | null;
};

export type SchedulingRankingItem = {
  key: string;
  label: string;
  scheduled: number;
  late_rate: number;
  ttfa_median_minutes: number | null;
};

export type SchedulingDashboard = {
  settings: Record<string, string>;
  summary: SchedulingSummary;
  ttfa_distribution: SchedulingBucket[];
  backlog_aging: SchedulingBucket[];
  daily_series: SchedulingDailyPoint[];
  operators: SchedulingOperatorRow[];
  filial_ranking: SchedulingRankingItem[];
  assunto_ranking: SchedulingRankingItem[];
};

export type SchedulingBacklogItem = {
  ixc_os_id: number;
  opened_at: string;
  age_hours: number;
  filial: string;
  setor: string;
  assunto: string;
  status: string | null;
};

export type SchedulingFilterOption = { id: string | number; name: string; is_team_member?: boolean | null };

export type SchedulingFilterOptions = {
  filiais: SchedulingFilterOption[];
  setores: SchedulingFilterOption[];
  assuntos: SchedulingFilterOption[];
  operators: SchedulingFilterOption[];
  data_available_from: string | null;
  data_available_to: string | null;
};

export type SchedulingTeamMember = { ixc_user_id: number; name: string; is_team_member: boolean };

export type SchedulingOrderDetailItem = {
  ixc_os_id: number;
  opened_at: string;
  filial: string;
  setor: string;
  assunto: string;
  status: string | null;
  first_scheduled_at: string | null;
  ttfa_business_minutes: number | null;
  sla_late: boolean | null;
  reschedule_count: number;
  reschedule_origins: ("backoffice" | "campo")[];
  operator_name: string | null;
  technician_name: string | null;
  age_hours: number | null;
};

export type SchedulingOrderDetailPage = {
  items: SchedulingOrderDetailItem[];
  total: number;
  page: number;
  page_size: number;
};

export type SchedulingTimelineEvent = {
  event_type: string;
  event_label: string;
  event_at: string;
  window_start: string | null;
  window_end: string | null;
  operator_name: string | null;
  technician_name: string | null;
  mensagem: string | null;
  historico: string | null;
};

export type SchedulingOrderTimeline = {
  ixc_os_id: number;
  opened_at: string;
  filial: string;
  setor: string;
  assunto: string;
  status: string | null;
  events: SchedulingTimelineEvent[];
};

export type SchedulingOperatorEventItem = {
  ixc_os_id: number;
  event_type: string;
  event_label: string;
  event_at: string;
  window_start: string | null;
  window_end: string | null;
  technician_name: string | null;
  filial: string;
  assunto: string;
};

export type SchedulingOperatorEventPage = {
  items: SchedulingOperatorEventItem[];
  total: number;
  page: number;
  page_size: number;
};

export type SchedulingOrderDrillParams = {
  status?: "pending" | "scheduled";
  sla_status?: "late" | "on_time";
  ttfa_bucket?: string;
  backlog_bucket?: string;
  only_rescheduled?: boolean;
  reschedule_origin?: "backoffice" | "campo";
  operator_ids?: number[];
  filial_ids?: string[];
  assunto_ids?: string[];
};

export type SchedulingSyncJob = {
  id: number;
  job_type: string;
  status: "pending" | "running" | "completed" | "failed";
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
};

export type SchedulingSyncStatus = {
  watermark: string | null;
  last_job: SchedulingSyncJob | null;
  orders_count: number;
  events_count: number;
};

export type SchedulingFilterState = {
  date_from: string;
  date_to: string;
  filial_ids: string[];
  setor_ids: string[];
  assunto_ids: string[];
  operator_ids: number[];
  count_mode: SchedulingCountMode;
};

export type SchedulingSavedFilterValues = {
  filial_ids: string[];
  setor_ids: string[];
  assunto_ids: string[];
  operator_ids: number[];
  count_mode: SchedulingCountMode;
};

export type SchedulingSavedFilter = {
  id: number;
  name: string;
  filters: SchedulingSavedFilterValues;
  visibility: "personal" | "global";
  user_id: number;
  created_at: string;
  updated_at: string;
};

export type SchedulingOrderSortKey =
  | "opened_at"
  | "first_scheduled_at"
  | "ttfa_business_minutes"
  | "reschedule_count"
  | "filial"
  | "assunto";

export type SchedulingOrderSort = { key: SchedulingOrderSortKey; direction: "asc" | "desc" };

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
  const response = await fetch(`${API_URL}${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) {
    const text = await response.text();
    let message = text || `Erro HTTP ${response.status}`;
    try {
      const body = JSON.parse(text) as { detail?: string };
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      // Resposta não JSON: mantém o texto amigável/fallback já definido.
    }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function filterQuery(filters: SchedulingFilterState, extras?: Record<string, string | number>) {
  const params = new URLSearchParams();
  params.set("date_from", filters.date_from);
  params.set("date_to", filters.date_to);
  filters.filial_ids.forEach((id) => params.append("filial_ids", id));
  filters.setor_ids.forEach((id) => params.append("setor_ids", id));
  filters.assunto_ids.forEach((id) => params.append("assunto_ids", id));
  filters.operator_ids.forEach((id) => params.append("operator_ids", String(id)));
  Object.entries(extras || {}).forEach(([key, value]) => params.set(key, String(value)));
  return params.toString();
}

export const schedulingApi = {
  dashboard: (filters: SchedulingFilterState, signal?: AbortSignal) =>
    request<SchedulingDashboard>(
      `/scheduling/dashboard?${filterQuery(filters, { count_mode: filters.count_mode })}`,
      { signal },
    ),
  backlog: (filters: SchedulingFilterState, limit = 100, signal?: AbortSignal) =>
    request<SchedulingBacklogItem[]>(`/scheduling/backlog?${filterQuery(filters, { limit })}`, { signal }),
  orders: (
    filters: SchedulingFilterState,
    drill: SchedulingOrderDrillParams,
    page = 1,
    pageSize = 50,
    sort?: SchedulingOrderSort,
    signal?: AbortSignal,
  ) => {
    const params = new URLSearchParams();
    params.set("date_from", filters.date_from);
    params.set("date_to", filters.date_to);
    (drill.filial_ids ?? filters.filial_ids).forEach((id) => params.append("filial_ids", id));
    filters.setor_ids.forEach((id) => params.append("setor_ids", id));
    (drill.assunto_ids ?? filters.assunto_ids).forEach((id) => params.append("assunto_ids", id));
    (drill.operator_ids ?? filters.operator_ids).forEach((id) => params.append("operator_ids", String(id)));
    if (drill.status) params.set("status", drill.status);
    if (drill.sla_status) params.set("sla_status", drill.sla_status);
    if (drill.ttfa_bucket) params.set("ttfa_bucket", drill.ttfa_bucket);
    if (drill.backlog_bucket) params.set("backlog_bucket", drill.backlog_bucket);
    if (drill.only_rescheduled) params.set("only_rescheduled", "true");
    if (drill.reschedule_origin) params.set("reschedule_origin", drill.reschedule_origin);
    params.set("page", String(page));
    params.set("page_size", String(pageSize));
    if (sort) {
      params.set("sort_by", sort.key);
      params.set("sort_dir", sort.direction);
    }
    return request<SchedulingOrderDetailPage>(`/scheduling/orders?${params.toString()}`, { signal });
  },
  orderTimeline: (ixcOsId: number, signal?: AbortSignal) =>
    request<SchedulingOrderTimeline>(`/scheduling/orders/${ixcOsId}/timeline`, { signal }),
  operatorEvents: (
    operatorId: number,
    filters: SchedulingFilterState,
    page = 1,
    pageSize = 50,
    signal?: AbortSignal,
  ) => {
    const params = new URLSearchParams();
    params.set("date_from", filters.date_from);
    params.set("date_to", filters.date_to);
    filters.filial_ids.forEach((id) => params.append("filial_ids", id));
    filters.setor_ids.forEach((id) => params.append("setor_ids", id));
    filters.assunto_ids.forEach((id) => params.append("assunto_ids", id));
    params.set("page", String(page));
    params.set("page_size", String(pageSize));
    return request<SchedulingOperatorEventPage>(`/scheduling/operators/${operatorId}/events?${params.toString()}`, { signal });
  },
  resolveTechnicians: () => request<{ resolved: number; pending: number }>("/scheduling/technicians/resolve", { method: "POST" }),
  filters: () => request<SchedulingFilterOptions>("/scheduling/filters"),
  settings: () => request<Record<string, string>>("/scheduling/settings"),
  updateSettings: (values: Record<string, string>) =>
    request<Record<string, string>>("/scheduling/settings", { method: "PUT", body: JSON.stringify(values) }),
  team: () => request<SchedulingTeamMember[]>("/scheduling/team"),
  updateTeam: (teamMemberIds: number[]) =>
    request<SchedulingTeamMember[]>("/scheduling/team", {
      method: "PUT",
      body: JSON.stringify({ team_member_ids: teamMemberIds }),
    }),
  startSync: (dateFrom?: string, dateTo?: string) =>
    request<SchedulingSyncJob>("/scheduling/sync", {
      method: "POST",
      body: JSON.stringify({ date_from: dateFrom ?? null, date_to: dateTo ?? null }),
    }),
  syncStatus: () => request<SchedulingSyncStatus>("/scheduling/sync/status"),
  startMessagesBackfill: () => request<SchedulingSyncJob>("/scheduling/messages/backfill", { method: "POST" }),
  messagesBackfillStatus: () => request<SchedulingSyncJob | null>("/scheduling/messages/backfill/status"),
  savedFilters: () => request<SchedulingSavedFilter[]>("/scheduling/saved-filters"),
  createSavedFilter: (name: string, filters: SchedulingSavedFilterValues, visibility: "personal" | "global" = "personal") =>
    request<SchedulingSavedFilter>("/scheduling/saved-filters", {
      method: "POST",
      body: JSON.stringify({ name, filters, visibility }),
    }),
  updateSavedFilter: (
    id: number,
    payload: { name?: string; filters?: SchedulingSavedFilterValues; visibility?: "personal" | "global" },
  ) =>
    request<SchedulingSavedFilter>(`/scheduling/saved-filters/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteSavedFilter: (id: number) =>
    request<void>(`/scheduling/saved-filters/${id}`, { method: "DELETE" }),
};
