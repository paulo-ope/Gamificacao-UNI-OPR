// Opções de gráfico compactas para a TV do Cockpit (F5) - mesmo padrão de
// lib/operations-chart-options.ts (ECharts), mas com grid/labels reduzidos para caber em cards
// pequenos ao lado de KPIs, sem virar gráfico decorativo.
import type { EChartsOption } from "echarts";

import type { CockpitBacklogPoint, CockpitProductionPoint, CockpitSlaPoint } from "@/lib/intelligence-cockpit-api";

function dateLabel(value: string) {
  return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", timeZone: "UTC" }).format(new Date(`${value}T12:00:00Z`));
}

const COMPACT_GRID = { left: 32, right: 8, top: 22, bottom: 20 };
const COMPACT_AXIS_LABEL = { color: "#94a3b8", fontSize: 9 };
const COMPACT_TOOLTIP = { trigger: "axis" as const, backgroundColor: "#0f172a", borderWidth: 0, textStyle: { color: "#f8fafc", fontSize: 10 } };

export function buildProductionChartOption(points: CockpitProductionPoint[]): EChartsOption {
  return {
    grid: COMPACT_GRID,
    tooltip: COMPACT_TOOLTIP,
    legend: { top: 0, itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 9, color: "#64748b" } },
    xAxis: {
      type: "category",
      data: points.map((point) => dateLabel(point.date)),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#e2e8f0" } },
      axisLabel: COMPACT_AXIS_LABEL,
    },
    yAxis: { type: "value", splitLine: { lineStyle: { color: "#f1f5f9" } }, axisLabel: COMPACT_AXIS_LABEL },
    series: [
      { name: "Abertas", type: "bar", data: points.map((point) => point.opened), itemStyle: { color: "#2563eb" }, barMaxWidth: 14 },
      { name: "Finalizadas", type: "bar", data: points.map((point) => point.closed), itemStyle: { color: "#059669" }, barMaxWidth: 14 },
    ],
  };
}

export function buildSlaChartOption(points: CockpitSlaPoint[], target: number): EChartsOption {
  return {
    grid: COMPACT_GRID,
    tooltip: COMPACT_TOOLTIP,
    xAxis: {
      type: "category",
      data: points.map((point) => dateLabel(point.date)),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#e2e8f0" } },
      axisLabel: COMPACT_AXIS_LABEL,
    },
    yAxis: { type: "value", min: 0, max: 100, splitLine: { lineStyle: { color: "#f1f5f9" } }, axisLabel: { ...COMPACT_AXIS_LABEL, formatter: "{value}%" } },
    series: [
      {
        name: "SLA",
        type: "line",
        data: points.map((point) => point.sla_rate),
        smooth: true,
        showSymbol: false,
        connectNulls: true,
        lineStyle: { color: "#2563eb", width: 2 },
        areaStyle: { color: "rgba(37, 99, 235, 0.12)" },
        markLine: { silent: true, symbol: "none", lineStyle: { color: "#dc2626", type: "dashed" }, label: { show: false }, data: [{ yAxis: target }] },
      },
    ],
  };
}

export function buildBacklogChartOption(points: CockpitBacklogPoint[]): EChartsOption {
  return {
    grid: COMPACT_GRID,
    tooltip: COMPACT_TOOLTIP,
    xAxis: {
      type: "category",
      data: points.map((point) => dateLabel(point.date)),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#e2e8f0" } },
      axisLabel: COMPACT_AXIS_LABEL,
    },
    yAxis: { type: "value", splitLine: { lineStyle: { color: "#f1f5f9" } }, axisLabel: COMPACT_AXIS_LABEL },
    series: [
      {
        name: "Backlog",
        type: "line",
        data: points.map((point) => point.quantity),
        smooth: true,
        showSymbol: false,
        lineStyle: { color: "#d97706", width: 2 },
        areaStyle: { color: "rgba(217, 119, 6, 0.12)" },
      },
    ],
  };
}
