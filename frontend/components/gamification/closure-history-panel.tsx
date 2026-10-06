"use client";

import { Fragment, useEffect, useState } from "react";
import { ChevronDown, History, Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Pagination } from "@/components/ui/pagination";
import { EmptyState } from "@/components/ui/empty-state";
import { MetricCard } from "@/components/gamification/config-ui";
import { ChartPanel, BarComparison } from "@/components/gamification/chart-panel";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatAnnulledPoints, formatDateTime, formatInteger, formatMoney, formatPoints } from "@/lib/format";
import { regionalName } from "@/lib/regional";
import type { CalculationRunHistory } from "@/lib/types";

type Props = { runs: CalculationRunHistory[] };

export function ClosureHistoryPanel({ runs }: Props) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<number | null>(null);
  useEffect(() => { setPage(1); }, [query, runs]);
  const latest = runs[0];
  const term = query.trim().toLocaleLowerCase("pt-BR");
  const filtered = runs.filter((run) => [String(run.id), `${run.reference_month}/${run.reference_year}`, run.regional ? regionalName(run.regional) : "Todas", run.source_filename ?? ""].some((value) => value.toLocaleLowerCase("pt-BR").includes(term)));
  const totalPages = Math.max(1, Math.ceil(filtered.length / 15));
  const currentPage = Math.min(page, totalPages);
  const recent = runs.slice(0, 8);
  return <div className="grid min-w-0 gap-4">
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-panel">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="mb-2 flex items-center gap-2 text-xs font-medium text-primary"><History className="h-4 w-4" /> Memória de cálculo</div><h2 className="text-xl font-semibold text-slate-950">Histórico de fechamentos</h2><p className="mt-1 text-sm text-slate-500">Consulte apurações anteriores e confira a origem de cada resultado.</p></div>{latest ? <Badge>Última apuração #{latest.id}</Badge> : null}</div>
      {latest ? <div className="mt-5 grid grid-cols-2 gap-3 xl:grid-cols-4"><MetricCard title="Último período" value={`${latest.reference_month}/${latest.reference_year}`} /><MetricCard title="O.S apuradas" value={formatInteger(latest.service_orders_count)} /><MetricCard title="Pontos finais" value={formatPoints(latest.final_points)} /><MetricCard title="Valor a pagar" value={formatMoney(latest.estimated_payment)} /></div> : null}
    </section>
    {recent.length > 1 ? <ChartPanel title="Valores das últimas apurações" description="Cada barra é um recálculo salvo. Apurações do mesmo mês podem ter recortes diferentes; os valores não devem ser somados." columns={["Apuração", "Período", "Valor a pagar"]} rows={recent.map((run) => [`#${run.id}`, `${run.reference_month}/${run.reference_year}`, formatMoney(run.estimated_payment)])}><BarComparison items={recent.map((run) => ({ label: `#${run.id} · ${run.reference_month}/${run.reference_year}`, detail: run.regional ? regionalName(run.regional) : "Todas as filiais", value: run.estimated_payment, formatted: formatMoney(run.estimated_payment) }))} /></ChartPanel> : null}
    <section className="min-w-0 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-panel">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 p-4"><div><h3 className="text-sm font-semibold text-slate-900">Apurações registradas</h3><p className="mt-1 text-xs text-slate-500">{filtered.length} resultado(s) · expanda uma linha para ver a memória de cálculo</p></div><div className="relative w-full sm:w-80"><Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-400" /><Input aria-label="Buscar apuração" placeholder="Apuração, período, filial ou arquivo" value={query} onChange={(event) => setQuery(event.target.value)} className="pl-9" /></div></div>
      <Table><TableHeader><TableRow><TableHead>Apuração / período</TableHead><TableHead>Filial</TableHead><TableHead>Calculado em</TableHead><TableHead className="text-right">O.S</TableHead><TableHead className="text-right">Pontos finais</TableHead><TableHead className="text-right">Valor a pagar</TableHead><TableHead><span className="sr-only">Detalhes</span></TableHead></TableRow></TableHeader><TableBody>
        {filtered.slice((currentPage - 1) * 15, currentPage * 15).map((run) => <Fragment key={run.id}><TableRow><TableCell className="min-w-32"><span className="font-semibold text-slate-950">#{run.id}</span><p className="mt-1 text-xs text-slate-500">{run.reference_month}/{run.reference_year}</p></TableCell><TableCell className="min-w-40">{run.regional ? regionalName(run.regional) : "Todas as filiais"}</TableCell><TableCell className="min-w-40 text-xs text-slate-500">{formatDateTime(run.created_at)}</TableCell><TableCell className="text-right">{formatInteger(run.service_orders_count)}</TableCell><TableCell className="whitespace-nowrap text-right font-medium">{formatPoints(run.final_points)}</TableCell><TableCell className="whitespace-nowrap text-right font-semibold text-primary">{formatMoney(run.estimated_payment)}</TableCell><TableCell><Button size="sm" variant="ghost" aria-label={`Detalhes da apuração ${run.id}`} aria-expanded={expanded === run.id} aria-controls={`run-details-${run.id}`} onClick={() => setExpanded(expanded === run.id ? null : run.id)}><ChevronDown className={`h-4 w-4 transition-transform ${expanded === run.id ? "rotate-180" : ""}`} /></Button></TableCell></TableRow>{expanded === run.id ? <TableRow id={`run-details-${run.id}`} className="bg-slate-50/70"><TableCell colSpan={7}><dl className="grid gap-4 p-2 sm:grid-cols-2 xl:grid-cols-3">{[
          ["Arquivo de origem", run.source_filename ?? "Não informado"],
          ["Versão da regra", run.rules_version_id ? `#${run.rules_version_id}` : "Não informada"],
          ["Colaboradores", formatInteger(run.collaborators_count)],
          ["Pontos brutos", formatPoints(run.gross_points)],
          ["Pontos anulados", formatAnnulledPoints(run.penalty_points)],
          ["Top colaborador", `${run.top_collaborator_name ?? "Não informado"}${run.top_collaborator_points != null ? ` · ${formatPoints(run.top_collaborator_points)}` : ""}`]
        ].map(([label, value]) => <div key={label} className="min-w-0"><dt className="text-xs text-slate-500">{label}</dt><dd className="mt-1 break-words text-sm font-medium text-slate-800">{value}</dd></div>)}</dl></TableCell></TableRow> : null}</Fragment>)}
        {!filtered.length ? <TableRow><TableCell colSpan={7}><EmptyState variant="plain" title={runs.length ? "Nenhuma apuração encontrada" : "Ainda não há apurações salvas"} description={runs.length ? "Ajuste a busca para consultar outro período ou arquivo." : "O histórico aparecerá após a primeira apuração de um período."} /></TableCell></TableRow> : null}
      </TableBody></Table>
      <Pagination className="border-t border-slate-100 p-4" page={currentPage} totalPages={totalPages} totalItems={filtered.length} itemLabel={filtered.length === 1 ? "apuração" : "apurações"} onPageChange={setPage} />
    </section>
  </div>;
}
