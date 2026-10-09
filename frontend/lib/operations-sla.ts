import type { OperationSlaItem } from "@/lib/operations-api";
import type { Tone } from "@/lib/tones";

export type SlaTone = "neutral" | "danger" | "warning" | "success";

/** Meta de SLA do sistema (a mesma que `operations/attention.py` usa nos pontos de atenção). */
export const SLA_TARGET_PERCENT = 80;

export function slaTone(rate: number | null): SlaTone {
  if (rate === null) return "neutral";
  if (rate >= 80) return "success";
  if (rate >= 60) return "warning";
  return "danger";
}

/**
 * Consolida vários grupos de SLA num só (gauge "Média selecionada" da Visão Geral): SLA =
 * soma de no prazo / soma de finalizadas (ponderado pelo volume, não média simples dos
 * percentuais) e tempo médio ponderado por finalizadas. `null` quando não há O.S. finalizada.
 */
export function aggregateSlaItems(
  items: readonly Pick<OperationSlaItem, "completed" | "on_time" | "average_closing_hours">[],
): { completed: number; sla_rate: number | null; average_closing_hours: number | null } {
  const completed = items.reduce((sum, item) => sum + item.completed, 0);
  if (completed === 0) return { completed: 0, sla_rate: null, average_closing_hours: null };
  const onTime = items.reduce((sum, item) => sum + item.on_time, 0);
  const withHours = items.filter((item) => item.average_closing_hours !== null && item.completed > 0);
  const hoursWeight = withHours.reduce((sum, item) => sum + item.completed, 0);
  const hours = withHours.reduce((sum, item) => sum + (item.average_closing_hours as number) * item.completed, 0);
  return {
    completed,
    sla_rate: Math.round((onTime / completed) * 1000) / 10,
    average_closing_hours: hoursWeight > 0 ? Math.round((hours / hoursWeight) * 10) / 10 : null,
  };
}

export function slaBadgeClass(rate: number | null) {
  const tone = slaTone(rate);
  if (tone === "success") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (tone === "warning") return "border-amber-200 bg-amber-50 text-amber-700";
  if (tone === "danger") return "border-red-200 bg-red-50 text-red-700";
  return "border-slate-200 bg-slate-50 text-slate-500";
}

// Ponte para o sistema de tons compartilhado (`lib/tones.ts`). Existe para que nenhuma tela
// precise reescrever "verde acima de 80, vermelho abaixo de 60" numa terceira tabela de cor -
// achado real: a Visão Geral e o quadro por filial começaram a fazer exatamente isso.
export function slaSystemTone(rate: number | null): Tone {
  const tone = slaTone(rate);
  if (tone === "success") return "emerald";
  if (tone === "warning") return "amber";
  if (tone === "danger") return "red";
  return "slate";
}
