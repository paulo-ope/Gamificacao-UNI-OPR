"use client";

import Link from "next/link";
import {
  ArrowUpDown,
  ArrowDownRight,
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
  Database,
  Eye,
  Home,
  Loader2,
  LogOut,
  Minus,
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
  dateTimeLabel,
  number,
  OpaGlobalFilters,
  OpaAttendantsPanel,
  OPA_NAV_ITEMS,
  OpaOverview,
  OpaSyncPanel,
  opaStatusLabel,
  secondsLabel,
  type OpaModuleTab,
} from "@/app/suporte/_components/opa-module-components";
import type {
  SupportOpaAttendanceDetail,
  SupportOpaAttendanceDetailData,
  SupportOpaAttendanceFilters,
  SupportOpaAttendanceListItem,
  SupportOpaAttendancePage,
  SupportOpaBreakdownItem,
  SupportOpaBreakdowns,
  SupportOpaFilters,
  SupportOpaOverview,
  SupportOpaSyncSettings,
  SupportOpaSyncStatus,
} from "@/lib/types";

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

function customerNameLabel(customerName?: string | null, customerId?: string | null) {
  const name = customerName?.trim();
  if (name) return name;
  return customerId?.trim() ? "Cliente sem nome cadastrado" : "Cliente não informado";
}

function customerCodeLabel(customerId?: string | null) {
  const id = customerId?.trim();
  return id ? `Código do cliente: ${id}` : "";
}

