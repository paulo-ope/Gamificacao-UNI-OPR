"use client";

import { ClipboardCheck, Info, Save, Search, Settings2, X } from "lucide-react";
import { useMemo, useState } from "react";

import { AppCombobox, AppInput, StatusBadge } from "@/components/gamification/config-ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatInteger, formatMoney } from "@/lib/format";
import type { DiagnosisActionType, ImportedDiagnosis } from "@/lib/types";

function severityTone(serviceOrdersCount: number): "danger" | "warning" | "neutral" {
  if (serviceOrdersCount >= 50) return "danger";
  if (serviceOrdersCount >= 10) return "warning";
  return "neutral";
}

type Props = {
  diagnoses: ImportedDiagnosis[];
  onConfigureDiagnosis: (
    diagnosisName: string,
    payload: DiagnosisConfigurePayload
  ) => Promise<void>;
  onConfigureDiagnoses: (items: Array<{ diagnosisName: string; payload: DiagnosisConfigurePayload }>) => Promise<void>;
};

type DiagnosisDraft = {
  action_type: DiagnosisActionType;
  penalty_points: number;
  force_points_value: number | null;
};

type DiagnosisConfigurePayload = DiagnosisDraft & {
  active: boolean;
  description: string;
};

const defaultDraft: DiagnosisDraft = { action_type: "requires_review", penalty_points: 0, force_points_value: null };

