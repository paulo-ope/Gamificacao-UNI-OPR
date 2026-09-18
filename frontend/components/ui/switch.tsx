"use client";

import { cn } from "@/lib/utils";

// Liga/desliga de uma configuração real (diferente do AppCheckbox, components/ui/checkbox.tsx,
// que seleciona um item/linha para ação em lote). Movido de components/gamification/config-ui.tsx
// (2026-09-16, auditoria de layout) - já era usado fora da Gamificação (overview-screen.tsx,
// ixc-sync-settings-card.tsx), então vivia no módulo errado.
export function AppSwitch({
  checked,
  onCheckedChange,
  label,
}: {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  label?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-2 py-1 text-xs font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        checked ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-slate-50 text-slate-600"
      )}
    >
      <span
        className={cn(
          "relative flex h-5 w-9 items-center rounded-full transition",
          checked ? "bg-emerald-500" : "bg-slate-300"
        )}
      >
        <span
          className={cn(
            "absolute h-4 w-4 rounded-full bg-white shadow-sm transition",
            checked ? "left-4" : "left-0.5"
          )}
        />
      </span>
      <span>{label ?? (checked ? "Ativo" : "Inativo")}</span>
    </button>
  );
}
