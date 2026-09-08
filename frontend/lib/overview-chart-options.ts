import type { EChartsOption } from "echarts";

import { CHART_INK, CHART_SURFACE } from "@/lib/chart-palette";
import { dateLabel, openingAnomalyThreshold, trendPointLabel } from "@/lib/operations-chart-options";
import type { OperationBacklogTrend, OperationTrendSeries } from "@/lib/operations-api";
import type { ShareSlice } from "@/lib/share-breakdown";

const numberFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const shareFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });

/**
 * Fluxo diário da Visão Geral: mesmo desenho de `buildOpeningsTrendOption` (módulo de Operação) -
 * abertas (barra), finalizadas (linha) e saldo (linha tracejada) - com UMA linha a mais quando
 * há período anterior disponível: finalizadas do período anterior, pra comparar o FORMATO da
 * curva, não só o total agregado (que os cards do topo já mostram). Pedido do usuário,
 * 2026-09-08: "trazer... linha comparando com um período anterior".
 *
 * Alinhamento por ÍNDICE (dia 1 do atual com dia 1 do anterior), não por data - os dois períodos
 * têm datas diferentes por definição. Só desalinha quando o período anterior é cortado no início
 * do ano operacional (`previousWindow`, `lib/period.ts`) e fica mais curto que o atual; nesse
 * caso os dias que faltam no fim ficam sem ponto (`connectNulls: false`), nunca inventados.
 *
 * Função PRÓPRIA da Visão Geral, não uma mudança em `buildOpeningsTrendOption` - o módulo de
 * Operação não pediu essa linha, e mudar a função compartilhada faria ela aparecer lá também.
 */
export function buildOverviewOpeningsTrendOption(
  trend: OperationTrendSeries,
  previousTrend: OperationTrendSeries | null,
): EChartsOption {
  const labels = trend.points.map((point) => trendPointLabel(point.period_start, point.period_end, trend.granularity));
  const openedValues = trend.points.map((point) => point.opened_operation);
  const threshold = openingAnomalyThreshold(openedValues);
  const previousCompleted = previousTrend?.points.map((point) => point.completed) ?? null;

  const series: NonNullable<EChartsOption["series"]> = [
    {
      name: "Abertas",
      type: "bar",
      data: openedValues.map((value) => ({
        value,
        itemStyle: { color: value > threshold ? "#fb7185" : "#93c5fd", borderRadius: [7, 7, 0, 0] },
      })),
      barMaxWidth: 34,
    },
    {
      name: "Finalizadas",
      type: "line",
      data: trend.points.map((point) => point.completed),
      smooth: 0.2,
      symbolSize: 6,
      lineStyle: { color: "#16a34a", width: 2.5 },
      itemStyle: { color: "#16a34a" },
    },
    {
      name: "Saldo",
      type: "line",
      data: trend.points.map((point) => point.opened_operation - point.completed),
      smooth: 0.2,
      symbolSize: 5,
      lineStyle: { color: "#f59e0b", type: "dashed", width: 2 },
      itemStyle: { color: "#f59e0b" },
    },
  ];
  if (previousCompleted) {
    series.push({
      name: "Finalizadas (período anterior)",
      type: "line",
      data: labels.map((_, index) => previousCompleted[index] ?? null),
      connectNulls: false,
      smooth: 0.2,
      symbolSize: 4,
      lineStyle: { color: CHART_INK.muted, width: 2, type: "dashed" },
      itemStyle: { color: CHART_INK.muted },
      emphasis: { focus: "series" },
    });
  }
  if (trend.responsible_filter_active) {
    series.push({
      name: "Associadas ao responsável",
      type: "line",
      data: trend.points.map((point) => point.opened_associated),
      smooth: 0.2,
      symbolSize: 5,
      lineStyle: { color: "#f97316", type: "dotted", width: 2 },
      itemStyle: { color: "#f97316" },
    });
  }

  return {
    animationDuration: 350,
    grid: { left: 48, right: 48, top: 54, bottom: 38 },
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
      axisLabel: { color: "#64748b", fontSize: 10 },
    },
    yAxis: {
      type: "value",
      min: 0,
      axisLabel: { color: "#64748b", fontSize: 10 },
      splitLine: { lineStyle: { color: "#e2e8f0" } },
    },
    series,
  };
}

