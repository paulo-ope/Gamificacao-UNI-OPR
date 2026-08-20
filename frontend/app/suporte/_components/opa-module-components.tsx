"use client";

import {
  type LucideIcon,
  ArrowDownRight,
  ArrowUpDown,
  ArrowUpRight,
  BarChart3,
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Database,
  Eye,
  GitBranch,
  Headphones,
  History,
  LayoutDashboard,
  ListFilter,
  Loader2,
  Minus,
  RefreshCw,
  RotateCcw,
  Search,
  Settings2,
  SlidersHorizontal,
  Star,
  Timer,
  TriangleAlert,
  Users,
  X,
} from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DateRangePicker, type DateRangePreset } from "@/components/ui/date-range-picker";
import { Input } from "@/components/ui/input";
import { MultiSelect } from "@/components/ui/multi-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type {
  SupportOpaBreakdownItem,
  SupportOpaBreakdowns,
  SupportOpaAttendanceFilters,
  SupportOpaFilters,
  SupportOpaMetricComparison,
  SupportOpaOverview,
  SupportOpaSyncSettings,
  SupportOpaSyncStatus,
} from "@/lib/types";

export type OpaModuleTab =
  | "overview"
  | "attendants"
  | "data"
  | "sync"
  | "operation"
  | "queues"
  | "agents"
  | "reasons"
  | "hours"
  | "history";

type Period = { date_from: string; date_to: string };

export type OpaNavigationItem = {
  value: OpaModuleTab;
  label: string;
  description: string;
  icon: LucideIcon;
};

export const OPA_NAV_ITEMS: OpaNavigationItem[] = [
  { value: "overview", label: "Visão Geral", description: "Indicadores confiáveis", icon: LayoutDashboard },
  { value: "attendants", label: "Atendentes", description: "Volume por atendente", icon: Users },
  { value: "data", label: "Dados", description: "Tabela analítica", icon: Database },
  { value: "sync", label: "Sincronização", description: "Status do OPA", icon: RefreshCw },
  { value: "operation", label: "Operação", description: "Planejado", icon: BarChart3 },
  { value: "queues", label: "Filas", description: "Planejado", icon: GitBranch },
  { value: "reasons", label: "Motivos", description: "Planejado", icon: ListFilter },
  { value: "hours", label: "Horários", description: "Planejado", icon: Clock3 },
  { value: "history", label: "Histórico", description: "Planejado", icon: History },
];

export const ACTIVE_OPA_TABS: OpaModuleTab[] = ["overview", "attendants", "data", "sync"];

const OPA_STATUS_LABELS: Record<string, string> = {
  AG: "Aguardando atendimento",
  EA: "Em atendimento",
  F: "Finalizado",
  PS: "Pausado",
};

export function opaStatusLabel(value: string | null | undefined) {
  if (!value) return "Não informado";
  return OPA_STATUS_LABELS[value.trim().toUpperCase()] || value;
}

function toDateValue(value: Date) {
  return value.toISOString().slice(0, 10);
}

function utcToday() {
  const now = new Date();
  return new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate(), 12));
}

function addDays(value: Date, amount: number) {
  return new Date(Date.UTC(value.getUTCFullYear(), value.getUTCMonth(), value.getUTCDate() + amount, 12));
}

function monthStart(value: Date) {
  return new Date(Date.UTC(value.getUTCFullYear(), value.getUTCMonth(), 1, 12));
}

function monthEnd(value: Date) {
  return new Date(Date.UTC(value.getUTCFullYear(), value.getUTCMonth() + 1, 0, 12));
}

