"use client";

import { Menu, type LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetClose, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

export type ModuleNavigationItem<TValue extends string> = {
  value: TValue;
  label: string;
  description: string;
  icon: LucideIcon;
};

export function ModuleNavigationSidebar<TValue extends string>({
  title,
  description,
  items,
  activeItem,
  footer,
  onChange,
}: {
  title: string;
  description: string;
  items: Array<ModuleNavigationItem<TValue>>;
  activeItem: TValue;
  footer?: string;
  onChange: (item: TValue) => void;
}) {
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button type="button" size="icon" variant="outline" aria-label={`Abrir menu de ${title}`}>
          <Menu className="h-5 w-5" />
        </Button>
      </SheetTrigger>
      <SheetContent className="left-0 right-auto w-[88vw] border-l-0 border-r bg-white p-0 text-slate-950 sm:max-w-sm">
        <SheetHeader className="border-slate-100">
          <SheetTitle className="text-slate-950">{title}</SheetTitle>
          <SheetDescription className="text-slate-500">{description}</SheetDescription>
        </SheetHeader>
        <nav className="flex-1 space-y-1 p-3" aria-label={`Navegação de ${title}`}>
          {items.map((item) => {
            const Icon = item.icon;
            const selected = activeItem === item.value;

            return (
              <SheetClose asChild key={item.value}>
                <button
                  type="button"
                  onClick={() => onChange(item.value)}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left transition-colors",
                    selected ? "bg-uni-royal/10 text-uni-royal" : "text-slate-600 hover:bg-slate-50 hover:text-slate-950",
                  )}
                >
                  <span
                    className={cn(
                      "flex h-9 w-9 items-center justify-center rounded-lg",
                      selected ? "bg-uni-royal text-white" : "bg-slate-100 text-slate-500",
                    )}
                  >
                    <Icon className="h-4 w-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-semibold">{item.label}</span>
                    <span className={cn("block text-[11px]", selected ? "text-uni-royal/70" : "text-slate-400")}>
                      {item.description}
                    </span>
                  </span>
                </button>
              </SheetClose>
            );
          })}
        </nav>
        {footer ? <div className="border-t border-slate-100 p-4 text-[11px] text-slate-400">{footer}</div> : null}
      </SheetContent>
    </Sheet>
  );
}
