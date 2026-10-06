"use client";

import * as React from "react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const Command = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => <div ref={ref} className={cn("rounded-md border bg-white", className)} {...props} />
);
Command.displayName = "Command";

const CommandInput = React.forwardRef<HTMLInputElement, React.ComponentProps<typeof Input>>((props, ref) => (
  <Input ref={ref} {...props} />
));
CommandInput.displayName = "CommandInput";

const CommandList = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => <div ref={ref} className={cn("max-h-72 overflow-auto", className)} {...props} />
);
CommandList.displayName = "CommandList";

const CommandItem = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} role={props.onClick ? "button" : undefined} tabIndex={props.onClick ? 0 : undefined}
      onKeyDown={(event) => {
        if (props.onClick && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault();
          event.currentTarget.click();
        }
      }}
      className={cn("cursor-default rounded-lg px-3 py-2 text-sm hover:bg-muted focus-visible:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary", className)} {...props} />
  )
);
CommandItem.displayName = "CommandItem";

export { Command, CommandInput, CommandItem, CommandList };
