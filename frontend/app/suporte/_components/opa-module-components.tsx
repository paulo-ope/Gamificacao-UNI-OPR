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
import { type ReactNode, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DateRangePicker, type DateRangePreset } from "@/components/ui/date-range-picker";
import { Input } from "@/components/ui/input";
import { MultiSelect } from "@/components/ui/multi-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { secondsLabel } from "@/lib/format-duration";
import type {
  SupportOpaBotHumanMetrics,
  SupportOpaBreakdownItem,
  SupportOpaBreakdowns,
  SupportOpaAttendanceFilters,
  SupportOpaAttendantOverride,
  SupportOpaAttendantOverrideCreate,
  SupportOpaFilters,
  SupportOpaMetricComparison,
  SupportOpaOverview,
  SupportOpaReasonMetric,
  SupportOpaRecurringCustomer,
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

const SUPPORT_TIMEZONE = "America/Porto_Velho";

function toDateValue(value: Date) {
  return value.toISOString().slice(0, 10);
}

// "Hoje" precisa ser o dia corrente no fuso operacional da UNI, não no fuso do
// navegador de quem está olhando a tela nem em UTC — ver
// docs/plano-analise-opa-suite-atendimentos.md, seção "fuso horário".
function localToday() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: SUPPORT_TIMEZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const lookup = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return new Date(Date.UTC(Number(lookup.year), Number(lookup.month) - 1, Number(lookup.day), 12));
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
      const today = localToday();
      return { from: toDateValue(today), to: toDateValue(today) };
    } },
    { label: "Ontem", range: () => {
      const yesterday = addDays(localToday(), -1);
      return { from: toDateValue(yesterday), to: toDateValue(yesterday) };
    } },
    { label: "Últimos 7 dias", range: () => {
      const today = localToday();
      return { from: toDateValue(addDays(today, -6)), to: toDateValue(today) };
    } },
    { label: "Últimos 30 dias", range: () => {
      const today = localToday();
      return { from: toDateValue(addDays(today, -29)), to: toDateValue(today) };
    } },
    { label: "Este mês", range: () => {
      const today = localToday();
      return { from: toDateValue(monthStart(today)), to: toDateValue(today) };
    } },
    { label: "Mês anterior", range: () => {
      const current = localToday();
      const previous = new Date(Date.UTC(current.getUTCFullYear(), current.getUTCMonth() - 1, 1, 12));
      return { from: toDateValue(monthStart(previous)), to: toDateValue(monthEnd(previous)) };
    } },
    { label: "Personalizado", range: () => {
      const today = localToday();
      return { from: toDateValue(monthStart(today)), to: toDateValue(today) };
    } },
  ];
}

export function number(value: number | null | undefined, digits = 0) {
  if (value === null || value === undefined) return "-";
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: digits }).format(value);
}

export { secondsLabel };

export function dateTimeLabel(value: string | null | undefined) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: SUPPORT_TIMEZONE,
  }).format(new Date(value));
}

// Nunca mostrar o código bruto do cliente como texto principal — cai pro
// mesmo fallback amigável em toda tela que exibe cliente. Ver
// docs/auditoria-divergencia-opa-suite-2026-08-25.md.
export function customerNameLabel(customerName?: string | null, customerId?: string | null) {
  const name = customerName?.trim();
  if (name) return name;
  return customerId?.trim() ? "Cliente sem nome cadastrado" : "Cliente não informado";
}

export function customerCodeLabel(customerId?: string | null) {
  const id = customerId?.trim();
  return id ? `Código do cliente: ${id}` : "";
}

