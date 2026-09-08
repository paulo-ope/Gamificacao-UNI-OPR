"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { useEffect } from "react";

import { NotificationBell } from "@/components/workspace/notification-bell";
import { WorkspaceLogin } from "@/components/workspace/workspace-login";
import { WorkspaceModuleGrid } from "@/components/workspace/module-grid";
import { Button } from "@/components/ui/button";
import { useVisibleModules } from "@/hooks/use-visible-modules";
import { useWorkspaceAuth } from "@/hooks/use-workspace-auth";

/**
 * Ponto de entrada do ecossistema (`/`): login e, depois de autenticar, encaminhamento.
 *
 * A entrada do sistema passou a ser a Visão Geral (decisão do usuário em 2026-09-03) - quem tem
 * `operations:read` cai direto nela, com os módulos no menu lateral. Quem NÃO tem (o caso real de
 * um colaborador, que só usa o Portal) continua vendo a grade de módulos aqui, senão o redirect
 * levaria essa pessoa para uma tela em branco.
 */
export function WorkspaceHome() {
  const router = useRouter();
  const { user, checking, error, login, logout } = useWorkspaceAuth();
  const modules = useVisibleModules(user);
  const goesToOverview = Boolean(user?.permissions.includes("operations:read"));

  useEffect(() => {
    if (goesToOverview) router.replace("/visao-geral");
  }, [goesToOverview, router]);

  if (checking && !user) {
    return (
      <main className="flex min-h-screen items-center justify-center text-sm text-slate-500">
        Carregando UNI Workspace...
      </main>
    );
  }
  if (!user) return <WorkspaceLogin isLoading={checking} error={error} onLogin={login} showPortalLink />;
  if (goesToOverview) {
    return (
      <main className="flex min-h-screen items-center justify-center text-sm text-slate-500">
        Abrindo a Visão Geral...
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-4">
          <div className="flex items-center gap-3">
            <img src="/brand/uni-logo.png" alt="UNI Internet" className="h-8 w-auto" />
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-blue-600">UNI Workspace</p>
              <h1 className="text-base font-semibold text-slate-950">Ecossistema Operacional</h1>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <NotificationBell />
            <Button type="button" variant="ghost" onClick={logout}>
              <LogOut className="h-4 w-4" /> Sair
            </Button>
          </div>
        </div>
      </header>
      <section className="mx-auto max-w-7xl px-5 py-12">
        <p className="text-sm text-slate-500">Olá, {user.name}.</p>
        <h2 className="mt-1 text-3xl font-semibold text-slate-950">Escolha um módulo</h2>
        <div className="mt-8">
          <WorkspaceModuleGrid modules={modules} />
        </div>
        {user.permissions.includes("portal:read_self") ? (
          <p className="mt-8 text-sm text-slate-500">
            Você também tem acesso ao{" "}
            <Link href="/portal" className="font-semibold text-uni-royal hover:underline">
              Portal do Colaborador
            </Link>
            .
          </p>
        ) : null}
      </section>
    </main>
  );
}
