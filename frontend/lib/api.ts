import type {
  AppSetting,
  AccessProfile,
  AdminWorkspaceModule,
  AdminWorkspaceModuleSettingsPatch,
  UserPermissionOverrideEffect,
  UserPermissionOverview,
  AdminForcePasswordResetResult,
  AdminPeopleStructure,
  AdminPersonStructure,
  AuthUser,
  AuditLog,
  AuditOrders,
  PortalAudit,
  CalculationRunHistory,
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
  GamificationPreview,
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
  ManagementCaseBulkReviewResult,
  ManagementCaseComment,
  ManagementCaseDiagnostics,
  ManagementCaseFilters,
  ManagementCaseGenerateResult,
  ManagementAutoGenerateSettings,
  ManagementCasePage,
  ManagementCaseReason,
  ManagementDashboard,
  ManagementOperationalMember,
  ManagementOptions,
  ManagementShiftPatternSuggestion,
  StructureAudit,
  Notification,
  EcosystemPermission,
  PermissionKey,
  PointBalanceEntry,
  PortalOrder,
  PortalOverview,
  PortalFirstAccessStatus,
  PortalAccessRequest,
  PortalAccessRequestCpfLookup,
  IxcCpfLookupResult,
  PortalInvite,
  PortalInviteCreateResult,
  PortalInviteStatus,
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
  ServiceOrderDeletePeriodResult,
  ServiceOrderPeriodSummary,
  ServiceOrderSubjectSummary,
  SupportImportResult,
  SupportOpaAttendanceDetail,
  SupportOpaAttendanceFilters,
  SupportOpaAttendancePage,
  SupportOpaAttendanceTimeline,
  SupportOpaAttendantOverride,
  SupportOpaAttendantOverrideCreate,
  SupportOpaAttendantOverrideUpdate,
  SupportOpaAttendantSummary,
  SupportOpaBreakdownDimension,
  SupportOpaBreakdowns,
  SupportIxcAnalyticsContext,
  SupportIxcAnalyticsDimension,
  SupportIxcAnalyticsDriverItem,
  SupportIxcAnalyticsPriorityItem,
  SupportIxcTicketBreakdown,
  SupportIxcTicketBreakdownLevel,
  SupportIxcTicketBurstWindow,
  SupportIxcTicketDailyPoint,
  SupportIxcTicketFilterOptions,
  SupportIxcTicketMomentum,
  SupportIxcTicketOsConversion,
  SupportIxcTicketOverviewKpis,
  SupportIxcTicketSavedFilter,
  SupportIxcTicketSavedFilterValues,
  SupportIxcTicketPage,
  SupportIxcTicketPriorityItem,
  SupportOpaFilters,
  SupportOpaImportMonth,
  SupportOpaSavedFilter,
  SupportOpaSavedFilterScope,
  SupportOpaTimeseries,
  SupportOpaOverview,
  SupportOpaSyncSettings,
  SupportOpaSyncStatus,
  SlaPenaltyRule,
  UnmappedSubject,
  WorkspaceVisibleModule
} from "@/lib/types";

import { authHeader, getAuthToken, notifyUnauthorized, setAuthToken as setAuthTokenShared } from "@/lib/auth-token";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "/api";
/** Espelha `PORTAL_ORDERS_MAX` do backend (`services/portal_dashboard.py`) - teto de O.S. que
 *  `/portal/my-orders` aceita. Pedir menos que isso cortava a lista do colaborador em silêncio. */
export const PORTAL_ORDERS_MAX = 500;
const inFlightGetRequests = new Map<string, Promise<unknown>>();

/**
 * Cache curto para as chamadas que a casca de navegação repete em TODA tela.
 *
 * Com a barra lateral em todas as telas, cada troca de tela remonta a casca e refazia
 * `/auth/me` + `/workspace/modules` antes de conseguir desenhar o menu - o que aparecia como um
 * "Carregando UNI Workspace..." piscando em cada navegação. São respostas que praticamente não
 * mudam durante o uso, então 30 segundos de cache eliminam o ida-e-volta sem esconder mudança de
 * permissão por muito tempo. Toda troca de token limpa o cache (ver `setAuthToken`), o que cobre
 * também o login/logout legado da Gamificação, que chama `setAuthToken` direto.
 *
 * Não entra aqui nada que precise estar sempre fresco - contador de notificações, por exemplo.
 */
