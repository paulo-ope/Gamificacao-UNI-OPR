"use client";

import { Activity } from "lucide-react";

import { OverviewBlock, type OverviewBlockState } from "@/components/overview/overview-block";
import type { CockpitMonitorHealth } from "@/lib/intelligence-cockpit-api";
import { formatAgo, monitorTone, type MonitorTone } from "@/lib/overview-monitors";
import { cn } from "@/lib/utils";

const DOT_CLASS: Record<MonitorTone, string> = {
  ok: "bg-emerald-500",
  failing: "bg-red-500",
  disabled: "bg-slate-300",
  never: "bg-slate-300",
};

const TONE_LABEL: Record<MonitorTone, string> = {
  ok: "Saudável",
  failing: "Com falha",
  disabled: "Desligado",
  never: "Nunca executou",
};

/**
 * Saúde dos monitores do UNI Intelligence (os que alimentam o cockpit e os alertas). Lê o mesmo
 * `monitor_health` do payload do cockpit; a cor e o "há X min" vêm de `lib/overview-monitors.ts`.
 * Só aparece para quem tem `intelligence:read` - sem a permissão a tela nem pede o dado.
 */
export function OverviewMonitorsCard({
  monitors,
  state,
}: {
  monitors: readonly CockpitMonitorHealth[] | null;
  state?: OverviewBlockState;
}) {
  return (
    <OverviewBlock
      eyebrow="UNI Intelligence"
      title="Saúde dos monitores"
      subtitle="Última execução de cada monitor que alimenta os alertas."
      badge={<Activity className="h-4 w-4 text-slate-400" aria-hidden="true" />}
      state={{ ...state, empty: !state?.loading && !state?.error && monitors !== null && monitors.length === 0 }}
      emptyLabel="Nenhum monitor configurado."
      deniedLabel="Seu perfil não tem acesso ao UNI Intelligence."
    >
      <ul className="divide-y divide-slate-100">
        {(monitors ?? []).map((monitor) => {
          const tone = monitorTone(monitor);
          return (
            <li key={monitor.monitor_key} className="flex items-center justify-between gap-3 py-2.5 text-xs">
              <span className="flex min-w-0 items-center gap-2 text-slate-700">
                <span className={cn("h-2 w-2 shrink-0 rounded-full", DOT_CLASS[tone])} aria-hidden="true" />
                <span className="min-w-0 truncate font-medium">{monitor.name}</span>
                <span className="sr-only">{TONE_LABEL[tone]}</span>
              </span>
              <span className="shrink-0 text-slate-500">{formatAgo(monitor.last_run_at)}</span>
            </li>
          );
        })}
      </ul>
    </OverviewBlock>
  );
}
