"use client";

import Link from "next/link";
import { Database, Home, Loader2, LogOut, Search, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { OperationsFilterPanel } from "@/components/operations/operations-filter-panel";
import { OperationsCollaboratorSlaTable } from "@/components/operations/operations-collaborator-sla-table";
import { OperationsControlTower } from "@/components/operations/operations-control-tower";
import { OperationsMonthlyCalendar } from "@/components/operations/operations-monthly-calendar";
import {
  OperationsModuleSidebar,
  type OperationTab,
} from "@/components/operations/operations-module-sidebar";
import { OperationsOpeningsAnalytics } from "@/components/operations/operations-openings-analytics";
import { OperationsOrderDetailDialog } from "@/components/operations/operations-order-detail-dialog";
import { OperationsOverviewCharts } from "@/components/operations/operations-overview-charts";
import { OperationsSlaHierarchyTable } from "@/components/operations/operations-sla-hierarchy-table";
import { OperationsTeamConfiguration } from "@/components/operations/operations-team-configuration";
import { OperationsWorkScheduleOverview } from "@/components/operations/operations-work-schedule-overview";
import { WorkspaceLogin } from "@/components/workspace/workspace-login";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent } from "@/components/ui/tabs";
import { useWorkspaceAuth } from "@/hooks/use-workspace-auth";
import {
  operationsApi,
  type OperationBreakdownItem,
  type OperationCalendar,
  type OperationCollaboratorSla,
  type OperationControlTower,
  type OperationControlTowerPath,
  type OperationDataFreshness,
  type OperationFilterState,
  type OperationFilters,
  type OperationIxcSyncSettings,
  type OperationOpeningsAnalytics,
  type OpeningsDrillField,
  type OpeningsDrillTarget,
  type OperationOrder,
  type OperationOrderPage,
  type OperationOverview,
  type OperationPeriod,
  type OperationSavedFilter,
  type OperationSavedFilterValues,
  type OperationSlaHierarchy,
  type OperationSlaRiskItem,
  type OperationTrendGranularity,
  type OperationTrendSeries,
  type OperationWorkScheduleOverview,
} from "@/lib/operations-api";

// Espelha PRIMARY_SECTOR_NAMES em backend/app/modules/operations/scope.py.
const DEFAULT_PRIORITY_SECTORS = [
  "Suporte Externo",
  "Suporte Externo Rádio",
  "Suporte Externo Fibra",
];

const EMPTY_FILTERS: OperationFilters = {
  team_models: [],
  companies: [],
  regionals: [],
  states: [],
  cities: [],
  contract_types: [],
  person_types: [],
  os_types: [],
  subjects: [],
  diagnoses: [],
  departments: [],
  sectors: [],
  priorities: [],
  creators: [],
  responsibles: [],
  statuses: [],
  sla_statuses: [],
  projects: [],
  pops: [],
  opened_weekdays: [],
  closed_weekdays: [],
};

const EMPTY_OVERVIEW: OperationOverview = {
  opened: 0,
  opened_associated: 0,
  responsible_filter_active: false,
  completed: 0,
  in_progress: 0,
  opened_out_of_time: 0,
  completed_on_time: 0,
  completed_out_of_time: 0,
  sla_rate: null,
  average_daily_opened: 0,
  average_daily_completed: 0,
  average_closing_hours: null,
  average_wait_to_displacement_minutes: null,
  average_cycle_minutes: null,
};

const EMPTY_TRENDS: OperationTrendSeries = {
  granularity: "day",
  responsible_filter_active: false,
  openings_ignore_responsibles: true,
  points: [],
};
const EMPTY_WORK_SCHEDULE: OperationWorkScheduleOverview = {
  completed: 0,
  classified: 0,
  outside_schedule: 0,
  before_start: 0,
  after_end: 0,
  unclassified: 0,
  outside_rate: null,
  selected_model_ids: [],
  available_models: [],
  by_model: [],
};
const EMPTY_CONTROL_TOWER: OperationControlTower = {
  reference_date: "",
  level: "subject",
  next_level: "regional",
  path: {},
  recent_days: 7,
  baseline_weeks: 8,
  timeline_days: 28,
  responsibles_ignored: true,
  calculation_note: "",
  summary: {
    status: "insufficient",
    opened_recent: 0,
    expected_opened: 0,
    deviation_percentage: null,
    completed_recent: 0,
    net_flow: 0,
    pressure_ratio: null,
    backlog: 0,
    overdue_backlog: 0,
    average_backlog_age_hours: null,
    persistent_days: 0,
    critical_nodes: 0,
    attention_nodes: 0,
    reasons: [],
  },
  timeline: [],
  items: [],
};

const EMPTY_OPENINGS_ANALYTICS: OperationOpeningsAnalytics = {
  date_from: "",
  date_to: "",
  baseline_weeks: 8,
  granularity: "day",
  calculation_note: "",
  summary: {
    opened: 0,
    completed: 0,
    net_flow: 0,
    pressure_ratio: null,
    average_daily_opened: 0,
    expected_opened: 0,
    deviation_percentage: null,
    backlog: 0,
    overdue_backlog: 0,
    without_responsible: 0,
    average_first_action_minutes: null,
  },
  timeline: [],
  heatmap: [],
  aging: [],
  rankings: {},
  insights: [],
};

const EMPTY_PAGE: OperationOrderPage = {
  items: [],
  total: 0,
  page: 1,
  page_size: 50,
  total_pages: 0,
};
const EMPTY_COLLABORATOR_SLA: OperationCollaboratorSla = {
  type_columns: [],
  items: [],
};
const EMPTY_CALENDAR: OperationCalendar = {
  competence: "",
  date_from: "",
  date_to: "",
  group_by: "regional",
  days: [],
  regionals: [],
};
const EMPTY_SLA_HIERARCHY: OperationSlaHierarchy = {
  level: "os_type",
  parent_os_type: null,
  parent_subject: null,
  items: [],
  total: {
    label: "Total ponderado",
    completed: 0,
    on_time: 0,
    out_of_time: 0,
    sla_rate: null,
    timed_orders: 0,
    up_to_12h_rate: null,
    from_12h_to_24h_rate: null,
    from_24h_to_48h_rate: null,
    from_48h_to_72h_rate: null,
    after_72h_rate: null,
    average_closing_hours: null,
  },
};
const CLOSED_OPERATION_STATUSES = new Set(["finalizada", "cancelada"]);
function filtersForOpenScope(current: OperationFilterState) {
  const statuses = (current.statuses || []).filter(
    (status) =>
      !CLOSED_OPERATION_STATUSES.has(status.trim().toLocaleLowerCase("pt-BR")),
  );
  return statuses.length === (current.statuses || []).length
    ? current
    : { ...current, statuses };
}

function datesInRange(dateFrom: string, dateTo: string) {
  const start = new Date(`${dateFrom}T00:00:00Z`);
  const end = new Date(`${dateTo}T00:00:00Z`);
  if (
    Number.isNaN(start.getTime()) ||
    Number.isNaN(end.getTime()) ||
    start > end
  )
    return [];
  const days: string[] = [];
  for (
    const current = new Date(start);
    current <= end;
    current.setUTCDate(current.getUTCDate() + 1)
  ) {
    days.push(current.toISOString().slice(0, 10));
  }
  return days;
}

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function configuredIxcSectorIds(settings: OperationIxcSyncSettings | null) {
  return settings?.sector_ids?.length ? settings.sector_ids : [];
}

function formatNumber(value: number | null, suffix = "") {
  if (value === null) return "—";
  return `${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 }).format(value)}${suffix}`;
}

function formatDurationMinutes(value: number | null) {
  if (value === null) return "—";
  const minutes = Math.round(value);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder ? `${hours}h ${remainder}min` : `${hours}h`;
}

function formatDate(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "America/Porto_Velho",
  }).format(new Date(value));
}

function slaLabel(value: string) {
  if (value === "on_time") return "No prazo";
  if (value === "out_of_time") return "Atrasada";
  return "Não identificado";
}

type DetailSortKey =
  | "order_code"
  | "customer"
  | "regional"
  | "type_subject"
  | "responsible"
  | "opened_at"
  | "closed_at"
  | "status"
  | "sla_status";

type ProgressDrillTarget =
  | { kind: "dimension"; field: "regionals" | "cities" | "os_types" | "subjects" | "statuses"; value: string; key: string }
  | { kind: "sla_risk"; bucket: string; label: string; key: string };

