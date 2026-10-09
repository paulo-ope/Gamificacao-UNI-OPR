import type { OperationSlaItem } from "@/lib/operations-api";
import { SLA_TARGET_PERCENT, aggregateSlaItems } from "@/lib/operations-sla";

export type SlaGaugeCard = {
  key: string;
  label: string;
  /** SLA do período (0-100), `null` sem O.S. finalizada. */
  rate: number | null;
  completed: number;
  /** Diferença em pontos percentuais contra o período anterior; `null` sem base de comparação. */
  deltaPp: number | null;
  /** SLA acumulado do ano até o fim do período; `null` sem dado. */
  yearRate: number | null;
  /** Distância da meta em pontos percentuais (negativo = abaixo da meta). */
  gapPp: number | null;
  /** Só nos grupos: está marcado para compor o "Geral". */
  selected: boolean;
  /** Só no "Geral": o que ele está somando ("todos" ou "2 de 3 selecionados"). */
  scopeLabel: string | null;
};

type SlaLookup = ReadonlyMap<string, OperationSlaItem>;

const GENERAL_KEY = "__geral__";

function lookup(items: readonly OperationSlaItem[] | null): SlaLookup {
  return new Map((items ?? []).map((item) => [item.label, item]));
}

const round1 = (value: number) => Math.round(value * 10) / 10;

function diff(current: number | null, reference: number | null): number | null {
  return current === null || reference === null ? null : round1(current - reference);
}

/**
 * Cartões de medidor de um grupo de SLA por tecnologia: "Geral" (todos os grupos do cartão,
 * ponderado pelo volume - não média simples de percentuais) seguido de cada grupo. Tudo é aritmética
 * sobre o que o backend já devolveu de `/operations/sla?group_by=technology_group` no período, no
 * período anterior e no ano; nenhuma taxa de SLA é recalculada a partir de O.S. aqui.
 */
export function buildSlaGaugeCards({
  groups,
  current,
  previous,
  year,
  selected = [],
}: {
  groups: readonly string[];
  current: readonly OperationSlaItem[] | null;
  previous: readonly OperationSlaItem[] | null;
  year: readonly OperationSlaItem[] | null;
  /** Grupos marcados pelo usuário: o "Geral" soma só eles; vazio = soma todos. */
  selected?: readonly string[];
}): SlaGaugeCard[] {
  const currentBy = lookup(current);
  const previousBy = lookup(previous);
  const yearBy = lookup(year);

  const chosen = groups.filter((group) => selected.includes(group));
  const scope = chosen.length > 0 ? chosen : groups;
  const pick = (by: SlaLookup) => scope.flatMap((group) => by.get(group) ?? []);
  const general = aggregateSlaItems(pick(currentBy));
  const generalPrevious = aggregateSlaItems(pick(previousBy));
  const generalYear = aggregateSlaItems(pick(yearBy));

  const cards: SlaGaugeCard[] = [
    {
      key: GENERAL_KEY,
      label: "Geral",
      rate: general.sla_rate,
      completed: general.completed,
      deltaPp: diff(general.sla_rate, generalPrevious.sla_rate),
      yearRate: generalYear.sla_rate,
      gapPp: general.sla_rate === null ? null : round1(general.sla_rate - SLA_TARGET_PERCENT),
      selected: false,
      scopeLabel: chosen.length > 0 ? `${chosen.length} de ${groups.length} selecionados` : "todos os grupos",
    },
  ];
  for (const group of groups) {
    const rate = currentBy.get(group)?.sla_rate ?? null;
    cards.push({
      key: group,
      label: group,
      rate,
      completed: currentBy.get(group)?.completed ?? 0,
      deltaPp: diff(rate, previousBy.get(group)?.sla_rate ?? null),
      yearRate: yearBy.get(group)?.sla_rate ?? null,
      gapPp: rate === null ? null : round1(rate - SLA_TARGET_PERCENT),
      selected: chosen.includes(group),
      scopeLabel: null,
    });
  }
  return cards;
}
