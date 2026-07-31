"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import type { EChartsOption } from "echarts";
import * as Popover from "@radix-ui/react-popover";
import {
  ArrowRight,
  Bookmark,
  CalendarClock,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Home,
  Inbox,
  ListChecks,
  Loader2,
  LogOut,
  MoreHorizontal,
  RefreshCcw,
  Search,
  Settings2,
  Users,
  X,
} from "lucide-react";
import type { ComponentType } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { InfoHint } from "@/components/gamification/info-hint";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DateRangePicker } from "@/components/ui/date-range-picker";
import { Input } from "@/components/ui/input";
import { AppRadio } from "@/components/ui/radio";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { WorkspaceLogin } from "@/components/workspace/workspace-login";
import { useWorkspaceAuth } from "@/hooks/use-workspace-auth";
import {
  schedulingApi,
  type SchedulingBacklogItem,
  type SchedulingDashboard,
  type SchedulingFilterOptions,
  type SchedulingFilterState,
  type SchedulingOperatorEventPage,
  type SchedulingOrderDetailPage,
  type SchedulingOrderDrillParams,
  type SchedulingOrderSort,
  type SchedulingOrderSortKey,
  type SchedulingOrderTimeline,
  type SchedulingSavedFilter,
  type SchedulingSavedFilterValues,
  type SchedulingSyncStatus,
  type SchedulingTeamMember,
} from "@/lib/scheduling-api";

const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => <div className="h-[280px] animate-pulse rounded-xl bg-slate-100" aria-label="Carregando gráfico" />,
});

const EMPTY_OPTIONS: SchedulingFilterOptions = {
  filiais: [],
  setores: [],
  assuntos: [],
  operators: [],
  data_available_from: null,
  data_available_to: null,
};

function isoDate(value: Date) {
  return value.toISOString().slice(0, 10);
}

function defaultPeriod(): { date_from: string; date_to: string } {
  const now = new Date();
  return { date_from: isoDate(new Date(now.getFullYear(), now.getMonth(), 2)), date_to: isoDate(now) };
}

function minutesLabel(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  if (value < 60) return `${Math.round(value)} min`;
  if (value < 60 * 24) return `${(value / 60).toFixed(1).replace(".", ",")} h`;
  return `${(value / (60 * 24)).toFixed(1).replace(".", ",")} dias`;
}

function hoursLabel(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  if (value < 48) return `${value.toFixed(1).replace(".", ",")} h`;
  return `${(value / 24).toFixed(1).replace(".", ",")} dias`;
}

// A operação inteira acontece em Rondônia - fixar o fuso na formatação garante que todo mundo vê o
// mesmo horário, não importa onde o navegador de quem está olhando a tela está fisicamente. Sem
// isso, `toLocaleString` usa o fuso do DISPOSITIVO de quem acessa, não o da operação (achado real,
// 2026-07-29: "Aberta em" mostrava 4h a menos do horário certo de Rondônia).
function formatPortoVelho(iso: string | null | undefined) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "medium",
    timeZone: "America/Porto_Velho",
  }).format(new Date(iso));
}

function number(value: number | null | undefined, suffix = "") {
  if (value === null || value === undefined) return "—";
  return `${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(value)}${suffix}`;
}

