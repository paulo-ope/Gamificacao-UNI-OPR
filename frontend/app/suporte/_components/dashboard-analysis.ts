import type { SupportMacroCard, SupportMacroDashboard } from "@/lib/types";

import { formatCardValue } from "./dashboard-format";

// Análise geral dos Indicadores do Suporte (pedido do usuário, 2026-10-27): o dia de maior aumento e o motivo, e quanto
// cada indicador com meta precisa mudar na semana seguinte para bater a meta. Números prontos do backend; aqui só se
// monta o texto.

export type DashboardAnalysisSection = { title: string; lines: string[] };

const TARGET_KEYS: { key: string; name: string }[] = [
  { key: "tmr", name: "TMR" },
  { key: "tma", name: "TMA" },
  { key: "csat", name: "Avaliação (CSAT)" },
  { key: "resolutivity", name: "Resolutividade" },
];
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

function targetLine(card: SupportMacroCard, name: string): string | null {
  if (card.target === null || card.value === null) return null;
  if (card.status === "partial" || card.status === "no_data") return `${name}: dados ainda incompletos no período, sem como avaliar a meta.`;
  const value = formatCardValue(card, card.value);
  const target = formatCardValue(card, card.target);
  const gap = card.direction === "min" ? card.target - card.value : card.value - card.target;
  if (gap <= 0) return `${name}: ${value}, dentro da meta de ${target}. Manter o ritmo na próxima semana.`;
  return `${name}: ${value} contra a meta de ${target}. Na próxima semana precisa ${card.direction === "min" ? "subir" : "cair"} ${gapWords(card, gap)} para bater a meta.`;
}

export function buildDashboardAnalysis(data: SupportMacroDashboard): DashboardAnalysisSection[] {
  const sections: DashboardAnalysisSection[] = [];
  const peak = data.peak_day;

  if (peak) {
    const lines = [
      `Dia ${dayMonth(peak.day)} teve ${number(peak.total, 0)} atendimentos no OPA, ${number(peak.percent_above)}% acima da média dos outros dias do período (${number(peak.average)} por dia).`,
    ];
    if (peak.reasons.length) {
      lines.push(`Motivos mais frequentes no dia: ${peak.reasons.slice(0, MAX_REASONS).map((item) => `${item.reason} (${item.count}, habitual ${number(item.usual_per_day)} por dia)`).join("; ")}.`);
      const heavy = peak.reasons.filter((item) => item.count >= item.usual_per_day * HEAVY_RATIO && item.count - item.usual_per_day >= HEAVY_MIN_EXTRA);
      lines.push(heavy.length ? `Puxaram o aumento: ${heavy.map((item) => item.reason).join(", ")}.` : "Nenhum motivo isolado explica o aumento: o volume subiu de forma geral.");
    }
    sections.push({ title: "Dia de maior aumento", lines });
  } else {
    sections.push({ title: "Dia de maior aumento", lines: ["Nenhum dia com aumento relevante de atendimentos no período."] });
  }

  const cards = Object.fromEntries(data.cards.map((card) => [card.key, card]));
  const lines = TARGET_KEYS.flatMap(({ key, name }) => {
    const card = cards[key];
    const line = card ? targetLine(card, name) : null;
    return line ? [line] : [];
  });
  if (lines.length) sections.push({ title: "Para bater a meta na próxima semana", lines });

  return sections;
}
