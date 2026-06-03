"use client";

import { AlertTriangle, BarChart3, CalendarDays, CheckCircle2, ChevronDown, ChevronUp, CircleDollarSign, ClipboardList, Download, Loader2, LockKeyhole, Mail, RefreshCw, Search, Settings2, Trophy, UsersRound } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AuditPanel } from "@/components/gamification/audit-panel";
import { ClosureHistoryPanel } from "@/components/gamification/closure-history-panel";
import { CollaboratorRegistryPanel } from "@/components/gamification/collaborator-registry-panel";
import { CollaboratorOrdersSheet } from "@/components/gamification/collaborator-orders-sheet";
import { DashboardCharts } from "@/components/gamification/dashboard-charts";
import { InfoHint } from "@/components/gamification/info-hint";
import { LogicConfigurationPanel } from "@/components/gamification/logic-configuration-panel";
import { LeadershipBonusPanel } from "@/components/gamification/leadership-bonus-panel";
import { RankingTable } from "@/components/gamification/ranking-table";
import { UnmappedDiagnosesPanel } from "@/components/gamification/unmapped-diagnoses-panel";
import { UnmappedSubjectsPanel } from "@/components/gamification/unmapped-subjects-panel";
import { UpvalueImportPanel } from "@/components/gamification/upvalue-import-panel";
import { UserManagementPanel } from "@/components/gamification/user-management-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, setAuthToken } from "@/lib/api";
import { normalizeRegional, regionalName } from "@/lib/regional";
import type {
  CalculationRunHistory,
  AuthUser,
  CollaboratorRegistry,
  CollaboratorRegistryItem,
  CollaboratorScore,
  DashboardSummary,
  FinancialBreakdownItem,
  HealthRule,
  ImportedDiagnosis,
  LeadershipProfile,
  LeadershipRoleProfile,
  PenaltyDistributionItem,
  RecurrenceClassificationRule,
  ScoringGroup,
  ScoringSubjectRule,
  ServiceOrder,
  ServiceOrderSubjectSummary,
  SlaPenaltyRule,
  UnmappedSubject
} from "@/lib/types";

const numberFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const moneyFormat = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
type AnalysisPeriod = { reference_month?: number; reference_year?: number; regional?: string | null };

const TAB_HELP: Record<string, string> = {
  closure: "Exibe o resumo financeiro e operacional do período, com valores, pontuação e conferências para pagamento.",
  ranking: "Mostra a comparação de desempenho entre equipes, regionais ou colaboradores no período analisado.",
  pending: "Lista itens que precisam de revisão, correção ou validação antes do fechamento.",
  config: "Reúne parâmetros operacionais, regras e definições que influenciam os cálculos e a exibição dos dados.",
  audit: "Permite consultar registros detalhados, validar regras aplicadas e conferir inconsistências.",
  history: "Mostra o acompanhamento de períodos anteriores e a evolução dos resultados.",
  import: "Permite definir ou consultar o mês de referência usado nas análises da competência."
};

const SECTION_HELP = {
  summary: "Consolida os valores principais do período, separando técnicos, liderança e total a pagar.",
  details: "Agrupa os blocos usados para conferência operacional e financeira do fechamento.",
  alerts: "Sinaliza inconsistências, itens sem regra ou pontos que exigem revisão.",
  leadership: "Resume o valor calculado para liderança com base no resultado auditado dos técnicos.",
  financial: "Mostra a decomposição dos valores do período por dimensão operacional.",
  financialRegional: "Distribui o valor estimado por regional dentro do recorte atual.",
  financialGroup: "Distribui o valor estimado por grupo ou tipo de serviço no recorte atual.",
  financialSubjects: "Aponta assuntos recorrentes que ainda não possuem regra aplicada.",
  chartArea: "Apresenta indicadores visuais para leitura rápida da saúde da base e do desempenho operacional.",
  filteredCharts: "Mostra os resultados considerando os filtros selecionados, como filial, regional ou período."
} as const;

function formatNumber(value: number) {
  return numberFormat.format(value);
}

function formatMoney(value: number) {
  return moneyFormat.format(value);
}

function formatPoints(value: number) {
  return `${formatNumber(value)} pts`;
}

function leadershipRoleLabel(value: string) {
  if (value === "supervisor") return "Supervisor";
  if (value === "regional_manager") return "Gerente da unidade";
  if (value === "portfolio_manager") return "Gerente de pasta";
  return value;
}

function parseOptionalNumber(value: string) {
  const normalized = value.trim().replace(",", ".");
  if (!normalized) return null;
  const parsed = Number(normalized);
  if (!Number.isFinite(parsed)) {
    throw new Error("Informe um valor numérico válido.");
  }
  return parsed;
}

function replaceById<T extends { id: number }>(items: T[], id: number, nextItem: T) {
  return items.map((item) => (item.id === id ? nextItem : item));
}

