import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

// Consolidado de 3 cópias quase idênticas (collaborator-registry-panel.tsx,
// leadership-bonus-panel.tsx, user-management-panel.tsx - achado da auditoria de layout,
// Fase 5 do plano de reestruturação da Gamificação, 2026-09-17). Valor grande com destaque
// opcional por cor, ícone + rótulo acima, texto de apoio abaixo - diferente do
// `SummaryMetric` (components/ui/summary-metric.tsx), que é o tile compacto com delta
// percentual; este é o cartão de resumo "grande" usado em cabeçalhos de painel.
export function SummaryCard({
  icon,
  label,
  value,
  hint,
  accent = "default",
  className,
}: {
  icon?: ReactNode;
  label: string;
  value: string;
  hint: string;
  accent?: "default" | "highlight" | "warning";
  className?: string;
}) {
  const accentClass =
    accent === "highlight" ? "text-uni-royal" : accent === "warning" ? "text-amber-700" : "text-slate-950";

  return (
    <div className={cn("rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]", className)}>
      <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
        {icon}
        {label}
      </div>
      <div className={cn("mt-3 text-2xl font-semibold", accentClass)}>{value}</div>
      <div className="mt-1 text-sm text-slate-500">{hint}</div>
    </div>
  );
}
