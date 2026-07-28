import type { EChartsOption } from "echarts";

import type {
  OperationControlTower,
  OperationTrendGranularity,
  OperationTrendSeries,
  OperationWorkScheduleOverview,
} from "@/lib/operations-api";

function dateLabel(value: string, options: Intl.DateTimeFormatOptions) {
  return new Intl.DateTimeFormat("pt-BR", {
    ...options,
    timeZone: "UTC",
  }).format(new Date(`${value}T12:00:00Z`));
}

export function trendPointLabel(
  start: string,
  end: string,
  granularity: OperationTrendGranularity,
) {
  if (granularity === "month")
    return dateLabel(start, { month: "short", year: "2-digit" }).replace(
      " de ",
      "/",
    );
  if (granularity === "week") {
    const from = dateLabel(start, { day: "2-digit", month: "2-digit" });
    const to = dateLabel(end, { day: "2-digit", month: "2-digit" });
    return from === to ? from : `${from}–${to}`;
  }
  return dateLabel(start, { day: "2-digit", month: "2-digit" });
}

function average(values: number[]) {
  return values.length
    ? values.reduce((total, value) => total + value, 0) / values.length
    : 0;
}

export function openingAnomalyThreshold(values: number[]) {
  if (values.length < 3) return Number.POSITIVE_INFINITY;
  const expected = average(values);
  const variance =
    values.reduce((total, value) => total + (value - expected) ** 2, 0) /
    values.length;
  return expected + 2 * Math.sqrt(variance);
}

function common(data: OperationTrendSeries) {
  const labels = data.points.map((point) =>
    trendPointLabel(point.period_start, point.period_end, data.granularity),
  );
  return {
    labels,
    grid: { left: 48, right: 48, top: 54, bottom: 38 },
    tooltip: {
      trigger: "axis" as const,
      backgroundColor: "#0f172a",
      borderWidth: 0,
      textStyle: { color: "#f8fafc", fontSize: 11 },
    },
    xAxis: {
      type: "category" as const,
      data: labels,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#cbd5e1" } },
      axisLabel: { color: "#64748b", fontSize: 10 },
    },
  };
}

export function buildSlaTrendOption(data: OperationTrendSeries): EChartsOption {
  const base = common(data);
  const groupLabel =
    data.granularity === "day"
      ? "SLA do dia"
      : data.granularity === "week"
        ? "SLA da semana"
        : "SLA do mês";

  return {
    animationDuration: 350,
    color: ["#1e3a8a", "#60a5fa", "#86efac", "#fecdd3"],
    grid: base.grid,
    tooltip: {
      ...base.tooltip,
      formatter: (params: unknown) => {
        const items = Array.isArray(params) ? params : [params];
        const index = Number(
          (items[0] as { dataIndex?: number } | undefined)?.dataIndex ?? 0,
        );
        const point = data.points[index];
        if (!point) return "";
        return [
          `<strong>${base.labels[index]}</strong>`,
          `O.S. no prazo: ${point.completed_on_time}`,
          `O.S. fora do prazo: ${point.completed_out_of_time}`,
          `${groupLabel}: ${point.sla_rate === null ? "-" : `${point.sla_rate}%`}`,
          `SLA acumulado ponderado: ${
            point.sla_cumulative_rate === null
              ? "-"
              : `${point.sla_cumulative_rate}%`
          }`,
          "Meta de SLA: 80%",
        ].join("<br/>");
      },
    },
    legend: {
      top: 8,
      right: 8,
      itemWidth: 10,
      itemHeight: 8,
      textStyle: { color: "#475569", fontSize: 10 },
    },
    xAxis: base.xAxis,
    yAxis: [
      {
        type: "value",
        min: 0,
        max: 100,
        axisLabel: { formatter: "{value}%", color: "#2563eb", fontSize: 10 },
        splitLine: { lineStyle: { color: "#e2e8f0" } },
      },
      {
        type: "value",
        min: 0,
        axisLabel: { color: "#94a3b8", fontSize: 10 },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: "SLA acumulado",
        type: "line",
        data: data.points.map((point) => point.sla_cumulative_rate),
        smooth: 0.25,
        symbolSize: 7,
        lineStyle: { width: 3, color: "#1e3a8a" },
        itemStyle: { color: "#1e3a8a" },
        connectNulls: true,
        markLine: {
          symbol: "none",
          label: { formatter: "Meta 80%", color: "#64748b", fontSize: 9 },
          lineStyle: { color: "#94a3b8", type: "dashed" },
          data: [{ yAxis: 80 }],
        },
      },
      {
        name: groupLabel,
        type: "line",
        data: data.points.map((point) => ({
          value: point.sla_rate,
          itemStyle: {
            color:
              point.sla_rate !== null && point.sla_rate < 80
                ? "#ef4444"
                : "#60a5fa",
          },
        })),
        smooth: 0.18,
        symbolSize: 6,
        lineStyle: { width: 2, color: "#60a5fa", type: "dashed" },
        itemStyle: { color: "#60a5fa" },
        connectNulls: true,
      },
      {
        name: "No prazo",
        type: "bar",
        stack: "completed",
        yAxisIndex: 1,
        data: data.points.map((point) => point.completed_on_time),
        barMaxWidth: 34,
        itemStyle: { color: "#bbf7d0" },
      },
      {
        name: "Fora do prazo",
        type: "bar",
        stack: "completed",
        yAxisIndex: 1,
        data: data.points.map((point) => point.completed_out_of_time),
        barMaxWidth: 34,
        itemStyle: { color: "#fecdd3", borderRadius: [7, 7, 0, 0] },
      },
    ],
  };
}

