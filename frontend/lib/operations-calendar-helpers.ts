import type { OperationCalendarTeamModel, OperationPerformanceBand } from "@/lib/operations-api";

// Lógica pura de cor/meta do calendário operacional - compartilhada entre a tela
// (operations-monthly-calendar.tsx) e o export em planilha (use-calendar-export.ts) para as duas
// nunca divergirem sobre qual cor representa qual desempenho.

export function customBackground(performance: OperationPerformanceBand, model: OperationCalendarTeamModel | null) {
  if (!model || performance === "neutral") return undefined;
  if (performance === "below") return model.below_target_color;
  if (performance === "median") return model.median_color;
  if (performance === "good") return model.good_color;
  return model.excellent_color;
}

export function ruleFor(model: OperationCalendarTeamModel, period: "weekday" | "saturday" | "sunday" | "monthly") {
  return model.target_rules.find((rule) => rule.period_type === period);
}

export function dayPeriod(weekday: number): "weekday" | "saturday" | "sunday" {
  if (weekday === 5) return "saturday";
  if (weekday === 6) return "sunday";
  return "weekday";
}

export function dayTarget(model: OperationCalendarTeamModel | null, weekday: number) {
  if (!model) return null;
  const rule = ruleFor(model, dayPeriod(weekday));
  if (rule) return rule.enabled ? rule : null;
  return weekday < 5 ? { target_quantity: model.daily_target } : null;
}

export function modelLegend(model: OperationCalendarTeamModel) {
  const rule = ruleFor(model, "weekday");
  const median = rule?.median_from_quantity ?? model.median_from_quantity;
  const good = rule?.good_from_quantity ?? model.good_from_quantity;
  const target = rule?.target_quantity ?? model.daily_target;
  return [
    { key: "below" as const, label: `Abaixo 1–${median - 1}`, color: model.below_target_color },
    { key: "median" as const, label: `Mediano ${median}–${good - 1}`, color: model.median_color },
    { key: "good" as const, label: `Bom ${good}–${target - 1}`, color: model.good_color },
    { key: "excellent" as const, label: `Excelente ${target}+`, color: model.excellent_color },
  ];
}

export const PERFORMANCE_LABEL: Record<OperationPerformanceBand, string> = {
  neutral: "Sem produção",
  below: "Abaixo da meta",
  median: "Mediano",
  good: "Bom",
  excellent: "Excelente",
};

export function performanceLabel(performance: OperationPerformanceBand, quantity: number, model: OperationCalendarTeamModel | null) {
  if (!model && quantity > 0) return "Sem meta configurada";
  return PERFORMANCE_LABEL[performance];
}
