"use client";

import ReactECharts from "echarts-for-react";

import { InfoHint } from "@/components/gamification/info-hint";
import { formatAnnulledPoints, formatMoney, formatPoints } from "@/lib/format";
import { normalizeRegional, regionalName } from "@/lib/regional";
import type { CollaboratorScore, PenaltyDistributionItem, RegionalHealthItem } from "@/lib/types";

type DashboardChartsProps = {
  ranking: CollaboratorScore[];
  penalties: PenaltyDistributionItem[];
  health: RegionalHealthItem[];
};

export function DashboardCharts({ ranking, penalties, health }: DashboardChartsProps) {
  // Mesma regra já aplicada à saúde por regional no backend: colaborador não cadastrado não conta
  // nos gráficos de análise (só pontos/O.S de quem está formalmente cadastrado).
  const registeredRanking = ranking.filter((item) => item.is_registered !== false);
  const scatterItems = registeredRanking.filter((item) => item.service_orders_count > 0);
  const maxScatterOrders = Math.max(...scatterItems.map((item) => item.service_orders_count), 0);
  const maxScatterPoints = Math.max(...scatterItems.map((item) => item.final_points), 0);
  const regionalPoints = new Map<string, { final_points: number; collaborators: number; estimated_payment: number }>();
  registeredRanking.forEach((item) => {
    const key = normalizeRegional(item.regional);
    const current = regionalPoints.get(key) ?? { final_points: 0, collaborators: 0, estimated_payment: 0 };
    current.final_points += item.final_points;
    current.collaborators += 1;
    current.estimated_payment += item.estimated_payment;
    regionalPoints.set(key, current);
  });
  const healthScatterItems = health
    .map((item) => {
      const points = regionalPoints.get(normalizeRegional(item.regional)) ?? { final_points: 0, collaborators: 0, estimated_payment: 0 };
      return {
        ...item,
        health_score: Math.max(0, Math.min(100, item.sla_rate)),
        final_points: points.final_points,
        collaborators: points.collaborators,
        estimated_payment: points.estimated_payment
      };
    })
    .filter((item) => item.total_orders > 0 || item.final_points > 0);
  const maxHealthScatterPoints = Math.max(...healthScatterItems.map((item) => item.final_points), 0);
  const scatterPoint = (item: CollaboratorScore) => ({
    value: [item.service_orders_count, item.final_points],
    collaborator_name: item.collaborator_name,
    regional: item.regional,
    estimated_payment: item.estimated_payment,
    penalty_points: item.penalty_points,
    recurrence_count: item.recurrence_service_orders ?? item.warranty_service_orders ?? 0,
    symbolSize:
      (item.recurrence_service_orders ?? item.warranty_service_orders ?? 0) > 0
        ? Math.max(12, Math.min(34, 10 + (item.recurrence_service_orders ?? item.warranty_service_orders ?? 0) * 1.5))
        : Math.max(8, Math.min(24, 8 + Math.abs(item.penalty_points) / 40))
  });
  const rankingData = [...registeredRanking]
    .sort((a, b) => b.final_points - a.final_points)
    .slice(0, 15)
    .sort((a, b) => a.final_points - b.final_points);

  // Estilo "lista de barras" moderno: nome completo ACIMA da barra (dentro da área do gráfico,
  // sem truncar nem colidir com o valor), barra fina com gradiente do manual da marca UNI
  // (royal → turquoise). Substitui o layout antigo de rótulos truncados num eixo lateral.
  const UNI_BAR_GRADIENT = {
    type: "linear",
    x: 0,
    y: 0,
    x2: 1,
    y2: 0,
    colorStops: [
      { offset: 0, color: "#2d5fff" },
      { offset: 1, color: "#27d9bf" }
    ]
  };

  const rankingOption = {
    tooltip: {
      trigger: "axis",
      formatter: (params: Array<{ dataIndex: number; value: number }>) => {
        const item = rankingData[params[0]?.dataIndex ?? 0];
        return [`<strong>${item?.collaborator_name ?? ""}</strong>`, `Pontos finais: ${formatPoints(item?.final_points ?? 0)}`].join("<br />");
      }
    },
    grid: { left: 8, right: 96, top: 8, bottom: 8 },
    xAxis: { type: "value", show: false },
    yAxis: {
      type: "category",
      data: rankingData.map((item) => item.collaborator_name),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        show: true,
        inside: true,
        verticalAlign: "bottom",
        align: "left",
        padding: [0, 0, 6, -2],
        color: "#334155",
        fontSize: 11,
        fontWeight: 600
      }
    },
    series: [
      {
        type: "bar",
        barWidth: 10,
        data: rankingData.map((item) => item.final_points),
        itemStyle: { color: UNI_BAR_GRADIENT, borderRadius: [5, 5, 5, 5] },
        showBackground: true,
        backgroundStyle: { color: "#f1f5f9", borderRadius: [5, 5, 5, 5] },
        label: {
          show: true,
          position: "right",
          distance: 6,
          color: "#010c8b",
          fontWeight: 600,
          formatter: ({ value }: { value: number }) => formatPoints(value)
        }
      }
    ]
  };

  const penaltyData = [...penalties]
    .filter((item) => item.value > 0 || item.service_orders_count > 0)
    .sort((a, b) => b.value - a.value)
    .slice(0, 10)
    .sort((a, b) => a.value - b.value);

  const penaltyOption = {
    tooltip: {
      trigger: "axis",
      confine: true,
      extraCssText: "max-width: 280px; white-space: normal;",
      formatter: (params: Array<{ dataIndex: number }>) => {
        const item = penaltyData[params[0]?.dataIndex ?? 0];
        return [
          `<strong>${item?.name ?? ""}</strong>`,
          `O.S: ${item?.service_orders_count ?? 0}`,
          `Pontos anulados: ${formatAnnulledPoints(item?.value ?? 0)}`
        ].join("<br />");
      }
    },
    // Mesmo estilo "lista de barras" do ranking: nome completo do motivo ACIMA da barra (sem
    // truncar), valor à direita da barra - elimina de vez a colisão entre rótulo truncado e valor
    // que existia no layout antigo de eixo lateral (achado real, ver print do usuário).
    grid: { left: 8, right: 150, top: 8, bottom: 8 },
    xAxis: { type: "value", show: false },
    yAxis: {
      type: "category",
      data: penaltyData.map((item) => item.name),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        show: true,
        inside: true,
        verticalAlign: "bottom",
        align: "left",
        padding: [0, 0, 6, -2],
        color: "#334155",
        fontSize: 11,
        fontWeight: 600
      }
    },
    series: [
      {
        type: "bar",
        barWidth: 10,
        data: penaltyData.map((item) => item.value),
        itemStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 1,
            y2: 0,
            colorStops: [
              { offset: 0, color: "#dc2626" },
              { offset: 1, color: "#f87171" }
            ]
          },
          borderRadius: [5, 5, 5, 5]
        },
        showBackground: true,
        backgroundStyle: { color: "#f1f5f9", borderRadius: [5, 5, 5, 5] },
        label: {
          show: true,
          position: "right",
          distance: 6,
          color: "#7f1d1d",
          fontWeight: 600,
          formatter: ({ dataIndex }: { dataIndex: number }) => {
            const item = penaltyData[dataIndex];
            return `${item.service_orders_count} O.S · ${formatAnnulledPoints(item.value)}`;
          }
        }
      }
    ]
  };

  const healthOption = {
    tooltip: { trigger: "axis", confine: true, extraCssText: "max-width: 280px; white-space: normal;" },
    legend: { top: 0, textStyle: { color: "#475569" } },
    grid: { left: 40, right: 16, top: 42, bottom: 58 },
    xAxis: {
      type: "category",
      data: health.map((item) => item.regional),
      axisLabel: { color: "#334155", interval: 0, rotate: 18 }
    },
    yAxis: { type: "value", min: 0, max: 100, axisLabel: { formatter: "{value}%", color: "#475569" } },
    color: ["#2d5fff", "#e11d48"],
    series: [
      {
        name: "SLA",
        type: "bar",
        data: health.map((item) => item.sla_rate),
        itemStyle: { borderRadius: [4, 4, 0, 0] }
      },
      {
        name: "Reincidência",
        type: "bar",
        data: health.map((item) => item.recurrence_rate),
        itemStyle: { borderRadius: [4, 4, 0, 0] }
      }
    ]
  };

  const scatterOption = {
    legend: { top: 0, textStyle: { color: "#475569" } },
    tooltip: {
      trigger: "item",
      confine: true,
      extraCssText: "max-width: 280px; white-space: normal;",
      formatter: (params: {
        value: [number, number];
        data: {
          collaborator_name: string;
          regional: string;
          estimated_payment: number;
          penalty_points: number;
          recurrence_count: number;
        };
      }) => {
        const [orders, points] = params.value;
        const item = params.data;
        return [
          `<strong>${item.collaborator_name}</strong>`,
          regionalName(item.regional),
          `O.S: ${orders}`,
          `Reincidências: ${item.recurrence_count}`,
          `Pontos finais: ${formatPoints(points)}`,
          `Pontos anulados: ${formatAnnulledPoints(item.penalty_points)}`,
          `Valor a ser pago: ${formatMoney(item.estimated_payment)}`
        ].join("<br />");
      }
    },
    grid: { left: 52, right: 24, top: 44, bottom: 48 },
    xAxis: {
      type: "value",
      name: "O.S",
      min: 0,
      max: maxScatterOrders ? Math.ceil(maxScatterOrders * 1.12) : 10,
      nameLocation: "middle",
      nameGap: 30,
      axisLabel: { color: "#475569" },
      splitLine: { lineStyle: { color: "#e2e8f0" } }
    },
    yAxis: {
      type: "value",
      name: "Pontos finais",
      min: 0,
      max: maxScatterPoints ? Math.ceil(maxScatterPoints * 1.12) : 10,
      axisLabel: { color: "#475569" },
      splitLine: { lineStyle: { color: "#e2e8f0" } }
    },
    series: [
      {
        name: "Sem reincidência",
        type: "scatter",
        symbolSize: (value: [number, number], params: { data: { symbolSize: number } }) => params.data.symbolSize,
        data: scatterItems
          .filter((item) => (item.recurrence_service_orders ?? item.warranty_service_orders ?? 0) === 0)
          .map(scatterPoint),
        itemStyle: { color: "#059669", opacity: 0.78, borderColor: "#ffffff", borderWidth: 1 }
      },
      {
        name: "Com reincidência",
        type: "scatter",
        symbolSize: (value: [number, number], params: { data: { symbolSize: number } }) => params.data.symbolSize,
        data: scatterItems
          .filter((item) => (item.recurrence_service_orders ?? item.warranty_service_orders ?? 0) > 0)
          .map(scatterPoint),
        itemStyle: { color: "#dc2626", opacity: 0.82, borderColor: "#ffffff", borderWidth: 1 }
      }
    ]
  };

  const healthScatterOption = {
    tooltip: {
      trigger: "item",
      confine: true,
      extraCssText: "max-width: 280px; white-space: normal;",
      formatter: (params: {
        value: [number, number];
        data: {
          regional: string;
          health_status: string;
          sla_rate: number;
          recurrence_rate: number;
          multiplier: number;
          total_orders: number;
          collaborators: number;
          estimated_payment: number;
        };
      }) => {
        const item = params.data;
        return [
          `<strong>${regionalName(item.regional)}</strong>`,
          `Saúde: ${params.value[1].toFixed(2)}% (${item.health_status})`,
          `SLA: ${item.sla_rate.toFixed(2)}%`,
          `Reincidência: ${item.recurrence_rate.toFixed(2)}%`,
          `Multiplicador: ${item.multiplier.toFixed(2)}x`,
          `Pontos finais: ${formatPoints(params.value[0])}`,
          `O.S: ${item.total_orders}`,
          `Colaboradores: ${item.collaborators}`,
          `Valor a ser pago: ${formatMoney(item.estimated_payment)}`
        ].join("<br />");
      }
    },
    grid: { left: 56, right: 28, top: 24, bottom: 54 },
    xAxis: {
      type: "value",
      name: "Pontos finais",
      min: 0,
      max: maxHealthScatterPoints ? Math.ceil(maxHealthScatterPoints * 1.12) : 10,
      nameLocation: "middle",
      nameGap: 34,
      axisLabel: { color: "#475569" },
      splitLine: { lineStyle: { color: "#e2e8f0" } }
    },
    yAxis: {
      type: "value",
      name: "Saúde da base",
      min: 0,
      max: 100,
      axisLabel: { formatter: "{value}%", color: "#475569" },
      splitLine: { lineStyle: { color: "#e2e8f0" } }
    },
    series: [
      {
        name: "Base/regional",
        type: "scatter",
        data: healthScatterItems.map((item) => ({
          value: [Number(item.final_points.toFixed(2)), Number(item.health_score.toFixed(2))],
          ...item
        })),
        symbolSize: (_value: [number, number], params: { data: { total_orders: number } }) =>
          Math.max(12, Math.min(42, 10 + Math.sqrt(params.data.total_orders || 0) / 2)),
        itemStyle: { color: "#2d5fff", opacity: 0.8, borderColor: "#ffffff", borderWidth: 1 },
        label: { show: false },
        emphasis: {
          label: {
            show: true,
            position: "top",
            color: "#0f172a",
            fontSize: 11,
            formatter: ({ data }: { data: { regional: string } }) => regionalName(data.regional).replace(/^UNI\s*-\s*/i, "")
          }
        }
      }
    ]
  };

  return (
    <section className="grid gap-4 lg:grid-cols-3">
      <div className="panel lg:col-span-3">
        <div className="panel-header bg-slate-50/70">
          <div className="flex items-center gap-2">
            <h2 className="panel-title">Dispersão saúde da base x pontuação</h2>
            <InfoHint ariaLabel="Ajuda sobre Dispersão saúde da base x pontuação" description="Compara a qualidade da base com a pontuação final gerada por regional." />
          </div>
        </div>
        <div className="px-2 py-4">
          <ReactECharts option={healthScatterOption} style={{ height: 320 }} />
        </div>
      </div>

      <div className="panel lg:col-span-3">
        <div className="panel-header bg-slate-50/70">
          <div className="flex items-center gap-2">
            <h2 className="panel-title">Dispersão de produtividade</h2>
            <InfoHint ariaLabel="Ajuda sobre Dispersão de produtividade" description="Relaciona volume, pontuação, reincidência e outros fatores por colaborador ou grupo." />
          </div>
        </div>
        <div className="px-2 py-4">
          <ReactECharts option={scatterOption} style={{ height: 320 }} />
        </div>
      </div>

      <div className="panel lg:col-span-2">
        <div className="panel-header bg-slate-50/70">
          <div className="flex items-center gap-2">
            <h2 className="panel-title">Top 15 por pontos finais</h2>
            <InfoHint ariaLabel="Ajuda sobre Top 15 por pontos finais" description="Mostra quem terminou o período com maior pontuação final depois das anulações e multiplicadores." />
          </div>
        </div>
        <div className="px-2 py-4">
          <ReactECharts option={rankingOption} style={{ height: Math.max(220, rankingData.length * 38) }} />
        </div>
      </div>

      <div className="panel">
        <div className="panel-header bg-slate-50/70">
          <div className="flex items-center gap-2">
            <h2 className="panel-title">Distribuição de pontos anulados</h2>
            <InfoHint ariaLabel="Ajuda sobre Distribuição de pontos anulados" description="Mostra os principais motivos de anulação por quantidade de O.S e volume de pontos." />
          </div>
        </div>
        <div className="px-2 py-4">
          <ReactECharts option={penaltyOption} style={{ height: Math.max(220, penaltyData.length * 42) }} />
        </div>
      </div>

      <div className="panel lg:col-span-3">
        <div className="panel-header bg-slate-50/70">
          <div className="flex items-center gap-2">
            <h2 className="panel-title">Saúde operacional por regional/base</h2>
            <InfoHint ariaLabel="Ajuda sobre Saúde operacional por regional/base" description="Mostra como SLA e reincidência influenciam a leitura de saúde operacional da base." />
          </div>
        </div>
        <div className="px-2 py-4">
          <ReactECharts option={healthOption} style={{ height: 300 }} />
        </div>
      </div>
    </section>
  );
}



