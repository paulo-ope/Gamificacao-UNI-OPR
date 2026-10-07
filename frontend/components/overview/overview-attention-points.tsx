"use client";

import { Bell, ChevronDown, CircleAlert, Info, TriangleAlert } from "lucide-react";
import { useState } from "react";

import { Card } from "@/components/ui/card";
import type { OverviewBlockState } from "@/components/overview/overview-block";
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
 * Pontos de atenção do recorte da Visão Geral, no fim da tela e recolhido por padrão: a linha de
 * resumo (quantos achados, quantos críticos) já diz se vale abrir, e a lista só ocupa espaço
 * quando alguém pede. Nenhuma regra roda aqui: o backend (`operations/attention.py`) avalia e
 * devolve cada achado com o número que o justifica; a tela só exibe. O rodapé da lista diz quantas
 * regras foram verificadas e quais ficaram de fora, porque "nenhum achado" só tem valor se o
 * painel disser o que olhou.
 */
export function OverviewAttentionPoints({
  data,
  state,
}: {
  data: OperationAttentionPoints | null;
  state?: OverviewBlockState;
}) {
  const [open, setOpen] = useState(false);
  const items = data?.items ?? [];
  const critical = items.filter(
    (point) => point.severity === "critical",
  ).length;
  const skipped = (data?.skipped_rules ?? []).map(
    (rule) => RULE_LABELS[rule] ?? rule,
  );

  let summary: string;
  if (state?.loading) summary = "Carregando...";
  else if (state?.error) summary = "Indisponível";
  else if (items.length === 0) summary = "Nenhum achado neste recorte";
  else
    summary = `${items.length} ${items.length === 1 ? "achado" : "achados"}${critical > 0 ? ` · ${critical} ${critical === 1 ? "crítico" : "críticos"}` : ""}`;

  const canExpand = !state?.loading && !state?.error;
  const periodLabel = data
    ? `${formatIsoDate(data.date_from)} a ${formatIsoDate(data.date_to)}`
    : null;

  return (
    <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
      <button
        type="button"
        onClick={() => canExpand && setOpen((current) => !current)}
        aria-expanded={open}
        aria-controls="overview-attention-points-list"
        disabled={!canExpand}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left disabled:cursor-default"
      >
        <span className="flex min-w-0 items-center gap-2.5">
          <Bell
            className={cn(
              "h-4 w-4 shrink-0",
              critical > 0
                ? "text-rose-600"
                : items.length > 0
                  ? "text-amber-600"
                  : "text-slate-400",
            )}
          />
          <span className="text-sm font-semibold text-slate-950">
            Pontos de atenção
          </span>
          <span
            className={cn(
              "truncate rounded-full border px-2.5 py-0.5 text-[10px] font-semibold",
              critical > 0
                ? "border-rose-200 bg-rose-50 text-rose-700"
                : items.length > 0
                  ? "border-amber-200 bg-amber-50 text-amber-700"
                  : "border-slate-200 bg-slate-50 text-slate-500",
            )}
          >
            {summary}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-3">
          {periodLabel ? (
            <span className="hidden text-[11px] text-slate-500 sm:inline">
              Período{" "}
              <span className="font-semibold text-slate-700">
                {periodLabel}
              </span>
            </span>
          ) : null}
          {canExpand ? (
            <ChevronDown
              className={cn(
                "h-4 w-4 shrink-0 text-slate-400 transition-transform",
                open && "rotate-180",
              )}
            />
          ) : null}
        </span>
      </button>

      {state?.error ? (
        <p className="border-t border-slate-100 px-4 py-2.5 text-xs text-amber-800">
          {state.error}
        </p>
      ) : null}

      {open && canExpand ? (
        <div
          id="overview-attention-points-list"
          className="border-t border-slate-100 px-4 py-3"
        >
          {items.length === 0 ? (
            <p className="text-sm text-slate-600">
              Nenhum achado pelas regras verificadas neste recorte.
            </p>
          ) : (
            <ul className="space-y-2">
              {items.map((point) => {
                const isCritical = point.severity === "critical";
                const Icon = isCritical ? CircleAlert : TriangleAlert;
                return (
                  <li
                    key={`${point.rule}-${point.regional ?? "geral"}`}
                    className={cn(
                      "flex items-start gap-2.5 rounded-xl border px-3 py-2",
                      isCritical
                        ? "border-rose-200 bg-rose-50"
                        : "border-amber-200 bg-amber-50",
                    )}
                  >
                    <Icon
                      className={cn(
                        "mt-0.5 h-4 w-4 shrink-0",
                        isCritical ? "text-rose-600" : "text-amber-600",
                      )}
                    />
                    <div className="min-w-0">
                      <p
                        className={cn(
                          "text-sm font-semibold",
                          isCritical ? "text-rose-900" : "text-amber-900",
                        )}
                      >
                        {point.title}
                        <span className="ml-2 text-[10px] font-semibold uppercase tracking-wide opacity-70">
                          {isCritical ? "Crítico" : "Atenção"}
                        </span>
                      </p>
                      <p
                        className={cn(
                          "text-xs",
                          isCritical ? "text-rose-800" : "text-amber-800",
                        )}
                      >
                        {point.detail}
                      </p>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
          {data?.notes?.map((note) => (
            <p key={note} className="mt-3 flex items-start gap-1.5 rounded-lg bg-slate-50 px-2.5 py-2 text-[11px] text-slate-600">
              <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" />
              <span>{note}</span>
            </p>
          ))}
          {data ? (
            <p className="mt-3 text-[11px] text-slate-500">
              Período {periodLabel} · {data.rules_checked} de {data.rules_total}{" "}
              regras verificadas
              {skipped.length > 0
                ? ` · não verificadas: ${skipped.join(", ")}`
                : ""}
              .
            </p>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}
