"use client";

import Link from "next/link";
import { Boxes, ExternalLink, History, Home, KeyRound, Loader2, LogOut, PlugZap, Plus, Save, Search, Settings2, ShieldCheck, SlidersHorizontal, Trash2, UserCog, Users, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { WorkspaceLogin } from "@/components/workspace/workspace-login";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AppCheckbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { MultiSelect } from "@/components/ui/multi-select";
import { Tabs, TabsContent } from "@/components/ui/tabs";
import { StatusToast } from "@/components/ui/status-toast";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ModuleNavigationSidebar, type ModuleNavigationItem } from "@/components/workspace/module-navigation-sidebar";
import { ModuleUserVisibilityEditor } from "@/components/workspace/module-user-visibility-editor";
import { IxcSyncSettingsCard } from "@/components/workspace/ixc-sync-settings-card";
import { AuditTrailPanel } from "@/components/shared/audit-trail-panel";
import { AiGovernancePanel } from "@/components/admin/ai-governance-panel";
import { useWorkspaceAuth } from "@/hooks/use-workspace-auth";
import { api } from "@/lib/api";
import { workspaceModules } from "@/lib/module-registry";
import { operationsApi, type OperationIxcSyncSettings } from "@/lib/operations-api";
import type { AccessProfile, AdminPeopleStructure, AdminPersonStructure, AdminWorkspaceModule, AuthUser, EcosystemPermission, Permission } from "@/lib/types";

const PARAMETER_MODULE_LINKS = [
  { module: "Gamificação Operacional", owner: "Pontuação, penalidades, fechamento e pagamento", permissionArea: "Gamificação", path: "/gamificacao" },
  { module: "Operação Analítica", owner: "Modelos de equipe, assuntos, SLA e filtros globais", permissionArea: "Operação", path: "/operacao" },
  { module: "Agendamento", owner: "Metas diárias, expediente, sincronização e equipe", permissionArea: "Agendamento", path: "/agendamento" },
  { module: "SGP Suporte", owner: "Atendimentos, dimensões e sincronização com o OPA Suite", permissionArea: "Suporte", path: "/suporte" },
  { module: "Gestão Integrada", owner: "Estrutura, motivos, prazos, justificativas e revisão", permissionArea: "Gestão", path: "/gestao" },
  { module: "UNI Intelligence", owner: "Monitores, alertas, conteúdo e publicação no cockpit", permissionArea: "Inteligência", path: "/intelligence" },
] as const;

const LEGACY_ROLE_BY_PROFILE: Record<string, AuthUser["role"]> = {
  "Admin Ecossistema": "admin",
  "Operador Operacional": "operator",
  "Leitor Operacional": "viewer",
  "Colaborador Portal": "collaborator",
  "Gestor Regional Portal": "regional_manager_viewer",
};

const STRUCTURE_TYPES = ["Campo", "Agendamento", "Suporte interno", "Supervisor", "Gerente regional", "Matriz"] as const;

const EMPLOYEE_TYPE_LABELS: Record<string, string> = {
  field_technician: "Técnico de campo",
  scheduling_operator: "Agendamento",
  internal_support: "Suporte interno",
  supervisor: "Supervisor",
  regional_manager: "Gerente regional",
  headquarters: "Matriz",
  administrative: "Administrativo",
  other: "Outro",
};

const TEAM_TYPE_LABELS: Record<string, string> = {
  field: "Campo",
  scheduling: "Agendamento",
  internal_support: "Suporte interno",
  regional: "Regional",
  administrative: "Administrativo",
  headquarters: "Matriz",
  other: "Outro",
};

const STRUCTURE_STATUS_LABELS: Record<string, string> = {
  pending_review: "Pendente",
  validated: "Validado",
  needs_fix: "Corrigir",
  outside_operation: "Fora da operação",
  inactive: "Inativo",
};

type AdminTab = "users" | "profiles" | "structure" | "modules" | "parameters" | "integrations" | "ai_governance" | "audit";

const ADMIN_NAV_ITEMS: Array<ModuleNavigationItem<AdminTab>> = [
  { value: "users", label: "Usuários", description: "Acessos e escopo", icon: Users },
  { value: "profiles", label: "Perfis", description: "Permissões por função", icon: ShieldCheck },
  { value: "structure", label: "Pessoas", description: "Estrutura e liderança", icon: UserCog },
  { value: "modules", label: "Módulos", description: "Visibilidade por perfil", icon: Boxes },
  { value: "parameters", label: "Parametrizações", description: "Regras por módulo", icon: SlidersHorizontal },
  { value: "integrations", label: "Integrações", description: "IXC, APIs e IA", icon: PlugZap },
  { value: "ai_governance", label: "Gestão API/MCP", description: "O que a IA pode acessar", icon: KeyRound },
  { value: "audit", label: "Auditoria", description: "Ações sensíveis", icon: History },
];

type UserDraft = {
  id: number | "new";
  name: string;
  email: string;
  password: string;
  active: boolean;
  access_profile_ids: number[];
  managed_regionals: string[];
};

type ProfileDraft = {
  id: number | "new";
  name: string;
  description: string;
  active: boolean;
  permission_keys: Permission[];
};

type PersonStructureDraft = {
  id: number;
  name: string;
  cpf: string;
  employee_type: string;
  team_type: string;
  supervisor_user_id: number | "";
  regional_manager_user_id: number | "";
  structure_status: string;
  structure_notes: string;
};

function blankUserDraft(): UserDraft {
  return {
    id: "new",
    name: "",
    email: "",
    password: "",
    active: true,
    access_profile_ids: [],
    managed_regionals: [],
  };
}

function blankProfileDraft(): ProfileDraft {
  return {
    id: "new",
    name: "",
    description: "",
    active: true,
    permission_keys: [],
  };
}

function profileNames(user: AuthUser, profiles: AccessProfile[]) {
  const names = user.access_profile_ids
    .map((id) => profiles.find((profile) => profile.id === id)?.name)
    .filter(Boolean);
  return names.length ? names.join(", ") : user.role;
}

function permissionGroups(permissions: EcosystemPermission[]) {
  return permissions.reduce<Record<string, EcosystemPermission[]>>((groups, permission) => {
    groups[permission.module] = [...(groups[permission.module] || []), permission];
    return groups;
  }, {});
}

