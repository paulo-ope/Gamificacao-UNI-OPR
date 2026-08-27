"use client";

import { Eye, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { secondsLabel } from "@/lib/format-duration";
import type { SupportOpaAttendanceFilters, SupportOpaAttendancePage, SupportOpaOverview } from "@/lib/types";

import { customerCodeLabel, customerNameLabel, number, opaStatusLabel, StatCell, tmrCoverageNote } from "./opa-module-components";

/** O que o usuário clicou no gráfico. `filters` é o recorte ADICIONAL daquele
 *  clique — sempre aplicado por cima dos filtros globais da tela, nunca no
 *  lugar deles: um drill-down que trocasse o recorte mostraria um número que
 *  não bate com o gráfico de onde ele saiu. */
export type OpaDrilldown = {
  title: string;
  subtitle: string;
  filters: Partial<SupportOpaAttendanceFilters>;
};

function shortDateTime(value: string | null | undefined) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "America/Porto_Velho",
  }).format(new Date(value));
}

export function OpaDrilldownSheet({
  drilldown,
  baseFilters,
  onOpenChange,
  onOpenAttendance,
}: {
  drilldown: OpaDrilldown | null;
  baseFilters: SupportOpaAttendanceFilters;
  onOpenChange: (open: boolean) => void;
  onOpenAttendance: (id: number) => void;
}) {
  const [overview, setOverview] = useState<SupportOpaOverview | null>(null);
  const [page, setPage] = useState<SupportOpaAttendancePage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const key = drilldown ? JSON.stringify([baseFilters, drilldown.filters]) : null;

  useEffect(() => {
    if (!drilldown) return;
    let cancelled = false;
    const merged: SupportOpaAttendanceFilters = { ...baseFilters, ...drilldown.filters };
    setLoading(true);
    setError(null);
    setOverview(null);
    setPage(null);
    Promise.all([
      api.supportOpaOverview(merged),
      api.supportOpaAttendances({ ...merged, page: 1, page_size: 25, sort_by: "opened_at", sort_dir: "desc" }),
    ])
      .then(([overviewData, pageData]) => {
        if (cancelled) return;
        setOverview(overviewData);
        setPage(pageData);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setError(reason instanceof Error ? reason.message : "Falha ao carregar o detalhamento.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // `key` já representa base + recorte do clique; depender dos objetos crus
    // refaria a chamada a cada render por identidade nova.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const items = page?.items ?? [];
  const coverageNote = tmrCoverageNote(overview?.tmr_all_responses_coverage);

  return (
    <Sheet open={drilldown !== null} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-3xl">
        <SheetHeader className="border-b border-slate-100 bg-gradient-to-br from-slate-50 to-white">
          <SheetTitle className="text-lg">{drilldown?.title ?? "Detalhamento"}</SheetTitle>
          <SheetDescription>{drilldown?.subtitle ?? ""}</SheetDescription>
        </SheetHeader>

        {loading ? (
          <div className="flex min-h-48 items-center justify-center gap-2 text-sm text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin" /> Carregando detalhamento...
          </div>
        ) : null}

        {!loading && error ? (
          <div className="mt-5 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>
        ) : null}

        {!loading && !error && overview ? (
          <div className="mt-5 grid gap-4">
            <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
              <div className="grid grid-cols-2 divide-x divide-y divide-slate-100 sm:grid-cols-4 sm:divide-y-0">
                <StatCell label="Atendimentos" value={number(overview.total_attendances.current)} />
                <StatCell label="Encerrados" value={number(overview.closed_attendances.current)} />
                <StatCell label="TMA" value={secondsLabel(overview.average_duration_seconds.current)} />
                <StatCell label="TMR geral" value={secondsLabel(overview.average_tmr_all_responses_seconds.current)} helper="inclui bot" />
              </div>
              {coverageNote ? (
                <p className="border-t border-amber-200/70 bg-amber-50 px-4 py-2 text-[11px] leading-relaxed text-amber-800">
                  {coverageNote}
                </p>
              ) : null}
            </section>

            <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
              <div className="flex items-center justify-between gap-2 border-b border-slate-100 bg-slate-50/60 px-4 py-3">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">Atendimentos</h3>
                <Badge className="border-slate-200 bg-white text-slate-600">
                  {number(page?.total ?? 0)} no recorte
                </Badge>
              </div>
              <div className="overflow-x-auto p-3">
                <Table className="min-w-[560px]">
                  <TableHeader>
                    <TableRow>
                      <TableHead>Abertura</TableHead>
                      <TableHead>Cliente</TableHead>
                      <TableHead>Atendente</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Ação</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {items.map((item, index) => (
                      <TableRow key={item.id} className={index % 2 === 1 ? "bg-slate-50/50" : undefined}>
                        <TableCell className="whitespace-nowrap tabular-nums">{shortDateTime(item.opened_at)}</TableCell>
                        <TableCell className="max-w-52">
                          <p className="truncate font-medium text-slate-800">
                            {customerNameLabel(item.customer_name, item.customer_id)}
                          </p>
                          {customerCodeLabel(item.customer_id) ? (
                            <p className="truncate text-[11px] text-slate-400">{customerCodeLabel(item.customer_id)}</p>
                          ) : null}
                        </TableCell>
                        <TableCell className="max-w-40 truncate">{item.attendant_name ?? "-"}</TableCell>
                        <TableCell className="whitespace-nowrap text-xs">{opaStatusLabel(item.status)}</TableCell>
                        <TableCell className="text-right">
                          <Button type="button" variant="ghost" size="sm" onClick={() => onOpenAttendance(item.id)}>
                            <Eye className="h-3.5 w-3.5" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                    {!items.length ? (
                      <TableRow>
                        <TableCell colSpan={5} className="py-8 text-center text-sm text-slate-500">
                          Nenhum atendimento neste recorte.
                        </TableCell>
                      </TableRow>
                    ) : null}
                  </TableBody>
                </Table>
              </div>
              {page && page.total > items.length ? (
                <p className="border-t border-slate-100 px-4 py-2 text-[11px] text-slate-500">
                  Mostrando os {number(items.length)} mais recentes de {number(page.total)}.
                </p>
              ) : null}
            </section>
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
