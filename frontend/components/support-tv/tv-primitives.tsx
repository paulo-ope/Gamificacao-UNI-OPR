import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import { TV_CLASSES, type TvStatus, type TvTheme } from "./tv-theme";

export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("pt-BR").format(value);
}

export function formatPercent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return "—";
  return `${value.toLocaleString("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits })}%`;
}

type TvCardProps = {
  theme: TvTheme;
  eyebrow: string;
  children: ReactNode;
  className?: string;
  // Só quando há um estado real a comunicar (meta estourada, alerta ativo): uma faixa fina na borda
  // esquerda. Nunca uma moldura colorida em volta do cartão inteiro.
  status?: TvStatus;
  aside?: ReactNode;
  // Atraso (ms) da animação de entrada - os cartões aparecem em cascata na primeira carga.
  revealDelay?: number;
};

export function TvCard({ theme, eyebrow, children, className, status = "neutral", aside, revealDelay = 0 }: TvCardProps) {
  const t = TV_CLASSES[theme];
  return (
    <section className={cn("tv-reveal relative flex min-h-0 flex-col overflow-hidden rounded-xl p-5", t.card, className)} style={{ animationDelay: `${revealDelay}ms` }}>
      {status !== "neutral" && <span className={cn("absolute inset-y-0 left-0 w-1", t.status[status].bar)} aria-hidden="true" />}
      <header className="flex items-center justify-between gap-3">
        <h2 className={cn("text-sm font-semibold uppercase tracking-[0.1em]", t.label)}>{eyebrow}</h2>
        {aside}
      </header>
      <div className="mt-3 flex min-h-0 flex-1 flex-col">{children}</div>
    </section>
  );
}

// Bloco que não pôde ser calculado: nunca um zero nem "tudo normal" no lugar (norma de métricas,
// seção 1 - número ausente é melhor que número errado).
export function TvUnavailable({ theme }: { theme: TvTheme }) {
  return (
    <div className="flex flex-1 items-center justify-center text-center">
      <p className={cn("text-lg", TV_CLASSES[theme].muted)}>Indisponível no momento</p>
    </div>
  );
}

export function TvEmpty({ theme, children }: { theme: TvTheme; children: ReactNode }) {
  return (
    <div className="flex flex-1 items-center justify-center text-center">
      <p className={cn("text-lg", TV_CLASSES[theme].muted)}>{children}</p>
    </div>
  );
}