export default function AdminPage() {
  const { user, checking, error: authError, login, logout } = useWorkspaceAuth();
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [profiles, setProfiles] = useState<AccessProfile[]>([]);
  const [permissions, setPermissions] = useState<EcosystemPermission[]>([]);
  const [operationRegionals, setOperationRegionals] = useState<string[]>([]);
  const [peopleStructure, setPeopleStructure] = useState<AdminPeopleStructure | null>(null);
  const [adminModules, setAdminModules] = useState<AdminWorkspaceModule[]>([]);
  const [ixcSyncSettings, setIxcSyncSettings] = useState<OperationIxcSyncSettings | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [userDraft, setUserDraft] = useState<UserDraft | null>(null);
  const [profileDraft, setProfileDraft] = useState<ProfileDraft | null>(null);
  const [personDraft, setPersonDraft] = useState<PersonStructureDraft | null>(null);
  const [personSearch, setPersonSearch] = useState("");
  const [personStatusFilter, setPersonStatusFilter] = useState("all");
  const [permissionSearch, setPermissionSearch] = useState("");
  const [activeTab, setActiveTab] = useState<AdminTab>("users");

  const canAdmin = Boolean(user?.permissions.includes("admin:users:read"));
  const canWriteUsers = Boolean(user?.permissions.includes("admin:users:write"));
  const canDeleteUsers = Boolean(user?.permissions.includes("admin:users:delete"));
  const canWriteProfiles = Boolean(user?.permissions.includes("admin:roles:write"));
  const canReadAudit = Boolean(user?.permissions.includes("admin:audit:read"));
  const canReadAiGovernance = Boolean(user?.permissions.includes("admin:ai_governance:read"));
  const groupedPermissions = useMemo(() => permissionGroups(permissions), [permissions]);
  const filteredPermissionGroups = useMemo(() => {
    const search = permissionSearch.trim().toLocaleLowerCase("pt-BR");
    if (!search) return groupedPermissions;
    return Object.fromEntries(
      Object.entries(groupedPermissions)
        .map(([module, items]) => [
          module,
          items.filter((permission) =>
            `${module} ${permission.label} ${permission.key}`.toLocaleLowerCase("pt-BR").includes(search),
          ),
        ])
        .filter(([, items]) => items.length > 0),
    ) as Record<string, EcosystemPermission[]>;
  }, [groupedPermissions, permissionSearch]);
  const activeUsers = users.filter((item) => item.active).length;
  const filteredPeople = (peopleStructure?.people || []).filter((person) => {
    const search = personSearch.trim().toLowerCase();
    const matchesSearch = !search || `${person.name} ${person.regional} ${person.role}`.toLowerCase().includes(search);
    const matchesStatus = personStatusFilter === "all" || person.structure_status === personStatusFilter;
    return matchesSearch && matchesStatus;
  });
  const visibleModuleRows = adminModules.length
    ? adminModules
    : workspaceModules.map((module) => ({
        key: module.key,
        name: module.name,
        description: module.description,
        web_path: module.webPath,
        api_prefix: module.apiPrefix,
        required_permission: module.requiredPermission,
        status: module.status,
        profiles: [],
        user_overrides: [],
      }));
  const permissionModuleRows = Object.entries(groupedPermissions)
    .map(([module, items]) => ({
      module,
      count: items.length,
      writeCount: items.filter((item) => item.key.includes(":write") || item.key.includes(":manage") || item.key.includes(":sync")).length,
    }))
    .sort((left, right) => left.module.localeCompare(right.module, "pt-BR"));

  async function loadAdminData() {
    setLoading(true);
    setLoadError(null);
    try {
      const [
        nextUsers,
        nextProfiles,
        nextPermissions,
        nextOperationRegionals,
        nextPeopleStructure,
        nextAdminModules,
        nextIxcSyncSettings,
      ] = await Promise.all([
        api.users(),
        api.accessProfiles(),
        api.ecosystemPermissions(),
        api.operationRegionals(),
        api.adminPeopleStructure(),
        api.adminModules(),
        operationsApi.ixcSyncSettings().catch(() => null),
      ]);
      setUsers(nextUsers);
      setProfiles(nextProfiles);
      setPermissions(nextPermissions);
      setOperationRegionals(nextOperationRegionals);
      setPeopleStructure(nextPeopleStructure);
      setAdminModules(nextAdminModules);
      setIxcSyncSettings(nextIxcSyncSettings);
    } catch (reason) {
      setLoadError(reason instanceof Error ? reason.message : "Não foi possível carregar a administração.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (user && canAdmin) void loadAdminData();
  }, [user, canAdmin]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const tab = params.get("tab");
    const person = params.get("person");
    if (tab && ADMIN_NAV_ITEMS.some((item) => item.value === tab)) setActiveTab(tab as AdminTab);
    if (person) setPersonSearch(person);
  }, []);

  if (checking && !user) {
    return (
      <main className="flex min-h-screen items-center justify-center text-sm text-slate-500">
        Carregando Administração...
      </main>
    );
  }
  if (!user) return <WorkspaceLogin isLoading={checking} error={authError} onLogin={login} />;

  if (!canAdmin) {
    return (
      <main className="min-h-screen bg-slate-50 p-6">
        <div className="mx-auto max-w-3xl rounded-3xl border border-amber-200 bg-amber-50 p-6 text-amber-900">
          <h1 className="text-xl font-semibold">Acesso administrativo necessário</h1>
          <p className="mt-2 text-sm">Seu usuário não possui permissão para administrar o ecossistema.</p>
          <Link href="/" className="mt-4 inline-flex text-sm font-semibold text-amber-800">
            Voltar ao ecossistema
          </Link>
        </div>
      </main>
    );
  }

  async function saveUserDraft() {
    if (!userDraft || !userDraft.name.trim() || !userDraft.email.trim()) return;
    if (userDraft.id === "new" && !userDraft.password.trim()) return;
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const selectedProfiles = profiles.filter((profile) => userDraft.access_profile_ids.includes(profile.id));
      const legacyRole = selectedProfiles.find((profile) => profile.legacy_role)?.legacy_role;
      const fallbackRole = LEGACY_ROLE_BY_PROFILE[selectedProfiles[0]?.name || ""] || "viewer";
      const payload = {
        name: userDraft.name.trim(),
        email: userDraft.email.trim(),
        password: userDraft.password.trim() || undefined,
        active: userDraft.active,
        role: (legacyRole || fallbackRole) as AuthUser["role"],
        access_profile_ids: userDraft.access_profile_ids,
        managed_regionals: Array.from(new Set(userDraft.managed_regionals)),
      };
      if (userDraft.id === "new") {
        await api.createUser({ ...payload, password: userDraft.password });
      } else {
        await api.updateUser(userDraft.id, payload);
      }
      setUserDraft(null);
      setMessage("Usuário salvo.");
      await loadAdminData();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível salvar o usuário.");
    } finally {
      setSaving(false);
    }
  }

  async function saveProfileDraft() {
    if (!profileDraft || !profileDraft.name.trim()) return;
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const payload = {
        name: profileDraft.name.trim(),
        description: profileDraft.description.trim() || null,
        active: profileDraft.active,
        permission_keys: profileDraft.permission_keys,
      };
      if (profileDraft.id === "new") {
        await api.createAccessProfile(payload);
      } else {
        await api.updateAccessProfile(profileDraft.id, payload);
      }
      closeProfileEditor();
      setMessage("Perfil salvo.");
      await loadAdminData();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível salvar o perfil.");
    } finally {
      setSaving(false);
    }
  }

  function toggleProfilePermission(permission: Permission) {
    setProfileDraft((current) => {
      if (!current) return current;
      const exists = current.permission_keys.includes(permission);
      return {
        ...current,
        permission_keys: exists
          ? current.permission_keys.filter((item) => item !== permission)
          : [...current.permission_keys, permission].sort(),
      };
    });
  }

  function openProfileEditor(draft: ProfileDraft) {
    setPermissionSearch("");
    setProfileDraft(draft);
  }

  function closeProfileEditor() {
    setPermissionSearch("");
    setProfileDraft(null);
  }

  function setProfileModulePermissions(modulePermissions: EcosystemPermission[], selected: boolean) {
    setProfileDraft((current) => {
      if (!current) return current;
      // Permissões sensíveis (aprovar caso da matriz, administração avançada, gerenciar acesso de
      // outras pessoas) ficam de fora do toggle em lote - achado real: marcar "Gestão Integrada"
      // inteira para dar acesso de rotina a um supervisor também concedia, sem aviso,
      // management:review (aprovar/rejeitar decisão da matriz). Precisam de clique individual.
      const bulkPermissions = modulePermissions.filter((permission) => !permission.sensitive);
      const modulePermissionKeys = bulkPermissions.map((permission) => permission.key);
      const moduleKeys = new Set(modulePermissionKeys);
      const permissionKeys = selected
        ? new Set<Permission>(current.permission_keys.concat(modulePermissionKeys))
        : new Set(current.permission_keys.filter((permission) => !moduleKeys.has(permission)));
      return { ...current, permission_keys: Array.from(permissionKeys).sort() };
    });
  }

  function openPersonDraft(person: AdminPersonStructure) {
    setPersonDraft({
      id: person.id,
      name: person.name,
      cpf: "",
      employee_type: person.employee_type || "",
      team_type: person.team_type || "",
      supervisor_user_id: person.supervisor_user_id || "",
      regional_manager_user_id: person.regional_manager_user_id || "",
      structure_status: person.structure_status || "pending_review",
      structure_notes: person.structure_notes || "",
    });
  }

  async function savePersonDraft() {
    if (!personDraft) return;
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      await api.updateAdminPersonStructure(personDraft.id, {
        cpf: personDraft.cpf.trim() || undefined,
        employee_type: personDraft.employee_type || null,
        team_type: personDraft.team_type || null,
        supervisor_user_id: personDraft.supervisor_user_id === "" ? null : Number(personDraft.supervisor_user_id),
        regional_manager_user_id: personDraft.regional_manager_user_id === "" ? null : Number(personDraft.regional_manager_user_id),
        structure_status: personDraft.structure_status || "pending_review",
        structure_notes: personDraft.structure_notes.trim() || null,
      });
      setPersonDraft(null);
      setMessage("Estrutura salva.");
      await loadAdminData();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível salvar a estrutura.");
    } finally {
      setSaving(false);
    }
  }

  async function updateModuleVisibility(moduleKey: string, profileId: number, visible: boolean) {
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const updated = await api.updateAdminModuleVisibility(moduleKey, { profile_id: profileId, visible });
      setAdminModules((current) => current.map((item) => (item.key === updated.key ? updated : item)));
      setMessage(visible ? "Módulo liberado para o perfil." : "Módulo ocultado para o perfil.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível alterar a visibilidade.");
    } finally {
      setSaving(false);
    }
  }

  async function addModuleUserOverride(moduleKey: string, userId: number, visible: boolean) {
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const updated = await api.updateAdminModuleUserVisibility(moduleKey, { user_id: userId, visible });
      setAdminModules((current) => current.map((item) => (item.key === updated.key ? updated : item)));
      setMessage(visible ? "Módulo liberado para o usuário." : "Módulo ocultado para o usuário.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível alterar a visibilidade individual.");
    } finally {
      setSaving(false);
    }
  }

  async function updateIxcSyncSettings(patch: Partial<Omit<OperationIxcSyncSettings, "available_sectors" | "sector_scope_label">>) {
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const updated = await operationsApi.updateIxcSyncSettings(patch);
      setIxcSyncSettings(updated);
      setMessage("Configuração de sincronização com o IXC atualizada.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível salvar a configuração do IXC.");
    } finally {
      setSaving(false);
    }
  }

  async function removeModuleUserOverride(moduleKey: string, userId: number) {
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const updated = await api.deleteAdminModuleUserVisibility(moduleKey, userId);
      setAdminModules((current) => current.map((item) => (item.key === updated.key ? updated : item)));
      setMessage("Exceção removida. O usuário volta a seguir a visibilidade do perfil.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível remover a exceção.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-4 px-4 py-3 lg:px-7">
          <div className="flex items-center gap-3">
            <ModuleNavigationSidebar
              title="Administração"
              description="Navegação modular do UNI Workspace"
              items={ADMIN_NAV_ITEMS}
              activeItem={activeTab}
              onChange={setActiveTab}
              footer="Novas áreas administrativas devem ser adicionadas a este menu sem alterar a navegação principal."
            />
            <Link
              href="/"
              aria-label="Voltar ao ecossistema"
              className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50 text-blue-700"
            >
              <Home className="h-5 w-5" />
            </Link>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-blue-600">UNI Workspace</p>
              <h1 className="text-base font-semibold text-slate-950">Administração do Ecossistema</h1>
            </div>
          </div>
          <Button type="button" variant="ghost" size="sm" onClick={logout}>
            <LogOut className="h-4 w-4" /> Sair
          </Button>
        </div>
      </header>

      {/* `grid-cols-1` é essencial aqui: sem uma coluna explícita (`minmax(0,1fr)`), o track
          implícito do grid herda o min-content do descendente mais largo (ex.: a tabela de
          usuários) e força a página inteira a ~800px, invisível em qualquer tela menor porque
          html/body usam overflow-x hidden (não gera scroll, só corta o conteúdo). */}
      <section className="mx-auto grid grid-cols-1 max-w-7xl gap-5 px-5 py-6">
        <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-blue-600">Controle central</p>
              <h2 className="mt-1 text-2xl font-semibold text-slate-950">Administração do ecossistema</h2>
              <p className="mt-1 max-w-3xl text-sm text-slate-500">
                Controle unificado para acesso, estrutura, módulos, parametrização e auditoria.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-2 text-center text-xs sm:grid-cols-4">
              <div className="rounded-2xl bg-slate-50 px-4 py-3">
                <p className="text-lg font-bold text-slate-950">{users.length}</p>
                <p className="text-slate-500">Usuários</p>
              </div>
              <div className="rounded-2xl bg-slate-50 px-4 py-3">
                <p className="text-lg font-bold text-slate-950">{activeUsers}</p>
                <p className="text-slate-500">Ativos</p>
              </div>
              <div className="rounded-2xl bg-slate-50 px-4 py-3">
                <p className="text-lg font-bold text-slate-950">{profiles.length}</p>
                <p className="text-slate-500">Perfis</p>
              </div>
              <div className="rounded-2xl bg-slate-50 px-4 py-3">
                <p className="text-lg font-bold text-slate-950">{permissions.length}</p>
                <p className="text-slate-500">Permissões</p>
              </div>
            </div>
          </div>
        </div>

        {loading ? (
          <div className="rounded-3xl border border-slate-200 bg-white p-8 text-sm text-slate-500">
            <Loader2 className="mr-2 inline h-4 w-4 animate-spin" />
            Carregando dados administrativos...
          </div>
        ) : null}
        {loadError ? (
          <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{loadError}</div>
        ) : null}
        <StatusToast
          error={error}
          message={message}
          busy={saving}
          busyLabel="Salvando alterações..."
          onDismissError={() => setError(null)}
          onDismissMessage={() => setMessage(null)}
        />

        <Tabs
          value={activeTab}
          onValueChange={(value) => setActiveTab(value as AdminTab)}
          // Mesmo racional do <section> acima: sem grid-cols-1, o conteúdo mais largo de
          // qualquer TabsContent (tabelas, cards) força esta grid além da viewport.
          className="grid grid-cols-1 gap-5"
        >
          <TabsContent value="users" className="mt-4">
            <div className="rounded-3xl border border-slate-200 bg-white shadow-sm">
              <div className="flex items-center justify-between gap-3 border-b border-slate-200 p-5">
                <div>
                  <h3 className="text-lg font-semibold text-slate-950">Usuários do ecossistema</h3>
                  <p className="text-sm text-slate-500">Controle acesso, perfis e escopo regional.</p>
                </div>
                {canWriteUsers ? (
                  <Button type="button" onClick={() => setUserDraft(blankUserDraft())}>
                    <Plus className="h-4 w-4" /> Novo usuário
                  </Button>
                ) : null}
              </div>
              <div className="overflow-x-auto p-5">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Nome</TableHead>
                      <TableHead>E-mail</TableHead>
                      <TableHead>Perfis</TableHead>
                      <TableHead>Regionais</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Ações</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {users.map((row) => (
                      <TableRow key={row.id}>
                        <TableCell className="font-medium text-slate-950">{row.name}</TableCell>
                        <TableCell className="text-sm text-slate-600">{row.email}</TableCell>
                        <TableCell className="max-w-xs text-sm text-slate-600">{profileNames(row, profiles)}</TableCell>
                        <TableCell className="text-sm text-slate-600">{row.managed_regionals.join(", ") || "—"}</TableCell>
                        <TableCell>
                          <Badge className={row.active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}>
                            {row.active ? "Ativo" : "Inativo"}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <div className="flex justify-end gap-2">
                            {canWriteUsers ? (
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                onClick={() =>
                                  setUserDraft({
                                    id: row.id,
                                    name: row.name,
                                    email: row.email,
                                    password: "",
                                    active: row.active,
                                    access_profile_ids: row.access_profile_ids,
                                    managed_regionals: row.managed_regionals,
                                  })
                                }
                              >
                                Editar
                              </Button>
                            ) : null}
                            {canDeleteUsers ? (
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                className="text-red-600"
                                onClick={async () => {
                                  if (!confirm(`Excluir acesso de ${row.name}?`)) return;
                                  await api.deleteUser(row.id);
                                  await loadAdminData();
                                }}
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </Button>
                            ) : null}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="profiles" className="mt-4">
            <div className="rounded-3xl border border-slate-200 bg-white shadow-sm">
              <div className="flex items-center justify-between gap-3 border-b border-slate-200 p-5">
                <div>
                  <h3 className="text-lg font-semibold text-slate-950">Perfis de acesso</h3>
                  <p className="text-sm text-slate-500">Monte grupos de permissões por módulo.</p>
                </div>
                {canWriteProfiles ? (
                  <Button type="button" onClick={() => openProfileEditor(blankProfileDraft())}>
                    <Plus className="h-4 w-4" /> Novo perfil
                  </Button>
                ) : null}
              </div>
              <div className="grid gap-3 p-5 md:grid-cols-2 xl:grid-cols-3">
                {profiles.map((profile) => (
                  <button
                    key={profile.id}
                    type="button"
                    className="rounded-2xl border border-slate-200 bg-white p-4 text-left transition hover:border-blue-300 hover:shadow"
                    onClick={() =>
                      openProfileEditor({
                        id: profile.id,
                        name: profile.name,
                        description: profile.description || "",
                        active: profile.active,
                        permission_keys: profile.permission_keys,
                      })
                    }
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <h4 className="font-semibold text-slate-950">{profile.name}</h4>
                        <p className="mt-1 line-clamp-2 text-sm text-slate-500">{profile.description || "Sem descrição."}</p>
                      </div>
                      {profile.is_system ? <ShieldCheck className="h-4 w-4 text-blue-600" /> : <UserCog className="h-4 w-4 text-slate-400" />}
                    </div>
                    <div className="mt-3 flex flex-wrap gap-1.5 text-[10px]">
                      <Badge className="border border-slate-200 bg-white text-slate-600">
                        {profile.permission_keys.length} permissões
                      </Badge>
                      <Badge className="border border-slate-200 bg-white text-slate-600">
                        {profile.user_count} usuários
                      </Badge>
                      <Badge className={profile.active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}>
                        {profile.active ? "Ativo" : "Inativo"}
                      </Badge>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </TabsContent>

          <TabsContent value="structure" className="mt-4">
            <div className="grid gap-4 lg:grid-cols-[1fr_1.2fr]">
              <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-semibold text-slate-950">Pessoas e estrutura</h3>
                  <Badge className="bg-blue-50 text-blue-700">Governança</Badge>
                </div>
                <div className="mt-5 grid grid-cols-2 gap-3">
                  <div className="rounded-2xl bg-slate-50 p-4">
                    <p className="text-2xl font-bold text-slate-950">{peopleStructure?.summary.active_people || 0}</p>
                    <p className="text-xs text-slate-500">Pessoas ativas</p>
                  </div>
                  <div className="rounded-2xl bg-slate-50 p-4">
                    <p className="text-2xl font-bold text-slate-950">{peopleStructure?.summary.without_supervisor || 0}</p>
                    <p className="text-xs text-slate-500">Campo sem supervisor</p>
                  </div>
                  <div className="rounded-2xl bg-slate-50 p-4">
                    <p className="text-2xl font-bold text-slate-950">{peopleStructure?.summary.without_team_type || 0}</p>
                    <p className="text-xs text-slate-500">Sem tipo de equipe</p>
                  </div>
                  <div className="rounded-2xl bg-slate-50 p-4">
                    <p className="text-2xl font-bold text-slate-950">{peopleStructure?.summary.pending_review || 0}</p>
                    <p className="text-xs text-slate-500">Pendentes</p>
                  </div>
                </div>
                <div className="mt-5 flex flex-wrap gap-2">
                  {STRUCTURE_TYPES.map((type) => (
                    <Badge key={type} className="border border-slate-200 bg-white text-slate-700">
                      {type}
                    </Badge>
                  ))}
                </div>
              </div>

              <div className="rounded-3xl border border-slate-200 bg-white shadow-sm">
                <div className="flex flex-col gap-3 border-b border-slate-200 p-5 lg:flex-row lg:items-center lg:justify-between">
                  <h3 className="text-lg font-semibold text-slate-950">Colaboradores</h3>
                  <div className="flex flex-col gap-2 sm:flex-row">
                    <Input
                      value={personSearch}
                      placeholder="Buscar pessoa"
                      onChange={(event) => setPersonSearch(event.target.value)}
                    />
                    <select
                      value={personStatusFilter}
                      className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700"
                      onChange={(event) => setPersonStatusFilter(event.target.value)}
                    >
                      <option value="all">Todos</option>
                      {(peopleStructure?.statuses || []).map((status) => (
                        <option key={status} value={status}>{STRUCTURE_STATUS_LABELS[status] || status}</option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="overflow-x-auto p-5">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Colaborador</TableHead>
                        <TableHead>Equipe</TableHead>
                        <TableHead>Supervisor</TableHead>
                        <TableHead>Status</TableHead>
                      <TableHead className="text-right">Ações</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filteredPeople.slice(0, 30).map((row) => (
                        <TableRow key={row.id}>
                          <TableCell>
                            <div className="font-medium text-slate-950">{row.name}</div>
                            <div className="text-xs text-slate-500">{row.regional} · {row.role}</div>
                          </TableCell>
                          <TableCell className="text-sm text-slate-600">
                            {row.team_type ? TEAM_TYPE_LABELS[row.team_type] || row.team_type : "Pendente"}
                          </TableCell>
                          <TableCell className="text-sm text-slate-600">{row.supervisor_name || "Pendente"}</TableCell>
                          <TableCell>
                            <Badge className={row.structure_status === "validated" ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}>
                              {STRUCTURE_STATUS_LABELS[row.structure_status] || row.structure_status}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-right">
                            {canWriteUsers ? (
                              <Button type="button" size="sm" variant="outline" onClick={() => openPersonDraft(row)}>
                                Editar
                              </Button>
                            ) : null}
                          </TableCell>
                        </TableRow>
                      ))}
                      {filteredPeople.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={5} className="py-8 text-center text-sm text-slate-500">
                            Nenhum colaborador encontrado.
                          </TableCell>
                        </TableRow>
                      ) : null}
                    </TableBody>
                  </Table>
                </div>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="modules" className="mt-4">
            <div className="rounded-3xl border border-slate-200 bg-white shadow-sm">
              <div className="flex items-center justify-between gap-3 border-b border-slate-200 p-5">
                <h3 className="text-lg font-semibold text-slate-950">Módulos do ecossistema</h3>
                <Badge className="bg-emerald-50 text-emerald-700">{visibleModuleRows.filter((item) => item.status === "active").length} ativos</Badge>
              </div>
              <div className="overflow-x-auto p-5">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Módulo</TableHead>
                      <TableHead>Rota</TableHead>
                      <TableHead>Permissão mínima</TableHead>
                      <TableHead>Visibilidade por perfil</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {visibleModuleRows.map((module) => (
                      <TableRow key={module.key}>
                        <TableCell>
                          <div className="font-medium text-slate-950">{module.name}</div>
                          <div className="text-xs text-slate-500">{module.description}</div>
                        </TableCell>
                        <TableCell className="text-sm text-slate-600">{module.web_path}</TableCell>
                        <TableCell className="text-xs text-slate-500">{module.required_permission}</TableCell>
                        <TableCell className="min-w-[26rem]">
                          <div className="flex flex-wrap gap-2">
                            {module.profiles.map((profile) => (
                              <button
                                key={profile.profile_id}
                                type="button"
                                disabled={saving || !user.permissions.includes("admin:modules:write")}
                                onClick={() => void updateModuleVisibility(module.key, profile.profile_id, !profile.visible)}
                                className={`rounded-xl border px-3 py-2 text-left text-xs transition ${
                                  profile.visible
                                    ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                                    : "border-slate-200 bg-slate-100 text-slate-500"
                                } ${profile.has_required_permission ? "" : "opacity-60"}`}
                                title={profile.has_required_permission ? "Perfil tem a permissão mínima" : "Perfil não tem a permissão mínima"}
                              >
                                <span className="block font-semibold">{profile.profile_name}</span>
                                <span>{profile.visible ? "Visível" : "Oculto"} · {profile.has_required_permission ? "com permissão" : "sem permissão"}</span>
                              </button>
                            ))}
                          </div>
                          <ModuleUserVisibilityEditor
                            overrides={module.user_overrides}
                            users={users}
                            saving={saving}
                            disabled={saving || !user.permissions.includes("admin:modules:write")}
                            onAdd={(userId, visible) => void addModuleUserOverride(module.key, userId, visible)}
                            onRemove={(userId) => void removeModuleUserOverride(module.key, userId)}
                          />
                        </TableCell>
                        <TableCell>
                          <Badge className={module.status === "active" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}>
                            {module.status === "active" ? "Ativo" : module.status}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="parameters" className="mt-4">
            <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
              <div className="flex flex-col gap-4 border-b border-slate-200 p-5 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <Settings2 className="h-4 w-4 text-blue-600" />
                    <h3 className="text-lg font-semibold text-slate-950">Central de parametrizações</h3>
                  </div>
                  <p className="mt-1 text-sm text-slate-500">Governança de módulos, acessos, integrações e regras operacionais.</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button type="button" size="sm" variant="outline" onClick={() => setActiveTab("profiles")}>
                    <ShieldCheck className="h-4 w-4" /> Perfis e permissões
                  </Button>
                  <Button type="button" size="sm" variant="outline" onClick={() => setActiveTab("modules")}>
                    <Boxes className="h-4 w-4" /> Módulos
                  </Button>
                  <Button type="button" size="sm" variant="outline" onClick={() => setActiveTab("integrations")}>
                    <PlugZap className="h-4 w-4" /> Integrações
                  </Button>
                </div>
              </div>
              <div className="grid border-b border-slate-200 bg-slate-50 sm:grid-cols-2 xl:grid-cols-4">
                {[
                  { label: "Módulos ativos", value: visibleModuleRows.filter((item) => item.status === "active").length },
                  { label: "Áreas de permissão", value: permissionModuleRows.length },
                  { label: "Permissões catalogadas", value: permissions.length },
                  { label: "Perfis configurados", value: profiles.length },
                ].map((item) => (
                  <div key={item.label} className="border-b border-slate-200 px-5 py-4 last:border-b-0 sm:[&:nth-child(odd)]:border-r xl:border-b-0 xl:border-r xl:last:border-r-0">
                    <p className="text-2xl font-semibold text-slate-950">{item.value}</p>
                    <p className="text-xs text-slate-500">{item.label}</p>
                  </div>
                ))}
              </div>
              <div className="p-5">
                <div className="mb-4">
                  <h4 className="font-semibold text-slate-950">Regras por domínio</h4>
                  <p className="mt-1 text-sm text-slate-500">Cada módulo mantém suas regras de negócio e validações no próprio contexto operacional.</p>
                </div>
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {PARAMETER_MODULE_LINKS.map((item) => (
                  <Link
                    key={item.module}
                    href={item.path}
                    className="group rounded-lg border border-slate-200 p-4 transition hover:border-blue-300 hover:bg-blue-50/40"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <h4 className="font-semibold text-slate-950">{item.module}</h4>
                      <ExternalLink className="h-4 w-4 shrink-0 text-slate-400 transition group-hover:text-blue-600" />
                    </div>
                    <p className="mt-2 text-sm text-slate-600">{item.owner}</p>
                    <Badge className="mt-3 border border-slate-200 bg-white text-slate-600">{item.permissionArea}</Badge>
                  </Link>
                ))}
                </div>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="integrations" className="mt-4 grid gap-4">
            <div className="rounded-3xl border border-slate-200 bg-white shadow-sm">
              <div className="border-b border-slate-200 p-5">
                <h3 className="text-lg font-semibold text-slate-950">Sincronização com o IXC</h3>
                <p className="mt-1 text-sm text-slate-500">
                  Regras de tempo de sincronização e escopo de setores usadas pela Operação Analítica.
                </p>
              </div>
              <div className="p-5">
                <IxcSyncSettingsCard
                  settings={ixcSyncSettings}
                  canEdit={Boolean(user.permissions.includes("operations:sync_ixc"))}
                  saving={saving}
                  onSave={updateIxcSyncSettings}
                />
              </div>
            </div>

            <div className="rounded-3xl border border-slate-200 bg-white shadow-sm">
              <div className="border-b border-slate-200 p-5">
                <h3 className="text-lg font-semibold text-slate-950">Outras integrações</h3>
              </div>
              <div className="grid gap-3 p-5 md:grid-cols-2">
                <div className="rounded-2xl border border-slate-200 p-4">
                  <h4 className="font-semibold text-slate-950">API interna</h4>
                  <p className="mt-2 text-sm text-slate-600">Fonte própria para dados não sensíveis</p>
                  <Badge className="mt-3 border border-slate-200 bg-white text-slate-600">Ainda não implementado</Badge>
                </div>
                <button
                  type="button"
                  onClick={() => setActiveTab("ai_governance")}
                  className="rounded-2xl border border-slate-200 p-4 text-left transition hover:border-slate-300 hover:bg-slate-50"
                >
                  <h4 className="font-semibold text-slate-950">IA (API/MCP)</h4>
                  <p className="mt-2 text-sm text-slate-600">Endpoints, campos, perfis, tokens e logs governados pela aba Gestão API/MCP</p>
                  <Badge className="mt-3 border border-emerald-200 bg-emerald-50 text-emerald-700">Abrir Gestão API/MCP</Badge>
                </button>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="ai_governance" className="mt-4 grid gap-4">
            {canReadAiGovernance ? (
              <AiGovernancePanel user={user} profiles={profiles} />
            ) : (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                Seu perfil não possui a permissão admin:ai_governance:read para ver esta tela.
              </div>
            )}
          </TabsContent>

          <TabsContent value="audit" className="mt-4 grid gap-4">
            {canReadAudit ? (
              <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                <AuditTrailPanel title="Auditoria administrativa (todos os módulos)" />
              </div>
            ) : (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                Seu perfil não possui a permissão admin:audit:read para ver a trilha de auditoria.
              </div>
            )}

            <div className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
              <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                <h3 className="text-lg font-semibold text-slate-950">Mapa de permissões</h3>
                <div className="mt-4 grid gap-2">
                  {permissionModuleRows.map((row) => (
                    <div key={row.module} className="flex items-center justify-between rounded-2xl bg-slate-50 px-4 py-3 text-sm">
                      <span className="font-medium text-slate-800">{row.module}</span>
                      <span className="text-slate-500">{row.count} permissões</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="rounded-3xl border border-slate-200 bg-white shadow-sm">
                <div className="border-b border-slate-200 p-5">
                  <h3 className="text-lg font-semibold text-slate-950">Ações sensíveis</h3>
                </div>
                <div className="overflow-x-auto p-5">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Módulo</TableHead>
                        <TableHead>Permissões de escrita</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {permissionModuleRows.map((row) => (
                        <TableRow key={row.module}>
                          <TableCell className="font-medium text-slate-950">{row.module}</TableCell>
                          <TableCell className="text-sm text-slate-600">{row.writeCount}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </section>

      {userDraft ? (
        <div className="fixed inset-0 z-50 flex items-end justify-end bg-slate-950/30 p-4">
          <div className="max-h-[92vh] w-full max-w-2xl overflow-y-auto rounded-3xl bg-white p-5 shadow-xl">
            <h3 className="text-lg font-semibold text-slate-950">{userDraft.id === "new" ? "Novo usuário" : "Editar usuário"}</h3>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <div className="grid gap-2 md:col-span-2">
                <Label>Nome</Label>
                <Input value={userDraft.name} onChange={(event) => setUserDraft({ ...userDraft, name: event.target.value })} />
              </div>
              <div className="grid gap-2">
                <Label>E-mail</Label>
                <Input type="email" value={userDraft.email} onChange={(event) => setUserDraft({ ...userDraft, email: event.target.value })} />
              </div>
              <div className="grid gap-2">
                <Label>{userDraft.id === "new" ? "Senha inicial" : "Nova senha"}</Label>
                <Input
                  type="password"
                  value={userDraft.password}
                  placeholder={userDraft.id === "new" ? "Obrigatória" : "Em branco mantém a atual"}
                  onChange={(event) => setUserDraft({ ...userDraft, password: event.target.value })}
                />
              </div>
              <div className="grid gap-2 md:col-span-2">
                <Label>Regionais permitidas</Label>
                <MultiSelect
                  values={userDraft.managed_regionals}
                  options={Array.from(new Set([...operationRegionals, ...userDraft.managed_regionals])).sort((left, right) => left.localeCompare(right, "pt-BR"))}
                  placeholder="Sem restrição regional"
                  ariaLabel="Selecionar regionais permitidas"
                  onChange={(managed_regionals) => setUserDraft({ ...userDraft, managed_regionals })}
                />
                <p className="text-xs text-slate-500">
                  Selecione uma ou mais regionais. A lista remove duplicidades automaticamente; vazio significa sem restrição regional para este usuário.
                </p>
              </div>
              <div className="grid gap-2 md:col-span-2">
                <Label>Perfis de acesso</Label>
                <div className="grid gap-2 rounded-2xl border border-slate-200 p-3 sm:grid-cols-2">
                  {profiles.map((profile) => (
                    <label key={profile.id} className="flex items-start gap-2 rounded-xl p-2 text-sm hover:bg-slate-50">
                      <AppCheckbox
                        checked={userDraft.access_profile_ids.includes(profile.id)}
                        onCheckedChange={(checked) =>
                          setUserDraft({
                            ...userDraft,
                            access_profile_ids: checked
                              ? [...userDraft.access_profile_ids, profile.id]
                              : userDraft.access_profile_ids.filter((id) => id !== profile.id),
                          })
                        }
                        ariaLabel={profile.name}
                      />
                      <span>
                        <span className="font-medium text-slate-800">{profile.name}</span>
                        <span className="block text-xs text-slate-500">{profile.permission_keys.length} permissões</span>
                      </span>
                    </label>
                  ))}
                </div>
                <p className="text-xs text-slate-500">
                  Remover todos os perfis bloqueia o acesso ao ecossistema para este usuário. Perfis inativos não podem ser vinculados.
                </p>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <AppCheckbox checked={userDraft.active} onCheckedChange={(checked) => setUserDraft({ ...userDraft, active: checked })} ariaLabel="Usuário ativo" />
                Usuário ativo
              </label>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setUserDraft(null)}>Cancelar</Button>
              <Button type="button" onClick={() => void saveUserDraft()} disabled={saving}>
                <Save className="h-4 w-4" /> {saving ? "Salvando..." : "Salvar"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {personDraft && peopleStructure ? (
        <div className="fixed inset-0 z-50 flex items-end justify-end bg-slate-950/30 p-4">
          <div className="max-h-[92vh] w-full max-w-2xl overflow-y-auto rounded-3xl bg-white p-5 shadow-xl">
            <h3 className="text-lg font-semibold text-slate-950">Estrutura do colaborador</h3>
            <p className="mt-1 text-sm text-slate-500">{personDraft.name}</p>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <div className="grid gap-2">
                <Label>CPF</Label>
                <Input
                  value={personDraft.cpf}
                  placeholder="Preencher somente se for alterar"
                  onChange={(event) => setPersonDraft({ ...personDraft, cpf: event.target.value })}
                />
              </div>
              <div className="grid gap-2">
                <Label>Status</Label>
                <select
                  value={personDraft.structure_status}
                  className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700"
                  onChange={(event) => setPersonDraft({ ...personDraft, structure_status: event.target.value })}
                >
                  {peopleStructure.statuses.map((status) => (
                    <option key={status} value={status}>{STRUCTURE_STATUS_LABELS[status] || status}</option>
                  ))}
                </select>
              </div>
              <div className="grid gap-2">
                <Label>Tipo de colaborador</Label>
                <select
                  value={personDraft.employee_type}
                  className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700"
                  onChange={(event) => setPersonDraft({ ...personDraft, employee_type: event.target.value })}
                >
                  <option value="">Sem tipo</option>
                  {peopleStructure.employee_types.map((type) => (
                    <option key={type} value={type}>{EMPLOYEE_TYPE_LABELS[type] || type}</option>
                  ))}
                </select>
              </div>
              <div className="grid gap-2">
                <Label>Tipo de equipe</Label>
                <select
                  value={personDraft.team_type}
                  className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700"
                  onChange={(event) => setPersonDraft({ ...personDraft, team_type: event.target.value })}
                >
                  <option value="">Sem equipe</option>
                  {peopleStructure.team_types.map((type) => (
                    <option key={type} value={type}>{TEAM_TYPE_LABELS[type] || type}</option>
                  ))}
                </select>
              </div>
              <div className="grid gap-2">
                <Label>Supervisor</Label>
                <select
                  value={personDraft.supervisor_user_id}
                  className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700"
                  onChange={(event) => setPersonDraft({ ...personDraft, supervisor_user_id: event.target.value ? Number(event.target.value) : "" })}
                >
                  <option value="">Sem supervisor</option>
                  {peopleStructure.supervisors.map((option) => (
                    <option key={option.id} value={option.id}>{option.name}</option>
                  ))}
                </select>
              </div>
              <div className="grid gap-2">
                <Label>Gerente regional</Label>
                <select
                  value={personDraft.regional_manager_user_id}
                  className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700"
                  onChange={(event) => setPersonDraft({ ...personDraft, regional_manager_user_id: event.target.value ? Number(event.target.value) : "" })}
                >
                  <option value="">Sem gerente</option>
                  {peopleStructure.regional_managers.map((option) => (
                    <option key={option.id} value={option.id}>{option.name}</option>
                  ))}
                </select>
              </div>
              <div className="grid gap-2 md:col-span-2">
                <Label>Observação</Label>
                <Input
                  value={personDraft.structure_notes}
                  onChange={(event) => setPersonDraft({ ...personDraft, structure_notes: event.target.value })}
                />
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setPersonDraft(null)}>Cancelar</Button>
              <Button type="button" onClick={() => void savePersonDraft()} disabled={saving || !canWriteUsers}>
                <Save className="h-4 w-4" /> {saving ? "Salvando..." : "Salvar estrutura"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {profileDraft ? (
        <div className="fixed inset-0 z-50 flex items-end justify-end bg-slate-950/35 sm:p-4" role="dialog" aria-modal="true" aria-labelledby="profile-editor-title">
          <div className="flex h-[100dvh] w-full flex-col overflow-hidden bg-white shadow-xl sm:h-[92vh] sm:max-w-5xl sm:rounded-2xl">
            <div className="shrink-0 border-b border-slate-200 bg-white px-4 py-4 sm:px-5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 id="profile-editor-title" className="text-lg font-semibold text-slate-950">
                    {profileDraft.id === "new" ? "Novo perfil de acesso" : `Editar perfil: ${profileDraft.name}`}
                  </h3>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    <span>{profileDraft.permission_keys.length} permissões selecionadas</span>
                    <span aria-hidden="true">·</span>
                    <span>{profileDraft.active ? "Perfil ativo" : "Perfil inativo"}</span>
                  </div>
                </div>
                <Button type="button" size="icon" variant="ghost" aria-label="Fechar editor de perfil" title="Fechar" onClick={closeProfileEditor}>
                  <X className="h-5 w-5" />
                </Button>
              </div>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-5">
              <section aria-labelledby="profile-identification-title" className="rounded-lg border border-slate-200 p-4">
                <h4 id="profile-identification-title" className="font-semibold text-slate-950">Identificação do perfil</h4>
                <div className="mt-4 grid gap-4 md:grid-cols-[1fr_auto]">
                  <div className="grid gap-2">
                    <Label>Nome do perfil</Label>
                    <Input value={profileDraft.name} onChange={(event) => setProfileDraft({ ...profileDraft, name: event.target.value })} />
                  </div>
                  <label className="flex items-center gap-2 self-end rounded-md border border-slate-200 px-3 py-2.5 text-sm">
                    <AppCheckbox
                      checked={profileDraft.active}
                      disabled={!canWriteProfiles}
                      onCheckedChange={(checked) => setProfileDraft({ ...profileDraft, active: checked })}
                      ariaLabel="Perfil ativo"
                    />
                    Perfil ativo
                  </label>
                  <div className="grid gap-2 md:col-span-2">
                    <Label>Descrição</Label>
                    <Input value={profileDraft.description} onChange={(event) => setProfileDraft({ ...profileDraft, description: event.target.value })} />
                  </div>
                </div>
              </section>

              <section aria-labelledby="profile-permissions-title" className="mt-5">
                <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
                  <div>
                    <h4 id="profile-permissions-title" className="font-semibold text-slate-950">Permissões por módulo</h4>
                    <p className="mt-1 text-sm text-slate-500">Localize uma ação ou selecione o conjunto completo de um módulo.</p>
                  </div>
                  <div className="relative w-full md:max-w-sm">
                    <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                    <Input
                      value={permissionSearch}
                      className="pl-9"
                      placeholder="Buscar módulo ou permissão"
                      aria-label="Buscar módulo ou permissão"
                      onChange={(event) => setPermissionSearch(event.target.value)}
                    />
                  </div>
                </div>

                <div className="mt-4 grid gap-4 lg:grid-cols-2">
                  {Object.entries(filteredPermissionGroups).map(([module, items]) => {
                    const modulePermissions = groupedPermissions[module] || items;
                    const bulkModulePermissions = modulePermissions.filter((permission) => !permission.sensitive);
                    const selectedCount = modulePermissions.filter((permission) => profileDraft.permission_keys.includes(permission.key)).length;
                    const bulkSelectedCount = bulkModulePermissions.filter((permission) => profileDraft.permission_keys.includes(permission.key)).length;
                    const allBulkSelected = bulkModulePermissions.length > 0 && bulkSelectedCount === bulkModulePermissions.length;
                    return (
                      <div key={module} className="overflow-hidden rounded-lg border border-slate-200">
                        <div className="flex items-center justify-between gap-3 border-b border-slate-200 bg-slate-50 px-3 py-2.5">
                          <div className="min-w-0">
                            <h5 className="truncate text-sm font-semibold text-slate-950">{module}</h5>
                            <p className="text-xs text-slate-500">{selectedCount} de {modulePermissions.length} selecionadas</p>
                          </div>
                          {bulkModulePermissions.length > 0 ? (
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              disabled={!canWriteProfiles}
                              onClick={() => setProfileModulePermissions(modulePermissions, !allBulkSelected)}
                            >
                              {allBulkSelected ? "Limpar módulo" : "Selecionar módulo"}
                            </Button>
                          ) : null}
                        </div>
                        <div className="grid gap-1 p-2">
                          {items.map((permission) => (
                            <label key={permission.key} className="flex items-start gap-2 rounded-md p-2 text-sm hover:bg-slate-50">
                              <AppCheckbox
                                checked={profileDraft.permission_keys.includes(permission.key)}
                                disabled={!canWriteProfiles}
                                onCheckedChange={() => toggleProfilePermission(permission.key)}
                                ariaLabel={permission.label}
                              />
                              <span className="min-w-0">
                                <span className="flex items-center gap-1.5 font-medium text-slate-800">
                                  {permission.label}
                                  {permission.sensitive ? (
                                    <span className="rounded-full border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700">
                                      Sensível
                                    </span>
                                  ) : null}
                                </span>
                                <span className="block break-all text-[11px] text-slate-400">{permission.key}</span>
                                {permission.sensitive ? (
                                  <span className="block text-[11px] text-amber-700">
                                    Fora do "Selecionar módulo" - exige marcar aqui, individualmente.
                                  </span>
                                ) : null}
                              </span>
                            </label>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
                {Object.keys(filteredPermissionGroups).length === 0 ? (
                  <div className="mt-4 rounded-lg border border-dashed border-slate-300 px-4 py-10 text-center text-sm text-slate-500">
                    Nenhuma permissão encontrada para a busca informada.
                  </div>
                ) : null}
              </section>
            </div>

            <div className="shrink-0 border-t border-slate-200 bg-white px-4 py-3 sm:px-5">
              <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                {profileDraft.id !== "new" && !profiles.find((profile) => profile.id === profileDraft.id)?.is_system && canWriteProfiles ? (
                  <Button
                    type="button"
                    variant="outline"
                    className="text-red-600"
                    onClick={async () => {
                      if (profileDraft.id === "new" || !confirm("Excluir este perfil?")) return;
                      await api.deleteAccessProfile(profileDraft.id);
                      closeProfileEditor();
                      await loadAdminData();
                    }}
                  >
                    <Trash2 className="h-4 w-4" /> Excluir perfil
                  </Button>
                ) : null}
              </div>
              <div className="flex gap-2">
                <Button type="button" variant="outline" onClick={closeProfileEditor}>Cancelar</Button>
                <Button type="button" onClick={() => void saveProfileDraft()} disabled={saving || !canWriteProfiles}>
                  <Save className="h-4 w-4" /> {saving ? "Salvando..." : "Salvar perfil"}
                </Button>
              </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}
