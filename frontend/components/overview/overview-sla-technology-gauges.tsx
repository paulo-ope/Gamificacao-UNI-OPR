"use client";

import dynamic from "next/dynamic";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { useMemo, useState } from "react";

import { OverviewBlock, type OverviewBlockState } from "@/components/overview/overview-block";
import { formatPercent } from "@/lib/format";
import type { OperationSlaItem } from "@/lib/operations-api";
import { SLA_TARGET_PERCENT, slaTone } from "@/lib/operations-sla";
import { buildSlaRingOption } from "@/lib/overview-chart-options";
import { buildSlaGaugeCards, type SlaGaugeCard } from "@/lib/overview-sla-cards";
import { cn } from "@/lib/utils";

const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => <div className="h-[116px] animate-pulse rounded-full bg-slate-100" aria-hidden="true" />,
});

const pp = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1, signDisplay: "exceptZero" });

function GaugeTile({
  card,
  previousLabel,
  isGeneral,
  onToggle,
  hasSelection,
}: {
  card: SlaGaugeCard;
  previousLabel: string;
  isGeneral: boolean;
  /** Grupo: marca/desmarca. Geral: limpa a seleção. */
  onToggle: () => void;
  hasSelection: boolean;
}) {
  const option = useMemo(() => buildSlaRingOption(card.rate), [card.rate]);
  const risk = slaTone(card.rate) === "danger";
  const DeltaIcon = card.deltaPp === null || card.deltaPp === 0 ? Minus : card.deltaPp > 0 ? ArrowUpRight : ArrowDownRight;
  // O Geral só é clicável quando há algo a limpar; os grupos sempre alternam a seleção.
  const disabled = isGeneral && !hasSelection;
  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={disabled}
      aria-pressed={isGeneral ? undefined : card.selected}
      title={isGeneral ? (hasSelection ? "Limpar seleção: o Geral volta a somar todos os grupos" : undefined) : card.selected ? "Clique para tirar do Geral" : "Clique para incluir no Geral"}
      className={cn(
        "min-w-0 rounded-xl border px-2 py-3 text-center transition-colors disabled:cursor-default",
        card.selected
          ? "border-blue-500 bg-blue-50 ring-1 ring-blue-500"
          : risk
            ? "border-red-200 bg-red-50/60 enabled:hover:border-red-300"
            : "border-slate-200 bg-slate-50/70 enabled:hover:border-blue-300",
      )}
    >
      <p className="truncate px-1 text-xs font-semibold text-slate-700" title={card.label}>
        {card.label}
      </p>
      {card.scopeLabel ? <p className="truncate px-1 text-[10px] text-slate-500">{card.scopeLabel}</p> : null}
      <div role="img" aria-label={`${card.label}: SLA ${card.rate === null ? "sem dado" : formatPercent(card.rate)}`}>
        <ReactECharts option={option} notMerge lazyUpdate opts={{ renderer: "canvas" }} style={{ height: 116, width: "100%" }} />
      </div>
      <span
        className={cn(
          "inline-flex flex-wrap items-center justify-center gap-x-1 rounded-md px-1.5 py-0.5 text-[10px] font-semibold",
          card.deltaPp === null || card.deltaPp === 0
            ? "bg-slate-100 text-slate-500"
            : card.deltaPp > 0
              ? "bg-emerald-50 text-emerald-700"
              : "bg-red-50 text-red-700",
        )}
      >
        <DeltaIcon className="h-3 w-3" aria-hidden="true" />
        {card.deltaPp === null ? "sem base" : `${pp.format(card.deltaPp)} p.p.`}
        <span className="font-normal opacity-80">{previousLabel}</span>
      </span>
      <div className="mx-1 mt-2.5 flex flex-wrap items-center justify-center gap-x-3 gap-y-0.5 border-t border-slate-200 pt-2.5 text-[10px] text-slate-500">
        <span>
          Meta <b className="text-slate-900">≥ {SLA_TARGET_PERCENT}%</b>
        </span>
        <span>
          No ano <b className="text-slate-900">{card.yearRate === null ? "—" : formatPercent(card.yearRate)}</b>
        </span>
      </div>
      {card.gapPp !== null ? (
        <p className={cn("mt-1 text-[10px] font-semibold", card.gapPp >= 0 ? "text-emerald-700" : "text-red-700")}>
          {card.gapPp >= 0 ? "+" : "−"}
          {Math.abs(card.gapPp).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} p.p. da meta
        </p>
      ) : null}
    </button>
  );
}

/**
 * "SLA de Ativação"/"SLA de Suporte" por tecnologia: um cartão "Geral" (todos os grupos juntos,
 * ponderado pelo volume) mais um por grupo, cada um com anel de SLA, variação contra o período
 * anterior, meta e SLA do ano.
 *
 * Consome `GET /operations/sla?group_by=technology_group` em três janelas (período, período
 * anterior e ano até o fim do período) - o mesmo endpoint de sempre, só com datas diferentes.
 * A conta de cada cartão fica em `lib/overview-sla-cards.ts`; este componente só desenha e guarda a
 * seleção. Clicar num grupo o inclui no "Geral" (ponderado pelo volume, com variação e SLA do ano da
 * mesma seleção); clicar de novo tira; clicar no "Geral" limpa e ele volta a somar todos.
 */
export function OverviewSlaTechnologyGauges({
  eyebrow,
  title,
  groups,
  current,
  previous,
  year,
  previousLabel,
  state,
}: {
  eyebrow: string;
  title: string;
  groups: readonly string[];
  current: readonly OperationSlaItem[] | null;
  previous: readonly OperationSlaItem[] | null;
  year: readonly OperationSlaItem[] | null;
  /** Texto curto depois da variação, ex.: "vs. ant.". */
  previousLabel: string;
  state?: OverviewBlockState;
}) {
  // Seleção que compõe o "Geral" deste cartão (Ativação e Suporte têm cada um a sua).
  const [selected, setSelected] = useState<readonly string[]>([]);
  const cards = useMemo(
    () => buildSlaGaugeCards({ groups, current, previous, year, selected }),
    [groups, current, previous, year, selected],
  );
  const toggle = (group: string) =>
    setSelected((currentSelection) =>
      currentSelection.includes(group) ? currentSelection.filter((item) => item !== group) : [...currentSelection, group],
    );
  return (
    <OverviewBlock
      eyebrow={eyebrow}
      title={title}
      subtitle={`Meta ≥ ${SLA_TARGET_PERCENT}% - assunto agrupado por tecnologia, não é o Tipo Geral padrão do módulo Operação. Clique nos grupos para o Geral somar só os selecionados.`}
      state={{ ...state, empty: !state?.loading && !state?.error && current !== null && current.length === 0 }}
    >
      <div className="grid grid-cols-2 gap-2.5 md:grid-cols-4">
        {cards.map((card, index) => (
          <GaugeTile
            key={card.key}
            card={card}
            previousLabel={previousLabel}
            isGeneral={index === 0}
            hasSelection={selected.length > 0}
            onToggle={() => (index === 0 ? setSelected([]) : toggle(card.label))}
          />
        ))}
      </div>
    </OverviewBlock>
  );
}
