"use client";

import dynamic from "next/dynamic";
import { useMemo } from "react";

import { OverviewBlock, type OverviewBlockState } from "@/components/overview/overview-block";
import type { OperationSlaItem } from "@/lib/operations-api";
import { buildSlaTechnologyGaugeOption } from "@/lib/overview-chart-options";

const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => <div className="h-[180px] animate-pulse rounded-xl bg-slate-100" aria-label="Carregando gráfico" />,
});

/**
 * "SLA de Ativação"/"SLA de Suporte" por tecnologia (Fibra Urbana/Fibra Rural/Rádio) - pedido do
 * usuário em 2026-09-17 pra reproduzir na Visão Geral o painel executivo que ele recebe de outro
 * sistema. Consome `GET /operations/sla?group_by=technology_group` (mesmo endpoint de SLA que já
 * existia, só um `group_by` novo) - ver `docs/integracao-uni/regras-agrupamento-sla-tecnologia.json`
 * para a tabela de regras original que este agrupamento reproduz.
 */
export function OverviewSlaTechnologyGauges({
  eyebrow,
  title,
  groups,
  items,
  state,
}: {
  eyebrow: string;
  title: string;
  groups: readonly string[];
  items: readonly OperationSlaItem[] | null;
  state?: OverviewBlockState;
}) {
  const option = useMemo(() => (items ? buildSlaTechnologyGaugeOption(items, groups) : null), [items, groups]);
  const byGroup = useMemo(() => new Map((items ?? []).map((item) => [item.label, item])), [items]);
  const slotWidthPercent = 100 / groups.length;

  return (
    <OverviewBlock
      eyebrow={eyebrow}
      title={title}
      subtitle="Meta ≥ 80% - assunto agrupado por tecnologia, não é o Tipo Geral padrão do módulo Operação."
      state={{ ...state, empty: !state?.loading && !state?.error && items !== null && items.length === 0 }}
    >
      {option ? (
        <>
          <ReactECharts option={option} notMerge lazyUpdate opts={{ renderer: "canvas" }} style={{ height: 148, width: "100%" }} />
          <div className="flex" role="presentation">
            {groups.map((group) => {
              const item = byGroup.get(group) ?? null;
              const averageHours = item?.average_closing_hours ?? null;
              return (
                <div key={group} className="px-1 text-center" style={{ width: `${slotWidthPercent}%` }}>
                  <p className="text-xs font-semibold leading-tight text-slate-600">
                    {group}
                    {item ? ` · ${item.completed}` : ""}
                  </p>
                  <p className="text-xs text-slate-500">
                    Tempo médio: {averageHours === null ? "-" : `${averageHours.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}h`}
                  </p>
                </div>
              );
            })}
          </div>
        </>
      ) : (
        <div className="h-[180px] animate-pulse rounded-xl bg-slate-100" aria-label="Carregando gráfico" />
      )}
    </OverviewBlock>
  );
}
