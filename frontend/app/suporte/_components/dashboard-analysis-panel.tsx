"use client";

import { OverviewBlock } from "@/components/overview/overview-block";

import type { AnalysisTone, DashboardAnalysis } from "./dashboard-analysis";

// Bloco "Análise do período" dos Indicadores do Suporte: três quadros em tabela, um por pergunta
// (o que subiu, o que falta na semana, o que o resto do mês precisa fechar). O texto vem de `dashboard-analysis.ts`.

const TONE_TEXT: Record<AnalysisTone, string> = {
  ok: "text-emerald-700",
  warn: "text-amber-700",
  bad: "text-red-600",
  none: "text-slate-500",
};

const TH = "px-2.5 py-1.5 text-left text-[10px] font-semibold uppercase tracking-wide text-slate-500";

function Frame({ title, caption, children }: { title: string; caption?: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0 rounded-xl border border-slate-200 bg-white p-3">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">{title}</p>
      {caption ? <p className="mt-0.5 text-xs text-slate-600">{caption}</p> : null}
      <div className="mt-2">{children}</div>
    </div>
  );
}

export function DashboardAnalysisPanel({ analysis }: { analysis: DashboardAnalysis }) {
  const { peak, goals, month } = analysis;
  return (
    <OverviewBlock eyebrow="Análise" title="Análise do período" subtitle="Gerada dos números do período; os filtros de departamento e colaborador valem para os indicadores do OPA.">
      <div className="grid gap-3 xl:grid-cols-3">
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
                    <td className={`px-2.5 py-1.5 ${item.heavy ? "font-semibold text-slate-900" : "text-slate-700"}`}>
                      {item.reason}
                      {item.heavy ? <span className="ml-1.5 rounded-full bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold text-red-700">puxou o aumento</span> : null}
                    </td>
                    <td className="px-2.5 py-1.5 text-right font-semibold tabular-nums text-slate-900">{item.count}</td>
                    <td className="px-2.5 py-1.5 text-right tabular-nums text-slate-600">{new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(item.usual)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          {peak.note ? <p className="mt-2 text-xs text-slate-500">{peak.note}</p> : null}
        </Frame>

        <Frame title="Meta da próxima semana" caption="O que cada indicador precisa mudar para bater a meta.">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className={TH}>Indicador</th>
                <th className={`${TH} text-right`}>Agora</th>
                <th className={`${TH} text-right`}>Meta</th>
                <th className={TH}>Ajuste</th>
              </tr>
            </thead>
            <tbody>
              {goals.map((row) => (
                <tr key={row.name} className="border-t border-slate-100">
                  <td className="px-2.5 py-1.5 font-semibold text-slate-800">{row.name}</td>
                  <td className="px-2.5 py-1.5 text-right tabular-nums text-slate-900">{row.current}</td>
                  <td className="px-2.5 py-1.5 text-right tabular-nums text-slate-600">{row.target}</td>
                  <td className={`px-2.5 py-1.5 font-semibold ${TONE_TEXT[row.tone]}`}>{row.action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Frame>

        {month ? (
          <Frame title="Fechar o mês na meta" caption={month.range}>
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <th className={TH}>Indicador</th>
                  <th className={`${TH} text-right`}>Mês até agora</th>
                  <th className={`${TH} text-right`}>Meta</th>
                </tr>
              </thead>
              <tbody>
                {month.rows.map((row) => (
                  <tr key={row.name} className="border-t border-slate-100 align-top">
                    <td className="px-2.5 py-1.5 font-semibold text-slate-800">
                      {row.name}
                      <span className={`block text-xs font-semibold ${TONE_TEXT[row.tone]}`}>{row.verdict}</span>
                    </td>
                    <td className="px-2.5 py-1.5 text-right tabular-nums text-slate-900">{row.monthValue}</td>
                    <td className="px-2.5 py-1.5 text-right tabular-nums text-slate-600">{row.target}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-[11px] text-slate-500">Estimado pelo ritmo de atendimentos do mês até agora.</p>
          </Frame>
        ) : null}
      </div>
    </OverviewBlock>
  );
}
