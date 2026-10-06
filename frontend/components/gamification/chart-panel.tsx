"use client";

import { useId, useState, type ReactNode } from "react";
import { BarChart3, Table2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

type ChartPanelProps = {
  title: string;
  description: string;
  children: ReactNode;
  columns: string[];
  rows: ReactNode[][];
  className?: string;
  emptyLabel?: string;
};

export function ChartPanel({ title, description, children, columns, rows, className, emptyLabel = "Nenhum dado neste recorte" }: ChartPanelProps) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const titleId = useId();
  return (
    <section aria-labelledby={titleId} className={cn("min-w-0 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-panel", className)}>
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 p-4 sm:p-5">
        <div className="min-w-0 flex-1">
          <h3 id={titleId} className="text-base font-semibold text-slate-950">{title}</h3>
          <p className="mt-1 text-xs leading-5 text-slate-500">{description}</p>
        </div>
        <div role="group" aria-label={`Visualização: ${title}`} className="flex rounded-lg bg-slate-100 p-1">
          <Button size="sm" variant={view === "chart" ? "secondary" : "ghost"} aria-pressed={view === "chart"} aria-label={`Ver gráfico: ${title}`} title="Ver gráfico" onClick={() => setView("chart")} className="h-8 px-2">
            <BarChart3 className="h-4 w-4" />
          </Button>
          <Button size="sm" variant={view === "table" ? "secondary" : "ghost"} aria-pressed={view === "table"} aria-label={`Ver dados: ${title}`} title="Ver dados" onClick={() => setView("table")} className="h-8 px-2">
            <Table2 className="h-4 w-4" />
          </Button>
        </div>
      </div>
      {!rows.length ? (
        <EmptyState className="m-4" title={emptyLabel} description="Ajuste o período ou as filiais para consultar outro recorte." />
      ) : view === "chart" ? (
        <div className="min-w-0 p-3 sm:p-4">{children}</div>
      ) : (
        <div className="max-h-[460px] overflow-auto">
          <Table>
            <TableHeader><TableRow>{columns.map((label, index) => <TableHead key={label} className={cn("whitespace-nowrap", index > 0 && "text-right")}>{label}</TableHead>)}</TableRow></TableHeader>
            <TableBody>
              {rows.map((row, index) => (
                <TableRow key={index}>
                  {row.map((cell, cellIndex) => <TableCell key={cellIndex} className={cellIndex ? "text-right" : "min-w-44 font-medium"}>{cell}</TableCell>)}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </section>
  );
}

type ComparisonItem = { label: string; value: number; formatted: string; detail?: string };

/** HTML labels stay selectable and wrap naturally on small screens. */
export function BarComparison({ items, tone = "blue" }: { items: ComparisonItem[]; tone?: "blue" | "red" }) {
  const max = Math.max(1, ...items.map((item) => Math.abs(item.value)));
  const signed = items.some((item) => item.value < 0);
  return (
    <ol className="max-h-[480px] space-y-4 overflow-y-auto px-1 py-2">
      {items.map((item, index) => (
        <li key={`${item.label}-${index}`} className="grid gap-2">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="break-words text-xs font-medium leading-5 text-slate-700">{item.label}</p>
              {item.detail ? <p className="text-xs text-slate-500">{item.detail}</p> : null}
            </div>
            <span className={cn("shrink-0 text-xs font-semibold tabular-nums", tone === "red" || item.value < 0 ? "text-red-700" : "text-primary")}>{item.formatted}</span>
          </div>
          <div aria-hidden="true" className="relative h-2 overflow-hidden rounded-full bg-slate-100">
            {signed ? <span className="absolute left-1/2 top-0 h-full border-l border-slate-400" /> : null}
            <div className={cn("absolute h-full rounded-full", tone === "red" || item.value < 0 ? "bg-red-400" : "bg-gradient-to-r from-blue-600 to-cyan-500")} style={{ width: `${Math.abs(item.value) / max * (signed ? 50 : 100)}%`, left: signed ? item.value < 0 ? undefined : "50%" : 0, right: signed && item.value < 0 ? "50%" : undefined }} />
          </div>
        </li>
      ))}
    </ol>
  );
}
