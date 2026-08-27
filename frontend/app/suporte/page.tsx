"use client";

import Link from "next/link";
import {
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  Database,
  Eye,
  Home,
  Loader2,
  LogOut,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { type ReactNode, Suspense, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { StatusToast } from "@/components/ui/status-toast";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { NotificationBell } from "@/components/workspace/notification-bell";
import { ModuleNavigationSidebar } from "@/components/workspace/module-navigation-sidebar";
import { WorkspaceLogin } from "@/components/workspace/workspace-login";
import { useWorkspaceAuth } from "@/hooks/use-workspace-auth";
import { api } from "@/lib/api";
import {
  ACTIVE_OPA_TABS,
  BotHumanSummary,
  ChannelSummary,
  customerCodeLabel,
  customerNameLabel,
  dateTimeLabel,
  isTransientBusyMessage,
  number,
  OpaAttendantOverridesPanel,
  OpaGlobalFilters,
  OpaAttendantsPanel,
  OPA_NAV_ITEMS,
  OpaOverview,
  OpaSyncPanel,
  opaStatusLabel,
  secondsLabel,
  StatCell,
  StatusSummary,
  TimeMetricsStrip,
  tmrCoverageNote,
  TopReasonsSummary,
  TrendValue,
  type OpaModuleTab,
} from "@/app/suporte/_components/opa-module-components";
import { BotHumanChart, RankingChart, TimeTrendChart, VolumeTrendChart } from "@/app/suporte/_components/opa-charts";
import { OpaDrilldownSheet, type OpaDrilldown } from "@/app/suporte/_components/opa-drilldown";
import { OpaSavedFiltersBar } from "@/app/suporte/_components/opa-saved-filters";
import type {
  SupportOpaAttendanceDetail,
  SupportOpaAttendanceDetailData,
  SupportOpaAttendanceFilters,
  SupportOpaAttendanceListItem,
  SupportOpaAttendancePage,
  SupportOpaAttendanceTimeline,
  SupportOpaAttendantOverride,
  SupportOpaAttendantOverrideCreate,
  SupportOpaAttendantOverrideUpdate,
  SupportOpaAttendantSummary,
  SupportOpaBreakdownItem,
  SupportOpaBreakdowns,
  SupportOpaFilters,
  SupportOpaImportMonth,
  SupportOpaOverview,
  SupportOpaSyncSettings,
  SupportOpaSyncStatus,
  SupportOpaTimelineEvent,
  SupportOpaTimeseriesPoint,
} from "@/lib/types";

function SyncStatusIndicator({ syncStatus, onOpenSync }: { syncStatus: SupportOpaSyncStatus | null; onOpenSync: () => void }) {
  if (!syncStatus) return null;
  const hasError = Boolean(syncStatus.last_error) && !isTransientBusyMessage(syncStatus.last_error ?? "");
  const inProgress = syncStatus.sync_in_progress;
  const label = hasError
    ? "Sincronização com erro"
    : inProgress
      ? syncStatus.active_run_mode === "scheduled" ? "Sincronizando (automático)" : "Sincronizando"
      : syncStatus.enabled
        ? "Sincronização automática ativa"
        : "Sincronização automática desligada";
  const tone = hasError ? "border-red-200 bg-red-50 text-red-700" : inProgress ? "border-blue-200 bg-blue-50 text-blue-700" : "border-slate-200 bg-slate-50 text-slate-600";
  return (
    <button
      type="button"
      onClick={onOpenSync}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors hover:opacity-80 ${tone}`}
      title="Abrir aba de sincronização"
    >
      <span className={`h-1.5 w-1.5 rounded-full ${hasError ? "bg-red-500" : inProgress ? "bg-blue-500" : syncStatus.enabled ? "bg-emerald-500" : "bg-slate-400"}`} aria-hidden="true" />
      {inProgress ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
      {label}
    </button>
  );
}

// Versão compacta da janela de base importada (ver `ImportedDataWindowNote`
// em opa-module-components.tsx) pro cabeçalho — mesma informação, formato
// mínimo pra caber ao lado do status de sincronização sem competir com o
// título da página.
function ImportedBaseBadge({ window }: { window: SupportOpaOverview["imported_data_window"] | null | undefined }) {
  if (!window || !window.max_opened_at) return null;
  const maxLabel = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", timeZone: "America/Porto_Velho" }).format(new Date(window.max_opened_at));
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-medium text-slate-600"
      title="Data mais recente com atendimento importado da base local"
    >
      <Database className="h-3 w-3 text-slate-400" />
      Base até {maxLabel} · {number(window.total_attendances)}
    </span>
  );
}

function isoDate(value: Date) {
  return value.toISOString().slice(0, 10);
}

function defaultPeriod() {
  const now = new Date();
  return { date_from: isoDate(new Date(now.getFullYear(), now.getMonth(), 1)), date_to: isoDate(now) };
}

function dateTimeShort(value: string | null | undefined) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "America/Porto_Velho",
  }).format(new Date(value));
}

function protocolLabel(item: { protocol: string | null; source_id: string }) {
  return item.protocol?.trim() || `Código OPA ${item.source_id}`;
}

function overviewFilters(period: { date_from: string; date_to: string }, filters: SupportOpaAttendanceFilters): SupportOpaAttendanceFilters {
  return {
    date_from: period.date_from,
    date_to: period.date_to,
    date_basis: filters.date_basis,
    status: filters.status,
    channel: filters.channel,
    attendant_id: filters.attendant_id,
    department_id: filters.department_id,
    reason_id: filters.reason_id,
    customer: filters.customer,
    search: filters.search,
  };
}

function queryStringFor(tab: OpaModuleTab, period: { date_from: string; date_to: string }, filters: SupportOpaAttendanceFilters) {
  const params = new URLSearchParams();
  if (tab !== "overview") params.set("tab", tab);
  params.set("date_from", period.date_from);
  params.set("date_to", period.date_to);
  URL_FILTER_KEYS.forEach((key) => {
    const value = filters[key];
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  });
  return params.toString();
}

/** Chaves de filtro que trafegam na URL. Ida e volta usam a MESMA lista de
 *  propósito: quando eram duas listas soltas, um filtro novo entrava só na
 *  escrita ou só na leitura e o recorte não sobrevivia a um reload — foi
 *  exatamente o que aconteceu com `tag_id` na primeira validação ao vivo. */
const URL_FILTER_KEYS = [
  "date_basis",
  "status",
  "channel",
  "attendant_id",
  "department_id",
  "reason_id",
  "customer",
  "search",
  "tag_id",
  "customer_id",
  "rating_min",
  "rating_max",
  "bot_human",
] as const;

const BOT_HUMAN_VALUES = ["with_bot", "without_bot", "reached_human", "bot_only", "handoff", "unclassified"] as const;

function numberParam(params: URLSearchParams, key: string) {
  const raw = params.get(key);
  if (raw === null || raw.trim() === "") return undefined;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function filtersFromParams(params: URLSearchParams): SupportOpaAttendanceFilters {
  const dateBasis = params.get("date_basis");
  const botHuman = params.get("bot_human");
  return {
    page: 1,
    page_size: 25,
    sort_by: "opened_at",
    sort_dir: "desc",
    date_basis: dateBasis === "closed_at" ? "closed_at" : undefined,
    status: params.get("status") || undefined,
    channel: params.get("channel") || undefined,
    attendant_id: params.get("attendant_id") || undefined,
    department_id: params.get("department_id") || undefined,
    reason_id: params.get("reason_id") || undefined,
    customer: params.get("customer") || undefined,
    search: params.get("search") || undefined,
    tag_id: params.get("tag_id") || undefined,
    customer_id: params.get("customer_id") || undefined,
    rating_min: numberParam(params, "rating_min"),
    rating_max: numberParam(params, "rating_max"),
    // Valor fora da lista é descartado em vez de repassado: o backend
    // responderia 422 e a tela abriria quebrada por causa de um link torto.
    bot_human: BOT_HUMAN_VALUES.includes(botHuman as never)
      ? (botHuman as SupportOpaAttendanceFilters["bot_human"])
      : undefined,
  };
}

function periodFromParams(params: URLSearchParams) {
  const fallback = defaultPeriod();
  return {
    date_from: params.get("date_from") || fallback.date_from,
    date_to: params.get("date_to") || fallback.date_to,
  };
}

export default function SupportPage() {
  return (
    <Suspense
      fallback={<main className="flex min-h-screen items-center justify-center text-sm text-slate-500">Carregando SGP Suporte...</main>}
    >
      <SupportPageContent />
    </Suspense>
  );
}

function SupportPageContent() {
  const { user, checking, error: authError, login, logout } = useWorkspaceAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const initialQueryParams = useMemo(() => new URLSearchParams(searchParams.toString()), [searchParams]);
  const initialPeriod = useMemo(() => periodFromParams(initialQueryParams), [initialQueryParams]);
  const initialFilters = useMemo(() => filtersFromParams(initialQueryParams), [initialQueryParams]);
  const initialTab = useMemo<OpaModuleTab>(() => {
    const tab = initialQueryParams.get("tab") as OpaModuleTab | null;
    if (tab === "agents") return "attendants";
    return tab && ACTIVE_OPA_TABS.includes(tab) ? tab : "overview";
  }, [initialQueryParams]);
  const [period, setPeriod] = useState(initialPeriod);
  const [appliedPeriod, setAppliedPeriod] = useState(initialPeriod);
  const [overview, setOverview] = useState<SupportOpaOverview | null>(null);
  const [timeseries, setTimeseries] = useState<SupportOpaTimeseriesPoint[]>([]);
  const [timeseriesLoading, setTimeseriesLoading] = useState(false);
  const [overviewRanking, setOverviewRanking] = useState<SupportOpaBreakdownItem[]>([]);
  const [overviewRankingLoading, setOverviewRankingLoading] = useState(false);
  const [drilldown, setDrilldown] = useState<OpaDrilldown | null>(null);
  const [activeView, setActiveView] = useState<OpaModuleTab>(initialTab);
  const [attendancePage, setAttendancePage] = useState<SupportOpaAttendancePage | null>(null);
  const [attendanceFilters, setAttendanceFilters] = useState<SupportOpaAttendanceFilters>(initialFilters);
  const [attendantBreakdown, setAttendantBreakdown] = useState<SupportOpaBreakdowns | null>(null);
  const [attendantBreakdownLoading, setAttendantBreakdownLoading] = useState(false);
  const [attendantSortBy, setAttendantSortBy] = useState("total");
  const [attendantSortDir, setAttendantSortDir] = useState<"asc" | "desc">("desc");
  const [selectedAttendant, setSelectedAttendant] = useState<SupportOpaBreakdownItem | null>(null);
  const [attendantRecentPage, setAttendantRecentPage] = useState<SupportOpaAttendancePage | null>(null);
  const [attendantRecentLoading, setAttendantRecentLoading] = useState(false);
  const [attendantRecentError, setAttendantRecentError] = useState<string | null>(null);
  const [attendantSummary, setAttendantSummary] = useState<SupportOpaAttendantSummary | null>(null);
  const [attendantSummaryLoading, setAttendantSummaryLoading] = useState(false);
  const [attendantSummaryError, setAttendantSummaryError] = useState<string | null>(null);
  const [filterOptions, setFilterOptions] = useState<SupportOpaFilters | null>(null);
  const [attendanceLoading, setAttendanceLoading] = useState(false);
  const [selectedAttendanceId, setSelectedAttendanceId] = useState<number | null>(null);
  const [attendanceDetail, setAttendanceDetail] = useState<SupportOpaAttendanceDetail | null>(null);
  const [attendanceDetailLoading, setAttendanceDetailLoading] = useState(false);
  const [attendanceDetailError, setAttendanceDetailError] = useState<string | null>(null);
  const [attendanceTimeline, setAttendanceTimeline] = useState<SupportOpaAttendanceTimeline | null>(null);
  const [attendanceTimelineLoading, setAttendanceTimelineLoading] = useState(false);
  const [attendanceTimelineError, setAttendanceTimelineError] = useState<string | null>(null);
  const [syncStatus, setSyncStatus] = useState<SupportOpaSyncStatus | null>(null);
  const [settings, setSettings] = useState<SupportOpaSyncSettings | null>(null);
  const [importMonths, setImportMonths] = useState<SupportOpaImportMonth[]>([]);
  const [importMonthsLoading, setImportMonthsLoading] = useState(false);
  const [attendantOverrides, setAttendantOverrides] = useState<SupportOpaAttendantOverride[]>([]);
  const [attendantOverridesLoading, setAttendantOverridesLoading] = useState(false);
  const [attendantOverridesError, setAttendantOverridesError] = useState<string | null>(null);
  const [savingAttendantOverride, setSavingAttendantOverride] = useState(false);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canRead = Boolean(user?.permissions.includes("support:read"));
  const canSync = Boolean(user?.permissions.includes("support:sync_opa"));

  function updateUrl(tab: OpaModuleTab, nextPeriod = period, nextFilters: SupportOpaAttendanceFilters = attendanceFilters) {
    const query = queryStringFor(tab, nextPeriod, nextFilters);
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  function navigateToTab(tab: OpaModuleTab) {
    setActiveView(tab);
    updateUrl(tab);
  }

  async function load(nextPeriod = period, nextFilters: SupportOpaAttendanceFilters = attendanceFilters, tab = activeView, syncUrl = true) {
    setLoading(true);
    setError(null);
    try {
      if (syncUrl) updateUrl(tab, nextPeriod, nextFilters);
      const requests: Promise<unknown>[] = [
        api.supportOpaOverview(overviewFilters(nextPeriod, nextFilters)).then(setOverview),
        api.supportOpaFilters({ ...nextPeriod, date_basis: nextFilters.date_basis }).then(setFilterOptions),
      ];
      if (canSync) {
        requests.push(api.supportOpaSyncStatus().then(setSyncStatus));
        requests.push(api.supportOpaSyncSettings().then(setSettings));
        requests.push(loadImportMonths());
      }
      await Promise.all(requests);
      setAppliedPeriod(nextPeriod);
      setAttendanceFilters((current) => ({ ...current, ...nextFilters, date_from: nextPeriod.date_from, date_to: nextPeriod.date_to, page: 1 }));
      if (tab === "overview") {
        // Gráficos são decomposições do MESMO recorte dos cards — carregam
        // junto, com os mesmos filtros, e nunca por outro caminho de cálculo.
        void loadOverviewCharts(nextPeriod, nextFilters);
      }
      if (tab === "data") {
        await loadAttendances({ ...overviewFilters(nextPeriod, nextFilters), page: 1 });
      }
      if (tab === "attendants") {
        await loadAttendantBreakdown(nextPeriod, nextFilters);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao carregar o SGP Suporte.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (user && canRead) void load(initialPeriod);
    // Carga inicial unica; filtros sao aplicados pelo botao.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, canRead, canSync]);

  useEffect(() => {
    if (!user || !canRead || activeView !== "data") return;
    void loadAttendances({ date_from: appliedPeriod.date_from, date_to: appliedPeriod.date_to, date_basis: attendanceFilters.date_basis, page: attendanceFilters.page ?? 1 });
    if (!filterOptions) void api.supportOpaFilters({ ...appliedPeriod, date_basis: attendanceFilters.date_basis }).then(setFilterOptions).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeView]);

  useEffect(() => {
    if (!user || !canRead || activeView !== "attendants") return;
    void loadAttendantBreakdown(appliedPeriod, attendanceFilters);
    if (!filterOptions) void api.supportOpaFilters({ ...appliedPeriod, date_basis: attendanceFilters.date_basis }).then(setFilterOptions).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeView, attendantSortBy, attendantSortDir]);

  useEffect(() => {
    if (!user || !canSync || activeView !== "sync") return;
    void loadAttendantOverrides();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeView]);

  async function loadAttendantOverrides() {
    setAttendantOverridesLoading(true);
    setAttendantOverridesError(null);
    try {
      const items = await api.supportOpaAttendantOverrides();
      setAttendantOverrides(items);
    } catch (reason) {
      setAttendantOverridesError(reason instanceof Error ? reason.message : "Falha ao carregar o cadastro de atendentes virtuais.");
    } finally {
      setAttendantOverridesLoading(false);
    }
  }

  async function createAttendantOverride(payload: SupportOpaAttendantOverrideCreate) {
    setSavingAttendantOverride(true);
    setAttendantOverridesError(null);
    try {
      await api.createSupportOpaAttendantOverride(payload);
      await loadAttendantOverrides();
    } catch (reason) {
      setAttendantOverridesError(reason instanceof Error ? reason.message : "Falha ao cadastrar o atendente.");
    } finally {
      setSavingAttendantOverride(false);
    }
  }

  async function updateAttendantOverride(id: number, payload: SupportOpaAttendantOverrideUpdate) {
    setSavingAttendantOverride(true);
    setAttendantOverridesError(null);
    try {
      await api.updateSupportOpaAttendantOverride(id, payload);
      await loadAttendantOverrides();
    } catch (reason) {
      setAttendantOverridesError(reason instanceof Error ? reason.message : "Falha ao atualizar o cadastro.");
    } finally {
      setSavingAttendantOverride(false);
    }
  }

  async function deleteAttendantOverride(id: number) {
    setSavingAttendantOverride(true);
    setAttendantOverridesError(null);
    try {
      await api.deleteSupportOpaAttendantOverride(id);
      await loadAttendantOverrides();
    } catch (reason) {
      setAttendantOverridesError(reason instanceof Error ? reason.message : "Falha ao remover o cadastro.");
    } finally {
      setSavingAttendantOverride(false);
    }
  }

  function clearFilters() {
    const clearedPeriod = defaultPeriod();
    const clearedFilters: SupportOpaAttendanceFilters = {
      page: 1,
      page_size: attendanceFilters.page_size ?? 25,
      sort_by: attendanceFilters.sort_by ?? "opened_at",
      sort_dir: attendanceFilters.sort_dir ?? "desc",
    };
    setPeriod(clearedPeriod);
    setAttendanceFilters(clearedFilters);
    router.replace(activeView === "overview" ? pathname : `${pathname}?tab=${activeView}`, { scroll: false });
    void load(clearedPeriod, clearedFilters, activeView, false);
  }

  async function loadAttendances(next: Partial<SupportOpaAttendanceFilters> = {}) {
    const merged = {
      ...attendanceFilters,
      ...next,
      date_from: next.date_from ?? attendanceFilters.date_from ?? appliedPeriod.date_from,
      date_to: next.date_to ?? attendanceFilters.date_to ?? appliedPeriod.date_to,
    };
    setAttendanceLoading(true);
    setError(null);
    try {
      const pageData = await api.supportOpaAttendances(merged);
      setAttendanceFilters(merged);
      setAttendancePage(pageData);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao carregar atendimentos OPA.");
    } finally {
      setAttendanceLoading(false);
    }
  }

  async function loadOverviewCharts(
    nextPeriod = appliedPeriod,
    nextFilters: SupportOpaAttendanceFilters = attendanceFilters,
  ) {
    const scoped = overviewFilters(nextPeriod, nextFilters);
    setTimeseriesLoading(true);
    setOverviewRankingLoading(true);
    // Os dois gráficos são independentes: um falhar não pode apagar o outro,
    // por isso `allSettled` em vez de `all`.
    const [seriesResult, rankingResult] = await Promise.allSettled([
      api.supportOpaTimeseries(scoped),
      api.supportOpaBreakdowns("attendant", { ...scoped, sort_by: "total", sort_dir: "desc", limit: 8 }),
    ]);
    setTimeseries(seriesResult.status === "fulfilled" ? seriesResult.value.points : []);
    setOverviewRanking(rankingResult.status === "fulfilled" ? rankingResult.value.items : []);
    setTimeseriesLoading(false);
    setOverviewRankingLoading(false);
  }

  async function loadAttendantBreakdown(
    nextPeriod = appliedPeriod,
    nextFilters: SupportOpaAttendanceFilters = attendanceFilters,
    sortBy = attendantSortBy,
    sortDir = attendantSortDir,
  ) {
    setAttendantBreakdownLoading(true);
    setError(null);
    try {
      const data = await api.supportOpaBreakdowns("attendant", {
        ...overviewFilters(nextPeriod, nextFilters),
        sort_by: sortBy,
        sort_dir: sortDir,
        limit: 200,
      });
      setAttendantBreakdown(data);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao carregar atendentes OPA.");
    } finally {
      setAttendantBreakdownLoading(false);
    }
  }

  function changeAttendantSort(sortBy: string) {
    const nextDir = attendantSortBy === sortBy && attendantSortDir === "desc" ? "asc" : "desc";
    setAttendantSortBy(sortBy);
    setAttendantSortDir(nextDir);
  }

  function openAttendantDrawer(attendant: SupportOpaBreakdownItem) {
    setSelectedAttendant(attendant);
    setAttendantRecentPage(null);
    setAttendantRecentError(null);
    setAttendantSummary(null);
    setAttendantSummaryError(null);
    if (attendant.id) {
      void loadAttendantRecentAttendances(attendant.id);
      void loadAttendantSummary(attendant.id);
    }
  }

  async function loadAttendantRecentAttendances(attendantId: string) {
    setAttendantRecentLoading(true);
    setAttendantRecentError(null);
    try {
      const data = await api.supportOpaAttendances({
        ...overviewFilters(appliedPeriod, attendanceFilters),
        attendant_id: attendantId,
        page: 1,
        page_size: 8,
        sort_by: "opened_at",
        sort_dir: "desc",
      });
      setAttendantRecentPage(data);
    } catch (reason) {
      setAttendantRecentError(reason instanceof Error ? reason.message : "Falha ao carregar atendimentos do atendente.");
    } finally {
      setAttendantRecentLoading(false);
    }
  }

  async function loadAttendantSummary(attendantId: string) {
    setAttendantSummaryLoading(true);
    setAttendantSummaryError(null);
    try {
      const data = await api.supportOpaAttendantSummary(attendantId, overviewFilters(appliedPeriod, attendanceFilters));
      setAttendantSummary(data);
    } catch (reason) {
      setAttendantSummaryError(reason instanceof Error ? reason.message : "Falha ao carregar o painel individual do atendente.");
    } finally {
      setAttendantSummaryLoading(false);
    }
  }

  function navigateToAttendantData(attendantId: string) {
    const nextFilters: SupportOpaAttendanceFilters = { ...attendanceFilters, attendant_id: attendantId, page: 1 };
    setAttendanceFilters(nextFilters);
    setSelectedAttendant(null);
    setActiveView("data");
    updateUrl("data", appliedPeriod, nextFilters);
    void loadAttendances({ ...overviewFilters(appliedPeriod, nextFilters), page: 1 });
  }

  async function loadAttendanceTimeline(id: number) {
    setAttendanceTimelineLoading(true);
    setAttendanceTimelineError(null);
    try {
      const timeline = await api.supportOpaAttendanceTimeline(id);
      setAttendanceTimeline(timeline);
    } catch (reason) {
      setAttendanceTimelineError(reason instanceof Error ? reason.message : "Falha ao carregar a timeline do atendimento.");
    } finally {
      setAttendanceTimelineLoading(false);
    }
  }

  async function openAttendanceDetail(id: number) {
    setSelectedAttendanceId(id);
    setAttendanceDetail(null);
    setAttendanceDetailError(null);
    setAttendanceDetailLoading(true);
    setAttendanceTimeline(null);
    setAttendanceTimelineError(null);
    void loadAttendanceTimeline(id);
    try {
      const detail = await api.supportOpaAttendanceDetail(id);
      setAttendanceDetail(detail);
      const customerName = detail.enriched?.customer_name || detail.local.customer_name;
      const customerId = detail.enriched?.customer_id || detail.local.customer_id;
      if (customerName || customerId) {
        setAttendancePage((current) => current ? {
          ...current,
          items: current.items.map((item) => item.id === id ? { ...item, customer_name: customerName ?? item.customer_name, customer_id: customerId ?? item.customer_id } : item),
        } : current);
        setAttendantRecentPage((current) => current ? {
          ...current,
          items: current.items.map((item) => item.id === id ? { ...item, customer_name: customerName ?? item.customer_name, customer_id: customerId ?? item.customer_id } : item),
        } : current);
      }
    } catch (reason) {
      setAttendanceDetailError(reason instanceof Error ? reason.message : "Falha ao carregar detalhe do atendimento OPA.");
    } finally {
      setAttendanceDetailLoading(false);
    }
  }

  async function loadImportMonths() {
    setImportMonthsLoading(true);
    try {
      setImportMonths(await api.supportOpaImportMonths());
    } catch {
      // Painel é auxiliar - uma falha aqui não deve derrubar o resto da tela.
    } finally {
      setImportMonthsLoading(false);
    }
  }

  // Achado real de 2026-08-27: import de mês inteiro busca mensagem por mensagem
  // pra calcular TMR e podia levar minutos rodando dentro da requisição HTTP
  // (risco de timeout). Agora o backend devolve o run_id na hora e processa em
  // background - aqui só ficamos perguntando o status a cada 2s até terminar,
  // mesmo padrão já usado pelo sync do IXC na tela de Agendamento.
  async function runImportJob(dateFrom: string, dateTo: string) {
    setSyncing(true);
    setError(null);
    setMessage(null);
    try {
      let result = await api.importSupportOpaPeriod({ date_from: dateFrom, date_to: dateTo });
      while (result.status === "pending" || result.status === "running") {
        await new Promise((resolve) => window.setTimeout(resolve, 2000));
        result = await api.supportOpaSyncRun(result.run_id);
      }
      if (result.status === "failed") {
        throw new Error("Falha ao importar o período selecionado do OPA Suite.");
      }
      setMessage(
        `Run #${result.run_id}: ${result.fetched_count} recebido(s) em ${result.pages_processed} página(s), ${result.created_count} criado(s), ` +
        `${result.updated_count} atualizado(s), ${result.unchanged_count} sem alteração, ${result.rejected_count} rejeitado(s).`,
      );
      window.dispatchEvent(new Event("notifications:refresh"));
      await load(period);
      await loadImportMonths();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao importar dados do OPA Suite.");
    } finally {
      setSyncing(false);
    }
  }

  async function importPeriod() {
    await runImportJob(period.date_from, period.date_to);
  }

  async function reimportMonth(yearMonth: string) {
    const [year, month] = yearMonth.split("-").map(Number);
    const dateFrom = `${yearMonth}-01`;
    const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate();
    const dateTo = `${yearMonth}-${String(lastDay).padStart(2, "0")}`;
    await runImportJob(dateFrom, dateTo);
  }

  async function saveSettings(next: Partial<SupportOpaSyncSettings>) {
    setSavingSettings(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await api.updateSupportOpaSyncSettings(next);
      setSettings(saved);
      await api.supportOpaSyncStatus().then(setSyncStatus);
      setMessage("Configuração de sincronização salva.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao salvar configuração.");
    } finally {
      setSavingSettings(false);
    }
  }

  if (checking && !user) {
    return <main className="flex min-h-screen items-center justify-center text-sm text-slate-500">Carregando SGP Suporte...</main>;
  }
  if (!user) return <WorkspaceLogin isLoading={checking} error={authError} onLogin={login} />;

  if (!canRead) {
    return (
      <main className="min-h-screen bg-slate-50 p-6">
        <div className="mx-auto max-w-3xl rounded-2xl border border-amber-200 bg-amber-50 p-6 text-amber-900">
          <h1 className="text-xl font-semibold">Acesso ao SGP necessário</h1>
          <p className="mt-2 text-sm">Seu usuário não possui permissão support:read.</p>
          <Link href="/" className="mt-4 inline-flex text-sm font-semibold text-amber-800">Voltar ao ecossistema</Link>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 shadow-[0_1px_0_0_rgba(37,99,235,0.35)] backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-4 px-4 py-3 lg:px-7">
          <div className="flex items-center gap-3">
            <ModuleNavigationSidebar
              title="SGP Suporte"
              description="Navegação modular do UNI Workspace"
              items={OPA_NAV_ITEMS.filter((item) => ACTIVE_OPA_TABS.includes(item.value))}
              activeItem={activeView}
              onChange={navigateToTab}
              footer="Novas áreas do SGP Suporte serão incluídas neste menu."
            />
            <Link
              href="/"
              aria-label="Voltar ao ecossistema"
              className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50 text-blue-700"
            >
              <Home className="h-5 w-5" />
            </Link>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-blue-600">UNI Workspace</p>
              <h1 className="text-base font-semibold text-slate-950">SGP Suporte</h1>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <NotificationBell />
            <Button type="button" variant="ghost" onClick={logout}><LogOut className="h-4 w-4" /> Sair</Button>
          </div>
        </div>
      </header>

      <section className="flex flex-wrap items-center justify-between gap-2 px-4 pb-1 pt-4 lg:px-7">
        <div className="flex min-w-0 items-baseline gap-2">
          <h2 className="text-lg font-semibold text-slate-950">Atendimentos do Suporte</h2>
          <p className="truncate text-xs text-slate-500">Dados sincronizados do OPA Suite</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ImportedBaseBadge window={overview?.imported_data_window} />
          {canSync ? <SyncStatusIndicator syncStatus={syncStatus} onOpenSync={() => navigateToTab("sync")} /> : null}
        </div>
      </section>

      <StatusToast error={error} message={message} onDismissError={() => setError(null)} onDismissMessage={() => setMessage(null)} />

      <OpaGlobalFilters
        period={period}
        filters={attendanceFilters}
        options={filterOptions}
        loading={loading}
        canSync={canSync}
        syncing={syncing}
        canImport={Boolean(syncStatus?.configured)}
        importedDataWindow={overview?.imported_data_window ?? null}
        onPeriodChange={setPeriod}
        onFilterChange={(patch) => setAttendanceFilters((current) => ({ ...current, ...patch }))}
        onApply={() => void load(period, { ...attendanceFilters, page: 1 }, activeView)}
        onClear={clearFilters}
        onImport={() => void importPeriod()}
      />

      <OpaSavedFiltersBar
        period={period}
        filters={attendanceFilters}
        canPublishGlobal={canSync}
        onApply={(saved) => {
          // Um recorte salvo substitui o recorte inteiro — aplicar por cima do
          // que já está na tela misturaria dois filtros e daria um terceiro
          // resultado que o usuário nunca salvou.
          const nextPeriod = {
            date_from: String(saved.date_from ?? period.date_from),
            date_to: String(saved.date_to ?? period.date_to),
          };
          const nextFilters: SupportOpaAttendanceFilters = {
            page: 1,
            page_size: attendanceFilters.page_size ?? 25,
            sort_by: attendanceFilters.sort_by ?? "opened_at",
            sort_dir: attendanceFilters.sort_dir ?? "desc",
            date_basis: saved.date_basis === "closed_at" ? "closed_at" : undefined,
            status: saved.status ? String(saved.status) : undefined,
            channel: saved.channel ? String(saved.channel) : undefined,
            attendant_id: saved.attendant_id ? String(saved.attendant_id) : undefined,
            department_id: saved.department_id ? String(saved.department_id) : undefined,
            reason_id: saved.reason_id ? String(saved.reason_id) : undefined,
            customer: saved.customer ? String(saved.customer) : undefined,
            search: saved.search ? String(saved.search) : undefined,
            tag_id: saved.tag_id ? String(saved.tag_id) : undefined,
            customer_id: saved.customer_id ? String(saved.customer_id) : undefined,
            rating_min: saved.rating_min === undefined ? undefined : Number(saved.rating_min),
            rating_max: saved.rating_max === undefined ? undefined : Number(saved.rating_max),
            bot_human: saved.bot_human ? (String(saved.bot_human) as SupportOpaAttendanceFilters["bot_human"]) : undefined,
          };
          setPeriod(nextPeriod);
          setAttendanceFilters(nextFilters);
          void load(nextPeriod, nextFilters, activeView);
        }}
      />

      <section className="px-4 py-6 lg:px-7">
        <div className="grid gap-5">
          {activeView === "overview" ? (
            <div className="grid gap-5">
              <div className="grid gap-3 xl:grid-cols-2">
                <VolumeTrendChart
                  points={timeseries}
                  loading={timeseriesLoading}
                  onSelectDay={(point) =>
                    setDrilldown({
                      title: `Atendimentos de ${dateLabel(point.day)}`,
                      subtitle: `${number(point.total)} atendimento(s) · ${number(point.closed)} encerrados · mesmo recorte de filtros da tela`,
                      filters: { date_from: point.day, date_to: point.day },
                    })
                  }
                />
                <TimeTrendChart points={timeseries} loading={timeseriesLoading} />
              </div>
              <div className="grid gap-3 xl:grid-cols-[1.4fr_1fr]">
                <RankingChart
                  title="Atendentes com mais volume"
                  items={overviewRanking}
                  loading={overviewRankingLoading}
                  onSelect={(item) =>
                    item.id &&
                    setDrilldown({
                      title: item.label,
                      subtitle: `${number(item.total)} atendimento(s) · ${number(item.share_percentage, 1)}% do volume filtrado`,
                      filters: { attendant_id: item.id },
                    })
                  }
                />
                <BotHumanChart metrics={overview?.bot_human ?? null} loading={loading} />
              </div>
              <OpaOverview overview={overview} />
            </div>
          ) : null}
          {activeView === "attendants" ? (
            <OpaAttendantsPanel
              breakdown={attendantBreakdown}
              overview={overview}
              loading={attendantBreakdownLoading}
              sortBy={attendantSortBy}
              sortDir={attendantSortDir}
              onSort={changeAttendantSort}
              onOpenAttendant={openAttendantDrawer}
            />
          ) : null}
          {activeView === "data" ? (
            <AttendanceDataTable
              page={attendancePage}
              filters={attendanceFilters}
              loading={attendanceLoading}
              onChange={(next) => void loadAttendances({ ...next, page: next.page ?? 1 })}
              onOpenDetail={(id) => void openAttendanceDetail(id)}
            />
          ) : null}
          {activeView === "sync" ? (
            <div className="grid gap-5">
              <OpaSyncPanel
                canSync={canSync}
                syncStatus={syncStatus}
                settings={settings}
                savingSettings={savingSettings}
                months={importMonths}
                monthsLoading={importMonthsLoading}
                onDraftSettings={(next) => setSettings((current) => current ? { ...current, ...next } : current)}
                onSaveSettings={(next) => void saveSettings(next)}
                onReimportMonth={(yearMonth) => void reimportMonth(yearMonth)}
              />
              <OpaAttendantOverridesPanel
                canManage={canSync}
                overrides={attendantOverrides}
                loading={attendantOverridesLoading}
                error={attendantOverridesError}
                saving={savingAttendantOverride}
                onCreate={(payload) => void createAttendantOverride(payload)}
                onToggleActive={(id, active) => void updateAttendantOverride(id, { active })}
                onDelete={(id) => void deleteAttendantOverride(id)}
              />
            </div>
          ) : null}
        </div>
      </section>
      <AttendanceDetailSheet
        open={selectedAttendanceId !== null}
        detail={attendanceDetail}
        loading={attendanceDetailLoading}
        error={attendanceDetailError}
        timeline={attendanceTimeline}
        timelineLoading={attendanceTimelineLoading}
        timelineError={attendanceTimelineError}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedAttendanceId(null);
            setAttendanceDetail(null);
            setAttendanceDetailError(null);
            setAttendanceTimeline(null);
            setAttendanceTimelineError(null);
          }
        }}
      />
      <OpaDrilldownSheet
        drilldown={drilldown}
        baseFilters={overviewFilters(appliedPeriod, attendanceFilters)}
        onOpenChange={(open) => {
          if (!open) setDrilldown(null);
        }}
        onOpenAttendance={(id) => {
          setDrilldown(null);
          void openAttendanceDetail(id);
        }}
      />
      <AttendantDetailSheet
        open={selectedAttendant !== null}
        attendant={selectedAttendant}
        period={appliedPeriod}
        recentPage={attendantRecentPage}
        loading={attendantRecentLoading}
        error={attendantRecentError}
        summary={attendantSummary}
        summaryLoading={attendantSummaryLoading}
        summaryError={attendantSummaryError}
        onViewAll={(attendantId) => navigateToAttendantData(attendantId)}
        onOpenAttendanceDetail={(id) => void openAttendanceDetail(id)}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedAttendant(null);
            setAttendantRecentPage(null);
            setAttendantRecentError(null);
            setAttendantSummary(null);
            setAttendantSummaryError(null);
          }
        }}
      />
    </main>
  );
}

