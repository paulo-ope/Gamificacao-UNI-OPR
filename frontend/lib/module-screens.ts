import { PlugZap, Tv, type LucideIcon } from "lucide-react";

import { GAMIFICATION_NAV_ITEMS } from "@/components/gamification/gamification-nav-items";
import { MANAGEMENT_NAV_ITEMS } from "@/components/management/management-module-sidebar";
import { OPERATION_NAV_ITEMS } from "@/components/operations/operations-module-sidebar";
import { SCHEDULING_NAV_ITEMS } from "@/components/scheduling/scheduling-module-sidebar";
import { ADMIN_NAV_ITEMS } from "@/components/admin/admin-shared";
import { LOCALIZA_NAV_ITEMS } from "@/components/localiza/localiza-nav-items";
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
  /** Rota própria, quando a tela não é uma aba do módulo (ex.: a TV, que é tela cheia). */
  path?: string;
  /** Abre em outra aba do navegador - para telas de tela cheia, sem a barra lateral. */
  opensInNewTab?: boolean;
  /**
   * Sub-aba: `value` da aba do módulo em que ela vive. O link vira `?tab=<parentValue>&sub=<value>`
   * e a página do módulo precisa ler `sub` (hoje só a Gamificação).
   */
  parentValue?: string;
  /** Rótulo da aba-mãe, para o menu global mostrar "Módulo · Aba" no resultado. */
  parentLabel?: string;
  /** Só a busca global lista esta tela - o menu lateral não (ex.: sub-abas, que já vivem dentro da aba). */
  searchOnly?: boolean;
};

// A TV do Suporte é uma rota própria (`/suporte/tv`), sem a barra lateral: por isso não entra em
// `OPA_NAV_ITEMS` (que a página do módulo usa como abas) - só no menu global.
const SUPPORT_TV_SCREEN: ModuleScreen = {
  value: "tv",
  label: "TV Suporte Interno",
  description: "Painel para televisão",
  icon: Tv,
  requiredPermissions: [],
  path: "/suporte/tv",
  opensInNewTab: true,
};

// A Governança de IA é uma aba da Administração (`?tab=ai_governance`) que não está em
// `ADMIN_NAV_ITEMS`: só se chega nela por um botão dentro de Integrações. Entra aqui para a busca
// global também encontrá-la, mas fica fora do menu lateral (`searchOnly`) - o menu não muda.
const ADMIN_AI_GOVERNANCE_SCREEN: ModuleScreen = {
  value: "ai_governance",
  label: "Governança de IA",
  description: "Endpoints, campos, perfis e tokens da IA",
  icon: PlugZap,
  requiredPermissions: ["admin:ai_governance:read"],
  searchOnly: true,
};

type ScreenPermissionMap =Record<string, Permission[]>;

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
  matrix: ["operations:view_sla"],
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
  exclusions: ["management:admin"],
  audit: ["management:audit_structure:read"],
};

// Sub-abas da Gamificação: vivem dentro de uma aba (`Tabs` aninhado em `app/gamificacao/page.tsx`) e
// por isso não estão em `GAMIFICATION_NAV_ITEMS`. As permissões espelham `visibleTabs` e o
// `can("users:manage")` do próprio `<TabsTrigger>` da página.
function gamificationSubScreen(
  parentValue: string,
  parentLabel: string,
  value: string,
  label: string,
  description: string,
  icon: LucideIcon,
  requiredPermissions: Permission[] = [],
): ModuleScreen {
  return { value, label, description, icon, requiredPermissions, parentValue, parentLabel, searchOnly: true };
}

const GAMIFICATION_CONFIG_PERMISSIONS: Permission[] = ["scoring:write"];
const GAMIFICATION_PENDING_PERMISSIONS: Permission[] = ["orders:import", "scoring:write"];

