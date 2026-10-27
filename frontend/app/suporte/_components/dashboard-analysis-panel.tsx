"use client";

import type { ReactNode } from "react";

import { OverviewBlock } from "@/components/overview/overview-block";

import { DAY_COLUMNS, WEEK_COLUMNS } from "./dashboard-analysis";
import type { AnalysisCell, AnalysisTone, DashboardAnalysis } from "./dashboard-analysis";

// Bloco "Análise do período" dos Indicadores do Suporte: o período dia a dia, o dia de maior aumento com os motivos,
// as semanas do mês e a projeção de fechamento do mês. Tudo em tabela; o conteúdo vem de `dashboard-analysis.ts`.

const CELL_TONE: Record<AnalysisTone, string> = {
  ok: "bg-emerald-100 text-emerald-800",
  warn: "bg-amber-100 text-amber-800",
  bad: "bg-red-100 text-red-700",
  none: "text-slate-800",
};
const TEXT_TONE: Record<AnalysisTone, string> = {
  ok: "text-emerald-700",
  warn: "text-amber-700",
  bad: "text-red-600",
  none: "text-slate-500",
};

const TH = "px-2.5 py-1.5 text-left text-[10px] font-semibold uppercase tracking-wide text-slate-500";
const TD = "px-2.5 py-1.5";

function Frame({ title, caption, children }: { title: string; caption?: string; children: ReactNode }) {
  return (
    <div className="min-w-0 rounded-xl border border-slate-200 bg-white p-3">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">{title}</p>
      {caption ? <p className="mt-0.5 text-xs text-slate-600">{caption}</p> : null}
      <div className="mt-2 overflow-x-auto">{children}</div>
    </div>
  );
}

function Value({ cell }: { cell: AnalysisCell }) {
  return <td className={`${TD} text-right font-semibold tabular-nums ${CELL_TONE[cell.tone]}`}>{cell.text}</td>;
}

export function DashboardAnalysisPanel({ analysis }: { analysis: DashboardAnalysis }) {
  const { days, peak, weeks, projection } = analysis;
  return (
    <OverviewBlock eyebrow="Análise" title="Análise do período" subtitle="Verde bateu a meta, amarelo está perto e vermelho está longe. Os filtros de departamento e colaborador valem para o OPA.">
      <div className="grid gap-3">
        <div className="grid gap-3 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
          <Frame title="Dia a dia do período" caption="O dia de maior aumento de atendimentos está marcado.">
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <th className={TH}>Dia</th>
                  {DAY_COLUMNS.map((column) => (
                    <th key={column} className={`${TH} text-right`}>
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {days.map((day) => (
                  <tr key={day.label} className="border-t border-slate-100">
                    <td className={`${TD} font-semibold capitalize text-slate-800`}>
                      {day.label}
                      {day.peak ? <span className="ml-1.5 rounded-full bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold normal-case text-red-700">pico</span> : null}
                    </td>
                    {day.cells.map((cell, index) => (
                      <Value key={DAY_COLUMNS[index]} cell={cell} />
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </Frame>

          <Frame title="Dia de maior aumento" caption={peak.headline}>
            {peak.reasons.length ? (
              <table className="w-full text-sm">
                <thead>
                  <tr>
                    <th className={TH}>Motivo</th>
                    <th className={`${TH} text-right`}>No dia</th>
                    <th className={`${TH} text-right`}>Habitual/dia</th>
                  </tr>
                </thead>
                <tbody>
                  {peak.reasons.map((item) => (
                    <tr key={item.reason} className="border-t border-slate-100">
                      <td className={`${TD} ${item.heavy ? "font-semibold text-slate-900" : "text-slate-700"}`}>
                        {item.reason}
                        {item.heavy ? <span className="ml-1.5 rounded-full bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold text-red-700">puxou o aumento</span> : null}
                      </td>
                      <td className={`${TD} text-right font-semibold tabular-nums text-slate-900`}>{item.count}</td>
                      <td className={`${TD} text-right tabular-nums text-slate-600`}>{new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(item.usual)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
            {peak.note ? <p className="mt-2 text-xs text-slate-500">{peak.note}</p> : null}
          </Frame>
        </div>

        <Frame title="Semana a semana do mês" caption="Semanas de domingo a sábado, cortadas nos limites do mês.">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className={TH}>Semana</th>
                {WEEK_COLUMNS.map((column) => (
                  <th key={column} className={`${TH} text-right`}>
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {weeks.map((week) => (
                <tr key={week.label} className={`border-t border-slate-100 ${week.muted ? "opacity-50" : ""}`}>
                  <td className={`${TD} font-semibold text-slate-800`}>
                    {week.label}
                    <span className="block text-[11px] font-normal text-slate-500">
                      {week.range}
                      {week.note ? ` · ${week.note}` : ""}
                    </span>
                  </td>
                  {week.cells.map((cell, index) => (
                    <Value key={WEEK_COLUMNS[index]} cell={cell} />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </Frame>

        {projection ? (
          <Frame title="Projeção de fechamento do mês" caption={projection.range}>
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <th className={TH}>Indicador</th>
                  <th className={`${TH} text-right`}>Mês até agora</th>
                  <th className={`${TH} text-right`}>Fecha em (ritmo atual)</th>
                  <th className={`${TH} text-right`}>Meta</th>
                  <th className={`${TH} text-right`}>Resto do mês precisa fechar</th>
                  <th className={TH}>Situação</th>
                </tr>
              </thead>
              <tbody>
                {projection.rows.map((row) => (
                  <tr key={row.name} className="border-t border-slate-100">
                    <td className={`${TD} font-semibold text-slate-800`}>{row.name}</td>
                    <td className={`${TD} text-right tabular-nums text-slate-900`}>{row.month}</td>
                    <td className={`${TD} text-right font-semibold tabular-nums text-slate-900`}>{row.pace}</td>
                    <td className={`${TD} text-right tabular-nums text-slate-600`}>{row.target}</td>
                    <td className={`${TD} text-right font-semibold tabular-nums text-slate-900`}>{row.required}</td>
                    <td className={`${TD} font-semibold ${TEXT_TONE[row.tone]}`}>{row.verdict}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-[11px] text-slate-500">
              Médias do mês são ponderadas pelo volume. O volume do resto do mês é estimado pelo ritmo do período selecionado; &quot;Resto do mês precisa fechar&quot; é o valor que as semanas que faltam
              precisam ter, juntas, para a média do mês terminar na meta.
            </p>
          </Frame>
        ) : null}
      </div>
    </OverviewBlock>
  );
}
