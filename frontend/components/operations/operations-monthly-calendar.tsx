"use client";

import {
  ArrowLeft,
  CalendarDays,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  ClipboardList,
  FileSpreadsheet,
  Loader2,
  MapPin,
  ShieldAlert,
  Target,
  UserRound,
} from "lucide-react";
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { OperationsCalendarDayMetricsPanel } from "@/components/operations/operations-calendar-day-metrics";
import { OperationsCapacitySummaryCards } from "@/components/operations/operations-capacity-summary-cards";
import { OperationsOrderDetailDialog } from "@/components/operations/operations-order-detail-dialog";
import { CaseDetailDialog } from "@/components/management/management-cases-panel";
import { api } from "@/lib/api";
import type { ManagementCaseReason } from "@/lib/types";
import {
  operationsApi,
  type OperationCalendar,
  type OperationCalendarDayMetrics,
  type OperationCalendarMonthlyDetail,
  type OperationCalendarTeamModel,
  type OperationFilterState,
  type OperationOrder,
  type OperationOrderPage,
  type OperationPerformanceBand,
} from "@/lib/operations-api";
import {
  customBackground,
  dayTarget,
  modelLegend,
  performanceLabel,
  ruleFor,
} from "@/lib/operations-calendar-helpers";
import { useCalendarExport } from "@/hooks/use-calendar-export";
import { cn } from "@/lib/utils";

function weekdayOf(dayIso: string): number {
  const utcDay = new Date(`${dayIso}T12:00:00Z`).getUTCDay();
  return utcDay === 0 ? 6 : utcDay - 1;
}

// Mesmo criterio de normalizacao do backend (casefold + colapsa espaco) para casar o responsavel
// do caso com o responsavel da celula do calendario, independente de acento/maiusculo.
function dailyCaseKey(responsibleName: string, referenceDate: string): string {
  return `${responsibleName.trim().toLowerCase().replace(/\s+/g, " ")}|${referenceDate}`;
}

const DAILY_CASE_STATUS_DOT: Record<string, string> = {
  pending: "bg-amber-500",
  justified: "bg-blue-500",
  in_progress: "bg-violet-500",
  resolved: "bg-emerald-500",
  rejected: "bg-slate-400",
};

const DAILY_CASE_STATUS_LABEL: Record<string, string> = {
  pending: "Aguardando justificativa",
  justified: "Justificado, aguardando decisão da matriz",
  in_progress: "Em andamento",
  resolved: "Resolvido pela matriz",
  rejected: "Rejeitado pela matriz",
};

const WEEKDAYS = ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM"];
const EMPTY_PAGE: OperationOrderPage = {
  items: [],
  total: 0,
  page: 1,
  page_size: 50,
  total_pages: 0,
};
const EMPTY_METRICS: OperationCalendarDayMetrics = {
  total_orders: 0,
  active_days: 0,
  timed_orders: 0,
  missing_execution_times: 0,
  average_execution_minutes: null,
  median_execution_minutes: null,
  minimum_execution_minutes: null,
  maximum_execution_minutes: null,
  average_pre_displacement_minutes: null,
  average_total_minutes: null,
  sla_rate: null,
  first_displacement_at: null,
  last_finished_at: null,
  operational_window_orders: 0,
  missing_operational_window_times: 0,
  total_execution_minutes: null,
  average_displacement_minutes: null,
  total_displacement_minutes: null,
  displacement_orders: 0,
  attended_regionals: [],
  cross_regional_orders: 0,
  type_counts: {},
};
const EMPTY_MONTHLY_DETAIL: OperationCalendarMonthlyDetail = {
  metrics: {
    total_orders: 0,
    active_days: 0,
    timed_orders: 0,
    missing_execution_times: 0,
    average_execution_minutes: null,
    median_execution_minutes: null,
    average_total_minutes: null,
    total_execution_minutes: null,
    average_displacement_minutes: null,
    total_displacement_minutes: null,
    displacement_orders: 0,
    sla_rate: null,
    attended_regionals: [],
    cross_regional_orders: 0,
  },
  by_regional: [],
  orders: EMPTY_PAGE,
};

const PERFORMANCE: Record<
  OperationPerformanceBand,
  { label: string; className: string }
> = {
  neutral: {
    label: "Sem produção",
    className: "border-slate-100 bg-slate-50 text-slate-300",
  },
  below: {
    label: "Abaixo da meta",
    className: "border-red-200 bg-red-50 text-red-700",
  },
  median: {
    label: "Boa",
    className: "border-amber-200 bg-amber-50 text-amber-700",
  },
  good: {
    label: "Ótima",
    className: "border-emerald-200 bg-emerald-50 text-emerald-700",
  },
  excellent: {
    label: "Excelente",
    className: "border-blue-200 bg-blue-50 text-blue-700",
  },
};

type SelectedCell = {
  day: string;
  periodEnd?: string;
  periodLabel?: string;
  regional: string;
  responsible: string;
  quantity: number;
  performance: OperationPerformanceBand;
  teamModel: OperationCalendarTeamModel | null;
  referenceRegional: string | null;
};

const ALL_RESPONSIBLES = "__ALL__";

type SelectedMonthly = Omit<
  SelectedCell,
  "day" | "periodEnd" | "periodLabel"
>;

function competenceLabel(competence: string) {
  const [year, month] = competence.split("-").map(Number);
  if (!year || !month) return "Competência mensal";
  return new Intl.DateTimeFormat("pt-BR", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(year, month - 1, 1)));
}

function shortDate(value: string) {
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "long",
    timeZone: "UTC",
  }).format(new Date(`${value}T12:00:00Z`));
}

function dateTime(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "America/Porto_Velho",
  }).format(new Date(value));
}

function duration(value: number | null) {
  if (value === null) return "—";
  const rounded = Math.round(value);
  if (rounded < 60) return `${rounded} min`;
  const hours = Math.floor(rounded / 60);
  const minutes = rounded % 60;
  return minutes ? `${hours}h ${minutes}min` : `${hours}h`;
}

function performanceClass(
  performance: OperationPerformanceBand,
  quantity: number,
  model: OperationCalendarTeamModel | null,
) {
  if (!model && quantity > 0)
    return "border-slate-200 bg-slate-50 text-slate-700";
  return PERFORMANCE[performance].className;
}

function CalendarSkeleton() {
  return (
    <div
      className="space-y-4"
      aria-label="Carregando calendário operacional"
      aria-busy="true"
    >
      <div className="h-28 animate-pulse rounded-2xl border border-slate-200 bg-white" />
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <div className="h-12 animate-pulse bg-slate-900" />
        <div className="space-y-px bg-slate-100 p-px">
          {[0, 1, 2, 3, 4].map((row) => (
            <div key={row} className="h-14 animate-pulse bg-white" />
          ))}
        </div>
      </div>
    </div>
  );
}