const ADMIN_SCREEN_PERMISSIONS: ScreenPermissionMap = {
  profiles: ["admin:roles:read"],
  permissions: ["admin:permissions:read"],
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
    return [...withPermissions(OPERATION_NAV_ITEMS, OPERATION_SCREEN_PERMISSIONS), ...operationConfigSubScreens(icon)];
  }
  if (moduleKey === "gamification") {
    return [
      ...withPermissions(GAMIFICATION_NAV_ITEMS, GAMIFICATION_SCREEN_PERMISSIONS),
      ...gamificationSubScreens(icon),
    ];
  }
  if (moduleKey === "scheduling") {
    return withPermissions(SCHEDULING_NAV_ITEMS, {});
  }
  if (moduleKey === "support") {
    // Só as abas ativas: as "Planejado" do módulo existem na lista mas não têm tela.
    return [...withPermissions(OPA_NAV_ITEMS, {}, ACTIVE_OPA_TABS), SUPPORT_TV_SCREEN];
  }
  if (moduleKey === "management") {
    return withPermissions(MANAGEMENT_NAV_ITEMS, MANAGEMENT_SCREEN_PERMISSIONS);
  }
  if (moduleKey === "admin") {
    // "Pessoas" saiu do menu lateral (pedido do usuário, 2026-10-09), mas a aba continua: a Gestão
    // Integrada linka `/admin?tab=structure&person=` e a busca global por pessoas abre ela.
    const adminScreens = withPermissions(ADMIN_NAV_ITEMS, ADMIN_SCREEN_PERMISSIONS).map((screen) =>
      screen.value === "structure" ? { ...screen, searchOnly: true } : screen,
    );
    return [...adminScreens, ADMIN_AI_GOVERNANCE_SCREEN];
  }
  if (moduleKey === "localiza") {
    // As duas telas exigem só `localiza:read` (a permissão do próprio módulo): quem entra no
    // módulo vê a lista e o mapa; `localiza:manage` controla ações dentro delas, não o acesso.
    return withPermissions(LOCALIZA_NAV_ITEMS, {});
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

// Seções da aba Config da Operação (`OperationsTeamConfiguration`). As permissões espelham o
// `.filter` dos botões de seção do próprio componente.
function operationConfigSubScreens(icon: LucideIcon): ModuleScreen[] {
  const sub = (
    value: string,
    label: string,
    description: string,
    requiredPermissions: Permission[],
  ): ModuleScreen => ({
    value, label, description, icon, requiredPermissions, parentValue: "teams", parentLabel: "Config", searchOnly: true,
  });
  const models: Permission[] = ["operations:manage_team_models"];
  return [
    sub("models", "Modelos, metas e jornadas", "Metas por dia, mês e horário operacional", models),
    sub("members", "Colaboradores e vínculos", "Modelo aplicado a cada responsável", [...models, "operations:manage_own_team_members"]),
    sub("subjects", "Tipos gerais e assuntos", "Catálogo e fila de classificação", ["operations:manage_subjects"]),
    sub("sync", "Sincronização IXC", "Intervalo automático e setores importados", ["operations:sync_ixc"]),
    sub("capacity", "Capacidade por filial", "Faixas Boa, Ótima e Excelente por filial", models),
    sub("sla-groups", "SLA por tecnologia", "Grupos e assuntos dos gauges da Visão Geral", ["operations:manage_sla_groups"]),
  ];
}

function gamificationSubScreens(icon: LucideIcon): ModuleScreen[] {
  const ranking = ["ranking", "Ranking"] as const;
  const pending = ["pending", "Pendências"] as const;
  const config = ["config", "Configuração"] as const;
  const audit = ["audit", "Auditoria"] as const;
  return [
    gamificationSubScreen(...ranking, "collaborators", "Ranking de colaboradores", "Resultado final por colaborador", icon),
    gamificationSubScreen(...ranking, "leaders", "Ranking de liderança", "Resultados da liderança", icon),
    gamificationSubScreen(...pending, "subjects", "Assuntos pendentes", "Assuntos sem mapeamento", icon, GAMIFICATION_PENDING_PERMISSIONS),
    gamificationSubScreen(...pending, "diagnoses", "Diagnósticos pendentes", "Diagnósticos sem mapeamento", icon, GAMIFICATION_PENDING_PERMISSIONS),
    gamificationSubScreen(...config, "rules", "Regras da gamificação", "Pontuação e regras", icon, GAMIFICATION_CONFIG_PERMISSIONS),
    gamificationSubScreen(...config, "collaborators", "Colaboradores e filiais", "Cadastro e filiais", icon, GAMIFICATION_CONFIG_PERMISSIONS),
    gamificationSubScreen(...config, "leadership", "Liderança e multiplicadores", "Perfis de liderança", icon, GAMIFICATION_CONFIG_PERMISSIONS),
    gamificationSubScreen(...config, "users", "Usuários da gamificação", "Contas com acesso", icon, ["users:manage"]),
    gamificationSubScreen(...audit, "scoring", "Auditoria: pontuação de O.S", "Como cada O.S foi pontuada", icon),
    gamificationSubScreen(...audit, "trail", "Auditoria: trilha de ações", "Registro de ações", icon),
  ];
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
  if (screen.path) return screen.path;
  if (screen.parentValue) {
    return `${webPath}?tab=${encodeURIComponent(screen.parentValue)}&sub=${encodeURIComponent(screen.value)}`;
  }
  return `${webPath}?tab=${encodeURIComponent(screen.value)}`;
}
