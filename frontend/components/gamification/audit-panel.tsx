"use client";

import {
  AlertTriangle,
  Clock,
  ClipboardCheck,
  ClipboardList,
  Download,
  FileSearch,
  Filter,
  HelpCircle,
  type LucideIcon,
  MinusCircle,
  RefreshCw,
  Repeat,
  Search,
  ShieldAlert,
  ShieldCheck,
  X,
  XCircle
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Avatar } from "@/components/gamification/config-ui";
import { OrderAuditSheet } from "@/components/gamification/order-audit-drawer";
import { api } from "@/lib/api";
import { formatAnnulledPoints, formatHours, formatInteger, formatMoney, formatPoints } from "@/lib/format";
import { normalizeRegional, regionalName } from "@/lib/regional";
import type { AuditOrders, CollaboratorOrderDetail, ScoringGroup } from "@/lib/types";

type FilterMode = "all" | "scored" | "unscored" | "penalized" | "sla_out" | "recurrence" | "non_recurrent" | "diagnosis_blocked";
type GroupMode = "group" | "subject" | "regional" | "collaborator" | "status";

const MODE_LABELS: Record<FilterMode, string> = {
  all: "Todas",
  scored: "Pontuadas",
  unscored: "Sem regra",
  penalized: "O.S anuladas",
  sla_out: "Fora prazo",
  recurrence: "Reincidências",
  non_recurrent: "Sem reincid.",
  diagnosis_blocked: "Diag. bloqueados"
};

type Props = {
  calculationRunId?: number;
  groups: ScoringGroup[];
  regionalOptions?: string[];
  collaboratorOptions?: Array<{ id: number; name: string; regional: string }>;
  subjectOptions?: string[];
};

type AuditOrder = CollaboratorOrderDetail & { collaborator_id: number; collaborator_name: string };

function statusBadgeClass(status: string) {
  const normalized = status.toLowerCase();
  if (normalized.includes("anulada")) return "border-red-200 bg-red-50 text-red-700";
  if (normalized.includes("penal")) return "border-red-200 bg-red-50 text-red-700";
  if (normalized.includes("sem regra")) return "border-amber-200 bg-amber-50 text-amber-800";
  if (normalized.includes("garantia")) return "border-blue-200 bg-blue-50 text-blue-700";
  if (normalized.includes("revisão")) return "border-violet-200 bg-violet-50 text-violet-700";
  if (normalized.includes("pontuada")) return "border-emerald-200 bg-emerald-50 text-emerald-700";
  return "border-slate-200 bg-slate-50 text-slate-700";
}

function recurrenceClassificationLabel(value: string | null | undefined) {
  if (value === "reincidencia_tecnica") return "Reincidência de manutenção";
  if (value === "garantia") return "Reincidência após ativação";
  if (value === "possivel_retorno_sem_regra") return "Retorno dentro da janela sem regra ativa";
  if (value === "os_nao_reincidente") return "O.S não reincidente";
  if (value === "nao_identificado") return "Não identificado";
  if (value === "demandas_diferentes") return "Demandas diferentes";
  if (value === "recorrencia_operacional") return "Recorrência operacional";
  return "Sem classificação";
}

type StatTone = "neutral" | "danger" | "warning" | "good" | "info";

function StatCard({ icon: Icon, label, value, tone = "neutral" }: { icon: LucideIcon; label: string; value: string; tone?: StatTone }) {
  const toneClass: Record<StatTone, string> = {
    neutral: "border-slate-200 bg-slate-50",
    danger: "border-red-200 bg-red-50",
    warning: "border-amber-200 bg-amber-50",
    good: "border-emerald-200 bg-emerald-50",
    info: "border-blue-200 bg-blue-50"
  };
  const iconToneClass: Record<StatTone, string> = {
    neutral: "bg-slate-200 text-slate-600",
    danger: "bg-red-100 text-red-700",
    warning: "bg-amber-100 text-amber-700",
    good: "bg-emerald-100 text-emerald-700",
    info: "bg-blue-100 text-blue-700"
  };
  const valueToneClass: Record<StatTone, string> = {
    neutral: "text-slate-950",
    danger: "text-red-700",
    warning: "text-amber-800",
    good: "text-emerald-700",
    info: "text-blue-700"
  };
  return (
    <div className={`flex min-w-0 items-center gap-2.5 rounded-xl border px-3 py-2.5 ${toneClass[tone]}`}>
      <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${iconToneClass[tone]}`}>
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0">
        <div className="truncate text-[10px] font-semibold uppercase tracking-wide text-slate-500">{label}</div>
        <div className={`truncate text-sm font-semibold ${valueToneClass[tone]}`}>{value}</div>
      </div>
    </div>
  );
}

function csvEscape(value: unknown) {
  const text = value === null || value === undefined ? "" : String(value);
  return `"${text.replace(/"/g, '""')}"`;
}

