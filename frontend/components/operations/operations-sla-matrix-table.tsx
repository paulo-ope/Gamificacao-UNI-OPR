"use client";

import { Fragment, useMemo, useState } from "react";
import { Download, Loader2 } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useSlaMatrixExport } from "@/hooks/use-sla-matrix-export";
import type { OperationFilterState, OperationSlaMatrix, OperationSlaMatrixCell } from "@/lib/operations-api";
import { slaSystemTone } from "@/lib/operations-sla";
import { toneSoftBgClass } from "@/lib/tones";

function volume(value: number) {
  return value ? new Intl.NumberFormat("pt-BR").format(value) : "—";
}

function percentage(rate: number | null) {
  if (rate === null) return "—";
  return `${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(rate)}%`;
}

function hours(value: number | null) {
  if (value === null) return "—";
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(value);
}

function emptyCell(regional: string): OperationSlaMatrixCell {
  return { regional, completed: 0, sla_rate: null, average_closing_hours: null };
}

/**
 * "Matriz de indicadores por filial" (pedido do usuário em 2026-09-18): Volume/SLA%/TME de cada
 * grupo de SLA (`/operations/sla-groups`, configurável pela tela) por filial - reproduz, direto da
 * O.S. já sincronizada do IXC, o painel executivo (`indicadores.html`) que ele antes montava na
 * mão a partir de planilhas Excel exportadas por regional. Passou por 3 desenhos nesta mesma
 * sessão: (1) colunas fixas por filial (igual ao Excel original) - larga demais, scroll lateral
 * em qualquer tela normal; (2) filial por linha, sem coluna nenhuma - user achou "feio" e pediu de
 * volta o formato de grade do HTML original. Este é o formato final: GRADE de verdade (filial em
 * coluna, indicador em linha, 3 sub-linhas por indicador - Realizadas/SLA/T.M. Fechamento, igual
 * às linhas TME/SLA/VOL do painel original), com scroll horizontal DENTRO do card (primeira coluna
 * e cabeçalho fixos) - o mesmo `.card { overflow-x: auto }` do HTML original, não mais evitado.
 */
