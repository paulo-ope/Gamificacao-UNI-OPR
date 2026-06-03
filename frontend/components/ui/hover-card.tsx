"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

const HoverCard = ({ children }: { children: React.ReactNode }) => <span className="group relative inline-flex">{children}</span>;
const HoverCardTrigger = ({ children }: { children: React.ReactNode }) => <>{children}</>;
const HoverCardContent = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(
      "absolute left-0 top-full z-40 mt-2 hidden w-80 rounded-md border bg-white p-3 text-sm text-slate-700 shadow-lg group-hover:block",
      className
    )}
    {...props}
  />
);

export { HoverCard, HoverCardContent, HoverCardTrigger };
