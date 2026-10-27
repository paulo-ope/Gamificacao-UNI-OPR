import type { SupportMacroCard, SupportMacroDashboard } from "@/lib/types";

import { clock, formatCardValue } from "./dashboard-format";

// Análise geral dos Indicadores do Suporte (pedido do usuário, 2026-10-27): o dia de maior aumento e o motivo, quanto
// cada indicador com meta precisa mudar na semana seguinte e o que o resto do mês precisa fechar para a média do mês
// terminar na meta. Números prontos do backend; aqui só se monta o modelo que a tela desenha em tabelas.

export type AnalysisTone = "ok" | "warn" | "bad" | "none";

export type DashboardAnalysis = {
  peak: {
    headline: string;
    reasons: { reason: string; count: number; usual: number; heavy: boolean }[];
    note: string | null;
  };
  goals: { name: string; current: string; target: string; action: string; tone: AnalysisTone }[];
  month: { range: string; rows: { name: string; monthValue: string; target: string; verdict: string; tone: AnalysisTone }[] } | null;
};

const GOAL_KEYS: { key: string; name: string }[] = [
  { key: "tmr", name: "TMR" },
  { key: "tma", name: "TMA" },
  { key: "csat", name: "Avaliação (CSAT)" },
  { key: "resolutivity", name: "Resolutividade" },
];
const MONTH_NAMES: Record<string, string> = { tmr: "TMR", tma: "TMA" };
const MAX_REASONS = 5;
// Um motivo "pesou" no pico se passou do habitual dele por esta proporção e por pelo menos esta quantidade.
const HEAVY_RATIO = 1.5;
const HEAVY_MIN_EXTRA = 3;

const number = (value: number, digits = 1) => new Intl.NumberFormat("pt-BR", { maximumFractionDigits: digits }).format(value);
const dayMonth = (iso: string) => iso.slice(0, 10).split("-").reverse().slice(0, 2).join("/");

/** "35 segundos", "1 min 20 s", "25 min". */
export function durationWords(totalSeconds: number) {
  const seconds = Math.max(0, Math.round(totalSeconds));
  if (seconds < 60) return `${seconds} ${seconds === 1 ? "segundo" : "segundos"}`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return rest ? `${minutes} min ${rest} s` : `${minutes} min`;
}

function gapWords(card: SupportMacroCard, gap: number) {
  switch (card.unit) {
    case "seconds":
      return durationWords(gap);
    case "percent":
      return `${number(gap, 1)} p.p.`;
    case "score":
      return `${number(gap, 2)} ${gap === 1 ? "ponto" : "pontos"}`;
    default:
      return number(gap, 0);
  }
}

function goalRow(card: SupportMacroCard, name: string): DashboardAnalysis["goals"][number] | null {
  if (card.target === null || card.value === null) return null;
  const current = formatCardValue(card, card.value);
  const target = `${card.direction === "min" ? "≥" : "≤"} ${formatCardValue(card, card.target)}`;
  if (card.status === "partial" || card.status === "no_data") return { name, current, target, action: "Dados incompletos", tone: "none" };
  const gap = card.direction === "min" ? card.target - card.value : card.value - card.target;
  if (gap <= 0) return { name, current, target, action: "Dentro da meta: manter", tone: "ok" };
  return { name, current, target, action: `${card.direction === "min" ? "Subir" : "Cair"} ${gapWords(card, gap)}`, tone: card.status === "attention" ? "warn" : "bad" };
}

function buildPeak(data: SupportMacroDashboard): DashboardAnalysis["peak"] {
  const peak = data.peak_day;
  if (!peak) return { headline: "Nenhum dia com aumento relevante de atendimentos no período.", reasons: [], note: null };
  const reasons = peak.reasons.slice(0, MAX_REASONS).map((item) => ({
    reason: item.reason,
    count: item.count,
    usual: item.usual_per_day,
    heavy: item.count >= item.usual_per_day * HEAVY_RATIO && item.count - item.usual_per_day >= HEAVY_MIN_EXTRA,
  }));
  return {
    headline: `Dia ${dayMonth(peak.day)}: ${number(peak.total, 0)} atendimentos no OPA, ${number(peak.percent_above)}% acima da média dos outros dias (${number(peak.average)} por dia).`,
    reasons,
    note: reasons.some((item) => item.heavy) ? null : "Nenhum motivo isolado explica o aumento: o volume subiu de forma geral.",
  };
}

function buildMonth(data: SupportMacroDashboard): DashboardAnalysis["month"] {
  const projection = data.month_projection;
  if (!projection) return null;
  const closedMonth = projection.remaining_days === 0;
  const range = closedMonth
    ? `Mês de ${dayMonth(projection.month_from)} a ${dayMonth(projection.month_to)}, já encerrado`
    : `Resto do mês: ${dayMonth(projection.remaining_from ?? projection.month_to)} a ${dayMonth(projection.month_to)} (${projection.remaining_days} ${projection.remaining_days === 1 ? "dia" : "dias"})`;
  const rows = projection.items.map((item) => {
    const name = MONTH_NAMES[item.key] ?? item.key;
    const unit = { unit: "seconds" } as const;
    const monthValue = item.month_value === null ? "-" : formatCardValue(unit, item.month_value);
    const target = item.target === null ? "-" : `≤ ${formatCardValue(unit, item.target)}`;
    if (item.status === "closed") {
      const hit = item.month_value !== null && item.target !== null && item.month_value <= item.target;
      return { name, monthValue, target, verdict: hit ? "Mês fechou dentro da meta" : "Mês fechou acima da meta", tone: hit ? ("ok" as const) : ("bad" as const) };
    }
    if (item.status === "reachable" && item.required_value !== null) {
      return { name, monthValue, target, verdict: `Precisa fechar o resto do mês em ${clock(item.required_value)}`, tone: "warn" as const };
    }
    if (item.status === "unreachable") return { name, monthValue, target, verdict: "Não dá mais para fechar o mês na meta", tone: "bad" as const };
    return { name, monthValue, target, verdict: "Sem dado suficiente no mês", tone: "none" as const };
  });
  return { range, rows };
}

export function buildDashboardAnalysis(data: SupportMacroDashboard): DashboardAnalysis {
  const cards = Object.fromEntries(data.cards.map((card) => [card.key, card]));
  const goals = GOAL_KEYS.flatMap(({ key, name }) => {
    const card = cards[key];
    const row = card ? goalRow(card, name) : null;
    return row ? [row] : [];
  });
  return { peak: buildPeak(data), goals, month: buildMonth(data) };
}