export function OperationsSlaMatrixTable({
  data,
  filters,
  isLoading = false,
}: {
  data: OperationSlaMatrix;
  filters: OperationFilterState;
  isLoading?: boolean;
}) {
  const [exporting, setExporting] = useState(false);
  const exportMatrix = useSlaMatrixExport();

  const sections = useMemo(() => {
    const groups: Array<{ cardLabel: string; rows: typeof data.rows }> = [];
    for (const row of data.rows) {
      const last = groups[groups.length - 1];
      if (last && last.cardLabel === row.card_label) last.rows.push(row);
      else groups.push({ cardLabel: row.card_label, rows: [row] });
    }
    return groups;
  }, [data.rows]);
  const showLoader = isLoading && !data.rows.length;
  const showEmpty = !isLoading && !data.rows.length;
  const totalColumns = data.regionals.length + 2;

  async function handleExport() {
    setExporting(true);
    try {
      await exportMatrix(data, filters);
    } finally {
      setExporting(false);
    }
  }

  return (
    <Card className="mt-4 overflow-hidden rounded-2xl border-slate-200">
      <CardHeader className="border-b bg-slate-950 px-4 py-3 text-white">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <CardTitle className="text-sm font-semibold">
              Matriz de indicadores por filial
            </CardTitle>
            <p className="text-[11px] text-slate-300">
              Realizadas / SLA / T.M. Fechamento por grupo x filial. "Matriz" é o total recalculado
              (não a média das filiais). Grupos são geridos em Configuração → SLA por tecnologia.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void handleExport()}
            disabled={exporting || !data.rows.length}
            title="Exportar planilha da matriz (.xlsx)"
            aria-label="Exportar planilha da matriz"
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-3 text-xs font-medium text-white shadow-sm transition hover:border-blue-400 hover:text-blue-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {exporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            Exportar
          </button>
        </div>
      </CardHeader>
      <CardContent className="overflow-x-auto p-0">
        <Table className="text-xs">
          <TableHeader className="sticky top-0 z-20 bg-slate-100">
            <TableRow className="hover:bg-slate-100">
              <TableHead className="sticky left-0 z-30 min-w-64 bg-slate-100">Indicador</TableHead>
              {data.regionals.map((regional) => (
                <TableHead key={regional} className="min-w-24 text-center text-[10px]">
                  {regional}
                </TableHead>
              ))}
              <TableHead className="min-w-24 bg-slate-200 text-center text-[10px] font-bold">
                Matriz
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {showLoader ? (
              <TableRow>
                <TableCell colSpan={totalColumns} className="py-14 text-center text-slate-500">
                  <Loader2 className="mx-auto h-5 w-5 animate-spin" />
                  <p className="mt-2">Calculando a matriz...</p>
                </TableCell>
              </TableRow>
            ) : (
              sections.map((section) => (
                <Fragment key={section.cardLabel}>
                  <TableRow className="bg-slate-100 hover:bg-slate-100">
                    <TableCell
                      colSpan={totalColumns}
                      className="sticky left-0 z-10 bg-slate-100 py-1.5 text-[10px] font-bold uppercase tracking-wide text-slate-600"
                    >
                      {section.cardLabel}
                    </TableCell>
                  </TableRow>
                  {section.rows.map((row) => {
                    function cellFor(regional: string): OperationSlaMatrixCell {
                      return row.cells.find((item) => item.regional === regional) || emptyCell(regional);
                    }
                    return (
                      <Fragment key={row.group_id}>
                        <TableRow className="border-t border-slate-200">
                          <TableCell
                            rowSpan={3}
                            className="sticky left-0 z-10 bg-white py-2 align-top font-semibold text-slate-900"
                          >
                            {row.group_name}
                          </TableCell>
                          <TableCell className="bg-slate-50 text-center text-[10px] font-medium uppercase text-slate-500">
                            Realizadas
                          </TableCell>
                          {data.regionals.map((regional) => (
                            <TableCell key={regional} className="bg-slate-50 text-center font-bold tabular-nums text-slate-900">
                              {volume(cellFor(regional).completed)}
                            </TableCell>
                          ))}
                          <TableCell className="bg-slate-200 text-center font-bold tabular-nums text-slate-900">
                            {volume(row.total.completed)}
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell className="text-center text-[10px] font-medium uppercase text-slate-500">
                            SLA
                          </TableCell>
                          {data.regionals.map((regional) => {
                            const cell = cellFor(regional);
                            return (
                              <TableCell
                                key={regional}
                                className={`text-center font-semibold ${cell.completed ? toneSoftBgClass(slaSystemTone(cell.sla_rate)) : "text-slate-300"}`}
                              >
                                {percentage(cell.sla_rate)}
                              </TableCell>
                            );
                          })}
                          <TableCell
                            className={`text-center font-semibold ${row.total.completed ? toneSoftBgClass(slaSystemTone(row.total.sla_rate)) : "text-slate-300"}`}
                          >
                            {percentage(row.total.sla_rate)}
                          </TableCell>
                        </TableRow>
                        <TableRow className="border-b border-slate-200">
                          <TableCell className="text-center text-[10px] font-medium uppercase text-slate-500">
                            T.M. fech. (h)
                          </TableCell>
                          {data.regionals.map((regional) => (
                            <TableCell key={regional} className="text-center tabular-nums text-slate-700">
                              {hours(cellFor(regional).average_closing_hours)}
                            </TableCell>
                          ))}
                          <TableCell className="bg-slate-100 text-center tabular-nums text-slate-900">
                            {hours(row.total.average_closing_hours)}
                          </TableCell>
                        </TableRow>
                      </Fragment>
                    );
                  })}
                </Fragment>
              ))
            )}
            {showEmpty ? (
              <TableRow>
                <TableCell colSpan={totalColumns} className="py-14 text-center text-slate-500">
                  Nenhum grupo de SLA cadastrado. Cadastre os grupos em Configuração → SLA por
                  tecnologia para a matriz aparecer aqui.
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </CardContent>
      <div className="flex flex-wrap gap-3 border-t bg-slate-50 px-4 py-2 text-[10px] font-medium text-slate-600">
        <span className="text-emerald-700">Verde: SLA ≥ 80%</span>
        <span className="text-amber-700">Amarelo: 60% ≤ SLA &lt; 80%</span>
        <span className="text-red-700">Vermelho: SLA &lt; 60%</span>
      </div>
    </Card>
  );
}
