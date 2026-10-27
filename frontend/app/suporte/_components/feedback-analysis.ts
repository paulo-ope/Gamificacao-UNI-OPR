import { percentChange } from "@/lib/period";
import type { SupportFeedback, SupportFeedbackDetails, SupportFeedbackIndicator } from "@/lib/types";

import { formatCardValue } from "./dashboard-format";
import { STATUS_LABEL, dateBr, periodTargetLabel, weeklyTargetLabel } from "./feedback-format";

// Análise em texto do Feedback individual (pedido do usuário, 2026-10-27): resume, em poucas linhas, os indicadores do
// próprio colaborador, as notas do OPA e as O.S. a campo dele (IXC). Só entra na tela individual, nunca na da equipe.
// Texto curto de propósito (pedido do usuário): uma linha por assunto e só os primeiros casos.

export type FeedbackAnalysisSection = { title: string; lines: string[] };

const HIGHLIGHT_MIN_PERCENT = 10;
const STABLE_PERCENT = 1;
const DUPLICATE_PREFIX = "Duplicada";
const MAX_BAD_RATINGS = 3;
const MAX_CASES = 5;
const REPORT_SHOWN_CHARS = 100;

const number = (value: number, digits = 1) => new Intl.NumberFormat("pt-BR", { maximumFractionDigits: digits }).format(value);
const signed = (value: number) => `${value > 0 ? "+" : ""}${number(value)}%`;
const dayMonth = (iso: string) => dateBr(iso.slice(0, 10)).slice(0, 5);

/** Variação % contra o período anterior (sinal do número, não de "melhor/pior"). */
function change(indicator: SupportFeedbackIndicator) {
  return percentChange(indicator.value, indicator.previous);
}

/** Positivo quando melhorou: maior-é-melhor sobe, menor-é-melhor desce. */
function improvement(indicator: SupportFeedbackIndicator, percent: number) {
  return indicator.direction === "min" ? percent : -percent;
}

/** "melhorou 10,9%" / "piorou 10,6%"; nada quando está estável ou sem período anterior. */
function trend(indicator: SupportFeedbackIndicator) {
  const percent = change(indicator);
  if (percent === null || Math.abs(percent) < STABLE_PERCENT) return null;
  return `${improvement(indicator, percent) > 0 ? "melhorou" : "piorou"} ${number(Math.abs(percent))}%`;
}

/** Quanto falta (maior-é-melhor) ou passou (menor-é-melhor) da meta. */
function gapToTarget(indicator: SupportFeedbackIndicator) {
  if (indicator.value === null) return null;
  const diff = indicator.direction === "min" ? indicator.target - indicator.value : indicator.value - indicator.target;
  if (diff <= 0) return null;
  const shown = formatCardValue(indicator, diff);
  return indicator.direction === "min" ? `faltam ${shown}` : `${shown} acima`;
}

function toImproveLine(indicator: SupportFeedbackIndicator) {
  const inside = [`meta ${periodTargetLabel(indicator).toLowerCase()}`, gapToTarget(indicator)].filter(Boolean).join(", ");
  const movement = trend(indicator);
  return `${indicator.label}: ${formatCardValue(indicator, indicator.value)} (${inside})${movement ? ` · ${movement}` : ""}`;
}

function shortReason(reason: string) {
  return reason.startsWith(DUPLICATE_PREFIX) ? "duplicada" : reason.toLowerCase();
}

function reasonList(groups: { reason: string; count: number }[]) {
  return groups.map((item) => `${item.count} ${item.count > 1 && item.reason.startsWith(DUPLICATE_PREFIX) ? "duplicadas" : shortReason(item.reason)}`).join(", ");
}