export function opaPeriodPresets(): DateRangePreset[] {
  return [
    { label: "Hoje", range: () => {
      const today = utcToday();
      return { from: toDateValue(today), to: toDateValue(today) };
    } },
    { label: "Ontem", range: () => {
      const yesterday = addDays(utcToday(), -1);
      return { from: toDateValue(yesterday), to: toDateValue(yesterday) };
    } },
    { label: "Últimos 7 dias", range: () => {
      const today = utcToday();
      return { from: toDateValue(addDays(today, -6)), to: toDateValue(today) };
    } },
    { label: "Últimos 30 dias", range: () => {
      const today = utcToday();
      return { from: toDateValue(addDays(today, -29)), to: toDateValue(today) };
    } },
    { label: "Este mês", range: () => {
      const today = utcToday();
      return { from: toDateValue(monthStart(today)), to: toDateValue(today) };
    } },
    { label: "Mês anterior", range: () => {
      const current = utcToday();
      const previous = new Date(Date.UTC(current.getUTCFullYear(), current.getUTCMonth() - 1, 1, 12));
      return { from: toDateValue(monthStart(previous)), to: toDateValue(monthEnd(previous)) };
    } },
    { label: "Personalizado", range: () => {
      const today = utcToday();
      return { from: toDateValue(monthStart(today)), to: toDateValue(today) };
    } },
  ];
}

export function number(value: number | null | undefined, digits = 0) {
  if (value === null || value === undefined) return "-";
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: digits }).format(value);
}

export function secondsLabel(value: number | null | undefined) {
  if (value === null || value === undefined) return "-";
  if (value < 60) return `${Math.round(value)} s`;
  if (value < 3600) return `${Math.round(value / 60)} min`;
  return `${(value / 3600).toFixed(1).replace(".", ",")} h`;
}

export function dateTimeLabel(value: string | null | undefined) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "America/Porto_Velho",
  }).format(new Date(value));
}

export function comparisonLabel(metric: SupportOpaMetricComparison | null | undefined, formatter: (value: number | null | undefined) => string = number) {
  if (!metric) return "Comparação indisponível";
  if (metric.percentage_change === null) return `Anterior: ${formatter(metric.previous)}`;
  const sign = metric.absolute_change && metric.absolute_change > 0 ? "+" : "";
  return `${sign}${number(metric.percentage_change, 1)}% vs período anterior`;
}

function activeFilterBadges(filters: SupportOpaAttendanceFilters, options: SupportOpaFilters | null) {
  const labelFrom = (items: Array<{ value: string; label: string }> | undefined, value?: string) => {
    const values = splitFilterValues(value);
    if (!values.length) return value;
    return values.map((item) => items?.find((option) => option.value === item)?.label ?? item).join(", ");
  };
  return [
    filters.search ? { key: "search", label: `Busca: ${filters.search}` } : null,
    filters.status ? { key: "status", label: `Status: ${splitFilterValues(filters.status).map(opaStatusLabel).join(", ")}` } : null,
    filters.channel ? { key: "channel", label: `Canal: ${labelFrom(options?.channels, filters.channel)}` } : null,
    filters.attendant_id ? { key: "attendant", label: `Atendente: ${labelFrom(options?.attendants, filters.attendant_id)}` } : null,
    filters.department_id ? { key: "department", label: `Departamento: ${labelFrom(options?.departments, filters.department_id)}` } : null,
    filters.reason_id ? { key: "reason", label: `Motivo: ${labelFrom(options?.reasons, filters.reason_id)}` } : null,
    filters.customer ? { key: "customer", label: `Cliente: ${filters.customer}` } : null,
  ].filter(Boolean) as Array<{ key: string; label: string }>;
}

function splitFilterValues(value?: string) {
  return (value || "").split(",").map((item) => item.trim()).filter(Boolean);
}

