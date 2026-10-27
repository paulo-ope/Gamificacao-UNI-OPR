"use client";

import { AlertCircle, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import type { SupportPlanItem, SupportPlanStatus } from "@/lib/types";

import { STATUS_LABEL } from "./planning-format";

// Pergunta o que falta quando um item é solto numa coluna que exige texto: concluir pede o resultado;
// bloquear e cancelar pedem o motivo. A regra de verdade é do backend; aqui só se coleta o texto.

export type PlanningMove = { item: SupportPlanItem; to: SupportPlanStatus };

/** Colunas em que soltar um cartão não muda o status sozinho: falta um texto. */
export function moveNeedsText(to: SupportPlanStatus): boolean {
  return to === "done" || to === "blocked" || to === "canceled";
}

type Props = {
  move: PlanningMove | null;
  onCancel: () => void;
  onConfirm: (move: PlanningMove, text: string, result: string) => Promise<string | null>;
};

export function PlanningMoveSheet({ move, onCancel, onConfirm }: Props) {
  const [text, setText] = useState("");
  const [result, setResult] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setText("");
    setResult("");
    setError(null);
  }, [move]);

  const finishing = move?.to === "done";
  const missing = finishing ? !result.trim() : !text.trim();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!move || missing) return;
    setSaving(true);
    setError(null);
    const failure = await onConfirm(move, text, result);
    setSaving(false);
    if (failure) setError(failure);
  }

  return (
    <Sheet open={move !== null} onOpenChange={(open) => (open ? undefined : onCancel())}>
      <SheetContent className="sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{move ? `Mover para ${STATUS_LABEL[move.to].toLowerCase()}` : "Mover"}</SheetTitle>
          <SheetDescription>{move?.item.title ?? ""}</SheetDescription>
        </SheetHeader>
        <form className="grid gap-4 p-6" onSubmit={submit}>
          {error ? (
            <div className="flex items-start gap-2 rounded-lg bg-rose-50 p-3 text-sm text-rose-800" role="alert">
              <AlertCircle size={16} className="mt-0.5 shrink-0" aria-hidden="true" /><p>{error}</p>
            </div>
          ) : null}
          {finishing ? (
            <>
              <label className="grid gap-1.5 text-sm font-medium text-slate-800">
                Resultado
                <Textarea value={result} maxLength={5000} onChange={(event) => setResult(event.target.value)} placeholder="O que foi feito e o que mudou" autoFocus />
              </label>
              <label className="grid gap-1.5 text-sm font-medium text-slate-800">
                Andamento (opcional)
                <Textarea value={text} maxLength={3000} onChange={(event) => setText(event.target.value)} className="min-h-[64px]" />
              </label>
            </>
          ) : (
            <label className="grid gap-1.5 text-sm font-medium text-slate-800">
              {move?.to === "blocked" ? "Motivo do bloqueio" : "Motivo do cancelamento"}
              <Textarea value={text} maxLength={3000} onChange={(event) => setText(event.target.value)} placeholder="Explique para a equipe" autoFocus />
            </label>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onCancel} disabled={saving}>Cancelar</Button>
            <Button type="submit" disabled={saving || missing}>
              {saving ? <Loader2 className="animate-spin" size={16} aria-hidden="true" /> : null}Mover
            </Button>
          </div>
        </form>
      </SheetContent>
    </Sheet>
  );
}
