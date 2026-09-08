"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { SchedulingDailyPoint } from "@/lib/scheduling-api";

import { isoDate, monthLabel, type MonthKey } from "./scheduling-format";

const WEEKDAY_LABELS = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];

// Intensidade só no número (não a célula inteira pintada), para o calendário ler como calendário
// (branco, compacto, com destaque), não como um mapa de calor sólido de ponta a ponta. Achado
// real de UX, 2026-08-31: preencher a célula inteira de cor saturada e mostrar "reagend." em cada
// uma deixava o mês inteiro parecendo um bloco maciço, difícil de escanear, e grande demais pra
// ser só o clique-para-o-dia (o gráfico de tendência ao lado é que carrega a leitura do mês).
function toneForRatio(ratio: number) {
  if (ratio <= 0) return "text-slate-300";
  if (ratio <= 0.25) return "text-amber-600";
  if (ratio <= 0.5) return "text-orange-600";
  if (ratio <= 0.75) return "text-red-600";
  return "text-red-800";
}

function CalendarSkeleton() {
  return (
    <div className="grid grid-cols-7 gap-1.5">
      {Array.from({ length: 35 }).map((_, index) => (
        <div key={index} className="h-12 animate-pulse rounded-lg bg-slate-100" />
      ))}
    </div>
  );
}

export function SchedulingMonthCalendar({
  month,
  dailyPoints,
  loading,
  onNavigate,
  onGoToday,
  onSelectDay,
  selectedDay,
}: {
  month: MonthKey;
  dailyPoints: SchedulingDailyPoint[];
  loading: boolean;
  onNavigate: (delta: number) => void;
  onGoToday: () => void;
  onSelectDay: (day: string) => void;
  selectedDay: string | null;
}) {
  const todayIso = isoDate(new Date());
  const byDate = new Map(dailyPoints.map((point) => [point.date, point]));
  const maxCount = Math.max(1, ...dailyPoints.map((point) => point.reschedule_events));

  const firstOfMonth = new Date(month.year, month.month - 1, 1);
  const daysInMonth = new Date(month.year, month.month, 0).getDate();
  const leadingBlanks = firstOfMonth.getDay(); // 0 = domingo
  const totalCells = Math.ceil((leadingBlanks + daysInMonth) / 7) * 7;

  const cells: Array<{ day: number; date: string } | null> = [];
  for (let index = 0; index < totalCells; index += 1) {
    const dayNumber = index - leadingBlanks + 1;
    if (dayNumber < 1 || dayNumber > daysInMonth) {
      cells.push(null);
      continue;
    }
    const pad = (n: number) => String(n).padStart(2, "0");
    cells.push({ day: dayNumber, date: `${month.year}-${pad(month.month)}-${pad(dayNumber)}` });
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Button type="button" variant="outline" size="icon" className="h-8 w-8" aria-label="Mês anterior" onClick={() => onNavigate(-1)}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <h2 className="min-w-40 text-center text-base font-semibold text-slate-950">{monthLabel(month)}</h2>
          <Button type="button" variant="outline" size="icon" className="h-8 w-8" aria-label="Próximo mês" onClick={() => onNavigate(1)}>
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
        <Button type="button" variant="ghost" size="sm" onClick={onGoToday}>
          Hoje
        </Button>
      </div>

      {loading ? (
        <CalendarSkeleton />
      ) : (
        <>
          <div className="mb-1 grid grid-cols-7 text-center text-[10px] font-semibold uppercase tracking-wide text-slate-400">
            {WEEKDAY_LABELS.map((label) => (
              <span key={label}>{label}</span>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-1.5">
            {cells.map((cell, index) => {
              if (!cell) return <div key={index} aria-hidden className="h-12" />;
              const point = byDate.get(cell.date);
              const count = point?.reschedule_events ?? 0;
              const ratio = count / maxCount;
              const toneClass = toneForRatio(ratio);
              const isToday = cell.date === todayIso;
              const isSelected = cell.date === selectedDay;
              return (
                <button
                  key={cell.date}
                  type="button"
                  disabled={!count}
                  onClick={() => onSelectDay(cell.date)}
                  aria-label={`Dia ${cell.day}: ${count} reagendamento(s)`}
                  title={`Dia ${cell.day}: ${count} reagendamento(s)`}
                  className={`relative flex h-12 flex-col items-center justify-center gap-0.5 rounded-lg border bg-white transition enabled:cursor-pointer enabled:hover:border-blue-300 enabled:hover:shadow-sm disabled:cursor-default ${
                    isSelected ? "border-slate-900 ring-2 ring-slate-900" : isToday ? "border-blue-400 ring-1 ring-blue-200" : "border-slate-200"
                  }`}
                >
                  <span className={`absolute left-1 top-1 text-[10px] ${isToday ? "font-semibold text-blue-600" : "text-slate-400"}`}>{cell.day}</span>
                  {count ? (
                    <span className={`text-sm font-bold tabular-nums leading-none ${toneClass}`}>{count}</span>
                  ) : null}
                </button>
              );
            })}
          </div>
          <div className="mt-3 flex items-center justify-end gap-1.5 text-[11px] text-slate-400">
            <span>Menos</span>
            <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
            <span className="h-2.5 w-2.5 rounded-full bg-orange-400" />
            <span className="h-2.5 w-2.5 rounded-full bg-red-400" />
            <span className="h-2.5 w-2.5 rounded-full bg-red-600" />
            <span>Mais reagendamentos</span>
          </div>
        </>
      )}
    </div>
  );
}
