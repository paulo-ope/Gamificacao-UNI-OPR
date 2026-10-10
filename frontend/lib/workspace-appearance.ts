/**
 * Preferência de aparência do Workspace guardada NO NAVEGADOR (decisão do usuário, 2026-10-10): cada
 * navegador lembra o tema da barra lateral escolhido na aba "Personalização" da Administração. Não há
 * backend nem preferência por conta - quem abrir o Workspace em outro navegador volta ao tema padrão.
 */

export type SidebarTheme = "light" | "dark";

export const SIDEBAR_THEME_STORAGE_KEY = "uni_workspace_sidebar_theme";
/** Avisa a mesma aba que o tema mudou (o evento `storage` nativo só dispara nas OUTRAS abas). */
export const SIDEBAR_THEME_EVENT = "uni-workspace-sidebar-theme-change";
export const DEFAULT_SIDEBAR_THEME: SidebarTheme = "light";

type ThemeStorage = Pick<Storage, "getItem" | "setItem">;

// Se o navegador bloquear o armazenamento (aba anônima, política corporativa), a escolha ainda vale
// até a página ser fechada, em vez de o botão simplesmente "não pegar".
let memoryTheme: SidebarTheme | null = null;

export function parseSidebarTheme(value: unknown): SidebarTheme {
  return value === "dark" || value === "light" ? value : DEFAULT_SIDEBAR_THEME;
}

function browserStorage(): ThemeStorage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function readSidebarTheme(storage: ThemeStorage | null = browserStorage()): SidebarTheme {
  if (storage) {
    try {
      const stored = storage.getItem(SIDEBAR_THEME_STORAGE_KEY);
      if (stored !== null) return parseSidebarTheme(stored);
    } catch {
      // Armazenamento indisponível: cai para a escolha em memória.
    }
  }
  return memoryTheme ?? DEFAULT_SIDEBAR_THEME;
}

export function saveSidebarTheme(theme: SidebarTheme, storage: ThemeStorage | null = browserStorage()): void {
  memoryTheme = theme;
  if (storage) {
    try {
      storage.setItem(SIDEBAR_THEME_STORAGE_KEY, theme);
    } catch {
      // Preferência é conveniência: o tema segue valendo em memória.
    }
  }
  if (typeof window !== "undefined") window.dispatchEvent(new Event(SIDEBAR_THEME_EVENT));
}

/** Só para testes: zera a escolha em memória entre um caso e outro. */
export function resetSidebarThemeMemory(): void {
  memoryTheme = null;
}
