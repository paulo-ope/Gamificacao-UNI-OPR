"use client";

import { Badge } from "@/components/ui/badge";
import { IxcSyncSettingsCard } from "@/components/workspace/ixc-sync-settings-card";
import type { OperationIxcSyncSettings } from "@/lib/operations-api";

type Props = {
  ixcSyncSettings: OperationIxcSyncSettings | null;
  canEditIxcSync: boolean;
  saving: boolean;
  onSaveIxcSyncSettings: (patch: Partial<Omit<OperationIxcSyncSettings, "available_sectors" | "sector_scope_label">>) => void;
  onOpenAiGovernance: () => void;
};

export function IntegrationsPanel({ ixcSyncSettings, canEditIxcSync, saving, onSaveIxcSyncSettings, onOpenAiGovernance }: Props) {
  return (
    <div className="grid gap-4">
      <div className="rounded-3xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 p-5">
          <h3 className="text-lg font-semibold text-slate-950">Sincronização com o IXC</h3>
          <p className="mt-1 text-sm text-slate-500">
            Regras de tempo de sincronização e escopo de setores usadas pela Operação Analítica.
          </p>
        </div>
        <div className="p-5">
          <IxcSyncSettingsCard settings={ixcSyncSettings} canEdit={canEditIxcSync} saving={saving} onSave={onSaveIxcSyncSettings} />
        </div>
      </div>

      <div className="rounded-3xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 p-5">
          <h3 className="text-lg font-semibold text-slate-950">Outras integrações</h3>
        </div>
        <div className="grid gap-3 p-5 md:grid-cols-2">
          <div className="rounded-2xl border border-slate-200 p-4">
            <h4 className="font-semibold text-slate-950">API interna</h4>
            <p className="mt-2 text-sm text-slate-600">Fonte própria para dados não sensíveis</p>
            <Badge className="mt-3 border border-slate-200 bg-white text-slate-600">Ainda não implementado</Badge>
          </div>
          <button
            type="button"
            onClick={onOpenAiGovernance}
            className="rounded-2xl border border-slate-200 p-4 text-left transition hover:border-slate-300 hover:bg-slate-50"
          >
            <h4 className="font-semibold text-slate-950">IA (API/MCP)</h4>
            <p className="mt-2 text-sm text-slate-600">Endpoints, campos, perfis, tokens e logs governados pela aba Gestão API/MCP</p>
            <Badge className="mt-3 border border-emerald-200 bg-emerald-50 text-emerald-700">Abrir Gestão API/MCP</Badge>
          </button>
        </div>
      </div>
    </div>
  );
}
