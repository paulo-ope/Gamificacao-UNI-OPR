import type { ReactNode } from "react";
import { Inbox } from "lucide-react";

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
  icon = <Inbox className="h-6 w-6" aria-hidden="true" />,
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
          ? "rounded-2xl border border-dashed border-slate-300 bg-slate-50/50 px-6 py-12"
          : "py-14",
        className,
      )}
    >
      {icon ? <div className="mx-auto flex w-fit items-center justify-center rounded-2xl border border-slate-200 bg-white p-3 text-slate-500 shadow-sm">{icon}</div> : null}
      <h3 className={titleClassName ?? cn("font-semibold text-slate-800", icon ? "mt-3" : undefined)}>{title}</h3>
      {description ? (
        <p className={descriptionClassName ?? "mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500"}>{description}</p>
      ) : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}
