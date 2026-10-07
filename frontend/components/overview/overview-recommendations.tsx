"use client";

import { ChevronDown, Target } from "lucide-react";
import { useState } from "react";

import { Card } from "@/components/ui/card";
import type { OverviewBlockState } from "@/components/overview/overview-block";
import type { OperationAttentionPoints } from "@/lib/operations-api";
import { cn } from "@/lib/utils";

/**
 * Recomendações gerais do recorte da Visão Geral: uma ação por problema que os Pontos de atenção
 * apontaram. Texto fixo vindo do backend (`operations/attention.py::RECOMMENDATIONS`) - sem IA e
 * sem recalcular nada aqui. Recolhido por padrão, mesmo padrão do card de Pontos de atenção, para
 * não ocupar espaço da tela.
 */
export function OverviewRecommendations({
  data,
  state,
}: {
  data: OperationAttentionPoints | null;
  state?: OverviewBlockState;
}) {
  const [open, setOpen] = useState(false);
  const items = data?.recommendations ?? [];
  const canExpand = !state?.loading && !state?.error;

  let summary: string;
  if (state?.loading) summary = "Carregando...";
  else if (state?.error) summary = "Indisponível";
  else if (items.length === 0) summary = "Nenhuma recomendação neste recorte";
  else summary = `${items.length} ${items.length === 1 ? "recomendação" : "recomendações"}`;

  return (
    <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
      <button
        type="button"
        onClick={() => canExpand && setOpen((current) => !current)}
        aria-expanded={open}
        aria-controls="overview-recommendations-list"
        disabled={!canExpand}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left disabled:cursor-default"
      >
        <span className="flex min-w-0 items-center gap-2.5">
          <Target className="h-4 w-4 shrink-0 text-uni-royal" />
          <span className="text-sm font-semibold text-slate-950">Recomendações</span>
          <span className="truncate rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-[10px] font-semibold text-slate-600">
            {summary}
          </span>
        </span>
        {canExpand ? (
          <ChevronDown className={cn("h-4 w-4 shrink-0 text-slate-400 transition-transform", open && "rotate-180")} />
        ) : null}
      </button>

      {state?.error ? <p className="border-t border-slate-100 px-4 py-2.5 text-xs text-amber-800">{state.error}</p> : null}

      {open && canExpand ? (
        <div id="overview-recommendations-list" className="border-t border-slate-100 px-4 py-3">
          {items.length === 0 ? (
            <p className="text-sm text-slate-600">Sem pontos de atenção, então nada a recomendar neste recorte.</p>
          ) : (
            <ol className="space-y-2.5">
              {items.map((item, index) => (
                <li key={item.rule} className="flex items-start gap-2.5">
                  <span
                    className={cn(
                      "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-bold",
                      item.severity === "critical" ? "bg-rose-100 text-rose-700" : "bg-amber-100 text-amber-700",
                    )}
                  >
                    {index + 1}
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-slate-900">{item.problem}</p>
                    <p className="text-xs text-slate-600">{item.action}</p>
                  </div>
                </li>
              ))}
            </ol>
          )}
          <p className="mt-3 text-[11px] text-slate-500">
            Sugestões fixas por tipo de problema, na ordem de gravidade - não são uma análise de causa.
          </p>
        </div>
      ) : null}
    </Card>
  );
}
