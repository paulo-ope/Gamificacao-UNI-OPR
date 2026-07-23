"use client";

import { Activity, AlertTriangle, ShieldAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { OperationSubjectVolumeAlerts } from "@/lib/operations-api";
import { cn } from "@/lib/utils";

const STATUS = {
  critical: { label: "Crítico", icon: ShieldAlert, className: "border-red-200 bg-red-50 text-red-700" },
  attention: { label: "Atenção", icon: AlertTriangle, className: "border-amber-200 bg-amber-50 text-amber-700" },
  normal: { label: "Normal", icon: Activity, className: "border-emerald-200 bg-emerald-50 text-emerald-700" },
  insufficient: { label: "Histórico insuficiente", icon: Activity, className: "border-slate-200 bg-slate-50 text-slate-600" }
};

function number(value: number) {
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(value);
}

export function OperationsVolumeAlerts({ data, isLoading }: { data: OperationSubjectVolumeAlerts; isLoading: boolean }) {
  if (isLoading && !data.items.length) return <div className="h-72 animate-pulse rounded-2xl border bg-white" aria-label="Carregando alertas de volume" />;
  const visible = data.items.slice(0, 8);
  return (
    <Card className="rounded-2xl border-slate-200 shadow-sm">
      <CardHeader className="flex-row items-start justify-between gap-4">
        <div>
          <p className="text-[9px] font-bold uppercase tracking-[0.18em] text-blue-600">Monitor de desvio</p>
          <CardTitle className="mt-1 text-base font-semibold text-slate-950">Backlog fora do padrão por assunto</CardTitle>
          <p className="mt-1 text-[11px] text-slate-500">Compara o estoque atual com os {data.baseline_days} dias anteriores. O filtro de responsável não altera este indicador operacional.</p>
        </div>
        <Badge className="shrink-0 border-blue-200 bg-blue-50 text-blue-700">Base operacional</Badge>
      </CardHeader>
      <CardContent className="px-0 pb-0">
        {visible.length ? <div className="divide-y divide-slate-100 border-t border-slate-100">
          {visible.map((item) => {
            const status = STATUS[item.status];
            const Icon = status.icon;
            return <div key={item.subject} className="grid gap-2 px-4 py-3 sm:grid-cols-[minmax(0,1fr)_auto_auto_auto] sm:items-center">
              <div className="min-w-0"><p className="break-words text-sm font-medium text-slate-800">{item.subject}</p><p className="text-[10px] text-slate-400">Média recente: {number(item.recent_average)}</p></div>
              <div className="flex items-baseline justify-between gap-2 sm:block sm:min-w-20 sm:text-right"><span className="text-[9px] uppercase text-slate-400">Atual</span><p className="font-semibold tabular-nums text-slate-950">{item.current_backlog}</p></div>
              <div className="flex items-baseline justify-between gap-2 sm:block sm:min-w-20 sm:text-right"><span className="text-[9px] uppercase text-slate-400">Esperado</span><p className="font-semibold tabular-nums text-slate-700">{number(item.expected_backlog)}</p></div>
              <Badge className={cn("w-fit gap-1", status.className)}><Icon className="h-3 w-3" />{status.label}{item.status !== "normal" && item.status !== "insufficient" && item.deviation_percentage !== null && item.deviation_percentage > 0 ? ` +${number(item.deviation_percentage)}%` : ""}</Badge>
            </div>;
          })}
        </div> : <div className="border-t border-slate-100 px-6 py-12 text-center"><Activity className="mx-auto h-8 w-8 text-slate-300" /><p className="mt-2 text-sm font-medium text-slate-700">Sem desvios mensuráveis</p><p className="text-xs text-slate-500">A base ainda não possui assuntos suficientes neste recorte.</p></div>}
      </CardContent>
    </Card>
  );
}
