"use client";

import { cn } from "@/lib/utils";

// Contraparte circular do AppCheckbox (components/ui/checkbox.tsx) - usado quando exatamente UMA
// opção de um grupo pode estar selecionada (ex.: visão Pessoal/Global, agrupamento de uma
// tabela). Mesma linguagem visual (borda cinza -> preenchimento azul da marca quando ativo).
export function AppRadio({
  checked,
  onSelect,
  ariaLabel,
  disabled,
  className,
}: {
  checked: boolean;
  onSelect: () => void;
  ariaLabel?: string;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={onSelect}
      className={cn(
        "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
        checked ? "border-uni-royal" : "border-slate-300 hover:border-slate-400",
        className
      )}
    >
      {checked ? <span className="h-2.5 w-2.5 rounded-full bg-uni-royal" /> : null}
    </button>
  );
}
