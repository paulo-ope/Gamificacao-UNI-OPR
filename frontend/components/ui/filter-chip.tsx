import { X } from "lucide-react";

import { Badge } from "@/components/ui/badge";

/**
 * Chip de resumo de um filtro ativo, dois estilos conforme onde a barra de filtros vive:
 * - `variant="badge"` (padrão): contagem simples, não removível - "Filial: 2" - usado nas barras
 *   compactas (Agendamento, SGP Suporte).
 * - `variant="pill"`: valor(es) por extenso com botão de remover embutido - usado na barra da
 *   Visão Geral, onde o chip é a única forma de editar o filtro sem reabrir o formulário inteiro.
 * Extraído em 2026-09-18 ao padronizar o formato de filtro recolhível entre módulos.
 */
export function FilterChip({
  label,
  onRemove,
  variant = "badge",
}: {
  label: string;
  onRemove?: () => void;
  variant?: "badge" | "pill";
}) {
  if (variant === "pill") {
    return (
      <span className="inline-flex max-w-full items-center gap-1 rounded-full border border-slate-200 bg-slate-50 py-1 pl-2.5 pr-1 text-[11px] font-medium text-slate-700">
        <span className="truncate">{label}</span>
        {onRemove ? (
          <button
            type="button"
            onClick={onRemove}
            aria-label={`Remover filtro ${label}`}
            className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-slate-400 hover:bg-slate-200 hover:text-slate-700"
          >
            <X className="h-2.5 w-2.5" />
          </button>
        ) : null}
      </span>
    );
  }

  return <Badge className="border-slate-200 bg-slate-100 text-[11px] text-slate-700">{label}</Badge>;
}
