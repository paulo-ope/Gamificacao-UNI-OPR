"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import { commonDateRangePresets, DateRangePicker } from "@/components/ui/date-range-picker";
import { StatusToast } from "@/components/ui/status-toast";
import { Tabs, TabsContent } from "@/components/ui/tabs";
import { WorkspaceAppShell } from "@/components/workspace/app-shell";
import type { AuthUser } from "@/lib/types";
import {
  schedulingApi,
  type SchedulingBacklogItem,
  type SchedulingDashboard,
  type SchedulingFilterOptions,
  type SchedulingFilterState,
  type SchedulingOrderDrillParams,
  type SchedulingRescheduleByOperatorItem,
  type SchedulingRescheduleByTechnicianItem,
  type SchedulingSavedFilter,
  type SchedulingSavedFilterValues,
  type SchedulingSyncHealth,
  type SchedulingSyncStatus,
} from "@/lib/scheduling-api";

import { SchedulingAdministrationPanel } from "@/components/scheduling/scheduling-administration-panel";
import { SchedulingAgingBar } from "@/components/scheduling/scheduling-aging-bar";
import { SchedulingBacklogPanel } from "@/components/scheduling/scheduling-backlog-panel";
import { SchedulingDayBreakdownCharts } from "@/components/scheduling/scheduling-day-breakdown-charts";
import { SchedulingDayDrawer } from "@/components/scheduling/scheduling-day-drawer";
import { SchedulingFiltersBar } from "@/components/scheduling/scheduling-filters-bar";
import { currentMonthKey, defaultPeriod, isoDate, monthBounds, shiftMonth, type MonthKey } from "@/components/scheduling/scheduling-format";
import { SCHEDULING_NAV_ITEMS, type SchedulingTab } from "@/components/scheduling/scheduling-module-sidebar";
import { SchedulingMonthCalendar } from "@/components/scheduling/scheduling-month-calendar";
import { OperatorEventsDrillPanel } from "@/components/scheduling/scheduling-operator-events-panel";
import { OrderDrillPanel } from "@/components/scheduling/scheduling-order-drill-panel";
import { SchedulingPerformancePanel } from "@/components/scheduling/scheduling-performance-panel";
import { SchedulingRankingsPanel } from "@/components/scheduling/scheduling-rankings-panel";
import { SchedulingSyncBadge } from "@/components/scheduling/scheduling-sync-badge";
import { TechnicianEventsDrillPanel } from "@/components/scheduling/scheduling-technician-events-panel";
import { SchedulingTodaySummary } from "@/components/scheduling/scheduling-today-summary";
import { SchedulingTrendChart } from "@/components/scheduling/scheduling-trend-chart";

const EMPTY_OPTIONS: SchedulingFilterOptions = {
  filiais: [],
  setores: [],
  assuntos: [],
  operators: [],
  technicians: [],
  data_available_from: null,
  data_available_to: null,
};

type SecondaryFilters = Omit<SchedulingFilterState, "date_from" | "date_to">;

const DEFAULT_SECONDARY_FILTERS: SecondaryFilters = {
  filial_ids: [],
  setor_ids: [],
  assunto_ids: [],
  operator_ids: [],
  technician_ids: [],
  count_mode: "all_events",
};

const TAB_TITLES: Record<SchedulingTab, { title: string; subtitle: string }> = {
  painel: { title: "Painel", subtitle: "Resumo do dia e calendário mensal de reagendamentos" },
  rankings: { title: "Rankings e fila", subtitle: "Produtividade, reagendamentos por pessoa e O.S. sem agendamento" },
  desempenho: { title: "Desempenho", subtitle: "SLA e tempo de resposta do setor" },
  administracao: { title: "Administração", subtitle: "Equipe, configurações e sincronização" },
};

// Filtros de recorte (filial/setor/assunto/operador/técnico) só fazem sentido nas views que
// mostram dados filtráveis - Administração é status e cadastro, não dados de período.
const TABS_WITH_FILTERS: SchedulingTab[] = ["painel", "rankings", "desempenho"];

