"use client";

import { CalendarDays, Clock3, Trophy } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatAnnulledPoints, formatDateTime, formatInteger, formatMoney, formatPoints } from "@/lib/format";
import { regionalName } from "@/lib/regional";
import type { CalculationRunHistory } from "@/lib/types";

type Props = {
  runs: CalculationRunHistory[];
};

export function ClosureHistoryPanel({ runs }: Props) {
  const latest = runs[0];

  return (
    <section className="panel flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="panel-header shrink-0 bg-slate-50/70">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-700">
            <Clock3 className="h-5 w-5" />
          </div>
          <div>
            <h2 className="panel-title">Histórico de fechamentos</h2>
            <p className="panel-subtitle">Cada recálculo fica salvo como uma apuração, com período, valor do ponto e resultado geral.</p>
          </div>
        </div>
        {latest ? (
          <Badge className="border-teal-200 bg-teal-50 text-teal-700">
            Última apuração #{latest.id} - {latest.reference_month}/{latest.reference_year}
          </Badge>
        ) : null}
      </div>

      {latest ? (
        <div className="grid shrink-0 gap-3 border-b bg-white p-4 md:grid-cols-5">
          <div className="rounded-lg border bg-slate-50/70 p-3">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase text-slate-500">
              <CalendarDays className="h-4 w-4" />
              Período
            </div>
            <div className="mt-2 text-lg font-semibold text-slate-950">
              {latest.reference_month}/{latest.reference_year}
            </div>
          </div>
          <div className="rounded-lg border bg-slate-50/70 p-3">
            <div className="text-xs font-semibold uppercase text-slate-500">Total de O.S</div>
            <div className="mt-2 text-lg font-semibold text-slate-950">{formatInteger(latest.service_orders_count)} O.S</div>
          </div>
          <div className="rounded-lg border bg-slate-50/70 p-3">
            <div className="text-xs font-semibold uppercase text-slate-500">Pontos finais</div>
            <div className="mt-2 text-lg font-semibold text-slate-950">{formatPoints(latest.final_points)}</div>
          </div>
          <div className="rounded-lg border bg-slate-50/70 p-3">
            <div className="text-xs font-semibold uppercase text-slate-500">Arquivo base</div>
            <div className="mt-2 truncate text-lg font-semibold text-slate-950" title={latest.source_filename ?? ""}>
              {latest.source_filename ?? "-"}
            </div>
          </div>
          <div className="rounded-lg border bg-slate-50/70 p-3">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase text-slate-500">
              <Trophy className="h-4 w-4" />
              Top colaborador
            </div>
            <div className="mt-2 truncate text-lg font-semibold text-slate-950" title={latest.top_collaborator_name ?? ""}>
              {latest.top_collaborator_name ?? "-"}
            </div>
          </div>
        </div>
      ) : null}

      <div className="table-frame min-h-0 flex-1 overflow-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Apuração</TableHead>
              <TableHead>Período</TableHead>
              <TableHead>Regional</TableHead>
              <TableHead>Data do cálculo</TableHead>
              <TableHead>Arquivo</TableHead>
              <TableHead>Versão da regra</TableHead>
              <TableHead>O.S</TableHead>
              <TableHead>Colab.</TableHead>
              <TableHead>Pontos brutos</TableHead>
              <TableHead>Pontos anulados</TableHead>
              <TableHead>Pontos finais</TableHead>
              <TableHead>Valor a ser pago</TableHead>
              <TableHead>Top colaborador</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {runs.map((run) => (
              <TableRow key={run.id}>
                <TableCell className="font-semibold">#{run.id}</TableCell>
                <TableCell>
                  {run.reference_month}/{run.reference_year}
                </TableCell>
                <TableCell className="min-w-44">{run.regional ? regionalName(run.regional) : "Todas"}</TableCell>
                <TableCell className="min-w-40">{formatDateTime(run.created_at)}</TableCell>
                <TableCell className="max-w-56 truncate" title={run.source_filename ?? ""}>
                  {run.source_filename ?? "-"}
                </TableCell>
                <TableCell>{run.rules_version_id ? `#${run.rules_version_id}` : "-"}</TableCell>
                <TableCell>{formatInteger(run.service_orders_count)} O.S</TableCell>
                <TableCell>{formatInteger(run.collaborators_count)} colaboradores</TableCell>
                <TableCell>{formatPoints(run.gross_points)}</TableCell>
                <TableCell className="text-red-600">{formatAnnulledPoints(run.penalty_points)}</TableCell>
                <TableCell className="font-semibold">{formatPoints(run.final_points)}</TableCell>
                <TableCell className="font-semibold text-teal-700">{formatMoney(run.estimated_payment)}</TableCell>
                <TableCell className="min-w-56">
                  <div className="truncate font-medium text-slate-950" title={run.top_collaborator_name ?? ""}>
                    {run.top_collaborator_name ?? "-"}
                  </div>
                  {run.top_collaborator_points != null ? (
                    <div className="text-xs text-slate-500">{formatPoints(run.top_collaborator_points)}</div>
                  ) : null}
                </TableCell>
              </TableRow>
            ))}
            {runs.length === 0 ? (
              <TableRow>
                <TableCell colSpan={13} className="py-8 text-center text-sm text-slate-500">
                  Nenhuma apuração salva ainda. Recalcule um período para criar o primeiro histórico.
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </div>
    </section>
  );
}


