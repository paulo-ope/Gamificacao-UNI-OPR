"use client";

import { Check } from "lucide-react";

import { cn } from "@/lib/utils";

// Visual de caixa de seleção (quadrado) - usado quando o clique SELECIONA um item/linha para uma
// ação em lote ou marca uma opção booleana, nunca para representar liga/desliga de uma
// configuração real (isso é o AppSwitch, components/gamification/config-ui.tsx). Compartilhado
// entre os módulos de gamificação, operações e admin para manter uma única linguagem visual.
export function AppCheckbox({
  checked,
  onCheckedChange,
  ariaLabel,
  disabled,
  className,
}: {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  ariaLabel?: string;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "flex h-5 w-5 shrink-0 items-center justify-center rounded border transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
        checked ? "border-uni-royal bg-uni-royal text-white" : "border-slate-300 bg-white hover:border-slate-400",
        className
      )}
    >
      {checked ? <Check className="h-3.5 w-3.5" /> : null}
    </button>
  );
}
