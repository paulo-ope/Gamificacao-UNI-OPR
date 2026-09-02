"use client";

import dynamic from "next/dynamic";
import type { EChartsOption } from "echarts";
import { useEffect, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { schedulingApi, type SchedulingFilterState, type SchedulingRescheduleDayBreakdown } from "@/lib/scheduling-api";

const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => <div className="h-[160px] animate-pulse rounded-xl bg-slate-100" aria-label="Carregando gráfico" />,
});

export function rankingOption(items: { label: string; count: number }[], color: string): EChartsOption {
  const ordered = [...items].reverse(); // echarts desenha a 1ª categoria de baixo pra cima
  return {
    color: [color],
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    grid: { left: 8, right: 24, top: 8, bottom: 8, containLabel: true },
    xAxis: { type: "value", show: false },
    yAxis: { type: "category", data: ordered.map((item) => item.label), axisLabel: { fontSize: 11 }, axisLine: { show: false }, axisTick: { show: false } },
    series: [{ type: "bar", barMaxWidth: 16, data: ordered.map((item) => item.count), label: { show: true, position: "right", fontSize: 11 } }],
  };
}

// Ranking "quem cobrar hoje" - substitui as listas de texto por barras horizontais (pedido do
// usuário 2026-08-31: "bater o olho e ver o padrão"). Escopado pelo dia (`event_at`), não pelo mês
// em navegação - reagendamentos são sempre lidos "hoje", igual ao resto do painel.
export function SchedulingDayBreakdownCharts({
  day,
  filters,
}: {
  day: string;
  filters: SchedulingFilterState;
}) {
  const [data, setData] = useState<SchedulingRescheduleDayBreakdown | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    schedulingApi
      .reschedulesBreakdown(day, filters, controller.signal)
      .then(setData)
      .catch((reason) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Falha ao carregar o ranking do dia.");
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [day, filters.date_from, filters.date_to, filters.filial_ids, filters.setor_ids, filters.assunto_ids, filters.operator_ids, filters.technician_ids]);

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
        <CardHeader className="pb-1">
          <CardTitle className="text-sm font-semibold text-slate-950">Técnicos — mais reagendamento hoje</CardTitle>
        </CardHeader>
        <CardContent className="px-3 pb-3">
          {error ? <p className="text-xs text-red-600">{error}</p> : null}
          {loading ? (
            <div className="h-40 animate-pulse rounded-xl bg-slate-100" />
          ) : data?.by_technician.length ? (
            <ReactECharts option={rankingOption(data.by_technician, "#eb6834")} notMerge lazyUpdate style={{ height: Math.max(120, data.by_technician.length * 28), width: "100%" }} />
          ) : (
            <p className="py-6 text-center text-xs text-slate-400">Nenhum reagendamento de técnico hoje.</p>
          )}
        </CardContent>
      </Card>
      <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
        <CardHeader className="pb-1">
          <CardTitle className="text-sm font-semibold text-slate-950">Filiais — mais reagendamento hoje</CardTitle>
        </CardHeader>
        <CardContent className="px-3 pb-3">
          {loading ? (
            <div className="h-40 animate-pulse rounded-xl bg-slate-100" />
          ) : data?.by_filial.length ? (
            <ReactECharts option={rankingOption(data.by_filial, "#2563eb")} notMerge lazyUpdate style={{ height: Math.max(120, data.by_filial.length * 28), width: "100%" }} />
          ) : (
            <p className="py-6 text-center text-xs text-slate-400">Nenhum reagendamento hoje.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
