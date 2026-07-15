"use client";

import { useCallback, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

type ConfirmOptions = {
  title?: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: "default" | "danger";
};

export function useConfirm() {
  const [options, setOptions] = useState<ConfirmOptions | null>(null);
  const resolverRef = useRef<((value: boolean) => void) | null>(null);

  const confirm = useCallback((opts: ConfirmOptions) => {
    setOptions(opts);
    return new Promise<boolean>((resolve) => {
      resolverRef.current = resolve;
    });
  }, []);

  function settle(result: boolean) {
    resolverRef.current?.(result);
    resolverRef.current = null;
    setOptions(null);
  }

  const ConfirmDialog = (
    <Dialog open={options !== null} onOpenChange={(open) => !open && settle(false)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{options?.title ?? "Confirmar ação"}</DialogTitle>
          <DialogDescription className="whitespace-pre-line">{options?.description}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => settle(false)}>
            {options?.cancelLabel ?? "Cancelar"}
          </Button>
          <Button type="button" variant={options?.tone === "danger" ? "destructive" : "default"} onClick={() => settle(true)}>
            {options?.confirmLabel ?? "Confirmar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  return { confirm, ConfirmDialog };
}
