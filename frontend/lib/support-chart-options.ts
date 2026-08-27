import type { EChartsOption } from "echarts";

import { secondsLabel } from "@/lib/format-duration";
import type { SupportOpaBreakdownItem, SupportOpaTimeseriesPoint } from "@/lib/types";

/** Paleta única do módulo — os gráficos precisam ler como um sistema só, e a cor
 *  aqui sempre carrega significado (série, ranking ou estado), nunca decoração.
 *  Azul = volume/geral, âmbar = tempo, esmeralda = humano, violeta = bot. */
export const SUPPORT_CHART_COLORS = {
  volume: "#2563eb",
  volumeSoft: "#93c5fd",
  closed: "#0ea5e9",
  open: "#f59e0b",
  tmrHuman: "#059669",
  tmrAll: "#d97706",
  tma: "#7c3aed",
  bot: "#8b5cf6",
  human: "#10b981",
  neutral: "#94a3b8",
} as const;

/** Intensidade decrescente por rank — o item de maior volume herda a cor mais
 *  forte, reforçando a leitura de ranking sem precisar de legenda à parte. */
export const SUPPORT_RANK_COLORS = ["#1d4ed8", "#2563eb", "#3b82f6", "#60a5fa", "#93c5fd", "#bfdbfe"];

// Sem `as const`: ele congelaria `padding` como tupla readonly, que os tipos do
// ECharts (arrays mutáveis) recusam.
const TOOLTIP = {
  backgroundColor: "#0f172a",
  borderWidth: 0,
  textStyle: { color: "#f8fafc", fontSize: 11 },
  padding: [8, 10],
};

const AXIS_LABEL = { color: "#64748b", fontSize: 10 };

function number(value: number | null | undefined, digits = 0) {
  if (value === null || value === undefined) return "-";
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: digits }).format(value);
}

/** `day` vem do backend como data local (YYYY-MM-DD) já no fuso de operação —
 *  fixar meio-dia UTC evita que o navegador do usuário jogue o rótulo pro dia
 *  anterior/seguinte na virada. */
function dayLabel(isoLocalDate: string) {
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    timeZone: "UTC",
  }).format(new Date(`${isoLocalDate}T12:00:00Z`));
}

/** Tendência diária de volume: encerrados e em aberto empilhados, somando o
 *  total do dia — a composição responde "o volume subiu, mas fechou?" numa
 *  leitura só, que duas linhas separadas não dariam. */
export function buildVolumeTrendOption(points: SupportOpaTimeseriesPoint[]): EChartsOption {
  const labels = points.map((point) => dayLabel(point.day));
  return {
    animationDuration: 300,
    color: [SUPPORT_CHART_COLORS.closed, SUPPORT_CHART_COLORS.open],
    grid: { left: 44, right: 16, top: 34, bottom: 26 },
    legend: { top: 0, right: 0, itemWidth: 10, itemHeight: 8, textStyle: { color: "#475569", fontSize: 10 } },
    tooltip: {
      ...TOOLTIP,
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (params: unknown) => {
        const items = Array.isArray(params) ? params : [params];
        const index = Number((items[0] as { dataIndex?: number } | undefined)?.dataIndex ?? 0);
        const point = points[index];
        if (!point) return "";
        return [
          `<strong>${labels[index]}</strong>`,
          `Total: ${number(point.total)}`,
          `Encerrados: ${number(point.closed)}`,
          `Em aberto: ${number(point.open)}`,
        ].join("<br/>");
      },
    },
    xAxis: {
      type: "category",
      data: labels,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#e2e8f0" } },
      axisLabel: AXIS_LABEL,
    },
    yAxis: {
      type: "value",
      splitLine: { lineStyle: { color: "#f1f5f9" } },
      axisLabel: AXIS_LABEL,
    },
    series: [
      { name: "Encerrados", type: "bar", stack: "volume", data: points.map((p) => p.closed), barMaxWidth: 26, itemStyle: { borderRadius: [0, 0, 0, 0] } },
      { name: "Em aberto", type: "bar", stack: "volume", data: points.map((p) => p.open), barMaxWidth: 26, itemStyle: { borderRadius: [3, 3, 0, 0] } },
    ],
  };
}

/** Tendência de tempos. TMR humano e TMR geral aparecem SEMPRE os dois — a
 *  norma de qualidade de dados proíbe esconder um dos dois, e o gráfico é
 *  justamente onde a diferença entre eles fica evidente. Dias sem cálculo
 *  viram buraco na linha (`null`), nunca zero: zero seria um número errado. */