export function UnmappedDiagnosesPanel({ diagnoses, onConfigureDiagnosis, onConfigureDiagnoses }: Props) {
  const [query, setQuery] = useState("");
  const [drafts, setDrafts] = useState<Record<string, DiagnosisDraft>>({});
  const [bulkAction, setBulkAction] = useState<DiagnosisActionType>("requires_review");
  const [bulkPoints, setBulkPoints] = useState("0");

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    const base = normalized
      ? diagnoses.filter((item) =>
          [item.diagnosis_name, item.predominant_regional, ...item.related_subjects].some((value) =>
            value.toLowerCase().includes(normalized)
          )
        )
      : diagnoses;
    return [...base].sort((a, b) => b.service_orders_count - a.service_orders_count);
  }, [diagnoses, query]);

  function draft(item: ImportedDiagnosis) {
    return drafts[item.diagnosis_name] ?? defaultDraft;
  }

  const selectedItems = useMemo(
    () =>
      diagnoses
        .filter((item) => drafts[item.diagnosis_name])
        .map((item) => {
          const currentDraft = drafts[item.diagnosis_name]!;
          return {
            diagnosisName: item.diagnosis_name,
            payload: toPayload(item.diagnosis_name, currentDraft)
          };
        }),
    [diagnoses, drafts]
  );

  function toPayload(diagnosisName: string, currentDraft: DiagnosisDraft): DiagnosisConfigurePayload {
    return {
      ...currentDraft,
      active: true,
      description: `Regra criada a partir do diagnóstico sem regra ${diagnosisName}.`
    };
  }

  function buildDraft(actionType: DiagnosisActionType, rawPoints: string): DiagnosisDraft {
    const points = rawPoints === "" ? 0 : Number(rawPoints);
    return {
      action_type: actionType,
      penalty_points: actionType === "force_points" ? 0 : points,
      force_points_value: actionType === "force_points" ? points : null
    };
  }

  function updateDraft(item: ImportedDiagnosis, patch: Partial<DiagnosisDraft>) {
    setDrafts({ ...drafts, [item.diagnosis_name]: { ...draft(item), ...patch } });
  }

  function applyBulkDiagnosisToFiltered() {
    const next = { ...drafts };
    for (const item of filtered) {
      next[item.diagnosis_name] = buildDraft(bulkAction, bulkPoints);
    }
    setDrafts(next);
  }

  async function saveBulkDiagnoses() {
    if (!selectedItems.length) return;
    await onConfigureDiagnoses(selectedItems);
    setDrafts({});
  }

  return (
    <section className="panel overflow-hidden">
      <div className="panel-header bg-slate-50/70">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-amber-200 bg-white text-amber-700">
            <ClipboardCheck className="h-5 w-5" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="panel-title">Diagnósticos sem regra</h2>
              <Badge className="border-amber-200 bg-amber-50 text-amber-700">
                {formatInteger(diagnoses.length)} item(ns)
              </Badge>
            </div>
            <p className="panel-subtitle">Fila de diagnósticos importados que ainda não possuem regra de liberação ou anulação.</p>
          </div>
        </div>
        <div className="flex w-full flex-col gap-2 sm:w-96">
          <Label htmlFor="diagnosis-unmapped-search">Buscar diagnóstico</Label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <AppInput
              id="diagnosis-unmapped-search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="pl-9"
              placeholder="Diagnóstico, assunto ou regional"
            />
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 border-b bg-amber-50 px-5 py-3 text-sm text-amber-800">
        <Info className="h-4 w-4 shrink-0" />
        Defina se o diagnóstico libera, anula ou exige revisão antes de recalcular a apuração.
      </div>

      <div className="grid gap-3 border-b bg-white px-5 py-4 lg:grid-cols-[minmax(180px,1fr)_160px_auto_auto_auto] lg:items-end">
        <div className="grid gap-2">
          <Label>Ação para aplicar aos filtrados</Label>
          <AppCombobox
            value={bulkAction}
            onChange={(value) => setBulkAction(value as DiagnosisActionType)}
            placeholder="Selecionar ação"
            ariaLabel="Ação para aplicar aos diagnósticos filtrados"
            options={[
              { value: "subtract_points", label: "Subtrair pontos" },
              { value: "cancel_points", label: "Anular pontos" },
              { value: "no_penalty", label: "Sem anulação" },
              { value: "requires_review", label: "Revisão manual" },
              { value: "force_points", label: "Forçar pontos" },
            ]}
          />
        </div>
        <div className="grid gap-2">
          <Label>Pontos</Label>
          <AppInput type="number" value={bulkPoints} onChange={(event) => setBulkPoints(event.target.value)} />
        </div>
        <Button variant="outline" onClick={applyBulkDiagnosisToFiltered} disabled={filtered.length === 0}>
          Aplicar aos filtrados
        </Button>
        <Button onClick={saveBulkDiagnoses} disabled={selectedItems.length === 0}>
          <Save className="h-4 w-4" />
          Salvar {formatInteger(selectedItems.length)} regra(s)
        </Button>
        <Button variant="ghost" onClick={() => setDrafts({})} disabled={selectedItems.length === 0}>
          <X className="h-4 w-4" />
          Limpar seleção
        </Button>
      </div>

      <div className="border-b bg-slate-50 px-5 py-2 text-xs font-medium uppercase tracking-wide text-slate-500">
        {selectedItems.length > 0
          ? `${formatInteger(selectedItems.length)} diagnóstico(s) selecionado(s) para salvar em massa.`
          : "Ajuste diagnósticos nas linhas ou aplique uma ação aos filtrados antes de salvar."}
      </div>

      <div className="table-frame">
        <Table>
        <TableHeader className="sticky top-0 z-10 bg-slate-900 text-white shadow-sm [&_th]:text-slate-200">
          <TableRow className="border-slate-700 hover:bg-slate-900">
            <TableHead>Diagnóstico</TableHead>
            <TableHead>Qtd O.S</TableHead>
            <TableHead>Assuntos relacionados</TableHead>
            <TableHead>Colaboradores</TableHead>
            <TableHead>Regional</TableHead>
            <TableHead>Impacto potencial</TableHead>
            <TableHead>Ação</TableHead>
            <TableHead>Pontos</TableHead>
            <TableHead>Configurar</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {filtered.length === 0 ? (
            <TableRow>
              <TableCell colSpan={9} className="h-28 text-center text-sm text-slate-500">
                Nenhum diagnóstico sem regra encontrado para os filtros atuais.
              </TableCell>
            </TableRow>
          ) : null}
          {filtered.map((item) => {
            const currentDraft = draft(item);
            return (
              <TableRow key={item.diagnosis_name}>
                <TableCell className="min-w-56">
                  <div className="font-medium text-slate-950">{item.diagnosis_name}</div>
                  <StatusBadge tone="warning" className="mt-1">Sem regra</StatusBadge>
                </TableCell>
                <TableCell>
                  <StatusBadge tone={severityTone(item.service_orders_count)}>{formatInteger(item.service_orders_count)}</StatusBadge>
                </TableCell>
                <TableCell className="min-w-80 text-xs text-slate-600">{item.related_subjects.join(" | ") || "-"}</TableCell>
                <TableCell>{formatInteger(item.collaborators_count)}</TableCell>
                <TableCell>{item.predominant_regional}</TableCell>
                <TableCell className="font-medium text-uni-royal">{formatMoney(item.estimated_impact)}</TableCell>
                <TableCell className="min-w-48">
                  <AppCombobox
                    value={currentDraft.action_type}
                    onChange={(value) => updateDraft(item, { action_type: value as DiagnosisActionType })}
                    placeholder="Selecionar ação"
                    ariaLabel={`Ação para o diagnóstico ${item.diagnosis_name}`}
                    options={[
                      { value: "subtract_points", label: "Subtrair pontos" },
                      { value: "cancel_points", label: "Anular pontos" },
                      { value: "no_penalty", label: "Sem anulação" },
                      { value: "requires_review", label: "Revisão manual" },
                      { value: "force_points", label: "Forçar pontos" },
                    ]}
                  />
                </TableCell>
                <TableCell className="w-32">
                  <AppInput
                    type="number"
                    value={currentDraft.action_type === "force_points" ? currentDraft.force_points_value ?? "" : currentDraft.penalty_points}
                    onChange={(event) =>
                      updateDraft(
                        item,
                        currentDraft.action_type === "force_points"
                          ? { force_points_value: event.target.value === "" ? null : Number(event.target.value) }
                          : { penalty_points: Number(event.target.value) }
                      )
                    }
                  />
                </TableCell>
                <TableCell>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      onConfigureDiagnosis(item.diagnosis_name, toPayload(item.diagnosis_name, currentDraft))
                    }
                  >
                    <Settings2 className="h-4 w-4" />
                    Configurar regra
                  </Button>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
        </Table>
      </div>
    </section>
  );
}



