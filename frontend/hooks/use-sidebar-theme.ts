"use client";

import { useSyncExternalStore } from "react";

import {
  DEFAULT_SIDEBAR_THEME,
  SIDEBAR_THEME_EVENT,
  readSidebarTheme,
  type SidebarTheme,
} from "@/lib/workspace-appearance";

function subscribe(onChange: () => void) {
  // `storage` cobre outras abas do mesmo navegador; o evento próprio cobre a aba atual.
  window.addEventListener("storage", onChange);
  window.addEventListener(SIDEBAR_THEME_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(SIDEBAR_THEME_EVENT, onChange);
  };
}

/** Tema da barra lateral escolhido neste navegador. No servidor (e na hidratação) é sempre o padrão,
 *  então não há divergência de HTML; a barra só aparece depois do login, já no cliente. */
export function useSidebarTheme(): SidebarTheme {
  return useSyncExternalStore(subscribe, () => readSidebarTheme(), () => DEFAULT_SIDEBAR_THEME);
}
