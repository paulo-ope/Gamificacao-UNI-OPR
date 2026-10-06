"use client";

import dynamic from "next/dynamic";

// Carregado sob demanda, como todos os outros módulos já fazem: este era o único lugar do sistema
// que importava o ECharts (~1 MB) de forma estática, e por isso a Gamificação baixava e
// interpretava a biblioteca inteira antes de conseguir desenhar qualquer coisa (achado medido no
// bundle de produção em 2026-09-03).
const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => <div className="h-[300px] animate-pulse rounded-xl bg-slate-100" aria-label="Carregando gráfico" />,
});

import { ChartPanel, BarComparison } from "@/components/gamification/chart-panel";
import { CATEGORICAL_SLOTS } from "@/lib/chart-palette";
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

  const penaltyData = [...penalties]
    .filter((item) => item.value > 0 || item.service_orders_count > 0)
    .sort((a, b) => b.value - a.value)
    .slice(0, 10)
    .sort((a, b) => a.value - b.value);

  const healthOption = {
    aria: { enabled: true },
    tooltip: { trigger: "axis", confine: true },
    legend: { top: 0, textStyle: { color: "#475569", fontSize: 11 } },
    grid: { left: 8, right: 24, top: 42, bottom: 28, containLabel: true },
    yAxis: { type: "category", inverse: true, data: health.map((item) => regionalName(item.regional).replace(/^UNI\s*-\s*/i, "")), axisLabel: { width: 100, overflow: "truncate", color: "#475569", fontSize: 11 }, axisTick: { show: false }, axisLine: { show: false } },
    xAxis: { type: "value", min: 0, max: 100, axisLabel: { formatter: "{value}%", color: "#64748b", fontSize: 11 }, splitLine: { lineStyle: { color: "#f1f5f9" } } },
    color: [CATEGORICAL_SLOTS[0], CATEGORICAL_SLOTS[7]],
    series: [
      { name: "SLA", type: "bar", barMaxWidth: 12, data: health.map((item) => item.sla_rate), itemStyle: { borderRadius: [0, 3, 3, 0] } },
      { name: "Reincidência", type: "bar", barMaxWidth: 12, data: health.map((item) => item.recurrence_rate), itemStyle: { borderRadius: [0, 3, 3, 0] } }
    ]
  };

  const scatterOption = {
    aria: { enabled: true },
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
    aria: { enabled: true },
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
        // Mesmo motivo do `color` de healthOption acima: série de dado usa o slot categórico, não
        // o azul de marca.
        itemStyle: { color: CATEGORICAL_SLOTS[0], opacity: 0.8, borderColor: "#ffffff", borderWidth: 1 },
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
    <section className="grid min-w-0 gap-4 xl:grid-cols-2" aria-label="Análise visual da gamificação">
      <ChartPanel title="Top 15 por pontos finais" description="Pontuação após anulações, multiplicadores e ajustes de garantia." columns={["Colaborador", "Pontos finais", "Valor a pagar"]} rows={[...rankingData].reverse().map((item) => [item.collaborator_name, formatPoints(item.final_points), formatMoney(item.estimated_payment)])}>
        <BarComparison items={[...rankingData].reverse().map((item) => ({ label: item.collaborator_name, value: item.final_points, formatted: formatPoints(item.final_points), detail: regionalName(item.regional) }))} />
      </ChartPanel>
      <ChartPanel title="Distribuição de pontos anulados" description="Os dez motivos com maior volume de pontos anulados no recorte." columns={["Motivo", "O.S", "Pontos anulados"]} rows={[...penaltyData].reverse().map((item) => [item.name, item.service_orders_count, formatAnnulledPoints(item.value)])}>
        <BarComparison tone="red" items={[...penaltyData].reverse().map((item) => ({ label: item.name, value: item.value, formatted: formatAnnulledPoints(item.value), detail: String(item.service_orders_count) + " O.S" }))} />
      </ChartPanel>
      <ChartPanel title="Saúde da base × pontuação" description="Cada círculo representa uma filial. O tamanho indica o volume de O.S." columns={["Filial", "Saúde / SLA", "Pontos finais", "O.S"]} rows={healthScatterItems.map((item) => [regionalName(item.regional), item.health_score.toFixed(2) + "%", formatPoints(item.final_points), item.total_orders])}>
        <ReactECharts option={healthScatterOption} style={{ height: 320 }} />
      </ChartPanel>
      <ChartPanel title="Produtividade dos colaboradores" description="Volume de O.S e pontos finais. A legenda permite comparar os grupos com e sem reincidência." columns={["Colaborador", "O.S", "Pontos finais", "Reincidências"]} rows={scatterItems.map((item) => [item.collaborator_name, item.service_orders_count, formatPoints(item.final_points), item.recurrence_service_orders ?? item.warranty_service_orders ?? 0])}>
        <ReactECharts option={scatterOption} style={{ height: 320 }} />
      </ChartPanel>
      <ChartPanel className="xl:col-span-2" title="Saúde operacional por filial" description="SLA e reincidência na mesma escala percentual. Consulte os dados para ver todos os nomes e valores." columns={["Filial", "SLA", "Reincidência"]} rows={health.map((item) => [regionalName(item.regional), item.sla_rate.toFixed(2) + "%", item.recurrence_rate.toFixed(2) + "%"])}>
        <div className="max-h-[520px] overflow-y-auto"><ReactECharts option={healthOption} style={{ height: Math.max(280, health.length * 48 + 80) }} /></div>
      </ChartPanel>
    </section>
  );
}
