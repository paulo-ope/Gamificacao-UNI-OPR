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
  Info,
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
import { type ReactNode, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { InfoHint } from "@/components/gamification/info-hint";
import { DateRangePicker, commonDateRangePresets, type DateRangePreset } from "@/components/ui/date-range-picker";
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
  SupportOpaBotHumanFilter,
  SupportOpaFilters,
  SupportOpaImportedDataWindow,
  SupportOpaImportMonth,
  SupportOpaMetricComparison,
  SupportOpaMetricCoverage,
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

// O backend recusa (422) QUALQUER consulta do OPA Suite - visão geral, gráficos, lista de
// atendimentos, importação - acima de 32 dias, não só a importação manual (ver
// `validate_opa_period`/`apply_opa_attendance_filters` em
// backend/app/modules/support/opa_filters.py). Achado real, 2026-08-27: um preset amplo
// ("Este ano") barrava a tela inteira com esse erro ao simplesmente trocar o período, sem
// nem chegar a clicar em importar.
export const OPA_MAX_PERIOD_DAYS = 32;

export function opaPeriodSpanDays(dateFrom: string, dateTo: string): number {
  if (!dateFrom || !dateTo) return 0;
  return Math.round((new Date(`${dateTo}T00:00:00Z`).getTime() - new Date(`${dateFrom}T00:00:00Z`).getTime()) / 86400000) + 1;
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

// Converte um timestamp ISO (UTC) pro dia LOCAL (America/Porto_Velho) no
// formato YYYY-MM-DD, comparável direto com `date_from`/`date_to` do filtro
// (que já são datas locais, sem componente de hora). Mesmo raciocínio de
// `localToday()`: nunca usar `.slice(0, 10)` num ISO em UTC pra isso, o
// resultado pode cair no dia errado perto da virada.
function toLocalDateString(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: SUPPORT_TIMEZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(iso));
  const lookup = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${lookup.year}-${lookup.month}-${lookup.day}`;
}

// "Hoje"/"Ontem" etc. precisam ser o dia corrente no fuso operacional da UNI
// (SUPPORT_TIMEZONE), não no fuso do navegador de quem está olhando a tela - por isso
// passa `localToday` como fonte de "hoje" pro conjunto de presets compartilhado.
export function opaPeriodPresets(): DateRangePreset[] {
  return commonDateRangePresets(localToday).filter((preset) => {
    const { from, to } = preset.range();
    return opaPeriodSpanDays(from, to) <= OPA_MAX_PERIOD_DAYS;
  });
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

// Tempo decorrido em texto curto ("3h 14min", "42 min") - usado pra avisar quando uma
// sincronização está rodando por mais tempo que o normal (achado real de 2026-08-27: o usuário
// olhou pro painel com uma importação travada há mais de 3h e não tinha como perceber isso -
// o mesmo aviso azul calmo aparecia tanto pra "rodando há 30s" quanto pra "rodando há 3h").
function elapsedLabel(fromIso: string): string {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(fromIso).getTime()) / 60000));
  if (minutes < 1) return "menos de 1 min";
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${minutes} min`;
  return rest === 0 ? `${hours}h` : `${hours}h ${rest}min`;
}

// Acima disso, uma sincronização em andamento deixa de ser "normal" (ciclos com TMR podem passar
// um pouco do intervalo configurado) e vira algo que merece atenção - achado real: um caso
// observado ficou rodando por mais de 3h, e nada no painel distinguia isso de uma execução comum.
const SYNC_RUNNING_WARNING_MINUTES = 15;

type SyncHeadline = {
  tone: "ok" | "running" | "warning" | "error" | "off" | "unconfigured";
  title: string;
  detail: string;
};

function syncHeadline(syncStatus: SupportOpaSyncStatus | null): SyncHeadline {
  if (!syncStatus) return { tone: "off", title: "Carregando status...", detail: "" };
  if (!syncStatus.configured) {
    return {
      tone: "unconfigured",
      title: "OPA Suite não está conectado",
      detail: "Falta configurar o endereço/token da API do OPA Suite - a sincronização não roda sem isso.",
    };
  }
  if (syncStatus.last_error && !isTransientBusyMessage(syncStatus.last_error)) {
    return {
      tone: "error",
      title: "A última sincronização falhou",
      detail: `${dateTimeLabel(syncStatus.last_error_at)} — ${syncStatus.last_error}`,
    };
  }
  if (syncStatus.sync_in_progress) {
    const startedAt = syncStatus.active_run_started_at;
    const elapsedMinutes = startedAt ? Math.round((Date.now() - new Date(startedAt).getTime()) / 60000) : 0;
    const modeLabel = syncStatus.active_run_mode === "scheduled" ? "automática" : "manual";
    if (startedAt && elapsedMinutes > SYNC_RUNNING_WARNING_MINUTES) {
      return {
        tone: "warning",
        title: "Sincronização rodando há mais tempo que o normal",
        detail: `Importação ${modeLabel} em andamento há ${elapsedLabel(startedAt)} (desde ${dateTimeLabel(startedAt)}). Uma sincronização comum leva segundos a poucos minutos — se continuar assim por muito mais tempo, vale olhar os logs do servidor.`,
      };
    }
    return {
      tone: "running",
      title: "Sincronizando agora",
      detail: startedAt
        ? `Importação ${modeLabel} em andamento há ${elapsedLabel(startedAt)}.`
        : "Existe uma importação em andamento.",
    };
  }
  if (!syncStatus.enabled) {
    return {
      tone: "off",
      title: "Sincronização automática desligada",
      detail: "Ninguém está atualizando os dados do OPA Suite sozinho agora — use \"Importar dados\" pra atualizar na mão, ou ligue o automático abaixo.",
    };
  }
  return {
    tone: "ok",
    title: "Sincronizado",
    detail: syncStatus.last_success_at
      ? `Última atualização com sucesso: ${dateTimeLabel(syncStatus.last_success_at)}. Próxima janela automática: ${dateTimeLabel(syncStatus.next_allowed_at)}.`
      : "Ainda não teve nenhuma sincronização concluída com sucesso.",
  };
}

const SYNC_HEADLINE_STYLES: Record<SyncHeadline["tone"], { box: string; icon: string }> = {
  ok: { box: "border-emerald-200 bg-emerald-50 text-emerald-800", icon: "text-emerald-600" },
  running: { box: "border-sky-200 bg-sky-50 text-sky-800", icon: "text-sky-600" },
  warning: { box: "border-amber-200 bg-amber-50 text-amber-800", icon: "text-amber-600" },
  error: { box: "border-red-200 bg-red-50 text-red-800", icon: "text-red-600" },
  off: { box: "border-slate-200 bg-slate-50 text-slate-700", icon: "text-slate-500" },
  unconfigured: { box: "border-red-200 bg-red-50 text-red-800", icon: "text-red-600" },
};

function SyncHeadlineIcon({ tone }: { tone: SyncHeadline["tone"] }) {
  const className = `h-5 w-5 shrink-0 ${SYNC_HEADLINE_STYLES[tone].icon}`;
  if (tone === "ok") return <CheckCircle2 className={className} />;
  if (tone === "running") return <Loader2 className={`${className} animate-spin`} />;
  if (tone === "warning") return <Clock3 className={className} />;
  if (tone === "error" || tone === "unconfigured") return <TriangleAlert className={className} />;
  return <Clock3 className={className} />;
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
    filters.tag_id ? { key: "tag", label: `Etiqueta: ${labelFrom(options?.tags, filters.tag_id)}` } : null,
    filters.bot_human ? { key: "bot_human", label: `Automação: ${BOT_HUMAN_LABELS[filters.bot_human] ?? filters.bot_human}` } : null,
    filters.rating_min !== undefined || filters.rating_max !== undefined
      ? {
          key: "rating",
          label: `Avaliação: ${filters.rating_min ?? 0} a ${filters.rating_max ?? 5}`,
        }
      : null,
  ].filter(Boolean) as Array<{ key: string; label: string }>;
}

