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
    <div ref={ref} className={cn("cursor-default px-3 py-2 text-sm hover:bg-muted", className)} {...props} />
  )
);
CommandItem.displayName = "CommandItem";

export { Command, CommandInput, CommandItem, CommandList };
