import type { SupportMacroCard, SupportMacroDashboard, SupportMacroProjectionItem } from "@/lib/types";

import { formatCardValue } from "./dashboard-format";

// Análise geral dos Indicadores do Suporte (pedido do usuário, 2026-10-27): o período dia a dia, as semanas do mês e a
// projeção de fechamento do mês. Números prontos do backend; aqui só se monta o modelo que a tela desenha em tabelas.

export type AnalysisTone = "ok" | "warn" | "bad" | "none";
export type AnalysisCell = { text: string; tone: AnalysisTone };

export type DashboardAnalysis = {
  days: { label: string; peak: boolean; cells: AnalysisCell[] }[];
  peak: {
    headline: string;
    reasons: { reason: string; count: number; usual: number; heavy: boolean }[];
    note: string | null;
  };
  weeks: { label: string; range: string; note: string | null; muted: boolean; cells: AnalysisCell[] }[];
  projection: { range: string; rows: { name: string; month: string; pace: string; target: string; required: string; verdict: string; tone: AnalysisTone }[] } | null;
};

// Colunas das tabelas dia a dia e semana a semana: chave do cartão (para meta e formato) e título.
export const DAY_COLUMNS = ["Atendimentos OPA", "Realizados IXC", "Foi a campo", "TMR", "TMA", "Avaliação"] as const;
export const WEEK_COLUMNS = ["Atendimentos OPA", "TMR", "TMA", "Avaliação", "Realizados IXC", "Foi a campo", "Resolutividade"] as const;

const PROJECTION_LABELS: Record<string, { name: string; unit: "count" | "seconds" | "score" | "percent" }> = {
  opa_total: { name: "Atendimentos OPA", unit: "count" },
  tmr: { name: "TMR", unit: "seconds" },
  tma: { name: "TMA", unit: "seconds" },
  csat: { name: "Avaliação (CSAT)", unit: "score" },
  performed: { name: "Realizados IXC", unit: "count" },
  field: { name: "Foi a campo", unit: "count" },
  resolutivity: { name: "Resolutividade", unit: "percent" },
};
const PROJECTION_ORDER = ["opa_total", "performed", "field", "tmr", "tma", "csat", "resolutivity"];
const MAX_REASONS = 5;
// Um motivo "pesou" no pico se passou do habitual dele por esta proporção e por pelo menos esta quantidade.
const HEAVY_RATIO = 1.5;
const HEAVY_MIN_EXTRA = 3;
const DASH: AnalysisCell = { text: "-", tone: "none" };

const number = (value: number, digits = 1) => new Intl.NumberFormat("pt-BR", { maximumFractionDigits: digits }).format(value);
const dayMonth = (iso: string) => iso.slice(0, 10).split("-").reverse().slice(0, 2).join("/");
const weekday = (iso: string) => new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString("pt-BR", { weekday: "short" }).replace(".", "");

function toneFor(value: number | null | undefined, target: number | null | undefined, direction: "min" | "max", margin = 0.1): AnalysisTone {
  if (value === null || value === undefined || target === null || target === undefined) return "none";
  const met = direction === "min" ? value >= target : value <= target;
  if (met) return "ok";
  const gap = direction === "min" ? (target - value) / target : (value - target) / target;
  return gap <= margin ? "warn" : "bad";
}

type Targets = { tmr: number | null; tma: number | null; csat: number | null; resolutivity: number | null };

function targetsOf(cards: SupportMacroCard[]): Targets {
  const target = (key: string) => cards.find((card) => card.key === key)?.target ?? null;
  return { tmr: target("tmr"), tma: target("tma"), csat: target("csat"), resolutivity: target("resolutivity") };
}

function cell(value: number | null | undefined, unit: "count" | "seconds" | "score" | "percent", tone: AnalysisTone = "none"): AnalysisCell {
  if (value === null || value === undefined) return DASH;
  return { text: formatCardValue({ unit }, value), tone };
}