/** A chave do badge nem sempre é o nome do campo (`attendant` -> `attendant_id`),
 *  e um badge pode limpar mais de um campo (`rating` -> mín. e máx.). Era uma
 *  cadeia de ternários inline no onClick; virou função pra caber os dois casos
 *  sem ficar ilegível. */
function clearPatchForBadge(key: string): Partial<SupportOpaAttendanceFilters> {
  const aliases: Record<string, keyof SupportOpaAttendanceFilters> = {
    attendant: "attendant_id",
    department: "department_id",
    reason: "reason_id",
    tag: "tag_id",
  };
  if (key === "rating") return { rating_min: undefined, rating_max: undefined, page: 1 };
  const field = aliases[key] ?? (key as keyof SupportOpaAttendanceFilters);
  return { [field]: undefined, page: 1 } as Partial<SupportOpaAttendanceFilters>;
}

const BOT_HUMAN_LABELS: Record<string, string> = {
  with_bot: "Teve bot",
  without_bot: "Sem bot",
  reached_human: "Chegou a humano",
  bot_only: "Só bot",
  handoff: "Handoff bot → humano",
  unclassified: "Não classificado",
};

function splitFilterValues(value?: string) {
  return (value || "").split(",").map((item) => item.trim()).filter(Boolean);
}

function attendantInitials(label: string | null | undefined) {
  const words = (label ?? "").trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return `${words[0][0]}${words[words.length - 1][0]}`.toUpperCase();
}

