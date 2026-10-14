"use client";

import { Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useSidebarTheme } from "@/hooks/use-sidebar-theme";
import { saveSidebarTheme } from "@/lib/workspace-appearance";

/**
 * Alterna o tema claro/escuro do Workspace, ao lado de "Buscar telas" no cabeçalho (pedido do usuário,
 * 2026-10-14, no lugar da aba Personalização da Administração, que foi removida). A escolha vale só para este
 * navegador (ver `lib/workspace-appearance.ts`) e hoje muda a barra lateral, que é a única parte do
 * Workspace com tema escuro.
 */
export function ThemeToggle() {
  const theme = useSidebarTheme();
  const next = theme === "dark" ? "light" : "dark";
  const label = next === "dark" ? "Mudar para o tema escuro" : "Mudar para o tema claro";
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      className="h-9 px-2.5"
      aria-label={label}
      title={label}
      onClick={() => saveSidebarTheme(next)}
    >
      {theme === "dark" ? <Sun className="h-4 w-4" aria-hidden="true" /> : <Moon className="h-4 w-4" aria-hidden="true" />}
    </Button>
  );
}