export function buildFeedbackAnalysis(data: SupportFeedback, details: SupportFeedbackDetails | null): FeedbackAnalysisSection[] {
  const sections: FeedbackAnalysisSection[] = [];
  const { summary } = data;
  const orders = details?.improper_orders ?? null;

  sections.push({
    title: "Resumo",
    lines: [`${STATUS_LABEL[summary.overall]}: ${summary.ok} na meta, ${summary.attention} em atenção, ${summary.critical} a evoluir.`],
  });

  const highlights = data.indicators
    .filter((item) => item.status === "ok")
    .map((item) => ({ item, percent: change(item) }))
    .filter((entry): entry is { item: SupportFeedbackIndicator; percent: number } => entry.percent !== null && improvement(entry.item, entry.percent) >= HIGHLIGHT_MIN_PERCENT)
    .sort((a, b) => improvement(b.item, b.percent) - improvement(a.item, a.percent))
    .slice(0, 3);
  if (highlights.length) sections.push({ title: "Destaques", lines: [highlights.map((entry) => `${entry.item.label} (${signed(entry.percent)})`).join("; ")] });

  const toImprove = data.indicators.filter((item) => item.status === "attention" || item.status === "critical");
  if (toImprove.length) sections.push({ title: "A evoluir", lines: toImprove.map(toImproveLine) });

  if (details && details.ratings.rated_count) {
    const { rated_count, average: mean, good, neutral, bad, attendances } = details.ratings;
    const lines = [
      `${rated_count} ${rated_count === 1 ? "avaliação" : "avaliações"}${mean !== null ? `, média ${number(mean, 2)}` : ""}: ${good.count} ${good.count === 1 ? "boa" : "boas"}, ${neutral.count} ${neutral.count === 1 ? "neutra" : "neutras"}, ${bad.count} ${bad.count === 1 ? "ruim" : "ruins"}.`,
    ];
    const badOnes = attendances.filter((row) => row.band === "bad");
    if (badOnes.length) {
      const shown = badOnes.slice(0, MAX_BAD_RATINGS).map((row) => `${row.protocol ?? "sem protocolo"} (${row.rating})`);
      lines.push(`Ruins: ${shown.join(", ")}${badOnes.length > MAX_BAD_RATINGS ? ` e mais ${badOnes.length - MAX_BAD_RATINGS}` : ""}.`);
    }
    sections.push({ title: "Pesquisa de satisfação (OPA)", lines });
  }

  if (orders && orders.total_orders > 0) {
    const avoidable = orders.improper_count + orders.remote_resolvable.count;
    const lines: string[] = [];
    if (avoidable > 0) {
      const percent = Math.round((avoidable / orders.total_orders) * 100);
      // Uma O.S. pode ter dois motivos (ex.: desistência e duplicada), então a lista de motivos pode somar mais que o total.
      lines.push(`${orders.total_orders} O.S. abertas, ${avoidable} evitáveis (${percent}%). Motivos: ${reasonList([...orders.by_reason, ...orders.remote_resolvable.by_reason])}.`);
    } else {
      lines.push(`${orders.total_orders} O.S. abertas, nenhuma evitável.`);
    }
    if (orders.to_review.count > 0) lines.push(`Revisar ${orders.to_review.count}: ${reasonList(orders.to_review.by_reason)}.`);
    sections.push({ title: "O.S. a campo (IXC)", lines });

    const cases = orders.orders.slice(0, MAX_CASES).map((order) => {
      const report = order.report && order.report.length > REPORT_SHOWN_CHARS ? `${order.report.slice(0, REPORT_SHOWN_CHARS).trimEnd()}…` : order.report;
      return `${order.order_code} · ${dayMonth(order.opened_at)} · ${order.reasons.map(shortReason).join(" + ")}${report ? `: "${report}"` : ""}`;
    });
    if (orders.orders.length > MAX_CASES) cases.push(`Mais ${orders.orders.length - MAX_CASES} O.S. indevidas.`);
    if (orders.repeat_customers.length) cases.push(`Clientes com mais de uma O.S.: ${orders.repeat_customers.map((item) => `${item.customer_name} (${item.count})`).join(", ")}.`);
    if (orders.no_diagnosis_codes.length) cases.push(`Sem diagnóstico: ${orders.no_diagnosis_codes.join(", ")}.`);
    if (cases.length) sections.push({ title: "Casos para conversar", lines: cases });
  }

  const next: string[] = [];
  if (toImprove.length) next.push(`Metas da semana: ${toImprove.map((item) => `${item.label} ${weeklyTargetLabel(item).toLowerCase()}`).join("; ")}.`);
  if (orders) {
    if (orders.remote_resolvable.count > 0 || orders.to_review.by_reason.some((item) => item.reason === "Atualização de configuração")) {
      next.push("Esgotar o atendimento remoto antes de abrir O.S. (travado, reset, configuração).");
    }
    if (orders.by_reason.some((item) => item.reason === "Assunto errado")) next.push("Escolher o assunto correto ao abrir a O.S.");
    if (orders.by_reason.some((item) => item.reason.startsWith(DUPLICATE_PREFIX)) || orders.repeat_customers.length) {
      next.push("Conferir o histórico do cliente antes de abrir; escalar reincidentes ao N2.");
    }
  }
  sections.push({ title: "Próxima semana", lines: next.length ? next : ["Manter o desempenho atual."] });

  return sections;
}
