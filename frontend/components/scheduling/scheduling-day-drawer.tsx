"use client";

import { CalendarDays, ChevronDown, Clock, ExternalLink, MapPin, Tag } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { schedulingApi, type SchedulingFilterState, type SchedulingRescheduleDayPage } from "@/lib/scheduling-api";

import { DrillPagination } from "./scheduling-drill-header";
import { DRILL_PAGE_SIZE, formatTimePortoVelho } from "./scheduling-format";
import { OrderTimelinePanel } from "./scheduling-order-timeline-panel";

// Fila do dia - drilldown central do cockpit: pedido do usuário em 2026-08-31 pra transformar a
// tela num painel operacional de supervisor ("o que preciso cobrar hoje"), com o calendário mensal
// como interação principal. Este drawer é aberto ao clicar num dia do calendário
// (`SchedulingMonthCalendar`) e lista TODO reagendamento (evento tipo 10) daquele dia, com o
// colaborador completo (operador + se é da equipe + técnico) e o texto que ele registrou.
export function SchedulingDayDrawer({
  day,
  filters,
  onClose,
}: {
  day: string;
  filters: SchedulingFilterState;
  onClose: () => void;
}) {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<SchedulingRescheduleDayPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [timelineOsId, setTimelineOsId] = useState<number | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  function toggleExpanded(index: number) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setExpanded(new Set());
    schedulingApi
      .reschedulesByDay(day, filters, page, DRILL_PAGE_SIZE, controller.signal)
      .then(setData)
      .catch((reason) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Falha ao carregar os reagendamentos do dia.");
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [day, page, filters.date_from, filters.date_to, filters.filial_ids, filters.setor_ids, filters.assunto_ids, filters.operator_ids, filters.technician_ids]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const dayLabel = day.split("-").reverse().join("/");

  return (
    <>
      <Sheet open onOpenChange={(open) => !open && onClose()}>
        <SheetContent className="flex w-full flex-col sm:max-w-[min(1400px,96vw)]">
          <SheetHeader className="border-b border-slate-100 bg-gradient-to-br from-slate-50 to-white">
            <SheetTitle className="flex items-center gap-2 text-lg">
              <CalendarDays className="h-4 w-4 text-blue-600" /> Reagendamentos de {dayLabel}
            </SheetTitle>
            <SheetDescription>
              {data ? `${new Intl.NumberFormat("pt-BR").format(data.total)} reagendamento(s) neste dia` : "Carregando..."} · recorte de filtros atual aplicado.
            </SheetDescription>
          </SheetHeader>
          <div className="flex-1 overflow-y-auto px-6 py-4">
            <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
              {error ? <p className="m-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p> : null}
              {loading ? (
                <div className="m-4 h-64 animate-pulse rounded-xl bg-slate-100" />
              ) : (
                <div>
                  {(data?.items || []).map((item, index) => {
                    const isOpen = expanded.has(index);
                    return (
                      <div key={`${item.ixc_os_id}-${item.event_at}-${index}`} className="border-b border-slate-100 last:border-b-0">
                        <button
                          type="button"
                          onClick={() => toggleExpanded(index)}
                          className={`flex w-full flex-wrap items-baseline gap-2.5 px-4 py-2.5 text-left transition hover:bg-blue-50/50 ${index % 2 === 1 ? "bg-slate-50/40" : ""}`}
                        >
                          <span className="flex min-w-[70px] items-center gap-1 whitespace-nowrap text-xs tabular-nums text-slate-500">
                            <Clock className="h-3 w-3" /> {formatTimePortoVelho(item.event_at)}
                          </span>
                          <span className="whitespace-nowrap text-xs text-slate-400">#{item.ixc_os_id}</span>
                          <span className="font-medium text-slate-800">{item.operator_name || "—"}</span>
                          {item.origin === "equipe" ? (
                            <Badge className="border-blue-200 bg-blue-50 text-[10px] text-blue-700">Equipe</Badge>
                          ) : item.origin === "campo" ? (
                            <Badge className="border-orange-200 bg-orange-50 text-[10px] text-orange-700">Campo</Badge>
                          ) : null}
                          <ChevronDown className={`ml-auto h-4 w-4 shrink-0 text-slate-400 transition-transform ${isOpen ? "rotate-180" : ""}`} />
                          <span className="basis-full text-xs text-slate-500">
                            <span className="inline-flex items-center gap-1"><MapPin className="h-3 w-3" /> {item.filial}</span>
                            <span className="mx-1.5 text-slate-300">·</span>
                            <span className="inline-flex items-center gap-1"><Tag className="h-3 w-3" /> {item.assunto}</span>
                          </span>
                          {item.mensagem ? <span className="basis-full text-xs text-slate-600">{item.mensagem}</span> : null}
                        </button>
                        {isOpen ? (
                          <div className="mx-4 mb-3 rounded-lg bg-slate-50 px-3 py-2.5 text-xs">
                            <p className="text-slate-400">Técnico</p>
                            <p className="mb-2 text-slate-700">{item.technician_name || "—"}</p>
                            <p className="text-slate-400">Histórico completo</p>
                            <p className="mb-2 whitespace-pre-wrap text-slate-700">{item.historico || "—"}</p>
                            <button
                              type="button"
                              onClick={() => setTimelineOsId(item.ixc_os_id)}
                              className="inline-flex items-center gap-1 font-medium text-blue-700 hover:underline"
                            >
                              <ExternalLink className="h-3 w-3" /> Ver linha do tempo completa da O.S.
                            </button>
                          </div>
                        ) : null}
                      </div>
                    );
                  })}
                  {data && !data.items.length ? (
                    <p className="py-10 text-center text-sm text-slate-500">Nenhum reagendamento neste dia com o recorte atual. 🎉</p>
                  ) : null}
                </div>
              )}
              {data && data.total > data.page_size ? <DrillPagination page={page} totalPages={totalPages} onChange={setPage} /> : null}
            </section>
          </div>
        </SheetContent>
      </Sheet>
      {timelineOsId !== null ? (
        <OrderTimelinePanel ixcOsId={timelineOsId} onClose={() => setTimelineOsId(null)} />
      ) : null}
    </>
  );
}
