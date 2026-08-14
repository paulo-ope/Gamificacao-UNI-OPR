export type AiEndpoint = {
  key: string;
  label: string;
  description: string | null;
  kind: string;
  enabled_api: boolean;
  enabled_mcp: boolean;
  enabled_ai: boolean;
  updated_at: string;
};

export type AiEndpointUpdate = Partial<Pick<AiEndpoint, "enabled_api" | "enabled_mcp" | "enabled_ai">>;

export type AiFieldPermission = {
  entity: string;
  field: string;
  filterable: boolean;
  text_filterable: boolean;
  groupable: boolean;
  returnable: boolean;
  selectable: boolean;
  detail_available: boolean;
  sensitive: boolean;
  enabled: boolean;
  updated_at: string;
};

export type AiFieldPermissionUpdate = Partial<
  Pick<AiFieldPermission, "filterable" | "text_filterable" | "groupable" | "returnable" | "selectable" | "detail_available" | "enabled">
>;

export type AiProfileEndpointGrant = {
  profile_id: number;
  endpoint_key: string;
  granted: boolean;
};

export type AiProfileFieldGrant = {
  profile_id: number;
  entity: string;
  field: string;
  granted: boolean;
};

export const AI_API_TOKEN_SCOPES = ["orders.read", "orders.detail", "orders.sla", "orders.aggregate", "infra.read", "users.read"] as const;
export type AiApiTokenScope = (typeof AI_API_TOKEN_SCOPES)[number];

export type AiApiKey = {
  id: number;
  source: "token" | "legacy";
  name: string;
  owner_name: string;
  owner_email: string;
  key_prefix: string;
  scopes: string[] | null;
  expires_at: string | null;
  active: boolean;
  last_used_at: string | null;
  created_at: string;
  revoked_at: string | null;
};

export type AiApiKeyCreateResponse = {
  key: AiApiKey;
  raw_key: string;
};

export type AiAccessAuditLog = {
  id: number;
  occurred_at: string;
  user_name: string | null;
  user_email: string | null;
  token_name: string | null;
  origin: string;
  endpoint_key: string;
  filters_summary: Record<string, number> | null;
  fields_requested: string[] | null;
  response_mode: string | null;
  result_count: number | null;
  duration_ms: number | null;
  status: string;
  error_message: string | null;
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
        message = body.detail.map((item) => item.msg || "Parâmetro inválido.").join(" ");
      }
    } catch {
      // Resposta não JSON: mantém o texto amigável/fallback já definido.
    }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function query(params: Record<string, string | number | undefined>) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") search.set(key, String(value));
  });
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const aiGovernanceApi = {
  listEndpoints: () => request<AiEndpoint[]>("/admin/ai-governance/endpoints"),
  updateEndpoint: (key: string, payload: AiEndpointUpdate) =>
    request<AiEndpoint>(`/admin/ai-governance/endpoints/${encodeURIComponent(key)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  listFields: (entity?: string) => request<AiFieldPermission[]>(`/admin/ai-governance/fields${query({ entity })}`),
  updateField: (entity: string, field: string, payload: AiFieldPermissionUpdate) =>
    request<AiFieldPermission>(`/admin/ai-governance/fields/${encodeURIComponent(entity)}/${encodeURIComponent(field)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  listProfileEndpointGrants: (profileId: number) =>
    request<AiProfileEndpointGrant[]>(`/admin/ai-governance/profiles/${profileId}/endpoint-grants`),
  upsertProfileEndpointGrant: (profileId: number, endpointKey: string, granted: boolean) =>
    request<AiProfileEndpointGrant>(`/admin/ai-governance/profiles/${profileId}/endpoint-grants/${encodeURIComponent(endpointKey)}`, {
      method: "PUT",
      body: JSON.stringify({ granted }),
    }),
  deleteProfileEndpointGrant: (profileId: number, endpointKey: string) =>
    request<void>(`/admin/ai-governance/profiles/${profileId}/endpoint-grants/${encodeURIComponent(endpointKey)}`, {
      method: "DELETE",
    }),

  listProfileFieldGrants: (profileId: number) =>
    request<AiProfileFieldGrant[]>(`/admin/ai-governance/profiles/${profileId}/field-grants`),
  upsertProfileFieldGrant: (profileId: number, entity: string, field: string, granted: boolean) =>
    request<AiProfileFieldGrant>(`/admin/ai-governance/profiles/${profileId}/field-grants`, {
      method: "PUT",
      body: JSON.stringify({ entity, field, granted }),
    }),
  deleteProfileFieldGrant: (profileId: number, entity: string, field: string) =>
    request<void>(`/admin/ai-governance/profiles/${profileId}/field-grants/${encodeURIComponent(entity)}/${encodeURIComponent(field)}`, {
      method: "DELETE",
    }),

  listTokens: () => request<AiApiKey[]>("/admin/ai-governance/tokens"),
  createToken: (name: string, scopes: string[], expiresInDays: number | null) =>
    request<AiApiKeyCreateResponse>("/admin/ai-governance/tokens", {
      method: "POST",
      body: JSON.stringify({ name, scopes, expires_in_days: expiresInDays }),
    }),
  revokeToken: (source: "token" | "legacy", id: number) =>
    request<AiApiKey>(`/admin/ai-governance/tokens/${source}/${id}`, { method: "DELETE" }),

  listAuditLogs: (params?: { origin?: string; endpoint_key?: string; status?: string; limit?: number }) =>
    request<AiAccessAuditLog[]>(`/admin/ai-governance/audit-logs${query(params || {})}`),
};
