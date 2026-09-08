import {
  BarChart3,
  BriefcaseBusiness,
  CalendarClock,
  Gauge,
  Headphones,
  LayoutGrid,
  Radar,
  ShieldCheck,
  Trophy,
  type LucideIcon,
} from "lucide-react";

import type { Permission } from "@/lib/types";

// Ícone por módulo do ecossistema. Tipado como `Record<string, ...>` de propósito: a chave vem do
// backend (`/workspace/modules`) e um módulo novo lá não deve quebrar a navegação daqui antes de
// alguém escolher um ícone - cai no fallback.
const MODULE_ICONS: Record<string, LucideIcon> = {
  gamification: Trophy,
  operations: BarChart3,
  scheduling: CalendarClock,
  support: Headphones,
  management: BriefcaseBusiness,
  admin: ShieldCheck,
  intelligence: Radar,
};

export function moduleIcon(key: string): LucideIcon {
  return MODULE_ICONS[key] ?? LayoutGrid;
}

/**
 * Telas do ecossistema - o nível de navegação que não é "módulo".
 *
 * Existe para a transição de "pular de módulo em módulo" para "pular de tela em tela": a Visão
 * Geral é a primeira tela transversal (lê Operação + SGP + Gamificação) e por isso não pertence a
 * nenhum módulo. `requiredPermission: null` significa "qualquer usuário autenticado".
 *
 * A tela "Módulos" (grade de cards, `/modulos`) saiu daqui em 2026-09-03: com o submenu de cada
 * módulo já disponível na própria barra lateral, ela virou uma segunda forma de chegar ao mesmo
 * lugar. A rota `/modulos` continua existindo (é para onde `/` manda quem não tem
 * `operations:read`, ver `workspace-home.tsx`) - só não tem mais entrada própria aqui.
 */
export type WorkspaceScreen = {
  key: "overview";
  name: string;
  description: string;
  path: string;
  icon: LucideIcon;
  requiredPermission: Permission | null;
};

export const workspaceScreens: readonly WorkspaceScreen[] = [
  {
    key: "overview",
    name: "Visão Geral",
    description: "Macrovisão da operação",
    path: "/visao-geral",
    icon: Gauge,
    // A espinha dorsal da tela são as O.S.: sem `operations:read` ela abriria vazia.
    requiredPermission: "operations:read",
  },
];

export function visibleWorkspaceScreens(permissions: readonly string[]) {
  return workspaceScreens.filter(
    (screen) => screen.requiredPermission === null || permissions.includes(screen.requiredPermission),
  );
}