function overviewFilters(period: { date_from: string; date_to: string }, filters: SupportOpaAttendanceFilters): SupportOpaAttendanceFilters {
  return {
    date_from: period.date_from,
    date_to: period.date_to,
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
  (["status", "channel", "attendant_id", "department_id", "reason_id", "customer", "search"] as const).forEach((key) => {
    const value = filters[key];
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  });
  return params.toString();
}

function filtersFromParams(params: URLSearchParams): SupportOpaAttendanceFilters {
  return {
    page: 1,
    page_size: 25,
    sort_by: "opened_at",
    sort_dir: "desc",
    status: params.get("status") || undefined,
    channel: params.get("channel") || undefined,
    attendant_id: params.get("attendant_id") || undefined,
    department_id: params.get("department_id") || undefined,
    reason_id: params.get("reason_id") || undefined,
    customer: params.get("customer") || undefined,
    search: params.get("search") || undefined,
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
  const [filterOptions, setFilterOptions] = useState<SupportOpaFilters | null>(null);
  const [attendanceLoading, setAttendanceLoading] = useState(false);
  const [selectedAttendanceId, setSelectedAttendanceId] = useState<number | null>(null);
  const [attendanceDetail, setAttendanceDetail] = useState<SupportOpaAttendanceDetail | null>(null);
  const [attendanceDetailLoading, setAttendanceDetailLoading] = useState(false);
  const [attendanceDetailError, setAttendanceDetailError] = useState<string | null>(null);
  const [syncStatus, setSyncStatus] = useState<SupportOpaSyncStatus | null>(null);
  const [settings, setSettings] = useState<SupportOpaSyncSettings | null>(null);
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
        api.supportOpaFilters(nextPeriod).then(setFilterOptions),
      ];
      if (canSync) {
        requests.push(api.supportOpaSyncStatus().then(setSyncStatus));
        requests.push(api.supportOpaSyncSettings().then(setSettings));
      }
      await Promise.all(requests);
      setAppliedPeriod(nextPeriod);
      setAttendanceFilters((current) => ({ ...current, ...nextFilters, date_from: nextPeriod.date_from, date_to: nextPeriod.date_to, page: 1 }));
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
    void loadAttendances({ date_from: appliedPeriod.date_from, date_to: appliedPeriod.date_to, page: attendanceFilters.page ?? 1 });
    if (!filterOptions) void api.supportOpaFilters(appliedPeriod).then(setFilterOptions).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeView]);

  useEffect(() => {
    if (!user || !canRead || activeView !== "attendants") return;
    void loadAttendantBreakdown(appliedPeriod, attendanceFilters);
    if (!filterOptions) void api.supportOpaFilters(appliedPeriod).then(setFilterOptions).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeView, attendantSortBy, attendantSortDir]);

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
    if (attendant.id) void loadAttendantRecentAttendances(attendant.id);
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

  function navigateToAttendantData(attendantId: string) {
    const nextFilters: SupportOpaAttendanceFilters = { ...attendanceFilters, attendant_id: attendantId, page: 1 };
    setAttendanceFilters(nextFilters);
    setSelectedAttendant(null);
    setActiveView("data");
    updateUrl("data", appliedPeriod, nextFilters);
    void loadAttendances({ ...overviewFilters(appliedPeriod, nextFilters), page: 1 });
  }

  async function openAttendanceDetail(id: number) {
    setSelectedAttendanceId(id);
    setAttendanceDetail(null);
    setAttendanceDetailError(null);
    setAttendanceDetailLoading(true);
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

  async function importPeriod() {
    setSyncing(true);
    setError(null);
    setMessage(null);
    try {
      const result = await api.importSupportOpaPeriod(period);
      setMessage(
        `Run #${result.run_id}: ${result.fetched_count} recebido(s) em ${result.pages_processed} página(s), ${result.created_count} criado(s), ` +
        `${result.updated_count} atualizado(s), ${result.unchanged_count} sem alteração, ${result.rejected_count} rejeitado(s).`,
      );
      window.dispatchEvent(new Event("notifications:refresh"));
      await load(period);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao importar dados do OPA Suite.");
    } finally {
      setSyncing(false);
    }
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
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
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

      <section className="px-4 pt-5 lg:px-7">
        <div className="flex flex-col justify-between gap-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm lg:flex-row lg:items-center">
          <div>
            <div className="flex items-center gap-2 text-blue-700">
              <Database className="h-5 w-5" />
              <p className="text-[10px] font-bold uppercase tracking-[0.22em]">OPA Suite</p>
            </div>
            <h2 className="mt-2 text-2xl font-semibold text-slate-950">Atendimentos do Suporte</h2>
            <p className="mt-1 max-w-3xl text-sm text-slate-500">
              Acompanhe os atendimentos sincronizados do OPA Suite em uma única visão.
            </p>
          </div>
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
        onPeriodChange={setPeriod}
        onFilterChange={(patch) => setAttendanceFilters((current) => ({ ...current, ...patch }))}
        onApply={() => void load(period, { ...attendanceFilters, page: 1 }, activeView)}
        onClear={clearFilters}
        onImport={() => void importPeriod()}
      />

      <section className="px-4 py-6 lg:px-7">
        <div className="grid gap-5">
          {activeView === "overview" ? <OpaOverview overview={overview} /> : null}
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
            <OpaSyncPanel
              canSync={canSync}
              syncStatus={syncStatus}
              settings={settings}
              savingSettings={savingSettings}
              onDraftSettings={(next) => setSettings((current) => current ? { ...current, ...next } : current)}
              onSaveSettings={(next) => void saveSettings(next)}
            />
          ) : null}
        </div>
      </section>
      <AttendanceDetailSheet
        open={selectedAttendanceId !== null}
        detail={attendanceDetail}
        loading={attendanceDetailLoading}
        error={attendanceDetailError}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedAttendanceId(null);
            setAttendanceDetail(null);
            setAttendanceDetailError(null);
          }
        }}
      />
      <AttendantDetailSheet
        open={selectedAttendant !== null}
        attendant={selectedAttendant}
        period={appliedPeriod}
        recentPage={attendantRecentPage}
        loading={attendantRecentLoading}
        error={attendantRecentError}
        onViewAll={(attendantId) => navigateToAttendantData(attendantId)}
        onOpenAttendanceDetail={(id) => void openAttendanceDetail(id)}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedAttendant(null);
            setAttendantRecentPage(null);
            setAttendantRecentError(null);
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
      <div className="border-b border-slate-200 p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-2">
            <Database className="h-4 w-4 text-blue-700" />
            <h3 className="text-base font-semibold text-slate-950">Dados</h3>
            <Badge className="border-slate-200 bg-slate-50 text-slate-700">{number(page?.total ?? 0)} registros</Badge>
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
            {!loading && items.map((item) => <AttendanceRow key={item.id} item={item} onOpenDetail={onOpenDetail} />)}
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

