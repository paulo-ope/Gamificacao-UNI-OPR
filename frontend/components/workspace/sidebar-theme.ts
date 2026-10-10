import { createContext, useContext } from "react";

import type { SidebarTheme } from "@/lib/workspace-appearance";

/** Classes de cada peça da barra lateral (e do drawer do celular) por tema. A marcação é uma só
 *  (`app-shell.tsx`); só as cores mudam. */
export type SidebarStyles = {
  aside: string;
  brand: string;
  brandName: string;
  brandSub: string;
  footer: string;
  avatar: string;
  userName: string;
  userEmail: string;
  iconButton: string;
  submenu: string;
  screenLinkSelected: string;
  screenLinkIdle: string;
  groupLabel: string;
  divider: string;
  itemSelected: string;
  itemIdle: string;
  iconBoxSelected: string;
  iconBoxIdle: string;
  descriptionSelected: string;
  descriptionIdle: string;
  scroll: string;
  sheet: string;
  sheetHeader: string;
  sheetTitle: string;
  sheetDescription: string;
};

export const SIDEBAR_STYLES: Record<SidebarTheme, SidebarStyles> = {
  // Igual à tela de acesso: branca, tinta azul-marinho, item ativo em azul-névoa com filete turquesa.
  light: {
    aside: "border-slate-200 bg-white text-slate-700",
    brand: "border-slate-200",
    brandName: "text-slate-900",
    brandSub: "text-slate-500",
    footer: "border-slate-200",
    avatar: "bg-uni-royal/10 text-uni-royal",
    userName: "text-slate-900",
    userEmail: "text-slate-500",
    iconButton: "text-slate-500 hover:bg-slate-100 hover:text-slate-900",
    submenu: "border-slate-200",
    screenLinkSelected: "bg-uni-mist font-semibold text-uni-impact ring-1 ring-inset ring-uni-royal/15",
    screenLinkIdle: "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
    groupLabel: "text-slate-500",
    divider: "border-slate-200",
    itemSelected:
      "bg-uni-mist text-uni-impact ring-1 ring-inset ring-uni-royal/15 before:absolute before:bottom-2 before:left-0 before:top-2 before:w-[3px] before:rounded-full before:bg-uni-turquoise before:content-['']",
    itemIdle: "text-slate-700 hover:bg-slate-100 hover:text-slate-900",
    iconBoxSelected: "bg-uni-royal text-white shadow-sm",
    iconBoxIdle: "bg-slate-100 text-slate-500",
    descriptionSelected: "text-slate-600",
    descriptionIdle: "text-slate-500",
    scroll: "sidebar-scroll",
    sheet: "border-slate-200 bg-white text-slate-700 [&>button]:text-slate-500 [&>button:hover]:bg-slate-100",
    sheetHeader: "border-slate-200",
    sheetTitle: "text-slate-900",
    sheetDescription: "text-slate-500",
  },
  // Como era antes da paleta nova (azul-marinho #101e38). Cores em hex explícito (os cinzas do Tailwind
  // foram remapeados para a tinta da tela de acesso) para a barra escura continuar idêntica à antiga.
  dark: {
    aside: "border-[#1e293b] bg-[#101e38] text-[#f1f5f9]",
    brand: "border-white/10",
    brandName: "text-white",
    brandSub: "text-[#cbd5e1]",
    footer: "border-white/10",
    avatar: "bg-white/10 text-white",
    userName: "text-[#f1f5f9]",
    userEmail: "text-[#94a3b8]",
    iconButton: "text-[#94a3b8] hover:bg-white/10 hover:text-white",
    submenu: "border-white/15",
    screenLinkSelected: "bg-white/10 font-semibold text-white ring-1 ring-inset ring-white/10",
    screenLinkIdle: "text-[#cbd5e1] hover:bg-white/10 hover:text-white",
    groupLabel: "text-[#94a3b8]",
    divider: "border-white/10",
    itemSelected: "bg-white/10 text-white ring-1 ring-inset ring-white/10",
    itemIdle: "text-[#cbd5e1] hover:bg-white/5 hover:text-white",
    iconBoxSelected: "bg-uni-royal text-white shadow-sm",
    iconBoxIdle: "bg-white/5 text-[#94a3b8]",
    descriptionSelected: "text-blue-200",
    descriptionIdle: "text-[#94a3b8]",
    scroll: "sidebar-scroll sidebar-scroll-dark",
    sheet: "border-[#1e293b] bg-[#101e38] text-[#f1f5f9] [&>button]:text-[#cbd5e1] [&>button:hover]:bg-white/10",
    sheetHeader: "border-white/10",
    sheetTitle: "text-white",
    sheetDescription: "text-[#94a3b8]",
  },
};

export const SidebarStylesContext = createContext<SidebarStyles>(SIDEBAR_STYLES.light);

export function useSidebarStyles(): SidebarStyles {
  return useContext(SidebarStylesContext);
}
