"use client";

import type { Dispatch, SetStateAction } from "react";
import { Save, Trash2 } from "lucide-react";

import { AppCombobox } from "@/components/gamification/config-ui";
import { configCardClass, configSoftCardClass } from "@/components/gamification/config-ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AppCheckbox } from "@/components/ui/checkbox";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { numericInputValue, parseNumericInput } from "@/lib/numeric-input";
import { cn } from "@/lib/utils";
import type { RecurrenceClassificationRule } from "@/lib/types";
import {
  SearchableMultiSelect,
  classificationSupportsDiscount,
  recurrenceActionLabel,
  recurrenceClassificationLabel,
  recurrenceIdentityFields,
  replaceById,
  toggleIdentityField,
} from "@/components/gamification/logic-configuration-helpers";
import type { ConfigSection, RecurrenceClassificationValue, SearchOption } from "@/components/gamification/logic-configuration-helpers";

type Props = {
  localSettings: Record<string, string>;
  setLocalSettings: Dispatch<SetStateAction<Record<string, string>>>;
  saveSettings: (patch: Record<string, string>) => Promise<void>;
  setConfigSection: Dispatch<SetStateAction<ConfigSection>>;
  newRecurrenceRule: Partial<RecurrenceClassificationRule>;
  setNewRecurrenceRule: Dispatch<SetStateAction<Partial<RecurrenceClassificationRule>>>;
  createRecurrenceRule: () => Promise<void>;
  osTypeOptions: string[];
  subjectOptions: SearchOption[];
  diagnosisOptions: SearchOption[];
  filteredRecurrenceRules: RecurrenceClassificationRule[];
  recurrenceRules: RecurrenceClassificationRule[];
  setRecurrenceRules: (rules: RecurrenceClassificationRule[]) => void;
  onSaveRecurrenceRule: (rule: RecurrenceClassificationRule) => Promise<void>;
  onDeleteRecurrenceRule: (rule: RecurrenceClassificationRule) => Promise<void>;
};