function AttendanceRow({ item, onOpenDetail }: { item: SupportOpaAttendanceListItem; onOpenDetail: (id: number) => void }) {
  const customerName = item.customer_name?.trim();
  const customerId = item.customer_id?.trim();
  const customerCode = customerCodeLabel(customerId);
  return (
    <TableRow className="cursor-pointer hover:bg-slate-50" onClick={() => onOpenDetail(item.id)}>
      <TableCell className="whitespace-nowrap tabular-nums">{dateTimeShort(item.opened_at)}</TableCell>
      <TableCell className="font-medium text-slate-900">{protocolLabel(item)}</TableCell>
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
      <TableCell>{opaStatusLabel(item.status)}</TableCell>
      <TableCell className="text-right tabular-nums">{secondsLabel(item.tma_seconds)}</TableCell>
      <TableCell className="text-right tabular-nums">{number(item.rating, 2)}</TableCell>
      <TableCell className="text-right">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={(event) => {
            event.stopPropagation();
            onOpenDetail(item.id);
          }}
        >
          <Eye className="h-3.5 w-3.5" /> Ver detalhes
        </Button>
      </TableCell>
    </TableRow>
  );
}

function dateLabel(value: string) {
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T12:00:00Z`));
}

function AttendantMetric({ label, value, helper }: { label: string; value: string; helper?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
      <p className="text-[11px] font-medium text-slate-500">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums text-slate-950">{value}</p>
      {helper ? <p className="mt-1 text-[11px] text-slate-500">{helper}</p> : null}
    </div>
  );
}

function AttendantTrend({ label, value, suffix = "" }: { label: string; value: number | null | undefined; suffix?: string }) {
  const missing = value === null || value === undefined;
  const positive = !missing && value > 0;
  const negative = !missing && value < 0;
  const Icon = missing ? Minus : positive ? ArrowUpRight : negative ? ArrowDownRight : Minus;
  const labelValue = missing ? "-" : `${positive ? "+" : negative ? "-" : ""}${number(Math.abs(value), suffix ? 1 : 2)}${suffix}`;
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2">
      <span className="text-xs font-medium text-slate-500">{label}</span>
      <span className={`inline-flex items-center gap-1 text-xs font-semibold tabular-nums ${positive ? "text-blue-700" : negative ? "text-slate-600" : "text-slate-400"}`}>
        <Icon className="h-3.5 w-3.5" />
        {labelValue}
      </span>
    </div>
  );
}

function AttendantDetailSheet({
  open,
  attendant,
  period,
  recentPage,
  loading,
  error,
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
        <SheetHeader>
          <SheetTitle>{attendant?.label ?? "Atendente"}</SheetTitle>
          <SheetDescription>
            Período: {dateLabel(period.date_from)} até {dateLabel(period.date_to)}
          </SheetDescription>
        </SheetHeader>

        {attendant ? (
          <div className="mt-5 grid gap-5">
            <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
              <div className="grid gap-0 lg:grid-cols-[1.2fr_2fr]">
                <div className="border-b border-slate-200 bg-slate-50 p-4 lg:border-b-0 lg:border-r">
                  <p className="text-xs font-medium text-slate-500">Atendimentos no período</p>
                  <p className="mt-2 text-4xl font-semibold tabular-nums text-slate-950">{number(attendant.total)}</p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Badge className="border-blue-100 bg-blue-50 text-blue-700">{number(attendant.share_percentage, 1)}% do volume</Badge>
                    <Badge className="border-slate-200 bg-white text-slate-700">{number(attendant.closed)} encerrados</Badge>
                    <Badge className="border-slate-200 bg-white text-slate-700">{number(attendant.open)} em aberto</Badge>
                  </div>
                </div>
                <div className="grid gap-3 p-4 sm:grid-cols-2">
                  <AttendantMetric label="Taxa de encerramento" value={`${number(attendant.closure_rate, 1)}%`} helper={`${number(attendant.closed)} de ${number(attendant.total)} atendimentos`} />
                  <AttendantMetric label="Duração média" value={secondsLabel(attendant.avg_duration_seconds)} helper="somente atendimentos encerrados" />
                  <AttendantMetric label="Avaliação média" value={number(attendant.avg_rating, 2)} helper={`${number(attendant.rating_count)} avaliação(ões)`} />
                  <AttendantMetric label="Cobertura de avaliação" value={ratingCoverage === null ? "-" : `${number(ratingCoverage, 1)}%`} helper="avaliações sobre o volume" />
                </div>
              </div>
            </section>

            <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-sm font-semibold text-slate-950">Tendência vs período anterior</h3>
                <span className="text-xs text-slate-500">sem julgamento automático</span>
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                <AttendantTrend label="Volume" value={attendant.total_change_percentage} suffix="%" />
                <AttendantTrend label="Taxa de encerramento" value={attendant.closure_rate_change_pp} suffix=" p.p." />
                <AttendantTrend label="Duração" value={attendant.avg_duration_change_percentage} suffix="%" />
                <AttendantTrend label="Avaliação" value={attendant.avg_rating_change} />
              </div>
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
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="text-sm font-semibold text-slate-950">{title}</h3>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">{children}</div>
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

function AttendanceDetailSheet({
  open,
  detail,
  loading,
  error,
  onOpenChange,
}: {
  open: boolean;
  detail: SupportOpaAttendanceDetail | null;
  loading: boolean;
  error: string | null;
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

              <DetailBlock title="Atendimento">
                <DetailField label="Protocolo" value={protocol.value} source={protocol.source} />
                <DetailField label="Status" value={typeof status.value === "string" ? opaStatusLabel(status.value) : status.value} source={status.source} />
              </DetailBlock>

              <DetailBlock title="Cliente">
                <DetailField label="Cliente" value={customerDisplayName} source={customerName.source} />
                <DetailField label="Código do cliente" value={customerId.value} source={customerId.source} />
              </DetailBlock>

              <DetailBlock title="Atendente">
                <DetailField label="Atendente" value={attendantName.value} source={attendantName.source} />
                <DetailField label="Código do atendente" value={attendantId.value} source={attendantId.source} />
                <DetailField label="Departamento/setor" value={departmentName.value} source={departmentName.source} />
                <DetailField label="Código do departamento" value={departmentId.value} source={departmentId.source} />
              </DetailBlock>

              <DetailBlock title="Canal">
                <DetailField label="Canal" value={channel.value} source={channel.source} />
                <DetailField label="Código do canal" value={channelId.value} source={channelId.source} />
                <DetailField label="Canal do cliente" value={channelCustomer.value} source={channelCustomer.source} />
              </DetailBlock>

              <DetailBlock title="Motivos e tags">
                <DetailField label="Motivos" value={reasons.length ? reasons.map(listLabel).join(", ") : null} source={listSource} />
                <DetailField label="Tags" value={tags.length ? tags.map(listLabel).join(", ") : null} source={listSource} />
              </DetailBlock>

              <DetailBlock title="Datas e duração">
                <DetailField label="Abertura" value={typeof openedAt.value === "string" ? dateTimeLabel(openedAt.value) : openedAt.value} source={openedAt.source} />
                <DetailField label="Encerramento" value={typeof closedAt.value === "string" ? dateTimeLabel(closedAt.value) : closedAt.value} source={closedAt.source} />
                <DetailField label="Duração" value={typeof duration.value === "number" ? secondsLabel(duration.value) : duration.value} source={duration.source} />
              </DetailBlock>

              <DetailBlock title="Avaliação">
                <DetailField label="Nota" value={rating.value} source={rating.source} />
              </DetailBlock>

              <DetailBlock title="Descrição/observações">
                <DetailText label="Descrição" value={description.value} source={description.source} />
                <DetailText label="Observações" value={observations.value} source={observations.source} />
              </DetailBlock>
            </>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
