"use client";

import { Sparkles } from "lucide-react";

import { OverviewBlock, type OverviewBlockState } from "@/components/overview/overview-block";
import { formatInteger, formatPercent } from "@/lib/format";
import type { SupportOpaBotHumanMetrics } from "@/lib/types";

const ROWS: { key: string; label: string; color: string; pick: (data: SupportOpaBotHumanMetrics) => number }[] = [
  { key: "bot", label: "Com IA / bot", color: "bg-blue-500", pick: (data) => data.with_bot },
  { key: "human", label: "Com atendimento humano", color: "bg-teal-500", pick: (data) => data.reached_human },
  { key: "handoff", label: "Transferências IA → humano", color: "bg-violet-400", pick: (data) => data.bot_to_human_handoff },
  { key: "unclassified", label: "Sem classificação", color: "bg-slate-300", pick: (data) => data.unclassified_attendances },
];

/**
 * IA × Humano do Suporte Interno. Os quatro números já vêm calculados do backend
 * (`bot_human` de `/support/opa/overview`); a barra é só a proporção sobre o total de
 * atendimentos do mesmo recorte. As linhas se sobrepõem (um atendimento com bot pode chegar ao
 * humano), por isso não somam 100% - o rodapé avisa.
 */
export function OverviewAiHumanCard({
  data,
  state,
}: {
  data: SupportOpaBotHumanMetrics | null;
  state?: OverviewBlockState;
}) {
  const total = data?.total_attendances ?? 0;
  return (
    <OverviewBlock
      eyebrow="Suporte Interno"
      title="IA × Humano"
      subtitle="Quem atendeu os atendimentos do período."
      badge={<Sparkles className="h-4 w-4 text-slate-400" aria-hidden="true" />}
      state={{ ...state, empty: !state?.loading && !state?.error && data !== null && total === 0 }}
      deniedLabel="Seu perfil não tem acesso ao Suporte Interno."
    >
      {data ? (
        <>
          <ul className="space-y-3.5">
            {ROWS.map((row) => {
              const value = row.pick(data);
              const share = total > 0 ? Math.min(100, (value / total) * 100) : 0;
              return (
                <li key={row.key}>
                  <div className="flex items-baseline justify-between gap-3 text-xs">
                    <span className="min-w-0 truncate font-medium text-slate-700">{row.label}</span>
                    <span className="shrink-0 tabular-nums">
                      <span className="font-bold text-slate-900">{formatInteger(value)}</span>
                      <span className="ml-1.5 text-slate-500">{formatPercent(share)}</span>
                    </span>
                  </div>
                  <div
                    className="mt-1.5 h-2 overflow-hidden rounded-full bg-slate-100"
                    role="meter"
                    aria-label={row.label}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={Math.round(share)}
                  >
                    <div className={`h-full rounded-full ${row.color}`} style={{ width: `${share}%` }} />
                  </div>
                </li>
              );
            })}
          </ul>
          <p className="mt-4 text-[11px] text-slate-500">
            Total de {formatInteger(total)} atendimentos. As linhas se sobrepõem (um atendimento com bot pode chegar ao humano),
            então não somam 100%.
          </p>
        </>
      ) : null}
    </OverviewBlock>
  );
}
