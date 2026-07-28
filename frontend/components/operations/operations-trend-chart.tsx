"use client";

import dynamic from "next/dynamic";
import type { EChartsOption } from "echarts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => <div className="h-[300px] animate-pulse rounded-xl bg-slate-100" aria-label="Carregando gráfico" />
});

export function OperationsTrendChart({
  eyebrow,
  title,
  description,
  badge,
  option
}: {
  eyebrow: string;
  title: string;
  description: string;
  badge?: string;
  option: EChartsOption;
}) {
  return (
    <Card className="overflow-hidden rounded-2xl border-slate-200 bg-white shadow-sm">
      <CardHeader className="flex-row items-start justify-between gap-3 pb-0">
        <div className="min-w-0">
          <p className="text-[9px] font-bold uppercase tracking-[0.18em] text-blue-600">{eyebrow}</p>
          <CardTitle className="mt-1 text-base font-semibold text-slate-950">{title}</CardTitle>
          <p className="mt-1 text-[11px] text-slate-500">{description}</p>
        </div>
        {badge ? <span className="shrink-0 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[9px] font-semibold text-slate-500">{badge}</span> : null}
      </CardHeader>
      <CardContent className="px-2 pb-2 pt-1 sm:px-4">
        <ReactECharts option={option} notMerge lazyUpdate opts={{ renderer: "canvas" }} style={{ height: 300, width: "100%" }} />
      </CardContent>
    </Card>
  );
}
