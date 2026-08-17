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
  confidence: number | null;
  coverage: Record<string, unknown>;
  warnings: Array<Record<string, unknown>>;
  first_detected_at: string;
  last_seen_at: string;
  age_seconds: number;
  source_type: string;
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
  content: CockpitContent[];
  monitor_health: CockpitMonitorHealth[];
  data_freshness: CockpitDataFreshness;
  meta: { applied_filters: Record<string, unknown>; ignored_filters: unknown[]; warnings: Array<Record<string, unknown>>; generated_at: string; source_last_sync: string | null };
};

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

export const intelligenceCockpitApi = {
  getCockpit: (profileKey: string) => request<CockpitPayload>(`/intelligence/cockpit/${encodeURIComponent(profileKey)}`),

  publishContent: (payload: PublishCockpitContentInput) =>
    request<CockpitContent>("/intelligence/cockpit-content", {
      method: "POST",
      body: JSON.stringify(payload)
    })
};
