"use client";

import * as Popover from "@radix-ui/react-popover";
import { CalendarRange, ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";

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

function addDays(value: Date, amount: number) {
  return new Date(Date.UTC(value.getUTCFullYear(), value.getUTCMonth(), value.getUTCDate() + amount, 12));
}

function monthStart(value: Date) {
  return new Date(Date.UTC(value.getUTCFullYear(), value.getUTCMonth(), 1, 12));
}

function monthEnd(value: Date) {
  return new Date(Date.UTC(value.getUTCFullYear(), value.getUTCMonth() + 1, 0, 12));
}

function browserLocalToday() {
  const now = new Date();
  return new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate(), 12));
}

// Aceita dd/mm/aaaa (formato que o brasileiro digita) - valida que os componentes batem
// com o que o Date normalizou, pra rejeitar coisas como 31/02/2026 em vez de silenciosamente
// virar 03/03/2026.
function parseTypedDate(text: string): Date | null {
  const match = text.trim().match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (!match) return null;
  const day = Number(match[1]);
  const month = Number(match[2]);
  const year = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day, 12));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return null;
  return date;
}

export type DateRangePreset = { label: string; range: () => { from: string; to: string } };

/**
 * Conjunto padrão de presets do ecossistema - use como base em qualquer tela que precise
 * filtrar por período, em vez de reescrever "Últimos 7 dias" etc. do zero a cada módulo
 * (achado real, 2026-08-27: Suporte, Operação e Agendamento tinham cada um sua própria lista
 * de presets, inconsistente entre si, e a de Suporte tinha um preset "Personalizado" que não
 * fazia nada além de reaplicar "Este mês").
 *
 * `getToday` é injetável porque "hoje" às vezes precisa ser calculado num fuso horário
 * operacional específico (ex.: Suporte usa America/Porto_Velho), não no fuso do navegador
 * de quem está olhando a tela.
 */
export function commonDateRangePresets(getToday: () => Date = browserLocalToday): DateRangePreset[] {
  return [
    {
      label: "Hoje",
      range: () => {
        const today = getToday();
        return { from: toDateValue(today), to: toDateValue(today) };
      },
    },
    {
      label: "Ontem",
      range: () => {
        const yesterday = addDays(getToday(), -1);
        return { from: toDateValue(yesterday), to: toDateValue(yesterday) };
      },
    },
    {
      label: "Esta semana",
      range: () => {
        const today = getToday();
        return { from: toDateValue(addDays(today, -today.getUTCDay())), to: toDateValue(today) };
      },
    },
    {
      label: "Últimos 7 dias",
      range: () => {
        const today = getToday();
        return { from: toDateValue(addDays(today, -6)), to: toDateValue(today) };
      },
    },
    {
      label: "Últimos 30 dias",
      range: () => {
        const today = getToday();
        return { from: toDateValue(addDays(today, -29)), to: toDateValue(today) };
      },
    },
    {
      label: "Este mês",
      range: () => {
        const today = getToday();
        return { from: toDateValue(monthStart(today)), to: toDateValue(today) };
      },
    },
    {
      label: "Mês anterior",
      range: () => {
        const previous = addMonths(getToday(), -1);
        return { from: toDateValue(monthStart(previous)), to: toDateValue(monthEnd(previous)) };
      },
    },
    {
      label: "Últimos 3 meses",
      range: () => {
        const today = getToday();
        return { from: toDateValue(monthStart(addMonths(today, -2))), to: toDateValue(today) };
      },
    },
    {
      label: "Este ano",
      range: () => {
        const today = getToday();
        return { from: toDateValue(new Date(Date.UTC(today.getUTCFullYear(), 0, 1, 12))), to: toDateValue(today) };
      },
    },
  ];
}

