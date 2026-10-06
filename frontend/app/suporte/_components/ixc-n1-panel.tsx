"use client";

import dynamic from "next/dynamic";
import type { EChartsOption } from "echarts";
import { AlertTriangle, CalendarDays, ChevronDown, Users } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { CHART_INK } from "@/lib/chart-palette";
import { openingAnomalyThreshold } from "@/lib/operations-chart-options";
import type { SupportIxcN1DailyPoint, SupportIxcN1Summary } from "@/lib/types";

// Suporte Interno N1 (pedido do usuário, 2026-10-06): protocolos do IXC abertos por colaboradores do
// grupos 105 e 117, separados em operacional (motivo 90) e financeiro (motivo 29). Toda a regra de quem é N1
// e de qual motivo é qual vive no backend (`ixc_n1.py`) - esta tela só exibe o resultado.

const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => <div className="h-[280px] animate-pulse rounded-2xl bg-slate-100" aria-label="Carregando gráfico" />,
});

function number(value: number) {
  return new Intl.NumberFormat("pt-BR").format(value);
}

function localIso(date: Date) {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

function monthStartIso() {
  const now = new Date();
  return localIso(new Date(now.getFullYear(), now.getMonth(), 1));
}

function daysAgoIso(days: number) {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return localIso(date);
}

function dayLabel(iso: string) {
  const [, month, day] = iso.split("-");
  return `${day}/${month}`;
}

// Variação contra o período anterior de mesmo tamanho. Sem base anterior não há percentual honesto.
function deltaHelper(current: number, previous: number) {
  if (previous === 0) return current === 0 ? "Sem protocolos no período anterior" : "Sem base no período anterior";
  const pct = ((current - previous) / previous) * 100;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(pct)}% vs. período anterior (${number(previous)})`;
}

function KpiTile({ label, value, helper, accent }: { label: string; value: string; helper: string; accent: string }) {
  return (
    <div className="relative overflow-hidden rounded-2xl bg-white p-4 shadow-sm">
      <span className={`absolute inset-x-0 top-0 h-1 ${accent}`} />
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-2 text-3xl font-bold tabular-nums text-slate-950">{value}</p>
      <p className="mt-1.5 text-xs text-slate-500">{helper}</p>
    </div>
  );
}

// Mesmo desenho do fluxo diário da Visão Geral de Operações (`buildOverviewOpeningsTrendOption`, em
// lib/overview-chart-options.ts), pedido do usuário (2026-10-06): barras com o total do dia (rosa
// quando o dia foge muito do padrão), uma linha por tipo e uma linha tracejada com o total do período
// anterior. As duas séries vêm do backend com um ponto por dia, então o alinhamento é por posição
// (dia 1 com dia 1), nunca por data.
function buildDailyOption(points: SupportIxcN1DailyPoint[], previous: SupportIxcN1DailyPoint[]): EChartsOption {
  const labels = points.map((point) => dayLabel(point.day));
  const totals = points.map((point) => point.operational + point.financial);
  const threshold = openingAnomalyThreshold(totals);
  const previousTotals = previous.map((point) => point.operational + point.financial);

  const series: NonNullable<EChartsOption["series"]> = [
    {
      name: "Total N1",
      type: "bar",
      data: totals.map((value) => ({
        value,
        itemStyle: { color: value > threshold ? "#fb7185" : "#93c5fd", borderRadius: [7, 7, 0, 0] },
      })),
      barMaxWidth: 34,
    },
    {
      name: "Operacional",
      type: "line",
      data: points.map((point) => point.operational),
      smooth: 0.2,
      symbolSize: 6,
      lineStyle: { color: "#16a34a", width: 2.5 },
      itemStyle: { color: "#16a34a" },
    },
    {
      name: "Financeiro",
      type: "line",
      data: points.map((point) => point.financial),
      smooth: 0.2,
      symbolSize: 6,
      lineStyle: { color: "#f59e0b", width: 2.5 },
      itemStyle: { color: "#f59e0b" },
    },
  ];
  if (previousTotals.length) {
    series.push({
      name: "Total (período anterior)",
      type: "line",
      data: labels.map((_, index) => previousTotals[index] ?? null),
      connectNulls: false,
      smooth: 0.2,
      symbolSize: 4,
      lineStyle: { color: CHART_INK.muted, width: 2, type: "dashed" },
      itemStyle: { color: CHART_INK.muted },
      emphasis: { focus: "series" },
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
      appendToBody: true,
      formatter: (params: unknown) => {
        const items = Array.isArray(params) ? params : [params];
        const index = Number((items[0] as { dataIndex?: number } | undefined)?.dataIndex ?? 0);
        const point = points[index];
        if (!point) return "";
        const lines = [
          `<strong>${labels[index]}</strong>`,
          `Total N1: ${number(totals[index])}`,
          `Operacional: ${number(point.operational)}`,
          `Financeiro: ${number(point.financial)}`,
        ];
        if (previousTotals.length) {
          const previousValue = previousTotals[index];
          lines.push(`Total (período anterior): ${previousValue === undefined ? "-" : number(previousValue)}`);
        }
        return lines.join("<br/>");
      },
    },
    legend: { top: 8, right: 8, itemWidth: 10, itemHeight: 8, textStyle: { color: "#475569", fontSize: 10 } },
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

const PRESETS = [
  { key: "month", label: "Mês atual", range: () => ({ date_from: monthStartIso(), date_to: localIso(new Date()) }) },
  { key: "7d", label: "Últimos 7 dias", range: () => ({ date_from: daysAgoIso(6), date_to: localIso(new Date()) }) },
  { key: "30d", label: "Últimos 30 dias", range: () => ({ date_from: daysAgoIso(29), date_to: localIso(new Date()) }) },
] as const;

// A tabela por atendente começa recolhida (só os de maior volume) pra não ficar longa demais - pedido
// do usuário (2026-10-06); o botão abaixo da tabela expande/recolhe a lista completa.
const COLLAPSED_ATTENDANT_COUNT = 5;

export function IxcN1Panel() {
  const [period, setPeriod] = useState(() => PRESETS[0].range());
  const [showAllAttendants, setShowAllAttendants] = useState(false);
  const [summary, setSummary] = useState<SupportIxcN1Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const invalidPeriod = !period.date_from || !period.date_to || period.date_to < period.date_from;

  useEffect(() => {
    if (invalidPeriod) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .supportIxcN1Summary(period)
      .then((data) => {
        if (!cancelled) setSummary(data);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Falha ao carregar o Suporte Interno N1.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [period, invalidPeriod]);

  const activePreset = PRESETS.find((preset) => {
    const range = preset.range();
    return range.date_from === period.date_from && range.date_to === period.date_to;
  })?.key;

  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-200 bg-white px-3 py-2 shadow-sm">
        <CalendarDays className="h-4 w-4 text-slate-400" aria-hidden />
        <div className="flex rounded-lg border border-slate-200 bg-slate-50 p-1">
          {PRESETS.map((preset) => (
            <button
              key={preset.key}
              type="button"
              onClick={() => setPeriod(preset.range())}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${activePreset === preset.key ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
            >
              {preset.label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1.5 text-xs text-slate-500">
          De
          <input
            type="date"
            value={period.date_from}
            max={period.date_to || undefined}
            onChange={(event) => setPeriod((current) => ({ ...current, date_from: event.target.value }))}
            className="h-8 rounded-md border border-slate-200 bg-white px-2 text-sm text-slate-700"
          />
        </label>
        <label className="flex items-center gap-1.5 text-xs text-slate-500">
          Até
          <input
            type="date"
            value={period.date_to}
            min={period.date_from || undefined}
            onChange={(event) => setPeriod((current) => ({ ...current, date_to: event.target.value }))}
            className="h-8 rounded-md border border-slate-200 bg-white px-2 text-sm text-slate-700"
          />
        </label>
      </div>

      {invalidPeriod ? (
        <div className="flex items-center gap-2 rounded-2xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 shadow-sm">
          <AlertTriangle className="h-4 w-4" aria-hidden /> Informe um período válido: a data final não pode ser anterior à inicial.
        </div>
      ) : error ? (
        <div role="alert" className="flex items-center gap-2 rounded-2xl border border-red-200 bg-red-50 p-3 text-sm text-red-700 shadow-sm">
          <AlertTriangle className="h-4 w-4" aria-hidden /> {error}
        </div>
      ) : loading || !summary ? (
        <div aria-busy className="grid gap-5">
          <div className="grid gap-3 sm:grid-cols-3">
            {Array.from({ length: 3 }).map((_, index) => (
              <div key={index} className="h-28 animate-pulse rounded-2xl bg-slate-100" />
            ))}
          </div>
          <div className="h-72 animate-pulse rounded-2xl bg-slate-100" />
          <div className="h-64 animate-pulse rounded-2xl bg-slate-100" />
        </div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <KpiTile
              label="Operacional"
              value={number(summary.operational)}
              helper={deltaHelper(summary.operational, summary.previous_operational)}
              accent="bg-blue-600"
            />
            <KpiTile
              label="Financeiro"
              value={number(summary.financial)}
              helper={deltaHelper(summary.financial, summary.previous_financial)}
              accent="bg-amber-500"
            />
            <KpiTile
              label="Total N1"
              value={number(summary.total)}
              helper={deltaHelper(summary.total, summary.previous_operational + summary.previous_financial)}
              accent="bg-emerald-600"
            />
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
            <p className="mb-3 text-sm font-semibold text-slate-900">Protocolos por dia</p>
            {summary.total > 0 ? (
              <ReactECharts option={buildDailyOption(summary.daily, summary.previous_daily)} notMerge lazyUpdate style={{ height: 280, width: "100%" }} />
            ) : (
              <p className="py-10 text-center text-sm text-slate-500">Nenhum protocolo do N1 no período.</p>
            )}
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
            <div className="mb-3 flex items-center gap-2">
              <Users className="h-4 w-4 text-blue-600" aria-hidden />
              <div>
                <p className="text-sm font-semibold text-slate-900">Por atendente</p>
                <p className="text-xs text-slate-500">Colaboradores {summary.group_ids.length === 1 ? "do grupo" : "dos grupos"} {summary.group_ids.join(" e ")} do IXC que abriram protocolos no período.</p>
              </div>
            </div>
            {summary.attendants.length ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[420px] text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                      <th className="py-2 pr-3 font-medium">Atendente</th>
                      <th className="px-3 py-2 text-right font-medium">Operacional</th>
                      <th className="px-3 py-2 text-right font-medium">Financeiro</th>
                      <th className="py-2 pl-3 text-right font-medium">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(showAllAttendants ? summary.attendants : summary.attendants.slice(0, COLLAPSED_ATTENDANT_COUNT)).map((attendant) => (
                      <tr key={attendant.user_id} className="border-b border-slate-100 last:border-0">
                        <td className="py-2 pr-3 text-slate-800">
                          {attendant.name}
                          {!attendant.active ? (
                            <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium uppercase text-slate-500">
                              Inativo
                            </span>
                          ) : null}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums text-slate-700">{number(attendant.operational)}</td>
                        <td className="px-3 py-2 text-right tabular-nums text-slate-700">{number(attendant.financial)}</td>
                        <td className="py-2 pl-3 text-right font-semibold tabular-nums text-slate-900">{number(attendant.total)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {summary.attendants.length > COLLAPSED_ATTENDANT_COUNT ? (
                  <button
                    type="button"
                    aria-expanded={showAllAttendants}
                    onClick={() => setShowAllAttendants((current) => !current)}
                    className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 py-2 text-xs font-medium text-slate-600 transition hover:bg-slate-100"
                  >
                    {showAllAttendants ? "Mostrar menos" : `Mostrar todos os ${summary.attendants.length} atendentes`}
                    <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showAllAttendants ? "rotate-180" : ""}`} aria-hidden />
                  </button>
                ) : null}
              </div>
            ) : (
              <p className="py-6 text-center text-sm text-slate-500">Nenhum atendente do N1 abriu protocolos no período.</p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
