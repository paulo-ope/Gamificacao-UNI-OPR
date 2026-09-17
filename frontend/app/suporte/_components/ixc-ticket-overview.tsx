"use client";

import dynamic from "next/dynamic";
import type { EChartsOption } from "echarts";
import { AlertTriangle, CalendarDays, ChevronRight, Gauge, Loader2, TrendingDown, TrendingUp } from "lucide-react";
import type { ComponentType } from "react";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type {
  SupportIxcTicketDailyPoint,
  SupportIxcTicketOverviewKpis,
  SupportIxcTicketPriorityItem,
  SupportIxcTicketSeverity,
} from "@/lib/types";

const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => <div className="h-[280px] animate-pulse rounded-2xl bg-slate-100" aria-label="Carregando gráfico" />,
});

function number(value: number | null | undefined, digits = 0) {
  if (value === null || value === undefined) return "-";
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: digits }).format(value);
}

function signedPct(value: number | null | undefined) {
  if (value === null || value === undefined) return "-";
  const sign = value > 0 ? "+" : "";
  return `${sign}${number(value, 1)}%`;
}

const SEVERITY_LABEL: Record<SupportIxcTicketSeverity, string> = {
  critico: "CRÍTICO",
  dentro_da_curva: "DENTRO DA CURVA",
  em_melhora: "EM MELHORA",
  sem_dado: "SEM DADO",
};

// Mesmo vocabulário de tom usado no resto do sistema (neutral/success/warning/danger - ver
// `MetricCard` em components/gamification/config-ui.tsx e `OverviewMetricCard` em
// app/operacao/page.tsx, ambos padronizados por pedido do usuário): CRÍTICO é a única cor de
// alerta de verdade, EM MELHORA é a boa notícia.
const SEVERITY_TONE: Record<SupportIxcTicketSeverity, "neutral" | "success" | "danger"> = {
  critico: "danger",
  dentro_da_curva: "neutral",
  em_melhora: "success",
  sem_dado: "neutral",
};

const SEVERITY_ICON: Record<SupportIxcTicketSeverity, ComponentType<{ className?: string }>> = {
  critico: AlertTriangle,
  dentro_da_curva: Gauge,
  em_melhora: TrendingDown,
  sem_dado: Gauge,
};

const SEVERITY_ROW_CLASS: Record<SupportIxcTicketSeverity, string> = {
  critico: "border-red-200 bg-red-50 hover:bg-red-100/70",
  dentro_da_curva: "border-slate-200 bg-white hover:bg-slate-50",
  em_melhora: "border-emerald-200 bg-emerald-50 hover:bg-emerald-100/70",
  sem_dado: "border-slate-200 bg-slate-50 hover:bg-slate-100/70",
};

const SEVERITY_ICON_CLASS: Record<SupportIxcTicketSeverity, string> = {
  critico: "text-red-600",
  dentro_da_curva: "text-slate-400",
  em_melhora: "text-emerald-600",
  sem_dado: "text-slate-400",
};