/** `YYYY-MM-DD` - `YYYY-MM-DD`, em dias corridos (UTC, sem fuso - mesmo cuidado de `lib/period.ts`). */
function daysBetween(iso: string, fromIso: string): number {
  const [y1, m1, d1] = iso.split("-").map(Number);
  const [y2, m2, d2] = fromIso.split("-").map(Number);
  return Math.round((Date.UTC(y1, m1 - 1, d1) - Date.UTC(y2, m2 - 1, d2)) / 86_400_000);
}

/**
 * Histórico de backlog: gráfico PRÓPRIO, não uma linha a mais em cima do fluxo diário
 * (`buildOpeningsTrendOption`, módulo de Operação) - achado real, 2026-09-04: com abertas
 * (barra) + finalizadas (linha) + backlog (linha, eixo secundário) no mesmo canvas, a escala do
 * backlog ficou parecida com a de abertas/finalizadas neste banco (todas na casa das centenas), e
 * a linha de estoque acabou cruzando por cima das barras, competindo por atenção em vez de ficar
 * claramente em segundo plano ("isso tá bom?" - usuário, vendo o resultado ao vivo). Separado,
 * cada gráfico serve um propósito só: fluxo (`buildOpeningsTrendOption`), qualidade (SLA,
 * `buildOverviewSlaTrendOption`) e estoque (aqui).
 *
 * `connectNulls: false`: onde não há fotografia (antes de `coverage_from`), a linha não desenha -
 * preencher com zero afirmaria um backlog que nunca foi medido. Buracos DENTRO do período já
 * coberto (job que não rodou numa hora) já vêm preenchidos pelo backend
 * (`backlog_daily_trend`), então não é um caso que este gráfico precise tratar.
 *
 * Linha de período anterior (pedido do usuário, 2026-09-08, "em todos os gráficos"): alinhada por
 * DESLOCAMENTO DE DIA dentro da janela (dia 5 da janela atual com dia 5 da janela anterior), não
 * por índice do array - diferente do fluxo diário/SLA, o backlog é naturalmente esparso (só tem
 * fotografia a partir de `coverage_from`), então os dois lados podem ter buracos em posições
 * diferentes; alinhar pelo índice bruto do array casaria dias errados entre si.
 */
export function buildBacklogTrendOption(
  trend: OperationBacklogTrend,
  previousTrend: OperationBacklogTrend | null,
): EChartsOption {
  const labels = trend.points.map((point) => dateLabel(point.snapshot_date, { day: "2-digit", month: "2-digit" }));
  const values = trend.points.map((point) => point.backlog);
  const previousByOffset = new Map(
    (previousTrend?.points ?? []).map((point) => [daysBetween(point.snapshot_date, previousTrend!.date_from), point.backlog]),
  );
  const previousValues = previousTrend
    ? trend.points.map((point) => previousByOffset.get(daysBetween(point.snapshot_date, trend.date_from)) ?? null)
    : null;

  const series: NonNullable<EChartsOption["series"]> = [
    {
      name: "Backlog",
      type: "line",
      data: values,
      connectNulls: false,
      smooth: 0.15,
      symbolSize: 5,
      areaStyle: { color: CHART_INK.gridline, opacity: 0.5 },
      lineStyle: { color: CHART_INK.secondary, width: 2 },
      itemStyle: { color: CHART_INK.secondary },
    },
  ];
  if (previousValues && previousValues.some((value) => value !== null)) {
    series.push({
      name: "Backlog (período anterior)",
      type: "line",
      data: previousValues,
      connectNulls: false,
      smooth: 0.15,
      symbolSize: 4,
      lineStyle: { color: "#94a3b8", width: 2, type: "dashed" },
      itemStyle: { color: "#94a3b8" },
      emphasis: { focus: "series" },
    });
  }

  return {
    animationDuration: 350,
    grid: { left: 48, right: 24, top: 30, bottom: 38 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "#0f172a",
      borderWidth: 0,
      textStyle: { color: "#f8fafc", fontSize: 11 },
    },
    legend: series.length > 1 ? { top: 4, right: 8, itemWidth: 10, itemHeight: 8, textStyle: { color: "#475569", fontSize: 10 } } : undefined,
    xAxis: {
      type: "category",
      data: labels,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#cbd5e1" } },
      axisLabel: { color: "#64748b", fontSize: 10 },
    },
    yAxis: {
      type: "value",
      min: 0,
      axisLabel: { color: "#64748b", fontSize: 10 },
      splitLine: { lineStyle: { color: "#e2e8f0" } },
    },
    series,
  };
}

