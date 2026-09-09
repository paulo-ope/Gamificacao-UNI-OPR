"use client";

import { ArrowRight } from "lucide-react";
import { useMemo, useState } from "react";

import { OverviewBlock, type OverviewBlockState } from "@/components/overview/overview-block";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatInteger, formatPercent } from "@/lib/format";
import { slaSystemTone } from "@/lib/operations-sla";
import type {
  OperationBranchCapacitySummaryItem,
  OperationRegionalMatrix,
  OperationRegionalMatrixItem,
} from "@/lib/operations-api";
import { toneTextClass } from "@/lib/tones";
import { cn } from "@/lib/utils";

type SortKey = "regional" | "opened" | "backlog" | "completed" | "sla_rate" | "capacity";

const COLUMNS: Array<{
  key: SortKey;
  label: string;
  scope: string;
  align: "left" | "right";
}> = [
  { key: "regional", label: "Filial", scope: "", align: "left" },
  { key: "opened", label: "Abertas no período", scope: "todo o período, qualquer equipe", align: "right" },
  { key: "backlog", label: "Em aberto", scope: "estoque de agora, qualquer equipe", align: "right" },
  { key: "completed", label: "Finalizadas", scope: "com os filtros aplicados", align: "right" },
  { key: "sla_rate", label: "SLA", scope: "com os filtros aplicados", align: "right" },
  { key: "capacity", label: "Meta da filial", scope: "finalizadas × faixa cadastrada", align: "left" },
];

function compare(left: OperationRegionalMatrixItem, right: OperationRegionalMatrixItem, key: SortKey) {
  // "Meta" não é ordenável por si (é texto de faixa); cai na ordem por filial.
  if (key === "regional" || key === "capacity") return left.regional.localeCompare(right.regional, "pt-BR");
  const leftValue = left[key];
  const rightValue = right[key];
  // Filial sem SLA medível (nenhuma O.S. finalizada com prazo) vai sempre para o fim, nas duas
  // direções: ordenar `null` como zero colocaria "sem dado" na frente de quem tem SLA ruim de
  // verdade, e o quadro existe justamente pra achar quem está ruim.
  if (leftValue === null && rightValue === null) return 0;
  if (leftValue === null) return 1;
  if (rightValue === null) return -1;
  return leftValue - rightValue;
}

