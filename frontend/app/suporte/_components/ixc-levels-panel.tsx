"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";

import { IxcN1Panel } from "./ixc-n1-panel";

// "Suporte N1/N2": as antigas telas "Atendimento Suporte Interno N1" e "Atendimento Operacional N2"
// juntas num item só do menu. A escolha do nível é só da tela; a regra de cada nível continua no
// backend (`ixc_n1.py`) e o período já é compartilhado entre os dois (`useIxcPeriod`).

type Level = "n1" | "n2";

const LEVELS: { value: Level; label: string; hint: string }[] = [
  { value: "n1", label: "N1", hint: "Operacional e financeiro" },
  { value: "n2", label: "N2", hint: "Interno e externo" },
];

export function IxcLevelsPanel({ initialLevel = "n1" }: { initialLevel?: Level }) {
  const [level, setLevel] = useState<Level>(initialLevel);
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex overflow-hidden rounded-md border border-input" role="group" aria-label="Nível de atendimento">
          {LEVELS.map((option) => (
            <Button
              key={option.value}
              variant={level === option.value ? "default" : "ghost"}
              size="sm"
              className="rounded-none px-5"
              aria-pressed={level === option.value}
              onClick={() => setLevel(option.value)}
            >
              {option.label}
            </Button>
          ))}
        </div>
        <p className="text-sm text-slate-500">{LEVELS.find((option) => option.value === level)?.hint}</p>
      </div>
      <IxcN1Panel key={level} level={level} />
    </div>
  );
}