function currentMonthIso() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`;
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

// Card de KPI padronizado do sistema: barra de destaque no topo por tom, valor grande, sem ícone
// (mesmo padrão de `MetricCard`/`OverviewMetricCard` - decisão do usuário de unificar o visual
// entre módulos em vez de cada tela inventar o próprio card).
function KpiTile({
  label,
  value,
  helper,
  tone = "neutral",
}: {
  label: string;
  value: string;
  helper: string;
  tone?: "neutral" | "success" | "danger";
}) {
  const toneClass = {
    neutral: "bg-white text-slate-950",
    success: "bg-emerald-50 text-emerald-950",
    danger: "bg-red-50 text-red-950",
  }[tone];
  const accentClass = {
    neutral: "bg-blue-600",
    success: "bg-emerald-600",
    danger: "bg-red-600",
  }[tone];

  return (
    <div className={`relative overflow-hidden rounded-2xl p-4 shadow-sm ${toneClass}`}>
      <span className={`absolute inset-x-0 top-0 h-1 ${accentClass}`} />
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-2 text-3xl font-bold tabular-nums">{value}</p>
      <p className="mt-1.5 text-xs text-slate-500">{helper}</p>
    </div>
  );
}

function buildDailyIncidenceOption(points: SupportIxcTicketDailyPoint[]): EChartsOption {
  const labels = points.map((p) => String(p.day));
  return {
    animationDuration: 300,
    color: ["#2563eb", "#94a3b8", "#f59e0b", "#059669"],
    grid: { left: 44, right: 16, top: 34, bottom: 26 },
    legend: { top: 0, right: 0, itemWidth: 10, itemHeight: 8, textStyle: { color: "#475569", fontSize: 10 } },
    tooltip: {
      trigger: "axis",
      backgroundColor: "#0f172a",
      borderWidth: 0,
      textStyle: { color: "#f8fafc", fontSize: 11 },
      appendToBody: true,
    },
    xAxis: {
      type: "category",
      name: "Dia do mês",
      nameLocation: "middle",
      nameGap: 22,
      nameTextStyle: { color: "#94a3b8", fontSize: 10 },
      data: labels,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#e2e8f0" } },
      axisLabel: { color: "#64748b", fontSize: 10 },
    },
    yAxis: {
      type: "value",
      splitLine: { lineStyle: { color: "#f1f5f9" } },
      axisLabel: { color: "#64748b", fontSize: 10 },
    },
    series: [
      { name: "Mês atual", type: "line", data: points.map((p) => p.current), symbolSize: 5, smooth: false },
      {
        name: "Mês anterior",
        type: "line",
        data: points.map((p) => p.previous_month),
        lineStyle: { type: "dashed" },
        symbol: "none",
      },
      { name: "Média histórica", type: "line", data: points.map((p) => p.historical_avg), symbol: "none", smooth: true },
      { name: "Média móvel 7d", type: "line", data: points.map((p) => p.moving_avg_7d), symbol: "none", smooth: true },
    ],
  };
}

export function IxcTicketOverviewPanel({
  onSelectRegional,
  subjectIds = [],
  sectorIds = [],
}: {
  onSelectRegional: (regional: string) => void;
  subjectIds?: string[];
  sectorIds?: string[];
}) {
  const [month] = useState(currentMonthIso);
  // "Ver só um dia específico" (pedido do usuário, 2026-09-12): null = KPIs acumulados do mês
  // até hoje (comportamento padrão); com uma data, os KPIs/prioridades passam a contar só aquele
  // dia. O gráfico de curva diária continua mostrando o mês inteiro como contexto - não faz
  // sentido "cortar" um gráfico de série temporal a um ponto só.
  const [day, setDay] = useState<string | null>(null);
  const [kpis, setKpis] = useState<SupportIxcTicketOverviewKpis | null>(null);
  const [series, setSeries] = useState<SupportIxcTicketDailyPoint[]>([]);
  const [priorities, setPriorities] = useState<SupportIxcTicketPriorityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    // Mesmo filtro de motivo/setor da barra compartilhada (ver page.tsx) - pedido do usuário
    // (2026-09-12): não pode valer só no drill-down, os KPIs/gráfico/prioridades também precisam
    // refletir o recorte escolhido.
    const subject_id = subjectIds.join(",") || undefined;
    const sector_id = sectorIds.join(",") || undefined;
    Promise.all([
      api.supportIxcTicketOverview({ month, subject_id, sector_id, day: day ?? undefined }),
      api.supportIxcTicketDailySeries({ month, subject_id, sector_id }),
      api.supportIxcTicketPriorities({ month, subject_id, sector_id, day: day ?? undefined }),
    ])
      .then(([kpisData, seriesData, prioritiesData]) => {
        if (cancelled) return;
        setKpis(kpisData);
        setSeries(seriesData);
        setPriorities(prioritiesData);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setError(reason instanceof Error ? reason.message : "Falha ao carregar a visão geral.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [month, subjectIds, sectorIds, day]);

  if (loading) {
    return (
      <div aria-busy className="grid gap-5">
        <div className="h-14 animate-pulse rounded-2xl bg-slate-100" />
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-28 animate-pulse rounded-2xl bg-slate-100" />
          ))}
        </div>
        <div className="h-72 animate-pulse rounded-2xl bg-slate-100" />
        <div className="h-64 animate-pulse rounded-2xl bg-slate-100" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-2 rounded-2xl border border-red-200 bg-red-50 p-3 text-sm text-red-700 shadow-sm">
        <AlertTriangle className="h-4 w-4" /> {error}
      </div>
    );
  }

  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-200 bg-white px-3 py-2 shadow-sm">
        <CalendarDays className="h-4 w-4 text-slate-400" />
        <div className="flex rounded-lg border border-slate-200 bg-slate-50 p-1">
          <button
            type="button"
            onClick={() => setDay(null)}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${day === null ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
          >
            Mês inteiro
          </button>
          <button
            type="button"
            onClick={() => setDay((current) => current ?? todayIso())}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${day !== null ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
          >
            Dia específico
          </button>
        </div>
        {day !== null ? (
          <input
            type="date"
            value={day}
            max={todayIso()}
            onChange={(event) => setDay(event.target.value)}
            className="h-8 rounded-md border border-slate-200 bg-white px-2 text-sm text-slate-700"
          />
        ) : null}
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <KpiTile
          label="Incidência parcial"
          value={kpis?.incidencia_parcial !== null && kpis?.incidencia_parcial !== undefined ? `${number(kpis.incidencia_parcial, 1)} / 1.000` : "-"}
          helper={
            day !== null
              ? `${number(kpis?.ticket_count)} atendimento(s) · dia ${kpis?.cutoff_day ?? "-"}`
              : `${number(kpis?.ticket_count)} atendimento(s) · até dia ${kpis?.cutoff_day ?? "-"}`
          }
        />
        <KpiTile
          label="Média histórica"
          value={kpis?.media_historica !== null && kpis?.media_historica !== undefined ? `${number(kpis.media_historica, 1)} / 1.000` : "-"}
          helper={
            day !== null
              ? `Últimos ${kpis?.history_months_used ?? 0} mês(es) · mesmo dia-do-mês`
              : `Últimos ${kpis?.history_months_used ?? 0} mês(es) · mesmo corte até dia ${kpis?.cutoff_day ?? "-"}`
          }
        />
        <KpiTile
          label="Desvio da curva"
          value={signedPct(kpis?.desvio_pct)}
          helper={kpis ? SEVERITY_LABEL[kpis.severity] : "-"}
          tone={kpis ? SEVERITY_TONE[kpis.severity] : "neutral"}
        />
        <KpiTile
          label="Base ativa comparável"
          value={number(kpis?.contract_count)}
          helper={kpis?.coverage_pct !== null && kpis?.coverage_pct !== undefined ? `Cobertura: ${number(kpis.coverage_pct, 1)}%` : "Cobertura indisponível"}
        />
      </div>

      {kpis?.taxonomy_coverage_pct !== null && kpis?.taxonomy_coverage_pct !== undefined && kpis.taxonomy_coverage_pct < 100 ? (
        <div className="flex items-center gap-2 rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 shadow-sm">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>
            {number(kpis.taxonomy_coverage_pct, 1)}% dos atendimentos deste recorte têm motivo com tema mapeado — o
            restante caiu em "Não mapeado" e precisa de revisão da taxonomia.
          </span>
        </div>
      ) : null}

      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
        <div className="mb-3 flex items-center gap-2">
          <TrendingUp className="h-4 w-4 text-blue-600" />
          <p className="text-sm font-semibold text-slate-900">Curva diária de incidência</p>
        </div>
        {series.length ? (
          <ReactECharts option={buildDailyIncidenceOption(series)} notMerge lazyUpdate style={{ height: 280, width: "100%" }} />
        ) : (
          <p className="py-10 text-center text-sm text-slate-500">Sem dado suficiente para o gráfico.</p>
        )}
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
        <div className="mb-3 flex items-center gap-2">
          <Gauge className="h-4 w-4 text-blue-600" />
          <div>
            <p className="text-sm font-semibold text-slate-900">Prioridades detectadas</p>
            <p className="text-xs text-slate-500">Clique em uma linha para aprofundar a leitura.</p>
          </div>
        </div>
        <div className="grid gap-2">
          {!priorities.length ? (
            <p className="py-6 text-center text-sm text-slate-500">Sem prioridades detectadas no período.</p>
          ) : (
            priorities.map((item) => {
              const Icon = SEVERITY_ICON[item.severity];
              return (
                <button
                  key={item.regional}
                  type="button"
                  onClick={() => onSelectRegional(item.regional)}
                  className={`flex items-center justify-between gap-3 rounded-xl border p-3 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md ${SEVERITY_ROW_CLASS[item.severity]}`}
                >
                  <div className="flex items-center gap-3">
                    <Icon className={`h-4 w-4 shrink-0 ${SEVERITY_ICON_CLASS[item.severity]}`} />
                    <div>
                      <p className="text-sm font-semibold text-slate-900">{item.regional}</p>
                      <p className="text-xs text-slate-500">{item.category}</p>
                      <p className={`text-[11px] font-semibold ${SEVERITY_ICON_CLASS[item.severity]}`}>{SEVERITY_LABEL[item.severity]}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="text-right">
                      <p className="text-sm font-semibold text-slate-900">
                        {item.incidencia_parcial !== null ? `${number(item.incidencia_parcial, 1)} / 1.000` : "-"}
                      </p>
                      <p className="text-xs text-slate-500">
                        {item.severity_basis === "none" ? (
                          "Sem base de comparação suficiente"
                        ) : item.severity_basis === "peers" ? (
                          <>
                            {signedPct(item.historical_deviation_pct)} vs. histórico ·{" "}
                            <span className="font-semibold text-slate-700">{signedPct(item.peers_deviation_pct)} vs. pares</span>
                            {" "}(sem histórico suficiente)
                          </>
                        ) : (
                          <>
                            {signedPct(item.historical_deviation_pct)} vs. histórico · {signedPct(item.peers_deviation_pct)} vs. pares
                          </>
                        )}
                      </p>
                    </div>
                    <ChevronRight className="h-4 w-4 shrink-0 text-slate-300" />
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