const SESSION_CACHE_TTL_MS = 30_000;
const SESSION_CACHED_PATHS = new Set<string>(["/auth/me", "/workspace/modules"]);
const sessionCache = new Map<string, { value: unknown; at: number }>();

function sessionCacheKey(path: string) {
  return `${getAuthToken() ?? ""}:${path}`;
}

/**
 * Descarta uma entrada do cache de sessão (ou o cache inteiro, sem argumento).
 *
 * Existe para a mudança que a PRÓPRIA tela acabou de fazer aparecer na hora, sem esperar os 30
 * segundos. Achado real (2026-09-09): renomear um módulo na Administração atualizava a tabela na
 * hora, mas a barra lateral continuava com o nome antigo até o cache expirar - o que se lê na tela
 * como "salvei e não mudou nada".
 */
export function invalidateSessionCache(path?: string) {
  if (!path) {
    sessionCache.clear();
    return;
  }
  sessionCache.delete(sessionCacheKey(path));
}

/** Leitura SINCRONA do cache, para a tela nascer já com o dado em vez de começar carregando. */
export function peekSessionCache<T>(path: string): T | null {
  const entry = sessionCache.get(sessionCacheKey(path));
  if (!entry || Date.now() - entry.at > SESSION_CACHE_TTL_MS) return null;
  return entry.value as T;
}

// Token/header centralizados em lib/auth-token.ts (achado da auditoria de 2026-09-14: a mesma
// lógica estava duplicada de forma independente em 6 arquivos de API - um deles, localiza-api.ts,
// cacheava o token numa variável própria que login/logout daqui nunca atualizava). `setAuthToken`
// continua exportado DESTE arquivo porque `hooks/use-workspace-auth.ts` e mais 2 telas já importam
// `{ setAuthToken } from "@/lib/api"` - não é um puro re-export porque o efeito colateral de
// limpar `sessionCache` (30s de /auth/me e /workspace/modules) precisa continuar acontecendo, ou
// um login logo após um logout/troca de usuário podia servir o cache do usuário ANTERIOR.
export function setAuthToken(token: string | null) {
  setAuthTokenShared(token);
  sessionCache.clear();
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = init?.method?.toUpperCase() ?? "GET";
  const cacheable = method === "GET" && SESSION_CACHED_PATHS.has(path);
  if (cacheable) {
    const cached = peekSessionCache<T>(path);
    if (cached !== null) return cached;
  }

  const dedupeKey = method === "GET" ? `${getAuthToken() ?? ""}:${path}` : null;
  if (dedupeKey && inFlightGetRequests.has(dedupeKey)) {
    return inFlightGetRequests.get(dedupeKey) as Promise<T>;
  }

  const promise = requestRaw<T>(path, init);
  if (cacheable) {
    void promise
      .then((value) => {
        sessionCache.set(sessionCacheKey(path), { value, at: Date.now() });
      })
      .catch(() => undefined);
  }
  if (dedupeKey) {
    inFlightGetRequests.set(dedupeKey, promise);
    promise.finally(() => {
      inFlightGetRequests.delete(dedupeKey);
    }).catch(() => undefined);
  }
  return promise;
}

