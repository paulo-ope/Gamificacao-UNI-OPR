import type {
  AppSetting,
  AuthUser,
  AuditOrders,
  CalculationRunHistory,
  CollaboratorOrderFilters,
  Collaborator,
  CollaboratorDeleteResult,
  CollaboratorRegistry,
  CollaboratorOrdersDetail,
  DashboardSummary,
  DiagnosisPenaltyRule,
  GamificationConfig,
  HealthRule,
  ImportedDiagnosis,
  ImportPreview,
  ImportResult,
  LeadershipBonusSummary,
  LeadershipProfile,
  LeadershipRoleProfile,
  LoginResult,
  PenaltyRule,
  RecurrenceAudit,
  RecurrenceClassificationRule,
  ScoringGroupDeleteResult,
  ScoringGroup,
  ScoringRule,
  ScoringSubjectRuleDeleteResult,
  ScoringSubjectRule,
  ServiceOrder,
  ServiceOrderDeletePeriodResult,
  ServiceOrderPeriodSummary,
  ServiceOrderSubjectSummary,
  SlaPenaltyRule,
  UnmappedSubject
} from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "/api";
const TOKEN_KEY = "gamification_auth_token";

let authToken: string | null = typeof window !== "undefined" ? window.localStorage.getItem(TOKEN_KEY) : null;

export function setAuthToken(token: string | null) {
  authToken = token;
  if (typeof window === "undefined") return;
  if (token) {
    window.localStorage.setItem(TOKEN_KEY, token);
  } else {
    window.localStorage.removeItem(TOKEN_KEY);
  }
}

function authHeaders(): HeadersInit {
  return authToken ? { Authorization: `Bearer ${authToken}` } : {};
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");
  if (authToken) headers.set("Authorization", `Bearer ${authToken}`);
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store"
  });

  if (!response.ok) {
    const body = await response.text();
    if (body) {
      try {
        const parsed = JSON.parse(body) as { detail?: string; message?: string };
        throw new Error(parsed.detail || parsed.message || body);
      } catch {
        throw new Error(body);
      }
    }
    throw new Error(`Erro HTTP ${response.status}`);
  }

  return response.json() as Promise<T>;
}

