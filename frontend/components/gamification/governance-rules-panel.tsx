"use client";

import { Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { HealthRule } from "@/lib/types";

type Props = {
  pointValue: string;
  setPointValue: (value: string) => void;
  localSettings: Record<string, string>;
  setLocalSettings: (value: Record<string, string>) => void;
  healthRules: HealthRule[];
  setHealthRules: (value: HealthRule[]) => void;
  onSavePointValue: () => Promise<void>;
  onSaveSetting: (patch: Record<string, string>) => Promise<void>;
  onSaveHealthRule: (rule: HealthRule) => Promise<void>;
  showHealthRules?: boolean;
};

function replaceById<T extends { id: number }>(items: T[], id: number, patch: Partial<T>) {
  return items.map((item) => (item.id === id ? { ...item, ...patch } : item));
}

function settingValue(settings: Record<string, string>, key: string) {
  return settings[key] ?? "";
}

function optionalNumberSettingValue(settings: Record<string, string>, key: string) {
  const value = settingValue(settings, key).trim();
  return ["0", "0.0", "0.00"].includes(value) ? "" : value;
}

export function GovernanceRulesPanel({
  pointValue,
  setPointValue,
  localSettings,
  setLocalSettings,
  healthRules,
  setHealthRules,
  onSavePointValue,
  onSaveSetting,
  onSaveHealthRule,
  showHealthRules = true
}: Props) {
  const hasActiveHealthRule = healthRules.some((rule) => rule.active);

  function updateLocalSetting(key: string, value: string) {
    setLocalSettings({ ...localSettings, [key]: value });
  }

  return (
    <section className="rounded-[24px] border border-slate-200 bg-white shadow-[0_10px_40px_rgba(15,23,42,0.05)]">
      <div className="panel-header">
        <div>
          <h2 className="panel-title">Governança da Apuração</h2>
          <p className="panel-subtitle">
            Primeiro ajuste o que manda no fechamento: valor do ponto, janela de reincidência e multiplicadores.
          </p>
        </div>
      </div>

      <div className="grid gap-4 border-t p-5 lg:grid-cols-4">
        <div className="grid gap-2">
          <Label htmlFor="point-value">Valor global do ponto</Label>
          <div className="flex gap-2">
            <Input
              id="point-value"
              inputMode="decimal"
              value={pointValue}
              onChange={(event) => setPointValue(event.target.value)}
              placeholder="Buscar do backend"
            />
            <Button variant="outline" size="icon" onClick={onSavePointValue} aria-label="Salvar valor do ponto">
              <Save className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="grid gap-2">
          <Label>Janela de reincidência (dias)</Label>
          <Input
            inputMode="numeric"
            value={settingValue(localSettings, "recurrence_window_days")}
            onChange={(event) => updateLocalSetting("recurrence_window_days", event.target.value)}
            onBlur={(event) => onSaveSetting({ recurrence_window_days: event.target.value })}
            placeholder="Ex.: 30"
          />
        </div>

        <div className="grid gap-2">
          <Label>Ação quando confirmar reincidência</Label>
          <select
            className="h-10 rounded-md border border-input bg-white px-3 text-sm"
            value={settingValue(localSettings, "recurrence_action")}
            onChange={(event) => {
              updateLocalSetting("recurrence_action", event.target.value);
              onSaveSetting({ recurrence_action: event.target.value });
            }}
          >
            <option value="">Usar backend</option>
            <option value="annul_original">Anular O.S origem</option>
            <option value="subtract_original">Anular pontos fixos</option>
            <option value="requires_review">Exigir revisão manual</option>
            <option value="no_penalty">Não anular</option>
          </select>
        </div>

        <div className="grid gap-2">
          <Label>Pontos fixos se anular</Label>
          <Input
            inputMode="decimal"
            value={optionalNumberSettingValue(localSettings, "recurrence_penalty_points")}
            onChange={(event) => updateLocalSetting("recurrence_penalty_points", event.target.value)}
            onBlur={(event) => onSaveSetting({ recurrence_penalty_points: event.target.value })}
            placeholder="Ex.: 10"
          />
        </div>
      </div>

      {showHealthRules ? (
      <div className="border-t p-5">
        <div className="mb-3">
          <h3 className="text-sm font-semibold text-slate-950">Multiplicadores de saúde operacional</h3>
          <p className="text-xs text-slate-500">
            O sistema calcula a saúde por regional: % de O.S dentro do SLA e % de reincidências. A regra ativa que bater nesses limites define o multiplicador aplicado nos pontos líquidos do colaborador.
          </p>
        </div>
        <div className="mb-3 grid gap-2 rounded-2xl border border-blue-100 bg-blue-50 p-4 text-xs text-slate-700 md:grid-cols-3">
          <div>
            <span className="font-semibold text-slate-950">SLA min.</span> e o percentual mínimo de O.S no prazo para a regional entrar nessa saúde.
          </div>
          <div>
            <span className="font-semibold text-slate-950">Reinc. max.</span> e o limite máximo de reincidências aceito na regional.
          </div>
          <div>
            <span className="font-semibold text-slate-950">Multiplicador</span> entra depois dos pontos líquidos: pontos líquidos x multiplicador = pontos finais.
          </div>
        </div>
        {!hasActiveHealthRule ? (
          <div className="mb-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs font-medium text-amber-800">
            Nenhuma regra de saúde está ativa. Enquanto isso, o ranking usa multiplicador neutro 1.00x.
          </div>
        ) : null}
        <div className="overflow-hidden rounded-2xl border border-slate-200">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Saúde</TableHead>
                <TableHead>SLA min.</TableHead>
                <TableHead>Reinc. max.</TableHead>
                <TableHead>Multiplicador</TableHead>
                <TableHead>Ativa</TableHead>
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
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-teal-700"
                      checked={rule.active}
                      onChange={(event) => setHealthRules(replaceById(healthRules, rule.id, { active: event.target.checked }))}
                    />
                  </TableCell>
                  <TableCell>
                    <Button variant="outline" size="sm" onClick={() => onSaveHealthRule(rule)}>
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
      ) : null}
    </section>
  );
}