async function requestRaw<T>(path: string, init?: RequestInit): Promise<T> {
  const hadToken = Boolean(getAuthToken());
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");
  const token = getAuthToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store"
  });

  // Sessão caiu no meio do uso (token expirou/foi revogado) - `hadToken` distingue isso de uma
  // tentativa de LOGIN com credencial errada (que chega aqui sem token nenhum, e não deve derrubar
  // a tela nem pisar na mensagem de erro que o próprio formulário de login já mostra). Achado da
  // auditoria de 2026-09-14: antes disso, uma sessão expirada virava só "Erro HTTP 401" genérico
  // em cada tela, sem reconduzir ao login.
  if (response.status === 401 && hadToken) {
    notifyUnauthorized();
  }

  if (!response.ok) {
    const body = await response.text();
    throw new Error(extractApiErrorMessage(body, `Erro HTTP ${response.status}`));
  }

  // 204 (e 205/304) não têm corpo - `response.json()` estouraria com "Unexpected end of JSON
  // input" numa resposta de sucesso. Aparece em exclusão que não devolve o recurso (ver
  // `deleteEcosystemPermission`).
  if (response.status === 204 || response.status === 205 || response.headers.get("content-length") === "0") {
    return undefined as T;
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
    const parsed = JSON.parse(body) as { detail?: string | Array<{ msg?: string }>; message?: string };
    if (typeof parsed.detail === "string" && parsed.detail) return parsed.detail;
    // Erro de validação do Pydantic (422) vem como uma LISTA de objetos `{msg, loc, ...}`, não uma
    // string - sem isto o JSON cru aparecia na tela. Mesmo tratamento que `lib/localiza-api.ts` já
    // tinha (achado real registrado em docs/STATUS.md como pendência deste arquivo).
    if (Array.isArray(parsed.detail) && parsed.detail.length > 0) {
      const messages = parsed.detail.map((item) => item?.msg).filter((msg): msg is string => Boolean(msg));
      if (messages.length > 0) return messages.join(" ");
    }
    if (typeof parsed.message === "string" && parsed.message) return parsed.message;
  } catch {
    // corpo nao e JSON valido - cai no fallback abaixo (texto cru)
  }
  return body || fallback;
}

async function requestBlob(path: string): Promise<Blob> {
  const hadToken = Boolean(getAuthToken());
  const response = await fetch(`${API_URL}${path}`, {
    headers: authHeader(),
    cache: "no-store"
  });
  if (response.status === 401 && hadToken) notifyUnauthorized();
  if (!response.ok) {
    const body = await response.text();
    throw new Error(extractApiErrorMessage(body, `Erro HTTP ${response.status}`));
  }
  return response.blob();
}

