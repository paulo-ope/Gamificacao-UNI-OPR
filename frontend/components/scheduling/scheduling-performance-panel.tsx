"use client";

import dynamic from "next/dynamic";
import type { EChartsOption } from "echarts";
import { InfoHint } from "@/components/gamification/info-hint";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SchedulingDashboard } from "@/lib/scheduling-api";

import { minutesLabel, number } from "./scheduling-format";

const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => <div className="h-[240px] animate-pulse rounded-xl bg-slate-100" aria-label="Carregando gráfico" />,
});

// Desempenho de SLA/tempo de resposta - análise SECUNDÁRIA do cockpit (pedido do usuário
// 2026-08-31: o calendário de reagendamentos é a peça central; este painel de tempo até agendar
// fica numa aba própria, não mais na primeira dobra).
export function SchedulingPerformancePanel({
  dashboard,
  onOpenSlaLate,
  onOpenTtfaBucket,
}: {
  dashboard: SchedulingDashboard | null;
  onOpenSlaLate: () => void;
  onOpenTtfaBucket: (bucket: string, count: number) => void;
}) {
  const summary = dashboard?.summary;
  const slaTone = summary?.sla_rate === null || summary?.sla_rate === undefined ? "text-slate-700" : summary.sla_met ? "text-emerald-700" : "text-red-700";

  const distributionOption: EChartsOption = {
    color: ["#2563eb"],
    tooltip: { trigger: "axis" },
    grid: { left: 40, right: 16, top: 16, bottom: 40 },
    xAxis: { type: "category", data: (dashboard?.ttfa_distribution || []).map((item) => item.label), axisLabel: { fontSize: 10, interval: 0 } },
    yAxis: { type: "value" },
    series: [{ name: "O.S.", type: "bar", barMaxWidth: 42, data: (dashboard?.ttfa_distribution || []).map((item) => item.count) }],
  };

  function handleDistributionClick(clickParams: { componentType?: string; dataIndex?: number }) {
    if (clickParams.componentType !== "series" || clickParams.dataIndex === undefined) return;
    const bucket = dashboard?.ttfa_distribution[clickParams.dataIndex];
    if (!bucket || !bucket.count) return;
    onOpenTtfaBucket(bucket.bucket, bucket.count);
  }

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
        <CardHeader className="pb-2">
          <span className="flex items-center gap-1.5">
            <CardTitle className="text-base font-semibold text-slate-950">SLA de agendamento</CardTitle>
            <InfoHint
              ariaLabel="Como é calculado o SLA"
              side="bottom"
              title="Como é calculado"
              description="Percentual das O.S. abertas no período que receberam o primeiro agendamento dentro do prazo, contando só o tempo útil do expediente do setor."
            />
          </span>
          <p className="text-xs text-slate-500">
            Prazo: agendar em até {minutesLabel(summary?.sla_minutes ?? null)} · meta {number(summary?.sla_target_pct, "%")}
          </p>
        </CardHeader>
        <CardContent className="px-4 pb-4">
          <div className="grid grid-cols-2 gap-3 text-center sm:grid-cols-4">
            <div>
              <p className={`text-2xl font-semibold tabular-nums ${slaTone}`}>{number(summary?.sla_rate, "%")}</p>
              <button type="button" onClick={onOpenSlaLate} className="mt-1 text-[11px] text-blue-700 hover:underline" disabled={!summary?.scheduled_orders}>
                Ver atrasadas
              </button>
            </div>
            <div>
              <p className="text-2xl font-semibold tabular-nums text-slate-900">{minutesLabel(summary?.ttfa_business.median)}</p>
              <p className="mt-1 text-[11px] text-slate-500">Mediana (útil)</p>
            </div>
            <div>
              <p className="text-2xl font-semibold tabular-nums text-slate-900">{minutesLabel(summary?.ttfa_business.p90)}</p>
              <p className="mt-1 text-[11px] text-slate-500">P90 (útil)</p>
            </div>
            <div>
              <p className="text-2xl font-semibold tabular-nums text-slate-900">{minutesLabel(summary?.ttfa_raw.median)}</p>
              <p className="mt-1 text-[11px] text-slate-500">Mediana (corrido)</p>
            </div>
          </div>
        </CardContent>
      </Card>
      <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
        <CardHeader className="pb-0">
          <CardTitle className="text-base font-semibold text-slate-950">Distribuição do tempo até agendar</CardTitle>
          <p className="text-xs text-slate-500">Em horas úteis do expediente do setor.</p>
        </CardHeader>
        <CardContent className="px-2 pb-2 pt-1 sm:px-4">
          <ReactECharts
            option={distributionOption}
            notMerge
            lazyUpdate
            style={{ height: 240, width: "100%" }}
            onEvents={{ click: handleDistributionClick }}
          />
          <p className="px-2 pb-1 text-[11px] text-slate-400">Clique numa barra para ver as O.S. dessa faixa.</p>
        </CardContent>
      </Card>
    </div>
  );
}
