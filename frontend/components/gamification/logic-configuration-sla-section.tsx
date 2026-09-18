"use client";

import type { Dispatch, SetStateAction } from "react";
import { Save } from "lucide-react";

import { AppCombobox, AppSwitch } from "@/components/gamification/config-ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AppCheckbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { numericInputValue, parseNumericInput } from "@/lib/numeric-input";
import type { HealthRule, SlaPenaltyRule, SlaPenaltyType } from "@/lib/types";
import { HEALTH_BELOW_MINIMUM_MULTIPLIER_SETTING, replaceById, slaValueFieldState } from "@/components/gamification/logic-configuration-helpers";

type Props = {
  slaRules: SlaPenaltyRule[];
  setSlaRules: (rules: SlaPenaltyRule[]) => void;
  filteredSlaRules: SlaPenaltyRule[];
  onCreateSlaRule: () => Promise<void>;
  onSaveSlaRule: (rule: SlaPenaltyRule) => Promise<void>;
  healthRules: HealthRule[];
  setHealthRules: (rules: HealthRule[]) => void;
  saveHealthRule: (rule: HealthRule) => Promise<void>;
  localSettings: Record<string, string>;
  setLocalSettings: Dispatch<SetStateAction<Record<string, string>>>;
  saveSettings: (patch: Record<string, string>) => Promise<void>;
};

export function SlaSection({
  slaRules,
  setSlaRules,
  filteredSlaRules,
  onCreateSlaRule,
  onSaveSlaRule,
  healthRules,
  setHealthRules,
  saveHealthRule,
  localSettings,
  setLocalSettings,
  saveSettings
}: Props) {
  return (
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
                  value={valueField.editable ? numericInputValue(rule.penalty_value) : ""}
                  disabled={!valueField.editable}
                  placeholder={valueField.editable ? undefined : "N/A"}
                  onChange={(event) => setSlaRules(replaceById(slaRules, rule.id, { penalty_value: parseNumericInput(event.target.value) }))}
                />
                <div className="mt-1 text-xs text-slate-500">{valueField.helper}</div>
              </TableCell>
              <TableCell>
                <Button
                  variant="default"
                  size="sm"
                  onClick={() =>
                    onSaveSlaRule({
                      ...rule,
                      // Pode estar vazio (NaN) se o usuário limpou o campo pra digitar de
                      // novo - nunca mandar isso pra API.
                      penalty_value: Number.isFinite(rule.penalty_value) ? rule.penalty_value : 0,
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
                      <AppCheckbox
                        checked={rule.active}
                        onCheckedChange={(checked) => setHealthRules(replaceById(healthRules, rule.id, { active: checked }))}
                        ariaLabel="Usar faixa"
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
                    value={localSettings[HEALTH_BELOW_MINIMUM_MULTIPLIER_SETTING] ?? ""}
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
  );
}