export function OperationsMonthlyCalendar({
  data,
  filters,
  isLoading,
  groupBy,
  onGroupByChange,
  onBack,
  canJustifyManagement = false,
  canReviewManagement = false,
}: {
  data: OperationCalendar;
  filters: OperationFilterState;
  isLoading: boolean;
  groupBy: "regional" | "collaborator";
  onGroupByChange: (groupBy: "regional" | "collaborator") => void;
  onBack: () => void;
  canJustifyManagement?: boolean;
  canReviewManagement?: boolean;
}) {
  const [selected, setSelected] = useState<SelectedCell | null>(null);
  const [orders, setOrders] = useState<OperationOrderPage>(EMPTY_PAGE);
  const [metrics, setMetrics] =
    useState<OperationCalendarDayMetrics>(EMPTY_METRICS);
  const [selectedOrder, setSelectedOrder] = useState<OperationOrder | null>(
    null,
  );
  const [selectedMonthly, setSelectedMonthly] =
    useState<SelectedMonthly | null>(null);
  const [monthlyDetail, setMonthlyDetail] =
    useState<OperationCalendarMonthlyDetail>(EMPTY_MONTHLY_DETAIL);
  const [monthlyLoading, setMonthlyLoading] = useState(false);
  const [monthlyError, setMonthlyError] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [expandedRegional, setExpandedRegional] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  // Legenda comeca fechada de proposito (pedido do usuario) - o calendario e o que importa ao
  // abrir a tela; quem ja sabe o que as cores significam nao precisa rolar por ela toda vez.
  const [legendOpen, setLegendOpen] = useState(false);
  const exportWorkbook = useCalendarExport();

  // Justificativa do dia vermelho (drill do calendário -> Gestão Integrada): abre/recupera um
  // ManagementCase para o dia clicado e reaproveita o mesmo diálogo de justificativa da Gestão
  // Integrada, em vez de duplicar a UI de justificar/comentar aqui.
  const [caseReasons, setCaseReasons] = useState<ManagementCaseReason[]>([]);
  const [dailyCaseId, setDailyCaseId] = useState<number | null>(null);
  const [openingCase, setOpeningCase] = useState(false);
  const [openCaseError, setOpenCaseError] = useState<string | null>(null);
  // Status do caso de cada dia ja justificado/em analise neste mes - sem isso o supervisor so
  // descobre que um dia ja foi tratado clicando nele de novo, um por um (achado real, 2026-08-13).
  // Chave: responsavel normalizado + data (a mesma dupla que identifica um caso diario no backend).
  const [dailyCaseStatusByKey, setDailyCaseStatusByKey] = useState<Map<string, string>>(new Map());

  useEffect(() => {
    if (!canJustifyManagement) return;
    void api.managementCaseReasons().then(setCaseReasons).catch(() => undefined);
  }, [canJustifyManagement]);

  const loadDailyCaseStatuses = useCallback(async () => {
    if (!canJustifyManagement || !data.competence) return;
    const [year, month] = data.competence.split("-").map(Number);
    if (!year || !month) return;
    try {
      const page = await api.managementCases({
        case_type: "daily_performance_below_target",
        reference_year: year,
        reference_month: month,
        page_size: 200,
      });
      const next = new Map<string, string>();
      for (const item of page.items) {
        if (!item.responsible_name || !item.reference_date) continue;
        next.set(dailyCaseKey(item.responsible_name, item.reference_date), item.status);
      }
      setDailyCaseStatusByKey(next);
    } catch {
      // Indicador e so um reforco visual - falha aqui nao deve travar o calendario.
    }
  }, [canJustifyManagement, data.competence]);

  useEffect(() => {
    void loadDailyCaseStatuses();
  }, [loadDailyCaseStatuses]);

  async function openDailyJustification(cell: SelectedCell) {
    setOpeningCase(true);
    setOpenCaseError(null);
    try {
      const expected = dayTarget(cell.teamModel, weekdayOf(cell.day))?.target_quantity ?? null;
      const managementCase = await api.openDailyManagementCase({
        responsible_name: cell.responsible,
        regional: cell.referenceRegional ?? cell.regional,
        reference_date: cell.day,
        expected_value: expected,
        actual_value: cell.quantity,
      });
      setDailyCaseId(managementCase.id);
      // Fecha o painel do dia ao abrir a justificativa - com os dois abertos ao mesmo tempo, o
      // Radix (Sheet) marca tudo que nao e o proprio modal como inerte/oculto pra acessibilidade,
      // e o dialogo de justificativa (que roda por cima via portal) ficava impossivel de clicar,
      // inclusive o proprio botao de fechar (achado real, 2026-08-13).
      setSelected(null);
    } catch (reason) {
      setOpenCaseError(reason instanceof Error ? reason.message : "Não foi possível abrir a justificativa deste dia.");
    } finally {
      setOpeningCase(false);
    }
  }

  async function handleExport() {
    setExporting(true);
    setExportError(null);
    try {
      await exportWorkbook(data);
    } catch (reason) {
      setExportError(reason instanceof Error ? reason.message : "Não foi possível gerar a planilha.");
    } finally {
      setExporting(false);
    }
  }
  const monthlyPanelMetrics = useMemo<OperationCalendarDayMetrics>(
    () => ({
      ...EMPTY_METRICS,
      total_orders: monthlyDetail.metrics.total_orders,
      active_days: monthlyDetail.metrics.active_days,
      timed_orders: monthlyDetail.metrics.timed_orders,
      missing_execution_times: monthlyDetail.metrics.missing_execution_times,
      average_execution_minutes:
        monthlyDetail.metrics.average_execution_minutes,
      median_execution_minutes: monthlyDetail.metrics.median_execution_minutes,
      average_total_minutes: monthlyDetail.metrics.average_total_minutes,
      sla_rate: monthlyDetail.metrics.sla_rate,
      total_execution_minutes: monthlyDetail.metrics.total_execution_minutes,
      average_displacement_minutes:
        monthlyDetail.metrics.average_displacement_minutes,
      total_displacement_minutes:
        monthlyDetail.metrics.total_displacement_minutes,
      displacement_orders: monthlyDetail.metrics.displacement_orders,
      attended_regionals: monthlyDetail.metrics.attended_regionals,
      cross_regional_orders: monthlyDetail.metrics.cross_regional_orders,
    }),
    [monthlyDetail],
  );

  async function loadCell(cell: SelectedCell, page = 1) {
    setSelected(cell);
    setDetailLoading(true);
    setDetailError(null);
    try {
      const detail =
        cell.periodEnd && cell.periodEnd !== cell.day
          ? await operationsApi.calendarWeekDetail(
              filters,
              cell.day,
              cell.periodEnd,
              cell.regional,
              cell.responsible,
              groupBy,
              cell.referenceRegional,
              page,
            )
          : await operationsApi.calendarDayDetail(
              filters,
              cell.day,
              cell.regional,
              cell.responsible,
              groupBy,
              cell.referenceRegional,
              page,
            );
      setOrders(detail.orders);
      setMetrics(detail.metrics);
    } catch (reason) {
      setDetailError(
        reason instanceof Error
          ? reason.message
          : "Não foi possível abrir as O.S. deste dia.",
      );
      setOrders(EMPTY_PAGE);
      setMetrics(EMPTY_METRICS);
    } finally {
      setDetailLoading(false);
    }
  }

  async function loadMonthlyDetail(item: SelectedMonthly, page = 1) {
    setSelectedMonthly(item);
    setMonthlyLoading(true);
    setMonthlyError(null);
    try {
      setMonthlyDetail(
        await operationsApi.calendarMonthDetail(
          filters,
          item.regional,
          item.responsible,
          groupBy,
          item.referenceRegional,
          page,
        ),
      );
    } catch (reason) {
      setMonthlyError(
        reason instanceof Error
          ? reason.message
          : "Não foi possível abrir o total mensal deste colaborador.",
      );
      setMonthlyDetail(EMPTY_MONTHLY_DETAIL);
    } finally {
      setMonthlyLoading(false);
    }
  }

  useEffect(() => {
    setSelected(null);
    setOrders(EMPTY_PAGE);
    setMetrics(EMPTY_METRICS);
    setSelectedOrder(null);
    setSelectedMonthly(null);
    setMonthlyDetail(EMPTY_MONTHLY_DETAIL);
  }, [data.competence, filters]);

  useEffect(() => {
    setExpandedRegional(null);
  }, [data.competence, data.group_by]);

  const weekGroups = useMemo(
    () =>
      data.days.reduce<Array<{ week: number; count: number; dates: string[] }>>(
        (groups, day) => {
          const current = groups.at(-1);
          if (current?.week === day.week) {
            current.count += 1;
            current.dates.push(day.date);
          } else groups.push({ week: day.week, count: 1, dates: [day.date] });
          return groups;
        },
        [],
      ),
    [data.days],
  );
  const weekByNumber = useMemo(
    () => new Map(weekGroups.map((group) => [group.week, group])),
    [weekGroups],
  );
  const weekTotal = (
    dates: string[],
    counts: Record<string, number>,
  ) => dates.reduce((sum, dateKey) => sum + (counts[dateKey] || 0), 0);
  const availableWeekDates = (dates: string[]) =>
    dates.filter((dateKey) =>
      data.days.some((day) => day.date === dateKey && day.available),
    );
  const legendModels = useMemo(() => {
    const unique = new Map<number, OperationCalendarTeamModel>();
    data.regionals.forEach((regional) =>
      regional.collaborators.forEach((collaborator) => {
        if (collaborator.team_model)
          unique.set(collaborator.team_model.id, collaborator.team_model);
      }),
    );
    return Array.from(unique.values()).sort((left, right) =>
      left.name.localeCompare(right.name, "pt-BR"),
    );
  }, [data.regionals]);

  if (isLoading && !data.competence) return <CalendarSkeleton />;

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm sm:px-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex min-w-0 items-start gap-3">
            <Button
              type="button"
              size="icon"
              variant="outline"
              aria-label="Voltar para a visão geral"
              onClick={onBack}
              className="mt-0.5 shrink-0"
            >
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <div className="min-w-0">
              <p className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.16em] text-blue-600">
                <CalendarDays className="h-4 w-4" /> Operação mensal
              </p>
              <h2 className="mt-1 text-xl font-semibold capitalize text-slate-950">
                Calendário operacional · {competenceLabel(data.competence)}
              </h2>
              <p className="mt-1 text-xs text-slate-500">
                Produção diária por fechamento, modelo de equipe e meta
                operacional.
              </p>
            </div>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1.5">
            <div className="flex items-center gap-2">
              <span className="rounded-md border border-slate-100 bg-slate-50 px-2 py-1 text-[10px] font-semibold text-slate-400">
                Sem produção: 0
              </span>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-8 text-xs"
                disabled={exporting || isLoading || !data.regionals.length}
                onClick={() => void handleExport()}
              >
                {exporting ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <FileSpreadsheet className="h-3.5 w-3.5" />
                )}
                Exportar planilha
              </Button>
            </div>
            {exportError ? (
              <p className="max-w-52 text-right text-[10px] text-red-600">{exportError}</p>
            ) : null}
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3">
          <div>
            <p className="text-[9px] font-bold uppercase tracking-[0.14em] text-slate-400">
              Agrupamento do calendário
            </p>
            <p className="mt-0.5 text-xs text-slate-500">
              {groupBy === "regional"
                ? "Produção separada pela filial onde a O.S. foi atendida."
                : "Toda a produção do técnico, inclusive apoios entre filiais."}
            </p>
          </div>
          <div
            className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-1"
            role="group"
            aria-label="Agrupamento do calendário"
          >
            <Button
              type="button"
              size="sm"
              variant={groupBy === "regional" ? "default" : "ghost"}
              // `ghost` (estado inativo) não define cor de texto nem fundo próprio - achado real:
              // sem isso, "Por filial" ficava sem nenhuma affordance de botão ao lado do "Por
              // colaborador" azul, parecendo texto solto/quebrado. Só aplica o reforço quando
              // inativo, pra não sobrescrever o texto branco do estado selecionado (`default`).
              className={cn("h-8 text-xs", groupBy !== "regional" && "text-slate-600 hover:bg-white hover:text-slate-900")}
              onClick={() => onGroupByChange("regional")}
              aria-pressed={groupBy === "regional"}
            >
              Por filial
            </Button>
            <Button
              type="button"
              size="sm"
              variant={groupBy === "collaborator" ? "default" : "ghost"}
              className={cn("h-8 text-xs", groupBy !== "collaborator" && "text-slate-600 hover:bg-white hover:text-slate-900")}
              onClick={() => onGroupByChange("collaborator")}
              aria-pressed={groupBy === "collaborator"}
            >
              Por colaborador
            </Button>
          </div>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-8 text-xs"
            onClick={() => setLegendOpen((current) => !current)}
            aria-expanded={legendOpen}
          >
            {legendOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            {legendOpen ? "Ocultar legenda" : "Exibir legenda"}
          </Button>
        </div>
        {legendOpen && legendModels.length ? (
          <div
            className="mt-4 space-y-2 border-t border-slate-100 pt-3"
            aria-label="Legenda de desempenho por modelo de equipe"
          >
            <p className="text-[9px] font-bold uppercase tracking-[0.14em] text-slate-400">
              Cores e faixas configuradas por modelo
            </p>
            <div className="flex flex-wrap gap-2">
              {legendModels.map((model) => {
                const saturday = ruleFor(model, "saturday");
                const sunday = ruleFor(model, "sunday");
                const monthly = ruleFor(model, "monthly");
                return (
                  <div
                    key={model.id}
                    className="flex flex-wrap items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 p-1.5 text-[9px] font-semibold"
                  >
                    <span className="px-1 text-slate-700">{model.name}</span>
                    {modelLegend(model).map((band) => (
                      <span
                        key={band.key}
                        className="rounded border border-black/10 px-1.5 py-1 text-slate-800"
                        style={{ backgroundColor: band.color }}
                      >
                        {band.label}
                      </span>
                    ))}
                    <span className="px-1 text-slate-500">
                      Sáb.{" "}
                      {saturday?.enabled
                        ? saturday.target_quantity
                        : "sem meta"}{" "}
                      · Dom.{" "}
                      {sunday?.enabled ? sunday.target_quantity : "sem meta"} ·
                      Mês{" "}
                      {monthly?.enabled ? monthly.target_quantity : "sem meta"}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        ) : legendOpen ? (
          <p className="mt-3 border-t border-slate-100 pt-3 text-xs text-slate-500">
            Nenhum modelo de equipe vinculado aos colaboradores deste recorte.
          </p>
        ) : null}
        {legendOpen && canJustifyManagement ? (
          <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-slate-100 pt-3" aria-label="Legenda de status de justificativa">
            <p className="text-[9px] font-bold uppercase tracking-[0.14em] text-slate-400">Bolinha no dia = status na Gestão Integrada</p>
            <span className="flex items-center gap-1 text-[9px] font-semibold text-slate-600">
              <span className="h-2 w-2 rounded-full bg-white ring-2 ring-red-500" />
              Abaixo da meta, ainda sem caso aberto
            </span>
            {Object.entries(DAILY_CASE_STATUS_LABEL).map(([status, label]) => (
              <span key={status} className="flex items-center gap-1 text-[9px] font-semibold text-slate-600">
                <span className={cn("h-2 w-2 rounded-full", DAILY_CASE_STATUS_DOT[status])} />
                {label}
              </span>
            ))}
          </div>
        ) : null}
      </section>

      <OperationsCapacitySummaryCards filters={filters} />

      {isLoading ? <CalendarSkeleton /> : null}

      {!isLoading && data.regionals.length
        ? data.regionals.map((regional) => (
            <Card
              key={regional.regional}
              className="overflow-hidden rounded-xl border-slate-300 bg-white shadow-sm"
            >
              <CardHeader className="border-b border-slate-100 border-l-4 border-l-uni-royal bg-white p-0">
                <button
                  type="button"
                  aria-expanded={expandedRegional === regional.regional}
                  aria-controls={`calendar-regional-${encodeURIComponent(regional.regional)}`}
                  onClick={() =>
                    setExpandedRegional((current) =>
                      current === regional.regional ? null : regional.regional,
                    )
                  }
                  className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left transition hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-uni-royal"
                >
                  <div className="min-w-0">
                    <CardTitle className="truncate text-xs font-bold uppercase tracking-[0.08em] text-slate-950">
                      {groupBy === "regional"
                        ? regional.regional
                        : "Produção consolidada por colaborador"}
                    </CardTitle>
                    <p className="mt-0.5 text-[10px] text-slate-500">
                      {regional.collaborators.length} colaborador(es) na
                      competência
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Badge className="border-uni-royal/20 bg-uni-royal/10 text-uni-royal">
                      {regional.total} O.S.
                    </Badge>
                    {expandedRegional === regional.regional ? (
                      <ChevronDown className="h-4 w-4 text-slate-400" />
                    ) : (
                      <ChevronRight className="h-4 w-4 text-slate-400" />
                    )}
                  </div>
                </button>
              </CardHeader>
              {expandedRegional === regional.regional ? (
                <CardContent
                  id={`calendar-regional-${encodeURIComponent(regional.regional)}`}
                  // `max-h` + `overflow-y-auto` são o que faz o cabeçalho (`sticky top-0` na
                  // `<thead>` abaixo) realmente grudar durante a rolagem - achado real: sem uma
                  // altura limitada aqui, este container nunca chega a rolar de verdade (fica do
                  // tamanho exato do conteúdo, quem rola é a página inteira), e um `sticky` sem
                  // viewport própria não gruda em lugar nenhum - só "parece" sticky no CSS, mas
                  // na prática o cabeçalho sobe junto com o resto ao rolar a página.
                  className="max-h-[70vh] overflow-x-auto overflow-y-auto p-0"
                >
                  <table
                    className="w-full min-w-[1120px] table-fixed border-collapse text-[9px]"
                    aria-label={
                      groupBy === "regional"
                        ? `Calendário operacional da regional ${regional.regional}`
                        : "Calendário operacional consolidado por colaborador"
                    }
                  >
                    <thead className="sticky top-0 z-20 shadow-sm">
                      <tr className="bg-slate-950 text-slate-300">
                        <th
                          rowSpan={3}
                          scope="col"
                          className="sticky left-0 z-30 w-48 border-r border-slate-600 bg-slate-950 px-2 text-left uppercase tracking-wider"
                        >
                          {groupBy === "regional"
                            ? "Equipe / técnico"
                            : "Colaborador"}
                        </th>
                        {weekGroups.map((group) => (
                          <th
                            key={group.week}
                            scope="colgroup"
                            colSpan={group.count + 1}
                            className="border-r-2 border-slate-500 py-1.5 text-center tracking-[0.18em] text-slate-200"
                          >
                            SEM. {group.week}
                          </th>
                        ))}
                        <th
                          rowSpan={3}
                          scope="col"
                          className="sticky right-0 z-30 w-14 border-l-2 border-blue-500 bg-slate-950 text-center"
                        >
                          TOTAL
                          <br />
                          O.S.
                        </th>
                      </tr>
                      <tr className="bg-slate-900 text-slate-200">
                        {data.days.map((day, index) => (
                          <Fragment key={day.date}>
                            <th
                              scope="col"
                              className={cn(
                                "h-7 border-r border-slate-700 p-0 text-center tabular-nums",
                                day.weekday >= 5 && "bg-slate-800",
                              )}
                            >
                              <button
                                type="button"
                                className="flex h-full w-full items-center justify-center font-bold text-slate-300 transition hover:bg-cyan-500/15 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-cyan-400"
                                title={`Abrir total de ${shortDate(day.date)}`}
                                onClick={() =>
                                  void loadCell({
                                    day: day.date,
                                    periodLabel: shortDate(day.date),
                                    regional: regional.regional,
                                    responsible: ALL_RESPONSIBLES,
                                    quantity:
                                      regional.daily_counts[day.date] || 0,
                                    performance: "neutral",
                                    teamModel: null,
                                    referenceRegional: null,
                                  })
                                }
                              >
                                {day.day}
                              </button>
                            </th>
                            {data.days[index + 1]?.week !== day.week ? (
                              <th
                                scope="col"
                                className="h-7 border-r-2 border-slate-500 bg-slate-800 text-center text-[8px] font-bold text-slate-200"
                              >
                                TOT
                              </th>
                            ) : null}
                          </Fragment>
                        ))}
                      </tr>
                      <tr className="bg-slate-900 text-[8px] text-slate-500">
                        {data.days.map((day, index) => (
                          <Fragment key={day.date}>
                            <th
                              className={cn(
                                "h-5 border-r border-slate-700 p-0 text-center",
                                day.weekday >= 5 && "bg-slate-800",
                              )}
                            >
                              <button
                                type="button"
                                className="flex h-full w-full items-center justify-center text-[8px] font-bold text-slate-500 transition hover:bg-cyan-500/10 hover:text-cyan-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-cyan-400"
                                title={`Abrir total de ${shortDate(day.date)}`}
                                onClick={() =>
                                  void loadCell({
                                    day: day.date,
                                    periodLabel: shortDate(day.date),
                                    regional: regional.regional,
                                    responsible: ALL_RESPONSIBLES,
                                    quantity:
                                      regional.daily_counts[day.date] || 0,
                                    performance: "neutral",
                                    teamModel: null,
                                    referenceRegional: null,
                                  })
                                }
                              >
                                {WEEKDAYS[day.weekday]}
                              </button>
                            </th>
                            {data.days[index + 1]?.week !== day.week ? (
                              <th className="border-r-2 border-slate-500 bg-slate-800 text-center text-[8px] text-slate-400">
                                Σ
                              </th>
                            ) : null}
                          </Fragment>
                        ))}
                      </tr>
                      <tr className="border-b border-slate-200 bg-slate-100 font-semibold text-slate-600">
                        <th
                          scope="row"
                          className="sticky left-0 z-20 border-r bg-slate-100 px-3 py-2 text-left uppercase"
                        >
                          {groupBy === "regional"
                            ? "Total da regional"
                            : "Total dos colaboradores"}
                        </th>
                        {data.days.map((day, index) => (
                          <Fragment key={day.date}>
                            <th className="border-r p-0 text-center tabular-nums">
                              <button
                                type="button"
                                className="flex h-8 w-full items-center justify-center font-bold text-slate-700 transition hover:bg-blue-50 hover:text-blue-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500"
                                title={`Abrir total de ${shortDate(day.date)}`}
                                onClick={() =>
                                  void loadCell({
                                    day: day.date,
                                    periodLabel: shortDate(day.date),
                                    regional: regional.regional,
                                    responsible: ALL_RESPONSIBLES,
                                    quantity:
                                      regional.daily_counts[day.date] || 0,
                                    performance: "neutral",
                                    teamModel: null,
                                    referenceRegional: null,
                                  })
                                }
                              >
                                {regional.daily_counts[day.date] || "—"}
                              </button>
                            </th>
                            {data.days[index + 1]?.week !== day.week ? (
                              <th className="border-r-2 border-slate-300 bg-slate-100 p-0 text-center font-bold tabular-nums">
                                {(() => {
                                  const group = weekByNumber.get(day.week);
                                  const dates = group
                                    ? availableWeekDates(group.dates)
                                    : [];
                                  const total = weekTotal(
                                    dates,
                                    regional.daily_counts,
                                  );
                                  return (
                                    <button
                                      type="button"
                                      className="flex h-8 w-full items-center justify-center text-slate-700 transition hover:bg-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500"
                                      title={`Abrir total da semana ${day.week}`}
                                      onClick={() =>
                                        dates.length &&
                                        void loadCell({
                                          day: dates[0],
                                          periodEnd:
                                            dates[dates.length - 1],
                                          periodLabel:
                                            dates.length === group?.dates.length
                                              ? `Semana ${day.week}`
                                              : `Semana ${day.week} até o momento`,
                                          regional: regional.regional,
                                          responsible: ALL_RESPONSIBLES,
                                          quantity: total,
                                          performance: "neutral",
                                          teamModel: null,
                                          referenceRegional: null,
                                        })
                                      }
                                    >
                                      {total || "—"}
                                    </button>
                                  );
                                })()}
                              </th>
                            ) : null}
                          </Fragment>
                        ))}
                        <th className="sticky right-0 z-20 border-l-2 border-blue-500 bg-slate-100 text-center text-slate-950">
                          {regional.total}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {regional.collaborators.map((collaborator) => (
                        <tr
                          key={`${regional.regional}-${collaborator.responsible}`}
                          className="group border-b border-slate-100 bg-white hover:bg-slate-50/70"
                        >
                          <th
                            scope="row"
                            className="sticky left-0 z-10 h-12 border-r border-slate-200 bg-inherit px-2 text-left"
                          >
                            <p
                              className="max-w-44 truncate font-bold uppercase text-slate-900"
                              title={collaborator.responsible}
                            >
                              {collaborator.responsible}
                            </p>
                            <p
                              className="mt-0.5 max-w-44 truncate text-[8px] font-semibold uppercase tracking-wide text-slate-400"
                              title={collaborator.team_model?.name}
                            >
                              {collaborator.team_model
                                ? `${collaborator.team_model.name} · META ${ruleFor(collaborator.team_model, "weekday")?.target_quantity ?? collaborator.team_model.daily_target}/DIA`
                                : "SEM MODELO DE EQUIPE"}
                            </p>
                          </th>
                          {data.days.map((day, index) => {
                            const quantity =
                              collaborator.daily_counts[day.date] || 0;
                            const performance =
                              collaborator.daily_performance[day.date] ||
                              "neutral";
                            const label = performanceLabel(
                              performance,
                              quantity,
                              collaborator.team_model,
                            );
                            const backgroundColor = customBackground(
                              performance,
                              collaborator.team_model,
                            );
                            const target = dayTarget(
                              collaborator.team_model,
                              day.weekday,
                            );
                            const cell: SelectedCell = {
                              day: day.date,
                              regional: regional.regional,
                              responsible: collaborator.responsible,
                              quantity,
                              performance,
                              teamModel: collaborator.team_model,
                              referenceRegional:
                                collaborator.reference_regional,
                            };
                            const dailyCaseStatus = dailyCaseStatusByKey.get(dailyCaseKey(collaborator.responsible, day.date));
                            return (
                              <Fragment key={day.date}>
                                <td
                                  className={cn(
                                    "relative h-12 border-r border-slate-100 p-0 text-center",
                                    day.weekday >= 5 && "bg-slate-50/60",
                                    !day.available && "bg-slate-100/70",
                                  )}
                                >
                                  {day.available ? (
                                    <button
                                      type="button"
                                      style={
                                        backgroundColor
                                          ? { backgroundColor }
                                          : undefined
                                      }
                                      className={cn(
                                        "flex h-full min-h-12 w-full items-center justify-center rounded-none border-0 font-bold tabular-nums transition hover:brightness-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-600",
                                        performanceClass(
                                          performance,
                                          quantity,
                                          collaborator.team_model,
                                        ),
                                      )}
                                      aria-label={`${quantity} O.S. de ${collaborator.responsible} em ${shortDate(day.date)}. ${label}.`}
                                      title={`${label} · ${quantity} O.S.${target ? ` · meta ${target.target_quantity}` : " · sem meta neste dia"}${dailyCaseStatus ? ` · ${DAILY_CASE_STATUS_LABEL[dailyCaseStatus] ?? dailyCaseStatus}` : ""}`}
                                      onClick={() => void loadCell(cell)}
                                    >
                                      {quantity || "·"}
                                    </button>
                                  ) : (
                                    <span className="text-slate-300">—</span>
                                  )}
                                  {dailyCaseStatus ? (
                                    <span
                                      className={cn(
                                        "pointer-events-none absolute right-1 top-1 h-2 w-2 rounded-full ring-1 ring-white",
                                        DAILY_CASE_STATUS_DOT[dailyCaseStatus] ?? "bg-slate-400",
                                      )}
                                      aria-hidden="true"
                                      title={DAILY_CASE_STATUS_LABEL[dailyCaseStatus] ?? dailyCaseStatus}
                                    />
                                  ) : canJustifyManagement && performance === "below" ? (
                                    // Distingue "abaixo da meta e ninguem verificou ainda" de "ja
                                    // tem caso aberto" (bolinha colorida acima) - sem isso, os dois
                                    // casos pareciam iguais (nenhum marcador), escondendo o que
                                    // realmente falta tratar (achado real, 2026-08-14).
                                    <span
                                      className="pointer-events-none absolute right-1 top-1 h-2 w-2 rounded-full bg-white ring-2 ring-red-500"
                                      aria-hidden="true"
                                      title="Abaixo da meta - ainda sem caso aberto na Gestão Integrada"
                                    />
                                  ) : null}
                                </td>
                                {data.days[index + 1]?.week !== day.week ? (
                                  <td className="h-12 border-r-2 border-slate-300 bg-slate-100 p-0 text-center font-bold tabular-nums text-slate-700">
                                    {(() => {
                                      const group = weekByNumber.get(day.week);
                                      const dates = group
                                        ? availableWeekDates(group.dates)
                                        : [];
                                      const total = weekTotal(
                                        dates,
                                        collaborator.daily_counts,
                                      );
                                      return (
                                        <button
                                          type="button"
                                          className="flex h-full w-full items-center justify-center transition hover:bg-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500"
                                          title={`Abrir semana ${day.week} de ${collaborator.responsible}`}
                                          onClick={() =>
                                            dates.length &&
                                            void loadCell({
                                              day: dates[0],
                                              periodEnd:
                                                dates[dates.length - 1],
                                              periodLabel:
                                                dates.length ===
                                                group?.dates.length
                                                  ? `Semana ${day.week}`
                                                  : `Semana ${day.week} até o momento`,
                                              regional: regional.regional,
                                              responsible:
                                                collaborator.responsible,
                                              quantity: total,
                                              performance: "neutral",
                                              teamModel:
                                                collaborator.team_model,
                                              referenceRegional:
                                                collaborator.reference_regional,
                                            })
                                          }
                                        >
                                          {total || "—"}
                                        </button>
                                      );
                                    })()}
                                  </td>
                                ) : null}
                              </Fragment>
                            );
                          })}
                          <td
                            className="sticky right-0 z-10 border-l-2 border-blue-500 p-1 text-center tabular-nums"
                            style={
                              customBackground(
                                collaborator.monthly_performance,
                                collaborator.team_model,
                              )
                                ? {
                                    backgroundColor: customBackground(
                                      collaborator.monthly_performance,
                                      collaborator.team_model,
                                    ),
                                  }
                                : undefined
                            }
                          >
                            <button
                              type="button"
                              onClick={() =>
                                void loadMonthlyDetail({
                                  regional: regional.regional,
                                  responsible: collaborator.responsible,
                                  quantity: collaborator.total,
                                  performance:
                                    collaborator.monthly_performance,
                                  teamModel: collaborator.team_model,
                                  referenceRegional:
                                    collaborator.reference_regional,
                                })
                              }
                              className="w-full rounded-md px-1 py-2 text-sm font-bold text-blue-950 transition hover:bg-white/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
                              aria-label={`Abrir total mensal de ${collaborator.responsible}: ${collaborator.total} O.S.`}
                              title={`${performanceLabel(collaborator.monthly_performance, collaborator.total, collaborator.team_model)} · abrir detalhe mensal`}
                            >
                              {collaborator.total}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </CardContent>
              ) : null}
            </Card>
          ))
        : null}

      {!isLoading && !data.regionals.length ? (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center shadow-sm">
          <CalendarDays className="mx-auto h-9 w-9 text-slate-300" />
          <h3 className="mt-3 font-semibold text-slate-800">
            Nenhuma produção nesta competência
          </h3>
          <p className="mt-1 text-sm text-slate-500">
            Ajuste os filtros ou atualize a base IXC para visualizar O.S.
            finalizadas.
          </p>
        </div>
      ) : null}

      <Sheet
        open={Boolean(selected)}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
      >
        <SheetContent className="sm:max-w-2xl">
          <SheetHeader className="bg-slate-950 text-white">
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-cyan-300">
              {selected?.periodEnd && selected.periodEnd !== selected.day
                ? "Detalhe operacional semanal"
                : "Detalhe operacional diário"}
            </p>
            <SheetTitle className="text-white">
              {selected?.responsible === ALL_RESPONSIBLES
                ? "Todos os colaboradores"
                : selected?.responsible || "O.S. finalizadas"}
            </SheetTitle>
            <SheetDescription className="text-slate-400">
              {selected?.periodLabel
                ? selected.periodLabel
                : selected?.teamModel
                ? `${selected.teamModel.name} · META ${selected ? (dayTarget(selected.teamModel, new Date(`${selected.day}T12:00:00Z`).getUTCDay() === 0 ? 6 : new Date(`${selected.day}T12:00:00Z`).getUTCDay() - 1)?.target_quantity ?? "SEM META") : "—"}/DIA`
                : "SEM MODELO DE EQUIPE"}
            </SheetDescription>
          </SheetHeader>
          {selected ? (
            <div className="grid grid-cols-2 gap-2 border-b bg-white p-3 text-xs sm:grid-cols-4 sm:p-4">
              <div className="rounded-lg border bg-slate-50 p-2">
                <MapPin className="mb-1 h-3.5 w-3.5 text-slate-400" />
                <p className="text-[9px] uppercase text-slate-400">Regional</p>
                <p
                  className="break-words font-semibold text-slate-800"
                  title={selected.regional}
                >
                  {selected.regional}
                </p>
              </div>
              <div className="rounded-lg border bg-slate-50 p-2">
                <CalendarDays className="mb-1 h-3.5 w-3.5 text-slate-400" />
                <p className="text-[9px] uppercase text-slate-400">Data</p>
                <p className="font-semibold capitalize text-slate-800">
                  {selected.periodEnd && selected.periodEnd !== selected.day
                    ? `${shortDate(selected.day)} até ${shortDate(selected.periodEnd)}`
                    : shortDate(selected.day)}
                </p>
              </div>
              <div className="rounded-lg border bg-slate-50 p-2">
                <ClipboardList className="mb-1 h-3.5 w-3.5 text-slate-400" />
                <p className="text-[9px] uppercase text-slate-400">
                  Quantidade
                </p>
                <p className="font-semibold text-slate-800">
                  {selected.quantity} O.S.
                </p>
              </div>
              <div
                style={
                  customBackground(selected.performance, selected.teamModel)
                    ? {
                        backgroundColor: customBackground(
                          selected.performance,
                          selected.teamModel,
                        ),
                      }
                    : undefined
                }
                className={cn(
                  "rounded-lg border p-2",
                  performanceClass(
                    selected.performance,
                    selected.quantity,
                    selected.teamModel,
                  ),
                )}
              >
                <Target className="mb-1 h-3.5 w-3.5" />
                <p className="text-[9px] uppercase opacity-70">Desempenho</p>
                <p className="font-semibold">
                  {performanceLabel(
                    selected.performance,
                    selected.quantity,
                    selected.teamModel,
                  )}
                </p>
              </div>
            </div>
          ) : null}
          {selected &&
          selected.performance === "below" &&
          selected.responsible !== ALL_RESPONSIBLES &&
          (!selected.periodEnd || selected.periodEnd === selected.day) &&
          canJustifyManagement ? (
            <div className="flex flex-col gap-2 border-b border-red-100 bg-red-50/60 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between sm:px-4">
              <p className="text-xs text-red-800">
                Dia abaixo da meta - registre uma justificativa na Gestão Integrada.
              </p>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-8 shrink-0 border-red-300 bg-white text-xs text-red-700 hover:bg-red-100"
                disabled={openingCase}
                onClick={() => void openDailyJustification(selected)}
              >
                {openingCase ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <ShieldAlert className="h-3.5 w-3.5" />
                )}
                Justificar dia
              </Button>
            </div>
          ) : null}
          {openCaseError ? (
            <p className="border-b border-red-100 bg-red-50 px-3 py-2 text-xs text-red-700 sm:px-4">{openCaseError}</p>
          ) : null}
          {!detailLoading && !detailError && selected ? (
            <OperationsCalendarDayMetricsPanel metrics={metrics} />
          ) : null}
          <div className="flex-1 overflow-y-auto bg-slate-50 p-2.5 sm:p-4">
            {detailLoading ? (
              <div
                className="space-y-2"
                aria-label="Carregando O.S."
                aria-busy="true"
              >
                {[0, 1, 2].map((item) => (
                  <div
                    key={item}
                    className="h-32 animate-pulse rounded-xl border bg-white"
                  />
                ))}
              </div>
            ) : null}
            {detailError ? (
              <div
                role="alert"
                className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"
              >
                {detailError}
              </div>
            ) : null}
            {!detailLoading && !detailError ? (
              <div className="space-y-2">
                {orders.items.map((order) => (
                  <button
                    key={order.id}
                    type="button"
                    onClick={() => setSelectedOrder(order)}
                    className="block w-full rounded-xl border border-slate-200 bg-white p-3 text-left shadow-sm transition hover:border-blue-300 hover:shadow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 sm:p-4"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2 sm:gap-3">
                      <div className="min-w-0 flex-1 basis-52">
                        <p className="break-words font-semibold text-slate-950">
                          O.S. {order.order_code}
                        </p>
                        <p className="break-words text-xs text-slate-500">
                          {order.customer_name || "Cliente não identificado"} ·
                          Contrato {order.contract_id || "—"}
                        </p>
                      </div>
                      {order.status ? (
                        <Badge className="shrink-0 border-slate-200 bg-slate-50 text-slate-700">
                          {order.status}
                        </Badge>
                      ) : null}
                    </div>
                    <div className="mt-3 grid grid-cols-1 gap-x-4 gap-y-3 text-xs min-[420px]:grid-cols-2 sm:grid-cols-3">
                      <div>
                        <span className="text-slate-400">Tipo</span>
                        <p className="font-medium text-slate-700">
                          {order.os_type || "—"}
                        </p>
                      </div>
                      <div>
                        <span className="text-slate-400">Assunto</span>
                        <p className="break-words font-medium text-slate-700">
                          {order.os_subject || "—"}
                        </p>
                      </div>
                      <div>
                        <span className="text-slate-400">Filial / cidade</span>
                        <p className="font-medium text-slate-700">
                          {order.regional || "—"} · {order.city || "—"}
                        </p>
                      </div>
                      <div>
                        <span className="text-slate-400">Fechamento</span>
                        <p className="font-medium text-slate-700">
                          {dateTime(order.closed_at)}
                        </p>
                      </div>
                      <div>
                        <span className="text-slate-400">Agendamento</span>
                        <p className="font-medium text-slate-700">
                          {dateTime(order.scheduled_at)}
                        </p>
                      </div>
                      <div className="min-[420px]:col-span-2 sm:col-span-3">
                        <span className="text-slate-400">Endereço</span>
                        <p className="break-words font-medium text-slate-700">
                          {order.service_address || "Não informado"}
                        </p>
                      </div>
                    </div>
                    {order.normalization_notes ? (
                      <div className="mt-3 rounded-lg border border-amber-100 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                        <p className="font-semibold">
                          Observações operacionais
                        </p>
                        <p className="mt-0.5 whitespace-pre-wrap">
                          {order.normalization_notes}
                        </p>
                      </div>
                    ) : null}
                    <p className="mt-3 text-[10px] font-semibold uppercase tracking-wide text-blue-600">
                      Clique para abrir o detalhamento completo da O.S.
                    </p>
                  </button>
                ))}
                {!orders.items.length ? (
                  <div className="py-14 text-center">
                    <UserRound className="mx-auto h-8 w-8 text-slate-300" />
                    <p className="mt-2 text-sm font-medium text-slate-700">
                      Nenhuma O.S. neste dia
                    </p>
                    <p className="text-xs text-slate-500">
                      A célula registra ausência de produção no recorte atual.
                    </p>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
          {orders.total_pages > 1 ? (
            <div className="flex items-center justify-between border-t bg-white px-5 py-3 text-xs text-slate-500">
              <span>
                Página {orders.page} de {orders.total_pages}
              </span>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={orders.page <= 1 || detailLoading || !selected}
                  onClick={() =>
                    selected && void loadCell(selected, orders.page - 1)
                  }
                >
                  Anterior
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={
                    orders.page >= orders.total_pages ||
                    detailLoading ||
                    !selected
                  }
                  onClick={() =>
                    selected && void loadCell(selected, orders.page + 1)
                  }
                >
                  Próxima
                </Button>
              </div>
            </div>
          ) : null}
        </SheetContent>
      </Sheet>
      <Sheet
        open={Boolean(selectedMonthly)}
        onOpenChange={(open) => {
          if (!open) setSelectedMonthly(null);
        }}
      >
        <SheetContent className="sm:max-w-2xl">
          <SheetHeader className="bg-slate-950 text-white">
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-cyan-300">
              Detalhe operacional mensal
            </p>
            <SheetTitle className="text-white">
              {selectedMonthly?.responsible || "Colaborador"}
            </SheetTitle>
            <SheetDescription className="text-slate-400">
              {selectedMonthly?.teamModel
                ? `${selectedMonthly.teamModel.name} · META MENSAL ${ruleFor(selectedMonthly.teamModel, "monthly")?.target_quantity ?? "NÃO CONFIGURADA"}`
                : "Sem modelo de equipe"}{" "}
              · {competenceLabel(data.competence)}
            </SheetDescription>
          </SheetHeader>
          {monthlyLoading ? (
            <div
              className="space-y-3 p-4"
              aria-label="Carregando total mensal"
              aria-busy="true"
            >
              {[0, 1, 2].map((item) => (
                <div
                  key={item}
                  className="h-20 animate-pulse rounded-xl border bg-slate-100"
                />
              ))}
            </div>
          ) : null}
          {monthlyError ? (
            <div
              role="alert"
              className="m-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"
            >
              {monthlyError}
            </div>
          ) : null}
          {!monthlyLoading && !monthlyError && selectedMonthly ? (
            <>
              <div className="grid grid-cols-2 gap-2 border-b bg-white p-3 text-xs sm:grid-cols-4 sm:p-4">
                <div className="rounded-lg border bg-slate-50 p-2">
                  <MapPin className="mb-1 h-3.5 w-3.5 text-slate-400" />
                  <p className="text-[9px] uppercase text-slate-400">
                    Regional
                  </p>
                  <p
                    className="break-words font-semibold text-slate-800"
                    title={selectedMonthly.regional}
                  >
                    {selectedMonthly.regional}
                  </p>
                </div>
                <div className="rounded-lg border bg-slate-50 p-2">
                  <CalendarDays className="mb-1 h-3.5 w-3.5 text-slate-400" />
                  <p className="text-[9px] uppercase text-slate-400">
                    Competência
                  </p>
                  <p className="font-semibold capitalize text-slate-800">
                    {competenceLabel(data.competence)}
                  </p>
                </div>
                <div className="rounded-lg border bg-slate-50 p-2">
                  <ClipboardList className="mb-1 h-3.5 w-3.5 text-slate-400" />
                  <p className="text-[9px] uppercase text-slate-400">
                    Quantidade
                  </p>
                  <p className="font-semibold text-slate-800">
                    {monthlyDetail.metrics.total_orders} O.S.
                  </p>
                </div>
                <div
                  style={
                    customBackground(
                      selectedMonthly.performance,
                      selectedMonthly.teamModel,
                    )
                      ? {
                          backgroundColor: customBackground(
                            selectedMonthly.performance,
                            selectedMonthly.teamModel,
                          ),
                        }
                      : undefined
                  }
                  className={cn(
                    "rounded-lg border p-2",
                    performanceClass(
                      selectedMonthly.performance,
                      selectedMonthly.quantity,
                      selectedMonthly.teamModel,
                    ),
                  )}
                >
                  <Target className="mb-1 h-3.5 w-3.5" />
                  <p className="text-[9px] uppercase opacity-70">Desempenho</p>
                  <p className="font-semibold">
                    {performanceLabel(
                      selectedMonthly.performance,
                      selectedMonthly.quantity,
                      selectedMonthly.teamModel,
                    )}
                  </p>
                </div>
              </div>
              <OperationsCalendarDayMetricsPanel metrics={monthlyPanelMetrics} />
              <div className="flex-1 overflow-y-auto bg-slate-50 p-3 sm:p-4">
                <p className="mb-3 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">
                  O.S. finalizadas na competência
                </p>
                <div className="space-y-2">
                  {monthlyDetail.orders.items.map((order) => (
                    <button
                      key={order.id}
                      type="button"
                      onClick={() => setSelectedOrder(order)}
                      className="block w-full rounded-xl border border-slate-200 bg-white p-3 text-left shadow-sm transition hover:border-blue-300 hover:shadow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-2 sm:gap-3">
                        <div className="min-w-0 flex-1 basis-52">
                          <p className="break-words font-semibold text-slate-950">
                            O.S. {order.order_code}
                          </p>
                          <p className="break-words text-xs text-slate-500">
                            {order.customer_name || "Cliente não identificado"} ·
                            Contrato {order.contract_id || "—"}
                          </p>
                        </div>
                        {order.status ? (
                          <Badge className="shrink-0 border-slate-200 bg-slate-50 text-slate-700">
                            {order.status}
                          </Badge>
                        ) : null}
                      </div>
                      <div className="mt-3 grid grid-cols-1 gap-x-4 gap-y-3 text-xs min-[420px]:grid-cols-2 sm:grid-cols-3">
                        <div>
                          <span className="text-slate-400">Tipo</span>
                          <p className="font-medium text-slate-700">
                            {order.os_type || "—"}
                          </p>
                        </div>
                        <div>
                          <span className="text-slate-400">Assunto</span>
                          <p className="break-words font-medium text-slate-700">
                            {order.os_subject || "—"}
                          </p>
                        </div>
                        <div>
                          <span className="text-slate-400">Filial / cidade</span>
                          <p className="font-medium text-slate-700">
                            {order.regional || "—"} · {order.city || "—"}
                          </p>
                        </div>
                        <div>
                          <span className="text-slate-400">Fechamento</span>
                          <p className="font-medium text-slate-700">
                            {dateTime(order.closed_at)}
                          </p>
                        </div>
                        <div>
                          <span className="text-slate-400">Agendamento</span>
                          <p className="font-medium text-slate-700">
                            {dateTime(order.scheduled_at)}
                          </p>
                        </div>
                        <div className="min-[420px]:col-span-2 sm:col-span-3">
                          <span className="text-slate-400">Endereço</span>
                          <p className="break-words font-medium text-slate-700">
                            {order.service_address || "Não informado"}
                          </p>
                        </div>
                      </div>
                      <p className="mt-2 text-[10px] font-semibold uppercase tracking-wide text-blue-600">
                        Clique para abrir o detalhamento completo da O.S.
                      </p>
                    </button>
                  ))}
                  {!monthlyDetail.orders.items.length ? (
                    <p className="py-12 text-center text-sm text-slate-500">
                      Nenhuma O.S. finalizada nesta competência.
                    </p>
                  ) : null}
                </div>
              </div>
              {monthlyDetail.orders.total_pages > 1 ? (
                <div className="flex items-center justify-between border-t bg-white px-5 py-3 text-xs text-slate-500">
                  <span>
                    Página {monthlyDetail.orders.page} de{" "}
                    {monthlyDetail.orders.total_pages}
                  </span>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={
                        monthlyDetail.orders.page <= 1 ||
                        monthlyLoading ||
                        !selectedMonthly
                      }
                      onClick={() =>
                        selectedMonthly &&
                        void loadMonthlyDetail(
                          selectedMonthly,
                          monthlyDetail.orders.page - 1,
                        )
                      }
                    >
                      Anterior
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={
                        monthlyDetail.orders.page >=
                          monthlyDetail.orders.total_pages ||
                        monthlyLoading ||
                        !selectedMonthly
                      }
                      onClick={() =>
                        selectedMonthly &&
                        void loadMonthlyDetail(
                          selectedMonthly,
                          monthlyDetail.orders.page + 1,
                        )
                      }
                    >
                      Próxima
                    </Button>
                  </div>
                </div>
              ) : null}
            </>
          ) : null}
        </SheetContent>
      </Sheet>
      <OperationsOrderDetailDialog
        order={selectedOrder}
        onOpenChange={(open) => {
          if (!open) setSelectedOrder(null);
        }}
      />
      {dailyCaseId !== null ? (
        <CaseDetailDialog
          caseId={dailyCaseId}
          reasons={caseReasons}
          canJustify={canJustifyManagement}
          canReview={canReviewManagement}
          onClose={() => setDailyCaseId(null)}
          onChanged={() => void loadDailyCaseStatuses()}
        />
      ) : null}
    </div>
  );
}
