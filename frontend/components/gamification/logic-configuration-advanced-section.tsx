"use client";

import type { RefObject } from "react";
import { FileDown, FileUp, RotateCcw, Save } from "lucide-react";

import { Button } from "@/components/ui/button";

type Props = {
  saveSnapshot: () => Promise<void>;
  exportConfig: () => Promise<void>;
  busy: boolean;
  fileRef: RefObject<HTMLInputElement | null>;
  resetDefault: () => Promise<void>;
};

export function AdvancedSection({ saveSnapshot, exportConfig, busy, fileRef, resetDefault }: Props) {
  return (
    <section className="grid gap-4">
      <section className="rounded-[24px] border border-slate-200 bg-white shadow-[0_10px_40px_rgba(15,23,42,0.05)]">
        <div className="panel-header">
          <div>
            <h3 className="panel-title">Avançado</h3>
            <p className="panel-subtitle">
              Ferramentas técnicas para snapshot, importação, exportação e restauração. A matriz operacional fica nas seções Grupos, Assuntos e Diagnósticos.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 border-t p-5">
          <Button onClick={saveSnapshot} disabled={busy}>
            <Save className="h-4 w-4" />
            Salvar snapshot
          </Button>
          <Button variant="outline" onClick={exportConfig} disabled={busy}>
            <FileDown className="h-4 w-4" />
            Exportar JSON
          </Button>
          <Button variant="outline" onClick={() => fileRef.current?.click()} disabled={busy}>
            <FileUp className="h-4 w-4" />
            Importar JSON
          </Button>
          <Button variant="destructive" onClick={resetDefault} disabled={busy}>
            <RotateCcw className="h-4 w-4" />
            Restaurar padrão
          </Button>
        </div>
      </section>
    </section>
  );
}
