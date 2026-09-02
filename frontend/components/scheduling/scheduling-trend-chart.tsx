"use client";

import dynamic from "next/dynamic";
import type { EChartsOption } from "echarts";

import type { SchedulingDailyPoint } from "@/lib/scheduling-api";

const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => <div className="h-[180px] animate-pulse rounded-xl bg-slate-100" aria-label="Carregando gráfico" />,
});

// Companheiro do calendário no painel "Hoje": o calendário é só o clique-para-o-dia (célula
// pequena, só um número), este gráfico é quem carrega a leitura do mês inteiro de uma vez -
// pedido do usuário 2026-08-31 ("pense em métricas, que tipo de gráfico a gente consegue gerar").
export function SchedulingTrendChart({ dailyPoints }: { dailyPoints: SchedulingDailyPoint[] }) {
  const option: EChartsOption = {
    color: ["#2563eb", "#f97316"],
    tooltip: { trigger: "axis" },
    legend: { top: 0, itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 11 } },
    grid: { left: 32, right: 12, top: 30, bottom: 20 },
    xAxis: { type: "category", data: dailyPoints.map((point) => point.date.slice(8)), axisLabel: { fontSize: 10, interval: 2 } },
    yAxis: { type: "value", axisLabel: { fontSize: 10 } },
    series: [
      { name: "1º agendamento", type: "bar", barMaxWidth: 8, data: dailyPoints.map((point) => point.first_schedule_events) },
      { name: "Reagendamento", type: "line", smooth: true, symbolSize: 5, data: dailyPoints.map((point) => point.reschedule_events) },
    ],
  };

  return <ReactECharts option={option} notMerge lazyUpdate style={{ height: 180, width: "100%" }} />;
}