function AttendanceDataTable({
  page,
  filters,
  loading,
  onChange,
  onOpenDetail,
}: {
  page: SupportOpaAttendancePage | null;
  filters: SupportOpaAttendanceFilters;
  loading: boolean;
  onChange: (next: Partial<SupportOpaAttendanceFilters>) => void;
  onOpenDetail: (id: number) => void;
}) {
  const items = page?.items ?? [];
  const currentPage = page?.page ?? filters.page ?? 1;
  const totalPages = page?.total_pages ?? 0;

  function sort(column: string) {
    const sameColumn = filters.sort_by === column;
    onChange({ sort_by: column, sort_dir: sameColumn && filters.sort_dir === "asc" ? "desc" : "asc", page: 1 });
  }

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 bg-slate-50/60 p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-2">
            <Database className="h-4 w-4 text-blue-700" />
            <h3 className="text-base font-semibold text-slate-950">Dados</h3>
            <Badge className="border-blue-100 bg-blue-50 text-blue-700">{number(page?.total ?? 0)} registros</Badge>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <select
              value={String(filters.page_size ?? 25)}
              onChange={(event) => onChange({ page_size: Number(event.target.value), page: 1 })}
              className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700"
            >
              {[25, 50, 100, 200].map((size) => <option key={size} value={size}>{size}/página</option>)}
            </select>
          </div>
        </div>
      </div>
      <div className="overflow-x-auto p-4">
        <Table className="min-w-[1080px]">
          <TableHeader>
            <TableRow>
              <SortableHead label="Abertura" active={filters.sort_by === "opened_at"} onClick={() => sort("opened_at")} />
              <TableHead>Protocolo</TableHead>
              <TableHead>Cliente</TableHead>
              <SortableHead label="Atendente" active={filters.sort_by === "attendant_name"} onClick={() => sort("attendant_name")} />
              <SortableHead label="Departamento" active={filters.sort_by === "department_name"} onClick={() => sort("department_name")} />
              <TableHead>Motivo</TableHead>
              <SortableHead label="Canal" active={filters.sort_by === "channel"} onClick={() => sort("channel")} />
              <TableHead>Status</TableHead>
              <TableHead className="text-right">TMA</TableHead>
              <TableHead className="text-right">Avaliação</TableHead>
              <TableHead className="text-right">Ação</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow><TableCell colSpan={11} className="py-10 text-center text-sm text-slate-500">Carregando atendimentos...</TableCell></TableRow>
            ) : null}
            {!loading && items.map((item, index) => <AttendanceRow key={item.id} item={item} zebra={index % 2 === 1} onOpenDetail={onOpenDetail} />)}
            {!loading && !items.length ? (
              <TableRow><TableCell colSpan={11} className="py-10 text-center text-sm text-slate-500">Não há atendimentos para os filtros aplicados.</TableCell></TableRow>
            ) : null}
          </TableBody>
        </Table>
      </div>
      <div className="flex flex-col gap-3 border-t border-slate-200 px-4 py-3 text-sm text-slate-600 sm:flex-row sm:items-center sm:justify-between">
        <span>Página {currentPage} de {totalPages || 1}</span>
        <div className="flex items-center gap-2">
          <Button type="button" variant="outline" disabled={loading || currentPage <= 1} onClick={() => onChange({ page: currentPage - 1 })}>
            <ChevronLeft className="h-4 w-4" /> Anterior
          </Button>
          <Button type="button" variant="outline" disabled={loading || totalPages === 0 || currentPage >= totalPages} onClick={() => onChange({ page: currentPage + 1 })}>
            Próxima <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}