async function uploadRequest<T>(path: string, file: File): Promise<T> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    body: formData,
    headers: authHeaders(),
    cache: "no-store"
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Erro HTTP ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export const api = {
  login: (email: string, password: string) =>
    request<LoginResult>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password })
    }),
  me: () => request<AuthUser>("/auth/me"),
  users: () => request<AuthUser[]>("/users"),
  createUser: (payload: { name?: string; email?: string; role?: string; active?: boolean; password: string }) =>
    request<AuthUser>("/users", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateUser: (id: number, payload: { name?: string; email?: string; role?: string; active?: boolean; password?: string }) =>
    request<AuthUser>(`/users/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  deleteUser: (id: number) =>
    request<AuthUser>(`/users/${id}`, {
      method: "DELETE"
    }),
  leadershipProfiles: () => request<LeadershipProfile[]>("/leadership/profiles"),
  leadershipRoleProfiles: () => request<LeadershipRoleProfile[]>("/leadership/role-profiles"),
  createLeadershipRoleProfile: (payload: Partial<LeadershipRoleProfile>) =>
    request<LeadershipRoleProfile>("/leadership/role-profiles", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateLeadershipRoleProfile: (id: number, payload: Partial<LeadershipRoleProfile>) =>
    request<LeadershipRoleProfile>(`/leadership/role-profiles/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  deleteLeadershipRoleProfile: (id: number) =>
    request<LeadershipRoleProfile>(`/leadership/role-profiles/${id}`, {
      method: "DELETE"
    }),
  createLeadershipProfile: (payload: Partial<LeadershipProfile> & { regional_names: string[] }) =>
    request<LeadershipProfile>("/leadership/profiles", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateLeadershipProfile: (id: number, payload: Partial<LeadershipProfile> & { regional_names?: string[] }) =>
    request<LeadershipProfile>(`/leadership/profiles/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  deleteLeadershipProfile: (id: number) =>
    request<LeadershipProfile>(`/leadership/profiles/${id}`, {
      method: "DELETE"
    }),
  calculateLeadershipBonus: (calculationRunId?: number) =>
    request<LeadershipBonusSummary>(
      `/leadership/bonus-results/calculate${calculationRunId ? `?calculation_run_id=${calculationRunId}` : ""}`,
      { method: "POST", body: JSON.stringify({}) }
    ),
  summary: (period?: { reference_month?: number; reference_year?: number; regional?: string | null }) => {
    const params = new URLSearchParams();
    if (period?.reference_month) params.set("reference_month", String(period.reference_month));
    if (period?.reference_year) params.set("reference_year", String(period.reference_year));
    if (period?.regional) params.set("regional", period.regional);
    const query = params.toString();
    return request<DashboardSummary>(`/dashboard/summary${query ? `?${query}` : ""}`);
  },
  calculationRuns: (limit = 24) => request<CalculationRunHistory[]>(`/calculation-runs?limit=${limit}`),
  gamificationConfig: () => request<GamificationConfig>("/gamification/config"),
  saveGamificationConfig: (payload: Partial<GamificationConfig>) =>
    request<GamificationConfig>("/gamification/config", {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  exportGamificationConfig: () =>
    request<GamificationConfig>("/gamification/config/export", {
      method: "POST",
      body: JSON.stringify({})
    }),
  importGamificationConfig: (payload: Partial<GamificationConfig>) =>
    request<GamificationConfig>("/gamification/config/import", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  resetDefaultGamificationConfig: () =>
    request<GamificationConfig>("/gamification/config/reset-default", {
      method: "POST",
      body: JSON.stringify({})
    }),
  calculate: (pointValue?: number | null, period?: { reference_month?: number; reference_year?: number; regional?: string | null }) =>
    request("/calculation-runs/calculate", {
      method: "POST",
      body: JSON.stringify({
        point_value: pointValue ?? undefined,
        reference_month: period?.reference_month,
        reference_year: period?.reference_year,
        regional: period?.regional ?? undefined
      })
    }),
  scoringGroups: () => request<ScoringGroup[]>("/scoring-groups"),
  createScoringGroup: (payload: Partial<ScoringGroup>) =>
    request<ScoringGroup>("/scoring-groups", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateScoringGroup: (id: number, payload: Partial<ScoringGroup>) =>
    request<ScoringGroup>(`/scoring-groups/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  deleteScoringGroup: (id: number, payload?: { replacement_group_id?: number; delete_linked_rules?: boolean }) =>
    request<ScoringGroupDeleteResult>(`/scoring-groups/${id}`, {
      method: "DELETE",
      body: JSON.stringify(payload ?? {})
    }),
  scoringRules: () => request<ScoringRule[]>("/scoring-rules"),
  updateScoringRule: (id: number, payload: Partial<ScoringRule>) =>
    request<ScoringRule>(`/scoring-rules/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  scoringSubjectRules: () => request<ScoringSubjectRule[]>("/scoring-subject-rules"),
  createScoringSubjectRule: (payload: Partial<ScoringSubjectRule>) =>
    request<ScoringSubjectRule>("/scoring-subject-rules", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateScoringSubjectRule: (id: number, payload: Partial<ScoringSubjectRule>) =>
    request<ScoringSubjectRule>(`/scoring-subject-rules/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  deleteScoringSubjectRule: (id: number) =>
    request<ScoringSubjectRuleDeleteResult>(`/scoring-subject-rules/${id}`, {
      method: "DELETE",
      body: JSON.stringify({})
    }),
  unmappedSubjects: (calculationRunId?: number) =>
    request<UnmappedSubject[]>(
      `/scoring-matrix/unmapped-subjects${calculationRunId ? `?calculation_run_id=${calculationRunId}` : ""}`
    ),
  linkSubjectToGroup: (payload: { group_id: number; os_type: string; os_subject: string }) =>
    request<ScoringSubjectRule>("/scoring-matrix/subjects/link-to-group", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  linkSubjectsToGroups: (items: Array<{ group_id: number; os_type: string; os_subject: string }>) =>
    request<ScoringSubjectRule[]>("/scoring-matrix/subjects/link-to-group/bulk", {
      method: "POST",
      body: JSON.stringify({ items })
    }),
  penaltyRules: () => request<PenaltyRule[]>("/penalty-rules"),
  updatePenaltyRule: (id: number, payload: Partial<PenaltyRule>) =>
    request<PenaltyRule>(`/penalty-rules/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  diagnosisPenaltyRules: () => request<DiagnosisPenaltyRule[]>("/diagnosis-penalty-rules"),
  createDiagnosisPenaltyRule: (payload: Partial<DiagnosisPenaltyRule>) =>
    request<DiagnosisPenaltyRule>("/diagnosis-penalty-rules", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateDiagnosisPenaltyRule: (id: number, payload: Partial<DiagnosisPenaltyRule>) =>
    request<DiagnosisPenaltyRule>(`/diagnosis-penalty-rules/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  importedDiagnoses: (calculationRunId?: number) =>
    request<ImportedDiagnosis[]>(
      `/diagnoses/imported${calculationRunId ? `?calculation_run_id=${calculationRunId}` : ""}`
    ),
  unmappedDiagnoses: (calculationRunId?: number) =>
    request<ImportedDiagnosis[]>(
      `/scoring-matrix/unmapped-diagnoses${calculationRunId ? `?calculation_run_id=${calculationRunId}` : ""}`
    ),
  configureDiagnosis: (payload: Partial<DiagnosisPenaltyRule> & { diagnosis_name: string }) =>
    request<DiagnosisPenaltyRule>("/scoring-matrix/diagnoses/configure", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  configureDiagnoses: (items: Array<Partial<DiagnosisPenaltyRule> & { diagnosis_name: string }>) =>
    request<DiagnosisPenaltyRule[]>("/scoring-matrix/diagnoses/configure/bulk", {
      method: "POST",
      body: JSON.stringify({ items })
    }),
  slaPenaltyRules: () => request<SlaPenaltyRule[]>("/sla-penalty-rules"),
  createSlaPenaltyRule: (payload: Partial<SlaPenaltyRule>) =>
    request<SlaPenaltyRule>("/sla-penalty-rules", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateSlaPenaltyRule: (id: number, payload: Partial<SlaPenaltyRule>) =>
    request<SlaPenaltyRule>(`/sla-penalty-rules/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  recurrenceClassificationRules: () => request<RecurrenceClassificationRule[]>("/recurrence-classification-rules"),
  createRecurrenceClassificationRule: (payload: Partial<RecurrenceClassificationRule>) =>
    request<RecurrenceClassificationRule>("/recurrence-classification-rules", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateRecurrenceClassificationRule: (id: number, payload: Partial<RecurrenceClassificationRule>) =>
    request<RecurrenceClassificationRule>(`/recurrence-classification-rules/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  deleteRecurrenceClassificationRule: (id: number) =>
    request<RecurrenceClassificationRule>(`/recurrence-classification-rules/${id}`, {
      method: "DELETE",
      body: JSON.stringify({})
    }),
  healthRules: () => request<HealthRule[]>("/health-rules"),
  updateHealthRule: (id: number, payload: Partial<HealthRule>) =>
    request<HealthRule>(`/health-rules/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  settings: () => request<AppSetting[]>("/settings"),
  updateSetting: (key: string, value: string) =>
    request<AppSetting>(`/settings/${key}`, {
      method: "PUT",
      body: JSON.stringify({ value })
    }),
  seed: () => request<{ status: string }>("/service-orders/seed", { method: "POST" }),
  serviceOrders: (limit = 10000) => request<ServiceOrder[]>(`/service-orders?limit=${limit}`),
  serviceOrderPeriodSummary: () => request<ServiceOrderPeriodSummary[]>("/service-orders/period-summary"),
  serviceOrderSubjectSummary: (period: { reference_month: number; reference_year: number; regional?: string | null }) => {
    const params = new URLSearchParams();
    params.set("reference_month", String(period.reference_month));
    params.set("reference_year", String(period.reference_year));
    if (period.regional) params.set("regional", period.regional);
    return request<ServiceOrderSubjectSummary[]>(`/service-orders/subject-summary?${params.toString()}`);
  },
  deleteServiceOrdersPeriod: (payload: {
    reference_month: number;
    reference_year: number;
    regional?: string | null;
    confirmation: string;
  }) =>
    request<ServiceOrderDeletePeriodResult>("/service-orders/delete-period", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  previewUpvalueServiceOrders: (file: File) =>
    uploadRequest<ImportPreview>("/imports/upvalue-service-orders/preview", file),
  importUpvalueServiceOrders: (file: File) => uploadRequest<ImportResult>("/imports/upvalue-service-orders", file),
  collaboratorsRegistry: () => request<CollaboratorRegistry>("/collaborators/registry"),
  createCollaborator: (payload: Partial<Collaborator>) =>
    request<Collaborator>("/collaborators", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateCollaborator: (id: number, payload: Partial<Collaborator>) =>
    request<Collaborator>(`/collaborators/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  deleteCollaborator: (id: number) =>
    request<CollaboratorDeleteResult>(`/collaborators/${id}`, {
      method: "DELETE",
      body: JSON.stringify({})
    }),
  collaboratorOrdersDetail: (collaboratorId: number, filters: CollaboratorOrderFilters = {}) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        params.set(key, String(value));
      }
    });
    const query = params.toString();
    return request<CollaboratorOrdersDetail>(
      `/collaborators/${collaboratorId}/scoring-detail${query ? `?${query}` : ""}`
    );
  },
  auditOrders: (filters: CollaboratorOrderFilters & { collaborator_id?: number } = {}) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        params.set(key, String(value));
      }
    });
    const query = params.toString();
    return request<AuditOrders>(`/audit/service-orders-scoring${query ? `?${query}` : ""}`);
  },
  recurrenceAudit: (serviceOrderId: number) =>
    request<RecurrenceAudit>(`/audit/service-orders/${serviceOrderId}/recurrence-audit`)
};

export { API_URL };