function shortDateLabel(isoLocalDate: string) {
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${isoLocalDate}T12:00:00Z`));
}

// Janela real da base vs. recorte escolhido — norma de qualidade de dados,
// seção 7: divergência por ausência de histórico não é bug, mas precisa
// ficar visível pra não ser confundida com um na hora de comparar com o
// painel oficial do OPA.
function ImportedDataWindowNote({
  window,
  periodDateFrom,
}: {
  window: SupportOpaImportedDataWindow | null | undefined;
  periodDateFrom: string;
}) {
  const minLocal = toLocalDateString(window?.min_opened_at);
  const maxLocal = toLocalDateString(window?.max_opened_at);
  if (!window || !minLocal || !maxLocal) return null;
  const startsBeforeBase = periodDateFrom < minLocal;
  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1.5">
      <span className="inline-flex items-center gap-1 text-[11px] text-slate-500">
        <Database className="h-3 w-3 text-slate-400" />
        Base importada: {shortDateLabel(minLocal)} até {shortDateLabel(maxLocal)} · {number(window.total_attendances)} atendimentos
      </span>
      {startsBeforeBase ? (
        <span className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] text-amber-800">
          <TriangleAlert className="h-3 w-3 shrink-0" />
          Este recorte começa antes da primeira data importada — a comparação com o OPA pode divergir por ausência de histórico local.
        </span>
      ) : null}
    </div>
  );
}

export function OpaGlobalFilters({
  period,
  filters,
  options,
  loading,
  canSync,
  syncing,
  canImport,
  importedDataWindow,
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
  importedDataWindow?: SupportOpaImportedDataWindow | null;
  onPeriodChange: (period: Period | ((current: Period) => Period)) => void;
  onFilterChange: (patch: Partial<SupportOpaAttendanceFilters>) => void;
  onApply: () => void;
  onClear: () => void;
  onImport: () => void;
}) {
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);
  const badges = activeFilterBadges(filters, options);
  // O backend recusa (422) QUALQUER consulta do OPA Suite acima de 32 dias - visão geral,
  // gráficos, lista de atendimentos e importação, não só "Importar dados" (ver
  // `opaPeriodSpanDays`/OPA_MAX_PERIOD_DAYS acima e `validate_opa_period` no backend). Os
  // presets do seletor já ficam de fora desse limite (`opaPeriodPresets` filtra), mas o
  // usuário ainda pode digitar/clicar um intervalo maior manualmente no calendário - por
  // isso trava "Filtrar" e "Importar dados" os dois, com uma explicação antes de deixar
  // estourar o erro. Achado real, 2026-08-27.
  const periodSpanDays = opaPeriodSpanDays(period.date_from, period.date_to);
  const periodTooLong = periodSpanDays > OPA_MAX_PERIOD_DAYS;
  return (
    <section className="contents">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 bg-white px-4 pb-3 pt-3 lg:px-7">
        <div>
          <p className="text-sm font-semibold text-slate-950">Filtros</p>
          <p className="text-xs text-slate-500">O mesmo recorte é aplicado à Visão Geral e aos Dados.</p>
          <ImportedDataWindowNote window={importedDataWindow} periodDateFrom={period.date_from} />
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
          <div className="text-right">
            <Button
              type="button"
              variant="outline"
              onClick={onImport}
              disabled={syncing || loading || !canImport || periodTooLong}
              title={periodTooLong ? "Período acima de 32 dias - reduza o período pra importar manualmente, ou use o backfill automático de meses na aba de sincronização." : undefined}
              className="h-9 border-blue-200 text-blue-700 hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {syncing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              Importar dados
            </Button>
            {periodTooLong ? (
              <p className="mt-1 max-w-64 text-[11px] text-amber-700">
                Período de {periodSpanDays} dias - o OPA Suite só aceita consultas de até 32 dias por vez. Pra trazer um histórico maior, use o backfill automático de meses.
              </p>
            ) : null}
          </div>
        ) : null}
      </div>

      <div className={`${mobileFiltersOpen ? "grid" : "hidden"} max-h-[calc(100vh-65px)] items-end gap-2 overflow-y-auto border-y border-slate-200 bg-white px-4 py-2 shadow-sm md:sticky md:top-[65px] md:z-20 md:grid md:max-h-none md:grid-cols-2 md:overflow-visible lg:px-7 xl:grid-cols-[14rem_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto]`}>
        <div className="min-w-0">
          <DateRangePicker
            dateFrom={period.date_from}
            dateTo={period.date_to}
            presets={opaPeriodPresets()}
            className="w-full"
            // Atualização funcional - presets e a inversão de intervalo no calendário chamam
            // onChange duas vezes seguidas (date_from e date_to) na mesma interação; usando
            // `{ ...period, [key]: value }` direto, a segunda chamada lia o `period` velho (de
            // antes da primeira) e desfazia a primeira mudança - clicar num preset como "Hoje"
            // silenciosamente não fazia nada. Achado real, 2026-08-27.
            onChange={(key, value) => onPeriodChange((current) => ({ ...current, [key]: value }))}
          />
          {periodTooLong ? (
            <p className="mt-1 text-[11px] text-amber-700">
              Período de {periodSpanDays} dias - reduza pra até 32 dias, o OPA Suite não aceita consultas maiores.
            </p>
          ) : null}
        </div>
        <FilterMultiSelect label="Atendente" value={filters.attendant_id} options={options?.attendants ?? []} onChange={(value) => onFilterChange({ attendant_id: value, page: 1 })} />
        <FilterMultiSelect label="Departamento" value={filters.department_id} options={options?.departments ?? []} onChange={(value) => onFilterChange({ department_id: value, page: 1 })} />
        <FilterMultiSelect label="Canal" value={filters.channel} options={options?.channels ?? []} onChange={(value) => onFilterChange({ channel: value, page: 1 })} />
        <div className="flex flex-wrap gap-2 xl:flex-nowrap xl:justify-end">
          <Button
            type="button"
            onClick={onApply}
            disabled={loading || periodTooLong}
            title={periodTooLong ? "Período acima de 32 dias - o OPA Suite não aceita consultas maiores que isso." : undefined}
            className="h-10"
          >
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
              <FilterMultiSelect label="Etiqueta" value={filters.tag_id} options={options?.tags ?? []} onChange={(value) => onFilterChange({ tag_id: value, page: 1 })} />
              <label className="grid min-w-0 gap-1.5 text-[11px] font-medium text-slate-600">
                Participação bot/humano
                <select
                  value={filters.bot_human ?? ""}
                  onChange={(event) => onFilterChange({ bot_human: (event.target.value || undefined) as SupportOpaBotHumanFilter | undefined, page: 1 })}
                  className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700"
                >
                  <option value="">Todos</option>
                  <option value="with_bot">Teve bot</option>
                  <option value="without_bot">Sem bot</option>
                  <option value="reached_human">Chegou a humano</option>
                  <option value="bot_only">Só bot (sem humano)</option>
                  <option value="handoff">Handoff bot → humano</option>
                  <option value="unclassified">Não classificado</option>
                </select>
              </label>
              <div className="grid min-w-0 gap-1.5 md:col-span-2">
                <span className="text-[11px] font-medium text-slate-600">
                  Avaliação
                  <span className="ml-1 font-normal text-slate-400">
                    só atendimentos avaliados entram neste recorte
                  </span>
                </span>
                <div className="flex items-center gap-2">
                  <Input
                    type="number"
                    min={0}
                    max={5}
                    step={0.5}
                    value={filters.rating_min ?? ""}
                    onChange={(event) => onFilterChange({ rating_min: event.target.value === "" ? undefined : Number(event.target.value), page: 1 })}
                    placeholder="mín."
                    aria-label="Avaliação mínima"
                    className="h-9 w-24"
                  />
                  <span className="text-xs text-slate-400">até</span>
                  <Input
                    type="number"
                    min={0}
                    max={5}
                    step={0.5}
                    value={filters.rating_max ?? ""}
                    onChange={(event) => onFilterChange({ rating_max: event.target.value === "" ? undefined : Number(event.target.value), page: 1 })}
                    placeholder="máx."
                    aria-label="Avaliação máxima"
                    className="h-9 w-24"
                  />
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </div>
      {badges.length ? <div className="border-b border-slate-200 bg-white px-4 pb-3 lg:px-7">
        <div className="mt-2 flex min-h-7 flex-wrap items-center gap-1.5 text-xs text-slate-500">
          <span className="font-medium text-slate-700">{badges.length} filtros aplicados</span>
          {badges.map((item) => (
            <button key={item.key} type="button" onClick={() => onFilterChange(clearPatchForBadge(item.key))} className="inline-flex max-w-52 items-center gap-1 truncate rounded-full border border-slate-200 bg-slate-50 px-2 py-1 text-[10px] text-slate-700 transition-colors hover:bg-slate-100" title={`Remover ${item.label}`}>
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
        <span className="h-3 w-1 rounded-full bg-blue-600" aria-hidden="true" />
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">{title}</h3>
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
// Denominador explícito do TMR geral pra tela — norma de qualidade de dados,
// seção 1 ("todo percentual precisa dizer sobre o que foi calculado") e seção
// 5 (histórico parcial precisa estar claro, não escondido). `null` quando não
// há nada a dizer (sem filtro no recorte, ou dado já 100% coberto).
export function tmrCoverageNote(coverage: SupportOpaMetricCoverage | null | undefined): string | null {
  if (!coverage || coverage.total === 0) return null;
  if (coverage.count >= coverage.total) return null;
  const pct = coverage.percentage ?? 0;
  if (coverage.count === 0) {
    return "TMR geral: nenhum atendimento deste recorte tem o cálculo ainda — histórico anterior à ativação do campo não foi reprocessado.";
  }
  return `TMR geral: média sobre ${number(coverage.count)} de ${number(coverage.total)} atendimentos (cobertura de ${number(pct, 1)}%) — histórico mais antigo ainda não foi reprocessado.`;
}

export function TimeMetricsStrip({
  items,
  note,
}: {
  items: Array<{ label: string; value: string; helper?: string; emphasis?: boolean; muted?: boolean }>;
  note?: string | null;
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
      {note ? (
        <div className="flex items-start gap-1.5 border-t border-amber-200/70 bg-amber-50 px-4 py-2 text-[11px] leading-relaxed text-amber-800">
          <Info className="mt-0.5 h-3 w-3 shrink-0" />
          <span>{note}</span>
        </div>
      ) : null}
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
            <div className="flex flex-col justify-center bg-gradient-to-br from-blue-600 to-blue-700 p-5">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-blue-100">Volume no período</p>
              <div className="mt-2 flex items-baseline gap-3">
                <p className="text-4xl font-bold tabular-nums text-white">{number(overview?.total_attendances.current)}</p>
                <TrendValue value={overview?.total_attendances.percentage_change} suffix="%" tone="onDark" />
              </div>
              <p className="mt-1 text-xs text-blue-100">vs. período anterior</p>
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
          note={tmrCoverageNote(overview?.tmr_all_responses_coverage)}
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
        <div className="border-b border-slate-200 bg-slate-50/60 p-4">
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
              <div className="flex items-start gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-blue-700 text-xs font-bold text-white">
                  {attendantInitials(item.label)}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <p className="truncate text-sm font-semibold text-slate-950">{item.label}</p>
                    <TrendValue value={item.total_change_percentage} suffix="%" />
                  </div>
                  <p className="mt-0.5 text-xs text-slate-500">{number(item.total)} atendimentos</p>
                  <div className="mt-1.5 flex items-center gap-1.5">
                    <div className="h-1.5 w-full max-w-24 overflow-hidden rounded-full bg-slate-100">
                      <div className="h-full rounded-full bg-blue-500" style={{ width: `${Math.max(Math.min(item.share_percentage, 100), 2)}%` }} />
                    </div>
                    <span className="text-[11px] text-slate-500">{number(item.share_percentage, 1)}%</span>
                  </div>
                </div>
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
  const closureTone = item.closure_rate >= 90 ? "text-emerald-700" : item.closure_rate >= 70 ? "text-amber-700" : "text-slate-700";
  const ratingTone = item.avg_rating === null ? "text-slate-400" : item.avg_rating >= 4.5 ? "text-emerald-700" : item.avg_rating >= 3.5 ? "text-amber-700" : "text-red-700";
  return (
    <TableRow className={item.id ? "group cursor-pointer border-l-2 border-l-transparent hover:border-l-blue-600 hover:bg-blue-50/30" : ""} onClick={() => item.id && onOpenAttendant(item)}>
      <TableCell className="min-w-72 max-w-80" title={`${item.label} - abrir detalhe lateral`}>
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-blue-700 text-xs font-bold text-white">
            {attendantInitials(item.label)}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate font-semibold text-slate-950">{item.label}</p>
            <div className="mt-1 flex items-center gap-1.5">
              <div className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-100">
                <div className="h-full rounded-full bg-blue-500" style={{ width: `${Math.max(Math.min(item.share_percentage, 100), 2)}%` }} />
              </div>
              <span className="text-[11px] text-slate-500">{number(item.share_percentage, 1)}% do volume</span>
            </div>
          </div>
        </div>
      </TableCell>
      <TableCell>
        <p className="font-semibold tabular-nums text-slate-950">{number(item.total)}</p>
        <p className="mt-0.5 text-[11px] text-slate-500">{number(item.closed)} encerrados · {number(item.open)} abertos</p>
      </TableCell>
      <TableCell>
        <p className={`font-semibold tabular-nums ${closureTone}`}>{number(item.closure_rate, 1)}%</p>
        <p className="mt-0.5 text-[11px] text-slate-500">do volume encerrado</p>
      </TableCell>
      <TableCell>
        <p className="font-semibold tabular-nums text-slate-950">{secondsLabel(item.avg_duration_seconds)}</p>
        <p className="mt-0.5 text-[11px] text-slate-500">média dos encerrados</p>
      </TableCell>
      <TableCell>
        <p className={`font-semibold tabular-nums ${ratingTone}`}>{number(item.avg_rating, 2)}</p>
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

// `tone="onDark"` existe só pros painéis com fundo colorido cheio (ex.: o
// destaque de volume da Visão Geral) — as cores padrão (`text-blue-700` etc.)
// ficam ilegíveis sobre um fundo azul/escuro sólido.
export function TrendValue({ value, suffix = "", tone = "onLight" }: { value: number | null | undefined; suffix?: string; tone?: "onLight" | "onDark" }) {
  if (value === null || value === undefined) {
    return <span className={`inline-flex items-center justify-end gap-1 text-xs ${tone === "onDark" ? "text-white/60" : "text-slate-400"}`}>-</span>;
  }
  const rounded = number(Math.abs(value), suffix === "" ? 2 : 1);
  const positive = value > 0;
  const negative = value < 0;
  const Icon = positive ? ArrowUpRight : negative ? ArrowDownRight : Minus;
  const colorClass = tone === "onDark"
    ? "text-white"
    : positive ? "text-blue-700" : negative ? "text-slate-600" : "text-slate-400";
  return (
    <span className={`inline-flex items-center justify-end gap-1 text-xs font-semibold tabular-nums ${colorClass}`}>
      <Icon className="h-3.5 w-3.5" />
      {positive ? "+" : negative ? "-" : ""}{rounded}{suffix}
    </span>
  );
}

// Intensidade decrescente por rank — o item de maior volume herda a cor mais
// forte da paleta, reforçando hierarquia visual sem precisar de legenda à
// parte (norma visual: cor precisa comunicar prioridade/agrupamento, não é
// decoração).
const RANK_BAR_COLORS = ["bg-blue-600", "bg-blue-500", "bg-sky-500", "bg-sky-400", "bg-slate-400"];
const RANK_BADGE_TONES = [
  "bg-blue-600 text-white",
  "bg-blue-100 text-blue-700",
  "bg-sky-100 text-sky-700",
  "bg-slate-100 text-slate-600",
  "bg-slate-100 text-slate-500",
];

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
      <div className="flex items-center gap-2 border-b border-slate-100 bg-slate-50/60 px-4 py-3">
        <Icon className="h-3.5 w-3.5 text-blue-600" />
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">{title}</h3>
      </div>
      <div className="grid gap-2.5 p-4">
        {items.map((item, index) => (
          <div key={item.key} className="grid min-w-0 grid-cols-[1.5rem_1fr] items-center gap-2.5">
            <span className={`flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold tabular-nums ${RANK_BADGE_TONES[Math.min(index, RANK_BADGE_TONES.length - 1)]}`}>
              {index + 1}
            </span>
            <div className="min-w-0">
              <div className="flex items-baseline justify-between gap-2">
                <p className="truncate text-sm font-medium text-slate-800" title={labelFor ? labelFor(item.key) : item.label}>{item.label}</p>
                <p className="shrink-0 text-sm font-semibold tabular-nums text-slate-950">{number(item.total)}</p>
              </div>
              <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                <div className={`h-full rounded-full ${RANK_BAR_COLORS[Math.min(index, RANK_BAR_COLORS.length - 1)]}`} style={{ width: `${Math.max((item.total / max) * 100, 2)}%` }} />
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
      <div className="border-b border-slate-100 bg-slate-50/60 px-4 py-3">
        <div className="flex items-center gap-2">
          <ListFilter className="h-3.5 w-3.5 text-blue-600" />
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">Motivos com mais volume</h3>
        </div>
        <p className="mt-1 text-xs text-slate-400">Considera só o primeiro motivo registrado em cada atendimento.</p>
      </div>
      <div className="overflow-x-auto p-4">
        <Table>
          <TableHeader>
            <TableRow className="border-slate-200">
              <TableHead>Motivo</TableHead>
              <TableHead className="text-right">Atendimentos</TableHead>
              <TableHead className="text-right">TMA médio</TableHead>
              <TableHead className="text-right">TMR humano</TableHead>
              <TableHead className="text-right text-blue-700">TMR geral</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item, index) => (
              <TableRow key={item.label} className={index % 2 === 1 ? "bg-slate-50/50" : undefined}>
                <TableCell className="max-w-72 truncate font-medium text-slate-800" title={item.label}>{item.label}</TableCell>
                <TableCell className="text-right tabular-nums">{number(item.total)}</TableCell>
                <TableCell className="text-right tabular-nums">{secondsLabel(item.average_tma_seconds)}</TableCell>
                <TableCell className="text-right tabular-nums">{secondsLabel(item.average_tmr_seconds)}</TableCell>
                <TableCell
                  className="text-right tabular-nums font-semibold text-blue-700"
                  title={
                    item.tmr_all_responses_coverage && item.tmr_all_responses_coverage.total > 0
                      ? `Média sobre ${number(item.tmr_all_responses_coverage.count)} de ${number(item.tmr_all_responses_coverage.total)} atendimentos deste motivo`
                      : undefined
                  }
                >
                  {secondsLabel(item.average_tmr_all_responses_seconds)}
                </TableCell>
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
        <RotateCcw className="h-3.5 w-3.5 text-blue-600" />
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">Clientes mais recorrentes</h3>
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
              <span className={`flex h-7 w-7 items-center justify-center rounded-full text-[11px] font-bold tabular-nums ${RANK_BADGE_TONES[Math.min(index, RANK_BADGE_TONES.length - 1)]}`}>
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
      <div className="border-b border-slate-100 bg-slate-50/60 px-4 py-3">
        <div className="flex items-center gap-2">
          <GitBranch className="h-3.5 w-3.5 text-blue-600" />
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">IA (bot) vs. atendimento humano</h3>
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

// Rascunho de texto livre pra um campo numérico de configuração - achado real de
// 2026-08-27: `value={settings?.x ?? default}` direto num <input type="number">
// com `onChange={(e) => onDraftSettings({ x: Number(e.target.value) })}` fazia o
// campo virar "0" ao apagar (Number("") === 0, não NaN, e 0 não é "nullish" então
// o `?? default` nunca entrava). Mantendo o texto digitado à parte (permite ficar
// vazio) e só convertendo/gravando no blur resolve isso pros 4 campos numéricos
// desta tela (intervalo, dias de histórico, hora do backfill, meses do backfill).
function useNumberDraft(committed: number | undefined, fallback: number) {
  const [draft, setDraft] = useState(String(committed ?? fallback));
  useEffect(() => {
    setDraft(String(committed ?? fallback));
  }, [committed, fallback]);
  return [draft, setDraft] as const;
}

export function OpaSyncPanel({
  canSync,
  syncStatus,
  settings,
  savingSettings,
  months,
  monthsLoading,
  onDraftSettings,
  onSaveSettings,
  onReimportMonth,
}: {
  canSync: boolean;
  syncStatus: SupportOpaSyncStatus | null;
  settings: SupportOpaSyncSettings | null;
  savingSettings: boolean;
  months: SupportOpaImportMonth[];
  monthsLoading: boolean;
  onDraftSettings: (next: Partial<SupportOpaSyncSettings>) => void;
  onSaveSettings: (next: Partial<SupportOpaSyncSettings>) => void;
  onReimportMonth: (yearMonth: string) => void;
}) {
  const [intervalDraft, setIntervalDraft] = useNumberDraft(settings?.interval_minutes, 20);
  const [lookbackDraft, setLookbackDraft] = useNumberDraft(settings?.lookback_days, 1);
  const [runHourDraft, setRunHourDraft] = useNumberDraft(settings?.backfill_run_hour, 3);
  const [backfillMonthsDraft, setBackfillMonthsDraft] = useNumberDraft(settings?.backfill_lookback_months, 3);
  const [dimensionsRefreshDraft, setDimensionsRefreshDraft] = useNumberDraft(settings?.dimensions_refresh_hours, 24);

  function commit(draft: string, min: number, max: number, fallback: number, apply: (value: number) => void) {
    const parsed = Number(draft);
    const value = draft.trim() === "" || Number.isNaN(parsed) ? fallback : Math.min(Math.max(Math.round(parsed), min), max);
    apply(value);
  }

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
      {(() => {
        const headline = syncHeadline(syncStatus);
        const styles = SYNC_HEADLINE_STYLES[headline.tone];
        return (
          <div className={`mt-4 flex items-start gap-3 rounded-xl border p-4 ${styles.box}`}>
            <SyncHeadlineIcon tone={headline.tone} />
            <div>
              <p className="text-sm font-semibold">{headline.title}</p>
              {headline.detail ? <p className="mt-0.5 text-xs opacity-90">{headline.detail}</p> : null}
            </div>
          </div>
        );
      })()}
      {/* Falhas na sequência atual (contador reseta a cada sucesso) - só aparece quando há alguma,
          não precisa ocupar espaço quando está tudo em dia. */}
      {syncStatus && syncStatus.consecutive_failures > 0 ? (
        <p className="mt-2 text-xs text-red-700">{syncStatus.consecutive_failures} falha(s) seguida(s) antes desta tentativa.</p>
      ) : null}
      <p className="mt-3 text-xs text-slate-500">
        {syncStatus?.enabled ? "Automático" : "Automático desligado"} · a cada {settings?.interval_minutes ?? 20} min · reimporta
        os últimos {settings?.lookback_days ?? 1} dia(s) · atualiza nomes de cliente/atendente/motivo a cada{" "}
        {settings?.dimensions_refresh_hours ?? 24}h
      </p>
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
            value={intervalDraft}
            disabled={savingSettings || !settings}
            onChange={(event) => setIntervalDraft(event.target.value)}
            onBlur={() => commit(intervalDraft, 5, 1440, 20, (value) => onSaveSettings({ interval_minutes: value }))}
          />
        </label>
        <label className="block">
          <span className="text-xs font-medium text-slate-600">Reimportar últimos dias</span>
          <Input
            type="number"
            min={1}
            max={30}
            value={lookbackDraft}
            disabled={savingSettings || !settings}
            onChange={(event) => setLookbackDraft(event.target.value)}
            onBlur={() => commit(lookbackDraft, 1, 30, 1, (value) => onSaveSettings({ lookback_days: value }))}
          />
        </label>
        <label className="block">
          <span className="flex items-center gap-1 text-xs font-medium text-slate-600">
            Atualizar cadastros (horas)
            <InfoHint
              ariaLabel="Ajuda sobre atualização de cadastros"
              side="bottom"
              title="Usuários, motivos, departamentos, etiquetas e clientes"
              description="De quantas em quantas horas a sincronização refaz a busca completa desses cadastros no OPA Suite (só nomes/rótulos, não afeta os atendimentos em si). O cadastro de clientes sozinho tem mais de 100 mil registros - buscar ele em toda sincronização (a cada poucos minutos) era o maior custo do módulo. Entre uma atualização e outra, os nomes já conhecidos continuam sendo usados normalmente."
            />
          </span>
          <Input
            type="number"
            min={1}
            max={168}
            value={dimensionsRefreshDraft}
            disabled={savingSettings || !settings}
            onChange={(event) => setDimensionsRefreshDraft(event.target.value)}
            onBlur={() => commit(dimensionsRefreshDraft, 1, 168, 24, (value) => onSaveSettings({ dimensions_refresh_hours: value }))}
          />
        </label>
      </div>
      <div className="mt-4 flex items-center gap-2 text-slate-800">
        <Clock3 className="h-4 w-4" />
        <h4 className="text-sm font-semibold">Backfill automático de meses (madrugada)</h4>
        <InfoHint
          ariaLabel="Ajuda sobre o backfill automático"
          side="bottom"
          title="Meses completos, sem esperar clique manual"
          description="Todo dia, no horário configurado, o sistema verifica os últimos N meses e importa (mês inteiro) qualquer um que ainda não esteja completo - sem travar a tela, roda em background."
        />
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-3">
        <label className="flex items-center justify-between rounded-xl border border-slate-200 px-3 py-2 text-sm">
          <span className="font-medium text-slate-700">Ligado</span>
          <input
            type="checkbox"
            checked={Boolean(settings?.backfill_enabled ?? true)}
            disabled={savingSettings || !settings}
            onChange={(event) => onSaveSettings({ backfill_enabled: event.target.checked })}
            className="h-4 w-4 rounded border-slate-300"
          />
        </label>
        <label className="block">
          <span className="text-xs font-medium text-slate-600">Hora do dia (0-23)</span>
          <Input
            type="number"
            min={0}
            max={23}
            value={runHourDraft}
            disabled={savingSettings || !settings}
            onChange={(event) => setRunHourDraft(event.target.value)}
            onBlur={() => commit(runHourDraft, 0, 23, 3, (value) => onSaveSettings({ backfill_run_hour: value }))}
          />
        </label>
        <label className="block">
          <span className="text-xs font-medium text-slate-600">Meses verificados</span>
          <Input
            type="number"
            min={1}
            max={24}
            value={backfillMonthsDraft}
            disabled={savingSettings || !settings}
            onChange={(event) => setBackfillMonthsDraft(event.target.value)}
            onBlur={() => commit(backfillMonthsDraft, 1, 24, 3, (value) => onSaveSettings({ backfill_lookback_months: value }))}
          />
        </label>
      </div>
      <OpaImportMonthsPanel months={months} loading={monthsLoading} onReimport={onReimportMonth} />
    </div>
  );
}

const MONTH_STATUS_LABEL: Record<string, string> = {
  complete: "Completo",
  partial: "Parcial",
  missing: "Faltando",
};

const MONTH_STATUS_BADGE: Record<string, string> = {
  complete: "border-emerald-200 bg-emerald-50 text-emerald-700",
  partial: "border-amber-200 bg-amber-50 text-amber-700",
  missing: "border-slate-200 bg-slate-100 text-slate-600",
};

function monthLabel(yearMonth: string): string {
  const [year, month] = yearMonth.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, 1));
  return date.toLocaleDateString("pt-BR", { month: "short", year: "numeric", timeZone: "UTC" });
}

function OpaImportMonthsPanel({
  months,
  loading,
  onReimport,
}: {
  months: SupportOpaImportMonth[];
  loading: boolean;
  onReimport: (yearMonth: string) => void;
}) {
  return (
    <div className="mt-4">
      <div className="flex items-center gap-2 text-slate-800">
        <Database className="h-4 w-4" />
        <h4 className="text-sm font-semibold">Meses importados</h4>
      </div>
      <p className="mt-1 text-xs text-slate-500">
        "Completo" = já existiu uma importação de mês inteiro concluída com sucesso. Clique em "Reimportar" pra forçar de novo.
      </p>
      {loading ? (
        <div className="mt-2 h-16 animate-pulse rounded-xl bg-slate-100" />
      ) : (
        <ul className="mt-2 flex flex-wrap gap-2">
          {months.map((month) => (
            <li
              key={month.year_month}
              className="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-xs"
            >
              <span className="font-medium capitalize text-slate-700">{monthLabel(month.year_month)}</span>
              <Badge className={MONTH_STATUS_BADGE[month.status] ?? MONTH_STATUS_BADGE.missing}>
                {MONTH_STATUS_LABEL[month.status] ?? month.status}
              </Badge>
              <button
                type="button"
                onClick={() => onReimport(month.year_month)}
                className="font-medium text-blue-700 hover:underline"
              >
                Reimportar
              </button>
            </li>
          ))}
        </ul>
      )}
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
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 bg-slate-50/60 px-4 py-3">
        <div className="flex items-center gap-2">
          <Users className="h-4 w-4 text-blue-700" />
          <h3 className="text-sm font-semibold text-slate-950">Atendentes virtuais</h3>
          <Badge className="border-slate-200 bg-white text-slate-600">{number(overrides.length)} cadastrados</Badge>
        </div>
        <p className="mt-1 text-xs text-slate-500">
          Cadastre um <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[10.5px] text-slate-700">attendant_id</code> do
          OPA Suite pra ser sempre tratado como agente virtual — o painel individual passa a priorizar TMR geral pra
          ele, mesmo que o OPA nunca mande <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[10.5px] text-slate-700">tipo=&quot;bot&quot;</code>.
        </p>
      </div>

      <div className="grid gap-2 border-b border-slate-100 bg-slate-50/30 p-4 sm:grid-cols-[1fr_1fr_auto]">
        <Input placeholder="attendant_id do OPA Suite" value={attendantId} onChange={(event) => setAttendantId(event.target.value)} disabled={saving} />
        <Input placeholder="Nome (opcional)" value={attendantName} onChange={(event) => setAttendantName(event.target.value)} disabled={saving} />
        <Button type="button" onClick={submit} disabled={saving || !attendantId.trim()}>
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : "Cadastrar"}
        </Button>
      </div>

      {error ? <div className="mx-4 mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">{error}</div> : null}

      {loading ? (
        <div className="flex items-center gap-2 p-4 text-sm text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin" /> Carregando cadastro...
        </div>
      ) : (
        <div className="overflow-x-auto p-4">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Atendente</TableHead>
                <TableHead>Classificação</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {overrides.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4} className="py-10 text-center text-sm text-slate-500">
                    Nenhum atendente virtual cadastrado.
                  </TableCell>
                </TableRow>
              ) : (
                overrides.map((override) => (
                  <TableRow key={override.id}>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-blue-700 text-[11px] font-bold text-white">
                          {attendantInitials(override.attendant_name ?? override.attendant_id)}
                        </span>
                        <div className="min-w-0">
                          <p className="truncate font-medium text-slate-900">{override.attendant_name ?? "Sem nome cadastrado"}</p>
                          <p className="truncate font-mono text-[11px] text-slate-400">{override.attendant_id}</p>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge className="border-blue-100 bg-blue-50 text-blue-700">Agente virtual</Badge>
                    </TableCell>
                    <TableCell>
                      <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${override.active ? "text-emerald-700" : "text-slate-500"}`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${override.active ? "bg-emerald-500" : "bg-slate-400"}`} aria-hidden="true" />
                        {override.active ? "Ativo" : "Inativo"}
                      </span>
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
