"use client";

import { ChevronDown, Info, TriangleAlert } from "lucide-react";
import { useState } from "react";

import { OverviewBlock, type OverviewBlockState } from "@/components/overview/overview-block";
import { formatIsoDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { OperationAttentionPoints } from "@/lib/operations-api";

const RULE_LABELS: Record<string, string> = {
  sla_below_target: "SLA geral",
  regional_sla_below_target: "SLA por regional",
  overdue_backlog_share: "Backlog vencido",
  completed_drop: "Comparação com o período anterior",
  inflow_exceeds_output: "Entrada x saída",
};

/**
 * Pontos de atenção do recorte da Visão Geral, sempre à vista no bloco de monitoramento. Nenhuma
 * regra roda aqui: o backend (`operations/attention.py`) avalia e devolve cada achado com o número
 * que o justifica; a tela só exibe. O rodapé diz quantas regras foram verificadas e quais ficaram
 * de fora, porque "nenhum achado" só tem valor se o painel disser o que olhou. O `id` é o destino
 * do link "+N alertas" do Status geral.
 */
export function OverviewAttentionPoints({
  data,
  state,
}: {
  data: OperationAttentionPoints | null;
  state?: OverviewBlockState;
}) {
  // Aberto por padrão (é o que o Status geral do topo aponta), mas recolhível: o título e o resumo
  // de achados continuam à vista no cabeçalho.
  const [open, setOpen] = useState(true);
  const items = data?.items ?? [];
  const critical = items.filter((point) => point.severity === "critical").length;
  const skipped = (data?.skipped_rules ?? []).map((rule) => RULE_LABELS[rule] ?? rule);
  const periodLabel = data ? `${formatIsoDate(data.date_from)} a ${formatIsoDate(data.date_to)}` : null;

  return (
    <div id="overview-attention-points" className="min-w-0 scroll-mt-28">
      <OverviewBlock
        eyebrow="Cockpit"
        title="Pontos de atenção"
        subtitle={
          items.length === 0
            ? "Nenhum achado pelas regras verificadas neste recorte."
            : `${items.length} ${items.length === 1 ? "achado" : "achados"}${critical > 0 ? ` · ${critical} ${critical === 1 ? "crítico" : "críticos"}` : ""}`
        }
        badge={<TriangleAlert className={cn("h-4 w-4", critical > 0 ? "text-rose-600" : items.length ? "text-amber-600" : "text-slate-400")} aria-hidden="true" />}
        actions={
          <button
            type="button"
            onClick={() => setOpen((current) => !current)}
            aria-expanded={open}
            aria-controls="overview-attention-points-body"
            aria-label={open ? "Recolher pontos de atenção" : "Expandir pontos de atenção"}
            className="flex h-7 w-7 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-slate-100"
          >
            <ChevronDown className={cn("h-4 w-4 transition-transform", open && "rotate-180")} />
          </button>
        }
        state={state}
      >
        <div id="overview-attention-points-body" hidden={!open}>
        {items.length > 0 ? (
          <ul className="space-y-2">
            {items.map((point) => {
              const isCritical = point.severity === "critical";
              return (
                <li
                  key={`${point.rule}-${point.regional ?? "geral"}`}
                  className="grid grid-cols-[3px_minmax(0,1fr)_auto] items-center gap-2.5 overflow-hidden rounded-lg border border-slate-200 bg-slate-50/70 py-2.5 pr-2.5"
                >
                  <span className={cn("h-full self-stretch", isCritical ? "bg-rose-500" : "bg-amber-500")} aria-hidden="true" />
                  <div className="min-w-0">
                    <p className="text-xs font-semibold leading-snug text-slate-900">{point.title}</p>
                    <p className="text-[11px] leading-snug text-slate-500">{point.detail}</p>
                  </div>
                  <span
                    className={cn(
                      "rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide",
                      isCritical ? "bg-rose-50 text-rose-700" : "bg-amber-50 text-amber-800",
                    )}
                  >
                    {isCritical ? "Crítico" : "Atenção"}
                  </span>
                </li>
              );
            })}
          </ul>
        ) : null}
        {data?.notes?.map((note) => (
          <p key={note} className="mt-3 flex items-start gap-1.5 rounded-lg bg-slate-50 px-2.5 py-2 text-[11px] text-slate-600">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" />
            <span>{note}</span>
          </p>
        ))}
        {data ? (
          <p className="mt-3 text-[11px] text-slate-500">
            Período {periodLabel} · {data.rules_checked} de {data.rules_total} regras verificadas
            {skipped.length > 0 ? ` · não verificadas: ${skipped.join(", ")}` : ""}.
          </p>
        ) : null}
        </div>
      </OverviewBlock>
    </div>
  );
}