export function buildOpeningsTrendOption(data: OperationTrendSeries): EChartsOption {
  const base = common(data);
  const values = data.points.map((point) => point.opened_operation);
  const expected = average(values);
  const threshold = openingAnomalyThreshold(values);
  const averageLabel =
    data.granularity === "month"
      ? "Média mensal"
      : data.granularity === "week"
        ? "Média semanal"
        : "Média diária";
  const series: NonNullable<EChartsOption["series"]> = [
    {
      name: "Abertas",
      type: "bar",
      data: values.map((value) => ({
        value,
        itemStyle: {
          color: value > threshold ? "#fb7185" : "#93c5fd",
          borderRadius: [7, 7, 0, 0],
        },
      })),
      barMaxWidth: 34,
      markLine: {
        symbol: "none",
        label: {
          show: true,
          position: "insideEndTop",
          formatter: `${averageLabel}: ${new Intl.NumberFormat("pt-BR", {
            maximumFractionDigits: 1,
          }).format(expected)}`,
          color: "#334155",
          fontSize: 10,
          fontWeight: 600,
          backgroundColor: "#f8fafc",
          borderColor: "#cbd5e1",
          borderWidth: 1,
          borderRadius: 4,
          padding: [3, 5],
        },
        lineStyle: { color: "#334155", type: "dashed", width: 2 },
        data: [{ yAxis: expected }],
      },
    },
    {
      name: "Finalizadas",
      type: "line",
      data: data.points.map((point) => point.completed),
      smooth: 0.2,
      symbolSize: 6,
      lineStyle: { color: "#16a34a", width: 2.5 },
      itemStyle: { color: "#16a34a" },
    },
    {
      name: "Saldo",
      type: "line",
      data: data.points.map((point) => point.opened_operation - point.completed),
      smooth: 0.2,
      symbolSize: 5,
      lineStyle: { color: "#f59e0b", type: "dashed", width: 2 },
      itemStyle: { color: "#f59e0b" },
    },
  ];
  if (data.responsible_filter_active) {
    series.push({
      name: "Associadas ao responsável",
      type: "line",
      data: data.points.map((point) => point.opened_associated),
      smooth: 0.2,
      symbolSize: 5,
      lineStyle: { color: "#f97316", type: "dotted", width: 2 },
      itemStyle: { color: "#f97316" },
    });
  }
  return {
    animationDuration: 350,
    grid: base.grid,
    tooltip: base.tooltip,
    legend: {
      top: 8,
      right: 8,
      itemWidth: 10,
      itemHeight: 8,
      textStyle: { color: "#475569", fontSize: 10 },
    },
    xAxis: base.xAxis,
    yAxis: {
      type: "value",
      min: 0,
      axisLabel: { color: "#64748b", fontSize: 10 },
      splitLine: { lineStyle: { color: "#e2e8f0" } },
    },
    series,
  };
}

