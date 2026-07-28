import type { LucideIcon } from "lucide-react";
import * as React from "react";

import { type Tone, toneSoftBgClass, toneTextClass } from "@/lib/tones";
import { cn } from "@/lib/utils";

type SummaryMetricProps = {
  label: string;
  value: React.ReactNode;
  tone?: Tone;
  icon?: LucideIcon;
  hint?: string;
  className?: string;
};

// Cartão de métrica compacto unificado (padrão SummaryMetric do módulo de operações + variante
// com ícone dos StatCards antigos da gamificação).
export function SummaryMetric({ label, value, tone = "slate", icon: Icon, hint, className }: SummaryMetricProps) {
  return (
    <div className={cn("flex min-w-0 items-center gap-2.5 rounded-xl border border-slate-200 bg-white px-3 py-2.5 shadow-sm", className)}>
      {Icon ? (
        <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-lg", toneSoftBgClass(tone))}>
          <Icon className="h-4 w-4" />
        </div>
      ) : null}
      <div className="min-w-0">
        <p className="truncate text-[9px] font-bold uppercase tracking-[0.12em] text-slate-400">{label}</p>
        <p className={cn("truncate text-sm font-semibold tabular-nums", toneTextClass(tone))}>{value}</p>
        {hint ? <p className="mt-0.5 truncate text-[10px] leading-4 text-slate-500">{hint}</p> : null}
      </div>
    </div>
  );
}