export function OpaGlobalFilters({
  period,
  filters,
  options,
  loading,
  canSync,
  syncing,
  canImport,
  onPeriodChange,
  onFilterChange,
  onApply,
  onClear,
  onImport,
}: {
  period: Period;
  filters: SupportOpaAttendanceFilters;
  options: SupportOpaFilters | null;
  loading: boolean;
  canSync: boolean;
  syncing: boolean;
  canImport: boolean;
  onPeriodChange: (period: Period) => void;
  onFilterChange: (patch: Partial<SupportOpaAttendanceFilters>) => void;
  onApply: () => void;
  onClear: () => void;
  onImport: () => void;
}) {
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);
  const badges = activeFilterBadges(filters, options);
  return (
    <section className="contents">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 bg-white px-4 pb-3 pt-3 lg:px-7">
        <div>
          <p className="text-sm font-semibold text-slate-950">Filtros</p>
          <p className="text-xs text-slate-500">O mesmo recorte é aplicado à Visão Geral e aos Dados.</p>
          <Button
            type="button"
            variant="outline"
            onClick={() => setMobileFiltersOpen((current) => !current)}
            aria-expanded={mobileFiltersOpen}
            className="mt-2 h-9 w-full justify-center md:hidden"
          >
            <SlidersHorizontal className="h-4 w-4" />
            {mobileFiltersOpen ? "Ocultar filtros" : "Filtros"}
            {badges.length ? <Badge className="border-blue-100 bg-blue-50 px-1.5 text-blue-700">{badges.length}</Badge> : null}
            <ChevronDown className={`h-4 w-4 transition ${mobileFiltersOpen ? "rotate-180" : ""}`} />
          </Button>
        </div>
        {canSync ? (
          <Button type="button" variant="outline" onClick={onImport} disabled={syncing || loading || !canImport} className="h-9 border-blue-200 text-blue-700 hover:bg-blue-50">
            {syncing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Importar dados
          </Button>
        ) : null}
      </div>

      <div className={`${mobileFiltersOpen ? "grid" : "hidden"} max-h-[calc(100vh-65px)] items-end gap-2 overflow-y-auto border-y border-slate-200 bg-white px-4 py-2 shadow-sm md:sticky md:top-[65px] md:z-20 md:grid md:max-h-none md:grid-cols-2 md:overflow-visible lg:px-7 xl:grid-cols-[14rem_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto]`}>
        <div className="min-w-0">
          <DateRangePicker
            dateFrom={period.date_from}
            dateTo={period.date_to}
            presets={opaPeriodPresets()}
            className="w-full"
            onChange={(key, value) => onPeriodChange({ ...period, [key]: value })}
          />
        </div>
        <FilterMultiSelect label="Atendente" value={filters.attendant_id} options={options?.attendants ?? []} onChange={(value) => onFilterChange({ attendant_id: value, page: 1 })} />
        <FilterMultiSelect label="Departamento" value={filters.department_id} options={options?.departments ?? []} onChange={(value) => onFilterChange({ department_id: value, page: 1 })} />
        <FilterMultiSelect label="Canal" value={filters.channel} options={options?.channels ?? []} onChange={(value) => onFilterChange({ channel: value, page: 1 })} />
        <div className="flex flex-wrap gap-2 xl:flex-nowrap xl:justify-end">
          <Button type="button" onClick={onApply} disabled={loading} className="h-10">
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <CalendarClock className="h-4 w-4" />}
            Filtrar
          </Button>
          <Button type="button" variant="ghost" onClick={onClear} disabled={loading} className="h-10 text-slate-600">
            <RotateCcw className="h-4 w-4" /> Limpar
          </Button>
          <Button type="button" variant="outline" onClick={() => setAdvancedOpen((current) => !current)} aria-expanded={advancedOpen} className="h-10 whitespace-nowrap">
            <SlidersHorizontal className="h-4 w-4" />
            Filtros avançados
            {badges.length ? <Badge className="border-blue-100 bg-blue-50 px-1.5 text-blue-700">{badges.length}</Badge> : null}
            <ChevronDown className={`h-4 w-4 transition ${advancedOpen ? "rotate-180" : ""}`} />
          </Button>
        </div>
        {advancedOpen ? (
          <div className="col-span-full grid gap-3 rounded-xl border border-slate-200 bg-white p-3 shadow-lg md:grid-cols-2 xl:grid-cols-4">
            <label className="grid min-w-0 gap-1.5 text-[11px] font-medium text-slate-600">
              Busca
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
                <Input value={filters.search ?? ""} onChange={(event) => onFilterChange({ search: event.target.value || undefined, page: 1 })} placeholder="Protocolo, cliente ou atendente" className="pl-9" />
              </div>
            </label>
            <div className="grid gap-3 rounded-lg bg-slate-50 p-3 md:grid-cols-2 xl:col-span-3">
              <FilterMultiSelect label="Status" value={filters.status} options={options?.statuses ?? []} formatOption={opaStatusLabel} onChange={(value) => onFilterChange({ status: value, page: 1 })} />
              <FilterMultiSelect label="Motivo" value={filters.reason_id} options={options?.reasons ?? []} onChange={(value) => onFilterChange({ reason_id: value, page: 1 })} />
            </div>
          </div>
        ) : null}
      </div>
      {badges.length ? <div className="border-b border-slate-200 bg-white px-4 pb-3 lg:px-7">
        <div className="mt-2 flex min-h-7 flex-wrap items-center gap-1.5 text-xs text-slate-500">
          <span className="font-medium text-slate-700">{badges.length} filtros aplicados</span>
          {badges.map((item) => (
            <button key={item.key} type="button" onClick={() => onFilterChange({ [item.key === "search" ? "search" : item.key === "attendant" ? "attendant_id" : item.key === "department" ? "department_id" : item.key === "reason" ? "reason_id" : item.key]: undefined, page: 1 })} className="inline-flex max-w-52 items-center gap-1 truncate rounded-full border border-slate-200 bg-slate-50 px-2 py-1 text-[10px] text-slate-700 transition-colors hover:bg-slate-100" title={`Remover ${item.label}`}>
              <span className="truncate">{item.label}</span><X className="h-3 w-3 shrink-0" />
            </button>
          ))}
        </div>
      </div> : null}
    </section>
  );
}

