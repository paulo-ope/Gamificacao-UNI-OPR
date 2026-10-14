import type { EChartsOption } from "echarts";

import { CHART_INK } from "@/lib/chart-palette";
import { openingAnomalyThreshold } from "@/lib/operations-chart-options";
import type { SupportMacroDailyPoint, SupportMacroWeekBucket } from "@/lib/types";

// Gráficos do Dashboard Suporte, no mesmo desenho da Visão Geral de Operações
// (`buildOverviewOpeningsTrendOption`): barras com o total, linhas por tipo, linha cinza tracejada com o
// período anterior alinhado por posição do dia e tooltip escuro. Os números vêm prontos do backend.

const numberFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const percentFormat = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

const AXIS = {
  axisTick: { show: false },
  axisLine: { lineStyle: { color: "#cbd5e1" } },
  axisLabel: { color: "#64748b", fontSize: 10 },
} as const;

const TOOLTIP = {
  trigger: "axis",
  backgroundColor: "#0f172a",
  borderWidth: 0,
  textStyle: { color: "#f8fafc", fontSize: 11 },
  appendToBody: true,
} as const;

const LEGEND = { top: 8, right: 8, itemWidth: 10, itemHeight: 8, textStyle: { color: "#475569", fontSize: 10 } } as const;

function dayLabel(iso: string) {
  const [, month, day] = iso.split("-");
  return `${day}/${month}`;
}

function indexOf(params: unknown) {
  const items = Array.isArray(params) ? params : [params];
  return Number((items[0] as { dataIndex?: number } | undefined)?.dataIndex ?? 0);
}

/** Fluxo diário: atendimentos realizados (barra) e solucionados / foi a campo (linhas), com o período anterior. */
export function buildSupportDailyFlowOption(
  points: readonly SupportMacroDailyPoint[],
  previous: readonly SupportMacroDailyPoint[],
): EChartsOption {
  const labels = points.map((point) => dayLabel(point.day));
  const performed = points.map((point) => point.performed);
  const threshold = openingAnomalyThreshold(performed);

  const series: NonNullable<EChartsOption["series"]> = [
    {
      name: "Realizados",
      type: "bar",
      data: performed.map((value) => ({
        value,
        itemStyle: { color: value > threshold ? "#fb7185" : "#93c5fd", borderRadius: [7, 7, 0, 0] },
      })),
      barMaxWidth: 34,
    },
    {
      name: "Solucionados",
      type: "line",
      data: points.map((point) => point.solved),
      smooth: 0.2,
      symbolSize: 6,
      lineStyle: { color: "#16a34a", width: 2.5 },
      itemStyle: { color: "#16a34a" },
    },
    {
      name: "Foi a campo",
      type: "line",
      data: points.map((point) => point.field),
      smooth: 0.2,
      symbolSize: 6,
      lineStyle: { color: "#f59e0b", width: 2.5 },
      itemStyle: { color: "#f59e0b" },
    },
  ];
  if (previous.length) {
    series.push({
      name: "Realizados (período anterior)",
      type: "line",
      data: labels.map((_, index) => previous[index]?.performed ?? null),
      connectNulls: false,
      smooth: 0.2,
      symbolSize: 4,
      lineStyle: { color: CHART_INK.muted, width: 2, type: "dashed" },
      itemStyle: { color: CHART_INK.muted },
      emphasis: { focus: "series" },
    });
  }

  return {
    animationDuration: 350,
    grid: { left: 48, right: 48, top: 54, bottom: 38 },
    tooltip: {
      ...TOOLTIP,
      formatter: (params: unknown) => {
        const index = indexOf(params);
        const point = points[index];
        if (!point) return "";
        const lines = [
          `<strong>${labels[index]}</strong>`,
          `Realizados: ${numberFormat.format(point.performed)}`,
          `Solucionados: ${numberFormat.format(point.solved)}`,
          `Foi a campo: ${numberFormat.format(point.field)}`,
        ];
        if (previous.length) {
          const prev = previous[index];
          lines.push(`Realizados (período anterior): ${prev ? numberFormat.format(prev.performed) : "-"}`);
        }
        return lines.join("<br/>");
      },
    },
    legend: LEGEND,
    xAxis: { type: "category", data: labels, ...AXIS },
    yAxis: { type: "value", min: 0, axisLabel: AXIS.axisLabel, splitLine: { lineStyle: { color: "#e2e8f0" } } },
    series,
  };
}

/** Hoje (data local) em ISO: semanas que ainda não começaram não entram no gráfico, que cresce a cada semana. */
function todayIso() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

/**
 * Evolução semanal (domingo a sábado): mesmo traço do mini-gráfico dos cartões da Visão Geral - linha suave
 * com área clara por baixo -, com a semana no eixo e os dados no tooltip ao passar o mouse sobre a linha.
 */
export function buildSupportWeeklyOption(allWeeks: readonly SupportMacroWeekBucket[]): EChartsOption {
  const today = todayIso();
  const weeks = allWeeks.filter((week) => week.date_from <= today);
  const range = (week: SupportMacroWeekBucket) => `${dayLabel(week.date_from)} a ${dayLabel(week.date_to)}`;
  const labels = weeks.map((week) => `${week.label}
${range(week)}`);
  const line = (name: string, key: "performed" | "solved" | "field", color: string) => ({
    name,
    type: "line" as const,
    data: weeks.map((week) => week[key]),
    smooth: true,
    symbol: "circle",
    symbolSize: 8,
    showSymbol: false,
    lineStyle: { width: 2.5, color },
    itemStyle: { color, borderColor: "#fff", borderWidth: 2 },
    areaStyle: { color, opacity: 0.12 },
    emphasis: { focus: "series" as const },
  });

  return {
    animationDuration: 350,
    grid: { left: 48, right: 24, top: 54, bottom: 52 },
    tooltip: {
      ...TOOLTIP,
      axisPointer: { type: "line", lineStyle: { color: "#94a3b8", type: "dashed" } },
      formatter: (params: unknown) => {
        const week = weeks[indexOf(params)];
        if (!week) return "";
        return [
          `<strong>${week.label} (${range(week)})</strong>`,
          `Realizados: ${numberFormat.format(week.performed)}`,
          `Solucionados: ${numberFormat.format(week.solved)}`,
          `Foi a campo: ${numberFormat.format(week.field)}`,
          `Resolutividade: ${week.resolutivity === null ? "-" : `${percentFormat.format(week.resolutivity)}%`}`,
        ].join("<br/>");
      },
    },
    legend: LEGEND,
    xAxis: { type: "category", data: labels, boundaryGap: false, ...AXIS, axisLabel: { ...AXIS.axisLabel, interval: 0, lineHeight: 14 } },
    yAxis: { type: "value", min: 0, axisLabel: AXIS.axisLabel, splitLine: { lineStyle: { color: "#e2e8f0" } } },
    series: [
      line("Realizados", "performed", "#2563eb"),
      line("Solucionados", "solved", "#16a34a"),
      line("Foi a campo", "field", "#f59e0b"),
    ],
  };
}
