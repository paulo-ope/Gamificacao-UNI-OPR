"use client";

import dynamic from "next/dynamic";
import type { EChartsOption } from "echarts";
import { BarChart3, GitBranch, Loader2, TrendingUp } from "lucide-react";
import type { ReactNode } from "react";

import {
  buildBotHumanDonutOption,
  buildRankingOption,
  buildTimeTrendOption,
  buildVolumeTrendOption,
} from "@/lib/support-chart-options";
import type {
  SupportOpaBotHumanMetrics,
  SupportOpaBreakdownItem,
  SupportOpaTimeseriesPoint,
} from "@/lib/types";

// `ssr: false` porque o ECharts toca `window` no import — mesmo padrão já usado
// em components/operations/operations-trend-chart.tsx.
const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => <div className="h-[240px] animate-pulse rounded-xl bg-slate-100" aria-label="Carregando gráfico" />,
});

function ChartPanel({
  title,
  icon: Icon,
  action,
  loading,
  isEmpty,
  emptyLabel,
  height = 240,
  children,
}: {
  title: string;
  icon: typeof BarChart3;
  action?: ReactNode;
  loading?: boolean;
  isEmpty?: boolean;
  emptyLabel: string;
  height?: number;
  children: ReactNode;
}) {
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between gap-2 border-b border-slate-100 bg-slate-50/60 px-4 py-3">
        <div className="flex items-center gap-2">
          <Icon className="h-3.5 w-3.5 text-blue-600" />
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">{title}</h3>
        </div>
        {action}
      </div>
      {loading ? (
        <div className="flex items-center justify-center gap-2 text-sm text-slate-500" style={{ height }}>
          <Loader2 className="h-4 w-4 animate-spin" /> Carregando...
        </div>
      ) : isEmpty ? (
        <div className="flex items-center justify-center px-6 text-center text-sm text-slate-500" style={{ height }}>
          {emptyLabel}
        </div>
      ) : (
        <div className="px-1 py-2">{children}</div>
      )}
    </div>
  );
}

function Chart({ option, height, onSlice }: { option: EChartsOption; height: number; onSlice?: (index: number) => void }) {
  return (
    <ReactECharts
      option={option}
      notMerge
      lazyUpdate
      opts={{ renderer: "canvas" }}
      style={{ height, width: "100%" }}
      onEvents={
        onSlice
          ? {
              click: (params: { dataIndex?: number }) => {
                if (typeof params?.dataIndex === "number") onSlice(params.dataIndex);
              },
            }
          : undefined
      }
    />
  );
}

export function VolumeTrendChart({
  points,
  loading,
  onSelectDay,
}: {
  points: SupportOpaTimeseriesPoint[];
  loading: boolean;
  onSelectDay?: (point: SupportOpaTimeseriesPoint) => void;
}) {
  // Um dia sem atendimento continua na série (o backend preenche com zero), mas
  // uma série INTEIRA zerada não é um gráfico — é um recorte vazio.
  const hasVolume = points.some((point) => point.total > 0);
  return (
    <ChartPanel
      title="Volume por dia"
      icon={BarChart3}
      loading={loading}
      isEmpty={!hasVolume}
      emptyLabel="Nenhum atendimento no recorte atual."
      action={onSelectDay ? <span className="text-[10px] text-slate-400">clique num dia para detalhar</span> : undefined}
    >
      <Chart
        option={buildVolumeTrendOption(points)}
        height={240}
        onSlice={onSelectDay ? (index) => points[index] && onSelectDay(points[index]) : undefined}
      />
    </ChartPanel>
  );
}

export function TimeTrendChart({ points, loading }: { points: SupportOpaTimeseriesPoint[]; loading: boolean }) {
  const hasAnyTime = points.some(
    (point) =>
      point.average_duration_seconds !== null ||
      point.average_tmr_seconds !== null ||
      point.average_tmr_all_responses_seconds !== null,
  );
  return (
    <ChartPanel
      title="Tempos por dia"
      icon={TrendingUp}
      loading={loading}
      isEmpty={!hasAnyTime}
      emptyLabel="Sem tempo calculado para os dias deste recorte."
    >
      <Chart option={buildTimeTrendOption(points)} height={240} />
    </ChartPanel>
  );
}

export function RankingChart({
  title,
  items,
  loading,
  onSelect,
}: {
  title: string;
  items: SupportOpaBreakdownItem[];
  loading: boolean;
  onSelect?: (item: SupportOpaBreakdownItem) => void;
}) {
  const top = items.slice(0, 8);
  return (
    <ChartPanel
      title={title}
      icon={BarChart3}
      loading={loading}
      isEmpty={!top.length}
      emptyLabel="Nada a ranquear no recorte atual."
      height={230}
      action={onSelect ? <span className="text-[10px] text-slate-400">clique para detalhar</span> : undefined}
    >
      <Chart
        option={buildRankingOption(items)}
        height={230}
        onSlice={
          onSelect
            ? (index) => {
                // `buildRankingOption` inverte a ordem pra desenhar o maior no
                // topo — o índice do clique precisa ser desinvertido aqui.
                const item = top[top.length - 1 - index];
                if (item) onSelect(item);
              }
            : undefined
        }
      />
    </ChartPanel>
  );
}

export function BotHumanChart({ metrics, loading }: { metrics: SupportOpaBotHumanMetrics | null; loading: boolean }) {
  const classified = metrics?.classified_attendances ?? 0;
  return (
    <ChartPanel
      title="Bot vs. humano"
      icon={GitBranch}
      loading={loading}
      isEmpty={!metrics || classified === 0}
      emptyLabel="Nenhum atendimento classificado neste recorte."
      height={230}
    >
      <Chart
        option={buildBotHumanDonutOption(
          metrics?.with_bot_percentage ?? null,
          classified,
          metrics?.total_attendances ?? 0,
        )}
        height={230}
      />
    </ChartPanel>
  );
}
