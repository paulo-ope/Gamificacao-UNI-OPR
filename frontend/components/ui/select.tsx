"use client";

import * as React from "react";
import { useFieldControlId } from "@/components/ui/field";
import { cn } from "@/lib/utils";

/** Native selection preserves keyboard, mobile picker and existing change-event contracts. */
export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, id, ...props }, ref) => {
    const controlId = useFieldControlId(id);
    return <select ref={ref} id={controlId} className={cn("field-control h-10 w-full min-w-0 px-3 py-2", className)} {...props} />;
  },
);
Select.displayName = "Select";
