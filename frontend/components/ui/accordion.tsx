"use client";

import * as React from "react";

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

const Accordion = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("grid gap-2", className)} {...props} />
);

const AccordionItem = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & { value: string; defaultOpen?: boolean }
>(({ className, defaultOpen, value, ...props }, ref) => (
  <Collapsible ref={ref} defaultOpen={defaultOpen} className={cn("rounded-md border bg-white", className)} {...props} />
));
AccordionItem.displayName = "AccordionItem";

const AccordionTrigger = CollapsibleTrigger;
const AccordionContent = CollapsibleContent;

export { Accordion, AccordionContent, AccordionItem, AccordionTrigger };
