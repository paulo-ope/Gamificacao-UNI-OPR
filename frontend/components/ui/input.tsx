"use client";

import * as React from "react";
import { useFieldControlId } from "@/components/ui/field";

import { cn } from "@/lib/utils";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(({ className, type, id, ...props }, ref) => {
  const controlId = useFieldControlId(id);
  return (
    <input
      type={type}
      id={controlId}
      className={cn(
        "field-control flex h-10 w-full min-w-0 px-3 py-2 file:mr-3 file:rounded-md file:border-0 file:bg-secondary file:px-3 file:py-1 file:text-xs file:font-semibold file:text-secondary-foreground",
        className
      )}
      ref={ref}
      {...props}
    />
  );
});
Input.displayName = "Input";

export { Input };
