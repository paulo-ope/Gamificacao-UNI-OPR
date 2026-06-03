"use client";

import * as React from "react";

const TooltipProvider = ({ children }: { children: React.ReactNode }) => <>{children}</>;
const Tooltip = ({ children }: { children: React.ReactNode }) => <span className="group relative inline-flex">{children}</span>;
const TooltipTrigger = ({ children, asChild = false }: { children: React.ReactNode; asChild?: boolean }) => (
  <>{asChild ? children : <span>{children}</span>}</>
);
const TooltipContent = ({ children }: { children: React.ReactNode }) => (
  <span className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 hidden -translate-x-1/2 whitespace-nowrap rounded-md border bg-white px-2 py-1 text-xs text-slate-700 shadow-md group-hover:inline-flex">
    {children}
  </span>
);

export { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger };
