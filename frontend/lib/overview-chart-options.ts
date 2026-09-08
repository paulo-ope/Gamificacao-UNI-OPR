import type { EChartsOption } from "echarts";

import { CHART_INK, CHART_SURFACE } from "@/lib/chart-palette";
import { dateLabel } from "@/lib/operations-chart-options";
import type { OperationBacklogTrend } from "@/lib/operations-api";
import type { ShareSlice } from "@/lib/share-breakdown";

const numberFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const shareFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });

/**
 * Histórico de backlog: gráfico PRÓPRIO, não uma linha a mais em cima do fluxo diário
 * (`buildOpeningsTrendOption`, módulo de Operação) - achado real, 2026-09-04: com abertas
 * (barra) + finalizadas (linha) + backlog (linha, eixo secundário) no mesmo canvas, a escala do
 * backlog ficou parecida com a de abertas/finalizadas neste banco (todas na casa das centenas), e
 * a linha de estoque acabou cruzando por cima das barras, competindo por atenção em vez de ficar
 * claramente em segundo plano ("isso tá bom?" - usuário, vendo o resultado ao vivo). Separado,
 * cada gráfico serve um propósito só: fluxo (`buildOpeningsTrendOption`), qualidade (SLA,
 * `buildSlaTrendOption`) e estoque (aqui).
 *
 * `connectNulls: false`: onde não há fotografia (antes de `coverage_from`), a linha não desenha -
 * preencher com zero afirmaria um backlog que nunca foi medido. Buracos DENTRO do período já
 * coberto (job que não rodou numa hora) já vêm preenchidos pelo backend
 * (`backlog_daily_trend`), então não é um caso que este gráfico precise tratar.
 */
export function buildBacklogTrendOption(trend: OperationBacklogTrend): EChartsOption {
  const labels = trend.points.map((point) => dateLabel(point.snapshot_date, { day: "2-digit", month: "2-digit" }));
  const values = trend.points.map((point) => point.backlog);

  return {
    animationDuration: 350,
    grid: { left: 48, right: 24, top: 30, bottom: 38 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "#0f172a",
      borderWidth: 0,
      textStyle: { color: "#f8fafc", fontSize: 11 },
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
    series: [
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
    ],
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
