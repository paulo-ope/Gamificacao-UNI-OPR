"use client";

import { ChevronDown } from "lucide-react";
import { useState } from "react";

import { deltaPresentation } from "@/components/ui/summary-metric";
import { formatHours, formatInteger, formatPercent } from "@/lib/format";
import type {
  OperationRegionalWeeklyComparison,
  OperationWeeklyComparisonItem,
  OperationWeeklyMeasures,
} from "@/lib/operations-api";
import { percentChange } from "@/lib/period";
import { cn } from "@/lib/utils";

type Measure = {
  key: keyof OperationWeeklyMeasures;
  label: string;
  format: (value: number | null) => string;
  /** `true`: subir é bom; `false`: subir é ruim; `null`: neutro (demanda). */
  goodWhenUp: boolean | null;
  /** SLA já é percentual: a variação é em pontos percentuais, não % sobre %. */
  points?: boolean;
  needsSla?: boolean;
};

const MEASURES: Measure[] = [
  { key: "opened", label: "Abertas", format: formatInteger, goodWhenUp: null },
  { key: "completed", label: "Finalizadas", format: formatInteger, goodWhenUp: true },
  { key: "sla_rate", label: "SLA", format: formatPercent, goodWhenUp: true, points: true, needsSla: true },
  { key: "average_closing_hours", label: "TMA", format: formatHours, goodWhenUp: false, needsSla: true },
];

const compactNumber = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });

function formatDay(iso: string) {
  const [, month, day] = iso.split("-");
  return `${day}/${month}`;
}

function variation(measure: Measure, current: number | null, previous: number | null) {
  if (current === null || previous === null) return null;
  const value = measure.points
    ? Math.round((current - previous) * 10) / 10
    : percentChange(current, previous);
  if (value === null) return null;
  const { className } = deltaPresentation({ value, goodWhenUp: measure.goodWhenUp, againstLabel: "" });
  const text = `${value > 0 ? "+" : ""}${compactNumber.format(value)}${measure.points ? " p.p." : "%"}`;
  return { text, className };
}

function MeasureCell({ measure, row }: { measure: Measure; row: OperationWeeklyComparisonItem }) {
  const current = row.current[measure.key];
  const previous = row.previous[measure.key];
  const delta = variation(measure, current, previous);
  return (
    <td className="px-2 py-2 text-right align-top tabular-nums">
      <span className="block text-sm font-semibold text-slate-800">{measure.format(current)}</span>
      <span className="block text-[10px] leading-3 text-slate-400">ant. {measure.format(previous)}</span>
      <span className={cn("block text-[10px] font-semibold leading-3", delta?.className ?? "text-slate-400")}>
        {delta?.text ?? "—"}
      </span>
    </td>
  );
}

/**
 * Comparativo das regionais: última semana fechada (domingo a sábado) contra a anterior a ela. A
 * janela é fixa e calculada no backend - o período do filtro da tela não interfere; os
 * demais filtros (regional, setor, modelo de equipe) valem.
 */
export function OverviewRegionalWeekly({ data }: { data: OperationRegionalWeeklyComparison | null }) {
  const [expanded, setExpanded] = useState(false);
  if (!data || !data.items.length) {
    return <p className="mt-4 text-xs text-slate-500">Sem movimento nas duas semanas para o recorte atual.</p>;
  }
  const measures = MEASURES.filter((measure) => !measure.needsSla || data.sla_available);
  // O total fica sempre na primeira linha: recolhido, o card mostra só o resumo geral; as regionais
  // abrem sob demanda para o bloco não ficar maior que os vizinhos da mesma linha.
  const rows = expanded ? [data.total, ...data.items] : [data.total];
  const regionalCount = data.items.length;
  return (
    <section aria-label="Comparativo das regionais: última semana contra a anterior" className="mt-4">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-3">
        <h3 className="text-xs font-semibold text-slate-700">Última semana × anterior</h3>
        <p className="text-[10px] text-slate-500">
          {formatDay(data.current_from)} a {formatDay(data.current_to)} contra {formatDay(data.previous_from)} a{" "}
          {formatDay(data.previous_to)}
        </p>
      </div>
      <div className={cn("overflow-x-auto", expanded && "max-h-80 overflow-y-auto")}>
        <table className="w-full min-w-[420px] border-collapse text-left">
          <thead className="sticky top-0 z-10 bg-white">
            <tr className="border-b border-slate-200 text-[10px] uppercase tracking-wide text-slate-500">
              <th scope="col" className="px-2 py-1 font-semibold">
                {expanded ? "Regional" : ""}
              </th>
              {measures.map((measure) => (
                <th key={measure.key} scope="col" className="px-2 py-1 text-right font-semibold">
                  {measure.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr
                key={row.regional}
                className={cn("border-b border-slate-100", index === 0 && "bg-slate-50")}
              >
                <th scope="row" className="px-2 py-2 align-top text-xs font-medium text-slate-800">
                  {index === 0 ? "Todas as regionais" : row.regional}
                </th>
                {measures.map((measure) => (
                  <MeasureCell key={measure.key} measure={measure} row={row} />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
        className="mt-2 inline-flex items-center gap-1 rounded text-[11px] font-semibold text-uni-royal hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {expanded ? "Recolher regionais" : `Ver as ${regionalCount} regionais`}
        <ChevronDown className={cn("h-3 w-3 transition-transform", expanded && "rotate-180")} aria-hidden="true" />
      </button>
      <p className="mt-1 text-[10px] leading-4 text-slate-500">
        Variação sobre a semana anterior, ambas fechadas (domingo a sábado). Verde melhorou, vermelho piorou; abertas é só demanda
        (sem cor).
      </p>
    </section>
  );
}
