"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Indicação de scroll horizontal - achado da auditoria de frontend de 2026-09-14: tabelas largas
 * (ex.: Estrutura operacional da Gestão Integrada) já tinham `overflow-x` funcional em mobile,
 * mas nada avisava que existiam colunas fora da tela - o corte no texto na borda direita parecia
 * conteúdo quebrado, não "arraste para o lado". A sombra some sozinha quando não há overflow (ex.:
 * telas largas) ou quando o usuário já rolou até o fim daquele lado - não cobre conteúdo (é
 * `pointer-events-none`) e não muda o comportamento do scroll em si, só some/aparece um gradiente
 * fino na borda.
 */
function useHorizontalScrollHints(ref: React.RefObject<HTMLDivElement | null>) {
  const [hints, setHints] = React.useState({ left: false, right: false });

  React.useEffect(() => {
    const node = ref.current;
    if (!node) return;

    function update() {
      if (!node) return;
      const { scrollLeft, scrollWidth, clientWidth } = node;
      const maxScrollLeft = scrollWidth - clientWidth;
      // 1px de folga: subpixel de zoom/DPI as vezes deixa 1px "de sobra" mesmo sem overflow real.
      setHints({
        left: scrollLeft > 1,
        right: maxScrollLeft > 1 && scrollLeft < maxScrollLeft - 1,
      });
    }

    update();
    node.addEventListener("scroll", update, { passive: true });
    const observer = new ResizeObserver(update);
    observer.observe(node);
    if (node.firstElementChild) observer.observe(node.firstElementChild);
    return () => {
      node.removeEventListener("scroll", update);
      observer.disconnect();
    };
  }, [ref]);

  return hints;
}

const Table = React.forwardRef<HTMLTableElement, React.HTMLAttributes<HTMLTableElement>>(
  ({ className, ...props }, ref) => {
    const scrollRef = React.useRef<HTMLDivElement>(null);
    const { left, right } = useHorizontalScrollHints(scrollRef);

    return (
      <div className="relative">
        <div ref={scrollRef} tabIndex={left || right ? 0 : undefined} role={left || right ? "region" : undefined} aria-label={left || right ? "Tabela com rolagem horizontal" : undefined} className="w-full overflow-auto rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary">
          <table ref={ref} className={cn("w-full caption-bottom text-sm tabular-nums", className)} {...props} />
        </div>
        {left || right ? <p className="border-t border-slate-100 px-3 py-2 text-xs text-slate-500">Role para os lados para ver todas as colunas.</p> : null}
        {left ? (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-y-0 left-0 w-6 bg-gradient-to-r from-black/10 to-transparent"
          />
        ) : null}
        {right ? (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-y-0 right-0 w-6 bg-gradient-to-l from-black/10 to-transparent"
          />
        ) : null}
      </div>
    );
  }
);
Table.displayName = "Table";

const TableHeader = React.forwardRef<HTMLTableSectionElement, React.HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => <thead ref={ref} className={cn("bg-slate-50/90 [&_tr]:border-b", className)} {...props} />
);
TableHeader.displayName = "TableHeader";

const TableBody = React.forwardRef<HTMLTableSectionElement, React.HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => <tbody ref={ref} className={cn("[&_tr:last-child]:border-0", className)} {...props} />
);
TableBody.displayName = "TableBody";

const TableRow = React.forwardRef<HTMLTableRowElement, React.HTMLAttributes<HTMLTableRowElement>>(
  ({ className, ...props }, ref) => (
    <tr ref={ref} className={cn("border-b border-slate-100 transition-colors hover:bg-blue-50/50 focus-within:bg-blue-50/50 data-[state=selected]:bg-blue-50", className)} {...props} />
  )
);
TableRow.displayName = "TableRow";

const TableHead = React.forwardRef<HTMLTableCellElement, React.ThHTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => (
    <th
      ref={ref}
      className={cn(
        // `[&_button]:uppercase`: cabeçalho ordenável (um <button> por dentro, pra virar
        // clicável) sem isso ficava com case diferente do resto - achado real de 2026-08-25:
        // <button> reseta `text-transform` por padrão do navegador, então não herdava o
        // `uppercase` daqui, e a linha de cabeçalho misturava "OPERADOR" (texto puro) com
        // "Aberta em" (dentro de botão) na mesma tabela.
        "h-11 px-4 text-left align-middle text-xs font-semibold text-slate-600",
        className,
      )}
      {...props}
    />
  )
);
TableHead.displayName = "TableHead";

const TableCell = React.forwardRef<HTMLTableCellElement, React.TdHTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => <td ref={ref} className={cn("px-4 py-3.5 align-middle", className)} {...props} />
);
TableCell.displayName = "TableCell";

export { Table, TableBody, TableCell, TableHead, TableHeader, TableRow };