function SortableHead({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <TableHead>
      <button type="button" onClick={onClick} className={`inline-flex items-center gap-1 ${active ? "text-blue-700" : ""}`}>
        {label}<ArrowUpDown className="h-3.5 w-3.5" />
      </button>
    </TableHead>
  );
}

function AttendanceStatusBadge({ status, closedAt }: { status: string | null; closedAt: string | null }) {
  const closed = Boolean(closedAt);
  return (
    <Badge className={closed ? "border-slate-200 bg-slate-50 text-slate-700" : "border-blue-100 bg-blue-50 text-blue-700"}>
      {opaStatusLabel(status)}
    </Badge>
  );
}

function AttendanceRow({ item, zebra, onOpenDetail }: { item: SupportOpaAttendanceListItem; zebra?: boolean; onOpenDetail: (id: number) => void }) {
  const customerName = item.customer_name?.trim();
  const customerId = item.customer_id?.trim();
  const customerCode = customerCodeLabel(customerId);
  return (
    <TableRow className={`cursor-pointer hover:bg-blue-50/40 ${zebra ? "bg-slate-50/50" : ""}`} onClick={() => onOpenDetail(item.id)}>
      <TableCell className="whitespace-nowrap tabular-nums">{dateTimeShort(item.opened_at)}</TableCell>
      <TableCell className="whitespace-nowrap font-mono text-[11px] text-slate-500">{protocolLabel(item)}</TableCell>
      <TableCell className="max-w-56" title={[customerName, customerCode].filter(Boolean).join(" - ")}>
        <div className="min-w-0">
          <p className="truncate font-medium text-slate-800">{customerNameLabel(customerName, customerId)}</p>
          {customerCode ? <p className="mt-0.5 truncate text-[11px] text-slate-500">{customerCode}</p> : null}
        </div>
      </TableCell>
      <TableCell className="max-w-48 truncate" title={item.attendant_name ?? ""}>{item.attendant_name ?? "-"}</TableCell>
      <TableCell className="max-w-48 truncate" title={item.department_name ?? ""}>{item.department_name ?? "-"}</TableCell>
      <TableCell className="max-w-52 truncate" title={item.reason_name ?? ""}>{item.reason_name ?? "-"}</TableCell>
      <TableCell>{item.channel ?? "-"}</TableCell>
      <TableCell><AttendanceStatusBadge status={item.status} closedAt={item.closed_at} /></TableCell>
      <TableCell className="text-right tabular-nums">{secondsLabel(item.tma_seconds)}</TableCell>
      <TableCell className="text-right tabular-nums">{number(item.rating, 2)}</TableCell>
      <TableCell className="text-right">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-label="Ver detalhes do atendimento"
          className="text-slate-500 hover:text-blue-700"
          onClick={(event) => {
            event.stopPropagation();
            onOpenDetail(item.id);
          }}
        >
          <Eye className="h-3.5 w-3.5" />
        </Button>
      </TableCell>
    </TableRow>
  );
}