function groupLabel(order: AuditOrder, groupMode: GroupMode) {
  if (groupMode === "group") return order.group_name ?? "Sem regra de pontuação";
  if (groupMode === "subject") return `${order.os_type} - ${order.os_subject}`;
  if (groupMode === "regional") return regionalName(order.regional);
  if (groupMode === "collaborator") return order.collaborator_name;
  return order.scoring_status;
}

function groupModeLabel(groupMode: GroupMode) {
  if (groupMode === "group") return "grupo";
  if (groupMode === "subject") return "assunto";
  if (groupMode === "regional") return "regional";
  if (groupMode === "collaborator") return "colaborador";
  return "status da pontuação";
}

function buildGroups(orders: AuditOrder[], groupMode: GroupMode, pointValue: number) {
  const grouped = new Map<string, AuditOrder[]>();
  orders.forEach((order) => {
    const label = groupLabel(order, groupMode);
    grouped.set(label, [...(grouped.get(label) ?? []), order]);
  });

  return Array.from(grouped.entries())
    .map(([label, groupOrders]) => {
      const basePoints = groupOrders.reduce((total, order) => total + order.base_points, 0);
      const penaltyPoints = groupOrders.reduce((total, order) => total + order.penalty_points, 0);
      const netPoints = groupOrders.reduce((total, order) => total + order.net_points, 0);
      return {
        label,
        orders: groupOrders,
        orderCount: groupOrders.length,
        basePoints,
        penaltyPoints,
        netPoints,
        estimatedPayment: netPoints * pointValue,
        unscored: groupOrders.filter((order) => order.is_unscored).length,
        penalized: groupOrders.filter((order) => order.is_penalized).length
      };
    })
    .sort((a, b) => b.orders.length - a.orders.length);
}

