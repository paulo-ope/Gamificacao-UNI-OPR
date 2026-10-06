"use client";

import * as React from "react";
import { useFieldControlId } from "@/components/ui/field";

import { cn } from "@/lib/utils";

const Label = React.forwardRef<HTMLLabelElement, React.LabelHTMLAttributes<HTMLLabelElement>>(
  ({ className, htmlFor, ...props }, ref) => {
    const controlId = useFieldControlId(htmlFor);
    return <label ref={ref} htmlFor={controlId} className={cn("text-sm font-medium leading-5 text-slate-700", className)} {...props} />;
  }
);
Label.displayName = "Label";

export { Label };