export function OverviewRegionalTable({
  data,
  capacity,
  state,
  onDrillRegional,
}: {
  data: OperationRegionalMatrix | null;
  /**
   * Faixas de capacidade por filial (`/operations/capacity-summary`): realizado × meta cadastrada.
   * Só as filiais com faixa cadastrada aparecem aqui - as demais mostram "sem meta", que é uma
   * informação em si (ninguém definiu a meta), não um erro.
   */
  capacity?: OperationBranchCapacitySummaryItem[] | null;
  state?: OverviewBlockState;
  onDrillRegional?: (regional: string) => void;
}) {
  const capacityByRegional = useMemo(
    () => new Map((capacity ?? []).map((item) => [item.regional, item] as const)),
    [capacity],
  );
  // Achado real da análise "premium" (2026-09-08): em produção NENHUMA filial tem meta
  // cadastrada (`operations_branch_capacity` com 0 linhas) - a coluna inteira só mostrava "sem
  // meta cadastrada" repetido, sem informar nada. Some a coluna até a primeira meta existir, em
  // vez de exibir uma coluna cinza sem função; volta sozinha assim que alguém cadastrar a
  // primeira faixa (não depende de mexer aqui de novo).
  const hasAnyCapacity = Boolean(capacity && capacity.length > 0);
  const visibleColumns = hasAnyCapacity ? COLUMNS : COLUMNS.filter((column) => column.key !== "capacity");
  const [sort, setSort] = useState<{ key: SortKey; direction: "asc" | "desc" }>({
    key: "opened",
    direction: "desc",
  });

  const items = useMemo(() => {
    const copy = [...(data?.items ?? [])];
    copy.sort((left, right) => {
      const result = compare(left, right, sort.key);
      return sort.direction === "asc" ? result : -result;
    });
    return copy;
  }, [data, sort]);

  function toggleSort(key: SortKey) {
    setSort((current) =>
      current.key === key
        ? { key, direction: current.direction === "asc" ? "desc" : "asc" }
        : { key, direction: key === "regional" ? "asc" : "desc" },
    );
  }

  return (
    <OverviewBlock
      eyebrow="Operação por filial"
      title="Quadro geral das filiais"
      subtitle="Cada coluna obedece a um recorte diferente - o rótulo abaixo do título diz qual."
      badge={data && !data.sla_available ? "SLA restrito" : undefined}
      state={{ ...state, empty: !state?.loading && !state?.error && !items.length }}
      contentClassName="px-0 pt-0"
    >
      {/*
        `min-w`: o `<Table>` compartilhado usa `w-full` na tag `<table>`, que trava a largura em
        100% do contêiner - numa tela estreita isso espreme as 6 colunas + botão de detalhar em
        vez de a tabela vazar e rolar. `min-width` maior que `w-full` faz a tabela nunca ficar
        menor que o necessário pra ler as colunas, e o `overflow-x-auto` (do próprio `<Table>` e
        deste div) passa a rolar de verdade - achado real, 2026-09-08, "FINALIZA..." cortado sem
        jeito de ver o resto em 375px.
      */}
      <div className="overflow-x-auto">
        <Table className="min-w-[720px]">
          <TableHeader>
            <TableRow>
              {visibleColumns.map((column) => (
                <TableHead
                  key={column.key}
                  className={cn("align-bottom", column.align === "right" && "text-right")}
                >
                  <button
                    type="button"
                    onClick={() => toggleSort(column.key)}
                    className="font-semibold text-slate-600 hover:text-slate-900"
                  >
                    {column.label}
                    {sort.key === column.key ? (sort.direction === "asc" ? " ↑" : " ↓") : ""}
                  </button>
                  {column.scope ? (
                    <span className="mt-0.5 block text-[9px] font-normal normal-case leading-3 text-slate-400">
                      {column.scope}
                    </span>
                  ) : null}
                </TableHead>
              ))}
              {onDrillRegional ? <TableHead className="w-10" /> : null}
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.regional}>
                <TableCell className="font-medium text-slate-800">{item.regional}</TableCell>
                <TableCell className="text-right tabular-nums">{formatInteger(item.opened)}</TableCell>
                <TableCell className="text-right tabular-nums">
                  <span className="block">{formatInteger(item.backlog)}</span>
                  {item.overdue_backlog ? (
                    <span className="mt-0.5 block text-[10px] font-semibold leading-3 text-red-600">
                      {formatInteger(item.overdue_backlog)} fora do prazo
                    </span>
                  ) : null}
                </TableCell>
                <TableCell className="text-right tabular-nums">{formatInteger(item.completed)}</TableCell>
                <TableCell
                  className={cn(
                    "text-right font-semibold tabular-nums",
                    toneTextClass(slaSystemTone(item.sla_rate)),
                  )}
                >
                  {formatPercent(item.sla_rate)}
                </TableCell>
                {hasAnyCapacity ? (
                  <TableCell>
                    <CapacityBadge item={capacityByRegional.get(item.regional)} />
                  </TableCell>
                ) : null}
                {onDrillRegional ? (
                  <TableCell className="text-right">
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      className="h-7 w-7 p-0"
                      aria-label={`Filtrar a Visão Geral por ${item.regional}`}
                      onClick={() => onDrillRegional(item.regional)}
                    >
                      <ArrowRight className="h-3.5 w-3.5" />
                    </Button>
                  </TableCell>
                ) : null}
              </TableRow>
            ))}
            {data ? (
              <TableRow className="border-t-2 border-slate-200 bg-slate-50 font-semibold">
                <TableCell className="text-slate-900">Total</TableCell>
                <TableCell className="text-right tabular-nums">{formatInteger(data.total.opened)}</TableCell>
                <TableCell className="text-right tabular-nums">{formatInteger(data.total.backlog)}</TableCell>
                <TableCell className="text-right tabular-nums">{formatInteger(data.total.completed)}</TableCell>
                <TableCell className="text-right tabular-nums">{formatPercent(data.total.sla_rate)}</TableCell>
                {hasAnyCapacity ? <TableCell /> : null}
                {onDrillRegional ? <TableCell /> : null}
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </div>
      <p className="px-4 py-3 text-[11px] leading-4 text-slate-500">
        <strong className="font-semibold text-slate-600">Por que as colunas não somam entre si:</strong>{" "}
        &quot;Abertas no período&quot; é a demanda que entrou e ignora modelo de equipe e colaborador (na abertura a
        O.S. ainda não tem executor). &quot;Em aberto&quot; é o estoque de agora e ignora o período selecionado.
        &quot;Finalizadas&quot; e &quot;SLA&quot; respeitam todos os filtros, inclusive modelo de equipe e
        colaborador.
      </p>
    </OverviewBlock>
  );
}

const TIER_TONE: Record<OperationBranchCapacitySummaryItem["tier"], string> = {
  below: "border-amber-200 bg-amber-50 text-amber-800",
  good: "border-emerald-200 bg-emerald-50 text-emerald-800",
  great: "border-emerald-300 bg-emerald-100 text-emerald-900",
  excellent: "border-uni-royal/30 bg-uni-royal/10 text-uni-royal",
};

/**
 * Faixa de capacidade da filial: rótulo + realizado/limiar da próxima faixa. Sempre texto e
 * fundo, nunca só cor - a faixa é um estado, e estado exige rótulo. As cores cadastradas no
 * backend por faixa (`good_color` etc.) são de uso da tela de configuração; aqui a faixa usa os
 * tons do sistema para não competir com a paleta dos gráficos.
 */
function CapacityBadge({ item }: { item: OperationBranchCapacitySummaryItem | undefined }) {
  if (!item) return <span className="text-[11px] text-slate-400">sem meta cadastrada</span>;
  const next =
    item.difference_to_next_tier === null
      ? "faixa máxima"
      : `faltam ${formatInteger(item.difference_to_next_tier)} p/ próxima`;
  return (
    <span className="inline-flex flex-col gap-0.5">
      <span className={cn("inline-flex w-fit items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold", TIER_TONE[item.tier])}>
        {item.tier_label}
      </span>
      <span className="text-[10px] leading-3 text-slate-500">
        {formatInteger(item.realized)} de {formatInteger(item.excellent_threshold)} · {next}
      </span>
    </span>
  );
}
