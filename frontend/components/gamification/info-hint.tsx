"use client";

import * as Popover from "@radix-ui/react-popover";
import { Info } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

type InfoHintProps = {
  ariaLabel: string;
  description: string;
  side?: "top" | "right" | "bottom" | "left";
  title?: string;
};

export function InfoHint({ ariaLabel, description, side = "top", title }: InfoHintProps) {
  const [open, setOpen] = useState(false);
  const hintId = useId();
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const clearTimer = () => { if (timer.current) clearTimeout(timer.current); };
  const show = () => { clearTimer(); setOpen(true); };
  const hide = () => { clearTimer(); timer.current = setTimeout(() => setOpen(false), 150); };
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Anchor asChild>
        <button type="button" aria-label={ariaLabel} aria-describedby={open ? hintId : undefined} aria-expanded={open}
          onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide} onClick={show}
          onKeyDown={(event) => { if (event.key === "Escape") { event.stopPropagation(); clearTimer(); setOpen(false); } }}
          className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-slate-500 transition-colors hover:bg-blue-50 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
          <Info className="h-4 w-4" aria-hidden="true" />
        </button>
      </Popover.Anchor>
      <Popover.Portal>
        <Popover.Content id={hintId} role="tooltip" side={side} sideOffset={8} collisionPadding={12}
          onOpenAutoFocus={(event) => event.preventDefault()} onCloseAutoFocus={(event) => event.preventDefault()}
          onMouseEnter={show} onMouseLeave={hide}
          className="z-[100] max-h-[var(--radix-popover-content-available-height)] w-[min(20rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border border-slate-200 bg-white p-4 shadow-floating data-[state=open]:animate-in data-[state=open]:fade-in-0">
          {title ? <span className="mb-1.5 block text-xs font-semibold text-slate-900">{title}</span> : null}
          <span className="block text-sm leading-6 text-slate-600">{description}</span>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
