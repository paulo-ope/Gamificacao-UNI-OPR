import { ArrowDownRight, ArrowUpRight, Minus, type LucideIcon } from "lucide-react";
import * as React from "react";

import { type Tone, toneSoftBgClass, toneTextClass } from "@/lib/tones";
import { cn } from "@/lib/utils";

export type SummaryMetricDelta = {
  /** Variação em % contra o período de referência; `null` = sem base de comparação. */
  value: number | null;
  /** Subir é bom (finalizadas, SLA), ruim (backlog, fora do prazo) ou neutro (demanda)? */
  goodWhenUp: boolean | null;
  /** Nome do período de referência, ex.: "30 dias anteriores". */
  againstLabel: string;
};

type SummaryMetricProps = {
  label: string;
  value: React.ReactNode;
  tone?: Tone;
  icon?: LucideIcon;
  hint?: string;
  delta?: SummaryMetricDelta;
  className?: string;
};

const percentFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });

export function deltaPresentation(delta: SummaryMetricDelta) {
  if (delta.value === null) {
    return { Icon: Minus, text: "sem base de comparação", className: "text-slate-400" };
  }
  const up = delta.value > 0;
  const flat = delta.value === 0;
  const Icon = flat ? Minus : up ? ArrowUpRight : ArrowDownRight;
  const text = `${up ? "+" : ""}${percentFormat.format(delta.value)}% vs. ${delta.againstLabel}`;
  // A cor do delta é direção × se subir é bom - não é a cor da série nem a do valor.
  if (flat || delta.goodWhenUp === null) return { Icon, text, className: "text-slate-500" };
  const good = up === delta.goodWhenUp;
  return { Icon, text, className: good ? "text-emerald-700" : "text-red-700" };
}

// Cartão de métrica compacto unificado (padrão SummaryMetric do módulo de operações + variante
// com ícone dos StatCards antigos da gamificação). `delta` segue o contrato de "stat tile":
// valor · variação assinada contra um período nomeado · cor = direção × se subir é bom.
export function SummaryMetric({ label, value, tone = "slate", icon: Icon, hint, delta, className }: SummaryMetricProps) {
  const deltaView = delta ? deltaPresentation(delta) : null;
  return (
    <div className={cn("flex min-w-0 items-start gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-panel", className)}>
      {Icon ? (
        <div className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-xl", toneSoftBgClass(tone))}>
          <Icon className="h-4 w-4" />
        </div>
      ) : null}
      <div className="min-w-0">
        <p className="text-xs font-medium leading-5 text-slate-600">{label}</p>
        <p className={cn("mt-1 break-words text-2xl font-semibold leading-8 tabular-nums", toneTextClass(tone))}>{value}</p>
        {deltaView ? (
          <p className={cn("mt-2 flex items-start gap-1 text-xs font-medium leading-5", deltaView.className)}>
            <deltaView.Icon className="h-3 w-3 shrink-0" aria-hidden="true" />
            <span>{deltaView.text}</span>
          </p>
        ) : null}
        {hint ? <p className="mt-1 text-xs leading-5 text-slate-500">{hint}</p> : null}
      </div>
    </div>
  );
}