function attendantInitials(label: string | null | undefined) {
  const words = (label ?? "").trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return `${words[0][0]}${words[words.length - 1][0]}`.toUpperCase();
}

function dateLabel(value: string) {
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T12:00:00Z`));
}

function AttendantDetailSheet({
  open,
  attendant,
  period,
  recentPage,
  loading,
  error,
  summary,
  summaryLoading,
  summaryError,
  onViewAll,
  onOpenAttendanceDetail,
  onOpenChange,
}: {
  open: boolean;
  attendant: SupportOpaBreakdownItem | null;
  period: { date_from: string; date_to: string };
  recentPage: SupportOpaAttendancePage | null;
  loading: boolean;
  error: string | null;
  summary: SupportOpaAttendantSummary | null;
  summaryLoading: boolean;
  summaryError: string | null;
  onViewAll: (attendantId: string) => void;
  onOpenAttendanceDetail: (id: number) => void;
  onOpenChange: (open: boolean) => void;
}) {
  const recentItems = recentPage?.items ?? [];
  const attendantId = attendant?.id ?? null;
  const ratingCoverage = attendant?.total ? (attendant.rating_count / attendant.total) * 100 : null;
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-4xl">
        <SheetHeader className="border-b border-slate-100 bg-gradient-to-br from-slate-50 to-white">
          <div className="flex items-center gap-3.5">
            <span
              className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl text-base font-bold shadow-sm ${
                summary?.attendant_type === "bot"
                  ? "bg-gradient-to-br from-blue-500 to-blue-700 text-white"
                  : "bg-gradient-to-br from-slate-600 to-slate-800 text-white"
              }`}
              aria-hidden="true"
            >
              {attendantInitials(attendant?.label)}
            </span>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <SheetTitle className="text-xl">{attendant?.label ?? "Atendente"}</SheetTitle>
                {summary?.attendant_type ? (
                  <Badge className={summary.attendant_type === "bot" ? "border-blue-100 bg-blue-50 text-blue-700" : "border-slate-200 bg-slate-50 text-slate-700"}>
                    {summary.attendant_type === "bot" ? "Agente virtual" : "Atendente humano"}
                  </Badge>
                ) : null}
              </div>
              {attendant ? (
                <p className="text-sm text-slate-600">
                  {number(attendant.total)} atendimento(s) · {number(attendant.closure_rate, 1)}% encerrados · avaliação média {number(attendant.avg_rating, 2)}
                </p>
              ) : null}
            </div>
          </div>
          <SheetDescription>
            Período: {dateLabel(period.date_from)} até {dateLabel(period.date_to)}
          </SheetDescription>
        </SheetHeader>

        {attendant ? (
          <div className="mt-5 grid gap-5">
            <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
              <div className="grid divide-y divide-slate-100 lg:grid-cols-[1fr_1.6fr] lg:items-stretch lg:divide-x lg:divide-y-0">
                <div className="flex flex-col justify-center p-4">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Volume no período</p>
                  <div className="mt-2 flex items-baseline gap-3">
                    <p className="text-4xl font-bold tabular-nums text-slate-950">{number(attendant.total)}</p>
                    <TrendValue value={attendant.total_change_percentage} suffix="%" />
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Badge className="border-slate-200 bg-slate-50 text-slate-700">{number(attendant.closed)} encerrados</Badge>
                    <Badge className="border-slate-200 bg-slate-50 text-slate-700">{number(attendant.open)} em aberto</Badge>
                  </div>
                </div>
                <div className="grid grid-cols-2 divide-x divide-y divide-slate-100 sm:divide-y-0 sm:grid-cols-4">
                  <StatCell label="Taxa de encerramento" value={`${number(attendant.closure_rate, 1)}%`} trend={attendant.closure_rate_change_pp} trendSuffix=" p.p." />
                  <StatCell label="Duração média" value={secondsLabel(attendant.avg_duration_seconds)} trend={attendant.avg_duration_change_percentage} />
                  <StatCell label="Avaliação média" value={number(attendant.avg_rating, 2)} trend={attendant.avg_rating_change} trendSuffix="" />
                  <StatCell label="Cobertura de avaliação" value={ratingCoverage === null ? "-" : `${number(ratingCoverage, 1)}%`} helper={`${number(attendant.rating_count)} avaliação(ões)`} />
                </div>
              </div>
            </section>

            <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
              <div className="border-b border-slate-100 px-4 py-3">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Painel individual</h3>
                <p className="mt-1 text-xs text-slate-400">
                  TMR humano, TMR geral, 1ª resposta, clientes e classificação bot/humano no mesmo recorte de filtros aplicado na tela.
                </p>
              </div>

              {summaryLoading ? (
                <div className="flex min-h-32 items-center justify-center gap-2 p-4 text-sm text-slate-500">
                  <Loader2 className="h-4 w-4 animate-spin" /> Carregando painel individual...
                </div>
              ) : null}

              {!summaryLoading && summaryError ? (
                <div className="m-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{summaryError}</div>
              ) : null}

              {!summaryLoading && !summaryError && summary ? (
                <div className="grid gap-5 p-4">
                  {summary.attendant_type === "bot" ? (
                    <div className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-800">
                      Agente virtual — TMR geral é a métrica de referência aqui; TMR humano não se aplica (não há atendente humano nesta conversa).
                    </div>
                  ) : null}
                  <div>
                    <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Tempos</p>
                    <TimeMetricsStrip
                      items={
                        summary.attendant_type === "bot"
                          ? [
                              { label: "TMA médio", value: secondsLabel(summary.average_tma_seconds), helper: "atendimentos encerrados" },
                              { label: "TMR geral", value: secondsLabel(summary.average_tmr_all_responses_seconds), helper: "métrica principal do agente virtual", emphasis: true },
                              { label: "TMR humano", value: secondsLabel(summary.average_tmr_seconds), helper: "não aplicável a agente virtual", muted: true },
                              { label: "1ª resposta humana", value: secondsLabel(summary.average_first_response_seconds) },
                            ]
                          : [
                              { label: "TMA médio", value: secondsLabel(summary.average_tma_seconds), helper: "atendimentos encerrados" },
                              { label: "TMR humano", value: secondsLabel(summary.average_tmr_seconds), helper: "exclui respostas automáticas", emphasis: true },
                              { label: "TMR geral", value: secondsLabel(summary.average_tmr_all_responses_seconds), helper: "inclui respostas automáticas" },
                              { label: "1ª resposta humana", value: secondsLabel(summary.average_first_response_seconds) },
                            ]
                      }
                      note={tmrCoverageNote(summary.tmr_all_responses_coverage)}
                    />
                  </div>

                  <div>
                    <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Clientes e automação</p>
                    <div className="grid gap-3 lg:grid-cols-2">
                      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
                        <div className="grid grid-cols-2 divide-x divide-y divide-slate-100 sm:divide-y-0">
                          <StatCell label="Clientes únicos" value={number(summary.customers.unique_customers)} helper={`${number(summary.customers.average_attendances_per_customer, 1)} atend./cliente`} />
                          <StatCell label="Reincidentes" value={number(summary.customers.recurring_customers)} helper={`${number(summary.customers.recurring_customers_percentage, 1)}% dos únicos`} />
                          <StatCell label="Total no recorte" value={number(summary.total_attendances)} helper={`${number(summary.closed_attendances)} encerrados · ${number(summary.open_attendances)} em aberto`} />
                          <StatCell label="Avaliação média" value={number(summary.average_rating, 2)} helper={`${number(summary.rating_count)} avaliação(ões)`} />
                        </div>
                      </div>
                      <BotHumanSummary metrics={summary.bot_human} />
                    </div>
                  </div>

                  <div>
                    <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Distribuição</p>
                    <div className="grid gap-3 lg:grid-cols-2">
                      <ChannelSummary items={summary.by_channel} />
                      <StatusSummary items={summary.by_status} />
                    </div>
                    <div className="mt-3">
                      <TopReasonsSummary items={summary.by_reason} />
                    </div>
                  </div>
                </div>
              ) : null}

              {!summaryLoading && !summaryError && !summary ? (
                <div className="p-6 text-center text-sm text-slate-500">
                  Sem dados suficientes para montar o painel individual neste recorte de filtros.
                </div>
              ) : null}
            </section>

            <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
              <div className="flex flex-col gap-3 border-b border-slate-200 p-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-slate-950">Atendimentos recentes</h3>
                  <p className="text-xs text-slate-500">{number(recentPage?.total ?? 0)} atendimento(s) no recorte atual</p>
                </div>
                {attendantId ? (
                  <Button type="button" variant="outline" size="sm" onClick={() => onViewAll(attendantId)}>
                    Ver todos os atendimentos
                  </Button>
                ) : null}
              </div>

              {loading ? (
                <div className="flex min-h-32 items-center justify-center gap-2 text-sm text-slate-500">
                  <Loader2 className="h-4 w-4 animate-spin" /> Carregando atendimentos...
                </div>
              ) : null}

              {!loading && error ? (
                <div className="m-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>
              ) : null}

              {!loading && !error ? (
                <div className="overflow-x-auto">
                  <Table className="min-w-[640px]">
                    <TableHeader>
                      <TableRow>
                        <TableHead>Abertura</TableHead>
                        <TableHead>Protocolo</TableHead>
                        <TableHead>Cliente</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead className="text-right">Ação</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {recentItems.map((item) => (
                        <TableRow key={item.id} className="hover:bg-slate-50">
                          <TableCell className="whitespace-nowrap tabular-nums">{dateTimeShort(item.opened_at)}</TableCell>
                          <TableCell className="font-medium text-slate-900">{protocolLabel(item)}</TableCell>
                          <TableCell className="max-w-56" title={[item.customer_name, customerCodeLabel(item.customer_id)].filter(Boolean).join(" - ")}>
                            <div className="min-w-0">
                              <p className="truncate font-medium text-slate-800">{customerNameLabel(item.customer_name, item.customer_id)}</p>
                              {customerCodeLabel(item.customer_id) ? <p className="mt-0.5 truncate text-[11px] text-slate-500">{customerCodeLabel(item.customer_id)}</p> : null}
                            </div>
                          </TableCell>
                          <TableCell>{opaStatusLabel(item.status)}</TableCell>
                          <TableCell className="text-right">
                            <Button type="button" variant="ghost" size="sm" onClick={() => onOpenAttendanceDetail(item.id)}>
                              <Eye className="h-3.5 w-3.5" /> Detalhe
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                      {!recentItems.length ? (
                        <TableRow>
                          <TableCell colSpan={5} className="py-8 text-center text-sm text-slate-500">Nenhum atendimento encontrado para este atendente no recorte atual.</TableCell>
                        </TableRow>
                      ) : null}
                    </TableBody>
                  </Table>
                </div>
              ) : null}
            </section>
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

function detailValue(detail: SupportOpaAttendanceDetail | null, key: keyof SupportOpaAttendanceDetailData) {
  const enrichedValue = detail?.enriched?.[key];
  if (enrichedValue !== null && enrichedValue !== undefined && enrichedValue !== "") {
    return { value: enrichedValue, source: "OPA detalhe" };
  }
  const localValue = detail?.local[key];
  return { value: localValue, source: "Local" };
}

function detailLabel(value: unknown) {
  if (value === null || value === undefined || value === "") return "Não informado";
  if (typeof value === "number") return number(value, 2);
  if (typeof value === "string") return value;
  return String(value);
}

function listLabel(item: Record<string, unknown>) {
  const name = typeof item.name === "string" ? item.name : "";
  const id = typeof item.id === "string" ? item.id : "";
  if (name && id) return `${name} - código ${id}`;
  if (name) return name;
  return id ? `Código ${id}` : "Não identificado";
}

function DetailBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 bg-slate-50/60 px-4 py-2.5">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">{title}</h3>
      </div>
      <div className="grid gap-3 p-4 sm:grid-cols-2">{children}</div>
    </section>
  );
}

// Resumo executivo do atendimento — protocolo/status/cliente/atendente/tempos
// numa única área de destaque, em vez de repetir o mesmo em vários blocos tipo
// formulário. Código do cliente/atendente/departamento vira metadado discreto
// (monoespaçado, cinza) sob o nome — nunca compete com ele como texto principal.
function AttendanceSummaryHeader({
  protocol,
  status,
  customerName,
  customerId,
  attendantName,
  attendantId,
  departmentName,
  openedAt,
  closedAt,
  duration,
  tmrHuman,
  tmrAll,
  rating,
}: {
  protocol: unknown;
  status: unknown;
  customerName: unknown;
  customerId: unknown;
  attendantName: unknown;
  attendantId: unknown;
  departmentName: unknown;
  openedAt: unknown;
  closedAt: unknown;
  duration: unknown;
  tmrHuman: unknown;
  tmrAll: unknown;
  rating: unknown;
}) {
  const customerCode = typeof customerId === "string" ? customerCodeLabel(customerId) : "";
  const attendantCode = typeof attendantId === "string" && attendantId.trim() ? `Código: ${attendantId}` : "";
  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 bg-gradient-to-br from-slate-50 to-white px-4 py-3">
        <div className="flex items-center gap-2">
          {typeof status === "string" ? <AttendanceStatusBadge status={status} closedAt={typeof closedAt === "string" ? closedAt : null} /> : null}
          <span className="font-mono text-[11px] text-slate-500">{detailLabel(protocol)}</span>
        </div>
        {typeof rating === "number" ? (
          <span className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-semibold text-amber-800">
            ★ {number(rating, 2)}
          </span>
        ) : null}
      </div>

      <div className="grid gap-4 p-4 sm:grid-cols-2">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Cliente</p>
          <p className="mt-0.5 truncate text-base font-semibold text-slate-950">{detailLabel(customerName)}</p>
          {customerCode ? <p className="mt-0.5 truncate text-[11px] text-slate-400">{customerCode}</p> : null}
        </div>
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Atendente</p>
          <p className="mt-0.5 truncate text-base font-semibold text-slate-950">{detailLabel(attendantName)}</p>
          <p className="mt-0.5 truncate text-[11px] text-slate-400">
            {typeof departmentName === "string" && departmentName ? departmentName : "Departamento não informado"}
            {attendantCode ? ` · ${attendantCode}` : ""}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 divide-x divide-y divide-slate-100 border-t border-slate-100 sm:grid-cols-4 sm:divide-y-0">
        <StatCell label="Duração" value={typeof duration === "number" ? secondsLabel(duration) : "-"} />
        <StatCell label="TMR humano" value={typeof tmrHuman === "number" ? secondsLabel(tmrHuman) : "Não disponível"} />
        <StatCell label="TMR geral" value={typeof tmrAll === "number" ? secondsLabel(tmrAll) : "Não disponível"} helper="inclui bot" />
        <StatCell label="Abertura → Encerramento" value={typeof openedAt === "string" ? dateTimeShort(openedAt) : "-"} helper={typeof closedAt === "string" ? `até ${dateTimeShort(closedAt)}` : "em aberto"} />
      </div>
    </section>
  );
}

function DetailField({ label, value }: { label: string; value: unknown; source?: string }) {
  const empty = value === null || value === undefined || value === "";
  return (
    <div className="min-w-0">
      <span className="text-[11px] font-semibold uppercase text-slate-500">{label}</span>
      <p className={`mt-1 break-words text-sm ${empty ? "text-slate-400" : "text-slate-900"}`}>{detailLabel(value)}</p>
    </div>
  );
}

function DetailText({ label, value }: { label: string; value: unknown; source?: string }) {
  const empty = value === null || value === undefined || value === "";
  return (
    <div className="sm:col-span-2">
      <span className="text-[11px] font-semibold uppercase text-slate-500">{label}</span>
      <p className={`mt-1 whitespace-pre-wrap break-words rounded-md border border-slate-100 bg-slate-50 p-3 text-sm ${empty ? "text-slate-400" : "text-slate-900"}`}>
        {detailLabel(value)}
      </p>
    </div>
  );
}

const TIMELINE_ACTOR_STYLE: Record<string, { dot: string; badge: string; actorLabel: string }> = {
  client: { dot: "bg-blue-500", badge: "border-blue-100 bg-blue-50 text-blue-700", actorLabel: "Cliente" },
  bot: { dot: "bg-violet-500", badge: "border-violet-100 bg-violet-50 text-violet-700", actorLabel: "IA / Bot" },
  human: { dot: "bg-emerald-500", badge: "border-emerald-100 bg-emerald-50 text-emerald-700", actorLabel: "Atendente" },
  system: { dot: "bg-slate-400", badge: "border-slate-200 bg-slate-50 text-slate-700", actorLabel: "Sistema" },
  unknown: { dot: "bg-slate-300", badge: "border-slate-200 bg-slate-50 text-slate-500", actorLabel: "Não identificado" },
};

function TimelineEventRow({ event, isLast }: { event: SupportOpaTimelineEvent; isLast: boolean }) {
  const style = TIMELINE_ACTOR_STYLE[event.actor_type] ?? TIMELINE_ACTOR_STYLE.unknown;
  return (
    <li className="relative flex gap-3 pb-3 last:pb-0">
      {!isLast ? <span className="absolute left-[6px] top-4 bottom-[-12px] w-px bg-slate-200" aria-hidden="true" /> : null}
      <span className={`relative z-10 mt-1.5 h-3 w-3 shrink-0 rounded-full ring-4 ring-white ${style.dot}`} aria-hidden="true" />
      <div className="min-w-0 flex-1 rounded-lg border border-slate-100 bg-white p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-medium text-slate-900">{event.label}</p>
            <Badge className={style.badge}>{style.actorLabel}</Badge>
          </div>
          <span className="shrink-0 whitespace-nowrap text-xs font-medium tabular-nums text-slate-600">{dateTimeLabel(event.occurred_at)}</span>
        </div>
        {event.description ? <p className="mt-1 text-xs text-slate-500">{event.description}</p> : null}
      </div>
    </li>
  );
}

function AttendanceTimelineSection({
  timeline,
  loading,
  error,
}: {
  timeline: SupportOpaAttendanceTimeline | null;
  loading: boolean;
  error: string | null;
}) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="text-sm font-semibold text-slate-950">Timeline do atendimento</h3>
      <div className="mt-1.5 flex items-start gap-1.5 text-xs text-slate-500">
        <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" />
        <p>
          Sequência de eventos em ordem cronológica. Por privacidade, mensagens mostram só quem enviou (cliente,
          agente virtual ou atendente) e o horário — o conteúdo da conversa nunca é exibido aqui.
        </p>
      </div>

      {loading ? (
        <div className="mt-3 flex min-h-24 items-center justify-center gap-2 rounded-lg border border-slate-100 text-sm text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin" /> Carregando timeline...
        </div>
      ) : null}

      {!loading && error ? (
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          <XCircle className="mt-0.5 h-4 w-4 shrink-0" /> {error}
        </div>
      ) : null}

      {!loading && !error && timeline ? (
        <div className="mt-3">
          {timeline.messages_source === "unavailable" && timeline.messages_error ? (
            <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
              {timeline.messages_error}
            </div>
          ) : null}
          {timeline.events.length ? (
            <ol>
              {timeline.events.map((event, index) => (
                <TimelineEventRow key={`${event.type}-${index}`} event={event} isLast={index === timeline.events.length - 1} />
              ))}
            </ol>
          ) : (
            <p className="rounded-lg border border-slate-100 bg-slate-50 p-4 text-center text-sm text-slate-500">
              Nenhum evento disponível para este atendimento.
            </p>
          )}
        </div>
      ) : null}
    </section>
  );
}

