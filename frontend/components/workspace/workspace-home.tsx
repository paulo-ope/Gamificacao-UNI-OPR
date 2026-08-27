"use client";

import Link from "next/link";
import { BarChart3, BriefcaseBusiness, CalendarClock, Headphones, Radar, ShieldCheck, Trophy } from "lucide-react";
import { useEffect, useState } from "react";

import { useWorkspaceShell } from "@/components/workspace/workspace-shell-context";
import { api } from "@/lib/api";
import { workspaceModules } from "@/lib/module-registry";
import type { WorkspaceOverviewCard, WorkspaceVisibleModule } from "@/lib/types";

const icons = { gamification: Trophy, operations: BarChart3, scheduling: CalendarClock, support: Headphones, management: BriefcaseBusiness, admin: ShieldCheck, intelligence: Radar };

export function WorkspaceHome() {
  const { user } = useWorkspaceShell();
  const [visibleModules, setVisibleModules] = useState<WorkspaceVisibleModule[] | null>(null);
  const [overviewCards, setOverviewCards] = useState<WorkspaceOverviewCard[] | null>(null);

  useEffect(() => {
    api.workspaceModules().then(setVisibleModules).catch(() => setVisibleModules(null));
    api.workspaceOverview().then((result) => setOverviewCards(result.cards)).catch(() => setOverviewCards(null));
  }, []);

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
      pinned: false,
      order_index: null,
    }));
  const modules = visibleModules ?? fallbackModules;

  return (
    <div className="mx-auto max-w-7xl px-5 py-10">
      <p className="text-sm text-slate-500">Olá, {user.name}.</p>
      <h1 className="mt-1 text-3xl font-semibold text-slate-950">Visão geral</h1>

      {overviewCards && overviewCards.length ? (
        <div className="mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {overviewCards.map((card) => (
            <Link
              key={card.module_key}
              href={card.link}
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-lg"
            >
              <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-blue-600">{card.title}</p>
              <p className="mt-3 text-3xl font-semibold text-slate-950">{card.metric_value}</p>
              <p className="mt-1 text-sm text-slate-500">{card.metric_label}</p>
              {card.subtitle ? <p className="mt-2 text-xs text-slate-400">{card.subtitle}</p> : null}
            </Link>
          ))}
        </div>
      ) : null}

      <h2 className="mt-12 text-xl font-semibold text-slate-950">Módulos</h2>
      <div className="mt-5 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {modules.map((module) => {
          const Icon = icons[module.key as keyof typeof icons];
          return (
            <Link key={module.key} href={module.web_path} className="group rounded-3xl border border-slate-200 bg-white p-6 shadow-sm transition hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-lg">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-50 text-blue-700">
                {Icon ? <Icon className="h-6 w-6" /> : null}
              </div>
              <h3 className="mt-5 text-lg font-semibold text-slate-950">{module.name}</h3>
              <p className="mt-2 text-sm leading-6 text-slate-500">{module.description}</p>
              <p className="mt-6 text-sm font-semibold text-blue-700 group-hover:text-blue-800">Abrir módulo →</p>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
