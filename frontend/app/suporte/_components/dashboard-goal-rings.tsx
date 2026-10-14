"use client";

import dynamic from "next/dynamic";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { useMemo } from "react";

import { OverviewBlock } from "@/components/overview/overview-block";
import { buildMetricRingOption } from "@/lib/overview-chart-options";
import type { SupportMacroCard } from "@/lib/types";
import { cn } from "@/lib/utils";

import { coverageNote, formatCardChange, formatCardTarget, formatCardValue, goalProgress, isGoodWhenUp } from "./dashboard-format";

const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => <div className="h-[116px] animate-pulse rounded-full bg-slate-100" aria-hidden="true" />,
});

const RING_TONE = { ok: "success", attention: "warning", critical: "danger", partial: "neutral", no_data: "neutral", no_target: "neutral" } as const;

function RingTile({ card, previousLabel }: { card: SupportMacroCard; previousLabel: string }) {
  const option = useMemo(
    () => buildMetricRingOption(goalProgress(card), RING_TONE[card.status], formatCardValue(card, card.value)),
    [card],
  );
  const change = formatCardChange(card);
  const goodWhenUp = isGoodWhenUp(card);
  const improved = card.change === null || card.change === 0 || goodWhenUp === null ? null : card.change > 0 === goodWhenUp;
  const DeltaIcon = card.change === null || card.change === 0 ? Minus : card.change > 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <div
      className={cn(
        "min-w-0 rounded-xl border px-2 py-3 text-center",
        card.status === "critical" ? "border-red-200 bg-red-50/60" : "border-slate-200 bg-slate-50/70",
      )}
    >
      <p className="px-1 text-xs font-semibold leading-snug text-slate-700" title={card.label}>
        {card.label}
      </p>
      <div role="img" aria-label={`${card.label}: ${formatCardValue(card, card.value)}`}>
        <ReactECharts option={option} notMerge lazyUpdate opts={{ renderer: "canvas" }} style={{ height: 116, width: "100%" }} />
      </div>
      <span
        className={cn(
          "inline-flex flex-wrap items-center justify-center gap-x-1 rounded-md px-1.5 py-0.5 text-[10px] font-semibold",
          improved === null ? "bg-slate-100 text-slate-500" : improved ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700",
        )}
      >
        <DeltaIcon className="h-3 w-3" aria-hidden="true" />
        {change ?? "sem base"}
        <span className="font-normal opacity-80">{previousLabel}</span>
      </span>
      <div className="mx-1 mt-2.5 flex flex-wrap items-center justify-center gap-x-3 gap-y-0.5 border-t border-slate-200 pt-2.5 text-[10px] text-slate-500">
        <b className="text-slate-900">{formatCardTarget(card)}</b>
      </div>
      {coverageNote(card) ? <p className="mt-1 text-[10px] font-medium text-amber-700">{coverageNote(card)}</p> : null}
    </div>
  );
}

/** Anéis dos indicadores que têm meta (CSAT, TMR, TMA e resolutividade), no desenho dos anéis de SLA da Visão Geral. */
export function DashboardGoalRings({ cards, previousLabel }: { cards: readonly SupportMacroCard[]; previousLabel: string }) {
  const withTarget = cards.filter((card) => card.target !== null);
  return (
    <OverviewBlock
      eyebrow="Metas do Suporte"
      title="Indicadores com meta"
      subtitle="O anel mostra quanto da meta foi atingido; a cor vem do status (dentro da meta, atenção a até 10% da meta, crítico além disso)."
      state={{ empty: withTarget.length === 0 }}
    >
      <div className="grid grid-cols-2 gap-2.5 md:grid-cols-4">
        {withTarget.map((card) => (
          <RingTile key={card.key} card={card} previousLabel={previousLabel} />
        ))}
      </div>
    </OverviewBlock>
  );
}
