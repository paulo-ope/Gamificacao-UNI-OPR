import type { Permission } from "@/lib/types";

export type WorkspaceModuleStatus = "active" | "planned" | "disabled";

export type WorkspaceModule = {
  key: "gamification" | "operations" | "admin";
  name: string;
  description: string;
  webPath: string;
  apiPrefix: string;
  requiredPermission: Permission;
  status: WorkspaceModuleStatus;
};

/**
 * Registro de descoberta visual. A autorização efetiva continua no backend.
 * Ele não é conectado à navegação atual nesta etapa para não mudar o fluxo da
 * Gamificação antes de o módulo Operação possuir rota e permissões próprias.
 */
export const workspaceModules: readonly WorkspaceModule[] = [
  {
    key: "gamification",
    name: "Gamificação Operacional",
    description: "Remuneração variável, fechamento e auditoria de produtividade.",
    webPath: "/gamificacao",
    apiPrefix: "/api",
    requiredPermission: "dashboard:read",
    status: "active"
  },
  {
    key: "operations",
    name: "Operação Analítica",
    description: "Análise de O.S., SLA, backlog, garantia e produtividade operacional.",
    webPath: "/operacao",
    apiPrefix: "/api/operations",
    requiredPermission: "operations:read",
    status: "active"
  },
  {
    key: "admin",
    name: "Administração",
    description: "Usuários, perfis de acesso, permissões e escopos do ecossistema.",
    webPath: "/admin",
    apiPrefix: "/api/admin",
    requiredPermission: "admin:users:read",
    status: "active"
  }
];

export function getWorkspaceModule(key: WorkspaceModule["key"]) {
  return workspaceModules.find((module) => module.key === key);
}
