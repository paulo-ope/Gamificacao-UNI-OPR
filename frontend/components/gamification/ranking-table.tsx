"use client";

import { useEffect, useState } from "react";
import { ChevronDown, FileSearch, LayoutList, Table2 } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Pagination } from "@/components/ui/pagination";
import { InfoHint } from "@/components/gamification/info-hint";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { pointValueFromTotals } from "@/lib/gamificacao-helpers";
import { regionalName } from "@/lib/regional";
import type { CollaboratorScore } from "@/lib/types";

const numberFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
const integerFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const moneyFormat = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

function healthBadgeClass(status: string) {
  const normalized = status.toLowerCase();
  if (normalized.includes("excel")) return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (normalized.includes("boa")) return "border-blue-200 bg-blue-50 text-uni-royal";
  if (normalized.includes("aten")) return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-red-200 bg-red-50 text-red-700";
}

function compactRegional(regional: string) {
  return regionalName(regional).replace(/^UNI\s*-\s*/i, "").replace(/\s+/g, " ").trim();
}

function formatPoints(value: number) {
  return `${numberFormat.format(value)} pts`;
}

function formatAnnulled(value: number) {
  return `${numberFormat.format(Math.abs(value))} pts anulados`;
}

function averagePointValue(score: CollaboratorScore) {
  return pointValueFromTotals(score.estimated_payment, score.final_points) ?? 0;
}

function finalPointsFormula(score: CollaboratorScore) {
  const subtotal = Math.round(score.net_points * score.health_multiplier * 100) / 100;
  const base = `${numberFormat.format(score.net_points)} líquidos × ${score.health_multiplier.toFixed(2)}x saúde = ${numberFormat.format(subtotal)} pts`;
  if (!score.balance_adjustment_points) {
    return base;
  }
  const signal = score.balance_adjustment_points < 0 ? "−" : "+";
  return `${base}, ${signal} ${numberFormat.format(Math.abs(score.balance_adjustment_points))} de garantia → ${numberFormat.format(score.final_points)} pts finais`;
}

function MiniMetric({
  label,
  value,
  tone = "default"
}: {
  label: string;
  value: string;
  tone?: "default" | "good" | "warning" | "danger" | "money";
}) {
  const toneClass =
    tone === "good"
      ? "text-emerald-700"
      : tone === "warning"
        ? "text-amber-700"
        : tone === "danger"
          ? "text-red-600"
          : tone === "money"
            ? "text-uni-royal"
            : "text-slate-950";

  return (
    <div className="min-w-0 rounded-lg bg-slate-50 px-3 py-2">
      <div className="text-[11px] font-medium leading-5 text-slate-500">{label}</div>
      <div className={`break-words text-sm font-semibold leading-5 tabular-nums ${toneClass}`}>{value}</div>
    </div>
  );
}

type RankingTableProps = {
  data: CollaboratorScore[];
  onViewOrders?: (score: CollaboratorScore) => void;
};

