"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import type { EChartsOption } from "echarts";
import { AlertTriangle, ArrowRight, Clock3, Gauge, Inbox, TrendingUp, X } from "lucide-react";

import { InfoHint } from "@/components/gamification/info-hint";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type {
  OpeningsDrillField,
  OpeningsDrillTarget,
  OperationOpeningsAnalytics,
  OperationOpeningsRankingItem,
  OperationOrderPage,
  OperationTrendGranularity,
} from "@/lib/operations-api";

const GRANULARITIES: Array<{ value: OperationTrendGranularity; label: string }> = [
  { value: "day", label: "Dia" },
  { value: "week", label: "Semana" },
  { value: "month", label: "Mês" },
];

const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => <div className="h-[300px] animate-pulse rounded-xl bg-slate-100" aria-label="Carregando gráfico" />,
});

const WEEKDAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];
const RANKING_LABELS: Record<string, string> = {
  regionals: "Filiais",
  cities: "Cidades",
  subjects: "Assuntos",
  os_types: "Tipos",
  sectors: "Setores",
  priorities: "Prioridades",
  creators: "Criadores",
  pops: "POPs",
  contract_types: "Tipos de contrato",
  person_types: "Tipos de pessoa",
};

function number(value: number | null | undefined, suffix = "") {
  if (value === null || value === undefined) return "—";
  return `${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(value)}${suffix}`;
}

function ratio(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

function minutes(value: number | null) {
  if (value === null) return "—";
  if (value < 60) return `${number(value)} min`;
  return `${number(value / 60)} h`;
}

function addDaysIso(iso: string, days: number) {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day + days)).toISOString().slice(0, 10);
}

function endOfMonthIso(iso: string) {
  const [year, month] = iso.split("-").map(Number);
  return new Date(Date.UTC(year, month, 0)).toISOString().slice(0, 10);
}

