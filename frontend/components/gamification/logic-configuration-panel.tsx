"use client";

import { Check, ChevronDown, FileDown, FileUp, RotateCcw, Save, Search, Settings2, SlidersHorizontal, Trash2, X } from "lucide-react";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";

import {
  AppCombobox,
  AppDrawer,
  AppInput,
  AppModal,
  AppSwitch,
  DataTableFrame,
  EmptyState,
  FilterToolbar,
  GuidanceCard,
  PageHeader,
  RowActionMenu,
  StatusBadge,
  StepHeroCard,
  ToolbarCount,
  ToolbarSearch,
  configCardClass,
  configSectionClass,
  configSoftCardClass,
} from "@/components/gamification/config-ui";
import { GovernanceRulesPanel } from "@/components/gamification/governance-rules-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { StatusToast } from "@/components/ui/status-toast";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatInteger, formatMoney, formatPoints } from "@/lib/format";
import { cn } from "@/lib/utils";
import type {
  DiagnosisActionType,
  FinancialBreakdownItem,
  GamificationConfig,
  HealthRule,
  ImportedDiagnosis,
  RecurrenceClassificationRule,
  ScoringGroup,
  ScoringSubjectRule,
  ServiceOrderSubjectSummary,
  SlaPenaltyRule,
  SlaPenaltyType
} from "@/lib/types";

type Props = {
  groups: ScoringGroup[];
  subjectRules: ScoringSubjectRule[];
  importedDiagnoses: ImportedDiagnosis[];
  recurrenceRules: RecurrenceClassificationRule[];
  healthRules: HealthRule[];
  slaRules: SlaPenaltyRule[];
  pointValue: string;
  periodSubjectSummaries: ServiceOrderSubjectSummary[];
  financialBreakdowns: {
    cost_by_group: FinancialBreakdownItem[];
    cost_by_subject: FinancialBreakdownItem[];
  };
  setGroups: (groups: ScoringGroup[]) => void;
  setSubjectRules: (rules: ScoringSubjectRule[]) => void;
  setRecurrenceRules: (rules: RecurrenceClassificationRule[]) => void;
  setHealthRules: (rules: HealthRule[]) => void;
  setSlaRules: (rules: SlaPenaltyRule[]) => void;
  setPointValue: (value: string) => void;
  onCreateGroup: (payload: Partial<ScoringGroup>) => Promise<void>;
  onSaveGroup: (group: ScoringGroup) => Promise<void>;
  onDeleteGroup: (group: ScoringGroup, replacementGroupId?: number | null) => Promise<void>;
  onSaveSubjectRule: (rule: ScoringSubjectRule) => Promise<void>;
  onDeleteSubjectRule: (rule: ScoringSubjectRule) => Promise<void>;
  onSaveDiagnosisRule: (
    diagnosisName: string,
    ruleId: number | null,
    payload: {
      action_type: DiagnosisActionType;
      penalty_points: number;
      force_points_value: number | null;
      active: boolean;
      description: string;
    }
  ) => Promise<void>;
  onSavePointValue: () => Promise<void>;
  onCreateRecurrenceRule: (payload: Partial<RecurrenceClassificationRule>) => Promise<void>;
  onSaveRecurrenceRule: (rule: RecurrenceClassificationRule) => Promise<void>;
  onDeleteRecurrenceRule: (rule: RecurrenceClassificationRule) => Promise<void>;
  onSaveHealthRule: (rule: HealthRule) => Promise<void>;
  onCreateSlaRule: () => Promise<void>;
  onSaveSlaRule: (rule: SlaPenaltyRule) => Promise<void>;
  onReload: () => Promise<void>;
};

type Mode = "simple" | "advanced";
type ConfigSection = "governance" | "categories" | "groups" | "subjects" | "diagnoses" | "recurrence" | "sla" | "integration" | "advanced";
type SubjectFilter = "all" | "scored" | "not_scored" | "without_group";
type DiagnosisFilter = "all" | "annuls_points" | "without_rule";
type RecurrenceClassificationValue = RecurrenceClassificationRule["classification"];

const SIMPLE_SECTIONS: Array<{ value: ConfigSection; label: string; help: string }> = [
  { value: "governance", label: "Governança geral", help: "Valor do ponto e janela de reincidência." },
  { value: "categories", label: "Tipos gerais", help: "Categorias reais vindas da planilha." },
  { value: "groups", label: "Grupos de pontuação", help: "Pontos e valor por grupo." },
  { value: "subjects", label: "Assuntos", help: "Tipo geral, grupo e status por assunto." },
  { value: "diagnoses", label: "Diagnósticos", help: "Regras principais de diagnóstico." }
];

const ADVANCED_SECTIONS: Array<{ value: ConfigSection; label: string; help: string }> = [
  ...SIMPLE_SECTIONS,
  { value: "recurrence", label: "Reincidência", help: "Fluxo e regras completas." },
  { value: "sla", label: "SLA/Saúde", help: "Prazo e multiplicadores." },
  { value: "integration", label: "Integração IXC", help: "Sincronização automática e recálculo." },
  { value: "advanced", label: "Avançado", help: "JSON, histórico e restauração." }
];

const IXC_SYNC_ENABLED_KEY = "ixc_sync_enabled";
const IXC_SYNC_INTERVAL_MINUTES_KEY = "ixc_sync_interval_minutes";
const IXC_SYNC_AUTO_RECALCULATE_KEY = "ixc_sync_auto_recalculate";


function replaceById<T extends { id: number }>(items: T[], id: number, patch: Partial<T>) {
  return items.map((item) => (item.id === id ? { ...item, ...patch } : item));
}

const HEALTH_BELOW_MINIMUM_MULTIPLIER_SETTING = "health_below_minimum_multiplier";

function numericInputValue(value: number) {
  return Number.isFinite(value) ? value : "";
}

function parseNumericInput(value: string) {
  return value === "" ? Number.NaN : Number(value);
}

type GroupSnapshot = Pick<ScoringGroup, "name" | "default_points" | "point_value_override" | "active">;

function groupSnapshot(group: ScoringGroup): GroupSnapshot {
  return {
    name: group.name,
    default_points: group.default_points,
    point_value_override: group.point_value_override ?? null,
    active: group.active,
  };
}

function sameGroupSnapshot(a: GroupSnapshot | undefined, b: GroupSnapshot) {
  return (
    a?.name === b.name &&
    a?.default_points === b.default_points &&
    (a?.point_value_override ?? null) === (b.point_value_override ?? null) &&
    a?.active === b.active
  );
}

function actionLabel(action: DiagnosisActionType | null) {
  if (action === "subtract_points") return "Subtrair pontos";
  if (action === "cancel_points") return "Anular pontos";
  if (action === "requires_review") return "Revisão manual";
  if (action === "force_points") return "Forçar pontos";
  if (action === "no_penalty") return "Sem anulação";
  return "Sem regra";
}

// O backend (scoring_detail.py) só lê o valor numérico pra "subtract_points" (desconta o valor
// exato) e "force_points" (usa como pontuação fixa). Pra "cancel_points" ele sempre zera 100% dos
// pontos da ocorrência, ignorando qualquer número digitado aqui; pra "requires_review" e
// "no_penalty" o valor nunca é lido. Sem isso, o campo parecia funcionar pra todo mundo e um admin
// podia achar que "Anular pontos" com valor "50" descontava 50 pontos, quando na verdade zera tudo.
function diagnosisPointsFieldState(action: DiagnosisActionType): { editable: boolean; helper: string } {
  if (action === "subtract_points") return { editable: true, helper: "Pontos descontados desta ocorrência." };
  if (action === "force_points") return { editable: true, helper: "Pontuação fixa aplicada, substitui a regra do assunto." };
  if (action === "cancel_points") return { editable: false, helper: "Anula 100% da pontuação - este valor não é usado." };
  return { editable: false, helper: "Esta ação não usa valor numérico." };
}

// Mesma lógica do diagnóstico, mas pra regra de SLA: "cancel_points" sempre zera 100% dos pontos da
// O.S fora do prazo (ignora o valor); "none" e "requires_review" nunca leem o valor.
function slaValueFieldState(penaltyType: SlaPenaltyType): { editable: boolean; helper: string } {
  if (penaltyType === "subtract_points") return { editable: true, helper: "Pontos descontados da O.S fora do prazo." };
  if (penaltyType === "percentage_reduction") return { editable: true, helper: "Percentual (0-100) reduzido da pontuação." };
  if (penaltyType === "cancel_points") return { editable: false, helper: "Anula 100% da pontuação - este valor não é usado." };
  return { editable: false, helper: "Este tipo não usa valor numérico." };
}

function recurrenceClassificationLabel(value: string) {
  if (value === "recorrencia_operacional") return "Reincidência operacional";
  if (value === "reincidencia_tecnica") return "Reincidência de manutenção";
  if (value === "garantia") return "Reincidência após ativação";
  if (value === "os_nao_reincidente") return "O.S. não reincidente";
  if (value === "demandas_diferentes") return "Demandas diferentes";
  return "Não identificado";
}

// O backend (scoring_detail.py, RECURRENCE_DISCOUNT_CLASSIFICATIONS) só aplica o desconto na O.S
// original pra esses dois subtipos - marcar "Anula pontuação" em qualquer outro subtipo não tem
// efeito nenhum no cálculo, então o checkbox fica desabilitado pra evitar essa falsa impressão.
function classificationSupportsDiscount(classification: string) {
  return classification === "reincidencia_tecnica" || classification === "garantia";
}

function recurrenceActionLabel(value: string) {
  if (value === "annul_original") return "Anular pontuação da O.S original";
  if (value === "subtract_original") return "Anular pontos fixos da O.S original";
  if (value === "requires_review") return "Enviar para revisão manual";
  if (value === "no_penalty") return "Apenas sinalizar";
  return "Usar configuração do backend";
}

function subjectStatus(rule: ScoringSubjectRule, group: ScoringGroup | null | undefined) {
  if (!group) return "sem_regra";
  if (!rule.active) return "nao_pontua";
  return "pontua";
}

function subjectRuleKey(osType: string, osSubject: string) {
  return `${osType.trim().toLowerCase()}::${osSubject.trim().toLowerCase()}`;
}

function subjectStatusLabel(status: string) {
  if (status === "pontua") return "Pontua";
  if (status === "nao_pontua") return "Não pontua";
  return "Sem regra";
}

function subjectStatusClass(status: string) {
  if (status === "pontua") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (status === "nao_pontua") return "border-slate-200 bg-slate-50 text-slate-700";
  return "border-amber-200 bg-amber-50 text-amber-800";
}

