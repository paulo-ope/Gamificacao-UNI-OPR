// Opções do gráfico por hora da TV do SGP Suporte (ECharts). Fonte grande para leitura à
// distância (o padrão compacto do cockpit, 9-10 px, é ilegível numa TV).
import type { EChartsOption } from "echarts";

import { TV_CHART_INK, TV_SERIES, type TvTheme } from "@/components/support-tv/tv-theme";
import type { SupportTvHourly } from "@/lib/support-tv-api";

function hourLabel(hour: number) {
  return `${String(hour).padStart(2, "0")}h`;
}

export function buildHourlyChartOption(hourly: SupportTvHourly, theme: TvTheme, compact = false): EChartsOption {
  const ink = TV_CHART_INK[theme];
  const baselineLabel = hourly.baseline_weeks_used === 1 ? "Mesmo dia da semana passada" : `Média do mesmo dia (últimas ${hourly.baseline_weeks_used} semanas)`;
  return {
    animation: false,
    grid: { left: compact ? 32 : 40, right: 12, top: compact ? 62 : 36, bottom: 28 },
    tooltip: {
      trigger: "axis",
      backgroundColor: ink.tooltipBg,
      borderWidth: 0,
      textStyle: { color: "#f8fafc", fontSize: 16 },
    },
    legend: {
      top: 0,
      ...(compact ? { left: 0, orient: "vertical" as const } : {}),
      itemWidth: 14,
      itemHeight: 14,
      textStyle: { color: ink.muted, fontSize: compact ? 13 : 15 },
      data: ["Hoje", baselineLabel],
    },
    xAxis: {
      type: "category",
      data: hourly.points.map((point) => hourLabel(point.hour)),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: ink.grid } },
      axisLabel: { color: ink.muted, fontSize: compact ? 13 : 15, interval: compact ? 3 : 1 },
    },
    yAxis: {
      type: "value",
      minInterval: 1,
      splitLine: { lineStyle: { color: ink.grid } },
      axisLabel: { color: ink.muted, fontSize: 15 },
    },
    series: [
      {
        name: "Hoje",
        type: "bar",
        // `null` nas horas futuras: o ECharts não desenha barra (nunca uma barra de zero).
        data: hourly.points.map((point) => point.today),
        itemStyle: { color: TV_SERIES.today, borderRadius: [4, 4, 0, 0] },
        barMaxWidth: 28,
      },
      {
        name: baselineLabel,
        type: "line",
        data: hourly.points.map((point) => point.baseline_average),
        smooth: true,
        showSymbol: false,
        connectNulls: false,
        lineStyle: { color: TV_SERIES.baseline[theme], width: 3, type: "dashed" },
        itemStyle: { color: TV_SERIES.baseline[theme] },
      },
    ],
  };
}
