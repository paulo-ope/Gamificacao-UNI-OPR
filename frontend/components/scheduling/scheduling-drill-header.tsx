"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";

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
    <div className="flex items-center justify-between border-t border-slate-100 p-3">
      <p className="text-xs text-slate-500">
        Página <span className="font-semibold text-slate-700">{page}</span> de {totalPages}
      </p>
      <div className="flex items-center gap-1.5">
        <Button type="button" size="sm" variant="outline" className="h-8 px-2" disabled={page <= 1} onClick={() => onChange(Math.max(1, page - 1))}>
          <ChevronLeft className="h-3.5 w-3.5" /> Anterior
        </Button>
        <Button type="button" size="sm" variant="outline" className="h-8 px-2" disabled={page >= totalPages} onClick={() => onChange(page + 1)}>
          Próxima <ChevronRight className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}
