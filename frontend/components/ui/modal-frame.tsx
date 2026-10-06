"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useRef, type HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

/** Accessible frame for existing domain dialogs: preserves content and save/cancel handlers. */
export function ModalFrame({ title, onClose, className, children, ...props }: HTMLAttributes<HTMLDivElement> & { title: string; onClose: () => void }) {
  const returnFocus = useRef<HTMLElement | null>(null);
  return (
    <DialogPrimitive.Root open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-slate-950/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=open]:fade-in-0" />
        <DialogPrimitive.Content
          {...props}
          aria-describedby={undefined}
          onOpenAutoFocus={() => { returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null; }}
          onCloseAutoFocus={(event) => { event.preventDefault(); if (returnFocus.current?.isConnected) returnFocus.current.focus(); }}
          onPointerDownOutside={(event) => event.preventDefault()}
          className={cn("fixed inset-0 z-[70] flex items-end justify-end outline-none data-[state=open]:animate-in data-[state=open]:fade-in-0", className)}
        >
          <DialogPrimitive.Title className="sr-only">{title}</DialogPrimitive.Title>
          {children}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
