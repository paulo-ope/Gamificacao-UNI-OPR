"use client";

import { Pagination } from "@/components/ui/pagination";

/**
 * Adaptador fino sobre `components/ui/pagination.tsx` (padrão único de paginação do Workspace) -
 * mantém a mesma assinatura `{ page, totalPages, onChange }` já usada nos 4 painéis de drill de
 * Agendamento, para não precisar tocar em cada call site.
 */
export function DrillPagination({
  page,
  totalPages,
  onChange,
}: {
  page: number;
  totalPages: number;
  onChange: (next: number) => void;
}) {
  return (
    <div className="border-t border-slate-100 p-3">
      <Pagination page={page} totalPages={totalPages} onPageChange={onChange} size="compact" />
    </div>
  );
}