function buildDays(data: SupportMacroDashboard, targets: Targets): DashboardAnalysis["days"] {
  const peakDay = data.peak_day?.day;
  return data.daily.map((point) => ({
    label: `${dayMonth(point.day)} ${weekday(point.day)}`,
    peak: point.day === peakDay,
    cells: [
      cell(point.opa_total, "count"),
      cell(point.performed, "count"),
      cell(point.field, "count"),
      cell(point.tmr_seconds, "seconds", toneFor(point.tmr_seconds, targets.tmr, "max")),
      cell(point.tma_seconds, "seconds", toneFor(point.tma_seconds, targets.tma, "max")),
      cell(point.rating, "score", toneFor(point.rating, targets.csat, "min")),
    ],
  }));
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
    headline: `Dia ${dayMonth(peak.day)} (${weekday(peak.day)}): ${number(peak.total, 0)} atendimentos no OPA, ${number(peak.percent_above)}% acima da média dos outros dias (${number(peak.average)} por dia).`,
    reasons,
    note: reasons.some((item) => item.heavy) ? null : "Nenhum motivo isolado explica o aumento: o volume subiu de forma geral.",
  };
}

function buildWeeks(data: SupportMacroDashboard, targets: Targets): DashboardAnalysis["weeks"] {
  const ixc = new Map(data.weekly.buckets.map((bucket) => [bucket.key, bucket]));
  return data.weeks_opa.map((week) => {
    const bucket = ixc.get(week.key);
    const range = `${dayMonth(week.date_from)} a ${dayMonth(week.date_to)}`;
    if (week.future) {
      return { label: week.label, range, note: "ainda não começou", muted: true, cells: WEEK_COLUMNS.map(() => DASH) };
    }
    return {
      label: week.label,
      range,
      note: week.partial ? "em andamento" : null,
      muted: false,
      cells: [
        cell(week.total, "count"),
        cell(week.tmr_seconds, "seconds", toneFor(week.tmr_seconds, targets.tmr, "max")),
        cell(week.tma_seconds, "seconds", toneFor(week.tma_seconds, targets.tma, "max")),
        cell(week.rating, "score", toneFor(week.rating, targets.csat, "min")),
        cell(bucket?.performed, "count"),
        cell(bucket?.field, "count"),
        cell(bucket?.resolutivity, "percent", toneFor(bucket?.resolutivity, targets.resolutivity, "min")),
      ],
    };
  });
}

function projectionRow(item: SupportMacroProjectionItem): NonNullable<DashboardAnalysis["projection"]>["rows"][number] | null {
  const meta = PROJECTION_LABELS[item.key];
  if (!meta) return null;
  const show = (value: number | null) => (value === null ? "-" : formatCardValue({ unit: meta.unit }, value));
  const sign = item.direction === "min" ? "≥" : "≤";
  const row = {
    name: meta.name,
    month: show(item.month_value),
    pace: show(item.pace_value),
    target: item.target === null ? "-" : `${sign} ${show(item.target)}`,
    required: item.status === "reachable" ? show(item.required_value) : "-",
  };
  switch (item.status) {
    case "closed":
      return { ...row, verdict: item.pace_meets_target === null ? "Mês encerrado" : item.pace_meets_target ? "Mês fechou na meta" : "Mês fechou fora da meta", tone: item.pace_meets_target === null ? "none" : item.pace_meets_target ? "ok" : "bad" };
    case "reachable":
      return { ...row, verdict: item.pace_meets_target ? "No ritmo atual bate a meta" : "Precisa melhorar o ritmo", tone: item.pace_meets_target ? "ok" : "warn" };
    case "unreachable":
      return { ...row, verdict: "Não dá mais para fechar o mês na meta", tone: "bad" };
    case "no_target":
      return { ...row, verdict: "Sem meta definida", tone: "none" };
    default:
      return { ...row, verdict: "Sem dado suficiente no mês", tone: "none" };
  }
}

function buildProjection(data: SupportMacroDashboard): DashboardAnalysis["projection"] {
  const projection = data.month_projection;
  if (!projection) return null;
  const range =
    projection.remaining_days === 0
      ? `Mês de ${dayMonth(projection.month_from)} a ${dayMonth(projection.month_to)}, já encerrado`
      : `Resto do mês: ${dayMonth(projection.remaining_from ?? projection.month_to)} a ${dayMonth(projection.month_to)} (${projection.remaining_days} ${projection.remaining_days === 1 ? "dia" : "dias"}), no ritmo do período selecionado`;
  const rows = PROJECTION_ORDER.flatMap((key) => {
    const item = projection.items.find((candidate) => candidate.key === key);
    const row = item ? projectionRow(item) : null;
    return row ? [row] : [];
  });
  return { range, rows };
}

export function buildDashboardAnalysis(data: SupportMacroDashboard): DashboardAnalysis {
  const targets = targetsOf(data.cards);
  return { days: buildDays(data, targets), peak: buildPeak(data), weeks: buildWeeks(data, targets), projection: buildProjection(data) };
}
