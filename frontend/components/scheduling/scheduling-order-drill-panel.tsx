"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  schedulingApi,
  type SchedulingFilterState,
  type SchedulingOrderDetailPage,
  type SchedulingOrderDrillParams,
  type SchedulingOrderSort,
  type SchedulingOrderSortKey,
} from "@/lib/scheduling-api";

import { DrillPagination } from "./scheduling-drill-header";
import { DRILL_PAGE_SIZE, formatPortoVelho, hoursLabel, minutesLabel, rescheduleOriginLabel } from "./scheduling-format";
import { OrderTimelinePanel } from "./scheduling-order-timeline-panel";

// Mesmo padrão de drilldown do resto do sistema (ex. `app/suporte/_components/opa-drilldown.tsx`):
// `Sheet` lateral largo com cabeçalho em degradê e a tabela dentro de um card próprio, em vez de um
// modal centralizado artesanal.
export function OrderDrillPanel({
  title,
  subtitle,
  filters,
  params,
  onClose,
}: {
  title: string;
  subtitle: string;
  filters: SchedulingFilterState;
  params: SchedulingOrderDrillParams;
  onClose: () => void;
}) {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<SchedulingOrderDetailPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [timelineOsId, setTimelineOsId] = useState<number | null>(null);
  const [sort, setSort] = useState<SchedulingOrderSort>({ key: "opened_at", direction: "desc" });
  const [originFilter, setOriginFilter] = useState<"all" | "backoffice" | "campo">(params.reschedule_origin ?? "all");

  function changeSort(key: SchedulingOrderSortKey) {
    const direction: "asc" | "desc" = sort.key === key && sort.direction === "desc" ? "asc" : "desc";
    setSort({ key, direction });
    setPage(1);
  }

  function sortMark(key: SchedulingOrderSortKey) {
    if (sort.key !== key) return "";
    return sort.direction === "asc" ? " ↑" : " ↓";
  }

  // Filtro de origem refina só dentro do painel (o card já abre o recorte "só reagendadas") - não
  // faz sentido mostrá-lo fora de um drill de reagendamento.
  const showOriginFilter = Boolean(params.only_rescheduled);
  const effectiveParams: SchedulingOrderDrillParams = showOriginFilter
    ? { ...params, reschedule_origin: originFilter === "all" ? undefined : originFilter }
    : params;

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    schedulingApi
      .orders(filters, effectiveParams, page, DRILL_PAGE_SIZE, sort, controller.signal)
      .then(setData)
      .catch((reason) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Falha ao carregar as O.S.");
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, sort.key, sort.direction, JSON.stringify(effectiveParams), filters.date_from, filters.date_to]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <>
      <Sheet open onOpenChange={(open) => !open && onClose()}>
        <SheetContent className="flex w-full flex-col sm:max-w-[min(1400px,96vw)]">
          <SheetHeader className="border-b border-slate-100 bg-gradient-to-br from-slate-50 to-white">
            <SheetTitle className="text-lg">{title}</SheetTitle>
            <SheetDescription>
              {subtitle}
              {data ? ` · ${new Intl.NumberFormat("pt-BR").format(data.total)} O.S. no total` : ""}
            </SheetDescription>
          </SheetHeader>

          <div className="flex-1 overflow-y-auto px-6 py-4">
            {showOriginFilter ? (
              <div className="mb-4 flex items-center gap-2">
                <span className="text-[11px] font-medium text-slate-500">Origem</span>
                <div className="flex rounded-lg border border-slate-200 bg-slate-50 p-1">
                  {(
                    [
                      ["all", "Todas"],
                      ["backoffice", "Backoffice"],
                      ["campo", "Campo"],
                    ] as const
                  ).map(([value, label]) => (
                    <Button
                      key={value}
                      type="button"
                      size="sm"
                      variant={originFilter === value ? "default" : "ghost"}
                      className="h-7 px-2.5 text-xs"
                      onClick={() => {
                        setOriginFilter(value);
                        setPage(1);
                      }}
                    >
                      {label}
                    </Button>
                  ))}
                </div>
              </div>
            ) : null}

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
                        <TableHead className="bg-slate-50">
                          <button type="button" onClick={() => changeSort("opened_at")}>Aberta em{sortMark("opened_at")}</button>
                        </TableHead>
                        <TableHead className="bg-slate-50">
                          <button type="button" onClick={() => changeSort("first_scheduled_at")}>1º agendamento{sortMark("first_scheduled_at")}</button>
                        </TableHead>
                        <TableHead className="bg-slate-50 text-right">
                          <button type="button" onClick={() => changeSort("ttfa_business_minutes")}>Tempo (útil){sortMark("ttfa_business_minutes")}</button>
                        </TableHead>
                        <TableHead className="bg-slate-50">Operador</TableHead>
                        <TableHead className="bg-slate-50">Técnico</TableHead>
                        <TableHead className="bg-slate-50">
                          <button type="button" onClick={() => changeSort("filial")}>Filial{sortMark("filial")}</button>
                        </TableHead>
                        <TableHead className="bg-slate-50">
                          <button type="button" onClick={() => changeSort("assunto")}>Assunto{sortMark("assunto")}</button>
                        </TableHead>
                        <TableHead className="bg-slate-50 text-right">
                          <button type="button" onClick={() => changeSort("reschedule_count")}>Reagend.{sortMark("reschedule_count")}</button>
                        </TableHead>
                        {showOriginFilter ? <TableHead className="bg-slate-50">Reagendado por</TableHead> : null}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(data?.items || []).map((item, index) => (
                        <TableRow
                          key={item.ixc_os_id}
                          className={`cursor-pointer hover:bg-blue-50/60 ${index % 2 === 1 ? "bg-slate-50/50" : ""}`}
                          onClick={() => setTimelineOsId(item.ixc_os_id)}
                        >
                          <TableCell className="font-medium text-slate-800">{item.ixc_os_id}</TableCell>
                          <TableCell>{formatPortoVelho(item.opened_at)}</TableCell>
                          <TableCell>
                            {item.first_scheduled_at ? (
                              formatPortoVelho(item.first_scheduled_at)
                            ) : (
                              <span className={item.age_hours && item.age_hours > 72 ? "font-semibold text-red-600" : "text-slate-400"}>
                                Pendente há {hoursLabel(item.age_hours)}
                              </span>
                            )}
                          </TableCell>
                          <TableCell className={`text-right tabular-nums ${item.sla_late ? "font-semibold text-red-600" : ""}`}>
                            {minutesLabel(item.ttfa_business_minutes)}
                          </TableCell>
                          <TableCell className="max-w-56 truncate whitespace-nowrap" title={item.operator_name || undefined}>{item.operator_name || "—"}</TableCell>
                          <TableCell className="max-w-56 truncate whitespace-nowrap" title={item.technician_name || undefined}>{item.technician_name || "—"}</TableCell>
                          <TableCell className="max-w-44 truncate whitespace-nowrap" title={item.filial}>{item.filial}</TableCell>
                          <TableCell className="max-w-64 truncate whitespace-nowrap" title={item.assunto}>{item.assunto}</TableCell>
                          <TableCell className="text-right tabular-nums">{item.reschedule_count || "—"}</TableCell>
                          {showOriginFilter ? (
                            <TableCell>{rescheduleOriginLabel(item.reschedule_origins)}</TableCell>
                          ) : null}
                        </TableRow>
                      ))}
                      {data && !data.items.length ? (
                        <TableRow>
                          <TableCell colSpan={showOriginFilter ? 10 : 9} className="py-10 text-center text-sm text-slate-500">Nenhuma O.S. encontrada para este recorte.</TableCell>
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
