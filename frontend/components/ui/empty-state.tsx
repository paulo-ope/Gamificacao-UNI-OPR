import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Bloco padrão de "sem resultados" (ícone + título + descrição) - antes disso existiam blocos quase
 * idênticos espalhados pelo código, cada um reescrevendo o mesmo ícone cinza centralizado + título +
 * descrição com paddings ligeiramente diferentes. Este componente cobre as duas variações mais
 * comuns encontradas (cartão com borda tracejada vs bloco simples centralizado) sem generalizar a
 * mensagem de negócio - o título/descrição continuam vindo de cada consumidor.
 */
export interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  /** "card": cartão com borda tracejada, fundo branco e mais respiro (bloco isolado na tela). "plain": bloco simples centralizado, sem borda (dentro de uma célula/lista que já tem seu próprio container). */
  variant?: "card" | "plain";
  className?: string;
  /** Overrides pontuais de estilo do título/descrição, para reproduzir exatamente um bloco existente que não seguia o peso/tamanho padrão. */
  titleClassName?: string;
  descriptionClassName?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  variant = "card",
  className,
  titleClassName,
  descriptionClassName,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "text-center",
        variant === "card"
          ? "rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-16 shadow-sm"
          : "py-14",
        className,
      )}
    >
      {icon ? <div className="mx-auto w-fit text-slate-300">{icon}</div> : null}
      <h3 className={titleClassName ?? cn("font-semibold text-slate-800", icon ? "mt-3" : undefined)}>{title}</h3>
      {description ? (
        <p className={descriptionClassName ?? "mt-1 text-sm text-slate-500"}>{description}</p>
      ) : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}
