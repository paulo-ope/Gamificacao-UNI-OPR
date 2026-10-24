import { CalendarClock, CheckCircle2, ClipboardList, PlayCircle, TriangleAlert, type LucideIcon } from "lucide-react";

import type { SupportPlanSummary } from "@/lib/types";

// Cartões de resumo da aba Especialista/Analista, nas cores da marca UNI. Os de alerta (bloqueados e
// atrasados) só acendem em vermelho/âmbar quando há algo a olhar; com zero ficam neutros.

type Tile = {
  key: keyof Pick<SupportPlanSummary, "open" | "in_progress" | "blocked" | "overdue" | "done_in_period">;
  label: string;
  hint: (summary: SupportPlanSummary) => string;
  icon: LucideIcon;
  /** Cores quando o cartão está "aceso". */
  tone: { bar: string; icon: string; value: string };
  /** Cartões de alerta ficam neutros enquanto o número for zero. */
  alert?: boolean;
};

const NEUTRAL = { bar: "bg-slate-200", icon: "bg-slate-100 text-slate-500", value: "text-slate-400" };

const TILES: Tile[] = [
  { key: "open", label: "Em aberto", hint: () => "Planejados, em andamento ou bloqueados", icon: ClipboardList, tone: { bar: "bg-uni-ink", icon: "bg-uni-mist text-uni-ink", value: "text-uni-ink" } },
  { key: "in_progress", label: "Em andamento", hint: () => "Sendo feitos agora", icon: PlayCircle, tone: { bar: "bg-uni-royal", icon: "bg-uni-royal/10 text-uni-royal", value: "text-uni-royal" } },
  { key: "blocked", label: "Bloqueados", hint: () => "Esperando alguém ou algo", icon: TriangleAlert, alert: true, tone: { bar: "bg-red-500", icon: "bg-red-50 text-red-600", value: "text-red-600" } },
  { key: "overdue", label: "Atrasados", hint: () => "Prazo vencido e não concluídos", icon: CalendarClock, alert: true, tone: { bar: "bg-amber-500", icon: "bg-amber-50 text-amber-600", value: "text-amber-600" } },
  { key: "done_in_period", label: "Concluídos", hint: (summary) => `Nos últimos ${summary.period_days} dias`, icon: CheckCircle2, tone: { bar: "bg-uni-turquoise", icon: "bg-uni-turquoise/15 text-teal-700", value: "text-teal-700" } },
];

export function PlanningSummary({ summary }: { summary: SupportPlanSummary | null }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
      {TILES.map((tile) => {
        const value = summary?.[tile.key];
        const lit = value !== undefined && !(tile.alert && value === 0);
        const tone = lit ? tile.tone : NEUTRAL;
        const Icon = tile.icon;
        return (
          <div key={tile.key} className="relative overflow-hidden rounded-2xl border border-slate-200 bg-white px-4 py-3.5 shadow-sm">
            <span className={`absolute inset-x-0 top-0 h-1 ${tone.bar}`} aria-hidden="true" />
            <div className="flex items-center gap-3">
              <span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${tone.icon}`}>
                <Icon size={22} aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-slate-500">{tile.label}</p>
                <p className={`text-3xl font-bold leading-tight tabular-nums ${tone.value}`}>{value ?? "—"}</p>
              </div>
            </div>
            <p className="mt-2 truncate text-xs text-slate-500">{summary ? tile.hint(summary) : ""}</p>
          </div>
        );
      })}
    </div>
  );
}
