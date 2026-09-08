"use client";

import { useEffect, useState } from "react";

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { schedulingApi, type SchedulingOrderTimeline } from "@/lib/scheduling-api";

import { formatPortoVelho } from "./scheduling-format";

function eventTypeTone(eventType: string) {
  switch (eventType) {
    case "5":
      return { dot: "bg-blue-600", accent: "border-l-blue-500", badge: "border-blue-200 bg-blue-50 text-blue-700" };
    case "10":
      return { dot: "bg-amber-500", accent: "border-l-amber-500", badge: "border-amber-200 bg-amber-50 text-amber-700" };
    case "6":
      return { dot: "bg-emerald-600", accent: "border-l-emerald-500", badge: "border-emerald-200 bg-emerald-50 text-emerald-700" };
    default:
      return { dot: "bg-slate-400", accent: "border-l-slate-300", badge: "border-slate-200 bg-slate-100 text-slate-600" };
  }
}

// Mesmo padrão do detalhamento de O.S. da Operação Analítica
// (`components/operations/operations-order-detail-dialog.tsx`): `Dialog` compartilhado, aberto
// como camada extra por cima de um Sheet de drilldown (mesma composição, um logo após o outro no
// JSX - funciona sem ajuste de z-index porque o portal montado depois empata e vence no empilhamento).
export function OrderTimelinePanel({ ixcOsId, onClose }: { ixcOsId: number; onClose: () => void }) {
  const [data, setData] = useState<SchedulingOrderTimeline | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    schedulingApi
      .orderTimeline(ixcOsId, controller.signal)
      .then(setData)
      .catch((reason) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Falha ao carregar o log da O.S.");
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [ixcOsId]);

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Log completo — O.S. {ixcOsId}</DialogTitle>
          <DialogDescription>{data ? `${data.filial} · ${data.setor} · ${data.assunto}` : "Carregando..."}</DialogDescription>
        </DialogHeader>
        {error ? <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p> : null}
        {loading ? (
          <div className="h-64 animate-pulse rounded-xl bg-slate-100" />
        ) : data ? (
          <ol className="relative space-y-3 border-l-2 border-slate-100 pl-5">
            {data.events.map((event, index) => {
              const tone = eventTypeTone(event.event_type);
              return (
              <li key={index} className="relative">
                <span className={`absolute -left-[27px] top-3 h-3 w-3 rounded-full ring-4 ring-white ${tone.dot}`} />
                <div className={`rounded-xl border border-slate-100 border-l-4 ${tone.accent} bg-white p-3 shadow-sm`}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${tone.badge}`}>
                      {event.event_label}
                    </span>
                    <p className="text-xs text-slate-500">{formatPortoVelho(event.event_at)}</p>
                  </div>
                  {event.window_start ? (
                    <p className="mt-1.5 text-xs text-slate-500">
                      Janela: {formatPortoVelho(event.window_start)}
                      {event.window_end ? ` até ${formatPortoVelho(event.window_end)}` : ""}
                    </p>
                  ) : null}
                  {event.operator_name || event.technician_name ? (
                    <p className="mt-1 text-xs text-slate-600">
                      {event.operator_name ? <>Operador: <span className="font-medium text-slate-700">{event.operator_name}</span></> : null}
                      {event.operator_name && event.technician_name ? " · " : ""}
                      {event.technician_name ? <>Técnico: <span className="font-medium text-slate-700">{event.technician_name}</span></> : null}
                    </p>
                  ) : null}
                  {event.mensagem ? (
                    <p className="mt-2 whitespace-pre-wrap rounded-lg bg-slate-50 px-2.5 py-2 text-xs text-slate-700">
                      {event.mensagem}
                    </p>
                  ) : null}
                  {event.historico ? (
                    <p className="mt-1.5 text-xs italic text-slate-400">{event.historico}</p>
                  ) : null}
                </div>
              </li>
              );
            })}
            {!data.events.length ? (
              <p className="text-sm text-slate-500">Nenhum evento sincronizado para esta O.S.</p>
            ) : null}
          </ol>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
