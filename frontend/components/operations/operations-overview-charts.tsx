"use client";

import { useMemo } from "react";

import { OperationsTrendChart } from "@/components/operations/operations-trend-chart";
import { Button } from "@/components/ui/button";
import type {
  OperationTrendGranularity,
  OperationTrendSeries,
  OperationWorkScheduleOverview,
} from "@/lib/operations-api";
import {
  buildOpeningsTrendOption,
  buildSlaTrendOption,
  buildTeamProductionOption,
} from "@/lib/operations-chart-options";

const GRANULARITIES: Array<{
  value: OperationTrendGranularity;
  label: string;
}> = [
  { value: "day", label: "Dia" },
  { value: "week", label: "Semana" },
  { value: "month", label: "Mês" },
];

export function OperationsOverviewCharts({
  trends,
  workSchedule,
  isLoading,
  onGranularityChange,
}: {
  trends: OperationTrendSeries;
  workSchedule: OperationWorkScheduleOverview;
  isLoading: boolean;
  onGranularityChange: (granularity: OperationTrendGranularity) => void;
}) {
  const slaOption = useMemo(() => buildSlaTrendOption(trends), [trends]);
  const openingsOption = useMemo(
    () => buildOpeningsTrendOption(trends),
    [trends],
  );
  const teamOption = useMemo(
    () => buildTeamProductionOption(workSchedule),
    [workSchedule],
  );
  const measurablePoints = trends.points.filter(
    (point) => point.sla_cumulative_rate !== null,
  );
  const accumulatedSla = measurablePoints.at(-1)?.sla_cumulative_rate ?? null;
  const previousSla = measurablePoints.at(-2)?.sla_cumulative_rate ?? null;
  const variation =
    accumulatedSla !== null && previousSla !== null
      ? accumulatedSla - previousSla
      : null;
  const number = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });

  return (
    <section className="mt-4 space-y-4" aria-label="Tendências operacionais">
      <div className="flex flex-wrap items-center justify-between gap-3 px-1">
        <div>
          <p className="text-sm font-semibold text-slate-900">
            Evolução operacional
          </p>
          <p className="text-[11px] text-slate-500">
            Séries agregadas no servidor e alinhadas ao período selecionado.
          </p>
        </div>
        <div
          className="flex rounded-lg border border-slate-200 bg-slate-50 p-1"
          aria-label="Agrupamento dos gráficos"
        >
          {GRANULARITIES.map((item) => (
            <Button
              key={item.value}
              type="button"
              size="sm"
              variant={trends.granularity === item.value ? "default" : "ghost"}
              className="h-7 px-3 text-xs"
              disabled={isLoading}
              onClick={() => onGranularityChange(item.value)}
            >
              {item.label}
            </Button>
          ))}
        </div>
      </div>
      {isLoading && !trends.points.length ? (
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="h-96 animate-pulse rounded-2xl border bg-white" />
          <div className="h-96 animate-pulse rounded-2xl border bg-white" />
        </div>
      ) : trends.points.length ? (
        <>
          <div className="grid gap-2 rounded-xl border border-blue-100 bg-blue-50/60 p-3 text-xs text-blue-900 sm:grid-cols-3">
            <span>
              <strong>SLA acumulado do período:</strong>{" "}
              {accumulatedSla === null ? "-" : `${number.format(accumulatedSla)}%`}
            </span>
            <span>
              <strong>Variação do último agrupamento:</strong>{" "}
              {variation === null
                ? "-"
                : `${variation > 0 ? "+" : ""}${number.format(variation)} p.p.`}
            </span>
            <span>
              <strong>Meta:</strong> 80%
            </span>
          </div>
          <OperationsTrendChart
            eyebrow="SLA operacional"
            title="SLA e volume de finalizações"
            description="Linha contínua: acumulado ponderado. Linha tracejada: SLA do agrupamento."
            badge="Meta 80%"
            option={slaOption}
          />
          <div className="grid gap-4 xl:grid-cols-2">
            <OperationsTrendChart
              eyebrow="Entrada x saída"
              title="Aberturas x finalizações por dia"
              description="Aberturas operacionais, finalizações e saldo para enxergar pressão no fluxo."
              badge={
                trends.responsible_filter_active
                  ? "Aberturas sem filtro de responsável"
                  : "Todos os filtros"
              }
              option={openingsOption}
            />
            <OperationsTrendChart
              eyebrow="Capacidade"
              title="Produção por equipe/modelo de equipe"
              description="Volume finalizado por modelo e quantidade fora da jornada configurada."
              badge="Top modelos"
              option={teamOption}
            />
          </div>
        </>
      ) : (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-14 text-center text-sm text-slate-500">
          Nenhum evento encontrado para construir as tendências.
        </div>
      )}
    </section>
  );
}
