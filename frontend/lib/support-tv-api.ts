// Cliente da TV do SGP Suporte - contrato de `GET /api/support/tv/snapshot`
// (backend/app/modules/support/tv_schemas.py). Mesmo padrão de intelligence-cockpit-api.ts:
// cada domínio com seu próprio request<T> pequeno, sem inchar lib/api.ts.

import { getAuthToken, notifyUnauthorized } from "@/lib/auth-token";

export type SupportTvCoverage = { count: number; total: number; percentage: number | null };

export type SupportTvTmr = {
  current_seconds: number | null;
  previous_seconds: number | null;
  target_seconds: number;
  status: "ok" | "above" | "no_data";
  coverage: SupportTvCoverage;
};

export type SupportTvKpis = {
  total_today: number;
  previous_day_total: number;
  closed_today: number;
  closure_rate: number | null;
  open_now: number;
  tmr_all_responses: SupportTvTmr;
  average_tmr_human_seconds: number | null;
  previous_average_tmr_human_seconds: number | null;
  average_first_response_seconds: number | null;
  average_rating: number | null;
  previous_average_rating: number | null;
};

export type SupportTvHourlyPoint = { hour: number; today: number | null; baseline_average: number | null };
export type SupportTvHourly = { current_hour: number; baseline_weeks_used: number; points: SupportTvHourlyPoint[] };

export type SupportTvCount = { label: string; total: number };

export type SupportTvBotHuman = {
  classified_attendances: number;
  unclassified_attendances: number;
  with_bot: number;
  with_bot_percentage: number | null;
  reached_human: number;
  reached_human_percentage: number | null;
  bot_to_human_handoff: number;
  bot_to_human_handoff_percentage: number | null;
};

export type SupportTvAttendant = {
  attendant_id: string;
  name: string;
  total: number;
  closed: number;
  average_tmr_seconds: number | null;
  average_rating: number | null;
};

export type SupportTvBurst = {
  window: string;
  observed: number;
  expected: number | null;
  ratio: number | null;
  active: boolean;
  // same_weekday = comparado ao mesmo dia da semana nas últimas semanas; none = sem histórico.
  basis: string;
};

export type SupportTvPace = {
  observed_today: number;
  expected_so_far: number | null;
  ratio: number | null;
  status: "normal" | "attention" | "critical" | "no_baseline";
};

export type SupportTvCityAlert = { city: string; today_count: number; expected: number; deviation_pct: number | null };

// Radar de incidente: SÓ protocolos operacionais (assunto 90 do IXC) e SÓ de hoje.
export type SupportTvRadar = {
  scope: "operational";
  baseline_weeks_used: number;
  pace: SupportTvPace | null;
  bursts: SupportTvBurst[] | null;
  cities_at_risk: SupportTvCityAlert[] | null;
};

export type SupportTvN1 = { operational: number; financial: number; total: number; previous_total: number };

export type SupportTvPresenceState = { code: string; label: string; total: number };
export type SupportTvPresenceAgent = { name: string; state_code: string; state_label: string; seconds_in_state: number | null };
export type SupportTvPresence = {
  generated_at: string;
  scope: "departments" | "all";
  total: number;
  available_percentage: number | null;
  states: SupportTvPresenceState[];
  agents: SupportTvPresenceAgent[];
  agents_total: number;
  unmapped_codes: string[];
  ringing_available: boolean;
};

export type SupportTvDepartmentFilter = { department_ids: string[]; department_names: string[] };
export type SupportTvDepartmentOption = { id: string; name: string };
export type SupportTvConfig = {
  department_ids: string[];
  available_departments: SupportTvDepartmentOption[];
  tmr_target_seconds: number;
};

export type SupportTvSnapshot = {
  generated_at: string;
  local_date: string;
  department_filter: SupportTvDepartmentFilter;
  kpis: SupportTvKpis | null;
  hourly: SupportTvHourly | null;
  top_reasons: SupportTvCount[] | null;
  channels: SupportTvCount[] | null;
  bot_human: SupportTvBotHuman | null;
  attendants: SupportTvAttendant[] | null;
  radar: SupportTvRadar;
  n1: SupportTvN1 | null;
  sync: { last_success_at: string | null; consecutive_failures: number };
  unavailable: string[];
};

const API_URL = process.env.NEXT_PUBLIC_API_URL || "/api";

async function request<T>(path: string, init?: RequestInit, fallbackMessage = "Não foi possível atualizar os dados agora."): Promise<T> {
  const headers = new Headers({ "Content-Type": "application/json" });
  const token = getAuthToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_URL}${path}`, { ...init, headers, cache: "no-store" });
  // Sessão caiu no meio do uso - mesmo tratamento dos demais clientes (ver lib/auth-token.ts).
  if (response.status === 401 && token) notifyUnauthorized();
  if (!response.ok) {
    // Nunca expõe corpo técnico cru na TV (norma visual). Só a mensagem de validação do servidor
    // (422, texto pt-BR escrito por nós) passa; o resto vira mensagem amigável.
    if (response.status === 403) throw new Error("Esta conta não tem permissão para isso.");
    if (response.status === 422) {
      try {
        const body = (await response.json()) as { detail?: unknown };
        if (typeof body.detail === "string") throw new Error(body.detail);
      } catch (reason) {
        if (reason instanceof Error && reason.message !== "Unexpected end of JSON input") throw reason;
      }
    }
    throw new Error(fallbackMessage);
  }
  return response.json() as Promise<T>;
}

export const fetchSupportTvSnapshot = () => request<SupportTvSnapshot>("/support/tv/snapshot");

export const fetchSupportTvPresence = () =>
  request<SupportTvPresence>("/support/tv/presence", undefined, "Não foi possível consultar a presença dos atendentes agora.");

export const fetchSupportTvConfig = () => request<SupportTvConfig>("/support/tv/config", undefined, "Não foi possível carregar a configuração.");

export const saveSupportTvConfig = (departmentIds: string[]) =>
  request<SupportTvConfig>(
    "/support/tv/config",
    { method: "PUT", body: JSON.stringify({ department_ids: departmentIds }) },
    "Não foi possível salvar a configuração.",
  );