async function uploadRequest<T>(path: string, file: File): Promise<T> {
  const formData = new FormData();
  formData.append("file", file);

  const hadToken = Boolean(getAuthToken());
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    body: formData,
    headers: authHeader(),
    cache: "no-store"
  });
  if (response.status === 401 && hadToken) notifyUnauthorized();

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
  changePassword: (payload: { current_password: string; new_password: string; confirm_password: string }) =>
    request<AuthUser>("/auth/change-password", { method: "POST", body: JSON.stringify(payload) }),
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
  portalFirstAccessStatus: () => request<PortalFirstAccessStatus>("/portal/first-access/status"),
  completePortalFirstAccess: (payload: { cpf: string; phone: string; email: string; new_password: string; confirm_password: string }) =>
    request<PortalFirstAccessStatus>("/portal/first-access/complete", { method: "POST", body: JSON.stringify(payload) }),
  portalOverview: () => request<PortalOverview>("/portal/overview"),
  portalOrders: (limit = PORTAL_ORDERS_MAX, period?: { reference_month: number; reference_year: number }) => {
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
  forcePasswordReset: (id: number) =>
    request<AdminForcePasswordResetResult>(`/users/${id}/force-password-reset`, { method: "POST" }),
  forceFirstAccessReset: (id: number) =>
    request<AuthUser>(`/users/${id}/force-first-access`, { method: "POST" }),
  listInvites: () => request<PortalInvite[]>("/invites"),
  createInvite: (payload: { email: string; collaborator_id: number; role?: string }) =>
    request<PortalInviteCreateResult>("/invites", { method: "POST", body: JSON.stringify(payload) }),
  revokeInvite: (id: number) => request<PortalInvite>(`/invites/${id}/revoke`, { method: "POST" }),
  lookupIxcCpf: (cpf: string) => request<IxcCpfLookupResult>("/invites/lookup-ixc-cpf", { method: "POST", body: JSON.stringify({ cpf }) }),
  createInviteFromIxc: (payload: { cpf: string; collaborator_id: number; email: string; role?: string }) =>
    request<PortalInviteCreateResult>("/invites/from-ixc", { method: "POST", body: JSON.stringify(payload) }),
  inviteStatus: (token: string) => request<PortalInviteStatus>(`/invites/accept?token=${encodeURIComponent(token)}`),
  acceptInvite: (payload: { token: string; new_password: string; confirm_password: string }) =>
    request<LoginResult>("/invites/accept", { method: "POST", body: JSON.stringify(payload) }),
  lookupAccessRequestCpf: (cpf: string) =>
    request<PortalAccessRequestCpfLookup>("/access-requests/lookup-cpf", { method: "POST", body: JSON.stringify({ cpf }) }),
  submitAccessRequest: (payload: { cpf: string; email: string; new_password: string; confirm_password: string; name?: string; phone?: string }) =>
    request<{ received: boolean }>("/access-requests", { method: "POST", body: JSON.stringify(payload) }),
  listAccessRequests: () => request<PortalAccessRequest[]>("/access-requests"),
  approveAccessRequest: (id: number, payload: { collaborator_id: number; decision_reason?: string | null }) =>
    request<PortalAccessRequest>(`/access-requests/${id}/approve`, { method: "POST", body: JSON.stringify(payload) }),
  rejectAccessRequest: (id: number, payload: { decision_reason: string }) =>
    request<PortalAccessRequest>(`/access-requests/${id}/reject`, { method: "POST", body: JSON.stringify(payload) }),
  operationRegionals: () => request<string[]>("/admin/operation-regionals"),
  ecosystemPermissions: () => request<EcosystemPermission[]>("/admin/permissions"),
  createEcosystemPermission: (payload: {
    key: string;
    label: string;
    module_key?: string | null;
    description?: string | null;
    sensitive?: boolean;
  }) =>
    request<EcosystemPermission>("/admin/permissions", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateEcosystemPermission: (
    key: string,
    payload: { label?: string; module_key?: string | null; description?: string | null; sensitive?: boolean; active?: boolean }
  ) =>
    request<EcosystemPermission>(`/admin/permissions/${encodeURIComponent(key)}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  deleteEcosystemPermission: (key: string) =>
    request<void>(`/admin/permissions/${encodeURIComponent(key)}`, {
      method: "DELETE"
    }),
  accessProfiles: () => request<AccessProfile[]>("/admin/access-profiles"),
  createAccessProfile: (payload: { name: string; description?: string | null; active: boolean; permission_keys: PermissionKey[] }) =>
    request<AccessProfile>("/admin/access-profiles", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateAccessProfile: (id: number, payload: { name?: string; description?: string | null; active?: boolean; permission_keys?: PermissionKey[] }) =>
    request<AccessProfile>(`/admin/access-profiles/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  /** `reassignProfileId` é exigido pelo backend quando o perfil tem usuários vinculados: eles são
   *  movidos para o perfil informado na mesma transação (ver `delete_access_profile`). */
  deleteAccessProfile: (id: number, reassignProfileId?: number | null) =>
    request<AccessProfile>(
      `/admin/access-profiles/${id}${reassignProfileId ? `?reassign_profile_id=${reassignProfileId}` : ""}`,
      { method: "DELETE" }
    ),
  // Permissão concedida ou negada diretamente numa pessoa, sem passar por perfil (ver aba
  // "Permissões individuais" no editor de usuário).
  getUserPermissionOverview: (userId: number) =>
    request<UserPermissionOverview>(`/admin/users/${userId}/permissions`),
  /** Chamar de novo com efeito diferente TROCA a exceção (não empilha) - é assim que a tela
   *  alterna "Conceder"/"Negar" com um clique cada. */
  setUserPermissionOverride: (
    userId: number,
    permission: string,
    payload: { effect: UserPermissionOverrideEffect; reason?: string | null }
  ) =>
    request<UserPermissionOverview>(`/admin/users/${userId}/permissions/${encodeURIComponent(permission)}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  /** Remove a exceção: a pessoa volta a ter exatamente o que o perfil dela concede. */
  deleteUserPermissionOverride: (userId: number, permission: string) =>
    request<UserPermissionOverview>(`/admin/users/${userId}/permissions/${encodeURIComponent(permission)}`, {
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
  /** Nome, descrição, status e ordem do módulo. Campo enviado em branco volta ao padrão do código. */
  updateAdminModuleSettings: (moduleKey: string, payload: AdminWorkspaceModuleSettingsPatch) =>
    request<AdminWorkspaceModule>(`/admin/modules/${moduleKey}/settings`, {
      method: "PUT",
      body: JSON.stringify(payload)
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
  managementDashboard: (filters?: {
    regional?: string;
    supervisor_user_id?: number;
    status?: string;
    search?: string;
    collaborator_regional?: string;
  }) => {
    const params = new URLSearchParams();
    if (filters?.regional) params.set("regional", filters.regional);
    if (filters?.supervisor_user_id) params.set("supervisor_user_id", String(filters.supervisor_user_id));
    if (filters?.status) params.set("status", filters.status);
    if (filters?.search) params.set("search", filters.search);
    if (filters?.collaborator_regional) params.set("collaborator_regional", filters.collaborator_regional);
    const query = params.toString();
    return request<ManagementDashboard>(`/management/dashboard${query ? `?${query}` : ""}`);
  },
  managementOptions: () => request<ManagementOptions>("/management/options"),
  managementStructureAudit: () => request<StructureAudit>("/management/structure-audit"),
  refreshManagementStructure: () =>
    request<{ created_candidates: number }>("/management/structure/refresh", {
      method: "POST",
      body: JSON.stringify({})
    }),
  updateManagementMember: (
    id: number,
    payload: {
      supervisor_user_id?: number | null;
      team_model_id?: number | null;
      status?: string;
      notes?: string | null;
      shift_pattern?: "standard" | "alternating" | null;
      shift_cycle_days_on?: number | null;
      shift_cycle_days_off?: number | null;
      shift_anchor_date?: string | null;
    }
  ) =>
    request<{ status: string }>(`/management/members/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  claimManagementMember: (id: number) =>
    request<ManagementOperationalMember>(`/management/members/${id}/claim`, { method: "POST" }),
  suggestManagementMemberShiftPattern: (id: number) =>
    request<ManagementShiftPatternSuggestion>(`/management/members/${id}/shift-pattern-suggestion`),
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
  openDailyManagementCase: (payload: {
    responsible_name: string;
    regional: string;
    reference_date: string;
    expected_value?: number | null;
    actual_value: number;
  }) =>
    request<ManagementCase>("/management/cases/daily", { method: "POST", body: JSON.stringify(payload) }),
  openMonthlyManagementCase: (payload: {
    responsible_name: string;
    regional: string;
    reference_year: number;
    reference_month: number;
    expected_value?: number | null;
    actual_value: number;
  }) =>
    request<ManagementCase>("/management/cases/monthly", { method: "POST", body: JSON.stringify(payload) }),
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
  exportManagementCases: (filters: ManagementCaseFilters) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "" || key === "page" || key === "page_size") return;
      params.set(key, String(value));
    });
    return requestBlob(`/management/cases/export?${params.toString()}`);
  },
  managementCaseDiagnostics: (filters: ManagementCaseFilters) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "" || key === "page" || key === "page_size") return;
      params.set(key, String(value));
    });
    return request<ManagementCaseDiagnostics>(`/management/cases/diagnostics?${params.toString()}`);
  },
  bulkReviewManagementCases: (payload: { case_ids: number[]; status: string; review_note?: string | null }) =>
    request<ManagementCaseBulkReviewResult>("/management/cases/bulk-review", { method: "POST", body: JSON.stringify(payload) }),
  managementAutoGenerateSettings: () =>
    request<ManagementAutoGenerateSettings>("/management/settings/auto-generate"),
  updateManagementAutoGenerateSettings: (enabled: boolean) =>
    request<ManagementAutoGenerateSettings>("/management/settings/auto-generate", {
      method: "PUT",
      body: JSON.stringify({ enabled })
    }),
  gamificationPreview: () => request<GamificationPreview>("/dashboard/gamification-preview"),
  supportOpaOverview: (filters: SupportOpaAttendanceFilters) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "") return;
      params.set(key, String(value));
    });
    return request<SupportOpaOverview>(`/support/opa/overview?${params.toString()}`);
  },
  supportOpaSyncStatus: () => request<SupportOpaSyncStatus>("/support/opa-sync-status"),
  supportOpaSyncSettings: () => request<SupportOpaSyncSettings>("/support/opa-sync-settings"),
  updateSupportOpaSyncSettings: (payload: Partial<SupportOpaSyncSettings>) =>
    request<SupportOpaSyncSettings>("/support/opa-sync-settings", {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  importSupportOpaPeriod: (period: { date_from: string; date_to: string }) =>
    request<SupportImportResult>("/support/opa-imports", {
      method: "POST",
      body: JSON.stringify(period)
    }),
  supportOpaSyncRun: (runId: number) => request<SupportImportResult>(`/support/opa/sync-runs/${runId}`),
  supportOpaImportMonths: (months = 6) =>
    request<SupportOpaImportMonth[]>(`/support/opa/import-months?months=${months}`),
  supportOpaAttendantOverrides: () =>
    request<SupportOpaAttendantOverride[]>("/support/opa/attendant-overrides"),
  createSupportOpaAttendantOverride: (payload: SupportOpaAttendantOverrideCreate) =>
    request<SupportOpaAttendantOverride>("/support/opa/attendant-overrides", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateSupportOpaAttendantOverride: (id: number, payload: SupportOpaAttendantOverrideUpdate) =>
    request<SupportOpaAttendantOverride>(`/support/opa/attendant-overrides/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  deleteSupportOpaAttendantOverride: (id: number) =>
    request<{ deleted: boolean }>(`/support/opa/attendant-overrides/${id}`, { method: "DELETE" }),
  supportOpaAttendances: (filters: SupportOpaAttendanceFilters) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "") return;
      params.set(key, String(value));
    });
    return request<SupportOpaAttendancePage>(`/support/opa/attendances?${params.toString()}`);
  },
  supportOpaBreakdowns: (
    dimension: SupportOpaBreakdownDimension,
    filters: SupportOpaAttendanceFilters & { limit?: number },
  ) => {
    const params = new URLSearchParams();
    params.set("dimension", dimension);
    Object.entries(filters).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "") return;
      params.set(key, String(value));
    });
    return request<SupportOpaBreakdowns>(`/support/opa/breakdowns?${params.toString()}`);
  },
  supportOpaAttendanceDetail: (id: number) => request<SupportOpaAttendanceDetail>(`/support/opa/attendances/${id}`),
  supportOpaAttendanceTimeline: (id: number, includeMessages = true) =>
    request<SupportOpaAttendanceTimeline>(`/support/opa/attendances/${id}/timeline?include_messages=${includeMessages}`),
  supportOpaTimeseries: (filters: SupportOpaAttendanceFilters) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "") return;
      // A série é sobre o período inteiro do recorte — paginação/ordenação da
      // tabela não fazem parte dele e distorceriam a query se vazassem.
      if (key === "page" || key === "page_size" || key === "sort_by" || key === "sort_dir") return;
      params.set(key, String(value));
    });
    return request<SupportOpaTimeseries>(`/support/opa/timeseries?${params.toString()}`);
  },
  supportOpaSavedFilters: () => request<SupportOpaSavedFilter[]>("/support/opa/saved-filters"),
  createSupportOpaSavedFilter: (payload: { name: string; scope: SupportOpaSavedFilterScope; filters: Record<string, string | number> }) =>
    request<SupportOpaSavedFilter>("/support/opa/saved-filters", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  deleteSupportOpaSavedFilter: (id: number) =>
    request<{ status: string }>(`/support/opa/saved-filters/${id}`, { method: "DELETE" }),
  supportOpaAttendantSummary: (attendantId: string, filters: SupportOpaAttendanceFilters) => {
    const params = new URLSearchParams();
    ([
      "date_from", "date_to", "date_basis", "status", "channel", "department_id", "reason_id", "customer", "search",
      "tag_id", "customer_id", "rating_min", "rating_max", "bot_human",
    ] as const).forEach((key) => {
      const value = filters[key];
      if (value === undefined || value === null || value === "") return;
      params.set(key, String(value));
    });
    const query = params.toString();
    return request<SupportOpaAttendantSummary>(`/support/opa/attendants/${encodeURIComponent(attendantId)}/summary${query ? `?${query}` : ""}`);
  },
  supportOpaFilters: (period?: { date_from?: string; date_to?: string; date_basis?: "opened_at" | "closed_at" }) => {
    const params = new URLSearchParams();
    if (period?.date_from) params.set("date_from", period.date_from);
    if (period?.date_to) params.set("date_to", period.date_to);
    if (period?.date_basis) params.set("date_basis", period.date_basis);
    const query = params.toString();
    return request<SupportOpaFilters>(`/support/opa/filters${query ? `?${query}` : ""}`);
  },
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
    }),

  // Atendimento real do IXC (su_ticket) - indicador antecipado de incidente, drill-down
  // regional -> cidade -> bairro -> motivo/protocolo. Ver docs/STATUS.md 2026-09-11.
  supportIxcTicketBreakdown: (params: {
    level: SupportIxcTicketBreakdownLevel;
    regional?: string;
    city?: string;
    neighborhood?: string;
    subject_id?: string;
    sector_id?: string;
    date_from?: string;
    date_to?: string;
  }) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "") return;
      query.set(key, String(value));
    });
    return request<SupportIxcTicketBreakdown>(`/support/ixc/tickets/breakdown?${query.toString()}`);
  },

  supportIxcTickets: (params: {
    regional?: string;
    city?: string;
    neighborhood?: string;
    subject_id?: string;
    sector_id?: string;
    date_from?: string;
    date_to?: string;
    limit?: number;
    offset?: number;
  }) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "") return;
      query.set(key, String(value));
    });
    return request<SupportIxcTicketPage>(`/support/ixc/tickets?${query.toString()}`);
  },

  supportIxcTicketFilterOptions: () =>
    request<SupportIxcTicketFilterOptions>(`/support/ixc/tickets/filter-options`),

  supportIxcSavedFilters: () => request<SupportIxcTicketSavedFilter[]>("/support/ixc/saved-filters"),
  createSupportIxcSavedFilter: (payload: { name: string; filters: SupportIxcTicketSavedFilterValues; is_default?: boolean }) =>
    request<SupportIxcTicketSavedFilter>("/support/ixc/saved-filters", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  setSupportIxcSavedFilterDefault: (id: number, isDefault: boolean) =>
    request<SupportIxcTicketSavedFilter>(`/support/ixc/saved-filters/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ is_default: isDefault }),
    }),
  deleteSupportIxcSavedFilter: (id: number) =>
    request<{ status: string }>(`/support/ixc/saved-filters/${id}`, { method: "DELETE" }),

  supportIxcTicketOverview: (params: {
    month: string;
    regional?: string;
    subject_id?: string;
    sector_id?: string;
    day?: string;
  }) => {
    const query = new URLSearchParams({ month: params.month });
    if (params.regional) query.set("regional", params.regional);
    if (params.subject_id) query.set("subject_id", params.subject_id);
    if (params.sector_id) query.set("sector_id", params.sector_id);
    if (params.day) query.set("day", params.day);
    return request<SupportIxcTicketOverviewKpis>(`/support/ixc/tickets/overview?${query.toString()}`);
  },

  supportIxcTicketDailySeries: (params: { month: string; regional?: string; subject_id?: string; sector_id?: string }) => {
    const query = new URLSearchParams({ month: params.month });
    if (params.regional) query.set("regional", params.regional);
    if (params.subject_id) query.set("subject_id", params.subject_id);
    if (params.sector_id) query.set("sector_id", params.sector_id);
    return request<SupportIxcTicketDailyPoint[]>(`/support/ixc/tickets/daily-series?${query.toString()}`);
  },

  supportIxcTicketPriorities: (params: { month: string; subject_id?: string; sector_id?: string; day?: string }) => {
    const query = new URLSearchParams({ month: params.month });
    if (params.subject_id) query.set("subject_id", params.subject_id);
    if (params.sector_id) query.set("sector_id", params.sector_id);
    if (params.day) query.set("day", params.day);
    return request<SupportIxcTicketPriorityItem[]>(`/support/ixc/tickets/priorities?${query.toString()}`);
  },

  // Fase 2/3 do plano de evolução analítica do Atendimento IXC (2026-09-15): contrato de
  // contexto único, aditivo aos endpoints acima - modelo de período livre (date_from/date_to +
  // janela anterior de mesmo tamanho), alimenta o painel unificado (ixc-ticket-analytics-panel).
  supportIxcAnalyticsContext: (params: {
    date_from?: string;
    date_to?: string;
    regional?: string;
    city?: string;
    neighborhood?: string;
    subject_id?: string;
    sector_id?: string;
  }) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "") return;
      query.set(key, String(value));
    });
    return request<SupportIxcAnalyticsContext>(`/support/ixc/analytics/context?${query.toString()}`);
  },

  supportIxcAnalyticsPriorities: (params: {
    dimension: SupportIxcAnalyticsDimension;
    date_from?: string;
    date_to?: string;
    regional?: string;
    city?: string;
    neighborhood?: string;
    subject_id?: string;
    sector_id?: string;
  }) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "") return;
      query.set(key, String(value));
    });
    return request<SupportIxcAnalyticsPriorityItem[]>(`/support/ixc/analytics/priorities?${query.toString()}`);
  },

  supportIxcAnalyticsDrivers: (params: {
    date_from?: string;
    date_to?: string;
    regional?: string;
    city?: string;
    neighborhood?: string;
    subject_id?: string;
    sector_id?: string;
  }) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "") return;
      query.set(key, String(value));
    });
    return request<SupportIxcAnalyticsDriverItem[]>(`/support/ixc/analytics/drivers?${query.toString()}`);
  },

  // Item 8 da correção pedida (2026-09-17): "hoje a IA recebe sinais que o usuário não vê na
  // aba" - momentum/burst/conversão em O.S. já existiam no backend sem função correspondente
  // aqui; expostos agora pro painel único mostrar a mesma inteligência que a IA já tinha.
  supportIxcAnalyticsMomentum: (params: { regional?: string; city?: string; subject_id?: string; sector_id?: string }) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "") return;
      query.set(key, String(value));
    });
    return request<SupportIxcTicketMomentum>(`/support/ixc/analytics/momentum?${query.toString()}`);
  },

  supportIxcAnalyticsBursts: (params: { regional?: string }) => {
    const query = new URLSearchParams();
    if (params.regional) query.set("regional", params.regional);
    return request<SupportIxcTicketBurstWindow[]>(`/support/ixc/analytics/bursts?${query.toString()}`);
  },

  supportIxcAnalyticsOsConversion: (params: { date_from?: string; date_to?: string; regional?: string; subject_id?: string; sector_id?: string }) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "") return;
      query.set(key, String(value));
    });
    return request<SupportIxcTicketOsConversion>(`/support/ixc/analytics/os-conversion?${query.toString()}`);
  }
};

export { API_URL };
