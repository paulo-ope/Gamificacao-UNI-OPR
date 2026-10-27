import { percentChange } from "@/lib/period";
import type { SupportFeedback, SupportFeedbackDetails, SupportFeedbackIndicator } from "@/lib/types";

import { formatCardValue } from "./dashboard-format";
import { STATUS_LABEL, periodTargetLabel } from "./feedback-format";

// Análise em texto do Feedback individual (pedido do usuário, 2026-10-27): resume, em frases curtas, os indicadores
// do próprio colaborador, as notas do OPA e as O.S. a campo dele (IXC). Só entra na tela individual, nunca na da equipe.

export type FeedbackAnalysisSection = { title: string; lines: string[] };

const HIGHLIGHT_MIN_PERCENT = 10;
const DUPLICATE_PREFIX = "Duplicada";

const number = (value: number, digits = 1) => new Intl.NumberFormat("pt-BR", { maximumFractionDigits: digits }).format(value);
const signed = (value: number) => `${value > 0 ? "+" : ""}${number(value)}%`;
const plural = (count: number, one: string, many: string) => `${count} ${count === 1 ? one : many}`;

/** Variação % contra o período anterior (sinal do número, não de "melhor/pior"). */
function change(indicator: SupportFeedbackIndicator) {
  return percentChange(indicator.value, indicator.previous);
}

/** Positivo quando melhorou: maior-é-melhor sobe, menor-é-melhor desce. */
function improvement(indicator: SupportFeedbackIndicator, percent: number) {
  return indicator.direction === "min" ? percent : -percent;
}

function indicatorLine(indicator: SupportFeedbackIndicator, withTarget: boolean) {
  const percent = change(indicator);
  let line = `${indicator.label}: ${formatCardValue(indicator, indicator.value)}`;
  if (withTarget) line += ` (${periodTargetLabel(indicator).toLowerCase()})`;
  if (percent !== null) line += `, ${signed(percent)} contra o período anterior`;
  return line;
}

function reasonList(groups: { reason: string; count: number }[]) {
  return groups.map((item) => `${item.count} ${item.reason.toLowerCase()}`).join(", ");
}

export function buildFeedbackAnalysis(data: SupportFeedback, details: SupportFeedbackDetails | null): FeedbackAnalysisSection[] {
  const sections: FeedbackAnalysisSection[] = [];
  const { summary } = data;

  sections.push({
    title: "Resumo",
    lines: [`Status: ${STATUS_LABEL[summary.overall]}. ${summary.ok} dentro da meta, ${summary.attention} em atenção e ${summary.critical} a evoluir.`],
  });

  const highlights = data.indicators
    .filter((item) => item.status === "ok")
    .map((item) => ({ item, percent: change(item) }))
    .filter((entry): entry is { item: SupportFeedbackIndicator; percent: number } => entry.percent !== null && improvement(entry.item, entry.percent) >= HIGHLIGHT_MIN_PERCENT)
    .sort((a, b) => improvement(b.item, b.percent) - improvement(a.item, a.percent))
    .slice(0, 3);
  if (highlights.length) sections.push({ title: "Destaques", lines: highlights.map((entry) => indicatorLine(entry.item, false)) });

  const toImprove = data.indicators.filter((item) => item.status === "attention" || item.status === "critical");
  if (toImprove.length) sections.push({ title: "A evoluir", lines: toImprove.map((item) => indicatorLine(item, true)) });

  if (details && details.ratings.rated_count) {
    const { rated_count, good, neutral, bad } = details.ratings;
    sections.push({
      title: "Pesquisa de satisfação (OPA)",
      lines: [`${plural(rated_count, "avaliação", "avaliações")}: ${good.count} boas (${number(good.percent ?? 0)}%), ${neutral.count} neutras e ${bad.count} ruins.`],
    });
  }

  const orders = details?.improper_orders;
  if (orders && orders.total_orders > 0) {
    const lines: string[] = [];
    const avoidable = orders.improper_count + orders.remote_resolvable.count;
    if (avoidable > 0) {
      const percent = Math.round((avoidable / orders.total_orders) * 100);
      const reasons = [...orders.by_reason.filter((item) => !item.reason.startsWith(DUPLICATE_PREFIX)), ...orders.remote_resolvable.by_reason];
      lines.push(`Das ${orders.total_orders} O.S. abertas, ${avoidable} (${percent}%) poderiam ter sido evitadas: ${reasonList(reasons)}.`);
    } else {
      lines.push(`Das ${orders.total_orders} O.S. abertas, nenhuma foi indevida ou evitável.`);
    }
    if (orders.to_review.count > 0) lines.push(`Vale revisar ${orders.to_review.count}: ${reasonList(orders.to_review.by_reason)}.`);
    const duplicates = orders.by_reason.find((item) => item.reason.startsWith(DUPLICATE_PREFIX));
    lines.push(duplicates ? `${plural(duplicates.count, "O.S. aberta em duplicidade", "O.S. abertas em duplicidade")} (cliente já tinha O.S. recente).` : "Nenhuma O.S. aberta em duplicidade.");
    if (orders.repeat_customers.length) {
      lines.push(`Clientes com mais de uma O.S. aberta por ele: ${orders.repeat_customers.map((item) => `${item.customer_name} (${item.count})`).join(", ")}.`);
    }
    sections.push({ title: "O.S. a campo (IXC)", lines });
  }

  return sections;
}