function orderField(order: OperationOrder, key: DetailSortKey) {
  if (key === "customer")
    return `${order.contract_id || ""} ${order.customer_name || ""}`;
  if (key === "type_subject")
    return `${order.os_type || ""} ${order.os_subject || ""}`;
  return String(order[key] || "");
}

function OverviewMetricCard({
  title,
  value,
  helper,
  note,
  tone = "neutral",
}: {
  title: string;
  value: string | number;
  helper: string;
  note?: string;
  tone?: "neutral" | "success" | "warning" | "danger";
}) {
  const toneClass = {
    neutral: "bg-white text-slate-950",
    success: "bg-emerald-50 text-emerald-950",
    warning: "bg-amber-50 text-amber-950",
    danger: "bg-red-50 text-red-950",
  }[tone];
  const accentClass = {
    neutral: "bg-blue-600",
    success: "bg-emerald-600",
    warning: "bg-amber-500",
    danger: "bg-red-600",
  }[tone];

  return (
    <div className={`relative overflow-hidden rounded-xl p-4 shadow-sm ${toneClass}`}>
      <span className={`absolute inset-x-0 top-0 h-1 ${accentClass}`} />
      <p className="text-xs font-medium text-slate-500">{title}</p>
      <p className="mt-2 text-3xl font-semibold tabular-nums">{value}</p>
      <p className="mt-2 text-xs text-slate-600">{helper}</p>
      {note ? <p className="mt-1 text-[11px] text-slate-500">{note}</p> : null}
    </div>
  );
}

function slaTone(rate: number | null) {
  if (rate === null) return "neutral";
  if (rate >= 80) return "success";
  if (rate >= 60) return "warning";
  return "danger";
}

function efficiencyInsight(overview: OperationOverview) {
  const wait = overview.average_wait_to_displacement_minutes;
  const cycle = overview.average_cycle_minutes;
  if (wait === null || cycle === null || cycle <= 0) return null;
  const percentage = (wait / cycle) * 100;
  if (percentage < 50) return null;
  return `Principal gargalo: ${formatNumber(percentage, "%")} do tempo médio da O.S. ocorre antes do deslocamento da equipe.`;
}

const BREAKDOWN_VISIBLE_DEFAULT = 6;