function AttendanceDetailSheet({
  open,
  detail,
  loading,
  error,
  timeline,
  timelineLoading,
  timelineError,
  onOpenChange,
}: {
  open: boolean;
  detail: SupportOpaAttendanceDetail | null;
  loading: boolean;
  error: string | null;
  timeline: SupportOpaAttendanceTimeline | null;
  timelineLoading: boolean;
  timelineError: string | null;
  onOpenChange: (open: boolean) => void;
}) {
  const protocol = detailValue(detail, "protocol");
  const customerName = detailValue(detail, "customer_name");
  const customerId = detailValue(detail, "customer_id");
  const attendantName = detailValue(detail, "attendant_name");
  const attendantId = detailValue(detail, "attendant_id");
  const departmentName = detailValue(detail, "department_name");
  const departmentId = detailValue(detail, "department_id");
  const channel = detailValue(detail, "channel");
  const channelId = detailValue(detail, "channel_id");
  const channelCustomer = detailValue(detail, "channel_customer");
  const status = detailValue(detail, "status");
  const openedAt = detailValue(detail, "opened_at");
  const closedAt = detailValue(detail, "closed_at");
  const duration = detailValue(detail, "duration_seconds");
  const tmrHuman = detailValue(detail, "tmr_seconds");
  const tmrAll = detailValue(detail, "tmr_all_responses_seconds");
  const rating = detailValue(detail, "rating");
  const description = detailValue(detail, "description");
  const observations = detailValue(detail, "observations");
  const reasons = detail?.enriched?.reasons?.length ? detail.enriched.reasons : detail?.local.reasons ?? [];
  const tags = detail?.enriched?.tags?.length ? detail.enriched.tags : detail?.local.tags ?? [];
  const listSource = detail?.enriched?.reasons?.length || detail?.enriched?.tags?.length ? "OPA detalhe" : "Local";
  const customerDisplayName =
    typeof customerName.value === "string" && customerName.value.trim()
      ? customerName.value
      : customerId.value
        ? "Cliente sem nome cadastrado"
        : customerName.value;
  const detailTitle =
    typeof protocol.value === "string" && protocol.value.trim()
      ? `Atendimento ${protocol.value}`
      : "Detalhe do atendimento";

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-3xl">
        <SheetHeader>
          <SheetTitle>{detail ? detailTitle : "Detalhe do atendimento"}</SheetTitle>
          <SheetDescription>{detail ? `Código OPA: ${detail.source_id}` : "Carregando dados do atendimento selecionado."}</SheetDescription>
        </SheetHeader>

        <div className="mt-5 grid gap-4">
          {loading ? (
            <div className="flex min-h-48 items-center justify-center gap-2 rounded-lg border border-slate-200 text-sm text-slate-500">
              <Loader2 className="h-4 w-4 animate-spin" /> Carregando detalhe...
            </div>
          ) : null}

          {!loading && error ? (
            <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              <XCircle className="mt-0.5 h-4 w-4 shrink-0" /> {error}
            </div>
          ) : null}

          {!loading && !error && detail ? (
            <>
              {detail.external_detail_error ? (
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
                  O detalhe local foi carregado. O enriquecimento sob demanda do OPA falhou: {detail.external_detail_error}
                </div>
              ) : null}

              <AttendanceSummaryHeader
                protocol={protocol.value}
                status={status.value}
                customerName={customerDisplayName}
                customerId={customerId.value}
                attendantName={attendantName.value}
                attendantId={attendantId.value}
                departmentName={departmentName.value}
                openedAt={openedAt.value}
                closedAt={closedAt.value}
                duration={duration.value}
                tmrHuman={tmrHuman.value}
                tmrAll={tmrAll.value}
                rating={rating.value}
              />

              <DetailBlock title="Canal e contexto">
                <DetailField label="Canal" value={channel.value} source={channel.source} />
                <DetailField label="Canal do cliente" value={channelCustomer.value} source={channelCustomer.source} />
                <DetailField label="Motivos" value={reasons.length ? reasons.map(listLabel).join(", ") : null} source={listSource} />
                <DetailField label="Tags" value={tags.length ? tags.map(listLabel).join(", ") : null} source={listSource} />
              </DetailBlock>

              {(description.value || observations.value) ? (
                <DetailBlock title="Descrição/observações">
                  <DetailText label="Descrição" value={description.value} source={description.source} />
                  <DetailText label="Observações" value={observations.value} source={observations.source} />
                </DetailBlock>
              ) : null}

              <p className="px-1 text-[11px] text-slate-400">
                Códigos internos: cliente {customerId.value ? String(customerId.value) : "-"} · atendente {attendantId.value ? String(attendantId.value) : "-"} · departamento {departmentId.value ? String(departmentId.value) : "-"} · canal {channelId.value ? String(channelId.value) : "-"}
              </p>

              <AttendanceTimelineSection timeline={timeline} loading={timelineLoading} error={timelineError} />
            </>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
