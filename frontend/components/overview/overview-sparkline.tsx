"use client";

import dynamic from "next/dynamic";
import { useMemo } from "react";

import { buildSparklineOption } from "@/lib/overview-chart-options";

const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => <div className="h-[46px] animate-pulse bg-slate-50" aria-hidden="true" />,
});

/** Tendência decorativa do cartão: o número do cartão já diz tudo, então fica fora da árvore de acessibilidade. */
export function OverviewSparkline({ values, color }: { values: readonly number[]; color: string }) {
  const option = useMemo(() => buildSparklineOption(values, color), [values, color]);
  if (values.length < 2) return <div className="h-[46px]" aria-hidden="true" />;
  return (
    <div aria-hidden="true">
      <ReactECharts option={option} notMerge lazyUpdate opts={{ renderer: "canvas" }} style={{ height: 46, width: "100%" }} />
    </div>
  );
}