function FilterMultiSelect({ label, value, options, formatOption, onChange }: { label: string; value?: string; options: Array<{ value: string; label: string }>; formatOption?: (value: string) => string; onChange: (value: string | undefined) => void }) {
  return (
    <label className="grid min-w-0 gap-1.5 text-[11px] font-medium text-slate-600">
      {label}
      <MultiSelect
        values={splitFilterValues(value)}
        options={options.map((option) => option.value)}
        formatOption={(selected) => formatOption?.(selected) ?? options.find((option) => option.value === selected)?.label ?? selected}
        ariaLabel={`Filtrar por ${label}`}
        onChange={(values) => onChange(values.join(",") || undefined)}
      />
    </label>
  );
}

export function OpaOverview({ overview }: { overview: SupportOpaOverview | null }) {
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon={Headphones} label="Atendimentos" value={number(overview?.total_attendances.current)} helper={comparisonLabel(overview?.total_attendances)} />
        <MetricCard icon={CheckCircle2} label="Encerrados" value={number(overview?.closed_attendances.current)} helper={comparisonLabel(overview?.closed_attendances)} />
        <MetricCard icon={TriangleAlert} label="Em aberto" value={number(overview?.open_attendances.current)} helper={comparisonLabel(overview?.open_attendances)} />
        <MetricCard icon={Timer} label="Duração média" value={secondsLabel(overview?.average_duration_seconds.current)} helper={comparisonLabel(overview?.average_duration_seconds, secondsLabel)} />
        <MetricCard icon={CheckCircle2} label="Taxa de encerramento" value={`${number(overview?.closure_rate.current, 1)}%`} helper={comparisonLabel(overview?.closure_rate, (value) => `${number(value, 1)}%`)} />
        <MetricCard icon={Star} label="Avaliação média" value={number(overview?.average_rating.current, 2)} helper={comparisonLabel(overview?.average_rating, (value) => number(value, 2))} />
        <MetricCard icon={Headphones} label="Atendentes distintos" value={number(overview?.distinct_attendants.current)} helper={comparisonLabel(overview?.distinct_attendants)} />
        <MetricCard icon={Database} label="Departamentos distintos" value={number(overview?.distinct_departments.current)} helper={comparisonLabel(overview?.distinct_departments)} />
      </div>
      <ChannelSummary items={overview?.by_channel ?? []} />
    </>
  );
}

