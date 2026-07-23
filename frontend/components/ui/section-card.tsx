import * as React from "react";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type SectionCardProps = {
  eyebrow: string;
  title: string;
  subtitle?: string;
  badge?: React.ReactNode;
  actions?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
  contentClassName?: string;
};

// Card padrão "premium" do sistema (mesmo padrão do módulo de operações analíticas:
// operations-trend-chart.tsx) - eyebrow azul, título forte, subtítulo discreto.
export function SectionCard({ eyebrow, title, subtitle, badge, actions, children, className, contentClassName }: SectionCardProps) {
  return (
    <Card className={cn("overflow-hidden rounded-2xl border-slate-200 bg-white shadow-sm", className)}>
      <CardHeader className="flex flex-row items-start justify-between gap-3 pb-0">
        <div className="min-w-0">
          <p className="text-[9px] font-bold uppercase tracking-[0.18em] text-blue-600">{eyebrow}</p>
          <h3 className="mt-1 text-base font-semibold text-slate-950">{title}</h3>
          {subtitle ? <p className="mt-1 text-[11px] text-slate-500">{subtitle}</p> : null}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {badge ? (
            <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[9px] font-semibold text-slate-500">
              {badge}
            </span>
          ) : null}
          {actions}
        </div>
      </CardHeader>
      {children ? <CardContent className={cn("pt-4", contentClassName)}>{children}</CardContent> : null}
    </Card>
  );
}
