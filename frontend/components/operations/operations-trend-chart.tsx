"use client";

import dynamic from "next/dynamic";
import type { EChartsOption } from "echarts";

import { SectionCard } from "@/components/ui/section-card";

const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => <div className="h-[300px] animate-pulse rounded-xl bg-slate-100" aria-label="Carregando gráfico" />
});

export function OperationsTrendChart({
  eyebrow,
  title,
  description,
  badge,
  option,
  onEvents
}: {
  eyebrow: string;
  title: string;
  description: string;
  badge?: string;
  option: EChartsOption;
  /** Ex.: `{ click: (params) => ... }` - drill-through por ponto/barra clicado. */
  onEvents?: Record<string, (params: unknown) => void>;
}) {
  return (
    // Sem `overflow-hidden`: cortava o tooltip do ECharts perto da borda do card (mesmo achado de
    // `section-card.tsx`, 2026-09-05) - nada aqui sangra até a borda arredondada, então não fazia
    // clipe nenhum de propósito.
    <SectionCard eyebrow={eyebrow} title={title} subtitle={description} badge={badge} contentClassName="px-2 pb-2 pt-3 sm:px-4">
      <div role="group" aria-label={title}>
        <ReactECharts
          option={option}
          notMerge
          lazyUpdate
          opts={{ renderer: "canvas" }}
          style={{ height: 300, width: "100%" }}
          onEvents={onEvents}
        />
      </div>
    </SectionCard>
  );
}