function brDate(iso: string) {
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

function insightClass(severity: string) {
  if (severity === "critical") return "border-red-200 bg-red-50 text-red-800";
  if (severity === "attention") return "border-amber-200 bg-amber-50 text-amber-800";
  if (severity === "insufficient") return "border-slate-200 bg-slate-50 text-slate-700";
  return "border-cyan-200 bg-cyan-50 text-cyan-800";
}

function MetricCard({ title, value, helper, tone = "blue" }: { title: string; value: string | number; helper: string; tone?: "blue" | "cyan" | "amber" | "red" | "slate" }) {
  const accentClass = {
    blue: "bg-blue-600",
    cyan: "bg-cyan-500",
    amber: "bg-amber-500",
    red: "bg-red-600",
    slate: "bg-slate-400",
  }[tone];
  return (
    <div className="relative overflow-hidden rounded-xl bg-white p-4 shadow-sm">
      <span className={`absolute inset-x-0 top-0 h-1 ${accentClass}`} />
      <p className="text-xs font-medium text-slate-500">{title}</p>
      <p className="mt-2 text-3xl font-semibold tabular-nums text-slate-950">{value}</p>
      <p className="mt-2 text-xs text-slate-600">{helper}</p>
    </div>
  );
}

type RankingSortKey = "opened" | "backlog" | "share_percentage";

const RANKING_SORT_OPTIONS: Array<{ key: RankingSortKey; label: string }> = [
  { key: "opened", label: "Abertas" },
  { key: "backlog", label: "Em aberto" },
  { key: "share_percentage", label: "Share" },
];

const RANKING_VISIBLE_DEFAULT = 6;

function RankingTable({ title, items, onDrill }: { title: string; items: OperationOpeningsRankingItem[]; onDrill?: (label: string) => void }) {
  const [sort, setSort] = useState<{ key: RankingSortKey; direction: "asc" | "desc" }>({
    key: "opened",
    direction: "desc",
  });
  const [expanded, setExpanded] = useState(false);
  const sortedItems = useMemo(() => {
    const copy = [...items];
    copy.sort((a, b) => (sort.direction === "asc" ? a[sort.key] - b[sort.key] : b[sort.key] - a[sort.key]));
    return copy;
  }, [items, sort]);
  const visibleItems = expanded ? sortedItems : sortedItems.slice(0, RANKING_VISIBLE_DEFAULT);
  const hiddenCount = sortedItems.length - visibleItems.length;
  function toggleSort(key: RankingSortKey) {
    setSort((current) =>
      current.key === key
        ? { key, direction: current.direction === "asc" ? "desc" : "asc" }
        : { key, direction: "desc" },
    );
  }
  return (
    <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
      <CardHeader className="flex-row items-center justify-between gap-2 pb-2">
        <CardTitle className="text-sm font-semibold text-slate-900">{title}</CardTitle>
        <div className="flex shrink-0 gap-0.5 rounded-lg bg-slate-50 p-0.5" aria-label={`Ordenar ${title}`}>
          {RANKING_SORT_OPTIONS.map((option) => (
            <button
              key={option.key}
              type="button"
              onClick={() => toggleSort(option.key)}
              className={`rounded-md px-1.5 py-1 text-[10px] font-medium transition-colors ${
                sort.key === option.key ? "bg-white text-slate-900 shadow-sm" : "text-slate-400 hover:text-slate-600"
              }`}
            >
              {option.label}
              {sort.key === option.key ? (sort.direction === "asc" ? " ↑" : " ↓") : ""}
            </button>
          ))}
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-3 pt-0">
        {visibleItems.length ? (
          <div className="divide-y divide-slate-100">
            {visibleItems.map((item) => (
              <div key={item.label} className="flex items-center justify-between gap-3 py-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-800">{item.label}</p>
                  <p className="text-xs text-slate-500">
                    {number(item.share_percentage, "%")} do total
                    {item.backlog ? ` · ${number(item.backlog)} ainda em aberto` : ""}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <span className="text-sm font-semibold tabular-nums text-slate-900">{number(item.opened)}</span>
                  {onDrill ? (
                    <Button type="button" size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => onDrill(item.label)} aria-label={`Ver O.S. de ${item.label}`}>
                      <ArrowRight className="h-3.5 w-3.5" />
                    </Button>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="py-6 text-center text-sm text-slate-500">Sem dados para este ranking.</p>
        )}
        {sortedItems.length > RANKING_VISIBLE_DEFAULT ? (
          <button
            type="button"
            onClick={() => setExpanded((current) => !current)}
            className="mt-1 text-xs font-medium text-blue-700 hover:text-blue-900"
          >
            {expanded ? "Mostrar menos" : `Mostrar mais ${hiddenCount}`}
          </button>
        ) : null}
      </CardContent>
    </Card>
  );
}

function drillPanelHeading(target: OpeningsDrillTarget) {
  if (target.kind === "dimension") return { eyebrow: RANKING_LABELS[target.field] || target.field, title: target.value };
  if (target.kind === "aging") return { eyebrow: "Envelhecimento do backlog", title: target.label };
  return { eyebrow: "Mapa de calor", title: target.label };
}

function DrillPanel({
  target,
  orders,
  isLoading,
  onClose,
}: {
  target: OpeningsDrillTarget;
  orders?: OperationOrderPage;
  isLoading: boolean;
  onClose?: () => void;
}) {
  const items = orders?.items || [];
  const heading = drillPanelHeading(target);
  return (
    <Card className="rounded-2xl border-blue-200 bg-blue-50/40 shadow-sm">
      <CardHeader className="flex-row items-center justify-between gap-4 pb-2">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-blue-600">
            {heading.eyebrow}
          </p>
          <CardTitle className="text-base font-semibold text-slate-950">{heading.title}</CardTitle>
          <p className="text-xs text-slate-500">
            {orders ? `${orders.total} O.S. no recorte de abertura` : "Carregando..."}
            {orders && orders.total > items.length ? ` · mostrando as ${items.length} mais recentes` : ""}
          </p>
        </div>
        <Button type="button" size="sm" variant="ghost" onClick={onClose} aria-label="Fechar detalhamento">
          <X className="h-4 w-4" /> Fechar
        </Button>
      </CardHeader>
      <CardContent className="px-0">
        {isLoading ? (
          <div className="mx-4 h-40 animate-pulse rounded-xl bg-white" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>O.S.</TableHead>
                <TableHead>Cliente</TableHead>
                <TableHead>Responsável</TableHead>
                <TableHead>Abertura</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.length ? (
                items.map((order) => (
                  <TableRow key={order.id}>
                    <TableCell className="font-medium text-slate-800">{order.order_code}</TableCell>
                    <TableCell className="max-w-56 truncate">{order.customer_name || "Cliente não identificado"}</TableCell>
                    <TableCell>{order.responsible || "Sem responsável"}</TableCell>
                    <TableCell>{new Date(order.opened_at).toLocaleString("pt-BR")}</TableCell>
                    <TableCell>{order.status || "—"}</TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={5} className="py-8 text-center text-sm text-slate-500">
                    Nenhuma O.S. encontrada para este recorte.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

export function OperationsOpeningsAnalytics({
  data,
  isLoading,
  onOpenOrders,
  onOpenAgingBucket,
  onOpenHeatmapSlot,
  drill,
  drillOrders,
  drillLoading,
  onCloseDrill,
  granularity = "day",
  onGranularityChange,
  temporaryPeriod,
  onSelectPeriod,
  onClearPeriod,
}: {
  data: OperationOpeningsAnalytics;
  isLoading: boolean;
  onOpenOrders?: (field: OpeningsDrillField, value: string) => void;
  onOpenAgingBucket?: (bucket: string, label: string) => void;
  onOpenHeatmapSlot?: (weekday: number, hour: number, label: string) => void;
  drill?: OpeningsDrillTarget | null;
  drillOrders?: OperationOrderPage;
  drillLoading?: boolean;
  onCloseDrill?: () => void;
  granularity?: OperationTrendGranularity;
  onGranularityChange?: (granularity: OperationTrendGranularity) => void;
  temporaryPeriod?: { label: string; date_from: string; date_to: string } | null;
  onSelectPeriod?: (dateFrom: string, dateTo: string, label: string) => void;
  onClearPeriod?: () => void;
}) {
  const flowCardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!temporaryPeriod || !onClearPeriod) return;
    function handlePointerDown(event: MouseEvent) {
      if (flowCardRef.current && !flowCardRef.current.contains(event.target as Node)) {
        onClearPeriod?.();
      }
    }
    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [temporaryPeriod, onClearPeriod]);

  function handleTimelineClick(params: { componentType?: string; dataIndex?: number }) {
    if (!onSelectPeriod || params.componentType !== "series" || params.dataIndex === undefined) return;
    const point = data.timeline[params.dataIndex];
    if (!point) return;
    let dateTo = point.date;
    if (data.granularity === "week") dateTo = addDaysIso(point.date, 6);
    else if (data.granularity === "month") dateTo = endOfMonthIso(point.date);
    if (dateTo > data.date_to) dateTo = data.date_to;
    if (temporaryPeriod && temporaryPeriod.date_from === point.date && temporaryPeriod.date_to === dateTo) {
      onClearPeriod?.();
      return;
    }
    onSelectPeriod(point.date, dateTo, `${brDate(point.date)} - ${brDate(dateTo)}`);
  }

  function handleAgingClick(params: { componentType?: string; dataIndex?: number }) {
    if (!onOpenAgingBucket || params.componentType !== "series" || params.dataIndex === undefined) return;
    const item = data.aging[params.dataIndex];
    if (!item) return;
    onOpenAgingBucket(item.bucket, item.label);
  }

  function handleHeatmapClick(params: { componentType?: string; value?: unknown }) {
    if (!onOpenHeatmapSlot || params.componentType !== "series" || !Array.isArray(params.value)) return;
    const [hour, weekdayIndex] = params.value as [number, number, number];
    const weekday = weekdayIndex + 1;
    onOpenHeatmapSlot(weekday, hour, `${WEEKDAYS[weekdayIndex]} · ${hour}h`);
  }

  const averageOpened = data.timeline.length
    ? data.timeline.reduce((total, item) => total + item.opened, 0) / data.timeline.length
    : 0;

  const timelineOption: EChartsOption = {
    color: ["#2563eb", "#10b981", "#7c3aed", "#f59e0b"],
    tooltip: { trigger: "axis" },
    legend: { top: 0 },
    grid: { left: 36, right: 24, top: 48, bottom: 32 },
    xAxis: { type: "category", data: data.timeline.map((item) => item.date.slice(5)) },
    yAxis: { type: "value" },
    series: [
      {
        name: "Abertas",
        type: "bar",
        data: data.timeline.map((item) => item.opened),
        barMaxWidth: 22,
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { color: "#94a3b8", type: "dashed" },
          label: { formatter: `Média: ${number(averageOpened)}`, color: "#64748b", fontSize: 10 },
          data: [{ type: "average", name: "Média" }],
        },
      },
      { name: "Finalizadas", type: "line", smooth: true, data: data.timeline.map((item) => item.completed) },
      { name: "Backlog", type: "line", smooth: true, data: data.timeline.map((item) => item.backlog) },
      { name: "Esperado", type: "line", smooth: true, lineStyle: { type: "dashed" }, data: data.timeline.map((item) => item.expected_opened) },
    ],
  };

  const heatmapOption: EChartsOption = {
    tooltip: { position: "top", confine: true },
    // Legenda de cores fica vertical à direita - horizontal embaixo (padrão antigo) disputava o
    // mesmo espaço da faixa de horas do eixo X e acabava cobrindo os rótulos "0h".."23h".
    grid: { left: 38, right: 64, top: 18, bottom: 28 },
    xAxis: { type: "category", data: Array.from({ length: 24 }, (_, hour) => `${hour}h`) },
    yAxis: { type: "category", data: WEEKDAYS },
    visualMap: {
      min: 0,
      max: Math.max(1, ...data.heatmap.map((item) => item.opened)),
      orient: "vertical",
      right: 4,
      top: "middle",
      itemHeight: 120,
      inRange: { color: ["#ecfeff", "#38bdf8", "#1d4ed8"] },
    },
    series: [{
      name: "Aberturas",
      type: "heatmap",
      data: data.heatmap.map((item) => [item.hour, item.weekday - 1, item.opened]),
      emphasis: { itemStyle: { shadowBlur: 8, shadowColor: "rgba(15, 23, 42, 0.25)" } },
    }],
  };

  const agingOption: EChartsOption = {
    color: ["#2563eb"],
    tooltip: { trigger: "axis" },
    grid: { left: 32, right: 16, top: 16, bottom: 28 },
    xAxis: { type: "category", data: data.aging.map((item) => item.label) },
    yAxis: { type: "value" },
    series: [{
      name: "O.S. abertas",
      type: "bar",
      data: data.aging.map((item) => item.quantity),
      barMaxWidth: 36,
      markLine: {
        silent: true,
        symbol: "none",
        lineStyle: { color: "#94a3b8", type: "dashed" },
        label: { formatter: "Média", color: "#64748b", fontSize: 10 },
        data: [{ type: "average", name: "Média" }],
      },
    }],
  };

  return (
    <div aria-busy={isLoading} className="space-y-4">
      <section className="rounded-2xl border border-blue-100 bg-gradient-to-br from-white via-cyan-50/50 to-blue-50 p-4 shadow-sm sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <Badge className="border-cyan-200 bg-cyan-50 text-cyan-800"><Inbox className="mr-1 h-3.5 w-3.5" /> Aberturas</Badge>
            <h2 className="mt-3 text-xl font-semibold text-slate-950">Entrada de demanda operacional</h2>
            <p className="mt-1 max-w-3xl text-sm text-slate-600">
              Acompanhe picos, desvios, origem da demanda e risco de acúmulo antes de avaliar produtividade da equipe.
            </p>
          </div>
          <p className="max-w-md rounded-xl border border-blue-100 bg-white/80 p-3 text-xs text-slate-500">{data.calculation_note}</p>
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard title="Abertas no período" value={number(data.summary.opened)} helper={`Média diária: ${number(data.summary.average_daily_opened)}`} />
        <MetricCard title="Desvio esperado" value={number(data.summary.deviation_percentage, "%")} helper={`Esperado: ${number(data.summary.expected_opened)} O.S.`} tone={data.summary.deviation_percentage && data.summary.deviation_percentage > 25 ? "amber" : "cyan"} />
        <MetricCard title="Pressão operacional" value={ratio(data.summary.pressure_ratio)} helper={`Abertas − finalizadas: ${data.summary.net_flow > 0 ? "+" : ""}${number(data.summary.net_flow)} O.S.`} tone={data.summary.net_flow > 0 ? "amber" : "blue"} />
        <MetricCard title="Backlog no recorte" value={number(data.summary.backlog)} helper={`${number(data.summary.overdue_backlog)} vencidas · ${number(data.summary.without_responsible)} sem responsável`} tone={data.summary.overdue_backlog ? "red" : "slate"} />
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.35fr_0.65fr]">
        <Card ref={flowCardRef} className="rounded-2xl border-slate-200 bg-white shadow-sm">
          <CardHeader className="flex-row items-start justify-between gap-3 pb-0">
            <div>
              <p className="text-[9px] font-bold uppercase tracking-[0.18em] text-blue-600">Fluxo operacional</p>
              <span className="flex items-center gap-1.5">
                <CardTitle className="text-base font-semibold text-slate-950">Aberturas, finalizações e backlog</CardTitle>
                <InfoHint
                  ariaLabel="Ajuda sobre a linha Esperado"
                  side="right"
                  title="Como o Esperado é calculado"
                  description={`Para cada dia, pega o mesmo dia da semana nas últimas ${data.baseline_weeks} semanas e tira a média de aberturas - essa média é a linha "Esperado". O limite de atenção (usado para marcar picos) fica acima da média: o maior entre "média + 2x o desvio", "média x 1,35" e "média + 2".`}
                />
              </span>
              <p className="text-xs text-slate-500">
                {onSelectPeriod ? "Clique numa barra para ver o detalhe daquele recorte; clique fora do gráfico para voltar. " : ""}
                Linha esperada compara o mesmo dia da semana nas últimas {data.baseline_weeks} semanas.
              </p>
            </div>
            {onGranularityChange ? (
              <div className="flex shrink-0 rounded-lg border border-slate-200 bg-slate-50 p-1" aria-label="Agrupamento do gráfico de aberturas">
                {GRANULARITIES.map((item) => (
                  <Button
                    key={item.value}
                    type="button"
                    size="sm"
                    variant={granularity === item.value ? "default" : "ghost"}
                    className="h-7 px-3 text-xs"
                    disabled={isLoading}
                    onClick={() => onGranularityChange(item.value)}
                  >
                    {item.label}
                  </Button>
                ))}
              </div>
            ) : null}
          </CardHeader>
          {temporaryPeriod ? (
            <div className="mx-4 mt-2 flex items-center justify-between gap-2 rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs text-blue-900">
              <span>
                Filtro temporário: <strong>{temporaryPeriod.label}</strong> · clique na barra de novo ou fora do gráfico para voltar
              </span>
              <button type="button" onClick={onClearPeriod} className="font-medium underline">
                Voltar
              </button>
            </div>
          ) : null}
          <CardContent className="px-2 pb-2 pt-1 sm:px-4">
            <ReactECharts
              option={timelineOption}
              notMerge
              lazyUpdate
              opts={{ renderer: "canvas" }}
              style={{ height: 320, width: "100%" }}
              onEvents={onSelectPeriod ? { click: handleTimelineClick } : undefined}
            />
          </CardContent>
        </Card>

        <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
          <CardHeader className="pb-2">
            <p className="text-[9px] font-bold uppercase tracking-[0.18em] text-blue-600">Leitura rápida</p>
            <CardTitle className="text-base font-semibold text-slate-950">Insights da gestão</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {data.insights.length ? data.insights.map((item) => (
              <div key={`${item.title}-${item.description}`} className={`rounded-xl border p-3 ${insightClass(item.severity)}`}>
                <p className="flex items-center gap-2 text-sm font-semibold">
                  {item.severity === "critical" || item.severity === "attention" ? <AlertTriangle className="h-4 w-4" /> : <Gauge className="h-4 w-4" />}
                  {item.title}
                </p>
                <p className="mt-1 text-xs opacity-80">{item.description}</p>
              </div>
            )) : (
              <p className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">Sem insight automático para o recorte atual.</p>
            )}
            <div className="rounded-xl border border-cyan-100 bg-cyan-50 p-3 text-xs text-cyan-900">
              <Clock3 className="mb-1 h-4 w-4" />
              Tempo médio até primeira ação: <strong>{minutes(data.summary.average_first_action_minutes)}</strong>
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
          <CardHeader className="pb-0">
            <CardTitle className="text-base font-semibold text-slate-950">Mapa de calor de abertura</CardTitle>
            <p className="text-xs text-slate-500">
              Mostra em quais dias e horários a demanda nasce com mais força.
              {onOpenHeatmapSlot ? " Clique numa célula para ver o detalhe; clique de novo para fechar." : ""}
            </p>
          </CardHeader>
          <CardContent className="px-2 pb-2 pt-1 sm:px-4">
            <ReactECharts
              option={heatmapOption}
              notMerge
              lazyUpdate
              opts={{ renderer: "canvas" }}
              style={{ height: 300, width: "100%" }}
              onEvents={onOpenHeatmapSlot ? { click: handleHeatmapClick } : undefined}
            />
          </CardContent>
        </Card>

        <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
          <CardHeader className="pb-0">
            <CardTitle className="text-base font-semibold text-slate-950">Envelhecimento do backlog gerado</CardTitle>
            <p className="text-xs text-slate-500">
              O.S. abertas no período que seguem sem fechamento.
              {onOpenAgingBucket ? " Clique numa barra para ver o detalhe; clique de novo para fechar." : ""}
            </p>
          </CardHeader>
          <CardContent className="px-2 pb-2 pt-1 sm:px-4">
            <ReactECharts
              option={agingOption}
              notMerge
              lazyUpdate
              opts={{ renderer: "canvas" }}
              style={{ height: 300, width: "100%" }}
              onEvents={onOpenAgingBucket ? { click: handleAgingClick } : undefined}
            />
          </CardContent>
        </Card>
      </section>

      {drill ? (
        <DrillPanel
          target={drill}
          orders={drillOrders}
          isLoading={Boolean(drillLoading)}
          onClose={onCloseDrill}
        />
      ) : null}

      <div className="flex items-center gap-1.5 px-1">
        <p className="text-sm font-semibold text-slate-900">Rankings de abertura</p>
        <InfoHint
          ariaLabel="Ajuda sobre Em aberto"
          side="right"
          title="O que é “Em aberto”"
          description="Quantas O.S. desse grupo ainda não foram fechadas até o fim do período selecionado (o estoque atual, não uma diferença). É diferente do card “Pressão operacional”, que mostra abertas menos finalizadas no período - aqui é sempre uma contagem de O.S. que seguem pendentes."
        />
      </div>

      <section className="grid gap-4 xl:grid-cols-2 2xl:grid-cols-3">
        {Object.entries(RANKING_LABELS).map(([key, label]) => (
          <RankingTable
            key={key}
            title={`Top ${label.toLowerCase()}`}
            items={data.rankings[key] || []}
            onDrill={onOpenOrders ? (value) => onOpenOrders(key as OpeningsDrillField, value) : undefined}
          />
        ))}
      </section>

      <div className="rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-600 shadow-sm">
        <TrendingUp className="mb-2 h-4 w-4 text-blue-600" />
        Use os rankings para investigar causa provável: assunto mostra natureza da demanda, regional/cidade mostra concentração territorial e criador/setor ajuda a entender origem operacional.
      </div>
    </div>
  );
}