function FinancialTable({
  title,
  rows,
  labelKey,
  collapsed,
  onToggle
}: {
  title: string;
  rows: Array<Record<string, string | number | undefined>>;
  labelKey: "regional" | "group" | "os_subject";
  collapsed: boolean;
  onToggle: () => void;
}) {
  const totalOrders = rows.reduce((total, row) => total + Number(row.orders ?? 0), 0);
  const totalPayment = rows.reduce((total, row) => total + Number(row.estimated_payment ?? 0), 0);
  const helpText =
    labelKey === "regional"
      ? SECTION_HELP.financialRegional
      : labelKey === "group"
        ? SECTION_HELP.financialGroup
        : SECTION_HELP.financialSubjects;

  return (
    <div className="overflow-hidden rounded-[20px] border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      <div className="border-b bg-[linear-gradient(180deg,#ffffff_0%,#f8fbff_100%)] px-4 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="truncate text-sm font-semibold text-slate-950">{title}</h3>
              <InfoHint ariaLabel={`Ajuda sobre ${title}`} description={helpText} />
            </div>
            <p className="mt-1 text-sm text-slate-500">{formatNumber(rows.length)} item(ns)</p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-8 w-8 rounded-xl p-0 text-slate-500 hover:bg-slate-100 hover:text-slate-700"
            onClick={onToggle}
            title={collapsed ? "Expandir todos" : "Recolher todos"}
          >
            {collapsed ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
          </Button>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-3">
          <div className="rounded-2xl border border-slate-200 bg-white px-3 py-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">O.S</div>
            <div className="mt-1 text-lg font-semibold text-slate-950">{formatNumber(totalOrders)} O.S</div>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white px-3 py-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">Valor a ser pago</div>
            <div className="mt-1 text-lg font-semibold text-teal-700">{formatMoney(totalPayment)}</div>
          </div>
        </div>
      </div>
      {!collapsed ? (
        <div className="table-frame px-2 py-2">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Dimensão</TableHead>
                <TableHead>O.S</TableHead>
                <TableHead>Valor a ser pago</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.slice(0, 8).map((row, index) => (
                <TableRow key={`${title}-${index}`}>
                  <TableCell className="min-w-52">
                    <div className="flex items-start gap-3">
                      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-100 text-[11px] font-semibold text-slate-600">
                        {index + 1}
                      </div>
                      <div className="font-medium text-slate-900">
                        {labelKey === "regional" ? regionalName(String(row[labelKey] ?? "-")) : String(row[labelKey] ?? "-")}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="font-medium text-slate-700">{formatNumber(Number(row.orders ?? 0))} O.S</TableCell>
                  <TableCell className="font-semibold text-teal-700">{formatMoney(Number(row.estimated_payment ?? 0))}</TableCell>
                </TableRow>
              ))}
              {rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={3} className="py-6 text-center text-sm text-slate-500">
                    Nenhum dado para os filtros atuais.
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </div>
      ) : (
        <div className="border-t bg-slate-50/70 px-4 py-3 text-sm text-slate-500">Painel recolhido. Use a seta para abrir os itens do recorte atual.</div>
      )}
    </div>
  );
}

function buildFinancialBreakdownsFromOrders(
  orders: Array<{
    regional: string;
    group_name: string | null;
    os_type: string;
    os_subject: string;
    net_points: number;
    point_value: number;
    is_unscored: boolean;
  }>,
  health: Array<{ regional: string; multiplier: number }>,
  pointValue: number,
  estimatedUnmappedPoints: number
) {
  const healthMultiplier = new Map(health.map((item) => [normalizeRegional(item.regional), item.multiplier || 1]));
  const regionalTotals = new Map<string, FinancialBreakdownItem>();
  const groupTotals = new Map<string, FinancialBreakdownItem>();
  const unmappedTotals = new Map<string, FinancialBreakdownItem>();

  orders.forEach((order) => {
    const regional = normalizeRegional(order.regional);
    const multiplier = healthMultiplier.get(regional) ?? 1;
    const estimated = Number((order.net_points * multiplier * (order.point_value || pointValue)).toFixed(2));

    const regionalItem = regionalTotals.get(regional) ?? { regional, orders: 0, estimated_payment: 0 };
    regionalItem.orders += 1;
    regionalItem.estimated_payment = Number((regionalItem.estimated_payment + estimated).toFixed(2));
    regionalTotals.set(regional, regionalItem);

    const group = order.group_name || "Sem regra";
    const groupItem = groupTotals.get(group) ?? { group, orders: 0, net_points: 0, estimated_payment: 0 };
    groupItem.orders += 1;
    groupItem.net_points = Number(((groupItem.net_points ?? 0) + order.net_points).toFixed(2));
    groupItem.estimated_payment = Number((groupItem.estimated_payment + estimated).toFixed(2));
    groupTotals.set(group, groupItem);

    if (order.is_unscored) {
      const subjectKey = `${order.os_type} | ${order.os_subject}`;
      const subjectItem = unmappedTotals.get(subjectKey) ?? {
        os_type: order.os_type,
        os_subject: order.os_subject,
        orders: 0,
        estimated_payment: 0
      };
      subjectItem.orders += 1;
      subjectItem.estimated_payment = Number((subjectItem.estimated_payment + estimatedUnmappedPoints * pointValue).toFixed(2));
      unmappedTotals.set(subjectKey, subjectItem);
    }
  });

  const byInvestment = (a: FinancialBreakdownItem, b: FinancialBreakdownItem) => b.estimated_payment - a.estimated_payment;
  const byOrders = (a: FinancialBreakdownItem, b: FinancialBreakdownItem) => b.orders - a.orders;

  return {
    cost_by_regional: Array.from(regionalTotals.values()).sort(byInvestment),
    cost_by_group: Array.from(groupTotals.values()).sort(byInvestment),
    top_unmapped_subjects: Array.from(unmappedTotals.values()).sort(byOrders)
  };
}

function buildPenaltyDistributionFromOrders(
  orders: Array<{
    diagnosis_penalty_points: number;
    sla_penalty_points: number;
    recurrence_penalty_points: number;
    additional_penalty_points: number;
  }>
): PenaltyDistributionItem[] {
  const buckets = new Map<string, PenaltyDistributionItem>();
  const add = (name: string, value: number) => {
    const annulled = Math.abs(value);
    if (annulled <= 0) return;
    const current = buckets.get(name) ?? { name, value: 0, service_orders_count: 0 };
    buckets.set(name, {
      ...current,
      value: current.value + annulled,
      service_orders_count: current.service_orders_count + 1
    });
  };

  orders.forEach((order) => {
    add("Diagnóstico", order.diagnosis_penalty_points);
    add("SLA fora do prazo", order.sla_penalty_points);
    add("Reincidências", order.recurrence_penalty_points);
    add("Outros ajustes", order.additional_penalty_points);
  });

  return Array.from(buckets.values());
}

export default function GamificacaoPage() {
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [calculationRuns, setCalculationRuns] = useState<CalculationRunHistory[]>([]);
  const [groups, setGroups] = useState<ScoringGroup[]>([]);
  const [subjectRules, setSubjectRules] = useState<ScoringSubjectRule[]>([]);
  const [unmappedSubjects, setUnmappedSubjects] = useState<UnmappedSubject[]>([]);
  const [importedDiagnoses, setImportedDiagnoses] = useState<ImportedDiagnosis[]>([]);
  const [unmappedDiagnoses, setUnmappedDiagnoses] = useState<ImportedDiagnosis[]>([]);
  const [serviceOrders, setServiceOrders] = useState<ServiceOrder[]>([]);
  const [configSubjectSummaries, setConfigSubjectSummaries] = useState<ServiceOrderSubjectSummary[]>([]);
  const [collaboratorRegistry, setCollaboratorRegistry] = useState<CollaboratorRegistry>({ registered: [], unregistered: [] });
  const [leadershipProfiles, setLeadershipProfiles] = useState<LeadershipProfile[]>([]);
  const [leadershipRoleProfiles, setLeadershipRoleProfiles] = useState<LeadershipRoleProfile[]>([]);
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [recurrenceRules, setRecurrenceRules] = useState<RecurrenceClassificationRule[]>([]);
  const [healthRules, setHealthRules] = useState<HealthRule[]>([]);
  const [slaRules, setSlaRules] = useState<SlaPenaltyRule[]>([]);
  const [pointValue, setPointValue] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedScore, setSelectedScore] = useState<CollaboratorScore | null>(null);
  const [ordersOpen, setOrdersOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("closure");
  const [configTab, setConfigTab] = useState("rules");
  const [rankingTab, setRankingTab] = useState("collaborators");
  const [analysisPeriod, setAnalysisPeriod] = useState<AnalysisPeriod>({});
  const [selectedRegionals, setSelectedRegionals] = useState<string[]>([]);
  const [rankingSearch, setRankingSearch] = useState("");
  const [chartPenalties, setChartPenalties] = useState<PenaltyDistributionItem[]>([]);
  const [financialCollapsed, setFinancialCollapsed] = useState(true);
  const [filteredAuditOrders, setFilteredAuditOrders] = useState<Array<{
    regional: string;
    group_name: string | null;
    os_type: string;
    os_subject: string;
    net_points: number;
    point_value: number;
    is_unscored: boolean;
    diagnosis_penalty_points: number;
    sla_penalty_points: number;
    recurrence_penalty_points: number;
    additional_penalty_points: number;
  }> | null>(null);
  const [serviceOrdersLoaded, setServiceOrdersLoaded] = useState(false);
  const [pendingDataLoaded, setPendingDataLoaded] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [collaboratorRegistryLoaded, setCollaboratorRegistryLoaded] = useState(false);
  const [leadershipProfilesLoaded, setLeadershipProfilesLoaded] = useState(false);
  const [usersLoaded, setUsersLoaded] = useState(false);
  const [rulesSupportLoaded, setRulesSupportLoaded] = useState(false);
  const authBootstrapRef = useRef(false);
  const initialLoadRef = useRef(false);
  const [tabLoading, setTabLoading] = useState<Record<string, boolean>>({});

  const can = useCallback((permission: string) => Boolean(currentUser?.permissions.some((item) => item === permission)), [currentUser]);

  const setTabBusy = useCallback((key: string, value: boolean) => {
    setTabLoading((current) => ({ ...current, [key]: value }));
  }, []);

  const resetLazyData = useCallback(() => {
    setCalculationRuns([]);
    setServiceOrders([]);
    setCollaboratorRegistry({ registered: [], unregistered: [] });
    setLeadershipProfiles([]);
    setLeadershipRoleProfiles([]);
    setUsers([]);
    setConfigSubjectSummaries([]);
    setUnmappedSubjects([]);
    setImportedDiagnoses([]);
    setUnmappedDiagnoses([]);
    setServiceOrdersLoaded(false);
    setPendingDataLoaded(false);
    setHistoryLoaded(false);
    setCollaboratorRegistryLoaded(false);
    setLeadershipProfilesLoaded(false);
    setUsersLoaded(false);
    setRulesSupportLoaded(false);
  }, []);

  const loadServiceOrdersSupport = useCallback(async () => {
    if (serviceOrdersLoaded) return;
    setTabBusy("serviceOrders", true);
    try {
      const serviceOrderData = await api.serviceOrders();
      setServiceOrders(serviceOrderData);
      setServiceOrdersLoaded(true);
    } finally {
      setTabBusy("serviceOrders", false);
    }
  }, [serviceOrdersLoaded, setTabBusy]);

  const loadRulesConfigSupport = useCallback(async (runId?: number) => {
    if (rulesSupportLoaded) return;
    setTabBusy("configRules", true);
    try {
      const referenceMonth = summary?.run?.reference_month ?? analysisPeriod.reference_month;
      const referenceYear = summary?.run?.reference_year ?? analysisPeriod.reference_year;
      const referenceRegional = summary?.run?.regional ?? analysisPeriod.regional ?? undefined;
      if (!referenceMonth || !referenceYear) {
        throw new Error("Período analisado não identificado para carregar a configuração.");
      }
      const [groupData, subjectRuleData, recurrenceRuleData, slaData, healthData, settingsData, subjectSummaryData, importedDiagnosisData] = await Promise.all([
        api.scoringGroups(),
        api.scoringSubjectRules(),
        api.recurrenceClassificationRules(),
        api.slaPenaltyRules(),
        api.healthRules(),
        api.settings(),
        api.serviceOrderSubjectSummary({
          reference_month: referenceMonth,
          reference_year: referenceYear,
          regional: referenceRegional
        }),
        api.importedDiagnoses(runId)
      ]);
      setGroups(groupData);
      setSubjectRules(subjectRuleData);
      setRecurrenceRules(recurrenceRuleData);
      setSlaRules(slaData);
      setHealthRules(healthData);
      const pointSetting = settingsData.find((setting) => setting.key === "point_value");
      setPointValue(pointSetting?.value ?? String(summary?.point_value ?? ""));
      setConfigSubjectSummaries(subjectSummaryData);
      setImportedDiagnoses(importedDiagnosisData);
      setRulesSupportLoaded(true);
    } finally {
      setTabBusy("configRules", false);
    }
  }, [
    analysisPeriod.reference_month,
    analysisPeriod.reference_year,
    analysisPeriod.regional,
    rulesSupportLoaded,
    setTabBusy,
    summary?.run?.reference_month,
    summary?.run?.reference_year,
    summary?.run?.regional
  ]);

  const loadPendingData = useCallback(async (runId?: number) => {
    if (pendingDataLoaded) return;
    setTabBusy("pending", true);
    try {
      const [unmappedData, unmappedDiagnosisData] = await Promise.all([
        api.unmappedSubjects(runId),
        api.unmappedDiagnoses(runId)
      ]);
      setUnmappedSubjects(unmappedData);
      setUnmappedDiagnoses(unmappedDiagnosisData);
      setPendingDataLoaded(true);
    } finally {
      setTabBusy("pending", false);
    }
  }, [pendingDataLoaded, setTabBusy]);

  const loadHistoryData = useCallback(async () => {
    if (historyLoaded) return;
    setTabBusy("history", true);
    try {
      const calculationRunData = await api.calculationRuns();
      setCalculationRuns(calculationRunData);
      setHistoryLoaded(true);
    } finally {
      setTabBusy("history", false);
    }
  }, [historyLoaded, setTabBusy]);

  const loadCollaboratorRegistryData = useCallback(async () => {
    if (collaboratorRegistryLoaded) return;
    setTabBusy("collaborators", true);
    try {
      const collaboratorRegistryData = await api.collaboratorsRegistry();
      setCollaboratorRegistry(collaboratorRegistryData);
      setCollaboratorRegistryLoaded(true);
    } finally {
      setTabBusy("collaborators", false);
    }
  }, [collaboratorRegistryLoaded, setTabBusy]);

  const loadLeadershipProfilesData = useCallback(async () => {
    if (leadershipProfilesLoaded) return;
    setTabBusy("leadership", true);
    try {
      const [roleProfiles, leaders] = await Promise.all([api.leadershipRoleProfiles(), api.leadershipProfiles()]);
      setLeadershipRoleProfiles(roleProfiles);
      setLeadershipProfiles(leaders);
      setLeadershipProfilesLoaded(true);
    } finally {
      setTabBusy("leadership", false);
    }
  }, [leadershipProfilesLoaded, setTabBusy]);

  const loadUsersData = useCallback(async () => {
    if (!currentUser?.permissions.includes("users:manage") || usersLoaded) return;
    setTabBusy("users", true);
    try {
      setUsers(await api.users());
      setUsersLoaded(true);
    } finally {
      setTabBusy("users", false);
    }
  }, [currentUser?.permissions, setTabBusy, usersLoaded]);

  const refreshRulesConfigData = useCallback(async (runId?: number) => {
    const [groupData, subjectRuleData, recurrenceRuleData, slaData, healthData, settingsData] = await Promise.all([
      api.scoringGroups(),
      api.scoringSubjectRules(),
      api.recurrenceClassificationRules(),
      api.slaPenaltyRules(),
      api.healthRules(),
      api.settings()
    ]);
    setGroups(groupData);
    setSubjectRules(subjectRuleData);
    setRecurrenceRules(recurrenceRuleData);
    setSlaRules(slaData);
    setHealthRules(healthData);
    const pointSetting = settingsData.find((setting) => setting.key === "point_value");
    setPointValue(pointSetting?.value ?? "");

    if (rulesSupportLoaded) {
      const referenceMonth = summary?.run?.reference_month ?? analysisPeriod.reference_month;
      const referenceYear = summary?.run?.reference_year ?? analysisPeriod.reference_year;
      const referenceRegional = summary?.run?.regional ?? analysisPeriod.regional ?? undefined;
      if (!referenceMonth || !referenceYear) {
        throw new Error("Período analisado não identificado para atualizar a configuração.");
      }
      const [importedDiagnosisData, subjectSummaryData] = await Promise.all([
        api.importedDiagnoses(runId),
        api.serviceOrderSubjectSummary({
          reference_month: referenceMonth,
          reference_year: referenceYear,
          regional: referenceRegional
        })
      ]);
      setImportedDiagnoses(importedDiagnosisData);
      setConfigSubjectSummaries(subjectSummaryData);
    }
    if (pendingDataLoaded) {
      const [unmappedData, unmappedDiagnosisData] = await Promise.all([
        api.unmappedSubjects(runId),
        api.unmappedDiagnoses(runId)
      ]);
      setUnmappedSubjects(unmappedData);
      setUnmappedDiagnoses(unmappedDiagnosisData);
    }
  }, [
    analysisPeriod.reference_month,
    analysisPeriod.reference_year,
    analysisPeriod.regional,
    pendingDataLoaded,
    rulesSupportLoaded,
    summary?.run?.reference_month,
    summary?.run?.reference_year,
    summary?.run?.regional
  ]);

  const loadAll = useCallback(async (period: AnalysisPeriod = analysisPeriod) => {
    if (!currentUser) return;
    setError(null);
    resetLazyData();
    const summaryData = await api.summary(period);
    setSummary(summaryData);
    setPointValue(String(summaryData.point_value ?? ""));
    setLoading(false);

    Promise.all([api.scoringGroups(), api.settings()])
      .then(([groupData, settingsData]) => {
        setGroups(groupData);
        const pointSetting = settingsData.find((setting) => setting.key === "point_value");
        setPointValue(pointSetting?.value ?? String(summaryData.point_value ?? ""));
      })
      .catch((err: Error) => setError(err.message));
  }, [analysisPeriod, currentUser, resetLazyData]);

  useEffect(() => {
    if (authBootstrapRef.current) return;
    authBootstrapRef.current = true;
    api.me()
      .then((user) => setCurrentUser(user))
      .catch(() => {
        setAuthToken(null);
        setCurrentUser(null);
      })
      .finally(() => setAuthChecked(true));
  }, []);

  useEffect(() => {
    if (!authChecked || !currentUser) {
      setLoading(false);
      return;
    }
    if (initialLoadRef.current) return;
    initialLoadRef.current = true;
    setLoading(true);
    loadAll()
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [authChecked, currentUser, loadAll]);

  useEffect(() => {
    if (summary && loading) {
      setLoading(false);
    }
  }, [loading, summary]);

  useEffect(() => {
    if (!currentUser || !summary) return;

    if (activeTab === "ranking" || activeTab === "audit") {
      void loadServiceOrdersSupport().catch((err: Error) => setError(err.message));
      return;
    }

    if (activeTab === "pending") {
      void loadPendingData(summary.run?.id).catch((err: Error) => setError(err.message));
      return;
    }

    if (activeTab === "history") {
      void loadHistoryData().catch((err: Error) => setError(err.message));
      return;
    }

    if (activeTab === "config") {
      if (configTab === "rules") {
        void loadRulesConfigSupport(summary.run?.id).catch((err: Error) => setError(err.message));
        return;
      }
      if (configTab === "collaborators") {
        void loadCollaboratorRegistryData().catch((err: Error) => setError(err.message));
        return;
      }
      if (configTab === "leadership") {
        void loadLeadershipProfilesData().catch((err: Error) => setError(err.message));
        return;
      }
      if (configTab === "users") {
        void loadUsersData().catch((err: Error) => setError(err.message));
      }
    }
  }, [
    activeTab,
    configTab,
    currentUser,
    loadCollaboratorRegistryData,
    loadHistoryData,
    loadLeadershipProfilesData,
    loadPendingData,
    loadRulesConfigSupport,
    loadServiceOrdersSupport,
    loadUsersData,
    summary,
  ]);

  const closure = useMemo(() => {
    if (!summary) {
      return {
        ready: false,
        pendingCount: 0,
        pendingItems: []
      };
    }

    const pendingItems = [
      {
        label: "O.S sem regra de pontuação",
        value: summary.cards.unscored_service_orders,
        tab: "pending",
        help: "Assuntos importados que ainda não estão vinculados a um grupo."
      },
      {
        label: "Diagnósticos sem regra",
        value: summary.cards.diagnosis_unmapped_service_orders,
        tab: "pending",
        help: "Diagnósticos encontrados sem regra de liberação ou anulação."
      },
      {
        label: "Colaboradores pendentes de cadastro",
        value: summary.leadership_bonus?.pending_collaborators.length ?? 0,
        tab: "settings" as const,
        help: "Colaboradores com produção no período que ainda não estão formalmente cadastrados."
      }
    ];
    const pendingCount = pendingItems.reduce((total, item) => total + item.value, 0);

    return {
      ready: pendingCount === 0,
      pendingCount,
      pendingItems
    };
  }, [summary]);

  const closureFinancials = useMemo(() => {
    const technicianAmount = summary?.cards.estimated_payment ?? 0;
    const leadershipAmount = summary?.leadership_bonus?.total_bonus_amount ?? 0;
    return {
      technicianAmount,
      leadershipAmount,
      totalAmount: technicianAmount + leadershipAmount
    };
  }, [summary]);

  const regionalOptions = useMemo(() => {
    if (!summary) return [];
    return Array.from(new Set(summary.ranking.map((score) => normalizeRegional(score.regional)).filter(Boolean))).sort((a, b) =>
      a.localeCompare(b, "pt-BR")
    );
  }, [summary]);

  const collaboratorRegionalOptions = useMemo(() => {
    const values = [
      ...regionalOptions,
      ...serviceOrders.map((order) => order.regional),
    ];
    return Array.from(
      new Set(
        values
          .map((value) => normalizeRegional(value))
          .filter((value) => value && value !== "NAO IDENTIFICADO" && value !== "0" && value !== "1")
      )
    ).sort((a, b) =>
      a.localeCompare(b, "pt-BR")
    );
  }, [regionalOptions, serviceOrders]);

  const periodServiceOrders = useMemo(() => {
    const month = summary?.run?.reference_month;
    const year = summary?.run?.reference_year;
    if (!month || !year) return serviceOrders;
    return serviceOrders.filter((order) => {
      const dateValue = order.closed_at ?? order.opened_at;
      if (!dateValue) return false;
      const orderDate = new Date(dateValue);
      if (Number.isNaN(orderDate.getTime())) return false;
      return orderDate.getMonth() + 1 === month && orderDate.getFullYear() === year;
    });
  }, [serviceOrders, summary?.run?.reference_month, summary?.run?.reference_year]);

  const auditCollaboratorOptions = useMemo(() => {
    if (!summary) return [];
    return summary.ranking
      .map((score) => ({
        id: score.collaborator_id,
        name: score.collaborator_name,
        regional: score.regional
      }))
      .sort((a, b) => a.name.localeCompare(b.name, "pt-BR"));
  }, [summary]);

  const auditSubjectOptions = useMemo(() => {
    return Array.from(new Set(periodServiceOrders.map((order) => order.os_subject).filter(Boolean))).sort((a, b) =>
      a.localeCompare(b, "pt-BR")
    );
  }, [periodServiceOrders]);

  const filteredRanking = useMemo(() => {
    if (!summary) return [];
    const search = rankingSearch.trim().toLowerCase();
    return summary.ranking.filter((score) => {
      const matchesRegional = selectedRegionals.length === 0 || selectedRegionals.includes(normalizeRegional(score.regional));
      const matchesSearch = !search || score.collaborator_name.toLowerCase().includes(search);
      return matchesRegional && matchesSearch;
    });
  }, [rankingSearch, selectedRegionals, summary]);

  const filteredLeadershipResults = useMemo(() => {
    if (!summary) return [];
    return (summary.leadership_bonus?.results ?? []).filter((item) => {
      return selectedRegionals.length === 0 || item.regionals.some((regional) => selectedRegionals.includes(normalizeRegional(regional)));
    });
  }, [selectedRegionals, summary]);

  const leadershipCoveredRegionals = useMemo(() => {
    return Array.from(
      new Set(filteredLeadershipResults.flatMap((item) => item.regionals.map((regional) => normalizeRegional(regional)).filter(Boolean)))
    ).length;
  }, [filteredLeadershipResults]);

  const rankingScope = useMemo(() => {
    if (!summary) return [];
    return summary.ranking.filter((score) => {
      return selectedRegionals.length === 0 || selectedRegionals.includes(normalizeRegional(score.regional));
    });
  }, [selectedRegionals, summary]);

  const rankingPeriodTotalOrders = useMemo(() => {
    if (!summary) return 0;
    if (selectedRegionals.length === 0) {
      return summary.cards.total_service_orders ?? 0;
    }
    return summary.health_by_regional
      .filter((item) => selectedRegionals.includes(normalizeRegional(item.regional)))
      .reduce((total, item) => total + (item.total_orders ?? 0), 0);
  }, [selectedRegionals, summary]);

  const rankingScopeTotals = useMemo(
    () => ({
      serviceOrders: rankingScope.reduce((total, score) => total + score.service_orders_count, 0),
      scored: rankingScope.reduce((total, score) => total + score.scored_service_orders, 0),
      unscored: rankingScope.reduce((total, score) => total + score.unscored_service_orders, 0),
      annulled: rankingScope.reduce((total, score) => total + score.annulled_service_orders, 0),
      estimated: rankingScope.reduce((total, score) => total + score.estimated_payment, 0)
    }),
    [rankingScope]
  );

  const outsideRankingCount = Math.max(rankingPeriodTotalOrders - rankingScopeTotals.serviceOrders, 0);
  const chartHealth = useMemo(() => {
    if (!summary) return [];
    return selectedRegionals.length > 0
      ? summary.health_by_regional.filter((item) => selectedRegionals.includes(normalizeRegional(item.regional)))
      : summary.health_by_regional;
  }, [selectedRegionals, summary]);
  const chartContext = useMemo(() => {
    const serviceOrders = chartHealth.reduce((total, item) => total + item.total_orders, 0);
    const recurrenceOrders = chartHealth.reduce((total, item) => total + (item.recurrence_orders ?? 0), 0);
    const recurrenceRate = serviceOrders > 0 ? (recurrenceOrders / serviceOrders) * 100 : 0;
    return {
      serviceOrders,
      recurrenceOrders,
      recurrenceRate,
      collaborators: filteredRanking.length,
      label:
        selectedRegionals.length === 0
          ? "Todas as regionais"
          : selectedRegionals.length === 1
            ? regionalName(selectedRegionals[0])
            : `${selectedRegionals.length} regionais`
    };
  }, [chartHealth, filteredRanking.length, selectedRegionals]);

  const filteredFinancials = useMemo(() => {
    if (!summary) {
      return {
        cost_by_regional: [],
        cost_by_group: [],
        top_unmapped_subjects: []
      };
    }
    if (!filteredAuditOrders) {
      return {
        cost_by_regional: summary.cost_by_regional,
        cost_by_group: summary.cost_by_group,
        top_unmapped_subjects: summary.top_unmapped_subjects
      };
    }

    const activeGroups = groups.filter((group) => group.active);
    const estimatedUnmappedPoints =
      activeGroups.length > 0
        ? activeGroups.reduce((total, group) => total + Number(group.default_points ?? 0), 0) / activeGroups.length
        : 0;

    return buildFinancialBreakdownsFromOrders(
      filteredAuditOrders,
      chartHealth,
      summary.run?.point_value ?? summary.point_value,
      estimatedUnmappedPoints
    );
  }, [chartHealth, filteredAuditOrders, groups, summary]);

  useEffect(() => {
    if (!summary) {
      setChartPenalties([]);
      setFilteredAuditOrders(null);
      return;
    }
    if (selectedRegionals.length === 0 || !summary.run?.id) {
      setChartPenalties(summary.penalty_distribution);
      setFilteredAuditOrders(null);
      return;
    }

    let cancelled = false;
    Promise.all(
      selectedRegionals.map((regional) =>
        api.auditOrders({
          calculation_run_id: summary.run?.id,
          regional
        })
      )
    )
      .then((responses) => {
        if (cancelled) return;
        const orders = responses.flatMap((response) => response.orders);
        setFilteredAuditOrders(orders);
        setChartPenalties(buildPenaltyDistributionFromOrders(orders));
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setError(err.message);
          setChartPenalties(summary.penalty_distribution);
          setFilteredAuditOrders(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedRegionals, summary]);

  function updateSelectedRegionals(values: string[]) {
    setSelectedRegionals(values.map((value) => normalizeRegional(value)).filter(Boolean));
  }

  async function withFeedback(action: () => Promise<void>, success: string) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await action();
      setMessage(success);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro inesperado.");
    } finally {
      setBusy(false);
    }
  }

  async function recalculate() {
    await withFeedback(async () => {
      const value = parseOptionalNumber(pointValue);
      if (value !== null) {
        await api.updateSetting("point_value", value.toFixed(2));
      }
      await api.calculate(value, {
        reference_month: summary?.run?.reference_month,
        reference_year: summary?.run?.reference_year,
        regional: summary?.run?.regional
      });
      await loadAll();
    }, "Pontuação recalculada com matriz operacional.");
  }

  async function refreshAfterCollaboratorRegistryChange() {
    if (summary?.run) {
      await api.calculate(summary.run.point_value ?? summary.point_value, {
        reference_month: summary.run.reference_month,
        reference_year: summary.run.reference_year,
        regional: summary.run.regional
      });
    }
    await loadAll();
  }

  async function calculatePeriod(month: number, year: number) {
    await withFeedback(async () => {
      const value = parseOptionalNumber(pointValue);
      if (value !== null) {
        await api.updateSetting("point_value", value.toFixed(2));
      }
      await api.calculate(value, {
        reference_month: month,
        reference_year: year,
        regional: summary?.run?.regional
      });
      const period = { reference_month: month, reference_year: year, regional: summary?.run?.regional };
      setAnalysisPeriod(period);
      await loadAll(period);
    }, "Período recalculado com janela de reincidência.");
  }

  async function viewPeriod(month: number, year: number) {
    await withFeedback(async () => {
      const period = { reference_month: month, reference_year: year, regional: summary?.run?.regional };
      setAnalysisPeriod(period);
      await loadAll(period);
    }, "Período de análise alterado.");
  }

  function exportPaymentCsv() {
    if (!summary || currentUser?.role === "viewer") return;
    const paymentRows = summary.ranking.filter((score) => {
      const matchesRegional = selectedRegionals.length === 0 || selectedRegionals.includes(normalizeRegional(score.regional));
      return matchesRegional && score.is_registered !== false;
    });
    const leadershipRows = (summary.leadership_bonus?.results ?? []).filter((item) => {
      return selectedRegionals.length === 0 || item.regionals.some((regional) => selectedRegionals.includes(normalizeRegional(regional)));
    });
    const pendingRows = (summary.leadership_bonus?.pending_collaborators ?? []).filter((item) => {
      return selectedRegionals.length === 0 || selectedRegionals.includes(normalizeRegional(item.suggested_regional || item.regional));
    });
    const rows = [
      ["Pagamento de técnicos"],
      ["Colaborador", "Filial", "Tipo", "Valor a ser pago"],
      ...paymentRows.map((score) => [
        score.collaborator_name,
        regionalName(score.regional),
        "Técnico",
        formatMoney(score.estimated_payment)
      ]),
      [],
      ["Bonificação de liderança"],
      ["Liderança", "Filiais", "Tipo", "Média final", "Multiplicador", "Valor a ser pago"],
      ...leadershipRows.map((item) => [
        item.name,
        item.regionals.map((regional) => regionalName(regional)).join(", "),
        leadershipRoleLabel(item.role_type),
        `${formatNumber(item.average_final_points)} pts`,
        `${formatNumber(item.multiplier)}x`,
        formatMoney(item.bonus_amount)
      ]),
      [],
      ["Pendentes de cadastro"],
      ["Nome identificado", "Filial sugerida", "O.S", "Valor potencial", "Status"],
      ...pendingRows.map((item) => [
        item.name,
        regionalName(item.suggested_regional || item.regional),
        `${formatNumber(item.service_orders_count)} O.S`,
        formatMoney(item.estimated_payment),
        "Pendente de cadastro"
      ])
    ];
    const csv = rows
      .map((row) => row.map((value) => `"${String(value).replace(/"/g, '""')}"`).join(";"))
      .join("\r\n");
    const blob = new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `pagamentos-gamificação-${summary.run?.reference_month ?? "período"}-${summary.run?.reference_year ?? "atual"}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  async function login() {
    setBusy(true);
    setError(null);
    try {
      const result = await api.login(loginEmail, loginPassword);
      setAuthToken(result.access_token);
      setCurrentUser(result.user);
      setLoginPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível entrar.");
    } finally {
      setBusy(false);
    }
  }

  function logout() {
    setAuthToken(null);
    setCurrentUser(null);
    setSummary(null);
    setActiveTab("closure");
  }

  if (!authChecked) {
    return <main className="h-dvh bg-slate-50 p-6 text-sm text-slate-500">Verificando acesso...</main>;
  }

  if (!currentUser) {
    return (
      <main className="flex min-h-dvh items-center justify-center bg-slate-50 px-4 py-8">
        <section className="w-full max-w-md rounded-2xl border border-slate-200 bg-white px-6 py-8 shadow-xl shadow-slate-200/70 sm:px-8">
          <div className="flex flex-col items-center text-center">
            <img src="/brand/uni-logo.png" alt="UNI Internet" className="h-16 w-auto object-contain" />
            <h1 className="mt-6 text-2xl font-semibold tracking-normal text-slate-950">Gamificação UNI OPR</h1>
            <p className="mt-2 text-sm text-slate-500">Acesse sua conta para continuar.</p>
          </div>

          <div className="mt-8 grid gap-4">
            <label className="grid gap-2 text-sm font-medium text-slate-700">
              E-mail
              <div className="relative">
                <Mail className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-400" />
                <Input
                  placeholder="Digite seu e-mail"
                  value={loginEmail}
                  onChange={(event) => setLoginEmail(event.target.value)}
                  className="h-11 rounded-lg border-slate-200 bg-slate-50 pl-10 shadow-sm transition focus-visible:bg-white focus-visible:ring-teal-500"
                />
              </div>
            </label>
            <label className="grid gap-2 text-sm font-medium text-slate-700">
              Senha
              <div className="relative">
                <LockKeyhole className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-400" />
                <Input
                  placeholder="Digite sua senha"
                  type="password"
                  value={loginPassword}
                  onChange={(event) => setLoginPassword(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") void login();
                  }}
                  className="h-11 rounded-lg border-slate-200 bg-slate-50 pl-10 shadow-sm transition focus-visible:bg-white focus-visible:ring-teal-500"
                />
              </div>
            </label>
            {error ? (
              <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
                {error}
              </div>
            ) : null}
            <Button
              onClick={login}
              disabled={busy || !loginEmail.trim() || !loginPassword.trim()}
              className="h-11 rounded-lg bg-teal-600 font-semibold shadow-sm transition hover:bg-teal-700 disabled:bg-slate-300"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {busy ? "Entrando..." : "Entrar"}
            </Button>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-dvh bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.12),transparent_24%),radial-gradient(circle_at_top_right,rgba(37,99,235,0.08),transparent_20%),linear-gradient(180deg,#f8fbff_0%,#f8fafc_42%,#f8fafc_100%)]">
      <div className="mx-auto flex min-h-dvh w-full max-w-[1680px] flex-col gap-4 px-2 py-3 sm:px-4">
        <header className="relative overflow-hidden rounded-[28px] border border-slate-200/80 bg-white/95 shadow-[0_18px_60px_-32px_rgba(15,23,42,0.35)] backdrop-blur">
          <div className="absolute inset-x-0 top-0 h-1.5 bg-gradient-to-r from-cyan-400 via-teal-400 to-blue-600" />
          <div className="absolute -left-10 top-10 h-40 w-40 rounded-full bg-cyan-100/40 blur-3xl" />
          <div className="absolute right-0 top-0 h-48 w-48 rounded-full bg-blue-100/40 blur-3xl" />

          <div className="relative grid gap-4 px-5 py-4 xl:grid-cols-[minmax(0,1fr)_minmax(320px,400px)] xl:items-center">
            <div className="flex min-w-0 items-start gap-4">
              <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl border border-slate-200/80 bg-white shadow-[0_12px_28px_-20px_rgba(15,23,42,0.55)]">
                <img src="/brand/uni-logo.png" alt="UNI Internet" className="max-h-9 w-auto object-contain" />
              </div>

              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                  <span>UNI Workspace</span>
                  <span className="h-1 w-1 rounded-full bg-slate-300" />
                  <span>Operação</span>
                  <Badge className="border-emerald-200 bg-emerald-50 text-emerald-700">Módulo ativo</Badge>
                </div>

                <div className="mt-2.5 flex flex-wrap items-center gap-3">
                  <h1 className="text-[32px] font-semibold leading-none tracking-tight text-slate-950">Gamificação Operacional</h1>
                  <span className="rounded-full border border-cyan-200 bg-cyan-50 px-3 py-1 text-xs font-medium text-cyan-700">Fechamento e auditoria</span>
                </div>

                <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                  Camada operacional da UNI para fechamento, auditoria, valor a ser pago e governança da apuração.
                </p>
              </div>
            </div>

            <div className="grid gap-3">
              <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-4 shadow-sm">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Ambiente</div>
                    <div className="mt-1 truncate text-base font-semibold text-slate-950">{currentUser.name}</div>
                    <div className="mt-1 text-[11px] uppercase tracking-[0.14em] text-slate-500">{currentUser.role}</div>
                  </div>
                  <div className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[11px] font-semibold text-emerald-700">
                    Sessão ativa
                  </div>
                </div>
              </div>

              <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
                {can("calculation:run") ? (
                  <Button onClick={recalculate} disabled={busy || loading} className="h-11 w-full rounded-2xl bg-teal-600 px-4 shadow-sm hover:bg-teal-700 sm:w-auto">
                    <RefreshCw className={busy ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
                    Recalcular pontuação
                  </Button>
                ) : null}
                <Button type="button" variant="outline" onClick={logout} className="h-11 rounded-2xl border-slate-300 bg-white px-4">
                  Sair
                </Button>
              </div>
            </div>
          </div>
        </header>

        {error ? (
          <div className="rounded-2xl border border-red-200 bg-[linear-gradient(180deg,#fff5f5_0%,#fef2f2_100%)] px-4 py-3 text-sm text-red-700 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
            <div className="flex items-start gap-3">
              <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-white text-red-600 shadow-sm">
                <AlertTriangle className="h-4 w-4" />
              </div>
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-red-500">Atenção</div>
                <div className="mt-1 text-sm font-medium text-red-700">{error}</div>
              </div>
            </div>
          </div>
        ) : null}
        {message ? (
          <div className="rounded-2xl border border-emerald-200 bg-[linear-gradient(180deg,#f0fdf9_0%,#ecfdf5_100%)] px-4 py-3 text-sm text-emerald-700 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
            <div className="flex items-start gap-3">
              <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-white text-emerald-600 shadow-sm">
                <CheckCircle2 className="h-4 w-4" />
              </div>
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-emerald-600">Atualização concluída</div>
                <div className="mt-1 text-sm font-medium text-emerald-700">{message}</div>
              </div>
            </div>
          </div>
        ) : null}

        {loading || !summary ? (
          <section className="overflow-hidden rounded-[24px] border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
            <div className="border-b bg-[linear-gradient(180deg,#ffffff_0%,#f8fbff_100%)] px-5 py-5">
              <div className="flex flex-col gap-2">
                <div className="h-3 w-32 animate-pulse rounded-full bg-slate-200" />
                <div className="h-8 w-80 max-w-full animate-pulse rounded-full bg-slate-200" />
                <div className="h-4 w-[420px] max-w-full animate-pulse rounded-full bg-slate-100" />
              </div>
            </div>

            <div className="grid gap-4 p-5">
              <div className="grid gap-3 lg:grid-cols-3">
                {[0, 1, 2].map((item) => (
                  <div key={item} className="rounded-[22px] border border-slate-200 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
                    <div className="h-3 w-24 animate-pulse rounded-full bg-slate-200" />
                    <div className="mt-4 h-9 w-40 animate-pulse rounded-full bg-slate-200" />
                    <div className="mt-3 h-4 w-48 animate-pulse rounded-full bg-slate-100" />
                  </div>
                ))}
              </div>

              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {[0, 1, 2, 3].map((item) => (
                  <div key={item} className="rounded-[20px] border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
                    <div className="h-3 w-20 animate-pulse rounded-full bg-slate-200" />
                    <div className="mt-4 h-8 w-28 animate-pulse rounded-full bg-slate-200" />
                  </div>
                ))}
              </div>

              <div className="rounded-[20px] border border-dashed border-slate-200 bg-slate-50/70 px-4 py-4 text-sm text-slate-500">
                Carregando motor de remuneração...
              </div>
            </div>
          </section>
        ) : (
          <Tabs value={activeTab} onValueChange={setActiveTab} className="flex flex-1 flex-col gap-3">
            <section className="rounded-2xl border border-slate-200/80 bg-white/90 p-3 shadow-sm backdrop-blur">
              <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
                <div className="min-w-0">
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Navegação do módulo</div>
                  <div className="mt-1 flex items-center gap-2 text-sm text-slate-600">
                    <span>{activeTab === "closure" ? "Fechamento" : activeTab === "ranking" ? "Ranking" : activeTab === "pending" ? "Pendências" : activeTab === "config" ? "Configuração" : activeTab === "audit" ? "Auditoria" : activeTab === "history" ? "Histórico" : "Período"}</span>
                    <InfoHint
                      ariaLabel={`Ajuda sobre a aba ${activeTab === "closure" ? "Fechamento" : activeTab === "ranking" ? "Ranking" : activeTab === "pending" ? "Pendências" : activeTab === "config" ? "Configuração" : activeTab === "audit" ? "Auditoria" : activeTab === "history" ? "Histórico" : "Período"}`}
                      description={TAB_HELP[activeTab] ?? TAB_HELP.closure}
                      side="bottom"
                    />
                  </div>
                </div>
                <Badge className="w-fit border-slate-200 bg-slate-50 text-slate-700">
                  {activeTab === "closure"
                    ? "Visão executiva"
                    : activeTab === "ranking"
                      ? "Ranking operacional"
                      : activeTab === "pending"
                        ? "Pendências de regra"
                        : activeTab === "config"
                          ? "Governança"
                          : activeTab === "audit"
                            ? "Rastreabilidade"
                            : activeTab === "history"
                              ? "Histórico"
                              : "Período analisado"}
                </Badge>
              </div>
              <TabsList className="mt-3 flex h-auto w-full justify-start gap-2 overflow-x-auto rounded-2xl border border-slate-200 bg-slate-50/80 p-2">
                <TabsTrigger value="closure" className="h-10 rounded-xl border border-transparent px-4 text-sm font-semibold text-slate-600 data-[state=active]:border-emerald-200 data-[state=active]:bg-emerald-50 data-[state=active]:text-emerald-800 data-[state=active]:shadow-none">
                  Fechamento
                </TabsTrigger>
                <TabsTrigger value="ranking" className="h-10 rounded-xl border border-transparent px-4 text-sm font-semibold text-slate-600 data-[state=active]:border-emerald-200 data-[state=active]:bg-emerald-50 data-[state=active]:text-emerald-800 data-[state=active]:shadow-none">
                  Ranking
                </TabsTrigger>
                {can("orders:import") || can("scoring:write") ? (
                  <TabsTrigger value="pending" className="h-10 rounded-xl border border-transparent px-4 text-sm font-semibold text-slate-600 data-[state=active]:border-emerald-200 data-[state=active]:bg-emerald-50 data-[state=active]:text-emerald-800 data-[state=active]:shadow-none">
                    Pendências
                  </TabsTrigger>
                ) : null}
                {can("scoring:write") ? (
                  <TabsTrigger value="config" className="h-10 rounded-xl border border-transparent px-4 text-sm font-semibold text-slate-600 data-[state=active]:border-emerald-200 data-[state=active]:bg-emerald-50 data-[state=active]:text-emerald-800 data-[state=active]:shadow-none">
                    Configuração
                  </TabsTrigger>
                ) : null}
                <TabsTrigger value="audit" className="h-10 rounded-xl border border-transparent px-4 text-sm font-semibold text-slate-600 data-[state=active]:border-emerald-200 data-[state=active]:bg-emerald-50 data-[state=active]:text-emerald-800 data-[state=active]:shadow-none">
                  Auditoria
                </TabsTrigger>
                <TabsTrigger value="history" className="h-10 rounded-xl border border-transparent px-4 text-sm font-semibold text-slate-600 data-[state=active]:border-emerald-200 data-[state=active]:bg-emerald-50 data-[state=active]:text-emerald-800 data-[state=active]:shadow-none">
                  Histórico
                </TabsTrigger>
                <TabsTrigger value="import" className="h-10 rounded-xl border border-transparent px-4 text-sm font-semibold text-slate-600 data-[state=active]:border-emerald-200 data-[state=active]:bg-emerald-50 data-[state=active]:text-emerald-800 data-[state=active]:shadow-none">
                  Período
                </TabsTrigger>
              </TabsList>
            </section>

            <TabsContent value="closure" className="mt-0 flex-1 pr-1">
              {activeTab === "closure" ? (
                <div className="grid gap-4">
                  <section
                    className={
                      closure.ready
                        ? "overflow-hidden rounded-[24px] border border-slate-200/80 bg-white shadow-sm"
                        : "overflow-hidden rounded-[24px] border border-slate-200/80 bg-white shadow-sm"
                    }
                  >
                    <div
                      className={
                        closure.ready
                          ? "grid gap-5 bg-[radial-gradient(circle_at_top_left,rgba(16,185,129,0.08),transparent_22%),linear-gradient(180deg,#ffffff_0%,#fbfdff_100%)] p-5"
                          : "grid gap-5 bg-[radial-gradient(circle_at_top_left,rgba(245,158,11,0.08),transparent_22%),linear-gradient(180deg,#ffffff_0%,#fbfdff_100%)] p-5"
                      }
                    >
                      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge
                              className={
                                closure.ready
                                  ? "w-fit border-emerald-200 bg-white text-emerald-700"
                                  : "w-fit border-amber-200 bg-white text-amber-700"
                              }
                            >
                              {closure.ready ? <CheckCircle2 className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
                              {closure.ready ? "Fechamento liberado" : "Fechamento com pendência"}
                            </Badge>
                            <Badge className="w-fit border-slate-200 bg-white text-slate-700">
                              <CalendarDays className="h-3.5 w-3.5" />
                              {summary.run ? `${summary.run.reference_month}/${summary.run.reference_year}` : "Sem cálculo"}
                            </Badge>
                          </div>
                          <div className="mt-3 flex items-center gap-2">
                            <h2 className="text-2xl font-semibold leading-tight text-slate-950">
                              {closure.ready ? "Resumo financeiro da competência" : "Regras pendentes antes do pagamento"}
                            </h2>
                            <InfoHint
                              ariaLabel={`Ajuda sobre ${closure.ready ? "Resumo financeiro da competência" : "Regras pendentes antes do pagamento"}`}
                              description={SECTION_HELP.summary}
                            />
                          </div>
                        </div>
                        {currentUser.role !== "viewer" ? (
                          <Button type="button" variant="outline" onClick={exportPaymentCsv} className="w-full bg-white sm:w-auto">
                            <Download className="h-4 w-4" />
                            Exportar pagamento
                          </Button>
                        ) : null}
                      </div>

                      <div className="grid gap-3 lg:grid-cols-3">
                        {[
                          {
                            label: "Técnicos",
                            value: formatMoney(closureFinancials.technicianAmount),
                            help: "Valor a ser pago aos colaboradores técnicos",
                            icon: UsersRound,
                            tone: "text-teal-700",
                            className: "border-slate-200 bg-white"
                          },
                          {
                            label: "Liderança",
                            value: formatMoney(closureFinancials.leadershipAmount),
                            help: "Bonificação sobre as filiais vinculadas",
                            icon: Trophy,
                            tone: "text-blue-700",
                            className: "border-slate-200 bg-white"
                          },
                          {
                            label: "Total a pagar",
                            value: formatMoney(closureFinancials.totalAmount),
                            help: "Técnicos + liderança",
                            icon: CircleDollarSign,
                            tone: "text-slate-950",
                            className: "border-slate-900/10 bg-[linear-gradient(135deg,#0f172a_0%,#111827_65%,#0b1220_100%)] text-white shadow-[0_18px_40px_-24px_rgba(2,6,23,0.9)]"
                          }
                        ].map((item) => {
                          const Icon = item.icon;
                          const isTotal = item.label === "Total a pagar";
                          return (
                            <div key={item.label} className={`min-w-0 rounded-[22px] border p-5 shadow-[0_1px_2px_rgba(15,23,42,0.04)] ${item.className}`}>
                              <div className={`flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] ${isTotal ? "text-slate-300" : "text-slate-500"}`}>
                                <Icon className="h-4 w-4" />
                                <span className="truncate">{item.label}</span>
                              </div>
                              <div className={`mt-3 truncate text-[32px] font-semibold leading-none ${isTotal ? "text-white" : item.tone}`}>{item.value}</div>
                              <div className={`mt-2 text-sm ${isTotal ? "text-slate-300" : "text-slate-500"}`}>{item.help}</div>
                              {isTotal ? (
                                <div className="mt-4 inline-flex w-fit rounded-full border border-emerald-400/20 bg-emerald-400/10 px-2.5 py-1 text-[11px] font-medium text-emerald-200">
                                  Pronto para exportação
                                </div>
                              ) : (
                                <div className="mt-4 h-px w-full bg-slate-100" />
                              )}
                            </div>
                          );
                        })}
                      </div>

                      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                        {[
                          {
                            label: "Total de O.S",
                            value: `${formatNumber(summary.cards.total_service_orders)} O.S`,
                            icon: ClipboardList,
                            tone: "text-slate-800"
                          },
                          {
                            label: "Regras pendentes",
                            value: `${formatNumber(closure.pendingCount)} item(ns)`,
                            icon: AlertTriangle,
                            tone: closure.pendingCount > 0 ? "text-amber-700" : "text-emerald-700"
                          },
                          {
                            label: "Pontos finais",
                            value: formatPoints(summary.cards.final_points),
                            icon: BarChart3,
                            tone: "text-blue-700"
                          },
                          {
                            label: "Pontos anulados",
                            value: `${formatNumber(summary.cards.penalty_points)} pts anulados`,
                            icon: AlertTriangle,
                            tone: summary.cards.penalty_points > 0 ? "text-red-700" : "text-slate-700"
                          }
                        ].map((item) => {
                          const Icon = item.icon;
                          return (
                            <div key={item.label} className="min-w-0 rounded-[20px] border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
                              <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                                <Icon className="h-3.5 w-3.5" />
                                <span className="truncate">{item.label}</span>
                              </div>
                              <div className={`mt-3 truncate text-[28px] font-semibold leading-none ${item.tone}`}>{item.value}</div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </section>

                  <section className="overflow-hidden rounded-[24px] border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
                    <div className="border-b bg-[linear-gradient(180deg,#ffffff_0%,#f8fbff_100%)] px-5 py-5">
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                          <div>
                            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Conferência detalhada</div>
                          <div className="mt-1 flex items-center gap-2">
                            <h2 className="text-[22px] font-semibold leading-tight text-slate-950">Detalhamento do fechamento</h2>
                            <InfoHint ariaLabel="Ajuda sobre Detalhamento do fechamento" description={SECTION_HELP.details} />
                          </div>
                        </div>
                        <div className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-[11px] font-medium text-slate-600">
                          O resumo executivo acima continua como referência principal da competência.
                        </div>
                      </div>
                    </div>

                    <Accordion className="gap-0 bg-white">
                      <AccordionItem value="closure-pending" defaultOpen={closure.pendingCount > 0} className="rounded-none border-0 border-b">
                        <AccordionTrigger asChild>
                          <button
                            type="button"
                            className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left transition hover:bg-slate-50/80"
                          >
                            <div className="flex min-w-0 items-start gap-3">
                              <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-amber-50 text-amber-700">
                                <AlertTriangle className="h-4 w-4" />
                              </div>
                              <div className="min-w-0">
                                <div className="flex items-center gap-2">
                                  <div className="text-sm font-semibold text-slate-950">Alertas e pendências</div>
                                  <InfoHint ariaLabel="Ajuda sobre Alertas e pendências" description={SECTION_HELP.alerts} />
                                </div>
                              </div>
                            </div>
                            <Badge className={closure.pendingCount > 0 ? "border-amber-200 bg-amber-50 text-amber-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}>
                              {closure.pendingCount > 0 ? `${formatNumber(closure.pendingCount)} pendência(s)` : "Sem pendências"}
                            </Badge>
                          </button>
                        </AccordionTrigger>
                        <AccordionContent className="px-5 pb-5">
                          {closure.pendingCount > 0 ? (
                            <div className="grid gap-3 rounded-[20px] border border-slate-200 bg-slate-50/60 p-3 md:grid-cols-2">
                              {closure.pendingItems.map((item) => (
                                <button
                                  key={item.label}
                                  className="rounded-[18px] border border-slate-200 bg-white p-4 text-left shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition hover:border-teal-300 hover:bg-teal-50/40"
                                  onClick={() => setActiveTab(item.tab)}
                                >
                                  <div className={item.value > 0 ? "text-2xl font-semibold text-amber-700" : "text-2xl font-semibold text-emerald-700"}>
                                    {formatNumber(item.value)}
                                  </div>
                                  <div className="mt-1 text-sm font-semibold text-slate-950">{item.label}</div>
                                  <div className="mt-2 text-xs text-slate-500">{item.help}</div>
                                </button>
                              ))}
                            </div>
                          ) : (
                            <div className="flex items-center gap-3 rounded-lg border bg-emerald-50/60 px-4 py-4 text-sm text-slate-700">
                              <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                              Todas as O.S do período possuem regra de assunto ou diagnóstico aplicada.
                            </div>
                          )}
                        </AccordionContent>
                      </AccordionItem>

                      <AccordionItem value="closure-leadership" className="rounded-none border-0 border-b">
                        <AccordionTrigger asChild>
                          <button
                            type="button"
                            className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left transition hover:bg-slate-50/80"
                          >
                            <div className="flex min-w-0 items-start gap-3">
                              <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-blue-50 text-blue-700">
                                <Trophy className="h-4 w-4" />
                              </div>
                              <div className="min-w-0">
                                <div className="flex items-center gap-2">
                                  <div className="text-sm font-semibold text-slate-950">Bonificação de liderança</div>
                                  <InfoHint ariaLabel="Ajuda sobre Bonificação de liderança" description={SECTION_HELP.leadership} />
                                </div>
                              </div>
                            </div>
                            <Badge className="border-blue-200 bg-blue-50 text-blue-700">{formatMoney(summary.leadership_bonus?.total_bonus_amount ?? 0)}</Badge>
                          </button>
                        </AccordionTrigger>
                        <AccordionContent className="px-5 pb-5">
                          <div className="grid gap-3 rounded-[20px] border border-slate-200 bg-slate-50/60 p-3 md:grid-cols-3">
                            {[
                              ["Valor da liderança", formatMoney(summary.leadership_bonus?.total_bonus_amount ?? 0)],
                              ["Perfis ativos", `${formatNumber(summary.leadership_bonus?.results.length ?? 0)} líder(es)`],
                              ["Filiais cobertas", `${formatNumber(leadershipCoveredRegionals)} filial(is)`]
                            ].map(([label, value]) => (
                              <div key={label} className="rounded-[18px] border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
                                <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">{label}</div>
                                <div className="mt-2 text-xl font-semibold text-slate-950">{value}</div>
                              </div>
                            ))}
                          </div>
                          <div className="mt-4 flex flex-col gap-3 rounded-[20px] border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)] sm:flex-row sm:items-center sm:justify-between">
                            <div>
                              <div className="text-sm font-semibold text-slate-950">Ranking de liderança separado do fechamento</div>
                              <p className="mt-1 text-sm text-slate-500">
                                A lista detalhada de líderes agora fica na aba Ranking, em uma visão própria para comparação e conferência.
                              </p>
                            </div>
                            <Button
                              type="button"
                              variant="outline"
                              className="rounded-xl border-slate-300"
                              onClick={() => {
                                setActiveTab("ranking");
                                setRankingTab("leaders");
                              }}
                            >
                              Ver ranking de líderes
                            </Button>
                          </div>
                        </AccordionContent>
                      </AccordionItem>

                      <AccordionItem value="closure-financial-breakdown" className="rounded-none border-0 border-b">
                        <AccordionTrigger asChild>
                          <button
                            type="button"
                            className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left transition hover:bg-slate-50/80"
                          >
                            <div className="flex min-w-0 items-start gap-3">
                              <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-teal-50 text-teal-700">
                                <CircleDollarSign className="h-4 w-4" />
                              </div>
                              <div className="min-w-0">
                                <div className="flex items-center gap-2">
                                  <div className="text-sm font-semibold text-slate-950">Detalhamento financeiro</div>
                                  <InfoHint ariaLabel="Ajuda sobre Detalhamento financeiro" description={SECTION_HELP.financial} />
                                </div>
                              </div>
                            </div>
                            <Badge className="border-slate-200 bg-slate-50 text-slate-700">3 painéis</Badge>
                          </button>
                        </AccordionTrigger>
                        <AccordionContent className="px-5 pb-5">
                          <div className="grid min-w-0 gap-4 xl:grid-cols-3">
                            <FinancialTable
                              title="Valor a ser pago por regional"
                              rows={filteredFinancials.cost_by_regional}
                              labelKey="regional"
                              collapsed={financialCollapsed}
                              onToggle={() => setFinancialCollapsed((value) => !value)}
                            />
                            <FinancialTable
                              title="Valor a ser pago por grupo"
                              rows={filteredFinancials.cost_by_group}
                              labelKey="group"
                              collapsed={financialCollapsed}
                              onToggle={() => setFinancialCollapsed((value) => !value)}
                            />
                            <FinancialTable
                              title="Assuntos sem regra frequentes"
                              rows={filteredFinancials.top_unmapped_subjects}
                              labelKey="os_subject"
                              collapsed={financialCollapsed}
                              onToggle={() => setFinancialCollapsed((value) => !value)}
                            />
                          </div>
                        </AccordionContent>
                      </AccordionItem>

                      <AccordionItem value="closure-analysis" className="rounded-none border-0">
                        <AccordionTrigger asChild>
                          <button
                            type="button"
                            className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left transition hover:bg-slate-50/80"
                          >
                            <div className="flex min-w-0 items-start gap-3">
                              <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-violet-50 text-violet-700">
                                <BarChart3 className="h-4 w-4" />
                              </div>
                              <div className="min-w-0">
                                <div className="flex items-center gap-2">
                                  <div className="text-sm font-semibold text-slate-950">Análise operacional e gráficos</div>
                                  <InfoHint ariaLabel="Ajuda sobre Análise operacional e gráficos" description={SECTION_HELP.chartArea} />
                                </div>
                              </div>
                            </div>
                            <Badge className="border-slate-200 bg-slate-50 text-slate-700">{selectedRegionals.length ? `${selectedRegionals.length} filial(is)` : "Todas as filiais"}</Badge>
                          </button>
                        </AccordionTrigger>
                        <AccordionContent className="px-5 pb-5">
                          <div className="grid gap-4 rounded-[20px] border border-slate-200 bg-[linear-gradient(180deg,#ffffff_0%,#f8fbff_100%)] p-4 lg:grid-cols-[1fr_minmax(260px,360px)] lg:items-start">
                            <div>
                              <Badge className="w-fit border-slate-200 bg-white text-slate-700">
                                <BarChart3 className="h-3.5 w-3.5" />
                                Análise operacional
                              </Badge>
                              <div className="mt-2 flex items-center gap-2">
                                <h2 className="text-lg font-semibold text-slate-950">Gráficos e indicadores filtrados</h2>
                                <InfoHint ariaLabel="Ajuda sobre Gráficos e indicadores filtrados" description={SECTION_HELP.filteredCharts} />
                              </div>
                            </div>
                            <div className="grid gap-1">
                              <select
                                multiple
                                className="h-16 rounded-md border border-input bg-white px-3 py-2 text-sm"
                                value={selectedRegionals}
                                onChange={(event) => updateSelectedRegionals(Array.from(event.currentTarget.selectedOptions, (option) => option.value))}
                              >
                                {regionalOptions.map((regional) => (
                                  <option key={regional} value={regional}>
                                    {regionalName(regional)}
                                  </option>
                                ))}
                              </select>
                              <div className="flex items-center justify-between gap-2 text-[11px] text-slate-500">
                                <span>{selectedRegionals.length ? `${selectedRegionals.length} filial(is) selecionada(s)` : "Todas as filiais"}</span>
                                <Button type="button" variant="ghost" size="sm" className="h-6 px-2" onClick={() => setSelectedRegionals([])}>
                                  Limpar
                                </Button>
                              </div>
                            </div>
                          </div>

                          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                            {[
                              { label: "Contexto", value: chartContext.label, icon: BarChart3, tone: "text-slate-950" },
                              { label: "Colaboradores", value: `${formatNumber(chartContext.collaborators)} colaboradores`, icon: UsersRound, tone: "text-slate-950" },
                              { label: "Reincidências", value: `${formatNumber(chartContext.recurrenceOrders)} O.S`, icon: AlertTriangle, tone: "text-amber-700" },
                              { label: "% reincidência", value: `${formatNumber(chartContext.recurrenceRate)}%`, icon: RefreshCw, tone: "text-teal-700" }
                            ].map((item) => {
                              const Icon = item.icon;
                              return (
                                <div key={item.label} className="rounded-md border bg-white px-3 py-2 shadow-sm">
                                  <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                                    <Icon className="h-3.5 w-3.5" />
                                    <span className="truncate">{item.label}</span>
                                  </div>
                                  <div className={`mt-1 truncate text-sm font-semibold ${item.tone}`}>{item.value}</div>
                                </div>
                              );
                            })}
                          </div>

                          <div className="mt-4">
                            <DashboardCharts ranking={filteredRanking} penalties={chartPenalties} health={chartHealth} />
                          </div>
                        </AccordionContent>
                      </AccordionItem>
                    </Accordion>
                  </section>
                </div>
              ) : null}
            </TabsContent>

            <TabsContent value="ranking" className="mt-0 flex-1 overflow-visible">
              {activeTab === "ranking" ? (
                !serviceOrdersLoaded && tabLoading.serviceOrders ? (
                  <div className="panel p-8 text-sm text-slate-500">Carregando base detalhada do ranking...</div>
                ) : (
                  <div className="flex h-full min-h-0 flex-col gap-3">
                    <section className="panel flex min-h-0 flex-1 flex-col overflow-hidden">
                      <div className="shrink-0 border-b bg-gradient-to-r from-slate-50 via-white to-white px-4 py-4">
                        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                          <div className="min-w-0">
                            <Badge className="w-fit border-slate-200 bg-white text-slate-700">
                              <Trophy className="h-3.5 w-3.5" />
                              Ranking operacional
                            </Badge>
                            <h2 className="mt-2 text-xl font-semibold text-slate-950">Colaboradores por resultado final</h2>
                            <p className="mt-1 text-sm text-slate-500">
                              Referência {summary.run?.reference_month}/{summary.run?.reference_year}. Valor global{" "}
                              {formatMoney(summary.run?.point_value ?? summary.point_value)}.
                            </p>
                          </div>
                          <div className="grid gap-2 sm:grid-cols-2 xl:min-w-[520px]">
                            <div className="grid gap-1">
                              <select
                                multiple
                                className="h-20 rounded-md border border-input bg-white px-3 py-2 text-sm"
                                value={selectedRegionals}
                                onChange={(event) => updateSelectedRegionals(Array.from(event.currentTarget.selectedOptions, (option) => option.value))}
                              >
                                {regionalOptions.map((regional) => (
                                  <option key={regional} value={regional}>
                                    {regionalName(regional)}
                                  </option>
                                ))}
                              </select>
                              <div className="flex items-center justify-between gap-2 text-[11px] text-slate-500">
                                <span>{selectedRegionals.length ? `${selectedRegionals.length} filial(is)` : "Todas as filiais"}</span>
                                <Button type="button" variant="ghost" size="sm" className="h-6 px-2" onClick={() => setSelectedRegionals([])}>
                                  Todas
                                </Button>
                              </div>
                            </div>
                            <div className="relative">
                              <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
                              <Input
                                className="h-9 pl-9"
                                value={rankingSearch}
                                onChange={(event) => setRankingSearch(event.target.value)}
                                placeholder="Buscar colaborador"
                                disabled={rankingTab !== "collaborators"}
                              />
                            </div>
                          </div>
                        </div>

                        <Tabs value={rankingTab} onValueChange={setRankingTab} className="mt-4 grid gap-4">
                          <div className="rounded-xl border border-slate-200 bg-white p-2">
                            <TabsList className="flex h-auto flex-wrap justify-start gap-2 bg-transparent p-0">
                              <TabsTrigger value="collaborators">Colaboradores</TabsTrigger>
                              <TabsTrigger value="leaders">Liderança</TabsTrigger>
                            </TabsList>
                          </div>

                          <TabsContent value="collaborators" className="mt-0 grid gap-4">
                            <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
                              <span className="font-medium text-slate-800">
                                Escopo atual: {formatNumber(rankingScopeTotals.serviceOrders)} O.S entraram no ranking
                              </span>{" "}
                              |{" "}
                              {formatNumber(outsideRankingCount)} O.S ficaram fora do ranking.
                              {rankingSearch.trim() ? " A busca por nome filtra a lista abaixo, mas não altera este resumo." : ""}
                            </div>

                            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5">
                              {[
                                ["O.S no ranking", `${formatNumber(rankingScopeTotals.serviceOrders)} O.S`],
                                ["Fora do ranking", `${formatNumber(outsideRankingCount)} O.S`],
                                ["O.S pontuadas", `${formatNumber(rankingScopeTotals.scored)} O.S`],
                                ["O.S sem regra", `${formatNumber(rankingScopeTotals.unscored)} O.S`],
                                ["Valor a ser pago", formatMoney(rankingScopeTotals.estimated)]
                              ].map(([label, value]) => (
                                <div key={label} className="min-w-0 rounded-md border bg-white px-3 py-2">
                                  <div className="truncate text-[10px] font-semibold uppercase tracking-wide text-slate-500">{label}</div>
                                  <div className="mt-1 truncate text-sm font-semibold text-slate-950">{value}</div>
                                </div>
                              ))}
                            </div>
                          </TabsContent>

                          <TabsContent value="leaders" className="mt-0 grid gap-4">
                            <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
                              <span className="font-medium text-slate-800">
                                Escopo atual: {formatNumber(filteredLeadershipResults.length)} líder(es) no recorte
                              </span>{" "}
                              |{" "}
                              {formatNumber(leadershipCoveredRegionals)} filial(is) coberta(s).
                            </div>

                            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                              {[
                                ["Líderes no ranking", `${formatNumber(filteredLeadershipResults.length)} líder(es)`],
                                ["Filiais cobertas", `${formatNumber(leadershipCoveredRegionals)} filial(is)`],
                                ["Multiplicador médio", filteredLeadershipResults.length ? `${formatNumber(filteredLeadershipResults.reduce((total, item) => total + item.multiplier, 0) / filteredLeadershipResults.length)}x` : "0x"],
                                ["Valor a pagar", formatMoney(filteredLeadershipResults.reduce((total, item) => total + item.bonus_amount, 0))]
                              ].map(([label, value]) => (
                                <div key={label} className="min-w-0 rounded-md border bg-white px-3 py-2">
                                  <div className="truncate text-[10px] font-semibold uppercase tracking-wide text-slate-500">{label}</div>
                                  <div className="mt-1 truncate text-sm font-semibold text-slate-950">{value}</div>
                                </div>
                              ))}
                            </div>
                          </TabsContent>
                        </Tabs>
                      </div>
                      <div className="min-h-0 flex-1 overflow-auto">
                        {rankingTab === "collaborators" ? (
                          <RankingTable
                            data={filteredRanking}
                            onViewOrders={(score) => {
                              setSelectedScore(score);
                              setOrdersOpen(true);
                            }}
                          />
                        ) : (
                          <div className="table-frame h-full px-2 py-2">
                            <Table>
                              <TableHeader>
                                <TableRow>
                                  <TableHead>Nome</TableHead>
                                  <TableHead>Tipo</TableHead>
                                  <TableHead>Filiais</TableHead>
                                  <TableHead>Média final</TableHead>
                                  <TableHead>Base</TableHead>
                                  <TableHead>Multiplicador</TableHead>
                                  <TableHead>Valor a pagar</TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {filteredLeadershipResults.map((item) => (
                                  <TableRow key={`${item.leadership_profile_id}-${item.role_type}`}>
                                    <TableCell className="font-medium">{item.name}</TableCell>
                                    <TableCell>{leadershipRoleLabel(item.role_type)}</TableCell>
                                    <TableCell className="max-w-[540px]">
                                      <div className="line-clamp-2 text-sm text-slate-700">
                                        {item.regionals.map((regional) => regionalName(regional)).join(", ")}
                                      </div>
                                    </TableCell>
                                    <TableCell>{formatNumber(item.average_final_points)} pts</TableCell>
                                    <TableCell>{formatMoney(item.base_amount)}</TableCell>
                                    <TableCell>{formatNumber(item.multiplier)}x</TableCell>
                                    <TableCell className="font-semibold text-teal-700">{formatMoney(item.bonus_amount)}</TableCell>
                                  </TableRow>
                                ))}
                                {filteredLeadershipResults.length === 0 ? (
                                  <TableRow>
                                    <TableCell colSpan={7} className="py-10 text-center text-sm text-slate-500">
                                      Nenhum líder encontrado para os filtros atuais.
                                    </TableCell>
                                  </TableRow>
                                ) : null}
                              </TableBody>
                            </Table>
                          </div>
                        )}
                      </div>
                    </section>
                  </div>
                )
              ) : null}
            </TabsContent>

            <TabsContent value="import" className="mt-0 flex-1 pr-1">
              {activeTab === "import" ? (
                <UpvalueImportPanel
                  onImported={loadAll}
                  onRecalculate={recalculate}
                  onAnalyzePeriod={can("calculation:run") ? calculatePeriod : viewPeriod}
                  canImport={can("orders:import")}
                  canCalculate={can("calculation:run")}
                  currentPeriod={{
                    reference_month: summary.run?.reference_month,
                    reference_year: summary.run?.reference_year
                  }}
                  busy={busy}
                />
              ) : null}
            </TabsContent>

            <TabsContent value="pending" className="mt-0 flex-1 pr-1">
              {activeTab === "pending" ? (
                !pendingDataLoaded && tabLoading.pending ? (
                  <div className="panel p-8 text-sm text-slate-500">Carregando assuntos e diagnósticos pendentes...</div>
                ) : (
                <div className="grid gap-4">
                  <section className="overflow-hidden rounded-lg border border-amber-200 bg-white shadow-sm">
                    <div className="grid gap-5 bg-gradient-to-r from-amber-50 via-white to-white p-5 lg:grid-cols-[1fr_auto] lg:items-start">
                      <div>
                        <Badge className="w-fit border-amber-200 bg-white text-amber-700">
                          <Settings2 className="h-3.5 w-3.5" />
                          Governança pendente
                        </Badge>
                        <h2 className="mt-3 text-xl font-semibold text-slate-950">Itens sem regra antes do fechamento</h2>
                        <p className="mt-1 max-w-2xl text-sm text-slate-600">
                          Resolva assuntos e diagnósticos sem governança. Depois recalcule para atualizar ranking, auditoria e valor a ser pago.
                        </p>
                      </div>
                      <Button onClick={recalculate} disabled={busy || loading}>
                        <RefreshCw className={busy ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
                        Recalcular após ajustes
                      </Button>
                    </div>
                    <div className="grid gap-3 border-t bg-white p-5 md:grid-cols-3">
                      <div className="rounded-lg border bg-slate-50/70 p-4">
                        <div className="text-xs font-medium uppercase text-slate-500">O.S sem regra</div>
                        <div className="mt-2 text-2xl font-semibold text-amber-700">{formatNumber(summary.cards.unscored_service_orders)} O.S</div>
                        <p className="mt-1 text-xs text-slate-500">Assuntos que precisam de grupo de pontuação.</p>
                      </div>
                      <div className="rounded-lg border bg-slate-50/70 p-4">
                        <div className="text-xs font-medium uppercase text-slate-500">Diagnósticos sem regra</div>
                        <div className="mt-2 text-2xl font-semibold text-amber-700">{formatNumber(summary.cards.diagnosis_unmapped_service_orders)} O.S</div>
                        <p className="mt-1 text-xs text-slate-500">Diagnósticos que ainda precisam de decisão.</p>
                      </div>
                      <div className="rounded-lg border bg-slate-50/70 p-4">
                        <div className="text-xs font-medium uppercase text-slate-500">Total pendente</div>
                        <div className="mt-2 text-2xl font-semibold text-slate-950">
                          {formatNumber(summary.cards.closure_pending_service_orders ?? (summary.cards.unscored_service_orders + summary.cards.diagnosis_unmapped_service_orders))} O.S
                        </div>
                        <p className="mt-1 text-xs text-slate-500">Conta O.S únicas com assunto sem grupo ou diagnóstico sem regra, sem duplicar a mesma ordem.</p>
                      </div>
                    </div>
                  </section>

                  <UnmappedSubjectsPanel
                    groups={groups}
                    subjects={unmappedSubjects}
                    onLinkSubject={(subject, groupId) =>
                      withFeedback(async () => {
                        await api.linkSubjectToGroup({
                          group_id: groupId,
                          os_type: subject.os_type,
                          os_subject: subject.os_subject
                        });
                        await loadAll();
                      }, "Assunto vinculado a grupo.")
                    }
                    onLinkSubjects={(items) =>
                      withFeedback(async () => {
                        await api.linkSubjectsToGroups(
                          items.map((item) => ({
                            group_id: item.groupId,
                            os_type: item.subject.os_type,
                            os_subject: item.subject.os_subject
                          }))
                        );
                        await loadAll();
                      }, `${items.length} assunto(s) vinculados em massa.`)
                    }
                    onCreateGroupForSubject={(subject) =>
                      withFeedback(async () => {
                        const group = await api.createScoringGroup({
                          name: `Grupo - ${subject.os_subject}`.slice(0, 150),
                          description: `Criado a partir do assunto sem regra: ${subject.os_subject}`,
                          default_points: 0,
                          active: true
                        });
                        await api.linkSubjectToGroup({
                          group_id: group.id,
                          os_type: subject.os_type,
                          os_subject: subject.os_subject
                        });
                        await loadAll();
                      }, "Grupo criado e assunto vinculado.")
                    }
                  />

                  <UnmappedDiagnosesPanel
                    diagnoses={unmappedDiagnoses}
                    onConfigureDiagnosis={(diagnosisName, payload) =>
                      withFeedback(async () => {
                        await api.configureDiagnosis({
                          diagnosis_name: diagnosisName,
                          ...payload
                        });
                        await loadAll();
                      }, "Regra de diagnóstico criada.")
                    }
                    onConfigureDiagnoses={(items) =>
                      withFeedback(async () => {
                        await api.configureDiagnoses(
                          items.map((item) => ({
                            diagnosis_name: item.diagnosisName,
                            ...item.payload
                          }))
                        );
                        await loadAll();
                      }, `${items.length} regra(s) de diagnóstico salvas em massa.`)
                    }
                  />
                </div>
                )
              ) : null}
            </TabsContent>

            <TabsContent value="config" className="mt-0 flex-1 pr-1">
              {activeTab === "config" ? (
                <Tabs value={configTab} onValueChange={setConfigTab} className="grid gap-4">
                  <div className="rounded-[24px] border border-slate-200 bg-white p-4 shadow-[0_10px_40px_rgba(15,23,42,0.05)]">
                    <TabsList
                      className={`grid h-auto gap-2 rounded-2xl bg-slate-50 p-1 ${
                        can("users:manage") ? "md:grid-cols-4" : "md:grid-cols-3"
                      }`}
                    >
                      <TabsTrigger value="rules" className="rounded-xl px-4 py-2.5">Regras da gamificação</TabsTrigger>
                      <TabsTrigger value="collaborators" className="rounded-xl px-4 py-2.5">Colaboradores e filiais</TabsTrigger>
                      <TabsTrigger value="leadership" className="rounded-xl px-4 py-2.5">Liderança e multiplicadores</TabsTrigger>
                      {can("users:manage") ? <TabsTrigger value="users" className="rounded-xl px-4 py-2.5">Usuários</TabsTrigger> : null}
                    </TabsList>
                  </div>

                  <TabsContent value="rules" className="mt-0">
                    {!rulesSupportLoaded && tabLoading.configRules ? (
                      <div className="panel p-8 text-sm text-slate-500">Carregando regras, assuntos e diagnósticos...</div>
                    ) : (
                    <LogicConfigurationPanel
                    groups={groups}
                    subjectRules={subjectRules}
                    importedDiagnoses={importedDiagnoses}
                    recurrenceRules={recurrenceRules}
                    healthRules={healthRules}
                    slaRules={slaRules}
                    pointValue={pointValue}
                    periodSubjectSummaries={configSubjectSummaries}
                    financialBreakdowns={{
                      cost_by_group: filteredFinancials.cost_by_group,
                      cost_by_subject: summary?.cost_by_subject ?? []
                    }}
                    setGroups={setGroups}
                    setSubjectRules={setSubjectRules}
                    setRecurrenceRules={setRecurrenceRules}
                    setHealthRules={setHealthRules}
                    setSlaRules={setSlaRules}
                    setPointValue={setPointValue}
                    onReload={() => refreshRulesConfigData(summary?.run?.id)}
                  onCreateGroup={(payload) =>
                    withFeedback(async () => {
                      const created = await api.createScoringGroup(payload);
                      setGroups((current) => [...current, created].sort((a, b) => a.name.localeCompare(b.name, "pt-BR")));
                    }, "Grupo criado. O cálculo só muda quando você recalcular.")
                  }
                  onSaveGroup={(group) =>
                    withFeedback(async () => {
                      const saved = await api.updateScoringGroup(group.id, {
                        name: group.name,
                        description: group.description,
                        default_points: group.default_points,
                        point_value_override: group.point_value_override,
                        active: group.active
                      });
                      setGroups((current) => replaceById(current, group.id, saved));
                    }, "Grupo salvo sem recarregar toda a tela.")
                  }
                  onDeleteGroup={(group, replacementGroupId) =>
                    withFeedback(async () => {
                      await api.deleteScoringGroup(group.id, {
                        replacement_group_id: replacementGroupId ?? undefined,
                        delete_linked_rules: replacementGroupId == null
                      });
                      await refreshRulesConfigData(summary?.run?.id);
                    }, replacementGroupId == null ? "Grupo e vínculos excluídos." : "Grupo excluído e vínculos realocados.")
                  }
                  onSaveSubjectRule={(rule) =>
                    withFeedback(async () => {
                      const saved = await api.updateScoringSubjectRule(rule.id, {
                        group_id: rule.group_id,
                        os_type: rule.os_type,
                        os_subject: rule.os_subject,
                        subject_category: rule.subject_category,
                        custom_points: rule.custom_points,
                        point_value_override: rule.point_value_override,
                        use_group_default: rule.use_group_default,
                        active: rule.active
                      });
                      setSubjectRules((current) => replaceById(current, rule.id, saved));
                      if (pendingDataLoaded || rulesSupportLoaded) {
                        const unmappedData = await api.unmappedSubjects(summary?.run?.id);
                        setUnmappedSubjects(unmappedData);
                      }
                    }, "Regra de assunto salva. O ranking só muda quando você recalcular.")
                  }
                  onDeleteSubjectRule={(rule) =>
                    withFeedback(async () => {
                      await api.deleteScoringSubjectRule(rule.id);
                      setSubjectRules((current) => current.filter((item) => item.id !== rule.id));
                      if (pendingDataLoaded || rulesSupportLoaded) {
                        const unmappedData = await api.unmappedSubjects(summary?.run?.id);
                        setUnmappedSubjects(unmappedData);
                      }
                    }, "Vínculo de assunto removido.")
                  }
                  onSaveDiagnosisRule={(diagnosisName, ruleId, payload) =>
                    withFeedback(async () => {
                      if (ruleId) {
                        await api.updateDiagnosisPenaltyRule(ruleId, payload);
                      } else {
                        await api.createDiagnosisPenaltyRule({
                          diagnosis_name: diagnosisName,
                          ...payload
                        });
                      }
                      if (pendingDataLoaded || rulesSupportLoaded) {
                        const [importedDiagnosisData, unmappedDiagnosisData] = await Promise.all([
                          api.importedDiagnoses(summary?.run?.id),
                          api.unmappedDiagnoses(summary?.run?.id)
                        ]);
                        setImportedDiagnoses(importedDiagnosisData);
                        setUnmappedDiagnoses(unmappedDiagnosisData);
                      }
                    }, "Regra de diagnóstico salva sem recarregar a página inteira.")
                  }
                  onSavePointValue={() =>
                    withFeedback(async () => {
                      const value = parseOptionalNumber(pointValue);
                      if (value === null) {
                        throw new Error("Informe o valor do ponto antes de salvar.");
                      }
                      await api.updateSetting("point_value", value.toFixed(2));
                    }, "Valor do ponto salvo. A apuração muda no próximo recálculo.")
                  }
                  onCreateRecurrenceRule={(payload) =>
                    withFeedback(async () => {
                      const created = await api.createRecurrenceClassificationRule(payload);
                      setRecurrenceRules((current) => [...current, created].sort((a, b) => (a.priority ?? 0) - (b.priority ?? 0) || a.id - b.id));
                    }, "Regra de reincidência criada.")
                  }
                  onSaveRecurrenceRule={(rule) =>
                    withFeedback(async () => {
                      const saved = await api.updateRecurrenceClassificationRule(rule.id, {
                        name: rule.name,
                        os_type_pattern: rule.os_type_pattern,
                        os_subject_pattern: rule.os_subject_pattern,
                        diagnosis_pattern: rule.diagnosis_pattern,
                        original_os_type_pattern: rule.original_os_type_pattern,
                        original_os_subject_pattern: rule.original_os_subject_pattern,
                        return_os_type_pattern: rule.return_os_type_pattern,
                        return_os_subject_pattern: rule.return_os_subject_pattern,
                        return_diagnosis_pattern: rule.return_diagnosis_pattern,
                        ignore_diagnosis_pattern: rule.ignore_diagnosis_pattern,
                        classification: rule.classification,
                        discount_points: rule.discount_points,
                        max_days: rule.max_days,
                        require_same_subject: rule.require_same_subject,
                        require_same_diagnosis: rule.require_same_diagnosis,
                        priority: rule.priority,
                        description: rule.description,
                        active: rule.active
                      });
                      setRecurrenceRules((current) => replaceById(current, rule.id, saved));
                    }, "Regra de reincidência salva.")
                  }
                  onDeleteRecurrenceRule={(rule) =>
                    withFeedback(async () => {
                      await api.deleteRecurrenceClassificationRule(rule.id);
                      setRecurrenceRules((current) => current.filter((item) => item.id !== rule.id));
                    }, "Regra de reincidência removida.")
                  }
                  onSaveHealthRule={(rule) =>
                    withFeedback(async () => {
                      const saved = await api.updateHealthRule(rule.id, {
                        min_sla: rule.min_sla,
                        max_recurrence_rate: rule.max_recurrence_rate,
                        multiplier: rule.multiplier,
                        active: rule.active
                      });
                      setHealthRules((current) => replaceById(current, rule.id, saved));
                    }, "Multiplicador salvo.")
                  }
                  onCreateSlaRule={() =>
                    withFeedback(async () => {
                      const created = await api.createSlaPenaltyRule({
                        name: "Fora do prazo",
                        condition_type: "status_sla_out_of_time",
                        penalty_type: "none",
                        penalty_value: 0,
                        active: true
                      });
                      setSlaRules((current) => [...current, created].sort((a, b) => a.id - b.id));
                    }, "Regra SLA criada.")
                  }
                  onSaveSlaRule={(rule) =>
                    withFeedback(async () => {
                      const saved = await api.updateSlaPenaltyRule(rule.id, {
                        name: rule.name,
                        condition_type: rule.condition_type,
                        penalty_type: rule.penalty_type,
                        penalty_value: rule.penalty_value,
                        active: rule.active
                      });
                      setSlaRules((current) => replaceById(current, rule.id, saved));
                    }, "Regra SLA salva.")
                  }
                />
                    )}
                  </TabsContent>

                  <TabsContent value="collaborators" className="mt-0">
                    {!collaboratorRegistryLoaded && tabLoading.collaborators ? (
                      <div className="panel p-8 text-sm text-slate-500">Carregando cadastro de colaboradores...</div>
                    ) : (
                    <CollaboratorRegistryPanel
                      registry={collaboratorRegistry}
                      regionalOptions={collaboratorRegionalOptions}
                      onCreate={(payload) =>
                        withFeedback(async () => {
                          await api.createCollaborator({
                            ...payload,
                            role: payload.role || "Importado UpValue",
                            regional: regionalName(payload.regional),
                          });
                          await refreshAfterCollaboratorRegistryChange();
                        }, "Colaborador cadastrado e cálculos atualizados.")
                      }
                      onSave={(item: CollaboratorRegistryItem) =>
                        withFeedback(async () => {
                          await api.updateCollaborator(item.id, {
                            name: item.name,
                            role: item.role || "Importado UpValue",
                            regional: regionalName(item.regional),
                            active: item.active,
                            is_registered: item.is_registered,
                          });
                          await refreshAfterCollaboratorRegistryChange();
                        }, item.is_registered ? "Cadastro do colaborador salvo e cálculos atualizados." : "Colaborador mantido como pendente.")
                      }
                      onDelete={(item: CollaboratorRegistryItem) =>
                        withFeedback(async () => {
                          const result = await api.deleteCollaborator(item.id);
                          await refreshAfterCollaboratorRegistryChange();
                          if (result.soft_deleted) {
                            setMessage(`Cadastro removido da lista principal. ${item.name} voltou para pendentes porque possui O.S vinculadas.`);
                          }
                        }, "Cadastro do colaborador removido.")
                      }
                      onDeleteMany={(items: CollaboratorRegistryItem[]) =>
                        withFeedback(async () => {
                          for (const item of items) {
                            await api.deleteCollaborator(item.id);
                          }
                          await refreshAfterCollaboratorRegistryChange();
                        }, `${items.length} colaborador(es) removido(s).`)
                      }
                    />
                    )}
                  </TabsContent>
                  <TabsContent value="leadership" className="mt-0">
                    {!leadershipProfilesLoaded && tabLoading.leadership ? (
                      <div className="panel p-8 text-sm text-slate-500">Carregando liderança e bonificação...</div>
                    ) : (
                      <LeadershipBonusPanel
                        roleProfiles={leadershipRoleProfiles}
                        profiles={leadershipProfiles}
                        regionalOptions={collaboratorRegionalOptions}
                        readOnly={!can("scoring:write")}
                        onCreateRoleProfile={(payload) =>
                          withFeedback(async () => {
                            const created = await api.createLeadershipRoleProfile(payload);
                            setLeadershipRoleProfiles((current) => [...current, created].sort((a, b) => a.name.localeCompare(b.name, "pt-BR")));
                          }, "Perfil de liderança criado.")
                        }
                        onSaveRoleProfile={(roleProfile) =>
                          withFeedback(async () => {
                            const saved = await api.updateLeadershipRoleProfile(roleProfile.id, roleProfile);
                            setLeadershipRoleProfiles((current) => replaceById(current, roleProfile.id, saved));
                            const leaders = await api.leadershipProfiles();
                            setLeadershipProfiles(leaders);
                            if (summary?.run?.id && can("calculation:run")) {
                              await api.calculateLeadershipBonus(summary.run.id);
                              await loadAll(analysisPeriod);
                            }
                          }, "Perfil de liderança salvo.")
                        }
                        onDeleteRoleProfile={(roleProfile) =>
                          withFeedback(async () => {
                            await api.deleteLeadershipRoleProfile(roleProfile.id);
                            setLeadershipRoleProfiles((current) => current.filter((item) => item.id !== roleProfile.id));
                          }, "Perfil de liderança removido.")
                        }
                        onCreate={(payload) =>
                          withFeedback(async () => {
                            const created = await api.createLeadershipProfile(payload);
                            setLeadershipProfiles((current) => [...current, created].sort((a, b) => a.name.localeCompare(b.name, "pt-BR")));
                            if (summary?.run?.id && can("calculation:run")) {
                              await api.calculateLeadershipBonus(summary.run.id);
                              await loadAll(analysisPeriod);
                            }
                          }, "Liderança cadastrada e bonificação atualizada.")
                        }
                        onSave={(profile) =>
                          withFeedback(async () => {
                            const saved = await api.updateLeadershipProfile(profile.id, {
                              name: profile.name,
                              role_type: profile.role_type,
                              multiplier: profile.multiplier,
                              role_profile_id: profile.role_profile_id,
                              use_custom_multiplier: profile.use_custom_multiplier,
                              custom_multiplier: profile.custom_multiplier,
                              active: profile.active,
                              collaborator_id: profile.collaborator_id,
                              regional_names: profile.regional_names
                            });
                            setLeadershipProfiles((current) => replaceById(current, profile.id, saved));
                            if (summary?.run?.id && can("calculation:run")) {
                              await api.calculateLeadershipBonus(summary.run.id);
                              await loadAll(analysisPeriod);
                            }
                          }, "Liderança salva e bonificação atualizada.")
                        }
                        onDelete={(profile) =>
                          withFeedback(async () => {
                            await api.deleteLeadershipProfile(profile.id);
                            setLeadershipProfiles((current) => current.filter((item) => item.id !== profile.id));
                            if (summary?.run?.id && can("calculation:run")) {
                              await api.calculateLeadershipBonus(summary.run.id);
                              await loadAll(analysisPeriod);
                            }
                          }, "Liderança removida.")
                        }
                      />
                    )}
                  </TabsContent>
                  {can("users:manage") ? (
                    <TabsContent value="users" className="mt-0">
                      {!usersLoaded && tabLoading.users ? (
                        <div className="panel p-8 text-sm text-slate-500">Carregando usuários...</div>
                      ) : (
                      <UserManagementPanel
                        users={users}
                        onCreate={(payload) =>
                          withFeedback(async () => {
                            await api.createUser(payload);
                            setUsers(await api.users());
                          }, "Usuário criado.")
                        }
                        onSave={(id, payload) =>
                          withFeedback(async () => {
                            await api.updateUser(id, payload);
                            setUsers(await api.users());
                          }, "Usuário salvo.")
                        }
                        onDelete={(id) =>
                          withFeedback(async () => {
                            await api.deleteUser(id);
                            setUsers(await api.users());
                          }, "Usuário excluído.")
                        }
                      />
                      )}
                    </TabsContent>
                  ) : null}
                </Tabs>
              ) : null}
            </TabsContent>

            <TabsContent value="unmapped">
              {activeTab === "unmapped" ? (
                <UnmappedSubjectsPanel
                  groups={groups}
                  subjects={unmappedSubjects}
                  onLinkSubject={(subject, groupId) =>
                    withFeedback(async () => {
                      await api.linkSubjectToGroup({
                        group_id: groupId,
                        os_type: subject.os_type,
                        os_subject: subject.os_subject
                      });
                      await loadAll();
                    }, "Assunto vinculado a grupo.")
                  }
                  onLinkSubjects={(items) =>
                    withFeedback(async () => {
                      await api.linkSubjectsToGroups(
                        items.map((item) => ({
                          group_id: item.groupId,
                          os_type: item.subject.os_type,
                          os_subject: item.subject.os_subject
                        }))
                      );
                      await loadAll();
                    }, `${items.length} assunto(s) vinculados em massa.`)
                  }
                  onCreateGroupForSubject={(subject) =>
                    withFeedback(async () => {
                      const group = await api.createScoringGroup({
                        name: `Grupo - ${subject.os_subject}`.slice(0, 150),
                        description: `Criado a partir do assunto sem regra: ${subject.os_subject}`,
                        default_points: 0,
                        active: true
                      });
                      await api.linkSubjectToGroup({
                        group_id: group.id,
                        os_type: subject.os_type,
                        os_subject: subject.os_subject
                      });
                      await loadAll();
                    }, "Grupo criado e assunto vinculado.")
                  }
                />
              ) : null}
            </TabsContent>

            <TabsContent value="diagnosis-unmapped">
              {activeTab === "diagnosis-unmapped" ? (
                <UnmappedDiagnosesPanel
                  diagnoses={unmappedDiagnoses}
                  onConfigureDiagnosis={(diagnosisName, payload) =>
                    withFeedback(async () => {
                      await api.configureDiagnosis({
                        diagnosis_name: diagnosisName,
                        ...payload
                      });
                      await loadAll();
                    }, "Regra de diagnóstico criada.")
                  }
                  onConfigureDiagnoses={(items) =>
                    withFeedback(async () => {
                      await api.configureDiagnoses(
                        items.map((item) => ({
                          diagnosis_name: item.diagnosisName,
                          ...item.payload
                        }))
                      );
                      await loadAll();
                    }, `${items.length} regra(s) de diagnóstico salvas em massa.`)
                  }
                />
              ) : null}
            </TabsContent>

            <TabsContent value="audit" className="mt-0 flex-1 overflow-visible">
              {activeTab === "audit" ? (
                !serviceOrdersLoaded && tabLoading.serviceOrders ? (
                  <div className="panel p-8 text-sm text-slate-500">Carregando filtros detalhados da auditoria...</div>
                ) : (
                  <AuditPanel
                    calculationRunId={summary.run?.id}
                    groups={groups}
                    regionalOptions={regionalOptions}
                    collaboratorOptions={auditCollaboratorOptions}
                    subjectOptions={auditSubjectOptions}
                  />
                )
              ) : null}
            </TabsContent>

            <TabsContent value="history" className="mt-0 flex flex-1 flex-col pr-1">
              {activeTab === "history" ? (
                !historyLoaded && tabLoading.history ? (
                  <div className="panel p-8 text-sm text-slate-500">Carregando histórico de apurações...</div>
                ) : (
                  <ClosureHistoryPanel runs={calculationRuns} />
                )
              ) : null}
            </TabsContent>
          </Tabs>
        )}
      </div>

      <CollaboratorOrdersSheet
        open={ordersOpen}
        onOpenChange={setOrdersOpen}
        score={selectedScore}
        calculationRunId={summary?.run?.id}
        groups={groups}
        rankingPosition={
          selectedScore
            ? filteredRanking.findIndex((score) => score.collaborator_id === selectedScore.collaborator_id) + 1 || null
            : null
        }
      />
    </main>
  );
}






