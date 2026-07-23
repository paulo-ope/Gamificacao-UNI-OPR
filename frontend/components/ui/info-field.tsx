import * as React from "react";

import { cn } from "@/lib/utils";

type InfoProps = {
  label: string;
  value: React.ReactNode;
  className?: string;
};

// Par rótulo/valor padrão dos detalhes (mesmo padrão do operations-order-detail-dialog).
export function Info({ label, value, className }: InfoProps) {
  const isEmpty = value === null || value === undefined || value === "";
  return (
    <div className={cn("min-w-0", className)}>
      <p className="text-[9px] font-semibold uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-0.5 break-words text-xs font-medium text-slate-800">{isEmpty ? "—" : value}</p>
    </div>
  );
}
