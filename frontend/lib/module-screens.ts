import type { LucideIcon } from "lucide-react";

import { GAMIFICATION_NAV_ITEMS } from "@/components/gamification/gamification-nav-items";
import { MANAGEMENT_NAV_ITEMS } from "@/components/management/management-module-sidebar";
import { OPERATION_NAV_ITEMS } from "@/components/operations/operations-module-sidebar";
import { SCHEDULING_NAV_ITEMS } from "@/components/scheduling/scheduling-module-sidebar";
import { ADMIN_NAV_ITEMS } from "@/components/admin/admin-shared";
import { OPA_NAV_ITEMS, ACTIVE_OPA_TABS } from "@/app/suporte/_components/opa-module-components";
import type { Permission } from "@/lib/types";
import type { WorkspaceModule } from "@/lib/module-registry";

/**
 * Catálogo das telas internas de cada módulo, para o menu lateral do ecossistema poder abrir
 * qualquer lugar direto da Visão Geral, sem entrar no módulo e caçar a aba lá dentro.
 *
 * Os rótulos, descrições e ícones vêm das MESMAS listas que cada módulo já usa no próprio menu
 * (`OPERATION_NAV_ITEMS`, `OPA_NAV_ITEMS`, `ADMIN_NAV_ITEMS`...), importadas aqui - manter uma
 * segunda cópia dos nomes garantiria divergência na primeira vez que alguém renomeasse uma aba.
 *
 * O que este arquivo acrescenta é `requiredPermissions`: quais permissões liberam cada tela, para
 * o menu global não oferecer um destino que o módulo vai recusar. É "qualquer uma da lista";
 * lista vazia significa "basta a permissão do próprio módulo".
 *
 * O link é `<rota do módulo>?tab=<valor>`. Essa convenção já existia no projeto (a Gestão
 * Integrada linka `/admin?tab=structure&person=...`) e cada página lê o parâmetro na montagem.
 */
export type ModuleScreen = {
  /** Valor da aba dentro do módulo - vai na URL como `?tab=`. */
  value: string;
  label: string;
  description: string;
  icon: LucideIcon;
  /** Qualquer uma destas permissões libera a tela. Vazio = só a permissão do módulo. */
  requiredPermissions: Permission[];
};

type ScreenPermissionMap = Record<string, Permission[]>;

function withPermissions(
  items: ReadonlyArray<{ value: string; label: string; description: string; icon: LucideIcon }>,
  permissions: ScreenPermissionMap,
  only?: readonly string[],
): ModuleScreen[] {
  return items
    .filter((item) => !only || only.includes(item.value))
    .map((item) => ({
      value: item.value,
      label: item.label,
      description: item.description,
      icon: item.icon,
      requiredPermissions: permissions[item.value] ?? [],
    }));
}

// Espelha `visibleTabs` em `app/operacao/page.tsx` - se uma aba nova entrar lá com permissão
// própria, ela precisa aparecer aqui também, senão o menu global oferece um destino que o módulo
// descarta (o módulo cai na aba padrão, não quebra, mas confunde).
const OPERATION_SCREEN_PERMISSIONS: ScreenPermissionMap = {
  openings: ["operations:view_openings"],
  sla: ["operations:view_sla"],
  garantias: ["operations:view_warranty"],
  calendar: ["operations:view_calendar"],
  progress: ["operations:view_backlog"],
  details: ["operations:view_order_details"],
  teams: [
    "operations:manage_team_models",
    "operations:manage_own_team_members",
    "operations:manage_subjects",
    "operations:sync_ixc",
  ],
};

// Espelha `visibleTabs` em `app/gamificacao/page.tsx`.
const GAMIFICATION_SCREEN_PERMISSIONS: ScreenPermissionMap = {
  pending: ["orders:import", "scoring:write"],
  config: ["scoring:write"],
};

// Espelha `canAdminReasons`/`canAudit` em `app/gestao/page.tsx`.
const MANAGEMENT_SCREEN_PERMISSIONS: ScreenPermissionMap = {
  reasons: ["management:admin"],
  audit: ["management:audit_structure:read"],
};

const ADMIN_SCREEN_PERMISSIONS: ScreenPermissionMap = {
  profiles: ["admin:roles:read"],
  modules: ["admin:modules:read"],
  audit: ["admin:audit:read"],
};

const INTELLIGENCE_SCREEN_PERMISSIONS: ScreenPermissionMap = {
  publicacoes: ["intelligence:publish"],
  profiles: ["intelligence:manage"],
  monitores: ["intelligence:manage"],
  regras: ["intelligence:manage"],
};

// O UNI Intelligence é o único módulo sem lista de navegação própria - as abas estão escritas
// direto no `<Tabs>` da página. Enquanto for assim, os rótulos vivem aqui; se o módulo ganhar um
// menu lateral como os outros, esta lista deve passar a importar dele.
const INTELLIGENCE_SCREENS: Array<{ value: string; label: string; description: string }> = [
  { value: "cockpit", label: "Cockpit", description: "Painel operacional publicado" },
  { value: "alertas", label: "Alertas", description: "Detecções e ciclo de vida" },
  { value: "publicacoes", label: "Publicações", description: "Conteúdo enviado às TVs" },
  { value: "profiles", label: "Perfis de painel", description: "Escopo e widgets do cockpit" },
  { value: "monitores", label: "Monitores", description: "Execuções do motor" },
  { value: "regras", label: "Regras de alerta", description: "Limiares e severidade" },
];

export function moduleScreens(moduleKey: WorkspaceModule["key"], icon: LucideIcon): ModuleScreen[] {
  if (moduleKey === "operations") {
    return withPermissions(OPERATION_NAV_ITEMS, OPERATION_SCREEN_PERMISSIONS);
  }
  if (moduleKey === "gamification") {
    return withPermissions(GAMIFICATION_NAV_ITEMS, GAMIFICATION_SCREEN_PERMISSIONS);
  }
  if (moduleKey === "scheduling") {
    return withPermissions(SCHEDULING_NAV_ITEMS, {});
  }
  if (moduleKey === "support") {
    // Só as abas ativas: as "Planejado" do módulo existem na lista mas não têm tela.
    return withPermissions(OPA_NAV_ITEMS, {}, ACTIVE_OPA_TABS);
  }
  if (moduleKey === "management") {
    return withPermissions(MANAGEMENT_NAV_ITEMS, MANAGEMENT_SCREEN_PERMISSIONS);
  }
  if (moduleKey === "admin") {
    return withPermissions(ADMIN_NAV_ITEMS, ADMIN_SCREEN_PERMISSIONS);
  }
  if (moduleKey === "intelligence") {
    return INTELLIGENCE_SCREENS.map((screen) => ({
      ...screen,
      icon,
      requiredPermissions: INTELLIGENCE_SCREEN_PERMISSIONS[screen.value] ?? [],
    }));
  }
  return [];
}

export function visibleModuleScreens(
  moduleKey: WorkspaceModule["key"],
  icon: LucideIcon,
  permissions: readonly string[],
): ModuleScreen[] {
  return moduleScreens(moduleKey, icon).filter(
    (screen) =>
      screen.requiredPermissions.length === 0 ||
      screen.requiredPermissions.some((permission) => permissions.includes(permission)),
  );
}

export function moduleScreenHref(webPath: string, screen: ModuleScreen) {
  return `${webPath}?tab=${encodeURIComponent(screen.value)}`;
}