export function AuditPanel({ calculationRunId, groups, regionalOptions = [], collaboratorOptions = [], subjectOptions = [] }: Props) {
  const [audit, setAudit] = useState<AuditOrders | null>(null);
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<FilterMode>("all");
  const [groupMode, setGroupMode] = useState<GroupMode>("group");
  const [regional, setRegional] = useState("");
  const [collaboratorId, setCollaboratorId] = useState("");
  const [groupId, setGroupId] = useState("");
  const [subject, setSubject] = useState("");
  const [sla, setSla] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [selectedGroupLabel, setSelectedGroupLabel] = useState<string | null>(null);
  const [selectedAuditOrder, setSelectedAuditOrder] = useState<AuditOrder | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(100);
  const activeGroups = useMemo(() => groups.filter((group) => group.active), [groups]);
  const filteredCollaboratorOptions = useMemo(() => {
    const normalizedRegional = regional ? normalizeRegional(regional) : "";
    return collaboratorOptions
      .filter((option) => !normalizedRegional || normalizeRegional(option.regional) === normalizedRegional)
      .sort((a, b) => a.name.localeCompare(b.name, "pt-BR"));
  }, [collaboratorOptions, regional]);
  const hasFilters = mode !== "all" || Boolean(regional || collaboratorId || groupId || subject || sla || selectedGroupLabel);

  const filters = useMemo(
    () => ({
      calculation_run_id: calculationRunId,
      regional: regional || undefined,
      collaborator_id: collaboratorId ? Number(collaboratorId) : undefined,
      group_id: groupId ? Number(groupId) : undefined,
      os_subject: subject || undefined,
      status_sla: sla || undefined,
      only_scored: mode === "scored" || undefined,
      only_unscored: mode === "unscored" || undefined,
      only_penalized: mode === "penalized" || undefined,
      only_sla_out: mode === "sla_out" || undefined,
      only_recurrence: mode === "recurrence" || undefined,
      only_non_recurrent: mode === "non_recurrent" || undefined,
      only_diagnosis_blocked: mode === "diagnosis_blocked" || undefined,
      audit_group_mode: groupMode,
      audit_group_label: selectedGroupLabel || undefined,
      page,
      page_size: pageSize
    }),
    [calculationRunId, collaboratorId, groupId, groupMode, mode, page, pageSize, regional, selectedGroupLabel, sla, subject]
  );

  useEffect(() => {
    setPage(1);
  }, [calculationRunId, collaboratorId, groupId, mode, regional, selectedGroupLabel, sla, subject]);

  useEffect(() => {
    setSelectedGroupLabel(null);
    setPage(1);
  }, [groupMode]);

  useEffect(() => {
    if (!collaboratorId) return;
    if (!filteredCollaboratorOptions.some((option) => String(option.id) === collaboratorId)) {
      setCollaboratorId("");
    }
  }, [collaboratorId, filteredCollaboratorOptions]);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .auditOrders(filters)
      .then(setAudit)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [filters]);

  const pointValue = audit?.summary.final_points
    ? audit.summary.estimated_payment / audit.summary.final_points
    : 0;
  const visibleOrders = useMemo(() => {
    return (audit?.orders ?? []) as AuditOrder[];
  }, [audit]);
  const grouped = useMemo(() => {
    const summaries = audit?.group_summaries?.[groupMode];
    if (summaries?.length) {
      return summaries.map((summary) => ({
        label: summary.label,
        orders: visibleOrders.filter((order) => groupLabel(order, groupMode) === summary.label),
        orderCount: summary.service_orders_count,
        basePoints: summary.base_points,
        penaltyPoints: summary.penalty_points,
        netPoints: summary.net_points,
        estimatedPayment: summary.estimated_payment,
        unscored: summary.unscored_service_orders,
        penalized: summary.penalized_service_orders
      }));
    }
    return buildGroups(visibleOrders, groupMode, pointValue);
  }, [audit, groupMode, pointValue, visibleOrders]);
  const activeGroup = grouped.find((group) => group.label === selectedGroupLabel) ?? grouped[0];
  const recurrenceClassificationCounts = useMemo(() => {
    const counts = new Map<string, number>();
    (audit?.orders ?? []).forEach((order) => {
      if (!order.recurrence_classification && !order.is_recurrence && !order.is_warranty) return;
      const label = recurrenceClassificationLabel(order.recurrence_classification);
      counts.set(label, (counts.get(label) ?? 0) + 1);
    });
    return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
  }, [audit]);
  const recurrenceHelp =
    mode === "recurrence"
      ? "Mostrando somente O.S com reincidência que anulou pontos."
      : mode === "non_recurrent"
        ? "Mostrando recorrências analisadas que não devem anular pontos."
        : null;

  useEffect(() => {
    if (selectedGroupLabel && !grouped.some((group) => group.label === selectedGroupLabel)) {
      setSelectedGroupLabel(null);
    }
  }, [grouped, selectedGroupLabel]);

  const activeFilterChips = useMemo(() => {
    const chips: Array<{ key: string; label: string; onRemove: () => void }> = [];
    if (mode !== "all") chips.push({ key: "mode", label: MODE_LABELS[mode], onRemove: () => setMode("all") });
    if (regional) chips.push({ key: "regional", label: `Regional: ${regionalName(regional)}`, onRemove: () => setRegional("") });
    if (collaboratorId) {
      const found = collaboratorOptions.find((option) => String(option.id) === collaboratorId);
      chips.push({ key: "collaborator", label: `Colaborador: ${found?.name ?? collaboratorId}`, onRemove: () => setCollaboratorId("") });
    }
    if (groupId) {
      const found = activeGroups.find((group) => String(group.id) === groupId);
      chips.push({ key: "group", label: `Grupo: ${found?.name ?? groupId}`, onRemove: () => setGroupId("") });
    }
    if (subject) chips.push({ key: "subject", label: `Assunto: ${subject}`, onRemove: () => setSubject("") });
    if (sla) chips.push({ key: "sla", label: `SLA: ${sla}`, onRemove: () => setSla("") });
    if (selectedGroupLabel) chips.push({ key: "groupLabel", label: `Grupo selecionado: ${selectedGroupLabel}`, onRemove: () => setSelectedGroupLabel(null) });
    return chips;
  }, [activeGroups, collaboratorId, collaboratorOptions, groupId, mode, regional, selectedGroupLabel, sla, subject]);

  function clearFilters() {
    setMode("all");
    setRegional("");
    setCollaboratorId("");
    setGroupId("");
    setSubject("");
    setSla("");
    setSelectedGroupLabel(null);
    setPage(1);
  }

  async function exportCsv() {
    if (!audit) return;
    const exportAudit = await api.auditOrders({ ...filters, page: 1, page_size: 5000 });
    const exportOrders = exportAudit.orders as AuditOrder[];
    const headers = [
      "ID O.S",
      "Colaborador",
      "Regional",
      "Cliente",
      "Login",
      "Plano/Contrato",
      "Tipo Geral",
      "Assunto",
      "Diagnóstico",
      "Grupo aplicado",
      "Pontuação base do grupo",
      "Sobrescrita assunto",
      "Regra de diagnóstico",
      "Ponto anulado por diagnóstico",
      "Ponto anulado por SLA",
      "Pontos anulados adicionais",
      "Pontos líquidos",
      "SLA original",
      "SLA normalizado",
      "Classificação reincidência",
      "Reagendamento",
      "Pendência",
      "Status pontuação",
      "Auditoria"
    ];
    const rows = exportOrders
      .map((order) => [
      order.os_code,
      order.collaborator_name,
      regionalName(order.regional),
      order.customer_name,
      order.customer_login ?? "",
      order.contract_id,
      order.os_type,
      order.os_subject,
      order.diagnosis,
      order.group_name ?? "Sem regra",
      order.group_base_points,
      order.subject_override_points ?? "",
      order.diagnosis_rule_applied ?? "",
      order.diagnosis_penalty_points,
      order.sla_penalty_points,
      order.additional_penalty_points,
      order.net_points,
      order.sla_status,
      order.sla_status_normalized,
      order.recurrence_classification ?? "",
      order.has_reschedule ? "Sim" : "Não",
      order.has_pending ? "Sim" : "Não",
      order.scoring_status,
      order.reasons.join(" | ")
    ]);
    const csv = [headers, ...rows].map((row) => row.map(csvEscape).join(",")).join("\n");
    const blob = new Blob([`\ufeff${csv}`], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "auditoria-operacional.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="panel flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 flex-col gap-3 border-b bg-gradient-to-r from-slate-50 via-white to-white px-4 py-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <Badge className="w-fit border-slate-200 bg-white text-slate-700">
            <ShieldCheck className="h-3.5 w-3.5" />
            Auditoria operacional
          </Badge>
          <h2 className="mt-2 text-xl font-semibold text-slate-950">Conferência das O.S e regras aplicadas</h2>
          <p className="mt-1 text-sm text-slate-500">Base, regra aplicada, pontos anulados e resultado final em uma tela operacional.</p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={() => setFiltersOpen((value) => !value)}>
            <Filter className="h-4 w-4" />
            {filtersOpen ? "Ocultar filtros" : "Filtros"}
            {activeFilterChips.length > 0 ? (
              <span className="ml-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-teal-600 px-1 text-[10px] font-semibold text-white">
                {activeFilterChips.length}
              </span>
            ) : null}
          </Button>
          <Button variant="outline" size="sm" onClick={clearFilters} disabled={!hasFilters}>
            Limpar
          </Button>
          <Button variant="outline" size="sm" onClick={exportCsv} disabled={!audit}>
            <Download className="h-4 w-4" />
            Exportar auditoria
          </Button>
        </div>
      </div>

      {audit ? (
        <div className="grid shrink-0 gap-2 overflow-x-auto border-b bg-white px-4 py-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
          <StatCard icon={ClipboardList} label="Total de O.S" value={`${formatInteger(audit.summary.total_service_orders)} O.S`} tone="neutral" />
          <StatCard
            icon={HelpCircle}
            label="O.S sem regra"
            value={`${formatInteger(audit.summary.unscored_service_orders)} O.S`}
            tone={audit.summary.unscored_service_orders > 0 ? "warning" : "good"}
          />
          <StatCard
            icon={XCircle}
            label="O.S anuladas"
            value={`${formatInteger(audit.summary.annulled_service_orders)} O.S`}
            tone={audit.summary.annulled_service_orders > 0 ? "danger" : "good"}
          />
          <StatCard
            icon={Clock}
            label="Fora prazo"
            value={`${formatInteger(audit.summary.sla_out_service_orders)} O.S`}
            tone={audit.summary.sla_out_service_orders > 0 ? "warning" : "good"}
          />
          <StatCard
            icon={MinusCircle}
            label="Pontos anulados"
            value={formatAnnulledPoints(audit.summary.penalty_points)}
            tone={audit.summary.penalty_points > 0 ? "danger" : "good"}
          />
          <StatCard icon={Repeat} label="Reincidências" value={`${formatInteger(audit.summary.recurrence_service_orders)} O.S`} tone="info" />
          <StatCard
            icon={ShieldAlert}
            label="Diagnósticos bloqueados"
            value={`${formatInteger(audit.summary.diagnosis_penalized_service_orders)} O.S`}
            tone={audit.summary.diagnosis_penalized_service_orders > 0 ? "danger" : "good"}
          />
        </div>
      ) : null}

      <div className="shrink-0 border-b bg-slate-50 px-4 py-3">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Status da O.S</div>
          <div className="mt-1.5 flex items-center gap-2 overflow-x-auto pb-1">
            {[
              ["all", "Todas"],
              ["scored", "Pontuadas"],
              ["unscored", "Sem regra"],
              ["penalized", "O.S anuladas"],
              ["sla_out", "Fora prazo"],
              ["recurrence", "Reincidências"],
              ["diagnosis_blocked", "Diag. bloqueados"],
              ["non_recurrent", "Sem reincid."]
            ].map(([value, label]) => (
              <Button key={value} variant={mode === value ? "default" : "outline"} size="sm" onClick={() => setMode(value as FilterMode)} className="h-8 shrink-0 px-3">
                {label}
              </Button>
            ))}
          </div>
        </div>

        <div className="mt-3 border-t border-slate-200 pt-3">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Agrupamento e busca</div>
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <select className="h-8 shrink-0 rounded-md border border-input bg-white px-2 text-xs" value={groupMode} onChange={(event) => setGroupMode(event.target.value as GroupMode)}>
              <option value="group">Agrupar por grupo</option>
              <option value="subject">Agrupar por assunto</option>
              <option value="regional">Agrupar por regional</option>
              <option value="collaborator">Agrupar por colaborador</option>
              <option value="status">Agrupar por status</option>
            </select>

            <select className="h-8 min-w-40 shrink-0 rounded-md border border-input bg-white px-2 text-xs" value={groupId} onChange={(event) => setGroupId(event.target.value)}>
              <option value="">Todos os grupos</option>
              {activeGroups.map((group) => (
                <option key={group.id} value={group.id}>
                  {group.name}
                </option>
              ))}
            </select>

            <div className="relative min-w-52 flex-1">
              <Search className="pointer-events-none absolute left-2 top-2 h-4 w-4 text-slate-400" />
              <Input value={subject} onChange={(event) => setSubject(event.target.value)} className="h-8 pl-7 text-xs" placeholder="Buscar assunto" list="audit-subject-options" />
              <datalist id="audit-subject-options">
                {subjectOptions.map((option) => (
                  <option key={option} value={option} />
                ))}
              </datalist>
            </div>
          </div>
        </div>

        {filtersOpen ? (
          <div className="mt-3 rounded-lg border border-slate-200 bg-white p-3">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Filtros avançados</div>
            <div className="mt-2 grid gap-3 md:grid-cols-3">
              <div className="grid gap-1">
                <Label className="text-[10px] uppercase text-slate-500">Regional</Label>
                <select className="h-8 rounded-md border border-input bg-white px-2 text-xs" value={regional} onChange={(event) => setRegional(event.target.value)}>
                  <option value="">Todas as regionais</option>
                  {regionalOptions.map((option) => (
                    <option key={option} value={option}>
                      {regionalName(option)}
                    </option>
                  ))}
                </select>
              </div>
              <div className="grid gap-1">
                <Label className="text-[10px] uppercase text-slate-500">Colaborador</Label>
                <select className="h-8 rounded-md border border-input bg-white px-2 text-xs" value={collaboratorId} onChange={(event) => setCollaboratorId(event.target.value)}>
                  <option value="">Todos os colaboradores</option>
                  {filteredCollaboratorOptions.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.name}
                    </option>
                  ))}
                </select>
                <div className="text-[11px] text-slate-500">
                  {regional ? `${filteredCollaboratorOptions.length} colaborador(es) nesta regional.` : "Selecione uma regional para reduzir a lista."}
                </div>
              </div>
              <div className="grid gap-1">
                <Label className="text-[10px] uppercase text-slate-500">SLA</Label>
                <select className="h-8 rounded-md border border-input bg-white px-2 text-xs" value={sla} onChange={(event) => setSla(event.target.value)}>
                  <option value="">Todos os SLAs</option>
                  <option value="Encerrada no Prazo">Encerrada no Prazo</option>
                  <option value="Encerrada Atrasada">Encerrada Atrasada</option>
                  <option value="No prazo">No prazo</option>
                  <option value="Fora do prazo">Fora do prazo</option>
                </select>
              </div>
            </div>
          </div>
        ) : null}
      </div>

      {activeFilterChips.length ? (
        <div className="flex shrink-0 flex-wrap items-center gap-1.5 border-b bg-white px-4 py-2">
          <span className="text-[11px] font-medium text-slate-500">Filtros ativos:</span>
          {activeFilterChips.map((chip) => (
            <button
              key={chip.key}
              type="button"
              onClick={chip.onRemove}
              className="flex items-center gap-1 rounded-full border border-teal-200 bg-teal-50 px-2.5 py-1 text-[11px] font-medium text-teal-800 hover:bg-teal-100"
            >
              {chip.label}
              <X className="h-3 w-3" />
            </button>
          ))}
          <button type="button" onClick={clearFilters} className="text-[11px] font-medium text-slate-500 underline hover:text-slate-700">
            Limpar todos
          </button>
        </div>
      ) : null}

      {error ? <div className="mx-3 mt-2 shrink-0 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div> : null}
      {loading ? (
        <div className="mx-3 mt-2 flex shrink-0 items-center gap-2 rounded-md border bg-slate-50 px-3 py-2 text-xs text-slate-600">
          <RefreshCw className="h-4 w-4 animate-spin" />
          Atualizando auditoria...
        </div>
      ) : null}

      {(mode === "recurrence" || mode === "non_recurrent") && recurrenceClassificationCounts.length ? (
        <div className="shrink-0 border-b bg-blue-50/60 px-3 py-2 text-xs">
          <div className="font-semibold text-slate-700">{recurrenceHelp}</div>
          <div className="mt-1 flex gap-2 overflow-x-auto">
            {recurrenceClassificationCounts.map(([label, count]) => (
              <span key={label} className="shrink-0 rounded-full border border-blue-200 bg-white px-3 py-1 font-medium text-slate-700">
                {label}: {formatInteger(count)}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {audit ? (
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="hidden shrink-0 border-b bg-white px-3 py-1 text-xs text-slate-600 sm:block">
            {formatInteger(audit.total_orders ?? visibleOrders.length)} O.S no filtro atual, exibindo página {audit.page ?? page} de {audit.total_pages ?? 1}, por {groupModeLabel(groupMode)}.
          </div>

          {visibleOrders.length === 0 && !loading ? (
            <div className="m-3 rounded-lg border border-amber-200 bg-amber-50 p-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
                <AlertTriangle className="h-4 w-4 text-amber-700" />
                Nenhuma O.S encontrada com os filtros atuais.
              </div>
              <p className="mt-1 text-xs text-slate-700">A base não está zerada necessariamente; os filtros podem estar restringindo a auditoria.</p>
              <Button className="mt-3" size="sm" variant="outline" onClick={clearFilters}>
                Limpar filtros
              </Button>
            </div>
          ) : null}

          {visibleOrders.length > 0 && activeGroup ? (
            <div className="flex min-h-0 flex-1 flex-col p-2">
              <div className="mb-1 flex shrink-0 gap-2 overflow-x-auto pb-1">
                {grouped.map((group) => (
                  <button
                    key={group.label}
                    className={
                      group.label === selectedGroupLabel
                        ? "min-w-48 rounded-md border border-teal-300 bg-teal-50 px-3 py-1.5 text-left text-xs"
                        : "min-w-48 rounded-md border bg-white px-3 py-1.5 text-left text-xs hover:bg-slate-50"
                    }
                    onClick={() => setSelectedGroupLabel((current) => (current === group.label ? null : group.label))}
                  >
                    <div className="truncate font-semibold text-slate-950">{group.label}</div>
                    <div className="mt-1 flex justify-between gap-3 text-[11px] text-slate-500">
                      <span>{formatInteger(group.orderCount)} O.S</span>
                      <span>{formatMoney(group.estimatedPayment)}</span>
                    </div>
                  </button>
                ))}
              </div>

              <div className="hidden shrink-0 grid-cols-5 gap-2 rounded-md border bg-white px-3 py-2 text-right text-xs sm:grid">
                <div className="text-left">
                  <div className="text-[10px] text-slate-500">Agrupamento</div>
                  <div className="flex items-center gap-2 truncate font-semibold text-slate-950">
                    <ClipboardCheck className="h-4 w-4 text-teal-700" />
                    <span className="truncate">{activeGroup.label}</span>
                  </div>
                </div>
                <div>
                  <div className="text-[10px] text-slate-500">O.S</div>
                  <div className="font-semibold">{formatInteger(activeGroup.orderCount)}</div>
                </div>
                <div>
                  <div className="text-[10px] text-slate-500">Sem regra</div>
                  <div className="font-semibold text-amber-700">{formatInteger(activeGroup.unscored)}</div>
                </div>
                <div>
                  <div className="text-[10px] text-slate-500">Anul.</div>
                  <div className="font-semibold text-red-600">{formatInteger(activeGroup.penalized)}</div>
                </div>
                <div>
                  <div className="text-[10px] text-slate-500">Valor a ser pago</div>
                  <div className="font-semibold text-teal-700">{formatMoney(activeGroup.estimatedPayment)}</div>
                </div>
              </div>

              <div className="mt-2 min-h-0 flex-1 overflow-hidden rounded-md border bg-white">
                <div className="audit-table-frame h-full">
                  <table className="audit-table">
                    <thead>
                      <tr>
                        <th className="w-[76px]">O.S</th>
                        <th className="w-[190px]">Colaborador</th>
                        <th className="w-[130px]">Regional</th>
                        <th className="w-[180px]">Cliente</th>
                        <th>Assunto / diagnóstico</th>
                        <th className="w-[170px]">Operação</th>
                        <th className="w-[100px]">Pontos</th>
                        <th className="w-[95px]">Valor</th>
                        <th className="w-[140px]">Status</th>
                        <th className="w-[90px]">Auditoria</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleOrders.map((order) => (
                        <tr key={order.id}>
                          <td className="font-semibold">{order.os_code}</td>
                          <td title={order.collaborator_name}>
                            <div className="flex min-w-0 items-center gap-2">
                              <Avatar name={order.collaborator_name} size="sm" />
                              <div className="line-clamp-2 min-w-0">{order.collaborator_name}</div>
                            </div>
                          </td>
                          <td title={regionalName(order.regional)}>
                            <div className="line-clamp-2">{regionalName(order.regional)}</div>
                          </td>
                          <td title={order.customer_name}>
                            <div className="line-clamp-2">{order.customer_name}</div>
                          </td>
                          <td title={`${order.os_subject} - ${order.diagnosis}`}>
                            <div className="line-clamp-1 font-semibold text-slate-950">{order.os_subject}</div>
                            <div className="line-clamp-1 text-[11px] text-slate-500">{order.diagnosis || order.os_type}</div>
                          </td>
                          <td>
                            <div className="line-clamp-1">{order.group_name ?? "Sem regra"}</div>
                            <div className="line-clamp-1 text-[11px] text-slate-500">{order.sla_status} - {formatHours(order.closing_time_hours)}</div>
                          </td>
                          <td>
                            <div className="font-semibold">{formatPoints(order.net_points)}</div>
                            <div className={order.penalty_points > 0 ? "text-[11px] font-medium text-red-600" : "text-[11px] text-slate-500"}>
                              {formatAnnulledPoints(order.penalty_points)}
                            </div>
                          </td>
                          <td>
                            <div className="font-semibold text-teal-700">{formatMoney(order.net_points * pointValue)}</div>
                          </td>
                          <td>
                            <Badge className={statusBadgeClass(order.scoring_status)}>{order.scoring_status}</Badge>
                            {order.recurrence_classification ? (
                              <div className="mt-1 text-[11px] text-blue-700">{recurrenceClassificationLabel(order.recurrence_classification)}</div>
                            ) : null}
                            {order.has_reschedule || order.has_pending ? (
                              <div className="mt-1 flex flex-wrap gap-1">
                                {order.has_reschedule ? (
                                  <span className="inline-flex items-center gap-0.5 rounded-full border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-800">
                                    <Repeat className="h-3 w-3" />
                                    Reagendada
                                  </span>
                                ) : null}
                                {order.has_pending ? (
                                  <span className="inline-flex items-center gap-0.5 rounded-full border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">
                                    <Clock className="h-3 w-3" />
                                    Pendência
                                  </span>
                                ) : null}
                              </div>
                            ) : null}
                          </td>
                          <td>
                            <Button type="button" variant="ghost" size="sm" className="h-8" onClick={() => setSelectedAuditOrder(order)}>
                              <FileSearch className="h-4 w-4" />
                              Auditar
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t bg-slate-50 px-3 py-2 text-xs text-slate-600">
                <div>
                  Exibindo {formatInteger(visibleOrders.length)} de {formatInteger(audit.total_orders ?? visibleOrders.length)} O.S filtradas.
                </div>
                <div className="flex items-center gap-2">
                  <select
                    className="h-8 rounded-md border border-input bg-white px-2 text-xs"
                    value={pageSize}
                    onChange={(event) => {
                      setPageSize(Number(event.target.value));
                      setPage(1);
                    }}
                  >
                    {[50, 100, 250, 500].map((value) => (
                      <option key={value} value={value}>
                        {value} por página
                      </option>
                    ))}
                  </select>
                  <Button variant="outline" size="sm" onClick={() => setPage((current) => Math.max(current - 1, 1))} disabled={(audit.page ?? page) <= 1}>
                    Anterior
                  </Button>
                  <span className="min-w-20 text-center">
                    {audit.page ?? page}/{audit.total_pages ?? 1}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((current) => Math.min(current + 1, audit.total_pages ?? current + 1))}
                    disabled={(audit.page ?? page) >= (audit.total_pages ?? 1)}
                  >
                    Próxima
                  </Button>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
      <OrderAuditSheet
        order={selectedAuditOrder}
        open={Boolean(selectedAuditOrder)}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) setSelectedAuditOrder(null);
        }}
        calculationRunId={calculationRunId}
      />
    </section>
  );
}