export function buildTimeTrendOption(points: SupportOpaTimeseriesPoint[]): EChartsOption {
  const labels = points.map((point) => dayLabel(point.day));
  const asMinutes = (value: number | null) => (value === null ? null : Number((value / 60).toFixed(2)));
  return {
    animationDuration: 300,
    color: [SUPPORT_CHART_COLORS.tma, SUPPORT_CHART_COLORS.tmrHuman, SUPPORT_CHART_COLORS.tmrAll],
    grid: { left: 46, right: 16, top: 34, bottom: 26 },
    legend: { top: 0, right: 0, itemWidth: 10, itemHeight: 8, textStyle: { color: "#475569", fontSize: 10 } },
    tooltip: {
      ...TOOLTIP,
      trigger: "axis",
      formatter: (params: unknown) => {
        const items = Array.isArray(params) ? params : [params];
        const index = Number((items[0] as { dataIndex?: number } | undefined)?.dataIndex ?? 0);
        const point = points[index];
        if (!point) return "";
        const cov = point.tmr_all_responses_coverage;
        return [
          `<strong>${labels[index]}</strong>`,
          `TMA: ${secondsLabel(point.average_duration_seconds)}`,
          `TMR humano: ${secondsLabel(point.average_tmr_seconds)}`,
          `TMR geral: ${secondsLabel(point.average_tmr_all_responses_seconds)}`,
          cov && cov.total > 0
            ? `<span style="opacity:.75">TMR geral sobre ${number(cov.count)} de ${number(cov.total)} atend.</span>`
            : "",
        ]
          .filter(Boolean)
          .join("<br/>");
      },
    },
    xAxis: {
      type: "category",
      data: labels,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#e2e8f0" } },
      axisLabel: AXIS_LABEL,
    },
    yAxis: {
      type: "value",
      name: "min",
      nameTextStyle: { color: "#94a3b8", fontSize: 9 },
      splitLine: { lineStyle: { color: "#f1f5f9" } },
      axisLabel: AXIS_LABEL,
    },
    series: [
      { name: "TMA", type: "line", smooth: true, showSymbol: false, connectNulls: false, data: points.map((p) => asMinutes(p.average_duration_seconds)) },
      { name: "TMR humano", type: "line", smooth: true, showSymbol: false, connectNulls: false, data: points.map((p) => asMinutes(p.average_tmr_seconds)) },
      { name: "TMR geral", type: "line", smooth: true, showSymbol: false, connectNulls: false, data: points.map((p) => asMinutes(p.average_tmr_all_responses_seconds)) },
    ],
  };
}

/** Ranking horizontal por categoria (atendente, motivo, canal...). Barra
 *  horizontal porque o rótulo é texto de tamanho variável — em barra vertical
 *  ele vira diagonal ou é truncado. */
export function buildRankingOption(items: SupportOpaBreakdownItem[], limit = 8): EChartsOption {
  // ECharts desenha o eixo de categoria de baixo pra cima; invertendo aqui, o
  // maior volume fica no topo, que é onde o olho começa a ler.
  const top = items.slice(0, limit).reverse();
  return {
    animationDuration: 300,
    grid: { left: 4, right: 46, top: 8, bottom: 4, containLabel: true },
    tooltip: {
      ...TOOLTIP,
      trigger: "item",
      formatter: (params: unknown) => {
        const item = params as { dataIndex?: number };
        const row = top[Number(item?.dataIndex ?? 0)];
        if (!row) return "";
        return [
          `<strong>${row.label}</strong>`,
          `Atendimentos: ${number(row.total)}`,
          `Participação: ${number(row.share_percentage, 1)}%`,
          `Encerramento: ${number(row.closure_rate, 1)}%`,
          `Duração média: ${secondsLabel(row.avg_duration_seconds)}`,
        ].join("<br/>");
      },
    },
    xAxis: { type: "value", show: false },
    yAxis: {
      type: "category",
      data: top.map((item) => item.label),
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: { ...AXIS_LABEL, width: 130, overflow: "truncate" },
    },
    series: [
      {
        type: "bar",
        data: top.map((item, index) => ({
          value: item.total,
          // `top` está invertido, então o rank real precisa ser recalculado —
          // sem isso a cor mais forte cairia no menor volume.
          itemStyle: {
            color: SUPPORT_RANK_COLORS[Math.min(top.length - 1 - index, SUPPORT_RANK_COLORS.length - 1)],
            borderRadius: [0, 4, 4, 0],
          },
        })),
        barMaxWidth: 18,
        label: {
          show: true,
          position: "right" as const,
          // `value` no tipo do ECharts é uma união ampla (string | Date | ...),
          // então normaliza aqui em vez de estreitar o parâmetro.
          formatter: (params: { value?: unknown }) =>
            typeof params.value === "number" ? number(params.value) : String(params.value ?? "-"),
          color: "#475569",
          fontSize: 10,
          fontWeight: 600,
        },
      },
    ],
  };
}

/** Composição bot vs. humano. O denominador vai no centro da rosca porque o
 *  percentual sozinho mente quando parte dos atendimentos não foi classificada. */
export function buildBotHumanDonutOption(
  withBotPercentage: number | null,
  classified: number,
  total: number,
): EChartsOption {
  const withBot = withBotPercentage ?? 0;
  return {
    animationDuration: 300,
    tooltip: {
      ...TOOLTIP,
      trigger: "item",
      formatter: (params: unknown) => {
        const item = params as { name?: string; value?: number };
        return `<strong>${item?.name}</strong><br/>${number(item?.value, 1)}% dos classificados`;
      },
    },
    legend: { bottom: 0, itemWidth: 8, itemHeight: 8, textStyle: { color: "#475569", fontSize: 10 } },
    series: [
      {
        type: "pie",
        radius: ["58%", "80%"],
        center: ["50%", "44%"],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: "#fff", borderWidth: 2 },
        label: {
          show: true,
          position: "center",
          formatter: () => `{v|${number(classified)}}\n{l|de ${number(total)} classificados}`,
          rich: {
            v: { fontSize: 18, fontWeight: 700, color: "#0f172a" },
            l: { fontSize: 9, color: "#94a3b8", padding: [3, 0, 0, 0] },
          },
        },
        emphasis: { label: { show: true } },
        data: [
          { name: "Com bot", value: Number(withBot.toFixed(1)), itemStyle: { color: SUPPORT_CHART_COLORS.bot } },
          { name: "Sem bot", value: Number(Math.max(0, 100 - withBot).toFixed(1)), itemStyle: { color: SUPPORT_CHART_COLORS.human } },
        ],
      },
    ],
  };
}
