"use client";

import Link from "next/link";
import { Loader2 } from "lucide-react";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import { WorkspaceAppShell } from "@/components/workspace/app-shell";
import { StatusToast } from "@/components/ui/status-toast";
import { Tabs, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { AiGovernancePanel } from "@/components/admin/ai-governance-panel";
import { AccessRequestsPanel } from "@/components/admin/access-requests-panel";
import { AdminOverviewPanel } from "@/components/admin/admin-overview-panel";
import { AuditPanelSection } from "@/components/admin/audit-panel-section";
import { IntegrationsPanel } from "@/components/admin/integrations-panel";
import { InternalAccountsPanel } from "@/components/admin/internal-accounts-panel";
import { InvitesPanel } from "@/components/admin/invites-panel";
import { ModuleSettingsDrawer } from "@/components/admin/module-settings-drawer";
import { ModulesPanel } from "@/components/admin/modules-panel";
import { PermissionsPanel } from "@/components/admin/permissions-panel";
import { OverviewSettingsPanel } from "@/components/admin/overview-settings-panel";
import { PeopleStructurePanel } from "@/components/admin/people-structure-panel";
import { PersonEditorDrawer } from "@/components/admin/person-editor-drawer";
import { PortalAccountsPanel } from "@/components/admin/portal-accounts-panel";
import { ProfileEditorDrawer } from "@/components/admin/profile-editor-drawer";
import { ProfilesPanel } from "@/components/admin/profiles-panel";
import { UserEditorDrawer } from "@/components/admin/user-editor-drawer";
import { UserPermissionOverridesDrawer } from "@/components/admin/user-permission-overrides-drawer";
import {
  ADMIN_NAV_ITEMS,
  blankUserDraft,
  LEGACY_ROLE_BY_PROFILE,
  permissionGroups,
  type AdminTab,
  type PersonStructureDraft,
  type VisibleModuleRow,
  type ProfileDraft,
  type UserDraft,
} from "@/components/admin/admin-shared";
import { useConfirm } from "@/hooks/use-confirm";
import { notifyWorkspaceModulesChanged } from "@/hooks/use-visible-modules";
import { usePrompt } from "@/hooks/use-prompt";
import { api } from "@/lib/api";
import { workspaceModules } from "@/lib/module-registry";
import { operationsApi, type OperationIxcSyncSettings } from "@/lib/operations-api";
import type { AccessProfile, AdminPeopleStructure, AdminPersonStructure, AdminWorkspaceModule, AdminWorkspaceModuleSettingsPatch, AuthUser, EcosystemPermission, EcosystemPermissionDraft, PermissionKey, PortalAccessRequest, PortalInvite, PortalInviteCreateResult } from "@/lib/types";

export default function AdminPage() {
  return (
    <WorkspaceAppShell
      activePath="/admin"
      title="Administração do Ecossistema"
      subtitle="Usuários, perfis de acesso, permissões e escopos"
    >
      {(user) => (
        <Suspense
          fallback={
            <p className="py-16 text-center text-sm text-slate-500" aria-busy="true">
              Carregando Administração...
            </p>
          }
        >
          <AdminPageContent user={user} />
        </Suspense>
      )}
    </WorkspaceAppShell>
  );
}

// A casca (`WorkspaceAppShell`) resolve autenticação, cabeçalho, sino, sair e o menu lateral com as
// telas deste módulo - aqui só chega o usuário pronto.
function AdminPageContent({ user }: { user: AuthUser }) {
  // Substituem `window.confirm`/`window.prompt` (achado real, 2026-08-29: `window.prompt` lançava
  // exceção não tratada e `window.confirm` podia ser silenciosamente ignorado em determinados
  // ambientes de navegador, deixando revogar convite/rejeitar solicitação sem efeito nenhum,
  // sem erro visível) - mesmo componente de diálogo já usado em outras telas do projeto.
  const { confirm, ConfirmDialog } = useConfirm();
  const { promptText, PromptDialog } = usePrompt();
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
  const [revealedTemporaryPassword, setRevealedTemporaryPassword] = useState<{ name: string; password: string } | null>(null);
  const [invites, setInvites] = useState<PortalInvite[]>([]);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteCollaboratorId, setInviteCollaboratorId] = useState("");
  const [creatingInvite, setCreatingInvite] = useState(false);
  const [revealedInviteLink, setRevealedInviteLink] = useState<{ email: string; link: string } | null>(null);
  const [accessRequests, setAccessRequests] = useState<PortalAccessRequest[]>([]);
  const [approveCollaboratorByRequest, setApproveCollaboratorByRequest] = useState<Record<number, string>>({});
  const [decidingAccessRequestId, setDecidingAccessRequestId] = useState<number | null>(null);
  const [profileDraft, setProfileDraft] = useState<ProfileDraft | null>(null);
  const [moduleSettingsDraft, setModuleSettingsDraft] = useState<VisibleModuleRow | null>(null);
  const [permissionOverridesUser, setPermissionOverridesUser] = useState<{ id: number; name: string } | null>(null);
  const [personDraft, setPersonDraft] = useState<PersonStructureDraft | null>(null);
  const [personSearch, setPersonSearch] = useState("");
  const [personStatusFilter, setPersonStatusFilter] = useState("all");
  const [permissionSearch, setPermissionSearch] = useState("");
  const [activeTab, setActiveTab] = useState<AdminTab>("overview");

  const canAdmin = Boolean(user?.permissions.includes("admin:users:read"));
  const canWriteUsers = Boolean(user?.permissions.includes("admin:users:write"));
  const canDeleteUsers = Boolean(user?.permissions.includes("admin:users:delete"));
  const canWriteProfiles = Boolean(user?.permissions.includes("admin:roles:write"));
  const canReadPermissions = Boolean(user?.permissions.includes("admin:permissions:read"));
  const canWritePermissions = Boolean(user?.permissions.includes("admin:permissions:write"));
  const canWriteModules = Boolean(user?.permissions.includes("admin:modules:write"));
  const canEditIxcSync = Boolean(user?.permissions.includes("operations:sync_ixc"));
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
  // Fallback só para o primeiro quadro antes de `/admin/modules` responder: os valores do registro
  // local, sem nenhum ajuste do admin (que só o backend conhece). `customized: false` aqui é
  // honesto - este fallback não sabe se existe ajuste, e ele é substituído assim que a lista chega.
  const visibleModuleRows: VisibleModuleRow[] = adminModules.length
    ? adminModules
    : workspaceModules.map((module, index) => ({
        key: module.key,
        name: module.name,
        description: module.description,
        web_path: module.webPath,
        api_prefix: module.apiPrefix,
        required_permission: module.requiredPermission,
        status: module.status,
        default_name: module.name,
        default_description: module.description,
        default_status: module.status,
        customized: false,
        sort_order: index,
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
        nextInvites,
        nextAccessRequests,
      ] = await Promise.all([
        api.users(),
        api.accessProfiles(),
        api.ecosystemPermissions(),
        api.operationRegionals(),
        api.adminPeopleStructure(),
        api.adminModules(),
        operationsApi.ixcSyncSettings().catch(() => null),
        api.listInvites(),
        api.listAccessRequests(),
      ]);
      setUsers(nextUsers);
      setProfiles(nextProfiles);
      setPermissions(nextPermissions);
      setOperationRegionals(nextOperationRegionals);
      setPeopleStructure(nextPeopleStructure);
      setAdminModules(nextAdminModules);
      setAccessRequests(nextAccessRequests);
      setIxcSyncSettings(nextIxcSyncSettings);
      setInvites(nextInvites);
    } catch (reason) {
      setLoadError(reason instanceof Error ? reason.message : "Não foi possível carregar a administração.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (user && canAdmin) void loadAdminData();
  }, [user, canAdmin]);

  // Tela pedida pela URL (`?tab=`), como o menu lateral do ecossistema linka. Vem de
  // `useSearchParams` e não de `window.location`: em navegação pelo lado do cliente a URL do
  // navegador ainda não está atualizada na primeira renderização da rota nova, e o efeito com
  // `[]` como dependência nunca reexecuta - clicar num submenu da Administração na barra lateral
  // trocava a URL mas a aba aberta continuava a mesma (achado real, 2026-09-03).
  const searchParams = useSearchParams();
  useEffect(() => {
    const tab = searchParams.get("tab");
    const person = searchParams.get("person");
    if (tab && ADMIN_NAV_ITEMS.some((item) => item.value === tab)) setActiveTab(tab as AdminTab);
    if (person) setPersonSearch(person);
  }, [searchParams]);

  if (!canAdmin) {
    return (
      <div className="mx-auto max-w-3xl rounded-3xl border border-amber-200 bg-amber-50 p-6 text-amber-900">
        <h2 className="text-xl font-semibold">Acesso administrativo necessário</h2>
        <p className="mt-2 text-sm">Seu usuário não possui permissão para administrar o ecossistema.</p>
      </div>
    );
  }

  function updateUserDraft(patch: Partial<UserDraft>) {
    setUserDraft((current) => (current ? { ...current, ...patch } : current));
  }

  function updateProfileDraft(patch: Partial<ProfileDraft>) {
    setProfileDraft((current) => (current ? { ...current, ...patch } : current));
  }

  function updatePersonDraft(patch: Partial<PersonStructureDraft>) {
    setPersonDraft((current) => (current ? { ...current, ...patch } : current));
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

  async function forcePasswordReset(row: AuthUser) {
    const ok = await confirm({
      title: "Forçar troca de senha",
      description: `Gerar uma senha temporária para ${row.name}? A pessoa vai precisar trocá-la no próximo login.`,
      confirmLabel: "Gerar senha temporária",
    });
    if (!ok) return;
    setMessage(null);
    setError(null);
    try {
      const result = await api.forcePasswordReset(row.id);
      setRevealedTemporaryPassword({ name: row.name, password: result.temporary_password });
      await loadAdminData();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível gerar a senha temporária.");
    }
  }

  async function forceFirstAccessReset(row: AuthUser) {
    const ok = await confirm({
      title: "Forçar primeiro acesso completo",
      description: `Reabrir o primeiro acesso completo de ${row.name}? A pessoa vai precisar reconfirmar CPF/contato e definir uma senha nova no próximo login.`,
      confirmLabel: "Reabrir primeiro acesso",
    });
    if (!ok) return;
    setMessage(null);
    setError(null);
    try {
      await api.forceFirstAccessReset(row.id);
      setMessage("Primeiro acesso reaberto.");
      await loadAdminData();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível reabrir o primeiro acesso.");
    }
  }

  async function deleteUserAction(row: AuthUser) {
    const ok = await confirm({
      title: "Excluir acesso",
      description: `Excluir acesso de ${row.name}?`,
      confirmLabel: "Excluir",
      tone: "danger",
    });
    if (!ok) return;
    await api.deleteUser(row.id);
    await loadAdminData();
  }

  async function createInviteSubmit() {
    if (!inviteEmail.trim() || !inviteCollaboratorId) return;
    setCreatingInvite(true);
    setMessage(null);
    setError(null);
    try {
      const result = await api.createInvite({ email: inviteEmail.trim(), collaborator_id: Number(inviteCollaboratorId) });
      const link = `${window.location.origin}/convite?token=${result.token}`;
      setRevealedInviteLink({ email: result.email, link });
      setInviteEmail("");
      setInviteCollaboratorId("");
      await loadAdminData();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível criar o convite.");
    } finally {
      setCreatingInvite(false);
    }
  }

  async function handleIxcInviteCreated(result: PortalInviteCreateResult) {
    const link = `${window.location.origin}/convite?token=${result.token}`;
    setRevealedInviteLink({ email: result.email, link });
    setMessage("Convite gerado a partir do IXC.");
    await loadAdminData();
  }

  async function revokeInviteAction(invite: PortalInvite) {
    const ok = await confirm({
      title: "Revogar convite",
      description: `Revogar o convite de ${invite.email}?`,
      confirmLabel: "Revogar",
      tone: "danger",
    });
    if (!ok) return;
    setMessage(null);
    setError(null);
    try {
      await api.revokeInvite(invite.id);
      setMessage("Convite revogado.");
      await loadAdminData();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível revogar o convite.");
    }
  }

  async function approveAccessRequestAction(request: PortalAccessRequest) {
    const collaboratorId = approveCollaboratorByRequest[request.id] || (request.suggested_collaborator_id ? String(request.suggested_collaborator_id) : "");
    if (!collaboratorId) {
      setError("Selecione o colaborador antes de aprovar.");
      return;
    }
    const ok = await confirm({
      title: "Aprovar solicitação",
      description: `Aprovar a solicitação de ${request.name}? A conta é criada direto, com a senha que a pessoa já definiu, vinculada ao colaborador escolhido.`,
      confirmLabel: "Aprovar",
    });
    if (!ok) return;
    setDecidingAccessRequestId(request.id);
    setMessage(null);
    setError(null);
    try {
      const result = await api.approveAccessRequest(request.id, { collaborator_id: Number(collaboratorId) });
      setMessage(`Solicitação aprovada. A conta de ${result.email} já pode acessar o Portal.`);
      await loadAdminData();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível aprovar a solicitação.");
    } finally {
      setDecidingAccessRequestId(null);
    }
  }

  async function rejectAccessRequestAction(request: PortalAccessRequest) {
    const reason = await promptText({
      title: "Rejeitar solicitação",
      description: `Motivo da rejeição da solicitação de ${request.name}:`,
      label: "Motivo",
      placeholder: "Ex.: CPF não corresponde a nenhum colaborador ativo.",
      confirmLabel: "Rejeitar",
    });
    if (reason === null) return;
    setDecidingAccessRequestId(request.id);
    setMessage(null);
    setError(null);
    try {
      await api.rejectAccessRequest(request.id, { decision_reason: reason });
      setMessage("Solicitação rejeitada.");
      await loadAdminData();
    } catch (rejectReason) {
      setError(rejectReason instanceof Error ? rejectReason.message : "Não foi possível rejeitar a solicitação.");
    } finally {
      setDecidingAccessRequestId(null);
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

  function toggleProfilePermission(permission: PermissionKey) {
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

  async function deleteProfileAction(reassignProfileId: number | null) {
    if (!profileDraft || profileDraft.id === "new") return;
    const destination = reassignProfileId ? profiles.find((profile) => profile.id === reassignProfileId) : null;
    const ok = await confirm({
      title: "Excluir perfil",
      description: destination
        ? `Excluir "${profileDraft.name}" e mover as pessoas vinculadas para "${destination.name}"?`
        : `Excluir o perfil "${profileDraft.name}"?`,
      confirmLabel: "Excluir",
      tone: "danger",
    });
    if (!ok) return;
    // O try/catch não existia (achado real): um 409 do backend - "perfil vinculado a usuários" -
    // estourava sem nada aparecer na tela, e o clique parecia simplesmente não fazer efeito.
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      await api.deleteAccessProfile(profileDraft.id, reassignProfileId);
      closeProfileEditor();
      setMessage(destination ? `Perfil excluído. Pessoas movidas para "${destination.name}".` : "Perfil excluído.");
      await loadAdminData();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível excluir o perfil.");
    } finally {
      setSaving(false);
    }
  }

  async function createPermission(draft: EcosystemPermissionDraft) {
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      await api.createEcosystemPermission({
        key: draft.key,
        label: draft.label,
        module_key: draft.module_key || null,
        description: draft.description || null,
        sensitive: draft.sensitive,
      });
      setMessage("Permissão criada.");
      await loadAdminData();
    } finally {
      setSaving(false);
    }
  }

  async function updatePermission(key: string, draft: EcosystemPermissionDraft) {
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      await api.updateEcosystemPermission(key, {
        label: draft.label,
        module_key: draft.module_key || null,
        description: draft.description || null,
        sensitive: draft.sensitive,
      });
      setMessage("Permissão atualizada.");
      await loadAdminData();
    } finally {
      setSaving(false);
    }
  }

  async function deletePermissionAction(permission: EcosystemPermission) {
    const inUse = permission.profile_count > 0;
    const ok = await confirm({
      title: "Excluir permissão",
      description: inUse
        ? `"${permission.label}" está em ${permission.profile_count} perfil(is) e afeta ${permission.user_count} pessoa(s). O backend vai recusar até você removê-la desses perfis.`
        : `Excluir a permissão "${permission.label}" (${permission.key})?`,
      confirmLabel: "Excluir",
      tone: "danger",
    });
    if (!ok) return;
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      await api.deleteEcosystemPermission(permission.key);
      setMessage("Permissão excluída.");
      await loadAdminData();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível excluir a permissão.");
    } finally {
      setSaving(false);
    }
  }

  async function saveModuleSettings(moduleKey: string, patch: AdminWorkspaceModuleSettingsPatch) {
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      await api.updateAdminModuleSettings(moduleKey, patch);
      setModuleSettingsDraft(null);
      setMessage("Módulo atualizado.");
      // Nome, status e ordem também alimentam a barra lateral do ecossistema
      // (`/workspace/modules`, com cache curto de sessão) - sem este aviso ela ficava com o valor
      // antigo por até 30s depois de salvar, parecendo que nada mudou.
      notifyWorkspaceModulesChanged();
      await loadAdminData();
    } finally {
      setSaving(false);
    }
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
        ? new Set<PermissionKey>(current.permission_keys.concat(modulePermissionKeys))
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
    <div className="min-w-0">
      {/* `grid-cols-1` é essencial aqui: sem uma coluna explícita (`minmax(0,1fr)`), o track
          implícito do grid herda o min-content do descendente mais largo (ex.: a tabela de
          usuários) e força a página inteira a ~800px, invisível em qualquer tela menor porque
          html/body usam overflow-x hidden (não gera scroll, só corta o conteúdo). */}
      <section className="grid grid-cols-1 gap-5">
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
        {ConfirmDialog}
        {PromptDialog}

        <Tabs
          value={activeTab}
          onValueChange={(value) => setActiveTab(value as AdminTab)}
          // Mesmo racional do <section> acima: sem grid-cols-1, o conteúdo mais largo de
          // qualquer TabsContent (tabelas, cards) força esta grid além da viewport.
          className="grid grid-cols-1 gap-5"
        >
          <TabsContent value="overview" className="mt-4">
            <AdminOverviewPanel
              users={users}
              activeUsers={activeUsers}
              profiles={profiles}
              permissions={permissions}
              invites={invites}
              accessRequests={accessRequests}
              peopleStructure={peopleStructure}
              visibleModuleRows={visibleModuleRows}
              permissionModuleRows={permissionModuleRows}
              onNavigate={setActiveTab}
            />
          </TabsContent>

          <TabsContent value="internal_accounts" className="mt-4">
            <InternalAccountsPanel
              users={users}
              profiles={profiles}
              canWriteUsers={canWriteUsers}
              canDeleteUsers={canDeleteUsers}
              onNewUser={() => setUserDraft(blankUserDraft())}
              revealedTemporaryPassword={revealedTemporaryPassword}
              onDismissRevealedPassword={() => setRevealedTemporaryPassword(null)}
              onEdit={(row) =>
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
              onForcePasswordReset={forcePasswordReset}
              onForceFirstAccessReset={forceFirstAccessReset}
              onDelete={deleteUserAction}
            />
          </TabsContent>

          <TabsContent value="portal_accounts" className="mt-4">
            <PortalAccountsPanel
              users={users}
              profiles={profiles}
              canWriteUsers={canWriteUsers}
              canDeleteUsers={canDeleteUsers}
              revealedTemporaryPassword={revealedTemporaryPassword}
              onDismissRevealedPassword={() => setRevealedTemporaryPassword(null)}
              onEdit={(row) =>
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
              onForcePasswordReset={forcePasswordReset}
              onForceFirstAccessReset={forceFirstAccessReset}
              onDelete={deleteUserAction}
            />
          </TabsContent>

          <TabsContent value="invites" className="mt-4">
            <InvitesPanel
              people={peopleStructure?.people || []}
              invites={invites}
              canWriteUsers={canWriteUsers}
              inviteEmail={inviteEmail}
              inviteCollaboratorId={inviteCollaboratorId}
              creatingInvite={creatingInvite}
              revealedInviteLink={revealedInviteLink}
              onInviteEmailChange={setInviteEmail}
              onInviteCollaboratorIdChange={setInviteCollaboratorId}
              onCreateInvite={createInviteSubmit}
              onIxcInviteCreated={handleIxcInviteCreated}
              onDismissRevealedInviteLink={() => setRevealedInviteLink(null)}
              onRevokeInvite={revokeInviteAction}
            />
          </TabsContent>

          <TabsContent value="access_requests" className="mt-4">
            <AccessRequestsPanel
              accessRequests={accessRequests}
              people={peopleStructure?.people || []}
              canWriteUsers={canWriteUsers}
              decidingAccessRequestId={decidingAccessRequestId}
              approveCollaboratorByRequest={approveCollaboratorByRequest}
              onApproveCollaboratorChange={(requestId, collaboratorId) =>
                setApproveCollaboratorByRequest((prev) => ({ ...prev, [requestId]: collaboratorId }))
              }
              onApprove={approveAccessRequestAction}
              onReject={rejectAccessRequestAction}
            />
          </TabsContent>

          <TabsContent value="profiles" className="mt-4">
            <ProfilesPanel profiles={profiles} canWriteProfiles={canWriteProfiles} onOpenProfileEditor={openProfileEditor} />
          </TabsContent>

          <TabsContent value="permissions" className="mt-4">
            {canReadPermissions ? (
              <PermissionsPanel
                permissions={permissions}
                canWritePermissions={canWritePermissions}
                saving={saving}
                onCreate={createPermission}
                onUpdate={updatePermission}
                onDelete={deletePermissionAction}
              />
            ) : (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                Seu perfil não possui a permissão admin:permissions:read para ver o catálogo de permissões.
              </div>
            )}
          </TabsContent>

          <TabsContent value="structure" className="mt-4">
            <PeopleStructurePanel
              peopleStructure={peopleStructure}
              filteredPeople={filteredPeople}
              canWriteUsers={canWriteUsers}
              personSearch={personSearch}
              personStatusFilter={personStatusFilter}
              onPersonSearchChange={setPersonSearch}
              onPersonStatusFilterChange={setPersonStatusFilter}
              onEditPerson={openPersonDraft}
            />
          </TabsContent>

          <TabsContent value="modules" className="mt-4">
            <ModulesPanel
              visibleModuleRows={visibleModuleRows}
              users={users}
              saving={saving}
              canWriteModules={canWriteModules}
              onUpdateModuleVisibility={updateModuleVisibility}
              onAddModuleUserOverride={addModuleUserOverride}
              onRemoveModuleUserOverride={removeModuleUserOverride}
              onOpenModuleSettings={setModuleSettingsDraft}
            />
            {/* Configuração da Visão Geral fica junto da visibilidade de módulos: os dois decidem o que
                cada pessoa encontra ao entrar no ecossistema. */}
            <div className="mt-5">
              <OverviewSettingsPanel onError={setError} onMessage={setMessage} />
            </div>
          </TabsContent>

          <TabsContent value="integrations" className="mt-4">
            <IntegrationsPanel
              ixcSyncSettings={ixcSyncSettings}
              canEditIxcSync={canEditIxcSync}
              saving={saving}
              onSaveIxcSyncSettings={updateIxcSyncSettings}
              onOpenAiGovernance={() => setActiveTab("ai_governance")}
            />
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

          <TabsContent value="audit" className="mt-4">
            <AuditPanelSection canReadAudit={canReadAudit} permissionModuleRows={permissionModuleRows} />
          </TabsContent>
        </Tabs>
      </section>

      {userDraft ? (
        <UserEditorDrawer
          userDraft={userDraft}
          profiles={profiles}
          operationRegionals={operationRegionals}
          saving={saving}
          onChange={updateUserDraft}
          onCancel={() => setUserDraft(null)}
          onSave={saveUserDraft}
          onOpenPermissionOverrides={
            userDraft.id === "new"
              ? undefined
              : () => setPermissionOverridesUser({ id: userDraft.id as number, name: userDraft.name })
          }
        />
      ) : null}

      {permissionOverridesUser ? (
        <UserPermissionOverridesDrawer
          userId={permissionOverridesUser.id}
          userName={permissionOverridesUser.name}
          catalog={permissions}
          canWrite={canWriteUsers}
          onClose={() => setPermissionOverridesUser(null)}
          onChanged={() => void loadAdminData()}
        />
      ) : null}

      {personDraft && peopleStructure ? (
        <PersonEditorDrawer
          personDraft={personDraft}
          peopleStructure={peopleStructure}
          saving={saving}
          canWriteUsers={canWriteUsers}
          onChange={updatePersonDraft}
          onCancel={() => setPersonDraft(null)}
          onSave={savePersonDraft}
        />
      ) : null}

      {profileDraft ? (
        <ProfileEditorDrawer
          profileDraft={profileDraft}
          profiles={profiles}
          canWriteProfiles={canWriteProfiles}
          saving={saving}
          permissionSearch={permissionSearch}
          groupedPermissions={groupedPermissions}
          filteredPermissionGroups={filteredPermissionGroups}
          onChange={updateProfileDraft}
          onPermissionSearchChange={setPermissionSearch}
          onTogglePermission={toggleProfilePermission}
          onSetModulePermissions={setProfileModulePermissions}
          onClose={closeProfileEditor}
          onSave={saveProfileDraft}
          onDelete={deleteProfileAction}
        />
      ) : null}

      {moduleSettingsDraft ? (
        <ModuleSettingsDrawer
          module={moduleSettingsDraft}
          saving={saving}
          onClose={() => setModuleSettingsDraft(null)}
          onSave={(patch) => saveModuleSettings(moduleSettingsDraft.key, patch)}
        />
      ) : null}
    </div>
  );
}
