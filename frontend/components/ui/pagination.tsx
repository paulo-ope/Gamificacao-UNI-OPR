"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Padrão único de paginação do Workspace - antes disso existiam 3 implementações quase idênticas
 * (Gestão em `management-cases-panel.tsx`, Suporte em `app/suporte/page.tsx` e o `DrillPagination`
 * de `scheduling-drill-header.tsx` usado em 4 painéis de Agendamento), cada uma com o próprio texto
 * "Página X de Y" e botões Anterior/Próxima. Este componente cobre os três casos sem mudar
 * comportamento: mesma prop de página/total, mesmos estados de desabilitado.
 */
export interface PaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  /** Contagem total de itens, exibida ao lado do "Página X de Y" quando informada (ex.: "· 42 caso(s)"). */
  totalItems?: number;
  /** Rótulo do item para o contador (ex.: "caso(s)", "registros"). Só é usado junto com `totalItems`. */
  itemLabel?: string;
  pageSize?: number;
  pageSizeOptions?: number[];
  onPageSizeChange?: (size: number) => void;
  disabled?: boolean;
  className?: string;
  /**
   * Densidade visual - existiam 3 tamanhos diferentes nas implementações originais (Gestão usava
   * botões `sm`, Suporte usava o tamanho padrão do `Button`, Agendamento usava botões `h-8`/`text-xs`
   * via `DrillPagination`). Escolha o `size` que reproduz o consumidor original em vez de forçar um
   * tamanho único, pra não alterar a aparência existente.
   */
  size?: "compact" | "sm" | "default";
  /** Gestão não usava setas nos botões; Suporte e Agendamento usavam. Default true para preservar os dois. */
  showIcons?: boolean;
  /** Sobrescreve a classe do rótulo "Página X de Y" quando o consumidor original usava uma cor/tamanho diferente do padrão de `size`. */
  labelClassName?: string;
}

export function Pagination({
  page,
  totalPages,
  onPageChange,
  totalItems,
  itemLabel,
  pageSize,
  pageSizeOptions,
  onPageSizeChange,
  disabled = false,
  className,
  size = "sm",
  showIcons = true,
  labelClassName,
}: PaginationProps) {
  const safeTotalPages = totalPages || 1;
  const labelClass = labelClassName ?? (size === "compact" ? "text-xs text-slate-500" : "text-sm text-slate-500");
  const buttonSize = size === "compact" ? "sm" : size === "default" ? "default" : "sm";
  const buttonClass = size === "compact" ? "h-8 px-2" : undefined;
  const iconClass = size === "compact" ? "h-3.5 w-3.5" : "h-4 w-4";

  return (
    <div className={cn("flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between", className)}>
      <p className={labelClass}>
        Página {page} de {safeTotalPages}
        {typeof totalItems === "number" ? ` · ${totalItems} ${itemLabel ?? "itens"}` : null}
      </p>
      <div className={cn("flex items-center", size === "compact" ? "gap-1.5" : "gap-2")}>
        {pageSizeOptions && onPageSizeChange ? (
          <select
            value={String(pageSize ?? pageSizeOptions[0])}
            disabled={disabled}
            onChange={(event) => onPageSizeChange(Number(event.target.value))}
            className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700"
          >
            {pageSizeOptions.map((size) => (
              <option key={size} value={size}>
                {size}/página
              </option>
            ))}
          </select>
        ) : null}
        <Button
          type="button"
          size={buttonSize}
          variant="outline"
          className={buttonClass}
          disabled={disabled || page <= 1}
          onClick={() => onPageChange(Math.max(1, page - 1))}
        >
          {showIcons ? <ChevronLeft className={iconClass} /> : null} Anterior
        </Button>
        <Button
          type="button"
          size={buttonSize}
          variant="outline"
          className={buttonClass}
          disabled={disabled || safeTotalPages === 0 || page >= safeTotalPages}
          onClick={() => onPageChange(page + 1)}
        >
          Próxima {showIcons ? <ChevronRight className={iconClass} /> : null}
        </Button>
      </div>
    </div>
  );
}
