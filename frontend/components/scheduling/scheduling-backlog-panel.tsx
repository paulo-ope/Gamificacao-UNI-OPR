"use client";

import dynamic from "next/dynamic";
import { Inbox } from "lucide-react";
import { useEffect, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { schedulingApi, type SchedulingBacklogBreakdown, type SchedulingBacklogItem, type SchedulingBucket, type SchedulingFilterState } from "@/lib/scheduling-api";

import { rankingOption } from "./scheduling-day-breakdown-charts";
import { formatPortoVelho, hoursLabel } from "./scheduling-format";

const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => <div className="h-[160px] animate-pulse rounded-xl bg-slate-100" aria-label="Carregando gráfico" />,
});

// Fila de trabalho (O.S. sem agendamento) - análise secundária do cockpit, separada do resumo de
// hoje: é uma fila CORRENTE (idade da O.S.), não um recorte por dia como os reagendamentos. Como
// essas O.S. ainda não têm técnico/operador atribuído, a dimensão "quem" não existe - filial/
// assunto é a quebra que sobra pra responder "onde agir" (pedido do usuário 2026-08-31: "essa
// fila de trabalho faz sentido desse formato... o que que faz mais sentido?").
export function SchedulingBacklogPanel({
  backlogAging,
  backlog,
  filters,
  onOpenBucket,
}: {
  backlogAging: SchedulingBucket[];
  backlog: SchedulingBacklogItem[];
  filters: SchedulingFilterState;
  onOpenBucket: (bucket: string, label: string, count: number) => void;
}) {
  const [breakdown, setBreakdown] = useState<SchedulingBacklogBreakdown | null>(null);
  const [breakdownLoading, setBreakdownLoading] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setBreakdownLoading(true);
    schedulingApi
      .backlogBreakdown(filters, controller.signal)
      .then(setBreakdown)
      .catch((reason) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
      })
      .finally(() => setBreakdownLoading(false));
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.date_from, filters.date_to, filters.filial_ids, filters.setor_ids, filters.assunto_ids]);

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
          <CardHeader className="pb-1">
            <CardTitle className="text-sm font-semibold text-slate-950">Filiais — mais O.S. sem agendamento</CardTitle>
          </CardHeader>
          <CardContent className="px-3 pb-3">
            {breakdownLoading ? (
              <div className="h-40 animate-pulse rounded-xl bg-slate-100" />
            ) : breakdown?.by_filial.length ? (
              <ReactECharts option={rankingOption(breakdown.by_filial, "#2563eb")} notMerge lazyUpdate style={{ height: Math.max(120, breakdown.by_filial.length * 28), width: "100%" }} />
            ) : (
              <p className="py-6 text-center text-xs text-slate-400">Fila zerada no recorte selecionado.</p>
            )}
          </CardContent>
        </Card>
        <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
          <CardHeader className="pb-1">
            <CardTitle className="text-sm font-semibold text-slate-950">Assuntos — mais O.S. sem agendamento</CardTitle>
          </CardHeader>
          <CardContent className="px-3 pb-3">
            {breakdownLoading ? (
              <div className="h-40 animate-pulse rounded-xl bg-slate-100" />
            ) : breakdown?.by_assunto.length ? (
              <ReactECharts option={rankingOption(breakdown.by_assunto, "#eb6834")} notMerge lazyUpdate style={{ height: Math.max(120, breakdown.by_assunto.length * 28), width: "100%" }} />
            ) : (
              <p className="py-6 text-center text-xs text-slate-400">Fila zerada no recorte selecionado.</p>
            )}
          </CardContent>
        </Card>
      </div>
      <div className="grid gap-4 xl:grid-cols-[0.6fr_1.4fr]">
      <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base font-semibold text-slate-950">
            <Inbox className="h-4 w-4 text-blue-600" /> Envelhecimento da fila
          </CardTitle>
          <p className="text-xs text-slate-500">O.S. abertas no período ainda sem nenhum agendamento.</p>
        </CardHeader>
        <CardContent className="space-y-2 px-4 pb-4">
          {backlogAging.map((bucket) => (
            <button
              key={bucket.bucket}
              type="button"
              disabled={!bucket.count}
              onClick={() => onOpenBucket(bucket.bucket, bucket.label, bucket.count)}
              className="flex w-full items-center justify-between rounded-lg border border-slate-100 px-3 py-2 text-left transition enabled:hover:border-blue-200 enabled:hover:bg-blue-50 disabled:cursor-default"
            >
              <span className="text-sm text-slate-700">{bucket.label}</span>
              <span className={`text-sm font-semibold tabular-nums ${bucket.bucket === "acima_7_dias" && bucket.count > 0 ? "text-red-600" : "text-slate-900"}`}>
                {bucket.count}
              </span>
            </button>
          ))}
        </CardContent>
      </Card>
      <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-semibold text-slate-950">Fila de trabalho — mais antigas primeiro</CardTitle>
          <p className="text-xs text-slate-500">É a lista de ação do dia: O.S. sem agendamento, da mais antiga para a mais nova.</p>
        </CardHeader>
        <CardContent className="px-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>O.S.</TableHead>
                <TableHead>Aberta em</TableHead>
                <TableHead className="text-right">Espera</TableHead>
                <TableHead>Filial</TableHead>
                <TableHead>Assunto</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {backlog.slice(0, 15).map((item) => (
                <TableRow key={item.ixc_os_id} className="odd:bg-slate-50/60">
                  <TableCell className="font-medium text-slate-800">{item.ixc_os_id}</TableCell>
                  <TableCell>{formatPortoVelho(item.opened_at)}</TableCell>
                  <TableCell className={`text-right tabular-nums ${item.age_hours > 72 ? "font-semibold text-red-600" : ""}`}>{hoursLabel(item.age_hours)}</TableCell>
                  <TableCell className="max-w-44 truncate">{item.filial}</TableCell>
                  <TableCell className="max-w-56 truncate">{item.assunto}</TableCell>
                </TableRow>
              ))}
              {!backlog.length ? (
                <TableRow>
                  <TableCell colSpan={5} className="py-8 text-center text-sm text-slate-500">Fila zerada no recorte selecionado. 🎉</TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
          {backlog.length > 15 ? <p className="px-4 py-2 text-xs text-slate-400">Mostrando 15 de {backlog.length} O.S. pendentes.</p> : null}
        </CardContent>
      </Card>
      </div>
    </div>
  );
}
