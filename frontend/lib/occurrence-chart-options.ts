import type { EChartsOption } from "echarts";

import { CATEGORICAL_SLOTS, NEUTRAL_SERIES } from "@/lib/chart-palette";
import type { SupportOccurrenceGroupStat, SupportOccurrenceOverview } from "@/lib/types";

// Opções ECharts da visão geral das Ocorrências (assunto 211). Mesmo visual dos gráficos da Visão
// Geral do Suporte (`support-chart-options.ts`): tooltip escuro, eixo cinza, cor com significado fixo.
// Cada builder usa o `dataIndex` do clique para voltar ao dado de origem.

export const OCCURRENCE_COLORS = {
  open: "#f59e0b",
  finalized: "#2563eb",
  volume: "#3b82f6",
} as const;

const TOOLTIP = {
  backgroundColor: "#0f172a",
  borderWidth: 0,
  textStyle: { color: "#f8fafc", fontSize: 11 },
  padding: [8, 10],
  appendToBody: true,
};
const AXIS_LABEL = { color: "#64748b", fontSize: 10 };
const GRIDLINE = { lineStyle: { color: "#e2e8f0" } };
const NO_DIAGNOSIS = "Sem diagnóstico";

function number(value: number) {
  return new Intl.NumberFormat("pt-BR").format(value);
}

function percent(value: number) {
  return `${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(value)}%`;
}

function dayLabel(iso: string) {
  const [, month, day] = iso.split("-");
  return `${day}/${month}`;
}

export function shortRegional(value: string) {
  if (value === "NAO IDENTIFICADO") return "Não identificada";
  return value.replace(/^UNI - /, "");
}

/** Cor de cada diagnóstico: slots categóricos em ordem; "Sem diagnóstico" e o excedente ficam neutros. */
export function diagnosisColors(rows: SupportOccurrenceGroupStat[]): string[] {
  let slot = 0;
  return rows.map((row) => {
    if (!row.name || row.name === NO_DIAGNOSIS) return NEUTRAL_SERIES;
    const color = CATEGORICAL_SLOTS[slot] ?? NEUTRAL_SERIES;
    slot += 1;
    return color;
  });
}

/** Rosca de diagnósticos com o total no centro; a legenda clicável é desenhada ao lado, em HTML. */
export function buildDiagnosisDonutOption(rows: SupportOccurrenceGroupStat[], total: number): EChartsOption {
  const colors = diagnosisColors(rows);
  return {
    animationDuration: 300,
    tooltip: {
      ...TOOLTIP,
      trigger: "item",
      formatter: (params: unknown) => {
        const row = rows[Number((params as { dataIndex?: number }).dataIndex ?? 0)];
        if (!row) return "";
        return [
          `<strong>${row.name ?? NO_DIAGNOSIS}</strong>`,
          `${number(row.total)} finalizadas (${percent(row.share_pct)})`,
          `Tempo médio: ${row.avg_resolution_minutes == null ? "—" : `${Math.round(row.avg_resolution_minutes)} min`}`,
          '<span style="color:#94a3b8">Clique para ver as ocorrências</span>',
        ].join("<br/>");
      },
    },
    title: {
      text: number(total),
      subtext: "finalizadas",
      left: "center",
      top: "38%",
      textStyle: { color: "#0f172a", fontSize: 26, fontWeight: 700 },
      subtextStyle: { color: "#64748b", fontSize: 11 },
      itemGap: 2,
    },
    series: [
      {
        type: "pie",
        radius: ["58%", "82%"],
        center: ["50%", "50%"],
        data: rows.map((row, index) => ({
          name: row.name ?? NO_DIAGNOSIS,
          value: row.total,
          itemStyle: { color: colors[index] },
        })),
        cursor: "pointer",
        label: { show: false },
        labelLine: { show: false },
        itemStyle: { borderColor: "#ffffff", borderWidth: 2, borderRadius: 4 },
        emphasis: { scaleSize: 4 },
      },
    ],
  };
}