export function buildTeamProductionOption(
  data: OperationWorkScheduleOverview,
): EChartsOption {
  const items = [...data.by_model]
    .sort((left, right) => right.completed - left.completed)
    .slice(0, 12);
  return {
    animationDuration: 350,
    grid: { left: 120, right: 28, top: 34, bottom: 24 },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      backgroundColor: "#0f172a",
      borderWidth: 0,
      textStyle: { color: "#f8fafc", fontSize: 11 },
    },
    xAxis: {
      type: "value",
      min: 0,
      axisLabel: { color: "#64748b", fontSize: 10 },
      splitLine: { lineStyle: { color: "#e2e8f0" } },
    },
    yAxis: {
      type: "category",
      data: items.map((item) => item.model_name),
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: {
        color: "#475569",
        fontSize: 10,
        width: 108,
        overflow: "truncate",
      },
    },
    series: [
      {
        name: "Finalizadas",
        type: "bar",
        data: items.map((item) => item.completed),
        barMaxWidth: 18,
        itemStyle: { color: "#2563eb", borderRadius: [0, 6, 6, 0] },
      },
      {
        name: "Fora da jornada",
        type: "bar",
        data: items.map((item) => item.outside_schedule),
        barMaxWidth: 18,
        itemStyle: { color: "#f97316", borderRadius: [0, 6, 6, 0] },
      },
    ],
  };
}

export function buildControlTowerOption(data: OperationControlTower): EChartsOption {
  const labels = data.timeline.map((point) =>
    dateLabel(point.date, { day: "2-digit", month: "2-digit" }),
  );
  return {
    animationDuration: 300,
    grid: { left: 42, right: 46, top: 52, bottom: 38 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "#0f172a",
      borderWidth: 0,
      textStyle: { color: "#f8fafc", fontSize: 11 },
    },
    legend: {
      top: 8,
      right: 8,
      itemWidth: 10,
      itemHeight: 8,
      textStyle: { color: "#475569", fontSize: 10 },
    },
    xAxis: {
      type: "category",
      data: labels,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#cbd5e1" } },
      axisLabel: {
        color: "#64748b",
        fontSize: 9,
        interval: data.timeline.length > 18 ? 2 : 0,
      },
    },
    yAxis: [
      {
        type: "value",
        min: 0,
        axisLabel: { color: "#64748b", fontSize: 9 },
        splitLine: { lineStyle: { color: "#e2e8f0" } },
      },
      {
        type: "value",
        min: 0,
        axisLabel: { color: "#64748b", fontSize: 9 },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: "Abertas",
        type: "bar",
        color: "#60a5fa",
        barMaxWidth: 24,
        data: data.timeline.map((point) => ({
          value: point.opened,
          itemStyle: {
            color: point.outside_expected ? "#ef4444" : "#60a5fa",
            borderRadius: [4, 4, 0, 0],
          },
        })),
      },
      {
        name: "Finalizadas",
        type: "line",
        color: "#10b981",
        data: data.timeline.map((point) => point.completed),
        smooth: 0.2,
        symbolSize: 4,
        lineStyle: { color: "#10b981", width: 2 },
        itemStyle: { color: "#10b981" },
      },
      {
        name: "Esperado",
        type: "line",
        color: "#475569",
        data: data.timeline.map((point) => point.expected_opened),
        smooth: 0.25,
        symbol: "none",
        lineStyle: { color: "#475569", type: "dashed", width: 1.5 },
      },
      {
        name: "Limite",
        type: "line",
        color: "#f59e0b",
        data: data.timeline.map((point) => point.upper_limit),
        smooth: 0.25,
        symbol: "none",
        lineStyle: { color: "#f59e0b", type: "dotted", width: 1.5 },
      },
      {
        name: "Backlog",
        type: "line",
        color: "#7c3aed",
        yAxisIndex: 1,
        data: data.timeline.map((point) => point.backlog),
        smooth: 0.2,
        symbol: "none",
        lineStyle: { color: "#7c3aed", width: 2 },
        areaStyle: { color: "rgba(124, 58, 237, 0.06)" },
      },
    ],
  };
}
