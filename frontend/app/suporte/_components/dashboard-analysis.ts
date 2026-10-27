import type { SupportMacroDashboard, SupportMacroProjectionItem } from "@/lib/types";

import { formatCardValue } from "./dashboard-format";

// Análise geral dos Indicadores do Suporte (pedido do usuário, 2026-10-27): o dia de maior aumento e o motivo, e o que a
// próxima semana precisa fechar para a média do mês terminar na meta. Números prontos do backend; aqui só se monta o texto.

export type DashboardAnalysisSection = { title: string; lines: string[] };

const GOAL_KEYS: { key: string; name: string; unit: "seconds" | "score" | "percent" }[] = [
  { key: "tmr", name: "TMR", unit: "seconds" },
  { key: "tma", name: "TMA", unit: "seconds" },
  { key: "csat", name: "Avaliação (CSAT)", unit: "score" },
  { key: "resolutivity", name: "Resolutividade", unit: "percent" },
];
const MAX_REASONS = 5;
// Um motivo "pesou" no pico se passou do habitual dele por esta proporção e por pelo menos esta quantidade.
const HEAVY_RATIO = 1.5;
const HEAVY_MIN_EXTRA = 3;
// Até este número de dias que faltam no mês, o "resto do mês" é a próxima semana.
const WEEK_DAYS = 7;

const number = (value: number, digits = 1) => new Intl.NumberFormat("pt-BR", { maximumFractionDigits: digits }).format(value);
const dayMonth = (iso: string) => iso.slice(0, 10).split("-").reverse().slice(0, 2).join("/");

function peakSection(data: SupportMacroDashboard): DashboardAnalysisSection {
  const peak = data.peak_day;
  if (!peak) return { title: "Dia de maior aumento", lines: ["Nenhum dia com aumento relevante de atendimentos no período."] };
  const lines = [
    `Dia ${dayMonth(peak.day)} teve ${number(peak.total, 0)} atendimentos no OPA, ${number(peak.percent_above)}% acima da média dos outros dias do período (${number(peak.average)} por dia).`,
  ];
  if (peak.reasons.length) {
    lines.push(`Motivos mais frequentes no dia: ${peak.reasons.slice(0, MAX_REASONS).map((item) => `${item.reason} (${item.count}, habitual ${number(item.usual_per_day)} por dia)`).join("; ")}.`);
    const heavy = peak.reasons.filter((item) => item.count >= item.usual_per_day * HEAVY_RATIO && item.count - item.usual_per_day >= HEAVY_MIN_EXTRA);
    lines.push(heavy.length ? `Puxaram o aumento: ${heavy.map((item) => item.reason).join(", ")}.` : "Nenhum motivo isolado explica o aumento: o volume subiu de forma geral.");
  }
  return { title: "Dia de maior aumento", lines };
}

function goalLine(name: string, unit: "seconds" | "score" | "percent", week: number | null, item: SupportMacroProjectionItem, rest: string): string | null {
  if (item.month_value === null || item.target === null || item.status === "no_data" || item.status === "no_target") return null;
  const show = (value: number) => formatCardValue({ unit }, value);
  const target = show(item.target);
  const opening = `${name}: ${week === null ? "" : `${show(week)} na semana e `}${show(item.month_value)} no mês (meta ${target}).`;
  if (item.status === "closed") {
    return `${name}: o mês fechou em ${show(item.month_value)} (meta ${target}), ${item.pace_meets_target ? "dentro da meta" : "fora da meta"}.`;
  }
  const pace = item.pace_value === null ? "" : ` No ritmo atual o mês fecharia em ${show(item.pace_value)}.`;
  if (item.status === "reachable" && item.required_value !== null) {
    return `${opening} Para fechar o mês na meta, ${rest} precisa fechar em ${show(item.required_value)}.${item.pace_meets_target ? " No ritmo atual já bate a meta." : pace}`;
  }
  return `${opening} Não dá mais para fechar o mês na meta só com ${rest}.${pace}`;
}

function monthSection(data: SupportMacroDashboard): DashboardAnalysisSection | null {
  const projection = data.month_projection;
  if (!projection) return null;
  const closed = projection.remaining_days === 0;
  const remainingFrom = projection.remaining_from ?? projection.month_to;
  const rest =
    projection.remaining_days <= WEEK_DAYS
      ? `a próxima semana (${dayMonth(remainingFrom)} a ${dayMonth(projection.month_to)})`
      : `o resto do mês (${dayMonth(remainingFrom)} a ${dayMonth(projection.month_to)})`;
  const cards = Object.fromEntries(data.cards.map((card) => [card.key, card]));
  const lines = GOAL_KEYS.flatMap(({ key, name, unit }) => {
    const item = projection.items.find((candidate) => candidate.key === key);
    const line = item ? goalLine(name, unit, closed ? null : (cards[key]?.value ?? null), item, rest) : null;
    return line ? [line] : [];
  });
  if (!lines.length) return null;
  return { title: closed ? "Fechamento do mês" : "Para fechar o mês na meta", lines };
}

export function buildDashboardAnalysis(data: SupportMacroDashboard): DashboardAnalysisSection[] {
  const month = monthSection(data);
  return month ? [peakSection(data), month] : [peakSection(data)];
}
