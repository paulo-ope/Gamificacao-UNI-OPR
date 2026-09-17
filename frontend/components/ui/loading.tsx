import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Indicador de carregamento em linha (ícone girando + texto), centralizado - padroniza o bloco que
 * se repetia em `app/suporte/page.tsx` (painel individual, lista de atendimentos, timeline, detalhe
 * do atendimento), cada um só variando a altura mínima/borda e o texto. Não cobre os skeletons de
 * gráfico/card espalhados pelo código - esses têm forma própria (replicam o layout do que vai
 * carregar) e não devem virar um spinner genérico.
 */
export interface LoadingProps {
  label?: string;
  className?: string;
}

export function Loading({ label = "Carregando...", className }: LoadingProps) {
  return (
    <div className={cn("flex items-center justify-center gap-2 text-sm text-slate-500", className)} aria-busy="true">
      <Loader2 className="h-4 w-4 animate-spin" />
      {label}
    </div>
  );
}
