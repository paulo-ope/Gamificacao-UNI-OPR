"use client";

import { Save, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  AppCombobox,
  AppDrawer,
  AppInput,
  AppModal,
  AppSwitch,
  FilterToolbar,
  GuidanceCard,
  PageHeader,
  StepHeroCard,
  ToolbarCount,
  ToolbarSearch,
  configCardClass,
  configSectionClass,
  configSoftCardClass,
} from "@/components/gamification/config-ui";
import { StatusBadge } from "@/components/ui/status-badge";
import { GovernanceRulesPanel } from "@/components/gamification/governance-rules-panel";
import { AdvancedSection } from "@/components/gamification/logic-configuration-advanced-section";
import { CategoriesSection } from "@/components/gamification/logic-configuration-categories-section";
import { DiagnosesSection } from "@/components/gamification/logic-configuration-diagnoses-section";
import { GroupsSection } from "@/components/gamification/logic-configuration-groups-section";
import { IntegrationSection } from "@/components/gamification/logic-configuration-integration-section";
import { RecurrenceSection } from "@/components/gamification/logic-configuration-recurrence-section";
import { SlaSection } from "@/components/gamification/logic-configuration-sla-section";
import { SubjectsSection } from "@/components/gamification/logic-configuration-subjects-section";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AppCheckbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { StatusToast } from "@/components/ui/status-toast";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatInteger, formatMoney, formatPoints } from "@/lib/format";
import { numericInputValue, parseNumericInput } from "@/lib/numeric-input";
import type {
  CpkRegionalSnapshot,
  DiagnosisActionType,
  FinancialBreakdownItem,
  GamificationConfig,
  HealthRule,
  ImportedDiagnosis,
  RecurrenceClassificationRule,
  ScoringGroup,
  ScoringSubjectRule,
  ServiceOrderSubjectSummary,
  SlaPenaltyRule
} from "@/lib/types";
import {
  ADVANCED_SECTIONS,
  SIMPLE_SECTIONS,
  downloadJson,
  groupSnapshot,
  recurrenceClassificationLabel,
  replaceById,
  subjectRuleKey,
  uniqueSorted,
} from "@/components/gamification/logic-configuration-helpers";
import type {
  ConfigSection,
  DiagnosisFilter,
  GroupSnapshot,
  Mode,
  RecurrenceClassificationValue,
  SubjectFilter,
} from "@/components/gamification/logic-configuration-helpers";

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
  const [cpkSnapshotRows, setCpkSnapshotRows] = useState<CpkRegionalSnapshot[]>([]);
  const [cpkSyncing, setCpkSyncing] = useState(false);
  const now = new Date();
  const [cpkPeriod, setCpkPeriod] = useState({ year: now.getFullYear(), month: now.getMonth() + 1 });
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
    if (configSection !== "integration") return;
    void loadCpkSnapshot(cpkPeriod.year, cpkPeriod.month);
  }, [configSection, cpkPeriod.year, cpkPeriod.month]);

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
    // Pontos pode estar vazio (NaN) se o usuário limpou o campo pra digitar de novo - nunca
    // mandar isso pra API, cai no valor salvo anteriormente (baseline) ou 0.
    const validatedGroup: ScoringGroup = {
      ...group,
      default_points: Number.isFinite(group.default_points) ? group.default_points : groupBaselines[groupId]?.default_points ?? 0,
    };
    setSavingGroupId(groupId);
    await runConfigAction(async () => {
      await onSaveGroup(validatedGroup);
      setGroupBaselines((current) => ({
        ...current,
        [groupId]: groupSnapshot(validatedGroup),
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
      if (saved.warnings?.length) {
        setError(`Salvo com avisos: ${saved.warnings.join(" | ")}`);
      }
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
      if (imported.warnings?.length) {
        setError(`Importado com avisos: ${imported.warnings.join(" | ")}`);
      }
    }, "Configuração JSON importada sem apagar histórico.");
    if (fileRef.current) fileRef.current.value = "";
  }

  async function resetDefault() {
    await runConfigAction(async () => {
      const defaults = await api.resetDefaultGamificationConfig();
      setConfig(defaults);
      setLocalSettings(defaults.settings ?? {});
      await onReload();
      if (defaults.warnings?.length) {
        setError(`Restaurado com avisos: ${defaults.warnings.join(" | ")}`);
      }
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

  async function loadCpkSnapshot(year: number, month: number) {
    try {
      const rows = await api.cpkSnapshot(year, month);
      setCpkSnapshotRows(rows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao carregar snapshot de CPK.");
    }
  }

  async function syncCpk() {
    setCpkSyncing(true);
    setError(null);
    setMessage(null);
    try {
      const rows = await api.syncCpkSnapshot(cpkPeriod.year, cpkPeriod.month);
      setCpkSnapshotRows(rows);
      setMessage("Sincronização de CPK concluída.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao sincronizar CPK.");
    } finally {
      setCpkSyncing(false);
    }
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
      min_hours_between: newRecurrenceRule.min_hours_between ?? null,
      require_same_subject: Boolean(newRecurrenceRule.require_same_subject),
      require_same_diagnosis: Boolean(newRecurrenceRule.require_same_diagnosis),
      priority: Number.isFinite(newRecurrenceRule.priority) ? (newRecurrenceRule.priority as number) : 100,
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
            <CategoriesSection
              typeRows={typeRows}
              subjectRules={subjectRules}
              groups={groups}
              typeDrafts={typeDrafts}
              setTypeDrafts={setTypeDrafts}
              expandedTypes={expandedTypes}
              setExpandedTypes={setExpandedTypes}
              periodRuleStats={periodRuleStats}
              saveTypeGeneral={saveTypeGeneral}
              busy={busy}
            />
          ) : null}
          {configSection === "groups" ? (
            <GroupsSection
              newGroupDraft={newGroupDraft}
              setNewGroupDraft={setNewGroupDraft}
              createGroup={createGroup}
              busy={busy}
              subjectsByGroup={subjectsByGroup}
              selectedVisibleGroups={selectedVisibleGroups}
              setDeleteGroupSelectionOpen={setDeleteGroupSelectionOpen}
              allVisibleGroupsSelected={allVisibleGroupsSelected}
              toggleAllVisibleGroups={toggleAllVisibleGroups}
              groupBaselines={groupBaselines}
              selectedGroupIds={selectedGroupIds}
              toggleGroupSelected={toggleGroupSelected}
              globalPointValueLabel={globalPointValueLabel}
              setEditingGroupId={setEditingGroupId}
              duplicateGroup={duplicateGroup}
              restoreGroup={restoreGroup}
              setPendingDeleteGroupId={setPendingDeleteGroupId}
            />
          ) : null}

          {configSection === "subjects" ? (
            <SubjectsSection
              subjectFilter={subjectFilter}
              setSubjectFilter={setSubjectFilter}
              subjectGroupFilter={subjectGroupFilter}
              setSubjectGroupFilter={setSubjectGroupFilter}
              activeGroups={activeGroups}
              filteredSubjectRules={filteredSubjectRules}
              selectedVisibleSubjectRules={selectedVisibleSubjectRules}
              setDeleteSubjectSelectionOpen={setDeleteSubjectSelectionOpen}
              allVisibleSubjectsSelected={allVisibleSubjectsSelected}
              toggleAllVisibleSubjects={toggleAllVisibleSubjects}
              visibleSubjectRules={visibleSubjectRules}
              groups={groups}
              periodRuleStats={periodRuleStats}
              selectedSubjectIds={selectedSubjectIds}
              toggleSubjectSelected={toggleSubjectSelected}
              globalPointValueLabel={globalPointValueLabel}
              setEditingSubjectId={setEditingSubjectId}
              setPendingDeleteSubjectRuleId={setPendingDeleteSubjectRuleId}
              visibleSubjectRulesCount={visibleSubjectRulesCount}
              setVisibleSubjectRulesCount={setVisibleSubjectRulesCount}
            />
          ) : null}

          {configSection === "diagnoses" ? (
            <DiagnosesSection
              diagnosisFilter={diagnosisFilter}
              setDiagnosisFilter={setDiagnosisFilter}
              diagnosisRows={diagnosisRows}
              visibleDiagnosisRowsCount={visibleDiagnosisRowsCount}
              setVisibleDiagnosisRowsCount={setVisibleDiagnosisRowsCount}
              diagnosisDraft={diagnosisDraft}
              updateDiagnosisDraft={updateDiagnosisDraft}
              onSaveDiagnosisRule={onSaveDiagnosisRule}
            />
          ) : null}

          {configSection === "sla" ? (
            <SlaSection
              slaRules={slaRules}
              setSlaRules={setSlaRules}
              filteredSlaRules={filteredSlaRules}
              onCreateSlaRule={onCreateSlaRule}
              onSaveSlaRule={onSaveSlaRule}
              healthRules={healthRules}
              setHealthRules={setHealthRules}
              saveHealthRule={saveHealthRule}
              localSettings={localSettings}
              setLocalSettings={setLocalSettings}
              saveSettings={saveSettings}
            />
          ) : null}

          {configSection === "recurrence" ? (
            <RecurrenceSection
              localSettings={localSettings}
              setLocalSettings={setLocalSettings}
              saveSettings={saveSettings}
              setConfigSection={setConfigSection}
              newRecurrenceRule={newRecurrenceRule}
              setNewRecurrenceRule={setNewRecurrenceRule}
              createRecurrenceRule={createRecurrenceRule}
              osTypeOptions={osTypeOptions}
              subjectOptions={subjectOptions}
              diagnosisOptions={diagnosisOptions}
              filteredRecurrenceRules={filteredRecurrenceRules}
              recurrenceRules={recurrenceRules}
              setRecurrenceRules={setRecurrenceRules}
              onSaveRecurrenceRule={onSaveRecurrenceRule}
              onDeleteRecurrenceRule={onDeleteRecurrenceRule}
            />
          ) : null}

          {configSection === "integration" ? (
            <IntegrationSection
              localSettings={localSettings}
              setLocalSettings={setLocalSettings}
              saveSettings={saveSettings}
              cpkPeriod={cpkPeriod}
              setCpkPeriod={setCpkPeriod}
              cpkSyncing={cpkSyncing}
              syncCpk={syncCpk}
              cpkSnapshotRows={cpkSnapshotRows}
            />
          ) : null}

          {configSection === "advanced" && mode === "advanced" ? (
            <AdvancedSection
              saveSnapshot={saveSnapshot}
              exportConfig={exportConfig}
              busy={busy}
              fileRef={fileRef}
              resetDefault={resetDefault}
            />
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
                          <AppCheckbox
                            checked={currentEditingSubject.use_group_default}
                            onCheckedChange={(checked) =>
                              setSubjectRules(replaceById(subjectRules, currentEditingSubject.id, { use_group_default: checked }))
                            }
                            ariaLabel="Usar pontuação padrão do grupo"
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
                        <StatusBadge tone="emerald">{formatInteger(stats.orders)} O.S impactadas</StatusBadge>
                        <StatusBadge tone="emerald">{formatMoney(stats.impact)}</StatusBadge>
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
                      value={numericInputValue(currentEditingGroup.default_points)}
                      onChange={(event) => updateGroupField(currentEditingGroup.id, { default_points: parseNumericInput(event.target.value) })}
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
                    <StatusBadge tone="emerald">
                      {formatInteger(subjectsByGroup.find((item) => item.group.id === currentEditingGroup.id)?.rules.length ?? 0)} assuntos
                    </StatusBadge>
                    <StatusBadge tone="blue">
                      {formatInteger(subjectsByGroup.find((item) => item.group.id === currentEditingGroup.id)?.orders ?? 0)} O.S
                    </StatusBadge>
                    <StatusBadge tone="emerald">
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