export function OpaAttendantsPanel({
  breakdown,
  overview,
  loading,
  sortBy,
  sortDir,
  onSort,
  onOpenAttendant,
}: {
  breakdown: SupportOpaBreakdowns | null;
  overview: SupportOpaOverview | null;
  loading: boolean;
  sortBy: string;
  sortDir: "asc" | "desc";
  onSort: (sortBy: string) => void;
  onOpenAttendant: (attendant: SupportOpaBreakdownItem) => void;
}) {
  const items = breakdown?.items ?? [];
  const ratingCount = items.reduce((sum, item) => sum + item.rating_count, 0);
  const totalAttendances = overview?.total_attendances.current ?? breakdown?.total ?? 0;
  const ratingCoverage = totalAttendances ? (ratingCount / totalAttendances) * 100 : null;

  return (
    <div className="grid gap-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
        <MetricCard icon={Users} label="Atendentes ativos" value={number(overview?.distinct_attendants.current)} helper={comparisonLabel(overview?.distinct_attendants)} />
        <MetricCard icon={Headphones} label="Atendimentos" value={number(overview?.total_attendances.current)} helper={comparisonLabel(overview?.total_attendances)} />
        <MetricCard icon={CheckCircle2} label="Taxa de encerramento" value={`${number(overview?.closure_rate.current, 1)}%`} helper={comparisonLabel(overview?.closure_rate, (value) => `${number(value, 1)}%`)} />
        <MetricCard icon={Timer} label="Duração média" value={secondsLabel(overview?.average_duration_seconds.current)} helper={comparisonLabel(overview?.average_duration_seconds, secondsLabel)} />
        <MetricCard icon={Star} label="Avaliação média" value={number(overview?.average_rating.current, 2)} helper={comparisonLabel(overview?.average_rating, (value) => number(value, 2))} />
        <MetricCard icon={Star} label="Cobertura de avaliação" value={ratingCoverage === null ? "-" : `${number(ratingCoverage, 1)}%`} helper={`${number(ratingCount)} avaliação(ões) no ranking`} />
      </div>

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 p-4">
          <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-center gap-2">
              <Users className="h-4 w-4 text-blue-700" />
              <h3 className="text-base font-semibold text-slate-950">Atendentes</h3>
              <Badge className="border-slate-200 bg-slate-50 text-slate-700">{number(items.length)} exibidos</Badge>
            </div>
            <p className="text-xs text-slate-500">Clique no atendente para abrir o detalhe lateral.</p>
          </div>
        </div>

        <div className="grid gap-3 p-4 lg:hidden">
          {loading ? <p className="rounded-lg border border-slate-200 p-6 text-center text-sm text-slate-500">Carregando atendentes...</p> : null}
          {!loading && items.map((item) => (
            <button key={item.id ?? item.label} type="button" disabled={!item.id} onClick={() => item.id && onOpenAttendant(item)} className="rounded-lg border border-slate-200 bg-white p-3 text-left shadow-sm transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-70">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-slate-950">{item.label}</p>
                  <p className="mt-1 text-xs text-slate-500">{number(item.total)} atendimentos · {number(item.share_percentage, 1)}% do volume</p>
                </div>
                <TrendValue value={item.total_change_percentage} suffix="%" />
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                <MiniStat label="Encerramento" value={`${number(item.closure_rate, 1)}%`} />
                <MiniStat label="Duração" value={secondsLabel(item.avg_duration_seconds)} />
                <MiniStat label="Avaliação" value={number(item.avg_rating, 2)} />
                <MiniStat label="Avaliações" value={number(item.rating_count)} />
              </div>
            </button>
          ))}
          {!loading && !items.length ? <p className="rounded-lg border border-slate-200 p-6 text-center text-sm text-slate-500">Nenhum atendente encontrado para os filtros aplicados.</p> : null}
        </div>

        <div className="hidden overflow-x-auto p-4 lg:block">
          <Table className="min-w-[980px]">
            <TableHeader>
              <TableRow>
                <BreakdownHead label="Atendente" column="label" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
                <BreakdownHead label="Volume" column="total" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
                <BreakdownHead label="Encerramento" column="closure_rate" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
                <BreakdownHead label="Duração" column="avg_duration_seconds" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
                <BreakdownHead label="Avaliação" column="avg_rating" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
                <TableHead>Tendências</TableHead>
                <TableHead className="text-right">Ação</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? <TableRow><TableCell colSpan={7} className="py-10 text-center text-sm text-slate-500">Carregando atendentes...</TableCell></TableRow> : null}
              {!loading && items.map((item) => (
                <AttendantBreakdownRow key={item.id ?? item.label} item={item} onOpenAttendant={onOpenAttendant} />
              ))}
              {!loading && !items.length ? (
                <TableRow><TableCell colSpan={7} className="py-10 text-center text-sm text-slate-500">Nenhum atendente encontrado para os filtros aplicados.</TableCell></TableRow>
              ) : null}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}

