"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";

import { buildHourlyChartOption } from "@/lib/support-tv-chart-options";
import type { SupportTvHourly } from "@/lib/support-tv-api";
import { TvCard, TvEmpty, TvUnavailable } from "./tv-primitives";
import type { TvTheme } from "./tv-theme";

const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => <div className="h-full min-h-[200px] animate-pulse rounded-lg bg-slate-500/10" aria-label="Carregando gráfico" />,
});

export function TvHourlyChart({ hourly, theme }: { hourly: SupportTvHourly | null; theme: TvTheme }) {
  // Celular: legenda em coluna e horas de 3 em 3, para nada se sobrepor em 390 px.
  const [compact, setCompact] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(max-width: 639px)");
    const update = () => setCompact(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  const option = useMemo(() => (hourly ? buildHourlyChartOption(hourly, theme, compact) : null), [hourly, theme, compact]);
  const hasData = hourly?.points.some((point) => (point.today ?? 0) > 0 || (point.baseline_average ?? 0) > 0) ?? false;

  return (
    <TvCard theme={theme} eyebrow="Ritmo por hora — atendimentos abertos">
      {!hourly || !option ? (
        <TvUnavailable theme={theme} />
      ) : !hasData ? (
        <TvEmpty theme={theme}>Nenhum atendimento aberto hoje até agora.</TvEmpty>
      ) : (
        <div className="relative min-h-[240px] flex-1 xl:min-h-0">
          <div className="absolute inset-0">
            <ReactECharts option={option} notMerge lazyUpdate opts={{ renderer: "canvas" }} style={{ height: "100%", width: "100%" }} />
          </div>
        </div>
      )}
    </TvCard>
  );
}
