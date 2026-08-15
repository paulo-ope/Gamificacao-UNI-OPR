"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { MultiSelect } from "@/components/ui/multi-select";
import { AppSwitch } from "@/components/gamification/config-ui";
import type { OperationIxcSyncSettings } from "@/lib/operations-api";

type IxcSyncSettingsPatch = Partial<Omit<OperationIxcSyncSettings, "available_sectors" | "sector_scope_label">>;

export function IxcSyncSettingsCard({
  settings,
  canEdit,
  saving,
  onSave,
}: {
  settings: OperationIxcSyncSettings | null;
  canEdit: boolean;
  saving: boolean;
  onSave: (patch: IxcSyncSettingsPatch) => Promise<void> | void;
}) {
  const [enabled, setEnabled] = useState(settings?.enabled ?? false);
  const [intervalMinutes, setIntervalMinutes] = useState(String(settings?.interval_minutes ?? 20));
  const [backlogIntervalMinutes, setBacklogIntervalMinutes] = useState(String(settings?.backlog_sweep_interval_minutes ?? 60));
  const [lookbackDays, setLookbackDays] = useState(String(settings?.lookback_days ?? 1));
  const [sectorIds, setSectorIds] = useState<string[]>(settings?.sector_ids ?? []);
  // Monitoramento de rede (status de login/sinal ONU) - loops independentes do sync de O.S.
  // acima, pedido do usuário em 2026-08-15 pra poder desligar quando não estiver acompanhando
  // incidentes, mantendo só a sincronização de O.S. rodando.
  const [loginStatusEnabled, setLoginStatusEnabled] = useState(settings?.login_status_enabled ?? true);
  const [onuSignalEnabled, setOnuSignalEnabled] = useState(settings?.onu_signal_enabled ?? true);
  const [loginStatusIntervalMinutes, setLoginStatusIntervalMinutes] = useState(String(settings?.login_status_interval_minutes ?? 5));
  const [onuSignalIntervalMinutes, setOnuSignalIntervalMinutes] = useState(String(settings?.onu_signal_interval_minutes ?? 15));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!settings) return;
    setEnabled(settings.enabled);
    setIntervalMinutes(String(settings.interval_minutes));
    setBacklogIntervalMinutes(String(settings.backlog_sweep_interval_minutes));
    setLookbackDays(String(settings.lookback_days));
    setSectorIds(settings.sector_ids);
    setLoginStatusEnabled(settings.login_status_enabled);
    setOnuSignalEnabled(settings.onu_signal_enabled);
    setLoginStatusIntervalMinutes(String(settings.login_status_interval_minutes));
    setOnuSignalIntervalMinutes(String(settings.onu_signal_interval_minutes));
  }, [settings]);

  if (!settings) {
    return (
      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
        Seu perfil não possui a permissão operations:sync_ixc para ver esta configuração.
      </div>
    );
  }

  async function submit() {
    const interval = Number(intervalMinutes);
    const backlog = Number(backlogIntervalMinutes);
    const lookback = Number(lookbackDays);
    const loginStatusInterval = Number(loginStatusIntervalMinutes);
    const onuSignalInterval = Number(onuSignalIntervalMinutes);
    if (!Number.isInteger(interval) || interval < 5 || interval > 1440) {
      setError("Intervalo de sincronização deve ser um número entre 5 e 1440 minutos.");
      return;
    }
    if (!Number.isInteger(backlog) || backlog < 15 || backlog > 1440) {
      setError("Varredura de backlog deve ser um número entre 15 e 1440 minutos.");
      return;
    }
    if (!Number.isInteger(lookback) || lookback < 1 || lookback > 30) {
      setError("Janela de reimportação deve ser um número entre 1 e 30 dias.");
      return;
    }
    if (!Number.isInteger(loginStatusInterval) || loginStatusInterval < 2 || loginStatusInterval > 120) {
      setError("Intervalo de status de login deve ser um número entre 2 e 120 minutos.");
      return;
    }
    if (!Number.isInteger(onuSignalInterval) || onuSignalInterval < 5 || onuSignalInterval > 180) {
      setError("Intervalo de sinal ONU deve ser um número entre 5 e 180 minutos.");
      return;
    }
    setError(null);
    await onSave({
      enabled,
      interval_minutes: interval,
      backlog_sweep_interval_minutes: backlog,
      lookback_days: lookback,
      sector_ids: sectorIds,
      login_status_enabled: loginStatusEnabled,
      onu_signal_enabled: onuSignalEnabled,
      login_status_interval_minutes: loginStatusInterval,
      onu_signal_interval_minutes: onuSignalInterval,
    });
  }

  const sectorOptions = settings.available_sectors.map((sector) => sector.id);
  const sectorLabel = (id: string) => settings.available_sectors.find((sector) => sector.id === id)?.name ?? id;

  return (
    <div className="grid gap-4">
      <div className="flex items-center gap-3">
        <AppSwitch checked={enabled} onCheckedChange={canEdit ? setEnabled : () => {}} label={enabled ? "Sincronização ativa" : "Sincronização desativada"} />
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="grid gap-1">
          <Label className="text-xs text-slate-500">Intervalo de sincronização (min)</Label>
          <Input value={intervalMinutes} onChange={(event) => setIntervalMinutes(event.target.value)} disabled={!canEdit} />
        </div>
        <div className="grid gap-1">
          <Label className="text-xs text-slate-500">Varredura de backlog (min)</Label>
          <Input value={backlogIntervalMinutes} onChange={(event) => setBacklogIntervalMinutes(event.target.value)} disabled={!canEdit} />
        </div>
        <div className="grid gap-1">
          <Label className="text-xs text-slate-500">Janela de reimportação (dias)</Label>
          <Input value={lookbackDays} onChange={(event) => setLookbackDays(event.target.value)} disabled={!canEdit} />
        </div>
      </div>

      <div className="grid gap-3 rounded-2xl border border-slate-200 p-3 sm:grid-cols-2">
        <div className="grid gap-2">
          <div className="flex items-center gap-3">
            <AppSwitch
              checked={loginStatusEnabled}
              onCheckedChange={canEdit ? setLoginStatusEnabled : () => {}}
              label="Status de login"
            />
          </div>
          <div className="grid gap-1">
            <Label className="text-xs text-slate-500">Intervalo (min)</Label>
            <Input
              value={loginStatusIntervalMinutes}
              onChange={(event) => setLoginStatusIntervalMinutes(event.target.value)}
              disabled={!canEdit}
            />
          </div>
        </div>
        <div className="grid gap-2">
          <div className="flex items-center gap-3">
            <AppSwitch
              checked={onuSignalEnabled}
              onCheckedChange={canEdit ? setOnuSignalEnabled : () => {}}
              label="Sinal ONU/PON"
            />
          </div>
          <div className="grid gap-1">
            <Label className="text-xs text-slate-500">Intervalo (min)</Label>
            <Input
              value={onuSignalIntervalMinutes}
              onChange={(event) => setOnuSignalIntervalMinutes(event.target.value)}
              disabled={!canEdit}
            />
          </div>
        </div>
        <p className="text-xs text-slate-400 sm:col-span-2">
          Loops independentes da sincronização de O.S. acima - desligue quando não estiver
          acompanhando incidentes de rede.
        </p>
      </div>

      <div className="grid gap-1">
        <Label className="text-xs text-slate-500">Setores sincronizados</Label>
        <MultiSelect
          values={sectorIds}
          options={sectorOptions}
          ariaLabel="Setores IXC sincronizados"
          formatOption={sectorLabel}
          onChange={canEdit ? setSectorIds : () => {}}
        />
        <p className="text-xs text-slate-400">Escopo atual: {settings.sector_scope_label}</p>
      </div>

      {error ? <p className="text-xs text-red-600">{error}</p> : null}

      {canEdit ? (
        <div>
          <Button type="button" size="sm" disabled={saving} onClick={() => void submit()}>
            Salvar
          </Button>
        </div>
      ) : null}
    </div>
  );
}
