import { percentChange } from "@/lib/period";
import type { SupportFeedback, SupportFeedbackDetails, SupportFeedbackIndicator } from "@/lib/types";

import { formatCardValue } from "./dashboard-format";
import { FOLLOW_UP, STATUS_LABEL, dateBr, periodTargetLabel, weeklyTargetLabel } from "./feedback-format";

// Análise em texto do Feedback individual (pedido do usuário, 2026-10-27): resume, em frases curtas, os indicadores
// do próprio colaborador, as notas do OPA e as O.S. a campo dele (IXC). Só entra na tela individual, nunca na da equipe.

export type FeedbackAnalysisSection = { title: string; lines: string[] };

const HIGHLIGHT_MIN_PERCENT = 10;
const STABLE_PERCENT = 1;
const DUPLICATE_PREFIX = "Duplicada";
const MAX_CASES = 5;

const number = (value: number, digits = 1) => new Intl.NumberFormat("pt-BR", { maximumFractionDigits: digits }).format(value);
const signed = (value: number) => `${value > 0 ? "+" : ""}${number(value)}%`;
const plural = (count: number, one: string, many: string) => `${count} ${count === 1 ? one : many}`;
const dayMonth = (iso: string) => dateBr(iso.slice(0, 10)).slice(0, 5);

/** Variação % contra o período anterior (sinal do número, não de "melhor/pior"). */
function change(indicator: SupportFeedbackIndicator) {
  return percentChange(indicator.value, indicator.previous);
}

/** Positivo quando melhorou: maior-é-melhor sobe, menor-é-melhor desce. */
function improvement(indicator: SupportFeedbackIndicator, percent: number) {
  return indicator.direction === "min" ? percent : -percent;
}

function trend(indicator: SupportFeedbackIndicator) {
  const percent = change(indicator);
  if (percent === null) return null;
  if (Math.abs(percent) < STABLE_PERCENT) return "estável contra o período anterior";
  return `${signed(percent)} contra o período anterior (${improvement(indicator, percent) > 0 ? "melhorou" : "piorou"})`;
}

/** Quanto falta (maior-é-melhor) ou passou (menor-é-melhor) da meta. */
function gapToTarget(indicator: SupportFeedbackIndicator) {
  if (indicator.value === null) return null;
  const diff = indicator.direction === "min" ? indicator.target - indicator.value : indicator.value - indicator.target;
  if (diff <= 0) return null;
  const shown = formatCardValue(indicator, diff);
  return indicator.direction === "min" ? `faltam ${shown} para a meta` : `${shown} acima da meta`;
}

function indicatorLine(indicator: SupportFeedbackIndicator, withTarget: boolean) {
  const parts = [`${indicator.label}: ${formatCardValue(indicator, indicator.value)}`];
  if (withTarget) parts[0] += ` (${periodTargetLabel(indicator).toLowerCase()})`;
  const gap = withTarget ? gapToTarget(indicator) : null;
  if (gap) parts.push(gap);
  const movement = trend(indicator);
  if (movement) parts.push(movement);
  return parts.join(", ");
}

function reasonList(groups: { reason: string; count: number }[]) {
  return groups.map((item) => `${item.count} ${item.reason.toLowerCase()}`).join(", ");
}

function average(values: (number | null)[]) {
  const valid = values.filter((value): value is number => value !== null);
  return valid.length ? valid.reduce((sum, value) => sum + value, 0) / valid.length : null;
}