function MetricCard({ icon: Icon, label, value, helper }: { icon: typeof Headphones; label: string; value: string; helper: string }) {
  return (
    <div className="relative flex min-h-[136px] flex-col overflow-hidden rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <span className="absolute inset-x-0 top-0 h-1 bg-blue-600" />
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs font-medium text-slate-500">{label}</p>
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-700">
          <Icon className="h-4 w-4" />
        </span>
      </div>
      <p className="mt-2 text-3xl font-semibold tabular-nums text-slate-950">{value}</p>
      <p className="mt-auto pt-3 text-xs text-slate-500">{helper}</p>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <span className="rounded-md bg-slate-50 px-2 py-1.5">
      <span className="block text-[10px] font-medium text-slate-500">{label}</span>
      <span className="mt-0.5 block font-semibold tabular-nums text-slate-900">{value}</span>
    </span>
  );
}

function BreakdownHead({
  label,
  column,
  sortBy,
  sortDir,
  align,
  onSort,
}: {
  label: string;
  column: string;
  sortBy: string;
  sortDir: "asc" | "desc";
  align?: "right";
  onSort: (sortBy: string) => void;
}) {
  const active = sortBy === column;
  return (
    <TableHead className={align === "right" ? "text-right" : undefined}>
      <button type="button" onClick={() => onSort(column)} className={`inline-flex items-center gap-1 ${align === "right" ? "justify-end" : ""} ${active ? "text-blue-700" : ""}`}>
        {label}
        <ArrowUpDown className={`h-3.5 w-3.5 ${active && sortDir === "asc" ? "rotate-180" : ""}`} />
      </button>
    </TableHead>
  );
}

