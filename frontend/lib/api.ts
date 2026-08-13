import type {
  AppSetting,
  AccessProfile,
  AdminWorkspaceModule,
  AdminPeopleStructure,
  AdminPersonStructure,
  AuthUser,
  AuditLog,
  AuditOrders,
  PortalAudit,
  CalculationRunHistory,
  CalculationRunSnapshot,
  CollaboratorOrderFilters,
  Collaborator,
  CollaboratorOrderDetail,
  CollaboratorDeleteResult,
  CollaboratorRegistry,
  CollaboratorOrdersDetail,
  CollaboratorPointBalance,
  CollaboratorMonthlyHistoryItem,
  CpkRegionalSnapshot,
  DashboardSummary,
  DashboardBootstrap,
  DashboardFilteredBreakdown,
  DiagnosisPenaltyRule,
  GamificationConfig,
  HealthRule,
  ImportedDiagnosis,
  ImportPreview,
  ImportResult,
  ImportRun,
  ImportServiceOrderAudit,
  LeadershipBonusSummary,
  LeadershipProfile,
  LeadershipRoleProfile,
  LoginResult,
  ManagementCase,
  ManagementCaseComment,
  ManagementCaseFilters,
  ManagementCaseGenerateResult,
  ManagementCasePage,
  ManagementCaseReason,
  ManagementDashboard,
  ManagementOptions,
  Notification,
  EcosystemPermission,
  Permission,
  PenaltyRule,
  PointBalanceEntry,
  PortalOrder,
  PortalOverview,
  PortalProfile,
  PortalRules,
  PortalSimulation,
  PortalSummary,
  PortalTeamSummary,
  RecurrenceAudit,
  RecurrenceClassificationRule,
  ScoringGroupDeleteResult,
  ScoringGroup,
  ScoringSubjectRuleDeleteResult,
  ScoringSubjectRule,
  ServiceOrder,
  ServiceOrderDeletePeriodResult,
  ServiceOrderPeriodSummary,
  ServiceOrderSubjectSummary,
  SlaPenaltyRule,
  UnmappedSubject,
  WorkspaceVisibleModule
} from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "/api";
const TOKEN_KEY = "gamification_auth_token";
const inFlightGetRequests = new Map<string, Promise<unknown>>();

function readStoredToken() {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(TOKEN_KEY);
}

let authToken: string | null = readStoredToken();

export function setAuthToken(token: string | null) {
  authToken = token;
  if (typeof window === "undefined") return;
  if (token) {
    window.sessionStorage.setItem(TOKEN_KEY, token);
  } else {
    window.sessionStorage.removeItem(TOKEN_KEY);
  }
}

function authHeaders(): HeadersInit {
  return authToken ? { Authorization: `Bearer ${authToken}` } : {};
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = init?.method?.toUpperCase() ?? "GET";
  const dedupeKey = method === "GET" ? `${authToken ?? ""}:${path}` : null;
  if (dedupeKey && inFlightGetRequests.has(dedupeKey)) {
    return inFlightGetRequests.get(dedupeKey) as Promise<T>;
  }

  const promise = requestRaw<T>(path, init);
  if (dedupeKey) {
    inFlightGetRequests.set(dedupeKey, promise);
    promise.finally(() => {
      inFlightGetRequests.delete(dedupeKey);
    }).catch(() => undefined);
  }
  return promise;
}

async function requestRaw<T>(path: string, init?: RequestInit): Promise<T> {
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
    throw new Error(extractApiErrorMessage(body, `Erro HTTP ${response.status}`));
  }

  return response.json() as Promise<T>;
}

// O corpo de erro do backend normalmente e um JSON `{"detail": "..."}` - extrai so o texto legivel.
// Nota: parsing e o throw precisam estar em blocos try/catch SEPARADOS - um throw dentro do mesmo
// try que faz o parsing e capturado pelo catch da mesma instrucao, entao o fallback (texto cru,
// as vezes o JSON inteiro sem parsear) sempre "vencia" mesmo quando o parsing tinha dado certo
// (achado real: apareceu um `{"detail":"..."}` cru numa caixa de confirmacao em vez do texto).
function extractApiErrorMessage(body: string, fallback: string): string {
  if (!body) return fallback;
  try {
    const parsed = JSON.parse(body) as { detail?: string; message?: string };
    if (typeof parsed.detail === "string" && parsed.detail) return parsed.detail;
    if (typeof parsed.message === "string" && parsed.message) return parsed.message;
  } catch {
    // corpo nao e JSON valido - cai no fallback abaixo (texto cru)
  }
  return body || fallback;
}

