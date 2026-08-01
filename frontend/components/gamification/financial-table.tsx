"use client";

import { ChevronDown, ChevronUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import { InfoHint } from "@/components/gamification/info-hint";
import { MetricCard } from "@/components/gamification/config-ui";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatMoney, formatNumber } from "@/lib/gamificacao-helpers";
import { regionalName } from "@/lib/regional";

type FinancialTableProps = {
  title: string;
  rows: Array<Record<string, string | number | undefined>>;
  labelKey: "regional" | "group" | "os_subject";
  collapsed: boolean;
  onToggle: () => void;
  helpText: string;
};

export function FinancialTable({ title, rows, labelKey, collapsed, onToggle, helpText }: FinancialTableProps) {
  const totalOrders = rows.reduce((total, row) => total + Number(row.orders ?? 0), 0);
  const totalPayment = rows.reduce((total, row) => total + Number(row.estimated_payment ?? 0), 0);

  return (
    <div className="overflow-hidden rounded-[20px] border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      <div className="border-b bg-[linear-gradient(180deg,#ffffff_0%,#f8fbff_100%)] px-4 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="truncate text-sm font-semibold text-slate-950">{title}</h3>
              <InfoHint ariaLabel={`Ajuda sobre ${title}`} description={helpText} />
            </div>
            <p className="mt-1 text-sm text-slate-500">{formatNumber(rows.length)} item(ns)</p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-8 w-8 rounded-xl p-0 text-slate-500 hover:bg-slate-100 hover:text-slate-700"
            onClick={onToggle}
            title={collapsed ? "Expandir todos" : "Recolher todos"}
            aria-label={collapsed ? "Expandir todos" : "Recolher todos"}
          >
            {collapsed ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
          </Button>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-3">
          <MetricCard title="O.S" value={`${formatNumber(totalOrders)} O.S`} />
          <MetricCard title="Valor a ser pago" value={formatMoney(totalPayment)} />
        </div>
      </div>
      {!collapsed ? (
        <div className="table-frame px-2 py-2">
          <Table>
            <TableHeader className="sticky top-0 z-10 bg-slate-900 text-white shadow-sm [&_th]:text-slate-200">
              <TableRow className="border-slate-700 hover:bg-slate-900">
                <TableHead>Dimensão</TableHead>
                <TableHead>O.S</TableHead>
                <TableHead>Valor a ser pago</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.slice(0, 8).map((row, index) => (
                <TableRow key={`${title}-${index}`}>
                  <TableCell className="min-w-52">
                    <div className="flex items-start gap-3">
                      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-100 text-[11px] font-semibold text-slate-600">
                        {index + 1}
                      </div>
                      <div className="font-medium text-slate-900">
                        {labelKey === "regional" ? regionalName(String(row[labelKey] ?? "-")) : String(row[labelKey] ?? "-")}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="font-medium text-slate-700">{formatNumber(Number(row.orders ?? 0))} O.S</TableCell>
                  <TableCell className="font-semibold text-uni-royal">{formatMoney(Number(row.estimated_payment ?? 0))}</TableCell>
                </TableRow>
              ))}
              {rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={3} className="py-6 text-center text-sm text-slate-500">
                    Nenhum dado para os filtros atuais.
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </div>
      ) : (
        <div className="border-t bg-slate-50/70 px-4 py-3 text-sm text-slate-500">Painel recolhido. Use a seta para abrir os itens do recorte atual.</div>
      )}
    </div>
  );
}
