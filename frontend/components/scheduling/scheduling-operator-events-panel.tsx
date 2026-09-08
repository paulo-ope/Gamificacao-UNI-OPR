"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { schedulingApi, type SchedulingFilterState, type SchedulingOperatorEventPage } from "@/lib/scheduling-api";

import { DrillPagination } from "./scheduling-drill-header";
import { DRILL_PAGE_SIZE, formatPortoVelho } from "./scheduling-format";
import { OrderTimelinePanel } from "./scheduling-order-timeline-panel";

export function OperatorEventsDrillPanel({
  operatorId,
  title,
  filters,
  onClose,
}: {
  operatorId: number;
  title: string;
  filters: SchedulingFilterState;
  onClose: () => void;
}) {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<SchedulingOperatorEventPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [timelineOsId, setTimelineOsId] = useState<number | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    schedulingApi
      .operatorEvents(operatorId, filters, page, DRILL_PAGE_SIZE, controller.signal)
      .then(setData)
      .catch((reason) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Falha ao carregar as ações do operador.");
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [operatorId, page, filters.date_from, filters.date_to]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <>
      <Sheet open onOpenChange={(open) => !open && onClose()}>
        <SheetContent className="flex w-full flex-col sm:max-w-3xl">
          <SheetHeader className="border-b border-slate-100 bg-gradient-to-br from-slate-50 to-white">
            <SheetTitle className="text-lg">{title}</SheetTitle>
            <SheetDescription>
              Cada agendamento/reagendamento feito por este operador no período
              {data ? ` · ${new Intl.NumberFormat("pt-BR").format(data.total)} ações no total` : ""}
            </SheetDescription>
          </SheetHeader>
          <div className="flex-1 overflow-y-auto px-6 py-4">
          <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            {error ? <p className="m-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p> : null}
            {loading ? (
              <div className="m-4 h-64 animate-pulse rounded-xl bg-slate-100" />
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="bg-slate-50">O.S.</TableHead>
                      <TableHead className="bg-slate-50">Ação</TableHead>
                      <TableHead className="bg-slate-50">Quando</TableHead>
                      <TableHead className="bg-slate-50">Janela</TableHead>
                      <TableHead className="bg-slate-50">Técnico</TableHead>
                      <TableHead className="bg-slate-50">Filial</TableHead>
                      <TableHead className="bg-slate-50">Assunto</TableHead>
                      <TableHead className="bg-slate-50">Mensagem</TableHead>
                      <TableHead className="bg-slate-50">Histórico</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(data?.items || []).map((item, index) => (
                      <TableRow
                        key={`${item.ixc_os_id}-${item.event_at}-${index}`}
                        className={`cursor-pointer hover:bg-blue-50/60 ${index % 2 === 1 ? "bg-slate-50/50" : ""}`}
                        onClick={() => setTimelineOsId(item.ixc_os_id)}
                      >
                        <TableCell className="font-medium text-slate-800">{item.ixc_os_id}</TableCell>
                        <TableCell>
                          <Badge className={item.event_type === "10" ? "border-amber-200 bg-amber-50 text-amber-700" : "border-blue-200 bg-blue-50 text-blue-700"}>
                            {item.event_label}
                          </Badge>
                        </TableCell>
                        <TableCell>{formatPortoVelho(item.event_at)}</TableCell>
                        <TableCell>
                          {item.window_start ? (
                            <>
                              {formatPortoVelho(item.window_start)}
                              {item.window_end ? ` até ${formatPortoVelho(item.window_end)}` : ""}
                            </>
                          ) : (
                            "—"
                          )}
                        </TableCell>
                        <TableCell className="max-w-56 truncate whitespace-nowrap" title={item.technician_name || undefined}>{item.technician_name || "—"}</TableCell>
                        <TableCell className="max-w-44 truncate whitespace-nowrap" title={item.filial}>{item.filial}</TableCell>
                        <TableCell className="max-w-64 truncate whitespace-nowrap" title={item.assunto}>{item.assunto}</TableCell>
                        <TableCell className="max-w-56 truncate whitespace-nowrap" title={item.mensagem || undefined}>{item.mensagem || "—"}</TableCell>
                        <TableCell className="max-w-56 truncate whitespace-nowrap" title={item.historico || undefined}>{item.historico || "—"}</TableCell>
                      </TableRow>
                    ))}
                    {data && !data.items.length ? (
                      <TableRow>
                        <TableCell colSpan={9} className="py-10 text-center text-sm text-slate-500">Nenhuma ação encontrada para este recorte.</TableCell>
                      </TableRow>
                    ) : null}
                  </TableBody>
                </Table>
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
