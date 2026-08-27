"use client";

import { LogOut } from "lucide-react";
import type { ReactNode } from "react";

import { NotificationBell } from "@/components/workspace/notification-bell";
import { WorkspaceLogin } from "@/components/workspace/workspace-login";
import { WorkspaceShellProvider } from "@/components/workspace/workspace-shell-context";
import { WorkspaceSidebar } from "@/components/workspace/workspace-sidebar";
import { Button } from "@/components/ui/button";
import { useWorkspaceAuth } from "@/hooks/use-workspace-auth";

// App shell único (sidebar fixa + header) pras páginas de módulo migradas - substitui o header
// duplicado que cada módulo desenhava por conta própria. `useWorkspaceAuth()` roda só AQUI, uma
// vez por navegação, e o resultado desce via contexto (`useWorkspaceShell`) pras páginas filhas -
// achado da modernização de 2026-08-27: antes cada página chamava o hook de novo, duplicando o
// GET /auth/me a cada módulo aberto.
export default function ShellLayout({ children }: { children: ReactNode }) {
  const { user, checking, error, login, logout } = useWorkspaceAuth();

  if (checking && !user) {
    return (
      <main className="flex min-h-screen items-center justify-center text-sm text-slate-500">
        Carregando UNI Workspace...
      </main>
    );
  }
  if (!user) return <WorkspaceLogin isLoading={checking} error={error} onLogin={login} />;

  return (
    <WorkspaceShellProvider value={{ user, logout }}>
      <div className="flex min-h-screen bg-slate-50">
        <WorkspaceSidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 flex items-center justify-end gap-1 border-b border-slate-200 bg-white/95 px-5 py-2.5 backdrop-blur">
            <NotificationBell />
            <Button type="button" variant="ghost" onClick={logout}>
              <LogOut className="h-4 w-4" /> Sair
            </Button>
          </header>
          <main className="min-w-0 flex-1">{children}</main>
        </div>
      </div>
    </WorkspaceShellProvider>
  );
}