function BreakdownTable({
  title,
  items,
  activeLabel,
  onDrill,
}: {
  title: string;
  items: OperationBreakdownItem[];
  activeLabel?: string | null;
  onDrill: (label: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const sortedItems = useMemo(
    () => [...items].sort((left, right) => right.quantity - left.quantity),
    [items],
  );
  const visibleItems = expanded
    ? sortedItems
    : sortedItems.slice(0, BREAKDOWN_VISIBLE_DEFAULT);
  const hiddenCount = sortedItems.length - visibleItems.length;
  return (
    <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold text-slate-900">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-3 pt-0">
        {visibleItems.length ? (
          <div className="divide-y divide-slate-100">
            {visibleItems.map((item) => (
              <button
                key={item.label}
                type="button"
                onClick={() => onDrill(item.label)}
                className={`flex w-full items-center justify-between gap-3 py-2 text-left ${
                  activeLabel === item.label ? "rounded-lg bg-blue-50 px-2 ring-1 ring-inset ring-blue-300" : ""
                }`}
              >
                <span className="min-w-0 flex-1 truncate text-sm font-medium text-slate-800">
                  {item.label}
                </span>
                <span className="flex shrink-0 items-baseline gap-1.5">
                  <span className="text-sm font-semibold tabular-nums text-slate-900">
                    {item.quantity}
                  </span>
                  <span className="text-xs text-slate-500">
                    {formatNumber(item.percentage, "%")}
                  </span>
                </span>
              </button>
            ))}
          </div>
        ) : (
          <p className="py-6 text-center text-sm text-slate-500">
            Nenhuma O.S. em andamento.
          </p>
        )}
        {sortedItems.length > BREAKDOWN_VISIBLE_DEFAULT ? (
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

const PROGRESS_FIELD_LABELS: Record<string, string> = {
  regionals: "Filial",
  cities: "Cidade",
  os_types: "Tipo geral",
  subjects: "Assunto",
  statuses: "SLA / Status",
};

function progressDrillHeading(target: ProgressDrillTarget) {
  if (target.kind === "sla_risk") return { eyebrow: "SLA em risco", title: target.label };
  return { eyebrow: PROGRESS_FIELD_LABELS[target.field] || target.field, title: target.value };
}

function ProgressDrillPanel({
  target,
  orders,
  isLoading,
  onClose,
}: {
  target: ProgressDrillTarget;
  orders: OperationOrderPage;
  isLoading: boolean;
  onClose: () => void;
}) {
  const heading = progressDrillHeading(target);
  const items = orders.items;
  return (
    <Card className="mb-4 rounded-2xl border-blue-200 bg-blue-50/40 shadow-sm">
      <CardHeader className="flex-row items-center justify-between gap-4 pb-2">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-blue-600">
            {heading.eyebrow}
          </p>
          <CardTitle className="text-base font-semibold text-slate-950">
            {heading.title}
          </CardTitle>
          <p className="text-xs text-slate-500">
            {orders.total} O.S. no total
            {orders.total > items.length ? ` · mostrando as ${items.length} mais recentes` : ""}
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
                <TableHead>Filial / Cidade</TableHead>
                <TableHead>Assunto</TableHead>
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
                    <TableCell>
                      <p>{order.regional || "—"}</p>
                      <p className="text-xs text-slate-500">{order.city || "Cidade não identificada"}</p>
                    </TableCell>
                    <TableCell className="max-w-56 truncate">
                      <p>{order.os_type || "—"}</p>
                      <p className="text-xs text-slate-500">{order.os_subject || "—"}</p>
                    </TableCell>
                    <TableCell>{order.responsible || "Sem responsável"}</TableCell>
                    <TableCell>{new Date(order.opened_at).toLocaleString("pt-BR")}</TableCell>
                    <TableCell>{order.status || "—"}</TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={7} className="py-8 text-center text-sm text-slate-500">
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

export default function OperacaoPage() {
  const {
    user,
    checking,
    error: authError,
    login,
    logout,
  } = useWorkspaceAuth();
  const [period, setPeriod] = useState<OperationPeriod | null>(null);
  const [filters, setFilters] = useState<OperationFilterState | null>(null);
  const [filterOptions, setFilterOptions] =
    useState<OperationFilters>(EMPTY_FILTERS);
  const [savedFilters, setSavedFilters] = useState<OperationSavedFilter[]>([]);
  const [selectedSavedFilterId, setSelectedSavedFilterId] = useState<
    number | null
  >(null);
  const [filterName, setFilterName] = useState("");
  const [savedFilterVisibility, setSavedFilterVisibility] = useState<
    "personal" | "global"
  >("personal");
  const [overview, setOverview] = useState<OperationOverview>(EMPTY_OVERVIEW);
  const [workSchedule, setWorkSchedule] =
    useState<OperationWorkScheduleOverview>(EMPTY_WORK_SCHEDULE);
  const [workScheduleModelIds, setWorkScheduleModelIds] = useState<number[]>(
    [],
  );
  const [overviewTrends, setOverviewTrends] =
    useState<OperationTrendSeries>(EMPTY_TRENDS);
  const [controlTower, setControlTower] =
    useState<OperationControlTower>(EMPTY_CONTROL_TOWER);
  const [openingsAnalytics, setOpeningsAnalytics] =
    useState<OperationOpeningsAnalytics>(EMPTY_OPENINGS_ANALYTICS);
  const [openingsDrill, setOpeningsDrill] = useState<OpeningsDrillTarget | null>(null);
  const [openingsDrillOrders, setOpeningsDrillOrders] =
    useState<OperationOrderPage>(EMPTY_PAGE);
  const [openingsDrillLoading, setOpeningsDrillLoading] = useState(false);
  const [openingsGranularity, setOpeningsGranularity] =
    useState<OperationTrendGranularity>("day");
  const [openingsTemporaryPeriod, setOpeningsTemporaryPeriod] = useState<{
    label: string;
    date_from: string;
    date_to: string;
  } | null>(null);
  const [openingsTemporaryData, setOpeningsTemporaryData] =
    useState<OperationOpeningsAnalytics | null>(null);
  const [openingsTemporaryLoading, setOpeningsTemporaryLoading] = useState(false);
  const [trendGranularity, setTrendGranularity] =
    useState<OperationTrendGranularity>("day");
  const [dataFreshness, setDataFreshness] =
    useState<OperationDataFreshness | null>(null);
  const [ixcSyncSettings, setIxcSyncSettings] =
    useState<OperationIxcSyncSettings | null>(null);
  const [slaHierarchy, setSlaHierarchy] =
    useState<OperationSlaHierarchy>(EMPTY_SLA_HIERARCHY);
  const [collaboratorSla, setCollaboratorSla] =
    useState<OperationCollaboratorSla>(EMPTY_COLLABORATOR_SLA);
  const [calendar, setCalendar] = useState<OperationCalendar>(EMPTY_CALENDAR);
  const [calendarGroupBy, setCalendarGroupBy] = useState<
    "regional" | "collaborator"
  >("regional");
  const [appliedFilters, setAppliedFilters] =
    useState<OperationFilterState | null>(null);
  const [regionalBreakdown, setRegionalBreakdown] = useState<
    OperationBreakdownItem[]
  >([]);
  const [cityBreakdown, setCityBreakdown] = useState<OperationBreakdownItem[]>(
    [],
  );
  const [typeBreakdown, setTypeBreakdown] = useState<OperationBreakdownItem[]>(
    [],
  );
  const [subjectBreakdown, setSubjectBreakdown] = useState<
    OperationBreakdownItem[]
  >([]);
  const [statusBreakdown, setStatusBreakdown] = useState<
    OperationBreakdownItem[]
  >([]);
  const [slaRiskBreakdown, setSlaRiskBreakdown] = useState<
    OperationSlaRiskItem[]
  >([]);
  const [progressDrill, setProgressDrill] = useState<ProgressDrillTarget | null>(null);
  const [progressDrillOrders, setProgressDrillOrders] =
    useState<OperationOrderPage>(EMPTY_PAGE);
  const [progressDrillLoading, setProgressDrillLoading] = useState(false);
  const [orders, setOrders] = useState<OperationOrderPage>(EMPTY_PAGE);
  const [selectedOrder, setSelectedOrder] = useState<OperationOrder | null>(
    null,
  );
  const detailTableRef = useRef<HTMLDivElement>(null);
  const [detailSort, setDetailSort] = useState<{
    key: DetailSortKey;
    direction: "asc" | "desc";
  }>({ key: "opened_at", direction: "desc" });
  const [detailQuickFilter, setDetailQuickFilter] = useState<{
    key: DetailSortKey;
    value: string;
  } | null>(null);
  const [activeTab, setActiveTab] = useState<OperationTab>("overview");
  const [detailsScope, setDetailsScope] = useState<"period" | "openings">(
    "period",
  );
  const [loading, setLoading] = useState(false);
  const [overviewLoading, setOverviewLoading] = useState(false);
  const [overviewSecondaryLoading, setOverviewSecondaryLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importingBacklog, setImportingBacklog] = useState(false);
  const [importProgress, setImportProgress] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Retained for the explicit option refresh flow; ordinary edits never trigger it.
  const filterOptionsRequest = useRef(0);
  const dashboardRequest = useRef(0);

  const canRead = Boolean(user?.permissions.includes("operations:read"));
  const canManage = Boolean(user?.permissions.includes("operations:manage"));
  const canManageTeamModels = Boolean(
    user?.permissions.includes("operations:manage_team_models"),
  );
  const canManageSubjects = Boolean(
    user?.permissions.includes("operations:manage_subjects"),
  );
  const canSyncIxc = Boolean(user?.permissions.includes("operations:sync_ixc"));
  const canViewOpenings = Boolean(user?.permissions.includes("operations:view_openings"));
  const canViewSla = Boolean(user?.permissions.includes("operations:view_sla"));
  const canViewCalendar = Boolean(user?.permissions.includes("operations:view_calendar"));
  const canViewBacklog = Boolean(user?.permissions.includes("operations:view_backlog"));
  const canViewOrderDetails = Boolean(user?.permissions.includes("operations:view_order_details"));
  const canManageViews = Boolean(user?.permissions.includes("operations:manage_filters"));
  const canCreateGlobalViews = Boolean(
    user?.permissions.includes("operations:views:create_global"),
  );
  const visibleTabs = useMemo<OperationTab[]>(
    () => [
      "overview",
      ...(canViewOpenings ? ["openings" as const] : []),
      ...(canViewSla ? ["sla" as const] : []),
      ...(canViewCalendar ? ["calendar" as const] : []),
      ...(canViewBacklog ? ["progress" as const] : []),
      ...(canViewOrderDetails ? ["details" as const] : []),
      ...(canManageTeamModels || canManageSubjects || canSyncIxc ? ["teams" as const] : []),
    ],
    [canManageSubjects, canManageTeamModels, canSyncIxc, canViewBacklog, canViewCalendar, canViewOpenings, canViewOrderDetails, canViewSla],
  );

  const loadDashboard = useCallback(
    async (
      nextFilters: OperationFilterState,
      page = 1,
      requestedTab: OperationTab = activeTab,
      calendarGrouping = calendarGroupBy,
    ) => {
      const requestId = dashboardRequest.current + 1;
      dashboardRequest.current = requestId;
      setLoading(true);
      setError(null);
      try {
        const openScope = requestedTab === "progress";
        const effectiveFilters = openScope
          ? filtersForOpenScope(nextFilters)
          : nextFilters;
        const hasPeriod = Boolean(
          effectiveFilters.date_from && effectiveFilters.date_to,
        );
        if (effectiveFilters !== nextFilters) {
          setFilters(effectiveFilters);
          setMessage(
            "O filtro de status finalizado/cancelado foi removido porque a visão Andamento exibe somente O.S. abertas.",
          );
        }
        setAppliedFilters(effectiveFilters);

        if (requestedTab === "teams") return;

        if (!hasPeriod && !openScope) {
          const nextOptions = await operationsApi.filters(
            effectiveFilters,
            "in_progress",
          );
          if (dashboardRequest.current !== requestId) return;
          setFilterOptions(nextOptions);
          setError(
            "Informe a data inicial e a data final para consultar esta visão. Em Andamento, as datas podem ficar vazias.",
          );
          return;
        }

        if (requestedTab === "overview") {
          setOverviewLoading(true);
          const nextOverview = await operationsApi.overview(effectiveFilters);
          if (dashboardRequest.current !== requestId) return;
          setOverview(nextOverview);
          setOverviewLoading(false);
          setOverviewSecondaryLoading(true);
          void Promise.allSettled([
            operationsApi.overviewTrends(effectiveFilters, trendGranularity),
            operationsApi.controlTower(effectiveFilters),
            operationsApi.overviewWorkSchedule(
              effectiveFilters,
              workScheduleModelIds,
            ),
          ])
            .then((results) => {
              if (dashboardRequest.current !== requestId) return;
              const [trends, tower, schedule] = results;
              if (trends.status === "fulfilled") setOverviewTrends(trends.value);
              if (tower.status === "fulfilled") setControlTower(tower.value);
              if (schedule.status === "fulfilled") setWorkSchedule(schedule.value);
            })
            .finally(() => {
              if (dashboardRequest.current === requestId)
                setOverviewSecondaryLoading(false);
            });
          return;
        }

        if (requestedTab === "openings") {
          const nextOpenings = await operationsApi.openingsAnalytics(
            effectiveFilters,
            openingsGranularity,
          );
          if (dashboardRequest.current !== requestId) return;
          setOpeningsAnalytics(nextOpenings);
          return;
        }

        if (requestedTab === "sla") {
          const [nextSlaHierarchy, nextCollaboratorSla] =
            await Promise.all([
              operationsApi.slaHierarchy(effectiveFilters, "os_type"),
              operationsApi.collaboratorSla(effectiveFilters),
            ]);
          if (dashboardRequest.current !== requestId) return;
          setSlaHierarchy(nextSlaHierarchy);
          setCollaboratorSla(nextCollaboratorSla);
          return;
        }

        if (requestedTab === "calendar") {
          const nextCalendar = await operationsApi.calendar(
            effectiveFilters,
            calendarGrouping,
          );
          if (dashboardRequest.current !== requestId) return;
          setCalendar(nextCalendar);
          return;
        }

        if (requestedTab === "progress") {
          const [nextRegional, nextCity, nextType, nextSubject, nextStatus, nextSlaRisk] =
            await Promise.all([
              operationsApi.inProgress(effectiveFilters, "regional"),
              operationsApi.inProgress(effectiveFilters, "city"),
              operationsApi.inProgress(effectiveFilters, "os_type"),
              operationsApi.inProgress(effectiveFilters, "subject"),
              operationsApi.inProgress(effectiveFilters, "status"),
              operationsApi.inProgressSlaRisk(effectiveFilters),
            ]);
          if (dashboardRequest.current !== requestId) return;
          setRegionalBreakdown(nextRegional);
          setCityBreakdown(nextCity);
          setTypeBreakdown(nextType);
          setSubjectBreakdown(nextSubject);
          setStatusBreakdown(nextStatus);
          setSlaRiskBreakdown(nextSlaRisk);
          closeProgressDrill();
          return;
        }

        const nextOrders = await (detailsScope === "openings"
          ? operationsApi.openingOrders(effectiveFilters, page, 50, detailSort)
          : operationsApi.orders(effectiveFilters, page, 50, detailSort));
        if (dashboardRequest.current !== requestId) return;
        setOrders(nextOrders);
      } catch (reason) {
        if (dashboardRequest.current === requestId) {
          setOverviewLoading(false);
          setOverviewSecondaryLoading(false);
          setError(
            reason instanceof Error
              ? reason.message
              : "Falha ao carregar o módulo Operação.",
          );
        }
      } finally {
        if (dashboardRequest.current === requestId) setLoading(false);
      }
    },
    [
      activeTab,
      calendarGroupBy,
      detailsScope,
      detailSort,
      openingsGranularity,
      trendGranularity,
      workScheduleModelIds,
    ],
  );

  useEffect(() => {
    if (!user || !canRead) return;
    let active = true;
    Promise.all([
      operationsApi.period(),
      operationsApi.savedFilters(),
      operationsApi.dataFreshness(),
      canSyncIxc ? operationsApi.ixcSyncSettings() : Promise.resolve(null),
    ])
      .then(([nextPeriod, nextSavedFilters, nextFreshness, nextIxcSettings]) => {
        if (!active) return;
        const initial: OperationFilterState = {
          date_from: nextPeriod.date_from,
          date_to: nextPeriod.date_to,
          responsible_mode: "all",
          sectors: [...DEFAULT_PRIORITY_SECTORS],
        };
        setPeriod(nextPeriod);
        setSavedFilters(nextSavedFilters);
        setDataFreshness(nextFreshness);
        setIxcSyncSettings(nextIxcSettings);
        setFilters(initial);
        void operationsApi.filters(initial, "period").then(setFilterOptions);
        void loadDashboard(initial);
      })
      .catch((reason) => {
        if (active)
          setError(
            reason instanceof Error
              ? reason.message
              : "Falha ao carregar o período disponível.",
          );
      });
    return () => {
      active = false;
    };
    // A carga inicial depende da sessão; mudanças de hierarquia SLA são tratadas
    // pelo efeito específico abaixo para não reinicializar os filtros.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, canRead]);

  const filterCount = useMemo(
    () =>
      filters
        ? Object.entries(filters).filter(([key, value]) => {
            if (key.startsWith("date_")) return false;
            if (key === "responsible_mode" && (!value || value === "all"))
              return false;
            return Array.isArray(value) ? value.length > 0 : Boolean(value);
          }).length
        : 0,
    [filters],
  );
  const visibleOrderItems = useMemo(() => {
    // A ordenação em si já vem pronta do backend (ver changeDetailSort/loadDetailsPage) - ela
    // cobre o dataset inteiro, não só a página carregada. Este useMemo só existe pra manter a
    // mesma referência de variável usada na tabela abaixo.
    return orders.items;
  }, [orders.items, detailSort]);
  const detailCellClass = (key: DetailSortKey, value: string | null) =>
    detailQuickFilter?.key === key && detailQuickFilter.value === (value || "")
      ? "bg-blue-100 text-blue-950 ring-1 ring-inset ring-blue-400"
      : undefined;

  useEffect(() => {
    function clearDetailSelection(event: PointerEvent) {
      if (
        detailTableRef.current &&
        !detailTableRef.current.contains(event.target as Node)
      )
        setDetailQuickFilter(null);
    }
    document.addEventListener("pointerdown", clearDetailSelection);
    return () =>
      document.removeEventListener("pointerdown", clearDetailSelection);
  }, []);

  function changeDetailSort(key: DetailSortKey) {
    const direction: "asc" | "desc" =
      detailSort.key === key && detailSort.direction === "desc"
        ? "asc"
        : "desc";
    const nextSort = { key, direction };
    setDetailSort(nextSort);
    void loadDetailsPage(1, nextSort);
  }

  function detailSortMark(key: DetailSortKey) {
    if (detailSort.key !== key) return "";
    return detailSort.direction === "asc" ? " ↑" : " ↓";
  }

  async function refreshFilterOptions(next: OperationFilterState) {
    const requestId = filterOptionsRequest.current + 1;
    filterOptionsRequest.current = requestId;
    try {
      const openScope =
        activeTab === "progress" || !next.date_from || !next.date_to;
      const nextOptions = await operationsApi.filters(
        next,
        openScope ? "in_progress" : "period",
      );
      if (filterOptionsRequest.current === requestId)
        setFilterOptions(nextOptions);
    } catch (reason) {
      if (filterOptionsRequest.current === requestId) {
        setError(
          reason instanceof Error
            ? reason.message
            : "Falha ao atualizar as opções dos filtros.",
        );
      }
    }
  }

  function applyFilters(next: OperationFilterState) {
    // Choices are refreshed only on an explicit application, not on every click.
    void refreshFilterOptions(next);
    void loadDashboard(next);
  }

  function updateFilter(
    key: keyof OperationFilterState,
    value: string | string[],
  ) {
    if (!filters) return;
    const normalizedValue = Array.isArray(value)
      ? value
      : key === "date_from" || key === "date_to"
        ? value
        : value || undefined;
    const next = { ...filters, [key]: normalizedValue };
    setFilters((current) =>
      current ? { ...current, [key]: normalizedValue } : current,
    );
  }

  function clearDates() {
    if (!filters) return;
    const next = { ...filters, date_from: "", date_to: "" };
    setFilters(next);
  }

  function clearAllFilters() {
    if (!period) return;
    const next: OperationFilterState = {
      date_from: period.date_from,
      date_to: period.date_to,
      responsible_mode: "all",
      sectors: [...DEFAULT_PRIORITY_SECTORS],
    };
    setSelectedSavedFilterId(null);
    setFilterName("");
    setMessage("Filtros limpos. O período voltou para o mês atual.");
    setError(null);
    setFilters(next);
    applyFilters(next);
  }

  function savedValues(
    current: OperationFilterState,
  ): OperationSavedFilterValues {
    const { date_from: _dateFrom, date_to: _dateTo, ...values } = current;
    return values;
  }

  async function refreshSavedFilters(selectedId?: number | null) {
    const next = await operationsApi.savedFilters();
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
    if (!saved || !filters) return;
    const cleanSaved = Object.fromEntries(
      Object.entries(saved.filters).filter(([, value]) => value !== null),
    );
    const next = {
      date_from: filters.date_from || "",
      date_to: filters.date_to || "",
      ...cleanSaved,
    } as OperationFilterState;
    setFilterName(saved.name);
    setSavedFilterVisibility(saved.visibility);
    setFilters(next);
    applyFilters(next);
  }

  async function saveCurrentFilter() {
    if (!filters || !filterName.trim()) return;
    setError(null);
    try {
      const saved = await operationsApi.createSavedFilter(
        filterName.trim(),
        savedValues(filters),
        savedFilterVisibility,
      );
      await refreshSavedFilters(saved.id);
      setFilterName(saved.name);
      setMessage(`Filtro "${saved.name}" salvo.`);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Falha ao salvar o filtro.",
      );
    }
  }

  async function updateCurrentSavedFilter() {
    if (!filters || !selectedSavedFilterId || !filterName.trim()) return;
    setError(null);
    try {
      const saved = await operationsApi.updateSavedFilter(
        selectedSavedFilterId,
        {
          name: filterName.trim(),
          filters: savedValues(filters),
          visibility: savedFilterVisibility,
        },
      );
      await refreshSavedFilters(saved.id);
      setFilterName(saved.name);
      setMessage(`Filtro "${saved.name}" atualizado.`);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Falha ao atualizar o filtro.",
      );
    }
  }

  async function deleteCurrentSavedFilter() {
    if (!selectedSavedFilterId) return;
    const savedName =
      savedFilters.find((item) => item.id === selectedSavedFilterId)?.name ||
      "selecionado";
    setError(null);
    try {
      await operationsApi.deleteSavedFilter(selectedSavedFilterId);
      await refreshSavedFilters(null);
      setFilterName("");
      setSavedFilterVisibility("personal");
      setMessage(`Filtro "${savedName}" excluído.`);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Falha ao excluir o filtro.",
      );
    }
  }

  async function runImport() {
    if (!filters || !canSyncIxc) return;
    const days = datesInRange(filters.date_from, filters.date_to);
    if (!days.length) {
      setError("Selecione um periodo valido para atualizar o IXC.");
      return;
    }
    setImporting(true);
    setImportProgress(`0/${days.length} dias`);
    setMessage(null);
    setError(null);
    const sectorIds = configuredIxcSectorIds(ixcSyncSettings);
    const scopeLabel = ixcSyncSettings?.sector_scope_label || "escopo padrão";
    try {
      // Sempre via job assíncrono, mesmo para 1 dia - uma importação em processo (varredura de 21
      // setores + lookups em cascata) passa fácil de 30s, e um request síncrono nessa duração
      // estourava o timeout do proxy do Next na VM e voltava 500. O job roda em background e a tela
      // só faz polling do status, então o botão nunca fica preso numa requisição longa.
      const started = await operationsApi.startBackfillImport(
        filters.date_from,
        filters.date_to,
        sectorIds,
      );
      let job = started;
      setImportProgress(`${job.processed_days}/${job.total_days} dias`);
      while (job.status === "pending" || job.status === "running") {
        await wait(1500);
        job = await operationsApi.backfillImportStatus(job.id);
        setImportProgress(`${job.processed_days}/${job.total_days} dias`);
      }
      if (job.status !== "completed") {
        throw new Error(
          `Importacao interrompida em ${job.processed_days}/${job.total_days} dias.`,
        );
      }
      setMessage(
        `IXC atualizado (${scopeLabel}): ${job.created_count} novas, ${job.updated_count} atualizadas, ${job.unchanged_count} sem alteracao e ${job.rejected_count} rejeitadas.`,
      );
      await loadDashboard(filters);
      void operationsApi
        .dataFreshness()
        .then(setDataFreshness)
        .catch(() => undefined);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Falha ao atualizar dados do IXC.",
      );
    } finally {
      setImporting(false);
      setImportProgress(null);
    }
  }

  async function runOpenBacklogImport() {
    if (!filters || !canSyncIxc) return;
    setImportingBacklog(true);
    setMessage(null);
    setError(null);
    try {
      const sectorIds = configuredIxcSectorIds(ixcSyncSettings);
      const scopeLabel = ixcSyncSettings?.sector_scope_label || "escopo padrão";
      // Mesmo raciocínio de runImport: a varredura de backlog aberto passa por todos os setores
      // configurados (particionando internamente quando um setor+status excede o limite seguro de
      // 3000 O.S.) e pode demorar bem mais que 30s - roda como job assíncrono, com polling de status.
      let job = await operationsApi.startOpenBacklogImport(sectorIds);
      setImportProgress(`${job.processed_sectors}/${job.total_sectors} setores`);
      while (job.status === "pending" || job.status === "running") {
        await wait(1500);
        job = await operationsApi.openBacklogImportStatus(job.id);
        setImportProgress(`${job.processed_sectors}/${job.total_sectors} setores`);
      }
      if (job.status !== "completed") {
        throw new Error(
          `Varredura de backlog interrompida em ${job.processed_sectors}/${job.total_sectors} setores.`,
        );
      }
      setMessage(
        `Backlog IXC atualizado (${scopeLabel}): ${job.created_count} novas, ${job.updated_count} atualizadas, ${job.unchanged_count} sem alteração e ${job.rejected_count} rejeitadas.`,
      );
      await loadDashboard(filters);
      void operationsApi
        .dataFreshness()
        .then(setDataFreshness)
        .catch(() => undefined);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Falha ao atualizar o backlog aberto do IXC.",
      );
    } finally {
      setImportingBacklog(false);
      setImportProgress(null);
    }
  }

  async function loadProgressDrill(target: ProgressDrillTarget) {
    // Mesmo padrão da aba Aberturas: expande inline dentro da própria aba Andamento, sem tocar em
    // `filters`/`activeTab` - sair do drill não deixa nada "grudado" no painel principal.
    if (!filters || !canViewOrderDetails) return;
    setProgressDrill(target);
    setProgressDrillLoading(true);
    try {
      const base = filtersForOpenScope(filters);
      const next = target.kind === "dimension" ? { ...base, [target.field]: [target.value] } : base;
      const slaRisk = target.kind === "sla_risk" ? target.bucket : undefined;
      setProgressDrillOrders(
        await operationsApi.inProgressOrders(next, 1, 25, { key: "opened_at", direction: "desc" }, slaRisk),
      );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Falha ao abrir o detalhamento.",
      );
    } finally {
      setProgressDrillLoading(false);
    }
  }

  function toggleProgressDrill(target: ProgressDrillTarget) {
    if (progressDrill?.key === target.key) {
      closeProgressDrill();
      return;
    }
    void loadProgressDrill(target);
  }

  function closeProgressDrill() {
    setProgressDrill(null);
    setProgressDrillOrders(EMPTY_PAGE);
  }

  async function loadOpeningsDrill(
    target: OpeningsDrillTarget,
    extra?: { aging_bucket?: string; weekday?: number; hour?: number },
  ) {
    // Expande inline dentro da própria aba Aberturas - usa appliedFilters como base sem tocar em
    // `filters`/`activeTab`, pra sair do drill não deixar o recorte "grudado" no painel principal.
    // Clicar de novo no mesmo alvo (mesma barra/célula) fecha em vez de recarregar - ver `toggle`
    // abaixo, chamado pelos três pontos de entrada (dimensão, envelhecimento, mapa de calor).
    if (!appliedFilters || !canViewOrderDetails) return;
    setOpeningsDrill(target);
    setOpeningsDrillLoading(true);
    try {
      const filters =
        target.kind === "dimension" ? { ...appliedFilters, [target.field]: [target.value] } : appliedFilters;
      setOpeningsDrillOrders(
        await operationsApi.openingOrders(
          filters,
          1,
          25,
          { key: "opened_at", direction: "desc" },
          extra,
        ),
      );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Falha ao abrir as O.S. de abertura.",
      );
    } finally {
      setOpeningsDrillLoading(false);
    }
  }

  function toggleOpeningsDrill(
    target: OpeningsDrillTarget,
    extra?: { aging_bucket?: string; weekday?: number; hour?: number },
  ) {
    if (openingsDrill?.key === target.key) {
      closeOpeningsDrill();
      return;
    }
    void loadOpeningsDrill(target, extra);
  }

  function drillOpenings(field: OpeningsDrillField, value: string) {
    toggleOpeningsDrill({ kind: "dimension", field, value, key: `dimension:${field}:${value}` });
  }

  function drillAgingBucket(bucket: string, label: string) {
    toggleOpeningsDrill({ kind: "aging", bucket, label, key: `aging:${bucket}` }, { aging_bucket: bucket });
  }

  function drillHeatmapSlot(weekday: number, hour: number, label: string) {
    toggleOpeningsDrill(
      { kind: "heatmap", weekday, hour, label, key: `heatmap:${weekday}:${hour}` },
      { weekday, hour },
    );
  }

  function closeOpeningsDrill() {
    setOpeningsDrill(null);
    setOpeningsDrillOrders(EMPTY_PAGE);
  }

  async function selectOpeningsPeriod(dateFrom: string, dateTo: string, label: string) {
    // Recorte temporário só desse gráfico - usa appliedFilters como base sem tocar em `filters`, e
    // sempre busca por dia (independente da granularidade escolhida) pra dar pra ver o detalhe diário
    // do período clicado.
    if (!appliedFilters) return;
    setOpeningsTemporaryPeriod({ label, date_from: dateFrom, date_to: dateTo });
    setOpeningsTemporaryLoading(true);
    try {
      const next = { ...appliedFilters, date_from: dateFrom, date_to: dateTo };
      setOpeningsTemporaryData(await operationsApi.openingsAnalytics(next, "day"));
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Falha ao abrir o recorte temporário do gráfico.",
      );
    } finally {
      setOpeningsTemporaryLoading(false);
    }
  }

  function clearOpeningsPeriod() {
    setOpeningsTemporaryPeriod(null);
    setOpeningsTemporaryData(null);
  }

  async function loadDetailsPage(
    page: number,
    sort: { key: DetailSortKey; direction: "asc" | "desc" } = detailSort,
  ) {
    if (!filters || !canViewOrderDetails) return;
    setLoading(true);
    setError(null);
    try {
      setOrders(
        detailsScope === "openings"
          ? await operationsApi.openingOrders(filters, page, 50, sort)
          : await operationsApi.orders(filters, page, 50, sort),
      );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Falha ao carregar a página de O.S.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function openControlTowerOrders(path: OperationControlTowerPath) {
    if (!filters || !controlTower.reference_date || !canViewOrderDetails) return;
    const end = new Date(`${controlTower.reference_date}T12:00:00Z`);
    end.setUTCDate(end.getUTCDate() - (controlTower.recent_days - 1));
    const next: OperationFilterState = {
      ...filters,
      date_from: end.toISOString().slice(0, 10),
      date_to: controlTower.reference_date,
      subjects: path.subject ? [path.subject] : filters.subjects,
      regionals: path.regional ? [path.regional] : filters.regionals,
      cities: path.city ? [path.city] : filters.cities,
      sectors: path.sector ? [path.sector] : filters.sectors,
      responsibles: path.responsible ? [path.responsible] : [],
    };
    setFilters(next);
    setAppliedFilters(next);
    setDetailsScope("openings");
    setActiveTab("details");
    setLoading(true);
    setError(null);
    try {
      setOrders(await operationsApi.openingOrders(next, 1, 50, detailSort));
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Falha ao abrir as O.S. deste alerta.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function changeTrendGranularity(
    nextGranularity: OperationTrendGranularity,
  ) {
    if (!appliedFilters || nextGranularity === trendGranularity) return;
    setTrendGranularity(nextGranularity);
    setLoading(true);
    setError(null);
    try {
      setOverviewTrends(
        await operationsApi.overviewTrends(appliedFilters, nextGranularity),
      );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Falha ao alterar o agrupamento dos gráficos.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function changeOpeningsGranularity(
    nextGranularity: OperationTrendGranularity,
  ) {
    if (!appliedFilters || nextGranularity === openingsGranularity) return;
    setOpeningsGranularity(nextGranularity);
    setLoading(true);
    setError(null);
    try {
      setOpeningsAnalytics(
        await operationsApi.openingsAnalytics(appliedFilters, nextGranularity),
      );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Falha ao alterar o agrupamento do gráfico de aberturas.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function changeWorkScheduleModels(modelIds: number[]) {
    setWorkScheduleModelIds(modelIds);
    if (!appliedFilters) return;
    try {
      setWorkSchedule(
        await operationsApi.overviewWorkSchedule(appliedFilters, modelIds),
      );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Falha ao analisar a jornada dos modelos selecionados.",
      );
    }
  }

  function navigateToTab(tab: OperationTab) {
    if (!visibleTabs.includes(tab)) return;
    setActiveTab(tab);
    if (!filters) return;
    if (tab === "teams") {
      dashboardRequest.current += 1;
      setLoading(false);
      return;
    }
    const next = tab === "progress" ? filtersForOpenScope(filters) : filters;
    if (next !== filters) setFilters(next);
    void loadDashboard(next, 1, tab);
  }

  if (checking && !user)
    return (
      <main className="flex min-h-screen items-center justify-center text-sm text-slate-500">
        Carregando UNI Workspace...
      </main>
    );
  if (!user)
    return (
      <WorkspaceLogin isLoading={checking} error={authError} onLogin={login} />
    );
  if (!canRead) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4">
        <div className="max-w-md rounded-2xl border bg-white p-8 text-center">
          <h1 className="text-xl font-semibold">Acesso não autorizado</h1>
          <p className="mt-2 text-sm text-slate-500">
            Seu perfil não possui a permissão operations:read.
          </p>
          <Link
            href="/"
            className="mt-5 inline-block text-sm font-semibold text-blue-700"
          >
            Voltar ao ecossistema
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-4 px-4 py-3 lg:px-7">
          <div className="flex items-center gap-3">
            <OperationsModuleSidebar
              activeTab={activeTab}
              detailsCount={orders.total}
              canManage={canManage}
              visibleTabs={visibleTabs}
              onChange={navigateToTab}
            />
            <Link
              href="/"
              aria-label="Voltar ao ecossistema"
              className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50 text-blue-700"
            >
              <Home className="h-5 w-5" />
            </Link>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-blue-600">
                UNI Workspace
              </p>
              <h1 className="text-base font-semibold text-slate-950">
                Operação Analítica
              </h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/gamificacao"
              className="hidden rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 sm:block"
            >
              Gamificação
            </Link>
            <Button type="button" variant="ghost" size="sm" onClick={logout}>
              <LogOut className="h-4 w-4" /> Sair
            </Button>
          </div>
        </div>
      </header>

      <OperationsFilterPanel
        filters={filters}
        options={filterOptions}
        period={period}
        savedFilters={savedFilters}
        selectedSavedFilterId={selectedSavedFilterId}
        filterName={filterName}
        savedFilterVisibility={savedFilterVisibility}
        loading={loading}
        importing={importing}
        importProgress={importProgress}
        lastUpdatedAt={dataFreshness?.last_successful_import_at || null}
        canSyncIxc={canSyncIxc}
        syncScopeLabel={`Escopo IXC: ${ixcSyncSettings?.sector_scope_label || "3 setores principais"}.`}
        canManageViews={canManageViews}
        canCreateGlobalViews={canCreateGlobalViews}
        datesIgnored={activeTab === "progress"}
        filterCount={filterCount}
        onChange={updateFilter}
        onApply={() => filters && applyFilters(filters)}
        onClearAll={clearAllFilters}
        onClearDates={clearDates}
        onImport={() => void runImport()}
        onSelectSavedFilter={selectSavedFilter}
        onFilterNameChange={setFilterName}
        onSavedFilterVisibilityChange={setSavedFilterVisibility}
        onSave={() => void saveCurrentFilter()}
        onUpdateSaved={() => void updateCurrentSavedFilter()}
        onDeleteSaved={() => void deleteCurrentSavedFilter()}
      />

      <section className="px-4 py-6 lg:px-7">
        {message ? (
          <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
            {message}
          </div>
        ) : null}
        {error ? (
          <div
            role="alert"
            className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
          >
            {error}
          </div>
        ) : null}
        <Tabs
          value={activeTab}
          onValueChange={(value) => navigateToTab(value as OperationTab)}
        >
          <TabsContent value="overview">
            <div
              aria-busy={overviewLoading}
              className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
            >
              <OverviewMetricCard
                title="Abertas no período"
                value={overview.opened}
                helper={`Média diária: ${formatNumber(overview.average_daily_opened)}`}
                note={
                  overview.responsible_filter_active
                    ? `${overview.opened_associated} associadas ao recorte de colaboradores`
                    : "Recorte pela data de abertura"
                }
              />
              <OverviewMetricCard
                title="Finalizadas no período"
                value={overview.completed}
                helper={`Média diária: ${formatNumber(overview.average_daily_completed)}`}
                note="Recorte pela data de fechamento"
              />
              <OverviewMetricCard
                title="Backlog atual"
                value={overview.in_progress}
                helper={`${overview.opened_out_of_time} abertas atrasadas`}
                note="Estoque ainda em andamento na consulta"
                tone={overview.opened_out_of_time ? "warning" : "neutral"}
              />
              <OverviewMetricCard
                title="SLA de finalização"
                value={formatNumber(overview.sla_rate, "%")}
                helper={`${overview.completed_on_time} no prazo · ${overview.completed_out_of_time} atrasadas`}
                note="Somente O.S. finalizadas e mensuráveis"
                tone={slaTone(overview.sla_rate)}
              />
            </div>
            <div className="mt-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="grid gap-4 lg:grid-cols-[1fr_1fr_1.2fr] lg:items-center">
                <div>
                  <p className="text-xs font-medium text-slate-500">
                    Tempo médio do ciclo
                  </p>
                  <p className="mt-1 text-2xl font-semibold text-slate-950">
                    {formatDurationMinutes(overview.average_cycle_minutes)}
                  </p>
                  <p className="text-xs text-slate-500">
                    Da abertura à finalização
                  </p>
                </div>
                <div>
                  <p className="text-xs font-medium text-slate-500">
                    Tempo até atendimento em campo
                  </p>
                  <p className="mt-1 text-2xl font-semibold text-slate-950">
                    {formatDurationMinutes(
                      overview.average_wait_to_displacement_minutes,
                    )}
                  </p>
                  <p className="text-xs text-slate-500">
                    Abertura até início do deslocamento
                  </p>
                </div>
                <div
                  className={`rounded-xl px-3 py-2 text-sm ${
                    efficiencyInsight(overview)
                      ? "bg-amber-50 text-amber-900"
                      : "bg-slate-50 text-slate-600"
                  }`}
                >
                  {efficiencyInsight(overview) ||
                    "Sem gargalo predominante identificado no ciclo médio do recorte."}
                </div>
              </div>
            </div>
            <OperationsWorkScheduleOverview
              data={workSchedule}
              selectedModelIds={workScheduleModelIds}
              onModelIdsChange={(ids) => void changeWorkScheduleModels(ids)}
            />
            <OperationsOverviewCharts
              trends={overviewTrends}
              workSchedule={workSchedule}
              isLoading={overviewSecondaryLoading}
              onGranularityChange={(granularity) =>
                void changeTrendGranularity(granularity)
              }
            />
            {appliedFilters ? (
              <OperationsControlTower
                data={controlTower}
                filters={appliedFilters}
                isLoading={overviewSecondaryLoading}
                onOpenOrders={(path) => void openControlTowerOrders(path)}
              />
            ) : (
              <div className="mt-4 h-24 animate-pulse rounded-2xl border bg-white" />
            )}
          </TabsContent>

          <TabsContent value="openings">
            <OperationsOpeningsAnalytics
              data={openingsTemporaryData || openingsAnalytics}
              isLoading={loading || openingsTemporaryLoading}
              onOpenOrders={(field, value) => drillOpenings(field, value)}
              onOpenAgingBucket={(bucket, label) => drillAgingBucket(bucket, label)}
              onOpenHeatmapSlot={(weekday, hour, label) => drillHeatmapSlot(weekday, hour, label)}
              drill={openingsDrill}
              drillOrders={openingsDrillOrders}
              drillLoading={openingsDrillLoading}
              onCloseDrill={closeOpeningsDrill}
              granularity={openingsTemporaryData ? "day" : openingsGranularity}
              onGranularityChange={
                openingsTemporaryData
                  ? undefined
                  : (granularity) => void changeOpeningsGranularity(granularity)
              }
              temporaryPeriod={openingsTemporaryPeriod}
              onSelectPeriod={(dateFrom, dateTo, label) =>
                void selectOpeningsPeriod(dateFrom, dateTo, label)
              }
              onClearPeriod={clearOpeningsPeriod}
            />
          </TabsContent>

          <TabsContent value="sla">
            {appliedFilters ? (
              <OperationsSlaHierarchyTable
                data={slaHierarchy}
                filters={appliedFilters}
                isLoading={loading}
              />
            ) : (
              <div className="h-80 animate-pulse rounded-2xl border bg-white" />
            )}
            <OperationsCollaboratorSlaTable data={collaboratorSla} />
          </TabsContent>

          <TabsContent value="calendar">
            {appliedFilters ? (
              <OperationsMonthlyCalendar
                data={calendar}
                filters={appliedFilters}
                isLoading={loading}
                groupBy={calendarGroupBy}
                onGroupByChange={(groupBy) => {
                  setCalendarGroupBy(groupBy);
                  void loadDashboard(
                    filters || appliedFilters,
                    1,
                    "calendar",
                    groupBy,
                  );
                }}
                onBack={() => setActiveTab("overview")}
              />
            ) : (
              <div className="h-80 animate-pulse rounded-2xl border bg-white" />
            )}
          </TabsContent>

          <TabsContent value="progress">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-blue-200 bg-blue-50 px-4 py-3">
              <div>
                <p className="font-semibold text-blue-950">
                  Backlog completo em andamento
                </p>
                <p className="text-xs text-blue-700">
                  Inclui todas as O.S. abertas existentes na base,
                  independentemente do mês de abertura.
                </p>
              </div>
              {canSyncIxc ? (
                <Button
                  type="button"
                  onClick={() => void runOpenBacklogImport()}
                  disabled={importingBacklog}
                >
                  {importingBacklog ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Database className="h-4 w-4" />
                  )}
                  {importingBacklog
                    ? `Consultando IXC${importProgress ? ` (${importProgress})` : "..."}`
                    : "Atualizar abertas no IXC"}
                </Button>
              ) : null}
            </div>
            {progressDrill ? (
              <ProgressDrillPanel
                target={progressDrill}
                orders={progressDrillOrders}
                isLoading={progressDrillLoading}
                onClose={closeProgressDrill}
              />
            ) : null}
            <div className="grid gap-4 xl:grid-cols-2 2xl:grid-cols-3">
              <BreakdownTable
                title="Filial"
                items={regionalBreakdown}
                activeLabel={progressDrill?.kind === "dimension" && progressDrill.field === "regionals" ? progressDrill.value : null}
                onDrill={(value) =>
                  toggleProgressDrill({ kind: "dimension", field: "regionals", value, key: `regionals:${value}` })
                }
              />
              <BreakdownTable
                title="Cidade"
                items={cityBreakdown}
                activeLabel={progressDrill?.kind === "dimension" && progressDrill.field === "cities" ? progressDrill.value : null}
                onDrill={(value) =>
                  toggleProgressDrill({ kind: "dimension", field: "cities", value, key: `cities:${value}` })
                }
              />
              <BreakdownTable
                title="Tipo geral"
                items={typeBreakdown}
                activeLabel={progressDrill?.kind === "dimension" && progressDrill.field === "os_types" ? progressDrill.value : null}
                onDrill={(value) =>
                  toggleProgressDrill({ kind: "dimension", field: "os_types", value, key: `os_types:${value}` })
                }
              />
              <BreakdownTable
                title="Assunto"
                items={subjectBreakdown}
                activeLabel={progressDrill?.kind === "dimension" && progressDrill.field === "subjects" ? progressDrill.value : null}
                onDrill={(value) =>
                  toggleProgressDrill({ kind: "dimension", field: "subjects", value, key: `subjects:${value}` })
                }
              />
              <BreakdownTable
                title="SLA / Status"
                items={statusBreakdown}
                activeLabel={progressDrill?.kind === "dimension" && progressDrill.field === "statuses" ? progressDrill.value : null}
                onDrill={(value) =>
                  toggleProgressDrill({ kind: "dimension", field: "statuses", value, key: `statuses:${value}` })
                }
              />
              <BreakdownTable
                title="SLA em risco (backlog)"
                items={slaRiskBreakdown}
                activeLabel={
                  progressDrill?.kind === "sla_risk"
                    ? slaRiskBreakdown.find((entry) => entry.bucket === progressDrill.bucket)?.label
                    : null
                }
                onDrill={(label) => {
                  const item = slaRiskBreakdown.find((entry) => entry.label === label);
                  if (item) toggleProgressDrill({ kind: "sla_risk", bucket: item.bucket, label: item.label, key: `sla_risk:${item.bucket}` });
                }}
              />
            </div>
          </TabsContent>

          <TabsContent value="details">
            <Card ref={detailTableRef} className="rounded-2xl border-slate-200">
              <CardHeader className="flex-row items-center justify-between gap-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <CardTitle className="text-base font-semibold text-slate-900">
                      {detailsScope === "openings"
                        ? "Aberturas do alerta operacional"
                        : "Detalhamento de O.S."}
                    </CardTitle>
                    <Badge className="border-blue-200 bg-blue-50 text-blue-800">
                      {orders.total} O.S. no total
                    </Badge>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">
                    Ordene pelo cabeçalho (considera todas as páginas); Ctrl/Cmd
                    + clique em um dado cria um recorte temporário.{" "}
                    {detailsScope === "openings"
                      ? "Somente O.S. abertas nos 7 dias analisados, preservando o caminho selecionado."
                      : "Os filtros do painel são preservados."}
                  </p>
                  {detailQuickFilter ? (
                    <Badge className="mt-2 border-blue-200 bg-blue-50 text-blue-800">
                      Recorte temporário:{" "}
                      {detailQuickFilter.value || "Não informado"}
                    </Badge>
                  ) : null}
                </div>
                <div className="relative w-full max-w-xs">
                  <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
                  <Input
                    value={filters?.search || ""}
                    onChange={(event) =>
                      updateFilter("search", event.target.value)
                    }
                    onKeyDown={(event) => {
                      if (event.key === "Enter") void loadDetailsPage(1);
                    }}
                    placeholder="Contrato, cliente ou O.S."
                    className="pl-9"
                  />
                </div>
              </CardHeader>
              <CardContent className="px-0">
                <Table
                  onClickCapture={(event) => {
                    if (!(event.ctrlKey || event.metaKey)) return;
                    const cell = (
                      event.target as HTMLElement
                    ).closest<HTMLElement>("[data-filter-key]");
                    if (!cell) return;
                    event.preventDefault();
                    event.stopPropagation();
                    const key = cell.dataset.filterKey as DetailSortKey;
                    const value = cell.dataset.filterValue || "";
                    setDetailQuickFilter((current) =>
                      current?.key === key && current.value === value
                        ? null
                        : { key, value },
                    );
                  }}
                >
                  <TableHeader>
                    <TableRow>
                      <TableHead>
                        <button
                          type="button"
                          onClick={() => changeDetailSort("order_code")}
                        >
                          O.S.{detailSortMark("order_code")}
                        </button>
                      </TableHead>
                      <TableHead>
                        <button
                          type="button"
                          onClick={() => changeDetailSort("customer")}
                        >
                          Contrato/Cliente{detailSortMark("customer")}
                        </button>
                      </TableHead>
                      <TableHead>
                        <button
                          type="button"
                          onClick={() => changeDetailSort("regional")}
                        >
                          Filial{detailSortMark("regional")}
                        </button>
                      </TableHead>
                      <TableHead>
                        <button
                          type="button"
                          onClick={() => changeDetailSort("type_subject")}
                        >
                          Tipo/Assunto{detailSortMark("type_subject")}
                        </button>
                      </TableHead>
                      <TableHead>
                        <button
                          type="button"
                          onClick={() => changeDetailSort("responsible")}
                        >
                          Responsável{detailSortMark("responsible")}
                        </button>
                      </TableHead>
                      <TableHead>
                        <button
                          type="button"
                          onClick={() => changeDetailSort("opened_at")}
                        >
                          Abertura{detailSortMark("opened_at")}
                        </button>
                      </TableHead>
                      <TableHead>
                        <button
                          type="button"
                          onClick={() => changeDetailSort("closed_at")}
                        >
                          Fechamento{detailSortMark("closed_at")}
                        </button>
                      </TableHead>
                      <TableHead>
                        <button
                          type="button"
                          onClick={() => changeDetailSort("status")}
                        >
                          Status{detailSortMark("status")}
                        </button>
                      </TableHead>
                      <TableHead>
                        <button
                          type="button"
                          onClick={() => changeDetailSort("sla_status")}
                        >
                          SLA{detailSortMark("sla_status")}
                        </button>
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {visibleOrderItems.length ? (
                      visibleOrderItems.map((order) => (
                        <TableRow
                          key={order.id}
                          tabIndex={0}
                          className="cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500"
                          aria-label={`Abrir detalhes da O.S. ${order.order_code}`}
                          onClick={() => setSelectedOrder(order)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault();
                              setSelectedOrder(order);
                            }
                          }}
                        >
                          <TableCell
                            data-filter-key="order_code"
                            data-filter-value={order.order_code}
                            className={detailCellClass(
                              "order_code",
                              order.order_code,
                            )}
                          >
                            <p className="font-semibold text-slate-900">
                              {order.order_code}
                            </p>
                            <p className="text-xs text-slate-500">
                              {order.protocol || "Sem protocolo"}
                            </p>
                          </TableCell>
                          <TableCell
                            data-filter-key="customer"
                            data-filter-value={orderField(order, "customer")}
                            className={detailCellClass(
                              "customer",
                              orderField(order, "customer"),
                            )}
                          >
                            <p>{order.contract_id || "—"}</p>
                            <p className="max-w-48 truncate text-xs text-slate-500">
                              {order.customer_name ||
                                "Cliente não identificado"}
                            </p>
                          </TableCell>
                          <TableCell
                            data-filter-key="regional"
                            data-filter-value={order.regional || ""}
                            className={detailCellClass(
                              "regional",
                              order.regional,
                            )}
                          >
                            {order.regional || "—"}
                          </TableCell>
                          <TableCell
                            data-filter-key="type_subject"
                            data-filter-value={orderField(
                              order,
                              "type_subject",
                            )}
                            className={detailCellClass(
                              "type_subject",
                              orderField(order, "type_subject"),
                            )}
                          >
                            <p>{order.os_type || "—"}</p>
                            <p className="max-w-64 truncate text-xs text-slate-500">
                              {order.os_subject || "—"}
                            </p>
                          </TableCell>
                          <TableCell
                            data-filter-key="responsible"
                            data-filter-value={order.responsible || ""}
                            className={detailCellClass(
                              "responsible",
                              order.responsible,
                            )}
                          >
                            {order.responsible || "—"}
                          </TableCell>
                          <TableCell
                            data-filter-key="opened_at"
                            data-filter-value={order.opened_at}
                            className={detailCellClass(
                              "opened_at",
                              order.opened_at,
                            )}
                          >
                            {formatDate(order.opened_at)}
                          </TableCell>
                          <TableCell
                            data-filter-key="closed_at"
                            data-filter-value={order.closed_at || ""}
                            className={detailCellClass(
                              "closed_at",
                              order.closed_at,
                            )}
                          >
                            {formatDate(order.closed_at)}
                          </TableCell>
                          <TableCell
                            data-filter-key="status"
                            data-filter-value={order.status || ""}
                            className={detailCellClass("status", order.status)}
                          >
                            {order.status || "—"}
                          </TableCell>
                          <TableCell
                            data-filter-key="sla_status"
                            data-filter-value={order.sla_status}
                            className={detailCellClass(
                              "sla_status",
                              order.sla_status,
                            )}
                          >
                            <Badge
                              className={
                                order.sla_status === "out_of_time"
                                  ? "border-red-200 bg-red-50 text-red-700"
                                  : "border-emerald-200 bg-emerald-50 text-emerald-700"
                              }
                            >
                              {slaLabel(order.sla_status)}
                            </Badge>
                            <p className="mt-1 text-xs text-slate-500">
                              {formatNumber(order.elapsed_hours, "h")}
                            </p>
                          </TableCell>
                        </TableRow>
                      ))
                    ) : (
                      <TableRow>
                        <TableCell
                          colSpan={9}
                          className="py-14 text-center text-slate-500"
                        >
                          Nenhuma O.S. encontrada no contexto atual.
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
                <div className="flex items-center justify-between border-t px-4 py-3 text-sm text-slate-500">
                  <span>
                    Página {orders.page} de {Math.max(orders.total_pages, 1)}
                  </span>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={orders.page <= 1 || loading || !filters}
                      onClick={() => void loadDetailsPage(orders.page - 1)}
                    >
                      Anterior
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={
                        orders.page >= orders.total_pages || loading || !filters
                      }
                      onClick={() => void loadDetailsPage(orders.page + 1)}
                    >
                      Próxima
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="teams">
            <OperationsTeamConfiguration
              canManageTeamModels={canManageTeamModels}
              canManageSubjects={canManageSubjects}
              canManageViews={canManageViews}
              canSyncIxc={canSyncIxc}
              ixcSyncSettings={ixcSyncSettings}
              onIxcSyncSettingsChange={setIxcSyncSettings}
            />
          </TabsContent>
        </Tabs>
        {loading ? (
          <div className="fixed bottom-5 right-5 flex items-center gap-2 rounded-full bg-slate-950 px-4 py-2 text-sm text-white shadow-xl">
            <Loader2 className="h-4 w-4 animate-spin" /> Atualizando painel
          </div>
        ) : null}
      </section>
      <OperationsOrderDetailDialog
        order={selectedOrder}
        onOpenChange={(open) => {
          if (!open) setSelectedOrder(null);
        }}
      />
    </main>
  );
}
