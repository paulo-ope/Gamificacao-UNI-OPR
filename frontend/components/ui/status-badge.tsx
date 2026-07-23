import type { LucideIcon } from "lucide-react";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { type Tone, toneBadgeClass } from "@/lib/tones";
import { cn } from "@/lib/utils";

const DOT_CLASS: Record<Tone, string> = {
  emerald: "bg-emerald-500",
  amber: "bg-amber-500",
  red: "bg-red-500",
  blue: "bg-blue-500",
  violet: "bg-violet-500",
  slate: "bg-slate-400"
};

type StatusBadgeProps = React.HTMLAttributes<HTMLDivElement> & {
  tone: Tone;
  icon?: LucideIcon;
  /** Em linhas de tabela densas, um ponto sólido lê melhor que um ícone de 12px (que vira uma
   * "bolinha" ilegível). Use `dot` nesses contextos; reserve `icon` para cards com mais espaço
   * (ex.: resumo do drawer de auditoria). */
  dot?: boolean;
};

export function StatusBadge({ tone, icon: Icon, dot = false, children, className, ...props }: StatusBadgeProps) {
  return (
    <Badge className={cn("gap-1.5 whitespace-nowrap", toneBadgeClass(tone), className)} {...props}>
      {dot ? (
        <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", DOT_CLASS[tone])} />
      ) : Icon ? (
        <Icon className="h-3.5 w-3.5 shrink-0" />
      ) : null}
      {children}
    </Badge>
  );
}

type SecondaryPillProps = React.HTMLAttributes<HTMLSpanElement> & {
  tone: Tone;
  icon?: LucideIcon;
};

// Pill secundário compacto (Reagendada/Pendência/etiqueta de retorno) - sempre no máximo um por
// linha de O.S., abaixo do StatusBadge principal.
export function SecondaryPill({ tone, icon: Icon, children, className, ...props }: SecondaryPillProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] font-medium",
        toneBadgeClass(tone),
        className
      )}
      {...props}
    >
      {Icon ? <Icon className="h-3 w-3 shrink-0" /> : null}
      {children}
    </span>
  );
}
