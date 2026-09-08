"use client";

import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

import { OverviewBlock, type OverviewBlockState } from "@/components/overview/overview-block";
import { SummaryMetric } from "@/components/ui/summary-metric";
import { secondsLabel } from "@/lib/format-duration";
import { formatDateTime, formatInteger, formatIsoDate, formatPercent } from "@/lib/format";
import type { SupportOpaMetricComparison, SupportOpaOverview } from "@/lib/types";

function changeHint(metric: SupportOpaMetricComparison | undefined, unit: "count" | "percent" | "seconds") {
  if (!metric || metric.percentage_change === null) return "Sem período anterior comparável";
  const direction = metric.percentage_change >= 0 ? "+" : "";
  const previous =
    unit === "seconds"
      ? secondsLabel(metric.previous)
      : unit === "percent"
        ? formatPercent(metric.previous)
        : formatInteger(metric.previous);
  return `${direction}${formatPercent(metric.percentage_change)} vs. ${previous}`;
}

/**
 * Bloco macro do SGP Suporte. Usa o mesmo `/support/opa/overview` da tela do módulo (nenhuma
 * métrica nova, nenhuma conta refeita aqui) e só o período da Visão Geral - os filtros de O.S.
 * (modelo de equipe, filial, colaborador) não existem no domínio de atendimentos, então aplicá-los
 * aqui daria a falsa impressão de um número recortado.
 */
export function OverviewSupportCard({
  data,
  state,
  dateFrom,
  dateTo,
}: {
  data: SupportOpaOverview | null;
  state?: OverviewBlockState;
  dateFrom: string;
  dateTo: string;
}) {
  return (
    <OverviewBlock
      eyebrow="SGP Suporte"
      title="Atendimentos do período"
      subtitle="Somente o período - os filtros de O.S. não se aplicam a atendimentos."
      actions={
        <Link
          href="/suporte"
          className="inline-flex items-center gap-1 text-[11px] font-semibold text-uni-royal hover:underline"
        >
          Abrir módulo
          <ArrowUpRight className="h-3 w-3" />
        </Link>
      }
      state={state}
      deniedLabel="Seu perfil não tem acesso ao SGP Suporte."
    >
      <div className="grid grid-cols-2 gap-2.5 xl:grid-cols-4">
        <SummaryMetric
          label="Atendimentos"
          value={formatInteger(data?.total_attendances.current ?? null)}
          tone="blue"
          hint={changeHint(data?.total_attendances, "count")}
        />
        <SummaryMetric
          label="Em aberto"
          value={formatInteger(data?.open_attendances.current ?? null)}
          tone={data?.open_attendances.current ? "amber" : "slate"}
          hint={`Taxa de encerramento ${formatPercent(data?.closure_rate.current ?? null)}`}
        />
        <SummaryMetric
          label="TMA"
          value={secondsLabel(data?.average_duration_seconds.current ?? null)}
          tone="slate"
          hint={changeHint(data?.average_duration_seconds, "seconds")}
        />
        <SummaryMetric
          label="TMR (humano)"
          value={secondsLabel(data?.average_tmr_seconds.current ?? null)}
          tone="slate"
          hint={changeHint(data?.average_tmr_seconds, "seconds")}
        />
      </div>
      {data ? (
        <p className="mt-3 text-[11px] text-slate-500">
          {data.imported_data_window.max_opened_at
            ? `Dado importado do OPA Suite até ${formatDateTime(data.imported_data_window.max_opened_at)}.`
            : "Nenhum atendimento importado do OPA Suite ainda."}{" "}
          Período consultado: {formatIsoDate(dateFrom)} a {formatIsoDate(dateTo)}.
        </p>
      ) : null}
    </OverviewBlock>
  );
}
