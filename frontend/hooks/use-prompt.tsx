"use client";

import { useCallback, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

type PromptOptions = {
  title?: string;
  description?: string;
  label?: string;
  placeholder?: string;
  confirmLabel?: string;
  cancelLabel?: string;
};

/** Substitui `window.prompt()` (bloqueado/instável em ambientes embutidos - achado real, 2026-08-29:
 *  `window.prompt` chegou a lançar exceção não tratada num navegador em iframe, deixando a ação
 *  travada em silêncio) por um diálogo controlado no mesmo padrão de `useConfirm`
 *  (hooks/use-confirm.tsx) - mesmos componentes de `components/ui/dialog`, só que devolve o texto
 *  digitado em vez de um booleano. */
export function usePrompt() {
  const [options, setOptions] = useState<PromptOptions | null>(null);
  const [value, setValue] = useState("");
  const resolverRef = useRef<((value: string | null) => void) | null>(null);

  const promptText = useCallback((opts: PromptOptions) => {
    setOptions(opts);
    setValue("");
    return new Promise<string | null>((resolve) => {
      resolverRef.current = resolve;
    });
  }, []);

  function settle(result: string | null) {
    resolverRef.current?.(result);
    resolverRef.current = null;
    setOptions(null);
  }

  const PromptDialog = (
    <Dialog open={options !== null} onOpenChange={(open) => !open && settle(null)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{options?.title ?? "Informe um motivo"}</DialogTitle>
          {options?.description ? <DialogDescription>{options.description}</DialogDescription> : null}
        </DialogHeader>
        <div className="grid gap-1.5">
          {options?.label ? <Label htmlFor="prompt-dialog-textarea">{options.label}</Label> : null}
          <Textarea
            id="prompt-dialog-textarea"
            autoFocus
            placeholder={options?.placeholder}
            value={value}
            onChange={(event) => setValue(event.target.value)}
          />
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => settle(null)}>
            {options?.cancelLabel ?? "Cancelar"}
          </Button>
          <Button type="button" disabled={!value.trim()} onClick={() => settle(value.trim())}>
            {options?.confirmLabel ?? "Confirmar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  return { promptText, PromptDialog };
}