function recurrenceIdentityFields(settings: Record<string, string>) {
  const value = settings.recurrence_identity_fields || "login,contract";
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function toggleIdentityField(settings: Record<string, string>, field: string, checked: boolean) {
  const current = new Set(recurrenceIdentityFields(settings));
  if (checked) {
    current.add(field);
  } else {
    current.delete(field);
  }
  return Array.from(current).join(",");
}

function splitRuleValues(value: string | null | undefined) {
  return (value ?? "")
    .split("|")
    .map((item) => item.trim())
    .filter(Boolean);
}

function joinRuleValues(values: string[]) {
  return values.filter(Boolean).join(" | ") || null;
}

function uniqueSorted(values: Array<string | null | undefined>) {
  return Array.from(new Set(values.map((value) => value?.trim()).filter(Boolean) as string[])).sort((a, b) =>
    a.localeCompare(b, "pt-BR")
  );
}

type SearchOption = {
  value: string;
  label: string;
  meta?: string;
};

function normalizeSearchOptions(options: Array<string | SearchOption>) {
  return options.map((option) => (typeof option === "string" ? { value: option, label: option } : option));
}

function SearchableMultiSelect({
  label,
  placeholder,
  options,
  value,
  onChange
}: {
  label: string;
  placeholder: string;
  options: Array<string | SearchOption>;
  value: string | null | undefined;
  onChange: (value: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const selected = splitRuleValues(value);
  const normalizedSearch = search.trim().toLowerCase();
  const normalizedOptions = normalizeSearchOptions(options);
  const filteredOptions = normalizedOptions
    .filter((option) => {
      const haystack = [option.label, option.value, option.meta ?? ""].join(" ").toLowerCase();
      return !normalizedSearch || haystack.includes(normalizedSearch);
    })
    .slice(0, 80);

  function toggleOption(option: string) {
    const next = selected.includes(option) ? selected.filter((item) => item !== option) : [...selected, option];
    onChange(joinRuleValues(next));
  }

  return (
    <div className="grid gap-1.5">
      <Label>{label}</Label>
      <button
        type="button"
        className="flex min-h-11 w-full items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-left text-sm shadow-sm transition hover:border-slate-300 hover:bg-slate-50"
        onClick={() => setOpen((value) => !value)}
      >
        <div className="min-w-0">
          <div className={selected.length ? "line-clamp-1 font-medium text-slate-950" : "text-sm text-slate-500"}>
            {selected.length ? `${selected.length} selecionado(s)` : placeholder}
          </div>
          <div className="truncate text-xs text-slate-500">
            {selected.length ? selected.slice(0, 3).join(", ") : "Busque e selecione os valores aplicáveis."}
          </div>
        </div>
        <ChevronDown className="h-4 w-4 shrink-0 text-slate-500" />
      </button>
      {selected.length ? (
        <div className="flex flex-wrap gap-2">
          {selected.slice(0, 4).map((item) => (
            <button
              key={item}
              type="button"
              className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-[11px] font-medium text-sky-700"
              onClick={() => toggleOption(item)}
              title={item}
            >
              <span className="max-w-40 truncate">{item}</span>
              <X className="h-3 w-3" />
            </button>
          ))}
          {selected.length > 4 ? <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] text-slate-500">+{selected.length - 4}</span> : null}
        </div>
      ) : null}
      {open ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-3 shadow-[0_18px_48px_rgba(15,23,42,0.12)]">
          <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Pesquisar..." className="mb-3 h-10 text-sm" />
          <div className="max-h-56 space-y-1 overflow-auto">
            {filteredOptions.map((option) => {
              const checked = selected.includes(option.value);
              return (
                <button
                  key={option.value}
                  type="button"
                  className="flex w-full items-center gap-3 rounded-xl border border-transparent px-3 py-2.5 text-left text-sm hover:border-slate-200 hover:bg-slate-50"
                  onClick={() => toggleOption(option.value)}
                  title={option.meta ? `${option.label} - ${option.meta}` : option.label}
                >
                  <span
                    className={cn(
                      "flex h-4 w-4 items-center justify-center rounded border",
                      checked ? "border-blue-600 bg-blue-600 text-white" : "border-slate-300 bg-white text-transparent"
                    )}
                  >
                    {checked ? <Check className="h-3 w-3" /> : null}
                  </span>
                  <span className="min-w-0">
                    <span className="line-clamp-2 font-medium text-slate-800">{option.label}</span>
                    {option.meta ? <span className="line-clamp-1 text-[11px] text-slate-500">{option.meta}</span> : null}
                  </span>
                </button>
              );
            })}
            {filteredOptions.length === 0 ? <div className="px-3 py-6 text-center text-sm text-slate-500">Nenhuma opção encontrada.</div> : null}
          </div>
          <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-3">
            <Button type="button" variant="ghost" size="sm" className="h-8 px-2 text-xs" onClick={() => onChange(null)}>
              Limpar
            </Button>
            <Button type="button" variant="outline" size="sm" className="h-8 px-3 text-xs" onClick={() => setOpen(false)}>
              Fechar
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function downloadJson(config: GamificationConfig) {
  const blob = new Blob([JSON.stringify(config, null, 2)], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "gamification_rules_config.json";
  link.click();
  URL.revokeObjectURL(url);
}

export function LogicConfigurationPanel({
  groups,
  subjectRules,
  importedDiagnoses,
  recurrenceRules,
  healthRules,
  slaRules,
  pointValue,
  periodSubjectSummaries,
  financialBreakdowns,
  setGroups,
  setSubjectRules,
  setRecurrenceRules,
  setHealthRules,
  setSlaRules,
  setPointValue,
  onCreateGroup,
  onSaveGroup,
  onDeleteGroup,
  onSaveSubjectRule,
  onDeleteSubjectRule,
  onSaveDiagnosisRule,
  onSavePointValue,
  onCreateRecurrenceRule,
  onSaveRecurrenceRule,
  onDeleteRecurrenceRule,
  onSaveHealthRule,
  onCreateSlaRule,
  onSaveSlaRule,
  onReload
}: Props) {
  const [mode, setMode] = useState<Mode>("simple");
  const [query, setQuery] = useState("");
  const [config, setConfig] = useState<GamificationConfig | null>(null);
  const [localSettings, setLocalSettings] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [deleteTargets, setDeleteTargets] = useState<Record<number, string>>({});
  const [groupBaselines, setGroupBaselines] = useState<Record<number, GroupSnapshot>>({});
  const [editingGroupId, setEditingGroupId] = useState<number | null>(null);
  const [pendingDeleteGroupId, setPendingDeleteGroupId] = useState<number | null>(null);
  const [pendingDeleteSubjectRuleId, setPendingDeleteSubjectRuleId] = useState<number | null>(null);
  const [editingSubjectId, setEditingSubjectId] = useState<number | null>(null);
  const [selectedSubjectIds, setSelectedSubjectIds] = useState<Set<number>>(new Set());
  const [deleteSubjectSelectionOpen, setDeleteSubjectSelectionOpen] = useState(false);
  const [deletingSubjectSelection, setDeletingSubjectSelection] = useState(false);
  const [savingSubjectId, setSavingSubjectId] = useState<number | null>(null);
  const [selectedGroupIds, setSelectedGroupIds] = useState<Set<number>>(new Set());
  const [deleteGroupSelectionOpen, setDeleteGroupSelectionOpen] = useState(false);
  const [deletingGroupSelection, setDeletingGroupSelection] = useState(false);
  const [savingGroupId, setSavingGroupId] = useState<number | null>(null);
  const [deletingGroupId, setDeletingGroupId] = useState<number | null>(null);
  const [newGroupDraft, setNewGroupDraft] = useState({ name: "", default_points: 0 });
  const [visibleSubjectRulesCount, setVisibleSubjectRulesCount] = useState(80);
  const [visibleDiagnosisRowsCount, setVisibleDiagnosisRowsCount] = useState(80);
  const [typeDrafts, setTypeDrafts] = useState<Record<string, string>>({});
  const [typeGroupDrafts, setTypeGroupDrafts] = useState<Record<string, string>>({});
  const [expandedTypes, setExpandedTypes] = useState<Record<string, boolean>>({});
  const [subjectFilter, setSubjectFilter] = useState<SubjectFilter>("all");
  const [subjectGroupFilter, setSubjectGroupFilter] = useState("all");
  const [diagnosisFilter, setDiagnosisFilter] = useState<DiagnosisFilter>("all");
  const [diagnosisDrafts, setDiagnosisDrafts] = useState<
    Record<
      string,
      {
        action_type: DiagnosisActionType;
        penalty_points: number;
        force_points_value: number | null;
        active: boolean;
        description: string;
      }
    >
  >({});
  const [configSection, setConfigSection] = useState<ConfigSection>("governance");
  const [newRecurrenceRule, setNewRecurrenceRule] = useState<Partial<RecurrenceClassificationRule>>({
    name: "",
    classification: "os_nao_reincidente",
    discount_points: false,
    priority: 100,
    active: true
  });
  const fileRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    api
      .gamificationConfig()
      .then((data) => {
        setConfig(data);
        setLocalSettings(data.settings ?? {});
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    if (mode === "simple" && !SIMPLE_SECTIONS.some((section) => section.value === configSection)) {
      setConfigSection("governance");
    }
  }, [configSection, mode]);

  useEffect(() => {
    setGroupBaselines((current) => {
      const next: Record<number, GroupSnapshot> = {};
      for (const group of groups) {
        next[group.id] = current[group.id] ?? groupSnapshot(group);
      }
      return next;
    });
  }, [groups]);

  const activeGroups = useMemo(() => groups.filter((group) => group.active), [groups]);
  const normalizedQuery = query.trim().toLowerCase();
  const periodSubjectCounts = useMemo(() => {
    const counts = new Map<string, number>();
    periodSubjectSummaries.forEach((item) => {
      const key = subjectRuleKey(item.os_type || "Não informado", item.os_subject || "Não informado");
      counts.set(key, item.service_orders_count);
    });
    return counts;
  }, [periodSubjectSummaries]);
  const closurePaymentByGroup = useMemo(() => {
    const values = new Map<string, { orders: number; impact: number }>();
    financialBreakdowns.cost_by_group.forEach((item) => {
      if (!item.group) return;
      values.set(item.group, {
        orders: item.orders,
        impact: item.estimated_payment
      });
    });
    return values;
  }, [financialBreakdowns.cost_by_group]);
  const closurePaymentBySubject = useMemo(() => {
    const values = new Map<string, { orders: number; impact: number }>();
    financialBreakdowns.cost_by_subject.forEach((item) => {
      if (!item.os_type || !item.os_subject) return;
      values.set(subjectRuleKey(item.os_type, item.os_subject), {
        orders: item.orders,
        impact: item.estimated_payment
      });
    });
    return values;
  }, [financialBreakdowns.cost_by_subject]);
  const periodRuleStats = (rule: ScoringSubjectRule) => {
    const key = subjectRuleKey(rule.os_type || "Não informado", rule.os_subject || "Não informado");
    const closureStats = closurePaymentBySubject.get(key);
    const orders = closureStats?.orders ?? periodSubjectCounts.get(key) ?? 0;
    return {
      orders,
      impact: closureStats?.impact ?? 0
    };
  };

  const subjectsByGroup = useMemo(() => {
    return groups.map((group) => {
      const rules = subjectRules.filter((rule) => {
        const matchesGroup = rule.group_id === group.id;
        const matchesQuery =
          !normalizedQuery ||
          [group.name, rule.os_type, rule.os_subject].some((value) => value.toLowerCase().includes(normalizedQuery));
        return matchesGroup && matchesQuery;
      });
      return {
        group,
        rules,
        orders: closurePaymentByGroup.get(group.name)?.orders ?? rules.reduce((total, rule) => total + periodRuleStats(rule).orders, 0),
        impact: closurePaymentByGroup.get(group.name)?.impact ?? rules.reduce((total, rule) => total + periodRuleStats(rule).impact, 0)
      };
    });
  }, [closurePaymentByGroup, closurePaymentBySubject, groups, normalizedQuery, periodSubjectCounts, subjectRules]);
  const selectedVisibleGroups = subjectsByGroup.filter(({ group }) => selectedGroupIds.has(group.id));
  const allVisibleGroupsSelected = subjectsByGroup.length > 0 && subjectsByGroup.every(({ group }) => selectedGroupIds.has(group.id));
  const currentEditingGroup = editingGroupId != null ? groups.find((group) => group.id === editingGroupId) ?? null : null;
  const pendingDeleteGroup = pendingDeleteGroupId != null ? groups.find((group) => group.id === pendingDeleteGroupId) ?? null : null;
  const pendingDeleteSubjectRule = pendingDeleteSubjectRuleId != null ? subjectRules.find((rule) => rule.id === pendingDeleteSubjectRuleId) ?? null : null;
  const currentEditingSubject = editingSubjectId != null ? subjectRules.find((rule) => rule.id === editingSubjectId) ?? null : null;

  const filteredSubjectRules = useMemo(() => {
    return subjectRules.filter((rule) => {
      const group = groups.find((item) => item.id === rule.group_id);
      const matchesQuery =
        !normalizedQuery || [group?.name ?? "", rule.os_type, rule.os_subject].some((value) => value.toLowerCase().includes(normalizedQuery));
      const matchesFilter =
        subjectFilter === "all" ||
        (subjectFilter === "scored" && Boolean(group) && rule.active) ||
        (subjectFilter === "not_scored" && (!rule.active || !group)) ||
        (subjectFilter === "without_group" && !group);
      const matchesGroupFilter = subjectGroupFilter === "all" || String(rule.group_id) === subjectGroupFilter;
      return matchesQuery && matchesFilter && matchesGroupFilter;
    });
  }, [groups, normalizedQuery, subjectFilter, subjectGroupFilter, subjectRules]);

  const visibleSubjectRules = filteredSubjectRules.slice(0, visibleSubjectRulesCount);
  const selectedVisibleSubjectRules = visibleSubjectRules.filter((rule) => selectedSubjectIds.has(rule.id));
  const allVisibleSubjectsSelected = visibleSubjectRules.length > 0 && visibleSubjectRules.every((rule) => selectedSubjectIds.has(rule.id));

  const filteredSlaRules = useMemo(() => {
    if (!normalizedQuery) return slaRules;
    return slaRules.filter((rule) =>
      [rule.name, rule.penalty_type, String(rule.penalty_value)].some((value) => value.toLowerCase().includes(normalizedQuery))
    );
  }, [normalizedQuery, slaRules]);

  const filteredRecurrenceRules = useMemo(() => {
    if (!normalizedQuery) return recurrenceRules;
    return recurrenceRules.filter((rule) =>
      [
        rule.name,
        rule.os_type_pattern ?? "",
        rule.os_subject_pattern ?? "",
        rule.diagnosis_pattern ?? "",
        rule.classification,
        recurrenceClassificationLabel(rule.classification)
      ].some((value) => value.toLowerCase().includes(normalizedQuery))
    );
  }, [normalizedQuery, recurrenceRules]);

  const diagnosisRows = useMemo(
    () =>
      importedDiagnoses.filter((item) => {
        const matchesQuery =
          !normalizedQuery ||
          [item.diagnosis_name, item.predominant_regional, ...item.related_subjects].some((value) =>
          value.toLowerCase().includes(normalizedQuery)
        );
        const annulsPoints = item.active !== false && (item.action_type === "cancel_points" || item.action_type === "subtract_points");
        const matchesFilter =
          diagnosisFilter === "all" ||
          (diagnosisFilter === "annuls_points" && annulsPoints) ||
          (diagnosisFilter === "without_rule" && !item.has_rule);
        return matchesQuery && matchesFilter;
      }),
    [diagnosisFilter, importedDiagnoses, normalizedQuery]
  );

  const diagnosisConfiguredCount = importedDiagnoses.filter((item) => item.has_rule).length;
  const diagnosisUnconfiguredCount = importedDiagnoses.length - diagnosisConfiguredCount;
  const globalPointValueLabel = pointValue ? formatMoney(Number(pointValue.replace(",", "."))) : "backend";
  const typeRows = useMemo(() => {
    const types = new Map<string, { os_type: string; subjects: number; orders: number; impact: number; groups: Set<string>; inactive: number }>();
    const ensure = (osType: string) => {
      const current = types.get(osType) ?? { os_type: osType, subjects: 0, orders: 0, impact: 0, groups: new Set<string>(), inactive: 0 };
      types.set(osType, current);
      return current;
    };

    subjectRules.forEach((rule) => {
      const row = ensure(rule.os_type || "Não informado");
      const stats = periodRuleStats(rule);
      row.subjects += 1;
      row.orders += stats.orders;
      row.impact += stats.impact;
      const group = groups.find((item) => item.id === rule.group_id);
      if (group) row.groups.add(group.name);
      if (!rule.active) row.inactive += 1;
    });

    return Array.from(types.values()).sort((a, b) => b.orders - a.orders || a.os_type.localeCompare(b.os_type, "pt-BR"));
  }, [closurePaymentBySubject, groups, periodSubjectCounts, subjectRules]);
  const osTypeOptions = useMemo(() => uniqueSorted(subjectRules.map((rule) => rule.os_type)), [subjectRules]);
  const subjectOptions = useMemo(
    () => {
      const bySubject = new Map<string, { types: Set<string>; groups: Set<string> }>();
      subjectRules.forEach((rule) => {
        const subject = rule.os_subject.trim();
        if (!subject) return;
        const current = bySubject.get(subject) ?? { types: new Set<string>(), groups: new Set<string>() };
        current.types.add(rule.os_type);
        if (rule.group?.name) current.groups.add(rule.group.name);
        bySubject.set(subject, current);
      });
      importedDiagnoses.flatMap((item) => item.related_subjects).forEach((subject) => {
        const cleanSubject = subject.trim();
        if (!cleanSubject || bySubject.has(cleanSubject)) return;
        bySubject.set(cleanSubject, { types: new Set<string>(["Não classificado na matriz"]), groups: new Set<string>() });
      });
      return Array.from(bySubject.entries())
        .map(([subject, info]) => ({
          value: subject,
          label: subject,
          meta: [
            `Tipo: ${Array.from(info.types).sort((a, b) => a.localeCompare(b, "pt-BR")).join(", ")}`,
            info.groups.size ? `Grupo: ${Array.from(info.groups).sort((a, b) => a.localeCompare(b, "pt-BR")).join(", ")}` : null
          ]
            .filter(Boolean)
            .join(" | ")
        }))
        .sort((a, b) => a.label.localeCompare(b.label, "pt-BR"));
    },
    [importedDiagnoses, subjectRules]
  );
  const diagnosisOptions = useMemo(
    () =>
      importedDiagnoses
        .map((item) => ({
          value: item.diagnosis_name,
          label: item.diagnosis_name,
          meta: `${formatInteger(item.service_orders_count)} O.S | ${formatInteger(item.subjects_count)} assunto(s)`
        }))
        .sort((a, b) => a.label.localeCompare(b.label, "pt-BR")),
    [importedDiagnoses]
  );

  function diagnosisDraft(item: ImportedDiagnosis) {
    return (
      diagnosisDrafts[item.diagnosis_name] ?? {
        action_type: item.action_type ?? "no_penalty",
        penalty_points: item.penalty_points ?? 0,
        force_points_value: item.force_points_value ?? null,
        active: item.active ?? true,
        description: `Regra operacional para diagnóstico ${item.diagnosis_name}.`
      }
    );
  }

  function updateDiagnosisDraft(item: ImportedDiagnosis, patch: Partial<ReturnType<typeof diagnosisDraft>>) {
    setDiagnosisDrafts((current) => ({
      ...current,
      [item.diagnosis_name]: {
        ...diagnosisDraft(item),
        ...patch
      }
    }));
  }

  async function runConfigAction(action: () => Promise<void>, success: string) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await action();
      setMessage(success);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro inesperado na configuração.");
    } finally {
      setBusy(false);
    }
  }

  async function createGroup() {
    const name = newGroupDraft.name.trim();
    if (!name) {
      setError("Informe o nome do novo grupo de pontuação.");
      return;
    }
    await runConfigAction(async () => {
      await onCreateGroup({
        name,
        default_points: Number(newGroupDraft.default_points || 0),
        active: true
      });
      setNewGroupDraft({ name: "", default_points: 0 });
    }, "Grupo de pontuação criado.");
  }

  function updateGroupField(groupId: number, patch: Partial<ScoringGroup>) {
    setGroups(replaceById(groups, groupId, patch));
  }

  function restoreGroup(groupId: number) {
    const baseline = groupBaselines[groupId];
    if (!baseline) return;
    setGroups(replaceById(groups, groupId, baseline));
  }

  async function saveGroup(groupId: number) {
    const group = groups.find((item) => item.id === groupId);
    if (!group) return;
    setSavingGroupId(groupId);
    await runConfigAction(async () => {
      await onSaveGroup(group);
      setGroupBaselines((current) => ({
        ...current,
        [groupId]: groupSnapshot(group),
      }));
    }, `Grupo "${group.name}" salvo.`);
    setSavingGroupId((current) => (current === groupId ? null : current));
  }

  async function duplicateGroup(group: ScoringGroup) {
    await runConfigAction(async () => {
      await onCreateGroup({
        name: `${group.name} (cópia)`,
        default_points: group.default_points,
        point_value_override: group.point_value_override ?? null,
        active: group.active,
      });
    }, `Cópia do grupo "${group.name}" criada.`);
  }

  async function saveSnapshot() {
    await runConfigAction(async () => {
      const snapshot = await api.gamificationConfig();
      const saved = await api.saveGamificationConfig(snapshot);
      setConfig(saved);
      setLocalSettings(saved.settings ?? {});
      await onReload();
    }, "Configuração permanente salva e versionada.");
  }

  async function exportConfig() {
    await runConfigAction(async () => {
      const exported = await api.exportGamificationConfig();
      downloadJson(exported);
    }, "JSON de configuração exportado.");
  }

  async function importConfig(file: File | null) {
    if (!file) return;
    await runConfigAction(async () => {
      const text = await file.text();
      const payload = JSON.parse(text) as Partial<GamificationConfig>;
      const imported = await api.importGamificationConfig(payload);
      setConfig(imported);
      setLocalSettings(imported.settings ?? {});
      await onReload();
    }, "Configuração JSON importada sem apagar histórico.");
    if (fileRef.current) fileRef.current.value = "";
  }

  async function resetDefault() {
    await runConfigAction(async () => {
      const defaults = await api.resetDefaultGamificationConfig();
      setConfig(defaults);
      setLocalSettings(defaults.settings ?? {});
      await onReload();
    }, "Configuração padrão restaurada.");
  }

  async function saveSettings(patch: Record<string, string>) {
    await runConfigAction(async () => {
      const snapshot = await api.gamificationConfig();
      const saved = await api.saveGamificationConfig({
        ...snapshot,
        settings: {
          ...(snapshot.settings ?? {}),
          ...patch
        }
      });
      setConfig(saved);
      setLocalSettings(saved.settings ?? {});
      await onReload();
    }, "Parâmetro operacional salvo.");
  }

  async function saveHealthRule(rule: HealthRule) {
    if (!Number.isFinite(rule.min_sla) || !Number.isFinite(rule.max_recurrence_rate) || !Number.isFinite(rule.multiplier)) {
      setError("Preencha SLA mínimo, reincidência máxima e multiplicador antes de salvar a faixa.");
      return;
    }
    if (rule.min_sla < 0 || rule.min_sla > 100 || rule.max_recurrence_rate < 0 || rule.max_recurrence_rate > 100) {
      setError("SLA mínimo e reincidência máxima devem ficar entre 0 e 100.");
      return;
    }
    if (rule.multiplier < 0) {
      setError("Multiplicador deve ser maior ou igual a zero.");
      return;
    }
    setError(null);
    await onSaveHealthRule(rule);
  }

  async function deleteGroup(group: ScoringGroup, linkedSubjects: number) {
    const replacementGroupId = deleteTargets[group.id] ? Number(deleteTargets[group.id]) : null;
    const replacementGroup = groups.find((item) => item.id === replacementGroupId) ?? null;
    setDeletingGroupId(group.id);
    await runConfigAction(async () => {
      await onDeleteGroup(group, replacementGroup?.id ?? null);
      setDeleteTargets((current) => {
        const next = { ...current };
        delete next[group.id];
        return next;
      });
      setGroupBaselines((current) => {
        const next = { ...current };
        delete next[group.id];
        return next;
      });
      setPendingDeleteGroupId(null);
      setEditingGroupId((current) => (current === group.id ? null : current));
    }, `Grupo "${group.name}" excluído.`);
    setDeletingGroupId((current) => (current === group.id ? null : current));
  }

  function toggleGroupSelected(id: number, checked: boolean) {
    setSelectedGroupIds((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(id);
      } else {
        next.delete(id);
      }
      return next;
    });
  }

  function toggleAllVisibleGroups(checked: boolean) {
    setSelectedGroupIds((current) => {
      const next = new Set(current);
      subjectsByGroup.forEach(({ group }) => {
        if (checked) {
          next.add(group.id);
        } else {
          next.delete(group.id);
        }
      });
      return next;
    });
  }

  async function deleteSelectedGroups() {
    if (selectedVisibleGroups.length === 0) return;
    setDeletingGroupSelection(true);
    try {
      // Exclusão em lote não pergunta um destino de transferência por grupo - assuntos vinculados
      // ficam sem grupo (mesmo comportamento do destino padrão "Remover vínculos" do modal
      // individual). Quem precisa reatribuir os assuntos antes de apagar, exclui um de cada vez.
      for (const { group } of selectedVisibleGroups) {
        await onDeleteGroup(group, null);
      }
      setSelectedGroupIds(new Set());
      setDeleteGroupSelectionOpen(false);
      setMessage(`${selectedVisibleGroups.length} grupo(s) excluído(s).`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro inesperado ao excluir os grupos selecionados.");
    } finally {
      setDeletingGroupSelection(false);
    }
  }

  async function deleteSubjectRule(rule: ScoringSubjectRule) {
    await onDeleteSubjectRule(rule);
    setPendingDeleteSubjectRuleId(null);
  }

  function toggleSubjectSelected(id: number, checked: boolean) {
    setSelectedSubjectIds((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(id);
      } else {
        next.delete(id);
      }
      return next;
    });
  }

  function toggleAllVisibleSubjects(checked: boolean) {
    setSelectedSubjectIds((current) => {
      const next = new Set(current);
      visibleSubjectRules.forEach((rule) => {
        if (checked) {
          next.add(rule.id);
        } else {
          next.delete(rule.id);
        }
      });
      return next;
    });
  }

  async function deleteSelectedSubjectRules() {
    if (selectedVisibleSubjectRules.length === 0) return;
    setDeletingSubjectSelection(true);
    try {
      for (const rule of selectedVisibleSubjectRules) {
        await onDeleteSubjectRule(rule);
      }
      setSelectedSubjectIds(new Set());
      setDeleteSubjectSelectionOpen(false);
    } finally {
      setDeletingSubjectSelection(false);
    }
  }

  async function saveSubjectRule(rule: ScoringSubjectRule) {
    const latestRule = subjectRules.find((item) => item.id === rule.id) ?? rule;
    if (!latestRule.os_type.trim()) {
      setError("Informe o Tipo Geral do assunto antes de salvar.");
      return;
    }
    setSavingSubjectId(rule.id);
    try {
      await onSaveSubjectRule(latestRule);
      setEditingSubjectId((current) => (current === rule.id ? null : current));
    } finally {
      setSavingSubjectId(null);
    }
  }

  async function saveTypeGeneral(currentType: string) {
    const nextType = (typeDrafts[currentType] ?? currentType).trim();
    if (!nextType) {
      setError("Informe o Tipo Geral antes de aplicar.");
      return;
    }
    if (nextType === currentType) {
      return;
    }

    const rulesToUpdate = subjectRules.filter((rule) => rule.os_type === currentType);
    if (!rulesToUpdate.length) {
      return;
    }

    await runConfigAction(async () => {
      for (const rule of rulesToUpdate) {
        await api.updateScoringSubjectRule(rule.id, {
          os_type: nextType,
          group_id: rule.group_id,
          custom_points: rule.custom_points,
          point_value_override: rule.point_value_override,
          use_group_default: rule.use_group_default,
          active: rule.active
        });
      }
      await onReload();
      setTypeDrafts((current) => {
        const next = { ...current };
        delete next[currentType];
        return next;
      });
    }, `Tipo Geral "${currentType}" atualizado para "${nextType}".`);
  }

  async function saveTypeGroup(currentType: string) {
    const groupId = Number(typeGroupDrafts[currentType] || 0);
    const group = groups.find((item) => item.id === groupId);
    if (!group) {
      setError("Selecione um grupo de pontuação para aplicar ao Tipo Geral.");
      return;
    }

    const rulesToUpdate = subjectRules.filter((rule) => rule.os_type === currentType);
    if (!rulesToUpdate.length) {
      return;
    }

    await runConfigAction(async () => {
      for (const rule of rulesToUpdate) {
        await api.updateScoringSubjectRule(rule.id, {
          os_type: rule.os_type,
          os_subject: rule.os_subject,
          group_id: group.id,
          custom_points: rule.custom_points,
          point_value_override: rule.point_value_override,
          use_group_default: rule.use_group_default,
          active: rule.active
        });
      }
      await onReload();
      setTypeGroupDrafts((current) => {
        const next = { ...current };
        delete next[currentType];
        return next;
      });
    }, `${rulesToUpdate.length} assunto(s) do Tipo Geral "${currentType}" vinculados ao grupo "${group.name}".`);
  }

  async function createRecurrenceRule() {
    if (!newRecurrenceRule.name?.trim()) {
      setError("Informe um nome para a regra de reincidência.");
      return;
    }
    await onCreateRecurrenceRule({
      name: newRecurrenceRule.name.trim(),
      os_type_pattern: newRecurrenceRule.os_type_pattern || null,
      os_subject_pattern: newRecurrenceRule.os_subject_pattern || null,
      diagnosis_pattern: newRecurrenceRule.diagnosis_pattern || null,
      original_os_type_pattern: newRecurrenceRule.original_os_type_pattern || null,
      original_os_subject_pattern: newRecurrenceRule.original_os_subject_pattern || null,
      return_os_type_pattern: newRecurrenceRule.return_os_type_pattern || null,
      return_os_subject_pattern: newRecurrenceRule.return_os_subject_pattern || null,
      return_diagnosis_pattern: newRecurrenceRule.return_diagnosis_pattern || null,
      ignore_diagnosis_pattern: newRecurrenceRule.ignore_diagnosis_pattern || null,
      classification: (newRecurrenceRule.classification ?? "nao_identificado") as RecurrenceClassificationValue,
      discount_points: Boolean(newRecurrenceRule.discount_points),
      max_days: newRecurrenceRule.max_days ?? null,
      require_same_subject: Boolean(newRecurrenceRule.require_same_subject),
      require_same_diagnosis: Boolean(newRecurrenceRule.require_same_diagnosis),
      priority: Number(newRecurrenceRule.priority ?? 100),
      description: newRecurrenceRule.description || null,
      active: newRecurrenceRule.active ?? true
    });
    setNewRecurrenceRule({
      name: "",
      classification: "os_nao_reincidente",
      discount_points: false,
      priority: 100,
      active: true
    });
  }

  return (
    <section className="grid gap-4">
      <div className={configSectionClass}>
        <PageHeader
          title="Configuração da gamificação"
          description={
            mode === "simple"
              ? "Use este modo para governança operacional: valor do ponto, grupos, assuntos e diagnósticos principais."
              : "Use este modo para configurações técnicas: SLA, reincidência, multiplicadores, JSON e restauração."
          }
          action={
            <div className="flex flex-wrap rounded-2xl border border-slate-200 bg-white p-1 shadow-sm">
              <Button variant={mode === "simple" ? "default" : "ghost"} onClick={() => setMode("simple")} className="h-9">
                Simples
              </Button>
              <Button variant={mode === "advanced" ? "default" : "ghost"} onClick={() => setMode("advanced")} className="h-9">
                <SlidersHorizontal className="h-4 w-4" />
                Avançado
              </Button>
            </div>
          }
        />

        <FilterToolbar className="border-t-0">
          <ToolbarSearch value={query} onChange={setQuery} placeholder="Buscar grupo, assunto, diagnóstico, SLA ou reincidência" />
          <ToolbarCount>{mode === "simple" ? "Modo simples" : "Modo avançado"}</ToolbarCount>
          <input ref={fileRef} type="file" accept="application/json,.json" className="hidden" onChange={(event) => importConfig(event.target.files?.[0] ?? null)} />
        </FilterToolbar>

        <StatusToast
          error={error}
          message={message}
          busy={busy}
          busyLabel="Atualizando configuração permanente..."
          onDismissError={() => setError(null)}
          onDismissMessage={() => setMessage(null)}
        />

        <div className="grid gap-3 border-t p-5 sm:grid-cols-2 xl:grid-cols-3">
          <StepHeroCard step={mode === "simple" ? "S" : "A"} title={mode === "simple" ? "Modo simples" : "Modo avançado"} description={mode === "simple" ? "Governança operacional para a apuração diária e o fechamento." : "Regras técnicas, SLA, reincidência e restauração."} />
          <GuidanceCard title="Diagnósticos monitorados" description={`${formatInteger(importedDiagnoses.length)} encontrados, sendo ${formatInteger(diagnosisConfiguredCount)} com regra e ${formatInteger(diagnosisUnconfiguredCount)} sem regra.`} />
          <GuidanceCard title="Base atual" description={`Grupos ativos: ${formatInteger(groups.filter((group) => group.active).length)}. Assuntos configurados: ${formatInteger(subjectRules.length)}. Valor do ponto: ${pointValue ? formatMoney(Number(pointValue.replace(",", "."))) : "Não configurado"}.`} />
        </div>
      </div>

      <section className="rounded-[24px] border border-slate-200 bg-white shadow-[0_10px_40px_rgba(15,23,42,0.05)]">
        <div className="panel-header bg-white">
          <div>
            <h3 className="panel-title">Roteiro de configuração</h3>
            <p className="panel-subtitle">
              Comece pelo essencial da operação. Use o avançado apenas para regras técnicas, integrações e restauração.
            </p>
          </div>
          <Badge className="border-slate-200 bg-slate-50 text-slate-700">
            {mode === "simple" ? "Modo simples" : "Modo avançado"}
          </Badge>
        </div>
        <div className="grid gap-3 p-5 md:grid-cols-2 xl:grid-cols-4">
          {(mode === "simple" ? SIMPLE_SECTIONS : ADVANCED_SECTIONS).map((section, index) => (
            <Button
              key={section.value}
              variant={configSection === section.value ? "default" : "outline"}
              className="h-auto justify-start gap-3 rounded-2xl px-4 py-4 text-left"
              onClick={() => setConfigSection(section.value)}
            >
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border bg-white/80 text-xs font-semibold text-slate-700">
                {index + 1}
              </span>
              <span>
                <span className="block text-sm font-semibold">{section.label}</span>
                <span className="block text-xs font-normal opacity-80">{section.help}</span>
              </span>
            </Button>
          ))}
        </div>
      </section>

      <div className="grid gap-4">
          {configSection === "governance" ? (
            <GovernanceRulesPanel
              pointValue={pointValue}
              setPointValue={setPointValue}
              localSettings={localSettings}
              setLocalSettings={setLocalSettings}
              healthRules={mode === "advanced" ? healthRules : []}
              setHealthRules={setHealthRules}
              onSavePointValue={onSavePointValue}
              onSaveSetting={saveSettings}
              onSaveHealthRule={onSaveHealthRule}
              showHealthRules={false}
            />
          ) : null}

          {configSection === "categories" ? (
          <section className="rounded-[24px] border border-slate-200 bg-white shadow-[0_10px_40px_rgba(15,23,42,0.05)]">
            <div className="panel-header">
              <div>
                <h3 className="panel-title">Tipos gerais da planilha</h3>
                <p className="panel-subtitle">
                  O tipo geral vem da planilha importada e classifica os assuntos por família operacional. Aqui você renomeia o tipo geral; grupo, pontos e status ficam centralizados em Assuntos.
                </p>
              </div>
            </div>
            <div className="grid gap-3 border-b bg-slate-50 p-5 md:grid-cols-3 xl:grid-cols-6">
              {typeRows.map((row) => (
                <div key={row.os_type} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
                  <div className="text-sm font-semibold text-slate-950">{row.os_type}</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <Badge className="border-slate-200 bg-slate-50 text-slate-700">{formatInteger(row.subjects)} assunto(s)</Badge>
                    <Badge className="border-blue-200 bg-blue-50 text-blue-700">{formatInteger(row.orders)} O.S</Badge>
                  </div>
                </div>
              ))}
            </div>
            <Table>
              <TableHeader className="sticky top-0 z-10 bg-slate-900 text-white shadow-sm [&_th]:text-slate-200">
                <TableRow className="border-slate-700 hover:bg-slate-900">
                  <TableHead>Tipo Geral</TableHead>
                  <TableHead>Assuntos</TableHead>
                  <TableHead>O.S impactadas</TableHead>
                  <TableHead>Valor a ser pago</TableHead>
                  <TableHead>Assuntos do Tipo Geral</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Ação</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {typeRows.map((row) => {
                  const rowRules = subjectRules
                    .filter((rule) => rule.os_type === row.os_type)
                    .sort((a, b) => periodRuleStats(b).orders - periodRuleStats(a).orders || a.os_subject.localeCompare(b.os_subject, "pt-BR"));
                  const expanded = Boolean(expandedTypes[row.os_type]);

                  return (
                  <Fragment key={row.os_type}>
                  <TableRow>
                    <TableCell className="min-w-72">
                      <Input
                        value={typeDrafts[row.os_type] ?? row.os_type}
                        onChange={(event) =>
                          setTypeDrafts((current) => ({
                            ...current,
                            [row.os_type]: event.target.value
                          }))
                        }
                      />
                      <div className="mt-1 text-xs text-slate-500">Tipo atual: {row.os_type}</div>
                    </TableCell>
                    <TableCell>{formatInteger(row.subjects)}</TableCell>
                    <TableCell>{formatInteger(row.orders)}</TableCell>
                    <TableCell className="font-medium text-blue-700">{formatMoney(row.impact)}</TableCell>
                    <TableCell className="min-w-96">
                      <div className="grid gap-2">
                        <div className="flex flex-wrap gap-2">
                          {rowRules.slice(0, 4).map((rule) => (
                            <Badge key={rule.id} className="max-w-64 truncate border-slate-200 bg-slate-50 text-slate-700">
                              {rule.os_subject}
                            </Badge>
                          ))}
                          {rowRules.length > 4 ? (
                            <Badge className="border-slate-200 bg-slate-50 text-slate-700">+{rowRules.length - 4}</Badge>
                          ) : null}
                        </div>
                        <button
                          type="button"
                          className="w-fit text-xs font-semibold text-blue-700 hover:text-blue-900"
                          onClick={() =>
                            setExpandedTypes((current) => ({
                              ...current,
                              [row.os_type]: !current[row.os_type]
                            }))
                          }
                        >
                          {expanded ? "Ocultar lista de assuntos" : "Abrir lista de assuntos"}
                        </button>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-2">
                        <Badge className="border-emerald-200 bg-emerald-50 text-emerald-700">Configurado</Badge>
                        {row.inactive ? <Badge className="border-slate-200 bg-slate-50 text-slate-700">{formatInteger(row.inactive)} inativo(s)</Badge> : null}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          size="sm"
                          onClick={() => void saveTypeGeneral(row.os_type)}
                          disabled={(typeDrafts[row.os_type] ?? row.os_type).trim() === row.os_type || busy}
                        >
                          <Save className="h-4 w-4" />
                          Aplicar tipo
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() =>
                            setExpandedTypes((current) => ({
                              ...current,
                              [row.os_type]: !current[row.os_type]
                            }))
                          }
                        >
                          {expanded ? "Ocultar assuntos" : "Ver assuntos"}
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                  {expanded ? (
                    <TableRow>
                      <TableCell colSpan={7} className="bg-slate-50 p-0">
                        <div className="grid gap-3 p-4">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div>
                              <div className="text-sm font-semibold text-slate-950">Assuntos em {row.os_type}</div>
                              <div className="text-xs text-slate-500">Lista de conferência. Para alterar grupo, pontos ou status, use a seção Assuntos.</div>
                            </div>
                            <Badge className="border-slate-200 bg-white text-slate-700">{formatInteger(rowRules.length)} assunto(s)</Badge>
                          </div>

                          <div className="grid gap-2">
                            {rowRules.map((rule) => {
                              const selectedGroup = groups.find((group) => group.id === rule.group_id) ?? null;
                              const status = subjectStatus(rule, selectedGroup);
                              const stats = periodRuleStats(rule);

                              return (
                                <div key={rule.id} className="grid gap-2 rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)] xl:grid-cols-[minmax(260px,1.3fr)_minmax(220px,0.8fr)_150px_150px] xl:items-center">
                                  <div className="min-w-0">
                                    <div className="truncate text-sm font-semibold text-slate-950" title={rule.os_subject}>
                                      {rule.os_subject}
                                    </div>
                                    <div className="text-xs text-slate-500">{formatInteger(stats.orders)} O.S impactadas</div>
                                  </div>
                                  <div className="min-w-0">
                                    <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Grupo atual</div>
                                    <div className="mt-1 truncate text-sm text-slate-700" title={selectedGroup?.name ?? "Sem grupo"}>
                                      {selectedGroup?.name ?? "Sem grupo"}
                                    </div>
                                  </div>
                                  <Badge className={subjectStatusClass(status)}>{subjectStatusLabel(status)}</Badge>
                                  <div className="text-sm font-semibold text-blue-700">{formatMoney(stats.impact)}</div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      </TableCell>
                    </TableRow>
                  ) : null}
                  </Fragment>
                );
                })}
              </TableBody>
            </Table>
          </section>
          ) : null}
          {configSection === "groups" ? (
          <section className="rounded-[24px] border border-slate-200 bg-white shadow-[0_10px_40px_rgba(15,23,42,0.05)]">
            <div className="panel-header">
              <div>
                <h3 className="panel-title">1. Grupos de Pontuação</h3>
                <p className="panel-subtitle">O grupo define pontos e R$/ponto padrão; o assunto pode sobrescrever quando necessário.</p>
              </div>
            </div>
            {/*
              O R$/ponto tem 3 níveis de sobrescrita (assunto > grupo > global, ver
              effective_rule_point_value em scoring_detail.py) mas em nenhum lugar da tela isso era
              dito explicitamente perto do campo - só dava pra descobrir lendo o placeholder
              ("Global R$X"/"Grupo R$X") linha por linha. Achado de revisão: clareza, não bug.
            */}
            <div className="mx-5 mt-4 rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-xs text-slate-700">
              <span className="font-semibold text-slate-950">Prioridade do R$/ponto:</span> assunto &gt; grupo &gt; global. Deixe o campo em
              branco para herdar o valor do nível acima.
            </div>
            <FilterToolbar className="items-end">
              <div className="grid min-w-[260px] flex-1 gap-1">
                <Label>Novo grupo de pontuação</Label>
                <AppInput
                  value={newGroupDraft.name}
                  placeholder="Ex.: Manutenção Especial"
                  onChange={(event) => setNewGroupDraft((current) => ({ ...current, name: event.target.value }))}
                />
              </div>
              <div className="grid w-full max-w-[180px] gap-1">
                <Label>Pontos padrão</Label>
                <AppInput
                  type="number"
                  value={newGroupDraft.default_points}
                  onChange={(event) => setNewGroupDraft((current) => ({ ...current, default_points: Number(event.target.value) }))}
                />
              </div>
              <Button type="button" onClick={() => void createGroup()} disabled={busy}>
                Criar grupo
              </Button>
              <ToolbarCount>{formatInteger(subjectsByGroup.length)} grupo(s) no recorte atual</ToolbarCount>
              {selectedVisibleGroups.length > 0 ? (
                <Button
                  type="button"
                  variant="outline"
                  className="border-red-200 text-red-700 hover:bg-red-50"
                  onClick={() => setDeleteGroupSelectionOpen(true)}
                >
                  <Trash2 className="h-4 w-4" />
                  Excluir selecionados ({selectedVisibleGroups.length})
                </Button>
              ) : null}
            </FilterToolbar>
            <div className="grid gap-3 border-b bg-slate-50/60 px-5 py-4 md:grid-cols-3">
              <GuidanceCard title="Leitura rápida" description='A tabela mostra o essencial; use "Editar" para abrir o cadastro completo do grupo.' />
              <GuidanceCard title="Ações discretas" description="Duplicar e excluir ficam no menu; exclusão sempre confirma em modal." />
              <GuidanceCard title="Impacto visível" description="Assuntos, O.S e custo estimado ficam agrupados em badges suaves para leitura rápida." />
            </div>
            <DataTableFrame className="overflow-x-auto rounded-b-[24px] border-t-0">
            <Table>
              <TableHeader className="sticky top-0 z-10 bg-slate-900 text-white shadow-sm [&_th]:text-slate-200">
                <TableRow className="border-slate-700 hover:bg-slate-900">
                  <TableHead className="w-10">
                    <AppSwitch checked={allVisibleGroupsSelected} onCheckedChange={toggleAllVisibleGroups} label={allVisibleGroupsSelected ? "Todos" : "Selecionar"} />
                  </TableHead>
                  <TableHead>Grupo</TableHead>
                  <TableHead>Pontos do grupo</TableHead>
                  <TableHead>R$/Ponto</TableHead>
                  <TableHead>Assuntos vinculados</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {subjectsByGroup.map(({ group, rules, orders, impact }) => {
                  const baseline = groupBaselines[group.id];
                  const dirty = !sameGroupSnapshot(baseline, groupSnapshot(group));

                  return (
                    <TableRow key={group.id} className={cn("align-top transition-colors hover:bg-slate-50/70", dirty ? "bg-blue-50/40" : "bg-white")}>
                      <TableCell className="py-4">
                        <AppSwitch checked={selectedGroupIds.has(group.id)} onCheckedChange={(checked) => toggleGroupSelected(group.id, checked)} label="" />
                      </TableCell>
                      <TableCell className="min-w-72 py-4">
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="text-sm font-semibold text-slate-950">{group.name}</div>
                          {dirty ? <StatusBadge tone="info">Alterações não salvas</StatusBadge> : null}
                        </div>
                      </TableCell>
                      <TableCell className="py-4 text-sm text-slate-700">{formatPoints(group.default_points)}</TableCell>
                      <TableCell className="py-4 text-sm text-slate-700">
                        {group.point_value_override != null ? formatMoney(group.point_value_override) : `Global ${globalPointValueLabel}`}
                      </TableCell>
                      <TableCell className="min-w-72 py-4">
                        <div className="flex flex-wrap gap-2">
                          <StatusBadge tone="success" className="border-emerald-200 bg-emerald-50 text-emerald-800">
                            {formatInteger(rules.length)} assuntos
                          </StatusBadge>
                          <StatusBadge tone="success" className="border-blue-200 bg-blue-50 text-blue-700">
                            {formatInteger(orders)} O.S
                          </StatusBadge>
                          <StatusBadge tone="success" className="border-emerald-200 bg-emerald-50 text-emerald-700">
                            {formatMoney(impact)}
                          </StatusBadge>
                        </div>
                      </TableCell>
                      <TableCell className="py-4">{group.active ? <StatusBadge tone="success">Ativo</StatusBadge> : <StatusBadge>Inativo</StatusBadge>}</TableCell>
                      <TableCell className="py-4">
                        <div className="flex items-center justify-end gap-2">
                          <Button variant="outline" size="sm" onClick={() => setEditingGroupId(group.id)}>
                            Editar
                          </Button>
                          <RowActionMenu
                            ariaLabel={`Ações do grupo ${group.name}`}
                            items={[
                              {
                                label: "Duplicar",
                                onSelect: () => void duplicateGroup(group),
                              },
                              ...(dirty
                                ? [
                                    {
                                      label: "Descartar alterações não salvas",
                                      onSelect: () => restoreGroup(group.id),
                                    },
                                  ]
                                : []),
                              {
                                label: "Excluir",
                                onSelect: () => setPendingDeleteGroupId(group.id),
                                tone: "danger" as const,
                              },
                            ]}
                          />
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
            </DataTableFrame>
          </section>
          ) : null}

          {configSection === "subjects" ? (
          <section className="rounded-[24px] border border-slate-200 bg-white shadow-[0_10px_40px_rgba(15,23,42,0.05)]">
            <div className="panel-header">
              <div>
                <h3 className="panel-title">2. Assuntos</h3>
                <p className="panel-subtitle">Vínculo permanente de assunto para grupo, com pontos e valor por ponto específicos quando precisar.</p>
              </div>
            </div>
            <div className="mx-5 mt-4 rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-xs text-slate-700">
              <span className="font-semibold text-slate-950">Prioridade do R$/ponto:</span> assunto &gt; grupo &gt; global. Deixe o campo em
              branco para herdar o valor do nível acima.
            </div>
            <div className="grid gap-3 border-b bg-slate-50/60 px-5 py-4 md:grid-cols-2">
              <GuidanceCard title="Leitura rápida" description='A tabela mostra o essencial; use "Editar" para abrir o cadastro completo do assunto.' />
              <GuidanceCard title="Ação em lote" description="Marque as linhas na coluna à esquerda para remover vários assuntos de uma vez." />
            </div>
            <FilterToolbar>
              {[
                ["all", "Todos"],
                ["scored", "Pontuam"],
                ["not_scored", "Não pontuam"],
                ["without_group", "Sem grupo"]
              ].map(([value, label]) => (
                <Button
                  key={value}
                  type="button"
                  variant={subjectFilter === value ? "default" : "outline"}
                  size="sm"
                  onClick={() => setSubjectFilter(value as SubjectFilter)}
                >
                  {label}
                </Button>
              ))}
              <div className="flex min-w-72 items-center gap-2">
                <Label htmlFor="subject-group-filter" className="sr-only">
                  Filtrar por grupo
                </Label>
                <AppCombobox
                  value={subjectGroupFilter}
                  onChange={setSubjectGroupFilter}
                  placeholder="Todos os grupos"
                  ariaLabel="Filtrar assuntos por grupo"
                  options={[
                    { value: "all", label: "Todos os grupos", description: "Exibe qualquer grupo vinculado." },
                    ...activeGroups.map((group) => ({
                      value: String(group.id),
                      label: group.name,
                      description: `${formatPoints(group.default_points)} por grupo`,
                    })),
                  ]}
                />
                {subjectGroupFilter !== "all" ? (
                  <Button type="button" variant="outline" size="sm" onClick={() => setSubjectGroupFilter("all")}>
                    Limpar grupo
                  </Button>
                ) : null}
              </div>
              <ToolbarCount>{formatInteger(filteredSubjectRules.length)} assunto(s) no filtro</ToolbarCount>
              {selectedVisibleSubjectRules.length > 0 ? (
                <Button
                  type="button"
                  variant="outline"
                  className="border-red-200 text-red-700 hover:bg-red-50"
                  onClick={() => setDeleteSubjectSelectionOpen(true)}
                >
                  <Trash2 className="h-4 w-4" />
                  Remover selecionados ({selectedVisibleSubjectRules.length})
                </Button>
              ) : null}
            </FilterToolbar>
            <DataTableFrame>
            <Table>
              <TableHeader className="sticky top-0 z-10 bg-slate-900 text-white shadow-sm [&_th]:text-slate-200">
                <TableRow className="border-slate-700 hover:bg-slate-900">
                  <TableHead className="w-10">
                    <AppSwitch checked={allVisibleSubjectsSelected} onCheckedChange={toggleAllVisibleSubjects} label={allVisibleSubjectsSelected ? "Todos" : "Selecionar"} />
                  </TableHead>
                  <TableHead>Assunto</TableHead>
                  <TableHead>Grupo vinculado</TableHead>
                  <TableHead>Pontos</TableHead>
                  <TableHead>R$/ponto</TableHead>
                  <TableHead>O.S impactadas</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {visibleSubjectRules.map((rule) => {
                  const selectedGroup = groups.find((group) => group.id === rule.group_id) ?? null;
                  const stats = periodRuleStats(rule);
                  const status = subjectStatus(rule, selectedGroup);

                  return (
                  <TableRow key={rule.id}>
                    <TableCell>
                      <AppSwitch checked={selectedSubjectIds.has(rule.id)} onCheckedChange={(checked) => toggleSubjectSelected(rule.id, checked)} label="" />
                    </TableCell>
                    <TableCell className="min-w-72">
                      <div className="font-medium text-slate-950">{rule.os_subject}</div>
                      <div className="text-xs text-slate-500">Tipo Geral: {rule.os_type}</div>
                    </TableCell>
                    <TableCell className="min-w-48 text-sm text-slate-700">
                      {selectedGroup ? selectedGroup.name : <Badge className="border-amber-200 bg-amber-50 text-amber-800">Sem grupo</Badge>}
                    </TableCell>
                    <TableCell className="text-sm text-slate-700">{formatPoints(rule.effective_points)}</TableCell>
                    <TableCell className="text-sm text-slate-700">
                      {rule.point_value_override != null
                        ? formatMoney(rule.point_value_override)
                        : selectedGroup?.point_value_override != null
                          ? `Grupo ${formatMoney(selectedGroup.point_value_override)}`
                          : `Global ${globalPointValueLabel}`}
                    </TableCell>
                    <TableCell>
                      <div className="font-medium">{formatInteger(stats.orders)}</div>
                      <div className="text-xs font-medium text-blue-700">{formatMoney(stats.impact)}</div>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-2">
                        <Badge className={subjectStatusClass(status)}>{subjectStatusLabel(status)}</Badge>
                        <Badge className={rule.active ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-slate-50 text-slate-700"}>
                          {rule.active ? "Ativo" : "Inativo"}
                        </Badge>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center justify-end gap-2">
                        <Button variant="outline" size="sm" onClick={() => setEditingSubjectId(rule.id)}>
                          Editar
                        </Button>
                        <RowActionMenu
                          ariaLabel={`Ações do assunto ${rule.os_subject}`}
                          items={[{ label: "Remover", onSelect: () => setPendingDeleteSubjectRuleId(rule.id), tone: "danger" }]}
                        />
                      </div>
                    </TableCell>
                  </TableRow>
                  );
                })}
                {visibleSubjectRules.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8} className="py-6 text-center text-sm text-slate-500">
                      Nenhum assunto encontrado para os filtros atuais.
                    </TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
            </DataTableFrame>
            {filteredSubjectRules.length > visibleSubjectRulesCount ? (
              <div className="flex items-center justify-center border-t border-slate-200 py-3">
                <Button type="button" variant="outline" size="sm" onClick={() => setVisibleSubjectRulesCount((count) => count + 80)}>
                  Mostrar mais ({visibleSubjectRulesCount} de {formatInteger(filteredSubjectRules.length)})
                </Button>
              </div>
            ) : null}
          </section>
          ) : null}

          {configSection === "diagnoses" ? (
          <section className="rounded-[24px] border border-slate-200 bg-white shadow-[0_10px_40px_rgba(15,23,42,0.05)]">
            <div className="panel-header">
              <div>
                <h3 className="panel-title">3. Diagnósticos</h3>
                <p className="panel-subtitle">Diagnóstico pode anular, liberar, forçar ponto ou exigir revisão sem alterar a classificação do assunto.</p>
              </div>
            </div>
            <FilterToolbar>
              {[
                ["all", "Todos"],
                ["annuls_points", "Anulam pontos"],
                ["without_rule", "Sem regra"]
              ].map(([value, label]) => (
                <Button
                  key={value}
                  type="button"
                  variant={diagnosisFilter === value ? "default" : "outline"}
                  size="sm"
                  onClick={() => setDiagnosisFilter(value as DiagnosisFilter)}
                >
                  {label}
                </Button>
              ))}
              <ToolbarCount>{formatInteger(diagnosisRows.length)} diagnóstico(s) no filtro</ToolbarCount>
            </FilterToolbar>
            <DataTableFrame>
            <Table>
              <TableHeader className="sticky top-0 z-10 bg-slate-900 text-white shadow-sm [&_th]:text-slate-200">
                <TableRow className="border-slate-700 hover:bg-slate-900">
                  <TableHead>Diagnóstico</TableHead>
                  <TableHead>Qtd O.S</TableHead>
                  <TableHead>Ação</TableHead>
                  <TableHead>Pontos</TableHead>
                  <TableHead>Impacto</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Ação</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {diagnosisRows.slice(0, visibleDiagnosisRowsCount).map((item) => {
                  const draft = diagnosisDraft(item);
                  const value = draft.action_type === "force_points" ? draft.force_points_value ?? "" : draft.penalty_points;
                  const pointsField = diagnosisPointsFieldState(draft.action_type);
                  return (
                    <TableRow key={item.diagnosis_name}>
                      <TableCell className="min-w-64 font-medium">{item.diagnosis_name}</TableCell>
                      <TableCell>{formatInteger(item.service_orders_count)}</TableCell>
                      <TableCell className="min-w-56">
                        <AppCombobox
                          value={draft.action_type}
                          onChange={(value) => updateDiagnosisDraft(item, { action_type: value as DiagnosisActionType })}
                          placeholder="Selecionar ação"
                          ariaLabel={`Ação do diagnóstico ${item.diagnosis_name}`}
                          options={[
                            { value: "subtract_points", label: "Subtrair pontos", description: "Desconta uma pontuação fixa da ocorrência." },
                            { value: "cancel_points", label: "Anular pontos", description: "Zera a pontuação dessa ocorrência." },
                            { value: "no_penalty", label: "Sem anulação", description: "Mantém a pontuação original." },
                            { value: "requires_review", label: "Revisão manual", description: "Leva o caso para análise operacional." },
                            { value: "force_points", label: "Forçar pontos", description: "Aplica um valor fixo de pontos." },
                          ]}
                        />
                        <div className="mt-1 text-xs text-slate-500">{actionLabel(draft.action_type)}</div>
                      </TableCell>
                      <TableCell className="w-36">
                        <Input
                          type="number"
                          value={pointsField.editable ? value : ""}
                          disabled={!pointsField.editable}
                          placeholder={pointsField.editable ? undefined : "N/A"}
                          onChange={(event) =>
                            updateDiagnosisDraft(
                              item,
                              draft.action_type === "force_points"
                                ? { force_points_value: event.target.value === "" ? null : Number(event.target.value) }
                                : { penalty_points: Number(event.target.value || 0) }
                            )
                          }
                        />
                        <div className="mt-1 text-xs text-slate-500">{pointsField.helper}</div>
                      </TableCell>
                      <TableCell className="font-medium text-blue-700">{formatMoney(item.estimated_impact)}</TableCell>
                      <TableCell>
                        <Badge className={item.has_rule ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-amber-200 bg-amber-50 text-amber-800"}>
                          {item.has_rule ? "Configurado" : "Sem regra"}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="default"
                          size="sm"
                          onClick={() => onSaveDiagnosisRule(item.diagnosis_name, item.rule_id, draft)}
                        >
                          <Save className="h-4 w-4" />
                          Salvar
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
            </DataTableFrame>
            {diagnosisRows.length > visibleDiagnosisRowsCount ? (
              <div className="flex items-center justify-center border-t border-slate-200 py-3">
                <Button type="button" variant="outline" size="sm" onClick={() => setVisibleDiagnosisRowsCount((count) => count + 80)}>
                  Mostrar mais ({visibleDiagnosisRowsCount} de {formatInteger(diagnosisRows.length)})
                </Button>
              </div>
            ) : null}
          </section>
          ) : null}

          {configSection === "sla" ? (
          <section className="rounded-[24px] border border-slate-200 bg-white shadow-[0_10px_40px_rgba(15,23,42,0.05)]">
            <div className="panel-header">
              <div>
                <h3 className="panel-title">4. SLA</h3>
                <p className="panel-subtitle">Configure se O.S fora do prazo perde ponto, reduz percentual, anula ou vai para revisão.</p>
              </div>
              {slaRules.length === 0 ? (
                <Button variant="outline" onClick={onCreateSlaRule}>
                  Criar regra SLA padrão
                </Button>
              ) : null}
            </div>
            <div className="overflow-hidden rounded-b-[24px] border-t border-slate-200">
            <Table>
              <TableHeader className="sticky top-0 z-10 bg-slate-900 text-white shadow-sm [&_th]:text-slate-200">
                <TableRow className="border-slate-700 hover:bg-slate-900">
                  <TableHead>Regra</TableHead>
                  <TableHead>Regra ativa</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Valor</TableHead>
                  <TableHead>Ação</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredSlaRules.map((rule) => {
                  const valueField = slaValueFieldState(rule.penalty_type);
                  return (
                  <TableRow key={rule.id}>
                    <TableCell className="min-w-56 font-medium">{rule.name}</TableCell>
                    <TableCell>
                      <AppSwitch checked={rule.active} onCheckedChange={(checked) => setSlaRules(replaceById(slaRules, rule.id, { active: checked }))} />
                    </TableCell>
                    <TableCell className="min-w-64">
                      <AppCombobox
                        value={rule.penalty_type}
                        onChange={(value) => setSlaRules(replaceById(slaRules, rule.id, { penalty_type: value as SlaPenaltyType }))}
                        placeholder="Selecionar tipo"
                        ariaLabel={`Tipo de penalidade da regra ${rule.name}`}
                        options={[
                          { value: "none", label: "Sem anulação", description: "Mantém a pontuação da O.S fora do prazo." },
                          { value: "subtract_points", label: "Subtrair pontos", description: "Desconta uma pontuação fixa." },
                          { value: "percentage_reduction", label: "Redução percentual", description: "Aplica redução proporcional da pontuação." },
                          { value: "cancel_points", label: "Anular pontos", description: "Zera os pontos da O.S fora do prazo." },
                          { value: "requires_review", label: "Revisão manual", description: "Leva o caso para conferência operacional." },
                        ]}
                      />
                    </TableCell>
                    <TableCell className="w-40">
                      <Input
                        type="number"
                        value={valueField.editable ? rule.penalty_value : ""}
                        disabled={!valueField.editable}
                        placeholder={valueField.editable ? undefined : "N/A"}
                        onChange={(event) => setSlaRules(replaceById(slaRules, rule.id, { penalty_value: Number(event.target.value) }))}
                      />
                      <div className="mt-1 text-xs text-slate-500">{valueField.helper}</div>
                    </TableCell>
                    <TableCell>
                      <Button variant="default" size="sm" onClick={() => onSaveSlaRule(rule)}>
                        <Save className="h-4 w-4" />
                        Salvar
                      </Button>
                    </TableCell>
                  </TableRow>
                  );
                })}
              </TableBody>
            </Table>
            </div>
            <div className="border-t p-5">
              <div className="mb-3">
                <h4 className="text-sm font-semibold text-slate-950">Multiplicadores de saúde operacional</h4>
                <p className="text-xs text-slate-500">
                  Configuração técnica do modo avançado: combina SLA mínimo, reincidência máxima e multiplicador final da base.
                </p>
              </div>
              <div className="overflow-hidden rounded-2xl border border-slate-200">
                <Table>
                  <TableHeader className="sticky top-0 z-10 bg-slate-900 text-white shadow-sm [&_th]:text-slate-200">
                    <TableRow className="border-slate-700 hover:bg-slate-900">
                      <TableHead>Faixa</TableHead>
                      <TableHead>SLA min.</TableHead>
                      <TableHead>Reinc. max.</TableHead>
                      <TableHead>Multiplicador</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Ação</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {healthRules.map((rule) => (
                      <TableRow key={rule.id}>
                        <TableCell className="font-medium">{rule.name}</TableCell>
                        <TableCell className="w-28">
                          <Input
                            type="number"
                            value={numericInputValue(rule.min_sla)}
                            onChange={(event) => setHealthRules(replaceById(healthRules, rule.id, { min_sla: parseNumericInput(event.target.value) }))}
                          />
                        </TableCell>
                        <TableCell className="w-28">
                          <Input
                            type="number"
                            value={numericInputValue(rule.max_recurrence_rate)}
                            onChange={(event) =>
                              setHealthRules(replaceById(healthRules, rule.id, { max_recurrence_rate: parseNumericInput(event.target.value) }))
                            }
                          />
                        </TableCell>
                        <TableCell className="w-32">
                          <Input
                            type="number"
                            step="0.05"
                            value={numericInputValue(rule.multiplier)}
                            onChange={(event) => setHealthRules(replaceById(healthRules, rule.id, { multiplier: parseNumericInput(event.target.value) }))}
                          />
                        </TableCell>
                        <TableCell>
                          <Badge className={rule.active ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-slate-50 text-slate-700"}>
                            {rule.active ? "Ativo" : "Inativo"}
                          </Badge>
                          <label className="mt-2 flex items-center gap-2 text-xs text-slate-600">
                            <input
                              type="checkbox"
                              className="h-4 w-4 accent-blue-700"
                              checked={rule.active}
                              onChange={(event) => setHealthRules(replaceById(healthRules, rule.id, { active: event.target.checked }))}
                            />
                            Usar faixa
                          </label>
                        </TableCell>
                        <TableCell>
                          <Button variant="default" size="sm" onClick={() => saveHealthRule(rule)}>
                            <Save className="h-4 w-4" />
                            Salvar
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                    <TableRow>
                      <TableCell className="font-medium">Abaixo do mínimo</TableCell>
                      <TableCell className="text-xs text-slate-500">Sem faixa</TableCell>
                      <TableCell className="text-xs text-slate-500">Sem faixa</TableCell>
                      <TableCell className="w-32">
                        <Input
                          type="number"
                          step="0.05"
                          value={localSettings[HEALTH_BELOW_MINIMUM_MULTIPLIER_SETTING] ?? "0"}
                          onChange={(event) =>
                            setLocalSettings({
                              ...localSettings,
                              [HEALTH_BELOW_MINIMUM_MULTIPLIER_SETTING]: event.target.value,
                            })
                          }
                          onBlur={(event) => {
                            const value = event.target.value === "" ? "0" : event.target.value;
                            setLocalSettings({
                              ...localSettings,
                              [HEALTH_BELOW_MINIMUM_MULTIPLIER_SETTING]: value,
                            });
                            void saveSettings({ [HEALTH_BELOW_MINIMUM_MULTIPLIER_SETTING]: value });
                          }}
                        />
                      </TableCell>
                      <TableCell>
                        <Badge className="border-amber-200 bg-amber-50 text-amber-700">Fallback</Badge>
                        <p className="mt-2 text-xs text-slate-500">Aplica quando nenhuma faixa ativa for atingida.</p>
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="default"
                          size="sm"
                          onClick={() => {
                            const value = localSettings[HEALTH_BELOW_MINIMUM_MULTIPLIER_SETTING] || "0";
                            void saveSettings({ [HEALTH_BELOW_MINIMUM_MULTIPLIER_SETTING]: value });
                          }}
                        >
                          <Save className="h-4 w-4" />
                          Salvar
                        </Button>
                      </TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </div>
            </div>
          </section>
          ) : null}

          {configSection === "recurrence" ? (
          <section className="rounded-[24px] border border-slate-200 bg-white shadow-[0_10px_40px_rgba(15,23,42,0.05)]">
            <div className="panel-header">
              <div>
                <h3 className="panel-title">5. Reincidência</h3>
                <p className="panel-subtitle">
                  Configure quando um retorno do mesmo cliente deve sinalizar reincidência ou anular a pontuação da O.S original.
                </p>
              </div>
            </div>
            <div className="grid gap-3 border-b bg-slate-50 p-5 md:grid-cols-4 xl:grid-cols-7">
              {[
                ["1", "O.S original concluída"],
                ["2", "Mesmo cliente/contrato/login"],
                ["3", `Dentro de ${localSettings.recurrence_window_days || "30"} dias`],
                ["4", "Origem entra na regra"],
                ["5", "Retorno confirma reincidência"],
                ["6", recurrenceActionLabel(localSettings.recurrence_action || "")],
                ["7", "Auditoria mostra evidências"]
              ].map(([step, label]) => (
                <div key={step} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
                  <div className="mb-2 flex h-6 w-6 items-center justify-center rounded-full bg-blue-700 text-xs font-semibold text-white">{step}</div>
                  <div className="text-xs font-semibold text-slate-700">{label}</div>
                </div>
              ))}
            </div>

            <div className="grid gap-4 border-b p-5 xl:grid-cols-[1fr_1.4fr]">
              <div className="grid gap-4">
              <section className="rounded-2xl border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
                <div className="border-b bg-slate-50 px-4 py-3">
                  <h4 className="text-sm font-semibold text-slate-950">Configuração geral</h4>
                  <p className="text-xs text-slate-500">Vínculo do cliente usado para detectar reincidência nesta tela; janela e ação padrão ficam em Governança geral.</p>
                </div>
                <div className="grid gap-4 p-4">
                  {/*
                    Janela/ação padrão/pontos fixos eram editados aqui E em GovernanceRulesPanel (aba
                    "Governança geral") - mesmo campo, duas telas, com rótulos levemente diferentes
                    ("Ação padrão" aqui vs "Ação quando confirmar reincidência" lá). Achado de revisão:
                    clássico "qual dos dois é o de verdade?". Mantém só um lugar editável e recapitula
                    o valor atual aqui, com atalho direto pra editar.
                  */}
                  <div className="grid gap-2 rounded-2xl border border-blue-100 bg-blue-50 p-4 text-xs text-slate-700">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-semibold text-slate-950">Janela e ação padrão configuradas em Governança geral</span>
                      <Button type="button" variant="outline" size="sm" onClick={() => setConfigSection("governance")}>
                        Editar em Governança geral
                      </Button>
                    </div>
                    <div>
                      Janela atual: <span className="font-medium">{localSettings.recurrence_window_days || "30"} dias</span> · Ação padrão:{" "}
                      <span className="font-medium">{recurrenceActionLabel(localSettings.recurrence_action || "")}</span>
                      {localSettings.recurrence_action === "subtract_original" ? (
                        <>
                          {" "}
                          · Pontos fixos: <span className="font-medium">{localSettings.recurrence_penalty_points || "0"}</span>
                        </>
                      ) : null}
                    </div>
                  </div>
                  <div className="grid gap-2">
                    <Label>Campos de vínculo</Label>
                    <div className={cn(configCardClass, "grid grid-cols-2 gap-2 text-xs")}>
                      {[
                        ["login", "Login"],
                        ["contract", "Contrato"],
                        ["cliente", "Cliente"],
                        ["cpf_cnpj", "CPF/CNPJ"]
                      ].map(([field, label]) => (
                        <label key={field} className="flex items-center gap-2">
                          <input
                            type="checkbox"
                            className="h-4 w-4 accent-blue-700"
                            checked={recurrenceIdentityFields(localSettings).includes(field)}
                            disabled={field === "cpf_cnpj"}
                            onChange={(event) => {
                              const value = toggleIdentityField(localSettings, field, event.target.checked);
                              setLocalSettings({ ...localSettings, recurrence_identity_fields: value });
                              saveSettings({ recurrence_identity_fields: value });
                            }}
                          />
                          {label}
                        </label>
                      ))}
                    </div>
                    <div className="text-[11px] text-slate-500">CPF/CNPJ não identificado no código atual da importação.</div>
                  </div>
                </div>
              </section>

              {/*
                warranty_mode/warranty_reduction_percentage: setting real, lido em explain_order
                (scoring_detail.py) pra decidir como a PRÓPRIA O.S de garantia/reincidência pontua
                (pontua normal, pontua com redução, não pontua, ou vai pra revisão manual). Achado de
                revisão: esse setting nunca teve controle nenhuma tela - só dava pra mudar editando o
                banco ou o JSON exportado - e o nome fica fácil de confundir com "Ação padrão" acima,
                que é sobre a O.S ORIGINAL quando um retorno confirma reincidência, não sobre a O.S
                de garantia em si. Título e texto abaixo tentam deixar essa diferença clara.
              */}
              <section className="rounded-2xl border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
                <div className="border-b bg-slate-50 px-4 py-3">
                  <h4 className="text-sm font-semibold text-slate-950">Pontuação da própria O.S de garantia/reincidência</h4>
                  <p className="text-xs text-slate-500">
                    Diferente da "Ação padrão" acima (que decide o que acontece com a O.S <strong>original</strong> quando um retorno confirma
                    reincidência): isto decide como pontua a O.S de garantia/retorno <strong>em si</strong>.
                  </p>
                </div>
                <div className="grid gap-4 p-4 md:grid-cols-2">
                  <div className="grid gap-2">
                    <Label>Como pontuar</Label>
                    <AppCombobox
                      value={localSettings.warranty_mode ?? "score_full"}
                      onChange={(value) => {
                        setLocalSettings({ ...localSettings, warranty_mode: value });
                        void saveSettings({ warranty_mode: value });
                      }}
                      placeholder="Pontua normalmente"
                      ariaLabel="Como pontuar a O.S de garantia/reincidência"
                      options={[
                        { value: "score_full", label: "Pontua normalmente", description: "A O.S de garantia/reincidência pontua igual a qualquer outra." },
                        { value: "score_reduced", label: "Pontua com redução", description: "Aplica um percentual de desconto sobre a pontuação base." },
                        { value: "no_points", label: "Não pontua", description: "A O.S de garantia/reincidência não gera pontos." },
                        { value: "requires_review", label: "Exige revisão manual", description: "Pontua, mas fica marcada para conferência." },
                      ]}
                    />
                  </div>
                  {(localSettings.warranty_mode ?? "score_full") === "score_reduced" ? (
                    <div className="grid gap-2">
                      <Label>Redução (%)</Label>
                      <Input
                        inputMode="decimal"
                        value={localSettings.warranty_reduction_percentage ?? ""}
                        onChange={(event) => setLocalSettings({ ...localSettings, warranty_reduction_percentage: event.target.value })}
                        onBlur={(event) => saveSettings({ warranty_reduction_percentage: event.target.value })}
                        placeholder="Ex.: 50"
                      />
                    </div>
                  ) : null}
                </div>
              </section>
              </div>

              <section className="rounded-2xl border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
                <div className="border-b bg-slate-50 px-4 py-3">
                  <h4 className="text-sm font-semibold text-slate-950">Nova regra</h4>
                  <p className="text-xs text-slate-500">Monte a regra por origem, retorno, diagnóstico e decisão final.</p>
                </div>
                <div className="grid gap-4 p-4">
                  <div className="grid gap-3 md:grid-cols-[1fr_260px]">
                    <div className="grid gap-2">
                      <Label>Nome da regra</Label>
                      <Input
                        value={newRecurrenceRule.name ?? ""}
                        onChange={(event) => setNewRecurrenceRule({ ...newRecurrenceRule, name: event.target.value })}
                        placeholder="Ex.: Reincidência de manutenção fibra"
                      />
                    </div>
                    <div className="grid gap-2">
                      <Label>Subtipo</Label>
                      <AppCombobox
                      value={newRecurrenceRule.classification ?? "reincidencia_tecnica"}
                        onChange={(value) =>
                          setNewRecurrenceRule({
                            ...newRecurrenceRule,
                            classification: value as RecurrenceClassificationValue,
                            discount_points: ["reincidencia_tecnica", "garantia"].includes(value)
                          })
                        }
                        placeholder="Selecionar subtipo"
                        ariaLabel="Subtipo da nova regra de reincidência"
                        options={[
                          { value: "reincidencia_tecnica", label: "Reincidência de manutenção" },
                          { value: "garantia", label: "Reincidência após ativação" },
                          { value: "recorrencia_operacional", label: "Reincidência operacional" },
                          { value: "os_nao_reincidente", label: "Não caracteriza reincidência" },
                          { value: "demandas_diferentes", label: "Demandas diferentes" },
                          { value: "nao_identificado", label: "Não identificado" },
                        ]}
                      />
                    </div>
                  </div>
                  <div className="grid gap-3 lg:grid-cols-2">
                    <div className="grid gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-4">
                      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">1. O.S original entra na regra</div>
                      <SearchableMultiSelect
                        label="Tipo original"
                        placeholder="Selecionar tipo"
                        options={osTypeOptions}
                        value={newRecurrenceRule.original_os_type_pattern}
                        onChange={(value) => setNewRecurrenceRule({ ...newRecurrenceRule, original_os_type_pattern: value })}
                      />
                      <SearchableMultiSelect
                        label="Assunto original"
                        placeholder="Selecionar assunto"
                        options={subjectOptions}
                        value={newRecurrenceRule.original_os_subject_pattern}
                        onChange={(value) => setNewRecurrenceRule({ ...newRecurrenceRule, original_os_subject_pattern: value })}
                      />
                    </div>
                    <div className="grid gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-4">
                      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">2. O.S retorno confirma reincidência</div>
                      <SearchableMultiSelect
                        label="Tipo retorno"
                        placeholder="Selecionar tipo"
                        options={osTypeOptions}
                        value={newRecurrenceRule.return_os_type_pattern}
                        onChange={(value) => setNewRecurrenceRule({ ...newRecurrenceRule, return_os_type_pattern: value })}
                      />
                      <SearchableMultiSelect
                        label="Assunto retorno"
                        placeholder="Selecionar assunto"
                        options={subjectOptions}
                        value={newRecurrenceRule.return_os_subject_pattern}
                        onChange={(value) => setNewRecurrenceRule({ ...newRecurrenceRule, return_os_subject_pattern: value })}
                      />
                      <SearchableMultiSelect
                        label="Diagnóstico que confirma"
                        placeholder="Selecionar diagnóstico"
                        options={diagnosisOptions}
                        value={newRecurrenceRule.return_diagnosis_pattern}
                        onChange={(value) => setNewRecurrenceRule({ ...newRecurrenceRule, return_diagnosis_pattern: value })}
                      />
                      <SearchableMultiSelect
                        label="Diagnóstico que ignora"
                        placeholder="Selecionar diagnóstico"
                        options={diagnosisOptions}
                        value={newRecurrenceRule.ignore_diagnosis_pattern}
                        onChange={(value) => setNewRecurrenceRule({ ...newRecurrenceRule, ignore_diagnosis_pattern: value })}
                      />
                    </div>
                  </div>
                  <div className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
                    <div className="flex flex-wrap items-center gap-4">
                      <label
                        className={cn(
                          "flex items-center gap-2 text-sm",
                          !classificationSupportsDiscount(newRecurrenceRule.classification ?? "reincidencia_tecnica") && "text-slate-400"
                        )}
                      >
                        <input
                          type="checkbox"
                          className="h-4 w-4 accent-blue-700"
                          checked={Boolean(newRecurrenceRule.discount_points)}
                          disabled={!classificationSupportsDiscount(newRecurrenceRule.classification ?? "reincidencia_tecnica")}
                          onChange={(event) => setNewRecurrenceRule({ ...newRecurrenceRule, discount_points: event.target.checked })}
                        />
                        Pode anular a O.S original
                      </label>
                      <label className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          className="h-4 w-4 accent-blue-700"
                          checked={Boolean(newRecurrenceRule.require_same_subject)}
                          onChange={(event) => setNewRecurrenceRule({ ...newRecurrenceRule, require_same_subject: event.target.checked })}
                        />
                        Exigir mesmo assunto
                      </label>
                      <label className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          className="h-4 w-4 accent-blue-700"
                          checked={Boolean(newRecurrenceRule.require_same_diagnosis)}
                          onChange={(event) => setNewRecurrenceRule({ ...newRecurrenceRule, require_same_diagnosis: event.target.checked })}
                        />
                        Exigir mesmo diagnóstico
                      </label>
                    </div>
                    {!classificationSupportsDiscount(newRecurrenceRule.classification ?? "reincidencia_tecnica") ? (
                      <p className="text-xs text-slate-500">
                        Este subtipo não anula pontos - a marcação acima não teria efeito no cálculo.
                      </p>
                    ) : null}
                    <div className="flex flex-wrap items-end justify-between gap-3">
                      <div className="grid gap-2">
                        <Label>Prioridade</Label>
                        <Input
                          type="number"
                          className="w-28"
                          value={newRecurrenceRule.priority ?? 100}
                          onChange={(event) => setNewRecurrenceRule({ ...newRecurrenceRule, priority: Number(event.target.value || 0) })}
                        />
                        <p className="text-[11px] text-slate-500">Regras com prioridade menor são conferidas primeiro quando mais de uma bate com a mesma O.S.</p>
                      </div>
                      <Button onClick={() => void createRecurrenceRule()}>Criar regra</Button>
                    </div>
                  </div>
                </div>
              </section>
            </div>

            <div className="grid gap-3 border-t p-5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h4 className="text-sm font-semibold text-slate-950">Regras cadastradas</h4>
                  <p className="text-xs text-slate-500">Edite uma regra por vez, com os mesmos campos usados para criar novas regras.</p>
                </div>
                <Badge className="border-slate-200 bg-slate-50 text-slate-700">{filteredRecurrenceRules.length} regra(s)</Badge>
              </div>

              {filteredRecurrenceRules.map((rule) => (
                <section key={rule.id} className="rounded-2xl border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
                  <div className="grid gap-3 border-b bg-slate-50 px-4 py-3 lg:grid-cols-[1fr_auto] lg:items-center">
                    <div className="min-w-0">
                      <Input
                        value={rule.name}
                        onChange={(event) => setRecurrenceRules(replaceById(recurrenceRules, rule.id, { name: event.target.value }))}
                        className="max-w-xl bg-white font-semibold"
                      />
                      <div className="mt-2 flex flex-wrap gap-2">
                        <Badge className={rule.active ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-slate-50 text-slate-700"}>
                          {rule.active ? "Ativa" : "Inativa"}
                        </Badge>
                        <Badge className="border-blue-200 bg-blue-50 text-blue-700">{recurrenceClassificationLabel(rule.classification)}</Badge>
                        <Badge className={rule.discount_points ? "border-red-200 bg-red-50 text-red-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}>
                          {rule.discount_points ? "Anula O.S original" : "Apenas sinaliza"}
                        </Badge>
                        <Badge className="border-slate-200 bg-white text-slate-700">Janela: {rule.max_days ?? localSettings.recurrence_window_days ?? "30"} dias</Badge>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button variant="default" size="sm" onClick={() => onSaveRecurrenceRule(rule)}>
                        <Save className="h-4 w-4" />
                        Salvar
                      </Button>
                      <Button variant="destructive" size="sm" onClick={() => onDeleteRecurrenceRule(rule)}>
                        <Trash2 className="h-4 w-4" />
                        Remover
                      </Button>
                    </div>
                  </div>
                  <div className="grid gap-3 p-4 xl:grid-cols-[1fr_1fr_240px]">
                    <div className={configSoftCardClass}>
                      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">O.S original</div>
                      <SearchableMultiSelect
                        label="Tipo original"
                        placeholder="Selecionar tipo"
                        options={osTypeOptions}
                        value={rule.original_os_type_pattern ?? rule.os_type_pattern ?? ""}
                        onChange={(value) => setRecurrenceRules(replaceById(recurrenceRules, rule.id, { original_os_type_pattern: value }))}
                      />
                      <SearchableMultiSelect
                        label="Assunto original"
                        placeholder="Selecionar assunto"
                        options={subjectOptions}
                        value={rule.original_os_subject_pattern ?? rule.os_subject_pattern ?? ""}
                        onChange={(value) => setRecurrenceRules(replaceById(recurrenceRules, rule.id, { original_os_subject_pattern: value }))}
                      />
                    </div>
                    <div className={configSoftCardClass}>
                      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">O.S de retorno</div>
                      <SearchableMultiSelect
                        label="Tipo retorno"
                        placeholder="Selecionar tipo"
                        options={osTypeOptions}
                        value={rule.return_os_type_pattern ?? rule.os_type_pattern ?? ""}
                        onChange={(value) => setRecurrenceRules(replaceById(recurrenceRules, rule.id, { return_os_type_pattern: value }))}
                      />
                      <SearchableMultiSelect
                        label="Assunto retorno"
                        placeholder="Selecionar assunto"
                        options={subjectOptions}
                        value={rule.return_os_subject_pattern ?? rule.os_subject_pattern ?? ""}
                        onChange={(value) => setRecurrenceRules(replaceById(recurrenceRules, rule.id, { return_os_subject_pattern: value }))}
                      />
                      <SearchableMultiSelect
                        label="Diagnóstico confirma"
                        placeholder="Selecionar diagnóstico"
                        options={diagnosisOptions}
                        value={rule.return_diagnosis_pattern ?? rule.diagnosis_pattern ?? ""}
                        onChange={(value) => setRecurrenceRules(replaceById(recurrenceRules, rule.id, { return_diagnosis_pattern: value }))}
                      />
                      <SearchableMultiSelect
                        label="Diagnóstico ignora"
                        placeholder="Selecionar diagnóstico"
                        options={diagnosisOptions}
                        value={rule.ignore_diagnosis_pattern ?? ""}
                        onChange={(value) => setRecurrenceRules(replaceById(recurrenceRules, rule.id, { ignore_diagnosis_pattern: value }))}
                      />
                    </div>
                    <div className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
                    <div className="grid gap-2">
                      <Label>Subtipo</Label>
                        <AppCombobox
                          value={rule.classification}
                          onChange={(value) =>
                            setRecurrenceRules(
                              replaceById(recurrenceRules, rule.id, {
                                classification: value as RecurrenceClassificationValue
                              })
                            )
                          }
                          placeholder="Selecionar subtipo"
                          ariaLabel={`Subtipo da regra ${rule.name}`}
                          options={[
                            { value: "reincidencia_tecnica", label: "Reincidência de manutenção" },
                            { value: "garantia", label: "Reincidência após ativação" },
                            { value: "recorrencia_operacional", label: "Reincidência operacional" },
                            { value: "os_nao_reincidente", label: "Não caracteriza reincidência" },
                            { value: "demandas_diferentes", label: "Demandas diferentes" },
                            { value: "nao_identificado", label: "Não identificado" },
                          ]}
                        />
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <div className="grid gap-2">
                          <Label>Janela da regra</Label>
                          <div className="flex items-center gap-2">
                            <Input
                              inputMode="numeric"
                              value={rule.max_days ?? ""}
                              placeholder="Global"
                              onChange={(event) =>
                                setRecurrenceRules(
                                  replaceById(recurrenceRules, rule.id, {
                                    max_days: event.target.value === "" ? null : Number(event.target.value)
                                  })
                                )
                              }
                            />
                            <span className="text-xs text-slate-500">dias</span>
                          </div>
                        </div>
                        <div className="grid gap-2">
                          <Label>Prioridade</Label>
                          <Input
                            type="number"
                            value={rule.priority ?? 100}
                            onChange={(event) =>
                              setRecurrenceRules(replaceById(recurrenceRules, rule.id, { priority: Number(event.target.value || 0) }))
                            }
                          />
                        </div>
                      </div>
                      <label
                        className={cn(
                          "flex items-start gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-3 text-xs leading-snug",
                          classificationSupportsDiscount(rule.classification) ? "text-slate-700" : "text-slate-400"
                        )}
                      >
                        <input
                          type="checkbox"
                          className="mt-0.5 h-4 w-4 shrink-0 accent-blue-700"
                          checked={rule.discount_points}
                          disabled={!classificationSupportsDiscount(rule.classification)}
                          onChange={(event) =>
                            setRecurrenceRules(replaceById(recurrenceRules, rule.id, { discount_points: event.target.checked }))
                          }
                        />
                        <span>
                          {rule.discount_points ? "Anula pontuação da O.S original" : "Apenas sinaliza reincidência"}
                          {!classificationSupportsDiscount(rule.classification) ? " - este subtipo não anula pontos, marcação sem efeito." : ""}
                        </span>
                      </label>
                      <div className="grid grid-cols-2 gap-2">
                        <label className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-700">
                          <input
                            type="checkbox"
                            className="h-4 w-4 shrink-0 accent-blue-700"
                            checked={rule.require_same_subject}
                            onChange={(event) =>
                              setRecurrenceRules(replaceById(recurrenceRules, rule.id, { require_same_subject: event.target.checked }))
                            }
                          />
                          Exigir mesmo assunto
                        </label>
                        <label className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-700">
                          <input
                            type="checkbox"
                            className="h-4 w-4 shrink-0 accent-blue-700"
                            checked={rule.require_same_diagnosis}
                            onChange={(event) =>
                              setRecurrenceRules(replaceById(recurrenceRules, rule.id, { require_same_diagnosis: event.target.checked }))
                            }
                          />
                          Exigir mesmo diagnóstico
                        </label>
                      </div>
                      <label className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-700">
                        <input
                          type="checkbox"
                          className="h-4 w-4 shrink-0 accent-blue-700"
                          checked={rule.active}
                          onChange={(event) => setRecurrenceRules(replaceById(recurrenceRules, rule.id, { active: event.target.checked }))}
                        />
                        {rule.active ? "Regra ativa" : "Regra inativa"}
                      </label>
                    </div>
                  </div>
                </section>
              ))}
              {filteredRecurrenceRules.length === 0 ? (
                <EmptyState
                  title="Nenhuma regra cadastrada"
                  description="Sem regra, o motor usa somente a evidência técnica padrão encontrada nas O.S."
                />
              ) : null}
            </div>
          </section>
          ) : null}

          {configSection === "integration" ? (
          <section className="rounded-[24px] border border-slate-200 bg-white shadow-[0_10px_40px_rgba(15,23,42,0.05)]">
            <div className="panel-header">
              <div>
                <h3 className="panel-title">Integração IXC</h3>
                <p className="panel-subtitle">
                  Controla a sincronização automática de O.S com a API do IXC, sem precisar reiniciar o sistema.
                </p>
              </div>
            </div>
            <div className="grid gap-4 p-5 md:grid-cols-2">
              <div className="grid gap-2">
                <Label>Sincronização automática</Label>
                <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
                  <AppSwitch
                    checked={(localSettings[IXC_SYNC_ENABLED_KEY] ?? "true") === "true"}
                    onCheckedChange={(checked) => {
                      const value = checked ? "true" : "false";
                      setLocalSettings({ ...localSettings, [IXC_SYNC_ENABLED_KEY]: value });
                      void saveSettings({ [IXC_SYNC_ENABLED_KEY]: value });
                    }}
                  />
                  <span className="text-sm text-slate-700">
                    {(localSettings[IXC_SYNC_ENABLED_KEY] ?? "true") === "true" ? "Ligada" : "Desligada"}
                  </span>
                </div>
              </div>
              <div className="grid gap-2">
                <Label>Intervalo entre sincronizações (minutos)</Label>
                <Input
                  inputMode="numeric"
                  value={localSettings[IXC_SYNC_INTERVAL_MINUTES_KEY] ?? ""}
                  onChange={(event) => setLocalSettings({ ...localSettings, [IXC_SYNC_INTERVAL_MINUTES_KEY]: event.target.value })}
                  onBlur={(event) => saveSettings({ [IXC_SYNC_INTERVAL_MINUTES_KEY]: event.target.value })}
                  placeholder="Ex.: 20"
                />
              </div>
              <div className="grid gap-2 md:col-span-2">
                <Label>Recalcular pontuação automaticamente</Label>
                <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
                  <AppSwitch
                    checked={(localSettings[IXC_SYNC_AUTO_RECALCULATE_KEY] ?? "true") === "true"}
                    onCheckedChange={(checked) => {
                      const value = checked ? "true" : "false";
                      setLocalSettings({ ...localSettings, [IXC_SYNC_AUTO_RECALCULATE_KEY]: value });
                      void saveSettings({ [IXC_SYNC_AUTO_RECALCULATE_KEY]: value });
                    }}
                  />
                  <span className="text-sm text-slate-700">
                    {(localSettings[IXC_SYNC_AUTO_RECALCULATE_KEY] ?? "true") === "true"
                      ? "Recalcula o rascunho do mês atual sempre que a sincronização trouxer O.S novas ou atualizadas."
                      : "Desligado - use o botão \"Recalcular pontuação\" manualmente."}
                  </span>
                </div>
                <p className="text-xs text-slate-500">
                  Só afeta o período atual, ainda não pago (rascunho). Um período já pago nunca é alterado
                  automaticamente - para revisar um pago, use "Criar revisão" manualmente.
                </p>
              </div>
            </div>
          </section>
          ) : null}

          {configSection === "advanced" && mode === "advanced" ? (
          <section className="grid gap-4">
              <section className="rounded-[24px] border border-slate-200 bg-white shadow-[0_10px_40px_rgba(15,23,42,0.05)]">
                <div className="panel-header">
                  <div>
                    <h3 className="panel-title">Avançado</h3>
                    <p className="panel-subtitle">
                      Ferramentas técnicas para snapshot, importação, exportação e restauração. A matriz operacional fica nas seções Grupos, Assuntos e Diagnósticos.
                    </p>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2 border-t p-5">
                  <Button onClick={saveSnapshot} disabled={busy}>
                    <Save className="h-4 w-4" />
                    Salvar snapshot
                  </Button>
                  <Button variant="outline" onClick={exportConfig} disabled={busy}>
                    <FileDown className="h-4 w-4" />
                    Exportar JSON
                  </Button>
                  <Button variant="outline" onClick={() => fileRef.current?.click()} disabled={busy}>
                    <FileUp className="h-4 w-4" />
                    Importar JSON
                  </Button>
                  <Button variant="destructive" onClick={resetDefault} disabled={busy}>
                    <RotateCcw className="h-4 w-4" />
                    Restaurar padrão
                  </Button>
                </div>
              </section>
            </section>
          ) : null}

          <AppModal
            open={deleteGroupSelectionOpen}
            onOpenChange={setDeleteGroupSelectionOpen}
            title="Excluir grupos selecionados?"
            description="Assuntos vinculados a cada grupo excluído ficam sem grupo, sem apagar o assunto da base."
            footer={
              <>
                <Button type="button" variant="outline" onClick={() => setDeleteGroupSelectionOpen(false)} disabled={deletingGroupSelection}>
                  Cancelar
                </Button>
                <Button type="button" variant="destructive" onClick={() => void deleteSelectedGroups()} disabled={deletingGroupSelection}>
                  {deletingGroupSelection ? "Excluindo..." : "Excluir grupos"}
                </Button>
              </>
            }
          >
            <div className="text-sm text-slate-600">{selectedVisibleGroups.length} grupo(s) serão excluídos.</div>
          </AppModal>

          <AppModal
            open={pendingDeleteGroup != null}
            onOpenChange={(open) => setPendingDeleteGroupId(open ? pendingDeleteGroupId : null)}
            title="Excluir grupo?"
            description={
              pendingDeleteGroup
                ? `Essa ação pode redistribuir ou soltar os assuntos vinculados ao grupo "${pendingDeleteGroup.name}".`
                : undefined
            }
            footer={
              <>
                <Button type="button" variant="outline" onClick={() => setPendingDeleteGroupId(null)} disabled={deletingGroupId != null}>
                  Cancelar
                </Button>
                <Button
                  type="button"
                  variant="destructive"
                  disabled={!pendingDeleteGroup || deletingGroupId === pendingDeleteGroup.id}
                  onClick={() => {
                    if (!pendingDeleteGroup) return;
                    const linkedSubjects = subjectsByGroup.find((item) => item.group.id === pendingDeleteGroup.id)?.rules.length ?? 0;
                    void deleteGroup(pendingDeleteGroup, linkedSubjects);
                  }}
                >
                  {pendingDeleteGroup && deletingGroupId === pendingDeleteGroup.id ? "Excluindo..." : "Excluir grupo"}
                </Button>
              </>
            }
          >
            {pendingDeleteGroup ? (
              <div className="grid gap-4">
                <div className={configSoftCardClass}>
                  <div className="text-sm font-semibold text-slate-950">{pendingDeleteGroup.name}</div>
                  <div className="mt-1 text-sm text-slate-500">
                    {formatInteger(subjectsByGroup.find((item) => item.group.id === pendingDeleteGroup.id)?.rules.length ?? 0)} assunto(s) vinculado(s),
                    {" "}
                    {formatInteger(subjectsByGroup.find((item) => item.group.id === pendingDeleteGroup.id)?.orders ?? 0)} O.S impactadas e custo estimado de{" "}
                    {formatMoney(subjectsByGroup.find((item) => item.group.id === pendingDeleteGroup.id)?.impact ?? 0)}.
                  </div>
                </div>
                <div className="grid gap-2">
                  <Label>Destino ao arquivar</Label>
                  <AppCombobox
                    value={deleteTargets[pendingDeleteGroup.id] ?? ""}
                    onChange={(value) =>
                      setDeleteTargets((current) => ({
                        ...current,
                        [pendingDeleteGroup.id]: value,
                      }))
                    }
                    placeholder="Remover vínculos e deixar assuntos sem regra"
                    ariaLabel={`Destino ao excluir o grupo ${pendingDeleteGroup.name}`}
                    options={[
                      {
                        value: "",
                        label: "Remover vínculos e deixar assuntos sem regra",
                        description: "Os assuntos permanecem cadastrados, mas sem grupo vinculado.",
                      },
                      ...groups
                        .filter((item) => item.id !== pendingDeleteGroup.id)
                        .map((item) => ({
                          value: String(item.id),
                          label: `Transferir assuntos para ${item.name}`,
                          description: `${formatPoints(item.default_points)} por grupo`,
                        })),
                    ]}
                  />
                </div>
              </div>
            ) : null}
          </AppModal>

          <AppModal
            open={pendingDeleteSubjectRule != null}
            onOpenChange={(open) => setPendingDeleteSubjectRuleId(open ? pendingDeleteSubjectRuleId : null)}
            title="Remover vínculo do assunto?"
            description={
              pendingDeleteSubjectRule
                ? `O assunto "${pendingDeleteSubjectRule.os_subject}" ficará sem grupo vinculado até receber uma nova regra.`
                : undefined
            }
            footer={
              <>
                <Button type="button" variant="outline" onClick={() => setPendingDeleteSubjectRuleId(null)}>
                  Cancelar
                </Button>
                <Button
                  type="button"
                  variant="destructive"
                  onClick={() => {
                    if (!pendingDeleteSubjectRule) return;
                    void deleteSubjectRule(pendingDeleteSubjectRule);
                  }}
                >
                  Remover vínculo
                </Button>
              </>
            }
          >
            <div className="text-sm text-slate-600">
              Isso remove o vínculo atual do assunto com o grupo de pontuação, sem apagar o assunto da base.
            </div>
          </AppModal>

          <AppModal
            open={deleteSubjectSelectionOpen}
            onOpenChange={setDeleteSubjectSelectionOpen}
            title="Remover assuntos selecionados?"
            description="Cada assunto marcado perde o vínculo com o grupo de pontuação, sem apagar o assunto da base."
            footer={
              <>
                <Button type="button" variant="outline" onClick={() => setDeleteSubjectSelectionOpen(false)} disabled={deletingSubjectSelection}>
                  Cancelar
                </Button>
                <Button type="button" variant="destructive" onClick={() => void deleteSelectedSubjectRules()} disabled={deletingSubjectSelection}>
                  {deletingSubjectSelection ? "Removendo..." : "Remover vínculos"}
                </Button>
              </>
            }
          >
            <div className="text-sm text-slate-600">{selectedVisibleSubjectRules.length} assunto(s) perderão o vínculo com o grupo atual.</div>
          </AppModal>

          <AppDrawer
            open={currentEditingSubject != null}
            onOpenChange={(open) => setEditingSubjectId(open ? editingSubjectId : null)}
            title={currentEditingSubject ? `Editar ${currentEditingSubject.os_subject}` : "Editar assunto"}
            description="Ajuste o vínculo de grupo, pontos e valor por ponto deste assunto."
          >
            {currentEditingSubject ? (
              (() => {
                const selectedGroup = groups.find((group) => group.id === currentEditingSubject.group_id) ?? null;
                const stats = periodRuleStats(currentEditingSubject);
                const pointValuePlaceholder =
                  selectedGroup?.point_value_override != null
                    ? `Grupo ${formatMoney(selectedGroup.point_value_override)}`
                    : `Global ${globalPointValueLabel}`;
                return (
                  <>
                    <div className="grid gap-4 md:grid-cols-2">
                      <div className="grid gap-2 md:col-span-2">
                        <Label>Tipo Geral</Label>
                        <AppCombobox
                          value={currentEditingSubject.os_type}
                          onChange={(value) => setSubjectRules(replaceById(subjectRules, currentEditingSubject.id, { os_type: value }))}
                          placeholder="Selecionar Tipo Geral"
                          ariaLabel={`Tipo Geral do assunto ${currentEditingSubject.os_subject}`}
                          options={osTypeOptions.map((type) => ({ value: type, label: type }))}
                        />
                        {!currentEditingSubject.os_type.trim() ? <p className="text-xs text-red-600">Tipo Geral é obrigatório.</p> : null}
                      </div>
                      <div className="grid gap-2 md:col-span-2">
                        <Label>Grupo vinculado</Label>
                        <AppCombobox
                          value={String(currentEditingSubject.group_id)}
                          onChange={(value) => setSubjectRules(replaceById(subjectRules, currentEditingSubject.id, { group_id: Number(value) }))}
                          placeholder="Selecionar grupo"
                          ariaLabel={`Grupo vinculado ao assunto ${currentEditingSubject.os_subject}`}
                          options={activeGroups.map((group) => ({
                            value: String(group.id),
                            label: `${group.name} (${formatPoints(group.default_points)})`,
                            description: group.point_value_override != null ? `R$/ponto ${formatMoney(group.point_value_override)}` : `Usa valor global ${globalPointValueLabel}`,
                          }))}
                        />
                        {!selectedGroup ? <Badge className="border-amber-200 bg-amber-50 text-amber-800">Sem grupo</Badge> : null}
                      </div>
                      <div className="grid gap-2">
                        <Label>Pontos</Label>
                        <AppInput
                          type="number"
                          value={currentEditingSubject.custom_points ?? ""}
                          disabled={currentEditingSubject.use_group_default}
                          placeholder={formatPoints(currentEditingSubject.effective_points)}
                          onChange={(event) =>
                            setSubjectRules(
                              replaceById(subjectRules, currentEditingSubject.id, {
                                custom_points: event.target.value === "" ? null : Number(event.target.value),
                              })
                            )
                          }
                        />
                        <label className="flex items-center gap-2 text-xs text-slate-600">
                          <input
                            type="checkbox"
                            className="h-4 w-4 accent-blue-700"
                            checked={currentEditingSubject.use_group_default}
                            onChange={(event) =>
                              setSubjectRules(replaceById(subjectRules, currentEditingSubject.id, { use_group_default: event.target.checked }))
                            }
                          />
                          Usar pontuação padrão do grupo
                        </label>
                      </div>
                      <div className="grid gap-2">
                        <Label>R$/ponto</Label>
                        <AppInput
                          type="number"
                          step="0.01"
                          value={currentEditingSubject.point_value_override ?? ""}
                          placeholder={pointValuePlaceholder}
                          onChange={(event) =>
                            setSubjectRules(
                              replaceById(subjectRules, currentEditingSubject.id, {
                                point_value_override: event.target.value === "" ? null : Number(event.target.value),
                              })
                            )
                          }
                        />
                      </div>
                      <div className="flex items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-slate-50/70 p-4 md:col-span-2">
                        <div>
                          <div className="text-sm font-medium text-slate-900">Pontuar assunto</div>
                          <div className="text-xs text-slate-500">Desligado remove o assunto da pontuação sem apagar o vínculo.</div>
                        </div>
                        <AppSwitch
                          checked={currentEditingSubject.active}
                          onCheckedChange={(checked) => setSubjectRules(replaceById(subjectRules, currentEditingSubject.id, { active: checked }))}
                        />
                      </div>
                    </div>
                    <div className={configCardClass}>
                      <div className="flex flex-wrap gap-2">
                        <StatusBadge tone="success">{formatInteger(stats.orders)} O.S impactadas</StatusBadge>
                        <StatusBadge tone="success">{formatMoney(stats.impact)}</StatusBadge>
                      </div>
                    </div>
                    <div className="flex flex-wrap justify-end gap-2">
                      <Button type="button" variant="outline" onClick={() => setEditingSubjectId(null)}>
                        Cancelar
                      </Button>
                      <Button type="button" onClick={() => void saveSubjectRule(currentEditingSubject)} disabled={savingSubjectId === currentEditingSubject.id}>
                        <Save className="h-4 w-4" />
                        {savingSubjectId === currentEditingSubject.id ? "Salvando..." : "Salvar assunto"}
                      </Button>
                    </div>
                  </>
                );
              })()
            ) : null}
          </AppDrawer>

          <AppDrawer
            open={currentEditingGroup != null}
            onOpenChange={(open) => setEditingGroupId(open ? editingGroupId : null)}
            title={currentEditingGroup ? `Editar ${currentEditingGroup.name}` : "Editar grupo"}
            description="Ajuste o grupo sem poluir a tabela. Os dados continuam respeitando a mesma API e regras atuais."
          >
            {currentEditingGroup ? (
              <>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="grid gap-2">
                    <Label>Nome do grupo</Label>
                    <AppInput
                      value={currentEditingGroup.name}
                      onChange={(event) => updateGroupField(currentEditingGroup.id, { name: event.target.value })}
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label>Status</Label>
                    <AppSwitch
                      checked={currentEditingGroup.active}
                      onCheckedChange={(checked) => updateGroupField(currentEditingGroup.id, { active: checked })}
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label>Pontos do grupo</Label>
                    <AppInput
                      type="number"
                      value={currentEditingGroup.default_points}
                      onChange={(event) => updateGroupField(currentEditingGroup.id, { default_points: Number(event.target.value) })}
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label>R$/Ponto</Label>
                    <AppInput
                      type="number"
                      step="0.01"
                      value={currentEditingGroup.point_value_override ?? ""}
                      placeholder={`Global ${globalPointValueLabel}`}
                      onChange={(event) =>
                        updateGroupField(currentEditingGroup.id, {
                          point_value_override: event.target.value === "" ? null : Number(event.target.value),
                        })
                      }
                    />
                  </div>
                </div>
                {/*
                  "Regra ao arquivar" (deleteTargets) saiu daqui e da linha da tabela - só faz
                  sentido no momento da exclusão, e já existe no modal de confirmação de exclusão.
                  Mostrar em 3 lugares ao mesmo tempo (linha, drawer, modal) era duplicação sem
                  necessidade - achado da mesma revisão que já corrigimos em Reincidência.
                */}
                <div className={configCardClass}>
                  <div className="flex flex-wrap gap-2">
                    <StatusBadge tone="success">
                      {formatInteger(subjectsByGroup.find((item) => item.group.id === currentEditingGroup.id)?.rules.length ?? 0)} assuntos
                    </StatusBadge>
                    <StatusBadge tone="info">
                      {formatInteger(subjectsByGroup.find((item) => item.group.id === currentEditingGroup.id)?.orders ?? 0)} O.S
                    </StatusBadge>
                    <StatusBadge tone="success">
                      {formatMoney(subjectsByGroup.find((item) => item.group.id === currentEditingGroup.id)?.impact ?? 0)}
                    </StatusBadge>
                  </div>
                </div>
                <div className="flex flex-wrap justify-end gap-2">
                  <Button type="button" variant="outline" onClick={() => restoreGroup(currentEditingGroup.id)}>
                    Cancelar alterações
                  </Button>
                  <Button type="button" onClick={() => void saveGroup(currentEditingGroup.id)} disabled={savingGroupId === currentEditingGroup.id}>
                    <Save className="h-4 w-4" />
                    {savingGroupId === currentEditingGroup.id ? "Salvando..." : "Salvar grupo"}
                  </Button>
                </div>
              </>
            ) : null}
          </AppDrawer>
        </div>
    </section>
  );
}




