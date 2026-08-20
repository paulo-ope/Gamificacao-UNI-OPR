// Cliente do Cockpit UNI Intelligence (F2) - mesmo padrão de ai-governance-api.ts/scheduling-api.ts
// (cada domínio com seu próprio request<T> pequeno em vez de inchar lib/api.ts).

export type CockpitProfile = {
  key: string;
  name: string;
  purpose: string;
  widgets: string[];
  refresh_seconds: number;
  display_config: Record<string, unknown>;
};

export type CockpitOverallStatus = {
  status: "NORMAL" | "ATTENTION" | "RISK" | "CRITICAL";
  reason: string;
};

export type CockpitProduction = {
  opened_today: number;
  closed_today: number;
  balance_today: number;
  avg_opened_7d: number;
  avg_closed_7d: number;
};

export type CockpitBacklog = {
  total: number;
  gt_3d: number;
  gt_7d: number;
  gt_15d: number;
};

export type CockpitCriticalRegional = { regional: string; sla_rate: number };

export type CockpitSla = {
  current: number | null;
  target: number;
  critical_regionals: CockpitCriticalRegional[];
};

export type CockpitAlertSummary = {
  id: number;
  kind: "ALERT" | "INCIDENT";
  alert_type: string;
  severity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  status: string;
  title: string;
  summary: string;
  recommended_action: string | null;
  regional: string | null;
  city: string | null;
  confidence: number | null;
  coverage: Record<string, unknown>;
  warnings: Array<Record<string, unknown>>;
  evidence: Record<string, unknown>;
  first_detected_at: string;
  last_seen_at: string;
  age_seconds: number;
  source_type: string;
  monitor_key: string;
  source_key: string | null;
  resolved_at: string | null;
  resolution_reason: string | null;
};

export type CockpitContent = {
  id: number;
  content_type: string;
  profile_key: string | null;
  regional: string | null;
  severity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | "INFO";
  title: string;
  body: string;
  evidence: Record<string, unknown>;
  confidence: number | null;
  source_type: "SYSTEM" | "MONITOR" | "AI" | "USER" | "MCP";
  source_key: string | null;
  author_user_id: number | null;
  valid_from: string;
  valid_until: string | null;
  created_at: string;
};

export type CockpitMonitorHealth = {
  monitor_key: string;
  name: string;
  enabled: boolean;
  last_run_at: string | null;
  last_run_status: string | null;
  last_success_at: string | null;
  consecutive_failures: number;
};

export type CockpitDataFreshness = {
  last_successful_import_at: string | null;
  status: string | null;
  date_from: string | null;
  date_to: string | null;
};

export type CockpitProductionPoint = { date: string; opened: number; closed: number };
export type CockpitSlaPoint = { date: string; sla_rate: number | null };
export type CockpitBacklogPoint = { date: string; quantity: number };

export type CockpitCharts = {
  production_7d: CockpitProductionPoint[];
  sla_7d: CockpitSlaPoint[];
  backlog_7d: CockpitBacklogPoint[];
};

export type CockpitPayload = {
  profile: CockpitProfile;
  generated_at: string;
  overall_status: CockpitOverallStatus;
  display_mode: "NORMAL" | "ATTENTION" | "INCIDENT";
  production: CockpitProduction;
  backlog: CockpitBacklog;
  sla: CockpitSla;
  alerts: CockpitAlertSummary[];
  incidents: CockpitAlertSummary[];
  recent_alerts: CockpitAlertSummary[];
  content: CockpitContent[];
  monitor_health: CockpitMonitorHealth[];
  charts: CockpitCharts;
  data_freshness: CockpitDataFreshness;
  meta: { applied_filters: Record<string, unknown>; ignored_filters: unknown[]; warnings: Array<Record<string, unknown>>; generated_at: string; source_last_sync: string | null };
};

// --- Administração (F5) ----------------------------------------------------------------------

export type WidgetEntry = { key: string; filters: Record<string, unknown> };

export type AdminProfile = {
  id: number;
  key: string;
  name: string;
  purpose: string;
  scope: Record<string, unknown>;
  widgets: WidgetEntry[];
  display_config: Record<string, unknown>;
  refresh_seconds: number;
  active: boolean;
  created_at: string;
  updated_at: string;
};

export type AdminProfileInput = {
  key?: string;
  name?: string;
  purpose?: string;
  scope?: Record<string, unknown>;
  widgets?: WidgetEntry[];
  display_config?: Record<string, unknown>;
  refresh_seconds?: number;
  active?: boolean;
};

export type WidgetCatalogEntry = { key: string; allowed_filters: string[] };