export function RecurrenceSection({
  localSettings,
  setLocalSettings,
  saveSettings,
  setConfigSection,
  newRecurrenceRule,
  setNewRecurrenceRule,
  createRecurrenceRule,
  osTypeOptions,
  subjectOptions,
  diagnosisOptions,
  filteredRecurrenceRules,
  recurrenceRules,
  setRecurrenceRules,
  onSaveRecurrenceRule,
  onDeleteRecurrenceRule
}: Props) {
  return (
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
            <div className="mb-2 flex h-6 w-6 items-center justify-center rounded-full bg-uni-royal text-xs font-semibold text-white">{step}</div>
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
                    <AppCheckbox
                      checked={recurrenceIdentityFields(localSettings).includes(field)}
                      disabled={field === "cpf_cnpj"}
                      onCheckedChange={(checked) => {
                        const value = toggleIdentityField(localSettings, field, checked);
                        setLocalSettings({ ...localSettings, recurrence_identity_fields: value });
                        saveSettings({ recurrence_identity_fields: value });
                      }}
                      ariaLabel={label}
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
                  <AppCheckbox
                    checked={Boolean(newRecurrenceRule.discount_points)}
                    disabled={!classificationSupportsDiscount(newRecurrenceRule.classification ?? "reincidencia_tecnica")}
                    onCheckedChange={(checked) => setNewRecurrenceRule({ ...newRecurrenceRule, discount_points: checked })}
                    ariaLabel="Pode anular a O.S original"
                  />
                  Pode anular a O.S original
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <AppCheckbox
                    checked={Boolean(newRecurrenceRule.require_same_subject)}
                    onCheckedChange={(checked) => setNewRecurrenceRule({ ...newRecurrenceRule, require_same_subject: checked })}
                    ariaLabel="Exigir mesmo assunto"
                  />
                  Exigir mesmo assunto
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <AppCheckbox
                    checked={Boolean(newRecurrenceRule.require_same_diagnosis)}
                    onCheckedChange={(checked) => setNewRecurrenceRule({ ...newRecurrenceRule, require_same_diagnosis: checked })}
                    ariaLabel="Exigir mesmo diagnóstico"
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
                    value={numericInputValue(newRecurrenceRule.priority ?? 100)}
                    onChange={(event) => setNewRecurrenceRule({ ...newRecurrenceRule, priority: parseNumericInput(event.target.value) })}
                  />
                  <p className="text-[11px] text-slate-500">Regras com prioridade menor são conferidas primeiro quando mais de uma bate com a mesma O.S.</p>
                </div>
                <div className="grid gap-2">
                  <Label>Intervalo mínimo</Label>
                  <div className="flex items-center gap-2">
                    <Input
                      inputMode="numeric"
                      className="w-28"
                      value={newRecurrenceRule.min_hours_between ?? ""}
                      placeholder="Sem mínimo"
                      onChange={(event) =>
                        setNewRecurrenceRule({
                          ...newRecurrenceRule,
                          min_hours_between: event.target.value === "" ? null : Number(event.target.value)
                        })
                      }
                    />
                    <span className="text-xs text-slate-500">horas</span>
                  </div>
                  <p className="text-[11px] text-slate-500">Só conta como reincidência se a O.S posterior abrir pelo menos essas horas depois da original.</p>
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
                  <Badge className="border-blue-200 bg-blue-50 text-uni-royal">{recurrenceClassificationLabel(rule.classification)}</Badge>
                  <Badge className={rule.discount_points ? "border-red-200 bg-red-50 text-red-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}>
                    {rule.discount_points ? "Anula O.S original" : "Apenas sinaliza"}
                  </Badge>
                  <Badge className="border-slate-200 bg-white text-slate-700">Janela: {rule.max_days ?? localSettings.recurrence_window_days ?? "30"} dias</Badge>
                  {rule.min_hours_between != null ? (
                    <Badge className="border-slate-200 bg-white text-slate-700">Mínimo: {rule.min_hours_between}h</Badge>
                  ) : null}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="default"
                  size="sm"
                  onClick={() =>
                    // Prioridade pode estar vazia (NaN) se o usuário limpou pra digitar de
                    // novo - nunca mandar isso pra API, cai em 100 (mesmo padrão de antes).
                    onSaveRecurrenceRule({
                      ...rule,
                      priority: Number.isFinite(rule.priority) ? rule.priority : 100,
                    })
                  }
                >
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
                <div className="grid grid-cols-3 gap-2">
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
                    <Label>Intervalo mínimo</Label>
                    <div className="flex items-center gap-2">
                      <Input
                        inputMode="numeric"
                        value={rule.min_hours_between ?? ""}
                        placeholder="Sem mínimo"
                        onChange={(event) =>
                          setRecurrenceRules(
                            replaceById(recurrenceRules, rule.id, {
                              min_hours_between: event.target.value === "" ? null : Number(event.target.value)
                            })
                          )
                        }
                      />
                      <span className="text-xs text-slate-500">horas</span>
                    </div>
                  </div>
                  <div className="grid gap-2">
                    <Label>Prioridade</Label>
                    <Input
                      type="number"
                      value={numericInputValue(rule.priority ?? 100)}
                      onChange={(event) =>
                        setRecurrenceRules(replaceById(recurrenceRules, rule.id, { priority: parseNumericInput(event.target.value) }))
                      }
                    />
                  </div>
                </div>
                <p className="text-[11px] text-slate-500">
                  Intervalo mínimo: só conta como reincidência se a O.S posterior abrir pelo menos essas horas depois da original (evita marcar visitas quase simultâneas).
                </p>
                <label
                  className={cn(
                    "flex items-start gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-3 text-xs leading-snug",
                    classificationSupportsDiscount(rule.classification) ? "text-slate-700" : "text-slate-400"
                  )}
                >
                  <AppCheckbox
                    className="mt-0.5"
                    checked={rule.discount_points}
                    disabled={!classificationSupportsDiscount(rule.classification)}
                    onCheckedChange={(checked) =>
                      setRecurrenceRules(replaceById(recurrenceRules, rule.id, { discount_points: checked }))
                    }
                    ariaLabel="Anula pontuação da O.S original"
                  />
                  <span>
                    {rule.discount_points ? "Anula pontuação da O.S original" : "Apenas sinaliza reincidência"}
                    {!classificationSupportsDiscount(rule.classification) ? " - este subtipo não anula pontos, marcação sem efeito." : ""}
                  </span>
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <label className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-700">
                    <AppCheckbox
                      checked={rule.require_same_subject}
                      onCheckedChange={(checked) =>
                        setRecurrenceRules(replaceById(recurrenceRules, rule.id, { require_same_subject: checked }))
                      }
                      ariaLabel="Exigir mesmo assunto"
                    />
                    Exigir mesmo assunto
                  </label>
                  <label className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-700">
                    <AppCheckbox
                      checked={rule.require_same_diagnosis}
                      onCheckedChange={(checked) =>
                        setRecurrenceRules(replaceById(recurrenceRules, rule.id, { require_same_diagnosis: checked }))
                      }
                      ariaLabel="Exigir mesmo diagnóstico"
                    />
                    Exigir mesmo diagnóstico
                  </label>
                </div>
                <label className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-700">
                  <AppCheckbox
                    checked={rule.active}
                    onCheckedChange={(checked) => setRecurrenceRules(replaceById(recurrenceRules, rule.id, { active: checked }))}
                    ariaLabel="Regra ativa"
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
  );
}
