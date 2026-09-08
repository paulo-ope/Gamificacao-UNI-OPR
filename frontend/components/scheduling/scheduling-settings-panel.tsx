"use client";

import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { StatusToast } from "@/components/ui/status-toast";
import { schedulingApi } from "@/lib/scheduling-api";

const SETTINGS_FIELDS: Array<{ key: string; label: string; helper: string; type: "number" | "time" | "text" }> = [
  { key: "scheduling_sla_target_pct", label: "Meta do SLA (%)", helper: "Percentual mínimo de O.S. agendadas dentro do prazo.", type: "number" },
  { key: "scheduling_sla_minutes", label: "Prazo do SLA (minutos úteis)", helper: "Ex.: 60 = agendar em até 1 hora útil.", type: "number" },
  { key: "scheduling_business_start", label: "Início do expediente", helper: "Hora em que o setor começa a operar.", type: "time" },
  { key: "scheduling_business_end", label: "Fim do expediente", helper: "Hora em que o setor encerra.", type: "time" },
  { key: "scheduling_business_days", label: "Dias ativos (0=seg ... 6=dom)", helper: "Separados por vírgula. Todos os dias: 0,1,2,3,4,5,6", type: "text" },
  { key: "scheduling_daily_goal", label: "Meta diária por operador", helper: "Ações de agendamento esperadas por membro da equipe por dia.", type: "number" },
];

// View "Configurações" do menu do módulo - mesmo padrão de painel fixo (não modal) das outras
// visões do cockpit (Hoje/Rankings/Fila/Desempenho), trocado pelo `SchedulingModuleSidebar`.
export function SchedulingSettingsPanel({ onSaved }: { onSaved: () => void }) {
  const [values, setValues] = useState<Record<string, string> | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [backfilling, setBackfilling] = useState(false);
  const [backfillMessage, setBackfillMessage] = useState<string | null>(null);

  useEffect(() => {
    void schedulingApi.settings().then(setValues).catch(() => setError("Falha ao carregar as configurações."));
    void schedulingApi.messagesBackfillStatus().then((job) => {
      if (job?.status === "completed") {
        setBackfillMessage(`Última busca: ${job.result?.events_updated ?? 0} eventos atualizados com o texto da mensagem.`);
      }
    }).catch(() => undefined);
  }, []);

  async function save() {
    if (!values) return;
    setSaving(true);
    setError(null);
    try {
      await schedulingApi.updateSettings(values);
      onSaved();
      setMessage("Configurações salvas.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao salvar.");
    } finally {
      setSaving(false);
    }
  }

  async function runMessagesBackfill() {
    setBackfilling(true);
    setBackfillMessage(null);
    setError(null);
    try {
      let job = await schedulingApi.startMessagesBackfill();
      while (job.status === "pending" || job.status === "running") {
        await new Promise((resolve) => window.setTimeout(resolve, 2000));
        const status = await schedulingApi.messagesBackfillStatus();
        if (status) job = status;
      }
      if (job.status === "failed") throw new Error(job.error || "Falha ao buscar mensagens no IXC.");
      setBackfillMessage(`Concluído: ${job.result?.events_updated ?? 0} eventos atualizados com o texto da mensagem.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao buscar mensagens no IXC.");
    } finally {
      setBackfilling(false);
    }
  }

  return (
    <div className="space-y-4">
      <StatusToast error={error} message={message} onDismissError={() => setError(null)} onDismissMessage={() => setMessage(null)} />
      <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-semibold text-slate-950">Configurações do módulo</CardTitle>
          <p className="text-xs text-slate-500">SLA, expediente e meta diária usados em todos os cálculos do cockpit.</p>
        </CardHeader>
        <CardContent className="px-4 pb-4">
          {values ? (
            <div className="grid gap-3 sm:grid-cols-2">
              {SETTINGS_FIELDS.map((field) => (
                <label key={field.key} className="block">
                  <span className="text-xs font-medium text-slate-600">{field.label}</span>
                  <Input
                    type={field.type}
                    value={values[field.key] ?? ""}
                    onChange={(event) => setValues((current) => ({ ...(current || {}), [field.key]: event.target.value }))}
                    className="mt-1"
                  />
                  <span className="mt-0.5 block text-[11px] text-slate-400">{field.helper}</span>
                </label>
              ))}
            </div>
          ) : (
            <div className="h-40 animate-pulse rounded-xl bg-slate-100" />
          )}
          <div className="mt-4 flex justify-end">
            <Button type="button" onClick={() => void save()} disabled={saving || !values}>
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Salvar
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-semibold text-slate-950">Mensagens antigas do IXC</CardTitle>
          <p className="text-xs text-slate-500">
            Busca no IXC o texto da mensagem/histórico dos eventos sincronizados antes desse recurso existir. Eventos novos já chegam com o texto pelo sync normal.
          </p>
        </CardHeader>
        <CardContent className="px-4 pb-4">
          {backfillMessage ? <p className="mb-2 text-[11px] text-emerald-700">{backfillMessage}</p> : null}
          <Button type="button" size="sm" variant="outline" onClick={() => void runMessagesBackfill()} disabled={backfilling}>
            {backfilling ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Buscar mensagens antigas
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