export type FilterCatalog = {
  regionals: string[];
  sectors: string[];
  team_models: string[];
  os_subjects: string[];
  content_types: string[];
  content_severities: string[];
  profile_purposes: string[];
  widgets: WidgetCatalogEntry[];
};

export type AdminContent = CockpitContent & { status: string };

export type AdminContentUpdateInput = {
  title?: string;
  body?: string;
  severity?: string;
  valid_until?: string | null;
};

export type MonitorInfo = {
  key: string;
  name: string;
  description: string;
  scope_strategy: string;
  enabled: boolean;
  interval_minutes: number;
  resolve_after_misses: number;
  last_run_at: string | null;
  last_run_status: string | null;
  last_success_at: string | null;
  consecutive_failures: number;
};

export type MonitorUpdateInput = {
  enabled?: boolean;
  interval_minutes?: number;
  resolve_after_misses?: number;
};

export type IntelligenceAlert = {
  id: number;
  kind: "ALERT" | "INCIDENT";
  alert_type: string;
  monitor_key: string;
  dedupe_key: string;
  regional: string | null;
  city: string | null;
  scope: Record<string, unknown>;
  severity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  title: string;
  summary: string;
  recommended_action: string | null;
  evidence: Record<string, unknown>;
  confidence: number | null;
  coverage: Record<string, unknown>;
  warnings: Array<Record<string, unknown>>;
  source_last_sync: string | null;
  status: string;
  first_detected_at: string;
  last_seen_at: string;
  resolved_at: string | null;
  acknowledged_by: number | null;
  acknowledged_at: string | null;
  misses_count: number;
  source_type: string;
  source_key: string | null;
  created_at: string;
  updated_at: string;
};

export type IntelligenceAlertEvent = {
  id: number;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
  created_by: number | null;
};

export type IntelligenceAlertDetail = IntelligenceAlert & { events: IntelligenceAlertEvent[] };

export type AlertPage = { items: IntelligenceAlert[]; total: number; page: number; page_size: number };

export type AlertRule = {
  id: number;
  key: string;
  name: string;
  rule_type: string;
  active: boolean;
  scope: Record<string, unknown>;
  params: Record<string, unknown>;
  severity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  cooldown_minutes: number;
  confirm_cycles: number;
  resolve_cycles: number;
  created_at: string;
  updated_at: string;
};

export type AlertRuleInput = {
  key?: string;
  name?: string;
  rule_type?: string;
  scope?: Record<string, unknown>;
  params?: Record<string, unknown>;
  severity?: string;
  active?: boolean;
  cooldown_minutes?: number;
  confirm_cycles?: number;
  resolve_cycles?: number;
};

export type AlertRuleTypeCatalogEntry = {
  key: string;
  allowed_scope: string[];
  allowed_params: string[];
  default_params: Record<string, unknown>;
};

export type AlertRuleCatalog = {
  rule_types: AlertRuleTypeCatalogEntry[];
  severities: string[];
  group_by_values: string[];
};

export type AlertRuleSimulation = { rule_key: string; detection_count: number; detections: Array<{ title: string; summary: string; severity: string; regional: string | null; city: string | null; evidence: Record<string, unknown>; confidence: number | null }> };

