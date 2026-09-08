"use client";

import { CheckCircle2, ChevronDown, Loader2, RefreshCcw, XCircle } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { StatusToast } from "@/components/ui/status-toast";
import { schedulingApi, type SchedulingSyncHealth, type SchedulingSyncStatus } from "@/lib/scheduling-api";

import { formatPortoVelho, number } from "./scheduling-format";

// View "Sincronização" do menu do módulo - mesmo padrão de painel fixo (não modal) das outras
// visões do cockpit. O loop automático incremental já roda sozinho
// (`app/modules/scheduling/scheduler.py`); esta view só existe para alguém CONFIRMAR que está tudo
// bem, ou forçar uma sincronização/backfill manual quando precisar.
export function SchedulingSyncPanel({
  health,
  status,
  canSync,
  onSynced,
}: {
  health: SchedulingSyncHealth | null;
  status: SchedulingSyncStatus | null;
  canSync: boolean;
  onSynced: () => void;
}) {
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [backfillOpen, setBackfillOpen] = useState(false);
  const [backfillFrom, setBackfillFrom] = useState("");
  const [backfillTo, setBackfillTo] = useState("");

  async function runSync(dateFrom?: string, dateTo?: string) {
    setSyncing(true);
    setError(null);
    setMessage(null);
    try {
      let job = await schedulingApi.startSync(dateFrom, dateTo);
      while (job.status === "pending" || job.status === "running") {
        await new Promise((resolve) => window.setTimeout(resolve, 2000));
        const next = await schedulingApi.syncStatus();
        if (next.last_job && next.last_job.id === job.id) job = next.last_job;
      }
      if (job.status === "failed") throw new Error(job.error || "Falha ao sincronizar com o IXC.");
      setMessage("Sincronização concluída.");
      onSynced();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao sincronizar com o IXC.");
    } finally {
      setSyncing(false);
    }
  }

  const hasWatermark = Boolean(status?.watermark);
  const healthy = (health?.consecutive_failures ?? 0) === 0;

  return (
    <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
      <CardHeader className="pb-2">
        <CardTitle className="text-base font-semibold text-slate-950">Sincronização com o IXC</CardTitle>
        <p className="text-xs text-slate-500">Histórico de reagendamento importado de `su_oss_chamado_mensagem`, atualizado automaticamente.</p>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        <StatusToast error={error} message={message} onDismissError={() => setError(null)} onDismissMessage={() => setMessage(null)} />

        <div className={`flex items-start gap-2 rounded-xl border p-3 ${healthy ? "border-emerald-100 bg-emerald-50" : "border-red-100 bg-red-50"}`}>
          {healthy ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" /> : <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" />}
          <div className="text-xs">
            {!health?.configured ? (
              <p className="text-slate-600">Integração com o IXC não configurada neste ambiente.</p>
            ) : healthy ? (
              <p className="text-emerald-800">
                Sincronização automática funcionando{health.enabled ? ` (a cada ${health.interval_minutes} min)` : " (desligada)"}.
                {health.last_success_at ? ` Último sucesso: ${formatPortoVelho(health.last_success_at)}.` : ""}
              </p>
            ) : (
              <p className="text-red-800">
                {health.consecutive_failures} falha(s) consecutiva(s) na sincronização automática.
                {health.last_error ? ` Último erro: ${health.last_error}` : ""}
                {health.last_error_at ? ` (${formatPortoVelho(health.last_error_at)})` : ""}
              </p>
            )}
          </div>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-600 sm:grid-cols-3">
          <p>Marca d&apos;água: <span className="font-medium text-slate-900">{status?.watermark ? formatPortoVelho(status.watermark) : "nenhuma ainda"}</span></p>
          <p>O.S. sincronizadas: <span className="font-medium text-slate-900">{number(status?.orders_count)}</span></p>
          <p>Eventos sincronizados: <span className="font-medium text-slate-900">{number(status?.events_count)}</span></p>
        </div>

        {canSync ? (
          <div className="mt-4 space-y-2">
            <Button type="button" onClick={() => void runSync()} disabled={syncing || !hasWatermark}>
              {syncing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />}
              {syncing ? "Sincronizando..." : "Sincronizar agora"}
            </Button>
            {!hasWatermark ? (
              <p className="text-[11px] text-amber-700">
                Sem marca d&apos;água ainda - rode um backfill por período abaixo antes da sincronização incremental funcionar.
              </p>
            ) : null}
            <button
              type="button"
              onClick={() => setBackfillOpen((current) => !current)}
              className="flex w-full max-w-sm items-center justify-between rounded-lg px-1 py-1 text-left text-xs font-medium text-slate-600 hover:text-slate-900"
            >
              Backfill por período (carga inicial ou correção)
              <ChevronDown className={`h-3.5 w-3.5 transition ${backfillOpen ? "rotate-180" : ""}`} />
            </button>
            {backfillOpen ? (
              <div className="max-w-sm rounded-lg border border-slate-100 bg-slate-50 p-3">
                <div className="grid grid-cols-2 gap-2">
                  <label className="block text-xs text-slate-600">
                    De
                    <Input type="date" value={backfillFrom} onChange={(event) => setBackfillFrom(event.target.value)} className="mt-1" />
                  </label>
                  <label className="block text-xs text-slate-600">
                    Até
                    <Input type="date" value={backfillTo} onChange={(event) => setBackfillTo(event.target.value)} className="mt-1" />
                  </label>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="mt-2 w-full"
                  disabled={syncing || !backfillFrom || !backfillTo}
                  onClick={() => void runSync(backfillFrom, backfillTo)}
                >
                  {syncing ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Rodar backfill do período
                </Button>
              </div>
            ) : null}
          </div>
        ) : (
          <p className="mt-4 text-[11px] text-slate-400">Seu perfil não tem permissão para disparar sincronização manual.</p>
        )}
      </CardContent>
    </Card>
  );
}
