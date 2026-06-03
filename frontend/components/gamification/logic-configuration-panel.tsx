"use client";

import { Check, ChevronDown, FileDown, FileUp, RefreshCw, RotateCcw, Save, Search, Settings2, SlidersHorizontal, Trash2, X } from "lucide-react";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";

import { GovernanceRulesPanel } from "@/components/gamification/governance-rules-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatInteger, formatMoney, formatPoints } from "@/lib/format";
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
type ConfigSection = "governance" | "categories" | "groups" | "subjects" | "diagnoses" | "recurrence" | "sla" | "advanced";
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
  { value: "advanced", label: "Avançado", help: "JSON, histórico e restauração." }
];

function replaceById<T extends { id: number }>(items: T[], id: number, patch: Partial<T>) {
  return items.map((item) => (item.id === id ? { ...item, ...patch } : item));
}

function actionLabel(action: DiagnosisActionType | null) {
  if (action === "subtract_points") return "Subtrair pontos";
  if (action === "cancel_points") return "Anular pontos";
  if (action === "requires_review") return "Revisão manual";
  if (action === "force_points") return "Forçar pontos";
  if (action === "no_penalty") return "Sem anulação";
  return "Sem regra";
}

function recurrenceClassificationLabel(value: string) {
  if (value === "recorrencia_operacional") return "Reincidência operacional";
  if (value === "reincidencia_tecnica") return "Reincidência de manutenção";
  if (value === "garantia") return "Reincidência após ativação";
  if (value === "os_nao_reincidente") return "O.S não reincidente";
  if (value === "demandas_diferentes") return "Demandas diferentes";
  return "Não identificado";
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
        className="flex min-h-10 w-full items-center justify-between gap-2 rounded-md border border-input bg-white px-3 py-2 text-left text-sm"
        onClick={() => setOpen((value) => !value)}
      >
        <span className={selected.length ? "line-clamp-1 text-slate-950" : "text-slate-500"}>
          {selected.length ? `${selected.length} selecionado(s)` : placeholder}
        </span>
        <ChevronDown className="h-4 w-4 shrink-0 text-slate-500" />
      </button>
      {selected.length ? (
        <div className="flex flex-wrap gap-1">
          {selected.slice(0, 4).map((item) => (
            <button
              key={item}
              type="button"
              className="inline-flex max-w-full items-center gap-1 rounded-md border bg-slate-50 px-2 py-1 text-[11px] text-slate-700"
              onClick={() => toggleOption(item)}
              title={item}
            >
              <span className="max-w-40 truncate">{item}</span>
              <X className="h-3 w-3" />
            </button>
          ))}
          {selected.length > 4 ? <span className="rounded-md bg-slate-100 px-2 py-1 text-[11px] text-slate-500">+{selected.length - 4}</span> : null}
        </div>
      ) : null}
      {open ? (
        <div className="rounded-md border bg-white p-2 shadow-sm">
          <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Pesquisar..." className="mb-2 h-8 text-xs" />
          <div className="max-h-56 overflow-auto">
            {filteredOptions.map((option) => {
              const checked = selected.includes(option.value);
              return (
                <button
                  key={option.value}
                  type="button"
                  className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-slate-50"
                  onClick={() => toggleOption(option.value)}
                  title={option.meta ? `${option.label} - ${option.meta}` : option.label}
                >
                  <span className={`flex h-4 w-4 items-center justify-center rounded border ${checked ? "border-teal-700 bg-teal-700 text-white" : "border-slate-300"}`}>
                    {checked ? <Check className="h-3 w-3" /> : null}
                  </span>
                  <span className="min-w-0">
                    <span className="line-clamp-2 font-medium text-slate-800">{option.label}</span>
                    {option.meta ? <span className="line-clamp-1 text-[11px] text-slate-500">{option.meta}</span> : null}
                  </span>
                </button>
              );
            })}
            {filteredOptions.length === 0 ? <div className="px-2 py-4 text-center text-xs text-slate-500">Nenhuma opção encontrada.</div> : null}
          </div>
          <div className="mt-2 flex items-center justify-between border-t pt-2">
            <Button type="button" variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => onChange(null)}>
              Limpar
            </Button>
            <Button type="button" variant="outline" size="sm" className="h-7 px-2 text-xs" onClick={() => setOpen(false)}>
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
  const [newGroupDraft, setNewGroupDraft] = useState({ name: "", default_points: 0 });
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

  async function deleteGroup(group: ScoringGroup, linkedSubjects: number) {
    const replacementGroupId = deleteTargets[group.id] ? Number(deleteTargets[group.id]) : null;
    const replacementGroup = groups.find((item) => item.id === replacementGroupId) ?? null;
    const confirmation = replacementGroup
      ? `Excluir o grupo "${group.name}" e mover ${linkedSubjects} assunto(s) para "${replacementGroup.name}"?`
      : linkedSubjects > 0
        ? `Este grupo possui ${linkedSubjects} assunto(s) vinculado(s). Deseja excluir o grupo e remover estes vínculos?`
        : `Excluir o grupo "${group.name}"?`;
    if (!window.confirm(confirmation)) return;
    await onDeleteGroup(group, replacementGroup?.id ?? null);
    setDeleteTargets((current) => {
      const next = { ...current };
      delete next[group.id];
      return next;
    });
  }

  async function deleteSubjectRule(rule: ScoringSubjectRule) {
    if (!window.confirm(`Remover o vínculo do assunto "${rule.os_subject}"?`)) return;
    await onDeleteSubjectRule(rule);
  }

  async function saveSubjectRule(rule: ScoringSubjectRule) {
    const latestRule = subjectRules.find((item) => item.id === rule.id) ?? rule;
    await onSaveSubjectRule(latestRule);
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
      <div className="rounded-[24px] border border-slate-200 bg-white shadow-[0_10px_40px_rgba(15,23,42,0.05)]">
        <div className="panel-header rounded-t-[24px] bg-gradient-to-r from-slate-50 via-white to-white">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-700">
              <Settings2 className="h-5 w-5" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="panel-title">Configuração da gamificação</h2>
                <Badge className={mode === "simple" ? "border-teal-200 bg-teal-50 text-teal-700" : "border-slate-200 bg-slate-100 text-slate-700"}>
                  {mode === "simple" ? "Modo simples" : "Modo avançado"}
                </Badge>
              </div>
              <p className="panel-subtitle">
                {mode === "simple"
                  ? "Use este modo para governança operacional: valor do ponto, grupos, assuntos e diagnósticos principais."
                  : "Use este modo para configurações técnicas: SLA, reincidência, multiplicadores, JSON e restauração."}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap rounded-2xl border border-slate-200 bg-white p-1 shadow-sm">
            <Button variant={mode === "simple" ? "default" : "ghost"} onClick={() => setMode("simple")} className="h-9">
              Simples
            </Button>
            <Button variant={mode === "advanced" ? "default" : "ghost"} onClick={() => setMode("advanced")} className="h-9">
              <SlidersHorizontal className="h-4 w-4" />
              Avançado
            </Button>
          </div>
        </div>

        <div className="grid gap-3 border-t p-5">
          <div className="grid gap-2">
            <Label htmlFor="logic-search">Buscar na configuração</Label>
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
              <Input
                id="logic-search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className="pl-9"
                placeholder="Buscar grupo, assunto, diagnóstico, SLA ou reincidência"
              />
            </div>
          </div>
          <input ref={fileRef} type="file" accept="application/json,.json" className="hidden" onChange={(event) => importConfig(event.target.files?.[0] ?? null)} />
        </div>

        {error ? <div className="mx-5 mb-5 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}
        {message ? <div className="mx-5 mb-5 rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</div> : null}
        {busy ? (
          <div className="mx-5 mb-5 flex items-center gap-2 rounded-md border bg-slate-50 px-4 py-3 text-sm text-slate-600">
            <RefreshCw className="h-4 w-4 animate-spin" />
            Atualizando configuração permanente...
          </div>
        ) : null}

        <div className="grid gap-3 border-t p-5 sm:grid-cols-2 xl:grid-cols-6">
          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
            <div className="text-xs font-medium uppercase text-slate-500">Grupos ativos</div>
            <div className="mt-1 text-lg font-semibold">{formatInteger(groups.filter((group) => group.active).length)}</div>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
            <div className="text-xs font-medium uppercase text-slate-500">Assuntos configurados</div>
            <div className="mt-1 text-lg font-semibold">{formatInteger(subjectRules.length)}</div>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
            <div className="text-xs font-medium uppercase text-slate-500">Diagnósticos encontrados</div>
            <div className="mt-1 text-lg font-semibold">{formatInteger(importedDiagnoses.length)}</div>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
            <div className="text-xs font-medium uppercase text-slate-500">Diagnósticos com regra</div>
            <div className="mt-1 text-lg font-semibold text-emerald-700">{formatInteger(diagnosisConfiguredCount)}</div>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
            <div className="text-xs font-medium uppercase text-slate-500">Diagnósticos sem regra</div>
            <div className="mt-1 text-lg font-semibold text-amber-700">{formatInteger(diagnosisUnconfiguredCount)}</div>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
            <div className="text-xs font-medium uppercase text-slate-500">Valor a ser pago por ponto</div>
            <div className="mt-1 text-lg font-semibold">{pointValue ? formatMoney(Number(pointValue.replace(",", "."))) : "Não configurado"}</div>
          </div>
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
                    <Badge className="border-teal-200 bg-teal-50 text-teal-700">{formatInteger(row.orders)} O.S</Badge>
                  </div>
                </div>
              ))}
            </div>
            <Table>
              <TableHeader>
                <TableRow>
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
                    <TableCell className="font-medium text-teal-700">{formatMoney(row.impact)}</TableCell>
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
                          className="w-fit text-xs font-semibold text-teal-700 hover:text-teal-900"
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
                                  <div className="text-sm font-semibold text-teal-700">{formatMoney(stats.impact)}</div>
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
            <div className="grid gap-3 border-b bg-slate-50 px-5 py-4 lg:grid-cols-[1fr_160px_auto] lg:items-end">
              <div className="grid gap-1">
                <Label>Novo grupo de pontuação</Label>
                <Input
                  value={newGroupDraft.name}
                  placeholder="Ex.: Manutenção Especial"
                  onChange={(event) => setNewGroupDraft((current) => ({ ...current, name: event.target.value }))}
                />
              </div>
              <div className="grid gap-1">
                <Label>Pontos padrão</Label>
                <Input
                  type="number"
                  value={newGroupDraft.default_points}
                  onChange={(event) => setNewGroupDraft((current) => ({ ...current, default_points: Number(event.target.value) }))}
                />
              </div>
              <Button type="button" onClick={() => void createGroup()} disabled={busy}>
                Criar grupo
              </Button>
            </div>
            <div className="overflow-hidden rounded-b-[24px] border-t border-slate-200">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Grupo</TableHead>
                  <TableHead>Pontos do grupo</TableHead>
                  <TableHead>R$/ponto</TableHead>
                  <TableHead>Assuntos vinculados</TableHead>
                  <TableHead>Ativo</TableHead>
                  <TableHead>Ao arquivar o grupo</TableHead>
                  <TableHead>Ação</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {subjectsByGroup.map(({ group, rules, orders, impact }) => (
                  <TableRow key={group.id}>
                    <TableCell className="min-w-72 font-medium">{group.name}</TableCell>
                    <TableCell className="w-40">
                      <Input
                        type="number"
                        value={group.default_points}
                        onChange={(event) => setGroups(replaceById(groups, group.id, { default_points: Number(event.target.value) }))}
                      />
                    </TableCell>
                    <TableCell className="w-44">
                      <Input
                        type="number"
                        step="0.01"
                        value={group.point_value_override ?? ""}
                        placeholder={`Global ${globalPointValueLabel}`}
                        onChange={(event) =>
                          setGroups(
                            replaceById(groups, group.id, {
                              point_value_override: event.target.value === "" ? null : Number(event.target.value)
                            })
                          )
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-2">
                        <Badge className="border-slate-200 bg-slate-50 text-slate-700">{formatInteger(rules.length)} assuntos</Badge>
                        <Badge className="border-teal-200 bg-teal-50 text-teal-700">{formatInteger(orders)} O.S</Badge>
                        <Badge className="border-emerald-200 bg-emerald-50 text-emerald-700">{formatMoney(impact)}</Badge>
                      </div>
                    </TableCell>
                    <TableCell>
                      <input
                        type="checkbox"
                        className="h-4 w-4 accent-teal-700"
                        checked={group.active}
                        onChange={(event) => setGroups(replaceById(groups, group.id, { active: event.target.checked }))}
                      />
                    </TableCell>
                    <TableCell className="min-w-72">
                      <select
                        className="h-9 w-full rounded-md border border-input bg-white px-3 text-sm"
                        value={deleteTargets[group.id] ?? ""}
                        onChange={(event) =>
                          setDeleteTargets((current) => ({
                            ...current,
                            [group.id]: event.target.value
                          }))
                        }
                      >
                        <option value="">Remover vínculos e deixar assuntos sem regra</option>
                        {groups
                          .filter((item) => item.id !== group.id)
                          .map((item) => (
                            <option key={item.id} value={item.id}>
                              Mover assuntos para {item.name}
                            </option>
                          ))}
                      </select>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-2">
                        <Button variant="default" size="sm" onClick={() => onSaveGroup(group)}>
                          <Save className="h-4 w-4" />
                          Salvar
                        </Button>
                        <Button variant="destructive" size="sm" onClick={() => void deleteGroup(group, rules.length)}>
                          <Trash2 className="h-4 w-4" />
                          Excluir
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            </div>
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
            <div className="flex flex-wrap gap-2 border-b bg-slate-50 px-5 py-3">
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
                <select
                  id="subject-group-filter"
                  className="h-9 w-full rounded-md border border-input bg-white px-3 text-sm"
                  value={subjectGroupFilter}
                  onChange={(event) => setSubjectGroupFilter(event.target.value)}
                >
                  <option value="all">Todos os grupos</option>
                  {activeGroups.map((group) => (
                    <option key={group.id} value={group.id}>
                      {group.name}
                    </option>
                  ))}
                </select>
                {subjectGroupFilter !== "all" ? (
                  <Button type="button" variant="outline" size="sm" onClick={() => setSubjectGroupFilter("all")}>
                    Limpar grupo
                  </Button>
                ) : null}
              </div>
              <div className="ml-auto text-xs text-slate-500">{formatInteger(filteredSubjectRules.length)} assunto(s) no filtro</div>
            </div>
            <div className="overflow-hidden rounded-b-[24px] border-t border-slate-200">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Assunto</TableHead>
                  <TableHead>Tipo Geral</TableHead>
                  <TableHead>Grupo vinculado</TableHead>
                  <TableHead>Pontos</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>R$/ponto</TableHead>
                  <TableHead>O.S impactadas</TableHead>
                  <TableHead>Ação</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredSubjectRules.slice(0, 80).map((rule) => {
                  const selectedGroup = groups.find((group) => group.id === rule.group_id) ?? null;
                  const stats = periodRuleStats(rule);
                  const pointValuePlaceholder =
                    selectedGroup?.point_value_override != null
                      ? `Grupo ${formatMoney(selectedGroup.point_value_override)}`
                      : `Global ${globalPointValueLabel}`;
                  const status = subjectStatus(rule, selectedGroup);

                  return (
                  <TableRow key={rule.id}>
                    <TableCell className="min-w-80">
                      <div className="font-medium">{rule.os_subject}</div>
                      <div className="text-xs text-slate-500">Tipo Geral: {rule.os_type}</div>
                    </TableCell>
                    <TableCell className="min-w-56">
                      <Input
                        list="logic-os-type-options"
                        value={rule.os_type}
                        onChange={(event) =>
                          setSubjectRules(
                            replaceById(subjectRules, rule.id, {
                              os_type: event.target.value
                            })
                          )
                        }
                      />
                      <datalist id="logic-os-type-options">
                        {osTypeOptions.map((type) => (
                          <option key={type} value={type} />
                        ))}
                      </datalist>
                    </TableCell>
                    <TableCell className="min-w-72">
                      <select
                        className="h-9 w-full rounded-md border border-input bg-white px-3 text-sm"
                        value={rule.group_id}
                        onChange={(event) => setSubjectRules(replaceById(subjectRules, rule.id, { group_id: Number(event.target.value) }))}
                      >
                        {activeGroups.map((group) => (
                          <option key={group.id} value={group.id}>
                            {group.name} ({formatPoints(group.default_points)})
                          </option>
                        ))}
                      </select>
                      {!selectedGroup ? <Badge className="mt-2 border-amber-200 bg-amber-50 text-amber-800">Sem grupo</Badge> : null}
                    </TableCell>
                    <TableCell className="min-w-44">
                      <div className="flex items-center gap-2">
                        <Input
                          type="number"
                          value={rule.custom_points ?? ""}
                          disabled={rule.use_group_default}
                          placeholder={formatPoints(rule.effective_points)}
                          onChange={(event) =>
                            setSubjectRules(
                              replaceById(subjectRules, rule.id, {
                                custom_points: event.target.value === "" ? null : Number(event.target.value)
                              })
                            )
                          }
                        />
                        <label className="flex items-center gap-1 text-xs text-slate-600" title="Usar pontuação padrão do grupo">
                          <input
                            type="checkbox"
                            className="h-4 w-4 accent-teal-700"
                            checked={rule.use_group_default}
                            onChange={(event) =>
                              setSubjectRules(replaceById(subjectRules, rule.id, { use_group_default: event.target.checked }))
                            }
                          />
                          Grupo
                        </label>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-2">
                        <Badge className={subjectStatusClass(status)}>{subjectStatusLabel(status)}</Badge>
                        <Badge className={rule.active ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-slate-50 text-slate-700"}>
                          {rule.active ? "Ativo" : "Inativo"}
                        </Badge>
                      </div>
                      <label className="mt-2 flex items-center gap-2 text-xs text-slate-600">
                        <input
                          type="checkbox"
                          className="h-4 w-4 accent-teal-700"
                          checked={rule.active}
                          onChange={(event) => setSubjectRules(replaceById(subjectRules, rule.id, { active: event.target.checked }))}
                        />
                        Pontuar assunto
                      </label>
                    </TableCell>
                    <TableCell className="w-44">
                      <Input
                        type="number"
                        step="0.01"
                        value={rule.point_value_override ?? ""}
                        placeholder={pointValuePlaceholder}
                        onChange={(event) =>
                          setSubjectRules(
                            replaceById(subjectRules, rule.id, {
                              point_value_override: event.target.value === "" ? null : Number(event.target.value)
                            })
                          )
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <div className="font-medium">{formatInteger(stats.orders)}</div>
                      <div className="text-xs font-medium text-teal-700">{formatMoney(stats.impact)}</div>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          variant="default"
                          size="sm"
                          onClick={() => void saveSubjectRule(rule)}
                        >
                          <Save className="h-4 w-4" />
                          Salvar
                        </Button>
                        <Button variant="destructive" size="sm" onClick={() => void deleteSubjectRule(rule)}>
                          <Trash2 className="h-4 w-4" />
                          Remover
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                  );
                })}
              </TableBody>
            </Table>
            </div>
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
            <div className="flex flex-wrap gap-2 border-b bg-slate-50 px-5 py-3">
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
              <div className="ml-auto text-xs text-slate-500">{formatInteger(diagnosisRows.length)} diagnóstico(s) no filtro</div>
            </div>
            <div className="overflow-hidden rounded-b-[24px] border-t border-slate-200">
            <Table>
              <TableHeader>
                <TableRow>
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
                {diagnosisRows.slice(0, 80).map((item) => {
                  const draft = diagnosisDraft(item);
                  const value = draft.action_type === "force_points" ? draft.force_points_value ?? "" : draft.penalty_points;
                  return (
                    <TableRow key={item.diagnosis_name}>
                      <TableCell className="min-w-64 font-medium">{item.diagnosis_name}</TableCell>
                      <TableCell>{formatInteger(item.service_orders_count)}</TableCell>
                      <TableCell className="min-w-56">
                        <select
                          className="h-9 w-full rounded-md border border-input bg-white px-3 text-sm"
                          value={draft.action_type}
                          onChange={(event) => updateDiagnosisDraft(item, { action_type: event.target.value as DiagnosisActionType })}
                        >
                          <option value="subtract_points">Subtrair pontos</option>
                          <option value="cancel_points">Anular pontos</option>
                          <option value="no_penalty">Sem anulação</option>
                          <option value="requires_review">Revisão manual</option>
                          <option value="force_points">Forçar pontos</option>
                        </select>
                        <div className="mt-1 text-xs text-slate-500">{actionLabel(draft.action_type)}</div>
                      </TableCell>
                      <TableCell className="w-36">
                        <Input
                          type="number"
                          value={value}
                          onChange={(event) =>
                            updateDiagnosisDraft(
                              item,
                              draft.action_type === "force_points"
                                ? { force_points_value: event.target.value === "" ? null : Number(event.target.value) }
                                : { penalty_points: Number(event.target.value || 0) }
                            )
                          }
                        />
                      </TableCell>
                      <TableCell className="font-medium text-teal-700">{formatMoney(item.estimated_impact)}</TableCell>
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
            </div>
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
              <TableHeader>
                <TableRow>
                  <TableHead>Regra</TableHead>
                  <TableHead>Regra ativa</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Valor</TableHead>
                  <TableHead>Ação</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredSlaRules.map((rule) => (
                  <TableRow key={rule.id}>
                    <TableCell className="min-w-56 font-medium">{rule.name}</TableCell>
                    <TableCell>
                      <input
                        type="checkbox"
                        className="h-4 w-4 accent-teal-700"
                        checked={rule.active}
                        onChange={(event) => setSlaRules(replaceById(slaRules, rule.id, { active: event.target.checked }))}
                      />
                    </TableCell>
                    <TableCell className="min-w-64">
                      <select
                        className="h-9 w-full rounded-md border border-input bg-white px-3 text-sm"
                        value={rule.penalty_type}
                        onChange={(event) => setSlaRules(replaceById(slaRules, rule.id, { penalty_type: event.target.value as SlaPenaltyType }))}
                      >
                        <option value="none">Sem anulação</option>
                        <option value="subtract_points">Subtrair pontos</option>
                        <option value="percentage_reduction">Redução percentual</option>
                        <option value="cancel_points">Anular pontos</option>
                        <option value="requires_review">Revisão manual</option>
                      </select>
                    </TableCell>
                    <TableCell className="w-40">
                      <Input
                        type="number"
                        value={rule.penalty_value}
                        onChange={(event) => setSlaRules(replaceById(slaRules, rule.id, { penalty_value: Number(event.target.value) }))}
                      />
                    </TableCell>
                    <TableCell>
                      <Button variant="default" size="sm" onClick={() => onSaveSlaRule(rule)}>
                        <Save className="h-4 w-4" />
                        Salvar
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
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
                  <TableHeader>
                    <TableRow>
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
                            value={rule.min_sla}
                            onChange={(event) => setHealthRules(replaceById(healthRules, rule.id, { min_sla: Number(event.target.value || 0) }))}
                          />
                        </TableCell>
                        <TableCell className="w-28">
                          <Input
                            type="number"
                            value={rule.max_recurrence_rate}
                            onChange={(event) =>
                              setHealthRules(replaceById(healthRules, rule.id, { max_recurrence_rate: Number(event.target.value || 0) }))
                            }
                          />
                        </TableCell>
                        <TableCell className="w-32">
                          <Input
                            type="number"
                            step="0.05"
                            value={rule.multiplier}
                            onChange={(event) => setHealthRules(replaceById(healthRules, rule.id, { multiplier: Number(event.target.value || 0) }))}
                          />
                        </TableCell>
                        <TableCell>
                          <Badge className={rule.active ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-slate-50 text-slate-700"}>
                            {rule.active ? "Ativo" : "Inativo"}
                          </Badge>
                          <label className="mt-2 flex items-center gap-2 text-xs text-slate-600">
                            <input
                              type="checkbox"
                              className="h-4 w-4 accent-teal-700"
                              checked={rule.active}
                              onChange={(event) => setHealthRules(replaceById(healthRules, rule.id, { active: event.target.checked }))}
                            />
                            Usar faixa
                          </label>
                        </TableCell>
                        <TableCell>
                          <Button variant="default" size="sm" onClick={() => onSaveHealthRule(rule)}>
                            <Save className="h-4 w-4" />
                            Salvar
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
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
                  <div className="mb-2 flex h-6 w-6 items-center justify-center rounded-full bg-teal-700 text-xs font-semibold text-white">{step}</div>
                  <div className="text-xs font-semibold text-slate-700">{label}</div>
                </div>
              ))}
            </div>

            <div className="grid gap-4 border-b p-5 xl:grid-cols-[1fr_1.4fr]">
              <section className="rounded-2xl border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
                <div className="border-b bg-slate-50 px-4 py-3">
                  <h4 className="text-sm font-semibold text-slate-950">Configuração geral</h4>
                  <p className="text-xs text-slate-500">Define a janela, o vínculo do cliente e o comportamento padrão.</p>
                </div>
                <div className="grid gap-4 p-4 md:grid-cols-2">
                  <div className="grid gap-2">
                    <Label>Janela de reincidência (dias)</Label>
                    <Input
                      inputMode="numeric"
                      value={localSettings.recurrence_window_days ?? ""}
                      onChange={(event) => setLocalSettings({ ...localSettings, recurrence_window_days: event.target.value })}
                      onBlur={(event) => saveSettings({ recurrence_window_days: event.target.value })}
                      placeholder="Ex.: 30"
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label>Ação padrão</Label>
                    <select
                      className="h-10 rounded-md border border-input bg-white px-3 text-sm"
                      value={localSettings.recurrence_action ?? ""}
                      onChange={(event) => {
                        setLocalSettings({ ...localSettings, recurrence_action: event.target.value });
                        saveSettings({ recurrence_action: event.target.value });
                      }}
                    >
                      <option value="">Usar backend</option>
                      <option value="no_penalty">Apenas sinalizar</option>
                      <option value="annul_original">Anular pontuação da O.S original</option>
                      <option value="requires_review">Enviar para revisão manual</option>
                      <option value="subtract_original">Anular pontos fixos da O.S original</option>
                    </select>
                  </div>
                  <div className="grid gap-2">
                    <Label>Pontos fixos, se usar essa ação</Label>
                    <Input
                      inputMode="decimal"
                      value={localSettings.recurrence_penalty_points ?? ""}
                      onChange={(event) => setLocalSettings({ ...localSettings, recurrence_penalty_points: event.target.value })}
                      onBlur={(event) => saveSettings({ recurrence_penalty_points: event.target.value })}
                      placeholder="Ex.: 10"
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label>Campos de vínculo</Label>
                    <div className="grid grid-cols-2 gap-2 rounded-md border bg-white p-2 text-xs">
                      {[
                        ["login", "Login"],
                        ["contract", "Contrato"],
                        ["cliente", "Cliente"],
                        ["cpf_cnpj", "CPF/CNPJ"]
                      ].map(([field, label]) => (
                        <label key={field} className="flex items-center gap-2">
                          <input
                            type="checkbox"
                            className="h-4 w-4 accent-teal-700"
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
                      <select
                        className="h-10 rounded-md border border-input bg-white px-3 text-sm"
                        value={newRecurrenceRule.classification ?? "reincidencia_tecnica"}
                        onChange={(event) =>
                          setNewRecurrenceRule({
                            ...newRecurrenceRule,
                            classification: event.target.value as RecurrenceClassificationValue,
                            discount_points: ["reincidencia_tecnica", "garantia"].includes(event.target.value)
                          })
                        }
                      >
                        <option value="reincidencia_tecnica">Reincidência de manutenção</option>
                        <option value="garantia">Reincidência após ativação</option>
                        <option value="recorrencia_operacional">Reincidência operacional</option>
                        <option value="os_nao_reincidente">Não caracteriza reincidência</option>
                        <option value="demandas_diferentes">Demandas diferentes</option>
                        <option value="nao_identificado">Não identificado</option>
                      </select>
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
                  <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        className="h-4 w-4 accent-teal-700"
                        checked={Boolean(newRecurrenceRule.discount_points)}
                        onChange={(event) => setNewRecurrenceRule({ ...newRecurrenceRule, discount_points: event.target.checked })}
                      />
                      Pode anular a O.S original
                    </label>
                    <Button onClick={() => void createRecurrenceRule()}>Criar regra</Button>
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
                    <div className="grid gap-3 rounded-md border bg-slate-50 p-3">
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
                    <div className="grid gap-3 rounded-md border bg-slate-50 p-3">
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
                        <select
                          className="h-9 w-full rounded-md border border-input bg-white px-3 text-sm"
                          value={rule.classification}
                          onChange={(event) =>
                            setRecurrenceRules(
                              replaceById(recurrenceRules, rule.id, {
                                classification: event.target.value as RecurrenceClassificationValue
                              })
                            )
                          }
                        >
                          <option value="reincidencia_tecnica">Reincidência de manutenção</option>
                          <option value="garantia">Reincidência após ativação</option>
                          <option value="recorrencia_operacional">Reincidência operacional</option>
                          <option value="os_nao_reincidente">Não caracteriza reincidência</option>
                          <option value="demandas_diferentes">Demandas diferentes</option>
                          <option value="nao_identificado">Não identificado</option>
                        </select>
                      </div>
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
                      <label className="flex items-start gap-2 rounded-md border bg-slate-50 p-2 text-xs leading-snug text-slate-700">
                        <input
                          type="checkbox"
                          className="mt-0.5 h-4 w-4 shrink-0 accent-teal-700"
                          checked={rule.discount_points}
                          onChange={(event) =>
                            setRecurrenceRules(replaceById(recurrenceRules, rule.id, { discount_points: event.target.checked }))
                          }
                        />
                        <span>{rule.discount_points ? "Anula pontuação da O.S original" : "Apenas sinaliza reincidência"}</span>
                      </label>
                      <label className="flex items-center gap-2 rounded-md border bg-slate-50 px-2 py-2 text-xs text-slate-700">
                        <input
                          type="checkbox"
                          className="h-4 w-4 shrink-0 accent-teal-700"
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
                <div className="rounded-md border border-dashed bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
                  Nenhuma regra cadastrada. Sem regra, o motor usa somente a evidência técnica padrão encontrada nas O.S.
                </div>
              ) : null}
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
        </div>
    </section>
  );
}





