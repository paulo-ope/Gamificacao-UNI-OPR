"use client";

import type { Dispatch, SetStateAction } from "react";
import { Save } from "lucide-react";

import { AppCombobox, DataTableFrame, FilterToolbar, ToolbarCount } from "@/components/gamification/config-ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatInteger, formatMoney } from "@/lib/format";
import { numericInputValue, parseNumericInput } from "@/lib/numeric-input";
import type { DiagnosisActionType, ImportedDiagnosis } from "@/lib/types";
import { actionLabel, diagnosisPointsFieldState } from "@/components/gamification/logic-configuration-helpers";
import type { DiagnosisFilter } from "@/components/gamification/logic-configuration-helpers";

type DiagnosisDraft = {
  action_type: DiagnosisActionType;
  penalty_points: number;
  force_points_value: number | null;
  active: boolean;
  description: string;
};

type Props = {
  diagnosisFilter: DiagnosisFilter;
  setDiagnosisFilter: Dispatch<SetStateAction<DiagnosisFilter>>;
  diagnosisRows: ImportedDiagnosis[];
  visibleDiagnosisRowsCount: number;
  setVisibleDiagnosisRowsCount: Dispatch<SetStateAction<number>>;
  diagnosisDraft: (item: ImportedDiagnosis) => DiagnosisDraft;
  updateDiagnosisDraft: (item: ImportedDiagnosis, patch: Partial<DiagnosisDraft>) => void;
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
};

export function DiagnosesSection({
  diagnosisFilter,
  setDiagnosisFilter,
  diagnosisRows,
  visibleDiagnosisRowsCount,
  setVisibleDiagnosisRowsCount,
  diagnosisDraft,
  updateDiagnosisDraft,
  onSaveDiagnosisRule
}: Props) {
  return (
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
            const value =
              draft.action_type === "force_points" ? draft.force_points_value ?? "" : numericInputValue(draft.penalty_points);
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
                          : { penalty_points: parseNumericInput(event.target.value) }
                      )
                    }
                  />
                  <div className="mt-1 text-xs text-slate-500">{pointsField.helper}</div>
                </TableCell>
                <TableCell className="font-medium text-uni-royal">{formatMoney(item.estimated_impact)}</TableCell>
                <TableCell>
                  <Badge className={item.has_rule ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-amber-200 bg-amber-50 text-amber-800"}>
                    {item.has_rule ? "Configurado" : "Sem regra"}
                  </Badge>
                </TableCell>
                <TableCell>
                  <Button
                    variant="default"
                    size="sm"
                    onClick={() =>
                      onSaveDiagnosisRule(item.diagnosis_name, item.rule_id, {
                        ...draft,
                        // Pode estar vazio (NaN) se o usuário limpou o campo pra digitar
                        // de novo - nunca mandar isso pra API.
                        penalty_points: Number.isFinite(draft.penalty_points) ? draft.penalty_points : 0,
                      })
                    }
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
  );
}
