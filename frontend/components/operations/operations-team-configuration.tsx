"use client";

import {
  Clock3,
  Download,
  FileJson,
  Layers3,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  Search,
  Settings2,
  Sparkles,
  Tags,
  Target,
  Trash2,
  Upload,
  Users,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AppCheckbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { MultiSelect } from "@/components/ui/multi-select";
import {
  operationsApi,
  type OperationIxcSyncSettings,
  type OperationResponsibleProfile,
  type OperationSubjectTypeMapping,
  type OperationTeamConfiguration,
  type OperationTeamModel,
  type OperationTeamModelPayload,
  type OperationTeamTargetRule,
} from "@/lib/operations-api";

const BASE_RULES: OperationTeamTargetRule[] = [
  {
    period_type: "weekday",
    enabled: true,
    median_from_quantity: 3,
    good_from_quantity: 4,
    target_quantity: 5,
    start_time: "08:00",
    end_time: "18:00",
  },
  {
    period_type: "saturday",
    enabled: true,
    median_from_quantity: 3,
    good_from_quantity: 4,
    target_quantity: 5,
    start_time: "08:00",
    end_time: "18:00",
  },
  {
    period_type: "sunday",
    enabled: false,
    median_from_quantity: 3,
    good_from_quantity: 4,
    target_quantity: 5,
    start_time: null,
    end_time: null,
  },
  {
    period_type: "monthly",
    enabled: true,
    median_from_quantity: 66,
    good_from_quantity: 88,
    target_quantity: 110,
    start_time: null,
    end_time: null,
  },
];

const DEFAULT_MODEL: OperationTeamModelPayload = {
  name: "",
  daily_target: 5,
  median_from_quantity: 3,
  good_from_quantity: 4,
  below_target_color: "#fee2e2",
  median_color: "#fef3c7",
  good_color: "#dcfce7",
  excellent_color: "#dbeafe",
  active: true,
  target_rules: BASE_RULES,
};

const STANDARD_MODELS = [
  "INSTALAÇÃO CIDADE",
  "TECNICO 12/36H",
  "SUPORTE MOTO",
  "SUPORTE CARRO",
  "RURAL",
  "FAZ TUDO",
  "AUXILIAR",
  "Nao informado",
] as const;
const MEMBERS_PER_PAGE = 50;

function payloadFromModel(
  model: OperationTeamModel,
): OperationTeamModelPayload {
  const {
    id: _id,
    created_at: _createdAt,
    updated_at: _updatedAt,
    ...payload
  } = model;
  return {
    ...payload,
    target_rules: payload.target_rules.map(({ id: _ruleId, ...rule }) => rule),
  };
}

export function OperationsTeamConfiguration({
  canManageTeamModels,
  canManageSubjects,
  canManageViews,
  canSyncIxc,
  ixcSyncSettings,
  onIxcSyncSettingsChange,
}: {
  canManageTeamModels: boolean;
  canManageSubjects: boolean;
  canManageViews: boolean;
  canSyncIxc: boolean;
  ixcSyncSettings: OperationIxcSyncSettings | null;
  onIxcSyncSettingsChange: (settings: OperationIxcSyncSettings) => void;
}) {
  const canManage = canManageTeamModels;
  const [data, setData] = useState<OperationTeamConfiguration | null>(null);
  const [section, setSection] = useState<"models" | "members" | "subjects" | "sync">(
    canManageTeamModels ? "models" : canManageSubjects ? "subjects" : "sync",
  );
  const [subjectMappings, setSubjectMappings] = useState<
    OperationSubjectTypeMapping[]
  >([]);
  const [subjectSearch, setSubjectSearch] = useState("");
  const [selectedSubjects, setSelectedSubjects] = useState<string[]>([]);
  const [targetOsType, setTargetOsType] = useState("");
  const [savingSubjects, setSavingSubjects] = useState(false);
  const [form, setForm] = useState<OperationTeamModelPayload>(DEFAULT_MODEL);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [regional, setRegional] = useState("");
  const [memberPage, setMemberPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<OperationTeamModel | null>(
    null,
  );
  const [savingMember, setSavingMember] = useState<string | null>(null);
  const [syncingDirectory, setSyncingDirectory] = useState(false);
  const [savingSyncSettings, setSavingSyncSettings] = useState(false);
  const [syncEnabled, setSyncEnabled] = useState(false);
  const [syncIntervalMinutes, setSyncIntervalMinutes] = useState("20");
  const [syncBacklogIntervalMinutes, setSyncBacklogIntervalMinutes] = useState("60");
  const [syncLookbackDays, setSyncLookbackDays] = useState("1");
  const [syncSectorIds, setSyncSectorIds] = useState<string[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const importInputRef = useRef<HTMLInputElement>(null);

  async function load() {
    setLoading(true);
    try {
      const [configuration, mappings] = await Promise.all([
        canManageTeamModels
          ? operationsApi.teamConfiguration()
          : Promise.resolve(null),
        canManageSubjects
          ? operationsApi.subjectTypeMappings()
          : Promise.resolve([]),
      ]);
      setData(configuration);
      setSubjectMappings(mappings);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Falha ao carregar os modelos de equipe.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [canManageSubjects, canManageTeamModels]);

  useEffect(() => {
    if (!ixcSyncSettings) return;
    setSyncEnabled(ixcSyncSettings.enabled);
    setSyncIntervalMinutes(String(ixcSyncSettings.interval_minutes));
    setSyncBacklogIntervalMinutes(String(ixcSyncSettings.backlog_sweep_interval_minutes));
    setSyncLookbackDays(String(ixcSyncSettings.lookback_days));
    setSyncSectorIds(ixcSyncSettings.sector_ids);
  }, [ixcSyncSettings]);

  const regionals = useMemo(
    () =>
      Array.from(
        new Set(data?.members.flatMap((item) => item.regionals) || []),
      ).sort(),
    [data],
  );
  const filteredMembers = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase("pt-BR");
    return (data?.members || []).filter(
      (item) =>
        (!regional || item.regionals.includes(regional)) &&
        (!needle ||
          item.responsible_name.toLocaleLowerCase("pt-BR").includes(needle)),
    );
  }, [data, regional, search]);
  const memberTotalPages = Math.max(
    1,
    Math.ceil(filteredMembers.length / MEMBERS_PER_PAGE),
  );
  const visibleMembers = useMemo(() => {
    const start = (memberPage - 1) * MEMBERS_PER_PAGE;
    return filteredMembers.slice(start, start + MEMBERS_PER_PAGE);
  }, [filteredMembers, memberPage]);

  useEffect(() => {
    setMemberPage(1);
  }, [regional, search]);
  useEffect(() => {
    setMemberPage((current) => Math.min(current, memberTotalPages));
  }, [memberTotalPages]);
  const thresholdsValid =
    1 < form.median_from_quantity &&
    form.median_from_quantity < form.good_from_quantity &&
    form.good_from_quantity < form.daily_target;
  const targetRulesValid = form.target_rules.every(
    (rule) =>
      !rule.enabled ||
      (1 < rule.median_from_quantity &&
        rule.median_from_quantity < rule.good_from_quantity &&
        rule.good_from_quantity < rule.target_quantity &&
        (rule.period_type === "monthly" ||
          Boolean(rule.start_time && rule.end_time))),
  );
  const filteredSubjects = useMemo(() => {
    const needle = subjectSearch.trim().toLocaleLowerCase("pt-BR");
    return subjectMappings.filter(
      (item) =>
        !needle ||
        `${item.subject} ${item.os_type}`
          .toLocaleLowerCase("pt-BR")
          .includes(needle),
    );
  }, [subjectMappings, subjectSearch]);
  const knownTypes = useMemo(
    () =>
      Array.from(
        new Set(
          subjectMappings
            .map((item) => item.os_type)
            .filter((item) => item !== "Pendente de classificação"),
        ),
      ).sort(),
    [subjectMappings],
  );

  function updateRule(
    periodType: OperationTeamTargetRule["period_type"],
    changes: Partial<OperationTeamTargetRule>,
  ) {
    setForm((current) => ({
      ...current,
      target_rules: current.target_rules.map((rule) =>
        rule.period_type === periodType ? { ...rule, ...changes } : rule,
      ),
    }));
  }

  function updateWeekday(changes: {
    median_from_quantity?: number;
    good_from_quantity?: number;
    daily_target?: number;
  }) {
    setForm((current) => ({
      ...current,
      ...changes,
      target_rules: current.target_rules.map((rule) =>
        rule.period_type === "weekday"
          ? {
              ...rule,
              ...(changes.median_from_quantity === undefined
                ? {}
                : { median_from_quantity: changes.median_from_quantity }),
              ...(changes.good_from_quantity === undefined
                ? {}
                : { good_from_quantity: changes.good_from_quantity }),
              ...(changes.daily_target === undefined
                ? {}
                : { target_quantity: changes.daily_target }),
            }
          : rule,
      ),
    }));
  }

  function startNew() {
    setEditingId(null);
    setForm({
      ...DEFAULT_MODEL,
      target_rules: BASE_RULES.map((rule) => ({ ...rule })),
    });
    setError(null);
  }

  function edit(model: OperationTeamModel) {
    setEditingId(model.id);
    setForm(payloadFromModel(model));
    setError(null);
  }

  async function saveModel() {
    if (!form.name.trim() || !thresholdsValid || !targetRulesValid) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      if (editingId) await operationsApi.updateTeamModel(editingId, form);
      else await operationsApi.createTeamModel(form);
      setMessage(editingId ? "Modelo atualizado." : "Modelo criado.");
      startNew();
      await load();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Falha ao salvar o modelo.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function saveSubjectClassification() {
    if (!selectedSubjects.length || !targetOsType.trim()) return;
    setSavingSubjects(true);
    setError(null);
    try {
      const updated = await operationsApi.updateSubjectTypeMappings(
        selectedSubjects,
        targetOsType,
      );
      setSubjectMappings(updated);
      setSelectedSubjects([]);
      setTargetOsType("");
      setMessage(`${selectedSubjects.length} assunto(s) classificado(s).`);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Falha ao classificar os assuntos.",
      );
    } finally {
      setSavingSubjects(false);
    }
  }

  function applyLegacyPattern() {
    const target = Math.max(4, form.daily_target);
    updateWeekday({
      daily_target: target,
      median_from_quantity: target - 2,
      good_from_quantity: target - 1,
    });
  }

  async function deleteModel() {
    if (!deleteTarget) return;
    setDeleting(true);
    setError(null);
    setMessage(null);
    try {
      await operationsApi.deleteTeamModel(deleteTarget.id);
      setDeleteTarget(null);
      startNew();
      await load();
      setMessage(`Modelo "${deleteTarget.name}" excluído.`);
    } catch (reason) {
      setDeleteTarget(null);
      setError(
        reason instanceof Error ? reason.message : "Falha ao excluir o modelo.",
      );
    } finally {
      setDeleting(false);
    }
  }

  async function assign(
    member: OperationResponsibleProfile,
    changes: Partial<OperationResponsibleProfile>,
  ) {
    const next = { ...member, ...changes };
    const key = member.responsible_name;
    setSavingMember(key);
    setError(null);
    setData((current) =>
      current
        ? {
            ...current,
            members: current.members.map((item) =>
              item.responsible_name === member.responsible_name
                ? next
                : item,
            ),
          }
        : current,
    );
    try {
      await operationsApi.assignTeamMember(next);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Falha ao atualizar o responsável operacional.",
      );
      await load();
    } finally {
      setSavingMember(null);
    }
  }

  async function exportConfiguration() {
    setError(null);
    setMessage(null);
    try {
      const configuration = await operationsApi.exportConfiguration();
      const blob = new Blob([JSON.stringify(configuration, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `operacao-configuracao-${new Date().toISOString().slice(0, 10)}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      setMessage("Arquivo de configuração exportado.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao exportar a configuração.");
    }
  }

  async function importConfiguration(file: File | undefined) {
    if (!file) return;
    setError(null);
    setMessage(null);
    try {
      const result = await operationsApi.importConfiguration(JSON.parse(await file.text()));
      await load();
      setMessage(`Configuração importada: ${result.team_models} modelo(s), ${result.team_members} colaborador(es), ${result.subject_mappings} assunto(s) e ${result.saved_filters} visão(ões).`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível importar este JSON.");
    } finally {
      if (importInputRef.current) importInputRef.current.value = "";
    }
  }

  async function changeResponsibleSource(source: "orders" | "ixc" | "both") {
    try {
      const next = await operationsApi.updateResponsibleDirectory(source);
      setData(next);
      setMessage("Origem da lista de responsáveis atualizada.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao atualizar a origem dos responsáveis.");
    }
  }

  async function syncResponsibleDirectory() {
    setSyncingDirectory(true);
    try {
      const result = await operationsApi.syncResponsibleDirectory();
      await load();
      setMessage(`${result.active} colaborador(es) ativos sincronizados do IXC.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao sincronizar colaboradores do IXC.");
    } finally {
      setSyncingDirectory(false);
    }
  }

  async function saveIxcSyncSettings() {
    if (!canSyncIxc) return;
    setSavingSyncSettings(true);
    setError(null);
    setMessage(null);
    try {
      const interval = Number(syncIntervalMinutes);
      const backlogInterval = Number(syncBacklogIntervalMinutes);
      const lookbackDays = Number(syncLookbackDays);
      const saved = await operationsApi.updateIxcSyncSettings({
        enabled: syncEnabled,
        interval_minutes: Number.isFinite(interval) ? interval : 20,
        backlog_sweep_interval_minutes: Number.isFinite(backlogInterval)
          ? backlogInterval
          : 60,
        lookback_days: Number.isFinite(lookbackDays) ? lookbackDays : 1,
        sector_ids: syncSectorIds,
      });
      onIxcSyncSettingsChange(saved);
      setMessage(`Sincronização IXC atualizada: ${saved.sector_scope_label}.`);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Falha ao salvar a sincronização IXC.",
      );
    } finally {
      setSavingSyncSettings(false);
    }
  }

  const ixcSectorOptions = ixcSyncSettings?.available_sectors.map((sector) => sector.id) || [];
  const ixcSectorLabel = (sectorId: string) =>
    ixcSyncSettings?.available_sectors.find((sector) => sector.id === sectorId)?.name ||
    sectorId;

  if (loading && !data)
    return (
      <div className="flex min-h-64 items-center justify-center gap-2 text-sm text-slate-500">
        <Loader2 className="h-4 w-4 animate-spin" /> Carregando equipes...
      </div>
    );

  return (
    <div className="space-y-4">
      {message ? (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {message}
        </div>
      ) : null}
      {error ? (
        <div
          role="alert"
          className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          {error}
        </div>
      ) : null}
      <Card className="rounded-2xl border-slate-200 bg-slate-50/70">
        <CardHeader>
          {canManageTeamModels ? (
            <div className="mb-3 flex flex-wrap justify-end gap-2">
              <input
                ref={importInputRef}
                type="file"
                accept="application/json,.json"
                className="sr-only"
                onChange={(event) => void importConfiguration(event.target.files?.[0])}
              />
              <Button type="button" variant="outline" size="sm" onClick={() => importInputRef.current?.click()}>
                <Upload className="h-4 w-4" /> Importar JSON
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => void exportConfiguration()}>
                <Download className="h-4 w-4" /> Exportar JSON
              </Button>
            </div>
          ) : null}
          <CardTitle className="flex items-center gap-2 text-base">
            <Settings2 className="h-4 w-4 text-blue-600" /> Configurações da
            Operação
          </CardTitle>
          <p className="text-xs text-slate-500">
            Personalize modelos, jornadas, metas, vínculos e a classificação
            operacional dos assuntos.
          </p>
          {canManageTeamModels ? (
            <p className="mt-2 flex items-center gap-1.5 text-[11px] text-slate-500">
              <FileJson className="h-3.5 w-3.5 shrink-0 text-blue-600" />
              O JSON usa nomes, não IDs. Um vínculo de colaborador vale para todas as filiais.
              {!canManageViews ? " Visões não são incluídas sem a permissão de gerenciar visões." : ""}
            </p>
          ) : null}
        </CardHeader>
        <CardContent className="grid gap-2 md:grid-cols-4">
          {(
            [
              [
                "models",
                "Modelos, metas e jornadas",
                "Metas por dia, mês e horário operacional",
                Target,
              ],
              [
                "members",
                "Colaboradores e vínculos",
                "Modelo aplicado a cada responsável",
                Users,
              ],
              [
                "subjects",
                "Tipos gerais e assuntos",
                "Catálogo e fila de classificação",
                Tags,
              ],
              [
                "sync",
                "Sincronizacao IXC",
                "Intervalo automatico e setores importados",
                RefreshCw,
              ],
            ] as const
          )
            .filter(([value]) =>
              value === "subjects"
                ? canManageSubjects
                : value === "sync"
                  ? canSyncIxc
                  : canManageTeamModels,
            )
            .map(([value, label, description, Icon]) => (
            <button
              key={value}
              type="button"
              onClick={() => setSection(value)}
              className={`rounded-xl border p-3 text-left transition ${section === value ? "border-blue-400 bg-blue-600 text-white shadow" : "bg-white text-slate-800 hover:border-blue-300"}`}
            >
              <Icon className="h-4 w-4" />
              <span className="mt-2 block text-sm font-semibold">{label}</span>
              <span
                className={`mt-0.5 block text-[11px] ${section === value ? "text-blue-100" : "text-slate-500"}`}
              >
                {description}
              </span>
            </button>
          ))}
        </CardContent>
      </Card>
      <div className="grid min-w-0 gap-4">
        <Card
          className={`${section === "sync" ? "block" : "hidden"} min-w-0 rounded-2xl border-slate-200`}
        >
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2 text-base">
              <RefreshCw className="h-4 w-4 text-blue-600" /> Sincronização IXC
            </CardTitle>
            <p className="text-xs text-slate-500">
              Controle a sincronização automática da Operação Analítica sem
              reiniciar o backend. O ciclo usa lotes diários e setores
              selecionados para reduzir pressão no IXC.
            </p>
          </CardHeader>
          <CardContent className="space-y-4 p-4">
            <div className="grid gap-3 lg:grid-cols-[1.2fr_0.8fr_0.8fr_0.8fr]">
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <p className="text-xs font-semibold text-slate-900">
                  Sincronização automática
                </p>
                <p className="mt-1 text-[11px] text-slate-500">
                  Quando ligada, o scheduler consulta IXC no intervalo abaixo e
                  atualiza os dados analíticos.
                </p>
                <button
                  type="button"
                  role="switch"
                  aria-checked={syncEnabled}
                  onClick={() => setSyncEnabled((current) => !current)}
                  className={`mt-3 inline-flex h-9 items-center rounded-full border px-1 transition ${syncEnabled ? "border-blue-600 bg-blue-600" : "border-slate-300 bg-white"}`}
                >
                  <span
                    className={`inline-flex h-7 w-7 items-center justify-center rounded-full bg-white text-[10px] font-bold shadow transition ${syncEnabled ? "translate-x-14 text-blue-700" : "translate-x-0 text-slate-500"}`}
                  >
                    {syncEnabled ? "ON" : "OFF"}
                  </span>
                  <span className="w-14 text-center text-xs font-semibold text-white">
                    {syncEnabled ? "" : "OFF"}
                  </span>
                </button>
              </div>
              <label className="grid gap-1.5 text-xs font-medium text-slate-700">
                Intervalo da sincronização
                <Input
                  type="number"
                  min={5}
                  max={1440}
                  value={syncIntervalMinutes}
                  onChange={(event) => setSyncIntervalMinutes(event.target.value)}
                />
                <span className="text-[10px] font-normal text-slate-500">
                  Mínimo 5 min. Recomendado: 20 a 60 min.
                </span>
              </label>
              <label className="grid gap-1.5 text-xs font-medium text-slate-700">
                Varredura de backlog
                <Input
                  type="number"
                  min={15}
                  max={1440}
                  value={syncBacklogIntervalMinutes}
                  onChange={(event) => setSyncBacklogIntervalMinutes(event.target.value)}
                />
                <span className="text-[10px] font-normal text-slate-500">
                  Mínimo 15 min. Essa consulta é mais pesada.
                </span>
              </label>
              <label className="grid gap-1.5 text-xs font-medium text-slate-700">
                Janela de dias reimportados
                <Input
                  type="number"
                  min={1}
                  max={30}
                  value={syncLookbackDays}
                  onChange={(event) => setSyncLookbackDays(event.target.value)}
                />
                <span className="text-[10px] font-normal text-slate-500">
                  Quantos dias antes de hoje o ciclo reimporta a cada rodada
                  (pega O.S. que só fecham/atualizam depois de abertas).
                </span>
              </label>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-xs font-semibold text-slate-900">
                    Setores sincronizados
                  </p>
                  <p className="text-[11px] text-slate-500">
                    Escolha quais setores do IXC entram na importação manual e
                    automática.
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setSyncSectorIds(ixcSectorOptions)}
                  >
                    Todos os setores
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => setSyncSectorIds(["7", "8", "9"])}
                  >
                    3 principais
                  </Button>
                </div>
              </div>
              <MultiSelect
                values={syncSectorIds}
                options={ixcSectorOptions}
                ariaLabel="Setores sincronizados no IXC"
                placeholder="3 setores principais"
                formatOption={(value) => `${value} · ${ixcSectorLabel(value)}`}
                onChange={setSyncSectorIds}
              />
              <p className="mt-2 text-[10px] text-slate-500">
                Atual: {ixcSyncSettings?.sector_scope_label || "3 setores principais"}.
                Se nada for selecionado, o backend usa o escopo seguro dos 3 setores.
              </p>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-blue-100 bg-blue-50 px-3 py-2">
              <p className="text-xs text-blue-900">
                Para importar desde 01/01/2026, selecione “Todos os setores”,
                salve e use “Sincronizar dados” no período desejado. Períodos
                grandes viram job em background com retomada.
              </p>
              <Button
                type="button"
                disabled={savingSyncSettings}
                onClick={() => void saveIxcSyncSettings()}
                className="shrink-0"
              >
                {savingSyncSettings ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Save className="h-4 w-4" />
                )}
                Salvar sincronização
              </Button>
            </div>
          </CardContent>
        </Card>
        <Card
          className={`${section === "models" ? "block" : "hidden"} min-w-0 rounded-2xl border-slate-200`}
        >
          <CardHeader className="flex-row items-start justify-between gap-3 border-b">
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                <Target className="h-4 w-4 text-blue-600" /> Modelo e meta
                diária
              </CardTitle>
              <p className="mt-1 text-xs text-slate-500">
                As cores usam a quantidade de O.S. finalizadas no dia, sem
                percentuais.
              </p>
            </div>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={startNew}
              disabled={!canManageTeamModels}
            >
              <Plus className="h-4 w-4" /> Novo
            </Button>
          </CardHeader>
          <CardContent className="space-y-4 pt-4">
            <label className="grid gap-1 text-xs font-semibold text-slate-600">
              Nome do modelo
              <Input
                list="operation-team-model-suggestions"
                value={form.name}
                maxLength={120}
                disabled={!canManage}
                placeholder="Ex.: Plantão Cidade 12/36H"
                onChange={(event) =>
                  setForm({ ...form, name: event.target.value })
                }
              />
              <datalist id="operation-team-model-suggestions">
                {STANDARD_MODELS.map((name) => (
                  <option key={name} value={name} />
                ))}
              </datalist>
              <span className="font-normal text-slate-400">
                O nome pode ser alterado sem perder os colaboradores vinculados.
              </span>
            </label>
            <div className="rounded-xl border border-blue-100 bg-blue-50/60 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-xs font-semibold text-blue-950">
                    Onde cada desempenho começa?
                  </p>
                  <p className="text-[11px] text-blue-700">
                    Exemplo legado: mediano 3, bom 4 e excelente/meta 5.
                  </p>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={applyLegacyPattern}
                  disabled={!canManage}
                >
                  <Sparkles className="h-3.5 w-3.5" /> Aplicar padrão -2 / -1
                </Button>
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-3">
                <label className="grid gap-1 text-[11px] font-semibold text-slate-600">
                  Mediano a partir de
                  <Input
                    type="number"
                    min={2}
                    max={Math.max(2, form.good_from_quantity - 1)}
                    value={form.median_from_quantity}
                    disabled={!canManage}
                    onChange={(event) =>
                      updateWeekday({
                        median_from_quantity: Number(event.target.value),
                      })
                    }
                  />
                </label>
                <label className="grid gap-1 text-[11px] font-semibold text-slate-600">
                  Bom a partir de
                  <Input
                    type="number"
                    min={form.median_from_quantity + 1}
                    max={Math.max(
                      form.median_from_quantity + 1,
                      form.daily_target - 1,
                    )}
                    value={form.good_from_quantity}
                    disabled={!canManage}
                    onChange={(event) =>
                      updateWeekday({
                        good_from_quantity: Number(event.target.value),
                      })
                    }
                  />
                </label>
                <label className="grid gap-1 text-[11px] font-semibold text-slate-600">
                  Excelente / meta a partir de
                  <Input
                    type="number"
                    min={form.good_from_quantity + 1}
                    max={500}
                    value={form.daily_target}
                    disabled={!canManage}
                    onChange={(event) =>
                      updateWeekday({
                        daily_target: Number(event.target.value),
                      })
                    }
                  />
                </label>
              </div>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
              <div className="flex items-center gap-2">
                <Clock3 className="h-4 w-4 text-blue-600" />
                <div>
                  <p className="text-xs font-semibold text-slate-900">
                    Metas e jornadas por período
                  </p>
                  <p className="text-[11px] text-slate-500">
                    Sábado e domingo podem ter metas e horários independentes. A
                    regra mensal colore o total do calendário.
                  </p>
                </div>
              </div>
              <div className="mt-3 space-y-2">
                {form.target_rules.map((rule) => {
                  const label =
                    rule.period_type === "weekday"
                      ? "Segunda a sexta"
                      : rule.period_type === "saturday"
                        ? "Sábado"
                        : rule.period_type === "sunday"
                          ? "Domingo"
                          : "Meta mensal";
                  return (
                    <div
                      key={rule.period_type}
                      className="rounded-lg border bg-white p-3"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-xs font-semibold text-slate-800">
                          {label}
                        </p>
                        <label className="flex items-center gap-2 text-[11px] text-slate-500">
                          <AppCheckbox
                            checked={rule.enabled}
                            disabled={!canManage}
                            onCheckedChange={(checked) =>
                              updateRule(rule.period_type, {
                                enabled: checked,
                              })
                            }
                            ariaLabel="Regra ativa"
                          />
                          {rule.enabled ? "Regra ativa" : "Sem meta"}
                        </label>
                      </div>
                      {rule.enabled ? (
                        <div className="mt-2 grid gap-2 sm:grid-cols-3 lg:grid-cols-5">
                          {rule.period_type !== "monthly" ? (
                            <>
                              <label className="grid gap-1 text-[10px] font-semibold text-slate-500">
                                Início
                                <Input
                                  type="time"
                                  value={(rule.start_time || "").slice(0, 5)}
                                  disabled={!canManage}
                                  onChange={(event) =>
                                    updateRule(rule.period_type, {
                                      start_time: event.target.value || null,
                                    })
                                  }
                                />
                              </label>
                              <label className="grid gap-1 text-[10px] font-semibold text-slate-500">
                                Término
                                <Input
                                  type="time"
                                  value={(rule.end_time || "").slice(0, 5)}
                                  disabled={!canManage}
                                  onChange={(event) =>
                                    updateRule(rule.period_type, {
                                      end_time: event.target.value || null,
                                    })
                                  }
                                />
                              </label>
                            </>
                          ) : null}
                          <label className="grid gap-1 text-[10px] font-semibold text-slate-500">
                            Mediano
                            <Input
                              type="number"
                              min={2}
                              value={rule.median_from_quantity}
                              disabled={
                                !canManage || rule.period_type === "weekday"
                              }
                              onChange={(event) =>
                                updateRule(rule.period_type, {
                                  median_from_quantity: Number(
                                    event.target.value,
                                  ),
                                })
                              }
                            />
                          </label>
                          <label className="grid gap-1 text-[10px] font-semibold text-slate-500">
                            Bom
                            <Input
                              type="number"
                              min={3}
                              value={rule.good_from_quantity}
                              disabled={
                                !canManage || rule.period_type === "weekday"
                              }
                              onChange={(event) =>
                                updateRule(rule.period_type, {
                                  good_from_quantity: Number(
                                    event.target.value,
                                  ),
                                })
                              }
                            />
                          </label>
                          <label className="grid gap-1 text-[10px] font-semibold text-slate-500">
                            Excelente/meta
                            <Input
                              type="number"
                              min={4}
                              value={rule.target_quantity}
                              disabled={
                                !canManage || rule.period_type === "weekday"
                              }
                              onChange={(event) =>
                                updateRule(rule.period_type, {
                                  target_quantity: Number(event.target.value),
                                })
                              }
                            />
                          </label>
                        </div>
                      ) : (
                        <p className="mt-2 text-[11px] text-slate-400">
                          A produção continua visível, mas não recebe
                          classificação por meta.
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <label
                className="rounded-lg border p-2 text-[10px] font-semibold text-slate-600"
                style={{ backgroundColor: form.below_target_color }}
              >
                <span className="block">Abaixo</span>
                <span className="block text-[11px]">
                  1–{form.median_from_quantity - 1}
                </span>
                <input
                  aria-label="Cor abaixo da meta"
                  type="color"
                  value={form.below_target_color}
                  disabled={!canManage}
                  onChange={(event) =>
                    setForm({ ...form, below_target_color: event.target.value })
                  }
                  className="mt-2 h-8 w-full cursor-pointer rounded border bg-white p-1"
                />
              </label>
              <label
                className="rounded-lg border p-2 text-[10px] font-semibold text-slate-600"
                style={{ backgroundColor: form.median_color }}
              >
                <span className="block">Mediano</span>
                <span className="block text-[11px]">
                  {form.median_from_quantity}–{form.good_from_quantity - 1}
                </span>
                <input
                  aria-label="Cor mediano"
                  type="color"
                  value={form.median_color}
                  disabled={!canManage}
                  onChange={(event) =>
                    setForm({ ...form, median_color: event.target.value })
                  }
                  className="mt-2 h-8 w-full cursor-pointer rounded border bg-white p-1"
                />
              </label>
              <label
                className="rounded-lg border p-2 text-[10px] font-semibold text-slate-600"
                style={{ backgroundColor: form.good_color }}
              >
                <span className="block">Bom</span>
                <span className="block text-[11px]">
                  {form.good_from_quantity}–{form.daily_target - 1}
                </span>
                <input
                  aria-label="Cor bom"
                  type="color"
                  value={form.good_color}
                  disabled={!canManage}
                  onChange={(event) =>
                    setForm({ ...form, good_color: event.target.value })
                  }
                  className="mt-2 h-8 w-full cursor-pointer rounded border bg-white p-1"
                />
              </label>
              <label
                className="rounded-lg border p-2 text-[10px] font-semibold text-slate-600"
                style={{ backgroundColor: form.excellent_color }}
              >
                <span className="block">Excelente</span>
                <span className="block text-[11px]">{form.daily_target}+</span>
                <input
                  aria-label="Cor excelente"
                  type="color"
                  value={form.excellent_color}
                  disabled={!canManage}
                  onChange={(event) =>
                    setForm({ ...form, excellent_color: event.target.value })
                  }
                  className="mt-2 h-8 w-full cursor-pointer rounded border bg-white p-1"
                />
              </label>
            </div>
            {!thresholdsValid || !targetRulesValid ? (
              <p
                role="alert"
                className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700"
              >
                Todas as regras ativas precisam de faixas crescentes e, quando
                aplicável, início e término da jornada.
              </p>
            ) : null}
            <label className="flex items-center gap-2 text-xs text-slate-600">
              <AppCheckbox
                checked={form.active}
                disabled={!canManage}
                onCheckedChange={(checked) =>
                  setForm({ ...form, active: checked })
                }
                ariaLabel="Modelo ativo"
              />{" "}
              Modelo ativo
            </label>
            {canManage ? (
              <div className="flex gap-2">
                <Button
                  type="button"
                  className="flex-1"
                  disabled={
                    saving ||
                    !form.name.trim() ||
                    !thresholdsValid ||
                    !targetRulesValid
                  }
                  onClick={() => void saveModel()}
                >
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  {editingId ? "Atualizar modelo" : "Criar modelo"}
                </Button>
                {editingId ? (
                  <Button
                    type="button"
                    variant="outline"
                    className="border-red-200 text-red-700 hover:bg-red-50"
                    aria-label="Excluir modelo"
                    onClick={() => {
                      const model = data?.models.find(
                        (item) => item.id === editingId,
                      );
                      if (model) setDeleteTarget(model);
                    }}
                  >
                    <Trash2 className="h-4 w-4" /> Excluir
                  </Button>
                ) : null}
              </div>
            ) : null}
            <div className="border-t pt-3">
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                Modelos cadastrados
              </p>
              <div className="flex flex-wrap gap-2">
                {data?.models.map((model) => (
                  <button
                    key={model.id}
                    type="button"
                    onClick={() => edit(model)}
                    className={`rounded-lg border px-3 py-2 text-left text-xs hover:border-blue-300 ${editingId === model.id ? "border-blue-400 bg-blue-50" : "bg-white"}`}
                  >
                    <span className="font-semibold text-slate-800">
                      {model.name}
                    </span>
                    <span className="ml-2 text-slate-400">
                      meta {model.daily_target}+
                    </span>
                    {!model.active ? (
                      <Badge className="ml-2 border-slate-200 bg-slate-100 text-slate-500">
                        Inativo
                      </Badge>
                    ) : null}
                  </button>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card
          className={`${section === "members" ? "block" : "hidden"} min-w-0 rounded-2xl border-slate-200`}
        >
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2 text-base">
              <Users className="h-4 w-4 text-blue-600" /> Responsáveis
              operacionais
            </CardTitle>
            <p className="text-xs text-slate-500">
              Atribua apenas o modelo de equipe ao responsável que vem do IXC.
            </p>
            <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold text-slate-800">Responsáveis exibidos nos filtros</p>
                  <p className="mt-1 text-[11px] text-slate-500">Defina a fonte usada na lista de responsáveis do módulo.</p>
                </div>
                {canSyncIxc ? (
                  <Button type="button" variant="outline" size="sm" disabled={syncingDirectory} onClick={() => void syncResponsibleDirectory()}>
                    {syncingDirectory ? <Loader2 className="h-4 w-4 animate-spin" /> : <Users className="h-4 w-4" />}
                    Sincronizar colaboradores IXC
                  </Button>
                ) : null}
              </div>
              <div className="mt-3 grid gap-2 md:grid-cols-3" role="radiogroup" aria-label="Origem dos responsáveis">
                {([
                  ["orders", "Produção no período", "Mostra apenas quem possui O.S. no recorte."],
                  ["ixc", "Cadastro completo IXC", "Inclui colaboradores ainda sem produção."],
                  ["both", "Visão combinada", "Une cadastro IXC e responsáveis das O.S."],
                ] as const).map(([source, title, description]) => {
                  const selected = (data?.responsible_source || "orders") === source;
                  return <button key={source} type="button" role="radio" aria-checked={selected} disabled={!canManage} onClick={() => void changeResponsibleSource(source)} className={`rounded-lg border p-3 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 ${selected ? "border-blue-500 bg-blue-600 text-white shadow-sm" : "border-slate-200 bg-white text-slate-700 hover:border-blue-300 hover:bg-blue-50/40"}`}>
                    <span className="block text-xs font-semibold">{title}</span>
                    <span className={`mt-1 block text-[10px] leading-snug ${selected ? "text-blue-100" : "text-slate-500"}`}>{description}</span>
                  </button>;
                })}
              </div>
              <p className="w-full text-[10px] text-slate-500">
                {data?.ixc_collaborators_synced_at ? `Cadastro IXC atualizado em ${new Date(data.ixc_collaborators_synced_at).toLocaleString("pt-BR")}.` : "Sincronize o cadastro IXC para disponibilizar colaboradores sem O.S."}
              </p>
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <div className="relative">
                <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
                <Input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Buscar responsável"
                  className="pl-9"
                />
              </div>
              <select
                value={regional}
                onChange={(event) => setRegional(event.target.value)}
                className="h-10 rounded-md border bg-white px-3 text-sm"
              >
                <option value="">Todas as regionais</option>
                {regionals.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>
          </CardHeader>
          <CardContent className="max-h-[620px] overflow-auto p-0">
            <table className="w-full min-w-[500px] text-xs">
              <thead className="sticky top-0 z-10 bg-slate-100 text-left text-[10px] uppercase text-slate-500">
                <tr>
                  <th className="px-3 py-2">Responsável / regional</th>
                  <th className="px-3 py-2">Modelo de equipe</th>
                  <th className="w-8"></th>
                </tr>
              </thead>
              <tbody>
                {visibleMembers.map((member) => {
                  const key = member.responsible_name;
                  return (
                    <tr
                      key={key}
                      className="border-t odd:bg-white even:bg-slate-50/70"
                    >
                      <td className="px-3 py-2">
                        <p className="font-semibold text-slate-900">
                          {member.responsible_name}
                        </p>
                        <p className="text-[10px] text-slate-400">
                          {member.regionals.join(" · ")}
                        </p>
                      </td>
                      <td className="px-3 py-2">
                        <select
                          disabled={!canManage}
                          value={member.team_model_id || ""}
                          onChange={(event) =>
                            void assign(member, {
                              team_model_id: event.target.value
                                ? Number(event.target.value)
                                : null,
                            })
                          }
                          className="h-9 w-full rounded-md border bg-white px-2"
                        >
                          <option value="">Sem modelo</option>
                          {data?.models
                            .filter((model) => model.active)
                            .map((model) => (
                              <option key={model.id} value={model.id}>
                                {model.name} · {model.daily_target}/dia
                              </option>
                            ))}
                        </select>
                      </td>
                      <td>
                        {savingMember === key ? (
                          <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {!visibleMembers.length ? (
              <p className="py-12 text-center text-sm text-slate-500">
                Nenhum responsável encontrado.
              </p>
            ) : null}
          </CardContent>
          {filteredMembers.length ? (
            <div className="flex items-center justify-between gap-3 border-t bg-white px-3 py-2 text-xs text-slate-500">
              <span>
                {(memberPage - 1) * MEMBERS_PER_PAGE + 1}–
                {Math.min(
                  memberPage * MEMBERS_PER_PAGE,
                  filteredMembers.length,
                )}{" "}
                de {filteredMembers.length}
              </span>
              <div className="flex gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={memberPage <= 1}
                  onClick={() =>
                    setMemberPage((current) => Math.max(1, current - 1))
                  }
                >
                  Anterior
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={memberPage >= memberTotalPages}
                  onClick={() =>
                    setMemberPage((current) =>
                      Math.min(memberTotalPages, current + 1),
                    )
                  }
                >
                  Próxima
                </Button>
              </div>
            </div>
          ) : null}
        </Card>
        <Card
          className={`${section === "subjects" ? "block" : "hidden"} min-w-0 rounded-2xl border-slate-200`}
        >
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2 text-base">
              <Layers3 className="h-4 w-4 text-blue-600" /> Tipos gerais e
              assuntos
            </CardTitle>
            <p className="text-xs text-slate-500">
              Classifique os assuntos do IXC. A alteração é aplicada às O.S.
              históricas do módulo e às próximas importações.
            </p>
            <div className="mt-3 relative">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
              <Input
                value={subjectSearch}
                onChange={(event) => setSubjectSearch(event.target.value)}
                placeholder="Buscar assunto ou tipo geral"
                className="pl-9"
              />
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <div className="flex flex-wrap items-end gap-2 border-b bg-slate-50 p-3">
              <label className="grid min-w-64 flex-1 gap-1 text-[10px] font-semibold uppercase text-slate-500">
                Mover selecionados para
                <Input
                  list="operation-os-types"
                  value={targetOsType}
                  disabled={!canManageSubjects}
                  placeholder="Ex.: Manutenção"
                  onChange={(event) => setTargetOsType(event.target.value)}
                />
                <datalist id="operation-os-types">
                  {knownTypes.map((item) => (
                    <option key={item} value={item} />
                  ))}
                </datalist>
              </label>
              <Button
                type="button"
                disabled={
                  !canManageSubjects ||
                  !selectedSubjects.length ||
                  !targetOsType.trim() ||
                  savingSubjects
                }
                onClick={() => void saveSubjectClassification()}
              >
                {savingSubjects ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Tags className="h-4 w-4" />
                )}
                Classificar {selectedSubjects.length || ""}
              </Button>
            </div>
            <div className="max-h-[620px] overflow-auto">
              <table className="w-full min-w-[680px] text-xs">
                <thead className="sticky top-0 z-10 bg-slate-100 text-left text-[10px] uppercase text-slate-500">
                  <tr>
                    <th className="w-10 px-3 py-2">
                      <AppCheckbox
                        ariaLabel="Selecionar assuntos visíveis"
                        disabled={!canManageSubjects}
                        checked={
                          Boolean(filteredSubjects.length) &&
                          filteredSubjects.every((item) =>
                            selectedSubjects.includes(item.subject),
                          )
                        }
                        onCheckedChange={(checked) =>
                          setSelectedSubjects(
                            checked
                              ? filteredSubjects.map((item) => item.subject)
                              : [],
                          )
                        }
                      />
                    </th>
                    <th className="px-3 py-2">Assunto IXC</th>
                    <th className="px-3 py-2">Tipo geral</th>
                    <th className="px-3 py-2 text-right">O.S.</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredSubjects.map((item) => (
                    <tr
                      key={item.subject}
                      className={`border-t ${selectedSubjects.includes(item.subject) ? "bg-blue-50" : "odd:bg-white even:bg-slate-50/60"}`}
                    >
                      <td className="px-3 py-2">
                        <AppCheckbox
                          ariaLabel={`Selecionar ${item.subject}`}
                          disabled={!canManageSubjects}
                          checked={selectedSubjects.includes(item.subject)}
                          onCheckedChange={(checked) =>
                            setSelectedSubjects((current) =>
                              checked
                                ? [...current, item.subject]
                                : current.filter(
                                    (subject) => subject !== item.subject,
                                  ),
                            )
                          }
                        />
                      </td>
                      <td className="px-3 py-2 font-medium text-slate-900">
                        {item.subject}
                      </td>
                      <td className="px-3 py-2">
                        <Badge
                          className={
                            item.os_type === "Pendente de classificação"
                              ? "border-amber-200 bg-amber-50 text-amber-700"
                              : "border-slate-200 bg-white text-slate-700"
                          }
                        >
                          {item.os_type}
                        </Badge>
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {item.order_count}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!filteredSubjects.length ? (
                <p className="py-14 text-center text-sm text-slate-500">
                  Nenhum assunto encontrado.
                </p>
              ) : null}
            </div>
          </CardContent>
        </Card>
      </div>
      <Dialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => {
          if (!open && !deleting) setDeleteTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Excluir modelo de equipe?</DialogTitle>
            <DialogDescription>
              O modelo <strong>{deleteTarget?.name}</strong> será removido
              definitivamente. A exclusão será bloqueada se houver colaboradores
              vinculados.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={deleting}
              onClick={() => setDeleteTarget(null)}
            >
              Cancelar
            </Button>
            <Button
              type="button"
              className="bg-red-600 hover:bg-red-700"
              disabled={deleting}
              onClick={() => void deleteModel()}
            >
              {deleting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}{" "}
              Excluir definitivamente
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
