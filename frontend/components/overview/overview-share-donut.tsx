"use client";

import { ChevronDown } from "lucide-react";
import dynamic from "next/dynamic";
import { useMemo, useState } from "react";

import { OverviewBlock, type OverviewBlockState } from "@/components/overview/overview-block";
import { formatInteger, formatPercent } from "@/lib/format";
import { buildShareDonutOption } from "@/lib/overview-chart-options";
import { foldShares, type ShareInput } from "@/lib/share-breakdown";
import { cn } from "@/lib/utils";

const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => <div className="h-[220px] animate-pulse rounded-xl bg-slate-100" aria-label="Carregando gráfico" />,
});

/** Linhas visíveis na lista antes de precisar de "Ver mais" - com muitas entidades nomeadas
 * (filial sem "Outros", por exemplo) o card não deveria crescer proporcional à contagem. */
const COLLAPSED_ROWS = 6;

/**
 * Donut de participação + lista lateral.
 *
 * A lista NÃO é decoração: é a legenda (identidade pela amostra de cor, obrigatória com 2+
 * séries) e a "vista em tabela" (valor exato de cada parte) ao mesmo tempo - o que a paleta exige
 * como compensação para os slots de contraste baixo. Clicar numa linha ou numa fatia aplica o
 * recorte na tela inteira quando o chamador passa `onSelect` (a fatia "Outros" nunca é clicável:
 * não corresponde a uma entidade).
 */
export function OverviewShareDonut({
  eyebrow,
  title,
  subtitle,
  items,
  totalLabel,
  state,
  maxSlices,
  onSelect,
}: {
  eyebrow: string;
  title: string;
  subtitle?: string;
  items: readonly ShareInput[];
  totalLabel: string;
  state?: OverviewBlockState;
  maxSlices?: number;
  onSelect?: (label: string) => void;
}) {
  const slices = useMemo(() => foldShares(items, { maxSlices }), [items, maxSlices]);
  const option = useMemo(() => buildShareDonutOption(slices, { totalLabel }), [slices, totalLabel]);
  // Recolhida por padrão: o ANEL sempre desenha todas as fatias (nenhum dado escondido) - só a
  // LISTA ao lado é que fica curta até o usuário pedir o resto, pra o card não crescer junto com a
  // contagem de entidades (pedido explícito do usuário, 2026-09-04, tela com ~15 filiais).
  const [expanded, setExpanded] = useState(false);
  const canCollapse = slices.length > COLLAPSED_ROWS;
  const visibleSlices = expanded || !canCollapse ? slices : slices.slice(0, COLLAPSED_ROWS);

  return (
    <OverviewBlock
      eyebrow={eyebrow}
      title={title}
      subtitle={subtitle}
      state={{ ...state, empty: !state?.loading && !state?.error && slices.length === 0 }}
      contentClassName="pt-2"
    >
      {/*
        Empilhado (nunca lado a lado): este bloco vive num grid de 3 colunas
        (`overview-screen.tsx`), então "lado a lado" sobra ~180px de largura pro gráfico -
        menos que a própria altura (220px). Como o ECharts calcula o raio da rosca pela MENOR
        dimensão do canvas, a largura vira o limite, e some a margem que o rótulo de % (fora do
        anel, com linha guia) precisa - o número simplesmente é cortado pela borda do canvas
        (achado real, 2026-09-04: "16,4%" cortava pra "16," e a fatia "Outros" virava
        pontinhos ilegíveis). Empilhado, o gráfico usa a largura inteira do card (~400px+),
        de sobra pra qualquer rótulo.
      */}
      <div className="grid gap-3">
        <ReactECharts
          option={option}
          notMerge
          lazyUpdate
          opts={{ renderer: "canvas" }}
          style={{ height: 220, width: "100%" }}
          onEvents={
            onSelect
              ? {
                  click: (params: { name?: string }) => {
                    const slice = slices.find((item) => item.label === params.name);
                    if (slice && !slice.isOther) onSelect(slice.label);
                  },
                }
              : undefined
          }
        />
        <ul className="min-w-0 divide-y divide-slate-100" aria-label={`Partes de ${title}`}>
          {visibleSlices.map((slice) => {
            const clickable = Boolean(onSelect) && !slice.isOther;
            const row = (
              <>
                <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ backgroundColor: slice.color }} aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate text-[12px] text-slate-700">{slice.label}</span>
                <span className="shrink-0 text-[12px] font-semibold tabular-nums text-slate-900">{formatInteger(slice.value)}</span>
                <span className="w-12 shrink-0 text-right text-[11px] tabular-nums text-slate-500">{formatPercent(slice.share)}</span>
              </>
            );
            return (
              <li key={slice.label}>
                {clickable ? (
                  <button
                    type="button"
                    onClick={() => onSelect?.(slice.label)}
                    title={`Filtrar a Visão Geral por ${slice.label}`}
                    className={cn("flex w-full items-center gap-2 rounded-md px-1 py-1.5 text-left transition-colors hover:bg-slate-50")}
                  >
                    {row}
                  </button>
                ) : (
                  <div className="flex items-center gap-2 px-1 py-1.5">{row}</div>
                )}
              </li>
            );
          })}
        </ul>
        {canCollapse ? (
          <button
            type="button"
            onClick={() => setExpanded((current) => !current)}
            className="flex w-full items-center justify-center gap-1 rounded-md py-1 text-[11px] font-semibold text-uni-royal hover:bg-slate-50"
          >
            {expanded ? "Ver menos" : `Ver mais (+${slices.length - COLLAPSED_ROWS})`}
            <ChevronDown className={cn("h-3 w-3 transition-transform", expanded && "rotate-180")} />
          </button>
        ) : null}
      </div>
    </OverviewBlock>
  );
}