function MetricCard({
  title,
  value,
  helper,
  hint,
  tone = "blue",
  icon: Icon,
  onClick,
}: {
  title: string;
  value: string | number;
  helper: string;
  hint?: { title: string; description: string };
  tone?: "blue" | "cyan" | "emerald" | "amber" | "red" | "slate";
  icon?: ComponentType<{ className?: string }>;
  onClick?: () => void;
}) {
  const toneClasses = {
    blue: { accent: "from-blue-600 to-cyan-500", badge: "bg-blue-50 text-blue-700" },
    cyan: { accent: "from-cyan-500 to-blue-500", badge: "bg-cyan-50 text-cyan-700" },
    emerald: { accent: "from-emerald-500 to-teal-500", badge: "bg-emerald-50 text-emerald-700" },
    amber: { accent: "from-amber-500 to-orange-500", badge: "bg-amber-50 text-amber-700" },
    red: { accent: "from-red-600 to-rose-500", badge: "bg-red-50 text-red-700" },
    slate: { accent: "from-slate-400 to-slate-300", badge: "bg-slate-100 text-slate-600" },
  }[tone];
  // Não usa <button> como wrapper quando clicável: o InfoHint (dentro) já é um <button>, e
  // <button> não pode conter outro <button> - HTML inválido, quebrava a hidratação do React.
  // <div role="button"> dá o clique/teclado sem esse conflito.
  return (
    <div
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={
        onClick
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onClick();
              }
            }
          : undefined
      }
      className={`relative w-full overflow-hidden rounded-2xl border border-slate-100 bg-white p-4 text-left shadow-sm ${onClick ? "cursor-pointer transition hover:-translate-y-0.5 hover:shadow-md hover:border-slate-200" : ""}`}
    >
      <span className={`absolute inset-x-0 top-0 h-1 bg-gradient-to-r ${toneClasses.accent}`} />
      <div className="flex items-start justify-between gap-2">
        <span className="flex items-center gap-1.5">
          <p className="text-xs font-medium text-slate-500">{title}</p>
          {hint ? <InfoHint ariaLabel={`Ajuda sobre ${title}`} side="bottom" title={hint.title} description={hint.description} /> : null}
        </span>
        {Icon ? (
          <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl ${toneClasses.badge}`}>
            <Icon className="h-4 w-4" />
          </span>
        ) : null}
      </div>
      <p className="mt-2 text-3xl font-semibold tabular-nums text-slate-950">{value}</p>
      <p className="mt-2 text-xs text-slate-600">{helper}</p>
      {onClick ? <span className="mt-1 flex items-center gap-1 text-[11px] font-medium text-blue-600">Ver O.S. <ArrowRight className="h-3 w-3" /></span> : null}
    </div>
  );
}

function MultiSelect({
  label,
  options,
  selected,
  onChange,
  disabled,
  showTeamFilter,
}: {
  label: string;
  options: Array<{ id: string | number; name: string; is_team_member?: boolean | null }>;
  selected: Array<string | number>;
  onChange: (next: Array<string | number>) => void;
  disabled?: boolean;
  showTeamFilter?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [teamOnly, setTeamOnly] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const visibleOptions = showTeamFilter && teamOnly ? options.filter((option) => option.is_team_member) : options;

  useEffect(() => {
    function close(event: PointerEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, []);

  function toggle(id: string | number) {
    onChange(selected.includes(id) ? selected.filter((item) => item !== id) : [...selected, id]);
  }

  return (
    <div ref={containerRef} className="relative">
      <label className="mb-1 block text-[11px] font-medium text-slate-500">{label}</label>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
        className="flex w-full min-w-36 items-center justify-between gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-left text-sm text-slate-700 disabled:opacity-60"
      >
        <span className="truncate">{selected.length ? `${selected.length} selecionado(s)` : "Todos"}</span>
        <ChevronDown className="h-3.5 w-3.5 shrink-0 text-slate-400" />
      </button>
      {open ? (
        <div className="absolute z-40 mt-1 max-h-72 w-72 overflow-y-auto rounded-xl border border-slate-200 bg-white p-2 shadow-lg">
          {showTeamFilter ? (
            <label className="mb-1 flex cursor-pointer items-center gap-2 rounded-lg border border-slate-100 bg-slate-50 px-2 py-1.5 text-xs font-medium text-slate-600">
              <input type="checkbox" checked={teamOnly} onChange={(event) => setTeamOnly(event.target.checked)} className="h-3.5 w-3.5 rounded border-slate-300" />
              Somente equipe de agendamento
            </label>
          ) : null}
          {selected.length ? (
            <button type="button" onClick={() => onChange([])} className="mb-1 w-full rounded-lg px-2 py-1.5 text-left text-xs font-medium text-blue-700 hover:bg-blue-50">
              Limpar seleção
            </button>
          ) : null}
          {visibleOptions.length ? (
            visibleOptions.map((option) => (
              <label key={String(option.id)} className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-slate-700 hover:bg-slate-50">
                <input type="checkbox" checked={selected.includes(option.id)} onChange={() => toggle(option.id)} className="h-4 w-4 rounded border-slate-300" />
                <span className="truncate">{option.name}</span>
                {option.is_team_member ? <Badge className="ml-auto shrink-0 border-blue-200 bg-blue-50 text-[10px] text-blue-700">Equipe</Badge> : null}
              </label>
            ))
          ) : (
            <p className="px-2 py-3 text-center text-xs text-slate-500">
              {showTeamFilter && teamOnly ? "Nenhum membro da equipe encontrado." : "Sem opções (sincronize os dados)."}
            </p>
          )}
        </div>
      ) : null}
    </div>
  );
}

export default function AgendamentoPage() {
  const { user, checking, error: authError, login, logout } = useWorkspaceAuth();
  const canRead = Boolean(user?.permissions.includes("scheduling:read"));
  const canSync = Boolean(user?.permissions.includes("scheduling:sync"));
  const canManage = Boolean(user?.permissions.includes("scheduling:manage"));
  const canManageFilters = Boolean(user?.permissions.includes("scheduling:manage_filters"));
  const canManageGlobalViews = Boolean(user?.permissions.includes("scheduling:views:manage_global"));

  const initialPeriod = useMemo(defaultPeriod, []);
  const [filters, setFilters] = useState<SchedulingFilterState>({
    ...initialPeriod,
    filial_ids: [],
    setor_ids: [],
    assunto_ids: [],
    operator_ids: [],
    count_mode: "all_events",
  });
  const [appliedFilters, setAppliedFilters] = useState<SchedulingFilterState>(filters);
  const [options, setOptions] = useState<SchedulingFilterOptions>(EMPTY_OPTIONS);
  const [dashboard, setDashboard] = useState<SchedulingDashboard | null>(null);
  const [backlog, setBacklog] = useState<SchedulingBacklogItem[]>([]);
  const [syncStatus, setSyncStatus] = useState<SchedulingSyncStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [teamOpen, setTeamOpen] = useState(false);
  const [drill, setDrill] = useState<{ title: string; subtitle: string; params: SchedulingOrderDrillParams } | null>(null);
  const [operatorEventsDrill, setOperatorEventsDrill] = useState<{ operatorId: number; title: string } | null>(null);
  const [operatorsExpanded, setOperatorsExpanded] = useState(false);
  const [savedFilters, setSavedFilters] = useState<SchedulingSavedFilter[]>([]);
  const [selectedSavedFilterId, setSelectedSavedFilterId] = useState<number | null>(null);
  const [filterName, setFilterName] = useState("");
  const [savedFilterVisibility, setSavedFilterVisibility] = useState<"personal" | "global">("personal");

  const loadDashboard = useCallback(async (next: SchedulingFilterState, signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const [nextDashboard, nextBacklog] = await Promise.all([
        schedulingApi.dashboard(next, signal),
        schedulingApi.backlog(next, 100, signal),
      ]);
      setDashboard(nextDashboard);
      setBacklog(nextBacklog);
      setAppliedFilters(next);
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      setError(reason instanceof Error ? reason.message : "Falha ao carregar o módulo de Agendamento.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!user || !canRead) return;
    const controller = new AbortController();
    void schedulingApi.syncStatus().then(setSyncStatus).catch(() => undefined);
    // /team antes do dashboard de propósito: é ele que resolve (uma única vez, com cache no banco)
    // os nomes de operadores novos junto ao IXC - sem isso o primeiro acesso mostraria
    // "Operador IXC 445" em vez do nome.
    void Promise.allSettled([schedulingApi.team(), schedulingApi.resolveTechnicians()]).then(() => {
      void schedulingApi.filters().then(setOptions).catch(() => undefined);
      void loadDashboard(filters, controller.signal);
    });
    void schedulingApi.savedFilters().then(setSavedFilters).catch(() => undefined);
    return () => controller.abort();
    // Carga inicial única por sessão - mudanças de filtro passam pelo botão Filtrar.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, canRead]);

  function savedValues(current: SchedulingFilterState): SchedulingSavedFilterValues {
    return {
      filial_ids: current.filial_ids,
      setor_ids: current.setor_ids,
      assunto_ids: current.assunto_ids,
      operator_ids: current.operator_ids,
      count_mode: current.count_mode,
    };
  }

  async function refreshSavedFilters(selectedId?: number | null) {
    const next = await schedulingApi.savedFilters();
    setSavedFilters(next);
    if (selectedId !== undefined) setSelectedSavedFilterId(selectedId);
  }

  function selectSavedFilter(id: number | null) {
    setSelectedSavedFilterId(id);
    if (!id) {
      setFilterName("");
      setSavedFilterVisibility("personal");
      return;
    }
    const saved = savedFilters.find((item) => item.id === id);
    if (!saved) return;
    const next: SchedulingFilterState = {
      date_from: filters.date_from,
      date_to: filters.date_to,
      filial_ids: saved.filters.filial_ids,
      setor_ids: saved.filters.setor_ids,
      assunto_ids: saved.filters.assunto_ids,
      operator_ids: saved.filters.operator_ids,
      count_mode: saved.filters.count_mode,
    };
    setFilterName(saved.name);
    setSavedFilterVisibility(saved.visibility);
    setFilters(next);
    void loadDashboard(next);
  }

  async function saveCurrentFilter() {
    if (!filterName.trim()) return;
    setError(null);
    try {
      const saved = await schedulingApi.createSavedFilter(filterName.trim(), savedValues(filters), savedFilterVisibility);
      await refreshSavedFilters(saved.id);
      setFilterName(saved.name);
      setMessage(`Filtro "${saved.name}" salvo.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao salvar o filtro.");
    }
  }

  async function updateCurrentSavedFilter() {
    if (!selectedSavedFilterId || !filterName.trim()) return;
    setError(null);
    try {
      const saved = await schedulingApi.updateSavedFilter(selectedSavedFilterId, {
        name: filterName.trim(),
        filters: savedValues(filters),
        visibility: savedFilterVisibility,
      });
      await refreshSavedFilters(saved.id);
      setFilterName(saved.name);
      setMessage(`Filtro "${saved.name}" atualizado.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao atualizar o filtro.");
    }
  }

  async function deleteCurrentSavedFilter() {
    if (!selectedSavedFilterId) return;
    const savedName = savedFilters.find((item) => item.id === selectedSavedFilterId)?.name || "selecionado";
    setError(null);
    try {
      await schedulingApi.deleteSavedFilter(selectedSavedFilterId);
      await refreshSavedFilters(null);
      setFilterName("");
      setSavedFilterVisibility("personal");
      setMessage(`Filtro "${savedName}" excluído.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao excluir o filtro.");
    }
  }

  async function runSync() {
    setSyncing(true);
    setError(null);
    setMessage(null);
    try {
      // Sem marca d'água ainda (primeira carga): usa o intervalo já selecionado na tela como
      // backfill. Depois que a marca d'água existir, sincroniza incremental (sem datas) - mesma
      // lógica que o backend já espera (ver POST /scheduling/sync).
      const isFirstLoad = !syncStatus?.watermark;
      let job = await schedulingApi.startSync(
        isFirstLoad ? filters.date_from : undefined,
        isFirstLoad ? filters.date_to : undefined,
      );
      while (job.status === "pending" || job.status === "running") {
        await new Promise((resolve) => window.setTimeout(resolve, 2000));
        const status = await schedulingApi.syncStatus();
        setSyncStatus(status);
        if (status.last_job && status.last_job.id === job.id) job = status.last_job;
      }
      if (job.status === "failed") throw new Error(job.error || "Falha ao sincronizar com o IXC.");
      setMessage("Sincronização concluída - dados atualizados.");
      await loadDashboard(appliedFilters);
      // Um sync pode trazer operadores/técnicos novos (nunca vistos antes) - resolver o nome deles
      // no IXC ANTES de recarregar os filtros, senão a lista mostra "Operador IXC {id}" até a
      // próxima carga de página (achado real, 2026-07-30: aconteceu logo após um sync).
      await Promise.allSettled([schedulingApi.team(), schedulingApi.resolveTechnicians()]);
      void schedulingApi.filters().then(setOptions).catch(() => undefined);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao sincronizar com o IXC.");
    } finally {
      setSyncing(false);
    }
  }

  const summary = dashboard?.summary;
  const slaTone = summary?.sla_rate === null || summary?.sla_rate === undefined ? "slate" : summary.sla_met ? "emerald" : "red";

  const distributionOption: EChartsOption = {
    color: ["#2563eb"],
    tooltip: { trigger: "axis" },
    grid: { left: 40, right: 16, top: 16, bottom: 40 },
    xAxis: { type: "category", data: (dashboard?.ttfa_distribution || []).map((item) => item.label), axisLabel: { fontSize: 10, interval: 0 } },
    yAxis: { type: "value" },
    series: [{ name: "O.S.", type: "bar", barMaxWidth: 42, data: (dashboard?.ttfa_distribution || []).map((item) => item.count) }],
  };

  function openDrill(title: string, subtitle: string, params: SchedulingOrderDrillParams) {
    setDrill({ title, subtitle, params });
  }

  function handleDistributionClick(clickParams: { componentType?: string; dataIndex?: number }) {
    if (clickParams.componentType !== "series" || clickParams.dataIndex === undefined) return;
    const bucket = dashboard?.ttfa_distribution[clickParams.dataIndex];
    if (!bucket || !bucket.count) return;
    openDrill(`Tempo até agendar: ${bucket.label}`, `${bucket.count} O.S. nessa faixa`, { ttfa_bucket: bucket.bucket, status: "scheduled" });
  }

  const dailyOption: EChartsOption = {
    color: ["#94a3b8", "#2563eb"],
    tooltip: { trigger: "axis" },
    legend: { top: 0 },
    grid: { left: 40, right: 16, top: 34, bottom: 32 },
    xAxis: { type: "category", data: (dashboard?.daily_series || []).map((item) => item.date.slice(5)) },
    yAxis: { type: "value" },
    series: [
      { name: "O.S. abertas", type: "bar", barMaxWidth: 18, data: (dashboard?.daily_series || []).map((item) => item.opened) },
      { name: "Ações de agendamento", type: "line", smooth: true, data: (dashboard?.daily_series || []).map((item) => item.schedule_events) },
    ],
  };

  if (checking && !user)
    return <main className="flex min-h-screen items-center justify-center text-sm text-slate-500">Carregando UNI Workspace...</main>;
  if (!user) return <WorkspaceLogin isLoading={checking} error={authError} onLogin={login} />;
  if (!canRead) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4">
        <div className="max-w-md rounded-2xl border bg-white p-8 text-center">
          <h1 className="text-xl font-semibold">Acesso não autorizado</h1>
          <p className="mt-2 text-sm text-slate-500">Seu perfil não possui a permissão scheduling:read.</p>
          <Link href="/" className="mt-5 inline-block text-sm font-semibold text-blue-700">Voltar ao ecossistema</Link>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-4 px-4 py-3 lg:px-7">
          <div className="flex items-center gap-3">
            <Link
              href="/"
              aria-label="Voltar ao ecossistema"
              className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-cyan-500 text-white shadow-sm transition hover:shadow-md"
            >
              <Home className="h-5 w-5" />
            </Link>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-blue-600">UNI Workspace</p>
              <h1 className="flex items-center gap-1.5 text-base font-semibold text-slate-950">
                <CalendarClock className="h-4 w-4 text-blue-600" /> Agendamento
              </h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {canManage ? (
              <>
                <Button type="button" variant="outline" size="sm" onClick={() => setTeamOpen(true)}>
                  <Users className="h-4 w-4" /> Equipe
                </Button>
                <Button type="button" variant="outline" size="sm" onClick={() => setSettingsOpen(true)}>
                  <Settings2 className="h-4 w-4" /> Configurações
                </Button>
              </>
            ) : null}
            {canSync ? (
              <Button type="button" size="sm" onClick={() => void runSync()} disabled={syncing}>
                {syncing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />}
                {syncing ? "Sincronizando..." : "Sincronizar IXC"}
              </Button>
            ) : null}
            <Button type="button" variant="ghost" size="sm" onClick={logout}>
              <LogOut className="h-4 w-4" /> Sair
            </Button>
          </div>
        </div>
      </header>

      <section className="border-b border-slate-200 bg-white px-4 py-3 lg:px-7">
        <div className="flex flex-wrap items-end gap-3">
          <DateRangePicker
            dateFrom={filters.date_from}
            dateTo={filters.date_to}
            onChange={(key, value) => setFilters((current) => ({ ...current, [key]: value }))}
            presets={[
              {
                label: "Mês atual",
                range: () => {
                  const today = new Date();
                  return {
                    from: isoDate(new Date(today.getFullYear(), today.getMonth(), 1)),
                    to: isoDate(today),
                  };
                },
              },
              {
                label: "Últimos 7 dias",
                range: () => {
                  const today = new Date();
                  const start = new Date(today);
                  start.setDate(start.getDate() - 6);
                  return { from: isoDate(start), to: isoDate(today) };
                },
              },
              {
                label: "Ano até hoje",
                range: () => {
                  const today = new Date();
                  return { from: isoDate(new Date(today.getFullYear(), 0, 1)), to: isoDate(today) };
                },
              },
            ]}
          />
          <MultiSelect
            label="Filial"
            options={options.filiais}
            selected={filters.filial_ids}
            onChange={(next) => setFilters((current) => ({ ...current, filial_ids: next as string[] }))}
          />
          <MultiSelect
            label="Setor"
            options={options.setores}
            selected={filters.setor_ids}
            onChange={(next) => setFilters((current) => ({ ...current, setor_ids: next as string[] }))}
          />
          <MultiSelect
            label="Assunto"
            options={options.assuntos}
            selected={filters.assunto_ids}
            onChange={(next) => setFilters((current) => ({ ...current, assunto_ids: next as string[] }))}
          />
          <MultiSelect
            label="Operador"
            options={options.operators}
            selected={filters.operator_ids}
            onChange={(next) => setFilters((current) => ({ ...current, operator_ids: next as number[] }))}
            showTeamFilter
          />
          <div>
            <label className="mb-1 block text-[11px] font-medium text-slate-500">Contagem</label>
            <div className="flex rounded-lg border border-slate-200 bg-slate-50 p-1">
              {([["all_events", "Cada ação"], ["distinct_orders", "O.S. distintas"]] as const).map(([mode, label]) => (
                <Button
                  key={mode}
                  type="button"
                  size="sm"
                  variant={filters.count_mode === mode ? "default" : "ghost"}
                  className="h-8 px-2.5 text-xs"
                  onClick={() => setFilters((current) => ({ ...current, count_mode: mode }))}
                >
                  {label}
                </Button>
              ))}
            </div>
          </div>
          <SchedulingSavedViewsPopover
            savedFilters={savedFilters}
            selectedSavedFilterId={selectedSavedFilterId}
            filterName={filterName}
            visibility={savedFilterVisibility}
            canManageViews={canManageFilters}
            canCreateGlobalViews={canManageGlobalViews}
            onSelect={selectSavedFilter}
            onNameChange={setFilterName}
            onVisibilityChange={setSavedFilterVisibility}
            onSave={() => void saveCurrentFilter()}
            onUpdate={() => void updateCurrentSavedFilter()}
            onDelete={() => void deleteCurrentSavedFilter()}
          />
          <Button type="button" onClick={() => void loadDashboard(filters)} disabled={loading}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Filtrar
          </Button>
          {syncStatus?.watermark ? (
            <p className="pb-2 text-[11px] text-slate-400">
              Dados até {formatPortoVelho(syncStatus.watermark)} · {number(syncStatus.orders_count)} O.S. · {number(syncStatus.events_count)} eventos
            </p>
          ) : null}
        </div>
      </section>

      <section className="space-y-4 px-4 py-5 lg:px-7">
        {message ? <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{message}</div> : null}
        {error ? <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div> : null}
        {!syncStatus?.orders_count && !loading ? (
          <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            Nenhum dado sincronizado ainda. Use &quot;Sincronizar IXC&quot; (ou peça a um usuário com permissão) para fazer a primeira carga.
          </div>
        ) : null}

        <section className="rounded-2xl border border-blue-100 bg-gradient-to-br from-white via-cyan-50/50 to-blue-50 p-4 shadow-sm sm:p-5">
          <Badge className="border-cyan-200 bg-cyan-50 text-cyan-800">
            <CalendarClock className="mr-1 h-3.5 w-3.5" /> Setor de agendamento
          </Badge>
          <h2 className="mt-3 text-xl font-semibold text-slate-950">Resposta, produtividade e fila</h2>
          <p className="mt-1 max-w-3xl text-sm text-slate-600">
            Tempo medido do log &quot;Aberta&quot; até o log &quot;Agendada&quot; (interação do colaborador, não a janela combinada com o
            cliente). Régua útil desconta o tempo fora do expediente configurado
            {dashboard ? ` (${dashboard.settings.scheduling_business_start}–${dashboard.settings.scheduling_business_end})` : ""}.
          </p>
        </section>

        <section aria-busy={loading} className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            title={`SLA: agendar em até ${minutesLabel(summary?.sla_minutes ?? null)}`}
            value={number(summary?.sla_rate, "%")}
            helper={`Meta: ${number(summary?.sla_target_pct, "%")} · ${number(summary?.scheduled_orders)} O.S. agendadas`}
            hint={{
              title: "Como é calculado",
              description: "Percentual das O.S. abertas no período que receberam o primeiro agendamento dentro do prazo, contando só o tempo útil do expediente do setor.",
            }}
            tone={slaTone}
            icon={CalendarClock}
            onClick={
              summary?.scheduled_orders
                ? () => openDrill("O.S. fora do SLA de agendamento", "Agendadas depois do prazo útil configurado", { sla_status: "late", status: "scheduled" })
                : undefined
            }
          />
          <MetricCard
            title="Tempo até agendar (útil)"
            value={minutesLabel(summary?.ttfa_business.median)}
            helper={`P90: ${minutesLabel(summary?.ttfa_business.p90)} · média: ${minutesLabel(summary?.ttfa_business.average)} · corrido: ${minutesLabel(summary?.ttfa_raw.median)}`}
            hint={{
              title: "Mediana, P90 e média",
              description: "Mediana é o caso típico; P90 mostra a cauda (10% piores); a média sozinha engana em distribuições assimétricas. Régua útil = só horas dentro do expediente.",
            }}
            tone="blue"
            icon={Clock3}
          />
          <MetricCard
            title="Aguardando agendamento"
            value={number(summary?.pending_orders)}
            helper={`de ${number(summary?.opened_orders)} O.S. abertas no período`}
            tone={summary && summary.opened_orders > 0 && summary.pending_orders / summary.opened_orders > 0.2 ? "amber" : "slate"}
            icon={Inbox}
            onClick={
              summary?.pending_orders
                ? () => openDrill("O.S. aguardando agendamento", "Todas as pendentes do recorte, mais antigas primeiro", { status: "pending" })
                : undefined
            }
          />
          <MetricCard
            title="Taxa de reagendamento"
            value={number(summary?.reschedule_rate, "%")}
            helper={`${number(summary?.rescheduled_orders)} O.S. reagendadas · antecedência mediana da janela: ${hoursLabel(summary?.window_lead_hours.median)}`}
            hint={{
              title: "Reagendamento e antecedência",
              description: "Reagendamento: O.S. com mais de um evento de agenda. Antecedência: distância entre o momento em que o operador agendou e a janela combinada - crescendo, indica agenda de campo lotada.",
            }}
            tone={summary?.reschedule_rate && summary.reschedule_rate > 30 ? "amber" : "cyan"}
            icon={RefreshCcw}
          />
        </section>

        <section className="grid gap-4 xl:grid-cols-2">
          <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
            <CardHeader className="pb-0">
              <CardTitle className="text-base font-semibold text-slate-950">Distribuição do tempo até agendar</CardTitle>
              <p className="text-xs text-slate-500">Em horas úteis do expediente do setor.</p>
            </CardHeader>
            <CardContent className="px-2 pb-2 pt-1 sm:px-4">
              <ReactECharts
                option={distributionOption}
                notMerge
                lazyUpdate
                style={{ height: 280, width: "100%" }}
                onEvents={{ click: handleDistributionClick }}
              />
              <p className="px-2 pb-1 text-[11px] text-slate-400">Clique numa barra para ver as O.S. dessa faixa.</p>
            </CardContent>
          </Card>
          <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
            <CardHeader className="pb-0">
              <CardTitle className="text-base font-semibold text-slate-950">Demanda × produção diária</CardTitle>
              <p className="text-xs text-slate-500">
                O.S. abertas por dia vs ações de agendamento do time.
                {summary?.expected_capacity ? ` Capacidade esperada no período: ${number(summary.expected_capacity)} ações (${number(summary.team_size)} membros × meta diária).` : ""}
              </p>
            </CardHeader>
            <CardContent className="px-2 pb-2 pt-1 sm:px-4">
              <ReactECharts option={dailyOption} notMerge lazyUpdate style={{ height: 280, width: "100%" }} />
            </CardContent>
          </Card>
        </section>

        <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
          <CardHeader className="flex-row items-center justify-between gap-3 pb-2">
            <div>
              <CardTitle className="text-base font-semibold text-slate-950">Produtividade por operador</CardTitle>
              <p className="text-xs text-slate-500">
                Meta diária ({dashboard?.settings.scheduling_daily_goal ?? "40"}) aplicada só a membros da equipe de agendamento.
                Modo: {appliedFilters.count_mode === "all_events" ? "cada ação conta" : "O.S. distintas"}.
              </p>
            </div>
            <Clock3 className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent className="px-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Operador</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                  <TableHead className="text-right">O.S. distintas</TableHead>
                  <TableHead className="text-right">Por dia</TableHead>
                  <TableHead className="w-44">Meta diária</TableHead>
                  <TableHead className="text-right">1º agendamento</TableHead>
                  <TableHead className="text-right">Tempo típico (útil)</TableHead>
                  <TableHead className="text-center">Detalhar</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(dashboard?.operators || []).slice(0, operatorsExpanded ? undefined : 15).map((operator) => (
                  <TableRow key={operator.ixc_operator_id} className="odd:bg-slate-50/60">
                    <TableCell>
                      <span className="font-medium text-slate-800">{operator.operator_name}</span>
                      {operator.is_team_member ? <Badge className="ml-2 border-blue-200 bg-blue-50 text-blue-700">Equipe</Badge> : null}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{operator.total_events}</TableCell>
                    <TableCell className="text-right tabular-nums">{operator.distinct_orders}</TableCell>
                    <TableCell className="text-right tabular-nums">{number(operator.per_day)}</TableCell>
                    <TableCell>
                      {operator.goal_percentage !== null ? (
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                            <div
                              className={`h-full rounded-full ${operator.goal_percentage >= 100 ? "bg-emerald-500" : operator.goal_percentage >= 60 ? "bg-blue-500" : "bg-amber-500"}`}
                              style={{ width: `${Math.min(100, operator.goal_percentage)}%` }}
                            />
                          </div>
                          <span className="shrink-0 text-xs tabular-nums text-slate-500">{number(operator.goal_percentage, "%")}</span>
                        </div>
                      ) : (
                        <span className="text-xs text-slate-400">fora da equipe</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{operator.first_schedules}</TableCell>
                    <TableCell className="text-right tabular-nums">{minutesLabel(operator.ttfa_business_median_minutes)}</TableCell>
                    <TableCell>
                      <div className="flex items-center justify-center gap-1">
                        <button
                          type="button"
                          title="Ver O.S. que este operador agendou primeiro"
                          aria-label="Ver 1º agendamento"
                          onClick={() => openDrill(operator.operator_name, "O.S. em que este operador foi o primeiro a agendar", { operator_ids: [operator.ixc_operator_id] })}
                          className="flex h-7 w-7 items-center justify-center rounded-lg text-slate-500 transition hover:bg-blue-50 hover:text-blue-700"
                        >
                          <CalendarClock className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          title="Ver todas as ações deste operador no período"
                          aria-label="Ver todas as ações"
                          onClick={() => setOperatorEventsDrill({ operatorId: operator.ixc_operator_id, title: operator.operator_name })}
                          className="flex h-7 w-7 items-center justify-center rounded-lg text-slate-500 transition hover:bg-blue-50 hover:text-blue-700"
                        >
                          <ListChecks className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {!dashboard?.operators.length ? (
                  <TableRow>
                    <TableCell colSpan={8} className="py-8 text-center text-sm text-slate-500">Nenhuma ação de agendamento no recorte.</TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
            {dashboard && dashboard.operators.length > 15 ? (
              <button
                type="button"
                onClick={() => setOperatorsExpanded((current) => !current)}
                className="w-full px-4 py-2 text-left text-xs font-medium text-blue-700 hover:bg-slate-50"
              >
                {operatorsExpanded ? "Mostrar menos" : `Mostrar todos os ${dashboard.operators.length} operadores`}
              </button>
            ) : null}
            <p className="px-4 pb-2 text-[11px] text-slate-400">
              Use os ícones em &quot;Detalhar&quot;: <CalendarClock className="mx-0.5 inline h-3 w-3 align-text-bottom" /> só as O.S. que o operador agendou primeiro,{" "}
              <ListChecks className="mx-0.5 inline h-3 w-3 align-text-bottom" /> todas as ações dele no período (agendamentos e reagendamentos).
            </p>
          </CardContent>
        </Card>

        <section className="grid gap-4 lg:grid-cols-2">
          <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-base font-semibold text-slate-950">Filiais com mais atraso</CardTitle>
              <p className="text-xs text-slate-500">SLA de agendamento por filial · mínimo de 5 O.S. agendadas no período.</p>
            </CardHeader>
            <CardContent className="px-4 pb-4">
              {(dashboard?.filial_ranking || []).length ? (
                <ul className="space-y-1.5">
                  {(dashboard?.filial_ranking || []).map((item) => (
                    <li key={item.key}>
                      <button
                        type="button"
                        onClick={() =>
                          openDrill(`Atraso em ${item.label}`, "Agendadas depois do prazo útil configurado nessa filial", {
                            filial_ids: [item.key],
                            status: "scheduled",
                            sla_status: "late",
                          })
                        }
                        className="flex w-full items-center justify-between rounded-lg border border-slate-100 px-3 py-2 text-left text-sm transition hover:border-blue-200 hover:bg-blue-50/60"
                      >
                        <span className="min-w-0 truncate text-slate-700">{item.label}</span>
                        <span className="flex shrink-0 items-center gap-3 text-xs text-slate-500">
                          <span>{item.scheduled} O.S.</span>
                          <span className={`font-semibold ${item.late_rate >= 50 ? "text-red-600" : "text-slate-700"}`}>{item.late_rate}% atraso</span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="py-6 text-center text-xs text-slate-400">Sem volume suficiente no recorte.</p>
              )}
            </CardContent>
          </Card>
          <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-base font-semibold text-slate-950">Assuntos com mais atraso</CardTitle>
              <p className="text-xs text-slate-500">SLA de agendamento por assunto · mínimo de 5 O.S. agendadas no período.</p>
            </CardHeader>
            <CardContent className="px-4 pb-4">
              {(dashboard?.assunto_ranking || []).length ? (
                <ul className="space-y-1.5">
                  {(dashboard?.assunto_ranking || []).map((item) => (
                    <li key={item.key}>
                      <button
                        type="button"
                        onClick={() =>
                          openDrill(`Atraso em ${item.label}`, "Agendadas depois do prazo útil configurado nesse assunto", {
                            assunto_ids: [item.key],
                            status: "scheduled",
                            sla_status: "late",
                          })
                        }
                        className="flex w-full items-center justify-between rounded-lg border border-slate-100 px-3 py-2 text-left text-sm transition hover:border-blue-200 hover:bg-blue-50/60"
                      >
                        <span className="min-w-0 truncate text-slate-700">{item.label}</span>
                        <span className="flex shrink-0 items-center gap-3 text-xs text-slate-500">
                          <span>{item.scheduled} O.S.</span>
                          <span className={`font-semibold ${item.late_rate >= 50 ? "text-red-600" : "text-slate-700"}`}>{item.late_rate}% atraso</span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="py-6 text-center text-xs text-slate-400">Sem volume suficiente no recorte.</p>
              )}
            </CardContent>
          </Card>
        </section>

        <section className="grid gap-4 xl:grid-cols-[0.6fr_1.4fr]">
          <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base font-semibold text-slate-950">
                <Inbox className="h-4 w-4 text-blue-600" /> Envelhecimento da fila
              </CardTitle>
              <p className="text-xs text-slate-500">O.S. abertas no período ainda sem nenhum agendamento.</p>
            </CardHeader>
            <CardContent className="space-y-2 px-4 pb-4">
              {(dashboard?.backlog_aging || []).map((bucket) => (
                <button
                  key={bucket.bucket}
                  type="button"
                  disabled={!bucket.count}
                  onClick={() => openDrill(`Fila: ${bucket.label}`, `${bucket.count} O.S. aguardando agendamento nessa faixa`, { status: "pending", backlog_bucket: bucket.bucket })}
                  className="flex w-full items-center justify-between rounded-lg border border-slate-100 px-3 py-2 text-left transition enabled:hover:border-blue-200 enabled:hover:bg-blue-50 disabled:cursor-default"
                >
                  <span className="text-sm text-slate-700">{bucket.label}</span>
                  <span className={`text-sm font-semibold tabular-nums ${bucket.bucket === "acima_7_dias" && bucket.count > 0 ? "text-red-600" : "text-slate-900"}`}>
                    {bucket.count}
                  </span>
                </button>
              ))}
            </CardContent>
          </Card>
          <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-base font-semibold text-slate-950">Fila de trabalho — mais antigas primeiro</CardTitle>
              <p className="text-xs text-slate-500">É a lista de ação do dia: O.S. sem agendamento, da mais antiga para a mais nova.</p>
            </CardHeader>
            <CardContent className="px-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>O.S.</TableHead>
                    <TableHead>Aberta em</TableHead>
                    <TableHead className="text-right">Espera</TableHead>
                    <TableHead>Filial</TableHead>
                    <TableHead>Assunto</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {backlog.slice(0, 15).map((item) => (
                    <TableRow key={item.ixc_os_id} className="odd:bg-slate-50/60">
                      <TableCell className="font-medium text-slate-800">{item.ixc_os_id}</TableCell>
                      <TableCell>{formatPortoVelho(item.opened_at)}</TableCell>
                      <TableCell className={`text-right tabular-nums ${item.age_hours > 72 ? "font-semibold text-red-600" : ""}`}>{hoursLabel(item.age_hours)}</TableCell>
                      <TableCell className="max-w-44 truncate">{item.filial}</TableCell>
                      <TableCell className="max-w-56 truncate">{item.assunto}</TableCell>
                    </TableRow>
                  ))}
                  {!backlog.length ? (
                    <TableRow>
                      <TableCell colSpan={5} className="py-8 text-center text-sm text-slate-500">Fila zerada no recorte selecionado. 🎉</TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
              {backlog.length > 15 ? <p className="px-4 py-2 text-xs text-slate-400">Mostrando 15 de {backlog.length} O.S. pendentes.</p> : null}
            </CardContent>
          </Card>
        </section>
      </section>

      {settingsOpen ? <SettingsDialog onClose={() => setSettingsOpen(false)} onSaved={() => void loadDashboard(appliedFilters)} /> : null}
      {teamOpen ? <TeamDialog onClose={() => setTeamOpen(false)} onSaved={() => void loadDashboard(appliedFilters)} /> : null}
      {drill ? (
        <OrderDrillPanel
          title={drill.title}
          subtitle={drill.subtitle}
          filters={appliedFilters}
          params={drill.params}
          onClose={() => setDrill(null)}
        />
      ) : null}
      {operatorEventsDrill ? (
        <OperatorEventsDrillPanel
          operatorId={operatorEventsDrill.operatorId}
          title={operatorEventsDrill.title}
          filters={appliedFilters}
          onClose={() => setOperatorEventsDrill(null)}
        />
      ) : null}
    </main>
  );
}

function SchedulingSavedViewsPopover({
  savedFilters,
  selectedSavedFilterId,
  filterName,
  visibility,
  canManageViews,
  canCreateGlobalViews,
  onSelect,
  onNameChange,
  onVisibilityChange,
  onSave,
  onUpdate,
  onDelete,
}: {
  savedFilters: SchedulingSavedFilter[];
  selectedSavedFilterId: number | null;
  filterName: string;
  visibility: "personal" | "global";
  canManageViews: boolean;
  canCreateGlobalViews: boolean;
  onSelect: (id: number | null) => void;
  onNameChange: (value: string) => void;
  onVisibilityChange: (value: "personal" | "global") => void;
  onSave: () => void;
  onUpdate: () => void;
  onDelete: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmUpdate, setConfirmUpdate] = useState(false);
  const active = savedFilters.find((item) => item.id === selectedSavedFilterId);
  const visible = savedFilters.filter((item) =>
    item.name.toLocaleLowerCase("pt-BR").includes(search.toLocaleLowerCase("pt-BR")),
  );
  const choose = (id: number) => {
    onSelect(id);
    setCreating(false);
    setRenaming(false);
    setConfirmDelete(false);
    setConfirmUpdate(false);
    setOpen(false);
  };
  const saveNew = () => {
    onSave();
    setCreating(false);
  };
  const update = () => {
    onUpdate();
    setRenaming(false);
  };

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <Button type="button" variant="outline" className="h-10 shrink-0 whitespace-nowrap">
          <Bookmark className="h-4 w-4" />
          <span className="max-w-36 truncate">{active ? `Visão: ${active.name}` : "Visões"}</span>
          <ChevronDown className="h-3.5 w-3.5 text-slate-500" />
        </Button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content align="end" sideOffset={8} className="z-50 w-[min(25rem,calc(100vw-2rem))] rounded-xl border border-slate-200 bg-white p-3 shadow-xl">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-slate-900">Visões salvas</p>
              <p className="text-[11px] text-slate-500">Combinações de filtros reutilizáveis.</p>
            </div>
            {active && canManageViews ? (
              <Popover.Root>
                <Popover.Trigger asChild>
                  <Button type="button" variant="ghost" size="icon" className="h-8 w-8" aria-label="Opções da visão">
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </Popover.Trigger>
                <Popover.Portal>
                  <Popover.Content align="end" sideOffset={6} className="z-[60] w-44 rounded-lg border border-slate-200 bg-white p-1 shadow-lg">
                    <button
                      type="button"
                      onClick={() => {
                        setConfirmUpdate(true);
                        setRenaming(false);
                        setConfirmDelete(false);
                      }}
                      className="flex w-full rounded-md px-2 py-2 text-left text-xs text-slate-700 hover:bg-slate-100"
                    >
                      Atualizar visão
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setRenaming(true);
                        setCreating(false);
                        setConfirmUpdate(false);
                      }}
                      className="flex w-full rounded-md px-2 py-2 text-left text-xs text-slate-700 hover:bg-slate-100"
                    >
                      Renomear e atualizar
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setConfirmDelete(true);
                        setConfirmUpdate(false);
                      }}
                      className="flex w-full rounded-md px-2 py-2 text-left text-xs text-red-700 hover:bg-red-50"
                    >
                      Excluir visão
                    </button>
                  </Popover.Content>
                </Popover.Portal>
              </Popover.Root>
            ) : null}
          </div>
          {active ? (
            <button
              type="button"
              onClick={() => {
                onSelect(null);
                onVisibilityChange("personal");
                setCreating(false);
                setRenaming(false);
                setConfirmDelete(false);
                setConfirmUpdate(false);
              }}
              className="mb-2 text-[11px] font-medium text-blue-700 hover:text-blue-900"
            >
              Retirar visão selecionada
            </button>
          ) : null}
          <label className="relative mb-2 block">
            <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-400" />
            <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar visão" className="h-9 pl-8 text-xs" />
          </label>
          <div className="max-h-44 space-y-1 overflow-y-auto pr-1">
            {visible.length ? (
              visible.map((saved) => (
                <button
                  key={saved.id}
                  type="button"
                  onClick={() => choose(saved.id)}
                  className={`flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-xs ${saved.id === selectedSavedFilterId ? "bg-blue-50 text-blue-800" : "text-slate-700 hover:bg-slate-50"}`}
                >
                  <span className="min-w-0 truncate">
                    {saved.name}
                    <span className="ml-1 rounded-full bg-slate-100 px-1.5 py-0.5 text-[9px] uppercase text-slate-500">
                      {saved.visibility === "global" ? "Global" : "Pessoal"}
                    </span>
                  </span>
                  {saved.id === selectedSavedFilterId ? <Check className="h-3.5 w-3.5 shrink-0" /> : null}
                </button>
              ))
            ) : (
              <p className="px-2 py-4 text-center text-xs text-slate-500">Nenhuma visão encontrada.</p>
            )}
          </div>
          {canManageViews ? (
            <div className="mt-3 border-t border-slate-100 pt-3">
              {creating || renaming ? (
                <div className="space-y-2">
                  <Input
                    value={filterName}
                    maxLength={120}
                    placeholder="Nome da visão"
                    onChange={(event) => onNameChange(event.target.value)}
                    className="h-9 text-xs"
                  />
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-2">
                    <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">Tipo da visão</p>
                    <div className="grid gap-1.5 sm:grid-cols-2">
                      <label className="flex items-center gap-2 rounded-md bg-white px-2 py-1.5 text-xs text-slate-700">
                        <AppRadio checked={visibility === "personal"} onSelect={() => onVisibilityChange("personal")} ariaLabel="Pessoal" />
                        Pessoal
                      </label>
                      {canCreateGlobalViews || active?.visibility === "global" ? (
                        <label className="flex items-center gap-2 rounded-md bg-white px-2 py-1.5 text-xs text-slate-700">
                          <AppRadio
                            checked={visibility === "global"}
                            disabled={!canCreateGlobalViews && active?.visibility !== "global"}
                            onSelect={() => onVisibilityChange("global")}
                            ariaLabel="Global"
                          />
                          Global
                        </label>
                      ) : (
                        <div className="rounded-md bg-white px-2 py-1.5 text-xs text-slate-400">Global indisponível para seu perfil</div>
                      )}
                    </div>
                  </div>
                  <div className="flex justify-end gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      className="h-8 text-xs"
                      onClick={() => {
                        setCreating(false);
                        setRenaming(false);
                        if (!active) onVisibilityChange("personal");
                      }}
                    >
                      Cancelar
                    </Button>
                    <Button type="button" size="sm" className="h-8 text-xs" disabled={!filterName.trim()} onClick={creating ? saveNew : update}>
                      {creating ? "Salvar visão" : "Atualizar visão"}
                    </Button>
                  </div>
                </div>
              ) : confirmDelete ? (
                <div className="flex items-center justify-between gap-2 rounded-lg bg-red-50 p-2">
                  <span className="text-[11px] text-red-800">Excluir "{active?.name}"?</span>
                  <div className="flex gap-1">
                    <Button type="button" size="sm" variant="ghost" className="h-7 text-[10px]" onClick={() => setConfirmDelete(false)}>
                      Cancelar
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      className="h-7 bg-red-600 text-[10px] hover:bg-red-700"
                      onClick={() => {
                        onDelete();
                        setConfirmDelete(false);
                        setOpen(false);
                      }}
                    >
                      Excluir
                    </Button>
                  </div>
                </div>
              ) : confirmUpdate ? (
                <div className="flex items-center justify-between gap-2 rounded-lg bg-blue-50 p-2">
                  <span className="text-[11px] text-blue-800">Atualizar "{active?.name}" com os filtros atuais?</span>
                  <div className="flex gap-1">
                    <Button type="button" size="sm" variant="ghost" className="h-7 text-[10px]" onClick={() => setConfirmUpdate(false)}>
                      Cancelar
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      className="h-7 text-[10px]"
                      onClick={() => {
                        onUpdate();
                        setConfirmUpdate(false);
                        setOpen(false);
                      }}
                    >
                      Atualizar
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="flex gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="h-8 flex-1 text-xs"
                    onClick={() => {
                      onSelect(null);
                      onVisibilityChange("personal");
                      setCreating(true);
                      setRenaming(false);
                    }}
                  >
                    Salvar como nova visão
                  </Button>
                </div>
              )}
            </div>
          ) : null}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

const DRILL_PAGE_SIZE = 50;

function DrillPanelHeader({
  icon: Icon,
  title,
  subtitle,
  onClose,
}: {
  icon: ComponentType<{ className?: string }>;
  title: string;
  subtitle?: string;
  onClose: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-slate-100 p-4">
      <div className="flex min-w-0 items-center gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-cyan-500 text-white shadow-sm">
          <Icon className="h-4 w-4" />
        </span>
        <div className="min-w-0">
          <h2 className="truncate text-base font-semibold text-slate-950">{title}</h2>
          {subtitle ? <p className="truncate text-xs text-slate-500">{subtitle}</p> : null}
        </div>
      </div>
      <Button type="button" size="sm" variant="ghost" onClick={onClose} aria-label="Fechar" className="shrink-0">
        <X className="h-4 w-4" />
      </Button>
    </div>
  );
}

function DrillPagination({
  page,
  totalPages,
  onChange,
}: {
  page: number;
  totalPages: number;
  onChange: (next: number) => void;
}) {
  return (
    <div className="flex items-center justify-between border-t border-slate-100 p-3">
      <p className="text-xs text-slate-500">
        Página <span className="font-semibold text-slate-700">{page}</span> de {totalPages}
      </p>
      <div className="flex items-center gap-1.5">
        <Button type="button" size="sm" variant="outline" className="h-8 px-2" disabled={page <= 1} onClick={() => onChange(Math.max(1, page - 1))}>
          <ChevronLeft className="h-3.5 w-3.5" /> Anterior
        </Button>
        <Button type="button" size="sm" variant="outline" className="h-8 px-2" disabled={page >= totalPages} onClick={() => onChange(page + 1)}>
          Próxima <ChevronRight className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}

function OrderDrillPanel({
  title,
  subtitle,
  filters,
  params,
  onClose,
}: {
  title: string;
  subtitle: string;
  filters: SchedulingFilterState;
  params: SchedulingOrderDrillParams;
  onClose: () => void;
}) {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<SchedulingOrderDetailPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [timelineOsId, setTimelineOsId] = useState<number | null>(null);
  const [sort, setSort] = useState<SchedulingOrderSort>({ key: "opened_at", direction: "desc" });

  function changeSort(key: SchedulingOrderSortKey) {
    const direction: "asc" | "desc" = sort.key === key && sort.direction === "desc" ? "asc" : "desc";
    setSort({ key, direction });
    setPage(1);
  }

  function sortMark(key: SchedulingOrderSortKey) {
    if (sort.key !== key) return "";
    return sort.direction === "asc" ? " ↑" : " ↓";
  }

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    schedulingApi
      .orders(filters, params, page, DRILL_PAGE_SIZE, sort, controller.signal)
      .then(setData)
      .catch((reason) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Falha ao carregar as O.S.");
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, sort.key, sort.direction, JSON.stringify(params), filters.date_from, filters.date_to]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4 backdrop-blur-sm" role="dialog" aria-modal="true">
      <div className="flex max-h-[85vh] w-full max-w-6xl flex-col rounded-2xl bg-white shadow-2xl">
        <DrillPanelHeader
          icon={ListChecks}
          title={title}
          subtitle={`${subtitle}${data ? ` · ${new Intl.NumberFormat("pt-BR").format(data.total)} O.S. no total` : ""}`}
          onClose={onClose}
        />
        <div className="flex-1 overflow-auto">
          {error ? <p className="m-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p> : null}
          {loading ? (
            <div className="m-4 h-64 animate-pulse rounded-xl bg-slate-100" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>O.S.</TableHead>
                  <TableHead>
                    <button type="button" onClick={() => changeSort("opened_at")}>Aberta em{sortMark("opened_at")}</button>
                  </TableHead>
                  <TableHead>
                    <button type="button" onClick={() => changeSort("first_scheduled_at")}>1º agendamento{sortMark("first_scheduled_at")}</button>
                  </TableHead>
                  <TableHead className="text-right">
                    <button type="button" onClick={() => changeSort("ttfa_business_minutes")}>Tempo (útil){sortMark("ttfa_business_minutes")}</button>
                  </TableHead>
                  <TableHead>Operador</TableHead>
                  <TableHead>Técnico</TableHead>
                  <TableHead>
                    <button type="button" onClick={() => changeSort("filial")}>Filial{sortMark("filial")}</button>
                  </TableHead>
                  <TableHead>
                    <button type="button" onClick={() => changeSort("assunto")}>Assunto{sortMark("assunto")}</button>
                  </TableHead>
                  <TableHead className="text-right">
                    <button type="button" onClick={() => changeSort("reschedule_count")}>Reagend.{sortMark("reschedule_count")}</button>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(data?.items || []).map((item) => (
                  <TableRow
                    key={item.ixc_os_id}
                    className="cursor-pointer odd:bg-slate-50/60 hover:bg-blue-50/60"
                    onClick={() => setTimelineOsId(item.ixc_os_id)}
                  >
                    <TableCell className="font-medium text-slate-800">{item.ixc_os_id}</TableCell>
                    <TableCell>{formatPortoVelho(item.opened_at)}</TableCell>
                    <TableCell>
                      {item.first_scheduled_at ? (
                        formatPortoVelho(item.first_scheduled_at)
                      ) : (
                        <span className={item.age_hours && item.age_hours > 72 ? "font-semibold text-red-600" : "text-slate-400"}>
                          Pendente há {hoursLabel(item.age_hours)}
                        </span>
                      )}
                    </TableCell>
                    <TableCell className={`text-right tabular-nums ${item.sla_late ? "font-semibold text-red-600" : ""}`}>
                      {minutesLabel(item.ttfa_business_minutes)}
                    </TableCell>
                    <TableCell className="max-w-56 truncate whitespace-nowrap" title={item.operator_name || undefined}>{item.operator_name || "—"}</TableCell>
                    <TableCell className="max-w-56 truncate whitespace-nowrap" title={item.technician_name || undefined}>{item.technician_name || "—"}</TableCell>
                    <TableCell className="max-w-44 truncate whitespace-nowrap" title={item.filial}>{item.filial}</TableCell>
                    <TableCell className="max-w-64 truncate whitespace-nowrap" title={item.assunto}>{item.assunto}</TableCell>
                    <TableCell className="text-right tabular-nums">{item.reschedule_count || "—"}</TableCell>
                  </TableRow>
                ))}
                {data && !data.items.length ? (
                  <TableRow>
                    <TableCell colSpan={9} className="py-10 text-center text-sm text-slate-500">Nenhuma O.S. encontrada para este recorte.</TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          )}
        </div>
        {data && data.total > data.page_size ? <DrillPagination page={page} totalPages={totalPages} onChange={setPage} /> : null}
      </div>
      {timelineOsId !== null ? (
        <OrderTimelinePanel ixcOsId={timelineOsId} onClose={() => setTimelineOsId(null)} />
      ) : null}
    </div>
  );
}

function OperatorEventsDrillPanel({
  operatorId,
  title,
  filters,
  onClose,
}: {
  operatorId: number;
  title: string;
  filters: SchedulingFilterState;
  onClose: () => void;
}) {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<SchedulingOperatorEventPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [timelineOsId, setTimelineOsId] = useState<number | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    schedulingApi
      .operatorEvents(operatorId, filters, page, DRILL_PAGE_SIZE, controller.signal)
      .then(setData)
      .catch((reason) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Falha ao carregar as ações do operador.");
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [operatorId, page, filters.date_from, filters.date_to]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4 backdrop-blur-sm" role="dialog" aria-modal="true">
      <div className="flex max-h-[85vh] w-full max-w-5xl flex-col rounded-2xl bg-white shadow-2xl">
        <DrillPanelHeader
          icon={CalendarClock}
          title={title}
          subtitle={`Cada agendamento/reagendamento feito por este operador no período${data ? ` · ${new Intl.NumberFormat("pt-BR").format(data.total)} ações no total` : ""}`}
          onClose={onClose}
        />
        <div className="flex-1 overflow-auto">
          {error ? <p className="m-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p> : null}
          {loading ? (
            <div className="m-4 h-64 animate-pulse rounded-xl bg-slate-100" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>O.S.</TableHead>
                  <TableHead>Ação</TableHead>
                  <TableHead>Quando</TableHead>
                  <TableHead>Janela</TableHead>
                  <TableHead>Técnico</TableHead>
                  <TableHead>Filial</TableHead>
                  <TableHead>Assunto</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(data?.items || []).map((item, index) => (
                  <TableRow
                    key={`${item.ixc_os_id}-${item.event_at}-${index}`}
                    className="cursor-pointer odd:bg-slate-50/60 hover:bg-blue-50/60"
                    onClick={() => setTimelineOsId(item.ixc_os_id)}
                  >
                    <TableCell className="font-medium text-slate-800">{item.ixc_os_id}</TableCell>
                    <TableCell>
                      <Badge className={item.event_type === "10" ? "border-amber-200 bg-amber-50 text-amber-700" : "border-blue-200 bg-blue-50 text-blue-700"}>
                        {item.event_label}
                      </Badge>
                    </TableCell>
                    <TableCell>{formatPortoVelho(item.event_at)}</TableCell>
                    <TableCell>
                      {item.window_start ? (
                        <>
                          {formatPortoVelho(item.window_start)}
                          {item.window_end ? ` até ${formatPortoVelho(item.window_end)}` : ""}
                        </>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell className="max-w-56 truncate whitespace-nowrap" title={item.technician_name || undefined}>{item.technician_name || "—"}</TableCell>
                    <TableCell className="max-w-44 truncate whitespace-nowrap" title={item.filial}>{item.filial}</TableCell>
                    <TableCell className="max-w-64 truncate whitespace-nowrap" title={item.assunto}>{item.assunto}</TableCell>
                  </TableRow>
                ))}
                {data && !data.items.length ? (
                  <TableRow>
                    <TableCell colSpan={7} className="py-10 text-center text-sm text-slate-500">Nenhuma ação encontrada para este recorte.</TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          )}
        </div>
        {data && data.total > data.page_size ? <DrillPagination page={page} totalPages={totalPages} onChange={setPage} /> : null}
      </div>
      {timelineOsId !== null ? (
        <OrderTimelinePanel ixcOsId={timelineOsId} onClose={() => setTimelineOsId(null)} />
      ) : null}
    </div>
  );
}

function eventTypeTone(eventType: string) {
  switch (eventType) {
    case "5":
      return { dot: "bg-blue-600", accent: "border-l-blue-500", badge: "border-blue-200 bg-blue-50 text-blue-700" };
    case "10":
      return { dot: "bg-amber-500", accent: "border-l-amber-500", badge: "border-amber-200 bg-amber-50 text-amber-700" };
    case "6":
      return { dot: "bg-emerald-600", accent: "border-l-emerald-500", badge: "border-emerald-200 bg-emerald-50 text-emerald-700" };
    default:
      return { dot: "bg-slate-400", accent: "border-l-slate-300", badge: "border-slate-200 bg-slate-100 text-slate-600" };
  }
}

function OrderTimelinePanel({ ixcOsId, onClose }: { ixcOsId: number; onClose: () => void }) {
  const [data, setData] = useState<SchedulingOrderTimeline | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    schedulingApi
      .orderTimeline(ixcOsId, controller.signal)
      .then(setData)
      .catch((reason) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Falha ao carregar o log da O.S.");
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [ixcOsId]);

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/50 p-4 backdrop-blur-sm" role="dialog" aria-modal="true">
      <div className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-2xl bg-white shadow-2xl">
        <DrillPanelHeader
          icon={CalendarClock}
          title={`Log completo — O.S. ${ixcOsId}`}
          subtitle={data ? `${data.filial} · ${data.setor} · ${data.assunto}` : undefined}
          onClose={onClose}
        />
        <div className="flex-1 overflow-y-auto p-4">
          {error ? <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p> : null}
          {loading ? (
            <div className="h-64 animate-pulse rounded-xl bg-slate-100" />
          ) : data ? (
            <ol className="relative space-y-3 border-l-2 border-slate-100 pl-5">
              {data.events.map((event, index) => {
                const tone = eventTypeTone(event.event_type);
                return (
                <li key={index} className="relative">
                  <span className={`absolute -left-[27px] top-3 h-3 w-3 rounded-full ring-4 ring-white ${tone.dot}`} />
                  <div className={`rounded-xl border border-slate-100 border-l-4 ${tone.accent} bg-white p-3 shadow-sm`}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${tone.badge}`}>
                        {event.event_label}
                      </span>
                      <p className="text-xs text-slate-500">{formatPortoVelho(event.event_at)}</p>
                    </div>
                    {event.window_start ? (
                      <p className="mt-1.5 text-xs text-slate-500">
                        Janela: {formatPortoVelho(event.window_start)}
                        {event.window_end ? ` até ${formatPortoVelho(event.window_end)}` : ""}
                      </p>
                    ) : null}
                    {event.operator_name || event.technician_name ? (
                      <p className="mt-1 text-xs text-slate-600">
                        {event.operator_name ? <>Operador: <span className="font-medium text-slate-700">{event.operator_name}</span></> : null}
                        {event.operator_name && event.technician_name ? " · " : ""}
                        {event.technician_name ? <>Técnico: <span className="font-medium text-slate-700">{event.technician_name}</span></> : null}
                      </p>
                    ) : null}
                    {event.mensagem ? (
                      <p className="mt-2 whitespace-pre-wrap rounded-lg bg-slate-50 px-2.5 py-2 text-xs text-slate-700">
                        {event.mensagem}
                      </p>
                    ) : null}
                    {event.historico ? (
                      <p className="mt-1.5 text-xs italic text-slate-400">{event.historico}</p>
                    ) : null}
                  </div>
                </li>
                );
              })}
              {!data.events.length ? (
                <p className="text-sm text-slate-500">Nenhum evento sincronizado para esta O.S.</p>
              ) : null}
            </ol>
          ) : null}
        </div>
      </div>
    </div>
  );
}

const SETTINGS_FIELDS: Array<{ key: string; label: string; helper: string; type: "number" | "time" | "text" }> = [
  { key: "scheduling_sla_target_pct", label: "Meta do SLA (%)", helper: "Percentual mínimo de O.S. agendadas dentro do prazo.", type: "number" },
  { key: "scheduling_sla_minutes", label: "Prazo do SLA (minutos úteis)", helper: "Ex.: 60 = agendar em até 1 hora útil.", type: "number" },
  { key: "scheduling_business_start", label: "Início do expediente", helper: "Hora em que o setor começa a operar.", type: "time" },
  { key: "scheduling_business_end", label: "Fim do expediente", helper: "Hora em que o setor encerra.", type: "time" },
  { key: "scheduling_business_days", label: "Dias ativos (0=seg ... 6=dom)", helper: "Separados por vírgula. Todos os dias: 0,1,2,3,4,5,6", type: "text" },
  { key: "scheduling_daily_goal", label: "Meta diária por operador", helper: "Ações de agendamento esperadas por membro da equipe por dia.", type: "number" },
];

function SettingsDialog({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [values, setValues] = useState<Record<string, string> | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [backfilling, setBackfilling] = useState(false);
  const [backfillMessage, setBackfillMessage] = useState<string | null>(null);

  useEffect(() => {
    void schedulingApi.settings().then(setValues).catch(() => setError("Falha ao carregar as configurações."));
    void schedulingApi.messagesBackfillStatus().then((job) => {
      if (job?.status === "completed") {
        setBackfillMessage(`Última busca: ${job.result?.events_updated ?? 0} eventos atualizados com o texto da mensagem.`);
      }
    }).catch(() => undefined);
  }, []);

  async function save() {
    if (!values) return;
    setSaving(true);
    setError(null);
    try {
      await schedulingApi.updateSettings(values);
      onSaved();
      onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao salvar.");
    } finally {
      setSaving(false);
    }
  }

  async function runMessagesBackfill() {
    setBackfilling(true);
    setBackfillMessage(null);
    setError(null);
    try {
      let job = await schedulingApi.startMessagesBackfill();
      while (job.status === "pending" || job.status === "running") {
        await new Promise((resolve) => window.setTimeout(resolve, 2000));
        const status = await schedulingApi.messagesBackfillStatus();
        if (status) job = status;
      }
      if (job.status === "failed") throw new Error(job.error || "Falha ao buscar mensagens no IXC.");
      setBackfillMessage(`Concluído: ${job.result?.events_updated ?? 0} eventos atualizados com o texto da mensagem.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao buscar mensagens no IXC.");
    } finally {
      setBackfilling(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4" role="dialog" aria-modal="true">
      <div className="w-full max-w-lg rounded-2xl bg-white p-5 shadow-xl">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-950">Configurações do módulo</h2>
          <Button type="button" size="sm" variant="ghost" onClick={onClose} aria-label="Fechar"><X className="h-4 w-4" /></Button>
        </div>
        {error ? <p className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p> : null}
        {values ? (
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {SETTINGS_FIELDS.map((field) => (
              <label key={field.key} className="block">
                <span className="text-xs font-medium text-slate-600">{field.label}</span>
                <input
                  type={field.type}
                  value={values[field.key] ?? ""}
                  onChange={(event) => setValues((current) => ({ ...(current || {}), [field.key]: event.target.value }))}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                />
                <span className="mt-0.5 block text-[11px] text-slate-400">{field.helper}</span>
              </label>
            ))}
          </div>
        ) : (
          <div className="mt-4 h-40 animate-pulse rounded-xl bg-slate-100" />
        )}
        <div className="mt-5 rounded-xl border border-slate-100 bg-slate-50 p-3">
          <p className="text-xs font-medium text-slate-700">Mensagens antigas do IXC</p>
          <p className="mt-0.5 text-[11px] text-slate-500">
            Busca no IXC o texto da mensagem/histórico dos eventos sincronizados antes desse recurso existir. Eventos novos já chegam com o texto pelo sync normal.
          </p>
          {backfillMessage ? <p className="mt-1.5 text-[11px] text-emerald-700">{backfillMessage}</p> : null}
          <Button type="button" size="sm" variant="outline" className="mt-2" onClick={() => void runMessagesBackfill()} disabled={backfilling}>
            {backfilling ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Buscar mensagens antigas
          </Button>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancelar</Button>
          <Button type="button" onClick={() => void save()} disabled={saving || !values}>
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Salvar
          </Button>
        </div>
      </div>
    </div>
  );
}

function TeamDialog({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [members, setMembers] = useState<SchedulingTeamMember[] | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    void schedulingApi.team().then(setMembers).catch(() => setError("Falha ao carregar os operadores."));
  }, []);

  const visible = (members || []).filter((member) => member.name.toLocaleLowerCase("pt-BR").includes(query.toLocaleLowerCase("pt-BR")));

  async function save() {
    if (!members) return;
    setSaving(true);
    setError(null);
    try {
      await schedulingApi.updateTeam(members.filter((m) => m.is_team_member).map((m) => m.ixc_user_id));
      onSaved();
      onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao salvar a equipe.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4" role="dialog" aria-modal="true">
      <div className="flex max-h-[85vh] w-full max-w-lg flex-col rounded-2xl bg-white p-5 shadow-xl">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-950">Equipe de agendamento</h2>
            <p className="text-xs text-slate-500">A meta diária só é cobrada de quem está marcado como membro.</p>
          </div>
          <Button type="button" size="sm" variant="ghost" onClick={onClose} aria-label="Fechar"><X className="h-4 w-4" /></Button>
        </div>
        {error ? <p className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p> : null}
        <input
          type="search"
          placeholder="Buscar operador..."
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="mt-3 rounded-lg border border-slate-200 px-3 py-2 text-sm"
        />
        <div className="mt-2 flex-1 space-y-1 overflow-y-auto">
          {members === null ? (
            <div className="h-40 animate-pulse rounded-xl bg-slate-100" />
          ) : (
            visible.map((member) => (
              <label key={member.ixc_user_id} className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-slate-700 hover:bg-slate-50">
                <input
                  type="checkbox"
                  checked={member.is_team_member}
                  onChange={() =>
                    setMembers((current) =>
                      (current || []).map((item) =>
                        item.ixc_user_id === member.ixc_user_id ? { ...item, is_team_member: !item.is_team_member } : item,
                      ),
                    )
                  }
                  className="h-4 w-4 rounded border-slate-300"
                />
                <span className="truncate">{member.name}</span>
              </label>
            ))
          )}
        </div>
        <div className="mt-4 flex items-center justify-between gap-2">
          <p className="text-xs text-slate-500">{(members || []).filter((m) => m.is_team_member).length} membro(s) na equipe</p>
          <div className="flex gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>Cancelar</Button>
            <Button type="button" onClick={() => void save()} disabled={saving || members === null}>
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Salvar equipe
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
