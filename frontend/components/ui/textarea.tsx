"use client";

import * as React from "react";
import { useFieldControlId } from "@/components/ui/field";

import { cn } from "@/lib/utils";

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {}

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(({ className, id, ...props }, ref) => {
  const controlId = useFieldControlId(id);
  return (
    <textarea
      id={controlId}
      className={cn(
        "field-control flex min-h-[96px] w-full px-3 py-2 leading-relaxed",
        className
      )}
      ref={ref}
      {...props}
    />
  );
});
Textarea.displayName = "Textarea";

export { Textarea };
