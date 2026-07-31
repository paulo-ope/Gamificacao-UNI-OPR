"use client";

import Link from "next/link";
import { BarChart3, BriefcaseBusiness, CalendarClock, LogOut, ShieldCheck, Trophy } from "lucide-react";
import { useEffect, useState } from "react";

import { WorkspaceLogin } from "@/components/workspace/workspace-login";
import { Button } from "@/components/ui/button";
import { useWorkspaceAuth } from "@/hooks/use-workspace-auth";
import { api } from "@/lib/api";
import { workspaceModules } from "@/lib/module-registry";
import type { WorkspaceVisibleModule } from "@/lib/types";


const icons = { gamification: Trophy, operations: BarChart3, scheduling: CalendarClock, management: BriefcaseBusiness, admin: ShieldCheck };

export function WorkspaceHome() {
  const { user, checking, error, login, logout } = useWorkspaceAuth();
  const [visibleModules, setVisibleModules] = useState<WorkspaceVisibleModule[] | null>(null);

  useEffect(() => {
    if (!user) return;
    api.workspaceModules()
      .then(setVisibleModules)
      .catch(() => setVisibleModules(null));
  }, [user]);

  if (checking && !user) {
    return <main className="flex min-h-screen items-center justify-center text-sm text-slate-500">Carregando UNI Workspace...</main>;
  }
  if (!user) return <WorkspaceLogin isLoading={checking} error={error} onLogin={login} />;

  const fallbackModules = workspaceModules
    .filter((module) => module.status === "active" && user.permissions.includes(module.requiredPermission))
    .map((module) => ({
      key: module.key,
      name: module.name,
      description: module.description,
      web_path: module.webPath,
      api_prefix: module.apiPrefix,
      required_permission: module.requiredPermission,
      status: module.status,
    }));
  const modules = visibleModules ?? fallbackModules;

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
          <Button type="button" variant="ghost" onClick={logout}><LogOut className="h-4 w-4" /> Sair</Button>
        </div>
      </header>
      <section className="mx-auto max-w-7xl px-5 py-12">
        <p className="text-sm text-slate-500">Olá, {user.name}.</p>
        <h2 className="mt-1 text-3xl font-semibold text-slate-950">Escolha um módulo</h2>
        <div className="mt-8 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {modules.map((module) => {
            const Icon = icons[module.key];
            return (
              <Link key={module.key} href={module.web_path} className="group rounded-3xl border border-slate-200 bg-white p-6 shadow-sm transition hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-lg">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-50 text-blue-700">
                  <Icon className="h-6 w-6" />
                </div>
                <h3 className="mt-5 text-lg font-semibold text-slate-950">{module.name}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-500">{module.description}</p>
                <p className="mt-6 text-sm font-semibold text-blue-700 group-hover:text-blue-800">Abrir módulo →</p>
              </Link>
            );
          })}
        </div>
      </section>
    </main>
  );
}