export function RankingTable({ data, onViewOrders }: RankingTableProps) {
  const [view, setView] = useState<"cards" | "table">("cards");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  useEffect(() => { setPage(1); }, [data]);
  const totalPages = Math.max(1, Math.ceil(data.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const offset = (currentPage - 1) * pageSize;
  const visible = data.slice(offset, offset + pageSize);
  if (!data.length) {
    return <EmptyState className="m-4" title="Nenhum colaborador encontrado" description="Experimente outro nome ou ajuste as filiais selecionadas para este período." />;
  }
  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-5 py-3 text-xs text-slate-500">
        <span><strong className="font-semibold text-slate-700">{integerFormat.format(data.length)}</strong> {data.length === 1 ? "colaborador" : "colaboradores"} no resultado</span>
        <div className="flex items-center gap-2"><span className="hidden sm:inline">Posição no recorte atual</span><div role="group" aria-label="Visualização do ranking" className="flex rounded-lg bg-slate-100 p-1"><Button size="sm" variant={view === "cards" ? "secondary" : "ghost"} aria-pressed={view === "cards"} onClick={() => setView("cards")}><LayoutList className="h-4 w-4" />Cartões</Button><Button size="sm" variant={view === "table" ? "secondary" : "ghost"} aria-pressed={view === "table"} onClick={() => setView("table")}><Table2 className="h-4 w-4" />Colunas</Button></div></div>
      </div>
      {view === "table" ? <Table><TableHeader><TableRow><TableHead>Posição</TableHead><TableHead>Colaborador / filial</TableHead><TableHead className="text-right">O.S</TableHead><TableHead className="text-right">Pontuadas</TableHead><TableHead className="text-right">Fora do prazo</TableHead><TableHead className="text-right">Saúde</TableHead><TableHead className="text-right">Pontos finais</TableHead><TableHead className="text-right">Valor a pagar</TableHead><TableHead><span className="sr-only">Extrato</span></TableHead></TableRow></TableHeader><TableBody>{visible.map((score, index) => <TableRow key={score.id}><TableCell className="font-semibold text-slate-500">{offset + index + 1}</TableCell><TableCell className="min-w-56"><p className="text-xs font-semibold text-slate-900">{score.collaborator_name}</p><p className="mt-1 text-xs text-slate-500">{compactRegional(score.regional)} · {score.role}</p></TableCell><TableCell className="text-right">{integerFormat.format(score.service_orders_count)}</TableCell><TableCell className="text-right">{integerFormat.format(score.scored_service_orders ?? 0)}</TableCell><TableCell className="text-right">{integerFormat.format(score.sla_out_service_orders ?? 0)}</TableCell><TableCell className="text-right"><Badge className={healthBadgeClass(score.health_status)}>{score.health_multiplier.toFixed(2)}x</Badge></TableCell><TableCell className="whitespace-nowrap text-right">{formatPoints(score.final_points)}</TableCell><TableCell className="whitespace-nowrap text-right font-semibold text-primary"><span className="inline-flex items-center gap-1">{moneyFormat.format(score.estimated_payment)}<InfoHint ariaLabel={`Cálculo de ${score.collaborator_name}`} description={finalPointsFormula(score)} /></span></TableCell><TableCell>{onViewOrders ? <Button size="sm" variant="ghost" aria-label={`Ver extrato de ${score.collaborator_name}`} onClick={() => onViewOrders(score)}><FileSearch className="h-4 w-4" />Extrato</Button> : null}</TableCell></TableRow>)}</TableBody></Table> : <div className="space-y-3 p-3 sm:p-4">
        {visible.map((score, index) => (
          <article key={score.id} className="rounded-xl border border-slate-200 bg-white shadow-panel transition-colors hover:border-blue-200">
            <div className="grid min-w-0 gap-4 p-4 xl:grid-cols-[minmax(180px,1fr)_minmax(280px,1.3fr)_minmax(200px,1fr)] xl:items-center">
              <div className="flex min-w-0 items-start gap-3">
                <span aria-label={`Posição ${offset + index + 1} no recorte`} className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-sm font-semibold tabular-nums ${offset + index < 3 ? "bg-blue-50 text-primary ring-1 ring-inset ring-blue-200" : "bg-slate-100 text-slate-600"}`}>
                  {offset + index + 1}
                </span>
                <div className="min-w-0">
                  <h3 className="text-sm font-semibold leading-5 text-slate-950">{score.collaborator_name}</h3>
                  <p className="mt-1 text-xs leading-5 text-slate-500">{score.role} · {compactRegional(score.regional)}</p>
                  <Badge className={`mt-2 ${healthBadgeClass(score.health_status)}`}>{score.health_multiplier.toFixed(2)}x saúde</Badge>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <MiniMetric label="Total de O.S" value={integerFormat.format(score.service_orders_count)} />
                <MiniMetric label="Pontuadas" value={integerFormat.format(score.scored_service_orders ?? 0)} tone="good" />
                <MiniMetric label="Fora do prazo" value={integerFormat.format(score.sla_out_service_orders ?? 0)} tone="warning" />
              </div>
              <div className="flex min-w-0 flex-wrap items-center justify-between gap-3 xl:justify-end">
                <div className="min-w-0 xl:text-right">
                  <div className="flex items-center gap-1.5 xl:justify-end">
                    <span className="break-words text-xl font-semibold tabular-nums text-primary">{moneyFormat.format(score.estimated_payment)}</span>
                    <InfoHint ariaLabel={`Como chegamos no valor de ${score.collaborator_name}`} description={finalPointsFormula(score)} side="left" />
                  </div>
                  <p className="mt-1 text-xs text-slate-500">{formatPoints(score.final_points)} {score.balance_adjustment_points ? "após garantia" : "finais"}</p>
                  <p className="mt-1 text-xs text-slate-500">{moneyFormat.format(averagePointValue(score))}/pt médio</p>
                </div>
                {onViewOrders ? <Button type="button" variant="outline" size="sm" aria-label={`Ver extrato de ${score.collaborator_name}`} onClick={() => onViewOrders(score)}><FileSearch className="h-4 w-4" /> Ver extrato</Button> : null}
              </div>
            </div>
            <details className="group border-t border-slate-100">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-2 rounded-b-xl px-4 py-2.5 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-50 [&::-webkit-details-marker]:hidden">
                <span>Detalhar indicadores e pontuação</span><ChevronDown className="h-4 w-4 shrink-0 transition-transform group-open:rotate-180" />
              </summary>
              <div className="grid grid-cols-2 gap-2 px-4 pb-4 sm:grid-cols-3 xl:grid-cols-5">
                <MiniMetric label="O.S sem regra" value={integerFormat.format(score.unscored_service_orders ?? 0)} tone="warning" />
                <MiniMetric label="O.S anuladas" value={integerFormat.format(score.penalized_service_orders ?? 0)} tone="danger" />
                <MiniMetric label="Pontos brutos" value={formatPoints(score.gross_points)} />
                <MiniMetric label="Pontos anulados" value={formatAnnulled(score.penalty_points)} tone="danger" />
                <MiniMetric label="Pontos líquidos" value={formatPoints(score.net_points)} />
              </div>
              {score.balance_adjustment_points ? <p className="px-4 pb-4 text-xs font-medium text-red-700">Ajuste de garantia: {numberFormat.format(score.balance_adjustment_points)} pts</p> : null}
            </details>
          </article>
        ))}
      </div>
      }
      <Pagination className="border-t border-slate-200 bg-slate-50/60 px-4 py-4" page={currentPage} totalPages={totalPages} totalItems={data.length} itemLabel={data.length === 1 ? "colaborador" : "colaboradores"} pageSize={pageSize} pageSizeOptions={[20, 50, 100]} onPageSizeChange={(size) => { setPageSize(size); setPage(1); }} onPageChange={setPage} />
    </div>
  );
}