// Mensagens de lock ocupado (ver `opa_ingestion._opa_import_busy_message` no
// backend) — condição esperada quando um ciclo com busca de mensagem por
// atendimento (TMR) ainda está rodando quando o próximo tenta começar. Não é
// uma falha de verdade, só não deve assustar o usuário como se fosse.
export function isTransientBusyMessage(message: string) {
  return message.includes("em andamento") && (message.includes("Aguarde") || message.includes("aguarde"));
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
    filters.date_basis === "closed_at" ? { key: "date_basis", label: "Data usada: Encerramento" } : null,
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
              Data usada
              <select
                value={filters.date_basis ?? "opened_at"}
                onChange={(event) => onFilterChange({ date_basis: event.target.value as "opened_at" | "closed_at", page: 1 })}
                className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700"
              >
                <option value="opened_at">Abertura</option>
                <option value="closed_at">Encerramento</option>
              </select>
            </label>
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

function OverviewSection({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <section>
      <div className="mb-2.5 flex items-baseline gap-2">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
        {description ? <span className="text-[11px] text-slate-400">{description}</span> : null}
      </div>
      {children}
    </section>
  );
}

// Célula sem borda própria — usada dentro de painéis com `divide-x`/`divide-y`,
// pra evitar a "grade de cards repetidos" (cada estatística não é mais um card
// individual com moldura e sombra, só uma coluna de um painel maior).
export function StatCell({
  label,
  value,
  helper,
  trend,
  trendSuffix = "%",
  size = "md",
}: {
  label: string;
  value: string;
  helper?: string;
  trend?: number | null;
  trendSuffix?: string;
  size?: "md" | "lg";
}) {
  return (
    <div className="min-w-0 p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="truncate text-[11px] font-medium text-slate-500">{label}</p>
        {trend !== undefined ? <TrendValue value={trend} suffix={trendSuffix} /> : null}
      </div>
      <p className={`mt-1 truncate font-semibold tabular-nums text-slate-950 ${size === "lg" ? "text-3xl" : "text-xl"}`}>{value}</p>
      {helper ? <p className="mt-1 truncate text-[11px] text-slate-500">{helper}</p> : null}
    </div>
  );
}

// Faixa de métricas de tempo — visual deliberadamente diferente dos cards de
// operação (fundo âmbar suave, sem selo de ícone por célula) pra não parecer
// "mais do mesmo": Tempo é uma dimensão distinta de Operação, não uma
// continuação da mesma grade.
export function TimeMetricsStrip({
  items,
}: {
  items: Array<{ label: string; value: string; helper?: string; emphasis?: boolean; muted?: boolean }>;
}) {
  return (
    <div className="overflow-hidden rounded-2xl border border-amber-200/70 bg-amber-50/50 shadow-sm">
      <div className="grid divide-amber-200/70 sm:grid-cols-2 sm:divide-x sm:divide-y-0 xl:grid-cols-4">
        {items.map((item, index) => (
          <div key={item.label} className={`min-w-0 p-4 ${index > 0 ? "border-t border-amber-200/70 sm:border-t-0" : ""}`}>
            <p className={`truncate text-[11px] font-medium ${item.emphasis ? "text-amber-800" : "text-slate-500"}`}>{item.label}</p>
            <p className={`mt-1 truncate text-2xl font-bold tabular-nums ${item.muted ? "text-slate-400" : item.emphasis ? "text-amber-900" : "text-slate-950"}`}>
              {item.value}
            </p>
            {item.helper ? <p className="mt-1 truncate text-[11px] text-slate-500">{item.helper}</p> : null}
          </div>
        ))}
      </div>
    </div>
  );
}

export function OpaOverview({ overview }: { overview: SupportOpaOverview | null }) {
  const customers = overview?.customers;
  const botHuman = overview?.bot_human;
  return (
    <div className="grid gap-6">
      <OverviewSection title="Operação">
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="grid divide-y divide-slate-100 lg:grid-cols-[1.1fr_2fr] lg:items-stretch lg:divide-x lg:divide-y-0">
            <div className="flex flex-col justify-center p-5">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Volume no período</p>
              <div className="mt-2 flex items-baseline gap-3">
                <p className="text-4xl font-bold tabular-nums text-slate-950">{number(overview?.total_attendances.current)}</p>
                <TrendValue value={overview?.total_attendances.percentage_change} suffix="%" />
              </div>
              <p className="mt-1 text-xs text-slate-500">vs. período anterior</p>
            </div>
            <div className="grid grid-cols-2 divide-x divide-y divide-slate-100 sm:grid-cols-3 sm:divide-y-0">
              <StatCell label="Encerrados" value={number(overview?.closed_attendances.current)} trend={overview?.closed_attendances.percentage_change} />
              <StatCell label="Em aberto" value={number(overview?.open_attendances.current)} trend={overview?.open_attendances.percentage_change} />
              <StatCell label="Taxa de encerramento" value={`${number(overview?.closure_rate.current, 1)}%`} trend={overview?.closure_rate.percentage_change} />
              <StatCell label="Avaliação média" value={number(overview?.average_rating.current, 2)} trend={overview?.average_rating.percentage_change} />
              <StatCell label="Atendentes distintos" value={number(overview?.distinct_attendants.current)} trend={overview?.distinct_attendants.percentage_change} />
              <StatCell label="Departamentos distintos" value={number(overview?.distinct_departments.current)} trend={overview?.distinct_departments.percentage_change} />
            </div>
          </div>
        </div>
      </OverviewSection>

      <OverviewSection title="Tempo">
        <TimeMetricsStrip
          items={[
            { label: "TMA", value: secondsLabel(overview?.average_duration_seconds.current), helper: "duração média" },
            { label: "TMR humano", value: secondsLabel(overview?.average_tmr_seconds.current), helper: "exclui bot" },
            { label: "TMR geral", value: secondsLabel(overview?.average_tmr_all_responses_seconds.current), helper: "inclui bot", emphasis: true },
            { label: "1ª resposta humana", value: secondsLabel(overview?.average_first_response_seconds) },
          ]}
        />
      </OverviewSection>

      <OverviewSection title="Clientes">
        <CustomerSummaryPanel customers={customers ?? null} />
      </OverviewSection>

      <OverviewSection title="Automação" description="bot vs. atendimento humano">
        <BotHumanSummary metrics={botHuman ?? null} />
      </OverviewSection>

      <OverviewSection title="Distribuição">
        <div className="grid gap-3 lg:grid-cols-2">
          <ChannelSummary items={overview?.by_channel ?? []} />
          <StatusSummary items={overview?.by_status ?? []} />
        </div>
        <div className="mt-3">
          <TopReasonsSummary items={overview?.top_reasons ?? []} />
        </div>
      </OverviewSection>
    </div>
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
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="grid grid-cols-2 divide-x divide-y divide-slate-100 sm:grid-cols-3 sm:divide-y-0 xl:grid-cols-6">
          <StatCell label="Atendentes ativos" value={number(overview?.distinct_attendants.current)} trend={overview?.distinct_attendants.percentage_change} />
          <StatCell label="Atendimentos" value={number(overview?.total_attendances.current)} trend={overview?.total_attendances.percentage_change} />
          <StatCell label="Taxa de encerramento" value={`${number(overview?.closure_rate.current, 1)}%`} trend={overview?.closure_rate.percentage_change} />
          <StatCell label="Duração média" value={secondsLabel(overview?.average_duration_seconds.current)} trend={overview?.average_duration_seconds.percentage_change} />
          <StatCell label="Avaliação média" value={number(overview?.average_rating.current, 2)} trend={overview?.average_rating.percentage_change} />
          <StatCell label="Cobertura de avaliação" value={ratingCoverage === null ? "-" : `${number(ratingCoverage, 1)}%`} helper={`${number(ratingCount)} avaliação(ões)`} />
        </div>
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

export function TrendValue({ value, suffix = "" }: { value: number | null | undefined; suffix?: string }) {
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

function BarListPanel({
  title,
  icon: Icon,
  items,
  emptyLabel,
  labelFor,
}: {
  title: string;
  icon: typeof Database;
  items: Array<{ key: string; label: string; total: number }>;
  emptyLabel: string;
  labelFor?: (key: string) => string;
}) {
  const max = items.reduce((acc, item) => Math.max(acc, item.total), 0) || 1;
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-3">
        <Icon className="h-3.5 w-3.5 text-slate-400" />
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
      </div>
      <div className="grid gap-3 p-4">
        {items.map((item) => (
          <div key={item.key} className="grid min-w-0 grid-cols-[1fr_auto] items-center gap-3">
            <div className="min-w-0">
              <div className="flex items-baseline justify-between gap-2">
                <p className="truncate text-sm font-medium text-slate-800" title={labelFor ? labelFor(item.key) : item.label}>{item.label}</p>
                <p className="shrink-0 text-sm font-semibold tabular-nums text-slate-950">{number(item.total)}</p>
              </div>
              <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                <div className="h-full rounded-full bg-blue-500" style={{ width: `${Math.max((item.total / max) * 100, 2)}%` }} />
              </div>
            </div>
          </div>
        ))}
        {!items.length ? <p className="py-6 text-center text-sm text-slate-500">{emptyLabel}</p> : null}
      </div>
    </div>
  );
}

export function ChannelSummary({ items }: { items: Array<{ channel: string; total: number }> }) {
  return (
    <BarListPanel
      title="Atendimentos por canal"
      icon={Database}
      items={items.map((item) => ({ key: item.channel, label: item.channel, total: item.total }))}
      emptyLabel="Nenhum canal encontrado para os filtros atuais."
    />
  );
}

export function StatusSummary({ items }: { items: Array<{ status: string; total: number }> }) {
  return (
    <BarListPanel
      title="Atendimentos por status"
      icon={TriangleAlert}
      items={items.map((item) => ({ key: item.status, label: opaStatusLabel(item.status), total: item.total }))}
      emptyLabel="Nenhum status encontrado para os filtros atuais."
    />
  );
}

export function TopReasonsSummary({ items }: { items: SupportOpaReasonMetric[] }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 px-4 py-3">
        <div className="flex items-center gap-2">
          <ListFilter className="h-3.5 w-3.5 text-slate-400" />
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Motivos com mais volume</h3>
        </div>
        <p className="mt-1 text-xs text-slate-400">Considera só o primeiro motivo registrado em cada atendimento.</p>
      </div>
      <div className="overflow-x-auto p-4">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Motivo</TableHead>
              <TableHead className="text-right">Atendimentos</TableHead>
              <TableHead className="text-right">TMA médio</TableHead>
              <TableHead className="text-right">TMR humano</TableHead>
              <TableHead className="text-right">TMR geral</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.label}>
                <TableCell className="max-w-72 truncate font-medium text-slate-800" title={item.label}>{item.label}</TableCell>
                <TableCell className="text-right tabular-nums">{number(item.total)}</TableCell>
                <TableCell className="text-right tabular-nums">{secondsLabel(item.average_tma_seconds)}</TableCell>
                <TableCell className="text-right tabular-nums">{secondsLabel(item.average_tmr_seconds)}</TableCell>
                <TableCell className="text-right tabular-nums">{secondsLabel(item.average_tmr_all_responses_seconds)}</TableCell>
              </TableRow>
            ))}
            {!items.length ? (
              <TableRow>
                <TableCell colSpan={5} className="py-10 text-center text-sm text-slate-500">Nenhum motivo encontrado para os filtros atuais.</TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

export function TopRecurringCustomers({ items }: { items: SupportOpaRecurringCustomer[] }) {
  return (
    <div>
      <div className="flex items-center gap-2 px-4 pb-2 pt-4 lg:px-5">
        <RotateCcw className="h-3.5 w-3.5 text-slate-400" />
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Clientes mais recorrentes</h3>
      </div>
      <div className="grid gap-1 px-3 pb-3 lg:px-4">
        {items.map((item, index) => {
          const customerCode = customerCodeLabel(item.customer_id);
          return (
            <div
              key={item.customer_id ?? `${item.customer_name ?? "cliente"}-${index}`}
              className="grid min-w-0 grid-cols-[2rem_minmax(0,1fr)_auto] items-center gap-3 rounded-lg px-2.5 py-2 transition-colors hover:bg-slate-50"
              title={[item.customer_name, customerCode].filter(Boolean).join(" - ")}
            >
              <span className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-100 text-[11px] font-semibold tabular-nums text-slate-500">
                {index + 1}
              </span>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-slate-900">{customerNameLabel(item.customer_name, item.customer_id)}</p>
                {customerCode ? <p className="mt-0.5 truncate text-[11px] text-slate-500">{customerCode}</p> : null}
              </div>
              <Badge className="border-blue-100 bg-blue-50 text-blue-700">
                {number(item.total)}
              </Badge>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function CustomerSummaryPanel({ customers }: { customers: SupportOpaOverview["customers"] | null }) {
  const recurringPercentage = customers?.recurring_customers_percentage ?? null;
  const recurrenceWidth = recurringPercentage === null ? 0 : Math.min(Math.max(recurringPercentage, 0), 100);
  const hasRecurringCustomers = Boolean(customers?.top_recurring_customers.length);

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="grid lg:grid-cols-[minmax(18rem,0.78fr)_minmax(0,1.42fr)] lg:items-stretch">
        <div className="flex flex-col justify-center gap-3 border-b border-slate-100 bg-slate-50/70 p-4 lg:border-b-0 lg:border-r lg:p-5">
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200/70">
              <p className="text-[11px] font-medium text-slate-500">Clientes únicos</p>
              <p className="mt-1 text-3xl font-bold tabular-nums text-slate-950">{number(customers?.unique_customers)}</p>
              <p className="mt-1 text-[11px] text-slate-500">{number(customers?.average_attendances_per_customer, 1)} atend./cliente</p>
            </div>
            <div className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200/70">
              <p className="text-[11px] font-medium text-slate-500">Reincidentes</p>
              <p className="mt-1 text-3xl font-bold tabular-nums text-slate-950">{number(customers?.recurring_customers)}</p>
              <p className="mt-1 text-[11px] text-slate-500">{customers ? `${number(customers.recurring_customers_percentage, 1)}% dos únicos` : "-"}</p>
            </div>
          </div>

          <div className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200/70">
            <div className="flex items-center justify-between gap-3">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Pressão de recorrência</p>
              <span className="text-sm font-bold tabular-nums text-slate-950">{recurringPercentage === null ? "-" : `${number(recurringPercentage, 1)}%`}</span>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
              <div className="h-full rounded-full bg-blue-600" style={{ width: `${recurrenceWidth}%` }} />
            </div>
            <p className="mt-2 text-xs leading-relaxed text-slate-500">
              Mostra quantos clientes voltaram a abrir atendimento no recorte atual.
            </p>
          </div>
        </div>

        <div className="min-w-0 max-h-[420px] overflow-y-auto">
          {hasRecurringCustomers ? (
            <TopRecurringCustomers items={customers?.top_recurring_customers ?? []} />
          ) : (
            <p className="p-6 text-center text-sm text-slate-500">Nenhum cliente recorrente encontrado para os filtros atuais.</p>
          )}
        </div>
      </div>
    </div>
  );
}

export function BotHumanSummary({ metrics }: { metrics: SupportOpaBotHumanMetrics | null }) {
  if (!metrics) return null;
  const hasClassified = metrics.classified_attendances > 0;
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 px-4 py-3">
        <div className="flex items-center gap-2">
          <GitBranch className="h-3.5 w-3.5 text-slate-400" />
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">IA (bot) vs. atendimento humano</h3>
        </div>
        <p className="mt-1 text-xs text-slate-400">
          Percentuais calculados só sobre atendimentos classificados ({number(metrics.classified_attendances)} de {number(metrics.total_attendances)}) —
          {" "}{number(metrics.unclassified_attendances)} sem dado suficiente para classificar não entram no percentual.
        </p>
      </div>
      <div className="grid grid-cols-3 divide-x divide-slate-100">
        <StatCell label="Com bot" value={hasClassified ? `${number(metrics.with_bot_percentage, 1)}%` : "-"} size="lg" />
        <StatCell label="Chegou a humano" value={hasClassified ? `${number(metrics.reached_human_percentage, 1)}%` : "-"} size="lg" />
        <StatCell label="Handoff bot → humano" value={hasClassified ? `${number(metrics.bot_to_human_handoff_percentage, 1)}%` : "-"} size="lg" />
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
        <StatusRow
          label="Importação agora"
          value={
            syncStatus?.sync_in_progress
              ? syncStatus.active_run_mode === "scheduled"
                ? "Automática em andamento"
                : "Em andamento"
              : "Nenhuma"
          }
        />
        <StatusRow label="Última tentativa" value={dateTimeLabel(syncStatus?.last_attempt_at)} />
        <StatusRow label="Último sucesso" value={dateTimeLabel(syncStatus?.last_success_at)} />
        <StatusRow label="Próxima janela" value={dateTimeLabel(syncStatus?.next_allowed_at)} />
        <StatusRow label="Falhas seguidas" value={String(syncStatus?.consecutive_failures ?? 0)} danger={Boolean(syncStatus?.consecutive_failures)} />
        <StatusRow label="Status" value={syncStatus?.enabled ? "Automático ligado" : "Automático desligado"} />
        <StatusRow label="Intervalo" value={`${settings?.interval_minutes ?? 20} min`} />
        <StatusRow label="Reimportação" value={`${settings?.lookback_days ?? 1} dia(s)`} />
      </div>
      {syncStatus?.sync_in_progress ? (
        <div className="mt-4 flex items-start gap-2 rounded-xl border border-sky-200 bg-sky-50 p-3 text-xs text-sky-800">
          <Loader2 className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-spin" />
          <span>
            {syncStatus.active_run_mode ? (
              <>
                Existe uma importação {syncStatus.active_run_mode === "scheduled" ? "automática" : "manual"} em andamento
                {syncStatus.active_run_started_at ? ` desde ${dateTimeLabel(syncStatus.active_run_started_at)}` : ""}.
              </>
            ) : (
              "Há uma importação do OPA em andamento, mas a run ativa ainda não pôde ser identificada."
            )}
            {syncStatus.next_window_delayed
              ? " A próxima janela automática está aguardando essa execução terminar — não é um erro."
              : ""}
          </span>
        </div>
      ) : null}
      {syncStatus?.last_error ? (
        isTransientBusyMessage(syncStatus.last_error) ? (
          <div className="mt-4 flex items-start gap-2 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
            <Clock3 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" />
            <span>
              A última tentativa em {dateTimeLabel(syncStatus.last_error_at)} esbarrou numa importação anterior ainda em
              andamento (ciclos que buscam mensagem por atendimento pra calcular TMR podem passar do intervalo
              configurado) — não é uma falha real, o próximo ciclo segue normal quando a execução atual terminar.
            </span>
          </div>
        ) : (
          <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-700">
            <div className="mb-1 flex items-center gap-1 font-semibold"><TriangleAlert className="h-3.5 w-3.5" /> Último erro</div>
            {syncStatus.last_error}
          </div>
        )
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

export function OpaAttendantOverridesPanel({
  canManage,
  overrides,
  loading,
  error,
  saving,
  onCreate,
  onToggleActive,
  onDelete,
}: {
  canManage: boolean;
  overrides: SupportOpaAttendantOverride[];
  loading: boolean;
  error: string | null;
  saving: boolean;
  onCreate: (payload: SupportOpaAttendantOverrideCreate) => void;
  onToggleActive: (id: number, active: boolean) => void;
  onDelete: (id: number) => void;
}) {
  const [attendantId, setAttendantId] = useState("");
  const [attendantName, setAttendantName] = useState("");

  if (!canManage) return null;

  function submit() {
    if (!attendantId.trim()) return;
    onCreate({ attendant_id: attendantId.trim(), attendant_name: attendantName.trim() || null, classification: "virtual_agent" });
    setAttendantId("");
    setAttendantName("");
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-2 text-slate-800">
        <Users className="h-5 w-5" />
        <h3 className="text-base font-semibold">Atendentes virtuais (agente virtual)</h3>
      </div>
      <p className="mt-1 text-xs text-slate-500">
        Cadastre aqui um `attendant_id` do OPA Suite que deve ser sempre tratado como agente virtual — o painel
        individual passa a priorizar TMR geral pra ele, mesmo que o OPA nunca mande `tipo="bot"`.
      </p>

      <div className="mt-4 grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
        <Input placeholder="attendant_id do OPA Suite" value={attendantId} onChange={(event) => setAttendantId(event.target.value)} disabled={saving} />
        <Input placeholder="Nome (opcional)" value={attendantName} onChange={(event) => setAttendantName(event.target.value)} disabled={saving} />
        <Button type="button" onClick={submit} disabled={saving || !attendantId.trim()}>
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : "Cadastrar"}
        </Button>
      </div>

      {error ? <div className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">{error}</div> : null}

      {loading ? (
        <div className="mt-4 flex items-center gap-2 text-sm text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin" /> Carregando cadastro...
        </div>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Attendant ID</TableHead>
                <TableHead>Nome</TableHead>
                <TableHead>Classificação</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {overrides.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-sm text-slate-500">
                    Nenhum atendente virtual cadastrado.
                  </TableCell>
                </TableRow>
              ) : (
                overrides.map((override) => (
                  <TableRow key={override.id}>
                    <TableCell className="font-mono text-xs">{override.attendant_id}</TableCell>
                    <TableCell>{override.attendant_name ?? "-"}</TableCell>
                    <TableCell>
                      <Badge className="border-blue-100 bg-blue-50 text-blue-700">Agente virtual</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge className={override.active ? "border-emerald-100 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-slate-50 text-slate-500"}>
                        {override.active ? "Ativo" : "Inativo"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-2">
                        <Button type="button" variant="outline" size="sm" disabled={saving} onClick={() => onToggleActive(override.id, !override.active)}>
                          {override.active ? "Desativar" : "Ativar"}
                        </Button>
                        <Button type="button" variant="outline" size="sm" disabled={saving} onClick={() => onDelete(override.id)}>
                          <X className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
