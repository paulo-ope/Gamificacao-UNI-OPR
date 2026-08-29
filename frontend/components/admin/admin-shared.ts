import { Boxes, History, Inbox, LayoutDashboard, Mail, PlugZap, ShieldCheck, UserCog, UserRound, Users } from "lucide-react";

import type { ModuleNavigationItem } from "@/components/workspace/module-navigation-sidebar";
import type { AccessProfile, AdminWorkspaceModule, AuthUser, EcosystemPermission, Permission } from "@/lib/types";

// `workspaceModules` (lib/module-registry.ts) inclui chaves de módulo (ex.: "intelligence") fora
// da união estreita de `WorkspaceVisibleModule["key"]` usada por `AdminWorkspaceModule` - o
// fallback de `visibleModuleRows` em admin/page.tsx mistura os dois formatos quando `adminModules`
// ainda não carregou. `key: string` aqui é só pra refletir isso; nada usa a união estreita.
export type VisibleModuleRow = Omit<AdminWorkspaceModule, "key"> & { key: string };

export type AdminTab =
  | "overview"
  | "internal_accounts"
  | "portal_accounts"
  | "invites"
  | "access_requests"
  | "structure"
  | "profiles"
  | "modules"
  | "integrations"
  | "ai_governance"
  | "audit";

// "structure" precisa manter esse valor exato: `frontend/app/gestao/page.tsx` linka
// `/admin?tab=structure&person=...` de fora deste arquivo.
export const ADMIN_NAV_ITEMS: Array<ModuleNavigationItem<AdminTab>> = [
  { value: "overview", label: "Visão geral", description: "KPIs e pendências", icon: LayoutDashboard },
  { value: "internal_accounts", label: "Contas internas", description: "Acessos sem colaborador vinculado", icon: Users },
  { value: "portal_accounts", label: "Contas do Portal", description: "Acessos vinculados a colaboradores", icon: UserRound },
  { value: "invites", label: "Convites", description: "IXC e convite manual", icon: Mail },
  { value: "access_requests", label: "Solicitações", description: "Pedidos de acesso ao Portal", icon: Inbox },
  { value: "structure", label: "Pessoas", description: "Estrutura e liderança", icon: UserCog },
  { value: "profiles", label: "Perfis", description: "Permissões por função", icon: ShieldCheck },
  { value: "modules", label: "Módulos", description: "Visibilidade por perfil", icon: Boxes },
  { value: "integrations", label: "Integrações", description: "IXC, APIs e IA", icon: PlugZap },
  { value: "audit", label: "Auditoria", description: "Ações sensíveis", icon: History },
];

export const PARAMETER_MODULE_LINKS = [
  { module: "Gamificação Operacional", owner: "Pontuação, penalidades, fechamento e pagamento", permissionArea: "Gamificação", path: "/gamificacao" },
  { module: "Operação Analítica", owner: "Modelos de equipe, assuntos, SLA e filtros globais", permissionArea: "Operação", path: "/operacao" },
  { module: "Agendamento", owner: "Metas diárias, expediente, sincronização e equipe", permissionArea: "Agendamento", path: "/agendamento" },
  { module: "SGP Suporte", owner: "Atendimentos, dimensões e sincronização com o OPA Suite", permissionArea: "Suporte", path: "/suporte" },
  { module: "Gestão Integrada", owner: "Estrutura, motivos, prazos, justificativas e revisão", permissionArea: "Gestão", path: "/gestao" },
  { module: "UNI Intelligence", owner: "Monitores, alertas, conteúdo e publicação no cockpit", permissionArea: "Inteligência", path: "/intelligence" },
] as const;

export const LEGACY_ROLE_BY_PROFILE: Record<string, AuthUser["role"]> = {
  "Admin Ecossistema": "admin",
  "Operador Operacional": "operator",
  "Leitor Operacional": "viewer",
  "Colaborador Portal": "collaborator",
  "Gestor Regional Portal": "regional_manager_viewer",
};

export const STRUCTURE_TYPES = ["Campo", "Agendamento", "Suporte interno", "Supervisor", "Gerente regional", "Matriz"] as const;

export const EMPLOYEE_TYPE_LABELS: Record<string, string> = {
  field_technician: "Técnico de campo",
  scheduling_operator: "Agendamento",
  internal_support: "Suporte interno",
  supervisor: "Supervisor",
  regional_manager: "Gerente regional",
  headquarters: "Matriz",
  administrative: "Administrativo",
  other: "Outro",
};

export const TEAM_TYPE_LABELS: Record<string, string> = {
  field: "Campo",
  scheduling: "Agendamento",
  internal_support: "Suporte interno",
  regional: "Regional",
  administrative: "Administrativo",
  headquarters: "Matriz",
  other: "Outro",
};

export const STRUCTURE_STATUS_LABELS: Record<string, string> = {
  pending_review: "Pendente",
  validated: "Validado",
  needs_fix: "Corrigir",
  outside_operation: "Fora da operação",
  inactive: "Inativo",
};

export const INVITE_STATUS_LABELS: Record<string, string> = {
  pending: "Pendente",
  accepted: "Aceito",
  revoked: "Revogado",
  expired: "Expirado",
};

export const INVITE_STATUS_BADGE: Record<string, string> = {
  pending: "bg-blue-50 text-blue-700",
  accepted: "bg-emerald-50 text-emerald-700",
  revoked: "bg-slate-100 text-slate-600",
  expired: "bg-amber-50 text-amber-700",
};

export const ACCESS_REQUEST_STATUS_LABELS: Record<string, string> = {
  pending: "Pendente",
  approved: "Aprovado",
  rejected: "Rejeitado",
};

export const ACCESS_REQUEST_STATUS_BADGE: Record<string, string> = {
  pending: "bg-blue-50 text-blue-700",
  approved: "bg-emerald-50 text-emerald-700",
  rejected: "bg-rose-50 text-rose-700",
};

export type UserDraft = {
  id: number | "new";
  name: string;
  email: string;
  password: string;
  active: boolean;
  access_profile_ids: number[];
  managed_regionals: string[];
};

export type ProfileDraft = {
  id: number | "new";
  name: string;
  description: string;
  active: boolean;
  permission_keys: Permission[];
};

export type PersonStructureDraft = {
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

export function blankUserDraft(): UserDraft {
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

export function blankProfileDraft(): ProfileDraft {
  return {
    id: "new",
    name: "",
    description: "",
    active: true,
    permission_keys: [],
  };
}

export function profileNames(user: AuthUser, profiles: AccessProfile[]) {
  const names = user.access_profile_ids
    .map((id) => profiles.find((profile) => profile.id === id)?.name)
    .filter(Boolean);
  return names.length ? names.join(", ") : user.role;
}

export function permissionGroups(permissions: EcosystemPermission[]) {
  return permissions.reduce<Record<string, EcosystemPermission[]>>((groups, permission) => {
    groups[permission.module] = [...(groups[permission.module] || []), permission];
    return groups;
  }, {});
}
