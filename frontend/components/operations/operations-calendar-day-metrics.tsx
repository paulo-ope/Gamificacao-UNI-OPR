"use client";

import {
  Activity,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Clock3,
  Gauge,
  MapPinned,
  Navigation,
  TimerReset,
} from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";

import type { OperationCalendarDayMetrics } from "@/lib/operations-api";

function duration(value: number | null) {
  if (value === null) return "—";
  const rounded = Math.round(value);
  if (rounded < 60) return `${rounded} min`;
  const hours = Math.floor(rounded / 60);
  const minutes = rounded % 60;
  return minutes ? `${hours}h ${minutes}min` : `${hours}h`;
}

function sumDurations(...values: Array<number | null>) {
  const validValues = values.filter((value): value is number => value !== null);
  if (!validValues.length) return null;
  return validValues.reduce((total, value) => total + value, 0);
}

function time(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "America/Porto_Velho",
  }).format(new Date(value));
}

function Metric({
  icon: Icon,
  label,
  value,
  helper,
}: {
  icon: typeof Clock3;
  label: string;
  value: string;
  helper: string;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-2.5 shadow-sm">
      <div className="flex items-center gap-1.5 text-slate-400">
        <Icon className="h-3.5 w-3.5" />
        <span className="text-[9px] font-semibold uppercase tracking-wide">
          {label}
        </span>
      </div>
      <p className="mt-1 text-base font-bold text-slate-950">{value}</p>
      <p className="mt-0.5 text-[10px] text-slate-500">{helper}</p>
    </div>
  );
}

export function OperationsCalendarDayMetricsPanel({
  metrics,
}: {
  metrics: OperationCalendarDayMetrics;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const slaLabel =
    metrics.sla_rate === null
      ? "—"
      : `${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(metrics.sla_rate)}%`;
  const activeTimeMinutes = sumDurations(
    metrics.total_execution_minutes,
    metrics.total_displacement_minutes,
  );
  const averageActiveTimeMinutes = sumDurations(
    metrics.average_execution_minutes,
    metrics.average_displacement_minutes,
  );
  const averageActiveTimePerDay =
    activeTimeMinutes !== null && metrics.active_days > 1
      ? activeTimeMinutes / metrics.active_days
      : null;
  const activeTimeHelper =
    averageActiveTimePerDay !== null
      ? `Média ${duration(averageActiveTimeMinutes)} por O.S. · ${duration(averageActiveTimePerDay)} por dia`
      : `Média ${duration(averageActiveTimeMinutes)} por O.S.`;

  return (
    <section
      className="border-b border-slate-200 bg-slate-50 px-3 py-2.5 sm:px-4"
      aria-label="Métricas operacionais do dia"
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
            Indicadores operacionais
          </p>
          <p className="truncate text-xs text-slate-600">
            Tempo ativo {duration(activeTimeMinutes)} · Atendimento{" "}
            {duration(metrics.total_execution_minutes)} · Deslocamento{" "}
            {duration(metrics.total_displacement_minutes)} · SLA {slaLabel}
          </p>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-8 shrink-0 text-xs"
          onClick={() => setIsExpanded((current) => !current)}
          aria-expanded={isExpanded}
        >
          {isExpanded ? (
            <ChevronUp className="h-3.5 w-3.5" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5" />
          )}
          {isExpanded ? "Ocultar indicadores" : "Ver indicadores"}
        </Button>
      </div>

      {isExpanded ? (
        <>
          <div className="mt-3 grid grid-cols-2 gap-2 lg:grid-cols-4">
            <Metric
              icon={TimerReset}
              label="Tempo Ativo"
              value={duration(activeTimeMinutes)}
              helper={activeTimeHelper}
            />
            <Metric
              icon={Activity}
              label="Atendimento total"
              value={duration(metrics.total_execution_minutes)}
              helper={`Média ${duration(metrics.average_execution_minutes)} por O.S.`}
            />
            <Metric
              icon={Navigation}
              label="Deslocamento total"
              value={duration(metrics.total_displacement_minutes)}
              helper={
                metrics.displacement_orders
                  ? `Média ${duration(metrics.average_displacement_minutes)} por O.S. · ${metrics.displacement_orders} O.S.`
                  : "Sem deslocamento mensurável"
              }
            />
            <Metric
              icon={Gauge}
              label="SLA do recorte"
              value={slaLabel}
              helper="O.S. mensuráveis no prazo"
            />
            <Metric
              icon={AlertTriangle}
              label="Janela operacional"
              value={`${time(metrics.first_displacement_at)} – ${time(metrics.last_finished_at)}`}
              helper={
                metrics.missing_operational_window_times
                  ? `Primeiro deslocamento → última finalização · ${metrics.missing_operational_window_times} O.S. sem tempos completos`
                  : `Primeiro deslocamento → última finalização · ${metrics.operational_window_orders} O.S.`
              }
            />
            <Metric
              icon={MapPinned}
              label="Filiais atendidas"
              value={String(metrics.attended_regionals.length)}
              helper={
                metrics.cross_regional_orders
                  ? `${metrics.cross_regional_orders} O.S. fora da referência`
                  : "Sem apoio externo identificado"
              }
            />
          </div>
          {metrics.attended_regionals.length ? (
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                Atendidas:
              </span>
              {metrics.attended_regionals.map((regional) => (
                <span
                  key={regional}
                  className="rounded-md border border-blue-100 bg-blue-50 px-2 py-1 text-[10px] font-medium text-blue-800"
                >
                  {regional}
                </span>
              ))}
            </div>
          ) : null}
          {Object.keys(metrics.type_counts).length ? (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {Object.entries(metrics.type_counts).map(([label, count]) => (
                <span
                  key={label}
                  className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[10px] font-medium text-slate-600"
                >
                  {label}: <strong className="text-slate-900">{count}</strong>
                </span>
              ))}
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
