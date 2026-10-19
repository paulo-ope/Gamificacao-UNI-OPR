"use client";

import dynamic from "next/dynamic";
import { useMemo } from "react";

import { buildSparklineOption } from "@/lib/overview-chart-options";

const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => <div className="h-[46px] animate-pulse bg-slate-50" aria-hidden="true" />,
});

const DEFAULT_HEIGHT = 46;

/** "2026-10-17" -> "17/10" (rótulo do dia no tooltip dos mini-gráficos). */
export function sparkDayLabel(iso: string) {
  const [, month, day] = iso.split("-");
  return day && month ? `${day.slice(0, 2)}/${month}` : iso;
}

/**
 * Tendência do cartão. O número do cartão já diz tudo, então o desenho fica fora da árvore de
 * acessibilidade; passar o mouse mostra o ponto (dia, valor, diferença para o anterior, pico).
 * `labels` tem um rótulo por valor (mesma ordem/tamanho); `format` formata o valor do tooltip.
 */
export function OverviewSparkline({
  values,
  color,
  height = DEFAULT_HEIGHT,
  labels,
  format,
}: {
  values: readonly number[];
  color: string;
  height?: number;
  labels?: readonly string[];
  format?: (value: number) => string;
}) {
  const option = useMemo(() => buildSparklineOption(values, color, labels, format), [values, color, labels, format]);
  if (values.length < 2) return <div style={{ height }} aria-hidden="true" />;
  return (
    <div aria-hidden="true">
      <ReactECharts option={option} notMerge lazyUpdate opts={{ renderer: "canvas" }} style={{ height, width: "100%" }} />
    </div>
  );
}