/** Abertas x finalizadas por dia (barras lado a lado), um ponto por dia do período. */
export function buildDailyFlowOption(daily: SupportOccurrenceOverview["daily"]): EChartsOption {
  return {
    animationDuration: 300,
    grid: { left: 8, right: 12, top: 24, bottom: 4, containLabel: true },
    legend: { top: 0, right: 0, itemWidth: 10, itemHeight: 10, textStyle: { color: "#475569", fontSize: 10 } },
    tooltip: { ...TOOLTIP, trigger: "axis", axisPointer: { type: "shadow" } },
    xAxis: {
      type: "category",
      data: daily.map((point) => dayLabel(point.day)),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#cbd5e1" } },
      axisLabel: { ...AXIS_LABEL, hideOverlap: true },
    },
    yAxis: { type: "value", minInterval: 1, axisLabel: AXIS_LABEL, splitLine: GRIDLINE },
    series: [
      {
        name: "Abertas",
        type: "bar",
        data: daily.map((point) => point.opened),
        itemStyle: { color: OCCURRENCE_COLORS.open, borderRadius: [4, 4, 0, 0] },
        barMaxWidth: 16,
        cursor: "pointer",
      },
      {
        name: "Finalizadas",
        type: "bar",
        data: daily.map((point) => point.finalized),
        itemStyle: { color: OCCURRENCE_COLORS.finalized, borderRadius: [4, 4, 0, 0] },
        barMaxWidth: 16,
        cursor: "pointer",
      },
    ],
  };
}

/** Ocorrências abertas por hora do dia (0h-23h). */
export function buildHourOption(byHour: SupportOccurrenceOverview["by_hour"]): EChartsOption {
  return {
    animationDuration: 300,
    grid: { left: 8, right: 12, top: 12, bottom: 4, containLabel: true },
    tooltip: {
      ...TOOLTIP,
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (params: unknown) => {
        const first = (Array.isArray(params) ? params[0] : params) as { dataIndex?: number };
        const point = byHour[Number(first?.dataIndex ?? 0)];
        return point ? `<strong>${String(point.hour).padStart(2, "0")}h</strong><br/>${number(point.count)} ocorrências` : "";
      },
    },
    xAxis: {
      type: "category",
      data: byHour.map((point) => `${String(point.hour).padStart(2, "0")}h`),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#cbd5e1" } },
      axisLabel: { ...AXIS_LABEL, interval: 2 },
    },
    yAxis: { type: "value", minInterval: 1, axisLabel: AXIS_LABEL, splitLine: GRIDLINE },
    series: [
      {
        type: "bar",
        data: byHour.map((point) => point.count),
        itemStyle: { color: OCCURRENCE_COLORS.volume, borderRadius: [4, 4, 0, 0] },
        barMaxWidth: 18,
        cursor: "pointer",
      },
    ],
  };
}

/** Mapa de calor regional x diagnóstico (só as combinações mais frequentes). */
export function buildHeatmapOption(overview: SupportOccurrenceOverview): EChartsOption {
  const regionals = overview.matrix_regionals;
  const diagnoses = overview.matrix_diagnoses;
  const max = Math.max(1, ...overview.matrix.map((cell) => cell.count));
  const data = overview.matrix.map((cell) => [
    diagnoses.indexOf(cell.diagnosis),
    // Eixo Y de baixo pra cima: a regional mais afetada fica no topo.
    regionals.length - 1 - regionals.indexOf(cell.regional),
    cell.count,
  ]);
  return {
    animationDuration: 300,
    grid: { left: 4, right: 16, top: 8, bottom: 56, containLabel: true },
    tooltip: {
      ...TOOLTIP,
      formatter: (params: unknown) => {
        const [x, y, value] = (params as { value: number[] }).value;
        const regional = regionals[regionals.length - 1 - y];
        return `<strong>${shortRegional(regional)}</strong><br/>${diagnoses[x]}: ${number(value)}<br/><span style="color:#94a3b8">Clique para ver as ocorrências</span>`;
      },
    },
    xAxis: {
      type: "category",
      data: diagnoses,
      splitArea: { show: true },
      axisTick: { show: false },
      axisLabel: { ...AXIS_LABEL, interval: 0, width: 90, overflow: "break" },
    },
    yAxis: {
      type: "category",
      data: [...regionals].reverse().map(shortRegional),
      splitArea: { show: true },
      axisTick: { show: false },
      axisLabel: { ...AXIS_LABEL, width: 130, overflow: "truncate" },
    },
    visualMap: {
      min: 0,
      max,
      show: false,
      inRange: { color: ["#dbeafe", "#2563eb", "#1e3a8a"] },
    },
    series: [
      {
        type: "heatmap",
        data,
        cursor: "pointer",
        label: { show: true, color: "#0f172a", fontSize: 11, fontWeight: 600 },
        itemStyle: { borderColor: "#ffffff", borderWidth: 2, borderRadius: 4 },
        emphasis: { itemStyle: { shadowBlur: 8, shadowColor: "rgba(15,23,42,0.25)" } },
      },
    ],
  };
}
