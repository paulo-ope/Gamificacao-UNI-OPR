"use client";

import * as Popover from "@radix-ui/react-popover";
import { Check, ChevronDown } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Command,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { cn } from "@/lib/utils";

export function MultiSelect({
  values,
  options,
  placeholder = "Todos",
  ariaLabel,
  formatOption = (value) => value,
  onChange,
  className,
}: {
  values: string[];
  options: string[];
  placeholder?: string;
  ariaLabel: string;
  formatOption?: (value: string) => string;
  onChange: (values: string[]) => void;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const filteredOptions = useMemo(() => {
    const normalized = search.trim().toLocaleLowerCase("pt-BR");
    return normalized
      ? options.filter((option) =>
          formatOption(option).toLocaleLowerCase("pt-BR").includes(normalized),
        )
      : options;
  }, [formatOption, options, search]);
  const selectedFilteredCount = filteredOptions.filter((option) =>
    values.includes(option),
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
        ? formatOption(values[0])
        : values.length === 2
          ? values.map(formatOption).join(", ")
          : `${formatOption(values[0])}, ${formatOption(values[1])} +${values.length - 2}`;

  function toggle(value: string) {
    onChange(
      values.includes(value)
        ? values.filter((item) => item !== value)
        : [...values, value],
    );
  }

  function selectFiltered() {
    const next = new Set(values);
    filteredOptions.forEach((option) => next.add(option));
    onChange(Array.from(next));
  }

  function clearFiltered() {
    const filtered = new Set(filteredOptions);
    onChange(values.filter((value) => !filtered.has(value)));
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
                const selected = values.includes(option);
                return (
                  <CommandItem
                    key={option}
                    role="option"
                    aria-selected={selected}
                    onClick={() => toggle(option)}
                    title={formatOption(option)}
                    className="flex items-start justify-between gap-3 rounded-lg px-2.5 py-2 hover:bg-slate-50"
                  >
                    <span className="min-w-0 whitespace-normal break-words leading-snug">
                      {formatOption(option)}
                    </span>
                    <span
                      className={cn(
                        "flex h-4 w-4 shrink-0 items-center justify-center rounded border",
                        selected
                          ? "border-blue-600 bg-blue-600 text-white"
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
