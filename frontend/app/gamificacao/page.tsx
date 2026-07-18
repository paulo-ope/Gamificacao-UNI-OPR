"use client";

import { AlertTriangle, BarChart3, CalendarDays, CheckCircle2, ChevronDown, ChevronUp, CircleDollarSign, ClipboardList, Download, HelpCircle, Loader2, LockKeyhole, Mail, MapPin, MinusCircle, RefreshCw, Search, Send, Settings2, ShieldAlert, Trophy, UsersRound, Wallet, XCircle } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AuditPanel } from "@/components/gamification/audit-panel";
import { AuditTrailPanel } from "@/components/gamification/audit-trail-panel";
import { ClosureHistoryPanel } from "@/components/gamification/closure-history-panel";
import { CollaboratorRegistryPanel } from "@/components/gamification/collaborator-registry-panel";
import { CollaboratorOrdersSheet } from "@/components/gamification/collaborator-orders-sheet";
import { AppDrawer } from "@/components/gamification/config-ui";
import { DashboardCharts } from "@/components/gamification/dashboard-charts";
import { InfoHint } from "@/components/gamification/info-hint";
import { LogicConfigurationPanel } from "@/components/gamification/logic-configuration-panel";
import { LeadershipBonusPanel } from "@/components/gamification/leadership-bonus-panel";
import { ModuleSidebar } from "@/components/gamification/module-sidebar";
import { PointBalancePanel } from "@/components/gamification/point-balance-panel";
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
import { useConfirm } from "@/hooks/use-confirm";
import { normalizeRegional, regionalName } from "@/lib/regional";
import type {
  CalculationRunHistory,
  AuthUser,
  CollaboratorRegistry,
  CollaboratorRegistryItem,
  CollaboratorScore,
  DashboardBootstrap,
  DashboardFilteredBreakdown,
  DashboardSummary,
  HealthRule,
  ImportedDiagnosis,
  LeadershipAverageAuditCollaborator,
  LeadershipProfile,
  LeadershipBonusResult,
  LeadershipRoleProfile,
  PenaltyDistributionItem,
  RecurrenceClassificationRule,
  ScoringGroup,
  ScoringSubjectRule,
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
  balance: "Lista débitos de garantia detectados após o pagamento do período original, pendentes de abatimento no próximo fechamento do colaborador.",
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

function calculationStatusMeta(status: string | undefined) {
  switch (status) {
    case "review":
      return {
        label: "Em conferência",
        className: "w-fit border-amber-200 bg-white text-amber-700"
      };
    case "approved":
      return {
        label: "Aprovado",
        className: "w-fit border-sky-200 bg-white text-sky-700"
      };
    case "paid":
      return {
        label: "Pago",
        className: "w-fit border-emerald-200 bg-white text-emerald-700"
      };
    case "cancelled":
      return {
        label: "Cancelado",
        className: "w-fit border-rose-200 bg-white text-rose-700"
      };
    case "draft":
    default:
      return {
        label: "Rascunho",
        className: "w-fit border-slate-200 bg-white text-slate-700"
      };
  }
}

function leadershipRoleLabel(value: string) {
  if (value === "supervisor") return "Supervisor";
  if (value === "regional_manager") return "Gerente da unidade";
  if (value === "portfolio_manager") return "Gerente de pasta";
  return value;
}

function leadershipAverageSourceLabel(value: string | undefined) {
  if (value === "collaborators_and_leaders") return "Colaboradores + líderes";
  return "Colaboradores";
}

function leadershipAuditSourceLabel(value: string | undefined) {
  if (value === "leader") return "Líder";
  return "Colaborador";
}

function pluralizeFilial(count: number, suffix: "" | " selecionada" | " coberta" = "") {
  const suffixPlural = suffix ? `${suffix}s` : "";
  return count === 1 ? `filial${suffix}` : `filiais${suffixPlural}`;
}

function summarizeLabels(items: string[], visibleCount = 2) {
  if (items.length <= visibleCount) return { visible: items, remaining: 0 };
  return { visible: items.slice(0, visibleCount), remaining: items.length - visibleCount };
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
            aria-label={collapsed ? "Expandir todos" : "Recolher todos"}
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

export default function GamificacaoPage() {
  const { confirm, ConfirmDialog } = useConfirm();
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [bootstrap, setBootstrap] = useState<DashboardBootstrap | null>(null);
  const [calculationRuns, setCalculationRuns] = useState<CalculationRunHistory[]>([]);
  const [groups, setGroups] = useState<ScoringGroup[]>([]);
  const [subjectRules, setSubjectRules] = useState<ScoringSubjectRule[]>([]);
  // Tipos Gerais já usados por alguma regra cadastrada - sugestões pro campo obrigatório de Tipo
  // Geral na tela de assuntos sem regra (não é uma lista fechada, só sugestão).
  const unmappedOsTypeOptions = useMemo(
    () => Array.from(new Set(subjectRules.map((rule) => rule.os_type).filter(Boolean))).sort(),
    [subjectRules]
  );
  const [unmappedSubjects, setUnmappedSubjects] = useState<UnmappedSubject[]>([]);
  const [importedDiagnoses, setImportedDiagnoses] = useState<ImportedDiagnosis[]>([]);
  const [unmappedDiagnoses, setUnmappedDiagnoses] = useState<ImportedDiagnosis[]>([]);
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
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedScore, setSelectedScore] = useState<CollaboratorScore | null>(null);
  const [selectedLeadershipResult, setSelectedLeadershipResult] = useState<LeadershipBonusResult | null>(null);
  const [ordersOpen, setOrdersOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("closure");
  const [configTab, setConfigTab] = useState("rules");
  const [auditTab, setAuditTab] = useState("scoring");
  const [rankingTab, setRankingTab] = useState("collaborators");
  const [analysisPeriod, setAnalysisPeriod] = useState<AnalysisPeriod>({});
  const [selectedRegionals, setSelectedRegionals] = useState<string[]>([]);
  const [rankingSearch, setRankingSearch] = useState("");
  const [chartPenalties, setChartPenalties] = useState<PenaltyDistributionItem[]>([]);
  const [financialCollapsed, setFinancialCollapsed] = useState(true);
  const [filteredBreakdowns, setFilteredBreakdowns] = useState<DashboardFilteredBreakdown | null>(null);
  const [serviceOrdersLoaded, setServiceOrdersLoaded] = useState(false);
  const [pendingDataLoaded, setPendingDataLoaded] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [collaboratorRegistryLoaded, setCollaboratorRegistryLoaded] = useState(false);
  const [leadershipProfilesLoaded, setLeadershipProfilesLoaded] = useState(false);
  const [usersLoaded, setUsersLoaded] = useState(false);
  const [rulesSupportLoaded, setRulesSupportLoaded] = useState(false);
  // Uma vez que o painel montou com dados reais, ele nunca mais deve ser desmontado por um
  // refresh subsequente (ex: refreshAfterCollaboratorRegistryChange) - senão um Dialog/Drawer do
  // Radix aberto dentro dele é arrancado da árvore em pleno meio da animação de fechamento,
  // deixando o overlay "fantasma" cobrindo a tela. Esses refs controlam a renderização do
  // esqueleto de carregamento apenas na primeira carga; refreshes usam o painel já montado.
  const collaboratorRegistryEverLoadedRef = useRef(false);
  const leadershipProfilesEverLoadedRef = useRef(false);
  const usersEverLoadedRef = useRef(false);
  const authBootstrapRef = useRef(false);
  const initialLoadRef = useRef(false);
  const serviceOrdersLoadKeyRef = useRef<string | null>(null);
  const pendingLoadKeyRef = useRef<string | null>(null);
  const historyLoadInFlightRef = useRef(false);
  const rulesSupportLoadKeyRef = useRef<string | null>(null);
  const loadAllKeyRef = useRef<string | null>(null);
  const calculationInFlightRef = useRef(false);
  const [tabLoading, setTabLoading] = useState<Record<string, boolean>>({});

  const can = useCallback((permission: string) => Boolean(currentUser?.permissions.some((item) => item === permission)), [currentUser]);

  const setTabBusy = useCallback((key: string, value: boolean) => {
    setTabLoading((current) => ({ ...current, [key]: value }));
  }, []);

  const resetLazyData = useCallback(() => {
    setCalculationRuns([]);
    // collaboratorRegistry/leadershipProfiles/leadershipRoleProfiles/users NÃO são zerados aqui:
    // os dados antigos ficam visíveis (levemente desatualizados) até o refetch concluir, em vez de
    // piscar para uma lista vazia - e, principalmente, em vez de forçar o desmonte do painel
    // correspondente (ver collaboratorRegistryEverLoadedRef acima).
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
      const referenceMonth = summary?.run?.reference_month ?? analysisPeriod.reference_month;
      const referenceYear = summary?.run?.reference_year ?? analysisPeriod.reference_year;
      const referenceRegional = summary?.run?.regional ?? analysisPeriod.regional ?? undefined;
      if (!referenceMonth || !referenceYear) {
        throw new Error("Período analisado não identificado para carregar a auditoria.");
      }
      const loadKey = `${referenceMonth}:${referenceYear}:${referenceRegional ?? ""}`;
      if (serviceOrdersLoadKeyRef.current === loadKey) return;
      serviceOrdersLoadKeyRef.current = loadKey;
      const subjectSummaryData = await api.serviceOrderSubjectSummary({
        reference_month: referenceMonth,
        reference_year: referenceYear,
        regional: referenceRegional
      });
      setConfigSubjectSummaries(subjectSummaryData);
      setServiceOrdersLoaded(true);
    } finally {
      serviceOrdersLoadKeyRef.current = null;
      setTabBusy("serviceOrders", false);
    }
  }, [
    analysisPeriod.reference_month,
    analysisPeriod.reference_year,
    analysisPeriod.regional,
    serviceOrdersLoaded,
    setTabBusy,
    summary?.run?.reference_month,
    summary?.run?.reference_year,
    summary?.run?.regional
  ]);

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
      const loadKey = `${runId ?? ""}:${referenceMonth}:${referenceYear}:${referenceRegional ?? ""}`;
      if (rulesSupportLoadKeyRef.current === loadKey) return;
      rulesSupportLoadKeyRef.current = loadKey;
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
      rulesSupportLoadKeyRef.current = null;
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
    const loadKey = String(runId ?? "latest");
    if (pendingLoadKeyRef.current === loadKey) return;
    pendingLoadKeyRef.current = loadKey;
    setTabBusy("pending", true);
    try {
      // subjectRules tambem e buscado aqui (nao so quando a aba Configuração abre) porque o seletor
      // de Tipo Geral desta aba depende dele pra sugerir os tipos ja cadastrados - sem isso, o
      // combobox aparecia vazio ("Nenhuma opção encontrada") pra quem nunca tinha aberto Configuração
      // nesta sessão (achado real).
      const [unmappedData, unmappedDiagnosisData, subjectRuleData] = await Promise.all([
        api.unmappedSubjects(runId),
        api.unmappedDiagnoses(runId),
        api.scoringSubjectRules()
      ]);
      setUnmappedSubjects(unmappedData);
      setUnmappedDiagnoses(unmappedDiagnosisData);
      setSubjectRules(subjectRuleData);
      setPendingDataLoaded(true);
    } finally {
      pendingLoadKeyRef.current = null;
      setTabBusy("pending", false);
    }
  }, [pendingDataLoaded, setTabBusy]);

  const loadHistoryData = useCallback(async () => {
    if (historyLoaded) return;
    if (historyLoadInFlightRef.current) return;
    historyLoadInFlightRef.current = true;
    setTabBusy("history", true);
    try {
      const calculationRunData = await api.calculationRuns();
      setCalculationRuns(calculationRunData);
      setHistoryLoaded(true);
    } finally {
      historyLoadInFlightRef.current = false;
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
      collaboratorRegistryEverLoadedRef.current = true;
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
      leadershipProfilesEverLoadedRef.current = true;
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
      usersEverLoadedRef.current = true;
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

  const loadAll = useCallback(async (period: AnalysisPeriod = analysisPeriod, options: { refreshRuleBasics?: boolean } = {}) => {
    if (!currentUser) return;
    const refreshRuleBasics = options.refreshRuleBasics ?? true;
    const loadKey = `${period.reference_month ?? ""}:${period.reference_year ?? ""}:${period.regional ?? ""}:${refreshRuleBasics}`;
    if (loadAllKeyRef.current === loadKey) return;
    loadAllKeyRef.current = loadKey;
    setError(null);
    setSummaryLoading(true);
    resetLazyData();
    try {
      const summaryData = await api.summary(period);
      setSummary(summaryData);
      setPointValue(String(summaryData.point_value ?? ""));
      if (refreshRuleBasics) {
        Promise.all([api.scoringGroups(), api.settings()])
          .then(([groupData, settingsData]) => {
            setGroups(groupData);
            const pointSetting = settingsData.find((setting) => setting.key === "point_value");
            setPointValue(pointSetting?.value ?? String(summaryData.point_value ?? ""));
          })
          .catch((err: Error) => setError(err.message));
      }
    } finally {
      loadAllKeyRef.current = null;
      setSummaryLoading(false);
      setLoading(false);
    }
  }, [analysisPeriod, currentUser, resetLazyData]);

  useEffect(() => {
    if (authBootstrapRef.current) return;
    authBootstrapRef.current = true;
    Promise.all([api.me(), api.dashboardBootstrap().catch(() => null)])
      .then(([user, bootstrapData]) => {
        setCurrentUser(user);
        setBootstrap(bootstrapData);
        if (bootstrapData?.reference_month && bootstrapData?.reference_year) {
          setAnalysisPeriod({
            reference_month: bootstrapData.reference_month,
            reference_year: bootstrapData.reference_year,
            regional: bootstrapData.regional ?? null
          });
        }
      })
      .catch(() => {
        setAuthToken(null);
        setCurrentUser(null);
        setBootstrap(null);
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
    if ((summary || bootstrap) && loading) {
      setLoading(false);
    }
  }, [bootstrap, loading, summary]);

  useEffect(() => {
    if (!currentUser) return;

    if (activeTab === "history") {
      void loadHistoryData().catch((err: Error) => setError(err.message));
      return;
    }

    if (activeTab === "config") {
      if (configTab === "collaborators") {
        void loadCollaboratorRegistryData().catch((err: Error) => setError(err.message));
        // Carrega usuários junto (se o perfil atual puder gerenciá-los) pra habilitar a seção
        // "Acesso ao portal" no drawer de colaborador sem depender de visitar a aba Usuários antes.
        void loadUsersData().catch((err: Error) => setError(err.message));
        return;
      }
      if (configTab === "leadership") {
        void loadLeadershipProfilesData().catch((err: Error) => setError(err.message));
        return;
      }
      if (configTab === "users") {
        void loadUsersData().catch((err: Error) => setError(err.message));
        // Precisa da lista de colaboradores pro combobox "Colaborador vinculado" desta aba.
        void loadCollaboratorRegistryData().catch((err: Error) => setError(err.message));
        return;
      }
    }

    if (!summary) return;

    if (activeTab === "ranking" || activeTab === "audit") {
      void loadServiceOrdersSupport().catch((err: Error) => setError(err.message));
      return;
    }

    if (activeTab === "pending") {
      void loadPendingData(summary.run?.id).catch((err: Error) => setError(err.message));
      return;
    }

    if (activeTab === "config") {
      if (configTab === "rules") {
        void loadRulesConfigSupport(summary.run?.id).catch((err: Error) => setError(err.message));
        return;
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
        pendingItems: [],
        isClosed: false
      };
    }

    const pendingItems = [
      {
        label: "O.S sem regra de pontuação",
        value: summary.cards.unscored_service_orders,
        tab: "pending",
        icon: HelpCircle,
        help: "Assuntos importados que ainda não estão vinculados a um grupo."
      },
      {
        label: "Diagnósticos sem regra",
        value: summary.cards.diagnosis_unmapped_service_orders,
        tab: "pending",
        icon: ShieldAlert,
        help: "Diagnósticos encontrados sem regra de liberação ou anulação."
      },
      {
        label: "Colaboradores pendentes de cadastro",
        value: summary.leadership_bonus?.pending_collaborators.length ?? 0,
        tab: "config" as const,
        configSubTab: "collaborators" as const,
        icon: UsersRound,
        help: "Colaboradores com produção no período que ainda não estão formalmente cadastrados."
      }
    ];
    const pendingCount = pendingItems.reduce((total, item) => total + item.value, 0);
    const isClosed = summary.run?.status === "paid" || summary.run?.status === "cancelled";

    return {
      ready: pendingCount === 0,
      pendingCount,
      pendingItems,
      isClosed
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

  const closureBalanceImpact = useMemo(() => {
    const affected = (summary?.ranking ?? []).filter((score) => (score.balance_adjustment_points ?? 0) < 0);
    return {
      collaboratorCount: affected.length,
      points: affected.reduce((total, score) => total + (score.balance_adjustment_points ?? 0), 0)
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
      ...collaboratorRegistry.registered.map((item) => item.regional),
      ...collaboratorRegistry.unregistered.map((item) => item.regional),
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
  }, [collaboratorRegistry.registered, collaboratorRegistry.unregistered, regionalOptions]);

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
    return Array.from(new Set(configSubjectSummaries.map((order) => order.os_subject).filter(Boolean))).sort((a, b) =>
      a.localeCompare(b, "pt-BR")
    );
  }, [configSubjectSummaries]);

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
    const search = rankingSearch.trim().toLowerCase();
    return (summary.leadership_bonus?.results ?? [])
      .filter((item) => {
        const matchesRegional =
          selectedRegionals.length === 0 || item.regionals.some((regional) => selectedRegionals.includes(normalizeRegional(regional)));
        const matchesSearch =
          !search ||
          item.name.toLowerCase().includes(search) ||
          leadershipRoleLabel(item.role_type).toLowerCase().includes(search) ||
          (item.role_profile_name ?? "").toLowerCase().includes(search);
        return matchesRegional && matchesSearch;
      })
      .sort((a, b) => b.bonus_amount - a.bonus_amount || b.average_final_points - a.average_final_points || a.name.localeCompare(b.name, "pt-BR"));
  }, [rankingSearch, selectedRegionals, summary]);

  const leadershipCoveredRegionals = useMemo(() => {
    return Array.from(
      new Set(filteredLeadershipResults.flatMap((item) => item.regionals.map((regional) => normalizeRegional(regional)).filter(Boolean)))
    ).length;
  }, [filteredLeadershipResults]);

  const leadershipScopeTotals = useMemo(
    () => ({
      leaders: filteredLeadershipResults.length,
      scopedCollaborators: filteredLeadershipResults.reduce((total, item) => total + item.scoped_collaborators, 0),
      averageMultiplier: filteredLeadershipResults.length
        ? filteredLeadershipResults.reduce((total, item) => total + item.multiplier, 0) / filteredLeadershipResults.length
        : 0,
      baseAmount: filteredLeadershipResults.reduce((total, item) => total + item.base_amount, 0),
      bonusAmount: filteredLeadershipResults.reduce((total, item) => total + item.bonus_amount, 0)
    }),
    [filteredLeadershipResults]
  );

  const leadershipAudit = useMemo(() => {
    if (!summary || !selectedLeadershipResult) {
      return {
        collaborators: [] as LeadershipAverageAuditCollaborator[],
        totalFinalPoints: 0,
        averageFinalPoints: 0,
        differenceFromStoredAverage: 0,
        isExactAudit: false,
        explanation: "",
      };
    }

    if (selectedLeadershipResult.audit) {
      const sourceLabel = leadershipAverageSourceLabel(selectedLeadershipResult.average_source);
      return {
        collaborators: selectedLeadershipResult.audit.collaborators,
        totalFinalPoints: selectedLeadershipResult.audit.total_final_points,
        averageFinalPoints: selectedLeadershipResult.audit.average_final_points,
        differenceFromStoredAverage: Math.abs(selectedLeadershipResult.audit.average_final_points - selectedLeadershipResult.average_final_points),
        isExactAudit: true,
        explanation: `Esta auditoria usa a base salva no fechamento. Origem da média: ${sourceLabel}.`,
      };
    }

    const scopedRegionals = new Set(selectedLeadershipResult.regionals.map((regional) => normalizeRegional(regional)).filter(Boolean));
    const collaborators = summary.ranking
      .filter((score) => {
        if (!score.is_registered) return false;
        if (selectedLeadershipResult.role_type === "portfolio_manager") return true;
        return scopedRegionals.has(normalizeRegional(score.regional));
      })
      .sort((a, b) => b.final_points - a.final_points || b.estimated_payment - a.estimated_payment || a.collaborator_name.localeCompare(b.collaborator_name, "pt-BR"))
      .map((score) => ({
        collaborator_id: score.collaborator_id,
        collaborator_name: score.collaborator_name,
        role: score.role,
        regional: score.regional,
        source_type: "collaborator" as const,
        service_orders_count: score.service_orders_count,
        health_multiplier: score.health_multiplier,
        final_points: score.final_points,
        estimated_payment: score.estimated_payment,
      }));

    const totalFinalPoints = collaborators.reduce((total, score) => total + score.final_points, 0);
    const averageFinalPoints = collaborators.length ? totalFinalPoints / collaborators.length : 0;
    const reconstructedSource = selectedLeadershipResult.average_source === "collaborators_and_leaders"
      ? "A média original desta liderança considera colaboradores + líderes, mas esta visualização foi reconstituída no frontend com base no ranking disponível."
      : "Esta visualização foi reconstituída no frontend a partir do ranking disponível para conferência rápida.";

    return {
      collaborators,
      totalFinalPoints,
      averageFinalPoints,
      differenceFromStoredAverage: Math.abs(averageFinalPoints - selectedLeadershipResult.average_final_points),
      isExactAudit: false,
      explanation: reconstructedSource,
    };
  }, [selectedLeadershipResult, summary]);

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
    if (!filteredBreakdowns) {
      return {
        cost_by_regional: summary.cost_by_regional,
        cost_by_group: summary.cost_by_group,
        top_unmapped_subjects: summary.top_unmapped_subjects
      };
    }
    return {
      cost_by_regional: filteredBreakdowns.cost_by_regional,
      cost_by_group: filteredBreakdowns.cost_by_group,
      top_unmapped_subjects: filteredBreakdowns.top_unmapped_subjects
    };
  }, [filteredBreakdowns, summary]);

  useEffect(() => {
    if (!summary) {
      setChartPenalties([]);
      setFilteredBreakdowns(null);
      return;
    }
    if (selectedRegionals.length === 0 || !summary.run?.id) {
      setChartPenalties(summary.penalty_distribution);
      setFilteredBreakdowns(null);
      return;
    }

    let cancelled = false;
    api.dashboardFilteredBreakdowns(summary.run.id, selectedRegionals)
      .then((response) => {
        if (cancelled) return;
        setFilteredBreakdowns(response);
        setChartPenalties(response.penalty_distribution);
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setError(err.message);
          setChartPenalties(summary.penalty_distribution);
          setFilteredBreakdowns(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedRegionals, summary]);

  function updateSelectedRegionals(values: string[]) {
    setSelectedRegionals(values.map((value) => normalizeRegional(value)).filter(Boolean));
  }

  async function withFeedback<T>(action: () => Promise<T>, success: string | (() => string)): Promise<T | undefined> {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await action();
      setMessage(typeof success === "function" ? success() : success);
      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro inesperado.");
      return undefined;
    } finally {
      setBusy(false);
    }
  }

  // O backend agora recusa (409) recalcular tanto um período já pago quanto um período que não é
  // mais o mês corrente (fuso de Porto Velho) mesmo sem ter sido pago - em ambos os casos, exige
  // "create_revision" explícito. Em vez de prever isso no cliente (duplicando a regra de fuso
  // horário aqui), tenta sem revisão primeiro e só pergunta ao usuário se o backend recusar por um
  // desses dois motivos - qualquer outro erro sobe normalmente.
  const CLOSED_PERIOD_MESSAGE_MARKERS = ["já está marcado como pago", "não é mais o mês corrente"];

  async function calculateWithRevisionPrompt(
    value: number | null,
    period: { reference_month?: number; reference_year?: number; regional?: string | null },
    revisionExecutionNote: string
  ): Promise<boolean> {
    try {
      await api.calculate(value, period);
      return false;
    } catch (err) {
      const messageText = err instanceof Error ? err.message : "";
      const isClosedPeriod = CLOSED_PERIOD_MESSAGE_MARKERS.some((marker) => messageText.includes(marker));
      if (!isClosedPeriod) throw err;
      const shouldCreateRevision = await confirm({
        title: "Período já encerrado",
        description: `${messageText} Deseja criar uma revisão em rascunho sem alterar o fechamento original?`,
        confirmLabel: "Criar revisão"
      });
      if (!shouldCreateRevision) {
        throw new Error("Recálculo cancelado para preservar o período encerrado.");
      }
      await api.calculate(value, period, { create_revision: true, execution_note: revisionExecutionNote });
      return true;
    }
  }

  async function recalculate() {
    if (calculationInFlightRef.current) return;
    calculationInFlightRef.current = true;
    try {
      let wasRevision = false;
      await withFeedback(async () => {
        const safePeriod = {
          reference_month: analysisPeriod.reference_month ?? summary?.run?.reference_month ?? bootstrap?.reference_month ?? undefined,
          reference_year: analysisPeriod.reference_year ?? summary?.run?.reference_year ?? bootstrap?.reference_year ?? undefined,
          regional: analysisPeriod.regional ?? summary?.run?.regional ?? bootstrap?.regional ?? undefined
        };
        if (!safePeriod.reference_month || !safePeriod.reference_year) {
          throw new Error("Selecione um periodo valido antes de recalcular a pontuacao.");
        }
        const value = parseOptionalNumber(pointValue);
        if (value !== null) {
          await api.updateSetting("point_value", value.toFixed(2));
        }
        wasRevision = await calculateWithRevisionPrompt(value, safePeriod, "Revisão criada pela interface para um período já encerrado.");
        setAnalysisPeriod(safePeriod);
        await loadAll(safePeriod, { refreshRuleBasics: false });
      }, () => (wasRevision ? "Revisão em rascunho criada para o período encerrado." : "Pontuação recalculada com matriz operacional."));
    } finally {
      calculationInFlightRef.current = false;
    }
  }

  async function refreshAfterCollaboratorRegistryChange() {
    // Um fechamento encerrado (pago, ou que já não é mais o mês corrente no fuso de Porto Velho) é
    // imutável: recalcular sem "create_revision" seria rejeitado pelo backend (409) e, como esse
    // erro interrompia esta função ANTES de recarregar a lista de colaboradores, a aprovação
    // parecia ter falhado mesmo já tendo sido salva no banco. O caso "pago" já era evitado
    // proativamente (só tenta se status !== "paid"); o caso "mês já virou" só dá pra saber
    // reativamente (não duplicamos aqui a regra de fuso horário do backend), então é ignorado
    // silenciosamente - o dashboard só não atualiza para aquele período específico.
    if (summary?.run && summary.run.status !== "paid") {
      try {
        await api.calculate(summary.run.point_value ?? summary.point_value, {
          reference_month: summary.run.reference_month,
          reference_year: summary.run.reference_year,
          regional: summary.run.regional
        });
      } catch (err) {
        const messageText = err instanceof Error ? err.message : "";
        if (!messageText.includes("não é mais o mês corrente")) {
          throw err;
        }
      }
    }
    await loadAll(undefined, { refreshRuleBasics: false });
  }

  async function calculatePeriod(month: number, year: number) {
    let wasRevision = false;
    await withFeedback(async () => {
      const value = parseOptionalNumber(pointValue);
      const requestedPeriod = {
        reference_month: month,
        reference_year: year,
        regional: summary?.run?.regional
      };
      if (value !== null) {
        await api.updateSetting("point_value", value.toFixed(2));
      }
      wasRevision = await calculateWithRevisionPrompt(value, requestedPeriod, "Revisão criada pela seleção de período para um período já encerrado.");
      const period = { reference_month: month, reference_year: year, regional: summary?.run?.regional };
      setAnalysisPeriod(period);
      await loadAll(period, { refreshRuleBasics: false });
    }, () => (wasRevision ? "Revisão em rascunho criada para o período encerrado." : "Período recalculado com janela de reincidência."));
  }

  async function viewPeriod(month: number, year: number) {
    await withFeedback(async () => {
      const period = { reference_month: month, reference_year: year, regional: summary?.run?.regional };
      setAnalysisPeriod(period);
      await loadAll(period, { refreshRuleBasics: false });
    }, "Período de análise alterado.");
  }

  async function advanceRunStatus(nextStatus: "review" | "approved" | "paid" | "cancelled", successMessage: string) {
    const runId = summary?.run?.id;
    if (!runId) {
      setError("Nenhum fechamento calculado para avançar o status. Recalcule o período primeiro.");
      return;
    }
    if (nextStatus === "paid") {
      const confirmed = await confirm({
        title: "Marcar como pago",
        description:
          "Marcar este fechamento como PAGO é definitivo e não pode ser revertido. " +
          "A partir daqui, débitos de garantia pendentes dos colaboradores serão aplicados. Deseja continuar?",
        confirmLabel: "Marcar como pago",
        tone: "danger"
      });
      if (!confirmed) return;
    }
    if (nextStatus === "cancelled") {
      const confirmed = await confirm({
        title: "Cancelar fechamento",
        description: "Cancelar este fechamento? Ele não poderá mais ser aprovado ou pago.",
        confirmLabel: "Cancelar fechamento",
        tone: "danger"
      });
      if (!confirmed) return;
    }
    await withFeedback(async () => {
      await api.updateCalculationRunStatus(runId, { status: nextStatus });
      const period = {
        reference_month: summary?.run?.reference_month,
        reference_year: summary?.run?.reference_year,
        regional: summary?.run?.regional
      };
      await loadAll(period, { refreshRuleBasics: false });
      setHistoryLoaded(false);
    }, successMessage);
  }

  function exportPaymentCsv() {
    if (!summary || currentUser?.role === "viewer") return;
    const healthByRegional = new Map(
      summary.health_by_regional.map((item) => [normalizeRegional(item.regional), item])
    );
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
      [
        "Colaborador",
        "Regional",
        "Tipo",
        "O.S",
        "Pontos brutos",
        "Pontos anulados",
        "Pontos líquidos",
        "SLA da base (%)",
        "Multiplicador saúde",
        "Pontos finais",
        "Valor a ser pago"
      ],
      ...paymentRows.map((score) => {
        const regionalHealth = healthByRegional.get(normalizeRegional(score.regional));
        return [
          score.collaborator_name,
          regionalName(score.regional),
          "Técnico",
          formatNumber(score.service_orders_count),
          formatPoints(score.gross_points),
          formatPoints(score.penalty_points),
          formatPoints(score.net_points),
          regionalHealth ? `${formatNumber(regionalHealth.sla_rate)}%` : "-",
          `${formatNumber(score.health_multiplier)}x`,
          formatPoints(score.final_points),
          formatMoney(score.estimated_payment)
        ];
      }),
      [],
      ["Bonificação de liderança"],
      [
        "Liderança",
        "Regionais",
        "Tipo",
        "Origem da média",
        "Pessoas na média",
        "Soma dos pontos",
        "Média final",
        "Multiplicador",
        "Valor a ser pago"
      ],
      ...leadershipRows.map((item) => [
        item.name,
        item.regionals.map((regional) => regionalName(regional)).join(", "),
        leadershipRoleLabel(item.role_type),
        leadershipAverageSourceLabel(item.average_source),
        formatNumber(item.audit?.scoped_collaborators ?? item.scoped_collaborators),
        `${formatNumber(item.audit?.total_final_points ?? item.average_final_points * item.scoped_collaborators)} pts`,
        `${formatNumber(item.average_final_points)} pts`,
        `${formatNumber(item.multiplier)}x`,
        formatMoney(item.bonus_amount)
      ]),
      [],
      ["Pendentes de cadastro"],
      ["Nome identificado", "Regional sugerida", "O.S", "Valor potencial", "Status"],
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
              className="h-11 rounded-lg bg-primary font-semibold text-primary-foreground shadow-sm transition hover:bg-primary/90 disabled:bg-slate-300"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {busy ? "Entrando..." : "Entrar"}
            </Button>
          </div>
        </section>
      </main>
    );
  }

  const visibleTabs = new Set<string>(["closure", "ranking", "audit", "balance", "history", "import"]);
  if (can("orders:import") || can("scoring:write")) visibleTabs.add("pending");
  if (can("scoring:write")) visibleTabs.add("config");

  return (
    <main className="min-h-dvh bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.12),transparent_24%),radial-gradient(circle_at_top_right,rgba(37,99,235,0.08),transparent_20%),linear-gradient(180deg,#f8fbff_0%,#f8fafc_42%,#f8fafc_100%)]">
      <div className="flex min-h-dvh w-full">
        <ModuleSidebar
          activeTab={activeTab}
          onTabChange={setActiveTab}
          visibleTabs={visibleTabs}
          user={currentUser}
          onLogout={logout}
          canRecalculate={can("calculation:run")}
          onRecalculate={recalculate}
          recalculating={busy || loading}
          isPaidPeriod={summary?.run?.status === "paid"}
        />
        <div className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto flex w-full max-w-[1680px] flex-col gap-4 px-2 py-3 sm:px-4">
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

        {loading && !bootstrap ? (
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
                    <span>{activeTab === "closure" ? "Fechamento" : activeTab === "ranking" ? "Ranking" : activeTab === "pending" ? "Pendências" : activeTab === "config" ? "Configuração" : activeTab === "audit" ? "Auditoria" : activeTab === "balance" ? "Saldo de pontos" : activeTab === "history" ? "Histórico" : "Período"}</span>
                    <InfoHint
                      ariaLabel={`Ajuda sobre a aba ${activeTab === "closure" ? "Fechamento" : activeTab === "ranking" ? "Ranking" : activeTab === "pending" ? "Pendências" : activeTab === "config" ? "Configuração" : activeTab === "audit" ? "Auditoria" : activeTab === "balance" ? "Saldo de pontos" : activeTab === "history" ? "Histórico" : "Período"}`}
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
                            : activeTab === "balance"
                              ? "Saldo de garantias"
                              : activeTab === "history"
                                ? "Histórico"
                                : "Período analisado"}
                </Badge>
              </div>
            </section>

            <TabsContent value="closure" className="mt-0 flex-1 pr-1">
              {activeTab === "closure" ? (
                !summary ? (
                  <div className="panel p-8 text-sm text-slate-500">Carregando resumo executivo e indicadores do fechamento...</div>
                ) : (
                <div className="grid gap-4">
                  <section className="overflow-hidden rounded-[24px] border border-slate-200/80 bg-white shadow-sm">
                    <div
                      className={
                        closure.ready || closure.isClosed
                          ? "grid gap-5 bg-[radial-gradient(circle_at_top_left,rgba(16,185,129,0.08),transparent_22%),linear-gradient(180deg,#ffffff_0%,#fbfdff_100%)] p-5"
                          : "grid gap-5 bg-[radial-gradient(circle_at_top_left,rgba(245,158,11,0.08),transparent_22%),linear-gradient(180deg,#ffffff_0%,#fbfdff_100%)] p-5"
                      }
                    >
                      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            {closure.isClosed ? (
                              <Badge className={summary.run?.status === "paid" ? "w-fit border-emerald-200 bg-white text-emerald-700" : "w-fit border-rose-200 bg-white text-rose-700"}>
                                <CheckCircle2 className="h-3.5 w-3.5" />
                                {summary.run?.status === "paid" ? "Fechamento pago" : "Fechamento cancelado"}
                              </Badge>
                            ) : (
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
                            )}
                            <Badge className="w-fit border-slate-200 bg-white text-slate-700">
                              <CalendarDays className="h-3.5 w-3.5" />
                              {summary.run ? `${summary.run.reference_month}/${summary.run.reference_year}` : "Sem cálculo"}
                            </Badge>
                            {summary.run ? (
                              <Badge className={calculationStatusMeta(summary.run.status).className}>
                                <ClipboardList className="h-3.5 w-3.5" />
                                {calculationStatusMeta(summary.run.status).label}
                              </Badge>
                            ) : null}
                          </div>
                          <div className="mt-3 flex items-center gap-2">
                            <h2 className="text-2xl font-semibold leading-tight text-slate-950">
                              {closure.isClosed || closure.ready ? "Resumo financeiro da competência" : "Regras pendentes antes do pagamento"}
                            </h2>
                            <InfoHint
                              ariaLabel={`Ajuda sobre ${closure.isClosed || closure.ready ? "Resumo financeiro da competência" : "Regras pendentes antes do pagamento"}`}
                              description={SECTION_HELP.summary}
                            />
                          </div>
                          {closure.isClosed && closure.pendingCount > 0 ? (
                            <p className="mt-2 text-sm text-amber-700">
                              Este fechamento tinha {formatNumber(closure.pendingCount)} pendência(s) de governança registrada(s) no momento do pagamento. Veja abaixo.
                            </p>
                          ) : null}
                          {summary.run?.status_note ? (
                            <p className="mt-2 text-sm text-slate-500">{summary.run.status_note}</p>
                          ) : null}
                        </div>
                        <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap sm:items-center sm:justify-end">
                          {currentUser.role !== "viewer" ? (
                            <Button type="button" variant="outline" onClick={exportPaymentCsv} className="w-full bg-white sm:w-auto">
                              <Download className="h-4 w-4" />
                              Exportar pagamento
                            </Button>
                          ) : null}
                          {summary.run && can("calculation:run") ? (
                            <>
                              {summary.run.status === "draft" ? (
                                <Button
                                  type="button"
                                  onClick={() => advanceRunStatus("review", "Fechamento enviado para conferência.")}
                                  disabled={busy}
                                  className="w-full bg-amber-600 text-white hover:bg-amber-700 sm:w-auto"
                                >
                                  <Send className="h-4 w-4" />
                                  Enviar para conferência
                                </Button>
                              ) : null}
                              {summary.run.status === "review" && currentUser.role === "admin" ? (
                                <Button
                                  type="button"
                                  onClick={() => advanceRunStatus("approved", "Fechamento aprovado.")}
                                  disabled={busy}
                                  className="w-full bg-sky-600 text-white hover:bg-sky-700 sm:w-auto"
                                >
                                  <CheckCircle2 className="h-4 w-4" />
                                  Aprovar fechamento
                                </Button>
                              ) : null}
                              {summary.run.status === "approved" && currentUser.role === "admin" ? (
                                <Button
                                  type="button"
                                  onClick={() => advanceRunStatus("paid", "Fechamento marcado como pago.")}
                                  disabled={busy}
                                  className="w-full bg-emerald-600 text-white hover:bg-emerald-700 sm:w-auto"
                                >
                                  <Wallet className="h-4 w-4" />
                                  Marcar como pago
                                </Button>
                              ) : null}
                              {["draft", "review", "approved"].includes(summary.run.status) ? (
                                <Button
                                  type="button"
                                  variant="outline"
                                  onClick={() => advanceRunStatus("cancelled", "Fechamento cancelado.")}
                                  disabled={busy}
                                  className="w-full bg-white text-rose-600 hover:bg-rose-50 sm:w-auto"
                                >
                                  <XCircle className="h-4 w-4" />
                                  Cancelar
                                </Button>
                              ) : null}
                            </>
                          ) : null}
                        </div>
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

                      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
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
                          },
                          {
                            label: "Descontos de garantia",
                            value: closureBalanceImpact.collaboratorCount > 0 ? formatPoints(Math.abs(closureBalanceImpact.points)) : "Sem descontos",
                            sub: closureBalanceImpact.collaboratorCount > 0 ? `em ${formatNumber(closureBalanceImpact.collaboratorCount)} colaborador(es)` : undefined,
                            icon: MinusCircle,
                            tone: closureBalanceImpact.collaboratorCount > 0 ? "text-red-700" : "text-slate-700",
                            onClick: closureBalanceImpact.collaboratorCount > 0 ? () => setActiveTab("balance") : undefined
                          }
                        ].map((item) => {
                          const Icon = item.icon;
                          const content = (
                            <>
                              <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                                <Icon className="h-3.5 w-3.5" />
                                <span className="truncate">{item.label}</span>
                              </div>
                              <div className={`mt-3 truncate text-[28px] font-semibold leading-none ${item.tone}`}>{item.value}</div>
                              {item.sub ? <div className="mt-1 truncate text-xs text-slate-500">{item.sub}</div> : null}
                            </>
                          );
                          if (item.onClick) {
                            return (
                              <button
                                key={item.label}
                                type="button"
                                onClick={item.onClick}
                                className="min-w-0 rounded-[20px] border border-slate-200 bg-white p-4 text-left shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition hover:border-teal-300 hover:bg-teal-50/40"
                              >
                                {content}
                              </button>
                            );
                          }
                          return (
                            <div key={item.label} className="min-w-0 rounded-[20px] border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
                              {content}
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
                        <div className="flex items-start gap-3 px-5 py-4 transition hover:bg-slate-50/80">
                          <AccordionTrigger asChild>
                            <button type="button" className="flex min-w-0 flex-1 items-center justify-between gap-4 text-left">
                              <div className="flex min-w-0 items-start gap-3">
                                <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-amber-50 text-amber-700">
                                  <AlertTriangle className="h-4 w-4" />
                                </div>
                                <div className="min-w-0">
                                  <div className="text-sm font-semibold text-slate-950">
                                    {closure.isClosed ? "Pendências registradas no fechamento" : "Alertas e pendências"}
                                  </div>
                                </div>
                              </div>
                              <Badge className={closure.pendingCount > 0 ? "border-amber-200 bg-amber-50 text-amber-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}>
                                {closure.pendingCount > 0 ? `${formatNumber(closure.pendingCount)} pendência(s)` : "Sem pendências"}
                              </Badge>
                            </button>
                          </AccordionTrigger>
                          <InfoHint ariaLabel="Ajuda sobre Alertas e pendências" description={SECTION_HELP.alerts} />
                        </div>
                        <AccordionContent className="px-5 pb-5">
                          {closure.pendingCount > 0 ? (
                            <div className="grid gap-3 rounded-[20px] border border-slate-200 bg-slate-50/60 p-3 md:grid-cols-2">
                              {closure.pendingItems.map((item) => {
                                const Icon = item.icon;
                                return (
                                  <button
                                    key={item.label}
                                    className="rounded-[18px] border border-slate-200 bg-white p-4 text-left shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition hover:border-teal-300 hover:bg-teal-50/40"
                                    onClick={() => {
                                      setActiveTab(item.tab);
                                      if ("configSubTab" in item && item.configSubTab) setConfigTab(item.configSubTab);
                                    }}
                                  >
                                    <div className="flex items-center justify-between gap-3">
                                      <div className={item.value > 0 ? "text-2xl font-semibold text-amber-700" : "text-2xl font-semibold text-emerald-700"}>
                                        {formatNumber(item.value)}
                                      </div>
                                      <div
                                        className={
                                          item.value > 0
                                            ? "flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-amber-50 text-amber-700"
                                            : "flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-emerald-50 text-emerald-700"
                                        }
                                      >
                                        <Icon className="h-4 w-4" />
                                      </div>
                                    </div>
                                    <div className="mt-1 text-sm font-semibold text-slate-950">{item.label}</div>
                                    <div className="mt-2 text-xs text-slate-500">{item.help}</div>
                                  </button>
                                );
                              })}
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
                        <div className="flex items-start gap-3 px-5 py-4 transition hover:bg-slate-50/80">
                          <AccordionTrigger asChild>
                            <button type="button" className="flex min-w-0 flex-1 items-center justify-between gap-4 text-left">
                              <div className="flex min-w-0 items-start gap-3">
                                <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-blue-50 text-blue-700">
                                  <Trophy className="h-4 w-4" />
                                </div>
                                <div className="min-w-0">
                                  <div className="text-sm font-semibold text-slate-950">Bonificação de liderança</div>
                                </div>
                              </div>
                              <Badge className="border-blue-200 bg-blue-50 text-blue-700">{formatMoney(summary.leadership_bonus?.total_bonus_amount ?? 0)}</Badge>
                            </button>
                          </AccordionTrigger>
                          <InfoHint ariaLabel="Ajuda sobre Bonificação de liderança" description={SECTION_HELP.leadership} />
                        </div>
                        <AccordionContent className="px-5 pb-5">
                          <div className="grid gap-3 rounded-[20px] border border-slate-200 bg-slate-50/60 p-3 md:grid-cols-3">
                            {[
                              ["Valor da liderança", formatMoney(summary.leadership_bonus?.total_bonus_amount ?? 0)],
                              ["Perfis ativos", `${formatNumber(summary.leadership_bonus?.results.length ?? 0)} líder(es)`],
                              ["Filiais cobertas", `${formatNumber(leadershipCoveredRegionals)} ${pluralizeFilial(leadershipCoveredRegionals)}`]
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
                        <div className="flex items-start gap-3 px-5 py-4 transition hover:bg-slate-50/80">
                          <AccordionTrigger asChild>
                            <button type="button" className="flex min-w-0 flex-1 items-center justify-between gap-4 text-left">
                              <div className="flex min-w-0 items-start gap-3">
                                <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-teal-50 text-teal-700">
                                  <CircleDollarSign className="h-4 w-4" />
                                </div>
                                <div className="min-w-0">
                                  <div className="text-sm font-semibold text-slate-950">Detalhamento financeiro</div>
                                </div>
                              </div>
                              <Badge className="border-slate-200 bg-slate-50 text-slate-700">3 painéis</Badge>
                            </button>
                          </AccordionTrigger>
                          <InfoHint ariaLabel="Ajuda sobre Detalhamento financeiro" description={SECTION_HELP.financial} />
                        </div>
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
                        <div className="flex items-start gap-3 px-5 py-4 transition hover:bg-slate-50/80">
                          <AccordionTrigger asChild>
                            <button type="button" className="flex min-w-0 flex-1 items-center justify-between gap-4 text-left">
                              <div className="flex min-w-0 items-start gap-3">
                                <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-violet-50 text-violet-700">
                                  <BarChart3 className="h-4 w-4" />
                                </div>
                                <div className="min-w-0">
                                  <div className="text-sm font-semibold text-slate-950">Análise operacional e gráficos</div>
                                </div>
                              </div>
                              <Badge className="border-slate-200 bg-slate-50 text-slate-700">{selectedRegionals.length ? `${selectedRegionals.length} ${pluralizeFilial(selectedRegionals.length)}` : "Todas as filiais"}</Badge>
                            </button>
                          </AccordionTrigger>
                          <InfoHint ariaLabel="Ajuda sobre Análise operacional e gráficos" description={SECTION_HELP.chartArea} />
                        </div>
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
                                <span>{selectedRegionals.length ? `${selectedRegionals.length} ${pluralizeFilial(selectedRegionals.length, " selecionada")}` : "Todas as filiais"}</span>
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
                )
              ) : null}
            </TabsContent>

            <TabsContent value="ranking" className="mt-0 flex-1 overflow-visible">
              {activeTab === "ranking" ? (
                !summary ? (
                  <div className="panel p-8 text-sm text-slate-500">Carregando resumo consolidado para montar o ranking...</div>
                ) : !serviceOrdersLoaded && tabLoading.serviceOrders ? (
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
                          <div className="grid gap-2 xl:min-w-[520px]">
                            <div className="grid gap-1.5">
                              <div className="flex items-center justify-between gap-2">
                                <span className="text-[11px] font-medium text-slate-500">
                                  {selectedRegionals.length ? `${selectedRegionals.length} ${pluralizeFilial(selectedRegionals.length, " selecionada")}` : "Todas as filiais"}
                                </span>
                                <Button type="button" variant="ghost" size="sm" className="h-6 px-2" onClick={() => setSelectedRegionals([])} disabled={selectedRegionals.length === 0}>
                                  Limpar
                                </Button>
                              </div>
                              <div className="flex max-h-20 flex-wrap gap-1.5 overflow-y-auto rounded-md border border-slate-200 bg-slate-50 p-2">
                                {regionalOptions.map((regional) => {
                                  const normalized = normalizeRegional(regional);
                                  const active = selectedRegionals.includes(normalized);
                                  return (
                                    <button
                                      key={regional}
                                      type="button"
                                      onClick={() =>
                                        updateSelectedRegionals(
                                          active ? selectedRegionals.filter((value) => value !== normalized) : [...selectedRegionals, normalized]
                                        )
                                      }
                                      className={
                                        active
                                          ? "shrink-0 rounded-full border border-teal-600 bg-teal-600 px-3 py-1 text-xs font-medium text-white"
                                          : "shrink-0 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-600 hover:border-teal-300 hover:bg-teal-50/40"
                                      }
                                    >
                                      {regionalName(regional)}
                                    </button>
                                  );
                                })}
                              </div>
                            </div>
                            <div className="relative">
                              <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
                              <Input
                                className="h-9 pl-9"
                                value={rankingSearch}
                                onChange={(event) => setRankingSearch(event.target.value)}
                                placeholder={rankingTab === "collaborators" ? "Buscar colaborador" : "Buscar líder ou perfil"}
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
                                { label: "O.S no ranking", value: `${formatNumber(rankingScopeTotals.serviceOrders)} O.S`, icon: ClipboardList, tone: "neutral" as const },
                                { label: "Fora do ranking", value: `${formatNumber(outsideRankingCount)} O.S`, icon: XCircle, tone: outsideRankingCount > 0 ? ("warning" as const) : ("good" as const) },
                                { label: "O.S pontuadas", value: `${formatNumber(rankingScopeTotals.scored)} O.S`, icon: CheckCircle2, tone: "good" as const },
                                { label: "O.S sem regra", value: `${formatNumber(rankingScopeTotals.unscored)} O.S`, icon: HelpCircle, tone: rankingScopeTotals.unscored > 0 ? ("warning" as const) : ("good" as const) },
                                { label: "Valor a ser pago", value: formatMoney(rankingScopeTotals.estimated), icon: CircleDollarSign, tone: "info" as const }
                              ].map((item) => {
                                const Icon = item.icon;
                                const iconToneClass =
                                  item.tone === "warning"
                                    ? "bg-amber-100 text-amber-700"
                                    : item.tone === "good"
                                      ? "bg-emerald-100 text-emerald-700"
                                      : item.tone === "info"
                                        ? "bg-blue-100 text-blue-700"
                                        : "bg-slate-200 text-slate-600";
                                return (
                                  <div key={item.label} className="min-w-0 rounded-md border bg-white px-3 py-2">
                                    <div className="flex items-center gap-2">
                                      <div className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md ${iconToneClass}`}>
                                        <Icon className="h-3.5 w-3.5" />
                                      </div>
                                      <div className="truncate text-[10px] font-semibold uppercase tracking-wide text-slate-500">{item.label}</div>
                                    </div>
                                    <div className="mt-1 truncate text-sm font-semibold text-slate-950">{item.value}</div>
                                  </div>
                                );
                              })}
                            </div>
                          </TabsContent>

                          <TabsContent value="leaders" className="mt-0 grid gap-4">
                            <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
                              <span className="font-medium text-slate-800">
                                Escopo atual: {formatNumber(filteredLeadershipResults.length)} líder(es) no recorte
                              </span>{" "}
                              |{" "}
                              {formatNumber(leadershipCoveredRegionals)} {pluralizeFilial(leadershipCoveredRegionals, " coberta")}.
                              {rankingSearch.trim() ? " A busca filtra a tabela abaixo, sem alterar o resumo financeiro do período." : ""}
                            </div>

                            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
                              {[
                                { label: "Líderes no ranking", value: `${formatNumber(leadershipScopeTotals.leaders)} líder(es)`, icon: Trophy, tone: "info" as const },
                                { label: "Filiais cobertas", value: `${formatNumber(leadershipCoveredRegionals)} ${pluralizeFilial(leadershipCoveredRegionals)}`, icon: MapPin, tone: "neutral" as const },
                                { label: "Colaboradores na base", value: `${formatNumber(leadershipScopeTotals.scopedCollaborators)} colaborador(es)`, icon: UsersRound, tone: "neutral" as const },
                                { label: "Multiplicador médio", value: leadershipScopeTotals.leaders ? `${formatNumber(leadershipScopeTotals.averageMultiplier)}x` : "0x", icon: BarChart3, tone: "neutral" as const },
                                { label: "Valor a pagar", value: formatMoney(leadershipScopeTotals.bonusAmount), icon: CircleDollarSign, tone: "info" as const }
                              ].map((item) => {
                                const Icon = item.icon;
                                const iconToneClass = item.tone === "info" ? "bg-blue-100 text-blue-700" : "bg-slate-200 text-slate-600";
                                return (
                                  <div key={item.label} className="min-w-0 rounded-md border bg-white px-3 py-2">
                                    <div className="flex items-center gap-2">
                                      <div className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md ${iconToneClass}`}>
                                        <Icon className="h-3.5 w-3.5" />
                                      </div>
                                      <div className="truncate text-[10px] font-semibold uppercase tracking-wide text-slate-500">{item.label}</div>
                                    </div>
                                    <div className="mt-1 truncate text-sm font-semibold text-slate-950">{item.value}</div>
                                  </div>
                                );
                              })}
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
                          <div className="table-frame h-full overflow-auto px-2 py-2">
                            <div className="rounded-xl border border-slate-200 bg-white">
                              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
                                <div>
                                  <div className="text-sm font-semibold text-slate-950">Ranking de liderança</div>
                                  <div className="text-xs text-slate-500">Ordenado pelo valor a pagar no recorte atual.</div>
                                </div>
                                <Badge className="border-slate-200 bg-slate-50 text-slate-700">
                                  Base financeira {formatMoney(leadershipScopeTotals.baseAmount)}
                                </Badge>
                              </div>
                              <Table>
                                <TableHeader>
                                  <TableRow>
                                    <TableHead>Líder</TableHead>
                                    <TableHead>Perfil</TableHead>
                                    <TableHead>Filiais cobertas</TableHead>
                                    <TableHead>Base</TableHead>
                                    <TableHead>Média final</TableHead>
                                    <TableHead>Multiplicador</TableHead>
                                    <TableHead className="text-right">Valor a pagar</TableHead>
                                  </TableRow>
                                </TableHeader>
                                <TableBody>
                                  {filteredLeadershipResults.map((item) => {
                                    const normalizedRegionals = item.regionals.map((regional) => regionalName(regional));
                                    const regionalSummary = summarizeLabels(normalizedRegionals);
                                    const roleLabel = leadershipRoleLabel(item.role_type);
                                    const profileLabel =
                                      item.role_profile_name && item.role_profile_name !== roleLabel ? item.role_profile_name : roleLabel;
                                    return (
                                      <TableRow key={`${item.leadership_profile_id}-${item.role_type}`}>
                                        <TableCell className="min-w-[220px]">
                                          <div className="grid gap-1">
                                            <div className="font-semibold text-slate-950">{item.name}</div>
                                            <div className="text-xs text-slate-500">{profileLabel}</div>
                                          </div>
                                        </TableCell>
                                        <TableCell>
                                          <Badge className="border-blue-200 bg-blue-50 text-blue-700">{profileLabel}</Badge>
                                        </TableCell>
                                        <TableCell className="min-w-[280px]">
                                          <div className="flex flex-wrap gap-1.5">
                                            {regionalSummary.visible.map((regional) => (
                                              <Badge key={`${item.leadership_profile_id}-${regional}`} className="border-slate-200 bg-slate-50 text-slate-700">
                                                {regional}
                                              </Badge>
                                            ))}
                                            {regionalSummary.remaining > 0 ? (
                                              <Badge className="border-slate-200 bg-white text-slate-500">+{regionalSummary.remaining}</Badge>
                                            ) : null}
                                          </div>
                                        </TableCell>
                                        <TableCell>
                                          <div className="grid gap-0.5">
                                            <span className="font-medium text-slate-900">{formatNumber(item.scoped_collaborators)} pessoa(s)</span>
                                            <span className="text-xs text-slate-500">{leadershipAverageSourceLabel(item.average_source)} - {formatMoney(item.base_amount)}</span>
                                          </div>
                                        </TableCell>
                                        <TableCell>
                                          <div className="grid gap-2">
                                            <span className="font-medium text-slate-950">{formatPoints(item.average_final_points)}</span>
                                            <Button
                                              type="button"
                                              size="sm"
                                              className="h-8 w-fit rounded-full border border-teal-600 bg-teal-600 px-3 text-[11px] font-semibold text-white shadow-sm hover:bg-teal-700"
                                              onClick={() => setSelectedLeadershipResult(item)}
                                            >
                                              <Search className="h-3.5 w-3.5" />
                                              Auditar média
                                            </Button>
                                          </div>
                                        </TableCell>
                                        <TableCell>
                                          <div className="grid gap-0.5">
                                            <span className="font-medium text-slate-900">{formatNumber(item.multiplier)}x</span>
                                            <span className="text-xs text-slate-500">{item.point_value > 0 ? `${formatMoney(item.point_value)}/pt` : "Sem valor"}</span>
                                          </div>
                                        </TableCell>
                                        <TableCell className="text-right">
                                          <span className="font-semibold text-teal-700">{formatMoney(item.bonus_amount)}</span>
                                        </TableCell>
                                      </TableRow>
                                    );
                                  })}
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
                  onAnalyzePeriod={calculatePeriod}
                  onViewPeriod={viewPeriod}
                  canImport={can("orders:import")}
                  canCalculate={can("calculation:run")}
                  currentPeriod={{
                    reference_month: summary?.run?.reference_month ?? bootstrap?.reference_month ?? undefined,
                    reference_year: summary?.run?.reference_year ?? bootstrap?.reference_year ?? undefined
                  }}
                  busy={busy}
                />
              ) : null}
            </TabsContent>

            <TabsContent value="pending" className="mt-0 flex-1 pr-1">
              {activeTab === "pending" ? (
                !summary ? (
                  <div className="panel p-8 text-sm text-slate-500">Carregando resumo consolidado antes de abrir as pendencias...</div>
                ) : !pendingDataLoaded && tabLoading.pending ? (
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
                      {[
                        {
                          label: "O.S sem regra",
                          value: `${formatNumber(summary.cards.unscored_service_orders)} O.S`,
                          help: "Assuntos que precisam de grupo de pontuação.",
                          icon: HelpCircle,
                          tone: summary.cards.unscored_service_orders > 0 ? "warning" : "good"
                        },
                        {
                          label: "Diagnósticos sem regra",
                          value: `${formatNumber(summary.cards.diagnosis_unmapped_service_orders)} O.S`,
                          help: "Diagnósticos que ainda precisam de decisão.",
                          icon: ShieldAlert,
                          tone: summary.cards.diagnosis_unmapped_service_orders > 0 ? "warning" : "good"
                        },
                        {
                          label: "Total pendente",
                          value: `${formatNumber(summary.cards.closure_pending_service_orders ?? (summary.cards.unscored_service_orders + summary.cards.diagnosis_unmapped_service_orders))} O.S`,
                          help: "Conta O.S únicas com assunto sem grupo ou diagnóstico sem regra, sem duplicar a mesma ordem.",
                          icon: ClipboardList,
                          tone: "neutral"
                        }
                      ].map((item) => {
                        const Icon = item.icon;
                        const toneClass =
                          item.tone === "warning"
                            ? { badge: "bg-amber-100 text-amber-700", value: "text-amber-700" }
                            : item.tone === "good"
                              ? { badge: "bg-emerald-100 text-emerald-700", value: "text-emerald-700" }
                              : { badge: "bg-slate-200 text-slate-600", value: "text-slate-950" };
                        return (
                          <div key={item.label} className="rounded-lg border bg-slate-50/70 p-4">
                            <div className="flex items-center gap-2">
                              <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${toneClass.badge}`}>
                                <Icon className="h-4 w-4" />
                              </div>
                              <div className="text-xs font-medium uppercase text-slate-500">{item.label}</div>
                            </div>
                            <div className={`mt-2 text-2xl font-semibold ${toneClass.value}`}>{item.value}</div>
                            <p className="mt-1 text-xs text-slate-500">{item.help}</p>
                          </div>
                        );
                      })}
                    </div>
                  </section>

                  <UnmappedSubjectsPanel
                    groups={groups}
                    subjects={unmappedSubjects}
                    osTypeOptions={unmappedOsTypeOptions}
                    onLinkSubject={(subject, groupId, osType) =>
                      withFeedback(async () => {
                        await api.linkSubjectToGroup({
                          group_id: groupId,
                          os_type: osType,
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
                            os_type: item.osType,
                            os_subject: item.subject.os_subject
                          }))
                        );
                        await loadAll();
                      }, `${items.length} assunto(s) vinculados em massa.`)
                    }
                    onCreateGroupForSubject={(subject, osType) =>
                      withFeedback(async () => {
                        const group = await api.createScoringGroup({
                          name: `Grupo - ${subject.os_subject}`.slice(0, 150),
                          description: `Criado a partir do assunto sem regra: ${subject.os_subject}`,
                          default_points: 0,
                          active: true
                        });
                        await api.linkSubjectToGroup({
                          group_id: group.id,
                          os_type: osType,
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
                    {!collaboratorRegistryEverLoadedRef.current && tabLoading.collaborators ? (
                      <div className="panel p-8 text-sm text-slate-500">Carregando cadastro de colaboradores...</div>
                    ) : (
                    <CollaboratorRegistryPanel
                      registry={collaboratorRegistry}
                      regionalOptions={collaboratorRegionalOptions}
                      onCreate={(payload) =>
                        withFeedback(async () => {
                          const created = await api.createCollaborator({
                            ...payload,
                            role: payload.role || "Importado UpValue",
                            regional: regionalName(payload.regional),
                          });
                          await refreshAfterCollaboratorRegistryChange();
                          return created.id;
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
                            phone: item.phone,
                            email: item.email,
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
                      canManagePortalAccess={can("users:manage")}
                      unlinkedUsers={users.filter((item) => item.collaborator_id == null)}
                      onCreatePortalUser={({ collaboratorId, email, password }) =>
                        withFeedback(async () => {
                          const collaborator = [...collaboratorRegistry.registered, ...collaboratorRegistry.unregistered].find(
                            (item) => item.id === collaboratorId
                          );
                          await api.createUser({
                            name: collaborator?.name || email,
                            email,
                            password,
                            role: "collaborator",
                            active: true,
                            collaborator_id: collaboratorId,
                          });
                          setUsers(await api.users());
                          await refreshAfterCollaboratorRegistryChange();
                        }, "Acesso ao portal criado.")
                      }
                      onLinkPortalUser={({ userId, collaboratorId }) =>
                        withFeedback(async () => {
                          await api.updateUser(userId, { collaborator_id: collaboratorId });
                          setUsers(await api.users());
                          await refreshAfterCollaboratorRegistryChange();
                        }, "Colaborador vinculado ao acesso do portal.")
                      }
                      onUnlinkPortalUser={(userId) =>
                        withFeedback(async () => {
                          await api.updateUser(userId, { collaborator_id: null });
                          setUsers(await api.users());
                          await refreshAfterCollaboratorRegistryChange();
                        }, "Vínculo com o portal removido.")
                      }
                    />
                    )}
                  </TabsContent>
                  <TabsContent value="leadership" className="mt-0">
                    {!leadershipProfilesEverLoadedRef.current && tabLoading.leadership ? (
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
                              average_source: profile.average_source,
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
                      {!usersEverLoadedRef.current && tabLoading.users ? (
                        <div className="panel p-8 text-sm text-slate-500">Carregando usuários...</div>
                      ) : (
                      <UserManagementPanel
                        users={users}
                        collaborators={[...collaboratorRegistry.registered, ...collaboratorRegistry.unregistered]}
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
                  osTypeOptions={unmappedOsTypeOptions}
                  onLinkSubject={(subject, groupId, osType) =>
                    withFeedback(async () => {
                      await api.linkSubjectToGroup({
                        group_id: groupId,
                        os_type: osType,
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
                          os_type: item.osType,
                          os_subject: item.subject.os_subject
                        }))
                      );
                      await loadAll();
                    }, `${items.length} assunto(s) vinculados em massa.`)
                  }
                  onCreateGroupForSubject={(subject, osType) =>
                    withFeedback(async () => {
                      const group = await api.createScoringGroup({
                        name: `Grupo - ${subject.os_subject}`.slice(0, 150),
                        description: `Criado a partir do assunto sem regra: ${subject.os_subject}`,
                        default_points: 0,
                        active: true
                      });
                      await api.linkSubjectToGroup({
                        group_id: group.id,
                        os_type: osType,
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

            <TabsContent value="audit" className="mt-0 flex flex-1 flex-col overflow-visible">
              {activeTab === "audit" ? (
                <Tabs value={auditTab} onValueChange={setAuditTab} className="flex h-full min-h-0 flex-1 flex-col gap-3">
                  <TabsList className="w-full shrink-0 justify-start gap-2 rounded-2xl border border-slate-200 bg-slate-50/80 p-2">
                    <TabsTrigger value="scoring" className="rounded-xl px-4 py-2">Pontuação de O.S</TabsTrigger>
                    <TabsTrigger value="trail" className="rounded-xl px-4 py-2">Trilha de ações</TabsTrigger>
                  </TabsList>
                  <TabsContent value="scoring" className="mt-0 flex min-h-0 flex-1 flex-col">
                    {!summary ? (
                      <div className="panel p-8 text-sm text-slate-500">Carregando resumo consolidado para habilitar a auditoria...</div>
                    ) : !serviceOrdersLoaded && tabLoading.serviceOrders ? (
                      <div className="panel p-8 text-sm text-slate-500">Carregando filtros detalhados da auditoria...</div>
                    ) : (
                      <AuditPanel
                        calculationRunId={summary?.run?.id}
                        groups={groups}
                        regionalOptions={regionalOptions}
                        collaboratorOptions={auditCollaboratorOptions}
                        subjectOptions={auditSubjectOptions}
                      />
                    )}
                  </TabsContent>
                  <TabsContent value="trail" className="mt-0 min-h-0 flex-1 overflow-auto">
                    <div className="panel p-4">
                      <AuditTrailPanel />
                    </div>
                  </TabsContent>
                </Tabs>
              ) : null}
            </TabsContent>

            <TabsContent value="balance" className="mt-0 flex-1 pr-1">
              {activeTab === "balance" ? (
                <PointBalancePanel
                  isAdmin={currentUser?.role === "admin"}
                  calculationRunId={summary?.run?.id}
                  referenceMonth={summary?.run?.reference_month ?? analysisPeriod.reference_month}
                  referenceYear={summary?.run?.reference_year ?? analysisPeriod.reference_year}
                  runStatus={summary?.run?.status}
                />
              ) : null}
            </TabsContent>

            <TabsContent value="history" className="mt-0 flex flex-1 flex-col pr-1">
              {activeTab === "history" ? (
                !historyLoaded && tabLoading.history ? (
                  <div className="panel p-8 text-sm text-slate-500">Carregando histórico de apurações...</div>
                ) : (
                  <div className="space-y-4">
                    <ClosureHistoryPanel runs={calculationRuns} />
                  </div>
                )
              ) : null}
            </TabsContent>
          </Tabs>
        )}
          </div>
        </div>
      </div>

      <CollaboratorOrdersSheet
        open={ordersOpen}
        onOpenChange={setOrdersOpen}
        score={selectedScore}
        calculationRunId={summary?.run?.id}
        groups={groups}
        regionalHealth={
          selectedScore
            ? summary?.health_by_regional.find((item) => normalizeRegional(item.regional) === normalizeRegional(selectedScore.regional)) ?? null
            : null
        }
        pointValue={summary?.run?.point_value ?? summary?.point_value ?? null}
        rulesVersionId={summary?.run?.rules_version_id ?? null}
        runStatus={summary?.run?.status ?? null}
        rankingPosition={
          selectedScore
            ? filteredRanking.findIndex((score) => score.collaborator_id === selectedScore.collaborator_id) + 1 || null
            : null
        }
      />

      <AppDrawer
        open={selectedLeadershipResult != null}
        onOpenChange={(open) => {
          if (!open) setSelectedLeadershipResult(null);
        }}
        title={selectedLeadershipResult ? `Auditoria da liderança: ${selectedLeadershipResult.name}` : "Auditoria da liderança"}
        description="Mostra exatamente quais pessoas entraram no escopo e como a média final foi formada."
        widthClassName="sm:max-w-7xl"
      >
        {selectedLeadershipResult ? (
          <>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Pessoas na base</div>
                <div className="mt-2 text-2xl font-semibold text-slate-950">{formatNumber(leadershipAudit.collaborators.length)}</div>
                <div className="mt-1 text-sm text-slate-500">Entraram na média deste líder.</div>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Soma dos pontos finais</div>
                <div className="mt-2 text-2xl font-semibold text-slate-950">{formatNumber(leadershipAudit.totalFinalPoints)}</div>
                <div className="mt-1 text-sm text-slate-500">Total antes de dividir pela base.</div>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Média final</div>
                <div className="mt-2 text-2xl font-semibold text-slate-950">{formatPoints(selectedLeadershipResult.average_final_points)}</div>
                <div className="mt-1 text-sm text-slate-500">Soma dos pontos finais / base.</div>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Base financeira</div>
                <div className="mt-2 text-2xl font-semibold text-slate-950">{formatMoney(selectedLeadershipResult.base_amount)}</div>
                <div className="mt-1 text-sm text-slate-500">{formatMoney(selectedLeadershipResult.point_value)}/pt aplicado sobre a média.</div>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Valor a pagar</div>
                <div className="mt-2 text-2xl font-semibold text-teal-700">{formatMoney(selectedLeadershipResult.bonus_amount)}</div>
                <div className="mt-1 text-sm text-slate-500">Base x multiplicador {formatNumber(selectedLeadershipResult.multiplier)}x.</div>
              </div>
            </div>

            <div className="rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-slate-700">
              <span className="font-semibold text-slate-950">Fórmula usada:</span>{" "}
              {formatNumber(leadershipAudit.totalFinalPoints)} pts / {formatNumber(leadershipAudit.collaborators.length)} pessoa(s)
              = {formatNumber(leadershipAudit.averageFinalPoints)} pts de média.
              {" "}Depois: {formatMoney(selectedLeadershipResult.base_amount)} x {formatNumber(selectedLeadershipResult.multiplier)}x
              = {formatMoney(selectedLeadershipResult.bonus_amount)}.
            </div>

            <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
              <span className="font-semibold text-slate-950">Como ler esta auditoria:</span>{" "}
              {leadershipAudit.explanation}
              {" "}
              {leadershipAudit.differenceFromStoredAverage > 0.01
                ? "A diferença aparece porque a média exibida na conferência não bate com a média salva no fechamento."
                : "A média exibida na conferência bate com a média salva no fechamento."}
            </div>

            <div className="grid gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="text-sm font-semibold text-slate-950">Escopo considerado</div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {selectedLeadershipResult.regionals.map((regional) => (
                    <Badge key={`${selectedLeadershipResult.leadership_profile_id}-${regional}`} className="border-slate-200 bg-slate-50 text-slate-700">
                      {regionalName(regional)}
                    </Badge>
                  ))}
                </div>
                <div className="mt-4 text-xs text-slate-500">
                  Origem da média: {leadershipAverageSourceLabel(selectedLeadershipResult.average_source)}.
                  {" "}
                  {selectedLeadershipResult.role_type === "portfolio_manager"
                    ? "Gerente de pasta usa toda a base registrada do ranking."
                    : "As filiais vinculadas definem o escopo desta média."}
                </div>
                {leadershipAudit.differenceFromStoredAverage > 0.01 ? (
                  <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                    Diferença detectada: a média recalculada na conferência difere da média salva em {formatNumber(leadershipAudit.differenceFromStoredAverage)} pts.
                    {" "}
                    {!leadershipAudit.isExactAudit && selectedLeadershipResult.average_source === "collaborators_and_leaders"
                      ? "Neste caso, o motivo mais provável é que a apuração salva considerou líderes na composição da média e a reconstrução visual usa apenas a base disponível no frontend."
                      : "Revise se a base desta liderança mudou entre o fechamento salvo e a visualização atual."}
                  </div>
                ) : null}
              </div>

              <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
                <div className="border-b border-slate-200 px-4 py-3">
                  <div className="text-sm font-semibold text-slate-950">Base que forma a média</div>
                  <div className="text-xs text-slate-500">Ordenados pelos pontos finais dentro do escopo deste líder.</div>
                </div>
                <div className="max-h-[60vh] overflow-y-auto overflow-x-hidden">
                  <Table className="table-fixed">
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-[22%]">Pessoa</TableHead>
                        <TableHead className="w-[14%]">Origem</TableHead>
                        <TableHead className="w-[24%]">Filial</TableHead>
                        <TableHead className="w-[8%]">O.S / time</TableHead>
                        <TableHead className="w-[12%]">Multiplicador saúde</TableHead>
                        <TableHead className="w-[12%]">Pontos finais</TableHead>
                        <TableHead className="w-[8%] text-right">Valor técnico</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {leadershipAudit.collaborators.map((score, index) => (
                        <TableRow key={`leadership-audit-${selectedLeadershipResult.leadership_profile_id}-${score.source_type}-${score.collaborator_id}-${score.collaborator_name}-${index}`}>
                          <TableCell className="break-words">
                            <div className="grid gap-0.5">
                              <span className="font-medium text-slate-950">{score.collaborator_name}</span>
                              <span className="text-xs text-slate-500">{score.role}</span>
                            </div>
                          </TableCell>
                          <TableCell className="break-words">
                            <Badge className={score.source_type === "leader" ? "border-cyan-200 bg-cyan-50 text-cyan-700" : "border-slate-200 bg-slate-50 text-slate-700"}>
                              {leadershipAuditSourceLabel(score.source_type)}
                            </Badge>
                          </TableCell>
                          <TableCell className="break-words text-sm text-slate-700">{regionalName(score.regional)}</TableCell>
                          <TableCell>
                            {score.source_type === "leader" ? (
                              <span title="Colaboradores no time deste líder, não ordens de serviço">
                                {formatNumber(score.service_orders_count)} no time
                              </span>
                            ) : (
                              formatNumber(score.service_orders_count)
                            )}
                          </TableCell>
                          <TableCell>{score.source_type === "leader" ? "—" : `${formatNumber(score.health_multiplier)}x`}</TableCell>
                          <TableCell className="font-medium text-slate-950">{formatPoints(score.final_points)}</TableCell>
                          <TableCell className="text-right font-semibold text-teal-700">{formatMoney(score.estimated_payment)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </div>
            </div>
          </>
        ) : null}
      </AppDrawer>
      {ConfirmDialog}
    </main>
  );
}






