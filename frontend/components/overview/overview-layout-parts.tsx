import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** Título de seção da Visão Geral: rótulo em caixa alta e uma linha que preenche o resto. */
export function OverviewSectionHeading({ children }: { children: ReactNode }) {
  return (
    <div className="mb-3 mt-7 flex items-center gap-3">
      <h2 className="text-[11px] font-bold uppercase tracking-[0.09em] text-slate-500">{children}</h2>
      <span className="h-px flex-1 bg-slate-200" aria-hidden="true" />
    </div>
  );
}

const TILE_ACCENT = {
  blue: "before:bg-blue-500",
  teal: "before:bg-teal-500",
  amber: "before:bg-amber-500",
  violet: "before:bg-violet-500",
} as const;

export type OverviewTileAccent = keyof typeof TILE_ACCENT;

/** Número de destaque com faixa de cor à esquerda: usado nos cartões de Ordens de serviço e Suporte. */
export function OverviewTile({
  label,
  value,
  accent,
  sub,
  subClassName,
}: {
  label: string;
  value: ReactNode;
  accent: OverviewTileAccent;
  sub?: ReactNode;
  subClassName?: string;
}) {
  return (
    <div
      className={cn(
        "relative min-w-0 overflow-hidden rounded-xl border border-slate-200 bg-slate-50/70 p-3 pl-4",
        "before:absolute before:bottom-3 before:left-0 before:top-3 before:w-[3px] before:rounded-sm before:content-['']",
        TILE_ACCENT[accent],
      )}
    >
      <p className="min-h-8 text-[11px] leading-snug text-slate-500">{label}</p>
      <p className="mb-1.5 mt-1 break-words text-[1.6rem] font-bold leading-tight tracking-tight text-slate-900 tabular-nums">{value}</p>
      {sub ? <p className={cn("text-[11px] leading-snug text-slate-500", subClassName)}>{sub}</p> : null}
    </div>
  );
}

/** Barra de progresso com rótulo nas duas pontas (ex.: Finalizadas 80,7% ... Pendentes 798). */
export function OverviewProgress({
  leftLabel,
  leftValue,
  rightLabel,
  rightValue,
  percent,
}: {
  leftLabel: string;
  leftValue: string;
  rightLabel: string;
  rightValue: string;
  percent: number | null;
}) {
  const width = percent === null ? 0 : Math.max(0, Math.min(100, percent));
  return (
    <div className="mt-4 flex flex-wrap items-center gap-x-2 gap-y-1.5 border-t border-slate-200 pt-4 text-[11px] text-slate-500">
      <span>
        {leftLabel} <b className="tabular-nums text-slate-900">{leftValue}</b>
      </span>
      <div
        className="h-1.5 min-w-[6rem] flex-1 basis-1/3 overflow-hidden rounded-full bg-slate-200"
        role="meter"
        aria-label={`${leftLabel}: ${leftValue}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(width)}
      >
        <div className="h-full rounded-full bg-teal-600" style={{ width: `${width}%` }} />
      </div>
      <span>
        {rightLabel} <b className="tabular-nums text-slate-900">{rightValue}</b>
      </span>
    </div>
  );
}
