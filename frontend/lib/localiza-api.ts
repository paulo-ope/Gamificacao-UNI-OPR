import type { DistanceClassification } from "@/lib/geo-distance";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "/api";
const TOKEN_KEY = "gamification_auth_token";

export type LocationRequestStatus = "pending" | "confirmed" | "invalidated" | "expired";

export type LocationRequest = {
  id: number;
  public_id: string;
  order_code: string | null;
  opa_protocol: string | null;
  customer_id: string | null;
  customer_name: string | null;
  status: LocationRequestStatus;
  registered_latitude: number | null;
  registered_longitude: number | null;
  gps_latitude: number | null;
  gps_longitude: number | null;
  confirmed_latitude: number | null;
  confirmed_longitude: number | null;
  accuracy_meters: number | null;
  adjusted_manually: boolean;
  distance_from_registered_meters: number | null;
  distance_classification: DistanceClassification | null;
  created_at: string;
  created_by_user_id: number | null;
  requested_by_name: string | null;
  expires_at: string;
  opened_at: string | null;
  confirmed_at: string | null;
  invalidated_at: string | null;
};

export type LocationRequestCreateResult = LocationRequest & { token: string; public_link: string };

export type LocationRequestCreatePayload = {
  // Nenhum campo obrigatório sozinho - o backend exige ao menos um identificador entre eles
  // (o link costuma ser enviado antes de existir O.S. no IXC).
  order_code?: string | null;
  opa_protocol?: string | null;
  customer_id?: string | null;
  customer_name?: string | null;
  registered_latitude?: number | null;
  registered_longitude?: number | null;
};

export type PublicLocationStatus = {
  valid: boolean;
  reason: string | null;
  order_code: string | null;
  opa_protocol: string | null;
  customer_name: string | null;
  status: LocationRequestStatus | null;
  expires_at: string | null;
};

export type IxcCustomerMatch = {
  login_id: number | null;
  login: string | null;
  cliente_id: number;
  name: string;
  cpf_masked: string | null;
  latitude: number | null;
  longitude: number | null;
};

export type LocationRequestListFilters = {
  search?: string;
  date_from?: string;
  date_to?: string;
  status?: LocationRequestStatus;
  mine_only?: boolean;
  limit?: number;
};

export type LocalizaSettings = {
  link_ttl_hours: number;
};

export type PublicLocationConfirmPayload = {
  latitude: number;
  longitude: number;
  accuracy_meters: number;
  gps_latitude: number;
  gps_longitude: number;
  adjusted_manually: boolean;
};

let authToken: string | null = typeof window !== "undefined" ? window.localStorage.getItem(TOKEN_KEY) : null;

// O módulo interno reaproveita o MESMO token de sessão que o resto do ecossistema já guarda em
// localStorage (`api.ts` também lê essa chave) - não é uma sessão própria, só evita importar o
// arquivo monolítico `lib/api.ts` inteiro por causa de uma leitura de token.
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");
  if (authToken) headers.set("Authorization", `Bearer ${authToken}`);
  const response = await fetch(`${API_URL}${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(extractApiErrorMessage(body, `Erro HTTP ${response.status}`));
  }
  return response.json() as Promise<T>;
}

function extractApiErrorMessage(body: string, fallback: string): string {
  if (!body) return fallback;
  try {
    const parsed = JSON.parse(body) as { detail?: string | Array<{ msg?: string }> };
    if (typeof parsed.detail === "string" && parsed.detail) return parsed.detail;
    // Erro de validação do Pydantic (422) vem como uma LISTA de objetos `{msg, loc, ...}`, não
    // uma string - sem isto o JSON cru aparecia na tela (achado real, testando o formulário com
    // um valor além do limite de tamanho de um campo).
    if (Array.isArray(parsed.detail) && parsed.detail.length > 0) {
      const messages = parsed.detail.map((item) => item?.msg).filter((msg): msg is string => Boolean(msg));
      if (messages.length > 0) return messages.join(" ");
    }
  } catch {
    // corpo não é JSON válido - cai no fallback (texto cru)
  }
  return body || fallback;
}

export const localizaApi = {
  list: (filters: LocationRequestListFilters = {}) => {
    const params = new URLSearchParams();
    if (filters.search) params.set("search", filters.search);
    if (filters.date_from) params.set("date_from", filters.date_from);
    if (filters.date_to) params.set("date_to", filters.date_to);
    if (filters.status) params.set("status", filters.status);
    if (filters.mine_only) params.set("mine_only", "true");
    if (filters.limit) params.set("limit", String(filters.limit));
    const query = params.toString();
    return request<LocationRequest[]>(`/localiza${query ? `?${query}` : ""}`);
  },
  get: (id: number) => request<LocationRequest>(`/localiza/${id}`),
  getSettings: () => request<LocalizaSettings>("/localiza/settings"),
  updateSettings: (payload: LocalizaSettings) =>
    request<LocalizaSettings>("/localiza/settings", { method: "PUT", body: JSON.stringify(payload) }),
  create: (payload: LocationRequestCreatePayload) =>
    request<LocationRequestCreateResult>("/localiza", { method: "POST", body: JSON.stringify(payload) }),
  invalidate: (id: number) => request<LocationRequest>(`/localiza/${id}/invalidate`, { method: "POST" }),
  regenerate: (id: number) => request<LocationRequestCreateResult>(`/localiza/${id}/regenerate`, { method: "POST" }),
  attachOrder: (id: number, orderCode: string) =>
    request<LocationRequest>(`/localiza/${id}/attach-order`, { method: "POST", body: JSON.stringify({ order_code: orderCode }) }),
  // Busca ao vivo no IXC - por login (número ou texto) OU por CPF, nunca os dois. Usada pra
  // autopreencher o formulário de criação a partir de um cadastro já existente.
  searchIxcByLogin: (login: string) =>
    request<{ matches: IxcCustomerMatch[] }>(`/localiza/ixc/search?login=${encodeURIComponent(login)}`),
  searchIxcByCpf: (cpf: string) =>
    request<{ matches: IxcCustomerMatch[] }>(`/localiza/ixc/search?cpf=${encodeURIComponent(cpf)}`),
  // Rotas públicas: chamadas pela página `/l/{token}`, sem token de sessão (`authToken` fica
  // vazio nesse contexto - o navegador do cliente nunca teve login).
  publicStatus: (token: string) => request<PublicLocationStatus>(`/public/location/${encodeURIComponent(token)}`),
  publicConfirm: (token: string, payload: PublicLocationConfirmPayload) =>
    request<{ status: "confirmed"; confirmed_at: string }>(`/public/location/${encodeURIComponent(token)}/confirm`, {
      method: "POST",
      body: JSON.stringify(payload)
    })
};