export function buildFeedbackAnalysis(data: SupportFeedback, details: SupportFeedbackDetails | null): FeedbackAnalysisSection[] {
  const sections: FeedbackAnalysisSection[] = [];
  const { summary } = data;
  const orders = details?.improper_orders ?? null;

  sections.push({
    title: "Resumo",
    lines: [
      `Período de ${dateBr(data.date_from)} a ${dateBr(data.date_to)}. Status: ${STATUS_LABEL[summary.overall]}, com ${summary.ok} indicadores dentro da meta, ${summary.attention} em atenção e ${summary.critical} a evoluir.`,
    ],
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
    const { rated_count, average: mean, good, neutral, bad, attendances } = details.ratings;
    const lines = [
      `${plural(rated_count, "avaliação", "avaliações")}${mean !== null ? `, nota média ${number(mean, 2)}` : ""}: ${good.count} boas (${number(good.percent ?? 0)}%), ${neutral.count} neutras e ${bad.count} ruins.`,
    ];
    const badOnes = attendances.filter((row) => row.band === "bad");
    if (badOnes.length) {
      const shown = badOnes.slice(0, MAX_CASES).map((row) => `${row.protocol ?? "sem protocolo"} (nota ${row.rating}, ${dayMonth(row.opened_at)}${row.channel ? `, ${row.channel}` : ""})`);
      lines.push(`Notas ruins: ${shown.join("; ")}${badOnes.length > MAX_CASES ? `; e mais ${badOnes.length - MAX_CASES}` : ""}.`);
      const badTmr = average(badOnes.map((row) => row.tmr_seconds));
      const allTmr = average(attendances.map((row) => row.tmr_seconds));
      if (badTmr !== null && allTmr !== null) {
        lines.push(
          `Nas avaliações ruins o TMR médio foi ${formatCardValue({ unit: "seconds" }, badTmr)}, contra ${formatCardValue({ unit: "seconds" }, allTmr)} nas avaliadas em geral${badTmr <= allTmr ? ": a demora provavelmente não explica a nota, vale olhar a solução dada" : ": a demora pode ter pesado na nota"}.`,
        );
      }
    }
    sections.push({ title: "Pesquisa de satisfação (OPA)", lines });
  }

  if (orders && orders.total_orders > 0) {
    const lines: string[] = [];
    const avoidable = orders.improper_count + orders.remote_resolvable.count;
    if (avoidable > 0) {
      const percent = Math.round((avoidable / orders.total_orders) * 100);
      const reasons = [...orders.by_reason.filter((item) => !item.reason.startsWith(DUPLICATE_PREFIX)), ...orders.remote_resolvable.by_reason];
      lines.push(`Das ${orders.total_orders} O.S. abertas, ${avoidable} (${percent}%) poderiam ter sido evitadas${reasons.length ? `: ${reasonList(reasons)}` : ""}.`);
    } else {
      lines.push(`Das ${orders.total_orders} O.S. abertas, nenhuma foi indevida ou evitável.`);
    }
    if (orders.remote_resolvable.count > 0) lines.push("Equipamento travado, resetado e procedimento organizacional costumam ser resolvidos com orientação remota.");
    if (orders.to_review.count > 0) lines.push(`Vale revisar ${orders.to_review.count}: ${reasonList(orders.to_review.by_reason)}.`);
    const duplicates = orders.by_reason.find((item) => item.reason.startsWith(DUPLICATE_PREFIX));
    lines.push(duplicates ? `${plural(duplicates.count, "O.S. aberta em duplicidade", "O.S. abertas em duplicidade")}: o cliente já tinha O.S. recente.` : "Nenhuma O.S. aberta em duplicidade.");
    sections.push({ title: "O.S. a campo (IXC)", lines });

    const cases: string[] = [];
    const duplicateOrders = orders.orders.filter((order) => order.reasons.some((reason) => reason.startsWith(DUPLICATE_PREFIX)));
    for (const order of duplicateOrders.slice(0, MAX_CASES)) {
      cases.push(`${order.order_code}${order.customer_name ? ` (${order.customer_name})` : ""}: o cliente já tinha outra O.S. de campo nas 72 h anteriores. Conferir o histórico antes de abrir.`);
    }
    if (duplicateOrders.length > MAX_CASES) cases.push(`Mais ${duplicateOrders.length - MAX_CASES} O.S. em duplicidade.`);
    if (orders.repeat_customers.length) {
      cases.push(`Clientes com mais de uma O.S. aberta por ele no período: ${orders.repeat_customers.map((item) => `${item.customer_name} (${item.count})`).join(", ")}. Se o problema se repete, escalar ao N2 em vez de abrir nova O.S.`);
    }
    if (orders.no_diagnosis_codes.length) cases.push(`Finalizada sem diagnóstico: ${orders.no_diagnosis_codes.join(", ")}.`);
    if (cases.length) sections.push({ title: "Casos para conversar", lines: cases });
  }

  const next: string[] = [];
  for (const item of toImprove) {
    if (item.key === "field" && orders) {
      next.push(`${item.label}: ${weeklyTargetLabel(item).toLowerCase()} na semana.`);
    } else {
      next.push(`${item.label} (${weeklyTargetLabel(item).toLowerCase()}): ${FOLLOW_UP[item.key] ?? "acompanhar diariamente."}`);
    }
  }
  if (orders) {
    if (orders.remote_resolvable.count > 0 || orders.to_review.by_reason.some((item) => item.reason === "Atualização de configuração")) {
      next.push("Esgotar o atendimento remoto antes de abrir O.S. a campo, principalmente em equipamento travado, reset e configuração.");
    }
    if (orders.by_reason.some((item) => item.reason === "Assunto errado")) next.push("Escolher o assunto correto na abertura da O.S.");
    if (orders.by_reason.some((item) => item.reason.startsWith(DUPLICATE_PREFIX)) || orders.repeat_customers.length) {
      next.push("Conferir o histórico do cliente antes de abrir e escalar ao N2 os casos reincidentes.");
    }
  }
  sections.push({ title: "Sugestão para a próxima semana", lines: next.length ? next : ["Manter o desempenho atual."] });

  return sections;
}
