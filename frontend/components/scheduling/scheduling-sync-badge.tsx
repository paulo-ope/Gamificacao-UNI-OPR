"use client";

import { Loader2 } from "lucide-react";

import type { SchedulingSyncHealth } from "@/lib/scheduling-api";

// Mesmo padrão do indicador de sincronização do SGP Suporte (`SyncStatusIndicator` em
// app/suporte/page.tsx) - badge discreto no subcabeçalho, nunca competindo com o título da view;
// clicar leva para a view "Sincronização" do menu do módulo.
export function SchedulingSyncBadge({
  health,
  syncing,
  onOpenSync,
}: {
  health: SchedulingSyncHealth | null;
  syncing: boolean;
  onOpenSync: () => void;
}) {
  if (!health) return null;
  const hasError = !health.configured ? false : health.consecutive_failures > 0;
  const label = !health.configured
    ? "IXC não configurado"
    : hasError
      ? "Sincronização com erro"
      : syncing
        ? "Sincronizando"
        : health.enabled
          ? "Sincronização automática ativa"
          : "Sincronização automática desligada";
  const tone = hasError
    ? "border-red-200 bg-red-50 text-red-700"
    : syncing
      ? "border-blue-200 bg-blue-50 text-blue-700"
      : "border-slate-200 bg-slate-50 text-slate-600";

  return (
    <button
      type="button"
      onClick={onOpenSync}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors hover:opacity-80 ${tone}`}
      title="Abrir a visão de sincronização"
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${hasError ? "bg-red-500" : syncing ? "bg-blue-500" : health.enabled ? "bg-emerald-500" : "bg-slate-400"}`}
        aria-hidden="true"
      />
      {syncing ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
      {label}
    </button>
  );
}
