"use client";

import * as Popover from "@radix-ui/react-popover";
import { Check, ChevronDown } from "lucide-react";
import type { ReactNode } from "react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Command,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { cn } from "@/lib/utils";

// Genérico em `T` (default `string`) - achado real de 2026-08-24: a tela de Agendamento
// reimplementava este componente do zero só porque precisava de opções como objeto
// ({id, name, is_team_member}), não string solta. `getValue` extrai a chave (string) usada pra
// seleção/comparação, `formatOption` extrai o texto exibido - quem só usa string[] (todo o resto
// do sistema) não precisa passar nenhum dos dois, o default é a própria string.
export function MultiSelect<T = string>({
  values,
  options,
  placeholder = "Todos",
  ariaLabel,
  formatOption = (option: T) => String(option),
  getValue = (option: T) => String(option),
  renderMeta,
  onChange,
  className,
}: {
  values: string[];
  options: T[];
  placeholder?: string;
  ariaLabel: string;
  formatOption?: (option: T) => string;
  getValue?: (option: T) => string;
  // Conteúdo extra por linha (ex.: badge "Equipe") - renderizado depois do texto, antes do check.
  renderMeta?: (option: T) => ReactNode;
  onChange: (values: string[]) => void;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");

  const optionsByValue = useMemo(() => {
    const map = new Map<string, T>();
    options.forEach((option) => map.set(getValue(option), option));
    return map;
  }, [options, getValue]);

  const labelForValue = (value: string) => {
    const option = optionsByValue.get(value);
    return option !== undefined ? formatOption(option) : value;
  };

  const filteredOptions = useMemo(() => {
    const normalized = search.trim().toLocaleLowerCase("pt-BR");
    return normalized
      ? options.filter((option) =>
          formatOption(option).toLocaleLowerCase("pt-BR").includes(normalized),
        )
      : options;
  }, [formatOption, options, search]);
  const selectedFilteredCount = filteredOptions.filter((option) =>
    values.includes(getValue(option)),
  ).length;
  const allFilteredSelected =
    filteredOptions.length > 0 &&
    selectedFilteredCount === filteredOptions.length;
  const allOptionsSelected =
    options.length > 0 && values.length === options.length;

  const summary =
    values.length === 0
      ? placeholder
      : allOptionsSelected
        ? `Todos (${options.length})`
        : values.length === 1
        ? labelForValue(values[0])
        : values.length === 2
          ? values.map(labelForValue).join(", ")
          : `${labelForValue(values[0])}, ${labelForValue(values[1])} +${values.length - 2}`;

  function toggle(option: T) {
    const value = getValue(option);
    onChange(
      values.includes(value)
        ? values.filter((item) => item !== value)
        : [...values, value],
    );
  }

  function selectFiltered() {
    const next = new Set(values);
    filteredOptions.forEach((option) => next.add(getValue(option)));
    onChange(Array.from(next));
  }

  function clearFiltered() {
    const filteredValues = new Set(filteredOptions.map(getValue));
    onChange(values.filter((value) => !filteredValues.has(value)));
  }

  return (
    <Popover.Root
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setSearch("");
      }}
    >
      <Popover.Trigger asChild>
        <button
          type="button"
          aria-label={ariaLabel}
          className={cn(
            "flex h-10 w-full min-w-0 items-center justify-between gap-2 rounded-md border border-slate-200 bg-white px-3 text-left text-sm font-normal normal-case tracking-normal text-slate-800 outline-none focus:ring-2 focus:ring-blue-500",
            className,
          )}
        >
          <span
            className={cn("truncate", values.length === 0 && "text-slate-500")}
          >
            {summary}
          </span>
          <ChevronDown className="h-4 w-4 shrink-0 text-slate-500" />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="start"
          sideOffset={6}
          collisionPadding={12}
          className="z-50 flex max-h-[min(28rem,var(--radix-popover-content-available-height))] w-[min(32rem,calc(100vw-2rem))] min-w-[var(--radix-popover-trigger-width)] flex-col overflow-hidden rounded-xl border border-slate-200 bg-white p-2 shadow-xl"
        >
          <Command className="flex min-h-0 flex-1 flex-col border-0 shadow-none">
            <CommandInput
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Pesquisar..."
              className="h-9 shrink-0"
            />
            {filteredOptions.length ? (
              <div className="mt-2 flex items-center justify-between gap-2 rounded-lg bg-slate-50 px-2 py-1.5">
                <span className="text-[11px] text-slate-500">
                  {selectedFilteredCount} de {filteredOptions.length} nesta lista
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2 text-[11px]"
                  onClick={allFilteredSelected ? clearFiltered : selectFiltered}
                >
                  {allFilteredSelected ? "Desmarcar lista" : "Selecionar todos"}
                </Button>
              </div>
            ) : null}
            <CommandList className="mt-2 min-h-0 flex-1 space-y-1 overflow-y-auto">
              {filteredOptions.map((option) => {
                const value = getValue(option);
                const selected = values.includes(value);
                return (
                  <CommandItem
                    key={value}
                    role="option"
                    aria-selected={selected}
                    onClick={() => toggle(option)}
                    title={formatOption(option)}
                    className="flex items-start justify-between gap-3 rounded-lg px-2.5 py-2 hover:bg-slate-50"
                  >
                    <span className="min-w-0 flex-1 whitespace-normal break-words leading-snug">
                      {formatOption(option)}
                      {renderMeta ? <span className="ml-1.5 inline-flex align-middle">{renderMeta(option)}</span> : null}
                    </span>
                    <span
                      className={cn(
                        "flex h-4 w-4 shrink-0 items-center justify-center rounded border",
                        selected
                          ? "border-uni-royal bg-uni-royal text-white"
                          : "border-slate-300 text-transparent",
                      )}
                    >
                      <Check className="h-3 w-3" />
                    </span>
                  </CommandItem>
                );
              })}
              {filteredOptions.length === 0 ? (
                <p className="px-3 py-6 text-center text-sm text-slate-500">
                  Nenhuma opção encontrada.
                </p>
              ) : null}
            </CommandList>
            {values.length ? (
              <div className="mt-2 flex items-center justify-between border-t border-slate-100 pt-2">
                <span className="text-xs text-slate-500">
                  {allOptionsSelected
                    ? `Todos os ${options.length} selecionados`
                    : `${values.length} selecionado(s)`}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => onChange([])}
                >
                  Limpar
                </Button>
              </div>
            ) : null}
          </Command>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