function AttendantBreakdownRow({ item, onOpenAttendant }: { item: SupportOpaBreakdownItem; onOpenAttendant: (attendant: SupportOpaBreakdownItem) => void }) {
  const evaluations = item.rating_count ? `${number(item.rating_count)} avaliações` : "Sem avaliações";
  return (
    <TableRow className={item.id ? "group cursor-pointer border-l-2 border-l-transparent hover:border-l-blue-600 hover:bg-slate-50" : ""} onClick={() => item.id && onOpenAttendant(item)}>
      <TableCell className="min-w-72 max-w-80" title={`${item.label} - abrir detalhe lateral`}>
        <div className="flex min-w-0 items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate font-semibold text-slate-950">{item.label}</p>
            <p className="mt-0.5 text-[11px] text-slate-500">{number(item.share_percentage, 1)}% do volume filtrado</p>
          </div>
        </div>
      </TableCell>
      <TableCell>
        <p className="font-semibold tabular-nums text-slate-950">{number(item.total)}</p>
        <p className="mt-0.5 text-[11px] text-slate-500">{number(item.closed)} encerrados · {number(item.open)} abertos</p>
      </TableCell>
      <TableCell>
        <p className="font-semibold tabular-nums text-slate-950">{number(item.closure_rate, 1)}%</p>
        <p className="mt-0.5 text-[11px] text-slate-500">do volume encerrado</p>
      </TableCell>
      <TableCell>
        <p className="font-semibold tabular-nums text-slate-950">{secondsLabel(item.avg_duration_seconds)}</p>
        <p className="mt-0.5 text-[11px] text-slate-500">média dos encerrados</p>
      </TableCell>
      <TableCell>
        <p className="font-semibold tabular-nums text-slate-950">{number(item.avg_rating, 2)}</p>
        <p className="mt-0.5 text-[11px] text-slate-500">{evaluations}</p>
      </TableCell>
      <TableCell>
        <div className="flex flex-wrap gap-1.5">
          <TrendPill label="Vol." value={item.total_change_percentage} suffix="%" />
          <TrendPill label="Enc." value={item.closure_rate_change_pp} suffix=" p.p." />
          <TrendPill label="Dur." value={item.avg_duration_change_percentage} suffix="%" />
          <TrendPill label="Aval." value={item.avg_rating_change} />
        </div>
      </TableCell>
      <TableCell className="text-right">
        {item.id ? (
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-500 transition-colors group-hover:border-blue-200 group-hover:text-blue-700" title="Abrir detalhe lateral">
            <Eye className="h-4 w-4" />
          </span>
        ) : null}
      </TableCell>
    </TableRow>
  );
}

function TrendPill({ label, value, suffix = "" }: { label: string; value: number | null | undefined; suffix?: string }) {
  if (value === null || value === undefined) {
    return <span className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-[11px] text-slate-400">{label}: -</span>;
  }
  const positive = value > 0;
  const negative = value < 0;
  return (
    <span className={`rounded-md border px-2 py-1 text-[11px] font-medium tabular-nums ${positive ? "border-blue-100 bg-blue-50 text-blue-700" : negative ? "border-slate-200 bg-slate-50 text-slate-700" : "border-slate-200 bg-white text-slate-500"}`}>
      {label}: {positive ? "+" : negative ? "-" : ""}{number(Math.abs(value), suffix ? 1 : 2)}{suffix}
    </span>
  );
}

function TrendValue({ value, suffix = "" }: { value: number | null | undefined; suffix?: string }) {
  if (value === null || value === undefined) {
    return <span className="inline-flex items-center justify-end gap-1 text-xs text-slate-400">-</span>;
  }
  const rounded = number(Math.abs(value), suffix === "" ? 2 : 1);
  const positive = value > 0;
  const negative = value < 0;
  const Icon = positive ? ArrowUpRight : negative ? ArrowDownRight : Minus;
  return (
    <span className={`inline-flex items-center justify-end gap-1 text-xs font-semibold tabular-nums ${positive ? "text-blue-700" : negative ? "text-slate-600" : "text-slate-400"}`}>
      <Icon className="h-3.5 w-3.5" />
      {positive ? "+" : negative ? "-" : ""}{rounded}{suffix}
    </span>
  );
}

