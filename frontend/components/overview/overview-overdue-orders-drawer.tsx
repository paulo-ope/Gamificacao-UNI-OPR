"use client";

import { useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { DRILL_PAGE_SIZE, Pagination } from "@/components/ui/pagination";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useBlockQuery } from "@/hooks/use-block-query";
import { formatDateTime, formatHours, formatInteger } from "@/lib/format";
import { operationsApi, type OperationFilterState } from "@/lib/operations-api";

/**
 * Detalhe do "N fora do prazo" do quadro por regional: as O.S. em aberto marcadas fora do prazo,
 * para análise. A lista vem do backend com o mesmo recorte do quadro (`overdue_only`), então o total
 * aqui é sempre o número clicado. `regional` nulo abre o total geral do quadro.
 */
export function OverviewOverdueOrdersDrawer({
  open,
  onOpenChange,
  regional,
  filters,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  regional: string | null;
  filters: OperationFilterState | null;
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent aria-describedby="overdue-orders-description">
        <SheetHeader>
          <SheetTitle>O.S. fora do prazo{regional ? ` · ${regional}` : ""}</SheetTitle>
          <SheetDescription id="overdue-orders-description">
            O.S. ainda em aberto com prazo estourado agora, de qualquer equipe e de qualquer data de abertura.
          </SheetDescription>
        </SheetHeader>
        {open && filters ? <OverdueOrdersList key={regional ?? "total"} regional={regional} filters={filters} /> : null}
      </SheetContent>
    </Sheet>
  );
}

function OverdueOrdersList({ regional, filters }: { regional: string | null; filters: OperationFilterState }) {
  const [page, setPage] = useState(1);
  const scopeKey = JSON.stringify(filters);
  const orders = useBlockQuery(
    () =>
      operationsApi.inProgressOrders(
        filters,
        page,
        DRILL_PAGE_SIZE,
        { key: "opened_at", direction: "asc" },
        undefined,
        true,
        // Rótulo da linha do quadro, resolvido no servidor com o mesmo agrupamento do quadro.
        regional ?? undefined,
      ),
    [scopeKey, regional, page],
    { fallbackError: "Não foi possível carregar as O.S. fora do prazo." },
  );

  if (orders.loading) {
    return <div className="m-6 h-48 animate-pulse rounded-2xl bg-slate-100" aria-label="Carregando O.S." />;
  }
  if (orders.error) {
    return (
      <p role="alert" className="m-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
        {orders.error}
      </p>
    );
  }
  const data = orders.data;
  if (!data || !data.items.length) {
    return (
      <EmptyState
        variant="plain"
        title="Nenhuma O.S. fora do prazo"
        description="Não há O.S. em aberto com prazo estourado neste recorte."
      />
    );
  }

  return (
    <div className="flex flex-col gap-3 px-6 py-4">
      <p className="text-sm text-slate-600">
        <strong className="font-semibold text-slate-800">{formatInteger(data.total)}</strong> O.S. fora do prazo, da
        mais antiga para a mais recente.
      </p>
      <div className="overflow-x-auto rounded-xl border border-slate-200">
        <Table className="min-w-[760px]">
          <TableHeader>
            <TableRow>
              <TableHead>O.S.</TableHead>
              <TableHead>Assunto</TableHead>
              <TableHead>Cliente</TableHead>
              <TableHead>Responsável</TableHead>
              <TableHead>Aberta em</TableHead>
              <TableHead className="text-right">Tempo × meta</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.items.map((order) => (
              <TableRow key={order.id}>
                <TableCell className="font-medium text-slate-800">
                  {order.order_code}
                  {!regional && order.regional ? (
                    <span className="block text-[11px] font-normal text-slate-500">{order.regional}</span>
                  ) : null}
                </TableCell>
                <TableCell>{order.os_subject ?? "—"}</TableCell>
                <TableCell>
                  {order.customer_name ?? "—"}
                  {order.city ? <span className="block text-[11px] text-slate-500">{order.city}</span> : null}
                </TableCell>
                <TableCell>{order.responsible ?? "Sem responsável"}</TableCell>
                <TableCell className="whitespace-nowrap">{formatDateTime(order.opened_at)}</TableCell>
                <TableCell className="whitespace-nowrap text-right tabular-nums">
                  <span className="font-semibold text-red-600">{formatHours(order.elapsed_hours)}</span>
                  <span className="block text-[11px] text-slate-500">
                    meta {order.sla_target_hours ? formatHours(order.sla_target_hours) : "—"}
                  </span>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <Pagination
        page={data.page}
        totalPages={data.total_pages}
        onPageChange={setPage}
        totalItems={data.total}
        itemLabel="O.S."
        disabled={orders.refreshing}
      />
    </div>
  );
}