export type PublishCockpitContentInput = {
  content_type: string;
  profile_key?: string | null;
  scope?: Record<string, unknown>;
  severity?: string;
  title: string;
  body: string;
  evidence?: Record<string, unknown>;
  confidence?: number | null;
  valid_until?: string | null;
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
    cache: "no-store"
  });
  if (!response.ok) {
    const text = await response.text();
    let message = text || `Erro HTTP ${response.status}`;
    try {
      const body = JSON.parse(text) as { detail?: string | Array<{ loc?: Array<string | number>; msg?: string }> };
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((item) => item.msg || "Parâmetro inválido.").join(" ");
    } catch {
      // resposta não-JSON: mantém o texto/fallback já definido
    }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

// Cache raso em memória (TTL curto) para catálogos que várias abas da Administração pedem de
// forma independente (Cockpit/Publicações/Profiles chamam listProfiles(); Profiles chama
// getFilterCatalog()) - achado real de performance: sem isso, trocar de aba refaz a mesma consulta
// mais de uma vez em poucos segundos. Nunca usado para dado operacional (alertas, conteúdo,
// monitores) - só catálogo que muda pouco.
const _shortCache = new Map<string, { value: unknown; expiresAt: number }>();
const CACHE_TTL_MS = 30_000;

async function cached<T>(key: string, loader: () => Promise<T>): Promise<T> {
  const hit = _shortCache.get(key);
  if (hit && hit.expiresAt > Date.now()) return hit.value as T;
  const value = await loader();
  _shortCache.set(key, { value, expiresAt: Date.now() + CACHE_TTL_MS });
  return value;
}

function invalidateCache(key: string) {
  _shortCache.delete(key);
}

export const intelligenceCockpitApi = {
  getCockpit: (profileKey: string) => request<CockpitPayload>(`/intelligence/cockpit/${encodeURIComponent(profileKey)}`),

  publishContent: (payload: PublishCockpitContentInput) =>
    request<CockpitContent>("/intelligence/cockpit-content", {
      method: "POST",
      body: JSON.stringify(payload)
    }),

  // --- alertas/incidentes ----------------------------------------------------------------------
  listAlerts: (params: { statuses?: string[]; severities?: string[]; kinds?: string[]; regionals?: string[]; page?: number; page_size?: number } = {}) => {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined) continue;
      if (Array.isArray(value)) value.forEach((v) => search.append(key, String(v)));
      else search.set(key, String(value));
    }
    const query = search.toString();
    return request<AlertPage>(`/intelligence/alerts${query ? `?${query}` : ""}`);
  },
  getAlert: (alertId: number) => request<IntelligenceAlertDetail>(`/intelligence/alerts/${alertId}`),
  dismissAlert: (alertId: number, reason?: string) =>
    request<IntelligenceAlertDetail>(`/intelligence/alerts/${alertId}/dismiss`, { method: "POST", body: JSON.stringify({ reason: reason ?? null }) }),

  // --- monitores --------------------------------------------------------------------------------
  listMonitors: () => request<{ items: MonitorInfo[] }>("/intelligence/monitors"),
  updateMonitor: (monitorKey: string, payload: MonitorUpdateInput) =>
    request<MonitorInfo>(`/intelligence/admin/monitors/${encodeURIComponent(monitorKey)}`, { method: "PUT", body: JSON.stringify(payload) }),

  // --- profiles -----------------------------------------------------------------------------------
  listProfiles: () => cached("profiles", () => request<AdminProfile[]>("/intelligence/admin/profiles")),
  getProfile: (profileKey: string) => request<AdminProfile>(`/intelligence/admin/profiles/${encodeURIComponent(profileKey)}`),
  createProfile: (payload: AdminProfileInput) =>
    request<AdminProfile>("/intelligence/admin/profiles", { method: "POST", body: JSON.stringify(payload) }).then((result) => {
      invalidateCache("profiles");
      return result;
    }),
  updateProfile: (profileKey: string, payload: AdminProfileInput) =>
    request<AdminProfile>(`/intelligence/admin/profiles/${encodeURIComponent(profileKey)}`, { method: "PUT", body: JSON.stringify(payload) }).then(
      (result) => {
        invalidateCache("profiles");
        return result;
      },
    ),
  getFilterCatalog: () => cached("filter-catalog", () => request<FilterCatalog>("/intelligence/admin/filter-catalog")),

  // --- publicações --------------------------------------------------------------------------------
  listAdminContent: (params: { profile_key?: string; status?: string; content_type?: string } = {}) => {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value) search.set(key, value);
    }
    const query = search.toString();
    return request<AdminContent[]>(`/intelligence/admin/content${query ? `?${query}` : ""}`);
  },
  updateAdminContent: (contentId: number, payload: AdminContentUpdateInput) =>
    request<AdminContent>(`/intelligence/admin/content/${contentId}`, { method: "PUT", body: JSON.stringify(payload) }),
  dismissAdminContent: (contentId: number) =>
    request<AdminContent>(`/intelligence/admin/content/${contentId}/dismiss`, { method: "POST" }),

  // --- regras de alertas ---------------------------------------------------------------------
  listAlertRules: () => request<AlertRule[]>("/intelligence/admin/alert-rules"),
  getAlertRuleCatalog: () => cached("alert-rule-catalog", () => request<AlertRuleCatalog>("/intelligence/admin/alert-rules/catalog")),
  createAlertRule: (payload: AlertRuleInput) => request<AlertRule>("/intelligence/admin/alert-rules", { method: "POST", body: JSON.stringify(payload) }),
  updateAlertRule: (ruleKey: string, payload: AlertRuleInput) =>
    request<AlertRule>(`/intelligence/admin/alert-rules/${encodeURIComponent(ruleKey)}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteAlertRule: (ruleKey: string) =>
    request<void>(`/intelligence/admin/alert-rules/${encodeURIComponent(ruleKey)}`, { method: "DELETE" }),
  simulateAlertRule: (ruleKey: string, payload: AlertRuleInput) => request<AlertRuleSimulation>(`/intelligence/admin/alert-rules/${encodeURIComponent(ruleKey)}/simulate`, { method: "POST", body: JSON.stringify(payload) })
};