function ChannelSummary({ items }: { items: Array<{ channel: string; total: number }> }) {
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 p-4">
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-blue-700" />
          <h3 className="text-base font-semibold text-slate-950">Atendimentos por canal</h3>
        </div>
      </div>
      <div className="overflow-x-auto p-4">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Canal</TableHead>
              <TableHead className="text-right">Atendimentos</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.channel}>
                <TableCell className="max-w-64 truncate font-medium text-slate-800" title={item.channel}>{item.channel}</TableCell>
                <TableCell className="text-right tabular-nums">{number(item.total)}</TableCell>
              </TableRow>
            ))}
            {!items.length ? (
              <TableRow>
                <TableCell colSpan={2} className="py-10 text-center text-sm text-slate-500">Nenhum canal encontrado para os filtros atuais.</TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

export function OpaSyncPanel({
  canSync,
  syncStatus,
  settings,
  savingSettings,
  onDraftSettings,
  onSaveSettings,
}: {
  canSync: boolean;
  syncStatus: SupportOpaSyncStatus | null;
  settings: SupportOpaSyncSettings | null;
  savingSettings: boolean;
  onDraftSettings: (next: Partial<SupportOpaSyncSettings>) => void;
  onSaveSettings: (next: Partial<SupportOpaSyncSettings>) => void;
}) {
  if (!canSync) {
    return (
      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-800">
        Seu usuário pode visualizar o SGP, mas não possui permissão support:sync_opa.
      </div>
    );
  }
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-2 text-slate-800">
        <Settings2 className="h-5 w-5" />
        <h3 className="text-base font-semibold">Sincronização do OPA Suite</h3>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <StatusRow label="Configurado" value={syncStatus?.configured ? "Sim" : "Não"} danger={!syncStatus?.configured} />
        <StatusRow label="Última tentativa" value={dateTimeLabel(syncStatus?.last_attempt_at)} />
        <StatusRow label="Último sucesso" value={dateTimeLabel(syncStatus?.last_success_at)} />
        <StatusRow label="Próxima janela" value={dateTimeLabel(syncStatus?.next_allowed_at)} />
        <StatusRow label="Falhas seguidas" value={String(syncStatus?.consecutive_failures ?? 0)} danger={Boolean(syncStatus?.consecutive_failures)} />
        <StatusRow label="Status" value={syncStatus?.enabled ? "Automático ligado" : "Automático desligado"} />
        <StatusRow label="Intervalo" value={`${settings?.interval_minutes ?? 20} min`} />
        <StatusRow label="Reimportação" value={`${settings?.lookback_days ?? 1} dia(s)`} />
      </div>
      {syncStatus?.last_error ? (
        <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-700">
          <div className="mb-1 flex items-center gap-1 font-semibold"><TriangleAlert className="h-3.5 w-3.5" /> Último erro</div>
          {syncStatus.last_error}
        </div>
      ) : null}
      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <label className="flex items-center justify-between rounded-xl border border-slate-200 px-3 py-2 text-sm">
          <span className="font-medium text-slate-700">Automático</span>
          <input
            type="checkbox"
            checked={Boolean(settings?.enabled)}
            disabled={savingSettings || !settings}
            onChange={(event) => onSaveSettings({ enabled: event.target.checked })}
            className="h-4 w-4 rounded border-slate-300"
          />
        </label>
        <label className="block">
          <span className="text-xs font-medium text-slate-600">Intervalo em minutos</span>
          <Input
            type="number"
            min={5}
            max={1440}
            value={settings?.interval_minutes ?? 20}
            disabled={savingSettings || !settings}
            onChange={(event) => onDraftSettings({ interval_minutes: Number(event.target.value) })}
            onBlur={(event) => onSaveSettings({ interval_minutes: Number(event.target.value) })}
          />
        </label>
        <label className="block">
          <span className="text-xs font-medium text-slate-600">Reimportar últimos dias</span>
          <Input
            type="number"
            min={1}
            max={30}
            value={settings?.lookback_days ?? 1}
            disabled={savingSettings || !settings}
            onChange={(event) => onDraftSettings({ lookback_days: Number(event.target.value) })}
            onBlur={(event) => onSaveSettings({ lookback_days: Number(event.target.value) })}
          />
        </label>
      </div>
    </div>
  );
}

function StatusRow({ label, value, danger }: { label: string; value: string; danger?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl border border-slate-100 bg-slate-50 px-3 py-2">
      <span className="text-xs font-medium text-slate-500">{label}</span>
      <span className={`text-right text-xs font-semibold ${danger ? "text-red-700" : "text-slate-800"}`}>{value}</span>
    </div>
  );
}