function toFilterState(bounds: { date_from: string; date_to: string }, secondary: SecondaryFilters): SchedulingFilterState {
  return { ...bounds, ...secondary };
}

export default function AgendamentoPage() {
  return (
    <WorkspaceAppShell
      activePath="/agendamento"
      title="Agendamento"
      subtitle="Tempo de resposta, produtividade e fila do setor de agendamento"
    >
      {(user) => (
        <Suspense
          fallback={
            <p className="py-16 text-center text-sm text-slate-500" aria-busy="true">
              Carregando Agendamento...
            </p>
          }
        >
          <AgendamentoPageContent user={user} />
        </Suspense>
      )}
    </WorkspaceAppShell>
  );
}

// A casca (`WorkspaceAppShell`) resolve autenticação, cabeçalho, sino, sair e o menu lateral com
// as telas deste módulo - aqui só chega o usuário pronto.
function AgendamentoPageContent({ user }: { user: AuthUser }) {
  const canRead = Boolean(user?.permissions.includes("scheduling:read"));
  const canSync = Boolean(user?.permissions.includes("scheduling:sync"));
  const canManage = Boolean(user?.permissions.includes("scheduling:manage"));
  const canManageFilters = Boolean(user?.permissions.includes("scheduling:manage_filters"));
  const canManageGlobalViews = Boolean(user?.permissions.includes("scheduling:views:manage_global"));

  const [activeTab, setActiveTab] = useState<SchedulingTab>("painel");

  // Abre direto na tela pedida pela URL (`?tab=`), que é como o menu lateral do ecossistema
  // linka as telas deste módulo. Mesma convenção que a Administração e o SGP Suporte já usavam.
  const searchParams = useSearchParams();
  useEffect(() => {
    const tab = searchParams.get("tab");
    if (tab && SCHEDULING_NAV_ITEMS.some((item) => item.value === tab)) setActiveTab(tab as SchedulingTab);
  }, [searchParams]);
  const [month, setMonth] = useState<MonthKey>(currentMonthKey);
  const [period, setPeriod] = useState<{ date_from: string; date_to: string }>(defaultPeriod);
  const [filters, setFilters] = useState<SecondaryFilters>(DEFAULT_SECONDARY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<SecondaryFilters>(DEFAULT_SECONDARY_FILTERS);
  const [options, setOptions] = useState<SchedulingFilterOptions>(EMPTY_OPTIONS);
  const [dashboard, setDashboard] = useState<SchedulingDashboard | null>(null);
  const [todayDashboard, setTodayDashboard] = useState<SchedulingDashboard | null>(null);
  const [backlog, setBacklog] = useState<SchedulingBacklogItem[]>([]);
  const [reschedulesByTechnician, setReschedulesByTechnician] = useState<SchedulingRescheduleByTechnicianItem[]>([]);
  const [reschedulesByOperator, setReschedulesByOperator] = useState<SchedulingRescheduleByOperatorItem[]>([]);
  // Dados das abas Rankings e Desempenho - janela própria (`period`), independente do mês em
  // navegação no calendário do Painel (pedido do usuário 2026-08-31, ver `defaultPeriod`).
  const [periodDashboard, setPeriodDashboard] = useState<SchedulingDashboard | null>(null);
  const [periodBacklog, setPeriodBacklog] = useState<SchedulingBacklogItem[]>([]);
  const [periodReschedulesByTechnician, setPeriodReschedulesByTechnician] = useState<SchedulingRescheduleByTechnicianItem[]>([]);
  const [periodReschedulesByOperator, setPeriodReschedulesByOperator] = useState<SchedulingRescheduleByOperatorItem[]>([]);
  const [periodLoading, setPeriodLoading] = useState(false);
  const [syncStatus, setSyncStatus] = useState<SchedulingSyncStatus | null>(null);
  const [syncHealth, setSyncHealth] = useState<SchedulingSyncHealth | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const [drill, setDrill] = useState<{ title: string; subtitle: string; params: SchedulingOrderDrillParams; filters: SchedulingFilterState } | null>(null);
  const [operatorEventsDrill, setOperatorEventsDrill] = useState<{ operatorId: number; title: string } | null>(null);
  const [technicianEventsDrill, setTechnicianEventsDrill] = useState<{ technicianId: number; title: string } | null>(null);

  const [savedFilters, setSavedFilters] = useState<SchedulingSavedFilter[]>([]);
  const [selectedSavedFilterId, setSelectedSavedFilterId] = useState<number | null>(null);
  const [filterName, setFilterName] = useState("");
  const [savedFilterVisibility, setSavedFilterVisibility] = useState<"personal" | "global">("personal");

  const monthBoundsValue = useMemo(() => monthBounds(month), [month]);
  const todayIso = useMemo(() => isoDate(new Date()), []);
  const monthFilterState = useMemo(() => toFilterState(monthBoundsValue, appliedFilters), [monthBoundsValue, appliedFilters]);
  const todayFilterState = useMemo(
    () => toFilterState({ date_from: todayIso, date_to: todayIso }, appliedFilters),
    [todayIso, appliedFilters],
  );
  const periodFilterState = useMemo(() => toFilterState(period, appliedFilters), [period, appliedFilters]);

  const loadMonthData = useCallback(async (nextMonth: MonthKey, secondary: SecondaryFilters, signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const bounds = monthBounds(nextMonth);
      const monthFilters = toFilterState(bounds, secondary);
      const todayFilters = toFilterState({ date_from: isoDate(new Date()), date_to: isoDate(new Date()) }, secondary);
      const [nextDashboard, nextToday, nextBacklog, nextByTechnician, nextByOperator] = await Promise.all([
        schedulingApi.dashboard(monthFilters, signal),
        schedulingApi.dashboard(todayFilters, signal),
        schedulingApi.backlog(monthFilters, 100, signal),
        schedulingApi.reschedulesByTechnician(monthFilters, signal),
        schedulingApi.reschedulesByOperator(monthFilters, signal),
      ]);
      setDashboard(nextDashboard);
      setTodayDashboard(nextToday);
      setBacklog(nextBacklog);
      setReschedulesByTechnician(nextByTechnician.items);
      setReschedulesByOperator(nextByOperator.items);
      setAppliedFilters(secondary);
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      setError(reason instanceof Error ? reason.message : "Falha ao carregar o módulo de Agendamento.");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadPeriodData = useCallback(async (nextPeriod: { date_from: string; date_to: string }, secondary: SecondaryFilters, signal?: AbortSignal) => {
    setPeriodLoading(true);
    setError(null);
    try {
      const periodFilters = toFilterState(nextPeriod, secondary);
      const [nextDashboard, nextBacklog, nextByTechnician, nextByOperator] = await Promise.all([
        schedulingApi.dashboard(periodFilters, signal),
        schedulingApi.backlog(periodFilters, 100, signal),
        schedulingApi.reschedulesByTechnician(periodFilters, signal),
        schedulingApi.reschedulesByOperator(periodFilters, signal),
      ]);
      setPeriodDashboard(nextDashboard);
      setPeriodBacklog(nextBacklog);
      setPeriodReschedulesByTechnician(nextByTechnician.items);
      setPeriodReschedulesByOperator(nextByOperator.items);
      setAppliedFilters(secondary);
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      setError(reason instanceof Error ? reason.message : "Falha ao carregar rankings e desempenho do período.");
    } finally {
      setPeriodLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!user || !canRead) return;
    const controller = new AbortController();
    void schedulingApi.syncStatus().then(setSyncStatus).catch(() => undefined);
    void schedulingApi.syncHealth().then(setSyncHealth).catch(() => undefined);
    // /team antes do dashboard de propósito: é ele que resolve (uma única vez, com cache no banco)
    // os nomes de operadores novos junto ao IXC - sem isso o primeiro acesso mostraria
    // "Operador IXC 445" em vez do nome.
    void Promise.allSettled([schedulingApi.team(), schedulingApi.resolveTechnicians()]).then(() => {
      void schedulingApi.filters().then(setOptions).catch(() => undefined);
      void loadMonthData(month, filters, controller.signal);
      void loadPeriodData(period, filters, controller.signal);
    });
    void schedulingApi.savedFilters().then(setSavedFilters).catch(() => undefined);
    return () => controller.abort();
    // Carga inicial única por sessão - navegação de mês e aplicar filtros passam por handlers próprios.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, canRead]);

  function navigateMonth(delta: number) {
    const next = shiftMonth(month, delta);
    setMonth(next);
    void loadMonthData(next, appliedFilters);
  }

  function goToToday() {
    const next = currentMonthKey();
    setMonth(next);
    void loadMonthData(next, appliedFilters);
  }

  function changePeriod(next: { date_from: string; date_to: string }) {
    setPeriod(next);
    void loadPeriodData(next, appliedFilters);
  }

  function applyFilters() {
    void loadMonthData(month, filters);
    void loadPeriodData(period, filters);
  }

  async function refreshAfterSync() {
    const [status, health] = await Promise.all([schedulingApi.syncStatus(), schedulingApi.syncHealth()]);
    setSyncStatus(status);
    setSyncHealth(health);
    await Promise.all([loadMonthData(month, appliedFilters), loadPeriodData(period, appliedFilters)]);
    // Um sync pode trazer operadores/técnicos novos (nunca vistos antes) - resolver o nome deles
    // no IXC ANTES de recarregar os filtros, senão a lista mostra "Operador IXC {id}" até a
    // próxima carga de página (achado real, 2026-07-30: aconteceu logo após um sync).
    await Promise.allSettled([schedulingApi.team(), schedulingApi.resolveTechnicians()]);
    void schedulingApi.filters().then(setOptions).catch(() => undefined);
  }

  function savedValues(current: SecondaryFilters): SchedulingSavedFilterValues {
    return {
      filial_ids: current.filial_ids,
      setor_ids: current.setor_ids,
      assunto_ids: current.assunto_ids,
      operator_ids: current.operator_ids,
      technician_ids: current.technician_ids,
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
    const next: SecondaryFilters = {
      filial_ids: saved.filters.filial_ids,
      setor_ids: saved.filters.setor_ids,
      assunto_ids: saved.filters.assunto_ids,
      operator_ids: saved.filters.operator_ids,
      technician_ids: saved.filters.technician_ids,
      count_mode: saved.filters.count_mode,
    };
    setFilterName(saved.name);
    setSavedFilterVisibility(saved.visibility);
    setFilters(next);
    void loadMonthData(month, next);
    void loadPeriodData(period, next);
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

  function openDrill(title: string, subtitle: string, params: SchedulingOrderDrillParams, filterState: SchedulingFilterState) {
    setDrill({ title, subtitle, params, filters: filterState });
  }

  const summary = dashboard?.summary;
  const todaySummary = todayDashboard?.summary;
  const todayPoint = todayDashboard?.daily_series[0] ?? null;

  if (!canRead) {
    return (
      <div className="mx-auto max-w-md rounded-2xl border border-amber-200 bg-amber-50 p-6 text-center text-amber-900">
        <h2 className="text-xl font-semibold">Acesso não autorizado</h2>
        <p className="mt-2 text-sm">Seu perfil não possui a permissão scheduling:read.</p>
      </div>
    );
  }

  const tabInfo = TAB_TITLES[activeTab];

  return (
    <div className="min-w-0">
      <section className="flex flex-wrap items-center justify-between gap-2 pb-1">
        <div className="flex min-w-0 items-baseline gap-2">
          <h2 className="text-lg font-semibold text-slate-950">{tabInfo.title}</h2>
          <p className="truncate text-xs text-slate-500">{tabInfo.subtitle}</p>
        </div>
        <SchedulingSyncBadge health={syncHealth} syncing={false} onOpenSync={() => setActiveTab("administracao")} />
      </section>

      <StatusToast error={error} message={message} onDismissError={() => setError(null)} onDismissMessage={() => setMessage(null)} />

      {TABS_WITH_FILTERS.includes(activeTab) ? (
        <SchedulingFiltersBar
          filters={toFilterState(monthBoundsValue, filters)}
          options={options}
          loading={loading || periodLoading}
          savedFilters={savedFilters}
          selectedSavedFilterId={selectedSavedFilterId}
          filterName={filterName}
          savedFilterVisibility={savedFilterVisibility}
          canManageFilters={canManageFilters}
          canManageGlobalViews={canManageGlobalViews}
          onChange={(next) => setFilters({
            filial_ids: next.filial_ids,
            setor_ids: next.setor_ids,
            assunto_ids: next.assunto_ids,
            operator_ids: next.operator_ids,
            technician_ids: next.technician_ids,
            count_mode: next.count_mode,
          })}
          onApply={applyFilters}
          onSelectSavedFilter={selectSavedFilter}
          onNameChange={setFilterName}
          onVisibilityChange={setSavedFilterVisibility}
          onSave={() => void saveCurrentFilter()}
          onUpdate={() => void updateCurrentSavedFilter()}
          onDelete={() => void deleteCurrentSavedFilter()}
        />
      ) : null}

      {activeTab === "rankings" || activeTab === "desempenho" ? (
        <div className="border-b border-slate-200 bg-white px-4 py-2 lg:px-7">
          <DateRangePicker
            label="Período (rankings e desempenho)"
            dateFrom={period.date_from}
            dateTo={period.date_to}
            presets={commonDateRangePresets()}
            onChange={(key, value) => changePeriod({ ...period, [key]: value })}
          />
        </div>
      ) : null}

      <section className="px-4 py-5 lg:px-7">
        {!syncStatus?.orders_count && !loading ? (
          <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            Nenhum dado sincronizado ainda. Abra a aba &quot;Administração&quot; para fazer a primeira carga.
          </div>
        ) : null}

        <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as SchedulingTab)}>
          <TabsContent value="painel" className="mt-0 space-y-4">
            <SchedulingTodaySummary
              todayPoint={todayPoint}
              todaySlaRate={todaySummary?.sla_rate ?? null}
              todaySlaTarget={todaySummary?.sla_target_pct ?? null}
              pendingOrders={summary?.pending_orders ?? null}
              loading={loading && !dashboard}
              onOpenToday={() => setSelectedDay(todayIso)}
              onOpenPending={() => openDrill("O.S. aguardando agendamento", "Todas as pendentes do recorte, mais antigas primeiro", { status: "pending" }, monthFilterState)}
            />
            <div className="grid gap-4 xl:grid-cols-[1.1fr_1.4fr]">
              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
                <SchedulingMonthCalendar
                  month={month}
                  dailyPoints={dashboard?.daily_series || []}
                  loading={loading && !dashboard}
                  onNavigate={navigateMonth}
                  onGoToday={goToToday}
                  onSelectDay={setSelectedDay}
                  selectedDay={selectedDay}
                />
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
                <h3 className="mb-2 text-sm font-semibold text-slate-950">Tendência do mês</h3>
                <SchedulingTrendChart dailyPoints={dashboard?.daily_series || []} />
              </div>
            </div>
            <SchedulingDayBreakdownCharts day={todayIso} filters={todayFilterState} />
            <SchedulingAgingBar
              buckets={dashboard?.backlog_aging || []}
              onSelectBucket={(bucket, label, count) =>
                openDrill(`Fila: ${label}`, `${count} O.S. aguardando agendamento nessa faixa`, { status: "pending", backlog_bucket: bucket }, monthFilterState)
              }
            />
          </TabsContent>

          <TabsContent value="rankings" className="mt-0 space-y-4">
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
              <SchedulingRankingsPanel
                dashboard={periodDashboard}
                reschedulesByOperator={periodReschedulesByOperator}
                reschedulesByTechnician={periodReschedulesByTechnician}
                filters={periodFilterState}
                onOpenOperatorFirstSchedules={(operatorId, operatorName) =>
                  openDrill(operatorName, "O.S. em que este operador foi o primeiro a agendar", { operator_ids: [operatorId] }, periodFilterState)
                }
                onOpenOperatorEvents={(operatorId, operatorName) => setOperatorEventsDrill({ operatorId, title: operatorName })}
                onOpenTechnicianEvents={(technicianId, technicianName) => setTechnicianEventsDrill({ technicianId, title: technicianName })}
                onOpenFilialLate={(filialId, filialLabel) =>
                  openDrill(`Atraso em ${filialLabel}`, "Agendadas depois do prazo útil configurado nessa filial", {
                    filial_ids: [filialId],
                    status: "scheduled",
                    sla_status: "late",
                  }, periodFilterState)
                }
                onOpenAssuntoLate={(assuntoId, assuntoLabel) =>
                  openDrill(`Atraso em ${assuntoLabel}`, "Agendadas depois do prazo útil configurado nesse assunto", {
                    assunto_ids: [assuntoId],
                    status: "scheduled",
                    sla_status: "late",
                  }, periodFilterState)
                }
              />
            </div>
            <div>
              <h3 className="mb-3 text-sm font-semibold text-slate-950">Fila de trabalho</h3>
              <SchedulingBacklogPanel
                backlogAging={periodDashboard?.backlog_aging || []}
                backlog={periodBacklog}
                filters={periodFilterState}
                onOpenBucket={(bucket, label, count) =>
                  openDrill(`Fila: ${label}`, `${count} O.S. aguardando agendamento nessa faixa`, { status: "pending", backlog_bucket: bucket }, periodFilterState)
                }
              />
            </div>
          </TabsContent>

          <TabsContent value="desempenho" className="mt-0">
            <SchedulingPerformancePanel
              dashboard={periodDashboard}
              onOpenSlaLate={() => openDrill("O.S. fora do SLA de agendamento", "Agendadas depois do prazo útil configurado", { sla_status: "late", status: "scheduled" }, periodFilterState)}
              onOpenTtfaBucket={(bucket, count) => openDrill(`Tempo até agendar: ${bucket}`, `${count} O.S. nessa faixa`, { ttfa_bucket: bucket, status: "scheduled" }, periodFilterState)}
            />
          </TabsContent>

          <TabsContent value="administracao" className="mt-0">
            <SchedulingAdministrationPanel
              canManage={canManage}
              canSync={canSync}
              syncHealth={syncHealth}
              syncStatus={syncStatus}
              onSaved={() => void loadMonthData(month, appliedFilters)}
              onSynced={() => void refreshAfterSync()}
            />
          </TabsContent>
        </Tabs>
      </section>

      {selectedDay ? (
        <SchedulingDayDrawer
          day={selectedDay}
          filters={selectedDay === todayIso ? todayFilterState : monthFilterState}
          onClose={() => setSelectedDay(null)}
        />
      ) : null}
      {drill ? (
        <OrderDrillPanel
          key={drill.title}
          title={drill.title}
          subtitle={drill.subtitle}
          filters={drill.filters}
          params={drill.params}
          onClose={() => setDrill(null)}
        />
      ) : null}
      {operatorEventsDrill ? (
        <OperatorEventsDrillPanel
          operatorId={operatorEventsDrill.operatorId}
          title={operatorEventsDrill.title}
          filters={periodFilterState}
          onClose={() => setOperatorEventsDrill(null)}
        />
      ) : null}
      {technicianEventsDrill ? (
        <TechnicianEventsDrillPanel
          technicianId={technicianEventsDrill.technicianId}
          title={technicianEventsDrill.title}
          filters={periodFilterState}
          onClose={() => setTechnicianEventsDrill(null)}
        />
      ) : null}
    </div>
  );
}
