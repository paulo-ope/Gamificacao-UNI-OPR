"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { AppCheckbox } from "@/components/ui/checkbox";
import { MultiSelect as SharedMultiSelect } from "@/components/ui/multi-select";

// Wrapper fino sobre o `MultiSelect` compartilhado (`@/components/ui/multi-select`) - achado real
// de 2026-08-24: esta tela reimplementava o próprio multi-select do zero (popover manual,
// `<input type="checkbox">` cru) só porque as opções são objetos `{id, name, is_team_member}`, não
// strings soltas como o resto do sistema usa. O componente compartilhado agora aceita isso via
// `getValue`/`formatOption` genéricos - aqui só resta o rótulo e o toggle "só equipe" (usado só
// pelo filtro de Operador), que não fazem parte do componente genérico de propósito.
export function SchedulingMultiSelect({
  label,
  options,
  selected,
  onChange,
  showTeamFilter,
}: {
  label: string;
  options: Array<{ id: string | number; name: string; is_team_member?: boolean | null }>;
  selected: Array<string | number>;
  onChange: (next: Array<string | number>) => void;
  showTeamFilter?: boolean;
}) {
  const [teamOnly, setTeamOnly] = useState(false);
  const visibleOptions = showTeamFilter && teamOnly ? options.filter((option) => option.is_team_member) : options;
  const values = selected.map(String);
  const isNumeric = options.some((option) => typeof option.id === "number");

  return (
    <label className="grid min-w-0 gap-1.5 text-[11px] font-medium text-slate-500">
      <span className="flex items-center justify-between gap-2">
        {label}
        {showTeamFilter ? (
          <span className="flex cursor-pointer items-center gap-1.5 text-[10px] font-normal normal-case text-slate-500">
            <AppCheckbox
              checked={teamOnly}
              onCheckedChange={setTeamOnly}
              ariaLabel="Mostrar só equipe de agendamento"
              className="h-3.5 w-3.5"
            />
            Só equipe
          </span>
        ) : null}
      </span>
      <SharedMultiSelect
        ariaLabel={`Filtrar por ${label}`}
        values={values}
        options={visibleOptions}
        getValue={(option) => String(option.id)}
        formatOption={(option) => option.name}
        renderMeta={(option) =>
          option.is_team_member ? (
            <Badge className="border-blue-200 bg-blue-50 text-[10px] text-blue-700">Equipe</Badge>
          ) : null
        }
        onChange={(next) => onChange(isNumeric ? next.map(Number) : next)}
      />
    </label>
  );
}
