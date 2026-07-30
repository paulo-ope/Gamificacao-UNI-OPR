"use client";

import * as Popover from "@radix-ui/react-popover";
import { CalendarRange, ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";

const WEEKDAYS = ["D", "S", "T", "Q", "Q", "S", "S"];

function parseLocalDate(value?: string | null) {
  if (!value) return null;
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return null;
  return new Date(Date.UTC(year, month - 1, day, 12));
}

function toDateValue(value: Date) {
  return value.toISOString().slice(0, 10);
}

function sameDate(left: Date, right: Date) {
  return toDateValue(left) === toDateValue(right);
}

function monthLabel(value: Date) {
  return new Intl.DateTimeFormat("pt-BR", { month: "long", year: "numeric", timeZone: "UTC" }).format(value);
}

function shortDateLabel(value?: string | null) {
  const date = parseLocalDate(value);
  if (!date) return "--/--/----";
  return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC" }).format(date);
}

function monthDays(viewMonth: Date) {
  const year = viewMonth.getUTCFullYear();
  const month = viewMonth.getUTCMonth();
  const first = new Date(Date.UTC(year, month, 1, 12));
  const firstWeekday = first.getUTCDay();
  const daysInMonth = new Date(Date.UTC(year, month + 1, 0, 12)).getUTCDate();
  const cells: Array<Date | null> = Array.from({ length: firstWeekday }, () => null);
  for (let day = 1; day <= daysInMonth; day += 1) cells.push(new Date(Date.UTC(year, month, day, 12)));
  return cells;
}

function addMonths(value: Date, amount: number) {
  return new Date(Date.UTC(value.getUTCFullYear(), value.getUTCMonth() + amount, 1, 12));
}

export type DateRangePreset = { label: string; range: () => { from: string; to: string } };

/**
 * Seletor de período padrão do ecossistema - popover com calendário duplo e presets. Extraído de
 * `operations-filter-panel.tsx` para ser compartilhado entre módulos (achado real, 2026-07-29: o
 * módulo de Agendamento tinha dois `<input type="date">` soltos, um padrão visual diferente do
 * resto do ecossistema).
 */
export function DateRangePicker({
  label = "Período",
  dateFrom,
  dateTo,
  min,
  max,
  presets,
  onChange,
}: {
  label?: string;
  dateFrom: string;
  dateTo: string;
  min?: string;
  max?: string;
  presets?: DateRangePreset[];
  onChange: (key: "date_from" | "date_to", value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [selecting, setSelecting] = useState<"from" | "to">("from");
  const initialView = parseLocalDate(dateFrom) || parseLocalDate(max) || new Date();
  const [viewMonth, setViewMonth] = useState(() => new Date(Date.UTC(initialView.getUTCFullYear(), initialView.getUTCMonth(), 1, 12)));
  const from = parseLocalDate(dateFrom);
  const to = parseLocalDate(dateTo);
  const minDate = parseLocalDate(min);
  const maxDate = parseLocalDate(max);

  function isDisabled(day: Date) {
    return Boolean((minDate && day < minDate) || (maxDate && day > maxDate));
  }

  function pick(day: Date) {
    if (isDisabled(day)) return;
    const value = toDateValue(day);
    if (selecting === "from") {
      onChange("date_from", value);
      if (to && day > to) onChange("date_to", value);
      setSelecting("to");
      return;
    }
    onChange("date_to", value);
    if (from && day < from) onChange("date_from", value);
    setOpen(false);
    setSelecting("from");
  }

  function applyPreset(preset: DateRangePreset) {
    const range = preset.range();
    onChange("date_from", range.from);
    onChange("date_to", range.to);
    const start = parseLocalDate(range.from);
    if (start) setViewMonth(new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), 1, 12)));
    setSelecting("from");
    setOpen(false);
  }

  function renderMonth(month: Date) {
    return (
      <div className="min-w-0">
        <p className="mb-2 text-center text-xs font-semibold capitalize text-slate-800">{monthLabel(month)}</p>
        <div className="grid grid-cols-7 gap-1 text-center text-[10px] font-semibold text-slate-400">
          {WEEKDAYS.map((day, index) => (
            <span key={`${day}-${index}`}>{day}</span>
          ))}
        </div>
        <div className="mt-1 grid grid-cols-7 gap-1">
          {monthDays(month).map((day, index) => {
            if (!day) return <span key={`empty-${index}`} />;
            const selected = (from && sameDate(day, from)) || (to && sameDate(day, to));
            const inRange = Boolean(from && to && day > from && day < to);
            const disabled = isDisabled(day);
            return (
              <button
                key={toDateValue(day)}
                type="button"
                disabled={disabled}
                onClick={() => pick(day)}
                className={[
                  "h-9 rounded-lg text-xs font-medium transition",
                  selected ? "bg-blue-600 text-white shadow-sm" : inRange ? "bg-blue-50 text-blue-800" : "text-slate-700 hover:bg-slate-100",
                  disabled ? "cursor-not-allowed opacity-30 hover:bg-transparent" : "",
                ].join(" ")}
              >
                {day.getUTCDate()}
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <label className="grid min-w-0 gap-1.5 text-[11px] font-medium text-slate-600">
      {label}
      <Popover.Root open={open} onOpenChange={setOpen}>
        <Popover.Trigger asChild>
          <button
            type="button"
            className="flex h-10 min-w-0 items-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-left text-sm text-slate-800 outline-none focus:ring-2 focus:ring-blue-500"
          >
            <CalendarRange className="h-3.5 w-3.5 shrink-0 text-slate-400" />
            <span className="min-w-0 whitespace-nowrap text-[13px]">
              {shortDateLabel(dateFrom)} <span className="text-slate-400">até</span> {shortDateLabel(dateTo)}
            </span>
          </button>
        </Popover.Trigger>
        <Popover.Portal>
          <Popover.Content align="start" sideOffset={8} className="z-[70] w-[min(46rem,calc(100vw-2rem))] rounded-xl border border-slate-200 bg-white p-3 shadow-xl">
            <div className="mb-3 grid grid-cols-2 gap-2 rounded-lg bg-slate-50 p-1">
              <button
                type="button"
                onClick={() => setSelecting("from")}
                className={["rounded-md px-3 py-2 text-left text-xs font-semibold transition", selecting === "from" ? "bg-white text-blue-700 shadow-sm" : "text-slate-500 hover:text-slate-800"].join(" ")}
              >
                Início
                <span className="block text-[11px] font-medium text-slate-500">{shortDateLabel(dateFrom)}</span>
              </button>
              <button
                type="button"
                onClick={() => setSelecting("to")}
                className={["rounded-md px-3 py-2 text-left text-xs font-semibold transition", selecting === "to" ? "bg-white text-blue-700 shadow-sm" : "text-slate-500 hover:text-slate-800"].join(" ")}
              >
                Fim
                <span className="block text-[11px] font-medium text-slate-500">{shortDateLabel(dateTo)}</span>
              </button>
            </div>
            <div className="mb-3 flex items-center justify-between gap-2">
              <Button type="button" variant="ghost" size="icon" className="h-8 w-8" aria-label="Mês anterior" onClick={() => setViewMonth((current) => addMonths(current, -1))}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <div className="flex flex-wrap justify-center gap-2">
                {(presets || []).map((preset) => (
                  <Button key={preset.label} type="button" variant="outline" size="sm" className="h-8 text-xs" onClick={() => applyPreset(preset)}>
                    {preset.label}
                  </Button>
                ))}
              </div>
              <Button type="button" variant="ghost" size="icon" className="h-8 w-8" aria-label="Próximo mês" onClick={() => setViewMonth((current) => addMonths(current, 1))}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {renderMonth(viewMonth)}
              {renderMonth(addMonths(viewMonth, 1))}
            </div>
            <div className="mt-3 flex items-center justify-between gap-2 border-t border-slate-100 pt-3 text-[11px] text-slate-500">
              <span>{selecting === "from" ? "Escolha a data inicial" : "Escolha a data final"}</span>
              <Button type="button" size="sm" className="h-8 text-xs" onClick={() => setOpen(false)}>
                Concluir
              </Button>
            </div>
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>
    </label>
  );
}