async function requestBlob(path: string): Promise<Blob> {
  const response = await fetch(`${API_URL}${path}`, {
    headers: authHeaders(),
    cache: "no-store"
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(extractApiErrorMessage(body, `Erro HTTP ${response.status}`));
  }
  return response.blob();
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
    throw new Error(extractApiErrorMessage(body, "Falha ao enviar o arquivo."));
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
  portalSummary: (period?: { reference_month: number; reference_year: number }) => {
    const query = period ? `?reference_month=${period.reference_month}&reference_year=${period.reference_year}` : "";
    return request<PortalSummary>(`/portal/summary${query}`);
  },
  portalProfile: () => request<PortalProfile>("/portal/profile"),
  updatePortalProfile: (payload: { phone?: string | null; email?: string | null }) =>
    request<PortalProfile>("/portal/profile", { method: "PUT", body: JSON.stringify(payload) }),
  uploadPortalProfilePhoto: (file: File) => uploadRequest<PortalProfile>("/portal/profile/photo", file),
  portalProfilePhoto: () => requestBlob("/portal/profile/photo"),
  deletePortalProfilePhoto: () => request<PortalProfile>("/portal/profile/photo", { method: "DELETE", body: JSON.stringify({}) }),
  portalOverview: () => request<PortalOverview>("/portal/overview"),
  portalOrders: (limit = 80, period?: { reference_month: number; reference_year: number }) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (period) {
      params.set("reference_month", String(period.reference_month));
      params.set("reference_year", String(period.reference_year));
    }
    return request<PortalOrder[]>(`/portal/my-orders?${params.toString()}`);
  },
  portalAudit: (period?: { reference_month: number; reference_year: number }) => {
    const query = period ? `?reference_month=${period.reference_month}&reference_year=${period.reference_year}` : "";
    return request<PortalAudit>(`/portal/my-audit${query}`);
  },
  portalRules: () => request<PortalRules>("/portal/rules"),
  portalSimulation: (extraPoints: number) =>
    request<PortalSimulation>(`/portal/simulation?extra_points=${encodeURIComponent(String(extraPoints))}`),
  portalTeamSummary: () => request<PortalTeamSummary>("/portal/team-summary"),
  users: () => request<AuthUser[]>("/users"),
  createUser: (payload: { name?: string; email?: string; role?: string; active?: boolean; password: string; collaborator_id?: number | null; managed_regionals?: string[]; access_profile_ids?: number[] }) =>
    request<AuthUser>("/users", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateUser: (id: number, payload: { name?: string; email?: string; role?: string; active?: boolean; password?: string; collaborator_id?: number | null; managed_regionals?: string[]; access_profile_ids?: number[] }) =>
    request<AuthUser>(`/users/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  deleteUser: (id: number) =>
    request<AuthUser>(`/users/${id}`, {
      method: "DELETE"
    }),
  operationRegionals: () => request<string[]>("/admin/operation-regionals"),
  ecosystemPermissions: () => request<EcosystemPermission[]>("/admin/permissions"),
  accessProfiles: () => request<AccessProfile[]>("/admin/access-profiles"),
  createAccessProfile: (payload: { name: string; description?: string | null; active: boolean; permission_keys: Permission[] }) =>
    request<AccessProfile>("/admin/access-profiles", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateAccessProfile: (id: number, payload: { name?: string; description?: string | null; active?: boolean; permission_keys?: Permission[] }) =>
    request<AccessProfile>(`/admin/access-profiles/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  deleteAccessProfile: (id: number) =>
    request<AccessProfile>(`/admin/access-profiles/${id}`, {
      method: "DELETE"
    }),
  workspaceModules: () => request<WorkspaceVisibleModule[]>("/workspace/modules"),
  adminModules: () => request<AdminWorkspaceModule[]>("/admin/modules"),
  updateAdminModuleVisibility: (moduleKey: string, payload: { profile_id: number; visible: boolean; reason?: string | null }) =>
    request<AdminWorkspaceModule>(`/admin/modules/${moduleKey}/visibility`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  updateAdminModuleUserVisibility: (moduleKey: string, payload: { user_id: number; visible: boolean; reason?: string | null }) =>
    request<AdminWorkspaceModule>(`/admin/modules/${moduleKey}/user-visibility`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  deleteAdminModuleUserVisibility: (moduleKey: string, userId: number) =>
    request<AdminWorkspaceModule>(`/admin/modules/${moduleKey}/user-visibility/${userId}`, {
      method: "DELETE"
    }),
  adminPeopleStructure: () => request<AdminPeopleStructure>("/admin/people-structure"),
  updateAdminPersonStructure: (
    id: number,
    payload: {
      cpf?: string | null;
      employee_type?: string | null;
      team_type?: string | null;
      supervisor_user_id?: number | null;
      regional_manager_user_id?: number | null;
      structure_status?: string | null;
      structure_notes?: string | null;
    }
  ) =>
    request<AdminPersonStructure>(`/admin/people-structure/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  managementDashboard: (filters?: { regional?: string; supervisor_user_id?: number; status?: string; search?: string }) => {
    const params = new URLSearchParams();
    if (filters?.regional) params.set("regional", filters.regional);
    if (filters?.supervisor_user_id) params.set("supervisor_user_id", String(filters.supervisor_user_id));
    if (filters?.status) params.set("status", filters.status);
    if (filters?.search) params.set("search", filters.search);
    const query = params.toString();
    return request<ManagementDashboard>(`/management/dashboard${query ? `?${query}` : ""}`);
  },
  managementOptions: () => request<ManagementOptions>("/management/options"),
  refreshManagementStructure: () =>
    request<{ created_candidates: number }>("/management/structure/refresh", {
      method: "POST",
      body: JSON.stringify({})
    }),
  updateManagementMember: (id: number, payload: { supervisor_user_id?: number | null; team_model_id?: number | null; status?: string; notes?: string | null }) =>
    request<{ status: string }>(`/management/members/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  managementCases: (filters?: ManagementCaseFilters) => {
    const params = new URLSearchParams();
    Object.entries(filters ?? {}).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "" || value === false) return;
      params.set(key, String(value));
    });
    const query = params.toString();
    return request<ManagementCasePage>(`/management/cases${query ? `?${query}` : ""}`);
  },
  managementCase: (id: number) => request<ManagementCase>(`/management/cases/${id}`),
  createManagementCase: (payload: {
    case_type: string;
    metric_name: string;
    regional?: string | null;
    responsible_name?: string | null;
    supervisor_user_id?: number | null;
    team_model_id?: number | null;
    reference_year?: number | null;
    reference_month?: number | null;
    expected_value?: number | null;
    actual_value?: number | null;
    deviation_value?: number | null;
    severity?: string;
    due_date?: string | null;
  }) =>
    request<ManagementCase>("/management/cases", { method: "POST", body: JSON.stringify(payload) }),
  openDailyManagementCase: (payload: {
    responsible_name: string;
    regional: string;
    reference_date: string;
    expected_value?: number | null;
    actual_value: number;
  }) =>
    request<ManagementCase>("/management/cases/daily", { method: "POST", body: JSON.stringify(payload) }),
  generateManagementCases: (reference_year: number, reference_month: number) =>
    request<ManagementCaseGenerateResult>("/management/cases/generate", {
      method: "POST",
      body: JSON.stringify({ reference_year, reference_month })
    }),
  justifyManagementCase: (
    id: number,
    payload: { reason_id?: number | null; justification_text: string; action_plan?: string | null; status?: string }
  ) =>
    request<ManagementCase>(`/management/cases/${id}/justify`, { method: "POST", body: JSON.stringify(payload) }),
  reviewManagementCase: (id: number, payload: { status: string; review_note?: string | null; due_date?: string | null }) =>
    request<ManagementCase>(`/management/cases/${id}/review`, { method: "POST", body: JSON.stringify(payload) }),
  managementCaseComments: (id: number) => request<ManagementCaseComment[]>(`/management/cases/${id}/comments`),
  createManagementCaseComment: (id: number, comment: string) =>
    request<ManagementCaseComment>(`/management/cases/${id}/comments`, {
      method: "POST",
      body: JSON.stringify({ comment })
    }),
  managementCaseReasons: (includeInactive?: boolean) =>
    request<ManagementCaseReason[]>(`/management/case-reasons${includeInactive ? "?include_inactive=true" : ""}`),
  createManagementCaseReason: (payload: { name: string; description?: string | null; active?: boolean; requires_description?: boolean }) =>
    request<ManagementCaseReason>("/management/case-reasons", { method: "POST", body: JSON.stringify(payload) }),
  updateManagementCaseReason: (
    id: number,
    payload: { name?: string; description?: string | null; active?: boolean; requires_description?: boolean }
  ) =>
    request<ManagementCaseReason>(`/management/case-reasons/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  managementSettings: () => request<Record<string, string>>("/management/settings"),
  updateManagementSettings: (values: Record<string, string>) =>
    request<Record<string, string>>("/management/settings", { method: "PUT", body: JSON.stringify(values) }),
  notifications: (limit?: number) => request<Notification[]>(`/notifications${limit ? `?limit=${limit}` : ""}`),
  notificationsUnreadCount: () => request<{ unread_count: number }>("/notifications/unread-count"),
  markNotificationRead: (id: number) => request<Notification>(`/notifications/${id}/read`, { method: "POST" }),
  markAllNotificationsRead: () => request<{ marked_read: number }>("/notifications/read-all", { method: "POST" }),
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
  dashboardBootstrap: () => request<DashboardBootstrap>("/dashboard/bootstrap"),
  summary: (period?: { reference_month?: number; reference_year?: number; regional?: string | null }) => {
    const params = new URLSearchParams();
    if (period?.reference_month) params.set("reference_month", String(period.reference_month));
    if (period?.reference_year) params.set("reference_year", String(period.reference_year));
    if (period?.regional) params.set("regional", period.regional);
    const query = params.toString();
    return request<DashboardSummary>(`/dashboard/summary${query ? `?${query}` : ""}`);
  },
  dashboardFilteredBreakdowns: (calculationRunId: number, regionals: string[]) => {
    const params = new URLSearchParams();
    params.set("calculation_run_id", String(calculationRunId));
    regionals.forEach((regional) => {
      if (regional) params.append("regional", regional);
    });
    return request<DashboardFilteredBreakdown>(`/dashboard/filtered-breakdowns?${params.toString()}`);
  },
  calculationRuns: (limit = 24, filters?: { reference_month?: number; reference_year?: number; regional?: string | null; status?: string }) => {
    const params = new URLSearchParams();
    params.set("limit", String(limit));
    if (filters?.reference_month) params.set("reference_month", String(filters.reference_month));
    if (filters?.reference_year) params.set("reference_year", String(filters.reference_year));
    if (filters?.regional) params.set("regional", filters.regional);
    if (filters?.status) params.set("status", filters.status);
    return request<CalculationRunHistory[]>(`/calculation-runs?${params.toString()}`);
  },
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
  syncCpkSnapshot: (year: number, month: number) =>
    request<CpkRegionalSnapshot[]>("/gamification/cpk/sync", {
      method: "POST",
      body: JSON.stringify({ year, month })
    }),
  cpkSnapshot: (year: number, month: number) =>
    request<CpkRegionalSnapshot[]>(`/gamification/cpk/snapshot?year=${year}&month=${month}`),
  calculate: (
    pointValue?: number | null,
    period?: { reference_month?: number; reference_year?: number; regional?: string | null },
    options?: { create_revision?: boolean; execution_note?: string | null }
  ) =>
    request("/calculation-runs/calculate", {
      method: "POST",
      body: JSON.stringify({
        point_value: pointValue ?? undefined,
        reference_month: period?.reference_month,
        reference_year: period?.reference_year,
        regional: period?.regional ?? undefined,
        create_revision: options?.create_revision ?? false,
        execution_note: options?.execution_note ?? undefined
      })
    }),
  calculationRunDetail: (runId: number) => request(`/calculation-runs/${runId}`),
  calculationRunSnapshot: (runId: number) => request<CalculationRunSnapshot>(`/calculation-runs/${runId}/snapshot`),
  updateCalculationRunStatus: (runId: number, payload: { status: string; note?: string | null }) =>
    request(`/calculation-runs/${runId}/status`, {
      method: "PATCH",
      body: JSON.stringify(payload)
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
  serviceOrders: (limit = 500) => request<ServiceOrder[]>(`/service-orders?limit=${limit}`),
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
  importRuns: (params?: { status?: string; file_name?: string; imported_by?: number; date_from?: string; date_to?: string; limit?: number }) => {
    const search = new URLSearchParams();
    if (params?.status) search.set("status", params.status);
    if (params?.file_name) search.set("file_name", params.file_name);
    if (params?.imported_by !== undefined) search.set("imported_by", String(params.imported_by));
    if (params?.date_from) search.set("date_from", params.date_from);
    if (params?.date_to) search.set("date_to", params.date_to);
    if (params?.limit) search.set("limit", String(params.limit));
    const query = search.toString();
    return request<ImportRun[]>(`/imports/runs${query ? `?${query}` : ""}`);
  },
  importRunDetail: (importRunId: number) => request<ImportRun>(`/imports/runs/${importRunId}`),
  importRunAudits: (
    importRunId: number,
    params?: { action?: string; os_code?: string; reason?: string; limit?: number; offset?: number }
  ) => {
    const search = new URLSearchParams();
    if (params?.action) search.set("action", params.action);
    if (params?.os_code) search.set("os_code", params.os_code);
    if (params?.reason) search.set("reason", params.reason);
    if (params?.limit) search.set("limit", String(params.limit));
    if (params?.offset) search.set("offset", String(params.offset));
    const query = search.toString();
    return request<ImportServiceOrderAudit[]>(`/imports/runs/${importRunId}/audits${query ? `?${query}` : ""}`);
  },
  importRunErrors: (importRunId: number, params?: { limit?: number; offset?: number }) => {
    const search = new URLSearchParams();
    if (params?.limit) search.set("limit", String(params.limit));
    if (params?.offset) search.set("offset", String(params.offset));
    const query = search.toString();
    return request<ImportServiceOrderAudit[]>(`/imports/runs/${importRunId}/errors${query ? `?${query}` : ""}`);
  },
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
  uploadCollaboratorPhoto: (id: number, file: File) => uploadRequest<Collaborator>(`/collaborators/${id}/photo`, file),
  collaboratorPhoto: (id: number) => requestBlob(`/collaborators/${id}/photo`),
  deleteCollaboratorPhoto: (id: number) =>
    request<Collaborator>(`/collaborators/${id}/photo`, {
      method: "DELETE"
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
  collaboratorStatementPdf: (collaboratorId: number, calculationRunId: number) =>
    requestBlob(`/collaborators/${collaboratorId}/statement.pdf?calculation_run_id=${calculationRunId}`),
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
  auditOrderDetail: (serviceOrderId: number, calculationRunId?: number) =>
    request<CollaboratorOrderDetail & { collaborator_id: number; collaborator_name: string }>(
      `/audit/service-orders/${serviceOrderId}/detail${calculationRunId ? `?calculation_run_id=${calculationRunId}` : ""}`
    ),
  recurrenceAudit: (serviceOrderId: number) =>
    request<RecurrenceAudit>(`/audit/service-orders/${serviceOrderId}/recurrence-audit`),

  auditLogs: (params?: { action?: string; entity?: string; entity_id?: string; user_id?: number; search?: string; limit?: number; offset?: number }) => {
    const search = new URLSearchParams();
    if (params?.action) search.set("action", params.action);
    if (params?.entity) search.set("entity", params.entity);
    if (params?.entity_id) search.set("entity_id", params.entity_id);
    if (params?.user_id) search.set("user_id", String(params.user_id));
    if (params?.search) search.set("search", params.search);
    if (params?.limit) search.set("limit", String(params.limit));
    if (params?.offset) search.set("offset", String(params.offset));
    const query = search.toString();
    return request<AuditLog[]>(`/audit/logs${query ? `?${query}` : ""}`);
  },

  collaboratorPointBalance: (collaboratorId: number) =>
    request<CollaboratorPointBalance>(`/collaborators/${collaboratorId}/point-balance`),

  collaboratorMonthlyHistory: (collaboratorId: number) =>
    request<CollaboratorMonthlyHistoryItem[]>(`/collaborators/${collaboratorId}/monthly-history`),

  pointBalancePending: (params?: { calculation_run_id?: number; reference_month?: number; reference_year?: number }) => {
    const search = new URLSearchParams();
    if (params?.calculation_run_id) search.set("calculation_run_id", String(params.calculation_run_id));
    if (params?.reference_month) search.set("reference_month", String(params.reference_month));
    if (params?.reference_year) search.set("reference_year", String(params.reference_year));
    const query = search.toString();
    return request<PointBalanceEntry[]>(`/point-balance/pending${query ? `?${query}` : ""}`);
  },

  revertPointBalanceEntry: (entryId: number, reason?: string) =>
    request<PointBalanceEntry>(`/point-balance/entries/${entryId}/revert`, {
      method: "POST",
      body: JSON.stringify({ reason: reason ?? null })
    }),

  createPointBalanceAdjustment: (payload: { collaborator_id: number; points: number; reason: string }) =>
    request<PointBalanceEntry>("/point-balance/entries", {
      method: "POST",
      body: JSON.stringify(payload)
    }),

  resolvePointBalanceReview: (entryId: number, points: number, note?: string) =>
    request<PointBalanceEntry>(`/point-balance/entries/${entryId}/resolve`, {
      method: "POST",
      body: JSON.stringify({ points, note: note ?? null })
    })
};

export { API_URL };