// Data no cabeçalho do popover, editável por digitação (dd/mm/aaaa) além de clicável pra
// alternar qual ponta do intervalo o calendário abaixo está preenchendo - antes só dava
// pra mudar clicando dia a dia no calendário, o que é lento pra datas muitos meses atrás.
function EditableDateField({
  fieldLabel,
  active,
  value,
  onFocus,
  onCommit,
}: {
  fieldLabel: string;
  active: boolean;
  value?: string | null;
  onFocus: () => void;
  onCommit: (text: string) => boolean;
}) {
  const [text, setText] = useState(shortDateLabel(value));
  const [invalid, setInvalid] = useState(false);

  useEffect(() => {
    setText(shortDateLabel(value));
    setInvalid(false);
  }, [value]);

  function commit() {
    if (text.trim() === "" || text === shortDateLabel(value)) {
      setInvalid(false);
      return;
    }
    const ok = onCommit(text);
    setInvalid(!ok);
  }

  return (
    <div className={["rounded-md px-3 py-2 text-left transition", active ? "bg-white shadow-sm" : ""].join(" ")}>
      <button
        type="button"
        onClick={onFocus}
        className={["text-xs font-semibold", active ? "text-blue-700" : "text-slate-500 hover:text-slate-800"].join(" ")}
      >
        {fieldLabel}
      </button>
      <input
        type="text"
        inputMode="numeric"
        placeholder="dd/mm/aaaa"
        value={text}
        onFocus={onFocus}
        onChange={(event) => setText(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            commit();
            event.currentTarget.blur();
          }
        }}
        className={[
          "mt-0.5 block w-full border-0 border-b bg-transparent p-0 text-[11px] font-medium outline-none",
          invalid ? "border-red-400 text-red-600" : "border-transparent text-slate-500 focus:border-blue-400",
        ].join(" ")}
      />
      {invalid ? <span className="mt-0.5 block text-[10px] font-medium text-red-500">Data inválida</span> : null}
    </div>
  );
}

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
  className,
  onChange,
}: {
  label?: string;
  dateFrom: string;
  dateTo: string;
  min?: string;
  max?: string;
  presets?: DateRangePreset[];
  className?: string;
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
    if (selecting === "from" || !from) {
      onChange("date_from", value);
      if (to && day > to) onChange("date_to", value);
      setSelecting("to");
      return;
    }
    // Selecionando "fim": se a data escolhida vier antes do início já marcado, o intervalo
    // é invertido (a nova data vira o início, e o início antigo vira o fim) em vez de
    // colapsar as duas pontas no mesmo dia - clicar 15 e depois 5 devia dar 5→15, não 5→5.
    if (day < from) {
      onChange("date_from", value);
      onChange("date_to", toDateValue(from));
    } else {
      onChange("date_to", value);
    }
    setOpen(false);
    setSelecting("from");
  }

  function commitTyped(field: "from" | "to", text: string): boolean {
    const parsed = parseTypedDate(text);
    if (!parsed || isDisabled(parsed)) return false;
    if (field === "from") {
      onChange("date_from", toDateValue(parsed));
      if (to && parsed > to) onChange("date_to", toDateValue(parsed));
      setSelecting("to");
    } else {
      onChange("date_to", toDateValue(parsed));
      if (from && parsed < from) onChange("date_from", toDateValue(parsed));
      setSelecting("from");
    }
    setViewMonth(new Date(Date.UTC(parsed.getUTCFullYear(), parsed.getUTCMonth(), 1, 12)));
    return true;
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
        <p className="mb-1.5 text-center text-[11px] font-semibold capitalize text-slate-800">{monthLabel(month)}</p>
        <div className="grid grid-cols-7 gap-0.5 text-center text-[9px] font-semibold text-slate-400">
          {WEEKDAYS.map((day, index) => (
            <span key={`${day}-${index}`}>{day}</span>
          ))}
        </div>
        <div className="mt-1 grid grid-cols-7 gap-0.5">
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
                  "h-7 rounded-md text-[11px] font-medium transition",
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
    <label className={`grid min-w-0 gap-1.5 text-[11px] font-medium text-slate-600 ${className || ""}`}>
      {label}
      <Popover.Root open={open} onOpenChange={setOpen}>
        <Popover.Trigger asChild>
          <button
            type="button"
            className="flex h-10 w-full min-w-0 items-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-left text-sm text-slate-800 outline-none focus:ring-2 focus:ring-blue-500"
          >
            <CalendarRange className="h-3.5 w-3.5 shrink-0 text-slate-400" />
            <span className="min-w-0 truncate text-[13px]">
              {shortDateLabel(dateFrom)} <span className="text-slate-400">até</span> {shortDateLabel(dateTo)}
            </span>
          </button>
        </Popover.Trigger>
        <Popover.Portal>
          <Popover.Content align="start" sideOffset={8} className="z-[70] w-[min(32rem,calc(100vw-2rem))] rounded-xl border border-slate-200 bg-white p-2.5 shadow-xl">
            <div className="mb-2 grid grid-cols-2 gap-2 rounded-lg bg-slate-50 p-1">
              <EditableDateField
                fieldLabel="Início"
                active={selecting === "from"}
                value={dateFrom}
                onFocus={() => setSelecting("from")}
                onCommit={(text) => commitTyped("from", text)}
              />
              <EditableDateField
                fieldLabel="Fim"
                active={selecting === "to"}
                value={dateTo}
                onFocus={() => setSelecting("to")}
                onCommit={(text) => commitTyped("to", text)}
              />
            </div>
            <div className="mb-2 flex items-center gap-1">
              <Button type="button" variant="ghost" size="icon" className="h-7 w-7 shrink-0" aria-label="Mês anterior" onClick={() => setViewMonth((current) => addMonths(current, -1))}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <div className="flex min-w-0 flex-1 flex-nowrap gap-1 overflow-x-auto">
                {(presets || []).map((preset) => (
                  <Button
                    key={preset.label}
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-7 shrink-0 whitespace-nowrap px-2 text-[11px]"
                    onClick={() => applyPreset(preset)}
                  >
                    {preset.label}
                  </Button>
                ))}
              </div>
              <Button type="button" variant="ghost" size="icon" className="h-7 w-7 shrink-0" aria-label="Próximo mês" onClick={() => setViewMonth((current) => addMonths(current, 1))}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              {renderMonth(viewMonth)}
              {renderMonth(addMonths(viewMonth, 1))}
            </div>
            <div className="mt-2 flex items-center justify-between gap-2 border-t border-slate-100 pt-2 text-[11px] text-slate-500">
              <span>{selecting === "from" ? "Escolha a data inicial" : "Escolha a data final"}</span>
              <Button type="button" size="sm" className="h-7 text-[11px]" onClick={() => setOpen(false)}>
                Concluir
              </Button>
            </div>
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>
    </label>
  );
}
