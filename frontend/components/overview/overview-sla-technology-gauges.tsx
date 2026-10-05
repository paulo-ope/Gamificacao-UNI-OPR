"use client";

import dynamic from "next/dynamic";
import { useMemo, useState } from "react";

import { OverviewBlock, type OverviewBlockState } from "@/components/overview/overview-block";
import type { OperationSlaItem } from "@/lib/operations-api";
import { aggregateSlaItems } from "@/lib/operations-sla";
import { buildSlaTechnologyGaugeOption } from "@/lib/overview-chart-options";
import { cn } from "@/lib/utils";

const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => <div className="h-[180px] animate-pulse rounded-xl bg-slate-100" aria-label="Carregando gráfico" />,
});

const AVERAGE_LABEL = "Média selecionada";

/**
 * "SLA de Ativação"/"SLA de Suporte" por tecnologia (Fibra Urbana/Fibra Rural/Rádio) - pedido do
 * usuário em 2026-09-17 pra reproduzir na Visão Geral o painel executivo que ele recebe de outro
 * sistema. Consome `GET /operations/sla?group_by=technology_group` (mesmo endpoint de SLA que já
 * existia, só um `group_by` novo) - ver `docs/integracao-uni/regras-agrupamento-sla-tecnologia.json`
 * para a tabela de regras original que este agrupamento reproduz.
 *
 * O último gauge ("Média selecionada") consolida os grupos marcados pelo usuário (clique no gauge
 * ou no rótulo): SLA ponderado pelo volume, ver `aggregateSlaItems`.
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
  const [selected, setSelected] = useState<readonly string[]>([]);
  const byGroup = useMemo(() => new Map((items ?? []).map((item) => [item.label, item])), [items]);

  const average = useMemo(() => {
    const chosen = groups.filter((group) => selected.includes(group)).flatMap((group) => byGroup.get(group) ?? []);
    return aggregateSlaItems(chosen);
  }, [groups, selected, byGroup]);

  const slots = useMemo(() => [...groups, AVERAGE_LABEL], [groups]);
  const option = useMemo(() => {
    if (!items) return null;
    const averageItem = { sla_rate: average.sla_rate, label: AVERAGE_LABEL } as OperationSlaItem;
    return buildSlaTechnologyGaugeOption([...items, averageItem], slots);
  }, [items, slots, average.sla_rate]);
  const slotWidthPercent = 100 / slots.length;

  function toggle(group: string) {
    setSelected((current) => (current.includes(group) ? current.filter((item) => item !== group) : [...current, group]));
  }

  const events = useMemo(
    () => ({
      click: (params: { seriesIndex?: number }) => {
        const group = params.seriesIndex === undefined ? undefined : groups[params.seriesIndex];
        if (group) toggle(group);
      },
    }),
    [groups],
  );

  function formatHours(value: number | null) {
    return value === null ? "-" : `${value.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}h`;
  }

  return (
    <OverviewBlock
      eyebrow={eyebrow}
      title={title}
      subtitle="Meta ≥ 80% - assunto agrupado por tecnologia, não é o Tipo Geral padrão do módulo Operação. Selecione grupos para ver a média ponderada."
      state={{ ...state, empty: !state?.loading && !state?.error && items !== null && items.length === 0 }}
    >
      {option ? (
        <>
          <ReactECharts
            option={option}
            notMerge
            lazyUpdate
            opts={{ renderer: "canvas" }}
            style={{ height: 148, width: "100%", cursor: "pointer" }}
            onEvents={events}
          />
          <div className="flex" role="group" aria-label={`Grupos de ${title}`}>
            {groups.map((group) => {
              const item = byGroup.get(group) ?? null;
              const isSelected = selected.includes(group);
              return (
                <button
                  key={group}
                  type="button"
                  aria-pressed={isSelected}
                  onClick={() => toggle(group)}
                  className={cn(
                    "rounded-lg border px-1 py-1 text-center transition-colors",
                    isSelected ? "border-blue-500 bg-blue-50" : "border-transparent hover:bg-slate-50",
                  )}
                  style={{ width: `${slotWidthPercent}%` }}
                >
                  <span className="block text-xs font-semibold leading-tight text-slate-600">
                    {group}
                    {item ? ` · ${item.completed}` : ""}
                  </span>
                  <span className="block text-xs text-slate-500">Tempo médio: {formatHours(item?.average_closing_hours ?? null)}</span>
                </button>
              );
            })}
            <div className="px-1 py-1 text-center" style={{ width: `${slotWidthPercent}%` }} aria-live="polite">
              <span className="block text-xs font-semibold leading-tight text-slate-600">
                {AVERAGE_LABEL}
                {average.completed > 0 ? ` · ${average.completed}` : ""}
              </span>
              <span className="block text-xs text-slate-500">
                {selected.length === 0 ? "Selecione um ou mais grupos" : `Tempo médio: ${formatHours(average.average_closing_hours)}`}
              </span>
            </div>
          </div>
        </>
      ) : (
        <div className="h-[180px] animate-pulse rounded-xl bg-slate-100" aria-label="Carregando gráfico" />
      )}
    </OverviewBlock>
  );
}