/**
 * SLA ponderado da Visão Geral: mesmo desenho de `buildSlaTrendOption` (módulo de Operação) - SLA
 * acumulado (linha cheia), SLA do dia (linha tracejada) e No prazo/Fora do prazo (barras
 * empilhadas, eixo secundário) - com a linha de SLA acumulado do período anterior quando
 * disponível. Alinhamento por ÍNDICE, igual ao fluxo diário: os pontos de `OperationTrendSeries`
 * são sempre densos (um por dia da janela pedida, nunca esparsos como o backlog).
 *
 * Função PRÓPRIA da Visão Geral - mesma razão de `buildOverviewOpeningsTrendOption`: não alterar
 * `buildSlaTrendOption`, que o módulo de Operação usa sem pedir essa linha.
 */
export function buildOverviewSlaTrendOption(
  trend: OperationTrendSeries,
  previousTrend: OperationTrendSeries | null,
): EChartsOption {
  const labels = trend.points.map((point) => trendPointLabel(point.period_start, point.period_end, trend.granularity));
  const groupLabel = trend.granularity === "day" ? "SLA do dia" : trend.granularity === "week" ? "SLA da semana" : "SLA do mês";
  const previousCumulative = previousTrend?.points.map((point) => point.sla_cumulative_rate) ?? null;

  const series: NonNullable<EChartsOption["series"]> = [
    {
      name: "SLA acumulado",
      type: "line",
      data: trend.points.map((point) => point.sla_cumulative_rate),
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
      data: trend.points.map((point) => ({
        value: point.sla_rate,
        itemStyle: { color: point.sla_rate !== null && point.sla_rate < 80 ? "#ef4444" : "#60a5fa" },
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
      data: trend.points.map((point) => point.completed_on_time),
      barMaxWidth: 34,
      itemStyle: { color: "#bbf7d0" },
    },
    {
      name: "Fora do prazo",
      type: "bar",
      stack: "completed",
      yAxisIndex: 1,
      data: trend.points.map((point) => point.completed_out_of_time),
      barMaxWidth: 34,
      itemStyle: { color: "#fecdd3", borderRadius: [7, 7, 0, 0] },
    },
  ];
  if (previousCumulative) {
    series.push({
      name: "SLA acumulado (período anterior)",
      type: "line",
      data: labels.map((_, index) => previousCumulative[index] ?? null),
      connectNulls: false,
      smooth: 0.25,
      symbolSize: 4,
      lineStyle: { color: CHART_INK.muted, width: 2, type: "dashed" },
      itemStyle: { color: CHART_INK.muted },
      emphasis: { focus: "series" },
    });
  }

  return {
    animationDuration: 350,
    color: ["#1e3a8a", "#60a5fa", "#86efac", "#fecdd3"],
    grid: { left: 48, right: 48, top: 54, bottom: 38 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "#0f172a",
      borderWidth: 0,
      textStyle: { color: "#f8fafc", fontSize: 11 },
      formatter: (params: unknown) => {
        const items = Array.isArray(params) ? params : [params];
        const index = Number((items[0] as { dataIndex?: number } | undefined)?.dataIndex ?? 0);
        const point = trend.points[index];
        if (!point) return "";
        const lines = [
          `<strong>${labels[index]}</strong>`,
          `O.S. no prazo: ${point.completed_on_time}`,
          `O.S. fora do prazo: ${point.completed_out_of_time}`,
          `${groupLabel}: ${point.sla_rate === null ? "-" : `${point.sla_rate}%`}`,
          `SLA acumulado ponderado: ${point.sla_cumulative_rate === null ? "-" : `${point.sla_cumulative_rate}%`}`,
        ];
        if (previousCumulative) {
          const prev = previousCumulative[index];
          lines.push(`SLA acumulado (período anterior): ${prev === null || prev === undefined ? "-" : `${prev}%`}`);
        }
        lines.push("Meta de SLA: 80%");
        return lines.join("<br/>");
      },
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
      axisLabel: { color: "#64748b", fontSize: 10 },
    },
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
    series,
  };
}

/**
 * Donut de participação (parte-para-todo), no padrão de marcas dos gráficos do ecossistema.
 *
 * O que está fixo aqui e por quê:
 * - anel fino (58–82%): marca fina, o dado é o comprimento do arco, não a área pintada;
 * - `borderColor` = cor do card e `borderWidth` 2: é o vão de 2px entre fatias que se tocam,
 *   feito com a própria superfície, nunca com um contorno desenhado;
 * - rótulo direto com a % em TODA fatia, em tinta de texto (não na cor da série): três slots da
 *   paleta ficam abaixo de 3:1 sobre branco, e o rótulo é a compensação exigida - além de ser o
 *   que torna um donut legível com fatias de valores próximos;
 * - sem legenda dentro do gráfico: a lista ao lado (`OverviewShareDonut`) faz o papel de legenda
 *   e de "vista em tabela" ao mesmo tempo;
 * - tooltip com valor em destaque e nome secundário, na hierarquia da legenda.
 *
 * Recebe fatias já dobradas por `foldShares` - este construtor não decide o que é "Outros".
 */
export function buildShareDonutOption(slices: readonly ShareSlice[], options: { totalLabel: string } = { totalLabel: "total" }): EChartsOption {
  const total = slices.reduce((sum, slice) => sum + slice.value, 0);
  return {
    animationDuration: 350,
    tooltip: {
      trigger: "item",
      backgroundColor: CHART_SURFACE,
      borderColor: CHART_INK.gridline,
      borderWidth: 1,
      padding: [6, 10],
      textStyle: { color: CHART_INK.primary, fontSize: 12 },
      formatter: (params) => {
        const p = params as { name: string; value: number; percent: number; color: string };
        return [
          `<span style="display:inline-block;width:10px;height:2px;background:${p.color};vertical-align:middle;margin-right:6px"></span>`,
          `<strong>${numberFormat.format(p.value)}</strong>`,
          `<span style="color:${CHART_INK.secondary}"> · ${shareFormat.format(p.percent)}% · ${p.name}</span>`,
        ].join("");
      },
    },
    graphic: [
      {
        type: "text",
        left: "center",
        top: "44%",
        style: { text: numberFormat.format(total), fill: CHART_INK.primary, fontSize: 22, fontWeight: 600, align: "center" },
      },
      {
        type: "text",
        left: "center",
        top: "56%",
        style: { text: options.totalLabel, fill: CHART_INK.muted, fontSize: 11, align: "center" },
      },
    ],
    series: [
      {
        type: "pie",
        radius: ["58%", "82%"],
        center: ["50%", "50%"],
        avoidLabelOverlap: true,
        minAngle: 3,
        itemStyle: { borderColor: CHART_SURFACE, borderWidth: 2, borderRadius: 4 },
        label: {
          show: true,
          position: "outside",
          formatter: (params) => `${shareFormat.format((params as { percent: number }).percent)}%`,
          color: CHART_INK.secondary,
          fontSize: 11,
          fontWeight: 600,
        },
        labelLine: { length: 8, length2: 6, lineStyle: { color: CHART_INK.gridline } },
        emphasis: { scale: true, scaleSize: 4, label: { fontWeight: 700, color: CHART_INK.primary } },
        data: slices.map((slice) => ({ name: slice.label, value: slice.value, itemStyle: { color: slice.color } })),
      },
    ],
  };
}
