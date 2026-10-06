import * as React from "react";

import { cn } from "@/lib/utils";

export function Badge({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "inline-flex max-w-full items-center gap-1 rounded-full border bg-slate-50 px-2.5 py-1 text-xs font-medium leading-4 text-slate-700",
        className
      )}
      {...props}
    />
  );
}
