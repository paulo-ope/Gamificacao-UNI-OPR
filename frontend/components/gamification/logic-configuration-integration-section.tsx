"use client";

import type { Dispatch, SetStateAction } from "react";

import { AppSwitch } from "@/components/gamification/config-ui";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { StatusBadge } from "@/components/ui/status-badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { CpkRegionalSnapshot } from "@/lib/types";
import {
  CPK_BONUS_POINTS_KEY,
  CPK_STATUS_LABEL,
  CPK_SYNC_ENABLED_KEY,
  IXC_SYNC_AUTO_RECALCULATE_KEY,
  IXC_SYNC_ENABLED_KEY,
  IXC_SYNC_INTERVAL_MINUTES_KEY,
} from "@/components/gamification/logic-configuration-helpers";

type Props = {
  localSettings: Record<string, string>;
  setLocalSettings: Dispatch<SetStateAction<Record<string, string>>>;
  saveSettings: (patch: Record<string, string>) => Promise<void>;
  cpkPeriod: { year: number; month: number };
  setCpkPeriod: Dispatch<SetStateAction<{ year: number; month: number }>>;
  cpkSyncing: boolean;
  syncCpk: () => Promise<void>;
  cpkSnapshotRows: CpkRegionalSnapshot[];
};

export function IntegrationSection({
  localSettings,
  setLocalSettings,
  saveSettings,
  cpkPeriod,
  setCpkPeriod,
  cpkSyncing,
  syncCpk,
  cpkSnapshotRows
}: Props) {
  return (
    <>
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

    <section className="rounded-[24px] border border-slate-200 bg-white shadow-[0_10px_40px_rgba(15,23,42,0.05)]">
      <div className="panel-header">
        <div>
          <h3 className="panel-title">Integração CPK</h3>
          <p className="panel-subtitle">
            Ajusta o multiplicador de saúde da regional com base no indicador de Custo Por Km (CPK) da frota:
            bônus quando a regional está na meta, penalidade quando está fora.
          </p>
        </div>
      </div>
      <div className="grid gap-4 p-5 md:grid-cols-2">
        <div className="grid gap-2">
          <Label>Sincronização automática</Label>
          <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
            <AppSwitch
              checked={(localSettings[CPK_SYNC_ENABLED_KEY] ?? "false") === "true"}
              onCheckedChange={(checked) => {
                const value = checked ? "true" : "false";
                setLocalSettings({ ...localSettings, [CPK_SYNC_ENABLED_KEY]: value });
                void saveSettings({ [CPK_SYNC_ENABLED_KEY]: value });
              }}
            />
            <span className="text-sm text-slate-700">
              {(localSettings[CPK_SYNC_ENABLED_KEY] ?? "false") === "true" ? "Ligada" : "Desligada"}
            </span>
          </div>
        </div>
        <div className="grid gap-2">
          <Label>Bônus/penalidade no multiplicador (pontos)</Label>
          <Input
            inputMode="decimal"
            value={localSettings[CPK_BONUS_POINTS_KEY] ?? ""}
            onChange={(event) => setLocalSettings({ ...localSettings, [CPK_BONUS_POINTS_KEY]: event.target.value })}
            onBlur={(event) => saveSettings({ [CPK_BONUS_POINTS_KEY]: event.target.value })}
            placeholder="Ex.: 0.2"
          />
        </div>
        <div className="grid gap-2">
          <Label>Ano de referência</Label>
          <Input
            inputMode="numeric"
            value={cpkPeriod.year}
            onChange={(event) => setCpkPeriod({ ...cpkPeriod, year: Number(event.target.value) || cpkPeriod.year })}
          />
        </div>
        <div className="grid gap-2">
          <Label>Mês de referência</Label>
          <Input
            inputMode="numeric"
            value={cpkPeriod.month}
            onChange={(event) => setCpkPeriod({ ...cpkPeriod, month: Number(event.target.value) || cpkPeriod.month })}
          />
        </div>
        <div className="md:col-span-2">
          <Button variant="outline" onClick={() => void syncCpk()} disabled={cpkSyncing}>
            {cpkSyncing ? "Sincronizando..." : "Sincronizar agora"}
          </Button>
        </div>
        <div className="md:col-span-2">
          <p className="text-xs text-slate-500 mb-2">
            Último snapshot sincronizado por regional para o período selecionado - confira os números antes de
            confiar neles. Um mês ainda em andamento (não fechado pela frota) sempre aparece como "Sem base".
          </p>
          {cpkSnapshotRows.length === 0 ? (
            <EmptyState
              title="Nenhum snapshot sincronizado"
              description='Clique em "Sincronizar agora" para buscar os dados de CPK desse período.'
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Regional</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>CPK realizado</TableHead>
                  <TableHead>CPK meta</TableHead>
                  <TableHead>Mês fechado</TableHead>
                  <TableHead>Sincronizado em</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cpkSnapshotRows.map((row) => (
                  <TableRow key={row.regional}>
                    <TableCell>{row.regional}</TableCell>
                    <TableCell>
                      <StatusBadge tone={row.status === "na_meta" ? "emerald" : row.status === "fora_meta" ? "red" : "slate"}>
                        {CPK_STATUS_LABEL[row.status] ?? row.status}
                      </StatusBadge>
                    </TableCell>
                    <TableCell>{row.cpk_realizado ?? "-"}</TableCell>
                    <TableCell>{row.cpk_meta ?? "-"}</TableCell>
                    <TableCell>{row.mes_fechado ? "Sim" : "Não"}</TableCell>
                    <TableCell>{new Date(row.synced_at).toLocaleString("pt-BR")}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      </div>
    </section>
    </>
  );
}
